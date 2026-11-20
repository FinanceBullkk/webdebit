"""ZALO-AGENT-01 Phần 3-4: bộ xử lý `money_images`, đọc OCR ảnh của nhóm đã chọn tại máy có Zalo, hỏi Gemini khi cần (ANH-GEMINI-01).

Theo revision như `bundle`: dựng lại từ đầu (lần đầu, baseline đổi, đổi nhóm đã chọn, mất `changes-N`, revision lùi, mỗi đêm) bằng một
lượt quét ảnh của nhóm đã chọn trong `max_age_days` ngày; giữa hai lần dựng chỉ xét tin thêm/sửa trong `changes-N`. Ảnh lấy từ
`media-store` qua `media-index.json` (tên file là `id`, không phải sha256). Khóa kho kết quả là sha256 của byte mà gói chat sẽ
lưu (JXL đã chuyển JPEG như `zalo_web_bundle.Media`), để `hao` nối kết quả với `media/<sha256>.<đuôi>`; `canon` nhớ băm file
thô -> băm đó để lần dựng lại không giải mã lại. Cùng ảnh gửi ở hai tin chỉ đọc một lần.

OCR và việc hỏi Gemini chạy ở **một luồng nền**, mỗi lần một việc (OCR ảnh mới trước, hỏi Gemini sau): `step()` chỉ nộp việc, thu kết
quả và ghi con trỏ, nên 14 giây mỗi ảnh không chặn `bundle` hay `insurance` trong cùng vòng lặp. Con trỏ `money_images.json` giữ hàng chờ
(`todo`) nên chết giữa chừng thì lượt sau đọc tiếp. `members` = ảnh của nhóm đang chọn đã có kết quả: tập duy nhất được phép xuất ra
ngoài, nên nhóm bị bỏ chọn rồi dựng lại thì ảnh của nhóm đó rời tập.

Kết luận từng ảnh (`members[sha]["by"]`, ANH-GEMINI-01 mục 4): `ocr` khi OCR chắc; ảnh có dấu hiệu tiền mà OCR không chắc thì gửi ảnh
ĐÃ CHE tới cả hai đường Gemini: hai đường cùng một số thì `gemini-2`, lệch hoặc lỗi hoặc không che được thì `human`; không dấu hiệu tiền
thì không kết luận và không rời máy. Gửi ra ngoài tắt (mặc định, hoặc `--dry-run`) thì ảnh không chắc đi thẳng `human`. Kết quả Gemini lưu
trong kho như một lượt đọc (`gemini-proxy@<model>`, `gemini-api@<model>`); đường lỗi lưu mã lỗi và số lần thử, thử lại sau 10 phút x lần
thử, đủ 3 lần thì `human`. Mỗi lần gửi ghi một dòng `sent.jsonl` (sha256, đường, giờ, kết quả hoặc mã lỗi).

`hao` nhận qua `push.py` tới `reads_target` (đích rỗng = tắt): file nhỏ `money-reads.json` (xem `export_bytes`) và, cho mỗi ảnh đã có kết
luận mà che được, ảnh đã che `redacted/<sha256 ảnh gốc>.jpg` (cùng luật che như trước khi gửi Gemini; ảnh không che được thì không có file,
`hao` chỉ gửi chữ). Ảnh đã che nhớ ở `<root>/redacted/`; `redacted/*` không còn trong kết quả thì bị dọn trên `hao`. Mọi hội thoại trong danh
sách đã chọn đều được xử lý, nhóm hay chat riêng 1-1 (không lọc theo `is_group`).

Mã lỗi: `ocr_unavailable` (thiếu easyocr/torch/Pillow), `no_revision`, `scan_failed`, `push_failed`. Ảnh hỏng thử 3 lần rồi bỏ, chỉ đếm vào
`counts.failed`. `--dry-run` không lưu con trỏ, không đẩy, không gửi ra ngoài (kho kết quả vẫn ghi: việc tại máy, idempotent).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import zalo_web_bundle as wb

from .. import cursor as cursors
from .. import gemini as gemini_module
from .. import ocr, reads, redact
from .. import push as pusher
from ..source import LiveSync, read_json, retry_io

NAME = "money_images"
EXPORT = "money-reads.json"
MIMES = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "image/jxl": ".jxl"}
IMAGES = ("image/jpeg", "image/png", "image/gif", "image/webp")
ID = re.compile(r"[A-Za-z0-9_-]{8,128}")
TRIES = 3
RETRY_ASK = 600        # giây x số lần thử: chờ trước khi hỏi lại đường Gemini đã lỗi
RESEND = 3600          # giây: gửi lại `money-reads.json` dù không đổi (hao mất file thì tự có lại)
MAX_FAILED = 2000


class MoneyImagesProcessor:
    name = NAME

    def __init__(self, live: LiveSync, state: Path, reads_dir: Path, *, engine=None, executor=None, prepare=ocr.prepare_image,
                 transcode=wb.transcode_jxl, dry_run: bool = False, clock=time.time, max_age_days: int | None = 30,
                 gemini=None, reads_target: str = "", run=pusher.ssh_run):
        self.live, self.dir, self.reads = live, Path(state), Path(reads_dir)
        self.engine = engine or ocr.EasyOcr()
        self.gemini = gemini if gemini is not None else gemini_module.Gemini()
        self.executor, self.prepare, self.transcode = executor, prepare, transcode
        self.dry_run, self.clock, self.max_age_days = dry_run, clock, max_age_days
        self.reads_target, self.run = reads_target, run
        self.cursor: dict | None = None
        self.future = None
        self.hidden_dir = self.reads.parent / "redacted"
        self.unhideable: set[str] = set()   # ảnh không che được (không ô chữ): khỏi thử lại mỗi lần xuất

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
        members = cursor["members"].values()
        return {"read": len(cursor["members"]), "pending": len(cursor["todo"]), "failed": len(cursor["failed"]),
                "review": sum(1 for member in members if member.get("by") == "human"),
                "asking": sum(1 for member in members if member.get("verdict") == "unsure" and member.get("by") is None)}

    def result(self, action: str, error: str | None = None) -> dict:
        cursor = self.state()
        return {"action": action, "revision": cursor.get("revision"), "error": error, "bytes_sent": 0, "reason": None, "counts": self.counts()}

    # ---------------------------------------------------------------- kết luận (ANH-GEMINI-01 mục 4)
    def asking(self) -> bool:
        """Gửi ra ngoài đang bật và đủ hai đường. `--dry-run` không bao giờ gửi ảnh ra ngoài."""
        return self.gemini.ready and not self.dry_run

    def decide(self, sha: str, primary: dict | None) -> str | None:
        """`ocr`, `gemini-2` hoặc `human`; None khi chưa có kết luận (không dấu hiệu tiền, hoặc đang chờ Gemini)."""
        kind = ocr.verdict(primary)
        if kind != "unsure":
            return "ocr" if kind == "ocr" else None
        if not self.asking():
            return "human"
        answers = [reads.load(self.reads, sha, name, self.gemini.model) for name in gemini_module.ROUTES]
        if any(answer and answer.get("error") and answer.get("tries", 0) >= TRIES for answer in answers):
            return "human"
        if any(answer is None or answer.get("error") for answer in answers):
            return None
        first, second = answers
        agree = all(answer["is_transfer"] and isinstance(answer["amount_vnd"], int) for answer in answers) and first["amount_vnd"] == second["amount_vnd"]
        return "gemini-2" if agree else "human"

    def export_bytes(self, members: dict) -> bytes:
        """`{"schema": 1, "reads": {sha256: {by, amount_vnd, txn_time, bank, reads: [{engine, version, amount_vnd, confidence}]}}}` cho ảnh
        có dấu hiệu tiền và đã có kết luận. Không chữ OCR, không số tài khoản, không tên, không ô chữ; `human` thì số tiền để trống (số OCR
        đoán nằm trong `reads` kèm độ tin cậy). Không có giờ tạo file nên không đổi dữ liệu thì không đổi byte."""
        items = {}
        for sha, member in sorted(members.items()):
            by = member.get("by")
            if by is None:
                continue
            done = [read for read in reads.for_image(self.reads, sha) if not read.get("error")]
            item = {"by": by, "amount_vnd": None, "txn_time": None, "bank": None,
                    "reads": [{"engine": read["engine"], "version": read["version"], "amount_vnd": read.get("amount_vnd"),
                               "confidence": read.get("confidence")} for read in done]}
            if by == "ocr":
                primary = next(read for read in done if read["engine"] == self.engine.name and read["version"] == self.engine.version)
                item.update({key: primary.get(key) for key in ("amount_vnd", "txn_time", "bank")})
            elif by == "gemini-2":
                first, second = (next(read for read in done if read["engine"] == name) for name in gemini_module.ROUTES)
                item.update({key: first.get(key) if first.get(key) == second.get(key) else None for key in ("amount_vnd", "txn_time", "bank")})
            items[sha] = item
        return json.dumps({"schema": 1, "reads": items}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def redacted_files(self, members: dict) -> list[pusher.Item]:
        """Ảnh đã che của mọi ảnh đã có kết luận mà che được. Dựng khi cần và nhớ trong `<root>/redacted/`; thiếu Pillow hay file nguồn tạm
        không đọc được thì bỏ qua lượt này (lần xuất sau thử lại), không che được vì không có ô chữ thì không bao giờ có file."""
        items = []
        for sha, member in sorted(members.items()):
            if member.get("by") is None or sha in self.unhideable:
                continue
            path = self.hidden_dir / f"{sha}.jpg"
            if not path.is_file():
                try:
                    primary = reads.load(self.reads, sha, self.engine.name, self.engine.version)
                    data = self.load_image(member)
                    hidden = redact.redact(data, primary, self.prepare) if data and primary else None
                except (ocr.OcrUnavailable, OSError):
                    continue
                except Exception:  # noqa: BLE001
                    hidden = None
                if hidden is None:
                    self.unhideable.add(sha)
                    continue
                self.hidden_dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
                tmp.write_bytes(hidden[0])
                retry_io(lambda tmp=tmp, path=path: os.replace(tmp, path))
            items.append(pusher.Item(f"redacted/{sha}.jpg", path, immutable=True))
        return items

    def export(self, now: float) -> str | None:
        """Đẩy `money-reads.json` khi đổi (hoặc mỗi giờ). Chỉ xuất khi `members` đúng với nhóm đang chọn; chọn rỗng thì xuất rỗng."""
        cursor, selection = self.state(), self.live.selection()
        if not self.reads_target or self.dry_run:
            return None
        if selection and cursor.get("selection_sha256") != cursors.selection_sha256(selection):
            return None   # vừa đổi nhóm, chưa dựng lại: members còn của nhóm cũ
        members = cursor["members"] if selection else {}
        data = self.export_bytes(members)
        digest = hashlib.sha256(data).hexdigest()
        if digest == cursor.get("pushed_sha") and now - cursor.get("pushed_at", 0) < RESEND:
            return None
        try:
            plan = pusher.Plan(self.reads_target, tuple(self.redacted_files(members)), pusher.Item(EXPORT, data), ("redacted/*",))
            pusher.push(plan, run=self.run)
        except pusher.PushError:
            return "push_failed"
        cursor.update(pushed_sha=digest, pushed_at=now)
        self.save(now)
        return None

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
                    cursor["members"][sha] = {**entry, "verdict": ocr.verdict(found), "by": self.decide(sha, found)}
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

    # ---------------------------------------------------------------- việc của luồng nền: đọc OCR một ảnh, hỏi Gemini một ảnh
    def load_image(self, item: dict) -> bytes | None:
        """Byte ảnh như gói chat sẽ lưu (JXL đã chuyển JPEG), hoặc None khi file không khớp chỉ mục của viewer hay không phải ảnh."""
        data = retry_io((self.live.dir / "media-store" / item["file"]).read_bytes)
        if hashlib.sha256(data).hexdigest() != item["raw"]:
            return None
        if wb.sniff(data) == "image/jxl":
            data = self.transcode(data)
        return data if wb.sniff(data) in IMAGES else None

    def process(self, item: dict, engine) -> dict:
        raw = item["raw"]
        try:
            version = engine.version
            data = self.load_image(item)
            if data is None:
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

    def sent(self, sha: str, route: str, result: str) -> None:
        """Một dòng mỗi lần gửi: không chữ OCR, không khóa, không địa chỉ."""
        line = {"sha256": sha, "route": route, "at": cursors.now_iso(self.clock()), "result": result}
        with (self.reads.parent / "sent.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line) + "\n")

    def ask(self, sha: str, member: dict) -> dict:
        """Che ảnh rồi gửi cả hai đường (đường đã có kết quả thì thôi). Không che được thì không gửi gì (Q3)."""
        try:
            primary = reads.load(self.reads, sha, self.engine.name, self.engine.version)
            data = self.load_image(member)
            hidden = redact.redact(data, primary, self.prepare) if data and primary else None
            if hidden is None:
                return {"sha": sha, "status": "no_image"}
            for name in gemini_module.ROUTES:
                have = reads.load(self.reads, sha, name, self.gemini.model)
                if have and (not have.get("error") or have.get("tries", 0) >= TRIES):
                    continue
                entry = {"engine": name, "version": self.gemini.model, "read_at": cursors.now_iso(self.clock()), "confidence": None}
                try:
                    entry.update(self.gemini.ask(name, hidden[0]))
                    self.sent(sha, name, "ok")
                except gemini_module.AskError as exc:
                    entry.update(error=exc.code, tries=(have or {}).get("tries", 0) + 1)
                    self.sent(sha, name, exc.code)
                reads.save(self.reads, sha, entry)
            return {"sha": sha, "status": "ok"}
        except ocr.OcrUnavailable:
            return {"sha": sha, "status": "unavailable"}
        except Exception:  # noqa: BLE001
            return {"sha": sha, "status": "error"}

    def finish_ask(self, outcome: dict, now: float) -> None:
        member = self.state()["members"].get(outcome["sha"])
        if member is None:
            return
        if outcome["status"] == "no_image":
            member["by"] = "human"
            return
        primary = reads.load(self.reads, outcome["sha"], self.engine.name, self.engine.version)
        member["by"] = self.decide(outcome["sha"], primary)
        if member["by"] is None:   # đường Gemini lỗi: hỏi lại sau, lâu dần
            tries = max((reads.load(self.reads, outcome["sha"], name, self.gemini.model) or {}).get("tries", 1) for name in gemini_module.ROUTES)
            member["next_ask"] = now + RETRY_ASK * tries

    def collect(self) -> tuple[bool, str | None]:
        """(đã thu một việc, mã lỗi). Chỉ luồng chính đụng con trỏ; luồng nền chỉ ghi kho kết quả và `sent.jsonl`."""
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
        cursor, now = self.state(), self.clock()
        if outcome["status"] == "unavailable":
            return False, "ocr_unavailable"
        if "raw" not in outcome:   # việc hỏi Gemini
            self.finish_ask(outcome, now)
            self.save(now)
            return True, None
        item = next((todo for todo in cursor["todo"] if todo["raw"] == outcome["raw"]), None)
        if item is None:   # nhóm bị bỏ chọn trong lúc đọc: kết quả nằm trong kho nhưng không vào `members`
            return True, None
        if outcome["status"] == "ok":
            sha = outcome["sha"]
            cursor["canon"][outcome["raw"]] = sha
            cursor["members"][sha] = {"raw": item["raw"], "file": item["file"], "ts": item["ts"], "verdict": outcome["verdict"],
                                      "by": self.decide(sha, reads.load(self.reads, sha, self.engine.name, self.engine.version))}
            cursor["todo"].remove(item)
        else:
            item["tries"] += 1
            if item["tries"] >= TRIES:
                cursor["todo"].remove(item)
                cursor["failed"] = [*cursor["failed"], item["raw"]][-MAX_FAILED:]
        self.save(now)
        return True, None

    def submit(self, now: float) -> None:
        cursor = self.state()
        if self.future is not None:
            return
        if self.executor is None:
            self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="money_ocr")
        if cursor["todo"]:
            self.future = self.executor.submit(self.process, dict(max(cursor["todo"], key=lambda item: item["ts"])), self.engine)   # mới nhất trước
        elif self.asking():
            due = [(member["ts"], sha) for sha, member in cursor["members"].items()
                   if member.get("verdict") == "unsure" and member.get("by") is None and now >= member.get("next_ask", 0)]
            if due:
                sha = max(due)[1]
                self.future = self.executor.submit(self.ask, sha, dict(cursor["members"][sha]))

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
        self.submit(now)
        return self.result("read" if worked else "idle", error or self.export(now))

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
