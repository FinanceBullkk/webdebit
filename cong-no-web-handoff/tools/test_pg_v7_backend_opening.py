"""V7 backend harness cases: Opening/cutover import, FIFO through opening, JS model parity, golden fixture, dashboard.

Run through test_pg_v7_backend.py."""

from __future__ import annotations

import json
import subprocess
import time

from pg_v7_harness import (
    DATABASE,
    HarnessError,
    Pg,
    PsqlSession,
    actor_sql,
    allocations,
    assert_allocations,
    call,
    cutover_book,
    import_book,
    import_data,
    lit,
    months,
    new_book,
    parse_blocker_row,
    reject_call,
    require,
    run,
    run_node,
    trip_json,
    version,
)


def check_opening_import(pg: Pg) -> None:
    amounts = [100, 0, -20, 30, 40, 50, 60, 70, 80, 90, 100]
    customer, cutover = cutover_book(pg, sum(amounts))
    openings, _, checks = import_data(amounts)
    legacy = json.dumps([{"debt_month": "2026-06-01", "kind": "receipt",
                          "display": {"pid": "PH-101"}, "source_total_vnd": 600694000,
                          "source_tab": "FAKE", "source_row": 101}])
    result = call(pg, "import_cutover", customer, 0, "eleven-month-import", cutover,
                  openings, legacy, checks, sum(amounts), "a" * 64)
    require(result["status"] == "draft" and result["version"] == 1, "import did not make draft")
    require(pg.value(f"SELECT count(*) FROM sokhach.opening_balance WHERE customer_id={customer}") == "11",
            "11 opening rows missing")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={customer} AND kind='import'") == "1",
            "import event missing")
    require(pg.value(f"SELECT display->>'pid' FROM sokhach.legacy_row WHERE customer_id={customer}") == "PH-101",
            "historical PH-101 missing")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "draft ledger leaked")
    require(pg.value(f"SELECT count(*) FROM sokhach.v_outstanding_month WHERE customer_id={customer}") == "0",
            "draft opening entered balance")


