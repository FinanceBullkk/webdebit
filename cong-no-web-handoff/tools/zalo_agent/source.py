"""ZALO-AGENT-01 Phần 1: đọc kho live-sync theo revision (chỉ đọc, không ghi gì vào thư mục đó).

`revision.json` ghi sau cùng, nên đọc nó TRƯỚC rồi mới đọc `changes-N.json` và `messages.jsonl`: nếu `messages.jsonl`
đã mới hơn `R` thì không sao, lượt sau xử lý lại phần dư và mọi thứ đẩy đi đều idempotent theo `message_id`.
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
# `message_id` nằm trong 400 byte đầu mỗi dòng (đo 20/11/2026: byte 92). Trích bằng regex rồi tra tập hợp: 0,26 giây
# cho 131 MB; lặp `id in dòng` cho 446 id mất 43 giây, nên không dùng.
ID_AT_HEAD = re.compile(rb'"message_id": ?"([^"]{1,128})"')
HEAD = 400
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

    def rows_for(self, ids: set[str], conversations: set[str]) -> list[dict]:
        """Một lượt quét `messages.jsonl`: dòng có `message_id` trong `ids` và thuộc `conversations`, theo thứ tự file."""
        if not ids or not conversations:
            return []
        wanted = {mid.encode() for mid in ids}
        rows = []
        with (self.dir / "messages.jsonl").open("rb") as stream:
            for raw in stream:
                found = ID_AT_HEAD.search(raw, 0, HEAD)
                if not found or found.group(1) not in wanted:
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                if row.get("conversation_id") in conversations:
                    rows.append(row)
        return rows
