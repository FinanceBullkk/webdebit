"""WECHAT-01: nguồn WeChat của zalo-agent, test với tiến trình con giả và dữ liệu bịa (không WeChat thật, không ssh)."""

import contextlib
import hashlib
import io
import json
import os
import struct
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
from zalo_agent import wechat_app as app  # noqa: E402
from zalo_agent import wechat_dat as dat  # noqa: E402
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


def jpeg(width: int, height: int) -> bytes:
    """JPEG nhỏ nhất có khối SOF0 (đủ để đọc kích thước); ảnh khác cỡ thì khác mã sha256."""
    return b"\xff\xd8\xff\xc0\x00\x11\x08" + struct.pack(">HH", height, width) + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01\xff\xd9"


FULL_JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 8 + b"\xff\xd9"
FULL_PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 8 + b"\x00\x00\x00\x00IEND\xaeB`\x82"
WXID, CODE = "wxid_demo_35b6", "123456"
GOOD_KEY = hashlib.md5(b"123456wxid_demo").hexdigest()[:16]   # mã kvcomm + wxid bỏ đuôi `_35b6`


def wechat_dirs(root: Path, code: str | None = CODE, area: str = "net", samples=((FULL_PNG, GOOD_KEY), (FULL_JPEG, GOOD_KEY))) -> Path:
    """APPDATA giả có file kvcomm và thư mục tài khoản có các file `.dat` V2 thật (mã hóa bằng bộ mã của repo)."""
    if code is not None:
        kvcomm = root / "appdata" / "Tencent" / "xwechat" / area / "kvcomm"
        kvcomm.mkdir(parents=True, exist_ok=True)
        (kvcomm / f"key_{code}_1000000001_1_1.statistic").write_bytes(b"")
    img = root / "account" / "msg" / "attach" / "a1b2" / "2026-11" / "Img"
    img.mkdir(parents=True, exist_ok=True)
    for index, (image, key) in enumerate(samples):
        (img / f"{index:02d}.dat").write_bytes(dat.encode_v2(image, key.encode(), int(CODE) & 0xFF))
    return root / "account"


class OfflineImageKeyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for cache in (export.KEYS, export.MISSES):
            patcher = unittest.mock.patch.dict(cache, clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def key(self, account, wxid=WXID, appdata=None):
        db = unittest.mock.Mock(wxid=wxid, account_dir=str(account))
        with unittest.mock.patch.dict(os.environ, {"APPDATA": str(appdata or self.root / "appdata")}):
            return export.offline_image_key(db)

    def test_kvcomm_code_and_clean_account_id_open_png_and_jpeg_samples(self):
        account = wechat_dirs(self.root)   # một mẫu PNG, một JPEG, đòi cả hai mở: bộ thử chỉ-JPEG của upstream loại khóa khi gặp mẫu PNG
        self.assertEqual(self.key(account), (GOOD_KEY, int(CODE) & 0xFF))

    def test_ilink_kvcomm_and_newest_code_first(self):
        account = wechat_dirs(self.root, code="999", area="ilink")
        old = self.root / "appdata" / "Tencent" / "xwechat" / "ilink" / "kvcomm" / "key_999_1000000001_1_1.statistic"
        os.utime(old, (1_700_000_000, 1_700_000_000))
        wechat_dirs(self.root, area="ilink", samples=())
        self.assertEqual(self.key(account), (GOOD_KEY, int(CODE) & 0xFF))
        self.assertEqual(export.kvcomm_codes(self.root / "appdata"), [CODE, "999"])

    def test_no_key_without_appdata_kvcomm_matching_samples_or_v2_files(self):
        account = wechat_dirs(self.root)
        db = unittest.mock.Mock(wxid=WXID, account_dir=str(account))
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(export.offline_image_key(db))   # APPDATA trống không được hiểu là thư mục hiện tại
        self.assertIsNone(self.key(account, appdata=self.root / "khong-co"))
        other = Path(self.tmp.name) / "khac"
        self.assertIsNone(self.key(wechat_dirs(other, samples=((FULL_JPEG, "0" * 16), (FULL_PNG, "0" * 16))), appdata=other / "appdata"))
        legacy = self.root / "cu"
        img = wechat_dirs(legacy, samples=()) / "msg" / "attach" / "a1b2" / "2026-11" / "Img"
        (img / "00.dat").write_bytes(bytes(b ^ 0x37 for b in FULL_JPEG))   # khuôn cũ XOR: không phải mẫu thử khóa V2
        self.assertIsNone(self.key(legacy / "account", appdata=legacy / "appdata"))

    def test_one_lucky_block_is_not_enough_when_there_are_two_samples(self):
        account = wechat_dirs(self.root, samples=((FULL_JPEG, GOOD_KEY), (FULL_JPEG, "f" * 16)))
        self.assertEqual(len(export.v2_probes(str(account))), 2)
        self.assertIsNone(self.key(account))   # một mẫu mở, một mẫu không: chưa đủ để nhận
        probe = lambda image, key: (dat.encode_v2(image, key.encode(), 1)[dat.V2_HEADER.size:dat.V2_HEADER.size + 16], b"")  # noqa: E731
        good, bad, png = probe(FULL_JPEG, GOOD_KEY), probe(FULL_JPEG, "f" * 16), probe(FULL_PNG, GOOD_KEY)
        self.assertFalse(export.opens(GOOD_KEY, [good, bad]))
        self.assertTrue(export.opens(GOOD_KEY, [good]))
        self.assertTrue(export.opens(GOOD_KEY, [bad, good, png]))
        self.assertEqual(export.v2_probes(str(account), limit=1), export.v2_probes(str(account))[:1])

    def test_a_checked_key_survives_an_empty_kvcomm_but_not_another_code(self):
        account = wechat_dirs(self.root)
        self.assertEqual(self.key(account), (GOOD_KEY, int(CODE) & 0xFF))
        for path in (account / "msg" / "attach" / "a1b2" / "2026-11" / "Img").iterdir():
            path.unlink()   # không còn mẫu: lượt sau vẫn có khóa nhờ bộ nhớ của tiến trình `serve`, không đọc lại mẫu
        self.assertEqual(self.key(account), (GOOD_KEY, int(CODE) & 0xFF))
        kvcomm = self.root / "appdata" / "Tencent" / "xwechat" / "net" / "kvcomm"
        (kvcomm / f"key_{CODE}_1000000001_1_1.statistic").unlink()
        self.assertEqual(self.key(account), (GOOD_KEY, int(CODE) & 0xFF))   # WeChat thoát thì xóa rồi tạo lại file: không báo mất khóa
        (kvcomm / "key_777_1000000001_1_1.statistic").write_bytes(b"")
        self.assertIsNone(self.key(account))   # mã khác thay chỗ: không tin khóa cũ nữa, suy lại (hết mẫu nên hụt)
        (kvcomm / f"key_{CODE}_1000000002_1_1.statistic").write_bytes(b"")
        self.assertEqual(self.key(account), (GOOD_KEY, int(CODE) & 0xFF))   # mã cũ trở lại: dùng lại khóa đã kiểm, không cần mẫu

    def test_a_miss_is_not_rescanned_for_ten_minutes_unless_a_new_kvcomm_code_appears(self):
        account = wechat_dirs(self.root, samples=((FULL_JPEG, "0" * 16), (FULL_PNG, "0" * 16)))   # mẫu của khóa khác: không suy được
        with unittest.mock.patch.object(export, "v2_probes", wraps=export.v2_probes) as scan:
            self.assertIsNone(self.key(account))
            self.assertIsNone(self.key(account))   # lượt 10 giây sau: không quét lại thư mục ảnh
            self.assertEqual(scan.call_count, 1)
            wechat_dirs(self.root, code="777", samples=())
            self.assertIsNone(self.key(account))   # có mã kvcomm mới: thử ngay
            self.assertEqual(scan.call_count, 2)
            os.utime(next((self.root / "appdata").rglob(f"key_{CODE}_*")), (2_000_000_000, 2_000_000_000))
            self.assertIsNone(self.key(account))   # chỉ đổi thứ tự (file cũ bị chạm): vẫn là cùng tập mã, không quét lại
            self.assertEqual(scan.call_count, 2)
            with unittest.mock.patch.object(export.time, "monotonic", return_value=time.monotonic() + export.MISS_RETRY + 1):
                self.assertIsNone(self.key(account))
            self.assertEqual(scan.call_count, 3)
            self.assertEqual(len(export.MISSES), 1)   # mục cũ được dọn, không phình

    def test_xor_byte_comes_from_image_endings_when_two_samples_agree(self):
        samples = ((FULL_JPEG, GOOD_KEY), (FULL_PNG, GOOD_KEY))
        account = wechat_dirs(self.root, samples=())
        img = account / "msg" / "attach" / "a1b2" / "2026-11" / "Img"
        for index, (image, key) in enumerate(samples):   # XOR 0x00, khác mã & 0xFF = 0x40: phải lấy byte suy từ đuôi ảnh
            (img / f"{index:02d}.dat").write_bytes(dat.encode_v2(image, key.encode(), 0x00))
        self.assertEqual(self.key(account), (GOOD_KEY, 0x00))
        probes = export.v2_probes(str(account))
        self.assertIsNone(export.tail_xor(GOOD_KEY, probes[:1]))   # một mẫu thì chưa đủ tin: dùng mã & 0xFF
        odd = dat.encode_v2(FULL_JPEG + b"thua", GOOD_KEY.encode(), 0x00)   # dữ liệu thừa sau FF D9: mẫu này không suy được, còn một mẫu
        (img / "00.dat").write_bytes(odd)
        self.assertIsNone(export.tail_xor(GOOD_KEY, export.v2_probes(str(account))))
        gif = b"GIF89a" + bytes(range(256)) * 4 + b"\x3b" + b"\x00" * 6   # GIF có đệm 0: đuôi một byte "khớp" với byte sai
        for index in range(2):
            (img / f"{index:02d}.dat").write_bytes(dat.encode_v2(gif, GOOD_KEY.encode(), 0x40))
        self.assertIsNone(export.tail_xor(GOOD_KEY, export.v2_probes(str(account))))   # không dùng GIF: quay về mã & 0xFF

    def test_export_only_decodes_when_upstream_finds_this_exact_message(self):
        downloader = unittest.mock.Mock()
        downloader.download_image.return_value = str(self.root / "anh.jpg")
        tools = (downloader, GOOD_KEY, 0x40)
        downloader.db.get_message_row.return_value = {"local_id": 7, "sort_seq": 9000}
        self.assertEqual(export.export_image(tools, USER, 7, 9000, str(self.root)), "anh.jpg")
        downloader.download_image.reset_mock()
        # local_id 7 cũng có ở mảnh DB khác với sort_seq lớn hơn: upstream sẽ trả ảnh của tin KIA, nên không giải
        self.assertIsNone(export.export_image(tools, USER, 7, 5000, str(self.root)))
        downloader.download_image.assert_not_called()
        downloader.db.get_message_row.side_effect = RuntimeError("hỏng")
        self.assertIsNone(export.export_image(tools, USER, 7, 9000, str(self.root)))


class FakeDb:
    """Nguồn của tiến trình con giả: lọc đúng như `wechat_export.read_group` bằng `is_new`."""

    def __init__(self):
        self.feed = []
        self.requests = []
        self.fail = None      # (mã trả về) hoặc ngoại lệ sẽ ném
        self.gate = None      # threading.Event: chặn cho tới khi test cho chạy
        self.window = []      # tin đọc lại trong cửa sổ (đã đổi tại chỗ), phát kèm ở mỗi lượt
        self.image_keys = True   # dòng `end` báo tiến trình con có khóa ảnh
        self.end_extra = {}      # trường thêm vào dòng `end` (image_budget_hit, images…)

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
        end = {"kind": "end", "messages": len(items), "image_keys": self.image_keys, **self.end_extra}
        return 0, "".join(json.dumps(item) + "\n" for item in [*items, *self.window, end])


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
        args = {"python": "py", "pilot": "pilot", "run": self.db, "clock": lambda: self.now, "background": False, "app": lambda: "logged_in", **kwargs}
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
        wechat = {"python": "py", "pilot": "p", "groups": str(self.selection.path), "run": self.db, "background": False, "app": lambda: "logged_in"}
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

    def test_a_window_pass_backfills_an_image_that_was_previously_missing(self):
        self.processor = self.make_processor(images=True)
        self.db.feed = [msg(1, 1000, "", "图片")]
        self.poll()
        (self.store.dir / "incoming").mkdir(exist_ok=True)
        (self.store.dir / "incoming" / "a.jpg").write_bytes(JPEG)
        self.db.window = [msg(1, 1000, "", "图片", image="a.jpg", window=True)]
        self.poll()
        self.assertEqual([(row["body"], bool(row.get("media"))) for row in self.store.rows_after(0)[0]], [("Ảnh WeChat", True)])
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 2)

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


