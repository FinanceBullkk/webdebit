"""Hàm đọc chạy với JIT tắt: get_ledger (MO-SO-NHANH-03), get_dashboard_debt (HIEU-NANG-02).

auto_explain ghi kế hoạch của từng câu, kể cả câu lồng trong hàm; câu nào được biên dịch LLVM thì kế hoạch có mục "JIT:".
Phiên ép JIT cho mọi câu (jit_above_cost = 0): câu SELECT ngoài cùng phải có JIT, câu lồng trong hàm thì không.
"""

from __future__ import annotations

from pg_v7_harness import Pg, actor_sql, call, new_book, require, version

PROBE = ("LOAD 'auto_explain'; SET auto_explain.log_min_duration = 0; SET auto_explain.log_nested_statements = on; "
         "SET auto_explain.log_analyze = on; SET auto_explain.log_level = notice; SET client_min_messages = notice; "
         "SET jit = on; SET jit_above_cost = 0; ")


def _require_jit_off(pg: Pg, signature: str, select: str, min_nested: int) -> list[str]:
    """Cấu hình hàm là search_path + jit=off, và không câu nào lồng trong `select` bị JIT. Trả kế hoạch các câu lồng."""
    config = pg.value(f"SELECT array_to_string(proconfig,'|') FROM pg_proc WHERE oid='sokhach.{signature}'::regprocedure")
    require(config == "search_path=pg_catalog, sokhach, pg_temp|jit=off", f"{signature} config: {config}")
    # check=False: psql riêng; phiên psql giữ chung của harness chạy thêm câu đánh dấu, câu đó cũng bị JIT.
    probed = pg.sql(PROBE + actor_sql(select), check=False)
    require(probed.returncode == 0, f"auto_explain probe failed: {probed.stderr[-700:]}")
    outer, nested = [], []
    for plan in probed.stderr.split("Query Text:")[1:]:
        (outer if plan.lstrip().startswith(select) else nested).append(plan)
    # Câu ngoài cùng lập kế hoạch theo phiên nên phải có JIT; không có thì ảnh thiếu LLVM và phép thử vô nghĩa.
    require(len(outer) == 1 and "\nJIT:" in outer[0], f"outer SELECT should use JIT: {len(outer)} plans")
    require(len(nested) >= min_nested, f"auto_explain did not log nested statements: {len(nested)}")
    compiled = [plan.strip().splitlines()[0][:80] for plan in nested if "\nJIT:" in plan]
    require(not compiled, f"statements inside {signature} used JIT: {compiled}")
    return nested


def check_ledger_jit_off(pg: Pg) -> None:
    """Mọi câu trong get_ledger lập kế hoạch không JIT, kể cả khi phiên ép JIT cho mọi câu (ngưỡng 0)."""
    customer = new_book(pg, ("2026-01-01", 1000), ("2026-02-01", 500))
    call(pg, "record_receipt", customer, version(pg, customer), "jit-receipt", "2026-02-01", "THU TIỀN", 300, None)
    _require_jit_off(pg, "get_ledger(bigint)", f"SELECT sokhach.get_ledger({customer})", 10)


def check_dashboard_debt_jit_off(pg: Pg) -> None:
    """Câu chính của get_dashboard_debt (Tổng quan, hộp việc, lưới an toàn) lập kế hoạch không JIT, cả khi gọi từ get_safety_net."""
    nested = _require_jit_off(pg, "get_dashboard_debt()", "SELECT sokhach.get_dashboard_debt()", 1)
    require(any(plan.lstrip().startswith("(WITH act AS") for plan in nested), "main get_dashboard_debt statement not logged")
