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
JOBS_TTL = 20.0
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
        done = subprocess.run(["systemctl", "show", "--property=Id,ActiveState,Result,LastTriggerUSec,NextElapseUSecRealtime", *names],
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
            if service.get("ActiveState") == "activating":
                state = "running"
            elif service.get("Result") not in (None, "", "success"):
                state = "failed"
            elif timer.get("ActiveState") != "active":
                state = "off"
            elif last_at is None or now - last_at.timestamp() > job["late_after"]:
                state = "late"
            else:
                state = "ok"
        out.append({"id": job["id"], "name": job["name"], "does": job["does"], "every": job["every"], "last": last, "next": _systemd_time(timer.get("NextElapseUSecRealtime", "")) if timer else None, "state": state})
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


def now_view(now: float | None = None) -> dict[str, Any]:
    """Phần đổi nhanh, gọi vài giây một lần khi tab đang mở."""
    now = time.time() if now is None else now
    folder = base_dir()
    return {"now": datetime.fromtimestamp(now, VN).isoformat(timespec="seconds"), "run": _read_json(folder / "reconcile-run.json"),
            "jobs": jobs(now), "office": _office(folder, now)}


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
    }


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
