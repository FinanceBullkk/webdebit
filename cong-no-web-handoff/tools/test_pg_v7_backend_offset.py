"""V7 backend harness cases: CT-2SO offsets between two books.

Run through test_pg_v7_backend.py."""

from __future__ import annotations

import json
import time

from pg_v7_harness import (
    HarnessError,
    Pg,
    PsqlSession,
    actor_sql,
    allocations,
    assert_allocations,
    call,
    lit,
    new_book,
    reject_call,
    require,
    version,
)


# CT-2SO uses disposable fake opening only. Snapshot covers both books and every
# pair-command artifact, not identity sequences (PostgreSQL sequences do not roll back).
def ct_total(pg: Pg, customer: int) -> int:
    return int(call(pg, "get_ledger", customer)["total_outstanding_vnd"])


def ct_record(pg: Pg, source: int, target: int, key: str, amount: int = 50,
              date: str = "2026-03-01") -> dict:
    return call(pg, "record_offset", target, version(pg, target), source,
                version(pg, source), key, date, amount)


def ct_snapshot(pg: Pg, source: int, target: int) -> str:
    ids = f"({source},{target})"
    queries = []
    for table, where in (
        ("customer", f"id IN {ids}"), ("event", f"customer_id IN {ids}"),
        ("receipt", f"customer_id IN {ids}"), ("receipt_line", f"customer_id IN {ids}"),
        ("idempotency", f"customer_id IN {ids}"),
        ("offset_pair", f"source_customer_id IN {ids} OR target_customer_id IN {ids}"),
        ("offset_command", f"low_customer_id IN {ids} OR high_customer_id IN {ids}"),
    ):
        queries.append(f"'{table}',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]') "
                       f"FROM sokhach.{table} t WHERE {where})")
    return pg.value("SELECT jsonb_build_object(" + ",".join(queries) + ")")


def check_ct_01(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100_000_000))
    b = new_book(pg, ("2026-01-01", 50_000_000))
    pair = ct_record(pg, a, b, "ct01", 50_000_000)
    require((ct_total(pg, a), ct_total(pg, b)) == (-50_000_000, 0), "CT01 balances")
    require(pair["source_version"] == pair["target_version"] == 1, "CT01 versions")
    for book, other in ((a, b), (b, a)):
        events = [e for e in call(pg, "get_ledger", book)["events"] if e["kind"] != "import"]
        require(len(events) == 1 and events[0]["actor"] == "harness", "CT01 audit cardinality/actor")
        require(events[0]["counterparty_customer_id"] == other, "CT01 audit link")
    require(call(pg, "get_ledger", a)["outgoing_offsets"][0]["amount_vnd"] == "-50000000",
            "CT01 outgoing displayed as negative payment")
    require(call(pg, "get_ledger", a)["months"][-1]["charges_vnd"] == "0",
            "CT01 outgoing became trip charge")


def check_ct_02(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100_000_000))
    b = new_book(pg, ("2026-01-01", 50_000_000))
    before = ct_snapshot(pg, a, b)
    reject_call(pg, "record_offset", b, 0, a, 0, "ct02", "2026-03-01", 120_000_000,
                error="OFFSET_EXCEEDS_CREDIT")
    require(ct_snapshot(pg, a, b) == before, "CT02 overflow changed state")
    result = pg.sql(actor_sql(f"SELECT sokhach.record_offset({b},0,{a},0,'ct02-detail',"
                             "'2026-03-01',120000000)"), check=False)
    require('"available_credit_vnd": "100000000"' in result.stderr, "CT02 missing credit detail")
    reject_call(pg, "record_offset", a, 0, a, 0, "ct02-same", "2026-03-01", 1,
                error="OFFSET_SAME_BOOK")
    for amount in (None, 0, -1):
        reject_call(pg, "record_offset", b, 0, a, 0, "ct02-invalid", "2026-03-01", amount,
                    error="INVALID_VND")
    unbased = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('CT UNBASED') RETURNING id"))
    reject_call(pg, "record_offset", b, 0, unbased, 0, "ct02-unbased-source", "2026-03-01", 1,
                error="NO_BASELINE")
    reject_call(pg, "record_offset", unbased, 0, a, 0, "ct02-unbased-target", "2026-03-01", 1,
                error="NO_BASELINE")
    for av, bv in ((1, 0), (0, 1)):
        reject_call(pg, "record_offset", b, bv, a, av, "ct02-stale", "2026-03-01", 1,
                    error="STALE_LEDGER")


