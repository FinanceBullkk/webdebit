"""Focused guards for the read-only M1 viewer."""

from __future__ import annotations

import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import app  # noqa: E402
from db import Database  # noqa: E402


class FakeDB:
    def __init__(self, baseline_date="2026-10-13"):
        self.baseline_date = baseline_date

    def provenance(self):
        return [{"baseline_date": self.baseline_date}]

    def source_row(self, gid, row):
        if (gid, row) != (1, 2):
            return []
        return [{"tab_title": '<img src=x onerror=alert(1)>',
                 "row_sha256": "a" * 64,
                 "source_values": ['<script>alert(1)</script>', '" onclick="bad()', None],
                 "source_url": "https://docs.google.com/example"}]

    def exception_counts(self):
        return [{"code": "ZERO_TOTAL", "n": 86}]

    def exception_total(self, code, customer):
        return 86

    def exceptions(self, code, customer, limit, offset):
        return []


class WebTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        handler = type("TestHandler", (app.ViewerHandler,), {
            "db": self.db,
            "capture_id": "2026-10-13-debit-2026-1791884418948",
            "as_of": "2026-10-13",
            "port": 0,
        })
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        handler.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, method="GET", headers=None):
        request = Request(self.base + path, method=method, headers=headers or {})
        try:
            response = urlopen(request, timeout=2)
        except HTTPError as exc:
            response = exc
        return response.status, response.read().decode("utf-8")

    def test_source_html_is_escaped(self):
        status, body = self.request("/source?gid=1&row=2")
        self.assertEqual(status, 200)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", body)
        self.assertNotIn("<script>", body)
        self.assertNotIn("<img src=x", body)

    def test_rejects_writes_bad_host_and_bad_pagination(self):
        self.assertEqual(self.request("/health", method="POST")[0], 405)
        self.assertEqual(self.request("/exceptions?page=0")[0], 400)
        self.assertEqual(self.request("/exceptions?page=10001")[0], 400)
        self.assertEqual(self.request("/period?name=x&period=2026-13")[0], 400)
        self.assertEqual(self.request("/source?gid=1&row=-2")[0], 400)
        self.assertEqual(self.request("/health", headers={"Host": "attacker.example"})[0], 400)

    def test_health_fails_on_wrong_baseline_date(self):
        self.db.baseline_date = "2026-10-12"
        status, body = self.request("/health")
        self.assertEqual(status, 503)
        self.assertIn('"ok": false', body)

    def test_pagination_keeps_filter(self):
        status, body = self.request("/exceptions?code=ZERO_TOTAL&page=2")
        self.assertEqual(status, 200)
        self.assertIn("Trang 2 / 2", body)
        self.assertIn("page=1&amp;code=ZERO_TOTAL", body)

    def test_replay_page_identifies_current_ledger(self):
        status, body = self.request("/exceptions")
        self.assertEqual(status, 200)
        self.assertIn("Sổ PostgreSQL độc lập là sổ hiện hành", body)
        self.assertIn("http://127.0.0.1:8766/", body)
        self.assertNotIn("Google Sheet vẫn là sổ chính", body)


class QueryTest(unittest.TestCase):
    def test_user_value_stays_in_psql_variable(self):
        database = Database("test_db", "capture-1", "2026-10-13")
        hostile = "x'; DROP TABLE pilot.raw_row; --"
        result = type("Result", (), {"returncode": 0, "stdout": "[]"})()
        with patch("subprocess.run", return_value=result) as run:
            self.assertEqual(database.customers(hostile), [])
        command = run.call_args.args[0]
        statement = run.call_args.kwargs["input"]
        self.assertIn(f"search={hostile}", command)
        self.assertNotIn(hostile, statement)
        self.assertIn(":'search'", statement)


if __name__ == "__main__":
    unittest.main()
