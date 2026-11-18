#!/usr/bin/env python3
"""Bản xuất cả sổ trên PostgreSQL 18.6 dùng một lần (XUAT-SO-01, specs/v7-xuat-ca-so.md).

Sổ giả qua lệnh ghi thật (hàm `sokhach.*` như API gọi): sổ nạp có dòng chuyến và dòng thu sổ gốc, sổ còn nợ có chuyến có giá và
chưa giá, phiếu thu, phiếu hủy, điều chỉnh; sổ khách dư; sổ chưa có số dư đầu. Bản xuất đọc mọi sổ trong một giao dịch chỉ đọc
bằng role `v7_app` qua adapter thật (`Psql.run_snapshot`) và phải tự kiểm khớp; làm sai `get_dashboard` hay `get_ledger` ngay trong
container thì phải báo đỏ. Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_v7_xuat_so.py [--report <file>.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))  # tools dùng được tầng web, không có chiều ngược lại
import v7_book_export
from pg_v7_harness import (
    DATABASE,
    IMAGE,
    HarnessError,
    Pg,
    call,
    cutover_book,
    disposable_database,
    import_book,
    import_data,
    new_book,
    require,
    trip_json,
    version,
)
from v7_psql import Psql
from v7_xlsx_writer import read_workbook

NOW = dt.datetime(2026, 11, 18, 10, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
SERIAL = itertools.count(1)   # khóa lệnh mới cho mỗi lệnh ghi


def cmd(pg: Pg, customer: int, function: str, *args) -> dict:
    return call(pg, function, customer, version(pg, customer), f"xuat-{next(SERIAL)}", *args)


def mutate(pg: Pg, function: str, old: str, new: str) -> str:
    """Làm sai một hàm ngay trong container dùng một lần; trả bản gốc để dựng lại."""
    source = pg.value(f"SELECT pg_get_functiondef('sokhach.{function}'::regproc)")
    require(source.count(old) == 1, f"mutant: không thấy đúng một chỗ {old!r} trong sokhach.{function}")
    pg.sql(source.replace(old, new))
    return source


def imported_book(pg: Pg) -> int:
    """Sổ nạp qua đúng đường import → verify → activate, có một dòng chuyến và một dòng thu sổ gốc."""
    customer, cutover = cutover_book(pg, 150)
    opening, _, checks = import_data([0, 150], charges=[100, 200], receipts=[0, 150])
    legacy = json.dumps([
        {"debt_month": "2026-01-01", "kind": "trip", "source_total_vnd": 100, "source_tab": "FAKE", "source_row": 1,
         "display": {"date": "2026-01-05", "container": "FAKE-L1", "unit_price": "100", "from": "FAKE-A", "to": "FAKE-B"}},
        {"debt_month": "2026-02-01", "kind": "receipt", "source_total_vnd": 150, "source_tab": "FAKE", "source_row": 2,
         "display": {"date": "2026-02-10", "raw_date": "10/02 ck", "note": "FAKE"}}])
    call(pg, "import_cutover", customer, 0, "xuat-import", cutover, opening, legacy, checks, 150, "a" * 64)
    call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer), "xuat-verify", None)
    call(pg, "verify_cutover", cutover, "xuat-verify-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover", cutover, "xuat-activate-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer), "xuat-activate", "FAKE-SIGNOFF")
    require(call(pg, "get_ledger", customer)["status"] == "active", "sổ nạp chưa hoạt động")
    return customer


def export(db: Psql) -> tuple[v7_book_export.Export, dict]:
    result = v7_book_export.export(db, "harness", NOW)
    return result, read_workbook(result.data)


def codes(result: v7_book_export.Export) -> set[str]:
    return {problem["code"] for problem in result.problems}


def scenario(pg: Pg, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    db = Psql(pg.name, DATABASE, "v7_app")
    legacy = imported_book(pg)
    debtor, credit = new_book(pg, ("2026-01-01", 1000)), new_book(pg, ("2026-01-01", -500))
    draft, draft_cutover = cutover_book(pg, 1)
    import_book(pg, draft, draft_cutover, [1], "xuat-draft")   # dừng ở bản nháp: sổ chưa có số dư đầu
    for book in (legacy, debtor, credit):
        cmd(pg, book, "set_month_lock", "2026-01-01", "false")
    priced = cmd(pg, debtor, "paste_trips", "2026-01-01", trip_json("200", container="FAKE-X1"))["trip_ids"][0]
    cmd(pg, debtor, "paste_trips", "2026-01-01", trip_json(None, container="FAKE-X2"))
    cmd(pg, debtor, "edit_trip_price", priced, "250", "30")
    wrong = cmd(pg, debtor, "record_receipt", "2026-01-15", "THU TIỀN", "400", None)["pid"]
    cmd(pg, debtor, "record_receipt", "2026-01-20", "THU TIỀN", "600", "FAKE-UNC")
    cmd(pg, debtor, "void_receipt", wrong, "nhập nhầm")
    cmd(pg, debtor, "adjust_month", "2026-01-01", "-30", "giảm giá")
    cmd(pg, credit, "record_receipt", "2026-01-10", "THU TIỀN", "100", None)

    result, book = export(db)
    require(result.ok, f"sổ sạch mà tự kiểm lệch: {result.problems}")
    require(result.filename == "so-web-20261118-1030.xlsx", f"tên file {result.filename}")
    require(list(book) == ["KIỂM", "TỔNG", "THÁNG", "CHUYẾN", "PHIẾU THU", "PHÂN BỔ THU", "ĐIỀU CHỈNH"], f"tab {list(book)}")
    totals = {row[0]: row[6] if len(row) > 6 else None for row in book["TỔNG"][1:]}
    for customer in (legacy, debtor, credit):
        want = int(call(pg, "get_ledger", customer)["total_outstanding_vnd"])
        require(totals[customer] == want, f"sổ {customer}: file {totals[customer]} khác get_ledger {want}")
    require(totals[draft] is None and totals[debtor] == 1000 + 280 - 600 - 30, f"nợ còn lại {totals}")
    trips = book["CHUYẾN"][1:]
    require(any(row[0] == legacy and row[2] == "sổ gốc" and row[14] == 100 for row in trips), "thiếu dòng chuyến sổ gốc")
    missing = [row for row in trips if row[0] == debtor and len(row) > 15 and row[15] == "chưa giá"]
    require(len(missing) == 1 and missing[0][14] is None, f"chuyến chưa giá phải để trống thành tiền: {missing}")
    receipts = book["PHIẾU THU"][1:]
    require(any(row[0] == legacy and row[2] == "sổ gốc" and row[8] == 150 for row in receipts), "thiếu dòng thu sổ gốc")
    require(sum(1 for row in receipts if row[0] == debtor and len(row) > 9 and str(row[9]).startswith("Đã hủy")) == 1,
            "phiếu hủy")
    require(sum(row[7] for row in book["PHÂN BỔ THU"][1:] if row[0] == debtor) == 600, "phân bổ thu của sổ còn nợ")
    cases.append("sổ thật qua nạp, dán chuyến, sửa giá, ghi thu, hủy phiếu, điều chỉnh: bảy tab, tự kiểm khớp, tổng bằng get_ledger")

    original = mutate(pg, "get_dashboard", "coalesce(sum(total) FILTER (WHERE total>0),0)::bigint recv",
                      "(coalesce(sum(total) FILTER (WHERE total>0),0)+1)::bigint recv")
    result, book = export(db)
    require(not result.ok and codes(result) == {"TONG_QUAN_PHAI_THU"} and result.filename.endswith("-CO-LECH.xlsx"),
            f"Tổng quan cộng sai mà không đỏ đúng mã: {result.problems}")
    require(book["KIỂM"][1][:2] == ["Kết quả tự kiểm", "CÓ LỆCH"], "tab KIỂM không ghi lệch")
    pg.sql(original)
    original = mutate(pg, "get_ledger", "'total_outstanding_vnd',v_total::bigint::text",
                      "'total_outstanding_vnd',(v_total+1)::bigint::text")
    result, _ = export(db)
    require({"SO_LECH_TONG_QUAN", "SO_LECH_THANG"} <= codes(result), f"get_ledger sai mà không đỏ: {result.problems}")
    pg.sql(original)
    require(export(db)[0].ok, "dựng lại hàm mà vẫn lệch")
    cases.append("Tổng quan cộng sai, get_ledger sai: tự kiểm đỏ đúng mã, file đánh dấu CO-LECH; dựng lại thì khớp")

    # Giao dịch xuất là chỉ đọc thật: một hàm đọc bị sửa thành có ghi thì cả lượt lỗi, không ra file.
    original = mutate(pg, "get_fee_types", "PERFORM sokhach._actor();",
                      "PERFORM sokhach._actor(); UPDATE sokhach.customer SET version=version WHERE false;")
    try:
        export(db)
    except v7_book_export.ApiError as exc:
        require(exc.code == "DB_UNAVAILABLE", f"lỗi lạ {exc.code}")
    else:
        raise HarnessError("hàm đọc có lệnh ghi mà vẫn xuất được: giao dịch không chỉ đọc")
    pg.sql(original)
    cases.append("giao dịch xuất là READ ONLY: hàm đọc có lệnh ghi thì cả lượt lỗi DB_UNAVAILABLE, không ra file")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "specs/v7-xuat-ca-so.md", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
    started = time.monotonic()
    try:
        with disposable_database(report) as pg:
            scenario(pg, cases)
        report["result"] = "pass"
    except (HarnessError, OSError, ValueError, KeyError) as exc:
        report["error"] = f"{type(exc).__name__}: {str(exc)[-3000:]}"
    report["seconds"] = round(time.monotonic() - started, 1)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report["result"] != "pass" or report["cleanup"] != "verified_and_removed")


if __name__ == "__main__":
    sys.exit(main())
