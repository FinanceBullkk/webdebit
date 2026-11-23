#!/usr/bin/env python3
"""Máy canh: báo email khi máy công nợ lỗi hoặc dừng (CANH-BAO-01, specs/v7-canh-bao.md).

Chạy trên hao dưới user runner (timer v7-watchdog, 15 phút một lần):

    v7_watchdog.py [--dry-run] [--test-fail]

Mỗi lượt kiểm tại chỗ, chỉ đọc: web còn trả lời, lượt đối soát còn mới và không báo lỗi ghi, bản chụp Sheet còn mới, nguồn booking
còn chuyến mới, hộp việc của API còn tính được, các timer còn bật, sao lưu không lỗi, đĩa còn chỗ, và lưới an toàn trên sổ thật
(`v7_safety_net.py`, LUOI-AN-TOAN-01; chỉ ghi file mốc của chính nó), máy Zalo còn báo nhịp tim (ZALO-AGENT-01, 7–20 giờ) và bot Zalo
hỏi đáp còn chạy, còn nhận tin (ZALO-BOT-01, 7–20 giờ). Rồi báo về healthchecks.io: ổn thì ping thường, có việc thì ping /fail
kèm danh sách. hao tắt hay mất mạng thì không còn ping và dịch vụ đó tự gửi email, nên không dùng Uptime Kuma nằm trên chính hao.

Nhiều check (audit vận hành 23/11/2026, O2): healthchecks.io chỉ gửi email khi check đổi trạng thái, nên một lỗi kéo dài (lưới an toàn
chưa ai chấp nhận, đĩa đầy) che mọi lỗi mới cùng check. Các phép kiểm chia nhóm (`GROUPS`), mỗi nhóm báo về check của nó nếu có URL riêng
(`WEBDEBIT_ALERT_PING_URL_<NHÓM>`), không thì về check chính `WEBDEBIT_ALERT_PING_URL`. Check chính luôn nhận một ping mỗi lượt: khi mọi
nhóm đã có check riêng thì nó chỉ còn là nhịp sống (hao còn chạy, máy canh còn chạy) và không bao giờ được Pause.

Nội dung gửi đi chỉ có mã và số đếm, không có tên khách hay số tiền. Chưa có URL nào thì chỉ in ra journal.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
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
# Cờ máy 15 phút phải bật (= drop-in auto-sheet.conf trên hao, audit vận hành 23/11/2026, O4). Cố ý tắt một cờ thì sửa biến này
# trong alert.env cùng lúc, không thì nhóm tiền báo (đúng ý: tắt nhầm khi sửa drop-in tay là chuyến/giá ngừng vào web mà web vẫn 200).
AUTO_FLAGS = tuple(flag.strip() for flag in
                   os.getenv("WEBDEBIT_ALERT_AUTO_FLAGS", "text,trips,prices,road,ps,headers").split(",") if flag.strip())
# Timer phải còn bật. Sao lưu có thêm số giờ tối đa từ lần chạy trước; các job 15 phút và đối soát đã có kiểm riêng theo kết quả.
MONEY_TIMERS: dict[str, float | None] = {"v7-reconcile-auto": None, "webdebit-sheet-sync": None, "webdebit-sheet-prices": None,
                                         "webdebit-ps-snapshot": None}
BACKUP_TIMERS: dict[str, float | None] = {"v7-backup-hourly": 12, "v7-backup-daily": 26, "v7-backup-config": 26, "v7-backup-offsite": 26}
TIMERS: dict[str, float | None] = {**MONEY_TIMERS, **BACKUP_TIMERS}
DISKS = ("/", "/srv", "/var/lib/postgresql")
DISK_MIN_FREE = 0.10
TEST_BODY = "Thử cảnh báo của máy công nợ, không có lỗi thật. Lượt kế sẽ báo ổn lại."
# Nhóm → biến môi trường của check riêng, theo thứ tự thử. Không có biến nào thì nhóm báo về check chính (MAIN_URL).
# Lưới an toàn tách khỏi tiền vì nó đỏ kéo dài tới khi có người chấp nhận (LUOI-AN-TOAN-01), sẽ che lỗi ghi của máy đối soát;
# chưa có check riêng thì nó đi chung check tiền.
GROUPS: dict[str, tuple[str, ...]] = {
    "tien": ("WEBDEBIT_ALERT_PING_URL_TIEN",),
    "luoi": ("WEBDEBIT_ALERT_PING_URL_LUOI", "WEBDEBIT_ALERT_PING_URL_TIEN"),
    "saoluu": ("WEBDEBIT_ALERT_PING_URL_SAOLUU",),
    "zalo": ("WEBDEBIT_ALERT_PING_URL_ZALO",),
}
MAIN_URL = "WEBDEBIT_ALERT_PING_URL"


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


RECONCILE_MAX_DIFFERENT = 40   # = v7_reconcile_auto.MAX_DIFFERENT: hơn số này khách lệch thì máy không ghi gì cả lượt


def previous_too_many(path: Path, checked_at: str) -> bool:
    """Lượt đối soát ngay trước lượt `checked_at` cũng hơn 40 khách lệch? Đọc đuôi `reconcile-log.jsonl` (mỗi lượt một dòng số đếm)."""
    try:
        with path.with_name("reconcile-log.jsonl").open("rb") as stream:
            size = stream.seek(0, os.SEEK_END)
            stream.seek(max(0, size - 16384))
            raw = stream.read().splitlines()
    except OSError:
        return False
    lines = []
    for item in raw[1:] if size > 16384 else raw:   # dòng đầu của khúc đuôi có thể bị cắt
        try:
            line = json.loads(item)
        except ValueError:
            continue
        if isinstance(line, dict) and str(line.get("checked_at") or "") < checked_at:
            lines.append(line)
    return bool(lines) and ((lines[-1].get("counts") or {}).get("LECH_TONG") or 0) > RECONCILE_MAX_DIFFERENT


def check_reconcile(path: Path, now: dt.datetime) -> list[str]:
    """Cùng luật "có thể cũ" với tab Việc cần làm: một lượt lỗi lẻ thì lượt sau tự lành, quá 3 giờ trong ngày mới là máy đã dừng.
    Máy chạy chế độ chỉ báo (thiếu `--fix`) và cầu dao hơn 40 khách lệch hai lượt liền cũng báo (audit vận hành 23/11/2026, O4):
    hai trường hợp này lượt vẫn mới mà máy không ghi gì."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        checked = dt.datetime.fromisoformat(data["checked_at"]) if data.get("checked_at") else None
    except (OSError, ValueError, TypeError):
        return ["Không đọc được kết quả đối soát."]
    found = []
    if checked is not None and data.get("mode") not in (None, "fix"):
        found.append(f"Máy đối soát đang chạy chế độ {data['mode']}: không tự sửa (thiếu --fix trong unit v7-reconcile-auto).")
    if checked is not None and (data.get("details") or {}).get("skipped") == "TOO_MANY_DIFFERENT" \
            and previous_too_many(path, data["checked_at"]):
        count = (data.get("counts") or {}).get("LECH_TONG")
        found.append(f"Máy đối soát dừng ghi hai lượt liền vì {count} khách lệch (quá {RECONCILE_MAX_DIFFERENT}). Cần xem ngay.")
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
    # API cũ chưa có các trường dưới thì im (O4).
    flags = inbox.get("auto_flags")
    if isinstance(flags, str):
        missing = [flag for flag in AUTO_FLAGS if flag not in flags.split(",")]
        if missing:
            found.append(f"Máy 15 phút trong API đang tắt {', '.join(missing)} (WEBDEBIT_AUTO_SHEET): "
                         "chuyến, giá hay phí theo Sheet không tự vào web nữa.")
    errors, error_rounds = inbox.get("auto_errors_last_round"), inbox.get("auto_error_rounds")
    if isinstance(errors, int) and isinstance(error_rounds, int) and errors and error_rounds >= INBOX_FAILED_ROUNDS:
        found.append(f"Máy 15 phút trong API lỗi {errors} lần ở lượt vừa rồi, {error_rounds} lượt liền: "
                     "xem journalctl -u v7-ledger-api | grep 'V7 máy'.")
    return found


