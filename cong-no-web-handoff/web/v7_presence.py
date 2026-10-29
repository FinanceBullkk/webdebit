"""PRESENCE-01: who is online, where, which cell, mouse pointer — RAM only, never DB/log.

Advisory only: no locks, no effect on ledger writes. Actor always comes from the
server (v7_identity); the client only supplies its tab id and position.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

TTL = 30.0            # không nghe báo 30 giây thì người đó biến mất
POINTER_TTL = 3.0     # mũi tên chuột cũ hơn 3 giây thì ẩn
MAX_BODY = 2048
MAX_STREAMS = 40
MAX_STREAMS_PER_ACTOR = 6
MAX_ENTRIES = 200
MAX_TABS_PER_ACTOR = 20
COLORS = 8
PAGES = ("dashboard", "cong-no-theo-thang", "so-khach", "sheet-queue")
TAB = re.compile(r"[A-Za-z0-9_-]{8,64}")
ROW = re.compile(r"[a-z_]{1,20}:[A-Za-z0-9_.:-]{1,40}")
COL = re.compile(r"[a-z0-9_]{1,40}")
MONTH = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
# Tên ngắn theo login Tailscale, file trên máy chạy (ngoài Git vì chứa login): {"version": 1, "names": {"login": "Tên"}}.
NAMES_PATH = os.getenv("WEBDEBIT_PRESENCE_NAMES_PATH", "/srv/v7/presence-names.json")


class PresenceError(ValueError):
    pass


def _bad() -> None:
    raise PresenceError("INVALID_REQUEST")


def _int_in(value, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _anchor(value, keys: set[str]) -> dict | None:
    if value is None:
        return None
    if type(value) is not dict or set(value) != keys:
        _bad()
    if not isinstance(value["row"], str) or not ROW.fullmatch(value["row"]):
        _bad()
    if not isinstance(value["col"], str) or not COL.fullmatch(value["col"]):
        _bad()
    if "editing" in keys and type(value["editing"]) is not bool:
        _bad()
    # Vị trí trong ô tính theo phần nghìn (0–1000), không dùng số thực.
    if "fx" in keys and not (_int_in(value["fx"], 0, 1000) and _int_in(value["fy"], 0, 1000)):
        _bad()
    return dict(value)


def parse(raw: bytes) -> dict:
    """Validate a POST body; returns the normalized report or raises PresenceError."""
    if len(raw) > MAX_BODY:
        raise PresenceError("BODY_TOO_LARGE")
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError):
        _bad()
    if type(body) is not dict or not set(body) <= {"tab", "page", "customer_id", "month", "cell", "pointer"}:
        _bad()
    if not isinstance(body.get("tab"), str) or not TAB.fullmatch(body["tab"]):
        _bad()
    page = body.get("page")
    if page is not None and page not in PAGES:
        _bad()
    customer = body.get("customer_id")
    if customer is not None and not _int_in(customer, 1, 9223372036854775807):
        _bad()
    month = body.get("month")
    if month is not None and (not isinstance(month, str) or not MONTH.fullmatch(month)):
        _bad()
    return {"tab": body["tab"], "page": page, "customer_id": customer, "month": month,
            "cell": _anchor(body.get("cell"), {"row", "col", "editing"}),
            "pointer": _anchor(body.get("pointer"), {"row", "col", "fx", "fy"})}


def display_name(actor: str, names: dict[str, str] | None = None) -> str:
    return (names or {}).get(actor.lower()) or actor.split("@", 1)[0][:40]


def load_names(path: str) -> dict[str, str]:
    """Read the short-name table; missing or invalid file means no short names (fall back to login)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if type(data) is not dict or data.get("version") != 1 or type(data.get("names")) is not dict:
            return {}
        return {login.strip().lower(): name.strip() for login, name in data["names"].items()
                if type(login) is str and type(name) is str and login.strip() and name.strip()
                and len(name.strip()) <= 30 and not any(ord(ch) < 32 for ch in name)}
    except (OSError, UnicodeError, ValueError):
        return {}


