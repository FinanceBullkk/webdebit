"""Receipt queue: Sheet receipts for one ledger, batch write through record_receipt. Fake data only."""
import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_api_sheet  # noqa: E402
import v7_ledger_api as api  # noqa: E402
import v7_price_snapshot as snapshot_tool  # noqa: E402
from test_v7_load_real_copy import fixture  # noqa: E402
from v7_receipt_queue import (  # noqa: E402
    classify,
    load_receipt_snapshot,
    pay_date,
    project_receipts,
    reference,
    rows_from_scan,
)

TODAY = dt.date(2026, 10, 30)
CUSTOMERS = [{"id": 7, "name": "KHACH A"}, {"id": 8, "name": "KHACH B"}]


def row(month="2026-09", source_row=40, amount=50000000, note="23/10/2026 tt", tab="KHACH A"):
    return {"customer_tab": tab, "source_row": source_row, "debt_month": month, "amount_vnd": amount, "note": note}


def legacy(row_id=21, month="2026-09-01", amount=50000000, note="23/10/2026 tt", deleted=False):
    return {"id": row_id, "kind": "receipt", "month": month, "source_total_vnd": str(amount),
            "current": {"deleted": True} if deleted else None, "display": {"raw_date": note}}


def receipt(date="2026-10-23", amount=50000000, voided=False):
    return {"id": 1, "date": date, "amount_vnd": str(amount), "voided_by_event": 99 if voided else None}


def ledger(legacy_rows=(), receipts=(), customer_id=7, version=3):
    return {"customer_id": customer_id, "version": version, "status": "active",
            "legacy_rows": [{"id": 1, "kind": "trip", "month": "2026-09-01"}, *legacy_rows], "receipts": list(receipts)}


def statuses(rows, led):
    return [r["status"] for r in classify(rows, led, TODAY)]


class PayDateTest(unittest.TestCase):
    def test_reads_day_first_iso_and_serial(self):
        self.assertEqual(pay_date("23/10/2026 tt"), dt.date(2026, 10, 23))
        self.assertEqual(pay_date("1.6.2026 can tru"), dt.date(2026, 6, 1))
        self.assertEqual(pay_date("2026-10-21"), dt.date(2026, 10, 21))
        self.assertEqual(pay_date("46316.0"), dt.date(2026, 10, 21))
        self.assertEqual(pay_date("46315"), dt.date(2026, 10, 20))

    def test_anything_else_has_no_date(self):
        for note in ("da tt", "", None, "138/2026 tt", "31/02/2026 tt", "tt 23/10/2026", "123/10/2026"):
            with self.subTest(note=note):
                self.assertIsNone(pay_date(note))


