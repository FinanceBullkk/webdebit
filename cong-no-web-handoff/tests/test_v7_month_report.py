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


if __name__ == "__main__":
    unittest.main()
