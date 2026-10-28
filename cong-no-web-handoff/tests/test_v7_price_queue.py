"""Price queue: Sheet prices for one ledger, batch write through existing commands. Fake data only."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_ledger_api as api  # noqa: E402
import v7_price_snapshot as snapshot_tool  # noqa: E402
from test_v7_load_real_copy import fixture  # noqa: E402
from v7_price_queue import classify, load_price_snapshot, project_prices, targets  # noqa: E402


def row(tab="KHACH A", source_row=5, container="FAKEU0000001", date="2026-10-03", price=50000000, fee=None, total=None):
    return {"customer_tab": tab, "source_row": source_row, "debt_month": "2026-10", "container": container,
            "date": date, "sheet_unit_price_vnd": price, "sheet_other_fee_vnd": fee, "sheet_total_vnd": total}


def ledger(customer_id=7, trips=(), legacy=(), version=3):
    return {"customer_id": customer_id, "version": version, "status": "active", "today_month": "2026-10-01",
            "month_locks": [{"month": "2026-10-01", "locked": False}, {"month": "2026-09-01", "locked": True}],
            "trips": list(trips), "legacy_rows": list(legacy)}


def trip(trip_id=11, container="FAKEU0000001", date="2026-10-03", price=None, month="2026-10-01"):
    return {"id": trip_id, "container": container, "event_date": date, "unit_price_vnd": price,
            "other_fee_vnd": None, "status": "confirmed", "month": month, "deleted": False}


def legacy_row(row_id=21, container="FAKEU0000002", date="2026-10-04"):
    return {"id": row_id, "kind": "trip", "month": "2026-10-01", "current": {
        "container": container, "event_date": date, "unit_price_vnd": None, "other_fee_vnd": None,
        "counted_vnd": "0", "month": "2026-10-01", "deleted": False}}


SNAPSHOT = {"sha256": "a" * 64, "row_count": 0, "rows": []}
CUSTOMERS = [{"id": 7, "name": "KHACH A"}, {"id": 8, "name": "KHACH B", "aliases": ["KHACH B CU"]}]


class ProjectionTest(unittest.TestCase):
    def test_only_this_customer_and_ready_vs_review(self):
        rows = [row(), row(source_row=6, container="FAKEU0000002", date="2026-10-04", fee=300000),
                row(source_row=7, container="FAKEU0000003", date="2026-09-20"),
                row(source_row=8, container="FAKEU0000004", fee=-500000),
                row(tab="KHACH B", source_row=9)]
        book = ledger(trips=[trip(), trip(13, "FAKEU0000003", "2026-09-20", month="2026-09-01"),
                             trip(14, "FAKEU0000004")], legacy=[legacy_row()])
        result = project_prices(SNAPSHOT | {"rows": rows, "row_count": 5}, book, CUSTOMERS)
        self.assertEqual([(r["target_kind"], r["target_id"]) for r in result["ready"]], [("trip", 11), ("legacy", 21), ("trip", 14)])
        self.assertEqual([r["status"] for r in result["review"]], ["MONTH_LOCKED"])
        self.assertEqual((result["ready_count"], result["review_count"]), (3, 1))

    def test_typed_fee_is_manual_even_when_price_missing(self):
        book = ledger(trips=[trip() | {"has_typed_fee": True}])
        result = project_prices(SNAPSHOT | {"rows": [row()], "row_count": 1}, book, CUSTOMERS)
        self.assertEqual(result["review"][0]["status"], "MANUAL")

    def test_typed_fee_matching_total_is_unchanged(self):
        current = trip(price="50000000") | {"other_fee_vnd": "300000", "has_typed_fee": True}
        result = project_prices(SNAPSHOT | {"rows": [row(fee=300000, total=50300000)], "row_count": 1},
                                ledger(trips=[current]), CUSTOMERS)
        self.assertEqual((result["ready_count"], result["review_count"]), (0, 0))
        self.assertEqual(classify(row(fee=300000, total=50300000), targets(ledger(trips=[current])))["status"],
                         "PRICE_UNCHANGED")

    def test_negative_fee_update_requeues_only_same_price(self):
        first = trip(price="50000000") | {"other_fee_vnd": "-300000"}
        rows = [row(fee=-500000)]
        result = project_prices(SNAPSHOT | {"rows": rows, "row_count": 1}, ledger(trips=[first]), CUSTOMERS)
        self.assertEqual(result["ready"][0]["sheet_other_fee_vnd"], "-500000")
        typed = ledger(trips=[first | {"has_typed_fee": True}])
        self.assertEqual(project_prices(SNAPSHOT | {"rows": rows, "row_count": 1}, typed, CUSTOMERS)["review"][0]["status"], "MANUAL")
        different_price = ledger(trips=[first | {"unit_price_vnd": "49000000"}])
        self.assertEqual(project_prices(SNAPSHOT | {"rows": rows, "row_count": 1}, different_price, CUSTOMERS)["review"][0]["status"], "CONFLICT")

    def test_alias_tab_belongs_to_its_book_only(self):
        rows = [row(tab="KHACH B CU")]
        self.assertEqual(project_prices(SNAPSHOT | {"rows": rows, "row_count": 1}, ledger(8, [trip()]), CUSTOMERS)["ready_count"], 1)
        self.assertEqual(project_prices(SNAPSHOT | {"rows": rows, "row_count": 1}, ledger(7, [trip()]), CUSTOMERS)["ready_count"], 0)

    def test_snapshot_loader_rejects_bad_files(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "prices.json"
            for content in ('{"rows":[],"row_count":0}', '{"rows":[{}],"row_count":0,"sha256":"' + "a" * 64 + '"}', "not json"):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(ValueError):
                    load_price_snapshot(path)

    def test_snapshot_tool_hash_follows_rows_not_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root)
            xlsx = root / "source-google-export.xlsx"
            first = snapshot_tool.build(xlsx)
            second = snapshot_tool.build(xlsx)
            self.assertEqual(first["sha256"], second["sha256"])
            self.assertEqual(first["row_count"], 1)
            output = root / "out" / "prices.json"
            snapshot_tool.write(first, output)
            self.assertEqual(load_price_snapshot(output)["sha256"], first["sha256"])


class Runner:
    def __init__(self, fail_at=None):
        self.calls, self.version, self.fail_at, self.writes = [], 3, fail_at, 0

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "get_ledger":
            return {"customer_id": 7, "version": self.version, "status": "active"}
        self.writes += 1
        if self.writes == self.fail_at:
            raise api.ApiError(409, "MONTH_LOCKED", "Tháng đang khóa.")
        self.version += 1
        return {"version": self.version}


READY = {"snapshot_sha256": "a" * 64, "ready": [
    {"target_kind": "trip", "target_id": 11, "sheet_unit_price_vnd": 50000000, "sheet_other_fee_vnd": None},
    {"target_kind": "legacy", "target_id": 21, "sheet_unit_price_vnd": 12000000, "sheet_other_fee_vnd": 300000}]}
BODY = {"customer_id": 7, "expected_version": 3, "snapshot_sha256": "a" * 64, "idempotency_key": "fake-batch"}


class ApproveTest(unittest.TestCase):
    def approve(self, runner, body=BODY, projection=READY):
        with patch.object(api, "price_projection", return_value=projection):
            return api.approve_prices(json.dumps(body).encode(), runner, "fake-actor")

    def test_writes_ready_rows_through_existing_commands(self):
        runner = Runner()
        status, result = self.approve(runner)
        self.assertEqual((status, result["written"], result["complete"], result["version"]), (200, 2, True, 6))
        writes = [(f, {k: v for k, v in p.items() if k != "idempotency_key"}) for f, p, _ in runner.calls if f != "get_ledger"]
        self.assertEqual(writes, [
            ("edit_trip_price", {"customer_id": 7, "expected_version": 3, "trip_id": 11, "unit_price_vnd": "50000000", "other_fee_vnd": None}),
            ("edit_legacy_trip", {"customer_id": 7, "expected_version": 4, "legacy_row_id": 21, "field": "unit_price_vnd", "value": "12000000"}),
            ("edit_legacy_trip", {"customer_id": 7, "expected_version": 5, "legacy_row_id": 21, "field": "other_fee_vnd", "value": "300000"})])
        self.assertTrue(all(c[2] == "fake-actor" for c in runner.calls))

    def test_repeat_click_uses_the_same_command_keys(self):
        first, second = Runner(), Runner()
        self.approve(first)
        self.approve(second)
        keys = [[p["idempotency_key"] for f, p, _ in r.calls if f != "get_ledger"] for r in (first, second)]
        self.assertEqual(keys[0], keys[1])
        self.assertEqual(len(set(keys[0])), 3)
        self.assertEqual(keys[0][0], hashlib.sha256(f"fake-batch:{'a' * 64}:trip:11:price".encode()).hexdigest())

    def test_two_negative_totals_replace_discount(self):
        runner = Runner()
        first = READY | {"ready": [READY["ready"][0] | {"sheet_other_fee_vnd": "-300000"}]}
        self.assertEqual(self.approve(runner, projection=first)[1]["written"], 1)
        second_row = row(fee=-500000)
        current = trip(price="50000000") | {"other_fee_vnd": "-300000"}
        second = project_prices(SNAPSHOT | {"sha256": "b" * 64, "rows": [second_row], "row_count": 1},
                                ledger(trips=[current]), CUSTOMERS)
        self.assertEqual(second["ready_count"], 1)
        body = BODY | {"expected_version": 4, "snapshot_sha256": "b" * 64}
        self.assertEqual(self.approve(runner, body=body, projection=second)[1]["written"], 1)
        writes = [payload for function, payload, _ in runner.calls if function == "edit_trip_price"]
        self.assertEqual([payload["other_fee_vnd"] for payload in writes], ["-300000", "-500000"])

    def test_legacy_fee_update_skips_unchanged_unit_price(self):
        runner = Runner()
        ready = READY | {"ready": [{"target_kind": "legacy", "target_id": 21,
                                     "sheet_unit_price_vnd": "12000000", "sheet_other_fee_vnd": "-500000",
                                     "web_unit_price_vnd": "12000000"}]}
        self.assertEqual(self.approve(runner, projection=ready)[1]["written"], 1)
        self.assertEqual([function for function, _, _ in runner.calls if function != "get_ledger"], ["edit_legacy_trip"])
        self.assertEqual(runner.calls[-1][1]["field"], "other_fee_vnd")

    def test_runtime_typed_fee_becomes_manual(self):
        class TypedRunner(Runner):
            def run(self, function, payload, actor):
                if function == "edit_trip_price":
                    raise api.ApiError(409, "FEE_LINES_TYPED", "Đã phân loại")
                return super().run(function, payload, actor)
        status, result = self.approve(TypedRunner(), projection=READY | {"ready": [READY["ready"][0]]})
        self.assertEqual((status, result["error"], result["review"][0]["status"]), (200, "FEE_LINES_TYPED", "MANUAL"))

    def test_stale_sheet_version_or_bad_body_writes_nothing(self):
        for body, projection in ((BODY | {"snapshot_sha256": "b" * 64}, READY), (BODY | {"expected_version": 2}, READY),
                                 (BODY | {"extra": 1}, READY)):
            runner = Runner()
            with self.subTest(body=body), self.assertRaises(api.ApiError):
                self.approve(runner, body, projection)
            self.assertEqual([c for c in runner.calls if c[0] != "get_ledger"], [])

    def test_failure_after_a_write_reports_partial_batch(self):
        runner = Runner(fail_at=2)   # trip written, legacy price refused
        status, result = self.approve(runner)
        self.assertEqual((status, result["written"], result["complete"], result["error"]), (200, 1, False, "MONTH_LOCKED"))
        with self.assertRaises(api.ApiError):   # failure on the very first write is a plain error
            self.approve(Runner(fail_at=1))

    def test_ledger_read_falls_back_when_price_snapshot_is_missing(self):
        with patch.object(api, "PRICE_SNAPSHOT_PATH", str(ROOT / "missing-prices.json")), \
                patch.object(api, "sheet_projection", return_value={"items": []}):
            status, result = api.handle("GET", "/api/v7/ledger?customer=7", {"host": "127.0.0.1:8780"}, b"",
                                        Runner(), port=8780, host="127.0.0.1", actor="fake-actor")
        self.assertEqual(status, 200)
        self.assertEqual(result["sheet_prices"]["unavailable"], True)
        self.assertEqual(result["sheet_prices"]["ready"], [])


if __name__ == "__main__":
    unittest.main()
