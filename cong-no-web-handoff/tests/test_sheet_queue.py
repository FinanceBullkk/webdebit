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

    def test_book_chosen_by_customer_and_commodity(self):
        """P3b: khách nhiều sổ (cùng tên khách `display_name`) chọn sổ theo cột "Mặt hàng" của booking sheet."""
        books = [{"id": 1, "name": "KHÁCH A", "status": "active", "commodity": "Thanh long"},
                 {"id": 2, "name": "KHÁCH A - DỪA", "display_name": "Khách A", "status": "active", "commodity": "Dừa"},
                 {"id": 3, "name": "SR BỘ - KHÁCH A", "display_name": "KHÁCH A", "status": "active", "commodity": "Sầu riêng",
                  "transport_mode": "BO"},
                 {"id": 4, "name": "SR CẢNG - KHÁCH A", "display_name": "KHÁCH A", "status": "active", "commodity": "Sầu riêng",
                  "transport_mode": "CANG"},
                 {"id": 5, "name": "KHÁCH B", "status": "active", "commodity": "Chuối"},
                 {"id": 6, "name": "XOÀI - KHÁCH C", "display_name": "KHÁCH C", "status": "active", "commodity": "Xoài"},
                 {"id": 7, "name": "KHÁCH D", "status": "active"},
                 {"id": 8, "name": "KHÁCH F", "status": "active", "commodity": "Thanh long"},
                 {"id": 9, "name": "SR BỘ - KHÁCH F", "display_name": "KHÁCH F", "status": "active", "commodity": "Sầu riêng",
                  "transport_mode": "BO"},
                 {"id": 10, "name": "KHÁCH G", "status": "active", "commodity": "Sầu riêng", "transport_mode": "BO"}]
        cases = [("Khách A", "THANH LONG", 1, "COMMODITY_OK"), ("Khách A", "Dừa", 2, "COMMODITY_OK"),
                 ("Khách A", "SẦU RIÊNG", 4, "COMMODITY_OK"),                # bỏ sổ đường bộ: dòng booking là BIỂN
                 ("Khách A", "MÍT", 1, "COMMODITY_MISMATCH"),                # không sổ nào trùng: giữ sổ trùng tên
                 ("Khách A", "KHÁC", 1, "COMMODITY_UNKNOWN"), ("Khách A", "", 1, "COMMODITY_UNKNOWN"),
                 ("Khách B", "CHUỐI", 5, "COMMODITY_OK"), ("Khách B", "DỪA", 5, "COMMODITY_MISMATCH"),
                 ("Khách C", "XOÀI", 6, "COMMODITY_OK"),                     # chỉ có sổ mang tên khách
                 ("Khách D", "DỪA", 7, "COMMODITY_UNKNOWN"),                 # sổ chưa có mặt hàng
                 ("Khách F", "SẦU RIÊNG", 8, "COMMODITY_MISMATCH"),          # sổ sầu riêng là đường bộ: không chọn
                 ("Khách G", "SẦU RIÊNG", 10, "ROAD_BOOK"),                  # sổ duy nhất là đường bộ: máy không đụng
                 ("Khách E", "DỪA", None, None)]
        rows = [{"source_row": n, "container": f"C{n}", "event_date": "2026-11-01", "status": "READY",
                 "customer_name": name, "commodity": commodity} for n, (name, commodity, _, _) in enumerate(cases, 2)]
        queue = build_queue({"sha256": "a" * 64, "row_count": len(rows), "rows": rows}, books, BASELINE)
        self.assertEqual([(i["customer_id"], i["book_match"]) for i in queue["items"]], [(c[2], c[3]) for c in cases])
        self.assertEqual(queue["items"][-1]["review_status"], "NEEDS_CUSTOMER")
        self.assertEqual(queue["items"][1]["commodity"], "Dừa")

    def test_name_tied_to_one_book_still_picks_sibling_by_commodity(self):
        """Tên Sheet nối thẳng tới tên sổ sầu riêng (bí danh) vẫn tìm sổ mít cùng tên khách (đo trên hao 3/11/2026)."""
        books = [{"id": 1, "name": "KHÁCH H-SR", "display_name": "KHÁCH H", "status": "active", "commodity": "Sầu riêng"},
                 {"id": 2, "name": "MIT - KHÁCH H", "display_name": "KHÁCH H", "status": "active", "commodity": "Mít"},
                 {"id": 3, "name": "KHÁCH K", "status": "active", "commodity": "Thanh long"},
                 {"id": 4, "name": "KHÁCH K-SR", "display_name": "KHÁCH K", "status": "active", "commodity": "Sầu riêng"}]
        cases = [("KHÁCH H-SR", "MÍT", 2), ("KHÁCH H-SR", "SẦU RIÊNG", 1), ("KHÁCH H-SR", "DỪA", 1),
                 ("KHÁCH K-SR", "THANH LONG", 3)]
        rows = [{"source_row": n, "container": f"C{n}", "event_date": "2026-11-01", "status": "READY",
                 "customer_name": name, "commodity": commodity} for n, (name, commodity, _) in enumerate(cases, 2)]
        queue = build_queue({"sha256": "a" * 64, "row_count": len(rows), "rows": rows}, books, BASELINE)
        self.assertEqual([i["customer_id"] for i in queue["items"]], [c[2] for c in cases])

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
        row["source_row"] = 41   # source tab switched, row numbers moved: the decision still holds
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
        # CHUYEN-KHONG-HOI-01: không vào sổ, cũng không thành việc; chỉ nằm ở danh sách chờ tab Sheet.
        self.assertEqual((result["items"], result["new_count"], result["conflict_count"], result["waiting_count"]), ([], 0, 0, 1))
        self.assertEqual((result["waiting_items"][0]["sync_state"], result["waiting_items"][0]["sync_reason"]),
                         ("WAITING", "CONTAINER_REUSED_OR_CHANGED"))
        ledger["trips"][0]["event_date"] = None
        self.assertEqual((project_customer(queue, ledger)["new_count"], project_customer(queue, ledger)["waiting_count"]), (0, 1))

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

    def test_other_book_original_row_is_not_offered_as_new(self):
        # docs/ux-luong-du-lieu.md 3.3: the same customer's other commodity book already has the trip in its original book.
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 2, "customer_id": 7,
            "container": "dup 1", "event_date": "2026-03-18", "review_status": "NEEDS_PRICE"}]}
        ledger = {"customer_id": 7, "legacy_rows": [], "trips": []}
        cases = [
            ({"container": "DUP1", "event_date": None, "debt_month": "2026-03-01"}, "OTHER_BOOK_LEGACY"),
            ({"container": "DUP1", "event_date": "2026-03-21", "debt_month": "2026-03-01"}, "OTHER_BOOK_LEGACY"),
            ({"container": "DUP1", "event_date": None, "debt_month": "2026-04-01"}, ""),
            ({"container": "DUP1", "event_date": "2026-03-28", "debt_month": "2026-03-01"}, ""),
            ({"container": "OTHER", "event_date": None, "debt_month": "2026-03-01"}, ""),
        ]
        for ref, reason in cases:
            with self.subTest(ref=ref):
                item = project_customer(queue, ledger, set(), [{"customer_id": 8, **ref}])["items"][0]
                self.assertEqual((item["sync_state"], item["sync_reason"]), ("CONFLICT", reason) if reason else ("NEW", ""))
        self.assertEqual(project_customer(queue, ledger)["new_count"], 1)
        # Sổ kia cùng khách: chuyến đã tính ở đó, không hiện gì; sổ khách khác vẫn đỏ.
        same = {"customer_id": 8, "container": "DUP1", "event_date": "2026-03-18", "debt_month": "2026-03-01"}
        self.assertEqual(project_customer(queue, ledger, set(), [same], {8})["items"], [])
        other = {**same, "customer_id": 9}
        for refs in ([other], [other, same]):  # có ở sổ khách khác thì vẫn để người xem
            item = project_customer(queue, ledger, set(), refs, {8})["items"][0]
            self.assertEqual(item["sync_reason"], "OTHER_BOOK_LEGACY")

    def test_undated_original_row_in_same_month_is_this_trip(self):
        """MAY-KHOA-01 nhóm A: dòng sổ gốc không ngày cùng tháng nợ là chuyến này (lệch ngày), không phải container đã dùng."""
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 2, "customer_id": 7, "container": "UND1",
                 "event_date": "2026-03-18", "review_status": "NEEDS_PRICE", "origin": "KHO", "destination": "CANG",
                 "shipper": "TN"}]}

        def legacy(n, month, date=None):
            return {"id": n, "kind": "trip", "month": month, "current": {"container": "UND1", "event_date": date,
                    "debt_month": month, "origin": "KHO", "destination": "CANG", "shipper": "TN"}}
        cases = [([legacy(5, "2026-03-01")], ("CONFLICT", "DIFFERENT_FIELDS", ["event_date"], 5, "2026-03-01")),
                 ([legacy(5, "2026-04-01")], "WAITING"),
                 ([legacy(5, "2026-03-01"), legacy(6, "2026-03-01")], "WAITING"),
                 ([legacy(5, "2026-03-01", "2026-03-18")], None)]   # có ngày, trùng ngày: không còn việc
        for rows, want in cases:
            with self.subTest(rows=len(rows), want=want):
                result = project_customer(queue, {"customer_id": 7, "trips": [], "legacy_rows": rows})
                items = result["items"]
                got = (items[0]["sync_state"], items[0]["sync_reason"], items[0]["changed_fields"], items[0]["existing_id"],
                       items[0]["existing_debt_month"]) if items else ("WAITING" if result["waiting_items"] else None)
                self.assertEqual(got, want)

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