class ImageRetryExportTest(unittest.TestCase):
    """Tiến trình con: tin ảnh trong cửa sổ mà bộ xử lý chưa có thì giải lại; lượt sâu chỉ thêm tin ảnh cũ hơn cửa sổ thường."""

    NOW = 1_793_100_000

    class Db(ExportTest.Db):
        def __init__(self, rows):
            super().__init__([(USER, NAME)])
            self.fixed = rows

        def rows(self):
            return self.fixed

    def row(self, local_id, kind, age_hours):
        return {"local_id": local_id, "type": kind, "sender_id": 5, "sender_username": "wxid_a", "content": "tin",
                "create_time": int(self.NOW - age_hours * 3600), "sort_seq": local_id * 1000}

    def setUp(self):
        self.db = self.Db([self.row(1, "图片", 9 * 24), self.row(2, "文本", 48), self.row(3, "图片", 48), self.row(4, "文本", 1),
                           self.row(5, "图片", 1), self.row(6, "图片", 0.5)])
        self.request = {"groups": {USER: {"sort_seq": 6000, "tail": [6]}}, "window_hours": 6, "images_dir": "incoming"}

    def run_read(self, request, tools=("downloader", "khoa", 1)):
        lines, decoded = [], []

        def fake_export(_tools, username, local_id, sort_seq, directory):
            decoded.append(local_id)
            return f"{local_id}.jpg"

        with unittest.mock.patch.object(export, "emit", lines.append), \
                unittest.mock.patch.object(export, "image_tools", return_value=tools), \
                unittest.mock.patch.object(export, "export_image", side_effect=fake_export), \
                unittest.mock.patch.object(export.time, "time", return_value=float(self.NOW)):
            export.cmd_read(self.db, request)
        return [line for line in lines if line["kind"] == "message"], lines[-1], decoded

    def test_window_images_the_parent_still_lacks_are_decoded_again_known_ones_are_not(self):
        first, end, decoded = self.run_read(self.request)
        self.assertEqual([(m["local_id"], m["image"]) for m in first], [(4, None), (5, "5.jpg"), (6, "6.jpg")])
        self.assertEqual((decoded, end["images"], end["window"]), ([5, 6], 2, 3))
        known = {USER: {f"{m['local_id']}:{m['sort_seq']}": m["fp"] for m in first if m["local_id"] in (4, 6)}}   # ảnh 5 vẫn thiếu
        again, end, decoded = self.run_read({**self.request, "known_fp": known})
        self.assertEqual(([m["local_id"] for m in again], decoded, end["window_same"]), ([5], [5], 2))

    def test_the_deep_pass_adds_only_older_image_rows_and_only_when_there_is_a_key(self):
        deep = {**self.request, "deep_image_hours": 7 * 24}
        rows, _, decoded = self.run_read(deep)
        self.assertEqual([m["local_id"] for m in rows], [3, 4, 5, 6])   # tin chữ 2 ngày và ảnh 9 ngày không vào
        self.assertEqual([m["local_id"] for m in rows if m.get("deep")], [3])   # chỉ phần ngoài cửa sổ thường mang cờ `deep`
        self.assertEqual(decoded, [3, 5, 6])
        rows, end, decoded = self.run_read(deep, tools=None)
        self.assertEqual(([m["local_id"] for m in rows], decoded, end["image_keys"]), ([4, 5, 6], [], False))
        with unittest.mock.patch.object(export, "DEEP_IMAGE_BUDGET", 0):   # trần ảnh của lượt sâu: yêu cầu luôn xong trong timeout
            rows, _, decoded = self.run_read(deep)
        self.assertEqual(([m["local_id"] for m in rows], decoded), ([4, 5, 6], [5, 6]))

    def test_out_of_image_time_new_messages_still_flow_without_images_and_the_end_line_says_so(self):
        self.db.fixed = [*self.db.fixed, self.row(7, "图片", 0.1), self.row(8, "文本", 0.1)]   # hai tin mới sau con trỏ
        with unittest.mock.patch.object(export, "IMAGE_SECONDS", 0):   # sau đợt máy tắt lâu: hết giờ giải ảnh ngay
            rows, end, decoded = self.run_read({**self.request, "deep_image_hours": 7 * 24})
        fresh = [m for m in rows if not m.get("window")]
        self.assertEqual([(m["local_id"], m["image"]) for m in fresh], [(7, None), (8, None)])   # tin mới vẫn đi, con trỏ vẫn tiến
        self.assertEqual([m["local_id"] for m in rows if m.get("window")], [4])   # tin ảnh cửa sổ/7 ngày không ảnh thì không phát
        self.assertEqual((decoded, end.get("image_budget_hit")), ([], True))
        _, end, _ = self.run_read(self.request)
        self.assertNotIn("image_budget_hit", end)   # còn giờ: dòng `end` như cũ

    def test_an_hevc_image_without_ffmpeg_falls_back_to_the_thumbnail(self):
        with tempfile.TemporaryDirectory() as tmp:
            downloader = unittest.mock.Mock()
            downloader.db.get_message_row.return_value = {"local_id": 7, "sort_seq": 7000}
            for name in ("a.wxgf", "a_thumb.jpg"):
                (Path(tmp) / name).write_bytes(b"x")
            downloader.download_image.side_effect = lambda *a, tier=None, **k: str(Path(tmp) / ("a.wxgf" if tier == "best" else "a_thumb.jpg"))
            self.assertEqual(export.export_image((downloader, "k", 1), USER, 7, 7000, tmp), "a_thumb.jpg")
            self.assertFalse((Path(tmp) / "a.wxgf").exists())
            downloader.download_image.side_effect = lambda *a, tier=None, **k: str(Path(tmp) / "b.wxgf")
            self.assertEqual(export.export_image((downloader, "k", 1), USER, 7, 7000, tmp), "b.wxgf")   # để bộ xử lý thôi thử