def systemctl_show(unit: str, *properties: str) -> dict[str, str]:
    command = ["systemctl", "show", unit, "--timestamp=unix", *(f"--property={name}" for name in properties)]
    output = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True).stdout
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def check_units(show: Callable[..., dict[str, str]], now: float, timers: dict[str, float | None] = TIMERS) -> list[str]:
    found = []
    for name, max_hours in timers.items():
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


def check_safety_net(now: dt.datetime, *, save_state: bool = True) -> list[str]:
    """Lưới an toàn (LUOI-AN-TOAN-01, specs/v7-luoi-an-toan.md): kiểm sổ thật chỉ đọc. Module riêng, import muộn để mã của nó
    (và tầng web nó dùng) hỏng thì chỉ mục này báo "Không kiểm được", máy canh vẫn chạy các mục khác."""
    import v7_safety_net
    return v7_safety_net.check(now, save_state=save_state)


def check_offsite_pulls(now: dt.datetime) -> list[str]:
    """Bản sao ngoài máy còn được PC kéo (CANH-BAO-01, bổ sung 18/11/2026). Module riêng, import muộn như lưới an toàn."""
    import v7_offsite_watch
    return v7_offsite_watch.check(now.timestamp())


ZALO_HOURS = (7, 20)   # ZALO-AGENT-01: chỉ canh máy Zalo từ 7:00 tới trước 20:00 giờ VN (máy có thể tắt ban đêm)
ZALO_PROCESSOR_NAMES = {"bundle": "gói chat", "insurance": "bảo hiểm", "money_images": "ảnh chuyển khoản", "wechat": "WeChat"}
# Độ trễ tin mới, chặng `total` (live-sync ghi revision → hao áp gói) trong 60 phút qua: mục tiêu p95 30 giây (spec, bước Chuyển);
# báo khi p95 quá 5 phút và có ít nhất 3 lượt (ít hơn thì một lượt chậm đã thành p95). Chặng `zalo` không xét: tin đọc bù sau khi
# máy tắt qua đêm luôn dài và không do agent.
ZALO_LATENCY_P95 = 300
ZALO_LATENCY_MIN = 3
# WECHAT-01: đọc DB và khóa ảnh vẫn chạy khi WeChat đã tắt hay chờ đăng nhập (22/11/2026: tắt từ khoảng 03:48 tới 06:10 mà không ai
# biết), nên máy canh nhìn chính app WeChat do agent báo (`processors.wechat.app`).
WECHAT_APP_TEXT = {"closed": "WeChat chưa mở trên máy Zalo", "update": "WeChat trên máy Zalo đang chờ cập nhật, chưa mở lại",
                   "login": "WeChat trên máy Zalo đang chờ đăng nhập (xác nhận trên điện thoại)"}
