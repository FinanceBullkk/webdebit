"""Quyết định cho mỗi tin từ kênh. PR-1 chỉ trả câu cố định; PR-2 nối model và công cụ đọc API.

Hàm thuần: nhận tin đã kiểm và giờ, trả lệnh gửi kênh, dòng nhật ký và tên bộ đếm. Không mở socket, không đọc file,
nên test chạy được trên mọi máy.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field

from . import protocol
from .config import User

GREETING = ("Chào bạn. Đây là máy trả lời tự động của web công nợ: chỉ đọc số, không ghi gì. "
            "Câu trả lời có số luôn kèm nguồn và giờ dữ liệu.")
NOT_READY = "Bot đang được dựng, chưa trả lời số. Bạn xem số trên web giúp mình nhé."
LATE = "Tin đến muộn, bạn hỏi lại giúp mình."
NO_IMAGE = "Mình chưa đọc ảnh. Ảnh chuyển khoản vẫn do máy Zalo đọc và đưa lên trang Thu chi."
TEXT_ONLY = "Mình chỉ đọc câu hỏi bằng chữ."

STALE_SECONDS = 600        # kênh nối lại mà tin cũ hơn 10 phút: không trả lời số, chỉ nhờ hỏi lại
RATE_WINDOW = 60
RATE_MAX = 6               # chặn vòng lặp do lỗi: tối đa 6 tin gửi mỗi phút cho một người
SEEN_KEEP = 86_400         # nhớ mã tin 24 giờ để chống trùng qua khởi động lại
SEEN_MAX = 2000


@dataclass
class Outcome:
    counter: str
    commands: list[bytes] = field(default_factory=list)
    log: dict | None = None
    ask: User | None = None      # có model: câu hỏi chờ bộ não tra (brain.Service.answer), chưa có câu trả lời


class Memory:
    """Mã tin đã thấy và người đã được chào; lưu ở `brain-state.json` để còn qua khởi động lại."""

    def __init__(self, seen: dict[str, int] | None = None, greeted: set[str] | None = None):
        self.seen = dict(seen or {})        # mã tin → giây Unix (số nguyên) lúc thấy
        self.greeted = set(greeted or ())

    def seen_before(self, msg_id: str, now: float) -> bool:
        if msg_id in self.seen:
            return True
        self.seen[msg_id] = int(now)
        if len(self.seen) > SEEN_MAX:
            self.prune(now)
        return False

    def prune(self, now: float) -> None:
        fresh = {key: at for key, at in self.seen.items() if now - at < SEEN_KEEP}
        if len(fresh) > SEEN_MAX:
            fresh = dict(sorted(fresh.items(), key=lambda item: item[1])[-SEEN_MAX:])
        self.seen = fresh

    def to_json(self) -> dict:
        return {"schema": 1, "seen": dict(self.seen), "greeted": sorted(self.greeted)}

    @classmethod
    def from_json(cls, data: object) -> Memory:
        """File hỏng hay sai khuôn: bắt đầu lại rỗng (chỉ mất chống trùng 24 giờ và câu chào, không mất dữ liệu)."""
        if not isinstance(data, dict) or data.get("schema") != 1:
            return cls()
        seen = data.get("seen")
        greeted = data.get("greeted")
        clean_seen = {key: at for key, at in seen.items()
                      if isinstance(key, str) and protocol.ID.fullmatch(key) and isinstance(at, int) and not isinstance(at, bool)
                      } if isinstance(seen, dict) else {}
        clean_greeted = {key for key in greeted if isinstance(key, str) and protocol.ID.fullmatch(key)} if isinstance(greeted, list) else set()
        return cls(clean_seen, clean_greeted)


class Brain:
    def __init__(self, users: dict[str, User], *, enabled: bool, memory: Memory, run_id: str | None = None, answering: bool = False):
        self.users = users
        self.enabled = enabled
        self.memory = memory
        self.answering = answering      # có model (PR-2b): câu hỏi chữ được tra, thay cho câu cố định
        self.run_id = run_id or format(int(time.time()), "x")
        self._sent: dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        self._refs = 0

    def _ref(self) -> str:
        self._refs += 1
        return f"{self.run_id}-{self._refs}"

    def _allow(self, thread_id: str, now: float) -> bool:
        times = self._sent[thread_id]
        while times and now - times[0] >= RATE_WINDOW:
            times.popleft()
        if len(times) >= RATE_MAX:
            return False
        times.append(now)
        return True

    def on_message(self, msg: protocol.Message, now: float) -> Outcome:
        if self.memory.seen_before(msg.msg_id, now):
            return Outcome("duplicate")
        user = self.users.get(msg.from_id)
        if user is None:
            # Người lạ: không trả lời; nhật ký một dòng có id người gửi (để P0 thêm người dùng vào danh sách), không có nội dung.
            return Outcome("stranger", log={"outcome": "stranger", "from_id": msg.from_id})
        base = {"login": user.login, "msg_id": msg.msg_id, "kind": msg.kind}
        if msg.thread_id != msg.from_id:
            # Chat riêng của zca-js có thread = người gửi; khác là tin nhóm lọt qua kênh. Không trả lời trong nhóm (Q8).
            return Outcome("not_private", log={**base, "outcome": "not_private"})
        if not self.enabled:
            return Outcome("disabled", log={**base, "outcome": "disabled"})
        fresh = now - msg.ts_ms / 1000 <= STALE_SECONDS
        if self.answering and fresh and msg.kind == "text":
            opening: list[bytes] = []
            if msg.from_id not in self.memory.greeted:
                self.memory.greeted.add(msg.from_id)
                if self._allow(msg.thread_id, now):
                    opening.append(protocol.send(self._ref(), msg.thread_id, GREETING, msg.msg_id))
            return Outcome("ask", [*opening, protocol.typing(msg.thread_id)], ask=user)
        if not fresh:
            outcome, replies = "late", [LATE]
        elif msg.kind == "image":
            outcome, replies = "image", [NO_IMAGE]
        elif msg.kind != "text":
            outcome, replies = "not_text", [TEXT_ONLY]
        else:
            outcome, replies = "fixed", [NOT_READY]
        if msg.from_id not in self.memory.greeted:
            replies = [GREETING, *replies]
            self.memory.greeted.add(msg.from_id)
        commands: list[bytes] = []
        for text in replies:
            for part in protocol.split_text(text):
                if not self._allow(msg.thread_id, now):
                    return Outcome("rate_limited", commands, {**base, "outcome": "rate_limited", "replies": len(commands)})
                commands.append(protocol.send(self._ref(), msg.thread_id, part, None if commands else msg.msg_id))
        question = msg.text if msg.kind == "text" else None
        return Outcome(outcome, commands, {**base, "outcome": outcome, "question": question, "truncated": msg.truncated,
                                           "replies": len(commands)})

    def reply(self, msg: protocol.Message, text: str, now: float) -> tuple[list[bytes], bool]:
        """Câu trả lời đã kiểm → lệnh gửi (tách tin dài, trích câu hỏi ở tin đầu). `False` nếu bị giới hạn 6 tin/phút cắt."""
        commands: list[bytes] = []
        for part in protocol.split_text(text):
            if not self._allow(msg.thread_id, now):
                return commands, False
            commands.append(protocol.send(self._ref(), msg.thread_id, part, None if commands else msg.msg_id))
        return commands, True
