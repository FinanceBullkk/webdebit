"""NHAT-KY-01: luồng nền đọc PR đã merge từ GitHub, tóm tắt ngày bằng Claude, route GET /api/v7/nhat-ky. Dữ liệu giả, không gọi mạng."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402
import v7_nhat_ky as nk  # noqa: E402


class Response(io.BytesIO):
    def __init__(self, body, status=200, etag=None):
        super().__init__(json.dumps(body).encode())
        self.status, self.headers = status, {"ETag": etag} if etag else {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def pr(number, title, merged="2026-11-20T02:15:00Z"):
    return {"number": number, "title": title, "merged_at": merged}


class FakeNet:
    """GitHub và Claude giả: danh sách PR, chi tiết từng PR, câu trả lời Claude."""

    def __init__(self, listing, answer=None):
        self.listing, self.answer, self.calls, self.etag = listing, answer, [], '"v1"'

    def __call__(self, request, timeout):
        url = request.full_url
        self.calls.append(url)
        if url.startswith("https://api.anthropic.com/"):
            self.prompt = json.loads(request.data)
            return Response({"content": [{"type": "text", "text": json.dumps(self.answer, ensure_ascii=False)}]})
        if "/pulls?" in url:
            if request.headers.get("If-none-match") == self.etag:
                raise HTTPError(url, 304, "Not Modified", {}, None)
            return Response(self.listing, etag=self.etag)
        number = int(url.rsplit("/", 1)[1])
        return Response({"number": number, "additions": 10 * number, "deletions": number, "changed_files": 2})


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.empty_seed = Path(self.dir.name) / "khong-co-seed.json"

    def journal(self, net, key="k", seed=None, clock=lambda: 10_000.0):
        return nk.Journal(self.dir.name, opener=net, clock=clock, key=lambda: key, seed=seed or self.empty_seed)

    def test_lanes_and_noise(self):
        self.assertEqual(nk.lane_of("Đội xe: phiếu chi mới"), "doi-xe")
        self.assertEqual(nk.lane_of("Debit note v4: một trang A4"), "gia")
        self.assertEqual(nk.lane_of("Tổng quan: lọc chéo"), "quan-ly")
        self.assertEqual(nk.lane_of("Máy đối soát mỗi giờ"), "may")
        self.assertEqual(nk.lane_of("test: chờ đúng tín hiệu"), "an-toan")
        self.assertEqual(nk.lane_of("Sổ khách: ô Đơn giá"), "gia")   # luật trước thắng: "giá"
        self.assertEqual(nk.lane_of("Sổ khách: phiếu thu gọn"), "so-khach")
        for title in ("Nhật ký triển khai: X lên hao", "docs(deploys): nhật ký", "Bump the pip group", "chore(deps): bump x",
                      "Record BANG-GIA-03 deployment on hao"):
            self.assertTrue(nk.NOISE.search(title), title)
        self.assertFalse(nk.NOISE.search("Đội xe: chốt chặng"))

    def test_poll_adds_merged_prs_skips_noise_then_uses_etag(self):
        net = FakeNet([pr(7, "Đội xe: phiếu chi mới"), pr(8, "Nhật ký triển khai: đội xe lên hao"),
                       {"number": 9, "title": "Chưa merge", "merged_at": None}],
                      answer={"headline": "Phiếu chi đội xe", "items": [["doi-xe", "Ghi phiếu chi xe trên web."]]})
        journal = self.journal(net)
        self.assertEqual(journal.poll_once(), 1)
        body = journal.view()
        self.assertTrue(body["available"])
        self.assertEqual(body["days"]["2026-11-20"]["changes"], [["#7", "Đội xe: phiếu chi mới", "doi-xe", 70, 7, 2, "09:15"]])
        self.assertEqual(body["days"]["2026-11-20"]["headline"], "Phiếu chi đội xe")   # giờ VN: 02:15Z là 09:15 ngày 20
        self.assertEqual(body["days"]["2026-11-20"]["items"], [["doi-xe", "Ghi phiếu chi xe trên web."]])
        self.assertEqual(json.loads(Path(self.dir.name, "store.json").read_text(encoding="utf-8"))["skip"], [8])
        self.assertIn("Đội xe: phiếu chi mới", net.prompt["messages"][0]["content"])
        # Nhịp sau: GitHub trả 304 nhờ ETag, không lấy chi tiết, không hỏi Claude lại (chưa quá 30 phút)
        net.calls.clear()
        self.assertEqual(journal.poll_once(), 0)
        self.assertEqual(len(net.calls), 1)
        if os.name == "posix":
            self.assertEqual(Path(self.dir.name, "store.json").stat().st_mode & 0o777, 0o600)

    def test_summary_rewritten_only_after_gap_and_bad_answers_dropped(self):
        now = [10_000.0]
        net = FakeNet([pr(7, "Sổ khách: phiếu thu gọn")], answer={"headline": "Phiếu thu", "items": [["so-khach", "Phiếu thu gọn hơn."]]})
        journal = self.journal(net, clock=lambda: now[0])
        journal.poll_once()
        net.listing = [pr(10, "Sổ khách: chọn vùng ô", "2026-11-20T03:00:00Z"), *net.listing]
        net.etag = '"v2"'
        net.answer = {"headline": "Chọn vùng ô", "items": [["khong-co-mang", "x"], ["so-khach", "Chọn vùng ô như Sheet."]]}
        journal.poll_once()   # mới 0 giây: chưa viết lại
        self.assertEqual(journal.view()["days"]["2026-11-20"]["headline"], "Phiếu thu")
        now[0] += nk.SUMMARY_GAP
        net.etag = '"v3"'
        net.listing = [pr(11, "Sổ khách: dán cả cột", "2026-11-20T04:00:00Z"), *net.listing]
        journal.poll_once()
        day = journal.view()["days"]["2026-11-20"]
        self.assertEqual((day["headline"], day["items"]), ("Chọn vùng ô", [["so-khach", "Chọn vùng ô như Sheet."]]))   # mảng lạ bị bỏ
        self.assertIsNone(nk._clean_summary({"headline": "x", "items": [["la", "y"]]}))
        self.assertIsNone(nk._clean_summary({"headline": 3, "items": []}))

    def test_without_key_no_claude_call_and_seed_is_loaded(self):
        seed = Path(self.dir.name) / "seed.json"
        seed.write_text(json.dumps({"prs": {"5": {"t": "Bảng giá theo tuyến", "l": "gia", "a": 1, "d": 0, "f": 1, "m": "2026-11-19 08:00"}},
                                    "skip": [6], "days": {"2026-11-19": {"headline": "Bảng giá", "items": [["gia", "Ghi giá theo tuyến."]]}},
                                    "meta": {"from": "2026-10-20", "highlights": [{"area": "gia", "title": "Giá"}], "next": ["Đội xe"]}}), encoding="utf-8")
        net = FakeNet([pr(5, "Bảng giá theo tuyến", "2026-11-19T01:00:00Z"), pr(6, "Bump x"), pr(12, "Sổ khách: phiếu thu")])
        journal = self.journal(net, key=None, seed=seed)
        self.assertEqual(journal.poll_once(), 1)   # chỉ PR 12; 5 đã có, 6 nằm trong danh sách bỏ
        self.assertFalse(any("anthropic" in url for url in net.calls))
        body = journal.view()
        self.assertEqual((body["from"], body["to"], body["next"]), ("2026-10-20", "2026-11-20", ["Đội xe"]))
        self.assertEqual(body["days"]["2026-11-19"]["headline"], "Bảng giá")
        self.assertEqual(body["days"]["2026-11-20"]["headline"], "")   # chưa có tóm tắt: trang hiện tên PR

    def test_rate_limit_waits_until_reset(self):
        net = Mock(side_effect=HTTPError("u", 403, "rate", {"X-RateLimit-Reset": "20000"}, None))
        journal = self.journal(net)
        with self.assertRaises(HTTPError):
            journal.poll_once()
        self.assertEqual(journal.next_allowed, 20000.0)
        self.assertEqual(journal.poll_once(), 0)   # chưa tới giờ mở lại: không gọi mạng
        self.assertEqual(net.call_count, 1)

    def test_route_and_page(self):
        journal = self.journal(FakeNet([pr(7, "Đội xe: phiếu chi mới")]), key=None)
        journal.poll_once()
        args = {"port": 8780, "host": "127.0.0.1", "actor": "nguoi-xem"}
        runner = Mock()
        with patch.object(nk, "journal", return_value=journal):
            status, body = api.handle("GET", "/api/v7/nhat-ky", {"Host": "127.0.0.1:8780"}, b"", runner, **args)
            self.assertEqual((status, list(body["days"])), (200, ["2026-11-20"]))
            with self.assertRaises(api.ApiError):
                api.handle("GET", "/api/v7/nhat-ky?x=1", {"Host": "127.0.0.1:8780"}, b"", runner, **args)
        runner.run.assert_not_called()
        self.assertEqual(api.ASSETS["/nhat-ky-cong-viec.html"][0], "nhat-ky-cong-viec.html")
        self.assertEqual(api.ASSETS["/nhat-ky-cong-viec-ui.js"][0], "nhat-ky-cong-viec-ui.js")

    def test_seed_shipped_with_app_is_clean(self):
        seed = json.loads(nk.SEED.read_text(encoding="utf-8"))
        self.assertGreater(len(seed["prs"]), 400)
        self.assertTrue(all(p["l"] in nk.LANES and not nk.NOISE.search(p["t"]) for p in seed["prs"].values()))
        self.assertEqual(seed["meta"]["from"], "2026-10-20")


if __name__ == "__main__":
    unittest.main()
