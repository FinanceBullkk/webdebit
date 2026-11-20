"""WECHAT-01: nguồn WeChat của zalo-agent, test với tiến trình con giả và dữ liệu bịa (không WeChat thật, không ssh)."""

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import zalo_web_bundle as wb  # noqa: E402
from test_zalo_agent import BUNDLE_REMOTE, Remote  # noqa: E402
from test_zalo_web_bundle import GROUP, NOW, FakeCdn, no_jxl, write_source  # noqa: E402
from zalo_agent import __main__ as agent_main  # noqa: E402
from zalo_agent import cursor as cursors  # noqa: E402
from zalo_agent import push as pusher  # noqa: E402
from zalo_agent import status as status_file  # noqa: E402
from zalo_agent import wechat_export as export  # noqa: E402
from zalo_agent.processors import wechat as wc  # noqa: E402
from zalo_agent.processors.bundle import CLEAN_KEYS, BundleProcessor  # noqa: E402
from zalo_agent.source import LiveSync  # noqa: E402

USER, NAME = "wxid_nhom_thu@chatroom", "Nhóm thu chi thử"
OTHER_USER = "wxid_nhom_khac@chatroom"
JPEG = b"\xff\xd8\xff\xe0wechat-jpeg"


def msg(local_id, seq, text="tin bịa", kind="文本", sender="wxid_a", name="Khách A", own=False, user=USER, **extra):
    return {"kind": "message", "username": user, "local_id": local_id, "sort_seq": seq, "create_time": 1_793_000_000 + seq // 1000,
            "type": kind, "is_self": own, "sender": "" if own else sender, "sender_name": "" if own else name, "content": text, "image": None, **extra}


class FakeDb:
    """Nguồn của tiến trình con giả: lọc đúng như `wechat_export.read_group` bằng `is_new`."""

    def __init__(self):
        self.feed = []
        self.requests = []
        self.fail = None      # (mã trả về) hoặc ngoại lệ sẽ ném
        self.gate = None      # threading.Event: chặn cho tới khi test cho chạy
        self.window = []      # tin đọc lại trong cửa sổ (đã đổi tại chỗ), phát kèm ở mỗi lượt

    def __call__(self, python, pilot, command, request, timeout=None):
        self.requests.append((command, request))
        if self.gate is not None:
            self.gate.wait(10)
        if isinstance(self.fail, Exception):
            raise self.fail
        if self.fail:
            return self.fail, ""
        groups = request.get("groups") or {}
        items = [item for item in self.feed if item["username"] in groups and export.is_new(item, groups[item["username"]])]
        return 0, "".join(json.dumps(item) + "\n" for item in [*items, *self.window, {"kind": "end", "messages": len(items)}])


class WeChatBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src, self.root = base / "live-sync", base / "agent"
        self.src.mkdir()
        (base / "remote").mkdir()
        write_source(self.src)
        (self.src / "baseline-manifest.json").write_text(json.dumps({"messages_sha256": "a" * 64}), encoding="utf-8")
        wb.Source(self.src).save_selection([GROUP])
        self.selection = wc.Selection(base / "wechat-groups.json")
        self.selection.save({USER: NAME})
        self.store = wc.Store(self.root / "wechat", self.selection)
        self.remote, self.now, self.db = Remote(base / "remote"), NOW, FakeDb()
        self.state = self.root / "state"
        self.bundle = self.make_bundle(self.remote)
        self.processor = self.make_processor()

    def make_bundle(self, run):
        return BundleProcessor(LiveSync(self.src), self.state, self.root / "bundle", "fake:" + BUNDLE_REMOTE, run=run, fetch=FakeCdn(),
                               transcode=no_jxl, max_age_days=None, clock=lambda: self.now, overlay=self.store)

    def make_processor(self, **kwargs):
        args = {"python": "py", "pilot": "pilot", "run": self.db, "clock": lambda: self.now, "background": False, **kwargs}
        return wc.WeChatProcessor(self.store, self.state, **args)

    def poll(self):
        self.now += 11   # qua nhịp đọc (INTERVAL = 10 giây)
        return self.processor.step()

    def remote_files(self):
        root = self.remote.dirs[BUNDLE_REMOTE]
        report = json.loads((root / wb.REPORT).read_text(encoding="utf-8"))
        data = root / report["data_dir"]
        lines = lambda path: [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.is_file() else []  # noqa: E731
        return {"report": report, "conversations": json.loads((data / "conversations.json").read_text(encoding="utf-8")),
                "users": json.loads((data / "users.json").read_text(encoding="utf-8")),
                "media": json.loads((data / "media.json").read_text(encoding="utf-8")),
                "messages": lines(data / "messages.jsonl"), "delta": lines(data / "messages-delta.jsonl"), "dir": data}

    def remote_text(self):
        files = self.remote_files()
        return json.dumps([*files["messages"], *files["delta"]], ensure_ascii=False)

    def wechat_rows(self, rows):
        return [row for row in rows if row["conversation_id"] == wc.conversation_id(USER)]


class ConvertTest(unittest.TestCase):
    def test_row_has_exactly_the_bundle_shape_and_ids_match_the_hao_regexes(self):
        row, user = wc.convert(msg(7, 1000, "  Thu 5 triệu ABC  ", sender="wxid_a", name="Khách A"))
        self.assertEqual(set(row), {*CLEAN_KEYS, "body"})
        self.assertRegex(row["conversation_id"], r"[0-9a-f]{64}")
        self.assertRegex(row["message_id"], r"[0-9A-Za-z_-]{1,128}")
        self.assertEqual(row["conversation_id"], hashlib.sha256(f"wechat:{USER}".encode()).hexdigest())
        self.assertEqual((row["message_type"], row["status"], row["body"]), (1, 4, "Thu 5 triệu ABC"))
        self.assertEqual((row["timestamp"], row["server_time"]), ("1793000001000", "1793000001000"))
        self.assertEqual(user, (row["sender_id"], "Khách A"))
        self.assertNotIn("wxid_a", json.dumps(row))   # mã người dùng WeChat không rời máy

    def test_message_ids_are_stable_and_distinct_across_db_shards(self):
        first, second = wc.convert(msg(7, 1000))[0], wc.convert(msg(7, 2000))[0]   # cùng local_id ở hai phân mảnh
        self.assertEqual(first["message_id"], wc.convert(msg(7, 1000))[0]["message_id"])
        self.assertNotEqual(first["message_id"], second["message_id"])

    def test_types_map_to_the_labels_hao_already_shows(self):
        expected = {"文本": 1, "图片": 2, "文件/链接/卡片": 19, "系统消息": -4, "语音": 3, "视频": 18, "位置": 17, "动画表情": 4, "音视频通话": 6}
        for kind, number in expected.items():
            self.assertEqual(wc.convert(msg(1, 1000, "nội dung", kind))[0]["message_type"], number, kind)
        self.assertEqual(wc.convert(msg(1, 1000, "x", "图片"))[0]["body"], "Ảnh WeChat (chưa đọc được)")
        self.assertEqual(wc.convert(msg(1, 1000, "x", "图片"), image="a" * 64)[0]["body"], "Ảnh WeChat")
        self.assertEqual(wc.convert(msg(1, 1000, "[语音]", "语音"))[0]["body"], "[Ghi âm WeChat]")   # chữ Hán giữ chỗ không đi lên web
        unknown = wc.convert(msg(1, 1000, "", 99999))[0]
        self.assertEqual((unknown["message_type"], unknown["body"]), (19, wc.UNKNOWN_LABEL))
        self.assertEqual(wc.convert(msg(1, 1000, "", "文本"))[0]["body"], wc.UNKNOWN_LABEL)

    def test_own_messages_and_system_messages(self):
        row, user = wc.convert(msg(1, 1000, "tôi gửi", own=True))
        self.assertEqual((row["status"], row["sender_id"], user[1]), (2, wc.SELF_ID, wc.SELF_NAME))
        row, user = wc.convert(msg(2, 2000, "hệ thống", "系统消息", sender=""))
        self.assertEqual((row["sender_id"], user, row["message_type"]), (None, None, -4))

    def test_malformed_lines_are_dropped(self):
        for bad in ({}, {**msg(1, 1000), "local_id": "1"}, {**msg(1, 1000), "sort_seq": None}, {**msg(1, 1000), "username": 5},
                    {**msg(1, 1000), "create_time": True}):
            self.assertIsNone(wc.convert(bad), bad)


class PollTest(WeChatBase):
    def test_new_messages_land_in_the_store_and_the_cursor_moves_only_forward(self):
        self.db.feed = [msg(1, 1000, "một"), msg(2, 2000, "hai"), msg(3, 3000, "ba")]
        result = self.poll()
        self.assertEqual((result["action"], result["error"], result["messages"], result["revision"]), ("poll", None, 3, None))
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 3)
        saved = json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["groups"][USER], {"sort_seq": 3000, "tail": [3]})
        self.assertEqual(self.db.requests[0][1]["groups"], {USER: {}})   # lần đầu: chưa có con trỏ
        self.assertEqual(self.poll()["action"], "idle")
        self.assertEqual(self.db.requests[1][1]["groups"], {USER: {"sort_seq": 3000, "tail": [3]}})
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 3)   # không đọc lại
        self.db.feed.append(msg(4, 3000, "đến muộn, cùng sort_seq"))
        self.poll()
        self.assertEqual(json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))["groups"][USER]["tail"], [3, 4])
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 4)

    def test_cursor_survives_agent_restart(self):
        self.db.feed = [msg(1, 1000)]
        self.poll()
        again = self.make_processor()
        self.now += 11
        again.step()
        self.assertEqual(self.db.requests[-1][1]["groups"], {USER: {"sort_seq": 1000, "tail": [1]}})
        self.assertEqual(again.total, 1)

    def test_unselected_groups_are_never_requested_or_stored(self):
        self.db.feed = [msg(1, 1000), msg(1, 1000, "bí mật", user=OTHER_USER)]
        self.poll()
        self.assertEqual(list(self.db.requests[0][1]["groups"]), [USER])
        self.assertNotIn("bí mật", self.store.log.read_text(encoding="utf-8"))
        # tiến trình con hư vẫn trả tin nhóm lạ: bộ xử lý bỏ
        liar = lambda *args, **kw: (0, json.dumps(msg(9, 9000, "lọt", user=OTHER_USER)) + "\n" + json.dumps({"kind": "end"}) + "\n")  # noqa: E731
        self.processor.run = liar
        self.poll()
        self.assertNotIn("lọt", self.store.log.read_text(encoding="utf-8"))

    def test_no_selected_group_means_no_child_process(self):
        self.selection.save({})
        self.assertEqual(self.poll()["action"], "idle")
        self.assertEqual(self.db.requests, [])

    def test_child_errors_back_off_on_their_own_and_recover(self):
        for failure, code in ((1, "child_failed"), (subprocess.TimeoutExpired("x", 1), "child_timeout"), (FileNotFoundError(), "child_missing")):
            self.db.fail = failure
            self.now += 1000   # qua mọi thời gian lùi của lần lỗi trước
            self.assertEqual(self.processor.step()["error"], code)
        self.assertEqual(self.processor.failures, 3)
        calls = len(self.db.requests)
        self.now += 1   # trong thời gian lùi (80 giây sau lần lỗi thứ 3): không gọi tiến trình con
        self.processor.step()
        self.assertEqual(len(self.db.requests), calls)
        self.db.fail, self.db.feed = None, [msg(1, 1000)]
        self.now += 100
        self.assertEqual(self.processor.step()["error"], None)
        self.assertEqual((self.processor.failures, self.processor.total), (0, 1))
        self.db.fail = 0
        self.processor.run = lambda *args, **kw: (0, "không phải JSON\n")   # thiếu dòng `end`
        self.assertEqual(self.poll()["error"], "child_output")

    def test_status_carries_the_count_and_only_short_codes(self):
        self.db.feed = [msg(1, 1000, "Nội dung riêng tư không được lọt vào status")]
        self.poll()
        status = status_file.compose(None, self.now, "abc", 1, LiveSync(self.src), {"wechat": {**self.processor.last, "error": "lỗi tự do!"}},
                                     None, None, ("attached", "2026-11-20T08:00:00+07:00"))
        self.assertEqual((status["processors"]["wechat"]["messages"], status["processors"]["wechat"]["error"]), (1, "unexpected"))
        self.assertNotIn("riêng tư", json.dumps(status))

    def test_slow_child_never_blocks_the_loop(self):
        self.db.gate = threading.Event()
        self.db.feed = [msg(1, 1000)]
        slow = self.make_processor(background=True)
        started = time.time()
        self.now += 11
        slow.step()
        self.assertLess(time.time() - started, 1.0)   # step trả về ngay dù tiến trình con đang treo
        self.assertEqual(self.bundle.step()["action"], "rebuild")   # bundle vẫn chạy cùng lúc
        self.db.gate.set()
        slow.thread.join(10)
        self.assertEqual(slow.step()["action"], "poll")
        self.assertEqual(slow.total, 1)