def check_cutover_gate(pg: Pg) -> None:
    wrong, wrong_cutover = cutover_book(pg, 300)
    wrong_openings, wrong_legacy, wrong_checks = import_data(
        [90, 210], buckets=[90, 210], standards=[100, 200])
    call(pg, "import_cutover", wrong, 0, "wrong-month-import", wrong_cutover,
         wrong_openings, wrong_legacy, wrong_checks, 300, "a" * 64)
    reject_call(pg, "verify_cutover_customer", wrong, wrong_cutover, version(pg, wrong),
                "wrong-month-verify", "FAKE-SIGNOFF", error="CUTOVER_MONTH_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={wrong}") == "draft",
            "[90,210] passed independent [100,200] monthly gate")
    customer, cutover = cutover_book(pg, 300)
    openings, legacy, checks = import_data([100, 200], buckets=[90, 210],
                                          charges=[100, 200])
    call(pg, "import_cutover", customer, 0, "gate-import", cutover,
         openings, legacy, checks, 300, "a" * 64)
    reject_call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer),
                "gate-bad-bucket", "FAKE-SIGNOFF", error="CUTOVER_MONTH_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={customer}") == "draft",
            "bad monthly bucket verified")
    # Source charges stay [100,200]; repair only imported monthly buckets.
    pg.sql(f"UPDATE sokhach.cutover_month_check SET standard_bucket_vnd=100, bucket_vnd=100 "
           f"WHERE customer_id={customer} "
           "AND debt_month='2026-01-01'")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET standard_bucket_vnd=200, bucket_vnd=200 "
           f"WHERE customer_id={customer} "
           "AND debt_month='2026-02-01'")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET replay_cumulative_vnd=-1 WHERE customer_id={customer}")
    # Client replay is diagnostic only; anchored bucket and source checks decide gate.
    no_anchor, no_anchor_cutover = cutover_book(pg, 0)
    anchor_openings, anchor_legacy, anchor_checks = import_data([0])
    broken_checks = json.loads(anchor_checks)
    broken_checks[0]["standard_source_ref"] = None
    call(pg, "import_cutover", no_anchor, 0, "missing-anchor-import", no_anchor_cutover,
         anchor_openings, anchor_legacy, json.dumps(broken_checks), 0, "a" * 64)
    reject_call(pg, "verify_cutover_customer", no_anchor, no_anchor_cutover,
                version(pg, no_anchor), "missing-anchor-verify", "FAKE-SIGNOFF",
                error="CUTOVER_MONTH_MISMATCH")
    missing_flow, missing_flow_cutover = cutover_book(pg, 100)
    import_book(pg, missing_flow, missing_flow_cutover, [100], "missing-flow-import")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET source_receipt_vnd=NULL "
           f"WHERE customer_id={missing_flow}")
    reject_call(pg, "verify_cutover_customer", missing_flow, missing_flow_cutover,
                version(pg, missing_flow), "missing-flow-verify", None,
                error="CUTOVER_MONTH_MISMATCH")
    # Real automatic policy; no fake signoff function in harness.
    contradictory, contradictory_cutover = cutover_book(pg, 300)
    import_book(pg, contradictory, contradictory_cutover, [100, 200], "anchor-import")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET opening_anchor_vnd=0, "
           f"source_cumulative_vnd=CASE WHEN debt_month='2026-01-01' THEN 110 ELSE 310 END, "
           f"replay_cumulative_vnd=CASE WHEN debt_month='2026-01-01' THEN 110 ELSE 310 END "
           f"WHERE customer_id={contradictory}")
    reject_call(pg, "verify_cutover_customer", contradictory, contradictory_cutover,
                version(pg, contradictory), "anchor-contradiction", "FAKE-SIGNOFF",
                error="CUTOVER_ANCHOR_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={contradictory}") == "draft",
            "self-contradictory first source anchor verified")
    absent, absent_cutover = cutover_book(pg, 100)
    import_book(pg, absent, absent_cutover, [100], "no-first-anchor")
    pg.sql(f"UPDATE sokhach.cutover_month_check SET opening_anchor_vnd=NULL "
           f"WHERE customer_id={absent}")
    reject_call(pg, "verify_cutover_customer", absent, absent_cutover,
                version(pg, absent), "no-first-anchor-verify", "FAKE-SIGNOFF",
                error="CUTOVER_MONTH_MISMATCH")
    # Initial 50 belongs in oldest monthly bucket; final anchor is 350.
    nonzero, nonzero_cutover = cutover_book(pg, 350)
    opening, legacy, checks = import_data([150, 200], charges=[100, 200], opening_anchor=50)
    call(pg, "import_cutover", nonzero, 0, "nonzero-anchor-import", nonzero_cutover,
         opening, legacy, checks, 350, "a" * 64)
    require(call(pg, "verify_cutover_customer", nonzero, nonzero_cutover,
                 version(pg, nonzero), "nonzero-anchor-verify", None)["status"] ==
             "verified", "initial 50 was not included in oldest FIFO bucket")
    lost, lost_cutover = cutover_book(pg, 300)
    opening, legacy, checks = import_data([100, 200], charges=[100, 200], opening_anchor=50)
    call(pg, "import_cutover", lost, 0, "lost-anchor-import", lost_cutover,
         opening, legacy, checks, 300, "a" * 64)
    reject_call(pg, "verify_cutover_customer", lost, lost_cutover, version(pg, lost),
                "lost-anchor-verify", None, error="CUTOVER_FIFO_MISMATCH")
    fifo, fifo_cutover = cutover_book(pg, 150)
    opening, legacy, checks = import_data([0, 150], charges=[100, 200], receipts=[0, 150])
    call(pg, "import_cutover", fifo, 0, "fifo-import", fifo_cutover,
         opening, legacy, checks, 150, "a" * 64)
    require(call(pg, "verify_cutover_customer", fifo, fifo_cutover, version(pg, fifo),
                 "fifo-verify", None)["status"] == "verified", "FIFO [0,150] rejected")
    wrong_fifo, wrong_fifo_cutover = cutover_book(pg, 150)
    opening, legacy, checks = import_data([100, 50], charges=[100, 200],
                                         receipts=[0, 150])
    call(pg, "import_cutover", wrong_fifo, 0, "wrong-fifo-import", wrong_fifo_cutover,
         opening, legacy, checks, 150, "a" * 64)
    reject_call(pg, "verify_cutover_customer", wrong_fifo, wrong_fifo_cutover,
                version(pg, wrong_fifo), "wrong-fifo-verify", None,
                error="CUTOVER_FIFO_MISMATCH")
    reject_call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer),
                "early-customer", "FAKE-SIGNOFF", error="CUTOVER_TRANSITION_ORDER")
    reject_call(pg, "verify_cutover", cutover, "early-cutover", "FAKE-SIGNOFF",
                error="CUTOVER_CUSTOMERS_NOT_VERIFIED")
    verified = call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer),
                    "gate-verify-customer", "FAKE-SIGNOFF")
    require(verified["status"] == "verified", "customer verification missing")
    require(pg.value(f"SELECT count(*) FROM sokhach.cutover_customer "
                     f"WHERE customer_id={customer} AND cutover_id={cutover} AND status='verified'") == "1"
            and pg.value(f"SELECT count(*) FROM sokhach.idempotency "
                         f"WHERE customer_id={customer} AND key='gate-verify-customer'") == "1"
            and call(pg, "verify_cutover_customer", customer, cutover, 0,
                     "gate-verify-customer", "FAKE-SIGNOFF") == verified,
            "automatic verification yielded more than one result")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "verified leaked")
    reject_call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer),
                "early-activate", "FAKE-SIGNOFF", error="CUTOVER_TRANSITION_ORDER")
    # Other cutover has a draft customer; whole-cutover gate must ignore it.
    other_customer, other_cutover = cutover_book(pg, 1)
    import_book(pg, other_customer, other_cutover, [1], "other-cutover-import")
    all_verified = call(pg, "verify_cutover", cutover, "gate-verify-all", "FAKE-SIGNOFF")
    require(all_verified["status"] == "verified", "cutover verification missing")
    require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={other_customer}")
            == "draft", "whole-cutover gate changed other cutover")
    reject_call(pg, "verify_cutover", other_cutover, "other-verify-all", "FAKE-SIGNOFF",
                error="CUTOVER_CUSTOMERS_NOT_VERIFIED")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "verified cutover leaked")
    active = call(pg, "activate_cutover", cutover, "gate-activate-all", "FAKE-SIGNOFF")
    require(active["status"] == "active", "cutover activation missing")
    require(call(pg, "get_ledger", customer)["status"] == "NO_BASELINE", "one-sided active leaked")
    customer_active = call(pg, "activate_cutover_customer", customer, cutover,
                           version(pg, customer), "gate-activate-customer", "FAKE-SIGNOFF")
    require(customer_active["status"] == "active", "customer activation missing")
    ledger = call(pg, "get_ledger", customer)
    require(ledger["total_outstanding_vnd"] == "300" and len(ledger["months"]) == 2,
            "active opening wrong or legacy doubled")
    require(call(pg, "verify_cutover", cutover, "gate-verify-all", "FAKE-SIGNOFF") == all_verified,
            "whole-cutover retry changed result")
    reject_call(pg, "verify_cutover", cutover, "gate-verify-all", "changed-ref",
                error="IDEMPOTENCY_CONFLICT")
    zero, zero_cutover = cutover_book(pg, 0)
    import_book(pg, zero, zero_cutover, [0], "zero-import")
    call(pg, "verify_cutover_customer", zero, zero_cutover, version(pg, zero),
         "zero-verify", "FAKE-SIGNOFF")
    call(pg, "verify_cutover", zero_cutover, "zero-verify-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover", zero_cutover, "zero-activate-all", "FAKE-SIGNOFF")
    call(pg, "activate_cutover_customer", zero, zero_cutover, version(pg, zero),
         "zero-activate-customer", "FAKE-SIGNOFF")
    require(call(pg, "get_ledger", zero)["total_outstanding_vnd"] == "0",
            "explicit zero baseline failed")
    mismatch, mismatch_cutover = cutover_book(pg, 301)
    import_book(pg, mismatch, mismatch_cutover, [100, 200], "total-import")
    call(pg, "verify_cutover_customer", mismatch, mismatch_cutover, version(pg, mismatch),
         "total-verify-customer", "FAKE-SIGNOFF")
    reject_call(pg, "verify_cutover", mismatch_cutover, "total-verify-all", "FAKE-SIGNOFF",
                error="CUTOVER_TOTAL_MISMATCH")
    require(pg.value(f"SELECT status FROM sokhach.cutover WHERE id={mismatch_cutover}") == "draft",
            "wrong whole-cutover total verified")


