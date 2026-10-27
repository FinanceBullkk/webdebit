#!/usr/bin/env python3
"""Load 20/10 export into one networkless V7 copy. Never print source values."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import posixpath
import re
import shutil
import sys
import time
import unicodedata
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import (
    ROUND_FLOOR,
    ROUND_HALF_DOWN,
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
)
from pathlib import Path
from xml.etree import ElementTree as ET

from test_pg_v7_backend import (
    DATABASE,
    FUNCTIONS,
    IMAGE,
    LABEL_RUN,
    LABEL_TEST,
    LABEL_VALUE,
    SCHEMA,
    Pg,
    call,
    inspect_owned,
    inspect_volume,
    run,
    version,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_ledger_api as api

SOURCE = Path(r"D:\webdebit\captures\2026-10-20-so-goc")
FILES = ("opening_by_period_so_goc.csv", "opening_final_so_goc.csv",
         "trips_so_goc.csv", "payments_so_goc.csv", "v7-reconcile-customer.csv",
         "v7-reconcile-period.csv", "source-google-export.xlsx")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
LOG_DIR = Path(r"D:\webdebit\worktrees\_logs\v7")
SOURCE_NOTICE = "Nguồn là bản xuất trong captures/2026-10-20-so-goc; chưa xác nhận trùng đúng bản v2 đã nạp lên hao"
# Also "THÁNG 2+3.2024" (combined block: the month-end balance is the last month),
# "THÁNG 122025" typed without a separator and stray separators (backslash, doubled dot).
MONTH = re.compile(r"TH[ÁA]NG\s*(?:\d{1,2}\s*\+\s*)*(\d{1,2})[\s/.,\\-]{0,4}(20\d{2})", re.I)
# Real Sheet block title: "SỔ CHI TIẾT THEO DÕI CÔNG NỢ PHẢI THU THÁNG 9.2026" (xlsx profile 20/10).
# Column headers also contain "THÁNG 9.2026", so only these cells open a block.
BLOCK_TITLE = "SO CHI TIET THEO DOI CONG NO"
# Exact tab names (leading/trailing spaces kept) chosen by the user when two tabs differ only in
# surrounding spaces; the others with the same trimmed name are skipped. Set by --raw-tab, never
# stored in Git (customer names stay on the command line).
PREFERRED_RAW_TABS: tuple[str, ...] = ()
# --sheet-is-truth (user 21/10/2026): the xlsx is newer than the CSV extracts and the opening on hao.
# CSV row differences and a hao opening total that differs from the Sheet's month-end balance become
# flags; buckets then come from the Sheet FIFO. The month-end balance chain still has to close.
SHEET_IS_TRUTH = False
SUMMARY_LABELS = {"TONG", "TOTAL", "TONG CONG", "CONG", "TONG THU"}


class LoadError(RuntimeError):
    pass


def rows(source: Path, name: str) -> list[dict[str, str]]:
    with (source / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def integer(value: str) -> int | None:
    if value is None or not str(value).strip():
        return None
    try:
        number = Decimal(value)
        if not number.is_finite() or number != number.to_integral_value():
            return None
        return int(number) if -(2**63) <= number < 2**63 else None
    except (InvalidOperation, ValueError):
        return None


def money(value: str, half_up: bool = True) -> tuple[int | None, Decimal | None]:
    """(whole VND, exact value when it had a fraction). Data cleaning (user 20/10/2026): a fractional
    cell (half a dong from "/2", a third from "/3") reads as the nearest dong, half up; the exact
    value is kept so that the month can be apportioned to the Sheet's own TOTAL (apportion_rounding).
    Charges round half up and receipts half down, so the balance (charge - receipt) still rounds
    half up, which is how the Sheet's month-end balance cell reads.
    Text, formula without cache and anything not finite stay None."""
    whole = integer(value)
    if whole is not None:
        return whole, None
    if value is None or not re.fullmatch(r"-?[0-9]+(?:\.[0-9]*)?(?:E[+-]?[0-9]+)?", str(value).strip(), re.I):
        return None, None
    try:
        exact = Decimal(str(value).strip())
        if not exact.is_finite():
            return None, None
        nearest = int(exact.to_integral_value(rounding=ROUND_HALF_UP if half_up else ROUND_HALF_DOWN))
    except (InvalidOperation, ValueError):
        return None, None
    return (nearest, exact) if -(2**63) <= nearest < 2**63 else (None, None)


def rounded(value: str) -> int | None:
    return money(value)[0]


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFD", value.upper().replace("Đ", "D"))
    return re.sub(r"[^A-Z0-9]+", " ", "".join(
        char for char in text if not unicodedata.combining(char))).strip()


HEADERS = {
    "container": {"CONTAINER NO", "CONTAINER", "SO CONTAINER"},
    # PACKING: one real tab labels the date column that way.
    "date": {"DATE", "NGAY CHUYEN", "NGAY XE NHAP KHO", "ETA", "PACKING"},
    "price": {"UNIT PRICE", "DON GIA"},
    "total": {"TOTAL VND", "TOTAL", "THANH TIEN"},
    "receipt_date": {"NGAY TT STK", "NGAY TT", "NGAY TRA", "PAYMENT DATE"},
    "receipt": {"SO DA UNG TRUOC DA THU TRONG THANG", "SO TIEN TRA", "SO TIEN THU", "PAYMENT"},
    "anchor": {"SO CON PHAI THU CUOI THANG", "CON NO CUOI THANG"},
    "initial": {"NO TRUOC", "NO THANG TRUOC", "SO DU DAU", "CHUYEN SANG"},
    "stt": {"MARKS NOS"},
    "from": {"FROM", "NOI DI"},
    "to": {"TO", "NOI DEN"},
}


def col_num(letters: str) -> int:
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - 64
    return number


def col_name(number: int) -> str:
    name = ""
    while number > 0:
        number, rest = divmod(number - 1, 26)
        name = chr(65 + rest) + name
    return name


def looks_like_date(value: str) -> bool:
    text = value.strip()
    if re.fullmatch(r"[0-9]{5}(?:\.0+)?", text):
        return 30000 <= int(text[:5]) <= 80000  # Excel serial between 1982 and 2119
    return bool(re.match(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{4}-\d{1,2}-\d{1,2}", text))
# Real headers append the month: "SỐ CÒN PHẢI THU CUỐI THÁNG 9.2026".
PREFIX_HEADERS = ("receipt", "anchor", "price")


def header_key(label: str) -> str | None:
    for key, aliases in HEADERS.items():
        if label in aliases or (key in PREFIX_HEADERS and any(label.startswith(a) for a in aliases)):
            return key
    # A note typed into the header cell ("TOTAL(VND) du ...") keeps it the TOTAL column.
    return "total" if label.startswith("TOTAL VND ") else None


def label_key(label: str) -> str | None:
    """Row labels outside the header row; real carry row reads "SỐ DƯ THÁNG CHUYỂN SANG"."""
    if label in HEADERS["initial"] or "CHUYEN SANG" in label:
        return "initial"
    return "anchor" if label in HEADERS["anchor"] else None


def block_month(value: str) -> re.Match | None:
    label = normalized(value)
    if not (label.startswith("THANG") or BLOCK_TITLE in label):
        return None
    return MONTH.search(value)


def workbook_rows(path: Path):
    """All tabs/cells, including inline strings and formula caches; no source output."""
    with zipfile.ZipFile(path) as book:
        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            for si in ET.fromstring(book.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.findall(".//m:t", NS)))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in
                   ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))}
        root = ET.fromstring(book.read("xl/workbook.xml"))
        properties = root.find("m:workbookPr", NS)
        if properties is not None and properties.attrib.get("date1904") in {"1", "true"}:
            raise LoadError("UNSUPPORTED_DATE_SYSTEM")
        trimmed_choice = {name.strip() for name in PREFERRED_RAW_TABS}
        for sheet in root.findall("m:sheets/m:sheet", NS):
            raw_name = sheet.attrib["name"]
            if raw_name.strip() in trimmed_choice and raw_name not in PREFERRED_RAW_TABS:
                continue
            target = targets[sheet.attrib[f"{{{NS['r']}}}id"]]
            target = posixpath.normpath(target.lstrip("/") if target.startswith("/") else "xl/" + target)
            data = []
            with book.open(target) as stream:
                for _, row in ET.iterparse(stream, events=("end",)):
                    if row.tag != f"{{{NS['m']}}}row":
                        continue
                    cells = {}
                    for cell in row.findall("m:c", NS):
                        column = re.match(r"[A-Z]+", cell.attrib["r"]).group()
                        value = cell.find("m:v", NS)
                        text = value.text or "" if value is not None else ""
                        if cell.attrib.get("t") == "s":
                            text = shared[int(text)]
                        elif cell.attrib.get("t") == "inlineStr":
                            text = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
                        if (cell.find("m:f", NS) is not None and not text
                                and not (value is not None and cell.attrib.get("t") == "str")):
                            # <v></v> on a string formula is a cached empty result (the formula
                            # returned blank); only a formula with no <v> at all lost its value.
                            text = "#MISSING_CACHE"
                        cells[column] = text.strip()
                    data.append((int(row.attrib["r"]), cells))
                    row.clear()
            yield sheet.attrib["name"].strip(), data


def source_date(value: str, month: str) -> tuple[str | None, set[str]]:
    if not value:
        return None, {"MISSING_DATE"}
    candidates = []
    # Excel numeric dates carry stored month/day, which can also be reversed.
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        number = Decimal(value)
        try:
            stored = date(1899, 12, 30) + timedelta(days=int(number))
        except (OverflowError, ValueError):
            return None, {"DATE_OUT_OF_BLOCK"}
        parts = stored.year, stored.month, stored.day
    else:
        match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", value)
        if match:
            parts = tuple(map(int, match.groups()))
        else:
            match = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", value)
            if not match:
                return None, {"DATE_OUT_OF_BLOCK"}
            day, mon, year = map(int, match.groups())
            parts = year, mon, day
    for swapped, (year, mon, day) in enumerate((parts, (parts[0], parts[2], parts[1]))):
        try:
            candidate = date(year, mon, day).isoformat()
        except ValueError:
            continue
        if candidate[:7] == month:
            candidates.append((candidate, swapped))
    if not candidates:
        return None, {"DATE_OUT_OF_BLOCK"}
    candidate, swapped = candidates[0]
    return candidate, {"DATE_SWAPPED"} if swapped else set()


SERIAL = re.compile(r"[0-9]+(?:\.0+)?")


def resolve_out_of_block_dates(records: list[dict]) -> None:
    """One display date (never two readings) for serial dates outside their month block.

    The 20/10 export swaps day/month on some tabs. Serial dates that fit their block show
    which way this tab leans; apply the majority reading to the rest. Display only:
    money and months never depend on these dates.
    """
    serial = [r for r in records if r["kind"] == "trip" and SERIAL.fullmatch(r["raw_date"] or "")]
    swapped = sum(1 for r in serial if r["date"] and "DATE_SWAPPED" in r["flags"])
    straight = sum(1 for r in serial if r["date"] and "DATE_SWAPPED" not in r["flags"])
    for record in serial:
        if record["date"]:
            continue
        try:
            stored = date(1899, 12, 30) + timedelta(days=int(Decimal(record["raw_date"])))
        except (OverflowError, ValueError, InvalidOperation):
            continue
        choice = stored
        if swapped > straight:
            with contextlib.suppress(ValueError):
                choice = date(stored.year, stored.day, stored.month)
        record["date"] = choice.isoformat()
        record["flags"].add("DATE_READING_FROM_TAB")


def date_months(value: str) -> set[tuple[int, int]]:
    """(year, month) readings of one date cell: as typed and with day/month swapped."""
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        try:
            stored = date(1899, 12, 30) + timedelta(days=int(Decimal(value)))
        except (OverflowError, ValueError):
            return set()
        parts = stored.year, stored.month, stored.day
    else:
        match = (re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", value)
                 or re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", value))
        if not match:
            return set()
        numbers = tuple(map(int, match.groups()))
        parts = numbers if len(match.group(1)) == 4 else (numbers[2], numbers[1], numbers[0])
    options = set()
    for year, mon, day in (parts, (parts[0], parts[2], parts[1])):
        try:
            date(year, mon, day)
        except ValueError:
            continue
        options.add((year, mon))
    return options


def title_month_from_dates(rows: list, start: int, title: str, check_digits: bool = True) -> str | None:
    """Month of a block title with a typo ("THÁNG 782026", "THÁNG 4.205").

    Read from the trip dates under the title, and only when every dated row allows exactly one
    common month and the title's own digits contain that month. Anything else stays unreadable
    (the caller holds the customer). The month-end balance chain still has to close afterwards.
    """
    digits = "".join(re.findall(r"\d", title.upper().rsplit("THANG", 1)[-1]))
    found, agreed = {}, None
    for _, cells in rows[start + 1:]:
        if any(block_month(v) or BLOCK_TITLE in normalized(v)
               for col, v in cells.items() if col in ("A", "B", "C")):
            break
        if not found:
            for col, value in sorted(cells.items(), key=lambda item: col_num(item[0])):
                key = header_key(normalized(value))
                if key and key not in found:
                    found[key] = col
            if not {"container", "total"} <= found.keys():
                found = {}
            continue
        if not cells.get(found["container"]):
            continue
        stop = col_num(found["price"]) if found.get("price") else col_num(found["container"]) + 4
        for number in range(col_num(found["container"]) + 1, stop):
            options = date_months(cells.get(col_name(number), ""))
            if options:
                agreed = options if agreed is None else agreed & options
                break
    if not agreed or len(agreed) != 1:
        return None
    year, mon = next(iter(agreed))
    return f"{year}-{mon:02d}" if not check_digits or str(mon) in digits else None


def spread_total_over_trips(block: dict) -> None:
    """The Sheet's TOTAL row carries money no trip row has (rows without a price and no TOTAL).

    User 20/10/2026: spread that sum evenly over those trips (VND whole, the remainder goes
    1 dong each to the first rows) so the month's charge is the Sheet's TOTAL. The month-end
    balance chain still has to close afterwards.
    """
    total = block.get("total_row_total")
    if total is None:
        return
    trips = [r for r in block["records"] if r["kind"] == "trip"]
    unpriced = [r for r in trips if r["container"] and not r["price"] and r["amount"] in (None, 0)]
    remainder = total - sum(r["amount"] or 0 for r in trips)
    if not unpriced or remainder <= 0:
        return
    share, extra = divmod(remainder, len(unpriced))
    for index, record in enumerate(unpriced):
        record["spread"] = share + (1 if index < extra else 0)
        record["flags"].add("TOTAL_SPREAD_OVER_TRIPS")
    block.setdefault("flags", set()).add("TOTAL_SPREAD_OVER_TRIPS")


def apportion_rounding(block: dict) -> None:
    """Largest-remainder rounding so rounded cells add up to the Sheet's own TOTAL row.

    Applies per kind (trips against TOTAL, receipts against the received sum) only when the
    exact decimals add up exactly to that whole-dong total; otherwise the plain half-up values
    stay and the month-end chain decides. Never changes a cell that was a whole number.
    """
    for kind, target_key in (("trip", "total_row_exact"), ("receipt", "total_row_receipt_exact")):
        target = block.get(target_key)
        records = [r for r in block["records"] if r["kind"] == kind and r["amount"] is not None]
        fractional = [r for r in records if r.get("exact") is not None]
        if not fractional or target is None or target != target.to_integral_value():
            continue
        if sum((r["exact"] if r.get("exact") is not None else Decimal(r["amount"])) for r in records) != target:
            continue
        fixed = sum(r["amount"] for r in records if r.get("exact") is None)
        floors = [int(r["exact"].to_integral_value(rounding=ROUND_FLOOR)) for r in fractional]
        missing = int(target) - fixed - sum(floors)
        if not 0 <= missing <= len(fractional):
            continue
        order = sorted(range(len(fractional)), key=lambda i: (fractional[i]["exact"] - floors[i], -i), reverse=True)
        bumped = set(order[:missing])
        for i, record in enumerate(fractional):
            record["amount"] = floors[i] + (1 if i in bumped else 0)
        block.setdefault("flags", set()).add("ROUNDING_APPORTIONED")


def block_signature(block: dict) -> tuple:
    return (block.get("anchor"), block.get("initial"),
            sorted((r["kind"], r["container"], r["raw_date"], r["amount"], r["price"])
                   for r in block["records"]))


def scan_workbook(path: Path) -> dict[str, dict]:
    return scan_tabs(workbook_rows(path))


def scan_tabs(tabs) -> dict[str, dict]:
    """Parse (tab name, [(row number, {column: raw cell text})]) from any reader (XLSX or Sheets API)."""
    result = {}
    seen = Counter()
    for tab, data in tabs:
        if normalized(tab) == "TONG":
            continue
        seen[tab] += 1
        blocks, records, issues, notes = {}, [], Counter(), Counter()
        total_rows = []
        current = None
        columns = {}
        rows_list = list(data)

        def settle(block, blocks=blocks, notes=notes, issues=issues):
            """A block outside `blocks` (repeated month, no title) is dropped only when provably empty/identical."""
            if block is None or not block.get("scratch"):
                return
            if block["scratch"] == "duplicate":
                if block_signature(block) == block_signature(blocks[block["month"]]):
                    notes["DUPLICATE_BLOCK_IDENTICAL"] += 1
                else:
                    issues["DUPLICATE_MONTH_BLOCK"] += 1
            elif (block["records"] or block.get("anchor") not in (None, 0)
                  or block.get("initial") not in (None, 0)):
                issues["SOURCE_LAYOUT_UNSUPPORTED"] += 1
                issues["LAYOUT_HEADER_MISSING_BLOCK"] += 1
            else:
                notes["UNTITLED_EMPTY_BLOCK"] += 1

        for position, (row_no, cells) in enumerate(rows_list):
            # Block titles live in the first columns; side tables (e.g. T..Z on one tab) repeat
            # "THÁNG 09/2026" on every row and must not open new blocks.
            title_cells = [(value, block_month(value)) for col, value in cells.items() if col in ("A", "B", "C")]
            titles = [match for _, match in title_cells if match]
            title_text = next((value for value, match in title_cells if match), None)
            if not titles:
                # Title phrase whose month or year was mistyped ("THÁNG 4.205").
                title_text = next((value for col, value in cells.items()
                                   if col in ("A", "B", "C") and BLOCK_TITLE in normalized(value)), None)
            if titles or title_text:
                settle(current)
                match = titles[0] if titles else None
                month = None
                if match and 1 <= int(match[1]) <= 12:
                    month = f"{match[2]}-{int(match[1]):02d}"
                    if month in blocks:
                        # Same title typed twice but the dates under it say a later month (title
                        # copied and not changed): take that month only if it is free and newer than
                        # every block so far. A true copy infers its own (taken) month: duplicate.
                        guess = title_month_from_dates(rows_list, position, title_text, check_digits=False)
                        if guess and guess not in blocks and guess > max(blocks):
                            month = guess
                            notes["TITLE_MONTH_FROM_DATES"] += 1
                else:
                    month = title_month_from_dates(rows_list, position, title_text)
                    if month and month in blocks:
                        month = None
                    if month:
                        notes["TITLE_MONTH_FROM_DATES"] += 1
                if month is None:
                    issues["SOURCE_LAYOUT_UNSUPPORTED"] += 1
                    issues["LAYOUT_BAD_MONTH_TITLE"] += 1
                    current = None
                    columns = {}
                    continue
                columns = {}
                if month in blocks:
                    current = {"anchor": None, "anchor_row": row_no, "initial": None, "records": [],
                               "month": month, "scratch": "duplicate"}
                else:
                    current = blocks.setdefault(month, {"anchor": None, "anchor_row": row_no,
                                                        "initial": None, "records": [], "month": month})
                continue
            # Leftmost column wins: some tabs put a second (invoice) table to the right with
            # its own "CONTAINER NO." / "TOTAL (VND)" headers.
            detected = {}
            for col, value in sorted(cells.items(), key=lambda item: col_num(item[0])):
                key = header_key(normalized(value))
                if key and key not in detected:
                    detected[key] = col
            side_header = bool(columns.get("container") and "container" in detected
                               and detected["container"] != columns["container"])
            if "container" in detected and "total" in detected and side_header:
                # Header of a second (invoice) table to the right on a later row of the same block.
                # It must not replace the main table's columns, and the row may still be a trip row.
                notes["SIDE_TABLE_HEADER_IGNORED"] += 1
            elif "container" in detected and "total" in detected:
                if current is None:
                    # Header before any title: tolerated only if the block turns out empty (settle).
                    current = {"anchor": None, "anchor_row": row_no, "initial": None, "records": [],
                               "month": "0000-00", "scratch": "untitled"}
                columns.update(detected)
                columns["fees"] = [col for col, value in cells.items()
                                   if normalized(value).startswith(("OTHER FEE", "PHU PHI"))]
                if not {"price", "date", "receipt", "anchor"} <= columns.keys():
                    issues["SOURCE_LAYOUT_UNSUPPORTED"] += 1
                    issues["LAYOUT_HEADER_MISSING_" + "_".join(sorted({"price", "date", "receipt", "anchor"} - columns.keys()) or ["BLOCK"])] += 1
                continue
            if current is None or current.get("closed"):
                # Rows after the block's TỔNG row are notes (CÒN LẠI, 总共, 剩余...), not trips.
                continue
            # Explicit labels can sit outside table columns; never use TONG as anchor.
            # Labels (TỔNG, CHUYỂN SANG...) count only inside the main table: side tables to the
            # right repeat "TỔNG"/"CÒN LẠI" on trip rows and must not close the block.
            limit = max((col_num(c) for k, c in columns.items() if k != "fees"), default=3)
            table = {col: value for col, value in cells.items() if col_num(col) <= limit}
            for col, value in table.items():
                key = label_key(normalized(value))
                if key:
                    following = list(table.values())[list(table).index(col) + 1:]
                    amounts = [rounded(v) for v in following if rounded(v) is not None]
                    if len(amounts) == 1:
                        current[key] = amounts[0]
                        current[key + "_row"] = row_no
                    elif len(amounts) > 1:
                        issues["SOURCE_LAYOUT_UNSUPPORTED"] += 1
                        issues["LAYOUT_LABEL_MANY_AMOUNTS"] += 1
                    elif key == "initial":
                        # Real carry row "SỐ DƯ THÁNG CHUYỂN SANG" is often left blank. Blank is
                        # not 0: mark it; source_data checks the assumption against the month anchor.
                        current["initial_blank"] = True
                        current["initial_row"] = row_no
                    elif col != columns.get(key):
                        issues["MISSING_MONTH_ANCHOR"] += 1
            totals_row = any(normalized(v) in SUMMARY_LABELS for v in table.values())
            summary = totals_row or any(label_key(normalized(v)) for v in table.values())
            if not columns:
                if not summary and any(integer(v) is not None for v in cells.values()):
                    # Numbers outside the table (notes, side sums): flag only; any effect on money
                    # still has to pass the month-end anchor chain.
                    current.setdefault("flags", set()).add("NUMBERS_OUTSIDE_TABLE")
                continue
            def get(key):
                return cells.get(columns.get(key), "")  # noqa: B023  (defined and called within the same row iteration)
            if get("initial") and normalized(get("initial")) not in HEADERS["initial"]:
                current["initial"] = rounded(get("initial"))
                if current["initial"] is None:
                    issues["MISSING_OPENING_ANCHOR"] += 1
            if get("anchor") and header_key(normalized(get("anchor"))) != "anchor":
                # Month-end balance comes from the TỔNG row when there is one; running
                # values on trip rows never override it.
                if totals_row or (not summary and not current.get("anchor_from_totals")):
                    current["anchor"] = rounded(get("anchor"))
                    current["anchor_row"] = row_no
                if totals_row:
                    current["anchor_from_totals"] = True
            if totals_row:
                current["closed"] = True
                current["total_row_total"] = rounded(get("total"))
                current["total_row_exact"] = money(get("total"))[1] or (
                    Decimal(rounded(get("total"))) if rounded(get("total")) is not None else None)
                current["total_row_receipt_exact"] = money(get("receipt"))[1] or (
                    Decimal(rounded(get("receipt"))) if rounded(get("receipt")) is not None else None)
            if summary:
                continue
            # Headers can contain several OTHER FEE columns; all retain raw cells.
            fee_columns = columns.get("fees", [])
            bare = not (get("container") or get("date") or get("price")
                        or any(cells.get(col) for col in fee_columns))
            if bare:
                total_value, receipt_value = rounded(get("total")), rounded(get("receipt"))
                if (not current["records"] and current.get("initial") is None and get("anchor")
                        and (not get("total") or rounded(get("total")) == 0) and not get("receipt")
                        and rounded(get("anchor")) is not None):
                    # Carry into the month typed in the balance column above the first trip,
                    # without the "SỐ DƯ THÁNG CHUYỂN SANG" label. Still checked by the chain.
                    current["initial"] = rounded(get("anchor"))
                    current["initial_row"] = row_no
                    current.setdefault("flags", set()).add("CARRY_ROW_UNLABELED")
                    continue
                if not get("receipt") and (not get("total") or total_value == 0):
                    continue  # empty template row: only a TOTAL formula returning 0
                trip_sum, receipt_sum = current.get("trip_sum", 0), current.get("receipt_sum", 0)
                # Rounded cells (ROUNDED_VND) may sit up to 1 dong each away from the Sheet's exact sums.
                slack = sum(1 for r in current["records"] if r.get("exact") is not None)
                if trip_sum and total_value is not None and abs(total_value - trip_sum) <= slack and (
                        not get("receipt") or (receipt_value is not None and abs(receipt_value - receipt_sum) <= slack)):
                    # Unlabeled totals row (count in A, sums in TOTAL/received, balance in
                    # the anchor column). Reading it as a fee + receipt would double both
                    # sides while the balance still matched, so the chain cannot catch it.
                    if get("anchor"):
                        current["anchor"] = rounded(get("anchor"))
                        current["anchor_row"] = row_no
                        current["anchor_from_totals"] = True
                    current["closed"] = True
                    current["total_row_total"] = total_value
                    current["total_row_exact"] = money(get("total"))[1] or Decimal(total_value)
                    current["total_row_receipt_exact"] = (money(get("receipt"))[1] or Decimal(receipt_value)
                                                          if receipt_value is not None else None)
                    issues_flags = current.setdefault("flags", set())
                    issues_flags.add("UNLABELED_TOTAL_ROW")
                    # The older CSV extract counts this row as a trip/receipt; remember it so that
                    # the row comparison does not treat the extractor's extra row as missing data.
                    total_rows.append(("trip", row_no, total_value))
                    if get("receipt"):
                        total_rows.append(("receipt", row_no, receipt_value))
                    continue
            if (columns.get("price") and integer(get("price")) is not None and not get("receipt")
                    and not any(value for col, value in table.items()
                                if col not in (columns["price"], columns.get("stt")))):
                # A bare unit price with no container, date, TOTAL or fee is a note, not a trip: the
                # Sheet's TOTAL cell is empty so the Sheet counts nothing. If the Sheet did count it,
                # the month-end balance chain below fails and the customer stays held.
                current.setdefault("flags", set()).add("PRICE_ONLY_ROW_IGNORED")
                continue
            # Some tabs type the descriptive cells one column off the header (date under
            # the blank carrier header, origin under DATE...). Money columns stay put; find
            # the date between container and price and shift date/from/to by the same step.
            shift = 0
            if columns.get("date") and columns.get("container") and not looks_like_date(get("date")):
                stop = col_num(columns["price"]) if columns.get("price") else col_num(columns["date"]) + 3
                for number in range(col_num(columns["container"]) + 1, stop):
                    if looks_like_date(cells.get(col_name(number), "")):
                        shift = number - col_num(columns["date"])
                        break

            def shifted(key):
                return cells.get(col_name(col_num(columns[key]) + shift), "") if columns.get(key) else ""  # noqa: B023  (defined and called within the same row iteration)
            carrier_col = col_name(col_num(columns["container"]) + 1) if columns.get("container") else None
            carrier = "" if not carrier_col or carrier_col in {
                col_name(col_num(columns[k]) + shift) for k in ("date", "from", "to") if columns.get(k)
            } else cells.get(carrier_col, "")
            fees = [integer(cells[col]) for col in fee_columns if cells.get(col)]
            details = {"stt": get("stt"), "carrier": carrier, "from": shifted("from"), "to": shifted("to"),
                       "fee": sum(fees) if fees and None not in fees else None,
                       "unit_price": integer(get("price"))}
            has_trip = bool(get("container") or get("date") or get("price") or get("total")
                            or any(cells.get(col) for col in fee_columns))
            for kind, present, raw_amount, raw_date in (
                    ("trip", has_trip, get("total"), shifted("date")),
                    # A payment needs an amount cell; "da tt"/date notes alone annotate a trip.
                    ("receipt", bool(get("receipt")), get("receipt"), get("receipt_date"))):
                if not present:
                    continue
                dt, flags = source_date(raw_date, current["month"])
                if kind == "trip" and shift:
                    flags.add("COLUMN_SHIFTED")
                if "#MISSING_CACHE" in cells.values():
                    flags.add("MISSING_CACHE")
                price = rounded(get("price")) if kind == "trip" else None
                fee_only = kind == "trip" and not get("container") and not get("price")
                if kind == "trip" and not fee_only and not get("price"):
                    # Flag only: history keeps the Sheet's own TOTAL cell (V7-MIG), which the
                    # Sheet's month-end balance already counts.
                    flags.add("MISSING_PRICE")
                if kind == "trip" and get("receipt_date") and not get("receipt"):
                    flags.add("PAYMENT_NOTE")
                if kind == "trip" and get("price") and price is None:
                    if rounded(get("total")) is not None:
                        # Price cell is text ("CHƯA CÓ GIÁ") or a formula without a cached value,
                        # but the Sheet TOTAL is a number: history keeps that total, price unknown.
                        flags.add("MISSING_PRICE")
                    else:
                        issues["INVALID_TRIP_AMOUNT"] += 1
                if kind == "trip" and price is not None and price < 0:
                    if not get("container") and rounded(get("total")) is not None and rounded(get("total")) < 0:
                        # Credit line (no container, negative price and TOTAL): the schema keeps
                        # trip charges signed and the Sheet balance already counts it.
                        flags.add("NEGATIVE_CREDIT_ROW")
                    else:
                        issues["INVALID_TRIP_AMOUNT"] += 1
                amount, exact = money(raw_amount, half_up=kind == "trip")
                if exact is not None:
                    flags.add("ROUNDED_VND")
                if amount is None and raw_amount == "#MISSING_CACHE":
                    # Same hold as an empty cell, with the cause named for whoever re-exports the Sheet.
                    issues["FORMULA_CACHE_MISSING"] += 1
                if kind == "receipt" and amount is None:
                    issues["MISSING_RECEIPT_AMOUNT"] += 1
                if kind == "receipt" and amount is not None and amount < 0:
                    issues["INVALID_RECEIPT_AMOUNT"] += 1
                if kind == "trip" and amount is None and "MISSING_PRICE" not in flags:
                    issues["MISSING_TRIP_AMOUNT"] += 1
                record = {"kind": kind, "month": current["month"], "row": row_no,
                          "amount": amount, "exact": exact, "flags": flags, "date": dt,
                          "container": get("container"), "price": get("price"),
                          "cells": cells, "raw_date": raw_date,
                          "details": details if kind == "trip" else {"stt": get("stt")}}
                records.append(record)
                current["records"].append(record)
                if amount is not None:
                    key = "trip_sum" if kind == "trip" else "receipt_sum"
                    current[key] = current.get(key, 0) + amount
        settle(current)
        for block in blocks.values():
            apportion_rounding(block)
            spread_total_over_trips(block)
        resolve_out_of_block_dates(records)
        if not blocks and any(any(cells.values()) for _, cells in data):
            issues["SOURCE_LAYOUT_UNSUPPORTED"] += 1
            issues["LAYOUT_NO_MONTH_BLOCK"] += 1
        if blocks or issues:
            if not blocks:
                issues["MISSING_MONTH"] += 1
            result[tab] = {"blocks": blocks, "records": records, "issues": issues,
                           "notes": notes, "total_rows": total_rows}
    # Tabs with the same trimmed name need per-customer rules kept outside Git:
    # hold only that customer, never abort the run or pick one tab.
    for tab, count in seen.items():
        if count > 1:
            result[tab] = {"blocks": {}, "records": [], "issues": Counter({"AMBIGUOUS_SOURCE_TAB": 1})}
    return result


# MH-01 (specs/v7-mat-hang-chon-khach.md): LOAI HANG label on TONG -> (commodity, transport mode).
# Labels not listed stay NULL ("Chưa phân loại"); never guessed.
COMMODITY_LABELS = {
    "SAU RIENG CANG": ("Sầu riêng", "CANG"), "SAU RIENG BO": ("Sầu riêng", "BO"),
    "SAU RIENG": ("Sầu riêng", None), "THANH LONG": ("Thanh long", None),
    "TLONG BO": ("Thanh long", "BO"), "XOAI": ("Xoài", None), "XOAI BO": ("Xoài", "BO"),
    "CHUOI": ("Chuối", None), "DUA COCONUT": ("Dừa", None), "DUA": ("Dừa", None),
    "DUA BO": ("Dừa", "BO"),
    "BUOI": ("Bưởi", None), "MIT": ("Mít", None), "NHAN": ("Nhãn", None),
    "GUNG TUOI": ("Gừng tươi", None), "KHOAI LANG": ("Khoai lang", None),
    "BAN CUOC": ("Bán cước", None), "HANG NHAP": ("Hàng nhập", None),
}


def tong_commodities(path: Path) -> dict[str, str | None]:
    """Normalized customer name -> LOAI HANG label of its rightmost (latest) TONG block.

    Two different labels at the same rightmost position (names that normalize alike) map to None.
    """
    found: dict[str, tuple[tuple[int, int], str | None]] = {}
    for tab, data in workbook_rows(path):
        if normalized(tab) != "TONG":
            continue
        pairs: list[tuple[str, str]] = []
        for number, cells in data:
            heads = {col: normalized(v) for col, v in cells.items()}
            labels = [col for col, v in heads.items() if v == "LOAI HANG"]
            if labels:
                pairs = [(col, col_name(col_num(col) + 1)) for col in labels
                         if heads.get(col_name(col_num(col) + 1)) == "TEN KHACH HANG"]
                continue
            for label_col, name_col in pairs:
                name, label = normalized(cells.get(name_col, "")), cells.get(label_col, "").strip()
                if not name or not label:
                    continue
                key = (col_num(label_col), number)
                if name not in found or key > found[name][0]:
                    found[name] = (key, label)
                elif key == found[name][0] and found[name][1] != label:
                    found[name] = (key, None)
    return {name: label for name, (_, label) in found.items()}


def commodity_of(label: str | None) -> tuple[str, str | None] | None:
    return COMMODITY_LABELS.get(normalized(label)) if label else None


def source_data(source: Path) -> tuple[list[dict], dict[str, str], dict[str, Counter]]:
    if any(not (source / name).is_file() for name in FILES):
        raise LoadError("SOURCE_FILE_MISSING")
    digests = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in FILES}
    anchors = rows(source, "opening_final_so_goc.csv")
    periods = rows(source, "opening_by_period_so_goc.csv")
    csv_rows = {kind: rows(source, filename) for kind, filename in
                (("trip", "trips_so_goc.csv"), ("receipt", "payments_so_goc.csv"))}
    scanned = scan_workbook(source / "source-google-export.xlsx")
    tong_labels = tong_commodities(source / "source-google-export.xlsx")
    names = set(scanned)
    for filename in ("v7-reconcile-customer.csv", "v7-reconcile-period.csv"):
        names.update(r["customer"].strip() for r in rows(source, filename))
    names.update(r["tab"].strip() for r in anchors)
    names.update(r["customer"].strip() for r in periods)
    for records in csv_rows.values():
        names.update(r["tab"].strip() for r in records)
    anchor_map = {}
    for r in anchors:
        name = r["tab"].strip()
        if name in anchor_map:
            raise LoadError("DUPLICATE_SOURCE_TAB")
        anchor_map[name] = r
    opening = defaultdict(dict)
    for n, row in enumerate(periods, 2):
        name, month = row["customer"].strip(), row["debt_period"]
        if not re.fullmatch(r"20[0-9]{2}-(?:0[1-9]|1[0-2])", month):
            raise LoadError("INVALID_OPENING_PERIOD")
        if month in opening[name] or integer(row["balance_vnd"]) is None:
            raise LoadError("INVALID_OPENING_PERIOD")
        opening[name][month] = (integer(row["balance_vnd"]), n)
    books, held = [], {}
    def build_item(name, ordinal, insurance_as_receipt):
        tab = scanned.get(name, {"blocks": {}, "records": [], "issues": Counter({"MISSING_SOURCE_TAB": 1})})
        reasons = tab["issues"].copy()
        flags = Counter({"NO_BASELINE": 1, "CHUA_PHAN_LOAI": 1})
        flags.update(tab.get("notes", {}))
        final = anchor_map.get(name, {})
        in_summary = bool(final)
        if not in_summary:
            # A book must be on TONG (OPENING-SO-GOC); copies/scratch tabs are reported, not loaded.
            reasons["NOT_ON_TONG"] += 1
        if integer(final.get("delta_vs_db", "")) in (-600, 600):
            flags["HISTORICAL_DELTA_600"] += 1
        if final.get("flags"):
            flags["OTHER"] += 1
        item = {"name": name, "ordinal": ordinal, "reasons": reasons, "flags": flags,
                "openings": [], "checks": [], "legacy": [], "anchor": None,
                "row_counts": Counter(r["kind"] for r in tab["records"]), "in_summary": in_summary}
        label = tong_labels.get(normalized(name))
        if (commodity := commodity_of(label)) is not None:
            item["commodity"], item["transport_mode"] = commodity
        elif label:
            item["commodity_label_unknown"] = True
        # Match physical row identity and raw amounts as well as per-tab counts/totals.
        for kind, records in csv_rows.items():
            extracted = [r for r in records if r["tab"].strip() == name]
            direct = [r for r in tab["records"] if r["kind"] == kind]
            amount_key = "total_cell" if kind == "trip" else "amount_vnd"
            def csv_amount(r, amount_key=amount_key, kind=kind):
                value = integer(r[amount_key])
                # The CSV signs insurance items "added to debt" negative; the xlsx cell is the
                # positive magnitude that the chain below counts as a charge. Same magnitude only.
                if (kind == "receipt" and value is not None and value < 0
                        and r.get("kind") == "INSURANCE_RECEIVABLE_added_to_debt"):
                    return -value
                return value
            csv_signature = Counter((integer(r["row"]), csv_amount(r)) for r in extracted)
            xml_signature = Counter((r["row"], None if r.get("exact") is not None else r["amount"]) for r in direct)
            only_csv = csv_signature - xml_signature
            counted_totals = Counter((row, amount) for total_kind, row, amount in tab.get("total_rows", ())
                                     if total_kind == kind)
            if only_csv and not (only_csv - counted_totals):
                # The extra CSV rows are the xlsx's unlabeled TOTAL rows (extractor read them as a
                # trip/receipt); the xlsx rows themselves still face the month-end chain.
                flags["CSV_COUNTED_TOTAL_ROW"] += 1
                csv_signature = csv_signature - only_csv
            item.setdefault("csv_only", []).extend(
                [kind, row, amount] for row, amount in sorted((csv_signature - xml_signature).elements(),
                                                             key=lambda pair: pair[0] or 0)[:8])
            if csv_signature - xml_signature:
                # CSV row absent from the xlsx scan, or a different amount: hold.
                if SHEET_IS_TRUTH:
                    flags["CSV_STALE_ROWS"] += 1
                else:
                    reasons["SOURCE_ROW_MISMATCH"] += 1
            elif xml_signature - csv_signature:
                # Known extractor bug (MOC-CHUYEN-MOI): CSV skips rows the xlsx has. The xlsx
                # rows still go through the month-end anchor chain below.
                flags["CSV_MISSING_ROWS"] += 1
            csv_by_row = {integer(r["row"]): r for r in extracted}
            for record in direct:
                csv_row = csv_by_row.get(record["row"], {})
                record["source_flags"] = csv_row.get("flags", "")
                if record["source_flags"]:
                    record["flags"].add("OTHER")
                if kind == "receipt":
                    record["source_kind"] = csv_row.get("kind", "")
                    record["note"] = csv_row.get("note", "")
        # Months come from the Sheet blocks. Opening months on hao outside them are noted;
        # the bucket split is then taken from the Sheet FIFO below when totals agree.
        months = sorted(tab["blocks"])
        if set(opening[name]) - set(months):
            flags["OPENING_MONTH_NOT_IN_SHEET"] += 1
        if not months:
            reasons["MISSING_MONTH_ANCHOR"] += 1
        blocks = tab["blocks"]
        if months and months[-1] in blocks:
            item["anchor"] = blocks[months[-1]]["anchor"]
        if item["anchor"] is None:
            reasons["NO_ANCHOR"] += 1
        if final and integer(final.get("target_balance_vnd", "")) != item["anchor"]:
            flags["SUMMARY_ANCHOR_DIFFERS"] += 1
        if item["anchor"] is not None and sum(a for a, _ in opening[name].values()) != item["anchor"]:
            if SHEET_IS_TRUTH:
                flags["OPENING_TOTAL_DIFFERS_FROM_HAO"] += 1
            else:
                reasons["OPENING_TOTAL_MISMATCH"] += 1
        balances = []
        cumulative = initial = exact_cum = None
        for month in months:
            block = blocks.get(month, {"records": [], "anchor": None})
            charge = receipt = 0
            exact_charge = exact_receipt = Decimal(0)
            adjusted = False
            charge_known = receipt_known = True
            month_flags = {"NO_BASELINE"}
            flags.update(block.get("flags", ()))
            for record in block["records"]:
                flags.update(record["flags"])
                month_flags.update(record["flags"])
                amount = record.get("spread", record["amount"])
                if record["kind"] == "trip":
                    if amount is None and "MISSING_PRICE" not in record["flags"]:
                        charge_known = False
                    if amount is not None:
                        charge += amount
                        exact_charge += record["exact"] if record.get("exact") is not None else amount
                elif amount is not None:
                    if record.get("source_kind") == "INSURANCE_RECEIVABLE_added_to_debt":
                        item["has_insurance"] = True
                    if (record.get("source_kind") == "INSURANCE_RECEIVABLE_added_to_debt"
                            and not insurance_as_receipt):
                        charge += amount
                        exact_charge += record["exact"] if record.get("exact") is not None else amount
                    else:
                        receipt += amount
                        exact_receipt += record["exact"] if record.get("exact") is not None else amount
                else:
                    receipt_known = False
                details = record.get("details", {})
                def money_text(value):
                    return None if value is None else str(value)
                # Structured fields let the page place history in the same columns as the Sheet;
                # VND as digit strings like every other money field.
                display = {"tab": name, "row": record["row"], "date": record["date"],
                           "raw_date": record["raw_date"], "container": record["container"],
                           "unit_price": money_text(details.get("unit_price")) if details.get("unit_price")
                           is not None else record["price"],
                           "stt": details.get("stt", ""), "carrier": details.get("carrier", ""),
                           "from": details.get("from", ""), "to": details.get("to", ""),
                           "fee_vnd": money_text(details.get("fee")),
                           "flags": sorted(record["flags"]),
                           "cells": record["cells"], "source_flags": record.get("source_flags", ""),
                           "note": record.get("note", ""), "source_kind": record.get("source_kind", "")}
                item["legacy"].append({"debt_month": month + "-01", "kind": record["kind"],
                    "display": display, "source_total_vnd": amount,
                    "source_tab": name + ":" + record["kind"], "source_row": record["row"]})
            if block["anchor"] is None:
                reasons["MISSING_MONTH_ANCHOR"] += 1
            if not balances:
                initial = block.get("initial")
                if initial is None and month in blocks:
                    # No explicit carry amount: assume 0 only as a hypothesis. The chain
                    # check below compares it with the Sheet's own month-end balance, so a
                    # wrong assumption holds the customer instead of loading a wrong number.
                    initial = 0
                    flags["OPENING_BLANK_AS_ZERO" if block.get("initial_blank")
                          else "OPENING_ROW_ABSENT_AS_ZERO"] += 1
                cumulative = initial
            elif block.get("initial") is not None and block["initial"] != cumulative:
                previous = months[months.index(month) - 1]
                if (cumulative is not None and charge_known and receipt_known and month.endswith("-01")
                        and previous[:4] == str(int(month[:4]) - 1)):
                    # User 20/10/2026: the January carry typed in the Sheet is right; the gap to
                    # the previous year's end is money not yet entered in the detail book. A
                    # shortfall is a payment (FIFO takes it from the oldest debt), a surplus is a
                    # charge. It is one visible adjustment row, flagged, and the chain still closes.
                    delta = block["initial"] - cumulative
                    if delta < 0:
                        receipt -= delta
                    else:
                        charge += delta
                    adjusted = True
                    flags["YEAR_END_CARRY_ADJUSTED"] += 1
                    month_flags.add("YEAR_END_CARRY_ADJUSTED")
                    item["legacy"].append({"debt_month": month + "-01",
                        "kind": "receipt" if delta < 0 else "trip",
                        "display": {"tab": name, "row": block.get("initial_row", block["anchor_row"]),
                                    "date": None, "raw_date": "", "container": "", "unit_price": None,
                                    "stt": "", "carrier": "", "from": "", "to": "", "fee_vnd": None,
                                    "flags": ["YEAR_END_CARRY_ADJUSTED"], "cells": {},
                                    "source_flags": "", "note": "", "source_kind": ""},
                        "source_total_vnd": abs(delta),
                        "source_tab": name + ":year-end-carry",
                        "source_row": block.get("initial_row", block["anchor_row"])})
                else:
                    reasons["ANCHOR_CHAIN_MISMATCH"] += 1
            if not charge_known or not receipt_known:
                cumulative = None
            month_rounded = False
            if cumulative is not None and exact_cum is not None and not adjusted and any(
                    r.get("exact") is not None for r in block["records"]):
                # Data cleaning with fractions (user 20/10/2026): the month's whole-dong charge is its
                # exact charge rounded, and the receipt is whatever makes the whole-dong balance equal
                # the exact running balance rounded half up (how the Sheet's balance cell reads).
                end = int((exact_cum + exact_charge - exact_receipt).to_integral_value(rounding=ROUND_HALF_UP))
                charge = int(exact_charge.to_integral_value(rounding=ROUND_HALF_UP))
                receipt = charge - (end - cumulative)
                flags["ROUNDED_MONTH_TOTALS"] += 1
                month_rounded = True
            if month_rounded:
                # Month rounding already defines charge/receipt above. Apportion its remainder
                # to fractional source rows so the frozen rows and month checks tell one story.
                month_rows = [r for r in item["legacy"] if r["debt_month"] == month + "-01"]
                for kind, target in (("trip", charge), ("receipt", receipt)):
                    kind_rows = [r for r in month_rows if (r["kind"] == "trip" or
                        (r["display"]["source_kind"] == "INSURANCE_RECEIVABLE_added_to_debt"
                         and not insurance_as_receipt)) == (kind == "trip")]
                    delta = target - sum(r["source_total_vnd"] or 0 for r in kind_rows)
                    fractional_rows = [r for r in kind_rows if "ROUNDED_VND" in r["display"]["flags"]]
                    if delta and fractional_rows:
                        if abs(delta) > len(fractional_rows):
                            reasons["ROUNDING_REMAINDER_UNSUPPORTED"] += 1
                            continue
                        share, extra = divmod(abs(delta), len(fractional_rows))
                        for index, row in enumerate(fractional_rows):
                            row["source_total_vnd"] += (1 if delta > 0 else -1) * (share + (index < extra))
                            row["display"]["flags"].append("ROUNDING_APPORTIONED")
            if cumulative is not None:
                exact_cum = (Decimal(cumulative + charge - receipt) if exact_cum is None or adjusted
                             else exact_cum + exact_charge - exact_receipt)
            if cumulative is not None:
                cumulative += charge - receipt
                if cumulative != block["anchor"]:
                    reasons["ANCHOR_CHAIN_MISMATCH"] += 1
            balances.append(charge + (initial if len(balances) == 0 and initial is not None else 0))
            left = receipt
            for index in range(len(balances)):
                paid = min(max(balances[index], 0), left)
                balances[index] -= paid
                left -= paid
            if left:
                balances[-1] -= left
            bucket, source_row = opening[name].get(month, (0, block.get("anchor_row", 1)))
            item["openings"].append({"debt_month": month + "-01", "amount_vnd": bucket,
                "source_tab": "opening_by_period_so_goc.csv", "source_row": source_row})
            # SQL whitelist stays unchanged: exact new flags live in legacy.display/report.
            sql_flags = month_flags & {"NO_BASELINE", "MISSING_PRICE", "MISSING_CACHE"}
            if flags["HISTORICAL_DELTA_600"]:
                sql_flags.add("HISTORICAL_DELTA_600")
            if month_flags - sql_flags or flags["OTHER"] or flags["CHUA_PHAN_LOAI"]:
                sql_flags.add("OTHER")
            item["checks"].append({"debt_month": month + "-01", "opening_anchor_vnd": initial,
                "source_cumulative_vnd": block["anchor"], "replay_cumulative_vnd": cumulative,
                "bucket_vnd": bucket, "standard_bucket_vnd": None,
                "source_charge_vnd": charge if charge_known else None,
                "source_receipt_vnd": receipt if receipt_known else None,
                "standard_source_ref": "XLSX explicit opening and month-end anchors; source rows",
                "standard_source_sha256": digests["source-google-export.xlsx"],
                "source_evidence_sha256": digests["source-google-export.xlsx"],
                "exception_codes": sorted(sql_flags)})
        sheet_split_ok = (cumulative is not None and balances and sum(balances) == item["anchor"]
                          and not reasons.get("OPENING_TOTAL_MISMATCH"))
        for check, opening_row, standard in zip(item["checks"], item["openings"], balances, strict=True):
            check["standard_bucket_vnd"] = standard if cumulative is not None else None
            if cumulative is not None and check["bucket_vnd"] != standard:
                if sheet_split_ok:
                    # Same total as hao, different month split: use the Sheet FIFO split (V7-BE 2,
                    # user 20/10/2026) and record it, so hao's split can be reviewed separately.
                    check["bucket_vnd"] = opening_row["amount_vnd"] = standard
                    flags["BUCKETS_FROM_SHEET"] += 1
                else:
                    reasons["FIFO_BUCKET_MISMATCH"] += 1
        if initial is None:
            reasons["MISSING_OPENING_ANCHOR"] += 1
        if cumulative is not None and balances and sum(balances) != item["anchor"]:
            reasons["ANCHOR_CHAIN_MISMATCH"] += 1
        return item

    for ordinal, name in enumerate(sorted(names), 1):
        item = build_item(name, ordinal, False)
        if item["reasons"] and item.get("has_insurance"):
            # Insurance items the older CSV calls "added to debt" count as charges. If the Sheet was
            # edited since, the same cells may now reduce the debt; try that reading and keep it only
            # when it leaves fewer holds (the month-end chain still has to close, cell for cell).
            other = build_item(name, ordinal, True)
            if sum(other["reasons"].values()) < sum(item["reasons"].values()):
                other["flags"]["INSURANCE_AS_RECEIPT"] += 1
                item = other
        books.append(item)
        held[name] = item["reasons"]
    if digests != {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in FILES}:
        raise LoadError("SOURCE_CHANGED_DURING_READ")
    return books, digests, held


CLEAN_FORMAT_VERSION = 2
CLEAN_FILES = ("clean_customers.csv", "clean_months.csv", "clean_rows.csv")
DISPLAY_FIELDS = ("date", "raw_date", "container", "unit_price", "fee_vnd", "carrier",
                  "from", "to", "note", "stt", "row", "tab", "cells", "source_kind", "source_flags", "flags")


def validate_books(books: list[dict], control_total: int) -> None:
    """Mechanical gates shared by export and clean reader; never substitute NULL with zero."""
    for item in books:
        months = [c["debt_month"] for c in item["checks"]]
        if months != sorted(set(months)) or any(r["debt_month"] not in months for r in item["legacy"]):
            raise LoadError("CLEAN_MONTHS")
        if not item["in_summary"] or item["reasons"]:
            raise LoadError("CLEAN_INELIGIBLE_CUSTOMER")
        checks = item["checks"]
        if not checks or len(checks) != len(item["openings"]):
            raise LoadError("CLEAN_MONTHS")
        cumulative = checks[0]["opening_anchor_vnd"]
        for check, opening in zip(checks, item["openings"], strict=True):
            charge = receipt = 0
            for row in item["legacy"]:
                if row["debt_month"] != check["debt_month"]:
                    continue
                amount = row["source_total_vnd"]
                if amount is None:
                    if row["kind"] == "trip" and "MISSING_PRICE" in row["display"]["flags"]:
                        continue
                    raise LoadError("CLEAN_MONTH_TOTAL")
                insurance_charge = (row["display"].get("source_kind") == "INSURANCE_RECEIVABLE_added_to_debt"
                                    and not item["flags"].get("INSURANCE_AS_RECEIPT"))
                if row["kind"] == "trip" or insurance_charge:
                    charge += amount
                else:
                    receipt += amount
            if (charge, receipt) != (check["source_charge_vnd"], check["source_receipt_vnd"]):
                raise LoadError("CLEAN_MONTH_TOTAL")
            if cumulative is None or check["opening_anchor_vnd"] != checks[0]["opening_anchor_vnd"]:
                raise LoadError("CLEAN_ANCHOR_CHAIN")
            cumulative += charge - receipt
            if cumulative != check["source_cumulative_vnd"] or cumulative != check["replay_cumulative_vnd"]:
                raise LoadError("CLEAN_ANCHOR_CHAIN")
            if (opening["debt_month"] != check["debt_month"] or
                    opening["amount_vnd"] != check["bucket_vnd"] or
                    opening["amount_vnd"] != check["standard_bucket_vnd"]):
                raise LoadError("CLEAN_BUCKET_TOTAL")
        if sum(o["amount_vnd"] for o in item["openings"]) != item["anchor"]:
            raise LoadError("CLEAN_BUCKET_TOTAL")
        if cumulative != item["anchor"]:
            raise LoadError("CLEAN_ANCHOR_CHAIN")
    if sum(b["anchor"] for b in books) != control_total:
        raise LoadError("CLEAN_CONTROL_TOTAL")


def clean_data(folder: Path) -> tuple[list[dict], dict, dict]:
    """Read only the frozen bundle. Hash all bytes before parsing any CSV or touching DB."""
    manifest_bytes = (folder / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("format_version") != CLEAN_FORMAT_VERSION:
        raise LoadError("CLEAN_FORMAT_VERSION")
    payload = {name: (folder / name).read_bytes() for name in CLEAN_FILES}
    if set(manifest.get("files_sha256", {})) != set(CLEAN_FILES) or any(
            hashlib.sha256(data).hexdigest() != manifest["files_sha256"][name]
            for name, data in payload.items()):
        raise LoadError("CLEAN_HASH_MISMATCH")
    tables = {name: list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
              for name, data in payload.items()}
    def number(value):
        result = integer(value)
        if value != "" and result is None:
            raise LoadError("CLEAN_INTEGER")
        return result
    books = []
    by_name = {}
    for row in tables[CLEAN_FILES[0]]:
        item = {"name": row["customer"], "ordinal": number(row["ordinal"]), "in_summary": True,
                "anchor": number(row["anchor_vnd"]), "flags": Counter(json.loads(row["flags"])),
                "reasons": Counter(), "csv_only": json.loads(row["csv_only"]),
                "row_counts": Counter(json.loads(row["row_counts"])),
                "checks": [], "openings": [], "legacy": []}
        metadata = json.loads(row["metadata"])
        if (set(metadata) - {"has_insurance", "commodity", "transport_mode"}
                or ("commodity" in metadata and (not isinstance(metadata["commodity"], str)
                                                 or not metadata["commodity"].strip()))
                or metadata.get("transport_mode") not in (None, "CANG", "BO")
                or ("transport_mode" in metadata and "commodity" not in metadata)):
            raise LoadError("CLEAN_METADATA")
        item.update(metadata)
        if item["name"] in by_name:
            raise LoadError("CLEAN_DUPLICATE_CUSTOMER")
        books.append(item)
        by_name[item["name"]] = item
    for row in tables[CLEAN_FILES[1]]:
        item = by_name[row["customer"]]
        check = {key: number(row[key]) if key.endswith("_vnd") else row[key] for key in
                 ("opening_anchor_vnd", "standard_bucket_vnd", "standard_source_ref", "standard_source_sha256",
                  "source_evidence_sha256")}
        check.update(debt_month=row["debt_month"] + "-01", source_charge_vnd=number(row["charge_vnd"]),
                     source_receipt_vnd=number(row["receipt_vnd"]), replay_cumulative_vnd=number(row["month_end_vnd"]),
                     source_cumulative_vnd=number(row["sheet_month_end_vnd"]), bucket_vnd=number(row["bucket_vnd"]),
                     exception_codes=json.loads(row["exception_codes"]))
        item["checks"].append(check)
        item["openings"].append({"debt_month": check["debt_month"], "amount_vnd": check["bucket_vnd"],
                                 "source_tab": row["source_tab"], "source_row": number(row["source_row"])})
    for row in tables[CLEAN_FILES[2]]:
        display = {key: json.loads(row[key]) if key in ("cells", "flags") else
                   number(row[key]) if key == "row" else row[key] for key in DISPLAY_FIELDS}
        for key in json.loads(row["null_fields"]):
            display[key] = None
        by_name[row["customer"]]["legacy"].append({"debt_month": row["debt_month"] + "-01", "kind": row["kind"],
            "source_tab": row["source_tab"], "source_row": number(row["source_row"]),
            "source_total_vnd": number(row["amount_vnd"]), "display": display})
    validate_books(books, manifest["control_total_vnd"])
    if clean_counts(books) != manifest["counts"]:
        raise LoadError("CLEAN_COUNTS")
    return books, {"manifest.json": hashlib.sha256(manifest_bytes).hexdigest()}, manifest


def clean_counts(books: list[dict]) -> dict:
    return {"customers": len(books), "months": sum(len(b["checks"]) for b in books),
            "rows": sum(len(b["legacy"]) for b in books),
            "trips": sum(r["kind"] == "trip" for b in books for r in b["legacy"]),
            "receipts": sum(r["kind"] == "receipt" for b in books for r in b["legacy"])}


def report(books: list[dict], digests: dict[str, str], run_id: str, *, loaded: bool = False) -> dict:
    reasons, flags, counts = Counter(), Counter(), Counter()
    held = []
    for item in books:
        reasons.update(item["reasons"])
        if not item["reasons"]:
            flags.update(item["flags"])
            counts.update(r["kind"] for r in item["legacy"])
        if item["reasons"]:
            held.append({"ordinal": item["ordinal"], "reason_counts": dict(sorted(item["reasons"].items()))})
    eligible = sum(not item["reasons"] for item in books)
    return {"run_id": run_id, "customers": eligible,
            "loaded_customers": sum(item.get("status") == "active" for item in books) if loaded else 0,
            "eligible_customers": eligible, "held_customers": len(held),
            "months": sum(len(item["checks"]) for item in books if not item["reasons"]),
            "row_counts": dict(sorted(counts.items())), "reason_counts": dict(sorted(reasons.items())),
            "flag_counts": dict(sorted(flags.items())), "held": held,
            "source_sha256": digests, "source_notice": "Clean manifest-bound bundle"}


def write_report(result: dict, filename: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    target = LOG_DIR / filename
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    # ASCII on stdout: a Windows console/redirect (cp1252) cannot encode Vietnamese and
    # would turn a finished report into a crash. The file above stays UTF-8.
    print(json.dumps(result, ensure_ascii=True), flush=True)


def text_sql(value: str) -> str:
    """UTF-8 text as a hex literal: customer names never pass through SQL quoting."""
    return "convert_from(decode('" + value.encode().hex() + "','hex'),'UTF8')"


def import_one(pg: Pg, item: dict, digest: str, index: int, *, cutover: int | None = None) -> str:
    if item["reasons"]:
        return "held"
    commodity = "NULL"
    if item.get("commodity"):
        commodity = text_sql(item["commodity"])
        pg.sql(f"INSERT INTO sokhach.commodity(name) VALUES ({commodity}) ON CONFLICT (name) DO NOTHING")
        commodity = f"(SELECT id FROM sokhach.commodity WHERE name={commodity})"
    mode = f"'{item['transport_mode']}'" if item.get("transport_mode") in ("CANG", "BO") else "NULL"
    customer = int(pg.value("INSERT INTO sokhach.customer(name,commodity_id,transport_mode) VALUES (" +
                            text_sql(item["name"]) + f",{commodity},{mode}) RETURNING id"))
    item["id"] = customer
    shared_cutover = cutover is not None
    if cutover is None:
        # ponytail: legacy fixture helper only; CLI always supplies one manifest-bound cutover.
        cutover = int(pg.value("INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by) "
            f"VALUES ('20/10 isolated copy','20/10 export','{digest}',now(),{item['anchor']},'isolated-loader') RETURNING id"))
    item["cutover_id"] = cutover
    call(pg, "import_cutover", customer, version(pg, customer), f"real-import-{index}", cutover,
         json.dumps(item["openings"], ensure_ascii=False), json.dumps(item["legacy"], ensure_ascii=False),
         json.dumps(item["checks"], ensure_ascii=False), item["anchor"], digest,
         actor="isolated-loader")
    try:
        call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer),
             f"real-verify-customer-{index}", None, actor="isolated-loader")
    except Exception as exc:  # noqa: BLE001  (any load failure becomes a coded reason)
        raise LoadError(reason(exc)) from None
    if shared_cutover:
        return "verified"
    call(pg, "verify_cutover", cutover, f"real-verify-{index}", None, actor="isolated-loader")
    call(pg, "activate_cutover", cutover, f"real-activate-{index}", None, actor="isolated-loader")
    call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer),
         f"real-activate-customer-{index}", None, actor="isolated-loader")
    return "active"


def reason(exc: Exception) -> str:
    if isinstance(exc, LoadError):
        return str(exc)
    match = re.search(r"CUTOVER_[A-Z_]+", str(exc))
    known = {"CUTOVER_ANCHOR_MISMATCH", "CUTOVER_CUSTOMER_NOT_FOUND",
             "CUTOVER_CUSTOMER_TOTAL_MISMATCH", "CUTOVER_CUSTOMERS_NOT_VERIFIED",
             "CUTOVER_FIFO_MISMATCH", "CUTOVER_IMPORT_CONFLICT", "CUTOVER_INPUT",
             "CUTOVER_MONTH_MISMATCH", "CUTOVER_NOT_DRAFT", "CUTOVER_NOT_FOUND",
             "CUTOVER_SOURCE_INCOMPLETE", "CUTOVER_TOTAL_MISMATCH", "CUTOVER_TRANSITION_ORDER"}
    return match.group() if match and match.group() in known else "IMPORT_ERROR"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-clean", type=Path, required=True)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument("--port", type=int, default=8782)
    parser.add_argument("--seed-only", action="store_true")
    args = parser.parse_args(argv)
    if args.port == 8777 or not 1 <= args.port <= 65535:
        parser.error("port must be 1..65535 and cannot be 8777")
    run_id = uuid.uuid4().hex
    name = volume = f"webdebit-v7-real-{run_id}"
    made_volume = False
    container_id = None
    server = None
    books, digests, manifest = [], {}, None
    exit_code = 0
    try:
        books, digests, manifest = clean_data(args.from_clean)
        def bundle_report(*, loaded=False):
            result = report(books, digests, run_id, loaded=loaded)
            result["counts"] = manifest["counts"]
            result["excluded_counts"] = manifest["excluded_counts"]
            return result
        if args.check_source:
            write_report(bundle_report(), f"source-check-{run_id}.json")
            return 2 if any(item["reasons"] for item in books) else 0
        if shutil.which("docker") is None:
            raise LoadError("DOCKER_UNAVAILABLE")
        run(["docker", "volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", volume])
        made_volume = True
        inspect_volume(volume, run_id)
        run(["docker", "run", "--detach", "--name", name,
             "--label", f"{LABEL_TEST}={LABEL_VALUE}", "--label", f"{LABEL_RUN}={run_id}",
             "--network", "none", "--volume", f"{volume}:/var/lib/postgresql",
             "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        container_id = inspect_owned(name, volume, run_id)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            logs = run(["docker", "logs", name], check=False, timeout=10)
            if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)
        else:
            raise LoadError("POSTGRES_INIT_TIMEOUT")
        pg = Pg(name, run_id)
        pg.sql(f"CREATE DATABASE {DATABASE}", database="postgres")
        for source in (SCHEMA, FUNCTIONS):
            run(["docker", "exec", "-i", *pg.env, name, "psql", "-X", "-v",
                 "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE],
                input_text=source.read_text(encoding="utf-8"))
        frozen_hex = manifest["frozen_at"].encode().hex()
        cutover = int(pg.value("INSERT INTO sokhach.cutover(name,source,source_sha256,frozen_at,control_total_vnd,created_by) "
            f"VALUES ('clean isolated copy','clean manifest','{digests['manifest.json']}',"
            f"convert_from(decode('{frozen_hex}','hex'),'UTF8')::timestamptz,"
            f"{manifest['control_total_vnd']},'isolated-loader') RETURNING id"))
        for index, item in enumerate(books, 1):
            try:
                item["status"] = import_one(pg, item, digests["manifest.json"], index, cutover=cutover)
            except Exception as exc:  # noqa: BLE001  (a held book is reported, not raised)
                item["reasons"][reason(exc)] += 1
                item["status"] = "held"
                exit_code = 1
        if not exit_code:
            call(pg, "verify_cutover", cutover, "clean-verify", None, actor="isolated-loader")
            call(pg, "activate_cutover", cutover, "clean-activate", None, actor="isolated-loader")
            for index, item in enumerate(books, 1):
                call(pg, "activate_cutover_customer", item["id"], cutover, version(pg, item["id"]),
                     f"clean-activate-{index}", None, actor="isolated-loader")
                item["status"] = "active"
        write_report(bundle_report(loaded=True), f"real-load-{run_id}.json")
        if not args.seed_only:
            class RealHandler(api.Handler):
                runner = api.Psql(name, DATABASE, "postgres")
                real_copy = True
                default_actor = "isolated-copy"
                # Host/Origin check compares against the class port; must match the bound port.
                port = args.port

            server = api.ThreadingHTTPServer(("127.0.0.1", args.port), RealHandler)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001  (failure is written to the report with a coded reason)
        result = report(books, digests, run_id)
        if manifest is not None:
            result["counts"] = manifest["counts"]
            result["excluded_counts"] = manifest["excluded_counts"]
        result["reason_counts"][reason(exc)] = result["reason_counts"].get(reason(exc), 0) + 1
        write_report(result, f"real-load-{run_id}.json")
        exit_code = 1
    finally:
        if server is not None:
            try:
                server.server_close()
            except Exception:  # noqa: BLE001  (best-effort close; failure sets the exit code)
                exit_code = 1
        if made_volume and (not args.keep or exit_code):
            try:
                owned = inspect_owned(name, volume, run_id, container_id)
                if owned:
                    run(["docker", "rm", "--force", owned])
                inspect_volume(volume, run_id)
                run(["docker", "volume", "rm", volume])
            except Exception:  # noqa: BLE001  (teardown failure is reported, not raised)
                exit_code = 1
                result = report(books, digests, run_id, loaded=True)
                result["reason_counts"]["TEARDOWN_FAILED"] = 1
                write_report(result, f"real-load-{run_id}.json")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
