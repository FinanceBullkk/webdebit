import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import v7_trip_source_match as match

NGUON_HEAD = ["Số cont", "Ngày đóng", "Booking", "Chủ hàng (chuẩn)", "Loại", "Giá + phí (gốc)"]
MONTH_HEAD = ["STT", "GIÁ + NEO +\n ĐIỆN + GHÉP", "BOOKING", "SỐ CONT", "CHỦ HÀNG", "Ngày đóng hàng"]


def sheet(tab, row, cont, day, month=None, amount=40_000_000, mode="CANG"):
    return {"tab": tab, "row": row, "cont": cont, "date": day, "raw_date": day or "", "month": month or day[:7],
            "amount": amount, "mode": mode}


def src(cont, day, owner="KHACH A", price="", family="BIEN"):
    return {"family": family, "tab": "THÁNG 3/2026", "line": 2, "cont": cont, "date": day, "owner": owner,
            "ref": "BK", "price": price}


def write(folder, name, payload):
    path = Path(folder) / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class TripSourceMatchTests(unittest.TestCase):
    def test_reads_booking_text(self):
        self.assertEqual(match.day_first("6/3/2025"), "2025-03-06")
        self.assertEqual(match.day_first("25/08", 2025), "2025-08-25")
        self.assertIsNone(match.day_first("25/08"))
        self.assertIsNone(match.day_first("30/12/1899"))
        self.assertEqual(match.container_key(" abcu 123456-7 "), "ABCU1234567")
        self.assertEqual(match.owner_key("NGUYỄN VĂN A 12"), match.owner_key("Nguyen Van A HTH12"))
        self.assertEqual(match.price_vnd("38TR+1"), 39_000_000)
        self.assertEqual(match.price_vnd("41.5tr"), 41_500_000)
        self.assertIsNone(match.price_vnd("HC +5TR"))
        self.assertIsNone(match.price_vnd(""))

    def test_sources_by_header_newest_first(self):
        newest = {"tabs": {"CONT_NGUON": [NGUON_HEAD, ["ABCU1234567", "06/03/2025", "BK1", "KHACH A", "BIỂN", "38TR"]]}}
        older = {"year": 2025, "tabs": {
            "THÁNG 3/2025": [MONTH_HEAD,
                             ["1", "40TR", "BK1", "ABCU1234567", "KHACH A", "7/3/2025"],  # repeats the newer tab
                             ["2", "40TR", "BK2", "WXYZ7654321", "KHACH B", "9/3/2025"],
                             ["3", "40TR", "BK3", "WXYZ7654321", "KHACH B", "10/3/2025"]],  # same tab: kept
            "SẦU TƯƠI ĐƯỜNG BỘ": [["STT", "KHÁCH", "SỐ CONT", "SỐ XE", "NGÀY LÊN KHO", "NGÀY XUẤT PHÁT"],
                                    ["1", "KHACH C", "QRSU1111111", "51C-1", "x", "25/08"]],
            "BANG TET": [["a"]]}}
        with tempfile.TemporaryDirectory() as folder:
            rows, stats = match.load_sources([write(folder, "new.json", newest), write(folder, "old.json", older)])
            self.assertEqual([(r["cont"], r["date"], r["family"]) for r in rows], [
                ("ABCU1234567", "2025-03-06", "BIEN"), ("WXYZ7654321", "2025-03-09", "BIEN"),
                ("WXYZ7654321", "2025-03-10", "BIEN"), ("QRSU1111111", "2025-08-25", "BO")])
            self.assertEqual((stats["dong_lap_tab_truoc"], stats["tab_bo_qua"]), (1, 1))
            self.assertEqual(rows[1]["price"], "40TR")
            with self.assertRaises(ValueError):
                match.load_sources([write(folder, "bad.json", {"tabs": {"CONT_BO": [["STT"], ["1"]]}})])

    def test_pairs_one_to_one_by_smallest_gap(self):
        rows = [sheet("A", 5, "ABCU1234567", "2026-03-05"), sheet("A", 6, "ABCU1234567", "2026-03-06"),
                sheet("A", 7, "ABCU1234567", "2026-05-20"),  # reused container, 10 days from the next trip
                sheet("A", 8, "WXYZ7654321", None, month="2026-04")]  # undated: same debt month
        source = [src("ABCU1234567", "2026-03-06"), src("ABCU1234567", "2026-05-30"), src("WXYZ7654321", "2026-04-10")]
        self.assertEqual(match.pair(rows, source)[0], {1: 0, 3: 2})

    def test_review_groups(self):
        rows = [sheet("A", 1, "DUPU1111111", "2026-03-10"), sheet("B", 1, "DUPU1111111", "2026-03-10"),
                sheet("A", 9, "NOSU1111111", "2026-03-12"), sheet("B", 9, "NOSU1111111", "2026-03-12"),
                sheet("A", 2, "GANU2222222", "2026-04-01"), sheet("A", 3, "GANU2222222", "2026-04-03"),
                sheet("X", 1, "DAOU3333333", "2025-03-06"), sheet("Y", 1, "DAOU3333333", "2025-06-03"),
                sheet("A", 4, "NONU4444444", "2026-03-15"), sheet("A", 5, "FARU5555555", "2026-03-20"),
                sheet("A", 6, "LECU6666666", "2026-03-21"), sheet("A", 7, "UNDU7777777", None, month="2026-03")]
        source = [src("DUPU1111111", "2026-03-10", price="38TR"), src("GANU2222222", "2026-04-01"),
                  src("DAOU3333333", "2025-03-06"), src("FARU5555555", "2026-03-30"),
                  src("LECU6666666", "2026-03-23", owner="KHACH B"), src("UNDU7777777", "2026-03-12"),
                  src("MISU8888888", "2026-03-25"), src("OLDU9999999", "2026-01-10"),
                  src("ZZZU1234567", "2026-03-11", owner="KHACH Z"), src("ENDU1234567", "2026-10-02")]
        s_pair, b_pair = match.pair(rows, source)
        found, counts = match.review(rows, source, s_pair, b_pair, "2026-10")
        groups = {(g, (s or b)["cont"]) for g, s, b, _ in found}
        for expected in [("TRUNG", "DUPU1111111"), ("GIA_KHAC", "DUPU1111111"), ("TRUNG_GAN", "GANU2222222"),
                         ("TRUNG_DAO_NGAY", "DAOU3333333"), ("KHONG_NGUON", "NONU4444444"),
                         ("LECH_NGAY", "FARU5555555"), ("LECH_NGAY", "LECU6666666"), ("KHAC_KHACH", "LECU6666666"),
                         ("NGAY_TU_NGUON", "UNDU7777777"), ("CHUA_TINH", "MISU8888888"),
                         ("TRUOC_KHI_CO_SO", "OLDU9999999"), ("CHU_HANG_CHUA_GHEP", "ZZZU1234567"),
                         ("THANG_CUOI", "ENDU1234567"), ("TRUNG", "NOSU1111111"), ("KHONG_NGUON", "NOSU1111111")]:
            self.assertIn(expected, groups)
        self.assertNotIn(("CHUA_TINH", "FARU5555555"), groups)  # already shown as a far date on the Sheet row
        self.assertEqual(counts, {"nhom_trung": 2, "nhom_trung_nguon_mot_chuyen": 1})

    def test_free_trip_nearby_beats_swapped_duplicate(self):
        # 05/04 could be a swapped 04/05 (paired with row 2), but the free trip of 31/03 is the better reading.
        rows = [sheet("A", 1, "SWPU1111111", "2026-04-05"), sheet("A", 2, "SWPU1111111", "2026-05-04")]
        source = [src("SWPU1111111", "2026-03-31"), src("SWPU1111111", "2026-05-04")]
        s_pair, b_pair = match.pair(rows, source)
        found, _ = match.review(rows, source, s_pair, b_pair, "2026-10")
        self.assertEqual([(g, (s or b)["date"]) for g, s, b, _ in found if s is rows[0]], [("LECH_NGAY", "2026-04-05")])

    def test_cli_prints_counts_only_and_keeps_files_out_of_repo(self):
        book = [(1, {"A": "THÁNG 3/2026"}),
                (2, {"A": "Marks & Nos", "B": "CONTAINER NO", "C": "DATE", "D": "UNIT PRICE", "E": "TOTAL(VND)",
                     "F": "NGAY TT(STK)", "G": "SỐ ĐÃ ỨNG TRƯỚC/ĐÃ THU TRONG THÁNG", "H": "SỐ CÒN PHẢI THU CUỐI THÁNG"}),
                (3, {"A": "1", "B": "ABCU1234567", "C": "06/03/2026", "D": "40000000", "E": "40000000"})]
        source = {"tabs": {"CONT_NGUON": [NGUON_HEAD, ["ABCU1234567", "06/03/2026", "BK1", "FAKE OWNER ZQ", "BIỂN", ""],
                                          ["WXYZ7654321", "09/03/2026", "BK2", "FAKE OWNER ZQ", "BIỂN", ""]]}}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(match.loader, "workbook_rows", return_value=[("FAKE BOOK", book)]), \
                patch.object(match.loader, "tong_commodities", return_value={}):
            args = ["--xlsx", "so-goc.xlsx", "--source", str(write(folder, "src.json", source)), "--end-month", "2026-10"]
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                self.assertEqual(match.main([*args, "--out", str(Path(folder) / "out")]), 0)
            self.assertNotIn("FAKE", buffer.getvalue())
            self.assertEqual(json.loads(buffer.getvalue())["coverage"]["2026 CANG"]["paired"], 1)
            with open(Path(folder) / "out" / "can_xem.csv", encoding="utf-8-sig") as stream:
                self.assertEqual([r["nhom"] for r in csv.DictReader(stream)], ["CHUA_TINH"])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(match.main([*args, "--out", str(match.REPO / "tmp-can-xem")]), 2)
                self.assertEqual(match.main(["--xlsx", "x", "--source", str(Path(folder) / "none.json"),
                                             "--out", str(Path(folder) / "out")]), 2)
            self.assertFalse((match.REPO / "tmp-can-xem").exists())


if __name__ == "__main__":
    unittest.main()