# Zalo không đọc được tin mới: chưa mở (`waiting_for_zalo`), hoặc đã mở mà live-sync chưa lấy được khóa đọc tin (`reprobing`). Lúc Zalo
# vừa mở thì `reprobing` chỉ thoáng qua; 22/11/2026 Zalo mở lại 06:03 rồi kẹt như vậy hơn 18 giờ, cửa sổ Zalo ở cỡ màn đăng nhập, mà
# không ai biết vì chỉ `waiting_for_zalo` được xét.
ZALO_IDENTITY_TEXT = {"waiting_for_zalo": "Zalo chưa mở trên máy Zalo: không đọc được tin mới {} phút.",
                      "reprobing": "Zalo đã mở trên máy Zalo nhưng máy chưa đọc được tin {} phút: xem Zalo có đang chờ đăng nhập lại không."}


# WeChat im: có nhóm mà không có lượt đọc thành công nào quá ngưỡng (3 nhịp đọc, tối thiểu 15 phút; `read_limit_minutes`), tính từ lượt
# đọc cuối hoặc từ lúc agent chạy lại / msi dậy, cái nào muộn hơn. Chỉ bỏ câu này khi câu khác về cùng nguyên nhân THẬT SỰ được báo (app đóng /
# chờ cập nhật / chờ đăng nhập quá 15 phút, hay lỗi đã quá 15 phút): app vừa đóng 3 phút hay `unknown` kéo dài thì vẫn báo "im", để người
# dùng tắt/mở lại WeChat không làm cảnh báo biến mất (email "đã ổn") rồi lỗi lại. Không báo khi chưa chọn nhóm WeChat nào.
# Giờ tin mới nhất (`newest_at`) chỉ để hiển thị: nhóm có thể im cả đêm.
# Đối chiếu số tin: máy Zalo báo số tin theo ngày đã vào kho quá 30 phút (`daily`); gói trên hao có ít hơn thì tin đã mất trên đường lên.
ZALO_BUNDLE = "/srv/v7/zalo-bundle"
BUNDLE_DATA_DIR = re.compile(r"data-[0-9-]{1,40}")
CONVERSATION_KEY = re.compile(rb'"conversation_id": ?"([0-9a-f]{64})"')


