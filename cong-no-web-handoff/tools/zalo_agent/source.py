"""ZALO-AGENT-01 Phần 1: đọc kho live-sync theo revision (chỉ đọc, không ghi gì vào thư mục đó).

`revision.json` ghi sau cùng, nên đọc nó TRƯỚC rồi mới đọc `changes-N.json` và `messages.jsonl`: nếu `messages.jsonl`
đã mới hơn `R` thì không sao, lượt sau xử lý lại phần dư và mọi thứ đẩy đi đều idempotent theo `message_id`.

Windows: `open()` của Python không cho file bị thay khi đang mở. Đã đo (20/11/2026): mở bằng `CreateFileW` đủ cờ chia sẻ
(READ|WRITE|DELETE) vẫn cho đổi tên file đi nhưng KHÔNG cho `os.replace` đè lên nó (WinError 5), nên không có cách mở nào
tránh được. `live_sync.py` bọc `os.replace` của `messages.jsonl` bằng `_retry_io` (60 lần, nghỉ tới 0,5 giây) và agent chỉ
giữ file mở khoảng 0,25 giây mỗi lượt quét, nên hai bên không chặn nhau. Dựng đầy đủ (`zalo_web_bundle.build`) lọc
byte theo `conversation_id` đã chọn trước khi `json.loads`, nên cũng chỉ giữ file mở cỡ đó (không phải 1,6 giây).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN = timezone(timedelta(hours=7))
SELECTION = "web-groups.json"
CONVERSATION_ID = re.compile(r"[0-9a-f]{64}")
# Trích mọi `"message_id": "…"` trong dòng bằng regex rồi tra tập hợp: 0,32 giây cho 131 MB (đo 20/11/2026); lặp
# `id in dòng` cho 446 id mất 43 giây, nên không dùng. Quét cả dòng (không chỉ đầu dòng) để khóa cấp trên cùng nằm sau
# một khóa lồng của tin trích dẫn vẫn không bị lỡ; sau json.loads luôn kiểm lại khóa cấp trên cùng. Dòng không có chuỗi
# `"message_id"` nào thì không thể có khóa đó: bỏ qua, khỏi parse.
ID_KEY = re.compile(rb'"message_id": ?"([^"]{1,128})"')
PAUSE = 0.05           # giây; hệ số nghỉ của retry_io (test đặt 0)
IDENTITIES = ("attached", "waiting_for_zalo", "reprobing")


class Rebuild(Exception):
    """Con trỏ không còn dùng được: dựng lại từ đầu. `reason` là mã ngắn, đi vào log."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def read_json(path: Path, default=None):
    for attempt in range(3):   # Windows: file đang được thay nguyên tử có thể bị từ chối đọc trong tích tắc
        try:
            return json.loads(path.read_bytes())
        except FileNotFoundError:
            return default
        except (OSError, ValueError):
            time.sleep(0.05 * (attempt + 1))
    return default


def retry_io(action, attempts: int = 5):
    """Thử lại ngắn khi Windows từ chối vì trình diệt virus hay trình lập chỉ mục đang giữ file (như `_retry_io` của live-sync)."""
    for attempt in range(attempts):
        try:
            return action()
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(PAUSE * (attempt + 1))


class LiveSync:
    def __init__(self, directory: Path):
        self.dir = Path(directory)

    def revision(self) -> int | None:
        value = (read_json(self.dir / "revision.json", {}) or {}).get("revision")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def revision_at(self) -> str | None:
        stamp = (read_json(self.dir / "revision.json", {}) or {}).get("message_publish_epoch_ms")
        if isinstance(stamp, int) and not isinstance(stamp, bool):
            return datetime.fromtimestamp(stamp / 1000, VN).isoformat(timespec="seconds")
        return None

    def baseline_sha256(self) -> str | None:
        try:
            return hashlib.sha256((self.dir / "baseline-manifest.json").read_bytes()).hexdigest()
        except OSError:
            return None

    def identity(self) -> str:
        status = (read_json(self.dir / "poller-identity.json", {}) or {}).get("status")
        return status if status in IDENTITIES else "unknown"

    def selection(self) -> list[str]:
        document = read_json(self.dir / SELECTION, {"conversations": []}) or {}
        return sorted({cid for cid in document.get("conversations", []) if isinstance(cid, str) and CONVERSATION_ID.fullmatch(cid)})

    def changed_ids(self, after: int, upto: int) -> set[str]:
        """Mọi `message_id` thêm, sửa, xóa trong revision (after, upto]. Thiếu một file ở giữa thì phải dựng lại."""
        ids: set[str] = set()
        for number in range(after + 1, upto + 1):
            change = read_json(self.dir / f"changes-{number}.json")
            if not isinstance(change, dict):
                raise Rebuild("missing_changes")
            for key in ("added", "updated", "deleted"):
                ids.update(mid for mid in change.get(key) or [] if isinstance(mid, str))
        return ids

    def image_rows(self, conversations: set[str], since_ms: int = 0, types: tuple = (2, 7)) -> list[dict]:
        """Một lượt quét `messages.jsonl`: dòng ảnh (`message_type` trong `types`, chưa xóa) của `conversations` có `timestamp` >=
        `since_ms`, theo thứ tự file. Lọc byte theo `conversation_id` trước khi `json.loads`, như `zalo_web_bundle.build`."""
        needles = [cid.encode() for cid in conversations]
        rows = []
        if not needles:
            return rows
        with (self.dir / "messages.jsonl").open("rb") as stream:
            for raw in stream:
                if not any(needle in raw for needle in needles):
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                stamp = row.get("timestamp") if isinstance(row, dict) else None
                if isinstance(row, dict) and row.get("conversation_id") in conversations and row.get("message_type") in types \
                        and not row.get("deleted") and (int(stamp) if str(stamp).isdigit() else 0) >= since_ms:
                    rows.append(row)
        return rows

    def rows_for(self, ids: set[str], conversations: set[str]) -> list[dict]:
        """Một lượt quét `messages.jsonl`: dòng có `message_id` trong `ids` và thuộc `conversations`, theo thứ tự file."""
        if not ids or not conversations:
            return []
        wanted = {mid.encode() for mid in ids}
        rows = []
        with (self.dir / "messages.jsonl").open("rb") as stream:
            for raw in stream:
                if wanted.isdisjoint(found.group(1) for found in ID_KEY.finditer(raw)):
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("message_id") in ids and row.get("conversation_id") in conversations:
                    rows.append(row)
        return rows
