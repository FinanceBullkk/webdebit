#!/usr/bin/env python3
"""Script ngoài container của quản lý Hermes, chạy theo lịch trên PC (MAY-CHAY-01).

Lấy bản tóm tắt từ API, chỉ gọi Hermes khi có việc mới, rồi đưa thẻ về web. Script này tin được vì là code của mình; Hermes thì không có
đường tới `hao`: nó chỉ thấy một file tóm tắt chỉ đọc và một thư mục thẻ. Thẻ đi qua kiểm ở đây và kiểm lại ở API.

    OFFICE_API=https://<máy>:<cổng> OFFICE_DATA=<thư mục> python pump.py

Không in tên khách hay số tiền: bản tóm tắt vốn không có, log chỉ có số đếm và mã lỗi.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROMPT = ("Đọc bản tóm tắt rồi cập nhật thẻ việc cho chủ sổ. Mỗi khách trong open là một thẻ, key dạng kh-<số>-lech, nhắc số lượt liền. "
          "Khách không còn trong open thì đóng thẻ của khách đó. Job có tình trạng failed, late, off thì một thẻ riêng, key job-<tên>. "
          "too_many_different hoặc last_run_failed là true thì một thẻ level urgent. Chỉ dùng số có trong bản tóm tắt. Kết thúc bằng một câu ngắn.")
BAD_JOB_STATES = ("failed", "late", "off")
CHAT_TIMEOUT = 300


def what_matters(summary: dict[str, Any]) -> dict[str, Any]:
    """Phần đổi thì mới cần quản lý xem. Số lượt và số lượt liền tăng mỗi giờ nên không tính, nếu không lượt nào cũng gọi model."""
    return {
        "open": sorted((row["customer"], row["reason"]) for row in summary.get("open") or []),
        "unlinked": summary.get("unlinked") or {},
        "too_many": bool(summary.get("too_many_different")),
        "failed": bool(summary.get("last_run_failed")),
        "jobs": sorted(key for key, state in (summary.get("jobs") or {}).items() if state in BAD_JOB_STATES),
    }


def fingerprint(summary: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(what_matters(summary), sort_keys=True).encode()).hexdigest()


def nothing_to_do(summary: dict[str, Any]) -> bool:
    return not any(what_matters(summary).values())


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def summary(self) -> dict[str, Any]:
        with urllib.request.urlopen(f"{self.base}/api/v7/machine/summary", timeout=30) as response:
            return json.load(response)

    def report(self, body: dict[str, Any]) -> None:
        request = urllib.request.Request(f"{self.base}/api/v7/machine/office", data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "Origin": self.base})
        with urllib.request.urlopen(request, timeout=30):
            pass


def run_hermes(compose: Path = HERE / "compose.yaml") -> bool:
    done = subprocess.run(["docker", "compose", "-f", str(compose), "--profile", "run", "run", "--rm", "-T", "hermes", "chat", "-Q", "-q", PROMPT],
                          capture_output=True, timeout=CHAT_TIMEOUT, check=False, encoding="utf-8", errors="replace")
    return done.returncode == 0


def run_once(api: Api, data: Path, hermes: Callable[[], bool] = run_hermes) -> str:
    """Một vòng; trả về kết luận ngắn cho log. Lỗi giữa chừng thì không lưu dấu, vòng sau làm lại."""
    state_path, tasks_path = data / "pump-state.json", data / "tasks" / "tasks.json"
    summary = api.summary()
    mark = fingerprint(summary)
    state = _read_json(state_path, {})
    if state.get("mark") == mark:
        return "khong doi"
    if nothing_to_do(summary):
        # Không có gì mở thì không cần AI: code tự dọn thẻ cũ.
        _write_atomic(tasks_path, "{}")
        api.report({"state": "idle", "tasks": {}})
        _write_atomic(state_path, json.dumps({"mark": mark}))
        return "het viec, khong goi model"
    _write_atomic(data / "feed" / "summary.json", json.dumps(summary, ensure_ascii=False))
    api.report({"state": "working"})
    try:
        worked = hermes()
    except (OSError, subprocess.SubprocessError):
        worked = False
    if not worked:
        api.report({"state": "idle"})
        return "hermes loi"
    tasks = _read_json(tasks_path, None)
    if not isinstance(tasks, dict):
        api.report({"state": "idle"})
        return "the hong"
    api.report({"state": "idle", "tasks": tasks, "model_called": True})
    _write_atomic(state_path, json.dumps({"mark": mark}))
    return f"goi model, {len(tasks)} the"


def main() -> int:
    base, data = os.environ.get("OFFICE_API"), os.environ.get("OFFICE_DATA")
    if not base or not data:
        print("thieu OFFICE_API hoac OFFICE_DATA", file=sys.stderr)
        return 2
    try:
        print(run_once(Api(base), Path(data)), flush=True)
    except urllib.error.HTTPError as exc:
        print(f"api loi {exc.code}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"loi {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