def duration_text(minutes: int) -> str:
    return f"{minutes // 60} giờ {minutes % 60} phút" if minutes >= 60 else f"{minutes} phút"


def wechat_bundle_counts(directory: Path, days: set[str]) -> tuple[dict[str, int] | None, str | None]:
    """Số tin (mã khác nhau) của các nhóm WeChat trong gói trên hao theo ngày VN, chỉ các ngày `days`. Đúng cái web hiển thị: tin trong
    `messages.jsonl` cộng phần thêm `messages-delta.jsonl` tới `delta_bytes` của báo cáo. Trả (số đếm, None), hoặc (None, lý do ngắn) khi không
    đọc được gói: thiếu thư mục, không có quyền (thư mục gói thuộc nhóm `v7app`), sai khuôn. Không đọc được thì không kết luận được lệch, nhưng
    phải báo (đường sai hay thiếu quyền mà im thì phép đối chiếu chết vĩnh viễn)."""
    try:
        report = {}
        for name in ("export-report.json", "message-export-report.json"):
            try:
                report = json.loads((directory / name).read_text(encoding="utf-8"))
                break
            except (OSError, ValueError):
                continue
        data = report.get("data_dir") if isinstance(report, dict) else None
        if data is not None and not (isinstance(data, str) and BUNDLE_DATA_DIR.fullmatch(data)):
            return None, "báo cáo gói sai khuôn"
        base = directory / data if data else directory
        conversations = json.loads((base / "conversations.json").read_text(encoding="utf-8"))
        wechat = {item["conversation_id"].encode() for item in conversations
                  if isinstance(item, dict) and isinstance(item.get("conversation_id"), str)
                  and str(item.get("display_name") or "").startswith("WeChat · ")}
        limit = report.get("delta_bytes") if isinstance(report, dict) else None
        limit = limit if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0 else 0
        seen: dict[str, str] = {}
        for name, cap in (("messages.jsonl", None), ("messages-delta.jsonl", limit)):
            if cap == 0:
                continue
            with (base / name).open("rb") as stream:
                data_bytes = stream if cap is None else iter(stream.read(cap).splitlines())
                for raw in data_bytes:
                    found = CONVERSATION_KEY.search(raw)
                    if not found or found.group(1) not in wechat:
                        continue
                    try:
                        row = json.loads(raw)
                        stamp = row["timestamp"]
                        stamp = int(stamp) if isinstance(stamp, str) else stamp
                        seen[row["message_id"]] = dt.datetime.fromtimestamp(stamp / 1000, ZoneInfo("Asia/Ho_Chi_Minh")).date().isoformat()
                    except (ValueError, KeyError, TypeError):
                        continue
    except PermissionError:
        return None, "không có quyền đọc thư mục gói"
    except FileNotFoundError:
        return None, "thiếu thư mục hoặc file của gói"
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return None, "gói không đọc được"
    counts: dict[str, int] = {}
    for day in seen.values():
        if day in days:
            counts[day] = counts.get(day, 0) + 1
    return counts, None


