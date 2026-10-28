"""V7 backend harness cases: Sheet duplicates/conflicts, missing price and fee lines.

Run through test_pg_v7_backend.py."""

from __future__ import annotations

import json

from pg_v7_harness import (
    Pg,
    actor_sql,
    call,
    fixture_open_month,
    new_book,
    reject_call,
    require,
    run_node,
    trip_json,
    version,
)


def check_ledger_fee(pg: Pg) -> None:
    # check_fee seeded these three shapes on active fake customer 1.
    rows = {r["id"]: r for r in call(pg, "get_ledger", 1)["trips"]}
    require({101, 102, 103} <= rows.keys(),
            "7.18a fee fixture missing; cannot check get_ledger parity")
    expected = run_node("const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js'); "
        "const x=[{container:'X',unitPriceVnd:'120',otherFeeVnd:null},"
        "{container:'X',unitPriceVnd:null,otherFeeVnd:'7'},"
        "{container:null,unitPriceVnd:null,otherFeeVnd:'7'}]; "
        "console.log(JSON.stringify(x.map(t=>{const r=m.tripAmount(t);return {amount:r.amountVnd?.toString()??null,missing:r.isMissingPrice,fee:r.isFeeOnly}})))")
    for trip_id, model in zip((101, 102, 103), expected, strict=True):
        row = rows[trip_id]
        require((row["amount_vnd"], row["is_missing_price"], row["is_fee_only"]) ==
                (model["amount"], model["missing"], model["fee"]),
                f"tripAmount parity failed for {trip_id}")
    require(rows[101]["other_fee_vnd"] is None and rows[102]["amount_vnd"] is None
            and rows[103]["event_date"] is None
            and call(pg, "get_ledger", 1)["pending_count"] == 1,
            "NULL storage or pending count wrong")
    c = new_book(pg, ("2026-01-01", 0))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    ids = call(pg, "paste_trips", c, 0, "space-container", current,
               trip_json(None, container="   ", month=current))["trip_ids"]
    call(pg, "edit_trip_price", c, 1, "space-fee", ids[0], None, 7)
    row = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == ids[0])
    require(row["is_fee_only"] is False and row["is_missing_price"] is True,
            "whitespace container differs from JS truthiness")
    require(any(m["month"] == current and m["outstanding_vnd"] == "0"
                for m in call(pg, "get_ledger", c)["months"]),
            "month with only missing-price trip absent")
    fee_only = json.dumps([{"container": None, "carrier": None, "date": None,
        "from": None, "to": None, "unitPriceVnd": None, "otherFeeVnd": "7",
        "note": "fee only", "src": "FAKE"}])
    fee_id = call(pg, "paste_trips", c, version(pg, c), "fee-no-date", current,
                  fee_only)["trip_ids"][0]
    fee_row = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == fee_id)
    require(fee_row["event_date"] is None and fee_row["amount_vnd"] == "7"
            and fee_row["is_fee_only"] is True, "undated fee was not entered and counted")
    require(any(m["month"] == current and m["outstanding_vnd"] == "7"
                for m in call(pg, "get_ledger", c)["months"]),
            "undated fee missing from month balance")
    normal = json.loads(trip_json())[0]
    normal["date"] = None
    reject_call(pg, "paste_trips", c, version(pg, c), "trip-no-date", current,
                json.dumps([normal]), error="INVALID_TRIP_INPUT")


def check_fee_intent_after_price(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 0))
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref VALUES ({cut},'BK1','FEE-BASE','2026-01-10')")
    call(pg, "set_month_lock", c, 0, "fee-open", "2026-01-01", "false")
    row = json.loads(trip_json(container="FEE-C"))[0] | {"date": "10/01/2026"}
    trip = call(pg, "paste_trips", c, version(pg, c), "fee-paste", "2026-01-01", json.dumps([row]))["trip_ids"][0]
    plus = call(pg, "adjust_trip", c, version(pg, c), "fee-plus", trip, None, "", "other_fee_vnd", 7)
    require(plus["delta_vnd"] == "7", "fee +7 delta wrong")
    call(pg, "edit_trip_price", c, version(pg, c), "fee-price", trip, 100, 30)
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "130", "price edit did not replace fee total")
    ten = call(pg, "adjust_trip", c, version(pg, c), "fee-ten", trip, None, "", "other_fee_vnd", 10)
    require(ten["delta_vnd"] == "-20" and call(pg, "get_ledger", c)["total_outstanding_vnd"] == "110",
            "fee intent must land on the effective fee after a price revision")


