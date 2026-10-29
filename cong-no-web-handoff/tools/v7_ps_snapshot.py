#!/usr/bin/env python3
"""Read the bill workbook's CONT_MASTER tab into the PS fee snapshot (specs/v7-phu-phi-tu-ps.md).

Usage: --spreadsheet-id ID --credentials SERVICE_ACCOUNT.json --output /var/lib/webdebit-sheet-sync/ps.json

Read-only, `spreadsheets.readonly`, the same service account as sheet_sync_runner.py. One
values:batchGet reads CONT_MASTER and the customer review mapping (booking owner -> V7 name).
Only rows carrying PS money, Bảo hiểm or a Health/KĐ mark are kept. Amounts are never rounded
here: rounding belongs to the bill workbook, so odd cells become problems for review. The hash
covers rows and aliases. The file holds names and money: keep it outside Git with mode 600.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

import sheet_sync_runner as runner
import webdebit_export_connector as connector

API = "https://sheets.googleapis.com/v4/spreadsheets/"
RANGE = "CONT_MASTER!A2:AC20000"   # row 1 holds group titles, row 2 the headers
COLUMNS = {"key": "Khóa", "container": "Số cont", "date": "Ngày đóng", "bill_month": "Tháng bill",
           "owner": "Chủ hàng", "booking": "Booking", "ps_match_count": "PS: số dòng khớp",
           "neo": "PS Neo", "dien": "PS Điện", "ghep": "PS Ghép", "combined": "PS Health+KĐ",
           "health": "PS cờ Health", "kd": "PS cờ KĐ", "khac": "PS Khác", "ps_source": "PS nguồn",
           "bao_hiem": "Bảo hiểm", "error": "Lỗi"}
FEES = ("neo", "dien", "ghep", "khac", "bao_hiem")
MIN_VND = 1000   # PHU-PHI-01 (11): smaller PS cells are typing mistakes
SERIAL_EPOCH = dt.date(1899, 12, 30)


def text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value if value is not None else "")).split())


def amount(value: Any) -> tuple[int | None, str | None]:
    """Cell -> (VND, problem). Blank and 0 are no fee; problems never become money."""
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, "PS_BAD_AMOUNT"
    if isinstance(value, float):
        if not value.is_integer():
            return None, "PS_BAD_AMOUNT"
        value = int(value)
    if isinstance(value, str):
        raw = value.strip()
        if not re.fullmatch(r"[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+", raw):
            return None, "PS_BAD_AMOUNT"
        value = int(raw.replace(",", ""))
    if not isinstance(value, int) or value < 0:
        return None, "PS_BAD_AMOUNT"
    if value == 0:
        return None, None
    return (value, None) if value >= MIN_VND else (None, "PS_TYPO")


def day(value: Any) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 <= value < 100000:
        return (SERIAL_EPOCH + dt.timedelta(days=int(value))).isoformat()
    try:
        return dt.datetime.strptime(text(value), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def flag(value: Any) -> bool:
    return value is True or text(value).upper() in ("TRUE", "CÓ")


def parse_rows(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values:
        raise ValueError("CONT_MASTER empty")
    header = [text(cell) for cell in values[0]]
    missing = [name for name in COLUMNS.values() if name not in header]
    if missing:
        raise ValueError("CONT_MASTER header mismatch")
    index = {field: header.index(name) for field, name in COLUMNS.items()}
    rows = []
    for offset, raw in enumerate(values[1:], start=3):
        cell = {field: raw[i] if i < len(raw) else None for field, i in index.items()}
        fees, problems = {}, []
        for field in FEES:
            fees[field], problem = amount(cell[field])
            if problem:
                problems.append({"field": field, "code": problem, "value": text(cell[field])})
        combined, problem = amount(cell["combined"])
        if problem:
            problems.append({"field": "combined", "code": problem, "value": text(cell["combined"])})
        health, kd = flag(cell["health"]), flag(cell["kd"])
        if not (any(v is not None for v in fees.values()) or combined or problems or health or kd):
            continue
        count = cell["ps_match_count"]
        rows.append({
            "key": text(cell["key"]), "source_row": offset,
            "container": "".join(text(cell["container"]).upper().split()), "date": day(cell["date"]),
            "bill_month": text(cell["bill_month"]), "owner": text(cell["owner"]),
            "booking": "".join(text(cell["booking"]).upper().split()),
            "ps_match_count": int(count) if isinstance(count, (int, float)) and not isinstance(count, bool)
            else int(text(count)) if text(count).isdigit() else None,
            "fees": {k: None if v is None else str(v) for k, v in fees.items()},
            "combined_vnd": None if combined is None else str(combined),
            "health": health, "kd": kd, "ps_source": text(cell["ps_source"]),
            "source_error": text(cell["error"]) or None, "problems": problems})
    return rows


def fetch(spreadsheet_id: str, token: str, opener: Callable[..., Any] = urllib.request.urlopen) -> list[list[list[Any]]]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", spreadsheet_id):
        raise ValueError("invalid spreadsheet ID")

    def batch(mapping_range: str) -> list:
        query = [("ranges", RANGE), ("ranges", mapping_range), ("valueRenderOption", "UNFORMATTED_VALUE"),
                 ("dateTimeRenderOption", "SERIAL_NUMBER"), ("majorDimension", "ROWS")]
        url = API + urllib.parse.quote(spreadsheet_id) + "/values:batchGet?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with opener(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8")).get("valueRanges", [])
    ranges = connector.fetch_with_legacy_mapping(batch)
    if len(ranges) != 2:
        raise ValueError("Sheets API returned a different number of ranges")
    return [value_range.get("values", []) for value_range in ranges]


def snapshot(rows: list[dict], aliases: dict[str, str]) -> dict:
    canonical = json.dumps({"rows": rows, "customer_aliases": aliases}, ensure_ascii=False,
                           separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"source": {"kind": "sheets_api", "range": RANGE}, "rows": rows, "row_count": len(rows),
            "customer_aliases": aliases, "sha256": hashlib.sha256(canonical).hexdigest(),
            "runner": {"created_at": dt.datetime.now(dt.UTC).isoformat(), "mode": "read-only"}}


def build(spreadsheet_id: str, credentials_path: str, token_exchange=runner.exchange_token, opener=None) -> dict:
    token = token_exchange(runner.load_credentials(credentials_path))
    master, mapping = fetch(spreadsheet_id, token, **({"opener": opener} if opener else {}))
    return snapshot(parse_rows(master), connector.parse_review_mapping(mapping))


def write(result: dict, output: pathlib.Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                     prefix=".ps-snapshot-", delete=False) as stream:
        temporary = pathlib.Path(stream.name)
        json.dump(result, stream, ensure_ascii=False)
        stream.write("\n")
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)   # readers never see a half-written file
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_PS_SHEET_ID") or os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--output", type=pathlib.Path,
                        default=pathlib.Path(os.getenv("WEBDEBIT_PS_SNAPSHOT_PATH", "ps.json")))
    args = parser.parse_args(argv)
    if not args.spreadsheet_id or not args.credentials:
        parser.error("set --spreadsheet-id/WEBDEBIT_PS_SHEET_ID and --credentials/WEBDEBIT_GOOGLE_CREDENTIALS")
    try:
        result = build(args.spreadsheet_id, args.credentials)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 2
    write(result, args.output)
    print(json.dumps({"ok": True, "row_count": result["row_count"], "sha256": result["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
