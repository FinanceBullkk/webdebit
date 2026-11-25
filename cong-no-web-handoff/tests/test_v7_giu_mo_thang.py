"""Giữ tháng mở ở sổ còn chuyến chưa giá, khóa lại tới hạn (WEB-CHINH-01). Dữ liệu giả."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_giu_mo_thang as tool
from v7_api_validate import ApiError


def trip(trip_id, month="2026-11-01", missing=True, status="confirmed"):
    return {"id": trip_id, "month": month, "status": status, "is_missing_price": missing}


def lock_event(locked, actor, month="2026-11-01"):
    return {"kind": "month_lock", "actor": actor, "after": {"month": month, "locked": locked}}


def ledger(trips=(), locks=(), events=(), today="2026-11-01", version=5):
    return {"status": "active", "version": version, "today_month": today, "trips": list(trips),
            "month_locks": [{"month": m, "locked": v} for m, v in locks], "events": list(events)}


class Runner:
    def __init__(self, books, fail=None):
        self.books, self.fail, self.calls = books, fail, []

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "list_customers":
            return {"customers": [{"id": cid} for cid in self.books]}
        if function == "get_ledger":
            return self.books[payload["customer_id"]]
        if function == "set_month_lock":
            if self.fail == payload["customer_id"]:
                raise ApiError(409, "VERSION_CONFLICT", "x")
            return {"version": payload["expected_version"] + 1}
        raise AssertionError(function)

    def writes(self):
        return [(p["customer_id"], p["month"], p["locked"], actor) for f, p, actor in self.calls if f == "set_month_lock"]


class Decide(unittest.TestCase):
    def test_unpriced_counts_only_confirmed_trips_of_that_month(self):
        book = ledger([trip(1), trip(2, missing=False), trip(3, status="pending_review"), trip(4, month="2026-10-01")])
        self.assertEqual(tool.unpriced(book, "2026-11"), 1)

    def test_open_before_month_end_writes_explicit_open_flag(self):
        self.assertEqual(tool.decide(ledger([trip(1)]), "2026-11", "open"), "OPEN")

    def test_open_after_month_end_reopens_default_locked_month(self):
        self.assertEqual(tool.decide(ledger([trip(1)], today="2026-12-01"), "2026-11", "open"), "OPEN")

    def test_open_after_machine_open_write_lock_still_opens(self):
        book = ledger([trip(1)], locks=[("2026-11-01", True)], events=[lock_event(True, "may-theo-sheet")], today="2026-12-01")
        self.assertEqual(tool.decide(book, "2026-11", "open"), "OPEN")

    def test_book_without_unpriced_trips_is_left_alone(self):
        self.assertEqual(tool.decide(ledger([trip(1, missing=False)]), "2026-11", "open"), "ALL_PRICED")

    def test_month_already_open_is_skipped(self):
        book = ledger([trip(1)], locks=[("2026-11-01", False)], events=[lock_event(False, "nguoi-nhap")])
        self.assertEqual(tool.decide(book, "2026-11", "open"), "ALREADY_OPEN")

    def test_person_who_locked_month_is_respected(self):
        book = ledger([trip(1)], locks=[("2026-11-01", True)], events=[lock_event(True, "nguoi-nhap")], today="2026-12-01")
        self.assertEqual(tool.decide(book, "2026-11", "open"), "LOCKED_BY_PERSON")

    def test_relock_only_month_the_tool_opened(self):
        mine = ledger(locks=[("2026-11-01", False)], events=[lock_event(False, tool.ACTOR)], today="2026-12-01")
        self.assertEqual(tool.decide(mine, "2026-11", "relock"), "LOCK")
        theirs = ledger(locks=[("2026-11-01", False)], events=[lock_event(False, "nguoi-nhap"), lock_event(False, tool.ACTOR)],
                        today="2026-12-01")
        self.assertEqual(tool.decide(theirs, "2026-11", "relock"), "OPENED_BY_OTHER")
        closed = ledger(locks=[("2026-11-01", True)], events=[lock_event(True, "nguoi-nhap"), lock_event(False, tool.ACTOR)])
        self.assertEqual(tool.decide(closed, "2026-11", "relock"), "NOT_OPEN")

    def test_relock_reports_trips_still_unpriced(self):
        book = ledger([trip(1), trip(2)], locks=[("2026-11-01", False)], events=[lock_event(False, tool.ACTOR)], today="2026-12-01")
        result = tool.run(Runner({7: book}), "2026-11", "relock", apply=True)
        self.assertEqual(result["written"], [7])
        self.assertEqual(result["unpriced_trips"], 2)


class Run(unittest.TestCase):
    def test_dry_run_counts_without_writing(self):
        runner = Runner({1: ledger([trip(1), trip(2)]), 2: ledger([trip(3, missing=False)])})
        result = tool.run(runner, "2026-11", "open", apply=False)
        self.assertEqual(result["to_write"], [1])
        self.assertEqual(result["unpriced_trips"], 2)
        self.assertEqual(result["skipped"], {"ALL_PRICED": 1})
        self.assertEqual(runner.writes(), [])

    def test_apply_writes_open_flag_with_tool_actor_and_version(self):
        runner = Runner({1: ledger([trip(1)], version=9)})
        result = tool.run(runner, "2026-11", "open", apply=True)
        self.assertEqual(result["written"], [1])
        self.assertEqual(runner.writes(), [(1, "2026-11-01", False, tool.ACTOR)])
        payload = next(p for f, p, _ in runner.calls if f == "set_month_lock")
        self.assertEqual(payload["expected_version"], 9)
        self.assertEqual(len(payload["idempotency_key"]), 64)

    def test_relock_writes_locked_flag(self):
        book = ledger(locks=[("2026-11-01", False)], events=[lock_event(False, tool.ACTOR)], today="2026-12-01")
        runner = Runner({4: book})
        tool.run(runner, "2026-11", "relock", apply=True)
        self.assertEqual(runner.writes(), [(4, "2026-11-01", True, tool.ACTOR)])

    def test_one_book_error_does_not_stop_others(self):
        runner = Runner({1: ledger([trip(1)]), 2: ledger([trip(2)])}, fail=1)
        result = tool.run(runner, "2026-11", "open", apply=True)
        self.assertEqual(result["written"], [2])
        self.assertEqual(result["errors"], {"VERSION_CONFLICT": 1})

    def test_inactive_book_is_skipped(self):
        runner = Runner({1: {"status": "not_cutover"}})
        self.assertEqual(tool.run(runner, "2026-11", "open", apply=True)["skipped"], {"INACTIVE": 1})

    def test_bad_month_is_rejected(self):
        with self.assertRaises(ValueError):
            tool.run(Runner({}), "2026-13", "open", apply=False)

    def test_tool_actor_is_not_the_machine_actor(self):
        # Lượt nền của máy theo Sheet khóa lại tháng do AUTO_ACTOR mở; tháng công cụ mở phải mang tên khác.
        from v7_inbox import AUTO_ACTOR, machine_unlocks
        self.assertNotEqual(tool.ACTOR, AUTO_ACTOR)
        book = ledger(locks=[("2026-11-01", False)], events=[{**lock_event(False, tool.ACTOR), "at": "2026-11-30T22:00:00+07:00"}],
                      today="2026-12-01")
        self.assertEqual(machine_unlocks(book), {})


if __name__ == "__main__":
    unittest.main()
