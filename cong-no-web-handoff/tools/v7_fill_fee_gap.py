#!/usr/bin/env python3
"""Bù phụ phí theo ô TOTAL của Sheet ở dòng sổ gốc (PHU-PHI-BU-01, docs/decisions/phu-phi-bu-01.md).

Bộ nạp chỉ đọc cột có tiêu đề OTHER FEE/PHU PHI, nên tiền ở cột không tiêu đề nằm trong TOTAL mà không có trong phụ phí. Công cụ
ghi phần thiếu thành một khoản Khác (âm thì Giảm trừ), chỉ ở dòng mà TOTAL bằng đúng đơn giá + mọi ô tiền bên trái cột giá. Dòng
khác để nguyên cho người xem. Dùng `rewrite_trip_fees` (đường `fill`): TOTAL và số dư không đổi, không phân bổ lại phiếu thu.

Chạy một lần trên hao dưới user của API, mặc định chỉ đếm, thêm --apply mới ghi:

    v7_fill_fee_gap.py [--customer ID ...] [--apply]

Stdout chỉ có số đếm và id khách, không có tên khách.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from v7_api_validate import ApiError  # tools may use the web layer; never the reverse
from v7_inbox import in_month
from v7_ps_queue import GAP_NOTE, GENERATED_NOTES
from v7_psql import PsqlDirect

ACTOR = "claude"   # người ghi trong Lịch sử; mở/khóa tháng do in_month ghi là máy, để lượt nền khóa lại nếu công cụ chết giữa chừng.
MAX_LINES = 10     # giới hạn của rewrite_trip_fees
MIN_MONEY = 100000  # ô nhỏ hơn là STT hoặc ngày dạng số (46332.0), không phải tiền.
NUMBER = re.compile(r"-?\d+(\.\d+)?([eE][+-]?\d+)?")


def _column(name: str) -> int:
    number = 0
    for letter in name:
        number = number * 26 + ord(letter) - 64
    return number


def explained(cells: dict[str, Any], unit: int, counted: int) -> bool:
    """TOTAL = đơn giá + mọi ô tiền bên trái cột giá. Cột giá là ô đầu tiên bằng đúng đơn giá."""
    numbers = sorted((_column(col), Decimal(value)) for col, value in cells.items()
                     if isinstance(value, str) and NUMBER.fullmatch(value))
    price = next((col for col, value in numbers if value == unit), None)
    if price is None:
        return False
    return sum((value for col, value in numbers if col < price and abs(value) >= MIN_MONEY), Decimal(0)) == counted - unit


def plan_row(row: dict[str, Any], types: dict[str, int]) -> dict[str, Any] | None:
    """Kế hoạch của một dòng sổ gốc; None khi dòng không lệch. `types`: system_key → id loại phí."""
    current = row.get("current")
    if row.get("kind") != "trip" or not row.get("counted_differs") or not current:
        return None
    unit, counted = int(current["unit_price_vnd"]), int(current["counted_vnd"])
    before = row.get("fee_lines") or []
    gap = counted - unit - sum(int(line["amount_vnd"]) for line in before)
    if not gap:
        return None
    if not explained((row.get("display") or {}).get("cells") or {}, unit, counted) or len(before) >= MAX_LINES:
        return {"status": "UNEXPLAINED", "gap_vnd": gap}

    def kind_of(amount: int) -> int:
        return types["discount"] if amount < 0 else types["other"]
    lines = []
    for line in before:
        amount, note = int(line["amount_vnd"]), line.get("note")
        # rewrite_trip_fees không nhận lại loại "Phụ phí ban đầu": đổi sang Khác/Giảm trừ, cùng nhóm chưa phân loại với nó.
        kept = kind_of(amount) if line["fee_type_id"] == types["initial"] else line["fee_type_id"]
        lines.append({"fee_type_id": kept, "amount_vnd": str(amount), "note": None if note in GENERATED_NOTES else note})
    lines.append({"fee_type_id": kind_of(gap), "amount_vnd": str(gap), "note": GAP_NOTE})
    return {"status": "READY", "row_id": row["id"], "month": str(row["month"])[:7], "gap_vnd": gap,
            "expected_line_ids": [line["id"] for line in before], "lines": lines}


def _write(runner, customer: int, version: int, plan: dict[str, Any]) -> int:
    digest = hashlib.sha256(f"bu-phu-phi:{plan['row_id']}:{json.dumps(plan['lines'], sort_keys=True)}".encode()).hexdigest()
    result = runner.run("rewrite_trip_fees", {
        "customer_id": customer, "expected_version": version, "idempotency_key": digest,
        "target": {"legacy_row_id": plan["row_id"]}, "expected_line_ids": plan["expected_line_ids"], "lines": plan["lines"],
        "source": {"kind": "sheet_total", "reason": "unlabeled_columns"}}, ACTOR)
    return result["version"] if type(result.get("version")) is int else runner.run("get_ledger", {"customer_id": customer}, ACTOR)["version"]


def _write_all(runner, customer: int, plans: list[dict[str, Any]], result: dict[str, Any], version: int) -> int:
    for plan in plans:
        version = _write(runner, customer, version, plan)
        result["written"] += 1
    return version


def run(runner, apply: bool, customers: list[int] | None = None) -> dict[str, Any]:
    types = {row["system_key"]: row["id"] for row in runner.run("get_fee_types", {}, ACTOR)["fee_types"] if row.get("system_key")}
    ids = customers if customers is not None else [row["id"] for row in runner.run("list_customers", {}, ACTOR)["customers"]]
    result: dict[str, Any] = {"ready": 0, "unexplained": 0, "written": 0, "gap_net_vnd": 0, "gap_abs_vnd": 0,
                              "ready_customers": [], "unexplained_customers": []}
    errors: Counter[str] = Counter()
    for customer in ids:
        ledger = runner.run("get_ledger", {"customer_id": customer}, ACTOR)
        plans = [plan for plan in (plan_row(row, types) for row in ledger.get("legacy_rows") or []) if plan]
        ready = [plan for plan in plans if plan["status"] == "READY"]
        result["unexplained"] += len(plans) - len(ready)
        if len(plans) > len(ready):
            result["unexplained_customers"].append(customer)
        if not ready:
            continue
        result["ready"] += len(ready)
        result["ready_customers"].append(customer)
        result["gap_net_vnd"] += sum(plan["gap_vnd"] for plan in ready)
        result["gap_abs_vnd"] += sum(abs(plan["gap_vnd"]) for plan in ready)
        if not apply:
            continue
        version = ledger["version"]
        try:
            for month in sorted({plan["month"] for plan in ready}):
                plans_of_month = [plan for plan in ready if plan["month"] == month]
                version = in_month(runner, customer, version, ledger, month, f"bu-phu-phi:{customer}",
                                   partial(_write_all, runner, customer, plans_of_month, result))
        except ApiError as exc:   # in_month đã khóa lại; dòng còn lại của sổ này để lần chạy sau, sổ khác vẫn chạy.
            errors[exc.code] += 1
    result["errors"] = dict(errors)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--database", default="webdebit_v7")
    parser.add_argument("--db-user", default="v7_app")
    parser.add_argument("--customer", type=int, action="append", help="chỉ chạy các khách này; bỏ trống là mọi khách")
    parser.add_argument("--apply", action="store_true", help="ghi thật; không có thì chỉ đếm")
    args = parser.parse_args()
    result = run(PsqlDirect(args.socket_dir, args.database, args.db_user), args.apply, args.customer)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
