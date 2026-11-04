"""MO-SO-NHANH-02: get_ledger_events cho khung Lịch sử, cùng dữ liệu với get_ledger."""

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
