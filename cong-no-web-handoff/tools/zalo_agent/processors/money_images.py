"""ZALO-AGENT-01 Phần 3-4: bộ xử lý `money_images`, đọc OCR ảnh của nhóm đã chọn tại máy có Zalo, hỏi Gemini khi cần (ANH-GEMINI-01).

Nguồn ảnh (A2, 23/11/2026): **gói chat do chính agent dựng** (`<root>/bundle`, bộ xử lý `bundle` chạy trước trong cùng vòng lặp), một
đường cho ảnh Zalo có ở máy, ảnh Zalo chỉ còn ở CDN (gói đã tải về) và ảnh WeChat (`wechat.merge_into`/`adopt` đã gộp vào gói). Gói đổi
(dấu `export-report.json`: thư mục dữ liệu, băm, delta) thì quét lại cả gói: gói đã giới hạn ở nhóm đã chọn và 30 ngày, vài trăm dòng.
Khóa kho kết quả là sha256 của byte trong `media/<sha256>.<đuôi>` của gói (JXL đã chuyển JPEG), trùng tên file trên `hao`. Cùng ảnh gửi
ở hai tin chỉ đọc một lần. Tin ảnh mà gói không có byte (CDN hết hạn, tải hỏng), mục `media.json` không phải ảnh, thiếu file hay quá
`max_age_days` thì không vào hàng đọc và được đếm theo lý do (`counts.skipped_*`).

Ảnh WeChat (người dùng chốt "Đọc, chưa cộng", 23/11/2026, `docs/decisions/wechat-01.md`): đọc OCR và lưu kết quả tại máy như ảnh Zalo,
nhưng **không xuất vào `money-reads.json`** (nên không vào tổng trang Thu chi), không hỏi Gemini, không dựng ảnh che, chỉ đếm vào
`counts.wechat`; cờ `export_wechat` (`--money-wechat-export`, mặc định tắt) để bật sau khi người dùng chốt lại.

OCR và việc hỏi Gemini chạy ở **một luồng nền**, mỗi lần một việc (OCR ảnh mới trước, hỏi Gemini sau): `step()` chỉ nộp việc, thu kết
quả và ghi con trỏ, nên 14 giây mỗi ảnh không chặn `bundle` hay `insurance` trong cùng vòng lặp. Con trỏ `money_images.json` giữ hàng chờ
(`todo`) nên chết giữa chừng thì lượt sau đọc tiếp. `members` = ảnh của nhóm đang chọn đã có kết quả: tập duy nhất được phép xuất ra
ngoài, nên nhóm bị bỏ chọn rồi dựng lại thì ảnh của nhóm đó rời tập.

Kết luận từng ảnh (`members[sha]["by"]`, ANH-GEMINI-01 mục 4): `ocr` khi OCR chắc; ảnh có dấu hiệu tiền mà OCR không chắc thì gửi ảnh
ĐÃ CHE tới cả hai đường Gemini: hai đường cùng một số thì `gemini-2`, lệch hoặc lỗi hoặc không che được thì `human`; không dấu hiệu tiền
thì không kết luận và không rời máy. Gửi ra ngoài tắt (mặc định, hoặc `--dry-run`) thì ảnh không chắc đi thẳng `human`. Kết quả Gemini lưu
trong kho như một lượt đọc (`gemini-proxy@<model>`, `gemini-api@<model>`); đường lỗi lưu mã lỗi và số lần thử, thử lại sau 10 phút x lần
thử, đủ 3 lần thì `human`. Mỗi lần gửi ghi một dòng `sent.jsonl` (sha256, đường, giờ, kết quả hoặc mã lỗi).

Kho OCR theo phiên bản ô chữ (`engine.version`), luật phân tích theo `ocr.ANALYSIS` (A1): luồng chính đọc kho qua `current` (luồng nền qua
`ocr.refresh`, chỉ trong bộ nhớ), nên đổi luật phân tích không OCR lại ảnh nào. Con trỏ nhớ `analysis`: lần đầu chạy với luật mới thì
`reanalyse` kết luận lại cả `members` từ ô chữ đã lưu; ảnh nào đổi số tiền thì bỏ ảnh đã che (luật che dán lại đúng `amount_vnd`) để dựng lại.

`hao` nhận qua `push.py` tới `reads_target` (đích rỗng = tắt): file nhỏ `money-reads.json` (xem `export_bytes`) và, cho mỗi ảnh đã có kết
luận mà che được, ảnh đã che `redacted-w1/<sha256 ảnh gốc>.jpg` (cùng luật che như trước khi gửi Gemini; ảnh không che được thì không có file,
`hao` chỉ gửi chữ). Ảnh đã che nhớ ở `<root>/redacted-w1/`; `redacted/*` không còn trong kết quả thì bị dọn trên `hao`. Mọi hội thoại trong danh
sách đã chọn đều được xử lý, nhóm hay chat riêng 1-1 (không lọc theo `is_group`).

Mã lỗi: `ocr_unavailable` (thiếu easyocr/torch/Pillow), `no_bundle` (chưa có gói chat), `scan_failed`, `push_failed`, `bundle_stale` (gói còn hội
thoại vừa bỏ chọn: chưa xuất, chờ `bundle` dựng lại). Ảnh hỏng (sai băm, không giải mã được)
thử 3 lần rồi bỏ vào `failed` (cấm 1 ngày, `reread` vẫn đọc lại được), chỉ đếm vào `counts.failed`, không làm cả bộ xử lý báo lỗi.
Engine không dùng được (thiếu thư viện, lỗi DLL, thiếu model) là `ocr_unavailable`, không phải lỗi của ảnh: không tính lần thử, không vào `failed`. `--dry-run` không lưu con trỏ, không đẩy, không gửi ra ngoài (kho kết quả
vẫn ghi: việc tại máy, idempotent).
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import time
from collections import deque
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
IMAGES = ("image/jpeg", "image/png", "image/gif", "image/webp")
DELTA = "messages-delta.jsonl"
SOURCE = "bundle"        # nguồn ảnh của con trỏ; con trỏ cũ (live-sync `media-index.json`) thì bỏ hàng chờ cũ, quét lại từ gói
SKIPS = ("no_media", "not_image", "no_file", "too_old")   # lý do một tin ảnh không vào hàng đọc (`counts.skipped_<lý do>`)
WECHAT_LABEL = "WeChat · "   # nhãn hội thoại WeChat trong gói (`wechat.merge_into`)
TRIES = 3
RETRY_ASK = 600        # giây x số lần thử: chờ trước khi hỏi lại đường Gemini đã lỗi
RESEND = 3600          # giây: gửi lại `money-reads.json` dù không đổi (hao mất file thì tự có lại)
MAX_FAILED = 2000
FAILED_BAN = 24 * 3600   # giây: ảnh đã thử đủ 3 lần rồi bỏ thì lần dựng lại sau 1 ngày mới thử lại (`reread` đọc lại được ngay)
BROKEN = 60              # giây: lần đầu engine chưa dùng được (`ocr_unavailable`) thì không hỏi lại và không đòi gom revision trong chừng này
COOL = 60                # giây: lần đầu nghỉ sau khi tiến trình OCR chết hoặc quá giờ
MAX_WAIT = 3600          # giây: cả hai đều lùi lũy thừa (x2 mỗi lần liên tiếp) tới tối đa chừng này
DRAIN_WINDOW = 3600     # giây: tốc độ xả hàng chờ OCR = số ảnh rời hàng chờ (đọc xong hoặc bỏ sau 3 lần) trong chừng này


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
                 dry_run: bool = False, clock=time.time, max_age_days: int | None = 30, gemini=None, reads_target: str = "",
                 run=pusher.ssh_run, bundle_dir: Path | None = None, wechat_ids=None, export_wechat: bool = False, second=None):
        self.live, self.dir, self.reads = live, Path(state), Path(reads_dir)
        self.bundle = Path(bundle_dir) if bundle_dir is not None else Path(state).parent / "bundle"
        self.wechat_ids, self.export_wechat = wechat_ids, export_wechat
        self.engine = engine or ocr.EasyOcr(work=str(Path(state).parent / "tmp"))
        self.second = second   # engine đọc lần hai (RapidOcr) cho ảnh có số mà lần đọc chính không chắc; None = tắt (mặc định)
        self.gemini = gemini if gemini is not None else gemini_module.Gemini()
        self.executor, self.prepare = executor, prepare
        self.dry_run, self.clock, self.max_age_days = dry_run, clock, max_age_days
        self.reads_target, self.run = reads_target, run
        self.cursor: dict | None = None
        self.future = None
        self.broken_until = self.cool_until = 0.0
        self.engine_failures = self.broken_failures = 0
        self.hidden_dir = self.reads.parent / f"redacted-{redact.RULE}"   # phiên bản luật che nằm trong tên thư mục: đổi luật thì không dùng lại ảnh cũ
        self.export_scope = None
        self.export_dirty = True   # có gì đổi kể từ lần xuất trước (hoặc chưa xuất lần nào): chỉ khi đó mới dựng lại `money-reads.json`
        # Tốc độ xả hàng chờ OCR (status.json `drain`), chỉ nhớ trong tiến trình: chạy lại agent thì đo lại từ lúc khởi động.
        self.drained_at: deque[float] = deque()
        self.pending_since: float | None = None   # lúc hàng chờ từ rỗng sang có ảnh
        self.last_drained: float | None = None

    # ---------------------------------------------------------------- con trỏ (nguồn thật là bản trong bộ nhớ)
    def state(self) -> dict:
        if self.cursor is None:
            self.cursor = {"todo": [], "members": {}, "failed": {}, **(cursors.load(self.dir, NAME) or {})}
            if self.cursor.get("source") != SOURCE:   # con trỏ của nguồn cũ (live-sync): hàng chờ và ảnh hỏng mang tên file cũ, quét lại từ gói
                self.cursor.update(todo=[], failed={}, source=SOURCE, bundle_key=None)
                self.cursor.pop("canon", None)
            if self.cursor.get("redact_rule") != redact.RULE:   # luật che đã đổi: các quyết định "đã có ảnh che" cũ không còn đúng
                for member in self.cursor["members"].values():
                    member.pop("hidden", None)
                    member.pop("hide_tries", None)
                    member.pop("next_hide", None)
                self.cursor["redact_rule"] = redact.RULE
            for sha, member in self.cursor["members"].items():   # "đã có ảnh che" mà file đã mất (lượt trước chết trước khi lưu con trỏ): dựng lại
                if member.get("hidden") is True and not (self.hidden_dir / f"{sha}.jpg").is_file():
                    for key in ("hidden", "hide_tries", "next_hide"):
                        member.pop(key, None)
            if self.cursor.get("analysis") != ocr.ANALYSIS or self.second is not None:   # một lần mỗi lần nạp con trỏ; có lần đọc hai thì kết luận lại cả ảnh đã đọc hai sau `reread`
                self.reanalyse()
        return self.cursor

    def reanalyse(self) -> None:
        """Luật phân tích đã đổi: kết luận lại mọi ảnh trong `members` từ ô chữ đã lưu (không gọi engine). Ảnh đổi nhóm (`verdict`) thì
        quyết lại `by` (có thể phải hỏi Gemini). Ảnh che chỉ dựng lại theo số mới khi kết luận (mới) là `ocr`: xem `current`. Thiếu engine thì để
        lần nạp con trỏ sau (ảnh vào lại `members` khi dựng lại mỗi đêm cũng đi qua `current`)."""
        cursor = self.cursor
        try:
            name, version = self.engine.name, self.engine.version
        except ocr.OcrUnavailable:
            return
        held = False
        for sha, member in cursor["members"].items():
            stored = reads.load(self.reads, sha, name, version)
            read = self.current(sha, stored)
            if read is None:
                continue
            if ocr.refresh(read) is not read:   # `current` không xóa được ảnh che: ảnh này giữ luật cũ
                held = True
            kind = ocr.verdict(read)
            if kind == member.get("verdict"):
                continue
            moved = member.get("by"), member.get("verdict")
            member["verdict"], member["by"] = kind, self.decide(sha, read, member.get("wechat", False))
            if member["by"] == "ocr" and read.get("amount_vnd") != stored.get("amount_vnd") and not self.dry_run:   # vừa thành `ocr`, số khác: ảnh che cũ sai số
                try:
                    self.drop_hidden(sha)
                except OSError:   # Windows còn giữ file: trả ảnh này về luật cũ (kho và kết luận), lần nạp sau thử lại
                    reads.save(self.reads, sha, stored)
                    member["by"], member["verdict"] = moved
                    held = True
                    continue
            for key in ("ask_tries", "next_ask"):
                member.pop(key, None)
        if not held:   # còn ảnh giữ luật cũ thì chưa đánh dấu: lần nạp con trỏ sau phân tích lại
            cursor["analysis"] = ocr.ANALYSIS
        self.export_dirty = True

    def with_second(self, sha: str, read: dict | None) -> dict | None:
        """Lượt đọc chính kèm `second` (tóm tắt lần đọc hai của engine thứ hai: không chữ, không ô chữ) khi kho có lần đọc đó. Chỉ trong bộ nhớ:
        không ghi kho. Không có lần đọc hai thì trả nguyên đối tượng."""
        if self.second is None or not read or not isinstance(read.get("boxes"), list):
            return read
        mine = [item for item in reads.for_image(self.reads, sha) if item.get("engine") == self.second.name and not item.get("error")]
        found = ocr.refresh(max(mine, key=lambda item: item.get("read_at", ""), default=None))
        if not found:
            return read
        return {**read, "second": {key: found.get(key) for key in ("engine", "version", "amount_vnd", "confidence", "unique")}}

    def read_second(self, sha: str, data: bytes) -> None:
        """(Luồng nền) đọc lần hai rồi ghi kho riêng của engine thứ hai. Lỗi của engine này không làm hỏng lần đọc chính: ảnh vẫn theo luật cũ."""
        try:
            version = self.second.version
            if reads.load(self.reads, sha, self.second.name, version):
                return
            image, size = self.prepare(data)
            boxes = self.second.read(image)
            reads.save(self.reads, sha, {"engine": self.second.name, "version": version, "read_at": cursors.now_iso(self.clock()), "size": list(size),
                                         "boxes": boxes, **ocr.stamped(boxes)})
        except Exception:  # noqa: BLE001  (OcrUnavailable, OcrFailure, ảnh lạ: lần đọc hai chỉ là phần thêm)
            return

    def current(self, sha: str, read: dict | None) -> dict | None:
        """(Chỉ luồng chính) lượt đọc OCR theo luật phân tích hiện tại, kèm lần đọc hai nếu có (`with_second`). Lệch luật thì ghi lại file kho (cùng tên, ô chữ giữ nguyên).

        Số tiền OCR đổi: ảnh chưa vào `members` hoặc đang kết luận `ocr` (số xuất ra là số OCR) thì xóa ảnh đã che **trước** khi ghi kho, để luồng
        nền dựng lại theo số mới; xóa không được thì giữ nguyên luật cũ cho ảnh này (lần nạp sau thử lại). Ảnh `gemini-2`/`human` giữ ảnh che và số
        đã có: ảnh che đó là ảnh đã gửi Gemini, dựng lại theo số OCR mới thì lệch với số Gemini mà không ai hỏi lại. `--dry-run` chỉ tính trong bộ
        nhớ, không ghi kho, không xóa gì (con trỏ không được lưu nên mọi thay đổi trên đĩa sẽ lệch với nó)."""
        fresh = ocr.refresh(read)
        if fresh is read or self.dry_run:
            return self.with_second(sha, fresh)
        member = (self.cursor or {}).get("members", {}).get(sha)
        if fresh.get("amount_vnd") != read.get("amount_vnd") and (member is None or member.get("by") in (None, "ocr")):
            try:
                self.drop_hidden(sha)
            except OSError:
                return self.with_second(sha, read)
        reads.save(self.reads, sha, fresh)
        return self.with_second(sha, fresh)

    def drop_hidden(self, sha: str) -> None:
        """Xóa ảnh đã che của một ảnh (thử lại khi Windows giữ file) và quyết định che trong `members`. Ném OSError khi không xóa được."""
        path = self.hidden_dir / f"{sha}.jpg"
        with contextlib.suppress(FileNotFoundError):
            retry_io(path.unlink)
        for key in ("hidden", "hide_tries", "next_hide"):
            (self.cursor or {}).get("members", {}).get(sha, {}).pop(key, None)

    def save(self, now: float) -> None:
        if not self.dry_run:
            cursors.save(self.dir, NAME, self.state(), now)

    def counts(self) -> dict:
        cursor = self.state()
        members = cursor["members"].values()
        banned = sum(1 for entry in cursor["failed"].values() if self.clock() - entry["at"] < FAILED_BAN)   # hết hạn cấm thì không còn tính
        shown = [member for member in members if self.exported(member)]
        return {"read": len(cursor["members"]), "pending": len(cursor["todo"]), "failed": banned,
                "review": sum(1 for member in shown if member.get("by") == "human"),
                "asking": sum(1 for member in shown if member.get("verdict") == "unsure" and member.get("by") is None),
                "wechat": sum(1 for member in members if member.get("wechat")),
                **{f"skipped_{reason}": (cursor.get("skipped") or {}).get(reason, 0) for reason in SKIPS}}

    def exported(self, member: dict) -> bool:
        """Ảnh được phép vào `money-reads.json` (và hỏi Gemini, dựng ảnh che): mọi ảnh Zalo; ảnh WeChat chỉ khi bật `export_wechat`."""
        return not member.get("wechat") or self.export_wechat

    def result(self, action: str, error: str | None = None) -> dict:
        return {"action": action, "revision": self.revision(), "error": error, "bytes_sent": 0, "reason": None, "counts": self.counts(),
                "drain": self.drain()}

    def revision(self) -> int | None:
        """Revision live-sync mà bộ xử lý đã theo kịp (status.json tính `lag_revisions` từ đây). Đã quét đúng gói hiện tại thì là revision
        `bundle` đã xử lý (con trỏ `bundle`): `bundle` chỉ tiến con trỏ mà không ghi lại gói khi revision mới không có tin của nhóm đã chọn,
        nên revision trong `export-report.json` tụt lại và tab Máy chạy báo "đang đuổi kịp" mãi (review #601)."""
        cursor = self.state()
        have = cursor.get("revision")
        if cursor.get("bundle_key") is None or cursor.get("bundle_key") != self.bundle_key():
            return have
        bundle = cursors.load(self.dir, "bundle") or {}
        done = bundle.get("revision")
        if bundle.get("pending") or not isinstance(done, int) or (isinstance(have, int) and done < have):
            return have
        return done

    def drain(self) -> dict:
        """Tốc độ xả hàng chờ: `done_1h` ảnh rời hàng chờ trong 60 phút qua, `pending_since` (hàng chờ có ảnh từ lúc nào),
        `last_done_at`. `hao` coi hàng chờ đứng khi còn ảnh mà quá 15 phút kể từ mốc muộn hơn trong hai mốc đó không ảnh nào xong."""
        now = self.clock()
        while self.drained_at and now - self.drained_at[0] > DRAIN_WINDOW:
            self.drained_at.popleft()
        if not self.state()["todo"]:
            self.pending_since = None
        elif self.pending_since is None:
            self.pending_since = now
        return {"done_1h": len(self.drained_at), "pending_since": None if self.pending_since is None else cursors.now_iso(self.pending_since),
                "last_done_at": None if self.last_drained is None else cursors.now_iso(self.last_drained)}

    def drained(self, now: float) -> None:
        self.drained_at.append(now)
        self.last_drained = now

    # ---------------------------------------------------------------- kết luận (ANH-GEMINI-01 mục 4)
    def asking(self) -> bool:
        """Gửi ra ngoài đang bật và đủ hai đường. `--dry-run` không bao giờ gửi ảnh ra ngoài."""
        return self.gemini.ready and not self.dry_run

    def decide(self, sha: str, primary: dict | None, wechat: bool = False) -> str | None:
        """`ocr`, `gemini-2` hoặc `human`; None khi chưa có kết luận (không dấu hiệu tiền, hoặc đang chờ Gemini). Ảnh WeChat không xuất
        thì không hỏi Gemini (ảnh không rời máy khi không dùng tới)."""
        kind = ocr.verdict(primary)
        if kind != "unsure":
            return "ocr" if kind == "ocr" else None
        if not self.asking() or (wechat and not self.export_wechat):
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
        return ocr.refresh(max(exact or mine, key=lambda read: read.get("read_at", ""), default=None))

    def export_bytes(self, members: dict) -> bytes:
        """`{"schema": 1, "reads": {sha256: {by, amount_vnd, txn_time, bank, reads: [{engine, version, amount_vnd, confidence}]}}}` cho ảnh
        có dấu hiệu tiền, đã có kết luận và đã quyết xong chuyện ảnh đã che (có file hoặc không che được: để `hao` không gửi chữ trước rồi mới có
        ảnh). Không chữ OCR, không số tài khoản, không tên, không ô chữ; `human` thì số tiền để trống (số OCR đoán nằm trong `reads` kèm độ tin
        cậy). Không có giờ tạo file nên không đổi dữ liệu thì không đổi byte. Từ luật `a3` mỗi mục thêm `direction` (`in`/`out`/null), chỉ có khi
        `by` = `ocr` (Gemini chưa trả trường này): **`hao` chưa dùng nó để đếm hay đổi chiều thu/chi** (đổi luật đếm phải hỏi người dùng,
        `specs/zalo-thu-chi-real-time.md` CÒN MỞ). `txn_ref` (mã giao dịch) chỉ nằm trong kho tại máy, không xuất (review #599: chuỗi sau nhãn có thể
        là số điện thoại hay tên trong lời nhắn)."""
        items = {}
        for sha, member in sorted(members.items()):
            by = member.get("by")
            if by is None or member.get("hidden") is None:
                continue
            done = [ocr.refresh(read) for read in reads.for_image(self.reads, sha) if not read.get("error")]
            item = {"by": by, "amount_vnd": None, "txn_time": None, "bank": None, "direction": None,
                    "reads": [{"engine": read["engine"], "version": read["version"], "amount_vnd": read.get("amount_vnd"),
                               "confidence": read.get("confidence")} for read in done]}
            if by == "ocr":
                primary = self.primary_read(done)
                item.update({key: (primary or {}).get(key) for key in ("amount_vnd", "txn_time", "bank", "direction")})
            elif by == "gemini-2":
                found = {read["engine"]: read for read in done if read["engine"] in gemini_module.ROUTES}
                first, second = (found.get(name, {}) for name in gemini_module.ROUTES)
                item.update({key: first.get(key) if first.get(key) == second.get(key) else None for key in ("amount_vnd", "txn_time", "bank")})
            items[sha] = item
        return json.dumps({"schema": 1, "redact": redact.RULE, "reads": items}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def redacted_files(self, members: dict) -> list[pusher.Item]:
        """Ảnh đã che đã dựng sẵn (ở luồng nền) của mọi ảnh trong tập xuất. Chỉ liệt kê file, không giải mã gì ở vòng chính. Tên theo băm ảnh
        GỐC nên nội dung có thể đổi (luật phân tích mới đổi số tiền thì ảnh che dựng lại): so sha256 với hao, không chỉ so cỡ."""
        return [pusher.Item(f"redacted-{redact.RULE}/{sha}.jpg", self.hidden_dir / f"{sha}.jpg")
                for sha, member in sorted(members.items())
                if member.get("by") is not None and member.get("hidden") is True and (self.hidden_dir / f"{sha}.jpg").is_file()]

    def export(self, now: float) -> str | None:
        """Đẩy `money-reads.json` và `redacted/*` khi có đổi (cờ bẩn, không dựng lại mỗi giây) hoặc mỗi giờ. Chỉ xuất khi gói đã quét không
        còn hội thoại nào ngoài nhóm đang chọn (vừa bỏ chọn mà gói chưa dựng lại thì chờ); chọn rỗng thì xuất rỗng. Ảnh WeChat không xuất
        trừ khi bật `export_wechat`."""
        cursor, selection = self.state(), self.live.selection()
        if not self.reads_target or self.dry_run:
            return None
        due = now - cursor.get("pushed_at", 0) >= RESEND
        wanted = sorted({*selection, *(self.wechat_ids() if self.wechat_ids else ())}) if selection else []
        scope = cursors.selection_sha256(wanted) if wanted else ""
        if scope != self.export_scope:   # đổi nhóm đã chọn (kể cả bỏ chọn hết) cũng là có đổi
            self.export_dirty = True
        if not (self.export_dirty or due):
            return None
        allowed = {*wanted, *(cursor.get("wechat_conversations") or ())}   # ảnh WeChat không bao giờ xuất khi chưa bật cờ
        if selection and not set(cursor.get("conversations") or ()) <= allowed:
            # vừa bỏ chọn một nhóm, gói chưa dựng lại: members còn ảnh của nhóm đó. Báo mã (status) để gói không dựng lại được thì không im lặng.
            return "bundle_stale"
        members = {sha: member for sha, member in cursor["members"].items() if self.exported(member)} if selection else {}
        data = self.export_bytes(members)
        digest = hashlib.sha256(data).hexdigest()
        if digest == cursor.get("pushed_sha") and not due:
            self.export_dirty, self.export_scope = False, scope
            return None
        try:
            plan = pusher.Plan(self.reads_target, tuple(self.redacted_files(members)), pusher.Item(EXPORT, data), (f"redacted-{redact.RULE}/*", "redacted-*"))
            pusher.push(plan, run=self.run)
        except pusher.PushError:
            return "push_failed"
        cursor.update(pushed_sha=digest, pushed_at=now)
        self.export_dirty, self.export_scope = False, scope
        self.save(now)
        return None

    # ---------------------------------------------------------------- phát hiện ảnh mới: từ gói chat do chính agent dựng (A2)
    def bundle_key(self) -> str | None:
        """Dấu của gói chat hiện tại (thư mục dữ liệu, băm, byte và số dòng delta), hoặc None khi chưa có gói. `bundle` ghi
        `export-report.json` sau cùng (sau delta, `media.json`, phần WeChat), nên dấu đổi là mọi file của lượt đó đã xong."""
        report = read_json(self.bundle / wb.REPORT, {}) or {}
        data = report.get("data_dir")
        if not (isinstance(data, str) and data.startswith("data-") and (self.bundle / data).is_dir()):
            return None
        return f"{data}:{report.get('bundle_sha256')}:{report.get('delta_bytes', 0)}:{report.get('delta_lines', 0)}"

    def wants_work(self) -> bool:
        """Gói chat vừa đổi (vòng lặp gom 3 giây). Hàng chờ OCR không tính: nó tự chạy mỗi nhịp."""
        if self.clock() < self.broken_until or not self.live.selection():
            return False   # engine hỏng: không đòi gom 3 giây mỗi vòng cho cả agent (review L8); bỏ chọn hết: gói cũ không còn là nguồn
        key = self.bundle_key()
        return key is not None and key != self.state().get("bundle_key")

    def wechat_conversations(self, names: dict[str, str]) -> set[str]:
        """Hội thoại WeChat của gói: theo danh sách của bộ xử lý `wechat` (nếu có) và theo nhãn "WeChat · " mà `wechat.merge_into` đặt.
        Nhận thừa thì chỉ là ảnh Zalo không xuất ra; nhận thiếu mới nguy (ảnh nhóm nội bộ thành khoản thu), nên lấy hợp của hai nguồn."""
        listed = set(self.wechat_ids() if self.wechat_ids else ())
        return listed | {cid for cid, name in names.items() if isinstance(name, str) and name.startswith(WECHAT_LABEL)}

    def scan(self, now: float) -> tuple[dict[str, dict], dict[str, int], dict, list[str], list[str]]:
        """(ảnh theo sha256, số ảnh bỏ qua theo lý do, báo cáo gói, hội thoại của gói, hội thoại WeChat của gói). Đọc `messages.jsonl` rồi `messages-delta.jsonl` của
        thư mục dữ liệu hiện tại (dòng sau của cùng `message_id` thắng: tin sửa, tin xóa). Một đường cho ảnh Zalo có ở máy, ảnh Zalo tải từ
        CDN và ảnh WeChat: gói đã có sẵn byte ở `media/<sha256>.<đuôi>` (JXL đã chuyển JPEG), cùng khóa với kho kết quả và tên file trên `hao`."""
        report = read_json(self.bundle / wb.REPORT, {}) or {}
        data = self.bundle / report["data_dir"]
        media = read_json(data / "media.json", {}) or {}
        conversations = [item for item in read_json(data / "conversations.json", []) or [] if isinstance(item, dict)]
        names = {item.get("conversation_id"): item.get("display_name") for item in conversations}
        wechat = self.wechat_conversations(names)
        since = int((now - self.max_age_days * 86400) * 1000) if self.max_age_days else 0
        latest: dict[str, dict] = {}
        for name in ("messages.jsonl", DELTA):
            path = data / name
            if not path.is_file():
                continue
            for line in retry_io(path.read_bytes).splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and isinstance(row.get("message_id"), str):
                    latest[row["message_id"]] = row
        images: dict[str, dict] = {}
        skipped = dict.fromkeys(SKIPS, 0)
        for row in latest.values():
            if row.get("deleted") or row.get("message_type") not in wb.IMAGE_TYPES:
                continue
            stamp = int(row["timestamp"]) if str(row.get("timestamp", "")).isdigit() else 0
            if stamp < since:
                skipped["too_old"] += 1
                continue
            shas = [sha for sha in row.get("media") or [] if isinstance(sha, str) and reads.SHA.fullmatch(sha)]
            if not shas:   # gói không có byte ảnh: CDN đã hết hạn hoặc tải hỏng, hoặc quá lượt tải của lần dựng
                skipped["no_media"] += 1
                continue
            for sha in shas:
                item = media.get(sha) if isinstance(media.get(sha), dict) else {}
                if item.get("mime") not in IMAGES:
                    skipped["not_image"] += 1
                    continue
                file = sha + wb.EXTENSIONS[item["mime"]]
                if not (self.bundle / "media" / file).is_file():
                    skipped["no_file"] += 1
                    continue
                entry = images.setdefault(sha, {"raw": sha, "file": file, "ts": stamp, "wechat": False})
                entry["ts"] = max(entry["ts"], stamp)
                entry["wechat"] = entry["wechat"] or row.get("conversation_id") in wechat   # cùng ảnh ở cả hai nguồn: coi là WeChat
        return images, skipped, report, sorted(cid for cid in names if isinstance(cid, str)), sorted(cid for cid in wechat if isinstance(cid, str))

    def discover(self, key: str, now: float) -> None:
        """Gói đổi thì quét lại cả gói (vài trăm dòng, đã giới hạn ở nhóm đã chọn và 30 ngày): `members` = ảnh của gói đã có kết quả (giữ
        nguyên kết luận, ảnh che, số lần thử của ảnh đã có), `todo` = ảnh chưa có kết quả và không bị cấm. Ảnh rời gói (bỏ chọn nhóm, quá hạn)
        rời `members`, nên không bao giờ được xuất."""
        cursor = self.state()
        if key == cursor.get("bundle_key"):
            return
        images, skipped, report, conversations, wechat = self.scan(now)
        banned = {raw for raw, entry in cursor["failed"].items() if now - entry["at"] < FAILED_BAN}
        version = self.engine.version
        before, waiting = cursor["members"], {item["raw"]: item for item in cursor["todo"]}
        members, todo = {}, []
        for sha, entry in sorted(images.items()):
            found = self.current(sha, reads.load(self.reads, sha, self.engine.name, version))
            if found:
                member = before.get(sha)
                if member is None:   # đã đọc (cùng engine và phiên bản): không đọc lại, chỉ vào tập `members`
                    member = {"verdict": ocr.verdict(found), "by": self.decide(sha, found, entry["wechat"])}
                    if (self.hidden_dir / f"{sha}.jpg").is_file():
                        member["hidden"] = True
                members[sha] = {**member, **entry}
            elif sha not in banned:
                todo.append({**entry, "tries": waiting.get(sha, {}).get("tries", 0)})
        cursor.update(members=members, todo=todo, skipped=skipped, conversations=conversations, wechat_conversations=wechat, bundle_key=key,
                      revision=report.get("revision", report.get("source_revision")), built_at=cursors.now_iso(now))
        self.export_dirty = True
        self.save(now)

    # ---------------------------------------------------------------- việc của luồng nền: đọc OCR một ảnh, hỏi Gemini một ảnh
    def load_image(self, item: dict) -> bytes | None:
        """Byte ảnh trong gói chat (`media/<sha256>.<đuôi>`), hoặc None khi file không khớp băm hay không phải ảnh."""
        data = retry_io((self.bundle / "media" / item["file"]).read_bytes)
        if hashlib.sha256(data).hexdigest() != item["raw"]:
            return None
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
                         "boxes": boxes, **ocr.stamped(boxes)}
                reads.save(self.reads, sha, found)
            else:   # đã có ô chữ của phiên bản này: luật phân tích mới chạy lại trong bộ nhớ, luồng chính ghi lại file (`current`)
                found = ocr.refresh(found)
            if self.second is not None and engine is self.engine and ocr.verdict(found) == "unsure" and found.get("amount_vnd"):
                self.read_second(sha, data)   # có số mà lần đọc chính không chắc: engine thứ hai đọc cho chắc
            return {"raw": raw, "status": "ok", "sha": sha, "verdict": ocr.verdict(self.with_second(sha, found))}
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
        primary = ocr.refresh(reads.load(self.reads, sha, self.engine.name, self.engine.version)) or self.primary_read(reads.for_image(self.reads, sha))
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
        member["by"] = self.decide(outcome["sha"], self.current(outcome["sha"], reads.load(self.reads, outcome["sha"], self.engine.name, self.engine.version)),
                                   member.get("wechat", False))
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
            entry = {key: item[key] for key in ("raw", "file", "ts", "wechat") if key in item}
            found = self.current(sha, reads.load(self.reads, sha, self.engine.name, self.engine.version))
            cursor["members"][sha] = {**entry, "verdict": ocr.verdict(found) if found else outcome["verdict"], "by": self.decide(sha, found, item.get("wechat", False))}
            cursor["todo"].remove(item)
            self.drained(now)
        else:
            item["tries"] += 1
            if item["tries"] >= TRIES:
                cursor["todo"].remove(item)
                self.drained(now)
                cursor["failed"][item["raw"]] = {"file": item["file"], "ts": item["ts"], "at": now, "wechat": item.get("wechat", False)}
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
               if self.asking() and self.exported(member) and member.get("verdict") == "unsure" and member.get("by") is None
               and now >= member.get("next_ask", 0)]
        if due:
            sha = max(due)[1]
            self.future = self.executor.submit(self.ask, sha, dict(members[sha]))
            return
        if self.reads_target and not self.dry_run:
            due = [(member["ts"], sha) for sha, member in members.items()
                   if self.exported(member) and member.get("by") is not None and member.get("hidden") is None and now >= member.get("next_hide", 0)]
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
        if not self.live.selection():   # bỏ chọn hết nhóm Zalo: `bundle` không dựng lại, gói còn của nhóm cũ nên không đọc tiếp
            return self.result("read" if worked else "idle", self.export(now))
        key = self.bundle_key()
        if key is None:   # chưa có gói chat (bộ xử lý `bundle` chưa dựng lần nào): vẫn đọc nốt hàng chờ đã có
            self.submit(now)
            return self.result("read" if worked else "idle", "no_bundle")
        try:
            self.discover(key, now)
        except (OSError, KeyError, TypeError):   # gói đang dở hoặc hỏng khuôn: lượt sau quét lại
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
        key = self.bundle_key()
        if key is not None and key != cursor.get("bundle_key"):   # con trỏ cũ (nguồn live-sync) hay gói mới: quét gói trước để tên file đúng
            self.discover(key, self.clock())
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
