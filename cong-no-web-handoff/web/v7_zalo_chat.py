"""ZALO-CHAT-01: đọc bản xuất chat Zalo (JSONL) theo trang cho tab Đòi nợ. Chỉ đọc, stdlib.

Bản xuất nằm ngoài repo (`WEBDEBIT_ZALO_EXPORT_DIR`): `conversations.json` + `messages.jsonl`
(+ `export-report.json`). Từ ZALO-GROUP-01 thư mục đó có thể là **gói web** do
`tools/zalo_web_bundle.py` dựng: `export-report.json` trỏ `data_dir` tới thư mục dữ liệu của lượt
dựng (thêm `users.json` tên người gửi, `media.json`), ảnh nằm ở `media/<sha256>.<đuôi>`; gói đổi
thì lập chỉ mục lại ở luồng nền, trong lúc đó vẫn trả theo chỉ mục cũ.
Khởi động chỉ đọc một lượt để lập chỉ mục offset theo hội thoại;
mỗi yêu cầu đọc đúng các dòng của trang cần trả, không bao giờ nạp cả file vào RAM hay gửi
cả file cho trình duyệt. Không ghi, không sửa file nguồn, không log nội dung tin.

ZALO-AGENT-01: thư mục dữ liệu có thể kèm `messages-delta.jsonl` (chỉ nối thêm: tin thêm/sửa/xóa). `export-report.json`
ghi `delta_bytes` = số byte hợp lệ; chỉ đọc tới đó, nên dòng đang ghi dở không bao giờ được đọc. Bản cuối cùng theo
`message_id` thắng (gói gốc rồi tới phần thêm); dòng `deleted` trong phần thêm hiện như tin `deleted: true` của bản dựng đầy đủ
(giữ chỗ và người gửi, bỏ chữ và ảnh). Báo cáo đổi mà `data_dir` và `bundle_sha256` giữ nguyên thì chỉ đọc tiếp phần thêm và
đọc lại `users.json`, `media.json` (có thể bị thay tại chỗ); không thì lập chỉ mục lại ở luồng nền.

Từ 21/11/2026 mỗi tin trả thêm `card`, `quote` (tin được trích dẫn, cùng hội thoại), `reactions`, `sticker`, `sender_avatar`;
mỗi hội thoại thêm `avatar`. Giá trị sai khuôn thì bỏ; gói cũ không có thì trả rỗng.
"""

from __future__ import annotations

import argparse
import bisect
import contextlib
import hashlib
import io
import json
import math
import os
import re
import sys
import threading
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs

EXPORT_DIR = os.getenv("WEBDEBIT_ZALO_EXPORT_DIR")   # chưa đặt: API trả 503, trang báo chưa cấu hình
DEFAULT_LIMIT = 50
MAX_LIMIT = 100
MAX_PAGE = 100_000
MAX_QUERY = 200
CONVERSATION_ID = re.compile(r"[0-9a-f]{64}")
MESSAGE_ID = re.compile(r"[0-9A-Za-z_-]{1,128}")
MEDIA_ID = re.compile(r"[0-9a-f]{64}")
SINCE_TOKEN = re.compile(r"[0-9a-f]{8}:[0-9]{1,15}")   # <8 ký tự băm của gói>:<byte của phần thêm đã đọc>
DATA_DIR = re.compile(r"data-[0-9-]{1,40}")
MEDIA_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "video/mp4": ".mp4",
                    "audio/aac": ".aac", "audio/amr": ".amr"}
# Nhãn loại tin suy từ bản xuất 30/10/2026 và kho thật 21/11/2026 (msgType của Zalo PC); loại lạ hiện "Loại N".
TYPE_NAMES = {1: "Văn bản", 2: "Ảnh", 3: "Ghi âm", 4: "Sticker", 5: "Ảnh", 6: "Cuộc gọi", 7: "GIF",
              17: "Vị trí", 18: "Video", 19: "Tệp", 20: "Đã thu hồi", 21: "Thẻ liên kết", 25: "Danh thiếp", 26: "Bình chọn",
              27: "Thẻ", 52: "Tin tương tác", -4: "Thông báo nhóm", -27: "Thông báo", -1909: "Tin hệ thống"}
# Mã thẻ do gói ghi theo (msgType, action) (`zalo_web_bundle.CARDS`): đúng hơn nhãn theo loại (loại 6 phần lớn là liên kết).
CARD_NAMES = {"link": "Liên kết", "missed_call": "Cuộc gọi nhỡ", "call": "Cuộc gọi", "contact": "Danh thiếp",
              "poll": "Bình chọn", "bank_card": "Thẻ ngân hàng", "system": "Tin hệ thống"}