class NameTable:
    """Re-read the file only when it changes, so editing it on the server needs no restart."""

    def __init__(self, path: str = NAMES_PATH):
        self.path, self.stamp, self.names = path, None, {}

    def __call__(self) -> dict[str, str]:
        try:
            info = os.stat(self.path)
            stamp = (info.st_mtime_ns, info.st_size)
        except OSError:
            stamp = None
        if stamp != self.stamp:
            self.stamp, self.names = stamp, load_names(self.path) if stamp else {}
        return self.names


class Presence:
    def __init__(self, clock=time.monotonic, names=None):
        self.clock = clock
        self.names = names or NameTable()
        self.salt = secrets.token_bytes(16)   # mã người theo tiến trình, không lộ login
        self.cond = threading.Condition()
        self.version = 0
        self.entries: dict[tuple[str, str], dict] = {}
        self.dev_numbers: dict[str, int] = {}
        self.streams: dict[str, int] = {}

    def _id(self, actor: str, tab: str) -> str:
        return hashlib.sha256(self.salt + f"{actor}\0{tab}".encode()).hexdigest()[:12]

    def _name(self, actor: str, tab: str, names: dict[str, str]) -> str:
        # Chạy dev mọi tab cùng một actor: đánh số theo tab để vẫn phân biệt được.
        if actor.startswith("dev:"):
            return f"Người dùng {self.dev_numbers.get(tab, 0)}"
        return display_name(actor, names)

    def _expire(self, now: float) -> None:
        for key in [key for key, entry in self.entries.items() if now - entry["at"] > TTL]:
            del self.entries[key]
            self.version += 1

    def report(self, actor: str, report: dict) -> None:
        key = (actor, report["tab"])
        with self.cond:
            now = self.clock()
            self._expire(now)
            if report["page"] is None:
                self.entries.pop(key, None)
            else:
                if key not in self.entries and (len(self.entries) >= MAX_ENTRIES
                                                or sum(a == actor for a, _ in self.entries) >= MAX_TABS_PER_ACTOR):
                    raise PresenceError("TOO_MANY_TABS")
                self.entries[key] = {**report, "at": now, "pointer_at": now}
                if actor.startswith("dev:"):
                    self.dev_numbers.setdefault(report["tab"], len(self.dev_numbers) + 1)
            if not self.entries:
                self.dev_numbers.clear()
            self.version += 1
            self.cond.notify_all()

    def view(self, actor: str, tab: str) -> list[dict]:
        """Everyone except this tab. Cell/pointer only between tabs on the same customer book."""
        with self.cond:
            now = self.clock()
            self._expire(now)
            me = self.entries.get((actor, tab))
            book = me["customer_id"] if me and me["page"] == "so-khach" else None
            names = self.names()
            people = []
            for (other, other_tab), entry in sorted(self.entries.items(), key=lambda item: item[1]["at"]):
                if (other, other_tab) == (actor, tab):
                    continue
                person = {"id": self._id(other, other_tab), "name": self._name(other, other_tab, names),
                          "color": int(hashlib.sha256(other.encode()).hexdigest(), 16) % COLORS,
                          "page": entry["page"], "customer_id": entry["customer_id"], "month": entry["month"],
                          "cell": None, "pointer": None}
                if book is not None and entry["page"] == "so-khach" and entry["customer_id"] == book:
                    person["cell"] = entry["cell"]
                    if entry["pointer"] is not None and now - entry["pointer_at"] <= POINTER_TTL:
                        person["pointer"] = entry["pointer"]
                people.append(person)
            return people

    def wait(self, version: int, timeout: float) -> int:
        with self.cond:
            if self.version == version:
                self.cond.wait(timeout)
            return self.version

    def open_stream(self, actor: str) -> bool:
        with self.cond:
            if sum(self.streams.values()) >= MAX_STREAMS or self.streams.get(actor, 0) >= MAX_STREAMS_PER_ACTOR:
                return False
            self.streams[actor] = self.streams.get(actor, 0) + 1
            return True

    def close_stream(self, actor: str) -> None:
        with self.cond:
            left = self.streams.get(actor, 0) - 1
            if left > 0:
                self.streams[actor] = left
            else:
                self.streams.pop(actor, None)