def check_wechat(row: dict, limit: int) -> list[str]:
    """WeChat ngừng đọc mà không báo lỗi, và tin ở máy Zalo không lên gói (xem chú thích trên). Một dòng WeChat của `v7_machine.zalo`."""
    found = []
    stale = row.get("read_minutes")
    boxed = row["error"] and (row["error_minutes"] is None or row["error_minutes"] > limit)
    app_told = row.get("app") in WECHAT_APP_TEXT and (row.get("app_minutes") or 0) > limit
    if (row.get("groups") or 0) > 0 and stale is not None and not boxed and not app_told and stale > row.get("read_limit_minutes", limit):
        found.append(f"Máy Zalo: WeChat im {duration_text(stale)}: chưa đọc được lượt nào, tin WeChat mới không về.")
    daily = row.get("daily") or {}
    if daily:
        counts, problem = wechat_bundle_counts(Path(os.getenv("WEBDEBIT_ZALO_EXPORT_DIR") or ZALO_BUNDLE), set(daily))
        if problem:
            found.append(f"Máy canh không đối chiếu được số tin WeChat với gói trên máy chủ ({problem}): xem WEBDEBIT_ZALO_EXPORT_DIR và quyền đọc.")
        short = [(day, daily[day], counts.get(day, 0)) for day in sorted(daily) if counts is not None and counts.get(day, 0) < daily[day]]
        if short:
            detail = ", ".join(f"{dt.date.fromisoformat(day):%d/%m}: gói {have}/{want} tin" for day, want, have in short)
            found.append(f"Máy Zalo: tin WeChat có ở máy Zalo mà chưa có trong gói trên máy chủ ({detail}), đã quá 30 phút.")
    return found