def check_import_behavior(pg: Pg) -> str:
    customer, cutover = cutover_book(pg, 100)
    args = (customer, 0, "import-retry", cutover, *import_data([100]), 100, "a" * 64)
    first = call(pg, "import_cutover", *args)
    require(call(pg, "import_cutover", *args) == first, "same-key import retry changed result")
    reject_call(pg, "import_cutover", customer, 0, "import-retry", cutover,
                *import_data([101]), 100, "a" * 64, error="IDEMPOTENCY_CONFLICT")
    reject_call(pg, "import_cutover", customer, 0, "import-stale", cutover,
                *import_data([100]), 100, "a" * 64, error="STALE_LEDGER")
    reject_call(pg, "import_cutover", customer, version(pg, customer), "import-duplicate", cutover,
                *import_data([100]), 100, "a" * 64, error="CUTOVER_IMPORT_CONFLICT")
    empty_customer, empty_cutover = cutover_book(pg, 0)
    empty_args = (empty_customer, 0, "empty-import", empty_cutover,
                  *import_data([]), 0, "a" * 64)
    empty_result = call(pg, "import_cutover", *empty_args)
    require(call(pg, "import_cutover", *empty_args) == empty_result,
            "empty opening retry changed result")
    reject_call(pg, "import_cutover", empty_customer, version(pg, empty_customer),
                "empty-duplicate", empty_cutover, *import_data([]), 0, "a" * 64,
                error="CUTOVER_IMPORT_CONFLICT")
    bad_customer, bad_cutover = cutover_book(pg, 100)
    reject_call(pg, "import_cutover", bad_customer, 0, "one-dong", bad_cutover,
                *import_data([100]), 101, "a" * 64, error="CUTOVER_CUSTOMER_TOTAL_MISMATCH")
    pg.true(f"NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer WHERE customer_id={bad_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.event WHERE customer_id={bad_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.opening_balance WHERE customer_id={bad_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.idempotency WHERE customer_id={bad_customer})",
            "one-dong rejection left partial rows")
    late_customer, late_cutover = cutover_book(pg, 200)
    late_openings, _, late_checks = import_data([100, 100])
    duplicate_legacy = json.dumps([{"debt_month": "2026-01-01", "kind": "trip",
        "display": {}, "source_tab": "FAKE", "source_row": 77},
        {"debt_month": "2026-02-01", "kind": "trip", "display": {},
         "source_tab": "FAKE", "source_row": 77}])
    reject_call(pg, "import_cutover", late_customer, 0, "late-fail", late_cutover,
                late_openings, duplicate_legacy, late_checks, 200, "a" * 64,
                error="duplicate key")
    pg.true(f"NOT EXISTS(SELECT 1 FROM sokhach.cutover_customer WHERE customer_id={late_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.event WHERE customer_id={late_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.opening_balance WHERE customer_id={late_customer}) "
            f"AND NOT EXISTS(SELECT 1 FROM sokhach.legacy_row WHERE customer_id={late_customer})",
            "late failure left partial rows")
    flagged, flagged_cutover = cutover_book(pg, 600)
    import_book(pg, flagged, flagged_cutover, [600], "flagged-import",
                flags=[["NO_BASELINE", "MISSING_PRICE", "MISSING_CACHE",
                        "HISTORICAL_DELTA_600"]])
    pg.true(f"EXISTS(SELECT 1 FROM sokhach.cutover_month_check WHERE customer_id={flagged} "
            "AND exception_codes @> ARRAY['NO_BASELINE','MISSING_PRICE','MISSING_CACHE',"
            "'HISTORICAL_DELTA_600']::text[])",
            "source exception flags lost")
    draft_ledger = call(pg, "get_ledger", flagged)
    require(draft_ledger["status"] == "NO_BASELINE"
            and len(draft_ledger["source_exceptions"][0]["exception_codes"]) == 4,
            "draft flags hidden or draft amount leaked")
    require(call(pg, "verify_cutover_customer", flagged, flagged_cutover, version(pg, flagged),
                 "flagged-verify", None)["status"] == "verified", "flags blocked mechanical gate")
    call(pg, "verify_cutover", flagged_cutover, "flagged-all", None)
    call(pg, "activate_cutover", flagged_cutover, "flagged-active", None)
    call(pg, "activate_cutover_customer", flagged, flagged_cutover, version(pg, flagged),
         "flagged-customer-active", None)
    require(set(call(pg, "get_ledger", flagged)["source_exceptions"][0]["exception_codes"])
            == {"NO_BASELINE", "MISSING_PRICE", "MISSING_CACHE", "HISTORICAL_DELTA_600"},
            "source flags missing from active ledger")
    live, live_cutover = cutover_book(pg, 0)
    reject_call(pg, "record_receipt", live, version(pg, live), "unbased-receipt",
                "2026-01-01", "THU TIỀN", 1, error="NO_BASELINE")
    pg.sql(f"INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
           f"VALUES({live},'paste','harness','{{}}','{{\"trips\":[]}}')")
    reject_call(pg, "import_cutover", live, 0, "late-import", live_cutover,
                *import_data([]), 0, "a" * 64, error="CUTOVER_IMPORT_CONFLICT")
    observed = check_import_verify_locks(pg)
    single = check_single_verification_result(pg)
    return ("retry, one-dong rollback, source flags, NO_BASELINE, live-event guard; "
            + observed + "; " + single)


def check_single_verification_result(pg: Pg) -> str:
    customer, cutover = cutover_book(pg, 100)
    import_book(pg, customer, cutover, [100], "race-import")
    a, b = PsqlSession(pg, f"v7_verify_a_{customer}"), PsqlSession(pg, f"v7_verify_b_{customer}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='race-a'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.verify_cutover_customer({customer},{cutover},1,'race-a','FAKE-SIGNOFF')")
        result = json.loads(a.line())
        b.send("BEGIN; SET LOCAL sokhach.actor='race-b'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.verify_cutover_customer({customer},{cutover},1,'race-b','FAKE-SIGNOFF')")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and pg.value(
                f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") != "t":
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t",
                "second verify did not wait for first")
        a.send("COMMIT; SELECT 'committed'")
        require(a.line() == "committed", "first verification did not commit")
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("STALE_LEDGER" in stderr and result["status"] == "verified",
                f"second verification did not reject stale version: {stderr[-500:]}")
        require(version(pg, customer) == 2 and pg.value(
            f"SELECT count(*) FROM sokhach.idempotency WHERE customer_id={customer} "
            "AND key IN ('race-a','race-b')") == "1",
            "automatic-policy race produced more than one result")
    finally:
        a.close()
        b.close()
    return "one verified result and one stale rejection under fake policy"


