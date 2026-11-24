"""Trang Khách của Quản trị (KHACH-WEB-01): tạo sổ khách mới và gán tên chủ hàng booking vào sổ, chỉ quản lý (đường /api/v7/admin).

Tên chủ hàng chuẩn hóa đúng như hàng chờ so (`v7_sheet_queue._name`: NFC, viết hoa, gộp khoảng trắng) trước khi gửi DB, nên tên gán
trên web trùng khóa với cột "Chủ hàng (chuẩn)" của CONT_NGUON và bảng WEB_GHEP_KHACH. Danh sách "chủ hàng chưa có sổ" tính từ hai bản
chụp booking: chuyến biển READY từ tháng nạp V7 mà hàng chờ chưa ứng sổ nào (NEEDS_CUSTOMER), chuyến bộ chưa ở tab nào mà chủ hàng
chưa rõ sổ (NO_TAB). Mỗi tên kèm tab Sheet đang ghi các container đó (cùng container, lệch không quá 3 ngày), để gợi ý sổ khi Sheet
vẫn chạy song song. Chỉ đọc bản chụp; ghi chỉ qua hai lệnh SQL có Lịch sử.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from typing import Any

import v7_api_sheet as sheet
from v7_api_tables import ERRORS
from v7_api_validate import bad, no_duplicates, positive_int
from v7_price_queue import container_key, iso, name_key, owners

FROM_MONTH = "2026-10"   # như AUTO_LOCKED_TRIPS_FROM / ROAD_FROM: máy chỉ đưa chuyến vào sổ từ tháng nạp V7
MAX_NAMES = 20
MAX_SAMPLES = 3
CREATE_FIELDS = {"book_name", "commodity", "transport_mode", "booking_names", "idempotency_key"}
NAME_FIELDS = {"customer_id", "expected_version", "idempotency_key", "name", "remove"}


def booking_name(value: Any) -> str | None:
    """Tên chủ hàng như hàng chờ so: NFC, bỏ khoảng trắng hai đầu và thừa, viết hoa. Rỗng, dài quá 200, có ký tự điều khiển: None."""
    if not isinstance(value, str):
        return None
    text = " ".join(unicodedata.normalize("NFC", value).strip().upper().split())
    if not text or len(text) > 200 or any(unicodedata.category(char) == "Cc" for char in text):
        return None
    return text


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


def handle_create(raw: bytes, runner, actor: str) -> tuple[int, dict]:
    """POST /api/v7/admin/customers: `{book_name, commodity, transport_mode, booking_names, idempotency_key}` → sổ mới, nợ 0.

    Tên sổ giữ như gõ (bỏ khoảng trắng hai đầu) vì khi chạy song song nó phải trùng tên tab trên Sheet; mặt hàng trống là chưa gán;
    phương thức bắt buộc (CANG/BO) để chuyến biển hay bộ vào đúng sổ. Tên booking chuẩn hóa, bỏ trùng, tối đa MAX_NAMES."""
    body = _body(raw, CREATE_FIELDS)
    book = body.get("book_name")
    if not isinstance(book, str) or not book.strip() or len(book.strip()) > 200:
        bad("INVALID_BOOK_NAME", ERRORS["INVALID_BOOK_NAME"][1])
    commodity = body.get("commodity")
    if commodity is not None and (not isinstance(commodity, str) or len(commodity.strip()) > 80):
        bad()
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
    payload = {"book_name": book.strip(), "commodity_name": commodity.strip() if isinstance(commodity, str) and commodity.strip() else None,
               "book_mode": mode, "booking_names": names, "idempotency_key": _key(body.get("idempotency_key"))}
    return 200, runner.run("create_customer", payload, actor)


def handle_booking_name(raw: bytes, runner, actor: str) -> tuple[int, dict]:
    """POST /api/v7/admin/booking-names: `{customer_id, expected_version, idempotency_key, name, remove}` gán hay bỏ một tên booking."""
    body = _body(raw, NAME_FIELDS)
    if set(body) != NAME_FIELDS or not positive_int(body["customer_id"]) or type(body["expected_version"]) is not int \
            or body["expected_version"] < 0 or type(body["remove"]) is not bool:
        bad()
    name = booking_name(body["name"])
    if name is None:
        bad("INVALID_BOOKING_NAME", ERRORS["INVALID_BOOKING_NAME"][1])
    payload = {"customer_id": body["customer_id"], "expected_version": body["expected_version"],
               "idempotency_key": _key(body["idempotency_key"]), "name": name, "remove": body["remove"]}
    return 200, runner.run("set_booking_name", payload, actor)


def _tab_index(prices: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in prices.get("rows") or []:
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


def unmapped(customers: list[dict[str, Any]]) -> dict[str, Any]:
    """Chủ hàng booking chưa có sổ, nhóm theo tên đã chuẩn hóa; bản chụp đọc lỗi thì `state: unavailable`, không đoán."""
    try:
        snapshot = sheet.cached_load(sheet.load_snapshot, sheet.SHEET_SNAPSHOT_PATH)
        baseline = sheet.cached_load(sheet.load_baseline, sheet.SHEET_BASELINE_PATH)
        prices = sheet.cached_load(sheet.load_price_snapshot, sheet.PRICE_SNAPSHOT_PATH)
    except (OSError, ValueError):
        return {"state": "unavailable", "owners": []}
    queue = sheet.cached_queue(snapshot, customers, baseline)
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
    road_state = "ok"
    try:
        road = sheet.cached_load(sheet.load_road_snapshot, sheet.ROAD_SNAPSHOT_PATH)
        road_queue = sheet.cached_road_queue(road, prices, customers)
        waiting = {(item["container"], item["event_date"]) for item in road_queue.get("skipped") or [] if item.get("reason") == "NO_TAB"}
        for row in road.get("rows") or []:
            key = (container_key(row.get("container")), str(row.get("event_date") or ""))
            if key in waiting:
                add("BO", row.get("owner"), *key)
    except (OSError, ValueError):
        road_state = "unavailable"
    index = _tab_index(prices)
    books = owners([{**c, "key": c["id"]} for c in customers if type(c.get("id")) is int and c.get("status") == "active"])
    result = []
    for group in groups.values():
        trips = sorted(group["trips"], key=lambda trip: trip[1])
        tabs = _tabs_for(trips, index)
        sheet_tabs = [{"tab": tab, "trips": count, "customer_id": books[name_key(tab)][0] if name_key(tab) in books else None}
                      for tab, count in tabs.most_common()]
        suggest = next((tab["customer_id"] for tab in sheet_tabs if tab["customer_id"] is not None), None)
        result.append({"name": group["name"], "family": group["family"], "trips": len(trips), "first": trips[0][1], "last": trips[-1][1],
                       "commodities": [name for name, _ in group["commodities"].most_common()],
                       "containers": [container for container, _ in trips[-MAX_SAMPLES:]],
                       "sheet_tabs": sheet_tabs, "suggest_customer_id": suggest})
    result.sort(key=lambda item: (-item["trips"], item["name"]))
    return {"state": "ok", "road_state": road_state, "owners": result,
            "snapshot_created_at": (snapshot.get("runner") or {}).get("created_at")}


def view(runner, actor: str) -> dict[str, Any]:
    """GET /api/v7/admin/customers: mọi sổ kèm tên booking, và chủ hàng booking chưa có sổ."""
    mapping = sheet.customer_name_mapping()
    customers = [sheet.named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    return {"customers": customers, "unmapped": unmapped(customers)}
