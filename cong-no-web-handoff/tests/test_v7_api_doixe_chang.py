"""DOI-XE-CHANG-01: API mục Chặng — đường đọc `GET /api/v7/doixe/chang` (việc từ bản chụp booking + chặng từ get_dieu_do, trạng thái do API
tính) và bốn đường ghi phân công. Dữ liệu giả, mã nhà xe giả; runner giả mô phỏng hàm `doixe.get_dieu_do` ở mức hình dạng JSON."""

import json
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_api_doixe as doixe  # noqa: E402
import v7_api_tables as tables  # noqa: E402
import v7_identity as identity  # noqa: E402
import v7_ledger_api as api  # noqa: E402

NOW = datetime(2026, 11, 19, 3, 0, tzinfo=UTC)   # 10:00 giờ VN, cùng giờ với bản chụp giả
USED, TRAP_LONGER, TRAP_SHORTER, OLD = "NX-AAA", "NX-AAA2", "NX-AA", "NX-OLD"


def src(cont, day, nha_xe=USED, line=None, **extra):
    row = {"source_row": line or 2, "container": cont, "event_date": day, "nha_xe": nha_xe, "origin": "Kho K1", "destination": "Cảng C1",
           "carrier": "Hãng H1", "booking": "BK1", "customer_name": "Khách giả", "commodity": "SẦU RIÊNG", "seal": "SL1",
           "nhiet_do": "-18", "ten_tau": "Tàu T1"}
    row.update(extra)
    return row


def snapshot(rows, columns=("nha_xe", "seal", "nhiet_do", "ten_tau"), created="2026-11-19T09:50:00+07:00"):
    return {"rows": rows, "row_count": len(rows), "columns": list(columns), "runner": {"created_at": created}}


def chang(id_, *, cont="MAUU1000001", ngay="2026-11-19", ngay_dong="2026-11-19", loai="hang", gui=False, hoan=False, phi=False, kho="Kho K1"):
    return {"id": id_, "loai": loai, "ngay": ngay, "ngay_dong": ngay_dong, "nguon": "dieu_do", "container": cont, "xe_id": 1, "tai_xe_id": 2,
            "tra": "nguoi", "nguoi_tra_id": 2, "noi_lay": None, "noi_ha": None, "kho": kho, "tinh": None, "ten_hang": None, "ghi_chu": None,
            "sau_khoa": False, "actor": "nv@gia", "luc": "2026-11-19T08:00:00+07:00", "co_phi": phi, "da_hoan": hoan, "da_gui": gui}


def money_fin(**over):
    """Phần tài chính mặc định của một chặng giả: một khoản chi nâng 450.000 người trả, cước 1.000.000, lãi gộp 550.000."""
    base = {"thang_khoa": False, "bang_ke_thang": "2026-11-01",
            "chi": {"dong": [{"khoan": "nang", "ten": "Nâng", "so_tien_vnd": "450000", "nguoi_tra": "nguoi", "nguoi_tra_id": 2,
                              "chi_ho": False, "da_hoan": False}],
                    "tong_vnd": "450000", "chi_ho_vnd": "0", "ngoai_chi_ho_vnd": "450000"},
            "thu": {"cuoc": {"vnd": "1000000", "gia_bang_vnd": "1000000", "tay": False, "tuyen_id": 3, "tuyen": "Tuyến giả"},
                    "ghep_vnd": "0", "ps_vnd": "0", "chi_ho_vnd": "0", "dc_vnd": None, "doi_vnd": "1000000",
                    "dong": [{"khoan": "xi_cont", "ten": "Xí cont", "so_luong": None, "muc_vnd": None, "so_tien_vnd": "0", "chi_ho": True,
                              "cot": "ps", "la": False}],
                    "loi": [{"goc": "x", "loi": "y"}], "chua_doc": 0},
            "lai_gop": {"thu_vnd": "1000000", "chi_vnd": "450000", "lai_vnd": "550000", "thieu": []}}
    return {**base, **over}


