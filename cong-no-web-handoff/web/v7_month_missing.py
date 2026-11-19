"""Báo cáo tháng: chuyến booking có mà web chưa có, kèm lý do máy chưa đưa vào sổ (BAO-CAO-THANG-02).

`GET /api/v7/report/month/missing?month=YYYY-MM`. Danh sách lấy đúng từ báo cáo tháng (`v7_month_report.build`): chuyến booking
không chuyến web nào ghép. Lý do đọc từ chính các hàng chờ máy dùng để tự dán chuyến (HANG-CHO-01, NGUON-CHUYEN-01), nên trang nói
đúng điều máy đang thấy:

- chuyến biển: hàng chờ CONT_NGUON (`build_queue`) cho biết dòng booking đủ thông tin chưa, gắn được sổ nào, mặt hàng có khớp sổ;
- chuyến bộ: hàng chờ CONT_BO (`build_road_queue`) cho biết vì sao chưa xếp được sổ (`skipped`);
- đã có sổ: chiếu sổ đó (`sheet_projection`, `road_projection`) như tab Việc cần làm, để biết dòng đang chờ, cần người xem
  hay chỉ chờ lượt máy tới.

Chiếu từng sổ tốn 0,1–1,2 giây (đo trên `hao` 19/11/2026), nên trang chỉ gọi route này khi người dùng mở danh sách, và chiếu
tối đa `MAX_BOOKS` sổ. Chỉ đọc: không ghi DB, sổ hay Sheet. Trả mã lý do; chữ cho người đọc ở `bao-cao-thang-model.js` (ARCH-03).
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from datetime import datetime
from typing import Any

import v7_api_sheet as sheet
import v7_machine
import v7_month_report as report
from v7_api_validate import ApiError
from v7_road_queue import ROAD_FROM

MAX_BOOKS = 40
# Tháng khóa mà máy vẫn tự mở, dán, khóa lại (MAY-KHOA-01, `v7_inbox.AUTO_LOCKED_TRIPS_FROM`); tháng cũ hơn thì người duyệt.
AUTO_LOCKED_FROM = "2026-10"


def missing_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Mọi chuyến booking của tháng chưa có chuyến web, kèm khách (tên sổ hoặc chủ hàng) như bảng theo khách."""
    out = []
    for customer in body.get("customers", []):
        for row in customer["rows"]:
            if row["status"] in report.BOOKING_TRIP and not row.get("web"):
                booking = row.get("booking") or {}
                out.append({"name": customer.get("name"), "owner": booking.get("owner") or customer.get("owner"),
                            "book_id": customer.get("book_id"), "cont": row["cont"], "family": row.get("family"),
                            "date": booking.get("date"), "ref": booking.get("ref"), "status": row["status"]})
    out.sort(key=lambda row: (row["date"] or "", row["name"] or row["owner"] or "", row["cont"]))
    return out


def _sea_queue(runner, actor: str) -> dict[tuple[str, str], dict[str, Any]]:
    snapshot = sheet.cached_load(sheet.load_snapshot, sheet.SHEET_SNAPSHOT_PATH)
    baseline = sheet.cached_load(sheet.load_baseline, sheet.SHEET_BASELINE_PATH)
    customers = sheet.with_display_names(runner.run("list_customers", {}, actor)).get("customers", [])
    queue = sheet.build_queue(snapshot, customers, baseline)
    return {(report.container_key(item.get("container")), str(item.get("event_date") or "")[:10]): item for item in queue["items"]}