def check_zalo(now: dt.datetime) -> list[str]:
    """Máy Zalo còn báo về (ZALO-AGENT-01 Phần 6): `status.json` cũ quá 15 phút, Zalo chưa mở hay đã mở mà chưa đọc được tin quá
    15 phút (`ZALO_IDENTITY_TEXT`), WeChat tắt / chờ cập nhật /
    chờ đăng nhập hay không giải được ảnh quá 15 phút (WECHAT-01), WeChat đã đăng nhập mà quá ngưỡng chưa đọc được lượt nào, tin WeChat có
    ở máy Zalo mà chưa có trong gói trên hao (`check_wechat`, 23/11/2026), một bộ xử lý chậm quá
    15 phút, hoặc một bộ xử lý / việc đẩy lên báo lỗi quá 15 phút (đo từ `error_since`, thiếu thì `last_ok_at`, thiếu cả hai thì báo ngay),
    tin mới lên web chậm (p95 trong 60 phút quá 5 phút), hoặc hàng chờ đọc ảnh còn ảnh mà quá 15 phút không ảnh nào xong (không lỗi).
    Chỉ trong giờ làm việc và chỉ khi đã chọn ít nhất một nhóm.
    Không có file thì im: chưa bật máy Zalo. Dùng chung bộ đọc của tab Máy chạy; import muộn như lưới an toàn (tools dùng được
    tầng web, không có chiều ngược lại)."""
    if not ZALO_HOURS[0] <= now.hour < ZALO_HOURS[1]:
        return []
    web = str(Path(__file__).resolve().parents[1] / "web")
    if web not in sys.path:
        sys.path.insert(0, web)
    import v7_machine
    view = v7_machine.zalo(now.timestamp())
    if view["state"] == "missing" or view["selected_groups"] == 0:
        return []
    limit = v7_machine.ZALO_LATE // 60
    if view["state"] == "silent":
        since = f" từ {dt.datetime.fromisoformat(view['at']):%H:%M ngày %d/%m}" if view["at"] else ""
        return [f"Máy Zalo im lặng{since}: không nhận được báo cáo nào quá {limit} phút."]
    found = []
    quiet = view["quiet_minutes"]
    if view["identity"] in ZALO_IDENTITY_TEXT and quiet is not None and quiet > limit:
        found.append(ZALO_IDENTITY_TEXT[view["identity"]].format(quiet))
    total = view.get("latency", {}).get("hour", {}).get("total") or {}
    if total.get("n", 0) >= ZALO_LATENCY_MIN and (total.get("p95") or 0) > ZALO_LATENCY_P95:
        found.append(f"Máy Zalo: tin mới lên web chậm, 95% lượt trong 60 phút qua mất tới {int(total['p95'] // 60)} phút ({total['n']} lượt).")
    for row in view["processors"]:
        name = ZALO_PROCESSOR_NAMES[row["id"]]
        if row["id"] == "wechat" and row.get("app") in WECHAT_APP_TEXT and (row.get("app_minutes") or 0) > limit:
            found.append(f"{WECHAT_APP_TEXT[row['app']]}: {row['app_minutes']} phút, tin WeChat mới không về.")
        elif row["id"] == "wechat" and row.get("images") == "no_key" and (row.get("images_minutes") or 0) > limit:
            found.append(f"Máy Zalo: WeChat không giải được ảnh {row['images_minutes']} phút (không suy được khóa ảnh).")
        if row["id"] == "wechat":
            found += check_wechat(row, limit)
        if row["error"] and (row["error_minutes"] is None or row["error_minutes"] > limit):
            how = "chưa từng xong lần nào" if row["error_minutes"] is None else f"{row['error_minutes']} phút"
            found.append(f"Máy Zalo: {name} lỗi {row['error']}, {how}.")
        elif row["state"] == "slow" and row["minutes"] is not None and row["minutes"] > limit:
            found.append(f"Máy Zalo xử lý {name} chậm {row['minutes']} phút ({row['lag']} lần thay đổi chưa xong).")
        elif row.get("stalled_minutes") is not None and row["stalled_minutes"] > limit:
            found.append(f"Máy Zalo: đọc {name} đứng {row['stalled_minutes']} phút ({row['pending']} ảnh chờ, không ảnh nào xong).")
    if view["push_error"] and (view["push_error_minutes"] is None or view["push_error_minutes"] > limit):
        how = "chưa từng đẩy được" if view["push_error_minutes"] is None else f"{view['push_error_minutes']} phút"
        found.append(f"Máy Zalo: đẩy lên máy chủ lỗi {view['push_error']}, {how}.")
    return found


# ZALO-BOT-01: bot Zalo hỏi đáp chạy trên hao. Canh trong giờ làm việc như máy Zalo: bộ não im quá 15 phút, hoặc (khi cờ trả lời bật)
# kênh không ở trạng thái nhận tin quá 15 phút. Chưa cài bot (không có file) thì im.
ZALO_BOT_TEXT = {"login_required": "nick phụ cần quét QR đăng nhập lại", "login_pending": "đang chờ quét QR",
                 "kicked": "nick phụ bị phiên khác đá ra (có ai mở nick phụ trên Zalo Web hay Zalo PC?)",
                 "offline": "tiến trình kênh không nối với bộ não", "connecting": "kênh nối mãi chưa được", "error": "kênh báo lỗi",
                 "sandbox_missing": "kênh không chạy vì unit thiếu chặn mạng tới API", "unknown": "kênh báo trạng thái lạ"}


# Bộ đếm trong ngày của bot (F8): hết hạn mức là báo ngay; "chưa chắc" và lỗi model vượt ngưỡng ngày thì báo.
ZALO_BOT_DAILY = {"not_sure": 5, "error": 3}


