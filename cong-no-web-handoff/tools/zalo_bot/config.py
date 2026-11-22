"""Cấu hình bộ não: cờ bật, danh sách người hỏi, đường dẫn. Không in hay ghi giá trị bí mật.

Danh sách người hỏi `/etc/webdebit/zalo-bot.json` (chủ root, nhóm của bộ não, 0640):

    {"users": [{"zalo_id": "<uid Zalo>", "login": "<login Tailscale>", "role": "admin" | "user"}]}

`role` theo QUYEN-01. Bộ não chỉ trả lời người có trong file; thiếu file là không ai được hỏi.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

from .protocol import ID

ENABLED_ENV = "WEBDEBIT_ZALO_BOT"                 # "1" mới trả lời; khác "1" thì chỉ đếm (cờ tắt hẳn của spec)
USERS_ENV = "WEBDEBIT_ZALO_BOT_USERS"
SOCKET_ENV = "WEBDEBIT_ZALO_BOT_SOCKET"
STATE_ENV = "WEBDEBIT_ZALO_BOT_STATE"
RELEASE_ENV = "WEBDEBIT_ZALO_BOT_RELEASE"
USERS_FILE = "/etc/webdebit/zalo-bot.json"
SOCKET_FILE = "/run/v7-zalo-sock/kenh.sock"
STATE_DIR = "/srv/v7/zalo-bot"
RELEASE_LINK = "/srv/v7/auto-releases/current"
ROLES = ("admin", "user")
LOGIN = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}$")


class ConfigError(ValueError):
    """Cấu hình sai: bộ não dừng thay vì chạy với danh sách mơ hồ."""


@dataclass(frozen=True)
class User:
    zalo_id: str
    login: str
    role: str


@dataclass(frozen=True)
class Config:
    enabled: bool
    users_file: Path
    socket: Path
    state_dir: Path
    release_link: Path

    @property
    def status_file(self) -> Path:
        return self.state_dir / "status.json"

    @property
    def memory_file(self) -> Path:
        return self.state_dir / "brain-state.json"

    @property
    def log_dir(self) -> Path:
        return self.state_dir / "log"


def from_env(env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    return Config(enabled=env.get(ENABLED_ENV) == "1", users_file=Path(env.get(USERS_ENV) or USERS_FILE),
                  socket=Path(env.get(SOCKET_ENV) or SOCKET_FILE), state_dir=Path(env.get(STATE_ENV) or STATE_DIR),
                  release_link=Path(env.get(RELEASE_ENV) or RELEASE_LINK))


def load_users(path: Path) -> dict[str, User]:
    """Đọc danh sách người hỏi theo Zalo id. Không có file: rỗng. File người khác ghi được hoặc sai khuôn: `ConfigError`."""
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return {}
    if os.name == "posix" and mode & 0o022:
        raise ConfigError("users_file_writable")    # nhóm hay người khác ghi được thì ai cũng tự thêm mình vào
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ConfigError("users_file_unreadable") from None
    rows = data.get("users") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ConfigError("users_missing")
    users: dict[str, User] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"zalo_id", "login", "role"}:
            raise ConfigError("user_shape")
        zalo_id, login, role = row["zalo_id"], row["login"], row["role"]
        if not isinstance(zalo_id, str) or not ID.fullmatch(zalo_id):
            raise ConfigError("user_zalo_id")
        if not isinstance(login, str) or not LOGIN.fullmatch(login):
            raise ConfigError("user_login")
        if role not in ROLES:
            raise ConfigError("user_role")
        if zalo_id in users:
            raise ConfigError("user_duplicate")
        users[zalo_id] = User(zalo_id, login, role)
    return users
