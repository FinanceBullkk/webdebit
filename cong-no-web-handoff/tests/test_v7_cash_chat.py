"""ZALO-THU-CHI-01 PR-2 (B1–B2): đọc mẫu thu/chi/ứng từ gói chat và đối chiếu chỉ đọc với sổ. Gói chat, sổ, xe, người đều bịa."""

import io
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_cash_chat as cash  # noqa: E402
import v7_ledger_api as api  # noqa: E402
import v7_role  # noqa: E402
import v7_zalo_chat as chat  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 11, 20, 10, 0, tzinfo=VN).timestamp()
GROUP, OTHER = "1" * 64, "2" * 64
LAN, MINH = "a" * 64, "b" * 64
PHOTO = "c" * 64
HAO = "e" * 64   # tài khoản Zalo của mình (self_user)
PAY = [f"{n:064x}" for n in range(1, 7)]   # ảnh chuyển khoản bịa


def at(day, hour=9, minute=0, second=0):
    return int(datetime.fromisoformat(f"2026-11-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}+07:00").timestamp() * 1000)


def row(mid, stamp, body, sender=LAN, cid=GROUP, media=None):
    return {"message_id": mid, "conversation_id": cid, "sender_id": sender, "timestamp": str(stamp), "message_type": 2 if media else 1,
            "body": body, "media": media or []}


