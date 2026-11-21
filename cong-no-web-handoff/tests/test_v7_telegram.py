"""TELEGRAM-01: bộ gửi tin báo thu chi trên hao, với Telegram giả và trang Thu chi giả (không mạng, không token thật)."""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_telegram as tg  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
EVENING = datetime(2026, 11, 20, 21, 0, tzinfo=VN).timestamp()
MORNING = datetime(2026, 11, 20, 9, 0, tzinfo=VN).timestamp()
IMG, OTHER_IMG = "c" * 64, "d" * 64
CFG = {"token": "123:token-gia", "chat": "-100999", "link": "https://web.example"}


def item(mid, status="WAITING", day="2026-11-20", amount=5_000_000, direction="thu", **extra):
    return {"message_id": mid, "status": status, "day": day, "amount_vnd": amount, "direction": direction, "sent_at": 1_795_000_000_000,
            "conversation_name": "Nhóm thử", "target": {"kind": "so", "id": 1, "label": "KHACH A"}, "text": "nội dung tin gốc bí mật",
            "media": [], "ledger_vnd": None, **extra}


class Sender:
    def __init__(self, fail=None):
        self.sent, self.fail = [], fail

    def __call__(self, cfg, text, photo=None):
        if self.fail:
            raise self.fail
        self.sent.append((text, photo))


class TelegramTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.box = self.dir / "outbox.json"
        self.items = []
        for patcher in (patch.dict(os.environ, {"WEBDEBIT_ZALO_READS_DIR": str(self.dir / "reads")}),):
            patcher.start()
            self.addCleanup(patcher.stop)

    def build(self, start, end, runner, actor, now):
        return {"unavailable": False, "items": list(self.items), "totals": {"amount_diff": 1}}

    def run_once(self, sender, now=MORNING):
        return tg.run_once(None, CFG, now, tg.Outbox(self.box), sender, self.build)

    def test_flag_and_secrets_stay_off_by_default(self):
        env = self.dir / "telegram.env"
        env.write_text("TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_CHAT_ID=-100\n# chú thích\n", encoding="utf-8")
        with patch.dict(os.environ, {"WEBDEBIT_TELEGRAM": "0"}):
            self.assertIsNone(tg.config(str(env)))
        with patch.dict(os.environ, {"WEBDEBIT_TELEGRAM": "1"}):
            self.assertEqual(tg.config(str(env)), {"token": "123:abc", "chat": "-100", "link": ""})
            env.write_text("TELEGRAM_BOT_TOKEN=123:abc\n", encoding="utf-8")
            self.assertIsNone(tg.config(str(env)))   # thiếu mã nhóm: tắt
            self.assertIsNone(tg.config(str(self.dir / "khong-co.env")))
        self.assertIsNone(tg.start(None, cfg=None) if os.getenv("WEBDEBIT_TELEGRAM") != "1" else None)

    def test_events_have_stable_keys_and_no_original_chat_text(self):
        self.items = [item("a"), item("b", "AMOUNT_DIFF", amount=4_500_000, ledger_vnd=5_000_000), item("c", "MISSING", day="2026-11-14"),
                      item("d", "NOT_CASH")]
        found = tg.events(self.build(None, None, None, None, EVENING), EVENING, CFG["link"])
        self.assertEqual([event["key"] for event in found], ["new:a", "new:b", "diff:b:4500000:5000000", "missing:c", "daily:2026-11-20"])
        text = "\n".join(event["text"] for event in found)
        self.assertNotIn("nội dung tin gốc", text)   # không bao giờ gửi chữ gốc của tin chat
        self.assertIn("Thu 5.000.000 đ · KHACH A", text)
        self.assertIn("https://web.example/thu-chi.html?m=a", text)
        self.assertEqual([event["key"] for event in tg.events(self.build(None, None, None, None, MORNING), MORNING)][-1], "missing:c")   # chưa tới giờ tổng

    def test_outbox_sends_each_event_once_starting_from_a_baseline(self):
        self.items = [item("old")]
        sender = Sender()
        self.assertEqual(self.run_once(sender)["baseline"], 1)   # lần bật đầu: không xả khoản cũ ra nhóm
        self.items.append(item("new"))
        self.assertEqual((self.run_once(sender)["sent"], [text.split(" · ")[0] for text, _ in sender.sent]), (1, ["Khoản mới: Thu 5.000.000 đ"]))
        self.assertEqual(self.run_once(sender)["sent"], 0)   # chạy lại: không gửi trùng
        self.items += [item(f"n{index}") for index in range(12)]
        self.assertEqual((self.run_once(sender)["sent"], self.run_once(sender)["sent"]), (10, 2))   # tối đa 10 tin mỗi lượt

    def test_a_crash_while_sending_is_never_resent_and_errors_retry_or_stop(self):
        self.items = []
        self.run_once(Sender())   # mốc rỗng
        self.items = [item("x")]

        class Killed(BaseException):
            pass

        with self.assertRaises(Killed):
            self.run_once(Sender(Killed()))
        reloaded = tg.Outbox(self.box)
        self.assertEqual(reloaded.items["new:x"]["state"], "uncertain")   # Telegram có thể đã nhận: không gửi lại
        sender = Sender()
        self.assertEqual((self.run_once(sender)["sent"], sender.sent), (0, []))
        self.items = [item("y"), item("z")]
        flaky = Sender(tg.SendError(retry=True))
        self.assertEqual(self.run_once(flaky)["retry"], 2)
        refused = Sender(tg.SendError(retry=False))
        tg.Outbox(self.box)   # đọc lại không đổi trạng thái retry
        self.assertEqual(self.run_once(Sender())["sent"], 2)   # lỗi mạng: lượt sau gửi được
        self.items = [item("w")]
        self.assertEqual(self.run_once(refused)["failed"], 1)
        self.assertEqual(self.run_once(Sender())["sent"], 0)   # Telegram từ chối: không thử lại

    def test_only_the_redacted_copy_is_ever_sent(self):
        self.run_once(Sender())
        hidden = self.dir / "reads" / "redacted-w1"
        hidden.mkdir(parents=True)
        (hidden / f"{IMG}.jpg").write_bytes(b"\xff\xd8\xff anh-da-che")
        self.items = [item("p", media=[{"id": IMG}]), item("q", media=[{"id": OTHER_IMG}])]
        sender = Sender()
        self.run_once(sender)
        self.assertEqual([photo for _, photo in sender.sent], [hidden / f"{IMG}.jpg", None])   # không có bản che: chỉ gửi chữ
        self.assertIsNone(tg.redacted("../" + IMG))

    def test_send_puts_the_token_only_in_the_url(self):
        calls = []
        request = lambda url, body, kind: calls.append((url, body, kind))  # noqa: E731
        tg.send(CFG, "Khoản mới", None, request)
        photo = self.dir / "anh.jpg"
        photo.write_bytes(b"\xff\xd8\xff anh")
        tg.send(CFG, "Khoản mới", photo, request)
        (url, body, kind), (photo_url, photo_body, photo_kind) = calls
        self.assertEqual((url.endswith("/sendMessage"), kind, json.loads(body)["chat_id"]), (True, "application/json", "-100999"))
        self.assertTrue(photo_url.endswith("/sendPhoto") and photo_kind.startswith("multipart/form-data"))
        self.assertIn(b"\xff\xd8\xff anh", photo_body)
        for sent in (body, photo_body):
            self.assertNotIn(b"token-gia", sent)
        self.assertIn("bot123:token-gia", url)


if __name__ == "__main__":
    unittest.main()
