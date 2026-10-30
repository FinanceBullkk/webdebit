"""V7 backend harness cases: SCHEMA cases on shared customer 1, plus actor/search_path.

Run through test_pg_v7_backend.py."""

from __future__ import annotations

import json
import re
import subprocess
import time

from pg_v7_harness import (
    DATABASE,
    HarnessError,
    Pg,
    PsqlSession,
    actor_sql,
    call,
    lit,
    new_book,
    require,
)


def check_actor(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 10))
    pg.rejects(f"SELECT sokhach.get_ledger({c})", message="ACTOR_REQUIRED")
    pg.rejects(f"SELECT sokhach.record_receipt({c},0,'actor-empty','2026-02-01','THU TIỀN',1)",
               message="ACTOR_REQUIRED")
    pg.rejects(actor_sql(f"SELECT sokhach.get_ledger({c})", " "), message="ACTOR_REQUIRED")
    require(json.loads(pg.value(actor_sql(f"SELECT sokhach.get_ledger({c})", "harness"),
                                user="v7_app"))["total_outstanding_vnd"] == "10",
            "app cannot read through allowed function")
    pg.rejects(f"SELECT sokhach.record_receipt({c},0,'actor-role','2026-02-01','THU TIỀN',1)",
               user="v7_app", message="ACTOR_REQUIRED")
    result = pg.value(actor_sql(f"SELECT sokhach.get_ledger({c})", "actor-a",
        search_path="CREATE TEMP TABLE customer(version bigint); INSERT INTO customer VALUES (999); "
                    "SET LOCAL search_path = pg_temp, public; "))
    require(json.loads(result)["total_outstanding_vnd"] == "10", "hostile search_path changed ledger")
    require(call(pg, "get_ledger", c, actor="actor-a")["status"] == "active"
            and call(pg, "get_ledger", c, actor="actor-b")["status"] == "active",
            "trial reader applied unexpected per-person ACL")
    pg.true("NOT EXISTS (SELECT 1 FROM pg_proc p WHERE p.pronamespace='sokhach'::regnamespace "
            "AND p.proname IN ('record_receipt','get_ledger') AND "
            "pg_get_function_arguments(p.oid) ~ '(^|, )actor ')",
            "public command accepts actor parameter")
    call(pg, "record_receipt", c, 0, "actor-ok", "2026-02-01", "THU TIỀN", 1,
         actor="actor-b")
    require(pg.value(f"SELECT actor FROM sokhach.event WHERE customer_id={c} AND kind='receipt'") == "actor-b",
            "event actor differs from SET LOCAL")


def check_immutable(pg: Pg) -> None:
    for table, column in [("event", "actor"), ("trip", "container"), ("trip_price_rev", "unit_price_vnd"),
                          ("adjustment", "amount_vnd"), ("idempotency", "request_hash"),
                          ("opening_balance", "amount_vnd"), ("legacy_row", "source_total_vnd")]:
        pg.true(f"EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.{table}'::regclass AND NOT tgisinternal AND tgname LIKE '%immutable%')",
                f"missing immutable trigger on {table}")
        pg.rejects(f"UPDATE sokhach.{table} SET {column}={column} WHERE false", user="v7_app")
        pg.rejects(f"DELETE FROM sokhach.{table} WHERE false", user="v7_app")
    pg.rejects("UPDATE sokhach.opening_balance SET amount_vnd=101 WHERE id=1", message="immutable row")
    pg.rejects("DELETE FROM sokhach.legacy_row WHERE id=1", message="immutable row")


