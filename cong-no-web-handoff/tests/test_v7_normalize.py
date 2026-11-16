"""KIEM-TAB-01 K4: một chỗ chuẩn hóa chữ và mã container. Dữ liệu giả; mã container bịa."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
import v7_month_report as month_report  # noqa: E402
import v7_normalize as normalize  # noqa: E402
import v7_trip_source_match as source_match  # noqa: E402
from v7_price_queue import container_key as price_key  # noqa: E402
from v7_sheet_queue import _container as queue_key  # noqa: E402
from v7_sheet_queue import project_customer  # noqa: E402


class TextTests(unittest.TestCase):
    def test_empty_and_blank_text_is_none_and_the_rest_is_trimmed(self):
        for raw in (None, "", "   ", "\t\n"):
            self.assertIsNone(normalize.text_or_none(raw), repr(raw))
        self.assertEqual(normalize.text_or_none("  KHOI PHONG "), "KHOI PHONG")
        self.assertEqual(normalize.text_or_none("0"), "0")   # chữ "0" vẫn là chữ, không phải rỗng


class ContainerTests(unittest.TestCase):
    def test_note_next_to_the_code_is_split_off(self):
        self.assertEqual(normalize.split_container("YMLU5506443-mã chưa up"), ("YMLU5506443", "mã chưa up"))
        self.assertEqual(normalize.split_container("chờ - TCNU1234567"), ("TCNU1234567", "chờ"))
        self.assertEqual(normalize.split_container("ymlu 5506443"), ("YMLU5506443", ""))
        self.assertEqual(normalize.split_container(" ABCD1234567 "), ("ABCD1234567", ""))

    def test_cells_that_cannot_be_split_stay_as_they_are(self):
        for raw in ("AAAA1111111/BBBB2222222",   # hai mã: không đoán mã nào
                    "FAKEU0000001",              # năm chữ: không phải khúc giữa của mã ISO
                    "YMLU55064431",              # tám số
                    "FAKE-C", "KT-1", ""):
            with self.subTest(raw=raw):
                self.assertEqual(normalize.split_container(raw), (raw.upper(), ""))
                self.assertEqual(normalize.container_key(raw), raw.upper())

    def test_key_reads_numbers_and_codes_with_notes(self):
        self.assertEqual(normalize.container_key("YMLU5506443-mã chưa up"), "YMLU5506443")
        self.assertEqual(normalize.container_key("SO YMLU5506443"), "YMLU5506443")
        for raw in ("4.2E7", "42000000.0", " 42000000 ", 42000000):
            self.assertEqual(normalize.container_key(raw), "42000000")
        self.assertEqual(normalize.container_key("0042"), "0042")

    def test_every_matcher_uses_the_same_code_rule(self):
        for raw in ("YMLU5506443-mã chưa up", "ymlu 5506443", "YMLU5506443"):
            self.assertEqual({price_key(raw), queue_key(raw), month_report.container_key(raw), source_match.container_key(raw)},
                             {"YMLU5506443"}, raw)
        self.assertEqual(month_report.container_key("FAKE-C"), "FAKEC")   # bản booking vẫn bỏ dấu, như trước


class SheetMatchTests(unittest.TestCase):
    """Ca thật 16/11/2026: ô `YMLU5506443-mã chưa up` (tab đã tính tiền) không khớp container, dòng nguồn cùng container hiện là chuyến mới."""

    def row(self, container, source_row=8):
        return {"source_row": source_row, "customer_id": 7, "container": container, "event_date": "2026-10-24", "carrier": "COSCO",
                "shipper": "KHOI PHONG", "origin": "A", "destination": "B", "review_status": "NEEDS_PRICE"}

    def test_clean_source_row_matches_the_web_row_whose_cell_carries_a_note(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [self.row("YMLU5506443")]}
        ledger = {"customer_id": 7, "trips": [], "legacy_rows": [{"id": 5, "kind": "trip", "current": {
            "container": "YMLU5506443-mã chưa up", "event_date": "2026-10-24", "carrier": "COSCO", "shipper": "KHOI PHONG",
            "origin": "A", "destination": "B", "month": "2026-10-01"}}]}
        self.assertEqual(project_customer(queue, ledger)["items"], [])   # không còn là NEW

    def test_the_same_rows_with_different_codes_are_still_new(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [self.row("YMLU5506443")]}
        ledger = {"customer_id": 7, "trips": [], "legacy_rows": [{"id": 5, "kind": "trip", "current": {
            "container": "YMLU5506444-mã chưa up", "event_date": "2026-10-24", "month": "2026-10-01"}}]}
        self.assertEqual([i["sync_state"] for i in project_customer(queue, ledger)["items"]], ["NEW"])


class ExistingValuesTests(unittest.TestCase):
    def test_empty_web_text_reaches_sql_as_none(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [{
            "source_row": 8, "customer_id": 7, "container": "ABC1", "event_date": "2026-10-24",
            "carrier": "COSCO", "shipper": "KHOI PHONG", "origin": "A", "destination": "B", "review_status": "NEEDS_PRICE"}]}
        for shipper in ("", "   ", None):
            with self.subTest(shipper=shipper):
                ledger = {"customer_id": 7, "trips": [{"id": 9, "container": "ABC1", "source_ref": f"sheet:{'a' * 64}:8",
                    "event_date": "2026-10-24", "carrier": "COSCO", "shipper": shipper, "origin": "A", "destination": "B"}],
                    "legacy_rows": []}
                conflict = project_customer(queue, ledger)["items"][0]
                self.assertEqual((conflict["changed_fields"], conflict["existing_values"]), (["shipper"], {"shipper": None}))

    def test_legacy_row_without_shipper_shows_its_carrier(self):
        queue = {"snapshot_sha256": "a" * 64, "items": [{
            "source_row": 8, "customer_id": 7, "container": "ABC1", "event_date": "2026-10-24",
            "carrier": "COSCO", "shipper": "KHOI PHONG", "origin": "A", "destination": "B", "review_status": "NEEDS_PRICE"}]}
        ledger = {"customer_id": 7, "trips": [], "legacy_rows": [{"id": 5, "kind": "trip", "current": {
            "container": "ABC1", "event_date": "2026-10-24", "carrier": "HT", "shipper": " ", "origin": "A", "destination": "B",
            "month": "2026-10-01"}}]}
        conflict = project_customer(queue, ledger)["items"][0]
        self.assertEqual(conflict["existing_values"], {"shipper": "HT"})


if __name__ == "__main__":
    unittest.main()
