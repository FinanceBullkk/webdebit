#!/usr/bin/env python3
"""ZALO-GROUP-01: dựng gói web chat Zalo từ kho của zalo-audit-viewer, chỉ gồm group đã chọn (stdlib).

Chạy ở máy có Zalo PC. `--source` là thư mục `live-sync-20261030` của viewer: công cụ chỉ đọc kho đó,
chỉ ghi `web-groups.json` (danh sách group được lên web) cạnh kho. Gói ghi ra `--out`:

    export-report.json      ghi cuối cùng; `data_dir` trỏ tới thư mục dữ liệu của lượt dựng
    data-<giờ>/             conversations.json, users.json, messages.jsonl, media.json (bất biến sau khi ghi)
    media/<sha256>.<đuôi>   ảnh/video đã kiểm, dùng lại giữa các lượt
    media-cache.json        sha256 của URL → file đã tải hoặc lần lỗi gần nhất (không lưu URL)

Gói không có URL CDN, đường dẫn máy, băm URL hay hội thoại không được chọn. Ảnh chỉ tải từ
`*.zdn.vn`/`*.zadn.vn` như viewer; ảnh JXL của Zalo đổi sang JPEG khi có `pillow-jxl-plugin`.
Không log nội dung tin.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import unicodedata
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

SELECTION = "web-groups.json"
REPORT = "export-report.json"
CACHE = "media-cache.json"
VN = timezone(timedelta(hours=7))
ALLOWED_HOSTS = (".zdn.vn", ".zadn.vn")
IMAGE_TYPES = {2, 7}          # ảnh, GIF
URL_KEYS = ("normalUrl", "oriUrl", "hdUrl")   # bản thường đủ xem, nhẹ hơn bản HD
MAX_BYTES = 30 * 1024 * 1024
RETRY_AFTER = 7 * 24 * 3600   # URL lỗi thì 7 ngày sau mới thử lại
KEEP_DATA_DIRS = 2            # lượt hiện tại và lượt trước (server có thể còn đọc lượt trước)
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp", "video/mp4": ".mp4"}
CONVERSATION_ID = re.compile(r"[0-9a-f]{64}")


class BundleError(Exception):
    pass


def fold(text: str) -> str:
    stripped = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return stripped.replace("đ", "d").replace("Đ", "D").casefold()


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise BundleError(f"thiếu {path.name} trong kho nguồn") from None
    except ValueError as exc:
        raise BundleError(f"{path.name} không đọc được") from exc


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def dump(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def sniff(data: bytes) -> str | None:
    """Kiểu file theo byte đầu; không tin đuôi file hay header của CDN."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\xff\x0a") or data.startswith(b"\x00\x00\x00\x0cJXL \r\n\x87\n"):
        return "image/jxl"
    if data[4:8] == b"ftyp":
        return "video/mp4"
    return None


def transcode_jxl(data: bytes) -> bytes:
    """JXL → JPEG; thiếu Pillow/pillow-jxl thì ném ImportError, lượt dựng đếm vào media_failed."""
    import pillow_jxl  # noqa: F401  (đăng ký codec JXL với Pillow)
    from PIL import Image
    with Image.open(io.BytesIO(data)) as decoded:
        out = io.BytesIO()
        decoded.convert("RGB").save(out, "JPEG", quality=88)
        return out.getvalue()


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "ZaloAudit/1.0 (local viewer)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise BundleError("file quá lớn")
    return data


def allowed(url: object) -> bool:
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    host = (urlsplit(url).hostname or "").lower()
    return host.endswith(ALLOWED_HOSTS)