def check_roles(pg: Pg) -> None:
    pg.true("NOT EXISTS (SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL "
            "aclexplode(coalesce(n.nspacl, acldefault('n',n.nspowner))) a "
            "WHERE n.nspname='sokhach' AND a.grantee=0 AND a.privilege_type='USAGE')",
            "PUBLIC has schema usage")
    for role in ("v7_app", "v7_reader"):
        pg.true(f"has_schema_privilege('{role}','sokhach','USAGE')", f"{role} lacks schema usage")
        for relation in ("customer", "cutover", "opening_balance", "trip", "receipt", "event",
                         "v_outstanding_month", "v_month_chain"):
            pg.true(f"NOT has_table_privilege('{role}','sokhach.{relation}','SELECT') AND "
                    f"NOT has_table_privilege('{role}','sokhach.{relation}','INSERT') AND "
                    f"NOT has_table_privilege('{role}','sokhach.{relation}','UPDATE') AND "
                    f"NOT has_table_privilege('{role}','sokhach.{relation}','DELETE')",
                    f"{role} can read/write {relation}")
        pg.rejects("SELECT * FROM sokhach.v_outstanding_month", user=role)
    public_commands = ("add_trip_fees", "set_trip_fee_type", "replace_trip_fee", "void_trip_fee", "rewrite_trip_fees",
                       "add_fee_type", "rename_fee_type", "set_fee_type_kind", "set_fee_type_active", "get_fee_types", "set_book_fee_columns",
                       "save_price_table", "apply_price_table", "get_price_table", "get_price_status",
                       "paste_trips", "edit_trip_price", "adjust_trip", "adjust_month", "delete_month_adjustment",
                       "record_receipt", "edit_receipt_meta", "void_receipt", "set_month_lock", "review_trip", "edit_trip_info", "delete_trip", "edit_legacy_trip", "delete_legacy_trip",
                       "get_ledger", "list_customers", "get_dashboard", "get_dashboard_debt", "list_sheet_trip_refs", "resolve_sheet_conflict", "record_offset", "void_offset",
                       "get_receivables_matrix", "get_receivables_detail", "record_reminder", "get_reminders",
                       "attach_receipt_image", "remove_receipt_image", "list_receipt_images", "get_receipt_image", "find_receipt_image",
                       "edit_offset_date", "list_offset_sources", "import_cutover", "verify_cutover_customer",
                       "verify_cutover", "activate_cutover", "activate_cutover_customer")
    allowed = ",".join(lit(name) for name in public_commands)
    pg.true("(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            f"WHERE n.nspname='sokhach' AND p.proname IN ({allowed})) = {len(public_commands)}",
            "public command missing or overloaded")
    for role in ("v7_app", "v7_reader"):
        forbidden = pg.value("SELECT coalesce(string_agg(p.oid::regprocedure::text,','), '') "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            f"WHERE n.nspname='sokhach' AND p.proname NOT IN ({allowed}) "
            f"AND has_function_privilege({lit(role)},p.oid,'EXECUTE')")
        require(not forbidden, f"{role} may execute private helper: {forbidden}")
    pg.true("(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            f"WHERE n.nspname='sokhach' AND p.proname NOT IN ({allowed})) >= 18",
            "private helper inventory unexpectedly incomplete")


def check_numbers(pg: Pg) -> None:
    pg.true("(SELECT data_type='bigint' FROM information_schema.columns WHERE table_schema='sokhach' AND table_name='opening_balance' AND column_name='amount_vnd')",
            "opening money not bigint")
    pg.true("(SELECT is_nullable='YES' AND data_type='bigint' FROM information_schema.columns WHERE table_schema='sokhach' AND table_name='trip_price_rev' AND column_name='other_fee_vnd')",
            "source fee NULL/bigint lost")
    pg.rejects("INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,created_by_event) VALUES (1,1,'2026-03-01',NULL,'FAKE',4,1)")
    pg.rejects("SELECT 9223372036854775808::bigint", message="out of range")
    pg.true("(SELECT standard_bucket_vnd IS NOT NULL FROM sokhach.cutover_month_check WHERE debt_month='2026-01-01')",
            "seed standard bucket missing")
    pg.true("(SELECT data_type='bigint' AND is_nullable='YES' FROM information_schema.columns "
            "WHERE table_schema='sokhach' AND table_name='cutover_month_check' "
            "AND column_name='opening_anchor_vnd')", "first source anchor column missing")