class BundleOverlayTest(WeChatBase):
    def test_rebuild_carries_the_wechat_group_users_and_messages(self):
        self.db.feed = [msg(1, 1000, "Thu 5 triệu", name="Khách A"), msg(2, 2000, "ảnh", "图片", name="Khách B", sender="wxid_b")]
        self.poll()
        result = self.bundle.step()
        self.assertEqual((result["action"], result["reason"], result["error"]), ("rebuild", "first_run", None))
        files = self.remote_files()
        cid = wc.conversation_id(USER)
        conversation = next(c for c in files["conversations"] if c["conversation_id"] == cid)
        self.assertEqual((conversation["display_name"], conversation["is_group"], conversation["message_count"]), (f"WeChat · {NAME}", True, 2))
        rows = self.wechat_rows(files["messages"])
        self.assertEqual([row["body"] for row in rows], ["Thu 5 triệu", "Ảnh WeChat (chưa đọc được)"])
        self.assertEqual({files["users"]["users"][row["sender_id"]] for row in rows}, {"Khách A", "Khách B"})
        self.assertIsNotNone(files["users"]["self_user"])   # chủ tài khoản Zalo giữ nguyên
        report = files["report"]
        self.assertEqual(report["message_count"], 8 + 2)
        digest = hashlib.sha256()
        for name in ("conversations.json", "users.json", "messages.jsonl", "media.json"):
            digest.update((files["dir"] / name).read_bytes())
        self.assertEqual(report["bundle_sha256"], digest.hexdigest())
        self.assertEqual(cursors.load(self.state, "bundle")["wechat_bytes"], self.store.size())
        self.assertEqual(self.bundle.step()["action"], "idle")
        self.assertFalse(self.bundle.wants_work())

    def test_new_wechat_messages_become_delta_with_no_zalo_change(self):
        self.db.feed = [msg(1, 1000)]
        self.poll()
        self.bundle.step()
        before = self.remote_files()
        self.db.feed.append(msg(2, 2000, "Chi 2 triệu tiền xe", name="Khách C", sender="wxid_c"))
        self.poll()
        self.assertTrue(self.bundle.wants_work())   # live-sync không đổi revision, kho WeChat dài ra
        result = self.bundle.step()
        self.assertEqual((result["action"], result["reason"]), ("delta", "delta"))
        files = self.remote_files()
        self.assertEqual(len(files["delta"]), 1)
        line = files["delta"][0]
        self.assertEqual(set(line), {*CLEAN_KEYS, "body"})
        self.assertEqual((line["body"], line["message_type"], line["conversation_id"]), ("Chi 2 triệu tiền xe", 1, wc.conversation_id(USER)))
        self.assertEqual(files["users"]["users"][line["sender_id"]], "Khách C")
        report = files["report"]
        self.assertEqual((report["delta_lines"], report["delta_bytes"] > 0, report["data_dir"], report["bundle_sha256"]),
                         (1, True, before["report"]["data_dir"], before["report"]["bundle_sha256"]))
        self.assertEqual(cursors.load(self.state, "bundle")["wechat_bytes"], self.store.size())
        self.assertEqual(self.bundle.step()["action"], "idle")

    def test_cursor_moves_only_after_a_successful_push_and_resend_has_no_duplicate(self):
        self.db.feed = [msg(1, 1000)]
        self.poll()
        self.bundle.step()
        self.db.feed.append(msg(2, 2000, "tin chờ đẩy"))
        self.poll()
        done = cursors.load(self.state, "bundle")["wechat_bytes"]

        def broken(host, command, stdin=None):
            raise pusher.PushError("mạng đứt")
        self.assertEqual(self.make_bundle(broken).step()["error"], "push_failed")
        saved = cursors.load(self.state, "bundle")
        self.assertEqual((saved["wechat_bytes"], saved["pending"]["wechat_bytes"]), (done, self.store.size()))
        self.assertEqual(self.bundle.step()["action"], "delta")   # lượt sau đẩy đúng phần đã chuẩn bị
        self.assertEqual([line["body"] for line in self.remote_files()["delta"]], ["tin chờ đẩy"])
        self.assertEqual(self.bundle.step()["action"], "idle")

    def test_resent_messages_are_deduplicated_and_latest_wins(self):
        self.store.append([{"message_id": "d1", "conversation_id": wc.conversation_id(USER), "body": "cũ"},
                           {"message_id": "d1", "conversation_id": wc.conversation_id(USER), "body": "mới"}], {}, {})
        rows, offset = self.store.rows_after(0)
        self.assertEqual([row["body"] for row in rows], ["mới"])
        self.assertEqual(offset, self.store.size())
        self.assertEqual(self.store.rows_after(offset), ([], offset))

    def test_changing_the_wechat_selection_rebuilds_and_removed_groups_leave_the_bundle(self):
        self.db.feed = [msg(1, 1000, "tin nhóm một"), msg(1, 1000, "tin nhóm hai", user=OTHER_USER)]
        self.poll()
        self.bundle.step()
        self.selection.save({USER: NAME, OTHER_USER: "Nhóm hai"})
        self.assertTrue(self.bundle.wants_work())
        self.assertEqual(self.bundle.step()["reason"], "selection_changed")
        self.poll()   # nhóm hai được đọc từ lúc này
        self.bundle.step()
        self.assertEqual(self.bundle.step()["action"], "idle")
        text = self.remote_text()
        self.assertIn("tin nhóm hai", text)
        self.selection.save({OTHER_USER: "Nhóm hai"})   # bỏ nhóm một
        self.assertEqual(self.bundle.step()["reason"], "selection_changed")
        text = self.remote_text()
        self.assertNotIn("tin nhóm một", text)
        self.assertIn("tin nhóm hai", text)
        self.assertIn("tin nhóm một", self.store.log.read_text(encoding="utf-8"))   # kho cục bộ vẫn giữ, chỉ gói không mang

    def test_deselected_rows_do_not_leak_into_a_delta(self):
        self.db.feed = [msg(1, 1000)]
        self.poll()
        self.bundle.step()
        self.store.append([{"message_id": "x1", "conversation_id": wc.conversation_id(OTHER_USER), "body": "nhóm chưa chọn"}], {}, {})
        self.assertEqual(self.bundle.step()["action"], "idle")   # con trỏ tiến nhưng không đẩy gì
        self.assertEqual(self.remote_files()["delta"], [])
        self.assertEqual(cursors.load(self.state, "bundle")["wechat_bytes"], self.store.size())

    def test_decoded_images_reach_media_in_rebuild_and_delta(self):
        self.processor = self.make_processor(images=True)
        (self.store.dir / "incoming").mkdir(exist_ok=True)
        (self.store.dir / "incoming" / "a.jpg").write_bytes(JPEG)
        self.db.feed = [msg(1, 1000, "", "图片", image="a.jpg"), msg(2, 2000, "", "图片")]
        self.poll()
        digest = hashlib.sha256(JPEG).hexdigest()
        self.assertFalse((self.store.dir / "incoming" / "a.jpg").exists())   # tệp tạm được dọn sau khi nhập kho
        self.bundle.step()
        files = self.remote_files()
        rows = self.wechat_rows(files["messages"])
        self.assertEqual([(row["body"], row.get("media")) for row in rows], [("Ảnh WeChat", [digest]), ("Ảnh WeChat (chưa đọc được)", None)])
        self.assertEqual(files["media"][digest]["mime"], "image/jpeg")
        self.assertEqual((self.remote.dirs[BUNDLE_REMOTE] / "media" / f"{digest}.jpg").read_bytes(), JPEG)
        (self.store.dir / "incoming" / "b.jpg").write_bytes(JPEG + b"-hai")
        self.db.feed.append(msg(3, 3000, "", "图片", image="b.jpg"))
        self.poll()
        self.assertEqual(self.bundle.step()["action"], "delta")
        digest_two = hashlib.sha256(JPEG + b"-hai").hexdigest()
        self.assertIn(digest_two, self.remote_files()["media"])
        self.assertTrue((self.remote.dirs[BUNDLE_REMOTE] / "media" / f"{digest_two}.jpg").is_file())