def first(result):
    """Dòng duy nhất của một lần chiếu: việc (`items`) hoặc dòng chờ tab Sheet (`waiting_items`), không bao giờ cả hai."""
    rows = result["items"] + result["waiting_items"]
    assert len(rows) == 1, rows
    return rows[0]


class KeptLegacyDateTests(unittest.TestCase):
    """CHUYEN-KHONG-HOI-01: dòng sổ gốc đã có ngày, lệch nguồn không quá 3 ngày: giữ ngày sổ gốc, không hỏi."""

    def items(self, source_date, old, **source):
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 2, "customer_id": 7, "container": "DAY1",
                 "event_date": source_date, "review_status": "NEEDS_PRICE", "origin": "KHO", "destination": "CANG",
                 "shipper": "TN", **source}]}
        return project_customer(queue, {"customer_id": 7, **old})

    def legacy(self, date, **current):
        return {"trips": [], "legacy_rows": [{"id": 5, "kind": "trip", "month": "2026-03-01", "current": {
            "container": "DAY1", "event_date": date, "debt_month": "2026-03-01", "origin": "KHO", "destination": "CANG",
            "shipper": "TN", **current}}]}

    def test_date_within_three_days_is_not_a_question(self):
        for source_date in ("2026-03-15", "2026-03-19", "2026-03-21"):
            with self.subTest(source_date):
                result = self.items(source_date, self.legacy("2026-03-18"))
                self.assertEqual((result["items"], result["waiting_items"]), ([], []))

    def test_text_difference_stays_and_the_machine_may_take_it(self):
        item = self.items("2026-03-20", self.legacy("2026-03-18"), destination="CANG MOI")["items"][0]
        self.assertEqual((item["sync_reason"], item["changed_fields"], item["existing_id"]), ("DIFFERENT_FIELDS", ["destination"], 5))
        self.assertEqual(item["existing_values"], {"destination": "CANG"})

    def test_undated_original_row_still_gets_its_date(self):
        item = self.items("2026-03-20", self.legacy(None))["items"][0]   # MAY-KHOA-01 nhóm A giữ nguyên
        self.assertEqual(item["changed_fields"], ["event_date"])

    def test_web_trip_date_still_asks(self):
        trip = {"legacy_rows": [], "trips": [{"id": 8, "container": "DAY1", "event_date": "2026-03-18", "origin": "KHO",
                "destination": "CANG", "shipper": "TN", "carrier": None}]}
        item = self.items("2026-03-20", trip)["items"][0]
        self.assertEqual((item["existing_kind"], item["changed_fields"]), ("trip", ["event_date"]))

    def test_four_days_is_not_the_same_trip(self):
        result = self.items("2026-03-22", self.legacy("2026-03-18"))
        self.assertEqual((result["items"], result["waiting_count"]), ([], 1))

    def test_three_days_across_a_month_end_is_not_a_question_either(self):
        result = self.items("2026-04-02", self.legacy("2026-03-31"))   # tháng nợ của dòng sổ gốc vẫn là tháng 3
        self.assertEqual((result["items"], result["waiting_items"]), ([], []))

    def test_original_row_claimed_by_two_source_rows_keeps_asking(self):
        """Nguồn có hai chuyến cách nhau trong 3 ngày, sổ có một dòng: bỏ ô ngày thì máy lấy chữ theo dòng này rồi dòng kia."""
        def source(row, date, destination="CANG"):
            return {"source_row": row, "customer_id": 7, "container": "DAY1", "event_date": date, "review_status": "NEEDS_PRICE",
                    "origin": "KHO", "destination": destination, "shipper": "TN"}
        ledger = {"customer_id": 7, **self.legacy("2026-03-18")}
        both = {"snapshot_sha256": "a" * 64, "items": [source(2, "2026-03-18"), source(3, "2026-03-20", "CANG MOI")]}
        items = project_customer(both, ledger)["items"]
        self.assertEqual([(item["source_row"], item["changed_fields"]) for item in items], [(3, ["event_date", "destination"])])
        date_only = {"snapshot_sha256": "a" * 64, "items": [source(2, "2026-03-18"), source(3, "2026-03-20")]}
        self.assertEqual([item["changed_fields"] for item in project_customer(date_only, ledger)["items"]], [["event_date"]])
        # Chỉ một dòng nguồn nhận dòng sổ gốc: ô ngày không còn là câu hỏi, phần chữ để máy lấy.
        alone = {"snapshot_sha256": "a" * 64, "items": [source(3, "2026-03-20", "CANG MOI")]}
        self.assertEqual([item["changed_fields"] for item in project_customer(alone, ledger)["items"]], [["destination"]])


