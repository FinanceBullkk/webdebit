"""ZALO-AGENT-01 Phần 6: `status.json`, nhịp tim của agent (hợp đồng dữ liệu trong specs/zalo-agent.md).

Chỉ có mã và số đếm, không chữ tự do. Ghi tại `<state>/status.json` rồi đẩy tới `hao:/srv/v7/zalo-agent/status.json`
qua kênh chung. `hao` coi thiếu file, đọc lỗi hoặc `schema` khác 1 là "không nghe máy Zalo".
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from . import push as pusher
from .cursor import now_iso
from .source import read_json, retry_io

SCHEMA = 1
FILE = "status.json"
CODE = re.compile(r"[a-z_]{1,40}")


def code(error: object) -> str | None:
    """Mã lỗi ngắn `[a-z_]{1,40}` hoặc None; mọi thứ khác (kể cả chữ tự do) thành `unexpected`."""
    if error is None:
        return None
    return error if isinstance(error, str) and CODE.fullmatch(error) else "unexpected"


def agent_version(repo: Path) -> str:
    try:
        done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"], capture_output=True, timeout=10,
                              check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        text = done.stdout.decode("ascii", "replace").strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return text if done.returncode == 0 and re.fullmatch(r"[0-9a-f]{7,40}", text) else "unknown"


def track_identity(state: Path, identity: str, now: float, persist: bool = True) -> str:
    """Lúc `identity` đổi sang giá trị hiện tại. Nhớ trong `<state>/identity.json` để chạy lại agent không mất mốc
    (`persist=False` cho `--dry-run`: tính mà không ghi)."""
    path = Path(state) / "identity.json"
    saved = read_json(path)
    if isinstance(saved, dict) and saved.get("identity") == identity and isinstance(saved.get("since"), str):
        return saved["since"]
    if not persist:
        return now_iso(now)
    Path(state).mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps({"identity": identity, "since": now_iso(now)}), encoding="utf-8")
    retry_io(lambda: os.replace(tmp, path))
    return now_iso(now)


def error_since(before: dict | None, error: str | None, now: float) -> str | None:
    """Lúc `error` chuyển từ null sang có lỗi: giữ mốc cũ khi vẫn lỗi (kể cả đổi sang mã khác), null khi hết lỗi.
    Mốc nằm trong status.json lượt trước, file này ở `<state>` nên chạy lại agent không mất."""
    if error is None:
        return None
    kept = (before or {}).get("error_since")
    return kept if (before or {}).get("error") is not None and isinstance(kept, str) else now_iso(now)


def compose(previous: dict | None, now: float, version: str, selected: int, live, results: dict[str, dict],
            push_ok_at: str | None, push_error: str | None, identity: tuple[str, str]) -> dict:
    """`live`: LiveSync. `results`: kết quả `step()` từng bộ xử lý. `identity`: (giá trị, lúc đổi sang giá trị đó).
    `last_ok_at` giữ giá trị lượt trước khi lượt này lỗi; `error_since` xem `error_since()`."""
    before = (previous or {}).get("processors", {}) if isinstance((previous or {}).get("processors"), dict) else {}
    revision = live.revision()
    processors = {}
    for name, result in sorted(results.items()):
        have = result.get("revision")
        error = code(result.get("error"))
        processors[name] = {
            "revision": have,
            "lag_revisions": max(0, revision - have) if isinstance(revision, int) and isinstance(have, int) else None,
            "last_ok_at": now_iso(now) if error is None else (before.get(name) or {}).get("last_ok_at"),
            "error": error,
            "error_since": error_since(before.get(name), error, now),
            **({"messages": result["messages"]} if isinstance(result.get("messages"), int) and not isinstance(result["messages"], bool) else {})}
    push_failure = code(push_error)   # chỉ đường đẩy nhịp tim (chính file này); lỗi đẩy từng bộ xử lý nằm ở processors.<tên>.error
    return {"schema": SCHEMA, "at": now_iso(now), "agent_version": version, "selected_groups": selected,
            "live_sync": {"revision": revision, "revision_at": live.revision_at(), "identity": identity[0], "identity_since": identity[1]},
            "processors": processors,
            "push": {"last_ok_at": push_ok_at or ((previous or {}).get("push") or {}).get("last_ok_at"), "error": push_failure,
                     "error_since": error_since((previous or {}).get("push"), push_failure, now)}}


def write(state: Path, status: dict, persist: bool = True) -> bytes:
    data = json.dumps(status, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if not persist:   # `--dry-run`: không đụng `status.json` thật (mốc `error_since` của lượt thật không được lẫn lượt thử)
        return data
    Path(state).mkdir(parents=True, exist_ok=True)
    path = Path(state) / FILE
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    retry_io(lambda: os.replace(tmp, path))
    return data


def load(state: Path) -> dict | None:
    value = read_json(Path(state) / FILE)
    return value if isinstance(value, dict) else None


def push_status(target: str, data: bytes, run=pusher.ssh_run) -> None:
    """Thư mục đích chỉ có file chốt: luôn gửi, `mv` nguyên tử."""
    pusher.push(pusher.Plan(target, (), pusher.Item(FILE, data)), run=run)
