"""Chuyến bộ mới vào sổ theo tab khách trên Sheet (NGUON-CHUYEN-01 GĐ3, specs/v7-chuyen-theo-nguon.md). Dữ liệu giả."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_api_sheet
from v7_road_queue import NO_WAREHOUSE, NOTE, build_road_queue, project_road

SHA = "a" * 64
CUSTOMERS = [{"id": 7, "name": "DUONG BO KHACH A 324", "status": "active"},
             {"id": 8, "name": "KHACH B", "status": "active", "aliases": ["KHACH B CU"]},
             {"id": 9, "name": "KHACH C", "status": "draft"}]


def road_row(line, container, date, status="READY", gate="CHIMA", plate="99Z-00001", warehouse="", owner="KHÁCH KHO 336"):
    return {"source_row": line, "container": container, "event_date": date, "source_date": date, "plate": plate,
            "gate": gate, "warehouse": warehouse, "shipper": "", "owner": owner, "status": status}


def tab_row(tab, row, container, date, month="2026-10"):
    return {"customer_tab": tab, "source_row": row, "debt_month": month, "container": container, "date": date,
            "sheet_unit_price_vnd": 11000000, "sheet_other_fee_vnd": 880000, "sheet_total_vnd": 11880000}


def ledger(trips=(), legacy=(), customer_id=7):
    return {"customer_id": customer_id, "today_month": "2026-11-01", "month_locks": [], "trips": list(trips),
            "legacy_rows": list(legacy)}


class BuildRoadQueueTests(unittest.TestCase):
    def build(self, road_rows, tab_rows):
        return build_road_queue({"sha256": SHA, "rows": road_rows}, {"rows": tab_rows}, CUSTOMERS)

    def test_book_comes_from_the_one_tab_holding_the_container_not_from_the_owner_column(self):
        queue = self.build([road_row(12, "FAKU1000001", "2026-10-02", warehouse="LÂM ĐỒNG")],
                           [tab_row("DUONG BO KHACH A 324", 382, "FAKU1000001", "2026-10-03"),
                            tab_row("KHACH B", 40, "FAKU1000001", "2026-08-31", month="2026-08")])   # container dùng lại
        self.assertEqual(queue["stats"], {"BOOK": 1})
        item = queue["items"][0]
        self.assertEqual((item["customer_id"], item["customer_tab"], item["tab_row"], item["tab_debt_month"]),
                         (7, "DUONG BO KHACH A 324", 382, "2026-10"))
        # Ngày theo CONT_BO; xe, cửa khẩu, kho theo CONT_BO; CHỦ HÀNG chỉ để hiện.
        self.assertEqual((item["event_date"], item["carrier"], item["destination"], item["origin"], item["owner"]),
                         ("2026-10-02", "99Z-00001", "CHIMA", "LÂM ĐỒNG", "KHÁCH KHO 336"))
        self.assertEqual((item["src"], item["note"], item["booking"]), (f"sheet:{SHA}:12", NOTE, ""))

    def test_alias_tab_and_blank_warehouse(self):
        queue = self.build([road_row(3, "FAKU1000002", "2026-10-24")], [tab_row("KHACH B CU", 108, "FAKU1000002", None)])
        self.assertEqual((queue["items"][0]["customer_id"], queue["items"][0]["origin"]), (8, NO_WAREHOUSE))

    def test_rows_that_cannot_be_placed_are_counted_never_guessed(self):
        queue = self.build([
            road_row(2, "NOTAB000001", "2026-10-05"),                         # chưa có ở tab nào: chờ Sheet
            road_row(3, "TWOTAB00001", "2026-10-05"),                         # hai tab
            road_row(4, "DRAFT000001", "2026-10-05"),                         # tab của sổ chưa hoạt động
            road_row(5, "OLDROW00001", "2026-09-30"),                         # trước tháng nạp V7
            road_row(6, "BADROW00001", "2026-10-05", status="INVALID"),
            road_row(7, "SHARED00001", "2026-10-05"), road_row(8, "SHARED00001", "2026-10-07"),   # hai chuyến, một dòng tab
        ], [tab_row("DUONG BO KHACH A 324", 1, "TWOTAB00001", "2026-10-05"), tab_row("KHACH B", 2, "TWOTAB00001", "2026-10-06"),
            tab_row("KHACH C", 3, "DRAFT000001", "2026-10-05"), tab_row("KHACH B", 4, "OLDROW00001", "2026-09-30"),
            tab_row("KHACH B", 5, "BADROW00001", "2026-10-05"), tab_row("KHACH B", 6, "SHARED00001", "2026-10-06")])
        self.assertEqual(queue["items"], [])
        self.assertEqual(queue["stats"], {"NO_TAB": 1, "AMBIGUOUS_TAB": 1, "NO_BOOK": 1, "BOOK": 0, "AMBIGUOUS_SOURCE": 2})


class ProjectRoadTests(unittest.TestCase):
    def queue(self, *items):
        return build_road_queue({"sha256": SHA, "rows": [road_row(n, c, d) for n, c, d, _ in items]},
                                {"rows": [tab_row("DUONG BO KHACH A 324", 100 + n, c, d, month=m) for n, c, d, m in items]},
                                CUSTOMERS)

    def test_new_unless_already_in_the_book_within_three_days(self):
        queue = self.queue((2, "NEWU0000001", "2026-10-02", "2026-10"), (3, "WEBU0000001", "2026-10-10", "2026-10"),
                           (4, "LEGU0000001", "2026-10-12", "2026-10"), (5, "REUS0000001", "2026-10-20", "2026-10"))
        book = ledger(trips=[{"id": 1, "container": "WEBU0000001", "event_date": "2026-10-12", "month": "2026-10-01",
                              "status": "pending_review"},
                             {"id": 2, "container": "REUS0000001", "event_date": "2026-08-15", "month": "2026-08-01"}],
                      legacy=[{"id": 3, "kind": "trip", "month": "2026-10-01",
                               "current": {"container": "LEGU0000001", "event_date": None, "month": "2026-10-01"}}])
        result = project_road(queue, book)
        # Đã có (kể cả chờ kiểm, dòng sổ gốc không ngày cùng tháng) thì không hiện; container dùng lại xa ngày là chuyến mới.
        self.assertEqual([(r["container"], r["sync_state"]) for r in result["items"]],
                         [("NEWU0000001", "NEW"), ("REUS0000001", "NEW")])
        self.assertEqual((result["new_count"], result["conflict_count"], result["snapshot_sha256"]), (2, 0, SHA))
        self.assertEqual(project_road(queue, ledger(customer_id=8))["items"], [])

    def test_other_books_and_month_mismatch_go_to_people(self):
        queue = self.queue((2, "OTHC0000001", "2026-10-02", "2026-10"), (3, "OTHL0000001", "2026-10-03", "2026-10"),
                           (4, "FAML0000001", "2026-10-04", "2026-10"), (5, "MONU0000001", "2026-10-31", "2026-11"))
        legacy = [{"customer_id": 8, "container": "OTHL0000001", "event_date": "2026-10-04", "debt_month": "2026-10-01"},
                  {"customer_id": 9, "container": "FAML0000001", "event_date": None, "debt_month": "2026-10-01"}]
        result = project_road(queue, ledger(), {"OTHC0000001"}, legacy, family_ids={9})
        self.assertEqual([(r["container"], r["sync_state"], r["sync_reason"]) for r in result["items"]],
                         [("OTHC0000001", "CONFLICT", "OTHER_CUSTOMER"), ("OTHL0000001", "CONFLICT", "OTHER_BOOK_LEGACY"),
                          ("MONU0000001", "CONFLICT", "MONTH_DIFFERS")])
        self.assertTrue(all(r["message"] for r in result["items"]))


class RoadProjectionApiTests(unittest.TestCase):
    """`road_projection`: không có road.json thì không có việc; có thì chặn sổ khác bằng đúng hàm của chuyến biển."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        folder = Path(self.dir.name)
        self.road, self.prices = folder / "road.json", folder / "prices.json"
        rows = [road_row(2, "FAKU1000001", "2026-10-02"), road_row(3, "FAKU1000003", "2026-10-02")]
        self.road.write_text(json.dumps({"sha256": SHA, "row_count": 2, "rows": rows}), encoding="utf-8")
        tabs = [tab_row("DUONG BO KHACH A 324", 382, "FAKU1000001", "2026-10-02"),
                tab_row("DUONG BO KHACH A 324", 383, "FAKU1000003", "2026-10-02")]
        self.prices.write_text(json.dumps({"sha256": "b" * 64, "row_count": 2, "rows": tabs}), encoding="utf-8")
        self.calls = []
        test = self

        class Runner:
            def run(self, function, payload, actor):
                test.calls.append(function)
                if function == "list_customers":
                    return {"customers": CUSTOMERS}
                if function == "list_sheet_trip_refs":
                    return {"items": [{"customer_id": 8, "container": "FAKU1000003"}]}
                if function == "get_ledger":
                    return ledger(trips=[{"id": 5, "container": "FAKU1000003", "event_date": "2026-10-03"}], customer_id=8)
                if function == "list_legacy_trip_refs":
                    return {"items": []}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_is_no_work_and_present_file_blocks_other_customers(self):
        with patch.object(v7_api_sheet, "ROAD_SNAPSHOT_PATH", str(Path(self.dir.name) / "none.json")):
            empty = v7_api_sheet.road_projection(self.runner, ledger(), "t")
        self.assertEqual((empty["items"], empty.get("source_missing"), self.calls), ([], True, []))
        with patch.object(v7_api_sheet, "ROAD_SNAPSHOT_PATH", str(self.road)), \
                patch.object(v7_api_sheet, "PRICE_SNAPSHOT_PATH", str(self.prices)):
            result = v7_api_sheet.road_projection(self.runner, ledger(), "t")
        self.assertEqual([(r["container"], r["sync_state"], r["sync_reason"]) for r in result["items"]],
                         [("FAKU1000001", "NEW", ""), ("FAKU1000003", "CONFLICT", "OTHER_CUSTOMER")])

    def test_paste_keeps_the_road_source_and_note(self):
        pasted = []

        class Runner:
            def run(self, function, payload, actor):
                pasted.append(payload)
                return {"trip_ids": [41], "pending_review": []}
        item = {"source_row": 2, "container": "FAKU1000001", "event_date": "2026-10-02", "carrier": "99Z-00001",
                "origin": NO_WAREHOUSE, "destination": "CHIMA", "shipper": None, "booking": "",
                "src": f"sheet:{SHA}:2", "note": NOTE}
        result = v7_api_sheet.paste_sheet_rows(Runner(), 7, 3, SHA, "k", [item], "may")
        trip = pasted[0]["trips"][0]
        self.assertEqual((trip["src"], trip["note"], trip["from"], trip["to"], trip["date"], trip["unitPriceVnd"]),
                         (f"sheet:{SHA}:2", NOTE, NO_WAREHOUSE, "CHIMA", "02/10/2026", None))
        self.assertEqual((pasted[0]["debt_month"], result["pasted"]), ("2026-10-01", [{"source_row": 2, "trip_id": 41}]))


if __name__ == "__main__":
    unittest.main()
