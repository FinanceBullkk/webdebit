"""WECHAT-01: nguồn WeChat của zalo-agent (hợp đồng dữ liệu trong specs/zalo-agent.md, mục "Nguồn WeChat").

Bộ xử lý `wechat` gọi bộ đọc chỉ-đọc `wechat_export.py` (tiến trình con, Python của venv WeChat) theo nhịp, đổi tin sang ĐÚNG
khuôn dòng tin của gói chat rồi nối vào kho cục bộ `<root>/wechat/log.jsonl`. Bộ xử lý `bundle` nhận kho đó làm "overlay":
dựng đầy đủ thì gộp nhóm, người gửi, tin và ảnh WeChat vào thư mục dữ liệu mới; giữa hai lần dựng thì nối tin mới vào
`messages-delta.jsonl` như tin Zalo. `hao` không phải sửa gì: nhóm WeChat là một hội thoại bình thường trong gói
(`conversation_id` = sha256 hex của `wechat:<username>`, nhãn "WeChat · <tên>").

Tiến trình con chạy trong luồng nền để chậm hay treo (timeout 60 giây) không giữ vòng lặp của `bundle`. Lỗi con lùi dần riêng
(`interval` nhân đôi tới 15 phút). Chỉ nhóm trong `wechat-groups.json` được đọc; không chữ tin nào đi vào model.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import queue
import re
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import zalo_web_bundle as wb

from .. import cursor as cursors
from .. import wechat_app
from ..cursor import now_iso
from ..source import VN, read_json, retry_io
from ..status import track_value
from ..wechat_export import XMLISH, clean_content

NAME = "wechat"
SCRIPT = Path(__file__).resolve().parents[1] / "wechat_export.py"
INTERVAL, MAX_BACKOFF, TIMEOUT = 10, 15 * 60, 60
RECHECK_HOURS = 6      # đọc lại các tin trong khoảng này mỗi lượt để thấy tin bị sửa tại chỗ (thu hồi)
DEEP_IMAGE_HOURS = 7 * 24   # lượt đầu sau khi agent chạy: thử lại ảnh còn thiếu của 7 ngày (bật ảnh muộn, sửa khóa xong rồi chạy lại)
DEEP_TRIES = 2              # lượt 7 ngày lỗi (quá giờ…) chừng này lần thì bỏ: tin chữ không bao giờ bị kẹt sau một yêu cầu quá nặng
SENDER_RULE = 2             # tăng khi đổi cách tìm người gửi (2: tiền tố `<username>:` thắng SenderName2Id, 22/11/2026)
RESEND_HOURS = 400 * 24     # lượt sửa người gửi một lần: đọc lại tin trong chừng này giờ (tối đa WINDOW_CAP tin mỗi nhóm)
RESEND_TRIES = 2            # lượt sửa quá giờ chừng này lần thì thôi tới lần chạy agent sau: tin mới không bao giờ kẹt sau nó
APP_EVERY = 30              # giây giữa hai lần xem app WeChat có chạy, có đăng nhập không
THUMB_PIXELS = 240 * 240    # ảnh từ chừng này điểm ảnh trở xuống coi là ảnh thu nhỏ của WeChat (cạnh dài ~120–240): còn tìm bản lớn hơn
SMALL_RETRY = 600           # giây: ảnh thu nhỏ hoặc tải dở thử tìm bản lớn/trọn hơn mỗi 10 phút trong cửa sổ
MISSING_RETRY = 60          # giây: tin ảnh chưa có ảnh nào thử lại mỗi phút (không mỗi 10 giây: upstream duyệt cả cây ảnh mỗi lần thử)
IMAGE_MIMES = ("image/jpeg", "image/png", "image/gif", "image/webp")   # `wb.sniff` còn nhận video; tin ảnh chỉ lấy ảnh
SETTLE = 30 * 60            # giây: tin đã vào kho chừng này mà vẫn chưa có trong gói trên hao mới tính là lệch (số đếm theo ngày)
RESUME_GAP = 120            # giây: `step` cách nhau quá chừng này (máy ngủ dậy, vòng lặp đứng) thì coi như vừa khởi động lại
DAILY_DAYS = 3              # số ngày VN gần nhất đưa vào số đếm `daily` của status
SELF_NAME = "Tôi (WeChat)"
# local_type của WeChat 4.x (tên do upstream đặt) → message_type của gói Zalo (TYPE_NAMES trong web/v7_zalo_chat.py).
KINDS = {"文本": 1, "图片": 2, "文件/链接/卡片": 19, "系统消息": -4, "语音": 3, "视频": 18, "位置": 17, "动画表情": 4,
         "音视频通话": 6, "红包": 19}
LABELS = {"图片": "Ảnh WeChat (chưa đọc được)", "语音": "[Ghi âm WeChat]", "视频": "[Video WeChat]", "位置": "[Vị trí WeChat]",
          "动画表情": "[Biểu tượng WeChat]", "音视频通话": "[Cuộc gọi WeChat]", "红包": "[Lì xì WeChat]"}
UNKNOWN_LABEL = "[Tin WeChat loại lạ]"
NOTICE_LABEL = "[Thông báo WeChat]"   # tin hệ thống không có chữ đọc được (vào nhóm, vỗ…)
MEMBER_NAME = "Thành viên WeChat"     # người gửi chưa tra được tên: không bao giờ dùng wxid thô làm tên


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def conversation_id(username: str) -> str:
    return sha("wechat:" + username)


def message_id(username: str, local_id: int, sort_seq: int) -> str:
    # `local_id` của WeChat 4.x lặp lại giữa các phân mảnh DB (upstream ghi rõ), nên thêm `sort_seq` để hai tin không trùng mã.
    return sha(f"wechat:{username}:{local_id}:{sort_seq}")


def seconds(value: object) -> float | None:
    """Giờ của dòng tin trong gói (mili giây dạng chuỗi hay số) → giây; None khi không đọc được."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    return value / 1000 if isinstance(value, int) else None


def number(value: object) -> float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def day_of(stamp: float) -> str:
    return datetime.fromtimestamp(stamp, VN).date().isoformat()


def sender_id(wxid: str) -> str:
    return sha("wechat:sender:" + wxid)[:32]


SELF_ID = sha("wechat:self")[:32]
WXID = re.compile(r"wxid_[A-Za-z0-9]+")


def safe_name(name: object, wxid: str = "") -> str:
    """Tên hiển thị của người gửi; thiếu hoặc là mã thô (`wxid_…`, đúng mã người gửi) thì "Thành viên WeChat"."""
    shown = name.strip() if isinstance(name, str) else ""
    return MEMBER_NAME if not shown or shown == wxid or WXID.fullmatch(shown) else shown


