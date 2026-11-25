#!/usr/bin/env python3
"""Giữ một tháng mở ở các sổ còn chuyến chưa giá, rồi khóa lại tới hạn (WEB-CHINH-01, tháng 11/2026).

Từ 1/12/2026 người nhập thôi gõ Sheet sổ nợ, giá và phụ phí tháng 11 nhập trễ phải gõ trên web. Tháng không có cờ khóa thì hết tháng
tự khóa (V7-SO), nên sổ còn chuyến chưa giá sẽ khóa mất. Người dùng chốt 25/11/2026 "Mở sẵn T11": mở tới hết 15/12 rồi khóa lại.
Công cụ không đổi luật khóa: nó gọi đúng lệnh mở/khóa tháng của sổ (`set_month_lock`), mỗi lần là một dòng Lịch sử có người làm
`ACTOR`, như người bấm ổ khóa.

    v7_giu_mo_thang.py --month 2026-11 --open   [--apply]   # ghi cờ mở ở sổ còn việc giá của tháng đó
    v7_giu_mo_thang.py --month 2026-11 --relock [--apply]   # khóa lại tháng mà chính công cụ đã mở, người chưa đụng tới

Không có --apply thì chỉ đếm. Chạy lại được: sổ đã mở thì bỏ qua, sổ người đã khóa thì không mở lại, sổ đã khóa lại thì bỏ qua.
Ý người là lần mở/khóa gần nhất không phải của máy theo Sheet (`AUTO_ACTOR`): máy chỉ mở–ghi–khóa trong một lượt, không phải lựa chọn.
Lượt nền của máy theo Sheet chỉ khóa lại tháng do chính nó mở (`machine_left_open`), không đụng tháng công cụ này mở.

Stdout chỉ có số đếm và id sổ, không có tên khách.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from v7_api_validate import ApiError  # tools may use the web layer; never the reverse
from v7_psql import PsqlDirect

ACTOR = "giu-mo-thang"   # người làm trong Lịch sử; khác máy theo Sheet để lượt nền không khóa lại tháng này
MACHINE = "may-theo-sheet"   # = v7_inbox.AUTO_ACTOR (test giữ hai tên khớp); không nạp v7_inbox để công cụ nhẹ
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
TRIES = 3   # sổ đổi phiên bản giữa lúc đọc và ghi (người đang gõ, máy đang ghi): đọc lại rồi thử lại


def unpriced(ledger: dict[str, Any], month: str) -> int:
    """Việc còn cần tháng mở ở tháng `month` (yyyy-mm): chuyến đã duyệt chưa giá (luật `is_missing_price` của server), chuyến chờ
    kiểm (kết luận cũng cần tháng mở) và dòng sổ gốc là chuyến chưa có đơn giá."""
    def of_month(row: dict[str, Any]) -> bool:
        return str(row.get("month") or "")[:7] == month
    trips = sum(1 for trip in ledger.get("trips") or [] if of_month(trip) and (
        (trip.get("status") == "confirmed" and trip.get("is_missing_price") is True) or trip.get("status") == "pending_review"))
    legacy = sum(1 for row in ledger.get("legacy_rows") or [] if of_month(row) and row.get("kind") == "trip"
                 and isinstance(row.get("current"), dict) and not row["current"].get("deleted")
                 and row["current"].get("unit_price_vnd") is None)
    return trips + legacy


def flag(ledger: dict[str, Any], month: str) -> bool | None:
    """Cờ khóa đã ghi của tháng; None khi sổ chưa có dòng cờ (mặc định: chỉ tháng hiện tại mở)."""
    for row in ledger.get("month_locks") or []:
        if str(row.get("month") or "")[:7] == month and type(row.get("locked")) is bool:
            return row["locked"]
    return None


def last_choice(ledger: dict[str, Any], month: str) -> dict[str, Any] | None:
    """Lần mở/khóa gần nhất của tháng không phải của máy theo Sheet (get_ledger trả mới nhất trước). Máy mở–ghi–khóa trong một lượt
    nên lần của máy không phải lựa chọn: người khóa rồi máy mở–ghi–khóa thì ý người vẫn là khóa."""
    return next((event for event in ledger.get("events") or [] if event.get("kind") == "month_lock" and event.get("actor") != MACHINE
                 and str((event.get("after") or {}).get("month") or "")[:7] == month), None)


def decide(ledger: dict[str, Any], month: str, mode: str) -> str:
    """Việc ở một sổ: OPEN / LOCK để ghi, còn lại là lý do bỏ qua."""
    choice = last_choice(ledger, month)
    by_tool = choice is not None and choice.get("actor") == ACTOR
    choice_locked = (choice or {}).get("after", {}).get("locked")
    if mode == "relock":
        if flag(ledger, month) is not False:
            return "NOT_OPEN"
        return "LOCK" if by_tool and choice_locked is False else "OPENED_BY_OTHER"
    if not unpriced(ledger, month):
        return "ALL_PRICED"
    if flag(ledger, month) is False:
        return "ALREADY_OPEN"
    if choice is not None and not by_tool and choice_locked is True:
        return "LOCKED_BY_PERSON"
    return "OPEN"


def _write(runner, customer: int, month: str, mode: str, ledger: dict[str, Any]) -> str:
    """Ghi một sổ; sổ đổi phiên bản thì đọc lại, xét lại rồi thử lại. Trả việc cuối cùng đã xét (OPEN/LOCK khi đã ghi)."""
    for attempt in range(TRIES):
        action = decide(ledger, month, mode)
        if action not in ("OPEN", "LOCK"):
            return action
        version = ledger["version"]
        key = hashlib.sha256(f"{ACTOR}:{mode}:{customer}:{month}:{version}".encode()).hexdigest()
        try:
            runner.run("set_month_lock", {"customer_id": customer, "expected_version": version, "idempotency_key": key,
                                          "month": month + "-01", "locked": action == "LOCK"}, ACTOR)
            return action
        except ApiError:
            if attempt == TRIES - 1:
                raise
            ledger = runner.run("get_ledger", {"customer_id": customer}, ACTOR)
    raise AssertionError("unreachable")


def run(runner, month: str, mode: str, apply: bool, customers: list[int] | None = None) -> dict[str, Any]:
    if not MONTH.fullmatch(month) or mode not in ("open", "relock"):
        raise ValueError("month yyyy-mm, mode open|relock")
    if customers is None:
        customers = [row["id"] for row in runner.run("list_customers", {}, ACTOR)["customers"] if not row.get("archived")]
    result: dict[str, Any] = {"month": month, "mode": mode, "apply": apply, "to_write": [], "written": [],
                              "unpriced_trips": 0, "opened_by_other": [], "skipped": {}, "errors": {}, "error_books": []}
    skipped: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    for customer in customers:
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer}, ACTOR)
        except ApiError as exc:
            errors[exc.code] += 1
            result["error_books"].append(customer)
            continue
        if ledger.get("status") != "active":
            skipped["INACTIVE"] += 1
            continue
        action = decide(ledger, month, mode)
        if action == "OPENED_BY_OTHER":   # người mở lại trong cửa sổ: không tự khóa, nêu sổ để người xem
            result["opened_by_other"].append(customer)
        if action not in ("OPEN", "LOCK"):
            skipped[action] += 1
            continue
        result["to_write"].append(customer)
        result["unpriced_trips"] += unpriced(ledger, month)
        if not apply:
            continue
        try:
            done = _write(runner, customer, month, mode, ledger)
        except ApiError as exc:   # lượt timer sau chạy lại sổ này
            errors[exc.code] += 1
            result["error_books"].append(customer)
            continue
        if done in ("OPEN", "LOCK"):
            result["written"].append(customer)
        else:   # đọc lại thấy không còn việc (người vừa mở/khóa, vừa ghi đủ giá)
            skipped[done] += 1
    result["skipped"], result["errors"] = dict(skipped), dict(errors)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--database", default="webdebit_v7")
    parser.add_argument("--db-user", default="v7_app")
    parser.add_argument("--month", required=True, help="yyyy-mm")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--open", dest="mode", action="store_const", const="open")
    mode.add_argument("--relock", dest="mode", action="store_const", const="relock")
    parser.add_argument("--customer", type=int, action="append", help="chỉ chạy các sổ này; bỏ trống là mọi sổ chưa lưu trữ")
    parser.add_argument("--apply", action="store_true", help="ghi thật; không có thì chỉ đếm")
    args = parser.parse_args()
    result = run(PsqlDirect(args.socket_dir, args.database, args.db_user), args.month, args.mode, args.apply, args.customer)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
