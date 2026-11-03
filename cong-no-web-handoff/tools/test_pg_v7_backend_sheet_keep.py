"""Keep Sheet tasks changes audit metadata only; run through disposable V7 harness."""
import json

from pg_v7_harness import (
    ROOT,
    call,
    fixture_open_month,
    months,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)


def check_sheet_keep(pg):
    customer = new_book(pg, ("2026-01-01", 100))
    fixture_open_month(pg, customer, "2026-01-01")
    trip = call(pg, "paste_trips", customer, version(pg, customer), "keep-paste", "2026-01-01", trip_json())["trip_ids"][0]
    before = months(pg, customer)
    current = {"unit_price_vnd": "100", "other_fee_vnd": None}
    args = (customer, version(pg, customer), "keep-price", "price", "trip", trip, "a" * 64, json.dumps(current))
    result = call(pg, "keep_sheet_task", *args)
    require(result["kept"] and call(pg, "keep_sheet_task", *args) == result, "keep retry changed result")
    require(months(pg, customer) == before, "keep changed money")
    event = call(pg, "get_ledger", customer)["events"][0]
    require(event["kind"] == "sheet_conflict_resolved" and event["after"]["target_value"] == current,
            "keep audit missing")
    reject_call(pg, "keep_sheet_task", *args[:-1], json.dumps({**current, "unit_price_vnd": "101"}), error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "keep_sheet_task", customer, version(pg, customer), "bad-state", "price", "trip", trip,
                "a" * 64, json.dumps({**current, "unit_price_vnd": "101"}), error="STALE_LEDGER")
    for index, (kind, target, ident) in enumerate(((None, "trip", trip), ("removed", "legacy", trip), ("price", None, trip), ("price", "trip", None))):
        reject_call(pg, "keep_sheet_task", customer, version(pg, customer), f"bad-{index}", kind, target, ident,
                    "a" * 64, json.dumps(current), error="INVALID_SHEET_RESOLUTION")
    migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-11-02-v7-giu-viec-sheet.sql").read_text(encoding="utf-8")
    catalog = "SELECT pg_get_functiondef('sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb)'::regprocedure)"
    original = pg.value(catalog)
    pg.sql(migration)
    pg.sql(migration)
    require(pg.value(catalog) == original, "migration changed canonical definition")
    pg.true("NOT has_function_privilege('sokhach_reader','sokhach.keep_sheet_task(bigint,bigint,text,text,text,bigint,text,jsonb)','EXECUTE')", "reader can keep")
    desired = {"unit_price_vnd": "120", "other_fee_vnd": "5"}
    apply_args = (customer, version(pg, customer), "apply-sheet", "trip", trip, "b" * 64, json.dumps(current), json.dumps(desired))
    applied = call(pg, "apply_sheet_price", *apply_args)
    require(call(pg, "apply_sheet_price", *apply_args) == applied, "apply price retry changed result")
    after_trip = next(t for t in call(pg, "get_ledger", customer)["trips"] if t["id"] == trip)
    require(after_trip["unit_price_vnd"] == "120" and after_trip["other_fee_vnd"] == "5", "Sheet price not applied")
    from test_pg_v7_backend_khoa_chu import _legacy, _lock
    _lock(pg, customer, "2026-01-01")
    reject_call(pg, "apply_sheet_price", customer, version(pg, customer), "locked-price", "trip", trip,
                "c" * 64, json.dumps(desired), json.dumps(current), error="MONTH_LOCKED")
    # Keeping metadata remains allowed in a locked month.
    call(pg, "keep_sheet_task", customer, version(pg, customer), "keep-locked", "price", "trip", trip,
         "c" * 64, json.dumps(desired))
    fixture_open_month(pg, customer, "2026-01-01")
    legacy = _legacy(pg, customer, {"container": "FAKE-L", "date": "2026-01-05", "unit_price": "100"}, 31)
    legacy_current = next(r for r in call(pg, "get_ledger", customer)["legacy_rows"] if r["id"] == legacy)["current"]
    old = {k: legacy_current.get(k) for k in ("unit_price_vnd", "other_fee_vnd")}
    call(pg, "apply_sheet_price", customer, version(pg, customer), "legacy-sheet", "legacy", legacy,
         "d" * 64, json.dumps(old), json.dumps(desired))
    legacy_after = next(r for r in call(pg, "get_ledger", customer)["legacy_rows"] if r["id"] == legacy)["current"]
    require(legacy_after["unit_price_vnd"] == "120" and legacy_after["other_fee_vnd"] == "5", "legacy Sheet price not applied")
    before_commodity = months(pg, customer)
    commodity_args = (customer, version(pg, customer), "commodity-test", "Dừa")
    commodity = call(pg, "set_customer_commodity", *commodity_args)
    require(call(pg, "set_customer_commodity", *commodity_args) == commodity, "commodity retry changed result")
    require(months(pg, customer) == before_commodity, "commodity changed money")
    reject_call(pg, "set_customer_commodity", customer, version(pg, customer), "replace-commodity", "Chuối", error="STALE_LEDGER")
    reject_call(pg, "set_customer_commodity", customer, version(pg, customer), "bad-commodity", "", error="INVALID_COMMAND")
    target = new_book(pg, ("2026-01-01", 50))
    fixture_open_month(pg, target, "2026-01-01")
    row = {"source_row": 41, "container": "FAKE-ASSIGNED", "event_date": "2026-01-02", "carrier": "FAKE",
           "origin": "FAKE-A", "destination": "FAKE-B", "booking": ""}
    assign_args = (customer, version(pg, customer), "assign-test", target, version(pg, target), "e" * 64, json.dumps(row))
    source_money, target_money = months(pg, customer), months(pg, target)
    assigned = call(pg, "assign_sheet_trip", *assign_args)
    require(call(pg, "assign_sheet_trip", *assign_args) == assigned, "assignment retry changed result")
    require(months(pg, customer) == source_money and months(pg, target) == target_money, "unpriced assignment changed money")
    assigned_trip = next(t for t in call(pg, "get_ledger", target)["trips"] if t["id"] == assigned["trip_id"])
    require(assigned_trip["unit_price_vnd"] is None, "assignment invented a price")
    reject_call(pg, "assign_sheet_trip", customer, version(pg, customer), "stale-target", target, 0,
                "f" * 64, json.dumps({**row, "container": "FAKE-OTHER"}), error="STALE_LEDGER")
    legacy_total = _legacy(pg, customer, {"container": "FAKE-TOTAL", "date": "2026-01-05", "unit_price": "25"}, 32)
    before_undo = months(pg, customer)
    receipt_key, price_key, legacy_key = "1" * 64, "2" * 64, "3" * 64
    call(pg, "record_receipt", customer, version(pg, customer), receipt_key, "2026-01-03", "THU TIỀN", 20, "FAKE")
    call(pg, "edit_trip_price", customer, version(pg, customer), price_key, trip, 300, 7)
    call(pg, "edit_legacy_trip", customer, version(pg, customer), legacy_key, legacy_total, "unit_price_vnd", "200")
    undo_args = (customer, version(pg, customer), "undo-test", json.dumps([receipt_key, price_key, legacy_key]))
    undone = call(pg, "undo_sheet_batch", *undo_args)
    require(call(pg, "undo_sheet_batch", *undo_args) == undone, "undo retry changed result")
    require(months(pg, customer) == before_undo, "undo did not restore exact month balances")
    restored = next(r for r in call(pg, "get_ledger", customer)["legacy_rows"] if r["id"] == legacy_total)["current"]
    require(restored["unit_price_vnd"] == "25" and restored["counted_vnd"] == "100", "undo lost original Sheet TOTAL")
    receipt = next(r for r in call(pg, "get_ledger", customer)["receipts"] if r["reference"] == "FAKE")
    require(receipt["voided_by_event"] is not None and receipt["void_reason"], "undo lost receipt void audit")
    reject_call(pg, "undo_sheet_batch", customer, 0, "undo-stale", json.dumps([receipt_key]), error="STALE_LEDGER")
    reject_call(pg, "undo_sheet_batch", customer, version(pg, customer), "undo-unknown", json.dumps(["4" * 64]), error="INVALID_COMMAND")
    return "keep/retry/audit, unchanged balances, stale state, invalid/null targets, migration rerun, reader denied"
