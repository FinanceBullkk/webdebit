#!/usr/bin/env python3
"""Turn one Sheet XLSX export into the price snapshot the V7 API reads (specs/v7-price-queue.md).

Usage: (--spreadsheet-id ID --credentials SERVICE_ACCOUNT.json | --xlsx SHEET.xlsx)
       --output /var/lib/webdebit-sheet-sync/prices.json

The runner path reads every tab through the Sheets API (spreadsheets.readonly, the same service
account as sheet_sync_runner.py); --xlsx builds the same snapshot from a manual export.

Read-only on the Sheet side. The snapshot holds customer-tab trip rows (tab, row, container,
date, unit price, fees, TOTAL); its hash covers the rows only, so re-exporting an unchanged
Sheet keeps the same hash and an approved batch is not reported stale. The file holds names
and money: keep it outside Git with mode 600. Stdout carries counts only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile

import sheet_sync_runner as runner
import v7_load_real_copy as loader
import v7_price_match as match
import v7_sheets_api_reader as sheets_api


def snapshot(rows: list[dict], source: dict) -> dict:
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"source": source, "rows": rows, "row_count": len(rows), "sha256": hashlib.sha256(canonical).hexdigest(),
            "runner": {"created_at": dt.datetime.now(dt.UTC).isoformat(), "mode": "read-only"}}


def build(xlsx: pathlib.Path) -> dict:
    return snapshot(match.sheet_rows(xlsx), {"kind": "xlsx", "xlsx_sha256": hashlib.sha256(xlsx.read_bytes()).hexdigest()})


def build_from_api(spreadsheet_id: str, credentials_path: str, token_exchange=runner.exchange_token,
                   opener=None) -> dict:
    token = token_exchange(runner.load_credentials(credentials_path))
    tabs = sheets_api.fetch_tabs(spreadsheet_id, token, **({"opener": opener} if opener else {}))
    return snapshot(match.rows_from_scan(loader.scan_tabs(tabs)), {"kind": "sheets_api"})


def write(snapshot: dict, output: pathlib.Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                     prefix=".price-snapshot-", delete=False) as stream:
        temporary = pathlib.Path(stream.name)
        json.dump(snapshot, stream, ensure_ascii=False)
        stream.write("\n")
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)   # readers never see a half-written file
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--xlsx", type=pathlib.Path)
    source.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--output", type=pathlib.Path,
                        default=pathlib.Path(os.getenv("WEBDEBIT_PRICE_SNAPSHOT_PATH", "sheet-prices.json")))
    args = parser.parse_args(argv)
    if args.spreadsheet_id and not args.credentials:
        parser.error("set --credentials/WEBDEBIT_GOOGLE_CREDENTIALS with --spreadsheet-id")
    try:
        result = build(args.xlsx) if args.xlsx else build_from_api(args.spreadsheet_id, args.credentials)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 2
    write(result, args.output)
    print(json.dumps({"ok": True, "row_count": result["row_count"], "sha256": result["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
