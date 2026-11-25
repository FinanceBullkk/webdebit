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
import hashlib
import unicodedata
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
# Chuyến máy không tự đưa vào sổ nhưng biết vài sổ có thể nhận (WEB-CHINH-01: sau 1/12/2026 tab Sheet đứng yên, người chọn sổ trên web).
CHOICE_MESSAGES = {"AMBIGUOUS_TAB": "Tab Sheet ghi container này ở nhiều dòng hoặc nhiều sổ · chọn sổ nhận chuyến",
                   "TAB_FAR": "Tab Sheet có dòng cùng container lệch ngày · chọn sổ nhận chuyến"}


def load_road_snapshot(path: Any) -> dict[str, Any]:
    return read_snapshot(path, "Sheet road snapshot")


def _near(tab_row: dict[str, Any], date: dt.date) -> bool:
    day = iso(tab_row.get("date"))
    if day:
        return abs((day - date).days) <= DATE_WINDOW_DAYS
    return str(tab_row.get("debt_month") or "")[:7] == date.isoformat()[:7]


def owner_key(owner: Any) -> str:
    """CHỦ HÀNG gõ tay: NFC (chữ gõ dạng tổ hợp vẫn khớp), bỏ khoảng trắng thừa và các dấu file xuất không nhận, không phân biệt hoa
    thường; số mã khách (379) vẫn giữ. Trang Khách dùng chung khóa này để kiểm tên gán trên web (KHACH-WEB-01)."""
    return name_key(unicodedata.normalize("NFC", str(owner or ""))).upper()


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
    """Mọi chuyến bộ từ ROAD_FROM đã gắn được một sổ; dòng không gắn được không đoán: đếm trong `stats` và ghi ở `skipped`
    (container, ngày, mã lý do) để Báo cáo tháng nói vì sao chuyến booking chưa lên web (BAO-CAO-THANG-02)."""
    active = [c for c in customers if type(c.get("id")) is int and c.get("status") == "active"]
    owned = owners([{**c, "key": c["id"]} for c in active])
    by_container: dict[str, list[dict[str, Any]]] = {}
    for row in prices.get("rows") or []:
        by_container.setdefault(container_key(row.get("container")), []).append(row)
    # Lượt 1, mọi tháng: chuyến nào tab xếp được vào sổ nào. Dùng để học CHỦ HÀNG → sổ và biết dòng tab nào đã có chủ.
    placed = []
    near_books: dict[int, set[int]] = {}   # chuyến có nhiều dòng tab gần ngày: các sổ của những dòng đó
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
            near_books[id(source)] = {book for book in books if book is not None}
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
    # KHACH-WEB-01: CHỦ HÀNG quản lý đã gán tên booking cho một sổ thì vào sổ đó, không cần đủ OWNER_MIN_TRIPS chuyến tab đã xếp.
    # Chỉ sổ không ghi là đi biển và chưa lưu trữ: tên gán ở sổ biển chỉ dẫn chuyến biển. Hai sổ cùng một khóa (tên khác nhau chỉ ở
    # dấu file bỏ) thì bỏ khóa đó, như `owners()`.
    named: dict[str, int | None] = {}
    for customer in active:
        if customer.get("transport_mode") == "CANG" or customer.get("archived"):
            continue
        for name in customer.get("booking_names") or ():
            key = owner_key(name) if isinstance(name, str) else ""
            if key:
                named[key] = customer["id"] if named.get(key, customer["id"]) == customer["id"] else None
    learned: dict[str, Counter] = {}
    for source, _date, reason, book, tab_row in placed:
        if not reason and claimed[(tab_row.get("customer_tab"), tab_row.get("source_row"))] == 1 and owner_key(source.get("owner")):
            learned.setdefault(owner_key(source.get("owner")), Counter())[book] += 1
    # Lượt 2, từ ROAD_FROM.
    items, stats, skipped, choices = [], Counter(), [], []

    def offer(source: dict[str, Any], date: dt.date, code: str, books: set[int]) -> None:
        """Chuyến bị giữ mà biết sổ nào có thể nhận: người chọn trên web (`project_choices`); máy vẫn không tự đưa vào."""
        if books:
            choices.append({**_item(road, source, date, None, None), "candidate_ids": sorted(books), "choice_reason": code})

    def skip(source: dict[str, Any], date: dt.date, code: str) -> None:
        stats[code] += 1
        skipped.append({"container": container_key(source.get("container")), "event_date": date.isoformat(), "reason": code})
    for source, date, reason, book, tab_row in placed:
        if date.isoformat()[:7] < ROAD_FROM:
            continue
        if reason == "NO_TAB":
            history = learned.get(owner_key(source.get("owner"))) or Counter()
            by_name = named.get(owner_key(source.get("owner")))
            if by_name and set(history) - {by_name}:
                by_name = None   # tab đã đưa chủ hàng này vào sổ khác (hay nhiều sổ, thường là kho): tên gán trên web không thắng
            books = Counter({by_name: OWNER_MIN_TRIPS}) if by_name else history
            if len(books) != 1 or sum(books.values()) < OWNER_MIN_TRIPS:
                skip(source, date, "NO_TAB")   # chủ hàng chưa rõ sổ (kho, khách mới): chờ tab
                continue
            far = [row for row in by_container.get(container_key(source.get("container")), [])
                   if (row.get("customer_tab"), row.get("source_row")) not in near_any and _close(row, date)]
            if far:
                skip(source, date, "TAB_FAR")   # tab có dòng lệch ngày chưa ai nhận: nhiều khả năng là chính chuyến này
                offer(source, date, "TAB_FAR", {*books, *(owned[name_key(row.get("customer_tab"))][0] for row in far
                                                          if name_key(row.get("customer_tab")) in owned)})
                continue
            stats["BOOKING_NAME" if by_name else "OWNER"] += 1
            items.append({**_item(road, source, date, next(iter(books)), None), **({"book_basis": "booking_name"} if by_name else {})})
        elif reason:
            skip(source, date, reason)
            if reason == "AMBIGUOUS_TAB":
                offer(source, date, reason, near_books.get(id(source), set()))
        elif claimed_new[(tab_row.get("customer_tab"), tab_row.get("source_row"))] > 1:
            # Hai chuyến CONT_BO (khác ngày, cùng container) nhận cùng một dòng tab: một dòng tiền không thành hai chuyến.
            skip(source, date, "AMBIGUOUS_SOURCE")
        else:
            stats["BOOK"] += 1
            items.append(_item(road, source, date, book, tab_row))
    # Hai dòng CONT_BO cùng container, cách không quá 3 ngày, cùng vào một sổ theo chủ hàng: có thể là một chuyến ghi hai lần.
    by_owner = [item for item in items if item["book_basis"] != "tab"]
    twin = {id(a) for a in by_owner for b in by_owner if a is not b and (a["customer_id"], a["container"]) == (b["customer_id"], b["container"])
            and abs((dt.date.fromisoformat(a["event_date"]) - dt.date.fromisoformat(b["event_date"])).days) <= DATE_WINDOW_DAYS}
    if twin:
        for item in items:
            if id(item) in twin:
                stats["BOOKING_NAME" if item["book_basis"] == "booking_name" else "OWNER"] -= 1
        stats["AMBIGUOUS_SOURCE"] += len(twin)
        skipped += [{"container": item["container"], "event_date": item["event_date"], "reason": "AMBIGUOUS_SOURCE"}
                    for item in items if id(item) in twin]
        items = [item for item in items if id(item) not in twin]
    # owner_books: CHỦ HÀNG → các sổ tab đã nhận chuyến của nó; trang Khách dựa vào đây để không gán tên kho hay tên đang vào sổ khác.
    return {"snapshot_sha256": road.get("sha256"), "snapshot_created_at": (road.get("runner") or {}).get("created_at"),
            "items": items, "stats": dict(stats), "skipped": skipped, "choices": choices,
            "owner_books": {key: sorted(found) for key, found in learned.items()}}


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


