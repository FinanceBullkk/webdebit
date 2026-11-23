"""Audit 23/11/2026 (O1, O3, O7): mọi đường ghi giá/phiếu theo Sheet nghe kết luận tab hỏng và từ chối bản chụp cũ. Dữ liệu giả, không DB.

Ca thật đằng sau (16/11/2026): người nhập chèn một ô ở cột giá, tab thành `row_shift`; máy đối soát đã dừng khách đó, nhưng máy giá
15 phút và các nút "Ghi N giá/phiếu từ Sheet" vẫn ghi giá lệch dòng. Phép thử của audit (`probe_machine.py`, `probe_stale.py`) thành test.
"""

import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
import v7_api_sheet  # noqa: E402
import v7_inbox  # noqa: E402
import v7_sheet_fix  # noqa: E402
from v7_api_validate import ApiError  # noqa: E402
from v7_price_queue import SNAPSHOT_MAX_AGE_SECONDS, project_prices, snapshot_stale  # noqa: E402
from v7_receipt_queue import project_receipts  # noqa: E402

TAB = "KHACH MAU"
CUSTOMERS = [{"id": 1, "name": TAB, "status": "active"}]
SHIFT = {"kind": "row_shift", "level": "error", "month": "2026-11", "rows": [7, 8], "cells": ["B7", "F8"]}
ACTOR = "nguoi@example.test"


def now_iso(hours_ago=0):
    return (dt.datetime.now(dt.UTC) - dt.timedelta(hours=hours_ago)).isoformat()


def price_row(source_row, container, day, price):
    return {"customer_tab": TAB, "source_row": source_row, "debt_month": day[:7] + "-01", "container": container, "date": day,
            "sheet_unit_price_vnd": price, "sheet_other_fee_vnd": None, "sheet_total_vnd": price}


# Chuyến 11, 12: tháng mở, chưa giá (READY). Chuyến 13: tháng 10 đang khóa, chưa giá (MONTH_LOCKED, máy mở-ghi-khóa).
# Chuyến 14: tháng mở, web đã có giá khác Sheet (CONFLICT ghi theo lô được).
PRICE_ROWS = [price_row(3, "MAUU1000101", "2026-11-05", 5000000), price_row(4, "MAUU1000102", "2026-11-06", 6000000),
              price_row(5, "MAUU1000103", "2026-10-07", 7000000), price_row(6, "MAUU1000104", "2026-11-08", 8000000)]
RECEIPT_ROWS = [{"customer_tab": TAB, "source_row": 30, "debt_month": "2026-11", "amount_vnd": 9000000, "note": "05/11/2026 ck"}]


def snapshot(rows, status="ok", created_at=None):
    snap = {"rows": rows, "row_count": len(rows), "sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
            "tabs": {TAB: {"status": status, "findings": [SHIFT] if status == "broken" else []}}}
    if created_at is not None:
        snap["runner"] = {"created_at": created_at}
    return snap


def trip(trip_id, container, day, price=None):
    return {"id": trip_id, "container": container, "event_date": day, "unit_price_vnd": price, "other_fee_vnd": None,
            "month": day[:7] + "-01", "status": "confirmed"}


def ledger(version=7):
    return {"customer_id": 1, "version": version, "status": "active", "today_month": "2026-11-01", "month_locks": [],
            "total_outstanding_vnd": "0", "legacy_rows": [], "events": [], "receipts": [], "adjustments": [],
            "trips": [trip(11, "MAUU1000101", "2026-11-05"), trip(12, "MAUU1000102", "2026-11-06"),
                      trip(13, "MAUU1000103", "2026-10-07"), trip(14, "MAUU1000104", "2026-11-08", "4000000")]}


class Runner:
    """Sổ giả: mỗi lệnh ghi tăng phiên bản; `fail_on`: lệnh giá thứ mấy lỗi STALE_LEDGER."""

    def __init__(self, fail_on=None):
        self.calls, self.version, self.fail_on = [], 7, fail_on

    def run(self, function, payload, actor, **_):
        if function == "get_ledger":
            return ledger(self.version)
        if function == "list_customers":
            return {"customers": CUSTOMERS}
        if function == "get_fee_types":
            return {"fee_types": []}
        prices = sum(1 for name, *_ in self.calls if name == "edit_trip_price")
        if self.fail_on and function == "edit_trip_price" and prices + 1 == self.fail_on:
            raise ApiError(409, "STALE_LEDGER", "Sổ vừa đổi.")
        self.calls.append((function, actor, payload.get("trip_id")))
        self.version += 1
        return {"version": self.version}

    def writes(self):
        return [name for name, *_ in self.calls]


