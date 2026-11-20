"""QUYEN-02: danh sách ai được vào sổ và ai là quản lý, sửa được trên trang Người dùng.

Hai nguồn gộp lại:
- Cố định: WEBDEBIT_ALLOWED_LOGINS / WEBDEBIT_ADMIN_LOGINS (ACCESS-01, QUYEN-01). Trang không sửa được nên đây là
  đường cứu khi lỡ tay trên web.
- File WEBDEBIT_ACCESS_FILE do API ghi (ghi tạm rồi đổi tên, mode 600), kèm lịch sử thay đổi.

Được vào = cố định ∪ file. Quản lý = cố định ∪ file có vai trò quản lý. Chưa đặt danh sách quản lý cố định và file
chưa có quản lý nào thì giữ nghĩa của QUYEN-01: mọi login được vào đều là quản lý. File hỏng thì chỉ dùng phần cố
định (fail closed) và không cho ghi, tới khi người vận hành sửa file.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import threading
import unicodedata
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import v7_identity
from v7_api_validate import ApiError

VN = ZoneInfo("Asia/Ho_Chi_Minh")
ADMIN, USER = "admin", "user"
ROLES = (ADMIN, USER)
MAX_HISTORY = 500
SHOWN_HISTORY = 30
MAX_DENIED = 20
MAX_NAME = 40
LOGIN_SHAPE = re.compile(r"[^\s@,]{1,128}@[^\s@,]{1,125}")


def now_text() -> str:
    return datetime.now(VN).isoformat(timespec="seconds")


def normalize_login(value: object) -> str:
    try:
        login = v7_identity.normalize_login(value)
    except v7_identity.IdentityError as exc:
        raise ApiError(422, "INVALID_LOGIN", "Login Tailscale không hợp lệ (dạng ten@mien).") from exc
    if not LOGIN_SHAPE.fullmatch(login):
        raise ApiError(422, "INVALID_LOGIN", "Login Tailscale không hợp lệ (dạng ten@mien).")
    return login


def clean_name(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(422, "INVALID_NAME", "Tên gọi không hợp lệ.")
    name = " ".join(value.split())
    if any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in name) or len(name) > MAX_NAME:
        raise ApiError(422, "INVALID_NAME", f"Tên gọi tối đa {MAX_NAME} ký tự.")
    return name or None


class DeniedLog:
    """Login vừa bị chặn (ACCESS-01) kể từ lần khởi động; chỉ trong bộ nhớ, tối đa MAX_DENIED login."""

    def __init__(self, limit: int = MAX_DENIED):
        self.limit = limit
        self.lock = threading.Lock()
        self.items: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def record(self, login: object) -> None:
        if not isinstance(login, str) or not LOGIN_SHAPE.fullmatch(login):
            return
        with self.lock:
            held = self.items.pop(login, {"count": 0})
            self.items[login] = {"count": held["count"] + 1, "last_at": now_text()}
            while len(self.items) > self.limit:
                self.items.popitem(last=False)

    def forget(self, login: str) -> None:
        with self.lock:
            self.items.pop(login, None)

    def view(self, allowed: frozenset[str] | None) -> list[dict[str, Any]]:
        with self.lock:
            rows = [{"login": login, **item} for login, item in self.items.items()]
        return [row for row in reversed(rows) if allowed is None or row["login"] not in allowed]


class AccessStore:
    def __init__(self, path: str | os.PathLike | None, fixed_allowed: frozenset[str] | None,
                 fixed_admins: frozenset[str] | None):
        self.path = Path(path) if path else None
        self.fixed_allowed = fixed_allowed
        self.fixed_admins = fixed_admins
        self.lock = threading.Lock()
        self.stamp: tuple | None = None
        self.doc: dict[str, Any] = {"version": 0, "users": [], "history": []}
        self.broken = False

    # ---- đọc ----
    def _stat(self) -> tuple | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return (stat.st_ino, stat.st_mtime_ns, stat.st_size)

    def _load(self) -> None:
        """Đọc lại khi file đổi. Gọi khi đã giữ lock."""
        if self.path is None:
            return
        try:
            stamp = self._stat()
        except OSError:
            stamp = ("unreadable",)
        if stamp == self.stamp:
            return
        self.stamp = stamp
        if stamp is None:
            self.doc, self.broken = {"version": 0, "users": [], "history": []}, False
            return
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            users = doc["users"]
            if not isinstance(doc.get("version"), int) or not isinstance(users, list) or not isinstance(doc.get("history", []), list):
                raise ValueError("shape")
            seen = set()
            for user in users:
                if not isinstance(user, dict) or user.get("role") not in ROLES or normalize_login(user.get("login")) != user["login"] \
                        or user["login"] in seen:
                    raise ValueError("user")
                seen.add(user["login"])
            self.doc, self.broken = {"version": doc["version"], "users": users, "history": doc.get("history", [])}, False
        except (OSError, ValueError, KeyError, TypeError, ApiError) as exc:
            print(f"QUYEN-02: file danh sách login hỏng ({type(exc).__name__}); chỉ dùng danh sách cố định", file=sys.stderr, flush=True)
            self.doc, self.broken = {"version": 0, "users": [], "history": []}, True

    def _lists(self) -> tuple[frozenset[str] | None, frozenset[str] | None]:
        users = self.doc["users"]
        allowed = None if self.fixed_allowed is None else self.fixed_allowed | {user["login"] for user in users}
        managed_admins = {user["login"] for user in users if user["role"] == ADMIN}
        admins = None if self.fixed_admins is None and not managed_admins else (self.fixed_admins or frozenset()) | managed_admins
        return allowed, admins

    def lists(self) -> tuple[frozenset[str] | None, frozenset[str] | None]:
        """(được vào, quản lý) có hiệu lực cho yêu cầu này."""
        with self.lock:
            self._load()
            return self._lists()

    def _fixed_role(self, login: str) -> str | None:
        if self.fixed_allowed is None or login not in self.fixed_allowed:
            return None
        return ADMIN if self.fixed_admins is None or login in self.fixed_admins else USER

    def view(self, actor: str) -> dict[str, Any]:
        with self.lock:
            self._load()
            allowed, _ = self._lists()
            rows = [{"login": login, "name": None, "role": self._fixed_role(login), "fixed": True, "added_by": None, "added_at": None}
                    for login in sorted(self.fixed_allowed or ())]
            fixed = {row["login"] for row in rows}
            rows += [{"login": user["login"], "name": user.get("name"), "role": user["role"], "fixed": False,
                      "added_by": user.get("added_by"), "added_at": user.get("added_at")}
                     for user in self.doc["users"] if user["login"] not in fixed]
            for row in rows:
                row["me"] = row["login"] == actor
            return {"configured": self.path is not None and not self.broken, "broken": self.broken, "version": self.doc["version"],
                    "users": rows, "denied": DENIED.view(allowed),
                    "history": list(reversed(self.doc["history"][-SHOWN_HISTORY:]))}

    # ---- ghi ----
    def apply(self, actor: str, body: object) -> dict[str, Any]:
        if not isinstance(body, dict) or body.get("action") not in ("add", "role", "name", "remove") \
                or not isinstance(body.get("version"), int) or isinstance(body.get("version"), bool):
            raise ApiError(422, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
        allowed_keys = {"add": {"action", "version", "login", "role", "name"}, "role": {"action", "version", "login", "role"},
                        "name": {"action", "version", "login", "name"}, "remove": {"action", "version", "login"}}[body["action"]]
        if set(body) - allowed_keys or "login" not in body:
            raise ApiError(422, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
        login = normalize_login(body["login"])
        action = body["action"]
        if action in ("add", "role") and body.get("role", USER if action == "add" else None) not in ROLES:
            raise ApiError(422, "INVALID_ROLE", "Vai trò phải là Quản lý hoặc Nhân viên.")
        name = clean_name(body.get("name"))
        if self.path is None:
            raise ApiError(503, "ACCESS_NOT_CONFIGURED", "Máy chủ chưa bật quản lý người dùng trên web.")
        with self.lock:
            self._load()
            if self.broken:
                raise ApiError(503, "ACCESS_FILE_BROKEN", "File danh sách người dùng trên máy chủ bị hỏng. Báo quản trị kiểm.")
            if body["version"] != self.doc["version"]:
                raise ApiError(409, "STALE", "Danh sách vừa được người khác đổi. Trang đã đọc lại, xem rồi làm lại.")
            if login == actor:
                raise ApiError(409, "SELF", "Không tự đổi quyền của chính mình.")
            if self._fixed_role(login) is not None:
                raise ApiError(409, "FIXED_LOGIN", "Login này đặt cố định trên máy chủ, không sửa trên web.")
            users = [dict(user) for user in self.doc["users"]]
            found = next((user for user in users if user["login"] == login), None)
            before = None if found is None else {key: found.get(key) for key in ("role", "name")}
            if action == "add":
                if found is not None:
                    raise ApiError(409, "EXISTS", "Login này đã có trong danh sách.")
                found = {"login": login, "role": body.get("role", USER), "name": name, "added_by": actor, "added_at": now_text()}
                users.append(found)
            elif found is None:
                raise ApiError(404, "NOT_FOUND", "Không có login này trong danh sách.")
            elif action == "role":
                found["role"] = body["role"]
            elif action == "name":
                found["name"] = name
            else:
                users.remove(found)
            after = None if action == "remove" else {key: found.get(key) for key in ("role", "name")}
            if before == after:
                return {"ok": True, "version": self.doc["version"], "changed": False}
            _, admins_before = self._lists()
            doc = {"version": self.doc["version"] + 1, "users": users,
                   "history": (self.doc["history"] + [{"at": now_text(), "actor": actor, "action": action, "login": login,
                                                       "before": before, "after": after}])[-MAX_HISTORY:]}
            old = self.doc
            self.doc = doc
            _, admins_after = self._lists()
            if admins_before is not None and not admins_after:
                self.doc = old
                raise ApiError(409, "LAST_ADMIN", "Phải còn ít nhất một quản lý.")
            try:
                self._write(doc)
            except OSError as exc:
                self.doc = old
                raise ApiError(503, "ACCESS_WRITE_FAILED", "Chưa ghi được danh sách người dùng. Thử lại sau.") from exc
        if action == "add":
            DENIED.forget(login)
        print(f"QUYEN-02: {actor} {action} {login} {before} → {after}", file=sys.stderr, flush=True)
        return {"ok": True, "version": doc["version"], "changed": True}

    def _write(self, doc: dict[str, Any]) -> None:
        folder = self.path.parent
        descriptor, name = tempfile.mkstemp(dir=folder, prefix=".access-", suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(doc, stream, ensure_ascii=False, indent=1)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(name)
            raise
        self.stamp = self._stat()


DENIED = DeniedLog()
STORE: AccessStore | None = None


def view_users(actor: str) -> dict[str, Any]:
    if STORE is None:
        raise ApiError(503, "ACCESS_NOT_CONFIGURED", "Máy chủ chưa bật quản lý người dùng trên web.")
    return STORE.view(actor)


def handle_users(raw: bytes, _runner: Any, actor: str) -> tuple[int, dict[str, Any]]:
    if STORE is None:
        raise ApiError(503, "ACCESS_NOT_CONFIGURED", "Máy chủ chưa bật quản lý người dùng trên web.")
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise ApiError(422, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.") from exc
    return 200, STORE.apply(actor, body)
