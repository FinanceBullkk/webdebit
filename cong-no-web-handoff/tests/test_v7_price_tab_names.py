"""Tab names and number cells read differently by the .xlsx download and the Sheets API.

Audit 29/10/2026: the download drops "/" and "'" from tab names and writes a number typed in the
container cell as "4.2E7"; the API keeps the name and returns 42000000. Books were named from the
download, the price runner reads the API. Fake names and fake containers only.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
import v7_load_real_copy as loader  # noqa: E402
import v7_price_match as match  # noqa: E402
import v7_sheets_api_reader as reader  # noqa: E402
from v7_price_queue import container_key, name_key, owners, project_prices  # noqa: E402

TAB_API, TAB_XLSX = "KHACH GIA A/B", "KHACH GIA AB"
QUOTE_API, QUOTE_XLSX = "KHACH'S GIA", "KHACHS GIA"
HEADERS = ["Marks & Nos", "CONTAINER NO", "DATE", "UNIT PRICE", "OTHER FEE", "TOTAL(VND)", "NGAY TT(STK)",
           "SỐ ĐÃ ỨNG TRƯỚC/ĐÃ THU TRONG THÁNG", "SỐ CÒN PHẢI THU CUỐI THÁNG"]
DATE_SERIAL = 46298   # 03/10/2026


def api_values(container):
    """values:batchGet with UNFORMATTED_VALUE: numbers stay numbers."""
    return [["THÁNG 10/2026"], HEADERS, ["1", container, DATE_SERIAL, 32500000, "", 32500000, "", "", 32500000],
            ["SỐ DƯ ĐẦU", 0]]


def download_rows(container_text):
    """What workbook_rows yields from the download: raw cell text, numbers as Google writes them."""
    return [(1, {"A": "THÁNG 10/2026"}), (2, {loader.col_name(n): h for n, h in enumerate(HEADERS, 1)}),
            (3, {"A": "1", "B": container_text, "C": str(DATE_SERIAL), "D": "32500000", "F": "32500000",
                 "I": "32500000"}),
            (4, {"A": "SỐ DƯ ĐẦU", "B": "0"})]


def book(container):
    return {"customer_id": 7, "version": 3, "status": "active", "today_month": "2026-10-01",
            "month_locks": [{"month": "2026-10-01", "locked": False}], "trips": [],
            "legacy_rows": [{"id": 21, "kind": "trip", "month": "2026-10-01", "current": {
                "container": container, "event_date": "2026-10-03", "unit_price_vnd": None, "other_fee_vnd": None,
                "counted_vnd": "0", "month": "2026-10-01", "deleted": False}}]}


class TabNameTest(unittest.TestCase):
    def test_download_and_api_give_the_same_rows_but_keep_the_sheet_name(self):
        from_download = match.rows_from_scan(loader.scan_tabs([(TAB_XLSX, download_rows("4.2E7"))]))
        from_api = match.rows_from_scan(loader.scan_tabs([(TAB_API, reader.grid_rows(api_values(42000000)))]))
        self.assertEqual([r["container"] for r in from_download], ["42000000"])
        self.assertEqual([r | {"customer_tab": ""} for r in from_api], [r | {"customer_tab": ""} for r in from_download])
        self.assertEqual([r["customer_tab"] for r in from_api], [TAB_API])
        self.assertEqual(name_key(TAB_API), name_key(TAB_XLSX))

    def test_book_named_from_download_gets_its_api_tab_prices(self):
        rows = match.rows_from_scan(loader.scan_tabs([(TAB_API, reader.grid_rows(api_values(42000000)))]))
        snapshot = {"sha256": "a" * 64, "rows": rows, "row_count": len(rows)}
        customers = [{"id": 7, "name": TAB_XLSX}, {"id": 8, "name": QUOTE_XLSX}]
        result = project_prices(snapshot, book("4.2E7"), customers)
        self.assertEqual([(r["customer_tab"], r["target_kind"], r["target_id"], r["sheet_unit_price_vnd"])
                          for r in result["ready"]], [(TAB_API, "legacy", 21, "32500000")])
        report = match.match(rows, {TAB_XLSX: book("4.2E7")})
        self.assertEqual([(r["status"], r["customer_basis"]) for r in report], [("READY", "name")])

    def test_dropped_characters_and_spacing_compare_alike(self):
        self.assertEqual(name_key(" KHACH  GIA A/B"), TAB_XLSX)
        self.assertEqual(name_key(QUOTE_API), QUOTE_XLSX)
        self.assertNotEqual(name_key("KHACH GIA A"), name_key("KHACH GIA B"))
        owned = owners([{"key": 7, "name": TAB_XLSX}, {"key": 8, "name": QUOTE_XLSX, "aliases": ["KHACH CU/MOI"]}])
        self.assertEqual((owned[name_key(TAB_API)], owned[name_key(QUOTE_API)]), ((7, "name"), (8, "name")))
        self.assertEqual(owned[name_key("KHACH CUMOI")], (8, "alias"))

    def test_two_books_with_the_same_key_get_no_tab(self):
        owned = owners([{"key": 7, "name": TAB_API}, {"key": 9, "name": TAB_XLSX},
                        {"key": 8, "name": "KHACH KHAC", "aliases": [TAB_XLSX]}])
        self.assertNotIn(name_key(TAB_API), owned)
        self.assertEqual(owned[name_key("KHACH KHAC")], (8, "name"))

    def test_number_typed_as_container_reads_the_same(self):
        for raw in ("4.2E7", "4.2e+07", "42000000.0", "42000000", " 42000000 ", 42000000, 4.2e7):
            with self.subTest(raw=raw):
                self.assertEqual(container_key(raw), "42000000")
        for raw, key in (("0042", "0042"), ("1.5", "1.5"), ("fakeu 0000001", "FAKEU0000001"), ("4.2E7X", "4.2E7X"),
                         ("1E999", "1E999"), (None, "")):
            with self.subTest(raw=raw):
                self.assertEqual(container_key(raw), key)


if __name__ == "__main__":
    unittest.main()
