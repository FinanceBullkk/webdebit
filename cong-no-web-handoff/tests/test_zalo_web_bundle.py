"""ZALO-GROUP-01: gói web chat Zalo chỉ gồm group đã chọn (dữ liệu bịa, không chạm kho thật)."""

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import zalo_web_bundle as bundle  # noqa: E402

OWNER, KHACH, BAN = "a" * 64, "b" * 64, "c" * 64
GROUP = "1" * 64     # group của khách, được chọn
OTHER = "2" * 64     # group khác, chọn rồi bỏ
PRIVATE = "3" * 64   # chat riêng, không bao giờ chọn
JPEG_LOCAL = b"\xff\xd8\xff\xe0local-jpeg"
JXL_LOCAL = b"\xff\x0ajxl-bytes"
CDN_OK = "https://f1.photo.zdn.vn/ok.jpg"
CDN_BROKEN = "https://f2.photo.zdn.vn/gone.jpg"
CDN_OTHER = "https://f3.photo.zdn.vn/other.jpg"
CDN_JXL = "https://f9.photo.zdn.vn/jxl.jpg"
NOW = 1_793_500_000.0


def image(url, width=1280, height=960, album=None):
    params = {"width": width, "height": height, **({"group_layout_id": album} if album else {})}
    return {"title": "", "description": "", "oriUrl": url, "normalUrl": url, "thumbUrl": url, "params": json.dumps(params)}


def row(cid, mid, sender, stamp, body, message_type=1, client=None, **extra):
    return {"message_id": mid, "client_message_id": client or "cm-" + mid, "conversation_id": cid, "sender_id": sender,
            "recipient_id": OWNER, "source_candidate_id": "s" * 64, "timestamp": str(stamp), "server_time": str(stamp),
            "local_time": stamp, "message_type": message_type, "status": 2 if sender == OWNER else 4, "body": body,
            "body_state": "decoded_basic_encryption", "attachment_metadata": {"url_sha256": {"oriUrl": "9" * 64}}, **extra}


def write_source(directory: Path) -> None:
    (directory / "conversations.json").write_text(json.dumps([
        {"conversation_id": GROUP, "message_count": 8, "participant_ids": [OWNER, KHACH]},
        {"conversation_id": OTHER, "message_count": 2, "participant_ids": [OWNER, BAN]},
        {"conversation_id": PRIVATE, "message_count": 1, "participant_ids": [OWNER, BAN]}]), encoding="utf-8")
    (directory / "name-index.json").write_text(json.dumps({"items": {GROUP: "Nhóm Hoàng Vũ - công nợ", OTHER: "Nhóm Vận tải", PRIVATE: "Bạn riêng"}}, ensure_ascii=False), encoding="utf-8")
    (directory / "conv-meta.json").write_text(json.dumps({"conversations": {GROUP: {"is_group": True}, OTHER: {"is_group": True}, PRIVATE: {"is_group": False}}}), encoding="utf-8")
    (directory / "user-index.json").write_text(json.dumps({"self_user": OWNER, "users": {OWNER: "Hào", KHACH: "Vũ", BAN: "Người lạ"}}, ensure_ascii=False), encoding="utf-8")
    (directory / "revision.json").write_text(json.dumps({"revision": 87}), encoding="utf-8")
    store = directory / "media-store"
    store.mkdir()
    (store / ("e" * 64 + ".jpg")).write_bytes(JPEG_LOCAL)
    (store / ("f" * 64 + ".jxl")).write_bytes(JXL_LOCAL)
    (directory / "media-index.json").write_text(json.dumps({"items": {
        "e" * 64: {"client_message_id": "cm-local", "mime": "image/jpeg", "sha256": hashlib.sha256(JPEG_LOCAL).hexdigest(), "bytes": len(JPEG_LOCAL)},
        "f" * 64: {"client_message_id": "cm-jxl", "mime": "image/jxl", "sha256": hashlib.sha256(JXL_LOCAL).hexdigest(), "bytes": len(JXL_LOCAL)}}}), encoding="utf-8")
    rows = [
        row(GROUP, "m2", KHACH, 1_700_000_002_000, image(CDN_OK, album=77), 2),
        row(GROUP, "m1", OWNER, 1_700_000_001_000, "Anh ơi tháng 10 còn 3 cont chưa thanh toán"),
        row(GROUP, "m3", KHACH, 1_700_000_003_000, image("https://f9.photo.zdn.vn/local.jpg"), 2, client="cm-local"),
        row(GROUP, "m4", KHACH, 1_700_000_004_000, image(CDN_JXL), 2, client="cm-jxl"),
        row(GROUP, "m5", KHACH, 1_700_000_005_000, image("https://evil.example.com/x.jpg"), 2),
        row(GROUP, "m6", KHACH, 1_700_000_006_000, [{"title": "Bảng giá", "description": "https://link.example/gia", "href": "https://link.example/gia"}], 21),
        row(GROUP, "m7", KHACH, 1_700_000_007_000, "tin đã xóa", deleted=True),
        row(GROUP, "m8", KHACH, 1_700_000_008_000, image(CDN_BROKEN), 2),
        row(OTHER, "o1", BAN, 1_700_000_001_500, "Bí mật nhóm vận tải"),
        row(OTHER, "o2", BAN, 1_700_000_001_600, image(CDN_OTHER), 2),
        row(PRIVATE, "p1", BAN, 1_700_000_000_900, "Chuyện riêng tư tuyệt đối"),
    ]
    with (directory / "messages.jsonl").open("w", encoding="utf-8") as stream:
        stream.write("không phải json\n")
        for item in rows:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")