class ImageRetryProcessorTest(WeChatBase):
    def setUp(self):
        super().setUp()
        self.processor = self.make_processor(images=True)
        (self.store.dir / "incoming").mkdir(parents=True, exist_ok=True)

    def images(self):
        return sorted((row["body"], bool(row.get("media"))) for row in self.store.rows_after(0)[0])

    def test_an_image_still_missing_is_offered_again_until_it_decodes_then_remembered(self):
        self.now = 1_793_000_100.0   # cùng thời với giờ tin của msg()
        self.db.feed = [msg(1, 1000, "", "图片", fp="a" * 16)]
        self.poll()
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["known_fp"], {USER: {"1:1000": "a" * 16}})   # không giải lại mỗi 10 giây
        self.now += wc.MISSING_RETRY
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["known_fp"], {})   # còn thiếu ảnh: sau 1 phút quên fp, cửa sổ sau gửi lại
        (self.store.dir / "incoming" / "a.jpg").write_bytes(JPEG)
        self.db.window = [msg(1, 1000, "", "图片", image="a.jpg", window=True, fp="a" * 16)]
        self.poll()
        self.poll()   # ảnh đã lấy (file incoming đã chuyển vào kho): cửa sổ không ảnh không đè `media`
        self.assertEqual(self.db.requests[-1][1]["known_fp"], {USER: {"1:1000": "a" * 16}})
        self.assertEqual(self.images(), [("Ảnh WeChat", True)])
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 2)

    def test_first_read_after_start_carries_the_seven_day_image_pass_until_it_succeeds_with_a_key(self):
        deep = lambda: self.db.requests[-1][1]["deep_image_hours"]  # noqa: E731
        self.db.fail = 3
        self.poll()
        self.assertEqual(deep(), wc.DEEP_IMAGE_HOURS)
        self.db.fail = None
        self.db.image_keys = False
        self.now += 3600   # qua thời gian lùi sau lỗi
        self.poll()
        self.assertEqual(deep(), wc.DEEP_IMAGE_HOURS)   # lượt lỗi không tính: làm lại
        self.poll()
        self.assertEqual(deep(), wc.DEEP_IMAGE_HOURS)   # chưa có khóa thì tiến trình con bỏ qua lượt sâu: giữ tới khi có khóa
        self.db.image_keys = True
        self.poll()
        self.assertEqual(deep(), wc.DEEP_IMAGE_HOURS)
        self.poll()
        self.assertEqual(deep(), 0)
        self.processor = self.make_processor(images=True)   # agent chạy lại
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["deep_image_hours"], wc.DEEP_IMAGE_HOURS)
        self.processor = self.make_processor()   # không bật ảnh: không bao giờ có lượt sâu
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["deep_image_hours"], 0)

    def test_two_timed_out_seven_day_passes_are_dropped_so_text_never_stays_stuck(self):
        self.db.fail = 3   # lỗi khác (mở DB…) không phải do lượt 7 ngày: không tính
        self.poll()
        self.db.fail = subprocess.TimeoutExpired("py", 60)
        for _ in range(2):
            self.now += 3600
            self.poll()
            self.assertEqual(self.db.requests[-1][1]["deep_image_hours"], wc.DEEP_IMAGE_HOURS)
        self.db.fail = None
        self.now += 3600
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["deep_image_hours"], 0)

    def test_a_seven_day_pass_cut_short_by_the_time_budget_continues_while_it_makes_progress(self):
        self.now = 1_793_000_100.0 + 2 * 86400   # tin của msg() đã cũ 2 ngày: chỉ lượt 7 ngày còn thấy
        (self.store.dir / "incoming" / "a.jpg").write_bytes(jpeg(1280, 720))
        self.processor.known = {wc.message_id(USER, 1, 1000): wc.trace(wc.convert(msg(1, 1000, "", "图片"))[0])}
        self.db.window = [msg(1, 1000, "", "图片", image="a.jpg", window=True, deep=True, fp="a" * 16)]
        self.db.end_extra = {"image_budget_hit": True, "images": 1}
        self.poll()
        self.assertEqual(self.images(), [("Ảnh WeChat", True)])
        self.db.window, self.db.end_extra = [], {"image_budget_hit": True, "images": 0}
        self.poll()
        request = self.db.requests[-1][1]
        self.assertEqual(request["deep_image_hours"], wc.DEEP_IMAGE_HOURS)   # còn dở, có tiến: làm tiếp
        self.assertEqual(request["known_fp"], {USER: {"1:1000": "a" * 16}})   # phần đã giải được nhớ cả 7 ngày, không giải lại
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["deep_image_hours"], 0)   # hết giờ mà không giải thêm được ảnh nào: thôi
        self.assertEqual(self.db.requests[-1][1]["known_fp"], {})   # xong lượt 7 ngày: nhớ `fp` lại theo cửa sổ thường

    def incoming(self, name, data):
        (self.store.dir / "incoming" / name).write_bytes(data)

    def test_a_thumbnail_is_retried_every_ten_minutes_and_replaced_only_by_a_larger_version(self):
        self.now = 1_793_000_100.0
        known = lambda: self.db.requests[-1][1]["known_fp"]  # noqa: E731
        self.incoming("t.jpg", jpeg(180, 102))   # cỡ ảnh thu nhỏ của WeChat
        self.db.feed = [msg(1, 1000, "", "图片", image="t.jpg", fp="a" * 16)]
        self.poll()
        self.poll()
        self.assertEqual(known(), {USER: {"1:1000": "a" * 16}})   # có ảnh rồi: không giải lại mỗi 10 giây
        self.now += wc.SMALL_RETRY + 1
        self.poll()
        self.assertEqual(known(), {})   # sau 10 phút quên `fp`: tiến trình con giải lại, tìm bản lớn hơn
        self.incoming("lon.jpg", jpeg(1280, 720))
        self.db.window = [msg(1, 1000, "", "图片", image="lon.jpg", window=True, fp="a" * 16)]
        self.poll()
        self.db.window = []
        self.now += wc.SMALL_RETRY + 1
        self.poll()
        self.assertEqual(known(), {USER: {"1:1000": "a" * 16}})   # bản lớn: nhớ luôn
        self.incoming("vua.jpg", jpeg(640, 360))   # bản nhỏ hơn bản đang có (ảnh gốc bị dọn chẳng hạn): không lùi
        self.db.window = [msg(1, 1000, "", "图片", image="vua.jpg", window=True, fp="a" * 16)]
        self.poll()
        rows = self.store.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 2)
        final = self.store.rows_after(0)[0][0]
        self.assertEqual(self.store.media_quality(final["media"][0]), (True, 1280 * 720))
        self.assertEqual(len(list((self.store.dir / "media").iterdir())), 2)   # bản bị bỏ không thành file mồ côi
        self.assertEqual(list((self.store.dir / "incoming").iterdir()), [])

    def test_a_half_downloaded_image_never_beats_a_whole_one_and_is_replaced_when_whole(self):
        self.now = 1_793_000_100.0
        cut = jpeg(1280, 720)[:-2]   # WeChat còn đang ghi file: đầu file đủ kích thước, thiếu `FF D9`
        self.assertEqual(wc.quality(cut), (False, 1280 * 720))
        self.incoming("t.jpg", jpeg(180, 102))
        self.db.feed = [msg(1, 1000, "", "图片", image="t.jpg", fp="a" * 16)]
        self.poll()
        self.incoming("cut.jpg", cut)
        self.db.window = [msg(1, 1000, "", "图片", image="cut.jpg", window=True, fp="a" * 16)]
        self.poll()   # ảnh trọn (dù nhỏ) thắng ảnh dở: giữ nguyên
        self.assertEqual(self.store.media_quality(self.store.rows_after(0)[0][0]["media"][0]), (True, 180 * 102))
        self.incoming("lon.jpg", jpeg(1280, 720))
        self.db.window = [msg(1, 1000, "", "图片", image="lon.jpg", window=True, fp="a" * 16)]
        self.poll()
        self.assertEqual(self.store.media_quality(self.store.rows_after(0)[0][0]["media"][0]), (True, 1280 * 720))
        # Chưa có ảnh nào thì ảnh dở vẫn hơn không có, và được thử lại sau 10 phút để lấy bản trọn.
        self.incoming("cut2.jpg", jpeg(800, 600)[:-2])
        self.db.feed = [msg(2, 2000, "", "图片", image="cut2.jpg", fp="b" * 16)]
        self.poll()
        self.assertEqual(self.processor.retry_at[(USER, 2, 2000)], self.now + wc.SMALL_RETRY)

    def test_a_read_error_retries_in_a_minute_and_a_failed_delete_keeps_the_image(self):
        self.now = 1_793_000_100.0
        self.db.feed = [msg(1, 1000, "", "图片", image="khong-co.jpg", fp="a" * 16)]   # file biến mất / đang bị khóa khi đọc
        self.poll()
        self.assertEqual(self.processor.retry_at[(USER, 1, 1000)], self.now + wc.MISSING_RETRY)
        self.incoming("a.jpg", jpeg(1280, 720))
        self.db.window = [msg(1, 1000, "", "图片", image="a.jpg", window=True, fp="a" * 16)]
        real_unlink = Path.unlink

        def locked(path, *args, **kwargs):   # phần mềm diệt virus đang giữ file trong incoming/
            if path.name == "a.jpg":
                raise PermissionError(32, "file đang bị giữ")
            return real_unlink(path, *args, **kwargs)

        with unittest.mock.patch.object(Path, "unlink", locked):
            self.poll()
        self.assertEqual(self.images(), [("Ảnh WeChat", True)])

    def test_heic_or_video_bytes_are_not_taken_as_an_image(self):
        self.incoming("a.heic", b"\x00\x00\x00\x18ftypheic" + bytes(64))
        self.db.feed = [msg(1, 1000, "", "图片", image="a.heic", fp="a" * 16)]
        self.poll()
        self.assertEqual(self.images(), [("Ảnh WeChat (chưa đọc được)", False)])
        self.assertNotIn((USER, 1, 1000), self.processor.retry_at)   # giải ra mà không dùng được: thôi thử

    def test_a_decoded_file_that_is_not_a_usable_image_stops_the_retries(self):
        self.now = 1_793_000_100.0
        self.db.feed = [msg(1, 1000, "", "图片", fp="a" * 16)]
        self.poll()
        self.incoming("x.wxgf", b"wxgf-khong-chuyen-duoc")   # upstream không có ffmpeg: ra file .wxgf
        self.db.window = [msg(1, 1000, "", "图片", image="x.wxgf", window=True, fp="a" * 16)]
        self.poll()
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["known_fp"], {USER: {"1:1000": "a" * 16}})
        self.assertEqual(self.images(), [("Ảnh WeChat (chưa đọc được)", False)])
        self.assertFalse((self.store.dir / "media").exists() and any((self.store.dir / "media").iterdir()))

    def test_the_deep_pass_never_imports_a_message_for_the_first_time(self):
        self.incoming("a.jpg", JPEG)
        self.db.window = [msg(9, 9000, "", "图片", image="a.jpg", window=True, deep=True)]   # tin lần đọc đầu đã cố ý bỏ
        self.poll()
        self.assertEqual(self.store.rows_after(0), ([], 0))

    def test_a_reread_without_the_key_never_overwrites_a_decoded_image_and_the_cursor_still_moves(self):
        (self.store.dir / "incoming" / "a.jpg").write_bytes(JPEG)
        self.db.feed = [msg(1, 1000, "", "图片", image="a.jpg")]
        self.poll()
        self.processor.cursors = {}   # con trỏ mất (state bị xóa) đúng lúc không có khóa: đọc lại từ đầu, ảnh không có
        self.db.feed = [msg(1, 1000, "", "图片"), msg(2, 2000, "tin sau")]
        self.poll()
        self.assertEqual(self.images(), [("tin sau", False), ("Ảnh WeChat", True)])
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 2)
        self.assertEqual(self.processor.cursors[USER]["sort_seq"], 2000)


