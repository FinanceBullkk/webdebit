"""Trang Khách của Quản trị (KHACH-WEB-01): tạo sổ khách mới và gán tên chủ hàng booking vào sổ, chỉ quản lý (đường /api/v7/admin).

Tên chủ hàng chuẩn hóa đúng như hàng chờ so (`v7_sheet_queue._name`: NFC, viết hoa, gộp khoảng trắng) trước khi gửi DB, nên tên gán
trên web trùng khóa với cột "Chủ hàng (chuẩn)" của CONT_NGUON và bảng WEB_GHEP_KHACH. Tên sổ phải sạch như tên tab trong file Sheet
xuất ra, và không được trùng sổ có sẵn theo khóa gộp mọi khóa tên của các máy (`book_key`): máy đối soát gặp hai sổ một tên thì dừng
cả lượt, bảng ghép giá bỏ tab đó. Gán tên mà tên đó đang đưa chuyến vào sổ khác (trùng tên sổ, bảng WEB_GHEP_KHACH, tab Sheet của
chuyến bộ) thì từ chối, kể cả tên kho đã vào nhiều sổ.

Danh sách "chủ hàng chưa có sổ" tính từ hai bản chụp booking: chuyến biển READY từ tháng nạp V7 mà hàng chờ chưa ứng sổ nào
(NEEDS_CUSTOMER), chuyến bộ chưa ở tab nào mà chủ hàng chưa rõ sổ (NO_TAB). Mỗi tên kèm tab Sheet đang ghi các container đó (cùng
container, lệch không quá 3 ngày) để gợi ý sổ khi Sheet vẫn chạy song song; chưa có bản chụp giá thì bỏ gợi ý. Chỉ đọc bản chụp; ghi
chỉ qua hai lệnh SQL có Lịch sử.
"""

from __future__ import annotations

import json
import os
import unicodedata
from collections import Counter
from datetime import datetime
from typing import Any

import v7_api_sheet as sheet
from v7_api_tables import ERRORS
from v7_api_validate import ApiError, bad, no_duplicates, positive_int
from v7_machine import VN
from v7_price_queue import XLSX_DROPPED, container_key, iso, name_key, owners
from v7_road_queue import owner_key
from v7_sheet_queue import _name

FROM_MONTH = "2026-10"   # như AUTO_LOCKED_TRIPS_FROM / ROAD_FROM: máy chỉ đưa chuyến vào sổ từ tháng nạp V7
MAX_NAMES = 20
MAX_SAMPLES = 3
MAX_BIGINT = 9223372036854775807
STALE_MINUTES = 60   # như SNAPSHOT_MAX_AGE_SECONDS: runner chạy 15 phút một lần
EMPTY_PRICES: dict[str, Any] = {"rows": []}   # đã thôi đọc Sheet: một đối tượng cố định để bộ nhớ đệm hàng chờ bộ nhận ra
CREATE_FIELDS = {"book_name", "commodity", "transport_mode", "booking_names", "idempotency_key"}
NAME_FIELDS = {"customer_id", "expected_version", "idempotency_key", "name", "remove"}
# Ký tự điều khiển, vô hình (ZWSP, BOM), dùng riêng, nửa cặp, ngắt dòng/đoạn: không có trong tên gõ tay, mà làm tên không bao giờ khớp.
BAD_CATEGORIES = {"Cc", "Cf", "Co", "Cs", "Zl", "Zp"}
BOOK_NAME_RULE = "Tên sổ không có ký tự lạ hay các dấu / \\ ? * [ ] : ' (Sheet bỏ các dấu này khi xuất file), tối đa 200 ký tự."


def _clean(value: Any) -> str | None:
    """NFC, mọi khoảng trắng (cả NBSP, tab) gộp thành một dấu cách, bỏ hai đầu. Rỗng, dài quá 200, có ký tự lạ: None."""
    if not isinstance(value, str):
        return None
    text = " ".join(unicodedata.normalize("NFC", value).split())
    if not text or len(text) > 200 or any(unicodedata.category(char) in BAD_CATEGORIES for char in text):
        return None
    return text


