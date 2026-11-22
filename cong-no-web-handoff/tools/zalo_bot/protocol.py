"""Giao thức kênh ↔ bộ não: mỗi dòng một JSON (NDJSON) qua socket Unix, trường `v` là phiên bản.

Kênh chạy mã bên thứ ba (zca-js), nên bộ não kiểm chặt mọi dòng nhận được: sai khuôn thì bỏ và đếm, không làm theo.
Khuôn mỗi loại dòng ghi ở `specs/zalo-bot.md` (Phần 1) và được kênh kiểm lại ở `kenh/core.js`.

Kênh → bộ não:
    {"v":1,"type":"hello","kenh_version":"0.1.0","own_id":"<uid nick phụ>"|null}
    {"v":1,"type":"state","state":"online","code":null}
    {"v":1,"type":"message","msg_id":"…","thread_id":"…","from_id":"…","ts":<ms>,"kind":"text","text":"…"}
    {"v":1,"type":"sent","ref":"…","ok":true,"code":null}
Bộ não → kênh:
    {"v":1,"type":"send","ref":"…","thread_id":"…","text":"…","quote_msg_id":"…"|null}
    {"v":1,"type":"typing","thread_id":"…"}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

VERSION = 1
MAX_LINE = 16_384          # byte mỗi dòng nhận; dài hơn thì bỏ cả dòng
MAX_TEXT_IN = 4000         # ký tự câu hỏi nhận vào; dài hơn thì cắt và đánh dấu `truncated`
MAX_TEXT_OUT = 2000        # ký tự mỗi tin gửi; bộ não tự tách trước khi gửi
ID = re.compile(r"^[0-9A-Za-z_.:-]{1,64}$")
CODE = re.compile(r"^[a-z_]{1,40}$")
KENH_VERSION = re.compile(r"^[0-9A-Za-z.+-]{1,20}$")
KINDS = ("text", "image", "sticker", "file", "other")
# Trạng thái kênh: đang nối, đã nhận tin, cần quét QR, đang chờ quét, bị phiên khác đá, mất kết nối, lỗi, thiếu hộp cát mạng.
STATES = ("connecting", "online", "login_required", "login_pending", "kicked", "offline", "error", "sandbox_missing")
TS_MAX = 10**14            # mili giây; lớn hơn là rác


class ProtocolError(ValueError):
    """Dòng sai khuôn. `str(error)` là một mã ngắn để đếm, không chứa dữ liệu của dòng."""


@dataclass(frozen=True)
class Hello:
    kenh_version: str
    own_id: str | None


@dataclass(frozen=True)
class State:
    state: str
    code: str | None


@dataclass(frozen=True)
class Message:
    msg_id: str
    thread_id: str
    from_id: str
    ts_ms: int
    kind: str
    text: str | None
    truncated: bool


@dataclass(frozen=True)
class Sent:
    ref: str
    ok: bool
    code: str | None


def _id(data: dict, key: str, *, optional: bool = False) -> str | None:
    value = data.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ProtocolError(f"bad_{key}")
    return value


def _code(data: dict) -> str | None:
    value = data.get("code")
    if value is None:
        return None
    if not isinstance(value, str) or not CODE.fullmatch(value):
        raise ProtocolError("bad_code")
    return value


def parse(line: bytes) -> Hello | State | Message | Sent:
    """Một dòng kênh gửi → đối tượng đã kiểm. Sai khuôn: `ProtocolError` với mã ngắn."""
    if len(line) > MAX_LINE:
        raise ProtocolError("too_long")
    try:
        data = json.loads(line)
    except (ValueError, UnicodeDecodeError):
        raise ProtocolError("bad_json") from None
    if not isinstance(data, dict) or data.get("v") != VERSION:
        raise ProtocolError("bad_version")
    kind = data.get("type")
    if kind == "hello":
        version = data.get("kenh_version")
        if not isinstance(version, str) or not KENH_VERSION.fullmatch(version):
            raise ProtocolError("bad_kenh_version")
        return Hello(version, _id(data, "own_id", optional=True))
    if kind == "state":
        if data.get("state") not in STATES:
            raise ProtocolError("bad_state")
        return State(data["state"], _code(data))
    if kind == "message":
        ts = data.get("ts")
        if not isinstance(ts, int) or isinstance(ts, bool) or not 0 < ts < TS_MAX:
            raise ProtocolError("bad_ts")
        if data.get("kind") not in KINDS:
            raise ProtocolError("bad_kind")
        text = data.get("text")
        if text is not None and not isinstance(text, str):
            raise ProtocolError("bad_text")
        if data["kind"] == "text" and not (text and text.strip()):
            raise ProtocolError("empty_text")
        truncated = text is not None and len(text) > MAX_TEXT_IN
        return Message(_id(data, "msg_id"), _id(data, "thread_id"), _id(data, "from_id"), ts, data["kind"],
                       text[:MAX_TEXT_IN] if truncated else text, truncated)
    if kind == "sent":
        if not isinstance(data.get("ok"), bool):
            raise ProtocolError("bad_ok")
        return Sent(_id(data, "ref"), data["ok"], _code(data))
    raise ProtocolError("bad_type")


def _line(payload: dict) -> bytes:
    return (json.dumps({"v": VERSION, **payload}, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def send(ref: str, thread_id: str, text: str, quote_msg_id: str | None = None) -> bytes:
    """Lệnh gửi một tin. Tin dài hơn `MAX_TEXT_OUT` phải được tách trước (`split_text`)."""
    if not ID.fullmatch(ref) or not ID.fullmatch(thread_id) or (quote_msg_id is not None and not ID.fullmatch(quote_msg_id)):
        raise ValueError("bad id")
    if not text or len(text) > MAX_TEXT_OUT:
        raise ValueError("text length")
    return _line({"type": "send", "ref": ref, "thread_id": thread_id, "text": text, "quote_msg_id": quote_msg_id})


def typing(thread_id: str) -> bytes:
    if not ID.fullmatch(thread_id):
        raise ValueError("bad id")
    return _line({"type": "typing", "thread_id": thread_id})


def split_text(text: str, limit: int = MAX_TEXT_OUT) -> list[str]:
    """Tách câu trả lời dài thành nhiều tin, ưu tiên cắt ở xuống dòng, rồi khoảng trắng; không bỏ ký tự nào ngoài khoảng trắng ở chỗ cắt."""
    parts: list[str] = []
    rest = text.strip()
    while len(rest) > limit:
        cut = rest.rfind("\n", 0, limit + 1)
        if cut < limit // 2:
            cut = rest.rfind(" ", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts
