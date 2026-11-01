"""Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): gom nhóm, tính nền, tính lại sổ vừa ghi."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_inbox
import v7_ledger_api as api
from v7_api_validate import ApiError


def projection(**parts):
    base = {"sheet_sync": {"items": [], "removed_items": []}, "sheet_receipts": {"ready": [], "review": []},
            "sheet_prices": {"ready": [], "review": []}, "ps_fees": {"ready": [], "review": []}}
    base.update(parts)
    return base


def wait_idle(inbox):
    deadline = time.monotonic() + 5
    while inbox.running and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not inbox.running


class Runner:
    def __init__(self, customers):
        self.customers, self.calls = customers, []

    def run(self, function, payload, actor):
        self.calls.append(function)
        if function == "list_customers":
            return {"customers": [{"id": c, "status": "active"} for c in self.customers] + [{"id": 99, "status": "draft"}]}
        if function == "get_ledger":
            if payload["customer_id"] == 5:
                raise ApiError(503, "DB_UNAVAILABLE", "x")
            return {"customer_id": payload["customer_id"]}
        raise AssertionError(function)


class SummarizeTests(unittest.TestCase):
    def test_groups(self):
        items = [{"sync_state": "NEW"}, {"sync_state": "NEW"},
                 {"sync_state": "CONFLICT", "sync_reason": "DIFFERENT_FIELDS", "changed_fields": ["origin", "shipper"]},
                 {"sync_state": "CONFLICT", "sync_reason": "DIFFERENT_FIELDS", "changed_fields": ["event_date", "origin"]},
                 {"sync_state": "CONFLICT", "sync_reason": "OTHER_BOOK_LEGACY", "changed_fields": []},
                 {"sync_state": "CONFLICT", "sync_reason": "OTHER_BOOK_LEGACY", "changed_fields": []}]
        book = v7_inbox.summarize(7, projection(
            sheet_sync={"items": items, "removed_items": [{"amount_vnd": "300"}, {"amount_vnd": None}]},
            sheet_receipts={"ready": [{"amount_vnd": "100"}], "review": [{"amount_vnd": "50"}, {"amount_vnd": ""}]},
            sheet_prices={"ready": [], "review": [{}]}, ps_fees={"ready": [{}], "review": [{}, {}]}))
        self.assertEqual(book, {
            "customer_id": 7,
            "receipts": {"ready": 1, "review": 2, "amount_vnd": "150"},   # phiếu không có số tiền không cộng như 0
            "removed": {"count": 2, "amount_vnd": "300"},
            "trips_new": 2,
            "trips_check": {"count": 3, "reasons": {"FIELDS": 1, "OTHER_BOOK_LEGACY": 2}},
            "text_diff": 1,
            "prices": {"ready": 0, "review": 1},
            "ps": {"ready": 1, "review": 2}})

    def test_empty_book_is_dropped_and_unavailable_raises(self):
        self.assertIsNone(v7_inbox.summarize(7, projection()))
        with self.assertRaises(ValueError):
            v7_inbox.summarize(7, projection(sheet_receipts={"unavailable": True, "ready": [], "review": []}))


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.paths = [Path(self.dir.name) / f"{n}.json" for n in ("s", "p")]
        for path in self.paths:
            path.write_text("{}", encoding="utf-8")
        self.outputs = {1: projection(sheet_sync={"items": [{"sync_state": "NEW"}], "removed_items": []}),
                        2: projection()}
        self.inbox = v7_inbox.Inbox(lambda runner, ledger, actor: self.outputs[ledger["customer_id"]],
                                    lambda: tuple(str(p) for p in self.paths),
                                    lambda: {"sheet_at": "2026-11-01T07:45:00+00:00"})

    def tearDown(self):
        self.dir.cleanup()

    def test_first_view_computes_in_background_then_ready(self):
        runner = Runner([1, 2, 5])
        first = self.inbox.view(runner)
        self.assertIn(first["state"], ("computing", "ready"))
        wait_idle(self.inbox)
        view = self.inbox.view(runner)
        self.assertEqual(view["state"], "ready")
        self.assertEqual([b["customer_id"] for b in view["books"]], [1])   # sổ 2 không có việc
        self.assertEqual(view["failed"], [5])                               # sổ lỗi được liệt kê
        self.assertEqual((view["books_total"], view["books_done"]), (3, 3))
        self.assertEqual(view["sheet_at"], "2026-11-01T07:45:00+00:00")
        self.assertEqual(runner.calls.count("list_customers"), 1)          # hàm đọc dùng chung lấy một lần

    def test_dirty_book_recomputed_on_next_view(self):
        runner = Runner([1, 2])
        self.inbox.start(runner)
        wait_idle(self.inbox)
        self.outputs[1] = projection()
        self.outputs[2] = projection(sheet_receipts={"ready": [{"amount_vnd": "9"}], "review": []})
        self.inbox.mark_dirty(1, 2, None, "x")
        view = self.inbox.view(runner)
        self.assertFalse(view["refreshing"])
        self.assertEqual([b["customer_id"] for b in view["books"]], [2])

    def test_new_snapshot_refreshes_once_settled_and_keeps_old_result(self):
        runner = Runner([1])
        now = [time.time()]
        self.inbox.clock = lambda: now[0]
        self.inbox.start(runner)
        wait_idle(self.inbox)
        stamp = now[0] + 5
        os.utime(self.paths[0], (stamp, stamp))
        self.outputs[1] = projection()
        # Runner khác còn đang ghi (file mới nhất chưa đủ cũ): giữ kết quả cũ, chưa tính lại.
        view = self.inbox.view(runner)
        self.assertEqual((view["state"], view["refreshing"], len(view["books"])), ("ready", False, 1))
        now[0] = stamp + v7_inbox.SETTLE_SECONDS + 1
        self.assertEqual(self.inbox.view(runner)["state"], "ready")
        wait_idle(self.inbox)
        self.assertEqual(self.inbox.view(runner)["books"], [])

    def test_missing_snapshot_is_unavailable(self):
        for path in self.paths:
            path.unlink()
        self.assertEqual(self.inbox.view(Runner([]))["state"], "unavailable")


class ApiInboxRoute(unittest.TestCase):
    def call(self, method, target, raw=b""):
        headers = {"Host": "127.0.0.1:8780"}
        if method == "POST":
            headers.update({"Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"})
        return api.handle(method, target, headers, raw, object(), port=8780, host="127.0.0.1", actor="tester")

    def test_get_returns_view_and_rejects_query(self):
        with patch.object(api.INBOX, "view", return_value={"state": "computing"}) as view:
            self.assertEqual(self.call("GET", "/api/v7/inbox"), (200, {"state": "computing"}))
            view.assert_called_once()
        with self.assertRaises(ApiError):
            self.call("GET", "/api/v7/inbox?x=1")

    def test_post_marks_books_dirty(self):
        with patch.dict(api.POST_HANDLERS, {"/api/v7/reminders": lambda raw, runner, actor: (200, {"ok": True})}), \
                patch.object(api.INBOX, "mark_dirty") as mark:
            self.call("POST", "/api/v7/reminders", b'{"customer_id": 7, "source": "copy-button"}')
        mark.assert_called_once_with(7, None, None)


if __name__ == "__main__":
    unittest.main()
