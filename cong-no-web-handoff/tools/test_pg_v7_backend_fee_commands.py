"""PR-B behavior; run only through disposable test_pg_v7_backend.py harness."""
import json

from pg_v7_harness import (
    ROOT,
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


def check_fee_commands(pg):
    c = new_book(pg, ("2026-01-01", 100))
    fixture_open_month(pg, c, "2026-01-01")
    rows = [json.loads(trip_json(container=f"FEE-{i}"))[0] for i in range(20)]
    for i, row in enumerate(rows):
        row["booking"] = f"FEE-{i}"
    ids = call(pg, "paste_trips", c, 0, "fee-paste", "2026-01-01", json.dumps(rows))["trip_ids"]
    targets = json.dumps([{"trip_id": i} for i in ids])
    ft = call(pg, "add_fee_type", "fee-new-type", "FAKE FEE", "service")["id"]
    other = int(pg.value("SELECT id FROM sokhach.fee_type WHERE system_key='other'"))
    initial = int(pg.value("SELECT id FROM sokhach.fee_type WHERE system_key='initial'"))
    discount = int(pg.value("SELECT id FROM sokhach.fee_type WHERE system_key='discount'"))
    # Count actual reallocate invocations without changing its money behavior.
    pg.sql("CREATE TABLE public.fee_calls(n int); INSERT INTO public.fee_calls VALUES(0); "
           "ALTER FUNCTION sokhach.reallocate(bigint,text) RENAME TO fee_original_reallocate; "
           "CREATE FUNCTION sokhach.reallocate(bigint,text) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER AS $$ "
           "BEGIN UPDATE public.fee_calls SET n=n+1; RETURN sokhach.fee_original_reallocate($1,$2); END $$")
    try:
        before = int(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}"))
        result = call(pg, "add_trip_fees", c, 1, "fee-batch", targets, ft, 10, "batch")
        require(pg.value("SELECT n FROM public.fee_calls") == "1", "batch did not allocate exactly once")
        require(int(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == before + 1, "batch event count")
        require(len(result["targets"]) == 20, "batch incomplete")
    finally:
        pg.sql("DROP FUNCTION sokhach.reallocate(bigint,text); ALTER FUNCTION sokhach.fee_original_reallocate(bigint,text) RENAME TO reallocate; DROP TABLE public.fee_calls")
    require(call(pg, "add_trip_fees", c, 1, "fee-batch", targets, ft, 10, "batch") == result, "batch retry changed")
    reject_call(pg, "add_trip_fees", c, version(pg, c), "fee-batch", targets, ft, 11, "batch", error="IDEMPOTENCY_CONFLICT")
    target = json.dumps({"trip_id": ids[0]})
    def add(key, amount=5, type_id=ft, book=c, selected=targets):
        return call(pg, "add_trip_fees", book, version(pg, book), key, selected, type_id, amount, None)
    def reject(key, error, amount=5, type_id=ft, book=c, selected=targets):
        reject_call(pg, "add_trip_fees", book, version(pg, book), key, selected, type_id, amount, None, error=error)
    add("fee-duplicate-type", selected=json.dumps([{"trip_id": ids[0]}]))
    call(pg, "set_trip_fee_type", c, version(pg, c), "fee-set", target, ft, 7)
    require(pg.value(f"SELECT count(*) FROM sokhach.trip_fee_line WHERE trip_id={ids[0]} AND fee_type_id={ft} AND voided_by_event IS NULL") == "1", "set kept old same-type lines")
    line = int(pg.value(f"SELECT id FROM sokhach.trip_fee_line WHERE trip_id={ids[0]} AND voided_by_event IS NULL"))
    call(pg, "replace_trip_fee", c, version(pg, c), "fee-replace", line, other, 7, "same total")
    require(next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == ids[0])["other_fee_vnd"] == "7", "replace changed total")
    line = int(pg.value(f"SELECT id FROM sokhach.trip_fee_line WHERE trip_id={ids[0]} AND voided_by_event IS NULL"))
    v = version(pg, c)
    voided = call(pg, "void_trip_fee", c, v, "fee-void", line)
    require(call(pg, "void_trip_fee", c, v, "fee-void", line) == voided, "void retry failed")
    for key, book in (("fee-void-again", c), ("fee-void-stranger", new_book(pg, ("2026-01-01", 1)))):
        reject_call(pg, "void_trip_fee", book, version(pg, book), key, line, error="FEE_LINE_NOT_FOUND")
    reject_call(pg, "replace_trip_fee", c, version(pg, c), "fee-replace-voided", line, other, 7, None, error="FEE_LINE_NOT_FOUND")
    for key, amount, type_id, error in [("zero", 0, ft, "FEE_AMOUNT_INVALID"), ("sign", -1, ft, "FEE_SIGN_INVALID"),
                                       ("discount-sign", 1, discount, "FEE_SIGN_INVALID"), ("system", 1, initial, "FEE_TYPE_SYSTEM"),
                                       ("overflow", 9223372036854775808, ft, "out of range")]:
        reject(key, error, amount, type_id)
    # Sum overflow, not only bigint argument conversion.
    reject("sum-overflow", "FEE_AMOUNT_INVALID", 9223372036854775807, selected=json.dumps([{ "trip_id": ids[1]}]))
    reject_call(pg, "add_trip_fees", c, 0, "stale", targets, ft, 1, None, error="VERSION_CONFLICT")
    stranger = new_book(pg, ("2026-01-01", 1))
    reject("cross-customer", "TRIP_NOT_FOUND", book=stranger)
    locked = call(pg, "paste_trips", c, version(pg, c), "locked-paste", "2026-02-01",
                  json.dumps([{**rows[0], "booking": "FEE-LOCKED", "container": "FEE-LOCKED", "date": "01/02/2026"}]))["trip_ids"][0]
    reject("locked-batch", "MONTH_LOCKED", selected=json.dumps([{"trip_id": i} for i in ids] + [{"trip_id": locked}]))
    require(pg.value(f"SELECT count(*) FROM sokhach.trip_fee_line WHERE customer_id={c} AND created_by_event IN (SELECT id FROM sokhach.event WHERE idempotency_key='locked-batch')") == "0", "locked batch leaked")
    pending = call(pg, "paste_trips", c, version(pg, c), "pending-paste", "2026-01-01", json.dumps([rows[0]]))["trip_ids"][0]
    reject("pending", "TRIP_PENDING_REVIEW", selected=json.dumps([{"trip_id": pending}]))
    ledger_line = next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == ids[1])["fee_lines"][0]
    require(set(ledger_line) == {"id", "fee_type_id", "amount_vnd", "note"}
            and ledger_line["fee_type_id"] == ft and ledger_line["amount_vnd"] == "10"
            and ledger_line["note"] == "batch", "ledger fee line contract")
    call(pg, "set_trip_fee_type", c, version(pg, c), "clear-fee-cell", json.dumps({"trip_id": ids[2]}), ft, None)
    require(next(t for t in call(pg, "get_ledger", c)["trips"] if t["id"] == ids[2])["fee_lines"] == [], "NULL did not clear type")
    # Every successful command commits deferred cache checks; additionally compare every trip.
    pg.true("NOT EXISTS(SELECT 1 FROM sokhach.v_trip_current t LEFT JOIN LATERAL (SELECT sum(amount_vnd)::bigint total FROM sokhach.trip_fee_line WHERE trip_id=t.id AND voided_by_event IS NULL) f ON true WHERE (SELECT other_fee_vnd FROM sokhach.trip_price_rev WHERE trip_id=t.id ORDER BY id DESC LIMIT 1) IS DISTINCT FROM f.total)", "FEE_CACHE_MISMATCH")


