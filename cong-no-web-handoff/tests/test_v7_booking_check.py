"""Kiểm Sheet sổ nợ so với booking (KIEM-BOOKING-01): bản chụp nguồn thành chuyến, phân nhóm cho trang, lỗi giữ kết quả cũ. Dữ liệu giả."""

import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import v7_booking_check as job

NOW = dt.datetime(2026, 11, 13, 10, 0, tzinfo=job.VN)
FAKE = "KHACH-GIA-ZQ"


def sheet(tab, row, cont, day, amount=40_000_000, mode="CANG", month=None):
    return {"tab": tab, "row": row, "cont": cont, "date": day, "raw_date": day or "", "month": month or day[:7], "amount": amount, "mode": mode}


def sea(cont, day, owner="KHACH A", line=2):
    return {"container": cont, "event_date": day, "customer_name": owner, "booking": "BK", "source_row": line, "status": "READY"}


def road(cont, day, owner="KHACH A", line=2):
    return {"container": cont, "event_date": day, "owner": owner, "plate": "51C-1", "source_row": line, "status": "READY"}


SHEET = [
    sheet("A", 1, "DUPU1111111", "2026-03-10"), sheet("B", 1, "DUPU1111111", "2026-03-10"),                  # tính hai lần cùng ngày
    sheet("A", 2, "GANU2222222", "2026-04-01"), sheet("A", 3, "GANU2222222", "2026-04-03"),                  # dòng thứ hai lệch 2 ngày
    sheet("A", 4, "NONU4444444", "2026-03-15"),                                                              # booking không có
    sheet("A", 5, "OLDU5555555", "2025-06-10"),                                                              # trước khoảng kiểm
    sheet("A", 6, "OTHU8888888", "2026-04-10"),                                                              # booking ghi khách khác
    sheet("B", 2, "BBBU1212121", "2026-03-20"),
    sheet("A BO", 1, "ROAU6666666", "2026-05-05", mode="BO"), sheet("A BO", 2, "ROBU7777777", "2026-05-06", mode="BO"),
    sheet("A BO", 3, "ROCU7777777", "2026-05-07", mode="BO"),
]
SEA = [sea("DUPU1111111", "2026-03-10"), sea("GANU2222222", "2026-04-01"), sea("OTHU8888888", "2026-04-10", owner="KHACH Z"),
       sea("BBBU1212121", "2026-03-20", owner="KHACH B"), sea("MISU9999999", "2026-04-20"), sea("QQQU1313131", "2026-04-22", owner="KHACH Q"),
       sea("BEFU1414141", "2025-12-05", owner="KHACH B"), sea("NEWU1515151", "2026-11-02"),
       sea("JUNK1616161", "1899-12-30"), sea("MISU9999999", "2026-04-20", line=9), sea("", "2026-04-01")]
ROAD = [road("ROAU6666666", "2026-05-05", owner="KHO X"), road("ROBU7777777", "2026-05-06"), road("ROCU7777777", "2026-05-07")]


class BookingCheckTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.out = self.dir / "booking-check.json"

    def snapshot(self, name, rows, created=NOW - dt.timedelta(minutes=10)):
        path = self.dir / name
        path.write_text(json.dumps({"rows": rows, "sha256": "x", "runner": {"created_at": created.isoformat()}}), encoding="utf-8")
        return path

    def check(self, sheet_rows=SHEET, sea_rows=SEA, road_rows=ROAD):
        with mock.patch.object(job.match, "load_sheet", return_value=[dict(row) for row in sheet_rows]):
            return job.check(Path("so-goc.xlsx"), self.snapshot("snapshot.json", sea_rows), self.snapshot("road.json", road_rows), NOW)

    def test_snapshot_rows_become_source_trips(self):
        rows, stats, fix = job.snapshot_sources({"rows": SEA}, {"rows": [*ROAD, road("DUPU1111111", "2026-03-11")]})
        self.assertEqual(stats, {"dong_thieu_ngay": 1, "dong_lap_cung_ngay": 1, "dong_khong_phai_chuyen": 1, "dong_lap_tab_truoc": 1})
        self.assertEqual({(row["tab"], row["family"]) for row in rows}, {("CONT_NGUON", "BIEN"), ("CONT_BO", "BO")})
        self.assertEqual(rows[0], {"family": "BIEN", "tab": "CONT_NGUON", "line": 2, "cont": "DUPU1111111", "date": "2026-03-10",
                                   "owner": "KHACH A", "ref": "BK", "price": ""})
        self.assertEqual([row["cont"] for row in fix], ["JUNK1616161"])

    def test_booking_rows_to_fix_and_rows_that_are_not_trips(self):
        """Lọc nhiễu 24/11/2026: dòng tổng, dòng tiêu đề mặt hàng không phải chuyến; chuyến có số container mà thiếu ngày thì liệt kê
        theo tab nguồn và dòng nguồn để người giữ booking sửa."""
        sea_rows = [{**sea("", None), "source_date": "04/11/1900", "event_date": "1900-11-04"},          # dòng cuối tab tháng
                    {**sea("THANHLONG", None), "source_date": ""},                                     # tiêu đề mặt hàng
                    {**sea("OERU4400262", None, owner="KHACH S", line=268), "source_date": "/", "source_tab": "THÁNG 08/2026",
                     "source_line": "41", "status": "INVALID"},
                    {**sea("FBIU5751189", "1900-01-21", line=315), "source_date": "21/01/1900"}]           # số cont thật, ngày rác
        road_rows = [{**road("CRLU1220757", None, owner="KHO R", line=91), "source_date": "", "status": "INVALID"},
                     road("ROAU6666666", "2026-05-05")]
        _, stats, fix = job.snapshot_sources({"rows": sea_rows}, {"rows": road_rows})
        self.assertEqual(stats, {"dong_khong_phai_chuyen": 2, "dong_thieu_ngay": 3})
        self.assertEqual(fix, [
            {"family": "BIEN", "tab": "CONT_NGUON", "line": 315, "cont": "FBIU5751189", "owner": "KHACH A", "ref": "BK", "raw_date": "21/01/1900"},
            {"family": "BIEN", "tab": "THÁNG 08/2026", "line": "41", "cont": "OERU4400262", "owner": "KHACH S", "ref": "BK", "raw_date": "/"},
            {"family": "BO", "tab": "CONT_BO", "line": 91, "cont": "CRLU1220757", "owner": "KHO R", "ref": "51C-1", "raw_date": ""}])
        result = self.check(sea_rows=[*SEA, *sea_rows], road_rows=[*ROAD, *road_rows[:1]])
        self.assertEqual([row["cont"] for row in result["booking_fix"]], ["JUNK1616161", "FBIU5751189", "OERU4400262", "CRLU1220757"])
        self.assertEqual(job.counts_line(result)["booking_fix"], 4)

    def test_missing_trip_counts_booking_trips_and_book_rows_of_the_container(self):
        rows = [*SHEET, sheet("A", 7, "MISU9999999", "2026-04-01"), sheet("A", 8, "MISU9999999", None, month="2026-05")]
        result = self.check(rows, [*SEA, sea("MISU9999999", "2026-04-02"), sea("MISU9999999", "2026-05-14")])
        missing = next(row for row in result["rows"] if row["code"] == "CHUA_TINH")
        self.assertEqual((missing["source"]["date"], missing["near"]), ("2026-04-20", {"booking": 3, "sheet": 2}))
        self.assertTrue(all(row["near"] is None for row in result["rows"] if row["group"] != "missing"))

    def test_groups_for_the_page(self):
        result = self.check()
        self.assertEqual(result["counts"], {"dup": 3, "missing": 2, "other": 1, "nosource": 1, "date": 0, "nodate": 0, "recent": 1})
        codes = {(row["code"], row["container"]) for row in result["rows"]}
        self.assertEqual(codes, {("TRUNG", "DUPU1111111"), ("TRUNG_GAN", "GANU2222222"), ("CHUA_TINH", "MISU9999999"),
                                 ("CHU_HANG_CHUA_GHEP", "QQQU1313131"), ("KHAC_KHACH", "OTHU8888888"), ("KHONG_NGUON", "NONU4444444"),
                                 ("THANG_CUOI", "NEWU1515151")})
        # Trước khi tab có sổ thì nằm trong số dư đầu kỳ; khách khác ở chuyến bộ không xét (khách theo sổ): chỉ đếm.
        self.assertEqual(result["hidden"], {"TRUOC_KHI_CO_SO": 1, "KHAC_KHACH": 1})
        twice = [row for row in result["rows"] if row["code"] == "TRUNG"]
        self.assertEqual([(row["tab"], row["paired"], (row["source"] or {}).get("date"), row["near_trips"]) for row in twice],
                         [("A", True, "2026-03-10", 1), ("B", False, None, 1)])
        near = next(row for row in result["rows"] if row["code"] == "TRUNG_GAN")
        self.assertEqual((near["tab"], near["row"], near["pair"], near["paired"]), ("A", 3, {"tab": "A", "row": 2, "date": "2026-04-01"}, False))
        missing = next(row for row in result["rows"] if row["code"] == "CHUA_TINH")
        self.assertEqual((missing["tab"], missing["amount_vnd"], missing["suggest"]), (None, None, {"tab": "A", "from": "2025-06"}))
        self.assertEqual(missing["source"]["date"], "2026-04-20")
        self.assertEqual(next(row for row in result["rows"] if row["code"] == "KHONG_NGUON")["amount_vnd"], "40000000")
        self.assertEqual([row["group"] for row in result["rows"]], sorted((row["group"] for row in result["rows"]), key=job.ORDER.index))
        self.assertEqual((result["window"], result["sheet"]), ({**job.WINDOW, "end": "2026-11"}, {"rows": 10, "paired": 7}))

    def test_plate_fee_line_and_zero_copy_on_the_page_and_in_the_month_report(self):
        rows = [sheet("CH", 1, "51C11111", None, month="2026-08", mode="BO"), sheet("CH", 2, "THUE", None, month="2026-08", mode="BO"),
                sheet("M", 1, "NYKU1000003", "2026-08-29", amount=0), sheet("M", 2, "NYKU1000003", "2026-09-01", month="2026-09")]
        with mock.patch.object(job.match, "load_sheet", return_value=[dict(row) for row in rows]):
            result, report = job.evaluate(Path("so-goc.xlsx"), self.snapshot("snapshot.json", [sea("NYKU1000003", "2026-08-29")]),
                                          self.snapshot("road.json", [{**road("TTLU1000005", "2026-08-17"), "plate": "51C-111.11"}]), NOW)
        self.assertEqual({(row["code"], row["container"]) for row in result["rows"]},
                         {("NGAY_TU_NGUON", "51C11111"), ("LECH_NGAY", "NYKU1000003")})
        self.assertEqual(result["hidden"], {"KHONG_PHAI_CONT": 1})
        got = sorted((row["cont"], row["status"], row["amount_vnd"]) for rows in report["months"].values() for row in rows)
        self.assertEqual(got, [("51C11111", "khop", "40000000"), ("NYKU1000003", "chep", None), ("NYKU1000003", "lech_ngay", "40000000"),
                               ("THUE", "khong_ngay", "40000000")])

    def test_old_and_road_duplicates_stay_inside_the_window(self):
        rows = [sheet("A", 1, "OLDU5555555", "2025-06-10"), sheet("B", 1, "OLDU5555555", "2025-06-10"),
                sheet("A BO", 1, "ROAU6666666", "2025-09-01", mode="BO"), sheet("B BO", 1, "ROAU6666666", "2025-09-01", mode="BO")]
        result = self.check(rows, SEA, [road("ROAU6666666", "2025-09-01")])
        self.assertEqual([(row["code"], row["container"]) for row in result["rows"] if row["group"] == "dup"], [("TRUNG", "ROAU6666666")] * 2)
        self.assertEqual(result["hidden"]["TRUNG"], 2)

    def test_bad_sources_are_errors_not_empty_results(self):
        fresh = self.snapshot("ok.json", ROAD)
        for name, body, code in (("missing.json", None, "SEA_MISSING"), ("broken.json", "{", "SEA_UNREADABLE"),
                                 ("empty.json", {"rows": [], "runner": {"created_at": NOW.isoformat()}}, "SEA_EMPTY"),
                                 ("old.json", {"rows": SEA, "runner": {"created_at": (NOW - dt.timedelta(hours=4)).isoformat()}}, "SEA_STALE"),
                                 ("naive.json", {"rows": SEA, "runner": {"created_at": "2026-11-13T09:00:00"}}, "SEA_STALE")):
            path = self.dir / name
            if body is not None:
                path.write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")
            with self.subTest(code=code), self.assertRaises(job.CheckError) as caught:
                job.check(Path("x.xlsx"), path, fresh, NOW)
            self.assertEqual(caught.exception.code, code)

    def test_failure_keeps_the_last_good_result_and_success_clears_the_error(self):
        sea_path, road_path = self.snapshot("snapshot.json", SEA), self.snapshot("road.json", ROAD)
        with mock.patch.object(job.match, "load_sheet", return_value=[dict(row) for row in SHEET]), mock.patch("sys.stderr"):
            self.assertIn("counts", job.run_safely(Path("x.xlsx"), self.out, sea_path, road_path, NOW))
            good = json.loads(self.out.read_text(encoding="utf-8"))
            later = NOW + dt.timedelta(hours=1)
            self.assertEqual(job.run_safely(Path("x.xlsx"), self.out, self.dir / "none.json", road_path, later)["error"], "SEA_MISSING")
            kept = json.loads(self.out.read_text(encoding="utf-8"))
            self.assertEqual((kept["checked_at"], kept["rows"], kept["last_error"]), (good["checked_at"], good["rows"], {"at": later.isoformat(), "reason": "SEA_MISSING"}))
            job.run_safely(Path("x.xlsx"), self.out, sea_path, road_path, NOW + dt.timedelta(minutes=30))
        self.assertNotIn("last_error", json.loads(self.out.read_text(encoding="utf-8")))
        if os.name == "posix":
            self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)

    def test_cli_prints_counts_only_and_refuses_output_in_the_repository(self):
        rows = [sheet(FAKE, 1, "NONU4444444", "2026-03-15")]
        sea_path, road_path = self.snapshot("snapshot.json", [sea("MISU9999999", "2026-04-20", owner=FAKE)]), self.snapshot("road.json", ROAD)
        printed = io.StringIO()
        with mock.patch.object(job.match, "load_sheet", return_value=rows), mock.patch.object(job, "now_vn", return_value=NOW), redirect_stdout(printed):
            self.assertEqual(job.main(["--xlsx", "x.xlsx", "--snapshot", str(sea_path), "--road", str(road_path), "--output", str(self.out)]), 0)
            self.assertEqual(job.main(["--xlsx", "x.xlsx", "--output", str(job.match.REPO / "tmp-booking.json")]), 2)
        self.assertNotIn(FAKE, printed.getvalue())
        self.assertNotIn("40000000", printed.getvalue())
        self.assertIn(FAKE, self.out.read_text(encoding="utf-8"))
        self.assertFalse((job.match.REPO / "tmp-booking.json").exists())

    def test_alongside_runs_in_a_child_and_reports_its_error_code(self):
        with mock.patch("sys.stderr"), job.alongside(Path("x.xlsx"), self.out, self.dir / "none.json", self.dir / "none2.json") as run:
            pass
        self.assertEqual(run["result"], {"error": "SEA_MISSING"})
        self.assertEqual(json.loads(self.out.read_text(encoding="utf-8"))["last_error"]["reason"], "SEA_MISSING")
        with job.alongside(Path("x.xlsx"), self.out, self.dir / "a", self.dir / "b", enabled=False) as off:
            pass
        self.assertEqual(off["result"], {"skipped": "OFF"})

    def alongside(self, **extra):
        return job.alongside(Path("x.xlsx"), self.out, self.dir / "a", self.dir / "b", **extra)

    def test_alongside_kills_the_child_when_the_run_fails_and_marks_the_result_old(self):
        child = mock.Mock()
        with mock.patch.object(job.subprocess, "Popen", return_value=child), mock.patch("sys.stderr"), \
                self.assertRaises(RuntimeError), self.alongside():
            raise RuntimeError("lượt đối soát lỗi")
        child.kill.assert_called_once()
        self.assertEqual(json.loads(self.out.read_text(encoding="utf-8"))["last_error"]["reason"], "RUN_FAILED")

    def test_nothing_in_the_child_handling_can_fail_the_run(self):
        """Lượt đối soát có thể đã ghi tiền: lỗi ở đây chỉ thành mã."""
        self.out.write_text("[]", encoding="utf-8")   # JSON hợp lệ mà không phải dict
        weird = mock.Mock(returncode=0)
        weird.communicate.return_value = ("[1]\n", None)
        with mock.patch.object(job.subprocess, "Popen", return_value=weird), mock.patch("sys.stderr"), self.alongside() as run:
            pass
        self.assertEqual(run["result"], {"error": "EXIT_0"})
        self.assertEqual(json.loads(self.out.read_text(encoding="utf-8"))["last_error"]["reason"], "EXIT_0")
        broken = mock.Mock()
        broken.communicate.side_effect = RuntimeError("x")
        with mock.patch.object(job.subprocess, "Popen", return_value=broken), mock.patch("sys.stderr"), self.alongside() as run:
            pass
        self.assertEqual(run["result"], {"error": "RuntimeError"})
        with mock.patch.object(job.subprocess, "Popen", side_effect=OSError("no python")), mock.patch("sys.stderr"), self.alongside() as run:
            pass
        self.assertEqual(run["result"], {"error": "START_OSError"})

    def test_deadline_counts_from_the_child_start_and_timeout_is_clean(self):
        child = mock.Mock()
        child.communicate.return_value = ('{"ok": true, "counts": {}}\n', None)
        clock = iter([100.0, 700.0])
        with mock.patch.object(job.subprocess, "Popen", return_value=child), mock.patch.object(job.time, "monotonic", lambda: next(clock)), \
                self.alongside(timeout=900) as run:
            pass
        self.assertEqual(child.communicate.call_args.kwargs["timeout"], 300.0)
        self.assertEqual(run["result"], {"counts": {}})
        slow = mock.Mock(returncode=-9)
        slow.communicate.side_effect = [job.subprocess.TimeoutExpired("x", 1), ("", None)]
        with mock.patch("sys.stderr"):
            self.assertEqual(job.finish(slow, self.out, 1), {"error": "TIMEOUT"})
        slow.kill.assert_called_once()
        self.assertEqual(json.loads(self.out.read_text(encoding="utf-8"))["last_error"]["reason"], "TIMEOUT")
        crashed = mock.Mock(returncode=1)
        crashed.communicate.return_value = ("Traceback\n", None)
        with mock.patch("sys.stderr"):
            self.assertEqual(job.finish(crashed, self.out, 1), {"error": "EXIT_1"})

    def test_no_sheet_rows_in_the_window_is_an_error_not_all_clear(self):
        with self.assertRaises(job.CheckError) as caught:
            self.check([sheet("A", 1, "OLDU5555555", "2025-06-10")])
        self.assertEqual(caught.exception.code, "SHEET_EMPTY")

