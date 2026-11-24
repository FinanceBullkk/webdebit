"""SO-TIEN P0-a lát 2: file Excel sổ tiền cho kế toán — ba tab đọc lại đúng, ô trống không thành 0, chữ bắt đầu bằng "=" vẫn là chữ,
chỉ VND, tên file ASCII. Dữ liệu bịa."""

import datetime as dt
import io
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_tien_xlsx as export  # noqa: E402
import v7_xlsx_writer  # noqa: E402
from test_v7_api_tien import export_sample  # noqa: E402


class TienXlsxTest(unittest.TestCase):
    def test_three_tabs_read_back(self):
        name, body = export.build(export_sample())
        self.assertEqual(name, "so-tien-NHGIA-1234-2026-10-01-2026-10-31.xlsx")
        book = v7_xlsx_writer.read_workbook(body)
        self.assertEqual(list(book), ["Giao dịch", "Phân bổ", "Ngày"])
        tx = book["Giao dịch"]
        self.assertEqual(tx[0][0], "Sổ tiền NHGIA ••••1234 (VND)")
        self.assertEqual(tx[1][0], "Phap nhan gia · kỳ 01/10/2026 – 31/10/2026")
        self.assertEqual((tx[2][0], tx[2][4], tx[3][0], tx[3][4]), ("Số dư sổ đầu kỳ", 1000000, "Số dư sổ cuối kỳ", 1030000))
        self.assertIn("Xuất bởi ketoan@gia.test lúc 25/11/2026 17:00", tx[4][0])
        self.assertEqual(tx[5][:5], ["Ngày ghi sổ", "Ngày hiệu lực", "Mã giao dịch NH", "Nội dung", "Thu"])
        self.assertEqual(tx[6], [dt.date(2026, 10, 1), None, "FT1", "=CK GIA MOT", 50000, None, "Đã phân bổ đủ", 50000, 0, "9"])
        self.assertEqual(tx[7], [dt.date(2026, 10, 2), dt.date(2026, 10, 2), None, None, None, 20000, "Chưa ghép", 0, 20000, "9, 10"])
        # Bộ đọc lại bỏ ô trống cuối hàng (ghi chú trống không thành chữ nào).
        self.assertEqual(book["Phân bổ"][1], [41, dt.date(2026, 10, 1), "Thu", "Tiền khách chưa rõ khoản", "Mã sổ khách 12", 50000])
        self.assertEqual(book["Ngày"][1], [dt.date(2026, 10, 1), "Đủ", "Đã ký", "Chưa ký"])

    def test_text_never_becomes_formula(self):
        _, body = export.build(export_sample())
        with zipfile.ZipFile(io.BytesIO(body)) as package:
            sheet = package.read("xl/worksheets/sheet1.xml").decode()
        self.assertNotIn("<f>", sheet)
        self.assertIn('t="inlineStr"', sheet)
        self.assertIn("=CK GIA MOT", sheet)

    def test_only_vnd(self):
        data = export_sample()
        data["account"]["currency"] = "USD"
        with self.assertRaises(export.ExportError):
            export.build(data)


if __name__ == "__main__":
    unittest.main()
