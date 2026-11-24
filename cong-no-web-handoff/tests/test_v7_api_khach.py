"""KHACH-WEB-01: trang Khách — kiểm thân lệnh, chuẩn hóa tên chủ hàng booking, danh sách chủ hàng chưa có sổ. Dữ liệu giả."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import v7_api_khach as khach  # noqa: E402
import v7_api_sheet  # noqa: E402
import v7_role  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402

SHA = "b" * 64


class FakeRunner:
    def __init__(self, customers=()):
        self.calls, self.customers = [], list(customers)

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "list_customers":
            return {"customers": self.customers}
        return {"ok": True}


def body(**fields):
    return json.dumps(fields, ensure_ascii=False).encode("utf-8")


class ValidateTests(unittest.TestCase):
    def error(self, handler, raw, code="INVALID_REQUEST"):
        with self.assertRaises(ApiError) as caught:
            handler(raw, FakeRunner(), "quan-ly")
        self.assertEqual(caught.exception.code, code)

    def test_booking_name_is_keyed_like_the_queue(self):
        self.assertEqual(khach.booking_name("  a  tank\t413 "), "A TANK 413")
        self.assertEqual(khach.booking_name("Khách Mới 黄总"), "KHÁCH MỚI 黄总")
        for bad in ("", "   ", None, 7, "A\x00B", "X" * 201):
            self.assertIsNone(khach.booking_name(bad))

    def test_create_normalizes_names_and_keeps_the_book_name_as_typed(self):
        runner = FakeRunner()
        status, _ = khach.handle_create(body(book_name="  HOA VIET  NONG+ ATANK 413 ", commodity=" Dừa ", transport_mode="CANG",
                                             booking_names=["a tank 413", "A TANK  413", "khác"], idempotency_key="k1"), runner, "quan-ly")
        self.assertEqual(status, 200)
        self.assertEqual(runner.calls, [("create_customer", {"book_name": "HOA VIET  NONG+ ATANK 413", "commodity_name": "Dừa",
                                                              "book_mode": "CANG", "booking_names": ["A TANK 413", "KHÁC"],
                                                              "idempotency_key": "k1"}, "quan-ly")])
        runner = FakeRunner()
        khach.handle_create(body(book_name="KHACH", commodity="", transport_mode="BO", idempotency_key="k2"), runner, "quan-ly")
        self.assertEqual(runner.calls[0][1]["commodity_name"], None)
        self.assertEqual(runner.calls[0][1]["booking_names"], [])

    def test_create_rejects_bad_bodies(self):
        ok = {"book_name": "KHACH", "transport_mode": "CANG", "booking_names": [], "idempotency_key": "k"}
        self.error(khach.handle_create, b"{", "INVALID_REQUEST")
        self.error(khach.handle_create, body(**ok, extra=1))
        self.error(khach.handle_create, body(**{**ok, "book_name": "  "}), "INVALID_BOOK_NAME")
        self.error(khach.handle_create, body(**{**ok, "transport_mode": "SAI"}))
        self.error(khach.handle_create, body(**{**ok, "booking_names": "A"}))
        self.error(khach.handle_create, body(**{**ok, "booking_names": [f"T {n}" for n in range(21)]}))
        self.error(khach.handle_create, body(**{**ok, "booking_names": ["  "]}), "INVALID_BOOKING_NAME")
        self.error(khach.handle_create, body(**{**ok, "idempotency_key": ""}))
        self.error(khach.handle_create, b'{"book_name": "A", "book_name": "B"}')

    def test_booking_name_command(self):
        runner = FakeRunner()
        khach.handle_booking_name(body(customer_id=7, expected_version=3, idempotency_key="k", name=" hezong  126 ", remove=False),
                                  runner, "quan-ly")
        self.assertEqual(runner.calls, [("set_booking_name", {"customer_id": 7, "expected_version": 3, "idempotency_key": "k",
                                                               "name": "HEZONG 126", "remove": False}, "quan-ly")])
        ok = {"customer_id": 7, "expected_version": 3, "idempotency_key": "k", "name": "A", "remove": True}
        for change in ({"customer_id": 0}, {"customer_id": True}, {"expected_version": -1}, {"expected_version": False},
                       {"remove": "true"}, {"idempotency_key": " "}):
            self.error(khach.handle_booking_name, body(**{**ok, **change}))
        self.error(khach.handle_booking_name, body(**{k: v for k, v in ok.items() if k != "remove"}))
        self.error(khach.handle_booking_name, body(**{**ok, "name": ""}), "INVALID_BOOKING_NAME")

    def test_routes_are_for_managers_only(self):
        for path in ("/api/v7/admin/customers", "/api/v7/admin/booking-names"):
            self.assertTrue(v7_role.admin_api(path))
            self.assertFalse(v7_role.allowed(path, v7_role.USER, {}))
        self.assertFalse(v7_role.allowed("/khach.html", v7_role.USER, {"/khach.html": "khach.html"}))


def sea(line, container, date, owner, commodity="Dừa", status="READY"):
    return {"source_row": line, "container": container, "event_date": date, "status": status, "customer_name": owner,
            "commodity": commodity, "carrier": "FAKE", "origin": "A", "destination": "B", "booking": "BK"}


class UnmappedTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)

    def write(self, name, payload):
        path = self.dir / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def paths(self, sea_rows, road_rows=None, tab_rows=()):
        created = {"created_at": "2026-11-24T01:00:00+00:00"}
        paths = {
            "SHEET_SNAPSHOT_PATH": self.write("snapshot.json", {"sha256": SHA, "row_count": len(sea_rows), "rows": sea_rows, "runner": created}),
            "SHEET_BASELINE_PATH": self.write("baseline.json", {"cutover_id": 1, "count": 1, "refs": [{"container_norm": "X"}]}),
            "PRICE_SNAPSHOT_PATH": self.write("prices.json", {"sha256": SHA, "row_count": len(tab_rows), "rows": list(tab_rows), "runner": created}),
            "ROAD_SNAPSHOT_PATH": self.write("road.json", {"sha256": SHA, "row_count": len(road_rows), "rows": road_rows, "runner": created})
            if road_rows is not None else str(self.dir / "none.json"),
        }
        return patch.multiple(v7_api_sheet, **paths)

    def test_owners_without_a_book_grouped_with_sheet_tab_hint(self):
        customers = [{"id": 9, "name": "KHACH CU", "status": "active", "commodity": "Dừa", "booking_names": ["CHU HANG CU"]},
                     {"id": 10, "name": "HOA VIET NONG+ ATANK 413", "status": "active", "commodity": "Dừa"}]
        rows = [sea(2, "FAKU1000001", "2026-11-02", "a tank 413"), sea(3, "FAKU1000002", "2026-11-05", "A TANK 413"),
                sea(4, "FAKU1000003", "2026-09-20", "A TANK 413"),                     # trước tháng nạp V7: không liệt kê
                sea(5, "FAKU1000004", "2026-11-06", "CHU HANG CU"),                    # đã gán trên web
                sea(6, "FAKU1000005", "2026-11-07", "XINGNONG", status="INVALID"),     # dòng lỗi
                sea(7, "FAKU1000006", "2026-11-22", "XINGNONG", commodity="Chuối")]
        tabs = [{"customer_tab": "HOA VIET NONG+ ATANK 413", "source_row": 9, "debt_month": "2026-11", "container": "FAKU1000001", "date": "2026-11-03"},
                {"customer_tab": "TAB CHUA CO SO", "source_row": 4, "debt_month": "2026-11", "container": "FAKU1000006", "date": None}]
        road = [{"source_row": 2, "container": "ROAU1000001", "event_date": "2026-11-08", "status": "READY", "owner": "KHO MOI 401",
                 "plate": "99Z-1", "gate": "CHIMA", "warehouse": "", "shipper": ""}]
        with self.paths(rows, road, tabs):
            result = khach.unmapped(customers)
        self.assertEqual((result["state"], result["road_state"]), ("ok", "ok"))
        got = {(owner["family"], owner["name"]): owner for owner in result["owners"]}
        self.assertEqual(set(got), {("BIEN", "A TANK 413"), ("BIEN", "XINGNONG"), ("BO", "KHO MOI 401")})
        tank = got[("BIEN", "A TANK 413")]
        self.assertEqual((tank["trips"], tank["first"], tank["last"], tank["commodities"], tank["suggest_customer_id"]),
                         (2, "2026-11-02", "2026-11-05", ["Dừa"], 10))
        self.assertEqual(tank["sheet_tabs"], [{"tab": "HOA VIET NONG+ ATANK 413", "trips": 1, "customer_id": 10}])
        self.assertEqual(got[("BIEN", "XINGNONG")]["sheet_tabs"], [{"tab": "TAB CHUA CO SO", "trips": 1, "customer_id": None}])
        self.assertIsNone(got[("BIEN", "XINGNONG")]["suggest_customer_id"])
        self.assertEqual(result["owners"][0]["name"], "A TANK 413")   # nhiều chuyến nhất lên đầu

    def test_missing_snapshots_are_reported_not_guessed(self):
        with patch.multiple(v7_api_sheet, SHEET_SNAPSHOT_PATH=str(self.dir / "none.json")):
            self.assertEqual(khach.unmapped([]), {"state": "unavailable", "owners": []})
        with self.paths([sea(2, "FAKU1000001", "2026-11-02", "KHACH LA")]):   # chưa có road.json
            result = khach.unmapped([])
        self.assertEqual((result["state"], result["road_state"], [o["name"] for o in result["owners"]]), ("ok", "unavailable", ["KHACH LA"]))

    def test_view_lists_books_with_booking_names(self):
        runner = FakeRunner([{"id": 9, "name": "KHACH CU", "status": "active", "booking_names": ["CHU HANG CU"]}])
        with self.paths([]):
            view = khach.view(runner, "quan-ly")
        self.assertEqual(view["customers"][0]["booking_names"], ["CHU HANG CU"])
        self.assertEqual(view["unmapped"]["owners"], [])


if __name__ == "__main__":
    unittest.main()
