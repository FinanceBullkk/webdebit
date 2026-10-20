"""Synthetic-only XLSX/CSV checks. No captures, Docker, or external packages."""

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from collections import Counter
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_load_real_copy as loader
import v7_reconcile_real_copy as reconciler

FAKE_NAME = "FAKE PRIVATE CUSTOMER ZXQ"
FAKE_AMOUNT = 876543219
M = loader.NS["m"]
R = loader.NS["r"]


def csv_file(folder, name, fields, records):
    with (folder / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def column(n):
    result = ""
    while n:
        n, digit = divmod(n - 1, 26)
        result = chr(65 + digit) + result
    return result


def fixture(folder, *, shift=0, months=None, missing_price=False, receipt="",
            receipt_date="", omit_csv=False, bucket_delta=0, shared=False,
            name=FAKE_NAME, extra_tab=False, opening_anchor=True):
    months = months or [("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT)]
    headers = ["Marks & Nos", "CONTAINER NO", "DATE", "UNIT PRICE", "OTHER FEE",
               "TOTAL(VND)", "NGAY TT(STK)", "SỐ ĐÃ ỨNG TRƯỚC/ĐÃ THU TRONG THÁNG",
               "SỐ CÒN PHẢI THU CUỐI THÁNG"]
    sheet = ET.Element(f"{{{M}}}worksheet")
    data = ET.SubElement(sheet, f"{{{M}}}sheetData")
    strings = []

    def row(number, values):
        element = ET.SubElement(data, f"{{{M}}}row", r=str(number))
        for index, value in enumerate(values, 1):
            if value == "":
                continue
            cell = ET.SubElement(element, f"{{{M}}}c", r=column(index + shift) + str(number))
            if isinstance(value, int):
                ET.SubElement(cell, f"{{{M}}}v").text = str(value)
            elif shared:
                cell.set("t", "s")
                strings.append(value)
                ET.SubElement(cell, f"{{{M}}}v").text = str(len(strings) - 1)
            else:
                cell.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(cell, f"{{{M}}}is"), f"{{{M}}}t").text = value

    trips, payments, periods = [], [], []
    running = 0
    for index, (month, dt, amount, anchor) in enumerate(months):
        base = index * 10 + 1
        year, mon = month.split("-")
        row(base, [f"THÁNG {int(mon)}/{year}"])
        row(base + 1, headers)
        price = "" if missing_price else str(amount)
        row(base + 2, ["1", "FAKE-CONT-XY", dt, price, "", amount,
                       receipt_date, receipt, anchor])
        trips.append({"tab": name, "block": str(index + 1), "row": str(base + 2),
                      "container": "FAKE-CONT-XY", "date_iso": "2026-03-10",
                      "date_mode": "fake", "unit_price": price, "total_cell": str(amount), "flags": ""})
        if receipt_date or receipt:
            payments.append({"tab": name, "block": str(index + 1), "row": str(base + 2),
                             "container": "", "note": "FAKE PRIVATE NOTE", "kind": "receipt",
                             "amount_vnd": receipt})
        if opening_anchor:
            row(base + 3, ["SỐ DƯ ĐẦU", running])
        # The Sheet's own TOTAL cell counts toward its month-end balance, priced or not.
        charge = amount if amount != "" else 0
        running += charge
        if receipt:
            running -= int(receipt)
        periods.append({"customer": name, "debt_period": month,
                        "balance_vnd": str(charge - (int(receipt) if receipt else 0)
                                           + (bucket_delta if index == 0 else 0))})
    final = months[-1][3]
    csv_file(folder, "trips_so_goc.csv", list(trips[0]), [] if omit_csv else trips)
    csv_file(folder, "payments_so_goc.csv", ["tab", "block", "row", "container", "note", "kind", "amount_vnd"], payments)
    csv_file(folder, "opening_final_so_goc.csv", ["tab", "target_balance_vnd", "flags", "delta_vs_db"],
             [{"tab": name, "target_balance_vnd": str(final), "flags": "NO_BASELINE", "delta_vs_db": "600"}])
    csv_file(folder, "opening_by_period_so_goc.csv", ["customer", "debt_period", "balance_vnd"], periods)
    csv_file(folder, "v7-reconcile-customer.csv", ["customer", "source_anchor_vnd"],
             [{"customer": name, "source_anchor_vnd": str(final)}])
    csv_file(folder, "v7-reconcile-period.csv", ["customer", "period", "source_vnd"],
             [{"customer": name, "period": m, "source_vnd": str(a)} for m, _, a, _ in months])
    workbook = ET.Element(f"{{{M}}}workbook")
    sheets = ET.SubElement(workbook, f"{{{M}}}sheets")
    ET.SubElement(sheets, f"{{{M}}}sheet", name=name, attrib={f"{{{R}}}id": "rId1"})
    if extra_tab:
        ET.SubElement(sheets, f"{{{M}}}sheet", name="FAKE OMITTED TAB", attrib={f"{{{R}}}id": "rId2"})
    rels = ET.Element("Relationships")
    ET.SubElement(rels, "Relationship", Id="rId1", Target="worksheets/sheet1.xml")
    if extra_tab:
        ET.SubElement(rels, "Relationship", Id="rId2", Target="/xl/worksheets/sheet2.xml")
    with zipfile.ZipFile(folder / "source-google-export.xlsx", "w") as book:
        book.writestr("xl/workbook.xml", ET.tostring(workbook))
        book.writestr("xl/_rels/workbook.xml.rels", ET.tostring(rels))
        book.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet))
        if extra_tab:
            book.writestr("xl/worksheets/sheet2.xml", ET.tostring(sheet))
        if shared:
            root = ET.Element(f"{{{M}}}sst")
            for value in strings:
                ET.SubElement(ET.SubElement(root, f"{{{M}}}si"), f"{{{M}}}t").text = value
            book.writestr("xl/sharedStrings.xml", ET.tostring(root))


REAL_HEADERS = ["Marks \n& Nos", "CONTAINER NO", "", "DATE", "FROM", "TO", "OTHER FEE",
                "OTHER FEE\n码头插电费\\", "OTHER FEE\n押车", "UNIT PRICE", "TOTAL(VND)", "NGAY TT(STK)",
                "SỐ ĐÃ ỨNG TRƯỚC/ĐÃ THU TRONG THÁNG {m}", "SỐ CÒN PHẢI THU CUỐI THÁNG {m}", "TỔNG THU T9"]


