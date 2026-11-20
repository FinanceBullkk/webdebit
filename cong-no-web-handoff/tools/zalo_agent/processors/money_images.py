"""ZALO-AGENT-01 Phần 3: bộ xử lý `money_images`, đọc OCR ảnh của nhóm đã chọn tại máy có Zalo (ANH-GEMINI-01).

Theo revision như `bundle`: dựng lại từ đầu (lần đầu, baseline đổi, đổi nhóm đã chọn, mất `changes-N`, revision lùi, mỗi đêm) bằng một
lượt quét ảnh của nhóm đã chọn trong `max_age_days` ngày; giữa hai lần dựng chỉ xét tin thêm/sửa trong `changes-N`. Ảnh lấy từ
`media-store` qua `media-index.json` (tên file là `id`, không phải sha256). Khóa kho kết quả là sha256 của byte mà gói chat sẽ
lưu (JXL đã chuyển JPEG như `zalo_web_bundle.Media`), để `hao` nối kết quả với `media/<sha256>.<đuôi>`; `canon` nhớ băm file
thô -> băm đó để lần dựng lại không giải mã lại. Cùng ảnh gửi ở hai tin chỉ đọc một lần.

OCR chạy ở **một luồng nền**: `step()` chỉ nộp việc, thu kết quả và ghi con trỏ, nên 14 giây mỗi ảnh không chặn `bundle` hay
`insurance` trong cùng vòng lặp. Con trỏ `money_images.json` giữ hàng chờ (`todo`) nên chết giữa chừng thì lượt sau đọc tiếp;
con trỏ tiến ngay khi ảnh vào hàng chờ (không có gì phải đẩy ở bước này). `members` = ảnh của nhóm đã chọn đã có kết quả: đó là
tập duy nhất được phép xuất ra ngoài, nên nhóm bị bỏ chọn rồi dựng lại thì ảnh của nhóm đó rời khỏi tập.

Mã lỗi: `ocr_unavailable` (thiếu easyocr/torch/Pillow), `no_revision`, `scan_failed`. Ảnh hỏng (sai băm chỉ mục, không giải mã được)
thử 3 lần rồi bỏ, chỉ đếm vào `counts.failed`, không làm cả bộ xử lý báo lỗi. `--dry-run` không lưu con trỏ ra đĩa (kho kết quả
vẫn ghi: đó là việc làm tại máy, idempotent).
"""
from __future__ import annotations

import hashlib
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import zalo_web_bundle as wb

from .. import cursor as cursors
from .. import ocr, reads
from ..source import LiveSync, read_json, retry_io

NAME = "money_images"
MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/jxl": ".jxl"}
ID = re.compile(r"[A-Za-z0-9_-]{8,128}")
TRIES = 3
MAX_FAILED = 2000


