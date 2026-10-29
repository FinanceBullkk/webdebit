"""V7 backend harness cases: Receipts: record, idempotency, atomicity, concurrency, void, snapshots, receipt date.

Run through test_pg_v7_backend.py."""

from __future__ import annotations

import json
import time

from pg_v7_harness import (
    Pg,
    PsqlSession,
    allocations,
    assert_allocations,
    call,
    cutover_book,
    fixture_open_month,
    import_data,
    lit,
    months,
    new_book,
    reject_call,
    require,
    run_node,
    trip_json,
    version,
)


def check_idempotency(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    first = call(pg, "record_receipt", c, 0, "idem-1", "2026-02-01", "THU TIỀN", 60)
    require(first["version"] == 1 and first["pid"] == "PH-001", "first receipt result wrong")
    require(call(pg, "record_receipt", c, 0, "idem-1", "2026-02-01", "THU TIỀN", 60) == first,
            "same-key retry changed result")
    require(version(pg, c) == 1 and pg.value(f"SELECT count(*) FROM sokhach.receipt WHERE customer_id={c}") == "1",
            "same-key retry wrote again")
    reject_call(pg, "record_receipt", c, 0, "idem-1", "2026-02-01", "THU TIỀN", 61,
                error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "record_receipt", c, 0, "idem-2", "2026-02-01", "THU TIỀN", 1,
                error="STALE_LEDGER")
    require(months(pg, c)[0][1] == "40", "idempotency changed balance")


def check_atomic(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    pg.sql("""CREATE FUNCTION public.fail_second_allocation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NEW.debt_month='2026-02-01' THEN RAISE EXCEPTION 'HARNESS_FAIL_SECOND_LINE'; END IF;
RETURN NEW; END $$;
CREATE TRIGGER harness_fail_second_allocation BEFORE INSERT ON sokhach.receipt_line
FOR EACH ROW EXECUTE FUNCTION public.fail_second_allocation()""")
    try:
        reject_call(pg, "record_receipt", c, 0, "atomic-1", "2026-03-01", "THU TIỀN", 100,
                    error="HARNESS_FAIL_SECOND_LINE")
        for table in ("receipt", "receipt_line", "idempotency"):
            require(pg.value(f"SELECT count(*) FROM sokhach.{table} WHERE customer_id={c}") == "0",
                    f"atomic failure left {table}")
        require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND kind='receipt'") == "0"
                and version(pg, c) == 0 and [r[1] for r in months(pg, c)] == ["60", "60"],
                "atomic failure left event/version/balance")
    finally:
        pg.sql("DROP TRIGGER harness_fail_second_allocation ON sokhach.receipt_line; "
               "DROP FUNCTION public.fail_second_allocation()")
    call(pg, "record_receipt", c, 0, "atomic-base", "2026-03-01", "THU TIỀN", 100)
    fixture_open_month(pg, c, "2026-01-01")
    before = (version(pg, c), months(pg, c), allocations(pg, c, "PH-001"),
              pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}"))
    pg.sql("CREATE FUNCTION public.fail_reallocation() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'HARNESS_REALLOCATE_ABORT'; END $$; "
           "CREATE TRIGGER harness_fail_reallocation BEFORE INSERT ON sokhach.receipt_line "
           "FOR EACH ROW EXECUTE FUNCTION public.fail_reallocation()")
    try:
        reject_call(pg, "adjust_month", c, 1, "atomic-reallocate", "2026-01-01", 20,
                    "sửa", error="HARNESS_REALLOCATE_ABORT")
        require((version(pg, c), months(pg, c), allocations(pg, c, "PH-001"),
                 pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == before,
                "reallocate insert failure left partial state")
    finally:
        pg.sql("DROP TRIGGER harness_fail_reallocation ON sokhach.receipt_line; "
               "DROP FUNCTION public.fail_reallocation()")
    pg.sql("CREATE FUNCTION public.fail_finish() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'HARNESS_FINISH_ABORT'; END $$; "
           "CREATE TRIGGER harness_fail_finish BEFORE INSERT ON sokhach.idempotency "
           "FOR EACH ROW EXECUTE FUNCTION public.fail_finish()")
    try:
        reject_call(pg, "adjust_month", c, 1, "atomic-finish", "2026-01-01", 20,
                    "sửa", error="HARNESS_FINISH_ABORT")
        require((version(pg, c), months(pg, c), allocations(pg, c, "PH-001"),
                 pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == before,
                "finish failure left partial state")
    finally:
        pg.sql("DROP TRIGGER harness_fail_finish ON sokhach.idempotency; "
               "DROP FUNCTION public.fail_finish()")


def check_invariant_rejections(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 0))
    call(pg, "record_receipt", c, 0, "invariant-receipt", "2026-03-01", "THU TIỀN", 120)
    line = pg.value(f"SELECT id FROM sokhach.receipt_line WHERE customer_id={c} AND kind='debt'")
    advance = pg.value(f"SELECT id FROM sokhach.receipt_line WHERE customer_id={c} AND kind='advance'")
    def reject_corruption(change: str, error: str) -> None:
        pg.rejects("BEGIN; ALTER TABLE sokhach.receipt_line DISABLE TRIGGER receipt_line_guard; "
                   + change + f"; SELECT sokhach._check_allocations({c})", message=error)
        assert_allocations(pg, c)
    reject_corruption(f"UPDATE sokhach.receipt_line SET amount_vnd=99 WHERE id={line}",
                      "ALLOCATION_INVARIANT")
    reject_corruption(f"UPDATE sokhach.receipt_line SET debt_month='2026-01-01' WHERE id={advance}",
                      "ADVANCE_MONTH_INVARIANT")
    bad_event = pg.value(f"INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
                         f"VALUES ({c},'paste','harness','{{}}','{{\"trips\":[]}}') RETURNING id")
    reject_corruption(f"UPDATE sokhach.receipt_line SET created_by_event={bad_event} WHERE id={line}",
                      "ALLOCATION_EVENT_INVARIANT")


def check_void(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    first = call(pg, "record_receipt", c, 0, "void-r1", "2026-03-01", "THU TIỀN", 100)
    call(pg, "record_receipt", c, 1, "void-r2", "2026-03-02", "THU TIỀN", 10)
    before = allocations(pg, c, first["pid"])
    other = allocations(pg, c, "PH-002")
    require(before == [("2026-01-01", "debt", "60"), ("2026-02-01", "debt", "40")],
            "void setup lacks two months")
    reject_call(pg, "void_receipt", c, 2, "void-blank", first["pid"], " ", error="VOID_REASON_REQUIRED")
    pg.sql("""CREATE FUNCTION public.fail_second_void() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF OLD.debt_month='2026-02-01' THEN RAISE EXCEPTION 'HARNESS_FAIL_SECOND_VOID'; END IF;
RETURN NEW; END $$;
CREATE TRIGGER harness_fail_second_void BEFORE UPDATE ON sokhach.receipt_line
FOR EACH ROW EXECUTE FUNCTION public.fail_second_void()""")
    try:
        reject_call(pg, "void_receipt", c, 2, "void-fault", first["pid"], "sai",
                    error="HARNESS_FAIL_SECOND_VOID")
        require(allocations(pg, c, first["pid"]) == before and version(pg, c) == 2
                and pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND kind='void'") == "0",
                "void failure left first closed line or event")
    finally:
        pg.sql("DROP TRIGGER harness_fail_second_void ON sokhach.receipt_line; "
               "DROP FUNCTION public.fail_second_void()")
    result = call(pg, "void_receipt", c, 2, "void-ok", first["pid"], "sai phiếu")
    require(result["voided_lines"] == 2 and allocations(pg, c, first["pid"]) == []
            and allocations(pg, c, "PH-002") == other, "void touched wrong lines")
    pg.true("(SELECT count(*)=2 AND count(DISTINCT l.superseded_by_event)=1 "
        "AND bool_and(e.kind='void' AND e.\"before\"->'allocations' @> "
        "jsonb_build_array(jsonb_build_object('id',l.id,'month',l.debt_month,'kind',l.kind,"
        "'amount_vnd',l.amount_vnd::text))) FROM sokhach.receipt_line l "
        "JOIN sokhach.receipt r ON r.id=l.receipt_id "
        "JOIN sokhach.event e ON e.id=l.superseded_by_event "
        f"WHERE r.customer_id={c} AND r.pid='PH-001')", "void event/snapshot misses original ID")
    pg.true("(SELECT e.\"after\"->'allocations'='[]'::jsonb "
        "AND e.\"after\"->>'void_reason'='sai phiếu' "
        "AND r.voided_on IS NOT NULL AND r.voided_by_event=e.id "
        "FROM sokhach.receipt r JOIN sokhach.event e ON e.id=r.voided_by_event "
        f"WHERE r.customer_id={c} AND r.pid='PH-001')", "void after snapshot or receipt state wrong")
    # DA-THU-01: tháng 3 (ngày thu PH-002) có dòng tháng riêng, nợ kỳ 0.
    require([r[1] for r in months(pg, c)] == ["60", "50", "0"], "void balance wrong")
    reject_call(pg, "void_receipt", c, 3, "void-again", first["pid"], "lại", error="RECEIPT_ALREADY_VOID")


def check_negative_receipt(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", -50), ("2026-02-01", 100), ("2026-03-01", 20))
    call(pg, "record_receipt", c, 0, "negative-r1", "2026-04-01", "THU TIỀN", 130)
    require(allocations(pg, c, "PH-001") == [("2026-02-01", "debt", "100"),
             ("2026-03-01", "debt", "20"), ("2026-03-01", "advance", "10")],
            "negative opening consumed receipt or advance wrong")
    before = allocations(pg, c, "PH-001")
    reject_call(pg, "adjust_month", c, 1, "unknown-month", "2099-01-01", 5, "sai kỳ",
                error="MONTH_NOT_FOUND")
    require(version(pg, c) == 1 and allocations(pg, c, "PH-001") == before
            and pg.value(f"SELECT count(*) FROM sokhach.adjustment WHERE customer_id={c}") == "0"
            and pg.value(f"SELECT count(*) FROM sokhach.v_outstanding_month "
                         f"WHERE customer_id={c} AND debt_month='2099-01-01'") == "0",
            "unknown month changed advance or created a new last month")
    call(pg, "record_receipt", c, 1, "negative-r2", "2026-04-02", "THU TIỀN", 5)
    other = allocations(pg, c, "PH-002")
    call(pg, "void_receipt", c, 2, "negative-void", "PH-001", "sai")
    require([r[1] for r in months(pg, c)] == ["-50", "100", "15", "0"]
            and allocations(pg, c, "PH-002") == other, "void altered negative opening or other receipt")


def check_csm_reference(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    other = new_book(pg, ("2026-01-01", 100))
    def write(key, reference=None):
        return call(pg, "record_receipt", c, version(pg, c), key,
                    "2026-01-02", "THU TIỀN", 10, reference)
    require(not write("no-ref")["duplicate_reference"], "optional reference warned")
    require(not write("blank-ref", "  ")["duplicate_reference"], "blank reference warned")
    require(not write("first-ref", " FAKE-TXN USD/rate text ")["duplicate_reference"], "first reference warned")
    duplicate = write("duplicate-ref", "FAKE-TXN USD/rate text")
    require(duplicate["duplicate_reference"] and version(pg, c) == 4, "duplicate blocked or not warned")
    require(call(pg, "record_receipt", c, 3, "duplicate-ref", "2026-01-02", "THU TIỀN", 10,
                 "FAKE-TXN USD/rate text") == duplicate and version(pg, c) == 4, "retry wrote twice")
    reject_call(pg, "record_receipt", c, 4, "duplicate-ref", "2026-01-02", "THU TIỀN", 10,
                "different", error="IDEMPOTENCY_CONFLICT")
    require(not call(pg, "record_receipt", other, 0, "other-ref", "2026-01-02", "THU TIỀN", 1,
                     "FAKE-TXN USD/rate text")["duplicate_reference"], "cross-ledger warning")
    old_lines = allocations(pg, c, "PH-001")
    edited = call(pg, "edit_receipt_meta", c, 4, "edit-ref", "PH-001", None, None, "FAKE-TXN USD/rate text")
    require(edited["duplicate_reference"] and allocations(pg, c, "PH-001") == old_lines,
            "reference edit blocked or changed allocations")
    ledger = call(pg, "get_ledger", c)
    receipt = next(r for r in ledger["receipts"] if r["pid"] == "PH-001")
    require(receipt["reference"] == "FAKE-TXN USD/rate text", "GET lost reference")
    event = next(e for e in ledger["events"] if e["kind"] == "receipt_edit")
    require(event["before"]["reference"] is None and event["after"]["reference"] == receipt["reference"],
            "reference edit audit missing")
    call(pg, "edit_receipt_meta", c, 5, "clear-ref", "PH-001", None, None, " ")
    pg.true(f"(SELECT reference IS NULL FROM sokhach.receipt WHERE customer_id={c} AND pid='PH-001')",
            "clear reference did not store NULL")
    pg.rejects(f"UPDATE sokhach.receipt SET reference='unaudited' WHERE customer_id={c} AND pid='PH-001'",
               message="receipt change forbidden")
    require(call(pg, "get_ledger", c)["total_outstanding_vnd"] == "60", "text changed VND")
    call(pg, "void_receipt", c, 6, "void-ref", "PH-004", "fake reason")
    require(write("voided-ref", "FAKE-TXN USD/rate text")["duplicate_reference"], "voided reference ignored")
    unique = call(pg, "edit_receipt_meta", c, version(pg, c), "unique-ref", "PH-005", None, None, "FAKE-UNIQUE")
    require(not unique["duplicate_reference"], "receipt warned against itself")
    call(pg, "edit_receipt_meta", c, version(pg, c), "preserve-ref", "PH-005", None, "KHÁC")
    pg.true(f"(SELECT reference='FAKE-UNIQUE' FROM sokhach.receipt WHERE customer_id={c} AND pid='PH-005')",
            "omitted reference erased existing text")


def check_concurrent(pg: Pg) -> str:
    c = new_book(pg, ("2026-01-01", 100))
    a, b = PsqlSession(pg, f"v7_a_{c}"), PsqlSession(pg, f"v7_b_{c}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='actor-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.record_receipt({c},0,'concurrent-a','2026-02-01','THU TIỀN',70)")
        first = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='actor-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.record_receipt({c},0,'concurrent-b','2026-02-02','THU TIỀN',70)")
        deadline = time.monotonic() + 8
        blocked = False
        while time.monotonic() < deadline:
            blocked = pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t"
            if blocked:
                break
        require(blocked, "second receipt never blocked behind customer lock")
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "first receipt did not commit")
        # ON_ERROR_STOP ends B on expected STALE_LEDGER; stderr is checked after exit.
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("STALE_LEDGER" in stderr, f"blocked stale command did not reject: {stderr[-500:]}")
        require(first["version"] == 1 and version(pg, c) == 1 and months(pg, c)[0][1] == "30"
                and pg.value(f"SELECT count(*) FROM sokhach.receipt WHERE customer_id={c}") == "1",
                "concurrent receipts overapplied debt")
        evidence = f"pg_blocking_pids observed: {pid_b} blocked by {pid_a}; stale rejected"
    finally:
        a.close()
        b.close()
    same = new_book(pg, ("2026-01-01", 100))
    a, b = PsqlSession(pg, f"v7_same_a_{same}"), PsqlSession(pg, f"v7_same_b_{same}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='same-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        sql = (f"SELECT sokhach.record_receipt({same},0,'same-key-concurrent',"
               "'2026-02-01','THU TIỀN',70)")
        a.send(sql)
        first = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='same-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(sql)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and pg.value(
                f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") != "t":
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t",
                "same-key command did not wait for first transaction")
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "first same-key command did not commit")
        require(json.loads(b.line()) == first, "concurrent same-key retry changed result")
        b.send("COMMIT; SELECT 'committed'")
        require(b.line() == "committed", "second same-key command did not commit")
        require(version(pg, same) == 1 and pg.value(
            f"SELECT count(*) FROM sokhach.receipt WHERE customer_id={same}") == "1",
            "same-key concurrent command wrote twice")
    finally:
        a.close()
        b.close()
    return evidence + "; same-key returned stored result"


def check_pid_order(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    call(pg, "record_receipt", c, 0, "pid-first", "2026-02-01", "THU TIỀN", 60)
    call(pg, "record_receipt", c, 1, "pid-second", "2026-02-01", "THU TIỀN", 60)
    pg.true("'PH-B' COLLATE \"C\" < 'PH-a' COLLATE \"C\" AND "
            "'PH-a' COLLATE \"en-US-x-icu\" < 'PH-B' COLLATE \"en-US-x-icu\"",
            "test pid pair does not distinguish C from en-US ICU")
    expected = run_node("const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');"
        "const d='01/02/2026',method='THU TIỀN';"
        "const r=(pid,amountVnd,kind)=>({pid,date:d,method,amountVnd,kind,voided:null});"
        "const book={months:[{key:'2026-01',trips:[{container:'C',unitPriceVnd:'100',"
        "otherFeeVnd:null}],adjustments:[],receipts:[r('PH-a','60','debt'),"
        "r('PH-B','40','debt'),r('PH-B','20','advance')]}]};"
        "console.log(JSON.stringify(m.planReallocation(book).lines.map(x=>"
        "[x.receipt.pid,x.receipt.kind,x.receipt.amountVnd]).sort((a,b)=>"
        "a[0]<b[0]?-1:a[0]>b[0]?1:a[1]<b[1]?-1:a[1]>b[1]?1:0)))")
    require(expected == [["PH-B", "debt", "60"], ["PH-a", "advance", "20"],
                         ["PH-a", "debt", "40"]], "JS mixed-case fixture changed")
    sql = ("BEGIN; ALTER TABLE sokhach.receipt DISABLE TRIGGER receipt_guard; "
           f"UPDATE sokhach.receipt SET pid=CASE pid WHEN 'PH-001' THEN 'PH-a' "
           f"ELSE 'PH-B' END WHERE customer_id={c}; "
           "SET CONSTRAINTS ALL IMMEDIATE; "  # deferred pair checks block ALTER TABLE
           "ALTER TABLE sokhach.receipt ENABLE TRIGGER receipt_guard; "
           "SET LOCAL sokhach.actor='harness'; "
           f"SELECT sokhach.reallocate({c},'pid-order'); "
           f"SELECT coalesce(jsonb_agg(jsonb_build_array(r.pid,l.kind,l.amount_vnd::text) "
           "ORDER BY r.pid COLLATE \"C\",l.kind),'[]'::jsonb) "
           "FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id=l.receipt_id "
           f"WHERE r.customer_id={c} AND l.superseded_by_event IS NULL; ROLLBACK")
    result = json.loads(pg.value(sql).splitlines()[-1])
    require(result == expected,
            f"same-day pid order differs from JS: {result}")


def check_snapshots(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    call(pg, "record_receipt", c, 0, "snap-receipt", "2026-03-01", "THU TIỀN", 100)
    call(pg, "set_month_lock", c, 1, "snap-open", "2026-01-01", "false")
    old = pg.value("SELECT jsonb_agg(jsonb_build_object('id',l.id,'month',l.debt_month,"
        "'kind',l.kind,'amount_vnd',l.amount_vnd::text) ORDER BY l.id)::text "
        f"FROM sokhach.receipt_line l WHERE l.customer_id={c}")
    result = call(pg, "adjust_month", c, 2, "snap-adjust", "2026-01-01", 10, "sửa")
    require(len(result["reallocated"]) == 1, "changed allocation lacks reallocation result")
    event_id = result["reallocated"][0]["event_id"]
    event = json.loads(pg.value(f"SELECT jsonb_build_object('before',\"before\",'after',\"after\") "
                                   f"FROM sokhach.event WHERE id={event_id}"))
    require(event["before"]["allocations"] == json.loads(old)
            and event["after"]["allocations"] == result["reallocated"][0]["after"],
            "reallocation snapshot mismatches row IDs and amounts")
    pg.true(f"(SELECT count(*)=2 AND bool_and(superseded_by_event={event_id}) "
        f"FROM sokhach.receipt_line WHERE customer_id={c} AND id IN "
        f"(SELECT (x->>'id')::bigint FROM jsonb_array_elements({lit(old)}::jsonb) x))",
        "original allocations not superseded by snapshot event")
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "70"),
            ("2026-02-01", "debt", "30")], "same-month-set reallocation tuple wrong")
    assert_allocations(pg, c)
    receipt_id = int(pg.value(f"SELECT id FROM sokhach.receipt WHERE customer_id={c} AND pid='PH-001'"))
    pg.rejects("INSERT INTO sokhach.receipt_line(receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event) "
               f"VALUES ({receipt_id},{c},'2026-01-01','debt',1,999999999)", message="foreign key")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
               f"VALUES ({c},'reallocation','harness','{{}}','{{\"allocations\":[]}}')",
               message="check constraint")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
               f"VALUES ({c},'reallocation','harness','{{\"allocations\":[]}}','{{}}')",
               message="check constraint")

    fault = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 100))
    call(pg, "set_month_lock", fault, 0, "fault-open", "2026-01-01", "false")
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    trip = call(pg, "paste_trips", fault, 1, "fault-base-trip", current, trip_json(month=current))["trip_ids"][0]
    call(pg, "record_receipt", fault, 2, "fault-base-receipt", "2026-03-01", "THU TIỀN", 150)
    pg.sql("CREATE FUNCTION public.harness_abort() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'HARNESS_ABORT'; END $$")
    try:
        operations = [
            ("record_receipt", ("2026-03-02", "THU TIỀN", 10), "receipt_line", "INSERT"),
            ("edit_receipt_meta", ("PH-001", "2026-03-03", None), "receipt", "UPDATE"),
            ("void_receipt", ("PH-001", "sai"), "receipt_line", "UPDATE"),
            ("adjust_trip", (trip, 101, "sửa"), "adjustment", "INSERT"),
            ("adjust_month", ("2026-01-01", 5, "sửa"), "adjustment", "INSERT"),
            ("edit_trip_price", (trip, 110, None), "trip_price_rev", "INSERT"),
            ("paste_trips", (current, trip_json(month=current)), "trip", "INSERT"),
        ]
        tables = ("event", "trip", "trip_price_rev", "adjustment", "receipt",
                  "receipt_line", "idempotency")
        def state() -> tuple:
            return (version(pg, fault), tuple(pg.value("SELECT coalesce(jsonb_agg(to_jsonb(x) "
                    "ORDER BY to_jsonb(x)::text),'[]'::jsonb) FROM "
                    f"(SELECT * FROM sokhach.{t} WHERE customer_id={fault}) x") for t in tables),
                    tuple(months(pg, fault)),
                    tuple(allocations(pg, fault, "PH-001")))
        for i, (name, args, table, timing) in enumerate(operations, 1):
            before = state()
            pg.sql(f"CREATE TRIGGER harness_abort_{i} BEFORE {timing} ON sokhach.{table} "
                   "FOR EACH ROW EXECUTE FUNCTION public.harness_abort()")
            try:
                reject_call(pg, name, fault, version(pg, fault), f"fault-{i}", *args,
                            error="HARNESS_ABORT")
                require(state() == before, f"{name} left partial rows/version/balance after abort")
            finally:
                pg.sql(f"DROP TRIGGER harness_abort_{i} ON sokhach.{table}")
    finally:
        pg.sql("DROP FUNCTION public.harness_abort()")
    success = [
        ("paste_trips", (current, trip_json("20", month=current)), "paste"),
        ("edit_trip_price", (trip, 110, None), "price_edit"),
        ("adjust_trip", (trip, 115, "sửa"), "adjust_trip"),
        ("adjust_month", ("2026-01-01", 5, "sửa"), "adjust_month"),
        ("record_receipt", ("2026-03-02", "THU TIỀN", 10), "receipt"),
        ("edit_receipt_meta", ("PH-002", "2026-03-04", None), "receipt_edit"),
        ("void_receipt", ("PH-002", "sai"), "void"),
    ]
    for i, (name, args, kind) in enumerate(success, 1):
        key = f"snap-success-{i}"
        call(pg, name, fault, version(pg, fault), key, *args)
        assert_allocations(pg, fault)
        events = json.loads(pg.value("SELECT coalesce(json_agg(json_build_object('kind',kind,"
            "'before',\"before\",'after',\"after\")),'[]'::json)::text FROM sokhach.event "
            f"WHERE customer_id={fault} AND idempotency_key={lit(key)} AND kind={lit(kind)}"))
        require(len(events) == 1 and isinstance(events[0]["before"], dict)
                and isinstance(events[0]["after"], dict) and bool(events[0]["after"]),
                f"{name} missing main event snapshot")
        if kind not in ("paste", "receipt"):
            require(bool(events[0]["before"]), f"{name} missing before snapshot")


