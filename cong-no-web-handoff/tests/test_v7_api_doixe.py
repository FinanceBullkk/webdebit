"""CHI-PHI-XE-01: API đội xe — kiểm thân lệnh trước DB, đường đọc, SQL cố định khớp hàm của migration, trần thân lệnh, tên người làm."""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_api_doixe as doixe  # noqa: E402
import v7_api_tables as tables  # noqa: E402
import v7_ledger_api as api  # noqa: E402

MIGRATION = ROOT / "tools" / "migrations" / "2026-11-18-v7-doi-xe.sql"
MIGRATION_THU = ROOT / "tools" / "migrations" / "2026-11-18-v7-doi-xe-thu.sql"
MIGRATION_DIEU_DO = ROOT / "tools" / "migrations" / "2026-11-19-v7-doi-xe-dieu-do.sql"
MIGRATION_TAI_CHINH = ROOT / "tools" / "migrations" / "2026-11-19-v7-doi-xe-tai-chinh-chang.sql"
MIGRATION_AUDIT = ROOT / "tools" / "migrations" / "2026-11-23-v7-doi-xe-sua-audit.sql"


class FakePsql:
    def __init__(self, result=None):
        self.calls, self.result = [], result

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        return self.result if self.result is not None else {"function": function}


def row(**extra):
    return {"ngay": "2026-11-17", "container": "MAUU1234567", "loai": "hang", "xe_id": 3, "tai_xe_id": 4, "tra": "nguoi",
            "nguoi_tra_id": 4, "phi": {"nangha": "300000", "vetc": "120000"}, **extra}


