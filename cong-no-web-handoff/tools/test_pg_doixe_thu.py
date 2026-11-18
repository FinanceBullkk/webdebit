#!/usr/bin/env python3
"""Đội xe đợt 2 (DOI-XE-THU-01, specs/doi-xe-thu-01.md): thu cước, bảng kê HTH, công nợ cước trên PostgreSQL 18.6 dùng một lần.

Dựng DB như harness V7, chạy migration đợt 1 rồi đợt 2 (lỗi giữa chừng thì quay lại; chạy lại được), nạp danh mục giả rồi gọi
thật các hàm `doixe.*` như API: đọc ghi chú phát sinh, tuyến và tên gốc, giá có ngày áp dụng (rút mooc 70% làm tròn nghìn), giá
nhập tay, gắn tuyến, bảng kê đang gom (chặng xe thuê không vào, chặng ghi muộn sang tháng sau), gửi (chép dòng, số máy đang
thấy khác thì chặn), điều chỉnh có lý do, đối chiếu xong, tiền về (thiếu được, thừa chặn), hủy có lý do, công nợ cước, Lịch sử,
quyền của `v7_app`, mã yêu cầu chống ghi trùng, bảng không sửa/xóa được, schema `sokhach` không đổi. Dữ liệu giả. Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_doixe_thu.py [--report <file>.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import threading
import time
from pathlib import Path

from pg_v7_harness import (
    DATABASE,
    IMAGE,
    HarnessError,
    Pg,
    actor_sql,
    disposable_database,
    lit,
    new_book,
    require,
)
from test_pg_doixe import MIGRATION as MIGRATION_1
from test_pg_doixe import PHIEU_CHI
from test_pg_doixe import PUBLIC_FUNCTIONS as PUBLIC_1
from test_pg_doixe import Dx, count

MIGRATION_2 = Path(__file__).resolve().parent / "migrations" / "2026-11-18-v7-doi-xe-thu.sql"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from v7_api_validate import ApiError  # noqa: E402
from v7_doixe_xlsx import build as build_xlsx  # noqa: E402
from v7_psql import Psql  # noqa: E402
from v7_xlsx_writer import read_workbook  # noqa: E402

PUBLIC_2 = ["doi_chieu_xong(jsonb)", "gan_tuyen(jsonb)", "get_bang_gia(text)", "get_bang_ke(text,date)", "get_lich_su_thu()",
            "ghi_dieu_chinh_bk(jsonb)", "ghi_tien_ve(jsonb)", "gui_bang_ke(jsonb)", "huy_tien_ve(jsonb)", "luu_gia(jsonb)",
            "luu_phat_sinh(jsonb)", "luu_tuyen(jsonb)", "sua_cuoc(jsonb)"]


def months_back(day: dt.date, n: int) -> dt.date:
    y, m = day.year, day.month - n
    while m < 1:
        y, m = y - 1, m + 12
    return dt.date(y, m, 1)


def line_total(line: dict) -> int:
    return sum(int(line[k] or 0) for k in ("cuoc_vnd", "ghep_vnd", "ps_vnd")) + int(line.get("dc_vnd") or 0)


def check_totals(book: dict) -> None:
    """Tổng của máy chủ phải bằng cộng lại từng dòng (tính độc lập ở đây)."""
    lines, tong = book["dong"], book["tong"]
    for key in ("cuoc_vnd", "ghep_vnd", "ps_vnd", "chi_ho_vnd", "dc_vnd"):
        require(int(tong[key]) == sum(int(x.get(key) or 0) for x in lines), f"tổng {key}: {tong[key]}")
    require(int(tong["doi_vnd"]) == sum(line_total(x) for x in lines), f"đòi HTH: {tong['doi_vnd']}")
    paid = sum(int(v["so_tien_vnd"]) for v in book["tien_ve"] if v["huy"] is None)
    require(int(tong["tra_vnd"]) == paid and int(tong["con_vnd"]) == int(tong["doi_vnd"]) - paid, f"đã trả/còn: {tong}")
    require(tong["so_chang"] == len(lines) and tong["chua_gia"] == sum(1 for x in lines if x["cuoc_vnd"] is None), f"đếm: {tong}")
    for line in lines:
        items = [i for i in line["ps"] if "loi" not in i]
        for col in ("ps", "ghep"):
            want = sum(int(i["so_tien_vnd"]) for i in items if i["cot"] == col) if any(i["cot"] == col for i in items) else None
            require((int(line[f"{col}_vnd"]) if line[f"{col}_vnd"] is not None else None) == want, f"dòng {line['container']} {col}")


def scenario(pg: Pg, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    today = dt.date.fromisoformat(pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    m0, m1, m2 = today.replace(day=1), months_back(today, 1), months_back(today, 2)
    tomorrow = today + dt.timedelta(days=1)

    book = new_book(pg, ("2026-01-01", 1000))
    stamp = pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'"))
    pg.sql(MIGRATION_1.read_text(encoding="utf-8"))
    pg.sql(PHIEU_CHI.read_text(encoding="utf-8"))   # đúng thứ tự trên hao: đợt 1, phiếu chi, rồi đợt 2
    source = MIGRATION_2.read_text(encoding="utf-8")
    pg.rejects(source.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'THU_FAULT'; END $$; COMMIT;"), message="THU_FAULT")
    require(pg.value("SELECT to_regclass('doixe.bang_ke') IS NULL AND NOT EXISTS (SELECT 1 FROM pg_attribute "
                     "WHERE attrelid='doixe.loai_phi'::regclass AND attname='chi_ho')") == "t", "migration lỗi không quay lại")
    pg.sql(source)
    pg.sql(source)
    require(pg.value("SELECT string_agg(ma, ',' ORDER BY ma) FROM doixe.loai_phi WHERE chi_ho") == "hasom,moi,xi", "cờ chi hộ phía chi")
    require(count(pg, "SELECT count(*) FROM doixe.phat_sinh") == 14 and count(pg, "SELECT count(*) FROM doixe.ben") == 1, "danh mục thu")
    cases.append("migration đợt 2 (sau đợt 1 và phiếu chi) lỗi thì quay lại, chạy lại được hai lượt; cờ chi hộ xí cont, cont mới, hạ sớm/KH; "
                 "14 khoản phát sinh, một bên HTH")

    granted = json.loads(pg.value("SELECT coalesce(json_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' "
                                  "ORDER BY 1),'[]') FROM pg_proc p WHERE p.pronamespace='doixe'::regnamespace "
                                  "AND has_function_privilege('v7_app',p.oid,'EXECUTE')"))
    require(sorted(granted) == sorted(PUBLIC_1 + PUBLIC_2), f"quyền gọi hàm của app sai: {granted}")
    require(pg.value("SELECT count(*) FROM pg_class c WHERE c.relnamespace='doixe'::regnamespace AND c.relkind IN ('r','S') "
                     "AND has_table_privilege('v7_app',c.oid,'SELECT,INSERT,UPDATE,DELETE')") == "0", "app có quyền trên bảng doixe")
    pg.rejects(actor_sql("SELECT doixe._doc_ghi_chu('_ Neo 100k')"), user="v7_app", message="permission denied")
    pg.rejects("SELECT doixe.get_bang_ke('hth', NULL)", user="v7_app", message="ACTOR_REQUIRED")
    cases.append("quyền: app gọi đúng 11 hàm đợt 1 + 13 hàm đợt 2, không hàm phụ, không bảng; thiếu người làm thì chặn")

    def parse(text: str) -> list[dict]:
        return json.loads(pg.value(f"SELECT doixe._doc_ghi_chu({lit(text)})"))

    dx = Dx(pg)
    dx.reject("luu_phat_sinh", {"ma": "can", "ten": "Cân", "cach": "nhap_tay", "muc_vnd": "100", "muc_them_vnd": None, "chi_ho": True,
                                "cot": "ps", "ten_goc": ["Cân"]}, "MUC_PHAT_SINH")
    dx.reject("luu_phat_sinh", {"ma": "neo", "ten": "Neo", "cach": "theo_ngay", "muc_vnd": "1300000", "muc_them_vnd": "1700000",
                                "chi_ho": False, "cot": "ps", "ten_goc": ["Neo", "Xí cont"]}, "TEN_GOC_TRUNG")
    dx.cmd("luu_phat_sinh", {"ma": "neo", "ten": "Neo", "cach": "theo_ngay", "muc_vnd": "1300000", "muc_them_vnd": "1700000",
                             "chi_ho": False, "cot": "ps", "ten_goc": ["Neo"]})
    dx.cmd("luu_phat_sinh", {"ma": "no_may", "ten": "Nổ máy phát", "cach": "theo_don_vi", "muc_vnd": "230000", "muc_them_vnd": None,
                             "chi_ho": False, "cot": "ps", "ten_goc": ["Nổ máy phát", "Nổ máy", "Máy phát"]})
    dx.cmd("luu_phat_sinh", {"ma": "xi_cont", "ten": "Xí cont", "cach": "co_dinh", "muc_vnd": "250000", "muc_them_vnd": None,
                             "chi_ho": True, "cot": "ps", "ten_goc": ["Xí cont"]})
    expect = [
        ("_ Kiểm hoá 1234k", [("kiem_hoa", 1234000, True, "ps")]),
        ("_ Hạ Sớm 450K\n_ Xí cont 250k", [("ha_som", 450000, True, "ps"), ("xi_cont", 250000, True, "ps")]),
        ("vá vỏ 350K _ Neo 1tr5 _ Neo 1,25tr _ Neo 2tr", [("neo", 1500000, False, "ps"), ("neo", 1250000, False, "ps"),
                                                         ("neo", 2000000, False, "ps")]),
        ("_ Cont mới 210.000đ _ Hạ kiểm hoá 615k", [("cont_moi", 210000, True, "ps"), ("kiem_hoa", 615000, True, "ps")]),
        ("_ Neo 2 ngày _ Nổ máy phát 4 tiếng _ Xí cont", [("neo", 3000000, False, "ps"), ("no_may", 920000, False, "ps"),
                                                         ("xi_cont", 250000, True, "ps")]),
        ("_ Đóng ghép 2 kho cách 70km 3100k", [("dong_ghep", 3100000, False, "ghep")]),
        ("__ Bãi xe 100k", [("bai_cho", 100000, False, "ps")]),
        ("_ Phí lạ 1.150.000", [(None, 1150000, False, "ps")]),
    ]
    for text, want in expect:
        got = [(i["ma"], int(i["so_tien_vnd"]), i["chi_ho"], i["cot"]) for i in parse(text)]
        require(got == want, f"đọc {text!r}: {got}")
    require(parse("vá vỏ 350K, tưới vỏ 80K") == [] and parse("abc_def 100k") == [] and parse("") == [], "chữ không có _ không đọc")
    errors = {text: parse(text)[0].get("loi") for text in ("_ Kiểm hoá 1234", "_ Cân", "_ Kiểm hoá", "_ Xí cont 0k", "_ 300k", "_ Neo 1600", "_ Kiểm hoá 1.234k", "_ Neo 1,5k", "_ Xí cont 150k ĐIỀU ĐỘ 450K")}
    require(errors.pop("_ 300k") is None and all(errors.values()), f"ghi chú lỗi: {errors}")
    require(parse("_ 300k")[0].get("la") is True, "khoản không tên vẫn tính, gắn cờ lạ")
    require(all("loi" in parse(text)[0] and "so_tien_vnd" not in parse(text)[0] for text in errors), f"khoản lỗi không tính: {errors}")
    require(pg.value("SELECT doixe._fold(' Sầu  ĐÔNG đắk lắk ')") == "SAU DONG DAK LAK", "chuẩn hóa chữ")
    cases.append("đọc ghi chú «_ Tên khoản số k»: k/tr/1tr5/1,25tr/1.150.000đ, theo ngày, theo đơn vị, mức cố định, tên dài nhất, "
                 "chữ không có _ bỏ qua; thiếu đơn vị, chưa có mức, 0k: không tính; khoản lạ vẫn tính, gắn cờ")

    # Danh mục giả, tuyến, giá.
    pg.value(actor_sql("SELECT doixe.nap_danh_muc(" + lit(json.dumps({
        "nguoi": [{"ma": "TX1", "ten": "Tài xế giả 1", "vai": "tai_xe", "so_du_dau_vnd": "0"},
                  {"ma": "TX2", "ten": "Tài xế giả 2", "vai": "tai_xe", "so_du_dau_vnd": "0"}],
        "xe": [{"bien_so": "99Z-000.01", "nhom": "NHOM GIA", "tai_xe_ma": "TX1"},
               {"bien_so": "99Z-000.02", "nhom": "NHOM GIA", "tai_xe_ma": "TX2"},
               {"bien_so": "99Y-000.01", "nhom": "THUE GIA", "thue_ngoai": True}]}, ensure_ascii=False)) + "::jsonb)", "nap-gia"))
    ids = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT ma_nguon||'|'||id FROM doixe.nguoi").splitlines())}
    xe = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT bien_so||'|'||id FROM doixe.xe").splitlines())}
    tx1, tx2, x1, x2, xt = ids["TX1"], ids["TX2"], xe["99Z-000.01"], xe["99Z-000.02"], xe["99Y-000.01"]

    r1 = dx.cmd("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "Sầu riêng", "di": "Krông Pắc", "den": "Cát Lái",
                              "ten_goc": [{"hang": "Sầu đông", "tinh": "Krongpak Đaklak"}], "gia_vnd": "9850500", "tu_ngay": "2026-01-01"})["tuyen_id"]
    rc = dx.cmd("luu_tuyen", {"tuyen_id": None, "loai": "chuyen_cang", "hang": None, "di": "Các cảng", "den": None, "ten_goc": [],
                              "gia_vnd": "700000", "tu_ngay": "2026-01-01"})["tuyen_id"]
    dx.reject("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "SẦU RIÊNG", "di": "krông pắc", "den": "cát lái", "ten_goc": [],
                            "gia_vnd": "1", "tu_ngay": "2026-01-01"}, "TUYEN_TRUNG")
    dx.reject("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "Dừa", "di": "Bến Tre", "den": None,
                            "ten_goc": [{"hang": "SAU DONG", "tinh": "KRONGPAK DAKLAK"}], "gia_vnd": "1", "tu_ngay": "2026-01-01"}, "TEN_GOC_TRUNG")
    dx.reject("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": None, "di": "Bến Tre", "den": None, "ten_goc": [],
                            "gia_vnd": "1", "tu_ngay": "2026-01-01"}, "TUYEN_THIEU")
    dx.reject("luu_gia", {"tuyen_id": r1, "tu_ngay": str(today + dt.timedelta(days=400)), "gia_vnd": "1"}, "NGAY_GIA_XA")
    require(pg.value(f"SELECT doixe._gia_bang('hth', 'tha_mooc', t, DATE '2026-02-01') FROM doixe.tuyen t WHERE id = {r1}") == "6895000",
            "thả mooc 70% làm tròn nghìn")
    require(pg.value("SELECT (5000::bigint * 7 + 5000) / 10000 * 1000") == "4000", "nửa nghìn làm tròn lên")
    cases.append("tuyến: thêm kèm giá đầu và tên gốc; trùng tuyến, trùng tên gốc, thiếu tên hàng, ngày áp dụng quá xa chặn; mooc 70% nghìn")

    def row(day, cont, *, loai="hang", xe_id=x1, tai_xe=tx1, hang="Sầu đông", tinh="KRONGPAK ĐAKLAK", ghi=None) -> dict:
        return {"ngay": str(day), "container": cont, "loai": loai, "xe_id": xe_id, "tai_xe_id": tai_xe, "tra": "nguoi" if tai_xe else "cong_ty",
                "nguoi_tra_id": tai_xe, "ten_hang": hang, "tinh": tinh, "ghi_chu": ghi, "phi": {}}

    d = lambda n: m2 + dt.timedelta(days=n)  # noqa: E731
    saved = dx.cmd("luu_chang", {"rows": [
        row(d(1), "MAUU1000001", ghi="_ Kiểm hoá 1234k _ Xí cont 250k"),
        row(d(2), "MAUU1000002", xe_id=x2, tai_xe=tx2, ghi="vá vỏ _ Neo 2 ngày _ Nổ máy phát 3"),
        row(d(4), "MAUU1000003", hang="THANH LONG", tinh="BÌNH THUẬN", ghi="_ Đóng ghép 3100k _ Lấy Đồng An 330k"),
        row(d(5), "MAUU1000004", loai="chuyen_cang", hang=None, tinh=None),
        row(d(6), "MAUU1000005", loai="rut_mooc"),
        row(d(7), "MAUU1000006", ghi="_ Cân _ CHI KIỂM CONT 250k"),
        row(d(3), "MAUU1000007", xe_id=xt, tai_xe=None),
        row(d(8), "MAUU1000008")]})
    require(saved["ok"], f"lưu chặng: {saved}")
    legs = dict(zip(["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"], saved["chang_ids"], strict=True))
    cur = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    require(cur["bang_ke"] is None and [x["container"] for x in cur["dong"]]
            == ["MAUU1000001", "MAUU1000002", "MAUU1000003", "MAUU1000004", "MAUU1000005", "MAUU1000006", "MAUU1000008"],
            f"đang gom: chặng xe thuê không vào, theo ngày: {[x['container'] for x in cur['dong']]}")
    line = {x["container"]: x for x in cur["dong"]}
    require(line["MAUU1000001"]["cuoc_vnd"] == "9850500" and line["MAUU1000005"]["cuoc_vnd"] == "6895000"
            and line["MAUU1000004"]["cuoc_vnd"] == "700000" and line["MAUU1000004"]["tuyen_id"] == rc
            and line["MAUU1000003"]["cuoc_vnd"] is None
            and line["MAUU1000003"]["tuyen"] is None, "giá theo tuyến, mooc 70%, chuyển cảng một tuyến, chưa có giá để trống")
    require(line["MAUU1000002"]["ps_vnd"] == "3690000" and line["MAUU1000003"]["ghep_vnd"] == "3100000"
            and line["MAUU1000001"]["chi_ho_vnd"] == "1484000" and line["MAUU1000006"]["chua_doc"] == 1
            and line["MAUU1000006"]["khoan_la"] == 1 and line["MAUU1000006"]["ps_vnd"] == "250000", "phát sinh, đóng ghép, chi hộ, cờ")
    check_totals(cur)
    cases.append("đang gom: chặng xe công ty của tháng, cước theo tuyến (tên gốc, chặng phụ một tuyến, mooc 70%), chưa có giá trống; "
                 "phát sinh và đóng ghép đọc từ ghi chú; tổng bằng cộng từng dòng")

    # Giá nhập tay; giá đổi từ ngày áp dụng chỉ đổi chặng theo bảng giá từ ngày đó.
    dx.reject("sua_cuoc", {"chang_id": legs["c8"], "truoc": "1", "gia_tri": "9000000"}, "CHANGED")
    dx.reject("sua_cuoc", {"chang_id": legs["c7"] + 999, "truoc": None, "gia_tri": "1"}, "CHANG_NOT_FOUND")
    require(dx.cmd("sua_cuoc", {"chang_id": legs["c8"], "truoc": None, "gia_tri": "9000000"})["cuoc_tay"] is True, "giá tay")
    require(dx.cmd("sua_cuoc", {"chang_id": legs["c1"], "truoc": None, "gia_tri": "9850500"})["khong_doi"], "bằng giá bảng là theo bảng")
    moved = dx.cmd("luu_gia", {"tuyen_id": r1, "tu_ngay": str(d(7)), "gia_vnd": "10000000"})
    require(moved["so_chang"] == 1, f"đổi giá từ ngày: {moved}")
    cur = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    line = {x["container"]: x for x in cur["dong"]}
    require(line["MAUU1000006"]["cuoc_vnd"] == "10000000" and line["MAUU1000005"]["cuoc_vnd"] == "6895000"
            and line["MAUU1000008"]["cuoc_vnd"] == "9000000" and line["MAUU1000008"]["gia_bang_vnd"] == "10000000", "đổi giá từ ngày")
    tong = cur["tong"]
    require((tong["cuoc_vnd"], tong["ghep_vnd"], tong["ps_vnd"], tong["chi_ho_vnd"], tong["doi_vnd"])
            == ("46296000", "3100000", "5754000", "1484000", "55150000")
            and (tong["so_chang"], tong["chua_gia"], tong["khac_gia"], tong["chua_doc"], tong["khoan_la"]) == (7, 1, 1, 1, 1), f"tổng: {tong}")
    check_totals(cur)
    gia = dx.read("doixe.get_bang_gia('hth')")
    r1_row = next(t for t in gia["tuyen"] if t["id"] == r1)
    require([g["gia_vnd"] for g in r1_row["gia"]] == ["9850500", "10000000"] and r1_row["ten_goc"] == ["SAU DONG|KRONGPAK DAKLAK"]
            and r1_row["cho_doi"] == [str(d(i)) for i in (1, 2, 6, 7)], f"bảng giá: {r1_row}")
    cases.append("giá tay (CHANGED khi khác máy, bằng giá bảng thì theo bảng); giá mới từ ngày chỉ đổi chặng theo bảng từ ngày đó; "
                 "bảng giá có lịch giá, tên gốc, ngày chặng chờ đổi")

    # Gửi: số máy đang thấy phải khớp; chép dòng; lặp lệnh trả kết quả cũ; gửi lần hai, tháng trống chặn.
    dx.reject("gui_bang_ke", {"thang": str(m2), "doi_vnd": "55150001", "so_chang": 7}, "BANG_KE_DOI")
    dx.reject("gui_bang_ke", {"thang": str(m2), "doi_vnd": "55150000", "so_chang": 6}, "BANG_KE_DOI")
    dx.reject("gui_bang_ke", {"thang": str(m0.replace(day=2)), "doi_vnd": "0", "so_chang": 0}, "INVALID_MONTH")
    sent = dx.cmd("gui_bang_ke", {"thang": str(m2), "doi_vnd": "55150000", "so_chang": 7}, key="gui-m2")
    again = dx.cmd("gui_bang_ke", {"thang": str(m2), "doi_vnd": "55150000", "so_chang": 7}, key="gui-m2")
    require(sent["so"] == f"HTH-{m2:%Y-%m}" and again.get("lap_lai") and again["bang_ke_id"] == sent["bang_ke_id"], f"gửi: {sent} {again}")
    dx.reject("gui_bang_ke", {"thang": str(m2), "doi_vnd": "55150000", "so_chang": 7}, "BANG_KE_DA_GUI")
    empty = months_back(today, 3)
    dx.reject("gui_bang_ke", {"thang": str(empty), "doi_vnd": "0", "so_chang": 0}, "BANG_KE_TRONG")
    before = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    require(before["bang_ke"]["trang_thai"] == "da_gui" and before["tong"]["doi_vnd"] == "55150000"
            and [x["stt"] for x in before["dong"]] == list(range(1, 8)), "đã gửi: chép đủ 7 dòng theo thứ tự")
    check_totals(before)
    # Sau khi gửi: đổi giá, sửa ghi chú, giá tay không đổi bảng kê; chặng đã gửi không sửa phần thu được.
    dx.cmd("luu_gia", {"tuyen_id": r1, "tu_ngay": str(d(0)), "gia_vnd": "12100000"})
    dx.cmd("sua_chang", {"chang_id": legs["c2"], "cot": "ghi_chu", "truoc": "vá vỏ _ Neo 2 ngày _ Nổ máy phát 3", "gia_tri": "_ Neo 9100k"})
    dx.reject("sua_cuoc", {"chang_id": legs["c1"], "truoc": None, "gia_tri": "1"}, "CHANG_DA_GUI")
    dx.reject("gan_tuyen", {"chang_id": legs["c3"], "tuyen_id": r1, "nho": False}, "CHANG_DA_GUI")
    after = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    require(after["dong"] == before["dong"] and after["tong"] == before["tong"], "bảng kê đã gửi không đổi theo giá, ghi chú")
    cases.append("gửi: số đòi/số chặng máy đang thấy khác thì chặn; chép dòng, số bảng kê; lặp lệnh trả kết quả cũ; gửi lần hai, "
                 "tháng trống chặn; sau gửi đổi giá, sửa ghi chú không đổi bảng kê; phần thu chặng đã gửi không sửa")

    # Chặng ghi muộn vào tháng đã gửi sang bảng kê đang gom kế tiếp; gắn tuyến nhớ tên gốc.
    late = dx.cmd("luu_chang", {"rows": [row(d(9), "MAUU1000009"), row(m1 + dt.timedelta(days=1), "MAUU1000010", hang="Thanh long",
                                                                         tinh="Bình Thuận")]})["chang_ids"]
    nxt = dx.read(f"doixe.get_bang_ke('hth', {lit(m1)}::date)")
    require([x["chang_id"] for x in nxt["dong"]] == late and nxt["dong"][0]["ngay"] == str(d(9)), f"ghi muộn sang tháng sau: {nxt['dong']}")
    require(dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")["tong"]["so_chang"] == 7, "bảng kê đã gửi không nhận chặng muộn")
    r3 = dx.cmd("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "Thanh long", "di": "Bình Thuận", "den": None, "ten_goc": [],
                              "gia_vnd": "800000", "tu_ngay": str(m1)})["tuyen_id"]
    dx.reject("gan_tuyen", {"chang_id": late[1], "tuyen_id": r3 + 99, "nho": True}, "TUYEN_NOT_FOUND")
    linked = dx.cmd("gan_tuyen", {"chang_id": late[1], "tuyen_id": r3, "nho": True})
    require(linked["so_chang"] == 1 and pg.value("SELECT tuyen_id FROM doixe.tuyen_ten_goc WHERE khoa = 'THANH LONG|BINH THUAN'") == str(r3),
            f"gắn tuyến nhớ tên gốc: {linked}")
    nxt = dx.read(f"doixe.get_bang_ke('hth', {lit(m1)}::date)")
    require(nxt["dong"][1]["cuoc_vnd"] == "800000" and nxt["dong"][1]["tuyen"] == "Thanh long · Bình Thuận", "giá sau khi gắn tuyến")
    dx.cmd("gan_tuyen", {"chang_id": late[1], "tuyen_id": None, "nho": False})
    months = {m["thang"]: m["trang_thai"] for m in dx.read("doixe.get_bang_ke('hth', NULL)")["thang_ds"]}
    require(months.get(str(m2)) == "gui" and months.get(str(m1)) == "nhap" and months.get(str(m0)) == "nhap", f"thanh tháng: {months}")
    cases.append("chặng ghi muộn vào tháng đã gửi sang bảng kê đang gom kế tiếp; gắn tuyến nhớ tên gốc đổi giá; thanh tháng có trạng thái")

    # Điều chỉnh: lý do bắt buộc, khác 0, dòng không âm; đối chiếu xong thì thôi nhận.
    dong = {x["container"]: x for x in dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")["dong"]}
    dx.reject("ghi_dieu_chinh_bk", {"dong_id": dong["MAUU1000006"]["id"], "so_tien_vnd": "-250000", "ly_do": " "}, "LY_DO_DIEU_CHINH")
    dx.reject("ghi_dieu_chinh_bk", {"dong_id": dong["MAUU1000006"]["id"], "so_tien_vnd": "0", "ly_do": "x"}, "INVALID_VND")
    dx.reject("ghi_dieu_chinh_bk", {"dong_id": dong["MAUU1000004"]["id"], "so_tien_vnd": "-800000", "ly_do": "x"}, "DIEU_CHINH_AM")
    dx.reject("ghi_tien_ve", {"thang": str(m2), "ngay": str(today), "so_tien_vnd": "1", "ghi_chu": None}, "BANG_KE_CHUA_DOI_CHIEU")
    adj = dx.cmd("ghi_dieu_chinh_bk", {"dong_id": dong["MAUU1000006"]["id"], "so_tien_vnd": "-250000", "ly_do": "HTH không chịu khoản lạ"})
    require((adj["doi_truoc_vnd"], adj["doi_sau_vnd"]) == ("55150000", "54900000"), f"điều chỉnh: {adj}")
    cur = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    require(cur["tong"]["dc_vnd"] == "-250000" and cur["tong"]["doi_vnd"] == "54900000"
            and next(x for x in cur["dong"] if x["container"] == "MAUU1000006")["dieu_chinh"][0]["ly_do"] == "HTH không chịu khoản lạ", "dòng có điều chỉnh")
    check_totals(cur)
    dx.reject("doi_chieu_xong", {"thang": str(m2), "doi_vnd": "55150000"}, "BANG_KE_DOI")
    dx.reject("doi_chieu_xong", {"thang": str(m1), "doi_vnd": "0"}, "BANG_KE_CHUA_GUI")
    dx.cmd("doi_chieu_xong", {"thang": str(m2), "doi_vnd": "54900000"})
    dx.reject("doi_chieu_xong", {"thang": str(m2), "doi_vnd": "54900000"}, "BANG_KE_DA_DOI_CHIEU")
    dx.reject("ghi_dieu_chinh_bk", {"dong_id": dong["MAUU1000001"]["id"], "so_tien_vnd": "100", "ly_do": "x"}, "BANG_KE_DA_DOI_CHIEU")
    cases.append("điều chỉnh gắn dòng: lý do bắt buộc, khác 0, dòng không âm, đòi HTH trước → sau; đối chiếu xong (số phải khớp) thì "
                 "thôi nhận điều chỉnh; chưa đối chiếu chưa ghi tiền về")

    # Tiền về: ngày, thừa chặn, thiếu ghi được, đủ thì thu đủ; hủy có lý do; công nợ cước.
    dx.reject("ghi_tien_ve", {"thang": str(m2), "ngay": str(tomorrow), "so_tien_vnd": "1", "ghi_chu": None}, "NGAY_TUONG_LAI")
    dx.reject("ghi_tien_ve", {"thang": str(m2), "ngay": str(today - dt.timedelta(days=1)), "so_tien_vnd": "1", "ghi_chu": None},
              "TIEN_VE_TRUOC_GUI")
    dx.reject("ghi_tien_ve", {"thang": str(m2), "ngay": str(today), "so_tien_vnd": "54900001", "ghi_chu": None}, "TIEN_VE_THUA")
    part = dx.cmd("ghi_tien_ve", {"thang": str(m2), "ngay": str(today), "so_tien_vnd": "50000000", "ghi_chu": "đợt 1"})
    require(part["con_sau_vnd"] == "4900000", f"trả thiếu: {part}")
    state = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    require(not state["bang_ke"]["thu_du"] and {m["thang"]: m["trang_thai"] for m in state["thang_ds"]}[str(m2)] == "doi"
            and state["cong_no_vnd"] == "4900000", "trả thiếu: chờ HTH trả, công nợ còn lại")
    dx.reject("ghi_tien_ve", {"thang": str(m2), "ngay": str(today), "so_tien_vnd": "4900001", "ghi_chu": None}, "TIEN_VE_THUA")
    results, errors = [], []

    def race() -> None:
        try:
            results.append(json.loads(pg.sql(dx.sql("ghi_tien_ve", {"idempotency_key": "tv-song-song", "thang": str(m2), "ngay": str(today),
                                                                    "so_tien_vnd": "4900000", "ghi_chu": None}), user="v7_app").stdout.strip()))
        except HarnessError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=race) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    require(not errors and len({r["tien_ve_id"] for r in results}) == 1, f"song song: {results} {errors}")
    require(count(pg, "SELECT count(*) FROM doixe.tien_ve") == 2, "lệnh song song ghi hơn một lần tiền về")
    state = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    require(state["bang_ke"]["thu_du"] and state["tong"]["con_vnd"] == "0" and state["cong_no_vnd"] == "0"
            and {m["thang"]: m["trang_thai"] for m in state["thang_ds"]}[str(m2)] == "du", "trả đủ: thu đủ, công nợ 0")
    first = state["tien_ve"][0]["id"]
    dx.reject("huy_tien_ve", {"tien_ve_id": first, "ly_do": ""}, "LY_DO_THIEU")
    undone = dx.cmd("huy_tien_ve", {"tien_ve_id": first, "ly_do": "ghi nhầm số"})
    require((undone["con_truoc_vnd"], undone["con_sau_vnd"]) == ("0", "50000000"), f"hủy tiền về: {undone}")
    dx.reject("huy_tien_ve", {"tien_ve_id": first, "ly_do": "lần hai"}, "DA_HUY")
    state = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    require(not state["bang_ke"]["thu_du"] and state["cong_no_vnd"] == "50000000" and state["tien_ve"][0]["huy"]["ly_do"] == "ghi nhầm số",
            "hủy: vẫn hiện kèm lý do, công nợ cộng lại")
    check_totals(state)
    cases.append("tiền về: ngày sau hôm nay, trước ngày gửi, trả thừa chặn; trả thiếu ghi được; ba lệnh song song cùng mã ghi một; "
                 "trả đủ thì thu đủ; hủy bắt buộc lý do, không hủy hai lần; công nợ cước = đã gửi + điều chỉnh − tiền về")

    # Lịch sử, bảng chỉ thêm, Lịch sử đợt 1 không lẫn việc thu.
    events = dx.read("doixe.get_lich_su_thu()")["events"]
    kinds = {e["viec"] for e in events}
    require({"gui_bang_ke", "doi_chieu_xong", "dieu_chinh_bk", "ghi_tien_ve", "huy_tien_ve", "sua_cuoc", "gan_tuyen", "sua_gia",
             "luu_tuyen", "luu_phat_sinh"} <= kinds, f"thiếu loại việc thu: {kinds}")
    adj_event = next(e for e in events if e["viec"] == "dieu_chinh_bk")
    require(adj_event["ly_do"] == "HTH không chịu khoản lạ" and adj_event["truoc"]["doi_vnd"] == "55150000"
            and adj_event["sau"]["doi_vnd"] == "54900000" and adj_event["actor"] == "nhan-vien-gia", f"Lịch sử điều chỉnh: {adj_event}")
    require(not ({e["viec"] for e in dx.read("doixe.get_lich_su(NULL,NULL)")["events"]} & kinds), "Lịch sử đợt 1 lẫn việc thu")
    pg.rejects("UPDATE doixe.bang_ke_dong SET cuoc_vnd = 1", message="IMMUTABLE")
    pg.rejects("DELETE FROM doixe.tien_ve", message="IMMUTABLE")
    pg.rejects("DELETE FROM doixe.dieu_chinh_bk", message="IMMUTABLE")
    pg.rejects("DELETE FROM doixe.bang_ke", message="IMMUTABLE")
    cases.append("Lịch sử thu: đủ loại việc, người làm, trước → sau, lý do; Lịch sử đợt 1 không lẫn; dòng bảng kê, điều chỉnh, tiền về, "
                 "bảng kê không sửa/xóa ngầm")

    # Qua đúng adapter của API (SQL cố định trong v7_api_tables, role v7_app).
    app = Psql(pg.name, DATABASE, "v7_app")
    via = app.run("doixe_get_bang_ke", {"thang": str(m2)}, "nv-api")
    require(via["tong"]["doi_vnd"] == "54900000" and app.run("doixe_get_bang_gia", {}, "nv-api")["tuyen"]
            and app.run("doixe_get_lich_su_thu", {}, "nv-api")["events"], "đọc qua adapter")
    paid = app.run("doixe_ghi_tien_ve", {"idempotency_key": "api-tv", "thang": str(m2), "ngay": str(today), "so_tien_vnd": "1000",
                                         "ghi_chu": None}, "nv-api")
    require(paid["ok"] and pg.value("SELECT actor FROM doixe.tien_ve ORDER BY id DESC LIMIT 1") == "nv-api", "ghi qua adapter, người làm")
    try:
        app.run("doixe_ghi_tien_ve", {"idempotency_key": "api-tv2", "thang": str(m2), "ngay": str(today), "so_tien_vnd": "99999999999",
                                      "ghi_chu": None}, "nv-api")
        raise HarnessError("trả thừa lọt qua adapter")
    except ApiError as exc:
        require(exc.status == 409 and exc.code == "TIEN_VE_THUA", f"mã lỗi qua adapter: {exc.code}")
    cases.append("qua adapter API (role v7_app): ba đường đọc, ghi tiền về, trả thừa thành 409 TIEN_VE_THUA, người làm từ phiên")

    # File Excel dựng từ đúng dữ liệu đọc: cùng cột với file debit, tổng khớp tổng máy chủ, bản nháp ghi rõ.
    sent_book = app.run("doixe_get_bang_ke", {"thang": str(m2)}, "nv-api")
    name, body = build_xlsx(sent_book)
    sheet = read_workbook(body)[f"T{m2.month:02d}-{m2.year}"]
    header = sheet[3]
    data_rows = sheet[4:4 + len(sent_book["dong"])]
    col = {title: header.index(title) for title in ("CƯỚC", "ĐÓNG GHÉP", "PHÁT SINH", "CƯỚC TỔNG", "+ - TIỀN")}
    total = sum((r[col["CƯỚC TỔNG"]] or 0) + (r[col["+ - TIỀN"]] if len(r) > col["+ - TIỀN"] and r[col["+ - TIỀN"]] else 0) for r in data_rows)
    require(name == f"BangKe_HTH_T{m2.month:02d}_{m2.year}.xlsx" and sheet[1] == ["Kính gửi: HTH"] and len(header) == 19
            and total == int(sent_book["tong"]["doi_vnd"]) == 54900000, f"Excel bảng kê: {name} {header} {total}")
    draft_name, _ = build_xlsx(app.run("doixe_get_bang_ke", {"thang": str(m1)}, "nv-api"))
    require(draft_name.endswith("_nhap.xlsx"), "bản nháp")
    cases.append("Excel bảng kê từ dữ liệu thật của DB: 19 cột như file debit, Kính gửi HTH, tổng các dòng + điều chỉnh = đòi HTH; "
                 "tháng chưa gửi là bản nháp")

    require(pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'")) == stamp, "doixe đã làm đổi dữ liệu sokhach")
    require(book > 0, "sổ khách giả")
    cases.append("dấu dữ liệu sokhach không đổi sau mọi lệnh thu")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "specs/doi-xe-thu-01.md", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
    started = time.monotonic()
    try:
        with disposable_database(report) as pg:
            scenario(pg, cases)
        report["result"] = "pass"
    except (HarnessError, OSError, ValueError, KeyError, StopIteration, IndexError, TypeError) as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[-3000:]}"
    report["seconds"] = round(time.monotonic() - started, 1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report["result"] != "pass" or report["cleanup"] != "verified_and_removed")


if __name__ == "__main__":
    sys.exit(main())
