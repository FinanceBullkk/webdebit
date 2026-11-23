#!/usr/bin/env python3
"""Đội xe: sửa lỗi audit 23/11/2026 (DX-01, DX-03, DX-04, DX-06) trên PostgreSQL 18.6 dùng một lần.

Dựng DB như harness V7, chạy sáu migration đội xe cũ rồi `2026-11-23-v7-doi-xe-sua-audit.sql` (lỗi giữa chừng thì quay lại; chạy
lại được; không đổi bảng, quyền, hàm ngoài danh sách thay), nạp danh mục giả rồi gọi thật các hàm `doixe.*` như API. Kiểm:
áp giá ngược về trước tháng này phải kèm xác nhận (NGAY_GIA_CU); ứng, đợt hoàn, tiền về, điều chỉnh bảng kê so số máy người ghi
đang thấy (hai người ghi cùng một khoản từ màn cũ thì người sau bị chặn, không ghi trùng); thiếu trường số đang thấy vẫn chạy như
cũ (áp migration trước bản code không gãy); container có hơn một chặng hàng lệch tới 10 ngày được báo khi lưu và trên bảng kê
đang gom (chỉ báo, không chặn, gửi vẫn khớp dấu); xóa chặng và sửa tên gốc của tuyến so số đang thấy. Dữ liệu giả. Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_doixe_audit.py [--report <file>.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

from pg_v7_harness import (
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
from test_pg_doixe import PHIEU_CHI, Dx, count
from test_pg_doixe import PUBLIC_FUNCTIONS as PUBLIC_1
from test_pg_doixe_chang import MIGRATION_5, PUBLIC_4
from test_pg_doixe_dieu_do import MIGRATION_4, PUBLIC_3
from test_pg_doixe_thu import MIGRATION_2, MIGRATION_3, PUBLIC_2

MIGRATION_6 = Path(__file__).resolve().parent / "migrations" / "2026-11-23-v7-doi-xe-sua-audit.sql"
CHANGED_FUNCS = ("_cont_lap", "_tinh_chang", "_tong_dong", "luu_chang", "xoa_chang", "ghi_ung", "ghi_hoan", "ghi_dieu_chinh_bk",
                 "ghi_tien_ve", "luu_gia", "luu_tuyen")


def months_back(day: dt.date, n: int) -> dt.date:
    y, m = day.year, day.month - n
    while m < 1:
        y, m = y - 1, m + 12
    return dt.date(y, m, 1)


def scenario(pg: Pg, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    today = dt.date.fromisoformat(pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    m0, m1, m2 = today.replace(day=1), months_back(today, 1), months_back(today, 2)
    require(m2 != dt.date(2026, 1, 1) and m1 != dt.date(2026, 1, 1), "harness dùng tháng 1/2026 làm tháng cũ đã khóa")
    new_book(pg, ("2026-01-01", 1000))
    for path in (MIGRATION_1, PHIEU_CHI, MIGRATION_2, MIGRATION_3, MIGRATION_4, MIGRATION_5):   # đúng thứ tự trên hao
        pg.sql(path.read_text(encoding="utf-8"))

    # --- Migration -------------------------------------------------------------------------------------------------------
    source = MIGRATION_6.read_text(encoding="utf-8")
    cols_sql = ("SELECT md5(string_agg(c.relname||'.'||a.attname||a.atttypid::text, ',' ORDER BY c.relname, a.attnum)) FROM pg_class c "
                "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
                "WHERE c.relnamespace = 'doixe'::regnamespace AND c.relkind IN ('r', 'i')")
    names = ",".join(lit(n) for n in CHANGED_FUNCS)
    other_funcs = ("SELECT count(*) || ':' || md5(string_agg(p.oid::regprocedure::text || md5(pg_get_functiondef(p.oid)), ',' "
                   f"ORDER BY p.oid::regprocedure::text)) FROM pg_proc p WHERE p.pronamespace = 'doixe'::regnamespace AND p.proname NOT IN ({names})")
    acl = ("SELECT md5(string_agg(p.oid::regprocedure::text || coalesce(p.proacl::text, ''), ',' ORDER BY p.oid::regprocedure::text)) "
           f"FROM pg_proc p WHERE p.pronamespace = 'doixe'::regnamespace AND p.proname <> '_cont_lap'")
    before = (pg.value(cols_sql), pg.value(other_funcs), pg.value(acl))
    luu_chang_def = pg.value("SELECT md5(pg_get_functiondef('doixe.luu_chang(jsonb)'::regprocedure))")
    pg.rejects(source.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'AUDIT_FAULT'; END $$; COMMIT;"), message="AUDIT_FAULT")
    require(pg.value("SELECT to_regprocedure('doixe._cont_lap(doixe.chang)') IS NULL") == "t"
            and pg.value("SELECT md5(pg_get_functiondef('doixe.luu_chang(jsonb)'::regprocedure))") == luu_chang_def, "migration lỗi không quay lại")
    pg.sql(source)
    pg.sql(source)
    require((pg.value(cols_sql), pg.value(other_funcs), pg.value(acl)) == before,
            "migration chỉ thay định nghĩa hàm trong danh sách: bảng, chỉ mục, hàm khác và quyền giữ nguyên")
    cases.append("migration lỗi thì quay lại, chạy lại được hai lượt; bảng, chỉ mục, các hàm ngoài danh sách thay và quyền giữ nguyên")

    granted = json.loads(pg.value("SELECT coalesce(json_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' "
                                  "ORDER BY 1),'[]') FROM pg_proc p WHERE p.pronamespace='doixe'::regnamespace "
                                  "AND has_function_privilege('v7_app',p.oid,'EXECUTE')"))
    require(sorted(granted) == sorted(PUBLIC_1 + PUBLIC_2 + PUBLIC_3 + PUBLIC_4), f"quyền gọi hàm của app sai: {granted}")
    require(pg.value("SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
                     "WHERE p.pronamespace='doixe'::regnamespace AND a.grantee=0 AND a.privilege_type='EXECUTE'") == "0", "PUBLIC gọi được hàm doixe")
    pg.rejects(actor_sql("SELECT doixe._cont_lap(c) FROM doixe.chang c"), user="v7_app", message="permission denied")
    cases.append("quyền: app gọi đúng các hàm như trước, không gọi hàm phụ mới _cont_lap; PUBLIC không gọi được")

    # --- Danh mục giả --------------------------------------------------------------------------------------------------
    dx = Dx(pg)
    pg.value(actor_sql("SELECT doixe.nap_danh_muc(" + lit(json.dumps({
        "nguoi": [{"ma": "TX1", "ten": "Tài xế giả 1", "vai": "tai_xe", "so_du_dau_vnd": "0"},
                  {"ma": "TX2", "ten": "Tài xế giả 2", "vai": "tai_xe", "so_du_dau_vnd": "0"}],
        "xe": [{"bien_so": "99Z-000.01", "nhom": "NHOM GIA", "tai_xe_ma": "TX1"},
               {"bien_so": "99Z-000.02", "nhom": "NHOM GIA", "tai_xe_ma": "TX2"},
               {"bien_so": "99Y-000.01", "nhom": "THUE GIA", "thue_ngoai": True}]}, ensure_ascii=False)) + "::jsonb)", "nap-gia"))
    ids = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT ma_nguon||'|'||id FROM doixe.nguoi").splitlines())}
    xe = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT bien_so||'|'||id FROM doixe.xe").splitlines())}
    tx1, tx2, x1, x2, xt = ids["TX1"], ids["TX2"], xe["99Z-000.01"], xe["99Z-000.02"], xe["99Y-000.01"]
    tuyen = dx.cmd("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "Hàng giả", "di": "Tỉnh giả", "den": None,
                                 "ten_goc": [{"hang": "Hàng giả", "tinh": "Tỉnh giả"}], "gia_vnd": "1000000", "tu_ngay": "2026-01-01"})["tuyen_id"]

    def row(day, cont, *, xe_id=x1, tai_xe=tx1, payer=tx1, loai="hang", phi=None) -> dict:
        return {"ngay": str(day), "container": cont, "loai": loai, "xe_id": xe_id, "tai_xe_id": tai_xe,
                "tra": "nguoi" if payer else "cong_ty", "nguoi_tra_id": payer, "ten_hang": "Hàng giả", "tinh": "Tỉnh giả", "phi": phi or {}}

    # --- DX-04: container có hơn một chặng hàng lệch tới 10 ngày ---------------------------------------------------------
    d2 = lambda n: m2 + dt.timedelta(days=n)  # noqa: E731
    first = dx.cmd("luu_chang", {"rows": [row(d2(4), "MAUU4000001", phi={"nang": "100000"}), row(d2(1), "MAUU4000002"),
                                          row(d2(1), "MAUU4000003")]})
    require(first["ok"] and first["canh_cont"] == [], f"lưu lần đầu không có cảnh báo: {first}")
    key = "luu-lap"
    lap_rows = [row(d2(5), "MAUU4000001", xe_id=x2, tai_xe=tx2, payer=tx2, phi={"nang": "300000", "vetc": "50000"}),      # Sheet sửa ngày rồi dán lại: lệch 1 ngày, xe khác
                row(d2(12), "MAUU4000002"),                                     # lệch 11 ngày: chuyến khác, không báo
                row(d2(2), "MAUU4000003", loai="tra_rong"),                      # chặng trả rỗng: không phải chặng hàng
                row(d2(3), "MAUU4000004", xe_id=xt, tai_xe=None, payer=None),    # hai chặng trong cùng lệnh, cùng container
                row(d2(6), "MAUU4000004", xe_id=xt, tai_xe=None, payer=None),
                row(d2(3), "MAUU4000003", xe_id=xt, tai_xe=None, payer=None)]   # xe thuê: khác nhóm với chặng xe công ty
    lap = dx.cmd("luu_chang", {"rows": lap_rows}, key=key)
    require(lap["ok"] and lap["so_dong"] == 6, f"cảnh báo không chặn lưu: {lap}")
    canh = {(c["container"], c["ngay"]): c["ngay_khac"] for c in lap["canh_cont"]}
    require(canh == {("MAUU4000001", str(d2(5))): [str(d2(4))], ("MAUU4000004", str(d2(3))): [str(d2(6))],
                     ("MAUU4000004", str(d2(6))): [str(d2(3))]}, f"canh_cont sai: {lap['canh_cont']}")
    require(dx.cmd("luu_chang", {"rows": lap_rows}, key=key) == {**lap, "lap_lai": True}, "gửi lại cùng mã trả đúng kết quả cũ kèm cảnh báo")
    book = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    flags = {(x["container"], x["ngay"]): x["cont_lap"] for x in book["dong"]}
    require(flags[("MAUU4000001", str(d2(4)))] == [str(d2(5))] and flags[("MAUU4000001", str(d2(5)))] == [str(d2(4))]
            and flags[("MAUU4000002", str(d2(1)))] is None and flags[("MAUU4000003", str(d2(1)))] is None,
            f"cờ dòng bảng kê sai: {flags}")
    require(book["tong"]["cont_lap"] == 2, f"đếm Trước khi gửi: {book['tong']}")
    cases.append("DX-04: lưu chặng hàng mà container đã có chặng hàng lệch ≤ 10 ngày (cùng nhóm xe) trả canh_cont, vẫn lưu; lệch 11 ngày, "
                 "chặng trả rỗng, xe khác nhóm không báo; gửi lại cùng mã trả đúng cảnh báo; bảng kê đang gom có cờ cont_lap và tổng đếm")

    # --- DX-06: xóa chặng kèm tổng phí đang thấy ----------------------------------------------------------------------
    victim = first["chang_ids"][1]
    dx.cmd("sua_chang", {"chang_id": victim, "cot": "phi:nang", "truoc": None, "gia_tri": "200000"})   # máy khác vừa nhập phí
    dx.reject("xoa_chang", {"chang_id": victim, "tong_vnd": "0"}, "CHANGED")
    require(count(pg, f"SELECT count(*) FROM doixe.chang WHERE id = {victim} AND NOT da_xoa") == 1, "màn cũ không xóa mất chặng có phí mới")
    dx.reject("xoa_chang", {"chang_id": victim, "tong_vnd": "abc"}, "INVALID_VND")
    require(dx.cmd("xoa_chang", {"chang_id": victim, "tong_vnd": "200000"})["ok"], "đúng tổng đang thấy thì xóa được")
    cases.append("DX-06: xóa chặng kèm tổng phí đang thấy; máy khác vừa nhập phí thì CHANGED, chặng còn nguyên; đúng tổng thì xóa")

    # --- DX-01: áp giá ngược phải xác nhận ----------------------------------------------------------------------------
    dx.reject("luu_gia", {"tuyen_id": tuyen, "tu_ngay": str(m1), "gia_vnd": "1100000"}, "NGAY_GIA_CU")
    dx.reject("luu_gia", {"tuyen_id": tuyen, "tu_ngay": str(m0 - dt.timedelta(days=1)), "gia_vnd": "1100000", "xac_nhan_ngay_cu": False},
              "NGAY_GIA_CU")
    dx.reject("luu_gia", {"tuyen_id": tuyen, "tu_ngay": str(m1), "gia_vnd": "1100000", "xac_nhan_ngay_cu": "true"}, "INVALID_COMMAND")
    require(count(pg, f"SELECT count(*) FROM doixe.gia_tuyen WHERE tuyen_id = {tuyen}") == 1, "chưa xác nhận thì không ghi giá")
    nguoc = dx.cmd("luu_gia", {"tuyen_id": tuyen, "tu_ngay": str(m2), "gia_vnd": "1100000", "xac_nhan_ngay_cu": True})
    require(nguoc["ok"] and nguoc["so_chang"] >= 3, f"xác nhận thì áp ngược, đếm chặng đổi: {nguoc}")
    require(dx.cmd("luu_gia", {"tuyen_id": tuyen, "tu_ngay": str(m0), "gia_vnd": "1200000"})["ok"], "mùng 1 tháng này không cần xác nhận")
    nam_sau = dt.date(m0.year + 1, 1, 1)
    require(dx.cmd("luu_gia", {"tuyen_id": tuyen, "tu_ngay": str(nam_sau), "gia_vnd": "1300000"})["ok"], "giá báo trước (năm sau) không cần xác nhận")
    cases.append("DX-01: giá từ ngày trước tháng này (giờ VN) thiếu hoặc sai xác nhận thì NGAY_GIA_CU, không ghi; có xác nhận thì áp ngược; "
                 "tháng này và giá báo trước không cần xác nhận")

    # --- DX-03: ứng và đợt hoàn so số dư đang thấy ---------------------------------------------------------------------
    so_du = lambda n: dx.so("nguoi", n)["so_du_vnd"]  # noqa: E731
    seen = so_du(tx1)
    a = dx.cmd("ghi_ung", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "3000000", "so_du_vnd": seen})
    require(a["ok"] and a["so_du_truoc_vnd"] == seen, f"người A ghi ứng: {a}")
    dx.reject("ghi_ung", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "3000000", "so_du_vnd": seen}, "SO_DU_DOI")
    require(count(pg, f"SELECT count(*) FROM doixe.ung WHERE nguoi_id = {tx1}") == 1, "người B (màn cũ) không ghi trùng lần ứng")
    dx.reject("ghi_ung", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "1", "so_du_vnd": "1.5"}, "INVALID_VND")
    require(dx.cmd("ghi_ung", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "1000", "so_du_vnd": so_du(tx1)})["ok"],
            "tải lại thấy số mới thì ghi được")
    require(dx.cmd("ghi_ung", {"nguoi_id": tx2, "ngay": str(today), "so_tien_vnd": "1000"})["ok"], "thiếu so_du_vnd (code cũ) vẫn ghi được")
    so = dx.so("nguoi", tx2, str(m2))
    dongs = [d for c in so["chua_hoan"] for d in c["dong"] if d["dot_hoan_id"] is None]
    require(dongs, "tài xế 2 có dòng chưa hoàn")
    tong = sum(int(v) for d in dongs for k, v in d["phi"].items() if k != "vetc")
    ids_h = [d["id"] for d in dongs]
    body = {"nguoi_id": tx2, "ngay": str(today), "so_tien_vnd": "0", "dong_ids": ids_h}
    dx.reject("ghi_hoan", {**body, "tong_dong_vnd": str(tong + 1), "so_du_vnd": so_du(tx2)}, "DONG_DA_DOI")
    dx.reject("ghi_hoan", {**body, "tong_dong_vnd": str(tong), "so_du_vnd": str(int(so_du(tx2)) + 1)}, "SO_DU_DOI")
    require(count(pg, f"SELECT count(*) FROM doixe.dot_hoan WHERE nguoi_id = {tx2}") == 0, "số đang thấy sai thì không ghi đợt hoàn")
    h = dx.cmd("ghi_hoan", {**body, "tong_dong_vnd": str(tong), "so_du_vnd": so_du(tx2)})
    require(h["ok"] and h["tong_dong_vnd"] == str(tong), f"đợt hoàn đúng số đang thấy: {h}")
    cases.append("DX-03: hai người ghi cùng một lần ứng từ cùng số dư đang thấy: người sau SO_DU_DOI, chỉ một lần ứng; đợt hoàn sai tổng dòng "
                 "đang thấy DONG_DA_DOI, sai số dư SO_DU_DOI, không ghi; thiếu trường số đang thấy (code cũ) vẫn chạy")

    # --- DX-03: điều chỉnh bảng kê và tiền về so số đang thấy -----------------------------------------------------------
    cur = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    sent = dx.cmd("gui_bang_ke", {"thang": str(m2), "doi_vnd": cur["tong"]["doi_vnd"], "so_chang": cur["tong"]["so_chang"], "dau": cur["dau"]})
    require(sent["ok"], f"gửi bảng kê có dòng cont_lap vẫn khớp dấu: {sent}")
    bk = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    doi = bk["tong"]["doi_vnd"]
    line = bk["dong"][0]["id"]
    one = dx.cmd("ghi_dieu_chinh_bk", {"dong_id": line, "so_tien_vnd": "-1000", "ly_do": "HTH báo trùng", "doi_vnd": doi})
    require(one["ok"] and one["doi_truoc_vnd"] == doi, f"điều chỉnh đúng số đang thấy: {one}")
    dx.reject("ghi_dieu_chinh_bk", {"dong_id": line, "so_tien_vnd": "-1000", "ly_do": "HTH báo trùng", "doi_vnd": doi}, "BANG_KE_DOI")
    require(count(pg, "SELECT count(*) FROM doixe.dieu_chinh_bk") == 1, "người sau (màn cũ) không ghi trùng điều chỉnh")
    doi = str(int(doi) - 1000)
    require(dx.cmd("doi_chieu_xong", {"thang": str(m2), "doi_vnd": doi})["ok"], "đối chiếu xong")
    tv = {"thang": str(m2), "ngay": str(today), "so_tien_vnd": "1000"}
    first_tv = dx.cmd("ghi_tien_ve", {**tv, "con_vnd": doi})
    require(first_tv["ok"] and first_tv["con_truoc_vnd"] == doi, f"tiền về đúng số đang thấy: {first_tv}")
    dx.reject("ghi_tien_ve", {**tv, "con_vnd": doi}, "BANG_KE_DOI")
    require(count(pg, "SELECT count(*) FROM doixe.tien_ve") == 1, "hai người cùng thấy tin ngân hàng: người sau không ghi trùng")
    dx.reject("ghi_tien_ve", {**tv, "con_vnd": "-1x"}, "INVALID_VND")
    require(dx.cmd("ghi_tien_ve", tv)["ok"], "thiếu con_vnd (code cũ) vẫn ghi được")
    cases.append("DX-03: điều chỉnh bảng kê và tiền về kèm số đòi / còn phải thu đang thấy: người thứ hai từ màn cũ bị BANG_KE_DOI, "
                 "không ghi trùng; thiếu trường (code cũ) vẫn chạy")

    # --- DX-06: tên gốc của tuyến so bộ đang thấy; ngưng dùng giữ tên gốc, dùng lại được -----------------------------
    base = {"tuyen_id": tuyen, "loai": "hang", "hang": "Hàng giả", "di": "Tỉnh giả", "den": None}
    goc = json.loads(pg.value(f"SELECT json_agg(khoa ORDER BY khoa) FROM doixe.tuyen_ten_goc WHERE tuyen_id = {tuyen}"))
    require(goc == ["HANG GIA|TINH GIA"], f"tên gốc ban đầu: {goc}")
    dx.cmd("luu_tuyen", {**base, "ten_goc": [{"hang": "Hàng giả", "tinh": "Tỉnh giả"}, {"hang": "Hàng giả", "tinh": "Tỉnh khác"}],
                         "ten_goc_truoc": goc})   # máy A thêm tên gốc
    dx.reject("luu_tuyen", {**base, "ten_goc": [], "ten_goc_truoc": goc}, "TUYEN_DOI")   # máy B (màn cũ) bỏ tên gốc cũ
    require(count(pg, f"SELECT count(*) FROM doixe.tuyen_ten_goc WHERE tuyen_id = {tuyen}") == 2, "màn cũ không xóa tên gốc vừa thêm")
    dx.reject("luu_tuyen", {**base, "ten_goc": [], "ten_goc_truoc": "HANG GIA|TINH GIA"}, "INVALID_COMMAND")
    dx.reject("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "Hàng giả 2", "di": "Tỉnh giả", "den": None, "ten_goc": [],
                            "gia_vnd": "1", "tu_ngay": str(m0), "ten_goc_truoc": []}, "INVALID_COMMAND")
    now = ["HANG GIA|TINH GIA", "HANG GIA|TINH KHAC"]
    keep = [{"hang": "Hàng giả", "tinh": "Tỉnh giả"}, {"hang": "Hàng giả", "tinh": "Tỉnh khác"}]
    require(dx.cmd("luu_tuyen", {**base, "ten_goc": keep, "dang_dung": False, "ten_goc_truoc": list(reversed(now))})["ok"],
            "ngưng dùng, bộ tên gốc đang thấy so không theo thứ tự")
    require(count(pg, f"SELECT count(*) FROM doixe.tuyen_ten_goc WHERE tuyen_id = {tuyen}") == 2
            and pg.value(f"SELECT dang_dung FROM doixe.tuyen WHERE id = {tuyen}") == "f", "ngưng dùng giữ tên gốc")
    require(dx.cmd("luu_tuyen", {**base, "ten_goc": keep, "dang_dung": True, "ten_goc_truoc": now})["ok"]
            and pg.value(f"SELECT dang_dung FROM doixe.tuyen WHERE id = {tuyen}") == "t", "dùng lại tuyến đã ngưng")
    require(dx.cmd("luu_tuyen", {**base, "ten_goc": keep})["ok"], "thiếu ten_goc_truoc (code cũ) vẫn chạy")
    cases.append("DX-06/07: sửa tên gốc kèm bộ đang thấy; máy khác vừa thêm tên gốc thì TUYEN_DOI, không xóa mất; ngưng dùng giữ tên gốc, "
                 "dùng lại được; so bộ không theo thứ tự; thiếu trường (code cũ) vẫn chạy")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "audit Đội xe 23/11/2026 (DX-01, DX-03, DX-04, DX-06)", "image": IMAGE, "cases": cases, "result": "fail",
              "cleanup": "not_started"}
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
