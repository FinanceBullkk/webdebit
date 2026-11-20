"""ZALO-AGENT-01 Phần 1–2: bộ xử lý `insurance`, giấy bảo hiểm lên `hao` (BAO-HIEM-ZALO-01).

Thay `insurance_web.py` + `insurance_push.py` + task `ZaloInsurancePush` của repo `zalo-audit-viewer` (nhánh `claude/bao-hiem-web`).
Kích hoạt **theo file đổi**, không theo revision: sha256 của `insurance-snapshot.json` (do `insurance_sync.py` ghi mỗi 15 phút) đổi,
hoặc kho PDF có file mới/đổi, hoặc đã 15 phút chưa hỏi `hao` (máy chủ mất file thì lượt sau tự gửi lại; máy chủ là nơi giữ trạng thái).

Bản gọn `insurance-web.json` giữ **nguyên hợp đồng** của `insurance_web.build` (schema_version 1, WHITELIST 13 trường, thứ tự dòng,
`sha256` tính trên các dòng, `row_count`, NULL vẫn NULL), nên `web/v7_insurance_queue.py` đọc như cũ. Không tên, mã số thuế, số vận
đơn, tàu, seal, giờ gửi hay chữ tin nhắn; giá trị riêng tư lọt vào `warnings` bị thay bằng `[redacted]`.

Đẩy qua kênh chung `push.py`: `pdf/<sha256>.pdf` (đặt tên theo nội dung nên cùng tên và cùng cỡ là đủ), `insurance-web.json` `mv` sau
cùng, dọn `pdf/*` không còn giấy nào dùng. Giấy có dòng mà máy này tạm không có PDF thì PDF đang có trên `hao` được giữ lại. Không đẩy
khi snapshot rỗng (0 dòng): không bao giờ để một snapshot hỏng dọn sạch `hao`. Không băm lại mọi PDF mỗi lượt: nhớ sha256 theo
(tên, cỡ, mtime) trong `<state>/insurance.json`; PDF đặt tên theo nội dung nên cache này an toàn. Lỗi chỉ là mã ngắn, không chữ tự do.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

from .. import cursor as cursors
from .. import push as pusher
from ..source import LiveSync, read_json, retry_io

NAME = "insurance"
SNAPSHOT = "insurance-snapshot.json"
STORE = "remote-media-store"
WEB = "insurance-web.json"
RESYNC = 15 * 60       # giây: lâu nhất giữa hai lần hỏi `hao` khi không có gì đổi tại máy
SCHEMA_VERSION = 1
AMOUNT_BASIS = "certificate total incl. VAT"
SHA_RE = re.compile(r"[0-9a-f]{64}")
# Trường riêng tư của dòng snapshot: không bao giờ chép, và bị xóa khỏi `warnings` nếu được trích ở đó.
PRIVATE_FIELDS = ("bl_no", "vessel", "insured", "policyholder", "insured_key", "policyholder_key",
                  "insured_tax_code", "policyholder_tax_code")
BL_IN_TEXT = re.compile(r"(B/L|BL|bill of lading)\s+\S+", re.IGNORECASE)


class SnapshotError(Exception):
    pass


# ---------------------------------------------------------------- bản gọn (chuyển từ insurance_web.py, giữ nguyên hành vi)

def as_text(value):
    return value if isinstance(value, str) else None


def as_int(value):
    """int giữ int, float nguyên / chuỗi số thành int, mọi thứ khác (None, rác, bool) là NULL, không bao giờ là 0."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,15}", value.strip()):
        return int(value.strip())
    return None


def private_values(row: dict) -> list[str]:
    values = {row[field] for field in PRIVATE_FIELDS if isinstance(row.get(field), str)}
    values.update(seal for seal in row.get("seals") or [] if isinstance(seal, str))
    return sorted((value.strip() for value in values if len(value.strip()) >= 3), key=len, reverse=True)


def clean_warning(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "[redacted]")
    return BL_IN_TEXT.sub(lambda match: match.group(1) + " [redacted]", text)


