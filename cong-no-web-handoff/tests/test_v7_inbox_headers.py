"""Máy tự tách phụ phí theo tên cột tab khách (TACH-PHI-TIEU-DE-01, bật `headers`). Dữ liệu giả."""

import hashlib
import json
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

TYPES = [{"id": 1, "name": "Khác", "system_key": "other", "active": True},
         {"id": 4, "name": "Neo", "system_key": None, "active": True},
         {"id": 11, "name": "Cân hàng", "system_key": None, "active": True},
         {"id": 12, "name": "Local charge", "system_key": None, "active": True}]


def plan(target_id, month, status="READY"):
    after = [{"fee_type_id": 11, "amount_vnd": "5000000", "note": None},
             {"fee_type_id": 12, "amount_vnd": "8907280", "note": None}]
    return {"status": status, "row": {"source_row": target_id, "container": f"C{target_id}", "date": f"{month}-09"},
            "target": {"kind": "trip", "id": target_id, "month": month},
            "info": {"before": [{"id": 100 + target_id, "fee_type_id": 1, "amount_vnd": "13907280", "note": None}],
                     "after": after}}


def wait_idle(inbox):
    deadline = time.monotonic() + 5
    while inbox.running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not inbox.running


class AutoHeadersTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        path = Path(self.dir.name) / "sheet.json"
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (time.time() - 1000, time.time() - 1000))
        self.calls, self.written, self.fail = [], set(), None
        self.plans = [plan(11, "2026-11"), plan(21, "2026-06", "MONTH_LOCKED"), plan(23, "2026-05", "TOTAL_DIFF")]
        test = self

        def project(runner, ledger, actor):   # sổ không có việc nào khác: chỉ việc máy tách theo tên cột
            return {"sheet_sync": {"items": [], "removed_items": []}, "sheet_receipts": {"ready": [], "review": []},
                    "sheet_prices": {"ready": [], "review": []}, "ps_fees": {"ready": [], "review": []}}
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
                            "fee_columns": [{"fee_type_id": 4, "position": 1}], "trips": [], "legacy_rows": []}
                if function in ("set_month_lock", "rewrite_trip_fees", "set_book_fee_columns"):
                    if function == "rewrite_trip_fees":
                        if payload["target"]["trip_id"] == test.fail:
                            raise ApiError(409, "FEE_LINES_CHANGED", "x")
                        test.written.add(payload["target"]["trip_id"])
                    self.version += 1
                    return {"version": self.version}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def headers(self, runner, ledger, actor):
        return "e" * 64, [p for p in self.plans if p["target"]["id"] not in self.written]

    def run_once(self):
        with patch.object(v7_inbox, "header_projection", side_effect=self.headers):
            self.inbox.start(self.runner)
            wait_idle(self.inbox)
            return self.inbox.view(self.runner)

    def writes(self):
        out = []
        for function, payload, actor in self.calls:
            if function == "set_month_lock":
                out.append((function, payload["month"], payload["locked"], actor))
            elif function == "rewrite_trip_fees":
                out.append((function, payload["target"]["trip_id"], actor))
            elif function == "set_book_fee_columns":
                out.append((function, payload["fee_type_ids"], actor))
        return out

    def test_off_by_default(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text,trips,prices,road,ps"}):
            view = self.run_once()
        self.assertEqual(self.writes(), [])
        self.assertFalse(view["auto"]["headers_enabled"])

    def test_splits_every_month_relocks_and_adds_columns(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "headers"}):
            view = self.run_once()
        machine = v7_inbox.AUTO_ACTOR
        # Tháng 6 khóa: mở, ghi, khóa lại; tháng 11 mở ghi thẳng; TOTAL_DIFF để nguyên (vẫn Khác như trước).
        self.assertEqual(self.writes(), [
            ("set_month_lock", "2026-06-01", False, machine), ("rewrite_trip_fees", 21, machine),
            ("set_month_lock", "2026-06-01", True, machine), ("rewrite_trip_fees", 11, machine),
            ("set_book_fee_columns", [4, 11, 12], machine)])
        payload = next(p for f, p, _ in self.calls if f == "rewrite_trip_fees")
        self.assertEqual(payload["source"]["kind"], "sheet_header")
        self.assertEqual(payload["expected_line_ids"], [121])
        self.assertEqual([x["amount_vnd"] for x in payload["lines"]], ["5000000", "8907280"])   # tổng bằng khoản Khác cũ
        auto = view["auto"]
        self.assertEqual((auto["headers_enabled"], auto["today_ps"], auto["errors"]), (True, 2, 0))
        self.assertEqual(view["books"], [])   # việc máy không thành việc của sổ
        self.assertEqual(self.inbox.header_todo, set())

    def test_same_snapshot_same_key(self):
        self.plans = [plan(11, "2026-11")]
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "headers"}):
            self.run_once()
        lines = plan(11, "2026-11")["info"]["after"]
        key = f"{v7_inbox.AUTO_ACTOR}:headers:1:{'e' * 64}:trip:11:{json.dumps(lines, sort_keys=True)}"
        self.assertEqual([p["idempotency_key"] for f, p, _ in self.calls if f == "rewrite_trip_fees"],
                         [hashlib.sha256(key.encode()).hexdigest()])

    def test_error_stops_the_book_and_relocks(self):
        self.plans = [plan(21, "2026-06", "MONTH_LOCKED"), plan(22, "2026-06", "MONTH_LOCKED")]
        self.fail = 22
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "headers"}), patch("sys.stderr"):
            view = self.run_once()
        self.assertEqual([w[:3] for w in self.writes()], [
            ("set_month_lock", "2026-06-01", False), ("rewrite_trip_fees", 21, v7_inbox.AUTO_ACTOR),
            ("rewrite_trip_fees", 22, v7_inbox.AUTO_ACTOR), ("set_month_lock", "2026-06-01", True),
            ("set_book_fee_columns", [4, 11, 12], v7_inbox.AUTO_ACTOR)])
        self.assertEqual((view["auto"]["errors"], view["auto"]["today_ps"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