def check_zalo_bot(now: dt.datetime) -> list[str]:
    """Bot Zalo hỏi đáp còn chạy và còn nhận tin (ZALO-BOT-01 Phần 6). Dùng chung bộ đọc với tab Máy chạy, import muộn như `check_zalo`.
    Bộ đếm hạn mức, "chưa chắc" và lỗi được xét cả ngoài giờ làm việc: bộ đếm về 0 lúc nửa đêm, đợi sáng thì mất."""
    web = str(Path(__file__).resolve().parents[1] / "web")
    if web not in sys.path:
        sys.path.insert(0, web)
    import v7_machine
    view = v7_machine.zalo_bot(now.timestamp())
    if view["state"] == "missing":
        return []
    counts = view.get("counts") or {}
    usage = []
    if counts.get("over_budget", 0) > 0:
        usage.append(f"Bot Zalo: đã hết hạn mức chi phí hôm nay ({counts['over_budget']} câu bị từ chối vì hạn mức).")
    for name, label in (("not_sure", "câu trả lời \"chưa chắc\" (bộ kiểm số chặn)"), ("error", "lần gọi model lỗi")):
        if counts.get(name, 0) >= ZALO_BOT_DAILY[name]:
            usage.append(f"Bot Zalo: hôm nay {counts[name]} {label}, ngưỡng {ZALO_BOT_DAILY[name]}.")
    if not ZALO_HOURS[0] <= now.hour < ZALO_HOURS[1]:
        return usage
    limit = v7_machine.ZALO_LATE // 60
    if view["state"] == "silent":
        since = f" từ {dt.datetime.fromisoformat(view['at']):%H:%M ngày %d/%m}" if view["at"] else ""
        return [f"Bot Zalo im lặng{since}: bộ não không ghi nhịp tim quá {limit} phút."]
    found = usage
    minutes = view["kenh_minutes"]
    if view["enabled"] and view["kenh"] != "online" and (minutes is None or minutes > limit):
        how = "" if minutes is None else f", {minutes} phút"
        found.append(f"Bot Zalo: {ZALO_BOT_TEXT.get(view['kenh'], ZALO_BOT_TEXT['unknown'])}{how}.")
    if view["error"]:
        found.append(f"Bot Zalo: bộ não báo lỗi {view['error']}.")
    check = view.get("tool_check") or {}
    if check.get("failed") and check.get("hours") is not None and check["hours"] <= 26:
        names = ", ".join(item.split(":")[0] for item in check["failed"][:5])
        found.append(f"Bot Zalo: lượt tự kiểm lúc {dt.datetime.fromisoformat(check['at']):%H:%M} có {len(check['failed'])} công cụ đọc API lỗi ({names}).")
    return found


def collect(now: dt.datetime, *, healthz: str, reconcile: Path, snapshots: Path, show: Callable = systemctl_show,
            safety: Callable[[dt.datetime], list[str]] = check_safety_net,
            offsite: Callable[[dt.datetime], list[str]] = check_offsite_pulls,
            zalo: Callable[[dt.datetime], list[str]] = check_zalo,
            zalo_bot: Callable[[dt.datetime], list[str]] = check_zalo_bot) -> list[str]:
    """Mọi dòng của mọi nhóm, theo thứ tự phép kiểm."""
    groups = collect_groups(now, healthz=healthz, reconcile=reconcile, snapshots=snapshots, show=show, safety=safety, offsite=offsite,
                            zalo=zalo, zalo_bot=zalo_bot)
    return [line for _, lines in groups for line in lines]


