"""THONG-TIN-CTY-01: job đọc Sheet thông tin khách hàng và route GET /api/v7/company-info. Dữ liệu giả."""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "web"))
import v7_company_info as served  # noqa: E402
import v7_company_info_snapshot as job  # noqa: E402
import v7_ledger_api as api  # noqa: E402

# Hình dạng như tab thật (đo trên bản đọc ngày 12/11/2026, chỉ số đếm): phần đầu có tên ở A và nhãn ở B, phần sau không nhãn,
# dòng ngân hàng ở E có lúc nằm sau một dòng trống. Dữ liệu giả.
CUSTOMERS = [
    [],
    ["", "", "SHIPPER", "THONG TIN XUAT HOA DON", "THONG TIN NGAN HANG"],
    ["THU A", "COMPANY:", "THU A COMPANY LIMITED", "CONG TY TNHH THU A", "THU A COMPANY LIMITED"],   # dòng 3
    ["", "ADD", "1 FAKE ST", "1 DUONG GIA", "1 FAKE ST"],
    ["", "TAX CODE", "0000000001", "0000000001", ""],
    ["", "PHONE/MAIL", "", "", "a@thu.test"],
    ["", "", "", "", "BANK: NH GIA A"],
    [],
    ["", "", "", "", "ACC: 111"],                                                                  # dòng 9: ngân hàng của THU A
    [],
    ["", "", "THU B CO.,LTD", "CONG TY TNHH THU B", "THU B CO.,LTD"],                               # dòng 11: phần không nhãn
    ["", "", "ADD: 2 FAKE RD", "DC: 2 DUONG GIA", ""],
    ["", "", "TAX CODE: 0000000002", "MST: 0000000002", ""],
    ["", "", "DIRECTOR: MR B", "GIAM DOC: ONG B", ""],
    ["", "", "", "", "ACC: 222"],
    ["", "", "THU C CO.,LTD", "CONG TY TNHH THU C", ""],                                           # dòng 16: liền sau, không dòng trống
    ["", "", "ADD: 3 FAKE RD", "", ""],
    ["", "", "", "D3", ""],
    ["", "", "THU D CO.,LTD", "CONG TY TNHH THU D", ""],                                           # dòng 19: sau dòng chỉ có D
    ["", "", "", "", ""],
]
ACCOUNTS = [
    [],
    ["", "收款人资料\nACCOUNT NUMBER INFORMATION\n(VND)\nNGAN HANG GIA", "公司全称 \nACC NAME", "CONG TY GIA"],
    ["", "", "公司地址\nADDRESS", "1 DUONG GIA"],
    ["", "", "银行名称\nBANK NAME", "TEST BANK"],
    ["", "", "银行地址\nBANK ADDRESS", "2 DUONG NGAN HANG GIA"],
    ["", "", "银行账户\nACCOUNT NUMBER", "1,234,567,890"],
    [],
    ["", "收款人资料\nACCOUNT NUMBER INFORMATION\n(USD)\nBANK B", "ACC NAME", "TEST CO"],
    ["", "", "BANK NAME", "BANK B"],
    ["", "", "ACCOUNT NUMBER", "000123"],
    ["", "", "SWIFT CODE", "TESTVNVX"],
    ["", "", "GHI CHU", "chi de doc"],
    ["", "KHOI KHONG SO", "BANK NAME", "BANK C"],
]


