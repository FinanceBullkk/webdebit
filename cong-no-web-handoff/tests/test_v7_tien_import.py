"""SO-TIEN P0-a lát 2: bộ đọc file sao kê — mẫu thử demo-csv@1 (chỉ dữ liệu bịa) ra StatementLine v1 đúng, lỗi cấu trúc báo đúng dòng,
giá trị sai nghiệp vụ để SQL thành lỗi dòng, mẫu thử chỉ bật khi WEBDEBIT_TIEN_DEMO=1."""

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_tien_import as reader

HEAD = "#period,2026-10-01,2026-10-03,{state}\n#opening,1000000\n#closing,1030000\ndate,ref,description,debit,credit,balance\n"


def csv(rows: str, state: str = "partial", head: str | None = None) -> bytes:
    return ((HEAD.format(state=state) if head is None else head) + rows).encode()


class DemoCsvTest(unittest.TestCase):
    def parse(self, data: bytes) -> reader.Parsed:
        return reader.parse_demo_csv(data, "VND")

    def fails(self, data: bytes, message: str, line: int | None) -> None:
        with self.assertRaises(reader.ParseError) as caught:
            self.parse(data)
        self.assertEqual((caught.exception.message, caught.exception.line), (message, line))

    def test_reads_period_balances_and_lines(self):
        parsed = self.parse(b"\xef\xbb\xbf" + csv("2026-10-01,FT1,CK GIA MOT,,50000,1050000\n\n2026-10-02, ,  CHI GIA HAI ,20000,,1030000\n"))
        self.assertEqual((parsed.period_from, parsed.period_to, parsed.last_day_complete, parsed.opening_minor, parsed.closing_minor),
                         ("2026-10-01", "2026-10-03", False, "1000000", "1030000"))
        self.assertEqual(parsed.lines[0], {"line_no": 1, "booking_date": "2026-10-01", "direction": "in", "amount_minor": "50000",
                                           "currency": "VND", "description": "CK GIA MOT", "bank_ref": "FT1",
                                           "balance_after_minor": "1050000",
                                           "cells": {"date": "2026-10-01", "ref": "FT1", "description": "CK GIA MOT", "debit": "",
                                                     "credit": "50000", "balance": "1050000"}})
        second = parsed.lines[1]
        self.assertEqual((second["line_no"], second["direction"], second["amount_minor"], second["bank_ref"], second["description"]),
                         (2, "out", "20000", None, "CHI GIA HAI"))
        self.assertEqual(second["cells"]["description"], "  CHI GIA HAI ", "ô gốc giữ nguyên văn")
        self.assertTrue(self.parse(csv("", state="complete")).last_day_complete)
        self.assertEqual(self.parse(csv("")).lines, [], "kỳ không phát sinh vẫn là file hợp lệ (chứng minh độ phủ)")
        no_balance = self.parse(csv("2026-10-01,,CK,,5,\n", head="#period,2026-10-01,2026-10-01,complete\n"
                                                              "date,ref,description,debit,credit,balance\n"))
        self.assertEqual((no_balance.opening_minor, no_balance.closing_minor, no_balance.lines[0]["balance_after_minor"]),
                         (None, None, None))

    def test_business_errors_left_to_sql(self):
        parsed = self.parse(csv("2026-10-01,,HAI CHIEU,5,5,\n2026-10-01,,KHONG TIEN,,,\n2026-10-01,,SO LE,,12.5,\n2026-11-30,,NGOAI KY,,7,\n"))
        self.assertEqual([(ln["direction"], ln["amount_minor"], ln["booking_date"]) for ln in parsed.lines],
                         [(None, None, "2026-10-01"), (None, None, "2026-10-01"), ("in", "12.5", "2026-10-01"), ("in", "7", "2026-11-30")])

    def test_structure_errors_name_the_line(self):
        self.fails(csv("01/10/2026,,CK,,5,\n"), "Ngày phải viết dạng năm-tháng-ngày (YYYY-MM-DD).", 5)
        self.fails(csv("2026-02-30,,CK,,5,\n"), "Ngày không có thật.", 5)
        self.fails(csv("2026-10-01,,CK,,5,1.000\n"), "Số dư sau phải là số nguyên, không dấu chấm, phẩy hay khoảng trắng.", 5)
        self.fails(csv("2026-10-01,,CK,,5\n"), "Dòng giao dịch phải đủ 6 ô.", 5)
        self.fails(csv("2026-10-01,,CK,,5,\n", head="date,ref,description,debit,credit,balance\n"), "Thiếu dòng #period (kỳ của sao kê).", None)
        self.fails(csv("", head="#period,2026-10-01,2026-10-03,partial\n"), "Thiếu dòng tiêu đề date,ref,description,debit,credit,balance.", None)
        self.fails(csv("", head="#period,2026-10-01,2026-10-03,partial\nngay,so tien\n"),
                   "Thiếu dòng tiêu đề date,ref,description,debit,credit,balance.", 2)
        self.fails(csv("", head="#period,2026-10-01,2026-10-03,xong\n"),
                   "Dòng #period: ô cuối phải là complete (ngày cuối đã trọn) hoặc partial.", 1)
        self.fails(csv("", head="#period,2026-10-01,2026-10-03,partial\n#period,2026-10-01,2026-10-03,partial\n"),
                   "Dòng thông tin lạ hoặc lặp lại.", 2)
        self.fails(csv("", head="#period,2026-10-01,2026-10-03,partial\n#tai_khoan,1234\n"), "Dòng thông tin lạ hoặc lặp lại.", 2)
        self.fails(csv("", head="#period,2026-10-01,2026-10-03,partial\n#opening,1 000\n"),
                   "Số dư đầu phải là số nguyên, không dấu chấm, phẩy hay khoảng trắng.", 2)
        self.fails(csv("", head="#period,2026-10-05,2026-10-03,partial\ndate,ref,description,debit,credit,balance\n"),
                   "Ngày đầu kỳ sau ngày cuối kỳ.", None)
        self.fails(b"\xff\xfe khong phai utf-8", "File phải là chữ UTF-8.", None)
        self.fails(csv("2026-10-01,,CK" + chr(0) + "GIA,,5,\n"), "File có ký tự lạ (NUL); tải lại file từ ngân hàng.", None)
        self.fails(csv("2026-10-01,," + "x" * 1001 + ",,5,\n"), "Nội dung hoặc mã giao dịch quá dài.", 5)

    def test_row_limit(self):
        with mock.patch.object(reader, "MAX_ROWS", 2):
            self.fails(csv("2026-10-01,,A,,1,\n2026-10-01,,B,,1,\n2026-10-01,,C,,1,\n"),
                       "File quá 20000 dòng giao dịch; tải kỳ ngắn hơn.", 7)


class RegistryTest(unittest.TestCase):
    def test_demo_template_only_when_enabled(self):
        with mock.patch.dict(os.environ, {"WEBDEBIT_TIEN_DEMO": "1"}):
            self.assertEqual([t.id for t in reader.available()], ["demo-csv@1"])
            self.assertIs(reader.get("demo-csv@1"), reader.TEMPLATES["demo-csv@1"])
        for value in ("", "0", "true"):
            with mock.patch.dict(os.environ, {"WEBDEBIT_TIEN_DEMO": value}):
                self.assertEqual(reader.available(), [])
                self.assertIsNone(reader.get("demo-csv@1"))
        self.assertIsNone(reader.get(None))
        self.assertIsNone(reader.get("vcb-xlsx@1"), "mẫu VCB chưa có tới khi có file mẫu (QD-07)")


if __name__ == "__main__":
    unittest.main()