def parse_params(body: dict) -> dict:
    params = body.get("params")
    if isinstance(params, str) and params.startswith("{"):
        try:
            parsed = json.loads(params)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def clean_body(body: object):
    """Chỉ giữ chữ người dùng đọc được: chuỗi giữ nguyên; thẻ giữ title/description/thời lượng/kích thước."""
    if body is None or isinstance(body, str):
        return body
    if isinstance(body, list):
        return [clean_body(item) for item in body if isinstance(item, dict)]
    if not isinstance(body, dict):
        return None
    clean = {key: body[key] for key in ("title", "description")
             if isinstance(body.get(key), str) and not body[key].strip().lower().startswith(("http://", "https://"))}
    params = parse_params(body)
    for key in ("duration", "width", "height"):
        value = params.get(key, body.get(key))
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
            clean[key] = int(value)
    if isinstance(params.get("group_layout_id"), int | str):
        # Album: Zalo gửi nhiều ảnh thành nhiều tin cùng một nhóm; giữ để giao diện gộp lại.
        clean["album"] = hashlib.sha256(str(params["group_layout_id"]).encode()).hexdigest()[:16]
    return clean


class Source:
    """Kho của viewer: chỉ đọc, trừ web-groups.json."""

    def __init__(self, directory: Path):
        self.dir = directory
        if not (directory / "messages.jsonl").is_file():
            raise BundleError(f"{directory} không phải kho live-sync (thiếu messages.jsonl)")
        conversations = read_json(directory / "conversations.json")
        self.conversations = {row["conversation_id"]: row for row in conversations
                              if isinstance(row, dict) and isinstance(row.get("conversation_id"), str)}
        self.names = read_json(directory / "name-index.json", {}).get("items", {})
        self.meta = read_json(directory / "conv-meta.json", {}).get("conversations", {})
        users = read_json(directory / "user-index.json", {})
        self.users, self.self_user = users.get("users", {}), users.get("self_user")
        self.revision = read_json(directory / "revision.json", {}).get("revision")

    def is_group(self, cid: str) -> bool:
        return bool((self.meta.get(cid) or {}).get("is_group"))

    def selection(self) -> list[str]:
        document = read_json(self.dir / SELECTION, {"conversations": []})
        return [cid for cid in document.get("conversations", []) if isinstance(cid, str) and CONVERSATION_ID.fullmatch(cid)]

    def save_selection(self, ids: list[str]) -> None:
        write_atomic(self.dir / SELECTION, dump({"schema": 1, "conversations": sorted(set(ids))}))

    def stats(self) -> dict[str, tuple[int, int]]:
        """Số tin và giờ tin cuối mỗi hội thoại (đọc một lượt, không giữ nội dung)."""
        counts: dict[str, list[int]] = {}
        with (self.dir / "messages.jsonl").open("rb") as stream:
            for raw in stream:
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                cid = row.get("conversation_id")
                stamp = int(row["timestamp"]) if str(row.get("timestamp", "")).isdigit() else 0
                entry = counts.setdefault(cid, [0, 0])
                entry[0] += 1
                entry[1] = max(entry[1], stamp)
        return {cid: (count, last) for cid, (count, last) in counts.items()}

    def find(self, needle: str) -> list[str]:
        needle = needle.strip()
        if CONVERSATION_ID.fullmatch(needle):
            return [needle] if needle in self.conversations else []
        if len(needle) >= 8 and re.fullmatch(r"[0-9a-f]+", needle):
            return [cid for cid in self.conversations if cid.startswith(needle)]
        exact = [cid for cid in self.conversations if fold(self.names.get(cid) or "") == fold(needle)]
        return exact or [cid for cid in self.conversations if fold(needle) in fold(self.names.get(cid) or "")]