class ParseTest(unittest.TestCase):
    def test_customers_are_blocks_labeled_and_unlabeled(self):
        customers, skipped = job.parse_customers(CUSTOMERS)
        self.assertEqual(skipped, 0)
        self.assertEqual([(item["name"], item["rows"]) for item in customers],
                         [("THU A", [3, 9]), ("THU B CO.,LTD", [11, 15]), ("THU C CO.,LTD", [16, 18]), ("THU D CO.,LTD", [19, 19])])
        a, b, c, _ = customers
        self.assertEqual(a["company"], "THU A COMPANY LIMITED")
        self.assertEqual(a["invoice"], "CONG TY TNHH THU A\nADD: 1 DUONG GIA\nTAX CODE: 0000000001")   # nhãn cột B in kèm, trừ COMPANY
        self.assertEqual(a["bank"], "THU A COMPANY LIMITED\n1 FAKE ST\na@thu.test\nBANK: NH GIA A\nACC: 111")   # dòng sau dòng trống vẫn của A
        self.assertEqual(b["invoice"], "CONG TY TNHH THU B\nDC: 2 DUONG GIA\nMST: 0000000002\nGIAM DOC: ONG B")
        self.assertEqual(b["bank"], "THU B CO.,LTD\nACC: 222")
        self.assertEqual(c["invoice"], "CONG TY TNHH THU C\nD3")
        self.assertEqual(a["header"], {"name": "THU A COMPANY LIMITED", "address": "1 FAKE ST", "tax_id": "0000000001", "tel": None, "email": None})
        self.assertEqual(b["header"], {"name": "THU B CO.,LTD", "address": "2 FAKE RD", "tax_id": "0000000002", "tel": None, "email": None})

    def test_header_fields_prefer_new_address_and_split_phone_mail(self):
        self.assertEqual(job.header_fields("THU E CO.,LTD\nADD: cu\nNEW ADD: moi\nTAX CODE: 0000000005\nPHONE/MAIL: 0900 000 000 / e@thu.test"),
                         {"name": "THU E CO.,LTD", "address": "moi", "tax_id": "0000000005", "tel": "0900 000 000", "email": "e@thu.test"})
        # Không nhãn: dòng thứ hai là địa chỉ; nhãn MST, TEL viết trong ô.
        self.assertEqual(job.header_fields("THU F CO.,LTD\n5 FAKE AVE, FAKE CITY\nMST: 0000000006\nTEL: 028 000"),
                         {"name": "THU F CO.,LTD", "address": "5 FAKE AVE, FAKE CITY", "tax_id": "0000000006", "tel": "028 000", "email": None})
        self.assertEqual(job.header_fields(""), dict.fromkeys(("name", "address", "tax_id", "tel", "email")))

    def test_customers_without_header_is_a_shape_error(self):
        with self.assertRaises(job.SheetShapeError):
            job.parse_customers([["", "", "TEN", "HOA DON"]])
        with self.assertRaises(job.SheetShapeError):
            job.parse_customers([["SHIPPER", "GHI CHU"]])

    def test_accounts_split_by_title_column_and_labels_read_in_english(self):
        accounts, skipped = job.parse_accounts(ACCOUNTS)
        self.assertEqual(skipped, 1)   # khối không có số tài khoản
        first, second = accounts
        self.assertEqual((first["label"], first["currency"], first["beneficiary"], first["address"], first["bank"], first["bank_address"],
                          first["account"], first["swift"]),
                         ("VND · NGAN HANG GIA", "VND", "CONG TY GIA", "1 DUONG GIA", "TEST BANK", "2 DUONG NGAN HANG GIA", "1234567890", None))
        self.assertEqual((second["label"], second["account"], second["swift"]), ("USD · BANK B", "000123", "TESTVNVX"))
        self.assertEqual(second["lines"][-1], {"label": "GHI CHU", "value": "chi de doc"})   # nhãn lạ vẫn hiện ở tab
        self.assertRegex(first["id"], r"^a[0-9a-f]{12}$")
        self.assertNotEqual(first["id"], second["id"])
        again, _ = job.parse_accounts(ACCOUNTS)
        self.assertEqual([item["id"] for item in again], [first["id"], second["id"]])   # id bền qua các lần đọc

    def test_bank_column_accounts_belong_to_their_block(self):
        # TAI-KHOAN-COT-E-01: cột E cùng khối là tài khoản của chính công ty; dòng sau chỗ hở vẫn của khối đó.
        customers, _ = job.parse_customers(CUSTOMERS)
        a, b, c, _d = customers
        self.assertEqual([(item["beneficiary"], item["bank"], item["account"]) for item in a["accounts"]],
                         [("THU A COMPANY LIMITED", "NH GIA A", "111")])
        self.assertEqual([(item["beneficiary"], item["account"]) for item in b["accounts"]], [("THU B CO.,LTD", "222")])
        self.assertEqual(c["accounts"], [])

    def test_bank_column_handwritten_labels(self):
        # Các kiểu viết đo trên Sheet thật ngày 12/11/2026, dữ liệu giả.
        two_with_gap = ["THU M COMPANY LIMITED", "ADD: 1 FAKE ST", "ACCOUNT NUMBER: 1000 0001", "ACCOUNT CURRENCY: USD",
                        "NAME OF BANK: NH GIA M1, CHI NHANH A", "BANK'S ADDRESS: 2 DUONG NGAN HANG", "SWIFT CODE: GIAMVNVX",
                        "", "-THU M COMPANY LIMITED", "-ADD: 1 FAKE ST", "-BANK NAME: NH GIA M2", "-BANK ADDRESS:3 DUONG",
                        "-ACCOUNT NUMBER :20000002  (USD)", "-SWIFTCODE:GIAM2VNX"]
        first, second = job.parse_bank_column(two_with_gap, "THU M CO")
        self.assertEqual((first["beneficiary"], first["address"], first["bank"], first["bank_address"], first["account"], first["currency"], first["swift"]),
                         ("THU M COMPANY LIMITED", "1 FAKE ST", "NH GIA M1, CHI NHANH A", "2 DUONG NGAN HANG", "1000 0001", "USD", "GIAMVNVX"))
        self.assertEqual((second["bank"], second["bank_address"], second["account"], second["currency"]), ("NH GIA M2", "3 DUONG", "20000002", "USD"))
        self.assertRegex(first["id"], r"^e[0-9a-f]{12}$")
        self.assertNotEqual(first["id"], second["id"])

        # Không chỗ hở: ACC NAME lặp lại là tài khoản mới; BENEFICIARY’S BANK là ngân hàng; ADD sau ngân hàng là địa chỉ ngân hàng.
        repeated = ["GHI CHU KHACH X DUNG TK NAY:", "ACC NAME : THU N CO", "5 FAKE RD", "TEL/FAX : 000 / 111", "TAX CODE : 0 0 0",
                    "BENEFICIARY’S BANK: NH GIA N1", "ADDRESS : 6 DUONG, PHUONG A", "QUAN B, THANH PHO C", "USD ACCOUNT NUMBER: 3000003",
                    "SWIFT CODE: GIANVNVX", "ACC NAME: CONG TY THU N", "BANK NAME: NH GIA N2", "ADD: 7 DUONG", "ACCOUNT NO.:4000004",
                    "SWIFT CODE: GIAN2VNX", "RMB ACCOUNT", "NEW UPDATE 3/11/2026"]
        n1, n2 = job.parse_bank_column(repeated, "THU N CO")
        self.assertEqual((n1["beneficiary"], n1["address"], n1["bank"], n1["bank_address"], n1["account"], n1["currency"]),
                         ("THU N CO", "5 FAKE RD", "NH GIA N1", "6 DUONG, PHUONG A QUAN B, THANH PHO C", "3000003", "USD"))
        self.assertEqual((n2["beneficiary"], n2["bank_address"], n2["account"], n2["currency"]), ("CONG TY THU N", "7 DUONG", "4000004", "CNY"))

        # Không có tên người nhận thì lấy tên công ty; NEW ADD thay địa chỉ cũ; ACOUNT viết sai vẫn nhận; dòng không có số bị bỏ.
        bare = ["ACC NAME: THU P CO", "1 DUONG CU", "NEW ADD: 2 DUONG MOI", "ACOUNT NUMBER (USD): 0500  0000  0005", "BANK: NH GIA P"]
        (p,) = job.parse_bank_column(bare, "THU P CO")
        self.assertEqual((p["address"], p["account"], p["currency"], p["bank"]), ("2 DUONG MOI", "0500 0000 0005", "USD", "NH GIA P"))
        (q,) = job.parse_bank_column(["ACCOUNT NO.: 5000005", "BANK: NH GIA Q"], "THU Q CO")
        self.assertEqual((q["beneficiary"], q["currency"]), ("THU Q CO", None))
        self.assertEqual(job.parse_bank_column(["ACC NAME: THU R", "BANK NAME: NH GIA R", "VND ACCOUNT NO:"], "THU R"), [])

    def test_no_account_number_anywhere_is_a_shape_error(self):
        with self.assertRaises(job.SheetShapeError):
            job.parse_accounts([["", "KHOI", "BANK NAME", "X"]])

    def test_fold_ignores_nfd_and_case(self):
        self.assertEqual(job.fold("TÀI KHOẢN usd"), job.fold("TÀI KHOẢN USD"))
        self.assertEqual(job.fold("Đường"), "DUONG")


class RunTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.credentials = self.dir / "sa.json"
        self.credentials.write_text(json.dumps({"type": "service_account", "client_email": "x@y", "private_key": "k"}), encoding="utf-8")
        self.output = self.dir / "company-info.json"

    def opener(self, customers, accounts, titles=("THÔNG TIN CTY", "TÀI KHOẢN USD", "KHAC")):
        seen = []

        def open_(request, timeout):
            seen.append(request.full_url)
            if "values:batchGet" in request.full_url:
                body = {"valueRanges": [{"range": "'THÔNG TIN CTY'!A1:Z9", "values": customers},
                                        {"range": "'TÀI KHOẢN USD'!A1:Z9", "values": accounts}]}
            else:
                body = {"sheets": [{"properties": {"title": title}} for title in titles]}
            return io.BytesIO(json.dumps(body).encode())
        return open_, seen

    def test_run_writes_snapshot_mode_600_and_reads_formatted_values(self):
        opener, seen = self.opener(CUSTOMERS, ACCOUNTS)
        snapshot = job.run_once(str(self.credentials), "s" * 30, str(self.output), token_exchange=lambda _c: "tok", opener=opener)
        self.assertEqual(snapshot["counts"], {"accounts": 2, "customers": 4, "skipped_accounts": 1, "skipped_customers": 0})
        self.assertIn("valueRenderOption=FORMATTED_VALUE", seen[-1])
        self.assertIn("TA%CC%80I", seen[-1])   # dùng đúng tên tab trên Sheet (NFD), không tên gõ trong code
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8"))["counts"]["accounts"], 2)
        if os.name == "posix":
            self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_shape_error_keeps_previous_file(self):
        self.output.write_text('{"old": true}', encoding="utf-8")
        opener, _ = self.opener([["khong co tieu de"]], ACCOUNTS)
        with self.assertRaises(job.SheetShapeError):
            job.run_once(str(self.credentials), "s" * 30, str(self.output), token_exchange=lambda _c: "tok", opener=opener)
        self.assertEqual(self.output.read_text(encoding="utf-8"), '{"old": true}')
        opener, _ = self.opener(CUSTOMERS, ACCOUNTS, titles=("THÔNG TIN CTY",))
        with self.assertRaises(job.SheetShapeError):
            job.run_once(str(self.credentials), "s" * 30, str(self.output), token_exchange=lambda _c: "tok", opener=opener)

    def test_main_prints_counts_only(self):
        opener, _ = self.opener(CUSTOMERS, ACCOUNTS)
        argv = ["v7_company_info_snapshot.py", "--credentials", str(self.credentials), "--spreadsheet-id", "s" * 30, "--output", str(self.output)]
        real = job.run_once
        with patch.object(sys, "argv", argv), patch("sys.stdout", new_callable=io.StringIO) as out, \
                patch.object(job, "run_once", lambda *a: real(*a, token_exchange=lambda _c: "tok", opener=opener)):
            self.assertEqual(job.main(), 0)
        printed = out.getvalue()
        self.assertIn('"accounts": 2', printed)
        self.assertNotIn("1234567890", printed)
        self.assertNotIn("CONG TY TNHH THU A", printed)


