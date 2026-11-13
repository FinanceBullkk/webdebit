"""Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): gom nhóm, tính nền, tính lại sổ vừa ghi."""

import json
import os
import sys
import tempfile
import threading
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
        # Trường của P2 (phiếu chi tiết, phiên bản, nợ) có test riêng; ở đây so bảy nhóm.
        book = {key: value for key, value in book.items() if key not in ("version", "outstanding_vnd")}
        book["receipts"] = {key: book["receipts"][key] for key in ("ready", "review", "amount_vnd")}
        self.assertEqual(book, {
            "customer_id": 7,
            "receipts": {"ready": 1, "review": 2, "amount_vnd": "150"},   # phiếu không có số tiền không cộng như 0
            "removed": {"count": 2, "amount_vnd": "300"},
            "trips_new": 2,
            "road_new": 0,
            "trips_check": {"count": 3, "reasons": {"FIELDS": 1, "OTHER_BOOK_LEGACY": 2}},
            "text_diff": 1,
            "prices": {"ready": 0, "review": 1},
            "prices_auto": 0,
            "prices_conflict": 0,
            "ps": {"ready": 1, "review": 2},
            "ps_auto": 1})

    def test_road_trips_count_as_new_and_checks(self):
        road = {"items": [{"sync_state": "NEW"}, {"sync_state": "NEW"}, {"sync_state": "CONFLICT", "sync_reason": "MONTH_DIFFERS"}]}
        book = v7_inbox.summarize(7, projection(sheet_sync={"items": [{"sync_state": "NEW"}], "removed_items": []}, sheet_road=road))
        self.assertEqual((book["trips_new"], book["road_new"], book["trips_check"]),
                         (3, 2, {"count": 1, "reasons": {"ROAD_MONTH_DIFFERS": 1}}))
        # road.json hỏng (phần chiếu "unavailable") không làm hỏng sổ: chỉ không có việc chuyến bộ.
        broken = v7_inbox.summarize(7, projection(sheet_road={"unavailable": True, "items": []},
                                                  sheet_sync={"items": [{"sync_state": "NEW"}], "removed_items": []}))
        self.assertEqual((broken["trips_new"], broken["road_new"]), (1, 0))

    def test_machine_price_rows_from_october_open_or_locked(self):
        prices = {"ready": [{"month": "2026-11"}, {"month": "2026-09"}],
                  "review": [{"status": "MONTH_LOCKED", "month": "2026-10"}, {"status": "MONTH_LOCKED", "month": "2026-09"},
                             {"status": "CONFLICT", "month": "2026-10"}, {"status": "MANUAL", "month": "2026-10"},
                             {"status": "AMBIGUOUS", "month": "2026-10"}]}
        # Trước 10/2026 sổ gốc là chuẩn; giá khác web, phụ phí gõ tay, nhiều chuyến khớp để người quyết.
        self.assertEqual([r["month"] for r in v7_inbox.auto_prices(prices)], ["2026-11", "2026-10"])
        book = v7_inbox.summarize(7, projection(sheet_prices=prices))
        self.assertEqual((book["prices"], book["prices_auto"]), ({"ready": 2, "review": 5}, 2))

    def test_receipt_details_for_writing_at_the_inbox(self):
        ledger = projection(sheet_receipts={"snapshot_sha256": "b" * 64,
            "ready": [{"date": "2026-10-30", "amount_vnd": "100", "debt_month": "2026-09-01", "note": " 30/10 tt "},
                      {"date": "2026-09-05", "amount_vnd": "40", "debt_month": "2026-08-01", "note": ""},
                      {"date": "2026-11-01", "amount_vnd": "5", "debt_month": "2026-11-01", "note": ""}],
            "review": [{"date": None, "amount_vnd": "7", "debt_month": "2026-08-01", "note": "?", "status": "NO_DATE"}]})
        ledger.update(version=12, total_outstanding_vnd="900", today_month="2026-11-01",
                      month_locks=[{"month": "2026-09-01", "locked": True}, {"month": "2026-10-01", "locked": False}])
        receipts = v7_inbox.summarize(7, ledger)["receipts"]
        book = v7_inbox.summarize(7, ledger)
        self.assertEqual((book["version"], book["outstanding_vnd"]), (12, "900"))
        self.assertEqual((receipts["ready"], receipts["review"], receipts["ready_amount_vnd"], receipts["amount_vnd"]), (3, 1, "145", "152"))
        self.assertEqual(receipts["snapshot_sha256"], "b" * 64)
        self.assertEqual(receipts["items"][0], {"status": "READY", "date": "2026-10-30", "amount_vnd": "100",
                                                "debt_month": "2026-09-01", "note": "30/10 tt"})
        self.assertEqual(receipts["items"][-1]["status"], "NO_DATE")
        # T9 khóa theo cờ, T10 mở theo cờ, T11 là tháng hiện tại (không có hàng) nên mở.
        self.assertEqual(receipts["locked_months"], ["2026-09"])
        ledger["month_locks"] = []
        self.assertEqual(v7_inbox.summarize(7, ledger)["receipts"]["locked_months"], ["2026-09", "2026-10"])

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

    def test_dirty_books_are_recomputed_in_parallel(self):
        # HIEU-NANG-01: ba sổ vừa ghi phải cùng vào get_ledger thì barrier mới mở; tính lần lượt sẽ hết giờ.
        runner = Runner([1, 2, 3])
        self.outputs[3] = projection()
        self.inbox.start(runner)
        wait_idle(self.inbox)
        barrier = threading.Barrier(3, timeout=5)
        plain = runner.run

        def run(function, payload, actor):
            if function == "get_ledger":
                barrier.wait()
            return plain(function, payload, actor)
        runner.run = run
        self.outputs[2] = projection(sheet_receipts={"ready": [{"amount_vnd": "9"}], "review": []})
        self.inbox.mark_dirty(1, 2, 3)
        view = self.inbox.view(runner)
        self.assertFalse(barrier.broken)
        self.assertEqual([b["customer_id"] for b in view["books"]], [1, 2])
        self.assertEqual(self.inbox.dirty, set())

    def test_two_views_at_once_recompute_dirty_books_once(self):
        runner = Runner([1, 2])
        self.inbox.start(runner)
        wait_idle(self.inbox)
        started, release = threading.Event(), threading.Event()
        plain, ledgers = runner.run, []

        def run(function, payload, actor):
            if function == "get_ledger":
                ledgers.append(payload["customer_id"])
                started.set()
                release.wait(5)
            return plain(function, payload, actor)
        runner.run = run
        self.inbox.mark_dirty(1)
        views = []
        threads = [threading.Thread(target=lambda: views.append(self.inbox.view(runner))) for _ in range(2)]
        threads[0].start()
        self.assertTrue(started.wait(5))
        threads[1].start()
        time.sleep(0.05)   # lượt sau đã tới chỗ chờ
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(ledgers, [1])
        self.assertEqual(len(views), 2)

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

    def test_background_tick_refreshes_new_snapshot_without_any_view(self):
        """Máy chạy theo đợt Sheet kể cả khi không ai mở Việc cần làm: nhịp nền tự tính lại khi bản chụp đã yên."""
        runner = Runner([1])
        now = [time.time()]
        self.inbox.clock = lambda: now[0]
        self.assertTrue(self.inbox.tick(runner))   # chưa tính lần nào
        wait_idle(self.inbox)
        self.assertFalse(self.inbox.tick(runner))  # bản chụp chưa đổi
        stamp = now[0] + 5
        os.utime(self.paths[0], (stamp, stamp))
        self.assertFalse(self.inbox.tick(runner))  # chưa yên
        now[0] = stamp + v7_inbox.SETTLE_SECONDS + 1
        self.outputs[1] = projection()
        self.inbox.keep_fresh(runner, every=0.01)
        deadline = time.monotonic() + 5
        while self.inbox.books and time.monotonic() < deadline:
            time.sleep(0.01)
        self.inbox.stopped.set()
        wait_idle(self.inbox)
        self.assertEqual(self.inbox.books, {})
        self.assertEqual(runner.calls.count("list_customers"), 2)

    def test_view_carries_last_reconcile_and_marks_books_still_matching(self):
        reconcile = Path(self.dir.name) / "reconcile.json"
        runner = Runner([1, 2])
        self.outputs[1].update(total_outstanding_vnd="500")
        self.outputs[2] = projection(sheet_sync={"items": [{"sync_state": "NEW"}], "removed_items": []}, total_outstanding_vnd="700")
        with patch.object(v7_inbox, "RECONCILE_PATH", str(reconcile)):
            self.inbox.start(runner)
            wait_idle(self.inbox)
            self.assertIsNone(self.inbox.view(runner)["reconcile"])   # chưa có lượt nào: không làm hỏng hộp việc
            reconcile.write_text(json.dumps({"version": 1, "checked_at": "2026-11-04T08:05:00+07:00", "counts": {"KHOP": 2},
                                             "matched": {"1": "500", "2": "650"}, "customers": []}), encoding="utf-8")
            view = self.inbox.view(runner)
            self.assertEqual((view["reconcile"]["checked_at"], view["reconcile"]["matched_ids"]), ("2026-11-04T08:05:00+07:00", [1, 2]))
            self.assertNotIn("matched", view["reconcile"])
            # Sổ 2 đã đổi tổng từ lúc đối soát: việc của sổ vẫn phải hiện.
            self.assertEqual({b["customer_id"]: b["sheet_matched"] for b in view["books"]}, {1: True, 2: False})
            # Tổng khớp mà giá từng chuyến khác Sheet: hai chỗ bù trừ nhau, không ẩn.
            self.outputs[1].update(sheet_prices={"ready": [], "review": [{"status": "CONFLICT", "month": "2026-10"}]})
            self.inbox.key = None
            self.inbox.start(runner)
            wait_idle(self.inbox)
            self.assertEqual({b["customer_id"]: b["sheet_matched"] for b in self.inbox.view(runner)["books"]}, {1: False, 2: False})
            reconcile.write_text("hỏng", encoding="utf-8")
            os.utime(reconcile, (1, 1))
            self.assertIsNone(self.inbox.view(runner)["reconcile"])

    def test_missing_snapshot_is_unavailable(self):
        for path in self.paths:
            path.unlink()
        self.assertEqual(self.inbox.view(Runner([]))["state"], "unavailable")



