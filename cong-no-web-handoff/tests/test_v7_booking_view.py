"""GET /api/v7/machine/booking (KIEM-BOOKING-01): trạng thái không bao giờ là "ổn" khi chưa kiểm, lượt lỗi hay kết quả cũ. Chỉ đọc
sổ web (get_trip_month) khi có dòng "tháng này chưa lên sổ", để tách chuyến máy đã đưa vào sổ web."""

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

    def test_route_reads_the_file_and_no_database_without_recent_rows(self):
        self.write(self.result())
        status, body = self.request("/api/v7/machine/booking")
        self.assertEqual((status, body["counts"]), (200, {"dup": 1}))
        with self.assertRaises(ApiError):
            self.request("/api/v7/machine/booking?x=1")

    def test_route_marks_recent_rows_already_on_the_web(self):
        row = recent("NEWU1515151", "2026-11-12")
        self.write(self.result(rows=[row]))
        runner = mock.Mock()
        runner.run.return_value = {"books": BOOKS, "trips": [trip(7, "NEWU1515151", "2026-11-13")]}
        with mock.patch.object(api, "READS", api.v7_read_cache.ReadCache()):
            status, body = api.handle("GET", "/api/v7/machine/booking", {"Host": "127.0.0.1:8780"}, b"", runner,
                                      port=8780, host="127.0.0.1", actor="nguoi@test")
        self.assertEqual((status, body["recent_web"]), (200, "checked"))
        self.assertEqual(body["rows"][0]["web"], {"customer_id": 7, "name": "KHACH BAY", "date": "2026-11-13"})

    def test_route_carries_the_web_check_with_its_own_state(self):
        """DU-CHUYEN-01: `web_check` đọc booking-web.json, tính `state` như phần Sheet; chưa có file thì `none`, không phải "ổn"."""
        self.write(self.result())
        status, body = self.request("/api/v7/machine/booking")
        self.assertEqual((status, body["web_check"]["state"]), (200, "none"))
        (self.dir / "booking-web.json").write_text(json.dumps(self.result(compare="web", booking={"trips": 9, "on_web": 8})), encoding="utf-8")
        body = view.both(mock.Mock(), None, "nguoi@test", at("13T10:30:00"))
        self.assertEqual((body["state"], body["web_check"]["state"], body["web_check"]["booking"]), ("ok", "ok", {"trips": 9, "on_web": 8}))
        self.assertNotIn("web_check", body["web_check"])

    def test_page_script_is_served(self):
        self.assertIn("/may-chay-booking.js", api.ASSETS)


class Reads:
    """Bộ đọc giả: trả bản `get_trip_month` theo tháng, ghi các tháng đã hỏi; `fail` thì lỗi như DB không trả lời."""

    def __init__(self, months, fail=False):
        self.months, self.fail, self.asked = months, fail, []

    def run(self, runner, function, payload, actor):
        self.asked.append((function, payload["month"]))
        if self.fail:
            raise ApiError(503, "DB", "x")
        return self.months.get(payload["month"][:7], {"books": [], "trips": []})


def recent(cont, day):
    return {"group": "recent", "code": "THANG_CUOI", "container": cont, "source": {"kind": "BIEN", "date": day}}


def trip(book, cont, day):
    return {"customer_id": book, "container": cont, "date": day, "source": "sheet"}


BOOKS = [{"id": 7, "name": "KHACH BAY"}, {"id": 9, "name": "KHACH CHIN"}]


class WithWebTests(unittest.TestCase):
    def body(self, *rows, state="ok"):
        return {"state": state, "rows": [{"group": "dup", "code": "TRUNG", "container": "AAAU1111111"}, *rows]}

    def test_marks_recent_rows_with_the_nearest_web_trip_in_any_book(self):
        reads = Reads({"2026-11": {"books": BOOKS, "trips": [
            trip(7, "AAAU1111111", "2026-11-19"), trip(9, "BBBU2222222", "2026-11-25"), trip(9, "CCCU3333333", "2026-11-01")]}})
        body = view.with_web(self.body(recent("AAAU1111111", "2026-11-19"), recent("BBBU2222222", "2026-11-21"),
                                       recent("CCCU3333333", "2026-11-14")), mock.Mock(), reads, "may")
        rows = body["rows"]
        self.assertEqual(body["recent_web"], "checked")
        self.assertEqual(rows[1]["web"], {"customer_id": 7, "name": "KHACH BAY", "date": "2026-11-19"})
        self.assertNotIn("web", rows[2], "lệch 4 ngày: không phải chuyến này")
        self.assertNotIn("web", rows[3], "container dùng lại đầu tháng: web chưa có chuyến này")
        self.assertNotIn("web", rows[0], "chỉ nhóm tháng này")
        self.assertEqual(reads.asked, [("get_trip_month", "2026-11-01")])

    def test_one_web_trip_pairs_one_row_and_the_closest_pair_wins(self):
        reads = Reads({"2026-11": {"books": BOOKS, "trips": [trip(7, "AAAU1111111", "2026-11-10")]}})
        body = view.with_web(self.body(recent("AAAU1111111", "2026-11-12"), recent("AAAU1111111", "2026-11-11")), mock.Mock(), reads, "may")
        self.assertEqual([row.get("web", {}).get("date") for row in body["rows"][1:]], [None, "2026-11-10"])

    def test_edge_of_month_trip_returned_by_two_months_counts_once(self):
        both = trip(7, "AAAU1111111", "2026-10-31")
        reads = Reads({"2026-10": {"books": BOOKS, "trips": [both]}, "2026-11": {"books": BOOKS, "trips": [both]}})
        body = view.with_web(self.body(recent("AAAU1111111", "2026-10-30"), recent("AAAU1111111", "2026-11-01")), mock.Mock(), reads, "may")
        self.assertEqual(sum("web" in row for row in body["rows"]), 1)
        self.assertEqual(reads.asked, [("get_trip_month", "2026-10-01"), ("get_trip_month", "2026-11-01")])

    def test_container_written_differently_still_pairs(self):
        reads = Reads({"2026-11": {"books": BOOKS, "trips": [trip(9, "aaau 111111-1", "2026-11-05")]}})
        body = view.with_web(self.body(recent("AAAU1111111", "2026-11-05")), mock.Mock(), reads, "may")
        self.assertEqual(body["rows"][1]["web"]["customer_id"], 9)

    def test_read_failure_keeps_one_group(self):
        body = view.with_web(self.body(recent("AAAU1111111", "2026-11-05")), mock.Mock(), Reads({}, fail=True), "may")
        self.assertEqual(body["recent_web"], "unavailable")
        self.assertNotIn("web", body["rows"][1])

    def test_no_recent_rows_or_no_result_reads_nothing(self):
        reads = Reads({})
        self.assertNotIn("recent_web", view.with_web(self.body(), mock.Mock(), reads, "may"))
        self.assertNotIn("recent_web", view.with_web(self.body(recent("AAAU1111111", "2026-11-05"), state="none"), mock.Mock(), reads, "may"))
        self.assertEqual(reads.asked, [])

    def test_cached_read_is_not_changed(self):
        month = {"books": BOOKS, "trips": [trip(7, "AAAU1111111", "2026-11-05")]}
        before = json.dumps(month, sort_keys=True)
        view.with_web(self.body(recent("AAAU1111111", "2026-11-05")), mock.Mock(), Reads({"2026-11": month}), "may")
        self.assertEqual(json.dumps(month, sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