class RouteTest(unittest.TestCase):
    def write(self, data) -> str:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "company-info.json"
        path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def test_missing_file_is_not_available_and_bad_file_is_503(self):
        self.assertEqual(served.handle_get("", str(Path(tempfile.gettempdir()) / "khong-co-company-info.json")), (200, {"available": False}))
        for data in ("{oops", {"accounts": "x", "customers": []}, {"accounts": [{"id": 1, "lines": []}], "customers": []}):
            with self.subTest(data=data), self.assertRaises(served.InfoError) as caught:
                served.handle_get("", self.write(data))
            self.assertEqual((caught.exception.status, caught.exception.code), (503, "COMPANY_INFO_UNAVAILABLE"))
        with self.assertRaises(served.InfoError) as caught:
            served.handle_get("x=1", self.write({}))
        self.assertEqual(caught.exception.status, 400)

    def test_snapshot_from_job_is_served(self):
        snapshot = job.build(CUSTOMERS, ACCOUNTS)
        status, body = served.handle_get("", self.write(snapshot))
        self.assertEqual(status, 200)
        self.assertTrue(body["available"])
        self.assertEqual(body["read_at"], snapshot["runner"]["created_at"])
        self.assertEqual([item["label"] for item in body["accounts"]], ["VND · NGAN HANG GIA", "USD · BANK B"])
        self.assertEqual((body["customers"][0]["name"], body["customers"][0]["rows"]), ("THU A", [3, 9]))
        own = body["customers"][0]["accounts"]
        self.assertEqual([(item["beneficiary"], item["bank"], item["account"]) for item in own], [("THU A COMPANY LIMITED", "NH GIA A", "111")])
        self.assertNotIn("lines", own[0])

    def test_old_snapshot_without_own_accounts_still_served(self):
        snapshot = job.build(CUSTOMERS, ACCOUNTS)
        for item in snapshot["customers"]:
            del item["accounts"]
        _, body = served.handle_get("", self.write(snapshot))
        self.assertEqual([item["accounts"] for item in body["customers"]], [[], [], [], []])
        snapshot["customers"][0]["accounts"] = "x"
        with self.assertRaises(served.InfoError):
            served.handle_get("", self.write(snapshot))

    def test_route_goes_through_api_without_db(self):
        runner = Mock()
        args = {"port": 8780, "host": "127.0.0.1", "actor": "nguoi-thu"}
        with patch.dict(os.environ, {"WEBDEBIT_COMPANY_INFO_PATH": self.write(job.build(CUSTOMERS, ACCOUNTS))}):
            status, body = api.handle("GET", "/api/v7/company-info", {"Host": "127.0.0.1:8780"}, b"", runner, **args)
        self.assertEqual((status, body["counts"]["accounts"]), (200, 2))
        runner.run.assert_not_called()
        self.assertEqual(api.ASSETS["/thong-tin-cty.html"][0], "thong-tin-cty.html")


if __name__ == "__main__":
    unittest.main()