class AutoTextTests(unittest.TestCase):
    """P3a (HANG-CHO-01 Q1, KHOA-CHU-01): máy tự lấy theo Sheet các ô chữ lệch, chỉ khi bật."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "s.json"
        self.path.write_text("{}", encoding="utf-8")
        self.resolved = False
        self.calls = []
        items = [
            {"sync_state": "CONFLICT", "sync_reason": "DIFFERENT_FIELDS", "changed_fields": ["origin", "destination"],
             "existing_kind": "legacy", "existing_id": 5, "source_row": 12, "container": "C1", "origin": "KHO B",
             "destination": " CANG D ", "existing_values": {"origin": "KHO A", "destination": "CANG C"}},
            {"sync_state": "CONFLICT", "sync_reason": "DIFFERENT_FIELDS", "changed_fields": ["event_date"],
             "existing_kind": "trip", "existing_id": 6, "source_row": 13, "event_date": "2026-10-02", "existing_values": {}},
            {"sync_state": "CONFLICT", "sync_reason": "DIFFERENT_FIELDS", "changed_fields": ["shipper_unavailable"],
             "existing_kind": "legacy", "existing_id": 7, "source_row": 14, "existing_values": {}},
            {"sync_state": "CONFLICT", "sync_reason": "DIFFERENT_FIELDS", "changed_fields": ["shipper"],
             "existing_kind": "legacy", "existing_id": 8, "source_row": 15, "shipper": "", "existing_values": {"shipper": "X"}},
        ]
        self.items = items

        def project(runner, ledger, actor):
            text = [] if self.resolved else [dict(item, sync_state="CONFLICT") for item in items[:1]]
            return projection(sheet_sync={"items": text, "removed_items": []})
        self.inbox = v7_inbox.Inbox(project, lambda: (str(self.path),))
        test = self

        class Runner:
            version = 3

            def run(self, function, payload, actor):
                test.calls.append((function, payload, actor))
                if function == "list_customers":
                    return {"customers": [{"id": 1, "status": "active"}]}
                if function == "get_ledger":
                    return {"customer_id": 1, "version": self.version}
                if function == "resolve_sheet_conflict":
                    self.version += 1
                    if payload["field"] == "destination":
                        test.resolved = True
                    return {"version": self.version}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def run_once(self):
        with patch.object(v7_inbox, "sheet_projection", return_value={"snapshot_sha256": "e" * 64, "items": self.items}):
            self.inbox.start(self.runner)
            wait_idle(self.inbox)
        return self.inbox.view(self.runner)

    def test_off_by_default(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": ""}):
            view = self.run_once()
        self.assertFalse([c for c in self.calls if c[0] == "resolve_sheet_conflict"])
        self.assertEqual((view["auto"]["text_enabled"], view["books"][0]["text_diff"]), (False, 1))

    def test_takes_sheet_text_only_and_logs(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text"}):
            view = self.run_once()
        resolves = [c for c in self.calls if c[0] == "resolve_sheet_conflict"]
        self.assertEqual([(c[1]["field"], c[1]["expected_version"], c[1]["target_value"], c[1]["sheet_value"]) for c in resolves],
                         [("origin", 3, "KHO A", "KHO B"), ("destination", 4, "CANG C", " CANG D ")])
        self.assertTrue(all(c[1]["decision"] == "use_sheet" and c[2] == v7_inbox.AUTO_ACTOR and c[1]["target_kind"] == "legacy"
                            and c[1]["target_id"] == 5 and c[1]["snapshot_sha256"] == "e" * 64 for c in resolves))
        self.assertEqual(len({c[1]["idempotency_key"] for c in resolves}), 2)
        # Lệch ngày, thiếu shipper trên Sheet, giá trị Sheet trống: để người quyết.
        self.assertEqual(view["books"], [])
        self.assertEqual((view["auto"]["today_count"], view["auto"]["today_books"], view["auto"]["errors"]), (2, 1, 0))
        self.assertEqual(view["auto"]["items"][0]["after"], "CANG D")


class AutoTripsTests(unittest.TestCase):
    """P3b (HANG-CHO-01 Q2 theo Q5 A): máy bấm thay "Duyệt" cho chuyến mới đủ điều kiện, chỉ khi bật."""

    NOW = 1793509200.0   # 1/11/2026 12:00 giờ VN

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "s.json"
        self.path.write_text("{}", encoding="utf-8")
        self.pasted = False
        self.calls = []
        new = {"sync_state": "NEW", "book_match": "COMMODITY_OK", "carrier": "HT", "origin": "KHO", "destination": "CANG"}
        self.items = [
            dict(new, source_row=10, container="OK1", event_date="2026-11-01"),
            dict(new, source_row=11, container="MIS1", event_date="2026-11-01", book_match="COMMODITY_MISMATCH"),
            dict(new, source_row=12, container="UNK1", event_date="2026-11-01", book_match="COMMODITY_UNKNOWN"),
            dict(new, source_row=13, container="LOCK1", event_date="2026-10-05"),    # tháng 10 khóa: máy mở, dán, khóa lại
            dict(new, source_row=17, container="OLD1", event_date="2026-09-05"),     # trước 10/2026: sổ gốc là chuẩn
            dict(new, source_row=14, container="FUT1", event_date="2026-11-02"),     # sau hôm nay
            dict(new, source_row=15, container="DUP1", event_date="2026-11-01"),     # paste_trips đẩy sang chờ kiểm
            {"sync_state": "CONFLICT", "sync_reason": "OTHER_CUSTOMER", "source_row": 16, "container": "OC1",
             "event_date": "2026-11-01", "book_match": "COMMODITY_OK"},
        ]

        def project(runner, ledger, actor):
            return projection(sheet_sync={"items": [] if self.pasted else [{"sync_state": "NEW"}], "removed_items": []})
        self.inbox = v7_inbox.Inbox(project, lambda: (str(self.path),), clock=lambda: self.NOW)
        test = self

        class Runner:
            version = 3

            def run(self, function, payload, actor):
                test.calls.append((function, payload, actor))
                if function == "list_customers":
                    return {"customers": [{"id": 1, "status": "active"}]}
                if function == "get_ledger":
                    return {"customer_id": 1, "version": self.version, "today_month": "2026-11-01", "month_locks": []}
                if function == "set_month_lock":
                    self.version += 1
                    return {"version": self.version}
                if function == "paste_trips":
                    if test.fail:
                        raise ApiError(409, "STALE_LEDGER", "x")
                    self.version += 1
                    test.pasted = True
                    ids = [100 + n for n in range(len(payload["trips"]))]
                    return {"trip_ids": ids, "pending_review": [{"trip_id": ids[-1], "reason": "WEB_DUPLICATE"}]}
                raise AssertionError(function)
        self.fail = False
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def run_once(self):
        with patch.object(v7_inbox, "sheet_projection", return_value={"snapshot_sha256": "e" * 64, "items": self.items}):
            self.inbox.start(self.runner)
            wait_idle(self.inbox)
        return self.inbox.view(self.runner)

    def test_off_by_default(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text"}):
            view = self.run_once()
        self.assertFalse([c for c in self.calls if c[0] == "paste_trips"])
        self.assertEqual((view["auto"]["trips_enabled"], view["books"][0]["trips_new"]), (False, 1))

    def test_pastes_only_eligible_rows_and_logs(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text,trips"}):
            view = self.run_once()
        writes = [(c[0], c[1].get("month") or c[1].get("debt_month"), c[1].get("locked"), c[1]["expected_version"])
                  for c in self.calls if c[0] in ("paste_trips", "set_month_lock")]
        # Tháng 10 khóa: mở, dán, khóa lại, đúng phiên bản nối tiếp; rồi tháng 11 đang mở dán thẳng.
        self.assertEqual(writes, [("set_month_lock", "2026-10-01", False, 3), ("paste_trips", "2026-10-01", None, 4),
                                  ("set_month_lock", "2026-10-01", True, 5), ("paste_trips", "2026-11-01", None, 6)])
        pastes = [c for c in self.calls if c[0] == "paste_trips"]
        self.assertTrue(all(c[2] == v7_inbox.AUTO_ACTOR for c in self.calls if c[0] in ("paste_trips", "set_month_lock")))
        self.assertEqual([[t["container"] for t in c[1]["trips"]] for c in pastes], [["LOCK1"], ["OK1", "DUP1"]])
        self.assertTrue(all(t["unitPriceVnd"] is None and t["src"].startswith("sheet:" + "e" * 64)
                            for c in pastes for t in c[1]["trips"]))
        auto = view["auto"]
        self.assertEqual((auto["today_trips"], auto["today_trip_books"], auto["today_trips_pending"], auto["errors"]), (3, 1, 2, 0))
        self.assertEqual({(i["container"], i["pending"]) for i in auto["trip_items"]},
                         {("LOCK1", True), ("OK1", False), ("DUP1", True)})
        self.assertEqual((auto["today_count"], auto["items"]), (0, []))   # ô chữ đếm riêng
        self.assertEqual(view["books"], [])

    def test_same_key_on_rerun_and_error_stops_book(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "trips"}):
            self.run_once()
            self.pasted = False
            self.inbox.key = None
            self.run_once()
        keys = [c[1]["idempotency_key"] for c in self.calls if c[0] == "paste_trips"]
        self.assertEqual((len(keys), len(set(keys))), (4, 2))   # cùng bản chụp, cùng dòng: DB trả lại kết quả cũ
        self.fail, self.pasted = True, False
        self.inbox.key = None
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "trips"}):
            view = self.run_once()
        self.assertEqual(view["auto"]["errors"], 1)
        # Lệnh dán lỗi trong tháng khóa: máy vẫn khóa lại tháng đã mở rồi mới dừng sổ.
        last = [(c[0], c[1].get("locked")) for c in self.calls if c[0] in ("paste_trips", "set_month_lock")][-3:]
        self.assertEqual(last, [("set_month_lock", False), ("paste_trips", None), ("set_month_lock", True)])


def price_row(kind, target, month, status="READY", fee=None, web=None):
    return {"target_kind": kind, "target_id": target, "month": month, "status": status, "container": f"CONT{target}",
            "date": f"{month}-05", "source_row": target, "sheet_unit_price_vnd": "50000000", "sheet_other_fee_vnd": fee,
            "web_unit_price_vnd": web, "web_other_fee_vnd": None, "month_locked": month != "2026-11"}


class AutoPricesTests(unittest.TestCase):
    """MAY-GIA-01: máy ghi giá Sheet sẵn sàng như nút "Ghi N giá từ Sheet", tháng khóa thì mở, ghi, khóa lại."""

    NOW = 1793595600.0   # 2/11/2026 12:00 giờ VN

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "p.json"
        self.path.write_text("{}", encoding="utf-8")
        self.calls, self.written, self.fail = [], False, None
        self.ready = [price_row("trip", 11, "2026-11"), price_row("trip", 12, "2026-09")]   # T9: trước mốc, để người
        self.review = [price_row("trip", 21, "2026-10", "MONTH_LOCKED"),
                       price_row("legacy", 22, "2026-10", "MONTH_LOCKED", fee="300000"),
                       price_row("trip", 23, "2026-09", "MONTH_LOCKED"),
                       price_row("trip", 24, "2026-10", "CONFLICT", web="49000000")]

        def project(runner, ledger, actor):
            if self.written:
                return projection(sheet_prices={"ready": [self.ready[1]], "review": self.review[2:]})
            return projection(sheet_prices={"ready": self.ready, "review": self.review})
        self.inbox = v7_inbox.Inbox(project, lambda: (str(self.path),), clock=lambda: self.NOW)
        test = self

        class Runner:
            version = 3

            def run(self, function, payload, actor):
                test.calls.append((function, payload, actor))
                if function == "list_customers":
                    return {"customers": [{"id": 1, "status": "active"}]}
                if function == "get_ledger":
                    return {"customer_id": 1, "version": self.version, "today_month": "2026-11-01", "month_locks": []}
                if function in ("set_month_lock", "edit_trip_price", "edit_legacy_trip"):
                    if function == "edit_trip_price" and payload["trip_id"] == test.fail:
                        raise ApiError(409, "STALE_LEDGER", "x")
                    test.written = function != "set_month_lock" or test.written
                    self.version += 1
                    return {"version": self.version}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def run_once(self):
        prices = {"snapshot_sha256": "f" * 64, "ready": self.ready, "review": self.review}
        with patch.object(v7_inbox, "price_projection", return_value=prices):
            self.inbox.start(self.runner)
            wait_idle(self.inbox)
        return self.inbox.view(self.runner)

    def writes(self):
        out = []
        for function, payload, actor in self.calls:
            if function == "set_month_lock":
                out.append((function, payload["month"], payload["locked"], payload["expected_version"], actor))
            elif function in ("edit_trip_price", "edit_legacy_trip"):
                out.append((function, payload.get("trip_id") or payload.get("legacy_row_id"), payload.get("field"),
                            payload["expected_version"], actor))
        return out

    def test_off_by_default(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text,trips"}):
            view = self.run_once()
        self.assertEqual(self.writes(), [])
        self.assertEqual((view["auto"]["prices_enabled"], view["books"][0]["prices_auto"]), (False, 3))

    def test_writes_ready_and_locked_rows_from_october(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "prices"}):
            view = self.run_once()
        machine = v7_inbox.AUTO_ACTOR
        # Tháng 10 khóa: mở một lần, ghi chuyến web và dòng sổ gốc (đơn giá rồi phụ phí), khóa lại; tháng 11 mở ghi thẳng.
        self.assertEqual(self.writes(), [
            ("set_month_lock", "2026-10-01", False, 3, machine),
            ("edit_trip_price", 21, None, 4, machine),
            ("edit_legacy_trip", 22, "unit_price_vnd", 5, machine),
            ("edit_legacy_trip", 22, "other_fee_vnd", 6, machine),
            ("set_month_lock", "2026-10-01", True, 7, machine),
            ("edit_trip_price", 11, None, 8, machine)])
        trip_21 = next(c[1] for c in self.calls if c[0] == "edit_trip_price" and c[1]["trip_id"] == 21)
        self.assertEqual((trip_21["unit_price_vnd"], trip_21["other_fee_vnd"]), ("50000000", None))
        auto = view["auto"]
        self.assertEqual((auto["prices_enabled"], auto["today_prices"], auto["today_price_books"], auto["errors"]),
                         (True, 3, 1, 0))
        self.assertEqual({(i["container"], i["locked"], i["month"]) for i in auto["price_items"]},
                         {("CONT21", True, "2026-10"), ("CONT22", True, "2026-10"), ("CONT11", False, "2026-11")})
        self.assertEqual((auto["today_count"], auto["today_trips"]), (0, 0))   # giá đếm riêng, không vào ô chữ hay chuyến
        self.assertEqual(view["books"][0]["prices_auto"], 0)

    def test_same_keys_on_rerun_and_error_relocks_then_stops_book(self):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "prices"}):
            self.run_once()
            self.written, self.inbox.key = False, None
            self.run_once()
        keys = [c[1]["idempotency_key"] for c in self.calls if c[0] in ("edit_trip_price", "edit_legacy_trip")]
        self.assertEqual((len(keys), len(set(keys))), (8, 4))   # cùng bản chụp giá, cùng đích và ô: DB trả lại kết quả cũ
        self.calls, self.fail, self.written, self.inbox.key = [], 21, False, None
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "prices"}):
            view = self.run_once()
        # Lệnh ghi lỗi trong tháng khóa: vẫn khóa lại tháng đã mở, rồi dừng sổ (tháng 11 chờ lượt sau).
        self.assertEqual([(w[0], w[1], w[2]) for w in self.writes()],
                         [("set_month_lock", "2026-10-01", False), ("edit_trip_price", 21, None),
                          ("set_month_lock", "2026-10-01", True)])
        self.assertEqual((view["auto"]["errors"], view["auto"]["today_prices"]), (1, 6))

    def test_prices_follow_machine_trips_in_the_same_pass(self):
        self.inbox.project = lambda runner, ledger, actor: projection(
            sheet_sync={"items": [{"sync_state": "NEW"}], "removed_items": []})
        order = []
        with patch.object(v7_inbox.Inbox, "_auto_trips", lambda inbox, runner, c: order.append("trips")), \
                patch.object(v7_inbox.Inbox, "_auto_prices", lambda inbox, runner, c: order.append("prices")):
            with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "prices"}):
                self.run_once()
            self.assertEqual(order, [])   # chưa có giá máy ghi được, máy không dán chuyến: không chạy
            self.inbox.key = None
            with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "trips,prices"}):
                self.run_once()
        self.assertEqual(order, ["trips", "prices"])


class AutoRoadTests(unittest.TestCase):
    """NGUON-CHUYEN-01 GĐ3: máy đưa chuyến bộ mới vào sổ của tab khách, cùng đường dán với chuyến biển, chỉ khi bật `road`."""

    NOW = 1793595600.0   # 2/11/2026 12:00 giờ VN

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "s.json"
        self.path.write_text("{}", encoding="utf-8")
        self.calls, self.pasted = [], False
        sha = "d" * 64

        def item(line, container, date, state="NEW"):
            return {"source_row": line, "container": container, "event_date": date, "carrier": "99Z-00001", "origin": "—",
                    "destination": "CHIMA", "shipper": None, "booking": "", "src": f"sheet:{sha}:{line}",
                    "note": "Chuyến bộ đồng bộ", "sync_state": state, "sync_reason": "" if state == "NEW" else "OTHER_CUSTOMER"}
        self.items = [item(5, "FAKU1000001", "2026-10-02"), item(6, "FAKU1000003", "2026-11-02"),
                      item(7, "FUTU0000001", "2026-11-03"),                      # sau hôm nay: chờ
                      item(8, "OTHU0000001", "2026-10-05", state="CONFLICT")]   # vướng sổ khác: để người
        self.road = {"snapshot_sha256": sha, "items": self.items}

        def project(runner, ledger, actor):
            road = {"items": [] if self.pasted else [{"sync_state": "NEW"}]}
            return projection(sheet_road=road)
        self.inbox = v7_inbox.Inbox(project, lambda: (str(self.path),), clock=lambda: self.NOW)
        test = self

        class Runner:
            version = 3

            def run(self, function, payload, actor):
                test.calls.append((function, payload, actor))
                if function == "list_customers":
                    return {"customers": [{"id": 1, "status": "active"}]}
                if function == "get_ledger":
                    return {"customer_id": 1, "version": self.version, "today_month": "2026-11-01", "month_locks": []}
                if function in ("set_month_lock", "paste_trips"):
                    self.version += 1
                    test.pasted = test.pasted or function == "paste_trips"
                    if function == "paste_trips":
                        return {"trip_ids": [100 + n for n in range(len(payload["trips"]))], "pending_review": []}
                    return {"version": self.version}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def run_once(self, flags):
        with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": flags}), \
                patch.object(v7_inbox, "road_projection", return_value=self.road), \
                patch.object(v7_inbox, "sheet_projection", side_effect=AssertionError("không có chuyến biển nào")):
            self.inbox.start(self.runner)
            wait_idle(self.inbox)
            return self.inbox.view(self.runner)

    def test_off_unless_road_is_enabled(self):
        view = self.run_once("text,trips")
        self.assertFalse([c for c in self.calls if c[0] == "paste_trips"])
        self.assertEqual((view["books"][0]["trips_new"], view["books"][0]["road_new"]), (1, 1))

    def test_pastes_new_road_trips_by_month_and_relocks_october(self):
        view = self.run_once("road")
        writes = [(c[0], c[1].get("month") or c[1].get("debt_month"), c[1].get("locked"), c[1]["expected_version"], c[2])
                  for c in self.calls if c[0] in ("paste_trips", "set_month_lock")]
        machine = v7_inbox.AUTO_ACTOR
        self.assertEqual(writes, [("set_month_lock", "2026-10-01", False, 3, machine), ("paste_trips", "2026-10-01", None, 4, machine),
                                  ("set_month_lock", "2026-10-01", True, 5, machine), ("paste_trips", "2026-11-01", None, 6, machine)])
        trips = [t for c in self.calls if c[0] == "paste_trips" for t in c[1]["trips"]]
        self.assertEqual([(t["container"], t["src"], t["note"], t["from"], t["unitPriceVnd"]) for t in trips],
                         [("FAKU1000001", "sheet:" + "d" * 64 + ":5", "Chuyến bộ đồng bộ", "—", None),
                          ("FAKU1000003", "sheet:" + "d" * 64 + ":6", "Chuyến bộ đồng bộ", "—", None)])
        auto = view["auto"]
        self.assertEqual((auto["today_trips"], auto["errors"]), (2, 0))
        self.assertTrue(all(entry["road"] for entry in auto["trip_items"]))


class AutoDateFillTests(unittest.TestCase):
    """MAY-KHOA-01 nhóm A: dòng sổ gốc không ngày, cùng tháng nợ, máy điền ngày theo Sheet (tháng khóa thì mở rồi khóa lại)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "s.json"
        self.path.write_text("{}", encoding="utf-8")
        self.calls = []
        fill = {"sync_state": "CONFLICT", "sync_reason": "DIFFERENT_FIELDS", "existing_kind": "legacy",
                "existing_values": {"event_date": None}}
        self.items = [
            dict(fill, changed_fields=["event_date", "shipper_unavailable"], existing_id=5, source_row=12, container="D1",
                 event_date="2026-03-18", existing_debt_month="2026-03-01"),
            dict(fill, changed_fields=["event_date", "origin"], existing_id=6, source_row=13, container="D2", origin="KHO B",
                 event_date="2026-11-02", existing_debt_month="2026-11-01", existing_values={"event_date": None, "origin": "KHO A"}),
            dict(fill, changed_fields=["event_date"], existing_id=7, source_row=14, container="D3",   # khác tháng nợ: người xem
                 event_date="2026-04-01", existing_debt_month="2026-03-01"),
            dict(fill, changed_fields=["event_date"], existing_id=8, source_row=15, container="D4",   # đã có ngày: người xem
                 event_date="2026-03-20", existing_debt_month="2026-03-01", existing_values={"event_date": "2026-03-10"}),
            dict(fill, changed_fields=["event_date"], existing_id=9, source_row=16, container="D5",   # cùng tháng 3 với D1
                 event_date="2026-03-25", existing_debt_month="2026-03-01"),
        ]
        self.inbox = v7_inbox.Inbox(lambda runner, ledger, actor: projection(sheet_sync={"items": [], "removed_items": []}),
                                    lambda: (str(self.path),))
        test = self

        class Runner:
            version = 3

            def run(self, function, payload, actor):
                test.calls.append((function, payload, actor))
                if function == "list_customers":
                    return {"customers": [{"id": 1, "status": "active"}]}
                if function == "get_ledger":
                    return {"customer_id": 1, "version": self.version, "today_month": "2026-11-01", "month_locks": []}
                if function in ("set_month_lock", "edit_legacy_trip", "resolve_sheet_conflict"):
                    self.version += 1
                    return {"version": self.version}
                raise AssertionError(function)
        self.runner = Runner()

    def tearDown(self):
        self.dir.cleanup()

    def test_summary_counts_fill_as_machine_text_work(self):
        book = v7_inbox.summarize(1, projection(sheet_sync={"items": self.items, "removed_items": []}))
        self.assertEqual((book["text_diff"], book["trips_check"]["count"]), (3, 2))

    def test_fills_date_only_for_undated_same_month_rows(self):
        with patch.object(v7_inbox, "sheet_projection", return_value={"snapshot_sha256": "e" * 64, "items": self.items}), \
                patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text"}):
            self.inbox._auto_text(self.runner, 1)
        writes = [(c[0], c[1].get("legacy_row_id") or c[1].get("target_id"), c[1].get("field"), c[1].get("value"),
                   c[1].get("month"), c[1].get("locked"), c[1]["expected_version"])
                  for c in self.calls if c[0] != "get_ledger"]
        self.assertEqual(writes, [
            ("resolve_sheet_conflict", 6, "origin", None, None, None, 3),       # ô chữ trước, không cần mở tháng
            ("set_month_lock", None, None, None, "2026-03-01", False, 4),       # tháng 3 khóa: mở một lần
            ("edit_legacy_trip", 5, "event_date", "2026-03-18", None, None, 5),
            ("edit_legacy_trip", 9, "event_date", "2026-03-25", None, None, 6),
            ("set_month_lock", None, None, None, "2026-03-01", True, 7),        # khóa lại một lần cho cả hai dòng
            ("edit_legacy_trip", 6, "event_date", "2026-11-02", None, None, 8),  # tháng 11 đang mở: sửa thẳng
        ])
        self.assertTrue(all(c[2] == v7_inbox.AUTO_ACTOR for c in self.calls))
        self.assertEqual(self.inbox.auto_errors, 0)
        self.assertEqual([(i["container"], i["field"], i["after"]) for i in self.inbox.auto_log if i["field"] == "event_date"],
                         [("D2", "event_date", "2026-11-02"), ("D5", "event_date", "2026-03-25"),
                          ("D1", "event_date", "2026-03-18")])

    def test_error_in_month_relocks_once_and_keeps_earlier_fills(self):
        test = self
        original = self.runner.run

        def failing(function, payload, actor):
            if function == "edit_legacy_trip" and payload["legacy_row_id"] == 9:
                test.calls.append((function, payload, actor))
                raise ApiError(409, "STALE_LEDGER", "x")
            return original(function, payload, actor)
        self.runner.run = failing
        with patch.object(v7_inbox, "sheet_projection", return_value={"snapshot_sha256": "e" * 64, "items": self.items}), \
                patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text"}):
            self.inbox._auto_text(self.runner, 1)
        locks = [c[1]["locked"] for c in self.calls if c[0] == "set_month_lock"]
        self.assertEqual(locks, [False, True])                     # lỗi giữa tháng: vẫn khóa lại, đúng một lần
        self.assertFalse([c for c in self.calls if c[0] == "edit_legacy_trip" and c[1]["legacy_row_id"] == 6])  # dừng sổ
        self.assertEqual(self.inbox.auto_errors, 1)
        self.assertEqual([i["container"] for i in self.inbox.auto_log if i["field"] == "event_date"], ["D1"])


