"""`run_snapshot` của adapter V7 (XUAT-SO-01): nhiều hàm đọc trong một giao dịch chỉ đọc, kết quả từng dòng, lỗi thành
DB_UNAVAILABLE. Không cần DB: chương trình psql giả (Python) đọc lệnh SQL và tham số `-v`, in kết quả theo chế độ được đặt.
Harness PostgreSQL thật ở tools/test_pg_v7_xuat_so.py."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_psql  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402

FAKE_PSQL = r'''
import json, os, sys, time
args, values = sys.argv[1:], {}
for index, arg in enumerate(args):
    if arg == "-v":
        name, _, value = args[index + 1].partition("=")
        values[name] = value
sql = sys.stdin.read()
with open(os.environ["FAKE_PSQL_OUT"], "w", encoding="utf-8") as out:
    json.dump({"sql": sql, "values": values}, out)
mode = os.environ.get("FAKE_PSQL_MODE", "ok")
calls = sorted((key for key in values if key[:1] == "p" and key[1:].isdigit()), key=lambda key: int(key[1:]))
if mode == "slow":
    time.sleep(30)
if mode == "bad":
    print("không phải JSON")
    sys.exit(0)
for number, key in enumerate(calls):
    if mode == "short" and number == len(calls) - 1:
        sys.exit(0)
    print(json.dumps({"n": number, "payload": json.loads(values[key])}, ensure_ascii=False), flush=True)
    if mode == "fail":
        sys.exit(3)
'''


class FakeRunner(v7_psql._PsqlRunner):
    def __init__(self, script: Path):
        self.script = script

    def _argv(self):
        return [sys.executable, "-I", str(self.script)]


class SnapshotTest(unittest.TestCase):
    CALLS = (("get_dashboard", {}), ("list_customers", {}), ("get_ledger_export", {"customer_id": 5}))

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        (self.folder / "psql.py").write_text(FAKE_PSQL, encoding="utf-8")
        self.runner = FakeRunner(self.folder / "psql.py")

    def run_mode(self, mode, calls=CALLS, **options):
        with patch.dict(os.environ, {"FAKE_PSQL_MODE": mode, "FAKE_PSQL_OUT": str(self.folder / "seen.json")}):
            got = []
            try:
                for value in self.runner.run_snapshot(calls, "nguoi-xuat", **options):
                    got.append(value)
            except ApiError as exc:
                return got, exc
            return got, None

    def seen(self):
        return json.loads((self.folder / "seen.json").read_text(encoding="utf-8"))

    def test_one_read_only_transaction_in_call_order(self):
        got, error = self.run_mode("ok")
        self.assertIsNone(error)
        self.assertEqual(got, [{"n": 0, "payload": {}}, {"n": 1, "payload": {}}, {"n": 2, "payload": {"customer_id": 5}}])
        seen = self.seen()
        self.assertEqual(seen["sql"].splitlines(), [
            "BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;",
            "SET LOCAL statement_timeout = '60s';",
            "SET LOCAL sokhach.actor = :'actor';",
            "SELECT sokhach.get_dashboard();",
            "SELECT sokhach.list_customers();",
            "SELECT sokhach.get_ledger((:'p2'::jsonb->>'customer_id')::bigint) - 'events';",
            "COMMIT;"])
        self.assertEqual(seen["values"], {"p0": "{}", "p1": "{}", "p2": '{"customer_id":5}', "actor": "nguoi-xuat"})

    def test_failure_after_some_results_raises_at_the_end(self):
        for mode, count in (("fail", 1), ("short", 2), ("bad", 0)):
            with self.subTest(mode=mode):
                got, error = self.run_mode(mode)
                self.assertEqual(len(got), count)
                self.assertEqual((error.status, error.code), (503, "DB_UNAVAILABLE"))

    def test_timeout_stops_psql(self):
        started = time.monotonic()
        got, error = self.run_mode("slow", timeout=1)
        self.assertEqual((got, error.code), ([], "DB_UNAVAILABLE"))
        self.assertLess(time.monotonic() - started, 20)

    def test_only_read_functions(self):
        for calls in ([], [("record_receipt", {})], [("get_ledger", {"customer_id": 1})]):
            with self.subTest(calls=calls), self.assertRaises(ValueError):
                next(self.runner.run_snapshot(calls, "a"))

    def test_closing_early_stops_without_error(self):
        with patch.dict(os.environ, {"FAKE_PSQL_MODE": "ok", "FAKE_PSQL_OUT": str(self.folder / "seen.json")}):
            results = self.runner.run_snapshot(self.CALLS, "a")
            self.assertEqual(next(results)["n"], 0)
            results.close()


class ConsistentReadTest(unittest.TestCase):
    """Audit 19/11/2026 (A01): lượt GET đọc nặng chạy trong một ảnh dữ liệu, giữ giới hạn thời gian thường của người dùng."""

    setUp, seen = SnapshotTest.setUp, SnapshotTest.seen

    def run_one(self, **flags):
        seen = self.folder / "seen.json"
        with patch.dict(os.environ, {"FAKE_PSQL_MODE": "ok", "FAKE_PSQL_OUT": str(seen)}), \
                patch.object(v7_psql.subprocess, "run", wraps=v7_psql.subprocess.run) as spy:
            self.runner.run_text("get_ledger", {"customer_id": 5}, "nguoi-xem", **flags)
        return self.seen()["sql"].splitlines(), spy.call_args.kwargs["timeout"]

    def test_consistent_get_is_one_repeatable_read_only_transaction(self):
        lines, timeout = self.run_one(consistent=True)
        self.assertEqual(lines[:2], ["BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;", "SET LOCAL sokhach.actor = :'actor';"])
        self.assertEqual(timeout, 25, "lượt GET của người dùng không nhận giới hạn 90 giây của việc nền")

    def test_default_and_background_headers_unchanged(self):
        self.assertEqual(self.run_one()[0][0], "BEGIN;")   # lệnh ghi: READ COMMITTED, thấy chính phần mình ghi
        lines, timeout = self.run_one(read_only=True)
        self.assertEqual(lines[:2], ["BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;", "SET LOCAL statement_timeout = '60s';"])
        self.assertEqual(timeout, v7_psql.READ_ONLY_PROCESS_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
