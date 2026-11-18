"""GET /api/v7/machine/booking (KIEM-BOOKING-01): trạng thái không bao giờ là "ổn" khi chưa kiểm, lượt lỗi hay kết quả cũ; không vào DB."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_booking_view as view
import v7_ledger_api as api
from v7_api_validate import ApiError


def at(text):
    return datetime.fromisoformat(f"2026-11-{text}+07:00")


class BookingViewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        patcher = mock.patch.dict(os.environ, {"WEBDEBIT_MACHINE_DIR": str(self.dir)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, body):
        (self.dir / "booking-check.json").write_text(body if isinstance(body, str) else json.dumps(body), encoding="utf-8")

    def result(self, checked="13T10:14:00", **extra):
        return {"version": 1, "checked_at": at(checked).isoformat(), "counts": {"dup": 1}, "rows": [{"group": "dup"}], **extra}

    def test_last_slot_follows_the_reconcile_timer(self):
        for now, slot in (("13T10:30:00", "13T10:05:00"), ("13T10:04:00", "13T09:05:00"), ("13T23:40:00", "13T22:05:00"),
                          ("13T06:00:00", "12T22:05:00"), ("13T07:04:59", "12T22:05:00"), ("13T07:05:00", "13T07:05:00")):
            self.assertEqual(view.last_slot(at(now)), at(slot), now)

    def test_states(self):
        self.assertEqual(view.view(at("13T10:30:00"))["state"], "none")
        self.write("{hỏng")
        self.assertEqual(view.view(at("13T10:30:00"))["state"], "none")
        self.write({"version": 1, "last_error": {"at": at("13T10:20:00").isoformat(), "reason": "SEA_MISSING"}})
        self.assertEqual(view.view(at("13T10:30:00"))["state"], "none", "chỉ có lỗi: chưa có kết quả")
        self.write(self.result())
        self.assertEqual(view.view(at("13T10:30:00"))["state"], "ok")
        self.assertEqual(view.view(at("13T11:20:00"))["state"], "ok", "lượt 11:05 có thể còn đang chạy")
        self.assertEqual(view.view(at("13T12:06:00"))["state"], "stale", "lượt 11:05 không ghi được: đã cũ")
        self.write(self.result("12T22:14:00"))
        self.assertEqual(view.view(at("13T07:30:00"))["state"], "ok", "đêm không có lượt")
        self.assertEqual(view.view(at("13T08:10:00"))["state"], "stale", "lượt 7:05 không ghi được")
        self.write(self.result(last_error={"at": at("13T11:13:00").isoformat(), "reason": "SEA_STALE"}))
        body = view.view(at("13T11:30:00"))
        self.assertEqual((body["state"], body["rows"]), ("error", [{"group": "dup"}]), "lỗi mới hơn: vẫn trả số cũ để trang ghi là cũ")
        self.write(self.result(last_error={"at": at("13T09:13:00").isoformat(), "reason": "SEA_STALE"}))
        self.assertEqual(view.view(at("13T10:30:00"))["state"], "ok", "lỗi cũ hơn lượt đạt thì thôi")

    def request(self, target):
        runner = mock.Mock()
        result = api.handle("GET", target, {"Host": "127.0.0.1:8780"}, b"", runner, port=8780, host="127.0.0.1", actor="nguoi@test")
        runner.run.assert_not_called()
        return result

    def test_route_reads_the_file_and_never_the_database(self):
        self.write(self.result())
        status, body = self.request("/api/v7/machine/booking")
        self.assertEqual((status, body["counts"]), (200, {"dup": 1}))
        with self.assertRaises(ApiError):
            self.request("/api/v7/machine/booking?x=1")

    def test_page_script_is_served(self):
        self.assertIn("/may-chay-booking.js", api.ASSETS)


if __name__ == "__main__":
    unittest.main()