def check_ct_03(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    before = ct_snapshot(pg, a, b)
    pg.sql("CREATE FUNCTION sokhach.ct_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
           "RAISE EXCEPTION 'CT_FAULT_AFTER_TARGET'; END $$; "
           "CREATE TRIGGER ct_fault BEFORE INSERT ON sokhach.offset_pair "
           "FOR EACH ROW EXECUTE FUNCTION sokhach.ct_fault()")
    try:
        reject_call(pg, "record_offset", b, 0, a, 0, "ct03", "2026-03-01", 50,
                    error="CT_FAULT_AFTER_TARGET")
        require(ct_snapshot(pg, a, b) == before, "CT03 target/source/event/key escaped rollback")
    finally:
        pg.sql("DROP TRIGGER ct_fault ON sokhach.offset_pair; DROP FUNCTION sokhach.ct_fault()")
    pair = ct_record(pg, a, b, "ct03")
    for command, value in (("void_offset", "wrong"), ("edit_offset_date", "2026-02-01")):
        before = ct_snapshot(pg, a, b)
        pg.sql("CREATE FUNCTION sokhach.ct_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
               "RAISE EXCEPTION 'CT_FAULT_AFTER_TARGET'; END $$; "
               "CREATE TRIGGER ct_fault BEFORE UPDATE ON sokhach.offset_pair "
               "FOR EACH ROW EXECUTE FUNCTION sokhach.ct_fault()")
        try:
            reject_call(pg, command, a, 1, 1, "ct03-" + command, pair["offset_pair_id"], value,
                        error="CT_FAULT_AFTER_TARGET")
            require(ct_snapshot(pg, a, b) == before, "CT03 change escaped rollback")
        finally:
            pg.sql("DROP TRIGGER ct_fault ON sokhach.offset_pair; DROP FUNCTION sokhach.ct_fault()")


def ct_contend(pg: Pg, cross: bool) -> str:
    source = new_book(pg, ("2026-01-01", -100))
    target = new_book(pg, ("2026-01-01", -100 if cross else 50))
    other = source if cross else new_book(pg, ("2026-01-01", 50))
    a, b = PsqlSession(pg, f"ct_a_{source}"), PsqlSession(pg, f"ct_b_{source}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='ct-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        first_sql = f"SELECT sokhach.record_offset({target},0,{source},0,'ct-first','2026-03-01',60)"
        if cross:
            # A owns only the lowest ID. Inverse B must wait here without owning
            # the higher ID, otherwise A's command below will expose a deadlock.
            a.send(f"SELECT id FROM sokhach.customer WHERE id={source} FOR UPDATE")
            require(int(a.line()) == source, "CT05 did not lock lowest ID")
        else:
            a.send(first_sql)
            first = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='ct-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        second_source = target if cross else source
        b.send(f"SELECT sokhach.record_offset({other},0,{second_source},0,'ct-second','2026-03-01',60)")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t":
                break
        else:
            raise HarnessError("CT contention did not observe pg_blocking_pids")
        if cross:
            a.send(first_sql)
            first = json.loads(a.line())
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "CT first commit")
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("STALE_LEDGER" in stderr and "deadlock" not in stderr.lower(),
                f"CT blocked writer wrong result: {stderr[-700:]}")
        require(first["source_version"] == 1 and ct_total(pg, source) == -40,
                "CT same credit spent twice")
    finally:
        a.close()
        b.close()
    if cross:
        ct_record(pg, target, source, "ct-reverse", 60)
        require(ct_total(pg, source) == ct_total(pg, target) == -100, "CT reverse after refresh")
    else:
        reject_call(pg, "record_offset", other, 0, source, 1, "ct-after-refresh", "2026-03-01", 60,
                    error="OFFSET_EXCEEDS_CREDIT")
    return f"pg_blocking_pids: {pid_b} blocked by {pid_a}; stale rejected without deadlock"


def check_ct_04(pg: Pg) -> str:
    return ct_contend(pg, False)


def check_ct_05(pg: Pg) -> str:
    return ct_contend(pg, True)


def check_ct_06(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    first = ct_record(pg, a, b, "ct06")
    before = ct_snapshot(pg, a, b)
    require(call(pg, "record_offset", b, 0, a, 0, "ct06", "2026-03-01", 50) == first,
            "CT06 retry stale versions")
    reject_call(pg, "record_offset", b, 0, a, 0, "ct06", "2026-03-01", 51,
                error="IDEMPOTENCY_CONFLICT")
    require(ct_snapshot(pg, a, b) == before, "CT06 retry wrote again")
    # Retries of a pair mutation can originate on the other side.
    edited = call(pg, "edit_offset_date", a, 1, 1, "ct06-edit", first["offset_pair_id"], "2026-02-01")
    require(call(pg, "edit_offset_date", b, 1, 1, "ct06-edit", first["offset_pair_id"],
                 "2026-02-01") == edited, "CT06 cross-side date retry")
    voided = call(pg, "void_offset", b, 2, 2, "ct06-void", first["offset_pair_id"], "wrong")
    require(call(pg, "void_offset", a, 2, 2, "ct06-void", first["offset_pair_id"], "wrong") == voided,
            "CT06 cross-side void retry")


def check_ct_07(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50), ("2026-02-01", 50))
    receipt = call(pg, "record_receipt", b, 0, "ct07-other", "2026-03-01", "THU TIỀN", 20)
    original = (ct_total(pg, a), ct_total(pg, b))
    other_lines = allocations(pg, b, receipt["pid"])
    for side in (a, b):
        pair = ct_record(pg, a, b, "ct07-record-" + str(side))
        reject_call(pg, "void_offset", side, version(pg, side), version(pg, b if side == a else a),
                    "ct07-empty", pair["offset_pair_id"], " ", error="VOID_REASON_REQUIRED")
        call(pg, "void_offset", side, version(pg, side), version(pg, b if side == a else a),
             "ct07-void-" + str(side), pair["offset_pair_id"], "wrong")
        require((ct_total(pg, a), ct_total(pg, b)) == original, "CT07 both books not restored")
        require(allocations(pg, b, receipt["pid"]) == other_lines, "CT07 changed other target receipt")
        assert_allocations(pg, b)
        reject_call(pg, "void_offset", side, version(pg, side), version(pg, b if side == a else a),
                    "ct07-again", pair["offset_pair_id"], "wrong", error="OFFSET_ALREADY_VOID")


def check_ct_08(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100), ("2026-02-01", 50))
    b = new_book(pg, ("2026-01-01", 40), ("2026-02-01", 40))
    call(pg, "record_receipt", a, 0, "ct08-source", "2026-03-02", "THU TIỀN", 60)
    call(pg, "record_receipt", b, 0, "ct08-target", "2026-03-02", "THU TIỀN", 30)
    pair = ct_record(pg, a, b, "ct08", 40, "2026-03-03")
    before = ct_total(pg, a) + ct_total(pg, b)
    changed = call(pg, "edit_offset_date", a, 2, 2, "ct08-edit", pair["offset_pair_id"], "2026-01-03")
    require(changed["source_reallocated"] and changed["target_receipt"]["reallocated"],
            "CT08 lacks both reallocation snapshots")
    pg.true(f"EXISTS (SELECT 1 FROM sokhach.offset_pair p JOIN sokhach.receipt r "
            f"ON r.id=p.target_receipt_id WHERE p.id={pair['offset_pair_id']} "
            "AND p.date='2026-01-03' AND r.date=p.date)", "CT08 dates differ")
    require(ct_total(pg, a) + ct_total(pg, b) == before, "CT08 changed total")
    for book in (a, b):
        ledger = call(pg, "get_ledger", book)
        require(any(e["kind"] == "receipt_edit" and e["counterparty_customer_id"] is not None
                    for e in ledger["events"]), "CT08 missing paired edit history")
        assert_allocations(pg, book)