class RealChildImageTest(WeChatBase):
    """Đường thật: bộ xử lý + `Session` (tiến trình con thật `wechat_export.py serve`, chạy bằng `-I`) + pilot giả có `wechatauto.media`
    giả. Phần thật được kiểm: suy khóa từ kvcomm và mẫu `.dat` V2 (bộ mã của repo nạp theo đường dẫn trong tiến trình con), thử lại
    ảnh ở lượt cửa sổ khi khóa có muộn, ảnh mới, và tiến trình con chết rồi tạo lại vẫn có khóa."""

    PILOT = (
        "import json, os, sys, types\n"
        "HERE = os.path.dirname(os.path.abspath(__file__))\n"
        "class MediaDownloader:\n"
        "    def __init__(self, db):\n"
        "        self.db = db\n"
        "    def _derive_cfg_key(self):\n"
        "        return None\n"
        "    def download_image(self, username, local_id, save_dir=None, aes_key=None, xor_key=None, tier=None):\n"
        "        with open(os.path.join(HERE, 'expected.json'), encoding='utf-8') as f:\n"
        "            if [aes_key, xor_key] != json.load(f):\n"
        "                return None\n"
        "        path = os.path.join(save_dir, 'anh-%d.jpg' % local_id)\n"
        "        with open(path, 'wb') as f:\n"
        "            f.write(b'\\xff\\xd8\\xff\\xe0wechat-jpeg-%d' % local_id)\n"
        "        return path\n"
        "media = types.ModuleType('wechatauto.media')\n"
        "media.MediaDownloader = MediaDownloader\n"
        "package = types.ModuleType('wechatauto')\n"
        "package.media = media\n"
        "sys.modules['wechatauto'], sys.modules['wechatauto.media'] = package, media\n"
        "class Db:\n"
        "    wxid, account_dir = WXID_VALUE, ACCOUNT_VALUE\n"
        "    def rows(self):\n"
        "        with open(os.path.join(HERE, 'rows.json'), encoding='utf-8') as f:\n"
        "            return json.load(f)\n"
        "    def get_groups(self):\n"
        "        return [{'username': USER_VALUE, 'name': 'Nhóm', 'members': [1]}]\n"
        "    def get_messages(self, username, limit=20, offset=0):\n"
        "        return list(reversed(self.rows()))[offset:offset + limit]\n"
        "    def get_new_messages(self, username, since_seq=0, limit=200):\n"
        "        return [row for row in self.rows() if row['sort_seq'] > since_seq][:limit]\n"
        "    def get_message_row(self, user, local_id, local_type=None):\n"
        "        same = sorted((row for row in self.rows() if row['local_id'] == local_id), key=lambda row: row['sort_seq'])\n"
        "        return same[-1] if same else None   # như upstream: local_id lặp giữa các mảnh thì lấy sort_seq lớn nhất\n"
        "    def nickname_map(self, refresh=False):\n"
        "        return {'wxid_a': 'Khách A'}\n"
        "def open_database():\n"
        "    return Db()\n"
    )

    def setUp(self):
        super().setUp()
        self.wx = Path(self.tmp.name) / "wx"
        account = wechat_dirs(self.wx, code=None)   # mẫu `.dat` có sẵn nhưng chưa có kvcomm: chưa suy được khóa
        self.pilot = Path(self.tmp.name) / "pilot"
        self.pilot.mkdir()
        source = self.PILOT.replace("WXID_VALUE", repr(WXID)).replace("ACCOUNT_VALUE", repr(str(account))).replace("USER_VALUE", repr(USER))
        (self.pilot / "db_adapter.py").write_text(source, encoding="utf-8")
        (self.pilot / "expected.json").write_text(json.dumps([GOOD_KEY, int(CODE) & 0xFF]), encoding="utf-8")
        self.rows = []
        env = unittest.mock.patch.dict(os.environ, {"APPDATA": str(self.wx / "appdata")})   # tiến trình con thừa hưởng
        env.start()
        self.addCleanup(env.stop)
        self.session = wc.Session()
        self.addCleanup(self.session.stop)
        self.processor = self.make_processor(images=True, run=self.session, python=sys.executable, pilot=str(self.pilot))

    def add_image(self, local_id, sort_seq=None):
        self.rows.append({"local_id": local_id, "type": "图片", "sender_id": 5, "sender_username": "wxid_a", "content": "<msg><img/></msg>",
                          "create_time": int(time.time()) - 60, "sort_seq": sort_seq or local_id * 1000})
        self.rows.sort(key=lambda row: row["sort_seq"])
        (self.pilot / "rows.json").write_text(json.dumps(self.rows), encoding="utf-8")

    def test_two_shards_with_the_same_local_id_never_swap_images(self):
        wechat_dirs(self.wx, samples=())   # có khóa ngay từ đầu
        self.add_image(1, sort_seq=1000)   # mảnh DB cũ
        self.add_image(1, sort_seq=5000)   # mảnh DB mới, local_id đếm lại từ 1
        self.poll()
        rows = self.store.rows_after(0)[0]
        self.assertEqual(sorted((row["body"], bool(row.get("media"))) for row in rows),
                         [("Ảnh WeChat", True), ("Ảnh WeChat (chưa đọc được)", False)])
        decoded = [row for row in rows if row.get("media")]
        self.assertEqual(decoded[0]["message_id"], wc.message_id(USER, 1, 5000))   # ảnh thuộc đúng tin mới, tin cũ không nhận nhầm

    def images(self):
        return sorted((row["body"], bool(row.get("media"))) for row in self.store.rows_after(0)[0])

    def test_late_key_then_new_image_then_a_restarted_child_all_decode(self):
        self.add_image(1)
        self.poll()
        self.assertEqual(self.images(), [("Ảnh WeChat (chưa đọc được)", False)])
        wechat_dirs(self.wx, samples=())   # kvcomm có sau (WeChat đăng nhập lại…): lượt thử lại kế tiếp bổ sung, không cần chạy lại serve
        self.now += wc.MISSING_RETRY   # tin thiếu ảnh được thử lại mỗi phút
        self.poll()
        self.assertEqual(self.images(), [("Ảnh WeChat", True)])
        self.add_image(2)
        self.poll()
        self.assertEqual(self.images(), [("Ảnh WeChat", True)] * 2)
        self.session.proc.kill()
        self.session.proc.wait(10)
        self.add_image(3)
        self.poll()   # Session tạo tiến trình con mới: khóa suy lại từ đầu
        self.assertEqual(self.images(), [("Ảnh WeChat", True)] * 3)
        self.assertEqual(len(self.store.log.read_text(encoding="utf-8").splitlines()), 4)   # ảnh 1 hai dòng (thiếu, rồi bổ sung)
        self.assertEqual(len(list((self.store.dir / "media").iterdir())), 3)
        self.assertEqual(list((self.store.dir / "incoming").iterdir()), [])

    def test_the_sender_repair_runs_alone_and_the_seven_day_pass_after_it_still_decodes_old_photos(self):
        """Review #583: lượt sửa người gửi và lượt ảnh 7 ngày chung một yêu cầu (hoặc lượt sửa nhớ `fp` của ảnh còn thiếu) thì lượt
        7 ngày coi ảnh cũ là đã xong và tắt. Nay lượt sửa đi riêng trước, không nhớ `fp` ngoài cửa sổ 6 giờ."""
        old = int(time.time()) - 48 * 3600   # ngoài cửa sổ 6 giờ, trong 7 ngày
        self.rows = [{"local_id": i, "type": "图片", "sender_id": 5, "sender_username": "wxid_a", "content": "<msg><img/></msg>",
                      "create_time": old + i, "sort_seq": i * 1000} for i in (1, 2, 3)]
        (self.pilot / "rows.json").write_text(json.dumps(self.rows), encoding="utf-8")
        self.poll()   # chưa có khóa: ba tin ảnh vào kho, thiếu ảnh, người gửi theo kết quả tra (sai)
        self.assertEqual(self.images(), [("Ảnh WeChat (chưa đọc được)", False)] * 3)
        for row in self.rows:   # nội dung thật có tiền tố của người gửi đúng
            row["content"] = "wxid_dung1:\n<msg><img/></msg>"
        (self.pilot / "rows.json").write_text(json.dumps(self.rows), encoding="utf-8")
        saved = json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))
        saved.pop("sender_rule", None)   # kho do bản cũ ghi
        (self.state / "wechat.json").write_text(json.dumps(saved), encoding="utf-8")
        wechat_dirs(self.wx, samples=())   # có khóa
        self.processor = self.make_processor(images=True, run=self.session, python=sys.executable, pilot=str(self.pilot))   # chạy lại agent
        self.poll()
        self.assertEqual((self.processor.resend_sent, self.processor.deep_sent), (True, False))
        self.assertEqual({row["sender_id"] for row in self.store.rows_after(0)[0]}, {wc.sender_id("wxid_dung1")})
        self.poll()
        self.assertEqual((self.processor.resend_sent, self.processor.deep_sent), (False, True))
        self.assertEqual(self.images(), [("Ảnh WeChat", True)] * 3)   # lượt 7 ngày vẫn giải đủ ảnh cũ
        self.assertEqual({row["sender_id"] for row in self.store.rows_after(0)[0]}, {wc.sender_id("wxid_dung1")})