def check_fee_catalog(pg):
    result = call(pg, "add_fee_type", "catalog-key", "FAKE CATALOG", "service", actor="catalog-actor")
    ft = result["id"]
    require(call(pg, "add_fee_type", "catalog-key", "FAKE CATALOG", "service") == result, "catalog retry")
    reject_call(pg, "add_fee_type", "catalog-key", "changed", "service", error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "add_fee_type", "catalog-duplicate", " fake catalog ", "service", error="FEE_TYPE_DUPLICATE")
    call(pg, "rename_fee_type", "catalog-rename", ft, "FAKE RENAMED")
    call(pg, "set_fee_type_kind", "catalog-kind", ft, "pass_through")
    call(pg, "set_fee_type_active", "catalog-off", ft, False)
    require(pg.value(f"SELECT actor FROM sokhach.fee_type_audit WHERE fee_type_id={ft} ORDER BY id LIMIT 1") == "catalog-actor", "catalog actor")
    c = new_book(pg, ("2026-01-01", 1))
    reject_call(pg, "set_book_fee_columns", c, 0, "inactive-column", json.dumps([ft]), error="FEE_TYPE_INACTIVE")
    call(pg, "set_fee_type_active", "catalog-on", ft, True)
    other = int(pg.value("SELECT id FROM sokhach.fee_type WHERE system_key='other'"))
    call(pg, "set_book_fee_columns", c, 0, "columns", json.dumps([other, ft]))
    require([x["fee_type_id"] for x in call(pg, "get_ledger", c)["fee_columns"]] == [other, ft], "column order")
    reject_call(pg, "set_book_fee_columns", c, version(pg, c), "four-columns", "[1,2,3,4]", error="FEE_COLUMNS_MAX")
    reject_call(pg, "set_book_fee_columns", c, version(pg, c), "duplicate-columns", json.dumps([ft, ft]), error="INVALID_COMMAND")
    for name, value in (("rename_fee_type", "SYSTEM"), ("set_fee_type_kind", "pass_through"), ("set_fee_type_active", False)):
        reject_call(pg, name, "system-" + name, other, value, error="FEE_TYPE_SYSTEM")
    call(pg, "set_book_fee_columns", c, version(pg, c), "no-columns", "[]")
    require(call(pg, "get_ledger", c)["fee_columns"] == [], "zero columns")
    for name in ("trip_fee_line", "fee_type", "book_fee_column", "fee_type_audit"):
        pg.rejects(f"INSERT INTO sokhach.{name} DEFAULT VALUES", user="v7_app", message="permission denied")
    for name in ("add_trip_fees", "set_trip_fee_type", "replace_trip_fee", "void_trip_fee", "add_fee_type", "rename_fee_type", "set_fee_type_kind", "set_fee_type_active", "set_book_fee_columns", "get_fee_types"):
        pg.true(f"(SELECT has_function_privilege('v7_app',oid,'EXECUTE') FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname={lit(name)})", "new command not executable")
    require(json.loads(pg.value(actor_sql("SELECT sokhach.get_fee_types()"), user="v7_app"))["fee_types"], "app catalog read")
    # Migration reruns preserve financial rows and definitions.
    migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-phu-phi-b.sql").read_text(encoding="utf-8")
    snapshot = pg.value("SELECT jsonb_agg(to_jsonb(v) ORDER BY customer_id,debt_month) FROM sokhach.v_outstanding_month v")
    p2 = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-phu-phi-b-p2.sql").read_text(encoding="utf-8")
    chung_tu = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-chung-tu.sql").read_text(encoding="utf-8")
    for _ in range(2):
        pg.sql(migration)
        pg.sql(p2)
    # Later migrations rewrite the same event constraints; reapply them so the shared DB stays canonical.
    pg.sql((ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-bang-gia.sql").read_text(encoding="utf-8"))
    pg.sql(chung_tu)  # PR-B dựng lại ràng buộc event; CHUNG-TU-01 phải chạy sau như khi triển khai
    require(pg.value("SELECT jsonb_agg(to_jsonb(v) ORDER BY customer_id,debt_month) FROM sokhach.v_outstanding_month v") == snapshot, "migration changed money")