def real_layout_fixture(folder, name=FAKE_NAME):
    """Fake values in the layout seen by tools/v7_profile_xlsx.py on the 20/10 export."""
    sheet = ET.Element(f"{{{M}}}worksheet")
    data = ET.SubElement(sheet, f"{{{M}}}sheetData")

    def row(number, values, shift=0):
        element = ET.SubElement(data, f"{{{M}}}row", r=str(number))
        for index, value in enumerate(values, 1):
            if value == "":
                continue
            cell = ET.SubElement(element, f"{{{M}}}c", r=column(index + shift) + str(number))
            if isinstance(value, int):
                ET.SubElement(cell, f"{{{M}}}v").text = str(value)
            else:
                cell.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(cell, f"{{{M}}}is"), f"{{{M}}}t").text = value

    pad = lambda **cols: [cols.get(column(i), "") for i in range(1, 16)]
    row(1, ["SỔ CHI TIẾT THEO DÕI CÔNG NỢ  PHẢI THU THÁNG 9.2026"])
    row(2, [h.format(m="9.2026") for h in REAL_HEADERS])
    row(3, pad(A="SỐ DƯ THÁNG  CHUYỂN SANG", N=1000))
    row(4, pad(A="1", B="FAKE-CONT-A1", C="FAKE-LINE", D="05/09/2026", E="FAKE-FROM", F="FAKE-TO",
               G=100, H=0, J=200, K=300, L="da tt"))
    # Descriptive cells typed one column left of the header (seen on a real tab).
    row(5, pad(A="2", B="FAKE-CONT-A2", C="7/9/2026", D="FAKE-FROM-2", E="FAKE-TO-2",
               J=200, K=200, L="10/9/2026 TT", M=500))
    row(6, pad(A=2, B="TỔNG", K=500, M=500, N=1000))
    row(7, pad(A="CÒN LẠI", K=999, N=999))
    # Second block: comma title and one extra label column (the CSV extractor bug case).
    row(10, ["SỔ CHI TIẾT THEO DÕI CÔNG NỢ  PHẢI THU THÁNG10,2026"])
    row(11, [h.format(m="") for h in REAL_HEADERS], shift=1)
    row(12, pad(A="1", B="FAKE-CONT-B1", D="02/10/2026", K=400), shift=1)
    row(13, pad(K=0), shift=1)  # template row: TOTAL formula only
    row(14, pad(A=1, K=400, N=1400), shift=1)  # totals row without a TỔNG label
    trips = [{"tab": name, "block": "1", "row": "4", "container": "FAKE-CONT-A1", "date_iso": "",
              "date_mode": "fake", "unit_price": "300", "total_cell": "300", "flags": ""},
             {"tab": name, "block": "1", "row": "5", "container": "FAKE-CONT-A2", "date_iso": "",
              "date_mode": "fake", "unit_price": "200", "total_cell": "200", "flags": ""}]
    csv_file(folder, "trips_so_goc.csv", list(trips[0]), trips)
    csv_file(folder, "payments_so_goc.csv", ["tab", "block", "row", "container", "note", "kind", "amount_vnd"],
             [{"tab": name, "block": "1", "row": "5", "container": "", "note": "", "kind": "receipt",
               "amount_vnd": "500"}])
    csv_file(folder, "opening_final_so_goc.csv", ["tab", "target_balance_vnd", "flags", "delta_vs_db"],
             [{"tab": name, "target_balance_vnd": "1400", "flags": "", "delta_vs_db": ""}])
    csv_file(folder, "opening_by_period_so_goc.csv", ["customer", "debt_period", "balance_vnd"],
             [{"customer": name, "debt_period": "2026-09", "balance_vnd": "1000"},
              {"customer": name, "debt_period": "2026-10", "balance_vnd": "400"}])
    csv_file(folder, "v7-reconcile-customer.csv", ["customer", "source_anchor_vnd"],
             [{"customer": name, "source_anchor_vnd": "1400"}])
    csv_file(folder, "v7-reconcile-period.csv", ["customer", "period", "source_vnd"],
             [{"customer": name, "period": "2026-09", "source_vnd": "1000"}])
    workbook = ET.Element(f"{{{M}}}workbook")
    sheets = ET.SubElement(workbook, f"{{{M}}}sheets")
    ET.SubElement(sheets, f"{{{M}}}sheet", name=name, attrib={f"{{{R}}}id": "rId1"})
    rels = ET.Element("Relationships")
    ET.SubElement(rels, "Relationship", Id="rId1", Target="worksheets/sheet1.xml")
    with zipfile.ZipFile(folder / "source-google-export.xlsx", "w") as book:
        book.writestr("xl/workbook.xml", ET.tostring(workbook))
        book.writestr("xl/_rels/workbook.xml.rels", ET.tostring(rels))
        book.writestr("xl/worksheets/sheet1.xml", ET.tostring(sheet))


class RealLayoutTest(unittest.TestCase):
    def test_real_sheet_layout_loads_with_anchor_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            real_layout_fixture(folder)
            item = loader.source_data(folder)[0][0]
        self.assertEqual(dict(item["reasons"]), {})
        self.assertEqual(item["anchor"], 1400)
        self.assertEqual([c["source_charge_vnd"] for c in item["checks"]], [500, 400])
        self.assertEqual([c["source_receipt_vnd"] for c in item["checks"]], [500, 0])
        self.assertEqual([c["opening_anchor_vnd"] for c in item["checks"]], [1000, 1000])
        self.assertEqual([c["standard_bucket_vnd"] for c in item["checks"]], [1000, 400])
        # "CÒN LẠI" note row after TỔNG is not a trip; "da tt" without amount is not a receipt.
        self.assertEqual(Counter(r["kind"] for r in item["legacy"]), Counter({"trip": 3, "receipt": 1}))
        self.assertEqual(item["flags"]["CSV_MISSING_ROWS"], 1)
        self.assertIn("MISSING_PRICE", item["legacy"][-1]["display"]["flags"])
        self.assertIn("PAYMENT_NOTE", item["legacy"][0]["display"]["flags"])
        # Unlabeled totals row is not a fee + receipt; template 0 rows are skipped.
        self.assertEqual(item["flags"]["UNLABELED_TOTAL_ROW"], 1)
        first, shifted = item["legacy"][0]["display"], item["legacy"][1]["display"]
        self.assertEqual((first["stt"], first["carrier"], first["from"], first["to"], first["fee_vnd"],
                          first["unit_price"]), ("1", "FAKE-LINE", "FAKE-FROM", "FAKE-TO", "100", "200"))
        self.assertEqual((shifted["date"], shifted["carrier"], shifted["from"], shifted["to"]),
                         ("2026-09-07", "", "FAKE-FROM-2", "FAKE-TO-2"))
        self.assertIn("COLUMN_SHIFTED", shifted["flags"])