class ClassifyTest(unittest.TestCase):
    def test_original_book_row_is_already_on_web(self):
        self.assertEqual(statuses([row(note=" 23/10/2026  TT ")], ledger([legacy()])), ["MATCHED_LEGACY"])

    def test_rounded_dong_matches_after_exact_ones(self):
        rows = [row(source_row=40, amount=12345666), row(source_row=41, amount=12345667)]
        led = ledger([legacy(row_id=21, amount=12345667), legacy(row_id=22, amount=12345666)])
        self.assertEqual(statuses(rows, led), ["MATCHED_LEGACY", "MATCHED_LEGACY"])
        self.assertEqual(statuses([row(amount=12345665)], ledger([legacy(amount=12345667)])), ["SHEET_EDITED"])

    def test_date_cell_serial_matches_in_both_forms(self):
        # The cutover read the .xlsx download ("45870.0"); the runner reads the Sheets API (45870).
        self.assertEqual(statuses([row(month="2025-08", note="45870")], ledger([legacy(month="2025-08-01", note="45870.0")])),
                         ["MATCHED_LEGACY"])
        self.assertEqual(statuses([row(month="2025-08", note="45870.0")], ledger([legacy(month="2025-08-01", note="45870")])),
                         ["MATCHED_LEGACY"])

    def test_two_equal_sheet_rows_need_two_book_rows(self):
        rows = [row(source_row=40), row(source_row=41)]
        self.assertEqual(statuses(rows, ledger([legacy()])), ["MATCHED_LEGACY", "READY"])

    def test_web_receipt_matches_exact_then_near_date(self):
        self.assertEqual(statuses([row()], ledger(receipts=[receipt()])), ["MATCHED_WEB"])
        self.assertEqual(statuses([row()], ledger(receipts=[receipt(date="2026-10-25")])), ["MATCHED_WEB"])
        self.assertEqual(statuses([row()], ledger(receipts=[receipt(date="2026-10-27")])), ["READY"])
        self.assertEqual(statuses([row()], ledger(receipts=[receipt(voided=True)])), ["READY"])
        self.assertEqual(statuses([row()], ledger(receipts=[receipt(amount=50000001)])), ["READY"])

    def test_near_match_never_takes_an_exact_one(self):
        rows = [row(source_row=40, note="22/10/2026 tt"), row(source_row=41, note="23/10/2026 tt")]
        web = [receipt(date="2026-10-23")]
        self.assertEqual(statuses(rows, ledger(receipts=web)), ["READY", "MATCHED_WEB"])

    def test_backdated_receipt_missing_from_the_cutover_is_ready(self):
        self.assertEqual(statuses([row(month="2026-08", note="20/10/2026 tt")], ledger()), ["READY"])

    def test_review_cases(self):
        self.assertEqual(statuses([row(note="da tt")], ledger()), ["NO_DATE"])
        self.assertEqual(statuses([row(note="31/10/2026 tt")], ledger()), ["FUTURE_DATE"])
        self.assertEqual(statuses([row()], ledger([legacy(deleted=True)])), ["WEB_DELETED"])

    def test_edited_old_receipt_blocks_its_month_only(self):
        rows = [row(amount=47000000, note="14/10/2026 tt"), row(month="2026-10", source_row=90, amount=1000000)]
        result = classify(rows, ledger([legacy(row_id=31, amount=48000000, note="14/10/2026 tt")]), TODAY)
        self.assertEqual([r["status"] for r in result], ["SHEET_EDITED", "READY"])
        self.assertEqual(result[0]["web_legacy"], [{"id": 31, "amount_vnd": "48000000"}])


SNAPSHOT = {"sha256": "a" * 64, "rows": [row(), row(tab="KHACH B", source_row=7), row(note="da tt", source_row=50)], "row_count": 3}


