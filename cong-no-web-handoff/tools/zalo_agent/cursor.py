"""ZALO-AGENT-01 Phần 1: con trỏ của một bộ xử lý, ở `<state>/<tên>.json`.

    {"revision": 1129, "baseline_sha256": "…", "updated_at": "…", ...trường riêng của bộ xử lý..., "pending": {...}}

Con trỏ chỉ tiến sau khi đẩy lên `hao` thành công (giao ít nhất một lần). `pending` giữ trạng thái đã chuẩn bị cục bộ
nhưng chưa đẩy xong: chết giữa lượt thì lượt sau đẩy lại đúng `pending` đó chứ không tính lại, nên file đã gửi không bao
giờ bị viết lại khác đi.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .source import VN, Rebuild, read_json, retry_io

NAME = re.compile(r"[a-z_]{1,30}")
MAX_GAP = 500          # lệch quá số revision này thì dựng lại còn rẻ hơn đọc từng changes-N
NIGHTLY_HOUR = 3       # mỗi đêm một lần: lượt dựng đầy đủ đầu tiên từ 03:00 giờ VN


def now_iso(now: float) -> str:
    return datetime.fromtimestamp(now, VN).isoformat(timespec="seconds")


def load(state: Path, name: str) -> dict | None:
    assert NAME.fullmatch(name)
    cursor = read_json(Path(state) / f"{name}.json")
    ok = isinstance(cursor, dict) and (isinstance(cursor.get("revision"), int) or isinstance(cursor.get("pending"), dict))
    return cursor if ok else None   # lần đầu có thể mới có `pending`, chưa có `revision`


def save(state: Path, name: str, cursor: dict, now: float) -> None:
    assert NAME.fullmatch(name)
    Path(state).mkdir(parents=True, exist_ok=True)
    path = Path(state) / f"{name}.json"
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps({**cursor, "updated_at": now_iso(now)}, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    retry_io(lambda: os.replace(tmp, path))


def selection_sha256(selection: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(selection)).encode()).hexdigest()


def rebuild_reason(cursor: dict | None, revision: int, baseline: str | None, selection: list[str], now: float) -> str | None:
    """Mã lý do phải dựng lại từ đầu, hoặc None khi đọc tiếp theo changes-N được (quy tắc 3 của Phần 1)."""
    if cursor is None:
        return "first_run"
    if revision < cursor["revision"]:
        return "revision_back"
    if baseline != cursor.get("baseline_sha256"):
        return "baseline_changed"
    if selection_sha256(selection) != cursor.get("selection_sha256"):
        return "selection_changed"
    if revision - cursor["revision"] > MAX_GAP:
        return "gap_too_large"
    built, current = cursor.get("built_at"), datetime.fromtimestamp(now, VN)
    if isinstance(built, str) and current.hour >= NIGHTLY_HOUR and datetime.fromisoformat(built).date() < current.date():
        return "nightly"
    return None


def decide(cursor: dict | None, revision: int, baseline: str | None, selection: list[str], now: float, live) -> tuple[str | None, set[str]]:
    """(lý do dựng lại hoặc None, các message_id cần xử lý). Thiếu changes-N ở giữa cũng là lý do dựng lại."""
    reason = rebuild_reason(cursor, revision, baseline, selection, now)
    if reason:
        return reason, set()
    try:
        return None, live.changed_ids(cursor["revision"], revision)
    except Rebuild as gap:
        return gap.reason, set()