def check_import_verify_locks(pg: Pg) -> str:
    """Cutover lock must block command before its customer lock, in both orders."""

    def worker(name: str, command: str) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ["docker", "exec", "--env", f"PGAPPNAME={name}", "--env",
             "PGOPTIONS=-c statement_timeout=20000 -c lock_timeout=18000",
             pg.name, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE, "-c", actor_sql(command)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace")

    def blockers(name: str) -> tuple[int | None, set[int]]:
        rows = pg.value("SELECT pid::text || '|' || array_to_string(pg_blocking_pids(pid), ',') "
            "FROM pg_stat_activity WHERE datname=current_database() "
            "AND state='active' AND wait_event_type='Lock' "
            f"AND application_name={lit(name)}").splitlines()
        require(len(rows) <= 1, f"multiple PostgreSQL sessions for {name}: {rows}")
        if not rows:
            return None, set()
        return parse_blocker_row(rows[0])

    def wait_blocked(name: str, expected: set[int], process: subprocess.Popen[str]) -> int:
        deadline = time.monotonic() + 8
        observed: tuple[int | None, set[int]] = (None, set())
        while time.monotonic() < deadline:
            observed = blockers(name)
            if observed[1] & expected:
                return observed[0]
            if process.poll() is not None:
                break
            time.sleep(0.05)  # polling only; pg_blocking_pids is lock evidence
        raise HarnessError(f"{name} did not block on cutover queue: "
                           f"pid/blockers={observed}, exit={process.poll()}")

    def finish(process: subprocess.Popen[str], error: str | None,
               status: str | None = None) -> None:
        try:
            out, err = process.communicate(timeout=22)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise HarnessError("import/verify worker timed out") from exc
        require("40P01" not in err and "deadlock detected" not in err,
                f"import/verify deadlock: {err[-600:]}")
        if error is None:
            require(process.returncode == 0, f"import worker failed: {out} {err[-600:]}")
            require(json.loads(out.strip())["status"] == status,
                    f"worker returned wrong status: {out} {err[-600:]}")
        else:
            require(process.returncode != 0 and error in err,
                    f"verify worker had unexpected outcome: {out} {err[-600:]}")

    def import_sql(c: int, key: str) -> str:
        args = (c, 0, key, cutover, *import_data([100]), 100, "a" * 64)
        return "SELECT sokhach.import_cutover(" + ",".join(lit(x) for x in args) + ")"

    def verify_sql(c: int, key: str) -> str:
        args = (c, cutover, version(pg, c), key, "FAKE-SIGNOFF")
        return "SELECT sokhach.verify_cutover_customer(" + ",".join(lit(x) for x in args) + ")"

    for direction in ("import-first", "verify-first"):
        customer, cutover = cutover_book(pg, 100)
        holder_name = f"v7_cutover_holder_{pg.run_id}"
        holder = PsqlSession(pg, holder_name)
        first = second = None
        try:
            holder.send("BEGIN")
            holder.send(f"SELECT pg_backend_pid() FROM sokhach.cutover WHERE id={cutover} FOR UPDATE")
            holder_pid = int(holder.line())
            require(pg.value(f"SELECT application_name FROM pg_stat_activity WHERE pid={holder_pid}")
                    == holder_name, "cutover holder PID/application_name mismatch")
            if direction == "import-first":
                first_name = f"v7_import_{pg.run_id}"
                first = worker(first_name, import_sql(customer, "lock-import"))
                first_error = None
                second_name = f"v7_verify_{pg.run_id}"
                second_command = verify_sql(customer, "lock-verify")
            else:
                first_name = f"v7_verify2_{pg.run_id}"
                first = worker(first_name, verify_sql(customer, "lock-verify2"))
                first_error = "CUTOVER_TRANSITION_ORDER"
                second_name = f"v7_import2_{pg.run_id}"
                second_command = import_sql(customer, "lock-import2")
            first_pid = wait_blocked(first_name, {holder_pid}, first)
            pg.value(f"BEGIN; SELECT id FROM sokhach.customer WHERE id={customer} FOR UPDATE NOWAIT; COMMIT")
            second = worker(second_name, second_command)
            # pg_blocking_pids may name first waiter as soft blocker of second.
            wait_blocked(second_name, {holder_pid, first_pid}, second)
            require(holder_pid in blockers(first_name)[1],
                    "first worker no longer blocked by cutover holder")
        finally:
            holder.close()
        if first is not None:
            finish(first, first_error, "draft" if direction == "import-first" else None)
        if second is not None:
            finish(second, "STALE_LEDGER" if direction == "import-first" else None,
                   "draft" if direction == "verify-first" else None)
        require(pg.value(f"SELECT status FROM sokhach.cutover_customer WHERE customer_id={customer}")
                == "draft" and version(pg, customer) == 1,
                f"{direction} did not leave exactly one draft import")
    return ("pg_blocking_pids: import then stale verify; "
            "transition-order verify then successful draft import")


def check_opening_fifo(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100), ("2026-02-01", 200))
    call(pg, "set_month_lock", c, 0, "fifo-open", "2026-01-01", "false")
    opening = pg.value(f"SELECT string_agg(amount_vnd::text,',' ORDER BY debt_month) FROM sokhach.opening_balance WHERE customer_id={c}")
    call(pg, "record_receipt", c, 1, "fifo-r", "2026-03-01", "THU TIỀN", 150)
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "100"),
             ("2026-02-01", "debt", "50")], "receipt did not use old opening first")
    call(pg, "adjust_month", c, 2, "fifo-a", "2026-01-01", 60, "giá mới")
    require(allocations(pg, c, "PH-001") == [("2026-01-01", "debt", "150")]
            and [r[1] for r in months(pg, c)] == ["10", "200", "0"], "adjustment did not reallocate FIFO")
    require(pg.value(f"SELECT string_agg(amount_vnd::text,',' ORDER BY debt_month) FROM sokhach.opening_balance WHERE customer_id={c}") == opening,
            "opening changed after reallocation")
    assert_allocations(pg, c)


