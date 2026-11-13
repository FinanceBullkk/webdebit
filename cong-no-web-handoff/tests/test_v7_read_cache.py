"""HIEU-NANG-01: bộ nhớ đọc theo dấu dữ liệu (web/v7_read_cache.py) và chỗ nối ở GET của API."""
import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_ledger_api as api
import v7_read_cache
from v7_api_validate import ApiError

STAMP_A, STAMP_B = "a" * 32, "b" * 32


class Runner:
    """Runner giả: đếm lần gọi; dấu đổi được giữa các lượt."""

    def __init__(self, stamp=STAMP_A, day="2026-11-13"):
        self.stamp, self.day, self.calls, self.version = stamp, day, [], 1

    def run(self, function, payload, actor):
        self.calls.append(function)
        if function == "get_read_stamp":
            if isinstance(self.stamp, Exception):
                raise self.stamp
            return {"as_of": self.day, "stamp": self.stamp} if isinstance(self.stamp, str) else self.stamp
        if function == "get_ledger":
            if payload["customer_id"] == 404:
                raise ApiError(404, "CUSTOMER_NOT_FOUND", "x")
            return {"customer_id": payload["customer_id"], "version": self.version, "events": [{"id": 1}]}
        return {"function": function}

    def reads(self, function):
        return self.calls.count(function)


