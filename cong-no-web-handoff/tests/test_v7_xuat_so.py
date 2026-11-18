"""Bản xuất cả sổ (XUAT-SO-01, specs/v7-xuat-ca-so.md): bảy tab, ô trống giữ trống, tự kiểm và các ca cố ý lệch, route API.

Không cần DB: kết quả giả cùng hình dạng `get_ledger`, `get_dashboard`, `get_dashboard_debt`, `list_customers`, `get_fee_types`.
Harness PostgreSQL thật ở tools/test_pg_v7_xuat_so.py. Tên khách, số tiền đều giả.
"""

import copy
import datetime as dt
import http.client
import io
import json
import sys
import threading
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_book_export as export_module  # noqa: E402
import v7_ledger_api as api  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402
from v7_xlsx_writer import Month, read_workbook  # noqa: E402

NOW = dt.datetime(2026, 11, 18, 10, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
TABS = ["KIỂM", "TỔNG", "THÁNG", "CHUYẾN", "PHIẾU THU", "PHÂN BỔ THU", "ĐIỀU CHỈNH"]


def month_row(month, prior, charges, received, outstanding):
    return {"month": month, "outstanding_vnd": str(outstanding), "end_of_month_vnd": str(prior + charges - received),
            "prior_months_vnd": str(prior), "charges_vnd": str(charges), "received_vnd": str(received)}


def ledger(book, months, **parts):
    body = {"status": "active", "customer_id": book, "fee_columns": [], "today_month": "2026-11-01", "month_locks": [],
            "version": 3, "months": months, "pending_count": 0, "trips": [], "adjustments": [], "receipts": [], "opening": [],
            "source_exceptions": [], "legacy_rows": [], "outgoing_offsets": []}
    body.update(parts)
    body["total_outstanding_vnd"] = str(sum(int(m["outstanding_vnd"]) for m in months))
    return body


def line(line_id, month, amount, kind="debt", superseded=None):
    return {"id": line_id, "month": month, "kind": kind, "amount_vnd": str(amount), "superseded_by_event": superseded}


def world():
    """Bốn sổ giả: 7 còn nợ (đủ loại dòng), 9 khách dư, 11 chưa có số dư đầu, 12 hết nợ."""
    trips = [
        {"id": 501, "month": "2026-11-01", "event_date": "2026-11-03", "container": "TEST0000001", "carrier": "HÃNG A",
         "shipper": "SHIPPER A", "status": "confirmed", "booking": "BK-01", "origin": "KHO A", "destination": "CẢNG B",
         "note": "chuyến thử", "unit_price_vnd": "200000", "other_fee_vnd": "50000", "amount_vnd": "250000",
         "fee_lines": [{"id": 1, "fee_type_id": 1, "amount_vnd": "30000", "note": None},
                       {"id": 2, "fee_type_id": 2, "amount_vnd": "20000", "note": "2 ngày"}],
         "is_fee_only": False, "is_missing_price": False},
        {"id": 502, "month": "2026-11-01", "event_date": "2026-11-04", "container": "TEST0000002", "status": "confirmed",
         "unit_price_vnd": None, "other_fee_vnd": None, "amount_vnd": None, "fee_lines": [], "is_missing_price": True},
        {"id": 503, "month": "2026-11-01", "event_date": None, "container": "TEST0000003", "status": "pending_review",
         "unit_price_vnd": None, "other_fee_vnd": None, "amount_vnd": None, "fee_lines": [], "is_missing_price": True},
    ]
    legacy = [
        {"id": 901, "month": "2026-09-01", "kind": "trip", "display": {"note": "sổ gốc"}, "source_total_vnd": "500000",
         "fee_lines": [{"id": 3, "fee_type_id": 1, "amount_vnd": "100000", "note": None}],
         "current": {"event_date": "2026-09-12", "container": "TEST0000009", "carrier": "HÃNG B", "shipper": None,
                     "origin": "KHO C", "destination": "CẢNG D", "unit_price_vnd": "400000", "other_fee_vnd": "100000",
                     "counted_vnd": "500000", "deleted": False}},
        {"id": 902, "month": "2026-10-01", "kind": "trip", "display": {}, "source_total_vnd": "300000", "fee_lines": [],
         "current": {"event_date": "2026-10-02", "container": "", "unit_price_vnd": None, "other_fee_vnd": None,
                     "counted_vnd": "300000", "deleted": False}},
        {"id": 903, "month": "2026-10-01", "kind": "trip", "display": {}, "source_total_vnd": None, "fee_lines": [],
         "current": {"event_date": None, "container": "TEST0000010", "unit_price_vnd": None, "other_fee_vnd": None,
                     "counted_vnd": "0", "deleted": False}},
        {"id": 904, "month": "2026-10-01", "kind": "receipt", "source_total_vnd": "150000", "fee_lines": [], "current": None,
         "display": {"date": "2026-10-03", "raw_date": "3/10 ck", "note": "ck ngân hàng"}},
    ]
    receipts = [
        {"id": 41, "pid": "PT-0001", "date": "2026-10-10", "method": "CK", "reference": "UNC 1", "amount_vnd": "600000",
         "void_reason": None, "voided_on": None, "counterparty_name": None,
         "allocations": [line(1, "2026-09-01", 500000), line(2, "2026-10-01", 100000),
                         line(3, "2026-10-01", 600000, superseded=77)]},
        {"id": 42, "pid": "PT-0002", "date": "2026-11-05", "method": "TM", "reference": None, "amount_vnd": "100000",
         "void_reason": None, "voided_on": None, "counterparty_name": None, "allocations": [line(4, "2026-10-01", 100000)]},
        {"id": 43, "pid": "PT-0003", "date": "2026-11-06", "method": "CK", "reference": None, "amount_vnd": "70000",
         "void_reason": "Nhập nhầm", "voided_on": "2026-11-06", "counterparty_name": None,
         "allocations": [line(5, "2026-11-01", 70000, superseded=80)]},
    ]
    books = {
        7: ledger(7, [month_row("2026-09-01", 0, 500000, 0, 0), month_row("2026-10-01", 500000, 300000, 600000, 100000),
                      month_row("2026-11-01", 200000, 250000, 100000, 250000)],
                  trips=trips, legacy_rows=legacy, receipts=receipts, pending_count=3,
                  opening=[{"id": 1, "month": "2026-09-01", "amount_vnd": "500000", "editable": False}],
                  month_locks=[{"month": "2026-09-01", "locked": True}, {"month": "2026-11-01", "locked": False}],
                  outgoing_offsets=[{"offset_pair_id": 61, "pid": "CT-0001", "date": "2026-11-07", "method": "CẤN TRỪ",
                                     "amount_vnd": "-20000", "void_reason": None, "voided_by_event": None,
                                     "counterparty_name": "Khách Chín Rồng"}],
                  adjustments=[{"id": 81, "month": "2026-10-01", "trip_id": None, "legacy_row_id": None, "amount_vnd": "-5000",
                                "note": "làm tròn", "at": "2026-10-31T23:30:00+07:00"},
                               {"id": 82, "month": "2026-09-01", "trip_id": None, "legacy_row_id": 901, "amount_vnd": "10000",
                                "note": None, "at": "2026-11-01T01:00:00+00:00"},
                               {"id": 83, "month": "2026-11-01", "trip_id": 501, "legacy_row_id": None, "amount_vnd": "3000",
                                "note": "phí thêm", "at": "2026-11-08T08:00:00+07:00"}]),
        9: ledger(9, [month_row("2026-10-01", 0, 100000, 150000, -50000)]),
        11: {"status": "NO_BASELINE", "customer_id": 11, "fee_columns": [], "version": 1, "months": [],
             "source_exceptions": [], "total_outstanding_vnd": None},
        12: ledger(12, [month_row("2026-08-01", 0, 80000, 80000, 0)]),
    }
    return {
        "get_dashboard": {"as_of": "2026-11-18", "receivable": {"total_vnd": "350000", "customers": 1},
                          "credit": {"total_vnd": "-50000", "customers": 1},
                          "todo": {"credit": [{"customer_id": 9, "name": "Khách Chín Rồng", "credit_vnd": "-50000"}]}},
        "get_dashboard_debt": {"receivable_vnd": "350000", "customers": [{"customer_id": 7, "outstanding_vnd": "350000"}]},
        "list_customers": {"customers": [
            {"id": 7, "name": "Khách Ba Sao", "status": "active", "commodity": "Sầu riêng", "transport_mode": "CANG"},
            {"id": 9, "name": "Khách Chín Rồng", "status": "active", "commodity": None, "transport_mode": "BO"},
            {"id": 11, "name": "Khách Mới", "status": "NO_BASELINE", "commodity": None, "transport_mode": None},
            {"id": 12, "name": "Khách Mười Hai", "status": "active", "commodity": None, "transport_mode": None}]},
        "get_fee_types": {"fee_types": [{"id": 1, "name": "Nâng hạ"}, {"id": 2, "name": "Lưu bãi"}]},
        "ledgers": books,
    }


class FakeDb:
    """`run` cho danh sách sổ lấy trước; `run_snapshot` trả lần lượt kết quả như adapter, ghi lại lệnh gọi."""

    def __init__(self, data, *, listings=None, fail_end=False):
        self.data, self.listings, self.fail_end, self.calls = data, list(listings or []), fail_end, []

    def run(self, function, payload, actor, *, read_only=False):
        self.calls.append(("run", function, read_only))
        return copy.deepcopy(self.listings.pop(0) if self.listings else self.data[function])

    def run_snapshot(self, calls, actor):
        self.calls.append(("snapshot", [function for function, _ in calls], [payload for _, payload in calls]))

        def results():
            for function, payload in calls:
                if function == "get_ledger_export":
                    yield copy.deepcopy(self.data["ledgers"][payload["customer_id"]])
                else:
                    yield copy.deepcopy(self.data[function])
            if self.fail_end:
                raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        return results()


def names(listing):
    return {**listing, "customers": [{**row, "display_name": "BA SAO (HN)"} if row["id"] == 7 else row
                                     for row in listing["customers"]]}


def run_export(data=None, **db):
    return export_module.export(FakeDb(data or world(), **db), "nguoi-thu@example.test", NOW, names=names)


def rows_of(result, tab, book=None):
    rows = read_workbook(result.data)[tab][1:]
    return [row for row in rows if book is None or row[0] == book]


class ExportTest(unittest.TestCase):
    def test_clean_export_has_seven_tabs_and_passes(self):
        result = run_export()
        self.assertTrue(result.ok)
        self.assertEqual(result.filename, "so-web-20261118-1030.xlsx")
        self.assertEqual(json.loads(result.header()), {"ok": True, "books": 4, "problems": []})
        book = read_workbook(result.data)
        self.assertEqual(list(book), TABS)
        guide = book["KIỂM"]
        self.assertEqual(guide[1][:2], ["Kết quả tự kiểm", "KHỚP"])
        self.assertIn(["Số sổ", 4, "3 sổ đang dùng, 1 sổ chưa có số dư đầu"], guide)
        self.assertIn(["Còn phải thu (Tổng quan)", 350000, "1 khách còn nợ"], guide)
        self.assertIn(["Tổng các sổ (nợ trừ dư)", 300000], guide)
        self.assertEqual([row[1] for row in guide if len(row) > 1 and row[1] in ("ĐẠT", "LỆCH")], ["ĐẠT"] * 6)

    def test_reads_everything_in_one_snapshot(self):
        db = FakeDb(world())
        export_module.export(db, "a", NOW)
        self.assertEqual(db.calls[0], ("run", "list_customers", True))
        kind, functions, payloads = db.calls[1]
        self.assertEqual((kind, len(db.calls)), ("snapshot", 2))
        self.assertEqual(functions, ["get_dashboard", "get_dashboard_debt", "list_customers", "get_fee_types"]
                         + ["get_ledger_export"] * 4)
        self.assertEqual(payloads[4:], [{"customer_id": book} for book in (7, 9, 11, 12)])

    def test_summary_and_month_rows(self):
        result = run_export()
        self.assertEqual(rows_of(result, "TỔNG"), [
            [7, "Khách Ba Sao", "BA SAO (HN)", "Đang dùng", "Sầu riêng", "cảng", 350000, Month(2026, 10, 1), 3],
            [9, "Khách Chín Rồng", None, "Đang dùng", None, "bộ", -50000, None, 0],
            [11, "Khách Mới", None, "Chưa có số dư đầu"],
            [12, "Khách Mười Hai", None, "Đang dùng", None, None, 0, None, 0]])
        self.assertEqual(rows_of(result, "THÁNG", 7), [
            [7, "Khách Ba Sao", Month(2026, 9, 1), 0, 500000, 0, 500000, 0, 500000, "Khóa"],
            [7, "Khách Ba Sao", Month(2026, 10, 1), 500000, 300000, 600000, 200000, 100000, None, "Khóa"],
            [7, "Khách Ba Sao", Month(2026, 11, 1), 200000, 250000, 100000, 350000, 250000, None, "Mở"]])

    def test_trip_rows_keep_blank_prices_blank(self):
        trips = rows_of(result := run_export(), "CHUYẾN", 7)
        self.assertEqual(trips[0], [7, "Khách Ba Sao", "web", 501, Month(2026, 11, 1), dt.date(2026, 11, 3), "TEST0000001",
                                    "BK-01", "HÃNG A", "SHIPPER A", "KHO A", "CẢNG B", 200000, 50000, 250000, None,
                                    "Tính tiền", "Nâng hạ: 30.000; Lưu bãi (2 ngày): 20.000", "chuyến thử"])
        missing = trips[1]
        self.assertEqual((missing[12:17]), [None, None, None, "chưa giá", "Tính tiền"])
        self.assertEqual(trips[2][16], "Chờ kiểm")
        self.assertEqual(trips[3][2:4] + trips[3][12:17], ["sổ gốc", 901, 400000, 100000, 500000, None, "Tính tiền"])
        self.assertEqual(trips[4][12:16], [None, None, 300000, None])      # khoán không đơn giá: vẫn có thành tiền
        self.assertEqual(trips[5][12:16], [None, None, None, "chưa giá"])  # chưa đơn giá và 0: trống, không 0
        self.assertEqual(len(rows_of(result, "CHUYẾN")), 6)

    def test_receipts_allocations_and_adjustments(self):
        result = run_export()
        receipts = rows_of(result, "PHIẾU THU", 7)
        self.assertEqual(receipts[0][2:], ["web", "PT-0001", 41, dt.date(2026, 10, 10), "CK", "UNC 1", 600000, None, None,
                                           "09/2026, 10/2026"])
        self.assertEqual(receipts[2][2:10], ["web", "PT-0003", 43, dt.date(2026, 11, 6), "CK", None, 70000, "Đã hủy: Nhập nhầm"])
        self.assertEqual(receipts[3][2:], ["sổ gốc", None, 904, dt.date(2026, 10, 3), None, "3/10 ck · ck ngân hàng", 150000,
                                           None, None, "10/2026"])
        self.assertEqual(receipts[4][2:11], ["cấn trừ đi", "CT-0001", 61, dt.date(2026, 11, 7), "CẤN TRỪ", None, -20000, None,
                                             "Khách Chín Rồng"])
        self.assertEqual([row[2:] for row in rows_of(result, "PHÂN BỔ THU", 7)], [
            ["PT-0001", 41, dt.date(2026, 10, 10), Month(2026, 9, 1), "nợ", 500000],
            ["PT-0001", 41, dt.date(2026, 10, 10), Month(2026, 10, 1), "nợ", 100000],
            ["PT-0002", 42, dt.date(2026, 11, 5), Month(2026, 10, 1), "nợ", 100000]])
        self.assertEqual([row[2:] for row in rows_of(result, "ĐIỀU CHỈNH", 7)], [
            [81, Month(2026, 10, 1), -5000, "cả tháng", "làm tròn", dt.date(2026, 10, 31)],
            [82, Month(2026, 9, 1), 10000, "dòng sổ gốc 901", None, dt.date(2026, 11, 1)],   # 01:00 UTC là 08:00 giờ VN
            [83, Month(2026, 11, 1), 3000, "chuyến 501", "phí thêm", dt.date(2026, 11, 8)]])

    def test_demo_prefix_and_snapshot_error_raises(self):
        self.assertTrue(export_module.export(FakeDb(world()), "a", NOW, prefix="so-web-du-lieu-gia").filename
                        .startswith("so-web-du-lieu-gia-20261118"))
        with self.assertRaises(ApiError) as caught:
            run_export(fail_end=True)
        self.assertEqual(caught.exception.code, "DB_UNAVAILABLE")

    def test_book_list_changed_between_reads(self):
        """Sổ vừa tạo giữa lần lấy danh sách và giao dịch: đọc lại cả lượt một lần; vẫn đổi thì báo lỗi, không xuất thiếu sổ."""
        first = {"customers": world()["list_customers"]["customers"][:2]}
        db = FakeDb(world(), listings=[first])
        result = export_module.export(db, "a", NOW)
        self.assertEqual((result.ok, result.books), (True, 4))
        self.assertEqual([call[0] for call in db.calls], ["run", "snapshot", "snapshot"])
        with patch.object(export_module, "_build", side_effect=export_module._ListChanged([7])),                 self.assertRaises(ApiError) as caught:
            export_module.export(FakeDb(world()), "a", NOW)
        self.assertEqual(caught.exception.status, 503)


class MismatchTest(unittest.TestCase):
    """Mỗi ca cố ý lệch phải làm tự kiểm báo đỏ đúng mã: file vẫn ra nhưng đánh dấu, không im lặng."""

    def assert_red(self, result, code, books=()):
        self.assertFalse(result.ok)
        self.assertTrue(result.filename.endswith("-CO-LECH.xlsx"), result.filename)
        problems = {p["code"]: p for p in json.loads(result.header())["problems"]}
        self.assertIn(code, problems)
        self.assertEqual(problems[code]["books"], list(books))
        guide = read_workbook(result.data)["KIỂM"]
        self.assertEqual(guide[1][:2], ["Kết quả tự kiểm", "CÓ LỆCH"])
        label = export_module.check.CHECKS[code]
        row = next(row for row in guide if row and row[0] == label)
        self.assertEqual(row[1], "LỆCH")
        for book in books:
            self.assertIn(str(book), row[2])
        return problems

    def test_overview_total_differs_from_books(self):
        data = world()
        data["get_dashboard"]["receivable"]["total_vnd"] = "350001"
        problems = self.assert_red(run_export(data), "TONG_QUAN_PHAI_THU")
        self.assertEqual(list(problems), ["TONG_QUAN_PHAI_THU"])
        header = run_export(data).header()
        self.assertNotIn("350", header)   # header không mang số tiền

    def test_credit_differs(self):
        data = world()
        data["get_dashboard"]["credit"]["customers"] = 2
        self.assert_red(run_export(data), "TONG_QUAN_KHACH_DU")

    def test_one_book_differs_from_overview(self):
        data = world()
        data["get_dashboard_debt"]["customers"][0]["outstanding_vnd"] = "349000"
        self.assert_red(run_export(data), "SO_LECH_TONG_QUAN", [7])

    def test_months_do_not_add_up(self):
        data = world()
        data["ledgers"][12]["months"][0]["outstanding_vnd"] = "1000"   # tổng sổ vẫn 0
        data["ledgers"][12]["total_outstanding_vnd"] = "0"
        self.assert_red(run_export(data), "SO_LECH_THANG", [12])

    def test_receipt_split_short(self):
        data = world()
        data["ledgers"][7]["receipts"][1]["allocations"][0]["amount_vnd"] = "90000"
        self.assert_red(run_export(data), "PHIEU_CHIA_LECH", [7])

    def test_voided_receipt_still_split(self):
        data = world()
        data["ledgers"][7]["receipts"][2]["allocations"][0]["superseded_by_event"] = None
        self.assert_red(run_export(data), "PHIEU_CHIA_LECH", [7])

    def test_file_missing_a_row(self):
        real = export_module.read_workbook

        def lossy(data):   # giả bộ ghi làm rơi chuyến 502 của sổ 7
            book = real(data)
            book["CHUYẾN"] = [row for row in book["CHUYẾN"] if row[3:4] != [502]]
            return book

        with patch.object(export_module, "read_workbook", side_effect=lossy):
            result = run_export()
        self.assert_red(result, "FILE_LECH", [7])


class ExportRouteTest(unittest.TestCase):
    def serve(self, runner):
        class TrialHandler(api.Handler):
            default_actor = "xuat-so-test"
            dev_actor_mode = True
        TrialHandler.runner = runner
        server = api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler)
        TrialHandler.port = server.server_port
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def stop():
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.addCleanup(stop)
        return server.server_port

    def get(self, port, path="/api/v7/xuat-so.xlsx"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", path)
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response, body

    def test_route_sends_file_and_check_header(self):
        port = self.serve(FakeDb(world()))
        with redirect_stderr(io.StringIO()) as log, patch.object(api, "with_display_names", side_effect=names):
            response, body = self.get(port)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), api.XLSX_TYPE)
        self.assertRegex(response.getheader("Content-Disposition"), r'^attachment; filename="so-web-[0-9]{8}-[0-9]{4}\.xlsx"$')
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(json.loads(response.getheader("X-Xuat-So")), {"ok": True, "books": 4, "problems": []})
        self.assertEqual(list(read_workbook(body)), TABS)
        self.assertIn("XUAT-SO-01: dev:xuat-so-test tải cả sổ: 4 sổ, kiểm khớp", log.getvalue())

    def test_mismatch_marks_filename(self):
        data = world()
        data["get_dashboard_debt"]["receivable_vnd"] = "1"
        port = self.serve(FakeDb(data))
        with redirect_stderr(io.StringIO()) as log:
            response, _ = self.get(port)
        self.assertEqual(response.status, 200)
        self.assertIn("-CO-LECH.xlsx", response.getheader("Content-Disposition"))
        self.assertFalse(json.loads(response.getheader("X-Xuat-So"))["ok"])
        self.assertIn("kiểm TONG_QUAN_PHAI_THU", log.getvalue())

    def test_second_export_while_busy_and_errors(self):
        port = self.serve(FakeDb(world()))
        self.assertTrue(api.EXPORT_LOCK.acquire(blocking=False))
        try:
            response, body = self.get(port)
        finally:
            api.EXPORT_LOCK.release()
        self.assertEqual((response.status, json.loads(body)["error"]), (429, "EXPORT_BUSY"))
        response, body = self.get(port, "/api/v7/xuat-so.xlsx?x=1")
        self.assertEqual(response.status, 422)
        port = self.serve(FakeDb(world(), fail_end=True))
        response, body = self.get(port)
        self.assertEqual((response.status, json.loads(body)["error"]), (503, "DB_UNAVAILABLE"))
        broken = world()
        broken["ledgers"][7]["months"][0]["outstanding_vnd"] = "12,5"
        port = self.serve(FakeDb(broken))
        with redirect_stderr(io.StringIO()):
            response, body = self.get(port)
        self.assertEqual((response.status, json.loads(body)["error"]), (503, "EXPORT_FAILED"))
        self.assertFalse(api.EXPORT_LOCK.locked())


if __name__ == "__main__":
    unittest.main()
