"""Content identities for reviewed Sheet tasks. Snapshot timestamps/row positions are not identities."""
from __future__ import annotations

import hashlib
import json


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def web_value(kind: str, row: dict) -> dict:
    fields = ("unit_price_vnd", "other_fee_vnd") if kind == "price" else ("container", "event_date", "status", "booking")
    return {field: row.get(field) for field in fields}


def kept(ledger: dict, kind: str, target_kind: str, target_id: int, source: str, current: dict) -> bool:
    latest = None
    for event in sorted(ledger.get("events", []), key=lambda row: row.get("id", 0)):
        after = event.get("after") or {}
        if (event.get("kind") == "sheet_conflict_resolved" and after.get("field") == "task_" + kind
                and after.get("target") == {"kind": target_kind, "id": target_id}):
            latest = after
    return bool(latest and latest.get("sheet_value") == source and latest.get("target_value") == current)


def price_identity(row: dict) -> str:
    return fingerprint({key: row.get(key) for key in (
        "container", "date", "sheet_unit_price_vnd", "sheet_other_fee_vnd", "sheet_total_vnd")})


def ps_identity(row: dict) -> str:
    """Nội dung một dòng PS (PS-HOI-01): ô phí, cờ, lỗi nguồn. Ô PS đổi thì dòng đã giữ hỏi lại."""
    return fingerprint({key: row.get(key) for key in (
        "container", "date", "fees", "combined_vnd", "health", "kd", "source_error", "problems", "ps_match_count")})


def ps_web_value(ledger: dict, target_kind: str, target_id) -> dict | None:
    """Đơn giá và phụ phí đang tính của chuyến đích, cùng dạng `keep_sheet_task` đọc trong DB; web đổi thì hỏi lại."""
    if target_kind == "trip":
        row = next((t for t in ledger.get("trips", []) if t.get("id") == target_id and not t.get("deleted")), None)
    else:
        row = next(((r.get("current") or {}) for r in ledger.get("legacy_rows", []) if r.get("id") == target_id), None)
    if row is None:
        return None
    return {field: None if row.get(field) is None else str(row.get(field)) for field in ("unit_price_vnd", "other_fee_vnd")}


def trip_identity(row: dict) -> str:
    return fingerprint({key: row.get(key) for key in ("container", "carrier", "shipper", "event_date", "origin",
                       "destination", "booking", "customer_name", "commodity", "durian_type", "source_date")})


def removed_identity(queue: dict, ledger: dict, trip: dict) -> str:
    # Same container, including rows reassigned to another book, is related; unrelated Sheet edits are not.
    def normalize(value):
        return "".join(str(value or "").upper().split())
    related = [{k: v for k, v in row.items() if k not in ("source_row", "source_tab", "review_status", "sync_state")}
               for row in queue["items"] if normalize(row.get("container")) == normalize(trip.get("container"))]
    related.sort(key=lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False))
    return fingerprint({"customer_id": ledger["customer_id"], "container": normalize(trip["container"]), "rows": related})