TRAY = "Qt51514WxTrayIconMessageWindowClass"


class WeChatAppTest(unittest.TestCase):
    """Phân loại theo đúng số đo trên máy thật 22/11/2026 (tiến trình chính, tiến trình con Weixin, cửa sổ khay)."""

    LOGGED = ((100, 4, "Weixin.exe"), (101, 100, "Weixin.exe"), (102, 100, "crashpad_handler.exe"), (103, 100, "WeChatAppEx.exe"))
    LOGIN = ((200, 4, "Weixin.exe"), (202, 200, "crashpad_handler.exe"), (203, 200, "WeChatAppEx.exe"))

    def test_states_from_processes_and_windows(self):
        self.assertEqual(app.classify([], []), app.CLOSED)
        self.assertEqual(app.classify([(9, 4, "WeixinUpdate.exe")], []), app.UPDATE)   # 06:07 ngày 22/11: chỉ còn trình cập nhật
        self.assertEqual(app.classify(self.LOGIN, [(200, "Qt51514QWindowIcon")]), app.LOGIN)   # "Confirm on Phone"
        self.assertEqual(app.classify(self.LOGGED, []), app.LOGGED_IN)   # có tiến trình con Weixin (wxutility…)
        main_only = [(100, 4, "WEIXIN.EXE")]
        self.assertEqual(app.classify(main_only, [(100, TRAY)]), app.LOGGED_IN)   # cửa sổ khay, tên exe không phân biệt hoa thường
        self.assertEqual(app.classify(main_only, [(100, "Qt6QWindowIcon")]), app.LOGIN)
        self.assertEqual(app.classify(main_only, [(555, TRAY)]), app.LOGIN)   # khay của tiến trình khác không tính

    def test_two_wechats_one_logged_in_is_logged_in(self):
        self.assertEqual(app.classify(self.LOGGED + self.LOGIN, [(200, "Qt51514QWindowIcon")]), app.LOGGED_IN)
        self.assertEqual(app.classify(self.LOGIN + ((300, 4, "Weixin.exe"),), []), app.LOGIN)

    def test_never_raises_and_reports_unknown(self):
        with unittest.mock.patch.object(app.sys, "platform", "linux"):
            self.assertEqual(app.state(), app.UNKNOWN)
        with unittest.mock.patch.object(app.sys, "platform", "win32"),                 unittest.mock.patch.object(app, "list_processes", side_effect=OSError("hỏng")):
            self.assertEqual(app.state(), app.UNKNOWN)
        with unittest.mock.patch.object(app.sys, "platform", "win32"),                 unittest.mock.patch.object(app, "list_processes", return_value=self.LOGIN),                 unittest.mock.patch.object(app, "list_windows", return_value=[]) as windows:
            self.assertEqual(app.state(), app.LOGIN)
        windows.assert_called_once_with({200})