def check_gate_view(pg: Pg) -> None:
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "draft leaked into balance")
    # Direct status moves characterize trigger/view only; they do not prove command reconciliation.
    pg.sql("UPDATE sokhach.cutover_customer SET status='verified' WHERE customer_id=1")
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "verified customer leaked")
    pg.sql("UPDATE sokhach.cutover SET status='verified' WHERE id=1")
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "verified cutover leaked")
    pg.sql("UPDATE sokhach.cutover SET status='active' WHERE id=1")
    require(pg.value("SELECT count(*) FROM sokhach.v_outstanding_month") == "0", "one-sided active leaked")
    pg.sql("UPDATE sokhach.cutover_customer SET status='active' WHERE customer_id=1")
    require(pg.value("SELECT string_agg(debt_month::text || ':' || outstanding_vnd::text, ',' ORDER BY debt_month) FROM sokhach.v_outstanding_month") ==
            "2026-01-01:100,2026-02-01:200", "active monthly amounts wrong")
    require(pg.value("SELECT string_agg(end_of_month_vnd::text, ',' ORDER BY debt_month) FROM sokhach.v_month_chain") == "100,300",
            "monthly cumulative view wrong")


def check_legacy(pg: Pg) -> None:
    require(pg.value("SELECT coalesce(sum(outstanding_vnd),0) FROM sokhach.v_outstanding_month") == "300",
            "legacy total added to balance")
    pg.rejects("UPDATE sokhach.legacy_row SET source_total_vnd=123 WHERE id=1", message="immutable row")
    pg.rejects("DELETE FROM sokhach.legacy_row WHERE id=1", message="immutable row")


def check_import_guard(pg: Pg) -> None:
    for index in ("event_import_once", "event_one_cutover_per_customer"):
        pg.true(f"EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='sokhach' AND indexname='{index}' AND indexdef LIKE '%UNIQUE%')",
                f"missing unique {index}")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\",cutover_id) VALUES (1,'import','test','{}','{\"cutover\":1}',1)")
    pg.rejects("INSERT INTO sokhach.cutover_customer(customer_id,cutover_id,expected_control_total_vnd,report_sha256,source_rows,imported_rows,quarantined_rows,skipped_with_reason_rows,unresolved_exceptions) SELECT customer_id,cutover_id,300,report_sha256,0,0,0,0,0 FROM sokhach.cutover_customer WHERE customer_id=1")


def check_negative(pg: Pg) -> None:
    customer = new_book(pg, ("2026-01-01", -50))
    require(pg.value(f"SELECT outstanding_vnd FROM sokhach.v_outstanding_month WHERE customer_id={customer}") == "-50",
            "negative opening clamped or omitted")


def check_events(pg: Pg) -> None:
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") VALUES (1,'receipt','test',NULL,'{\"receipt\":1}')")
    pg.rejects("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") VALUES (1,'receipt','test','{}','{}')")
    pg.true("EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='sokhach.receipt_line'::regclass AND conname='receipt_line_created_by_event_customer_id_fkey') OR EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='sokhach.receipt_line'::regclass AND contype='f' AND pg_get_constraintdef(oid) LIKE '%created_by_event, customer_id%')",
            "receipt line event/customer FK missing")


