"""KHACH-WEB-01: trang Khách — kiểm thân lệnh, chuẩn hóa tên, chặn tên sổ gần trùng và tên đang vào sổ khác, danh sách chủ hàng
chưa có sổ. Dữ liệu giả (tên khách, container đều bịa)."""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))

import v7_api_khach as khach  # noqa: E402
import v7_api_sheet  # noqa: E402
import v7_role  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402

SHA = "b" * 64
CREATED = {"created_at": "2026-11-24T01:00:00+00:00"}
OLD_BOOK = {"id": 9, "name": "KHACH CU GIA", "status": "active", "commodity": "Dừa", "transport_mode": "CANG", "booking_names": ["CHU HANG CU"]}


class FakeRunner:
    def __init__(self, customers=()):
        self.calls, self.customers = [], list(customers)

    def run(self, function, payload, actor):
        if function == "list_customers":
            return {"customers": self.customers}
        self.calls.append((function, payload, actor))
        return {"ok": True}


def body(**fields):
    return json.dumps(fields, ensure_ascii=False).encode("utf-8")


class Snapshots:
    """Bản chụp giả trong thư mục tạm; thiếu file nào thì đường dẫn trỏ vào file không có (đã thôi đọc Sheet)."""

    def __init__(self, test):
        folder = tempfile.TemporaryDirectory()
        test.addCleanup(folder.cleanup)
        self.dir, self.count = Path(folder.name), 0

    def write(self, name, payload):
        # Mỗi lần ghi một file mới: bộ nhớ đệm bản chụp khóa theo (mtime, cỡ, inode), mà Windows CI ghi đè hai lần cùng cỡ trong một nhịp
        # đồng hồ file thì khóa trùng và test đọc lại bản cũ.
        self.count += 1
        path = self.dir / f"{self.count}-{name}"
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def patch(self, sea=None, road=None, tabs=None, aliases=None, created=CREATED):
        none = str(self.dir / "none.json")
        sea_payload = None if sea is None and aliases is None else {
            "sha256": SHA, "row_count": len(sea or []), "rows": sea or [], "runner": created, **({"customer_aliases": aliases} if aliases else {})}
        paths = {
            "SHEET_SNAPSHOT_PATH": self.write("snapshot.json", sea_payload) if sea_payload else none,
            "SHEET_BASELINE_PATH": self.write("baseline.json", {"cutover_id": 1, "count": 1, "refs": [{"container_norm": "X"}]}),
            "PRICE_SNAPSHOT_PATH": (tabs if isinstance(tabs, str) else self.write("prices.json", {
                "sha256": SHA, "row_count": len(tabs), "rows": list(tabs), "runner": created})) if tabs is not None else none,
            "ROAD_SNAPSHOT_PATH": self.write("road.json", {"sha256": SHA, "row_count": len(road), "rows": road, "runner": created})
            if road is not None else none,
        }
        return patch.multiple(v7_api_sheet, **paths)


def tab(name, line, month, container, date=None):
    return {"customer_tab": name, "source_row": line, "debt_month": month, "container": container, "date": date}


def road_row(line, container, date, owner):
    return {"source_row": line, "container": container, "event_date": date, "status": "READY", "owner": owner,
            "plate": "99Z-1", "gate": "CUA KHAU GIA", "warehouse": "", "shipper": ""}


class NameTests(unittest.TestCase):
    def test_booking_name_is_keyed_like_the_queue(self):
        self.assertEqual(khach.booking_name("  chu  hang\tgia 413 "), "CHU HANG GIA 413")
        self.assertEqual(khach.booking_name("Khách Mới 黄总"), "KHÁCH MỚI 黄总")
        self.assertEqual(khach.booking_name("CHU\u00a0HANG\u2028GIA"), "CHU HANG GIA")   # NBSP, ngắt dòng Unicode gộp như khoảng trắng
        for bad in ("", "   ", None, 7, "A\x00B", "X" * 201, "A\u200bB", "A\ufeffB", "A\u2066B"):
            self.assertIsNone(khach.booking_name(bad), repr(bad))

    def test_book_key_merges_every_machine_key(self):
        """Đối soát gộp khoảng trắng, bảng ghép giá bỏ / \\ ? * [ ] : ', DB không phân biệt hoa thường: một khóa gộp cả ba."""
        self.assertEqual(khach.book_key("Khách\u00a0 Mới"), khach.book_key("KHÁCH MỚI"))
        self.assertEqual(khach.book_key("khach a/b"), khach.book_key("KHACH  AB"))
        self.assertNotEqual(khach.book_key("KHACH A"), khach.book_key("KHACH B"))
        self.assertEqual(khach.tab_book_name(" Khach  A/B: '1' "), "Khach AB 1")


