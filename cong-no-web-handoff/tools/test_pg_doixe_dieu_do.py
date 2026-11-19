#!/usr/bin/env python3
"""Đội xe: điều độ, chặng sinh từ booking (DOI-XE-DIEU-DO-01, specs/doi-xe-dieu-do-01.md) trên PostgreSQL 18.6 dùng một lần.

Dựng DB như harness V7, chạy bốn migration đội xe cũ rồi migration điều độ (lỗi giữa chừng thì quay lại; chạy lại được), nạp danh
mục giả, rồi gọi thật các hàm `doixe.*` như API: phân xe (một chặng, người trả mặc định, tuyến chuyến khách), mã yêu cầu chống ghi
trùng (ba lệnh song song cùng mã, ba lệnh khác mã cùng việc), luật nối việc ↔ chặng ±3 ngày / ±10 ngày / so nguyên container /
việc gần nhất, từng luật chặn, đổi và bỏ phân công (chặn khi có phí, đã hoàn, đã lên bảng kê đã gửi), nhận thay đổi của booking,
chặng mồ côi, danh mục mã nhà xe, Lịch sử trước → sau, tháng khóa, quyền của `v7_app`, xoa_chang sau khi chuyển thân sang hàm
chung, schema `sokhach` không đổi. Dữ liệu giả (mã nhà xe giả NX-A, NX-B, NX-AB). Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_doixe_dieu_do.py [--report <file>.json]
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
    IMAGE,
    HarnessError,
    Pg,
    actor_sql,
    call,
    disposable_database,
    lit,
    new_book,
    require,
    version,
)
from test_pg_doixe import MIGRATION as MIGRATION_1
from test_pg_doixe import PHIEU_CHI, Dx, count
from test_pg_doixe import PUBLIC_FUNCTIONS as PUBLIC_1
from test_pg_doixe_thu import MIGRATION_2, MIGRATION_3, PUBLIC_2

MIGRATION_4 = Path(__file__).resolve().parent / "migrations" / "2026-11-19-v7-doi-xe-dieu-do.sql"
PUBLIC_3 = ["bo_phan_cong(jsonb)", "doi_phan_cong(jsonb)", "get_dieu_do(jsonb)", "nhan_booking(jsonb)", "phan_xe(jsonb)"]


def scenario(pg: Pg, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    today = dt.date.fromisoformat(pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    m0 = today.replace(day=1)
    m1 = (m0 - dt.timedelta(days=1)).replace(day=1)
    require(m0 != dt.date(2026, 1, 1), "harness dùng tháng 1/2026 làm tháng cũ đã khóa")
    tomorrow = today + dt.timedelta(days=1)

    def day(n: int) -> dt.date:
        return today + dt.timedelta(days=n)

    # Chuyến khách giả (5/1/2026) để thử điền tuyến cho chặng hàng.
    book = new_book(pg, ("2026-01-01", 1000))
    call(pg, "set_month_lock", book, version(pg, book), "kh-1", "2026-01-01", "false")
    trips = json.dumps([{"container": "MAUU1234567", "carrier": "FAKE", "date": "05/01/2026", "from": "KHO GIA A", "to": "CANG GIA B",
                         "unitPriceVnd": "100", "otherFeeVnd": None, "note": "", "src": "FAKE"}])
    call(pg, "paste_trips", book, version(pg, book), "kh-2", "2026-01-01", trips)
    stamp = pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'"))

    # Đúng thứ tự trên hao: đợt 1, phiếu chi, đợt 2, bản sửa bộ đọc ghi chú; rồi dựng dữ liệu "có trước điều độ".
    for path in (MIGRATION_1, PHIEU_CHI, MIGRATION_2, MIGRATION_3):
        pg.sql(path.read_text(encoding="utf-8"))
    pg.value(actor_sql("SELECT doixe.nap_danh_muc(" + lit(json.dumps({
        "nguoi": [{"ma": "TX1", "ten": "Tài xế giả 1", "vai": "tai_xe", "so_du_dau_vnd": "0"},
                  {"ma": "TX2", "ten": "Tài xế giả 2", "vai": "tai_xe", "so_du_dau_vnd": "0"},
                  {"ma": "TX3", "ten": "Tài xế giả đã nghỉ", "vai": "tai_xe", "so_du_dau_vnd": "0", "dang_dung": False},
                  {"ma": "DL1", "ten": "Người đi lệnh giả", "vai": "di_lenh", "so_du_dau_vnd": "0"}],
        "xe": [{"bien_so": "99Z-000.01", "nhom": "NHOM GIA", "tai_xe_ma": "TX1"},
               {"bien_so": "99Z-000.02", "nhom": "NHOM GIA", "tai_xe_ma": "TX2"},
               {"bien_so": "99Z-000.03", "nhom": "NHOM GIA"},
               {"bien_so": "99Z-000.09", "nhom": "NHOM GIA", "dang_dung": False},
               {"bien_so": "99Y-000.01", "nhom": "THUE GIA", "thue_ngoai": True}]}, ensure_ascii=False)) + "::jsonb)", "nap-gia"))
    ids = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT ma_nguon||'|'||id FROM doixe.nguoi").splitlines())}
    xe = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT bien_so||'|'||id FROM doixe.xe").splitlines())}
    tx1, tx2 = ids["TX1"], ids["TX2"]
    x1, x2, x3, xs, xt = xe["99Z-000.01"], xe["99Z-000.02"], xe["99Z-000.03"], xe["99Z-000.09"], xe["99Y-000.01"]
    dx = Dx(pg)

    def row(ngay, cont, *, loai="hang", xe_id=x1, tai_xe=tx1, payer: int | None = tx1, phi=None) -> dict:
        return {"ngay": str(ngay), "container": cont, "loai": loai, "xe_id": xe_id, "tai_xe_id": tai_xe,
                "tra": "nguoi" if payer else "cong_ty", "nguoi_tra_id": payer, "phi": phi or {}}

    legacy = dx.cmd("luu_chang", {"rows": [
        row(today, "MAUU2000001"), row(day(-4), "MAUU2000002"), row(today, "MAUU2000002"), row(day(-12), "MAUU2000003"),
        row(today, "MAUU2000009", phi={"nangha": "100"})]})["chang_ids"]
    leg_a, leg_b1, leg_b2, leg_c, leg_pay = legacy

    # --- Migration -------------------------------------------------------------------------------------------------------
    source = MIGRATION_4.read_text(encoding="utf-8")
    pg.rejects(source.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'DD_FAULT'; END $$; COMMIT;"), message="DD_FAULT")
    require(pg.value("SELECT to_regclass('doixe.ma_nha_xe') IS NULL AND to_regprocedure('doixe.phan_xe(jsonb)') IS NULL AND NOT EXISTS "
                     "(SELECT 1 FROM pg_attribute WHERE attrelid='doixe.chang'::regclass AND attname IN ('ngay_dong','nguon') "
                     "AND NOT attisdropped)") == "t", "migration lỗi không quay lại")
    pg.sql(source)
    pg.sql(source)
    require(count(pg, "SELECT count(*) FROM doixe.ma_nha_xe") == 0, "migration không được seed mã nhà xe")
    require(count(pg, f"SELECT count(*) FROM doixe.chang WHERE id = ANY (ARRAY{legacy}) AND (nguon IS NOT NULL OR ngay_dong IS NOT NULL)") == 0,
            "chặng có trước điều độ phải giữ NULL cả hai ô")
    new_leg = dx.cmd("luu_chang", {"rows": [row(today, "MAUU2000004", xe_id=x2, tai_xe=tx2, payer=tx2)]})["chang_ids"][0]
    require(pg.value(f"SELECT nguon||'|'||coalesce(ngay_dong::text,'null') FROM doixe.chang WHERE id={new_leg}") == "nhap|null",
            "chặng nhập chi phí sau migration phải mang nguon = nhap")
    pg.rejects("UPDATE doixe.chang SET nguon = 'la' WHERE id = " + str(new_leg), message="chang_nguon_check")
    cases.append("migration điều độ lỗi thì quay lại, chạy lại được hai lượt; không seed mã nhà xe; chặng có trước giữ NULL (ngay_dong, nguon); "
                 "chặng nhập chi phí mới mang nguon = nhap; nguon ngoài ba giá trị bị chặn")

    # --- Quyền -----------------------------------------------------------------------------------------------------------
    granted = json.loads(pg.value("SELECT coalesce(json_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' "
                                  "ORDER BY 1),'[]') FROM pg_proc p WHERE p.pronamespace='doixe'::regnamespace "
                                  "AND has_function_privilege('v7_app',p.oid,'EXECUTE')"))
    require(sorted(granted) == sorted(PUBLIC_1 + PUBLIC_2 + PUBLIC_3), f"quyền gọi hàm của app sai: {granted}")
    require(pg.value("SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
                     "WHERE p.pronamespace='doixe'::regnamespace AND a.grantee=0 AND a.privilege_type='EXECUTE'") == "0", "PUBLIC gọi được hàm doixe")
    require(pg.value("SELECT count(*) FROM pg_class c WHERE c.relnamespace='doixe'::regnamespace AND c.relkind IN ('r','S') "
                     "AND has_table_privilege('v7_app',c.oid,'SELECT,INSERT,UPDATE,DELETE')") == "0", "app có quyền trên bảng doixe")
    pg.rejects(actor_sql("SELECT doixe.nap_nha_xe('{}')"), user="v7_app", message="permission denied")
    pg.rejects(actor_sql("SELECT doixe._chang_hang('MAUU1', DATE '2026-11-19')"), user="v7_app", message="permission denied")
    pg.rejects("SELECT * FROM doixe.ma_nha_xe", user="v7_app", message="permission denied")
    pg.rejects("SELECT doixe.get_dieu_do('[]')", user="v7_app", message="ACTOR_REQUIRED")
    pg.rejects("SELECT doixe.phan_xe('{}')", user="v7_app", message="ACTOR_REQUIRED")
    cases.append("quyền: app gọi đúng hàm cũ + 5 hàm điều độ, không hàm phụ, không nap_nha_xe, không bảng; PUBLIC không gọi được; thiếu người làm chặn")

    # --- Danh mục mã nhà xe ----------------------------------------------------------------------------------------------
    def nap_ma(items: list[dict], actor: str = "nap-gia") -> dict:
        return json.loads(pg.value(actor_sql("SELECT doixe.nap_nha_xe(" + lit(json.dumps({"nha_xe": items})) + "::jsonb)", actor)))

    require(nap_ma([{"ma": "NX-A"}, {"ma": "NX-B"}, {"ma": "NX-AB", "dang_dung": False}])["so_ma"] == 3, "nạp mã nhà xe")
    nap_ma([{"ma": "NX-AB", "dang_dung": True}, {"ma": "NX-B", "dang_dung": True}], "nap-gia-2")   # NX-B không đổi: giữ người nạp cũ
    got = pg.value("SELECT string_agg(ma||':'||dang_dung||':'||actor, ',' ORDER BY ma) FROM doixe.ma_nha_xe")
    require(got == "NX-A:true:nap-gia,NX-AB:true:nap-gia-2,NX-B:true:nap-gia", f"danh mục mã nhà xe: {got}")
    # So nguyên mã: mã ngắn không là tiền tố của mã dài; mã dài không nhận chuỗi con.
    require(pg.value("SELECT count(*) FROM doixe.ma_nha_xe WHERE ma = 'NX-A'") == "1"
            and pg.value("SELECT count(*) FROM doixe.ma_nha_xe WHERE ma = 'NX-'") == "0"
            and pg.value("SELECT count(*) FROM doixe.ma_nha_xe WHERE ma = 'nx-a'") == "0", "so nguyên mã")
    for bad in ([], [{"ma": "  "}], [{"ma": "NX\tC"}], [{"ma": "NX-C", "dang_dung": "co"}], [{"ma": "NX-C", "la": 1}],
                [{"ma": "X" * 61}]):
        pg.rejects(actor_sql("SELECT doixe.nap_nha_xe(" + lit(json.dumps({"nha_xe": bad})) + "::jsonb)"), message="INVALID_COMMAND")
    pg.rejects("SELECT doixe.nap_nha_xe('{\"nha_xe\":[{\"ma\":\"NX-C\"}]}')", message="ACTOR_REQUIRED")
    pg.rejects("DELETE FROM doixe.ma_nha_xe WHERE ma = 'NX-A'", message="IMMUTABLE")
    pg.rejects("INSERT INTO doixe.ma_nha_xe(ma, actor) VALUES (' NX-Z', 'x')", message="ma_nha_xe_ma_check")
    nap_events = [e for e in dx.read("doixe.get_lich_su(NULL,NULL)")["events"] if e["viec"] == "nap" and "nha_xe" in e["sau"]]
    require(len(nap_events) == 2 and nap_events[1]["truoc"]["nha_xe"] == [] and len(nap_events[1]["sau"]["nha_xe"]) == 3
            and nap_events[0]["truoc"]["nha_xe"][1] == {"ma": "NX-AB", "dang_dung": False}
            and nap_events[0]["sau"]["nha_xe"][1] == {"ma": "NX-AB", "dang_dung": True}
            and nap_events[0]["actor"] == "nap-gia-2", f"Lịch sử nạp mã nhà xe: {nap_events}")
    cases.append("danh mục mã nhà xe (mã giả NX-A, NX-B, NX-AB): nạp, đổi cờ dang_dung, so nguyên mã, mã rỗng/có ký tự lạ/quá dài/khóa thừa chặn, "
                 "thiếu người làm chặn, không xóa được, Lịch sử nạp trước → sau")

    # --- Mở tháng trước để ngày chạy hôm qua, hôm kia luôn ở tháng mở ----------------------------------------------------------
    dx.cmd("khoa_thang", {"thang": str(m1), "khoa": False})

    def viec(*items: tuple[str, dt.date]) -> dict:
        return dx.read("doixe.get_dieu_do(" + lit(json.dumps([{"container": c, "ngay_dong": str(d)} for c, d in items])) + "::jsonb)")

    def chang_ids(res: dict, i: int = 0) -> list[int]:
        return [c["id"] for c in res["viec"][i]["chang"]]

    def balance(person: int) -> str:
        return dx.so("nguoi", person)["so_du_vnd"]

    def events(viec_name: str) -> list[dict]:
        return [e for e in dx.read("doixe.get_lich_su(NULL,NULL)")["events"] if e["viec"] == viec_name]

    # --- Phân xe: một chặng, người trả mặc định, tuyến chuyến khách -------------------------------------------------------------
    sd_truoc = balance(tx1)
    px = {"container": "MAUU3000001", "ngay_dong": str(today), "xe_id": x1}
    v1 = dx.cmd("phan_xe", px)
    require(v1["ok"] and v1["nguon"] == "dieu_do" and v1["tra"] == "nguoi" and v1["nguoi_tra_id"] == tx1, f"phân xe: {v1}")
    res = viec(("MAUU3000001", today))
    leg = res["viec"][0]["chang"][0]
    require(res["viec"][0]["hang_id"] == v1["chang_id"] and len(res["viec"][0]["chang"]) == 1
            and (leg["loai"], leg["ngay"], leg["ngay_dong"], leg["nguon"], leg["xe_id"], leg["tai_xe_id"], leg["tra"], leg["nguoi_tra_id"])
            == ("hang", str(today), str(today), "dieu_do", x1, tx1, "nguoi", tx1)
            and (leg["co_phi"], leg["da_hoan"], leg["da_gui"]) == (False, False, False), f"đọc chặng vừa phân: {leg}")
    require(count(pg, "SELECT count(*) FROM doixe.chang WHERE container='MAUU3000001'") == 1
            and count(pg, f"SELECT count(*) FROM doixe.dong WHERE chang_id={v1['chang_id']} AND loai='goc'") == 1
            and count(pg, f"SELECT count(*) FROM doixe.dong_phi f JOIN doixe.dong d ON d.id=f.dong_id WHERE d.chang_id={v1['chang_id']}") == 0,
            "một chặng, một dòng gốc, chưa phí (NULL, không phải 0)")
    require(balance(tx1) == sd_truoc, "phân xe không có tiền nên không đổi số dư")
    # Chặng của điều độ nhận tiền qua đường đợt 1 (sổ tài xế), không cần đường mới.
    sd_fee = int(balance(tx1))
    require(dx.cmd("sua_chang", {"chang_id": v1["chang_id"], "cot": "phi:nangha", "truoc": None, "gia_tri": "300"})["cach"] == "ghi_de"
            and int(balance(tx1)) == sd_fee + 300, "nhập phí vào chặng đã phân xe")
    require(viec(("MAUU3000001", today))["viec"][0]["chang"][0]["co_phi"] is True, "cờ co_phi sau khi nhập phí")
    # Người trả: xe không tài xế thì công ty; tài xế chọn tay thì tài xế đó.
    v2 = dx.cmd("phan_xe", {"container": "MAUU3000002", "ngay_dong": str(today), "xe_id": x3})
    v3 = dx.cmd("phan_xe", {"container": "MAUU3000003", "ngay_dong": str(today), "xe_id": x1, "tai_xe_id": tx2})
    v_thue = dx.cmd("phan_xe", {"container": "MAUU3000005", "ngay_dong": str(today), "xe_id": xt})
    row2, row3 = (viec((c, today))["viec"][0]["chang"][0] for c in ("MAUU3000002", "MAUU3000003"))
    require((v2["tra"], v2["nguoi_tra_id"], row2["tai_xe_id"]) == ("cong_ty", None, None)
            and (v3["tra"], v3["nguoi_tra_id"], row3["tai_xe_id"], row3["xe_id"]) == ("nguoi", tx2, tx2, x1)
            and (v_thue["tra"], v_thue["nguoi_tra_id"]) == ("cong_ty", None), f"người trả mặc định: {v2} {v3} {v_thue}")
    # Tuyến chuyến khách điền khi nơi lấy/hạ trống: mở tháng 1/2026 rồi phân xe cho container có chuyến khách ngày 5/1.
    dx.reject("phan_xe", {"container": "MAUU1234567", "ngay_dong": "2026-01-05", "xe_id": x1}, "THANG_KHOA")
    dx.cmd("khoa_thang", {"thang": "2026-01-01", "khoa": False})
    v_jan = dx.cmd("phan_xe", {"container": "MAUU1234567", "ngay_dong": "2026-01-05", "xe_id": x1})
    jan_leg = viec(("MAUU1234567", dt.date(2026, 1, 5)))["viec"][0]["chang"][0]
    require((jan_leg["noi_lay"], jan_leg["noi_ha"], jan_leg["sau_khoa"]) == ("KHO GIA A", "CANG GIA B", False), f"tuyến từ chuyến khách: {jan_leg}")
    v_text = dx.cmd("phan_xe", {"container": "MAUU3000004", "ngay_dong": str(today), "xe_id": x1, "noi_lay": "KHO BOOKING", "noi_ha": "CANG BOOKING",
                                "kho": "KHO", "tinh": "TINH", "ten_hang": "HANG", "ghi_chu": "ghi chú"})
    leg4 = viec(("MAUU3000004", today))["viec"][0]["chang"][0]
    require((leg4["noi_lay"], leg4["noi_ha"], leg4["kho"], leg4["tinh"], leg4["ten_hang"], leg4["ghi_chu"])
            == ("KHO BOOKING", "CANG BOOKING", "KHO", "TINH", "HANG", "ghi chú") and v_text["ok"], f"chữ từ booking: {leg4}")
    ev = events("phan_xe")
    mine = next(e for e in ev if e["sau"]["chang_id"] == v1["chang_id"])
    require(mine["actor"] == "nhan-vien-gia" and mine["truoc"] == {"container": "MAUU3000001", "ngay_dong": str(today), "loai": "hang", "chang_id": None}
            and mine["sau"]["xe_id"] == x1 and mine["sau"]["tai_xe_id"] == tx1 and mine["sau"]["ngay"] == str(today)
            and mine["tai_xe_id"] == tx1 and mine["xe_id"] == x1 and mine["nguoi_id"] == tx1, f"Lịch sử phân xe: {mine}")
    require(any(e["viec"] == "phan_xe" for e in dx.read(f"doixe.get_lich_su({tx1},NULL)")["events"])
            and any(e["viec"] == "phan_xe" for e in dx.read(f"doixe.get_lich_su(NULL,{x1})")["events"]), "Lịch sử lọc theo người và xe")
    cases.append("phân xe: đúng một chặng và một dòng gốc chưa phí, nguon = dieu_do; người trả mặc định (tài xế của xe, tài xế chọn tay, xe không "
                 "tài xế thì công ty); điền tuyến từ chuyến khách và chữ từ booking; nhập phí qua đường đợt 1; Lịch sử có người làm, trước → sau, "
                 "lọc theo người và xe")

    # --- Mã yêu cầu: lặp, khác nội dung, song song ---------------------------------------------------------------------------
    pay = {"container": "MAUU3100001", "ngay_dong": str(today), "xe_id": x2}
    first = dx.cmd("phan_xe", pay, key="px-lap")
    again = dx.cmd("phan_xe", pay, key="px-lap")
    require(again.get("lap_lai") and again["chang_id"] == first["chang_id"]
            and count(pg, "SELECT count(*) FROM doixe.chang WHERE container='MAUU3100001'") == 1, f"lặp lệnh: {again}")
    pg.rejects(dx.sql("phan_xe", {"idempotency_key": "px-lap", **pay, "xe_id": x1}), message="IDEMPOTENCY_CONFLICT")
    results, errors = [], []

    def race(payload: dict) -> None:
        try:
            results.append(json.loads(pg.sql(dx.sql("phan_xe", payload), user="v7_app").stdout.strip()))
        except HarnessError as exc:
            errors.append(str(exc))

    def run_threads(payloads: list[dict]) -> None:
        results.clear()
        errors.clear()
        threads = [threading.Thread(target=race, args=(p,)) for p in payloads]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)

    run_threads([{"idempotency_key": "px-song-song", "container": "MAUU3100002", "ngay_dong": str(today), "xe_id": x1}] * 3)
    require(not errors and len(results) == 3 and len({r["chang_id"] for r in results}) == 1
            and count(pg, "SELECT count(*) FROM doixe.chang WHERE container='MAUU3100002'") == 1, f"ba lệnh cùng mã: {results} {errors}")
    run_threads([{"idempotency_key": f"px-khac-{i}", "container": "MAUU3100003", "ngay_dong": str(today), "xe_id": xe_id}
                 for i, xe_id in enumerate((x1, x2, x3))])
    require(len(results) == 1 and len(errors) == 2 and all("CHANG_HANG_DA_CO" in e for e in errors)
            and count(pg, "SELECT count(*) FROM doixe.chang WHERE container='MAUU3100003'") == 1, f"ba lệnh khác mã cùng việc: {results} {errors}")
    cases.append("mã yêu cầu: lặp trả kết quả cũ, khác nội dung từ chối; ba lệnh song song (role app) cùng mã chỉ ra một chặng; ba lệnh khác mã "
                 "cùng việc chỉ một lệnh thắng, hai lệnh sau bị chặn CHANG_HANG_DA_CO")

    # --- Từng luật chặn của phân xe ----------------------------------------------------------------------------------------
    base = {"container": "MAUU3200001", "ngay_dong": str(today), "xe_id": x1}
    dx.reject("phan_xe", {**base, "container": "   "}, "CONT_THIEU")
    dx.reject("phan_xe", {k: v for k, v in base.items() if k != "container"}, "CONT_THIEU")
    dx.reject("phan_xe", {**base, "container": "M" * 21}, "INVALID_COMMAND")
    dx.reject("phan_xe", {k: v for k, v in base.items() if k != "ngay_dong"}, "INVALID_DATE")
    dx.reject("phan_xe", {**base, "ngay_dong": "19/11/2026"}, "INVALID_DATE")
    dx.reject("phan_xe", {**base, "xe_id": xs}, "XE_NGUNG")
    dx.reject("phan_xe", {**base, "xe_id": 999999}, "XE_KHONG_RO")
    dx.reject("phan_xe", {k: v for k, v in base.items() if k != "xe_id"}, "XE_KHONG_RO")
    dx.reject("phan_xe", {**base, "tai_xe_id": 999999}, "NGUOI_NOT_FOUND")
    dx.reject("phan_xe", {**base, "ngay": str(tomorrow)}, "NGAY_TUONG_LAI")
    dx.reject("phan_xe", {**base, "ngay": str(day(2)), "ngay_dong": str(tomorrow)}, "NGAY_TUONG_LAI")
    dx.reject("phan_xe", {**base, "ngay_dong": "2026-01-05", "container": "MAUU3200009", "ngay": "2025-12-31"}, "THANG_KHOA")
    dx.reject("phan_xe", {**base, "la": 1}, "INVALID_COMMAND")
    dx.reject("phan_xe", {**base, "loai": "bay"}, "INVALID_COMMAND")
    dx.reject("phan_xe", {**base, "loai": 5}, "INVALID_COMMAND")
    dx.reject("phan_xe", {**base, "ngay_dong_khac": "2026-11-19"}, "INVALID_COMMAND")
    dx.reject("phan_xe", {**base, "ngay_dong_khac": [str(today)] * 21}, "INVALID_COMMAND")
    dx.reject("phan_xe", {**px, "xe_id": x2}, "CHANG_HANG_DA_CO")
    require(count(pg, "SELECT count(*) FROM doixe.chang WHERE container IN ('MAUU3200001','MAUU3200009')") == 0, "lệnh bị chặn không được ghi gì")
    # Ngày chạy mai chỉ khi đúng bằng ngày đóng của việc (xe lấy rỗng hôm nay, đóng hàng hôm sau).
    future = dx.cmd("phan_xe", {"container": "MAUU4000001", "ngay_dong": str(tomorrow), "xe_id": x1})
    fut_leg = viec(("MAUU4000001", tomorrow))["viec"][0]["chang"][0]
    require(future["ok"] and fut_leg["ngay"] == str(tomorrow) and fut_leg["sau_khoa"] is False, f"ngày chạy = ngày đóng của mai: {fut_leg}")
    # Chặng phụ: nhiều chặng một việc, mỗi chặng một xe; trùng (ngày, container, loại, xe) bị chặn.
    cp = dx.cmd("phan_xe", {"container": "MAUU3000001", "ngay_dong": str(today), "xe_id": x2, "loai": "chuyen_cang"})
    cp2 = dx.cmd("phan_xe", {"container": "MAUU3000001", "ngay_dong": str(today), "xe_id": x3, "loai": "chuyen_cang"})
    dx.reject("phan_xe", {"container": "MAUU3000001", "ngay_dong": str(today), "xe_id": x2, "loai": "chuyen_cang"}, "TRUNG_CHANG")
    require(chang_ids(viec(("MAUU3000001", today))) == [v1["chang_id"], cp["chang_id"], cp2["chang_id"]], "hàng đứng đầu, chặng phụ theo sau")
    cases.append("phan_xe chặn: container trống/thiếu/quá dài, ngày đóng thiếu/sai, xe ngừng dùng, xe không rõ, tài xế không có, ngày chạy sau hôm nay "
                 "(trừ khi bằng ngày đóng), tháng khóa, khóa thừa, loại sai, đã có chặng hàng chưa bỏ, trùng chặng; lệnh bị chặn không ghi gì; "
                 "chặng phụ không giới hạn, mỗi chặng một xe")

    # --- Luật nối việc ↔ chặng ----------------------------------------------------------------------------------------------
    for delta, want in ((-4, False), (-3, True), (0, True), (3, True), (4, False)):
        require(bool(chang_ids(viec(("MAUU3000001", day(delta))))) is want, f"chặng có ngày đóng: lệch {delta} ngày phải {'nối' if want else 'không nối'}")
    require(not chang_ids(viec(("MAUU300000", today))) and not chang_ids(viec(("MAUU30000011", today)))
            and not chang_ids(viec(("MAUU3000002", day(30)))) and chang_ids(viec(("mauu 3000001", today)))[0] == v1["chang_id"],
            "so nguyên container (không chuỗi con); khoảng trắng và chữ thường chuẩn hóa như sổ khách")
    for delta, want in ((-10, True), (-11, False), (10, True), (11, False)):
        require(bool(chang_ids(viec(("MAUU2000001", day(delta))))) is want, f"chặng cũ: lệch {delta} ngày phải {'nối' if want else 'không nối'}")
    require(chang_ids(viec(("MAUU2000003", today))) == [] and chang_ids(viec(("MAUU2000003", day(-2)))) == [leg_c], "chặng cũ lệch 12 ngày")
    near = viec(("MAUU2000002", day(-3)))["viec"][0]
    require(near["hang_id"] == leg_b1 and [c["id"] for c in near["chang"]] == [leg_b1, leg_b2], f"chặng cũ: gần nhất đứng đầu: {near}")
    # Chặng cũ có ngày đóng (sau khi nhận booking) theo ±3 ngày, không còn theo ±10 ngày của ngày chạy.
    dx.cmd("nhan_booking", {"chang_id": leg_c, "kieu": "cap_nhat", "ngay_dong": str(day(-12))})
    require(chang_ids(viec(("MAUU2000003", day(-2)))) == [] and chang_ids(viec(("MAUU2000003", day(-9)))) == [leg_c], "ngày đóng thay luật 10 ngày")
    # Việc gần nhất: chặng ngày đóng D không bị việc xa hơn cùng container kéo đi; việc khác chỉ biết qua ngay_dong_khac.
    comp = dx.cmd("phan_xe", {"container": "MAUU5000001", "ngay_dong": str(today), "xe_id": x1})
    two = viec(("MAUU5000001", day(-2)), ("MAUU5000001", day(1)))
    require(two["viec"][0]["hang_id"] is None and two["viec"][1]["hang_id"] == comp["chang_id"], f"chặng thuộc việc gần nhất: {two['viec']}")
    dx.reject("phan_xe", {"container": "MAUU5000001", "ngay_dong": str(day(-2)), "xe_id": x2}, "CHANG_HANG_DA_CO")    # chỉ biết một việc
    comp2 = dx.cmd("phan_xe", {"container": "MAUU5000001", "ngay_dong": str(day(-2)), "xe_id": x2, "ngay_dong_khac": [str(day(1))]})
    two = viec(("MAUU5000001", day(-2)), ("MAUU5000001", day(1)))
    require(two["viec"][0]["hang_id"] == comp2["chang_id"] and two["viec"][1]["hang_id"] == comp["chang_id"], f"đọc và ghi cùng luật: {two['viec']}")
    # Chặng cũ bị chặn phân xe mới của đúng việc đó (chặng hàng chưa bỏ): nối theo ngày chạy ±10 ngày.
    dx.reject("phan_xe", {"container": "MAUU2000001", "ngay_dong": str(day(-8)), "xe_id": x2}, "CHANG_HANG_DA_CO")
    other = dx.cmd("phan_xe", {"container": "MAUU2000001", "ngay_dong": str(day(-14)), "xe_id": x2, "ngay": str(day(-1))})
    require(other["ok"], "việc cách chặng cũ quá 10 ngày thì phân xe được")
    cases.append("luật nối: chặng có ngày đóng ±3 ngày, chặng cũ ±10 ngày theo ngày chạy (gần nhất đứng đầu), so nguyên container (không chuỗi con, "
                 "khoảng trắng và chữ thường chuẩn hóa), nhận booking đặt ngày đóng thì theo ±3; hai việc cùng container: chặng về việc gần nhất, "
                 "ghi và đọc cùng luật (ngay_dong_khac)")

    # --- Chặng mồ côi -------------------------------------------------------------------------------------------------------
    live = pg.value("SELECT json_agg(json_build_object('container', container, 'ngay_dong', ngay_dong)) FROM doixe.chang "
                    "WHERE nguon = 'dieu_do' AND NOT da_xoa AND NOT da_bo AND ngay_dong IS NOT NULL")
    all_jobs = json.loads(live)
    res = dx.read("doixe.get_dieu_do(" + lit(json.dumps(all_jobs)) + "::jsonb)")
    require(res["mo_coi"] == [], f"việc nào cũng còn trên booking thì không chặng mồ côi: {res['mo_coi']}")
    gone = next(j for j in all_jobs if j["container"] == "MAUU3000003")
    res = dx.read("doixe.get_dieu_do(" + lit(json.dumps([j for j in all_jobs if j != gone])) + "::jsonb)")
    require([c["id"] for c in res["mo_coi"]] == [v3["chang_id"]] and res["mo_coi"][0]["container"] == "MAUU3000003", f"chặng mồ côi: {res['mo_coi']}")
    require(not {leg_a, leg_b1, leg_b2, new_leg} & {c["id"] for c in res["mo_coi"]}, "chặng cũ/nhập chi phí không bao giờ là mồ côi")
    require(dx.read("doixe.get_dieu_do('[]')")["mo_coi"] == [] and dx.read("doixe.get_dieu_do('[]')")["viec"] == [], "danh sách trống")
    # Container đổi số: chuyển chặng mồ côi sang container mới (nhận booking), Lịch sử trước → sau, không đổi tiền.
    sd2 = balance(tx2)
    moved = dx.cmd("nhan_booking", {"chang_id": v3["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(today), "container": "MAUU3000333"})
    require(moved["ok"] and chang_ids(viec(("MAUU3000333", today))) == [v3["chang_id"]] and chang_ids(viec(("MAUU3000003", today))) == []
            and balance(tx2) == sd2, f"chuyển sang container mới: {moved}")
    nb = events("nhan_booking")[0]
    require(nb["truoc"]["container"] == "MAUU3000003" and nb["sau"]["container"] == "MAUU3000333" and nb["actor"] == "nhan-vien-gia"
            and nb["truoc"]["kieu"] == "cap_nhat", f"Lịch sử nhận booking: {nb}")
    # Booking đổi ngày đóng và chữ: nhận để cập nhật; khóa vắng giữ nguyên, null xóa.
    dx.cmd("nhan_booking", {"chang_id": v3["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(day(-1)), "kho": "KHO MOI", "noi_lay": "LAY MOI"})
    dx.cmd("nhan_booking", {"chang_id": v3["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(day(-1)), "kho": None})
    got3 = viec(("MAUU3000333", day(-1)))["viec"][0]["chang"][0]
    require((got3["ngay_dong"], got3["kho"], got3["noi_lay"], got3["ngay"], got3["xe_id"]) == (str(day(-1)), None, "LAY MOI", str(today), x1),
            f"nhận ngày đóng và chữ: {got3}")
    require(dx.cmd("nhan_booking", {"chang_id": v3["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(day(-1))})["khong_doi"], "không đổi")
    # Giữ thành chặng ngoài booking: ngày đóng NULL, không còn là mồ côi.
    held = dx.cmd("nhan_booking", {"chang_id": comp2["chang_id"], "kieu": "giu_ngoai"})
    require(held["ok"] and pg.value(f"SELECT ngay_dong IS NULL AND nguon = 'dieu_do' FROM doixe.chang WHERE id={comp2['chang_id']}") == "t"
            and dx.cmd("nhan_booking", {"chang_id": comp2["chang_id"], "kieu": "giu_ngoai"})["khong_doi"], "giữ ngoài booking")
    res = dx.read("doixe.get_dieu_do(" + lit(json.dumps([{"container": "MAUU9999999", "ngay_dong": str(day(-14))}, {"container": "MAUU9999998", "ngay_dong": str(tomorrow)}]))
                  + "::jsonb)")
    require(comp2["chang_id"] not in {c["id"] for c in res["mo_coi"]}, "chặng giữ ngoài booking không phải mồ côi")
    for bad, err in (({"kieu": "xoa"}, "INVALID_COMMAND"), ({"kieu": "cap_nhat"}, "INVALID_DATE"),
                     ({"kieu": "cap_nhat", "ngay_dong": str(today), "container": " "}, "CONT_THIEU"),
                     ({"kieu": "cap_nhat", "ngay_dong": str(today), "xe_id": x1}, "INVALID_COMMAND"),
                     ({"kieu": "giu_ngoai", "ngay_dong": str(today)}, "INVALID_COMMAND"),
                     ({"kieu": "cap_nhat", "ngay_dong": str(today), "container": "MAUU3000001"}, "TRUNG_CHANG")):
        dx.reject("nhan_booking", {"chang_id": v3["chang_id"] if err != "TRUNG_CHANG" else v_text["chang_id"], **bad}, err)
    dx.reject("nhan_booking", {"chang_id": 999999, "kieu": "giu_ngoai"}, "CHANG_NOT_FOUND")
    cases.append("chặng mồ côi (nguồn điều độ, ngày đóng trong khoảng, không khớp việc nào); nhận booking: chuyển sang container mới, đặt ngày đóng "
                 "và chữ (khóa vắng giữ nguyên, null xóa), giữ ngoài booking; web không tự sửa; không đổi số dư; Lịch sử trước → sau; sai thì chặn")

    # --- Đổi phân công -------------------------------------------------------------------------------------------------------
    sd_before = (balance(tx1), balance(tx2))
    new = {"chang_id": v3["chang_id"], "truoc": {"xe_id": x1, "tai_xe_id": tx2, "ngay": str(today)}, "xe_id": x2, "tai_xe_id": tx1, "ngay": str(day(-1))}
    dx.reject("doi_phan_cong", {**new, "truoc": {**new["truoc"], "xe_id": x3}}, "CHANGED")
    dx.reject("doi_phan_cong", {k: v for k, v in new.items() if k != "truoc"}, "INVALID_COMMAND")
    dx.reject("doi_phan_cong", {**new, "truoc": {"xe_id": x1}}, "INVALID_COMMAND")
    dx.reject("doi_phan_cong", {**new, "xe_id": xs}, "XE_NGUNG")
    dx.reject("doi_phan_cong", {**new, "xe_id": 999999}, "XE_KHONG_RO")
    dx.reject("doi_phan_cong", {**new, "tai_xe_id": 999999}, "NGUOI_NOT_FOUND")
    dx.reject("doi_phan_cong", {**new, "ngay": str(tomorrow)}, "NGAY_TUONG_LAI")
    dx.reject("doi_phan_cong", {**new, "ngay": "2025-12-10"}, "THANG_KHOA_CHUYEN")
    require(dx.cmd("doi_phan_cong", {**new, "xe_id": x1, "tai_xe_id": tx2, "ngay": str(today)})["khong_doi"], "không đổi")
    changed = dx.cmd("doi_phan_cong", new)
    after = viec(("MAUU3000333", day(-1)))["viec"][0]["chang"][0]
    require(changed["ok"] and (after["xe_id"], after["tai_xe_id"], after["ngay"], after["tra"], after["nguoi_tra_id"], after["ngay_dong"])
            == (x2, tx1, str(day(-1)), "nguoi", tx1, str(day(-1))), f"đổi phân công, người trả theo tài xế mới: {after}")
    require((balance(tx1), balance(tx2)) == sd_before, "đổi phân công chưa có phí nên số dư không đổi")
    dx.reject("doi_phan_cong", new, "CHANGED")      # máy khác đã đổi rồi
    ev = events("doi_phan_cong")[0]
    require(ev["actor"] == "nhan-vien-gia" and ev["truoc"]["xe_id"] == x1 and ev["sau"]["xe_id"] == x2 and ev["truoc"]["tai_xe_id"] == tx2
            and ev["sau"]["tai_xe_id"] == tx1 and ev["truoc"]["ngay"] == str(today) and ev["sau"]["ngay"] == str(day(-1))
            and ev["truoc"]["nguoi_tra_id"] == tx2 and ev["sau"]["nguoi_tra_id"] == tx1, f"Lịch sử đổi phân công: {ev}")
    # Xe không tài xế (công ty trả) được tài xế mới thì tài xế trả (mặc định đợt 1).
    r2 = dx.cmd("doi_phan_cong", {"chang_id": v2["chang_id"], "truoc": {"xe_id": x3, "tai_xe_id": None, "ngay": str(today)}, "xe_id": x3, "tai_xe_id": tx2,
                                  "ngay": str(today)})
    require((r2["tra"], r2["nguoi_tra_id"]) == ("nguoi", tx2), f"công ty trả → tài xế trả: {r2}")
    # Người trả đã chỉnh tay (khác mặc định) giữ nguyên khi đổi tài xế.
    dx.cmd("sua_chang", {"chang_id": v2["chang_id"], "cot": "nguoi_tra", "truoc": str(tx2), "gia_tri": str(ids["DL1"])})
    r3 = dx.cmd("doi_phan_cong", {"chang_id": v2["chang_id"], "truoc": {"xe_id": x3, "tai_xe_id": tx2, "ngay": str(today)}, "xe_id": x3, "tai_xe_id": tx1,
                                  "ngay": str(today)})
    require((r3["tra"], r3["nguoi_tra_id"]) == ("nguoi", ids["DL1"]), f"người trả chỉnh tay giữ nguyên: {r3}")
    # Trùng chặng khi đổi; ngày chạy bằng ngày đóng của mai vẫn đổi được xe.
    dx.reject("doi_phan_cong", {"chang_id": cp2["chang_id"], "truoc": {"xe_id": x3, "tai_xe_id": None, "ngay": str(today)}, "xe_id": x2, "tai_xe_id": None,
                               "ngay": str(today)}, "TRUNG_CHANG")
    fut = dx.cmd("doi_phan_cong", {"chang_id": future["chang_id"], "truoc": {"xe_id": x1, "tai_xe_id": tx1, "ngay": str(tomorrow)}, "xe_id": x2,
                                  "tai_xe_id": tx2, "ngay": str(tomorrow)})
    require(fut["ok"], "chặng ngày chạy = ngày đóng của mai đổi xe được")
    cases.append("đổi phân công: CHANGED khi máy thấy cũ, không đổi gì thì khong_doi, xe ngừng/không rõ, tài xế không có, ngày mai, chuyển vào tháng "
                 "khóa, trùng chặng chặn; người trả theo tài xế mới khi đang ở mặc định, chỉnh tay thì giữ; không đổi số dư; Lịch sử trước → sau")

    # --- Chặn đổi/bỏ khi có phí, đã hoàn; bỏ chặng chưa phí ----------------------------------------------------------------
    for name, extra in (("doi_phan_cong", {"truoc": {"xe_id": x1, "tai_xe_id": tx1, "ngay": str(today)}, "xe_id": x2, "tai_xe_id": tx1, "ngay": str(today)}),
                        ("bo_phan_cong", {})):
        dx.reject(name, {"chang_id": v1["chang_id"], **extra}, "CHANG_CO_PHI")
    dx.reject("bo_phan_cong", {"chang_id": leg_pay}, "CHANG_CO_PHI")      # chặng có trước điều độ cũng được bảo vệ như vậy
    require(count(pg, f"SELECT count(*) FROM doixe.chang WHERE id={v1['chang_id']} AND NOT da_xoa AND NOT da_bo AND xe_id={x1}") == 1, "chặng có phí không đổi")
    h = dx.cmd("phan_xe", {"container": "MAUU3300001", "ngay_dong": str(today), "xe_id": x2})["chang_id"]
    dx.cmd("sua_chang", {"chang_id": h, "cot": "phi:nang", "truoc": None, "gia_tri": "500"})
    lines = [d["id"] for leg_ in dx.so("nguoi", tx2)["chua_hoan"] for d in leg_["dong"] if leg_["id"] == h]
    dx.cmd("ghi_hoan", {"nguoi_id": tx2, "ngay": str(today), "so_tien_vnd": "500", "dong_ids": lines})
    for name, extra in (("doi_phan_cong", {"truoc": {"xe_id": x2, "tai_xe_id": tx2, "ngay": str(today)}, "xe_id": x1, "tai_xe_id": tx1, "ngay": str(today)}),
                        ("bo_phan_cong", {})):
        dx.reject(name, {"chang_id": h, **extra}, "CHANG_DA_HOAN")
    flags = viec(("MAUU3300001", today))["viec"][0]["chang"][0]
    require((flags["co_phi"], flags["da_hoan"], flags["da_gui"]) == (True, True, False), f"cờ khóa: {flags}")
    # Nhận booking: đổi container là đổi phân công (bị chặn khi có phí, đã hoàn); chỉ đổi ngày đóng thì vẫn được vì không đụng tiền.
    dx.reject("nhan_booking", {"chang_id": v1["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(today), "container": "MAUU3000011"}, "CHANG_CO_PHI")
    dx.reject("nhan_booking", {"chang_id": h, "kieu": "cap_nhat", "ngay_dong": str(today), "container": "MAUU3300011"}, "CHANG_DA_HOAN")
    require(dx.cmd("nhan_booking", {"chang_id": v1["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(day(-1))})["ok"]
            and dx.cmd("nhan_booking", {"chang_id": h, "kieu": "cap_nhat", "ngay_dong": str(day(-1)), "kho": "KHO SAU HOAN"})["ok"]
            and pg.value(f"SELECT ngay_dong::text||'|'||container FROM doixe.chang WHERE id={v1['chang_id']}") == f"{day(-1)}|MAUU3000001",
            "chặng có phí/đã hoàn vẫn nhận ngày đóng và chữ, container giữ nguyên")
    require(dx.cmd("nhan_booking", {"chang_id": v1["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(today)})["ok"], "trả ngày đóng về cũ")
    require(dx.cmd("nhan_booking", {"chang_id": v1["chang_id"], "kieu": "giu_ngoai"})["ok"]
            and dx.cmd("nhan_booking", {"chang_id": v1["chang_id"], "kieu": "cap_nhat", "ngay_dong": str(today)})["ok"], "giu_ngoai khi có phí")
    sd_bo = balance(tx1)
    gone_leg = dx.cmd("phan_xe", {"container": "MAUU3400001", "ngay_dong": str(today), "xe_id": x1})["chang_id"]
    out = dx.cmd("bo_phan_cong", {"chang_id": gone_leg})
    require(out["cach"] == "xoa" and chang_ids(viec(("MAUU3400001", today))) == [] and balance(tx1) == sd_bo, f"bỏ chặng chưa phí: {out}")
    dx.reject("bo_phan_cong", {"chang_id": gone_leg}, "CHANG_NOT_FOUND")
    dx.reject("doi_phan_cong", {"chang_id": gone_leg, "truoc": {"xe_id": x1, "tai_xe_id": tx1, "ngay": str(today)}, "xe_id": x2, "tai_xe_id": tx2,
                               "ngay": str(today)}, "CHANG_NOT_FOUND")
    again_leg = dx.cmd("phan_xe", {"container": "MAUU3400001", "ngay_dong": str(today), "xe_id": x2})
    require(again_leg["ok"] and again_leg["chang_id"] != gone_leg, "bỏ phân công rồi phân xe lại được (chặng đã ẩn không tính)")
    ev = events("bo_phan_cong")[0]
    require(ev["actor"] == "nhan-vien-gia" and ev["truoc"]["chang_id"] == gone_leg and ev["truoc"]["ngay_dong"] == str(today) and ev["truoc"]["xe_id"] == x1
            and ev["sau"]["cach"] == "xoa", f"Lịch sử bỏ phân công: {ev}")
    # Tháng khóa: bỏ thành gạch ngang (da_bo), không còn tính vào việc; mở/khóa lại tháng 1/2026.
    dx.cmd("khoa_thang", {"thang": "2026-01-01", "khoa": True})
    dx.reject("nhan_booking", {"chang_id": v_jan["chang_id"], "kieu": "cap_nhat", "ngay_dong": "2026-01-05", "container": "MAUU1234568"}, "THANG_KHOA")
    require(dx.cmd("nhan_booking", {"chang_id": v_jan["chang_id"], "kieu": "cap_nhat", "ngay_dong": "2026-01-06"})["ok"]
            and dx.cmd("nhan_booking", {"chang_id": v_jan["chang_id"], "kieu": "cap_nhat", "ngay_dong": "2026-01-05"})["ok"],
            "chặng tháng khóa vẫn nhận ngày đóng, chỉ đổi container bị chặn")
    jan_out = dx.cmd("bo_phan_cong", {"chang_id": v_jan["chang_id"]})
    require(jan_out["cach"] == "bo" and pg.value(f"SELECT da_bo AND NOT da_xoa FROM doixe.chang WHERE id={v_jan['chang_id']}") == "t"
            and chang_ids(viec(("MAUU1234567", dt.date(2026, 1, 5)))) == [], f"tháng khóa: bỏ thành gạch ngang: {jan_out}")
    dx.reject("phan_xe", {"container": "MAUU1234567", "ngay_dong": "2026-01-05", "xe_id": x1}, "THANG_KHOA")
    cases.append("đổi/bỏ bị chặn khi chặng đã có phí (CHANG_CO_PHI) hoặc đã hoàn (CHANG_DA_HOAN), không đổi gì ở chặng; cờ co_phi/da_hoan đúng; "
                 "bỏ chặng chưa phí: ẩn, phân xe lại được, Lịch sử trước → sau; tháng khóa: bỏ thành gạch ngang (da_bo); nhận booking đổi container "
                 "bị chặn như đổi phân công (có phí, đã hoàn, tháng khóa) còn đổi ngày đóng/giu_ngoai vẫn được")

    # --- xoa_chang sau khi chuyển thân sang hàm chung: hành vi đợt 1 giữ nguyên ----------------------------------------------
    sd_x = int(balance(tx1))
    leg_x = dx.cmd("luu_chang", {"rows": [row(today, "MAUU8000001", phi={"nangha": "90"})]})["chang_ids"][0]
    require(int(balance(tx1)) == sd_x + 90 and dx.cmd("xoa_chang", {"chang_id": leg_x})["cach"] == "xoa" and int(balance(tx1)) == sd_x,
            "xóa chặng tháng mở: ẩn, số dư về lại")
    leg_j = dx.cmd("luu_chang", {"rows": [row("2026-01-09", "MAUU8000002", phi={"nangha": "70", "neo": "30"})]})["chang_ids"][0]
    sd_j = int(balance(tx1))
    require(dx.cmd("xoa_chang", {"chang_id": leg_j})["cach"] == "bo" and int(balance(tx1)) == sd_j - 100, "xóa chặng tháng khóa: gạch ngang, dòng trừ lại")
    jan_book = dx.so("nguoi", tx1, "2026-01-01")["chang"]
    jleg = next(c for c in jan_book if c["id"] == leg_j)
    require(jleg["da_bo"] and jleg["dong"][-1]["loai"] == "tru_lai" and jleg["dong"][-1]["phi"] == {"nangha": "-70", "neo": "-30"}, f"dòng trừ lại: {jleg}")
    dx.reject("xoa_chang", {"chang_id": leg_j}, "CHANG_DA_BO")
    require(events("xoa_chang")[0]["viec"] == "xoa_chang" and any(e["viec"] == "bo_chang" for e in dx.read("doixe.get_lich_su(NULL,NULL)")["events"]),
            "Lịch sử xoa_chang giữ tên việc cũ")
    cases.append("xoa_chang (thân chuyển sang hàm chung): tháng mở ẩn chặng và số dư về lại, tháng khóa gạch ngang với dòng trừ lại đúng từng phí, "
                 "Lịch sử giữ tên việc xoa_chang/bo_chang")

    # --- Đã lên bảng kê đã gửi: chỉ sang Bảng kê ----------------------------------------------------------------------------
    sent_leg = dx.cmd("phan_xe", {"container": "MAUU9100001", "ngay_dong": str(today), "xe_id": x1})["chang_id"]
    cur = dx.read(f"doixe.get_bang_ke('hth', {lit(m0)}::date)")
    dx.cmd("gui_bang_ke", {"thang": str(m0), "doi_vnd": cur["tong"]["doi_vnd"], "so_chang": cur["tong"]["so_chang"], "dau": cur["dau"]})
    flags = viec(("MAUU9100001", today))["viec"][0]["chang"][0]
    require(flags["da_gui"] is True and flags["id"] == sent_leg and count(pg, f"SELECT count(*) FROM doixe.bang_ke_dong WHERE chang_id={sent_leg}") == 1,
            f"chặng đã lên bảng kê: {flags}")
    dx.reject("doi_phan_cong", {"chang_id": sent_leg, "truoc": {"xe_id": x1, "tai_xe_id": tx1, "ngay": str(today)}, "xe_id": x2, "tai_xe_id": tx2,
                               "ngay": str(today)}, "CHANG_DA_GUI")
    dx.reject("bo_phan_cong", {"chang_id": sent_leg}, "CHANG_DA_GUI")
    dx.reject("nhan_booking", {"chang_id": sent_leg, "kieu": "cap_nhat", "ngay_dong": str(today), "container": "MAUU9100002"}, "CHANG_DA_GUI")
    # Booking đổi không đổi bảng kê đã gửi: nhận ngày đóng và chữ vẫn được, dòng đã gửi giữ nguyên.
    sent_before = pg.value(f"SELECT row_to_json(d)::text FROM doixe.bang_ke_dong d WHERE chang_id={sent_leg}")
    dx.cmd("nhan_booking", {"chang_id": sent_leg, "kieu": "cap_nhat", "ngay_dong": str(day(-1)), "kho": "KHO SAU KHI GUI"})
    require(pg.value(f"SELECT row_to_json(d)::text FROM doixe.bang_ke_dong d WHERE chang_id={sent_leg}") == sent_before
            and pg.value(f"SELECT kho FROM doixe.chang WHERE id={sent_leg}") == "KHO SAU KHI GUI", "bảng kê đã gửi không đổi khi booking đổi")
    require(count(pg, f"SELECT count(*) FROM doixe.bang_ke_dong WHERE chang_id={v_thue['chang_id']}") == 0,
            "chặng phân cho xe thuê ngoài không lên bảng kê HTH")
    # Phân xe sau khi gửi vẫn được (chặng vào bảng kê đang gom kế tiếp).
    require(dx.cmd("phan_xe", {"container": "MAUU9100003", "ngay_dong": str(today), "xe_id": x1})["ok"], "phân xe sau khi gửi bảng kê tháng")
    cases.append("chặng đã lên bảng kê đã gửi: đổi/bỏ/đổi container bị chặn CHANG_DA_GUI; cờ da_gui đúng; nhận booking vẫn cập nhật chặng nhưng dòng "
                 "bảng kê đã gửi giữ nguyên; phân xe sau khi gửi vẫn được")

    require(pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'")) == stamp, "điều độ đã làm đổi dữ liệu sokhach")
    require(book > 0, "sổ khách giả")
    cases.append("dấu dữ liệu sokhach không đổi sau mọi lệnh điều độ")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "specs/doi-xe-dieu-do-01.md", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
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
