#!/usr/bin/env python3
"""Tách phụ phí theo tên cột trên tab khách (TACH-PHI-TIEU-DE-01, docs/decisions/tach-phi-tieu-de-01.md).

Bộ nạp và máy giá cộng mọi ô phí của dòng tab thành một khoản Khác (PHU-PHI-01 (8)). Tab có cột mang tên rõ
(`PHÍ NEO 押车费`, `卫生证`, `BAO HIEM`...) thì tên cột đã nói loại phí: công cụ đọc từng ô theo tên cột rồi lập kế hoạch tách
bằng đúng hàm `plan` của máy PS (MAY-PS-01), nên chỉ đổi loại, không đổi tiền. Cột không tên hoặc tên lạ vẫn là Khác.

Một dòng chỉ được tách khi tổng các ô phí bằng đúng TOTAL − đơn giá của dòng tab, tới từng đồng, và có ít nhất một ô mang
tên nhận ra được. Dòng khác để nguyên. Ghi bằng `rewrite_trip_fees`: Thành tiền, số dư, phân bổ phiếu thu giữ nguyên.

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
import unicodedata
from collections import Counter
from functools import partial
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_load_real_copy as loader
from v7_api_validate import ApiError  # tools may use the web layer; never the reverse
from v7_inbox import in_month
from v7_price_queue import container_key, name_key, owners
from v7_ps_queue import GENERATED_NOTES, fee_type_ids, match, plan, pool
from v7_psql import PsqlDirect

ACTOR = "claude"
# Tên cột → trường của máy PS. Một tiêu đề khớp từ hai loại trở lên ("Neo / Phi dien / Dong ghep") là Khác.
# 卫生证 (Health cert) vào loại gộp "Health + KĐ" vì đó là cột HC FEE mặc định của sổ (COT-PHU-PHI-01); debit note in như nhau.
RULES = (("neo", ("NEO", "押车", "OVERSTAY")),
         ("ghep", ("GHEP", "拼柜", "TRUCKING")),
         ("dien", ("DIEN", "发电", "插电", "电费", "GENSET", "GENERATOR")),
         ("combined", ("卫生证", "HEALTH", "HC FEE")),
         ("bao_hiem", ("BAO HIEM", "保险", "INSURANCE")))
WRITABLE = ("READY", "MONTH_LOCKED")


def fold(text: str) -> str:
    """Hoa, bỏ dấu tiếng Việt, giữ chữ Hán; khác `loader.normalized` (bỏ mọi chữ ngoài A-Z0-9)."""
    text = unicodedata.normalize("NFD", str(text or "").upper().replace("Đ", "D"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).replace("/", " ").split())


def field_of(header: str) -> str:
    text = fold(header)
    found = {field for field, words in RULES if any(word in text for word in words)}
    return found.pop() if len(found) == 1 else "khac"


def _header(cells: dict[str, str]) -> dict[str, str]:
    """Cột của các khóa nhận ra được (cột trái nhất thắng, như bộ nạp)."""
    detected: dict[str, str] = {}
    for col, value in sorted(cells.items(), key=lambda item: loader.col_num(item[0])):
        key = loader.header_key(loader.normalized(value))
        if key and key not in detected:
            detected[key] = col
    return detected


def tab_rows(rows: list, records: list[dict]) -> list[dict]:
    """Dòng chuyến của một tab kèm phụ phí theo tên cột; `records` là kết quả `scan_tabs` của chính tab đó."""
    trips = {r["row"]: r for r in records if r["kind"] == "trip"}
    out, header, keys = [], {}, {}
    for row_no, cells in rows:
        detected = _header(cells)
        if {"container", "total", "price"} <= detected.keys() and not (
                keys.get("container") and detected["container"] != keys["container"]):
            header, keys = cells, detected
            continue
        record = trips.get(row_no)
        if record is None or not keys:
            continue
        out.append(fees_of(record, header, keys))
    return out


def fees_of(record: dict, header: dict[str, str], keys: dict[str, str]) -> dict:
    cells, details = record["cells"], record.get("details") or {}
    row = {"source_row": record["row"], "month": record["month"], "container": container_key(record.get("container")),
           "date": record.get("date"), "booking": None, "fees": {}, "combined_vnd": None, "status": "SHEET_OK"}
    unit, total = details.get("unit_price"), record.get("amount")
    if "COLUMN_SHIFTED" in record.get("flags", set()):
        return {**row, "status": "SHEET_SHIFTED"}
    if unit is None or total is None:
        return {**row, "status": "SHEET_NO_PRICE"}
    left = max(loader.col_num(keys[k]) for k in ("date", "from", "to") if keys.get(k)) if any(
        keys.get(k) for k in ("date", "from", "to")) else loader.col_num(keys["container"])
    fees: Counter = Counter()
    for number in range(left + 1, loader.col_num(keys["price"])):
        col = loader.col_name(number)
        value = str(cells.get(col) or "").strip()
        if not value:
            continue
        amount = loader.rounded(value)
        if amount is None:
            return {**row, "status": "SHEET_BAD_CELL"}
        if amount:
            fees[field_of(header.get(col, ""))] += amount
    if sum(fees.values()) != total - unit:
        return {**row, "status": "SHEET_DIFF"}
    if not set(fees) - {"khac"}:
        return {**row, "status": "NO_NAMED"}
    combined = fees.pop("combined", None)
    return {**row, "fees": dict(fees), "combined_vnd": combined}


def keeps_notes(before: list[dict], after: list[dict]) -> bool:
    """Như máy PS: thay khoản mà làm mất ghi chú người đã gõ thì để người bấm."""
    notes = Counter(x.get("note") for x in before if x.get("note") and x["note"] not in GENERATED_NOTES)
    return not notes - Counter(x.get("note") for x in after if x.get("note"))


def plan_customer(rows: list[dict], ledger: dict, ids: dict) -> list[dict]:
    candidates = pool(ledger)
    plans = []
    for row in rows:
        if row["status"] != "SHEET_OK":
            plans.append({"status": row["status"], "row": row})
            continue
        found, _ = match(row, candidates) if row["container"] else ([], "")
        if len(found) != 1:
            plans.append({"status": "NOT_FOUND" if not found else "AMBIGUOUS", "row": row})
            continue
        target = found[0]
        status, info = plan(row, target, ids)
        if status in WRITABLE and not keeps_notes(info["before"], info["after"]):
            status = "NOTE_LOST"
        plans.append({"status": status, "row": row, "target": target, "info": info})
    used = Counter((p["target"]["kind"], p["target"]["id"]) for p in plans if p.get("target"))
    for item in plans:
        if item.get("target") and used[(item["target"]["kind"], item["target"]["id"])] > 1:
            item["status"] = "AMBIGUOUS"
    return plans


def _write(runner, customer: int, version: int, item: dict) -> int:
    target, info = item["target"], item["info"]
    lines = [{k: x[k] for k in ("fee_type_id", "amount_vnd", "note")} for x in info["after"]]
    digest = hashlib.sha256(f"tach-phi-tieu-de:{target['kind']}:{target['id']}:{json.dumps(lines, sort_keys=True)}".encode()).hexdigest()
    key = "trip_id" if target["kind"] == "trip" else "legacy_row_id"
    result = runner.run("rewrite_trip_fees", {
        "customer_id": customer, "expected_version": version, "idempotency_key": digest, "target": {key: target["id"]},
        "expected_line_ids": [x["id"] for x in info["before"]], "lines": lines,
        "source": {"kind": "sheet_header", "reason": "named_columns", "row": item["row"]["source_row"]}}, ACTOR)
    return result["version"] if type(result.get("version")) is int else runner.run("get_ledger", {"customer_id": customer}, ACTOR)["version"]


def _write_all(runner, customer: int, items: list[dict], result: dict, version: int) -> int:
    for item in items:
        version = _write(runner, customer, version, item)
        result["written"] += 1
    return version


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
    result: dict[str, Any] = {"status": {}, "fields": {}, "written": 0, "ready_customers": [], "errors": {}}
    status, fields, errors = Counter(), Counter(), Counter()
    for customer, rows in sorted(by_customer.items()):
        ledger = runner.run("get_ledger", {"customer_id": customer}, ACTOR)
        plans = plan_customer(rows, ledger, ids)
        status.update(p["status"] for p in plans)
        ready = [p for p in plans if p["status"] in WRITABLE]
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--xlsx", type=Path)
    source.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--database", default="webdebit_v7")
    parser.add_argument("--db-user", default="v7_app")
    parser.add_argument("--customer", type=int, action="append", help="chỉ chạy các khách này; bỏ trống là mọi khách")
    parser.add_argument("--apply", action="store_true", help="ghi thật; không có thì chỉ đếm")
    args = parser.parse_args()
    result = run(PsqlDirect(args.socket_dir, args.database, args.db_user), read_tabs(args), args.apply, args.customer)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