class Media:
    """Ảnh/video của gói: file đặt tên theo sha256 nội dung; cache theo sha256 của URL."""

    def __init__(self, out: Path, source: Source, fetch=fetch_url, transcode=transcode_jxl,
                 max_fetch: int = 300, now: float | None = None, max_age_days: int | None = None):
        self.out, self.source, self.fetch, self.transcode = out, source, fetch, transcode
        self.max_age_days = max_age_days
        self.dir = out / "media"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.cache = read_json(out / CACHE, {"urls": {}}).get("urls", {})
        self.budget = max_fetch
        self.now = time.time() if now is None else now
        self.items: dict[str, dict] = {}
        self.counts = dict.fromkeys(("local", "fetched", "cached", "missing", "pending", "failed"), 0)
        local = read_json(source.dir / "media-index.json", {"items": {}}).get("items", {})
        self.local: dict[str, list[dict]] = {}
        for opaque, item in local.items():
            if isinstance(item, dict) and isinstance(item.get("client_message_id"), str):
                self.local.setdefault(item["client_message_id"], []).append({**item, "opaque": opaque})

    def _store(self, data: bytes, width=None, height=None) -> str | None:
        mime = sniff(data)
        if mime == "image/jxl":
            try:
                data = self.transcode(data)
            except Exception:  # noqa: BLE001  (giải mã ảnh lỗi chỉ làm thiếu một ảnh, không dừng cả gói)
                self.counts["failed"] += 1
                return None
            mime = sniff(data)
        if mime not in EXTENSIONS:
            self.counts["failed"] += 1
            return None
        sha = hashlib.sha256(data).hexdigest()
        target = self.dir / (sha + EXTENSIONS[mime])
        if not target.is_file():
            write_atomic(target, data)
        self.items[sha] = {"mime": mime, "bytes": len(data), "width": width, "height": height}
        return sha

    def _known(self, sha: str, width=None, height=None) -> str | None:
        for mime, extension in EXTENSIONS.items():
            target = self.dir / (sha + extension)
            if target.is_file():
                self.items[sha] = {"mime": mime, "bytes": target.stat().st_size, "width": width, "height": height}
                return sha
        return None

    def for_message(self, row: dict, body: object) -> list[str]:
        found = []
        params = parse_params(body) if isinstance(body, dict) else {}
        width, height = params.get("width"), params.get("height")
        for item in self.local.get(row.get("client_message_id") or "", []):
            path = self.source.dir / "media-store" / (item["opaque"] + {"image/jxl": ".jxl"}.get(item.get("mime"), EXTENSIONS.get(item.get("mime"), "")))
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if hashlib.sha256(data).hexdigest() != item.get("sha256"):
                continue   # file local không khớp chỉ mục của viewer: bỏ, không tin
            sha = self._store(data, width, height)
            if sha:
                self.counts["local"] += 1
                found.append(sha)
        if found or row.get("message_type") not in IMAGE_TYPES or not isinstance(body, dict):
            return found
        urls = list(dict.fromkeys(body.get(key) for key in URL_KEYS if allowed(body.get(key))))
        if not urls:
            self.counts["missing"] += 1
            return []
        keys = [hashlib.sha256(url.encode("utf-8")).hexdigest() for url in urls]
        for key in keys:
            sha = (self.cache.get(key) or {}).get("sha256")
            if sha and self._known(sha, width, height):
                self.counts["cached"] += 1
                return [sha]
        stamp = int(row["timestamp"]) if str(row.get("timestamp", "")).isdigit() else 0
        too_old = self.max_age_days is not None and self.now - stamp / 1000 > self.max_age_days * 86400
        if too_old or all(self.now - (self.cache.get(key) or {}).get("failed_at", 0) < RETRY_AFTER for key in keys):
            self.counts["missing"] += 1
            return []
        if self.budget <= 0:
            self.counts["pending"] += 1
            return []
        self.budget -= 1
        for url, key in zip(urls, keys, strict=True):
            try:
                data = self.fetch(url)
            except Exception:  # noqa: BLE001  (CDN gỡ ảnh, mất mạng: ghi lần lỗi rồi thử URL kế)
                self.cache[key] = {"failed_at": int(self.now)}
                continue
            sha = self._store(data, width, height)
            if sha:
                self.cache[key] = {"sha256": sha}
                self.counts["fetched"] += 1
                return [sha]
            self.cache[key] = {"failed_at": int(self.now)}
        self.counts["missing"] += 1
        return []

    def save_cache(self) -> None:
        write_atomic(self.out / CACHE, dump({"schema": 1, "urls": self.cache}))


