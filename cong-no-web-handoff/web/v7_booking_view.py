"""Kết quả kiểm Sheet sổ nợ so với booking (KIEM-BOOKING-01) cho khối "Kiểm booking" của tab Máy chạy. Chỉ đọc file job ghi, không vào DB.

`state` nói trang được tin số tới đâu, để không bao giờ hiện "không có gì lệch" khi thật ra chưa kiểm:
- `none`: chưa có lượt nào ghi được kết quả (kể cả khi chỉ có lỗi);
- `error`: lượt mới nhất lỗi, số còn lại là của lượt đạt trước đó;
- `stale`: lượt đạt gần nhất cũ hơn hai lượt trước lượt theo lịch gần nhất (:05 mỗi giờ 7–22 giờ; đêm không có lượt);
- `ok`.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import v7_machine

FIRST_HOUR, LAST_HOUR, MINUTE = 7, 22, 5      # lịch timer v7-reconcile-auto


def path() -> Path:
    return Path(os.getenv("WEBDEBIT_BOOKING_CHECK_PATH") or v7_machine.base_dir() / "booking-check.json")


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


def view(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(v7_machine.VN)
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
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
    elif checked < previous_slot(previous_slot(last_slot(now))):   # lượt theo lịch có thể đang chạy; lỡ thêm hai lượt nữa mới là cũ
        state = "stale"
    else:
        state = "ok"
    return {**data, "state": state, "now": now.isoformat(timespec="seconds")}
