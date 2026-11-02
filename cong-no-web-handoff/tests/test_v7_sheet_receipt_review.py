"""A supplied receipt date must survive refresh and cannot cause a second write."""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_api_sheet as api
from v7_api_validate import ApiError
from v7_receipt_queue import project_receipts, review_reference


class ReceiptReviewTests(unittest.TestCase):
    def test_duplicates_row_moves_refresh_and_void(self):
        row = {"customer_tab": "FAKE", "source_row": 4, "debt_month": "2026-01-01", "amount_vnd": 100, "note": "CK"}
        snapshot = {"sha256": "a" * 64, "rows": [row, {**row, "source_row": 5}]}
        ledger = {"customer_id": 1, "receipts": []}
        customers = [{"id": 1, "name": "FAKE"}]
        today = dt.date(2026, 11, 2)
        before = project_receipts(snapshot, ledger, customers, today)
        sources = [r["source_fingerprint"] for r in before["review"]]
        self.assertEqual(len(set(sources)), 2)
        ledger["receipts"] = [{"id": 7, "date": "2026-01-01", "amount_vnd": "100", "reference": review_reference(sources[0]) + "CK"}]
        snapshot["sha256"] = "b" * 64
        row["source_row"] = 3
        self.assertEqual(project_receipts(snapshot, ledger, customers, today)["review_count"], 1)
        ledger["receipts"][0]["voided_by_event"] = 9
        self.assertEqual(project_receipts(snapshot, ledger, customers, today)["review_count"], 2)

    def test_api_server_amount_retry_and_stale_source(self):
        source = "a" * 64
        request = {"customer_id": 1, "expected_version": 2, "idempotency_key": "review-test", "source_fingerprint": source, "date": "2026-01-02"}
        ledger = {"version": 2, "receipts": []}
        runner = Mock()
        runner.run.side_effect = [ledger, {"receipt_id": 7, "version": 3}]
        with patch.object(api, "receipt_projection", return_value={"review": [{"status": "NO_DATE", "source_fingerprint": source, "amount_vnd": "100", "note": "CK"}]}):
            _, result = api.review_sheet_receipt(json.dumps(request).encode(), runner, "actor")
        self.assertEqual(runner.run.call_args.args[1]["amount_vnd"], "100")
        self.assertEqual(result["receipt_id"], 7)
        ledger.update(version=3, receipts=[{"id": 7, "date": "2026-01-02", "reference": review_reference(source), "amount_vnd": "100"}])
        runner.run.side_effect = None
        runner.run.return_value = ledger
        runner.reset_mock()
        with patch.object(api, "receipt_projection", side_effect=AssertionError("retry reprojected")):
            self.assertEqual(api.review_sheet_receipt(json.dumps(request).encode(), runner, "actor")[1]["receipt_id"], 7)
        self.assertEqual(runner.run.call_count, 1)
        ledger.update(version=2, receipts=[])
        with patch.object(api, "receipt_projection", return_value={"review": []}), self.assertRaises(ApiError):
            api.review_sheet_receipt(json.dumps(request).encode(), runner, "actor")

    def test_untrusted_date_and_extra_amount_rejected_before_reads(self):
        request = {"customer_id": 1, "expected_version": 2, "idempotency_key": "review-test", "source_fingerprint": "a" * 64, "date": "2026-01-02"}
        for fields in ({"amount_vnd": "1"}, {"date": "2026-02-30"}, {"date": "2999-01-01"}, {"customer_id": True}):
            runner = Mock()
            with self.subTest(fields=fields), self.assertRaises(ApiError):
                api.review_sheet_receipt(json.dumps({**request, **fields}).encode(), runner, "actor")
            runner.run.assert_not_called()
