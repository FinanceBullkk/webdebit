"""TIM-CONT-01, KHACH-THANG-01: route đọc tìm cont và khách theo tháng, SQL cố định, migration khớp file chuẩn."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402
import v7_read_cache  # noqa: E402
import v7_role  # noqa: E402


class FakePsql:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        return {"function": function}


class RouteTest(unittest.TestCase):
    def get(self, target):
        runner = FakePsql()
        headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780"}
        status, data = api.handle("GET", target, headers, b"", runner, port=8780, host="127.0.0.1", actor="server-actor")
        return status, data, runner.calls

    def test_find_container_passes_the_raw_query(self):
        status, data, calls = self.get("/api/v7/containers/find?q=abcd%201234")
        self.assertEqual((status, data["function"]), (200, "find_container"))
        self.assertEqual(calls, [("find_container", {"q": "abcd 1234"}, "server-actor")])

    def test_find_container_rejects_bad_queries_before_the_database(self):
        for query in ("", "q=", "q=abc", "q=%20a%20b%20c%20", "q=" + "A" * 21, "q=abcd&q=efgh", "q=abcd&x=1", "x=abcd"):
            with self.subTest(query=query), self.assertRaises(api.ApiError) as caught:
                self.get(f"/api/v7/containers/find?{query}")
            self.assertEqual(caught.exception.code, "INVALID_QUERY")

    def test_month_customers_default_and_explicit_month(self):
        status, data, calls = self.get("/api/v7/month-customers")
        self.assertEqual((status, data["function"]), (200, "get_month_customers"))
        self.assertEqual(calls[-1], ("get_month_customers", {"month": None}, "server-actor"))
        _, _, calls = self.get("/api/v7/month-customers?month=2026-10-01")
        self.assertEqual(calls[-1], ("get_month_customers", {"month": "2026-10-01"}, "server-actor"))

    def test_month_customers_rejects_bad_month(self):
        for query in ("month=2026-10-15", "month=2026-10", "month=", "thang=2026-10-01", "month=2026-10-01&month=2026-11-01"):
            with self.subTest(query=query), self.assertRaises(api.ApiError) as caught:
                self.get(f"/api/v7/month-customers?{query}")
            self.assertEqual(caught.exception.code, "INVALID_MONTH")

    def test_sql_is_fixed(self):
        self.assertEqual(api.SQL["find_container"], "SELECT sokhach.find_container(:'payload'::jsonb->>'q');")
        self.assertIn("sokhach.get_month_customers((:'payload'::jsonb->>'month')::date)", api.SQL["get_month_customers"])

    def test_month_customers_is_cached_and_open_to_every_login(self):
        self.assertIn("get_month_customers", v7_read_cache.CACHED)
        for path in ("/api/v7/month-customers", "/api/v7/containers/find"):
            self.assertFalse(v7_role.admin_api(path), path)


if __name__ == "__main__":
    unittest.main()