def _road_queue(runner, actor: str) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], str]]:
    road = sheet.cached_load(sheet.load_road_snapshot, sheet.ROAD_SNAPSHOT_PATH)
    prices = sheet.cached_load(sheet.load_price_snapshot, sheet.PRICE_SNAPSHOT_PATH)
    mapping = sheet.customer_name_mapping()
    customers = [sheet.named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    queue = sheet.cached_road_queue(road, prices, customers)
    placed = {(item["container"], item["event_date"]): item for item in queue["items"]}
    skipped = {(item["container"], item["event_date"]): item["reason"] for item in queue.get("skipped") or ()}
    return placed, skipped


def _nearest(index: dict[tuple[str, str], Any], cont: str, day: str | None) -> Any:
    """Dòng hàng chờ cùng container, cùng ngày; không có thì lệch ít ngày nhất trong ±3 ngày (luật ghép NGUON-CHUYEN-01)."""
    if not day:
        return None
    if (cont, day) in index:
        return index[(cont, day)]
    near = [(abs((dt.date.fromisoformat(other) - dt.date.fromisoformat(day)).days), other) for c, other in index
            if c == cont and other]
    near = [pair for pair in near if pair[0] <= report.PAIR_DAYS]
    return index[(cont, min(near)[1])] if near else None


def _project(runner, actor: str, book: int, road: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = runner.run("get_ledger", {"customer_id": book}, actor)
    projection = (sheet.road_projection if road else sheet.sheet_projection)(runner, ledger, actor)
    return ledger, projection


def _from_projection(ledger: dict[str, Any], projection: dict[str, Any], cont: str, day: str) -> str:
    items = [*(projection.get("items") or ()), *(projection.get("waiting_items") or ())]
    index = {(report.container_key(item.get("container")), str(item.get("event_date") or "")[:10]): item for item in items}
    item = _nearest(index, cont, day)
    if item is None:
        return "IN_BOOK_OTHER_DATE"   # sổ đã có chuyến này (dòng sổ gốc cùng booking hay khác ngày): hàng chờ không hiện lại
    if item.get("sync_state") == "WAITING":
        return str(item.get("sync_reason") or "WAITING")
    if item.get("sync_state") == "CONFLICT" or item.get("closed"):
        return "NEEDS_REVIEW"
    month = str(item.get("event_date") or day)[:7]
    if month < AUTO_LOCKED_FROM and sheet._month_locked(ledger, month):
        return "MONTH_LOCKED"
    return "NEXT_RUN"


def explain(rows: list[dict[str, Any]], runner, actor: str, today: str) -> list[dict[str, Any]]:
    """Gắn `reason` (mã) và `book_id` (sổ máy chọn, nếu có) cho từng chuyến. Lỗi một nguồn chỉ làm chuyến đó thành `UNKNOWN`."""
    sea = road = skipped = None
    try:
        sea = _sea_queue(runner, actor) if any(row["family"] == "BIEN" for row in rows) else {}
    except (ValueError, ApiError):
        sea = None
    try:
        road, skipped = _road_queue(runner, actor) if any(row["family"] == "BO" for row in rows) else ({}, {})
    except (ValueError, ApiError):
        road = None
    wanted: dict[tuple[int, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row["reason"], row["machine_book"] = "UNKNOWN", None
        day = row["date"]
        if day and day > today:
            row["reason"] = "FUTURE"
        elif row["family"] == "BIEN" and sea is not None:
            item = _nearest(sea, row["cont"], day)
            if item is None:
                row["reason"] = "NOT_IN_SOURCE"
            elif item.get("status") != "READY":
                row["reason"] = "SOURCE_INCOMPLETE"
            elif item.get("customer_id") is None:
                row["reason"] = "NO_BOOK"
            elif item.get("book_match") in ("COMMODITY_MISMATCH", "COMMODITY_UNKNOWN", "ROAD_BOOK"):
                row["reason"], row["machine_book"] = item["book_match"], item["customer_id"]
            else:
                row["machine_book"] = item["customer_id"]
                wanted[(item["customer_id"], False)].append(row)
        elif row["family"] == "BO" and road is not None:
            item = _nearest(road, row["cont"], day)
            if item is not None:
                row["machine_book"] = item["customer_id"]
                wanted[(item["customer_id"], True)].append(row)
            else:
                code = _nearest(skipped, row["cont"], day)
                row["reason"] = f"ROAD_{code}" if code else ("ROAD_EARLY" if (day or "") < ROAD_FROM else "NOT_IN_SOURCE")
    for count, ((book, is_road), group) in enumerate(sorted(wanted.items())):
        if count >= MAX_BOOKS:
            for row in group:
                row["reason"] = "NOT_CHECKED"
            continue
        try:
            ledger, projection = _project(runner, actor, book, is_road)
        except (ValueError, ApiError):
            continue   # giữ UNKNOWN
        for row in group:
            row["reason"] = _from_projection(ledger, projection, row["cont"], row["date"])
    return rows


def handle_get(query: str, runner, reads, actor: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(v7_machine.VN)
    month = report.parse_month(query, now)
    web = reads.run(runner, "get_trip_month", {"month": f"{month}-01"}, actor)
    body = report.build(month, report.read_report(), web if isinstance(web, dict) else {}, now)
    rows = missing_rows(body)
    today = now.astimezone(v7_machine.VN).date().isoformat()
    return {"month": month, "state": body["state"], "checked_at": body["checked_at"], "now": now.isoformat(timespec="seconds"),
            "rows": explain(rows, runner, actor, today)}
