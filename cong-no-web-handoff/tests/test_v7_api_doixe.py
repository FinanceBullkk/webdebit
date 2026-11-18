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
            ("/api/v7/doixe/chang/xoa", "doixe_xoa_chang", {"chang_id": 9}),
            ("/api/v7/doixe/ung", "doixe_ghi_ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "3000000"}),
            ("/api/v7/doixe/ung", "doixe_ghi_ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "3000000", "ghi_chu": "đi đường"}),
            ("/api/v7/doixe/ung/huy", "doixe_huy_ung", {"ung_id": 2, "ly_do": "ghi trùng"}),
            ("/api/v7/doixe/hoan", "doixe_ghi_hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "0", "dong_ids": [5, 6]}),
            ("/api/v7/doixe/hoan/huy", "doixe_huy_hoan", {"dot_id": 1, "ly_do": "chuyển nhầm"}),
            ("/api/v7/doixe/thang/khoa", "doixe_khoa_thang", {"thang": "2026-10-01", "khoa": False}),
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
            ("/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "0"}, "INVALID_VND"),
            ("/api/v7/doixe/ung", {"nguoi_id": "4", "ngay": "2026-11-18", "so_tien_vnd": "1"}, "INVALID_REQUEST"),
            ("/api/v7/doixe/ung/huy", {"ung_id": 2, "ly_do": "  "}, "LY_DO_THIEU"),
            ("/api/v7/doixe/hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "dong_ids": []}, "DONG_THIEU"),
            ("/api/v7/doixe/hoan", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1", "dong_ids": [5, 5]}, "INVALID_REQUEST"),
            ("/api/v7/doixe/hoan/huy", {"dot_id": 1}, "INVALID_REQUEST"),
            ("/api/v7/doixe/thang/khoa", {"thang": "2026-10-15", "khoa": True}, "INVALID_MONTH"),
            ("/api/v7/doixe/thang/khoa", {"thang": "2026-10-01", "khoa": "true"}, "INVALID_REQUEST"),
        ]
        for path, body, code in bad:
            with self.subTest(path=path, body=body):
                self.rejects("POST", path, {**key, **body}, code)
        self.rejects("POST", "/api/v7/doixe/ung", {"nguoi_id": 4, "ngay": "2026-11-18", "so_tien_vnd": "1"}, "INVALID_REQUEST")
        self.rejects("POST", "/api/v7/doixe/khong-co", {**key}, "NOT_FOUND")

    def test_reads_and_actor_names(self):
        self.assertEqual(self.call("GET", "/api/v7/doixe")[0], ("doixe_get_tong", {"thang": None}))
        self.assertEqual(self.call("GET", "/api/v7/doixe?thang=2026-10-01")[0], ("doixe_get_tong", {"thang": "2026-10-01"}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/so?loai=nguoi&id=4&thang=2026-11-01")[0],
                         ("doixe_get_so", {"loai": "nguoi", "id": 4, "thang": "2026-11-01"}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/so?loai=xe&id=3")[0], ("doixe_get_so", {"loai": "xe", "id": 3, "thang": None}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/lich-su")[0], ("doixe_get_lich_su", {"nguoi": None, "xe": None}))
        self.assertEqual(self.call("GET", "/api/v7/doixe/lich-su?xe=3")[0], ("doixe_get_lich_su", {"nguoi": None, "xe": 3}))
        for path, code in (("/api/v7/doixe?thang=2026-10-02", "INVALID_MONTH"), ("/api/v7/doixe/so?loai=khach&id=1", "INVALID_REQUEST"),
                           ("/api/v7/doixe/so?loai=nguoi", "INVALID_REQUEST"), ("/api/v7/doixe/so?loai=nguoi&id=0", "INVALID_REQUEST"),
                           ("/api/v7/doixe/lich-su?nguoi=1&xe=2", "INVALID_REQUEST"), ("/api/v7/doixe?x=1", "INVALID_REQUEST"),
                           ("/api/v7/doixe/khac", "NOT_FOUND")):
            with self.subTest(path=path):
                self.rejects("GET", path, None, code)
        nested = {"events": [{"actor": "nv@gia", "truoc": {}}], "chang": [{"dong": [{"actor": "loader"}]}]}
        _, value = self.call("GET", "/api/v7/doixe/lich-su", result=nested)
        self.assertEqual(value["events"][0]["actor_name"], "nv")
        self.assertIn("actor_name", value["chang"][0]["dong"][0])

    def test_sql_matches_migration_functions(self):
        source = MIGRATION.read_text(encoding="utf-8")
        granted = re.search(r"GRANT EXECUTE ON FUNCTION (.*?) TO sokhach_app;", source, re.S).group(1)
        names = set(re.findall(r"doixe\.(\w+)\(", granted))
        used = {re.search(r"doixe\.(\w+)\(", tables.SQL[key]).group(1) for key in tables.SQL if key.startswith("doixe_")}
        self.assertEqual(used, names, "SQL của API phải gọi đúng các hàm migration cấp cho app")
        self.assertEqual(len(doixe.POST_HANDLERS), 8)
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
