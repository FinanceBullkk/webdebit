"""Bộ nhớ đọc của API theo dấu dữ liệu (HIEU-NANG-01, specs/hieu-nang-01.md).

Bốn hàm đọc nặng (`CACHED`) chỉ chạy lại khi dữ liệu `sokhach` đổi hoặc sang ngày VN mới. Mỗi lượt đọc lấy dấu mới bằng
`get_read_stamp` (một lần psql, ~30 ms trong DB), nên lượt GET đến sau một lệnh ghi luôn thấy bản mới. Chỉ dùng ở đường GET:
lệnh ghi, máy theo Sheet và hộp thư nền đọc thẳng runner.

Giữ chữ JSON, không giữ dict: mỗi lượt `json.loads` một bản mới, nơi gọi sửa dict thoải mái. Dấu hỏng hoặc DB chưa có hàm dấu
thì đọc thẳng như trước bộ nhớ.
"""

from __future__ import annotations

import json
import re
import threading
from collections import OrderedDict
from concurrent.futures import Future
from typing import Any

from v7_api_validate import ApiError

CACHED = frozenset({"get_ledger", "get_dashboard", "get_dashboard_debt", "get_receivables_matrix"})
MAX_BYTES = 96 * 1024 * 1024
_STAMP = re.compile(r"[0-9a-f]{32}")
_DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _text(runner, function: str, payload: dict, actor: str) -> str:
    run_text = getattr(runner, "run_text", None)
    if run_text is not None:
        return run_text(function, payload, actor)
    return json.dumps(runner.run(function, payload, actor), ensure_ascii=False, separators=(",", ":"))


class ReadCache:
    def __init__(self, max_bytes: int = MAX_BYTES):
        self.max_bytes = max_bytes
        self.lock = threading.Lock()
        self.stamp: str | None = None                   # dấu của các bản đang giữ
        self.entries: OrderedDict[tuple, str] = OrderedDict()
        self.size = 0
        self.flights: dict[tuple, Future] = {}
        self.hits = self.misses = 0

    def current_stamp(self, runner, actor: str) -> str | None:
        """`as_of:stamp` mới đọc, hoặc None (DB cũ chưa có hàm, lỗi, sai dạng) để đọc thẳng."""
        try:
            body = runner.run("get_read_stamp", {}, actor)
        except Exception:  # noqa: BLE001  dấu hỏng không được làm hỏng lượt đọc
            return None
        if not isinstance(body, dict):
            return None
        day, stamp = body.get("as_of"), body.get("stamp")
        if not (isinstance(day, str) and _DAY.fullmatch(day) and isinstance(stamp, str) and _STAMP.fullmatch(stamp)):
            return None
        return f"{day}:{stamp}"

    def run(self, runner, function: str, payload: dict, actor: str) -> Any:
        if function not in CACHED:
            return runner.run(function, payload, actor)
        stamp = self.current_stamp(runner, actor)
        if stamp is None:
            return runner.run(function, payload, actor)
        key = (stamp, function, json.dumps(payload, sort_keys=True, separators=(",", ":")))
        with self.lock:
            text = self.entries.get(key)
            if text is not None:
                self.entries.move_to_end(key)
                self.hits += 1
                return json.loads(text)
            flight = self.flights.get(key)
            owner = flight is None
            if owner:
                flight = self.flights[key] = Future()
                self.misses += 1
        if not owner:
            return json.loads(flight.result())   # lỗi của lượt đang chạy ném lại ở đây
        try:
            text = _text(runner, function, payload, actor)
            try:
                value = json.loads(text)
            except ValueError as exc:   # như runner.run: chữ hỏng là DB không trả lời được; không giữ
                raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.") from exc
        except BaseException as exc:
            with self.lock:
                self.flights.pop(key, None)
            flight.set_exception(exc)
            raise
        with self.lock:
            self.flights.pop(key, None)
            self._keep(key, text)
        flight.set_result(text)
        return value

    def _keep(self, key: tuple, text: str) -> None:
        if key[0] != self.stamp:   # dấu mới: bản của dấu cũ không bao giờ trúng nữa
            self.entries.clear()
            self.size, self.stamp = 0, key[0]
        if len(text) > self.max_bytes:
            return
        old = self.entries.pop(key, None)
        if old is not None:
            self.size -= len(old)
        self.entries[key] = text
        self.size += len(text)
        while self.size > self.max_bytes:
            _, dropped = self.entries.popitem(last=False)
            self.size -= len(dropped)


class CachedReads:
    """Runner chỉ đọc cho một lượt GET: hàm trong `CACHED` qua bộ nhớ, còn lại đi thẳng."""

    def __init__(self, runner, cache: ReadCache):
        self.runner, self.cache = runner, cache

    def run(self, function: str, payload: dict, actor: str) -> Any:
        return self.cache.run(self.runner, function, payload, actor)
