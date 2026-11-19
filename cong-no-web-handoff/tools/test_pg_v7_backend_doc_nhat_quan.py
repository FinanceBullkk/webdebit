"""Audit kiến trúc 19/11/2026 (A01): một trả lời get_ledger ở GET không trộn hai trạng thái đã commit.

Run only through disposable test_pg_v7_backend.py harness. Như probe gốc (_logs/architecture-deep-20261119/pg-probes.py), chèn tạm một
rào khóa tư vấn vào get_ledger ngay sau câu tính tổng tháng, ghi một phiếu thu trong lúc lượt đọc chờ ở rào, rồi thả rào. Đầu giao
dịch lấy đúng từ adapter (`v7_psql.begin_sql`): cờ `consistent` của GET phải cho tổng nợ và danh sách phiếu cùng một ảnh; đầu
mặc định (READ COMMITTED, đường ghi) là ca đối chứng chứng minh rào thật sự tạo được trộn lẫn."""
import json
import sys
import time
from pathlib import Path

from pg_v7_harness import PsqlSession, call, lit, new_book, require, version

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_psql

BARRIER = 819263741
MARKER = "INTO v_months,v_total FROM chain;"


def _wait_blocked(pg, name: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if pg.value("SELECT count(*) FROM pg_stat_activity WHERE application_name=" + lit(name)
                    + " AND wait_event_type='Lock' AND cardinality(pg_blocking_pids(pid))>0") == "1":
            return
        time.sleep(0.05)
    raise AssertionError("reader never reached the advisory-lock barrier")


def _read_across_receipt(pg, begin: str, name: str) -> tuple[dict, int]:
    customer = new_book(pg, ("2026-01-01", 100))
    holder, reader = PsqlSession(pg, name + "_holder"), PsqlSession(pg, name)
    try:
        holder.send(f"BEGIN; SELECT pg_advisory_xact_lock({BARRIER}); SELECT 1")
        require(holder.line() == "" and holder.line() == "1", "holder barrier failed")
        reader.send(begin.replace("\n", " ") + f" SET LOCAL sokhach.actor='reader'; SELECT sokhach.get_ledger({customer}); COMMIT")
        _wait_blocked(pg, name)
        call(pg, "record_receipt", customer, version(pg, customer), f"dnq-{name}", "2026-01-02", "KHÁC", 50)
        holder.send("COMMIT; SELECT 2")
        require(holder.line() == "2", "holder release failed")
        result = json.loads(reader.line())
        return result, sum(int(item["amount_vnd"]) for item in result["receipts"] if not item["voided_on"])
    finally:
        holder.close()
        reader.close()


def check_doc_nhat_quan(pg) -> str:
    original = pg.value("SELECT pg_get_functiondef('sokhach.get_ledger(bigint)'::regprocedure)")
    require(original.count(MARKER) == 1, "get_ledger instrumentation point moved; update this check")
    pg.sql(original.replace(MARKER, MARKER + f"\n    PERFORM pg_advisory_xact_lock({BARRIER});"))
    try:
        consistent, receipts = _read_across_receipt(pg, v7_psql.begin_sql(consistent=True), "dnq_consistent")
        require(consistent["total_outstanding_vnd"] == "100" and receipts == 0,
                f"GET read mixed states: outstanding {consistent['total_outstanding_vnd']} with receipts {receipts}")
        mixed, receipts = _read_across_receipt(pg, v7_psql.begin_sql(), "dnq_committed")
        require(mixed["total_outstanding_vnd"] == "100" and receipts == 50,
                "control: READ COMMITTED read should mix states at the barrier (otherwise this check proves nothing)")
    finally:
        pg.sql(original)   # pg_get_functiondef kèm cả SET (jit=off của MO-SO-NHANH-03), nên trả lại đúng bản cũ
    require(pg.value("SELECT pg_get_functiondef('sokhach.get_ledger(bigint)'::regprocedure)") == original,
            "get_ledger not restored after instrumentation")
    return "GET header keeps outstanding and receipts in one snapshot across a concurrent receipt; READ COMMITTED control mixes"