def check_dashboard(pg: Pg) -> None:
    before = call(pg, "get_dashboard")
    current = pg.value("SELECT date_trunc('month',now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    recent = pg.value("SELECT (date_trunc('month',now() AT TIME ZONE 'Asia/Ho_Chi_Minh')-interval '2 months')::date")
    old = pg.value("SELECT (date_trunc('month',now() AT TIME ZONE 'Asia/Ho_Chi_Minh')-interval '7 months')::date")
    today = pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    positive = new_book(pg, (old, 100), (recent, 200))
    credit = new_book(pg, ("2026-01-01", -50))
    zero = new_book(pg, ("2026-01-01", 0))
    classified = new_book(pg, (current, 25))
    commodity = int(pg.value("INSERT INTO sokhach.commodity(name) VALUES ('FAKE COMMODITY') RETURNING id"))
    pg.sql(f"UPDATE sokhach.customer SET commodity_id={commodity},transport_mode='CANG' WHERE id={classified}")
    no_base = int(pg.value("INSERT INTO sokhach.customer(name) VALUES ('FAKE NO BASELINE') RETURNING id"))
    batch = json.dumps([json.loads(trip_json(month=current))[0],
                        json.loads(trip_json(container="FAKE-D", month=current))[0]])
    call(pg, "paste_trips", positive, version(pg, positive), "dash-paste", current, batch)
    call(pg, "paste_trips", positive, version(pg, positive), "dash-missing", current,
         trip_json(None, container="FAKE-M", month=current))
    call(pg, "paste_trips", positive, version(pg, positive), "dash-pending", current,
         trip_json(container="FAKE-C", month=current))
    call(pg, "record_receipt", positive, version(pg, positive), "dash-receipt", today, "THU TIỀN", 25)
    call(pg, "void_receipt", positive, version(pg, positive), "dash-void", "PH-001", "dash void")
    result = call(pg, "get_dashboard")
    customers = call(pg, "list_customers")["customers"]
    active = [(c, call(pg, "get_ledger", c["id"])) for c in customers if c["status"] == "active"]
    positive_ledgers = [(c, ledger, int(ledger["total_outstanding_vnd"]))
                        for c, ledger in active if int(ledger["total_outstanding_vnd"]) > 0]
    negative_ledgers = [(c, ledger, int(ledger["total_outstanding_vnd"]))
                        for c, ledger in active if int(ledger["total_outstanding_vnd"]) < 0]
    require(int(result["receivable"]["total_vnd"]) - int(before["receivable"]["total_vnd"]) == 525
            and result["receivable"]["customers"] - before["receivable"]["customers"] == 2,
            f"dashboard receivable delta: {before['receivable']} -> {result['receivable']}")
    require(int(result["credit"]["total_vnd"]) - int(before["credit"]["total_vnd"]) == -50
            and result["credit"]["customers"] - before["credit"]["customers"] == 1,
            f"dashboard credit delta: {before['credit']} -> {result['credit']}")
    require(result["receivable"] == {"total_vnd": str(sum(x[2] for x in positive_ledgers)),
                                     "customers": len(positive_ledgers)},
            "dashboard positive get_ledger reconciliation")
    require(result["credit"] == {"total_vnd": str(sum(x[2] for x in negative_ledgers)),
                                 "customers": len(negative_ledgers)},
            "dashboard credit get_ledger reconciliation")
    receivable = int(result["receivable"]["total_vnd"])
    require(sum(int(x["receivable_vnd"]) for x in result["aging"]) == receivable,
            "dashboard aging total")
    require(sum(int(x["receivable_vnd"]) for x in result["by_commodity"]) == receivable,
            "dashboard commodity total")
    require([x["bucket"] for x in result["aging"]] == ["current", "1-2", "3-6", "over-6"],
            "dashboard aging buckets")
    require(any(x["commodity"] == "FAKE COMMODITY" and x["transport_mode"] == "CANG"
                and x["customers"] == 1 for x in result["by_commodity"]),
            "dashboard commodity grouping")
    expected_top = [x[0]["id"] for x in sorted(positive_ledgers,
                    key=lambda x: (-x[2], x[0]["name"], x[0]["id"]))[:10]]
    require([x["customer_id"] for x in result["top_debtors"]] == expected_top,
            "dashboard top debtor order")
    positive_top = next((x for x in result["top_debtors"] if x["customer_id"] == positive), None)
    require(positive_top is not None and positive_top["oldest_open_month"] == old,
            "dashboard oldest open month")
    aging = {x["bucket"]: int(x["receivable_vnd"]) for x in result["aging"]}
    before_aging = {x["bucket"]: int(x["receivable_vnd"]) for x in before["aging"]}
    require({key: aging[key] - before_aging[key] for key in aging}
            == {"current": 225, "1-2": 200, "3-6": 0, "over-6": 100},
            "dashboard aging month boundaries")
    require(result["today"]["trips"] - before["today"]["trips"] == 4
            and result["today"]["receipts"] - before["today"]["receipts"] == 1
            and int(result["today"]["received_vnd"]) - int(before["today"]["received_vnd"]) == 25
            and result["today"]["voids"] - before["today"]["voids"] == 1,
            "dashboard today event counts")
    actor = next(x for x in result["today"]["by_actor"] if x["actor"] == "harness")
    before_actor = next((x for x in before["today"]["by_actor"] if x["actor"] == "harness"),
                        {"trips": 0, "receipts": 0, "received_vnd": "0", "voids": 0})
    require(actor["trips"] - before_actor["trips"] == 4
            and actor["receipts"] - before_actor["receipts"] == 1
            and int(actor["received_vnd"]) - int(before_actor["received_vnd"]) == 25
            and actor["voids"] - before_actor["voids"] == 1, "dashboard actor counts")
    require(any(x["customer_id"] == no_base for x in result["todo"]["no_baseline"])
            and any(x["customer_id"] == positive for x in result["todo"]["missing_price"])
            and any(x["customer_id"] == positive for x in result["todo"]["pending_review"])
            and any(x["customer_id"] == credit for x in result["todo"]["credit"])
            and zero not in [x["customer_id"] for x in result["todo"]["credit"]], "dashboard todo boundaries")
    pg.sql("INSERT INTO sokhach.event(customer_id,kind,actor,at,\"before\",\"after\") "
           f"VALUES ({positive},'paste','late',(((now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date "
           "+ time '23:30') AT TIME ZONE 'Asia/Ho_Chi_Minh'),'{}','{\"trips\":[{}]}')")
    pg.sql("INSERT INTO sokhach.event(customer_id,kind,actor,at,\"before\",\"after\") "
           f"VALUES ({positive},'paste','tomorrow',((((now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date + 1) "
           "+ time '00:30') AT TIME ZONE 'Asia/Ho_Chi_Minh'),'{}','{\"trips\":[{}]}')")
    boundary = call(pg, "get_dashboard")
    require(boundary["today"]["trips"] == result["today"]["trips"] + 1
            and any(x["actor"] == "late" and x["trips"] == 1 for x in boundary["today"]["by_actor"])
            and not any(x["actor"] == "tomorrow" for x in boundary["today"]["by_actor"]),
            "dashboard Asia/Ho_Chi_Minh event boundary")


def check_model(pg: Pg) -> None:
    # Identical two-month fixture and operation order in Node and PostgreSQL.
    js = r"""
const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');
const book={months:['2026-01','2026-02'].map((key,i)=>({key,
  trips:[{container:'FAKE-C',unitPriceVnd:'100',otherFeeVnd:null}],receipts:[],adjustments:[]}))};
const month=k=>book.months.find(x=>x.key===k);
const apply=()=>{const p=m.planReallocation(book);for(const x of book.months)x.receipts=x.receipts.filter(r=>r.voided!==null);
  for(const x of p.lines)month(x.monthKey).receipts.push(x.receipt)};
// V7-SO (29/10/2026): ghi phiếu mới cũng phân bổ lại theo (ngày, mã phiếu) như server.
const add=(pid,date,amount)=>{const p=m.planReceipt(book,{pid,date,method:'THU TIỀN',amountVnd:amount});
  for(const x of p.lines)month(x.monthKey).receipts.push({pid,date,method:'THU TIỀN',amountVnd:x.amountVnd,kind:x.kind,voided:null});apply()};
const snap=()=>({months:m.outstandingByMonth(book).map(x=>[x.monthKey,x.outstandingVnd.toString()]),
  total:m.monthChain(book).totalOutstandingVnd.toString(),
  receipts:Object.fromEntries(['PH-001','PH-002','PH-003'].map(pid=>[pid,book.months.flatMap(x=>
    x.receipts.filter(r=>r.pid===pid&&r.voided===null).map(r=>[x.key,r.kind,r.amountVnd]))]))});
const out=[];add('PH-001','03/01/2026','120');out.push(snap());
const t=month('2026-01').trips[0];
for(const [target,note] of [['80','lần một'],['110','lần hai']]){
  month('2026-01').adjustments.push(m.planAdjustment(book,{'2026-01':true},
    {monthKey:'2026-01',lineId:'2026-01#0',newAmountVnd:target,reason:note}));apply();out.push(snap())}
for(const amount of ['+20','-10']){month('2026-01').adjustments.push(
  m.planMonthAdjustment(book,{monthKey:'2026-01',amount,reason:'tháng'}));apply();out.push(snap())}
add('PH-002','02/01/2026','20');out.push(snap());
for(const date of ['04/01/2026','02/01/2026']){
  const edit=m.planReceiptEdit(book,'PH-001',{date});
  for(const x of edit.lines)month(x.monthKey).receipts[x.index]=x.receipt;
  apply();out.push(snap());
}
const voided=m.planVoid(book,'PH-001','sai','20/10/2026');
for(const x of voided.lines)month(x.monthKey).receipts[x.index]=x.receipt;out.push(snap());
add('PH-003','04/01/2026','30');out.push(snap());
console.log(JSON.stringify(out));
"""
    expected = run_node(js)
    c = new_book(pg)
    for month in ("2026-01-01", "2026-02-01"):
        call(pg, "set_month_lock", c, version(pg, c), "open-" + month, month, "false")
        call(pg, "paste_trips", c, version(pg, c), "paste-" + month, month, trip_json(container="FAKE-" + month, month=month))
    trip = int(pg.value(f"SELECT id FROM sokhach.trip WHERE customer_id={c} AND debt_month='2026-01-01'"))
    actions = [
        ("record_receipt", ("2026-01-03", "THU TIỀN", 120)),
        ("adjust_trip", (trip, 80, "lần một")),
        ("adjust_trip", (trip, 110, "lần hai")),
        ("adjust_month", ("2026-01-01", 20, "tháng")),
        ("adjust_month", ("2026-01-01", -10, "tháng")),
        ("record_receipt", ("2026-01-02", "THU TIỀN", 20)),
        ("edit_receipt_meta", ("PH-001", "2026-01-04", None)),
        ("edit_receipt_meta", ("PH-001", "2026-01-02", None)),
        ("void_receipt", ("PH-001", "sai")),
        ("record_receipt", ("2026-01-04", "THU TIỀN", 30)),
    ]
    for index, ((name, args), want) in enumerate(zip(actions, expected, strict=True), 1):
        result = call(pg, name, c, version(pg, c), f"model-{index}", *args)
        got_rows = months(pg, c)
        got = {"months": [[m, amount] for m, amount, _ in got_rows],
               "total": call(pg, "get_ledger", c)["total_outstanding_vnd"],
               "receipts": {pid: [[m[:7], kind, amount] for m, kind, amount in allocations(pg, c, pid)]
                            for pid in ("PH-001", "PH-002", "PH-003")}}
        require(got == want, f"JS/SQL operation {index} {name} differs: {got} != {want}")
        if name in ("adjust_trip", "adjust_month", "edit_receipt_meta"):
            prior = expected[index - 2]["receipts"]
            changed = sorted(pid for pid in want["receipts"]
                             if {r[0] for r in prior[pid]} !=
                                {r[0] for r in want["receipts"][pid]})
            returned = sorted(item["pid"] for item in result["reallocated"]
                              if {line["month"][:7] for line in item["before"]} !=
                                 {line["month"][:7] for line in item["after"]})
            require(returned == changed,
                    f"operation {index} changed receipt-month list differs: {returned} != {changed}")
        assert_allocations(pg, c)


def check_model_edges(pg: Pg) -> None:
    c = new_book(pg, ("2025-12-01", 100))
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    first = call(pg, "record_receipt", c, 0, "edge-advance", "2026-02-01", "THU TIỀN", 150)
    require(first["overpayment_vnd"] == "50" and allocations(pg, c, "PH-001") ==
            [("2025-12-01", "debt", "100"), ("2025-12-01", "advance", "50")],
            "receipt over debt did not create advance")
    missing = call(pg, "paste_trips", c, 1, "edge-missing", current,
                   trip_json(None, month=current))["trip_ids"][0]
    require(call(pg, "get_ledger", c)["pending_count"] == 1,
            "missing price did not remain pending after receipt")
    call(pg, "edit_trip_price", c, 2, "edge-price", missing, 20, None)
    require(call(pg, "get_ledger", c)["pending_count"] == 0 and
            allocations(pg, c, "PH-001")[-1] == (current, "advance", "30"),
            "pricing pending trip did not move advance to last month")
    priced = call(pg, "paste_trips", c, 3, "edge-paste-after-receipt", current,
                  trip_json("40", container="FAKE-NEW", month=current))["trip_ids"][0]
    require(priced != missing and allocations(pg, c, "PH-001") ==
            [("2025-12-01", "debt", "100"), (current, "debt", "50")],
            "paste after receipt did not reallocate FIFO")
    call(pg, "void_receipt", c, 4, "edge-void", "PH-001", "sai")
    before = months(pg, c)
    call(pg, "adjust_month", c, 5, "edge-adjust-after-void", current, 10, "sửa")
    require(allocations(pg, c, "PH-001") == [] and
            [int(row[1]) for row in months(pg, c)] == [int(row[1]) for row in before[:-1]] +
            [int(before[-1][1]) + 10], "adjustment after void moved canceled receipt")
    assert_allocations(pg, c)


def check_golden(pg: Pg) -> None:
    fixture = run_node("console.log(JSON.stringify(require('./cong-no-web-handoff/preview/so-khach-v7-fixture.js')))")
    c = new_book(pg)
    trips = [{"month": m["key"] + "-01", "trip": t} for m in fixture["months"] for t in m["trips"]]
    receipts: dict[str, dict] = {}
    for month in fixture["months"]:
        for line in month["receipts"]:
            require(line["voided"] is None, "golden fixture contains unsupported voided line")
            item = receipts.setdefault(line["pid"], {"pid": line["pid"], "date": line["date"],
                "method": line["method"], "amount": 0, "lines": []})
            item["amount"] += int(line["amountVnd"])
            item["lines"].append({"month": month["key"] + "-01", "kind": line.get("kind", "debt"),
                                  "amount": line["amountVnd"]})
    # One psql transaction; large fixture travels on stdin, never command line.
    script = """BEGIN;
DO $fixture$ DECLARE t jsonb; r jsonb; l jsonb; v_event bigint; v_trip bigint;
 v_receipt bigint; v_lines jsonb; v_line jsonb;
BEGIN
INSERT INTO sokhach.event(customer_id,kind,actor,"before","after")
VALUES (CUSTOMER,'paste','harness','{}','{"trips":[]}') RETURNING id INTO v_event;
FOR t IN SELECT value FROM jsonb_array_elements(TRIPS::jsonb) LOOP
 INSERT INTO sokhach.trip(customer_id,debt_month,event_date,container,carrier,origin,destination,
 note,source_ref,created_by_event) VALUES (CUSTOMER,(t->>'month')::date,
  CASE WHEN t->'trip'->>'date' IS NULL THEN NULL
      ELSE to_date(t->'trip'->>'date','DD/MM/YYYY') END,
 t->'trip'->>'container',t->'trip'->>'carrier',
 t->'trip'->>'from',t->'trip'->>'to',t->'trip'->>'note',t->'trip'->>'src',v_event)
 RETURNING id INTO v_trip;
 INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
 VALUES(v_trip,CUSTOMER,(t->'trip'->>'unitPriceVnd')::bigint,
 (t->'trip'->>'otherFeeVnd')::bigint,v_event);
 IF t->'trip'->>'otherFeeVnd' IS NOT NULL AND (t->'trip'->>'otherFeeVnd')::bigint<>0 THEN
  INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
  SELECT CUSTOMER,v_trip,f.id,(t->'trip'->>'otherFeeVnd')::bigint,v_event
    FROM sokhach.fee_type f WHERE f.system_key=CASE WHEN (t->'trip'->>'otherFeeVnd')::bigint<0 THEN 'discount' ELSE 'other' END;
 END IF;
END LOOP;
FOR r IN SELECT value FROM jsonb_array_elements(RECEIPTS::jsonb) LOOP
 v_receipt:=nextval(pg_get_serial_sequence('sokhach.receipt','id'));
 v_lines:='[]'::jsonb;
 FOR l IN SELECT value FROM jsonb_array_elements(r->'lines') LOOP
  v_line:=jsonb_build_object('id',nextval(pg_get_serial_sequence('sokhach.receipt_line','id')),
   'month',l->>'month','kind',l->>'kind','amount_vnd',l->>'amount');
  v_lines:=v_lines||jsonb_build_array(v_line);
 END LOOP;
 INSERT INTO sokhach.event(customer_id,kind,actor,"before","after") VALUES
 (CUSTOMER,'receipt','harness','{}',jsonb_build_object('receipt',v_receipt,'pid',r->>'pid',
  'allocations',v_lines)) RETURNING id INTO v_event;
 INSERT INTO sokhach.receipt(id,customer_id,pid,date,method,amount_vnd,created_by_event)
 OVERRIDING SYSTEM VALUE VALUES(v_receipt,CUSTOMER,r->>'pid',to_date(r->>'date','DD/MM/YYYY'),
 r->>'method',(r->>'amount')::bigint,v_event);
 FOR l IN SELECT value FROM jsonb_array_elements(v_lines) LOOP
  INSERT INTO sokhach.receipt_line(id,receipt_id,customer_id,debt_month,kind,amount_vnd,created_by_event)
  OVERRIDING SYSTEM VALUE VALUES((l->>'id')::bigint,v_receipt,CUSTOMER,(l->>'month')::date,
  l->>'kind',(l->>'amount_vnd')::bigint,v_event);
 END LOOP;
END LOOP;
END $fixture$;
COMMIT;
"""
    script = script.replace("CUSTOMER", str(c)).replace("TRIPS", lit(json.dumps(trips, ensure_ascii=False)))
    script = script.replace("RECEIPTS", lit(json.dumps(list(receipts.values()), ensure_ascii=False)))
    p = run(["docker", "exec", "-i", *pg.env, pg.name, "psql", "-X", "-v", "ON_ERROR_STOP=1",
             "-U", "postgres", "-d", DATABASE], input_text=script, timeout=120)
    require(p.returncode == 0, "golden fixture load failed")
    ledger = call(pg, "get_ledger", c)
    expected = run_node("const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');"
        "const f=require('./cong-no-web-handoff/preview/so-khach-v7-fixture.js');"
        "const x=m.monthChain(f);console.log(JSON.stringify({months:x.months.map(r=>"
        "[r.key,r.chargesVnd.toString(),r.receivedVnd.toString(),r.endOfMonthVnd.toString(),"
        "r.lineCount,r.tripCount]),total:x.totalOutstandingVnd.toString(),"
        "ph101:m.planReallocation(f).lines.filter(x=>x.receipt.pid==='PH-101').map(x=>"
        "[x.monthKey+'-01',x.receipt.kind,x.receipt.amountVnd]),"
        "plan:m.planReallocation(f).lines.map(x=>"
        "[x.receipt.pid,x.monthKey,x.receipt.kind,x.receipt.amountVnd]),"
        "changed:m.planReallocation(f).changedPids}))")
    got = []
    bucket_cum = date_cum = 0
    counts = {month: sum(t["month"][:7] == month for t in ledger["trips"])
              for month in (row["month"][:7] for row in ledger["months"])}
    for row in ledger["months"]:
        m = row["month"][:7]
        charges = sum(int(t["amount_vnd"] or 0) for t in ledger["trips"] if t["month"][:7] == m)
        received = sum(int(a["amount_vnd"]) for r in ledger["receipts"] for a in r["allocations"]
                       if r["voided_on"] is None and a["superseded_by_event"] is None
                       and a["month"][:7] == m)
        trip_count = sum(t["month"][:7] == m and not t["is_fee_only"] for t in ledger["trips"])
        # DA-THU-01: cộng dồn của sổ trừ tiền theo ngày thu; đổi về cộng dồn theo kỳ trừ nợ để so với model JS.
        bucket_cum += received
        date_cum += sum(int(r["amount_vnd"]) for r in ledger["receipts"]
                        if r["voided_on"] is None and r["date"][:7] == m)
        by_bucket = int(row["end_of_month_vnd"]) + date_cum - bucket_cum
        got.append([m, str(charges), str(received), str(by_bucket), counts[m], trip_count])
    require(got == expected["months"] and ledger["total_outstanding_vnd"] == expected["total"]
            and len(ledger["months"]) == 11, f"golden monthly totals differ: {got}")
    ph101 = [[line["month"], line["kind"], line["amount_vnd"]]
             for receipt in ledger["receipts"] if receipt["pid"] == "PH-101"
             for line in receipt["allocations"] if line["superseded_by_event"] is None]
    require(ph101 == expected["ph101"] and len(ph101) == 2,
            "PH-101 two-month allocation differs from JS plan")
    require(ledger["pending_count"] == run_node(
        "const m=require('./cong-no-web-handoff/preview/so-khach-v7-model.js');"
        "const f=require('./cong-no-web-handoff/preview/so-khach-v7-fixture.js');"
        "console.log(JSON.stringify(m.pendingCounts(f).missingPrice))"), "golden pending_count differs")
    fee = next(t for t in ledger["trips"] if t["id"] == int(pg.value(
        f"SELECT id FROM sokhach.trip WHERE customer_id={c} AND source_ref='CH:900'")))
    require(fee["is_fee_only"] is True and fee["event_date"] is None
            and fee["amount_vnd"] == "1310000"
            and fee["is_missing_price"] is False, "CH:900 fee-only classification differs")
    replay = pg.value("BEGIN; SET LOCAL sokhach.actor='golden'; "
        f"SELECT sokhach.reallocate({c},'golden-rollback'); "
        "SELECT coalesce(jsonb_agg(jsonb_build_array(r.pid,to_char(l.debt_month,'YYYY-MM'),"
        "l.kind,l.amount_vnd::text) ORDER BY r.pid COLLATE \"C\",l.debt_month,l.kind), '[]'::jsonb) "
        f"FROM sokhach.receipt_line l JOIN sokhach.receipt r ON r.id=l.receipt_id "
        f"WHERE r.customer_id={c} AND l.superseded_by_event IS NULL; ROLLBACK")
    changes, got_plan = map(json.loads, replay.splitlines()[-2:])
    require(expected["changed"] and set(expected["changed"]).issubset(
        {change["pid"] for change in changes}), "golden reallocate made no expected changes")
    require(sorted(got_plan) == sorted(expected["plan"]),
            "golden reallocate differs from independent JS plan")
    require(pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c} AND "
                     "idempotency_key='golden-rollback'") == "0", "golden replay did not rollback")


def check_monthly_identity(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 500), ("2026-02-01", -50), ("2026-03-01", 0))
    call(pg, "set_month_lock", c, 0, "identity-open", "2026-02-01", "false")
    call(pg, "record_receipt", c, 1, "identity-r", "2026-04-01", "THU TIỀN", 100)
    rows = call(pg, "get_ledger", c)["months"]
    # DA-THU-01: phiếu 01/04 trừ nợ tháng 1 nhưng thuộc tháng 4; còn nợ cuối tháng 1 không bị sửa lùi.
    require(rows[0]["charges_vnd"] == "500" and rows[0]["end_of_month_vnd"] == "500"
            and rows[0]["outstanding_vnd"] == "400" and rows[-1]["month"] == "2026-04-01"
            and rows[-1]["received_vnd"] == "100" and rows[-1]["end_of_month_vnd"] == "350",
            "opening absent from charges, counted twice, or receipt not in its date month")
    call(pg, "adjust_month", c, 2, "identity-a", "2026-02-01", -25, "giảm")
    rows = call(pg, "get_ledger", c)["months"]
    require(rows[1]["charges_vnd"] == "-75" and rows[1]["outstanding_vnd"] == "-75",
            "signed opening/adjustment missing from charges")
