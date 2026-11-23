"""Công cụ tầng A của bot Zalo (ZALO-BOT-01 Phần 3): đọc API giả qua lớp chỉ GET thật, giữ quyền theo trang, bỏ chữ tự do,
kèm trạng thái khớp Sheet, cắt kết quả dài. Dữ liệu là dữ liệu giả."""

import datetime as dt
import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from zalo_bot import tools, webapi  # noqa: E402
from zalo_bot.config import User  # noqa: E402

VN = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=VN).timestamp()
ADMIN = User("1111", "chu@example.com", "admin")
STAFF = User("2222", "nv@example.com", "user")

DATA = {
    "/api/v7/customers": {"customers": [
        {"id": 7, "name": "KHACH A - SR", "display_name": "Khách A", "status": "active", "commodity": "Sầu riêng", "transport_mode": "CANG"},
        {"id": 8, "name": "KHACH A2", "status": "active", "commodity": "Dừa", "transport_mode": None, "aliases": ["Khách Á hai"]},
        {"id": 9, "name": "KHACH B", "status": "active", "commodity": "Dừa"}]},
    "/api/v7/dashboard": {"as_of": "2026-11-22", "receivable": {"total_vnd": "1234567890", "customers": 3},
                          "top_debtors": [{"customer_id": 7, "name": "Khách A", "outstanding_vnd": "350000000", "truong_moi_cua_api": "bí mật"}],
                          "today": {"trips": 4, "receipts": 1, "received_vnd": "45000", "by_actor": [{"actor": "nv@example.com"}]}},
    "/api/v7/dashboard/debt": {"as_of": "2026-11-22", "summary": {"overdue_vnd": "120500000", "overdue_customers": 1},
                               "due_tiers": [{"tier": "not_due", "receivable_vnd": "229500000"}], "this_month": {"received_vnd": "45000"},
                               "customers": [{"customer_id": 7, "outstanding_vnd": "350000000", "overdue_vnd": "120500000",
                                              "tiers_vnd": ["229500000", "0", "120500000", "0", "0"], "oldest_open_month": "2026-08-01",
                                              "last_receipt_date": "2026-11-02", "pay_days": 20, "risk": "high",
                                              "months": [{"month": "2026-08-01", "outstanding_vnd": "120500000"}]}]},
    "/api/v7/ledger?customer=9": {"total_outstanding_vnd": "0", "months": [], "trips": [], "receipts": [], "adjustments": []},
    "/api/v7/ledger?customer=7": {
        "total_outstanding_vnd": "350000000", "months": [{"month": "2026-10-01", "outstanding_vnd": "100000000", "charges_vnd": "100000000"}],
        "trips": [{"id": 31, "container": "MAUU1000101", "booking": "BKG777", "origin": "Kho riêng", "destination": "Cửa khẩu",
                   "event_date": "2026-10-03", "amount_vnd": "100000000", "note": "ghi chú riêng", "shipper": "X"},
                  {"container": "MAUU1000102", "event_date": "2026-11-01", "amount_vnd": "250000000"}],
        "receipts": [{"pid": 5, "date": "2026-10-20", "amount_vnd": "45000", "reference": "STK 0123456789", "void_reason": None}],
        "adjustments": [], "legacy_rows": [{"display": "chữ thô"}], "sheet_sync": {"x": 1}},
    "/api/v7/ledger/events?customer=7": {"events": [
        {"id": 1, "kind": "trip", "label": "Thêm chuyến", "actor": "nv@example.com", "actor_name": "Nhân viên", "at": "2026-11-20T09:00:00+07:00",
         "before": {"note": "a"}, "after": {"amount_vnd": "1"}},
        {"id": 2, "kind": "receipt", "label": "Thu", "actor_name": "Máy", "at": "2026-10-01T09:00:00+07:00"}]},
    "/api/v7/inbox": {"reconcile": {"checked_at": "2026-11-22T10:05:00+07:00", "counts": {"KHOP": 2, "LECH_TONG": 1}, "matched_ids": [7],
                                    "customers": [{"customer_id": 9, "status": "LECH_TONG", "reason": "HELD", "sheet_total_vnd": "45000",
                                                   "web_total_vnd": "0", "difference_vnd": "45000", "hints": ["chữ"]}]},
                      "books": [{"customer_id": 7, "receipts": {"items": ["chữ"]}}]},
    "/api/v7/receipt-book?month=2026-11-01": {"as_of": "2026-11-22", "summary": {"total_vnd": "45000", "count": 1},
                                              "days": [{"date": "2026-11-02", "total_vnd": "45000", "rows": [
                                                  {"pid": 5, "customer_id": 7, "name": "Khách A", "amount_vnd": "45000", "note": "chữ", "method": "CK"}]}]},
    "/api/v7/zalo/conversations?q=Kh%C3%A1ch+A": {"total": 1, "conversations": [
        {"conversation_id": "ab" * 32, "display_name": "Khách A", "is_group": True, "message_count": 12, "last_message_at": 1795316400000}]},
    "/api/v7/sheet/doi-chieu?customer=9": {"web_vnd": "0", "sheet_total_vnd": "45000", "checked_at": "2026-11-22T10:05:00+07:00",
                                           "reason": "HELD", "groups": [{"kind": "receipt", "month": "2026-11-01", "count": 1, "delta_vnd": "45000",
                                                                         "rows": [{"note": "chữ"}]}], "findings": ["chữ"]},
    "/api/v7/cash-chat": {"from": "2026-11-15", "to": "2026-11-22", "totals": {"thu_vnd": 45000, "chi_vnd": 0, "ung_vnd": 0},
                          "items": [{"direction": "thu", "amount_vnd": 45000, "status": "MATCHED", "target": {"kind": "customer", "id": 7, "label": "Khách A"},
                                     "day": "2026-11-20", "text": "ck 45k", "sender_name": "Người gửi", "image": "x.jpg"},
                                    {"direction": "ung", "amount_vnd": 5000, "status": "OPEN", "target": {"kind": "driver", "id": 3, "label": "Tài xế Tư"},
                                     "day": "2026-11-21"}],
                          "counts": {"MATCHED": 1, "Tên lạ": "x"}},
    "/api/v7/doixe?thang=2026-11-01": {"nguoi": [{"id": 3, "ten": "Tài xế Tư", "vai": "tai_xe", "so_du_vnd": "5000"}],
                                       "xe": [{"id": 4, "bien_so": "99C-00000", "nhom": "dau_keo", "chua_phi": 1}]},
    "/api/v7/doixe/bang-ke?thang=2026-11-01": {"cong_no_vnd": "7000", "dong": [{"tai_xe": "Tài xế Tư", "so_xe": "99C-00000"}]},
    "/api/v7/activity": {"day": "2026-11-22", "total": 2, "events": [
        {"customer_id": 7, "customer": "Khách A", "kind": "trip", "actor": "nv@example.com", "actor_name": "Nhân viên", "at": "2026-11-22T09:00+07:00"},
        {"customer_id": 7, "customer": "Khách A", "kind": "receipt", "actor_name": None, "at": "2026-11-22T10:00+07:00"}]},
    "/api/v7/nhat-ky": {"days": {"2026-11-22": {"changes": [["#1", "Tên PR", "web", 1, 1, 1, "09:00"], ["#2", "PR khác", "web", 1, 1, 1, "10:00"]],
                                                "headline": "Hai thay đổi"}}},
}


