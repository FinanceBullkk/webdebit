#!/usr/bin/env python3
"""Máy canh: báo email khi máy công nợ lỗi hoặc dừng (CANH-BAO-01, specs/v7-canh-bao.md).

Chạy trên hao dưới user runner (timer v7-watchdog, 15 phút một lần):

    v7_watchdog.py [--dry-run] [--test-fail]

Mỗi lượt kiểm tại chỗ, chỉ đọc: web còn trả lời, lượt đối soát còn mới và không báo lỗi ghi, bản chụp Sheet còn mới, nguồn booking
còn chuyến mới, hộp việc của API còn tính được, các timer còn bật, sao lưu không lỗi, đĩa còn chỗ. Rồi báo về một check trên
healthchecks.io: ổn thì ping thường, có việc thì ping /fail kèm danh sách.
hao tắt hay mất mạng thì không còn ping và dịch vụ đó tự gửi email, nên không dùng Uptime Kuma nằm trên chính hao.

Nội dung gửi đi chỉ có mã và số đếm, không có tên khách hay số tiền. Chưa có WEBDEBIT_ALERT_PING_URL thì chỉ in ra journal.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HEALTHZ = "http://127.0.0.1:8780/healthz"
RECONCILE = "/var/lib/webdebit-sheet-sync/reconcile.json"
SNAPSHOT_DIR = "/var/lib/webdebit-sheet-sync"
SNAPSHOTS = ("snapshot.json", "prices.json", "receipts.json", "road.json", "ps.json")
SNAPSHOT_MAX_MINUTES = 60   # runner 15 phút một lần, lỗi lẻ tự lành ở lượt sau (audit DevOps #14: 5 lần trong 2 ngày)
# Nguồn booking là tab gộp phía Sheet (CONT_NGUON, CONT_BO): tab tháng mới chưa vào tab gộp thì bản chụp vẫn mới mà không thêm chuyến.
# Đo 18/11/2026 từ 1/5/2026: cả hai nguồn chưa từng trống quá 2 ngày liền, nên khung 3 ngày không báo nhầm; Tết thì báo là đúng.
SOURCES = (("snapshot.json", "chuyến biển (CONT_NGUON)"), ("road.json", "chuyến bộ (CONT_BO)"))
SOURCE_DAYS = int(os.getenv("WEBDEBIT_ALERT_SOURCE_DAYS") or 3)
# Hộp việc tính lại mỗi đợt bản chụp (15 phút): quá 90 phút là nhịp nền đã dừng. Sổ lỗi phải lặp 2 lượt liền mới báo (lỗi lẻ tự lành).
INBOX_MAX_MINUTES = 90
INBOX_FAILED_ROUNDS = 2
# Timer phải còn bật. Sao lưu có thêm số giờ tối đa từ lần chạy trước; các job 15 phút và đối soát đã có kiểm riêng theo kết quả.
TIMERS: dict[str, float | None] = {"v7-reconcile-auto": None, "webdebit-sheet-sync": None, "webdebit-sheet-prices": None,
                                   "webdebit-ps-snapshot": None, "v7-backup-hourly": 12, "v7-backup-daily": 26,
                                   "v7-backup-config": 26, "v7-backup-offsite": 26}
DISKS = ("/", "/srv", "/var/lib/postgresql")
DISK_MIN_FREE = 0.10
TEST_BODY = "Thử cảnh báo của máy công nợ, không có lỗi thật. Lượt kế sẽ báo ổn lại."


def now_vn() -> dt.datetime:
    return dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))


def check_api(url: str, opener: Callable = urllib.request.urlopen) -> list[str]:
    """/healthz chạy SELECT 1 qua đường psql của app, nên 200 nghĩa là cả API lẫn DB còn sống."""
    try:
        with opener(url, timeout=15) as response:
            code = response.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except OSError as exc:
        return [f"Web không trả lời ({type(exc).__name__})."]
    return [] if code == 200 else [f"Web báo lỗi ({code})."]


def check_reconcile(path: Path, now: dt.datetime) -> list[str]:
    """Cùng luật "có thể cũ" với tab Việc cần làm: một lượt lỗi lẻ thì lượt sau tự lành, quá 3 giờ trong ngày mới là máy đã dừng."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        checked = dt.datetime.fromisoformat(data["checked_at"]) if data.get("checked_at") else None
    except (OSError, ValueError, TypeError):
        return ["Không đọc được kết quả đối soát."]
    found = []
    code = (data.get("last_error") or {}).get("reason")
    tail = f" (lỗi gần nhất: {code})" if code else ""
    if checked is None:
        found.append(f"Máy đối soát chưa có lượt nào chạy được{tail}.")
    else:
        hours = (now - checked).total_seconds() / 3600
        if hours > 14 or (10 <= now.hour <= 22 and hours > 3):
            found.append(f"Máy đối soát chưa chạy được từ {checked:%H:%M ngày %d/%m}{tail}.")
    rows = data.get("customers") or []
    wrong = sum(row.get("reason") == "VERIFY_FAILED" for row in rows)
    failed = sum(row.get("reason") in ("WRITE_ERROR", "CHECK_ERROR") and row.get("error") != "STALE_LEDGER" for row in rows)
    if wrong:
        found.append(f"Máy đối soát ghi xong mà không khớp ở {wrong} khách. Cần xem ngay.")
    if failed:
        found.append(f"Máy đối soát lỗi khi xử lý {failed} khách.")
    # SHEET-LOG-01: log dừng thì máy không còn biết tab vừa sửa. Hết giờ hay lỗi lẻ của Google thì lượt sau tự lành; mã quyền thì không.
    edit_log = data.get("edit_log") or {}
    if edit_log.get("status") == "STALE":
        found.append("Log sửa Sheet không có dòng mới quá 26 giờ: bộ ghi Apps Script có thể đã dừng.")
    elif edit_log.get("status") == "UNAVAILABLE" and edit_log.get("reason") in ("401", "403", "404"):
        found.append(f"Máy không còn đọc được log sửa Sheet ({edit_log['reason']}).")
    return found


