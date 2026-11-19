#!/usr/bin/env python3
"""Đội xe: hàm đọc thu, chi, lãi gộp của chặng (DOI-XE-CHANG-01 PR 2, specs/doi-xe-chang-01.md) trên PostgreSQL 18.6 dùng một lần.

Dựng DB như harness V7, chạy năm migration đội xe cũ rồi migration `2026-11-19-v7-doi-xe-tai-chinh-chang.sql` (lỗi giữa chừng thì
quay lại; chạy lại được), nạp danh mục giả, rồi gọi thật `doixe.get_chang_tai_chinh` như API. Kiểm: chi từng khoản kèm người trả và
chi hộ, hoàn, điều chỉnh và bỏ chặng; thu theo giá bảng, giá tay, phát sinh, đóng ghép, khoản chưa đọc được; lãi gộp NULL (không
phải 0) khi thiếu giá, phí, hoặc khoản chưa đọc, hoặc chặng không vào bảng kê; TỔNG CHI theo tháng bằng đúng `get_so` của từng người
trả; TỔNG THU theo tháng bằng đúng `get_bang_ke` (doi_vnd, cuoc_vnd, ghep_vnd, ps_vnd, chi_ho_vnd), cả lúc đang gom lẫn sau khi gửi
(số đã chép, điều chỉnh bảng kê); chặng chọn theo khoảng ngày chạy, ngày đóng và id; hàm chỉ đọc; quyền của `v7_app`; schema `sokhach`
không đổi. Dữ liệu giả. Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_doixe_chang.py [--report <file>.json]
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
from test_pg_doixe_dieu_do import MIGRATION_4, PUBLIC_3
from test_pg_doixe_thu import MIGRATION_2, MIGRATION_3, PUBLIC_2

MIGRATION_5 = Path(__file__).resolve().parent / "migrations" / "2026-11-19-v7-doi-xe-tai-chinh-chang.sql"
PUBLIC_4 = ["get_chang_tai_chinh(jsonb)"]


def months_back(day: dt.date, n: int) -> dt.date:
    y, m = day.year, day.month - n
    while m < 1:
        y, m = y - 1, m + 12
    return dt.date(y, m, 1)


def total(rows: list[dict], key) -> int:
    return sum(int(key(r) or 0) for r in rows)


def scenario(pg: Pg, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    today = dt.date.fromisoformat(pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    m0, m1, m2 = today.replace(day=1), months_back(today, 1), months_back(today, 2)
    require(m2 != dt.date(2026, 1, 1) and m1 != dt.date(2026, 1, 1), "harness dùng tháng 1/2026 làm tháng cũ đã khóa")

    new_book(pg, ("2026-01-01", 1000))
    stamp = pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'"))
    for path in (MIGRATION_1, PHIEU_CHI, MIGRATION_2, MIGRATION_3, MIGRATION_4):   # đúng thứ tự trên hao
        pg.sql(path.read_text(encoding="utf-8"))

    # --- Migration -------------------------------------------------------------------------------------------------------
    source = MIGRATION_5.read_text(encoding="utf-8")
    pg.rejects(source.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'TC_FAULT'; END $$; COMMIT;"), message="TC_FAULT")
    require(pg.value("SELECT to_regprocedure('doixe.get_chang_tai_chinh(jsonb)') IS NULL AND to_regprocedure('doixe._tai_chinh_chang(bigint)') IS NULL")
            == "t", "migration lỗi không quay lại")
    before_tables = pg.value("SELECT string_agg(c.relname || ':' || c.reltuples::bigint, ',' ORDER BY c.relname) FROM pg_class c "
                             "WHERE c.relnamespace = 'doixe'::regnamespace AND c.relkind = 'r'")
    cols = pg.value("SELECT md5(string_agg(c.relname||'.'||a.attname||a.atttypid::text, ',' ORDER BY c.relname, a.attnum)) FROM pg_class c "
                    "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
                    "WHERE c.relnamespace = 'doixe'::regnamespace AND c.relkind = 'r'")
    old_funcs = ("SELECT count(*) || ':' || md5(string_agg(p.oid::regprocedure::text || md5(pg_get_functiondef(p.oid)), ',' "
                 "ORDER BY p.oid::regprocedure::text)) FROM pg_proc p WHERE p.pronamespace = 'doixe'::regnamespace "
                 "AND p.proname NOT IN ('_tai_chinh_chang', 'get_chang_tai_chinh')")
    funcs = pg.value(old_funcs)
    pg.sql(source)
    pg.sql(source)
    after_cols = pg.value("SELECT md5(string_agg(c.relname||'.'||a.attname||a.atttypid::text, ',' ORDER BY c.relname, a.attnum)) FROM pg_class c "
                          "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
                          "WHERE c.relnamespace = 'doixe'::regnamespace AND c.relkind = 'r'")
    require(cols == after_cols, "migration chỉ có hàm đọc: không đổi cột bảng nào")
    require(pg.value("SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'doixe'::regnamespace AND p.proname IN ('_tai_chinh_chang', "
                     "'get_chang_tai_chinh')") == "2", "hai hàm mới")
    require(funcs.split(":")[0] != "0" and pg.value(old_funcs) == funcs and before_tables,
            f"migration đụng hàm cũ của doixe: trước {funcs}, sau {pg.value(old_funcs)}")
    cases.append("migration chỉ có hàm đọc lỗi thì quay lại, chạy lại được hai lượt; không đổi cột của bảng nào; định nghĩa mọi hàm doixe cũ (trừ hai hàm mới) giống hệt trước và sau")

    # --- Quyền -----------------------------------------------------------------------------------------------------------
    granted = json.loads(pg.value("SELECT coalesce(json_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' "
                                  "ORDER BY 1),'[]') FROM pg_proc p WHERE p.pronamespace='doixe'::regnamespace "
                                  "AND has_function_privilege('v7_app',p.oid,'EXECUTE')"))
    require(sorted(granted) == sorted(PUBLIC_1 + PUBLIC_2 + PUBLIC_3 + PUBLIC_4), f"quyền gọi hàm của app sai: {granted}")
    require(pg.value("SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
                     "WHERE p.pronamespace='doixe'::regnamespace AND a.grantee=0 AND a.privilege_type='EXECUTE'") == "0", "PUBLIC gọi được hàm doixe")
    require(pg.value("SELECT count(*) FROM pg_class c WHERE c.relnamespace='doixe'::regnamespace AND c.relkind IN ('r','S') "
                     "AND has_table_privilege('v7_app',c.oid,'SELECT,INSERT,UPDATE,DELETE')") == "0", "app có quyền trên bảng doixe")
    pg.rejects(actor_sql("SELECT doixe._tai_chinh_chang(1)"), user="v7_app", message="permission denied")
    pg.rejects("SELECT * FROM doixe.dong_phi", user="v7_app", message="permission denied")
    pg.rejects("SELECT doixe.get_chang_tai_chinh('{\"ids\":[1]}')", user="v7_app", message="ACTOR_REQUIRED")
    cases.append("quyền: app gọi được get_chang_tai_chinh cùng các hàm cũ, không hàm phụ, không quyền trên bảng; PUBLIC không gọi được; "
                 "thiếu người làm chặn")

    # --- Danh mục giả, tuyến, giá ---------------------------------------------------------------------------------------
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
    r1 = dx.cmd("luu_tuyen", {"tuyen_id": None, "loai": "hang", "hang": "Sầu riêng", "di": "Krông Pắc", "den": "Cát Lái",
                              "ten_goc": [{"hang": "Sầu đông", "tinh": "Krongpak Đaklak"}], "gia_vnd": "9850500", "tu_ngay": "2026-01-01"})["tuyen_id"]

    def row(day, cont, *, xe_id=x1, tai_xe=tx1, payer=tx1, hang="Sầu đông", tinh="KRONGPAK ĐAKLAK", ghi=None, phi=None) -> dict:
        return {"ngay": str(day), "container": cont, "loai": "hang", "xe_id": xe_id, "tai_xe_id": tai_xe,
                "tra": "nguoi" if payer else "cong_ty", "nguoi_tra_id": payer, "ten_hang": hang, "tinh": tinh, "ghi_chu": ghi, "phi": phi or {}}

    d = lambda n: m2 + dt.timedelta(days=n)  # noqa: E731
    saved = dx.cmd("luu_chang", {"rows": [
        row(d(1), "MAUU1000001", ghi="_ Kiểm hoá 1234k _ Xí cont 250k", phi={"nang": "450000", "vetc": "80000", "xi": "150000"}),
        row(d(2), "MAUU1000002", xe_id=x2, tai_xe=tx2, payer=tx2, hang="THANH LONG", tinh="BÌNH THUẬN", ghi="_ Đóng ghép 3100k _ Lấy Đồng An 330k",
            phi={"nang": "450000"}),
        row(d(3), "MAUU1000003"),
        row(d(4), "MAUU1000004", xe_id=xt, tai_xe=None, payer=None, phi={"dau": "1000000"}),
        row(d(5), "MAUU1000005", ghi="_ Cân", phi={"nang": "100000"}),
        row(d(6), "MAUU1000006", xe_id=x2, tai_xe=tx2, payer=None, phi={"nang": "200000"})]})
    require(saved["ok"], f"lưu chặng: {saved}")
    leg = dict(zip("ABCDEF", saved["chang_ids"], strict=True))

    def fin(tu=None, den=None, chang_ids=None, *, user: str = "postgres") -> list[dict]:
        payload = {"tu": tu, "den": den, "ids": chang_ids if chang_ids is not None else []}
        got = json.loads(pg.value(actor_sql("SELECT doixe.get_chang_tai_chinh(" + lit(json.dumps(payload)) + "::jsonb)", "nhan-vien-gia"), user=user))
        return got["chang"]

    def month_fin(month: dt.date) -> dict[int, dict]:
        end = (month + dt.timedelta(days=31)).replace(day=1) - dt.timedelta(days=1)
        return {c["id"]: c for c in fin(str(month), str(end))}

    def khoan(c: dict) -> dict:
        return {k["khoan"]: k for k in c["chi"]["dong"]}

    got = month_fin(m2)
    require(sorted(got) == sorted(leg.values()), f"khoảng tháng phải trả đủ sáu chặng: {sorted(got)}")
    a, b, c, dd, e, f = (got[leg[k]] for k in "ABCDEF")

    # Chi: từng khoản, ai trả, chi hộ; tổng; NULL khi chưa có phí.
    ka = khoan(a)
    require({k: (v["so_tien_vnd"], v["nguoi_tra"], v["chi_ho"]) for k, v in ka.items()}
            == {"nang": ("450000", "nguoi", False), "vetc": ("80000", "cong_ty", False), "xi": ("150000", "nguoi", True)}, f"chi chặng A: {ka}")
    require(ka["nang"]["nguoi_tra_id"] == tx1 and ka["vetc"]["nguoi_tra_id"] is None and ka["vetc"]["da_hoan"] is None
            and ka["nang"]["da_hoan"] is False, "người trả và hoàn từng khoản (công ty trả: không áp dụng hoàn)")
    require(a["chi"]["tong_vnd"] == "680000" and a["chi"]["chi_ho_vnd"] == "150000" and a["chi"]["ngoai_chi_ho_vnd"] == "530000", f"tổng chi A: {a['chi']}")
    require(c["co_phi"] is False and c["chi"]["dong"] == [] and c["chi"]["tong_vnd"] is None and c["chi"]["ngoai_chi_ho_vnd"] is None,
            f"chưa có phí là NULL, không phải 0: {c['chi']}")
    require({k["nguoi_tra"] for k in khoan(f).values()} == {"cong_ty"} and {k["nguoi_tra"] for k in khoan(dd).values()} == {"cong_ty"},
            "chặng công ty trả: mọi khoản là công ty")
    company = sum(int(k["so_tien_vnd"]) for x in got.values() for k in x["chi"]["dong"] if k["nguoi_tra"] == "cong_ty")
    require(company == 80000 + 1000000 + 200000, f"tổng chi công ty trả (VETC của A, dầu của chặng xe thuê, nâng của F): {company}")
    cases.append("chi: từng khoản {khoản, tên, số tiền, người trả, chi hộ, đã hoàn}; VETC và chặng công ty trả là công ty (hoàn không áp "
                 "dụng); chưa có phí thì tổng NULL")

    # Thu: giá bảng, đóng ghép, phát sinh, chi hộ, khoản chưa đọc, chưa có giá.
    require(a["thu"]["cuoc"]["vnd"] == "9850500" and a["thu"]["cuoc"]["tay"] is False and a["thu"]["cuoc"]["tuyen_id"] == r1
            and a["thu"]["ps_vnd"] == "1484000" and a["thu"]["chi_ho_vnd"] == "1484000" and a["thu"]["ghep_vnd"] == "0"
            and a["thu"]["doi_vnd"] == "11334500" and a["thu"]["dc_vnd"] is None, f"thu A: {a['thu']}")
    require(sorted(x["so_tien_vnd"] for x in a["thu"]["dong"]) == ["1234000", "250000"] and all(x["chi_ho"] for x in a["thu"]["dong"]),
            "từng dòng phát sinh {khoản, tên, số tiền, chi hộ}")
    require(b["thu"]["cuoc"]["vnd"] is None and b["thu"]["ghep_vnd"] == "3100000" and b["thu"]["ps_vnd"] == "330000"
            and b["thu"]["doi_vnd"] == "3430000", f"thu B (chưa có giá, cước trống góp 0 vào số đòi): {b['thu']}")
    require(e["thu"]["chua_doc"] == 1 and e["thu"]["dong"] == [] and len(e["thu"]["loi"]) == 1 and e["thu"]["loi"][0]["goc"] == "Cân",
            f"khoản chưa đọc được: {e['thu']}")
    require(dd["thu"] is None and dd["bang_ke_thang"] is None and dd["lai_gop"]["thieu"] == ["khong_vao_bang_ke"], f"xe thuê ngoài: {dd}")
    # Lãi gộp = thu không chi hộ − chi không chi hộ; NULL khi thiếu.
    require(a["lai_gop"] == {"thu_vnd": "9850500", "chi_vnd": "530000", "lai_vnd": "9320500", "thieu": []}, f"lãi A: {a['lai_gop']}")
    require(f["lai_gop"]["lai_vnd"] == "9650500" and f["lai_gop"]["chi_vnd"] == "200000", f"lãi F: {f['lai_gop']}")
    require(b["lai_gop"] == {"thu_vnd": None, "chi_vnd": "450000", "lai_vnd": None, "thieu": ["gia"]}, f"chưa giá: {b['lai_gop']}")
    require(c["lai_gop"] == {"thu_vnd": "9850500", "chi_vnd": None, "lai_vnd": None, "thieu": ["phi"]}, f"chưa phí: {c['lai_gop']}")
    require(e["lai_gop"]["lai_vnd"] is None and e["lai_gop"]["thieu"] == ["doc"], f"khoản chưa đọc: {e['lai_gop']}")
    cases.append("thu: giá bảng, đóng ghép, phát sinh chi hộ, dòng từng khoản, khoản chưa đọc được; lãi gộp = thu không chi hộ − chi không "
                 "chi hộ; NULL (không phải 0) khi chưa giá, chưa phí, còn khoản chưa đọc, hoặc xe thuê ngoài không vào bảng kê")

    # Tổng chi theo tháng bằng đúng get_so của từng người trả; tổng thu theo tháng bằng đúng get_bang_ke.
    def check_chi(month: dt.date, label: str) -> None:
        listed = month_fin(month)
        lines = [k for x in listed.values() for k in x["chi"]["dong"] if k["nguoi_tra"] == "nguoi"]
        for person in (tx1, tx2):
            mine = sum(int(k["so_tien_vnd"]) for k in lines if k["nguoi_tra_id"] == person)
            want = int(dx.so("nguoi", person, str(month))["the"]["chi_vnd"])
            require(mine == want, f"{label}: chi người {person} = {mine}, get_so = {want}")

    def check_thu(month: dt.date, label: str) -> dict:
        # Theo tháng của BẢNG KÊ, không theo ngày chạy: chặng ghi muộn sang bảng kê tháng kế.
        listed = [x for x in fin(str(m2), str(today)) if x["bang_ke_thang"] == str(month)]
        tong = dx.read(f"doixe.get_bang_ke('hth', {lit(month)}::date)")["tong"]
        thu = [x["thu"] for x in listed]
        mine = {"doi_vnd": total(thu, lambda t: t["doi_vnd"]), "cuoc_vnd": total(thu, lambda t: t["cuoc"]["vnd"]),
                "ghep_vnd": total(thu, lambda t: t["ghep_vnd"]), "ps_vnd": total(thu, lambda t: t["ps_vnd"]),
                "chi_ho_vnd": total(thu, lambda t: t["chi_ho_vnd"])}
        want = {k: int(tong[k]) for k in mine}
        require(mine == want and len(listed) == tong["so_chang"], f"{label}: thu {mine} ({len(listed)} chặng) ≠ get_bang_ke {want} ({tong['so_chang']})")
        return tong

    check_chi(m2, "đang gom")
    tong = check_thu(m2, "đang gom")
    require(tong["so_chang"] == 5 and tong["chua_gia"] == 1, f"bảng kê đang gom 5 chặng xe công ty: {tong}")
    cases.append("tổng chi theo tháng từ hàm mới bằng đúng get_so từng người trả; tổng thu bằng đúng get_bang_ke (doi_vnd, cuoc_vnd, ghep_vnd, "
                 "ps_vnd, chi_ho_vnd, số chặng) lúc đang gom")

    # Hoàn và điều chỉnh ở tháng khóa: chi cộng đúng như get_so, từng khoản có cờ đã hoàn.
    chua = dx.so("nguoi", tx1, str(m2))["chua_hoan"]
    dong_ids = [x["id"] for leg_ in chua for x in leg_["dong"] if x["dot_hoan_id"] is None]
    refund = dx.cmd("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "0", "dong_ids": dong_ids})
    require(dong_ids and refund["ok"], "hoàn các dòng của tx1")
    a = month_fin(m2)[leg["A"]]
    ka = khoan(a)
    require(a["da_hoan"] is True and ka["nang"]["da_hoan"] is True and ka["xi"]["da_hoan"] is True and ka["vetc"]["da_hoan"] is None, f"đã hoàn: {ka}")
    require(dx.cmd("huy_hoan", {"dot_id": refund["dot_id"], "ly_do": "chuyển nhầm số"})["ok"], "hủy đợt hoàn")
    a = month_fin(m2)[leg["A"]]
    require(a["da_hoan"] is False and all(k["da_hoan"] is False for k in khoan(a).values() if k["nguoi_tra"] == "nguoi"),
            f"hủy đợt hoàn: các khoản chưa hoàn lại: {khoan(a)}")
    check_chi(m2, "sau khi hủy đợt hoàn")
    refund = dx.cmd("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "0", "dong_ids": dong_ids})
    require(refund["ok"], "hoàn lại")
    edit = dx.cmd("sua_chang", {"chang_id": leg["A"], "cot": "phi:nang", "truoc": "450000", "gia_tri": "500000"})
    require(edit["ok"], f"điều chỉnh nâng: {edit}")
    a = month_fin(m2)[leg["A"]]
    ka = khoan(a)
    require(ka["nang"]["so_tien_vnd"] == "500000" and ka["nang"]["da_hoan"] is False and ka["xi"]["da_hoan"] is True and a["da_hoan"] is True
            and a["chi"]["tong_vnd"] == "730000" and a["lai_gop"]["chi_vnd"] == "580000" and a["lai_gop"]["lai_vnd"] == "9270500",
            f"dòng điều chỉnh cộng vào khoản; phần điều chỉnh chưa hoàn nên khoản chưa hoàn hết: {a['chi']} {a['lai_gop']}")
    check_chi(m2, "sau hoàn và điều chỉnh")
    cases.append("hoàn: cờ đã hoàn từng khoản, hủy đợt hoàn thì về chưa hoàn (khoản vừa điều chỉnh thêm chưa hoàn hết thì chưa); điều chỉnh ở tháng khóa cộng vào khoản; "
                 "tổng chi vẫn bằng get_so")

    # Chặng bỏ ở tháng khóa và chặng xóa ở tháng mở không còn trong hàm; tổng chi vẫn khớp get_so.
    g = dx.cmd("luu_chang", {"rows": [row(m1 + dt.timedelta(days=1), "MAUU1000007", ghi="_ Neo 100k", phi={"nang": "300000", "xi": "50000"})]})["chang_ids"][0]
    check_chi(m1, "tháng m1 trước khi bỏ")
    require(g in month_fin(m1), "chặng mới hiện")
    require(dx.cmd("xoa_chang", {"chang_id": g})["cach"] == "bo", "tháng khóa thì gạch ngang (bỏ)")
    require(g not in month_fin(m1) and g not in {c_["id"] for c_ in fin(None, None, [g])}, "chặng đã bỏ không còn trong hàm, kể cả theo id")
    check_chi(m1, "tháng m1 sau khi bỏ (dòng trừ lại bù đủ)")
    now_leg = dx.cmd("luu_chang", {"rows": [row(today, "MAUU1000008", phi={"nang": "100000"})]})["chang_ids"][0]
    require(now_leg in {x["id"] for x in fin(str(today), str(today))}, "chặng tháng mở hiện")
    require(dx.cmd("xoa_chang", {"chang_id": now_leg})["cach"] == "xoa" and not fin(str(today), str(today)), "chặng tháng mở xóa thì ẩn")
    cases.append("chặng bỏ (tháng khóa) hoặc xóa (tháng mở) không còn trong kết quả, kể cả theo id; tổng chi vẫn bằng get_so")

    # Gửi bảng kê: số đã chép, đóng băng; điều chỉnh bảng kê; tổng thu vẫn bằng get_bang_ke.
    cur = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    sent = dx.cmd("gui_bang_ke", {"thang": str(m2), "doi_vnd": cur["tong"]["doi_vnd"], "so_chang": cur["tong"]["so_chang"], "dau": cur["dau"]})
    require(sent["ok"], f"gửi: {sent}")
    got = month_fin(m2)
    require(all(got[leg[k]]["da_gui"] is True and got[leg[k]]["bang_ke_thang"] == str(m2) for k in "ABCEF") and got[leg["D"]]["da_gui"] is False,
            "chặng đã gửi: cờ da_gui, tháng bảng kê")
    check_thu(m2, "đã gửi")
    dx.cmd("luu_gia", {"tuyen_id": r1, "tu_ngay": str(m2), "gia_vnd": "12100000"})
    dx.cmd("sua_chang", {"chang_id": leg["B"], "cot": "ghi_chu", "truoc": "_ Đóng ghép 3100k _ Lấy Đồng An 330k", "gia_tri": "_ Đóng ghép 1k"})
    again = month_fin(m2)
    require(all(again[leg[k]]["thu"] == got[leg[k]]["thu"] for k in "ABCEF"), "chặng đã gửi giữ số đã chép khi giá, ghi chú đổi sau đó")
    book = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")
    row_a = next(x for x in book["dong"] if x["container"] == "MAUU1000001")
    dx.cmd("ghi_dieu_chinh_bk", {"dong_id": row_a["id"], "so_tien_vnd": "-380000", "ly_do": "HTH báo trùng"})
    adj = month_fin(m2)[leg["A"]]
    require(adj["thu"]["dc_vnd"] == "-380000" and adj["thu"]["doi_vnd"] == str(int(a["thu"]["doi_vnd"]) - 380000), f"điều chỉnh bảng kê: {adj['thu']}")
    require(adj["lai_gop"]["thu_vnd"] == "9470500" and adj["lai_gop"]["lai_vnd"] == "8890500", f"lãi sau điều chỉnh bảng kê: {adj['lai_gop']}")
    check_thu(m2, "đã gửi và có điều chỉnh bảng kê")
    check_chi(m2, "đã gửi")
    # Ngoại lệ đã ghi trong spec: chặng đã gửi rồi bị bỏ vẫn nằm trong bảng kê (chang_con = false) nhưng hàm này không liệt kê chặng bỏ.
    before = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")["tong"]
    gone = month_fin(m2)[leg["F"]]["thu"]["doi_vnd"]
    require(dx.cmd("xoa_chang", {"chang_id": leg["F"]})["cach"] == "bo", "chặng đã gửi bị bỏ (tháng khóa: gạch ngang)")
    after = dx.read(f"doixe.get_bang_ke('hth', {lit(m2)}::date)")["tong"]
    require(after["doi_vnd"] == before["doi_vnd"] and after["chang_bo"] == 1 and leg["F"] not in month_fin(m2), "bảng kê đã gửi giữ nguyên số, đánh dấu chặng bỏ")
    listed = [x["thu"]["doi_vnd"] for x in fin(str(m2), str(today)) if x["bang_ke_thang"] == str(m2)]
    require(sum(int(v) for v in listed) == int(after["doi_vnd"]) - int(gone), "tổng thu của hàm = get_bang_ke trừ đúng phần chặng đã bỏ")
    check_chi(m2, "sau khi bỏ chặng đã gửi")
    cases.append("chặng đã gửi rồi bị bỏ: bảng kê giữ số và đánh dấu chặng bỏ, hàm không liệt kê chặng bỏ nên tổng thu thấp hơn đúng phần của nó")
    cases.append("đã gửi bảng kê: thu lấy số đã chép (đổi giá, sửa ghi chú sau đó không đổi), điều chỉnh bảng kê vào số đòi và lãi; tổng thu vẫn "
                 "bằng get_bang_ke")

    # Chặng ghi muộn sang bảng kê đang gom kế tiếp; chặng điều độ chọn theo ngày đóng và id.
    require(next(x for x in month_fin(m2).values() if x["id"] == leg["A"])["bang_ke_thang"] == str(m2), "tháng bảng kê của chặng đã gửi")
    late = dx.cmd("luu_chang", {"rows": [row(d(9), "MAUU1000009", ghi="_ Phí lạ 500k", phi={"nang": "100000"})]})["chang_ids"][0]
    require(month_fin(m2)[late]["bang_ke_thang"] == str(m1) and month_fin(m2)[late]["da_gui"] is False,
            "chặng ghi muộn vào tháng đã gửi sang bảng kê đang gom kế tiếp")
    require(dx.cmd("sua_cuoc", {"chang_id": late, "truoc": None, "gia_tri": "9000000"})["cuoc_tay"] is True, "giá tay cho chặng ghi muộn")
    mine_late = month_fin(m2)[late]
    strange = mine_late["thu"]["dong"]
    require(mine_late["thu"]["cuoc"]["tay"] is True and mine_late["thu"]["cuoc"]["vnd"] == "9000000" and mine_late["thu"]["cuoc"]["gia_bang_vnd"] == "12100000"
            and len(strange) == 1 and strange[0]["khoan"] is None and strange[0]["la"] is True and strange[0]["so_tien_vnd"] == "500000"
            and strange[0]["chi_ho"] is False and mine_late["lai_gop"]["lai_vnd"] == "9400000", f"giá tay và khoản lạ: {mine_late['thu']} {mine_late['lai_gop']}")
    check_thu(m1, "bảng kê tháng kế (chặng ghi muộn, giá tay, khoản lạ)")
    placed = dx.cmd("phan_xe", {"container": "MAUU1000010", "ngay_dong": str(today - dt.timedelta(days=3)), "ngay": str(today), "loai": "chuyen_cang",
                                "xe_id": x1})
    h = placed["chang_id"]
    inside = {x["id"] for x in fin(str(today - dt.timedelta(days=3)), str(today - dt.timedelta(days=3)))}
    require(h in inside, "chặng điều độ chọn theo ngày đóng dù ngày chạy ngoài khoảng")
    require(h not in {x["id"] for x in fin(str(today - dt.timedelta(days=2)), str(today - dt.timedelta(days=1)))}, "ngoài cả hai ngày thì không chọn")
    only = fin(None, None, [h])
    require(len(only) == 1 and only[0]["nguon"] == "dieu_do" and only[0]["ngay_dong"] == str(today - dt.timedelta(days=3))
            and only[0]["container"] == "MAUU1000010" and only[0]["xe_id"] == x1 and only[0]["da_gui"] is False,
            "theo id: chặng đầy đủ trường của _chang_dd cộng tài chính")
    require(only[0]["co_phi"] is False and only[0]["lai_gop"]["thieu"] == ["gia", "phi"], f"chặng mới phân xe: chưa giá, chưa phí: {only[0]['lai_gop']}")
    cases.append("khoảng chọn chặng theo ngày chạy hoặc ngày đóng, và theo id; chặng ghi muộn mang tháng bảng kê kế tiếp; chặng mới phân xe "
                 "chưa giá, chưa phí (lãi NULL)")

    # Đo thời gian một tháng đầy (S3): thêm 240 chặng nữa vào tháng m1 (phiên psql mới cho mỗi lượt, cả thời gian docker exec).
    for part in range(2):
        batch = [row(m1 + dt.timedelta(days=n % 28), f"MAUU{2000000 + part * 120 + n:07d}", ghi="_ Xí cont 250k" if n % 2 else None,
                     phi={"nang": "450000", "vetc": "80000"}) for n in range(120)]
        require(dx.cmd("luu_chang", {"rows": batch})["ok"], "nạp 120 chặng")
    month_end = (m1 + dt.timedelta(days=31)).replace(day=1) - dt.timedelta(days=1)
    big = month_fin(m1)
    require(len(big) >= 240, f"một tháng đầy: {len(big)} chặng")

    def timed(statement: str) -> tuple[float, float]:
        """(mili giây trong DB, mili giây cả lượt gọi psql) cho một câu đọc."""
        started = time.monotonic()
        out = pg.value(actor_sql("SELECT clock_timestamp() AS t0 \\gset\n" + statement + ";\nSELECT round(extract(epoch FROM clock_timestamp() - :'t0'::timestamptz) * 1000)",
                                 "nhan-vien-gia")).splitlines()
        return float(out[-1]), round((time.monotonic() - started) * 1000)

    asked = [{"container": x["container"], "ngay_dong": x["ngay"]} for x in big.values()]
    db_fin, wall_fin = timed("SELECT jsonb_array_length(doixe.get_chang_tai_chinh(" + lit(json.dumps({"tu": str(m1), "den": str(month_end), "ids": []})) + "::jsonb)->'chang')")
    db_dd, wall_dd = timed("SELECT jsonb_array_length(doixe.get_dieu_do(" + lit(json.dumps(asked)) + "::jsonb)->'viec')")
    check_chi(m1, "một tháng đầy")
    require(db_fin < 8000 and db_dd < 8000, f"quá chậm: get_chang_tai_chinh {db_fin} ms, get_dieu_do {db_dd} ms")
    cases.append(f"ĐO ({len(big)} chặng một tháng, DB giả dùng một lần, máy dev): get_chang_tai_chinh {db_fin:.0f} ms trong DB ({wall_fin} ms cả lượt psql); "
                 f"get_dieu_do với {len(asked)} việc {db_dd:.0f} ms trong DB ({wall_dd} ms cả lượt); tổng chi vẫn bằng get_so")

    # Đầu vào sai, hàm chỉ đọc, app gọi được, sokhach không đổi.
    for bad, error in (({}, "INVALID_COMMAND"), ({"tu": "2026-01-01"}, "INVALID_COMMAND"), ({"den": "2026-01-01"}, "INVALID_COMMAND"),
                       ({"tu": "2026-02-01", "den": "2026-01-01"}, "INVALID_COMMAND"), ({"tu": "2026-01-01", "den": "2027-03-01"}, "INVALID_COMMAND"),
                       ({"ids": "1"}, "INVALID_COMMAND"), ({"ids": [0]}, "INVALID_COMMAND"), ({"ids": ["1"]}, "INVALID_COMMAND"),
                       ({"ids": [1.5]}, "INVALID_COMMAND"), ({"ids": [True]}, "INVALID_COMMAND"),
                       ({"ids": list(range(1, 3002))}, "INVALID_COMMAND"), ({"ids": [1], "x": 1}, "INVALID_COMMAND"),
                       ({"tu": "2026-13-01", "den": "2026-13-02"}, "INVALID_DATE"), ({"ids": []}, "INVALID_COMMAND"),
                       ({"tu": None, "den": None}, "INVALID_COMMAND")):
        pg.rejects(actor_sql("SELECT doixe.get_chang_tai_chinh(" + lit(json.dumps(bad)) + "::jsonb)"), message=error)
    pg.rejects(actor_sql("SELECT doixe.get_chang_tai_chinh('[]'::jsonb)"), message="INVALID_COMMAND")
    events = count(pg, "SELECT count(*) FROM doixe.su_kien")
    commands = count(pg, "SELECT count(*) FROM doixe.lenh")
    legs_total = count(pg, "SELECT count(*) FROM doixe.chang")
    rows_total = count(pg, "SELECT count(*) FROM doixe.dong")
    via_app = json.loads(pg.value(actor_sql("SELECT doixe.get_chang_tai_chinh(" + lit(json.dumps({"tu": str(m2), "den": str(m0)})) + "::jsonb)", "nhan-vien-gia"),
                                  user="v7_app"))["chang"]
    require(len(via_app) >= 6, f"v7_app gọi được hàm mới: {len(via_app)}")
    require((events, commands, legs_total, rows_total) == (count(pg, "SELECT count(*) FROM doixe.su_kien"), count(pg, "SELECT count(*) FROM doixe.lenh"),
                                                           count(pg, "SELECT count(*) FROM doixe.chang"), count(pg, "SELECT count(*) FROM doixe.dong")),
            "hàm đọc không ghi Lịch sử, lệnh, chặng hay dòng")
    cases.append("đầu vào sai (thiếu khoảng và id, khoảng ngược hoặc quá 400 ngày, id không phải số nguyên dương, quá 3000 id, khóa lạ) bị chặn; "
                 "hàm chỉ đọc; v7_app gọi được")

    require(pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'")) == stamp, "hàm đọc tài chính làm đổi dữ liệu sokhach")
    cases.append("dấu dữ liệu sokhach không đổi")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "specs/doi-xe-chang-01.md", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
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
