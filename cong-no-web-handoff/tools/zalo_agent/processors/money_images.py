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

Mã lỗi: `ocr_unavailable` (thiếu easyocr/torch/Pillow), `no_revision`, `scan_failed`, `push_failed`. Ảnh hỏng (sai băm chỉ mục, không giải mã được)
thử 3 lần rồi bỏ vào `failed` (cấm 1 ngày, `reread` vẫn đọc lại được), chỉ đếm vào `counts.failed`, không làm cả bộ xử lý báo lỗi.
Engine không dùng được (thiếu thư viện, lỗi DLL, thiếu model) là `ocr_unavailable`, không phải lỗi của ảnh: không tính lần thử, không vào `failed`. `--dry-run` không lưu con trỏ, không đẩy, không gửi ra ngoài (kho kết quả
vẫn ghi: việc tại máy, idempotent).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import Future
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
FAILED_BAN = 24 * 3600   # giây: ảnh đã thử đủ 3 lần rồi bỏ thì lần dựng lại sau 1 ngày mới thử lại (`reread` đọc lại được ngay)
BROKEN = 60              # giây: lần đầu engine chưa dùng được (`ocr_unavailable`) thì không hỏi lại và không đòi gom revision trong chừng này
COOL = 60                # giây: lần đầu nghỉ sau khi tiến trình OCR chết hoặc quá giờ
MAX_WAIT = 3600          # giây: cả hai đều lùi lũy thừa (x2 mỗi lần liên tiếp) tới tối đa chừng này


def wait_for(first: int, failures: int) -> int:
    """Giây chờ sau lần hỏng thứ `failures` liên tiếp: first, 2 x first, … tối đa MAX_WAIT."""
    return min(MAX_WAIT, first * 2 ** (max(1, failures) - 1))


class Background:
    """Chạy mỗi việc ở một luồng **daemon**: thoát agent (`--once`) không chờ OCR đang đọc dở (review L7). Chỉ có một việc mỗi lúc."""

    def submit(self, function, *args) -> Future:
        future: Future = Future()

        def run() -> None:
            try:
                future.set_result(function(*args))
            except BaseException as exc:  # noqa: BLE001
                future.set_exception(exc)
        threading.Thread(target=run, name="money_ocr", daemon=True).start()
        return future


