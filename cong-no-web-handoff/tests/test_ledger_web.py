"""Focused checks for the ledger read surface and maker input guard."""

from __future__ import annotations

import sys
import threading
import unittest
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import ledger_app  # noqa: E402


class FakeLedger:
    def cutover(self):
        return [{"capture_id": ledger_app.CAPTURE, "as_of": "2026-10-13"}]

    def totals(self, as_of):
        return {"customers": 1, "opening_periods": 1, "no_baseline": 1,
                "opening_vnd": 100, "movement_vnd": 0,
                "balance_vnd": 100, "pending": 1, "postings": 0}

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


class LedgerWebTest(unittest.TestCase):
    def setUp(self):
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
        self.assertIn("1 kỳ thiếu mốc đối soát", body)
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
