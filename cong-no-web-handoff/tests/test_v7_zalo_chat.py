"""ZALO-CHAT-01: API đọc bản xuất chat Zalo theo trang (dữ liệu giả, không chạm bản xuất thật)."""

import hashlib
import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import test_zalo_web_bundle as fixture  # noqa: E402  (kho bịa dùng chung với test công cụ gói)
import v7_ledger_api as api  # noqa: E402
import v7_zalo_chat as chat  # noqa: E402
import zalo_web_bundle as bundle  # noqa: E402

OWNER = "a" * 64
KHACH = "b" * 64
BAN = "c" * 64
CONV_A = "1" * 64   # hội thoại với khách, 7 tin
CONV_B = "2" * 64   # hội thoại không tên, 1 tin
CONV_C = "3" * 64   # có trong conversations.json nhưng không có tin
CONV_D = "4" * 64   # chỉ có một tin của chủ tài khoản (để nhận ra chủ: người có mặt ở nhiều hội thoại nhất)
HEADERS = {"Host": "127.0.0.1:8780"}


def message(cid, mid, sender, stamp, body, message_type=1, status=None, attachment=None):
    return {"message_id": mid, "conversation_id": cid, "sender_id": sender, "timestamp": str(stamp),
            "server_time": str(stamp), "message_type": message_type, "status": status or (2 if sender == OWNER else 4),
            "body": body, "body_state": "decoded_basic_encryption", "attachment_metadata": attachment}


def media_bytes(store, media_id):
    mime, path = store.media_path(media_id)
    return mime, path.read_bytes()


def write_fixture(directory: Path) -> None:
    conversations = [
        {"conversation_id": CONV_A, "message_count": 7, "participant_ids": [OWNER, KHACH], "display_name": "Nguyễn Kim Mẫu", "name_status": "matched_storage_info_cache"},
        {"conversation_id": CONV_B, "message_count": 1, "participant_ids": [BAN], "display_name": None, "name_status": "unmatched"},
        {"conversation_id": CONV_C, "message_count": 0, "participant_ids": [OWNER, KHACH], "display_name": "Trống", "name_status": "matched_storage_info_cache"},
        {"conversation_id": CONV_D, "message_count": 1, "participant_ids": [OWNER, "d" * 64], "display_name": "Khách D", "name_status": "matched_storage_info_cache"},
    ]
    rows = [
        # Ghi lộn thứ tự thời gian để kiểm sắp xếp.
        message(CONV_A, "m3", KHACH, 1_700_000_003_000, "Em gửi hình cont nha", 2,
                attachment={"url_sha256": {"oriUrl": "f" * 64}, "media_items": [{"source_table": "image", "media_id": "e" * 64, "type": 1, "width": 1920, "height": 2560}]}),
        message(CONV_A, "m1", OWNER, 1_700_000_001_000, "Chào anh, tháng này còn 3 cont chưa thanh toán"),
        message(CONV_A, "m2", KHACH, 1_700_000_002_000, "Dạ để em xem lại"),
        message(CONV_A, "m4", OWNER, 1_700_000_004_000, "Anh gửi file công nợ", 19,
                attachment={"title": "cong-no.pdf", "url_sha256": {"href": "d" * 64}}),
        message(CONV_A, "m5", KHACH, 1_700_000_005_000, None),
        message(CONV_A, "m6", OWNER, 1_700_000_006_000, {"title": "sendBubbleMessage", "description": "Cuộc gọi", "params": "{\"duration\": 97}"}, 6,
                attachment={"title": "sendBubbleMessage"}),
        message(CONV_A, "m7", KHACH, 1_700_000_007_000, {"type": "7", "catId": 1, "id": 2}, 4, attachment={"type": "7"}),
        message(CONV_B, "x1", BAN, 1_700_000_000_500, "Khuyến mãi hôm nay"),
        message(CONV_D, "d1", OWNER, 1_700_000_000_400, "Anh ơi còn 1 cont"),
        {"conversation_id": "z" * 64, "message_id": "orphan", "sender_id": BAN, "timestamp": "1", "body": "ngoài danh sách"},
    ]
    (directory / "conversations.json").write_text(json.dumps(conversations, ensure_ascii=False), encoding="utf-8")
    with (directory / "messages.jsonl").open("w", encoding="utf-8") as stream:
        stream.write("không phải json\n")
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    (directory / "export-report.json").write_text(json.dumps({"status": "EXPORTED_WITH_GAPS"}), encoding="utf-8")


class ZaloChatStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        write_fixture(cls.dir)
        cls.store = chat.ChatStore(cls.dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_index_owner_and_summary(self):
        self.assertEqual(self.store.owner_id, OWNER)
        self.assertEqual(self.store.summary(), {
            "status": "EXPORTED_WITH_GAPS", "built_at": None, "media_count": 0,
            "conversation_count": 4, "message_count": 9, "named_conversations": 3,
            "owner_conversations": 2, "body_missing": 1, "attachment_matched": 1, "attachment_unmatched": 1,
            "skipped_lines": 2})

    def test_conversations_sorted_by_last_message_and_folded_search(self):
        rows = self.store.conversations()
        self.assertEqual([row["conversation_id"] for row in rows], [CONV_A, CONV_B, CONV_D, CONV_C])
        self.assertEqual(rows[0]["last_message_at"], 1_700_000_007_000)
        self.assertEqual(rows[0]["last_own_message_at"], 1_700_000_006_000)
        self.assertEqual((rows[1]["display_name"], rows[1]["last_own_message_at"], rows[3]["last_message_at"]), (None, None, None))
        self.assertEqual([row["display_name"] for row in self.store.conversations("KIM mau")], ["Nguyễn Kim Mẫu"])
        self.assertEqual([row["conversation_id"] for row in self.store.conversations("222")], [CONV_B])
        self.assertEqual(self.store.conversations("không có"), [])

    def test_messages_newest_page_first_chronological_inside(self):
        page = self.store.messages(CONV_A, 0, 3)
        self.assertEqual([m["message_id"] for m in page["messages"]], ["m5", "m6", "m7"])
        self.assertEqual((page["total"], page["pages"], page["has_older"], page["page"], page["limit"]), (7, 3, True, 0, 3))
        page = self.store.messages(CONV_A, 2, 3)
        self.assertEqual([m["message_id"] for m in page["messages"]], ["m1"])
        self.assertFalse(page["has_older"])
        self.assertEqual(self.store.messages(CONV_A, 3, 3)["messages"], [])
        self.assertEqual(self.store.messages(CONV_C)["total"], 0)

    def test_message_shape_body_and_attachment_states(self):
        rows = {m["message_id"]: m for m in self.store.messages(CONV_A, 0, 100)["messages"]}
        self.assertEqual((rows["m1"]["is_own"], rows["m1"]["status_label"], rows["m1"]["type_label"], rows["m1"]["body_kind"]), (True, "đã gửi", "Văn bản", "text"))
        self.assertEqual((rows["m2"]["is_own"], rows["m2"]["status_label"], rows["m2"]["attachment"]), (False, "đã nhận", None))
        self.assertEqual(rows["m3"]["attachment"]["state"], "matched")
        self.assertEqual(rows["m3"]["attachment"]["media_items"], [{"source_table": "image", "ext_type": None, "title": None, "file_size": None, "width": 1920, "height": 2560}])
        self.assertEqual(rows["m4"]["attachment"], {"state": "unmatched", "title": "cong-no.pdf", "url_count": 1, "media_items": []})
        self.assertEqual((rows["m5"]["body_kind"], rows["m5"]["body_text"]), ("missing", None))
        self.assertEqual((rows["m6"]["body_kind"], rows["m6"]["body_text"], rows["m6"]["attachment"]), ("card", "Cuộc gọi · thời lượng 97 giây", None))
        self.assertEqual((rows["m7"]["type_label"], rows["m7"]["body_text"], rows["m7"]["attachment"]), ("Sticker", None, None))
        for row in rows.values():
            self.assertNotIn("url_sha256", json.dumps(row))
            self.assertNotIn("path_hmac", json.dumps(row))

    def test_search_inside_conversation_is_accent_insensitive(self):
        page = self.store.messages(CONV_A, 0, 50, "CONT")
        self.assertEqual([m["message_id"] for m in page["messages"]], ["m1", "m3"])
        self.assertEqual((page["total"], page["query"]), (2, "CONT"))
        self.assertEqual(self.store.messages(CONV_A, 0, 50, "cuoc goi")["total"], 1)
        self.assertEqual(self.store.messages(CONV_A, 0, 50, "không có chữ này")["total"], 0)

    def test_unknown_conversation(self):
        with self.assertRaises(chat.ChatError) as caught:
            self.store.messages("9" * 64)
        self.assertEqual((caught.exception.status, caught.exception.code), (404, "CONVERSATION_NOT_FOUND"))

    def test_source_files_untouched(self):
        before = {name: (self.dir / name).read_bytes() for name in ("conversations.json", "messages.jsonl")}
        self.store.messages(CONV_A, 0, 50, "cont")
        self.store.conversations("vu")
        self.assertEqual({name: (self.dir / name).read_bytes() for name in before}, before)


class ZaloChatApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        write_fixture(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        chat._STORE, chat._STORE_DIR = None, None
        patcher = patch.object(chat, "EXPORT_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def get(self, path):
        return api.handle("GET", path, HEADERS, b"", None, port=8780, host="127.0.0.1", actor="server")

    def test_report_carries_the_zalo_heartbeat_codes_only(self):
        """Chat Zalo ghi "Zalo cập nhật (lần cuối) lúc …" theo nhịp tim máy Zalo như trang Thu chi; chỉ mã, giờ, số phút."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            with patch.dict(os.environ, {"WEBDEBIT_ZALO_AGENT_STATUS": str(path)}):
                _, report = self.get("/api/v7/zalo/report")
                self.assertEqual(report["zalo"], {"state": "missing", "at": None, "silent_minutes": None, "identity": None, "quiet_minutes": None})
                at = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 60))
                since = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 7 * 60))
                path.write_text(json.dumps({"schema": 1, "at": at, "processors": {"bundle": {"error": "secret_path_should_not_leak"}},
                                            "live_sync": {"identity": "waiting_for_zalo", "identity_since": since}}), encoding="utf-8")
                _, report = self.get("/api/v7/zalo/report")
        self.assertEqual(set(report["zalo"]), {"state", "at", "silent_minutes", "identity", "quiet_minutes"})
        self.assertEqual((report["zalo"]["state"], report["zalo"]["identity"], report["zalo"]["quiet_minutes"]), ("ok", "waiting_for_zalo", 7))
        self.assertNotIn("secret_path_should_not_leak", json.dumps(report))   # trang người dùng thường: không có lỗi bộ xử lý
        self.assertEqual(report["conversation_count"], 4)   # phần đếm của gói giữ nguyên

    def test_routes(self):
        status, report = self.get("/api/v7/zalo/report")
        self.assertEqual((status, report["conversation_count"], report["message_count"]), (200, 4, 9))
        status, body = self.get("/api/v7/zalo/conversations?q=m%E1%BA%ABu")
        self.assertEqual((status, body["total"], body["conversations"][0]["display_name"]), (200, 1, "Nguyễn Kim Mẫu"))
        status, body = self.get(f"/api/v7/zalo/messages?conversation={CONV_A}&page=1&limit=2&q=")
        self.assertEqual((status, [m["message_id"] for m in body["messages"]], body["total"]), (200, ["m4", "m5"], 7))
        status, body = self.get(f"/api/v7/zalo/messages?conversation={CONV_A}&q=cont")
        self.assertEqual((status, body["total"], body["limit"]), (200, 2, chat.DEFAULT_LIMIT))

    def test_errors(self):
        cases = {
            "/api/v7/zalo/messages": (400, "INVALID_REQUEST"),
            "/api/v7/zalo/messages?conversation=abc": (400, "INVALID_REQUEST"),
            f"/api/v7/zalo/messages?conversation={CONV_A}&page=-1": (400, "INVALID_REQUEST"),
            f"/api/v7/zalo/messages?conversation={CONV_A}&limit=0": (400, "INVALID_REQUEST"),
            f"/api/v7/zalo/messages?conversation={CONV_A}&limit=101": (400, "INVALID_REQUEST"),
            f"/api/v7/zalo/messages?conversation={CONV_A}&page=1&page=2": (400, "INVALID_REQUEST"),
            f"/api/v7/zalo/messages?conversation={CONV_A}&extra=1": (400, "INVALID_REQUEST"),
            "/api/v7/zalo/conversations?page=1": (400, "INVALID_REQUEST"),
            "/api/v7/zalo/report?x=1": (400, "INVALID_REQUEST"),
            f"/api/v7/zalo/messages?conversation={'9' * 64}": (404, "CONVERSATION_NOT_FOUND"),
            "/api/v7/zalo/other": (404, "NOT_FOUND"),
        }
        for path, expected in cases.items():
            with self.subTest(path=path), self.assertRaises(api.ApiError) as caught:
                self.get(path)
            self.assertEqual((caught.exception.status, caught.exception.code), expected)

    def test_unconfigured_and_missing_export(self):
        with patch.object(chat, "EXPORT_DIR", None), self.assertRaises(api.ApiError) as caught:
            self.get("/api/v7/zalo/report")
        self.assertEqual((caught.exception.status, caught.exception.code), (503, "ZALO_EXPORT_UNAVAILABLE"))
        with tempfile.TemporaryDirectory() as empty, patch.object(chat, "EXPORT_DIR", empty), self.assertRaises(api.ApiError) as caught:
            self.get("/api/v7/zalo/conversations")
        self.assertEqual(caught.exception.status, 503)
        self.assertIn("conversations.json", caught.exception.message)

    def test_page_and_assets_served(self):
        self.assertEqual(api.ASSETS["/zalo-chat.html"], ("zalo-chat.html", "text/html; charset=utf-8"))
        self.assertIn("/zalo-chat.js", api.ASSETS)
        self.assertIn("/zalo-chat.css", api.ASSETS)


class ZaloWebBundleStoreTest(unittest.TestCase):
    """ZALO-GROUP-01: đọc gói web do tools/zalo_web_bundle.py dựng (dựng thật từ kho bịa của test công cụ)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / "live-sync"
        self.src.mkdir()
        fixture.write_source(self.src)
        self.out = Path(self.tmp.name) / "web-bundle"
        self.source = bundle.Source(self.src)
        self.source.save_selection([fixture.GROUP])
        self.report = bundle.build(self.source, self.out, fetch=fixture.FakeCdn(), transcode=fixture.no_jxl, now=fixture.NOW)
        chat._STORE, chat._STORE_DIR = None, None
        chat._RELOAD.clear()
        chat._RELOAD["running"] = False
        self.addCleanup(setattr, chat, "_STORE", None)

    def test_extras_reach_the_api_and_bad_values_are_dropped(self):
        plain = chat.ChatStore(self.out)   # gói dựng khi chưa có chỉ mục phụ: trường mới rỗng
        old = {m["message_id"]: m for m in plain.messages(fixture.GROUP, 0, 100)["messages"]}["m1"]
        self.assertEqual((old["quote"], old["reactions"], old["sticker"], old["sender_avatar"], old["card"]), (None, [], None, None, None))
        fixture.write_extras(self.src)
        bundle.build(bundle.Source(self.src), self.out, fetch=fixture.FakeCdn(), transcode=fixture.no_jxl, now=fixture.NOW + 60)
        store = chat.ChatStore(self.out)
        rows = {m["message_id"]: m for m in store.messages(fixture.GROUP, 0, 100)["messages"]}
        parent = rows["m1"]
        self.assertEqual(rows["q1"]["quote"], {"message_id": "m1", "found": True, "sender_id": fixture.OWNER, "sender_name": parent["sender_name"],
                                               "type_label": "Văn bản", "deleted": False, "body_text": parent["body_text"][:chat.QUOTE_CHARS]})
        self.assertEqual(parent["reactions"], [{"emoji": "/-heart", "count": 2}, {"emoji": "/-strong", "count": 1}])
        self.assertEqual((rows["m7"]["deleted"], rows["m7"]["quote"], rows["m7"]["reactions"]), (True, None, []))
        self.assertEqual(rows["s1"]["sticker"], {"id": fixture.sha(fixture.STICKER_PNG), "mime": "image/png", "width": None, "height": None})
        self.assertEqual(media_bytes(store, rows["v1"]["media"][0]["id"]), ("audio/aac", fixture.VOICE_AAC))
        self.assertEqual([(rows[key]["card"], rows[key]["type_label"]) for key in ("c1", "c2")], [("link", "Liên kết"), ("poll", "Bình chọn")])
        self.assertEqual((rows["q1"]["sender_avatar"], parent["sender_avatar"]), (fixture.sha(fixture.AVATAR_JPEG), None))
        self.assertEqual(store.conversations()[0]["avatar"], fixture.sha(fixture.GROUP_PNG))
        bad = store.shape({"message_id": "x1", "conversation_id": fixture.GROUP, "message_type": 6, "card": "khac", "quote_id": "../m1",
                           "reactions": [{"emoji": "x" * 17, "count": 1}, {"emoji": "ok", "count": True}, "rác"], "sticker": "e" * 64})
        self.assertEqual((bad["card"], bad["type_label"], bad["quote"], bad["reactions"], bad["sticker"]), (None, "Cuộc gọi", None, [], None))
        self.assertIsNone(store.shape({"message_id": "x3", "conversation_id": fixture.GROUP, "card": ["link"], "reactions": {"emoji": "x"}})["card"])
        self.assertEqual(store.shape({"message_id": "x2", "conversation_id": fixture.GROUP, "quote_id": "khong-co"}, {})["quote"],
                         {"message_id": "khong-co", "found": False})

    def test_names_owner_media_and_album(self):
        store = chat.ChatStore(self.out)
        self.assertEqual(store.owner_id, fixture.OWNER)        # self_user của viewer, không đoán
        self.assertEqual(store.conversations()[0]["is_group"], True)
        rows = {m["message_id"]: m for m in store.messages(fixture.GROUP, 0, 100)["messages"]}
        self.assertEqual((rows["m1"]["sender_name"], rows["m1"]["is_own"], rows["m2"]["sender_name"]), ("Hào", True, "Vũ"))
        sha = hashlib.sha256(fixture.cdn_bytes(fixture.CDN_OK)).hexdigest()
        self.assertEqual(rows["m2"]["media"], [{"id": sha, "mime": "image/jpeg", "width": 1280, "height": 960}])
        self.assertEqual(rows["m2"]["album"], hashlib.sha256(b"77").hexdigest()[:16])
        self.assertEqual((rows["m5"]["media"], rows["m7"]["deleted"]), ([], True))
        self.assertEqual(media_bytes(store, sha), ("image/jpeg", fixture.cdn_bytes(fixture.CDN_OK)))
        self.assertEqual(store.summary()["media_count"], self.report["media_count"])
        for bad in ("0" * 64, "../media.json", sha.upper()):
            with self.subTest(bad=bad), self.assertRaises(chat.ChatError) as caught:
                store.media_path(bad)
            self.assertEqual(caught.exception.status, 404)

    def test_focus_returns_page_holding_message(self):
        store = chat.ChatStore(self.out)
        page = store.messages(fixture.GROUP, 0, 3, focus="m2")   # 8 tin: trang 0 = m6..m8, trang 1 = m3..m5, trang 2 = m1, m2
        self.assertEqual((page["page"], page["focus"], [m["message_id"] for m in page["messages"]]), (2, "m2", ["m1", "m2"]))
        self.assertEqual(store.messages(fixture.GROUP, 5, 3, focus="m8")["page"], 0)
        with self.assertRaises(chat.ChatError) as caught:
            store.messages(fixture.GROUP, 0, 3, focus="khong-co")
        self.assertEqual((caught.exception.status, caught.exception.code), (404, "MESSAGE_NOT_FOUND"))

    def test_api_message_param_and_media_route(self):
        base = f"/api/v7/zalo/messages?conversation={fixture.GROUP}&limit=3"
        status, body = chat.handle_get("/api/v7/zalo/messages", base.split("?", 1)[1] + "&message=m4", str(self.out))
        self.assertEqual((status, body["page"], body["focus"]), (200, 1, "m4"))
        for query in (base.split("?", 1)[1] + "&message=m4&q=cont", base.split("?", 1)[1] + "&message=a%2Fb"):
            with self.subTest(query=query), self.assertRaises(chat.ChatError) as caught:
                chat.handle_get("/api/v7/zalo/messages", query, str(self.out))
            self.assertEqual(caught.exception.status, 400)
        sha = hashlib.sha256(fixture.cdn_bytes(fixture.CDN_OK)).hexdigest()
        self.assertEqual(chat.handle_media(chat.MEDIA_PREFIX + sha, "", str(self.out))[0], "image/jpeg")
        with self.assertRaises(chat.ChatError):
            chat.handle_media(chat.MEDIA_PREFIX + sha, "x=1", str(self.out))

    def test_rebuilt_bundle_reloads_in_background(self):
        first = chat.get_store(str(self.out))
        self.assertEqual([row["conversation_id"] for row in first.conversations()], [fixture.GROUP])
        self.source.save_selection([fixture.GROUP, fixture.OTHER])
        bundle.build(self.source, self.out, fetch=fixture.FakeCdn(), transcode=fixture.no_jxl, now=fixture.NOW + 60)
        self.assertIs(chat.get_store(str(self.out)), first)   # đang lập chỉ mục mới: vẫn trả chỉ mục cũ
        for _ in range(200):
            if chat.get_store(str(self.out)) is not first:
                break
            time.sleep(0.01)
        self.assertEqual(sorted(row["conversation_id"] for row in chat.get_store(str(self.out)).conversations()),
                         [fixture.GROUP, fixture.OTHER])


class ZaloDeltaTest(unittest.TestCase):
    """ZALO-AGENT-01: gói gốc + messages-delta.jsonl (bản cuối theo message_id thắng, dòng xóa ẩn tin, đọc tới delta_bytes)."""

    SHA = "e" * 64

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data-20261120-0800"
        self.data.mkdir()
        write_fixture(self.data)
        self.delta = self.data / "messages-delta.jsonl"
        chat._STORE, chat._STORE_DIR = None, None
        chat._RELOAD.clear()
        chat._RELOAD["running"] = False
        self.addCleanup(setattr, chat, "_STORE", None)

    def write_report(self, **extra):
        report = {"status": "BUNDLED", "data_dir": self.data.name, "bundle_sha256": self.SHA, **extra}
        (self.root / "export-report.json").write_text(json.dumps(report), encoding="utf-8")

    def append(self, *rows) -> int:
        """Nối dòng vào delta, trả về số byte hợp lệ mới (đặt vào delta_bytes)."""
        with self.delta.open("ab") as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
        return self.delta.stat().st_size

    @staticmethod
    def ids(page):
        return [m["message_id"] for m in page["messages"]]

    def test_without_delta_behaves_as_before(self):
        self.write_report()
        store = chat.ChatStore(self.root)
        self.assertEqual((store.message_count, store.delta_offset), (9, 0))
        self.assertEqual(self.ids(store.messages(CONV_A, 0, 3)), ["m5", "m6", "m7"])

    def test_edit_replaces_and_deleted_line_shows_like_a_full_build(self):
        size = self.append(
            message(CONV_A, "m8", KHACH, 1_700_000_008_000, "Tin mới"),
            message(CONV_A, "m2", KHACH, 1_700_000_002_000, "Dạ em xem rồi, sửa lại"),   # tin sửa: cùng mã, thay cả dòng
            {"message_id": "m4", "conversation_id": CONV_A, "timestamp": "1700000004000", "deleted": True})
        self.write_report(delta_bytes=size, delta_lines=3, revision=7)
        store = chat.ChatStore(self.root)
        page = store.messages(CONV_A, 0, 100)
        self.assertEqual(self.ids(page), ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8"])   # m4 vẫn đúng chỗ, m8 thêm
        rows = {m["message_id"]: m for m in page["messages"]}
        self.assertEqual(rows["m2"]["body_text"], "Dạ em xem rồi, sửa lại")
        self.assertEqual((page["total"], store.message_count, store.conversations()[0]["last_message_at"]), (8, 10, 1_700_000_008_000))
        self.assertEqual(self.ids(store.messages(CONV_A, 0, 50, "sửa lại")), ["m2"])   # tìm chữ ở bản mới
        self.assertEqual(store.messages(CONV_A, 0, 50, "Dạ để em xem lại")["total"], 0)   # bản cũ không còn
        self.assertEqual(store.messages(CONV_A, 0, 50, focus="m4")["focus"], "m4")
        # Giống hệt bản dựng đầy đủ: cùng người gửi, giờ, loại, nhãn; không chữ, không đính kèm.
        full = self.root / "full"
        full.mkdir()
        write_fixture(full)
        gone = message(CONV_A, "m4", OWNER, 1_700_000_004_000, None, 19)
        gone["deleted"] = True
        gone["attachment_metadata"] = None
        text = (full / "messages.jsonl").read_text(encoding="utf-8").replace(
            next(line for line in (full / "messages.jsonl").read_text(encoding="utf-8").splitlines() if '"m4"' in line), json.dumps(gone, ensure_ascii=False))
        (full / "messages.jsonl").write_text(text, encoding="utf-8")
        expected = {m["message_id"]: m for m in chat.ChatStore(full).messages(CONV_A, 0, 100)["messages"]}["m4"]
        self.assertTrue(rows["m4"]["deleted"])
        self.assertEqual(rows["m4"], expected)

    def test_delete_then_readd_and_unknown_rows(self):
        size = self.append(
            {"message_id": "m1", "conversation_id": CONV_A, "timestamp": "1700000001000", "deleted": True},
            {"message_id": "khong-co", "conversation_id": CONV_A, "timestamp": "1700000000100", "deleted": True},   # chưa từng thấy bản trước
            {"message_id": "m1", "conversation_id": "z" * 64, "timestamp": "5", "body": "ngoài danh sách"},
            message(CONV_A, "m1", OWNER, 1_700_000_001_000, "Gửi lại sau khi xóa"))
        self.write_report(delta_bytes=size)
        store = chat.ChatStore(self.root)
        page = store.messages(CONV_A, 0, 100)
        rows = {m["message_id"]: m for m in page["messages"]}
        self.assertEqual((rows["m1"]["body_text"], rows["m1"]["deleted"]), ("Gửi lại sau khi xóa", False))
        self.assertEqual((rows["khong-co"]["deleted"], rows["khong-co"]["body_text"]), (True, None))
        self.assertEqual((page["total"], self.ids(page)[0]), (8, "khong-co"))

    def test_media_and_users_replaced_in_place_reach_new_delta_messages(self):
        png = b"PNG fake image bytes"
        sha = hashlib.sha256(png).hexdigest()
        (self.data / "users.json").write_text(json.dumps({"self_user": OWNER, "users": {KHACH: "Mẫu"}}), encoding="utf-8")
        (self.data / "media.json").write_text("{}", encoding="utf-8")
        self.write_report(delta_bytes=0)
        store = chat.get_store(str(self.root))
        self.assertEqual(store.messages(CONV_A, 0, 100)["messages"][-1]["sender_name"], "Mẫu")
        # PR-1 thay media.json và users.json tại chỗ rồi nối delta: tin mới có ảnh và người gửi mới.
        (self.data / "users.json").write_text(json.dumps({"self_user": OWNER, "users": {KHACH: "Mẫu", BAN: "Bạn mới"}}), encoding="utf-8")
        (self.data / "media.json").write_text(json.dumps({sha: {"mime": "image/png", "width": 2, "height": 3}}), encoding="utf-8")
        (self.root / "media").mkdir(exist_ok=True)
        (self.root / "media" / f"{sha}.png").write_bytes(png)
        picture = {**message(CONV_A, "m8", BAN, 1_700_000_008_000, None, 2), "media": [sha]}
        self.write_report(delta_bytes=self.append(picture), revision=2)
        with patch.object(chat.ChatStore, "_index", side_effect=AssertionError("không được lập lại chỉ mục")):
            self.assertIs(chat.get_store(str(self.root)), store)
        row = store.messages(CONV_A, 0, 100)["messages"][-1]
        self.assertEqual((row["message_id"], row["sender_name"], row["media"]), ("m8", "Bạn mới", [{"id": sha, "mime": "image/png", "width": 2, "height": 3}]))
        mime, found = chat.handle_media(chat.MEDIA_PREFIX + sha, "", str(self.root))
        self.assertEqual((mime, found.read_bytes()), ("image/png", png))
        self.assertEqual(store.summary()["media_count"], 1)
        # Chỉ đổi media.json/users.json mà delta không đổi (báo cáo đổi) cũng được đọc lại.
        (self.data / "users.json").write_text(json.dumps({"self_user": OWNER, "users": {BAN: "Bạn đổi tên"}}), encoding="utf-8")
        self.write_report(delta_bytes=self.delta.stat().st_size, revision=3)
        chat.get_store(str(self.root))
        self.assertEqual(store.messages(CONV_A, 0, 100)["messages"][-1]["sender_name"], "Bạn đổi tên")

    def test_report_change_detected_even_with_same_size_and_mtime(self):
        # Windows: hai lần ghi export-report.json liền nhau có thể cùng nhịp đồng hồ, cùng cỡ (revision 2 → 3).
        # Dấu (mtime, size) không đổi thì users.json thay tại chỗ không bao giờ được đọc lại (CI windows 20/11/2026).
        (self.data / "users.json").write_text(json.dumps({"self_user": OWNER, "users": {KHACH: "Tên cũ"}}), encoding="utf-8")
        self.write_report(delta_bytes=0, revision=2)
        report = self.root / "export-report.json"
        before = report.stat()
        store = chat.get_store(str(self.root))
        self.assertEqual(store.messages(CONV_A, 0, 100)["messages"][-1]["sender_name"], "Tên cũ")
        (self.data / "users.json").write_text(json.dumps({"self_user": OWNER, "users": {KHACH: "Tên mới"}}), encoding="utf-8")
        self.write_report(delta_bytes=0, revision=3)
        os.utime(report, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual((report.stat().st_mtime_ns, report.stat().st_size), (before.st_mtime_ns, before.st_size))
        chat.get_store(str(self.root))
        self.assertEqual(store.messages(CONV_A, 0, 100)["messages"][-1]["sender_name"], "Tên mới")

    def test_reads_exactly_delta_bytes(self):
        first = self.append(message(CONV_A, "m8", KHACH, 1_700_000_008_000, "Đủ dòng"))
        partial = json.dumps(message(CONV_A, "m9", KHACH, 1_700_000_009_000, "Ghi dở"), ensure_ascii=False)
        with self.delta.open("ab") as stream:
            stream.write(partial.encode("utf-8")[:20])   # dòng đang ghi dở, chưa có xuống dòng
        self.write_report(delta_bytes=first)
        store = chat.ChatStore(self.root)
        self.assertEqual((store.delta_offset, "m9" in store.latest, "m8" in store.latest), (first, False, True))
        # Dù tệp dài hơn delta_bytes (dòng m9 đã trọn nhưng báo cáo chưa nói tới), không đọc quá.
        with self.delta.open("ab") as stream:
            stream.write(partial.encode("utf-8")[20:] + b"\n")
        store.read_delta(first)
        self.assertEqual((store.delta_offset, "m9" in store.latest), (first, False))
        # delta_bytes cắt giữa dòng: chỉ lấy tới dòng trọn cuối.
        store.read_delta(self.delta.stat().st_size - 5)
        self.assertEqual((store.delta_offset, "m9" in store.latest), (first, False))
        store.read_delta(self.delta.stat().st_size)
        self.assertIn("m9", store.latest)

    def test_missing_delta_file_is_ignored(self):
        self.write_report(delta_bytes=500)
        store = chat.ChatStore(self.root)
        self.assertEqual((store.delta_offset, store.message_count), (0, 9))

    def test_report_change_reads_only_new_delta(self):
        self.write_report(delta_bytes=self.append(message(CONV_A, "m8", KHACH, 1_700_000_008_000, "Một")))
        store = chat.get_store(str(self.root))
        before = store.delta_offset
        with patch.object(chat.ChatStore, "_index", side_effect=AssertionError("không được lập lại chỉ mục")):
            self.write_report(delta_bytes=self.append(message(CONV_A, "m9", KHACH, 1_700_000_009_000, "Hai")), revision=8)
            self.assertIs(chat.get_store(str(self.root)), store)
        self.assertGreater(store.delta_offset, before)
        self.assertEqual(self.ids(store.messages(CONV_A, 0, 3)), ["m7", "m8", "m9"])
        self.assertEqual(store.report.get("revision"), 8)

    def test_new_bundle_hash_or_dir_reindexes(self):
        self.write_report(delta_bytes=self.append(message(CONV_A, "m8", KHACH, 1_700_000_008_000, "Một")))
        store = chat.ChatStore(self.root)
        for change in ({"bundle_sha256": "f" * 64}, {"data_dir": "data-20261121-0800"}, {"delta_bytes": 0}):
            with self.subTest(change=change):
                self.write_report(delta_bytes=self.delta.stat().st_size)
                report = json.loads((self.root / "export-report.json").read_text(encoding="utf-8"))
                (self.root / "export-report.json").write_text(json.dumps({**report, **change}), encoding="utf-8")
                self.assertFalse(store.refresh_delta())
        (self.root / "export-report.json").write_text(json.dumps({"status": "BUNDLED"}), encoding="utf-8")   # bản cũ, không có hash
        self.assertFalse(store.refresh_delta())

    def get(self, query):
        return chat.handle_get("/api/v7/zalo/messages", query, str(self.root))[1]

    def test_since_returns_everything_that_arrived_after_the_token_even_old_edits_and_late_messages(self):
        self.write_report(delta_bytes=self.append(message(CONV_A, "m8", KHACH, 1_700_000_008_000, "Tin mới")))
        first = self.get(f"conversation={CONV_A}&limit=3")
        token = first["token"]
        self.assertRegex(token, r"^[0-9a-f]{8}:[0-9]+$")
        again = self.get(f"conversation={CONV_A}&since={token}")
        self.assertEqual((again["messages"], again["token"], again["reset"], again["has_more"]), ([], token, False, False))
        # Máy Zalo mở lại sau khi tắt đêm: đọc bù tin có giờ cũ hơn tin mới nhất, sửa một tin cũ, xóa một tin cũ, và một tin của hội thoại khác.
        size = self.append(
            message(CONV_A, "m0", KHACH, 1_699_999_999_000, "Tin tới muộn, giờ rất cũ"),
            message(CONV_A, "m2", KHACH, 1_700_000_002_000, "Dạ em xem rồi, sửa lại"),
            {"message_id": "m4", "conversation_id": CONV_A, "timestamp": "1700000004000", "deleted": True},
            message(CONV_B, "x2", BAN, 1_700_000_009_000, "hội thoại khác"),
            message(CONV_A, "m9", OWNER, 1_700_000_009_500, "Tin mới nhất"))
        self.write_report(delta_bytes=size, revision=9)
        body = self.get(f"conversation={CONV_A}&since={token}")
        rows = {m["message_id"]: m for m in body["messages"]}
        self.assertEqual(sorted(rows), ["m0", "m2", "m4", "m9"])
        self.assertEqual([m["message_id"] for m in body["messages"]], ["m0", "m2", "m4", "m9"])   # theo giờ của tin
        self.assertEqual((rows["m2"]["body_text"], rows["m4"]["deleted"], rows["m4"]["body_text"]), ("Dạ em xem rồi, sửa lại", True, None))
        self.assertEqual((body["has_more"], body["reset"], body["total"], body["latest_ms"]), (False, False, 10, 1_700_000_009_500))
        self.assertEqual(self.get(f"conversation={CONV_A}&since={body['token']}")["messages"], [])
        self.assertEqual([m["message_id"] for m in self.get(f"conversation={CONV_B}&since={token}")["messages"]], ["x2"])

    def test_since_pages_through_a_long_catch_up_without_losing_or_repeating(self):
        self.write_report(delta_bytes=0)
        token = self.get(f"conversation={CONV_A}")["token"]
        rows = [message(CONV_A, f"n{i}", KHACH, 1_700_000_100_000 - i, f"Đọc bù {i}") for i in range(5)]
        self.write_report(delta_bytes=self.append(*rows), revision=3)
        seen = []
        for _ in range(5):
            body = self.get(f"conversation={CONV_A}&since={token}&limit=2")
            seen += [m["message_id"] for m in body["messages"]]
            token = body["token"]
            if not body["has_more"]:
                break
        self.assertEqual(sorted(seen), [f"n{i}" for i in range(5)])
        self.assertEqual(len(seen), 5)
        self.assertEqual(self.get(f"conversation={CONV_A}&since={token}")["messages"], [])

    def test_since_asks_for_a_reload_when_the_bundle_was_rebuilt(self):
        self.write_report(delta_bytes=self.append(message(CONV_A, "m8", KHACH, 1_700_000_008_000, "Một")))
        token = self.get(f"conversation={CONV_A}")["token"]
        other = "f" * 8 + ":" + token.split(":")[1]
        body = self.get(f"conversation={CONV_A}&since={other}")
        self.assertEqual((body["reset"], body.get("messages")), (True, None))
        self.assertEqual(body["token"], token)
        beyond = token.split(":")[0] + ":" + str(int(token.split(":")[1]) + 1000)
        self.assertTrue(self.get(f"conversation={CONV_A}&since={beyond}")["reset"])
        # Dựng lại: thư mục dữ liệu mới và gói mới, token cũ không còn khớp.
        self.write_report(delta_bytes=0, bundle_sha256="a" * 64)
        chat._STORE, chat._STORE_DIR = None, None
        self.assertTrue(self.get(f"conversation={CONV_A}&since={token}")["reset"])

    def test_since_token_is_strictly_validated(self):
        self.write_report(delta_bytes=0)
        good = self.get(f"conversation={CONV_A}")["token"]
        for bad in ("since=", "since=abc", "since=1234", "since=ABCDEF12:5", "since=abcdef12:", "since=abcdef12:-1", "since=abcdef12:5%C2%B2",
                    "since=abcdef12:1234567890123456", f"since={good}&page=1", f"since={good}&q=cont", f"since={good}&message=m1", "after=1"):
            with self.subTest(bad=bad), self.assertRaises(chat.ChatError) as caught:
                self.get(f"conversation={CONV_A}&{bad}")
            self.assertEqual(caught.exception.status, 400)
        with self.assertRaises(chat.ChatError) as caught:
            self.get(f"conversation={'9' * 64}&since={good}")
        self.assertEqual(caught.exception.status, 404)

    def test_broken_media_or_users_file_keeps_the_previous_one(self):
        sha = hashlib.sha256(b"x").hexdigest()
        (self.data / "users.json").write_text(json.dumps({"self_user": OWNER, "users": {KHACH: "Mẫu"}}), encoding="utf-8")
        (self.data / "media.json").write_text(json.dumps({sha: {"mime": "image/png", "width": 1, "height": 1}}), encoding="utf-8")
        self.write_report(delta_bytes=0)
        store = chat.get_store(str(self.root))
        self.assertEqual((len(store.media), store.user_names), (1, {KHACH: "Mẫu"}))
        (self.data / "users.json").write_text('{"users": {"b"', encoding="utf-8")          # đang ghi dở
        (self.data / "media.json").write_text("[1, 2]", encoding="utf-8")                  # không phải dict
        self.write_report(delta_bytes=self.append(message(CONV_A, "m8", KHACH, 1_700_000_008_000, "Một")), revision=2)
        self.assertIs(chat.get_store(str(self.root)), store)
        self.assertEqual((len(store.media), store.user_names, "m8" in store.latest), (1, {KHACH: "Mẫu"}, True))
        (self.data / "media.json").write_text("{}", encoding="utf-8")                      # dict rỗng hợp lệ: thay thật
        self.write_report(delta_bytes=self.delta.stat().st_size, revision=3)
        chat.get_store(str(self.root))
        self.assertEqual(len(store.media), 0)


class ZaloMediaRangeTest(unittest.TestCase):
    """Media của trang Chat qua HTTP thật: Range cho Safari iOS, gửi theo khúc, hạn tính theo khúc (23/11/2026)."""

    DATA = bytes(range(256)) * 4   # 1024 byte, mỗi byte nhận ra vị trí của mình
    SHA = "a" * 64
    EMPTY = "b" * 64
    BIG = "c" * 64
    VOICE = "d" * 64

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        write_fixture(self.root)
        (self.root / "media").mkdir()
        listed = {sha: {"mime": "video/mp4", "width": 2, "height": 2} for sha in (self.SHA, self.EMPTY, self.BIG)}
        listed[self.VOICE] = {"mime": "audio/aac", "width": None, "height": None}
        (self.root / "media.json").write_text(json.dumps(listed), encoding="utf-8")
        (self.root / "media" / f"{self.SHA}.mp4").write_bytes(self.DATA)
        (self.root / "media" / f"{self.EMPTY}.mp4").write_bytes(b"")
        (self.root / "media" / f"{self.VOICE}.aac").write_bytes(self.DATA[:100])
        patcher = patch.object(chat, "EXPORT_DIR", str(self.root))
        patcher.start()
        self.addCleanup(patcher.stop)
        chat._STORE, chat._STORE_DIR = None, None
        chat._RELOAD.clear()
        chat._RELOAD["running"] = False
        self.addCleanup(setattr, chat, "_STORE", None)

        class TrialHandler(api.Handler):
            runner = object()
            default_actor = "media-test"
            dev_actor_mode = True

            def setup(self):
                super().setup()
                # Bộ đệm gửi nhỏ để máy nào cũng chặn sendall khi client không đọc (Windows nhận trọn file lớn vào đệm hạt nhân).
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)

        self.server = api.ThreadingHTTPServer(("127.0.0.1", 0), TrialHandler)
        TrialHandler.port = self.server.server_port
        worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def get(self, sha, range_header=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            conn.request("GET", chat.MEDIA_PREFIX + sha, headers={"Range": range_header} if range_header else {})
            response = conn.getresponse()
            return response.status, {key.lower(): value for key, value in response.getheaders()}, response.read()
        finally:
            conn.close()

    def test_whole_file_declares_accept_ranges_and_keeps_the_old_guards(self):
        status, headers, body = self.get(self.SHA)
        self.assertEqual((status, body, headers["content-type"], headers["content-length"]), (200, self.DATA, "video/mp4", "1024"))
        self.assertEqual((headers["accept-ranges"], headers["x-content-type-options"], headers["cache-control"]),
                         ("bytes", "nosniff", "private, max-age=86400"))
        self.assertNotIn("content-range", headers)
        status, headers, body = self.get(self.VOICE)
        self.assertEqual((status, headers["content-type"], headers["accept-ranges"], len(body)), (200, "audio/aac", "bytes", 100))

    def test_one_range_gets_206_with_content_range(self):
        for header, (first, last) in (("bytes=0-1", (0, 1)), ("bytes=10-19", (10, 19)), ("bytes=1000-", (1000, 1023)),
                                      ("bytes=-24", (1000, 1023)),
                                      ("bytes=1000-5000", (1000, 1023)),   # cuối vượt cỡ: cắt về byte cuối
                                      ("bytes=-5000", (0, 1023)),          # đuôi dài hơn file: cả file
                                      ("bytes=0-", (0, 1023)), ("bytes=1023-1023", (1023, 1023)), ("Bytes= 5-6 ", (5, 6))):
            with self.subTest(header=header):
                status, headers, body = self.get(self.SHA, header)
                self.assertEqual((status, body), (206, self.DATA[first:last + 1]))
                self.assertEqual((headers["content-range"], headers["content-length"], headers["accept-ranges"]),
                                 (f"bytes {first}-{last}/1024", str(last - first + 1), "bytes"))
                self.assertEqual((headers["content-type"], headers["x-content-type-options"], headers["cache-control"]),
                                 ("video/mp4", "nosniff", "private, max-age=86400"))

    def test_range_outside_the_file_gets_416(self):
        for header in ("bytes=1024-", "bytes=2000-3000", "bytes=-0", "bytes=1024-2000"):
            with self.subTest(header=header):
                status, headers, body = self.get(self.SHA, header)
                self.assertEqual((status, headers["content-range"], headers["accept-ranges"], headers["x-content-type-options"]),
                                 (416, "bytes */1024", "bytes", "nosniff"))
                self.assertEqual(body, b"")

    def test_unusable_range_falls_back_to_whole_file(self):
        for header in ("bytes=0-1,5-9", "bytes=abc", "items=0-1", "bytes=5-2", "bytes=-", "bytes=", "0-1", "bytes=1-2-3", "bytes=²-5"):
            with self.subTest(header=header):
                status, headers, body = self.get(self.SHA, header)
                self.assertEqual((status, body, headers["accept-ranges"]), (200, self.DATA, "bytes"))
                self.assertNotIn("content-range", headers)

    def test_empty_file(self):
        status, headers, body = self.get(self.EMPTY)
        self.assertEqual((status, body, headers["content-length"], headers["accept-ranges"]), (200, b"", "0", "bytes"))
        for header in ("bytes=0-", "bytes=0-1", "bytes=-5"):
            with self.subTest(header=header):
                status, headers, body = self.get(self.EMPTY, header)
                self.assertEqual((status, headers["content-range"], body), (416, "bytes */0", b""))

    def test_only_listed_regular_files_are_served(self):
        for sha in ("e" * 64, "../media.json", self.SHA.upper()):
            with self.subTest(sha=sha):
                for header in (None, "bytes=0-1"):
                    self.assertEqual(self.get(sha, header)[0], 404)
        target = self.root / "outside.bin"
        target.write_bytes(b"secret")
        try:
            (self.root / "media" / f"{self.BIG}.mp4").symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("không tạo được symlink trên máy này")
        for header in (None, "bytes=0-1"):
            self.assertEqual(self.get(self.BIG, header)[0], 404)

    def test_sends_in_chunks_without_reading_the_whole_file(self):
        real = Path.read_bytes

        def guarded(path):   # chỉ file trong media/ bị cấm đọc trọn; file báo cáo của gói vẫn đọc được
            if path.parent.name == "media":
                raise AssertionError("không được đọc cả file vào RAM")
            return real(path)

        with patch.object(Path, "read_bytes", guarded):
            status, _, body = self.get(self.SHA, "bytes=2-3")
            self.assertEqual((status, body), (206, self.DATA[2:4]))
            self.assertEqual(self.get(self.SHA)[2], self.DATA)

    def test_deadline_is_rearmed_for_every_chunk(self):
        # Xác định trên mọi máy (Windows nhận trọn file lớn vào đệm hạt nhân nên không tự tái hiện được cú cắt 5 giây):
        # mỗi khúc phải được đặt lại hạn socket, và kết nối trả về hạn thường sau khi gửi xong.
        calls = []

        class Recorder:
            def __init__(self, sock):
                self.sock = sock

            def settimeout(self, value):
                calls.append(value)
                self.sock.settimeout(value)

            def __getattr__(self, name):
                return getattr(self.sock, name)

        finished = threading.Event()

        class Watched(self.server.RequestHandlerClass):
            def setup(self):
                super().setup()
                self.connection = Recorder(self.connection)

            def finish(self):
                try:
                    super().finish()
                finally:
                    finished.set()

        self.server.RequestHandlerClass = Watched
        chunks = 5
        (self.root / "media" / f"{self.BIG}.mp4").write_bytes(b"\0" * (api.MEDIA_CHUNK * chunks - 7))
        self.assertEqual(len(self.get(self.BIG)[2]), api.MEDIA_CHUNK * chunks - 7)
        # Client đọc đủ thân trước khi luồng máy chủ chạy xong khối finally: chờ luồng xử lý kết thúc rồi mới đọc `calls`.
        self.assertTrue(finished.wait(10))
        self.assertEqual(calls[0], 5)                                   # _request: hạn đọc yêu cầu
        self.assertEqual(calls[1:-1], [api.MEDIA_CHUNK_SECONDS] * chunks)   # một lần cho mỗi khúc
        self.assertEqual(calls[-1], api.Handler.timeout)                # rồi về hạn thường cho yêu cầu kế tiếp
        self.assertGreaterEqual(api.MEDIA_CHUNK_SECONDS, 5)

    def test_total_time_cap_stops_a_trickling_client(self):
        # Mỗi khúc có 15 giây nên client ~4 KB/s giữ luồng hàng giờ; trần tổng = max(60 giây, cỡ / 32 KB/s) cắt kết nối.
        chunks = 10
        size = api.MEDIA_CHUNK * chunks
        (self.root / "media" / f"{self.BIG}.mp4").write_bytes(b"\1" * size)
        self.assertEqual(max(api.MEDIA_MIN_SECONDS, size / api.MEDIA_MIN_RATE), 60)
        ticks = iter(range(0, 10_000, 20))   # đồng hồ giả: mỗi lần hỏi trôi thêm 20 giây (lần đầu = lúc bắt đầu gửi)
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            with patch.object(api, "MEDIA_CLOCK", lambda: next(ticks)):
                conn.request("GET", chat.MEDIA_PREFIX + self.BIG)
                response = conn.getresponse()
                self.assertEqual((response.status, response.getheader("Content-Length")), (200, str(size)))
                with self.assertRaises(http.client.IncompleteRead) as cut:
                    response.read()
        finally:
            conn.close()
        self.assertEqual(len(cut.exception.partial), 2 * api.MEDIA_CHUNK)   # hạn 60 giây: còn 40 và 20 giây cho hai khúc đầu, khúc 3 hết hạn

    def test_slow_reader_still_gets_the_whole_file_after_five_seconds(self):
        # Hạn 5 giây của _request từng áp cho cả lần sendall: file lớn trên mạng chậm bị cắt. Giờ hạn tính theo từng khúc.
        big = os.urandom(1024) * (24 * 1024)   # 24 MB, lớn hơn mọi bộ đệm socket loopback
        (self.root / "media" / f"{self.BIG}.mp4").write_bytes(big)
        sock = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=30)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
            sock.sendall(f"GET {chat.MEDIA_PREFIX}{self.BIG} HTTP/1.1\r\nHost: 127.0.0.1:{self.server.server_port}\r\n\r\n".encode())
            time.sleep(6.5)   # không đọc một byte nào, lâu hơn hạn 5 giây cũ
            received = b""
            while b"\r\n\r\n" not in received:
                received += sock.recv(65536)
            head, _, first = received.partition(b"\r\n\r\n")
            self.assertIn(b" 200 ", head.split(b"\r\n")[0])
            body = bytearray(first)
            while len(body) < len(big):
                chunk = sock.recv(1 << 20)
                if not chunk:
                    break
                body += chunk
        finally:
            sock.close()
        self.assertEqual(len(body), len(big))
        self.assertEqual(hashlib.sha256(body).digest(), hashlib.sha256(big).digest())


if __name__ == "__main__":
    unittest.main()