def write_bundle(directory: Path, rows: list[dict]) -> None:
    (directory / "conversations.json").write_text(json.dumps([
        {"conversation_id": GROUP, "display_name": "Nhóm thu chi thử", "participant_ids": [LAN, MINH], "is_group": True},
        {"conversation_id": OTHER, "display_name": "Nhóm khác", "participant_ids": [LAN], "is_group": True}]), encoding="utf-8")
    (directory / "messages.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows), encoding="utf-8")
    (directory / "users.json").write_text(json.dumps({"users": {LAN: "Lan", MINH: "Minh", HAO: "Văn phòng"}, "self_user": HAO}), encoding="utf-8")
    (directory / "media.json").write_text(json.dumps({key: {"mime": "image/jpeg", "width": 800, "height": 1200} for key in (PHOTO, *PAY)}), encoding="utf-8")
    (directory / "export-report.json").write_text(json.dumps({"status": "BUNDLED", "built_at": "2026-11-20T09:55:00+07:00"}), encoding="utf-8")


def receipt(rid, customer, name, day, amount, source="web"):
    return {"source": source, "id": rid, "pid": f"PH-{rid}" if source == "web" else None, "customer_id": customer, "name": name,
            "date": f"2026-11-{day:02d}", "amount_vnd": str(amount)}


class FakeRunner:
    """Chỉ các hàm đọc mà trang Thu chi được phép gọi; hàm lạ thì nổ để test thấy ngay."""

    def __init__(self, receipts=(), marks=(), voided=(), ung=(), chang=(), fail=(), slow=0.0, links=(), reviews=None):
        self.receipts, self.marks, self.voided, self.ung, self.chang = list(receipts), list(marks), list(voided), list(ung), list(chang)
        self.links = list(links)
        self.reviews, self.recorded = dict(reviews or {}), []
        self.fail, self.slow = set(fail), slow
        self.calls = []

    def run(self, function, payload, actor, **_):
        self.calls.append((function, payload))
        if function in self.fail:
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        if function == "list_customers" and self.slow:
            time.sleep(self.slow)
        if function == "list_customers":
            return {"customers": [{"id": 1, "name": "KHACH A"}, {"id": 2, "name": "KHACH B"}, {"id": 3, "name": "KHACH C"}, {"id": 4, "name": "KHACH D"},
                                  {"id": 5, "name": "KHACH E"}, {"id": 6, "name": "AN"}, {"id": 7, "name": "AN LONG"}]}
        if function == "doixe_get_tong":
            return {"danh_muc": {"xe": [{"id": 10, "bien_so": "51C-123.45", "tai_xe_id": 20, "dang_dung": True},
                                        {"id": 11, "bien_so": "29H-678.90", "tai_xe_id": None, "dang_dung": True},
                                        {"id": 12, "bien_so": "43C-999.45", "tai_xe_id": None, "dang_dung": True}],
                                "nguoi": [{"id": 20, "ten": "Bình", "vai": "tai_xe", "dang_dung": True},
                                          {"id": 21, "ten": "Cường", "vai": "tai_xe", "dang_dung": True}]}}
        if function == "get_receipt_book":
            month = payload["month"][:7]
            mine = [item for item in self.receipts if item["date"].startswith(month)]
            return {"days": [{"date": item["date"], "rows": [item]} for item in mine], "voided": self.voided}
        if function == "doixe_get_so":
            return {"ung": self.ung if payload["loai"] == "nguoi" and payload["id"] == 20 else [],
                    "chang": self.chang if payload["id"] in (10, 20) else []}
        if function == "get_marks":
            return {"marks": self.marks if payload["conversation_id"] == GROUP else []}
        if function == "get_zalo_links":
            return {"links": self.links}
        if function == "get_cash_reviews":
            return {"reviews": {key: value for key, value in self.reviews.items() if key in payload["message_ids"]}}
        if function == "record_cash_review":   # PR-3: lệnh ghi duy nhất của trang Thu chi
            self.recorded.append(payload)
            return {"id": len(self.recorded), **payload, "state": {}}
        raise AssertionError(f"hàm không được đọc: {function}")


class CashChatCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name) / "bundle"
        self.dir.mkdir()
        self.status = Path(folder.name) / "status.json"
        self.reads = Path(folder.name) / "reads" / "money-reads.json"
        for patcher in (patch.object(chat, "EXPORT_DIR", str(self.dir)), patch.object(chat, "_STORE", None), patch.object(chat, "_STORE_DIR", None),
                        patch.dict(os.environ, {"WEBDEBIT_ZALO_AGENT_STATUS": str(self.status), "WEBDEBIT_ZALO_READS_DIR": str(Path(folder.name) / "reads")}),
                        patch.dict(cash._CACHE, clear=True), patch.dict(cash._READS, {"stamp": None, "value": {}, "ok": True})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def get(self, rows, runner=None, query="from=2026-11-01&to=2026-11-20"):
        write_bundle(self.dir, rows)
        chat._STORE, chat._STORE_DIR = None, None
        cash._CACHE.clear()
        return cash.handle_get(query, runner or FakeRunner(), "tester", NOW)

    def statuses(self, body):
        return {item["message_id"]: item["status"] for item in body["items"]}


class ReadPatternTests(unittest.TestCase):
    def test_amount_forms(self):
        for text, expected in {"thu 50tr A": 50_000_000, "chi 2tr5 dầu": 2_500_000, "chi 2,5tr": 2_500_000, "chi 2.5tr": 2_500_000, "thu 50 triệu": 50_000_000,
                               "chi 800k phí": 800_000, "thu 1.200.000 ck": 1_200_000, "thu 1200000": 1_200_000, "thu 1,200,000": 1_200_000,
                               "chi 1.200k": 1_200_000, "chi 2tr05": 2_050_000, "chi 1k5": 1_500, "thu 1 tỷ": 1_000_000_000, "THU 50TR": 50_000_000,
                               "ứng 3tr tài xế": 3_000_000, "Ung: 3 tr": 3_000_000, "thu 800000đ": 800_000, "thu 800.000d": 800_000}.items():
            with self.subTest(text):
                self.assertEqual(cash.read_report(text)["amount_vnd"], expected)

    def test_unreadable_amount_is_none_not_zero(self):
        for text in ("thu 50 khach a", "chi 500 dầu", "thu 12/11 50tr", "chi 2,5,5tr", "thu 0k", "chi 2.5555k", "thu 99999999999999999tr",
                     "chi 1 triệu 2 cho Hùng", "chi 2 tr 5", "thu 1tr 500", "thu 1.200 000", "chi 50tr 15.11",   # số rời sau đơn vị: không đoán
                     "chi -500k", "chi: -500k", "thu-50tr", "chi –500k", "chi −500k"):   # dấu trừ dính vào số: không thành khoản dương
            with self.subTest(text):
                self.assertIsNone(cash.read_report(text)["amount_vnd"])

    def test_dash_with_space_and_dates_after_the_amount_still_read(self):
        for text, expected in {"chi - 500k xăng": 500_000, "thu 50tr 20/11 khách a": 50_000_000, "thu 50tr 15-11": 50_000_000, "chi 800k 12345 xe": 800_000,
                               "thu 5tr 30 cont": 5_000_000, "thu 2tr 51C-123.45": 2_000_000, "chi 2tr 4 xe": 2_000_000, "chi 800k 2 bao": 800_000,
                               "chi 1k5 3 xe": 1_500, "thu 5tr 30 cont khách a": 5_000_000, "thu 5tr 30": None, "thu 5tr 30 cho khach": None}.items():
            with self.subTest(text):
                self.assertEqual(cash.read_report(text)["amount_vnd"], expected)

    def test_not_a_report(self):
        for text in ("chi tiết thế nào", "thu xếp giúp em", "hôm nay thu 50tr", "chiều nay 5tr", "", "thu", "ứng dụng 5tr"):
            with self.subTest(text):
                self.assertIsNone(cash.read_report(text))

    def test_direction_ignores_case_and_accents(self):
        self.assertEqual([cash.read_report(text)["direction"] for text in ("Thu 1tr", "CHI 1tr", "Ứng 1tr", "ung 1tr", "ỨNG 1tr")], ["thu", "chi", "ung", "ung", "ung"])

    def test_rest_keeps_plate_after_amount(self):
        self.assertEqual(cash.read_report("chi 800k 12345 xe")["amount_vnd"], 800_000)
        self.assertIn("12345", cash.read_report("chi 800k 12345 xe")["rest"])


class TargetTests(unittest.TestCase):
    directory = cash.Directory(
        [{"id": 1, "name": "KHACH A", "display_name": "Anh Ba", "aliases": ["chị Hai"]}, {"id": 2, "name": "KHACH B"}, {"id": 6, "name": "AN"},
         {"id": 7, "name": "AN LONG"}, {"id": 8, "name": "CÔNG TY 陈氏"}, {"id": 9, "name": "KHACH A MỚI"}],
        [{"id": 10, "bien_so": "51C-123.45"}, {"id": 12, "bien_so": "43C-999.45"}, {"id": 11, "bien_so": "29H-678.90"}],
        [{"id": 20, "ten": "Bình", "dang_dung": True}, {"id": 21, "ten": "Bình An", "dang_dung": True}, {"id": 22, "ten": "Cường", "dang_dung": False},
         {"id": 23, "ten": "Vi", "dang_dung": True}])

    def target(self, text):
        report = cash.read_report(text)
        return self.directory.target(report["direction"], report["rest"])

    def test_book_by_unaccented_name_display_name_and_alias(self):
        self.assertEqual(self.target("thu 5tr khách b")["id"], 2)
        self.assertEqual(self.target("thu 5tr anh ba ck")["id"], 1)
        self.assertEqual(self.target("thu 5tr Chị Hai")["id"], 1)
        self.assertEqual(self.target("thu 5tr 陈氏")["kind"], None)   # chỉ có tên đầy đủ "CÔNG TY 陈氏" mới khớp
        self.assertEqual(self.target("thu 5tr công ty 陈氏")["id"], 8)

    def test_two_books_is_unknown_but_longest_name_wins(self):
        self.assertEqual(self.target("thu 5tr khach a")["id"], 1)   # "KHACH A" nằm trong "KHACH A MỚI" nhưng text không có "mới"
        found = self.target("thu 5tr an long")   # "AN" nằm trong "AN LONG": giữ tên dài
        self.assertEqual((found["kind"], found["id"]), ("so", 7))
        both = self.target("thu 5tr khach a hoac khach b")
        self.assertEqual((both["kind"], both["ambiguous"]), (None, True))

    def test_vehicle_by_last_four_or_five_digits(self):
        for text in ("chi 2tr5 dầu xe 12345", "chi 2tr5 dầu xe 2345", "chi 2tr5 dầu xe 123.45", "chi 2tr5 dầu xe 51C-123.45", "chi 2tr5 dầu 51c-12345",
                     "chi 2tr5 dầu 51C12345", "chi 2tr5 dầu bks 12345", "chi 2tr5 dầu biển số 123.45"):
            with self.subTest(text):
                self.assertEqual((self.target(text)["kind"], self.target(text)["id"]), ("xe", 10))

    def test_vehicle_ambiguous_or_unknown_gets_no_target(self):
        self.assertIsNone(self.target("chi 2tr5 dầu xe 3945")["kind"])   # không xe nào
        self.assertIsNone(self.target("chi 2tr5 dầu xe 99945 xe 12345")["kind"])   # hai xe
        self.assertIsNone(self.target("chi 2tr5 dầu xe 123")["kind"])   # dưới 4 số

    def test_dates_years_and_bare_numbers_are_not_plates(self):
        for text in ("chi 2tr5 dầu 12345", "chi 2tr5 dầu 20/11 2345", "chi 2tr5 15.11", "chi 2tr5 dầu năm 2026", "chi 2tr5 dầu 20.11.2026", "chi 2tr5 dầu 2345 lít",
                     "chi 2tr5 dầu 20tr 2345"):
            with self.subTest(text):
                self.assertIsNone(self.target(text)["kind"])

    def test_names_of_two_letters_do_not_match_by_themselves(self):
        self.assertIsNone(self.target("ứng 3tr vi")["kind"])   # tên "Vi" quá ngắn, trùng từ thường
        self.assertIsNone(self.target("thu 5tr an")["kind"])   # sổ "AN" quá ngắn
        self.assertEqual(self.target("thu 5tr an long")["id"], 7)

    def test_driver_by_name_only_when_exactly_one(self):
        self.assertEqual((self.target("ứng 3tr tài xế bình an")["kind"], self.target("ứng 3tr tài xế bình an")["id"]), ("tai_xe", 21))
        self.assertEqual(self.target("ứng 3tr cuong")["kind"], None)   # người đã ngừng dùng
        self.assertEqual(self.target("ứng 3tr bình")["id"], 20)


class BuildTests(CashChatCase):
    def test_every_status(self):
        rows = [
            row("recorded", at(19), "thu 50tr khách a ck"),
            row("missing", at(10), "thu 40tr khách a"),
            row("waiting", at(20, 8), "thu 30tr khách b"),
            row("diff", at(18), "thu 20tr khách c"),
            row("suggest", at(17), "thu 7tr"),
            row("unknown", at(17, 10), "thu 9tr"),
            row("chi_ok", at(18), "chi 2tr5 dầu xe 12345"),
            row("ung_ok", at(18), "ứng 3tr tài xế bình"),
            row("office", at(18), "chi 5tr lương tháng 11"),
            row("noamount", at(18), "thu 50 khach a"),
            row("chi_none", at(11), "chi 500k xe 12345"),
            row("not_report", at(18), "chi tiết giúp em"),
        ]
        runner = FakeRunner(
            receipts=[receipt(1, 1, "KHACH A", 19, 50_000_000), receipt(2, 3, "KHACH C", 18, 18_000_000), receipt(3, 4, "KHACH D", 17, 7_000_000)],
            ung=[{"id": 5, "ngay": "2026-11-18", "so_tien_vnd": "3000000", "huy": None}, {"id": 6, "ngay": "2026-11-18", "so_tien_vnd": "3000000", "huy": {"ly_do": "x"}}],
            chang=[{"id": 70, "ngay": "2026-11-18", "da_bo": False, "nguoi_tra_id": 20, "dong": [{"id": 80, "phi": {"dau": "2500000"}}]}])
        body = self.get(rows, runner)
        self.assertEqual(self.statuses(body), {
            "recorded": "RECORDED", "missing": "MISSING", "waiting": "WAITING", "diff": "AMOUNT_DIFF", "suggest": "SUGGEST", "unknown": "UNKNOWN_TARGET",
            "chi_ok": "RECORDED", "ung_ok": "RECORDED", "office": "NO_LEDGER", "noamount": "NO_AMOUNT", "chi_none": "MISSING"})
        by_id = {item["message_id"]: item for item in body["items"]}
        self.assertEqual(by_id["diff"]["ledger_vnd"], 18_000_000)
        self.assertEqual(by_id["suggest"]["ledger_ref"]["customer_id"], 4)
        self.assertEqual(by_id["recorded"]["ledger_ref"]["pid"], "PH-1")
        self.assertEqual(by_id["chi_ok"]["ledger_ref"], {"kind": "dong_phi", "id": 80, "loai_phi": "dau", "chang_id": 70, "date": "2026-11-18"})
        self.assertEqual(by_id["ung_ok"]["ledger_ref"]["id"], 5)   # ứng đã hủy không tính
        self.assertEqual(sorted(body["counts"]), sorted(cash.STATUSES))
        self.assertEqual(body["counts"]["RECORDED"], 3)

    def test_totals_skip_missing_amount_and_count_it_apart(self):
        body = self.get([row("a", at(19), "thu 50tr khách a"), row("b", at(19), "chi 2tr5 dầu xe 12345"), row("c", at(19), "ứng 3tr bình"),
                         row("d", at(19), "thu 12 khach")])
        self.assertEqual({key: body["totals"][key] for key in ("thu_vnd", "chi_vnd", "ung_vnd", "no_amount", "thu_count")},
                         {"thu_vnd": 50_000_000, "chi_vnd": 2_500_000, "ung_vnd": 3_000_000, "no_amount": 1, "thu_count": 1})
        self.assertIsNone(next(item for item in body["items"] if item["message_id"] == "d")["amount_vnd"])

    def test_missing_and_waiting_follow_the_three_day_rule(self):
        body = self.get([row("day3", at(17, 23), "thu 5tr khách a"), row("day4", at(16, 23), "thu 5tr khách a")])
        self.assertEqual(self.statuses(body), {"day3": "WAITING", "day4": "MISSING"})   # hôm nay 20/11: quá báo+3 mới là chưa vào sổ

    def test_receipt_window_is_three_days_before_seven_after(self):
        rows = [row("m", at(10), "thu 5tr khách a")]
        for day, expected in ((7, "RECORDED"), (17, "RECORDED"), (6, "MISSING"), (18, "MISSING")):
            with self.subTest(day=day):
                body = self.get(rows, FakeRunner(receipts=[receipt(1, 1, "KHACH A", day, 5_000_000)]))
                self.assertEqual(body["items"][0]["status"], expected)

    def test_voided_receipt_is_not_counted(self):
        voided = [{"pid": "PH-9", "customer_id": 1, "name": "KHACH A", "date": "2026-11-19", "amount_vnd": "5000000", "voided_on": "2026-11-20"}]
        body = self.get([row("m", at(19), "thu 5tr khách a")], FakeRunner(voided=voided))
        self.assertEqual(body["items"][0]["status"], "WAITING")

    def test_one_receipt_matches_one_report(self):
        runner = FakeRunner(receipts=[receipt(1, 5, "KHACH E", 19, 4_000_000)])
        body = self.get([row("first", at(19, 9), "thu 4tr khách e"), row("second", at(19, 10), "thu 4tr khách e")], runner)
        for item in body["items"]:
            self.assertEqual((item["status"], item["shared"], item["ledger_vnd"]), ("AMOUNT_DIFF", True, 4_000_000))
        two = self.get([row("first", at(19, 9), "thu 4tr khách e"), row("second", at(19, 10), "thu 4tr khách e")],
                       FakeRunner(receipts=[receipt(1, 5, "KHACH E", 19, 4_000_000), receipt(2, 5, "KHACH E", 19, 4_000_000)]))
        self.assertEqual(sorted((item["status"], item["ledger_ref"]["id"]) for item in two["items"]), [("RECORDED", 1), ("RECORDED", 2)])

    def test_unclear_receipt_suggested_to_two_reports_is_shared(self):
        body = self.get([row("a", at(19, 9), "thu 7tr"), row("b", at(19, 10), "thu 7tr")], FakeRunner(receipts=[receipt(3, 4, "KHACH D", 19, 7_000_000)]))
        self.assertEqual([(item["status"], item["shared"]) for item in body["items"]], [("SUGGEST", True), ("SUGGEST", True)])

    def test_two_receipts_of_the_same_amount_in_other_books_are_not_suggested(self):
        body = self.get([row("a", at(19), "thu 7tr")], FakeRunner(receipts=[receipt(3, 4, "KHACH D", 19, 7_000_000), receipt(4, 2, "KHACH B", 18, 7_000_000)]))
        self.assertEqual(body["items"][0]["status"], "UNKNOWN_TARGET")

    def test_sheet_receipt_counts_like_web_receipt(self):
        body = self.get([row("m", at(19), "thu 5tr khách a")], FakeRunner(receipts=[receipt(8, 1, "KHACH A", 19, 5_000_000, source="sheet")]))
        self.assertEqual((body["items"][0]["status"], body["items"][0]["ledger_ref"]["source"]), ("RECORDED", "sheet"))

    def test_photos_from_same_sender_within_two_minutes_are_proof(self):
        rows = [row("m", at(19, 9, 0), "thu 5tr khách a"), row("p1", at(19, 9, 1, 59), None, media=[PHOTO]), row("p2", at(19, 9, 2, 1), None, media=[PHOTO]),
                row("p3", at(19, 9, 0, 30), None, sender=MINH, media=[PHOTO]), row("p0", at(19, 8, 59), None, media=[PHOTO])]
        item = self.get(rows)["items"][0]
        self.assertEqual([media["id"] for media in item["media"]], [PHOTO])   # chỉ p1
        self.assertEqual((item["sender_name"], item["conversation_name"], item["conversation_id"]), ("Lan", "Nhóm thu chi thử", GROUP))

    def test_photo_after_midnight_still_attaches(self):
        rows = [row("m", at(19, 23, 59, 30), "thu 5tr khách a"), row("p", at(20, 0, 1), None, media=[PHOTO])]
        self.assertEqual(len(self.get(rows, query="from=2026-11-19&to=2026-11-19")["items"][0]["media"]), 1)

    def test_range_and_status_filter(self):
        rows = [row("old", at(1), "thu 5tr khách a"), row("new", at(19), "thu 5tr khách a")]
        self.assertEqual([item["message_id"] for item in self.get(rows, query="from=2026-11-15&to=2026-11-20")["items"]], ["new"])
        body = self.get(rows, query="status=WAITING")   # mặc định 7 ngày tới hôm nay
        self.assertEqual([item["message_id"] for item in body["items"]], ["new"])
        filtered = self.get(rows, query="from=2026-11-01&to=2026-11-20&status=MISSING")
        self.assertEqual(([item["message_id"] for item in filtered["items"]], filtered["counts"]["WAITING"], filtered["counts"]["MISSING"]), (["old"], 1, 1))   # số đếm không theo bộ lọc

    def test_items_are_newest_first_and_carry_vn_day(self):
        body = self.get([row("a", at(18), "thu 5tr khách a"), row("b", at(19, 23, 30), "thu 5tr khách a"), row("c", at(19, 1, 0), "thu 5tr khách a")])
        self.assertEqual([(item["message_id"], item["day"]) for item in body["items"]], [("b", "2026-11-19"), ("c", "2026-11-19"), ("a", "2026-11-18")])

    def test_deleted_and_non_text_messages_are_not_reports(self):
        rows = [dict(row("gone", at(19), None), deleted=True), row("card", at(19), {"title": "thu 5tr khách a"}), row("ok", at(19), "thu 5tr khách a")]
        self.assertEqual([item["message_id"] for item in self.get(rows)["items"]], ["ok"])

    def test_no_report_means_no_ledger_lookups_except_marks(self):
        runner = FakeRunner()
        body = self.get([row("a", at(19), "chào anh")], runner)
        self.assertEqual(body["items"], [])
        self.assertNotIn("get_receipt_book", [name for name, _ in runner.calls])
        self.assertNotIn("doixe_get_so", [name for name, _ in runner.calls])

    def test_reports_without_a_match_do_not_hit_months_in_the_future(self):
        runner = FakeRunner()
        self.get([row("a", at(20), "thu 5tr khách a")], runner)
        months = {payload["month"] for name, payload in runner.calls if name == "get_receipt_book"}
        self.assertEqual(months, {"2026-11-01"})   # 20/11 + 7 ngày chạm tháng 12 nhưng tháng đó chưa tới

    def test_contact_marks_show_as_receipts_without_duplicating_the_message(self):
        marks = [
            {"id": 1, "kind": "paid_claim", "status": "received", "customer_id": 1, "amount_vnd": "9000000", "on_date": "2026-11-18", "conversation_id": GROUP,
             "message_id": "markmsg", "message_at": "2026-11-18T10:00:00+07:00", "message_sender": "Lan", "message_excerpt": "đã chuyển", "receipt_pid": "PH-7", "note": None},
            {"id": 2, "kind": "paid_claim", "status": "not_seen", "customer_id": 2, "amount_vnd": "1000000", "on_date": "2026-11-12", "conversation_id": GROUP,
             "message_id": None, "message_at": None, "message_sender": None, "message_excerpt": None, "receipt_pid": None, "note": "khách báo"},
            {"id": 3, "kind": "paid_claim", "status": "cancelled", "customer_id": 1, "amount_vnd": "8000000", "on_date": "2026-11-18", "conversation_id": GROUP},
            {"id": 4, "kind": "promise", "status": "pending", "customer_id": 1, "amount_vnd": "8000000", "on_date": "2026-11-25", "conversation_id": GROUP},
            {"id": 5, "kind": "paid_claim", "status": "received", "customer_id": 1, "amount_vnd": "6000000", "on_date": "2026-11-18", "conversation_id": GROUP,
             "message_id": "samemsg", "message_at": "2026-11-18T09:00:00+07:00", "receipt_pid": None}]
        body = self.get([row("samemsg", at(18), "thu 6tr khách a")], FakeRunner(marks=marks))
        found = {item["message_id"] or f"mark{index}": item for index, item in enumerate(body["items"])}
        self.assertEqual(len(body["items"]), 3)   # tin thường, dấu 1, dấu 2; dấu đã hủy, lời hứa và dấu cùng tin bị bỏ
        mark = next(item for item in body["items"] if item["message_id"] == "markmsg")
        self.assertEqual((mark["source"], mark["status"], mark["ledger_ref"]["pid"], mark["target"]["label"]), ("mark", "RECORDED", "PH-7", "KHACH A"))
        self.assertEqual(next(item for item in body["items"] if item["amount_vnd"] == 1_000_000)["status"], "MISSING")
        self.assertEqual(next(item for item in found.values() if item["message_id"] == "samemsg")["source"], "chat")

    def test_matching_is_maximum_not_greedy_in_both_orders(self):
        """Khoản muộn chỉ có một dòng ứng viên, khoản sớm có hai: khoản sớm không được lấy mất dòng chung rồi để khoản muộn trỏ vào dòng đã ghép."""
        early, late = row("early", at(5), "thu 5tr khách a"), row("late", at(12), "thu 5tr khách a")   # cửa sổ sớm 2–12/11, muộn 9–19/11
        body = self.get([early, late], FakeRunner(receipts=[receipt(1, 1, "KHACH A", 10, 5_000_000), receipt(2, 1, "KHACH A", 3, 5_000_000)]))
        self.assertEqual({item["message_id"]: (item["status"], item["ledger_ref"]["id"], item["shared"]) for item in body["items"]},
                         {"early": ("RECORDED", 2, False), "late": ("RECORDED", 1, False)})
        body = self.get([early, late], FakeRunner(receipts=[receipt(1, 1, "KHACH A", 10, 5_000_000), receipt(2, 1, "KHACH A", 18, 5_000_000)]))
        self.assertEqual({item["message_id"]: (item["status"], item["ledger_ref"]["id"], item["shared"]) for item in body["items"]},
                         {"early": ("RECORDED", 1, False), "late": ("RECORDED", 2, False)})

    def test_no_complete_matching_puts_the_whole_group_to_the_person(self):
        rows = [row(f"r{index}", at(10, 9 + index), "thu 5tr khách a") for index in range(3)]
        body = self.get(rows, FakeRunner(receipts=[receipt(1, 1, "KHACH A", 10, 5_000_000), receipt(2, 1, "KHACH A", 11, 5_000_000)]))
        self.assertEqual([(item["status"], item["shared"]) for item in body["items"]], [("AMOUNT_DIFF", True)] * 3)

    def test_a_failing_source_never_breaks_the_page_or_claims_missing(self):
        old = [row("old", at(10), "thu 5tr khách a"), row("fee", at(10), "chi 1tr xe 12345"), row("unk", at(10), "thu 9tr"), row("ok", at(10), "thu 50 khach a")]
        body = self.get(old, FakeRunner(fail={"get_receipt_book"}))
        self.assertEqual(self.statuses(body), {"old": "WAITING", "fee": "MISSING", "unk": "UNKNOWN_TARGET", "ok": "NO_AMOUNT"})
        self.assertEqual(body["sources_failed"], ["receipt"])
        # "unk" (thu chưa rõ sổ) cũng chưa kiểm được: không đọc được phiếu thì không biết có SUGGEST hay không.
        self.assertEqual({item["message_id"] for item in body["items"] if item["unchecked"]}, {"old", "unk"})
        body = self.get(old, FakeRunner(fail={"doixe_get_so"}))
        self.assertEqual(self.statuses(body), {"old": "MISSING", "fee": "WAITING", "unk": "UNKNOWN_TARGET", "ok": "NO_AMOUNT"})
        self.assertEqual((body["sources_failed"], {item["message_id"] for item in body["items"] if item["unchecked"]}), (["fleet"], {"fee"}))
        body = self.get(old, FakeRunner(fail={"list_customers"}))
        self.assertEqual(body["sources_failed"], ["directory"])
        self.assertTrue(all(item["unchecked"] for item in body["items"] if item["status"] == "UNKNOWN_TARGET"))
        self.assertEqual(self.get(old, FakeRunner(fail={"get_marks"}))["sources_failed"], ["marks"])
        self.assertEqual(self.get(old)["sources_failed"], [])

    def test_null_and_malformed_source_rows_are_skipped_not_counted_as_zero(self):
        runner = FakeRunner(receipts=[dict(receipt(1, 1, "KHACH A", 19, 5_000_000), amount_vnd=None), dict(receipt(2, 1, "KHACH A", 19, 5_000_000), date="bậy"),
                                      dict(receipt(3, 1, "KHACH A", 19, 5_000_000), customer_id=None), receipt(4, 1, "KHACH A", 19, 5_000_000)],
                            ung=[{"id": 1, "ngay": None, "so_tien_vnd": "3000000", "huy": None}, {"id": 2, "ngay": "2026-11-19", "so_tien_vnd": None, "huy": None},
                                 {"id": 3, "ngay": "2026-11-19", "so_tien_vnd": "3000000", "huy": None}],
                            chang=[{"id": 9, "ngay": None, "dong": [{"id": 1, "phi": {"dau": "1000000"}}]},
                                   {"id": 10, "ngay": "2026-11-19", "nguoi_tra_id": 20,
                                    "dong": [{"id": 2, "phi": {"dau": None, "nang": "abc", "cau": "2500000"}}, {"id": None, "phi": {"dau": "2500000"}}, "bậy"]}])
        body = self.get([row("t", at(19), "thu 5tr khách a"), row("u", at(19), "ứng 3tr bình"), row("c", at(19), "chi 2tr5 xe 12345")], runner)
        by = {item["message_id"]: item for item in body["items"]}
        self.assertEqual((by["t"]["ledger_ref"]["id"], by["u"]["ledger_ref"]["id"], by["c"]["ledger_ref"]["loai_phi"]), (4, 3, "cau"))
        self.assertEqual(body["sources_failed"], [])

        class Broken(FakeRunner):
            def run(self, function, payload, actor, **_):
                return ["không phải dict"]
        broken = self.get([row("t", at(19), "thu 5tr khách a")], Broken())
        self.assertEqual((broken["items"][0]["status"], broken["items"][0]["unchecked"]), ("UNKNOWN_TARGET", True))

    def test_mark_and_chat_report_of_the_same_receipt_count_once(self):
        mark = {"id": 1, "kind": "paid_claim", "status": "received", "customer_id": 1, "amount_vnd": "50000000", "on_date": "2026-11-19", "conversation_id": GROUP,
                "message_id": "other-msg", "message_at": "2026-11-19T10:00:00+07:00", "message_sender": "Lan", "message_excerpt": "đã chuyển", "receipt_pid": "PH-1"}
        runner = FakeRunner(receipts=[receipt(1, 1, "KHACH A", 19, 50_000_000)],
                            marks=[mark, {**mark, "id": 2, "message_id": "third", "receipt_pid": "PH-1"},
                                   {**mark, "id": 3, "message_id": "free", "receipt_pid": "PH-77", "amount_vnd": "1000000"},
                                   {**mark, "id": 4, "message_id": "free2", "receipt_pid": "PH-77", "amount_vnd": "1000000"}])
        body = self.get([row("chat", at(19), "thu 50tr khách a")], runner)
        self.assertEqual(sorted((item["source"], item["amount_vnd"]) for item in body["items"]), [("chat", 50_000_000), ("mark", 1_000_000)])
        # Ba dấu bị ẩn: hai dấu cùng phiếu PH-1 với khoản chat, một dấu thứ hai của phiếu PH-77. Phiếu chỉ cộng một lần.
        self.assertEqual((body["totals"]["thu_vnd"], body["totals"]["thu_count"], body["marks_hidden"]), (51_000_000, 2, 3))

    def test_concurrent_requests_build_once(self):
        write_bundle(self.dir, [row("a", at(19), "thu 5tr khách a")])
        chat._STORE, chat._STORE_DIR = None, None
        cash._CACHE.clear()
        runner = FakeRunner(slow=0.3)
        results = []
        workers = [threading.Thread(target=lambda: results.append(cash.handle_get("", runner, "tester", NOW))) for _ in range(6)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(len(results), 6)
        self.assertEqual(sum(name == "list_customers" for name, _ in runner.calls), 1)
        self.assertEqual(len({json.dumps(result["items"]) for result in results}), 1)

    def test_one_conversation_limit_applies_to_reports_and_marks_alike(self):
        rows = [row("new", at(19), "thu 5tr khách a"), row("old", at(18), "thu 5tr khách a", cid=OTHER)]
        runner = FakeRunner()
        with patch.object(cash, "MAX_CONVERSATIONS", 1):
            body = self.get(rows, runner)
        self.assertEqual(([item["message_id"] for item in body["items"]], body["conversations_skipped"]), (["new"], 1))
        self.assertEqual([payload["conversation_id"] for name, payload in runner.calls if name == "get_marks"], [GROUP])
        self.assertEqual(self.get(rows)["conversations_skipped"], 0)

    def test_chosen_behaviours(self):
        """Hành vi chủ ý (đổi thì phải đổi test): chi khớp từng dòng phí chứ không khớp tổng; ứng cho xe không có tài xế là chưa rõ;
        "chi lương tài xế …" có người nên ghép sổ Đội xe; cửa sổ ngày của khoản chat tính từ ngày tin."""
        two_lines = [{"id": 70, "ngay": "2026-11-18", "da_bo": False, "nguoi_tra_id": 20, "dong": [{"id": 80, "phi": {"dau": "1000000", "nang": "1500000"}}]}]
        body = self.get([row("sum", at(18), "chi 2tr5 dầu xe 12345"), row("line", at(18), "chi 1tr5 nâng xe 12345"), row("nodriver", at(18), "ứng 3tr xe 67890"),
                         row("wage", at(18), "chi 3tr lương tài xế bình"), row("office", at(18), "chi 3tr lương tháng 11")], FakeRunner(chang=two_lines))
        # 2tr5 không khớp dòng phí nào (1tr + 1tr5 là hai dòng): không ghép theo tổng. Sau khi "line" lấy dòng 1tr5, dòng 1tr còn lại là dòng duy nhất
        # nên hai khoản chi 2tr5 và 3tr đều hiện "lệch" so với nó và cùng `shared` (người xem chọn).
        self.assertEqual(self.statuses(body), {"sum": "AMOUNT_DIFF", "line": "RECORDED", "nodriver": "UNKNOWN_TARGET", "wage": "AMOUNT_DIFF", "office": "NO_LEDGER"})
        self.assertEqual([(item["ledger_vnd"], item["shared"]) for item in body["items"] if item["message_id"] in ("sum", "wage")], [(1_000_000, True)] * 2)
        self.assertEqual(next(item for item in body["items"] if item["message_id"] == "wage")["target"]["kind"], "tai_xe")

    def test_group_waiting_for_a_person_keeps_its_rows_away_from_other_reports(self):
        """Hai khoản 5tr tranh một phiếu 5tr (shared): phiếu đó không được gán thêm cho khoản thứ ba (4tr) làm "lệch" như thể của riêng nó."""
        runner = FakeRunner(receipts=[receipt(1, 1, "KHACH A", 10, 5_000_000)])
        body = self.get([row("a", at(10, 9), "thu 5tr khách a"), row("b", at(10, 10), "thu 5tr khách a"), row("c", at(10, 11), "thu 4tr khách a")], runner)
        by = {item["message_id"]: item for item in body["items"]}
        self.assertEqual([(by[key]["status"], by[key]["shared"]) for key in "ab"], [("AMOUNT_DIFF", True)] * 2)
        self.assertEqual((by["c"]["status"], by["c"]["ledger_ref"], by["c"]["shared"]), ("MISSING", None, False))

    def test_unclear_receipt_with_failing_source_is_unchecked_not_just_unknown(self):
        body = self.get([row("unk", at(19), "thu 9tr")], FakeRunner(fail={"get_receipt_book"}))
        self.assertEqual((body["items"][0]["status"], body["items"][0]["unchecked"]), ("UNKNOWN_TARGET", True))
        body = self.get([row("unk", at(19), "thu 9tr")])
        self.assertEqual((body["items"][0]["status"], body["items"][0]["unchecked"]), ("UNKNOWN_TARGET", False))

    def test_odd_data_never_makes_the_route_fail(self):
        class Odd(FakeRunner):
            def run(self, function, payload, actor, **kw):
                if function == "list_customers":
                    self.calls.append((function, payload))
                    return {"customers": [{"id": 1, "name": "KHACH A", "aliases": 5}, {"id": 2, "name": "KHACH B", "aliases": "khach b hai"},
                                          {"id": 3, "name": "KHACH C", "aliases": [None, 7, "khach c ba"], "display_name": ["lạ"]}, {"name": None}, "bậy", None]}
                return super().run(function, payload, actor, **kw)
        body = self.get([row("a", at(19), "thu 5tr khách a"), row("c", at(19), "thu 5tr khach c ba")], Odd())
        self.assertEqual({item["message_id"]: item["target"]["id"] for item in body["items"]}, {"a": 1, "c": 3})
        marks = [{"id": 1, "kind": "paid_claim", "status": "received", "customer_id": 1, "amount_vnd": "1000000", "on_date": "2026-11-19", "conversation_id": GROUP,
                  "message_id": "m1", "message_at": "0001-01-01T00:00:00+07:00"},
                 {"id": 2, "kind": "paid_claim", "status": "received", "customer_id": 1, "amount_vnd": "1000000", "on_date": "2026-11-18", "conversation_id": GROUP,
                  "message_id": "m2", "message_at": "9999-12-31T23:59:59-12:00"}]
        body = self.get([row("a", at(19), "thu 5tr khách a")], FakeRunner(marks=marks))
        self.assertEqual(len(body["items"]), 3)
        self.assertIsNone(next(item for item in body["items"] if item["message_id"] == "m1")["sent_at"])
        with patch.object(cash.v7_api_sheet, "with_display_names", side_effect=KeyError("id")):
            body = self.get([row("a", at(19), "thu 5tr khách a")])
        self.assertEqual((body["sources_failed"], body["items"][0]["status"], body["items"][0]["unchecked"]), (["directory"], "UNKNOWN_TARGET", True))
        with patch.object(cash, "_core", side_effect=OverflowError("tràn")), patch.object(sys, "stderr", io.StringIO()) as log:
            body = self.get([row("a", at(19), "thu 5tr khách a")])
        self.assertEqual((body["unavailable"], body["reason"]), (True, "UNREADABLE"))
        self.assertNotIn("khách", log.getvalue())   # chỉ ghi tên lỗi, không ghi chữ của tin
        self.assertFalse(self.get([row("a", at(19), "thu 5tr khách a")])["unavailable"])   # lỗi không bị giữ lại trong bộ nhớ đệm

    def test_waiter_gives_up_on_a_stuck_leader_and_builds_itself(self):
        from concurrent.futures import Future
        key = ("stuck",)
        cash._FLIGHTS[key] = Future()
        self.addCleanup(cash._FLIGHTS.pop, key, None)
        with patch.object(cash, "FLIGHT_WAIT", 0.05):
            self.assertEqual(cash._single_flight(key, 0.0, lambda: {"built": True}), {"built": True})

    def test_unavailable_when_no_bundle(self):
        with patch.object(chat, "EXPORT_DIR", str(self.dir / "khong-co")):
            self.assertEqual(cash.handle_get("", FakeRunner(), "tester", NOW)["unavailable"], True)
        with patch.object(chat, "EXPORT_DIR", None):
            self.assertTrue(cash.handle_get("", FakeRunner(), "tester", NOW)["unavailable"])

    def test_zalo_state_comes_from_status_json(self):
        body = self.get([row("a", at(19), "thu 5tr khách a")])
        self.assertEqual((body["zalo"]["state"], body["bundle_at"]), ("missing", "2026-11-20T09:55:00+07:00"))
        self.status.write_text(json.dumps({"schema": 1, "at": "2026-11-20T09:59:00+07:00", "live_sync": {"identity": "attached"}, "processors": {}, "push": {}}), encoding="utf-8")
        self.assertEqual({key: self.get([row("a", at(19), "thu 5tr khách a")])["zalo"][key] for key in ("state", "identity")}, {"state": "ok", "identity": "attached"})
        self.status.write_text(json.dumps({"schema": 1, "at": "2026-11-20T09:00:00+07:00", "live_sync": {"identity": "waiting_for_zalo"}, "processors": {}, "push": {}}), encoding="utf-8")
        old = self.get([row("a", at(19), "thu 5tr khách a")])["zalo"]
        self.assertEqual((old["state"], old["silent_minutes"]), ("silent", 60))
        self.assertEqual(self.get([])["last_message_at"], None)

    def test_database_reads_are_cached_for_a_few_seconds(self):
        write_bundle(self.dir, [row("a", at(19), "thu 5tr khách a")])
        chat._STORE, chat._STORE_DIR = None, None
        cash._CACHE.clear()
        runner = FakeRunner()
        cash.handle_get("", runner, "tester", NOW)
        first = len(runner.calls)
        cash.handle_get("", runner, "tester", NOW + 3)
        self.assertEqual(len(runner.calls), first)
        cash.handle_get("", runner, "tester", NOW + 30)
        self.assertGreater(len(runner.calls), first)

    def test_only_read_functions_and_no_text_leaves_the_module(self):
        # PR-3: lệnh ghi duy nhất là record_cash_review (xác nhận/sửa/loại, ngoài đường tiền); không lệnh ghi nào khác.
        source = (ROOT / "web" / "v7_cash_chat.py").read_text(encoding="utf-8").replace("record_cash_review", "")
        self.assertNotIn("record_", source)
        self.assertNotIn("ghi_", source)
        self.assertNotRegex(source, r"v7_ai_explain|anthropic|gemini|openai")


LINK = {"conversation_id": GROUP, "customer_id": 1, "customer_name": "KHACH A"}   # nhóm GROUP gắn sổ KHACH A (ZALO-GROUP-01)


def read_entry(amount, by="ocr", bank="VCB", txn=None, reads=None):
    """Một mục của money-reads.json (ZALO-AGENT-01 Phần 3), số bịa."""
    return {"by": by, "amount_vnd": amount, "txn_time": txn, "bank": bank,
            "reads": reads if reads is not None else [{"engine": "easyocr", "version": "1.7.2+a2", "amount_vnd": amount, "confidence": 0.9}]}


class ImageReadTests(CashChatCase):
    """B4 trên hao (PR-4b): số đọc từ ảnh chuyển khoản trong trang Thu chi."""
    def write_reads(self, reads, schema=1):
        self.reads.parent.mkdir(exist_ok=True)
        self.reads.write_text(json.dumps({"schema": schema, "redact": "w1", "reads": reads}), encoding="utf-8")

    def test_image_without_report_is_a_receipt_of_the_linked_book(self):
        self.write_reads({PAY[0]: read_entry(7_000_000, txn="2026-11-19T15:02:00+07:00")})
        runner = FakeRunner(receipts=[receipt(1, 1, "KHACH A", 19, 7_000_000)], links=[LINK])
        body = self.get([row("img", at(19, 15, 5), None, sender=MINH, media=[PAY[0]])], runner)
        item = body["items"][0]
        self.assertEqual((item["source"], item["direction"], item["amount_vnd"], item["amount_from"], item["status"], item["target"]),
                         ("anh", "thu", 7_000_000, "anh", "RECORDED", {"kind": "so", "id": 1, "label": "KHACH A"}))
        self.assertEqual(item["image"], {"by": "ocr", "bank": "VCB", "txn_time": "2026-11-19T15:02:00+07:00", "candidates": [7_000_000]})
        self.assertEqual(([media["id"] for media in item["media"]], item["sender_name"], item["text"]), ([PAY[0]], "Minh", ""))
        self.assertEqual((body["totals"]["thu_vnd"], body["totals"]["thu_count"], body["totals"]["from_image"]), (7_000_000, 1, 1))

    def test_own_deleted_and_unread_images_are_not_receipts(self):
        self.write_reads({PAY[0]: read_entry(7_000_000)})
        runner = FakeRunner(links=[LINK])
        body = self.get([row("own", at(19), None, sender=HAO, media=[PAY[0]]), row("plain", at(19, 10), None, sender=MINH, media=[PHOTO]),
                         dict(row("gone", at(19, 11), None, sender=MINH, media=[PAY[0]]), deleted=True)], runner)
        self.assertEqual(body["items"], [])
        self.assertNotIn("get_zalo_links", [name for name, _ in runner.calls])   # không có ảnh nào thì không đọc danh sách nhóm gắn sổ

    def test_unsure_read_has_no_amount_and_stays_out_of_totals(self):
        self.write_reads({PAY[0]: read_entry(None, by="human", reads=[{"engine": "easyocr", "amount_vnd": 1_500_000}, {"engine": "b", "amount_vnd": 1_050_000},
                                                                       {"engine": "c", "amount_vnd": None}])})
        body = self.get([row("img", at(19), None, sender=MINH, media=[PAY[0]])], FakeRunner(links=[LINK]))
        item = body["items"][0]
        self.assertEqual((item["status"], item["amount_vnd"], item["amount_from"], item["image"]["by"], item["image"]["candidates"]),
                         ("NO_AMOUNT", None, None, "human", [1_050_000, 1_500_000]))
        self.assertEqual((body["totals"]["thu_vnd"], body["totals"]["no_amount"], body["totals"]["from_image"]), (0, 1, 0))

    def test_conversation_not_linked_to_exactly_one_book_is_unknown(self):
        self.write_reads({PAY[0]: read_entry(7_000_000)})
        rows = [row("img", at(19), None, sender=MINH, media=[PAY[0]])]
        alone = self.get(rows, FakeRunner())["items"][0]
        self.assertEqual((alone["status"], alone["target"]["kind"], alone["ambiguous"]), ("UNKNOWN_TARGET", None, False))
        two = self.get(rows, FakeRunner(links=[LINK, {**LINK, "customer_id": 2, "customer_name": "KHACH B"}]))["items"][0]
        self.assertEqual((two["status"], two["ambiguous"]), ("UNKNOWN_TARGET", True))
        elsewhere = self.get(rows, FakeRunner(links=[{**LINK, "conversation_id": OTHER}]))["items"][0]
        self.assertIsNone(elsewhere["target"]["kind"])
        suggest = self.get(rows, FakeRunner(receipts=[receipt(3, 4, "KHACH D", 19, 7_000_000)]))["items"][0]
        self.assertEqual((suggest["status"], suggest["ledger_ref"]["customer_id"]), ("SUGGEST", 4))

    def test_proof_image_is_compared_with_the_typed_amount(self):
        self.write_reads({PAY[0]: read_entry(5_500_000), PAY[1]: read_entry(5_000_000)})
        runner = FakeRunner(receipts=[receipt(1, 1, "KHACH A", 19, 5_000_000)])
        body = self.get([row("m", at(19, 9), "thu 5tr khách a"), row("p", at(19, 9, 1), None, media=[PAY[0]])], runner)
        item = body["items"][0]
        self.assertEqual(len(body["items"]), 1)   # ảnh chứng không thành khoản thứ hai
        # Mẫu và ảnh khác số: cảnh báo riêng, trạng thái đối chiếu giữ nguyên (đã vào sổ theo số gõ).
        self.assertEqual((item["status"], item["image_diff"], item["amount_vnd"], item["image_vnd"], item["ledger_vnd"], item["amount_from"]),
                         ("RECORDED", True, 5_000_000, 5_500_000, 5_000_000, None))
        self.assertEqual(body["totals"]["amount_diff"], 1)
        same = self.get([row("m", at(19, 9), "thu 5tr khách a"), row("p", at(19, 9, 1), None, media=[PAY[1]])], runner)["items"][0]
        self.assertEqual((same["status"], same["image_vnd"], same["image_diff"]), ("RECORDED", 5_000_000, False))
        filled = self.get([row("m", at(19, 9), "thu 50 khach a"), row("p", at(19, 9, 1), None, media=[PAY[1]])], runner)["items"][0]
        self.assertEqual((filled["status"], filled["amount_vnd"], filled["amount_from"], filled["image_diff"]), ("RECORDED", 5_000_000, "anh", False))
        both = self.get([row("m", at(19, 9), "thu 5tr khách a"), row("p", at(19, 9, 1), None, media=[PAY[0], PAY[1]])], runner)["items"][0]
        self.assertEqual((both["status"], both["image_vnd"], both["image_diff"]), ("RECORDED", None, False))   # hai ảnh đọc ra hai số: không so

    def test_image_mismatch_keeps_the_matching_status(self):
        """Review #562 (6): "mẫu X, ảnh Y" là cảnh báo thêm, không đè gợi ý sổ hay "chưa vào sổ"."""
        self.write_reads({PAY[0]: read_entry(5_500_000)})
        suggest = self.get([row("m", at(19, 9), "thu 5tr"), row("p", at(19, 9, 1), None, media=[PAY[0]])],
                           FakeRunner(receipts=[receipt(3, 4, "KHACH D", 19, 5_000_000)]))["items"][0]
        self.assertEqual((suggest["status"], suggest["image_diff"], suggest["ledger_ref"]["customer_id"]), ("SUGGEST", True, 4))
        body = self.get([row("m", at(15, 9), "thu 5tr khách a"), row("p", at(15, 9, 1), None, media=[PAY[0]])], FakeRunner())
        self.assertEqual((body["items"][0]["status"], body["items"][0]["image_diff"], body["counts"]["MISSING"]), ("MISSING", True, 1))

    def test_typed_report_takes_the_proof_amount_before_screenshots_are_matched(self):
        """Review #562 (1): mẫu không đọc được số lấy số ảnh chứng trước, nên ảnh khách gửi trước đó gộp vào, không thành khoản thứ hai."""
        self.write_reads({PAY[0]: read_entry(50_000_000), PAY[1]: read_entry(50_000_000)})
        rows = [row("s1", at(19, 9), None, sender=MINH, media=[PAY[0]]), row("m", at(19, 9, 5), "thu 50 khách a"), row("s2", at(19, 9, 6), None, media=[PAY[1]])]
        body = self.get(rows, FakeRunner(links=[LINK]))
        self.assertEqual([(item["message_id"], item["amount_vnd"], item["amount_from"]) for item in body["items"]], [("m", 50_000_000, "anh")])
        self.assertEqual(sorted(media["id"] for media in body["items"][0]["media"]), sorted([PAY[0], PAY[1]]))
        self.assertEqual(body["totals"]["thu_vnd"], 50_000_000)

    def test_screenshot_merged_later_does_not_hide_the_proof_mismatch(self):
        """Review #562 (1): số ảnh chứng tính trước khi gộp, ảnh của khách gộp sau không xóa cảnh báo "mẫu X, ảnh Y"."""
        self.write_reads({PAY[0]: read_entry(6_500_000), PAY[1]: read_entry(7_000_000)})
        rows = [row("m", at(19, 9), "thu 7tr khách a"), row("p", at(19, 9, 1), None, media=[PAY[0]]), row("s", at(19, 9, 30), None, sender=MINH, media=[PAY[1]])]
        body = self.get(rows, FakeRunner(links=[LINK]))
        item = body["items"][0]
        self.assertEqual((len(body["items"]), item["image_vnd"], item["image_diff"], body["totals"]["thu_vnd"]), (1, 6_500_000, True, 7_000_000))
        self.assertEqual([media["id"] for media in item["media"]], [PAY[0], PAY[1]])

    def test_proof_wins_over_a_standalone_copy_in_any_order(self):
        """Review #562 (2): ảnh đã làm ảnh chứng ở bất kỳ nhóm nào thì không thành khoản riêng, dù nhóm nào được đọc trước."""
        self.write_reads({PAY[0]: read_entry(7_000_000)})
        for report_in, alone_in in ((GROUP, OTHER), (OTHER, GROUP)):
            with self.subTest(report_in=report_in[:1]):
                rows = [row("s", at(19, 9), None, sender=MINH, cid=alone_in, media=[PAY[0]]), row("m", at(19, 10), "thu 7tr khách a", cid=report_in),
                        row("p", at(19, 10, 1), None, cid=report_in, media=[PAY[0]])]
                body = self.get(rows, FakeRunner(links=[LINK]))
                self.assertEqual(([item["message_id"] for item in body["items"]], body["totals"]["thu_vnd"]), (["m"], 7_000_000))
        same = self.get([row("s", at(19, 9), None, sender=MINH, media=[PAY[0]]), row("m", at(19, 9, 30), "thu 5tr khách a"),
                         row("p", at(19, 9, 31), None, media=[PAY[0]])], FakeRunner(links=[LINK]))
        self.assertEqual(([item["message_id"] for item in same["items"]], same["items"][0]["image_diff"], same["totals"]["thu_vnd"]), (["m"], True, 5_000_000))

    def test_image_never_guesses_a_receipt_held_by_a_contact_mark(self):
        """Review #562 (3): ảnh 7 triệu không "lệch" với phiếu 5 triệu mà dấu khách báo đang giữ, và không làm ẩn dấu đó."""
        mark = {"id": 1, "kind": "paid_claim", "status": "received", "customer_id": 1, "amount_vnd": "5000000", "on_date": "2026-11-17", "conversation_id": GROUP,
                "message_id": "claim", "message_at": "2026-11-17T09:00:00+07:00", "receipt_pid": "PH-1"}
        self.write_reads({PAY[0]: read_entry(7_000_000), PAY[1]: read_entry(5_000_000)})
        runner = FakeRunner(receipts=[receipt(1, 1, "KHACH A", 17, 5_000_000)], marks=[mark], links=[LINK])
        body = self.get([row("img", at(19, 10), None, sender=MINH, media=[PAY[0]])], runner)
        self.assertEqual(sorted((item["source"], item["status"], item["amount_vnd"]) for item in body["items"]),
                         [("anh", "WAITING", 7_000_000), ("mark", "RECORDED", 5_000_000)])
        self.assertEqual(body["totals"]["thu_vnd"], 12_000_000)
        other = self.get([row("img", at(19, 10), None, sender=MINH, cid=OTHER, media=[PAY[1]])], runner)   # nhóm chưa gắn sổ, đúng số phiếu của dấu
        self.assertEqual(sorted((item["source"], item["status"]) for item in other["items"]), [("anh", "UNKNOWN_TARGET"), ("mark", "RECORDED")])

    def test_old_screenshot_counts_on_its_transaction_day(self):
        """Review #562 (4): ảnh cũ gửi lại đối chiếu và cộng theo ngày giao dịch; giao dịch trước khoảng xem thì không cộng, chỉ đếm."""
        self.write_reads({PAY[0]: read_entry(5_000_000, txn="2026-11-02T10:15:00+07:00")})
        rows = [row("img", at(19, 10), None, sender=MINH, media=[PAY[0]])]
        runner = FakeRunner(receipts=[receipt(1, 1, "KHACH A", 2, 5_000_000)], links=[LINK])
        wide = self.get(rows, runner, query="from=2026-11-01&to=2026-11-20")
        self.assertEqual((wide["items"][0]["day"], wide["items"][0]["status"], wide["images_before"]), ("2026-11-02", "RECORDED", 0))
        narrow = self.get(rows, runner, query="from=2026-11-14&to=2026-11-20")
        self.assertEqual((narrow["items"], narrow["images_before"], narrow["totals"]["thu_vnd"]), ([], 1, 0))

    def test_different_transaction_times_are_different_payments(self):
        """Review #562 (5): khoản gõ hay dấu chỉ nhận ảnh của đúng lần trả của nó; giờ giao dịch khác là lần trả khác."""
        self.write_reads({PAY[0]: read_entry(7_000_000, txn="2026-11-19T08:58:00+07:00"), PAY[1]: read_entry(7_000_000, txn="2026-11-19T14:55:00+07:00"),
                          PAY[2]: read_entry(7_000_000, txn="2026-11-18T10:00:00+07:00"), PAY[3]: read_entry(7_000_000, txn="2026-11-19T11:00:00+07:00")})
        rows = [row("m", at(19, 9), "thu 7tr khách a"), row("p", at(19, 9, 1), None, media=[PAY[0]]), row("s", at(19, 15), None, sender=MINH, media=[PAY[1]])]
        body = self.get(rows, FakeRunner(links=[LINK]))
        self.assertEqual((sorted(item["message_id"] for item in body["items"]), body["totals"]["thu_vnd"]), (["m", "s"], 14_000_000))
        mark = {"id": 1, "kind": "paid_claim", "status": "waiting", "customer_id": 1, "amount_vnd": "7000000", "on_date": "2026-11-19", "conversation_id": GROUP,
                "message_id": "claim", "message_at": "2026-11-19T09:00:00+07:00", "receipt_pid": None}
        rows = [row("a", at(18, 10, 5), None, sender=MINH, media=[PAY[2]]), row("b", at(19, 11, 5), None, sender=MINH, media=[PAY[3]])]
        body = self.get(rows, FakeRunner(marks=[mark], links=[LINK]))
        self.assertEqual(sorted((item["source"], [media["id"] for media in item["media"]]) for item in body["items"]), [("anh", [PAY[3]]), ("mark", [PAY[2]])])
        self.assertEqual(body["totals"]["thu_vnd"], 14_000_000)

    def test_same_transaction_joins_its_payment_without_a_time_limit(self):
        """Review #562 (7): ảnh cùng số, cùng giờ giao dịch gửi lại hai ngày sau vẫn gắn vào lần trả đã có."""
        txn = "2026-11-17T09:05:00+07:00"
        self.write_reads({PAY[0]: read_entry(7_000_000, txn=txn), PAY[1]: read_entry(7_000_000, txn=txn)})
        rows = [row("m", at(17, 9), "thu 7tr khách a"), row("s1", at(17, 9, 10), None, sender=MINH, media=[PAY[0]]),
                row("s2", at(19, 10), None, sender=MINH, media=[PAY[1]])]
        body = self.get(rows, FakeRunner(links=[LINK]))
        self.assertEqual([(item["message_id"], [media["id"] for media in item["media"]]) for item in body["items"]], [("m", [PAY[0], PAY[1]])])
        self.assertEqual(body["totals"]["thu_vnd"], 7_000_000)

    def test_link_reason_tells_why_the_book_is_unknown(self):
        """Review #562 (8): lý do chưa rõ sổ đi kèm khoản, không đoán từ cờ `unchecked`."""
        self.write_reads({PAY[0]: read_entry(7_000_000)})
        rows = [row("img", at(19), None, sender=MINH, media=[PAY[0]])]
        for expected, links in (("none", []), ("many", [LINK, {**LINK, "customer_id": 2}]), ("one", [LINK])):
            with self.subTest(expected):
                self.assertEqual(self.get(rows, FakeRunner(links=links))["items"][0]["link"], expected)
        failed = self.get(rows, FakeRunner(fail={"get_zalo_links"}))["items"][0]
        self.assertEqual((failed["link"], failed["unchecked"]), ("failed", True))
        customers = self.get(rows, FakeRunner(fail={"list_customers"}))["items"][0]
        self.assertEqual((customers["link"], customers["unchecked"]), ("none", True))

    def test_transaction_times_are_normalised(self):
        for raw, expected in {"2026-11-19 15:02": "2026-11-19T15:02", "2026-11-19T08:02:00Z": "2026-11-19T08:02:00+00:00",
                              "2026-11-19T15:02+0700": "2026-11-19T15:02+07:00", "2026-11-19": "2026-11-19", "2026-02-30": None, "2026-11-19T25:00": None,
                              "hôm qua": None, None: None, 5: None}.items():
            with self.subTest(raw=raw):
                self.assertEqual(cash._txn_time(raw), expected)
        self.assertEqual(cash.txn_key("2026-11-19T08:02:00+00:00"), cash.txn_key("2026-11-19T15:02+07:00"))
        self.assertIsNone(cash.txn_key("2026-11-19"))

    def test_the_same_payment_is_counted_once(self):
        txn = "2026-11-19T15:02:00+07:00"
        self.write_reads({PAY[0]: read_entry(7_000_000, txn=txn), PAY[1]: read_entry(7_000_000, txn=txn), PAY[2]: read_entry(7_000_000, txn="2026-11-19"),
                          PAY[3]: read_entry(7_000_000, txn="2026-11-19")})
        runner = FakeRunner(links=[LINK])
        media = lambda body: [(item["message_id"], item["source"], [one["id"] for one in item["media"]]) for item in body["items"]]   # noqa: E731
        again = self.get([row("a", at(19, 15), None, sender=MINH, media=[PAY[0]]), row("b", at(19, 15, 30), None, sender=MINH, media=[PAY[0]]),
                          row("c", at(19, 16), None, sender=MINH, media=[PAY[1]])], runner)
        self.assertEqual(media(again), [("a", "anh", [PAY[0], PAY[1]])])   # cùng ảnh gửi lại; ảnh khác cùng số, cùng giờ giao dịch
        dates = self.get([row("a", at(19, 15), None, sender=MINH, media=[PAY[2]]), row("b", at(19, 16), None, sender=MINH, media=[PAY[3]])], runner)
        self.assertEqual(len(dates["items"]), 2)   # chỉ có ngày giao dịch: không đủ để gộp
        typed = self.get([row("m", at(18, 20), "thu 7tr khách a"), row("img", at(19, 15), None, sender=MINH, media=[PAY[0]]),
                          row("later", at(20, 9), None, sender=MINH, media=[PAY[2]])], runner)
        self.assertEqual(media(typed), [("later", "anh", [PAY[2]]), ("m", "chat", [PAY[0]])])   # 19 giờ sau thì gộp, 37 giờ sau thì không
        self.assertEqual(typed["totals"]["thu_vnd"], 14_000_000)

    def test_contact_mark_keeps_the_payment_and_takes_the_image(self):
        self.write_reads({PAY[0]: read_entry(7_000_000), PAY[1]: read_entry(9_000_000), PAY[2]: read_entry(4_000_000)})
        base = {"kind": "paid_claim", "status": "waiting", "customer_id": 1, "conversation_id": GROUP, "message_at": "2026-11-19T10:00:00+07:00", "receipt_pid": None}
        marks = [{**base, "id": 1, "amount_vnd": "8000000", "on_date": "2026-11-19", "message_id": "on-image"},   # dấu đặt ngay trên tin ảnh
                 {**base, "id": 2, "amount_vnd": "9000000", "on_date": "2026-11-18", "message_id": "text-msg"}]   # cùng số, ngày báo cách 1 ngày
        rows = [row("on-image", at(19, 10), None, sender=MINH, media=[PAY[0]]), row("near", at(19, 11), None, sender=MINH, media=[PAY[1]]),
                row("free", at(19, 12), None, sender=MINH, media=[PAY[2]])]
        body = self.get(rows, FakeRunner(marks=marks, links=[LINK]))
        found = sorted((item["source"], item["amount_vnd"], item["image_vnd"], [one["id"] for one in item["media"]]) for item in body["items"])
        self.assertEqual(found, [("anh", 4_000_000, 4_000_000, [PAY[2]]), ("mark", 8_000_000, 7_000_000, [PAY[0]]), ("mark", 9_000_000, 9_000_000, [PAY[1]])])
        self.assertEqual(body["totals"]["thu_vnd"], 21_000_000)   # số người nhập trên dấu, mỗi lần trả một lần

    def test_bad_reads_file_never_breaks_the_page(self):
        rows = [row("m", at(19), "thu 5tr khách a"), row("img", at(19, 10), None, sender=MINH, media=[PAY[0]])]
        self.reads.parent.mkdir()
        for content in ("{hỏng", json.dumps({"schema": 2, "reads": {}}), json.dumps({"schema": 1, "reads": []}), json.dumps([1, 2])):
            with self.subTest(content=content[:12]):
                self.reads.write_text(content, encoding="utf-8")
                body = self.get(rows, FakeRunner(links=[LINK]))
                self.assertEqual(([item["message_id"] for item in body["items"]], body["sources_failed"]), (["m"], ["reads"]))
        self.write_reads({"KHONG-PHAI-SHA": read_entry(1_000_000), PAY[0]: read_entry("7000000"), PAY[1]: read_entry(True), PAY[2]: read_entry(0),
                          PAY[3]: {**read_entry(2_000_000), "by": "Bad By"}, PAY[4]: {**read_entry(3_000_000), "bank": "x" * 41, "txn_time": "hôm qua"},
                          PAY[5]: [1]})
        body = self.get([row(f"i{n}", at(19, 10 + n), None, sender=MINH, media=[PAY[n]]) for n in range(6)], FakeRunner(links=[LINK]))
        self.assertEqual(body["sources_failed"], [])
        self.assertEqual([(item["message_id"], item["amount_vnd"], item["image"]["bank"], item["image"]["txn_time"]) for item in body["items"]],
                         [("i4", 3_000_000, None, None)])   # mục sai khuôn bị bỏ; ngân hàng, giờ lạ để trống

    def test_failing_link_list_leaves_image_items_unchecked(self):
        self.write_reads({PAY[0]: read_entry(7_000_000)})
        body = self.get([row("img", at(19), None, sender=MINH, media=[PAY[0]])], FakeRunner(fail={"get_zalo_links"}, links=[LINK]))
        item = body["items"][0]
        self.assertEqual((body["sources_failed"], item["status"], item["unchecked"]), (["links"], "UNKNOWN_TARGET", True))

    def test_reads_file_is_read_again_when_it_changes(self):
        rows = [row("img", at(19), None, sender=MINH, media=[PAY[0]])]
        self.write_reads({PAY[0]: read_entry(7_000_000)})
        self.assertEqual(self.get(rows, FakeRunner(links=[LINK]))["items"][0]["amount_vnd"], 7_000_000)
        self.write_reads({PAY[0]: read_entry(17_000_000)})
        self.assertEqual(self.get(rows, FakeRunner(links=[LINK]))["items"][0]["amount_vnd"], 17_000_000)


class QueryAndRouteTests(CashChatCase):
    def test_query_validation(self):
        for query in ("from=2026-11-21&to=2026-11-20", "from=2026-02-30", "from=2026-08-01&to=2026-11-20", "status=NOPE", "x=1", "from=a&from=b",
                      "to=20-11-2026"):
            with self.subTest(query), self.assertRaises(ApiError):
                cash.parse_query(query, datetime(2026, 11, 20, tzinfo=VN).date())
        start, end, wanted = cash.parse_query("", datetime(2026, 11, 20, tzinfo=VN).date())
        self.assertEqual((start.isoformat(), end.isoformat(), wanted), ("2026-11-14", "2026-11-20", set()))

    def test_route_goes_through_identity_and_validation(self):
        write_bundle(self.dir, [row("a", at(19), "thu 5tr khách a")])
        headers = {"Host": "127.0.0.1:8780"}
        runner = FakeRunner()
        status, body = api.handle("GET", "/api/v7/cash-chat?status=WAITING", headers, b"", runner, port=8780, host="127.0.0.1", actor="tester")
        self.assertEqual(status, 200)
        self.assertEqual((body["unavailable"], sorted(body["counts"])), (False, sorted(cash.STATUSES)))   # giờ thật: khoảng 7 ngày mặc định có thể không còn tin bịa
        with self.assertRaises(ApiError) as caught:
            api.handle("GET", "/api/v7/cash-chat?status=NOPE", headers, b"", runner, port=8780, host="127.0.0.1", actor="tester")
        self.assertEqual(caught.exception.status, 422)
        with self.assertRaises(ApiError) as caught:
            api.handle("POST", "/api/v7/cash-chat", {**headers, "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}, b"{}", runner,
                       port=8780, host="127.0.0.1", actor="tester")
        self.assertIn(caught.exception.status, (404, 405, 422))

    def test_only_managers_may_call_the_route(self):
        self.assertTrue(v7_role.admin_api("/api/v7/cash-chat"))
        self.assertFalse(v7_role.allowed("/api/v7/cash-chat", v7_role.USER, {}))
        self.assertTrue(v7_role.allowed("/api/v7/cash-chat", v7_role.ADMIN, {}))


class ReviewTests(CashChatCase):
    """ZALO-THU-CHI-01 PR-3: xác nhận, gắn đối tượng, sửa số, loại; không ghi tiền."""

    def post(self, body, runner):
        write_bundle(self.dir, [row("a", at(19), "thu 5tr khách a"), {**row("d", at(19), "chi 1tr xe 51C-123.45"), "deleted": True}])
        chat._STORE, chat._STORE_DIR = None, None
        return cash.handle_review(json.dumps(body).encode(), runner, "tester")

    def test_review_goes_to_the_sql_function_with_the_bundle_conversation_and_clears_the_cache(self):
        runner = FakeRunner()
        cash._CACHE[("cu",)] = (NOW, {})
        status, _ = self.post({"message_id": "a", "action": "amount", "value": "4500000", "request_id": "r1"}, runner)
        self.assertEqual(status, 200)
        self.assertEqual(runner.recorded, [{"message_id": "a", "action": "amount", "request_id": "r1", "reason": None, "amount_vnd": "4500000",
                                            "conversation_id": GROUP}])
        self.assertEqual(cash._CACHE, {})   # lần hỏi kế tiếp của trang thấy ngay kết quả bấm
        self.post({"message_id": "a", "action": "target", "value": {"kind": "xe", "id": 10, "label": "51C"}, "request_id": "r2"}, runner)
        self.post({"message_id": "a", "action": "not_cash", "reason": "  tin hỏi giá ", "request_id": "r3"}, runner)
        self.assertEqual((runner.recorded[1]["target"], runner.recorded[2]["reason"]), ({"kind": "xe", "id": 10}, "tin hỏi giá"))

    def test_review_rejects_bad_bodies_before_the_database(self):
        cases = {
            "INVALID_CASH_REVIEW": [{"message_id": "a", "action": "xoa", "request_id": "r"}, {"message_id": "a", "action": "confirm"},
                                    {"message_id": "a", "action": "amount", "value": "0", "request_id": "r"},
                                    {"message_id": "a", "action": "amount", "value": 5000, "request_id": "r"},
                                    {"message_id": "a", "action": "target", "value": {"kind": "so", "id": "1"}, "request_id": "r"},
                                    {"message_id": "a", "action": "target", "value": {"kind": "khac", "id": 1}, "request_id": "r"},
                                    {"message_id": "a", "action": "confirm", "value": "1", "request_id": "r"},
                                    {"message_id": "a", "action": "confirm", "request_id": "r", "khac": 1},
                                    {"message_id": "../a", "action": "confirm", "request_id": "r"}],
            "REASON_REQUIRED": [{"message_id": "a", "action": "not_cash", "request_id": "r"},
                                {"message_id": "a", "action": "not_cash", "reason": "   ", "request_id": "r"}],
            "MESSAGE_NOT_FOUND": [{"message_id": "khong-co", "action": "confirm", "request_id": "r"},
                                  {"message_id": "d", "action": "confirm", "request_id": "r"}],   # tin đã xóa
        }
        for code, bodies in cases.items():
            for body in bodies:
                runner = FakeRunner()
                with self.subTest(body=body), self.assertRaises(ApiError) as caught:
                    self.post(body, runner)
                self.assertEqual((caught.exception.code, runner.recorded), (code, []))

    def test_reviews_replace_amount_and_target_and_drop_items_from_totals(self):
        rows = [row("a", at(19), "thu 5tr khách a"), row("b", at(19, 10), "chi 2tr xe 51C-123.45"), row("c", at(19, 11), "thu 3tr khách b")]
        rows.append(row("d", at(19, 12), "thu 2tr khách c"))
        reviews = {"a": {"amount_vnd": "4500000", "decision": "confirm", "reviews": 2, "last_action": "confirm", "last_by": "tester"},
                   "b": {"target": {"kind": "tai_xe", "id": 21}, "decision": None, "reviews": 1, "last_action": "target"},
                   "c": {"decision": "not_cash", "reason": "tin hỏi giá", "reviews": 1, "last_action": "not_cash"},
                   "d": {"amount_vnd": "rác", "target": {"kind": "so", "id": "1"}, "decision": "khac"}}   # giá trị lạ: bỏ
        runner = FakeRunner(receipts=[receipt(1, 1, "KHACH A", 19, 4_500_000)], reviews=reviews)
        body = self.get(rows, runner)
        self.assertNotIn("c", {item["message_id"] for item in body["items"]})   # khoản đã loại ẩn khỏi danh sách mặc định
        cash._CACHE.clear()
        by = {item["message_id"]: item for item in cash.handle_get("from=2026-11-01&to=2026-11-20&status=NOT_CASH,RECORDED,MISSING,WAITING,UNKNOWN_TARGET",
                                                                    runner, "tester", NOW)["items"]}
        self.assertEqual((by["d"]["amount_vnd"], by["d"]["target"]["id"], by["d"]["amount_from"]), (2_000_000, 3, None))
        self.assertEqual((by["a"]["amount_vnd"], by["a"]["amount_from"], by["a"]["status"], by["a"]["review"]["decision"]),
                         (4_500_000, "sua", "RECORDED", "confirm"))   # số đã sửa khớp phiếu
        self.assertEqual(by["b"]["target"], {"kind": "tai_xe", "id": 21, "label": "Cường"})
        self.assertEqual((by["c"]["status"], by["c"]["review"]["reason"], by["c"]["ledger_ref"]), ("NOT_CASH", "tin hỏi giá", None))
        self.assertEqual((body["totals"]["thu_vnd"], body["totals"]["thu_count"], body["counts"]["NOT_CASH"]), (6_500_000, 2, 1))
        self.assertEqual(body["sources_failed"], [])
        failed = self.get(rows, FakeRunner(receipts=[receipt(1, 1, "KHACH A", 19, 4_500_000)], reviews=reviews, fail={"get_cash_reviews"}))
        self.assertEqual((failed["sources_failed"], failed["counts"]["NOT_CASH"]), (["reviews"], 0))   # đọc lỗi thì báo, không im

    def test_a_corrected_typo_takes_its_screenshot_and_a_dropped_text_keeps_the_real_transfer(self):
        self.reads.parent.mkdir(exist_ok=True)
        self.reads.write_text(json.dumps({"schema": 1, "redact": "w1", "reads": {PAY[0]: read_entry(4_500_000)}}), encoding="utf-8")
        rows = [row("a", at(19), "thu 5tr khách a"), row("p", at(19, 9, 30), "", media=[PAY[0]])]
        fixed = self.get(rows, FakeRunner(reviews={"a": {"amount_vnd": "4500000", "reviews": 1, "last_action": "amount"}}))
        self.assertEqual(([item["message_id"] for item in fixed["items"]], fixed["totals"]["thu_vnd"]), (["a"], 4_500_000))   # không cộng hai lần
        self.assertEqual([media["id"] for media in fixed["items"][0]["media"]], [PAY[0]])
        rows = [row("a", at(19), "thu 4500k khách a"), row("p", at(19, 9, 30), "", media=[PAY[0]])]
        kept = self.get(rows, FakeRunner(reviews={"a": {"decision": "not_cash", "reason": "gõ nhầm", "reviews": 1}}))
        self.assertEqual(([(item["message_id"], item["source"]) for item in kept["items"]], kept["totals"]["thu_vnd"], kept["counts"]["NOT_CASH"]),
                         ([("p", "anh")], 4_500_000, 1))   # khoản gõ đã loại không kéo theo ảnh chuyển khoản thật

    def test_an_image_marked_not_cash_does_not_break_the_page(self):
        self.reads.parent.mkdir(exist_ok=True)
        self.reads.write_text(json.dumps({"schema": 1, "redact": "w1", "reads": {PAY[0]: read_entry(1_000_000)}}), encoding="utf-8")
        body = self.get([row("p", at(19), "", sender=MINH, media=[PAY[0]])],
                        FakeRunner(reviews={"p": {"decision": "not_cash", "reason": "ảnh cũ", "reviews": 1}}),
                        query="from=2026-11-01&to=2026-11-20&status=NOT_CASH")
        self.assertEqual((body["unavailable"], [item["status"] for item in body["items"]], body["totals"]["thu_vnd"]), (False, ["NOT_CASH"], 0))
        self.assertEqual(body["items"][0]["target"], {"kind": None, "id": None, "label": None})

    def test_a_vehicle_set_by_hand_survives_an_unreadable_fleet_list(self):
        body = self.get([row("u", at(19), "ứng 2tr xe 29H-678.90")],
                        FakeRunner(fail={"doixe_get_tong"}, reviews={"u": {"target": {"kind": "xe", "id": 10}, "reviews": 1}}))
        self.assertEqual((body["unavailable"], body["items"][0]["target"]["id"]), (False, 10))

    def test_a_message_with_two_read_images_is_not_reviewed(self):
        self.reads.parent.mkdir(exist_ok=True)
        self.reads.write_text(json.dumps({"schema": 1, "redact": "w1", "reads": {PAY[0]: read_entry(1_000_000), PAY[1]: read_entry(2_000_000)}}),
                              encoding="utf-8")
        write_bundle(self.dir, [row("p", at(19), "", media=[PAY[0], PAY[1]])])
        chat._STORE, chat._STORE_DIR = None, None
        runner = FakeRunner(reviews={"p": {"amount_vnd": "9000000", "reviews": 1}})
        with self.assertRaises(ApiError) as caught:
            cash.handle_review(json.dumps({"message_id": "p", "action": "confirm", "request_id": "r"}).encode(), runner, "tester")
        self.assertEqual((caught.exception.code, runner.recorded), ("MULTIPLE_IMAGES", []))
        body = self.get([row("p", at(19), "", media=[PAY[0], PAY[1]])], runner)
        self.assertEqual(sorted(item["amount_vnd"] for item in body["items"]), [1_000_000, 2_000_000])   # không áp cho cả hai ảnh

    def test_only_managers_may_review(self):
        self.assertTrue(v7_role.admin_api("/api/v7/cash-chat/review"))
        self.assertFalse(v7_role.allowed("/api/v7/cash-chat/review", v7_role.USER, {}))
        self.assertIs(api.POST_HANDLERS["/api/v7/cash-chat/review"], cash.handle_review)


class SqlRuleSyncTests(unittest.TestCase):
    def test_window_matches_the_contact_mark_scoring_in_sql(self):
        """Hai nơi cùng chấm "khách báo đã chuyển": đổi một nơi mà quên nơi kia thì test này đỏ."""
        sql = (ROOT / "tools" / "v7_backend_functions.sql").read_text(encoding="utf-8")
        body = sql[sql.index("ELSIF m.kind='paid_claim' THEN"):]
        body = body[:body.index("END IF;")]
        before, after = re.search(r"r\.date BETWEEN m\.on_date-(\d+) AND m\.on_date\+(\d+)", body).groups()
        missing = re.search(r"p_today>m\.on_date\+(\d+) THEN 'not_seen'", body).group(1)
        self.assertEqual((cash.MATCH_BEFORE, cash.MATCH_AFTER, cash.MISSING_AFTER), (int(before), int(after), int(missing)))


if __name__ == "__main__":
    unittest.main()
