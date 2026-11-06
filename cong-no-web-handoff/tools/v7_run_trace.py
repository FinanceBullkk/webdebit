"""Tín hiệu từng bước của lượt đối soát cho tab Máy chạy (MAY-CHAY-01). Chỉ để xem: mọi lỗi ở đây đều bị nuốt, không bao giờ làm hỏng lượt ghi tiền.

Ghi `reconcile-run.json` (lượt đang chạy hoặc vừa xong) và thêm một dòng vào `reconcile-run-history.jsonl` khi xong, cùng thư mục với
reconcile.json, mode 600. Khách chỉ có customer_id, không có tên. Tiền là chuỗi số nguyên chính xác.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

STAGES = ("tai", "sach", "doc", "so", "chot", "tim", "ghi", "luu")
TICK_SECONDS = 3.0    # đếm khách không ghi file nhiều hơn mức này
KEEP_RUNS, PRUNE_AT = 500, 600
VN = ZoneInfo("Asia/Ho_Chi_Minh")


def _safe(method: Callable[..., None]) -> Callable[..., None]:
    @functools.wraps(method)
    def wrapper(self: RunTrace, *args: Any, **kwargs: Any) -> None:
        try:
            method(self, *args, **kwargs)
        except Exception:  # noqa: BLE001  tín hiệu lỗi thì mất tín hiệu, không được đụng tới lượt đang ghi tiền
            self.broken = True
    return wrapper


def _now() -> str:
    return dt.datetime.now(VN).isoformat(timespec="seconds")


class RunTrace:
    """`path` None thì không ghi gì (test và công cụ gọi trực tiếp)."""

    def __init__(self, path: Path | None, mode: str = "report") -> None:
        self.path, self.broken, self._last_tick = path, False, 0.0
        self.data: dict[str, Any] = {"version": 1, "state": "running", "mode": mode, "started_at": _now(), "finished_at": None, "stage": None,
                                     "done": None, "total": None, "segments": [], "customers": {}, "unlinked": {}, "too_many": False}
        self._begin()

    @_safe
    def _begin(self) -> None:
        self._write()

    @_safe
    def stage(self, name: str, total: int | None = None, done: int = 0) -> None:
        if name not in STAGES:
            raise ValueError(name)
        if self.data["stage"] != name:   # quay lại đúng trạm đang chạy chỉ đổi số đếm, không mở đoạn mới
            self.data["segments"].append({"stage": name, "at": _now()})
        self.data.update(stage=name, done=done if total is not None else None, total=total)
        self._write()

    @_safe
    def tick(self, done: int) -> None:
        self.data["done"] = done
        if time.monotonic() - self._last_tick >= TICK_SECONDS:
            self._write()

    @_safe
    def customer(self, customer_id: int | None, *, decided: bool = False, done: bool = False, **fields: Any) -> None:
        """Một khách cần xét. Khách chưa có sổ thì không có id: chỉ đếm theo lý do."""
        if customer_id is None:
            reason = str(fields.get("reason"))
            self.data["unlinked"][reason] = self.data["unlinked"].get(reason, 0) + 1
            return
        row = self.data["customers"].setdefault(str(customer_id), {"customer_id": customer_id})
        if decided:
            row.setdefault("decided_at", _now())
        if done:
            row.setdefault("done_at", _now())
        row.update({key: (str(value) if key.endswith("_vnd") and value is not None else value) for key, value in fields.items()})
        self._write()

    @_safe
    def mark(self, **fields: Any) -> None:
        self.data.update(fields)
        self._write()

    @_safe
    def finish(self, *, ok: bool, reason: str | None = None, counts: dict[str, int] | None = None, books: int | None = None, fixed: int | None = None, created: int | None = None) -> None:
        self.data.update(state="done" if ok else "failed", finished_at=_now(), stage=None, done=None, total=None, reason=reason, counts=counts, books=books, fixed=fixed, created=created)
        # Khách đang xét dở mà chưa có kết luận (ví dụ người khác vừa sửa nên hết lệch) không phải một kết quả của lượt.
        self.data["customers"] = {key: row for key, row in self.data["customers"].items() if row.get("reason")}
        self._write()
        self._append_history()

    def _write(self) -> None:
        if self.path is None:
            return
        self._last_tick = time.monotonic()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=self.path.parent, prefix=".reconcile-run-", suffix=".tmp")   # mkstemp đã là mode 600
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(self.data, stream, ensure_ascii=False)
            os.replace(name, self.path)
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise

    def _append_history(self) -> None:
        if self.path is None:
            return
        history = self.path.with_name("reconcile-run-history.jsonl")
        descriptor = os.open(history, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(self.data, ensure_ascii=False) + "\n")
        lines = history.read_text(encoding="utf-8").splitlines()
        if len(lines) > PRUNE_AT:
            descriptor, name = tempfile.mkstemp(dir=history.parent, prefix=".reconcile-run-", suffix=".tmp")
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write("\n".join(lines[-KEEP_RUNS:]) + "\n")
            os.replace(name, history)
