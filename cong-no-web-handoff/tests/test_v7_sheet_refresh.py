"""Nút Làm mới đọc Sheet ngay (specs/v7-sheet-refresh.md): trạng thái theo giờ file, API chỉ ghi file tín hiệu."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402
import v7_sheet_refresh as refresh  # noqa: E402


class SheetRefreshTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        base = Path(self.directory.name)
        self.signal = str(base / "refresh.request")
        self.trips, self.prices = str(base / "snapshot.json"), str(base / "prices.json")
        self.paths = (self.trips, self.prices)
        self.now = time.time()

    def tearDown(self):
        self.directory.cleanup()

    def touch(self, path, age):
        Path(path).write_text("{}", encoding="utf-8")
        os.utime(path, (self.now - age, self.now - age))

    def test_unavailable_without_signal_path(self):
        self.touch(self.trips, 600)
        self.touch(self.prices, 600)
        self.assertEqual(refresh.status(None, self.paths, self.now)["state"], "unavailable")
        self.assertEqual(refresh.request(None, self.paths, "a@b", self.now)["state"], "unavailable")

    def test_request_writes_signal_once_then_reports_running(self):
        self.touch(self.trips, 600)
        self.touch(self.prices, 590)
        before = refresh.status(self.signal, self.paths, self.now)
        self.assertEqual(before["state"], "idle")
        self.assertFalse(before["recent"])
        result = refresh.request(self.signal, self.paths, "nguoi@nhap", time.time())
        self.assertEqual(result["state"], "running")
        self.assertEqual(json.loads(Path(self.signal).read_text(encoding="utf-8"))["actor"], "nguoi@nhap")
        written = Path(self.signal).stat().st_mtime
        again = refresh.request(self.signal, self.paths, "khac@nhap", time.time() + 5)
        self.assertEqual(again["state"], "running")
        self.assertEqual(Path(self.signal).stat().st_mtime, written)   # bấm lặp không ghi thêm

    def test_idle_when_both_snapshots_newer_than_signal(self):
        self.touch(self.signal, 120)
        self.touch(self.trips, 100)
        self.touch(self.prices, 130)   # chuyến xong, giá chưa xong thì vẫn chạy
        self.assertEqual(refresh.status(self.signal, self.paths, self.now)["state"], "running")
        self.touch(self.prices, 90)
        result = refresh.status(self.signal, self.paths, self.now)
        self.assertEqual(result["state"], "idle")
        self.assertEqual(result["sheet_at"], refresh._iso(self.now - 100))   # bản cũ hơn trong hai file

    def test_recent_snapshot_is_not_read_again(self):
        self.touch(self.trips, 20)
        self.touch(self.prices, 10)
        result = refresh.request(self.signal, self.paths, "a@b", self.now)
        self.assertEqual(result["state"], "idle")
        self.assertTrue(result["recent"])
        self.assertFalse(Path(self.signal).exists())

    def test_failed_after_three_minutes_and_can_retry(self):
        self.touch(self.trips, 900)
        self.touch(self.prices, 900)
        self.touch(self.signal, refresh.RUNNING_LIMIT_SECONDS + 10)
        self.assertEqual(refresh.status(self.signal, self.paths, self.now)["state"], "failed")
        self.assertEqual(refresh.request(self.signal, self.paths, "a@b", time.time())["state"], "running")

    def test_missing_snapshot_counts_as_not_done(self):
        self.touch(self.trips, 100)
        self.touch(self.signal, 30)
        result = refresh.status(self.signal, self.paths, self.now)
        self.assertEqual(result["state"], "running")
        self.assertIsNone(result["sheet_at"])


class SheetRefreshApiTest(unittest.TestCase):
    def setUp(self):
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}

    def call(self, method, path, body=b""):
        return api.handle(method, path, self.headers, body, None, port=8780, host="127.0.0.1", actor="nguoi@nhap")

    def test_routes_use_configured_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ("snapshot.json", "prices.json"):
                (base / name).write_text("{}", encoding="utf-8")
                os.utime(base / name, (time.time() - 600, time.time() - 600))
            with patch.object(api, "SHEET_REFRESH_PATH", str(base / "refresh.request")), \
                    patch.object(api, "SHEET_SNAPSHOT_PATH", str(base / "snapshot.json")), \
                    patch.object(api, "PRICE_SNAPSHOT_PATH", str(base / "prices.json")):
                self.assertEqual(self.call("GET", "/api/v7/sheet/refresh")[1]["state"], "idle")
                status, result = self.call("POST", "/api/v7/sheet/refresh", b"{}")
                self.assertEqual((status, result["state"]), (200, "running"))
                self.assertTrue((base / "refresh.request").exists())

    def test_unconfigured_and_bad_requests(self):
        with patch.object(api, "SHEET_REFRESH_PATH", None):
            self.assertEqual(self.call("GET", "/api/v7/sheet/refresh")[1]["state"], "unavailable")
            self.assertEqual(self.call("POST", "/api/v7/sheet/refresh", b"{}")[1]["state"], "unavailable")
            for body in (b'{"x":1}', b"[]", b"no"):
                with self.assertRaises(api.ApiError) as caught:
                    self.call("POST", "/api/v7/sheet/refresh", body)
                self.assertEqual(caught.exception.status, 422)
            with self.assertRaises(api.ApiError):
                self.call("GET", "/api/v7/sheet/refresh?x=1")

    def test_unwritable_signal_is_503(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(api, "SHEET_REFRESH_PATH", str(Path(directory) / "missing" / "refresh.request")), \
                patch.object(api, "SHEET_SNAPSHOT_PATH", str(Path(directory) / "snapshot.json")), \
                patch.object(api, "PRICE_SNAPSHOT_PATH", str(Path(directory) / "prices.json")):
            with self.assertRaises(api.ApiError) as caught:
                self.call("POST", "/api/v7/sheet/refresh", b"{}")
            self.assertEqual(caught.exception.code, "SHEET_REFRESH_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