def check_sheet_cross_customer(pg: Pg) -> None:
    first = new_book(pg, ("2026-01-01", 100))
    second = new_book(pg, ("2026-01-01", 200))
    untagged = new_book(pg, ("2026-01-01", 300))
    today = pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    month = today[:7] + "-01"
    row = json.loads(trip_json(None, container="FAKE-CROSS-CUSTOMER"))[0]
    row.update(date=today[8:10] + "/" + today[5:7] + "/" + today[:4],
               src="sheet:" + "a" * 64 + ":2", unitPriceVnd=None, otherFeeVnd=None)
    before = call(pg, "get_ledger", first)["total_outstanding_vnd"]
    trip_id = call(pg, "paste_trips", first, version(pg, first), "sheet-first", month,
                   json.dumps([row]))["trip_ids"][0]
    ledger = call(pg, "get_ledger", first)
    saved = next(trip for trip in ledger["trips"] if trip["id"] == trip_id)
    require(ledger["total_outstanding_vnd"] == before and saved["unit_price_vnd"] is None
            and saved["amount_vnd"] is None, "NULL price changed balance")
    refs = json.loads(pg.value(actor_sql("SELECT sokhach.list_sheet_trip_refs()")))["items"]
    require(any(ref["customer_id"] == first and ref["container"] == "FAKE-CROSS-CUSTOMER"
                for ref in refs), "cross-customer reference missing")
    # Non-Sheet fixture rows may share a container; guard owns only Sheet imports.
    call(pg, "paste_trips", untagged, version(pg, untagged), "fixture-untagged", month,
         json.dumps([row | {"src": None}]))
    before_second = call(pg, "get_ledger", second)["total_outstanding_vnd"]
    reject_call(pg, "paste_trips", second, version(pg, second), "sheet-second", month,
                json.dumps([row | {"src": "sheet:" + "a" * 64 + ":3"}]), error="SHEET_CROSS_CUSTOMER_MATCH")
    require(call(pg, "get_ledger", second)["total_outstanding_vnd"] == before_second,
            "rejected cross-customer row changed balance")


def check_sheet_conflict_resolution(pg: Pg) -> None:
    c = new_book(pg, ("2026-09-01", 0))
    fixture_open_month(pg, c, "2026-09-01")
    row = json.loads(trip_json(container="FAKE-SHEET-DATE"))[0] | {"date": "15/09/2026", "booking": "BK-OLD"}
    trip_id = call(pg, "paste_trips", c, version(pg, c), "sheet-date-paste", "2026-09-01",
                   json.dumps([row]))["trip_ids"][0]
    before = call(pg, "get_ledger", c)
    sha = "a" * 64

    def resolve(key, field, target, sheet, decision, kind="trip", target_id=trip_id):
        return (c, version(pg, c), key, sha, 9, kind, target_id, field, target, sheet, decision)

    # Date and booking differences close as "keep web" only, without touching the trip or money.
    call(pg, "resolve_sheet_conflict", *resolve("keep-date", "event_date", "2026-09-15", "2026-09-20", "keep_web"))
    call(pg, "resolve_sheet_conflict", *resolve("keep-booking", "booking", "BK-OLD", "", "keep_web"))
    after = call(pg, "get_ledger", c)
    trip = next(t for t in after["trips"] if t["id"] == trip_id)
    require(trip["event_date"] == "2026-09-15" and trip["booking"] == "BK-OLD", "keep_web changed the trip")
    require(after["total_outstanding_vnd"] == before["total_outstanding_vnd"], "keep_web changed balance")
    events = [e for e in after["events"] if e["kind"] == "sheet_conflict_resolved"]
    require(sorted(e["after"]["field"] for e in events) == ["booking", "event_date"]
            and all(e["after"]["decision"] == "keep_web" for e in events), "resolution events missing")
    for key, args in [("date-sheet", resolve("x", "event_date", "2026-09-15", "2026-09-20", "use_sheet")),
                      ("booking-sheet", resolve("x", "booking", "BK-OLD", "BK-NEW", "use_sheet")),
                      ("booking-legacy", resolve("x", "booking", None, "BK-NEW", "keep_web", "legacy", 1))]:
        reject_call(pg, "resolve_sheet_conflict", *args[:2], key, *args[3:], error="INVALID_SHEET_RESOLUTION")
    # Taking the Sheet value now honours the month lock; keeping web stays allowed.
    pg.sql(f"UPDATE sokhach.month_state SET locked=true WHERE customer_id={c} AND month='2026-09-01'")
    reject_call(pg, "resolve_sheet_conflict", *resolve("locked-carrier", "carrier", "FAKE", "FAKE NEW", "use_sheet"),
                error="MONTH_LOCKED")
    call(pg, "resolve_sheet_conflict", *resolve("locked-keep", "carrier", "FAKE", "FAKE NEW", "keep_web"))
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == before["total_outstanding_vnd"],
            "locked resolution changed balance")
