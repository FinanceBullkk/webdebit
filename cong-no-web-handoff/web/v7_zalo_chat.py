"""ZALO-CHAT-01: đọc bản xuất chat Zalo (JSONL) theo trang cho tab Đòi nợ. Chỉ đọc, stdlib.

Bản xuất nằm ngoài repo (`WEBDEBIT_ZALO_EXPORT_DIR`): `conversations.json` + `messages.jsonl`
(+ `export-report.json`). Khởi động chỉ đọc một lượt để lập chỉ mục offset theo hội thoại;
mỗi yêu cầu đọc đúng các dòng của trang cần trả, không bao giờ nạp cả file vào RAM hay gửi
cả file cho trình duyệt. Không ghi, không sửa file nguồn, không log nội dung tin.
"""

from __future__ import annotations

import argparse
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
# Nhãn loại tin suy từ bản xuất 30/10/2026 (msgType của Zalo PC); loại lạ hiện "Loại N".
TYPE_NAMES = {1: "Văn bản", 2: "Ảnh", 3: "Ghi âm", 4: "Sticker", 5: "Ảnh", 6: "Cuộc gọi", 7: "GIF",
              17: "Vị trí", 18: "Video", 19: "Tệp", 20: "Đã thu hồi", 21: "Thẻ liên kết", -4: "Thông báo nhóm"}
# Trong bản xuất, 100% tin chủ tài khoản gửi có status 2 và tin nhận có status 4; mã khác giữ số.
STATUS_NAMES = {2: "đã gửi", 4: "đã nhận"}
_LOCK = threading.Lock()
_STORE: ChatStore | None = None
_STORE_DIR: str | None = None


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


class ChatStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.messages_path = directory / "messages.jsonl"
        try:
            conversations = json.loads((directory / "conversations.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise unavailable("không đọc được conversations.json") from exc
        if not isinstance(conversations, list):
            raise unavailable("conversations.json không đúng dạng")
        self.by_id: dict[str, dict] = {}
        for row in conversations:
            if isinstance(row, dict) and isinstance(row.get("conversation_id"), str):
                self.by_id[row["conversation_id"]] = row
        self.report = {}
        for name in ("export-report.json", "message-export-report.json"):
            try:
                self.report = json.loads((directory / name).read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                continue
        self.entries: dict[str, list[tuple[int, int, int]]] = {cid: [] for cid in self.by_id}
        self.last_sent: dict[str, dict[str, int]] = {cid: {} for cid in self.by_id}
        self.body_missing = self.attachment_matched = self.attachment_unmatched = self.skipped = 0
        self._index()
        for entries in self.entries.values():
            entries.sort()
        self.owner_id = self._owner()
        self.message_count = sum(len(entries) for entries in self.entries.values())

    def _index(self) -> None:
        try:
            with self.messages_path.open("rb") as stream:
                offset = 0
                for raw in stream:
                    length = len(raw)
                    try:
                        row = json.loads(raw)
                    except ValueError:
                        row = None
                    if not isinstance(row, dict) or row.get("conversation_id") not in self.entries:
                        self.skipped += 1
                    else:
                        cid = row["conversation_id"]
                        stamp = to_millis(row.get("timestamp")) or to_millis(row.get("server_time")) or 0
                        self.entries[cid].append((stamp, offset, length))
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
                    offset += length
        except OSError as exc:
            raise unavailable("không đọc được messages.jsonl") from exc

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
                "conversation_count": len(self.by_id), "message_count": self.message_count,
                "named_conversations": named, "owner_conversations": owner_conversations,
                "body_missing": self.body_missing, "attachment_matched": self.attachment_matched,
                "attachment_unmatched": self.attachment_unmatched, "skipped_lines": self.skipped}

    def conversations(self, query: str = "") -> list[dict]:
        needle = fold(query.strip())
        rows = []
        for cid, row in self.by_id.items():
            name = row.get("display_name") if isinstance(row.get("display_name"), str) else None
            if needle and needle not in fold(name or "") and not cid.startswith(needle):
                continue
            entries = self.entries[cid]
            sent = self.last_sent[cid]
            rows.append({"conversation_id": cid, "display_name": name or None,
                         "name_status": row.get("name_status") if isinstance(row.get("name_status"), str) else None,
                         "message_count": len(entries),
                         "last_message_at": entries[-1][0] if entries else None,
                         "last_own_message_at": sent.get(self.owner_id) if self.owner_id else None,
                         "participant_count": len(row.get("participant_ids") or [])})
        rows.sort(key=lambda item: (-(item["last_message_at"] or 0), item["conversation_id"]))
        return rows

    def _read(self, stream, entry: tuple[int, int, int]) -> dict:
        stream.seek(entry[1])
        return json.loads(stream.read(entry[2]))

    def messages(self, conversation_id: str, page: int = 0, limit: int = DEFAULT_LIMIT, query: str = "") -> dict:
        """Trang 0 là các tin mới nhất; tin trong trang xếp theo thời gian tăng dần."""
        if conversation_id not in self.by_id:
            raise ChatError(404, "CONVERSATION_NOT_FOUND", "Không có hội thoại này.")
        entries = self.entries[conversation_id]
        needle = fold(query.strip())
        with self.messages_path.open("rb") as stream:
            if needle:
                selected = []
                for entry in entries:
                    row = self._read(stream, entry)
                    text = body_text(row.get("body"))
                    if text and needle in fold(text):
                        selected.append(entry)
            else:
                selected = entries
            total = len(selected)
            end = max(total - page * limit, 0)
            start = max(end - limit, 0)
            rows = [self.shape(self._read(stream, entry)) for entry in selected[start:end]]
        return {"conversation_id": conversation_id, "messages": rows, "total": total, "page": page, "limit": limit,
                "pages": math.ceil(total / limit), "has_older": start > 0, "query": query.strip()}

    def shape(self, row: dict) -> dict:
        body = row.get("body")
        kind = "missing" if body is None else "text" if isinstance(body, str) else "card"
        message_type = row.get("message_type") if isinstance(row.get("message_type"), int) else None
        status = row.get("status") if isinstance(row.get("status"), int) else None
        return {"message_id": row.get("message_id"), "sender_id": row.get("sender_id"),
                "is_own": self.owner_id is not None and row.get("sender_id") == self.owner_id,
                "timestamp_ms": to_millis(row.get("timestamp")) or to_millis(row.get("server_time")),
                "message_type": message_type,
                "type_label": TYPE_NAMES.get(message_type, f"Loại {message_type}" if message_type is not None else "Không rõ loại"),
                "status": status,
                "status_label": STATUS_NAMES.get(status, f"trạng thái {status}" if status is not None else "không rõ trạng thái"),
                "body_kind": kind, "body_text": body_text(body),
                "body_state": row.get("body_state") if isinstance(row.get("body_state"), str) else None,
                "attachment": shape_attachment(row.get("attachment_metadata"))}


def get_store(directory: str | None = None) -> ChatStore:
    """Lập chỉ mục một lần cho mỗi tiến trình; lỗi thì lần gọi sau thử lại."""
    global _STORE, _STORE_DIR
    directory = EXPORT_DIR if directory is None else directory
    if not directory:
        raise unavailable("chưa đặt WEBDEBIT_ZALO_EXPORT_DIR")
    with _LOCK:
        if _STORE is None or directory != _STORE_DIR:
            _STORE, _STORE_DIR = ChatStore(Path(directory)), directory
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
        values = _query(query, {"conversation", "page", "limit", "q"})
        conversation = values.get("conversation", "")
        page_text, limit_text = values.get("page", "0"), values.get("limit", str(DEFAULT_LIMIT))
        if (not CONVERSATION_ID.fullmatch(conversation) or not page_text.isdigit() or not limit_text.isdigit()
                or len(page_text) > 6 or len(limit_text) > 3
                or not 0 <= int(page_text) <= MAX_PAGE or not 1 <= int(limit_text) <= MAX_LIMIT):
            raise ChatError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
        return 200, get_store(directory).messages(conversation, int(page_text), int(limit_text), values.get("q", "")[:MAX_QUERY])
    raise ChatError(404, "NOT_FOUND", "Không có đường dẫn này.")


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
