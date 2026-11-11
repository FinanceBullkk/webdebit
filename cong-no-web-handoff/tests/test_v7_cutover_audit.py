"""Audit trước chuyển hẳn (specs/v7-cutover-audit.md): dữ liệu giả, không cần API, Sheet hay DB thật."""

import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_cutover_audit as audit  # noqa: E402
import v7_inbox  # noqa: E402  (v7_cutover_audit đã thêm web/ vào sys.path)
import v7_load_real_copy as loader  # noqa: E402

A, B = {"id": 1, "name": "Khách A"}, {"id": 2, "name": "Khách B"}


def text(value):
    return None if value is None else str(value)


def trip(trip_id, container, month, price, day=None, status="confirmed"):
    return {"id": trip_id, "container": container, "month": f"{month}-01", "event_date": day, "unit_price_vnd": text(price), "other_fee_vnd": None,
            "status": status, "is_missing_price": price is None}


def old(row_id, container, month, counted, day=None, flags=(), kind="trip", source_total=None):
    current = None if kind == "receipt" else {"container": container, "month": f"{month}-01", "event_date": day, "unit_price_vnd": text(counted),
                                              "other_fee_vnd": None, "counted_vnd": text(counted), "deleted": False}
    return {"id": row_id, "kind": kind, "month": f"{month}-01", "current": current, "display": {"flags": list(flags)}, "source_total_vnd": text(source_total)}


def book(customer, total, months, **parts):
    return {"customer_id": customer["id"], "total_outstanding_vnd": str(total), "today_month": "2026-11-01",
            "months": [{"month": f"{month}-01", "charges_vnd": str(charges), "received_vnd": str(received)} for month, charges, received in months],
            "trips": [], "legacy_rows": [], "adjustments": [], "receipts": [], "month_locks": [], **parts}


def sheet(customer, row, month, container, money=None, day=None):
    return {"customer_tab": customer["name"], "source_row": row, "debt_month": month, "container": container, "date": day,
            "sheet_unit_price_vnd": money, "sheet_other_fee_vnd": None, "sheet_total_vnd": money}


def paid(customer, row, month, amount):
    return {"customer_tab": customer["name"], "source_row": row, "debt_month": month, "amount_vnd": amount, "note": ""}


def rows(ledgers, prices, receipts=(), ahead=None, customers=(A, B)):
    used = [customer for customer in customers if customer["id"] in ledgers]
    return audit.audit_rows(used, ledgers, {"rows": list(prices)}, {"rows": list(receipts)}, ahead or {})


def whys(items):
    return sorted(item["why"] for item in items)