class AgentWiringTest(WeChatBase):
    def test_wechat_is_off_unless_asked_and_gets_its_own_processor_when_on(self):
        live = LiveSync(self.src)
        off = agent_main.Agent(live, self.root, "fake:" + BUNDLE_REMOTE, "fake:/srv/v7/zalo-agent", run=self.remote)
        self.assertEqual([p.name for p in off.processors], ["bundle"])
        on = agent_main.Agent(live, self.root, "fake:" + BUNDLE_REMOTE, "fake:/srv/v7/zalo-agent", run=self.remote,
                              wechat={"python": "py", "pilot": "p", "groups": str(self.selection.path), "run": self.db})
        self.assertEqual([p.name for p in on.processors], ["bundle", "wechat"])
        self.assertIsNotNone(on.processors[0].overlay)
        self.assertIsNone(off.processors[0].overlay)
        self.assertFalse(off.processors[0].wechat_pending({}))

    def test_flag_defaults_to_off_on_the_command_line(self):
        source = (ROOT / "tools" / "zalo_agent" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn('"--wechat", action="store_true", default=os.environ.get("ZALO_AGENT_WECHAT") == "1"', source)

    def test_step_result_is_reported_once_so_the_loop_does_not_log_every_second(self):
        self.db.feed = [msg(1, 1000)]
        self.assertEqual(self.poll()["action"], "poll")
        self.assertEqual(self.processor.step()["action"], "idle")


class ExportTest(unittest.TestCase):
    class Db:
        def get_groups(self):
            return [{"username": u, "name": n, "members": [1, 2]} for u, n in self.groups]

        def __init__(self, groups, total=7):
            self.groups, self.touched, self.total = groups, [], total

        def rows(self):
            return [{"local_id": i, "type": "文本", "sender_id": 5, "sender_username": "wxid_a", "create_time": 1_793_000_000 + i,
                     "content": f"tin {i}", "sort_seq": i * 1000} for i in range(1, self.total + 1)]

        def get_messages(self, username, limit=20, offset=0):
            self.touched.append(username)   # `get_messages` trả mới trước cũ như upstream
            return list(reversed(self.rows()))[offset:offset + limit]

        def get_new_messages(self, username, since_seq=0, limit=200):
            self.touched.append(username)   # sort_seq > since_seq, tăng dần, `limit` tin nhỏ nhất như upstream
            return [row for row in self.rows() if row["sort_seq"] > since_seq][:limit]

        def nickname_map(self):
            return {"wxid_a": "Khách A"}

    def test_read_group_pages_back_only_as_far_as_the_cursor_with_tail_overlap(self):
        db = self.Db([(USER, NAME)])
        with unittest.mock.patch.object(export, "PAGE", 3):
            self.assertEqual([r["local_id"] for r in export.read_group(db, USER, {"sort_seq": 5000, "tail": [5]}, 100)], [6, 7])
            self.assertEqual([r["local_id"] for r in export.read_group(db, USER, {"sort_seq": 5000, "tail": []}, 100)], [5, 6, 7])
            self.assertEqual([r["local_id"] for r in export.read_group(db, USER, None, 4)], [4, 5, 6, 7])   # lần đầu: tối đa first_limit tin

    def test_a_backlog_of_three_thousand_is_read_in_full_across_pages_and_the_cursor_follows(self):
        db = self.Db([(USER, NAME)], total=3000)
        got, cursor = [], {"sort_seq": 1000, "tail": [1]}
        for _ in range(5):   # mỗi yêu cầu tối đa REQUEST_BUDGET tin mới; con trỏ tiến theo tin cuối nên cộng lại không mất tin nào
            rows = export.read_group(db, USER, cursor, 100)
            self.assertLessEqual(len(rows), export.REQUEST_BUDGET)
            if not rows:
                break
            got += rows
            cursor = {"sort_seq": rows[-1]["sort_seq"], "tail": [rows[-1]["local_id"]]}
        self.assertEqual([r["local_id"] for r in got], list(range(2, 3001)))   # không mất tin nào dù tồn > 2000
        again = export.read_group(db, USER, {"sort_seq": 3_000_000, "tail": [3000]}, 100)
        self.assertEqual(again, [])
        with unittest.mock.patch.object(export, "PAGE", 100):   # trang đầy ngay ranh giới: không lặp vô hạn, không trùng
            rows = export.read_group(db, USER, {"sort_seq": 1000, "tail": [1]}, 100, limit=10_000)
        self.assertEqual([r["local_id"] for r in rows], list(range(2, 3001)))

    def test_clean_content_keeps_only_readable_text_never_urls_keys_or_ids(self):
        card = ("wxid_abc123:\n<msg><appmsg appid=\"\" sdkver=\"0\"><title>Báo giá tháng 11.pdf</title><des>Bản đã duyệt</des>"
                "<url>https://cdn.example.test/file?key=SECRET</url><appattach><cdnattachurl>3057020100</cdnattachurl>"
                "<aeskey>0123456789abcdef0123456789abcdef</aeskey><md5>fedcba9876543210fedcba9876543210</md5></appattach>"
                "<refermsg><title>tin cũ được trích</title><content>wxid_xyz</content></refermsg></appmsg></msg>")
        text = export.clean_content("文件/链接/卡片", card, "wxid_abc123")
        self.assertEqual(text, "Báo giá tháng 11.pdf · Bản đã duyệt")
        for leak in ("http", "SECRET", "aeskey", "0123456789abcdef", "fedcba98", "wxid", "<", "cdn"):
            self.assertNotIn(leak, text)
        cdata = "<msg><appmsg><title><![CDATA[Tiêu đề &amp; chữ]]></title></appmsg></msg>"
        self.assertEqual(export.clean_content("文件/链接/卡片", cdata), "Tiêu đề & chữ")
        revoke = "<sysmsg type=\"revokemsg\"><revokemsg><session>abc@chatroom</session><newmsgid>123</newmsgid><replacemsg><![CDATA[\"A\" 撤回了一条消息]]></replacemsg></revokemsg></sysmsg>"
        self.assertEqual(export.clean_content("系统消息", revoke), "\"A\" 撤回了一条消息")
        self.assertEqual(export.clean_content("系统消息", "<sysmsg type=\"x\"><a>mã</a></sysmsg>"), "")   # XML không có chữ: rỗng, không lộ mã
        self.assertEqual(export.clean_content("系统消息", "Bạn đã thêm X vào nhóm https://x.example.test/y"), "Bạn đã thêm X vào nhóm")
        self.assertEqual(export.clean_content("文本", "wxid_abc123:\nThu 5 triệu", "wxid_abc123"), "Thu 5 triệu")
        self.assertEqual(export.clean_content("文本", "Ghi chú:\nThu 5 triệu", "wxid_abc123"), "Ghi chú:\nThu 5 triệu")   # không phải mã người gửi
        self.assertEqual(export.clean_content("语音", "<voicemsg voiceurl=\"x\"/>"), "")
        item = export.record({}, USER, {"local_id": 1, "sort_seq": 1000, "create_time": 1, "type": "文件/链接/卡片", "sender_id": 5,
                                        "sender_username": "wxid_abc123", "content": card}, None, None)
        self.assertNotIn("aeskey", json.dumps(item))   # XML không ra khỏi tiến trình con
        row = wc.convert({**item, "content": card})[0]   # phòng con cũ: bộ xử lý cũng không để XML lên gói
        self.assertEqual(row["body"], "Báo giá tháng 11.pdf · Bản đã duyệt")

    def test_read_only_touches_requested_groups_and_never_the_image_tools_unless_asked(self):
        db = self.Db([(USER, NAME), (OTHER_USER, "Nhóm khác")])
        lines = []
        with unittest.mock.patch.object(export, "emit", lines.append), unittest.mock.patch.object(export, "image_tools") as tools:
            export.cmd_read(db, {"groups": {USER: {}, "wxid_khong_co@chatroom": {}}, "first_limit": 50})
        self.assertEqual(set(db.touched), {USER})
        tools.assert_not_called()
        self.assertEqual(lines[-1], {"kind": "end", "messages": 7, "images": 0, "missing_groups": 1, "window": 0, "window_same": 0, "image_keys": False})
        self.assertEqual(lines[0]["sender_name"], "Khách A")
        self.assertNotIn("wxid", json.dumps([line for line in lines if line["kind"] == "end"]))

    def test_real_subprocess_with_a_fake_pilot_reads_jsonl_and_hides_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            pilot = Path(tmp) / "pilot"
            pilot.mkdir()
            (pilot / "db_adapter.py").write_text(
                "class Db:\n"
                "    def get_groups(self):\n"
                f"        return [{{'username': {USER!r}, 'name': 'Nhóm 群', 'members': [1]}}]\n"
                "    def get_messages(self, username, limit=20, offset=0):\n"
                "        rows = [{'local_id': 1, 'type': '文本', 'sender_id': 2, 'sender_username': '', 'create_time': 1793000001, "
                "'content': '收到 5 triệu', 'sort_seq': 1000}]\n"
                "        return rows[offset:offset + limit]\n"
                "    def nickname_map(self):\n"
                "        return {}\n"
                "def open_database():\n"
                "    return Db()\n", encoding="utf-8")
            code, output = wc.run_child(sys.executable, str(pilot), "read", {"groups": {USER: {}}}, 60)
            self.assertEqual(code, 0)
            items = wc.parse(output)
            self.assertEqual([i["kind"] for i in items], ["message", "end"])
            self.assertEqual((items[0]["content"], items[0]["is_self"]), ("收到 5 triệu", True))
            self.assertTrue(output.isascii())   # ra bằng \\uXXXX: không phụ thuộc bảng mã của ống dẫn Windows
            code, output = wc.run_child(sys.executable, str(pilot), "groups", {}, 60)
            self.assertEqual([(g["name"], g["members"]) for g in wc.parse(output)], [("Nhóm 群", 1)])
            (pilot / "db_adapter.py").write_text("def open_database():\n    raise RuntimeError('C:/duong/dan/bi-mat khoa=123')\n", encoding="utf-8")
            code, output = wc.run_child(sys.executable, str(pilot), "read", {"groups": {USER: {}}}, 60)
            self.assertEqual((code, wc.parse(output)), (2, [{"kind": "error", "code": "RuntimeError"}]))
            self.assertNotIn("bi-mat", output)


LISTED = [{"kind": "group", "username": USER, "name": "Nhóm Thu Chi", "members": 13},
          {"kind": "group", "username": OTHER_USER, "name": "Nhóm Thu Mua", "members": 4}]


class SelectionCommandTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.selection = wc.Selection(Path(self.tmp.name) / "wechat-groups.json")
        quiet = contextlib.redirect_stdout(io.StringIO())   # các lệnh in kết quả ra màn hình
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        self.run = lambda *args, **kw: (0, "".join(json.dumps(g) + "\n" for g in LISTED))

    def test_add_by_name_ignoring_case_and_accents_then_remove(self):
        self.assertEqual(wc.cmd_change(self.selection, ["nhom thu chi"], True, "py", "p", self.run), 0)
        document = json.loads(self.selection.path.read_text(encoding="utf-8"))
        self.assertEqual(document, {"schema": 1, "groups": [{"name": "Nhóm Thu Chi", "username": USER}]})
        self.assertEqual(self.selection.groups(), {USER: "Nhóm Thu Chi"})
        self.assertEqual(wc.cmd_change(self.selection, ["Thu Chi"], False, "py", "p", self.run), 0)
        self.assertEqual(self.selection.groups(), {})

    def test_ambiguous_or_missing_name_changes_nothing(self):
        self.assertEqual(wc.cmd_change(self.selection, ["nhóm thu"], True, "py", "p", self.run), 1)   # khớp cả hai nhóm
        self.assertEqual(wc.cmd_change(self.selection, ["không có"], True, "py", "p", self.run), 1)
        self.assertEqual(self.selection.groups(), {})

    def test_failing_reader_is_reported_not_raised_as_a_traceback(self):
        failing = lambda *args, **kw: (2, "")  # noqa: E731
        with self.assertRaises(RuntimeError):
            wc.list_groups("py", "p", failing)

    def test_only_chatroom_usernames_are_accepted_from_the_selection_file(self):
        self.selection.path.write_text(json.dumps({"groups": [{"username": "wxid_ca_nhan", "name": "x"}, {"username": USER, "name": "y"}]}),
                                       encoding="utf-8")
        self.assertEqual(self.selection.groups(), {USER: "y"})   # chat riêng không bao giờ được đọc


class RevokeTest(WeChatBase):
    def test_a_message_turned_into_a_revoke_notice_becomes_one_deleted_row_never_flip_flopping(self):
        self.db.feed = [msg(1, 1000, "Thu 5 triệu", sender="wxid_a", name="Khách A")]
        self.poll()
        original = json.loads(self.store.log.read_text(encoding="utf-8").splitlines()[0])
        revoked = msg(1, 1000, "A 撤回了一条消息", "系统消息", sender="", window=True, revoked=True)
        self.db.window = [msg(1, 1000, "Thu 5 triệu", sender="wxid_a", name="Khách A", window=True)]
        self.poll()
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 1)   # cửa sổ không đổi: không phát lại
        self.db.window = [revoked]
        self.poll()
        lines = [json.loads(line) for line in self.store.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(lines), 2)
        deleted = lines[1]
        self.assertEqual(set(deleted), {*CLEAN_KEYS, "body", "deleted"})
        self.assertEqual((deleted["message_id"], deleted["conversation_id"], deleted["timestamp"], deleted["body"], deleted["deleted"]),
                         (original["message_id"], original["conversation_id"], original["timestamp"], None, True))
        self.assertEqual((deleted["sender_id"], deleted["message_type"], deleted["status"]),
                         (original["sender_id"], original["message_type"], original["status"]))   # như dòng xóa của bản dựng đầy đủ
        self.poll()   # cửa sổ vẫn thấy tin hệ thống: không ghi đè dòng xóa, không phát lại
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 2)
        self.assertTrue(self.store.rows_after(0)[0][0]["deleted"])   # bản cuối thắng

    def test_deleted_row_reaches_hao_in_the_delta_and_a_new_revoke_notice_row_stays_a_notice(self):
        self.db.feed = [msg(1, 1000, "Chi 2 triệu")]
        self.poll()
        self.bundle.step()
        self.db.window = [msg(1, 1000, "A 撤回了一条消息", "系统消息", sender="", window=True, revoked=True)]
        self.poll()
        self.assertEqual(self.bundle.step()["action"], "delta")
        delta = self.remote_files()["delta"]
        self.assertEqual([(line["body"], line.get("deleted")) for line in delta], [(None, True)])
        self.db.window = []
        self.db.feed.append(msg(2, 2000, "B 撤回了一条消息", "系统消息", sender="", revoked=True))   # dòng hệ thống MỚI, không phải sửa tại chỗ
        self.poll()
        rows = self.store.rows_after(cursors.load(self.state, "bundle")["wechat_bytes"])[0]
        self.assertEqual([(row["message_type"], row.get("deleted")) for row in rows], [(-4, None)])

    def test_edited_text_in_the_window_is_resent_as_the_latest_version(self):
        self.db.feed = [msg(1, 1000, "Thu 5 triệu")]
        self.poll()
        self.db.window = [msg(1, 1000, "Thu 6 triệu", window=True)]
        self.poll()
        rows, _ = self.store.rows_after(0)
        self.assertEqual([row["body"] for row in rows], ["Thu 6 triệu"])

    def test_late_arrival_older_than_the_cursor_is_picked_up_from_the_window(self):
        self.db.feed = [msg(2, 2000, "đến trước")]
        self.poll()
        self.db.window = [msg(1, 1000, "đến muộn nhưng sort_seq nhỏ hơn", window=True)]
        self.poll()
        self.assertEqual(sorted(row["body"] for row in self.store.rows_after(0)[0]), ["đến muộn nhưng sort_seq nhỏ hơn", "đến trước"])
        self.assertEqual(json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))["groups"][USER]["sort_seq"], 2000)