def convert(item: dict, image: str | None = None) -> tuple[dict, tuple[str, str] | None] | None:
    """Một dòng JSON của bộ đọc → (dòng tin của gói, (mã người gửi, tên) hoặc None). Dòng sai khuôn thì None."""
    username, local_id, seq, stamp = item.get("username"), item.get("local_id"), item.get("sort_seq"), item.get("create_time")
    if not (isinstance(username, str) and all(isinstance(value, int) and not isinstance(value, bool) for value in (local_id, seq, stamp))):
        return None
    kind = item.get("type")
    content = item.get("content") if isinstance(item.get("content"), str) else ""
    if isinstance(item.get("type"), str) and XMLISH.search(content):   # phòng con cũ chưa làm sạch: XML không bao giờ lên gói
        content = clean_content(item["type"], content, item.get("sender") or "", bool(item.get("is_self")))
    mtype = KINDS.get(kind, 19) if isinstance(kind, str) else 19
    if kind == "图片":
        body = "Ảnh WeChat" if image else LABELS[kind]
    elif kind == "系统消息":
        body = content.strip() or NOTICE_LABEL
    elif kind in ("文本", "文件/链接/卡片"):
        body = content.strip() or UNKNOWN_LABEL
    else:
        body = LABELS.get(kind, UNKNOWN_LABEL) if isinstance(kind, str) else UNKNOWN_LABEL
    own = bool(item.get("is_self"))
    wxid = item.get("sender") if isinstance(item.get("sender"), str) else ""
    sid = SELF_ID if own else sender_id(wxid) if wxid else None
    name = SELF_NAME if own else safe_name(item.get("sender_name"), wxid) if wxid else None
    millis = str(stamp * 1000)
    row = {"message_id": message_id(username, local_id, seq), "conversation_id": conversation_id(username), "sender_id": sid,
           "timestamp": millis, "server_time": millis, "message_type": mtype, "status": 2 if own else 4, "body_state": None,
           "body": body}
    return row, ((sid, str(name)) if sid and name else None)


def trace(row: dict) -> dict:
    """Dấu vết đủ để so một dòng với bản đã ghi: chữ ký (loại, chữ, người gửi, đã xóa, ảnh nào) và các trường cần cho dòng xóa.
    `media` là danh sách mã ảnh của bản đã ghi, để biết tin ảnh đã có ảnh chưa và ảnh mới có khác không."""
    media = [digest for digest in (row.get("media") or []) if isinstance(digest, str)]
    body = json.dumps([row.get("message_type"), row.get("body"), row.get("sender_id"), bool(row.get("deleted")), media],
                      ensure_ascii=False, sort_keys=True)
    return {"sig": sha(body), "deleted": bool(row.get("deleted")), "media": media, "sender_id": row.get("sender_id"),
            "message_type": row.get("message_type"), "status": row.get("status")}


def quality(data: bytes) -> tuple[bool, int] | None:
    """(ảnh trọn, số điểm ảnh) để so hai bản của cùng một ảnh: bản trọn thắng bản tải dở, rồi bản nhiều điểm ảnh thắng. None khi
    không đọc được kích thước. Trọn: JPEG có `FF D9` trong 64 byte cuối, PNG có khối IEND trong 16 byte cuối, GIF kết thúc `3B`
    (bỏ đệm 0), WEBP đủ độ dài ghi ở đầu RIFF; như `_image_complete` của upstream, vì file đang tải dở vẫn đọc được kích thước."""
    count = pixels(data)
    if count is None:
        return None
    if data[:3] == b"\xff\xd8\xff":
        whole = b"\xff\xd9" in data[-64:]
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        whole = b"IEND" in data[-16:]
    elif data[:4] == b"GIF8":
        whole = data.rstrip(b"\x00")[-1:] == b"\x3b"
    else:
        whole = len(data) >= struct.unpack("<I", data[4:8])[0] + 8
    return whole, count


