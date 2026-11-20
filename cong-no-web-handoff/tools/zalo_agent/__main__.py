"""ZALO-AGENT-01: `python -X utf8 -I …\\zalo_agent run [--once] [--dry-run]`, một tiến trình nền ở máy có Zalo.

Cấu hình đọc từ tham số hoặc biến môi trường (`ZALO_LIVE_SYNC`, `ZALO_AGENT_ROOT`, `ZALO_AGENT_TARGET`,
`ZALO_AGENT_STATUS_TARGET`), không có bí mật trong repo. Thư mục gốc `D:\\zalo-agent`: `state/` (con trỏ, status.json),
`bundle/` (gói chat dựng tại máy), `logs/` (xoay vòng 10 MB x 3). Chỉ đọc thư mục live-sync.
"""
from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):   # chạy `python -I …\zalo_agent`: đưa thư mục cha vào sys.path rồi nạp như gói
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from zalo_agent import cursor as cursors
from zalo_agent import push as pusher
from zalo_agent import status as status_file
from zalo_agent.processors.bundle import BundleProcessor
from zalo_agent.source import LiveSync

REPO = Path(__file__).resolve().parents[3]
STATUS_EVERY = 60     # giây: nhịp tim tối thiểu khi không có gì đổi
SETTLE = 3            # giây: gom các revision liên tiếp rồi mới xử lý
LOCK_STALE = 2 * 3600


class Agent:
    def __init__(self, live: LiveSync, root: Path, bundle_target: str, status_target: str, *, run=pusher.ssh_run,
                 dry_run: bool = False, clock=time.time, sleep=time.sleep, log=None, **processor_args):
        self.live, self.root, self.status_target, self.run = live, Path(root), status_target, run
        self.dry_run, self.clock, self.sleep = dry_run, clock, sleep
        self.state = self.root / "state"
        self.log = log or logging.getLogger("zalo_agent")
        self.version = status_file.agent_version(REPO)
        self.processors = [BundleProcessor(live, self.state, self.root / "bundle", bundle_target, run=run, dry_run=dry_run,
                                           clock=clock, **processor_args)]
        self.last = {}
        self.last_status_at = 0.0
        self.retry_at = 0.0
        self.failures = 0
        self.push_ok_at = None
        self.push_error = None

    def lock(self):
        self.state.mkdir(parents=True, exist_ok=True)
        path = self.state / "agent.lock"
        try:
            if path.is_file() and time.time() - path.stat().st_mtime > LOCK_STALE:
                path.unlink()
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            return None
        return path

    def cycle(self, force_status: bool = False) -> dict | None:
        """Một lượt: chạy từng bộ xử lý, ghi `status.json` (và đẩy) khi có đổi hoặc đủ một phút."""
        lock = self.lock()
        if lock is None:
            return None
        try:
            results = {}
            for processor in self.processors:
                try:
                    results[processor.name] = processor.step()
                except Exception as exc:  # noqa: BLE001  (một bộ xử lý lỗi không được làm chết cả agent)
                    saved = cursors.load(self.state, processor.name)
                    results[processor.name] = {"action": "idle", "revision": (saved or {}).get("revision"), "error": "unexpected"}
                    self.log.error("%s: %s", processor.name, type(exc).__name__)
            now = self.clock()
            for name, result in results.items():
                if result["action"] != "idle" or result["error"] != (self.last.get(name) or {}).get("error"):
                    self.log.info("%s: %s revision=%s bytes=%s error=%s", name, result["action"], result["revision"],
                                  result.get("bytes_sent"), result["error"])
            changed = {name: (r["action"], r["revision"], r["error"]) for name, r in results.items()} != \
                {name: (r["action"], r["revision"], r["error"]) for name, r in self.last.items()}
            self.last = results
            if not (force_status or changed or now - self.last_status_at >= STATUS_EVERY):
                return None
            status = status_file.compose(status_file.load(self.state), now, self.version, len(self.live.selection()), self.live,
                                         results, self.push_ok_at, self.push_error)
            data = status_file.write(self.state, status)
            self.last_status_at = now
            if not self.dry_run:
                try:
                    status_file.push_status(self.status_target, data, self.run)
                    self.push_ok_at, self.push_error = cursors.now_iso(now), None
                except pusher.PushError:
                    self.push_error = "push_failed"
            return status
        finally:
            lock.unlink(missing_ok=True)

    def wants_work(self) -> bool:
        return any(processor.wants_work() for processor in self.processors)

    def forever(self, interval: float = 1.0) -> None:
        while True:
            now = self.clock()
            if now >= self.retry_at and self.wants_work():
                self.sleep(SETTLE)
                self.cycle()
                failed = any(result["error"] for result in self.last.values())
                self.failures = self.failures + 1 if failed else 0
                self.retry_at = now + (min(60, 2 ** self.failures) if failed else 0)
            else:
                self.cycle()   # nhịp tim: chỉ ghi và đẩy khi đủ một phút
            self.sleep(interval)


def configure_logging(root: Path) -> logging.Logger:
    logger = logging.getLogger("zalo_agent")
    logger.setLevel(logging.INFO)
    (root / "logs").mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(root / "logs" / "agent.log", maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="zalo_agent", description="Tiến trình nền ở máy có Zalo (ZALO-AGENT-01).")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="đọc live-sync theo revision, đẩy gói chat và nhịp tim lên hao")
    run.add_argument("--once", action="store_true", help="chạy một lượt rồi thoát")
    run.add_argument("--dry-run", action="store_true", help="làm hết ở máy, không đẩy gì lên hao")
    run.add_argument("--live-sync", default=os.environ.get("ZALO_LIVE_SYNC", r"D:\zalo-audit-viewer\live-sync-20261030"))
    run.add_argument("--root", default=os.environ.get("ZALO_AGENT_ROOT", r"D:\zalo-agent"))
    run.add_argument("--target", default=os.environ.get("ZALO_AGENT_TARGET", "hao:/srv/v7/zalo-bundle"))
    run.add_argument("--status-target", default=os.environ.get("ZALO_AGENT_STATUS_TARGET", "hao:/srv/v7/zalo-agent"))
    run.add_argument("--max-fetch", type=int, default=50, help="số ảnh tối đa tải từ Zalo mỗi lượt")
    run.add_argument("--max-age-days", type=int, default=30)
    args = parser.parse_args(argv)
    root = Path(args.root)
    agent = Agent(LiveSync(Path(args.live_sync)), root, args.target, args.status_target, dry_run=args.dry_run,
                  log=configure_logging(root), max_fetch=args.max_fetch, max_age_days=args.max_age_days)
    if args.once:
        status = agent.cycle(force_status=True)
        print(json.dumps(status, ensure_ascii=False, indent=2) if status else "đang có lượt khác chạy")
        return 1 if status and any(item["error"] for item in status["processors"].values()) else 0
    agent.forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
