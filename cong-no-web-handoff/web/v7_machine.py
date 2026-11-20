"""Tab Máy chạy (MAY-CHAY-01): đọc lượt đối soát, lịch các job, bảng việc của quản lý Hermes. Không đọc, không ghi sổ.

Nguồn là các file job để cạnh reconcile.json và `systemctl show`. Ghi duy nhất là `office/state.json`: bảng việc tách khỏi DB sổ, nên lỗi ở đây
không đụng được tiền. `summary()` là thứ duy nhất đưa cho Hermes: chỉ có mã khách, mã lý do và số đếm; không tên, không tiền, không chữ tự do lấy
từ Sheet hay Zalo, để câu lệnh lừa nằm trong dữ liệu không có đường tới model.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from v7_api_validate import ApiError

VN = ZoneInfo("Asia/Ho_Chi_Minh")
RUNS_KEPT = 120         # khoảng một tuần theo nhịp 16 lượt mỗi ngày
JOBS_TTL = 2.0          # trang hỏi mỗi 2 giây; job Sheet chỉ chạy 4–13 giây nên cache dài hơn là không thấy; systemctl đo 27 ms trên hao
LOST_SIGNAL = 300       # job báo đang chạy mà systemd thấy đã tắt và file đứng yên chừng này giây thì coi như chết giữa chừng
WORKING_STALE = 900     # Hermes báo đang làm quá 15 phút mà không báo xong thì coi như đã dừng
LEVELS = ("info", "warn", "urgent")
KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MONEY = re.compile(r"\d{7,}|\d{1,3}(?:[.,]\d{3}){2,}")
MAX_TITLE, MAX_BODY, MAX_TASKS = 120, 600, 30
# Lý do máy không xử lý được: bản tóm tắt chỉ mang mã và câu cố định dưới đây.
OPEN_REASONS = {
    "NO_EXACT_FIX": "Không có tổ hợp nào bằng đúng số lệch",
    "AMBIGUOUS_FIX": "Có hơn một tổ hợp cùng ra đúng số lệch",
    "NOTHING_TO_WRITE": "Lệch mà không có việc nào đang chờ để ghi",
    "TOO_MANY_GROUPS": "Quá nhiều nhóm việc để máy xét",
    "TOO_MANY_DIFFERENT": "Quá nhiều khách lệch cùng lúc, lượt này không ghi",
    "SHEET_SHUFFLED": "Giá trên Sheet đổi chỗ trong tháng",
    "DETAIL_DIFFERS": "Khớp tổng nhưng Sheet còn khoản web chưa theo",
    "WRITE_ERROR": "Lỗi khi ghi",
    "CHECK_ERROR": "Lỗi khi kiểm",
    "VERIFY_FAILED": "Ghi xong đọc lại không khớp",
    "HELD": "Tab đọc không được, khách bị giữ lại",
    "WEB_AHEAD": "Web đi trước Sheet",
    "CHI_CO_WEB": "Có sổ trên web, không thấy trên Sheet",
    "CHI_CO_SHEET": "Có trên Sheet, chưa có sổ web",
    "THIEU_SO": "Thiếu số để so",
    "BOOK_OVERLAP": "Tab mới trùng chuyến với sổ khác",
    "TOO_MANY_NEW_BOOKS": "Quá nhiều tab mới cùng lúc",
    "WOULD_FIX": "Sẽ ghi nếu bật chế độ ghi",
    "WOULD_CREATE_BOOK": "Sẽ tạo sổ nếu bật chế độ ghi",
    "LECH_TONG": "Lệch tổng",
}
JOBS = (
    {"id": "reconcile", "name": "Đối soát tự sửa", "does": "So tổng từng khách, ghi khi khớp", "unit": "v7-reconcile-auto", "every": "Mỗi giờ, 7–22 giờ", "late_after": 3 * 3600},
    {"id": "sheet", "name": "Bản chụp Sheet", "does": "Đọc CONT_NGUON, CONT_BO", "unit": "webdebit-sheet-sync", "every": "15 phút một lần", "late_after": 3600},
    {"id": "prices", "name": "Giá Sheet", "does": "Đọc giá và phiếu thu", "unit": "webdebit-sheet-prices", "every": "15 phút một lần", "late_after": 3600},
    {"id": "ps", "name": "Phí PS", "does": "Đọc cột PS", "unit": "webdebit-ps-snapshot", "every": "15 phút một lần", "late_after": 3600},
    {"id": "watchdog", "name": "Máy canh", "does": "Báo email khi có lỗi", "unit": "v7-watchdog", "every": "15 phút một lần", "late_after": 3600},
    {"id": "backup-hourly", "name": "Sao lưu giờ", "does": "Sao lưu DB", "unit": "v7-backup-hourly", "every": "Mỗi giờ, 6–22 giờ", "late_after": 12 * 3600},
    {"id": "backup-daily", "name": "Sao lưu ngày", "does": "Sao lưu đêm", "unit": "v7-backup-daily", "every": "Mỗi đêm", "late_after": 26 * 3600},
    {"id": "backup-config", "name": "Sao lưu cấu hình", "does": "Sao lưu đêm", "unit": "v7-backup-config", "every": "Mỗi đêm", "late_after": 26 * 3600},
    {"id": "backup-offsite", "name": "Bản sao ngoài máy", "does": "Chuẩn bị bản kéo về", "unit": "v7-backup-offsite", "every": "Mỗi đêm", "late_after": 26 * 3600},
)
_jobs_cache: dict[str, Any] = {"at": 0.0, "rows": []}
# ZALO-AGENT-01 Phần 6: máy có Zalo ghi `status.json` mỗi phút, đẩy lên đây. Chỉ có mã và số đếm.
ZALO_STATUS = "/srv/v7/zalo-agent/status.json"
ZALO_LATE = 900         # im lặng, chờ Zalo hay xử lý chậm quá 15 phút thì máy canh báo
ZALO_SLOW_SHOW = 120    # chậm dưới 2 phút chỉ là đang đuổi kịp
ZALO_PROCESSORS = ("bundle", "insurance", "money_images")   # chỉ các bộ xử lý này được hiện, theo thứ tự này
ZALO_IDENTITY = ("attached", "waiting_for_zalo", "reprobing", "unknown")
ZALO_CODE = re.compile(r"^[a-z_]{1,40}$")


def base_dir() -> Path:
    return Path(os.getenv("WEBDEBIT_MACHINE_DIR") or "/var/lib/webdebit-sheet-sync")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_lines(path: Path, keep: int) -> list[dict[str, Any]]:
    """Các dòng JSON cuối file; dòng hỏng thì bỏ, đang ghi dở cũng không làm hỏng trang."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-keep:]
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _when(text: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        return None


def runs(folder: Path | None = None) -> list[dict[str, Any]]:
    """Các lượt cũ tới mới. Dòng log chỉ có số đếm; lượt từ khi có tín hiệu thì kèm `detail` để xem lại từng trạm."""
    folder = folder or base_dir()
    traces = _read_lines(folder / "reconcile-run-history.jsonl", RUNS_KEPT)
    log = _read_lines(folder / "reconcile-log.jsonl", RUNS_KEPT)
    out, used = [], set()
    for line in log:
        at = _when(line.get("checked_at"))
        row = {"finished_at": line.get("checked_at"), "mode": line.get("mode"), "counts": line.get("counts") or {}, "total": line.get("total"),
               "fixed": line.get("fixed") or 0, "created": line.get("created") or 0, "detail": None}
        for index, trace in enumerate(traces):
            start, end = _when(trace.get("started_at")), _when(trace.get("finished_at"))
            if at and start and end and index not in used and start <= at <= end:
                row["detail"] = trace
                used.add(index)
                break
        out.append(row)
    # Lượt lỗi không có dòng log: vẫn phải thấy.
    for index, trace in enumerate(traces):
        if index not in used:
            out.append({"finished_at": trace.get("finished_at"), "mode": trace.get("mode"), "counts": trace.get("counts") or {}, "total": trace.get("books"),
                        "fixed": trace.get("fixed") or 0, "created": trace.get("created") or 0, "detail": trace})
    out.sort(key=lambda row: str(row["finished_at"]))
    return out[-RUNS_KEPT:]


def _systemd_time(text: str) -> str | None:
    parts = text.split()
    if len(parts) != 4 or parts[3] != "UTC":
        return None
    try:
        at = datetime.strptime(f"{parts[1]} {parts[2]}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
    return at.astimezone(VN).isoformat(timespec="seconds")


def _parse_show(output: str) -> dict[str, dict[str, str]]:
    units: dict[str, dict[str, str]] = {}
    for block in output.split("\n\n"):
        fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if fields.get("Id"):
            units[fields["Id"]] = fields
    return units


def jobs(now: float | None = None) -> list[dict[str, Any]]:
    """Lịch và tình trạng từng job. systemctl lỗi thì `state` là unknown, không làm hỏng trang."""
    now = time.time() if now is None else now
    if now - _jobs_cache["at"] < JOBS_TTL and _jobs_cache["rows"]:
        return _jobs_cache["rows"]
    names = [f"{job['unit']}.{kind}" for job in JOBS for kind in ("timer", "service")]
    try:
        done = subprocess.run(["systemctl", "show", "--property=Id,ActiveState,Result,LastTriggerUSec,NextElapseUSecRealtime,InactiveExitTimestamp,InactiveEnterTimestamp", *names],
                      capture_output=True, text=True, timeout=5, check=False)
        units = _parse_show(done.stdout) if done.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError):
        units = {}
    out = []
    for job in JOBS:
        timer, service = units.get(f"{job['unit']}.timer"), units.get(f"{job['unit']}.service", {})
        last = _systemd_time(timer.get("LastTriggerUSec", "")) if timer else None
        state = "unknown"
        if timer:
            last_at = _when(last) if last else None
            if service.get("ActiveState") in ("activating", "active"):
                state = "running"
            elif service.get("Result") not in (None, "", "success"):
                state = "failed"
            elif timer.get("ActiveState") != "active":
                state = "off"
            elif last_at is None or now - last_at.timestamp() > job["late_after"]:
                state = "late"
            else:
                state = "ok"
        started, ended = _systemd_time(service.get("InactiveExitTimestamp", "")), _systemd_time(service.get("InactiveEnterTimestamp", ""))
        if started and ended and ended < started:   # đang chạy: lần kết thúc còn lại là của lần trước
            ended = None
        out.append({"id": job["id"], "name": job["name"], "does": job["does"], "every": job["every"], "last": last, "next": _systemd_time(timer.get("NextElapseUSecRealtime", "")) if timer else None,
                    "state": state, "started": started, "ended": ended})
    _jobs_cache.update(at=now, rows=out)
    return out


def _office(folder: Path, now: float) -> dict[str, Any]:
    data = _read_json(folder / "office" / "state.json")
    if not isinstance(data, dict):
        return {"state": "off", "tasks": {}, "updated_at": None, "model_called_at": None}
    state = data.get("state")
    updated = _when(data.get("updated_at"))
    if state == "working" and (updated is None or now - updated.timestamp() > WORKING_STALE):
        state = "idle"
    return {"state": state, "tasks": data.get("tasks") or {}, "updated_at": data.get("updated_at"), "model_called_at": data.get("model_called_at")}


def _current_run(folder: Path, rows: list[dict[str, Any]], now: float) -> Any:
    """Lượt đang chạy hoặc vừa xong. Job bị giết thì file đứng mãi ở "running": systemd đã tắt và file cũ thì báo là lượt đã chết, không vẽ tiếp."""
    path = folder / "reconcile-run.json"
    run = _read_json(path)
    if not isinstance(run, dict) or run.get("state") != "running":
        return run
    state = next((row["state"] for row in rows if row["id"] == "reconcile"), "unknown")
    try:
        changed = path.stat().st_mtime
    except OSError:
        return run
    if state in ("running", "unknown") or now - changed < LOST_SIGNAL:
        return run
    return {**run, "state": "failed", "stage": None, "reason": "MAT_TIN_HIEU", "finished_at": datetime.fromtimestamp(changed, VN).isoformat(timespec="seconds")}


def _aware(text: Any) -> datetime | None:
    at = _when(text)
    return at if at is not None and at.tzinfo is not None else None


def _code(value: Any) -> str | None:
    """Mã lỗi của máy Zalo: chỉ nhận đúng khuôn `[a-z_]{1,40}`, chữ khác coi như "error" để không có chữ tự do đi tiếp."""
    if value is None:
        return None
    return value if isinstance(value, str) and ZALO_CODE.fullmatch(value) else "error"


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _minutes_since(text: Any, now: float) -> int | None:
    at = _aware(text)
    return None if at is None else max(int((now - at.timestamp()) // 60), 0)


def zalo(now: float | None = None) -> dict[str, Any]:
    """Máy Zalo báo về (ZALO-AGENT-01 Phần 6), đọc `status.json`. Không có file: `missing` (chưa bật máy Zalo, không phải lỗi).

    File hỏng, `schema` khác 1 hoặc `at` cũ quá 15 phút: `silent`, vẫn trả các bộ xử lý lần báo cuối. Chỉ có mã, số và giờ:
    bộ xử lý lạ bị bỏ, mã lỗi sai khuôn thành "error".
    """
    now = time.time() if now is None else now
    path = Path(os.getenv("WEBDEBIT_ZALO_AGENT_STATUS") or ZALO_STATUS)
    silent: dict[str, Any] = {"state": "silent", "at": None, "silent_minutes": None, "selected_groups": None, "identity": "unknown",
                              "quiet_minutes": None, "processors": [], "push_error": None}
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"state": "missing"}
    except OSError:
        return silent
    try:
        data = json.loads(text)
    except ValueError:
        return silent
    at = _aware(data.get("at")) if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("schema") != 1 or at is None:
        return silent
    live = data.get("live_sync") if isinstance(data.get("live_sync"), dict) else {}
    identity = live.get("identity") if live.get("identity") in ZALO_IDENTITY else "unknown"
    rows = []
    reported = data.get("processors") if isinstance(data.get("processors"), dict) else {}
    for key in ZALO_PROCESSORS:
        item = reported.get(key)
        if not isinstance(item, dict):
            continue
        lag, error = _count(item.get("lag_revisions")), _code(item.get("error"))
        late = _minutes_since(item.get("last_ok_at"), now)
        state = "error" if error else "ok" if lag == 0 else "slow" if late is None or late * 60 >= ZALO_SLOW_SHOW else "catching_up"
        rows.append({"id": key, "state": state, "lag": lag, "minutes": late if lag else None, "error": error})
    push = data.get("push") if isinstance(data.get("push"), dict) else {}
    silent_for = max(now - at.timestamp(), 0)
    return {"state": "silent" if silent_for > ZALO_LATE else "ok", "at": at.astimezone(VN).isoformat(timespec="seconds"),
            "silent_minutes": int(silent_for // 60), "selected_groups": _count(data.get("selected_groups")), "identity": identity,
            # Phút từ lần live-sync thấy thay đổi cuối: hợp đồng chưa có "chờ Zalo từ lúc nào", đây là thước đo gần nhất.
            "quiet_minutes": _minutes_since(live.get("revision_at"), now), "processors": rows, "push_error": _code(push.get("error"))}


def now_view(now: float | None = None) -> dict[str, Any]:
    """Phần đổi nhanh, gọi 2 giây một lần khi tab đang mở."""
    now = time.time() if now is None else now
    folder = base_dir()
    rows = jobs(now)
    return {"now": datetime.fromtimestamp(now, VN).isoformat(timespec="seconds"), "run": _current_run(folder, rows, now),
            "jobs": rows, "office": _office(folder, now), "zalo": zalo(now)}


def view(now: float | None = None) -> dict[str, Any]:
    return {**now_view(now), "runs": runs()}


def _streaks(traces: list[dict[str, Any]]) -> dict[str, int]:
    """Mỗi khách đã lệch bao nhiêu lượt liền, tính ngược từ lượt mới nhất."""
    streak: dict[str, int] = {}
    alive: set[str] | None = None
    for trace in reversed(traces):
        here = {key for key, row in (trace.get("customers") or {}).items() if row.get("reason") in OPEN_REASONS}
        alive = here if alive is None else alive & here
        if not alive:
            break
        for key in alive:
            streak[key] = streak.get(key, 0) + 1
    return streak


def summary(now: float | None = None) -> dict[str, Any]:
    """Bản đưa cho Hermes. Thêm trường nào vào đây phải là số, mã cố định hoặc câu cố định."""
    now = time.time() if now is None else now
    folder = base_dir()
    day = datetime.fromtimestamp(now, VN).date().isoformat()
    every = runs(folder)
    today = [row for row in every if str(row["finished_at"]).startswith(day)]
    traces = [trace for trace in _read_lines(folder / "reconcile-run-history.jsonl", 30) if trace.get("state") == "done"]
    last = traces[-1] if traces else None
    streak = _streaks(traces)
    open_rows = []
    for key, row in sorted(((last or {}).get("customers") or {}).items(), key=lambda item: int(item[0])):
        reason = row.get("reason")
        if reason in OPEN_REASONS and isinstance(row.get("customer_id"), int):
            open_rows.append({"customer": f"kh-{row['customer_id']}", "reason": reason, "note": OPEN_REASONS[reason], "runs_in_a_row": streak.get(key, 1)})
    latest = _read_json(folder / "reconcile-run.json")
    return {
        "day": day,
        "books_total": every[-1]["total"] if every else None,
        "runs": [{"at": str(row["finished_at"])[11:16], "matched": (row["counts"] or {}).get("KHOP", 0), "different": (row["total"] or 0) - (row["counts"] or {}).get("KHOP", 0),
                  "fixed": row["fixed"], "created": row["created"]} for row in today[-8:]],
        "open": open_rows,
        "unlinked": {reason: count for reason, count in ((last or {}).get("unlinked") or {}).items() if reason in OPEN_REASONS and isinstance(count, int)},
        "too_many_different": bool((last or {}).get("too_many")),
        "last_run_failed": isinstance(latest, dict) and latest.get("state") == "failed",
        "jobs": {job["id"]: job["state"] for job in jobs(now)},
        "zalo": _zalo_summary(now),
    }


def _zalo_summary(now: float) -> dict[str, Any]:
    """Máy Zalo cho Hermes: chỉ mã trạng thái cố định và số phút, không chữ nào lấy từ máy Zalo."""
    view = zalo(now)
    if view["state"] == "missing":
        return {"state": "missing"}
    return {"state": view["state"], "identity": view["identity"], "silent_minutes": view["silent_minutes"],
            "processors": {row["id"]: row["state"] for row in view["processors"]}}


def _bad(message: str) -> ApiError:
    return ApiError(400, "INVALID_OFFICE", message)


def _clean_text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise _bad(f"{field} không hợp lệ.")
    if MONEY.search(value):
        raise _bad(f"{field} không được chứa số tiền.")
    return value.strip()


def clean_tasks(tasks: Any) -> dict[str, dict[str, str]]:
    if not isinstance(tasks, dict) or len(tasks) > MAX_TASKS:
        raise _bad("Bảng việc không hợp lệ.")
    out = {}
    for key, task in tasks.items():
        if not isinstance(key, str) or not KEY.match(key) or not isinstance(task, dict):
            raise _bad("Thẻ việc không hợp lệ.")
        if set(task) - {"title", "body", "level"} or task.get("level", "info") not in LEVELS:
            raise _bad("Thẻ việc không hợp lệ.")
        out[key] = {"title": _clean_text(task.get("title"), "Tên thẻ", MAX_TITLE), "body": _clean_text(task.get("body"), "Nội dung thẻ", MAX_BODY), "level": task.get("level", "info")}
    return out


def handle_office(raw: bytes, _runner: Any, _actor: str) -> tuple[int, dict[str, Any]]:
    """Script quản lý trên PC báo tình trạng và bảng việc. Ghi vào file riêng, không chạm DB."""
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise _bad("Dữ liệu gửi không hợp lệ.") from exc
    if not isinstance(body, dict) or set(body) - {"state", "tasks", "model_called"} or body.get("state") not in ("working", "idle"):
        raise _bad("Dữ liệu gửi không hợp lệ.")
    folder = base_dir() / "office"
    path = folder / "state.json"
    current = _read_json(path)
    current = current if isinstance(current, dict) else {}
    stamp = datetime.now(VN).isoformat(timespec="seconds")
    state = {"state": body["state"], "updated_at": stamp, "tasks": clean_tasks(body["tasks"]) if "tasks" in body else current.get("tasks") or {},
             "model_called_at": stamp if body.get("model_called") is True else current.get("model_called_at")}
    try:
        folder.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(dir=folder, prefix=".state-", suffix=".tmp")
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False)
        os.replace(name, path)
    except OSError as exc:
        raise ApiError(503, "OFFICE_UNAVAILABLE", "Chưa ghi được bảng việc.") from exc
    return 200, {"ok": True, "tasks": len(state["tasks"])}
