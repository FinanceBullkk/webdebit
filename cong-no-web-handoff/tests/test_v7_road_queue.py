"""Chuyến bộ mới vào sổ theo tab khách trên Sheet (NGUON-CHUYEN-01 GĐ3, specs/v7-chuyen-theo-nguon.md). Dữ liệu giả."""

import json
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_api_sheet
from v7_road_queue import (
    NO_WAREHOUSE,
    NOTE,
    build_road_queue,
    project_choices,
    project_road,
    source_fingerprint,
)

SHA = "a" * 64
CUSTOMERS = [{"id": 7, "name": "DUONG BO KHACH A 324", "status": "active"},
             {"id": 8, "name": "KHACH B", "status": "active", "aliases": ["KHACH B CU"]},
             {"id": 9, "name": "KHACH C", "status": "draft"}]


def road_row(line, container, date, status="READY", gate="CHIMA", plate="99Z-00001", warehouse="", owner="KHÁCH KHO 336"):
    return {"source_row": line, "container": container, "event_date": date, "source_date": date, "plate": plate,
            "gate": gate, "warehouse": warehouse, "shipper": "", "owner": owner, "status": status}


def tab_row(tab, row, container, date, month="2026-10"):
    return {"customer_tab": tab, "source_row": row, "debt_month": month, "container": container, "date": date,
            "sheet_unit_price_vnd": 11000000, "sheet_other_fee_vnd": 880000, "sheet_total_vnd": 11880000}


def ledger(trips=(), legacy=(), customer_id=7):
    return {"customer_id": customer_id, "today_month": "2026-11-01", "month_locks": [], "trips": list(trips),
            "legacy_rows": list(legacy)}


class BuildRoadQueueTests(unittest.TestCase):
    def build(self, road_rows, tab_rows):
        return build_road_queue({"sha256": SHA, "rows": road_rows}, {"rows": tab_rows}, CUSTOMERS)

    def test_book_comes_from_the_one_tab_holding_the_container_not_from_the_owner_column(self):
        queue = self.build([road_row(12, "FAKU1000001", "2026-10-02", warehouse="LÂM ĐỒNG")],
                           [tab_row("DUONG BO KHACH A 324", 382, "FAKU1000001", "2026-10-03"),
                            tab_row("KHACH B", 40, "FAKU1000001", "2026-08-31", month="2026-08")])   # container dùng lại
        self.assertEqual(queue["stats"], {"BOOK": 1})
        item = queue["items"][0]
        self.assertEqual((item["customer_id"], item["customer_tab"], item["tab_row"], item["tab_debt_month"]),
                         (7, "DUONG BO KHACH A 324", 382, "2026-10"))
        # Ngày theo CONT_BO; xe, cửa khẩu, kho theo CONT_BO; CHỦ HÀNG chỉ để hiện.
        self.assertEqual((item["event_date"], item["carrier"], item["destination"], item["origin"], item["owner"]),
                         ("2026-10-02", "99Z-00001", "CHIMA", "LÂM ĐỒNG", "KHÁCH KHO 336"))
        self.assertEqual((item["src"], item["note"], item["booking"]), (f"sheet:{SHA}:12", NOTE, ""))

    def test_alias_tab_and_blank_warehouse(self):
        queue = self.build([road_row(3, "FAKU1000002", "2026-10-24")], [tab_row("KHACH B CU", 108, "FAKU1000002", None)])
        self.assertEqual((queue["items"][0]["customer_id"], queue["items"][0]["origin"]), (8, NO_WAREHOUSE))

    def test_rows_that_cannot_be_placed_are_counted_never_guessed(self):
        queue = self.build([
            road_row(2, "NOTAB000001", "2026-10-05", owner="KHO MOI"),        # chưa có ở tab nào, chủ hàng lạ: chờ Sheet
            road_row(3, "TWOTAB00001", "2026-10-05"),                         # hai tab
            road_row(4, "DRAFT000001", "2026-10-05"),                         # tab của sổ chưa hoạt động
            road_row(5, "OLDROW00001", "2026-09-30"),                         # trước tháng nạp V7
            road_row(6, "BADROW00001", "2026-10-05", status="INVALID"),
            road_row(7, "SHARED00001", "2026-10-05"), road_row(8, "SHARED00001", "2026-10-07"),   # hai chuyến, một dòng tab
        ], [tab_row("DUONG BO KHACH A 324", 1, "TWOTAB00001", "2026-10-05"), tab_row("KHACH B", 2, "TWOTAB00001", "2026-10-06"),
            tab_row("KHACH C", 3, "DRAFT000001", "2026-10-05"), tab_row("KHACH B", 4, "OLDROW00001", "2026-09-30"),
            tab_row("KHACH B", 5, "BADROW00001", "2026-10-05"), tab_row("KHACH B", 6, "SHARED00001", "2026-10-06")])
        self.assertEqual(queue["items"], [])
        self.assertEqual(queue["stats"], {"NO_TAB": 1, "AMBIGUOUS_TAB": 1, "NO_BOOK": 1, "AMBIGUOUS_SOURCE": 2})
        # BAO-CAO-THANG-02: từng chuyến không xếp được ghi lý do, để Báo cáo tháng nói vì sao web chưa có
        self.assertEqual(sorted((s["container"], s["event_date"], s["reason"]) for s in queue["skipped"]), [
            ("DRAFT000001", "2026-10-05", "NO_BOOK"), ("NOTAB000001", "2026-10-05", "NO_TAB"),
            ("SHARED00001", "2026-10-05", "AMBIGUOUS_SOURCE"), ("SHARED00001", "2026-10-07", "AMBIGUOUS_SOURCE"),
            ("TWOTAB00001", "2026-10-05", "AMBIGUOUS_TAB")])