def check_evidence(pg: Pg) -> str:
    for table in ("cutover_month_check", "opening_balance", "legacy_row"):
        pg.true(f"EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach.{table}'::regclass AND NOT tgisinternal AND tgfoid='sokhach.guard_cutover_evidence()'::regprocedure)",
                f"evidence guard absent on {table}")
    # check_gate_view moved customer and cutover through draft -> verified -> active.
    pg.true("EXISTS (SELECT 1 FROM sokhach.cutover AS c JOIN sokhach.cutover_customer AS cc "
            "ON cc.cutover_id=c.id WHERE c.id=1 AND cc.customer_id=1 "
            "AND c.status='active' AND cc.status='active')", "evidence fixture not active")
    pg.rejects("UPDATE sokhach.cutover_month_check SET bucket_vnd=91 WHERE customer_id=1 AND debt_month='2026-01-01'", message="cutover evidence frozen")
    pg.rejects("INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month) VALUES (1,1,'2026-03-01')", message="cutover evidence frozen")
    pg.rejects("DELETE FROM sokhach.cutover_month_check WHERE customer_id=1 AND debt_month='2026-01-01'", message="cutover evidence frozen")
    pg.rejects("INSERT INTO sokhach.opening_balance(customer_id,cutover_id,debt_month,amount_vnd,source_tab,source_row,created_by_event) VALUES (1,1,'2026-03-01',1,'FAKE',4,1)", message="cutover evidence frozen")
    pg.rejects("INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_tab,source_row,created_by_event) VALUES (1,1,'2026-03-01','trip','{}','FAKE',4,1)", message="cutover evidence frozen")
    pg.rejects("UPDATE sokhach.cutover SET control_total_vnd=301 WHERE id=1", message="cutover status transition forbidden")
    pg.rejects("UPDATE sokhach.cutover_customer SET report_sha256=repeat('c',64) WHERE customer_id=1", message="cutover customer transition order forbidden")
    holder = PsqlSession(pg, f"v7_holder_{pg.run_id}")
    worker = None
    observed = None
    try:
        holder.send("BEGIN")
        holder.send("SELECT pg_backend_pid() FROM sokhach.cutover WHERE id=1 FOR UPDATE")
        holder_pid = int(holder.line())
        worker_name = f"v7_worker_{pg.run_id}"
        worker = subprocess.Popen(
            ["docker", "exec", "--env", f"PGAPPNAME={worker_name}", "--env",
             "PGOPTIONS=-c statement_timeout=10000", pg.name, "psql", "-X", "-qAt",
             "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE, "-c",
             "INSERT INTO sokhach.cutover_month_check(customer_id,cutover_id,debt_month) VALUES (1,1,'2026-03-01')"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            snapshot = pg.value(
                "SELECT coalesce(string_agg(pid::text || ':' || pg_blocking_pids(pid)::text,','), '') "
                f"FROM pg_stat_activity WHERE application_name='{worker_name}'")
            if re.search(rf"\b{holder_pid}\b", snapshot):
                observed = snapshot
                break
            if worker.poll() is not None:
                break
            time.sleep(0.05)  # polling; only pg_blocking_pids counts as evidence
        require(observed is not None, "direct evidence DML did not block on cutover holder via pg_blocking_pids")
    finally:
        holder.close()
        if worker is not None:
            try:
                out, err = worker.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                worker.kill()
                out, err = worker.communicate()
                raise HarnessError("direct evidence worker timed out") from None
            require(worker.returncode != 0 and "cutover evidence frozen" in err,
                    f"worker must reject evidence after lock release: {out} {err[-500:]}")
    return f"trigger freeze and pg_blocking_pids observed: {observed}"


def check_fee(pg: Pg) -> None:
    # Two event-linked fake trips plus fee-only row under active fake customer.
    event = int(pg.value("INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
        "VALUES (1,'paste','test','{}','{\"trips\":[]}') RETURNING id"))
    pg.sql(f"""BEGIN;
INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,created_by_event)
OVERRIDING SYSTEM VALUE VALUES (101,1,'2026-03-01','2026-03-04','FAKE-1',{event}),
       (102,1,'2026-04-01','2026-04-04','FAKE-2',{event}),
       (103,1,'2026-05-01',NULL,NULL,{event});
INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
VALUES (101,1,120,NULL,{event}),(102,1,NULL,7,{event}),(103,1,NULL,7,{event});
INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event)
SELECT 1,t.id,f.id,7,{event} FROM sokhach.trip t CROSS JOIN sokhach.fee_type f
WHERE t.id IN (102,103) AND f.system_key='other';
COMMIT;""")
    pg.rejects(f"""BEGIN;
INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,created_by_event)
OVERRIDING SYSTEM VALUE VALUES (104,1,'2026-06-01',NULL,NULL,{event});
INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event)
VALUES (104,1,120,NULL,{event});
COMMIT;""", message="INVALID_FEE_ONLY_DATE")
    pg.rejects(f"INSERT INTO sokhach.trip(id,customer_id,debt_month,event_date,container,created_by_event) "
               f"OVERRIDING SYSTEM VALUE VALUES (104,1,'2026-06-01',NULL,'FAKE-4',{event})",
               message="trip_missing_date_fee_only")
    pg.sql("SELECT setval(pg_get_serial_sequence('sokhach.trip','id'),103,true)")
    require(pg.value("SELECT other_fee_vnd IS NULL FROM sokhach.trip_price_rev WHERE trip_id=101") == "t",
            "stored NULL fee changed")
    require(pg.value("SELECT string_agg(debt_month::text || ':' || outstanding_vnd::text, ',' ORDER BY debt_month) FROM sokhach.v_outstanding_month WHERE customer_id=1") ==
            "2026-01-01:100,2026-02-01:200,2026-03-01:120,2026-05-01:7",
            "NULL fee/missing price/fee-only SQL view differs")