def source_fingerprint(item: dict[str, Any]) -> str:
    """Dấu vân của một dòng CONT_BO theo bản chụp: nút chọn sổ gửi lại dấu này, bản chụp đổi thì dấu đổi và lệnh bị từ chối."""
    return hashlib.sha256(str(item["src"]).encode()).hexdigest()


def project_choices(queue: dict[str, Any], ledger: dict[str, Any], customers: list[dict[str, Any]], other_containers: set[str] | None = None,
                    other_legacy: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Chuyến bộ chờ người chọn sổ, hiện một lần ở sổ ứng viên có mã nhỏ nhất (như dòng chuyến biển chưa rõ sổ). Chuyến đã có ở sổ này
    hay ở sổ khác (người đã chọn, hoặc nhập tay) thì thôi hiện. `CONFLICT` + `NEEDS_BOOK` để máy dán chuyến không bao giờ tự đưa vào."""
    books = {c["id"]: c for c in customers if type(c.get("id")) is int}
    mine = [c for c in queue.get("choices") or [] if c["candidate_ids"] and min(c["candidate_ids"]) == ledger.get("customer_id")]
    pool = targets(ledger) if mine else []
    out = []
    for choice in mine:
        date = dt.date.fromisoformat(choice["event_date"])
        if (in_book(pool, choice["container"], date) or choice["container"] in (other_containers or set())
                or any(_same_legacy_trip(ref, choice["container"], date) for ref in other_legacy or ())):
            continue
        out.append({**choice, "customer_id": ledger.get("customer_id"), "sync_state": "CONFLICT", "sync_reason": "NEEDS_BOOK",
                    "message": CHOICE_MESSAGES[choice["choice_reason"]], "source_fingerprint": source_fingerprint(choice),
                    "candidate_books": [{key: books[book].get(key) for key in ("id", "name", "display_name", "commodity", "transport_mode")}
                                        for book in choice["candidate_ids"] if book in books]})
    return out


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
