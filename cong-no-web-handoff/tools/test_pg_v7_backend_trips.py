"""V7 backend harness cases: Trip input, field edits/adjustments, deletion, duplicate quarantine, review, grid entry.

Run through test_pg_v7_backend.py."""

from __future__ import annotations

import json

from pg_v7_harness import (
    Pg,
    actor_sql,
    allocations,
    assert_allocations,
    call,
    fixture_open_month,
    lit,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)


def check_input(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 1))
    month = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    for key, amount, error in (("neg-zero", "-0", "INVALID_VND"),
                               ("overflow", "9223372036854775808", "INVALID_VND"),
                               ("decimal", "1.5", "INVALID_TRIP_INPUT")):
        reject_call(pg, "paste_trips", c, 0, key, month,
                    trip_json(amount), error=error)
    both = json.loads(trip_json("9223372036854775807"))
    both[0]["otherFeeVnd"] = "1"
    reject_call(pg, "paste_trips", c, 0, "sum-overflow", month, json.dumps(both),
                error="INVALID_VND")
    reject_call(pg, "paste_trips", c, 0, "null-trip", month, "null", error="INVALID_TRIPS")
    require(version(pg, c) == 0 and pg.value(f"SELECT count(*) FROM sokhach.trip WHERE customer_id={c}") == "0",
            "invalid amount inserted a trip")
    trip = call(pg, "paste_trips", c, 0, "missing-price", month, trip_json(None, month=month))["trip_ids"][0]
    reject_call(pg, "edit_trip_price", c, 1, "price-sum-overflow", trip,
                9223372036854775807, 1, error="INVALID_VND")
    row = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip)
    require(row["unit_price_vnd"] is None and row["amount_vnd"] is None
            and row["is_missing_price"] is True and call(pg, "get_ledger", c)["pending_count"] == 1,
            "NULL price became zero or entered balance")
    event = int(pg.value(f"INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
        f"VALUES ({c},'price_edit','harness','{{\"price\":{{}}}}','{{\"price\":{{}}}}') RETURNING id"))
    # Corrupt fixture and rejection share a transaction: no invalid price leaks
    # into later cross-customer reads such as list_offset_sources.
    pg.rejects(actor_sql("INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event) "
           f"VALUES ({trip},{c},9223372036854775807,1,{event}); "
           f"SELECT sokhach.adjust_trip({c},1,'adjust-overflow',{trip},1,'sửa')"),
           message="INVALID_VND")
    pg.true(f"NOT EXISTS (SELECT 1 FROM sokhach.trip_price_rev WHERE trip_id={trip} "
            "AND unit_price_vnd=9223372036854775807)", "overflow price fixture leaked")
    overflow = new_book(pg, ("2026-01-01", 9223372036854775807))
    fixture_open_month(pg, overflow, "2026-01-01")
    reject_call(pg, "adjust_month", overflow, 0, "month-overflow", "2026-01-01", 1,
                "sửa", error="INVALID_VND")
    require(version(pg, overflow) == 0 and pg.value(
        f"SELECT count(*) FROM sokhach.adjustment WHERE customer_id={overflow}") == "0",
        "overflow adjustment left partial money rows")
    event = int(pg.value("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
        f"VALUES ({overflow},'adjust_month','harness','{{\"month\":\"2026-01-01\"}}',"
        "'{\"adjustment\":1}') RETURNING id"))
    pg.rejects(actor_sql("INSERT INTO sokhach.adjustment(customer_id,debt_month,amount_vnd,actor,created_by_event) "
           f"VALUES ({overflow},'2026-01-01',1,'harness',{event}); "
           f"SELECT sokhach.reallocate({overflow},'direct-overflow')"),
               message="INVALID_VND")
    pg.true(f"NOT EXISTS (SELECT 1 FROM sokhach.adjustment WHERE customer_id={overflow})",
            "overflow adjustment fixture leaked")


