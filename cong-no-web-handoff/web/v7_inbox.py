"""Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): việc của hàng chờ Sheet ở mọi sổ, chỉ đọc.

Mỗi sổ chiếu bằng đúng `ledger_projections` như khi mở sổ (khoảng 0,75 giây/sổ trên `hao`), nên API tính nền và giữ kết
quả trong bộ nhớ: lúc khởi động, khi bản chụp Sheet đổi, và từng sổ ngay sau một lệnh ghi lên sổ đó. Không gọi hàm ghi.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from v7_api_sheet import (  # hàm đọc dùng chung chỉ chạy một lần mỗi lượt
    SharedReads,
    paste_sheet_rows,
    sheet_projection,
)
from v7_api_validate import ApiError

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
AUTO_LOG = 300   # số việc máy vừa làm giữ trong RAM để hiện "Máy đã tự làm"
# P3b (HANG-CHO-01 Q2 theo Q5 A, specs/v7-hop-ngoai-le-p3b.md): máy bấm thay "Duyệt" cho chuyến mới khớp đúng sổ theo
# mặt hàng, tháng mở, ngày không sau hôm nay. Bật bằng WEBDEBIT_AUTO_SHEET=trips (gộp được: "text,trips").
# MAY-KHOA-01 (3/11/2026): khóa tháng chỉ chặn người. Máy mở tháng khóa, ghi, khóa lại ngay (ba lệnh có sẵn, đều vào
# Lịch sử) để điền ngày cho dòng sổ gốc không ngày ở mọi tháng, và đưa chuyến mới vào tháng khóa từ tháng này trở đi
# (trước đó sổ gốc là chuẩn).
AUTO_LOCKED_TRIPS_FROM = "2026-10"


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
        "trips_check": {"count": sum(check_reasons.values()), "reasons": check_reasons},
        "text_diff": text_diff,
        "prices": {"ready": len(prices.get("ready") or []), "review": len(prices.get("review") or [])},
        "ps": {"ready": len(ps.get("ready") or []), "review": len(ps.get("review") or [])},
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
            return customer_id, summarize(customer_id, self.project(runner, ledger, ACTOR)), True
        except Exception:  # noqa: BLE001  một sổ lỗi không chặn sổ khác; sổ đó vào `failed`
            return customer_id, None, False

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
        text, trips = auto_enabled("text"), auto_enabled("trips")
        todo = sorted(cid for cid, book in books.items() if (text and book["text_diff"]) or (trips and book["trips_new"]))
        if todo and key is not None:
            for customer_id in todo:
                if text and books[customer_id]["text_diff"]:
                    self._auto_text(shared, customer_id)
                if trips and books[customer_id]["trips_new"]:
                    # Đọc lại chuyến web mọi sổ cho từng sổ: chuyến máy vừa thêm ở sổ trước phải chặn được ở sổ sau.
                    self._auto_trips(SharedReads(shared.runner), customer_id)
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
        `edit_legacy_trip`, tháng khóa thì máy mở rồi khóa lại); lệch ngày khác, container, booking, khách khác để người quyết.
        Mỗi ô một khóa chống ghi trùng cố định theo (bản chụp, dòng Sheet, đích, ô, giá trị Sheet). Lỗi ở một sổ dừng sổ đó,
        lượt sau thử lại.
        """
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            projection = sheet_projection(runner, ledger, AUTO_ACTOR)
        except (ApiError, ValueError):
            self.auto_errors += 1
            return
        version, digest = ledger.get("version"), projection.get("snapshot_sha256")
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
                except ApiError:
                    self.auto_errors += 1
                    return
                version = result.get("version", version)
                with self.lock:
                    self.auto_log.appendleft({"at": self.clock(), "customer_id": customer_id, "container": item.get("container"),
                                              "field": field, "before": target_value, "after": sheet_value.strip()})
            if fill:
                day = str(item["event_date"])[:10]
                key = f"auto:{digest}:{item.get('source_row')}:legacy:{item.get('existing_id')}:event_date:{day}"

                def edit(at, item=item, day=day, key=key):
                    return runner.run("edit_legacy_trip", {
                        "customer_id": customer_id, "expected_version": at,
                        "idempotency_key": hashlib.sha256(key.encode()).hexdigest(), "legacy_row_id": item.get("existing_id"),
                        "field": "event_date", "value": day}, AUTO_ACTOR).get("version", at)
                try:
                    version = self._in_month(runner, customer_id, version, ledger, day[:7], key, edit)
                except ApiError:
                    self.auto_errors += 1
                    return
                with self.lock:
                    self.auto_log.appendleft({"at": self.clock(), "customer_id": customer_id, "container": item.get("container"),
                                              "field": "event_date", "before": None, "after": day})

    def _in_month(self, runner, customer_id: int, version: int, ledger: dict[str, Any], month: str, key: str,
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

    def _auto_trips(self, runner, customer_id: int) -> None:
        """Dán chuyến mới đủ điều kiện Q2 của một sổ bằng đúng đường của nút "Duyệt" (`paste_sheet_rows`), chưa có giá.

        Chỉ dòng "chuyến mới" khớp sổ theo mặt hàng (`COMMODITY_OK`), ngày không sau hôm nay (giờ VN), tháng nợ đang mở
        hoặc khóa nhưng từ AUTO_LOCKED_TRIPS_FROM (máy mở, dán, khóa lại; MAY-KHOA-01).
        `paste_trips` vẫn tự đẩy chuyến nghi trùng sang "chờ kiểm". Lỗi ở một sổ dừng sổ đó, lượt sau thử lại.
        """
        try:
            ledger = runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)
            projection = sheet_projection(runner, ledger, AUTO_ACTOR)
        except (ApiError, ValueError):
            self.auto_errors += 1
            return
        today = _vn_day(self.clock())
        rows = [item for item in projection.get("items") or []
                if item.get("sync_state") == "NEW" and item.get("book_match") == "COMMODITY_OK"
                and str(item.get("event_date") or "") <= today]
        locked = set(_locked_months(ledger, {str(item["event_date"])[:7] for item in rows}))
        rows = [item for item in rows if str(item["event_date"])[:7] not in locked
                or str(item["event_date"])[:7] >= AUTO_LOCKED_TRIPS_FROM]
        if not rows:
            return
        digest = projection.get("snapshot_sha256")
        months: dict[str, list[dict[str, Any]]] = {}
        for item in rows:
            months.setdefault(str(item["event_date"])[:7], []).append(item)
        version = ledger.get("version")
        for month in sorted(months):
            batch, out = months[month], {}

            def paste(at, batch=batch, out=out):
                out.update(paste_sheet_rows(runner, customer_id, at, digest, f"{AUTO_ACTOR}:trips:{customer_id}", batch,
                                            AUTO_ACTOR))
                return runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["version"]
            try:
                version = self._in_month(runner, customer_id, version, ledger, month, f"{AUTO_ACTOR}:trips:{customer_id}",
                                         paste)
            except ApiError:
                self.auto_errors += 1
                return
            pending = {entry.get("trip_id") for entry in out.get("pending_review") or []}
            by_row = {item["source_row"]: item for item in batch}
            with self.lock:
                for entry in out.get("pasted") or []:
                    item = by_row.get(entry["source_row"], {})
                    self.auto_log.appendleft({"at": self.clock(), "kind": "trip", "customer_id": customer_id,
                                              "container": item.get("container"), "event_date": item.get("event_date"),
                                              "trip_id": entry["trip_id"], "pending": entry["trip_id"] in pending})
            if not out.get("complete"):
                self.auto_errors += 1
                return

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
                shared = SharedReads(runner)
                results = [self._one(shared, customer_id) for customer_id in dirty]
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
            text_done = [entry for entry in done_today if entry.get("kind") != "trip"]
            trip_done = [entry for entry in done_today if entry.get("kind") == "trip"]
            auto = {"text_enabled": auto_enabled("text"), "trips_enabled": auto_enabled("trips"),
                    "last_run": iso(self.auto_run_at), "errors": self.auto_errors,
                    "today_count": len(text_done), "today_books": len({entry["customer_id"] for entry in text_done}),
                    "today_trips": len(trip_done), "today_trip_books": len({entry["customer_id"] for entry in trip_done}),
                    "today_trips_pending": sum(1 for entry in trip_done if entry.get("pending")),
                    "items": [{**entry, "at": iso(entry["at"])} for entry in text_done[:100]],
                    "trip_items": [{**entry, "at": iso(entry["at"])} for entry in trip_done[:100]]}
            return {"state": state, "computed_at": iso(self.computed_at), "auto": auto,
                    "sheet_at": self.sheet_status().get("sheet_at"), "refreshing": self.running,
                    "books_total": self.total, "books_done": self.done, "failed": sorted(self.failed),
                    "books": sorted(self.books.values(), key=lambda b: b["customer_id"])}