class AppStatusTest(WeChatBase):
    def setUp(self):
        super().setUp()
        self.now = 1_793_000_100.0
        self.value = "logged_in"
        self.processor = self.make_processor(images=True, app=lambda: self.value)

    def status(self):
        return status_file.compose(None, self.now, "abc", 1, LiveSync(self.src), {"wechat": self.poll()}, None, None,
                                   ("attached", "2026-11-20T08:00:00+07:00"))["processors"]["wechat"]

    def test_app_state_and_since_reach_status_and_survive_an_agent_restart(self):
        first = self.status()
        self.assertEqual((first["app"], first["images"]), ("logged_in", "ok"))
        self.value = "closed"
        self.now += 5   # chưa tới 30 giây: chưa xem lại
        self.assertEqual(self.status()["app"], "logged_in")
        self.now += wc.APP_EVERY
        closed = self.status()
        self.assertEqual(closed["app"], "closed")
        self.assertNotEqual(closed["app_since"], first["app_since"])
        self.processor = self.make_processor(images=True, app=lambda: self.value)   # agent chạy lại: mốc không mất
        self.now += 120
        self.assertEqual((self.status()["app"], self.status()["app_since"]), ("closed", closed["app_since"]))

    def test_image_key_state_follows_the_end_line_and_only_when_images_are_on(self):
        self.db.image_keys = False
        self.assertEqual(self.status()["images"], "no_key")
        self.db.image_keys = True
        self.assertEqual(self.status()["images"], "ok")
        self.processor = self.make_processor(app=lambda: self.value)   # tắt ảnh: không có trường `images`
        self.assertNotIn("images", self.status())

    def test_dry_run_does_not_write_the_marks_and_status_keeps_only_codes(self):
        self.processor = self.make_processor(images=True, app=lambda: "logged_in", dry_run=True)
        self.status()
        self.assertFalse((self.state / "wechat-app.json").exists())
        status = status_file.compose(None, self.now, "abc", 1, LiveSync(self.src),
                                     {"wechat": {"error": None, "app": "Đã đăng nhập!", "images": "ok", "images_since": "hôm nay"}}, None, None,
                                     ("attached", "2026-11-20T08:00:00+07:00"))["processors"]["wechat"]
        self.assertNotIn("app", status)
        self.assertEqual((status["images"], status["images_since"]), ("ok", None))


SENDER_NICKS = {"wxid_dung1": "Người gửi thật", "wxid_sai1": "Người khác"}