class CreateTests(unittest.TestCase):
    def setUp(self):
        self.snap = Snapshots(self)

    def error(self, raw, code, customers=(OLD_BOOK,), **snapshots):
        with self.snap.patch(**snapshots), self.assertRaises(ApiError) as caught:
            khach.handle_create(raw, FakeRunner(customers), "quan-ly")
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def create(self, raw, customers=(OLD_BOOK,), **snapshots):
        runner = FakeRunner(customers)
        with self.snap.patch(**snapshots):
            status, result = khach.handle_create(raw, runner, "quan-ly")
        self.assertEqual(status, 200)
        return runner.calls, result

    def test_create_normalizes_names(self):
        calls, result = self.create(body(book_name="  KHACH GIA  NONG+ 413 ", commodity=" Dừa ", transport_mode="CANG",
                                         booking_names=["chu hang gia 413", "CHU HANG  GIA 413", "khác"], idempotency_key="k1"))
        self.assertEqual(calls, [("create_customer", {"book_name": "KHACH GIA NONG+ 413", "commodity_name": "Dừa", "book_mode": "CANG",
                                                      "booking_names": ["CHU HANG GIA 413", "KHÁC"], "idempotency_key": "k1"}, "quan-ly")])
        self.assertEqual(result["name"], "KHACH GIA NONG+ 413")
        calls, _ = self.create(body(book_name="KHACH", commodity="", transport_mode="BO", idempotency_key="k2"))
        self.assertEqual((calls[0][1]["commodity_name"], calls[0][1]["booking_names"]), (None, []))

    def test_create_rejects_bad_bodies(self):
        ok = {"book_name": "KHACH", "transport_mode": "CANG", "booking_names": [], "idempotency_key": "k"}
        self.error(b"{", "INVALID_REQUEST")
        self.error(body(**ok, extra=1), "INVALID_REQUEST")
        for name in ("  ", "KHACH A/B", "KHACH: A", "KHACH 'A'", "KHACH\u200bA", "X" * 201):
            self.error(body(**{**ok, "book_name": name}), "INVALID_BOOK_NAME")
        self.error(body(**{**ok, "commodity": "Dừa\x07"}), "INVALID_REQUEST")
        self.error(body(**{**ok, "transport_mode": "SAI"}), "INVALID_REQUEST")
        self.error(body(**{**ok, "booking_names": "A"}), "INVALID_REQUEST")
        self.error(body(**{**ok, "booking_names": [f"T {n}" for n in range(21)]}), "INVALID_REQUEST")
        self.error(body(**{**ok, "booking_names": ["  "]}), "INVALID_BOOKING_NAME")
        self.error(body(**{**ok, "idempotency_key": ""}), "INVALID_REQUEST")
        self.error(b'{"book_name": "A", "book_name": "B"}', "INVALID_REQUEST")

    def test_near_duplicate_books_are_refused_exact_name_goes_to_the_database(self):
        """Gần trùng (khoảng trắng, hoa thường): máy đối soát hay bảng ghép giá sẽ gặp hai sổ một tên, nên chặn ở đây. Đúng tên thì
        để DB quyết: bấm lại cùng khóa trả kết quả cũ (kể cả khi đã sang tháng và tab đã có dòng tháng trước), không thì BOOK_EXISTS."""
        ok = {"transport_mode": "CANG", "booking_names": [], "idempotency_key": "k"}
        refused = self.error(body(book_name="khach  cu gia", **ok), "BOOK_EXISTS")
        self.assertIn("KHACH CU GIA", refused.message)
        shown = {**OLD_BOOK, "id": 10, "name": "SO GIA 10", "display_name": "KHACH HIEN THI GIA"}
        self.error(body(book_name="Khach Hien Thi Gia", **ok), "BOOK_EXISTS", customers=[shown])
        calls, _ = self.create(body(book_name="KHACH CU GIA", **ok), tabs=[tab("KHACH CU GIA", 3, "2026-10", "FAKU1000001")])
        self.assertEqual(calls[0][1]["book_name"], "KHACH CU GIA")

    def test_book_takes_the_exact_sheet_tab_spelling(self):
        tabs = [tab("Khach Tab Gia", 3, "2026-11", "FAKU1000001"), tab("KHACH A/B GIA", 4, "2026-11", "FAKU1000002")]
        ok = {"transport_mode": "CANG", "booking_names": [], "idempotency_key": "k"}
        with patch.object(khach, "datetime", wraps=khach.datetime) as clock:
            clock.now.return_value = khach.datetime(2026, 11, 24, 9, 0, tzinfo=khach.VN)
            calls, result = self.create(body(book_name="KHACH TAB GIA", **ok), tabs=tabs)
            self.assertEqual((calls[0][1]["book_name"], result["name"]), ("Khach Tab Gia", "Khach Tab Gia"))
            calls, _ = self.create(body(book_name="khach ab gia", **ok), tabs=tabs)
            self.assertEqual(calls[0][1]["book_name"], "KHACH AB GIA")

    def test_create_refuses_names_that_route_trips_elsewhere(self):
        ok = {"transport_mode": "CANG", "idempotency_key": "k"}
        self.error(body(book_name="chu hang cu", booking_names=[], **ok), "BOOKING_NAME_ROUTED")   # tên booking của sổ khác
        self.error(body(book_name="KHACH LA GIA", booking_names=[], **ok), "BOOKING_NAME_ROUTED",
                   sea=[], aliases={"KHACH LA GIA": "KHACH CU GIA"})                             # WEB_GHEP_KHACH ghép vào sổ khác
        refused = self.error(body(book_name="KHACH MOI GIA", booking_names=["khach cu gia"], **ok), "BOOKING_NAME_ROUTED")
        self.assertEqual(refused.extra, {"name": "KHACH CU GIA"})
        calls, _ = self.create(body(book_name="KHACH MOI GIA", booking_names=["CHU HANG MOI"], **ok),
                               sea=[], aliases={"CHU HANG MOI": "KHACH MOI GIA"})                  # bảng đã ghép đúng sổ sắp tạo
        self.assertEqual(calls[0][1]["booking_names"], ["CHU HANG MOI"])

    def test_create_refuses_a_sheet_tab_that_already_has_older_debt(self):
        """Khi chạy song song: tab Sheet có dòng tháng trước thì để máy tạo sổ theo Sheet, không tạo tay sổ nợ 0."""
        tabs = [tab("KHACH CU  TAB", 3, "2026-10", "FAKU1000001", "2026-10-02"), tab("KHACH MOI TAB", 4, "2026-11", "FAKU1000002", "2026-11-02")]
        ok = {"transport_mode": "CANG", "booking_names": [], "idempotency_key": "k"}
        with patch.object(khach, "datetime", wraps=khach.datetime) as clock:
            clock.now.return_value = khach.datetime(2026, 11, 24, 9, 0, tzinfo=khach.VN)
            self.error(body(book_name="khach cu tab", **ok), "SHEET_TAB_HAS_HISTORY", tabs=tabs)
            self.create(body(book_name="KHACH MOI TAB", **ok), tabs=tabs)                    # khách mới tháng này trên Sheet
            self.create(body(book_name="KHACH CHUA CO TAB", **ok), tabs=tabs)
            self.error(body(book_name="KHACH X", **ok), "SHEET_SNAPSHOT_UNAVAILABLE", tabs=self.snap.write("bad.json", "{"))
            self.create(body(book_name="KHACH CU TAB", **ok))                                # đã thôi đọc Sheet: không chặn