if __name__ == "__main__":
    unittest.main()


# Báo cáo tháng (BAO-CAO-THANG-01): mọi chuyến theo tháng ngày chuyến. Tên tab giả.
REPORT_SHEET = [
    sheet("KHACH M", 1, "AAAU1000001", "2026-10-03", amount=90_000_000),
    sheet("KHACH M CHEP", 1, "AAAU1000001", "2026-10-03", amount=0),                      # chép 0đ chuyến của KHACH M
    sheet("KHACH M", 2, "BBBU1000002", None, amount=7_000_000, month="2026-10"),       # không ngày, không booking
    sheet("KHACH T", 1, "CCCU1000003", "2026-10-07", amount=0, month="2026-10"),        # khối cũ 0đ, lệch 19 ngày với chuyến đã tính
    sheet("KHACH T", 2, "CCCU1000003", "2026-10-26", amount=59_000_000, month="2026-11"),
    sheet("X", 1, "DDDU1000004", "2026-09-30", month="2026-09"),                      # booking ngày 01/10: tháng theo booking
    sheet("X", 2, "EEEU1000005", "2026-10-05"),                                       # booking không có
    sheet("X", 3, "FFFU1000006", "2026-10-10"),                                       # booking lệch 15 ngày
    sheet("NHAP", 1, "GGGU1000007", "2026-10-11", mode="NHAP"),                      # hàng nhập: không có booking để so
    sheet("X BO", 1, "HHHU1000008", "2026-10-12", mode="BO"),
]
REPORT_SEA = [sea("AAAU1000001", "2026-10-03", owner="KHACH M CHEP"), sea("CCCU1000003", "2026-10-26", owner="KHACH T"),
              sea("DDDU1000004", "2026-10-01", owner="KHACH X"), sea("FFFU1000006", "2026-10-25", owner="KHACH X"),
              sea("MISU1000009", "2026-10-29", owner="KHACH X"), sea("OLDU1000010", "2025-12-05", owner="KHACH X"),
              sea("PREU1000011", "2025-11-10", owner="KHACH X")]
