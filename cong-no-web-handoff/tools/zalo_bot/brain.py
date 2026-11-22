"""Tiến trình bộ não `v7-zalo-bot` (ZALO-BOT-01): nghe socket Unix của kênh, trả lời theo `core.Brain`, ghi nhịp tim mỗi phút.

    v7_zalo_bot.py [--check]

`--check` chỉ đọc cấu hình rồi in số người trong danh sách và cờ bật (không in id hay login), dùng khi cài.

Mỗi lúc chỉ giữ một kết nối kênh; kênh mới nối thì kết nối cũ bị đóng. Dòng sai khuôn bị bỏ và đếm (`bad_line`).
Bản phát hành đổi (`current` trỏ chỗ khác) thì tiến trình tự thoát để systemd chạy lại bằng mã mới, vì lệnh deploy chỉ được
khởi động lại API.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import stat
import sys
import time
from collections.abc import Callable

from . import VERSION, config, core, protocol, state

HEARTBEAT = 60
PRUNE_EVERY = 86_400


class Service:
    def __init__(self, cfg: config.Config, users: dict[str, config.User], memory: core.Memory, clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self.users = users
        self.clock = clock
        self.brain = core.Brain(users, enabled=cfg.enabled, memory=memory)
        self.kenh = state.KenhView(since=clock())
        self.counters = state.Counters()
        self.logbook = state.LogBook(cfg.log_dir)
        self.writer: asyncio.StreamWriter | None = None
        self.release = os.path.realpath(cfg.release_link)
        self.stop = asyncio.Event()
        self.error: str | None = None
        self._pruned_at = 0.0

    def on_line(self, line: bytes) -> list[bytes]:
        """Một dòng từ kênh → các dòng trả lại kênh. Không ném lỗi vì dữ liệu kênh."""
        now = self.clock()
        try:
            event = protocol.parse(line)
        except protocol.ProtocolError:
            self.counters.add("bad_line", now)
            return []
        self.kenh.seen(now)
        if isinstance(event, protocol.Hello):
            self.kenh.version = event.kenh_version
            return []
        if isinstance(event, protocol.State):
            self.kenh.set(event.state, event.code, now)
            return []
        if isinstance(event, protocol.Sent):
            self.counters.add("sent_ok" if event.ok else "sent_failed", now)
            return []
        outcome = self.brain.on_message(event, now)
        self.counters.add(outcome.counter, now)
        if outcome.log is not None:
            try:
                self.logbook.write(outcome.log, now)
            except OSError:
                self.error = "log_write_failed"
        if outcome.counter != "duplicate":
            self.save_memory()
        return outcome.commands

    def save_memory(self) -> None:
        try:
            state.save_memory(self.cfg.memory_file, self.brain.memory)
        except OSError:
            self.error = "memory_write_failed"

    def write_status(self) -> None:
        data = state.status(now=self.clock(), version=VERSION, enabled=self.cfg.enabled, users=len(self.users), kenh=self.kenh,
                            counters=self.counters, error=self.error)
        try:
            state.write_status(self.cfg.status_file, data)
        except OSError:
            print("zalo-bot: không ghi được status.json", file=sys.stderr)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        now = self.clock()
        if self.writer is not None:
            self.counters.add("kenh_replaced", now)
            self.writer.close()
        self.writer = writer
        self.kenh.attach(now)
        try:
            while True:
                try:
                    line = await reader.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    self.counters.add("bad_line", self.clock())   # dòng quá dài: đóng kết nối, kênh tự nối lại
                    break
                if not line:
                    break
                for command in self.on_line(line):
                    writer.write(command)
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            if self.writer is writer:
                self.writer = None
                self.kenh.detach(self.clock())
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()

    def tick(self) -> None:
        """Việc mỗi phút: nhịp tim, dọn nhật ký mỗi ngày, phát hiện bản phát hành mới."""
        now = self.clock()
        self.write_status()
        if now - self._pruned_at >= PRUNE_EVERY:
            self._pruned_at = now
            self.brain.memory.prune(now)
            self.save_memory()
            with contextlib.suppress(OSError):
                self.logbook.prune(now)
        if os.path.realpath(self.cfg.release_link) != self.release:
            print("zalo-bot: bản phát hành đổi, thoát để systemd chạy lại", file=sys.stderr)
            self.stop.set()

    async def heartbeat(self) -> None:
        while not self.stop.is_set():
            self.tick()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.stop.wait(), HEARTBEAT)


def _clear_socket(path: os.PathLike) -> None:
    """Socket cũ của lượt chạy trước còn sót thì xóa; file khác cùng tên thì không đụng (lỗi cấu hình)."""
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(mode):
        raise config.ConfigError("socket_path_not_socket")
    os.unlink(path)


async def serve(cfg: config.Config, users: dict[str, config.User], *, ready: Callable[[Service], None] | None = None) -> int:
    """Chạy tới khi nhận SIGTERM/SIGINT hoặc bản phát hành đổi. `ready` (cho test) nhận `Service` khi socket đã nghe."""
    service = Service(cfg, users, state.load_memory(cfg.memory_file))
    _clear_socket(cfg.socket)
    server = await asyncio.start_unix_server(service.handle, path=str(cfg.socket), limit=protocol.MAX_LINE + 1)
    os.chmod(cfg.socket, 0o660)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, service.stop.set)
    beat = asyncio.create_task(service.heartbeat())
    if ready is not None:
        ready(service)
    await service.stop.wait()
    server.close()
    if service.writer is not None:
        service.writer.close()
    await server.wait_closed()
    await beat
    with contextlib.suppress(FileNotFoundError):
        os.unlink(cfg.socket)
    service.kenh.detach(service.clock())
    service.save_memory()
    service.write_status()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bộ não bot Zalo hỏi đáp công nợ (ZALO-BOT-01).")
    parser.add_argument("--check", action="store_true", help="chỉ kiểm cấu hình, không chạy")
    args = parser.parse_args(argv)
    cfg = config.from_env()
    try:
        users = config.load_users(cfg.users_file)
    except config.ConfigError as error:
        print(f"zalo-bot: cấu hình sai ({error})", file=sys.stderr)
        return 2
    if args.check:
        print(f"zalo-bot: {len(users)} người trong danh sách; trả lời {'bật' if cfg.enabled else 'tắt'}")
        return 0
    if os.name != "posix":
        print("zalo-bot: chỉ chạy trên Linux (socket Unix)", file=sys.stderr)
        return 2
    try:
        return asyncio.run(serve(cfg, users))
    except config.ConfigError as error:
        print(f"zalo-bot: cấu hình sai ({error})", file=sys.stderr)
        return 2