def check_field_adjustment(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    call(pg, "set_month_lock", c, 0, "field-open", "2026-01-01", "false")
    trip = call(pg, "paste_trips", c, 1, "field-paste", "2026-01-01", trip_json(container="FIELD-PRICED"))["trip_ids"][0]
    missing = call(pg, "paste_trips", c, 2, "field-missing", "2026-01-01", trip_json(None, container="FIELD-MISSING"))["trip_ids"][0]
    call(pg, "set_month_lock", c, 3, "field-open-again", "2026-01-01", "false")
    for expected_version, key, field, value, delta in (
            (4, "field-unit-1", "unit_price_vnd", 120, "20"),
            (5, "field-unit-2", "unit_price_vnd", 130, "10"),
            (6, "field-fee-1", "other_fee_vnd", 7, "7"),
            (7, "field-fee-2", "other_fee_vnd", 9, "2"),
            (8, "field-unit-3", "unit_price_vnd", 140, "10")):
        result = call(pg, "adjust_trip", c, expected_version, key, trip, None, "ghi chú", field, value)
        require(result["delta_vnd"] == delta, f"field current value double-counted: {key}")
        require(call(pg, "adjust_trip", c, expected_version, key, trip, None, "ghi chú", field, value) == result,
                "field retry not idempotent")
    reject_call(pg, "adjust_trip", c, 4, "field-unit-1", trip, None, "ghi chú", "unit_price_vnd", 121,
                error="IDEMPOTENCY_CONFLICT")
    rows = call(pg, "get_ledger", c)
    require([a["amount_vnd"] for a in rows["adjustments"]] == ["20", "10", "10"]
            and rows["total_outstanding_vnd"] == "149", "field deltas or final balance wrong")
    original = next(t for t in rows["trips"] if t["id"] == trip)
    require(original["unit_price_vnd"] == "100" and original["other_fee_vnd"] == "9",
            "locked edit changed original price or NULL storage")
    require(all(a["note"] == "ghi chú" for a in rows["adjustments"]), "field note lost")
    edits = [e for e in reversed(rows["events"]) if e["kind"] == "adjust_trip"]
    require(edits[1]["before"]["new_value_vnd"] == "120" and edits[1]["after"]["new_value_vnd"] == "130"
            and edits[2]["before"]["new_value_vnd"] == "0", "field snapshots lost current value/NULL-fee semantics")
    reject_call(pg, "adjust_trip", c, 9, "field-no-price", missing, None, "", "other_fee_vnd", 5,
                error="TRIP_HAS_NO_PRICE")
    reject_call(pg, "adjust_trip", c, 9, "field-invalid", trip, None, "", "invalid", 5,
                error="INVALID_ADJUSTMENT")
    reject_call(pg, "adjust_trip", c, 9, "field-negative", trip, None, "", "unit_price_vnd", -1,
                error="INVALID_ADJUSTMENT")
    reject_call(pg, "adjust_trip", c, 9, "field-overflow", trip, None, "", "unit_price_vnd", 9223372036854775807,
                error="INVALID_VND")
    require(version(pg, c) == 9, "rejected field adjustment changed version")
    require(call(pg, "adjust_trip", c, 9, "field-legacy", trip, 159, "legacy")["delta_vnd"] == "10",
            "legacy total amount route broke")
    require(call(pg, "adjust_trip", c, 10, "field-after-legacy", trip, None, "", "unit_price_vnd", 155)["delta_vnd"] == "5",
            "field edit ignored current total after legacy adjustment")
    # GET audit money must be strings before JavaScript parses JSON, including old numeric price snapshots.
    call(pg, "set_month_lock", c, 11, "field-reopen", "2026-01-01", "false")
    call(pg, "edit_trip_price", c, 12, "field-big-price", missing, 9007199254740993, None)
    event = next(e for e in call(pg, "get_ledger", c)["events"] if e["kind"] == "price_edit")
    require(event["after"]["price"]["unit_price_vnd"] == "9007199254740993"
            and event["before"]["price"]["unit_price_vnd"] is None,
            "GET price history loses integer precision or turns NULL into zero")


def check_adjustment_source(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    fixture_open_month(pg, c, "2026-01-01")
    trip = call(pg, "paste_trips", c, 0, "source-paste", "2026-01-01", trip_json())["trip_ids"][0]
    call(pg, "adjust_trip", c, 1, "source-unit", trip, None, "", "unit_price_vnd", 120)
    fee = call(pg, "adjust_trip", c, 2, "source-fee", trip, None, "", "other_fee_vnd", 7)
    require(fee["delta_vnd"] == "7" and "adjustment_id" not in fee, "fee must use lines, not adjustment")
    pg.true(f"(SELECT count(*)=0 FROM sokhach.adjustment WHERE trip_id={trip} AND field='other_fee_vnd')",
            "fee adjustment was inserted")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "127", "fee line not counted")
    event = pg.value(f"SELECT created_by_event FROM sokhach.trip_fee_line WHERE trip_id={trip} AND voided_by_event IS NULL")
    pg.sql("BEGIN; SET LOCAL ROLE sokhach_owner; "
           "ALTER TABLE sokhach.event DISABLE TRIGGER event_immutable; "
           f"UPDATE sokhach.event SET \"after\"=jsonb_set(\"after\",'{{new_value_vnd}}','\"999\"'::jsonb) WHERE id={event}; "
           "ALTER TABLE sokhach.event ENABLE TRIGGER event_immutable; COMMIT")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "127", "money depends on audit payload")
    call(pg, "adjust_trip", c, 3, "source-unit-after-audit", trip, None, "", "unit_price_vnd", 130)
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "137", "unit edit double-counted fee")
    zero = call(pg, "adjust_trip", c, 4, "source-zero", trip, None, "", "other_fee_vnd", 0)
    require(zero["delta_vnd"] == "-7" and call(pg, "get_ledger", c)["total_outstanding_vnd"] == "130",
            "zero fee did not clear source lines")


