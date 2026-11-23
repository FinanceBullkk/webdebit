"""ZALO-AGENT-01 PR-4a-1: bộ xử lý `money_images` (OCR ảnh của nhóm đã chọn tại máy, kho kết quả, đọc lại).

Không cần easyocr/torch/Pillow: engine giả (`FakeEngine`) trả ô chữ dựng sẵn theo byte ảnh, `prepare` giả không giải mã ảnh.
Kho live-sync và dữ liệu là bịa trong thư mục tạm. Không ssh, không kho thật.
"""

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import zalo_web_bundle as wb  # noqa: E402
from test_zalo_agent import BUNDLE_REMOTE, STATUS_REMOTE, Remote  # noqa: E402
from test_zalo_web_bundle import (  # noqa: E402
    GROUP,
    JPEG_LOCAL,
    KHACH,
    NOW,
    OTHER,
    FakeCdn,
    no_jxl,
    row,
    write_source,
)
from zalo_agent import __main__ as agent_main  # noqa: E402
from zalo_agent import cursor as cursors  # noqa: E402
from zalo_agent import gemini, ocr, reads  # noqa: E402
from zalo_agent.processors.money_images import MoneyImagesProcessor  # noqa: E402
from zalo_agent.source import LiveSync  # noqa: E402

JXL_AS_JPEG = b"\xff\xd8\xff\xe0jxl-decoded-to-jpeg"
SHA_LOCAL, SHA_JXL = hashlib.sha256(JPEG_LOCAL).hexdigest(), hashlib.sha256(JXL_AS_JPEG).hexdigest()


def box(x0, y0, x1, y1, text, conf=0.95):
    return {"b": [x0, y0, x1, y1], "t": text, "c": conf}


TRANSFER = [box(40, 100, 700, 140, "Chuyển khoản thành công"), box(40, 300, 700, 380, "1.500.000 VND"),
            box(40, 420, 400, 450, "Người nhận"), box(40, 460, 400, 490, "Số tài khoản"), box(40, 500, 400, 530, "Vietcombank"),
            box(40, 560, 600, 590, "19/11/2026 15:02"), box(40, 600, 600, 625, "Phí giao dịch 0 VND", 0.9)]
PHOTO = [box(10, 10, 300, 40, "CONT 123 seal"), box(10, 50, 300, 80, "nhiệt độ 4.5")]


class FakeEngine:
    """Trả ô chữ theo byte ảnh (`script`), mặc định là ảnh không có chữ tiền. Đếm số lần đọc."""
    name = "fake"

    def __init__(self, version="1.0+t", script=None):
        self.version, self.script, self.calls, self.broken = version, script or {}, [], False

    def read(self, image):
        if self.broken:
            raise RuntimeError("engine hỏng")
        self.calls.append(image)
        return self.script.get(image, PHOTO)


class Missing(FakeEngine):
    """Máy này không có easyocr: `version` ném OcrUnavailable như EasyOcr thật."""
    @property
    def version(self):
        raise ocr.OcrUnavailable("easyocr")

    @version.setter
    def version(self, value):
        pass


class Inline:
    """Executor chạy ngay trong luồng gọi: test xác định, không cần chờ luồng nền."""
    def submit(self, function, *args):
        future = Future()
        future.set_result(function(*args))
        return future


class Stuck:
    """Executor mà việc không bao giờ xong: mô phỏng OCR đang chạy 14 giây."""
    def __init__(self):
        self.jobs = 0

    def submit(self, function, *args):
        self.jobs += 1
        return Future()


SKIPPED = {"wechat": 0, "skipped_no_media": 0, "skipped_not_image": 0, "skipped_no_file": 0, "skipped_too_old": 0}


def offline(url):
    raise wb.BundleError("offline")


def prepare(data):
    return data, (100, 200)   # `read` của engine giả nhận lại đúng byte ảnh


