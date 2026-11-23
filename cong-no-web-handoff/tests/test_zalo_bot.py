"""Bot Zalo hỏi đáp (ZALO-BOT-01) PR-1: giao thức kênh ↔ bộ não, danh sách người hỏi, quyết định trả lời, file trạng thái,
bộ đọc nhịp tim của tab Máy chạy và máy canh. Không cần Zalo, mạng hay systemd thật; phần socket Unix chỉ chạy trên Linux."""

import asyncio
import datetime as dt
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "web"))
import v7_machine  # noqa: E402
import v7_watchdog as dog  # noqa: E402
from zalo_bot import brain, config, core, protocol, state  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = dt.datetime(2026, 11, 22, 10, 0, tzinfo=VN).timestamp()
USER = config.User("1111", "chu@example.com", "admin")


def line(**payload) -> bytes:
    return json.dumps({"v": 1, **payload}).encode()


def message(msg_id="m1", *, frm="1111", thread=None, ts=None, kind="text", text="khách A còn nợ bao nhiêu"):
    return protocol.Message(msg_id, thread or frm, frm, int((NOW if ts is None else ts) * 1000), kind, text, False)


def sent_texts(commands):
    return [json.loads(c)["text"] for c in commands]


class ProtocolTests(unittest.TestCase):
    def test_parses_each_line_type(self):
        self.assertEqual(protocol.parse(line(type="hello", kenh_version="0.1.0", own_id="999")), protocol.Hello("0.1.0", "999"))
        self.assertEqual(protocol.parse(line(type="state", state="online", code=None)), protocol.State("online", None))
        got = protocol.parse(line(type="message", msg_id="7", thread_id="1111", from_id="1111", ts=1_700_000_000_000, kind="text", text="hỏi"))
        self.assertEqual(got, protocol.Message("7", "1111", "1111", 1_700_000_000_000, "text", "hỏi", False))
        self.assertEqual(protocol.parse(line(type="sent", ref="r-1", ok=False, code="zalo_error")), protocol.Sent("r-1", False, "zalo_error"))

    def test_rejects_anything_off_shape_with_a_short_code(self):
        good = {"type": "message", "msg_id": "7", "thread_id": "1", "from_id": "1", "ts": 1_700_000_000_000, "kind": "text", "text": "x"}
        cases = {
            b"not json": "bad_json",
            json.dumps({**good, "v": 2}).encode(): "bad_version",
            line(**{**good, "msg_id": "có dấu"}): "bad_msg_id",
            line(**{**good, "from_id": 7}): "bad_from_id",
            line(**{**good, "ts": True}): "bad_ts",
            line(**{**good, "kind": "voice"}): "bad_kind",
            line(**{**good, "text": "  "}): "empty_text",
            line(type="state", state="happy"): "bad_state",
            line(type="state", state="error", code="Có chữ tự do"): "bad_code",
            line(type="sent", ref="r", ok="yes"): "bad_ok",
            line(type="hack"): "bad_type",
            b"x" * (protocol.MAX_LINE + 1): "too_long",
        }
        for raw, code in cases.items():
            with self.subTest(code=code), self.assertRaises(protocol.ProtocolError) as caught:
                protocol.parse(raw)
            self.assertEqual(str(caught.exception), code)

    def test_long_question_is_cut_and_marked(self):
        got = protocol.parse(line(type="message", msg_id="7", thread_id="1", from_id="1", ts=1, kind="text", text="a" * 5000))
        self.assertEqual((len(got.text), got.truncated), (protocol.MAX_TEXT_IN, True))

    def test_commands_are_one_json_line_each(self):
        raw = protocol.send("r-1", "1111", "Chào", "m1")
        self.assertTrue(raw.endswith(b"\n") and raw.count(b"\n") == 1)
        self.assertEqual(json.loads(raw), {"v": 1, "type": "send", "ref": "r-1", "thread_id": "1111", "text": "Chào", "quote_msg_id": "m1"})
        self.assertEqual(json.loads(protocol.typing("1111")), {"v": 1, "type": "typing", "thread_id": "1111"})
        with self.assertRaises(ValueError):
            protocol.send("r-1", "1111", "x" * (protocol.MAX_TEXT_OUT + 1))

    def test_split_text_keeps_every_word_and_prefers_line_breaks(self):
        text = "\n".join(f"Dòng {i}: " + "chữ " * 30 for i in range(40))
        parts = protocol.split_text(text, 500)
        self.assertTrue(all(len(p) <= 500 for p in parts))
        self.assertEqual(" ".join(" ".join(parts).split()), " ".join(text.split()))
        self.assertTrue(all(p.startswith("Dòng") for p in parts))
        self.assertEqual(protocol.split_text("ngắn"), ["ngắn"])


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.file = self.dir / "zalo-bot.json"

    def write(self, data):
        self.file.write_text(json.dumps(data), encoding="utf-8")
        if os.name == "posix":
            os.chmod(self.file, 0o640)

    def test_missing_file_means_nobody_may_ask(self):
        self.assertEqual(config.load_users(self.dir / "khong-co.json"), {})

    def test_reads_users_by_zalo_id(self):
        self.write({"users": [{"zalo_id": "1111", "login": "chu@example.com", "role": "admin"}]})
        self.assertEqual(config.load_users(self.file), {"1111": USER})

    def test_role_is_optional_and_only_caps_the_web_role(self):
        """F11: không ghi role thì web quyết (trần admin); ghi "user" thì bot luôn coi là user."""
        self.write({"users": [{"zalo_id": "1111", "login": "chu@example.com"}, {"zalo_id": "2222", "login": "nv@example.com", "role": "user"}]})
        users = config.load_users(self.file)
        self.assertEqual((users["1111"].role, users["2222"].role), ("admin", "user"))

    def test_ambiguous_or_wrong_files_stop_the_bot(self):
        bad = {"user_role": {"zalo_id": "1", "login": "a@b.c", "role": "boss"},
               "user_login": {"zalo_id": "1", "login": "không phải login", "role": "user"},
               "user_zalo_id": {"zalo_id": "", "login": "a@b.c", "role": "user"},
               "user_shape": {"zalo_id": "1", "login": "a@b.c", "role": "user", "extra": 1}}
        for code, row in bad.items():
            with self.subTest(code=code), self.assertRaises(config.ConfigError) as caught:
                self.write({"users": [row]})
                config.load_users(self.file)
            self.assertEqual(str(caught.exception), code)
        self.write({"users": [{"zalo_id": "1", "login": "a@b.c", "role": "user"}] * 2})
        with self.assertRaises(config.ConfigError):
            config.load_users(self.file)

    @unittest.skipUnless(os.name == "posix", "quyền file chỉ có nghĩa trên Linux")
    def test_file_others_can_write_is_refused(self):
        self.write({"users": []})
        os.chmod(self.file, 0o666)
        with self.assertRaises(config.ConfigError):
            config.load_users(self.file)

    def test_reply_flag_must_be_exactly_one(self):
        self.assertTrue(config.from_env({"WEBDEBIT_ZALO_BOT": "1"}).enabled)
        for value in ("", "0", "true", "yes"):
            self.assertFalse(config.from_env({"WEBDEBIT_ZALO_BOT": value}).enabled)