class FakeDb:
    """Biết get_dieu_do (danh mục mã nhà xe, chặng đã nối theo (container, ngày đóng), chặng mồ côi) và get_chang_tai_chinh
    (phần tài chính mặc định cho mọi chặng đã biết, ghi đè theo id; `outside`: chặng ngoài booking trong khoảng)."""

    def __init__(self, joined=None, orphans=None, codes=((USED, True), (OLD, False)), fin=None, outside=()):
        self.joined, self.orphans, self.calls, self.fin, self.outside = joined or {}, orphans or [], [], fin or {}, list(outside)
        self.codes = [{"ma": m, "dang_dung": on} for m, on in codes]

    def known(self):
        return [c for rows in self.joined.values() for c in rows] + self.orphans + self.outside

    def asked(self):
        """Mảng việc của lượt get_dieu_do cuối có việc."""
        return [call[1] for call in self.calls if call[0] == "doixe_get_dieu_do" and call[1]][-1]

    def named(self, function):
        return [call for call in self.calls if call[0] == function]

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if function == "doixe_get_chang_tai_chinh":
            ids, out = set(payload["ids"]), []
            for c in self.known():
                if c["id"] in ids or (payload["tu"] and payload["tu"] <= c["ngay"] <= payload["den"]):
                    out.append({**c, **self.fin.get(c["id"], money_fin())})
            return {"hom_nay": "2026-11-19", "chang": sorted(out, key=lambda c: (c["ngay"], c["id"]))}
        if function != "doixe_get_dieu_do":
            return {"function": function}
        viec = []
        for item in payload:
            rows = self.joined.get((item["container"], item["ngay_dong"]), [])
            hang = next((c["id"] for c in rows if c["loai"] == "hang"), None)
            viec.append({"container": item["container"], "ngay_dong": item["ngay_dong"], "hang_id": hang, "chang": rows})
        return {"hom_nay": "2026-11-19", "viec": viec, "mo_coi": self.orphans if payload else [],
                "xe": [{"id": 1, "bien_so": "99X-00001", "nhom": "A", "thue_ngoai": False, "tai_xe_id": 2}],
                "tai_xe": [{"id": 2, "ten": "Tài xế giả"}], "nha_xe": self.codes}


