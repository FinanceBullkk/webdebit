"""Chuyến bộ mới từ CONT_BO vào sổ theo tab khách trên Sheet (NGUON-CHUYEN-01, specs/v7-chuyen-theo-nguon.md GĐ3). Chỉ đọc.

Một chuyến bộ (dòng READY của `road.json`) thuộc sổ khi đúng một tab khách trên Sheet có cùng container, ngày cách không
quá 3 ngày (dòng tab không ngày: cùng tháng nợ), và tab đó ứng đúng một sổ web đang hoạt động (tên sổ hoặc tên khác, như
hàng chờ giá). Cột CHỦ HÀNG của CONT_BO chỉ để hiện: có khi là kho đóng hàng (người dùng chốt 3/11/2026). Chuyến chưa có ở
tab nào thì chờ, vì phía Sheet chưa vào sổ. Ngày theo CONT_BO, tháng nợ theo ngày; giá theo tab do máy ghi giá (MAY-GIA-01).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from v7_price_queue import container_key, iso, name_key, owners, targets
from v7_sheet_queue import _same_legacy_trip, read_snapshot

ROAD_FROM = "2026-10"   # tháng nạp V7: trước đó sổ gốc là chuẩn (MAY-KHOA-01)
DATE_WINDOW_DAYS = 3
NOTE = "Chuyến bộ đồng bộ"   # khác "Chuyến đồng bộ": bộ dò "Sheet đã xóa" chỉ so với CONT_NGUON, không được báo chuyến bộ
NO_WAREHOUSE = "—"   # CONT_BO để trống KHO ở hầu hết dòng; paste_trips bắt buộc nơi đi
MESSAGES = {"NEW": "Chuyến bộ theo CONT_BO, chưa có trên sổ", "OTHER_CUSTOMER": "Container ở khách khác",
            "OTHER_BOOK_LEGACY": "Đã có ở sổ gốc của sổ khác",
            "MONTH_DIFFERS": "Tháng trên tab Sheet khác tháng của ngày CONT_BO"}


def load_road_snapshot(path: Any) -> dict[str, Any]:
    return read_snapshot(path, "Sheet road snapshot")


def _near(tab_row: dict[str, Any], date: dt.date) -> bool:
    day = iso(tab_row.get("date"))
    if day:
        return abs((day - date).days) <= DATE_WINDOW_DAYS
    return str(tab_row.get("debt_month") or "")[:7] == date.isoformat()[:7]


def build_road_queue(road: dict[str, Any], prices: dict[str, Any], customers: list[dict[str, Any]]) -> dict[str, Any]:
    """Mọi chuyến bộ từ ROAD_FROM đã gắn được một sổ; dòng không gắn được chỉ đếm trong `stats`, không đoán."""
    active = [c for c in customers if type(c.get("id")) is int and c.get("status") == "active"]
    owned = owners([{**c, "key": c["id"]} for c in active])
    by_container: dict[str, list[dict[str, Any]]] = {}
    for row in prices.get("rows") or []:
        by_container.setdefault(container_key(row.get("container")), []).append(row)
    items, stats = [], Counter()
    for source in road.get("rows") or []:
        date = iso(source.get("event_date"))
        if source.get("status") != "READY" or date is None or date.isoformat()[:7] < ROAD_FROM:
            continue
        container = container_key(source.get("container"))
        tab_rows = [row for row in by_container.get(container, []) if _near(row, date)]
        tabs = {name_key(row.get("customer_tab")) for row in tab_rows}
        if not tabs:
            stats["NO_TAB"] += 1   # phía Sheet chưa vào sổ: chờ
            continue
        books = {owned[tab][0] if tab in owned else None for tab in tabs}
        if len(tab_rows) != 1 or len(books) != 1 or None in books:
            stats["AMBIGUOUS_TAB" if len(tab_rows) != 1 or len(books) != 1 else "NO_BOOK"] += 1
            continue
        tab_row = tab_rows[0]
        stats["BOOK"] += 1
        items.append({
            "customer_id": next(iter(books)), "customer_tab": tab_row.get("customer_tab"), "tab_row": tab_row.get("source_row"),
            "tab_debt_month": str(tab_row.get("debt_month") or "")[:7], "source_row": source.get("source_row"),
            "container": container, "event_date": date.isoformat(), "source_date": source.get("source_date"),
            "carrier": source.get("plate"), "origin": source.get("warehouse") or NO_WAREHOUSE, "destination": source.get("gate"),
            "shipper": source.get("shipper") or None, "booking": "", "owner": source.get("owner"),
            "src": f"sheet:{road['sha256']}:{source.get('source_row')}", "note": NOTE})
    # Hai chuyến CONT_BO (khác ngày, cùng container) nhận cùng một dòng tab: một dòng tiền không thành hai chuyến.
    claimed = Counter((item["customer_tab"], item["tab_row"]) for item in items)
    shared = [item for item in items if claimed[(item["customer_tab"], item["tab_row"])] > 1]
    if shared:
        stats["BOOK"] -= len(shared)
        stats["AMBIGUOUS_SOURCE"] += len(shared)
        items = [item for item in items if claimed[(item["customer_tab"], item["tab_row"])] == 1]
    return {"snapshot_sha256": road.get("sha256"), "snapshot_created_at": (road.get("runner") or {}).get("created_at"),
            "items": items, "stats": dict(stats)}


def in_book(ledger: dict[str, Any], container: str, date: dt.date) -> bool:
    """Sổ đã có chuyến này: chuyến web hoặc dòng sổ gốc cùng container, cách không quá 3 ngày, hoặc dòng không ngày cùng tháng.

    Container dùng lại xa ngày hơn là chuyến khác (chuyện thường ở chuyến bộ), không chặn.
    """
    for target in targets(ledger):
        if target["container"] != container:
            continue
        if target["date"] is not None and abs((target["date"] - date).days) <= DATE_WINDOW_DAYS:
            return True
        if target["date"] is None and target.get("month") == date.isoformat()[:7]:
            return True
    return False


def project_road(queue: dict[str, Any], ledger: dict[str, Any], other_containers: set[str] | None = None,
                 other_legacy: list[dict[str, Any]] | None = None, family_ids: set[int] | None = None) -> dict[str, Any]:
    """Chuyến bộ của một sổ chưa có trên sổ: NEW để máy (hoặc người) đưa vào; CONFLICT khi vướng sổ khác hay lệch tháng."""
    visible = []
    for item in queue.get("items") or []:
        if item.get("customer_id") != ledger.get("customer_id"):
            continue
        date = dt.date.fromisoformat(item["event_date"])
        if in_book(ledger, item["container"], date):
            continue
        if item["tab_debt_month"] != item["event_date"][:7]:
            reason = "MONTH_DIFFERS"
        elif item["container"] in (other_containers or set()):
            reason = "OTHER_CUSTOMER"
        elif same := [ref for ref in other_legacy or () if _same_legacy_trip(ref, item["container"], date)]:
            if all(ref.get("customer_id") in (family_ids or ()) for ref in same):
                continue   # cùng khách, sổ khác đã tính
            reason = "OTHER_BOOK_LEGACY"
        else:
            reason = ""
        state = "CONFLICT" if reason else "NEW"
        visible.append({**item, "sync_state": state, "sync_reason": reason, "message": MESSAGES[reason or "NEW"]})
    return {"snapshot_sha256": queue.get("snapshot_sha256"), "items": visible,
            "new_count": sum(row["sync_state"] == "NEW" for row in visible),
            "conflict_count": sum(row["sync_state"] == "CONFLICT" for row in visible)}
