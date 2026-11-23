#!/usr/bin/env python3
"""Đội xe DX-05 (DOI-XE-SAU-KHOA-01): ứng, đợt hoàn và hủy vào tháng đã khóa vẫn ghi, gắn cờ sau khóa, trên PostgreSQL 18.6 dùng một lần.

Dựng DB như harness V7, chạy bảy migration đội xe cũ, ghi một lần ứng bằng hàm cũ, rồi `2026-11-24-v7-doi-xe-sau-khoa.sql` (lỗi
giữa chừng thì quay lại; chạy lại được; chỉ thêm bốn cột, các hàm ngoài danh sách thay và quyền giữ nguyên; số dư không đổi; khoản
cũ giữ cờ false). Gọi thật các hàm `doixe.*` như API: ứng và đợt hoàn ngày ở tháng đã khóa được ghi, gắn `sau_khoa`, số dư tính
như thường; ngày ở tháng mở thì không gắn; hủy ở tháng đã khóa vẫn đòi lý do, gắn `sau_khoa` trên phần hủy; khóa/mở tháng đổi cờ
của lệnh sau, không đổi cờ đã ghi; `get_so` và Lịch sử có cờ; gửi lại cùng mã trả đúng kết quả cũ. Dữ liệu giả. Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_doixe_sau_khoa.py [--report <file>.json]
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
from test_pg_doixe_audit import MIGRATION_6, months_back
from test_pg_doixe_chang import MIGRATION_5, PUBLIC_4
from test_pg_doixe_dieu_do import MIGRATION_4, PUBLIC_3
from test_pg_doixe_thu import MIGRATION_2, MIGRATION_3, PUBLIC_2

MIGRATION_7 = Path(__file__).resolve().parent / "migrations" / "2026-11-24-v7-doi-xe-sau-khoa.sql"
CHANGED_FUNCS = ("ghi_ung", "huy_ung", "ghi_hoan", "huy_hoan", "get_so")
NEW_COLS = {"dot_hoan.huy_sau_khoa", "dot_hoan.sau_khoa", "ung.huy_sau_khoa", "ung.sau_khoa"}


def scenario(pg: Pg, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    today = dt.date.fromisoformat(pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    m0, m1 = today.replace(day=1), months_back(today, 1)
    require(m1 != dt.date(2026, 1, 1), "harness dùng tháng 1/2026 làm tháng cũ đã khóa")
    d1 = lambda n: m1 + dt.timedelta(days=n)  # noqa: E731
    new_book(pg, ("2026-01-01", 1000))
    for path in (MIGRATION_1, PHIEU_CHI, MIGRATION_2, MIGRATION_3, MIGRATION_4, MIGRATION_5, MIGRATION_6):   # đúng thứ tự trên hao
        pg.sql(path.read_text(encoding="utf-8"))

    dx = Dx(pg)
    pg.value(actor_sql("SELECT doixe.nap_danh_muc(" + lit(json.dumps({
        "nguoi": [{"ma": "TX1", "ten": "Tài xế giả 1", "vai": "tai_xe", "so_du_dau_vnd": "0"},
                  {"ma": "TX2", "ten": "Tài xế giả 2", "vai": "tai_xe", "so_du_dau_vnd": "500000"}],
        "xe": [{"bien_so": "99Z-000.01", "nhom": "NHOM GIA", "tai_xe_ma": "TX1"},
               {"bien_so": "99Z-000.02", "nhom": "NHOM GIA", "tai_xe_ma": "TX2"}]}, ensure_ascii=False)) + "::jsonb)", "nap-gia"))
    ids = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT ma_nguon||'|'||id FROM doixe.nguoi").splitlines())}
    xe = {r[0]: int(r[1]) for r in (x.split("|") for x in pg.value("SELECT bien_so||'|'||id FROM doixe.xe").splitlines())}
    tx1, tx2, x1 = ids["TX1"], ids["TX2"], xe["99Z-000.01"]

    def row(day, cont, phi) -> dict:
        return {"ngay": str(day), "container": cont, "loai": "hang", "xe_id": x1, "tai_xe_id": tx1, "tra": "nguoi",
                "nguoi_tra_id": tx1, "ten_hang": "Hàng giả", "tinh": "Tỉnh giả", "phi": phi}

    saved = dx.cmd("luu_chang", {"rows": [row(d1(2), "MAUU5000001", {"nang": "400000"}), row(d1(3), "MAUU5000002", {"nang": "250000"}),
                                          row(today, "MAUU5000003", {"nang": "300000"})]})
    require(saved["ok"] and saved["sau_khoa"] == 2, f"chặng tháng trước (đã khóa) gắn sau khóa như cũ: {saved}")
    cu = dx.cmd("ghi_ung", {"nguoi_id": tx2, "ngay": str(d1(5)), "so_tien_vnd": "100000"})   # hàm cũ, tháng đã khóa
    require(cu["ok"] and "sau_khoa" not in cu, f"bản cũ không có cờ: {cu}")

    # --- Migration -------------------------------------------------------------------------------------------------------
    source = MIGRATION_7.read_text(encoding="utf-8")
    cols_sql = ("SELECT string_agg(c.relname||'.'||a.attname||':'||a.atttypid::text, ',' ORDER BY c.relname, a.attnum) FROM pg_class c "
                "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped "
                "WHERE c.relnamespace = 'doixe'::regnamespace AND c.relkind IN ('r', 'i')")
    names = ",".join(lit(n) for n in CHANGED_FUNCS)
    other_funcs = ("SELECT count(*) || ':' || md5(string_agg(p.oid::regprocedure::text || md5(pg_get_functiondef(p.oid)), ',' "
                   f"ORDER BY p.oid::regprocedure::text)) FROM pg_proc p WHERE p.pronamespace = 'doixe'::regnamespace AND p.proname NOT IN ({names})")
    acl = ("SELECT md5(string_agg(p.oid::regprocedure::text || coalesce(p.proacl::text, ''), ',' ORDER BY p.oid::regprocedure::text)) "
           "FROM pg_proc p WHERE p.pronamespace = 'doixe'::regnamespace")
    money = ("SELECT string_agg(n.id || '=' || doixe._so_du(n.id), ',' ORDER BY n.id) || '|' || "
             "(SELECT count(*) FROM doixe.ung) || '|' || (SELECT count(*) FROM doixe.dot_hoan) || '|' || (SELECT count(*) FROM doixe.su_kien) "
             "FROM doixe.nguoi n")
    new_cols = ("SELECT count(*) FROM pg_attribute WHERE attrelid IN ('doixe.ung'::regclass, 'doixe.dot_hoan'::regclass) "
                "AND attname IN ('sau_khoa', 'huy_sau_khoa') AND NOT attisdropped")
    cols0 = pg.value(cols_sql)
    before = (pg.value(other_funcs), pg.value(acl), pg.value(money))
    ghi_ung_def = pg.value("SELECT md5(pg_get_functiondef('doixe.ghi_ung(jsonb)'::regprocedure))")
    pg.rejects(source.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'SAU_KHOA_FAULT'; END $$; COMMIT;"), message="SAU_KHOA_FAULT")
    require(count(pg, new_cols) == 0 and pg.value("SELECT md5(pg_get_functiondef('doixe.ghi_ung(jsonb)'::regprocedure))") == ghi_ung_def,
            "migration lỗi không quay lại")
    pg.sql(source)
    pg.sql(source)
    cols1 = pg.value(cols_sql)
    added = set(cols1.split(",")) - set(cols0.split(","))
    require(set(cols0.split(",")) <= set(cols1.split(",")) and {c.rsplit(":", 1)[0] for c in added} == NEW_COLS,
            f"migration chỉ thêm bốn cột: {sorted(added)}")
    require((pg.value(other_funcs), pg.value(acl), pg.value(money)) == before,
            "hàm ngoài danh sách thay, quyền, số dư mọi người, số khoản và Lịch sử giữ nguyên")
    require(count(pg, "SELECT count(*) FROM doixe.ung WHERE sau_khoa OR huy_sau_khoa") == 0, "khoản cũ giữ cờ false, không đoán")
    cases.append("migration lỗi thì quay lại, chạy lại được hai lượt; chỉ thêm bốn cột cờ; hàm khác, quyền, số dư, số khoản, Lịch sử "
                 "giữ nguyên; khoản ghi trước migration giữ cờ false")

    granted = json.loads(pg.value("SELECT coalesce(json_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' "
                                  "ORDER BY 1),'[]') FROM pg_proc p WHERE p.pronamespace='doixe'::regnamespace "
                                  "AND has_function_privilege('v7_app',p.oid,'EXECUTE')"))
    require(sorted(granted) == sorted(PUBLIC_1 + PUBLIC_2 + PUBLIC_3 + PUBLIC_4), f"quyền gọi hàm của app sai: {granted}")
    require(pg.value("SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
                     "WHERE p.pronamespace='doixe'::regnamespace AND a.grantee=0 AND a.privilege_type='EXECUTE'") == "0", "PUBLIC gọi được hàm doixe")
    cases.append("quyền: app gọi đúng các hàm như trước; PUBLIC không gọi được")

    # --- Ứng ----------------------------------------------------------------------------------------------------------
    so_du = lambda n: int(dx.so("nguoi", n)["so_du_vnd"])  # noqa: E731
    sd = so_du(tx1)
    mo = dx.cmd("ghi_ung", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "200000", "so_du_vnd": str(sd)})
    require(mo["ok"] and mo["sau_khoa"] is False and int(mo["so_du_sau_vnd"]) == sd - 200000, f"ứng tháng mở không gắn cờ: {mo}")
    body = {"nguoi_id": tx1, "ngay": str(d1(6)), "so_tien_vnd": "150000", "so_du_vnd": str(sd - 200000)}
    khoa = dx.cmd("ghi_ung", body, key="ung-khoa")
    require(khoa["ok"] and khoa["sau_khoa"] is True and int(khoa["so_du_sau_vnd"]) == sd - 350000,
            f"ứng tháng đã khóa vẫn ghi, gắn cờ, số dư trừ như thường: {khoa}")
    require(dx.cmd("ghi_ung", body, key="ung-khoa") == {**khoa, "lap_lai": True}, "gửi lại cùng mã trả đúng kết quả cũ")
    require(count(pg, f"SELECT count(*) FROM doixe.ung WHERE nguoi_id = {tx1}") == 2, "gửi lại không ghi thêm")
    so_m1 = dx.so("nguoi", tx1, str(m1))
    flags = {u["id"]: u["sau_khoa"] for u in so_m1["ung"]}
    require(flags == {khoa["ung_id"]: True} and int(so_m1["the"]["ung_vnd"]) == 150000, f"get_so tháng trước: {so_m1['ung']}")
    require(dx.so("nguoi", tx2, str(m1))["ung"][0]["sau_khoa"] is False, "khoản ghi trước migration hiện cờ false")
    cases.append("ứng ngày ở tháng đã khóa: ghi được, sau_khoa = true trên khoản và kết quả, số dư và thẻ tháng trừ như thường; "
                 "tháng mở không gắn; gửi lại cùng mã không ghi thêm")

    dx.reject("huy_ung", {"ung_id": khoa["ung_id"], "ly_do": " "}, "LY_DO_THIEU")
    huy = dx.cmd("huy_ung", {"ung_id": khoa["ung_id"], "ly_do": "ghi nhầm ngày"})
    require(huy["ok"] and huy["sau_khoa"] is True and int(huy["so_du_sau_vnd"]) == sd - 200000, f"hủy ở tháng đã khóa: {huy}")
    item = dx.so("nguoi", tx1, str(m1))["ung"][0]
    require(item["sau_khoa"] is True and item["huy"]["sau_khoa"] is True and item["huy"]["ly_do"] == "ghi nhầm ngày", f"hủy hiện cờ: {item}")
    huy_mo = dx.cmd("huy_ung", {"ung_id": mo["ung_id"], "ly_do": "trùng"})
    require(huy_mo["sau_khoa"] is False and dx.so("nguoi", tx1)["ung"][0]["huy"]["sau_khoa"] is False, f"hủy ở tháng mở: {huy_mo}")
    cases.append("hủy lần ứng ở tháng đã khóa: vẫn bắt buộc lý do, hủy được, huy.sau_khoa = true; tháng mở thì false")

    # --- Đợt hoàn ------------------------------------------------------------------------------------------------------
    so = dx.so("nguoi", tx1)
    dongs = [d for c in so["chua_hoan"] for d in c["dong"] if d["dot_hoan_id"] is None and c["ngay"] < str(m0)]
    tong = sum(int(v) for d in dongs for k, v in d["phi"].items() if k != "vetc")
    require(len(dongs) == 2 and tong == 650000, f"dòng chưa hoàn tháng trước: {dongs}")
    hoan = dx.cmd("ghi_hoan", {"nguoi_id": tx1, "ngay": str(d1(20)), "so_tien_vnd": str(tong), "dong_ids": [d["id"] for d in dongs],
                               "tong_dong_vnd": str(tong), "so_du_vnd": so["so_du_vnd"]})
    require(hoan["ok"] and hoan["sau_khoa"] is True and int(hoan["so_du_sau_vnd"]) == int(so["so_du_vnd"]) - tong,
            f"đợt hoàn tháng đã khóa: {hoan}")
    dot = dx.so("nguoi", tx1, str(m1))["dot"]
    require([(x["id"], x["sau_khoa"], x["huy"]) for x in dot] == [(hoan["dot_id"], True, None)], f"get_so đợt hoàn: {dot}")
    huy_h = dx.cmd("huy_hoan", {"dot_id": hoan["dot_id"], "ly_do": "chuyển nhầm"})
    require(huy_h["ok"] and huy_h["sau_khoa"] is True and huy_h["dong_tro_lai"] == 2, f"hủy đợt hoàn tháng khóa: {huy_h}")
    require(dx.so("nguoi", tx1, str(m1))["dot"][0]["huy"]["sau_khoa"] is True, "hủy đợt hoàn hiện cờ")
    hoan2 = dx.cmd("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "0", "dong_ids": [d["id"] for d in dongs]})
    require(hoan2["ok"] and hoan2["sau_khoa"] is False, f"đợt hoàn tháng mở (dòng tháng khóa) không gắn cờ: {hoan2}")
    cases.append("đợt hoàn ngày ở tháng đã khóa: ghi được, sau_khoa = true; hủy vẫn đòi lý do, huy.sau_khoa = true, dòng trở lại; "
                 "đợt hoàn ngày ở tháng mở thì không gắn (cờ theo ngày của khoản, không theo dòng)")

    # --- Khóa / mở tháng đổi cờ của lệnh sau, không đổi cờ đã ghi ------------------------------------------------------------
    require(dx.cmd("khoa_thang", {"thang": str(m0), "khoa": True})["khoa"] is True, "khóa tháng này")
    nay = dx.cmd("ghi_ung", {"nguoi_id": tx2, "ngay": str(today), "so_tien_vnd": "10000"})
    require(nay["sau_khoa"] is True, f"tháng này vừa khóa thì gắn cờ: {nay}")
    require(dx.cmd("khoa_thang", {"thang": str(m0), "khoa": False})["khoa"] is False, "mở lại tháng này")
    require(dx.cmd("khoa_thang", {"thang": str(m1), "khoa": False})["khoa"] is False, "mở tháng trước")
    mo1 = dx.cmd("ghi_ung", {"nguoi_id": tx2, "ngay": str(d1(7)), "so_tien_vnd": "10000"})
    huy_nay = dx.cmd("huy_ung", {"ung_id": nay["ung_id"], "ly_do": "thử"})
    require(mo1["sau_khoa"] is False and huy_nay["sau_khoa"] is False, f"tháng đã mở thì không gắn: {mo1} {huy_nay}")
    require(pg.value(f"SELECT sau_khoa::text || huy_sau_khoa::text FROM doixe.ung WHERE id = {nay['ung_id']}") == "truefalse",
            "mở tháng không đổi cờ đã ghi")
    cases.append("khóa tháng hiện tại thì ứng hôm nay gắn cờ; mở tháng thì lệnh sau không gắn; cờ đã ghi giữ nguyên")

    # --- Lịch sử ---------------------------------------------------------------------------------------------------------
    events = dx.read(f"doixe.get_lich_su({tx1}, NULL)")["events"]
    seen = {(e["viec"], (e["sau"] or {}).get("sau_khoa")) for e in events if e["viec"] in ("ghi_ung", "huy_ung", "ghi_hoan", "huy_hoan")}
    require(seen == {("ghi_ung", False), ("ghi_ung", True), ("huy_ung", True), ("huy_ung", False), ("ghi_hoan", True),
                     ("huy_hoan", True), ("ghi_hoan", False)}, f"Lịch sử có cờ: {seen}")
    cases.append("Lịch sử: ghi/hủy ứng, ghi/hủy đợt hoàn có sau.sau_khoa đúng từng lệnh")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "DOI-XE-SAU-KHOA-01 (DX-05)", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
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
