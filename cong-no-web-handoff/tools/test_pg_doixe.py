#!/usr/bin/env python3
"""Schema `doixe` (đội xe đợt 1, CHI-PHI-XE-01, specs/chi-phi-xe-01.md) trên PostgreSQL 18.6 dùng một lần.

Dựng DB như harness V7 (`pg_v7_harness.disposable_database`), chạy migration đội xe hai lượt, nạp danh mục giả rồi gọi thật
từng hàm `doixe.*` như API gọi: lưu chặng (lỗi theo dòng, trùng, ngày tương lai, nối chuyến khách), sửa ô (ghi đè, dòng điều
chỉnh ở tháng khóa và dòng đã hoàn, đổi người trả), xóa/bỏ chặng, ghi/hủy ứng, ghi/hủy đợt hoàn, khóa tháng, Lịch sử, quyền
của `v7_app`, mã yêu cầu chống ghi trùng (cả hai lệnh song song) và bất biến: số dư = số dư đầu + tài xế chi − đã hoàn − đã ứng,
schema `sokhach` không đổi. Dữ liệu giả. Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_doixe.py [--report <file>.json]
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
    call,
    disposable_database,
    lit,
    new_book,
    require,
    version,
)

MIGRATION = Path(__file__).resolve().parent / "migrations" / "2026-11-18-v7-doi-xe.sql"
PHIEU_CHI = Path(__file__).resolve().parent / "migrations" / "2026-11-18-v7-doi-xe-phieu-chi.sql"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from v7_api_validate import ApiError  # noqa: E402
from v7_psql import Psql  # noqa: E402

PUBLIC_FUNCTIONS = sorted([
    "get_lich_su(bigint,bigint)", "get_so(text,bigint,date)", "get_tong(date)", "ghi_hoan(jsonb)", "ghi_ung(jsonb)",
    "huy_hoan(jsonb)", "huy_ung(jsonb)", "khoa_thang(jsonb)", "luu_chang(jsonb)", "sua_chang(jsonb)", "xoa_chang(jsonb)",
])


class Dx:
    """Gọi hàm doixe.* với payload jsonb và mã yêu cầu mới mỗi lệnh (trừ khi truyền key)."""

    def __init__(self, pg: Pg):
        self.pg, self.serial = pg, 0

    def key(self) -> str:
        self.serial += 1
        return f"dx-{self.serial}"

    def sql(self, name: str, payload: dict) -> str:
        return actor_sql(f"SELECT doixe.{name}({lit(json.dumps(payload, ensure_ascii=False))}::jsonb)", "nhan-vien-gia")

    def cmd(self, name: str, payload: dict, *, key: str | None = None) -> dict:
        return json.loads(self.pg.value(self.sql(name, {"idempotency_key": key or self.key(), **payload})))

    def reject(self, name: str, payload: dict, error: str) -> None:
        self.pg.rejects(self.sql(name, {"idempotency_key": self.key(), **payload}), message=error)

    def read(self, sql: str) -> dict:
        return json.loads(self.pg.value(actor_sql("SELECT " + sql, "nhan-vien-gia")))

    def so(self, kind: str, ident: int, month: str | None = None) -> dict:
        return self.read(f"doixe.get_so({lit(kind)},{ident},{'NULL' if month is None else lit(month)}::date)")


def money(rows: list[dict], fee: str | None = None, *, company: tuple[str, ...] = ("vetc",)) -> int:
    """Tổng tiền các dòng của một danh sách chặng (bỏ phí công ty trả), tính độc lập với SQL."""
    total = 0
    for leg in rows:
        for line in leg["dong"]:
            for code, value in line["phi"].items():
                if (fee is None and code not in company) or code == fee:
                    total += int(value)
    return total


def count(pg: Pg, sql: str) -> int:
    return int(pg.value(sql))


def scenario(pg: Pg, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    today = dt.date.fromisoformat(pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    month = today.replace(day=1)
    require(month != dt.date(2026, 1, 1), "harness dùng tháng 1/2026 làm tháng cũ đã khóa")
    tomorrow = today + dt.timedelta(days=1)

    # Chuyến khách giả để nối chặng hàng: một sổ khách, một chuyến ngày 5/1/2026.
    book = new_book(pg, ("2026-01-01", 1000))
    call(pg, "set_month_lock", book, version(pg, book), "kh-1", "2026-01-01", "false")
    trips = json.dumps([{"container": "MAUU1234567", "carrier": "FAKE", "date": "05/01/2026", "from": "KHO GIA A", "to": "CANG GIA B",
                         "unitPriceVnd": "100", "otherFeeVnd": None, "note": "", "src": "FAKE"}])
    call(pg, "paste_trips", book, version(pg, book), "kh-2", "2026-01-01", trips)
    stamp = pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'"))

    source = MIGRATION.read_text(encoding="utf-8")
    pg.rejects(source.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'DOIXE_FAULT'; END $$; COMMIT;"), message="DOIXE_FAULT")
    require(pg.value("SELECT to_regnamespace('doixe') IS NULL") == "t", "migration lỗi không quay lại")
    pg.sql(source)
    pg.sql(source)
    require(count(pg, "SELECT count(*) FROM doixe.loai_phi") == 15, "danh mục phí phải đủ 15 loại")
    phieu = PHIEU_CHI.read_text(encoding="utf-8")
    pg.rejects(phieu.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'PHIEU_FAULT'; END $$; COMMIT;"), message="PHIEU_FAULT")
    require(count(pg, "SELECT count(*) FROM doixe.loai_phi") == 15, "migration phiếu chi lỗi không quay lại")
    pg.sql(phieu)
    pg.sql(phieu)
    require(count(pg, "SELECT count(*) FROM doixe.loai_phi") == 16
            and pg.value("SELECT cot_sheet IS NULL AND NOT cong_ty_tra FROM doixe.loai_phi WHERE ma='hasom'") == "t",
            "phiếu chi: thêm Hạ sớm/KH, tài xế chi, không cột Sheet")
    cases.append("migration lỗi thì quay lại, chạy lại được, đủ 15 loại phí; phiếu chi mới thêm Hạ sớm/KH (16 loại), chạy lại được")

    # Quyền: app gọi đúng 11 hàm, không gọi hàm phụ hay hàm nạp; không quyền trên bảng; PUBLIC không gọi được gì.
    granted = json.loads(pg.value("SELECT coalesce(json_agg(p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' "
                                  "ORDER BY 1),'[]') FROM pg_proc p WHERE p.pronamespace='doixe'::regnamespace "
                                  "AND has_function_privilege('v7_app',p.oid,'EXECUTE')"))
    require(sorted(granted) == PUBLIC_FUNCTIONS, f"quyền gọi hàm của app sai: {granted}")
    require(pg.value("SELECT count(*) FROM pg_proc p CROSS JOIN LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
                     "WHERE p.pronamespace='doixe'::regnamespace AND a.grantee=0 AND a.privilege_type='EXECUTE'") == "0",
            "PUBLIC gọi được hàm doixe")
    require(pg.value("SELECT count(*) FROM pg_class c WHERE c.relnamespace='doixe'::regnamespace AND c.relkind IN ('r','S') "
                     "AND (has_table_privilege('v7_app',c.oid,'SELECT,INSERT,UPDATE,DELETE') )") == "0", "app có quyền trên bảng doixe")
    pg.rejects(actor_sql("SELECT doixe.nap_danh_muc('{}')"), user="v7_app", message="permission denied")
    pg.rejects("SELECT * FROM doixe.ung", user="v7_app", message="permission denied")
    pg.rejects("SELECT doixe.get_tong(NULL)", user="v7_app", message="ACTOR_REQUIRED")
    cases.append("quyền: app gọi đúng 11 hàm, không hàm phụ/nạp, không bảng; PUBLIC không gọi được; thiếu người làm thì chặn")

    # Danh mục giả.
    pg.value(actor_sql("SELECT doixe.nap_danh_muc(" + lit(json.dumps({
        "nguoi": [{"ma": "TX1", "ten": "Tài xế giả 1", "vai": "tai_xe", "so_du_dau_vnd": "0"},
                  {"ma": "TX2", "ten": "Tài xế giả 2", "vai": "tai_xe", "so_du_dau_vnd": "1000"},
                  {"ma": "DL1", "ten": "Người đi lệnh giả", "vai": "di_lenh", "so_du_dau_vnd": "-3000"}],
        "xe": [{"bien_so": "99Z-000.01", "nhom": "NHOM GIA", "tai_xe_ma": "TX1"},
               {"bien_so": "99Z-000.02", "nhom": "NHOM GIA", "tai_xe_ma": "TX2"},
               {"bien_so": "99Z-000.03", "nhom": "NHOM GIA"},
               {"bien_so": "99Y-000.01", "nhom": "THUE GIA", "thue_ngoai": True}]}, ensure_ascii=False)) + "::jsonb)", "nap-gia"))
    ids = {row[0]: int(row[1]) for row in (line.split("|") for line in pg.value("SELECT ma_nguon||'|'||id FROM doixe.nguoi").splitlines())}
    xe = {row[0]: int(row[1]) for row in (line.split("|") for line in pg.value("SELECT bien_so||'|'||id FROM doixe.xe").splitlines())}
    tx1, tx2, dl1 = ids["TX1"], ids["TX2"], ids["DL1"]
    x1, x2, x3, xt = xe["99Z-000.01"], xe["99Z-000.02"], xe["99Z-000.03"], xe["99Y-000.01"]
    dx = Dx(pg)

    def row(ngay, cont, *, loai="hang", xe_id=x1, tai_xe=tx1, payer: int | None = tx1, phi=None, **extra) -> dict:
        return {"ngay": str(ngay) if ngay else None, "container": cont, "loai": loai, "xe_id": xe_id, "tai_xe_id": tai_xe,
                "tra": "nguoi" if payer else "cong_ty", "nguoi_tra_id": payer, "phi": phi or {}, **extra}

    # Lưu chặng: lỗi theo dòng thì không ghi gì.
    before = count(pg, "SELECT count(*) FROM doixe.chang")
    bad = dx.cmd("luu_chang", {"rows": [
        row(tomorrow, "MAUU0000001", phi={"nangha": "300"}),
        row(None, "MAUU0000002", phi={"nangha": "300"}),
        row(today, "", phi={"nangha": "300"}),
        row(today, "MAUU0000003", xe_id=None),
        row(today, "MAUU0000004"), row(today, "mauu 0000004")]})
    require(bad["ok"] is False and count(pg, "SELECT count(*) FROM doixe.chang") == before, f"lỗi dòng vẫn ghi: {bad}")
    require([(e["i"], e["cot"], e["ma"]) for e in bad["loi"]] == [
        (0, "ngay", "NGAY_TUONG_LAI"), (1, "ngay", "NGAY_THIEU"), (2, "container", "CONT_THIEU"), (3, "xe_id", "XE_KHONG_RO"),
        (5, "container", "TRUNG_CHANG")], f"lỗi theo dòng sai: {bad['loi']}")
    for value in ("300.5", "-300", "3,000", "1e3"):
        dx.reject("luu_chang", {"rows": [row(today, "MAUU0000009", phi={"ps": value})]}, "INVALID_VND")
    dx.reject("luu_chang", {"rows": [row(today, "MAUU0000009", phi={"khong_co": "1"})]}, "INVALID_COMMAND")
    cases.append("lưu chặng: ngày sau hôm nay, thiếu ngày/container, xe không rõ, trùng trong lệnh báo theo dòng, không ghi gì; tiền lẻ/âm chặn")

    # Lưu thật: chặng hàng tháng 1/2026 (khóa) nối chuyến khách, chặng phụ, chặng tháng này có VETC + nổ máy.
    jan = dt.date(2026, 1, 8)
    saved = dx.cmd("luu_chang", {"rows": [
        row(jan, "MAUU1234567", phi={"nang": "450", "nangha": "350"}),
        row(jan, "MAUU1234567", loai="tra_rong", phi={"nangha": "250"}, noi_lay="CANG GIA B", noi_ha="BAI GIA"),
        row(jan + dt.timedelta(days=12), "MAUU1234567", loai="hang", xe_id=x2, tai_xe=tx2, payer=tx2, phi={"nangha": "100"}),
        row(today, "MAUU7654321", phi={"nangha": "300", "vetc": "120", "may": "50", "ps": "0"}, ghi_chu="vá vỏ"),
        row(today, "MAUU7654322", phi={}),
        row(today, "MAUU7654323", xe_id=x2, tai_xe=tx2, payer=dl1, phi={"nang": "500"}),
        row(today, "MAUU7654324", xe_id=xt, tai_xe=None, payer=None, phi={"nang": "700", "vetc": "90"})]})
    require(saved["ok"] and saved["so_dong"] == 7 and saved["sau_khoa"] == 3, f"lưu chặng: {saved}")
    legs = dx.so("nguoi", tx1, "2026-01-01")["chang"]
    hang = next(leg for leg in legs if leg["loai"] == "hang")
    require(hang["chuyen"] == {"khach": "FAKE CONTRACT", "ngay": "2026-01-05", "tu": "KHO GIA A", "den": "CANG GIA B"}
            and hang["noi_lay"] == "KHO GIA A" and hang["noi_ha"] == "CANG GIA B" and hang["sau_khoa"], f"nối chuyến khách: {hang}")
    require(next(leg for leg in legs if leg["loai"] == "tra_rong")["chuyen"] is None, "chặng phụ không nối chuyến khách")
    far = dx.so("nguoi", tx2, "2026-01-01")["chang"][0]
    require(far["chuyen"] is None and far["noi_lay"] is None, f"lệch 15 ngày không được nối: {far}")
    retry = dx.cmd("luu_chang", {"rows": [row(today, "MAUU7654322")]})
    require(retry["ok"] is False and retry["loi"][0]["ma"] == "TRUNG_CHANG", "dán lại cùng chặng phải báo trùng")
    cases.append("lưu chặng: nối chuyến khách lệch ≤ 10 ngày, gần nhất, điền tuyến trống; chặng phụ không nối; tháng khóa gắn sau khóa; dán lại báo trùng")

    # Mã yêu cầu: lặp cùng nội dung trả kết quả cũ; khác nội dung bị từ chối; hai lệnh song song chỉ ghi một.
    payload = {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "500", "ghi_chu": "ứng giả"}
    first = dx.cmd("ghi_ung", payload, key="ung-lap")
    again = dx.cmd("ghi_ung", payload, key="ung-lap")
    require(again.get("lap_lai") and again["ung_id"] == first["ung_id"], f"lặp lệnh: {again}")
    pg.rejects(dx.sql("ghi_ung", {"idempotency_key": "ung-lap", **payload, "so_tien_vnd": "600"}), message="IDEMPOTENCY_CONFLICT")
    results, errors = [], []

    def race() -> None:
        try:
            results.append(json.loads(pg.sql(dx.sql("ghi_ung", {"idempotency_key": "ung-song-song", "nguoi_id": tx2, "ngay": str(today),
                                                                "so_tien_vnd": "200"}), user="v7_app").stdout.strip()))
        except HarnessError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=race) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    require(not errors and len(results) == 3 and len({r["ung_id"] for r in results}) == 1, f"song song: {results} {errors}")
    require(count(pg, f"SELECT count(*) FROM doixe.ung WHERE nguoi_id={tx2}") == 1, "lệnh song song ghi hơn một lần ứng")
    dx.reject("ghi_ung", {**payload, "ngay": str(tomorrow)}, "NGAY_TUONG_LAI")
    dx.reject("ghi_ung", {**payload, "so_tien_vnd": "0"}, "INVALID_VND")
    dx.reject("ghi_ung", {**payload, "so_tien_vnd": 500}, "INVALID_VND")
    cases.append("mã yêu cầu: lặp trả kết quả cũ, khác nội dung từ chối, ba lệnh song song (role app) chỉ ghi một; ứng ngày mai/0đ chặn")

    # Số dư và thẻ tiền: số dư đầu + chi − hoàn − ứng; VETC và dòng người khác trả không vào; công ty trả không vào ai.
    def check_balance(person: int, opening: int) -> int:
        chi = 0
        for m in ("2026-01-01", str(month)):
            chi += money([leg for leg in dx.so("nguoi", person, m)["chang"] if leg["nguoi_tra_id"] == person])
        ung = int(pg.value(f"SELECT coalesce(sum(so_tien_vnd),0) FROM doixe.ung WHERE nguoi_id={person} AND huy_luc IS NULL"))
        hoan = int(pg.value(f"SELECT coalesce(sum(so_tien_vnd),0) FROM doixe.dot_hoan WHERE nguoi_id={person} AND huy_luc IS NULL"))
        book_now = dx.so("nguoi", person)
        card = book_now["the"]
        require(int(card["dau_vnd"]) + int(card["chi_vnd"]) - int(card["hoan_vnd"]) - int(card["ung_vnd"]) == int(card["cuoi_vnd"])
                == int(book_now["so_du_vnd"]) == opening + chi - hoan - ung, f"số dư người {person}: {card} {book_now['so_du_vnd']}")
        return int(book_now["so_du_vnd"])

    require(check_balance(tx1, 0) == 450 + 350 + 250 + 300 + 50 - 500, "số dư tài xế 1")
    require(check_balance(tx2, 1000) == 1000 + 100 - 200, "số dư tài xế 2")
    require(check_balance(dl1, -3000) == -3000 + 500, "số dư người đi lệnh")
    tx2_rows = dx.so("nguoi", tx2)["chang"]
    require({leg["container"] for leg in tx2_rows} == {"MAUU7654323"} and tx2_rows[0]["nguoi_tra_id"] == dl1,
            "sổ tài xế thấy chặng mình lái do người đi lệnh trả")
    overview = dx.read("doixe.get_tong(NULL)")
    require(overview["nguoi"][0]["chua_hoan"] == 3 and [x["chang"] for x in overview["xe"] if x["id"] == x1] == [2]
            and [x["chua_phi"] for x in overview["xe"] if x["id"] == x1] == [1], f"màn Đội xe: {overview['nguoi']} {overview['xe']}")
    require(overview["khoa"] == {"2026-01-01": True, str(month): False}, f"khóa mặc định: {overview['khoa']}")
    cases.append("số dư = số dư đầu + tài xế chi − hoàn − ứng ở mọi người; thẻ tiền khớp; VETC, người khác trả, công ty trả không vào; đếm màn Đội xe")

    # Sửa ô: tháng mở ghi đè; tháng khóa thêm dòng điều chỉnh; giá trị máy khác thấy thì CHANGED.
    now_leg = next(leg for leg in dx.so("nguoi", tx1)["chang"] if leg["container"] == "MAUU7654321")
    lines = count(pg, f"SELECT count(*) FROM doixe.dong WHERE chang_id={now_leg['id']}")
    edited = dx.cmd("sua_chang", {"chang_id": now_leg["id"], "cot": "phi:nangha", "truoc": "300", "gia_tri": "320"})
    require(edited["cach"] == "ghi_de" and count(pg, f"SELECT count(*) FROM doixe.dong WHERE chang_id={now_leg['id']}") == lines, f"ghi đè: {edited}")
    dx.reject("sua_chang", {"chang_id": now_leg["id"], "cot": "phi:nangha", "truoc": "300", "gia_tri": "330"}, "CHANGED")
    require(dx.cmd("sua_chang", {"chang_id": now_leg["id"], "cot": "phi:nangha", "truoc": "320", "gia_tri": "320"})["khong_doi"], "không đổi")
    jan_leg = hang
    adj = dx.cmd("sua_chang", {"chang_id": jan_leg["id"], "cot": "phi:neo", "truoc": None, "gia_tri": "100"})
    require(adj["cach"] == "dieu_chinh" and adj["ly_do_dc"] == "thang_khoa" and adj["chenh_vnd"] == "100", f"điều chỉnh: {adj}")
    adj2 = dx.cmd("sua_chang", {"chang_id": jan_leg["id"], "cot": "phi:nang", "truoc": "450", "gia_tri": "400"})
    require(adj2["chenh_vnd"] == "-50", "điều chỉnh giảm")
    jan_now = next(leg for leg in dx.so("nguoi", tx1, "2026-01-01")["chang"] if leg["id"] == jan_leg["id"])
    require(jan_now["dong"][0]["phi"] == {"nang": "450", "nangha": "350"} and len(jan_now["dong"]) == 3
            and [d["dc_phi"] for d in jan_now["dong"][1:]] == ["neo", "nang"], f"số cũ giữ nguyên: {jan_now['dong']}")
    dx.reject("sua_chang", {"chang_id": now_leg["id"], "cot": "ngay", "truoc": str(today), "gia_tri": "2026-01-20"}, "THANG_KHOA_CHUYEN")
    dx.reject("sua_chang", {"chang_id": jan_leg["id"], "cot": "ngay", "truoc": "2026-01-08", "gia_tri": str(today)}, "THANG_KHOA_CHUYEN")
    dx.reject("sua_chang", {"chang_id": now_leg["id"], "cot": "ngay", "truoc": str(today), "gia_tri": str(tomorrow)}, "NGAY_TUONG_LAI")
    dx.reject("sua_chang", {"chang_id": now_leg["id"], "cot": "container", "truoc": "MAUU7654321", "gia_tri": "MAUU7654322"}, "TRUNG_CHANG")
    require(dx.cmd("sua_chang", {"chang_id": jan_leg["id"], "cot": "noi_ha", "truoc": "CANG GIA B", "gia_tri": "CANG GIA C"})["cach"] == "ghi_de",
            "sửa chữ ở tháng khóa ghi đè")
    dx.reject("sua_chang", {"chang_id": jan_leg["id"], "cot": "nguoi_tra", "truoc": str(tx1), "gia_tri": "cong_ty"}, "KHONG_DOI_NGUOI_TRA")
    check_balance(tx1, 0)
    cases.append("sửa ô: tháng mở ghi đè; tháng khóa thêm dòng điều chỉnh (tăng/giảm), số cũ giữ; CHANGED khi khác máy; không chuyển vào/ra tháng khóa; trùng chặn")

    # Đổi người trả ở tháng mở: tiền chuyển sang người mới; công ty trả thì không vào ai.
    empty_leg = next(leg for leg in dx.so("nguoi", tx1)["chang"] if leg["container"] == "MAUU7654322")
    dx.cmd("sua_chang", {"chang_id": empty_leg["id"], "cot": "phi:nangha", "truoc": None, "gia_tri": "80"})
    sd_tx1 = int(dx.so("nguoi", tx1)["so_du_vnd"])
    dx.cmd("sua_chang", {"chang_id": empty_leg["id"], "cot": "nguoi_tra", "truoc": str(tx1), "gia_tri": "cong_ty"})
    require(int(dx.so("nguoi", tx1)["so_du_vnd"]) == sd_tx1 - 80, "đổi sang công ty trả bỏ tiền khỏi số dư tài xế")
    dx.cmd("sua_chang", {"chang_id": empty_leg["id"], "cot": "nguoi_tra", "truoc": "cong_ty", "gia_tri": str(tx1)})
    require(int(dx.so("nguoi", tx1)["so_du_vnd"]) == sd_tx1, "đổi lại tài xế trả")
    cases.append("đổi người trả ở tháng mở: tiền theo người trả mới, công ty trả không vào ai")

    # Hoàn theo đợt: dòng đúng người, chưa hoàn; chuyển khác tổng; hủy có lý do trả dòng về.
    pending = dx.so("nguoi", tx1)["chua_hoan"]
    line_ids = [line["id"] for leg in pending for line in leg["dong"] if line["dot_hoan_id"] is None
                and sum(int(v) for k, v in line["phi"].items() if k != "vetc") != 0]
    total = sum(int(v) for leg in pending for line in leg["dong"] if line["id"] in line_ids for k, v in line["phi"].items() if k != "vetc")
    sd0 = check_balance(tx1, 0)
    dx.reject("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "100", "dong_ids": []}, "DONG_THIEU")
    other = [line["id"] for leg in dx.so("nguoi", dl1)["chua_hoan"] for line in leg["dong"]]
    dx.reject("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "100", "dong_ids": other}, "DONG_DA_DOI")
    dx.reject("ghi_hoan", {"nguoi_id": tx1, "ngay": str(tomorrow), "so_tien_vnd": "100", "dong_ids": line_ids}, "NGAY_TUONG_LAI")
    refund = dx.cmd("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": str(total - 400), "dong_ids": line_ids})
    require(refund["tong_dong_vnd"] == str(total) and int(refund["so_du_sau_vnd"]) == sd0 - (total - 400), f"đợt hoàn: {refund} tổng {total}")
    require(dx.so("nguoi", tx1)["chua_hoan"] == [] and check_balance(tx1, 0) == sd0 - (total - 400), "hoàn xong không còn dòng chờ")
    dx.reject("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "0", "dong_ids": line_ids[:1]}, "DONG_DA_DOI")
    # Dòng đã hoàn (tháng mở): sửa tiền thêm dòng điều chỉnh chờ hoàn; VETC (công ty trả) vẫn ghi đè; không đổi người trả; xóa thành bỏ.
    adj3 = dx.cmd("sua_chang", {"chang_id": now_leg["id"], "cot": "phi:neo", "truoc": None, "gia_tri": "60"})
    require(adj3["ly_do_dc"] == "da_hoan", f"dòng đã hoàn: {adj3}")
    require(dx.cmd("sua_chang", {"chang_id": now_leg["id"], "cot": "phi:vetc", "truoc": "120", "gia_tri": "125"})["cach"] == "ghi_de", "VETC ghi đè")
    dx.reject("sua_chang", {"chang_id": now_leg["id"], "cot": "nguoi_tra", "truoc": str(tx1), "gia_tri": str(tx2)}, "KHONG_DOI_NGUOI_TRA")
    require([d["phi"] for leg in dx.so("nguoi", tx1)["chua_hoan"] for d in leg["dong"] if d["dot_hoan_id"] is None] == [{"neo": "60"}],
            "dòng điều chỉnh của dòng đã hoàn là dòng chờ hoàn")
    dx.reject("huy_hoan", {"dot_id": refund["dot_id"], "ly_do": "  "}, "LY_DO_THIEU")
    undone = dx.cmd("huy_hoan", {"dot_id": refund["dot_id"], "ly_do": "chuyển nhầm số"})
    require(undone["dong_tro_lai"] == len(line_ids) and count(pg, f"SELECT count(*) FROM doixe.dong WHERE dot_hoan_id={refund['dot_id']}") == 0,
            f"hủy đợt hoàn: {undone}")
    dx.reject("huy_hoan", {"dot_id": refund["dot_id"], "ly_do": "lần hai"}, "DA_HUY")
    zero = dx.cmd("ghi_hoan", {"nguoi_id": tx1, "ngay": str(today), "so_tien_vnd": "0", "dong_ids": line_ids})
    require(int(zero["so_du_sau_vnd"]) == int(zero["so_du_truoc_vnd"]), "quyết toán chuyển 0 không đổi số dư")
    check_balance(tx1, 0)
    cases.append("hoàn theo đợt: chặn dòng người khác/đã hoàn/rỗng/ngày mai; chuyển khác tổng; dòng đã hoàn sửa thành điều chỉnh; hủy có lý do trả dòng; chuyển 0")

    # Xóa/bỏ chặng: tháng mở chưa hoàn thì ẩn và mở lại khóa trùng; tháng khóa (hoặc đã hoàn) gạch ngang + dòng trừ lại.
    extra = dx.cmd("luu_chang", {"rows": [row(today, "MAUU5550001", phi={"nangha": "90"})]})["chang_ids"][0]
    sd1 = int(dx.so("nguoi", tx1)["so_du_vnd"])
    require(dx.cmd("xoa_chang", {"chang_id": extra})["cach"] == "xoa" and int(dx.so("nguoi", tx1)["so_du_vnd"]) == sd1 - 90, "xóa tháng mở")
    require(all(leg["id"] != extra for leg in dx.so("nguoi", tx1)["chang"]), "chặng đã xóa không hiện")
    require(dx.cmd("luu_chang", {"rows": [row(today, "MAUU5550001", phi={"nangha": "95"})]})["ok"], "xóa rồi nhập lại được")
    dx.reject("xoa_chang", {"chang_id": extra}, "CHANG_NOT_FOUND")
    sd2 = int(dx.so("nguoi", tx1)["so_du_vnd"])
    gone = dx.cmd("xoa_chang", {"chang_id": jan_leg["id"]})
    after = next(leg for leg in dx.so("nguoi", tx1, "2026-01-01")["chang"] if leg["id"] == jan_leg["id"])
    require(gone["cach"] == "bo" and after["da_bo"] and money([after]) == 0 and after["dong"][-1]["loai"] == "tru_lai"
            and int(dx.so("nguoi", tx1)["so_du_vnd"]) == sd2 - (400 + 350 + 100), f"bỏ chặng tháng khóa: {after}")
    dx.reject("sua_chang", {"chang_id": jan_leg["id"], "cot": "phi:nang", "truoc": "0", "gia_tri": "1"}, "CHANG_DA_BO")
    require(dx.cmd("xoa_chang", {"chang_id": now_leg["id"]})["cach"] == "bo", "chặng có dòng đã hoàn: bỏ, không xóa")
    check_balance(tx1, 0)
    cases.append("xóa tháng mở ẩn chặng, nhập lại được; tháng khóa hoặc đã hoàn: gạch ngang, dòng trừ lại đúng từng phí, không sửa được nữa")

    # Khóa/mở tháng chung cả đội: ghi Lịch sử; tháng tương lai chặn; tháng khóa thì mọi sửa tiền là điều chỉnh.
    dx.reject("khoa_thang", {"thang": str((month + dt.timedelta(days=40)).replace(day=1)), "khoa": True}, "INVALID_MONTH")
    dx.reject("khoa_thang", {"thang": str(today.replace(day=2)) if today.day != 2 else str(today.replace(day=3)), "khoa": True}, "INVALID_MONTH")
    require(dx.cmd("khoa_thang", {"thang": str(month), "khoa": True})["khoa"] is True, "khóa tháng này")
    require(dx.cmd("khoa_thang", {"thang": str(month), "khoa": True})["khong_doi"], "khóa lần hai không đổi")
    locked_leg = next(leg for leg in dx.so("nguoi", tx1)["chang"] if leg["container"] == "MAUU5550001")
    require(dx.cmd("sua_chang", {"chang_id": locked_leg["id"], "cot": "phi:nangha", "truoc": "95", "gia_tri": "99"})["ly_do_dc"] == "thang_khoa",
            "tháng vừa khóa: sửa tiền thành điều chỉnh")
    require(dx.cmd("khoa_thang", {"thang": "2026-01-01", "khoa": False})["khoa"] is False, "mở tháng cũ")
    overview = dx.read("doixe.get_tong(NULL)")
    require(overview["khoa"] == {"2026-01-01": False, str(month): True}, f"trạng thái khóa: {overview['khoa']}")
    cases.append("khóa/mở tháng chung cả đội, chặn tháng tương lai và ngày giữa tháng; tháng vừa khóa sửa tiền thành điều chỉnh")

    # Hủy ứng: bắt buộc lý do, không hủy hai lần, vẫn hiện kèm lý do.
    dx.reject("huy_ung", {"ung_id": first["ung_id"], "ly_do": ""}, "LY_DO_THIEU")
    sd3 = int(dx.so("nguoi", tx1)["so_du_vnd"])
    void = dx.cmd("huy_ung", {"ung_id": first["ung_id"], "ly_do": "ghi trùng"})
    require(int(void["so_du_sau_vnd"]) == sd3 + 500, "hủy ứng cộng lại số dư")
    dx.reject("huy_ung", {"ung_id": first["ung_id"], "ly_do": "lần hai"}, "DA_HUY")
    shown = dx.so("nguoi", tx1)["ung"]
    require(shown[0]["huy"]["ly_do"] == "ghi trùng" and shown[0]["huy"]["actor"] == "nhan-vien-gia", f"lần ứng đã hủy vẫn hiện: {shown}")
    check_balance(tx1, 0)
    cases.append("hủy ứng bắt buộc lý do, không hủy hai lần, vẫn hiện kèm người hủy và lý do")

    # Lịch sử: chỉ thêm, có người làm, trước → sau, lý do; lọc theo người và xe; khóa tháng hiện mọi nơi.
    events = dx.read("doixe.get_lich_su(NULL,NULL)")["events"]
    kinds = {e["viec"] for e in events}
    require({"nap", "them_chang", "sua_chang", "dieu_chinh", "doi_nguoi_tra", "xoa_chang", "bo_chang", "ghi_ung", "huy_ung", "ghi_hoan",
             "huy_hoan", "khoa_thang"} <= kinds, f"thiếu loại việc: {kinds}")
    voided = next(e for e in events if e["viec"] == "huy_ung")
    require(voided["ly_do"] == "ghi trùng" and voided["truoc"]["so_du_vnd"] == str(sd3) and voided["sau"]["so_du_vnd"] == str(sd3 + 500),
            f"Lịch sử hủy ứng: {voided}")
    mine = dx.read(f"doixe.get_lich_su({tx2},NULL)")["events"]
    require(any(e["viec"] == "them_chang" and e["nguoi_id"] == dl1 and e["tai_xe_id"] == tx2 for e in mine)
            and any(e["viec"] == "khoa_thang" for e in mine) and not any(e["viec"] == "huy_ung" for e in mine), "Lịch sử theo người")
    truck = dx.read(f"doixe.get_lich_su(NULL,{x3})")["events"]
    require({e["viec"] for e in truck} == {"khoa_thang"}, f"Lịch sử xe không có chặng: {truck}")
    pg.rejects("UPDATE doixe.su_kien SET actor='khac'", message="IMMUTABLE")
    pg.rejects("DELETE FROM doixe.ung", message="IMMUTABLE")
    cases.append("Lịch sử chỉ thêm: người làm, trước → sau, lý do hủy; lọc theo người (kể cả chặng mình lái), theo xe; khóa tháng hiện mọi nơi")

    # Qua đúng adapter của API (SQL cố định trong v7_api_tables, role v7_app): đọc, ghi, mã lỗi thành câu thông báo.
    app = Psql(pg.name, DATABASE, "v7_app")
    whole = app.run("doixe_get_tong", {"thang": None}, "nv-api")
    book_x = app.run("doixe_get_so", {"loai": "xe", "id": x2, "thang": str(month)}, "nv-api")
    require(len(whole["nguoi"]) == 3 and book_x["xe"]["id"] == x2 and app.run("doixe_get_lich_su", {"nguoi": None, "xe": x1}, "nv-api")["events"],
            "đọc qua adapter")
    via = app.run("doixe_ghi_ung", {"idempotency_key": "api-1", "nguoi_id": tx2, "ngay": str(today), "so_tien_vnd": "10"}, "nv-api")
    require(via["ok"] and app.run("doixe_ghi_ung", {"idempotency_key": "api-1", "nguoi_id": tx2, "ngay": str(today), "so_tien_vnd": "10"},
                                  "nv-api")["lap_lai"], "ghi qua adapter, lặp không ghi lại")
    try:
        app.run("doixe_ghi_ung", {"idempotency_key": "api-2", "nguoi_id": tx2, "ngay": str(tomorrow), "so_tien_vnd": "10"}, "nv-api")
        raise HarnessError("ngày mai lọt qua adapter")
    except ApiError as exc:
        require(exc.status == 422 and exc.code == "NGAY_TUONG_LAI", f"mã lỗi qua adapter: {exc.code}")
    require(pg.value("SELECT actor FROM doixe.ung ORDER BY id DESC LIMIT 1") == "nv-api", "người làm lấy từ phiên của API")
    cases.append("qua adapter API (role v7_app): ba đường đọc, ghi ứng và lặp lệnh, ngày mai thành 422 NGAY_TUONG_LAI, người làm từ phiên")

    # Phiếu chi mới: Hạ sớm/KH là tài xế chi; ba ô số lượng lưu, sửa ghi đè cả ở tháng khóa, vào Lịch sử, không đổi tiền.
    phieu_ids = dx.cmd("luu_chang", {"rows": [
        row(jan + dt.timedelta(days=2), "MAUU6660001", phi={"hasom": "70"}, neo_ngay="2", may_gio="5", km="45"),
        row(today, "MAUU6660002", phi={"hasom": "30", "neo": "40"}, neo_ngay=None, may_gio=None, km=None)]})["chang_ids"]
    sd_phieu = check_balance(tx1, 0)
    locked = next(leg for leg in dx.so("nguoi", tx1, "2026-01-01")["chang"] if leg["id"] == phieu_ids[0])
    require((locked["neo_ngay"], locked["may_gio"], locked["km"], locked["dong"][0]["phi"]) == (2, 5, 45, {"hasom": "70"}),
            f"lưu số lượng: {locked}")
    lines = count(pg, f"SELECT count(*) FROM doixe.dong WHERE chang_id={phieu_ids[0]}")
    require(dx.cmd("sua_chang", {"chang_id": phieu_ids[0], "cot": "km", "truoc": "45", "gia_tri": "60"})["cach"] == "ghi_de",
            "km ghi đè ở tháng khóa")
    require(dx.cmd("sua_chang", {"chang_id": phieu_ids[0], "cot": "may_gio", "truoc": "5", "gia_tri": None})["cach"] == "ghi_de",
            "xóa giờ máy")
    require(dx.cmd("sua_chang", {"chang_id": phieu_ids[0], "cot": "neo_ngay", "truoc": "2", "gia_tri": "2"})["khong_doi"], "không đổi")
    dx.reject("sua_chang", {"chang_id": phieu_ids[0], "cot": "km", "truoc": "45", "gia_tri": "70"}, "CHANGED")
    current = {"neo_ngay": "2", "may_gio": None, "km": "60"}
    for name, value in (("neo_ngay", "366"), ("may_gio", "1.5"), ("km", "0"), ("km", 12)):
        dx.reject("sua_chang", {"chang_id": phieu_ids[0], "cot": name, "truoc": current[name], "gia_tri": value}, "INVALID_COMMAND")
        dx.reject("luu_chang", {"rows": [row(today, "MAUU6660009", **{name: value})]}, "INVALID_COMMAND")
    after = next(leg for leg in dx.so("nguoi", tx1, "2026-01-01")["chang"] if leg["id"] == phieu_ids[0])
    require((after["km"], after["may_gio"], after["neo_ngay"]) == (60, None, 2)
            and count(pg, f"SELECT count(*) FROM doixe.dong WHERE chang_id={phieu_ids[0]}") == lines, f"số lượng không thêm dòng: {after}")
    require(check_balance(tx1, 0) == sd_phieu, "sửa số lượng làm đổi số dư")
    edits = [e for e in dx.read(f"doixe.get_lich_su({tx1},NULL)")["events"]
             if e["viec"] == "sua_chang" and e["truoc"].get("chang_id") == phieu_ids[0]]
    require(sorted((e["truoc"]["cot"], e["truoc"]["gia_tri"], e["sau"]["gia_tri"]) for e in edits) == [("km", "45", "60"), ("may_gio", "5", None)],
            f"Lịch sử số lượng: {edits}")
    cases.append("phiếu chi mới: Hạ sớm/KH vào tài xế chi; ngày neo, giờ máy, km lưu, ghi đè cả tháng khóa không thêm dòng, "
                 "sai thì chặn, vào Lịch sử trước → sau, số dư không đổi")

    # Không ghi sokhach.
    require(pg.value(actor_sql("SELECT sokhach.get_read_stamp()->>'stamp'")) == stamp, "doixe đã làm đổi dữ liệu sokhach")
    cases.append("dấu dữ liệu sokhach không đổi sau mọi lệnh đội xe")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "specs/chi-phi-xe-01.md", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
    started = time.monotonic()
    try:
        with disposable_database(report) as pg:
            scenario(pg, cases)
        report["result"] = "pass"
    except (HarnessError, OSError, ValueError, KeyError, StopIteration, IndexError) as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[-3000:]}"
    report["seconds"] = round(time.monotonic() - started, 1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report["result"] != "pass" or report["cleanup"] != "verified_and_removed")


if __name__ == "__main__":
    sys.exit(main())
