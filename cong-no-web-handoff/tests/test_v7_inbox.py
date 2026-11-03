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
        # Trường của P2 (phiếu chi tiết, phiên bản, nợ) có test riêng; ở đây so bảy nhóm.
        book = {key: value for key, value in book.items() if key not in ("version", "outstanding_vnd")}
        book["receipts"] = {key: book["receipts"][key] for key in ("ready", "review", "amount_vnd")}
        self.assertEqual(book, {
            "customer_id": 7,
            "receipts": {"ready": 1, "review": 2, "amount_vnd": "150"},   # phiếu không có số tiền không cộng như 0
            "removed": {"count": 2, "amount_vnd": "300"},
            "trips_new": 2,
            "trips_check": {"count": 3, "reasons": {"FIELDS": 1, "OTHER_BOOK_LEGACY": 2}},
            "text_diff": 1,
            "prices": {"ready": 0, "review": 1},
            "ps": {"ready": 1, "review": 2}})

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
        self.assertEqual((book["text_diff"], book["trips_check"]["count"]), (2, 2))

    def test_fills_date_only_for_undated_same_month_rows(self):
        with patch.object(v7_inbox, "sheet_projection", return_value={"snapshot_sha256": "e" * 64, "items": self.items}), \
                patch.dict(os.environ, {"WEBDEBIT_AUTO_SHEET": "text"}):
            self.inbox._auto_text(self.runner, 1)
        writes = [(c[0], c[1].get("legacy_row_id") or c[1].get("target_id"), c[1].get("field"), c[1].get("value"),
                   c[1].get("month"), c[1].get("locked"), c[1]["expected_version"])
                  for c in self.calls if c[0] != "get_ledger"]
        self.assertEqual(writes, [
            ("set_month_lock", None, None, None, "2026-03-01", False, 3),       # tháng 3 khóa
            ("edit_legacy_trip", 5, "event_date", "2026-03-18", None, None, 4),
            ("set_month_lock", None, None, None, "2026-03-01", True, 5),
            ("resolve_sheet_conflict", 6, "origin", None, None, None, 6),       # ô chữ như trước
            ("edit_legacy_trip", 6, "event_date", "2026-11-02", None, None, 7),  # tháng 11 đang mở: sửa thẳng
        ])
        self.assertTrue(all(c[2] == v7_inbox.AUTO_ACTOR for c in self.calls))
        self.assertEqual(self.inbox.auto_errors, 0)
        self.assertEqual([(i["container"], i["field"], i["after"]) for i in self.inbox.auto_log if i["field"] == "event_date"],
                         [("D2", "event_date", "2026-11-02"), ("D1", "event_date", "2026-03-18")])


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