def check_shipper_write_sync(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','SHIP-BASE','2026-01-10')")
    call(pg, "set_month_lock", c, 0, "ship-open", "2026-01-01", "false")
    row = json.loads(trip_json(container="SHIP-C", shipper="SAIGON A"))[0] | {"date": "10/01/2026"}
    first = call(pg, "paste_trips", c, version(pg, c), "ship-first", "2026-01-01", json.dumps([row]))["trip_ids"][0]
    second = call(pg, "paste_trips", c, version(pg, c), "ship-second", "2026-01-01",
                  json.dumps([row]))["trip_ids"][0]

    def trip(trip_id):
        return next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip_id)

    require(trip(first)["shipper"] == "SAIGON A", "paste lost shipper")
    require(trip(second)["status"] == "pending_review" and trip(second)["shipper"] == "SAIGON A",
            "pending paste lost shipper")
    call(pg, "review_trip", c, version(pg, c), "ship-confirm", second, "confirm", "đối chiếu xong")
    require(trip(second)["shipper"] == "SAIGON A", "review lost shipper")
    call(pg, "edit_trip_info", c, version(pg, c), "ship-origin", first, "origin", "DIEN BIEN")
    require(trip(first)["shipper"] == "SAIGON A", "info edit lost shipper")
    call(pg, "edit_trip_info", c, version(pg, c), "ship-edit", first, "shipper", "HA NOI B")
    require(trip(first)["shipper"] == "HA NOI B", "shipper field rejected")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "200", "shipper edits changed money")


def check_dedup(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','BASE','2026-01-10')")

    def paste(key, container, day="10/01/2026", booking=None, month=current):
        row = json.loads(trip_json(container=container))[0]
        row.update(date=day, booking=booking)
        return call(pg, "paste_trips", c, version(pg, c), key, month, json.dumps([row]))

    code = paste("code", " b a s e\u00a0", booking=" b\u202fk 1")
    require(code["pending_review"][0]["reason"] == "BASELINE_CODE_MATCH", "Unicode code match")
    # Test outside days before nearby pending rows are saved into this same book.
    for day, pending in (("06/01/2026", False), ("14/01/2026", False),
                         ("07/01/2026", True), ("13/01/2026", True)):
        result = paste(day, "BASE", day, "BK-" + day)
        require(bool(result["pending_review"]) == pending, "date boundary")
    first = paste("first", "NEW")
    again = paste("again", " n e w", booking="/")
    require(not first["pending_review"] and again["pending_review"][0]["reason"] == "WEB_DUPLICATE", "ALT duplicate")
    row = json.loads(trip_json(container="BATCH"))[0]
    result = call(pg, "paste_trips", c, version(pg, c), "batch", current, json.dumps([row, row]))
    require(result["pending_review"][0]["reason"] == "BATCH_DUPLICATE", "batch duplicate")
    pending_id = code["trip_ids"][0]
    money_rows = pg.value(f"SELECT (SELECT count(*) FROM sokhach.trip_price_rev WHERE customer_id={c})||':'||"
                                     f"(SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c})")
    before = pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")
    reject_call(pg, "edit_trip_price", c, version(pg, c), "edit-pending", pending_id, 20, None,
                error="TRIP_PENDING_REVIEW")
    reject_call(pg, "adjust_trip", c, version(pg, c), "adjust-pending", pending_id, 20, "fake",
                error="TRIP_PENDING_REVIEW")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}") == before, "pending mutation event")
    require(pg.value(f"SELECT (SELECT count(*) FROM sokhach.trip_price_rev WHERE customer_id={c})||':'||"
                     f"(SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c})") == money_rows,
            "pending edit wrote price or adjustment")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "400", "pending leaked into money")
    # Only pending trip in a later month must not move overpayment there.
    future_month = "2099-01-01"
    call(pg, "set_month_lock", c, version(pg, c), "open-future", future_month, "false")
    paste("future-pending", "BASE", day="01/01/2099", booking="BK1", month=future_month)
    call(pg, "record_receipt", c, version(pg, c), "advance", "2026-01-01", "THU TIỀN", 500)
    require(allocations(pg, c, "PH-001")[-1] == ("2026-01-01", "advance", "100"), "pending advance month")
    reject_call(pg, "adjust_month", c, version(pg, c), "pending-month", future_month, 1, "fake",
                error="MONTH_NOT_FOUND")
    assert_allocations(pg, c)
    probe = new_book(pg, ("2026-01-01", 0))
    call(pg, "paste_trips", probe, 0, "probe-first", current, trip_json(month=current))
    second = call(pg, "paste_trips", probe, 1, "probe-again", current, trip_json(month=current))
    require(second["pending_review"][0]["reason"] == "WEB_DUPLICATE"
            and call(pg, "get_ledger", probe)["total_outstanding_vnd"] == "100", "C1 reproduced: must be 100, not 200")
    fee = json.loads(trip_json(None, container=""))[0]
    fee.update(date=None, otherFeeVnd="7")
    for n in range(2):
        require(not call(pg, "paste_trips", probe, version(pg, probe), f"fee-{n}", current,
                         json.dumps([fee]))["pending_review"], "fee-only deduped")
    require(call(pg, "get_ledger", probe)["total_outstanding_vnd"] == "114", "fee-only no longer counts")
    # NEWTRIP-01: web and within-batch matches include the inclusive +/-3 day window.
    for delta, pending in ((-4, False), (-3, True), (3, True), (4, False)):
        for scope in ("web", "batch"):
            target = new_book(pg, ("2026-01-01", 0))
            first_row = json.loads(trip_json(container="WINDOW"))[0]
            first_row.update(date="10/01/2026", booking="BK-FIRST")
            next_row = first_row | {"date": f"{10 + delta:02d}/01/2026", "booking": "BK-NEXT"}
            safe = first_row | {"container": "SAFE"}
            if scope == "web":
                call(pg, "paste_trips", target, 0, "window-first", current, json.dumps([first_row]))
            rows = [next_row, safe] if scope == "web" else [first_row, next_row, safe]
            result = call(pg, "paste_trips", target, version(pg, target), "window-mixed", current, json.dumps(rows))
            require(bool(result["pending_review"]) == pending, f"{scope} window {delta}")
            ledger = call(pg, "get_ledger", target)
            require(ledger["total_outstanding_vnd"] == ("200" if pending else "300"), "mixed batch balance")
            held = [t for t in ledger["trips"] if t["status"] == "pending_review"]
            require(len(held) == int(pending) and all(t["amount_vnd"] is None for t in held),
                    "pending row contract")
            if pending:
                require(result["pending_review"][0]["trip_id"] == result["trip_ids"][0 if scope == "web" else 1],
                        "wrong row quarantined")
    empty = new_book(pg)
    # Use separate empty cutover rather than bypass immutable reference rows.
    pg.sql("ALTER TABLE sokhach.baseline_trip_ref DISABLE TRIGGER baseline_trip_ref_immutable")
    empty_cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={empty}")
    pg.sql(f"DELETE FROM sokhach.baseline_trip_ref WHERE cutover_id={empty_cut}")
    pg.sql("ALTER TABLE sokhach.baseline_trip_ref ENABLE TRIGGER baseline_trip_ref_immutable")
    reject_call(pg, "paste_trips", empty, 0, "missing-ref", current, trip_json(), error="BASELINE_REF_MISSING")
    require(version(pg, empty) == 0, "missing reference changed version")