def booking_name(value: Any) -> str | None:
    """Tên chủ hàng như hàng chờ so (`_name`): NFC, khoảng trắng gộp, viết hoa (NFC lại sau khi viết hoa). Không hợp lệ: None."""
    text = _clean(value)
    if text is None:
        return None
    text = unicodedata.normalize("NFC", text.upper())
    return text if len(text) <= 200 and text == _name(text) else None


def book_key(value: Any) -> str:
    """Khóa gộp mọi khóa tên sổ của các máy: đối soát (gộp khoảng trắng), bảng ghép giá (bỏ / \\ ? * [ ] : '), hàng chờ (viết hoa),
    DB (không phân biệt hoa thường). Hai tên cùng khóa này là một sổ với máy nào đó."""
    return " ".join(unicodedata.normalize("NFC", str(value or "")).translate(XLSX_DROPPED).split()).casefold()


def tab_book_name(tab: Any) -> str:
    """Tên sổ máy tạo cho một tab Sheet (MAY-TAO-SO-01 đọc file xuất): tên tab bỏ các dấu file không nhận, gộp khoảng trắng."""
    return " ".join(unicodedata.normalize("NFC", str(tab or "")).translate(XLSX_DROPPED).split())


def _body(raw: bytes, fields: set[str]) -> dict[str, Any]:
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, ValueError):
        body = None
    if not isinstance(body, dict) or not set(body) <= fields:
        bad()
    return body