REPORT_ROAD = [road("HHHU1000008", "2026-10-12", owner="KHO X")]


class MonthReportTests(unittest.TestCase):
    setUp, snapshot = BookingCheckTests.setUp, BookingCheckTests.snapshot

    def evaluate(self):
        with mock.patch.object(job.match, "load_sheet", return_value=[dict(row) for row in REPORT_SHEET]):
            return job.evaluate(Path("so-goc.xlsx"), self.snapshot("snapshot.json", REPORT_SEA),
                                self.snapshot("road.json", REPORT_ROAD), NOW)

    maxDiff = None

    def test_every_trip_lands_in_its_trip_month_with_a_status(self):
        result, report = self.evaluate()
        self.assertEqual((report["start"], report["end"], report["checked_at"]), ("2025-12", "2026-11", result["checked_at"]))
        october = report["months"]["2026-10"]
        got = sorted((row["tab"], row["cont"], row["status"], row["family"]) for row in october)
        self.assertEqual(got, sorted([
            ("KHACH M", "AAAU1000001", "khop", "BIEN"), ("KHACH M CHEP", "AAAU1000001", "chep", "BIEN"),
            ("KHACH M", "BBBU1000002", "khong_ngay", "BIEN"),
            ("KHACH T", "CCCU1000003", "chep", "BIEN"), ("KHACH T", "CCCU1000003", "khop", "BIEN"),
            ("X", "DDDU1000004", "khop", "BIEN"), ("X", "EEEU1000005", "khong_booking", "BIEN"),
            ("X", "FFFU1000006", "lech_ngay", "BIEN"), ("NHAP", "GGGU1000007", "ngoai", None),
            ("X BO", "HHHU1000008", "khop", "BO"), ("X", "MISU1000009", "thieu", "BIEN"),
        ]))
        tank = next(row for row in october if row["cont"] == "CCCU1000003" and row["status"] == "khop")
        self.assertEqual((tank["block"], tank["row"], tank["amount_vnd"], tank["booking"]["date"]), ("2026-11", 2, "59000000", "2026-10-26"))
        missing = next(row for row in october if row["status"] == "thieu")
        self.assertEqual((missing["row"], missing["amount_vnd"], missing["booking"]["owner"]), (None, None, "KHACH X"))
        self.assertIsNone(next(row for row in october if row["cont"] == "BBBU1000002")["date"])
        # Trước tháng đầu của tab khách: trong số dư đầu kỳ, chỉ đếm; trước tháng hai bản chụp cùng phủ thì không có.
        self.assertEqual(report["before_book"], {"2025-12": 1})
        self.assertNotIn("2025-11", report["months"])
        self.assertNotIn("2026-09", report["months"])

    def test_report_is_written_with_the_check_and_kept_when_a_run_fails(self):
        sea_path, road_path = self.snapshot("snapshot.json", REPORT_SEA), self.snapshot("road.json", REPORT_ROAD)
        target = job.report_path(self.out)
        with mock.patch.object(job.match, "load_sheet", return_value=[dict(row) for row in REPORT_SHEET]), mock.patch("sys.stderr"):
            job.run_safely(Path("x.xlsx"), self.out, sea_path, road_path, NOW)
            good = target.read_text(encoding="utf-8")
            job.run_safely(Path("x.xlsx"), self.out, self.dir / "none.json", road_path, NOW + dt.timedelta(hours=1))
        self.assertEqual(target.read_text(encoding="utf-8"), good)
        self.assertEqual(target.name, "booking-report.json")
        if os.name == "posix":
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)


