"""Mức nền của GET /api/v7/ledger: các chỗ đã đo trên `hao` 4/11/2026 không được chậm lại, kết quả không đổi."""
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_api_sheet as sheet  # noqa: E402
import v7_price_queue  # noqa: E402
import v7_road_queue  # noqa: E402
import v7_sheet_queue  # noqa: E402
import v7_sheet_task_keep  # noqa: E402


class SharedReadsTests(unittest.TestCase):
    def test_different_shared_reads_run_at_the_same_time(self):
        # Cả ba cùng phải vào được hàm đọc thì barrier mới mở; khóa chung sẽ làm barrier hết giờ.
        barrier = threading.Barrier(3, timeout=5)

        class Runner:
            def run(self, function, payload, actor):
                barrier.wait()
                return {"function": function}

        shared = sheet.SharedReads(Runner())
        results, errors = {}, []

        def read(function):
            try:
                results[function] = shared.run(function, {}, "fake")
            except threading.BrokenBarrierError as exc:
                errors.append(exc)

        threads = [threading.Thread(target=read, args=(name,)) for name in sheet.SharedReads.SHARED]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(results, {name: {"function": name} for name in sheet.SharedReads.SHARED})

    def test_same_shared_read_still_runs_once(self):
        calls = []
        started, release = threading.Event(), threading.Event()

        class Runner:
            def run(self, function, payload, actor):
                calls.append(function)
                started.set()
                release.wait(5)
                return {"n": len(calls)}

        shared = sheet.SharedReads(Runner())
        results = []
        threads = [threading.Thread(target=lambda: results.append(shared.run("list_customers", {}, "fake"))) for _ in range(4)]
        for thread in threads:
            thread.start()
        started.wait(5)
        release.set()
        for thread in threads:
            thread.join()
        self.assertEqual(calls, ["list_customers"])
        self.assertEqual(results, [{"n": 1}] * 4)

    def test_failed_shared_read_is_not_remembered(self):
        outcomes = [RuntimeError("hỏng"), {"ok": True}]

        class Runner:
            def run(self, function, payload, actor):
                outcome = outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        shared = sheet.SharedReads(Runner())
        with self.assertRaises(RuntimeError):
            shared.run("get_fee_types", {}, "fake")
        self.assertEqual(shared.run("get_fee_types", {}, "fake"), {"ok": True})

    def test_other_reads_are_not_shared(self):
        calls = []

        class Runner:
            def run(self, function, payload, actor):
                calls.append(function)
                return {}

        shared = sheet.SharedReads(Runner())
        shared.run("get_ledger", {"customer_id": 1}, "fake")
        shared.run("get_ledger", {"customer_id": 1}, "fake")
        self.assertEqual(calls, ["get_ledger", "get_ledger"])


def queue_row(container="C1", customer_id=9, date="2026-10-01"):
    return {"container": container, "customer_id": customer_id, "status": "READY", "event_date": date, "booking": "",
            "carrier": "X", "origin": "A", "destination": "B", "customer_name": "K"}


def sheet_trip(trip_id=5, container="GONE", date="2026-10-02"):
    return {"id": trip_id, "container": container, "event_date": date, "note": "Chuyến đồng bộ", "status": "approved",
            "month": "2026-10-01", "amount_vnd": "1", "info_editable": True}


class RemovedTripsTests(unittest.TestCase):
    def test_no_assignment_event_means_no_hash_over_the_whole_queue(self):
        queue = {"items": [queue_row(f"C{i}") for i in range(50)]}
        ledger = {"customer_id": 9, "trips": [], "events": [{"kind": "receipt_recorded", "after": {}}]}
        with patch.object(v7_sheet_task_keep, "trip_identity", wraps=v7_sheet_task_keep.trip_identity) as identity:
            self.assertEqual(v7_sheet_queue.removed_trips(queue, ledger), [])
        identity.assert_not_called()

    def test_assignment_to_a_row_still_on_the_sheet_keeps_the_trip_out(self):
        row = queue_row()
        event = {"kind": "sheet_conflict_resolved", "after": {
            "field": "task_assignment", "sheet_value": v7_sheet_task_keep.trip_identity(row),
            "target": {"kind": "trip", "id": 5}}}
        ledger = {"customer_id": 9, "trips": [sheet_trip()], "events": [event]}
        self.assertEqual(v7_sheet_queue.removed_trips({"items": [row]}, ledger), [])

    def test_assignment_to_a_row_gone_from_the_sheet_still_flags_the_trip(self):
        event = {"kind": "sheet_conflict_resolved", "after": {
            "field": "task_assignment", "sheet_value": "không còn trên Sheet", "target": {"kind": "trip", "id": 5}}}
        ledger = {"customer_id": 9, "trips": [sheet_trip()], "events": [event]}
        result = v7_sheet_queue.removed_trips({"items": [queue_row()]}, ledger)
        self.assertEqual([row["trip_id"] for row in result], [5])

    def test_trip_without_any_assignment_is_flagged(self):
        ledger = {"customer_id": 9, "trips": [sheet_trip()], "events": []}
        result = v7_sheet_queue.removed_trips({"items": [queue_row()]}, ledger)
        self.assertEqual([row["trip_id"] for row in result], [5])


def road_item(container, date="2026-10-02", customer_id=9):
    return {"customer_id": customer_id, "container": container, "event_date": date, "tab_debt_month": date[:7]}


class ProjectRoadTests(unittest.TestCase):
    def ledger(self):
        return {"customer_id": 9, "today_month": "2026-10-01", "trips": [
            {"id": 1, "container": "IN1", "event_date": "2026-10-03", "month": "2026-10-01"}]}

    def test_book_targets_are_built_once_however_many_rows_wait(self):
        items = [road_item(f"C{i}") for i in range(40)]
        with patch.object(v7_road_queue, "targets", wraps=v7_road_queue.targets) as targets:
            v7_road_queue.project_road({"items": items}, self.ledger())
        self.assertEqual(targets.call_count, 1)

    def test_no_row_of_this_book_builds_nothing(self):
        with patch.object(v7_road_queue, "targets", wraps=v7_road_queue.targets) as targets:
            v7_road_queue.project_road({"items": [road_item("C1", customer_id=8)]}, self.ledger())
        targets.assert_not_called()

    def test_matching_rules_unchanged(self):
        result = v7_road_queue.project_road({"items": [
            road_item("IN1"),                         # đã có, cách 1 ngày
            road_item("IN1", date="2026-10-20"),      # cùng container, xa ngày: chuyến khác
            road_item("C2"),                          # mới
        ]}, self.ledger())
        self.assertEqual([(row["container"], row["event_date"], row["sync_state"]) for row in result["items"]],
                         [("IN1", "2026-10-20", "NEW"), ("C2", "2026-10-02", "NEW")])


class NameKeyTests(unittest.TestCase):
    def test_same_result_for_every_kind_of_cell(self):
        cases = {None: "", "": "", 0: "", "  A  B ": "A B", "A/B:C": "ABC", "x'y": "xy", 12: "12", 1.5: "1.5", "A\tB\nC": "A B C"}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(v7_price_queue.name_key(value), expected)
                self.assertEqual(v7_price_queue.name_key(value), expected)   # lần hai trả đúng như lần đầu


if __name__ == "__main__":
    unittest.main()