class ReadChangTest(unittest.TestCase):
    def read(self, rows, query="thang=2026-11-01", db=None, **snap):
        db = db or FakeDb()
        with mock.patch.object(doixe, "load_booking", return_value=snapshot(rows, **snap)):
            return db, doixe.read_chang(query, db, "nv@gia", now=NOW)

    def test_only_exact_codes_become_jobs(self):
        rows = [src("MAUU1000001", "2026-11-19", USED, 2), src("MAUU1000002", "2026-11-19", TRAP_LONGER, 3),
                src("MAUU1000003", "2026-11-19", TRAP_SHORTER, 4), src("MAUU1000004", "2026-11-19", f"  {USED} ", 5),
                src("MAUU1000005", "2026-11-19", OLD, 6), src("MAUU1000006", "2026-11-19", "", 7),
                src("MAUU1000007", "2026-11-19", USED.lower(), 8), src("MAUU1000008", "2026-11-19", f"{USED} {USED}", 9)]
        db, out = self.read(rows)
        self.assertEqual([v["container"] for v in out["viec"]], ["MAUU1000001", "MAUU1000004"])
        sent = db.asked()
        self.assertEqual([i["container"] for i in sent], ["MAUU1000001", "MAUU1000004"])
        self.assertEqual(out["nguon"]["bo_qua"]["khong_nha_xe"], 6)

    def test_job_without_container_is_upcoming_and_not_sent_to_db(self):
        rows = [src("", "2026-11-20", line=5), src("chờ cont", "2026-11-20", line=6), src("MAUU1000001", "2026-11-20", line=7)]
        db, out = self.read(rows)
        by_id = {v["id"]: v for v in out["viec"]}
        self.assertEqual(set(by_id), {"#5|2026-11-20", "#6|2026-11-20", "MAUU1000001|2026-11-20"})
        self.assertEqual((by_id["#5|2026-11-20"]["trang_thai"], by_id["#5|2026-11-20"]["container"], by_id["#5|2026-11-20"]["chang"]),
                         ("sap_toi", None, []))
        self.assertEqual(by_id["#6|2026-11-20"]["trang_thai"], "sap_toi")   # chữ không phải số container
        self.assertEqual(by_id["MAUU1000001|2026-11-20"]["trang_thai"], "cho_phan_xe")
        self.assertEqual(db.asked(), [{"container": "MAUU1000001", "ngay_dong": "2026-11-20"}])
        self.assertEqual(out["dem"]["sap_toi"], 2)
        self.assertEqual(out["viec"][0]["booking"]["kho"], "Kho K1")

    def test_only_unnumbered_jobs_skip_the_second_db_call(self):
        db, out = self.read([src("", "2026-11-20")])
        self.assertEqual([call[0] for call in db.calls], ["doixe_get_dieu_do", "doixe_get_chang_tai_chinh"])   # không có lượt nối chặng
        self.assertEqual(out["viec"][0]["trang_thai"], "sap_toi")

    def test_states_flags_and_counts(self):
        rows = [src(f"MAUU10000{n:02d}", "2026-11-19", line=n) for n in range(1, 6)]
        joined = {
            ("MAUU1000002", "2026-11-19"): [chang(12, cont="MAUU1000002")],
            ("MAUU1000003", "2026-11-19"): [chang(13, cont="MAUU1000003", phi=True), chang(14, cont="MAUU1000003", loai="chuyen_cang")],
            ("MAUU1000004", "2026-11-19"): [chang(15, cont="MAUU1000004", phi=True, hoan=True)],
            ("MAUU1000005", "2026-11-19"): [chang(16, cont="MAUU1000005", phi=True, gui=True)],
        }
        _, out = self.read(rows, db=FakeDb(joined))
        self.assertEqual([v["trang_thai"] for v in out["viec"]],
                         ["cho_phan_xe", "da_phan_xe", "da_co_phi", "da_co_phi", "da_len_bang_ke"])
        by = {v["container"]: v for v in out["viec"]}
        self.assertEqual(by["MAUU1000002"]["hang_id"], 12)
        self.assertEqual([(c["id"], c["khoa"], c["cho_phep"]["doi_phan_cong"]) for c in by["MAUU1000003"]["chang"]],
                         [(13, "CHANG_CO_PHI", False), (14, None, True)])
        self.assertEqual(by["MAUU1000004"]["chang"][0]["khoa"], "CHANG_DA_HOAN")
        self.assertEqual(by["MAUU1000005"]["chang"][0]["khoa"], "CHANG_DA_GUI")
        self.assertEqual(out["dem"], {"viec": 5, "sap_toi": 0, "cho_phan_xe": 1, "da_phan_xe": 1, "da_co_phi": 2, "da_len_bang_ke": 1,
                                      "booking_doi": 0, "chua_co_phi": 2, "chua_co_gia": 0, "khong_con_tren_booking": 0, "ngoai_booking": 0})
        self.assertEqual((out["xe"][0]["bien_so"], out["tai_xe"][0]["ten"], out["hom_nay"]), ("99X-00001", "Tài xế giả", "2026-11-19"))

    def test_booking_changed_shows_before_and_after_and_does_not_touch_the_chang(self):
        rows = [src("MAUU1000001", "2026-11-19", origin="Kho K2")]
        joined = {("MAUU1000001", "2026-11-19"): [chang(12, ngay_dong="2026-11-18", kho="Kho K1")]}
        _, out = self.read(rows, db=FakeDb(joined))
        self.assertEqual(out["viec"][0]["booking_doi"],
                         [{"chang_id": 12, "truong": "ngay_dong", "truoc": "2026-11-18", "sau": "2026-11-19"},
                          {"chang_id": 12, "truong": "kho", "truoc": "Kho K1", "sau": "Kho K2"}])
        self.assertEqual(out["dem"]["booking_doi"], 1)
        self.assertEqual(out["viec"][0]["chang"][0]["ngay_dong"], "2026-11-18")   # chỉ báo, không sửa
        # Cùng chữ kho khác hoa thường và khoảng trắng: không phải thay đổi. Chặng chưa có ngày đóng không so được.
        rows = [src("MAUU1000001", "2026-11-19", origin=" kho  k1 ")]
        joined = {("MAUU1000001", "2026-11-19"): [chang(12), chang(13, ngay_dong=None, kho="Kho Z")]}
        _, out = self.read(rows, db=FakeDb(joined))
        self.assertIsNone(out["viec"][0]["booking_doi"])

    def test_orphan_chang_is_listed_with_choices(self):
        orphans = [chang(21, cont="MAUU1000009", ngay_dong="2026-11-10"), chang(22, cont="MAUU1000008", ngay_dong="2026-11-10", phi=True),
                   chang(23, cont="MAUU1000007", ngay_dong="2026-09-01")]
        _, out = self.read([src("MAUU1000001", "2026-11-19")], db=FakeDb(orphans=orphans))
        self.assertEqual([c["id"] for c in out["khong_con_tren_booking"]], [21, 22])   # 23 ngoài khoảng đang xem
        self.assertEqual({c["trang_thai"] for c in out["khong_con_tren_booking"]}, {"khong_con_tren_booking"})
        free, locked = out["khong_con_tren_booking"]
        self.assertEqual(free["cho_phep"], {"doi_phan_cong": True, "bo_phan_cong": True, "chuyen_container": True, "giu_ngoai": True})
        self.assertEqual(locked["cho_phep"], {"doi_phan_cong": False, "bo_phan_cong": False, "chuyen_container": False, "giu_ngoai": True})
        self.assertEqual(out["dem"]["khong_con_tren_booking"], 2)

    def test_old_waiting_jobs_only_with_cu_and_only_while_waiting(self):
        rows = [src("MAUU1000001", "2026-11-05", line=2), src("MAUU1000002", "2026-11-06", line=3), src("MAUU1000003", "2026-10-01", line=4),
                src("MAUU1000004", "2026-11-19", line=5)]
        joined = {("MAUU1000002", "2026-11-06"): [chang(12, cont="MAUU1000002")]}
        _, out = self.read(rows, query="tu=2026-11-18&den=2026-11-20", db=FakeDb(joined))
        self.assertEqual([v["container"] for v in out["viec"]], ["MAUU1000004"])
        _, out = self.read(rows, query="tu=2026-11-18&den=2026-11-20&cu=30", db=FakeDb(joined))
        self.assertEqual([(v["container"], v["cu"]) for v in out["viec"]], [("MAUU1000001", True), ("MAUU1000004", False)])
        self.assertEqual(out["cu"], 30)

    def test_neighbour_job_outside_range_is_sent_but_not_shown(self):
        # Cùng container có hai việc cách nhau 2 ngày: hàm nối cần thấy cả hai để chọn đúng việc cho từng chặng.
        rows = [src("MAUU1000001", "2026-12-01", line=2), src("MAUU1000001", "2026-11-30", line=3)]
        db, out = self.read(rows, query="thang=2026-11-01")
        self.assertEqual([(v["ngay_dong"], v["ngay_dong_khac"]) for v in out["viec"]], [("2026-11-30", ["2026-12-01"])])
        self.assertEqual({i["ngay_dong"] for i in db.asked()}, {"2026-11-30", "2026-12-01"})

    def test_duplicate_booking_rows_are_one_job(self):
        _db, out = self.read([src("MAUU1000001", "2026-11-19", line=2), src("MAUU1000001", "2026-11-19", line=3)])
        self.assertEqual(len(out["viec"]), 1)
        self.assertEqual(out["nguon"]["bo_qua"]["trung"], 1)

    def test_rows_without_date_are_skipped_and_counted(self):
        _, out = self.read([src("MAUU1000001", None, line=2), src("MAUU1000002", "1899-12-30", line=3), src("MAUU1000003", "", line=4)])
        self.assertEqual(out["viec"], [])
        self.assertEqual(out["nguon"]["bo_qua"]["khong_ngay"], 3)

    def test_no_active_code_or_old_snapshot(self):
        db, out = self.read([src("MAUU1000001", "2026-11-19")], db=FakeDb(codes=((OLD, False),)))
        self.assertEqual((out["viec"], len(db.calls)), ([], 2))   # danh mục mã, rồi chặng ngoài booking trong khoảng
        self.assertEqual(out["xe"][0]["id"], 1)   # danh mục xe, tài xế vẫn trả
        with self.assertRaises(api.ApiError) as caught:
            self.read([src("MAUU1000001", "2026-11-19")], columns=())
        self.assertEqual((caught.exception.status, caught.exception.code), (503, "NGUON_THIEU_NHA_XE"))
        db = FakeDb()
        with mock.patch.object(doixe, "load_booking", return_value={"rows": [], "row_count": 0}),                 self.assertRaises(api.ApiError) as caught:   # bản chụp trước khi có cột
            doixe.read_chang("", db, "nv@gia", now=NOW)
        self.assertEqual(caught.exception.code, "NGUON_THIEU_NHA_XE")
        self.assertEqual(db.calls, [])   # chưa tốn lượt DB nào

    def test_snapshot_unavailable_and_stale(self):
        with mock.patch.object(doixe.v7_api_sheet, "load_snapshot", side_effect=ValueError("x")), \
                mock.patch.object(doixe.v7_api_sheet, "cached_load", side_effect=lambda loader, path: loader(path)), \
                self.assertRaises(api.ApiError) as caught:
            doixe.load_booking()
        self.assertEqual((caught.exception.status, caught.exception.code), (503, "SHEET_SNAPSHOT_UNAVAILABLE"))
        _, out = self.read([], created="2026-11-19T07:00:00+07:00")
        self.assertTrue(out["nguon"]["qua_han"])
        _, out = self.read([], created="2026-11-19T09:50:00+07:00")
        self.assertFalse(out["nguon"]["qua_han"])
        _, out = self.read([], created="khong-phai-ngay")
        self.assertTrue(out["nguon"]["qua_han"])

    def test_finance_is_merged_in_short_form_and_ids_are_sent(self):
        rows = [src("MAUU1000001", "2026-11-19", line=2), src("MAUU1000002", "2026-11-19", line=3)]
        joined = {("MAUU1000001", "2026-11-19"): [chang(12), chang(14, loai="chuyen_cang", ngay="2026-12-02")]}
        fin = {14: money_fin(thu={**money_fin()["thu"], "cuoc": {"vnd": None, "gia_bang_vnd": None, "tay": False, "tuyen_id": None, "tuyen": None}},
                             lai_gop={"thu_vnd": None, "chi_vnd": "450000", "lai_vnd": None, "thieu": ["gia"]})}
        db, out = self.read(rows, db=FakeDb(joined, fin=fin))
        ask = db.named("doixe_get_chang_tai_chinh")[0][1]
        self.assertEqual((ask["tu"], ask["den"], sorted(ask["ids"])), ("2026-11-01", "2026-11-30", [12, 14]))   # chặng lệch ngày vẫn có số
        first, late = out["viec"][0]["chang"]
        self.assertEqual((first["chi"], first["lai_gop"]["lai_vnd"], first["thu"]["doi_vnd"], first["bang_ke_thang"], first["thang_khoa"]),
                         ({"tong_vnd": "450000", "chi_ho_vnd": "0", "ngoai_chi_ho_vnd": "450000"}, "550000", "1000000", "2026-11-01", False))
        self.assertNotIn("dong", first["thu"])   # từng khoản và từng dòng chỉ có ở phiếu chặng
        self.assertNotIn("loi", first["thu"])
        self.assertEqual((late["lai_gop"]["lai_vnd"], late["lai_gop"]["thieu"], late["thu"]["cuoc"]["vnd"]), (None, ["gia"], None))   # NULL, không phải 0
        self.assertEqual(out["dem"]["chua_co_gia"], 1)
        self.assertEqual(out["viec"][1]["chang"], [])

    def test_chang_without_finance_row_stays_without_finance_keys(self):
        class Gone(FakeDb):
            def run(self, function, payload, actor):
                got = super().run(function, payload, actor)
                if function == "doixe_get_chang_tai_chinh":
                    got["chang"] = []   # chặng vừa bị bỏ giữa hai lượt
                return got
        _, out = self.read([src("MAUU1000001", "2026-11-19")], db=Gone({("MAUU1000001", "2026-11-19"): [chang(12)]}))
        self.assertNotIn("lai_gop", out["viec"][0]["chang"][0])

    def test_chang_outside_booking_are_listed_from_the_finance_call(self):
        extra = [chang(31, cont="MAUU1000050", ngay="2026-11-10", ngay_dong=None, loai="chuyen_cang") | {"nguon": "nhap"},
                 chang(32, cont="MAUU1000051", ngay="2026-11-11", ngay_dong="2026-11-11")]   # có ngày đóng mà không thuộc việc nào đang hiện
        joined = {("MAUU1000001", "2026-11-19"): [chang(12)]}
        _, out = self.read([src("MAUU1000001", "2026-11-19")], db=FakeDb(joined, outside=extra))
        self.assertEqual([c["id"] for c in out["ngoai_booking"]], [31])
        self.assertEqual((out["ngoai_booking"][0]["trang_thai"], out["ngoai_booking"][0]["khoa"], out["dem"]["ngoai_booking"]),
                         ("ngoai_booking", None, 1))
        self.assertEqual(out["ngoai_booking"][0]["lai_gop"]["lai_vnd"], "550000")
        self.assertNotIn("dong", out["ngoai_booking"][0]["chi"])
        self.assertNotIn(31, [c["id"] for v in out["viec"] for c in v["chang"]])

    def test_orphans_carry_finance_too(self):
        _, out = self.read([src("MAUU1000001", "2026-11-19")], db=FakeDb(orphans=[chang(21, cont="MAUU1000009", ngay_dong="2026-11-10")]))
        self.assertEqual(out["khong_con_tren_booking"][0]["lai_gop"]["lai_vnd"], "550000")

    def test_phieu_returns_full_detail_and_rejects_unknown_chang(self):
        db = FakeDb({("MAUU1000001", "2026-11-19"): [chang(12, phi=True)]})
        out = doixe.read_phieu("id=12", db, "nv@gia")
        self.assertEqual(db.calls, [("doixe_get_chang_tai_chinh", {"tu": None, "den": None, "ids": [12]}, "nv@gia")])
        got = out["chang"]
        self.assertEqual((got["id"], got["khoa"], got["chi"]["dong"][0]["nguoi_tra"], got["thu"]["dong"][0]["khoan"], got["thu"]["loi"][0]["loi"]),
                         (12, "CHANG_CO_PHI", "nguoi", "xi_cont", "y"))
        with self.assertRaises(api.ApiError) as caught:
            doixe.read_phieu("id=99", db, "nv@gia")
        self.assertEqual((caught.exception.status, caught.exception.code), (409, "CHANG_NOT_FOUND"))
        for query in ("", "id=0", "id=x", "id=1&id=2", "id=1&x=2", "id=99999999999999999999"):
            with self.subTest(query=query), self.assertRaises(api.ApiError):
                doixe.read_phieu(query, db, "nv@gia")
        self.assertIsNone(doixe.read_route("/api/v7/doixe/so", "", db, "nv@gia"))

    def test_query_rules(self):
        window = doixe.parse_chang_query("", NOW)
        self.assertEqual((window["tu"], window["den"], window["cu"]), ("2026-11-01", "2026-11-30", 0))
        self.assertEqual(doixe.parse_chang_query("thang=2026-02-01")["den"], "2026-02-28")
        self.assertEqual(doixe.parse_chang_query("tu=2026-11-18&den=2026-11-18&cu=92")["lui"], "2026-08-18")
        for query in ("thang=2026-11-02", "thang=2026-11-01&tu=2026-11-01&den=2026-11-02", "tu=2026-11-01", "den=2026-11-01",
                      "tu=2026-11-02&den=2026-11-01", "tu=2026-01-01&den=2026-04-04", "tu=2026-13-01&den=2026-13-02", "cu=93", "cu=-1",
                      "cu=01", "cu=", "x=1", "thang=2026-11-01&thang=2026-10-01"):
            with self.subTest(query=query), self.assertRaises(api.ApiError):
                doixe.parse_chang_query(query, NOW)
        self.assertEqual(doixe.parse_chang_query("tu=2026-01-01&den=2026-04-03")["den"], "2026-04-03")   # đúng 93 ngày

    def test_too_many_jobs_rejected_before_the_second_db_call(self):
        rows = [src(f"MAUU{n:07d}", "2026-11-19", line=n) for n in range(doixe.MAX_VIEC + 1)]
        db = FakeDb()
        with self.assertRaises(api.ApiError) as caught:
            self.read(rows, db=db)
        self.assertEqual(caught.exception.code, "QUA_NHIEU_VIEC")
        self.assertEqual([call[0] for call in db.calls], ["doixe_get_dieu_do"])