def build(source: Source, out: Path, *, fetch=fetch_url, transcode=transcode_jxl, max_fetch: int = 300,
          now: float | None = None, max_age_days: int | None = None) -> dict:
    chosen = [cid for cid in source.selection() if cid in source.conversations]
    if not chosen:
        raise BundleError("chưa chọn group nào: chạy `add` trước")
    out.mkdir(parents=True, exist_ok=True)
    media = Media(out, source, fetch, transcode, max_fetch, now, max_age_days)
    rows: dict[str, list[tuple[int, dict]]] = {cid: [] for cid in chosen}
    senders: set[str] = set()
    wanted: list[tuple[int, dict, dict]] = []   # tin có thể có ảnh/video: (giờ, tin gốc, tin đã làm sạch)
    with (source.dir / "messages.jsonl").open("rb") as stream:
        for raw in stream:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            cid = row.get("conversation_id")
            if cid not in rows:
                continue
            clean = {key: row.get(key) for key in ("message_id", "conversation_id", "sender_id", "timestamp", "server_time",
                                                     "message_type", "status", "body_state")}
            clean["body"] = clean_body(row.get("body"))
            stamp = int(row["timestamp"]) if str(row.get("timestamp", "")).isdigit() else 0
            if row.get("deleted"):
                clean["deleted"] = True
            elif row.get("message_type") in IMAGE_TYPES or row.get("client_message_id") in media.local:
                wanted.append((stamp, row, clean))
            rows[cid].append((stamp, clean))
            if isinstance(row.get("sender_id"), str):
                senders.add(row["sender_id"])
    # CDN của Zalo chỉ giữ ảnh khoảng 2–3 tuần (đo 1/11/2026): tải ảnh mới nhất trước khi hết lượt tải.
    for _, row, clean in sorted(wanted, key=lambda item: -item[0]):
        found = media.for_message(row, row.get("body"))
        if found:
            clean["media"] = found
    media.save_cache()
    built = datetime.fromtimestamp(time.time() if now is None else now, VN)
    data_name = "data-" + built.strftime("%Y%m%d-%H%M%S")
    data_dir = out / data_name
    if data_dir.exists():
        data_name += f"-{os.getpid()}"
        data_dir = out / data_name
    tmp = out / f".{data_name}.tmp"
    tmp.mkdir()
    conversations = [{"conversation_id": cid, "display_name": source.names.get(cid) or None,
                      "name_status": "name_index" if source.names.get(cid) else "unmatched",
                      "is_group": source.is_group(cid),
                      "participant_ids": list(source.conversations[cid].get("participant_ids") or []),
                      "message_count": len(rows[cid])} for cid in chosen]
    users = {"self_user": source.self_user, "users": {uid: source.users[uid] for uid in sorted(senders) if uid in source.users}}
    (tmp / "conversations.json").write_bytes(dump(conversations))
    (tmp / "users.json").write_bytes(dump(users))
    with (tmp / "messages.jsonl").open("wb") as stream:
        for cid in chosen:
            for _, clean in sorted(rows[cid], key=lambda item: (item[0], item[1].get("message_id") or "")):
                stream.write(dump(clean) + b"\n")
    (tmp / "media.json").write_bytes(dump(media.items))
    digest = hashlib.sha256()
    for name in ("conversations.json", "users.json", "messages.jsonl", "media.json"):
        digest.update((tmp / name).read_bytes())
    os.replace(tmp, data_dir)
    report = {"status": "BUNDLED", "schema": 1, "data_dir": data_name, "built_at": built.isoformat(timespec="seconds"),
              "source_revision": source.revision, "conversation_count": len(chosen),
              "message_count": sum(len(items) for items in rows.values()), "media_count": len(media.items),
              **{f"media_{key}": value for key, value in media.counts.items()}, "bundle_sha256": digest.hexdigest()}
    write_atomic(out / REPORT, dump(report))
    old = sorted(path for path in out.glob("data-*") if path.is_dir() and path.name != data_name)
    for index, path in enumerate(old):
        # Giữ lượt trước cho server đang đọc dở, trừ khi nó còn hội thoại vừa bị bỏ chọn: bỏ chọn là rời gói ngay.
        previous = {row.get("conversation_id") for row in read_json(path / "conversations.json", [])}
        if index < len(old) - (KEEP_DATA_DIRS - 1) or not previous <= set(chosen):
            shutil.rmtree(path, ignore_errors=True)
    # Ảnh cũng vậy: chỉ giữ file mà các lượt còn giữ dùng tới.
    keep = set(media.items)
    for path in out.glob("data-*/media.json"):
        keep.update(read_json(path, {}))
    for path in media.dir.iterdir():
        if path.is_file() and path.name.split(".", 1)[0] not in keep:
            path.unlink()
    return report