class Files(unittest.TestCase):
    """Bản chụp giá và phiếu trong thư mục tạm, đường của `v7_api_sheet` trỏ vào đó."""

    status = "ok"
    created_at = None

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.prices = snapshot(PRICE_ROWS, self.status, self.created_at)
        self.receipts = snapshot(RECEIPT_ROWS, self.status, self.created_at)
        for name, data, attribute in (("prices.json", self.prices, "PRICE_SNAPSHOT_PATH"),
                                      ("receipts.json", self.receipts, "RECEIPT_SNAPSHOT_PATH")):
            path = os.path.join(folder.name, name)
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(data, stream)
            old = getattr(v7_api_sheet, attribute)
            setattr(v7_api_sheet, attribute, path)
            self.addCleanup(setattr, v7_api_sheet, attribute, old)
        self.inbox = v7_inbox.Inbox(lambda *_a: {}, lambda: ())

    def body(self, digest, **extra):
        return json.dumps({"customer_id": 1, "expected_version": 7, "snapshot_sha256": digest, "idempotency_key": "k", **extra}).encode()

    def conflict_body(self):
        return self.body(self.prices["sha256"], conflicts=[{"target_kind": "trip", "target_id": 14, "source_row": 6}])

    def sheet_price_body(self):
        fingerprint = next(row["source_fingerprint"] for row in project_prices(snapshot(PRICE_ROWS), ledger(), CUSTOMERS)["review"]
                           if row["target_id"] == 14)
        return json.dumps({"customer_id": 1, "expected_version": 7, "idempotency_key": "k", "task_kind": "price",
                           "target_kind": "trip", "target_id": 14, "source_fingerprint": fingerprint}).encode()

    def refused(self, call, code):
        runner = Runner()
        with self.assertRaises(ApiError) as caught:
            call(runner)
        self.assertEqual((caught.exception.status, caught.exception.code), (409, code))
        self.assertEqual(runner.writes(), [])


class HealthyControl(Files):
    """Đối chứng: tab lành, bản chụp mới thì mọi đường trên vẫn ghi như trước."""

    def test_projection_has_ready_locked_and_batchable_conflict(self):
        projected = project_prices(self.prices, ledger(), CUSTOMERS)
        self.assertEqual([row["target_id"] for row in projected["ready"]], [11, 12])
        self.assertEqual({row["target_id"]: (row["status"], row["batchable"]) for row in projected["review"]},
                         {13: ("MONTH_LOCKED", False), 14: ("CONFLICT", True)})
        self.assertEqual(projected["tab_health"]["status"], "ok")

    def test_machine_writes_ready_and_locked_rows(self):
        runner = Runner()
        self.inbox._auto_prices(runner, 1)
        self.assertEqual([(name, trip_id) for name, _, trip_id in runner.calls],
                         [("set_month_lock", None), ("edit_trip_price", 13), ("set_month_lock", None),
                          ("edit_trip_price", 11), ("edit_trip_price", 12)])

    def test_buttons_write(self):
        self.assertEqual(v7_api_sheet.approve_prices(self.body(self.prices["sha256"]), Runner(), ACTOR)[1]["written"], 2)
        self.assertEqual(v7_api_sheet.approve_price_conflicts(self.conflict_body(), Runner(), ACTOR)[1]["written"], 1)
        self.assertEqual(v7_api_sheet.approve_receipts(self.body(self.receipts["sha256"]), Runner(), ACTOR)[1]["written"], 1)


class BrokenTab(Files):
    """O1: tab của sổ `broken` (row_shift) trong chính bản chụp giá/phiếu."""

    status = "broken"

    def test_health_is_broken_and_reconcile_plan_is_empty(self):
        self.assertEqual(v7_sheet_fix.customer_health(self.prices, ledger(), CUSTOMERS)["status"], "broken")
        self.assertEqual(v7_sheet_fix.plan(self.prices, self.receipts, ledger(), CUSTOMERS, dt.date(2026, 11, 23))[0], [])

    def test_price_projection_has_no_ready_and_nothing_batchable(self):
        projected = project_prices(self.prices, ledger(), CUSTOMERS)
        self.assertEqual((projected["ready"], projected["ready_count"]), ([], 0))
        self.assertFalse(any(row["batchable"] for row in projected["review"]))
        self.assertEqual(projected["tab_health"]["findings"][0]["kind"], "row_shift")

    def test_receipt_projection_has_no_ready(self):
        projected = project_receipts(self.receipts, ledger(), CUSTOMERS, dt.date(2026, 11, 23))
        self.assertEqual((projected["ready"], projected["tab_health"]["status"]), ([], "broken"))

    def test_machine_writes_nothing_not_even_locked_months(self):
        runner = Runner()
        self.inbox._auto_prices(runner, 1)
        self.assertEqual(runner.writes(), [])   # cả `set_month_lock` của tháng khóa
        self.assertEqual(v7_inbox.auto_prices(project_prices(self.prices, ledger(), CUSTOMERS)), [])

    def test_approve_prices_is_409_tab_broken(self):
        self.refused(lambda runner: v7_api_sheet.approve_prices(self.body(self.prices["sha256"]), runner, ACTOR), "TAB_BROKEN")

    def test_approve_price_conflicts_is_409_tab_broken(self):
        self.refused(lambda runner: v7_api_sheet.approve_price_conflicts(self.conflict_body(), runner, ACTOR), "TAB_BROKEN")

    def test_apply_sheet_price_is_409_tab_broken(self):
        self.refused(lambda runner: v7_api_sheet.apply_sheet_price(self.sheet_price_body(), runner, ACTOR), "TAB_BROKEN")

    def test_approve_receipts_is_409_tab_broken(self):
        self.refused(lambda runner: v7_api_sheet.approve_receipts(self.body(self.receipts["sha256"]), runner, ACTOR), "TAB_BROKEN")


