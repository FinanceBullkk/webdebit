import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "web"))
import v7_sheet_queue as sheet_queue
from v7_sheet_queue import (
    build_queue,
    load_snapshot,
    plan_shipper_backfill,
    project_customer,
)

BASELINE = {"cutover_id": 1, "count": 1, "refs": [{
    "container_norm": "OLD123", "booking_norm": "ALT:OLD123:20261001", "event_date": "2026-10-01"
}]}


class SheetQueueTests(unittest.TestCase):
    def test_reconciled_baseline_rows_join_realtime_queue_by_source_row(self):
        snapshot = {"sha256": "a" * 64, "row_count": 2, "rows": [
            {"source_row": 2, "container": "OLD123", "event_date": "2026-10-01", "status": "READY", "customer_name": "Khách A", "durian_type": "frozen"},
            {"source_row": 3, "container": "NEW123", "event_date": "2026-10-02", "status": "READY", "customer_name": "Unknown"},
        ]}
        queue = build_queue(snapshot, [{"id": 7, "name": "KHÁCH A", "status": "active"}], BASELINE)
        self.assertEqual(queue["items"][0]["review_status"], "NEEDS_PRICE")
        self.assertEqual(queue["items"][0]["durian_type"], "frozen")
        self.assertEqual(queue["items"][0]["customer_id"], 7)
        self.assertEqual(queue["items"][1]["review_status"], "NEEDS_CUSTOMER")
        self.assertEqual(queue["ready_count"], 0)

    def test_baseline_container_without_current_row_is_new_after_reconciliation(self):
        snapshot = {"sha256": "a" * 64, "row_count": 1, "rows": [
            {"source_row": 2, "container": "OLD123", "event_date": "2026-10-01", "status": "READY", "customer_name": "Khách A"}
        ]}
        queue = build_queue(snapshot, [{"id": 7, "name": "KHÁCH A", "status": "active"}], BASELINE)
        result = project_customer(queue, {"customer_id": 7, "trips": [], "legacy_rows": []})
        self.assertEqual(result["items"][0]["sync_state"], "NEW")
        self.assertEqual(result["items"][0]["sync_reason"], "")

    def test_realtime_row_uses_source_mapping_when_sheet_date_changes(self):
        row = {"source_row": 8, "customer_id": 7, "container": "NEWNAME", "event_date": "2026-10-24",
               "carrier": "WH", "origin": "A", "destination": "B", "review_status": "NEEDS_PRICE"}
        queue = {"snapshot_sha256": "b" * 64, "items": [row]}
        ledger = {"customer_id": 7, "trips": [{"id": 9, "container": "OLDNAME", "source_ref": f"sheet:{'a' * 64}:8",
            "event_date": "2026-10-01", "carrier": "WH", "origin": "A", "destination": "B"}], "legacy_rows": []}
        result = project_customer(queue, ledger)
        self.assertEqual(result["items"][0]["existing_id"], 9)
        self.assertIn("event_date", result["items"][0]["changed_fields"])

    def test_durian_type_only_for_exact_source_trip(self):
        row = {"source_row": 8, "customer_id": 7, "container": "ABC1", "event_date": "2026-10-24",
               "durian_type": "fresh", "status": "READY", "review_status": "NEEDS_PRICE"}
        queue = {"snapshot_sha256": "b" * 64, "items": [row]}
        ledger = {"customer_id": 7, "trips": [
            {"id": 9, "container": "ABC1", "source_ref": f"sheet:{'a' * 64}:8", "event_date": "2026-10-24"},
            {"id": 10, "container": "ABC1", "source_ref": f"sheet:{'a' * 64}:9", "event_date": "2026-10-24"}],
            "legacy_rows": []}
        result = project_customer(queue, ledger)
        self.assertEqual(result["trip_types"], {"9": "fresh"})
        self.assertEqual(result["items"], [])

    def test_direct_source_match_does_not_grow_matches_while_scanning(self):
        row = {"source_row": 8, "customer_id": 7, "container": "ABC1", "event_date": "2026-10-24",
               "carrier": "COSCO", "origin": "A", "destination": "B", "review_status": "NEEDS_PRICE"}
        queue = {"snapshot_sha256": "b" * 64, "items": [row]}
        ledger = {"customer_id": 7, "trips": [{"id": 9, "container": "ABC1", "source_ref": f"sheet:{'a' * 64}:8",
            "event_date": "2026-10-24", "carrier": "WH", "origin": "A", "destination": "B"}], "legacy_rows": []}
        original_container = sheet_queue._container
        calls = 0

        def bounded_container(value):
            nonlocal calls
            calls += 1
            if calls > 4:
                raise AssertionError("container matcher looped")
            return original_container(value)

        with patch.object(sheet_queue, "_container", side_effect=bounded_container):
            result = project_customer(queue, ledger)

        self.assertEqual(calls, 2)
        self.assertEqual(result["items"][0]["existing_id"], 9)
        self.assertEqual(result["items"][0]["changed_fields"], ["carrier"])

    def test_trip_shipper_conflict_keeps_null_web_value(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [{
            "source_row": 8, "customer_id": 7, "container": "ABC1", "event_date": "2026-10-24",
            "carrier": "COSCO", "shipper": "KHOI PHONG", "origin": "A", "destination": "B",
            "review_status": "NEEDS_PRICE"}]}
        ledger = {"customer_id": 7, "trips": [{"id": 9, "container": "ABC1", "source_ref": f"sheet:{'a' * 64}:8",
            "event_date": "2026-10-24", "carrier": "COSCO", "shipper": None, "origin": "A", "destination": "B"}],
            "legacy_rows": []}
        conflict = project_customer(queue, ledger)["items"][0]
        self.assertEqual(conflict["changed_fields"], ["shipper"])
        self.assertEqual(conflict["existing_values"], {"shipper": None})

    def test_later_years_stay_in_queue_and_older_rows_are_counted(self):
        rows = [{"source_row": n, "container": f"Y{n}", "event_date": date, "status": "READY", "customer_name": "Khách A"}
                for n, date in ((2, "2025-12-31"), (3, "2026-12-31"), (4, "2027-01-02"), (5, "2030-06-01"))]
        queue = build_queue({"sha256": "a" * 64, "row_count": 4, "rows": rows},
                            [{"id": 7, "name": "KHÁCH A", "status": "active"}], BASELINE)
        self.assertEqual([item["source_row"] for item in queue["items"]], [3, 4, 5])
        self.assertEqual(queue["skipped_out_of_scope"], 1)

    def test_invalid_rows_remain_visible(self):
        snapshot = {"sha256": "b" * 64, "row_count": 1, "rows": [{"source_row": 2, "status": "INVALID"}]}
        queue = build_queue(snapshot, [], BASELINE)
        self.assertEqual(queue["items"][0]["review_status"], "INVALID")

    def test_load_snapshot_rejects_missing_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            path.write_text('{"rows":[],"row_count":0}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash"):
                load_snapshot(path)

    def test_customer_projection_new_same_and_changed(self):
        rows = [
            {"source_row": 2, "container": "NEW1", "event_date": "2026-10-24", "carrier": "WH",
             "origin": "A", "destination": "B", "status": "READY", "customer_name": "Khách A"},
            {"source_row": 3, "container": "OLD123", "event_date": "2026-10-01", "carrier": "WH", "shipper": "WH",
             "origin": "A", "destination": "B", "status": "READY", "customer_name": "Khách A"},
            {"source_row": 4, "container": "WEB1", "booking": "BK-NEW", "event_date": "2026-10-24", "carrier": "COSCO",
             "origin": "A", "destination": "B", "status": "READY", "customer_name": "Khách A"},
        ]
        queue = build_queue({"sha256": "a" * 64, "row_count": 3, "rows": rows},
                            [{"id": 7, "name": "KHÁCH A", "status": "active"}], BASELINE)
        ledger = {"customer_id": 7, "legacy_rows": [{"id": 1, "kind": "trip", "current": {
            "container": "OLD123", "event_date": "2026-10-01", "carrier": "WH", "origin": "A", "destination": "B"}}],
            "trips": [{"id": 9, "container": "WEB1", "booking": "BK-OLD", "event_date": "2026-10-24", "carrier": "WH",
                       "origin": "A", "destination": "B"}]}
        result = project_customer(queue, ledger)
        self.assertEqual([item["sync_state"] for item in result["items"]], ["NEW", "CONFLICT"])
        self.assertEqual(result["items"][1]["existing_id"], 9)
        self.assertEqual(result["items"][1]["changed_fields"], ["carrier", "booking"])
        self.assertEqual((result["new_count"], result["conflict_count"]), (1, 1))

    def test_kept_web_field_stays_resolved_until_either_value_changes(self):
        row = {"source_row": 4, "customer_id": 7, "container": "ABC1", "event_date": "2026-10-01",
               "carrier": "COSCO", "origin": "A", "destination": "B", "review_status": "NEEDS_PRICE"}
        queue = {"snapshot_sha256": "a" * 64, "items": [row]}
        ledger = {"customer_id": 7, "trips": [{"id": 9, "container": "ABC1", "event_date": "2026-10-01",
            "carrier": "WH", "origin": "A", "destination": "B"}], "legacy_rows": [], "events": []}
        self.assertEqual(project_customer(queue, ledger)["items"][0]["changed_fields"], ["carrier"])
        ledger["events"] = [{"kind": "sheet_conflict_resolved", "after": {"source_row": 4,
            "target": {"kind": "trip", "id": 9}, "field": "carrier", "target_value": "WH", "sheet_value": "COSCO"}}]
        self.assertEqual(project_customer(queue, ledger)["items"], [])
        queue["snapshot_sha256"] = "b" * 64
        self.assertEqual(project_customer(queue, ledger)["items"], [])
        row["carrier"] = "MAERSK"
        self.assertEqual(project_customer(queue, ledger)["conflict_count"], 1)
        row["carrier"] = "COSCO"
        ledger["trips"][0]["carrier"] = "ONE"
        self.assertEqual(project_customer(queue, ledger)["conflict_count"], 1)

    def test_container_reuse_is_reviewed_not_auto_approved(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 2, "customer_id": 7,
            "container": "SAME1", "event_date": "2026-10-24", "carrier": "WH", "origin": "A",
            "destination": "B", "review_status": "NEEDS_PRICE"}]}
        ledger = {"customer_id": 7, "legacy_rows": [], "trips": [{"id": 8, "container": "SAME1",
            "event_date": "2026-01-01", "carrier": "WH", "origin": "A", "destination": "B"}]}
        result = project_customer(queue, ledger)
        self.assertEqual(result["items"][0]["sync_reason"], "CONTAINER_REUSED_OR_CHANGED")
        self.assertEqual(result["new_count"], 0)
        ledger["trips"][0]["event_date"] = None
        self.assertEqual(project_customer(queue, ledger)["new_count"], 0)

    def test_legacy_shipper_compares_with_booking_shipper_not_shipping_line(self):
        ledger = {"customer_id": 7, "legacy_rows": [{"id": 1, "kind": "trip", "current": {
            "container": "ABC1", "event_date": "2026-10-01", "carrier": "TAY NGUYEN",
            "origin": "A", "destination": "B"}}], "trips": []}
        source = {"source_row": 2, "customer_id": 7, "container": "ABC1", "event_date": "2026-10-01",
                  "carrier": "COSCO", "shipper": "TAY NGUYEN", "origin": "A", "destination": "B",
                  "review_status": "NEEDS_PRICE"}
        queue = {"snapshot_sha256": "a" * 64, "items": [source]}
        self.assertEqual(project_customer(queue, ledger)["conflict_count"], 0)
        queue["items"][0] = source | {"shipper": "KHOI PHONG"}
        conflict = project_customer(queue, ledger)["items"][0]
        self.assertEqual(conflict["changed_fields"], ["shipper"])
        self.assertEqual(conflict["existing_values"], {"shipper": "TAY NGUYEN"})
        queue["items"][0] = {key: value for key, value in source.items() if key != "shipper"}
        self.assertEqual(project_customer(queue, ledger)["items"][0]["changed_fields"], ["shipper_unavailable"])

    def test_other_customer_trip_is_red_even_when_current_ledger_is_empty(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 2, "customer_id": 7,
            "container": "CROSS1", "event_date": "2026-10-24", "review_status": "NEEDS_PRICE"}]}
        ledger = {"customer_id": 7, "legacy_rows": [], "trips": []}
        result = project_customer(queue, ledger, {"CROSS1"})
        self.assertEqual((result["new_count"], result["conflict_count"]), (0, 1))
        self.assertEqual(result["items"][0]["sync_reason"], "OTHER_CUSTOMER")

    def test_shipper_backfill_only_proposes_unique_exact_matches(self):
        queue = {"items": [{"customer_id": 7, "status": "READY", "source_row": 8,
                            "container": "ABC1", "event_date": "2026-10-01",
                            "carrier": "COSCO", "shipper": "TAY NGUYEN"}]}
        ledger = {"customer_id": 7, "trips": [], "legacy_rows": [{"id": 3, "kind": "trip",
                  "current": {"container": "ABC1", "event_date": "2026-10-01", "carrier": "TAY NGUYEN"}}]}
        proposals = plan_shipper_backfill(queue, ledger)
        self.assertEqual(proposals[0]["after"], {"carrier": "COSCO", "shipper": "TAY NGUYEN"})
        queue["items"].append(queue["items"][0] | {"source_row": 9})
        self.assertEqual(plan_shipper_backfill(queue, ledger), [])


