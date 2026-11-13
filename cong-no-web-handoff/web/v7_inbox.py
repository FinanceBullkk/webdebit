"""Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): việc của hàng chờ Sheet ở mọi sổ, chỉ đọc.

Mỗi sổ chiếu bằng đúng `ledger_projections` như khi mở sổ (trung vị khoảng 0,3 giây/sổ trên `hao`, đo 4/11/2026), nên API tính nền và giữ kết
quả trong bộ nhớ: lúc khởi động, khi bản chụp Sheet đổi, và từng sổ ngay sau một lệnh ghi lên sổ đó. Không gọi hàm ghi.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import threading
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from v7_api_sheet import (  # hàm đọc dùng chung chỉ chạy một lần mỗi lượt
    SharedReads,
    cached_load,
    paste_sheet_rows,
    price_projection,
    ps_projection,
    road_projection,
    sheet_projection,
    write_price_items,
    write_ps_items,
)
from v7_api_validate import ApiError
from v7_ps_queue import auto_ps, best_columns
from v7_road_queue import NOTE as ROAD_NOTE

ACTOR = "hop-viec"   # đọc nền, không phải người; hàm đọc chỉ cần sokhach.actor khác rỗng
WORKERS = 2   # đo trên `hao` 1/11/2026: 4 luồng làm mở sổ lúc đang tính chậm 1,36 s, 2 luồng 0,84 s (hộp 34 → 39 s)
DIRTY_INLINE_LIMIT = 5   # quá số này thì tính lại nền, không giữ GET chờ
# Ba runner (chuyến, giá, PS) ghi bản chụp cách nhau vài chục giây mỗi 15 phút; chờ file mới nhất cũ hơn chừng này
# mới tính lại, để mỗi đợt Sheet chỉ một lượt thay vì ba (đo trên `hao` 1/11/2026).
SETTLE_SECONDS = 90
TICK_SECONDS = 60   # nhịp nền: xem bản chụp Sheet đã đổi chưa (runner 15 phút một lần)
# P3a (HANG-CHO-01 Q1, KHOA-CHU-01): máy tự lấy theo Sheet khi dòng lệch chỉ ở các ô chữ này (không đụng tiền). Bật bằng
# WEBDEBIT_AUTO_SHEET=text trên `hao`; mặc định tắt. Người làm trong Lịch sử là AUTO_ACTOR ("Máy (theo Sheet)").
AUTO_ACTOR = "may-theo-sheet"
AUTO_FIELDS = {"carrier", "shipper", "origin", "destination"}
# Số việc máy vừa làm giữ trong RAM để hiện "Máy đã tự làm". Thử bản sao 3/11/2026: lượt đầu bật chuyến bộ có 195 chuyến
# + 195 giá, trần 300 cũ làm rơi 90 chuyến khỏi số đếm hôm nay.
AUTO_LOG = 2000
# P3b (HANG-CHO-01 Q2 theo Q5 A, specs/v7-hop-ngoai-le-p3b.md): máy bấm thay "Duyệt" cho chuyến mới khớp đúng sổ theo
# mặt hàng, tháng mở, ngày không sau hôm nay. Bật bằng WEBDEBIT_AUTO_SHEET=trips (gộp được: "text,trips").
# MAY-KHOA-01 (3/11/2026): khóa tháng chỉ chặn người. Máy mở tháng khóa, ghi, khóa lại ngay (ba lệnh có sẵn, đều vào
# Lịch sử) để điền ngày cho dòng sổ gốc không ngày ở mọi tháng, và đưa chuyến mới vào tháng khóa từ tháng này trở đi
# (trước đó sổ gốc là chuẩn).
AUTO_LOCKED_TRIPS_FROM = "2026-10"
# MAY-GIA-01 (3/11/2026): máy ghi giá Sheet sẵn sàng (READY, và dòng chỉ vướng tháng khóa) như nút "Ghi N giá từ Sheet",
# ở mọi tháng nợ từ mốc này, tháng mở hay khóa; tháng khóa thì mở, ghi, khóa lại. Bật bằng WEBDEBIT_AUTO_SHEET=prices.
AUTO_PRICES_FROM = AUTO_LOCKED_TRIPS_FROM
# NGUON-CHUYEN-01 GĐ3 (3/11/2026): máy đưa chuyến bộ mới (CONT_BO) vào sổ của tab khách trên Sheet, bằng đúng đường dán của
# chuyến biển, chưa có giá; tháng khóa thì mở, dán, khóa lại. Bật bằng WEBDEBIT_AUTO_SHEET=road.
# MAY-PS-01 (4/11/2026): máy tự tách phụ phí theo bảng PS và tự chọn cột, ở mọi tháng vì không đổi tiền; tháng khóa thì mở,
# ghi, khóa lại. Bật bằng WEBDEBIT_AUTO_SHEET=ps.
# Rà máy tự ghi 4/11/2026: mở–ghi–khóa là ba lệnh riêng, API tắt giữa chừng (mỗi lần triển khai) thì tháng nằm mở. Lượt sau
# khóa lại tháng máy đã mở mà chưa khóa, khi lần mở cũ hơn chừng này (không giành tháng của một lượt máy khác đang ghi dở).
RELOCK_AFTER_SECONDS = 600
# MAY-DOI-SOAT-01: kết quả lượt đối soát gần nhất của máy (tools/v7_reconcile_auto.py, timer mỗi giờ), API chỉ đọc.
RECONCILE_PATH = os.getenv("WEBDEBIT_RECONCILE_PATH") or "/var/lib/webdebit-sheet-sync/reconcile.json"


def auto_prices(prices: dict[str, Any]) -> list[dict[str, Any]]:
    """Dòng giá Sheet máy được ghi (MAY-GIA-01): READY và MONTH_LOCKED, tháng nợ từ AUTO_PRICES_FROM.

    Giá khác web, nhiều chuyến khớp, phụ phí gõ tay, chuyến chờ kiểm vẫn ở "Cần xem" cho người quyết.
    """
    rows = list(prices.get("ready") or []) + [row for row in prices.get("review") or [] if row.get("status") == "MONTH_LOCKED"]
    return [row for row in rows if str(row.get("month") or "") >= AUTO_PRICES_FROM]


def date_fill(item: dict[str, Any]) -> bool:
    """Dòng sổ gốc không ngày khớp dòng Sheet cùng tháng nợ: máy điền ngày theo Sheet, không đổi tiền (MAY-KHOA-01)."""
    month = str(item.get("event_date") or "")[:7]
    return ("event_date" in (item.get("changed_fields") or []) and item.get("existing_kind") == "legacy"
            and not (item.get("existing_values") or {}).get("event_date")
            and month != "" and str(item.get("existing_debt_month") or "")[:7] == month)


def auto_enabled(kind: str) -> bool:
    return kind in {part.strip() for part in os.getenv("WEBDEBIT_AUTO_SHEET", "").split(",")}


def _vn_day(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp + 7 * 3600, UTC).date().isoformat()
TEXT_FIELDS = {"origin", "destination", "shipper", "carrier", "shipper_unavailable"}


def _vnd(value: Any) -> int | None:
    text = str(value) if value is not None else ""
    return int(text) if text.lstrip("-").isdigit() else None


def _locked_months(ledger: dict[str, Any], months: set[str]) -> list[str]:
    """Tháng (yyyy-mm) đang khóa trong `months`: cờ đã ghi thắng; tháng không có hàng thì chỉ tháng hiện tại mở."""
    flags = {str(row.get("month") or "")[:7]: row.get("locked") for row in ledger.get("month_locks") or []}
    today = str(ledger.get("today_month") or "")[:7]
    return sorted(m for m in months if (flags[m] is True if m in flags else m != today))


def in_month(runner, customer_id: int, version: int, ledger: dict[str, Any], month: str, key: str,
             action: Callable[[int], int]) -> int:
    """Chạy `action(version)`; tháng `month` (yyyy-mm) đang khóa thì máy mở, chạy, khóa lại (MAY-KHOA-01).

    Khóa chống ghi trùng của lệnh mở/khóa gắn phiên bản sổ lúc đó, nên mỗi lần là một lệnh mới. Lệnh chính lỗi thì vẫn
    khóa lại rồi ném lỗi.
    """
    if not _locked_months(ledger, {month}):
        return action(version)

    def lock(locked: bool, at: int) -> int:
        digest = hashlib.sha256(f"{key}:khoa:{month}:{locked}:{at}".encode()).hexdigest()
        return runner.run("set_month_lock", {"customer_id": customer_id, "expected_version": at, "idempotency_key": digest,
                                             "month": month + "-01", "locked": locked}, AUTO_ACTOR).get("version", at + 1)

    version = lock(False, version)
    try:
        version = action(version)
    finally:
        current = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["version"]
        version = lock(True, current)
    return version


def _read_reconcile(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("reconcile file invalid")
    return data


def reconcile_result() -> dict[str, Any] | None:
    """Kết quả máy đối soát gần nhất; chưa có file hoặc file hỏng thì None, không làm hỏng hộp việc."""
    try:
        return cached_load(_read_reconcile, RECONCILE_PATH)
    except (OSError, ValueError):
        return None


def _epoch(at: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(at)).timestamp()
    except ValueError:
        return None


def machine_left_open(ledger: dict[str, Any], now: float) -> list[str]:
    """Tháng (yyyy-mm) máy đã mở mà chưa khóa lại: cờ đang mở, không phải tháng hiện tại, và lần đổi khóa gần nhất của
    tháng đó là máy mở, cũ hơn RELOCK_AFTER_SECONDS. Tháng người mở (lần đổi gần nhất là người) giữ nguyên."""
    today = str(ledger.get("today_month") or "")[:7]
    open_months = {str(row.get("month") or "")[:7] for row in ledger.get("month_locks") or [] if row.get("locked") is False}
    latest: dict[str, dict] = {}
    for event in ledger.get("events") or []:   # get_ledger trả mới nhất trước
        month = str((event.get("after") or {}).get("month") or "")[:7]
        if event.get("kind") == "month_lock" and month in open_months:
            latest.setdefault(month, event)
    left = []
    for month, event in sorted(latest.items()):
        at = _epoch(event.get("at"))
        if (month != today and event.get("actor") == AUTO_ACTOR and (event.get("after") or {}).get("locked") is False
                and at is not None and now - at >= RELOCK_AFTER_SECONDS):
            left.append(month)
    return left


def machine_entries(customer_id: int, ledger: dict[str, Any], day: str) -> list[dict[str, Any]]:
    """Việc máy đã làm ở một sổ trong ngày `day` (giờ VN), dựng lại từ Lịch sử theo đúng dạng của `auto_log`.

    Danh sách trong RAM mất mỗi lần API khởi động lại (mỗi lần triển khai); lượt nền đầu tiên nạp lại từ đây, nên người
    nhập vẫn soát được việc máy làm trước đó. Mới nhất trước.
    """
    trips = {trip.get("id"): trip for trip in ledger.get("trips") or []}
    legacy = {row.get("id"): row.get("current") or {} for row in ledger.get("legacy_rows") or []}
    events = []
    for event in ledger.get("events") or []:
        at = _epoch(event.get("at"))
        if event.get("actor") == AUTO_ACTOR and at is not None and _vn_day(at) == day:
            events.append((at, event.get("kind"), event.get("before") or {}, event.get("after") or {}))
    unlocks = [(at, str(after.get("month") or "")[:7]) for at, kind, _, after in events
               if kind == "month_lock" and after.get("locked") is False]

    def locked(month: str, at: float) -> bool:   # máy vừa mở tháng này trong cùng lượt: tháng đang khóa
        return any(m == month and 0 <= at - t <= RELOCK_AFTER_SECONDS for t, m in unlocks)
    entries: list[dict[str, Any]] = []
    legacy_prices: dict[Any, dict[str, Any]] = {}
    for at, kind, before, after in reversed(events):   # cũ trước: gộp hai ô giá của cùng một dòng sổ gốc
        base = {"at": at, "customer_id": customer_id}
        if kind == "sheet_conflict_resolved" and after.get("decision") == "use_sheet":
            target = after.get("target") or {}
            row = trips.get(target.get("id")) if target.get("kind") == "trip" else legacy.get(target.get("id"))
            entries.append(base | {"container": (row or {}).get("container"), "field": after.get("field"),
                                   "before": before.get("value"), "after": str(after.get("sheet_value") or "").strip()})
        elif kind == "legacy_edit" and isinstance(after.get("legacy"), dict):
            new, old = after["legacy"], before.get("legacy") or {}
            if new.get("field") == "event_date":
                entries.append(base | {"container": new.get("container"), "field": "event_date",
                                       "before": old.get("value"), "after": new.get("value")})
            elif new.get("field") in ("unit_price_vnd", "other_fee_vnd"):
                month = str(new.get("debt_month") or new.get("month") or "")[:7]
                entry = legacy_prices.get(new.get("legacy_row_id"))
                if entry is None:
                    entry = legacy_prices[new.get("legacy_row_id")] = base | {
                        "kind": "price", "container": new.get("container"), "date": new.get("event_date"), "month": month,
                        "before_unit_price_vnd": old.get("unit_price_vnd"), "before_other_fee_vnd": old.get("other_fee_vnd"),
                        "locked": locked(month, at)}
                    entries.append(entry)
                entry.update(at=at, unit_price_vnd=new.get("unit_price_vnd"), other_fee_vnd=new.get("other_fee_vnd"))
        elif kind == "price_edit":
            new, old = after.get("price") or {}, before.get("price") or {}
            trip = trips.get(new.get("trip_id")) or {}
            month = str(trip.get("month") or "")[:7]
            entries.append(base | {"kind": "price", "container": trip.get("container"), "date": trip.get("event_date"),
                                   "month": month, "unit_price_vnd": new.get("unit_price_vnd"),
                                   "other_fee_vnd": new.get("other_fee_vnd"),
                                   "before_unit_price_vnd": old.get("unit_price_vnd"),
                                   "before_other_fee_vnd": old.get("other_fee_vnd"), "locked": locked(month, at)})
        elif kind == "rewrite_trip_fees":
            for target in after.get("targets") or []:
                row = trips.get(target.get("trip_id")) or legacy.get(target.get("legacy_row_id")) or {}
                month = str(row.get("month") or "")[:7]
                entries.append(base | {"kind": "ps", "container": row.get("container"), "date": row.get("event_date"),
                                       "month": month, "locked": locked(month, at)})
        elif kind == "paste":
            for row in after.get("trips") or []:
                entries.append(base | {"kind": "trip", "container": row.get("container"), "event_date": row.get("event_date"),
                                       "trip_id": row.get("trip_id"), "pending": row.get("status") != "confirmed",
                                       **({"road": True} if row.get("note") == ROAD_NOTE else {})})
    return sorted(entries, key=lambda entry: entry["at"], reverse=True)


def _receipt_item(row: dict[str, Any], ready: bool) -> dict[str, Any]:
    note = str(row.get("note") or "").strip()
    return {"status": "READY" if ready else str(row.get("status") or "REVIEW"), "date": row.get("date"),
            "amount_vnd": row.get("amount_vnd"), "debt_month": str(row.get("debt_month") or "")[:10] or None,
            "note": note[:80]}


def summarize(customer_id: int, ledger: dict[str, Any]) -> dict[str, Any] | None:
    """Gom kết quả chiếu của một sổ thành bảy nhóm; None khi sổ không có việc.

    P2 (specs/v7-hop-ngoai-le-p2.md): kèm phiên bản và tổng còn nợ của sổ, danh sách phiếu thu và bản chụp để hộp ghi
    được phiếu bằng lệnh duyệt đang có, và các tháng đang khóa của phiếu sẵn sàng (chỉ để báo, lệnh ghi không chặn).
    """
    sync = ledger.get("sheet_sync") or {}
    receipts = ledger.get("sheet_receipts") or {}
    prices = ledger.get("sheet_prices") or {}
    ps = ledger.get("ps_fees") or {}
    for part in (sync, receipts, prices, ps):
        if part.get("unavailable"):
            raise ValueError("projection unavailable")
    receipt_rows = list(receipts.get("ready") or []) + list(receipts.get("review") or [])
    receipt_amounts = [_vnd(row.get("amount_vnd")) for row in receipt_rows]
    removed = list(sync.get("removed_items") or [])
    removed_amounts = [_vnd(row.get("amount_vnd")) for row in removed]
    trips_new = 0
    text_diff = 0
    check_reasons: dict[str, int] = {}
    for item in sync.get("items") or []:
        state, reason = item.get("sync_state"), item.get("sync_reason") or ""
        if state == "NEW":
            trips_new += 1
        elif state == "CONFLICT":
            fields = set(item.get("changed_fields") or [])
            fill = date_fill(item)
            if fill:
                fields.discard("event_date")
            if reason == "DIFFERENT_FIELDS" and (fill or fields) and fields <= TEXT_FIELDS:
                text_diff += 1
            else:
                key = "FIELDS" if reason == "DIFFERENT_FIELDS" else reason
                check_reasons[key] = check_reasons.get(key, 0) + 1
    # Chuyến bộ (NGUON-CHUYEN-01 GĐ3) đếm chung "chuyến mới"/"cần xem"; road.json hỏng thì phần này trống, sổ vẫn tính.
    road_new = 0
    for item in (ledger.get("sheet_road") or {}).get("items") or []:
        if item.get("sync_state") == "NEW":
            road_new += 1
        elif item.get("sync_state") == "CONFLICT":
            key = "ROAD_" + str(item.get("sync_reason") or "")
            check_reasons[key] = check_reasons.get(key, 0) + 1
    trips_new += road_new
    ready_rows = list(receipts.get("ready") or [])
    book = {
        "customer_id": customer_id,
        "version": ledger.get("version"),
        "outstanding_vnd": ledger.get("total_outstanding_vnd"),
        "receipts": {"ready": len(ready_rows), "review": len(receipts.get("review") or []),
                     "amount_vnd": str(sum(a for a in receipt_amounts if a is not None)),
                     "ready_amount_vnd": str(sum(a for a in (_vnd(r.get("amount_vnd")) for r in ready_rows) if a is not None)),
                     "snapshot_sha256": receipts.get("snapshot_sha256"),
                     "items": [_receipt_item(r, True) for r in ready_rows]
                     + [_receipt_item(r, False) for r in receipts.get("review") or []],
                     "locked_months": _locked_months(ledger, {str(r.get("date") or "")[:7] for r in ready_rows if r.get("date")})},
        "removed": {"count": len(removed), "amount_vnd": str(sum(a for a in removed_amounts if a is not None))},
        "trips_new": trips_new,
        "road_new": road_new,   # phần chuyến bộ trong `trips_new`: máy đưa vào khi bật `road`; không cộng vào `busy`
        "trips_check": {"count": sum(check_reasons.values()), "reasons": check_reasons},
        "text_diff": text_diff,
        "prices": {"ready": len(prices.get("ready") or []), "review": len(prices.get("review") or [])},
        "prices_auto": len(auto_prices(prices)),   # phần của hai nhóm trên máy ghi được; không cộng vào `busy`
        "prices_conflict": sum(row.get("status") == "CONFLICT" for row in prices.get("review") or []),   # không cộng vào `busy`
        "ps": {"ready": len(ps.get("ready") or []), "review": len(ps.get("review") or [])},
        "ps_auto": len(auto_ps(ps)),   # phần của nhóm trên máy tách được; không cộng vào `busy`
    }
    busy = (book["receipts"]["ready"] + book["receipts"]["review"] + book["removed"]["count"] + trips_new
            + book["trips_check"]["count"] + text_diff + sum(book["prices"].values()) + sum(book["ps"].values()))
    return book if busy else None


class Inbox:
    def __init__(self, project: Callable[[Any, dict, str], dict], snapshot_paths: Callable[[], tuple[str, ...]],
                 sheet_status: Callable[[], dict] | None = None, clock: Callable[[], float] | None = None):
        self.project = project                  # ledger_projections
        self.snapshot_paths = snapshot_paths    # đọc lúc gọi để test vá được đường dẫn
        self.sheet_status = sheet_status or (lambda: {})
        self.clock = clock or (lambda: datetime.now(UTC).timestamp())
        self.lock = threading.Lock()
        self.dirty_lock = threading.Lock()   # một lượt tính sổ vừa ghi tại một lúc (view)
        self.books: dict[int, dict] = {}
        self.failed: set[int] = set()
        self.total = 0
        self.done = 0
        self.computed_at: float | None = None
        self.key: tuple | None = None
        self.running = False
        self.dirty: set[int] = set()
        self.unavailable = False
        self.auto_log: deque = deque(maxlen=AUTO_LOG)
        self.auto_errors = 0
        self.auto_run_at: float | None = None
        self.machine_open: dict[int, list[str]] = {}    # tháng máy đã mở mà chưa khóa, theo sổ (lượt nền vừa đọc)
        self.machine_seen: dict[int, list[dict]] = {}   # việc máy làm hôm nay theo Lịch sử, chờ nạp vào auto_log
        self.seeded_day: str | None = None
        self.stopped = threading.Event()   # đặt để dừng nhịp nền (test)

    def _key(self) -> tuple | None:
        try:
            return tuple(os.stat(path).st_mtime_ns for path in self.snapshot_paths())
        except OSError:
            return None

    def _settled(self, key: tuple | None) -> bool:
        return key is None or self.clock() - max(key) / 1e9 >= SETTLE_SECONDS

    def _one(self, runner, customer_id: int) -> tuple[int, dict | None, bool]:
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, ACTOR)
            with contextlib.suppress(Exception):   # đọc Lịch sử của máy hỏng không làm sổ thành `failed`
                self._note_machine(customer_id, ledger)
            return customer_id, summarize(customer_id, self.project(runner, ledger, ACTOR)), True
        except Exception:  # noqa: BLE001  một sổ lỗi không chặn sổ khác; sổ đó vào `failed`
            return customer_id, None, False

    def _note_machine(self, customer_id: int, ledger: dict[str, Any]) -> None:
        now = self.clock()
        left = machine_left_open(ledger, now)
        day = _vn_day(now)
        seen = machine_entries(customer_id, ledger, day) if self.seeded_day != day else []
        with self.lock:
            if left:
                self.machine_open[customer_id] = left
            else:
                self.machine_open.pop(customer_id, None)
            if seen:
                self.machine_seen[customer_id] = seen

    def _error(self, step: str, customer_id: int, error: Any) -> None:
        """Một lỗi của máy: đếm cho Việc cần làm và ghi một dòng journal, để còn thấy sau khi API khởi động lại."""
        self.auto_errors += 1
        code = getattr(error, "code", None) or (error if isinstance(error, str) else type(error).__name__)
        print(f"V7 máy (theo Sheet): {step} sổ {customer_id} lỗi {code}", file=sys.stderr, flush=True)

    def _relock(self, runner) -> None:
        """Khóa lại tháng máy đã mở mà chưa khóa (API tắt giữa lúc mở–ghi–khóa, hoặc lệnh khóa lại lỗi)."""
        with self.lock:
            todo = sorted((customer_id, months) for customer_id, months in self.machine_open.items() if months)
        for customer_id, months in todo:
            for month in months:
                try:
                    ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
                    if month not in machine_left_open(ledger, self.clock()):
                        continue
                    key = hashlib.sha256(f"{AUTO_ACTOR}:khoa-lai:{customer_id}:{month}:{ledger['version']}".encode()).hexdigest()
                    runner.run("set_month_lock", {"customer_id": customer_id, "expected_version": ledger["version"],
                                                  "idempotency_key": key, "month": month + "-01", "locked": True}, AUTO_ACTOR)
                    print(f"V7 máy (theo Sheet): khóa lại tháng {month} sổ {customer_id} (máy đã mở mà chưa khóa)",
                          file=sys.stderr, flush=True)
                except ApiError as exc:
                    self._error("khóa lại tháng", customer_id, exc)

    def _seed_log(self) -> None:
        """Lượt đầu mỗi ngày, gồm lượt đầu sau khi API khởi động: RAM chưa có việc nào của hôm nay thì nạp từ Lịch sử."""
        day = _vn_day(self.clock())
        with self.lock:
            if self.seeded_day == day:
                return
            if not any(_vn_day(entry["at"]) == day for entry in self.auto_log):
                self.auto_log.clear()   # chỉ còn việc của ngày trước, view không hiện nữa
                self.auto_log.extend(sorted((entry for items in self.machine_seen.values() for entry in items),
                                            key=lambda entry: entry["at"], reverse=True))   # mới nhất ở đầu, như appendleft
            self.machine_seen.clear()
            self.seeded_day = day

    def _apply(self, customer_id: int, book: dict | None, ok: bool) -> None:
        self.books.pop(customer_id, None)
        self.failed.discard(customer_id)
        if not ok:
            self.failed.add(customer_id)
        elif book is not None:
            self.books[customer_id] = book

    def refresh_all(self, runner) -> None:
        """Một lượt tính cả mọi sổ (chạy ở luồng nền)."""
        key = self._key()
        shared = SharedReads(runner)
        try:
            customers = [c["id"] for c in shared.run("list_customers", {}, ACTOR).get("customers", [])
                         if type(c.get("id")) is int and c.get("status") == "active"]
        except Exception:  # noqa: BLE001
            with self.lock:
                self.running = False
            return
        with self.lock:
            self.total, self.done = len(customers), 0
        books: dict[int, dict] = {}
        failed: set[int] = set()
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for customer_id, book, ok in pool.map(lambda c: self._one(shared, c), customers):
                if not ok:
                    failed.add(customer_id)
                elif book is not None:
                    books[customer_id] = book
                with self.lock:
                    self.done += 1
        self._seed_log()   # trước các bước máy của lượt này, để RAM chưa có việc nào của lượt
        self._relock(shared)
        text, trips, prices, road, ps = (auto_enabled(kind) for kind in ("text", "trips", "prices", "road", "ps"))

        def pasting(book: dict) -> bool:
            return bool((trips and book["trips_new"] - book["road_new"]) or (road and book["road_new"]))
        todo = sorted(cid for cid, book in books.items() if (text and book["text_diff"]) or pasting(book)
                      or (prices and book["prices_auto"]) or (ps and book["ps_auto"]))
        if todo and key is not None:
            for customer_id in todo:
                book = books[customer_id]
                if text and book["text_diff"]:
                    self._auto_text(shared, customer_id)
                # Đọc lại chuyến web mọi sổ cho từng sổ: chuyến máy vừa thêm ở sổ trước phải chặn được ở sổ sau.
                if trips and book["trips_new"] - book["road_new"]:
                    self._auto_trips(SharedReads(shared.runner), customer_id)
                if road and book["road_new"]:
                    self._auto_road(SharedReads(shared.runner), customer_id)
                if prices and (book["prices_auto"] or pasting(book)):
                    # Sau lượt dán: chuyến máy vừa đưa vào sổ (chưa giá) nhận giá Sheet ngay trong lượt này.
                    self._auto_prices(shared, customer_id)
                if ps and book["ps_auto"]:
                    self._auto_ps(shared, customer_id)
                result = self._one(shared, customer_id)
                if result[2]:
                    books.pop(customer_id, None)
                    if result[1] is not None:
                        books[customer_id] = result[1]
            self.auto_run_at = self.clock()
        with self.lock:
            self.books, self.failed = books, failed
            self.computed_at, self.key, self.running = self.clock(), key, False
            self.unavailable = key is None

    def _auto_text(self, runner, customer_id: int) -> None:
        """Lấy theo Sheet mọi ô chữ lệch của một sổ, bằng đúng lệnh giải quyết lệch người dùng bấm (decision use_sheet).

        Chỉ dòng lệch toàn ô chữ (AUTO_FIELDS), cộng ngày của dòng sổ gốc không ngày cùng tháng nợ (`date_fill`, sửa bằng
        `edit_legacy_trip`); lệch ngày khác, container, booking, khách khác để người quyết. Ngày điền gom theo tháng: tháng khóa
        chỉ mở rồi khóa lại một lần cho mọi dòng của tháng đó. Mỗi ô một khóa chống ghi trùng cố định theo (bản chụp, dòng
        Sheet, đích, ô, giá trị Sheet). Lỗi ở một sổ dừng sổ đó, lượt sau thử lại.
        """
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            projection = sheet_projection(runner, ledger, AUTO_ACTOR)
        except (ApiError, ValueError) as exc:
            self._error("đọc chữ", customer_id, exc)
            return
        version, digest = ledger.get("version"), projection.get("snapshot_sha256")
        fills: dict[str, list[tuple[dict[str, Any], str]]] = {}
        for item in projection.get("items") or []:
            fields = item.get("changed_fields") or []
            fill = date_fill(item)
            text = [field for field in fields if not (fill and field == "event_date")]
            if (item.get("sync_state") != "CONFLICT" or item.get("sync_reason") != "DIFFERENT_FIELDS" or not fields
                    or not set(text) <= AUTO_FIELDS | ({"shipper_unavailable"} if fill else set())
                    or item.get("existing_kind") not in ("trip", "legacy")):
                continue
            for field in text:
                sheet_value = item.get(field)
                target_value = (item.get("existing_values") or {}).get(field)
                if not isinstance(sheet_value, str) or not sheet_value.strip():
                    continue
                key = hashlib.sha256(f"auto:{digest}:{item.get('source_row')}:{item['existing_kind']}:{item.get('existing_id')}:"
                                     f"{field}:{sheet_value}".encode()).hexdigest()
                try:
                    result = runner.run("resolve_sheet_conflict", {
                        "customer_id": customer_id, "expected_version": version, "idempotency_key": key,
                        "snapshot_sha256": digest, "source_row": item.get("source_row"), "target_kind": item["existing_kind"],
                        "target_id": item.get("existing_id"), "field": field, "target_value": target_value,
                        "sheet_value": sheet_value, "decision": "use_sheet"}, AUTO_ACTOR)
                except ApiError as exc:
                    self._error("lấy chữ", customer_id, exc)
                    return
                version = result.get("version", version)
                with self.lock:
                    self.auto_log.appendleft({"at": self.clock(), "customer_id": customer_id, "container": item.get("container"),
                                              "field": field, "before": target_value, "after": sheet_value.strip()})
            if fill:
                day = str(item["event_date"])[:10]
                fills.setdefault(day[:7], []).append((item, day))
        # Gom theo tháng (đo 3/11/2026: điền từng dòng thì 57 dòng thành 76 cặp mở/khóa trên 28 sổ–tháng, Lịch sử rối).
        for month in sorted(fills):
            def edit_all(at, rows=fills[month]):
                for item, day in rows:
                    key = f"auto:{digest}:{item.get('source_row')}:legacy:{item.get('existing_id')}:event_date:{day}"
                    at = runner.run("edit_legacy_trip", {
                        "customer_id": customer_id, "expected_version": at,
                        "idempotency_key": hashlib.sha256(key.encode()).hexdigest(), "legacy_row_id": item.get("existing_id"),
                        "field": "event_date", "value": day}, AUTO_ACTOR).get("version", at)
                    with self.lock:
                        self.auto_log.appendleft({"at": self.clock(), "customer_id": customer_id,
                                                  "container": item.get("container"), "field": "event_date",
                                                  "before": None, "after": day})
                return at
            try:
                version = in_month(runner, customer_id, version, ledger, month,
                                         f"auto:{digest}:{customer_id}:event_date", edit_all)
            except ApiError as exc:
                self._error("điền ngày", customer_id, exc)
                return

    def _auto_trips(self, runner, customer_id: int) -> None:
        """Dán chuyến mới đủ điều kiện Q2 của một sổ bằng đúng đường của nút "Duyệt" (`paste_sheet_rows`), chưa có giá.

        Chỉ dòng "chuyến mới" khớp sổ theo mặt hàng (`COMMODITY_OK`), ngày không sau hôm nay (giờ VN), tháng nợ đang mở
        hoặc khóa nhưng từ AUTO_LOCKED_TRIPS_FROM (máy mở, dán, khóa lại; MAY-KHOA-01).
        `paste_trips` vẫn tự đẩy chuyến nghi trùng sang "chờ kiểm". Lỗi ở một sổ dừng sổ đó, lượt sau thử lại.
        """
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            projection = sheet_projection(runner, ledger, AUTO_ACTOR)
        except (ApiError, ValueError) as exc:
            self._error("đọc chuyến mới", customer_id, exc)
            return
        today = _vn_day(self.clock())
        rows = [item for item in projection.get("items") or []
                if item.get("sync_state") == "NEW" and item.get("book_match") == "COMMODITY_OK"
                and str(item.get("event_date") or "") <= today]
        locked = set(_locked_months(ledger, {str(item["event_date"])[:7] for item in rows}))
        rows = [item for item in rows if str(item["event_date"])[:7] not in locked
                or str(item["event_date"])[:7] >= AUTO_LOCKED_TRIPS_FROM]
        self._paste_by_month(runner, customer_id, ledger, rows, projection.get("snapshot_sha256"),
                             f"{AUTO_ACTOR}:trips:{customer_id}")

    def _auto_road(self, runner, customer_id: int) -> None:
        """Đưa chuyến bộ mới của một sổ vào sổ bằng đúng đường dán của chuyến biển (`paste_sheet_rows`), chưa có giá.

        Chỉ dòng NEW của `road_projection`: sổ theo tab khách, đã chặn trùng ở sổ này và sổ khác; ngày không sau hôm nay
        (giờ VN), tháng từ AUTO_LOCKED_TRIPS_FROM (tháng khóa thì mở, dán, khóa lại). `paste_trips` vẫn tự đẩy chuyến nghi trùng
        sang "chờ kiểm". Lỗi ở một sổ dừng sổ đó, lượt sau thử lại.
        """
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            projection = road_projection(runner, ledger, AUTO_ACTOR)
        except (ApiError, ValueError) as exc:
            self._error("đọc chuyến bộ", customer_id, exc)
            return
        today = _vn_day(self.clock())
        rows = [item for item in projection.get("items") or [] if item.get("sync_state") == "NEW"
                and str(item.get("event_date") or "") <= today and str(item.get("event_date"))[:7] >= AUTO_LOCKED_TRIPS_FROM]
        self._paste_by_month(runner, customer_id, ledger, rows, projection.get("snapshot_sha256"),
                             f"{AUTO_ACTOR}:road:{customer_id}", road=True)

    def _paste_by_month(self, runner, customer_id: int, ledger: dict[str, Any], rows: list[dict[str, Any]], digest: str,
                        key: str, road: bool = False) -> None:
        """Dán `rows` theo tháng; tháng khóa thì mở, dán, khóa lại một lần (MAY-KHOA-01). Ghi việc đã làm vào `auto_log`."""
        months: dict[str, list[dict[str, Any]]] = {}
        for item in rows:
            months.setdefault(str(item["event_date"])[:7], []).append(item)
        version = ledger.get("version")
        for month in sorted(months):
            batch, out = months[month], {}

            def paste(at, batch=batch, out=out):
                out.update(paste_sheet_rows(runner, customer_id, at, digest, key, batch, AUTO_ACTOR))
                return runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["version"]
            step = "dán chuyến bộ" if road else "dán chuyến mới"
            try:
                version = in_month(runner, customer_id, version, ledger, month, key, paste)
            except ApiError as exc:
                self._error(step, customer_id, exc)
                return
            pending = {entry.get("trip_id") for entry in out.get("pending_review") or []}
            by_row = {item["source_row"]: item for item in batch}
            with self.lock:
                for entry in out.get("pasted") or []:
                    item = by_row.get(entry["source_row"], {})
                    self.auto_log.appendleft({"at": self.clock(), "kind": "trip", "customer_id": customer_id,
                                              "container": item.get("container"), "event_date": item.get("event_date"),
                                              "trip_id": entry["trip_id"], "pending": entry["trip_id"] in pending,
                                              **({"road": True} if road else {})})
            if not out.get("complete"):
                self._error(step, customer_id, out.get("error") or "INCOMPLETE")
                return

    def _auto_prices(self, runner, customer_id: int) -> None:
        """Ghi giá Sheet của một sổ bằng đúng đường của nút "Ghi N giá từ Sheet" (`write_price_items`), MAY-GIA-01.

        Chỉ dòng `auto_prices`; gom theo tháng nợ của chuyến, tháng khóa chỉ mở rồi khóa lại một lần cho cả tháng. Khóa chống ghi
        trùng cố định theo (bản chụp giá, đích, ô) như nút. Lỗi ở một sổ dừng sổ đó, lượt sau thử lại.
        """
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            projection = price_projection(runner, ledger, AUTO_ACTOR)
        except (ApiError, ValueError) as exc:
            self._error("đọc giá", customer_id, exc)
            return
        rows = auto_prices(projection)
        if not rows:
            return
        digest, key = projection.get("snapshot_sha256"), f"{AUTO_ACTOR}:prices:{customer_id}"
        months: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            months.setdefault(row["month"], []).append(row)
        version = ledger.get("version")
        for month in sorted(months):
            batch, out = months[month], {}

            def write(at, batch=batch, out=out):
                out.update(write_price_items(batch, customer_id, at, digest, key, runner, AUTO_ACTOR)[1])
                return out["version"] if out.get("complete") else \
                    runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["version"]
            try:
                version = in_month(runner, customer_id, version, ledger, month, key, write)
            except ApiError as exc:
                self._error("ghi giá", customer_id, exc)
                return
            with self.lock:
                for row in batch[:out.get("written", 0)]:
                    self.auto_log.appendleft({"at": self.clock(), "kind": "price", "customer_id": customer_id,
                                              "container": row.get("container"), "date": row.get("date"), "month": month,
                                              "unit_price_vnd": row.get("sheet_unit_price_vnd"),
                                              "other_fee_vnd": row.get("sheet_other_fee_vnd"),
                                              "before_unit_price_vnd": row.get("web_unit_price_vnd"),
                                              "before_other_fee_vnd": row.get("web_other_fee_vnd"),
                                              "locked": bool(row.get("month_locked"))})
            if not out.get("complete"):
                self._error("ghi giá", customer_id, out.get("error") or "INCOMPLETE")
                return

    def _auto_ps(self, runner, customer_id: int) -> None:
        """Tách phụ phí theo PS của một sổ bằng đúng đường của nút Tách (`write_ps_items`), rồi chọn cột (MAY-PS-01).

        Gom theo tháng, tháng khóa chỉ mở rồi khóa lại một lần. Lệnh tách không đổi tổng còn nợ. Lỗi ở một sổ dừng sổ đó,
        lượt sau thử lại; đã tách được chuyến nào thì vẫn chọn cột.
        """
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            projection = ps_projection(runner, ledger, AUTO_ACTOR)
        except (ApiError, ValueError) as exc:
            self._error("đọc PS", customer_id, exc)
            return
        rows = auto_ps(projection)
        if not rows:
            return
        digest, key = projection.get("snapshot_sha256"), f"{AUTO_ACTOR}:ps:{customer_id}"
        months: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            months.setdefault(str(row["month"])[:7], []).append(row)
        version, total = ledger.get("version"), 0
        locked_months = set(_locked_months(ledger, set(months)))
        for month in sorted(months):
            batch, out = months[month], {}

            def write(at, batch=batch, out=out):
                out.update(write_ps_items(batch, customer_id, at, digest, key, runner, AUTO_ACTOR)[1])
                return out["version"] if out.get("complete") else \
                    runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["version"]
            try:
                version = in_month(runner, customer_id, version, ledger, month, key, write)
            except ApiError as exc:
                self._error("tách phụ phí", customer_id, exc)
                break
            total += out.get("written", 0)
            with self.lock:
                for row in batch[:out.get("written", 0)]:
                    self.auto_log.appendleft({"at": self.clock(), "kind": "ps", "customer_id": customer_id,
                                              "container": row.get("container"), "date": row.get("date"), "month": month,
                                              "locked": month in locked_months})
            if not out.get("complete"):
                self._error("tách phụ phí", customer_id, out.get("error") or "INCOMPLETE")
                break
        if total:
            self._auto_columns(runner, customer_id)

    def auto_today(self) -> list[dict[str, Any]]:
        """Việc máy đã ghi hôm nay qua hộp chờ, mới trước, cho tab Máy chạy (MAY-CHAY-01). Chỉ đọc trong RAM, không chạm DB. Giờ theo VN."""
        today = _vn_day(self.clock())
        with self.lock:
            rows = [entry for entry in self.auto_log if _vn_day(entry["at"]) == today]
        return [{**entry, "at": datetime.fromtimestamp(entry["at"] + 7 * 3600, UTC).strftime("%Y-%m-%dT%H:%M:%S+07:00")} for entry in rows]

    def _auto_columns(self, runner, customer_id: int) -> None:
        """Đưa các loại nhiều tiền nhất của sổ lên cột riêng; không đổi tiền, không vướng khóa tháng (MAY-PS-01)."""
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            columns = best_columns(ledger, runner.run("get_fee_types", {}, AUTO_ACTOR).get("fee_types", []))
            if columns is None:
                return
            digest = hashlib.sha256(f"{AUTO_ACTOR}:cot:{customer_id}:{ledger['version']}:{columns}".encode()).hexdigest()
            runner.run("set_book_fee_columns", {"customer_id": customer_id, "expected_version": ledger["version"],
                                                "idempotency_key": digest, "fee_type_ids": columns}, AUTO_ACTOR)
        except ApiError as exc:
            self._error("chọn cột phụ phí", customer_id, exc)

    def start(self, runner) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.dirty.clear()   # lượt đầy đủ tính lại cả các sổ vừa ghi
        threading.Thread(target=self.refresh_all, args=(runner,), daemon=True, name="hop-viec").start()
        return True

    def mark_dirty(self, *customer_ids: Any) -> None:
        with self.lock:
            self.dirty.update(c for c in customer_ids if type(c) is int and c > 0)

    def tick(self, runner) -> bool:
        """Khởi động lượt nền khi bản chụp Sheet đã đổi và đã yên. Nhịp nền của API gọi mỗi phút, để máy (P3a, P3b)
        chạy theo từng đợt Sheet mà không cần ai mở Việc cần làm."""
        key = self._key()
        with self.lock:
            stale = self.computed_at is None or key != self.key
        return stale and (self.computed_at is None or self._settled(key)) and self.start(runner)

    def keep_fresh(self, runner, every: float = TICK_SECONDS) -> None:
        """Luồng nền chạy suốt đời API: `tick` mỗi `every` giây; lỗi một nhịp không dừng luồng."""
        def loop():
            while not self.stopped.wait(every):
                with contextlib.suppress(Exception):   # nhịp sau thử lại
                    self.tick(runner)
        threading.Thread(target=loop, daemon=True, name="hop-viec-nhip").start()

    def view(self, runner) -> dict:
        """Trả kết quả cho GET; tự khởi động lượt nền khi cần và tính lại ngay vài sổ vừa ghi."""
        key = self._key()
        with self.lock:
            dirty = sorted(self.dirty) if not self.running else []
        if not self.tick(runner) and dirty:
            if len(dirty) > DIRTY_INLINE_LIMIT:
                self.start(runner)
            else:
                # HIEU-NANG-01: các sổ vừa ghi tính song song (đo 13/11/2026: 5 sổ lần lượt 3,6 giây); hai GET cùng lúc
                # (trang và menu) không tính trùng: lượt sau chờ lượt trước rồi chỉ tính sổ còn bẩn.
                with self.dirty_lock:
                    with self.lock:
                        dirty = sorted(self.dirty) if not self.running else []
                    if dirty:
                        shared = SharedReads(runner)
                        with ThreadPoolExecutor(max_workers=len(dirty)) as pool:
                            results = list(pool.map(lambda customer_id: self._one(shared, customer_id), dirty))
                        with self.lock:
                            for result in results:
                                self._apply(*result)
                            self.dirty.difference_update(dirty)
        with self.lock:
            if key is None and self.computed_at is None:
                state = "unavailable"
            elif self.computed_at is None:
                state = "computing"
            else:
                state = "unavailable" if self.unavailable else "ready"
            iso = lambda t: None if t is None else datetime.fromtimestamp(t, UTC).isoformat()  # noqa: E731
            today = _vn_day(self.clock())
            done_today = [entry for entry in self.auto_log if _vn_day(entry["at"]) == today]
            text_done = [entry for entry in done_today if "kind" not in entry]
            trip_done = [entry for entry in done_today if entry.get("kind") == "trip"]
            price_done = [entry for entry in done_today if entry.get("kind") == "price"]
            ps_done = [entry for entry in done_today if entry.get("kind") == "ps"]
            auto = {"text_enabled": auto_enabled("text"), "trips_enabled": auto_enabled("trips"),
                    "prices_enabled": auto_enabled("prices"), "ps_enabled": auto_enabled("ps"),
                    "last_run": iso(self.auto_run_at), "errors": self.auto_errors,
                    "today_count": len(text_done), "today_books": len({entry["customer_id"] for entry in text_done}),
                    "today_trips": len(trip_done), "today_trip_books": len({entry["customer_id"] for entry in trip_done}),
                    "today_trips_pending": sum(1 for entry in trip_done if entry.get("pending")),
                    "today_prices": len(price_done), "today_price_books": len({entry["customer_id"] for entry in price_done}),
                    "today_ps": len(ps_done), "today_ps_books": len({entry["customer_id"] for entry in ps_done}),
                    "items": [{**entry, "at": iso(entry["at"])} for entry in text_done[:100]],
                    "trip_items": [{**entry, "at": iso(entry["at"])} for entry in trip_done[:100]],
                    "price_items": [{**entry, "at": iso(entry["at"])} for entry in price_done[:100]],
                    "ps_items": [{**entry, "at": iso(entry["at"])} for entry in ps_done[:100]]}
            # Sổ đã khớp Sheet ở lượt đối soát gần nhất và tổng chưa đổi từ đó: việc còn treo của sổ không làm số đúng hơn. Riêng giá
            # khác giá Sheet vẫn hiện: tổng khớp mà giá từng chuyến lệch là hai chỗ bù trừ nhau, phép khớp tổng không thấy.
            reconcile = reconcile_result()
            matched = (reconcile or {}).get("matched") or {}
            return {"state": state, "computed_at": iso(self.computed_at), "auto": auto,
                    "sheet_at": self.sheet_status().get("sheet_at"), "refreshing": self.running,
                    "books_total": self.total, "books_done": self.done, "failed": sorted(self.failed),
                    "reconcile": None if reconcile is None else {**{k: v for k, v in reconcile.items() if k != "matched"},
                                                                  "matched_ids": sorted(int(key) for key in matched)},
                    "books": [{**book, "sheet_matched": matched.get(str(book["customer_id"])) == book.get("outstanding_vnd")
                               and not book.get("prices_conflict")}
                              for book in sorted(self.books.values(), key=lambda b: b["customer_id"])]}