class RowTests(unittest.TestCase):
    def test_book_equal_to_its_tab_leaves_nothing_to_explain(self):
        result = rows({1: book(A, 100, [("2026-10", 100, 0)], legacy_rows=[old(11, "AAAU1111111", "2026-10", 100, day="2026-10-05")])},
                      [sheet(A, 10, "2026-10", "AAAU1111111", 100, day="2026-10-05")])
        only = result["books"][0]
        self.assertEqual(dict(only["statuses"]), {"PRICE_UNCHANGED": 1})
        self.assertEqual((only["month_diffs"], only["not_found"], only["web_only"], only["row_diffs"], only["paid_why"]), ([], [], [], [], None))
        self.assertEqual((result["tabs_without_book"], result["books_without_tab"]), ([], []))

    def test_row_money_is_the_total_column_or_else_price_plus_fee(self):
        fee_trip = trip(21, "FEEU0000001", "2026-10", 50, day="2026-10-02") | {"other_fee_vnd": "5"}
        ledger = book(A, 135, [("2026-10", 135, 0)], legacy_rows=[old(11, "TOTU0000001", "2026-10", 80, day="2026-10-01")], trips=[fee_trip])
        ledger["legacy_rows"][0]["current"]["unit_price_vnd"] = None   # dòng sổ gốc chỉ có TỔNG, không có đơn giá
        tab = [sheet(A, 1, "2026-10", "TOTU0000001", day="2026-10-01") | {"sheet_total_vnd": 80},
               sheet(A, 2, "2026-10", "FEEU0000001", day="2026-10-02") | {"sheet_unit_price_vnd": 50, "sheet_other_fee_vnd": 5}]
        only = rows({1: ledger}, tab)["books"][0]
        self.assertEqual((only["month_diffs"], only["row_diffs"], only["sheet_charge"]), ([], [], {"2026-10": 135}))

    def test_reused_container_is_matched_to_the_trip_of_its_own_date(self):
        ledger = book(A, 150, [("2026-08", 70, 0), ("2026-10", 80, 0)],
                      legacy_rows=[old(11, "REUU0000001", "2026-08", 70, day="2026-08-01"), old(12, "REUU0000001", "2026-10", 80, day="2026-10-01")])
        only = rows({1: ledger}, [sheet(A, 1, "2026-08", "REUU0000001", 70, day="2026-08-02"), sheet(A, 2, "2026-10", "REUU0000001", 80, day="2026-10-01")])["books"][0]
        self.assertEqual((dict(only["statuses"]), only["ambiguous"], only["month_diffs"], only["web_only"]), ({"PRICE_UNCHANGED": 2}, 0, [], []))

    def test_web_ahead_is_accepted_only_when_it_adds_up_to_the_reconcile_figure(self):
        ledger = book(A, 70, [("2026-11", 70, 0)], trips=[trip(21, "BBBU2222222", "2026-11", 40, day="2026-11-03"), trip(22, "CCCU3333333", "2026-11", 30, day="2026-11-04")])
        tab = [sheet(A, 12, "2026-11", "CCCU3333333", None, day="2026-11-04")]   # Sheet đã có dòng nhưng chưa ghi tiền
        exact = rows({1: ledger}, tab, ahead={1: 70})["books"][0]
        self.assertEqual((whys(exact["web_only"]), whys(exact["row_diffs"]), whys(exact["month_diffs"])), (["WEB_DI_TRUOC"], ["WEB_DI_TRUOC"], ["WEB_DI_TRUOC"]))
        short = rows({1: ledger}, tab, ahead={1: 69})["books"][0]   # lệch một đồng so với số máy đối soát báo: không nhận
        self.assertEqual((whys(short["web_only"]), whys(short["row_diffs"]), whys(short["month_diffs"])), ([audit.UNEXPLAINED],) * 3)

    def test_same_container_listed_twice_on_the_tab(self):
        only = rows({1: book(A, 100, [("2025-06", 100, 0)], legacy_rows=[old(11, "DUPU0000001", "2025-06", 100, day="2025-06-10")])},
                    [sheet(A, 5, "2025-06", "DUPU0000001", 100, day="2025-06-10"), sheet(A, 9, "2025-06", "DUPU0000001", 100, day="2025-06-10")])["books"][0]
        self.assertEqual(dict(only["statuses"]), {"AMBIGUOUS": 2})
        self.assertEqual([(item["diff_vnd"], item["why"]) for item in only["month_diffs"]], [(-100, "DONG_LAP_TREN_SHEET")])

    def test_loader_made_rows_explain_themselves_by_their_flags(self):
        ledger = book(A, 0, [("2024-04", 100, 0), ("2026-01", 70, 130)], legacy_rows=[
            old(31, "SPRU0000001", "2024-04", 50, flags=[audit.FLAG_SPREAD]), old(32, "SPRU0000002", "2024-04", 50, flags=[audit.FLAG_SPREAD]),
            old(41, None, "2026-01", 70, flags=[audit.FLAG_CARRY]), old(42, None, "2025-01", None, flags=[audit.FLAG_CARRY], kind="receipt", source_total=30)])
        only = rows({1: ledger}, [sheet(A, 8, "2024-04", "SPRU0000001"), sheet(A, 9, "2024-04", "SPRU0000002")], [paid(A, 20, "2026-01", 100)])["books"][0]
        self.assertEqual({item["month"]: item["why"] for item in only["month_diffs"]}, {"2024-04": "TONG_TRAI_DEU_LUC_NAP", "2026-01": "BU_SO_DU_CHUYEN_NAM"})
        self.assertEqual(whys(only["row_diffs"]), ["TONG_TRAI_DEU_LUC_NAP"] * 2)
        self.assertEqual((only["paid_diff_vnd"], only["paid_why"]), (30, "BU_SO_DU_CHUYEN_NAM"))

    def test_rounding_needs_the_flag_and_at_most_one_dong_per_row(self):
        receipts = [paid(A, 20, "2026-07", 50), paid(A, 21, "2026-07", 50)]
        flagged = [old(51, "RNDU0000001", "2026-07", 0, flags=[audit.FLAG_ROUNDED])]
        tab = [sheet(A, 5, "2026-07", "RNDU0000001", 0)]

        def reason(received, legacy_rows):
            return rows({1: book(A, 0, [("2026-07", 0, received)], legacy_rows=legacy_rows)}, tab, receipts)["books"][0]["paid_why"]

        self.assertEqual(reason(102, flagged), "LAM_TRON_DONG")
        self.assertEqual(reason(103, flagged), audit.UNEXPLAINED)                                       # 3 đồng trên 2 dòng
        self.assertEqual(reason(102, [old(51, "RNDU0000001", "2026-07", 0)]), audit.UNEXPLAINED)      # không có cờ làm tròn

    def test_one_sided_rows_moved_retyped_adjusted_or_left_unexplained(self):
        first = book(A, 87, [("2026-03", 46, 0), ("2026-08", 25, 0), ("2026-09", 0, 0), ("2026-10", 7, 0)],
                     legacy_rows=[old(61, "TEXTA", "2026-08", 25)],
                     adjustments=[{"id": 1, "month": "2026-03-01", "amount_vnd": "46", "legacy_row_id": None, "trip_id": None},
                                  {"id": 2, "month": "2026-10-01", "amount_vnd": "7", "legacy_row_id": None, "trip_id": None}])
        second = book(B, 0, [("2026-03", 0, 0)], trips=[trip(71, "MOVU0000001", "2026-03", 46, day="2026-03-10")],
                      adjustments=[{"id": 3, "month": "2026-03-01", "amount_vnd": "-46", "legacy_row_id": None, "trip_id": None}])
        result = rows({1: first, 2: second}, [
            sheet(A, 1, "2026-03", "MOVU0000001", 46, day="2026-03-10"), sheet(A, 2, "2026-08", "TEXTA-取消", 25),
            sheet(A, 3, "2026-10", "PHIU0000007 取消", 7), sheet(A, 4, "2026-09", "LOSU0000009", 9, day="2026-09-09")])
        one, two = result["books"]
        self.assertEqual({item["source_row"]: item["why"] for item in one["not_found"]},
                         {1: "DOI_SANG_SO_KHAC", 2: "KHAC_CHU_O_CONTAINER", 3: "DA_GHI_BANG_DIEU_CHINH", 4: audit.UNEXPLAINED})
        self.assertEqual((whys(one["web_only"]), whys(two["web_only"])), (["KHAC_CHU_O_CONTAINER"], ["DOI_SANG_SO_KHAC"]))
        state = {"open_old_months": [], "missing_price": {}, "pending_review": 0, "offsets": 0, "queues": {}}
        summary = audit.summarize({"rows": result, "tong": {"month": None}, "activity": {}, "state": state, "reconcile": {}})
        self.assertEqual((summary["ok"], summary["must_explain"]["row_items"], summary["must_explain"]["month_diffs"]), (False, 1, 1))

    def test_tabs_and_books_without_a_partner_are_listed_until_acknowledged(self):
        ledgers = {1: book(A, 0, []), 2: book(B, 0, [])}
        prices = [sheet(A, 1, "2026-10", "AAAU1111111"), sheet({"name": "Copy of Khách A"}, 1, "2026-10", "AAAU1111111")]
        result = rows(ledgers, prices)
        self.assertEqual((result["tabs_without_book"], result["books_without_tab"]), (["Copy of Khách A"], [2]))
        ignored = audit.audit_rows([A, B], ledgers, {"rows": prices}, {"rows": []}, {}, frozenset({"Copy of Khách A"}))
        self.assertEqual((ignored["tabs_without_book"], ignored["tabs_ignored"]), ([], 1))


