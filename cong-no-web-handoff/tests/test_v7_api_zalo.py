"""ZALO-GROUP-01: API gắn group ↔ sổ và dấu tin — kiểm thân lệnh trước DB, SQL cố định, migration khớp file chuẩn."""

import json
import re
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_api_zalo as zalo  # noqa: E402
import v7_ledger_api as api  # noqa: E402

CONV = "a1" * 32
TODAY = date(2026, 11, 1)


class FakePsql:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        return {"function": function}


class ZaloApiTest(unittest.TestCase):
    def setUp(self):
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}
        patcher = patch.object(zalo, "today_vn", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, method, path, body=None):
        runner = FakePsql()
        raw = json.dumps(body).encode() if body is not None else b""
        status, _ = api.handle(method, path, self.headers, raw, runner, port=8780, host="127.0.0.1", actor="server-actor")
        self.assertEqual(status, 200)
        self.assertEqual(runner.calls[-1][2], "server-actor")   # người làm lấy từ phiên, không từ thân lệnh
        return runner.calls[-1][:2]

    def rejects(self, method, path, body, code):
        with self.assertRaises(api.ApiError) as caught:
            self.call(method, path, body)
        self.assertEqual(caught.exception.code, code)

    def test_link_unlink_and_reads(self):
        self.assertEqual(self.call("POST", "/api/v7/zalo/link", {"conversation_id": CONV, "customer_id": 7}),
                         ("link_zalo", {"conversation_id": CONV, "customer_id": 7}))
        self.assertEqual(self.call("POST", "/api/v7/zalo/unlink", {"conversation_id": CONV, "customer_id": 7, "reason": " nhầm sổ "}),
                         ("unlink_zalo", {"conversation_id": CONV, "customer_id": 7, "reason": "nhầm sổ"}))
        self.assertEqual(self.call("GET", "/api/v7/zalo/links"), ("get_zalo_links", {}))
        self.assertEqual(self.call("GET", "/api/v7/marks?customer=7"), ("get_marks", {"customer_id": 7}))
        self.assertEqual(self.call("GET", f"/api/v7/marks?conversation={CONV}"), ("get_marks", {"conversation_id": CONV}))
        for body in ({"conversation_id": "abc", "customer_id": 7}, {"conversation_id": CONV, "customer_id": "7"},
                     {"conversation_id": CONV, "customer_id": 7, "actor": "x"}):
            with self.subTest(body=body):
                self.rejects("POST", "/api/v7/zalo/link", body, "INVALID_LINK")
        self.rejects("POST", "/api/v7/zalo/unlink", {"conversation_id": CONV, "customer_id": 7, "reason": "  "}, "REASON_REQUIRED")
        for query in ("", "?customer=0", "?customer=7&conversation=" + CONV, "?conversation=abc", "?customer=7&customer=8"):
            with self.subTest(query=query), self.assertRaises(api.ApiError):
                self.call("GET", "/api/v7/marks" + query)

    def test_mark_payloads(self):
        promise = {"customer_id": 7, "kind": "promise", "idempotency_key": "k1", "amount_vnd": "50000000", "on_date": "2026-11-05",
                   "note": " mai chuyển ", "conversation_id": CONV, "message_id": "m42", "message_at": "2026-11-01T09:15:00+07:00",
                   "message_sender": "Vũ", "message_excerpt": "Mai em chuyển 50 triệu"}
        function, payload = self.call("POST", "/api/v7/marks", promise)
        self.assertEqual((function, payload["note"], payload["amount_vnd"]), ("record_mark", "mai chuyển", "50000000"))
        self.assertIn("SELECT sokhach.record_mark(:'payload'::jsonb)", api.SQL["record_mark"])
        claim = {"customer_id": 7, "kind": "paid_claim", "idempotency_key": "k2", "amount_vnd": "300", "on_date": "2026-11-01"}
        self.assertEqual(self.call("POST", "/api/v7/marks", claim)[0], "record_mark")
        note = {"customer_id": 7, "kind": "note", "idempotency_key": "k3", "note": "Xin giãn", "amount_vnd": None}
        self.assertNotIn("amount_vnd", self.call("POST", "/api/v7/marks", note)[1])
        self.assertEqual(self.call("POST", "/api/v7/marks/cancel", {"id": 9, "reason": " sai "}), ("cancel_mark", {"id": 9, "reason": "sai"}))

    def test_mark_rejections(self):
        base = {"customer_id": 7, "kind": "promise", "idempotency_key": "k", "amount_vnd": "300", "on_date": "2026-11-05"}
        cases = [
            ({**base, "amount_vnd": 300}, "INVALID_MARK"),           # tiền là chuỗi như mọi lệnh tiền
            ({**base, "amount_vnd": "0"}, "INVALID_MARK"),
            ({**base, "amount_vnd": "1.5"}, "INVALID_MARK"),
            ({**base, "amount_vnd": "-5"}, "INVALID_MARK"),
            ({**base, "on_date": "05/11/2026"}, "INVALID_MARK"),
            ({**base, "on_date": "2026-10-31"}, "INVALID_MARK_DATE"),  # hứa trả hẹn ngày đã qua
            ({**base, "on_date": "2027-12-31"}, "INVALID_MARK_DATE"),
            ({**base, "kind": "paid_claim", "on_date": "2026-11-02"}, "INVALID_MARK_DATE"),  # báo đã chuyển ngày mai
            ({**base, "kind": "note"}, "INVALID_MARK"),             # ghi chú không có số tiền
            ({"customer_id": 7, "kind": "note", "idempotency_key": "k", "note": "  "}, "INVALID_MARK"),
            ({**base, "kind": "da_tra"}, "INVALID_MARK"),
            ({**base, "idempotency_key": ""}, "INVALID_MARK"),
            ({**base, "message_id": "m1"}, "INVALID_MARK"),         # tin phải đi cùng group
            ({**base, "conversation_id": CONV, "message_id": "a/b"}, "INVALID_MARK"),
            ({**base, "conversation_id": CONV, "message_id": "m1", "message_at": "2026-11-01 09:15"}, "INVALID_MARK"),
            ({**base, "message_excerpt": "x" * 301}, "INVALID_MARK"),
            ({**base, "actor": "giả"}, "INVALID_MARK"),
            ({**base, "customer_id": True}, "INVALID_MARK"),
        ]
        for body, code in cases:
            with self.subTest(body=body):
                self.rejects("POST", "/api/v7/marks", body, code)
        self.rejects("POST", "/api/v7/marks/cancel", {"id": 9, "reason": ""}, "REASON_REQUIRED")
        self.rejects("POST", "/api/v7/marks/cancel", {"id": "9", "reason": "x"}, "INVALID_MARK")

    def test_chat_routes_still_reach_chat_module(self):
        with self.assertRaises(api.ApiError) as caught, patch.object(api.v7_zalo_chat, "EXPORT_DIR", None):
            self.call("GET", "/api/v7/zalo/report")
        self.assertEqual(caught.exception.code, "ZALO_EXPORT_UNAVAILABLE")


class ZaloGroupSqlSync(unittest.TestCase):
    """Migration và file hàm chuẩn phải giống từng byte ở các hàm, bảng ở migration giống lược đồ chuẩn."""

    def test_migration_matches_canonical(self):
        repo = ROOT.parent
        migration = (ROOT / "tools/migrations/2026-11-01-v7-zalo-group.sql").read_text(encoding="utf-8")
        functions = (ROOT / "tools/v7_backend_functions.sql").read_text(encoding="utf-8")
        schema = (repo / "specs/v7-backend/schema-draft.sql").read_text(encoding="utf-8")
        block = re.search(r"(?ms)^-- ZALO-GROUP-01: gắn group Zalo ↔ sổ, dấu tin.*?TO sokhach_app,sokhach_reader;\n", migration).group()
        self.assertIn(block, functions)
        for table in ("zalo_link", "contact_mark"):
            with self.subTest(table=table):
                created = re.search(rf"(?ms)^CREATE TABLE IF NOT EXISTS sokhach\.{table} \(.*?^\);\n", migration).group()
                self.assertIn(created.replace(" IF NOT EXISTS", ""), schema)


if __name__ == "__main__":
    unittest.main()
