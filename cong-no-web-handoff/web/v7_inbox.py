"""Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): việc của hàng chờ Sheet ở mọi sổ, chỉ đọc.

Mỗi sổ chiếu bằng đúng `ledger_projections` như khi mở sổ (khoảng 0,75 giây/sổ trên `hao`), nên API tính nền và giữ kết
quả trong bộ nhớ: lúc khởi động, khi bản chụp Sheet đổi, và từng sổ ngay sau một lệnh ghi lên sổ đó. Không gọi hàm ghi.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from v7_api_sheet import SharedReads  # hàm đọc dùng chung chỉ chạy một lần mỗi lượt

ACTOR = "hop-viec"   # đọc nền, không phải người; hàm đọc chỉ cần sokhach.actor khác rỗng
WORKERS = 2   # đo trên `hao` 1/11/2026: 4 luồng làm mở sổ lúc đang tính chậm 1,36 s, 2 luồng 0,84 s (hộp 34 → 39 s)
DIRTY_INLINE_LIMIT = 5   # quá số này thì tính lại nền, không giữ GET chờ
# Ba runner (chuyến, giá, PS) ghi bản chụp cách nhau vài chục giây mỗi 15 phút; chờ file mới nhất cũ hơn chừng này
# mới tính lại, để mỗi đợt Sheet chỉ một lượt thay vì ba (đo trên `hao` 1/11/2026).
SETTLE_SECONDS = 90
TEXT_FIELDS = {"origin", "destination", "shipper", "carrier", "shipper_unavailable"}


def _vnd(value: Any) -> int | None:
    text = str(value) if value is not None else ""
    return int(text) if text.lstrip("-").isdigit() else None


def summarize(customer_id: int, ledger: dict[str, Any]) -> dict[str, Any] | None:
    """Gom kết quả chiếu của một sổ thành bảy nhóm; None khi sổ không có việc."""
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
            if reason == "DIFFERENT_FIELDS" and fields and fields <= TEXT_FIELDS:
                text_diff += 1
            else:
                key = "FIELDS" if reason == "DIFFERENT_FIELDS" else reason
                check_reasons[key] = check_reasons.get(key, 0) + 1
    book = {
        "customer_id": customer_id,
        "receipts": {"ready": len(receipts.get("ready") or []), "review": len(receipts.get("review") or []),
                     "amount_vnd": str(sum(a for a in receipt_amounts if a is not None))},
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
        with self.lock:
            self.books, self.failed = books, failed
            self.computed_at, self.key, self.running = self.clock(), key, False
            self.unavailable = key is None

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

    def view(self, runner) -> dict:
        """Trả kết quả cho GET; tự khởi động lượt nền khi cần và tính lại ngay vài sổ vừa ghi."""
        key = self._key()
        with self.lock:
            stale = self.computed_at is None or key != self.key
            dirty = sorted(self.dirty) if not self.running else []
        if stale and (self.computed_at is None or self._settled(key)):
            self.start(runner)
        elif dirty:
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
            return {"state": state, "computed_at": iso(self.computed_at),
                    "sheet_at": self.sheet_status().get("sheet_at"), "refreshing": self.running,
                    "books_total": self.total, "books_done": self.done, "failed": sorted(self.failed),
                    "books": sorted(self.books.values(), key=lambda b: b["customer_id"])}
