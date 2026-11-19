"""GET /api/v7/report/month (BAO-CAO-THANG-01): ghép chuyến web với dòng Sheet, đếm theo khách và biển/bộ. Dữ liệu giả."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_ledger_api as api
import v7_month_missing as missing
import v7_month_report as report
from v7_api_validate import ApiError

NOW = datetime.fromisoformat("2026-11-16T10:30:00+07:00")


def row(tab, cont, status, family="BIEN", date=None, booking=None, amount=None, block="2026-10", line=1):
    return {"tab": tab, "row": line, "block": block, "cont": cont, "family": family, "amount_vnd": amount, "date": date,
            "status": status, **({"booking": {"date": booking, "owner": "CHU HANG", "ref": "BK"}} if booking else {})}


OCTOBER = [
    row("KHACH A", "AAAU1000001", "khop", date="2026-10-03", booking="2026-10-03", amount="90000000"),
    row("KHACH A", "AAAU1000002", "khop", date="2026-10-04", booking="2026-10-04", amount="80000000"),
    row("KHACH A COPY", "AAAU1000001", "chep", date="2026-10-03"),
    row("KHACH A", "BBBU1000003", "khong_ngay", amount="7000000"),
    row("KHACH B", "CCCU1000004", "khop", family="BO", date="2026-10-12", booking="2026-10-12", amount="50000000"),
    row("KHACH B", "DDDU1000005", "thieu", family="BO", booking="2026-10-20"),
    row(None, "EEEU1000006", "thieu", booking="2026-10-21"),
]
FILE = {"version": 1, "checked_at": "2026-11-16T10:09:00+07:00", "start": "2025-12", "end": "2026-11",
        "before_book": {"2026-10": 2}, "months": {"2026-10": OCTOBER}}
WEB = {"month": "2026-10-01",
       "books": [{"id": 1, "name": "KHACH A", "commodity": "Dừa", "transport_mode": "CANG"},
                 {"id": 2, "name": "KHACH  B", "commodity": None, "transport_mode": "BO"},
                 {"id": 3, "name": "KHACH C", "commodity": "Sầu riêng", "transport_mode": "CANG"}],
       "trips": [{"customer_id": 1, "date": "2026-10-05", "container": "aaau 1000001", "source": "web"},   # lệch 2 ngày: vẫn ghép
                 {"customer_id": 1, "date": "2026-09-29", "container": "ZZZU1000009", "source": "web"},   # ngoài tháng: không đếm
                 {"customer_id": 2, "date": "2026-10-12", "container": "CCCU1000004", "source": "legacy"},
                 {"customer_id": 3, "date": "2026-10-15", "container": "FFFU1000007", "source": "web"}]}


class MonthReportTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        patcher = mock.patch.dict(os.environ, {"WEBDEBIT_MACHINE_DIR": str(self.dir)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, data=FILE):
        (self.dir / "booking-report.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_counts_by_customer_and_family(self):
        body = report.build("2026-10", json.loads(json.dumps(FILE)), WEB, NOW)
        self.assertEqual((body["state"], body["before_book"], body["current"]), ("ok", 2, False))
        total = body["totals"]["ALL"]
        self.assertEqual((total["booking"], total["sheet"], total["web"], total["thieu"]), (5, 3, 3, 2))
        self.assertEqual((body["totals"]["BIEN"]["booking"], body["totals"]["BO"]["booking"]), (3, 2))
        people = {item["name"] or item["owner"]: item for item in body["customers"]}
        a = people["KHACH A"]
        self.assertEqual((a["book_id"], a["commodity"], a["families"]), (1, "Dừa", ["BIEN"]))
        self.assertEqual((a["booking"], a["sheet"], a["web"], a["web_thieu"], a["khong_ngay"]), (2, 2, 1, 1, 1))
        self.assertEqual(a["amount_vnd"], "177000000", "chuyến và dòng không ngày, không có bản chép")
        b = people["KHACH B"]   # tên sổ web có hai khoảng trắng vẫn ghép
        self.assertEqual((b["book_id"], b["booking"], b["sheet"], b["web"], b["thieu"]), (2, 2, 1, 1, 1))
        c = people["KHACH C"]
        self.assertEqual((c["booking"], c["sheet"], c["web"], c["chi_web"], c["rows"][0]["status"]), (0, 0, 1, 1, "chi_web"))
        self.assertEqual(people["KHACH A COPY"]["chep"], 1)
        self.assertEqual(people["CHU HANG"]["name"], None, "chuyến booking chưa rõ sổ: gom theo chủ hàng")
        self.assertEqual(body["customers"][0]["issues"] > 0, True, "khách có lệch lên đầu")

    def test_undated_sheet_row_does_not_take_the_web_trip_of_a_dated_row(self):
        rows = [row("KHACH T", "SEGU1000008", "khong_ngay", amount="57000000"),
                row("KHACH T", "SEGU1000008", "khop", date="2026-10-07", booking="2026-10-07", amount="49500000", block="2026-11")]
        web = {"books": [{"id": 5, "name": "KHACH T", "commodity": None, "transport_mode": "CANG"}],
               "trips": [{"customer_id": 5, "date": "2026-10-07", "container": "SEGU1000008", "source": "web"}]}
        body = report.build("2026-10", {**FILE, "months": {"2026-10": rows}}, web, NOW)
        tank = body["customers"][0]
        self.assertEqual((tank["web"], tank["web_thieu"], tank["khong_ngay"]), (1, 0, 1))
        self.assertEqual([r["status"] for r in tank["rows"] if r.get("web")], ["khop"])

    def test_booking_trip_not_on_sheet_takes_the_web_trip_of_any_book(self):
        """BAO-CAO-THANG-02: Sheet chưa ghi thì tab chỉ là sổ đoán; máy đặt chuyến theo mặt hàng/chủ hàng ở sổ khác."""
        rows = [row("KHACH A", "MOVU1000001", "thieu", booking="2026-10-10", block=None, line=None),   # web ở sổ C, lệch 1 ngày
                row("KHACH A", "MOVU1000002", "thieu", booking="2026-10-11", block=None, line=None),   # không sổ nào có
                row("KHACH A", "STAY1000003", "khop", date="2026-10-12", booking="2026-10-12", amount="1")]   # Sheet đã ghi: giữ sổ
        web = {"books": WEB["books"],
               "trips": [{"customer_id": 3, "date": "2026-10-11", "container": "MOVU1000001", "source": "web"},
                         {"customer_id": 3, "date": "2026-10-12", "container": "STAY1000003", "source": "web"}]}
        body = report.build("2026-10", {**FILE, "months": {"2026-10": rows}}, web, NOW)
        people = {item["name"]: item for item in body["customers"]}
        moved = next(r for r in people["KHACH C"]["rows"] if r["cont"] == "MOVU1000001")
        self.assertEqual((moved["status"], moved["web"]["date"], moved["guess_tab"], moved["book_id"]), ("thieu", "2026-10-11", "KHACH A", 3))
        self.assertEqual((people["KHACH C"]["booking"], people["KHACH C"]["web"], people["KHACH C"]["chi_web"]), (1, 2, 1),
                         "dòng Sheet đã ghi không đổi sổ: chuyến web ở sổ khác vẫn là chỉ có trên web")
        a = people["KHACH A"]
        self.assertEqual((a["booking"], a["web"], a["web_thieu"], a["thieu_web"], a["web_chua"]), (2, 0, 1, 1, 2))
        total = body["totals"]["ALL"]
        self.assertEqual((total["booking"], total["web"], total["web_chua"], total["chi_web"]), (3, 2, 2, 1))

    def test_month_outside_the_report_and_missing_file_show_web_only(self):
        body = report.build("2025-10", FILE, WEB, NOW)
        self.assertEqual((body["state"], body["totals"]["ALL"]["booking"], body["totals"]["ALL"]["sheet"]), ("outside", None, None))
        body = report.build("2026-10", None, WEB, NOW)
        self.assertEqual((body["state"], body["totals"]["ALL"]["web"]), ("none", 3))

    def test_old_report_is_stale(self):
        old = {**FILE, "checked_at": "2026-11-16T07:09:00+07:00"}
        self.assertEqual(report.build("2026-10", old, WEB, NOW)["state"], "stale")

    def request(self, target, web=WEB):
        runner = mock.Mock()
        runner.run.return_value = web
        status, body = api.handle("GET", target, {"Host": "127.0.0.1:8780"}, b"", runner, port=8780, host="127.0.0.1", actor="nguoi@test")
        return status, body, runner

    def test_route_reads_the_file_and_the_month_from_the_database(self):
        self.write()
        status, body, runner = self.request("/api/v7/report/month?month=2026-10")
        self.assertEqual((status, body["month"], body["totals"]["ALL"]["booking"]), (200, "2026-10", 5))
        runner.run.assert_called_once_with("get_trip_month", {"month": "2026-10-01"}, "nguoi@test")
        with mock.patch.object(report, "datetime") as clock:
            clock.now.return_value, clock.fromisoformat = NOW, datetime.fromisoformat
            _, body, runner = self.request("/api/v7/report/month")
        self.assertEqual(body["month"], "2026-11", "không chọn tháng thì là tháng hiện tại giờ VN")
        for bad in ("month=2026-13", "month=2026-1", "month=2099-01", "month=2026-10&x=1", "x=1"):
            with self.subTest(bad=bad), self.assertRaises(ApiError) as caught:
                self.request(f"/api/v7/report/month?{bad}")
            self.assertEqual(caught.exception.code, "INVALID_MONTH")

    def test_page_and_scripts_are_served(self):
        for name in ("/bao-cao-thang.html", "/bao-cao-thang-model.js", "/bao-cao-thang-ui.js", "/bao-cao-thang.css"):
            with self.subTest(name=name):
                self.assertIn(name, api.ASSETS)


# BAO-CAO-THANG-02: dữ liệu giả cho MissingReasonTests.
MISS_ROWS = [row("KHACH A", "REUS1000001", "thieu", booking="2026-11-04"), row("KHACH A", "NOBK1000002", "thieu", booking="2026-11-05"),
             row("KHACH A", "MISM1000003", "thieu", booking="2026-11-06"), row("KHACH A", "NEWT1000004", "thieu", booking="2026-11-07"),
             row("KHACH A", "LOCK1000005", "khop", date="2026-09-08", booking="2026-09-08"),
             row("KHACH B", "ROAD1000006", "thieu", family="BO", booking="2026-11-09"),
             row("KHACH B", "ROAD1000007", "thieu", family="BO", booking="2026-11-10"),
             row("KHACH A", "GONE1000008", "thieu", booking="2026-11-11"), row("KHACH A", "SOON1000009", "thieu", booking="2026-11-20")]
MISS_SEA = {("REUS1000001", "2026-11-04"): {"status": "READY", "customer_id": 1, "book_match": "COMMODITY_OK"},
            ("NOBK1000002", "2026-11-06"): {"status": "READY", "customer_id": None, "book_match": None},   # lệch 1 ngày vẫn là dòng này
            ("MISM1000003", "2026-11-06"): {"status": "READY", "customer_id": 1, "book_match": "COMMODITY_MISMATCH"},
            ("NEWT1000004", "2026-11-07"): {"status": "READY", "customer_id": 1, "book_match": "COMMODITY_OK"},
            ("LOCK1000005", "2026-09-08"): {"status": "READY", "customer_id": 1, "book_match": "COMMODITY_OK"}}
MISS_ROAD = ({("ROAD1000006", "2026-11-09"): {"customer_id": 2}}, {("ROAD1000007", "2026-11-10"): "NO_TAB"})
MISS_LEDGER = {1: {"customer_id": 1, "today_month": "2026-11-01", "month_locks": [{"month": "2026-09-01", "locked": True}]},
               2: {"customer_id": 2, "today_month": "2026-11-01"}}
MISS_PROJECTION = {1: {"items": [{"container": "NEWT1000004", "event_date": "2026-11-07", "sync_state": "NEW"},
                                 {"container": "LOCK1000005", "event_date": "2026-09-08", "sync_state": "NEW"}],
                       "waiting_items": [{"container": "REUS1000001", "event_date": "2026-11-04", "sync_state": "WAITING",
                                          "sync_reason": "CONTAINER_REUSED_OR_CHANGED"}]},
                   2: {"items": [{"container": "ROAD1000006", "event_date": "2026-11-09", "sync_state": "CONFLICT", "sync_reason": "MONTH_DIFFERS"}]}}


class MissingReasonTests(unittest.TestCase):
    """BAO-CAO-THANG-02: GET /api/v7/report/month/missing, lý do máy chưa đưa chuyến booking vào web. Dữ liệu giả."""

    def body(self):
        return report.build("2026-11", {**FILE, "months": {"2026-11": MISS_ROWS}}, {"books": WEB["books"][:2], "trips": []}, NOW)

    def test_each_trip_gets_the_reason_the_machine_sees(self):
        rows = missing.missing_rows(self.body())
        self.assertEqual(len(rows), 9, "mọi chuyến booking không có chuyến web, kể cả dòng Sheet đã ghi")
        with mock.patch.object(missing, "_sea_queue", return_value=MISS_SEA), \
                mock.patch.object(missing, "_road_queue", return_value=MISS_ROAD), \
                mock.patch.object(missing, "_project", side_effect=lambda r, a, book, road: (MISS_LEDGER[book], MISS_PROJECTION[book])) as project:
            out = {item["cont"]: (item["reason"], item["machine_book"]) for item in missing.explain(rows, None, "nguoi@test", "2026-11-16")}
        self.assertEqual(out, {
            "REUS1000001": ("CONTAINER_REUSED_OR_CHANGED", 1), "NOBK1000002": ("NO_BOOK", None),
            "MISM1000003": ("COMMODITY_MISMATCH", 1), "NEWT1000004": ("NEXT_RUN", 1), "LOCK1000005": ("MONTH_LOCKED", 1),
            "ROAD1000006": ("NEEDS_REVIEW", 2), "ROAD1000007": ("ROAD_NO_TAB", None),
            "GONE1000008": ("NOT_IN_SOURCE", None), "SOON1000009": ("FUTURE", None)})
        self.assertEqual(sorted((call.args[2], call.args[3]) for call in project.call_args_list), [(1, False), (2, True)],
                         "mỗi sổ chiếu một lần")

    def test_a_broken_source_or_book_leaves_unknown_not_a_guess(self):
        rows = missing.missing_rows(self.body())
        with mock.patch.object(missing, "_sea_queue", side_effect=ValueError("Sheet snapshot unavailable")), \
                mock.patch.object(missing, "_road_queue", return_value=MISS_ROAD), \
                mock.patch.object(missing, "_project", side_effect=ApiError(503, "X", "x")):
            out = {item["cont"]: item["reason"] for item in missing.explain(rows, None, "nguoi@test", "2026-11-16")}
        self.assertEqual((out["REUS1000001"], out["ROAD1000006"], out["ROAD1000007"]), ("UNKNOWN", "UNKNOWN", "ROAD_NO_TAB"))

    def test_route(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        Path(folder.name, "booking-report.json").write_text(json.dumps({**FILE, "months": {"2026-11": MISS_ROWS[:1]}}), encoding="utf-8")
        runner = mock.Mock()
        runner.run.return_value = {"books": WEB["books"][:1], "trips": []}
        with mock.patch.dict(os.environ, {"WEBDEBIT_MACHINE_DIR": folder.name}), \
                mock.patch.object(missing, "explain", side_effect=lambda rows, *_: [{**r, "reason": "X"} for r in rows]):
            status, body = api.handle("GET", "/api/v7/report/month/missing?month=2026-11", {"Host": "127.0.0.1:8780"}, b"", runner,
                                      port=8780, host="127.0.0.1", actor="nguoi@test")
        self.assertEqual((status, body["month"], [(r["cont"], r["reason"], r["owner"]) for r in body["rows"]]),
                         (200, "2026-11", [("REUS1000001", "X", "CHU HANG")]))
        with self.assertRaises(ApiError) as caught:
            api.handle("GET", "/api/v7/report/month/missing?month=2099-01", {"Host": "127.0.0.1:8780"}, b"", runner,
                       port=8780, host="127.0.0.1", actor="nguoi@test")
        self.assertEqual(caught.exception.code, "INVALID_MONTH")


if __name__ == "__main__":
    unittest.main()
