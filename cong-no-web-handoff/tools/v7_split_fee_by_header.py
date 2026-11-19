#!/usr/bin/env python3
"""Tách phụ phí theo tên cột trên tab khách (TACH-PHI-TIEU-DE-01, docs/decisions/tach-phi-tieu-de-01.md).

Bộ nạp và máy giá cộng mọi ô phí của dòng tab thành một khoản Khác (PHU-PHI-01 (8)). Tab có cột mang tên rõ
(`PHÍ NEO 押车费`, `卫生证`, `过磅`, `LOCAL CHARGE 本地费用`...) thì tên cột đã nói loại phí: công cụ đọc từng ô theo tên cột
(`v7_fee_headers`) rồi lập kế hoạch tách bằng đúng hàm `plan` của máy PS (`web/v7_header_fees`), nên chỉ đổi loại, không đổi
tiền. Cột không tên hoặc tên lạ vẫn là Khác. Máy theo Sheet làm cùng việc này cho chuyến mới (bật `headers`).

Một dòng chỉ được tách khi tổng các ô phí bằng đúng TOTAL − đơn giá của dòng tab, tới từng đồng, và có ít nhất một ô mang
tên nhận ra được. Dòng khác để nguyên. Ghi bằng `rewrite_trip_fees`: Thành tiền, số dư, phân bổ phiếu thu giữ nguyên. Loại
vừa ghi mà sổ chưa có cột riêng thì thêm cột (chỉ đổi cách hiện).

Chạy trên hao dưới user của API, mặc định chỉ đếm, thêm --apply mới ghi:

    v7_split_fee_by_header.py (--xlsx SHEET.xlsx | --spreadsheet-id ID --credentials SA.json) [--customer ID ...] [--apply]

Stdout chỉ có số đếm và id khách, không có tên khách.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from functools import partial
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I không tự thêm thư mục của script
import v7_fee_headers as headers
import v7_load_real_copy as loader
from v7_api_validate import ApiError  # tools may use the web layer; never the reverse
from v7_header_fees import added_columns, plan_rows, writable, write_lines
from v7_inbox import in_month
from v7_price_queue import name_key, owners
from v7_ps_queue import fee_type_ids
from v7_psql import PsqlDirect

ACTOR = "claude"
# Giữ tên cũ cho người đọc nhật ký 19/11/2026 và test: luật nằm ở `v7_fee_headers`.
RULES, fold, field_of, tab_rows, fees_of = headers.RULES, headers.fold, headers.field_of, headers.tab_rows, headers.fees_of
plan_customer = plan_rows


def _write(runner, customer: int, version: int, item: dict) -> int:
    target, lines = item["target"], write_lines(item)
    digest = hashlib.sha256(f"tach-phi-tieu-de:{target['kind']}:{target['id']}:{json.dumps(lines, sort_keys=True)}".encode()).hexdigest()
    key = "trip_id" if target["kind"] == "trip" else "legacy_row_id"
    result = runner.run("rewrite_trip_fees", {
        "customer_id": customer, "expected_version": version, "idempotency_key": digest, "target": {key: target["id"]},
        "expected_line_ids": [x["id"] for x in item["info"]["before"]], "lines": lines,
        "source": {"kind": "sheet_header", "reason": "named_columns", "row": item["row"]["source_row"]}}, ACTOR)
    return result["version"] if type(result.get("version")) is int else runner.run("get_ledger", {"customer_id": customer}, ACTOR)["version"]


def _write_all(runner, customer: int, items: list[dict], result: dict, version: int) -> int:
    for item in items:
        version = _write(runner, customer, version, item)
        result["written"] += 1
    return version


def _columns(runner, customer: int, ready: list[dict], ids: dict) -> bool:
    """Thêm cột riêng cho loại vừa tách mà sổ chưa có; không đổi tiền, không vướng khóa tháng."""
    skip = set(ids["unclassified"]) | {ids["khac"]}
    typed = {line["fee_type_id"] for item in ready for line in item["info"]["after"]} - skip
    ledger = runner.run("get_ledger", {"customer_id": customer}, ACTOR)
    columns = added_columns(ledger, typed)
    if columns is None:
        return False
    digest = hashlib.sha256(f"tach-phi-tieu-de:cot:{customer}:{ledger['version']}:{columns}".encode()).hexdigest()
    runner.run("set_book_fee_columns", {"customer_id": customer, "expected_version": ledger["version"],
                                        "idempotency_key": digest, "fee_type_ids": columns}, ACTOR)
    return True


def read_scan(tabs: list) -> tuple[dict, list]:
    tabs = [(name, list(rows)) for name, rows in tabs]
    return loader.scan_tabs(tabs), tabs


def run(runner, tabs: list, apply: bool, customers: list[int] | None = None) -> dict[str, Any]:
    scan, raw = read_scan(tabs)
    listed = runner.run("list_customers", {}, ACTOR)["customers"]
    owned = owners([{"key": c["id"], "name": c.get("name"), "display_name": c.get("display_name"),
                     "aliases": c.get("aliases")} for c in listed if type(c.get("id")) is int])
    by_customer: dict[int, list[dict]] = {}
    for name, rows in raw:
        if name not in scan:
            continue
        customer = owned.get(name_key(name), (None, ""))[0]
        named = tab_rows(rows, scan[name].get("records", []))
        if customer is not None and named and (customers is None or customer in customers):
            by_customer.setdefault(customer, []).extend(named)
    ids = fee_type_ids(runner.run("get_fee_types", {}, ACTOR)["fee_types"])
    result: dict[str, Any] = {"status": {}, "fields": {}, "written": 0, "columns": 0, "ready_customers": [], "errors": {}}
    status, fields, errors = Counter(), Counter(), Counter()
    for customer, rows in sorted(by_customer.items()):
        ledger = runner.run("get_ledger", {"customer_id": customer}, ACTOR)
        plans = plan_rows(rows, ledger, ids)
        status.update(p["status"] for p in plans)
        ready = writable(plans)
        for item in ready:
            fields.update({f: 1 for f, v in {**item["row"]["fees"], "combined": item["row"]["combined_vnd"]}.items() if v})
        if not ready:
            continue
        result["ready_customers"].append(customer)
        if not apply:
            continue
        version = ledger["version"]
        try:
            for month in sorted({p["target"]["month"] for p in ready}):
                batch = [p for p in ready if p["target"]["month"] == month]
                version = in_month(runner, customer, version, ledger, month, f"tach-phi-tieu-de:{customer}",
                                   partial(_write_all, runner, customer, batch, result))
            result["columns"] += _columns(runner, customer, ready, ids)
        except ApiError as exc:   # in_month đã khóa lại; sổ khác vẫn chạy, lần sau thử lại sổ này.
            errors[exc.code] += 1
    result.update(status=dict(status), fields=dict(fields), errors=dict(errors))
    return result


def read_tabs(args) -> list:
    if args.xlsx:
        return list(loader.workbook_rows(args.xlsx))
    import sheet_sync_runner
    import v7_sheets_api_reader as sheets_api
    token = sheet_sync_runner.exchange_token(sheet_sync_runner.load_credentials(args.credentials))
    return list(sheets_api.fetch_tabs(args.spreadsheet_id, token))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--xlsx", type=Path)
    source.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--database", default="webdebit_v7")
    parser.add_argument("--db-user", default="v7_app")
    parser.add_argument("--customer", type=int, action="append", help="chỉ chạy các khách này; bỏ trống là mọi khách")
    parser.add_argument("--apply", action="store_true", help="ghi thật; không có thì chỉ đếm")
    args = parser.parse_args()
    if not (args.xlsx or args.spreadsheet_id):
        parser.error("cần --xlsx hoặc --spreadsheet-id (hay WEBDEBIT_SHEET_ID)")
    result = run(PsqlDirect(args.socket_dir, args.database, args.db_user), read_tabs(args), args.apply, args.customer)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