def compact_row(row: dict) -> dict:
    """Một dòng snapshot thành một dòng bản gọn. Không chép gì không có tên ở đây (WHITELIST)."""
    secrets = private_values(row)
    bookings = row.get("chat_bookings")
    return {
        "cert_no": as_text(row.get("cert_no")),
        "sha256": as_text(row.get("sha256")),
        "container": as_text(row.get("container")),
        "bookings": sorted({item for item in bookings if isinstance(item, str)}) if isinstance(bookings, list) else [],
        "amount_vnd": as_int(row.get("amount_vnd")),
        "cert_premium_vnd": as_int(row.get("cert_premium_vnd")),
        "cert_vat_vnd": as_int(row.get("cert_vat_vnd")),
        "cert_total_vnd": as_int(row.get("cert_total_vnd")),
        "containers_on_cert": as_int(row.get("containers_on_cert")),
        "depart_date": as_text(row.get("depart_date")),
        "issue_date": as_text(row.get("issue_date")),
        "status": as_text(row.get("status")),
        "warnings": [clean_warning(item, secrets) for item in (row.get("warnings") or []) if isinstance(item, str)],
    }


def build_rows(snapshot) -> list[dict]:
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or not isinstance(snapshot.get("rows"), list):
        raise SnapshotError("snapshot: schema_version lạ hoặc không có danh sách rows")
    return sorted((compact_row(row) for row in snapshot["rows"] if isinstance(row, dict)),
                  key=lambda row: (row["sha256"] or "", row["cert_no"] or "", row["container"] or ""))


