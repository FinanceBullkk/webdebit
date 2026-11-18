"""Máy canh: bản sao ngoài máy còn được PC kéo về (CANH-BAO-01, bổ sung 18/11/2026; specs/v7-canh-bao.md).

PC kéo bằng SFTP chỉ đọc (`v7_offsite_pull.py`), nên trên hao chỉ còn dòng đăng nhập SSH "Accepted publickey … SHA256:…".
Mục này đọc các dòng đó trong journal (unit máy canh có nhóm `systemd-journal` qua drop-in, không cấp cho cả user `v7app`)
và so dấu vân khóa với `WEBDEBIT_OFFSITE_PULL_KEYS` (`nhãn=SHA256:…`, cách nhau bằng dấu phẩy, nằm ở `/etc/webdebit/alert.env`,
ngoài Git). Chưa khai khóa thì không kiểm. Nội dung báo chỉ có giờ, không IP, không khóa.

Lý do: 17/11/2026 lịch kéo trên một PC hỏng (thư mục đích mất), hai PC kia tắt; không gì báo (audit DevOps #2).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
from collections.abc import Callable
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
HOURS = int(os.getenv("WEBDEBIT_ALERT_OFFSITE_HOURS") or 48)   # người dùng: "không PC nào kéo backup quá 2 ngày" (18/11/2026)
ACCEPTED = re.compile(r"^Accepted publickey for \S+ from \S+ port \d+ \S+: \S+ (SHA256:\S+)$")


def keys(raw: str) -> set[str]:
    """`nhãn=SHA256:…` cách nhau bằng dấu phẩy hoặc khoảng trắng → tập dấu vân; nhãn chỉ để người đọc file cấu hình."""
    found = set()
    for item in re.split(r"[,\s]+", raw.strip()):
        _, _, fingerprint = item.partition("=")
        if fingerprint.startswith("SHA256:"):
            found.add(fingerprint)
    return found


def readable() -> bool:
    """Journal của hệ thống chỉ đọc được khi tiến trình có nhóm `systemd-journal` (hoặc là root). Thiếu nhóm thì journalctl
    vẫn thoát 0 nhưng chỉ trả dòng của chính user, nên phải hỏi trước, không thì "không thấy lần kéo nào" thành báo nhầm."""
    try:
        import grp  # chỉ có trên Unix; test chạy cả trên Windows
        gid = grp.getgrnam("systemd-journal").gr_gid
    except (ImportError, KeyError):
        return False
    return os.geteuid() == 0 or gid in os.getgroups()


def accepts(hours: int, run: Callable = subprocess.run) -> list[tuple[float, str]]:
    """(giờ unix, dấu vân) của mọi lần đăng nhập SSH bằng khóa trong `hours` giờ qua (OpenSSH 10 ghi dưới `sshd-session`)."""
    output = run(["journalctl", "--since", f"-{hours}h", "--output=json", "--output-fields=MESSAGE", "--no-pager",
                  "_COMM=sshd-session", "_COMM=sshd"], capture_output=True, text=True, timeout=60, check=True).stdout
    found = []
    for line in output.splitlines():
        try:
            entry = json.loads(line)
            match = ACCEPTED.match(str(entry.get("MESSAGE") or ""))
            if match:
                found.append((int(entry["__REALTIME_TIMESTAMP"]) / 1_000_000, match.group(1)))
        except (ValueError, KeyError, TypeError):
            continue
    return found


def check(now: float, *, wanted: set[str] | None = None, hours: int = HOURS,
          read: Callable[[int], list[tuple[float, str]]] = accepts, can_read: Callable[[], bool] = readable) -> list[str]:
    """Báo khi không khóa kéo nào đăng nhập trong `hours` giờ. Nhìn rộng thêm 24 giờ để nêu được lần kéo cuối."""
    wanted = keys(os.getenv("WEBDEBIT_OFFSITE_PULL_KEYS") or "") if wanted is None else wanted
    if not wanted:
        return []
    if not can_read():
        return ["Không đọc được log SSH để kiểm bản sao ngoài máy: unit máy canh thiếu nhóm systemd-journal."]
    window = hours + 24
    last = max((at for at, fingerprint in read(window) if fingerprint in wanted), default=None)
    if last is not None and now - last <= hours * 3600:
        return []
    when = (f"lần cuối {dt.datetime.fromtimestamp(last, VN):%H:%M ngày %d/%m}" if last is not None
            else f"không thấy lần nào trong {window} giờ")
    return [f"Không PC nào kéo bản sao ngoài máy quá {hours} giờ ({when}): xem lịch Webdebit V7 Backup Pull trên các PC."]