class OverlayDetailsTest(WeChatBase):
    def test_previous_data_dir_survives_when_only_wechat_groups_are_in_it(self):
        self.db.feed = [msg(1, 1000)]
        self.poll()
        self.bundle.step()
        self.now += 100   # mỗi lượt dựng một thư mục dữ liệu theo giờ
        self.selection.save({USER: NAME, OTHER_USER: "Nhóm hai"})
        self.bundle.step()
        self.assertEqual(len(list((self.root / "bundle").glob("data-*"))), 2)   # KEEP_DATA_DIRS: hao còn đọc dở lượt trước
        self.now += 100
        self.selection.save({OTHER_USER: "Nhóm hai"})
        self.bundle.step()
        dirs = sorted(path.name for path in (self.root / "bundle").glob("data-*"))
        self.assertEqual(len(dirs), 1)   # các lượt trước còn nhóm vừa bỏ chọn: bỏ ngay, không giữ cho hao đọc dở
        current = json.loads((self.root / "bundle" / dirs[0] / "conversations.json").read_text(encoding="utf-8"))
        self.assertNotIn(wc.conversation_id(USER), {c["conversation_id"] for c in current})

    def test_own_wechat_messages_carry_the_zalo_owner_id_in_rebuild_and_delta(self):
        self.db.feed = [msg(1, 1000, "tôi gửi trước", own=True)]
        self.poll()
        self.bundle.step()
        files = self.remote_files()
        owner = files["users"]["self_user"]
        self.assertEqual([row["sender_id"] for row in self.wechat_rows(files["messages"])], [owner])
        self.db.feed.append(msg(2, 2000, "tôi gửi sau", own=True))
        self.poll()
        self.bundle.step()
        self.assertEqual([line["sender_id"] for line in self.remote_files()["delta"]], [owner])

    def test_wechat_with_no_zalo_group_reports_a_code_instead_of_staying_silent(self):
        wb.Source(self.src).save_selection([])
        self.assertEqual(self.bundle.step()["error"], "no_zalo_group")
        plain = BundleProcessor(LiveSync(self.src), self.root / "state2", self.root / "bundle2", "fake:" + BUNDLE_REMOTE, run=self.remote,
                                fetch=FakeCdn(), transcode=no_jxl, clock=lambda: self.now)
        self.assertIsNone(plain.step()["error"])   # không có WeChat thì giữ hành vi cũ

    def test_dry_run_uses_its_own_store_so_the_real_log_is_never_appended(self):
        live = LiveSync(self.src)
        wechat = {"python": "py", "pilot": "p", "groups": str(self.selection.path), "run": self.db}
        dry = agent_main.Agent(live, self.root, "fake:" + BUNDLE_REMOTE, "fake:/srv/v7/zalo-agent", run=self.remote, dry_run=True, wechat=wechat)
        self.assertEqual(dry.processors[0].overlay.dir.name, "wechat-dry")
        real = agent_main.Agent(live, self.root, "fake:" + BUNDLE_REMOTE, "fake:/srv/v7/zalo-agent", run=self.remote, wechat=wechat)
        self.assertEqual(real.processors[0].overlay.dir.name, "wechat")

    def test_rebuild_reads_the_group_list_once(self):
        self.db.feed = [msg(1, 1000)]
        self.poll()
        data = self.root / "bundle" / "data-x"
        data.mkdir(parents=True)
        for name, content in (("conversations.json", "[]"), ("users.json", '{"self_user": null, "users": {}}'), ("messages.jsonl", ""), ("media.json", "{}")):
            (data / name).write_text(content, encoding="utf-8")
        reads = []
        original = self.selection.groups
        self.selection.groups = lambda: (reads.append(1), original())[1]
        self.store.merge_into(data, self.root / "bundle")
        self.assertEqual(len(reads), 1)


