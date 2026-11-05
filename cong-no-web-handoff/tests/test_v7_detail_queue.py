"""Bảng chi tiết từ tab "CHI TIET ..." (SO-CHI-TIET-01). Dữ liệu giả; không ghi gì vào sổ."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "tools"))
import v7_load_real_copy as loader  # noqa: E402
import v7_price_snapshot as snapshots  # noqa: E402
from v7_detail_queue import (  # noqa: E402
    _port,
    load_detail_snapshot,
    project_details,
    rows_from_tabs,
    short_day,
)

BILL_HEAD = {"B": "NO.", "C": "SỐ CONT\nCONTAINER NO.", "D": "SO TK", "E": "BILL", "F": "TÊN TÀU\nSHIPPING NAME", "G": "NGÀY ĐÓNG HÀNG\nDATE", "H": "ETD", "I": "ETA",
             "J": "NƠI ĐÓNG HÀNG\nFROM", "K": "CẢNG ĐẾN\nTO", "L": "PHÍ PHÁT SINH\nNEO XE", "M": "PHÍ DICH VỤ HẢI QUAN\nXUẤT HD VAT", "N": "CƯỚC VẬN CHUYỂN NỘI ĐỊA",
             "O": "CƯỚC VẬN TẢI QUỐC TẾ\nOF", "P": "VAT 8%", "Q": "TỔNG\nTOTAL(VND)", "R": "DA TT", "S": "CÒN LẠI"}
BILL_ROWS = [
    (2, {"B": " COMMERCIAL INVOICE "}), (11, BILL_HEAD),
    # Cước tàu trong Tổng, hai dòng (mình thu).
    (12, {"B": "1", "C": "FAKU0000001", "E": "BILL1", "F": "TAU 1", "G": "20/2/2026", "H": "25/2/2026", "I": "46090", "J": "KHO A", "K": "CANG X", "O": "12000000", "Q": "12000000"}),
    (13, {"M": "19000000", "N": "10000000", "P": "2320000", "Q": "31320000"}),
    # Cước tàu ngoài Tổng, số cont ở dòng dưới (khách tự trả), VAT lẻ.
    (14, {"B": "2", "J": "KHO B", "K": "CANG X", "O": "21000000"}),
    (15, {"C": "FAKU0000002", "E": "BILL2", "G": "46090", "L": "500000", "M": "6000000", "N": "13000000", "P": "1560000.6", "Q": "21060000.6"}),
    # Một dòng, số cont dùng lại ở dưới.
    (16, {"C": "FAKU0000003", "J": "KHO C", "M": "5000000", "N": "1000000", "P": "480000", "Q": "6480000"}),
    (17, {"C": "FAKU0000003", "J": "KHO C", "M": "5000000", "N": "2000000", "P": "560000", "Q": "7560000"}),
    (18, {"B": "TỔNG( TOTAL）VND", "Q": "77420000.6"}), (19, {"C": "FAKU0000009", "Q": "1"}),
]
TRUST_ROWS = [
    (11, {"B": "NO.", "C": "CONTAINER NO.", "D": "NHÀ XE", "E": "HT", "F": "SỐ TỜ KHAI", "G": "SỐ BILL", "H": "NGÀY", "I": "KHO", "J": "CẢNG ĐẾN", "K": "ĐƠN GIÁ",
          "L": "CƯỚC TÀU OF+LCC", "N": "CƯỚC XE VẬN CHUYỂN NỘI ĐIA", "P": "PHÍ DICH VỤ ỦY THÁC"}),
    (12, {"L": "KHÁCH ĐÃ TT", "M": "VAT", "N": "TT HÓA ĐƠN XE", "O": "VAT", "P": "TT PHÍ DV", "Q": "VAT"}),
    (13, {"B": "1", "C": "FAKU0000004", "E": "WH", "G": "BILL4", "H": "28/1/2026", "I": "KHO D", "J": "CANG X", "K": "43000000", "L": "19000000", "M": "500000",
          "N": "10000000", "O": "800000", "P": "12000000", "Q": "960000"}),
    (69, {"C": "STK: 1027350580 VCB"}),
]
TABS = [("KHACH A", [(1, {"B": "KHONG PHAI TAB CHI TIET"})]), ("CHI TIET KHACH A", BILL_ROWS), ("CHI TIET KHACH A - UTXK", TRUST_ROWS)]


def legacy(row_id, row, month, container, counted):
    return {"id": row_id, "kind": "trip", "month": month, "display": {"row": row},
            "current": {"month": month, "container": container, "event_date": month[:8] + "05", "counted_vnd": str(counted), "deleted": False,
                        "origin": "KHO SO", "destination": "CANG SO", "carrier": "HT"}}


class Rows(unittest.TestCase):
    def setUp(self):
        self.rows = rows_from_tabs(TABS)

    def test_doc_hai_mau_va_dung_o_dong_tong(self):
        self.assertEqual([row["container"] for row in self.rows], ["FAKU0000001", "FAKU0000002", "FAKU0000003", "FAKU0000003", "FAKU0000004"])

    def test_cuoc_tau_trong_hay_ngoai_tong(self):
        first, second = self.rows[0], self.rows[1]
        self.assertEqual((first["of_vnd"], first["of_counted"], first["total_vnd"]), ("12000000", True, "43320000"))
        self.assertEqual((second["of_vnd"], second["of_counted"], second["total_vnd"], second["vat_vnd"]), ("21000000", False, "21060001", "1560001"))
        self.assertEqual((second["from"], second["bill"]), ("KHO B", "BILL2"))

    def test_bang_uy_thac_cong_xe_phi_vat_khong_gom_cuoc_tau(self):
        row = self.rows[4]
        self.assertEqual((row["layout"], row["of_vnd"], row["of_counted"], row["total_vnd"], row["vat_vnd"], row["ship"]),
                         ("trust", "19500000", False, "23760000", "1760000", "WH"))

    def test_tab_chi_tiet_khong_sinh_dong_tien_cua_so(self):
        scan = loader.scan_tabs([(name, rows) for name, rows in TABS if name != "KHACH A"])
        for result in scan.values():
            self.assertEqual((result["records"], result["blocks"]), ([], {}))

    def test_mot_lan_doc_ghi_ca_ban_chup_chi_tiet(self):
        made = [snapshots.snapshot([], {"kind": "test"}), snapshots.snapshot([], {"kind": "test"}), snapshots.snapshot(self.rows, {"kind": "test"})]
        with tempfile.TemporaryDirectory() as folder, patch.object(snapshots, "build_with_details", return_value=made) as build:
            self.assertEqual(snapshots.main(["--xlsx", "gia.xlsx", "--output", str(Path(folder) / "prices.json")]), 0)
            build.assert_called_once()
            self.assertEqual(load_detail_snapshot(Path(folder) / "details.json")["row_count"], 5)

    def test_ban_chup_ghi_va_doc_lai(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "details.json"
            snapshots.write(snapshots.snapshot(self.rows, {"kind": "test"}), path)
            self.assertEqual(load_detail_snapshot(path)["row_count"], 5)
            path.write_text(json.dumps({"rows": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_detail_snapshot(path)


class Project(unittest.TestCase):
    def setUp(self):
        self.snapshot = {"rows": rows_from_tabs(TABS)}

    def ledger(self, rows, trips=(), charges="0"):
        return {"legacy_rows": rows, "trips": list(trips), "months": [{"month": "2026-03-01", "charges_vnd": charges}]}

    def test_so_it_container_trung_khong_co_bang(self):
        ledger = self.ledger([legacy(1, 5, "2026-03-01", "FAKU0000001", 1), legacy(2, 6, "2026-03-01", "OTHU0000001", 1), legacy(3, 7, "2026-03-01", "OTHU0000002", 1)])
        self.assertEqual(project_details(self.snapshot, ledger), {"rows": [], "months": {}})

    def test_ghep_dong_khong_container_tren_duoi_va_bao_lech(self):
        rows = [legacy(1, 12, "2026-03-01", "FAKU0000001", 12000000), legacy(2, 13, "2026-03-01", "", 31320000),   # dòng trên có cont
                legacy(3, 14, "2026-03-01", "", 20000000), legacy(4, 15, "2026-03-01", "FAKU0000002", 0)]           # dòng dưới có cont, lệch sổ
        out = project_details(self.snapshot, self.ledger(rows, charges="63320000"))
        self.assertEqual([row["container"] for row in out["rows"]], ["FAKU0000001", "FAKU0000002"])
        self.assertEqual([(row["ledger_vnd"], row["differs"]) for row in out["rows"]], [("43320000", False), ("20000000", True)])
        summary = out["months"]["2026-03"]
        self.assertEqual((summary["total_vnd"], summary["of_counted_vnd"], summary["of_customer_vnd"], summary["differs"], summary["diff_vnd"]),
                         ("64380001", "12000000", "21000000", ["FAKU0000002"], "-1060001"))

    def test_dong_khong_container_khong_ke_ben_giu_rieng(self):
        rows = [legacy(1, 12, "2026-03-01", "FAKU0000001", 43320000), legacy(2, 30, "2026-03-01", "", 5000000)]
        out = project_details(self.snapshot, self.ledger(rows, charges="48320000"))
        self.assertEqual([(row["container"], row["total_vnd"], row["has_detail"]) for row in out["rows"]],
                         [("FAKU0000001", "43320000", True), ("", "5000000", False)])
        self.assertEqual(out["months"]["2026-03"]["diff_vnd"], "0")

    def test_container_dung_lai_lan_cuoi_ung_voi_lan_cuoi(self):
        rows = [legacy(1, 40, "2026-03-01", "FAKU0000003", 6480000), legacy(2, 41, "2026-03-01", "FAKU0000003", 7560000)]
        rows[1]["current"]["event_date"] = "2026-03-20"
        out = project_details(self.snapshot, self.ledger(rows))
        self.assertEqual([row["total_vnd"] for row in out["rows"]], ["6480000", "7560000"])
        one = project_details(self.snapshot, self.ledger(rows[1:]))
        self.assertEqual(one["rows"][0]["total_vnd"], "7560000")

    def test_chuyen_web_chua_co_tren_bang_ke(self):
        trips = [{"id": 9, "month": "2026-03-01", "container": "NEWU0000001", "event_date": "2026-03-09", "amount_vnd": None, "status": "confirmed", "origin": "KHO", "destination": "CANG", "carrier": "EMC"},
                 {"id": 10, "month": "2026-03-01", "container": "NEWU0000002", "event_date": "2026-03-09", "amount_vnd": "5000000", "status": "confirmed"},
                 {"id": 11, "month": "2026-03-01", "container": "NEWU0000003", "status": "rejected"}]
        rows = [legacy(1, 12, "2026-03-01", "FAKU0000001", 43320000), legacy(2, 13, "2026-03-01", "FAKU0000002", 21060001), legacy(3, 14, "2026-03-01", "FAKU0000004", 23760000)]
        out = project_details(self.snapshot, self.ledger(rows, trips))
        self.assertEqual([(row["container"], row["total_vnd"]) for row in out["rows"]][3:], [("NEWU0000001", None), ("NEWU0000002", "5000000")])
        self.assertEqual(out["months"]["2026-03"]["no_detail"], 2)

    def test_cang_den_bo_chu_han(self):
        self.assertEqual(_port("SHEKOU- 蛇口"), "SHEKOU")
        self.assertEqual(_port("NANSHA-南沙"), "NANSHA")
        self.assertEqual(_port("PORT KLANG"), "PORT KLANG")
        self.assertEqual(_port(None), "")

    def test_ngay_bi_dao_doc_theo_thang_cua_so(self):
        self.assertEqual(short_day("46090", "2026-09"), "03/09")      # 46090 là 9/3/2026, sổ tháng 9
        self.assertEqual(short_day("46090", "2026-03"), "09/03")      # đúng tháng thì giữ
        self.assertEqual(short_day("20/2/2026", "2026-02"), "20/02")
        self.assertEqual(short_day("3/10//2026", "2026-10"), "3/10//2026")
        self.assertEqual(short_day("", "2026-10"), "")


if __name__ == "__main__":
    unittest.main()
