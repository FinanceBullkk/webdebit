"""ZALO-CHAT-01: API đọc bản xuất chat Zalo theo trang (dữ liệu giả, không chạm bản xuất thật)."""

import hashlib
import json
import sys
import tempfile
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


def write_fixture(directory: Path) -> None:
    conversations = [
        {"conversation_id": CONV_A, "message_count": 7, "participant_ids": [OWNER, KHACH], "display_name": "Nguyễn Hoàng Vũ", "name_status": "matched_storage_info_cache"},
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
        self.assertEqual([row["display_name"] for row in self.store.conversations("HOANG vu")], ["Nguyễn Hoàng Vũ"])
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

    def test_routes(self):
        status, report = self.get("/api/v7/zalo/report")
        self.assertEqual((status, report["conversation_count"], report["message_count"]), (200, 4, 9))
        status, body = self.get("/api/v7/zalo/conversations?q=ho%C3%A0ng")
        self.assertEqual((status, body["total"], body["conversations"][0]["display_name"]), (200, 1, "Nguyễn Hoàng Vũ"))
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
        self.assertEqual(store.media_file(sha), ("image/jpeg", fixture.cdn_bytes(fixture.CDN_OK)))
        self.assertEqual(store.summary()["media_count"], self.report["media_count"])
        for bad in ("0" * 64, "../media.json", sha.upper()):
            with self.subTest(bad=bad), self.assertRaises(chat.ChatError) as caught:
                store.media_file(bad)
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


if __name__ == "__main__":
    unittest.main()
