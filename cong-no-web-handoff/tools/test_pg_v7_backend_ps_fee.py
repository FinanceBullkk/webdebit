"""Tách phụ phí theo PS (rewrite_trip_fees); run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    ROOT,
    call,
    fixture_open_month,
    new_book,
    reject_call,
    require,
    trip_json,
    version,
)

MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-ps-fee.sql"


def check_ps_fee(pg):
    # Earlier cases reapply older migrations that rebuild the event constraints; rerunning also proves idempotency.
    pg.sql(MIGRATION.read_text(encoding="utf-8"))
    pg.sql(MIGRATION.read_text(encoding="utf-8"))
    fee = {name: int(pg.value(f"SELECT id FROM sokhach.fee_type WHERE {cond}")) for name, cond in (
        ("neo", "name='Neo'"), ("dien", "name='Điện'"), ("other", "system_key='other'"),
        ("initial", "system_key='initial'"), ("discount", "system_key='discount'"))}
    c = new_book(pg, ("2026-01-01", 100))
    fixture_open_month(pg, c, "2026-01-01")
    rows = []
    for name in ("PS-1", "PS-PENDING"):
        row = json.loads(trip_json(container=name))[0]
        row.update(booking=name, otherFeeVnd="2000")
        rows.append(row)
    trip, pending_source = call(pg, "paste_trips", c, 0, "ps-paste", "2026-01-01", json.dumps(rows))["trip_ids"]
    pending = call(pg, "paste_trips", c, version(pg, c), "ps-pending", "2026-01-01", json.dumps([rows[1]]))["trip_ids"][0]
    require(pending != pending_source, "duplicate paste did not create a second trip")
    balances = f"SELECT jsonb_agg(to_jsonb(v) ORDER BY debt_month) FROM sokhach.v_outstanding_month v WHERE customer_id={c}"
    before_money = pg.value(balances)

    def lines_of(trip_id):
        return next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip_id)["fee_lines"]

    old = lines_of(trip)
    require([(x["fee_type_id"], x["amount_vnd"]) for x in old] == [(fee["other"], "2000")], "paste fee fixture")
    target, ids = json.dumps({"trip_id": trip}), json.dumps([x["id"] for x in old])
    plan = json.dumps([{"fee_type_id": fee["neo"], "amount_vnd": "1500"},
                       {"fee_type_id": fee["dien"], "amount_vnd": 500, "note": " PS ghi chú "}])
    source = json.dumps({"kind": "ps", "key": "FAKE|2026-01-01", "snapshot_sha256": "a" * 64})
    pg.sql("CREATE TABLE public.ps_calls(n int); INSERT INTO public.ps_calls VALUES(0); "
           "ALTER FUNCTION sokhach.reallocate(bigint,text) RENAME TO ps_original_reallocate; "
           "CREATE FUNCTION sokhach.reallocate(bigint,text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$ "
           "BEGIN UPDATE public.ps_calls SET n=n+1; RETURN sokhach.ps_original_reallocate($1,$2); END $$")
    try:
        v = version(pg, c)
        result = call(pg, "rewrite_trip_fees", c, v, "ps-rewrite", target, ids, plan, source)
        require(pg.value("SELECT n FROM public.ps_calls") == "0", "rewrite reallocated receipts")
    finally:
        pg.sql("DROP FUNCTION sokhach.reallocate(bigint,text); "
               "ALTER FUNCTION sokhach.ps_original_reallocate(bigint,text) RENAME TO reallocate; DROP TABLE public.ps_calls")
    require(pg.value(balances) == before_money, "rewrite changed money")
    after = lines_of(trip)
    require(sorted((x["fee_type_id"], x["amount_vnd"], x["note"]) for x in after)
            == sorted([(fee["neo"], "1500", None), (fee["dien"], "500", "PS ghi chú")]), "rewrite lines")
    require(next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == trip)["other_fee_vnd"] == "2000",
            "fee cache changed")
    event = json.loads(pg.value(f"SELECT jsonb_build_object('kind',kind,'after',\"after\") FROM sokhach.event "
                                f"WHERE id={result['event_id']}"))
    require(event["kind"] == "rewrite_trip_fees" and event["after"]["source"]["kind"] == "ps", "event source")
    pg.true(f"(SELECT voided_by_event={result['event_id']} FROM sokhach.trip_fee_line WHERE id={old[0]['id']})",
            "old line not voided by the rewrite event")
    require(call(pg, "rewrite_trip_fees", c, v, "ps-rewrite", target, ids, plan, source) == result, "retry changed")
    reject_call(pg, "rewrite_trip_fees", c, v, "ps-rewrite", target, ids, "[]", source, error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "rewrite_trip_fees", c, v, "ps-stale", target, ids, plan, source, error="VERSION_CONFLICT")
    now = json.dumps([x["id"] for x in after])

    def reject(key, lines, error, expected=now, book=c, selected=target):
        reject_call(pg, "rewrite_trip_fees", book, version(pg, book), key, selected, expected, json.dumps(lines),
                    source, error=error)
    two = [{"fee_type_id": fee["neo"], "amount_vnd": "1000"}, {"fee_type_id": fee["other"], "amount_vnd": "1000"}]
    reject("ps-old-ids", two, "FEE_LINES_CHANGED", expected=ids)
    reject("ps-total", [{"fee_type_id": fee["neo"], "amount_vnd": "2001"}], "FEE_TOTAL_CHANGED")
    reject("ps-initial", [{"fee_type_id": fee["initial"], "amount_vnd": "2000"}], "FEE_TYPE_SYSTEM")
    reject("ps-zero", [{"fee_type_id": fee["neo"], "amount_vnd": "0"}, *two], "FEE_AMOUNT_INVALID")
    reject("ps-sign", [{"fee_type_id": fee["discount"], "amount_vnd": "5"}], "FEE_SIGN_INVALID")
    reject("ps-key", [{"fee_type_id": fee["neo"], "amount_vnd": "2000", "x": 1}], "INVALID_COMMAND")
    reject("ps-many", [{"fee_type_id": fee["neo"], "amount_vnd": "200"}] * 10 + [{"fee_type_id": fee["neo"], "amount_vnd": "0"}],
           "INVALID_COMMAND")
    reject("ps-same", [{"fee_type_id": fee["dien"], "amount_vnd": "500", "note": "PS ghi chú"},
                       {"fee_type_id": fee["neo"], "amount_vnd": "1500"}], "NO_CHANGE")
    pending_ids = json.dumps([x["id"] for x in lines_of(pending)])
    reject("ps-pending-split", [{"fee_type_id": fee["neo"], "amount_vnd": "2000"}], "TRIP_PENDING_REVIEW",
           expected=pending_ids, selected=json.dumps({"trip_id": pending}))
    stranger = new_book(pg, ("2026-01-01", 1))
    reject("ps-stranger", two, "TRIP_NOT_FOUND", book=stranger)
    locked_row = {**rows[0], "booking": "PS-LOCKED", "container": "PS-LOCKED", "date": "01/02/2026"}
    locked = call(pg, "paste_trips", c, version(pg, c), "ps-locked-paste", "2026-02-01",
                  json.dumps([locked_row]))["trip_ids"][0]
    reject("ps-locked", [{"fee_type_id": fee["neo"], "amount_vnd": "2000"}], "MONTH_LOCKED",
           expected=json.dumps([x["id"] for x in lines_of(locked)]), selected=json.dumps({"trip_id": locked}))

    # Dòng sổ gốc có TOTAL lệch đơn giá + phí: tách giữ nguyên counted_vnd, không ghi revision hay điều chỉnh.
    book = new_book(pg, ("2026-01-01", 999))
    fixture_open_month(pg, book, "2026-01-01")
    imported = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={book} AND kind='import'")
    legacy = pg.value("BEGIN; SET LOCAL ROLE sokhach_owner; "
        "ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,source_row,created_by_event) "
        f"SELECT {book},cutover_id,'2026-01-01','trip','{{\"container\":\"PS-LEGACY\",\"unit_price\":\"100\",\"fee_vnd\":\"5\"}}',999,'FAKE',7,{imported} "
        f"FROM sokhach.cutover_customer WHERE customer_id={book} RETURNING id; "
        "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.trip_fee_line(customer_id,legacy_row_id,fee_type_id,amount_vnd,created_by_event) "
        f"SELECT {book},currval(pg_get_serial_sequence('sokhach.legacy_row','id')),{fee['other']},5,{imported}; COMMIT").splitlines()[0]
    legacy_money = ("SELECT jsonb_build_array((SELECT jsonb_agg(to_jsonb(v) ORDER BY debt_month) FROM sokhach.v_outstanding_month v "
                    f"WHERE customer_id={book}),(SELECT count(*) FROM sokhach.legacy_trip_rev WHERE legacy_row_id={legacy}),"
                    f"(SELECT count(*) FROM sokhach.adjustment WHERE legacy_row_id={legacy}))")
    before_legacy = pg.value(legacy_money)

    def legacy_row():
        return next(r for r in call(pg, "get_ledger", book)["legacy_rows"] if r["id"] == int(legacy))
    row = legacy_row()
    require(row["counted_differs"] is True and row["current"]["counted_vnd"] == "999", "legacy fixture")
    call(pg, "rewrite_trip_fees", book, version(pg, book), "ps-legacy", json.dumps({"legacy_row_id": int(legacy)}),
         json.dumps([x["id"] for x in row["fee_lines"]]), json.dumps([{"fee_type_id": fee["neo"], "amount_vnd": "5"}]), source)
    row = legacy_row()
    require(row["current"]["counted_vnd"] == "999" and row["counted_differs"] is True, "legacy TOTAL changed")
    require([(x["fee_type_id"], x["amount_vnd"]) for x in row["fee_lines"]] == [(fee["neo"], "5")], "legacy lines")
    require(pg.value(legacy_money) == before_legacy, "legacy rewrite wrote money rows")
    pg.true("(SELECT has_function_privilege('v7_app','sokhach.rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb)','EXECUTE')"
            " AND NOT has_function_privilege('v7_app','sokhach._rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb)','EXECUTE'))",
            "rewrite grants")
