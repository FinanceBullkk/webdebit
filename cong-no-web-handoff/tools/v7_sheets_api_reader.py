"""Read every customer tab through the Sheets API into the loader's cell grid (read-only).

The XLSX reader (`v7_load_real_copy.workbook_rows`) yields raw stored cell values: numbers as
stored, dates as serial numbers, formulas as cached results. `values:batchGet` with
UNFORMATTED_VALUE and SERIAL_NUMBER returns the same values, so `scan_tabs` parses both alike.
Only `spreadsheets.readonly` is needed; a full XLSX export (about 32MB) exceeds the Drive
export limit, which is why the price runner uses this path.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import v7_load_real_copy as loader

API = "https://sheets.googleapis.com/v4/spreadsheets/"
BATCH = 25   # ranges per batchGet; keeps the URL short with long Vietnamese tab names
WORKERS = 4  # batchGet calls in flight; about 11 requests a run stays far below the per-minute quota


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):          # XLSX stores booleans as 1/0
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value).strip()


def range_start(a1: str) -> tuple[int, int]:
    """'Tab'!B3:Z9 -> (3, 2). A whole-sheet range starts at A1."""
    match = re.search(r"!([A-Z]+)(\d+)", a1 or "")
    return (int(match.group(2)), loader.col_num(match.group(1))) if match else (1, 1)


def grid_rows(values: list[list[Any]], start_row: int = 1, start_col: int = 1) -> list[tuple[int, dict[str, str]]]:
    rows = []
    for offset, raw in enumerate(values or []):
        cells = {loader.col_name(start_col + index): text
                 for index, value in enumerate(raw) if (text := cell_text(value))}
        if cells:   # empty rows carry nothing the parser reads
            rows.append((start_row + offset, cells))
    return rows


def quote(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def fetch_tabs(spreadsheet_id: str, token: str,
               opener: Callable[..., Any] = urllib.request.urlopen) -> Iterator[tuple[str, list]]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", spreadsheet_id):
        raise ValueError("invalid spreadsheet ID")

    def get(url: str) -> dict:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with opener(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    base = API + urllib.parse.quote(spreadsheet_id)
    meta = get(base + "?fields=" + urllib.parse.quote("sheets.properties.title"))
    titles = [sheet["properties"]["title"] for sheet in meta.get("sheets", [])]
    chosen = {name.strip() for name in loader.PREFERRED_RAW_TABS}
    titles = [t for t in titles if not (t.strip() in chosen and t not in loader.PREFERRED_RAW_TABS)]
    batches = [titles[start:start + BATCH] for start in range(0, len(titles), BATCH)]

    def fetch(batch: list[str]) -> dict:
        query = [("ranges", quote(title)) for title in batch] + [
            ("valueRenderOption", "UNFORMATTED_VALUE"), ("dateTimeRenderOption", "SERIAL_NUMBER"),
            ("majorDimension", "ROWS")]
        return get(base + "/values:batchGet?" + urllib.parse.urlencode(query))

    # Tải các lô song song (nút "Làm mới" cần nhanh); map giữ đúng thứ tự tab như đọc tuần tự.
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        payloads = list(pool.map(fetch, batches))
    for batch, payload in zip(batches, payloads, strict=True):
        ranges = payload.get("valueRanges", [])
        if len(ranges) != len(batch):
            raise ValueError("Sheets API returned a different number of tabs")
        for title, value_range in zip(batch, ranges, strict=True):
            row, col = range_start(value_range.get("range", ""))
            yield title.strip(), grid_rows(value_range.get("values", []), row, col)