MAX_REACTIONS = 20
QUOTE_CHARS = 120
# Trong bản xuất, 100% tin chủ tài khoản gửi có status 2 và tin nhận có status 4; mã khác giữ số.
STATUS_NAMES = {2: "đã gửi", 4: "đã nhận"}
_LOCK = threading.Lock()
_STORE: ChatStore | None = None
_STORE_DIR: str | None = None
_RELOAD: dict = {"running": False}   # luồng nền đang lập chỉ mục gói mới; xong thì để "store" chờ get_store lấy


class ChatError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def unavailable(reason: str) -> ChatError:
    return ChatError(503, "ZALO_EXPORT_UNAVAILABLE", f"Máy chủ chưa có bản xuất chat Zalo: {reason}")


def fold(text: str) -> str:
    """So khớp không phân biệt hoa thường và dấu tiếng Việt ("Hoang" khớp "Hoàng", "đ" khớp "d")."""
    stripped = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


def to_millis(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def body_text(body: object) -> str | None:
    """Chữ đọc được của tin: văn bản giữ nguyên; thẻ (ảnh, tệp, gọi, vị trí) ghép tiêu đề/mô tả."""
    if isinstance(body, str):
        return body
    if isinstance(body, list):
        parts = [body_text(item) for item in body if isinstance(item, dict)]
        return " · ".join(part for part in parts if part) or None
    if not isinstance(body, dict):
        return None
    # "sendBubbleMessage" là tiêu đề kỹ thuật của thẻ cuộc gọi, không phải chữ của người dùng.
    parts = [body.get(key) for key in ("title", "description", "desc") if body.get(key) != "sendBubbleMessage"]
    params = body.get("params")
    if isinstance(params, str) and params.startswith("{"):
        try:
            duration = json.loads(params).get("duration")
        except (ValueError, AttributeError):
            duration = None
        if isinstance(duration, int | float) and not isinstance(duration, bool) and duration > 0:
            parts.append(f"thời lượng {int(duration)} giây")
    return " · ".join(part.strip() for part in parts if isinstance(part, str) and part.strip()) or None


def shape_attachment(meta: object) -> dict | None:
    """Metadata đính kèm: đã khớp bảng media hay chưa; không bao giờ có URL hay đường dẫn.

    Thẻ không có liên kết lẫn media (sticker, cuộc gọi) không phải đính kèm: trả None.
    """
    if not isinstance(meta, dict):
        return None
    items = []
    for item in meta.get("media_items") or []:
        if isinstance(item, dict):
            items.append({key: item.get(key) for key in ("source_table", "ext_type", "title", "file_size", "width", "height")})
    urls = meta.get("url_sha256")
    if not items and not (isinstance(urls, dict) and urls):
        return None
    return {"state": "matched" if items else "unmatched",
            "title": meta.get("title") if isinstance(meta.get("title"), str) else None,
            "url_count": len(urls) if isinstance(urls, dict) else 0,
            "media_items": items}


def shape_reactions(value: object) -> list[dict]:
    """[{emoji, count}] của gói, tối đa MAX_REACTIONS; mục sai khuôn thì bỏ."""
    rows = []
    for item in value[:MAX_REACTIONS] if isinstance(value, list) else ():
        emoji, count = (item.get("emoji"), item.get("count")) if isinstance(item, dict) else (None, None)
        if (isinstance(emoji, str) and 0 < len(emoji) <= 16 and isinstance(count, int) and not isinstance(count, bool)
                and 0 < count <= 100_000):
            rows.append({"emoji": emoji, "count": count})
    return rows


def parse_users(users: dict) -> tuple[dict[str, str], dict[str, str]]:
    """users.json → (tên theo mã người, mã ảnh avatar theo mã người); mục sai khuôn thì bỏ."""
    names = users.get("users") if isinstance(users.get("users"), dict) else {}
    avatars = users.get("avatars") if isinstance(users.get("avatars"), dict) else {}
    return ({key: value for key, value in names.items() if isinstance(key, str) and isinstance(value, str)},
            {key: value for key, value in avatars.items() if isinstance(key, str) and isinstance(value, str) and MEDIA_ID.fullmatch(value)})


def report_stamp(directory: Path) -> str | None:
    """Dấu nhận biết gói đổi: băm nội dung `export-report.json` (vài trăm byte). Không dùng (mtime, cỡ): trên Windows hai lần
    ghi liền nhau có thể cùng nhịp đồng hồ và cùng cỡ (revision 2 → 3), nên thay đổi bị bỏ qua (CI windows 20/11/2026)."""
    try:
        return hashlib.sha256((directory / "export-report.json").read_bytes()).hexdigest()
    except OSError:
        return None


def read_optional(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_dict(path: Path) -> dict | None:
    """Như read_optional nhưng phân biệt "không đọc được" (None: đang ghi dở, JSON hỏng) với một dict rỗng hợp lệ."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def load_report(directory: Path) -> dict:
    for name in ("export-report.json", "message-export-report.json"):
        try:
            return json.loads((directory / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def delta_limit(report: object) -> int:
    value = report.get("delta_bytes") if isinstance(report, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


MAIN, DELTA, TOMBSTONE = 0, 1, 2   # nguồn của một dòng chỉ mục: messages.jsonl hay messages-delta.jsonl; cờ TOMBSTONE: tin đã bị xóa


class ChatStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.Lock()      # chỉ mục đổi khi đọc tiếp phần thêm; người đọc lấy bản sao dưới khóa này
        self.stamp = report_stamp(directory)
        self.report = load_report(directory)
        data_dir = self.report.get("data_dir") if isinstance(self.report, dict) else None
        if data_dir is not None and not (isinstance(data_dir, str) and DATA_DIR.fullmatch(data_dir)):
            raise unavailable("export-report.json trỏ tới thư mục dữ liệu không hợp lệ")
        base = directory / data_dir if data_dir else directory
        self.messages_path = base / "messages.jsonl"
        self.delta_path = base / "messages-delta.jsonl"
        self.base = base
        try:
            conversations = json.loads((base / "conversations.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise unavailable("không đọc được conversations.json") from exc
        if not isinstance(conversations, list):
            raise unavailable("conversations.json không đúng dạng")
        self.by_id: dict[str, dict] = {}
        for row in conversations:
            if isinstance(row, dict) and isinstance(row.get("conversation_id"), str):
                self.by_id[row["conversation_id"]] = row
        # Gói web (ZALO-GROUP-01): tên người gửi, chủ tài khoản do viewer xác minh, bảng ảnh. Bản xuất cũ không có.
        users = read_optional(base / "users.json")
        self.user_names, self.avatars = parse_users(users)
        self.self_user = users.get("self_user") if isinstance(users.get("self_user"), str) else None
        self.media = {key: value for key, value in read_optional(base / "media.json").items()
                      if MEDIA_ID.fullmatch(key) and isinstance(value, dict) and value.get("mime") in MEDIA_EXTENSIONS}
        self.media_dir = directory / "media"
        # Dòng chỉ mục: (thời điểm, offset, độ dài, mã tin, nguồn). `latest` giữ dòng cuối của mỗi mã tin.
        self.entries: dict[str, list[tuple[int, int, int, str, int]]] = {cid: [] for cid in self.by_id}
        self.latest: dict[str, tuple[str, tuple]] = {}
        self.last_sent: dict[str, dict[str, int]] = {cid: {} for cid in self.by_id}
        # Bộ đếm tính trên các dòng đã đọc, không trừ lại khi một tin bị thay/ẩn (chỉ để hiện tóm tắt).
        self.body_missing = self.attachment_matched = self.attachment_unmatched = self.skipped = 0
        self.delta_offset = 0
        # Thứ tự đến của phần thêm (cho `since=`): offset đầu dòng, hội thoại, mã tin, offset cuối dòng. Token gắn với gói đang đọc.
        self.change_offsets: list[int] = []
        self.changes: list[tuple[int, str, str, int]] = []
        self.prefix = hashlib.sha256(f"{self.report.get('data_dir')}|{self.report.get('bundle_sha256')}".encode()).hexdigest()[:8]
        self.live = False                 # đã sắp xếp xong: từ đây thêm dòng bằng insort
        self._index()
        for entries in self.entries.values():
            entries.sort()
        self.live = True
        self.read_delta(delta_limit(self.report))
        self.owner_id = self.self_user or self._owner()
        self.message_count = sum(len(entries) for entries in self.entries.values())

    def _index(self) -> None:
        stale: set[tuple] = set()
        try:
            with self.messages_path.open("rb") as stream:
                offset = 0
                for raw in stream:
                    length = len(raw)
                    try:
                        row = json.loads(raw)
                    except ValueError:
                        row = None
                    self._add(row, offset, length, MAIN, stale)
                    offset += length
        except OSError as exc:
            raise unavailable("không đọc được messages.jsonl") from exc
        if stale:   # mã tin trùng trong gói gốc: giữ dòng cuối
            for cid, entries in self.entries.items():
                self.entries[cid] = [entry for entry in entries if entry not in stale]

    def _add(self, row: object, offset: int, length: int, source: int, stale: set | None = None) -> None:
        """Nạp một dòng vào chỉ mục. Trùng mã tin thì dòng này thay dòng trước. Dòng `deleted` của phần thêm giữ chỗ và người gửi của
        bản trước, chỉ đánh cờ TOMBSTONE: tin hiện giống hệt tin `deleted: true` của bản dựng đầy đủ."""
        if not isinstance(row, dict) or row.get("conversation_id") not in self.entries:
            self.skipped += 1
            return
        cid = row["conversation_id"]
        mid = row.get("message_id") if isinstance(row.get("message_id"), str) else ""
        previous = self.latest.pop(mid, None) if mid else None
        if previous is not None:
            if stale is not None:
                stale.add(previous[1])
            else:
                with contextlib.suppress(ValueError):
                    self.entries[previous[0]].remove(previous[1])
        if source == DELTA and row.get("deleted") is True:
            source |= TOMBSTONE
        if previous is not None and source & TOMBSTONE:
            entry = (*previous[1][:4], previous[1][4] | TOMBSTONE)
            stamp = entry[0]
        else:
            stamp = to_millis(row.get("timestamp")) or to_millis(row.get("server_time")) or 0
            entry = (stamp, offset, length, mid, source)
        if self.live:
            bisect.insort(self.entries[cid], entry)
        else:
            self.entries[cid].append(entry)
        if mid:
            self.latest[mid] = (cid, entry)
        sender = row.get("sender_id")
        if isinstance(sender, str):
            sent = self.last_sent[cid]
            sent[sender] = max(sent.get(sender, 0), stamp)
        if row.get("body") is None:
            self.body_missing += 1
        attachment = shape_attachment(row.get("attachment_metadata"))
        if attachment is not None:
            if attachment["state"] == "matched":
                self.attachment_matched += 1
            else:
                self.attachment_unmatched += 1

    def read_delta(self, limit: int) -> None:
        """Đọc tiếp `messages-delta.jsonl` từ byte đã đọc tới đúng `limit`; chỉ lấy dòng trọn (kết thúc bằng xuống dòng)."""
        if limit <= self.delta_offset:
            return
        try:
            with self.delta_path.open("rb") as stream:
                stream.seek(self.delta_offset)
                data = stream.read(limit - self.delta_offset)
        except OSError:
            return   # phần thêm chưa tới hoặc mất: giữ chỉ mục hiện có, lần báo cáo sau thử lại
        offset = self.delta_offset
        for raw in io.BytesIO(data[:data.rfind(b"\n") + 1]):
            try:
                row = json.loads(raw)
            except ValueError:
                row = None
            self._add(row, offset, len(raw), DELTA)
            if isinstance(row, dict) and row.get("conversation_id") in self.entries and isinstance(row.get("message_id"), str):
                self.change_offsets.append(offset)
                self.changes.append((offset, row["conversation_id"], row["message_id"], offset + len(raw)))
            offset += len(raw)
        self.delta_offset = offset
        self.message_count = sum(len(entries) for entries in self.entries.values())

    def refresh_delta(self) -> bool:
        """Báo cáo đổi: cùng `data_dir` và `bundle_sha256` thì chỉ đọc tiếp phần thêm (True).

        False khi phải lập chỉ mục lại: gói gốc đổi, thiếu `bundle_sha256` (bản cũ) hoặc phần thêm ngắn đi.
        """
        stamp = report_stamp(self.directory)
        report = load_report(self.directory)
        if (not isinstance(report, dict) or not isinstance(report.get("bundle_sha256"), str)
                or report.get("data_dir") != self.report.get("data_dir")
                or report.get("bundle_sha256") != self.report.get("bundle_sha256")
                or delta_limit(report) < self.delta_offset):
            return False
        users = read_dict(self.base / "users.json")
        media = read_dict(self.base / "media.json")
        with self.lock:
            # Đọc lỗi (đang ghi dở, JSON hỏng) thì giữ bản cũ; chỉ thay khi đọc được một dict hợp lệ.
            if users is not None:
                self.user_names, self.avatars = parse_users(users)
            if media is not None:
                self.media = {key: value for key, value in media.items()
                              if MEDIA_ID.fullmatch(key) and isinstance(value, dict) and value.get("mime") in MEDIA_EXTENSIONS}
            self.read_delta(delta_limit(report))
            self.report, self.stamp = report, stamp
        return True

    def _owner(self) -> str | None:
        """Chủ tài khoản = người gửi có mặt ở nhiều hội thoại nhất (bản xuất không ghi uid chủ)."""
        seen: dict[str, int] = {}
        for sent in self.last_sent.values():
            for sender in sent:
                seen[sender] = seen.get(sender, 0) + 1
        if not seen:
            return None
        owner = max(seen, key=lambda key: (seen[key], key))
        return owner if seen[owner] > 1 or len(self.by_id) == 1 else None

    def summary(self) -> dict:
        named = sum(1 for row in self.by_id.values() if isinstance(row.get("display_name"), str) and row["display_name"].strip())
        owner_conversations = sum(1 for sent in self.last_sent.values() if self.owner_id in sent)
        return {"status": self.report.get("status") if isinstance(self.report.get("status"), str) else None,
                "built_at": self.report.get("built_at") if isinstance(self.report.get("built_at"), str) else None,
                "media_count": len(self.media),
                "conversation_count": len(self.by_id), "message_count": self.message_count,
                "named_conversations": named, "owner_conversations": owner_conversations,
                "body_missing": self.body_missing, "attachment_matched": self.attachment_matched,
                "attachment_unmatched": self.attachment_unmatched, "skipped_lines": self.skipped}

    def conversations(self, query: str = "") -> list[dict]:
        needle = fold(query.strip())
        rows = []
        with self.lock:
            for cid, row in self.by_id.items():
                name = row.get("display_name") if isinstance(row.get("display_name"), str) else None
                if needle and needle not in fold(name or "") and not cid.startswith(needle):
                    continue
                avatar = row.get("avatar")
                entries = self.entries[cid]
                sent = self.last_sent[cid]
                rows.append({"conversation_id": cid, "display_name": name or None,
                             "name_status": row.get("name_status") if isinstance(row.get("name_status"), str) else None,
                             "message_count": len(entries),
                             "last_message_at": entries[-1][0] if entries else None,
                             "last_own_message_at": sent.get(self.owner_id) if self.owner_id else None,
                             "participant_count": len(row.get("participant_ids") or []),
                             "is_group": bool(row.get("is_group")),
                             "avatar": avatar if isinstance(avatar, str) and avatar in self.media else None})
        rows.sort(key=lambda item: (-(item["last_message_at"] or 0), item["conversation_id"]))
        return rows

    def _read(self, streams: dict, entry: tuple[int, int, int, str, int]) -> dict:
        """Đọc đúng dòng của `entry`; mở file nguồn (gói gốc hoặc phần thêm) lần đầu cần tới."""
        where = entry[4] & DELTA
        stream = streams.get(where)
        if stream is None:
            stream = streams[where] = (self.delta_path if where else self.messages_path).open("rb")
        stream.seek(entry[1])
        row = json.loads(stream.read(entry[2]))
        if entry[4] & TOMBSTONE:   # như một dòng đã xóa của bản dựng đầy đủ: không nội dung, không ảnh
            row = {**row, "deleted": True, "body": None, "attachment_metadata": None}
            row.pop("media", None)
        return row

    def token(self) -> str:
        return f"{self.prefix}:{self.delta_offset}"

    def _snapshot(self, conversation_id: str) -> tuple[list, str]:
        """Bản sao các dòng của hội thoại cùng token tại đúng lúc đó, để tin tới sau token không lọt giữa hai lần hỏi."""
        with self.lock:
            return list(self.entries[conversation_id]), self.token()

    def messages_since(self, conversation_id: str, token: str, limit: int = DEFAULT_LIMIT) -> dict:
        """Mọi tin của hội thoại đến (thêm, sửa, xóa) sau `token`, theo thứ tự đến, kèm token mới.

        Token là vị trí trong phần thêm nên tin tới muộn (đọc bù sau khi máy Zalo tắt) hay tin cũ bị sửa/xóa cũng tới trang đang mở.
        Token của gói khác (đã dựng lại) hoặc vượt phần đã đọc thì `reset`: trang tải lại hội thoại. Quá `limit` tin thì `has_more`.
        """
        if conversation_id not in self.by_id:
            raise ChatError(404, "CONVERSATION_NOT_FOUND", "Không có hội thoại này.")
        prefix, _, offset_text = token.partition(":")
        offset = int(offset_text)
        with self.lock:
            if prefix != self.prefix or offset > self.delta_offset:
                return {"conversation_id": conversation_id, "reset": True, "token": self.token()}
            picked: dict[str, tuple] = {}
            reached, more = self.delta_offset, False
            for _, cid, mid, stop in self.changes[bisect.bisect_left(self.change_offsets, offset):]:
                if cid != conversation_id or mid in picked:
                    continue
                if len(picked) >= limit:
                    more = True
                    break
                found = self.latest.get(mid)
                if found is not None and found[0] == conversation_id:
                    picked[mid] = found[1]
                    reached = stop   # nếu còn tin sau đó thì token dừng ngay sau tin cuối đã lấy
            entries = self.entries[conversation_id]
            total, latest_ms = len(entries), entries[-1][0] if entries else None
            new_token = f"{self.prefix}:{reached if more else self.delta_offset}"
        streams: dict = {}
        try:
            rows = [self.shape(self._read(streams, entry), streams) for entry in sorted(picked.values())]
        finally:
            for stream in streams.values():
                stream.close()
        return {"conversation_id": conversation_id, "messages": rows, "since": token, "token": new_token, "reset": False,
                "total": total, "has_more": more, "latest_ms": latest_ms}

    def messages_between(self, start_ms: int, end_ms: int) -> list[tuple[str, dict]]:
        """Mọi tin chưa xóa có giờ gửi trong [start_ms, end_ms) của mọi hội thoại, theo từng hội thoại rồi giờ gửi (ZALO-THU-CHI-01: trang Thu chi)."""
        with self.lock:
            picked = [(cid, entry) for cid, entries in self.entries.items()
                      for entry in entries[bisect.bisect_left(entries, (start_ms,)):bisect.bisect_left(entries, (end_ms,))]
                      if not entry[4] & TOMBSTONE]
        streams: dict = {}
        try:
            return [(cid, self.shape(self._read(streams, entry), streams)) for cid, entry in picked]
        finally:
            for stream in streams.values():
                stream.close()

    def messages(self, conversation_id: str, page: int = 0, limit: int = DEFAULT_LIMIT, query: str = "",
                 focus: str = "") -> dict:
        """Trang 0 là các tin mới nhất; tin trong trang xếp theo thời gian tăng dần.

        `focus` (mã tin): trả đúng trang chứa tin đó, bỏ qua `page`, để mở lại tin đã đánh dấu.
        """
        if conversation_id not in self.by_id:
            raise ChatError(404, "CONVERSATION_NOT_FOUND", "Không có hội thoại này.")
        entries, token = self._snapshot(conversation_id)
        if focus:
            position = next((index for index, entry in enumerate(entries) if entry[3] == focus), None)
            if position is None:
                raise ChatError(404, "MESSAGE_NOT_FOUND", "Tin này không còn trong dữ liệu chat.")
            page = (len(entries) - 1 - position) // limit
        needle = fold(query.strip())
        streams: dict = {}
        try:
            if needle:
                selected = []
                for entry in entries:
                    row = self._read(streams, entry)
                    text = body_text(row.get("body"))
                    if text and needle in fold(text):
                        selected.append(entry)
            else:
                selected = entries
            total = len(selected)
            end = max(total - page * limit, 0)
            start = max(end - limit, 0)
            rows = [self.shape(self._read(streams, entry), streams) for entry in selected[start:end]]
        finally:
            for stream in streams.values():
                stream.close()
        result = {"conversation_id": conversation_id, "messages": rows, "total": total, "page": page, "limit": limit,
                  "pages": math.ceil(total / limit), "has_older": start > 0, "query": query.strip(), "token": token}
        if focus:
            result["focus"] = focus
        return result

    def media_ref(self, key: object) -> dict | None:
        item = self.media.get(key) if isinstance(key, str) else None
        if not item:
            return None
        return {"id": key, "mime": item["mime"], **{name: item.get(name) if isinstance(item.get(name), int) else None for name in ("width", "height")}}

    def quote(self, row: dict, streams: dict | None) -> dict | None:
        """Tin được trích dẫn (cùng hội thoại): người gửi, nhãn, tối đa QUOTE_CHARS ký tự; không đọc được thì `found: false`."""
        parent = row.get("quote_id")
        if not (isinstance(parent, str) and MESSAGE_ID.fullmatch(parent)):
            return None
        found = self.latest.get(parent)
        if streams is None or found is None or found[0] != row.get("conversation_id"):
            return {"message_id": parent, "found": False}
        quoted = self.shape(self._read(streams, found[1]))   # không truyền streams: tin được trích không kèm trích dẫn của nó
        text = quoted["body_text"]
        return {"message_id": parent, "found": True, **{key: quoted[key] for key in ("sender_id", "sender_name", "type_label", "deleted")},
                "body_text": text[:QUOTE_CHARS] if isinstance(text, str) else None}

    def shape(self, row: dict, streams: dict | None = None) -> dict:
        body = row.get("body")
        kind = "missing" if body is None else "text" if isinstance(body, str) else "card"
        message_type = row.get("message_type") if isinstance(row.get("message_type"), int) else None
        status = row.get("status") if isinstance(row.get("status"), int) else None
        sender = row.get("sender_id")
        media = [ref for ref in (self.media_ref(key) for key in row.get("media") or []) if ref]
        album = body.get("album") if isinstance(body, dict) and isinstance(body.get("album"), str) else None
        deleted = row.get("deleted") is True
        card = row.get("card") if isinstance(row.get("card"), str) and row["card"] in CARD_NAMES else None
        avatar = self.avatars.get(sender) if isinstance(sender, str) else None
        return {"message_id": row.get("message_id"), "sender_id": sender,
                "sender_name": self.user_names.get(sender) if isinstance(sender, str) else None,
                "is_own": self.owner_id is not None and sender == self.owner_id,
                "deleted": deleted, "media": media, "album": album,
                "timestamp_ms": to_millis(row.get("timestamp")) or to_millis(row.get("server_time")),
                "message_type": message_type, "card": card,
                "type_label": CARD_NAMES.get(card) or TYPE_NAMES.get(message_type, f"Loại {message_type}" if message_type is not None else "Không rõ loại"),
                "status": status,
                "status_label": STATUS_NAMES.get(status, f"trạng thái {status}" if status is not None else "không rõ trạng thái"),
                "body_kind": kind, "body_text": body_text(body),
                "body_state": row.get("body_state") if isinstance(row.get("body_state"), str) else None,
                "attachment": shape_attachment(row.get("attachment_metadata")),
                "quote": None if deleted else self.quote(row, streams),
                "reactions": [] if deleted else shape_reactions(row.get("reactions")),
                "sticker": None if deleted else self.media_ref(row.get("sticker")),
                "sender_avatar": avatar if avatar in self.media else None}


    def media_path(self, media_id: str) -> tuple[str, Path]:
        """Ảnh/video/ghi âm của gói: chỉ sha có trong media.json, chỉ file thường nằm thẳng trong `media/`.

        Trả (kiểu, đường dẫn) chứ không đọc file: Handler gửi theo khúc, video lớn không vào RAM (23/11/2026).
        """
        item = self.media.get(media_id) if MEDIA_ID.fullmatch(media_id) else None
        if item is None:
            raise ChatError(404, "MEDIA_NOT_FOUND", "Không có ảnh này.")
        path = self.media_dir / (media_id + MEDIA_EXTENSIONS[item["mime"]])
        if path.is_symlink() or not path.is_file():
            raise ChatError(404, "MEDIA_NOT_FOUND", "Không có ảnh này.")
        return item["mime"], path


def _reload(directory: str) -> None:
    """Luồng nền: lập chỉ mục gói mới rồi để sẵn; get_store thay chỉ mục ở lần gọi kế tiếp."""
    try:
        store = ChatStore(Path(directory))
    except ChatError as exc:
        print(f"WARNING: zalo export: {exc.message}", file=sys.stderr)
        store = None
    with _LOCK:
        _RELOAD.update(running=False, store=store, directory=directory)


def get_store(directory: str | None = None) -> ChatStore:
    """Lập chỉ mục một lần cho mỗi tiến trình; lỗi thì lần gọi sau thử lại.

    Gói web được dựng lại (export-report.json đổi) thì lập chỉ mục mới ở luồng nền, vẫn trả chỉ mục cũ tới khi xong.
    """
    global _STORE, _STORE_DIR
    directory = EXPORT_DIR if directory is None else directory
    if not directory:
        raise unavailable("chưa đặt WEBDEBIT_ZALO_EXPORT_DIR")
    with _LOCK:
        ready = _RELOAD.pop("store", None)
        if ready is not None and _RELOAD.pop("directory", None) == directory == _STORE_DIR:
            _STORE, _STORE_DIR = ready, directory
        if _STORE is None or directory != _STORE_DIR:
            _STORE, _STORE_DIR = ChatStore(Path(directory)), directory
        elif not _RELOAD["running"] and report_stamp(Path(directory)) != _STORE.stamp and not _STORE.refresh_delta():
            _RELOAD["running"] = True
            threading.Thread(target=_reload, args=(directory,), name="zalo-chat-reload", daemon=True).start()
        return _STORE


def warm() -> None:
    """Gọi lúc khởi động server để yêu cầu đầu tiên không phải chờ lập chỉ mục."""
    if not EXPORT_DIR:
        return
    def run() -> None:
        try:
            get_store()
        except ChatError as exc:
            print(f"WARNING: zalo export: {exc.message}", file=sys.stderr)
    threading.Thread(target=run, name="zalo-chat-index", daemon=True).start()


def _query(raw: str, allowed: set[str]) -> dict[str, str]:
    values = parse_qs(raw, keep_blank_values=True)
    if not set(values) <= allowed or any(len(items) != 1 for items in values.values()):
        raise ChatError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
    return {key: items[0] for key, items in values.items()}


def handle_get(path: str, query: str, directory: str | None = None) -> tuple[int, dict]:
    """GET /api/v7/zalo/{report,conversations,messages}; lỗi ném ChatError (400/404/503)."""
    if path == "/api/v7/zalo/report":
        _query(query, set())
        return 200, get_store(directory).summary()
    if path == "/api/v7/zalo/conversations":
        values = _query(query, {"q"})
        rows = get_store(directory).conversations(values.get("q", "")[:MAX_QUERY])
        return 200, {"conversations": rows, "total": len(rows)}
    if path == "/api/v7/zalo/messages":
        values = _query(query, {"conversation", "page", "limit", "q", "message", "since"})
        conversation = values.get("conversation", "")
        page_text, limit_text = values.get("page", "0"), values.get("limit", str(DEFAULT_LIMIT))
        focus = values.get("message", "")
        since = values.get("since", "")
        if (not CONVERSATION_ID.fullmatch(conversation) or not page_text.isdigit() or not limit_text.isdigit()
                or len(page_text) > 6 or len(limit_text) > 3
                or not 0 <= int(page_text) <= MAX_PAGE or not 1 <= int(limit_text) <= MAX_LIMIT
                or ("message" in values and (not MESSAGE_ID.fullmatch(focus) or values.get("q", "").strip()))
                # since= là chế độ riêng: chỉ đi với conversation và limit, token đúng khuôn.
                or ("since" in values and (not SINCE_TOKEN.fullmatch(since) or {"page", "q", "message"} & set(values)))):
            raise ChatError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
        if "since" in values:
            return 200, get_store(directory).messages_since(conversation, since, int(limit_text))
        return 200, get_store(directory).messages(conversation, int(page_text), int(limit_text),
                                                  values.get("q", "")[:MAX_QUERY], focus)
    raise ChatError(404, "NOT_FOUND", "Không có đường dẫn này.")


MEDIA_PREFIX = "/api/v7/zalo/media/"


def handle_media(path: str, query: str, directory: str | None = None) -> tuple[str, Path]:
    """GET /api/v7/zalo/media/<sha256>: trả (kiểu, đường dẫn) cho Handler gửi theo khúc; lỗi ném ChatError."""
    if query:
        raise ChatError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
    return get_store(directory).media_path(path.removeprefix(MEDIA_PREFIX))


class RangeNotSatisfiable(Exception):
    """Range hợp lệ nhưng ngoài cỡ file: Handler trả 416 kèm `Content-Range: bytes */<cỡ>`."""


_RANGE = re.compile(r"bytes[ \t]*=[ \t]*([0-9]{1,18})?-([0-9]{1,18})?[ \t]*", re.IGNORECASE)


def byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Một khoảng `Range` (RFC 9110 §14) → (đầu, cuối) tính cả hai đầu; None = gửi cả file (200).

    Safari iOS hỏi `bytes=0-1` trước và chỉ phát video khi nhận 206. Nhiều khoảng, đơn vị lạ hoặc cú pháp hỏng
    thì bỏ qua Range, gửi cả file như máy chủ không biết Range (cho phép theo RFC). Ngoài cỡ thì ném RangeNotSatisfiable.
    """
    found = _RANGE.fullmatch(header) if header else None
    if found is None:
        return None
    first_text, last_text = found.groups()
    if first_text is None and last_text is None:
        return None
    if first_text is None:   # bytes=-n: n byte cuối; n lớn hơn file thì lấy cả file
        length = int(last_text)
        if length == 0 or size == 0:
            raise RangeNotSatisfiable
        return max(size - length, 0), size - 1
    first = int(first_text)
    last = int(last_text) if last_text is not None else size - 1
    if last_text is not None and last < first:
        return None
    if first >= size:
        raise RangeNotSatisfiable
    return first, min(last, size - 1)


class _NoDatabase:
    """Chạy một mình (không PostgreSQL): mọi route sổ trả 503, chỉ chat và trang tĩnh chạy."""

    def run(self, function: str, payload: dict, actor: str) -> dict:
        import v7_ledger_api
        raise v7_ledger_api.ApiError(503, "DATABASE_UNAVAILABLE", "Bản chạy thử chat Zalo không nối sổ công nợ.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chạy thử tab Chat Zalo trên máy có bản xuất, không cần PostgreSQL.")
    parser.add_argument("--export-dir", default=EXPORT_DIR, help="thư mục có conversations.json và messages.jsonl")
    parser.add_argument("--port", type=int, default=8781)
    args = parser.parse_args()
    if not args.export_dir:
        parser.error("cần --export-dir hoặc WEBDEBIT_ZALO_EXPORT_DIR")
    # Chạy như script thì file này là __main__; v7_ledger_api nạp thêm một bản `v7_zalo_chat` riêng,
    # nên truyền thư mục qua biến môi trường để bản đó đọc đúng chỗ.
    os.environ["WEBDEBIT_ZALO_EXPORT_DIR"] = args.export_dir
    import v7_ledger_api
    store = v7_ledger_api.v7_zalo_chat.get_store()
    v7_ledger_api.Handler.runner = _NoDatabase()
    v7_ledger_api.Handler.bind_host, v7_ledger_api.Handler.port = "127.0.0.1", args.port
    server = v7_ledger_api.ThreadingHTTPServer(("127.0.0.1", args.port), v7_ledger_api.Handler,
                                               default_actor="zalo-local", dev_actor_mode=True)
    print(f"Chat Zalo: {store.summary()['conversation_count']} hội thoại, {store.message_count} tin. "
          f"Mở http://127.0.0.1:{args.port}/zalo-chat.html (Ctrl+C để dừng)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