class MachineAfterRestartTests(unittest.TestCase):
    """Rà máy tự ghi 4/11/2026: tháng máy mở mà chưa khóa thì lượt sau khóa lại; "Máy đã tự làm hôm nay" nạp lại từ Lịch sử."""

    NOW = 1793595600.0   # 2/11/2026 12:00 giờ VN
    MACHINE = v7_inbox.AUTO_ACTOR

    @staticmethod
    def at(minutes_ago):   # dạng `at` của get_ledger (timestamptz, giờ VN)
        from datetime import UTC, datetime, timedelta, timezone
        moment = datetime.fromtimestamp(MachineAfterRestartTests.NOW, UTC) - timedelta(minutes=minutes_ago)
        return moment.astimezone(timezone(timedelta(hours=7))).isoformat()

    def lock_event(self, month, locked, actor, minutes_ago):
        return {"kind": "month_lock", "actor": actor, "at": self.at(minutes_ago),
                "before": {"month": month + "-01", "locked": not locked}, "after": {"month": month + "-01", "locked": locked}}

    def test_left_open_only_when_machine_opened_last_and_long_enough(self):
        ledger = {"today_month": "2026-11-01",
                  "month_locks": [{"month": m + "-01", "locked": locked} for m, locked in
                                  (("2026-08", False), ("2026-09", False), ("2026-10", False), ("2026-07", True),
                                   ("2026-11", False))],
                  "events": [   # mới nhất trước, như get_ledger
                      self.lock_event("2026-11", False, self.MACHINE, 30),   # tháng hiện tại: mở là thường
                      self.lock_event("2026-10", False, self.MACHINE, 3),    # máy đang ghi dở: chưa giành
                      self.lock_event("2026-09", False, "nguoi@vi.du", 40),   # người mở sau máy: giữ
                      self.lock_event("2026-09", False, self.MACHINE, 50),
                      self.lock_event("2026-08", False, self.MACHINE, 45),   # máy mở rồi tắt giữa chừng
                      self.lock_event("2026-07", False, self.MACHINE, 60)]}  # đã khóa lại (cờ khóa)
        self.assertEqual(v7_inbox.machine_left_open(ledger, self.NOW), ["2026-08"])
        self.assertEqual(v7_inbox.machine_left_open(ledger, self.NOW + 600), ["2026-08", "2026-10"])

    def history(self):
        """Lịch sử một sổ: đủ các loại việc máy làm hôm nay, một việc hôm qua và một việc của người."""
        def ev(kind, minutes_ago, before, after, actor=self.MACHINE):
            return {"kind": kind, "actor": actor, "at": self.at(minutes_ago), "before": before, "after": after}
        legacy = {"legacy_row_id": 22, "container": "CONT22", "debt_month": "2026-10-01", "event_date": "2026-10-05"}
        return {"customer_id": 1, "today_month": "2026-11-01", "month_locks": [],
                "trips": [{"id": 21, "container": "CONT21", "month": "2026-10-01", "event_date": "2026-10-03"},
                          {"id": 31, "container": "CONT31", "month": "2026-11-01", "event_date": "2026-11-01"}],
                "legacy_rows": [{"id": 40, "current": {"container": "CONT40"}}],
                "events": list(reversed([
                    ev("paste", 60 * 24, {}, {"trips": [{"trip_id": 30, "container": "HOMQUA", "status": "confirmed"}]}),
                    ev("month_lock", 10, {"month": "2026-10-01", "locked": True}, {"month": "2026-10-01", "locked": False}),
                    ev("price_edit", 10, {"price": {"trip_id": 21, "unit_price_vnd": None, "other_fee_vnd": None}},
                       {"price": {"trip_id": 21, "unit_price_vnd": "50000000", "other_fee_vnd": None}}),
                    ev("legacy_edit", 10, {"legacy": {**legacy, "field": "unit_price_vnd", "unit_price_vnd": None, "other_fee_vnd": None}},
                       {"legacy": {**legacy, "field": "unit_price_vnd", "unit_price_vnd": "45000000", "other_fee_vnd": None}}),
                    ev("legacy_edit", 10, {"legacy": {**legacy, "field": "other_fee_vnd", "unit_price_vnd": "45000000", "other_fee_vnd": None}},
                       {"legacy": {**legacy, "field": "other_fee_vnd", "unit_price_vnd": "45000000", "other_fee_vnd": "300000"}}),
                    ev("month_lock", 10, {"month": "2026-10-01", "locked": False}, {"month": "2026-10-01", "locked": True}),
                    ev("legacy_edit", 8, {"legacy": {**legacy, "legacy_row_id": 23, "container": "D1", "field": "event_date", "value": None}},
                       {"legacy": {**legacy, "legacy_row_id": 23, "container": "D1", "field": "event_date", "value": "2026-10-07"}}),
                    ev("sheet_conflict_resolved", 6, {"field": "origin", "value": "KHO A"},
                       {"field": "origin", "decision": "use_sheet", "sheet_value": " KHO B ", "target": {"kind": "legacy", "id": 40}}),
                    ev("paste", 5, {}, {"trips": [{"trip_id": 31, "container": "CONT31", "event_date": "2026-11-01", "status": "confirmed"},
                                                  {"trip_id": 32, "container": "CONT32", "event_date": "2026-11-02",
                                                   "status": "pending_review", "note": "Chuyến bộ đồng bộ"}]}),
                    ev("price_edit", 4, {"price": {"trip_id": 31}}, {"price": {"trip_id": 31, "unit_price_vnd": "1"}},
                       actor="nguoi@vi.du")]))}

    def test_entries_rebuilt_from_history_in_auto_log_shape(self):
        entries = v7_inbox.machine_entries(1, self.history(), "2026-11-02")
        brief = [(e.get("kind"), e["container"]) for e in entries]
        self.assertEqual(brief, [("trip", "CONT31"), ("trip", "CONT32"), (None, "CONT40"), (None, "D1"),
                                 ("price", "CONT21"), ("price", "CONT22")])
        text, date, trip, road = entries[2], entries[3], entries[0], entries[1]
        self.assertEqual((text["field"], text["before"], text["after"]), ("origin", "KHO A", "KHO B"))
        self.assertEqual((date["field"], date["before"], date["after"]), ("event_date", None, "2026-10-07"))
        self.assertEqual((trip["trip_id"], trip["pending"], "road" in trip), (31, False, False))
        self.assertEqual((road["pending"], road["road"]), (True, True))
        legacy_price = entries[5]   # hai ô giá của cùng dòng sổ gốc gộp một dòng, tháng 10 máy vừa mở nên "tháng khóa"
        self.assertEqual({k: legacy_price[k] for k in ("unit_price_vnd", "other_fee_vnd", "before_unit_price_vnd",
                                                        "before_other_fee_vnd", "month", "date", "locked")},
                         {"unit_price_vnd": "45000000", "other_fee_vnd": "300000", "before_unit_price_vnd": None,
                          "before_other_fee_vnd": None, "month": "2026-10", "date": "2026-10-05", "locked": True})
        self.assertEqual((entries[4]["unit_price_vnd"], entries[4]["month"], entries[4]["locked"]), ("50000000", "2026-10", True))

    def runner(self, ledger, calls):
        class Runner:
            def run(self, function, payload, actor):
                calls.append((function, payload, actor))
                if function == "list_customers":
                    return {"customers": [{"id": 1, "status": "active"}]}
                if function == "get_ledger":
                    return {**ledger, "version": 9}
                if function == "set_month_lock":
                    return {"version": 10}
                raise AssertionError(function)
        return Runner()

    def test_first_pass_after_restart_reloads_today_and_relocks_month_left_open(self):
        ledger = self.history()
        ledger["month_locks"] = [{"month": "2026-09-01", "locked": False}]
        ledger["events"] = [self.lock_event("2026-09", False, self.MACHINE, 30)] + ledger["events"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "s.json"
            path.write_text("{}", encoding="utf-8")
            inbox = v7_inbox.Inbox(lambda runner, ledger, actor: projection(), lambda: (str(path),), clock=lambda: self.NOW)
            calls = []
            with patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": ""}), patch("sys.stderr"):
                inbox.start(self.runner(ledger, calls))
                wait_idle(inbox)
                auto = inbox.view(self.runner(ledger, calls))["auto"]
                self.assertEqual((auto["today_trips"], auto["today_trips_pending"], auto["today_count"], auto["today_prices"]),
                                 (2, 1, 2, 2))
                locks = [(c[1]["month"], c[1]["locked"], c[1]["expected_version"], c[2]) for c in calls if c[0] == "set_month_lock"]
                self.assertEqual(locks, [("2026-09-01", True, 9, self.MACHINE)])
                inbox.key = None   # lượt sau cùng ngày: không nạp trùng
                inbox.start(self.runner(ledger, calls))
                wait_idle(inbox)
                self.assertEqual(inbox.view(self.runner(ledger, calls))["auto"]["today_trips"], 2)

    def test_error_counts_and_writes_one_journal_line(self):
        inbox = v7_inbox.Inbox(lambda runner, ledger, actor: projection(), lambda: ())
        with patch("sys.stderr") as stderr:
            inbox._error("ghi giá", 7, ApiError(409, "STALE_LEDGER", "x"))
            inbox._error("dán chuyến mới", 8, "INCOMPLETE")
        self.assertEqual(inbox.auto_errors, 2)
        lines = "".join(call.args[0] for call in stderr.write.call_args_list if call.args[0].strip())
        self.assertIn("ghi giá sổ 7 lỗi STALE_LEDGER", lines)
        self.assertIn("dán chuyến mới sổ 8 lỗi INCOMPLETE", lines)


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
