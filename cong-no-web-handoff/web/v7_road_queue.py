"""Chuyến bộ mới từ CONT_BO vào sổ (NGUON-CHUYEN-01, CHUYEN-BO-CHU-HANG-01, specs/v7-chuyen-theo-nguon.md GĐ3). Chỉ đọc.

Một chuyến bộ (dòng READY của `road.json`) thuộc sổ khi đúng một tab khách trên Sheet có cùng container, ngày cách không
quá 3 ngày (dòng tab không ngày: cùng tháng nợ), và tab đó ứng đúng một sổ web đang hoạt động (tên sổ hoặc tên khác, như
hàng chờ giá). Ngày theo CONT_BO, tháng nợ theo ngày; giá theo tab do máy ghi giá (MAY-GIA-01).

Chuyến chưa có ở tab nào thì lấy sổ theo CHỦ HÀNG (CHUYEN-BO-CHU-HANG-01, người dùng chốt 16/11/2026), nhưng chỉ khi chủ hàng
đó đã có ít nhất OWNER_MIN_TRIPS chuyến được tab xếp vào sổ, và tất cả vào cùng một sổ: CHỦ HÀNG có khi là kho đóng hàng
cho nhiều khách, kho thì đã từng vào hai sổ nên vẫn chờ tab. Tab còn dòng cùng container cách không quá TAB_FAR_DAYS ngày
mà chưa dòng CONT_BO nào nhận thì cũng chờ: đó thường là chính chuyến này với ngày gõ lệch (CONTAINER-DUNG-LAI-01).
"""

from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from v7_price_queue import container_key, iso, name_key, owners, targets
from v7_sheet_queue import _same_legacy_trip, read_snapshot

ROAD_FROM = "2026-10"   # tháng nạp V7: trước đó sổ gốc là chuẩn (MAY-KHOA-01)
DATE_WINDOW_DAYS = 3
OWNER_MIN_TRIPS = 3     # chủ hàng phải có từng ấy chuyến tab đã xếp, đều một sổ (đo 16/11/2026: nhỏ nhất 4 chuyến)
TAB_FAR_DAYS = 31       # dòng tab cùng container chưa ai nhận trong khoảng này: chờ tab, không tự thêm
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


def _owner_key(owner: Any) -> str:
    """CHỦ HÀNG gõ tay: bỏ khoảng trắng thừa và không phân biệt hoa thường; số mã khách (379) vẫn giữ."""
    return name_key(owner).upper()


def _close(tab_row: dict[str, Any], date: dt.date) -> bool:
    """Dòng tab có thể là cùng chuyến với ngày gõ lệch: cách không quá TAB_FAR_DAYS, dòng không ngày thì tháng nợ liền kề."""
    day = iso(tab_row.get("date"))
    if day:
        return abs((day - date).days) <= TAB_FAR_DAYS
    month = iso(f"{str(tab_row.get('debt_month') or '')[:7]}-01")
    return month is not None and abs((month.year - date.year) * 12 + month.month - date.month) <= 1


def _item(road: dict[str, Any], source: dict[str, Any], date: dt.date, book: int, tab_row: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "customer_id": book, "customer_tab": tab_row.get("customer_tab") if tab_row else None,
        "tab_row": tab_row.get("source_row") if tab_row else None,
        "tab_debt_month": str(tab_row.get("debt_month") or "")[:7] if tab_row else date.isoformat()[:7],
        "book_basis": "tab" if tab_row else "owner", "source_row": source.get("source_row"),
        "container": container_key(source.get("container")), "event_date": date.isoformat(), "source_date": source.get("source_date"),
        "carrier": source.get("plate"), "origin": source.get("warehouse") or NO_WAREHOUSE, "destination": source.get("gate"),
        "shipper": source.get("shipper") or None, "booking": "", "owner": source.get("owner"),
        "src": f"sheet:{road['sha256']}:{source.get('source_row')}", "note": NOTE}


