"""Bộ câu hỏi mẫu của bot Zalo (ZALO-BOT-01 PR-3c): dựng câu và đáp án từ API giả, chấm câu trả lời, gom kết quả. Dữ liệu giả."""

import datetime as dt
import io
import json
import sys
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from zalo_bot import config, model, tools, webapi  # noqa: E402
from zalo_bot import eval as bot_eval  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=VN).timestamp()
ADMIN = config.User("1111", "chu@example.com", "admin")
DATA = {
    "/api/v7/customers": {"customers": [{"id": 7, "name": "KHACH A", "display_name": "Khách A"}, {"id": 9, "name": "Khách B"}]},
    "/api/v7/dashboard": {"as_of": "2026-11-22", "receivable": {"total_vnd": "395045000", "customers": 2}},
    "/api/v7/dashboard/debt": {"customers": [
        {"customer_id": 9, "outstanding_vnd": "45000", "overdue_vnd": "0", "last_receipt_date": "2026-11-02", "oldest_open_month": "2026-11-01"},
        {"customer_id": 7, "outstanding_vnd": "395000000", "overdue_vnd": "120500000", "last_receipt_date": "2026-10-20",
         "oldest_open_month": "2026-08-01"}]},
    "/api/v7/inbox": {"reconcile": {"checked_at": "2026-11-22T14:05:00+07:00", "matched_ids": [7], "customers": []}},
    "/api/v7/receivables/detail?customer=7&month=2026-08-01": {"outstanding_vnd": "120500000"},
    "/api/v7/receivables/detail?customer=9&month=2026-11-01": {"outstanding_vnd": "45000"},
    "/api/v7/receipt-book?month=2026-11-01": {"summary": {"total_vnd": "45000"}, "days": []},
    "/api/v7/machine/now": {"run": {"state": "done", "finished_at": "2026-11-22T14:09:30+07:00"}},
    "/api/v7/machine/booking": {"state": "ok"},
    "/api/v7/cash-chat": {"totals": {"thu_vnd": 45000}, "items": []},
}


class Opener:
    def open(self, request, timeout=None):
        parts = urllib.parse.urlsplit(request.full_url)
        key = parts.path + (f"?{parts.query}" if parts.query else "")
        if key not in DATA:
            raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)
        return io.BytesIO(json.dumps(DATA[key]).encode("utf-8"))


class EvalTests(unittest.TestCase):
    def setUp(self):
        tools.reset_cache()
        self.ctx = tools.Context(webapi.WebApi(opener=Opener()), ADMIN, now=NOW)

    def test_cases_and_answers_come_from_the_api(self):
        cases, skipped = bot_eval.build(self.ctx)
        by_id = {case.id: case for case in cases}
        self.assertEqual(by_id["tong_no"].expect, [["395.045.000 đ"]])
        self.assertEqual(by_id["no_nhieu_nhat"].expect, [["Khách A"]])
        self.assertEqual(by_id["no_khach_7"].question, "Khách Khách A còn nợ bao nhiêu?")
        self.assertEqual(by_id["qua_han_7"].expect, [["120.500.000 đ"]])
        self.assertIn("20/10/2026", by_id["tra_cuoi_7"].expect[0])
        self.assertEqual(by_id["thang_7"].question, "Tháng 8/2026 khách Khách A còn nợ bao nhiêu?")
        self.assertEqual(by_id["doi_soat_7"].expect, [["khớp"]])
        self.assertEqual(by_id["doi_soat_cuoi"].expect, [["14:09"]])
        self.assertEqual(by_id["bao_chuyen"].expect, [["45.000 đ"]])
        self.assertGreaterEqual(skipped, 0)
        self.assertLessEqual(len(bot_eval.build(self.ctx, limit=3)[0]), 3)

    def test_scoring(self):
        case = bot_eval.Case("x", "no_khach", "?", [["395.000.000 đ"]])
        self.assertEqual(bot_eval.score(model.Answer("Khách A còn nợ 395.000.000 đ.", "answered", body="…"), case), "dung")
        self.assertEqual(bot_eval.score(model.Answer("Còn nợ 390.000.000 đ.", "answered", body="Còn nợ 390.000.000 đ."), case), "sai_so")
        self.assertEqual(bot_eval.score(model.Answer("Mình chưa tra được.", "answered", body="Mình chưa tra được."), case), "thieu")
        self.assertEqual(bot_eval.score(model.Answer(model.NOT_SURE, "not_sure"), case), "khong_tra_loi")
        rule = bot_eval.Case("y", "quy_tac", "?", [["nợ cũ", "no cu"]])
        self.assertEqual(bot_eval.score(model.Answer("Thu mới trừ vào NỢ CŨ trước.", "answered"), rule), "dung")

    def test_run_totals_costs_and_never_needs_the_sdk(self):
        cases = [bot_eval.Case("a", "g", "q1", [["1.000 đ"]]), bot_eval.Case("b", "g", "q2", [["2.000 đ"]])]
        replies = iter([model.Answer("Là 1.000 đ.", "answered", cost_nano_usd=7), model.Answer(model.NOT_SURE, "not_sure", cost_nano_usd=3)])
        report = bot_eval.run(NS(answer=lambda user, question: next(replies)), ADMIN, cases, clock=lambda: NOW)
        self.assertEqual((report["totals"], report["cost_nano_usd"]), ({"dung": 1, "khong_tra_loi": 1}, 10))
        self.assertEqual(bot_eval.usd(1_234_000_000), "1,23")
        self.assertEqual(bot_eval.usd(5_000_000), "0,01")


if __name__ == "__main__":
    unittest.main()