def day(stamp: int) -> str:
    return datetime.fromtimestamp(stamp / 1000, VN).strftime("%d/%m/%Y") if stamp else "—"


def cmd_list(source: Source, show_all: bool) -> None:
    chosen = set(source.selection())
    stats = source.stats()
    rows = [cid for cid in source.conversations if show_all or source.is_group(cid) or cid in chosen]
    rows.sort(key=lambda cid: -stats.get(cid, (0, 0))[1])
    print(f"{'web':4} {'id':8}  {'tin':>6}  {'tin cuối':10}  tên")
    for cid in rows:
        count, last = stats.get(cid, (0, 0))
        kind = "" if source.is_group(cid) else " (chat riêng)"
        print(f"{'[x]' if cid in chosen else '[ ]':4} {cid[:8]}  {count:>6}  {day(last):10}  {source.names.get(cid) or 'chưa rõ tên'}{kind}")
    print(f"\n{len(chosen)} hội thoại đang được lên web.")


def cmd_change(source: Source, needles: list[str], add: bool) -> int:
    chosen = set(source.selection())
    for needle in needles:
        matches = source.find(needle)
        if len(matches) != 1:
            print(f"“{needle}”: {'không thấy hội thoại nào' if not matches else f'{len(matches)} hội thoại khớp, ghi rõ hơn (8 ký tự đầu id)'}")
            for cid in matches[:10]:
                print(f"    {cid[:8]}  {source.names.get(cid) or 'chưa rõ tên'}")
            return 1
        cid = matches[0]
        if add and not source.is_group(cid):
            print(f"Lưu ý: {source.names.get(cid) or cid[:8]} là chat riêng, không phải group.")
        (chosen.add if add else chosen.discard)(cid)
        print(f"{'Thêm' if add else 'Bỏ'}: {cid[:8]}  {source.names.get(cid) or 'chưa rõ tên'}")
    source.save_selection(sorted(chosen))
    return 0


# Đẩy gói lên máy chủ qua ssh (G5). Thư mục đích trên máy chủ là bản gương của `--out`: chỉ gửi thư mục dữ liệu và ảnh
# máy chủ chưa có (cả hai bất biến theo tên), đổi export-report.json sau cùng bằng mv (server nạp lại khi file này đổi),
# rồi xóa phía máy chủ mọi thư mục dữ liệu và ảnh mà máy này không còn giữ: bỏ chọn group là rời máy chủ ở lượt đẩy kế tiếp.
TARGET = re.compile(r"(?P<host>[A-Za-z0-9][A-Za-z0-9.-]{0,62}):(?P<path>/[A-Za-z0-9_./-]{1,200})")
REMOTE_APPLY = r"""set -eu
cd "$1"
tar -xf - --no-same-owner --no-same-permissions
mv -f .incoming-report.json export-report.json
for d in data-*; do
  if [ -d "$d" ] && ! grep -qxF "$d" .keep-data; then rm -rf -- "$d"; fi
done
if [ -d media ]; then
  for f in media/*; do
    if [ -f "$f" ] && ! grep -qxF "${f#media/}" .keep-media; then rm -f -- "$f"; fi
  done
fi
rm -f .keep-data .keep-media
chmod -R u+rwX,g+rX,g-w,o-rwx .
"""


