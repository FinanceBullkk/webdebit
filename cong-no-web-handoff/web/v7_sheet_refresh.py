"""Manual "Làm mới" Sheet refresh (specs/v7-sheet-refresh.md).

The API never runs the Sheet runners itself. A POST writes one signal file; on `hao` a systemd
path unit sees it and starts the two existing read-only runners. State is read from file times
only: the signal file and the two snapshot files the runners replace atomically on every run.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

RUNNING_LIMIT_SECONDS = 180   # quá 3 phút chưa có bản chụp mới thì báo chưa lấy được
RECENT_SECONDS = 60           # bản chụp mới hơn 1 phút thì không đọc lại


def _mtime(path: str | os.PathLike[str]) -> float | None:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def _iso(seconds: float | None) -> str | None:
    return None if seconds is None else datetime.fromtimestamp(seconds, UTC).isoformat()


def status(signal_path: str | None, snapshot_paths: tuple[str, ...], now: float) -> dict:
    """Return {state, sheet_at, requested_at, recent} for the refresh button."""
    if not signal_path:
        return {"state": "unavailable", "sheet_at": None, "requested_at": None, "recent": False}
    times = [_mtime(path) for path in snapshot_paths]
    # Giờ của bản đang dùng là bản cũ hơn trong hai file: chuyến và giá phải cùng mới.
    sheet_at = None if any(value is None for value in times) else min(times)
    requested_at = _mtime(signal_path)
    if requested_at is not None and (sheet_at is None or requested_at > sheet_at):
        state = "running" if now - requested_at <= RUNNING_LIMIT_SECONDS else "failed"
    else:
        state = "idle"
    recent = state == "idle" and sheet_at is not None and now - sheet_at < RECENT_SECONDS
    return {"state": state, "sheet_at": _iso(sheet_at), "requested_at": _iso(requested_at), "recent": recent}


def request(signal_path: str | None, snapshot_paths: tuple[str, ...], actor: str, now: float) -> dict:
    """Write the signal unless a run is pending or the snapshot is fresh; return the new status."""
    current = status(signal_path, snapshot_paths, now)
    if current["state"] in ("unavailable", "running") or current["recent"]:
        return current
    # Ghi thẳng (không đổi tên file) để unit .path thấy sự kiện đóng file sau khi ghi.
    with open(signal_path, "w", encoding="utf-8") as stream:
        json.dump({"requested_at": _iso(now), "actor": actor}, stream, ensure_ascii=False)
        stream.write("\n")
    return status(signal_path, snapshot_paths, now)