def check_ct_09(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    pair = ct_record(pg, a, b, "ct09")
    before = ct_snapshot(pg, a, b)
    for method in ("KHÁC", "CẤN TRỪ"):
        reject_call(pg, "edit_receipt_meta", b, 1, "ct09-method", pair["target_pid"],
                    "2026-02-01", method, error="OFFSET_PAIR_REQUIRED")
    reject_call(pg, "void_receipt", b, 1, "ct09-single-void", pair["target_pid"], "wrong",
                error="OFFSET_PAIR_REQUIRED")
    require(ct_snapshot(pg, a, b) == before, "CT09 single side command modified pair")


def check_ct_10(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    receipt = call(pg, "record_receipt", b, 0, "ct10", "2026-03-01", "CẤN TRỪ", 50)
    require(ct_total(pg, a) == -100 and ct_total(pg, b) == 0 and version(pg, a) == 0,
            "CT10 outside receipt changed source")
    require(call(pg, "get_ledger", b)["receipts"][0]["offset_pair_id"] is None,
            "CT10 outside receipt linked")
    call(pg, "void_receipt", b, 1, "ct10-void", receipt["pid"], "wrong")
    require(ct_total(pg, b) == 50, "CT10 outside void no longer works")


def check_ct_11(pg: Pg) -> None:
    target = new_book(pg, ("2026-01-01", -10))
    yes_a = new_book(pg, ("2026-01-01", -20))
    yes_z = new_book(pg, ("2026-01-01", -30))
    debt = new_book(pg, ("2026-01-01", 20))
    zero = new_book(pg, ("2026-01-01", 0))
    archived = new_book(pg, ("2026-01-01", -20))
    draft = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('CT11 DRAFT') RETURNING id"))
    pg.sql(f"UPDATE sokhach.customer SET name='CT11 A' WHERE id={yes_a}; "
           f"UPDATE sokhach.customer SET name='CT11 Z' WHERE id={yes_z}; "
           f"UPDATE sokhach.customer SET archived=true WHERE id={archived}")
    rows = call(pg, "list_offset_sources", target)
    ids = [row["customer_id"] for row in rows]
    require(yes_a in ids and yes_z in ids and ids.index(yes_a) < ids.index(yes_z), "CT11 A-Z order")
    require(not {target, debt, zero, archived, draft} & set(ids), "CT11 invalid source listed")
    row = next(r for r in rows if r["customer_id"] == yes_a)
    require(row["version"] == 0 and row["available_credit_vnd"] == "20"
            and row["outstanding_vnd"] == "-20", "CT11 source contract")
    reject_call(pg, "record_offset", target, 0, archived, 0, "ct11-archive", "2026-03-01", 1,
                error="OFFSET_SOURCE_ARCHIVED")


def check_ct_12(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    # Clock independent of sokhach helper; session timezone deliberately differs.
    today = pg.value("SET TIME ZONE 'Pacific/Honolulu'; "
                     "SELECT (clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    tomorrow = pg.value(f"SELECT ({lit(today)}::date+1)::text")
    before = ct_snapshot(pg, a, b)
    reject_call(pg, "record_offset", b, 0, a, 0, "ct12-future", tomorrow, 1, error="FUTURE_DATE")
    require(ct_snapshot(pg, a, b) == before, "CT12 future record changed state")
    pair = ct_record(pg, a, b, "ct12-today", 50, today)
    before = ct_snapshot(pg, a, b)
    for side in (a, b):
        reject_call(pg, "edit_offset_date", side, 1, 1, "ct12-edit", pair["offset_pair_id"], tomorrow,
                    error="FUTURE_DATE")
    require(ct_snapshot(pg, a, b) == before, "CT12 future edit changed state")


def check_ct_13(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    old = call(pg, "record_receipt", b, 0, "ct13-old", "2026-02-01", "CẤN TRỪ", 10)
    ct_record(pg, a, b, "ct13-new", 10, "2026-02-01")
    ledger = call(pg, "get_ledger", b)
    row = next(r for r in ledger["receipts"] if r["pid"] == old["pid"])
    require(row["offset_pair_id"] is None and row["counterparty_customer_id"] is None,
            "CT13 guessed link from identical date/method/amount")
    require(pg.value(f"SELECT count(*) FROM sokhach.offset_pair WHERE target_customer_id={b}") == "1",
            "CT13 backfilled old receipt")


def check_ct_14(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100))
    b = new_book(pg, ("2026-01-01", 50))
    for n in range(12):
        call(pg, "record_receipt", a, n, f"ct14-a{n}", "2026-02-01", "THU TIỀN", 1)
    call(pg, "record_receipt", b, 0, "ct14-b", "2026-02-01", "THU TIỀN", 1)
    pair = ct_record(pg, a, b, "ct14", 10)
    require(pair["source_pid"] == "PH-013" and pair["target_pid"] == "PH-002", "CT14 per-book code")
    receipt = call(pg, "record_receipt", a, 13, "ct14-next", "2026-04-01", "THU TIỀN", 1)
    require(receipt["pid"] == "PH-014", "CT14 ordinary receipt reused outgoing code")
    pg.true("NOT EXISTS (SELECT customer_id,pid FROM (SELECT customer_id,pid FROM sokhach.receipt "
            "UNION ALL SELECT source_customer_id,source_pid FROM sokhach.offset_pair) codes "
            f"WHERE customer_id IN ({a},{b}) GROUP BY customer_id,pid HAVING count(*)>1)", "CT14 duplicate codes")


def check_ct_15(pg: Pg) -> None:
    a = new_book(pg, ("2026-01-01", -100_000_000))
    b = new_book(pg, ("2026-01-01", 50_000_000))
    pair = ct_record(pg, a, b, "ct15", 70_000_000)
    require((ct_total(pg, a), ct_total(pg, b)) == (-30_000_000, -20_000_000), "CT15 balances")
    require(allocations(pg, b, pair["target_pid"]) == [("2026-01-01", "debt", "50000000"),
                                                    ("2026-01-01", "advance", "20000000")],
            "CT15 missing advance")
    require(pair["target_receipt"]["overpayment_vnd"] == "20000000", "CT15 overpayment contract")