class ReadCacheTests(unittest.TestCase):
    def setUp(self):
        self.cache = v7_read_cache.ReadCache()

    def read(self, runner, customer=7):
        return self.cache.run(runner, "get_ledger", {"customer_id": customer}, "fake")

    def test_same_stamp_reads_the_database_once(self):
        runner = Runner()
        first, second = self.read(runner), self.read(runner)
        self.assertEqual(first, second)
        # Lượt trượt lấy dấu hai lần (trước và sau khi đọc), lượt trúng một lần.
        self.assertEqual((runner.reads("get_ledger"), runner.reads("get_read_stamp")), (1, 3))
        self.assertEqual((self.cache.hits, self.cache.misses), (1, 1))

    def test_new_stamp_reads_again_and_drops_old_entries(self):
        runner = Runner()
        self.read(runner, 7)
        self.read(runner, 8)
        runner.stamp, runner.version = STAMP_B, 2
        self.assertEqual(self.read(runner, 7)["version"], 2)
        self.assertEqual(runner.reads("get_ledger"), 3)
        self.assertEqual([key[0] for key in self.cache.entries], [f"2026-11-13:{STAMP_B}"])

    def test_write_during_the_read_is_not_kept_under_the_old_stamp(self):
        class Racing(Runner):
            def run(self, function, payload, actor):
                result = super().run(function, payload, actor)
                if function == "get_ledger":
                    self.stamp = STAMP_B   # lệnh ghi commit trong lúc đọc
                return result
        runner = Racing()
        self.assertEqual(self.read(runner)["version"], 1)
        self.assertEqual(len(self.cache.entries), 0)
        runner.run = Runner.run.__get__(runner)   # hết ghi: lượt sau giữ dưới dấu mới
        self.read(runner)
        self.read(runner)
        self.assertEqual(runner.reads("get_ledger"), 2)

    def test_broken_stamp_is_logged_once_per_change(self):
        runner = Runner(ApiError(503, "DB_UNAVAILABLE", "x"))
        with patch("sys.stderr") as err:
            for _ in range(3):
                self.cache.run(runner, "get_dashboard", {}, "fake")
            runner.stamp = STAMP_A
            self.cache.run(runner, "get_dashboard", {}, "fake")
        lines = "".join(call.args[0] for call in err.write.call_args_list).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("DB_UNAVAILABLE", lines[0])

    def test_new_vn_day_reads_again(self):
        runner = Runner()
        self.read(runner)
        runner.day = "2026-11-14"
        self.read(runner)
        self.assertEqual(runner.reads("get_ledger"), 2)

    def test_other_functions_go_straight_without_stamp(self):
        runner = Runner()
        for _ in range(2):
            self.cache.run(runner, "list_customers", {}, "fake")
        self.assertEqual(runner.calls, ["list_customers", "list_customers"])

    def test_broken_or_missing_stamp_reads_straight(self):
        for stamp in (ApiError(503, "DB_UNAVAILABLE", "x"), KeyError("get_read_stamp"), {"as_of": "2026-11-13"},
                      {"as_of": "13/11/2026", "stamp": STAMP_A}, {"as_of": "2026-11-13", "stamp": "x' OR 1"}, ["a"]):
            with self.subTest(stamp=stamp):
                cache, runner = v7_read_cache.ReadCache(), Runner(stamp)
                cache.run(runner, "get_dashboard", {}, "fake")
                cache.run(runner, "get_dashboard", {}, "fake")
                self.assertEqual(runner.reads("get_dashboard"), 2)
                self.assertEqual(len(cache.entries), 0)

    def test_errors_are_not_kept(self):
        runner = Runner()
        for _ in range(2):
            with self.assertRaises(ApiError):
                self.read(runner, 404)
        self.assertEqual(runner.reads("get_ledger"), 2)
        self.assertEqual(len(self.cache.entries), 0)

    def test_broken_json_text_is_db_unavailable_and_not_kept(self):
        class TextRunner(Runner):
            def run_text(self, function, payload, actor):
                self.calls.append(function)
                return "{broken"
        runner = TextRunner()
        with self.assertRaises(ApiError) as caught:
            self.read(runner)
        self.assertEqual(caught.exception.code, "DB_UNAVAILABLE")
        self.assertEqual(len(self.cache.entries), 0)

    def test_run_text_is_kept_as_is(self):
        class TextRunner(Runner):
            def run_text(self, function, payload, actor):
                self.calls.append(function)
                return '{"customer_id": 7, "total": "12345678901234567890"}'
        runner = TextRunner()
        self.assertEqual(self.read(runner)["total"], "12345678901234567890")
        self.assertEqual(self.read(runner)["total"], "12345678901234567890")
        self.assertEqual(runner.reads("get_ledger"), 1)

    def test_returned_dict_can_be_changed_without_touching_the_kept_copy(self):
        runner = Runner()
        first = self.read(runner)
        first.pop("events")
        first["customer_id"] = 0
        self.assertEqual(self.read(runner), {"customer_id": 7, "version": 1, "events": [{"id": 1}]})

    def test_same_key_at_once_runs_the_read_once(self):
        results, errors, runner = self.three_at_once(fail=False)
        self.assertEqual((runner.reads("get_ledger"), results, errors), (1, [{"customer_id": 7}] * 3, []))

    def test_same_key_at_once_shares_the_error(self):
        results, errors, runner = self.three_at_once(fail=True)
        self.assertEqual((runner.reads("get_ledger"), results, errors), (1, [], ["DB_UNAVAILABLE"] * 3))

    def three_at_once(self, fail):
        cache, started, release, results, errors = v7_read_cache.ReadCache(), threading.Event(), threading.Event(), [], []

        class Slow(Runner):
            def run(self, function, payload, actor):
                if function != "get_ledger":
                    return super().run(function, payload, actor)
                self.calls.append(function)
                started.set()
                release.wait(5)
                if fail:
                    raise ApiError(503, "DB_UNAVAILABLE", "x")
                return {"customer_id": 7}
        runner = Slow()

        def read():
            try:
                results.append(cache.run(runner, "get_ledger", {"customer_id": 7}, "fake"))
            except ApiError as exc:
                errors.append(exc.code)
        threads = [threading.Thread(target=read) for _ in range(3)]
        threads[0].start()
        self.assertTrue(started.wait(5))
        for thread in threads[1:]:
            thread.start()
        while runner.reads("get_read_stamp") < 3:
            threading.Event().wait(0.01)
        threading.Event().wait(0.1)   # hai lượt sau đã lấy dấu, tới chỗ chờ lượt đầu
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(cache.flights, {})
        return results, errors, runner

    def test_byte_limit_drops_oldest(self):
        cache, runner = v7_read_cache.ReadCache(max_bytes=120), Runner()
        size = len(json.dumps(runner.run("get_ledger", {"customer_id": 1}, "x"), separators=(",", ":")))
        for customer in (1, 2, 3):
            cache.run(runner, "get_ledger", {"customer_id": customer}, "fake")
        self.assertLessEqual(cache.size, 120)
        self.assertEqual(len(cache.entries), 120 // size)
        self.assertNotIn(1, [json.loads(key[2])["customer_id"] for key in cache.entries])


class ApiWiringTests(unittest.TestCase):
    """GET Tổng quan và sổ qua bộ nhớ; POST đi thẳng; kết quả GET giống khi không có bộ nhớ."""

    def setUp(self):
        self.reads = patch.object(api, "READS", v7_read_cache.ReadCache())
        self.reads.start()
        self.addCleanup(self.reads.stop)

    def get(self, runner, target):
        return api.handle("GET", target, {"Host": "127.0.0.1:8780"}, b"", runner, port=8780, host="127.0.0.1", actor="fake")

    def test_dashboard_get_goes_through_the_cache(self):
        runner = Runner()
        for path in ("/api/v7/dashboard", "/api/v7/dashboard/debt"):
            for _ in range(3):
                self.get(runner, path)
        self.assertEqual((runner.reads("get_dashboard"), runner.reads("get_dashboard_debt")), (1, 1))

    def test_ledger_get_matches_uncached_and_projections_still_run(self):
        runner = Runner()
        with patch.object(api, "ledger_projections", side_effect=lambda r, ledger, actor: {**ledger, "sheet_sync": {}}) as project:
            cached = [self.get(runner, "/api/v7/ledger?customer=7") for _ in range(2)]
            with patch.object(api, "READS", v7_read_cache.ReadCache(max_bytes=0)):
                plain = self.get(Runner(), "/api/v7/ledger?customer=7")
        self.assertEqual(cached, [plain, plain])
        self.assertNotIn("events", cached[0][1])
        self.assertEqual(project.call_count, 3)
        self.assertEqual(runner.reads("get_ledger"), 1)
        # Phép chiếu nhận đủ events dù bản trước đã bị cắt events cho trình duyệt.
        self.assertEqual(project.call_args_list[1].args[1]["events"], [{"id": 1}])

    def test_post_does_not_use_the_cache(self):
        runner = Runner()
        with patch.object(api.READS, "run") as cached, patch.object(api, "validate", return_value=("adjust_month", {})), \
                patch.object(api, "touch_inbox"):
            api.handle("POST", "/api/v7/months/adjust", {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780",
                                                         "Content-Type": "application/json"}, b"{}", runner,
                       port=8780, host="127.0.0.1", actor="fake")
        cached.assert_not_called()
        self.assertEqual(runner.calls, ["adjust_month"])


if __name__ == "__main__":
    unittest.main()
