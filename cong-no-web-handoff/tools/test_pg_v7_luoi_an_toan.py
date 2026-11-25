#!/usr/bin/env python3
"""Lưới an toàn trên PostgreSQL 18.6 dùng một lần (LUOI-AN-TOAN-01, specs/v7-luoi-an-toan.md).

Sổ giả sạch qua nhiều lệnh ghi thật (hàm `sokhach.*` như API gọi) thì không báo gì; mỗi phép kiểm có một vi phạm cố ý làm nó đỏ,
rồi chấp nhận thì hết. Hàm được gọi bằng role `v7_app` qua adapter thật (`Psql`, `read_only=True`) và so như máy canh
(`v7_safety_net.run`), nên kiểm cả quyền, giao dịch chỉ đọc, hàm SQL và phần so mốc. Cần Docker:

    uv run --python 3.13 python cong-no-web-handoff/tools/test_pg_v7_luoi_an_toan.py [--report <file>.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
import time
from pathlib import Path

import v7_safety_net as net  # thêm web/ vào sys.path cho adapter bên dưới
from pg_v7_harness import (
    AUDIT_SQL_MIGRATION,
    DATABASE,
    DIEU_CHINH_THEO_GIA_MIGRATION,
    IMAGE,
    SO_GON_MIGRATION,
    THANG_HIEN_TAI_MIGRATION,
    HarnessError,
    Pg,
    actor_sql,
    call,
    disposable_database,
    new_book,
    require,
    trip_json,
    version,
)
from v7_psql import Psql

MIGRATION = Path(__file__).resolve().parent / "migrations" / "2026-11-18-v7-luoi-an-toan.sql"
# Dòng Lịch sử trong harness vừa ghi xong: không chờ 10 phút "lắng" như trên hao (không có giao dịch nào chạy song song ở đây).
net.SETTLE_SECONDS = 0


class Ledger:
    """Một sổ giả; mỗi lệnh đi qua đúng hàm sokhach.* với version hiện tại và khóa lệnh mới."""

    serial = 0

    def __init__(self, pg: Pg, *openings: tuple[str, int]):
        self.pg, self.id = pg, new_book(pg, *openings)

    def cmd(self, function: str, *args) -> dict:
        Ledger.serial += 1
        return call(self.pg, function, self.id, version(self.pg, self.id), f"luoi-{Ledger.serial}", *args)


class Probe:
    """Chạy lưới an toàn như máy canh: một thư mục mốc, mỗi lượt cách nhau 15 phút."""

    def __init__(self, pg: Pg, folder: Path):
        self.db, self.folder = Psql(pg.name, DATABASE, "v7_app"), folder
        self.at = dt.datetime(2026, 11, 18, 10, 2, tzinfo=net.VN)

    def run(self, **kwargs) -> dict:
        self.at += dt.timedelta(minutes=15)
        return net.run(self.at, db=self.db, state_dir=self.folder, slices=1, **kwargs)

    def quiet(self, label: str) -> None:
        problems = self.run()["problems"]
        require(problems == [], f"{label}: báo nhầm {problems}")

    def expect(self, label: str, *starts: str) -> list[str]:
        problems = self.run()["problems"]
        for start in starts:
            require(any(line.startswith(start) for line in problems), f"{label}: thiếu câu '{start}…' trong {problems}")
        require(len(problems) == len(starts), f"{label}: thừa câu báo {problems}")
        return problems

    def accept(self, label: str) -> None:
        report = self.run(accept=True)
        require(report["accepted"] and report["problems"] == [], f"{label}: chấp nhận không sạch {report}")


def mutate(pg: Pg, function: str, old: str, new: str) -> str:
    """Làm sai một hàm ngay trong container dùng một lần; trả bản gốc để dựng lại."""
    source = pg.value(f"SELECT pg_get_functiondef('sokhach.{function}'::regproc)")
    require(source.count(old) == 1, f"mutant: không thấy đúng một chỗ {old!r} trong sokhach.{function}")
    pg.sql(source.replace(old, new))
    return source


def as_superuser(pg: Pg, sql: str) -> None:
    """Sửa tay như một người có quyền quản trị DB: tắt trigger và khóa ngoại trong phiên (session_replication_role)."""
    pg.sql("SET session_replication_role = replica; " + sql + "; RESET session_replication_role")


def scenario(pg: Pg, folder: Path, cases: list[str]) -> None:
    pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app")
    probe = Probe(pg, folder)
    debtor, credit, spare = Ledger(pg, ("2026-01-01", 1000)), Ledger(pg, ("2026-01-01", -500)), Ledger(pg, ("2026-01-01", 700))

    # Giao dịch phải chỉ đọc và một ảnh dữ liệu; role đọc không có quyền gọi.
    for begin in ("BEGIN; ", "BEGIN READ ONLY; "):
        pg.rejects(actor_sql("SELECT sokhach.get_safety_net('{}')").replace("BEGIN; ", begin, 1), user="v7_app",
                   message="SNAPSHOT_REQUIRED")
    pg.sql("CREATE ROLE v7_reader LOGIN IN ROLE sokhach_reader")
    pg.rejects("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; SET LOCAL sokhach.actor='x'; "
               "SELECT sokhach.get_safety_net('{}'); COMMIT", user="v7_reader", message="permission denied")
    result = probe.db.run("get_safety_net", {"ledger_slices": 1}, net.ACTOR, read_only=True)
    # Khối catalog (kiểm 5) là tên hàm/bảng/ràng buộc của lược đồ (vd. adjustment_amount_vnd_check) và md5, không phải dữ liệu sổ.
    catalog = result.pop("catalog")
    raw = json.dumps(result, ensure_ascii=False)
    require("FAKE" not in raw and "_vnd" not in raw, "kết quả hàm lộ tên sổ hoặc khóa số tiền")
    require("FAKE" not in json.dumps(catalog, ensure_ascii=False)
            and all(re.fullmatch(r"[0-9a-f]{32}(:[OADR])?", value) for part, values in catalog.items() if part != "level"
                    for value in values.values()), "khối catalog chỉ được có tên đối tượng và md5")
    cases.append("chỉ đọc, một ảnh dữ liệu, chỉ app, không tên/số tiền")

    # Sạch: lượt đầu lấy mốc; lệnh ghi thật trên nhiều sổ không gây báo.
    first = probe.run()
    require(first["summary"]["baseline"] == "lần đầu, lấy mốc" and first["problems"] == [], f"lượt đầu: {first}")
    for ledger in (debtor, credit, spare):
        ledger.cmd("set_month_lock", "2026-01-01", "false")
    trip = debtor.cmd("paste_trips", "2026-01-01", trip_json("200", container="FAKE-LAT-1"))["trip_ids"][0]
    debtor.cmd("edit_trip_price", trip, "250", None)
    paid = debtor.cmd("record_receipt", "2026-01-15", "THU TIỀN", "400", None)["pid"]
    debtor.cmd("record_receipt", "2026-01-20", "THU TIỀN", "600", None)  # sổ còn nợ: 1000 + 250 - 30 - 600
    debtor.cmd("void_receipt", paid, "nhập nhầm")
    debtor.cmd("adjust_month", "2026-01-01", "-30", "giảm giá")
    credit.cmd("record_receipt", "2026-01-10", "THU TIỀN", "100", None)
    probe.quiet("lệnh ghi thật")
    probe.quiet("không có gì đổi")
    cases.append("sổ sạch qua dán chuyến, sửa giá, ghi thu, hủy phiếu, điều chỉnh, khóa tháng: không báo")

    # Kiểm 1 (và 3): sửa tay một dòng chia phiếu thu.
    line = f"(SELECT max(id) FROM sokhach.receipt_line WHERE customer_id={debtor.id} AND superseded_by_event IS NULL)"
    as_superuser(pg, f"UPDATE sokhach.receipt_line SET amount_vnd=amount_vnd+1 WHERE id={line}")
    probe.expect("sửa dòng chia", "Phiếu thu chia không khớp tiền phiếu ở 1 sổ", f"Sổ {debtor.id}: dòng chia phiếu thu đổi")
    as_superuser(pg, f"UPDATE sokhach.receipt_line SET amount_vnd=amount_vnd-1 WHERE id={line}")
    probe.expect("trả dòng chia về cũ", f"Sổ {debtor.id}: dòng chia phiếu thu đổi")  # kiểm 1 hết, mục chờ còn
    probe.accept("dòng chia")
    probe.quiet("sau chấp nhận")
    cases.append("kiểm 1: dòng chia lệch tiền phiếu thì đỏ, sửa lại thì tự hết; kiểm 3 giữ tới khi chấp nhận")

    # Kiểm 2: sổ lưu trữ còn nợ; Tổng quan, dải hạn trả và get_ledger bị làm sai.
    pg.sql(f"UPDATE sokhach.customer SET archived=true WHERE id={spare.id}")
    probe.expect("lưu trữ còn nợ", "1 sổ lưu trữ còn số dư nên Tổng quan không tính")
    pg.sql(f"UPDATE sokhach.customer SET archived=false WHERE id={spare.id}")
    original = mutate(pg, "get_dashboard", "coalesce(sum(total) FILTER (WHERE total>0),0)::bigint recv",
                      "(coalesce(sum(total) FILTER (WHERE total>0),0)+1)::bigint recv")
    # Kiểm 5 (audit SQL F1) thấy luôn hàm bị sửa tay.
    probe.expect("Tổng quan cộng sai", "Tổng quan không khớp tổng các sổ: tổng Còn phải thu.", "Định nghĩa trong DB khác repo")
    pg.sql(original)
    original = mutate(pg, "get_dashboard_debt", "WHERE s.total>0),", f"WHERE s.total>0 AND act.id<>{debtor.id}),")
    probe.expect("dải hạn trả thiếu sổ", "Tổng quan không khớp tổng các sổ: tổng ở dải hạn trả, năm nhóm hạn trả, "
                 f"danh sách khách nợ (sổ {debtor.id}).", "Định nghĩa trong DB khác repo")
    pg.sql(original)
    original = mutate(pg, "get_ledger", "'total_outstanding_vnd',v_total::bigint::text",
                      "'total_outstanding_vnd',(v_total+1)::bigint::text")
    probe.expect("tổng trong sổ sai", "Tổng trong sổ khác tổng Tổng quan dùng ở 3 sổ", "Định nghĩa trong DB khác repo")
    pg.sql(original)
    probe.quiet("dựng lại hàm")
    cases.append("kiểm 2: sổ lưu trữ còn nợ, Tổng quan, dải hạn trả, get_ledger sai thì đỏ, đúng lại thì tự hết")

    # Kiểm 3: khóa tháng, giá chuyến sửa tay (kiểm 1, 2 không thấy), version lùi.
    pg.sql(f"UPDATE sokhach.month_state SET locked=NOT locked WHERE customer_id={credit.id}")
    as_superuser(pg, f"UPDATE sokhach.trip_price_rev SET unit_price_vnd=unit_price_vnd+5 WHERE trip_id={trip}")
    pg.sql(f"UPDATE sokhach.customer SET version=version-1 WHERE id={spare.id}")
    probe.expect("sửa tay ngoài lệnh", f"Sổ {debtor.id}: giá chuyến đổi", f"Sổ {credit.id}: khóa tháng đổi",
                 "Số lần ghi của 1 sổ bị lùi")
    debtor.cmd("record_receipt", "2026-01-25", "THU TIỀN", "10", None)  # lệnh mới không xóa dấu vết
    probe.expect("lệnh mới sau sửa tay", f"Sổ {debtor.id}: giá chuyến đổi", f"Sổ {credit.id}: khóa tháng đổi",
                 "Số lần ghi của 1 sổ bị lùi")
    probe.accept("sửa tay")
    probe.quiet("sau chấp nhận")
    cases.append("kiểm 3: khóa tháng, giá chuyến sửa tay, version lùi thì đỏ và giữ qua lệnh mới tới khi chấp nhận")

    # Kiểm 4: sửa và xóa dòng Lịch sử cũ.
    as_superuser(pg, "UPDATE sokhach.event SET actor='sua-tay' WHERE id=(SELECT min(id) FROM sokhach.event)")
    probe.expect("sửa Lịch sử", "Lịch sử có dòng cũ bị sửa hoặc xóa")
    probe.accept("sửa Lịch sử")
    as_superuser(pg, "DELETE FROM sokhach.event WHERE id=(SELECT max(id) FROM sokhach.event WHERE kind='month_lock')")
    probe.expect("xóa Lịch sử", "Lịch sử có dòng cũ bị sửa hoặc xóa")
    probe.accept("xóa Lịch sử")
    probe.quiet("sau chấp nhận")
    cases.append("kiểm 4: sửa hay xóa dòng Lịch sử cũ thì đỏ tới khi chấp nhận")

    # DB chưa nâng thì im; migration chạy lại được và đưa hàm về.
    pg.sql("DROP FUNCTION sokhach.get_safety_net(jsonb)")
    require(probe.run()["summary"].get("skipped"), "thiếu hàm mà không im")
    for _ in range(2):
        pg.sql(MIGRATION.read_text(encoding="utf-8"))
    # Migration 18/11 là bản cũ của get_safety_net (chưa có bảng băm): kiểm 5 báo tới khi chạy lại migration mới nhất.
    probe.expect("chạy lại migration cũ", "DB chưa trả bảng băm định nghĩa")
    pg.sql(AUDIT_SQL_MIGRATION.read_text(encoding="utf-8"))
    pg.sql(DIEU_CHINH_THEO_GIA_MIGRATION.read_text(encoding="utf-8"))  # DIEU-CHINH-THEO-GIA-01: v_adjustment_current, schema_level hiện hành
    pg.sql(SO_GON_MIGRATION.read_text(encoding="utf-8"))  # audit SQL F4: get_ledger, ba lệnh ghi Sheet, schema_level hiện hành
    pg.sql(THANG_HIEN_TAI_MIGRATION.read_text(encoding="utf-8"))  # SK-C1: get_ledger hiện hành
    probe.quiet("sau migration")
    require(pg.value("SELECT has_function_privilege('v7_app','sokhach.get_safety_net(jsonb)','EXECUTE') AND NOT "
                     "has_function_privilege('v7_app','sokhach._safety_events(bigint,interval)','EXECUTE')") == "t",
            "quyền sau migration")
    cases.append("DB chưa có hàm thì im; migration chạy hai lần được; migration cũ kéo hàm về bản cũ thì kiểm 5 báo")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows chuyển hướng ra file thì mặc định cp1252
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", type=Path, help="ghi báo cáo JSON")
    args = ap.parse_args()
    cases: list[str] = []
    report = {"spec": "specs/v7-luoi-an-toan.md", "image": IMAGE, "cases": cases, "result": "fail", "cleanup": "not_started"}
    started = time.monotonic()
    try:
        with disposable_database(report) as pg, tempfile.TemporaryDirectory() as folder:
            scenario(pg, Path(folder), cases)
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