class LayoutVariantTest(unittest.TestCase):
    def build(self, folder, extra_rows, first_rows=(), scan=False):
        """Patch the fixture: a cell value of None deletes the cell, "=" is a formula with no
        cached value, first_rows go before every other row (document order is what the reader sees)."""
        real_layout_fixture(folder)
        path = folder / "source-google-export.xlsx"
        with zipfile.ZipFile(path) as book:
            entries = {name: book.read(name) for name in book.namelist()}
        sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
        data = sheet.find("m:sheetData", loader.NS)
        rows = {int(r.get("r")): r for r in data}

        def put(row, number, cells):
            for col, value in cells.items():
                ref = f"{col}{number}"
                for old in [c for c in row if c.get("r") == ref]:
                    row.remove(old)
                if value is None:
                    continue
                cell = ET.SubElement(row, f"{{{M}}}c", r=ref)
                if value == "=s":
                    cell.set("t", "str")  # formula whose cached result is an empty string
                    ET.SubElement(cell, f"{{{M}}}f").text = "1+1"
                    ET.SubElement(cell, f"{{{M}}}v").text = ""
                elif value == "=":
                    ET.SubElement(cell, f"{{{M}}}f").text = "1+1"
                elif isinstance(value, int):
                    ET.SubElement(cell, f"{{{M}}}v").text = str(value)
                else:
                    cell.set("t", "inlineStr")
                    ET.SubElement(ET.SubElement(cell, f"{{{M}}}is"), f"{{{M}}}t").text = value

        for index, (number, cells) in enumerate(first_rows):
            row = ET.Element(f"{{{M}}}row", r=str(number))
            data.insert(index, row)
            put(row, number, cells)
        for number, cells in extra_rows:
            row = rows.get(number)
            if row is None:
                row = ET.SubElement(data, f"{{{M}}}row", r=str(number))
            put(row, number, cells)
        entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
        with zipfile.ZipFile(path, "w") as book:
            for name, content in entries.items():
                book.writestr(name, content)
        if scan:
            return loader.scan_workbook(path)[FAKE_NAME]
        return loader.source_data(folder)[0][0]

    def test_side_table_month_text_does_not_open_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(4, {"X": "THÁNG 09/2026"}), (5, {"X": "THÁNG 09/2026"})])
        self.assertNotIn("DUPLICATE_MONTH_BLOCK", item["reasons"])
        self.assertFalse(item["reasons"])

    def test_second_table_to_the_right_does_not_steal_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(2, {"U": "CONTAINER NO.", "W": "TOTAL (VND)"}),
                                           (4, {"U": "FAKE-OTHER", "W": 1}),
                                           (5, {"U": "FAKE-OTHER-2", "W": 2})])
        self.assertFalse(item["reasons"])
        self.assertEqual([c["source_charge_vnd"] for c in item["checks"]], [500, 400])

    def test_text_price_with_numeric_total_is_flag_not_hold(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(4, {"J": "CHƯA CÓ GIÁ"})])
        self.assertFalse(item["reasons"])
        self.assertIn("MISSING_PRICE", item["legacy"][0]["display"]["flags"])
        self.assertEqual(item["legacy"][0]["source_total_vnd"], 300)

    TITLE = "SỔ CHI TIẾT THEO DÕI CÔNG NỢ  PHẢI THU THÁNG "
    FAKE_HEADER = {column(i): h.format(m="") for i, h in enumerate(REAL_HEADERS, 1) if h}

    def test_stray_separators_in_month_title(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(1, {"A": self.TITLE + "9\\.2026"})])
        self.assertFalse(item["reasons"])
        self.assertEqual([c["debt_month"] for c in item["checks"]], ["2026-09-01", "2026-10-01"])

    def test_mistyped_title_reads_month_from_trip_dates_only_when_digits_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(10, {"A": self.TITLE + "10.206"}), (12, {"E": "22/10/2026"})])
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["TITLE_MONTH_FROM_DATES"], 1)
        self.assertEqual([c["debt_month"] for c in item["checks"]], ["2026-09-01", "2026-10-01"])
        # The typed digits ("7") do not contain the month the dates give (10): stay unreadable.
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(10, {"A": self.TITLE + "7.206"}), (12, {"E": "22/10/2026"})])
        self.assertIn("LAYOUT_BAD_MONTH_TITLE", item["reasons"])
        self.assertIn("LAYOUT_HEADER_MISSING_BLOCK", item["reasons"])
        self.assertNotIn("TITLE_MONTH_FROM_DATES", item["flags"])

    def test_header_of_side_table_on_a_trip_row_keeps_main_columns_and_the_row(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(4, {"U": "CONTAINER NO.", "W": "TOTAL (VND)", "V": "UNIT PRICE"})])
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["SIDE_TABLE_HEADER_IGNORED"], 1)
        self.assertEqual([c["source_charge_vnd"] for c in item["checks"]], [500, 400])
        self.assertEqual(Counter(r["kind"] for r in item["legacy"]), Counter(trip=3, receipt=1))

    def test_empty_block_without_title_is_dropped_but_filled_one_holds(self):
        untitled = [(101, {"A": "Khách Hàng: FAKE"}), (102, self.FAKE_HEADER),
                    (103, {"A": "SỐ DƯ THÁNG CHUYỂN SANG"}), (104, {"K": 0}),
                    (105, {"A": 0, "B": "TỔNG", "K": 0, "M": 0, "N": 0})]
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [], first_rows=untitled)
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["UNTITLED_EMPTY_BLOCK"], 1)
        filled = untitled[:3] + [(104, {"A": "1", "B": "FAKE-CONT-U1", "D": "01/09/2026", "J": 5, "K": 5}),
                                 untitled[4]]
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [], first_rows=filled)
        self.assertIn("LAYOUT_HEADER_MISSING_BLOCK", item["reasons"])

    def copy_of_first_block(self, amount=500):
        return [(20, {"A": self.TITLE + "9.2026"}), (21, self.FAKE_HEADER),
                (22, {"A": "SỐ DƯ THÁNG  CHUYỂN SANG", "N": 1000}),
                (23, {"A": "1", "B": "FAKE-CONT-A1", "C": "FAKE-LINE", "D": "05/09/2026", "E": "FAKE-FROM",
                      "F": "FAKE-TO", "G": 100, "H": 0, "J": 200, "K": 300, "L": "da tt"}),
                (24, {"A": "2", "B": "FAKE-CONT-A2", "C": "7/9/2026", "D": "FAKE-FROM-2", "E": "FAKE-TO-2",
                      "J": 200, "K": amount - 300, "L": "10/9/2026 TT", "M": 500}),
                (25, {"A": 2, "B": "TỔNG", "K": amount, "M": 500, "N": 1000})]

    def test_identical_repeated_block_is_ignored_but_a_different_one_holds(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), self.copy_of_first_block())
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["DUPLICATE_BLOCK_IDENTICAL"], 1)
        self.assertEqual([c["source_charge_vnd"] for c in item["checks"]], [500, 400])
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), self.copy_of_first_block(amount=501))
        self.assertIn("DUPLICATE_MONTH_BLOCK", item["reasons"])

    def test_bare_price_row_is_a_note_but_priced_total_still_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(13, {"L": None, "K": 15})])
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["PRICE_ONLY_ROW_IGNORED"], 1)
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(13, {"K": 15, "L": 15})])
        self.assertIn("ANCHOR_CHAIN_MISMATCH", item["reasons"])
        self.assertNotIn("PRICE_ONLY_ROW_IGNORED", item["flags"])

    def test_negative_credit_line_without_container_only(self):
        with tempfile.TemporaryDirectory() as temp:
            tab = self.build(Path(temp), [(13, {"K": -50, "L": -50})], scan=True)
        self.assertNotIn("INVALID_TRIP_AMOUNT", tab["issues"])
        credit = [r for r in tab["records"] if r["row"] == 13][0]
        self.assertEqual(credit["amount"], -50)
        self.assertIn("NEGATIVE_CREDIT_ROW", credit["flags"])
        with tempfile.TemporaryDirectory() as temp:
            tab = self.build(Path(temp), [(13, {"C": "FAKE-CONT-NEG", "K": -50, "L": -50})], scan=True)
        self.assertEqual(tab["issues"]["INVALID_TRIP_AMOUNT"], 1)

    def test_unreadable_receipt_names_its_cause_and_still_holds(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(5, {"M": "12.5"})])
        self.assertIn("NON_INTEGER_AMOUNT", item["reasons"])
        self.assertIn("MISSING_RECEIPT_AMOUNT", item["reasons"])
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(5, {"M": "="})])
        self.assertIn("FORMULA_CACHE_MISSING", item["reasons"])
        self.assertIn("MISSING_RECEIPT_AMOUNT", item["reasons"])
        self.assertIsNone(item["checks"][0]["source_receipt_vnd"])

    def test_formula_with_cached_blank_is_blank_but_formula_without_cache_is_not(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(4, {"M": "=s"})])
        self.assertFalse(item["reasons"])
        self.assertEqual(Counter(r["kind"] for r in item["legacy"]), Counter(trip=3, receipt=1))
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(4, {"M": "="})])
        self.assertIn("FORMULA_CACHE_MISSING", item["reasons"])

    def year_end(self, carry, end, buckets, title="1.2026"):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            self.build(folder, [(1, {"A": self.TITLE + "12.2025"}), (10, {"A": self.TITLE + title}),
                                (13, {"L": None, "B": "SỐ DƯ THÁNG CHUYỂN SANG", "O": carry}), (14, {"O": end})])
            csv_file(folder, "opening_by_period_so_goc.csv", ["customer", "debt_period", "balance_vnd"],
                     [{"customer": FAKE_NAME, "debt_period": month, "balance_vnd": str(amount)}
                      for month, amount in buckets])
            csv_file(folder, "opening_final_so_goc.csv", ["tab", "target_balance_vnd", "flags", "delta_vs_db"],
                     [{"tab": FAKE_NAME, "target_balance_vnd": str(end), "flags": "", "delta_vs_db": ""}])
            return loader.source_data(folder)[0][0]

    def test_january_carry_gap_is_one_visible_adjustment_and_other_months_still_hold(self):
        # December ends at 1000; the January carry typed in the Sheet is 800: 200 was paid but
        # not yet in the detail book. FIFO takes it from the oldest debt.
        item = self.year_end(800, 1200, [("2025-12", 800), ("2026-01", 400)])
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["YEAR_END_CARRY_ADJUSTED"], 1)
        self.assertEqual([(c["source_charge_vnd"], c["source_receipt_vnd"]) for c in item["checks"]],
                         [(500, 500), (400, 200)])
        adjustment = [r for r in item["legacy"] if r["source_tab"].endswith(":year-end-carry")]
        self.assertEqual([(r["kind"], r["source_total_vnd"], r["debt_month"]) for r in adjustment],
                         [("receipt", 200, "2026-01-01")])
        # Carry above the previous end: the surplus is a charge.
        item = self.year_end(1300, 1700, [("2025-12", 1000), ("2026-01", 700)])
        self.assertFalse(item["reasons"])
        self.assertEqual([(c["source_charge_vnd"], c["source_receipt_vnd"]) for c in item["checks"]][1], (700, 0))
        # Same gap in any other month is still a broken chain; the adjustment must also close.
        item = self.year_end(800, 1200, [("2026-09", 800), ("2026-10", 400)], title="10.2026")
        self.assertIn("ANCHOR_CHAIN_MISMATCH", item["reasons"])
        item = self.year_end(800, 1199, [("2025-12", 800), ("2026-01", 400)])
        self.assertIn("ANCHOR_CHAIN_MISMATCH", item["reasons"])

    def test_total_row_sum_is_spread_over_unpriced_trips(self):
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), [(12, {"L": None}), (13, {"C": "FAKE-CONT-B2"}), (14, {"C": "TỔNG"})])
        self.assertFalse(item["reasons"])
        spread = sorted((r["source_row"], r["source_total_vnd"]) for r in item["legacy"] if r["source_row"] in (12, 13))
        self.assertEqual(spread, [(12, 200), (13, 200)])
        self.assertEqual([c["source_charge_vnd"] for c in item["checks"]], [500, 400])
        block = {"total_row_total": 10, "records": [
            {"kind": "trip", "container": "X", "price": "", "amount": None, "flags": set()} for _ in range(3)]}
        loader.spread_total_over_trips(block)
        self.assertEqual([r["spread"] for r in block["records"]], [4, 3, 3])
        # Nothing to spread when rows already add up or a trip is priced.
        block = {"total_row_total": 10, "records": [
            {"kind": "trip", "container": "X", "price": "5", "amount": 10, "flags": set()}]}
        loader.spread_total_over_trips(block)
        self.assertNotIn("spread", block["records"][0])

    def test_repeated_title_with_later_dates_is_that_later_month_but_a_copy_is_not(self):
        rows = self.copy_of_first_block()
        rows[3][1]["D"] = "15/11/2026"
        rows[4][1]["C"] = "20/11/2026"
        with tempfile.TemporaryDirectory() as temp:
            item = self.build(Path(temp), rows)
        self.assertNotIn("DUPLICATE_MONTH_BLOCK", item["reasons"])
        self.assertIn("2026-11-01", [c["debt_month"] for c in item["checks"]])
        self.assertEqual(item["flags"]["TITLE_MONTH_FROM_DATES"], 1)

    def test_csv_trip_row_equal_to_unlabeled_total_row_is_extractor_noise(self):
        row = {"tab": FAKE_NAME, "block": "2", "row": "14", "container": "", "date_iso": "",
               "date_mode": "fake", "unit_price": "", "total_cell": "400", "flags": ""}
        for amount, held in (("400", False), ("401", True)):
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                real_layout_fixture(folder)
                trips = loader.rows(folder, "trips_so_goc.csv")
                csv_file(folder, "trips_so_goc.csv", list(row), trips + [dict(row, total_cell=amount)])
                item = loader.source_data(folder)[0][0]
            self.assertEqual("SOURCE_ROW_MISMATCH" in item["reasons"], held)
            if not held:
                self.assertEqual(item["flags"]["CSV_COUNTED_TOTAL_ROW"], 1)
                self.assertEqual(item["csv_only"], [])

    def test_header_keeps_total_column_with_a_note_typed_in_it(self):
        self.assertEqual(loader.header_key("TOTAL VND DU"), "total")
        self.assertEqual(loader.header_key(loader.normalized("TOTAL(VND)")), "total")
        self.assertIsNone(loader.header_key(loader.normalized("TOTAL (USD)")))
        self.assertEqual(loader.header_key("PACKING"), "date")

    def test_unlabeled_carry_row_above_first_trip(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            real_layout_fixture(folder)
            # Replace the labeled carry row 3 with only the amount in the balance column.
            path = folder / "source-google-export.xlsx"
            with zipfile.ZipFile(path) as book:
                entries = {name: book.read(name) for name in book.namelist()}
            sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
            row3 = sheet.find(".//m:row[@r='3']", loader.NS)
            for cell in list(row3):
                if cell.get("r") == "A3":
                    row3.remove(cell)
            entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
            with zipfile.ZipFile(path, "w") as book:
                for name, content in entries.items():
                    book.writestr(name, content)
            item = loader.source_data(folder)[0][0]
        self.assertFalse(item["reasons"])
        self.assertEqual(item["checks"][0]["opening_anchor_vnd"], 1000)
        self.assertEqual(item["flags"]["CARRY_ROW_UNLABELED"], 1)


class OutOfBlockDateTest(unittest.TestCase):
    def test_out_of_block_serial_follows_tab_majority_single_reading(self):
        serial = lambda d: str((d - date(1899, 12, 30)).days) + ".0"
        def rec(raw, dt=None, flags=()):
            return {"kind": "trip", "raw_date": raw, "date": dt, "flags": set(flags)}
        # Tab leans swapped: two in-block rows needed DATE_SWAPPED, one did not.
        rows = [rec(serial(date(2026, 1, 8)), "2026-08-01", {"DATE_SWAPPED"}),
                rec(serial(date(2026, 2, 8)), "2026-08-02", {"DATE_SWAPPED"}),
                rec(serial(date(2026, 8, 20)), "2026-08-20"),
                rec(serial(date(2026, 3, 9))),          # fits neither reading of its block
                rec(serial(date(2026, 1, 28))),         # 28 cannot be a month: stored reading
                rec("da tt")]
        loader.resolve_out_of_block_dates(rows)
        self.assertEqual(rows[3]["date"], "2026-09-03")
        self.assertEqual(rows[4]["date"], "2026-01-28")
        self.assertIsNone(rows[5]["date"])
        self.assertIn("DATE_READING_FROM_TAB", rows[3]["flags"])
        # Tab leans straight: keep the stored reading.
        rows = [rec(serial(date(2026, 8, 20)), "2026-08-20"), rec(serial(date(2026, 3, 9)))]
        loader.resolve_out_of_block_dates(rows)
        self.assertEqual(rows[1]["date"], "2026-03-09")


class RealCopyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def load(self, **options):
        fixture(self.folder, **options)
        return loader.source_data(self.folder)[0]

    def test_shifted_header_inline_and_shared_strings(self):
        for shared in (False, True):
            with self.subTest(shared=shared):
                item = self.load(shift=1, shared=shared)[0]
                self.assertFalse(item["reasons"])
                self.assertEqual(len(item["legacy"]), 1)
                self.assertEqual(item["checks"][0]["source_charge_vnd"], FAKE_AMOUNT)
                self.assertIn("NO_BASELINE", item["checks"][0]["exception_codes"])
                self.assertEqual(item["flags"]["HISTORICAL_DELTA_600"], 1)
                self.assertEqual(item["flags"]["CHUA_PHAN_LOAI"], 1)

    def test_duplicate_trimmed_tab_name_holds_only_that_customer(self):
        fixture(self.folder, extra_tab=True)
        path = self.folder / "source-google-export.xlsx"
        with zipfile.ZipFile(path) as book:
            entries = {name: book.read(name) for name in book.namelist()}
        entries["xl/workbook.xml"] = entries["xl/workbook.xml"].replace(
            b"FAKE OMITTED TAB", (FAKE_NAME + " ").encode())
        with zipfile.ZipFile(path, "w") as book:
            for name, content in entries.items():
                book.writestr(name, content)
        books = loader.source_data(self.folder)[0]
        held = [item for item in books if item["name"] == FAKE_NAME]
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["reasons"]["AMBIGUOUS_SOURCE_TAB"], 1)
        self.assertEqual(held[0]["legacy"], [])

    def test_dates_use_block_and_never_csv_guess(self):
        for value, expected, flag in (("10/03/2026", "2026-10-03", "DATE_SWAPPED"),
                                      ("03/04/2026", None, "DATE_OUT_OF_BLOCK"),
                                      ("03/10/2026", "2026-10-03", None),
                                      ("2026-03-10", "2026-10-03", "DATE_SWAPPED"),
                                      ("", None, "MISSING_DATE")):
            with self.subTest(value=value):
                item = self.load(months=[("2026-10", value, FAKE_AMOUNT, FAKE_AMOUNT)])[0]
                self.assertFalse(item["reasons"])
                display = item["legacy"][0]["display"]
                self.assertEqual(display["date"], expected)
                if flag:
                    self.assertIn(flag, display["flags"])
                    self.assertEqual(item["flags"][flag], 1)
        serial = str((date(2026, 3, 10) - date(1899, 12, 30)).days)
        self.assertEqual(loader.source_date(serial, "2026-10"), ("2026-10-03", {"DATE_SWAPPED"}))

    def test_missing_price_keeps_sheet_total_and_flags(self):
        # V7-MIG: history rows keep the Sheet TOTAL cell; the Sheet's balance already counts it.
        item = self.load(missing_price=True, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT)])[0]
        self.assertFalse(item["reasons"])
        self.assertEqual(item["checks"][0]["source_charge_vnd"], FAKE_AMOUNT)
        self.assertEqual(item["legacy"][0]["source_total_vnd"], FAKE_AMOUNT)
        self.assertIn("MISSING_PRICE", item["legacy"][0]["display"]["flags"])
        # Excluding the cell would contradict the Sheet anchor and must hold the customer.
        held = self.load(missing_price=True, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, 0)])[0]
        self.assertIn("ANCHOR_CHAIN_MISMATCH", held["reasons"])

    def test_missing_price_with_blank_total_is_known_zero_movement_only(self):
        item = self.load(missing_price=True, months=[("2026-10", "03/10/2026", "", 0)])[0]
        self.assertFalse(item["reasons"])
        self.assertIsNone(item["legacy"][0]["source_total_vnd"])
        self.assertEqual(item["checks"][0]["source_charge_vnd"], 0)
        self.assertIn("MISSING_PRICE", item["checks"][0]["exception_codes"])

    def test_formula_without_cached_anchor_quarantines(self):
        fixture(self.folder)
        path = self.folder / "source-google-export.xlsx"
        with zipfile.ZipFile(path) as book:
            entries = {name: book.read(name) for name in book.namelist()}
        sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
        anchor = sheet.find(".//m:c[@r='I3']", loader.NS)
        anchor.clear()
        anchor.set("r", "I3")
        ET.SubElement(anchor, f"{{{M}}}f").text = "SUM(F3)-H3"
        entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
        with zipfile.ZipFile(path, "w") as book:
            for name, content in entries.items():
                book.writestr(name, content)
        reasons = loader.source_data(self.folder)[0][0]["reasons"]
        self.assertIn("MISSING_MONTH_ANCHOR", reasons)
        self.assertIn("NO_ANCHOR", reasons)

    def test_explicit_opening_anchor_and_footer_anchor(self):
        fixture(self.folder)
        path = self.folder / "source-google-export.xlsx"
        with zipfile.ZipFile(path) as book:
            entries = {name: book.read(name) for name in book.namelist()}
        sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
        data = sheet.find("m:sheetData", loader.NS)
        def append_row(n, label, amount):
            row = ET.SubElement(data, f"{{{M}}}row", r=str(n))
            cell = ET.SubElement(row, f"{{{M}}}c", r=f"A{n}", t="inlineStr")
            ET.SubElement(ET.SubElement(cell, f"{{{M}}}is"), f"{{{M}}}t").text = label
            value = ET.SubElement(row, f"{{{M}}}c", r=f"B{n}")
            ET.SubElement(value, f"{{{M}}}v").text = str(amount)
        append_row(5, "SỐ CÒN PHẢI THU CUỐI THÁNG", FAKE_AMOUNT)
        entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
        with zipfile.ZipFile(path, "w") as book:
            for name, content in entries.items():
                book.writestr(name, content)
        item = loader.source_data(self.folder)[0][0]
        self.assertFalse(item["reasons"])
        self.assertEqual(item["checks"][0]["opening_anchor_vnd"], 0)
        # No carry row: 0 is only a hypothesis, accepted when the Sheet month-end agrees...
        item = self.load(opening_anchor=False)[0]
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["OPENING_ROW_ABSENT_AS_ZERO"], 1)
        self.assertEqual(item["checks"][0]["opening_anchor_vnd"], 0)
        # ...and held when the Sheet implies a nonzero carry.
        item = self.load(opening_anchor=False, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT + 5)])[0]
        self.assertIn("ANCHOR_CHAIN_MISMATCH", item["reasons"])

    def test_payment_note_without_amount_is_not_a_receipt(self):
        item = self.load(receipt_date="03/10/2026")[0]
        self.assertNotIn("MISSING_RECEIPT_AMOUNT", item["reasons"])
        self.assertEqual([r["kind"] for r in item["legacy"]], ["trip"])
        self.assertIn("PAYMENT_NOTE", item["legacy"][0]["display"]["flags"])

    def test_missing_receipt_quarantines_whole_customer_before_sql(self):
        fixture(self.folder, receipt_date="03/10/2026")
        path = self.folder / "source-google-export.xlsx"
        with zipfile.ZipFile(path) as book:
            entries = {name: book.read(name) for name in book.namelist()}
        sheet = ET.fromstring(entries["xl/worksheets/sheet1.xml"])
        row3 = sheet.find(".//m:row[@r='3']", loader.NS)
        cell = ET.Element(f"{{{M}}}c", r="H3", t="inlineStr")
        ET.SubElement(ET.SubElement(cell, f"{{{M}}}is"), f"{{{M}}}t").text = "not a number"
        row3.insert(7, cell)
        entries["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
        with zipfile.ZipFile(path, "w") as book:
            for name, content in entries.items():
                book.writestr(name, content)
        item = loader.source_data(self.folder)[0][0]
        self.assertIn("MISSING_RECEIPT_AMOUNT", item["reasons"])
        self.assertIsNone(item["checks"][0]["source_receipt_vnd"])
        self.assertIsNone(item["checks"][0]["standard_bucket_vnd"])
        pg = Mock()
        self.assertEqual(loader.import_one(pg, item, "a" * 64, 1), "held")
        pg.value.assert_not_called()

    def test_raw_tab_choice_resolves_tabs_that_differ_only_in_spaces(self):
        fixture(self.folder, extra_tab=True)
        path = self.folder / "source-google-export.xlsx"
        with zipfile.ZipFile(path) as book:
            entries = {name: book.read(name) for name in book.namelist()}
        spaced = "  " + FAKE_NAME
        entries["xl/workbook.xml"] = entries["xl/workbook.xml"].replace(
            b"FAKE OMITTED TAB", spaced.encode())
        with zipfile.ZipFile(path, "w") as book:
            for name, content in entries.items():
                book.writestr(name, content)
        self.assertIn("AMBIGUOUS_SOURCE_TAB", loader.source_data(self.folder)[0][0]["reasons"])
        for choice in (spaced, FAKE_NAME):
            with self.subTest(choice=choice), patch.object(loader, "PREFERRED_RAW_TABS", (choice,)):
                self.assertFalse(loader.source_data(self.folder)[0][0]["reasons"])

    def test_missing_csv_row_or_customer_is_not_partial_import(self):
        # CSV missing an xlsx row is the known extractor bug: flag, rows still face the chain.
        item = self.load(omit_csv=True)[0]
        self.assertNotIn("SOURCE_ROW_MISMATCH", item["reasons"])
        self.assertEqual(item["flags"]["CSV_MISSING_ROWS"], 1)
        # CSV row the xlsx scan does not have: hold.
        self.load()
        records = loader.rows(self.folder, "trips_so_goc.csv")
        records.append(dict(records[0], row="99"))
        csv_file(self.folder, "trips_so_goc.csv", list(records[0]), records)
        self.assertIn("SOURCE_ROW_MISMATCH", loader.source_data(self.folder)[0][0]["reasons"])
        items = self.load(extra_tab=True)
        self.assertEqual(len(items), 2)
        omitted = next(item for item in items if item["name"] != FAKE_NAME)
        # A tab with no opening/reference rows cannot pass the bucket gates.
        self.assertIn("OPENING_TOTAL_MISMATCH", omitted["reasons"])
        path = self.folder / "source-google-export.xlsx"
        with zipfile.ZipFile(path) as book:
            entries = {name: book.read(name) for name in book.namelist()}
        # Unknown nonempty tab cannot silently vanish from source coverage.
        entries["xl/worksheets/sheet2.xml"] = (
            f'<worksheet xmlns="{M}"><sheetData><row r="1">'
            '<c r="A1" t="inlineStr"><is><t>FAKE UNKNOWN LAYOUT</t></is></c>'
            '</row></sheetData></worksheet>').encode()
        with zipfile.ZipFile(path, "w") as book:
            for name, content in entries.items():
                book.writestr(name, content)
        omitted = next(item for item in loader.source_data(self.folder)[0] if item["name"] != FAKE_NAME)
        self.assertIn("SOURCE_LAYOUT_UNSUPPORTED", omitted["reasons"])

    def test_csv_same_count_different_amount_is_mismatch(self):
        self.load()
        records = loader.rows(self.folder, "trips_so_goc.csv")
        records[0]["total_cell"] = str(FAKE_AMOUNT + 1)
        csv_file(self.folder, "trips_so_goc.csv", list(records[0]), records)
        self.assertIn("SOURCE_ROW_MISMATCH", loader.source_data(self.folder)[0][0]["reasons"])

    def test_bucket_total_and_fifo_gates(self):
        item = self.load(bucket_delta=1)[0]
        self.assertIn("OPENING_TOTAL_MISMATCH", item["reasons"])
        self.assertIn("FIFO_BUCKET_MISMATCH", item["reasons"])
        self.load(months=[("2026-09", "03/09/2026", 100, 100),
                          ("2026-10", "03/10/2026", 200, 300)])
        periods = loader.rows(self.folder, "opening_by_period_so_goc.csv")
        periods[0]["balance_vnd"], periods[1]["balance_vnd"] = "50", "250"
        csv_file(self.folder, "opening_by_period_so_goc.csv", list(periods[0]), periods)
        item = loader.source_data(self.folder)[0][0]
        # Same total, different month split: the Sheet FIFO split is used and recorded.
        self.assertFalse(item["reasons"])
        self.assertEqual(item["flags"]["BUCKETS_FROM_SHEET"], 2)
        self.assertEqual([o["amount_vnd"] for o in item["openings"]], [100, 200])
        self.assertEqual([c["bucket_vnd"] for c in item["checks"]], [100, 200])

    def test_independent_month_anchor_chain(self):
        months = [("2026-09", "03/09/2026", 100, 100), ("2026-10", "03/10/2026", 200, 300)]
        self.assertFalse(self.load(months=months)[0]["reasons"])
        months[1] = ("2026-10", "03/10/2026", 200, 301)
        self.assertIn("ANCHOR_CHAIN_MISMATCH", self.load(months=months)[0]["reasons"])

    def test_fifo_receipts_skip_negative_and_keep_advance(self):
        item = self.load(receipt="50", receipt_date="03/10/2026",
                         months=[("2026-10", "03/10/2026", 100, 50)])[0]
        self.assertFalse(item["reasons"])
        self.assertEqual(item["checks"][0]["standard_bucket_vnd"], 50)
        item = self.load(receipt="150", receipt_date="03/10/2026",
                         months=[("2026-10", "03/10/2026", 100, -50)])[0]
        self.assertFalse(item["reasons"])
        self.assertEqual(item["checks"][0]["standard_bucket_vnd"], -50)

    def test_integer_exactness(self):
        self.assertIsNone(loader.integer("1.1"))
        self.assertIsNone(loader.integer(""))
        self.assertIsNone(loader.integer("NaN"))
        self.assertIsNone(loader.integer(str(2**63)))
        self.assertEqual(loader.integer(str(2**53 + 1)), 2**53 + 1)

    def test_report_privacy_and_check_source_without_docker(self):
        fixture(self.folder, bucket_delta=1)
        output = io.StringIO()
        logdir = self.folder / "logs"
        with patch.object(sys, "argv", ["loader", "--source-dir", str(self.folder), "--check-source"]), \
                patch.object(loader, "LOG_DIR", logdir), patch.object(loader, "run") as docker, \
                patch.object(loader.shutil, "which") as which, redirect_stdout(output):
            self.assertEqual(loader.main(), 2)
            docker.assert_not_called()
            which.assert_not_called()
        result = json.loads(output.getvalue())
        saved = next(logdir.glob("*.json")).read_text(encoding="utf-8")
        self.assertEqual(result, json.loads(saved))
        for text in (output.getvalue(), saved):
            for secret in (FAKE_NAME, str(FAKE_AMOUNT), "FAKE-CONT-XY", "FAKE PRIVATE NOTE"):
                self.assertNotIn(secret, text)
        self.assertEqual(result["held"][0]["ordinal"], 1)
        self.assertEqual(len(result["source_sha256"]), len(loader.FILES))
        self.assertEqual(result["source_notice"], loader.SOURCE_NOTICE)
        self.assertEqual(result["loaded_customers"], 0)

    def test_check_source_subprocess_on_fake_files(self):
        fixture(self.folder)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        process = subprocess.run([sys.executable, str(ROOT / "tools/v7_load_real_copy.py"),
                                  "--source-dir", str(self.folder), "--check-source"],
                                 capture_output=True, text=True, encoding="utf-8", env=env, timeout=20)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["eligible_customers"], 1)
        self.assertEqual(result["held_customers"], 0)
        self.assertNotIn(FAKE_NAME, process.stdout + process.stderr)

    def test_forbidden_port_rejected_before_source_or_docker(self):
        for port in ("8777", "0", "65536"):
            with patch.object(sys, "argv", ["loader", "--port", port]), \
                    patch.object(loader, "source_data") as source, \
                    patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit):
                    loader.main()
                source.assert_not_called()

    def test_runtime_failure_sanitized_and_cleanup_even_with_keep(self):
        fixture(self.folder)
        commands = []
        def fake_run(args, **kwargs):
            commands.append(args)
            if args[:3] == ["docker", "logs", args[-1]]:
                return Mock(stdout="PostgreSQL init process complete; ready for start up.", stderr="")
            if "psql" in args:
                raise RuntimeError(FAKE_NAME + " " + str(FAKE_AMOUNT))
            return Mock(stdout="", stderr="")
        output = io.StringIO()
        with patch.object(sys, "argv", ["loader", "--source-dir", str(self.folder), "--keep"]), \
                patch.object(loader, "run", side_effect=fake_run), \
                patch.object(loader, "Pg"), patch.object(loader.shutil, "which", return_value="fake"), \
                patch.object(loader, "inspect_volume") as volume, \
                patch.object(loader, "inspect_owned", return_value="owned-full-id") as owned, \
                patch.object(loader, "LOG_DIR", self.folder / "logs"), redirect_stdout(output):
            self.assertEqual(loader.main(), 1)
        self.assertNotIn(FAKE_NAME, output.getvalue())
        self.assertNotIn(str(FAKE_AMOUNT), output.getvalue())
        result = json.loads(output.getvalue())
        self.assertEqual(result["reason_counts"], {"IMPORT_ERROR": 1})
        container = "webdebit-v7-real-" + result["run_id"]
        owned.assert_any_call(container, container, result["run_id"], "owned-full-id")
        volume.assert_any_call(container, result["run_id"])
        self.assertIn(["docker", "rm", "--force", "owned-full-id"], commands)
        self.assertIn(["docker", "volume", "rm", container], commands)
        creation = next(args for args in commands if args[:2] == ["docker", "run"])
        self.assertEqual(creation[creation.index("--network") + 1], "none")
        self.assertNotIn("-p", creation)
        self.assertNotIn("--publish", creation)

    def test_http_port_default_and_explicit_are_loopback_only(self):
        fixture(self.folder)
        for extra, expected_port in (([], 8782), (["--port", "8783"], 8783)):
            with self.subTest(port=expected_port), \
                    patch.object(sys, "argv", ["loader", "--source-dir", str(self.folder)] + extra), \
                    patch.object(loader, "run", return_value=Mock(stdout=
                        "PostgreSQL init process complete; ready for start up.", stderr="")), \
                    patch.object(loader.shutil, "which", return_value="fake"), \
                    patch.object(loader, "inspect_volume"), \
                    patch.object(loader, "inspect_owned", return_value="owned-full-id"), \
                    patch.object(loader, "Pg"), patch.object(loader, "import_one", return_value="active"), \
                    patch.object(loader.api, "Psql"), patch.object(loader, "write_report"), \
                    patch.object(loader.api, "ThreadingHTTPServer") as server:
                server.return_value.serve_forever.side_effect = KeyboardInterrupt
                self.assertEqual(loader.main(), 0)
                self.assertEqual(server.call_args.args[0], ("127.0.0.1", expected_port))
                server.return_value.server_close.assert_called_once()

    def test_cleanup_refuses_unowned_resource(self):
        fixture(self.folder)
        commands = []
        with patch.object(sys, "argv", ["loader", "--source-dir", str(self.folder)]), \
                patch.object(loader, "run", side_effect=lambda args, **kw: commands.append(args)), \
                patch.object(loader.shutil, "which", return_value="fake"), \
                patch.object(loader, "inspect_volume"), \
                patch.object(loader, "inspect_owned", side_effect=RuntimeError("wrong run id")), \
                patch.object(loader, "write_report"), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(loader.main(), 1)
        self.assertFalse(any(args[:2] == ["docker", "rm"] for args in commands))
        self.assertFalse(any(args[:3] == ["docker", "volume", "rm"] for args in commands))

    def test_reconcile_uses_xlsx_anchor_not_summary_and_reports_counts(self):
        fixture(self.folder)
        summary = loader.rows(self.folder, "v7-reconcile-customer.csv")
        summary[0]["source_anchor_vnd"] = "1"
        csv_file(self.folder, "v7-reconcile-customer.csv", list(summary[0]), summary)
        pg = Mock(run_id="a" * 32)
        pg.value.return_value = json.dumps([{"name": FAKE_NAME, "active": True,
                                           "months": {"2026-10-01": str(FAKE_AMOUNT)}}])
        result = reconciler.reconcile(pg, self.folder)
        self.assertEqual(result["loaded_customers"], 1)
        self.assertFalse(result["reason_counts"])
        self.assertNotIn(FAKE_NAME, json.dumps(result))
        pg.value.return_value = json.dumps([{"name": FAKE_NAME, "active": True,
                                           "months": {"2026-10-01": "1"}}])
        result = reconciler.reconcile(pg, self.folder)
        self.assertIn("PERIOD_MISMATCH", result["reason_counts"])
        self.assertIn("CUSTOMER_MISMATCH", result["reason_counts"])


if __name__ == "__main__":
    unittest.main()
