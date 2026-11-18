"""MO-SO-NHANH-02: get_ledger_events cho khung Lịch sử, cùng dữ liệu với get_ledger. MO-SO-NHANH-03: get_ledger không JIT."""

from __future__ import annotations

import json

from pg_v7_harness import Pg, actor_sql, call, new_book, reject_call, require, version


def check_ledger_events(pg: Pg) -> None:
    customer = new_book(pg, ("2026-01-01", 1000))
    call(pg, "record_receipt", customer, version(pg, customer), "events-receipt", "2026-02-01", "THU TIỀN", 300, None)
    ledger = call(pg, "get_ledger", customer)
    body = call(pg, "get_ledger_events", customer)
    require(set(body) == {"customer_id", "version", "events"}, f"unexpected keys: {sorted(body)}")
    require(body["customer_id"] == customer and body["version"] == ledger["version"], f"version differs: {body['version']} vs {ledger['version']}")
    require(ledger["events"], "fixture should have events")
    require(body["events"] == ledger["events"], "events differ from get_ledger")

    # Mới nhất trước, như get_ledger; đọc không đổi version.
    stamps = [(event["at"], event["id"]) for event in body["events"]]
    require(stamps == sorted(stamps, reverse=True), "events must be newest first")
    require(version(pg, customer) == ledger["version"], "reading must not bump customer.version")

    # Sổ chưa có mốc active: không có Lịch sử, như get_ledger trả NO_BASELINE.
    draft = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('FAKE EVENTS DRAFT') RETURNING id"))
    require(call(pg, "get_ledger", draft)["status"] == "NO_BASELINE", "draft book should have no baseline")
    empty = call(pg, "get_ledger_events", draft)
    require(empty["events"] == [] and empty["customer_id"] == draft, f"draft book: {empty}")

    # Lỗi và quyền: thiếu người làm, không có khách, reader không gọi được, hàm trong không ai gọi thẳng được.
    reject_call(pg, "get_ledger_events", 999999999, error="CUSTOMER_NOT_FOUND")
    pg.rejects(f"SELECT sokhach.get_ledger_events({customer})", message="ACTOR_REQUIRED")
    app = json.loads(pg.value(actor_sql(f"SELECT sokhach.get_ledger_events({customer})", "harness"), user="v7_app"))
    require(app["events"] == body["events"], "app must read through the allowed function")
    pg.rejects(actor_sql(f"SELECT sokhach.get_ledger_events({customer})", "harness"), user="v7_reader", message="permission denied")
    for user in ("v7_app", "v7_reader"):
        pg.rejects(actor_sql(f"SELECT sokhach._ledger_events({customer})", "harness"), user=user, message="permission denied")


def check_ledger_jit_off(pg: Pg) -> None:
    """Mọi câu trong get_ledger lập kế hoạch không JIT, kể cả khi phiên ép JIT cho mọi câu (ngưỡng 0)."""
    customer = new_book(pg, ("2026-01-01", 1000), ("2026-02-01", 500))
    call(pg, "record_receipt", customer, version(pg, customer), "jit-receipt", "2026-02-01", "THU TIỀN", 300, None)
    config = pg.value("SELECT array_to_string(proconfig,'|') FROM pg_proc WHERE oid='sokhach.get_ledger(bigint)'::regprocedure")
    require(config == "search_path=pg_catalog, sokhach, pg_temp|jit=off", f"get_ledger config: {config}")
    # auto_explain ghi kế hoạch của từng câu, kể cả câu lồng trong hàm; câu nào được biên dịch thì kế hoạch có mục "JIT:".
    probe = ("LOAD 'auto_explain'; SET auto_explain.log_min_duration = 0; SET auto_explain.log_nested_statements = on; "
             "SET auto_explain.log_analyze = on; SET auto_explain.log_level = notice; SET client_min_messages = notice; "
             "SET jit = on; SET jit_above_cost = 0; ")
    # check=False: psql riêng; phiên psql giữ chung của harness chạy thêm câu đánh dấu, câu đó cũng bị JIT.
    probed = pg.sql(probe + actor_sql(f"SELECT sokhach.get_ledger({customer})"), check=False)
    require(probed.returncode == 0, f"auto_explain probe failed: {probed.stderr[-700:]}")
    outer, nested = [], []
    for plan in probed.stderr.split("Query Text:")[1:]:
        (outer if plan.lstrip().startswith("SELECT sokhach.get_ledger(") else nested).append(plan)
    # Câu ngoài cùng lập kế hoạch theo phiên nên phải có JIT; không có thì ảnh thiếu LLVM và phép thử vô nghĩa.
    require(len(outer) == 1 and "\nJIT:" in outer[0], f"outer SELECT should use JIT: {len(outer)} plans")
    require(len(nested) >= 10, f"auto_explain did not log nested statements: {len(nested)}")
    compiled = [plan.strip().splitlines()[0][:80] for plan in nested if "\nJIT:" in plan]
    require(not compiled, f"statements inside get_ledger used JIT: {compiled}")
