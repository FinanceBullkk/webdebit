"""HOAT-DONG-01: get_activity — việc đã ghi của một ngày, mọi sổ, cả máy lẫn người; chỉ đọc, chỉ app."""

from __future__ import annotations

import json

from pg_v7_harness import (
    Pg,
    actor_sql,
    call,
    fixture_open_month,
    lit,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)


def _today(pg: Pg) -> str:
    return pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")


def check_activity(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", 1000))
    b = new_book(pg, ("2026-01-01", 500))
    for book in (a, b):
        fixture_open_month(pg, book, "2026-01-01")
        fixture_open_month(pg, book, "2026-02-01")
    trip = call(pg, "paste_trips", a, version(pg, a), "hd-paste", "2026-01-01",
                trip_json(container="FAKE-HD-1"), actor="may-theo-sheet")["trip_ids"][0]
    call(pg, "edit_trip_price", a, version(pg, a), "hd-price", trip, 250, None, actor="may-theo-sheet")
    call(pg, "record_receipt", b, version(pg, b), "hd-receipt", "2026-02-01", "THU TIỀN", 300, None, actor="ke-toan@example")
    versions = (version(pg, a), version(pg, b))

    body = call(pg, "get_activity", None)
    today = _today(pg)
    require(body["day"] == today and body["today"] == today, f"default day must be VN today: {body['day']}")
    mine = [event for event in body["events"] if event["customer_id"] in (a, b) and event["kind"] != "import"]   # import: fixture mở sổ
    require([event["kind"] for event in mine] == ["receipt", "price_edit", "paste"], f"newest first, all books: {mine}")
    require(body["total"] >= len(mine) and len(body["events"]) == body["total"], "total counts every event of the day")
    require({event["actor"] for event in mine} == {"may-theo-sheet", "ke-toan@example"}, "machine and people both listed")
    require(all(event["customer"] == "FAKE CONTRACT" for event in mine), "book name attached")

    # Cùng hình dạng với Lịch sử của sổ: giá là chuỗi, lô dán giữ container/ngày/giá.
    price = next(event for event in mine if event["kind"] == "price_edit")
    ledger_price = next(event for event in call(pg, "get_ledger_events", a)["events"] if event["kind"] == "price_edit")
    require(price["before"] == ledger_price["before"] and price["after"] == ledger_price["after"], "price event differs from Lịch sử")
    paste = next(event for event in mine if event["kind"] == "paste")
    require(paste["after"]["trips"][0]["container"] == "FAKE-HD-1" and paste["after"]["trips"][0]["trip_id"] == trip, f"paste: {paste}")
    require("carrier" not in paste["after"]["trips"][0], "paste rows keep only the fields the page reads")
    require({"id": trip, "container": "FAKE-HD-1"} in body["trips"], "referenced trip container attached")
    receipt = next(event for event in mine if event["kind"] == "receipt")
    receipt_id = int(pg.value(f"SELECT id FROM sokhach.receipt WHERE customer_id={b}"))
    require(any(item["id"] == receipt_id and item["pid"] for item in body["receipts"]), f"receipt pid attached: {receipt}")
    require(body["fee_types"] and all({"id", "name"} == set(item) for item in body["fee_types"]), "fee type names attached")

    # Ngày trước/sau: không có việc thì rỗng; ngày gần nhất có việc chỉ đường đi.
    yesterday = pg.value(f"SELECT ({lit(today)}::date - 1)::text")
    old = call(pg, "get_activity", "2000-01-01")
    require(old["events"] == [] and old["total"] == 0 and old["prev_day"] is None, f"empty day: {old}")
    require(old["next_day"] is not None and old["next_day"] <= today, "next_day points at the next day with work")
    require(call(pg, "get_activity", yesterday)["next_day"] == today, "yesterday's next_day is today")
    reject_call(pg, "get_activity", pg.value(f"SELECT ({lit(today)}::date + 1)::text"), error="INVALID_DAY")

    # Chỉ đọc; quyền: thiếu người làm bị chặn, app đọc được, reader không.
    require((version(pg, a), version(pg, b)) == versions, "reading must not bump versions")
    pg.rejects("SELECT sokhach.get_activity(NULL)", message="ACTOR_REQUIRED")
    app = json.loads(pg.value(actor_sql("SELECT sokhach.get_activity(NULL)", "harness"), user="v7_app"))
    require([e["id"] for e in app["events"]] == [e["id"] for e in body["events"]], "app reads the same list")
    pg.rejects(actor_sql("SELECT sokhach.get_activity(NULL)", "harness"), user="v7_reader", message="permission denied")