class ChangRouteTest(unittest.TestCase):
    def setUp(self):
        self.headers = {"Host": "127.0.0.1:8780", "Origin": "http://127.0.0.1:8780", "Content-Type": "application/json"}

    def call(self, method, path, body=None, *, actor="nv@gia", runner=None, **extra):
        runner = runner or FakeDb()
        raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
        status, value = api.handle(method, path, self.headers, raw, runner, port=8780, host="127.0.0.1", actor=actor, **extra)
        self.assertEqual(status, 200)
        return runner, value

    def rejects(self, method, path, body, code):
        with self.assertRaises(api.ApiError) as caught:
            self.call(method, path, body)
        self.assertEqual(caught.exception.code, code, body)

    def test_get_route_adds_actor_names_and_hits_the_booking_loader(self):
        rows = [src("MAUU1000001", "2026-11-19")]
        joined = {("MAUU1000001", "2026-11-19"): [chang(12)]}
        with mock.patch.object(doixe, "load_booking", return_value=snapshot(rows)):
            db, value = self.call("GET", "/api/v7/doixe/chang?thang=2026-11-01", runner=FakeDb(joined))
        self.assertEqual(value["viec"][0]["chang"][0]["actor_name"], "nv")
        self.assertEqual({call[2] for call in db.calls}, {"nv@gia"})   # người làm lấy từ phiên
        with mock.patch.object(doixe, "load_booking", return_value=snapshot(rows)), self.assertRaises(api.ApiError) as caught:
            self.call("GET", "/api/v7/doixe/chang?thang=2026-11-02")
        self.assertEqual(caught.exception.code, "INVALID_MONTH")

    def test_phieu_route_and_missing_permission(self):
        db, value = self.call("GET", "/api/v7/doixe/chang/phieu?id=12", runner=FakeDb({("MAUU1000001", "2026-11-19"): [chang(12)]}))
        self.assertEqual(value["chang"]["actor_name"], "nv")
        self.assertEqual(db.calls[0][2], "nv@gia")
        runner = FakeDb()
        headers = {**self.headers, "Tailscale-User-Login": "stranger@example.test"}
        with self.assertRaises(identity.IdentityError) as caught:
            api.handle("GET", "/api/v7/doixe/chang/phieu?id=12", headers, b"", runner, port=8780, host="127.0.0.1", source_ip="127.0.0.1",
                       behind_tailscale_serve=True, allowed_logins=frozenset({"nv@gia"}))
        self.assertEqual((caught.exception.code, runner.calls), ("LOGIN_NOT_ALLOWED", []))

    def test_four_writes_pass_body_as_is_with_session_actor(self):
        cases = [
            ("/api/v7/doixe/chang/phan-xe", "doixe_phan_xe", {"container": "MAUU1000001", "ngay_dong": "2026-11-19", "xe_id": 1}),
            ("/api/v7/doixe/chang/phan-xe", "doixe_phan_xe", {"container": "MAUU1000001", "ngay_dong": "2026-11-19", "xe_id": 1, "tai_xe_id": 2,
                                                              "ngay": "2026-11-19", "loai": "chuyen_cang", "noi_lay": "A", "noi_ha": "B",
                                                              "kho": "Kho K1", "tinh": None, "ten_hang": "Sầu riêng", "ghi_chu": None,
                                                              "ngay_dong_khac": ["2026-11-21"]}),
            ("/api/v7/doixe/chang/doi-phan-cong", "doixe_doi_phan_cong",
             {"chang_id": 5, "truoc": {"xe_id": 1, "tai_xe_id": None, "ngay": "2026-11-19"}, "xe_id": 2, "tai_xe_id": 3, "ngay": "2026-11-18"}),
            ("/api/v7/doixe/chang/bo-phan-cong", "doixe_bo_phan_cong", {"chang_id": 5}),
            ("/api/v7/doixe/chang/nhan-booking", "doixe_nhan_booking", {"chang_id": 5, "kieu": "giu_ngoai"}),
            ("/api/v7/doixe/chang/nhan-booking", "doixe_nhan_booking",
             {"chang_id": 5, "kieu": "cap_nhat", "ngay_dong": "2026-11-20", "container": "MAUU1000002", "kho": None, "noi_lay": "A",
              "noi_ha": "B", "ten_hang": "X", "tinh": "Y"}),
            ("/api/v7/doixe/chang/nhan-booking", "doixe_nhan_booking", {"chang_id": 5, "kieu": "cap_nhat", "ngay_dong": "2026-11-20"}),
        ]
        for path, function, body in cases:
            with self.subTest(path=path, body=body):
                db, value = self.call("POST", path, {"idempotency_key": "k1", **body})
                self.assertEqual(db.calls[-1], (function, {"idempotency_key": "k1", **body}, "nv@gia"))
                self.assertEqual(value, {"function": function})

    def test_same_request_id_is_forwarded_unchanged_so_the_db_can_deduplicate(self):
        body = {"idempotency_key": "abc", "container": "MAUU1000001", "ngay_dong": "2026-11-19", "xe_id": 1}

        class Replaying(FakeDb):
            def __init__(self):
                super().__init__()
                self.done = {}

            def run(self, function, payload, actor):
                self.calls.append((function, payload, actor))
                return self.done.setdefault(payload["idempotency_key"], {"ok": True, "chang_id": len(self.done) + 1})

        db = Replaying()
        _, first = self.call("POST", "/api/v7/doixe/chang/phan-xe", body, runner=db)
        _, again = self.call("POST", "/api/v7/doixe/chang/phan-xe", dict(body), runner=db)
        self.assertEqual(first, again)
        self.assertEqual(db.calls[0], db.calls[1])
        self.assertEqual(len(db.done), 1)

    def test_bad_writes_are_rejected_before_the_db(self):
        key = {"idempotency_key": "k"}
        phan = {"container": "MAUU1000001", "ngay_dong": "2026-11-19", "xe_id": 1}
        nhan = {"chang_id": 5, "kieu": "cap_nhat", "ngay_dong": "2026-11-20"}
        doi = {"chang_id": 5, "truoc": {"xe_id": 1, "tai_xe_id": 2, "ngay": "2026-11-19"}, "xe_id": 2, "tai_xe_id": 3, "ngay": "2026-11-19"}
        cases = [
            ("phan-xe", {**phan, "idempotency_key": None}, "INVALID_REQUEST"),
            ("phan-xe", dict(phan), "INVALID_REQUEST"),   # thiếu mã yêu cầu
            ("phan-xe", {**key, "container": "MAUU1000001", "ngay_dong": "2026-11-19"}, "INVALID_REQUEST"),   # thiếu khóa xe_id
            ("phan-xe", {**key, **phan, "container": ""}, "CONT_THIEU"),
            ("phan-xe", {**key, **phan, "container": "  "}, "CONT_THIEU"),
            ("phan-xe", {**key, **phan, "container": None}, "CONT_THIEU"),
            ("phan-xe", {**key, **phan, "container": 5}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "container": "X" * 41}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "ngay_dong": "2026-02-30"}, "INVALID_DATE"),
            ("phan-xe", {**key, **phan, "ngay_dong": None}, "INVALID_DATE"),
            ("phan-xe", {**key, **phan, "ngay": "19/11/2026"}, "INVALID_DATE"),
            ("phan-xe", {**key, **phan, "xe_id": 0}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "xe_id": "1"}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "xe_id": True}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "tai_xe_id": -1}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "loai": "lạ"}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "kho": "x" * 201}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "ghi_chu": "a\nb"}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "ngay_dong_khac": "2026-11-20"}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "ngay_dong_khac": ["2026-11-20"] * 21}, "INVALID_REQUEST"),
            ("phan-xe", {**key, **phan, "ngay_dong_khac": ["hôm nay"]}, "INVALID_DATE"),
            ("phan-xe", {**key, **phan, "ghi_tien": "1"}, "INVALID_REQUEST"),
            ("doi-phan-cong", {**key, **doi, "truoc": {"xe_id": 1, "tai_xe_id": 2}}, "INVALID_REQUEST"),
            ("doi-phan-cong", {**key, **doi, "truoc": {"xe_id": None, "tai_xe_id": 2, "ngay": "2026-11-19"}}, "INVALID_REQUEST"),
            ("doi-phan-cong", {**key, **doi, "truoc": "x"}, "INVALID_REQUEST"),
            ("doi-phan-cong", {**key, **doi, "ngay": None}, "INVALID_DATE"),
            ("doi-phan-cong", {**key, **{k: v for k, v in doi.items() if k != "ngay"}}, "INVALID_REQUEST"),
            ("doi-phan-cong", {**key, **doi, "chang_id": 0}, "INVALID_REQUEST"),
            ("bo-phan-cong", {**key, "chang_id": "5"}, "INVALID_REQUEST"),
            ("bo-phan-cong", {**key, "chang_id": 5, "ly_do": "x"}, "INVALID_REQUEST"),
            ("nhan-booking", {**key, "chang_id": 5, "kieu": "khac"}, "INVALID_REQUEST"),
            ("nhan-booking", {**key, "chang_id": 5, "kieu": "giu_ngoai", "ngay_dong": "2026-11-20"}, "INVALID_REQUEST"),
            ("nhan-booking", {**key, "chang_id": 5, "kieu": "cap_nhat"}, "INVALID_REQUEST"),
            ("nhan-booking", {**key, **nhan, "ngay_dong": None}, "INVALID_DATE"),
            ("nhan-booking", {**key, **nhan, "container": None}, "CONT_THIEU"),
            ("nhan-booking", {**key, **nhan, "kho": 3}, "INVALID_REQUEST"),
            ("nhan-booking", {**key, **nhan, "xe_id": 1}, "INVALID_REQUEST"),   # nhận booking không đổi xe
        ]
        for name, body, code in cases:
            with self.subTest(name=name, body=body):
                self.rejects("POST", f"/api/v7/doixe/chang/{name}", body, code)
        self.rejects("POST", "/api/v7/doixe/chang/nap-nha-xe", {**key, "nha_xe": []}, "NOT_FOUND")   # công cụ nạp không có đường nào
        self.assertNotIn("doixe_nap_nha_xe", tables.SQL)

    def test_missing_permission_stops_before_any_db_call(self):
        runner = FakeDb()
        for method, path, body in (("GET", "/api/v7/doixe/chang", b""), ("POST", "/api/v7/doixe/chang/phan-xe",
                                   json.dumps({"idempotency_key": "k", "container": "MAUU1000001", "ngay_dong": "2026-11-19", "xe_id": 1}).encode())):
            headers = {**self.headers, "Tailscale-User-Login": "stranger@example.test"}
            with self.subTest(path=path), mock.patch.object(doixe, "load_booking", side_effect=AssertionError("không được đọc bản chụp")):
                with self.assertRaises(identity.IdentityError) as caught:
                    api.handle(method, path, headers, body, runner, port=8780, host="127.0.0.1", source_ip="127.0.0.1",
                               behind_tailscale_serve=True, allowed_logins=frozenset({"nv@gia"}))
                self.assertEqual(caught.exception.code, "LOGIN_NOT_ALLOWED")
        self.assertEqual(runner.calls, [])

    def test_new_error_codes_have_plain_vietnamese_messages(self):
        for code, status in (("CHANG_HANG_DA_CO", 409), ("XE_NGUNG", 422), ("THANG_KHOA", 409), ("CHANG_CO_PHI", 409), ("CHANG_DA_HOAN", 409)):
            with self.subTest(code=code):
                self.assertEqual(tables.ERRORS[code][0], status)
                self.assertGreater(len(tables.ERRORS[code][1]), 20)
        self.assertEqual(doixe.NO_COLUMN[0], "NGUON_THIEU_NHA_XE")


if __name__ == "__main__":
    unittest.main()
