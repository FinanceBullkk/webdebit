"""Focused checks for the ledger read surface and maker input guard."""

from __future__ import annotations

import sys
import threading
import unittest
import io
import json
from contextlib import redirect_stderr
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import ledger_app  # noqa: E402



class FakeLedger:
    data_scope = "fake test fixture; no live customer data"
    invalid_cutover = False
    source_workbook_sha256 = "a" * 64
    engine_sha256 = "b" * 64
    opening_periods = 496
    opening_vnd = 65051673578
    no_baseline = 46
    balance_vnd = 100

    def cutover(self):
        if self.invalid_cutover:
            return [{"capture_id": "wrong-capture", "as_of": "2026-10-13",
                     "source_workbook_sha256": self.source_workbook_sha256,
                     "engine_sha256": self.engine_sha256}]
        return [{"capture_id": ledger_app.CAPTURE, "as_of": "2026-10-13",
                 "source_workbook_sha256": self.source_workbook_sha256,
                 "engine_sha256": self.engine_sha256}]

    def totals(self, as_of):
        return {"customers": 1, "opening_periods": self.opening_periods,
                "no_baseline": self.no_baseline, "opening_vnd": self.opening_vnd,
                "movement_vnd": 0, "balance_vnd": self.balance_vnd,
                "pending": 1, "postings": 0}

    def customers(self, as_of, search=""):
        return [{"customer": "A & B", "opening_vnd": 100, "movement_vnd": 0,
                 "balance_vnd": 100, "periods": 1, "no_baseline": 1}]

    def overview(self, as_of, period, search=""):
        return [{"customer": "A & B", "carried_vnd": 0, "period_opening_vnd": 100,
                 "period_movement_vnd": 0, "period_balance_vnd": 100,
                 "total_balance_vnd": 100, "charge_vnd": 0, "receipt_vnd": 0,
                 "offset_vnd": 0, "other_vnd": 0, "comparison_status": "NO_BASELINE"}]

    def periods(self, as_of, customer):
        return [{"customer": customer, "debt_period": "2026-10", "opening_vnd": 100,
                 "movement_vnd": 0, "balance_vnd": 100, "comparison_status": "NO_BASELINE",
                 "replay_event_count": 2}]

    def period(self, as_of, customer, period):
        return self.periods(as_of, customer)

    def postings(self, as_of, customer="", period="", limit=100, offset=0):
        return []

    def proposals(self, status="pending", limit=100):
        return []

    def pending_for_customer(self, customer):
        return {"proposals": 1, "amount_vnd": 25,
                "pending_receipts": 1, "pending_charges": 0}