def check_da_thu(pg: Pg) -> None:
    """DA-THU-01: Tổng tháng như Sheet; phân bổ nợ cũ trước và nợ từng kỳ giữ nguyên."""
    customer, cutover = cutover_book(pg, 150)
    # Sheet: phát sinh 100/50/30, thu 30 trong tháng 2 (trừ nợ tháng 1) → bucket 70/50/30, cộng dồn 100/120/150.
    openings, legacy, checks = import_data([70, 50, 30], charges=[100, 50, 30], receipts=[0, 30, 0])
    call(pg, "import_cutover", customer, 0, "da-thu-import", cutover, openings, legacy, checks, 150, "a" * 64)
    call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer), "da-thu-verify", "FAKE-SIGNOFF")
    call(pg, "verify_cutover", cutover, "da-thu-verify-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover", cutover, "da-thu-activate-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer), "da-thu-activate", "FAKE-SIGNOFF")

    def rows() -> list[tuple[str, str, str, str, str, str]]:
        return [(m["month"][:7], m["prior_months_vnd"], m["charges_vnd"], m["received_vnd"], m["end_of_month_vnd"],
                 m["outstanding_vnd"]) for m in call(pg, "get_ledger", customer)["months"]]
    require(rows() == [("2026-01", "0", "100", "0", "100", "70"), ("2026-02", "100", "50", "30", "120", "50"),
                       ("2026-03", "120", "30", "0", "150", "30")], f"Sheet figures not used for month totals: {rows()}")
    # Thu 100 ngày 15/03: trừ nợ tháng 1 (70) và tháng 2 (30) nhưng nằm ở tháng 3; tháng 1, 2 giữ số như Sheet.
    call(pg, "record_receipt", customer, version(pg, customer), "da-thu-r1", "2026-03-15", "THU TIỀN", 100)
    first = call(pg, "get_ledger", customer)["receipts"][0]["pid"]
    require(allocations(pg, customer, first) == [("2026-01-01", "debt", "70"), ("2026-02-01", "debt", "30")],
            "old-debt-first allocation changed")
    # Thu 10 ngày 02/04: tháng chưa có chuyến vẫn hiện để đặt phiếu.
    call(pg, "record_receipt", customer, version(pg, customer), "da-thu-r2", "2026-04-02", "THU TIỀN", 10)
    # Phiếu 02/04 cũng trừ nợ tháng 2 trước (còn 10); nợ từng kỳ theo phân bổ, cộng dồn theo ngày thu.
    expected = [("2026-01", "0", "100", "0", "100", "0"), ("2026-02", "100", "50", "30", "120", "10"),
                ("2026-03", "120", "30", "100", "50", "30"), ("2026-04", "50", "0", "10", "40", "0")]
    require(rows() == expected, f"received not by receipt date or cumulative rewritten: {rows()}")
    require(call(pg, "get_ledger", customer)["total_outstanding_vnd"] == "40", "total outstanding changed")
    pid = call(pg, "get_ledger", customer)["receipts"][-1]["pid"]
    call(pg, "void_receipt", customer, version(pg, customer), "da-thu-void", pid, "nhập trùng")
    require(rows()[1:] == [("2026-02", "100", "50", "30", "120", "20"), ("2026-03", "120", "30", "100", "50", "30")],
            f"voided receipt still counted: {rows()}")
    # Xóa khoản thu sổ gốc (XOA-THU-GOC-01): Đã thu của tháng giảm, phát sinh không đổi, nợ tăng lại đúng số đó.
    book, book_cutover = cutover_book(pg, 70)
    openings, _, checks = import_data([70], charges=[100], receipts=[30])
    legacy = json.dumps([{"debt_month": "2026-01-01", "kind": "receipt", "display": {"row": 9},
                          "source_total_vnd": 30, "source_tab": "FAKE", "source_row": 9}])
    call(pg, "import_cutover", book, 0, "da-thu-legacy-import", book_cutover, openings, legacy, checks, 70, "a" * 64)
    call(pg, "verify_cutover_customer", book, book_cutover, version(pg, book), "da-thu-legacy-verify", "FAKE-SIGNOFF")
    call(pg, "verify_cutover", book_cutover, "da-thu-legacy-verify-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover", book_cutover, "da-thu-legacy-activate-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover_customer", book, book_cutover, version(pg, book), "da-thu-legacy-activate", "FAKE-SIGNOFF")
    fixture_open_month(pg, book, "2026-01-01")
    legacy_id = call(pg, "get_ledger", book)["legacy_rows"][0]["id"]
    call(pg, "delete_legacy_trip", book, version(pg, book), "da-thu-legacy-delete", legacy_id)
    month = call(pg, "get_ledger", book)["months"][0]
    require((month["charges_vnd"], month["received_vnd"], month["end_of_month_vnd"], month["outstanding_vnd"])
            == ("100", "0", "100", "100"), f"deleted Sheet receipt not removed from received: {month}")


def check_future_receipt(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 500))
    today = pg.value("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    tomorrow = pg.value(f"SELECT ({lit(today)}::date+1)::text")
    first = call(pg, "record_receipt", c, 0, "date-today", today, "THU TIỀN", 100)
    require(version(pg, c) == 1, "today receipt rejected")
    before = call(pg, "get_ledger", c)
    reject_call(pg, "record_receipt", c, 1, "date-tomorrow", tomorrow, "THU TIỀN", 10,
                error="FUTURE_RECEIPT_DATE")
    reject_call(pg, "edit_receipt_meta", c, 1, "date-edit-tomorrow", first["pid"], tomorrow, None,
                error="FUTURE_RECEIPT_DATE")
    require(call(pg, "get_ledger", c) == before and version(pg, c) == 1,
            "future receipt changed version, events, allocations or receipt")
    call(pg, "edit_receipt_meta", c, 1, "date-edit-today", first["pid"], today, "KHÁC")
    require(version(pg, c) == 2, "today metadata edit rejected")
    for name in ("record_receipt", "edit_receipt_meta"):
        definition = pg.value("SELECT pg_get_functiondef(oid) FROM pg_proc "
            f"WHERE pronamespace='sokhach'::regnamespace AND proname='{name}'")
        require(definition.index("_begin_command") < definition.index("clock_timestamp()"),
                f"{name} reads receipt clock before customer lock")


def check_void_get(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 60), ("2026-02-01", 60))
    first = call(pg, "record_receipt", c, 0, "void-get-r", "2026-03-01", "THU TIỀN", 100)
    fixture_open_month(pg, c, "2026-01-01")
    call(pg, "adjust_month", c, 1, "void-get-a", "2026-01-01", -30, "đổi phân bổ")
    at_void = allocations(pg, c, first["pid"])
    call(pg, "void_receipt", c, 2, "void-get-v", first["pid"], "nhập trùng")
    receipt = call(pg, "get_ledger", c)["receipts"][0]
    require(receipt["voided_by_event"] is not None, "GET lacks void event")
    shown = [(line["month"], line["kind"], line["amount_vnd"]) for line in receipt["allocations"]
             if line["superseded_by_event"] == receipt["voided_by_event"]]
    require(shown == at_void and len(receipt["allocations"]) > len(shown),
            "void shows reallocation history or loses current allocation")