class ProjectionTest(unittest.TestCase):
    def test_rows_of_this_customer_only_money_as_strings(self):
        result = project_receipts(SNAPSHOT, ledger(), CUSTOMERS, TODAY)
        self.assertEqual((result["ready_count"], result["review_count"]), (1, 1))
        self.assertEqual(result["ready"][0] | {}, {"customer_tab": "KHACH A", "source_row": 40, "debt_month": "2026-09",
                                                   "amount_vnd": "50000000", "note": "23/10/2026 tt",
                                                   "date": "2026-10-23", "status": "READY"})
        self.assertEqual(result["review"][0]["status"], "NO_DATE")

    def test_tab_with_structural_issue_is_left_out(self):
        scan = {"KHACH A": {"issues": {}, "blocks": {"2026-09": {"records": [
                    {"kind": "receipt", "row": 9, "month": "2026-09", "amount": 5, "raw_date": "1/10/2026"},
                    {"kind": "trip", "row": 10, "month": "2026-09", "amount": 7, "raw_date": ""},
                    {"kind": "receipt", "row": 11, "month": "2026-09", "amount": None, "raw_date": "x"}]}},
                                    "records": [{"kind": "receipt", "row": 30, "month": "2026-09", "amount": 5, "raw_date": "1/10/2026"}]},
                "KHACH B": {"issues": {"SOURCE_LAYOUT_UNSUPPORTED": 1}, "blocks": {"2026-09": {"records": [
                    {"kind": "receipt", "row": 3, "month": "2026-09", "amount": 5, "raw_date": "1/10/2026"}]}}}}
        self.assertEqual(rows_from_scan(scan), [{"customer_tab": "KHACH A", "source_row": 9, "debt_month": "2026-09",
                                                 "amount_vnd": 5, "note": "1/10/2026"}])

    def test_snapshot_must_be_whole(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "receipts.json"
            for content in ('{"rows":[],"row_count":0}', '{"rows":[{}],"row_count":0,"sha256":"' + "a" * 64 + '"}', "x"):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValueError):
                    load_receipt_snapshot(path)

    def test_runner_writes_receipts_beside_prices(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            output = root / "out" / "prices.json"
            with patch("sys.stdout"):
                self.assertEqual(snapshot_tool.main(["--xlsx", str(root / "source-google-export.xlsx"), "--output", str(output)]), 0)
            prices, receipts = snapshot_tool.build_all(root / "source-google-export.xlsx")
            self.assertEqual(load_receipt_snapshot(output.with_name("receipts.json"))["sha256"], receipts["sha256"])
            self.assertEqual(snapshot_tool.build(root / "source-google-export.xlsx")["sha256"], prices["sha256"])

    def test_reference_names_the_sheet(self):
        self.assertEqual(reference("23/10/2026 tt"), "Sheet: 23/10/2026 tt")
        self.assertEqual(reference(""), "Sheet")
        self.assertEqual(len(reference("x" * 900)), 500)


class Runner:
    def __init__(self, fail_at=None):
        self.calls, self.version, self.fail_at, self.writes = [], 3, fail_at, 0

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "get_ledger":
            return {"customer_id": 7, "version": self.version, "status": "active"}
        self.writes += 1
        if self.writes == self.fail_at:
            raise api.ApiError(409, "INVALID_RECEIPT", "x")
        self.version += 1
        return {"version": self.version}


READY = {"snapshot_sha256": "a" * 64, "ready": [
    {"customer_tab": "KHACH A", "source_row": 40, "amount_vnd": "50000000", "note": "23/10/2026 tt", "date": "2026-10-23"},
    {"customer_tab": "KHACH A", "source_row": 41, "amount_vnd": "1000", "note": "46316", "date": "2026-10-21"}]}
BODY = {"customer_id": 7, "expected_version": 3, "snapshot_sha256": "a" * 64, "idempotency_key": "fake-batch"}


class ApproveTest(unittest.TestCase):
    def approve(self, runner, body=BODY, projection=READY):
        with patch.object(v7_api_sheet, "receipt_projection", return_value=projection):
            return api.approve_receipts(json.dumps(body).encode(), runner, "fake-actor")

    def test_writes_ready_rows_through_record_receipt(self):
        runner = Runner()
        status, result = self.approve(runner)
        self.assertEqual((status, result["written"], result["complete"], result["version"]), (200, 2, True, 5))
        writes = [(f, {k: v for k, v in p.items() if k != "idempotency_key"}) for f, p, _ in runner.calls if f != "get_ledger"]
        self.assertEqual(writes, [
            ("record_receipt", {"customer_id": 7, "expected_version": 3, "date": "2026-10-23", "method": "THU TIỀN",
                                "amount_vnd": "50000000", "reference": "Sheet: 23/10/2026 tt"}),
            ("record_receipt", {"customer_id": 7, "expected_version": 4, "date": "2026-10-21", "method": "THU TIỀN",
                                "amount_vnd": "1000", "reference": "Sheet: 46316"})])
        self.assertTrue(all(c[2] == "fake-actor" for c in runner.calls))

    def test_repeat_click_uses_the_same_command_keys(self):
        first, second = Runner(), Runner()
        self.approve(first)
        self.approve(second)
        keys = [[p["idempotency_key"] for f, p, _ in r.calls if f != "get_ledger"] for r in (first, second)]
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(keys[0][0], hashlib.sha256(f"fake-batch:{'a' * 64}:KHACH A:40:50000000:2026-10-23".encode()).hexdigest())

    def test_stale_sheet_and_ledger_are_refused(self):
        with self.assertRaises(api.ApiError) as stale:
            self.approve(Runner(), body=BODY | {"snapshot_sha256": "b" * 64})
        self.assertEqual(stale.exception.code, "STALE_SHEET")
        with self.assertRaises(api.ApiError) as old:
            self.approve(Runner(), body=BODY | {"expected_version": 2})
        self.assertEqual(old.exception.code, "STALE_LEDGER")

    def test_failure_mid_batch_reports_what_was_written(self):
        status, result = self.approve(Runner(fail_at=2))
        self.assertEqual((status, result["written"], result["remaining"], result["complete"]), (200, 1, 1, False))
        with self.assertRaises(api.ApiError):
            self.approve(Runner(fail_at=1))

    def test_bad_body_is_refused(self):
        for body in (BODY | {"extra": 1}, BODY | {"customer_id": 0}, BODY | {"idempotency_key": ""}):
            with self.subTest(body=body), self.assertRaises(api.ApiError):
                self.approve(Runner(), body=body)


if __name__ == "__main__":
    unittest.main()