class FakeHistory:
    fail_summary = False
    fail_reconciliation = False
    summary_calls = 0
    reconciliation_calls = 0

    def events_for_customer(self, capture, customer, first_period="", limit=2001):
        return [
            {"debt_period": "2026-10", "event_no": 1, "posting_date": "2026-10-01",
             "kind": "charge", "amount_vnd": 150, "signed_amount_vnd": 150,
             "sheet_gid": 449250445, "source_row": 7,
             "source_values": ["A & B", "2026-10", "2026-10-01T00:00:00", "ABCU1234567",
                               "KMTC", "A", "B", "", "", "", 150, 150]},
            {"debt_period": "2026-10", "event_no": 2, "posting_date": "2026-10-03",
             "kind": "receipt", "amount_vnd": 50, "signed_amount_vnd": -50,
             "sheet_gid": 493290434, "source_row": 7,
             "source_values": ["A & B", "2026-10", "2026-10-03T00:00:00",
                               "2026-10-03T00:00:00", "THỰC NHẬN", 50]},
        ]

    def exception_items(self):
        return [
            {"exception_no": 1, "code": "MISSING_TOTAL", "status": "open", "customer": "ACME",
             "period": "2026-10", "detail": "<img src=x onerror=alert(1)>",
             "tab_title": "Chuyến hàng", "source_url": "javascript:alert(1)"},
            {"exception_no": 2, "code": "ZERO_TOTAL", "status": "open", "customer": "ACME",
             "period": "2026-10", "detail": "zero total", "tab_title": "Chuyến hàng",
             "source_url": "https://docs.google.com/spreadsheets/d/fake/edit#gid=3&range=A4"},
            {"exception_no": 3, "code": None, "status": "open", "customer": None,
             "period": "", "detail": "unclassified", "tab_title": "Khách hàng",
             "source_url": "https://example.test/source"},
            *[{"exception_no": number, "code": f"C{number}", "status": "open",
               "customer": "ACME", "period": "2026-10", "detail": f"detail {number}",
               "tab_title": "Chuyến hàng", "source_url": "https://example.test/source"}
              for number in range(4, 53)],
            {"exception_no": 53, "code": "W", "status": "open", "customer": "ACME",
             "period": " 2026-10", "detail": "source period with whitespace", "tab_title": "Chuyến hàng",
             "source_url": "https://example.test/source"},
        ]

    @staticmethod
    def matches(item, key, value):
        if value is None:
            return True
        actual = item.get("period" if key == "period" else key)
        if not value.strip(" \t\n\r\f\v"):
            return actual is None or not str(actual).strip(" \t\n\r\f\v")
        return actual == value

    def exception_summary(self, customer=None, period=None, code=None):
        type(self).summary_calls += 1
        if self.fail_summary:
            raise ledger_app.LedgerUnavailable("fake provenance failure")
        items = [item for item in self.exception_items()
                 if self.matches(item, "customer", customer)
                 and self.matches(item, "period", period)
                 and self.matches(item, "code", code)]
        def groups(key):
            values = {}
            field = "period" if key == "period" else key
            for item in items:
                value = item.get(field)
                status = "UNCLASSIFIED" if value is None or not str(value).strip(" \t\n\r\f\v") else "CLASSIFIED"
                grouped = None if status == "UNCLASSIFIED" else value
                group = values.setdefault(grouped, {field: grouped, "group_status": status,
                    "exception_count": 0, "source_row_count": 0, "trip_source_row_count": 0})
                group["exception_count"] += 1
                group["source_row_count"] += 1
                group["trip_source_row_count"] += item["tab_title"] == "Chuyến hàng"
            return list(values.values())
        return {"exception_count": len(items), "source_row_count": len(items),
                "trip_source_row_count": sum(item["tab_title"] == "Chuyến hàng" for item in items),
                "by_customer": groups("customer"), "by_period": groups("period"),
                "by_code": groups("code")}

    def exception_page(self, customer=None, period=None, code=None, page=1, page_size=50):
        summary = self.exception_summary(customer, period, code)
        items = [item for item in self.exception_items()
                 if self.matches(item, "customer", customer)
                 and self.matches(item, "period", period)
                 and self.matches(item, "code", code)]
        start = (page - 1) * page_size
        selected = items[start:start + page_size]
        return {"page": page, "page_size": page_size, "total_results": len(items),
                "items": [{**item, "customer_group_status": "UNCLASSIFIED" if item.get("customer") is None else "CLASSIFIED",
                           "period_group_status": "UNCLASSIFIED" if not str(item.get("period") or "").strip() else "CLASSIFIED",
                           "customer_group": item.get("customer"), "period_group": item.get("period"),
                           "source_identity": {"capture_id": "fake", "as_of": "2026-10-13",
                                               "sheet_gid": 1, "source_row": item["exception_no"]}}
                          for item in selected]}

    def customer_reconciliations(self, customer=None):
        type(self).reconciliation_calls += 1
        if self.fail_reconciliation:
            raise ledger_app.LedgerUnavailable("fake reconciliation permission failure")
        items = [
            {"customer": "A & B", "reconciliation_status": "MISMATCH",
             "old_book_delta_vnd": 731, "old_book_delta_status": "AVAILABLE"},
            {"customer": "ACME", "reconciliation_status": "MISMATCH",
             "old_book_delta_vnd": 731, "old_book_delta_status": "AVAILABLE"},
            {"customer": "KNOWN", "reconciliation_status": "MATCH",
             "old_book_delta_vnd": 10, "old_book_delta_status": "AVAILABLE"},
            {"customer": "MISSING", "reconciliation_status": "MISMATCH",
             "old_book_delta_vnd": None, "old_book_delta_status": "MISSING"},
            {"customer": "NO-BASELINE", "reconciliation_status": "NO_BASELINE",
             "old_book_delta_vnd": None, "old_book_delta_status": "NO_BASELINE"},
            {"customer": "DUPLICATE", "reconciliation_status": "DUPLICATE_BASELINE",
             "old_book_delta_vnd": 777, "old_book_delta_status": "AVAILABLE"},
            {"customer": "INVALID", "reconciliation_status": "INVALID_BASELINE",
             "old_book_delta_vnd": 888, "old_book_delta_status": "AVAILABLE"},
            {"customer": "NO-EVENTS", "reconciliation_status": "NO_DB_EVENTS",
             "old_book_delta_vnd": None, "old_book_delta_status": "MISSING"},
        ]
        selected = items if customer is None else [item for item in items if item["customer"] == customer]
        return {"items": selected, "total_results": len(selected)}


