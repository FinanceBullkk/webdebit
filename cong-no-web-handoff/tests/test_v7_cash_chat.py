"""ZALO-THU-CHI-01 PR-2 (B1–B2): đọc mẫu thu/chi/ứng từ gói chat và đối chiếu chỉ đọc với sổ. Gói chat, sổ, xe, người đều bịa."""

import json
import os
import re
import sys
import tempfile
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
    (directory / "users.json").write_text(json.dumps({"users": {LAN: "Lan", MINH: "Minh"}}), encoding="utf-8")
    (directory / "media.json").write_text(json.dumps({PHOTO: {"mime": "image/jpeg", "width": 800, "height": 1200}}), encoding="utf-8")
    (directory / "export-report.json").write_text(json.dumps({"status": "BUNDLED", "built_at": "2026-11-20T09:55:00+07:00"}), encoding="utf-8")


def receipt(rid, customer, name, day, amount, source="web"):
    return {"source": source, "id": rid, "pid": f"PH-{rid}" if source == "web" else None, "customer_id": customer, "name": name,
            "date": f"2026-11-{day:02d}", "amount_vnd": str(amount)}


class FakeRunner:
    """Chỉ các hàm đọc mà trang Thu chi được phép gọi; hàm lạ thì nổ để test thấy ngay."""

    def __init__(self, receipts=(), marks=(), voided=(), ung=(), chang=()):
        self.receipts, self.marks, self.voided, self.ung, self.chang = list(receipts), list(marks), list(voided), list(ung), list(chang)
        self.calls = []

    def run(self, function, payload, actor, **_):
        self.calls.append((function, payload))
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
        raise AssertionError(f"hàm không được đọc: {function}")


class CashChatCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name) / "bundle"
        self.dir.mkdir()
        self.status = Path(folder.name) / "status.json"
        for patcher in (patch.object(chat, "EXPORT_DIR", str(self.dir)), patch.object(chat, "_STORE", None), patch.object(chat, "_STORE_DIR", None),
                        patch.dict(os.environ, {"WEBDEBIT_ZALO_AGENT_STATUS": str(self.status)}), patch.dict(cash._CACHE, clear=True)):
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
        for text in ("thu 50 khach a", "chi 500 dầu", "thu 12/11 50tr", "chi 2,5,5tr", "thu 0k", "chi 2.5555k", "thu 99999999999999999tr"):
            with self.subTest(text):
                self.assertIsNone(cash.read_report(text)["amount_vnd"])

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
        [{"id": 20, "ten": "Bình", "dang_dung": True}, {"id": 21, "ten": "Bình An", "dang_dung": True}, {"id": 22, "ten": "Cường", "dang_dung": False}])

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
        for text in ("chi 2tr5 dầu xe 12345", "chi 2tr5 dầu 2345", "chi 2tr5 dầu xe 123.45", "chi 2tr5 dầu xe 51C-123.45"):
            with self.subTest(text):
                self.assertEqual((self.target(text)["kind"], self.target(text)["id"]), ("xe", 10))

    def test_vehicle_ambiguous_or_unknown_gets_no_target(self):
        self.assertIsNone(self.target("chi 2tr5 dầu xe 3945")["kind"])   # không xe nào
        self.assertIsNone(self.target("chi 2tr5 dầu xe 99945 va 12345")["kind"])   # hai xe
        self.assertIsNone(self.target("chi 2tr5 dầu xe 123")["kind"])   # dưới 4 số

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
        source = (ROOT / "web" / "v7_cash_chat.py").read_text(encoding="utf-8")
        self.assertNotIn("record_", source)
        self.assertNotIn("ghi_", source)
        self.assertNotRegex(source, r"v7_ai_explain|anthropic|gemini|openai")


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