def build_road_queue(road: dict[str, Any], prices: dict[str, Any], customers: list[dict[str, Any]]) -> dict[str, Any]:
    """Mọi chuyến bộ từ ROAD_FROM đã gắn được một sổ; dòng không gắn được chỉ đếm trong `stats`, không đoán."""
    active = [c for c in customers if type(c.get("id")) is int and c.get("status") == "active"]
    owned = owners([{**c, "key": c["id"]} for c in active])
    by_container: dict[str, list[dict[str, Any]]] = {}
    for row in prices.get("rows") or []:
        by_container.setdefault(container_key(row.get("container")), []).append(row)
    # Lượt 1, mọi tháng: chuyến nào tab xếp được vào sổ nào. Dùng để học CHỦ HÀNG → sổ và biết dòng tab nào đã có chủ.
    placed = []
    for source in road.get("rows") or []:
        date = iso(source.get("event_date"))
        if source.get("status") != "READY" or date is None:
            continue
        tab_rows = [row for row in by_container.get(container_key(source.get("container")), []) if _near(row, date)]
        tabs = {name_key(row.get("customer_tab")) for row in tab_rows}
        books = {owned[tab][0] if tab in owned else None for tab in tabs}
        if not tabs:
            reason = "NO_TAB"
        elif len(tab_rows) != 1 or len(books) != 1:
            reason = "AMBIGUOUS_TAB"
        elif None in books:
            reason = "NO_BOOK"
        else:
            reason = ""
        placed.append((source, date, reason, next(iter(books)) if not reason else None, tab_rows[0] if not reason else None))
    claimed = Counter((tab_row.get("customer_tab"), tab_row.get("source_row")) for *_, tab_row in placed if tab_row)
    # Chặn "hai chuyến một dòng tab" chỉ giữa các chuyến từ ROAD_FROM, như trước khi có luật chủ hàng.
    claimed_new = Counter((tab_row.get("customer_tab"), tab_row.get("source_row")) for _s, date, _r, _b, tab_row in placed
                          if tab_row and date.isoformat()[:7] >= ROAD_FROM)
    near_any = {(row.get("customer_tab"), row.get("source_row")) for source, date, *_ in placed
                for row in by_container.get(container_key(source.get("container")), []) if _near(row, date)}
    learned: dict[str, Counter] = {}
    for source, _date, reason, book, tab_row in placed:
        if not reason and claimed[(tab_row.get("customer_tab"), tab_row.get("source_row"))] == 1 and _owner_key(source.get("owner")):
            learned.setdefault(_owner_key(source.get("owner")), Counter())[book] += 1
    # Lượt 2, từ ROAD_FROM.
    items, stats = [], Counter()
    for source, date, reason, book, tab_row in placed:
        if date.isoformat()[:7] < ROAD_FROM:
            continue
        if reason == "NO_TAB":
            books = learned.get(_owner_key(source.get("owner"))) or Counter()
            if len(books) != 1 or sum(books.values()) < OWNER_MIN_TRIPS:
                stats["NO_TAB"] += 1   # chủ hàng chưa rõ sổ (kho, khách mới): chờ tab
                continue
            far = [row for row in by_container.get(container_key(source.get("container")), [])
                   if (row.get("customer_tab"), row.get("source_row")) not in near_any and _close(row, date)]
            if far:
                stats["TAB_FAR"] += 1   # tab có dòng lệch ngày chưa ai nhận: nhiều khả năng là chính chuyến này
                continue
            stats["OWNER"] += 1
            items.append(_item(road, source, date, next(iter(books)), None))
        elif reason:
            stats[reason] += 1
        elif claimed_new[(tab_row.get("customer_tab"), tab_row.get("source_row"))] > 1:
            # Hai chuyến CONT_BO (khác ngày, cùng container) nhận cùng một dòng tab: một dòng tiền không thành hai chuyến.
            stats["AMBIGUOUS_SOURCE"] += 1
        else:
            stats["BOOK"] += 1
            items.append(_item(road, source, date, book, tab_row))
    # Hai dòng CONT_BO cùng container, cách không quá 3 ngày, cùng vào một sổ theo chủ hàng: có thể là một chuyến ghi hai lần.
    by_owner = [item for item in items if item["book_basis"] == "owner"]
    twin = {id(a) for a in by_owner for b in by_owner if a is not b and (a["customer_id"], a["container"]) == (b["customer_id"], b["container"])
            and abs((dt.date.fromisoformat(a["event_date"]) - dt.date.fromisoformat(b["event_date"])).days) <= DATE_WINDOW_DAYS}
    if twin:
        stats["OWNER"] -= len(twin)
        stats["AMBIGUOUS_SOURCE"] += len(twin)
        items = [item for item in items if id(item) not in twin]
    return {"snapshot_sha256": road.get("sha256"), "snapshot_created_at": (road.get("runner") or {}).get("created_at"),
            "items": items, "stats": dict(stats)}


def in_book(pool: list[dict[str, Any]], container: str, date: dt.date) -> bool:
    """Sổ đã có chuyến này: chuyến web hoặc dòng sổ gốc cùng container, cách không quá 3 ngày, hoặc dòng không ngày cùng tháng.

    Container dùng lại xa ngày hơn là chuyến khác (chuyện thường ở chuyến bộ), không chặn. `pool` là `targets(ledger)`, dựng
    một lần cho cả sổ: dựng lại theo từng dòng chờ tốn 2,1 giây ở sổ lớn nhất (đo trên `hao` 4/11/2026, 156 dòng).
    """
    for target in pool:
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
    mine = [item for item in queue.get("items") or [] if item.get("customer_id") == ledger.get("customer_id")]
    pool = targets(ledger) if mine else []
    for item in mine:
        date = dt.date.fromisoformat(item["event_date"])
        if in_book(pool, item["container"], date):
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
