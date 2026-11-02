"""Selected Sheet price conflicts: validation and fake write path. No real DB or Sheet."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_api_sheet as sheet  # noqa: E402
from test_v7_price_queue import (  # noqa: E402
    CUSTOMERS,
    SNAPSHOT,
    Runner,
    ledger,
    legacy_row,
    row,
    trip,
)
from v7_price_queue import project_prices  # noqa: E402

BODY = {"customer_id": 7, "expected_version": 3, "snapshot_sha256": "a" * 64,
        "idempotency_key": "selected-batch", "conflicts": [
            {"target_kind": "trip", "target_id": 11, "source_row": 5},
            {"target_kind": "legacy", "target_id": 21, "source_row": 6}]}
PROJECTION = {"snapshot_sha256": "a" * 64, "review": [
    {"status": "CONFLICT", "batchable": True, "target_kind": "trip", "target_id": 11, "source_row": 5,
     "sheet_unit_price_vnd": "52000000", "sheet_other_fee_vnd": None, "web_unit_price_vnd": "50000000",
     "web_other_fee_vnd": None},
    {"status": "CONFLICT", "batchable": True, "target_kind": "legacy", "target_id": 21, "source_row": 6,
     "sheet_unit_price_vnd": "95000000", "sheet_other_fee_vnd": "3000000", "web_unit_price_vnd": "90000000",
     "web_other_fee_vnd": "3000000"}]}


class ConflictBatchTest(unittest.TestCase):
    def approve(self, runner, body=BODY, projection=PROJECTION):
        with patch.object(sheet, "price_projection", return_value=projection):
            return sheet.approve_price_conflicts(json.dumps(body).encode(), runner, "fake-actor")

    def test_only_selected_conflicts_write_at_server_prices(self):
        runner = Runner()
        status, result = self.approve(runner)
        self.assertEqual((status, result["written"], result["complete"]), (200, 2, True))
        writes = [(name, payload) for name, payload, _ in runner.calls if name != "get_ledger"]
        self.assertEqual([name for name, _ in writes], ["edit_trip_price", "edit_legacy_trip"])
        self.assertEqual(writes[0][1]["unit_price_vnd"], "52000000")
        self.assertEqual(writes[1][1]["value"], "95000000")
        self.assertEqual([payload["expected_version"] for _, payload in writes], [3, 4])

    def test_invalid_stale_and_unbatchable_selection_write_nothing(self):
        cases = [BODY | {"conflicts": []}, BODY | {"conflicts": BODY["conflicts"] * 2},
                 BODY | {"conflicts": [{"target_kind": "trip", "target_id": 11, "source_row": 999}]},
                 BODY | {"snapshot_sha256": "b" * 64}, BODY | {"expected_version": 2}]
        for body in cases:
            runner = Runner()
            with self.subTest(body=body), self.assertRaises(sheet.ApiError):
                self.approve(runner, body)
            self.assertEqual([name for name, _, _ in runner.calls if name != "get_ledger"], [])
        runner = Runner()
        with self.assertRaises(sheet.ApiError):
            self.approve(runner, projection=PROJECTION | {"review": [PROJECTION["review"][0] | {"batchable": False}]})
        self.assertEqual([name for name, _, _ in runner.calls if name != "get_ledger"], [])

    def test_partial_result_reports_remaining(self):
        status, result = self.approve(Runner(fail_at=2))
        self.assertEqual((status, result["written"], result["remaining"], result["complete"]), (200, 1, 1, False))

    def test_legacy_fee_can_be_cleared_without_rewriting_same_price(self):
        item = PROJECTION["review"][1] | {"sheet_unit_price_vnd": "90000000", "sheet_other_fee_vnd": None}
        runner = Runner()
        self.approve(runner, body=BODY | {"conflicts": [BODY["conflicts"][1]]},
                     projection=PROJECTION | {"review": [item]})
        writes = [(name, payload) for name, payload, _ in runner.calls if name != "get_ledger"]
        self.assertEqual([(name, payload["field"], payload["value"]) for name, payload in writes],
                         [("edit_legacy_trip", "other_fee_vnd", "")])

    def test_projection_excludes_locked_typed_and_unexplained_legacy_totals(self):
        rows = [row(price=52000000), row(source_row=6, container="FAKEU0000002", date="2026-10-04",
                                     price=95000000, fee=3000000, total=98000000)]
        old = legacy_row() | {"current": legacy_row()["current"] | {
            "unit_price_vnd": "90000000", "other_fee_vnd": "3000000", "counted_vnd": "93000000"}}
        book = ledger(trips=[trip(price="50000000")], legacy=[old])
        projected = project_prices(SNAPSHOT | {"rows": rows, "row_count": 2}, book, CUSTOMERS)
        self.assertEqual([item["batchable"] for item in projected["review"]], [True, True])
        mismatched = project_prices(SNAPSHOT | {"rows": [rows[1] | {"sheet_total_vnd": 99000000}], "row_count": 1},
                                    book, CUSTOMERS)
        self.assertFalse(mismatched["review"][0]["batchable"])
        bad_trip_total = project_prices(SNAPSHOT | {"rows": [rows[0] | {"sheet_total_vnd": 53000000}],
                                                    "row_count": 1}, book, CUSTOMERS)
        self.assertFalse(bad_trip_total["review"][0]["batchable"])
        typed = project_prices(SNAPSHOT | {"rows": [rows[0]], "row_count": 1},
                               ledger(trips=[trip(price="50000000") | {"has_typed_fee": True}]), CUSTOMERS)
        self.assertFalse(typed["review"][0]["batchable"])
        locked = ledger(trips=[trip(price="50000000")], legacy=[old])
        locked["month_locks"][0]["locked"] = True
        self.assertFalse(project_prices(SNAPSHOT | {"rows": [rows[0]], "row_count": 1},
                                        locked, CUSTOMERS)["review"][0]["batchable"])


if __name__ == "__main__":
    unittest.main()