class MoneyImagesProcessor:
    name = NAME

    def __init__(self, live: LiveSync, state: Path, reads_dir: Path, *, engine=None, executor=None, prepare=ocr.prepare_image,
                 transcode=wb.transcode_jxl, dry_run: bool = False, clock=time.time, max_age_days: int | None = 30,
                 gemini=None, reads_target: str = "", run=pusher.ssh_run):
        self.live, self.dir, self.reads = live, Path(state), Path(reads_dir)
        self.engine = engine or ocr.EasyOcr(work=str(Path(state).parent / "tmp"))
        self.gemini = gemini if gemini is not None else gemini_module.Gemini()
        self.executor, self.prepare, self.transcode = executor, prepare, transcode
        self.dry_run, self.clock, self.max_age_days = dry_run, clock, max_age_days
        self.reads_target, self.run = reads_target, run
        self.cursor: dict | None = None
        self.future = None
        self.broken_until = self.cool_until = 0.0
        self.engine_failures = self.broken_failures = 0
        self.hidden_dir = self.reads.parent / "redacted"
        self.export_scope = None
        self.export_dirty = True   # có gì đổi kể từ lần xuất trước (hoặc chưa xuất lần nào): chỉ khi đó mới dựng lại `money-reads.json`

    # ---------------------------------------------------------------- con trỏ (nguồn thật là bản trong bộ nhớ)
    def state(self) -> dict:
        if self.cursor is None:
            self.cursor = {"todo": [], "members": {}, "canon": {}, "failed": {}, **(cursors.load(self.dir, NAME) or {})}
        return self.cursor

    def save(self, now: float) -> None:
        if not self.dry_run:
            cursors.save(self.dir, NAME, self.state(), now)

    def counts(self) -> dict:
        cursor = self.state()
        members = cursor["members"].values()
        banned = sum(1 for entry in cursor["failed"].values() if self.clock() - entry["at"] < FAILED_BAN)   # hết hạn cấm thì không còn tính
        return {"read": len(cursor["members"]), "pending": len(cursor["todo"]), "failed": banned,
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
        positive = all(answer["is_transfer"] and isinstance(answer["amount_vnd"], int) and answer["amount_vnd"] > 0 for answer in answers)
        return "gemini-2" if positive and first["amount_vnd"] == second["amount_vnd"] else "human"

    def primary_read(self, done: list[dict]) -> dict | None:
        """Kết quả của engine hiện tại: đúng phiên bản nếu có, không thì bản mới nhất của cùng engine (sau khi đổi engine hay `ANALYSIS`, ảnh cũ
        chưa được đọc lại thì vẫn có số để xuất, không ném)."""
        mine = [read for read in done if read.get("engine") == self.engine.name]
        exact = [read for read in mine if read.get("version") == self.engine.version]
        return max(exact or mine, key=lambda read: read.get("read_at", ""), default=None)

    def export_bytes(self, members: dict) -> bytes:
        """`{"schema": 1, "reads": {sha256: {by, amount_vnd, txn_time, bank, reads: [{engine, version, amount_vnd, confidence}]}}}` cho ảnh
        có dấu hiệu tiền, đã có kết luận và đã quyết xong chuyện ảnh đã che (có file hoặc không che được: để `hao` không gửi chữ trước rồi mới có
        ảnh). Không chữ OCR, không số tài khoản, không tên, không ô chữ; `human` thì số tiền để trống (số OCR đoán nằm trong `reads` kèm độ tin
        cậy). Không có giờ tạo file nên không đổi dữ liệu thì không đổi byte."""
        items = {}
        for sha, member in sorted(members.items()):
            by = member.get("by")
            if by is None or member.get("hidden") is None:
                continue
            done = [read for read in reads.for_image(self.reads, sha) if not read.get("error")]
            item = {"by": by, "amount_vnd": None, "txn_time": None, "bank": None,
                    "reads": [{"engine": read["engine"], "version": read["version"], "amount_vnd": read.get("amount_vnd"),
                               "confidence": read.get("confidence")} for read in done]}
            if by == "ocr":
                primary = self.primary_read(done)
                item.update({key: (primary or {}).get(key) for key in ("amount_vnd", "txn_time", "bank")})
            elif by == "gemini-2":
                found = {read["engine"]: read for read in done if read["engine"] in gemini_module.ROUTES}
                first, second = (found.get(name, {}) for name in gemini_module.ROUTES)
                item.update({key: first.get(key) if first.get(key) == second.get(key) else None for key in ("amount_vnd", "txn_time", "bank")})
            items[sha] = item
        return json.dumps({"schema": 1, "reads": items}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def redacted_files(self, members: dict) -> list[pusher.Item]:
        """Ảnh đã che đã dựng sẵn (ở luồng nền) của mọi ảnh trong tập xuất. Chỉ liệt kê file, không giải mã gì ở vòng chính."""
        return [pusher.Item(f"redacted/{sha}.jpg", self.hidden_dir / f"{sha}.jpg", immutable=True)
                for sha, member in sorted(members.items()) if member.get("by") is not None and member.get("hidden") is True]

    def export(self, now: float) -> str | None:
        """Đẩy `money-reads.json` và `redacted/*` khi có đổi (cờ bẩn, không dựng lại mỗi giây) hoặc mỗi giờ. Chỉ xuất khi `members` đúng với
        nhóm đang chọn; chọn rỗng thì xuất rỗng."""
        cursor, selection = self.state(), self.live.selection()
        if not self.reads_target or self.dry_run:
            return None
        due = now - cursor.get("pushed_at", 0) >= RESEND
        scope = cursors.selection_sha256(selection) if selection else ""
        if scope != self.export_scope:   # đổi nhóm đã chọn (kể cả bỏ chọn hết) cũng là có đổi
            self.export_dirty = True
        if not (self.export_dirty or due):
            return None
        if selection and cursor.get("selection_sha256") != cursors.selection_sha256(selection):
            return None   # vừa đổi nhóm, chưa dựng lại: members còn của nhóm cũ
        members = cursor["members"] if selection else {}
        data = self.export_bytes(members)
        digest = hashlib.sha256(data).hexdigest()
        if digest == cursor.get("pushed_sha") and not due:
            self.export_dirty, self.export_scope = False, scope
            return None
        try:
            plan = pusher.Plan(self.reads_target, tuple(self.redacted_files(members)), pusher.Item(EXPORT, data), ("redacted/*",))
            pusher.push(plan, run=self.run)
        except pusher.PushError:
            return "push_failed"
        cursor.update(pushed_sha=digest, pushed_at=now)
        self.export_dirty, self.export_scope = False, scope
        self.save(now)
        return None

    # ---------------------------------------------------------------- phát hiện ảnh mới
    def wants_work(self) -> bool:
        """Có revision mới hoặc phải dựng lại (vòng lặp gom 3 giây). Hàng chờ OCR không tính: nó tự chạy mỗi nhịp."""
        revision, selection, cursor = self.live.revision(), self.live.selection(), self.state()
        if revision is None or not selection or self.clock() < self.broken_until:
            return False   # engine hỏng: không đòi gom 3 giây mỗi vòng cho cả agent (review L8)
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
        waiting, now = {item["raw"] for item in cursor["todo"]}, self.clock()
        failed = {raw for raw, entry in cursor["failed"].items() if now - entry["at"] < FAILED_BAN}
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
                    if (self.hidden_dir / f"{sha}.jpg").is_file():
                        cursor["members"][sha]["hidden"] = True
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
        self.export_dirty = True
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
        except ocr.OcrFailure:   # tiến trình OCR chết hoặc quá giờ: lỗi của engine, chưa chắc của ảnh
            return {"raw": raw, "status": "engine_error"}
        except Exception:  # noqa: BLE001  (ảnh hỏng không được làm chết luồng nền)
            return {"raw": raw, "status": "error"}

    def sent(self, sha: str, route: str, result: str) -> None:
        """Một dòng mỗi lần gửi: không chữ OCR, không khóa, không địa chỉ."""
        line = {"sha256": sha, "route": route, "at": cursors.now_iso(self.clock()), "result": result}
        with (self.reads.parent / "sent.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(line) + "\n")

    def hidden_bytes(self, sha: str, member: dict) -> bytes | None:
        """Ảnh đã che của một ảnh (luồng nền): file đã dựng thì đọc lại, chưa thì dựng, nhớ ở `<root>/redacted/`. None khi không che được."""
        path = self.hidden_dir / f"{sha}.jpg"
        if path.is_file():
            return retry_io(path.read_bytes)
        primary = reads.load(self.reads, sha, self.engine.name, self.engine.version) or self.primary_read(reads.for_image(self.reads, sha))
        data = self.load_image(member)
        hidden = redact.redact(data, primary, self.prepare) if data and primary else None
        if hidden is None:
            return None
        self.hidden_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        tmp.write_bytes(hidden[0])
        retry_io(lambda: os.replace(tmp, path))
        return hidden[0]

    def hide(self, sha: str, member: dict) -> dict:
        try:
            return {"kind": "hide", "sha": sha, "status": "hidden" if self.hidden_bytes(sha, member) is not None else "unhideable"}
        except ocr.OcrUnavailable:
            return {"kind": "hide", "sha": sha, "status": "unavailable"}
        except Exception:  # noqa: BLE001
            return {"kind": "hide", "sha": sha, "status": "error"}

    def ask(self, sha: str, member: dict) -> dict:
        """Che ảnh rồi gửi cả hai đường (đường đã có kết quả thì thôi). Không che được thì không gửi gì (Q3)."""
        try:
            hidden = self.hidden_bytes(sha, member)
            if hidden is None:
                return {"kind": "ask", "sha": sha, "status": "no_image"}
            for name in gemini_module.ROUTES:
                have = reads.load(self.reads, sha, name, self.gemini.model)
                if have and (not have.get("error") or have.get("tries", 0) >= TRIES):
                    continue
                entry = {"engine": name, "version": self.gemini.model, "read_at": cursors.now_iso(self.clock()), "confidence": None}
                try:
                    entry.update(self.gemini.ask(name, hidden))
                    self.sent(sha, name, "ok")
                except gemini_module.AskError as exc:
                    entry.update(error=exc.code, tries=(have or {}).get("tries", 0) + 1)
                    self.sent(sha, name, exc.code)
                except Exception:  # noqa: BLE001  (lỗi lạ khi gửi: cũng tính một lần thử của đường đó)
                    entry.update(error="error", tries=(have or {}).get("tries", 0) + 1)
                    self.sent(sha, name, "error")
                reads.save(self.reads, sha, entry)
            return {"kind": "ask", "sha": sha, "status": "ok"}
        except ocr.OcrUnavailable:
            return {"kind": "ask", "sha": sha, "status": "unavailable"}
        except Exception:  # noqa: BLE001  (thiếu file media cũ, ghi đĩa lỗi…)
            return {"kind": "ask", "sha": sha, "status": "error"}

    def finish_job(self, outcome: dict, now: float) -> None:
        """Áp kết quả việc hỏi Gemini hoặc dựng ảnh che vào `members` (luồng chính)."""
        member = self.state()["members"].get(outcome["sha"])
        if member is None:
            return
        status = outcome["status"]
        if outcome["kind"] == "hide":
            if status in ("hidden", "unhideable"):
                member["hidden"] = status == "hidden"
            else:   # lỗi lạ: thử lại sau, đủ 3 lần thì coi như không che được (hao chỉ gửi chữ)
                member["hide_tries"] = member.get("hide_tries", 0) + 1
                member["next_hide"] = now + RETRY_ASK * member["hide_tries"]
                if member["hide_tries"] >= TRIES:
                    member["hidden"] = False
            return
        if status == "no_image":
            member["by"], member["hidden"] = "human", False
            return
        if status == "error":   # thiếu file media cũ, lỗi lạ: cũng đếm lần thử, đủ 3 lần thì để người xem (không lặp mỗi giây)
            member["ask_tries"] = member.get("ask_tries", 0) + 1
            member["next_ask"] = now + RETRY_ASK * member["ask_tries"]
            if member["ask_tries"] >= TRIES:
                member["by"] = "human"
            return
        member["hidden"] = True   # `hidden_bytes` đã dựng xong file trước khi gửi
        member["by"] = self.decide(outcome["sha"], reads.load(self.reads, outcome["sha"], self.engine.name, self.engine.version))
        if member["by"] is None:   # đường Gemini lỗi: hỏi lại sau, lâu dần
            tries = max((reads.load(self.reads, outcome["sha"], name, self.gemini.model) or {}).get("tries", 1) for name in gemini_module.ROUTES)
            member["next_ask"] = now + RETRY_ASK * tries

    def collect(self) -> tuple[bool, str | None]:
        """(đã thu một việc, mã lỗi). Chỉ luồng chính đụng con trỏ; luồng nền chỉ ghi kho kết quả, ảnh đã che và `sent.jsonl`."""
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
        if outcome["status"] == "unavailable":   # thiếu thư viện, lỗi nạp DLL, thiếu model, thiếu Pillow: không tính lần thử, không vào `failed`
            self.broken_failures += 1
            self.broken_until = now + wait_for(BROKEN, self.broken_failures)
            return False, "ocr_unavailable"
        self.export_dirty = True
        if "kind" in outcome:   # việc hỏi Gemini hoặc dựng ảnh che
            self.finish_job(outcome, now)
            self.save(now)
            return True, None
        if outcome["status"] == "engine_error":
            self.engine_failures += 1
            self.cool_until = now + wait_for(COOL, self.engine_failures)
        elif outcome["status"] == "ok":
            self.engine_failures = self.broken_failures = 0
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
                cursor["failed"][item["raw"]] = {"file": item["file"], "ts": item["ts"], "at": now}
                for old in sorted(cursor["failed"], key=lambda raw: cursor["failed"][raw]["at"])[:-MAX_FAILED]:
                    del cursor["failed"][old]
        self.save(now)
        return True, None

    def submit(self, now: float) -> None:
        """Một việc mỗi lúc, theo thứ tự: đọc OCR ảnh mới nhất, hỏi Gemini, dựng ảnh đã che (chỉ khi có đích xuất)."""
        cursor = self.state()
        if self.future is not None:
            return
        if self.executor is None:
            self.executor = Background()
        members = cursor["members"]
        if cursor["todo"]:
            if now >= self.cool_until:   # tiến trình OCR vừa chết: nghỉ rồi mới đọc tiếp
                self.future = self.executor.submit(self.process, dict(max(cursor["todo"], key=lambda item: item["ts"])), self.engine)   # mới nhất trước
            return
        due = [(member["ts"], sha) for sha, member in members.items()
               if self.asking() and member.get("verdict") == "unsure" and member.get("by") is None and now >= member.get("next_ask", 0)]
        if due:
            sha = max(due)[1]
            self.future = self.executor.submit(self.ask, sha, dict(members[sha]))
            return
        if self.reads_target and not self.dry_run:
            due = [(member["ts"], sha) for sha, member in members.items()
                   if member.get("by") is not None and member.get("hidden") is None and now >= member.get("next_hide", 0)]
            if due:
                sha = max(due)[1]
                self.future = self.executor.submit(self.hide, sha, dict(members[sha]))

    def step(self) -> dict:
        now = self.clock()
        worked, error = self.collect()   # luôn thu trước: kết quả của lần đọc đang chạy không được kẹt lại
        if error is None and now >= self.broken_until:
            try:
                _ = self.engine.version   # thiếu engine: báo ngay, đừng để hàng chờ rỗng che mất lỗi
            except ocr.OcrUnavailable:
                self.broken_failures += 1
                self.broken_until = now + wait_for(BROKEN, self.broken_failures)
                error = "ocr_unavailable"
        if error or now < self.broken_until:   # engine chưa dùng được: không phát hiện, không nộp việc, khỏi hỏi lại mỗi giây
            return self.result("read" if worked else "idle", error or "ocr_unavailable")
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
        Cùng engine và phiên bản thì bỏ qua. Gồm cả ảnh đã bị bỏ vào `failed` (thử lại bằng engine mới). Chỉ ghi kho kết quả, không đụng
        con trỏ (ảnh `failed` đọc được thì lần dựng lại sau hết hạn cấm sẽ nhận nó từ kho). Ném `OcrUnavailable` khi thiếu engine."""
        version = engine.version
        cursor = self.state()
        counts = {"wanted": 0, "read": 0, "had": 0, "failed": 0}
        candidates = list(cursor["members"].items()) + [(None, {"raw": raw, **entry}) for raw, entry in cursor["failed"].items()]
        for sha, member in sorted(candidates, key=lambda pair: -pair[1]["ts"]):
            if member["ts"] < since_ms:
                continue
            counts["wanted"] += 1
            if sha and reads.load(self.reads, sha, engine.name, version):
                counts["had"] += 1
                continue
            outcome = self.process(member, engine)
            if outcome["status"] == "unavailable":
                raise ocr.OcrUnavailable(engine.name)
            counts["read" if outcome["status"] == "ok" else "failed"] += 1
        return counts