class BookingNameTests(unittest.TestCase):
    def setUp(self):
        self.snap = Snapshots(self)

    def send(self, name, customer_id=7, remove=False, customers=None, **snapshots):
        customers = customers if customers is not None else [
            {"id": 7, "name": "KHACH DICH GIA", "status": "active", "transport_mode": "BO", "booking_names": []}, OLD_BOOK]
        runner = FakeRunner(customers)
        with self.snap.patch(**snapshots):
            khach.handle_booking_name(body(customer_id=customer_id, expected_version=3, idempotency_key="k", name=name, remove=remove),
                                      runner, "quan-ly")
        return runner.calls

    def refused(self, name, code="BOOKING_NAME_ROUTED", **kwargs):
        with self.assertRaises(ApiError) as caught:
            self.send(name, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception.message

    def test_booking_name_command(self):
        self.assertEqual(self.send(" chu hang  thu 126 "), [("set_booking_name", {"customer_id": 7, "expected_version": 3, "idempotency_key": "k",
                                                                                   "name": "CHU HANG THU 126", "remove": False}, "quan-ly")])
        ok = {"customer_id": 7, "expected_version": 3, "idempotency_key": "k", "name": "A", "remove": True}
        for change in ({"customer_id": 0}, {"customer_id": True}, {"expected_version": -1}, {"expected_version": False},
                       {"expected_version": 2 ** 63}, {"remove": "true"}, {"idempotency_key": " "}):
            with self.assertRaises(ApiError) as caught:
                khach.handle_booking_name(body(**{**ok, **change}), FakeRunner(), "quan-ly")
            self.assertEqual(caught.exception.code, "INVALID_REQUEST", change)
        with self.assertRaises(ApiError) as caught:
            khach.handle_booking_name(body(**{**ok, "name": ""}), FakeRunner(), "quan-ly")
        self.assertEqual(caught.exception.code, "INVALID_BOOKING_NAME")

    def test_name_that_routes_to_another_book_is_refused(self):
        self.assertIn("KHACH CU GIA", self.refused("khach cu gia"))                       # trùng tên một sổ khác
        shown = [{"id": 7, "name": "KHACH DICH GIA", "status": "active", "booking_names": []},
                 {"id": 8, "name": "SO GIA 8", "status": "active", "display_name": "TEN KHACH GIA", "booking_names": []}]
        self.refused("ten khach gia", customers=shown)                                      # trùng tên khách của sổ khác
        self.assertIn("đã gán", self.refused("CHU HANG CU"))                               # đã gán cho sổ khác
        self.assertIn("gần trùng", self.refused("CHU HANG: CU"))                           # chuyến bộ so như nhau
        self.assertIn("WEB_GHEP_KHACH", self.refused("CHU HANG BANG", sea=[], aliases={"CHU HANG BANG": "KHACH CU GIA"}))
        self.assertEqual(len(self.send("CHU HANG BANG", sea=[], aliases={"CHU HANG BANG": "KHACH DICH GIA"})), 1)   # bảng ghép đúng sổ này
        self.assertEqual(self.send("KHACH CU GIA", remove=True)[0][1]["remove"], True)    # bỏ tên không kiểm

    def test_road_owner_already_placed_by_sheet_tabs_is_refused(self):
        """Chủ hàng bộ mà tab Sheet đã đưa vào sổ khác (hay nhiều sổ: kho) thì không gán; chỉ vào đúng sổ đó thì gán được."""
        customers = [{"id": 7, "name": "KHACH BO GIA 1", "status": "active", "transport_mode": "BO", "booking_names": []},
                     {"id": 8, "name": "KHACH BO GIA 2", "status": "active", "transport_mode": "BO", "booking_names": []}]
        tabs = [tab("KHACH BO GIA 1", 3, "2026-11", "ROAU1000001", "2026-11-02"), tab("KHACH BO GIA 2", 4, "2026-11", "ROAU1000002", "2026-11-03")]
        one = [road_row(2, "ROAU1000001", "2026-11-02", "chu hang bo")]
        self.assertIn("KHACH BO GIA 1", self.refused("CHU HANG BO", customer_id=8, customers=customers, sea=[], tabs=tabs, road=one))
        self.assertEqual(len(self.send("CHU HANG BO", customer_id=7, customers=customers, sea=[], tabs=tabs, road=one)), 1)
        two = one + [road_row(3, "ROAU1000002", "2026-11-03", "CHU HANG BO")]
        self.assertIn("2 sổ", self.refused("CHU HANG BO", customer_id=7, customers=customers, sea=[], tabs=tabs, road=two))

    def test_unreadable_snapshot_is_not_guessed(self):
        self.refused("CHU HANG MOI", code="SHEET_SNAPSHOT_UNAVAILABLE", tabs=self.snap.write("bad.json", "{"))

    def test_routes_are_for_managers_only(self):
        for path in ("/api/v7/admin/customers", "/api/v7/admin/booking-names"):
            self.assertTrue(v7_role.admin_api(path))
            self.assertFalse(v7_role.allowed(path, v7_role.USER, {}))
        self.assertFalse(v7_role.allowed("/khach.html", v7_role.USER, {"/khach.html": "khach.html"}))


def sea(line, container, date, owner, commodity="Dừa", status="READY"):
    return {"source_row": line, "container": container, "event_date": date, "status": status, "customer_name": owner,
            "commodity": commodity, "carrier": "FAKE", "origin": "A", "destination": "B", "booking": "BK"}


class UnmappedTests(unittest.TestCase):
    NOW = datetime(2026, 11, 24, 9, 0, tzinfo=khach.VN)

    def setUp(self):
        self.snap = Snapshots(self)

    def test_owners_without_a_book_grouped_with_sheet_tab_hint(self):
        customers = [OLD_BOOK, {"id": 10, "name": "KHACH GIA NONG+ 413", "status": "active", "commodity": "Dừa", "transport_mode": "CANG"},
                     {"id": 11, "name": "KHACH A/B GIA", "status": "active", "commodity": "Dừa", "transport_mode": "BO"}]
        rows = [sea(2, "FAKU1000001", "2026-11-02", "chu hang gia 413"), sea(3, "FAKU1000002", "2026-11-05", "CHU HANG GIA 413"),
                sea(4, "FAKU1000003", "2026-09-20", "CHU HANG GIA 413"),              # trước tháng nạp V7: không liệt kê
                sea(5, "FAKU1000004", "2026-11-06", "CHU HANG CU"),                   # đã gán trên web
                sea(6, "FAKU1000005", "2026-11-07", "CHU HANG LA", status="INVALID"),  # dòng lỗi
                sea(7, "FAKU1000006", "2026-11-22", "CHU HANG LA", commodity="Chuối"),
                sea(8, "FAKU1000007", "2026-11-23", "CHU HANG SANG BO")]
        tabs = [tab("KHACH GIA NONG+ 413", 9, "2026-11", "FAKU1000001", "2026-11-03"), tab("TAB CHUA: CO SO", 4, "2026-11", "FAKU1000006"),
                tab("KHACH A/B GIA", 5, "2026-11", "FAKU1000007", "2026-11-23")]
        road = [road_row(2, "ROAU1000001", "2026-11-08", "KHO MOI 401")]
        with self.snap.patch(sea=rows, road=road, tabs=tabs):
            result = khach.unmapped(customers, self.NOW)
        self.assertEqual((result["state"], result["road_state"], result["sheet_state"], result["snapshot_stale_minutes"]), ("ok", "ok", "ok", None))
        got = {(owner["family"], owner["name"]): owner for owner in result["owners"]}
        self.assertEqual(set(got), {("BIEN", "CHU HANG GIA 413"), ("BIEN", "CHU HANG LA"), ("BIEN", "CHU HANG SANG BO"), ("BO", "KHO MOI 401")})
        main = got[("BIEN", "CHU HANG GIA 413")]
        self.assertEqual((main["trips"], main["first"], main["last"], main["commodities"], main["suggest_customer_id"], main["many_books"], main["assigned_to"]),
                         (2, "2026-11-02", "2026-11-05", ["Dừa"], 10, 0, None))
        self.assertEqual(main["sheet_tabs"], [{"tab": "KHACH GIA NONG+ 413", "book_name": "KHACH GIA NONG+ 413", "trips": 1, "customer_id": 10}])
        self.assertEqual(got[("BIEN", "CHU HANG LA")]["sheet_tabs"], [{"tab": "TAB CHUA: CO SO", "book_name": "TAB CHUA CO SO", "trips": 1, "customer_id": None}])
        self.assertIsNone(got[("BIEN", "CHU HANG LA")]["suggest_customer_id"])
        self.assertIsNone(got[("BIEN", "CHU HANG SANG BO")]["suggest_customer_id"], "tab ứng sổ đi bộ: không gợi ý cho chuyến biển")
        self.assertEqual(result["owners"][0]["name"], "CHU HANG GIA 413")   # nhiều chuyến nhất lên đầu

    def test_road_owner_of_several_books_and_name_assigned_elsewhere(self):
        customers = [{"id": 7, "name": "KHACH BO GIA 1", "status": "active", "transport_mode": "BO", "booking_names": []},
                     {"id": 8, "name": "KHACH BO GIA 2", "status": "active", "transport_mode": "BO", "booking_names": []},
                     {"id": 9, "name": "KHACH BIEN GIA", "status": "active", "transport_mode": "CANG", "booking_names": ["CHU HANG HAI DUONG"]}]
        tabs = [tab("KHACH BO GIA 1", 3, "2026-11", "ROAU1000001", "2026-11-02"), tab("KHACH BO GIA 2", 4, "2026-11", "ROAU1000002", "2026-11-03")]
        road = [road_row(2, "ROAU1000001", "2026-11-02", "KHO GIA"), road_row(3, "ROAU1000002", "2026-11-03", "KHO GIA"),
                road_row(4, "ROAU1000003", "2026-11-10", "KHO GIA"), road_row(5, "ROAU1000004", "2026-11-11", "CHU HANG HAI DUONG")]
        with self.snap.patch(sea=[], road=road, tabs=tabs):
            owners = {owner["name"]: owner for owner in khach.unmapped(customers, self.NOW)["owners"]}
        self.assertEqual((owners["KHO GIA"]["many_books"], owners["KHO GIA"]["suggest_customer_id"], owners["KHO GIA"]["trips"]), (2, None, 1))
        self.assertEqual(owners["CHU HANG HAI DUONG"]["assigned_to"], {"id": 9, "name": "KHACH BIEN GIA"}, "tên ở sổ biển không dẫn chuyến bộ")

    def test_missing_or_broken_snapshots_are_reported_not_guessed(self):
        self.assertEqual(khach.unmapped([], self.NOW), {"state": "unavailable", "owners": []})   # mọi đường dẫn mặc định đều không có
        with self.snap.patch(sea=[sea(2, "FAKU1000001", "2026-11-02", "KHACH LA")]):           # chưa có road.json, prices.json
            result = khach.unmapped([], self.NOW)
        self.assertEqual((result["state"], result["road_state"], result["sheet_state"], [o["name"] for o in result["owners"]]),
                         ("ok", "unavailable", "none", ["KHACH LA"]))
        with self.snap.patch(sea=[], road=[road_row(2, "ROAU1000001", "2026-11-08", "KHO MOI")], tabs=self.snap.write("bad.json", "{")):
            result = khach.unmapped([], self.NOW)
        self.assertEqual((result["sheet_state"], result["road_state"], result["owners"]), ("unavailable", "unavailable", []))
        with self.snap.patch(sea=[], road=[road_row(2, "ROAU1000001", "2026-11-08", "KHO MOI")]):   # đã thôi đọc Sheet: chuyến bộ theo chủ hàng
            result = khach.unmapped([], self.NOW)
        self.assertEqual((result["sheet_state"], result["road_state"], [o["name"] for o in result["owners"]]), ("none", "ok", ["KHO MOI"]))
        with self.snap.patch(sea=[], created={"created_at": (self.NOW - timedelta(hours=2)).isoformat()}):
            self.assertEqual(khach.unmapped([], self.NOW)["snapshot_stale_minutes"], 120)
        with self.snap.patch(sea=[]), patch.object(v7_api_sheet, "cached_queue", side_effect=ValueError("hỏng")):
            self.assertEqual(khach.unmapped([], self.NOW)["state"], "unavailable")

    def test_view_lists_books_with_booking_names(self):
        runner = FakeRunner([{"id": 9, "name": "KHACH CU", "status": "active", "booking_names": ["CHU HANG CU"]}])
        with self.snap.patch(sea=[]):
            view = khach.view(runner, "quan-ly")
        self.assertEqual(view["customers"][0]["booking_names"], ["CHU HANG CU"])
        self.assertEqual(view["unmapped"]["owners"], [])


if __name__ == "__main__":
    unittest.main()
