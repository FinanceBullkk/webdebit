"""Bảng đối chiếu (VIEC-DOI-CHIEU-01): đọc đúng khoản của máy, ghi đúng số người đã xem, tháng khóa mở-ghi-khóa. Dữ liệu giả, không DB."""

import json
import sys
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_api_doi_chieu as api
from v7_api_validate import ApiError
from v7_inbox import AUTO_ACTOR

SHA_P, SHA_R = "a" * 64, "b" * 64
ACTOR = "chu-so@example.test"


def price_row(target, delta_fee, status="CONFLICT"):
    return {"status": status, "month": "2026-10", "target_kind": "legacy", "target_id": target, "container": f"MAUU{target}", "date": "2026-10-03",
            "source_row": 400 + target, "sheet_unit_price_vnd": "60000000", "sheet_other_fee_vnd": str(delta_fee),
            "web_unit_price_vnd": "60000000", "web_other_fee_vnd": None, "web_total_vnd": "60000000", "source_fingerprint": "f" * 64}


def receipt_row():
    return {"customer_tab": "KHACH MAU", "source_row": 30, "debt_month": "2026-10-01", "amount_vnd": "6100000", "note": "tru phi",
            "date": None, "status": "NO_DATE", "source_fingerprint": "e" * 64}


PRICES = {"kind": "prices", "month": "2026-10", "rows": [price_row(1, 50000000), price_row(2, 8400000)], "delta_vnd": 58400000}
RECEIPTS = {"kind": "receipts_no_date", "month": "2026-09", "rows": [receipt_row()], "delta_vnd": -6100000}
FEES = {"kind": "fee_rows", "month": "2026-08", "rows": [{"source_row": 9, "amount_vnd": "100"}], "delta_vnd": 100}


class Runner:
    """Sổ giả: tháng 10 đang khóa, mỗi lệnh ghi tăng phiên bản; ghi tiền ở tháng khóa thì báo lỗi như DB."""

    def __init__(self, fail=None):
        self.version, self.total, self.calls, self.locks, self.fail = 12, 5210000000, [], {"2026-10-01": True}, fail

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "get_ledger":
            return {"customer_id": 7, "version": self.version, "total_outstanding_vnd": str(self.total), "today_month": "2026-11-01",
                    "month_locks": [{"month": month, "locked": locked} for month, locked in self.locks.items()]}
        if function == "list_customers":
            return {"customers": [{"id": 7, "name": "KHACH MAU"}]}
        if function == self.fail:
            raise ApiError(409, "FAKE_FAILED", "Lỗi giả.")
        self.version += 1
        if function == "set_month_lock":
            self.locks[payload["month"]] = payload["locked"]
        if function == "edit_legacy_trip":
            if self.locks.get("2026-10-01"):
                raise ApiError(409, "MONTH_LOCKED", "Tháng đang khóa.")
            self.total += int(payload["value"] or 0)
        if function == "record_receipt":
            self.total -= int(payload["amount_vnd"])
        return {"version": self.version}

    def writes(self):
        return [(function, actor) for function, _, actor in self.calls if function not in ("get_ledger", "list_customers")]