class SenderPrefixTest(unittest.TestCase):
    """22/11/2026: `SenderName2Id` chung của upstream lệch với WeChat 4 trên máy Zalo (0/61 tin khớp, 21 tin ra người khác): người
    gửi lấy từ tiền tố `<username>:` máy chủ WeChat ghi đầu tin."""


    def row(self, content, looked_up="wxid_sai1", sender_id=7, kind="文本"):
        return {"local_id": 1, "sort_seq": 1000, "create_time": 1, "type": kind, "sender_id": sender_id, "sender_username": looked_up,
                "content": content}

    def test_the_prefix_wins_over_a_wrong_lookup_and_is_stripped(self):
        item = export.record(SENDER_NICKS, USER, self.row("wxid_dung1:\nThu 5 triệu"), None, None)
        self.assertEqual((item["sender"], item["sender_name"], item["content"]), ("wxid_dung1", "Người gửi thật", "Thu 5 triệu"))
        item = export.record(SENDER_NICKS, USER, self.row("wxid_dung1:\nThu 5 triệu", looked_up=""), None, None)   # tra không ra ai
        self.assertEqual((item["sender"], item["content"]), ("wxid_dung1", "Thu 5 triệu"))
        photo = export.record(SENDER_NICKS, USER, self.row("wxid_dung1:\n<msg><img/></msg>", kind="图片"), None, None)
        self.assertEqual(photo["sender"], "wxid_dung1")   # tin ảnh cũng có tiền tố: đúng người gửi
        self.assertIsNone(export.stale_key(self.row("wxid_dung1:\nx"), SENDER_NICKS))
        self.assertEqual(export.stale_key(self.row("wxid_moi9:\nx"), SENDER_NICKS), ("name", "wxid_moi9"))

    def test_a_first_line_that_only_looks_like_an_id_never_becomes_the_sender(self):
        item = export.record(SENDER_NICKS, USER, self.row("KH0001:\nthu 5tr", looked_up="wxid_dung1"), None, None)
        self.assertEqual((item["sender"], item["content"]), ("wxid_dung1", "KH0001:\nthu 5tr"))
        own = export.record(SENDER_NICKS, USER, self.row("wxid_dung1:\nthu", looked_up="", sender_id=2), None, None)
        self.assertEqual((own["is_self"], own["sender"], own["content"]), (True, "", "wxid_dung1:\nthu"))   # tin của mình giữ nguyên

    def test_resend_hours_reread_old_rows_once_flagged_so_only_existing_rows_change(self):
        db = ExportTest.Db([(USER, NAME)], total=5)
        lines = []
        with unittest.mock.patch.object(export, "emit", lines.append), \
                unittest.mock.patch.object(export.time, "time", return_value=1_793_000_000.0 + 30 * 24 * 3600):
            export.cmd_read(db, {"groups": {USER: {"sort_seq": 5000, "tail": [5]}}, "window_hours": 6})
            self.assertEqual([line["kind"] for line in lines], ["end"])   # tin cũ hơn 6 giờ: không đọc lại
            lines.clear()
            export.cmd_read(db, {"groups": {USER: {"sort_seq": 5000, "tail": [5]}}, "window_hours": 6, "resend_hours": 400 * 24})
        messages = [line for line in lines if line["kind"] == "message"]
        self.assertEqual(len(messages), 5)
        self.assertTrue(all(line.get("resend") and line.get("deep") and line.get("window") for line in messages))


class SenderResendProcessorTest(WeChatBase):
    def test_an_upgraded_store_rereads_once_and_fixes_senders_of_rows_already_on_the_web(self):
        self.db.feed = [msg(1, 1000, "tin chữ", sender="wxid_sai1", name="Người khác"),
                        msg(2, 2000, "", "图片", sender="wxid_sai1", name="Người khác")]
        self.processor = self.make_processor(images=True)
        (self.store.dir / "incoming").mkdir(exist_ok=True)
        (self.store.dir / "incoming" / "a.jpg").write_bytes(JPEG)
        self.db.feed[1]["image"] = "a.jpg"
        self.poll()
        saved = json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))
        saved.pop("sender_rule", None)   # kho ghi bằng bản cũ (chưa có mốc)
        (self.state / "wechat.json").write_text(json.dumps(saved), encoding="utf-8")
        self.processor = self.make_processor(images=True)
        self.db.feed = []
        self.db.window = [msg(1, 1000, "tin chữ", sender="wxid_dung1", name="Người gửi thật", window=True, deep=True, resend=True),
                          msg(2, 2000, "", "图片", sender="wxid_dung1", name="Người gửi thật", window=True, resend=True),   # trong 6 giờ
                          msg(3, 3000, "tin chưa từng nhập", sender="wxid_dung1", window=True, deep=True, resend=True)]
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["resend_hours"], wc.RESEND_HOURS)
        rows = {row["message_id"]: row for row in self.store.rows_after(0)[0]}
        right = wc.sender_id("wxid_dung1")
        self.assertEqual(len(rows), 2)   # tin chưa từng nhập không vào kho
        self.assertEqual({row["sender_id"] for row in rows.values()}, {right})
        photo = next(row for row in rows.values() if row["message_type"] == 2)
        self.assertEqual((photo["body"], bool(photo.get("media"))), ("Ảnh WeChat", True))   # ảnh đang có giữ nguyên
        names = json.loads((self.store.dir / "users.json").read_text(encoding="utf-8"))
        self.assertEqual(names[right], "Người gửi thật")
        self.assertEqual(self.processor.total, 2)   # Máy chạy đếm tin, không đếm lần ghi lại người gửi
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["resend_hours"], 0)   # chỉ một lần
        self.assertEqual(json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))["sender_rule"], wc.SENDER_RULE)

    def test_a_fresh_store_never_needs_the_reread(self):
        self.poll()
        self.assertEqual(self.db.requests[-1][1]["resend_hours"], 0)

    def upgraded(self):
        self.db.feed = [msg(1, 1000, "tin")]
        self.poll()
        saved = json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))
        saved.pop("sender_rule", None)
        (self.state / "wechat.json").write_text(json.dumps(saved), encoding="utf-8")
        self.processor = self.make_processor(images=True)
        self.db.requests.clear()

    def test_the_repair_never_rides_with_the_seven_day_pass(self):
        self.upgraded()
        self.poll()
        self.poll()
        self.assertEqual([(request["resend_hours"] > 0, request["deep_image_hours"] > 0) for _, request in self.db.requests[:2]],
                         [(True, False), (False, True)])

    def test_a_repair_that_times_out_twice_stops_until_the_next_agent_start(self):
        self.upgraded()
        self.db.fail = subprocess.TimeoutExpired("wechat_export", 60)
        for _ in range(2):
            self.now += 3600   # qua thời gian lùi
            self.processor.step()
        self.db.fail = None
        self.now += 3600
        self.processor.step()
        self.assertEqual([request["resend_hours"] > 0 for _, request in self.db.requests], [True, True, False])
        self.assertLess(self.processor.sender_rule, wc.SENDER_RULE)   # chưa xong: lần chạy agent sau thử lại
        self.assertEqual(self.make_processor(images=True).request({USER: NAME})["resend_hours"], wc.RESEND_HOURS)

    def test_a_group_missing_during_the_repair_keeps_the_repair_pending(self):
        self.upgraded()
        self.db.end_extra = {"missing_groups": 1}
        self.poll()
        self.assertLess(self.processor.sender_rule, wc.SENDER_RULE)
        self.db.end_extra = {}
        self.poll()
        self.assertEqual(self.processor.sender_rule, wc.SENDER_RULE)
        self.assertEqual([request["resend_hours"] > 0 for _, request in self.db.requests], [True, True])