class RoadChoiceTests(unittest.TestCase):
    """WEB-CHINH-01: chuyến bộ máy giữ lại mà biết sổ có thể nhận thì người chọn sổ trên web, như chuyến biển chưa rõ sổ."""

    def queue(self):
        return build_road_queue({"sha256": SHA, "rows": [road_row(3, "TWOTAB00001", "2026-10-05"), road_row(2, "NOTAB000001", "2026-10-05", owner="KHO MOI"),
                                                         road_row(4, "DRAFT000001", "2026-10-05")]},
                                {"rows": [tab_row("DUONG BO KHACH A 324", 1, "TWOTAB00001", "2026-10-05"), tab_row("KHACH B", 2, "TWOTAB00001", "2026-10-06"),
                                          tab_row("KHACH C", 3, "DRAFT000001", "2026-10-05")]}, CUSTOMERS)

    def test_only_trips_with_known_candidate_books_are_offered(self):
        queue = self.queue()
        self.assertEqual(queue["stats"], {"AMBIGUOUS_TAB": 1, "NO_TAB": 1, "NO_BOOK": 1})   # máy vẫn không tự đưa vào
        self.assertEqual([(c["container"], c["candidate_ids"], c["choice_reason"]) for c in queue["choices"]],
                         [("TWOTAB00001", [7, 8], "AMBIGUOUS_TAB")])   # không tab nào, hay tab của sổ chưa hoạt động: không có ứng viên

    def test_shown_once_in_the_first_candidate_book_and_gone_once_any_book_has_the_trip(self):
        queue = self.queue()
        shown = project_choices(queue, ledger(customer_id=7), CUSTOMERS)
        self.assertEqual([(r["container"], r["sync_state"], r["sync_reason"], r["customer_id"]) for r in shown],
                         [("TWOTAB00001", "CONFLICT", "NEEDS_BOOK", 7)])
        self.assertEqual([c["name"] for c in shown[0]["candidate_books"]], ["DUONG BO KHACH A 324", "KHACH B"])
        self.assertEqual(shown[0]["source_fingerprint"], source_fingerprint(queue["choices"][0]))
        self.assertIn("chọn sổ", shown[0]["message"])
        self.assertEqual(project_choices(queue, ledger(customer_id=8), CUSTOMERS), [])
        here = ledger(trips=[{"id": 5, "container": "TWOTAB00001", "event_date": "2026-10-06", "month": "2026-10-01"}], customer_id=7)
        self.assertEqual(project_choices(queue, here, CUSTOMERS), [])                                 # đã vào sổ này
        self.assertEqual(project_choices(queue, ledger(customer_id=7), CUSTOMERS, {"TWOTAB00001"}), [])   # đã vào sổ khác