class Base(unittest.TestCase):
    groups = (PRICES, RECEIPTS)
    reconcile: ClassVar[dict] = {"checked_at": "2026-11-06T10:12:00+07:00", "customers": [
        {"customer_id": 7, "sheet_total_vnd": "5274200000", "reason": "NO_EXACT_FIX", "sheet_editing": True, "sheet_last_edit_at": "2026-11-06T10:00:00+07:00"}]}

    def setUp(self):
        snapshots = {api.load_price_snapshot: {"sha256": SHA_P}, api.load_receipt_snapshot: {"sha256": SHA_R}}
        for target, value in (("cached_load", lambda loader, _path: snapshots[loader]), ("customer_name_mapping", dict),
                              ("plan", lambda *_args: ([dict(group) for group in self.groups], 0, [])), ("reconcile_result", lambda: self.reconcile)):
            patcher = patch.object(api, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def body(**extra):
        return json.dumps({"customer_id": 7, "expected_version": 12, "prices_sha256": SHA_P, "receipts_sha256": SHA_R,
                           "items": [{"id": "prices:2026-10", "delta_vnd": "58400000", "rows": None}], **extra}).encode()


class StatementTest(Base):
    def test_numbers_and_rows(self):
        result = api.statement(7, Runner(), ACTOR)
        self.assertEqual((result["web_vnd"], result["sheet_total_vnd"], result["version"], result["web_ahead_vnd"]), ("5210000000", "5274200000", 12, "0"))
        self.assertEqual((result["prices_sha256"], result["receipts_sha256"], result["sheet_editing"]), (SHA_P, SHA_R, True))
        prices, receipts = result["groups"]
        self.assertEqual((prices["id"], prices["delta_vnd"], prices["count"], prices["locked"], prices["undoable"]), ("prices:2026-10", "58400000", 2, True, True))
        self.assertEqual((prices["rows"][0]["key"], prices["rows"][0]["delta_vnd"], prices["rows"][0]["source_row"]), ("legacy:1", "50000000", 401))
        self.assertEqual((receipts["id"], receipts["delta_vnd"], receipts["rows"][0]["amount_vnd"]), ("receipts_no_date:2026-09", "-6100000", "6100000"))

    def test_customer_not_in_reconcile_has_null_sheet_total(self):
        with patch.object(api, "reconcile_result", return_value=None):
            self.assertIsNone(api.statement(7, Runner(), ACTOR)["sheet_total_vnd"])

    def test_broken_snapshot_is_503(self):
        with patch.object(api, "cached_load", side_effect=ValueError), self.assertRaises(ApiError) as caught:
            api.statement(7, Runner(), ACTOR)
        self.assertEqual(caught.exception.status, 503)


class WriteTest(Base):
    def test_locked_month_opens_writes_relocks_with_person_on_the_money_commands(self):
        runner = Runner()
        status, result = api.write(self.body(), runner, ACTOR)
        self.assertEqual((status, result["complete"], result["before_vnd"], result["after_vnd"]), (200, True, "5210000000", "5268400000"))
        self.assertEqual(runner.writes(), [("set_month_lock", AUTO_ACTOR), ("edit_legacy_trip", ACTOR), ("edit_legacy_trip", ACTOR), ("set_month_lock", AUTO_ACTOR)])
        self.assertEqual(runner.locks["2026-10-01"], True)
        self.assertEqual(len(result["undo"]["command_keys"]), 2)
        self.assertEqual(result["undo"]["months"], ["2026-10"])

    def test_selected_rows_only_and_their_sum_must_match(self):
        runner = Runner()
        api.write(self.body(items=[{"id": "prices:2026-10", "delta_vnd": "8400000", "rows": ["legacy:2"]}]), runner, ACTOR)
        edits = [payload for function, payload, _ in runner.calls if function == "edit_legacy_trip"]
        self.assertEqual([edit["legacy_row_id"] for edit in edits], [2])
        runner = Runner()
        with self.assertRaises(ApiError) as caught:
            api.write(self.body(items=[{"id": "prices:2026-10", "delta_vnd": "58400000", "rows": ["legacy:2"]}]), runner, ACTOR)
        self.assertEqual(caught.exception.code, "STALE_SHEET")
        self.assertEqual(runner.writes(), [])

    def test_anything_changed_since_viewing_writes_nothing(self):
        cases = {"STALE_LEDGER": {"expected_version": 11}, "STALE_SHEET": {"prices_sha256": "c" * 64},
                 "STALE_SHEET ": {"items": [{"id": "prices:2026-10", "delta_vnd": "1", "rows": None}]},
                 "STALE_SHEET  ": {"items": [{"id": "prices:2026-09", "delta_vnd": "58400000", "rows": None}]},
                 "STALE_SHEET   ": {"items": [{"id": "prices:2026-10", "delta_vnd": "8400000", "rows": ["legacy:9"]}]}}
        for code, change in cases.items():
            runner = Runner()
            with self.subTest(code=code), self.assertRaises(ApiError) as caught:
                api.write(self.body(**change), runner, ACTOR)
            self.assertEqual(caught.exception.code, code.strip())
            self.assertEqual(runner.writes(), [])

    def test_retry_after_lost_response_does_not_write_twice(self):
        runner = Runner()
        api.write(self.body(), runner, ACTOR)
        count = len(runner.writes())
        with self.assertRaises(ApiError) as caught:
            api.write(self.body(), runner, ACTOR)
        self.assertEqual(caught.exception.code, "STALE_LEDGER")
        self.assertEqual(len(runner.writes()), count)

    def test_invalid_bodies_rejected(self):
        for raw in (b"{", json.dumps({"customer_id": 7}).encode(), self.body(items=[]), self.body(items=["x"]),
                    self.body(items=[{"id": "prices:2026-10", "delta_vnd": "x", "rows": None}]),
                    self.body(items=[{"id": "prices:2026-10", "delta_vnd": "58400000", "rows": None}] * 2),
                    self.body(items=[{"id": "receipts_no_date:2026-09", "delta_vnd": "-6100000", "rows": ["a"]}]),
                    self.body(prices_sha256="short"), self.body(customer_id=0), self.body(expected_version="12")):
            runner = Runner()
            with self.subTest(raw=raw[:60]), self.assertRaises(ApiError) as caught:
                api.write(raw, runner, ACTOR)
            self.assertEqual(caught.exception.status, 422)
            self.assertEqual(runner.writes(), [])

    def test_failure_midway_still_relocks_month(self):
        runner = Runner(fail="edit_legacy_trip")
        with self.assertRaises(ApiError):
            api.write(self.body(), runner, ACTOR)
        self.assertEqual(runner.locks["2026-10-01"], True)

    def test_kinds_without_undo_return_no_undo(self):
        with patch.object(api, "plan", lambda *_args: ([dict(PRICES), dict(FEES)], 0, [])):
            items = [{"id": "prices:2026-10", "delta_vnd": "58400000", "rows": None}, {"id": "fee_rows:2026-08", "delta_vnd": "100", "rows": None}]
            self.assertIsNone(api.write(self.body(items=items), Runner(), ACTOR)[1]["undo"])


class KeepUndoTest(Base):
    def test_keep_many_rows_chain_versions_and_retry_same_keys(self):
        runner = Runner()
        calls = []

        def fake_keep(raw, run, actor):
            calls.append((json.loads(raw), actor))
            run.version += 1
            return 200, {}
        rows = [{"target_kind": "legacy", "target_id": 1, "source_fingerprint": "f" * 64}, {"target_kind": "legacy", "target_id": 2, "source_fingerprint": "f" * 64}]
        raw = json.dumps({"customer_id": 7, "expected_version": 12, "idempotency_key": "lan-1", "rows": rows}).encode()
        with patch.object(api, "keep_sheet_task", fake_keep):
            status, result = api.keep(raw, runner, ACTOR)
        self.assertEqual((status, result["kept"], result["version"]), (200, 2, 14))
        self.assertEqual([call[0]["expected_version"] for call in calls], [12, 13])
        self.assertEqual({call[0]["task_kind"] for call in calls}, {"price"})
        self.assertEqual({call[1] for call in calls}, {ACTOR})
        first_keys = [call[0]["idempotency_key"] for call in calls]
        self.assertEqual(len(set(first_keys)), 2)
        calls.clear()
        with patch.object(api, "keep_sheet_task", fake_keep):
            api.keep(raw, Runner(), ACTOR)
        self.assertEqual([call[0]["idempotency_key"] for call in calls], first_keys)

    def test_keep_rejects_bad_rows(self):
        for rows in ([], ["x"], [{"target_kind": "legacy"}]):
            raw = json.dumps({"customer_id": 7, "expected_version": 12, "idempotency_key": "k", "rows": rows}).encode()
            with self.subTest(rows=rows), self.assertRaises(ApiError):
                api.keep(raw, Runner(), ACTOR)

    def test_undo_opens_each_locked_month_and_relocks(self):
        runner = Runner()
        raw = json.dumps({"customer_id": 7, "expected_version": 12, "idempotency_key": "hoan-tac", "command_keys": ["d" * 64], "months": ["2026-10"]}).encode()
        status, result = api.undo(raw, runner, ACTOR)
        self.assertEqual((status, result["undone"]), (200, 1))
        self.assertEqual(runner.writes(), [("set_month_lock", AUTO_ACTOR), ("undo_sheet_batch", ACTOR), ("set_month_lock", AUTO_ACTOR)])
        self.assertEqual(runner.locks["2026-10-01"], True)

    def test_undo_refused_when_book_changed_or_body_invalid(self):
        for change in ({"expected_version": 5}, {"command_keys": ["short"]}, {"command_keys": []}, {"months": ["10/2026"]}):
            base = {"customer_id": 7, "expected_version": 12, "idempotency_key": "k", "command_keys": ["d" * 64], "months": []}
            runner = Runner()
            with self.subTest(change=change), self.assertRaises(ApiError):
                api.undo(json.dumps(base | change).encode(), runner, ACTOR)
            self.assertEqual(runner.writes(), [])


if __name__ == "__main__":
    unittest.main()