def ssh_run(host: str, command: str, stdin=None) -> str:
    import subprocess
    # Chạy theo lịch bằng pythonw: không mở cửa sổ console cho ssh.exe.
    done = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", host, command],
                          stdin=stdin, capture_output=True, check=False, timeout=1800,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        raise BundleError(f"ssh {host} lỗi (mã {done.returncode}): {done.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return done.stdout.decode("utf-8", "replace")


def push(out: Path, target: str, run=ssh_run) -> dict:
    import shlex
    import tarfile
    import tempfile
    match = TARGET.fullmatch(target)
    if not match or ".." in match["path"]:
        raise BundleError("--target phải dạng máy:/đường/dẫn tuyệt đối, ví dụ hao:/srv/v7/zalo-bundle")
    host, remote = match["host"], match["path"].rstrip("/")
    report = read_json(out / REPORT)
    data_dirs = sorted(path.name for path in out.glob("data-*") if path.is_dir())
    media = sorted(path.name for path in (out / "media").glob("*") if path.is_file() and ".tmp-" not in path.name)
    if report.get("data_dir") not in data_dirs:
        raise BundleError("gói chưa dựng xong (export-report.json trỏ tới thư mục dữ liệu không có)")
    there = run(host, f"cd {shlex.quote(remote)} && ls -1A && echo --- && (ls -1A media 2>/dev/null || true)").split("---")
    remote_dirs = set(there[0].split())
    remote_media = set(there[1].split()) if len(there) > 1 else set()
    new_dirs = [name for name in data_dirs if name not in remote_dirs]
    new_media = [name for name in media if name not in remote_media]

    def add(tar, name: str, data: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size, info.mode, info.mtime = len(data), 0o640, int(time.time())
        tar.addfile(info, io.BytesIO(data))

    with tempfile.TemporaryFile() as spool:
        with tarfile.open(fileobj=spool, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for name in new_dirs:
                for path in sorted((out / name).iterdir()):
                    add(tar, f"{name}/{path.name}", path.read_bytes())
            for name in new_media:
                add(tar, f"media/{name}", (out / "media" / name).read_bytes())
            add(tar, ".keep-data", ("\n".join(data_dirs) + "\n").encode())
            add(tar, ".keep-media", ("\n".join(media) + "\n").encode())
            add(tar, ".incoming-report.json", (out / REPORT).read_bytes())
        size = spool.tell()
        spool.seek(0)
        run(host, f"sh -c {shlex.quote(REMOTE_APPLY)} apply {shlex.quote(remote)}", stdin=spool)
    return {"data_sent": len(new_dirs), "media_sent": len(new_media), "bytes_sent": size, "data_dir": report["data_dir"]}


def log_line(out: Path, text: str) -> None:
    """Nhật ký đồng bộ (chỉ số đếm, không nội dung tin), giữ 500 dòng gần nhất."""
    path = out / "sync.log"
    lines = path.read_text(encoding="utf-8").splitlines()[-499:] if path.is_file() else []
    lines.append(f"{datetime.now(VN).isoformat(timespec='seconds')} {text}")
    write_atomic(path, ("\n".join(lines) + "\n").encode("utf-8"))


def cmd_sync(source: Source, out: Path, target: str, **build_args) -> int:
    """Lịch chạy định kỳ: dựng gói rồi đẩy. Chưa chọn group thì thôi, không lỗi. Hai lượt không chạy chồng nhau."""
    out.mkdir(parents=True, exist_ok=True)
    lock = out / "sync.lock"
    try:
        if lock.is_file() and time.time() - lock.stat().st_mtime > 2 * 3600:
            lock.unlink()   # lượt trước chết giữa chừng
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        log_line(out, "bỏ qua: lượt trước còn đang chạy")
        return 0
    try:
        os.close(fd)
        if not [cid for cid in source.selection() if cid in source.conversations]:
            log_line(out, "bỏ qua: chưa chọn group nào")
            return 0
        report = build(source, out, **build_args)
        sent = push(out, target)
        log_line(out, f"ok: {report['conversation_count']} group, {report['message_count']} tin, {report['media_count']} ảnh "
                      f"(tải mới {report['media_fetched']}, chờ {report['media_pending']}); gửi {sent['data_sent']} thư mục dữ liệu, "
                      f"{sent['media_sent']} ảnh, {sent['bytes_sent']} byte")
        print(f"Đã đẩy {sent['data_dir']} lên {target}: {sent['media_sent']} ảnh mới, {sent['bytes_sent']} byte.")
        return 0
    except BundleError as exc:
        log_line(out, f"lỗi: {exc}")
        raise
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    # Tên group tiếng Việt: đầu ra đi qua pipe hay Task Scheduler trên Windows mặc định cp1252 sẽ lỗi; in UTF-8, ký tự lạ thì thay.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Chọn group Zalo được lên web và dựng gói web (ZALO-GROUP-01).")
    parser.add_argument("--source", required=True, help="thư mục live-sync-20261030 của zalo-audit-viewer")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="liệt kê group, đánh dấu group đang lên web")
    listing.add_argument("--all", action="store_true", help="hiện cả chat riêng")
    for name in ("add", "remove"):
        sub.add_parser(name, help=f"{'thêm' if name == 'add' else 'bỏ'} group theo tên hoặc 8 ký tự đầu id").add_argument("needles", nargs="+")
    building = sub.add_parser("build", help="dựng gói web từ các group đã chọn")
    syncing = sub.add_parser("sync", help="dựng gói rồi đẩy lên máy chủ qua ssh (chạy theo lịch)")
    syncing.add_argument("--target", required=True, help="máy:/đường/dẫn trên máy chủ, ví dụ hao:/srv/v7/zalo-bundle")
    for command in (building, syncing):
        command.add_argument("--out", required=True)
        command.add_argument("--max-fetch", type=int, default=300, help="số ảnh tối đa tải từ Zalo mỗi lượt")
        command.add_argument("--no-fetch", action="store_true", help="không tải ảnh mới, chỉ dùng ảnh đã có")
        command.add_argument("--max-age-days", type=int, default=30,
                             help="không tải ảnh cũ hơn số ngày này (CDN của Zalo giữ ảnh khoảng 2–3 tuần)")
    args = parser.parse_args(argv)
    try:
        source = Source(Path(args.source))
        if args.command == "list":
            cmd_list(source, args.all)
            return 0
        if args.command in ("add", "remove"):
            return cmd_change(source, args.needles, args.command == "add")
        limits = {"max_fetch": 0 if args.no_fetch else args.max_fetch, "max_age_days": args.max_age_days}
        if args.command == "sync":
            return cmd_sync(source, Path(args.out), args.target, **limits)
        report = build(source, Path(args.out), **limits)
    except BundleError as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 2
    print(f"Gói web: {report['conversation_count']} group, {report['message_count']} tin, {report['media_count']} ảnh/video "
          f"(có sẵn {report['media_local']}, tải mới {report['media_fetched']}, đã có {report['media_cached']}, "
          f"không còn {report['media_missing']}, chờ lượt sau {report['media_pending']}, lỗi {report['media_failed']}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