class Opener:
    def __init__(self):
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append((request.get_method(), request.full_url))
        parts = urllib.parse.urlsplit(request.full_url)
        key = parts.path + (f"?{parts.query}" if parts.query else "")
        if key not in DATA:
            raise AssertionError(f"API giả không có {key}")
        return io.BytesIO(json.dumps(DATA[key]).encode("utf-8"))


class ToolTests(unittest.TestCase):
    def setUp(self):
        tools.reset_cache()
        self.opener = Opener()
        self.api = webapi.WebApi(opener=self.opener)

    def ctx(self, user=ADMIN):
        return tools.Context(self.api, user, now=NOW, link_base="https://web.example")

    def run_tool(self, name, args, user=ADMIN):
        return tools.run(self.ctx(user), name, args)

    def test_staff_only_get_the_six_user_pages_tools(self):
        staff = {tool.name for tool in tools.for_role("user")}
        self.assertEqual(len(staff), 12)                  # 11 công cụ theo trang + tra tài liệu
        self.assertIn("tra_tai_lieu", staff)
        self.assertFalse(staff & {"doi_soat", "viec_da_lam", "may_chay", "doi_xe", "thu_chi", "nhat_ky_web"})
        self.assertEqual(len(tools.for_role("admin")), 18)
        for tool in tools.TOOLS:
            schema = tool.schema()["input_schema"]
            self.assertEqual((schema["type"], schema["additionalProperties"]), ("object", False))
            self.assertTrue(set(schema["required"]) <= set(schema["properties"]))
        self.assertEqual(self.run_tool("thu_chi", {}, user=STAFF), ({"loi": "khong_co_cong_cu_nay"}, True))
        self.assertEqual(self.run_tool("xoa_so", {}), ({"loi": "khong_co_cong_cu_nay"}, True))
        self.assertEqual(self.opener.calls, [])

    def test_find_customer_without_accents_and_ask_back_when_several_match(self):
        result, error = self.run_tool("tim_khach", {"ten": "khach a"})
        self.assertFalse(error)
        self.assertEqual([row["khach_id"] for row in result["khach"]], [7, 8])
        self.assertIn("goi_y", result)
        self.assertEqual(self.run_tool("tim_khach", {"ten": "khách á hai"})[0]["khach"][0]["khach_id"], 8)

    def test_debt_answer_carries_money_link_and_matched_sheet_status(self):
        result, error = self.run_tool("no_khach", {"khach_id": 7})
        self.assertFalse(error)
        self.assertEqual((result["no_vnd"], result["qua_han_vnd"], result["ten"]), ("350000000", "120500000", "Khách A"))
        self.assertEqual(result["link"], "https://web.example/so-khach-v7-live.html?customer=7")
        self.assertEqual(result["du_lieu_luc"], "2026-11-22T15:00+07:00")
        self.assertEqual(result["doi_soat"], {"trang_thai": "khop", "luc": "2026-11-22T10:05:00+07:00", "cu": True})   # 5 giờ, trong 10–22h

    def test_customer_not_owing_reads_ledger_total_and_lech_status(self):
        result, _ = self.run_tool("no_khach", {"khach_id": 9})
        self.assertEqual(result["no_vnd"], "0")
        self.assertEqual(result["doi_soat"]["trang_thai"], "lech_tong")
        self.assertEqual(result["doi_soat"]["lech_vnd"], "45000")

    def test_month_view_keeps_numbers_and_drops_free_text(self):
        result, _ = self.run_tool("so_khach_thang", {"khach_id": 7, "thang": "2026-10"})
        self.assertEqual(result["chuyen"], [{"id": 31, "event_date": "2026-10-03", "amount_vnd": "100000000"}])
        self.assertEqual(result["phieu_thu"], [{"pid": 5, "date": "2026-10-20", "amount_vnd": "45000"}])
        text = json.dumps(result, ensure_ascii=False)
        for secret in ("ghi chú riêng", "STK", "chữ thô", "shipper", "MAUU1000101", "BKG777", "Kho riêng", "Cửa khẩu"):
            self.assertNotIn(secret, text)

    def test_q5_reason_and_error_are_codes_only(self):
        """Q5 (24/11/2026): lý do, lỗi gửi model chỉ khi là mã máy; chữ gõ tay thành None."""
        rows = [{"customer_id": 7, "reason": "HELD"}, {"customer_id": 8, "reason": "khách hẹn trả, gọi 0901 234 567"},
                {"customer_id": 9, "reason": "WEB_AHEAD", "error": "Traceback: kết nối hỏng"}]
        self.assertEqual(tools.compact(rows, "doi_soat"), [{"customer_id": 7, "reason": "HELD"}, {"customer_id": 8, "reason": None},
                                                           {"customer_id": 9, "reason": "WEB_AHEAD"}])
        self.assertEqual(tools.compact([{"name": "dong_bo", "error": "mat_ket_noi"}, {"name": "x", "error": "lỗi lạ: xem log"}], "may_chay"),
                         [{"name": "dong_bo", "error": "mat_ket_noi"}, {"name": "x", "error": None}])

    def test_q5_forbidden_fields_never_leave(self):
        """Q5 (24/11/2026): không gửi số điện thoại, số tài khoản, ảnh, tin chat, ghi chú tự do, ở công cụ nào cũng vậy."""
        forbidden = {"phone": "0901234567", "so_dien_thoai": "0901234567", "bank_account": "0123456789", "account_number": "0123456789",
                     "so_tai_khoan": "0123456789", "image": "a.jpg", "image_url": "https://x/a.jpg", "anh": "a.jpg", "text": "tin khách",
                     "message": "tin khách", "message_excerpt": "tin khách", "body": "tin khách", "note": "ghi chú", "ghi_chu": "ghi chú",
                     "void_reason": "gõ tay", "comment": "ghi chú", "email": "a@example.com", "actor": "a@example.com"}
        for tool in tools.KEEP:
            with self.subTest(tool=tool):
                self.assertEqual(tools.compact({**forbidden, "amount_vnd": "1000"}, tool), {"amount_vnd": "1000"})
                self.assertFalse((tools.KEEP_COMMON | tools.KEEP[tool]) & set(forbidden))

    def test_history_is_filtered_by_date_without_actor_emails(self):
        result, _ = self.run_tool("lich_su_so", {"khach_id": 7})
        self.assertEqual(result["so_thao_tac"], 1)
        self.assertNotIn("nv@example.com", json.dumps(result))
        self.assertEqual(result["thao_tac"], [{"id": 1, "kind": "trip", "label": "Thêm chuyến", "at": "2026-11-20T09:00:00+07:00"}])

    def test_receipt_book_by_day_and_by_customer(self):
        day, _ = self.run_tool("bang_thu", {"thang": "2026-11", "ngay": "2026-11-02"})
        self.assertEqual(day["ngay"]["rows"], [{"pid": 5, "customer_id": 7, "name": "Khách A", "amount_vnd": "45000"}])
        self.assertTrue(day["link"].endswith("/bang-thu.html?month=2026-11&ngay=2026-11-02"))
        mine, _ = self.run_tool("bang_thu", {"thang": "2026-11", "khach_id": 7})
        self.assertEqual(len(mine["phieu_cua_khach"]), 1)

    def test_last_chat_gives_times_only(self):
        result, error = self.run_tool("lan_cuoi_noi_chuyen", {"ten": "Khách A"})
        self.assertFalse(error)
        self.assertEqual(result["cuoc_tro_chuyen"][0]["last_message_at"], "2026-11-22T10:00+07:00")
        self.assertTrue(result["link"].endswith("/zalo-chat.html?q=Kh%C3%A1ch%20A"))

    def test_admin_reconcile_detail_without_rows_or_findings(self):
        result, _ = self.run_tool("doi_soat", {"khach_id": 9})
        self.assertEqual(result["khach_lech"][0]["difference_vnd"], "45000")
        self.assertEqual(result["khach"]["nhom_lech"], [{"kind": "receipt", "month": "2026-11-01", "count": 1, "delta_vnd": "45000"}])
        self.assertNotIn("chữ", json.dumps(result, ensure_ascii=False))

    def test_cash_chat_amounts_become_vnd_strings_without_chat_text(self):
        result, _ = self.run_tool("thu_chi", {})
        self.assertEqual(result["tong"], {"thu_vnd": "45000", "chi_vnd": "0", "ung_vnd": "0"})
        self.assertEqual(result["khoan"][0]["so_tien_vnd"], "45000")
        text = json.dumps(result, ensure_ascii=False)
        for secret in ("ck 45k", "Người gửi", "x.jpg", "Tài xế Tư", "Tên lạ"):
            self.assertNotIn(secret, text)
        self.assertEqual([row["doi_tuong"] for row in result["khoan"]],
                         [{"loai": "customer", "id": 7, "ten": "Khách A"}, {"loai": "driver", "id": 3}])
        self.assertEqual(result["dem"], {"MATCHED": 1})

    def test_only_kept_keys_reach_the_model(self):
        """F7: khóa API mới, tên tài xế, biển số, tên người thao tác không đi ra ngoài; nhật ký web chỉ đếm số thay đổi."""
        board, _ = self.run_tool("tong_quan", {})
        self.assertEqual(board["khach_no_nhieu_nhat"], [{"customer_id": 7, "name": "Khách A", "outstanding_vnd": "350000000"}])
        self.assertNotIn("nv@example.com", json.dumps(board))
        fleet, _ = self.run_tool("doi_xe", {"thang": "2026-11"})
        self.assertEqual((fleet["tai_xe"], fleet["xe"]), ([{"id": 3, "vai": "tai_xe", "so_du_vnd": "5000"}], [{"id": 4, "nhom": "dau_keo", "chua_phi": 1}]))
        self.assertNotIn("99C", json.dumps(fleet, ensure_ascii=False))
        done, _ = self.run_tool("viec_da_lam", {})
        self.assertEqual((done["so_viec_nguoi_lam"], done["so_viec_may_lam"]), (1, 1))
        self.assertNotIn("Nhân viên", json.dumps(done, ensure_ascii=False))
        news, _ = self.run_tool("nhat_ky_web", {})
        self.assertEqual(news["ngay"], [{"ngay": "2026-11-22", "so_thay_doi": 2, "tom_tat": "Hai thay đổi"}])
        self.assertEqual(set(tools.KEEP), {tool.name for tool in tools.TOOLS} - {"tim_khach", "lan_cuoi_noi_chuyen", "tra_tai_lieu", "thu_chi", "nhat_ky_web"})

    def test_bad_arguments_are_short_errors_and_make_no_call(self):
        self.assertEqual(self.run_tool("no_khach", {"khach_id": "7"}), ({"loi": "khach_id_sai"}, True))
        self.assertEqual(self.run_tool("so_khach_thang", {"khach_id": 7, "thang": "10/2026"}), ({"loi": "thang_sai"}, True))
        self.assertEqual(self.run_tool("tim_khach", "Khách A"), ({"loi": "tham_so_sai"}, True))
        self.assertEqual(self.opener.calls, [])

    def test_inbox_read_once_per_minute_across_questions(self):
        self.run_tool("no_khach", {"khach_id": 7})
        tools.run(tools.Context(self.api, ADMIN, now=NOW + 30), "no_khach", {"khach_id": 7})
        self.assertEqual(sum(url.endswith("/api/v7/inbox") for _, url in self.opener.calls), 1)
        self.assertTrue(all(method == "GET" for method, _ in self.opener.calls))

    def docs(self):
        root = Path(tempfile.mkdtemp())
        files = {
            "docs/business-rules.md": "# Luật nghiệp vụ\n\nVND nguyên chính xác; NULL hay ô trống không phải 0.\n\n"
                                      "## Thu tiền\n\nThu mới theo nợ cũ trước; không phân bổ lại opening.",
            "docs/decisions/quyen-01.md": "# QUYEN-01\n\n## Quyết định\n\nNgười dùng thường chỉ thấy sáu trang: Tổng quan, Công nợ theo tháng, "
                                          "Sổ khách, Bảng thu, Báo cáo tháng, Chat Zalo.",
            "specs/zalo-bot.md": "# Bot Zalo\n\nBot chỉ đọc qua API web và không ghi tiền, kể cả khi người hỏi nhờ.",
        }
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        return root

    def test_docs_search_finds_rules_and_decisions_without_accents(self):
        ctx = tools.Context(self.api, STAFF, now=NOW, docs_root=self.docs())
        result, error = tools.run(ctx, "tra_tai_lieu", {"tu_khoa": "thu theo no cu truoc"})
        self.assertFalse(error)
        self.assertEqual((result["doan"][0]["nguon"], result["doan"][0]["muc"]), ("docs/business-rules.md", "Thu tiền"))
        found, _ = tools.run(ctx, "tra_tai_lieu", {"tu_khoa": "quyền người dùng thấy trang nào"})
        self.assertEqual(found["doan"][0]["ma_quyet_dinh"], "QUYEN-01")
        self.assertEqual(self.opener.calls, [])                                   # tra tài liệu không gọi API

    def test_docs_search_errors(self):
        with_docs = tools.Context(self.api, STAFF, now=NOW, docs_root=self.docs())
        self.assertEqual(tools.run(with_docs, "tra_tai_lieu", {"tu_khoa": "là của và"}), ({"loi": "tu_khoa_sai"}, True))
        self.assertEqual(tools.run(with_docs, "tra_tai_lieu", {"tu_khoa": 5}), ({"loi": "tu_khoa_sai"}, True))
        no_docs = tools.Context(self.api, STAFF, now=NOW, docs_root=Path(tempfile.mkdtemp()))
        self.assertEqual(tools.run(no_docs, "tra_tai_lieu", {"tu_khoa": "công nợ"}), ({"loi": "khong_co_tai_lieu"}, True))

    def test_long_results_are_cut_under_the_limit(self):
        big = {"trang": "x", "rows": [{"amount_vnd": str(i), "pad": "y" * 50} for i in range(1000)]}
        cut = tools.fit(big, limit=2000)
        self.assertTrue(cut["da_cat"])
        self.assertLessEqual(len(json.dumps(cut)), 2000)
        self.assertGreater(len(cut["rows"]), 1)


if __name__ == "__main__":
    unittest.main()