class RemovedSheetTripTests(unittest.TestCase):
    def ready(self, container, date, booking=None, customer_id=7):
        return {"source_row": 2, "customer_id": customer_id, "container": container, "event_date": date,
                "booking": booking, "status": "READY", "review_status": "NEEDS_PRICE"}

    def trip(self, trip_id, container, date, booking=None, **extra):
        return {"id": trip_id, "month": date[:7] + "-01", "container": container, "event_date": date, "booking": booking,
                "note": "Chuyến đồng bộ", "status": "confirmed", "amount_vnd": "5000000", "info_editable": True, **extra}

    def project(self, rows, trips, legacy=()):
        queue = {"snapshot_sha256": "c" * 64, "items": rows}
        return project_customer(queue, {"customer_id": 7, "trips": trips, "legacy_rows": list(legacy)})

    def test_trip_without_sheet_row_is_reported_with_amount_and_lock(self):
        result = self.project([self.ready("KEEP1", "2026-10-20")], [
            self.trip(9, "GONE1", "2026-09-10", info_editable=False),
            self.trip(10, "KEEP1", "2026-10-20")])
        self.assertEqual(result["removed_items"], [{"trip_id": 9, "container": "GONE1", "event_date": "2026-09-10",
            "month": "2026-09-01", "status": "confirmed", "amount_vnd": "5000000", "month_locked": True}])
        self.assertEqual(result["removed_count"], 1)
        self.assertEqual(result["items"], [])

    def test_sheet_row_within_three_days_or_same_booking_keeps_trip(self):
        rows = [self.ready("ABC1", "2026-10-23"), self.ready("ABC2", "2026-10-01", "BK9")]
        result = self.project(rows, [self.trip(9, "ABC1", "2026-10-20"), self.trip(10, "abc 2", "2026-10-20", "bk9"),
                                     self.trip(11, "ABC1", "2026-10-19")])
        self.assertEqual([item["trip_id"] for item in result["removed_items"]], [11])

    def test_source_ref_trip_counts_and_other_customer_row_does_not_match(self):
        rows = [self.ready("KEEP1", "2026-10-20"), self.ready("MOVED", "2026-10-20", customer_id=8)]
        trip = {**self.trip(9, "MOVED", "2026-10-20"), "note": None, "source_ref": f"sheet:{'a' * 64}:5"}
        self.assertEqual(self.project(rows, [trip])["removed_count"], 1)

    def test_unmapped_sheet_row_keeps_trip(self):
        rows = [self.ready("KEEP1", "2026-10-20"), self.ready("NONAME", "2026-10-20", customer_id=None)]
        self.assertEqual(self.project(rows, [self.trip(9, "NONAME", "2026-10-20")])["removed_items"], [])

    def test_legacy_manual_rejected_and_old_trips_are_not_reported(self):
        rows = [self.ready("KEEP1", "2026-10-20")]
        legacy = [{"id": 1, "kind": "trip", "current": {"container": "OLD1", "event_date": "2026-10-01"}}]
        trips = [{**self.trip(9, "MANUAL", "2026-10-20"), "note": None},
                 self.trip(10, "REJ1", "2026-10-20", status="rejected"),
                 self.trip(11, "OLDYEAR", "2025-12-30")]
        self.assertEqual(self.project(rows, trips, legacy)["removed_items"], [])

    def test_non_ready_row_does_not_keep_trip_but_empty_snapshot_reports_nothing(self):
        invalid = {**self.ready("ABC1", "2026-10-20"), "status": "INVALID", "review_status": "INVALID"}
        trips = [self.trip(9, "ABC1", "2026-10-20")]
        self.assertEqual(self.project([invalid, self.ready("KEEP1", "2026-10-20")], trips)["removed_count"], 1)
        self.assertEqual(self.project([invalid], trips)["removed_count"], 0)
        self.assertEqual(self.project([], trips)["removed_items"], [])


if __name__ == "__main__":
    unittest.main()