class TongTests(unittest.TestCase):
    def setUp(self):
        self.customers = ({"id": 1, "name": "DUONG BỘ-Khách  Ô"}, {"id": 2, "name": "Ngủ Quên"}, {"id": 3, "name": "Tên Lạ"})
        one = book(self.customers[0], 150, [("2026-10", 100, 0), ("2026-11", 50, 0)], legacy_rows=[old(11, "AAAU1111111", "2026-10", 100)],
                   trips=[trip(21, "BBBU2222222", "2026-11", 30), trip(22, "CCCU3333333", "2026-11", 20)])
        ledgers = {1: one, 2: book(self.customers[1], 77, [("2025-12", 77, 0)]), 3: book(self.customers[2], 5, [("2026-10", 5, 0)])}
        prices = [sheet(self.customers[0], 1, "2026-10", "AAAU1111111", 100), sheet(self.customers[0], 2, "2026-11", "BBBU2222222", 30)]
        self.ahead = {1: 20}
        self.books = rows(ledgers, prices, [paid(self.customers[0], 9, "2026-11", 10)], self.ahead, self.customers)["books"]

    def tong(self, *names_and_ends, aliases=None):
        table = {"month": "2026-10", "rows": [{"name": name, "end_vnd": end} for name, end in names_and_ends]}
        return audit.audit_tong(table, self.books, self.ahead, aliases or {})

    def test_month_end_equals_web_minus_ahead_minus_later_charges_plus_later_receipts(self):
        result = self.tong(("duong bo - KHACH O", 110), ("NGU QUEN", 77), ("Ten La", 5))   # 150 − 20 − 30 + 10 = 110
        self.assertEqual((result["matched"], result["differs"], result["unknown_names"], result["blank_on_tong"], result["gap_vnd"]), (3, [], [], [], 0))
        off = self.tong(("duong bo - KHACH O", 111), ("NGU QUEN", 77), ("Ten La", 5))
        self.assertEqual([(row["book"], row["tong_vnd"], row["expected_vnd"]) for row in off["differs"]], [(1, 111, 110)])

    def test_blank_cell_and_unknown_name_are_reported_and_alias_resolves_the_name(self):
        result = self.tong(("duong bo - KHACH O", 110), ("NGU QUEN", None), ("TEN KHAC HAN", 5))
        self.assertEqual([(row["book"], row["expected_vnd"]) for row in result["blank_on_tong"]], [(2, 77), (3, 5)])
        self.assertEqual(result["unknown_names"], [{"name": "TEN KHAC HAN", "end_vnd": 5}])
        self.assertEqual(result["gap_vnd"], 115 - 192)
        fixed = self.tong(("duong bo - KHACH O", 110), ("TEN KHAC HAN", 5), aliases={audit.tong_key("TEN KHAC HAN"): "Tên Lạ"})
        self.assertEqual((fixed["matched"], fixed["unknown_names"], [row["book"] for row in fixed["blank_on_tong"]]), (2, [], [2]))

    def test_unreadable_tong_is_skipped_not_guessed(self):
        self.assertEqual(audit.audit_tong({"month": None, "rows": []}, self.books, {}, {})["skipped"], "TONG_KHONG_DOC_DUOC")

    def test_read_tong_takes_the_rightmost_block_and_keeps_names(self):
        tab = [(6, {"D": "LOAI HANG", "E": "TÊN KHÁCH HÀNG", "H": "CÔNG NỢ PHÁT SINH TRONG THÁNG 9.2026", "I": "SỐ CÒN PHẢI THU CUỐI THÁNG",
                    "L": " LOAI HANG ", "M": " TÊN KHÁCH HÀNG ", "O": "CÔNG NỢ PHÁT SINH TRONG THÁNG 10.2026", "Q": " SỐ CÒN PHẢI THU CUỐI THÁNG "}),
               (7, {"E": "Khối cũ", "I": "9", "M": " Khách  A ", "Q": "500"}), (8, {"M": "Ô trống"}), (9, {"Q": "600"})]
        with patch.object(loader, "workbook_rows", return_value=[("CHANG", []), ("TONG ", tab)]):
            self.assertEqual(audit.read_tong(Path("khong-mo.xlsx")), {"month": "2026-10", "rows": [{"name": "Khách A", "end_vnd": 500}, {"name": "Ô trống", "end_vnd": None}]})
        with patch.object(loader, "workbook_rows", return_value=[("TONG", [(6, {"E": "TÊN KHÁCH HÀNG"})])]):
            self.assertEqual(audit.read_tong(Path("khong-mo.xlsx")), {"month": None, "rows": []})


