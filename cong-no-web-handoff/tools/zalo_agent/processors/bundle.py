"""ZALO-AGENT-01 Phần 1: bộ xử lý `bundle`, gói chat theo phần thêm (hợp đồng dữ liệu trong specs/zalo-agent.md).

Dựng đầy đủ (lần đầu, baseline đổi, đổi nhóm đã chọn, mất `changes-N`, revision lùi, mỗi đêm) bằng `zalo_web_bundle.build`.
Giữa hai lần dựng chỉ nối vào `data-<…>/messages-delta.jsonl` những tin thêm, sửa, xóa của nhóm đã chọn:

- tin thêm hoặc sửa: cùng khuôn một dòng `messages.jsonl` của gói;
- tin xóa: đúng dòng mà bản dựng đầy đủ sinh cho tin đó (các trường làm sạch + `deleted: true`, nên có đủ
  `message_id`, `conversation_id`, `timestamp` của hợp đồng).

`users.json` và `media.json` của thư mục dữ liệu hiện tại được gộp thêm người gửi và ảnh mới của các dòng delta
(`bundle_sha256` giữ giá trị của lần dựng đầy đủ). `export-report.json` thêm `delta_bytes`, `delta_lines`, `revision`.
Thứ tự: viết delta cục bộ, lưu con trỏ `pending`, đẩy (file chốt `mv` sau cùng), rồi mới tiến con trỏ.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import zalo_web_bundle as wb

from .. import cursor as cursors
from .. import push as pusher
from ..source import LiveSync, read_json

NAME = "bundle"
DELTA = "messages-delta.jsonl"
MUTABLE = {DELTA, "media.json", "users.json"}   # file của thư mục dữ liệu hiện tại có thể đổi giữa hai lần dựng
PRUNE = ("data-*", "media/*")
CLEAN_KEYS = ("message_id", "conversation_id", "sender_id", "timestamp", "server_time", "message_type", "status", "body_state")


def clean_row(row: dict) -> dict:
    """Cùng làm sạch như `wb.build`: không URL, không đường dẫn máy, không băm URL."""
    return {**{key: row.get(key) for key in CLEAN_KEYS}, "body": wb.clean_body(row.get("body"))}


class BundleProcessor:
    name = NAME

    def __init__(self, live: LiveSync, state: Path, work: Path, target: str, *, run=pusher.ssh_run, dry_run: bool = False,
                 fetch=wb.fetch_url, transcode=wb.transcode_jxl, max_fetch: int = 50, max_age_days: int | None = 30,
                 clock=time.time):
        self.live, self.state, self.out, self.target = live, Path(state), Path(work), target
        self.run, self.dry_run, self.fetch, self.transcode = run, dry_run, fetch, transcode
        self.max_fetch, self.max_age_days, self.clock = max_fetch, max_age_days, clock

    def save(self, cursor: dict, now: float) -> None:
        """`--dry-run` làm hết ở máy nhưng không lưu con trỏ: lượt thật sau đó vẫn đẩy phần chưa tới `hao`."""
        if not self.dry_run:
            cursors.save(self.state, NAME, cursor, now)

    def result(self, action: str, revision: int | None, error: str | None = None, sent: int = 0, reason: str | None = None) -> dict:
        return {"action": action, "revision": revision, "error": error, "bytes_sent": sent, "reason": reason}

    def damaged(self, current: dict) -> str | None:
        """Gói cục bộ không còn khớp con trỏ (thư mục dữ liệu mất, báo cáo trỏ chỗ khác, delta ngắn hơn đã ghi): dựng lại."""
        directory = self.out / current["data_dir"]
        if not directory.is_dir():
            return "data_dir_missing"
        if (read_json(self.out / wb.REPORT, {}) or {}).get("data_dir") != current["data_dir"]:
            return "report_mismatch"
        path = directory / DELTA
        if (path.stat().st_size if path.is_file() else 0) < current["delta_bytes"]:
            return "delta_short"
        return None

    def wants_work(self) -> bool:
        """Rẻ (vài file nhỏ): có revision mới, lượt chưa đẩy xong, hoặc phải dựng lại. Vòng lặp chỉ gom 3 giây khi True."""
        revision, selection, current = self.live.revision(), self.live.selection(), cursors.load(self.state, NAME)
        if revision is None or not selection:
            return False
        if current is None or current.get("pending") or revision != current["revision"] or self.damaged(current):
            return True
        return cursors.rebuild_reason(current, revision, self.live.baseline_sha256(), selection, self.clock()) is not None

    def step(self) -> dict:
        now = self.clock()
        revision = self.live.revision()
        current = cursors.load(self.state, NAME)
        have = current.get("revision") if current else None
        if revision is None:
            return self.result("idle", have, "no_revision")
        if current and current.get("pending"):
            return self.finish(current, now)
        selection = self.live.selection()
        if not selection:
            return self.result("idle", have)
        reason, ids = cursors.decide(current, revision, self.live.baseline_sha256(), selection, now, self.live)
        if current and not reason:
            reason = self.damaged(current)
        if reason is None and revision == have:
            return self.result("idle", have)
        try:
            pending = self.rebuild(reason, revision, selection, now) if reason else self.delta(current, ids, revision, now)
        except wb.BundleError:
            return self.result("idle", have, "build_failed")
        if pending is None:   # revision mới nhưng không có tin nào của nhóm đã chọn: tiến con trỏ, không đẩy gì
            self.save({**current, "revision": revision}, now)
            return self.result("idle", revision)
        self.save({**(current or {}), "pending": pending}, now)
        return self.finish({**(current or {}), "pending": pending}, now)

    def rebuild(self, reason: str, revision: int, selection: list[str], now: float) -> dict:
        source = wb.Source(self.live.dir)
        report = wb.build(source, self.out, fetch=self.fetch, transcode=self.transcode, max_fetch=self.max_fetch,
                          now=now, max_age_days=self.max_age_days)
        wb.write_atomic(self.out / wb.REPORT, wb.dump({**report, "delta_bytes": 0, "delta_lines": 0, "revision": revision}))
        return {"revision": revision, "baseline_sha256": self.live.baseline_sha256(), "selection_sha256": cursors.selection_sha256(selection),
                "data_dir": report["data_dir"], "delta_bytes": 0, "delta_lines": 0, "built_at": cursors.now_iso(now), "reason": reason}

    def delta(self, current: dict, ids: set[str], revision: int, now: float) -> dict | None:
        source = wb.Source(self.live.dir)
        rows = self.live.rows_for(ids, {cid for cid in self.live.selection() if cid in source.conversations})
        if not rows:
            return None
        directory = self.out / current["data_dir"]
        path = directory / DELTA
        if path.is_file() and path.stat().st_size > current["delta_bytes"]:
            with path.open("r+b") as stream:   # phần dư của lượt chết trước khi lưu `pending`: chưa từng được gửi, bỏ đi
                stream.truncate(current["delta_bytes"])
        media = wb.Media(self.out, source, self.fetch, self.transcode, self.max_fetch, now, self.max_age_days)
        known = read_json(directory / "media.json", {})
        media.items = dict(known)
        users = read_json(directory / "users.json", {"self_user": source.self_user, "users": {}})
        lines = []
        for row in rows:
            if row.get("deleted"):
                lines.append({**clean_row(row), "deleted": True})   # giống hệt dòng tin xóa của một bản dựng đầy đủ
                continue
            clean = clean_row(row)
            if row.get("message_type") in wb.IMAGE_TYPES or row.get("client_message_id") in media.local:
                found = media.for_message(row, row.get("body"))
                if found:
                    clean["media"] = found
            lines.append(clean)
            sender = row.get("sender_id")
            if isinstance(sender, str) and sender in source.users:
                users.setdefault("users", {}).setdefault(sender, source.users[sender])
        with path.open("ab") as stream:
            stream.write(b"".join(wb.dump(line) + b"\n" for line in lines))
            stream.flush()
            os.fsync(stream.fileno())
        if media.items != known:
            wb.write_atomic(directory / "media.json", wb.dump(media.items))
        wb.write_atomic(directory / "users.json", wb.dump(users))
        media.save_cache()
        pending = {key: value for key, value in current.items() if key not in ("pending", "updated_at")}
        pending.update(revision=revision, delta_bytes=path.stat().st_size, delta_lines=current["delta_lines"] + len(lines), reason="delta")
        report = read_json(self.out / wb.REPORT)
        wb.write_atomic(self.out / wb.REPORT, wb.dump({**report, "delta_bytes": pending["delta_bytes"],
                                                       "delta_lines": pending["delta_lines"], "revision": revision}))
        return pending

    def plan(self, data_dir: str) -> pusher.Plan:
        items = []
        for directory in sorted(path for path in self.out.glob("data-*") if path.is_dir()):
            for path in sorted(directory.iterdir()):
                if path.is_file() and ".tmp-" not in path.name:
                    mutable = directory.name == data_dir and path.name in MUTABLE
                    items.append(pusher.Item(f"{directory.name}/{path.name}", path, immutable=not mutable))
        for path in sorted((self.out / "media").glob("*")):
            if path.is_file() and ".tmp-" not in path.name:
                items.append(pusher.Item(f"media/{path.name}", path, immutable=True))
        return pusher.Plan(self.target, tuple(items), pusher.Item(wb.REPORT, self.out / wb.REPORT), PRUNE)

    def finish(self, current: dict, now: float) -> dict:
        pending = current["pending"]
        sent = 0
        if not self.dry_run:
            try:
                sent = pusher.push(self.plan(pending["data_dir"]), run=self.run)["bytes"]
            except pusher.PushError:
                return self.result("retry", current.get("revision"), "push_failed", reason=pending.get("reason"))
        done = {key: value for key, value in {**current, **pending}.items() if key != "pending"}
        self.save(done, now)
        return self.result("rebuild" if pending.get("reason") != "delta" else "delta", done["revision"], sent=sent, reason=pending.get("reason"))