def book(book_id, name, trips, mode=None):
    return {"id": book_id, "name": name, "transport_mode": mode, "trips": trips}


def target(cont, day, month=None, kind="trip", price=None, total=None, ident=1):
    return {"kind": kind, "id": ident, "container": cont, "date": dt.date.fromisoformat(day) if day else None,
            "month": month or day[:7], "price": price, "total": total}


# Sổ web giả (DU-CHUYEN-01): cùng chuyến với SHEET ở trên, mã sổ thay tên tab.
BOOKS = [
    book(1, "A", [target("DUPU1111111", "2026-03-10", price=40_000_000), target("GANU2222222", "2026-04-01", kind="legacy", total=40_000_000, ident=2),
                  target("NONU4444444", "2026-03-15", price=40_000_000, ident=3), target("OTHU8888888", "2026-04-10", ident=4)]),
    book(2, "B", [target("DUPU1111111", "2026-03-10", kind="legacy", total=40_000_000), target("BBBU1212121", "2026-03-20", ident=2),
                  target("BEFU0000000", "2026-03-01", ident=3)]),
    book(3, "A BO", [target("ROAU6666666", "2026-05-05"), target("ROBU7777777", None, month="2026-05", ident=2)], mode="BO"),
]


class WebCheckTests(unittest.TestCase):
    """DU-CHUYEN-01: sổ web so với booking, cùng luật ghép và nhóm như phép kiểm Sheet."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.out = self.dir / "booking-web.json"

    def snapshot(self, name, rows):
        path = self.dir / name
        path.write_text(json.dumps({"rows": rows, "runner": {"created_at": (NOW - dt.timedelta(minutes=10)).isoformat()}}), encoding="utf-8")
        return path

    def evaluate(self, books=BOOKS):
        return job.evaluate_web(books, self.snapshot("snapshot.json", SEA), self.snapshot("road.json", ROAD), NOW)

    def test_web_trips_become_book_rows(self):
        rows = job.web_rows([*BOOKS, book(4, "DUONG BO X", [target("XYZU1000001", "2026-05-01")]),
                             book(5, "C", [{"kind": "trip", "id": 9, "container": "", "date": None, "month": "2026-05"}])])
        self.assertEqual(rows[0], {"tab": "A", "row": "trip:1", "customer_id": 1, "month": "2026-03", "date": "2026-03-10", "raw_date": "",
                                   "cont": "DUPU1111111", "mode": "CANG", "amount": 40_000_000})
        self.assertEqual(rows[1]["amount"], 40_000_000, "dòng sổ gốc lấy tổng đã tính")
        self.assertEqual(rows[3]["amount"], 0, "chuyến chưa giá: 0, chỉ để xếp ưu tiên khi ghép")
        self.assertEqual({row["tab"]: row["mode"] for row in rows}, {"A": "CANG", "B": "CANG", "A BO": "BO", "DUONG BO X": "BO"})
        self.assertNotIn("C", {row["tab"] for row in rows}, "chuyến không container không so được")
        self.assertIsNone(next(row for row in rows if row["cont"] == "ROBU7777777")["date"])

    def test_groups_and_how_many_booking_trips_the_web_has(self):
        result = self.evaluate()
        self.assertEqual(result["compare"], "web")
        self.assertEqual(result["counts"]["dup"], 2, "hai sổ cùng tính một chuyến")
        self.assertEqual(result["counts"]["nosource"], 2, "NONU trên sổ A, BEFU trên sổ B: booking không có")
        missing = {row["container"] for row in result["rows"] if row["group"] == "missing"}
        self.assertEqual(missing, {"MISU9999999", "QQQU1313131", "ROCU7777777"})
        self.assertEqual(result["counts"]["recent"], 1)
        self.assertEqual(result["counts"]["nodate"], 1, "dòng web không ngày ghép chuyến booking cùng tháng")
        self.assertEqual(result["booking"], {"trips": 10, "on_web": 6})
        self.assertEqual(result["web"], {"rows": 9, "paired": 6}, "hai dòng DUPU chỉ một dòng giữ được chuyến booking")
        on_book = [row for row in result["rows"] if row["tab"]]
        self.assertTrue(on_book and all(row["customer_id"] in (1, 2, 3) for row in on_book), "dòng sổ web mang mã sổ để mở đúng sổ")
        self.assertTrue(all("customer_id" not in row for row in result["rows"] if not row["tab"]))

    def test_empty_web_is_an_error_not_all_clear(self):
        with self.assertRaises(job.CheckError) as caught:
            self.evaluate([book(1, "A", [target("OLDU5555555", "2025-06-10")])])
        self.assertEqual(caught.exception.code, "WEB_EMPTY")

    def test_run_never_raises_and_keeps_the_last_good_result(self):
        sea_path, road_path = self.snapshot("snapshot.json", SEA), self.snapshot("road.json", ROAD)
        with mock.patch("sys.stderr"):
            line = job.run_web_safely(BOOKS, self.out, sea_path, road_path, NOW)
            self.assertEqual(line["booking"], {"trips": 10, "on_web": 6})
            good = json.loads(self.out.read_text(encoding="utf-8"))
            self.assertEqual(job.run_web_safely([{"bad": True}], self.out, sea_path, road_path, NOW)["error"], "WEB_EMPTY")
            self.assertEqual(job.run_web_safely(None, self.out, sea_path, road_path, NOW)["error"], "TypeError")
        kept = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual((kept["checked_at"], kept["rows"], kept["last_error"]["reason"]), (good["checked_at"], good["rows"], "TypeError"))
        self.assertNotIn(FAKE, json.dumps(line), "dòng in ra chỉ có số đếm")
        self.assertEqual(job.web_path(Path("/x/booking-check.json")), Path("/x/booking-web.json"))