class SessionTest(unittest.TestCase):
    PILOT = (
        "import os, time\n"
        "HERE = os.path.dirname(os.path.abspath(__file__))\n"
        "class Db:\n"
        "    def get_groups(self):\n"
        "        if os.path.exists(os.path.join(HERE, 'slow')):\n"
        "            time.sleep(30)\n"
        f"        return [{{'username': {USER!r}, 'name': 'Nhóm', 'members': []}}]\n"
        "    def get_messages(self, username, limit=20, offset=0):\n"
        "        return []\n"
        "    def get_new_messages(self, username, since_seq=0, limit=200):\n"
        "        return []\n"
        "    def nickname_map(self):\n"
        "        return {}\n"
        "def open_database():\n"
        "    with open(os.path.join(HERE, 'opens.txt'), 'a') as f:\n"
        "        f.write('x')\n"
        "    if os.path.exists(os.path.join(HERE, 'fail')):\n"
        "        raise RuntimeError('hỏng')\n"
        "    return Db()\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pilot = Path(self.tmp.name)
        (self.pilot / "db_adapter.py").write_text(self.PILOT, encoding="utf-8")
        self.session = wc.Session()
        self.addCleanup(self.session.stop)

    def opens(self):
        return len((self.pilot / "opens.txt").read_text(encoding="utf-8")) if (self.pilot / "opens.txt").exists() else 0

    def read(self, timeout=60):
        return self.session(sys.executable, str(self.pilot), "read", {"groups": {USER: {}}}, timeout)

    def test_one_long_lived_child_opens_the_database_once_for_many_requests(self):
        for _ in range(3):
            code, output = self.read()
            self.assertEqual((code, [i["kind"] for i in wc.parse(output)]), (0, ["end"]))
        self.assertEqual(self.opens(), 1)   # khóa chỉ lấy một lần, không mỗi 10 giây

    def test_a_dead_child_is_recreated_on_the_next_request(self):
        self.read()
        self.session.proc.kill()
        self.session.proc.wait(10)
        self.assertEqual(self.read()[0], 0)
        self.assertEqual(self.opens(), 2)

    def test_a_hung_request_times_out_kills_the_child_and_the_next_one_works(self):
        self.read()
        (self.pilot / "slow").write_text("1", encoding="utf-8")
        started = time.time()
        with self.assertRaises(subprocess.TimeoutExpired):
            self.read(timeout=2)
        self.assertLess(time.time() - started, 15)
        self.assertIsNone(self.session.proc)
        (self.pilot / "slow").unlink()
        self.assertEqual(self.read()[0], 0)

    def test_a_failing_database_open_reports_an_error_code_and_recovers_later(self):
        (self.pilot / "fail").write_text("1", encoding="utf-8")
        code, output = self.read()
        self.assertEqual((code, wc.parse(output)), (2, [{"kind": "error", "code": "RuntimeError"}]))
        (self.pilot / "fail").unlink()
        self.assertEqual(self.read()[0], 0)   # cùng tiến trình sống, mở lại DB ở yêu cầu sau

    def test_groups_command_still_runs_one_shot(self):
        code, output = self.session(sys.executable, str(self.pilot), "groups", {}, 60)
        self.assertEqual((code, [g["name"] for g in wc.parse(output)]), (0, ["Nhóm"]))
        self.assertIsNone(self.session.proc)


class RoundTwoExportTest(unittest.TestCase):
    Db = ExportTest.Db

    class Stale(ExportTest.Db):
        """Upstream giữ `_sender_id_cache` và `nickname_map` trong bộ nhớ: người mới vào nhóm sau khi mở DB chưa có trong đó."""

        def __init__(self):
            super().__init__([(USER, NAME)], total=2)
            self._sender_id_cache = {}   # còn cũ
            self.fresh_nicks = False

        def get_messages(self, username, limit=20, offset=0):
            rows = super().get_messages(username, limit, offset)
            return [{**row, "sender_username": "" if self._sender_id_cache is not None else "wxid_moi1",
                     "content": "wxid_moi1:\n" + row["content"]} for row in rows]

        def nickname_map(self, refresh=False):
            self.fresh_nicks = self.fresh_nicks or refresh
            return {"wxid_moi1": "Người mới"} if self.fresh_nicks else {}

    def run_read(self, db, request):
        lines = []
        with unittest.mock.patch.object(export, "emit", lines.append):
            export.cmd_read(db, request)
        return lines

    def test_stale_sender_cache_is_reset_and_the_group_reread_so_new_members_get_names(self):
        db = self.Stale()
        lines = self.run_read(db, {"groups": {USER: {}}, "first_limit": 10})
        messages = [line for line in lines if line["kind"] == "message"]
        self.assertIsNone(db._sender_id_cache)
        self.assertEqual({(m["sender"], m["sender_name"]) for m in messages}, {("wxid_moi1", "Người mới")})
        self.assertEqual([m["content"] for m in messages], ["tin 1", "tin 2"])   # tiền tố id tùy chỉnh bị bỏ sau khi đọc lại

    def test_prefix_of_any_id_like_token_is_dropped_but_plain_words_are_kept(self):
        self.assertEqual(export.clean_content("文本", "abc123:\nThu 5 triệu"), "Thu 5 triệu")
        self.assertEqual(export.clean_content("文本", "wxid_xyz12:\nThu 5 triệu"), "Thu 5 triệu")
        self.assertEqual(export.clean_content("文本", "T10:\nThu 5 triệu"), "T10:\nThu 5 triệu")   # quá ngắn để là username
        self.assertEqual(export.clean_content("文本", "Ghi:\nThu 5 triệu"), "Ghi:\nThu 5 triệu")
        self.assertEqual(export.clean_content("文本", "Ghi:\nThu 5 triệu", "Ghi"), "Thu 5 triệu")

    def test_system_text_loses_every_scheme_tag_and_placeholder(self):
        text = 'Bạn xem <_wc_custom_link_ href="weixin://findfriend/verifycontact">liên kết</_wc_custom_link_> weixin://abc/def ftp://x.example.test/y'
        self.assertEqual(export.clean_content("系统消息", text), "Bạn xem liên kết")
        join = '<sysmsg type="sysmsgtemplate"><sysmsgtemplate><content_template><template><![CDATA["${username}" vừa vào nhóm]]></template></content_template></sysmsgtemplate></sysmsg>'
        cleaned = export.clean_content("系统消息", join)
        self.assertIn("vừa vào nhóm", cleaned)
        self.assertNotIn("$", cleaned)
        self.assertEqual(export.clean_content("系统消息", '<sysmsg type="x"><a>mã</a></sysmsg>'), "")
        row = wc.convert(msg(1, 1000, "", "系统消息", sender=""))[0]
        self.assertEqual(row["body"], wc.NOTICE_LABEL)

    def test_window_rows_the_parent_already_has_are_not_sent_again(self):
        db = self.Db([(USER, NAME)], total=3)
        request = {"groups": {USER: {"sort_seq": 3000, "tail": [3]}}, "window_hours": 6}
        with unittest.mock.patch.object(export.time, "time", return_value=1_793_000_010.0):
            first = self.run_read(db, request)
            sent = {USER: {f"{m['local_id']}:{m['sort_seq']}": m["fp"] for m in first if m["kind"] == "message"}}
            second = self.run_read(db, {**request, "known_fp": sent})
            changed = {USER: {**sent[USER], "2:2000": "0" * 16}}   # một dòng đã khác: gửi lại đúng dòng đó
            third = self.run_read(db, {**request, "known_fp": changed})
        self.assertEqual((first[-1]["window"], first[-1]["window_same"]), (3, 0))
        self.assertEqual((second[-1]["window"], second[-1]["window_same"], len(second)), (0, 3, 1))
        self.assertEqual([m["local_id"] for m in third if m["kind"] == "message"], [2])

    def test_the_request_budget_is_shared_across_groups_so_one_request_always_finishes(self):
        groups = [(f"wxid_g{i}@chatroom", f"Nhóm {i}") for i in range(3)]
        db = self.Db(groups, total=3000)
        lines = self.run_read(db, {"groups": {u: {"sort_seq": 1000, "tail": [1]} for u, _ in groups}})
        per_group = {}
        for line in lines:
            if line["kind"] == "message":
                per_group[line["username"]] = per_group.get(line["username"], 0) + 1
        self.assertEqual(sorted(per_group.values()), [666, 666, 666])
        self.assertLessEqual(lines[-1]["messages"], export.REQUEST_BUDGET)


class RoundTwoProcessorTest(WeChatBase):
    def make_agent(self):
        wechat = {"python": "py", "pilot": "p", "groups": str(self.selection.path), "run": self.db, "background": False}
        agent = agent_main.Agent(LiveSync(self.src), self.root, "fake:" + BUNDLE_REMOTE, "fake:/srv/v7/zalo-agent", run=self.remote,
                                 clock=lambda: self.now, wechat=wechat, fetch=FakeCdn(), transcode=no_jxl, max_age_days=None)
        self.addCleanup(agent.release)
        return agent

    def test_an_unchanged_window_causes_no_poll_result_log_line_or_status_push(self):
        agent = self.make_agent()
        self.db.feed = [msg(1, 1000, "tin có sẵn")]
        for _ in range(4):   # lượt đầu có dòng thật sự ghi, dựng gói, đẩy phần thêm: trạng thái đổi bình thường
            self.now += 11
            agent.cycle(force_status=True)
        self.db.window = [msg(1, 1000, "tin có sẵn", window=True)]   # cửa sổ 6 giờ: mọi tin phát lại y nguyên mỗi lượt
        pushes = self.remote.applies("/srv/v7/zalo-agent")
        for _ in range(4):
            self.now += 11
            self.assertIsNone(agent.cycle())
        self.assertEqual(self.remote.applies("/srv/v7/zalo-agent"), pushes)

    def test_poll_is_reported_only_when_rows_were_really_written(self):
        self.db.feed = [msg(1, 1000)]
        self.assertEqual(self.poll()["action"], "poll")
        self.db.window = [msg(1, 1000, window=True)]
        self.assertEqual([self.poll()["action"] for _ in range(3)], ["idle", "idle", "idle"])
        self.db.window = [msg(1, 1000, "đã sửa", window=True)]
        self.assertEqual(self.poll()["action"], "poll")

    def test_known_fingerprints_travel_with_the_next_request_and_expire_after_the_window(self):
        self.now = 1_793_000_100.0   # cùng thời với giờ tin của msg()
        self.db.feed = [msg(1, 1000, fp="f" * 16)]
        self.poll()
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["known_fp"], {USER: {"1:1000": "f" * 16}})
        self.now += 8 * 3600   # quá cửa sổ 6 giờ cộng một giờ đệm: quên
        self.processor.step()
        self.assertEqual(self.db.requests[-1][1]["known_fp"], {})

    def test_a_window_pass_never_overwrites_a_decoded_image_row(self):
        self.processor = self.make_processor(images=True)
        (self.store.dir / "incoming").mkdir(exist_ok=True)
        (self.store.dir / "incoming" / "a.jpg").write_bytes(JPEG)
        self.db.feed = [msg(1, 1000, "", "图片", image="a.jpg")]
        self.poll()
        self.db.window = [msg(1, 1000, "", "图片", window=True)]   # cửa sổ không có ảnh giải mã
        self.poll()
        self.assertEqual([(row["body"], bool(row.get("media"))) for row in self.store.rows_after(0)[0]], [("Ảnh WeChat", True)])

    def test_a_group_unselected_while_the_child_was_reading_is_neither_stored_nor_given_a_cursor(self):
        self.processor.apply(None, [msg(1, 1000, "đến sau khi bỏ chọn")], {}, {})
        self.assertEqual(self.store.rows_after(0), ([], 0))
        self.assertEqual(self.processor.cursors, {})

    def test_a_missing_sender_is_corrected_later_and_never_shown_as_a_raw_id(self):
        self.db.feed = [msg(1, 1000, "tin", sender="")]
        self.poll()
        first = self.store.rows_after(0)[0][0]
        self.assertIsNone(first["sender_id"])
        self.db.window = [msg(1, 1000, "tin", sender="wxid_moi", name="", window=True)]   # tra ra id nhưng chưa có biệt danh
        self.poll()
        fixed = self.store.rows_after(0)[0][0]
        self.assertIsNotNone(fixed["sender_id"])
        names = json.loads((self.store.dir / "users.json").read_text(encoding="utf-8"))
        self.assertEqual(names, {fixed["sender_id"]: wc.MEMBER_NAME})
        self.assertNotIn("wxid", json.dumps([fixed, names]))