def check_snapshots(folder: Path, now: float) -> list[str]:
    found = []
    for name in SNAPSHOTS:
        try:
            minutes = (now - (folder / name).stat().st_mtime) / 60
        except OSError:
            found.append(f"Thiếu bản chụp Sheet {name}.")
            continue
        if minutes > SNAPSHOT_MAX_MINUTES:
            found.append(f"Bản chụp Sheet {name} đã cũ {int(minutes)} phút.")
    return found


def check_sources(folder: Path, today: dt.date, days: int = SOURCE_DAYS) -> list[str]:
    """Mỗi nguồn booking phải có chuyến mang ngày trong `days` ngày gần nhất (kể cả hôm nay). Thiếu hay hỏng file thì phần bản chụp
    và hộp việc đã báo; ở đây chỉ xét nội dung. Diễn tập 1/12 (18/11/2026): máy canh trước đây không thấy nguồn ngừng thêm dòng."""
    found = []
    since = today - dt.timedelta(days=days)
    for name, label in SOURCES:
        try:
            rows = json.loads((folder / name).read_text(encoding="utf-8")).get("rows") or []
        except (OSError, ValueError, AttributeError):
            continue
        dates = []
        for row in rows:
            try:
                dates.append(dt.date.fromisoformat(str((row or {}).get("event_date") or "")[:10]))
            except (ValueError, AttributeError):
                continue
        if any(since <= day <= today for day in dates):
            continue
        newest = max((day for day in dates if day <= today), default=None)
        since_text = f" từ {newest:%d/%m}" if newest else ""
        found.append(f"Nguồn {label} không có chuyến mới{since_text}, {days} ngày gần nhất trống: tab tháng mới có thể chưa vào tab gộp.")
    return found


def check_inbox(url: str, opener: Callable = urllib.request.urlopen) -> list[str]:
    """Hộp việc của API (dán chuyến, ghi giá, phí PS) qua phần `inbox` của /healthz. Web không trả lời thì phần web đã báo, ở đây im;
    API cũ chưa có phần này thì cũng im."""
    try:
        with opener(url, timeout=15) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:   # 503 khi DB lỗi: thân vẫn có hộp việc
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (OSError, ValueError, AttributeError):
            return []
    except (OSError, ValueError):
        return []
    inbox = body.get("inbox") if isinstance(body, dict) else None
    if not isinstance(inbox, dict):
        return []
    found = []
    if inbox.get("state") == "unavailable":
        found.append("Hộp việc không đọc được bản chụp Sheet: máy ngừng dán chuyến và ghi giá.")
    failed, rounds = inbox.get("failed") or 0, inbox.get("failed_rounds") or 0
    if failed and rounds >= INBOX_FAILED_ROUNDS:
        found.append(f"Hộp việc không tính được {failed}/{inbox.get('books')} sổ qua {rounds} lượt liền: "
                     "máy ngừng tự dán chuyến, ghi giá ở các sổ đó.")
    age = inbox.get("computed_age_seconds")
    if isinstance(age, int) and age > INBOX_MAX_MINUTES * 60:
        found.append(f"Hộp việc chưa tính lại {age // 60} phút: nhịp nền của API có thể đã dừng.")
    return found


