"""ZALO-AGENT-01 Phần 2: kênh đẩy chung từ máy có Zalo lên `hao` (ssh + tar, stdlib).

Một "kế hoạch đẩy" (`Plan`) mô tả thư mục đích trên máy chủ: các file nên có, file chốt và luật dọn. `push` hỏi máy chủ
đang có gì (một lệnh ssh), chỉ gửi phần thiếu hoặc khác, rồi áp gói bằng đoạn shell `APPLY_SCRIPT`. Không có gì đổi và
không có gì cần dọn thì không gửi tar. Máy chủ là nơi giữ trạng thái: chết giữa lượt thì lượt sau tự khớp lại.

Quyền: `umask 027` ở đầu, không bao giờ `chmod` (chmod của tài khoản đẩy, không thuộc nhóm API, xóa bit setgid của thư
mục; lỗi 19/11/2026). Giải nén vào `.incoming-XXXXXX` (mktemp trong thư mục đích, `trap` dọn khi lỗi), chuyển file vào
chỗ bằng `mv`, file chốt `mv` sau mọi file khác (nó là thứ máy chủ nạp lại khi đổi), rồi mới dọn file không còn trong
kế hoạch, để người đọc đang theo file chốt cũ không bị mất dữ liệu trước khi file chốt mới hiện.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import shlex
import subprocess
import tarfile
import tempfile
import time
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path

TARGET = re.compile(r"(?P<host>[A-Za-z0-9][A-Za-z0-9.-]{0,62}):(?P<path>/[A-Za-z0-9_./-]{1,200})")
REL = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,120}(?:/[A-Za-z0-9_][A-Za-z0-9_.-]{0,120}){0,3}")
PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.*-]{0,60}(?:/[A-Za-z0-9_.*-]{1,60})?")

INVENTORY_SCRIPT = r"""set -eu
cd "$1"
shift
find . -type f ! -path './.incoming-*' -printf '%P\t%s\n'
echo ---
for f in "$@"; do
  if [ -f "$f" ]; then sha256sum -- "$f"; fi
done
"""

APPLY_SCRIPT = r"""set -eu
umask 027
cd "$1"
final="$2"
shift 2
find . -maxdepth 1 -name '.incoming-*' -mmin +60 -exec rm -rf -- {} + 2>/dev/null || true
tmp=$(mktemp -d .incoming-XXXXXX)
trap 'rm -rf -- "$tmp"' EXIT
tar -xf - -C "$tmp" --no-same-owner --no-same-permissions
while IFS= read -r f; do
  d=$(dirname -- "$f")
  if [ "$d" != . ]; then mkdir -p -- "$d"; fi
  mv -f -- "$tmp/$f" "$f"
done < "$tmp/.list"
mv -f -- "$tmp/$final" "$final"
for pattern in "$@"; do
  for p in $pattern; do
    if [ -e "$p" ] && ! grep -qxF -- "$p" "$tmp/.keep"; then rm -rf -- "$p"; fi
  done