class RoundThreeExportTest(unittest.TestCase):
    Db = ExportTest.Db

    def setUp(self):
        export.TRIED.clear()
        self.addCleanup(export.TRIED.clear)

    def run_read(self, db, request):
        lines = []
        with unittest.mock.patch.object(export, "emit", lines.append), unittest.mock.patch.object(export.time, "time", return_value=1_793_000_010.0):
            export.cmd_read(db, request)
        return lines

    def test_own_messages_never_lose_their_first_line_even_when_it_looks_like_a_prefix(self):
        self.assertEqual(export.clean_content("文本", "KH0001:\nthu 5tr", "", is_self=True), "KH0001:\nthu 5tr")
        self.assertEqual(export.clean_content("文本", "T10:\nthu 5tr", "", is_self=True), "T10:\nthu 5tr")
        self.assertEqual(export.clean_content("文本", "wxid_abcdef:\nthu", "", is_self=True), "wxid_abcdef:\nthu")
        row = {"local_id": 1, "sort_seq": 1000, "create_time": 1, "type": "文本", "sender_id": 2, "sender_username": "", "content": "KH0001:\nthu 5tr"}
        self.assertEqual(export.record({}, USER, row, None, None)["content"], "KH0001:\nthu 5tr")

    def test_a_known_sender_only_loses_a_prefix_equal_to_their_own_username(self):
        self.assertEqual(export.clean_content("文本", "KH0001:\nthu 5tr", "wxid_a1b2c3"), "KH0001:\nthu 5tr")
        self.assertEqual(export.clean_content("文本", "wxid_a1b2c3:\nthu 5tr", "wxid_a1b2c3"), "thu 5tr")
        self.assertEqual(export.clean_content("文本", "wxid_other9:\nthu 5tr", "wxid_a1b2c3"), "wxid_other9:\nthu 5tr")   # không phải người gửi

    def test_the_real_join_template_with_dollar_placeholders_keeps_only_readable_text(self):
        template = '<sysmsg type="sysmsgtemplate"><sysmsgtemplate><content_template type="tmpl_type_profilewithrevoke"><template><![CDATA["$username$"邀请"$names$"加入了群聊]]></template></content_template></sysmsgtemplate></sysmsg>'
        cleaned = export.clean_content("系统消息", template)
        self.assertIn("加入了群聊", cleaned)
        self.assertNotIn("$", cleaned)
        self.assertNotIn("username", cleaned)

    def test_an_unresolvable_sender_triggers_one_refresh_then_none_for_six_hours_and_never_drops_the_db(self):
        class Gone(ExportTest.Db):
            """Người gửi đã rời nhóm: không bao giờ tra ra, và làm mới biệt danh lúc nào cũng lỗi."""

            def __init__(self):
                super().__init__([(USER, NAME)], total=2)
                self.refreshes = 0

            def get_messages(self, username, limit=20, offset=0):
                return [{**row, "sender_username": "wxid_roi1"} for row in super().get_messages(username, limit, offset)]

            def nickname_map(self, refresh=False):
                if refresh:
                    self.refreshes += 1
                    raise RuntimeError("lỗi thoáng qua")
                return {}

        db = Gone()
        for _ in range(4):
            lines = self.run_read(db, {"groups": {USER: {}}, "first_limit": 10})
            self.assertEqual(lines[-1]["kind"], "end")   # lỗi làm mới không làm hỏng yêu cầu, không ném ra serve (không bỏ DB)
        self.assertEqual(db.refreshes, 1)
        export.TRIED[("name", "wxid_roi1")] = 1_793_000_010.0 - 7 * 3600   # quá hạn 6 giờ: thử lại một lần
        self.run_read(db, {"groups": {USER: {}}, "first_limit": 10})
        self.assertEqual(db.refreshes, 2)

    def test_only_new_messages_decide_a_refresh_not_the_replayed_window(self):
        class Stale(ExportTest.Db):
            def __init__(self):
                super().__init__([(USER, NAME)], total=3)
                self.refreshes = 0

            def get_messages(self, username, limit=20, offset=0):
                return [{**row, "sender_username": "wxid_cu"} for row in super().get_messages(username, limit, offset)]

            def nickname_map(self, refresh=False):
                self.refreshes += refresh
                return {"wxid_cu": "Người cũ"} if refresh else {}   # tên chỉ có sau làm mới

        db = Stale()
        # cursor ở cuối: không có tin mới, chỉ có cửa sổ với người gửi "chưa tra được" → không làm mới
        self.run_read(db, {"groups": {USER: {"sort_seq": 3000, "tail": [3]}}, "window_hours": 6})
        self.assertEqual(db.refreshes, 0)

    def test_first_read_is_inside_the_shared_budget_and_takes_only_the_newest(self):
        groups = [(f"wxid_g{i}@chatroom", f"Nhóm {i}") for i in range(3)]
        db = self.Db(groups, total=3000)
        lines = self.run_read(db, {"groups": {u: {} for u, _ in groups}, "first_limit": 5000})
        messages = [line for line in lines if line["kind"] == "message"]
        self.assertEqual(len(messages), 3 * 666)   # không còn 3 × 5000 làm yêu cầu vượt timeout và kẹt
        self.assertEqual(max(m["local_id"] for m in messages), 3000)   # lấy tin GẦN NHẤT
        self.assertEqual(min(m["local_id"] for m in messages), 3000 - 666 + 1)