def rows_hash(rows: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def encode(rows: list[dict], digest: str, created_at: str) -> bytes:
    payload = {"schema_version": SCHEMA_VERSION, "created_at": created_at, "amount_basis": AMOUNT_BASIS, "row_count": len(rows),
               "sha256": digest, "rows": rows}
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def reusable(raw: bytes | None, rows: list[dict], digest: str) -> bool:
    """File bản gọn cũ đã đúng những dòng này: giữ nguyên byte (kể cả `created_at`) để máy chủ không thấy đổi vô cớ."""
    try:
        have = json.loads(raw)
        return (have.get("schema_version") == SCHEMA_VERSION and have.get("amount_basis") == AMOUNT_BASIS
                and have.get("sha256") == digest and have.get("rows") == rows and have.get("row_count") == len(rows))
    except (TypeError, ValueError, AttributeError):
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------- bộ xử lý

class InsuranceProcessor:
    name = NAME

    def __init__(self, live: LiveSync, state: Path, work: Path, target: str, *, snapshot: Path | None = None, store: Path | None = None,
                 run=pusher.ssh_run, dry_run: bool = False, clock=time.time, resync: float = RESYNC):
        self.state, self.work, self.target = Path(state), Path(work), target
        self.snapshot = Path(snapshot) if snapshot else live.dir / SNAPSHOT
        self.store = Path(store) if store else live.dir / STORE
        self.run, self.dry_run, self.clock, self.resync = run, dry_run, clock, resync
        self.memory: dict | None = None   # --dry-run: nhớ trong tiến trình, không ghi đĩa

    def result(self, action: str, error: str | None = None, sent: int = 0, reason: str | None = None) -> dict:
        return {"action": action, "revision": None, "error": error, "bytes_sent": sent, "reason": reason}

    def load(self) -> dict:
        saved = self.memory if self.dry_run and self.memory is not None else read_json(self.state / f"{NAME}.json")
        return saved if isinstance(saved, dict) else {}

    def save(self, saved: dict, now: float) -> None:
        self.memory = saved
        if not self.dry_run:
            cursors.save(self.state, NAME, saved, now)

    def store_signature(self) -> str:
        entries = []
        for path in sorted(self.store.glob("*.pdf")):
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((path.name, stat.st_size, stat.st_mtime_ns))
        return hashlib.sha256(json.dumps(entries).encode()).hexdigest()

    def look(self) -> tuple[bytes | None, str | None, str]:
        """(nội dung snapshot, sha256 của nó, chữ ký kho PDF); rẻ: snapshot cỡ vài chục KB, kho cỡ vài chục file."""
        try:
            raw = self.snapshot.read_bytes()
        except OSError:
            raw = None
        return raw, hashlib.sha256(raw).hexdigest() if raw is not None else None, self.store_signature()

    def wants_work(self) -> bool:
        """Có đổi tại máy (snapshot hoặc kho PDF): vòng lặp gom 3 giây rồi mới xử lý. Lần hỏi định kỳ không tính."""
        _, sha, signature = self.look()
        saved = self.load()
        return sha is not None and (sha != saved.get("snapshot_sha256") or signature != saved.get("store_sig"))

    def scan(self, wanted: set[str], cache: dict) -> tuple[dict[str, Path], dict]:
        """({sha256 nội dung: đường dẫn}, cache mới). Kho đặt tên file theo băm URL nên phải băm nội dung; chỉ băm lại file có (cỡ, mtime) đổi."""
        found, fresh = {}, {}
        for path in sorted(self.store.glob("*.pdf")):
            try:
                stat = path.stat()
                entry = cache.get(path.name)
                if isinstance(entry, list) and len(entry) == 3 and entry[:2] == [stat.st_size, stat.st_mtime_ns] and \
                        isinstance(entry[2], str) and SHA_RE.fullmatch(entry[2]):
                    digest = entry[2]
                else:
                    digest = sha256_file(path)
            except OSError:
                continue
            fresh[path.name] = [stat.st_size, stat.st_mtime_ns, digest]
            if digest in wanted and digest not in found:
                found[digest] = path
        return found, fresh

    def web_bytes(self, rows: list[dict], now: float) -> bytes:
        path = self.work / WEB
        digest = rows_hash(rows)
        try:
            old = path.read_bytes()
        except OSError:
            old = None
        if reusable(old, rows, digest):
            return old
        data = encode(rows, digest, cursors.now_iso(now))
        self.work.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
        tmp.write_bytes(data)
        retry_io(lambda: os.replace(tmp, path))
        return data

    def step(self) -> dict:
        now = self.clock()
        raw, sha, signature = self.look()
        saved = self.load()
        if raw is None:   # chưa từng có snapshot (chưa cài insurance_sync): im; từng có rồi mất: lỗi
            return self.result("idle", "no_snapshot" if saved.get("snapshot_sha256") else None)
        asked = saved.get("checked_at")
        due = sha != saved.get("snapshot_sha256") or signature != saved.get("store_sig") or \
            not isinstance(asked, (int, float)) or now - asked >= self.resync or asked > now
        if not due:
            return self.result("idle")
        try:
            rows = build_rows(json.loads(raw))
        except (ValueError, SnapshotError):
            return self.result("idle", "snapshot_invalid")
        if not rows:   # không bao giờ để một snapshot rỗng dọn sạch `hao`
            return self.result("idle", "empty_snapshot")
        try:
            web = self.web_bytes(rows, now)
        except OSError:
            return self.result("idle", "build_failed")
        wanted = {row["sha256"] for row in rows if row["sha256"] and SHA_RE.fullmatch(row["sha256"])}
        found, cache = self.scan(wanted, saved.get("pdf_cache") if isinstance(saved.get("pdf_cache"), dict) else {})
        names = {digest: f"pdf/{digest}.pdf" for digest in wanted}
        plan = pusher.Plan(self.target, tuple(pusher.Item(names[digest], path, immutable=True) for digest, path in sorted(found.items())),
                           pusher.Item(WEB, web), ("pdf/*",), keep=tuple(names[digest] for digest in sorted(wanted - set(found))))
        sent, skipped, shipped = 0, True, []
        if not self.dry_run:
            try:
                done = pusher.push(plan, run=self.run)
            except pusher.PushError:
                self.save({**saved, "pdf_cache": cache}, now)   # băm PDF khỏi làm lại; snapshot_sha256 giữ cũ nên lượt sau thử lại
                return self.result("retry", "push_failed")
            sent, skipped, shipped = done["bytes"], done["skipped"], done["sent"]
        self.save({"snapshot_sha256": sha, "store_sig": signature, "checked_at": now, "pdf_cache": cache}, now)
        reason = f"rows={len(rows)} pdf_sent={sum(name.startswith('pdf/') for name in shipped)} missing_local={len(wanted) - len(found)}"
        return self.result("idle" if skipped else "push", sent=sent, reason=reason)