class FakeCdn:
    def __init__(self):
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url == CDN_BROKEN:
            raise bundle.BundleError("404")
        return cdn_bytes(url)


def cdn_bytes(url):
    return b"\xff\xd8\xff\xe0cdn:" + hashlib.sha256(url.encode()).digest()


def no_jxl(data):
    raise ImportError("pillow_jxl")


def snapshot(directory: Path) -> dict[str, bytes]:
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*")
            if path.is_file() and path.name != bundle.SELECTION}


def bundle_text(out: Path) -> str:
    return "\n".join(path.read_bytes().decode("utf-8", "replace") for path in out.rglob("*") if path.is_file())


class ZaloWebBundleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "live-sync"
        self.src.mkdir()
        write_source(self.src)
        self.out = Path(self.tmp.name) / "web-bundle"
        self.source = bundle.Source(self.src)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = bundle.main(["--source", str(self.src), *args])
        return code, output.getvalue()

    def build(self, cdn=None, **kwargs):
        return bundle.build(bundle.Source(self.src), self.out, fetch=cdn or FakeCdn(), transcode=no_jxl, now=kwargs.pop("now", NOW), **kwargs)

    def data(self, report):
        directory = self.out / report["data_dir"]
        messages = [json.loads(line) for line in (directory / "messages.jsonl").read_text(encoding="utf-8").splitlines()]
        return (json.loads((directory / "conversations.json").read_text(encoding="utf-8")),
                json.loads((directory / "users.json").read_text(encoding="utf-8")), messages,
                json.loads((directory / "media.json").read_text(encoding="utf-8")))

    def test_select_by_name_and_prefix(self):
        self.assertEqual(self.run_cli("add", "hoang vu")[0], 0)   # không dấu, một phần tên
        self.assertEqual(self.source.selection(), [GROUP])
        code, text = self.run_cli("add", "nhóm")                 # hai group khớp: không chọn bừa
        self.assertEqual(code, 1)
        self.assertIn("2 hội thoại khớp", text)
        self.assertEqual(self.run_cli("add", OTHER[:8])[0], 0)
        self.assertEqual(self.source.selection(), [GROUP, OTHER])
        self.assertEqual(self.run_cli("remove", "Nhóm Vận tải")[0], 0)
        self.assertEqual(self.source.selection(), [GROUP])
        code, text = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("[x]  11111111", text)
        self.assertNotIn("Bạn riêng", text)                      # chat riêng chỉ hiện khi --all
        self.assertIn("Bạn riêng", self.run_cli("list", "--all")[1])

    def test_build_requires_selection(self):
        code, text = self.run_cli("build", "--out", str(self.out), "--no-fetch")
        self.assertEqual(code, 2)
        self.assertIn("chưa chọn group", text)

    def test_only_chosen_group_and_no_urls(self):
        before = snapshot(self.src)
        self.source.save_selection([GROUP])
        report = self.build()
        conversations, users, messages, _ = self.data(report)
        self.assertEqual([row["conversation_id"] for row in conversations], [GROUP])
        self.assertEqual(conversations[0]["display_name"], "Nhóm Hoàng Vũ - công nợ")
        self.assertTrue(conversations[0]["is_group"])
        self.assertEqual([row["message_id"] for row in messages], ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8"])
        self.assertEqual(users, {"self_user": OWNER, "users": {OWNER: "Hào", KHACH: "Vũ"}})
        text = bundle_text(self.out)
        for secret in ("Bí mật", "riêng tư", "Người lạ", OTHER, PRIVATE, "http", "zdn.vn", "9" * 64, "cm-", "s" * 64):
            self.assertNotIn(secret, text)
        self.assertEqual(messages[0]["body"], "Anh ơi tháng 10 còn 3 cont chưa thanh toán")
        self.assertEqual(messages[1]["body"], {"title": "", "description": "", "width": 1280, "height": 960,
                                               "album": hashlib.sha256(b"77").hexdigest()[:16]})
        self.assertEqual(messages[5]["body"], [{"title": "Bảng giá"}])
        self.assertTrue(messages[6]["deleted"])
        self.assertNotIn("media", messages[6])
        self.assertEqual(snapshot(self.src), before)   # kho nguồn không đổi byte nào
        self.assertEqual(report["status"], "BUNDLED")
        self.assertEqual(report["message_count"], 8)

    def test_media_local_cdn_and_failures(self):
        self.source.save_selection([GROUP])
        cdn = FakeCdn()
        report = self.build(cdn)
        _, _, messages, media = self.data(report)
        by_id = {row["message_id"]: row for row in messages}
        local_sha = hashlib.sha256(JPEG_LOCAL).hexdigest()
        cdn_sha = hashlib.sha256(cdn_bytes(CDN_OK)).hexdigest()
        self.assertEqual(by_id["m3"]["media"], [local_sha])               # có ở máy: không tải
        self.assertEqual(by_id["m2"]["media"], [cdn_sha])
        self.assertEqual(media[cdn_sha], {"mime": "image/jpeg", "bytes": len(cdn_bytes(CDN_OK)), "width": 1280, "height": 960})
        self.assertEqual((self.out / "media" / (local_sha + ".jpg")).read_bytes(), JPEG_LOCAL)
        # JXL ở máy không đổi được (thiếu pillow-jxl): đếm lỗi rồi lấy bản JPEG của Zalo.
        self.assertEqual(by_id["m4"]["media"], [hashlib.sha256(cdn_bytes(CDN_JXL)).hexdigest()])
        for missing in ("m5", "m8"):
            self.assertNotIn("media", by_id[missing])
        self.assertEqual(cdn.calls, [CDN_BROKEN, CDN_JXL, CDN_OK])        # mới nhất trước; host lạ không bao giờ được gọi
        self.assertEqual((report["media_local"], report["media_fetched"], report["media_failed"], report["media_missing"]), (1, 2, 1, 2))
        cache = json.loads((self.out / bundle.CACHE).read_text(encoding="utf-8"))
        self.assertNotIn("http", json.dumps(cache))
        # Lượt sau: ảnh đã tải dùng lại, URL lỗi chưa đủ 7 ngày thì không gọi lại.
        again = FakeCdn()
        report = self.build(again, now=NOW + 86400)
        self.assertEqual(again.calls, [])
        self.assertEqual((report["media_cached"], report["media_missing"]), (2, 2))
        later = FakeCdn()
        self.build(later, now=NOW + 8 * 86400)
        self.assertEqual(later.calls, [CDN_BROKEN])

    def test_fetch_budget_leaves_pending(self):
        self.source.save_selection([GROUP])
        cdn = FakeCdn()
        report = self.build(cdn, max_fetch=0)
        self.assertEqual(cdn.calls, [])
        self.assertEqual(report["media_pending"], 3)
        # Một lượt tải: dành cho ảnh mới nhất (CDN của Zalo xóa ảnh cũ sau 2–3 tuần).
        cdn = FakeCdn()
        report = self.build(cdn, max_fetch=1, now=NOW + 60)
        self.assertEqual(cdn.calls, [CDN_BROKEN])
        self.assertEqual(report["media_pending"], 2)
        # Ảnh cũ hơn giới hạn: không gọi CDN (đằng nào cũng 404), tính là không còn.
        cdn = FakeCdn()
        report = self.build(cdn, max_age_days=30, now=NOW + 120)
        self.assertEqual(cdn.calls, [])
        self.assertEqual((report["media_pending"], report["media_missing"]), (0, 4))

    def test_unselecting_removes_group_from_bundle_now(self):
        self.source.save_selection([GROUP, OTHER])
        first = self.build()
        other_sha = hashlib.sha256(cdn_bytes(CDN_OTHER)).hexdigest()
        self.assertTrue((self.out / "media" / (other_sha + ".jpg")).is_file())
        self.source.save_selection([GROUP])
        second = self.build(now=NOW + 60)
        self.assertNotEqual(first["data_dir"], second["data_dir"])
        self.assertFalse((self.out / first["data_dir"]).exists())
        self.assertFalse((self.out / "media" / (other_sha + ".jpg")).exists())
        self.assertNotIn("Bí mật", bundle_text(self.out))
        # Cùng lựa chọn thì lượt trước được giữ cho server đang đọc dở; lượt thứ ba xóa lượt đầu.
        third = self.build(now=NOW + 120)
        self.assertTrue((self.out / second["data_dir"]).is_dir())
        fourth = self.build(now=NOW + 180)
        self.assertFalse((self.out / second["data_dir"]).exists())
        self.assertEqual(sorted(path.name for path in self.out.glob("data-*")), sorted([third["data_dir"], fourth["data_dir"]]))

    def test_clean_body(self):
        self.assertIsNone(bundle.clean_body(None))
        self.assertEqual(bundle.clean_body({"title": "sendBubbleMessage", "params": "{\"duration\": 97}", "href": "https://x"}),
                         {"title": "sendBubbleMessage", "duration": 97})
        self.assertEqual(bundle.clean_body({"type": "7", "id": 2, "catId": 1}), {})
        self.assertEqual(bundle.sniff(b"\x89PNG\r\n\x1a\nabc"), "image/png")
        self.assertIsNone(bundle.sniff(b"<html>"))
        self.assertFalse(bundle.allowed("http://f1.photo.zdn.vn/x.jpg"))   # chỉ https
        self.assertFalse(bundle.allowed("https://zdn.vn.evil.com/x.jpg"))


if __name__ == "__main__":
    unittest.main()