class AssignRoadTripTests(unittest.TestCase):
    """`POST /api/v7/sheet/road/assign`: người chọn sổ cho chuyến bộ `NEEDS_BOOK`; dán bằng đúng đường của máy, dưới tên người bấm."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        folder = Path(self.dir.name)
        self.road, self.prices = folder / "road.json", folder / "prices.json"
        self.road.write_text(json.dumps({"sha256": SHA, "row_count": 1, "rows": [road_row(3, "TWOTAB00001", "2026-10-05")]}), encoding="utf-8")
        tabs = [tab_row("DUONG BO KHACH A 324", 1, "TWOTAB00001", "2026-10-05"), tab_row("KHACH B", 2, "TWOTAB00001", "2026-10-06")]
        self.prices.write_text(json.dumps({"sha256": "b" * 64, "row_count": 2, "rows": tabs}), encoding="utf-8")
        self.writes, self.versions = [], {7: 4, 8: 9}
        test = self

        class Runner:
            def run(self, function, payload, actor):
                if function == "list_customers":
                    return {"customers": CUSTOMERS}
                if function in ("list_sheet_trip_refs", "list_legacy_trip_refs"):
                    return {"items": []}
                if function == "get_ledger":
                    return {**ledger(customer_id=payload["customer_id"]), "version": test.versions[payload["customer_id"]], "events": []}
                if function == "paste_trips":
                    test.writes.append((payload, actor))
                    return {"trip_ids": [41], "pending_review": []}
                raise AssertionError(function)
        self.runner = Runner()
        for name, value in (("ROAD_SNAPSHOT_PATH", self.road), ("PRICE_SNAPSHOT_PATH", self.prices)):
            patcher = patch.object(v7_api_sheet, name, str(value))
            patcher.start()
            self.addCleanup(patcher.stop)
        v7_api_sheet._ROAD[:] = [None, None, None, None]

    def assign(self, **change):
        fingerprint = v7_api_sheet.road_projection(self.runner, {**ledger(customer_id=7), "version": 4}, "t")["items"][0]["source_fingerprint"]
        body = {"customer_id": 7, "expected_version": 4, "idempotency_key": "k-1", "target_customer_id": 8, "target_version": 9,
                "source_fingerprint": fingerprint, **change}
        return v7_api_sheet.assign_road_trip(json.dumps(body).encode(), self.runner, "nguoi-nhap")

    def test_the_chosen_book_gets_the_trip_without_price_under_the_person(self):
        status, out = self.assign()
        self.assertEqual((status, out["complete"], out["target_customer_id"]), (200, True, 8))
        payload, actor = self.writes[0]
        self.assertEqual((payload["customer_id"], payload["expected_version"], payload["debt_month"], actor), (8, 9, "2026-10-01", "nguoi-nhap"))
        trip = payload["trips"][0]
        self.assertEqual((trip["container"], trip["date"], trip["unitPriceVnd"], trip["note"], trip["src"]),
                         ("TWOTAB00001", "05/10/2026", None, NOTE, f"sheet:{SHA}:3"))

    def test_stale_or_foreign_choices_write_nothing(self):
        for change, code in (({"target_customer_id": 9}, "STALE_SHEET"), ({"source_fingerprint": "f" * 64}, "STALE_SHEET"),
                             ({"expected_version": 3}, "STALE_LEDGER"), ({"target_version": 8}, "STALE_LEDGER")):
            with self.assertRaises(v7_api_sheet.ApiError) as raised:
                self.assign(**change)
            self.assertEqual(raised.exception.code, code)
        with self.assertRaises(v7_api_sheet.ApiError):
            v7_api_sheet.assign_road_trip(b'{"customer_id": 7}', self.runner, "t")
        self.assertEqual(self.writes, [])


class OwnerBookTests(unittest.TestCase):
    """CHUYEN-BO-CHU-HANG-01: chuyến chưa ở tab nào lấy sổ theo CHỦ HÀNG khi chủ hàng đó chỉ từng vào một sổ."""

    HISTORY = (  # ba chuyến cũ của "CHU HANG X 379" tab đã xếp vào sổ 7; kho "KHO CHUNG" từng vào hai sổ
        (road_row(90, "HIST0000001", "2026-08-05", owner="CHU HANG X 379"), tab_row("DUONG BO KHACH A 324", 30, "HIST0000001", "2026-08-05", "2026-08")),
        (road_row(91, "HIST0000002", "2026-09-16", owner="Chu hang x  379"), tab_row("DUONG BO KHACH A 324", 31, "HIST0000002", "2026-09-16", "2026-09")),
        (road_row(92, "REUS0000001", "2026-09-20", owner="CHU HANG X 379"), tab_row("DUONG BO KHACH A 324", 32, "REUS0000001", "2026-09-20", "2026-09")),
        (road_row(93, "HIST0000004", "2026-09-01", owner="KHO CHUNG"), tab_row("DUONG BO KHACH A 324", 33, "HIST0000004", "2026-09-01", "2026-09")),
        (road_row(94, "HIST0000005", "2026-09-02", owner="KHO CHUNG"), tab_row("KHACH B", 34, "HIST0000005", "2026-09-02", "2026-09")),
        (road_row(95, "HIST0000006", "2026-09-03", owner="KHO CHUNG"), tab_row("KHACH B", 35, "HIST0000006", "2026-09-03", "2026-09")),
    )

    def build(self, road_rows, tab_rows=()):
        return build_road_queue({"sha256": SHA, "rows": [r for r, _ in self.HISTORY] + road_rows},
                                {"rows": [t for _, t in self.HISTORY] + list(tab_rows)}, CUSTOMERS)

    def test_reused_container_with_its_own_cont_bo_row_goes_to_the_owner_book(self):
        # Cùng container chuyến 20/9 (dòng tab đó đã có dòng CONT_BO nhận), chuyến 11/10 chưa ở tab nào.
        queue = self.build([road_row(2, "REUS0000001", "2026-10-11", owner="CHU HANG X 379")])
        self.assertEqual(queue["stats"], {"OWNER": 1})
        item = queue["items"][0]
        self.assertEqual((item["customer_id"], item["book_basis"], item["customer_tab"], item["tab_row"], item["tab_debt_month"]),
                         (7, "owner", None, None, "2026-10"))
        self.assertEqual((item["event_date"], item["owner"], item["src"], item["note"]),
                         ("2026-10-11", "CHU HANG X 379", f"sheet:{SHA}:2", NOTE))
        book = ledger(legacy=[{"id": 3, "kind": "trip", "month": "2026-09-01",
                               "current": {"container": "REUS0000001", "event_date": "2026-09-20", "month": "2026-09-01"}}])
        result = project_road(queue, book)
        self.assertEqual([(r["container"], r["sync_state"]) for r in result["items"]], [("REUS0000001", "NEW")])

    def test_unknown_owner_warehouse_and_too_few_trips_wait_for_the_tab(self):
        queue = self.build([road_row(2, "WAIT0000001", "2026-10-11", owner="KHO CHUNG"),       # kho: hai sổ
                            road_row(3, "WAIT0000002", "2026-10-11", owner="KHACH MOI 401"),   # chưa từng ghép
                            road_row(4, "WAIT0000003", "2026-10-11", owner="")])
        self.assertEqual((queue["items"], queue["stats"]), ([], {"NO_TAB": 3}))
        few = build_road_queue({"sha256": SHA, "rows": [self.HISTORY[0][0], self.HISTORY[1][0],
                                                        road_row(2, "WAIT0000004", "2026-10-11", owner="CHU HANG X 379")]},
                               {"rows": [self.HISTORY[0][1], self.HISTORY[1][1]]}, CUSTOMERS)
        self.assertEqual(few["stats"], {"NO_TAB": 1})   # mới hai chuyến: chưa đủ OWNER_MIN_TRIPS

    def test_unclaimed_tab_row_close_by_means_a_mistyped_date_so_it_waits(self):
        queue = self.build([road_row(2, "FARU0000001", "2026-10-11", owner="CHU HANG X 379"),
                            road_row(3, "FARU0000002", "2026-10-11", owner="CHU HANG X 379"),
                            road_row(4, "FARU0000003", "2026-10-11", owner="CHU HANG X 379")],
                           [tab_row("DUONG BO KHACH A 324", 50, "FARU0000001", "2026-10-25"),            # lệch 14 ngày
                            tab_row("KHACH B", 51, "FARU0000002", None, month="2026-09"),               # không ngày, tháng liền kề
                            tab_row("DUONG BO KHACH A 324", 52, "FARU0000003", "2026-06-02", "2026-06")])  # xa: chuyến khác
        self.assertEqual(queue["stats"], {"TAB_FAR": 2, "OWNER": 1})
        self.assertEqual([i["container"] for i in queue["items"]], ["FARU0000003"])

    def test_tab_far_trip_offers_the_owner_book_and_the_book_of_the_far_tab_row(self):
        """WEB-CHINH-01: tab Sheet đứng yên sau 1/12 thì chuyến chờ tab không bao giờ tự vào sổ; người chọn sổ trên web. Ứng viên là sổ
        của chủ hàng và sổ của dòng tab lệch ngày. Máy vẫn không tự đưa vào (vẫn đếm TAB_FAR, không có trong `items`)."""
        queue = self.build([road_row(2, "FARU0000001", "2026-10-11", owner="CHU HANG X 379"),
                            road_row(3, "FARU0000002", "2026-10-11", owner="CHU HANG X 379")],
                           [tab_row("DUONG BO KHACH A 324", 50, "FARU0000001", "2026-10-25"),
                            tab_row("KHACH B", 51, "FARU0000002", None, month="2026-09")])
        self.assertEqual((queue["items"], queue["stats"]), ([], {"TAB_FAR": 2}))
        self.assertEqual([(c["container"], c["candidate_ids"], c["choice_reason"], c["customer_id"]) for c in queue["choices"]],
                         [("FARU0000001", [7], "TAB_FAR", None), ("FARU0000002", [7, 8], "TAB_FAR", None)])

    def test_booking_name_set_on_the_web_places_an_owner_without_tab_history(self):
        """KHACH-WEB-01: chủ hàng quản lý đã gán tên booking cho sổ thì vào sổ đó dù chưa đủ chuyến tab đã xếp; tab có dòng lệch ngày
        chưa ai nhận thì vẫn chờ tab; hai dòng cùng container cách 2 ngày không thành hai chuyến."""
        customers = [{**CUSTOMERS[0], "booking_names": ["KHÁCH MỚI 401"]}, *CUSTOMERS[1:]]
        queue = build_road_queue({"sha256": SHA, "rows": [
            road_row(2, "NEWU1000001", "2026-11-05", owner="khách mới  401"),
            road_row(3, "NEWU1000002", "2026-11-06", owner="KHÁCH MỚI 401"),
            road_row(4, "NEWU1000003", "2026-11-07", owner="KHÁCH MỚI 401"), road_row(5, "NEWU1000003", "2026-11-09", owner="KHÁCH MỚI 401"),
            road_row(6, "NEWU1000004", "2026-11-08", owner="KHO LẠ")]},
            {"rows": [tab_row("KHACH B", 77, "NEWU1000002", "2026-11-20", month="2026-11")]}, customers)
        self.assertEqual([(item["container"], item["customer_id"], item["book_basis"]) for item in queue["items"]],
                         [("NEWU1000001", 7, "booking_name")])
        self.assertEqual(queue["stats"], {"BOOKING_NAME": 1, "TAB_FAR": 1, "AMBIGUOUS_SOURCE": 2, "NO_TAB": 1})

    def test_booking_name_respects_road_mode_tab_history_and_unicode(self):
        """Review KHACH-WEB-01: tên ở sổ ghi đi biển không dẫn chuyến bộ; sổ lưu trữ không nhận; tab đã đưa chủ hàng vào sổ khác thì
        tên web không thắng (về luật chủ hàng như trước); chữ gõ dạng tổ hợp (NFD) vẫn khớp; hai sổ cùng một khóa thì bỏ khóa."""
        customers = [{**CUSTOMERS[0], "booking_names": ["KHÁCH MỚI 401"]},
                     {**CUSTOMERS[1], "transport_mode": "CANG", "booking_names": ["CHU HANG BIEN"]},
                     {"id": 10, "name": "KHACH LUU TRU", "status": "active", "archived": True, "booking_names": ["CHU HANG CU"]},
                     {"id": 11, "name": "KHACH D", "status": "active", "transport_mode": "BO", "booking_names": ["CHU HANG A/B"]},
                     {"id": 12, "name": "KHACH E", "status": "active", "transport_mode": "BO", "booking_names": ["CHU HANG AB"]},
                     {"id": 13, "name": "KHACH F", "status": "active", "transport_mode": "BO", "booking_names": ["CHU HANG TAB"]}]
        rows = [road_row(2, "NEWU1000001", "2026-11-05", owner=unicodedata.normalize("NFD", "khách mới 401")),
                road_row(3, "NEWU1000002", "2026-11-06", owner="CHU HANG BIEN"),
                road_row(4, "NEWU1000003", "2026-11-07", owner="CHU HANG CU"),
                road_row(5, "NEWU1000004", "2026-11-08", owner="CHU HANG AB"),
                road_row(6, "TABU1000001", "2026-10-02", owner="CHU HANG TAB"),
                road_row(7, "NEWU1000005", "2026-11-09", owner="CHU HANG TAB")]
        queue = build_road_queue({"sha256": SHA, "rows": rows}, {"rows": [tab_row("KHACH B", 40, "TABU1000001", "2026-10-02")]}, customers)
        self.assertEqual([(item["container"], item["customer_id"], item["book_basis"]) for item in queue["items"]],
                         [("NEWU1000001", 7, "booking_name"), ("TABU1000001", 8, "tab")])
        self.assertEqual(queue["stats"], {"BOOKING_NAME": 1, "BOOK": 1, "NO_TAB": 4})
        self.assertEqual(queue["owner_books"], {"CHU HANG TAB": [8]})

    def test_same_container_twice_within_three_days_is_not_two_trips(self):
        queue = self.build([road_row(2, "TWIN0000001", "2026-10-11", owner="CHU HANG X 379"),
                            road_row(3, "TWIN0000001", "2026-10-13", owner="CHU HANG X 379"),
                            road_row(4, "TWIN0000001", "2026-11-20", owner="CHU HANG X 379")])   # xa: chuyến khác
        self.assertEqual(queue["stats"], {"OWNER": 1, "AMBIGUOUS_SOURCE": 2})
        self.assertEqual([i["event_date"] for i in queue["items"]], ["2026-11-20"])


class ProjectRoadTests(unittest.TestCase):
    def queue(self, *items):
        return build_road_queue({"sha256": SHA, "rows": [road_row(n, c, d) for n, c, d, _ in items]},
                                {"rows": [tab_row("DUONG BO KHACH A 324", 100 + n, c, d, month=m) for n, c, d, m in items]},
                                CUSTOMERS)

    def test_new_unless_already_in_the_book_within_three_days(self):
        queue = self.queue((2, "NEWU0000001", "2026-10-02", "2026-10"), (3, "WEBU0000001", "2026-10-10", "2026-10"),
                           (4, "LEGU0000001", "2026-10-12", "2026-10"), (5, "REUS0000001", "2026-10-20", "2026-10"))
        book = ledger(trips=[{"id": 1, "container": "WEBU0000001", "event_date": "2026-10-12", "month": "2026-10-01",
                              "status": "pending_review"},
                             {"id": 2, "container": "REUS0000001", "event_date": "2026-08-15", "month": "2026-08-01"}],
                      legacy=[{"id": 3, "kind": "trip", "month": "2026-10-01",
                               "current": {"container": "LEGU0000001", "event_date": None, "month": "2026-10-01"}}])
        result = project_road(queue, book)
        # Đã có (kể cả chờ kiểm, dòng sổ gốc không ngày cùng tháng) thì không hiện; container dùng lại xa ngày là chuyến mới.
        self.assertEqual([(r["container"], r["sync_state"]) for r in result["items"]],
                         [("NEWU0000001", "NEW"), ("REUS0000001", "NEW")])
        self.assertEqual((result["new_count"], result["conflict_count"], result["snapshot_sha256"]), (2, 0, SHA))
        self.assertEqual(project_road(queue, ledger(customer_id=8))["items"], [])

    def test_other_books_and_month_mismatch_go_to_people(self):
        queue = self.queue((2, "OTHC0000001", "2026-10-02", "2026-10"), (3, "OTHL0000001", "2026-10-03", "2026-10"),
                           (4, "FAML0000001", "2026-10-04", "2026-10"), (5, "MONU0000001", "2026-10-31", "2026-11"))
        legacy = [{"customer_id": 8, "container": "OTHL0000001", "event_date": "2026-10-04", "debt_month": "2026-10-01"},
                  {"customer_id": 9, "container": "FAML0000001", "event_date": None, "debt_month": "2026-10-01"}]
        result = project_road(queue, ledger(), {"OTHC0000001"}, legacy, family_ids={9})
        self.assertEqual([(r["container"], r["sync_state"], r["sync_reason"]) for r in result["items"]],
                         [("OTHC0000001", "CONFLICT", "OTHER_CUSTOMER"), ("OTHL0000001", "CONFLICT", "OTHER_BOOK_LEGACY"),
                          ("MONU0000001", "CONFLICT", "MONTH_DIFFERS")])
        self.assertTrue(all(r["message"] for r in result["items"]))


class RoadProjectionApiTests(unittest.TestCase):
    """`road_projection`: không có road.json thì không có việc; có thì chặn sổ khác bằng đúng hàm của chuyến biển."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        folder = Path(self.dir.name)
        self.road, self.prices = folder / "road.json", folder / "prices.json"
        rows = [road_row(2, "FAKU1000001", "2026-10-02"), road_row(3, "FAKU1000003", "2026-10-02")]
        self.road.write_text(json.dumps({"sha256": SHA, "row_count": 2, "rows": rows}), encoding="utf-8")
        tabs = [tab_row("DUONG BO KHACH A 324", 382, "FAKU1000001", "2026-10-02"),
                tab_row("DUONG BO KHACH A 324", 383, "FAKU1000003", "2026-10-02")]
        self.prices.write_text(json.dumps({"sha256": "b" * 64, "row_count": 2, "rows": tabs}), encoding="utf-8")
        self.calls = []
        test = self

        class Runner:
            def run(self, function, payload, actor):
                test.calls.append(function)
                if function == "list_customers":
                    return {"customers": CUSTOMERS}
                if function == "list_sheet_trip_refs":
                    return {"items": [{"customer_id": 8, "container": "FAKU1000003"}]}
                if function == "get_ledger":
                    return ledger(trips=[{"id": 5, "container": "FAKU1000003", "event_date": "2026-10-03"}], customer_id=8)
                if function == "list_legacy_trip_refs":
                    return {"items": []}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def test_missing_file_is_no_work_and_present_file_blocks_other_customers(self):
        with patch.object(v7_api_sheet, "ROAD_SNAPSHOT_PATH", str(Path(self.dir.name) / "none.json")):
            empty = v7_api_sheet.road_projection(self.runner, ledger(), "t")
        self.assertEqual((empty["items"], empty.get("source_missing"), self.calls), ([], True, []))
        with patch.object(v7_api_sheet, "ROAD_SNAPSHOT_PATH", str(self.road)), \
                patch.object(v7_api_sheet, "PRICE_SNAPSHOT_PATH", str(self.prices)):
            result = v7_api_sheet.road_projection(self.runner, ledger(), "t")
        self.assertEqual([(r["container"], r["sync_state"], r["sync_reason"]) for r in result["items"]],
                         [("FAKU1000001", "NEW", ""), ("FAKU1000003", "CONFLICT", "OTHER_CUSTOMER")])

    def test_paste_keeps_the_road_source_and_note(self):
        pasted = []

        class Runner:
            def run(self, function, payload, actor):
                pasted.append(payload)
                return {"trip_ids": [41], "pending_review": []}
        item = {"source_row": 2, "container": "FAKU1000001", "event_date": "2026-10-02", "carrier": "99Z-00001",
                "origin": NO_WAREHOUSE, "destination": "CHIMA", "shipper": None, "booking": "",
                "src": f"sheet:{SHA}:2", "note": NOTE}
        result = v7_api_sheet.paste_sheet_rows(Runner(), 7, 3, SHA, "k", [item], "may")
        trip = pasted[0]["trips"][0]
        self.assertEqual((trip["src"], trip["note"], trip["from"], trip["to"], trip["date"], trip["unitPriceVnd"]),
                         (f"sheet:{SHA}:2", NOTE, NO_WAREHOUSE, "CHIMA", "02/10/2026", None))
        self.assertEqual((pasted[0]["debt_month"], result["pasted"]), ("2026-10-01", [{"source_row": 2, "trip_id": 41}]))


