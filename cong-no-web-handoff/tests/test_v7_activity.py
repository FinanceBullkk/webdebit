"""HOAT-DONG-01: route đọc việc đã ghi theo ngày, tên ngắn người làm, migration khớp file chuẩn, hàm chỉ đọc."""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402

FUNCTIONS = ROOT / "tools/v7_backend_functions.sql"
MIGRATION = ROOT / "tools/migrations/2026-11-09-v7-hoat-dong.sql"
HEADERS = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780"}


class FakePsql:
    def __init__(self, result=None):
        self.calls = []
        self.result = result

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        return self.result if self.result is not None else {"function": function}


def definition(text, name):
    start = text.index(f"CREATE OR REPLACE FUNCTION sokhach.{name}(")
    return text[start:text.index("END $$;", start)]


class ActivityRouteTest(unittest.TestCase):
    def get(self, target, runner=None):
        runner = runner or FakePsql()
        status, data = api.handle("GET", target, HEADERS, b"", runner, port=8780, host="127.0.0.1", actor="server-actor")
        return status, data, runner.calls

    def test_default_day_and_explicit_day(self):
        status, _, calls = self.get("/api/v7/activity")
        self.assertEqual(status, 200)
        self.assertEqual(calls, [("get_activity", {"day": None}, "server-actor")])
        _, _, calls = self.get("/api/v7/activity?day=2026-11-08")
        self.assertEqual(calls, [("get_activity", {"day": "2026-11-08"}, "server-actor")])

    def test_bad_query_is_rejected_before_the_database(self):
        for query in ("day=2026-11", "day=", "day=2026-02-30", "day=08/11/2026", "day=2026-11-08&day=2026-11-07", "ngay=2026-11-08",
                      "day=2026-11-08&x=1"):
            runner = FakePsql()
            with self.subTest(query=query), self.assertRaises(api.ApiError) as caught:
                self.get(f"/api/v7/activity?{query}", runner)
            self.assertEqual((caught.exception.status, caught.exception.code), (422, "INVALID_DAY"))
            self.assertEqual(runner.calls, [])

    def test_actor_short_names_are_attached(self):
        body = {"day": "2026-11-08", "events": [{"id": 2, "actor": "Thu.Ke@example.test"}, {"id": 1, "actor": "may-theo-sheet"}]}
        with tempfile.TemporaryDirectory() as folder:
            names = Path(folder) / "names.json"
            names.write_text(json.dumps({"version": 1, "names": {"thu.ke@example.test": "Thu"}}), encoding="utf-8")
            with patch.object(api.PRESENCE, "names", api.v7_presence.NameTable(str(names))):
                _, data, _ = self.get("/api/v7/activity?day=2026-11-08", FakePsql(body))
        self.assertEqual([event["actor_name"] for event in data["events"]], ["Thu", "Máy (theo Sheet)"])
        self.assertEqual(data["day"], "2026-11-08")

    def test_sql_is_fixed_and_passes_day_as_date(self):
        self.assertEqual(api.SQL["get_activity"], "SELECT sokhach.get_activity((:'payload'::jsonb->>'day')::date);")


class SqlTextTest(unittest.TestCase):
    def test_migration_matches_canonical_file(self):
        self.assertEqual(definition(MIGRATION.read_text(encoding="utf-8"), "get_activity"),
                         definition(FUNCTIONS.read_text(encoding="utf-8"), "get_activity"))

    def test_function_is_read_only_and_app_only(self):
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", definition(text, "get_activity")))
        self.assertIn("GRANT EXECUTE ON FUNCTION sokhach.get_activity(date) TO sokhach_app;", text)
        self.assertNotIn("TO sokhach_app, sokhach_reader", text)


if __name__ == "__main__":
    unittest.main()