class BrainTests(unittest.TestCase):
    def setUp(self):
        self.brain = core.Brain({"1111": USER}, enabled=True, memory=core.Memory(), run_id="t")

    def test_first_question_gets_greeting_then_fixed_reply_quoting_the_question(self):
        out = self.brain.on_message(message(), NOW)
        self.assertEqual(out.counter, "fixed")
        self.assertEqual(sent_texts(out.commands), [core.GREETING, core.NOT_READY])
        self.assertEqual([json.loads(c)["quote_msg_id"] for c in out.commands], ["m1", None])
        self.assertEqual(out.log["question"], "khách A còn nợ bao nhiêu")
        again = self.brain.on_message(message("m2"), NOW + 1)
        self.assertEqual(sent_texts(again.commands), [core.NOT_READY])

    def test_strangers_get_nothing_and_leave_no_content(self):
        out = self.brain.on_message(message(frm="2222"), NOW)
        self.assertEqual((out.counter, out.commands, out.log), ("stranger", [], {"outcome": "stranger", "from_id": "2222"}))

    def test_same_message_twice_is_answered_once(self):
        self.brain.on_message(message(), NOW)
        self.assertEqual(self.brain.on_message(message(), NOW + 5).counter, "duplicate")

    def test_group_message_from_a_known_user_is_not_answered(self):
        out = self.brain.on_message(message(thread="group-9"), NOW)
        self.assertEqual((out.counter, out.commands), ("not_private", []))

    def test_off_switch_only_counts(self):
        off = core.Brain({"1111": USER}, enabled=False, memory=core.Memory())
        out = off.on_message(message(), NOW)
        self.assertEqual((out.counter, out.commands), ("disabled", []))
        self.assertNotIn("question", out.log)

    def test_late_image_and_other_kinds_get_fixed_sentences(self):
        self.brain.memory.greeted.add("1111")
        self.assertEqual(sent_texts(self.brain.on_message(message("a", ts=NOW - 601), NOW).commands), [core.LATE])
        self.assertEqual(sent_texts(self.brain.on_message(message("b", kind="image", text=None), NOW).commands), [core.NO_IMAGE])
        self.assertEqual(sent_texts(self.brain.on_message(message("c", kind="sticker", text=None), NOW).commands), [core.TEXT_ONLY])

    def test_runaway_loop_is_cut_at_six_messages_a_minute(self):
        self.brain.memory.greeted.add("1111")
        counters = [self.brain.on_message(message(f"m{i}"), NOW + i).counter for i in range(8)]
        self.assertEqual(counters, ["fixed"] * 6 + ["rate_limited"] * 2)
        self.assertEqual(self.brain.on_message(message("later"), NOW + 61).counter, "fixed")

    def test_memory_round_trip_prune_and_bad_file(self):
        memory = core.Memory()
        memory.seen_before("old", NOW - 90_000)
        memory.seen_before("new", NOW)
        memory.greeted.add("1111")
        back = core.Memory.from_json(json.loads(json.dumps(memory.to_json())))
        self.assertEqual((set(back.seen), back.greeted), ({"old", "new"}, {"1111"}))
        back.prune(NOW)
        self.assertEqual(set(back.seen), {"new"})
        self.assertEqual(core.Memory.from_json({"schema": 9}).seen, {})
        self.assertEqual(core.Memory.from_json({"schema": 1, "seen": {"có dấu": 1, "ok": True}, "greeted": [5]}).seen, {})


class StateTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_counters_restart_each_vietnam_day(self):
        counters = state.Counters()
        counters.add("fixed", NOW)
        counters.add("fixed", NOW + 60)
        self.assertEqual(counters.snapshot(NOW + 60), {"fixed": 2})
        midnight = dt.datetime(2026, 11, 23, 0, 0, 1, tzinfo=VN).timestamp()
        self.assertEqual(counters.snapshot(midnight), {})
        counters.add("stranger", midnight)
        self.assertEqual(counters.snapshot(midnight), {"stranger": 1})

    def test_status_has_codes_counts_and_times_only(self):
        kenh = state.KenhView(since=NOW)
        kenh.attach(NOW)
        kenh.set("online", None, NOW + 5)
        counters = state.Counters()
        counters.add("fixed", NOW)
        data = state.status(now=NOW + 60, version="0.1.0", enabled=True, users=1, kenh=kenh, counters=counters, error=None)
        self.assertEqual(data["kenh"]["state"], "online")
        self.assertEqual(data["kenh"]["since"], "2026-11-22T10:00:05+07:00")
        self.assertEqual((data["schema"], data["counts"], data["users"]), (1, {"fixed": 1}, 1))
        path = self.dir / "status.json"
        state.write_status(path, data)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["at"], "2026-11-22T10:01:00+07:00")
        if os.name == "posix":
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_log_book_writes_by_month_and_drops_months_past_90_days(self):
        book = state.LogBook(self.dir / "log")
        book.write({"outcome": "fixed"}, NOW)
        (self.dir / "log" / "2026-07.jsonl").write_text("{}\n", encoding="utf-8")
        (self.dir / "log" / "2026-08.jsonl").write_text("{}\n", encoding="utf-8")
        self.assertEqual(json.loads((self.dir / "log" / "2026-11.jsonl").read_text(encoding="utf-8"))["outcome"], "fixed")
        self.assertEqual(book.prune(NOW), ["2026-07.jsonl"])     # 31/8 cách 22/11 là 83 ngày: giữ tháng 8
        self.assertEqual(sorted(p.name for p in (self.dir / "log").iterdir()), ["2026-08.jsonl", "2026-11.jsonl"])

    def test_broken_memory_file_starts_empty(self):
        path = self.dir / "brain-state.json"
        path.write_text("{hỏng", encoding="utf-8")
        self.assertEqual(state.load_memory(path).seen, {})
        state.save_memory(path, core.Memory({"a": NOW}, {"1111"}))
        self.assertEqual(state.load_memory(path).greeted, {"1111"})


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.cfg = config.Config(enabled=True, users_file=self.dir / "u.json", socket=self.dir / "s.sock", state_dir=self.dir / "state",
                                 release_link=self.dir / "current")
        self.clock = [NOW]
        self.service = brain.Service(self.cfg, {"1111": USER}, core.Memory(), clock=lambda: self.clock[0])

    def test_lines_update_kenh_state_and_answers_are_logged(self):
        self.assertEqual(self.service.on_line(b"rac\n"), [])
        self.assertEqual(self.service.on_line(line(type="hello", kenh_version="0.1.0", own_id="999")), [])
        self.service.on_line(line(type="state", state="online"))
        out = self.service.on_line(line(type="message", msg_id="m1", thread_id="1111", from_id="1111", ts=int(NOW * 1000), kind="text", text="hỏi"))
        self.assertEqual(len(out), 2)
        self.assertEqual((self.service.kenh.state, self.service.kenh.version), ("online", "0.1.0"))
        self.assertEqual(self.service.counters.snapshot(NOW), {"bad_line": 1, "fixed": 1})
        log = (self.cfg.log_dir / "2026-11.jsonl").read_text(encoding="utf-8")
        self.assertIn('"question": "hỏi"', log)
        self.assertIn("m1", state.load_memory(self.cfg.memory_file).seen)

    def test_tick_writes_heartbeat_and_exits_when_release_changes(self):
        self.service.tick()
        data = json.loads(self.cfg.status_file.read_text(encoding="utf-8"))
        self.assertEqual((data["kenh"]["state"], data["enabled"]), ("offline", True))
        self.assertFalse(self.service.stop.is_set())
        self.service.release = "/srv/v7/auto-releases/cu"
        with redirect_stderr(io.StringIO()) as err:
            self.service.tick()
        self.assertTrue(self.service.stop.is_set())
        self.assertIn("bản phát hành đổi", err.getvalue())