class ReadHealthTest(WeChatBase):
    """23/11/2026 (rà kỹ thuật): WeChat ngừng đọc mà status vẫn xanh — `last_ok_at` chỉ là nhịp tim, luồng đọc chết không ai dựng lại,
    `wechat-groups.json` hỏng thì thành "chưa chọn nhóm", chỉ mục hỏng bị ghi đè. Mỗi trường hợp phải ra mã lỗi hoặc tuổi lượt đọc."""

    def status(self, result):
        return status_file.compose(None, self.now, "abc", 1, LiveSync(self.src), {"wechat": result}, None, None,
                                   ("attached", "2026-11-20T08:00:00+07:00"))["processors"]["wechat"]

    def test_read_ok_at_is_the_last_successful_read_not_the_heartbeat(self):
        self.db.feed = [msg(1, 1000), msg(2, 2000)]
        first = self.status(self.poll())
        self.assertEqual(first["read_ok_at"], cursors.now_iso(self.now))
        self.assertEqual(first["newest_at"], cursors.now_iso(1_793_000_002))   # giờ của tin mới nhất, không phải giờ đọc
        self.assertEqual((first["groups"], first["read_every"]), (1, 10))
        read_at = first["read_ok_at"]
        self.db.fail = 1   # tiến trình con hỏng: đọc không được thì tuổi lượt đọc không đổi
        failed = self.status(self.poll())
        self.assertEqual((failed["error"], failed["read_ok_at"], failed["newest_at"]), ("child_failed", read_at, first["newest_at"]))
        # Luồng đọc đang treo: `error` null nên `last_ok_at` (nhịp tim) vẫn sáng theo từng nhịp, còn `read_ok_at` đứng yên.
        self.db.fail = None
        self.processor = self.make_processor(background=True)   # agent chạy lại: tuổi lượt đọc đọc từ `<state>`
        self.db.gate = threading.Event()
        self.addCleanup(self.db.gate.set)
        self.now += 60
        self.processor.step()   # bắt đầu luồng, treo ở cổng
        self.now += 600
        hung = self.status(self.processor.step())
        self.assertEqual((hung["error"], hung["last_ok_at"], hung["read_ok_at"]), (None, cursors.now_iso(self.now), read_at))

    def test_newest_message_time_only_moves_forward_and_survives_restart(self):
        self.db.feed = [msg(5, 5000)]
        self.poll()
        self.db.window = [msg(1, 1000, window=True)]   # tin cũ đọc lại trong cửa sổ không kéo "tin mới nhất" lùi
        result = self.poll()
        self.assertEqual(result["newest_at"], cursors.now_iso(1_793_000_005))
        again = self.make_processor()
        self.assertEqual(again.step()["newest_at"], cursors.now_iso(1_793_000_005))

    def test_a_reader_thread_that_raises_reports_thread_died_and_the_next_round_reads_again(self):
        self.db.feed = [msg(1, 1000)]
        self.db.fail = ValueError("lỗi lạ trong luồng đọc")
        result = self.poll()
        self.assertEqual((result["error"], result["messages"]), ("thread_died", 0))
        self.db.fail = None
        self.now += 60   # qua thời gian lùi
        recovered = self.poll()
        self.assertEqual((recovered["error"], recovered["action"], recovered["messages"]), (None, "poll", 1))

    def test_a_thread_that_exits_without_an_outcome_is_noticed_and_rebuilt(self):
        self.processor = self.make_processor(background=True)
        dead = threading.Thread(target=lambda: None)
        dead.start()
        dead.join()
        self.processor.thread = dead   # luồng chết mà `outcome` vẫn None: trước đây không bao giờ đọc lại, status vẫn xanh
        stopped = []
        self.processor.run = type("Run", (), {"__call__": lambda *args, **kw: (0, ""), "stop": lambda self_: stopped.append(1)})()
        self.now += 11
        self.assertEqual(self.processor.step()["error"], "thread_died")
        self.assertIsNone(self.processor.thread)
        self.assertEqual(stopped, [1])   # tiến trình con (nếu có) bị giết để lượt sau dựng lại từ đầu
        self.now += 60
        self.db.feed = [msg(1, 1000)]
        self.processor.run = self.db
        self.processor.step()   # dựng luồng mới
        self.processor.thread.join(10)
        self.assertEqual((self.processor.step()["error"], self.processor.total), (None, 1))

    def test_a_corrupt_groups_file_is_an_error_not_an_empty_selection(self):
        self.db.feed = [msg(1, 1000)]
        self.assertIsNone(self.poll()["error"])
        for broken in ("{không phải json", "[]", '{"groups": "x"}', ""):
            self.selection.path.write_text(broken, encoding="utf-8")
            result = self.poll()
            self.assertEqual(result["error"], "groups_corrupt", broken)
            self.assertEqual(self.db.requests[-1][1]["groups"].keys(), {USER}, broken)   # vẫn đọc nhóm đã chọn lần cuối
        self.selection.save({USER: NAME})
        self.assertIsNone(self.poll()["error"])
        # Chưa từng đọc được danh sách: không có nhóm nào để đọc, nhưng lỗi vẫn lộ ra.
        fresh = wc.Selection(self.selection.path)
        self.selection.path.write_text("{hỏng", encoding="utf-8")
        self.assertEqual((fresh.groups(), fresh.error), ({}, "groups_corrupt"))
        self.selection.path.unlink()
        self.assertEqual((fresh.groups(), fresh.error), ({}, None))   # không có file là chưa chọn nhóm nào: hợp lệ

    def test_a_corrupt_index_is_never_overwritten_and_blocks_the_round_until_fixed(self):
        self.db.feed = [msg(1, 1000)]
        self.poll()
        lines = lambda: len(self.store.log.read_text(encoding="utf-8").splitlines())  # noqa: E731
        cursor = lambda: json.loads((self.state / "wechat.json").read_text(encoding="utf-8"))["groups"][USER]["sort_seq"]  # noqa: E731
        self.assertEqual((lines(), cursor()), (1, 1000))
        good = self.store.users_path.read_bytes()
        self.store.users_path.write_bytes(b"{hong")
        self.db.feed.append(msg(2, 2000, "tin mới", sender="wxid_b", name="Khách B"))
        self.assertEqual(self.poll()["error"], "users_index_corrupt")
        self.assertEqual(self.store.users_path.read_bytes(), b"{hong")   # không ghi đè bằng phần mới
        self.assertEqual((lines(), cursor()), (1, 1000))                 # không nhập gì, con trỏ không tiến
        self.store.users_path.write_bytes(good)                          # khôi phục từ bản sao lưu
        self.now += 60
        self.assertIsNone(self.poll()["error"])
        self.assertEqual((lines(), cursor()), (2, 2000))
        self.store.media_path.write_bytes(b"[1, 2]")                     # JSON hợp lệ nhưng không phải từ điển: cũng hỏng
        self.db.feed.append(msg(3, 3000, "tin ba"))
        self.now += 60
        self.assertEqual(self.poll()["error"], "media_index_corrupt")
        self.assertEqual((self.store.media_path.read_bytes(), lines()), (b"[1, 2]", 2))
        self.store.media_path.unlink()
        self.now += 60
        self.assertEqual((self.poll()["error"], lines()), (None, 3))

    def test_a_corrupt_index_with_nothing_to_write_is_still_reported(self):
        self.store.users_path.write_bytes(b"{hong")
        self.assertEqual(self.poll()["error"], "users_index_corrupt")   # không cần có tin mới mới lộ ra

    def test_daily_counts_only_include_messages_settled_in_the_store_for_30_minutes(self):
        base = int(self.now) - 120
        self.db.feed = [msg(1, 1000, create_time=base), msg(2, 2000, create_time=base + 1)]
        today = wc.day_of(base)
        self.assertNotIn("daily", self.poll())   # vừa vào kho: chưa kịp lên gói, chưa tính
        self.now += wc.SETTLE + 100
        result = self.processor.step()
        self.assertEqual(result["daily"], {today: 2})
        self.assertEqual(self.status(result)["daily"], {today: 2})
        self.db.window = [msg(1, 1000, create_time=base, window=True)]   # đọc lại cùng mã: không đếm đôi, không đổi lúc vào kho
        self.now += 61
        self.assertEqual(self.processor.step()["daily"], {today: 2})
        self.processor = self.make_processor()   # agent chạy lại: tin trong log coi như đã vào kho từ trước
        self.assertEqual(self.processor.step()["daily"], {today: 2})
        self.selection.save({OTHER_USER: "Nhóm khác"})
        self.now += 61
        self.assertNotIn("daily", self.processor.step())   # nhóm đã bỏ chọn không đưa vào số đếm

    def test_status_keeps_only_well_formed_health_fields(self):
        status = self.status({"error": None, "read_ok_at": "hôm qua", "newest_at": "2026-11-23T09:00:00+07:00", "groups": True,
                              "read_every": 10, "daily": {"2026-11-23": 5, "hôm nay": 3, "2026-11-22": -1, "2026-11-21": True}})
        self.assertNotIn("read_ok_at", status)
        self.assertEqual((status["newest_at"], status["read_every"], status["daily"]), ("2026-11-23T09:00:00+07:00", 10, {"2026-11-23": 5}))
        self.assertNotIn("groups", status)


if __name__ == "__main__":
    unittest.main()
