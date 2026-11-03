"""Row-scoped keep decisions, API trust boundary, and unknown-response retry."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_api_sheet as api
from v7_api_validate import ApiError
from v7_price_queue import project_prices
from v7_sheet_task_keep import kept, price_identity, removed_identity


class SheetTaskKeepTests(unittest.TestCase):
    def setUp(self):
        self.row = {"container": "FAKE1", "date": "2026-11-01", "sheet_unit_price_vnd": 200,
                    "sheet_other_fee_vnd": None, "customer_tab": "FAKE", "source_row": 4}
        self.ledger = {"customer_id": 1, "version": 3, "today_month": "2026-11-01", "trips": [
            {"id": 2, "container": "FAKE1", "event_date": "2026-11-01", "month": "2026-11-01",
             "unit_price_vnd": "100", "other_fee_vnd": None, "status": "confirmed"}]}
        self.request = {"customer_id": 1, "expected_version": 3, "idempotency_key": "keep-test",
                        "task_kind": "price", "target_kind": "trip", "target_id": 2,
                        "source_fingerprint": price_identity(self.row)}
        self.event = {"id": 5, "kind": "sheet_conflict_resolved", "after": {
            "field": "task_price", "target": {"kind": "trip", "id": 2},
            "sheet_value": self.request["source_fingerprint"], "target_value": {"unit_price_vnd": "100", "other_fee_vnd": None},
            "decision": "keep_web", "request_key": "keep-test"}}

    def test_projection_is_row_scoped_and_exact(self):
        self.ledger["events"] = [self.event]
        snapshot = {"sha256": "a" * 64, "rows": [self.row]}
        customers = [{"id": 1, "name": "FAKE"}]
        self.assertEqual(project_prices(snapshot, self.ledger, customers)["review_count"], 0)
        snapshot["sha256"] = "b" * 64
        self.row["source_row"] = 40
        snapshot["rows"].append({**self.row, "container": "UNRELATED"})
        self.assertEqual(project_prices(snapshot, self.ledger, customers)["review_count"], 0)
        self.row["sheet_other_fee_vnd"] = 0
        self.assertEqual(project_prices(snapshot, self.ledger, customers)["review_count"], 1)
        self.row["sheet_other_fee_vnd"] = None
        self.ledger["trips"][0]["unit_price_vnd"] = "110"
        self.assertEqual(project_prices(snapshot, self.ledger, customers)["review_count"], 1)

    def test_latest_event_wins_independent_of_order(self):
        newer = {**self.event, "id": 9, "after": {**self.event["after"], "sheet_value": "b" * 64}}
        self.ledger["events"] = [newer, self.event]
        self.assertFalse(kept(self.ledger, "price", "trip", 2, self.request["source_fingerprint"], self.event["after"]["target_value"]))

    def test_removed_related_rows_only(self):
        trip = self.ledger["trips"][0]
        queue = {"items": [{"container": "OTHER", "booking": "A"}]}
        source = removed_identity(queue, self.ledger, trip)
        queue["items"][0]["booking"] = "B"
        self.assertEqual(source, removed_identity(queue, self.ledger, trip))
        queue["items"].append({"container": "FAKE1", "booking": "NEW"})
        self.assertNotEqual(source, removed_identity(queue, self.ledger, trip))

    def test_api_validates_source_and_replays_original_after_unknown(self):
        runner = Mock()
        runner.run.side_effect = [self.ledger, {"kept": True, "version": 4}]
        row = {**self.request, "status": "CONFLICT", "web_unit_price_vnd": "100", "web_other_fee_vnd": None}
        with patch.object(api, "price_projection", return_value={"review": [row]}):
            status, result = api.keep_sheet_task(json.dumps(self.request).encode(), runner, "actor")
        self.assertEqual((status, result["version"]), (200, 4))
        original = runner.run.call_args
        self.ledger.update(version=4, events=[self.event])
        runner.run.side_effect = [self.ledger, result]
        with patch.object(api, "price_projection", side_effect=AssertionError("retry must not reproject")):
            api.keep_sheet_task(json.dumps(self.request).encode(), runner, "actor")
        self.assertEqual(runner.run.call_args, original)

    def test_bad_or_stale_input_never_writes(self):
        for fields in ({"target_id": True}, {"task_kind": None}, {"source_fingerprint": "bad"}, {"expected_version": -1}, {"extra": 1}):
            runner = Mock()
            with self.subTest(fields=fields), self.assertRaises(ApiError):
                api.keep_sheet_task(json.dumps({**self.request, **fields}).encode(), runner, "actor")
            runner.run.assert_not_called()
        runner = Mock()
        runner.run.return_value = self.ledger
        with patch.object(api, "price_projection", return_value={"review": []}), self.assertRaises(ApiError):
            api.keep_sheet_task(json.dumps(self.request).encode(), runner, "actor")
        self.assertEqual(runner.run.call_count, 1)

    def test_apply_price_uses_server_values_and_retries_original(self):
        runner = Mock()
        result = {"written": 1, "version": 6}
        runner.run.side_effect = [self.ledger, result]
        row = {**self.request, "status": "CONFLICT", "web_unit_price_vnd": "100", "web_other_fee_vnd": None,
               "sheet_unit_price_vnd": "200", "sheet_other_fee_vnd": None}
        with patch.object(api, "price_projection", return_value={"review": [row]}):
            api.apply_sheet_price(json.dumps(self.request).encode(), runner, "actor")
        original = runner.run.call_args
        self.assertEqual(original.args[0], "apply_sheet_price")
        self.assertEqual(original.args[1]["sheet_price"], {"unit_price_vnd": "200", "other_fee_vnd": None})
        self.event["after"].update(decision="use_sheet", requested_price=original.args[1]["sheet_price"], web_value=original.args[1]["web_value"])
        self.ledger.update(version=6, events=[self.event])
        runner.run.side_effect = [self.ledger, result]
        with patch.object(api, "price_projection", side_effect=AssertionError("retry reprojected")):
            api.apply_sheet_price(json.dumps(self.request).encode(), runner, "actor")
        self.assertEqual(runner.run.call_args, original)

    def test_sql_copies_match(self):
        from test_v7_fee_sql_sync import FUNCTIONS, ROOT, definition
        migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-11-02-v7-giu-viec-sheet.sql").read_text(encoding="utf-8")
        self.assertEqual(definition(migration, "FUNCTION", "keep_sheet_task"),
                         definition(FUNCTIONS.read_text(encoding="utf-8"), "FUNCTION", "keep_sheet_task"))
        migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-11-02-v7-lay-gia-sheet.sql").read_text(encoding="utf-8")
        self.assertEqual(definition(migration, "FUNCTION", "apply_sheet_price"),
                         definition(FUNCTIONS.read_text(encoding="utf-8"), "FUNCTION", "apply_sheet_price"))
        migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-11-02-v7-gan-mat-hang.sql").read_text(encoding="utf-8")
        self.assertEqual(definition(migration, "FUNCTION", "set_customer_commodity"),
                         definition(FUNCTIONS.read_text(encoding="utf-8"), "FUNCTION", "set_customer_commodity"))

    def test_commodity_request_only_accepts_approved_choices(self):
        from v7_api_validate import validate
        request = {"customer_id": 1, "expected_version": 0, "idempotency_key": "commodity", "commodity_name": "Dừa"}
        self.assertEqual(validate("/api/v7/customers/commodity", json.dumps(request).encode())[0], "set_customer_commodity")
        for value in (None, "", "UNKNOWN", [], True):
            with self.subTest(value=value), self.assertRaises(ApiError):
                validate("/api/v7/customers/commodity", json.dumps({**request, "commodity_name": value}).encode())

    def test_assignment_validates_candidate_and_retries_saved_source(self):
        request = {"customer_id": 1, "expected_version": 3, "idempotency_key": "assign", "target_customer_id": 9,
                   "target_version": 4, "source_fingerprint": "a" * 64}
        row = {"source_row": 41, "container": "FAKE", "event_date": "2026-01-02", "sync_state": "NEW",
               "source_fingerprint": "a" * 64, "candidate_books": [{"id": 9}]}
        runner = Mock()
        runner.run.side_effect = [self.ledger, {"approved": 1}]
        with patch.object(api, "sheet_projection", return_value={"items": [row]}):
            api.assign_sheet_trip(json.dumps(request).encode(), runner, "actor")
        original = runner.run.call_args
        self.assertEqual(original.args[0], "assign_sheet_trip")
        self.assertEqual(original.args[1]["source_row"]["container"], "FAKE")
        self.ledger.update(version=5, events=[{"kind": "sheet_conflict_resolved", "after": {
            "field": "task_assignment", "request_key": "assign", "arguments": original.args[1]}}])
        runner.run.side_effect = [self.ledger, {"approved": 1}]
        with patch.object(api, "sheet_projection", side_effect=AssertionError("retry reprojected")):
            api.assign_sheet_trip(json.dumps(request).encode(), runner, "actor")
        self.assertEqual(runner.run.call_args, original)
        self.ledger.update(version=3, events=[])
        runner.run.side_effect = None
        runner.run.return_value = self.ledger
        with patch.object(api, "sheet_projection", return_value={"items": [row]}), self.assertRaises(ApiError):
            api.assign_sheet_trip(json.dumps({**request, "target_customer_id": 99}).encode(), runner, "actor")