@unittest.skipUnless(os.name == "posix", "socket Unix chỉ có trên Linux; hao chạy Linux")
class SocketTests(unittest.TestCase):
    def test_kenh_round_trip_over_unix_socket(self):
        base = Path(tempfile.mkdtemp(dir="/tmp"))
        cfg = config.Config(enabled=True, users_file=base / "u.json", socket=base / "k.sock", state_dir=base / "state", release_link=base / "cur")

        async def scenario():
            started: list[brain.Service] = []
            task = asyncio.create_task(brain.serve(cfg, {"1111": USER}, ready=started.append))
            for _ in range(200):
                if started:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(cfg.socket.stat().st_mode & 0o777, 0o660)
            reader, writer = await asyncio.open_unix_connection(str(cfg.socket))
            writer.write(line(type="hello", kenh_version="0.1.0", own_id=None) + b"\n")
            writer.write(line(type="message", msg_id="m1", thread_id="1111", from_id="1111", ts=int(time.time() * 1000), kind="text", text="hỏi") + b"\n")
            await writer.drain()
            replies = [json.loads(await asyncio.wait_for(reader.readline(), 5)) for _ in range(2)]
            writer.close()
            started[0].stop.set()
            self.assertEqual(await asyncio.wait_for(task, 5), 0)
            return replies

        replies = asyncio.run(scenario())
        self.assertEqual([r["type"] for r in replies], ["send", "send"])
        self.assertFalse(cfg.socket.exists())
        self.assertEqual(json.loads(cfg.status_file.read_text(encoding="utf-8"))["kenh"]["state"], "offline")


class HeartbeatReaderTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.file = self.dir / "status.json"
        patcher = patch.dict(os.environ, {"WEBDEBIT_ZALO_BOT_STATUS": str(self.file)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, at=NOW, **extra):
        data = {"schema": 1, "at": state.now_iso(at), "version": "0.1.0", "enabled": True, "users": 1,
                "kenh": {"state": "online", "code": None, "since": state.now_iso(at - 3600), "version": "0.1.0", "last_event_at": None},
                "counts": {"fixed": 3}, "error": None}
        data.update(extra)
        self.file.write_text(json.dumps(data), encoding="utf-8")

    def test_machine_reader_states(self):
        self.assertEqual(v7_machine.zalo_bot(NOW), {"state": "missing"})
        self.write()
        view = v7_machine.zalo_bot(NOW + 60)
        self.assertEqual((view["state"], view["kenh"], view["kenh_minutes"], view["counts"]), ("ok", "online", 61, {"fixed": 3}))
        self.assertEqual(v7_machine.zalo_bot(NOW + 16 * 60)["state"], "silent")
        self.write(at=NOW + 3600)
        self.assertEqual(v7_machine.zalo_bot(NOW)["state"], "silent")       # giờ ở tương lai: không tin
        self.file.write_text("{hỏng", encoding="utf-8")
        self.assertEqual(v7_machine.zalo_bot(NOW)["state"], "silent")

    def test_machine_reader_lets_no_free_text_through(self):
        self.write(kenh={"state": "đang vui", "code": "Lỗi có chữ tự do"}, error="tên khách", counts={"fixed": 1, "Tên Khách": 2, "x": -1, "y": True})
        view = v7_machine.zalo_bot(NOW)
        self.assertEqual((view["kenh"], view["kenh_code"], view["error"], view["counts"]), ("unknown", "error", "error", {"fixed": 1}))

    def test_watchdog_reports_silence_and_a_stuck_channel_in_working_hours(self):
        ten = dt.datetime.fromtimestamp(NOW, VN)
        self.assertEqual(dog.check_zalo_bot(ten), [])                       # chưa cài bot
        self.write(at=NOW - 20 * 60)
        self.assertIn("Bot Zalo im lặng từ 09:40 ngày 22/11", dog.check_zalo_bot(ten)[0])
        self.assertEqual(dog.check_zalo_bot(dt.datetime(2026, 11, 22, 21, 0, tzinfo=VN)), [])
        self.write(kenh={"state": "login_required", "since": state.now_iso(NOW - 20 * 60)})
        self.assertEqual(dog.check_zalo_bot(ten), ["Bot Zalo: nick phụ cần quét QR đăng nhập lại, 20 phút."])
        self.write(kenh={"state": "login_required", "since": state.now_iso(NOW - 5 * 60)})
        self.assertEqual(dog.check_zalo_bot(ten), [])                       # chưa quá 15 phút
        self.write(enabled=False, kenh={"state": "offline", "since": state.now_iso(NOW - 60 * 60)})
        self.assertEqual(dog.check_zalo_bot(ten), [])                       # cờ trả lời tắt: không canh kênh
        self.write(error="log_write_failed")
        self.assertEqual(dog.check_zalo_bot(ten), ["Bot Zalo: bộ não báo lỗi log_write_failed."])

    def test_daily_tool_check_reaches_the_watchdog_with_codes_only(self):
        ten = dt.datetime.fromtimestamp(NOW, VN)
        morning = dt.datetime(2026, 11, 22, 6, 30, tzinfo=VN).timestamp()
        self.write(tool_check={"at": state.now_iso(morning), "failed": ["no_khach:api_not_found", "Tên Khách:x", "a:b:c", 5]})
        view = v7_machine.zalo_bot(NOW)
        self.assertEqual(view["tool_check"], {"at": "2026-11-22T06:30:00+07:00", "hours": 3, "failed": ["no_khach:api_not_found"]})
        self.assertEqual(dog.check_zalo_bot(ten), ["Bot Zalo: lượt tự kiểm lúc 06:30 có 1 công cụ đọc API lỗi (no_khach)."])
        self.write(tool_check={"at": state.now_iso(morning), "failed": []})
        self.assertEqual(dog.check_zalo_bot(ten), [])
        self.write(tool_check={"at": state.now_iso(morning - 2 * 86400), "failed": ["no_khach:api_not_found"]})
        self.assertEqual(dog.check_zalo_bot(ten), [])                       # lượt kiểm quá 26 giờ: không báo theo lượt cũ
        self.write()
        self.assertIsNone(v7_machine.zalo_bot(NOW)["tool_check"])

    def test_watchdog_reports_budget_not_sure_and_errors_even_after_hours(self):
        """F8: hết hạn mức báo ngay; "chưa chắc" từ 5 và lỗi model từ 3 trong ngày thì báo, kể cả ngoài giờ làm việc."""
        ten = dt.datetime.fromtimestamp(NOW, VN)
        self.write(counts={"answered": 9, "not_sure": 4, "error": 2})
        self.assertEqual(dog.check_zalo_bot(ten), [])
        self.write(counts={"over_budget": 2, "not_sure": 5, "error": 3})
        self.assertEqual(dog.check_zalo_bot(ten), [
            "Bot Zalo: đã hết hạn mức chi phí hôm nay (2 câu bị từ chối vì hạn mức).",
            "Bot Zalo: hôm nay 5 câu trả lời \"chưa chắc\" (bộ kiểm số chặn), ngưỡng 5.",
            "Bot Zalo: hôm nay 3 lần gọi model lỗi, ngưỡng 3."])
        night = NOW + 11 * 3600
        self.write(at=night, counts={"over_budget": 1})
        self.assertEqual(dog.check_zalo_bot(dt.datetime.fromtimestamp(night, VN)),
                         ["Bot Zalo: đã hết hạn mức chi phí hôm nay (1 câu bị từ chối vì hạn mức)."])

    def test_a_broken_bot_check_does_not_hide_other_checks(self):
        for name in ("check_api", "check_reconcile", "check_snapshots", "check_sources", "check_inbox", "check_units", "check_disks"):
            item = patch.object(dog, name, return_value=[])
            item.start()
            self.addCleanup(item.stop)

        def broken(_now):
            raise RuntimeError("x")
        found = dog.collect(dt.datetime.fromtimestamp(NOW, VN), healthz="x", reconcile=self.dir / "r.json", snapshots=self.dir,
                            safety=lambda _n: [], offsite=lambda _n: [], zalo=lambda _n: ["máy Zalo lỗi"], zalo_bot=broken)
        self.assertEqual(found, ["máy Zalo lỗi", "Không kiểm được phần bot Zalo (RuntimeError)."])


if __name__ == "__main__":
    unittest.main()
