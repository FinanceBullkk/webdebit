"""Máy canh (CANH-BAO-01): phát hiện đúng, không nhiễu bởi lỗi lẻ, không lộ dữ liệu khách. Không cần DB, mạng hay systemd thật."""

import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from collections import namedtuple
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_watchdog as dog  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOON = dt.datetime(2026, 11, 4, 12, 0, tzinfo=VN)
Disk = namedtuple("Disk", "total used free")


class Response:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def healthy_units(unit, *properties):
    if unit.endswith(".timer"):
        return {"ActiveState": "active", "LastTriggerUSec": f"@{int(NOON.timestamp()) - 3600}"}
    return {"Result": "success"}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "reconcile.json"

    def write(self, **data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class ApiTests(unittest.TestCase):
    def test_only_200_is_healthy(self):
        self.assertEqual(dog.check_api("x", lambda *a, **k: Response()), [])
        self.assertEqual(dog.check_api("x", lambda *a, **k: Response(204)), ["Web báo lỗi (204)."])

    def test_http_error_and_no_connection_are_reported(self):
        def http_error(*args, **kwargs):
            raise urllib.error.HTTPError("x", 503, "x", None, None)

        def refused(*args, **kwargs):
            raise urllib.error.URLError("refused")
        self.assertEqual(dog.check_api("x", http_error), ["Web báo lỗi (503)."])
        self.assertEqual(dog.check_api("x", refused), ["Web không trả lời (URLError)."])


class ReconcileTests(Base):
    def test_fresh_run_is_quiet_even_with_customers_to_review(self):
        self.write(checked_at="2026-11-04T11:12:00+07:00", customers=[{"customer": "KHACH THAT", "reason": "NO_EXACT_FIX", "status": "LECH_TONG"}])
        self.assertEqual(dog.check_reconcile(self.path, NOON), [])

    def test_one_failed_run_self_heals_so_no_alert_until_three_hours(self):
        self.write(checked_at="2026-11-04T10:12:00+07:00", last_error={"at": "2026-11-04T11:05:00+07:00", "reason": "HTTPError"}, customers=[])
        self.assertEqual(dog.check_reconcile(self.path, NOON), [])
        self.assertEqual(dog.check_reconcile(self.path, NOON + dt.timedelta(hours=2)),
                         ["Máy đối soát chưa chạy được từ 10:12 ngày 04/11 (lỗi gần nhất: HTTPError)."])

    def test_overnight_gap_is_not_a_stop(self):
        self.write(checked_at="2026-11-03T22:12:00+07:00", customers=[])
        self.assertEqual(dog.check_reconcile(self.path, dt.datetime(2026, 11, 4, 7, 30, tzinfo=VN)), [])
        self.assertEqual(dog.check_reconcile(self.path, dt.datetime(2026, 11, 4, 9, 30, tzinfo=VN)), [])   # lượt 7 và 8 giờ lỗi: tới 10 giờ mới báo
        self.assertTrue(dog.check_reconcile(self.path, dt.datetime(2026, 11, 4, 10, 30, tzinfo=VN)))
        self.write(checked_at="2026-11-02T22:12:00+07:00", customers=[])
        self.assertTrue(dog.check_reconcile(self.path, dt.datetime(2026, 11, 4, 2, 0, tzinfo=VN)))         # đêm mà đã hơn 14 giờ

    def test_never_ran_and_unreadable_file_are_reported(self):
        self.write(last_error={"at": "x", "reason": "KeyError"})
        self.assertEqual(dog.check_reconcile(self.path, NOON), ["Máy đối soát chưa có lượt nào chạy được (lỗi gần nhất: KeyError)."])
        self.assertEqual(dog.check_reconcile(self.root / "khong-co.json", NOON), ["Không đọc được kết quả đối soát."])
        self.path.write_text("{hỏng", encoding="utf-8")
        self.assertEqual(dog.check_reconcile(self.path, NOON), ["Không đọc được kết quả đối soát."])

    def test_write_problems_are_counted_without_names_and_a_race_with_a_person_is_ignored(self):
        self.write(checked_at="2026-11-04T11:12:00+07:00", customers=[
            {"customer": "KHACH THAT 1", "reason": "VERIFY_FAILED", "difference_vnd": "123456"},
            {"customer": "KHACH THAT 2", "reason": "WRITE_ERROR", "error": "MONTH_LOCKED"},
            {"customer": "KHACH THAT 3", "reason": "CHECK_ERROR", "error": "KeyError"},
            {"customer": "KHACH THAT 4", "reason": "WRITE_ERROR", "error": "STALE_LEDGER"}])
        found = dog.check_reconcile(self.path, NOON)
        self.assertEqual(found, ["Máy đối soát ghi xong mà không khớp ở 1 khách. Cần xem ngay.", "Máy đối soát lỗi khi xử lý 2 khách."])
        self.assertNotIn("KHACH", " ".join(found))
        self.assertNotIn("123456", " ".join(found))


class SnapshotTests(Base):
    def test_old_and_missing_files_are_named_and_a_late_tick_is_not(self):
        now = NOON.timestamp()
        for name in dog.SNAPSHOTS[:-1]:
            (self.root / name).write_text("{}", encoding="utf-8")
            os.utime(self.root / name, (now - 45 * 60, now - 45 * 60))
        self.assertEqual(dog.check_snapshots(self.root, now), [f"Thiếu bản chụp Sheet {dog.SNAPSHOTS[-1]}."])
        os.utime(self.root / "prices.json", (now - 95 * 60, now - 95 * 60))
        self.assertIn("Bản chụp Sheet prices.json đã cũ 95 phút.", dog.check_snapshots(self.root, now))


class UnitTests(unittest.TestCase):
    def test_all_healthy(self):
        self.assertEqual(dog.check_units(healthy_units, NOON.timestamp()), [])

    def test_stopped_timer_failed_backup_and_backup_that_stopped_running(self):
        def show(unit, *properties):
            if unit == "v7-reconcile-auto.timer":
                return {"ActiveState": "inactive", "LastTriggerUSec": ""}
            if unit == "v7-backup-daily.service":
                return {"Result": "exit-code"}
            if unit == "v7-backup-offsite.timer":
                return {"ActiveState": "active", "LastTriggerUSec": f"@{int(NOON.timestamp()) - 27 * 3600}"}
            return healthy_units(unit, *properties)
        self.assertEqual(dog.check_units(show, NOON.timestamp()),
                         ["Timer v7-reconcile-auto không chạy.", "Sao lưu v7-backup-daily lỗi (exit-code).", "Sao lưu v7-backup-offsite đã hơn 26 giờ chưa chạy."])

    def test_failed_run_of_a_fifteen_minute_job_is_left_to_the_snapshot_age(self):
        def show(unit, *properties):
            return {"Result": "exit-code"} if unit == "webdebit-sheet-sync.service" else healthy_units(unit, *properties)
        self.assertEqual(dog.check_units(show, NOON.timestamp()), [])


class DiskTests(unittest.TestCase):
    def test_low_space_and_missing_path(self):
        def usage(path):
            if path == "/khong-co":
                raise FileNotFoundError(path)
            return Disk(100, 95, 5) if path == "/day" else Disk(100, 50, 50)
        self.assertEqual(dog.check_disks(("/", "/day", "/khong-co"), usage), ["Đĩa /day chỉ còn 5% trống."])


class CollectTests(Base):
    def test_one_broken_check_does_not_hide_the_others(self):
        self.write(checked_at="2026-11-04T01:00:00+07:00", customers=[])
        with patch.object(dog, "check_api", return_value=[]), patch.object(dog, "check_disks", return_value=[]):
            found = dog.collect(NOON, healthz="x", reconcile=self.path, snapshots=self.root,
                                show=lambda *a: (_ for _ in ()).throw(FileNotFoundError("systemctl")))
        self.assertIn("Không kiểm được phần timer (FileNotFoundError).", found)
        self.assertTrue(any(line.startswith("Máy đối soát chưa chạy được") for line in found))
        self.assertTrue(any(line.startswith("Thiếu bản chụp") for line in found))


class SendTests(unittest.TestCase):
    def test_ok_goes_to_the_plain_url_and_problems_to_fail_with_the_list(self):
        calls = []

        def opener(request, timeout):
            calls.append((request.full_url, request.data.decode("utf-8"), request.get_method()))
            return Response()
        self.assertTrue(dog.send("https://ping.test/abc", "Ổn.", failed=False, opener=opener))
        self.assertTrue(dog.send("https://ping.test/abc", "Web báo lỗi (503).", failed=True, opener=opener))
        self.assertEqual(calls, [("https://ping.test/abc", "Ổn.", "POST"), ("https://ping.test/abc/fail", "Web báo lỗi (503).", "POST")])

    def test_retries_then_gives_up(self):
        calls = []

        def opener(request, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise urllib.error.URLError("mạng")
            return Response()
        self.assertTrue(dog.send("https://ping.test/abc", "x", failed=False, opener=opener, pause=0))
        calls.clear()

        def down(request, timeout):
            calls.append(1)
            raise TimeoutError
        self.assertFalse(dog.send("https://ping.test/abc", "x", failed=False, opener=down, pause=0))
        self.assertEqual(len(calls), 3)


class MainTests(Base):
    def run_main(self, *args, url=None, sent=True):
        printed = io.StringIO()
        env = {key: value for key, value in os.environ.items() if key != "WEBDEBIT_ALERT_PING_URL"}
        if url:
            env["WEBDEBIT_ALERT_PING_URL"] = url
        with patch.dict(os.environ, env, clear=True), patch.object(dog, "collect", return_value=["Web báo lỗi (503)."]), \
                patch.object(dog, "send", return_value=sent) as send, redirect_stdout(printed):
            code = dog.main(list(args))
        return code, send, printed.getvalue()

    def test_without_url_it_only_reports_to_the_journal(self):
        code, send, printed = self.run_main()
        self.assertEqual(code, 0)
        send.assert_not_called()
        self.assertEqual(json.loads(printed), {"ok": False, "problems": ["Web báo lỗi (503)."], "configured": False})

    def test_with_url_problems_go_out_and_url_is_never_printed(self):
        link = "https://ping.test/rieng-tu"
        code, send, printed = self.run_main(url=link)
        self.assertEqual(code, 0)
        send.assert_called_once_with(link, "Web báo lỗi (503).", failed=True)
        self.assertNotIn("rieng-tu", printed)

    def test_dry_run_and_non_https_url_send_nothing(self):
        self.assertEqual(self.run_main("--dry-run", url="https://ping.test/x")[1].call_count, 0)
        code, send, _ = self.run_main(url="http://ping.test/x")
        self.assertEqual((code, send.call_count), (2, 0))

    def test_test_fail_sends_the_test_text_without_checking(self):
        code, send, _ = self.run_main("--test-fail", url="https://ping.test/x")
        self.assertEqual(code, 0)
        send.assert_called_once_with("https://ping.test/x", dog.TEST_BODY, failed=True)

    def test_failed_send_exits_non_zero(self):
        self.assertEqual(self.run_main(url="https://ping.test/x", sent=False)[0], 3)


if __name__ == "__main__":
    unittest.main()