def check_trip_review(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','BASE','2026-01-10')")

    def paste(key, container, booking):
        row = json.loads(trip_json(container=container))[0] | {"date": "10/01/2026", "booking": booking}
        return call(pg, "paste_trips", c, version(pg, c), key, current, json.dumps([row]))

    def trip(trip_id):
        return next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip_id)

    held = paste("held", "BASE", "BK1")["trip_ids"][0]
    other = paste("other", "BASE", "BK2")["trip_ids"][0]
    require(trip(held)["review_reason"] == "BASELINE_CODE_MATCH"
            and trip(other)["review_reason"] == "BASELINE_DATE_WINDOW", "GET lost pending reason")
    call(pg, "record_receipt", c, version(pg, c), "pay", "2026-01-02", "THU TIỀN", 30)
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "advance", "30")], "receipt not advance before review")
    before = version(pg, c)
    for args, error in (((held, "confirm", " "), "REVIEW_REASON_REQUIRED"),
                        ((held, "approve", "fake"), "INVALID_REVIEW"),
                        ((999999, "confirm", "fake"), "TRIP_NOT_FOUND")):
        reject_call(pg, "review_trip", c, before, "bad-" + error, *args, error=error)
    require(version(pg, c) == before, "rejected review changed version")
    call(pg, "set_month_lock", c, version(pg, c), "review-open-jan", "2026-01-01", "false")
    before = version(pg, c)
    confirmed = call(pg, "review_trip", c, before, "confirm", held, "confirm", " đã đối chiếu sổ gốc ", actor="fake-a")
    require(confirmed["status"] == "confirmed" and confirmed["reallocated"], "confirm did not reallocate")
    require(call(pg, "review_trip", c, before, "confirm", held, "confirm", " đã đối chiếu sổ gốc ") == confirmed,
            "review retry wrote twice")
    reject_call(pg, "review_trip", c, before, "confirm", held, "reject", "khác", error="IDEMPOTENCY_CONFLICT")
    ledger = call(pg, "get_ledger", c)
    require(ledger["total_outstanding_vnd"] == "70" and trip(held)["amount_vnd"] == "100"
            and trip(held)["editable"], "confirmed trip not in balance")
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "30")], "receipt not moved onto confirmed trip")
    event = next(e for e in ledger["events"] if e["kind"] == "trip_review")
    require(event["actor"] == "fake-a" and event["before"]["status"] == "pending_review"
            and event["after"] == {"trip": held, "container": "BASE", "status": "confirmed",
                                   "review_reason": "đã đối chiếu sổ gốc"}, "review audit wrong")
    reject_call(pg, "review_trip", c, version(pg, c), "again", held, "reject", "fake", error="TRIP_NOT_PENDING")
    call(pg, "edit_trip_price", c, version(pg, c), "price-after", held, 120, None)
    # Locked month blocks conclusions since the 24/10 update (decisions.md);
    # reject leaves money untouched.
    call(pg, "set_month_lock", c, version(pg, c), "lock", "2026-01-01", "true")
    total = call(pg, "get_ledger", c)["total_outstanding_vnd"]
    reject_call(pg, "review_trip", c, version(pg, c), "locked-reject", other, "reject", "trùng dòng sổ gốc", error="MONTH_LOCKED")
    call(pg, "set_month_lock", c, version(pg, c), "unlock-review", "2026-01-01", "false")
    rejected = call(pg, "review_trip", c, version(pg, c), "reject", other, "reject", "trùng dòng sổ gốc")
    require(rejected == rejected | {"status": "rejected", "reallocated": []}, "reject result wrong")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == total and trip(other)["status"] == "rejected"
            and trip(other)["amount_vnd"] is None, "rejected trip leaked into money")
    call(pg, "set_month_lock", c, version(pg, c), "unlock", "2026-01-01", "false")
    reject_call(pg, "edit_trip_price", c, version(pg, c), "price-rejected", other, 5, None, error="TRIP_PENDING_REVIEW")
    require(paste("again", "BASE", "BK2")["pending_review"][0]["reason"] == "BASELINE_DATE_WINDOW",
            "rejected trip no longer blocks duplicate")
    assert_allocations(pg, c)
    pg.rejects(f"UPDATE sokhach.trip SET note='x' WHERE id={held}", message="immutable row")
    pg.rejects(f"DELETE FROM sokhach.trip WHERE id={other}", message="immutable row")
    pending = paste("direct", "BASE", "BK3")["trip_ids"][0]
    late = paste("late", "BASE", "BK4")["trip_ids"][0]
    call(pg, "set_month_lock", c, version(pg, c), "lock-late", "2026-01-01", "true")
    total = int(call(pg, "get_ledger", c)["total_outstanding_vnd"])
    reject_call(pg, "review_trip", c, version(pg, c), "locked-confirm", late, "confirm", "đối chiếu xong", error="MONTH_LOCKED")
    call(pg, "set_month_lock", c, version(pg, c), "unlock-late-review", "2026-01-01", "false")
    call(pg, "review_trip", c, version(pg, c), "confirmed-late", late, "confirm", "đối chiếu xong")
    require(int(call(pg, "get_ledger", c)["total_outstanding_vnd"]) == total + 100, "locked-month confirm not counted")
    assert_allocations(pg, c)
    call(pg, "set_month_lock", c, version(pg, c), "unlock-late", current, "false")
    pg.rejects(f"UPDATE sokhach.trip SET status='confirmed' WHERE id={pending}", message="immutable row")
    pg.rejects(f"UPDATE sokhach.trip SET status='confirmed',reviewed_by_event=1,note='x' WHERE id={pending}",
               message="immutable row")