class LedgerWebTest(unittest.TestCase):
    def setUp(self):
        FakeHistory.fail_summary = False
        FakeHistory.fail_reconciliation = False
        FakeHistory.summary_calls = 0
        FakeHistory.reconciliation_calls = 0
        handler = type("TestLedgerHandler", (ledger_app.LedgerHandler,),
                       {"db": FakeLedger(), "history": FakeHistory(), "port": 0})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        handler.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{handler.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path, method="GET", headers=None):
        try:
            response = urlopen(Request(self.base + path, method=method, headers=headers or {}), timeout=2)
        except HTTPError as exc:
            response = exc
        return response.status, response.read().decode("utf-8")

    def test_dashboard_keeps_one_total_and_customer_period_balance(self):
        status, body = self.request("/?as_of=2026-10-13")
        self.assertEqual(status, 200)
        self.assertIn('class="overview-summary"', body)
        self.assertIn("Tổng còn nợ mọi kỳ", body)
        self.assertIn("1 khách · đến 13/10/2026", body)
        self.assertIn("100 ₫", body)
        self.assertIn("46 kỳ thiếu mốc đối soát", body)
        self.assertNotIn("Dư trước kỳ", body)
        self.assertNotIn("Mở web replay", body)
        self.assertIn("A &amp; B", body)
        self.assertNotIn("A & B", body)

    def test_overview_total_comes_from_full_ledger_not_displayed_rows(self):
        class LimitedOverview(FakeLedger):
            def totals(self, as_of):
                return {**super().totals(as_of), "customers": 2, "balance_vnd": 900}
        body = ledger_app.render_overview(LimitedOverview(), date(2026, 10, 13), "")
        self.assertIn('<strong>900 ₫</strong>', body)
        self.assertIn('2 khách · đến 13/10/2026', body)
        self.assertIn('1 khách</span>', body)

    def test_overview_opens_full_customer_history(self):
        status, body = self.request("/?period=2026-10&as_of=2026-10-13")
        self.assertEqual(status, 200)
        self.assertIn("/customer?name=A+%26+B&amp;as_of=2026-10-13", body)
        self.assertNotIn("first_period=2026-10", body)

    def test_read_only_and_input_bounds(self):
        self.assertEqual(self.request("/", method="POST")[0], 405)
        self.assertEqual(self.request("/", headers={"Host": "wrong.example"})[0], 400)
        self.assertEqual(self.request("/?as_of=2026-10-12")[0], 400)
        self.assertEqual(self.request("/?period=2026-13")[0], 400)
        self.assertEqual(self.request("/customer?name=A%20%26%20B&first_period=bad")[0], 400)
        self.assertEqual(self.request("/period?name=x&period=2026-13")[0], 400)
        self.assertEqual(self.request("/proposal?id=abc")[0], 400)

    def test_overview_keeps_global_total_and_renders_all_251_customers(self):
        class LargeLedger(FakeLedger):
            def overview(self, as_of, period, search=""):
                return [{"customer": f"customer-{number:03}", "carried_vnd": 0,
                         "period_opening_vnd": 0, "period_movement_vnd": 0,
                         "period_balance_vnd": 0, "total_balance_vnd": 0,
                         "comparison_status": "MATCH"}
                        for number in range(1, 252)]

        self.server.RequestHandlerClass.db = LargeLedger()
        status, body = self.request("/?q=limited&as_of=2026-10-13")
        self.assertEqual(status, 200)
        self.assertIn("Tổng còn nợ mọi kỳ", body)
        self.assertIn("100 ₫", body)
        self.assertIn("251 khách</span>", body)
        self.assertIn("customer-251", body)
        self.assertEqual(FakeHistory.summary_calls, 2)
        self.assertEqual(FakeHistory.reconciliation_calls, 1)

    def test_source_exceptions_filter_page_total_and_encoded_source_link(self):
        status, body = self.request("/exceptions")
        self.assertEqual(status, 200)
        self.assertIn("53 kết quả · 50 mỗi trang", body)
        self.assertIn('label for="customer_mode"', body)
        self.assertIn('label for="customer"', body)
        self.assertIn("MISSING_TOTAL", body)
        self.assertIn("Tổng nguồn thiếu: 1 ngoại lệ", body)
        self.assertIn("Tổng nguồn bằng 0: 1 ngoại lệ", body)
        self.assertIn("1.472 ₫ từ 3 khách", body)
        self.assertNotIn("3.137 ₫", body)
        self.assertNotIn("1.665 ₫", body)  # Invalid and duplicate baselines do not enter known total.
        status, second_page = self.request("/exceptions?page=2")
        self.assertEqual(status, 200)
        self.assertIn("source period with whitespace", second_page)
        self.assertNotIn('href="javascript:alert(1)"', body)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", body)
        self.assertIn("<td>Chưa phân loại</td><td>open</td>", body)
        self.assertIn("https://docs.google.com/spreadsheets/d/fake/edit#gid=3&amp;range=A4", body)
        self.assertIn("page=2", body)

        filtered = ("/exceptions?customer_mode=exact&customer=ACME&period_mode=exact"
                    "&period=2026-10&code_mode=all&page=2")
        status, body = self.request(filtered)
        self.assertEqual(status, 200)
        self.assertIn("ACME", body)
        self.assertIn("period=2026-10", body)
        self.assertIn("code_mode=all", body)
        self.assertIn("← Trước", body)

    def test_exception_summary_failure_returns_clear_503(self):
        FakeHistory.fail_summary = True
        status, body = self.request("/exceptions")
        self.assertEqual(status, 503)
        self.assertIn("Chưa kiểm được ngoại lệ nguồn", body)

    def test_missing_and_zero_totals_show_at_global_customer_and_period_scopes(self):
        class AcmeLedger(FakeLedger):
            def customers(self, as_of, search=""):
                return [{"customer": "ACME", "opening_vnd": 100, "movement_vnd": 0,
                         "balance_vnd": 100, "periods": 1, "no_baseline": 0}]

        self.server.RequestHandlerClass.db = AcmeLedger()
        for path in ("/?period=2026-10", "/customer?name=ACME",
                     "/period?name=ACME&period=2026-10"):
            with self.subTest(path=path):
                status, body = self.request(path)
                self.assertEqual(status, 200)
                self.assertIn("Tổng nguồn thiếu: 1 ngoại lệ", body)
                self.assertIn("Tổng nguồn bằng 0: 1 ngoại lệ", body)

    def test_access_log_drops_customer_and_source_values(self):
        output = io.StringIO()
        with redirect_stderr(output):
            status, _ = self.request("/?q=PRIVATE-CUSTOMER&source_url=PRIVATE-SOURCE")
        self.assertEqual(status, 200)
        self.assertEqual(output.getvalue(), "")

    def test_unclassified_and_whitespace_source_period_filters_are_distinct(self):
        status, unclassified = self.request(
            "/exceptions?customer_mode=unclassified&period_mode=all&code_mode=all")
        self.assertEqual(status, 200)
        self.assertIn("1 kết quả · 50 mỗi trang", unclassified)
        self.assertIn("Chưa phân loại", unclassified)
        self.assertNotIn("fake A1", unclassified)

        status, whitespace_period = self.request(
            "/exceptions?customer_mode=all&period_mode=exact&period=+2026-10&code_mode=all")
        self.assertEqual(status, 200)
        self.assertIn("1 kết quả · 50 mỗi trang", whitespace_period)
        self.assertIn("source period with whitespace", whitespace_period)

        self.assertEqual(self.request("/exceptions?period_mode=exact&period=2026-13")[0], 200)
        self.assertEqual(self.request("/exceptions?customer_mode=all&customer=%00")[0], 400)
        self.assertEqual(self.request("/exceptions?code=" + "x" * 251)[0], 400)
        self.assertEqual(self.request("/exceptions?page=0")[0], 400)

    def test_history_failure_keeps_readable_balance_and_marks_source_unknown(self):
        FakeHistory.fail_summary = True
        status, body = self.request("/?as_of=2026-10-13")
        self.assertEqual(status, 200)
        self.assertIn("Tổng còn nợ mọi kỳ", body)
        self.assertIn("100 ₫", body)
        self.assertIn("Chưa kiểm được ngoại lệ nguồn", body)
        self.assertNotIn("0 ngoại lệ", body)

        FakeHistory.fail_summary = False
        FakeHistory.fail_reconciliation = True
        status, body = self.request("/customer?name=A%20%26%20B&as_of=2026-10-13")
        self.assertEqual(status, 200)
        self.assertIn("Tổng còn nợ", body)
        self.assertIn("Chưa kiểm được ngoại lệ nguồn", body)

        FakeHistory.fail_reconciliation = False
        status, body = self.request("/exceptions")
        self.assertEqual(status, 200)

    def test_period_null_zero_and_new_period_render_differently(self):
        class UnknownOpeningLedger(FakeLedger):
            def period(self, as_of, customer, period):
                return [{"customer": customer, "debt_period": period, "opening_vnd": None,
                         "movement_vnd": 50, "balance_vnd": 50,
                         "comparison_status": None, "replay_event_count": None}]

        self.server.RequestHandlerClass.db = UnknownOpeningLedger()
        status, body = self.request("/period?name=A%20%26%20B&period=2026-11&as_of=2026-10-15")
        self.assertEqual(status, 200)
        self.assertIn("Số mở sổ kỳ —", body)
        self.assertIn("Kỳ mới chưa có số mở sổ lịch sử", body)
        self.assertIn("không phải 0", body)
        self.assertIn("— dòng lịch sử", body)

        class ZeroOpeningLedger(FakeLedger):
            def period(self, as_of, customer, period):
                return [{"customer": customer, "debt_period": period, "opening_vnd": 0,
                         "movement_vnd": 0, "balance_vnd": 0,
                         "comparison_status": "MATCH", "replay_event_count": 0}]

        self.server.RequestHandlerClass.db = ZeroOpeningLedger()
        status, body = self.request("/period?name=A%20%26%20B&period=2026-10&as_of=2026-10-15")
        self.assertEqual(status, 200)
        self.assertIn("Số mở sổ kỳ 0 ₫", body)
        self.assertNotIn("Kỳ mới chưa có số mở sổ lịch sử", body)

    def test_customer_null_opening_never_compares_replay_to_zero(self):
        class NewPeriodLedger(FakeLedger):
            def periods(self, as_of, customer):
                return [{"customer": customer, "debt_period": "2026-11", "opening_vnd": None,
                         "movement_vnd": 50, "balance_vnd": 50, "comparison_status": None,
                         "replay_event_count": None}]

        self.server.RequestHandlerClass.db = NewPeriodLedger()
        status, body = self.request("/customer?name=A%20%26%20B&as_of=2026-10-15")
        self.assertEqual(status, 200)
        self.assertIn("Kỳ mới không có số mở sổ lịch sử", body)
        self.assertIn("Số mở sổ kỳ —", body)
        self.assertIn("Bút toán mới 50 ₫", body)
        self.assertNotIn("0 ₫ mở sổ kỳ", body)
        self.assertIn("Thiếu chi tiết", body)

    def test_wrong_cutover_still_blocks_normal_ledger_page(self):
        self.server.RequestHandlerClass.db.invalid_cutover = True
        status, body = self.request("/?as_of=2026-10-13")
        self.assertEqual(status, 503)
        self.assertIn("Chưa đọc được sổ PostgreSQL", body)

    def test_health_checks_opening_history_and_current_delta(self):
        status, body = self.request("/health")
        payload = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("fake test fixture", payload["data_scope"])
        self.assertEqual(payload["components"]["history_exception_summary"], "ok")
        self.assertEqual(payload["components"]["history_customer_reconciliation"], "ok")

        db = self.server.RequestHandlerClass.db
        db.no_baseline = 45
        status, body = self.request("/health")
        payload = json.loads(body)
        self.assertEqual(status, 503)
        self.assertEqual(payload["components"]["no_baseline"], "invalid")
        db.no_baseline = 46
        db.balance_vnd = 900000
        status, body = self.request("/health")
        self.assertEqual(status, 200)  # New postings may change current balance.

        FakeHistory.fail_reconciliation = True
        status, body = self.request("/health")
        payload = json.loads(body)
        self.assertEqual(status, 503)
        self.assertEqual(payload["components"]["history_customer_reconciliation"], "unavailable")
        self.assertEqual(payload["components"]["opening_vnd"], "ok")

    def test_health_refreshes_cutover_before_constructing_history_api(self):
        handler = self.server.RequestHandlerClass
        handler.db.source_workbook_sha256 = "c" * 64
        handler.history = ledger_app.HistoryDB()  # No cached cutover metadata.
        observed = []

        def checked_summary(self, customer=None, period=None, code=None):
            observed.append(self.expected_cutover["source_workbook_sha256"])
            raise ledger_app.LedgerUnavailable("history hash mismatch")

        with patch.object(ledger_app.HistoryDB, "exception_summary", checked_summary), \
             patch.object(ledger_app.HistoryDB, "customer_reconciliations", lambda self, customer=None: {}):
            status, body = self.request("/health")
        payload = json.loads(body)
        self.assertEqual(status, 503)
        self.assertEqual(observed, ["c" * 64])
        self.assertEqual(payload["components"]["history_provenance"], "unavailable")

    def test_health_uses_historydb_transport_and_rejects_stale_or_missing_hashes(self):
        handler = self.server.RequestHandlerClass
        handler.history = ledger_app.HistoryDB()
        bad_hashes = (
            ("stale workbook", "c" * 64, "b" * 64),
            ("stale engine", "a" * 64, "d" * 64),
            ("missing workbook", None, "b" * 64),
            ("missing engine", "a" * 64, None),
        )
        for label, workbook_hash, engine_hash in bad_hashes:
            with self.subTest(label=label):
                observed = []

                def patched_rows(history, sql, **values):
                    self.assertIn("FROM pilot.m1_provenance", sql)
                    observed.append((history.expected_cutover.copy(), values))
                    return [{"capture_id": ledger_app.CAPTURE,
                             "as_of": ledger_app.OPENING_DATE.isoformat(),
                             "source_workbook_sha256": workbook_hash,
                             "engine_sha256": engine_hash,
                             "baseline_date": ledger_app.OPENING_DATE.isoformat()}]

                with patch.object(ledger_app.HistoryDB, "rows", patched_rows):
                    status, body = self.request("/health")
                payload = json.loads(body)
                self.assertEqual(status, 503)
                self.assertTrue(payload["ok"] is False)
                self.assertEqual(payload["components"]["cutover"], "ok")
                self.assertEqual(payload["components"]["history_exception_summary"], "unavailable")
                self.assertEqual(payload["components"]["history_customer_reconciliation"], "unavailable")
                self.assertEqual(payload["components"]["history_provenance"], "unavailable")
                self.assertEqual(len(observed), 2)
                self.assertTrue(all(row[0]["source_workbook_sha256"] == "a" * 64
                                    and row[0]["engine_sha256"] == "b" * 64
                                    for row in observed))

    def test_health_missing_ledger_cutover_hash_returns_component_503(self):
        handler = self.server.RequestHandlerClass
        handler.db.cutover = lambda: [{"capture_id": ledger_app.CAPTURE,
                                       "as_of": ledger_app.OPENING_DATE.isoformat()}]
        handler.history = ledger_app.HistoryDB()
        with patch.object(ledger_app.HistoryDB, "rows",
                          side_effect=AssertionError("history transport must not run")) as rows:
            status, body = self.request("/health")
        payload = json.loads(body)
        self.assertEqual(status, 503)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["components"]["cutover"], "invalid")
        self.assertEqual(payload["components"]["history_provenance"], "unavailable")
        rows.assert_not_called()

    def test_health_rejects_each_opening_invariant_from_one_constant(self):
        self.assertEqual(ledger_app.OPENING_INVARIANTS,
                         {"opening_periods": 496, "opening_vnd": 65051673578, "no_baseline": 46})
        status, payload = ledger_app.health_payload(FakeLedger(), FakeHistory(), date(2026, 10, 16))
        self.assertEqual(status, 200)
        for key, expected in ledger_app.OPENING_INVARIANTS.items():
            with self.subTest(invariant=key):
                wrong = type("Wrong", (FakeLedger,), {key: expected + 1})()
                status, payload = ledger_app.health_payload(wrong, FakeHistory(), date(2026, 10, 16))
                self.assertEqual(status, 503)
                self.assertEqual(payload["components"][key], "invalid")
                self.assertFalse(ledger_app.opening_validation(wrong, date(2026, 10, 16))["ok"])

    def test_startup_and_health_share_opening_validation(self):
        calls = []
        original = ledger_app.opening_validation

        def record(db, as_of):
            calls.append((db, as_of))
            return original(db, as_of)

        class Server:
            def __init__(self, address, handler):
                self.address, self.handler = address, handler

            def serve_forever(self):
                return None

        with patch.object(ledger_app, "opening_validation", side_effect=record), \
             patch.object(ledger_app, "LedgerDB", return_value=FakeLedger()), \
             patch.object(ledger_app, "ThreadingHTTPServer", Server), \
             patch.dict("os.environ", {"WEBDEBIT_LEDGER_PORT": "8876"}), \
             redirect_stderr(io.StringIO()):
            ledger_app.main()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], ledger_app.today())

    def test_known_old_book_total_excludes_missing_and_invalid_baselines(self):
        text = ledger_app.reconciliation_overview(
            FakeHistory().customer_reconciliations()["items"])
        self.assertIn("1.472 ₫ từ 3 khách", text)
        self.assertIn("2 khách thiếu chênh lệch", text)
        self.assertIn("1 NO_BASELINE", text)
        self.assertIn("2 mốc trùng/không hợp lệ", text)
        self.assertNotIn("2.406 ₫", text)

    def test_web_source_urls_allow_only_http_schemes(self):
        self.assertIsNone(ledger_app.web_source_url("javascript:alert(1)"))
        self.assertIsNone(ledger_app.web_source_url("file:///tmp/source"))
        self.assertIsNone(ledger_app.web_source_url("https://user:pass@example.test/source"))
        self.assertEqual(ledger_app.web_source_url("https://example.test/source"),
                         "https://example.test/source")

    def test_period_does_not_treat_pending_as_movement(self):
        status, body = self.request("/period?name=A%20%26%20B&period=2026-10")
        self.assertEqual(status, 200)
        self.assertIn("Thiếu mốc đối soát", body)
        self.assertIn("A &amp; B", body)
        self.assertIn("Chưa có bút toán sau mở sổ", body)
        self.assertIn('class="period-explanation period-page-explanation"', body)
        self.assertNotIn("25 ₫", body)

    def test_customer_separates_debt_and_receipts_without_overflow_table(self):
        status, body = self.request("/customer?name=A%20%26%20B")
        self.assertEqual(status, 200)
        self.assertIn("Phát sinh nợ", body)
        self.assertIn("Đã thu / giảm trừ", body)
        self.assertIn("ABCU1234567", body)
        self.assertNotIn('class="book-table"', body)
        self.assertIn('class="row-details"', body)
        self.assertIn("Cách tính và nguồn số dư", body)
        self.assertNotIn('class="month-total"', body)
        self.assertIn("150 ₫", body)
        self.assertIn("50 ₫", body)
        self.assertIn("1 khoản chờ duyệt", body)
        self.assertIn('name="name" required', body)
        self.assertIn('<summary>Đổi khách hoặc lọc tháng</summary>', body)
        self.assertIn("100 ₫", body)
        self.assertNotIn("Chi tiết hiển thị chưa đối chiếu đủ", body)

    def test_customer_shows_active_month_filter(self):
        status, body = self.request("/customer?name=A%20%26%20B&first_period=2026-10")
        self.assertEqual(status, 200)
        self.assertIn("Từ tháng 10/2026 · Đổi khách / lọc tháng", body)
        self.assertIn("Bỏ lọc tháng", body)

    def test_incomplete_replay_does_not_show_false_running_balance(self):
        class MissingHistory(FakeHistory):
            def events_for_customer(self, *args, **kwargs):
                return super().events_for_customer(*args, **kwargs)[:1]
        self.server.RequestHandlerClass.history = MissingHistory()
        status, body = self.request("/customer?name=A%20%26%20B")
        self.assertEqual(status, 200)
        self.assertIn("Chi tiết hiển thị chưa đối chiếu đủ", body)
        self.assertIn('class="badge alert">Thiếu chi tiết', body)
        self.assertIn("Phát sinh nợ <b>—</b>", body)
        self.assertIn("Còn nợ kỳ 100 ₫", body)

    def test_more_receipts_than_trips_keep_independent_rows(self):
        events = FakeHistory().events_for_customer(None, None)
        second_receipt = dict(events[1], event_no=3, amount_vnd=10,
                              signed_amount_vnd=-10, kind="offset", source_row=8)
        rows, charges, payments, ending = ledger_app.month_rows(
            events + [second_receipt], [], 25)
        self.assertEqual((charges, payments, ending), (150, 60, 115))
        self.assertEqual(rows.count('class="history-row"'), 3)
        self.assertIn("Cấn trừ", rows)
        self.assertNotIn("115 ₫", rows)

    def test_only_latest_month_starts_open(self):
        class TwoPeriodLedger(FakeLedger):
            def periods(self, as_of, customer):
                return [*super().periods(as_of, customer),
                        {"customer": customer, "debt_period": "2026-09", "opening_vnd": 0,
                         "movement_vnd": 0, "balance_vnd": 0, "comparison_status": "MATCH",
                         "replay_event_count": 0}]
        body = ledger_app.render_customer(TwoPeriodLedger(), date(2026, 10, 13),
                                          "A & B", history=FakeHistory())
        self.assertLess(body.index('id="period-2026-10" open'), body.index('id="period-2026-09"'))
        self.assertNotIn('id="period-2026-09" open', body)

    def test_review_label_stays_visible_when_price_is_unclear(self):
        event = dict(FakeHistory().events_for_customer(None, None)[0])
        event["source_values"] = [*event["source_values"]]
        event["source_values"][10] = "chưa có giá"
        body, *_ = ledger_app.month_rows([event], [], 0)
        self.assertIn('<span class="badge warn">CẦN KT</span>', body)
        self.assertIn("Dòng nguồn", body)

    def test_proposal_keeps_evidence_in_a_separate_detail(self):
        class ProposalLedger:
            def proposal(self, proposal_id):
                return [{"status": "pending", "kind": "receipt", "total_vnd": 100,
                         "event_date": "2026-10-14", "posting_date": "2026-10-14",
                         "maker": "maker", "checker": None, "source_ref": "bank-row-1",
                         "evidence_ref": "slip-1", "reason": "customer payment"}]

            def proposal_lines(self, proposal_id):
                return [{"customer": "A & B", "debt_period": "2026-10", "amount_vnd": 100}]

            def proposal_audit(self, proposal_id):
                return [{"at": "2026-10-14", "actor": "maker", "action": "created"}]

        body = ledger_app.render_proposal(ProposalLedger(), 7)
        self.assertIn("Phiếu #7", body)
        self.assertIn("Phân bổ theo kỳ", body)
        self.assertIn('<details class="panel proposal-details"><summary>Thông tin và bằng chứng', body)
        self.assertIn("bank-row-1", body)
        self.assertIn("slip-1", body)
        self.assertIn("Nhật ký xử lý", body)

    def test_unknown_historical_price_is_not_zero(self):
        self.assertEqual(ledger_app.source_vnd(None), "—")
        self.assertEqual(ledger_app.source_vnd("chưa có giá"), "CẦN KT")


if __name__ == "__main__":
    unittest.main()
