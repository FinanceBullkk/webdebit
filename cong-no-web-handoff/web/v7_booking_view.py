"""Kết quả kiểm sổ so với booking cho khối "Kiểm booking" của tab Máy chạy: sổ web (DU-CHUYEN-01, `web_check`) và Sheet sổ nợ
(KIEM-BOOKING-01).

Số của file job ghi. Riêng nhóm "tháng này chưa lên sổ" (`THANG_CUOI`), `with_web` đọc thêm sổ web (`get_trip_month`, hàm đọc của
Báo cáo tháng): phép kiểm so tab khách trên Sheet, nên chuyến máy đã đưa vào sổ web vẫn nằm trong nhóm tới khi Sheet ghi (đo
24/11/2026: 119/122 dòng).

`state` nói trang được tin số tới đâu, để không bao giờ hiện "không có gì lệch" khi thật ra chưa kiểm:
- `none`: chưa có lượt nào ghi được kết quả (kể cả khi chỉ có lỗi);
- `error`: lượt mới nhất lỗi, số còn lại là của lượt đạt trước đó;
- `stale`: lượt đạt gần nhất cũ hơn lượt liền trước lượt theo lịch gần nhất (:05 mỗi giờ 7–22 giờ; đêm không có lượt). Lượt
  theo lịch gần nhất có thể còn đang chạy, nên chỉ lỡ thêm một lượt là đã cũ;
- `ok`.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import v7_machine
import v7_normalize as normalize
from v7_api_validate import ApiError

FIRST_HOUR, LAST_HOUR, MINUTE = 7, 22, 5      # lịch timer v7-reconcile-auto
PAIR_DAYS = 3   # cùng luật ghép của NGUON-CHUYEN-01 (1) và Báo cáo tháng


def path() -> Path:
    return Path(os.getenv("WEBDEBIT_BOOKING_CHECK_PATH") or v7_machine.base_dir() / "booking-check.json")


def web_path() -> Path:
    """Kết quả so sổ web với booking (DU-CHUYEN-01), lượt đối soát ghi cạnh file kiểm Sheet."""
    return Path(os.getenv("WEBDEBIT_BOOKING_WEB_PATH") or path().with_name("booking-web.json"))


def last_slot(now: datetime) -> datetime:
    """Giờ lượt đối soát gần nhất theo lịch, tính tới `now` (giờ VN)."""
    slot = now.astimezone(v7_machine.VN).replace(minute=MINUTE, second=0, microsecond=0)
    if slot > now:
        slot -= timedelta(hours=1)
    if slot.hour > LAST_HOUR:
        slot = slot.replace(hour=LAST_HOUR)
    elif slot.hour < FIRST_HOUR:
        slot = (slot - timedelta(days=1)).replace(hour=LAST_HOUR)
    return slot


def previous_slot(slot: datetime) -> datetime:
    return last_slot(slot - timedelta(minutes=1))


def _when(text: Any) -> datetime | None:
    try:
        found = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return found if found.tzinfo else None


def view(now: datetime | None = None, source: Path | None = None) -> dict[str, Any]:
    now = now or datetime.now(v7_machine.VN)
    try:
        data = json.loads((source or path()).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        return {"state": "none", "now": now.isoformat(timespec="seconds")}
    checked, error = _when(data.get("checked_at")), data.get("last_error") if isinstance(data.get("last_error"), dict) else None
    error_at = _when((error or {}).get("at"))
    if checked is None or not isinstance(data.get("rows"), list):
        state = "none"
    elif error_at and error_at > checked:
        state = "error"
    elif checked < previous_slot(last_slot(now)):
        state = "stale"
    else:
        state = "ok"
    return {**data, "state": state, "now": now.isoformat(timespec="seconds")}


def both(runner, reads, actor: str, now: datetime | None = None) -> dict[str, Any]:
    """Body của `GET /api/v7/machine/booking`: kết quả kiểm Sheet (như trước, kèm `with_web`) và `web_check` là kết quả so sổ web, cùng
    cách tính `state`. Trang mặc định hiện phần sổ web (tiêu chí số 1)."""
    now = now or datetime.now(v7_machine.VN)
    return {**with_web(view(now), runner, reads, actor), "web_check": view(now, web_path())}


def _cont(raw: Any) -> str:
    return normalize.container_code(raw) or "".join(ch for ch in str(raw or "").upper() if ch.isalnum())


def _day(text: Any) -> date | None:
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


MISSING_CODES = ("CHUA_TINH", "THANG_CUOI")   # booking có, sổ web chưa có: tháng trước và tháng này


def load_web(source: Path) -> dict[str, Any] | None:
    """File so sổ web của lượt đối soát; thiếu hay hỏng thì None (Sổ khách không vẽ dòng mờ, không chặn đọc sổ)."""
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _book_trips(ledger: dict[str, Any]) -> list[tuple[str, date | None, str]]:
    """(container, ngày, tháng) của mọi chuyến trên sổ, kể cả chờ kiểm và đã loại (người đã kết luận), trừ dòng đã xóa."""
    out = []
    for trip in ledger.get("trips") or ():
        if not trip.get("deleted"):
            out.append((_cont(trip.get("container")), _day(trip.get("event_date")), str(trip.get("month") or "")[:7]))
    for row in ledger.get("legacy_rows") or ():
        current = row.get("current") or {}
        if row.get("kind") == "trip" and not current.get("deleted"):
            out.append((_cont(current.get("container")), _day(current.get("event_date")), str(current.get("month") or row.get("month") or "")[:7]))
    return [trip for trip in out if trip[0]]


def book_missing(ledger: dict[str, Any], data: dict[str, Any] | None) -> dict[str, Any]:
    """`booking_missing` của `GET /api/v7/ledger` (DONG-MO-BOOKING-01): chuyến booking mà lượt so sổ web gần nhất thấy sổ này chưa có.

    Sổ khách vẽ mỗi chuyến thành dòng mờ cuối bảng chuyến của tháng ngày booking. Lượt chạy mỗi giờ, nên trước khi trả, bỏ chuyến
    mà sổ nay đã có (cùng container, lệch không quá 3 ngày; dòng không ngày thì cùng tháng): chuyến máy hay người vừa thêm không
    hiện mờ tới lượt sau. Chuyến vừa vào một sổ khác thì vẫn hiện tới lượt sau. Chỉ đọc file của job và sổ đã đọc sẵn."""
    if not isinstance(data, dict) or _when(data.get("checked_at")) is None or not isinstance(data.get("rows"), list):
        return {"unavailable": True, "items": []}
    have = _book_trips(ledger)
    items = []
    for row in data["rows"]:
        source = row.get("source") if isinstance(row, dict) else None
        if (not isinstance(source, dict) or row.get("code") not in MISSING_CODES
                or (row.get("suggest") or {}).get("customer_id") != ledger.get("customer_id")):
            continue
        cont, day = _cont(row.get("container")), _day(source.get("date"))
        if day is None or any(cont == other and (abs((when - day).days) <= PAIR_DAYS if when else month == day.isoformat()[:7])
                              for other, when, month in have):
            continue
        items.append({"container": row.get("container"), "date": day.isoformat(), "kind": source.get("kind"),
                      "ref": source.get("ref") or ""})
    items.sort(key=lambda item: (item["date"], item["container"] or ""))
    return {"checked_at": data["checked_at"], "items": items}


def with_web(body: dict[str, Any], runner, reads, actor: str) -> dict[str, Any]:
    """Gắn `web` (sổ, ngày của chuyến web cùng container, lệch không quá 3 ngày, sổ nào cũng được) cho dòng `THANG_CUOI`.

    `recent_web`: `checked` khi đã so; `unavailable` khi đọc sổ web lỗi, trang giữ một nhóm như trước. Một chuyến web chỉ ghép
    một dòng, cặp lệch ít ngày nhất trước. Chuyến web "chờ kiểm" cũng tính là đã có (hàm đọc chỉ bỏ chuyến đã xóa và bị từ chối).
    Không sửa kết quả đọc (có thể là bản của bộ nhớ đọc).
    """
    rows = [row for row in body.get("rows") or () if isinstance(row, dict) and row.get("code") == "THANG_CUOI"]
    if body.get("state") == "none" or not rows:
        return body
    days = [_day((row.get("source") or {}).get("date")) for row in rows]
    trips: dict[tuple[int, str, date], None] = {}   # khóa (sổ, container, ngày): hai tháng liền kề cùng trả chuyến ở mép tháng
    names: dict[int, Any] = {}
    try:
        for month in sorted({day.isoformat()[:7] for day in days if day}):
            web = reads.run(runner, "get_trip_month", {"month": f"{month}-01"}, actor)
            web = web if isinstance(web, dict) else {}
            names.update({book["id"]: book.get("name") for book in web.get("books") or ()})
            for trip in web.get("trips") or ():
                if (day := _day(trip.get("date"))) is not None:
                    trips[(trip["customer_id"], _cont(trip.get("container")), day)] = None
    except (ApiError, ValueError):
        return {**body, "recent_web": "unavailable"}
    by_cont: dict[str, list[tuple[int, date]]] = {}
    for book, cont, day in trips:
        by_cont.setdefault(cont, []).append((book, day))
    pairs = []
    for index, (row, day) in enumerate(zip(rows, days, strict=True)):
        for book, web_day in by_cont.get(_cont(row.get("container")), ()) if day else ():
            gap = abs((web_day - day).days)
            if gap <= PAIR_DAYS:
                pairs.append((gap, index, book, web_day))
    used_rows: set[int] = set()
    used_trips: set[tuple[int, str, date]] = set()
    for _gap, index, book, web_day in sorted(pairs):
        trip = (book, _cont(rows[index].get("container")), web_day)
        if index in used_rows or trip in used_trips:
            continue
        used_rows.add(index)
        used_trips.add(trip)
        rows[index]["web"] = {"customer_id": book, "name": names.get(book), "date": web_day.isoformat()}
    return {**body, "recent_web": "checked"}
