"""BANG-THU-01: route đọc bảng thu, trang được phục vụ, migration khớp file chuẩn, chuỗi của máy khớp SQL."""

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402
from v7_api_tables import ASSETS  # noqa: E402
from v7_receipt_queue import reference, review_reference  # noqa: E402
from v7_sheet_fix import NO_DATE_NOTE  # noqa: E402

FUNCTIONS = ROOT / "tools/v7_backend_functions.sql"
MIGRATION = ROOT / "tools/migrations/2026-11-04-v7-bang-thu.sql"
HARNESS = ROOT / "tools/test_pg_v7_backend_bang_thu.py"


class FakePsql:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        return {"function": function}


def definition(text, name):
    start = text.index(f"CREATE OR REPLACE FUNCTION sokhach.{name}(")
    return text[start:text.index("END $$;", start)]


class ReceiptBookRouteTest(unittest.TestCase):
    def get(self, target):
        runner = FakePsql()
        headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780"}
        status, data = api.handle("GET", target, headers, b"", runner, port=8780, host="127.0.0.1", actor="server-actor")
        return status, data, runner.calls

    def test_default_month_and_explicit_month(self):
        status, data, calls = self.get("/api/v7/receipt-book")
        self.assertEqual((status, data["function"]), (200, "get_receipt_book"))
        self.assertEqual(calls, [("get_receipt_book", {"month": None}, "server-actor")])
        _, _, calls = self.get("/api/v7/receipt-book?month=2026-10-01")
        self.assertEqual(calls, [("get_receipt_book", {"month": "2026-10-01"}, "server-actor")])

    def test_bad_query_is_rejected_before_the_database(self):
        for query in ("month=2026-10-15", "month=2026-10", "month=", "month=2026-10-01&month=2026-11-01", "thang=2026-10-01",
                      "month=2026-10-01&x=1", "month=abc"):
            with self.subTest(query=query), self.assertRaises(api.ApiError) as caught:
                self.get(f"/api/v7/receipt-book?{query}")
            self.assertEqual(caught.exception.code, "INVALID_MONTH")

    def test_sql_is_fixed_and_passes_month_as_date(self):
        self.assertIn("sokhach.get_receipt_book((:'payload'::jsonb->>'month')::date)", api.SQL["get_receipt_book"])

    def test_page_and_assets_are_served(self):
        self.assertEqual(ASSETS["/bang-thu.html"][0], "bang-thu.html")
        for asset in ("/bang-thu.js", "/bang-thu.css", "/cong-no-format.js", "/app-nav.js", "/presence.js"):
            self.assertIn(asset, ASSETS)


class SqlTextTest(unittest.TestCase):
    def test_migration_matches_canonical_file(self):
        migration, functions = MIGRATION.read_text(encoding="utf-8"), FUNCTIONS.read_text(encoding="utf-8")
        for name in ("_legacy_pay_date", "get_receipt_book"):
            self.assertEqual(definition(migration, name), definition(functions, name), name)

    def test_machine_strings_match_the_sql(self):
        """SQL nhận phiếu máy đặt ngày và bỏ tiền tố kỹ thuật bằng đúng chuỗi mà máy ghi; đổi một bên thì test này đỏ."""
        sql = definition(MIGRATION.read_text(encoding="utf-8"), "get_receipt_book")
        marker = rf"( \(ngày tượng trưng\)|{NO_DATE_NOTE})$"
        self.assertEqual(sql.count(f"'{marker}'"), 2, "cả chỗ nhận phiếu đặt ngày lẫn chỗ bỏ đuôi khỏi ghi chú")
        self.assertIn(f'NO_DATE_NOTE = "{NO_DATE_NOTE}"', HARNESS.read_text(encoding="utf-8"))
        prefix = re.compile(r"^Sheet( #[^:]*)?(: ?|$)")
        for text, left in ((reference("23/10/2026 tt"), "23/10/2026 tt"), (reference(""), ""), (review_reference("ab12") + "da tt", "da tt")):
            self.assertEqual(prefix.sub("", text), left)
        self.assertIn("'^Sheet( #[^:]*)?(: ?|$)'", sql)

    def test_function_is_read_only(self):
        sql = definition(MIGRATION.read_text(encoding="utf-8"), "get_receipt_book")
        self.assertIsNone(re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE)\b", sql))


if __name__ == "__main__":
    unittest.main()