class ReusedContainerTests(unittest.TestCase):
    """CONTAINER-DUNG-LAI-01: container đã có trong sổ chỉ là chuyến mới khi tab khách ghi riêng chuyến đó."""

    def item(self, event_date, old_dates, tab_dates, **kwargs):
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 500, "customer_id": 7, "container": "reuse 1",
                 "event_date": event_date, "booking": "BK-MOI", "review_status": "NEEDS_PRICE"}]}
        legacy = [{"id": n, "kind": "trip", "month": "2026-01-01",
                   "current": {"container": "REUSE1", "event_date": old, "debt_month": "2026-01-01"}}
                  for n, old in enumerate(old_dates, 1)]
        tab = [{"customer_tab": "Khách mẫu", "container": "REUSE1", "date": date} for date in tab_dates]
        return first(project_customer(queue, {"customer_id": 7, "trips": [], "legacy_rows": legacy}, tab_rows=tab, **kwargs))

    def assert_held(self, item):
        # CHUYEN-KHONG-HOI-01: giữ ngoài sổ như trước, nhưng là dòng chờ tab Sheet chứ không phải việc cần người xem.
        self.assertEqual((item["sync_state"], item["sync_reason"]), ("WAITING", "CONTAINER_REUSED_OR_CHANGED"))

    def test_tab_has_its_own_row_for_the_new_trip(self):
        item = self.item("2026-10-31", ["2026-02-01"], ["2026-02-01", "2026-10-31"])
        self.assertEqual((item["sync_state"], item["sync_reason"]), ("NEW", ""))
        near = self.item("2026-10-31", ["2026-02-01"], ["2026-02-01", "2026-10-28"])
        self.assertEqual(near["sync_state"], "NEW")

    def test_same_trip_with_another_date_stays_held(self):
        """Đo trên `hao` 4/11/2026: 15/17 dòng là một chuyến, nguồn và tab khác ngày; xét theo khoảng cách ngày sẽ cộng trùng."""
        cases = {"lệch vài tuần": ("2026-03-28", ["2026-03-10"], ["2026-03-10"]),
                 "tab sai năm": ("2026-01-04", ["2025-01-04"], ["2025-01-04"]),
                 "tab ngày lạ": ("2026-07-31", ["1909-01-29"], ["1909-01-29"]),
                 "tab không ngày": ("2026-08-18", [None], [None])}
        for name, case in cases.items():
            with self.subTest(name):
                self.assert_held(self.item(*case))

    def test_tab_without_the_new_row_yet_stays_held_then_passes(self):
        self.assert_held(self.item("2026-11-04", ["2026-04-20", "2026-07-19"], ["2026-04-20", "2026-07-19"]))
        item = self.item("2026-11-04", ["2026-04-20", "2026-07-19"], ["2026-04-20", "2026-07-19", "2026-11-04"])
        self.assertEqual(item["sync_state"], "NEW")

    def test_date_corrected_on_tab_is_not_a_second_trip(self):
        """Tab sửa đúng ngày mà sổ còn ngày cũ: vẫn một dòng tab, một dòng sổ."""
        self.assert_held(self.item("2026-07-31", ["1909-01-29"], ["2026-07-31"]))

    def test_tab_row_must_be_a_trip_of_its_own(self):
        cases = {"dòng lặp ở ngày cũ": ("2026-07-17", ["2026-07-27"], ["2026-07-27", "2026-07-27"]),
                 "dòng tab sát dòng sổ": ("2026-10-31", ["2026-10-25"], ["2026-10-25", "2026-10-28"]),
                 "dòng tab không ngày": ("2026-10-31", ["2026-02-01"], ["2026-02-01", None]),
                 "ngày tab đọc không được": ("2026-10-31", ["2026-02-01"], ["2026-02-01", "31/10"])}
        for name, case in cases.items():
            with self.subTest(name):
                self.assert_held(self.item(*case))

    def test_no_tab_data_keeps_the_old_rule(self):
        self.assert_held(self.item("2026-10-31", ["2026-02-01"], []))
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 500, "customer_id": 7, "container": "REUSE1",
                 "event_date": "2026-10-31", "review_status": "NEEDS_PRICE"}]}
        ledger = {"customer_id": 7, "trips": [{"id": 1, "container": "REUSE1", "event_date": "2026-02-01"}], "legacy_rows": []}
        self.assert_held(first(project_customer(queue, ledger)))

    def test_other_rows_of_the_tab_do_not_count(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [{"source_row": 500, "customer_id": 7, "container": "REUSE1",
                 "event_date": "2026-10-31", "review_status": "NEEDS_PRICE"}]}
        ledger = {"customer_id": 7, "trips": [{"id": 1, "container": "REUSE1", "event_date": "2026-02-01"}], "legacy_rows": []}
        tab = [{"container": "KHAC1", "date": "2026-10-31"}, {"container": "KHAC2", "date": "2026-10-31"}]
        self.assert_held(first(project_customer(queue, ledger, tab_rows=tab)))

    def test_other_book_checks_still_apply_to_a_new_trip(self):
        tab = ["2026-02-01", "2026-10-31"]
        near = {"customer_id": 8, "container": "REUSE1", "event_date": "2026-10-30", "debt_month": "2026-10-01"}
        item = self.item("2026-10-31", ["2026-02-01"], tab, other_legacy=[near])
        self.assertEqual((item["sync_state"], item["sync_reason"]), ("CONFLICT", "OTHER_BOOK_LEGACY"))
        item = self.item("2026-10-31", ["2026-02-01"], tab, other_customer_containers={"REUSE1"})
        self.assertEqual((item["sync_state"], item["sync_reason"]), ("CONFLICT", "OTHER_CUSTOMER"))