def event(event_id, kind, actor, after, before=None, minute=0, customer_id=1):
    return {"id": event_id, "kind": kind, "actor": actor, "at": f"2026-11-05T02:{minute:02d}:00+00:00", "after": after, "before": before or {},
            "customer_id": customer_id, "counterparty_name": None}


class ActivityAndStateTests(unittest.TestCase):
    def test_machine_writes_that_people_had_to_undo_are_surfaced(self):
        person, machine = "nguoi.nhap@example.com", audit.MACHINE
        events = [
            event(1, "receipt", machine, {"receipt": 5, "pid": "PH-001", "amount_vnd": "100"}),
            event(2, "void", person, {"receipt": 5, "pid": "PH-001", "void_reason": "sai"}, {"amount_vnd": "100"}, minute=1),
            event(3, "adjust_month", machine, {"adjustment": 9, "amount_vnd": "7", "month": "2026-10-01"}, minute=2),
            event(4, "adjust_month_delete", machine, {}, {"adjustment": {"id": 9}}, minute=32),
            event(5, "price_edit", machine, {"price": {"trip_id": 3, "unit_price_vnd": "60", "other_fee_vnd": None}}, {"price": {"trip_id": 3, "unit_price_vnd": "50", "other_fee_vnd": None}}, minute=3),
            event(6, "price_edit", person, {"price": {"trip_id": 3, "unit_price_vnd": "50", "other_fee_vnd": None}}, {"price": {"trip_id": 3, "unit_price_vnd": "60", "other_fee_vnd": None}}, minute=4),
            event(7, "price_edit", machine, {"price": {"trip_id": 4, "unit_price_vnd": "10", "other_fee_vnd": None}}, {"price": {"trip_id": 4, "unit_price_vnd": None, "other_fee_vnd": None}}, minute=5),
            event(8, "paste", person, {"trips": [{"trip_id": 7}]}, minute=6), event(9, "trip_delete", person, {"trip": {"id": 7}}, minute=7),
            event(10, "month_lock", machine, {"month": "2026-10-01", "locked": False}, minute=8),
            event(11, "mystery", "claude", {}, minute=9),
        ]
        result = audit.audit_activity([{"day": "2026-11-05", "total": 99, "events": events}])
        robot = result["machine"]
        self.assertEqual((result["people"], result["person_events"], result["capped_days"], result["unknown_kinds"]), (1, 4, ["2026-11-05"], ["mystery"]))
        self.assertEqual((result["operations"]["Hủy phiếu"]["person"], result["operations"]["Ghi phiếu thu"]["machine"]), (1, 1))
        self.assertIn("Kết luận chuyến chờ kiểm", result["never_by_anyone"])
        self.assertIn("Ghi phiếu thu", result["never_by_person"])
        self.assertEqual([row["pid"] for row in robot["receipts_voided"]], ["PH-001"])
        self.assertEqual((robot["adjustments"], robot["adjustments_deleted"], robot["adjustment_minutes"]), (1, 1, [30, 30, 30]))
        self.assertEqual((robot["price_fills"], len(robot["price_overwrites"]), len(robot["price_flipped_back"]), len(robot["price_corrected_by_person"])), (1, 1, 1, 1))
        self.assertEqual((result["trips_deleted_by_origin"], robot["months_left_open"], robot["receipts_vnd"]), ({"person": 1}, 1, 100))

    def test_state_counts_come_from_the_ledgers_themselves(self):
        ledger = book(A, 0, [], trips=[trip(1, "AAAU1111111", "2026-11", None), trip(2, "BBBU2222222", "2026-11", None, status="pending_review")],
                      month_locks=[{"month": "2026-09-01", "locked": False}, {"month": "2026-11-01", "locked": False}, {"month": "2026-10-01", "locked": True}],
                      receipts=[{"pid": "PH-001", "voided_on": "2026-11-02"}, {"pid": "PH-002", "voided_on": None, "offset_pair_id": 4}],
                      sheet_sync={"new_count": 2, "conflict_count": 0})
        state = audit.audit_state([A], {1: ledger})
        self.assertEqual([(row["book"], row["month"]) for row in state["open_old_months"]], [(1, "2026-09")])
        self.assertEqual((state["missing_price"], state["pending_review"], state["receipts"], state["receipts_voided"], state["offsets"], state["queues"]),
                         ({"2026-11": 1}, 1, 2, 1, 1, {"sheet_sync.new_count": 2}))

    def test_reconcile_counts_ahead_only_when_it_explains_the_whole_difference(self):
        result = audit.audit_reconcile({"checked_at": "x", "counts": {"KHOP": 1, "LECH_TONG": 2}, "customers": [
            {"customer_id": 1, "customer": "Khách A", "status": "LECH_TONG", "reason": "WEB_AHEAD", "difference_vnd": "40", "web_ahead_vnd": "40"},
            {"customer_id": 2, "customer": "Khách B", "status": "LECH_TONG", "reason": "NO_EXACT_FIX", "difference_vnd": "-15", "web_ahead_vnd": "0"},
            {"customer_id": 3, "customer": "Khách C", "status": "KHOP", "reason": "FIXED"}]})
        self.assertEqual((result["ahead"], result["ahead_vnd"], result["unexplained_vnd"], [row["customer_id"] for row in result["not_matched"]]), ({1: 40}, 40, 15, [2]))
        self.assertEqual(audit.audit_reconcile(None)["ahead"], {})

    def test_operations_cover_every_event_kind_the_backend_writes(self):
        sql = (ROOT / "tools" / "v7_backend_functions.sql").read_text(encoding="utf-8")
        written = set(re.findall(r"INSERT INTO sokhach\.event\([^)]*\)\s*VALUES\s*\(\s*[A-Za-z_]+\s*,\s*'([a-z_]+)'", sql))
        known = {kind for kinds in audit.OPERATIONS.values() for kind in kinds} | audit.SYSTEM_KINDS
        self.assertGreater(len(written), 15)
        self.assertEqual(written - known, set())
        self.assertEqual(audit.MACHINE, v7_inbox.AUTO_ACTOR)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        web = self.root / "web"
        (web / "ledgers").mkdir(parents=True)
        (web / "activity").mkdir()
        self.write(web / "customers.json", {"customers": [A]})
        self.write(web / "ledgers" / "1.json", book(A, 100, [("2026-10", 100, 0)], legacy_rows=[old(11, "AAAU1111111", "2026-10", 100, day="2026-10-05")]))
        self.write(web / "activity" / "2026-11-05.json", {"day": "2026-11-05", "total": 0, "events": []})
        self.write(self.root / "prices.json", {"rows": [sheet(A, 10, "2026-10", "AAAU1111111", 100, day="2026-10-05")]})
        self.write(self.root / "receipts.json", {"rows": []})

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def run_cli(self, out, *extra, prices="prices.json"):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = audit.main(["--web-dir", str(self.root / "web"), "--prices", str(self.root / prices), "--receipts", str(self.root / "receipts.json"), "--out", str(out), *extra])
        return code, stream.getvalue()

    def test_clean_run_exits_zero_and_keeps_names_out_of_stdout(self):
        code, printed = self.run_cli(self.root / "out")
        self.assertEqual((code, json.loads(printed)["ok"], json.loads(printed)["row_statuses"]), (0, True, {"PRICE_UNCHANGED": 1}))
        self.assertNotIn("Khách A", printed)
        self.assertIn("Khách A", (self.root / "out" / "chi-tiet.json").read_text(encoding="utf-8"))
        self.assertIn("không còn mục tiền nào", (self.root / "out" / "bao-cao.txt").read_text(encoding="utf-8"))

    def test_unexplained_money_exits_one(self):
        self.write(self.root / "lech.json", {"rows": [sheet(A, 10, "2026-10", "AAAU1111111", 100, day="2026-10-05"), sheet(A, 11, "2026-10", "LOSU0000009", 9, day="2026-10-09")]})
        code, printed = self.run_cli(self.root / "out", prices="lech.json")
        self.assertEqual((code, json.loads(printed)["must_explain"]["row_items"], json.loads(printed)["must_explain"]["month_diffs"]), (1, 1, 1))

    def test_bad_input_and_unsafe_output_exit_two_without_writing(self):
        self.assertEqual(self.run_cli(ROOT / "khong-duoc-ghi-vao-repo")[0], 2)
        self.assertFalse((ROOT / "khong-duoc-ghi-vao-repo").exists())
        (self.root / "da-co").mkdir()
        self.assertEqual(self.run_cli(self.root / "da-co")[0], 2)
        self.assertEqual(self.run_cli(self.root / "out", "--xlsx", str(self.root / "so-goc.xlsx"))[0], 2)   # vừa xlsx vừa bản chụp
        self.assertEqual(self.run_cli(self.root / "out", "--tong-alias", "thiếu dấu bằng")[0], 2)
        self.assertFalse((self.root / "out").exists())


if __name__ == "__main__":
    unittest.main()
