"""Số đệm menu Quản trị (web/v7_todo_badge.py): một lần đọc gọn thay ba lần đọc nặng, không tự đếm (audit giao diện 23/11)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_todo_badge as badge
from v7_api_validate import ApiError

INBOX = {
    "state": "ready", "computed_at": "2026-11-23T08:00:00+00:00", "auto": {"today_count": 3}, "insurance": {"rows": [1, 2, 3]},
    "books": [{"customer_id": 1, "receipts": {"ready": 1, "review": 0}, "sheet_matched": False},
              {"customer_id": 2, "trips_new": 2, "sheet_matched": True}],
    "reconcile": {"matched_ids": [2], "statements": [{"customer_id": 9, "rows": ["dài"] * 50}]},
}
DASHBOARD = {"receivable": {"total_vnd": "1000"}, "today": {"trips": 4},
             "todo": {"missing_price": [{"customer_id": 3, "count": 2}], "pending_review": [], "no_baseline": []}}
DEBT = {"as_of": "2026-11-23", "customers": [
    {"customer_id": 4, "name": "Khách Thử", "commodity": None, "transport_mode": None, "outstanding_vnd": "5", "months": [{"m": 1}]}]}


class FakeReads:
    def __init__(self):
        self.calls = []

    def run(self, runner, function, payload, actor):
        self.calls.append((function, payload, actor))
        return {"get_dashboard": DASHBOARD, "get_dashboard_debt": DEBT}[function]


class FakeInbox:
    def view(self, runner):
        return INBOX


class TodoBadgeTest(unittest.TestCase):
    def test_giu_nguyen_hop_cho_va_tong_quan_cat_danh_sach_no(self):
        body = badge.view(INBOX, DASHBOARD, DEBT)
        self.assertEqual(body["inbox"], INBOX)   # menu lưu làm bản chụp cho Việc cần làm (#342): cần nguyên
        self.assertEqual(body["dashboard"], DASHBOARD)
        self.assertEqual(body["debt"], {"customers": [{"customer_id": 4, "name": "Khách Thử", "commodity": None, "transport_mode": None}]})

    def test_nguon_trong_khong_vo(self):
        self.assertEqual(badge.view({}, {}, {}), {"inbox": {}, "dashboard": {}, "debt": {"customers": []}})

    def test_doc_qua_bo_nho_doc_va_tu_choi_tham_so(self):
        reads = FakeReads()
        body = badge.handle_get("", object(), reads, FakeInbox(), "nguoi-thu")
        self.assertEqual([call[0] for call in reads.calls], ["get_dashboard", "get_dashboard_debt"])
        self.assertTrue(all(call[2] == "nguoi-thu" for call in reads.calls))
        self.assertEqual(body["inbox"]["books"], INBOX["books"])
        with self.assertRaises(ApiError) as caught:
            badge.handle_get("x=1", object(), reads, FakeInbox(), "nguoi-thu")
        self.assertEqual(caught.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