def pixels(data: bytes) -> int | None:
    """Số điểm ảnh (rộng × cao) đọc từ phần đầu file JPEG, PNG, GIF hoặc WEBP; None khi không đọc được."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return width * height
    if data[:4] == b"GIF8" and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return width * height
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            return (1 + int.from_bytes(data[24:27], "little")) * (1 + int.from_bytes(data[27:30], "little"))
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            return (int.from_bytes(data[26:28], "little") & 0x3FFF) * (int.from_bytes(data[28:30], "little") & 0x3FFF)
        if chunk == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            return ((bits & 0x3FFF) + 1) * (((bits >> 14) & 0x3FFF) + 1)
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF or marker == 0x01 or 0xD0 <= marker <= 0xD8:   # đệm và mốc không có độ dài
            i += 1 if marker == 0xFF else 2
            continue
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):   # SOF: cao, rộng nằm sau 1 byte độ chính xác
            if i + 9 > len(data):
                return None
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width * height
        i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


class Selection:
    """`wechat-groups.json`: {"schema": 1, "groups": [{"username": "…@chatroom", "name": "…"}]}, ngoài repo, chỉ nhóm người dùng chọn."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.error: str | None = None   # `groups_corrupt` khi file có mà không đọc được ở lần `groups()` gần nhất
        self.good: dict[str, str] = {}  # danh sách đọc được lần cuối: file hỏng thì vẫn đọc nhóm này, không rơi về "chưa chọn nhóm nào"

    def groups(self) -> dict[str, str]:
        """Thiếu file là chưa chọn nhóm nào (hợp lệ, `{}`). File có mà hỏng (JSON dở, sai khuôn) thì KHÔNG phải "chưa chọn": giữ danh
        sách đọc được lần cuối và đặt `error` (23/11/2026: trước đây file hỏng làm WeChat ngừng đọc im lặng, status vẫn xanh)."""
        missing = object()
        document = read_json(self.path, missing)
        if document is missing and not self.path.exists():
            self.error, self.good = None, {}
            return {}
        if not isinstance(document, dict) or not isinstance(document.get("groups", []), list):
            self.error = "groups_corrupt"
            return dict(self.good)
        self.error = None
        self.good = {g["username"]: g.get("name") or "" for g in document.get("groups", [])
                     if isinstance(g, dict) and isinstance(g.get("username"), str) and g["username"].endswith("@chatroom")}
        return dict(self.good)

    def save(self, groups: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp-{os.getpid()}")
        tmp.write_bytes(wb.dump({"schema": 1, "groups": [{"username": u, "name": n} for u, n in sorted(groups.items())]}))
        retry_io(lambda: os.replace(tmp, self.path))


class IndexCorrupt(Exception):
    """`media.json` hay `users.json` của kho có mà không đọc được. `code` là mã lỗi của status."""

    def __init__(self, name: str):
        super().__init__(name)
        self.code = f"{name.split('.')[0]}_index_corrupt"


def load_index(path: Path) -> dict:
    """Chỉ mục JSON của kho: thiếu file là `{}` (chưa có gì); có file mà hỏng thì ném `IndexCorrupt`, KHÔNG trả `{}` (ghi đè bằng phần
    mới sẽ làm mất chỉ mục ảnh/tên cũ). Lỗi đọc tạm (OSError) ném nguyên để vòng sau thử lại."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return {}
    try:
        value = json.loads(data)
    except ValueError:
        raise IndexCorrupt(path.name) from None
    if not isinstance(value, dict):
        raise IndexCorrupt(path.name)
    return value


class Store:
    """Kho cục bộ `<root>/wechat/`: `log.jsonl` (chỉ nối thêm, bản cuối của mỗi mã tin thắng), `users.json`, `media.json`, `media/`."""

    def __init__(self, root: Path, selection: Selection):
        self.dir, self.selection = Path(root), selection
        self.log, self.users_path, self.media_path = self.dir / "log.jsonl", self.dir / "users.json", self.dir / "media.json"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.checked: dict[Path, tuple[int, int]] = {}   # chỉ mục đã kiểm hợp lệ: (mtime_ns, byte), đổi mới kiểm lại
        (self.dir / "media").mkdir(exist_ok=True)
        if self.log.is_file():   # lượt chết giữa chừng có thể để dòng dở: cắt về dòng trọn cuối cùng
            data = self.log.read_bytes()
            if data and not data.endswith(b"\n"):
                with self.log.open("r+b") as stream:
                    stream.truncate(data.rfind(b"\n") + 1)

    def conversation_ids(self) -> list[str]:
        return sorted(conversation_id(username) for username in self.selection.groups())

    def size(self) -> int:
        return self.log.stat().st_size if self.log.is_file() else 0

    def check_indexes(self) -> None:
        """Ném `IndexCorrupt` khi `media.json` hay `users.json` có mà hỏng. Gọi trước mỗi lượt nhập: chỉ mục hỏng thì không nhập gì (con
        trỏ không tiến, không ghi đè), lỗi báo ra status tới khi người dùng khôi phục file. Chỉ đọc lại file khi mtime/kích thước đổi."""
        for path in (self.media_path, self.users_path):
            try:
                stat = path.stat()
            except FileNotFoundError:
                self.checked.pop(path, None)
                continue
            signature = (stat.st_mtime_ns, stat.st_size)
            if self.checked.get(path) != signature:
                load_index(path)
                self.checked[path] = signature

    def append(self, rows: list[dict], users: dict[str, str], media: dict[str, dict]) -> None:
        known_media = load_index(self.media_path) if media else {}   # đọc cả hai TRƯỚC khi ghi gì: một cái hỏng thì không ghi cái nào
        known_users = load_index(self.users_path) if users else {}
        if media:
            wb.write_atomic(self.media_path, wb.dump({**known_media, **media}))
        if users:
            wb.write_atomic(self.users_path, wb.dump({**{key: safe_name(name) for key, name in known_users.items()}, **users}))
        if rows:
            with self.log.open("ab") as stream:
                stream.write(b"".join(wb.dump(row) + b"\n" for row in rows))
                stream.flush()
                os.fsync(stream.fileno())

    def recent(self, since: float) -> dict[str, tuple[str, str]]:
        """Mã tin → (ngày VN, conversation_id) của tin trong log có giờ từ `since` (giây); bản cuối của mỗi mã thắng. Quét một lần."""
        out: dict[str, tuple[str, str]] = {}
        if not self.log.is_file():
            return out
        for raw in self.log.read_bytes().splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            stamp = seconds(row.get("timestamp")) if isinstance(row, dict) else None
            if stamp is not None and stamp >= since and isinstance(row.get("message_id"), str) and isinstance(row.get("conversation_id"), str):
                out[row["message_id"]] = (day_of(stamp), row["conversation_id"])
        return out

    def media_quality(self, digest: str) -> tuple[bool, int] | None:
        """`quality` của một ảnh đã lưu trong `media/` (None: không có file, hoặc không đọc được kích thước)."""
        for extension in sorted(set(wb.EXTENSIONS.values())):
            path = self.dir / "media" / (digest + extension)
            if path.is_file():
                try:
                    return quality(path.read_bytes())
                except OSError:
                    return None
        return None

    def store_image(self, data: bytes) -> tuple[str, dict] | None:
        mime = wb.sniff(data)
        if mime not in wb.EXTENSIONS:
            return None
        digest = hashlib.sha256(data).hexdigest()
        target = self.dir / "media" / (digest + wb.EXTENSIONS[mime])
        if not target.is_file():
            wb.write_atomic(target, data)
        return digest, {"mime": mime, "bytes": len(data), "width": None, "height": None}

    def rows_after(self, offset: int, chosen: set[str] | None = None) -> tuple[list[dict], int]:
        """Tin của nhóm đang chọn nằm sau `offset` (bản cuối của mỗi mã tin thắng) và vị trí mới. Nhóm đã bỏ chọn không lọt.
        `chosen` (tập `conversation_id`) cho người gọi đọc danh sách nhóm đúng một lần."""
        if not self.log.is_file():
            return [], 0
        with self.log.open("rb") as stream:
            stream.seek(offset)
            data = stream.read()
        data = data[:data.rfind(b"\n") + 1]
        chosen = set(self.conversation_ids()) if chosen is None else chosen
        latest: dict[str, dict] = {}
        for raw in data.splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and row.get("conversation_id") in chosen and isinstance(row.get("message_id"), str):
                latest[row["message_id"]] = row
        return list(latest.values()), offset + len(data)

    def known(self) -> dict[str, dict]:
        """Mã tin → dấu vết của bản cuối trong log, để nhận ra tin đã đổi (cửa sổ đọc lại) mà không phát dòng trùng."""
        out: dict[str, dict] = {}
        if not self.log.is_file():
            return out
        for raw in self.log.read_bytes().splitlines():
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("message_id"), str):
                out[row["message_id"]] = trace(row)
        return out

    @staticmethod
    def adopt(rows: list[dict], self_user: object) -> list[dict]:
        """Tin chính chủ gửi từ WeChat mang mã người gửi của chủ tài khoản Zalo (`users.json.self_user`, thứ duy nhất hao dùng để
        nhận ra chủ): cùng một người nên căn lề và tên đúng."""
        if not isinstance(self_user, str) or not self_user:
            return rows
        return [{**row, "sender_id": self_user} if row.get("sender_id") == SELF_ID else row for row in rows]

    def users_for(self, rows: list[dict]) -> dict[str, str]:
        known = read_json(self.users_path, {}) or {}
        # tên mã thô còn sót từ bản cũ chỉ ở máy: không bao giờ vào gói
        return {row["sender_id"]: safe_name(known[row["sender_id"]]) for row in rows if row.get("sender_id") in known}

    def media_for(self, rows: list[dict], out: Path) -> dict[str, dict]:
        """Chép ảnh của các dòng vào `out/media` (nếu thiếu) và trả mục `media.json` của chúng."""
        known = read_json(self.media_path, {}) or {}
        items = {}
        (out / "media").mkdir(parents=True, exist_ok=True)
        for row in rows:
            for digest in row.get("media") or []:
                item = known.get(digest)
                if not item:
                    continue
                name = digest + wb.EXTENSIONS[item["mime"]]
                if not (out / "media" / name).is_file() and (self.dir / "media" / name).is_file():
                    wb.write_atomic(out / "media" / name, (self.dir / "media" / name).read_bytes())
                items[digest] = item
        return items

    def merge_into(self, data_dir: Path, out: Path) -> dict:
        """Dựng đầy đủ xong: thêm nhóm, người gửi, tin và ảnh WeChat vào thư mục dữ liệu mới, tính lại `bundle_sha256`."""
        groups = self.selection.groups()   # đọc một lần: `wechat-remove` giữa chừng không làm lệch tập nhóm
        count = dict.fromkeys((conversation_id(username) for username in groups), 0)
        users = read_json(data_dir / "users.json", {"self_user": None, "users": {}}) or {}
        rows, offset = self.rows_after(0, set(count))
        rows = self.adopt(rows, users.get("self_user"))
        for row in rows:
            count[row["conversation_id"]] += 1
        conversations = read_json(data_dir / "conversations.json", []) or []
        have = {c.get("conversation_id") for c in conversations if isinstance(c, dict)}
        extra = [{"conversation_id": conversation_id(u), "display_name": f"WeChat · {name or u[:8]}", "name_status": "name_index",
                  "is_group": True, "participant_ids": [], "message_count": count[conversation_id(u)]}
                 for u, name in sorted(groups.items()) if conversation_id(u) not in have]
        users["users"] ={**(users.get("users") or {}), **self.users_for(rows)}
        media = read_json(data_dir / "media.json", {}) or {}
        media.update(self.media_for(rows, out))
        wb.write_atomic(data_dir / "conversations.json", wb.dump(conversations + extra))
        wb.write_atomic(data_dir / "users.json", wb.dump(users))
        wb.write_atomic(data_dir / "media.json", wb.dump(media))
        if rows:
            with (data_dir / "messages.jsonl").open("ab") as stream:
                stream.write(b"".join(wb.dump(row) + b"\n" for row in rows))
        digest = hashlib.sha256()
        for name in ("conversations.json", "users.json", "messages.jsonl", "media.json"):
            digest.update((data_dir / name).read_bytes())
        return {"bytes": offset, "messages": len(rows), "conversations": len(extra), "media": len(media), "sha256": digest.hexdigest()}


def run_child(python: str, pilot: str, command: str, request: dict, timeout: float = TIMEOUT, script: Path = SCRIPT) -> tuple[int, str]:
    done = subprocess.run([python, "-X", "utf8", "-I", str(script), "--pilot", pilot, command], input=json.dumps(request).encode(),
                          capture_output=True, timeout=timeout, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return done.returncode, done.stdout.decode("utf-8", "replace")


def parse(output: str) -> list[dict]:
    items = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            items.append(item)
    return items


class Session:
    """Tiến trình con SỐNG LÂU cho lệnh `read` (`wechat_export serve`): giữ `WeChatDB` mở nên chỉ lấy khóa một lần (mở DB mỗi 10
    giây làm upstream quét bộ nhớ Weixin.exe mỗi lần). Mỗi yêu cầu một dòng JSON, trả về tới dòng `end` hoặc `error`; quá `timeout`
    thì giết và tạo lại (ném `TimeoutExpired`), tiến trình chết giữa chừng thì tạo lại ở yêu cầu sau. Gọi từ luồng nền của bộ xử lý
    nên chờ ở đây không bao giờ giữ vòng lặp của `bundle`. Lệnh khác (`groups`) vẫn chạy một lần bằng `run_child`.
    Có cùng chữ ký với `run_child`: `(python, pilot, command, request, timeout) -> (mã thoát, đầu ra)`."""

    def __init__(self, script: Path = SCRIPT, popen=subprocess.Popen):
        self.script, self.popen = script, popen
        self.proc = None
        self.lines: queue.Queue | None = None
        self.key = None

    def start(self, python: str, pilot: str) -> None:
        self.stop()
        self.proc = self.popen([python, "-X", "utf8", "-I", str(self.script), "--pilot", pilot, "serve"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.lines, self.key = queue.Queue(), (python, pilot)
        threading.Thread(target=self.pump, args=(self.proc, self.lines), daemon=True, name="wechat-export-reader").start()

    @staticmethod
    def pump(proc, lines: queue.Queue) -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        except (OSError, ValueError):
            pass
        lines.put(None)   # EOF: tiến trình đã chết

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is not None:
            with contextlib.suppress(OSError):
                proc.kill()
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                proc.wait(5)
            for stream in (proc.stdin, proc.stdout):   # đóng ống để luồng đọc thấy EOF và không rò tay cầm
                with contextlib.suppress(OSError, ValueError):
                    stream.close()

    def __call__(self, python: str, pilot: str, command: str, request: dict, timeout: float = TIMEOUT) -> tuple[int, str]:
        if command != "read":
            return run_child(python, pilot, command, request, timeout)
        if self.proc is None or self.proc.poll() is not None or self.key != (python, pilot):
            self.start(python, pilot)
        deadline, out = time.monotonic() + timeout, []
        try:
            self.proc.stdin.write(json.dumps(request) + "\n")
            self.proc.stdin.flush()
        except OSError:
            self.stop()
            raise
        while True:
            try:
                line = self.lines.get(timeout=max(0.0, deadline - time.monotonic()))
            except queue.Empty:
                self.stop()
                raise subprocess.TimeoutExpired("wechat_export", timeout) from None
            if line is None:
                self.stop()
                return 1, "".join(out)
            out.append(line)
            kind = (parse(line) or [{}])[0].get("kind")
            if kind in ("end", "error"):
                return (2 if kind == "error" else 0), "".join(out)


class WeChatProcessor:
    name = NAME

    def __init__(self, store: Store, state: Path, *, python: str, pilot: str, interval: float = INTERVAL, first_limit: int = 5000,
                 images: bool = False, run=run_child, clock=time.time, dry_run: bool = False, background: bool = True,
                 recheck_hours: float = RECHECK_HOURS, app=None):
        self.store, self.state, self.python, self.pilot = store, Path(state), python, pilot
        self.app_state = app or wechat_app.state   # app WeChat có chạy, có đăng nhập không (đọc DB vẫn được khi WeChat tắt)
        self.app: tuple[str, str] | None = None     # (mã, lúc bắt đầu giữ mã đó)
        self.app_checked: float | None = None
        self.keys: tuple[str, str] | None = None    # khóa ảnh: ("ok" | "no_key", lúc bắt đầu), chỉ khi bật ảnh
        self.interval, self.first_limit, self.images, self.recheck_hours = interval, first_limit, images, recheck_hours
        self.fps: dict[tuple, tuple[str, int]] = {}   # (nhóm, local_id, sort_seq) → (dấu vân tay, giờ tin): cửa sổ chỉ gửi nội dung khi khác
        self.retry_at: dict[tuple, float] = {}        # tin có ảnh thu nhỏ → lúc quên `fp` để tiến trình con giải lại tìm bản lớn hơn
        self.deep_pending = True                      # lượt đọc thành công đầu tiên CÓ KHÓA của tiến trình này kèm lượt thử lại ảnh 7 ngày
        self.deep_sent = False
        self.deep_failures = 0
        self.appended = 0                             # số dòng THẬT SỰ ghi ở lượt nhập gần nhất
        self.names: dict[str, str] | None = None   # users.json của kho; nạp lười, cập nhật khi ghi
        self.known: dict[str, dict] | None = None   # dấu vết bản cuối của mỗi mã tin trong log; nạp lười ở lượt nhập đầu
        self.run, self.clock, self.dry_run, self.background = run, clock, dry_run, background
        saved = read_json(self.state / f"{NAME}.json", {}) or {}
        self.cursors: dict = saved.get("groups") if isinstance(saved.get("groups"), dict) else {}
        self.total = saved.get("messages") if isinstance(saved.get("messages"), int) else 0
        # Kho đã có tin ghi theo cách tìm người gửi cũ: lượt đọc thành công đầu tiên đọc lại cả nhóm để sửa người gửi, rồi thôi.
        rule = saved.get("sender_rule")
        self.sender_rule = rule if isinstance(rule, int) else (SENDER_RULE if not self.cursors else 0)
        self.resend_sent = False
        self.resend_failures = 0
        self.next_at = 0.0
        self.failures = 0
        self.thread: threading.Thread | None = None
        self.outcome: tuple[str | None, list[dict], dict] | None = None
        # Sức khỏe đọc tin (status.json, canh WeChat ngừng đọc): lúc lượt đọc THÀNH CÔNG gần nhất (đọc được và nhập xong, không phải
        # nhịp tim) và giờ của tin mới nhất từng thấy. Nhớ trong `<state>` để chạy lại agent không mất.
        self.started_at = self.clock()   # lúc (chạy lại / dậy) gần nhất: lượt đọc đầu chưa xong thì máy canh chưa được coi giờ đọc cũ là "im"
        self.last_step: float | None = None
        self.read_ok = number(saved.get("read_ok_at"))
        self.newest = saved.get("newest") if isinstance(saved.get("newest"), int) and not isinstance(saved.get("newest"), bool) else None
        self.recent: dict[str, tuple[str, str, float]] | None = None   # tin ba ngày gần nhất: mã → (ngày VN, nhóm, lúc vào kho); nạp lười
        self.daily_at: tuple[float, dict[str, int]] | None = None
        self.last = {"action": "idle", "revision": None, "error": None, "messages": self.total}

    def wants_work(self) -> bool:
        return False   # đọc theo nhịp riêng, không giữ vòng lặp gom 3 giây của bundle; `bundle` tự thấy log dài ra

    def request(self, groups: dict[str, str]) -> dict:
        images = str(self.store.dir / "incoming") if self.images else None
        if images:
            Path(images).mkdir(exist_ok=True)
        now = self.clock()
        # Đang dở lượt 7 ngày (hết giờ giải ảnh ở lượt trước) thì nhớ `fp` theo cả 7 ngày, để lượt sau không giải lại phần đã xong.
        span = max(self.recheck_hours, DEEP_IMAGE_HOURS) if self.images and self.deep_pending else self.recheck_hours
        floor = now - (span + 1) * 3600
        self.fps = {key: value for key, value in self.fps.items() if value[1] >= floor and self.retry_at.get(key, now + 1) > now}
        self.retry_at = {key: at for key, at in self.retry_at.items() if key in self.fps}
        known: dict[str, dict] = {}
        for (username, local_id, seq), (fp, _) in self.fps.items():
            if username in groups:
                known.setdefault(username, {})[f"{local_id}:{seq}"] = fp
        # Lượt sửa người gửi đi trước và không bao giờ chung yêu cầu với lượt ảnh 7 ngày: hai lượt nặng chung một ngân sách giải ảnh
        # thì lượt 7 ngày bị cắt (ảnh hết giờ vẫn được phát để sửa người gửi, rồi bị coi như đã xong). Lượt 7 ngày chạy ngay sau.
        self.resend_sent = self.sender_rule < SENDER_RULE and self.resend_failures < RESEND_TRIES
        self.deep_sent = bool(images) and self.deep_pending and not self.resend_sent
        return {"groups": {u: self.cursors.get(u) or {} for u in groups}, "first_limit": self.first_limit, "images_dir": images,
                "window_hours": self.recheck_hours, "deep_image_hours": DEEP_IMAGE_HOURS if self.deep_sent else 0, "known_fp": known,
                "resend_hours": RESEND_HOURS if self.resend_sent else 0}

    def poll(self, groups: dict[str, str]) -> tuple[str | None, list[dict], dict]:
        """Chạy tiến trình con (có thể ở luồng nền). Trả (mã lỗi, các dòng tin, dòng `end`)."""
        try:
            code, output = self.run(self.python, self.pilot, "read", self.request(groups))
        except subprocess.TimeoutExpired:
            return "child_timeout", [], {}
        except OSError:
            return "child_missing", [], {}
        items = parse(output)
        end = next((item for item in items if item.get("kind") == "end"), None)
        if code != 0 or end is None:
            return ("child_failed" if code != 0 else "child_output"), [], {}
        return None, [item for item in items if item.get("kind") == "message" and item.get("username") in groups], end

    def work(self, groups: dict[str, str]) -> None:
        try:
            self.outcome = self.poll(groups)
        except Exception:  # noqa: BLE001  (luồng đọc chết vì lỗi lạ: báo mã, vòng sau dựng luồng mới, không im lặng vĩnh viễn)
            self.outcome = ("thread_died", [], {})

    def step(self) -> dict:
        groups = self.store.selection.groups()
        now = self.clock()
        if self.last_step is not None and now - self.last_step > RESUME_GAP:
            self.started_at = now   # msi ngủ dậy: giờ đọc cũ trong `<state>` chưa nói được gì tới khi lượt đọc đầu xong
        self.last_step = now
        # Hỏi luồng đã thoát chưa TRƯỚC khi đọc `outcome`: luồng thoát thì `outcome` (nếu có) đã được đặt xong, nên không báo `thread_died` nhầm
        # khi luồng vừa trả kết quả giữa hai câu hỏi.
        dead = self.thread is not None and not self.thread.is_alive()
        outcome = self.outcome
        if outcome is not None:
            error, items, end = outcome
            self.outcome, self.thread = None, None
            self.apply(error, items, end, groups)
        elif dead:
            # Luồng đã thoát mà không để lại kết quả (bị giết, lỗi ngoài `Exception`): trước đây `self.thread` không bao giờ về None nên
            # không đọc lại nữa mà status vẫn xanh. Giết tiến trình con (nếu có) để lượt sau dựng lại từ đầu.
            self.thread = None
            getattr(self.run, "stop", lambda: None)()
            self.apply("thread_died", [], {}, groups)
        elif self.thread is None and groups and self.clock() >= self.next_at:
            self.next_at = self.clock() + self.interval
            if self.background:
                self.thread = threading.Thread(target=self.work, args=(groups,), daemon=True, name="wechat-export")
                self.thread.start()
            else:
                self.work(groups)
                return self.step()
        result = self.last
        self.last = {**result, "action": "idle"}   # kết quả một lần: vòng lặp gọi step mỗi giây, đừng ghi log "poll" mãi
        if self.store.selection.error:   # file nhóm hỏng: gốc của việc ngừng đọc, báo trước mọi lỗi khác
            result = {**result, "error": self.store.selection.error}
        return {**result, **self.app_fields(), **self.health_fields(groups)}

    def health_fields(self, groups: dict[str, str]) -> dict:
        """Cho `status.json`: số nhóm đang đọc, nhịp đọc (giây), lúc lượt đọc thành công gần nhất, giờ tin mới nhất, và số tin theo ngày
        đã vào kho (`daily`) để máy canh trên hao so với gói. Chỉ số và giờ, không chữ tự do."""
        out: dict = {"groups": len(groups), "read_every": max(1, int(self.interval)), "started_at": now_iso(self.started_at)}
        if self.read_ok is not None:
            out["read_ok_at"] = now_iso(self.read_ok)
        if self.newest is not None:
            out["newest_at"] = now_iso(self.newest)
        daily = self.daily(groups)
        if daily:
            out["daily"] = daily
        return out

    def daily(self, groups: dict[str, str]) -> dict[str, int]:
        """Số tin (mã khác nhau) của nhóm đang chọn theo ngày VN trong `DAILY_DAYS` ngày gần nhất, chỉ tin đã vào kho quá `SETTLE` giây:
        tin vừa tới chưa kịp lên gói không tính là lệch. Tính lại mỗi phút."""
        now = self.clock()
        if self.daily_at is not None and 0 <= now - self.daily_at[0] < 60:
            return self.daily_at[1]
        days = {day_of(now - n * 86400) for n in range(DAILY_DAYS)}
        self.ensure_recent()
        self.recent = {mid: value for mid, value in self.recent.items() if value[0] in days}
        chosen = {conversation_id(username) for username in groups}
        counts: dict[str, int] = {}
        for day, cid, at in self.recent.values():
            if cid in chosen and at <= now - SETTLE:
                counts[day] = counts.get(day, 0) + 1
        self.daily_at = (now, counts)
        return counts

    def app_fields(self) -> dict:
        """`app` (wechat_app.STATES) và `images` ("ok" | "no_key"), mỗi cái kèm `…_since`, cho `status.json` và máy canh. App kiểm
        mỗi `APP_EVERY` giây (đọc danh sách tiến trình và cửa sổ khoảng 25 ms); mốc nhớ trong `<state>` nên chạy lại agent không mất."""
        now = self.clock()
        if self.app_checked is None or now - self.app_checked >= APP_EVERY:
            self.app_checked = now
            value = self.app_state()
            value = value if value in wechat_app.STATES else wechat_app.UNKNOWN
            self.app = (value, track_value(self.state, "wechat-app", value, now, persist=not self.dry_run))
        out = {"app": self.app[0], "app_since": self.app[1]}
        if self.images and self.keys:
            out.update(images=self.keys[0], images_since=self.keys[1])
        return out

    def apply(self, error: str | None, items: list[dict], end: dict, groups: dict[str, str]) -> None:
        now = self.clock()
        end = end or {}
        if error is None:
            try:
                self.store.check_indexes()
                error = self.ingest(items, groups)
                # Đã đọc lại và sửa người gửi của tin cũ ở MỌI nhóm (nhóm vắng mặt lúc đọc thì chưa): lần sau đọc như thường.
                if error is None and self.resend_sent and not end.get("missing_groups"):
                    self.sender_rule = SENDER_RULE
                    self.save()
            except IndexCorrupt as exc:   # chỉ mục hỏng: không nhập, không ghi đè, báo mã
                error = exc.code
            except OSError:
                error = "store_failed"
            except Exception:  # noqa: BLE001  (dòng tin lạ làm `ingest` ném: báo mã, không để lỗi lan ra vòng lặp và không im lặng)
                error = "ingest_failed"
        self.failures = self.failures + 1 if error else 0
        if not error and self.images:   # lượt đọc thành công cho biết tiến trình con có suy được khóa ảnh không
            value = "ok" if end.get("image_keys") else "no_key"
            self.keys = (value, track_value(self.state, "wechat-images", value, now, persist=not self.dry_run))
        if error:
            self.next_at = now + min(MAX_BACKOFF, self.interval * 2 ** self.failures)
            if self.deep_sent and error == "child_timeout":   # chỉ quá giờ mới có thể do lượt 7 ngày quá nặng
                self.deep_failures += 1
                self.deep_pending = self.deep_failures < DEEP_TRIES   # quá giờ hai lần thì bỏ lượt 7 ngày, đọc tin như thường
            if self.resend_sent and error == "child_timeout":   # như lượt 7 ngày: quá giờ hai lần thì thôi, lần chạy agent sau thử lại
                self.resend_failures += 1
        elif self.deep_sent and end.get("image_keys"):
            # Lượt 7 ngày đã chạy có khóa. Hết giờ giải ảnh mà vẫn giải được ảnh thì làm tiếp ở lượt sau (phần đã xong được nhớ `fp`);
            # không giải thêm được ảnh nào thì thôi, để ảnh không bao giờ tải về không giữ lượt này mãi.
            self.deep_pending = bool(end.get("image_budget_hit")) and end.get("images", 0) > 0
        # "poll" (và thay đổi trạng thái) chỉ khi có dòng THẬT SỰ được ghi: cửa sổ đọc lại không làm log và đẩy status mỗi lượt
        self.last = {"action": "poll" if not error and self.appended else "idle", "revision": None, "error": error, "messages": self.total}

    def ingest(self, items: list[dict], groups: dict[str, str]) -> str | None:
        if self.known is None:
            self.known = self.store.known()
        self.ensure_recent()
        rows, users, media, moved, staged, seen_fp = [], {}, {}, {}, {}, {}   # staged: dấu vết chỉ nhớ sau khi nối log thành công
        retry: dict[tuple, float | None] = {}
        newest = self.newest or 0
        for item in items:
            if item.get("username") not in groups:   # nhóm vừa bỏ chọn giữa lượt đọc nền: không nhập, không trả con trỏ
                continue
            created = item.get("create_time")
            if isinstance(created, int) and not isinstance(created, bool) and created > newest:
                newest = created
            photo = item.get("type") == "图片"
            data = self.read_image(item["image"]) if item.get("image") and self.images else None
            image = None   # (mã sha256, dữ liệu, (trọn, số điểm ảnh) | None) khi file là ảnh dùng được; CHƯA lưu (chỉ lưu khi dùng)
            if data is not None and wb.sniff(data) in IMAGE_MIMES:
                image = (hashlib.sha256(data).hexdigest(), data, quality(data))
            unusable = data is not None and image is None   # giải ra mà không dùng được (wxgf, HEIC…): thôi thử; đọc lỗi thì thử lại
            converted = convert(item, image[0] if image else None)
            if converted is None:
                continue
            row, user = converted
            window = bool(item.get("window"))
            prior = staged.get(row["message_id"]) or self.known.get(row["message_id"])
            if item.get("deep") and prior is None:
                continue   # lượt ảnh 7 ngày chỉ thử lại/nâng ảnh cho tin đã có; tin lần đọc đầu đã cố ý bỏ thì không nhập
            had = list((prior or {}).get("media") or [])
            had_quality = self.store.media_quality(had[0]) if photo and had and self.images else None
            if photo and image and had:   # đã có ảnh: chỉ thay bằng bản TỐT HƠN (dở → trọn, thu nhỏ → nén/gốc), không bao giờ lùi
                if image[0] in had or image[2] is None:
                    accepted = False
                elif had_quality is None:   # bản đang có không đọc được cỡ (mất file…): chỉ thay bằng ảnh trọn và đủ lớn
                    accepted = image[2][0] and image[2][1] > THUMB_PIXELS
                else:
                    accepted = image[2] > had_quality
            else:
                accepted = bool(image)
            stored = self.store.store_image(image[1]) if accepted else None
            accepted = stored is not None
            if accepted:
                media[stored[0]] = stored[1]
                row["media"] = [stored[0]]
            elif image is not None:   # có ảnh mà không dùng (trùng, nhỏ hơn, không lưu được): dòng giữ đúng như bản đang có
                row = convert(item, had[0] if had else None)[0]
                if had:
                    row["media"] = had
            final = image[2] if accepted else had_quality
            has_media = accepted or bool(had)
            # Mọi tin đều nhớ `fp`; `retry_at` quyết định lúc quên để tiến trình con giải lại: chưa có ảnh (file `.dat` tải chậm, khóa
            # có muộn, đọc file lỗi) sau 1 phút; ảnh thu nhỏ hay tải dở sau 10 phút; file không dùng được và ảnh trọn đủ lớn thì thôi.
            missing = self.images and photo and not has_media and not unusable
            small = self.images and photo and has_media and final is not None and (not final[0] or final[1] <= THUMB_PIXELS)
            # Tin ngoài cửa sổ 6 giờ chỉ đọc lại để sửa người gửi thì không nhớ `fp`: nhớ thì lượt ảnh 7 ngày ngay sau coi ảnh còn thiếu
            # của nó là đã xong và không thử lại.
            if isinstance(item.get("fp"), str) and not (item.get("resend") and item.get("deep")):
                key = (item["username"], item["local_id"], item["sort_seq"])
                seen_fp[key] = (item["fp"], item["create_time"])
                retry[key] = self.clock() + (MISSING_RETRY if missing else SMALL_RETRY) if missing or small else None
            keep_media = False
            if photo and prior is not None and not accepted:
                if item.get("resend") and prior["sender_id"] != row["sender_id"]:
                    row = convert(item, had[0] if had else None)[0]   # chỉ sửa người gửi: ảnh giữ như bản đang có
                    if had:
                        row["media"] = had
                elif window:
                    continue   # không có gì tốt hơn bản đang có: không ghi đè, không phát lại
                else:
                    keep_media = bool(had)   # đọc lại (con trỏ mất) lúc không có khóa / chỉ có bản kém hơn: giữ ảnh đang có, con trỏ vẫn tiến
            if window and prior is not None:
                # Cửa sổ đọc lại: chỉ phát khi dòng đã đổi. WeChat thu hồi bằng cách biến dòng cũ thành tin hệ thống: dòng đó
                # trở thành dòng xóa (giữ người gửi, loại tin cũ) và không bao giờ bị tin hệ thống ghi đè lại.
                if prior["deleted"]:
                    continue
                if item.get("revoked") and prior["message_type"] != -4:
                    row = {**row, "sender_id": prior["sender_id"], "message_type": prior["message_type"], "status": prior["status"],
                           "body": None, "deleted": True}
                    row.pop("media", None)
            duplicate = prior is not None and (prior["sig"] == trace(row)["sig"] or keep_media)
            if not duplicate:
                rows.append(row)
                staged[row["message_id"]] = trace(row)
            if user:   # tên theo bản MỚI NHẤT, kể cả khi dòng không đổi (biệt danh có sau); chỉ ghi khi khác bản đã lưu
                self.names = self.names if self.names is not None else read_json(self.store.users_path, {}) or {}
                have = users.get(user[0]) or self.names.get(user[0])
                if user[1] != have and not (user[1] == MEMBER_NAME and have):   # không để "Thành viên WeChat" đè tên thật đã biết
                    users[user[0]] = user[1]
            if window:
                continue   # tin cũ đọc lại không đẩy con trỏ
            username, seq, local_id = item["username"], item["sort_seq"], item["local_id"]
            old = moved.get(username) or self.cursors.get(username) or {}
            tail = (old.get("tail") or []) if old.get("sort_seq") == seq else []
            if not isinstance(old.get("sort_seq"), int) or seq >= old["sort_seq"]:
                moved[username] = {"sort_seq": seq, "tail": [*tail, local_id]}
        self.store.append(rows, users, media)
        self.known.update(staged)
        self.names = {**(self.names or {}), **users}
        self.fps.update(seen_fp)
        for key, at in retry.items():
            if at is None:
                self.retry_at.pop(key, None)
            else:
                self.retry_at[key] = at
        self.appended = len(rows)
        self.remember_recent(rows)
        self.newest = newest or self.newest
        self.read_ok = self.clock()   # tới đây lượt đọc đã THÀNH CÔNG (đọc được, nhập xong): không phải nhịp tim
        self.cursors = {**{u: c for u, c in self.cursors.items() if u in groups}, **{u: c for u, c in moved.items() if u in groups}}
        self.total = len(self.known)   # số TIN khác nhau trong kho (tab Máy chạy), không đếm lần ghi lại một tin (ảnh, người gửi, thu hồi)
        self.save()
        return None

    def ensure_recent(self) -> None:
        """Nạp tin ba ngày gần nhất từ log, tính như vào kho lúc khởi động (tin vừa ghi trước khi tắt chưa chắc đã lên gói: chờ đủ `SETTLE`
        mới đưa vào số đếm). Gọi trước khi nối tin mới, để tin mới không bị tính là cũ."""
        if self.recent is None:
            self.recent = {mid: (day, cid, self.started_at) for mid, (day, cid) in self.store.recent(self.clock() - (DAILY_DAYS + 1) * 86400).items()}

    def remember_recent(self, rows: list[dict]) -> None:
        """Tin vừa ghi vào kho nhập vào số đếm theo ngày với lúc vào kho (mã đã có giữ lúc cũ: đã quá `SETTLE` thì không bị đếm lại)."""
        now = self.clock()
        for row in rows:
            stamp = seconds(row.get("timestamp"))
            if stamp is not None and row["message_id"] not in self.recent:
                self.recent[row["message_id"]] = (day_of(stamp), row["conversation_id"], now)

    def save(self) -> None:
        if not self.dry_run:
            state = {"groups": self.cursors, "messages": self.total, "sender_rule": self.sender_rule}
            if self.read_ok is not None:
                state["read_ok_at"] = self.read_ok
            if self.newest is not None:
                state["newest"] = self.newest
            cursors.save(self.state, NAME, state, self.clock())

    def read_image(self, name: str) -> bytes | None:
        """Byte của file tiến trình con vừa giải ra trong `incoming/` (đọc xong là xóa); None khi không đọc được. Xóa lỗi (phần mềm
        diệt virus đang giữ file…) không làm mất ảnh đã đọc."""
        path = self.store.dir / "incoming" / Path(name).name
        try:
            data = path.read_bytes()
        except OSError:
            return None
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)
        return data


# ---- lệnh chọn nhóm: `zalo_agent wechat-list | wechat-add <tên> | wechat-remove <tên>` ----

def list_groups(python: str, pilot: str, run=run_child) -> list[dict]:
    code, output = run(python, pilot, "groups", {}, 120)
    if code != 0:
        raise RuntimeError("không đọc được danh sách nhóm WeChat (bộ đọc lỗi)")
    return [item for item in parse(output) if item.get("kind") == "group" and isinstance(item.get("username"), str)]


def find(groups: list[dict], needle: str) -> list[dict]:
    needle = needle.strip()
    fold = wb.fold
    exact = [g for g in groups if fold(g.get("name") or "") == fold(needle)]
    return exact or [g for g in groups if fold(needle) in fold(g.get("name") or "") or conversation_id(g["username"]).startswith(needle)]


def cmd_list(selection: Selection, python: str, pilot: str, run=run_child) -> int:
    chosen = selection.groups()
    for group in list_groups(python, pilot, run):
        mark = "[x]" if group["username"] in chosen else "[ ]"
        print(f"{mark} {conversation_id(group['username'])[:8]}  {group.get('members', 0):>4} người  {group.get('name') or 'chưa rõ tên'}")
    print(f"\n{len(chosen)} nhóm WeChat đang được lên web.")
    return 0


def cmd_change(selection: Selection, needles: list[str], add: bool, python: str, pilot: str, run=run_child) -> int:
    chosen = selection.groups()
    pool = list_groups(python, pilot, run) if add else [{"username": u, "name": n} for u, n in chosen.items()]
    for needle in needles:
        matches = find(pool, needle)
        if len(matches) != 1:
            print(f"“{needle}”: {'không thấy nhóm nào' if not matches else f'{len(matches)} nhóm khớp, ghi rõ hơn (8 ký tự đầu mã)'}")
            for group in matches[:10]:
                print(f"    {conversation_id(group['username'])[:8]}  {group.get('name') or 'chưa rõ tên'}")
            return 1
        group = matches[0]
        if add:
            chosen[group["username"]] = group.get("name") or ""
        else:
            chosen.pop(group["username"], None)
        print(f"{'Thêm' if add else 'Bỏ'}: {conversation_id(group['username'])[:8]}  {group.get('name') or 'chưa rõ tên'}")
    selection.save(chosen)
    return 0


def add_arguments(parser) -> None:
    parser.add_argument("--wechat-python", default=os.environ.get("ZALO_WECHAT_PYTHON", r"D:\deibt\wechat-mcp-pilot\.venv\Scripts\python.exe"))
    parser.add_argument("--wechat-pilot", default=os.environ.get("ZALO_WECHAT_PILOT", r"D:\deibt\wechat-mcp-pilot"))
    parser.add_argument("--wechat-groups", default=os.environ.get("ZALO_WECHAT_GROUPS", r"D:\zalo-agent\wechat-groups.json"))


def main_command(args) -> int:
    for stream in (sys.stdout, sys.stderr):   # tên nhóm có chữ Hán: đầu ra qua pipe Windows mặc định cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    selection = Selection(Path(args.wechat_groups))
    try:
        if args.command == "wechat-list":
            return cmd_list(selection, args.wechat_python, args.wechat_pilot)
        return cmd_change(selection, args.needles, args.command == "wechat-add", args.wechat_python, args.wechat_pilot)
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
