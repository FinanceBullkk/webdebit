"""DOI-XE-THU-01: file Excel bảng kê gửi HTH — cùng cột với file debit, "Kính gửi", tổng khớp tổng máy chủ, ô trống không thành 0."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_doixe_xlsx as bk  # noqa: E402
from v7_xlsx_writer import read_workbook  # noqa: E402

HEADER = ["STT", "NGÀY", "SỐ CONT", "CONT KÉO", "TỈNH", "KHO ĐÓNG HÀNG", "TÀI XẾ", "SỐ XE", "NƠI LẤY", "NƠI HẠ", "TÊN HÀNG", "CƯỚC",
          "ĐÓNG GHÉP", "PHÁT SINH", "GHI CHÚ", "CƯỚC TỔNG", "KẾ TOÁN NOTE", "+ - TIỀN", "CHECK LÝ DO"]


def item(goc, ten, ma, tien, cot="ps", chi_ho=False):
    return {"goc": goc, "ten": ten, "ma": ma, "so_tien_vnd": tien, "chi_ho": chi_ho, "cot": cot}


def data(sent=True):
    lines = [
        {"stt": 1, "ngay": "2026-10-02", "container": "MAUU1000001", "loai": "hang", "tinh": "TỈNH GIẢ", "kho": "KHO GIẢ",
         "tai_xe": "Tài xế giả", "so_xe": "99Z-000.01", "noi_lay": "CẢNG A", "noi_ha": "CẢNG B", "ten_hang": "HÀNG GIẢ",
         "cuoc_vnd": "1000000", "ghep_vnd": None, "ps_vnd": "360000", "chi_ho_vnd": "360000",
         "ps": [item("Kiểm hoá 150k", "Kiểm hoá", "kiem_hoa", "150000", chi_ho=True), item("Xí cont 210k", "Xí cont", "xi_cont", "210000", chi_ho=True),
                {"goc": "Cân", "loi": "Thiếu số tiền"}],
         "dc_vnd": "-200000", "dieu_chinh": [{"ly_do": "HTH báo trùng", "actor": "nv@gia", "actor_name": "nv", "luc": "05/11 09:00",
                                              "so_tien_vnd": "-200000"}]},
        {"stt": 2, "ngay": "2026-10-03", "container": "MAUU1000002", "loai": "chuyen_cang", "tinh": None, "kho": None, "tai_xe": None,
         "so_xe": "99Z-000.02", "noi_lay": None, "noi_ha": None, "ten_hang": None, "cuoc_vnd": None, "ghep_vnd": "2900000",
         "ps_vnd": None, "chi_ho_vnd": None, "ps": [item("Đóng ghép 2 kho 2900k", "Đóng ghép 2 kho", "dong_ghep", "2900000", "ghep")],
         "dc_vnd": None, "dieu_chinh": []},
    ]
    if not sent:
        for line in lines:
            line.pop("stt"), line.pop("dc_vnd"), line.pop("dieu_chinh")
    tong = {"cuoc_vnd": "1000000", "ghep_vnd": "2900000", "ps_vnd": "360000", "chi_ho_vnd": "360000",
            "dc_vnd": "-200000" if sent else "0", "doi_vnd": "4060000" if sent else "4260000",
            "tra_vnd": "1000000" if sent else "0", "con_vnd": "3060000" if sent else "4260000"}
    return {"hom_nay": "2026-11-18", "thang": "2026-10-01", "dong": lines, "tong": tong,
            "ben": {"ma": "hth", "ten": "HTH", "kinh_gui": "HTH", "tieu_de": "DEBIT TÍN PHÁT"},
            "bang_ke": {"so": "HTH-2026-10", "gui_ngay": "2026-11-03", "trang_thai": "da_gui"} if sent else None}


class BangKeXlsxTest(unittest.TestCase):
    def test_sent_statement_layout_and_totals(self):
        name, body = bk.build(data())
        self.assertEqual(name, "BangKe_HTH_T10_2026.xlsx")
        rows = read_workbook(body)["T10-2026"]
        self.assertEqual(rows[0], ["DEBIT TÍN PHÁT THÁNG 10/2026"])
        self.assertEqual(rows[1], ["Kính gửi: HTH"])
        self.assertIn("HTH-2026-10", rows[2][0])
        self.assertEqual(rows[3], HEADER)
        first, second = rows[4], rows[5]
        self.assertEqual(first[0], 1)
        self.assertEqual(first[11:17], [1000000, None, 360000, "_ Kiểm hoá 150k\n_ Xí cont 210k", 1360000, None])
        self.assertEqual(first[17], -200000)
        self.assertIn("HTH báo trùng (nv, 05/11 09:00)", first[18])
        self.assertEqual(second[10], "CHUYỂN CẢNG")                     # chặng phụ ghi loại ở TÊN HÀNG như file hiện nay
        self.assertEqual(second[3], "Đóng ghép 2 kho")
        self.assertEqual(second[11:17], [None, 2900000, None, "_ Đóng ghép 2 kho 2900k", 2900000, "Chưa có giá"])
        total = rows[6]
        self.assertEqual([total[i] for i in (11, 12, 13, 15, 17)], [1000000, 2900000, 360000, 4260000, -200000])
        summary = {row[2]: row[15] for row in rows[8:11]}
        self.assertEqual(summary, {"ĐÒI HTH (sau điều chỉnh)": 4060000, "HTH ĐÃ TRẢ": 1000000, "CÒN PHẢI THU": 3060000})

    def test_draft_is_marked(self):
        name, body = bk.build(data(sent=False))
        self.assertEqual(name, "BangKe_HTH_T10_2026_nhap.xlsx")
        rows = read_workbook(body)["T10-2026"]
        self.assertIn("BẢN NHÁP", rows[0][0])
        self.assertEqual([rows[4][0], rows[5][0]], [1, 2])
        self.assertTrue(len(rows[4]) <= 17 or rows[4][17] is None)   # read_workbook bỏ ô trống cuối hàng

    def test_total_mismatch_refuses(self):
        broken = data()
        broken["tong"]["cuoc_vnd"] = "1000001"
        with self.assertRaises(bk.ExportError):
            bk.build(broken)
        broken = data()
        broken["tong"]["doi_vnd"] = "1"
        with self.assertRaises(bk.ExportError):
            bk.build(broken)


if __name__ == "__main__":
    unittest.main()