PROJECTION_SNAPSHOT = {"sha256": "c" * 64, "row_count": 1, "rows": [
    {"source_row": 500, "container": "REUSE1", "event_date": "2026-10-31", "status": "READY", "customer_name": "Khách mẫu",
     "carrier": "WH", "origin": "A", "destination": "B"}]}
PROJECTION_BASELINE = {"cutover_id": 1, "count": 0, "refs": []}
PROJECTION_LEDGER = {"customer_id": 7, "legacy_rows": [], "events": [],
                     "trips": [{"id": 1, "container": "REUSE1", "event_date": "2026-02-01"}]}
PROJECTION_CUSTOMERS = [{"id": 7, "name": "KHÁCH MẪU", "status": "active"}, {"id": 8, "name": "KHÁCH KHÁC", "status": "active"}]


class SheetProjectionTabRowsTests(unittest.TestCase):
    """sheet_projection lấy dòng tab đúng của sổ từ bản chụp giá; bản chụp hỏng thì giữ luật cũ, không làm hỏng hàng chờ."""

    def project(self, prices, ledger=PROJECTION_LEDGER, whole=False):
        import v7_api_sheet
        from v7_price_queue import load_price_snapshot

        class Runner:
            def run(self, function, payload, actor):
                return {"customers": PROJECTION_CUSTOMERS} if function == "list_customers" else {"items": []}

        def load(loader, path):
            if loader is load_price_snapshot:
                if prices is None:
                    raise ValueError("Sheet price snapshot unavailable")
                return {"sha256": "d" * 64, "rows": prices}
            return PROJECTION_SNAPSHOT if loader is sheet_queue.load_snapshot else PROJECTION_BASELINE

        with patch.object(v7_api_sheet, "cached_load", load), patch.object(v7_api_sheet, "customer_name_mapping", return_value={}), \
                patch.object(v7_api_sheet, "other_book_checks", return_value=(set(), [])):
            result = v7_api_sheet.sheet_projection(Runner(), ledger, "test")
            return result if whole else first(result)

    def test_rows_come_from_this_book_tab_only(self):
        mine = [{"customer_tab": "KHÁCH MẪU", "container": "REUSE1", "date": day} for day in ("2026-02-01", "2026-10-31")]
        self.assertEqual(self.project(mine)["sync_state"], "NEW")
        other = [{**row, "customer_tab": "KHÁCH KHÁC"} for row in mine]
        self.assertEqual(self.project(other)["sync_reason"], "CONTAINER_REUSED_OR_CHANGED")

    def test_broken_price_snapshot_keeps_the_old_rule(self):
        self.assertEqual(self.project(None)["sync_reason"], "CONTAINER_REUSED_OR_CHANGED")

    def test_waiting_row_a_person_assigned_elsewhere_is_gone(self):
        """CHUYEN-KHONG-HOI-01: dòng chờ tab Sheet mà người đã gán vào một chuyến thì không còn chờ ở sổ này."""
        from v7_sheet_task_keep import trip_identity
        waiting = self.project(None)
        self.assertEqual(waiting["sync_state"], "WAITING")
        assigned = {"kind": "sheet_conflict_resolved", "after": {"field": "task_assignment", "target_customer_id": 7,
                    "target": {"kind": "trip", "id": 1}, "sheet_value": trip_identity(waiting)}}
        result = self.project(None, {**PROJECTION_LEDGER, "events": [assigned]}, whole=True)
        self.assertEqual((result["items"], result["waiting_items"], result["waiting_count"]), ([], [], 0))


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
        self.assertRegex(result["removed_items"][0].pop("source_fingerprint"), r"^[0-9a-f]{64}$")
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