def _key(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        bad()
    return value


def _optional(load, path: str) -> dict[str, Any] | None:
    """Bản chụp không bắt buộc: chưa có file (đã thôi đọc Sheet) thì None; file có mà đọc lỗi thì không đoán, từ chối để thử lại."""
    if not os.path.exists(path):
        return None
    try:
        return sheet.cached_load(load, path)
    except (OSError, ValueError) as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", "Chưa đọc được bản chụp Sheet để kiểm tên. Thử lại sau ít phút.") from exc


def _customers(runner, actor: str) -> list[dict[str, Any]]:
    mapping = sheet.customer_name_mapping()
    return [sheet.named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]


def _labels(customer: dict[str, Any]) -> list[str]:
    """Tên sổ, tên khách và tên khác trong bảng gán tên: hàng chờ và bảng ghép giá ứng sổ theo các tên này."""
    return [label for label in (customer.get("name"), customer.get("display_name"), *(customer.get("aliases") or []))
            if isinstance(label, str) and label.strip()]


def sheet_history(book: str, today_month: str, prices: dict[str, Any] | None) -> None:
    """Chặn tạo tay một sổ trùng tên tab khách trên Sheet đã có dòng từ tháng trước: sổ web bắt đầu từ nợ 0 thì mất số dư cũ.

    Khi Sheet còn là sổ chính thức (SONG-SONG-01), tab đó phải để máy tạo sổ theo Sheet (MAY-TAO-SO-01, qua đủ số dư từng tháng).
    Tab chỉ có dòng tháng này (khách mới tháng này) thì cho tạo: chuyến, giá, phiếu về sau đi theo các máy như mọi sổ. Chưa có bản
    chụp giá (đã thôi đọc Sheet) thì không chặn.
    """
    key = book_key(book)
    if any(book_key(row.get("customer_tab")) == key and str(row.get("debt_month") or "")[:7] < today_month for row in (prices or {}).get("rows") or []):
        raise ApiError(409, "SHEET_TAB_HAS_HISTORY", "Sheet đã có tab tên này với nợ từ tháng trước. Để máy tạo sổ theo Sheet (giữ đúng số dư cũ); "
                                                       "chỉ tạo ở đây khi khách chưa có trên Sheet hoặc mới từ tháng này.")


class Routes:
    """Các đường đưa chuyến vào sổ hôm nay, để biết một tên booking (hay tên sổ mới) có đang đưa chuyến vào sổ khác không."""

    def __init__(self, customers: list[dict[str, Any]], snapshot: dict[str, Any] | None, prices: dict[str, Any] | None,
                 road: dict[str, Any] | None):
        self.customers = [c for c in customers if type(c.get("id")) is int and isinstance(c.get("name"), str)]
        self.active = [c for c in self.customers if c.get("status") == "active"]
        self.aliases = {_name(key): book for key, book in ((snapshot or {}).get("customer_aliases") or {}).items()
                        if isinstance(key, str) and isinstance(book, str)}
        self.owner_books = (sheet.cached_road_queue(road, prices, customers).get("owner_books") or {}) if road and prices else {}

    def name_of(self, customer_id: Any) -> str:
        return next((c["name"] for c in self.customers if c["id"] == customer_id), f"#{customer_id}")

    def booking(self, name: str, target_id: int | None, target_name: str) -> str | None:
        """Câu báo khi tên booking `name` đang đưa chuyến vào sổ khác `target` (sổ sắp tạo: `target_id` None); None khi không vướng."""
        key, road_key = _name(name), owner_key(name)
        for customer in self.active:
            if customer["id"] == target_id:
                continue
            if any(_name(label) == key for label in _labels(customer)):
                return f"«{name}» trùng tên sổ «{customer['name']}», nên chuyến biển của tên này đang tự vào sổ đó."
            near = next((other for other in customer.get("booking_names") or () if isinstance(other, str) and owner_key(other) == road_key), None)
            if near == name:
                return f"«{name}» đã gán cho sổ «{customer['name']}». Bỏ tên ở sổ đó trước."
            if near is not None:
                return f"«{name}» gần trùng tên booking «{near}» của sổ «{customer['name']}» (chuyến bộ so như nhau)."
        alias = self.aliases.get(key)
        if alias is not None and _name(alias) != _name(target_name):
            return f"Bảng WEB_GHEP_KHACH trên Sheet đang ghép «{name}» vào sổ «{alias}». Sửa bảng đó trước nếu muốn đổi."
        others = [book for book in self.owner_books.get(road_key, []) if book != target_id]
        if len(self.owner_books.get(road_key, [])) > 1:
            return f"Chuyến bộ của «{name}» đã vào {len(self.owner_books[road_key])} sổ khác nhau theo tab Sheet (thường là kho), nên không gán vào một sổ."
        if others:
            return f"Chuyến bộ của «{name}» đã vào sổ «{self.name_of(others[0])}» theo tab Sheet."
        return None

    def book(self, book: str) -> str | None:
        """Câu báo khi tên sổ mới đang là tên booking hay tên trong bảng WEB_GHEP_KHACH đưa chuyến vào sổ khác."""
        key = _name(book)
        for customer in self.active:
            if any(isinstance(other, str) and _name(other) == key for other in customer.get("booking_names") or ()):
                return f"«{book}» đang là tên booking của sổ «{customer['name']}». Bỏ tên ở sổ đó trước."
        alias = self.aliases.get(key)
        if alias is not None and _name(alias) != key:
            return f"Bảng WEB_GHEP_KHACH trên Sheet đang ghép «{book}» vào sổ «{alias}»: sổ mới tên này sẽ không nhận chuyến. Sửa bảng đó trước."
        return None


def _routes(customers: list[dict[str, Any]], prices: dict[str, Any] | None) -> Routes:
    return Routes(customers, _optional(sheet.load_snapshot, sheet.SHEET_SNAPSHOT_PATH), prices,
                  _optional(sheet.load_road_snapshot, sheet.ROAD_SNAPSHOT_PATH))


def _refuse(reason: str, name: str) -> None:
    raise ApiError(409, "BOOKING_NAME_ROUTED", f"{reason} Không gán được.", {"name": name})


def handle_create(raw: bytes, runner, actor: str) -> tuple[int, dict]:
    """POST /api/v7/admin/customers: `{book_name, commodity, transport_mode, booking_names, idempotency_key}` → sổ mới, nợ 0.

    Tên sổ sạch như tên tab Sheet trong file xuất; Sheet có tab cùng khóa (khác hoa thường, khoảng trắng, dấu bị bỏ) thì sổ lấy đúng chữ
    tab để máy đối soát và bảng ghép giá ghép được. Mặt hàng trống là chưa gán, có thì phải có trong danh mục (DB kiểm); phương thức
    bắt buộc (CANG/BO). Tên booking chuẩn hóa, bỏ trùng, tối đa MAX_NAMES, không tên nào đang vào sổ khác. Đã có sổ đúng tên này
    thì để DB quyết (bấm lại cùng khóa trả kết quả cũ, không thì BOOK_EXISTS), không kiểm lại để lần bấm lại sau khi sang tháng vẫn
    nhận kết quả cũ."""
    body = _body(raw, CREATE_FIELDS)
    book = _clean(body.get("book_name"))
    if book is None or book.translate(XLSX_DROPPED) != book:
        bad("INVALID_BOOK_NAME", BOOK_NAME_RULE)
    commodity = body.get("commodity")
    if commodity is not None and (not isinstance(commodity, str) or len(commodity.strip()) > 80):
        bad()
    if isinstance(commodity, str) and commodity.strip():
        commodity = _clean(commodity)
        if commodity is None:
            bad()
    else:
        commodity = None
    mode = body.get("transport_mode")
    if mode not in ("CANG", "BO"):
        bad()
    raw_names = body.get("booking_names", [])
    if not isinstance(raw_names, list) or len(raw_names) > MAX_NAMES:
        bad()
    names: list[str] = []
    for value in raw_names:
        name = booking_name(value)
        if name is None:
            bad("INVALID_BOOKING_NAME", ERRORS["INVALID_BOOKING_NAME"][1])
        if name not in names:
            names.append(name)
    key = _key(body.get("idempotency_key"))
    customers = _customers(runner, actor)
    prices = _optional(sheet.load_price_snapshot, sheet.PRICE_SNAPSHOT_PATH)
    tab = next((tab_book_name(row.get("customer_tab")) for row in (prices or {}).get("rows") or []
                if row.get("customer_tab") and book_key(row["customer_tab"]) == book_key(book)), None)
    if tab and _clean(tab) == tab:
        book = tab
    same = next((c for c in customers if isinstance(c.get("name"), str) and book_key(c["name"]) == book_key(book)), None)
    if same is not None and same["name"] != book:
        raise ApiError(409, "BOOK_EXISTS", f"Đã có sổ «{same['name']}», gần trùng tên này. Mở sổ đó, không tạo thêm.", {"book": same["name"]})
    if same is None:
        other = next((c for c in customers if any(book_key(label) == book_key(book) for label in _labels(c)[1:])), None)
        if other is not None:
            raise ApiError(409, "BOOK_EXISTS", f"«{book}» là tên khách của sổ «{other['name']}». Mở sổ đó, không tạo thêm.", {"book": other["name"]})
        routes = _routes(customers, prices)
        if (reason := routes.book(book)) is not None:
            raise ApiError(409, "BOOKING_NAME_ROUTED", f"{reason} Không tạo được.", {"name": book})
        for name in names:
            if (reason := routes.booking(name, None, book)) is not None:
                _refuse(reason, name)
        sheet_history(book, datetime.now(VN).date().isoformat()[:7], prices)
    payload = {"book_name": book, "commodity_name": commodity, "book_mode": mode, "booking_names": names, "idempotency_key": key}
    return 200, {**runner.run("create_customer", payload, actor), "name": book}


def handle_booking_name(raw: bytes, runner, actor: str) -> tuple[int, dict]:
    """POST /api/v7/admin/booking-names: `{customer_id, expected_version, idempotency_key, name, remove}` gán hay bỏ một tên booking.

    Gán thì tên không được đang đưa chuyến vào sổ khác (`Routes.booking`); bỏ tên thì không kiểm."""
    body = _body(raw, NAME_FIELDS)
    if set(body) != NAME_FIELDS or not positive_int(body["customer_id"]) or type(body["expected_version"]) is not int \
            or not 0 <= body["expected_version"] <= MAX_BIGINT or type(body["remove"]) is not bool:
        bad()
    name = booking_name(body["name"])
    if name is None:
        bad("INVALID_BOOKING_NAME", ERRORS["INVALID_BOOKING_NAME"][1])
    key = _key(body["idempotency_key"])
    if not body["remove"]:
        customers = _customers(runner, actor)
        target = next((c for c in customers if c.get("id") == body["customer_id"]), None)
        if target is not None:   # sổ không có: để DB trả CUSTOMER_NOT_FOUND
            reason = _routes(customers, _optional(sheet.load_price_snapshot, sheet.PRICE_SNAPSHOT_PATH)).booking(name, target["id"], target["name"])
            if reason is not None:
                _refuse(reason, name)
    payload = {"customer_id": body["customer_id"], "expected_version": body["expected_version"],
               "idempotency_key": key, "name": name, "remove": body["remove"]}
    return 200, runner.run("set_booking_name", payload, actor)


def _tab_index(prices: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in (prices or {}).get("rows") or []:
        index.setdefault(container_key(row.get("container")), []).append(row)
    return index


def _tabs_for(trips: list[tuple[str, str]], index: dict[str, list[dict[str, Any]]]) -> Counter:
    """Tab Sheet đang ghi các chuyến này: cùng container, lệch không quá 3 ngày (dòng tab không ngày: cùng tháng)."""
    found: Counter = Counter()
    for container, day in trips:
        date = iso(day)
        tabs = set()
        for row in index.get(container, ()):
            row_day = iso(row.get("date"))
            same = abs((row_day - date).days) <= 3 if row_day and date else str(row.get("debt_month") or "")[:7] == day[:7]
            if same and row.get("customer_tab"):
                tabs.add(row["customer_tab"])
        found.update(tabs)
    return found


def fits(customer: dict[str, Any] | None, family: str) -> bool:
    """Sổ nhận được tên của chủ hàng này: tên ở sổ đi biển chỉ dẫn chuyến biển, ở sổ đi bộ chỉ dẫn chuyến bộ; sổ chưa ghi thì cả hai."""
    return bool(customer) and customer.get("status") == "active" and not customer.get("archived") \
        and customer.get("transport_mode") != ("BO" if family == "BIEN" else "CANG")


def _age_minutes(created_at: Any, now: datetime) -> int | None:
    try:
        return max(0, int((now - datetime.fromisoformat(str(created_at))).total_seconds() // 60))
    except (TypeError, ValueError):
        return None


def unmapped(customers: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """Chủ hàng booking chưa có sổ, nhóm theo tên đã chuẩn hóa. Bản chụp CONT_NGUON đọc lỗi thì `state: unavailable`, không đoán;
    bản chụp giá chỉ để gợi ý tab, thiếu thì `sheet_state` báo riêng."""
    now = now or datetime.now(VN)
    try:
        snapshot = sheet.cached_load(sheet.load_snapshot, sheet.SHEET_SNAPSHOT_PATH)
        baseline = sheet.cached_load(sheet.load_baseline, sheet.SHEET_BASELINE_PATH)
        queue = sheet.cached_queue(snapshot, customers, baseline)
    except (OSError, ValueError, KeyError, TypeError):
        return {"state": "unavailable", "owners": []}
    # Bản chụp giá chỉ để gợi ý tab và xếp chuyến bộ theo tab. Chưa có file (đã thôi đọc Sheet): không gợi ý, chuyến bộ chỉ còn theo chủ
    # hàng như hàng chờ thật. File có mà đọc lỗi (tạm thời): bỏ phần chuyến bộ, không đoán.
    missing = not os.path.exists(sheet.PRICE_SNAPSHOT_PATH)
    try:
        prices, sheet_state = sheet.cached_load(sheet.load_price_snapshot, sheet.PRICE_SNAPSHOT_PATH), "ok"
    except (OSError, ValueError):
        prices, sheet_state = None, "none" if missing else "unavailable"
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    def add(family: str, owner: Any, container: str, day: str, commodity: str = "") -> None:
        name = booking_name(owner)
        if name is None or not container or not day or day[:7] < FROM_MONTH:
            return
        group = groups.setdefault((family, name), {"name": name, "family": family, "trips": [], "commodities": Counter()})
        group["trips"].append((container, day))
        if commodity:
            group["commodities"][commodity] += 1

    for row in queue["items"]:
        if row.get("status") == "READY" and row.get("review_status") == "NEEDS_CUSTOMER":
            add("BIEN", row.get("customer_name"), container_key(row.get("container")), str(row.get("event_date") or ""),
                str(row.get("commodity") or "").strip())
    road_state, owner_books = "ok", {}
    try:
        if sheet_state == "unavailable":
            raise ValueError("price snapshot unreadable")
        road = sheet.cached_load(sheet.load_road_snapshot, sheet.ROAD_SNAPSHOT_PATH)
        road_queue = sheet.cached_road_queue(road, prices or EMPTY_PRICES, customers)
        owner_books = road_queue.get("owner_books") or {}
        waiting = {(item["container"], item["event_date"]) for item in road_queue.get("skipped") or [] if item.get("reason") == "NO_TAB"}
        for row in road.get("rows") or []:
            key = (container_key(row.get("container")), str(row.get("event_date") or ""))
            if row.get("status") == "READY" and key in waiting:
                add("BO", row.get("owner"), *key)
    except (OSError, ValueError, KeyError, TypeError):
        road_state = "unavailable"
    index = _tab_index(prices)
    by_id = {c["id"]: c for c in customers if type(c.get("id")) is int}
    books = owners([{**c, "key": c["id"]} for c in customers if type(c.get("id")) is int and c.get("status") == "active"])
    assigned = {name: c for c in customers for name in c.get("booking_names") or () if isinstance(name, str)}
    result = []
    for group in groups.values():
        trips = sorted(group["trips"], key=lambda trip: trip[1])
        tabs = _tabs_for(trips, index)
        sheet_tabs = [{"tab": tab, "book_name": tab_book_name(tab), "trips": count,
                       "customer_id": books[name_key(tab)][0] if name_key(tab) in books else None}
                      for tab, count in tabs.most_common()]
        history = owner_books.get(owner_key(group["name"]), []) if group["family"] == "BO" else []
        suggest = history[0] if len(history) == 1 else next((tab["customer_id"] for tab in sheet_tabs if tab["customer_id"] is not None), None)
        owner = assigned.get(group["name"])
        result.append({"name": group["name"], "family": group["family"], "trips": len(trips), "first": trips[0][1], "last": trips[-1][1],
                       "commodities": [name for name, _ in group["commodities"].most_common()],
                       "containers": [container for container, _ in trips[-MAX_SAMPLES:]],
                       "sheet_tabs": sheet_tabs, "suggest_customer_id": suggest if fits(by_id.get(suggest), group["family"]) else None,
                       "many_books": len(history) if len(history) > 1 else 0,
                       "assigned_to": {"id": owner["id"], "name": owner["name"]} if owner else None})
    result.sort(key=lambda item: (-item["trips"], item["name"]))
    created = (snapshot.get("runner") or {}).get("created_at")
    age = _age_minutes(created, now)
    return {"state": "ok", "road_state": road_state, "sheet_state": sheet_state, "owners": result, "snapshot_created_at": created,
            "snapshot_stale_minutes": age if age is not None and age > STALE_MINUTES else None}


def view(runner, actor: str) -> dict[str, Any]:
    """GET /api/v7/admin/customers: mọi sổ kèm tên booking, và chủ hàng booking chưa có sổ."""
    customers = _customers(runner, actor)
    return {"customers": customers, "unmapped": unmapped(customers)}