done
"""


class PushError(Exception):
    pass


@dataclass(frozen=True)
class Item:
    """Một file của kế hoạch. `immutable`: đã có trên máy chủ cùng tên và cùng cỡ là đủ (file đặt tên theo nội dung
    hoặc không bao giờ đổi); ngược lại so sha256."""
    rel: str
    source: Path | bytes
    immutable: bool = False

    def size(self) -> int:
        return len(self.source) if isinstance(self.source, bytes) else self.source.stat().st_size

    def data(self) -> bytes:
        return self.source if isinstance(self.source, bytes) else self.source.read_bytes()

    def sha256(self) -> str:
        return hashlib.sha256(self.data()).hexdigest()


@dataclass(frozen=True)
class Plan:
    target: str                    # máy:/đường/dẫn
    files: tuple[Item, ...]        # mọi file nên có (trừ file chốt), theo thứ tự cài
    final: Item                    # file chốt, nằm thẳng trong thư mục đích
    prune: tuple[str, ...] = ()    # mẫu như `data-*` hoặc `media/*`: mục khớp mà không có trong kế hoạch bị xóa
    keep: tuple[str, ...] = ()     # tên mà máy chủ đang có thì giữ, không gửi (nguồn tại máy tạm mất): không bị dọn


def ssh_run(host: str, command: str, stdin=None) -> str:
    """Lượt hỏi (không stdin) tối đa 120 giây; lượt gửi tar thêm 1 giây mỗi 100 KB, tối đa 30 phút. Mọi lỗi chạy ssh
    (quá giờ, thiếu ssh.exe) đổi thành PushError để vòng lặp của agent không chết."""
    size = os.fstat(stdin.fileno()).st_size if stdin is not None else 0
    options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]
    try:
        # Chạy theo lịch bằng pythonw: không mở cửa sổ console cho ssh.exe.
        done = subprocess.run(["ssh", *options, host, command], stdin=subprocess.DEVNULL if stdin is None else stdin,
                              capture_output=True, check=False, timeout=min(1800, 120 + size // 100_000),
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        raise PushError(f"ssh {host} quá thời gian") from None
    except OSError as exc:
        raise PushError(f"không chạy được ssh: {type(exc).__name__}") from None
    if done.returncode != 0:
        raise PushError(f"ssh {host} lỗi (mã {done.returncode}): {done.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return done.stdout.decode("utf-8", "replace")


def command(script: str, remote: str, *args: str) -> str:
    return " ".join(["sh -c", shlex.quote(script), "run", shlex.quote(remote), *(shlex.quote(arg) for arg in args)])


def validate(plan: Plan) -> tuple[str, str]:
    match = TARGET.fullmatch(plan.target)
    if not match or ".." in match["path"]:
        raise PushError("đích phải dạng máy:/đường/dẫn tuyệt đối, ví dụ hao:/srv/v7/zalo-bundle")
    held = [*(item.rel for item in plan.files), *plan.keep]
    if len(set(held)) != len(held) or plan.final.rel in held or "/" in plan.final.rel:
        raise PushError("kế hoạch đẩy có file trùng tên hoặc file chốt không nằm thẳng trong thư mục đích")
    if not all(REL.fullmatch(rel) and ".." not in rel for rel in [*held, plan.final.rel]) or \
            not all(PATTERN.fullmatch(pattern) and ".." not in pattern for pattern in plan.prune):
        raise PushError("tên file hoặc mẫu dọn trong kế hoạch đẩy không hợp lệ")
    return match["host"], match["path"].rstrip("/")


def unit(rel: str, pattern: str) -> str:
    return "/".join(rel.split("/")[:pattern.count("/") + 1])


def survey(plan: Plan, host: str, remote: str, run) -> tuple[dict[str, int], dict[str, str]]:
    mutable = [item.rel for item in (*plan.files, plan.final) if not item.immutable]
    text = run(host, command(INVENTORY_SCRIPT, remote, *mutable))
    listing, _, hashes = text.partition("---\n")
    sizes = {}
    for line in listing.splitlines():
        name, _, size = line.partition("\t")
        if name and size.isdigit():
            sizes[name] = int(size)
    shas = {}
    for line in hashes.splitlines():
        sha, _, name = line.partition(" ")   # Linux: "sha  tên"; Git Bash: "sha *tên"
        if len(sha) == 64 and name.lstrip(" *"):
            shas[name.lstrip(" *")] = sha
    return sizes, shas


def push(plan: Plan, run=ssh_run) -> dict:
    """Đẩy một kế hoạch. Trả {sent: [đường dẫn file đã gửi], bytes, skipped}."""
    host, remote = validate(plan)
    held = [*(item.rel for item in plan.files), *plan.keep]   # giữ trên máy chủ: file sẽ gửi và file "giữ nếu có"
    if plan.files or plan.prune:
        sizes, shas = survey(plan, host, remote, run)
        send = [item for item in plan.files
                if sizes.get(item.rel) != item.size() or (not item.immutable and shas.get(item.rel) != item.sha256())]
        planned = set(held) | {plan.final.rel}
        known = {pattern: {unit(name, pattern) for name in planned} for pattern in plan.prune}
        # Glob của shell bỏ qua tên bắt đầu bằng dấu chấm còn fnmatch thì không: bỏ chúng khi so.
        stale = any(fnmatchcase(unit(rel, pattern), pattern) and not unit(rel, pattern).rsplit("/", 1)[-1].startswith(".")
                    and unit(rel, pattern) not in known[pattern] for rel in sizes for pattern in plan.prune)
        if not send and not stale and shas.get(plan.final.rel) == plan.final.sha256():
            return {"sent": [], "bytes": 0, "skipped": True}
    else:
        send = []   # thư mục chỉ có file chốt (nhịp tim): luôn gửi, khỏi hỏi máy chủ
    ancestors = {"/".join(rel.split("/")[:depth]) for rel in held for depth in range(1, rel.count("/") + 1)}

    def add(tar, name: str, data: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size, info.mode, info.mtime = len(data), 0o640, int(time.time())
        tar.addfile(info, io.BytesIO(data))

    with tempfile.TemporaryFile() as spool:
        with tarfile.open(fileobj=spool, mode="w", format=tarfile.PAX_FORMAT) as tar:
            for item in send:
                add(tar, item.rel, item.data())
            add(tar, ".list", "".join(f"{item.rel}\n" for item in send).encode())
            add(tar, ".keep", "".join(f"{name}\n" for name in [*held, *sorted(ancestors)]).encode())
            add(tar, plan.final.rel, plan.final.data())
        size = spool.tell()
        spool.seek(0)
        run(host, command(APPLY_SCRIPT, remote, plan.final.rel, *plan.prune), stdin=spool)
    return {"sent": [item.rel for item in send] + [plan.final.rel], "bytes": size, "skipped": False}
