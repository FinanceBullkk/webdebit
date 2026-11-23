"""Trần chi phí model của bot (ZALO-BOT-01 Q4): cộng tiền theo token mỗi lượt gọi, vượt trần ngày thì dừng gọi model.

Đơn vị là nano-USD (1e-9 USD), số nguyên: giá "USD mỗi triệu token" nhân 1000 là nano-USD mỗi token. Giá lấy theo bảng giá
Anthropic tháng 11/2026 (skill claude-api); đổi giá thì sửa `PRICES`. Ngày tính theo giờ Việt Nam.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from .state import write_atomic

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NANO = 10**9


@dataclass(frozen=True)
class Price:
    input: int
    output: int
    cache_write_5m: int
    cache_write_1h: int
    cache_read: int


# nano-USD mỗi token = USD mỗi triệu token × 1000.
PRICES = {
    "claude-opus-5-5": Price(4000, 20000, 5000, 8000, 200),
    "claude-sonnet-5-5": Price(2000, 10000, 2500, 4000, 100),
    "claude-haiku-5-5": Price(100, 500, 125, 200, 10),          # lời nhắc tới 100K token
}
HAIKU_LONG = Price(500, 2500, 625, 1000, 50)                    # Haiku 5.5 khi lời nhắc trên 100K token
HAIKU_LONG_FROM = 100_000


def _count(usage: dict, key: str) -> int:
    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def cost(model: str, usage: dict) -> int:
    """Chi phí một lượt gọi theo `usage` của Messages API. Model lạ: lỗi (không đoán giá)."""
    price = PRICES[model]
    read, created = _count(usage, "cache_read_input_tokens"), _count(usage, "cache_creation_input_tokens")
    fresh, out = _count(usage, "input_tokens"), _count(usage, "output_tokens")
    split = usage.get("cache_creation") if isinstance(usage.get("cache_creation"), dict) else {}
    hour = _count(split, "ephemeral_1h_input_tokens")
    five = created - hour if created >= hour else 0
    if model == "claude-haiku-5-5" and fresh + read + created > HAIKU_LONG_FROM:
        price = HAIKU_LONG
    return fresh * price.input + out * price.output + five * price.cache_write_5m + hour * price.cache_write_1h + read * price.cache_read


class Budget:
    """Tiền đã tiêu trong ngày giờ VN, lưu ở `budget.json` để còn qua khởi động lại."""

    def __init__(self, path: Path, cap_usd: int):
        self.path = path
        self.cap = cap_usd * NANO
        self.day: str | None = None
        self.spent = 0
        self._lock = threading.Lock()     # nhiều người hỏi cùng lúc: mỗi câu chạy ở một luồng (F9)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("spent_nano_usd"), int) and isinstance(data.get("day"), str):
                self.day, self.spent = data["day"], data["spent_nano_usd"]
        except (OSError, ValueError):
            pass

    def _today(self, now: float) -> None:
        day = dt.datetime.fromtimestamp(now, VN).date().isoformat()
        if day != self.day:
            self.day, self.spent = day, 0

    def allows(self, now: float) -> bool:
        with self._lock:
            self._today(now)
            return self.spent < self.cap

    def add(self, model: str, usage: dict, now: float) -> int:
        amount = cost(model, usage)
        with self._lock:
            self._today(now)
            self.spent += amount
            write_atomic(self.path, json.dumps({"day": self.day, "spent_nano_usd": self.spent}).encode("utf-8"), 0o600)
        return amount