def collect_groups(now: dt.datetime, *, healthz: str, reconcile: Path, snapshots: Path, show: Callable = systemctl_show,
                   safety: Callable[[dt.datetime], list[str]] = check_safety_net,
                   offsite: Callable[[dt.datetime], list[str]] = check_offsite_pulls,
                   zalo: Callable[[dt.datetime], list[str]] = check_zalo,
                   zalo_bot: Callable[[dt.datetime], list[str]] = check_zalo_bot) -> list[tuple[str, list[str]]]:
    """(nhóm, dòng) cho từng phép kiểm, theo thứ tự. Một phép kiểm hỏng không được che các phép kiểm khác."""
    moment = now.timestamp()
    checks: tuple[tuple[str, str, Callable[[], list[str]]], ...] = (
        ("tien", "web", lambda: check_api(healthz)), ("tien", "đối soát", lambda: check_reconcile(reconcile, now)),
        ("tien", "bản chụp", lambda: check_snapshots(snapshots, moment)),
        ("tien", "nguồn chuyến", lambda: check_sources(snapshots, now.date())),
        ("tien", "hộp việc", lambda: check_inbox(healthz)), ("tien", "timer", lambda: check_units(show, moment, MONEY_TIMERS)),
        ("saoluu", "timer sao lưu", lambda: check_units(show, moment, BACKUP_TIMERS)), ("saoluu", "đĩa", lambda: check_disks(DISKS)),
        ("luoi", "lưới an toàn", lambda: safety(now)), ("saoluu", "bản sao ngoài máy", lambda: offsite(now)),
        ("zalo", "máy Zalo", lambda: zalo(now)), ("zalo", "bot Zalo", lambda: zalo_bot(now)))
    found: list[tuple[str, list[str]]] = []
    for group, label, check in checks:
        try:
            found.append((group, check()))
        except Exception as exc:  # noqa: BLE001  (máy canh không được chết im vì một phép kiểm)
            found.append((group, [f"Không kiểm được phần {label} ({type(exc).__name__})."]))
    return found


def ping_routes(env: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """(URL check chính, {nhóm: URL}). Nhóm không có check riêng thì về check chính; không có cả hai thì nhóm không có trong bảng."""
    main = (env.get(MAIN_URL) or "").strip()
    routes = {}
    for group, names in GROUPS.items():
        url = next((value for value in ((env.get(name) or "").strip() for name in names) if value), main)
        if url:
            routes[group] = url
    return main, routes


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
    main_url, routes = ping_routes(os.environ)
    if any(not url.startswith("https://") for url in (main_url, *routes.values()) if url):
        print(json.dumps({"ok": False, "error": "WEBDEBIT_ALERT_PING_URL… phải bắt đầu bằng https://"}, ensure_ascii=False))
        return 2
    # Mỗi check nhận đúng một ping mỗi lượt: các nhóm chung một check thì gộp dòng; check chính luôn có mặt (nhịp sống).
    outgoing: dict[str, list[str]] = {main_url: []} if main_url else {}
    if args.test_fail:   # thử mọi check một lần, mỗi check gửi email riêng
        found = [TEST_BODY]
        outgoing = dict.fromkeys([*outgoing, *routes.values()], found)
    else:
        # --dry-run không ghi gì, kể cả mốc của lưới an toàn.
        groups = collect_groups(now_vn(), healthz=args.healthz, reconcile=args.reconcile, snapshots=args.snapshots,
                                safety=functools.partial(check_safety_net, save_state=not args.dry_run))
        found = [line for _, lines in groups for line in lines]
        for group, lines in groups:
            if group in routes:
                outgoing.setdefault(routes[group], []).extend(lines)
    report: dict[str, Any] = {"ok": not found, "problems": found, "configured": bool(outgoing), "checks": len(outgoing)}
    print(json.dumps(report, ensure_ascii=False))
    if args.dry_run or not outgoing:
        return 0
    failed = [url for url, lines in outgoing.items() if not send(url, "\n".join(lines) or "Ổn.", failed=bool(lines))]
    if not failed:
        return 0
    print(json.dumps({"ok": False, "error": f"không gửi được báo cáo tới {len(failed)}/{len(outgoing)} check"}, ensure_ascii=False))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