class RoundThreeProcessorTest(WeChatBase):
    def test_a_nickname_that_arrives_later_updates_users_json_and_a_placeholder_never_overwrites_it(self):
        self.db.feed = [msg(1, 1000, "tin", sender="wxid_moi1", name="")]
        self.poll()
        row = self.store.rows_after(0)[0][0]
        users = lambda: json.loads((self.store.dir / "users.json").read_text(encoding="utf-8"))  # noqa: E731
        self.assertEqual(users(), {row["sender_id"]: wc.MEMBER_NAME})
        self.db.window = [msg(1, 1000, "tin", sender="wxid_moi1", name="Người mới", window=True)]   # dòng không đổi, biệt danh có sau
        self.poll()
        self.assertEqual(users(), {row["sender_id"]: "Người mới"})
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 1)   # không thêm dòng, chỉ cập nhật tên
        self.db.window = [msg(1, 1000, "tin", sender="wxid_moi1", name="", window=True)]
        self.poll()
        self.assertEqual(users(), {row["sender_id"]: "Người mới"})   # tra lỗi thoáng qua: không đè tên thật

    def test_raw_ids_left_in_an_old_users_json_are_cleaned_and_never_reach_the_bundle(self):
        self.db.feed = [msg(1, 1000, "tin", sender="wxid_moi1", name="Người mới")]
        self.poll()
        row = self.store.rows_after(0)[0][0]
        (self.store.dir / "users.json").write_text(json.dumps({row["sender_id"]: "wxid_moi1xyz"}), encoding="utf-8")   # bản cũ còn mã thô
        self.assertEqual(self.store.users_for([row]), {row["sender_id"]: wc.MEMBER_NAME})
        self.bundle.step()
        files = self.remote_files()
        self.assertEqual(files["users"]["users"][row["sender_id"]], wc.MEMBER_NAME)
        self.assertNotIn("wxid", json.dumps(files["users"]))
        self.assertEqual(wc.safe_name("wxid_abc123"), wc.MEMBER_NAME)
        self.assertEqual(wc.safe_name("Anh Hùng"), "Anh Hùng")


if __name__ == "__main__":
    unittest.main()