def check_nhap_sheet(pg: Pg) -> None:
    c = new_book(pg, ("2026-09-01", 60000000), ("2026-10-01", 93000000))
    for month in ("2026-08-01", "2026-09-01", "2026-10-01"):
        fixture_open_month(pg, c, month)
    opening = pg.value(f"SELECT jsonb_agg(to_jsonb(o) ORDER BY id) FROM sokhach.opening_balance o WHERE customer_id={c}")
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={c} AND kind='import'")
    # Harness-only source rows; bypass import freeze, never monetary immutability.
    pg.sql("ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard")
    ids = []
    try:
        for n, (month, amount, unit, kind) in enumerate([
            ("2026-09-01", 60000000, "60000000", "trip"),
            ("2026-10-01", 0, None, "trip"),
            ("2026-10-01", 93000000, "93000000", "trip"),
            ("2026-10-01", 4000000, None, "receipt"),
        ], 100):
            display = json.dumps({"container": f"FAKE-{n}", "carrier": "FAKE", "from": "A", "to": "B",
                                  "date": month, "unit_price": unit, "fee_vnd": None})
            ids.append(int(pg.value("INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,"
                "source_total_vnd,source_tab,source_row,created_by_event) "
                f"VALUES({c},{cut},{lit(month)},{lit(kind)},{lit(display)}, {amount},'FAKE',{n},{event}) RETURNING id")))
    finally:
        pg.sql("ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard")
    legacy = pg.value(f"SELECT jsonb_agg(to_jsonb(l) ORDER BY id) FROM sokhach.legacy_row l WHERE customer_id={c}")
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-09-01'")
    reject_call(pg, "edit_legacy_trip", c, 0, "locked-legacy-edit", ids[0], "carrier", "FAKE NEW", error="MONTH_LOCKED")
    reject_call(pg, "delete_legacy_trip", c, 0, "locked-legacy-delete", ids[0], error="MONTH_LOCKED")
    require(version(pg, c) == 0, "locked legacy mutation changed version")
    fixture_open_month(pg, c, "2026-09-01")

    def write(name, *args, key=None, actor="fake-editor"):
        before = version(pg, c)
        key = key or f"nhap-{before}-{name}"
        result = call(pg, name, c, before, key, *args, actor=actor)
        require(version(pg, c) == before + 1, f"{name}: version")
        require(call(pg, name, c, before, key, *args, actor=actor) == result, f"{name}: retry")
        reject_call(pg, name, c, before, key+"-stale", *args, error="STALE_LEDGER")
        if name in ("edit_trip_info", "delete_trip", "edit_legacy_trip", "delete_legacy_trip"):
            reject_call(pg, name, c, before, key, args[0]+100000, *args[1:], error="IDEMPOTENCY_CONFLICT")
        return result

    def total():
        return int(call(pg, "get_ledger", c)["total_outstanding_vnd"])

    def deltas(row):
        return int(pg.value(f"SELECT coalesce(sum(amount_vnd),0) FROM sokhach.adjustment WHERE legacy_row_id={row}"))

    start = total()
    write("edit_legacy_trip", ids[0], "unit_price_vnd", "65000000", key="legacy-60-to-65")
    require(total() == start+5000000 and deltas(ids[0]) == 5000000, "60M to 65M")
    audit = json.loads(pg.value(f"SELECT jsonb_build_array(\"before\"->'legacy'->>'counted_vnd',\"after\"->'legacy'->>'counted_vnd') FROM sokhach.event WHERE customer_id={c} AND idempotency_key='legacy-60-to-65' AND kind='legacy_edit'"))
    require(audit == ["60000000", "65000000"], "legacy source/current amount audit")
    write("delete_legacy_trip", ids[0])
    require(total() == start-60000000 and deltas(ids[0]) == -60000000, "delete revised 65M")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "70000000")
    require(total() == start+10000000 and deltas(ids[1]) == 70000000, "missing price to 70M")
    write("edit_legacy_trip", ids[2], "event_date", "2026-09-28")
    require(total() == start+10000000 and deltas(ids[2]) == 0, "93M move preserves total")
    got = json.loads(pg.value(f"SELECT jsonb_object_agg(debt_month,amount_vnd::text) FROM sokhach.adjustment WHERE legacy_row_id={ids[2]}"))
    require(got == {"2026-10-01": "-93000000", "2026-09-01": "93000000"}, "93M wrong month deltas")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "69000000")
    require(deltas(ids[1]) == 69000000, "legacy negative price delta")
    for field, value in [("container", " fake changed "), ("carrier", "FAKE TWO"),
                         ("origin", "C"), ("destination", "D")]:
        count = pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE legacy_row_id={ids[1]}")
        write("edit_legacy_trip", ids[1], field, value)
        require(pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE legacy_row_id={ids[1]}") == count, "text edit wrote money")
    ledger = call(pg, "get_ledger", c)
    require(not any(row["id"] == ids[0] for row in ledger["legacy_rows"]), "deleted legacy visible")
    moved = next(row for row in ledger["legacy_rows"] if row["id"] == ids[2])
    require(moved["month"] == "2026-09-01" and moved["current"]["counted_vnd"] == "93000000"
            and moved["display"]["date"] == "2026-10-01" and moved["editable"], "legacy current/source separation")
    require(any(a["legacy_row_id"] == ids[2] for a in ledger["adjustments"]), "GET lost legacy target")
    for name, args, error in [
        ("edit_legacy_trip", (ids[3], "carrier", "X"), "LEGACY_NOT_TRIP"),
        ("delete_legacy_trip", (ids[0],), "LEGACY_NOT_FOUND"),
        ("edit_legacy_trip", (ids[1], "unknown", "X"), "INVALID_FIELD"),
        ("edit_legacy_trip", (ids[1], "unit_price_vnd", "-0"), "INVALID_VND"),
        ("edit_legacy_trip", (ids[1], "unit_price_vnd", "9223372036854775808"), "INVALID_VND"),
        ("edit_legacy_trip", (ids[1], "event_date", "2026-02-30"), "INVALID_DATE"),
    ]:
        reject_call(pg, name, c, version(pg, c), "bad-"+error, *args, error=error)
    # XOA-THU-GOC-01: xóa khoản thu sổ gốc cộng lại đúng số đã trừ, ở tháng của dòng.
    before_receipt = total()
    write("delete_legacy_trip", ids[3], key="legacy-receipt-delete")
    require(total() == before_receipt+4000000 and deltas(ids[3]) == 4000000, "receipt delete adds debt back")
    got = json.loads(pg.value(f"SELECT jsonb_object_agg(debt_month,amount_vnd::text) FROM sokhach.adjustment WHERE legacy_row_id={ids[3]}"))
    require(got == {"2026-10-01": "4000000"}, "receipt delete month")
    audit = json.loads(pg.value(f"SELECT \"before\"->'legacy' FROM sokhach.event WHERE customer_id={c} AND idempotency_key='legacy-receipt-delete'"))
    require(audit["kind"] == "receipt" and audit["counted_vnd"] == "4000000", "receipt delete audit")
    require(not any(row["id"] == ids[3] for row in call(pg, "get_ledger", c)["legacy_rows"]), "deleted receipt visible")
    reject_call(pg, "delete_legacy_trip", c, version(pg, c), "receipt-again", ids[3], error="LEGACY_NOT_FOUND")
    assert_allocations(pg, c)
    other = new_book(pg, ("2026-09-01", 0))
    reject_call(pg, "edit_legacy_trip", other, 0, "wrong-cut", ids[1], "carrier", "X", error="LEGACY_NOT_FOUND")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "")
    require(deltas(ids[1]) == 0, "blank price did not restore zero contribution")
    reject_call(pg, "edit_legacy_trip", c, version(pg, c), "fee-without-price", ids[1], "other_fee_vnd", "7",
                error="LEGACY_NO_UNIT_PRICE")
    require(deltas(ids[1]) == 0, "fee without unit price entered balance")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "1")
    write("edit_legacy_trip", ids[1], "other_fee_vnd", "7")
    require(deltas(ids[1]) == 8, "legacy unit plus fee")
    write("edit_legacy_trip", ids[1], "other_fee_vnd", "")
    require(deltas(ids[1]) == 1, "NULL fee with known price is not zero in calculation")
    write("edit_legacy_trip", ids[1], "unit_price_vnd", "")
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    row = json.loads(trip_json("100", container="FAKE-WEB", month=current))[0]
    mixed = [row, row | {"container": "FAKE-LOCKED", "date": "10/09/2026"}]
    pasted = write("paste_trips", current, json.dumps(mixed))
    t, locked_trip = pasted["trip_ids"]
    require(pg.value(f"SELECT debt_month FROM sokhach.trip WHERE id={locked_trip}") == "2026-09-01", "paste into locked month")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND kind='paste'") == "1", "mixed batch multiple events")
    write("adjust_trip", t, 125, "fake")
    write("record_receipt", "2026-09-01", "THU TIỀN", 100)
    before_move = total()
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-08-01'")
    reject_call(pg, "edit_trip_info", c, version(pg, c), "locked-destination", t,
                "event_date", "2026-08-10", error="MONTH_LOCKED")
    fixture_open_month(pg, c, "2026-08-01")
    write("edit_trip_info", t, "event_date", "2026-08-10")
    require(total() == before_move, "web move changed customer total")
    require(pg.value(f"SELECT debt_month FROM sokhach.adjustment WHERE trip_id={t}") == current, "rewrote adjustment FK month")
    require(pg.value(f"SELECT debt_month FROM sokhach.v_adjustment_current WHERE trip_id={t}") == "2026-08-01", "adjustment did not follow trip")
    require(allocations(pg, c, "PH-001") == [("2026-08-01", "debt", "100")], "move did not reallocate FIFO")
    require(any(m["month"] == "2026-08-01" for m in call(pg, "get_ledger", c)["months"]), "moved month missing")
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-08-01'")
    reject_call(pg, "edit_trip_price", c, version(pg, c), "current-lock", t, 101, None, error="MONTH_LOCKED")
    write("set_month_lock", "2026-08-01", "false")
    write("edit_trip_info", t, "event_date", "2026-08-11")
    write("edit_trip_price", t, 110, None)
    for locked in (False,):
        write("set_month_lock", "2026-08-01", str(locked).lower())
        for field, value in [("container", f" FAKE {locked} "), ("carrier", f"FAKE {locked}"),
                             ("origin", f"A {locked}"), ("destination", f"B {locked}")]:
            before = version(pg, c)
            old = pg.value(f"SELECT {field} FROM sokhach.v_trip_current WHERE id={t}")
            key = f"cell-{before}"
            write("edit_trip_info", t, field, value, key=key)
            audit = json.loads(pg.value(f"SELECT jsonb_build_object('before',\"before\",'after',\"after\",'actor',actor) FROM sokhach.event WHERE customer_id={c} AND idempotency_key={lit(key)} AND kind='trip_edit'"))
            require(audit["before"]["trip"]["value"] == old and audit["actor"] == "fake-editor", "edit audit before/actor")
            require(audit["after"]["trip"]["value"] == (value.replace(" ", "").upper() if field == "container" else value.strip()), "edit audit after")
            reject_call(pg, "edit_trip_info", c, before, key, t, field, "different", error="IDEMPOTENCY_CONFLICT")
    write("edit_trip_info", t, "event_date", "2026-08-10")
    for args, error in [((t, "carrier", "FAKE False"), "NO_CHANGE"), ((t, "price", "1"), "INVALID_FIELD"),
                        ((t, "event_date", "9999-01-01"), "FUTURE_DATE"), ((t, "carrier", " "), "INVALID_TRIP_INPUT")]:
        reject_call(pg, "edit_trip_info", c, version(pg, c), "info-"+error, *args, error=error)
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES({cut},'BASE','BASE','2026-08-10')")
    held = write("edit_trip_info", t, "container", "BASE")
    require(held["pending_review"] and pg.value(f"SELECT status FROM sokhach.v_trip_current WHERE id={t}") == "pending_review", "duplicate edit not quarantined")
    write("edit_trip_info", t, "container", "FAKE-CLEAN")
    require(pg.value(f"SELECT status FROM sokhach.v_trip_current WHERE id={t}") == "pending_review", "edit auto-confirmed")
    balance = total()
    write("delete_trip", t)
    require(total() == balance, "pending deletion changed total")
    write("delete_trip", locked_trip)
    require(total() == balance-100, "locked deletion amount")
    again = write("paste_trips", current, json.dumps([mixed[1]]))["trip_ids"][0]
    require(pg.value(f"SELECT status FROM sokhach.v_trip_current WHERE id={again}") == "confirmed", "deleted web duplicate blocked paste")
    write("adjust_trip", again, 150, "fake")
    balance = total()
    write("delete_trip", again, key="delete-adjusted")
    require(total() == balance-150, "delete did not remove adjusted amount")
    audit = json.loads(pg.value(f"SELECT \"before\"->'trip' FROM sokhach.event WHERE customer_id={c} AND idempotency_key='delete-adjusted' AND kind='trip_delete'"))
    require(audit["amount_vnd"] == "150" and audit["unit_price_vnd"] == "150"
            and audit["other_fee_vnd"] is None and audit["debt_month"] == "2026-09-01", "delete current amount snapshot")
    open_id = write("paste_trips", current, trip_json("20", container="FAKE-OPEN", month=current))["trip_ids"][0]
    balance = total()
    write("delete_trip", open_id)
    require(total() == balance-20, "open deletion")
    reject_call(pg, "delete_trip", c, version(pg, c), "deleted-again", t, error="TRIP_NOT_FOUND")
    atomic_trip = write("paste_trips", current, trip_json("20", container="FAKE-ATOMIC", month=current))["trip_ids"][0]
    pg.sql("CREATE FUNCTION public.nhap_abort() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'NHAP_ABORT'; END $$")
    try:
        for name, args, table in [
            ("edit_trip_info", (atomic_trip, "carrier", "FAKE CHANGE"), "trip_info_rev"),
            ("delete_trip", (atomic_trip,), "trip_info_rev"),
            ("edit_legacy_trip", (ids[2], "unit_price_vnd", "94000000"), "legacy_trip_rev"),
            ("delete_legacy_trip", (ids[2],), "legacy_trip_rev"),
        ]:
            def state():
                return (version(pg, c), total(), pg.value(f"SELECT jsonb_build_array("
                    f"(SELECT count(*) FROM sokhach.event WHERE customer_id={c}),"
                    f"(SELECT count(*) FROM sokhach.trip_info_rev WHERE customer_id={c}),"
                    f"(SELECT count(*) FROM sokhach.legacy_trip_rev WHERE customer_id={c}),"
                    f"(SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c}))"))
            before = state()
            pg.sql(f"CREATE TRIGGER nhap_abort BEFORE INSERT ON sokhach.{table} FOR EACH ROW EXECUTE FUNCTION public.nhap_abort()")
            try:
                reject_call(pg, name, c, version(pg, c), "fault-"+name, *args, error="NHAP_ABORT")
                require(state() == before, f"{name} left partial changes")
            finally:
                pg.sql(f"DROP TRIGGER nhap_abort ON sokhach.{table}")
    finally:
        pg.sql("DROP FUNCTION public.nhap_abort()")
    fee = write("paste_trips", current, json.dumps([{"container": None, "date": None,
        "unitPriceVnd": None, "otherFeeVnd": "5"}]))["trip_ids"][0]
    for field, value in [("carrier", "FAKE"), ("origin", "A"), ("destination", "B"),
                         ("event_date", current), ("container", "FAKE-FEE-CONVERTED")]:
        write("edit_trip_info", fee, field, value)
    write("edit_trip_price", fee, 7, None)
    require(pg.value(f"SELECT jsonb_agg(to_jsonb(o) ORDER BY id) FROM sokhach.opening_balance o WHERE customer_id={c}") == opening, "opening changed")
    require(pg.value(f"SELECT jsonb_agg(to_jsonb(l) ORDER BY id) FROM sokhach.legacy_row l WHERE customer_id={c}") == legacy, "legacy source changed")
    for table in ("trip", "adjustment", "legacy_row", "opening_balance", "trip_info_rev", "legacy_trip_rev"):
        pg.rejects(f"UPDATE sokhach.{table} SET customer_id=customer_id WHERE customer_id={c}", message="immutable row")
        pg.rejects(f"DELETE FROM sokhach.{table} WHERE customer_id={c}", message="immutable row")
    assert_allocations(pg, c)
