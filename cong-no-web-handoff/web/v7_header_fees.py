"""Tách phụ phí theo tên cột tab khách: lập kế hoạch ghi trên một sổ (TACH-PHI-TIEU-DE-01). Chỉ đọc.

Runner giá đọc tiền từng ô theo tên cột (`tools/v7_fee_headers.py`) và ghi vào mỗi dòng `prices.json` khóa `sheet_fees`
(trường → đồng) khi tổng các ô bằng đúng TOTAL − đơn giá. Ở đây ghép dòng đó với chuyến trên web và lập bộ khoản mới bằng
đúng hàm `plan` của máy PS (MAY-PS-01): chỉ đổi loại, không đổi tiền. Công cụ một lần và máy theo Sheet dùng chung.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from v7_price_queue import book_rows, container_key
from v7_ps_queue import GENERATED_NOTES, fee_type_ids, match, plan, pool

WRITABLE = ("READY", "MONTH_LOCKED")


def keeps_notes(before: list[dict], after: list[dict]) -> bool:
    """Như máy PS: thay khoản mà làm mất ghi chú người đã gõ thì để người bấm."""
    notes = Counter(x.get("note") for x in before if x.get("note") and x["note"] not in GENERATED_NOTES)
    return not notes - Counter(x.get("note") for x in after if x.get("note"))


def plan_rows(rows: list[dict], ledger: dict, ids: dict) -> list[dict]:
    """Mỗi dòng tab (dạng `v7_fee_headers.fees_of`) → trạng thái và bộ khoản mới trên đúng một chuyến của sổ."""
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


def snapshot_rows(snapshot: dict, customer: Any, customers: list[dict]) -> list[dict]:
    """Dòng `prices.json` của tab thuộc sổ này mà runner đã tách được theo tên cột, ở dạng `plan_rows` nhận."""
    out = []
    for row in book_rows(snapshot, customer, customers):
        fees = row.get("sheet_fees")
        if not isinstance(fees, dict) or not fees:
            continue
        rest = {field: int(value) for field, value in fees.items() if field != "combined"}
        out.append({"source_row": row.get("source_row"), "month": row.get("debt_month"), "status": "SHEET_OK",
                    "container": container_key(row.get("container")), "date": row.get("date"), "booking": None,
                    "fees": rest, "combined_vnd": int(fees["combined"]) if fees.get("combined") else None})
    return out


def project(snapshot: dict, ledger: dict, customers: list[dict], fee_types: list[dict]) -> list[dict]:
    """Kế hoạch tách của một sổ; máy chỉ ghi các dòng `WRITABLE`, còn lại để nguyên như trước (vẫn là Khác)."""
    rows = snapshot_rows(snapshot, ledger.get("customer_id"), customers)
    return plan_rows(rows, ledger, fee_type_ids(fee_types)) if rows else []


def writable(plans: list[dict]) -> list[dict]:
    return [item for item in plans if item["status"] in WRITABLE]


def write_lines(item: dict) -> list[dict]:
    return [{k: x[k] for k in ("fee_type_id", "amount_vnd", "note")} for x in item["info"]["after"]]


def added_columns(ledger: dict, type_ids: set[int]) -> list[int] | None:
    """Cột riêng sau khi tách: thêm cột cho loại vừa ghi mà sổ chưa có cột, không đổi cột đang có. None khi không đổi."""
    current = [c["fee_type_id"] for c in sorted(ledger.get("fee_columns") or [], key=lambda c: c.get("position") or 0)]
    columns = current + sorted(type_id for type_id in type_ids if type_id not in current)
    return None if columns == current else columns