class MoneyImagesProcessor:
    name = NAME

    def __init__(self, live: LiveSync, state: Path, reads_dir: Path, *, engine=None, executor=None, prepare=ocr.prepare_image,
                 transcode=wb.transcode_jxl, dry_run: bool = False, clock=time.time, max_age_days: int | None = 30):
        self.live, self.dir, self.reads = live, Path(state), Path(reads_dir)
        self.engine = engine or ocr.EasyOcr()
        self.executor, self.prepare, self.transcode = executor, prepare, transcode
        self.dry_run, self.clock, self.max_age_days = dry_run, clock, max_age_days
        self.cursor: dict | None = None
        self.future = None

    # ---------------------------------------------------------------- con trỏ (nguồn thật là bản trong bộ nhớ)
    def state(self) -> dict:
        if self.cursor is None:
            self.cursor = {"todo": [], "members": {}, "canon": {}, "failed": [], **(cursors.load(self.dir, NAME) or {})}
        return self.cursor

    def save(self, now: float) -> None:
        if not self.dry_run:
            cursors.save(self.dir, NAME, self.state(), now)

    def counts(self) -> dict:
        cursor = self.state()
        return {"read": len(cursor["members"]), "pending": len(cursor["todo"]), "failed": len(cursor["failed"]),
                "review": sum(1 for member in cursor["members"].values() if member.get("verdict") == "unsure")}

    def result(self, action: str, error: str | None = None) -> dict:
        cursor = self.state()
        return {"action": action, "revision": cursor.get("revision"), "error": error, "bytes_sent": 0, "reason": None, "counts": self.counts()}

    # ---------------------------------------------------------------- phát hiện ảnh mới
    def wants_work(self) -> bool:
        """Có revision mới hoặc phải dựng lại (vòng lặp gom 3 giây). Hàng chờ OCR không tính: nó tự chạy mỗi nhịp."""
        revision, selection, cursor = self.live.revision(), self.live.selection(), self.state()
        if revision is None or not selection:
            return False
        if cursor.get("revision") is None or revision != cursor["revision"]:
            return True
        return cursors.rebuild_reason(cursor, revision, self.live.baseline_sha256(), selection, self.clock()) is not None

    def add_rows(self, rows: list[dict]) -> None:
        cursor = self.state()
        if not rows:
            return
        by_message: dict[str, list[dict]] = {}
        for key, item in ((read_json(self.live.dir / "media-index.json", {}) or {}).get("items") or {}).items():
            if isinstance(item, dict) and isinstance(item.get("client_message_id"), str) and item.get("mime") in MIMES:
                by_message.setdefault(item["client_message_id"], []).append({**item, "id": item.get("id") or key})
        waiting, failed = {item["raw"] for item in cursor["todo"]}, set(cursor["failed"])
        version = self.engine.version
        for row in rows:
            stamp = int(row["timestamp"]) if str(row.get("timestamp", "")).isdigit() else 0
            for item in by_message.get(row.get("client_message_id"), ()):
                raw = item.get("sha256")
                if not isinstance(raw, str) or raw in waiting or raw in failed or not ID.fullmatch(str(item["id"])):
                    continue
                entry = {"raw": raw, "file": item["id"] + MIMES[item["mime"]], "ts": stamp}
                sha = cursor["canon"].get(raw)
                found = sha and reads.load(self.reads, sha, self.engine.name, version)
                if found:   # đã đọc (cùng engine và phiên bản): không đọc lại, chỉ vào tập `members`
                    cursor["members"][sha] = {**entry, "verdict": ocr.verdict(found)}
                else:
                    cursor["todo"].append({**entry, "tries": 0})
                    waiting.add(raw)

    def discover(self, revision: int, selection: list[str], now: float) -> None:
        cursor, baseline = self.state(), self.live.baseline_sha256()
        have = cursor.get("revision")
        reason, ids = cursors.decide(cursor if have is not None else None, revision, baseline, selection, now, self.live)
        if reason is None and revision == have:
            return
        conversations = set(selection)
        if reason:
            since = int((now - self.max_age_days * 86400) * 1000) if self.max_age_days else 0
            rows = self.live.image_rows(conversations, since)
            cursor["todo"], cursor["members"] = [], {}
            cursor["built_at"] = cursors.now_iso(now)
        else:
            rows = [row for row in self.live.rows_for(ids, conversations) if row.get("message_type") in wb.IMAGE_TYPES and not row.get("deleted")]
        self.add_rows(rows)
        cursor.update(revision=revision, baseline_sha256=baseline, selection_sha256=cursors.selection_sha256(selection))
        self.save(now)

    # ---------------------------------------------------------------- đọc một ảnh (chạy ở luồng nền) và thu kết quả
    def process(self, item: dict, engine) -> dict:
        raw = item["raw"]
        try:
            version = engine.version
            data = retry_io((self.live.dir / "media-store" / item["file"]).read_bytes)
            if hashlib.sha256(data).hexdigest() != raw:   # file không khớp chỉ mục của viewer: không tin
                return {"raw": raw, "status": "error"}
            if wb.sniff(data) == "image/jxl":
                data = self.transcode(data)
            if wb.sniff(data) not in ("image/jpeg", "image/png", "image/gif", "image/webp"):
                return {"raw": raw, "status": "error"}
            sha = hashlib.sha256(data).hexdigest()
            found = reads.load(self.reads, sha, engine.name, version)
            if found is None:
                image, size = self.prepare(data)
                boxes = engine.read(image)
                found = {"engine": engine.name, "version": version, "read_at": cursors.now_iso(self.clock()), "size": list(size),
                         "boxes": boxes, **ocr.analyse(boxes)}
                reads.save(self.reads, sha, found)
            return {"raw": raw, "status": "ok", "sha": sha, "verdict": ocr.verdict(found)}
        except ocr.OcrUnavailable:
            return {"raw": raw, "status": "unavailable"}
        except Exception:  # noqa: BLE001  (ảnh hỏng không được làm chết luồng nền)
            return {"raw": raw, "status": "error"}

    def collect(self) -> tuple[bool, str | None]:
        """(đã thu một ảnh, mã lỗi). Chỉ luồng chính đụng con trỏ; luồng nền chỉ ghi kho kết quả."""
        future, self.future = self.future, None
        if future is None:
            return False, None
        if not future.done():
            self.future = future
            return False, None
        try:
            outcome = future.result()
        except Exception:  # noqa: BLE001
            return False, None
        cursor = self.state()
        item = next((todo for todo in cursor["todo"] if todo["raw"] == outcome["raw"]), None)
        if outcome["status"] == "unavailable":
            return False, "ocr_unavailable"
        if item is None:   # nhóm bị bỏ chọn trong lúc đọc: kết quả nằm trong kho nhưng không vào `members`
            return True, None
        if outcome["status"] == "ok":
            cursor["canon"][outcome["raw"]] = outcome["sha"]
            cursor["members"][outcome["sha"]] = {"raw": item["raw"], "file": item["file"], "ts": item["ts"], "verdict": outcome["verdict"]}
            cursor["todo"].remove(item)
        else:
            item["tries"] += 1
            if item["tries"] >= TRIES:
                cursor["todo"].remove(item)
                cursor["failed"] = [*cursor["failed"], item["raw"]][-MAX_FAILED:]
        self.save(self.clock())
        return True, None

    def submit(self) -> None:
        todo = self.state()["todo"]
        if self.future is not None or not todo:
            return
        if self.executor is None:
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="money_ocr")
        self.future = self.executor.submit(self.process, dict(max(todo, key=lambda item: item["ts"])), self.engine)   # mới nhất trước

    def step(self) -> dict:
        now = self.clock()
        try:
            _ = self.engine.version   # thiếu engine: báo ngay, đừng để hàng chờ rỗng che mất lỗi
        except ocr.OcrUnavailable:
            return self.result("idle", "ocr_unavailable")
        worked, error = self.collect()
        revision, selection = self.live.revision(), self.live.selection()
        if revision is None:
            return self.result("read" if worked else "idle", error or "no_revision")
        if selection:
            try:
                self.discover(revision, selection, now)
            except OSError:
                return self.result("idle", error or "scan_failed")
        self.submit()
        return self.result("read" if worked else "idle", error)

    # ---------------------------------------------------------------- `zalo_agent reread`
    def reread(self, engine, since_ms: int) -> dict:
        """Đọc lại ảnh đã nhận (`members`) có giờ gửi >= `since_ms` bằng `engine` (engine hoặc phiên bản mới), giữ kết quả cũ cạnh bên.
        Cùng engine và phiên bản thì bỏ qua. Chỉ ghi kho kết quả, không đụng con trỏ. Ném `OcrUnavailable` khi thiếu engine."""
        version = engine.version
        counts = {"wanted": 0, "read": 0, "had": 0, "failed": 0}
        for sha, member in sorted(self.state()["members"].items(), key=lambda pair: -pair[1]["ts"]):
            if member["ts"] < since_ms:
                continue
            counts["wanted"] += 1
            if reads.load(self.reads, sha, engine.name, version):
                counts["had"] += 1
                continue
            outcome = self.process(member, engine)
            if outcome["status"] == "unavailable":
                raise ocr.OcrUnavailable(engine.name)
            counts["read" if outcome["status"] == "ok" else "failed"] += 1
        return counts