class DoiXeApiTest(unittest.TestCase):
    def setUp(self):
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}

    def call(self, method, path, body=None, *, result=None):
        runner = FakePsql(result)
        raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
        status, value = api.handle(method, path, self.headers, raw, runner, port=8780, host="127.0.0.1", actor="nv@gia")
        self.assertEqual(status, 200)
        self.assertEqual(runner.calls[-1][2], "nv@gia")   # người làm lấy từ phiên, không từ thân lệnh
        return runner.calls[-1][:2], value

    def rejects(self, method, path, body, code):
        with self.assertRaises(api.ApiError) as caught:
            self.call(method, path, body)
        self.assertEqual(caught.exception.code, code, body)

    def test_writes_pass_body_as_is(self):
        cases = [
            ("/api/v7/doixe/chang", "doixe_luu_chang", {"rows": [row(), row(ngay=None, xe_id=None, tra="cong_ty", nguoi_tra_id=None, phi={})]}),
            ("/api/v7/doixe/chang", "doixe_luu_chang", {"rows": [row(phi={"hasom": "250000"}, neo_ngay="2", may_gio="5", km="120"),
                                                                 row(neo_ngay=None, may_gio=None, km=None)]}),
            ("/api/v7/doixe/chang/sua", "doixe_sua_chang", {"chang_id": 9, "cot": "phi:neo", "truoc": None, "gia_tri": "100000"}),
            ("/api/v7/doixe/chang/sua", "doixe_sua_chang", {"chang_id": 9, "cot": "phi:hasom", "truoc": None, "gia_tri": "250000"}),
            ("/api/v7/doixe/chang/sua", "doixe_sua_chang", {"chang_id": 9, "cot": "may_gio", "truoc": None, "gia_tri": "5"}),
            ("/api/v7/doixe/chang/sua", "doixe_sua_chang", {"chang_id": 9, "cot": "km", "truoc": "120", "gia_tri": None}),
            ("/api/v7/doixe/chang/sua", "doixe_sua_chang", {"chang_id": 9, "cot": "ngay", "truoc": "2026-11-01", "gia_tri": "2026-11-02"}),
            ("/api/v7/doixe/chang/sua", "doixe_sua_chang", {"chang_id": 9, "cot": "nguoi_tra", "truoc": "4", "gia_tri": "cong_ty"}),
            ("/api/v7/doixe/chang/sua", "doixe_sua_chang", {"chang_id": 9, "cot": "ghi_chu", "truoc": "vá vỏ", "gia_tri": None}),
            ("/api/v7/doixe/chang/xoa", "doixe_xoa_chang", {"chang_id": 9, "tong_vnd": "750000"}),
            ("/api/v7/doixe/chang/xoa", "doixe_xoa_chang", {"chang_id": 9, "tong_vnd": "0"}),
            ("/api/v7/doixe/ung", "doixe_ghi_ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "3000000", "so_du_vnd": "-50000"}),
            ("/api/v7/doixe/ung", "doixe_ghi_ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "3000000", "ghi_chu": "đi đường",
                                                    "so_du_vnd": "0"}),
            ("/api/v7/doixe/ung/huy", "doixe_huy_ung", {"ung_id": 2, "ly_do": "ghi trùng"}),
            ("/api/v7/doixe/hoan", "doixe_ghi_hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "0", "dong_ids": [5, 6],
                                                      "tong_dong_vnd": "1150000", "so_du_vnd": "650000"}),
            ("/api/v7/doixe/hoan/huy", "doixe_huy_hoan", {"dot_id": 1, "ly_do": "chuyển nhầm"}),
            ("/api/v7/doixe/thang/khoa", "doixe_khoa_thang", {"thang": "2026-10-01", "khoa": False}),
            # DOI-XE-THU-01
            ("/api/v7/doixe/bang-ke/gui", "doixe_gui_bang_ke", {"thang": "2026-10-01", "doi_vnd": "123000", "so_chang": 7,
                                                                "dau": "0123456789abcdef0123456789abcdef"}),
            ("/api/v7/doixe/bang-ke/doi-chieu", "doixe_doi_chieu_xong", {"thang": "2026-10-01", "doi_vnd": "0"}),
            ("/api/v7/doixe/bang-ke/dieu-chinh", "doixe_ghi_dieu_chinh_bk", {"dong_id": 5, "so_tien_vnd": "-380000", "ly_do": "HTH báo trùng",
                                                                             "doi_vnd": "2680000"}),
            ("/api/v7/doixe/bang-ke/tien-ve", "doixe_ghi_tien_ve", {"thang": "2026-10-01", "ngay": "2026-11-18", "so_tien_vnd": "1000",
                                                                    "con_vnd": "2680000"}),
            ("/api/v7/doixe/bang-ke/tien-ve", "doixe_ghi_tien_ve", {"thang": "2026-10-01", "ngay": "2026-11-18", "so_tien_vnd": "1000",
                                                                    "ghi_chu": "chuyển khoản", "con_vnd": "1000"}),
            ("/api/v7/doixe/bang-ke/tien-ve/huy", "doixe_huy_tien_ve", {"tien_ve_id": 3, "ly_do": "ghi nhầm"}),
            ("/api/v7/doixe/thu/cuoc", "doixe_sua_cuoc", {"chang_id": 9, "truoc": None, "gia_tri": "24000000"}),
            ("/api/v7/doixe/thu/cuoc", "doixe_sua_cuoc", {"chang_id": 9, "truoc": "24000000", "gia_tri": None}),
            ("/api/v7/doixe/thu/tuyen", "doixe_gan_tuyen", {"chang_id": 9, "tuyen_id": 2, "nho": True}),
            ("/api/v7/doixe/thu/tuyen", "doixe_gan_tuyen", {"chang_id": 9, "tuyen_id": None, "nho": False}),
            ("/api/v7/doixe/gia", "doixe_luu_gia", {"tuyen_id": 2, "tu_ngay": "2026-12-01", "gia_vnd": "12200000"}),
            ("/api/v7/doixe/gia", "doixe_luu_gia", {"tuyen_id": 2, "tu_ngay": "2026-01-01", "gia_vnd": "12200000", "xac_nhan_ngay_cu": True}),
            ("/api/v7/doixe/tuyen", "doixe_luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "Sầu riêng", "di": "Krông Pắc",
                                                        "den": "Cát Lái", "ten_goc": [{"hang": "Sầu đông", "tinh": None}],
                                                        "gia_vnd": "25000000", "tu_ngay": "2026-01-01"}),
            ("/api/v7/doixe/tuyen", "doixe_luu_tuyen", {"tuyen_id": 4, "loai": "chuyen_cang", "hang": None, "di": "Các cảng", "den": None,
                                                        "ten_goc": [], "dang_dung": False, "ten_goc_truoc": []}),
            ("/api/v7/doixe/tuyen", "doixe_luu_tuyen", {"tuyen_id": 4, "loai": "hang", "hang": "A", "di": "B", "den": None,
                                                        "ten_goc": [{"hang": "A", "tinh": "B"}], "ten_goc_truoc": ["A|B", "A|C"]}),
            ("/api/v7/doixe/phat-sinh", "doixe_luu_phat_sinh", {"ma": "neo", "ten": "Neo", "cach": "theo_ngay", "muc_vnd": "1500000",
                                                                "muc_them_vnd": "2000000", "chi_ho": False, "cot": "ps", "ten_goc": ["Neo"]}),
        ]
        for path, function, fields in cases:
            with self.subTest(path=path, body=fields):
                body = {"idempotency_key": "k-1", **fields}
                self.assertEqual(self.call("POST", path, body)[0], (function, body))

    def test_bad_writes_rejected_before_db(self):
        key = {"idempotency_key": "k-1"}
        bad = [
            ("/api/v7/doixe/chang", {"rows": []}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang", {"rows": [row()] * 201}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang", {"rows": [row(phi={"nangha": "300.5"})]}, "INVALID_VND"),
            ("/api/v7/doixe/chang", {"rows": [row(phi={"nangha": "-1"})]}, "INVALID_VND"),
            ("/api/v7/doixe/chang", {"rows": [row(phi={"nangha": 300})]}, "INVALID_VND"),
            ("/api/v7/doixe/chang", {"rows": [row(phi={"khac": "1"})]}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang", {"rows": [row(ngay="17/11/2026")]}, "INVALID_DATE"),
            ("/api/v7/doixe/chang", {"rows": [row(loai="xe")]}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang", {"rows": [row(tra="nguoi", nguoi_tra_id=None)]}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang", {"rows": [row(actor="x")]}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang", {"rows": [row(may_gio="1.5")]}, "INVALID_SO_LUONG"),
            ("/api/v7/doixe/chang", {"rows": [row(may_gio=5)]}, "INVALID_SO_LUONG"),
            ("/api/v7/doixe/chang", {"rows": [row(neo_ngay="0")]}, "INVALID_SO_LUONG"),
            ("/api/v7/doixe/chang", {"rows": [row(neo_ngay="366")]}, "INVALID_SO_LUONG"),
            ("/api/v7/doixe/chang", {"rows": [row(km="10000")]}, "INVALID_SO_LUONG"),
            ("/api/v7/doixe/chang/sua", {"chang_id": 9, "cot": "may_gio", "truoc": None, "gia_tri": "1000"}, "INVALID_SO_LUONG"),
            ("/api/v7/doixe/chang/sua", {"chang_id": 9, "cot": "km", "truoc": "abc", "gia_tri": "1"}, "INVALID_SO_LUONG"),
            ("/api/v7/doixe/chang/sua", {"chang_id": 9, "cot": "tra", "truoc": None, "gia_tri": "1"}, "INVALID_FIELD"),
            ("/api/v7/doixe/chang/sua", {"chang_id": 9, "cot": "phi:neo", "truoc": None, "gia_tri": "1.5"}, "INVALID_VND"),
            ("/api/v7/doixe/chang/sua", {"chang_id": 9, "cot": "ngay", "truoc": None, "gia_tri": None}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang/sua", {"chang_id": 9, "cot": "phi:neo", "gia_tri": "1"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "0", "so_du_vnd": "0"}, "INVALID_VND"),
            ("/api/v7/doixe/ung", {"nguoi_id": "4", "ngay": "2026-11-18", "so_tien_vnd": "1", "so_du_vnd": "0"}, "INVALID_REQUEST"),
            # Audit DX-03, DX-06: số đang thấy là bắt buộc và phải là chuỗi số nguyên VND (có dấu).
            ("/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "so_du_vnd": -5}, "INVALID_VND"),
            ("/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "so_du_vnd": "-0"}, "INVALID_VND"),
            ("/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "so_du_vnd": "1.5"}, "INVALID_VND"),
            ("/api/v7/doixe/hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "dong_ids": [5], "so_du_vnd": "0"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "dong_ids": [5], "so_du_vnd": "0",
                                    "tong_dong_vnd": None}, "INVALID_VND"),
            ("/api/v7/doixe/chang/xoa", {"chang_id": 9}, "INVALID_REQUEST"),
            ("/api/v7/doixe/chang/xoa", {"chang_id": 9, "tong_vnd": "1,5"}, "INVALID_VND"),
            ("/api/v7/doixe/bang-ke/dieu-chinh", {"dong_id": 5, "so_tien_vnd": "-100", "ly_do": "x"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/bang-ke/dieu-chinh", {"dong_id": 5, "so_tien_vnd": "-100", "ly_do": "x", "doi_vnd": "-1"}, "INVALID_VND"),
            ("/api/v7/doixe/bang-ke/tien-ve", {"thang": "2026-10-01", "ngay": "2026-11-18", "so_tien_vnd": "1"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/gia", {"tuyen_id": 2, "tu_ngay": "2026-01-01", "gia_vnd": "1", "xac_nhan_ngay_cu": "true"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": 4, "loai": "hang", "hang": "A", "di": "B", "den": None, "ten_goc": []}, "INVALID_REQUEST"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": 4, "loai": "hang", "hang": "A", "di": "B", "den": None, "ten_goc": [],
                                     "ten_goc_truoc": "A|B"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": None, "loai": "hang", "hang": "A", "di": "B", "den": None, "ten_goc": [],
                                     "gia_vnd": "1", "tu_ngay": "2026-01-01", "ten_goc_truoc": []}, "INVALID_REQUEST"),
            ("/api/v7/doixe/ung/huy", {"ung_id": 2, "ly_do": "  "}, "LY_DO_THIEU"),
            ("/api/v7/doixe/hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "dong_ids": [], "so_du_vnd": "0",
                                    "tong_dong_vnd": "0"}, "DONG_THIEU"),
            ("/api/v7/doixe/hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "dong_ids": [5, 5], "so_du_vnd": "0",
                                    "tong_dong_vnd": "0"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/hoan/huy", {"dot_id": 1}, "INVALID_REQUEST"),
            ("/api/v7/doixe/thang/khoa", {"thang": "2026-10-15", "khoa": True}, "INVALID_MONTH"),
            ("/api/v7/doixe/thang/khoa", {"thang": "2026-10-01", "khoa": "true"}, "INVALID_REQUEST"),
            # DOI-XE-THU-01
            ("/api/v7/doixe/bang-ke/gui", {"thang": "2026-10-02", "doi_vnd": "1", "so_chang": 1, "dau": "0123456789abcdef0123456789abcdef"}, "INVALID_MONTH"),
            ("/api/v7/doixe/bang-ke/gui", {"thang": "2026-10-01", "doi_vnd": 1, "so_chang": 1, "dau": "0123456789abcdef0123456789abcdef"}, "INVALID_VND"),
            ("/api/v7/doixe/bang-ke/gui", {"thang": "2026-10-01", "doi_vnd": "1", "so_chang": "1", "dau": "0123456789abcdef0123456789abcdef"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/bang-ke/gui", {"thang": "2026-10-01", "doi_vnd": "1", "so_chang": 1, "dau": "ABC"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/bang-ke/gui", {"thang": "2026-10-01", "doi_vnd": "1", "so_chang": 1}, "INVALID_REQUEST"),
            ("/api/v7/doixe/bang-ke/gui", {"thang": "2026-10-01", "doi_vnd": "1"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/bang-ke/dieu-chinh", {"dong_id": 5, "so_tien_vnd": "0", "ly_do": "x", "doi_vnd": "1"}, "INVALID_VND"),
            ("/api/v7/doixe/bang-ke/dieu-chinh", {"dong_id": 5, "so_tien_vnd": "-1.5", "ly_do": "x", "doi_vnd": "1"}, "INVALID_VND"),
            ("/api/v7/doixe/bang-ke/dieu-chinh", {"dong_id": 5, "so_tien_vnd": "-100", "ly_do": "  ", "doi_vnd": "1"}, "LY_DO_DIEU_CHINH"),
            ("/api/v7/doixe/bang-ke/tien-ve", {"thang": "2026-10-01", "ngay": "18/11/2026", "so_tien_vnd": "1", "con_vnd": "1"}, "INVALID_DATE"),
            ("/api/v7/doixe/bang-ke/tien-ve", {"thang": "2026-10-01", "ngay": "2026-11-18", "so_tien_vnd": "0", "con_vnd": "1"}, "INVALID_VND"),
            ("/api/v7/doixe/bang-ke/tien-ve/huy", {"tien_ve_id": 3, "ly_do": ""}, "LY_DO_THIEU"),
            ("/api/v7/doixe/thu/cuoc", {"chang_id": 9, "truoc": None, "gia_tri": "-1"}, "INVALID_VND"),
            ("/api/v7/doixe/thu/tuyen", {"chang_id": 9, "tuyen_id": 2, "nho": "true"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/gia", {"tuyen_id": 2, "tu_ngay": "2026-12-01", "gia_vnd": "0"}, "INVALID_VND"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": None, "loai": "hang", "hang": "A", "di": " ", "den": None, "ten_goc": [],
                                     "gia_vnd": "1", "tu_ngay": "2026-01-01"}, "TUYEN_THIEU"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": None, "loai": "hang", "hang": "A", "di": "B", "den": None, "ten_goc": []}, "INVALID_REQUEST"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": 4, "loai": "hang", "hang": "A", "di": "B", "den": None, "ten_goc": [],
                                     "gia_vnd": "1", "ten_goc_truoc": []}, "INVALID_REQUEST"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": 4, "loai": "xe", "hang": "A", "di": "B", "den": None, "ten_goc": [], "ten_goc_truoc": []},
             "INVALID_REQUEST"),
            ("/api/v7/doixe/tuyen", {"tuyen_id": 4, "loai": "hang", "hang": "A", "di": "B", "den": None, "ten_goc": [{"hang": "A"}],
                                     "ten_goc_truoc": []}, "INVALID_REQUEST"),
            ("/api/v7/doixe/phat-sinh", {"ma": "Neo", "ten": "Neo", "cach": "theo_ngay", "muc_vnd": None, "muc_them_vnd": None,
                                         "chi_ho": False, "cot": "ps", "ten_goc": ["Neo"]}, "INVALID_REQUEST"),
            ("/api/v7/doixe/phat-sinh", {"ma": "neo", "ten": "Neo", "cach": "theo_ngay", "muc_vnd": None, "muc_them_vnd": None,
                                         "chi_ho": False, "cot": "ps", "ten_goc": []}, "TEN_GOC_LA"),
            ("/api/v7/doixe/phat-sinh", {"ma": "neo", "ten": "Neo", "cach": "tu_do", "muc_vnd": None, "muc_them_vnd": None,
                                         "chi_ho": False, "cot": "ps", "ten_goc": ["Neo"]}, "INVALID_REQUEST"),
        ]
        for path, body, code in bad:
            with self.subTest(path=path, body=body):
                self.rejects("POST", path, {**key, **body}, code)
        self.rejects("POST", "/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "so_du_vnd": "0"}, "INVALID_REQUEST")
        self.rejects("POST", "/api/v7/doixe/khong-co", {**key}, "NOT_FOUND")

    def test_reads_and_actor_names(self):
        self.assertEqual(self.call("GET", "/api/v7/doixe")[0], ("doixe_get_tong", {"thang": None}))
        self.assertEqual(self.call("GET", "/api/v7/doixe?thang=2026-10-01")[0], ("doixe_get_tong", {"thang": "2026-10-01"}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/so?loai=nguoi&id=4&thang=2026-11-01")[0],
                         ("doixe_get_so", {"loai": "nguoi", "id": 4, "thang": "2026-11-01"}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/so?loai=xe&id=3")[0], ("doixe_get_so", {"loai": "xe", "id": 3, "thang": None}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/lich-su")[0], ("doixe_get_lich_su", {"nguoi": None, "xe": None}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/lich-su?xe=3")[0], ("doixe_get_lich_su", {"nguoi": None, "xe": 3}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/bang-ke")[0], ("doixe_get_bang_ke", {"thang": None}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/bang-ke?thang=2026-10-01")[0], ("doixe_get_bang_ke", {"thang": "2026-10-01"}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/bang-gia")[0], ("doixe_get_bang_gia", {}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/bang-ke/lich-su")[0], ("doixe_get_lich_su_thu", {}))
        self.assertEqual(doixe.parse_get(doixe.XLSX_PATH, "thang=2026-10-01"), ("doixe_get_bang_ke", {"thang": "2026-10-01"}))
        for path, code in (("/api/v7/doixe?thang=2026-10-02", "INVALID_MONTH"), ("/api/v7/doixe/so?loai=khach&id=1", "INVALID_REQUEST"),
                           ("/api/v7/doixe/so?loai=nguoi", "INVALID_REQUEST"), ("/api/v7/doixe/so?loai=nguoi&id=0", "INVALID_REQUEST"),
                           ("/api/v7/doixe/lich-su?nguoi=1&xe=2", "INVALID_REQUEST"), ("/api/v7/doixe?x=1", "INVALID_REQUEST"),
                           ("/api/v7/doixe/khac", "NOT_FOUND"), ("/api/v7/doixe/bang-ke?thang=2026-10", "INVALID_MONTH"),
                           ("/api/v7/doixe/bang-gia?ben=khac", "INVALID_REQUEST"), ("/api/v7/doixe/bang-ke/lich-su?x=1", "INVALID_REQUEST")):
            with self.subTest(path=path):
                self.rejects("GET", path, None, code)
        nested = {"events": [{"actor": "nv@gia", "truoc": {}}], "chang": [{"dong": [{"actor": "loader"}]}]}
        _, value = self.call("GET", "/api/v7/doixe/lich-su", result=nested)
        self.assertEqual(value["events"][0]["actor_name"], "nv")
        self.assertIn("actor_name", value["chang"][0]["dong"][0])

    def test_sql_matches_migration_functions(self):
        source = "".join(m.read_text(encoding="utf-8") for m in (MIGRATION, MIGRATION_THU, MIGRATION_DIEU_DO, MIGRATION_TAI_CHINH,
                                                                 MIGRATION_AUDIT))
        names = {name for granted in re.findall(r"GRANT EXECUTE ON FUNCTION (.*?) TO sokhach_app;", source, re.S)
                 for name in re.findall(r"doixe\.(\w+)\(", granted)}
        used = {re.search(r"doixe\.(\w+)\(", tables.SQL[key]).group(1) for key in tables.SQL if key.startswith("doixe_")}
        self.assertEqual(used, names, "SQL của API phải gọi đúng các hàm migration cấp cho app")
        self.assertEqual(len(doixe.POST_HANDLERS), 22)
        for code in ("NGAY_TUONG_LAI", "CHANGED", "TRUNG_CHANG", "DONG_DA_DOI", "LY_DO_THIEU", "KHONG_DOI_NGUOI_TRA", "THANG_KHOA_CHUYEN"):
            self.assertIn(code, tables.ERRORS)
            self.assertIn(f"'{code}'", source)
        for code in set(re.findall(r"RAISE EXCEPTION '([A-Z_]+)'", source)) - {"IMMUTABLE", "ACTOR_REQUIRED"}:
            self.assertIn(code, tables.ERRORS, f"mã lỗi {code} của doixe phải có câu thông báo")

    def test_body_limit(self):
        self.assertEqual(api.body_limit("/api/v7/doixe/chang"), doixe.MAX_CHANG_BODY)
        self.assertEqual(api.body_limit("/api/v7/doixe/ung"), tables.MAX_BODY)
        rows = {"idempotency_key": "k", "rows": [row(ghi_chu="x" * 190, noi_lay="y" * 190, noi_ha="z" * 190) for _ in range(200)]}
        raw = json.dumps(rows).encode()
        self.assertGreater(len(raw), tables.MAX_BODY)
        self.assertLess(len(raw), doixe.MAX_CHANG_BODY)
        runner = FakePsql()
        status, _ = api.handle("POST", "/api/v7/doixe/chang", self.headers, raw, runner, port=8780, host="127.0.0.1", actor="nv")
        self.assertEqual(status, 200)
        with self.assertRaises(api.ApiError) as caught:
            api.handle("POST", "/api/v7/doixe/ung", self.headers, raw, runner, port=8780, host="127.0.0.1", actor="nv")
        self.assertEqual(caught.exception.code, "BODY_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
