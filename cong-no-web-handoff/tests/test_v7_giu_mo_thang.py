"""Giữ tháng mở ở sổ còn chuyến chưa giá, khóa lại tới hạn (WEB-CHINH-01). Dữ liệu giả."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_giu_mo_thang as tool
from v7_api_validate import ApiError

STALE = "STALE_LEDGER"   # mã máy chủ trả khi expected_version cũ


def trip(trip_id, month="2026-11-01", missing=True, status="confirmed"):
    return {"id": trip_id, "month": month, "status": status, "is_missing_price": missing}


def legacy(row_id, unit=None, month="2026-11-01", kind="trip"):
    return {"id": row_id, "month": month, "kind": kind, "current": {"unit_price_vnd": unit, "deleted": False}}


def lock_event(locked, actor, month="2026-11-01"):
    return {"kind": "month_lock", "actor": actor, "after": {"month": month, "locked": locked}}


def ledger(trips=(), locks=(), events=(), today="2026-11-01", version=5, legacy_rows=()):
    return {"status": "active", "version": version, "today_month": today, "trips": list(trips), "legacy_rows": list(legacy_rows),
            "month_locks": [{"month": m, "locked": v} for m, v in locks], "events": list(events)}


class Runner:
    """`fail`: số lần set_month_lock của sổ đó ném STALE_LEDGER trước khi được; `reread`: sổ đọc lại sau lỗi (mặc định như cũ)."""
    def __init__(self, books, fail=None, reread=None, customers=None):
        self.books, self.fail, self.reread, self.calls = books, dict(fail or {}), dict(reread or {}), []
        self.customers = customers if customers is not None else [{"id": cid} for cid in books]

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "list_customers":
            return {"customers": self.customers}
        if function == "get_ledger":
            customer = payload["customer_id"]
            reads = sum(1 for f, p, _ in self.calls if f == "get_ledger" and p["customer_id"] == customer)
            return self.reread[customer] if reads > 1 and customer in self.reread else self.books[customer]
        if function == "set_month_lock":
            customer = payload["customer_id"]
            if self.fail.get(customer, 0) > 0:
                self.fail[customer] -= 1
                raise ApiError(409, STALE, "x")
            return {"version": payload["expected_version"] + 1}
        raise AssertionError(function)

    def writes(self):
        return [(p["customer_id"], p["month"], p["locked"], actor) for f, p, actor in self.calls if f == "set_month_lock"]


class Decide(unittest.TestCase):
    def test_work_counts_unpriced_pending_and_legacy_rows_of_that_month(self):
        book = ledger([trip(1), trip(2, missing=False), trip(3, status="pending_review"), trip(4, month="2026-10-01"),
                       trip(5, status="rejected")], legacy_rows=[legacy(21), legacy(22, unit="45000000"), legacy(23, kind="receipt"),
                                                                 legacy(24, month="2026-10-01")])
        self.assertEqual(tool.unpriced(book, "2026-11"), 3)

    def test_book_with_only_pending_or_legacy_work_is_opened(self):
        self.assertEqual(tool.decide(ledger([trip(3, status="pending_review")]), "2026-11", "open"), "OPEN")
        self.assertEqual(tool.decide(ledger(legacy_rows=[legacy(21)]), "2026-11", "open"), "OPEN")

    def test_open_before_month_end_writes_explicit_open_flag(self):
        self.assertEqual(tool.decide(ledger([trip(1)]), "2026-11", "open"), "OPEN")

    def test_open_after_month_end_reopens_default_locked_month(self):
        self.assertEqual(tool.decide(ledger([trip(1)], today="2026-12-01"), "2026-11", "open"), "OPEN")

    def test_open_after_machine_open_write_lock_still_opens(self):
        book = ledger([trip(1)], locks=[("2026-11-01", True)], events=[lock_event(True, tool.MACHINE)], today="2026-12-01")
        self.assertEqual(tool.decide(book, "2026-11", "open"), "OPEN")

    def test_book_without_unpriced_trips_is_left_alone(self):
        self.assertEqual(tool.decide(ledger([trip(1, missing=False)]), "2026-11", "open"), "ALL_PRICED")

    def test_month_already_open_is_skipped(self):
        book = ledger([trip(1)], locks=[("2026-11-01", False)], events=[lock_event(False, "nguoi-nhap")])
        self.assertEqual(tool.decide(book, "2026-11", "open"), "ALREADY_OPEN")

    def test_person_who_locked_month_is_respected(self):
        book = ledger([trip(1)], locks=[("2026-11-01", True)], events=[lock_event(True, "nguoi-nhap")], today="2026-12-01")
        self.assertEqual(tool.decide(book, "2026-11", "open"), "LOCKED_BY_PERSON")

    def test_person_lock_still_wins_after_machine_open_write_lock(self):
        # Người khóa; sau đó máy theo Sheet mở–ghi–khóa (hai sự kiện mới hơn). Ý người vẫn là khóa.
        events = [lock_event(True, tool.MACHINE), lock_event(False, tool.MACHINE), lock_event(True, "nguoi-nhap")]
        book = ledger([trip(1)], locks=[("2026-11-01", True)], events=events, today="2026-12-01")
        self.assertEqual(tool.decide(book, "2026-11", "open"), "LOCKED_BY_PERSON")

    def test_relock_only_month_the_tool_opened(self):
        mine = ledger(locks=[("2026-11-01", False)], events=[lock_event(False, tool.ACTOR)], today="2026-12-01")
        self.assertEqual(tool.decide(mine, "2026-11", "relock"), "LOCK")
        theirs = ledger(locks=[("2026-11-01", False)], events=[lock_event(False, "nguoi-nhap"), lock_event(False, tool.ACTOR)],
                        today="2026-12-01")
        self.assertEqual(tool.decide(theirs, "2026-11", "relock"), "OPENED_BY_OTHER")
        closed = ledger(locks=[("2026-11-01", True)], events=[lock_event(True, "nguoi-nhap"), lock_event(False, tool.ACTOR)])
        self.assertEqual(tool.decide(closed, "2026-11", "relock"), "NOT_OPEN")


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

    def test_relock_writes_locked_flag_and_reports_work_left(self):
        book = ledger([trip(1), trip(2)], locks=[("2026-11-01", False)], events=[lock_event(False, tool.ACTOR)], today="2026-12-16")
        runner = Runner({4: book})
        result = tool.run(runner, "2026-11", "relock", apply=True)
        self.assertEqual(runner.writes(), [(4, "2026-11-01", True, tool.ACTOR)])
        self.assertEqual(result["unpriced_trips"], 2)

    def test_relock_lists_books_a_person_reopened(self):
        reopened = ledger(locks=[("2026-11-01", False)], events=[lock_event(False, "nguoi-nhap"), lock_event(True, "nguoi-nhap"),
                                                                  lock_event(False, tool.ACTOR)], today="2026-12-16")
        result = tool.run(Runner({7: reopened}), "2026-11", "relock", apply=True)
        self.assertEqual(result["opened_by_other"], [7])
        self.assertEqual(result["written"], [])

    def test_stale_version_rereads_and_retries(self):
        runner = Runner({1: ledger([trip(1)], version=5)}, fail={1: 2}, reread={1: ledger([trip(1)], version=6)})
        result = tool.run(runner, "2026-11", "open", apply=True)
        self.assertEqual(result["written"], [1])
        self.assertEqual(result["errors"], {})
        versions = [p["expected_version"] for f, p, _ in runner.calls if f == "set_month_lock"]
        self.assertEqual(versions, [5, 6, 6])

    def test_reread_after_stale_that_shows_no_work_writes_nothing(self):
        # Người vừa ghi đủ giá giữa lúc đọc và ghi: đọc lại thấy không còn việc, không mở.
        runner = Runner({1: ledger([trip(1)])}, fail={1: 1}, reread={1: ledger([trip(1, missing=False)], version=6)})
        result = tool.run(runner, "2026-11", "open", apply=True)
        self.assertEqual(result["written"], [])
        self.assertEqual(result["skipped"], {"ALL_PRICED": 1})

    def test_book_still_failing_after_retries_is_reported_and_others_continue(self):
        runner = Runner({1: ledger([trip(1)]), 2: ledger([trip(2)])}, fail={1: tool.TRIES})
        result = tool.run(runner, "2026-11", "open", apply=True)
        self.assertEqual(result["written"], [2])
        self.assertEqual(result["errors"], {STALE: 1})
        self.assertEqual(result["error_books"], [1])

    def test_archived_and_inactive_books_are_skipped(self):
        runner = Runner({1: {"status": "not_cutover"}, 2: ledger([trip(1)])}, customers=[{"id": 1}, {"id": 2, "archived": True}])
        result = tool.run(runner, "2026-11", "open", apply=True)
        self.assertEqual(result["skipped"], {"INACTIVE": 1})
        self.assertEqual(runner.writes(), [])

    def test_bad_month_is_rejected(self):
        with self.assertRaises(ValueError):
            tool.run(Runner({}), "2026-13", "open", apply=False)

    def test_tool_actor_is_not_the_machine_actor(self):
        # Lượt nền của máy theo Sheet khóa lại tháng do AUTO_ACTOR mở; tháng công cụ mở phải mang tên khác.
        from v7_inbox import AUTO_ACTOR, machine_unlocks
        self.assertEqual(tool.MACHINE, AUTO_ACTOR)
        self.assertNotEqual(tool.ACTOR, AUTO_ACTOR)
        book = ledger(locks=[("2026-11-01", False)], events=[{**lock_event(False, tool.ACTOR), "at": "2026-11-30T22:00:00+07:00"}],
                      today="2026-12-01")
        self.assertEqual(machine_unlocks(book), {})


if __name__ == "__main__":
    unittest.main()
