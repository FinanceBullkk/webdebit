"""Máy tự tách phụ phí theo bảng PS và tự chọn cột (MAY-PS-01). Dữ liệu giả."""

import hashlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_inbox
from v7_api_validate import ApiError

TYPES = [{"id": 3, "name": "Phụ phí ban đầu", "system_key": "initial", "active": True},
         {"id": 4, "name": "Neo", "system_key": None, "active": True},
         {"id": 10, "name": "Health + KĐ", "system_key": None, "active": True}]


def item(target_id, month, status=None, fee=3000000, note=None):
    row = {"key": f"C{target_id}|{month}-03", "ps_source": "PS · dòng 4", "container": f"C{target_id}", "date": f"{month}-03",
           "target_kind": "legacy", "target_id": target_id, "month": month,
           "before": [{"id": target_id, "fee_type_id": 3, "amount_vnd": str(fee), "note": note}],
           "after": [{"fee_type_id": 10, "amount_vnd": str(fee), "note": None}], "fill": False}
    return row | ({"status": status} if status else {})


def wait_idle(inbox):
    deadline = time.monotonic() + 5
    while inbox.running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not inbox.running


class AutoPsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        path = Path(self.dir.name) / "sheet.json"
        path.write_text("{}", encoding="utf-8")
        self.calls, self.fail = [], None
        self.ready = [item(11, "2026-11")]
        self.review = [item(21, "2026-06", "MONTH_LOCKED"), item(22, "2026-06", "MONTH_LOCKED"), item(23, "2026-05", "TOTAL_DIFF")]
        self.lines = []
        test = self
        os.utime(path, (time.time() - 1000, time.time() - 1000))

        def project(runner, ledger, actor):
            ps = {"snapshot_sha256": "f" * 64, "ready": [] if test.written else test.ready,
                  "review": [r for r in test.review if not test.written or r["status"] != "MONTH_LOCKED"]}
            return {"sheet_sync": {"items": [], "removed_items": []}, "sheet_receipts": {"ready": [], "review": []},
                    "sheet_prices": {"ready": [], "review": []}, "ps_fees": ps}
        self.written = False
        self.inbox = v7_inbox.Inbox(project, lambda: (str(path),))

        class Runner:
            version = 3

            def run(self, function, payload, actor):
                test.calls.append((function, payload, actor))
                if function == "list_customers":
                    return {"customers": [{"id": 1, "status": "active"}]}
                if function == "get_fee_types":
                    return {"fee_types": TYPES}
                if function == "get_ledger":
                    return {"customer_id": 1, "version": self.version, "today_month": "2026-11-01", "month_locks": [],
                            "fee_columns": [{"fee_type_id": 4, "position": 1}],
                            "trips": [], "legacy_rows": [{"kind": "trip", "fee_lines": test.lines}]}
                if function in ("set_month_lock", "rewrite_trip_fees", "set_book_fee_columns"):
                    if function == "rewrite_trip_fees" and payload["target"].get("legacy_row_id") == test.fail:
                        raise ApiError(409, "FEE_LINES_CHANGED", "x")
                    self.version += 1
                    if function == "rewrite_trip_fees":
                        test.lines = test.lines + [{"fee_type_id": 10, "amount_vnd": "3000000"}]
                    return {"version": self.version}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def run_once(self):
        projection = self.inbox.project(self.runner, {}, "x")["ps_fees"]
        with patch.object(v7_inbox, "ps_projection", return_value=projection):
            self.inbox.start(self.runner)
            wait_idle(self.inbox)
        return self.inbox.view(self.runner)

    def writes(self):
        out = []
        for function, payload, actor in self.calls:
            if function == "set_month_lock":
                out.append((function, payload["month"], payload["locked"], actor))
            elif function == "rewrite_trip_fees":
                out.append((function, payload["target"]["legacy_row_id"], actor))
            elif function == "set_book_fee_columns":
                out.append((function, payload["fee_type_ids"], actor))
        return out

    def test_off_by_default(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text,trips,prices,road"}):
            view = self.run_once()
        self.assertEqual(self.writes(), [])
        self.assertEqual((view["auto"]["ps_enabled"], view["books"][0]["ps_auto"]), (False, 3))

    def test_splits_all_months_relocks_and_then_picks_columns(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "ps"}):
            view = self.run_once()
        machine = v7_inbox.AUTO_ACTOR
        # Tháng 6 khóa: mở một lần cho cả tháng, ghi, khóa lại; tháng 11 đang mở ghi thẳng; TOTAL_DIFF không đụng.
        self.assertEqual(self.writes(), [
            ("set_month_lock", "2026-06-01", False, machine),
            ("rewrite_trip_fees", 21, machine),
            ("rewrite_trip_fees", 22, machine),
            ("set_month_lock", "2026-06-01", True, machine),
            ("rewrite_trip_fees", 11, machine),
            ("set_book_fee_columns", [4, 10], machine)])
        auto = view["auto"]
        self.assertEqual((auto["ps_enabled"], auto["today_ps"], auto["today_ps_books"], auto["errors"]), (True, 3, 1, 0))
        self.assertEqual({(i["container"], i["locked"], i["month"]) for i in auto["ps_items"]},
                         {("C21", True, "2026-06"), ("C22", True, "2026-06"), ("C11", False, "2026-11")})
        self.assertEqual((auto["today_count"], auto["today_trips"], auto["today_prices"]), (0, 0, 0))

    def test_same_key_on_retry_matches_the_button_path(self):
        self.ready, self.review = [item(11, "2026-11")], []
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "ps"}):
            self.run_once()
            self.inbox.key = None
            self.run_once()
        keys = [p["idempotency_key"] for f, p, _ in self.calls if f == "rewrite_trip_fees"]
        machine = f"{v7_inbox.AUTO_ACTOR}:ps:1"
        self.assertEqual(keys, [hashlib.sha256(f"{machine}:{'f' * 64}:legacy:11".encode()).hexdigest()] * 2)

    def test_note_keeps_the_row_for_a_person(self):
        self.ready, self.review = [item(11, "2026-11", note="gõ tay")], []
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "ps"}):
            view = self.run_once()
        self.assertEqual(self.writes(), [])
        self.assertEqual(view["books"][0]["ps_auto"], 0)

    def test_error_relocks_and_still_picks_columns_for_what_was_written(self):
        self.review = [item(21, "2026-05", "MONTH_LOCKED"), item(22, "2026-06", "MONTH_LOCKED")]
        self.fail = 22
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "ps"}), patch("sys.stderr"):
            view = self.run_once()
        self.assertEqual([w[:3] for w in self.writes()], [
            ("set_month_lock", "2026-05-01", False, ), ("rewrite_trip_fees", 21, v7_inbox.AUTO_ACTOR),
            ("set_month_lock", "2026-05-01", True), ("set_month_lock", "2026-06-01", False),
            ("rewrite_trip_fees", 22, v7_inbox.AUTO_ACTOR), ("set_month_lock", "2026-06-01", True),
            ("set_book_fee_columns", [4, 10], v7_inbox.AUTO_ACTOR)])
        self.assertEqual((view["auto"]["errors"], view["auto"]["today_ps"]), (1, 1))

    def test_history_rebuilds_machine_entries(self):
        ledger = {"trips": [], "legacy_rows": [{"id": 21, "current": {"container": "C21", "event_date": "2026-06-03", "month": "2026-06-01"}}],
                  "events": [{"actor": v7_inbox.AUTO_ACTOR, "kind": "rewrite_trip_fees", "at": "2026-11-04T03:00:00+00:00",
                              "before": {}, "after": {"targets": [{"legacy_row_id": 21}]}},
                             {"actor": "nguoi-thu", "kind": "rewrite_trip_fees", "at": "2026-11-04T03:00:00+00:00",
                              "before": {}, "after": {"targets": [{"legacy_row_id": 21}]}},
                             {"actor": v7_inbox.AUTO_ACTOR, "kind": "month_lock", "at": "2026-11-04T02:59:50+00:00",
                              "before": {}, "after": {"month": "2026-06-01", "locked": False}}]}
        entries = v7_inbox.machine_entries(1, ledger, "2026-11-04")
        self.assertEqual([(e["kind"], e["container"], e["date"], e["month"], e["locked"]) for e in entries],
                         [("ps", "C21", "2026-06-03", "2026-06", True)])


if __name__ == "__main__":
    unittest.main()