class Live:
    """Bắt chước live_sync: ghi lại messages.jsonl, thêm changes-N, revision.json ghi sau cùng."""
    def __init__(self, directory: Path):
        self.dir, self.count = directory, 0

    def revision(self) -> int:
        return json.loads((self.dir / "revision.json").read_text(encoding="utf-8"))["revision"]

    def add_image(self, cid, data: bytes, mime="image/jpeg", stamp=1_700_000_100_000, same_file=None):
        self.count += 1
        key = same_file or hashlib.sha256(f"id{self.count}".encode()).hexdigest()
        (self.dir / "media-store" / (key + (".jxl" if mime == "image/jxl" else ".jpg"))).write_bytes(data)
        index = json.loads((self.dir / "media-index.json").read_text(encoding="utf-8"))
        index["items"][key] = {"client_message_id": f"cm-img{self.count}", "mime": mime, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        (self.dir / "media-index.json").write_text(json.dumps(index), encoding="utf-8")
        message = row(cid, f"img{self.count}", KHACH, stamp + self.count, {"title": ""}, 2, client=f"cm-img{self.count}")
        with (self.dir / "messages.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(message) + "\n")
        revision = self.revision() + 1
        (self.dir / f"changes-{revision}.json").write_text(json.dumps({"revision": revision, "added": [message["message_id"]]}), encoding="utf-8")
        (self.dir / "revision.json").write_text(json.dumps({"revision": revision}), encoding="utf-8")
        return message["message_id"]


class MoneyBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src, self.root = base / "live-sync", base / "agent"
        self.src.mkdir()
        write_source(self.src)
        (self.src / "baseline-manifest.json").write_text(json.dumps({"messages_sha256": "a" * 64}), encoding="utf-8")
        wb.Source(self.src).save_selection([GROUP])
        self.base, self.now = base, NOW
        self.live, self.feed = LiveSync(self.src), Live(self.src)
        self.engine = FakeEngine(script={JPEG_LOCAL: TRANSFER})
        self.fetch = offline   # CDN: mặc định không tải được gì, chỉ ảnh có ở máy vào gói (ca CDN tự đặt `self.fetch`)
        self.build()

    def build(self):
        """Dựng gói chat như bộ xử lý `bundle` (A2: nguồn ảnh của `money_images`), từ live-sync bịa."""
        self.builds = getattr(self, "builds", 0) + 1   # mỗi lần dựng một thư mục `data-<giờ>` mới, như bộ xử lý thật
        return wb.build(wb.Source(self.src), self.root / "bundle", fetch=self.fetch, transcode=lambda data: JXL_AS_JPEG,
                        now=self.now + self.builds, max_age_days=None)

    def make(self, **kwargs):
        args = {"engine": self.engine, "executor": Inline(), "gemini": gemini.Gemini({}),   # gửi ra ngoài tắt, không đọc môi trường thật
                "prepare": prepare, "clock": lambda: self.now, "max_age_days": None, **kwargs}
        return MoneyImagesProcessor(self.live, self.root / "state", self.root / "reads", **args)

    def drain(self, processor, limit=20, build=True):
        """Dựng lại gói rồi chạy step tới khi hàng chờ hết (mỗi step thu một ảnh rồi nộp ảnh kế)."""
        if build:
            self.build()
        processor.step()
        for _ in range(limit):
            if not processor.counts()["pending"] and processor.future is None:
                break
            processor.step()
        return processor.step()

    def stored(self, sha):
        return reads.load(self.root / "reads", sha, "fake", self.engine.version)


class AnalyseTest(unittest.TestCase):
    def test_transfer_screenshot_amount_time_and_bank(self):
        found = ocr.analyse(TRANSFER)
        self.assertTrue(found["is_money"])
        self.assertEqual((found["amount_vnd"], found["bank"], found["txn_time"]), (1_500_000, "VIETCOMBANK", "2026-11-19T15:02:00+07:00"))
        self.assertTrue(found["unique"])
        self.assertGreaterEqual(found["hits"], 2)
        self.assertTrue(ocr.is_confident(found))
        self.assertEqual(ocr.verdict(found), "ocr")

    def test_photo_has_no_money_signal_and_is_not_confident(self):
        found = ocr.analyse(PHOTO)
        self.assertFalse(found["is_money"])
        self.assertEqual((ocr.verdict(found), found["amount_vnd"]), ("none", None))

    def test_year_time_and_account_number_are_not_amounts(self):
        found = ocr.analyse([box(0, 0, 300, 30, "Số tài khoản 0123456789012"), box(0, 40, 300, 70, "ngày 19/11/2026 lúc 15:02"),
                             box(0, 80, 300, 110, "Vietcombank")])
        self.assertIsNone(found["amount_vnd"])
        self.assertFalse(ocr.is_confident(found))

    def test_plain_digits_need_a_unit_and_a_separate_unit_box_counts(self):
        self.assertEqual(ocr.analyse([box(0, 0, 200, 60, "500000 VND")])["amount_vnd"], 500_000)
        self.assertIsNone(ocr.analyse([box(0, 0, 200, 60, "500000")])["amount_vnd"])
        split = ocr.analyse([box(0, 0, 200, 60, "2.000.000"), box(210, 5, 280, 55, "VND")])
        self.assertEqual(split["amount_vnd"], 2_000_000)
        self.assertTrue(split["is_money"])   # số kèm VND là dấu hiệu tiền dù chưa đủ 2 từ khóa

    def test_two_equally_big_different_amounts_are_not_confident(self):
        found = ocr.analyse([*TRANSFER[:1], box(40, 300, 700, 380, "1.500.000 VND"), box(40, 400, 700, 480, "2.500.000 VND"),
                             box(40, 500, 400, 530, "Vietcombank")])
        self.assertFalse(found["unique"])
        self.assertEqual(ocr.verdict(found), "unsure")

    def test_low_confidence_and_few_keywords_are_not_confident_and_threshold_is_configurable(self):
        weak = ocr.analyse([{**item, "c": 0.5} if "VND" in item["t"] else item for item in TRANSFER])
        self.assertEqual(ocr.verdict(weak), "unsure")
        self.assertFalse(ocr.is_confident(ocr.analyse(TRANSFER), 0.99))
        with patch.dict(os.environ, {"ZALO_AGENT_OCR_CONFIDENCE": "0.4"}):
            self.assertEqual(ocr.verdict(weak), "ocr")
        one_keyword = ocr.analyse([box(0, 0, 400, 80, "1.500.000 đ"), box(0, 100, 300, 130, "Vietcombank")])
        self.assertTrue(one_keyword["is_money"])
        self.assertFalse(ocr.is_confident(one_keyword))   # chỉ 1 từ khóa

    def test_invalid_date_gives_no_time(self):
        self.assertIsNone(ocr.when("31/02/2026 10:00"))
        self.assertEqual(ocr.when("05/11/2026"), "2026-11-05")


class FinishedTransactionTest(unittest.TestCase):
    """A3: luật phân tích `a3` rút từ 42 ảnh có dấu hiệu tiền trên máy có Zalo (23/11/2026). Chữ trong ca dưới là bịa theo bố cục, không chép ảnh thật."""

    def test_payment_request_and_qr_code_without_a_finished_transaction_are_not_confident(self):
        invoices = [box(0, 40, 120, 60, "Tên cty"), box(130, 40, 250, 60, "Số hóa đơn"), box(260, 40, 360, 60, "Ngày HĐ"),
                    box(370, 40, 470, 60, "Số tiền"), box(0, 80, 250, 100, "CONG TY TNHH MAU"), box(260, 80, 360, 100, "15/06/2026"),
                    box(370, 80, 600, 130, "1.500.000 VND"), box(0, 140, 300, 160, "Vietcombank")]
        qr = [box(0, 0, 400, 40, "Quét mã QR để thanh toán"), box(0, 60, 400, 120, "Số tiền 1.500.000 VND"), box(0, 140, 300, 170, "Vietcombank")]
        for boxes in (invoices, qr):
            found = ocr.analyse(boxes)
            self.assertTrue(found["is_money"] and found["unique"] and found["hits"] >= 2)
            self.assertFalse(found["done"])
            self.assertEqual(ocr.verdict(found), "unsure")   # có dấu hiệu tiền nhưng giao dịch chưa xong: không thành khoản thu chắc

    def test_finished_transaction_markers_seen_on_real_receipts(self):
        english = [box(40, 100, 500, 140, "Transaction successful"), box(40, 300, 600, 380, "1.500.000 VND"), box(40, 420, 300, 450, "MBBank"),
                   box(40, 460, 300, 490, "Account name")]
        approved = [box(100, 20, 300, 60, "Chuyển tiền"), box(320, 20, 360, 60, "Đã"), box(420, 22, 520, 58, "duyệt"), box(365, 21, 415, 59, "phê"),
                    box(100, 300, 600, 360, "Số tiền 1.500.000 VND"), box(100, 400, 400, 440, "Vietcombank")]
        for boxes in (TRANSFER, english, approved):   # nhãn "Đã phê duyệt" bị OCR tách ba ô lệch thứ tự: ghép theo dòng
            self.assertTrue(ocr.analyse(boxes)["done"])
            self.assertEqual(ocr.verdict(ocr.analyse(boxes)), "ocr")

    def test_a_stored_read_from_the_old_rule_has_no_done_field_and_is_not_confident(self):
        old = {key: value for key, value in ocr.analyse(TRANSFER).items() if key not in ("done", "direction", "txn_ref")}
        self.assertFalse(ocr.is_confident(old))   # chỉ đúng khi đã qua `refresh` theo luật mới

    def test_time_comes_from_one_line_dot_times_count_and_the_status_bar_clock_does_not(self):
        rows = [box(10, 5, 80, 25, "09:41"), box(40, 100, 500, 140, "Chuyển khoản thành công"),
                box(40, 300, 600, 380, "1.500.000 VND"), box(40, 500, 300, 530, "Vietcombank"),
                box(40, 560, 250, 590, "Thời gian"), box(300, 560, 600, 590, "19/11/2026 15.02")]
        self.assertEqual(ocr.analyse(rows)["txn_time"], "2026-11-19T15:02:00+07:00")
        no_clock = [box(10, 5, 80, 25, "09:41"), box(40, 560, 300, 590, "19/11/2026")]
        self.assertEqual(ocr.analyse(no_clock)["txn_time"], "2026-11-19")   # không ghép ngày với giờ của dòng khác
        self.assertEqual(ocr.analyse([box(0, 0, 300, 30, "31/02/2026 10:00")])["txn_time"], None)

    def test_approval_screen_takes_the_approval_time_not_the_request_time(self):
        rows = [box(100, 600, 350, 640, "Ngày yêu cầu"), box(720, 600, 1000, 640, "19/11/2026 10.32"),
                box(100, 680, 390, 720, "Ngày phê duyệt"), box(720, 680, 1000, 720, "19/11/2026 12:15")]
        self.assertEqual(ocr.analyse(rows)["txn_time"], "2026-11-19T12:15:00+07:00")

    def test_reference_number_is_taken_from_its_labelled_line_never_an_account_number(self):
        rows = [box(30, 600, 230, 630, "Reference number"), box(400, 600, 650, 630, "123456789012345678"),
                box(30, 650, 180, 680, "Transfer code"), box(400, 650, 650, 680, "FT12345678901234")]
        self.assertEqual(ocr.analyse(rows)["txn_ref"], "123456789012345678")
        self.assertEqual(ocr.analyse([box(0, 0, 200, 30, "Mã giao dịch: ft26323123456")])["txn_ref"], "FT26323123456")
        self.assertIsNone(ocr.analyse([box(0, 0, 200, 30, "Số tài khoản"), box(250, 0, 450, 30, "0123456789")])["txn_ref"])
        self.assertIsNone(ocr.analyse([box(0, 0, 200, 30, "Mã giao dịch"), box(250, 0, 450, 30, "Xem chi tiết")])["txn_ref"])
        # review #599: số điện thoại, tên kèm năm sinh, chuỗi trong ô nội dung không phải mã; chỉ lấy giá trị ngay sau nhãn
        self.assertIsNone(ocr.analyse([box(0, 0, 200, 30, "Mã GD"), box(250, 0, 450, 30, "0912345678")])["txn_ref"])
        self.assertIsNone(ocr.analyse([box(0, 0, 200, 30, "Reference number"), box(250, 0, 450, 30, "NGUYENVANA1990")])["txn_ref"])
        self.assertIsNone(ocr.analyse([box(0, 0, 200, 30, "Nội dung"), box(250, 0, 650, 30, "ma giao dich 123456789 chuyen tien")])["txn_ref"])
        self.assertIsNone(ocr.analyse([box(0, 0, 200, 30, "Mã giao dịch"), box(250, 0, 350, 30, "Xem"), box(360, 0, 600, 30, "123456789012")])["txn_ref"])

    def test_direction_from_the_sign_of_the_amount_then_from_words(self):
        self.assertEqual(ocr.analyse([box(0, 0, 400, 60, "+1.500.000 VND"), box(0, 80, 300, 110, "Vietcombank")])["direction"], "in")
        self.assertEqual(ocr.analyse([box(0, 0, 400, 60, "-1.500.000 VND"), box(0, 80, 300, 110, "Vietcombank")])["direction"], "out")
        self.assertEqual(ocr.analyse([box(0, 0, 400, 60, "−1.500.000 VND"), box(0, 80, 300, 110, "Vietcombank")])["direction"], "out")   # dấu trừ Unicode
        self.assertEqual(ocr.analyse(TRANSFER)["direction"], "out")   # biên lai chuyển khoản: tiền ra của người chụp
        self.assertEqual(ocr.analyse([box(0, 0, 400, 60, "1.500.000 VND"), box(0, 80, 300, 110, "Nhận tiền")])["direction"], "in")
        self.assertIsNone(ocr.analyse([box(0, 0, 400, 60, "1.500.000 VND")])["direction"])

    def test_a_finished_receipt_whose_amount_lost_its_dots_still_waits_for_a_person(self):
        # review #599: biên lai thật, OCR đọc "5000000" và "VND" thành hai ô: không có số ứng viên nhưng giao dịch đã xong
        found = ocr.analyse([box(0, 0, 400, 40, "Chuyển khoản thành công"), box(0, 100, 300, 160, "5000000"), box(310, 105, 380, 155, "VND"),
                             box(0, 200, 300, 230, "Vietcombank")])
        self.assertTrue(found["done"])
        self.assertEqual((found["is_money"], found["amount_vnd"], ocr.verdict(found)), (True, None, "unsure"))

    def test_done_markers_from_review_and_linear_time_matching(self):
        for marker in ("Thành công", "Successful", "Payment successful", "Transfer completed", "Đã chuyển tiền"):
            self.assertTrue(ocr.analyse([box(0, 0, 300, 30, marker)])["done"], marker)
        hostile = "19/11/2026" + " " * 100_000 + "x"
        started = time.perf_counter()
        self.assertEqual(ocr.when(hostile), "2026-11-19")
        self.assertLess(time.perf_counter() - started, 2)   # trước đây hai \s* liền nhau: bậc hai (100k khoảng trắng mất vài phút)

    def test_beneficiary_details_without_any_amount_are_not_a_money_image(self):
        # 12/16 ảnh "cần người xem" trên máy thật là ảnh cắt phần người hưởng: có từ khóa, không có số tiền nào.
        found = ocr.analyse([box(0, 0, 300, 30, "Thông tin người hưởng"), box(0, 40, 400, 70, "Chuyển tiền nhanh liên ngân hàng 24/7"),
                             box(0, 80, 300, 110, "Tài khoản người hưởng"), box(320, 80, 520, 110, "0123456789"),
                             box(0, 120, 300, 150, "Tên ngân hàng hưởng"), box(320, 120, 600, 150, "Ngân hàng TMCP Á Châu")])
        self.assertGreaterEqual(found["hits"], 2)
        self.assertEqual((found["is_money"], found["amount_vnd"], ocr.verdict(found)), (False, None, "none"))

    def test_amounts_in_another_currency_never_become_amount_vnd(self):
        for boxes, code in (([box(0, 0, 400, 60, "USD 67,435.89"), box(0, 80, 300, 110, "Chuyển tiền"), box(0, 120, 300, 150, "Tài khoản")], "USD"),
                            ([box(0, 0, 60, 60, "¥"), box(70, 0, 400, 60, "1,500"), box(0, 80, 300, 110, "Transaction successful")], "CNY"),
                            ([box(0, 0, 300, 60, "1,500.00 元"), box(0, 80, 300, 110, "转账成功")], "CNY")):
            found = ocr.analyse(boxes)
            self.assertTrue(found["is_money"])   # vẫn là ảnh tiền chờ người xem, không bị bỏ qua
            self.assertEqual((found["amount_vnd"], found["confidence"], found["currency"]), (None, None, code))
            self.assertEqual(ocr.verdict(found), "unsure")
        self.assertEqual(ocr.analyse(TRANSFER)["currency"], "VND")
        label = ocr.analyse([box(0, 0, 200, 60, "Amount (USD/VND)"), box(220, 0, 500, 60, "1.500.000"), box(0, 80, 300, 110, "Vietcombank"),
                             box(0, 120, 300, 150, "Số tiền")])
        self.assertEqual((label["currency"], label["amount_vnd"]), (None, 1_500_000))   # nhãn ghi cả USD lẫn VND không biến số thành USD
        self.assertNotEqual(ocr.analyse([box(0, 0, 300, 60, "Mã $ khuyến mãi"), box(310, 0, 600, 60, "1.500.000 đ")])["currency"], "USD")
        self.assertIsNone(ocr.analyse([box(0, 0, 400, 60, "1.500.000"), box(0, 80, 300, 110, "Vietcombank"), box(0, 120, 300, 150, "Số tiền")])["currency"])


class ProcessorTest(MoneyBase):
    def test_reads_images_of_selected_groups_only_and_stores_the_result_per_engine_and_version(self):
        self.feed.add_image(OTHER, b"\xff\xd8\xff\xe0other-group")   # nhóm chưa chọn: không được đọc
        processor = self.make()
        result = self.drain(processor)
        self.assertEqual(set(processor.state()["members"]), {SHA_LOCAL, SHA_JXL})   # khóa = băm byte gói chat sẽ lưu (JXL đã chuyển JPEG)
        self.assertEqual(len(self.engine.calls), 2)
        saved = self.stored(SHA_LOCAL)
        self.assertEqual((saved["engine"], saved["version"], saved["amount_vnd"], saved["bank"], saved["is_money"]), ("fake", "1.0+t", 1_500_000, "VIETCOMBANK", True))
        self.assertEqual(saved["size"], [100, 200])
        self.assertTrue(saved["boxes"])   # chữ OCR và ô chữ có trong kho (chỉ ở máy)
        # 3 tin ảnh của nhóm chỉ có trên CDN (không tải được ở đây) không vào hàng đọc và được đếm (A2)
        self.assertEqual(result["counts"], {"read": 2, "pending": 0, "failed": 0, "review": 0, "asking": 0, **SKIPPED, "skipped_no_media": 3})
        self.assertEqual((result["action"], result["error"], result["revision"]), ("idle", None, self.feed.revision()))
        self.assertEqual(sorted(path.name for path in (self.root / "reads").iterdir()), sorted([SHA_LOCAL, SHA_JXL]))

    def test_drain_counts_images_leaving_the_queue_and_when_the_queue_filled(self):
        waiting = self.make(executor=Stuck()).step()
        self.assertEqual(waiting["drain"], {"done_1h": 0, "pending_since": cursors.now_iso(self.now), "last_done_at": None})
        processor = self.make()
        self.assertEqual(self.drain(processor)["drain"], {"done_1h": 2, "pending_since": None, "last_done_at": cursors.now_iso(self.now)})
        self.now += 3601
        self.assertEqual(processor.step()["drain"]["done_1h"], 0)   # quá 60 phút thì không còn tính vào tốc độ

    def test_unselected_group_image_never_enters_the_store(self):
        other = self.feed.add_image(OTHER, b"\xff\xd8\xff\xe0other-group")
        self.assertTrue(other)
        processor = self.make()
        self.drain(processor)
        self.assertFalse((self.root / "reads" / hashlib.sha256(b"\xff\xd8\xff\xe0other-group").hexdigest()).exists())

    def test_same_picture_in_two_messages_is_read_once(self):
        self.feed.add_image(GROUP, JPEG_LOCAL)   # cùng byte với ảnh sẵn có, thêm một tin nữa
        processor = self.make()
        self.drain(processor)
        self.assertEqual(len(self.engine.calls), 2)
        self.assertEqual(processor.counts()["read"], 2)

    def test_same_engine_and_version_is_not_read_again_new_version_reads_and_keeps_the_old_file(self):
        self.drain(self.make())
        before = len(self.engine.calls)
        again = self.make()   # tiến trình mới, con trỏ từ đĩa
        self.drain(again)
        self.assertEqual(len(self.engine.calls), before)
        # Đổi version (đổi engine hoặc luật phân tích): dựng lại, đọc lại, kết quả cũ nằm cạnh kết quả mới.
        self.engine.version = "2.0+t"
        for path in (self.root / "state").glob("money_images.json"):
            path.unlink()
        self.drain(self.make())
        self.assertEqual(len(self.engine.calls), before + 2)
        self.assertEqual(sorted(path.name for path in (self.root / "reads" / SHA_LOCAL).iterdir()), ["fake@1.0+t.json", "fake@2.0+t.json"])
        self.assertEqual(len(reads.for_image(self.root / "reads", SHA_LOCAL)), 2)

    def test_delta_reads_only_the_new_image_and_unrelated_revisions_do_nothing(self):
        processor = self.make()
        self.drain(processor)
        calls = len(self.engine.calls)
        self.feed.add_image(GROUP, b"\xff\xd8\xff\xe0new-photo")
        self.assertFalse(processor.wants_work())   # gói chưa dựng lại: chưa có gì mới cho bộ xử lý này
        self.build()   # bộ xử lý `bundle` chạy trước trong cùng vòng lặp
        self.assertTrue(processor.wants_work())
        self.drain(processor)
        self.assertEqual(len(self.engine.calls), calls + 1)
        self.assertEqual(processor.counts()["read"], 3)
        self.assertFalse(processor.wants_work())

    def test_cursor_is_kept_on_disk_queue_survives_a_restart(self):
        processor = self.make(executor=Stuck())
        result = processor.step()
        self.assertEqual((result["counts"]["pending"], result["counts"]["read"]), (2, 0))
        cursor = json.loads((self.root / "state" / "money_images.json").read_text(encoding="utf-8"))
        self.assertEqual((cursor["revision"], len(cursor["todo"])), (87, 2))
        revived = self.make()
        self.assertEqual(self.drain(revived)["counts"]["read"], 2)

    def test_newest_image_goes_first(self):
        newer = self.feed.add_image(GROUP, b"\xff\xd8\xff\xe0newest", stamp=1_800_000_000_000)
        self.assertTrue(newer)
        self.build()
        processor = self.make()
        processor.step()
        processor.step()
        self.assertEqual(self.engine.calls[0], b"\xff\xd8\xff\xe0newest")

    def test_deselected_group_leaves_the_exportable_set_after_the_rebuild(self):
        wb.Source(self.src).save_selection([GROUP, OTHER])
        self.feed.add_image(OTHER, b"\xff\xd8\xff\xe0other-group")
        processor = self.make()
        self.drain(processor)
        other_sha = hashlib.sha256(b"\xff\xd8\xff\xe0other-group").hexdigest()
        self.assertIn(other_sha, processor.state()["members"])
        wb.Source(self.src).save_selection([GROUP])
        processor.step()   # gói chưa dựng lại: vẫn còn ảnh của nhóm vừa bỏ (export chờ, xem test_zalo_agent_money_external)
        self.build()
        processor.step()
        self.assertNotIn(other_sha, processor.state()["members"])
        self.assertEqual(set(processor.state()["members"]), {SHA_LOCAL, SHA_JXL})

    def test_unreadable_images_are_dropped_after_three_tries_and_never_fail_the_processor(self):
        data = b"\xff\xd8\xff\xe0bad-photo"
        self.feed.add_image(GROUP, data)
        self.build()
        (self.root / "bundle" / "media" / (hashlib.sha256(data).hexdigest() + ".jpg")).write_bytes(b"\xff\xd8\xff\xe0changed")   # file sai băm
        processor = self.make()
        result = self.drain(processor, 40, build=False)
        self.assertEqual((result["error"], result["counts"]["failed"], result["counts"]["pending"], result["counts"]["read"]), (None, 1, 0, 2))
        self.assertTrue(processor.wants_work() is False)

    def test_engine_error_on_one_image_does_not_stop_the_others(self):
        self.engine.broken = True
        processor = self.make()
        result = self.drain(processor, 40)
        self.assertEqual((result["error"], result["counts"]["failed"], result["counts"]["read"]), (None, 2, 0))

    def test_missing_engine_reports_ocr_unavailable_and_keeps_the_queue(self):
        processor = self.make(engine=Missing())
        result = processor.step()
        self.assertEqual((result["action"], result["error"]), ("idle", "ocr_unavailable"))
        self.assertFalse((self.root / "reads").exists())
        self.assertEqual(self.drain(self.make())["counts"]["read"], 2)   # engine có lại: đọc bình thường

    def test_dry_run_reads_but_does_not_save_the_cursor(self):
        processor = self.make(dry_run=True)
        self.assertEqual(self.drain(processor)["counts"]["read"], 2)
        self.assertFalse((self.root / "state" / "money_images.json").exists())
        self.assertTrue((self.root / "reads" / SHA_LOCAL).is_dir())

    def test_no_selected_group_reads_nothing(self):
        (self.src / "web-groups.json").write_text(json.dumps({"conversations": []}), encoding="utf-8")
        processor = self.make()
        self.assertFalse(processor.wants_work())
        self.assertEqual(processor.step()["counts"], {"read": 0, "pending": 0, "failed": 0, "review": 0, "asking": 0, **SKIPPED})
        self.assertEqual(self.engine.calls, [])

    def test_unsure_money_image_counts_as_review(self):
        self.engine.script[JPEG_LOCAL] = [*TRANSFER[:1], box(0, 100, 600, 200, "1.500.000 đ", 0.4), box(0, 300, 300, 330, "Vietcombank")]
        result = self.drain(self.make())
        self.assertEqual(result["counts"]["review"], 1)


def strict(boxes):
    """Luật phân tích "mới" giả: như cũ nhưng không nhận từ khóa nào, nên ảnh chuyển khoản thành "không chắc"."""
    return {**ANALYSE(boxes), "hits": 0}


ANALYSE = ocr.analyse


class AnalysisVersionTest(MoneyBase):
    """A1: phiên bản ô chữ (engine + tiền xử lý, tên file kho) tách khỏi phiên bản luật phân tích (trường `analysis` trong file)."""

    def test_easyocr_version_follows_the_engine_and_preprocessing_not_the_analysis_rule(self):
        with patch.object(ocr.metadata, "version", lambda name: "1.7.2"):
            self.assertEqual(ocr.EasyOcr(command=["x"]).version, "1.7.2+a2")   # đúng tên 52 file kho cũ `easyocr@1.7.2+a2.json`
            with patch.object(ocr, "ANALYSIS", "a9"):
                self.assertEqual(ocr.EasyOcr(command=["x"]).version, "1.7.2+a2")
            with patch.object(ocr, "PREPARE", "p9"):
                self.assertEqual(ocr.EasyOcr(command=["x"]).version, "1.7.2+p9")

    def test_new_analysis_rule_reanalyses_stored_boxes_without_calling_the_engine(self):
        self.drain(self.make())
        calls = len(self.engine.calls)
        self.assertEqual(self.stored(SHA_LOCAL)["analysis"], ocr.ANALYSIS)
        boxes = self.stored(SHA_LOCAL)["boxes"]
        with patch.object(ocr, "ANALYSIS", "a9"), patch.object(ocr, "analyse", strict):
            newer = self.make()   # tiến trình mới, con trỏ từ đĩa còn `analysis` cũ
            result = self.drain(newer)
            self.assertEqual(len(self.engine.calls), calls)   # không OCR lại ảnh nào
            members = newer.state()["members"]
            self.assertEqual((members[SHA_LOCAL]["verdict"], members[SHA_LOCAL]["by"]), ("unsure", "human"))   # trước là ocr; gửi ra ngoài tắt
            self.assertEqual((members[SHA_JXL]["verdict"], members[SHA_JXL]["by"]), ("none", None))   # ảnh không chữ tiền vẫn vậy
            self.assertEqual(result["counts"]["review"], 1)
            saved = self.stored(SHA_LOCAL)
            self.assertEqual((saved["analysis"], saved["hits"], saved["boxes"]), ("a9", 0, boxes))   # cùng file, ô chữ giữ nguyên
            self.assertEqual(sorted(path.name for path in (self.root / "reads" / SHA_LOCAL).iterdir()), ["fake@1.0+t.json"])
            self.assertEqual(newer.state()["analysis"], "a9")
            fresh = b"\xff\xd8\xff\xe0new-image"
            self.feed.add_image(GROUP, fresh)   # ảnh mới dưới luật mới: OCR một lần, ghi kèm `analysis` mới
            self.drain(newer)
            self.assertEqual(len(self.engine.calls), calls + 1)
            self.assertEqual(self.stored(hashlib.sha256(fresh).hexdigest())["analysis"], "a9")

    def test_old_store_files_without_an_analysis_field_are_used_and_not_read_again(self):
        legacy = {"engine": "fake", "version": self.engine.version, "read_at": "2026-11-20T00:00:00Z", "size": [100, 200], "boxes": TRANSFER,
                  **dict(ocr.analyse(TRANSFER).items()), "amount_vnd": 7_000_000}   # như file trước A1: không có `analysis`
        reads.save(self.root / "reads", SHA_LOCAL, legacy)
        path = reads.path(self.root / "reads", SHA_LOCAL, "fake", self.engine.version)
        before = path.read_bytes()
        with patch.object(ocr, "ANALYSIS", ocr.LEGACY_ANALYSIS):   # agent chạy đúng luật đã sinh file cũ
            processor = self.make()
            self.drain(processor)
            self.assertEqual(self.engine.calls, [JXL_AS_JPEG])   # chỉ ảnh chưa có trong kho được OCR
            self.assertEqual(path.read_bytes(), before)   # cùng luật: dùng nguyên, không ghi lại
            self.assertEqual(processor.primary_read(reads.for_image(self.root / "reads", SHA_LOCAL))["amount_vnd"], 7_000_000)
        with patch.object(ocr, "ANALYSIS", "a9"):
            newer = self.make()
            self.drain(newer)
            self.assertEqual(self.engine.calls, [JXL_AS_JPEG])
            self.assertEqual((self.stored(SHA_LOCAL)["amount_vnd"], self.stored(SHA_LOCAL)["analysis"]), (1_500_000, "a9"))


class RereadTest(MoneyBase):
    def test_reread_fills_a_new_version_since_a_date_and_skips_what_exists(self):
        processor = self.make()
        self.drain(processor)
        newer = self.make(engine=FakeEngine("2.0+t", {JPEG_LOCAL: TRANSFER}))
        counts = newer.reread(newer.engine, 0)
        self.assertEqual(counts, {"wanted": 2, "read": 2, "had": 0, "failed": 0})
        self.assertEqual(newer.reread(newer.engine, 0), {"wanted": 2, "read": 0, "had": 2, "failed": 0})   # cùng engine và phiên bản: không đọc lại
        self.assertEqual(len(reads.for_image(self.root / "reads", SHA_LOCAL)), 2)   # kết quả cũ vẫn còn cạnh bên
        future = self.make(engine=FakeEngine("3.0+t"))
        self.assertEqual(future.reread(future.engine, 9_999_999_999_999)["wanted"], 0)   # --since sau mọi ảnh

    def test_cli_prints_counts_only(self):
        self.drain(self.make())

        class Wrapped(FakeEngine):
            def __init__(self):
                super().__init__("9.9+t", {JPEG_LOCAL: TRANSFER})
        def processor(live, state, reads_dir, dry_run=False):
            self.assertTrue(dry_run)   # reread không lưu con trỏ nên không được ghi kho hay xóa ảnh che khi nạp con trỏ
            return self.make(engine=None, prepare=prepare, dry_run=dry_run)
        with patch.dict(ocr.ENGINES, {"fake": Wrapped}), patch.object(agent_main, "MoneyImagesProcessor", processor), patch("builtins.print") as shown:
            code = agent_main.main(["reread", "--engine", "fake", "--since", "2020-01-01", "--live-sync", str(self.src), "--root", str(self.root)])
        self.assertEqual(code, 0)
        printed = " ".join(str(call.args[0]) for call in shown.call_args_list)
        self.assertEqual(json.loads(printed), {"wanted": 2, "read": 2, "had": 0, "failed": 0})


class AgentTest(MoneyBase):
    def setUp(self):
        super().setUp()
        (self.base / "remote").mkdir()
        self.remote = Remote(self.base / "remote")
        (self.src / "poller-identity.json").write_text(json.dumps({"status": "attached"}), encoding="utf-8")

    def agent(self, executor=None, **kwargs):
        money = {"engine": self.engine, "executor": executor or Inline(), "prepare": prepare, "max_age_days": None}
        agent = agent_main.Agent(self.live, self.root, "fake:" + BUNDLE_REMOTE, "fake:" + STATUS_REMOTE, run=self.remote, clock=lambda: self.now,
                                 fetch=FakeCdn(), transcode=no_jxl, max_age_days=None, money_images=True, money_args=money, **kwargs)
        self.addCleanup(agent.release)
        return agent

    def test_revisions_without_messages_of_selected_groups_do_not_make_money_images_lag(self):
        agent = self.agent()
        for _ in range(4):
            agent.cycle(force_status=True)
        self.feed.add_image(OTHER, b"\xff\xd8\xff\xe0other-1")   # hai tin của nhóm không chọn: `bundle` chỉ tiến con trỏ, không ghi gói
        self.feed.add_image(OTHER, b"\xff\xd8\xff\xe0other-2")
        for _ in range(2):
            status = agent.cycle(force_status=True)
        entry = status["processors"]["money_images"]
        self.assertEqual((entry["revision"], entry["lag_revisions"]), (self.feed.revision(), 0))   # review #601: không "đang đuổi kịp" mãi

    def test_off_by_default(self):
        agent = agent_main.Agent(self.live, self.root, "fake:" + BUNDLE_REMOTE, "fake:" + STATUS_REMOTE, run=self.remote, clock=lambda: self.now)
        self.addCleanup(agent.release)
        self.assertEqual([processor.name for processor in agent.processors], ["bundle"])

    def test_status_carries_money_images_counts_only(self):
        agent = self.agent()
        for _ in range(4):   # mỗi lượt thu một ảnh rồi nộp ảnh kế
            status = agent.cycle(force_status=True)
        entry = status["processors"]["money_images"]
        self.assertEqual(entry["counts"], {"read": 2, "pending": 0, "failed": 0, "review": 0, "asking": 0, **SKIPPED, "skipped_no_media": 3})
        self.assertEqual((entry["error"], entry["revision"]), (None, 87))
        remote = json.loads((self.remote.dirs[STATUS_REMOTE] / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(remote["processors"]["money_images"]["counts"]["read"], 2)
        self.assertNotIn("1.500.000", json.dumps(remote))   # không chữ OCR, không số tiền trong nhịp tim
        self.assertTrue(all(isinstance(value, int) for value in entry["counts"].values()))

    def test_slow_ocr_never_holds_back_the_bundle(self):
        stuck = Stuck()
        agent = self.agent(executor=stuck)
        status = agent.cycle(force_status=True)
        self.assertEqual(status["processors"]["bundle"]["revision"], 87)
        self.assertIsNone(status["processors"]["bundle"]["error"])
        self.assertTrue((self.remote.dirs[BUNDLE_REMOTE] / wb.REPORT).is_file())
        self.assertEqual(status["processors"]["money_images"]["counts"]["pending"], 2)
        self.assertEqual(stuck.jobs, 1)   # một ảnh đang đọc, ảnh kế chờ

    def test_money_images_errors_back_off_on_their_own_and_leave_the_bundle_alone(self):
        agent = self.agent()
        agent.processors[-1].engine = Missing()
        with patch.object(agent, "sleep", lambda seconds: None):
            agent.tick()
        self.assertEqual(agent.last["money_images"]["error"], "ocr_unavailable")
        self.assertIsNone(agent.last["bundle"]["error"])
        self.assertEqual(agent.retry_at["bundle"], 0.0)
        self.assertEqual(agent.retry_at["money_images"], self.now + agent_main.LOCAL_RETRY)

    def test_unexpected_crash_in_money_images_is_contained(self):
        agent = self.agent()
        with patch.object(agent.processors[-1], "step", side_effect=RuntimeError("hỏng")), patch.object(agent, "sleep", lambda seconds: None):
            status = agent.cycle(force_status=True)
        self.assertEqual(status["processors"]["money_images"]["error"], "unexpected")
        self.assertEqual(status["processors"]["bundle"]["revision"], 87)


class SourceTest(MoneyBase):
    def test_image_rows_filters_by_group_type_deleted_and_age(self):
        self.feed.add_image(OTHER, b"\xff\xd8\xff\xe0x")
        rows = self.live.image_rows({GROUP})
        self.assertEqual(sorted(item["message_id"] for item in rows), ["m2", "m3", "m4", "m5", "m8"])   # chỉ message_type 2, nhóm đã chọn
        self.assertEqual([item["message_id"] for item in self.live.image_rows({GROUP}, 1_700_000_004_500)], ["m5", "m8"])
        self.assertEqual(self.live.image_rows(set()), [])


if __name__ == "__main__":
    unittest.main()
