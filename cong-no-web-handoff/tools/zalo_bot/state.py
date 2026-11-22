"""File của bộ não trên hao: nhịp tim `status.json`, nhớ chống trùng, nhật ký hỏi đáp theo tháng.

- `status.json` (0644): chỉ mã, số đếm và giờ; tab Máy chạy và máy canh đọc (`web/v7_machine.py`, `zalo_bot()`).
- `brain-state.json` (0600): mã tin đã thấy và người đã được chào.
- `log/<YYYY-MM>.jsonl` (0640): mỗi lượt hỏi một dòng, có câu hỏi; giữ 90 ngày (Q6), không vào repo.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import Memory

VN = ZoneInfo("Asia/Ho_Chi_Minh")
SCHEMA = 1
LOG_KEEP_DAYS = 90


def now_iso(now: float) -> str:
    return dt.datetime.fromtimestamp(now, VN).isoformat(timespec="seconds")


def write_atomic(path: Path, data: bytes, mode: int) -> None:
    """Ghi file tạm cùng thư mục với đúng quyền ngay từ lúc tạo, rồi thay file cũ một lần."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
    finally:
        os.close(fd)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


class Counters:
    """Bộ đếm trong ngày theo giờ Việt Nam; sang ngày mới thì về 0."""

    def __init__(self) -> None:
        self.day: str | None = None
        self.values: dict[str, int] = {}

    def add(self, name: str, now: float) -> None:
        day = dt.datetime.fromtimestamp(now, VN).date().isoformat()
        if day != self.day:
            self.day, self.values = day, {}
        self.values[name] = self.values.get(name, 0) + 1

    def snapshot(self, now: float) -> dict[str, int]:
        day = dt.datetime.fromtimestamp(now, VN).date().isoformat()
        return dict(sorted(self.values.items())) if day == self.day else {}


@dataclass
class KenhView:
    """Kênh nhìn từ bộ não: trạng thái kênh tự báo, cộng "offline" khi socket đứt."""

    since: float
    state: str = "offline"
    code: str | None = None
    version: str | None = None
    connected: bool = False
    last_event_at: float | None = None

    def set(self, state: str, code: str | None, now: float) -> None:
        if (state, code) != (self.state, self.code):
            self.state, self.code, self.since = state, code, now

    def seen(self, now: float) -> None:
        self.last_event_at = now

    def attach(self, now: float) -> None:
        self.connected = True
        self.set("connecting", None, now)

    def detach(self, now: float) -> None:
        self.connected = False
        self.version = None
        self.set("offline", None, now)


def status(*, now: float, version: str, enabled: bool, users: int, kenh: KenhView, counters: Counters, error: str | None,
           tool_check: dict | None = None) -> dict:
    """`tool_check`: lượt tự kiểm công cụ gần nhất, `{"at": giờ, "failed": ["công_cụ:mã_lỗi", …]}`; chưa chạy thì None."""
    return {"schema": SCHEMA, "at": now_iso(now), "version": version, "enabled": enabled, "users": users,
            "kenh": {"state": kenh.state, "code": kenh.code, "since": now_iso(kenh.since), "version": kenh.version,
                     "last_event_at": now_iso(kenh.last_event_at) if kenh.last_event_at is not None else None},
            "counts": counters.snapshot(now), "error": error, "tool_check": tool_check}


def write_status(path: Path, data: dict) -> None:
    write_atomic(path, json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8"), 0o644)


def load_memory(path: Path) -> Memory:
    try:
        return Memory.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return Memory()


def save_memory(path: Path, memory: Memory) -> None:
    write_atomic(path, json.dumps(memory.to_json(), sort_keys=True).encode("utf-8"), 0o600)


class LogBook:
    """Nhật ký hỏi đáp theo tháng giờ Việt Nam; chỉ bộ não đọc được (0640, thư mục 0750)."""

    def __init__(self, directory: Path):
        self.directory = directory

    def write(self, record: dict, now: float) -> None:
        self.directory.mkdir(mode=0o750, parents=True, exist_ok=True)
        month = dt.datetime.fromtimestamp(now, VN).strftime("%Y-%m")
        line = json.dumps({"at": now_iso(now), **record}, ensure_ascii=False, sort_keys=True) + "\n"
        fd = os.open(self.directory / f"{month}.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)

    def prune(self, now: float) -> list[str]:
        """Xóa file tháng đã hết hạn giữ: ngày cuối tháng cách hôm nay quá 90 ngày. Trả tên file đã xóa."""
        today = dt.datetime.fromtimestamp(now, VN).date()
        removed = []
        for path in sorted(self.directory.glob("????-??.jsonl")):
            try:
                year, month = int(path.stem[:4]), int(path.stem[5:])
            except ValueError:
                continue
            if not 1 <= month <= 12:
                continue
            first_next = dt.date(year + month // 12, month % 12 + 1, 1)
            if (today - (first_next - dt.timedelta(days=1))).days > LOG_KEEP_DAYS:
                path.unlink(missing_ok=True)
                removed.append(path.name)
        return removed
