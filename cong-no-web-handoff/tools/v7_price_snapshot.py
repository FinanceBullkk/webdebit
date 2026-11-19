#!/usr/bin/env python3
"""Turn one Sheet XLSX export into the price and receipt snapshots the V7 API reads
(specs/v7-price-queue.md, specs/v7-receipt-queue.md).

Usage: (--spreadsheet-id ID --credentials SERVICE_ACCOUNT.json | --xlsx SHEET.xlsx)
       --output /var/lib/webdebit-sheet-sync/prices.json [--receipts-output …/receipts.json]

The runner path reads every tab through the Sheets API (spreadsheets.readonly, the same service
account as sheet_sync_runner.py); --xlsx builds the same snapshot from a manual export. One read
feeds both snapshots; the receipt file defaults to receipts.json beside the price file. The same read also writes details.json
beside it from the "CHI TIET ..." tabs (SO-CHI-TIET-01, display only).

Read-only on the Sheet side. The price snapshot holds customer-tab trip rows (tab, row, container,
date, unit price, fees, TOTAL), the receipt snapshot the payment rows (tab, row, month, amount,
payment-date text); each hash covers its rows only, so re-exporting an unchanged Sheet keeps the
same hash and an approved batch is not reported stale. The files hold names and money: keep them
outside Git with mode 600. Stdout carries counts only.
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
import v7_fee_headers as fee_headers
import v7_load_real_copy as loader
import v7_price_match as match
import v7_receipt_queue as receipt_queue  # web layer, on the path through v7_price_match
import v7_sheets_api_reader as sheets_api
import v7_tab_health as tab_health


def snapshot(rows: list[dict], source: dict, tabs: dict | None = None) -> dict:
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    result = {"source": source, "rows": rows, "row_count": len(rows), "sha256": hashlib.sha256(canonical).hexdigest(),
              "runner": {"created_at": dt.datetime.now(dt.UTC).isoformat(), "mode": "read-only"}}
    if tabs is not None:
        result["tabs"] = tabs   # KIEM-TAB-01: kết luận sức khỏe từng tab, cùng một lượt quét và cùng một file với `rows`
    return result


def snapshots(scan: dict, source: dict, tabs=None) -> tuple[dict, dict]:
    """(prices, receipts) from one scan of the customer tabs; both carry the tabs' health (`v7_tab_health`) from that same scan.
    `tabs`: the raw rows the scan came from, so a finding can name its cell; without them the health has no cell names."""
    health = tab_health.scan_health(scan, tabs)
    rows = match.rows_from_scan(scan)
    if tabs is not None:
        # TACH-PHI-TIEU-DE-01: tiền theo loại khi cột phí của tab có tên rõ và các ô cộng đúng TOTAL − đơn giá; máy tự tách.
        named = fee_headers.scan_fees(tabs, scan)
        for row in rows:
            fees = named.get((row["customer_tab"], row["source_row"]))
            if fees:
                row["sheet_fees"] = fees
    return (snapshot(rows, source, health), snapshot(receipt_queue.rows_from_scan(scan), source, health))


def read_tabs(tabs) -> list:
    """Raw tabs as lists, so the scan and the health read the same rows (a reader may hand over generators)."""
    return [(name, list(rows)) for name, rows in tabs]


def build_all(xlsx: pathlib.Path) -> tuple[dict, dict]:
    tabs = read_tabs(loader.workbook_rows(xlsx))
    return snapshots(loader.scan_tabs(tabs), {"kind": "xlsx", "xlsx_sha256": hashlib.sha256(xlsx.read_bytes()).hexdigest()}, tabs)


def build_all_from_api(spreadsheet_id: str, credentials_path: str, token_exchange=runner.exchange_token,
                       opener=None) -> tuple[dict, dict]:
    token = token_exchange(runner.load_credentials(credentials_path))
    tabs = read_tabs(sheets_api.fetch_tabs(spreadsheet_id, token, **({"opener": opener} if opener else {})))
    return snapshots(loader.scan_tabs(tabs), {"kind": "sheets_api"}, tabs)


def with_details(tabs: list, source: dict) -> tuple[dict, dict, dict]:
    """(prices, receipts, details) from one read. Imported here because the web layer joins the path only through v7_price_match."""
    import v7_detail_queue as details
    tabs = read_tabs(tabs)
    return (*snapshots(loader.scan_tabs(tabs), source, tabs), snapshot(details.rows_from_tabs(tabs), source))


def build_with_details(xlsx: pathlib.Path) -> tuple[dict, dict, dict]:
    return with_details(list(loader.workbook_rows(xlsx)), {"kind": "xlsx", "xlsx_sha256": hashlib.sha256(xlsx.read_bytes()).hexdigest()})


def build_with_details_from_api(spreadsheet_id: str, credentials_path: str, token_exchange=runner.exchange_token,
                                opener=None) -> tuple[dict, dict, dict]:
    token = token_exchange(runner.load_credentials(credentials_path))
    return with_details(list(sheets_api.fetch_tabs(spreadsheet_id, token, **({"opener": opener} if opener else {}))), {"kind": "sheets_api"})


def build(xlsx: pathlib.Path) -> dict:
    return build_all(xlsx)[0]


def build_from_api(spreadsheet_id: str, credentials_path: str, token_exchange=runner.exchange_token,
                   opener=None) -> dict:
    return build_all_from_api(spreadsheet_id, credentials_path, token_exchange, opener)[0]


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
    parser.add_argument("--receipts-output", type=pathlib.Path,
                        default=os.getenv("WEBDEBIT_RECEIPT_SNAPSHOT_PATH") or None)
    parser.add_argument("--details-output", type=pathlib.Path,
                        default=os.getenv("WEBDEBIT_DETAIL_SNAPSHOT_PATH") or None)
    args = parser.parse_args(argv)
    if args.spreadsheet_id and not args.credentials:
        parser.error("set --credentials/WEBDEBIT_GOOGLE_CREDENTIALS with --spreadsheet-id")
    try:
        prices, receipts, detail = (build_with_details(args.xlsx) if args.xlsx
                                    else build_with_details_from_api(args.spreadsheet_id, args.credentials))
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 2
    write(prices, args.output)
    write(receipts, pathlib.Path(args.receipts_output or args.output.with_name("receipts.json")))
    write(detail, pathlib.Path(args.details_output or args.output.with_name("details.json")))
    print(json.dumps({"ok": True, "row_count": prices["row_count"], "sha256": prices["sha256"],
                      "receipt_row_count": receipts["row_count"], "receipt_sha256": receipts["sha256"],
                      "detail_row_count": detail["row_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