def systemctl_show(unit: str, *properties: str) -> dict[str, str]:
    command = ["systemctl", "show", unit, "--timestamp=unix", *(f"--property={name}" for name in properties)]
    output = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True).stdout
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def check_units(show: Callable[..., dict[str, str]], now: float) -> list[str]:
    found = []
    for name, max_hours in TIMERS.items():
        timer = show(f"{name}.timer", "ActiveState", "LastTriggerUSec")
        if timer.get("ActiveState") != "active":
            found.append(f"Timer {name} không chạy.")
            continue
        if max_hours is None:
            continue
        result = show(f"{name}.service", "Result").get("Result")
        if result != "success":
            found.append(f"Sao lưu {name} lỗi ({result}).")
        last = timer.get("LastTriggerUSec", "")
        if last.startswith("@") and (now - int(last[1:].split(".")[0])) / 3600 > max_hours:
            found.append(f"Sao lưu {name} đã hơn {max_hours} giờ chưa chạy.")
    return found


def check_disks(paths: tuple[str, ...], usage: Callable = shutil.disk_usage) -> list[str]:
    found = []
    for path in paths:
        try:
            disk = usage(path)
        except OSError:
            continue
        if disk.free / disk.total < DISK_MIN_FREE:
            found.append(f"Đĩa {path} chỉ còn {disk.free * 100 // disk.total}% trống.")
    return found


def collect(now: dt.datetime, *, healthz: str, reconcile: Path, snapshots: Path, show: Callable = systemctl_show) -> list[str]:
    """Một phép kiểm hỏng không được che các phép kiểm khác."""
    moment = now.timestamp()
    checks: tuple[tuple[str, Callable[[], list[str]]], ...] = (
        ("web", lambda: check_api(healthz)), ("đối soát", lambda: check_reconcile(reconcile, now)),
        ("bản chụp", lambda: check_snapshots(snapshots, moment)), ("nguồn chuyến", lambda: check_sources(snapshots, now.date())),
        ("hộp việc", lambda: check_inbox(healthz)), ("timer", lambda: check_units(show, moment)),
        ("đĩa", lambda: check_disks(DISKS)))
    found: list[str] = []
    for label, check in checks:
        try:
            found += check()
        except Exception as exc:  # noqa: BLE001  (máy canh không được chết im vì một phép kiểm)
            found.append(f"Không kiểm được phần {label} ({type(exc).__name__}).")
    return found


def send(url: str, body: str, *, failed: bool, opener: Callable = urllib.request.urlopen, attempts: int = 3, pause: float = 5) -> bool:
    """Ping thường hoặc /fail. Mạng chập chờn thì thử lại; vẫn không được thì dịch vụ tự báo khi quá giờ. URL là bí mật, không in ra."""
    request = urllib.request.Request(url + ("/fail" if failed else ""), data=body.encode("utf-8"), method="POST")
    for attempt in range(attempts):
        try:
            with opener(request, timeout=20):
                return True
        except OSError:
            if attempt + 1 < attempts:
                time.sleep(pause)
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="kiểm và in ra, không báo đi")
    parser.add_argument("--test-fail", action="store_true", help="gửi một cảnh báo thử, không kiểm gì")
    parser.add_argument("--healthz", default=os.getenv("WEBDEBIT_HEALTHZ_URL") or HEALTHZ)
    parser.add_argument("--reconcile", type=Path, default=Path(os.getenv("WEBDEBIT_RECONCILE_PATH") or RECONCILE))
    parser.add_argument("--snapshots", type=Path, default=Path(SNAPSHOT_DIR))
    args = parser.parse_args(argv)
    url = (os.getenv("WEBDEBIT_ALERT_PING_URL") or "").strip()
    if url and not url.startswith("https://"):
        print(json.dumps({"ok": False, "error": "WEBDEBIT_ALERT_PING_URL phải bắt đầu bằng https://"}, ensure_ascii=False))
        return 2
    found: list[str] = [TEST_BODY] if args.test_fail else collect(now_vn(), healthz=args.healthz, reconcile=args.reconcile, snapshots=args.snapshots)
    report: dict[str, Any] = {"ok": not found, "problems": found, "configured": bool(url)}
    print(json.dumps(report, ensure_ascii=False))
    if args.dry_run or not url:
        return 0
    if send(url, "\n".join(found) or "Ổn.", failed=bool(found)):
        return 0
    print(json.dumps({"ok": False, "error": "không gửi được báo cáo"}, ensure_ascii=False))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