class StaleSnapshot(Files):
    """O7: runner đọc Sheet dừng ba ngày, API khởi động lại: không ghi theo bản chụp cũ."""

    created_at = now_iso(hours_ago=72)

    def test_machine_writes_nothing(self):
        runner = Runner()
        self.inbox._auto_prices(runner, 1)
        self.assertEqual(runner.writes(), [])

    def test_buttons_are_409_sheet_stale(self):
        self.refused(lambda runner: v7_api_sheet.approve_prices(self.body(self.prices["sha256"]), runner, ACTOR), "SHEET_STALE")
        self.refused(lambda runner: v7_api_sheet.approve_price_conflicts(self.conflict_body(), runner, ACTOR), "SHEET_STALE")
        self.refused(lambda runner: v7_api_sheet.apply_sheet_price(self.sheet_price_body(), runner, ACTOR), "SHEET_STALE")
        self.refused(lambda runner: v7_api_sheet.approve_receipts(self.body(self.receipts["sha256"]), runner, ACTOR), "SHEET_STALE")


class FreshSnapshot(Files):
    created_at = now_iso(hours_ago=0.25)

    def test_snapshot_from_the_last_run_still_writes(self):
        self.assertEqual(v7_api_sheet.approve_prices(self.body(self.prices["sha256"]), Runner(), ACTOR)[1]["written"], 2)


class StaleRuleTest(unittest.TestCase):
    def test_age_threshold(self):
        now = dt.datetime(2026, 11, 23, 8, 0, tzinfo=dt.UTC)
        self.assertEqual(SNAPSHOT_MAX_AGE_SECONDS, 3600)   # cùng ngưỡng máy canh (`tools/v7_watchdog.py`)
        self.assertFalse(snapshot_stale("2026-11-23T07:01:00+00:00", now))
        self.assertTrue(snapshot_stale("2026-11-23T06:59:00+00:00", now))
        self.assertFalse(snapshot_stale("2026-11-23T14:30:00+07:00", now))   # giờ VN, 30 phút trước
        self.assertTrue(snapshot_stale("không phải giờ", now))
        self.assertTrue(snapshot_stale("2026-11-23T07:30:00", now))   # không múi giờ: không biết tuổi, coi như cũ
        self.assertFalse(snapshot_stale(None, now))   # bản chụp không có `runner` (bản dựng trong test): không xét


class ApplyFixUndoKeys(unittest.TestCase):
    """O3: lệnh giá thứ hai lỗi sau khi lệnh đầu đã lưu: khóa hoàn tác của lệnh đầu vẫn về tay nơi gọi."""

    def test_keys_of_saved_commands_survive_the_stop(self):
        healthy = snapshot(PRICE_ROWS[:2])
        groups = v7_sheet_fix.price_groups(project_prices(healthy, ledger(), CUSTOMERS), [])
        runner, keys, written = Runner(fail_on=2), [], {}
        with self.assertRaises(ApiError) as caught:
            v7_sheet_fix.apply_fix(runner, 1, ledger(), groups, healthy["sha256"], dt.date(2026, 11, 23), actor=ACTOR,
                                   undo_keys=keys, health={"status": "ok", "findings": []}, written=written)
        self.assertEqual(caught.exception.code, "STALE_LEDGER")
        self.assertEqual(runner.writes(), ["edit_trip_price"])
        self.assertEqual(len(keys), 1)
        self.assertEqual(written["prices"], 1)


if __name__ == "__main__":
    unittest.main()