class RoadWithoutPriceSnapshotTests(unittest.TestCase):
    """WEB-CHINH-01, tắt máy 1/12/2026: thôi đọc Sheet sổ nợ thì có thể không còn bản chụp giá. Chuyến bộ khi đó chỉ theo tên booking gán
    trên web (KHACH-WEB-01), không ném lỗi; bản chụp có mà hỏng thì vẫn ném. Cùng dữ liệu với `RoadProjectionApiTests`."""

    setUp = RoadProjectionApiTests.setUp
    tearDown = RoadProjectionApiTests.tearDown

    def test_missing_price_snapshot_is_not_an_error(self):
        with patch.object(v7_api_sheet, "ROAD_SNAPSHOT_PATH", str(self.road)), \
                patch.object(v7_api_sheet, "PRICE_SNAPSHOT_PATH", str(Path(self.dir.name) / "none.json")):
            result = v7_api_sheet.road_projection(self.runner, ledger(), "t")
        self.assertEqual(result["items"], [])   # không tab, không tên gán: chưa rõ sổ, chờ người

    def test_broken_price_snapshot_still_raises(self):
        self.prices.write_text("{", encoding="utf-8")
        with patch.object(v7_api_sheet, "ROAD_SNAPSHOT_PATH", str(self.road)), \
                patch.object(v7_api_sheet, "PRICE_SNAPSHOT_PATH", str(self.prices)), self.assertRaises(ValueError):
            v7_api_sheet.road_projection(self.runner, ledger(), "t")


if __name__ == "__main__":
    unittest.main()
