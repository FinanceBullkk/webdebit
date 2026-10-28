"""V7 backend harness cases: Month locks and the atomic CSM migration.

Run through test_pg_v7_backend.py."""

from __future__ import annotations

import json
import re
import time

from pg_v7_harness import (
    DA_THU_MIGRATION,
    DASHBOARD_MIGRATION,
    DETAIL_MIGRATION,
    LEGACY_RECEIPT_MIGRATION,
    LOCKED_TRIP_MIGRATION,
    MATRIX_MIGRATION,
    MH_MIGRATION,
    NHAP_MIGRATION,
    REVIEW_MIGRATION,
    ROOT,
    SHEET_CONFLICT_DATE_MIGRATION,
    SHEET_CONFLICT_MIGRATION,
    SHEET_MIGRATION,
    SYNC_MIGRATION,
    Pg,
    PsqlSession,
    call,
    fixture_open_month,
    lit,
    new_book,
    reject_call,
    require,
    run,
    trip_json,
    version,
)
from test_pg_v7_backend_receipts import (
    check_csm_reference,
)
from test_pg_v7_backend_sheet_fee import (
    check_sheet_conflict_resolution,
)


def check_csm_migration(pg: Pg) -> None:
    old_ref = "b49a752156bbc57e418fbf1a48838711b0ec4ee5"
    old_schema = run(["git", "show", old_ref + ":specs/v7-backend/schema-draft.sql"], cwd=ROOT).stdout
    old_functions = run(["git", "show", old_ref + ":cong-no-web-handoff/tools/v7_backend_functions.sql"], cwd=ROOT).stdout
    db = "webdebit_v7_csm_migration_test"
    pg.sql(f"CREATE DATABASE {db}", database="postgres")
    class CopyPg(Pg):
        def sql(self, sql, **kwargs):
            return super().sql(sql, **{**kwargs, "database": db})
    copy = CopyPg(pg.name, pg.run_id)
    copy.sql(re.sub(r"^CREATE ROLE .*;\n", "", old_schema, flags=re.M))
    copy.sql(old_functions)
    c = new_book(copy, ("2026-01-01", 100))
    old_result = call(copy, "record_receipt", c, 0, "old-retry", "2026-01-02", "THU TIỀN", 10)
    snapshot = copy.value(f"SELECT row_to_json(x) FROM sokhach.receipt x WHERE customer_id={c}")
    migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-21-v7-csm.sql").read_text(encoding="utf-8")
    copy.rejects(migration.replace("COMMIT;", "DO $$ BEGIN RAISE EXCEPTION 'CSM_MIGRATION_FAULT'; END $$; COMMIT;"),
                 message="CSM_MIGRATION_FAULT")
    copy.true("NOT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='sokhach' "
              "AND table_name='receipt' AND column_name='reference')", "migration rollback left column")
    copy.sql(migration)
    copy.sql(migration)  # repeat is safe; no new events or financial writes
    copy.sql(REVIEW_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(REVIEW_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(NHAP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(NHAP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MH_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MH_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DASHBOARD_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DASHBOARD_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LOCKED_TRIP_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SHEET_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SHEET_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MATRIX_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(MATRIX_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DETAIL_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DETAIL_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SYNC_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(SYNC_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LEGACY_RECEIPT_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(LEGACY_RECEIPT_MIGRATION.read_text(encoding="utf-8"))
    for migration in (SHEET_CONFLICT_MIGRATION, SHEET_CONFLICT_DATE_MIGRATION):
        copy.sql(migration.read_text(encoding="utf-8"))
        copy.sql(migration.read_text(encoding="utf-8"))
    fee_book = new_book(copy, ("2026-01-01", 0))
    fixture_open_month(copy, fee_book, "2026-01-01")
    row = json.loads(trip_json())[0]
    row["otherFeeVnd"] = "5"
    fee_trip = call(copy, "paste_trips", fee_book, version(copy, fee_book), "fee-old-paste",
                    "2026-01-01", json.dumps([row]))["trip_ids"][0]
    call(copy, "adjust_trip", fee_book, version(copy, fee_book), "fee-old-adjust",
         fee_trip, None, "", "other_fee_vnd", 7)
    zero_book = new_book(copy, ("2026-01-01", 0))
    fixture_open_month(copy, zero_book, "2026-01-01")
    zero_row = json.loads(trip_json(container="ZERO-FEE"))[0]
    zero_row["otherFeeVnd"] = "0"
    zero_trip = call(copy, "paste_trips", zero_book, version(copy, zero_book), "zero-old-paste",
                     "2026-01-01", json.dumps([zero_row]))["trip_ids"][0]
    legacy_book = new_book(copy, ("2026-01-01", 999))
    fixture_open_month(copy, legacy_book, "2026-01-01")
    cutover = copy.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={legacy_book}")
    import_event = copy.value(f"SELECT id FROM sokhach.event WHERE customer_id={legacy_book} AND kind='import'")
    legacy_id = copy.value("BEGIN; SET LOCAL ROLE sokhach_owner; "
        "ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard; "
        "INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,source_total_vnd,source_tab,source_row,created_by_event) "
        f"VALUES({legacy_book},{cutover},'2026-01-01','trip','{{\"container\":\"LEGACY\",\"unit_price\":\"100\",\"fee_vnd\":\"5\"}}',999,'FAKE',99,{import_event}) RETURNING id; "
        "ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard; COMMIT").splitlines()[0]
    before_fee = copy.value(f"SELECT outstanding_vnd FROM sokhach.v_outstanding_month WHERE customer_id={fee_book}")
    fee_migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-28-v7-phu-phi-core-a.sql").read_text(encoding="utf-8")
    dry_gate = "DO $$ DECLARE r record; BEGIN SELECT * INTO r FROM sokhach.v7_fee_migration_dry_run();"
    require(dry_gate in fee_migration, "fee dry-run gate missing")
    for container, event_date, old_fee, adjustment in (("NULL", "NULL", "0", ""),
                                                        ("'DRY-C'", "'2026-01-01'", "NULL",
                                                         "INSERT INTO sokhach.adjustment(customer_id,debt_month,trip_id,amount_vnd,actor,created_by_event,field,new_value_vnd) "
                                                         "SELECT customer_id,debt_month,id,5,'harness',created_by_event,'other_fee_vnd',5 FROM fee_dry_trip;")):
        fixture = ("WITH e AS (INSERT INTO sokhach.event(customer_id,kind,actor,\"before\",\"after\") "
                   f"VALUES({fee_book},'paste','harness','{{}}','{{\"trips\":[]}}') RETURNING id), "
                   "t AS (INSERT INTO sokhach.trip(customer_id,debt_month,event_date,container,created_by_event) "
                   f"SELECT {fee_book},'2026-01-01',{event_date},{container},id FROM e RETURNING id,customer_id,debt_month,created_by_event) "
                   "INSERT INTO sokhach.trip_price_rev(trip_id,customer_id,unit_price_vnd,other_fee_vnd,created_by_event) "
                   f"SELECT id,customer_id,NULL,{old_fee},created_by_event FROM t; "
                   "CREATE TEMP TABLE fee_dry_trip ON COMMIT DROP AS SELECT * FROM sokhach.trip ORDER BY id DESC LIMIT 1; "
                   + adjustment)
        copy.rejects(fee_migration.replace(dry_gate, fixture + dry_gate), message="FEE_MIGRATION_REVIEW_REQUIRED")
        copy.true("to_regclass('sokhach.trip_fee_line') IS NULL", "rejected fee dry-run left schema")
    copy.sql(fee_migration)
    copy.true(f"(SELECT other_fee_vnd IS NULL FROM sokhach.trip_price_rev WHERE trip_id={zero_trip} ORDER BY id DESC LIMIT 1)",
              "zero fee not normalized to NULL")
    copy.true(f"(SELECT count(*)=1 FROM sokhach.event WHERE customer_id={fee_book} AND kind='fee_migration')",
              "migration did not create one fee event per customer")
    copy.true(f"(SELECT bool_and(e.kind='fee_migration') FROM sokhach.trip_fee_line l "
              f"JOIN sokhach.event e ON e.id=l.created_by_event WHERE l.trip_id={fee_trip})",
              "fee line reused an old event")
    require(any(e["kind"] == "fee_migration" and e["label"] == "Tách phụ phí"
                for e in call(copy, "get_ledger", fee_book)["events"]), "migration history label missing")
    copy.true(f"(SELECT amount_vnd=5 FROM sokhach.trip_fee_line WHERE legacy_row_id={legacy_id})",
              "legacy fee line missing")
    require(next(r for r in call(copy, "get_ledger", legacy_book)["legacy_rows"] if r["id"] == int(legacy_id))["current"]["counted_vnd"] == "999",
            "legacy TOTAL changed during migration")
    fee_counts = copy.value("SELECT jsonb_build_array((SELECT count(*) FROM sokhach.trip_price_rev),"
                            "(SELECT count(*) FROM sokhach.trip_fee_line),"
                            "(SELECT count(*) FROM sokhach.event))")
    copy.sql(fee_migration)
    require(copy.value("SELECT jsonb_build_array((SELECT count(*) FROM sokhach.trip_price_rev),"
                       "(SELECT count(*) FROM sokhach.trip_fee_line),"
                       "(SELECT count(*) FROM sokhach.event))") == fee_counts,
            "fee migration second run changed rows")
    copy.true(f"(SELECT fee_absorbed FROM sokhach.adjustment WHERE trip_id={fee_trip} AND field='other_fee_vnd')",
              "old fee adjustment not absorbed")
    require(copy.value(f"SELECT outstanding_vnd FROM sokhach.v_outstanding_month WHERE customer_id={fee_book}") == before_fee,
            "fee migration changed old adjusted trip")
    rollback = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-28-v7-phu-phi-core-a.rollback.sql").read_text(encoding="utf-8")
    rollback_check = "DO $$ BEGIN\n IF EXISTS(SELECT * FROM fee_rollback_month"
    require(rollback_check in rollback, "fee rollback balance checker marker missing")
    drift = ("INSERT INTO sokhach.adjustment(customer_id,debt_month,amount_vnd,actor,created_by_event) "
             f"VALUES({legacy_book},'2026-01-01',1,'harness',{import_event});\n")
    copy.rejects(rollback.replace(rollback_check, drift + rollback_check),
                 message="FEE_ROLLBACK_TOTAL_MISMATCH")
    copy.sql(rollback)
    copy.true("to_regclass('sokhach.trip_fee_line') IS NULL AND "
              "NOT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='sokhach' "
              "AND table_name='adjustment' AND column_name='fee_absorbed') AND "
              "(SELECT count(*)=2 FROM pg_constraint WHERE conname IN "
              "('trip_price_rev_other_fee_vnd_check','legacy_trip_rev_other_fee_vnd_check'))",
              "fee rollback did not restore old schema")
    copy.true(f"(SELECT other_fee_vnd=0 FROM sokhach.trip_price_rev WHERE trip_id={zero_trip} ORDER BY id DESC LIMIT 1)",
              "rollback lost source zero fee")
    copy.true("NOT EXISTS(SELECT 1 FROM sokhach.event WHERE kind='fee_migration')",
              "rollback left fee migration events")
    require(copy.value(f"SELECT outstanding_vnd FROM sokhach.v_outstanding_month WHERE customer_id={fee_book}") == before_fee,
            "fee rollback changed old adjusted trip")
    copy.sql(fee_migration)
    copy.sql(DA_THU_MIGRATION.read_text(encoding="utf-8"))
    copy.sql(DA_THU_MIGRATION.read_text(encoding="utf-8"))
    require(json.loads(copy.value(f"SELECT (to_jsonb(x)-'reference')::text FROM sokhach.receipt x WHERE customer_id={c}"))
            == json.loads(snapshot),
            "migration changed receipt row")
    require(call(copy, "record_receipt", c, 0, "old-retry", "2026-01-02", "THU TIỀN", 10) == old_result,
            "old idempotency key broken by migration")
    catalog = "SELECT jsonb_object_agg(proname,pg_get_functiondef(oid)) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace"
    migrated = json.loads(copy.value(catalog))
    fresh = json.loads(pg.value(catalog))
    migrated.pop("resolve_sheet_conflict", None)  # Existing migration, absent from canonical function file.
    require(migrated == fresh, f"migrated functions differ: {[k for k in migrated.keys() | fresh.keys() if migrated.get(k) != fresh.get(k)]}")
    call(copy, "edit_trip_price", fee_book, version(copy, fee_book), "fee-after-migration",
         fee_trip, 110, 7)
    require(copy.value(f"SELECT outstanding_vnd FROM sokhach.v_outstanding_month WHERE customer_id={fee_book}") == "117",
            "old fee adjustment counted twice after unit edit")
    call(copy, "edit_legacy_trip", legacy_book, version(copy, legacy_book), "legacy-fee-total",
         int(legacy_id), "other_fee_vnd", "7")
    copy.true(f"(SELECT counted_vnd=107 FROM sokhach.legacy_trip_rev WHERE legacy_row_id={legacy_id} ORDER BY id DESC LIMIT 1)",
              "legacy fee edit ignored source TOTAL difference")
    copy.true(f"(SELECT amount_vnd=-892 FROM sokhach.adjustment WHERE legacy_row_id={legacy_id} ORDER BY id DESC LIMIT 1)",
              "legacy fee adjustment delta wrong")
    legacy_flag = copy.value("BEGIN; SET LOCAL ROLE sokhach_owner; SET LOCAL sokhach.actor='harness'; "
        "INSERT INTO sokhach.trip_fee_line(customer_id,legacy_row_id,fee_type_id,amount_vnd,created_by_event) "
        f"SELECT {legacy_book},{legacy_id},id,3,{import_event} FROM sokhach.fee_type WHERE name='Neo'; "
        f"SELECT sokhach.get_ledger({legacy_book})->'legacy_rows'->0->>'has_typed_fee'; ROLLBACK")
    require(legacy_flag == "true", "legacy has_typed_fee missing")
    typed_book = new_book(copy, ("2026-01-01", 0))
    fixture_open_month(copy, typed_book, "2026-01-01")
    fee_rows = []
    for n, fee in enumerate((None, "5", "-5", None)):
        item = json.loads(trip_json(container=f"TYPED-{n}"))[0]
        item["otherFeeVnd"] = fee
        fee_rows.append(item)
    typed_ids = call(copy, "paste_trips", typed_book, version(copy, typed_book), "typed-flags",
                     "2026-01-01", json.dumps(fee_rows))["trip_ids"]
    copy.rejects(f"BEGIN; SET LOCAL ROLE sokhach_owner; INSERT INTO sokhach.trip_fee_line"
                 f"(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event) "
                 f"SELECT {typed_book},{typed_ids[0]},id,3,(SELECT created_by_event FROM sokhach.trip WHERE id={typed_ids[0]}) "
                 "FROM sokhach.fee_type WHERE system_key='other'; COMMIT", message="FEE_CACHE_MISMATCH")
    copy.rejects(f"INSERT INTO sokhach.trip_fee_line(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event) "
                 f"SELECT {c},{typed_ids[0]},id,3,(SELECT created_by_event FROM sokhach.trip WHERE id={typed_ids[0]}) "
                 "FROM sokhach.fee_type WHERE system_key='other'", message="foreign key")
    copy.sql(f"BEGIN; SET LOCAL ROLE sokhach_owner; INSERT INTO sokhach.trip_fee_line"
             f"(customer_id,trip_id,fee_type_id,amount_vnd,created_by_event) "
             f"SELECT {typed_book},{typed_ids[3]},id,3,(SELECT created_by_event FROM sokhach.trip WHERE id={typed_ids[3]}) "
             "FROM sokhach.fee_type WHERE name='Neo'; "
             f"SELECT sokhach._sync_trip_fee({typed_ids[3]},(SELECT created_by_event FROM sokhach.trip WHERE id={typed_ids[3]})); COMMIT")
    flags = [row["has_typed_fee"] for row in call(copy, "get_ledger", typed_book)["trips"]]
    require(flags == [False, False, False, True], f"typed fee flags wrong: {flags}")
    line_before = copy.value(f"SELECT id::text FROM sokhach.trip_fee_line WHERE trip_id={typed_ids[3]} AND voided_by_event IS NULL")
    call(copy, "edit_trip_price", typed_book, version(copy, typed_book), "typed-price-only",
         typed_ids[3], 101, 3)
    require(copy.value(f"SELECT id::text FROM sokhach.trip_fee_line WHERE trip_id={typed_ids[3]} AND voided_by_event IS NULL")
            == line_before, "price-only edit replaced typed fee line")
    for n, fee in enumerate((-7, -9)):
        call(copy, "edit_trip_price", typed_book, version(copy, typed_book), f"negative-fee-{n}",
             typed_ids[2], 100, fee)
    copy.true(f"(SELECT count(*)=1 AND min(amount_vnd)=-9 FROM sokhach.trip_fee_line "
              f"WHERE trip_id={typed_ids[2]} AND voided_by_event IS NULL)",
              "second negative fee did not replace first")
    reject_call(copy, "edit_trip_price", typed_book, version(copy, typed_book), "typed-reject",
                typed_ids[3], 100, 4, error="FEE_LINES_TYPED")
    copy.rejects(rollback, message="ROLLBACK_CLASSIFIED_LINES")
    writers = json.loads(copy.value("SELECT coalesce(jsonb_agg(proname ORDER BY proname),'[]'::jsonb) "
        "FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND "
        "(prosrc ~* 'INSERT[[:space:]]+INTO[[:space:]]+sokhach\\.(trip_price_rev|legacy_trip_rev)[^;]*other_fee_vnd' "
        "OR prosrc ~* 'UPDATE[[:space:]]+sokhach\\.(trip_price_rev|legacy_trip_rev)[^;]*other_fee_vnd')"))
    # Historical sheet conflict command copies unchanged legacy fee for an information edit.
    require(writers == ["_change_legacy", "_sync_trip_fee", "resolve_sheet_conflict"],
            f"unexpected fee cache writers: {writers}")
    check_csm_reference(copy)
    check_csm_locks(copy)
    from test_pg_v7_grants import check_catalog
    check_catalog(copy, extra_functions={"resolve_sheet_conflict"}, extra_app={
        "resolve_sheet_conflict(bigint,bigint,text,text,bigint,text,bigint,text,text,text,text)"})
    check_sheet_conflict_resolution(copy)


def check_csm_locks(pg: Pg) -> None:
    c = new_book(pg, ("2026-01-01", 100))
    before = pg.value("SELECT clock_timestamp()")
    opened = call(pg, "set_month_lock", c, 0, "csm-open", "2026-01-01", "false", actor="fake-opener")
    call(pg, "paste_trips", c, 1, "csm-late-paste", "2026-01-01", trip_json(container="FAKE-LATE"))
    call(pg, "set_month_lock", c, 2, "csm-close", "2026-01-01", "true", actor="fake-closer")
    require(call(pg, "set_month_lock", c, 0, "csm-open", "2026-01-01", "false") == opened,
            "lock retry not stable")
    call(pg, "set_month_lock", c, 3, "csm-close-again", "2026-01-01", "true")
    reject_call(pg, "set_month_lock", c, 3, "csm-stale", "2026-01-01", "false", error="STALE_LEDGER")
    reject_call(pg, "set_month_lock", c, 4, "csm-invalid", "2026-01-02", "false", error="INVALID_MONTH_LOCK")
    events = [e for e in call(pg, "get_ledger", c)["events"] if e["kind"] == "month_lock"]
    require(len(events) == 3 and events[-1]["actor"] == "fake-opener"
            and events[-2]["actor"] == "fake-closer", "lock event count/actor")
    require(events[-1]["before"]["locked"] is True and events[-2]["before"]["locked"] is False,
            "default/explicit lock before snapshot wrong")
    require([e["after"] for e in events] == [
        {"month": "2026-01-01", "locked": True}, {"month": "2026-01-01", "locked": True},
        {"month": "2026-01-01", "locked": False}], "open/close events merged")
    pg.true(f"(SELECT bool_and(at>={lit(before)}::timestamptz AND at<=clock_timestamp()) "
            f"FROM sokhach.event WHERE customer_id={c} AND kind='month_lock')", "event timestamp")
    for snapshot in ({}, {"month": "2026-01-01"}, {"month": "2026-01-01", "locked": "false"},
                     {"month": "2026-02-01", "locked": False}):
        pg.rejects('INSERT INTO sokhach.event(customer_id,kind,actor,"before","after") '
                   f"VALUES ({c},'month_lock','fake',"
                   f"'{json.dumps({'month': '2026-01-01', 'locked': True})}',{lit(json.dumps(snapshot))})",
                   message="check constraint")
    pg.sql("CREATE FUNCTION public.csm_abort_lock() RETURNS trigger LANGUAGE plpgsql AS $$ "
           "BEGIN RAISE EXCEPTION 'CSM_ABORT'; END $$; "
           "CREATE TRIGGER csm_abort_lock BEFORE UPDATE ON sokhach.month_state "
           "FOR EACH ROW EXECUTE FUNCTION public.csm_abort_lock()")
    try:
        reject_call(pg, "set_month_lock", c, 4, "csm-rollback", "2026-01-01", "false", error="CSM_ABORT")
        pg.true(f"(SELECT count(*)=3 FROM sokhach.event WHERE customer_id={c} AND kind='month_lock')",
                "rollback left event")
        require(version(pg, c) == 4, "rollback changed version")
    finally:
        pg.sql("DROP TRIGGER csm_abort_lock ON sokhach.month_state; DROP FUNCTION public.csm_abort_lock()")


def check_locks(pg: Pg) -> str:
    c = new_book(pg, ("2026-01-01", 1))
    definition = pg.value("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='edit_trip_price'")
    require(definition.index("_begin_command") < definition.index("clock_timestamp()") < definition.index("_month_open"),
            "price edit must read wall clock after customer lock")
    paste = pg.value("SELECT pg_get_functiondef(oid) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='paste_trips'")
    require("_month_open" not in paste, "paste still blocks locked months")
    pg.value(f"SELECT sokhach._month_open({c},'2026-10-01','2026-10-31 16:59:59+00')")
    pg.rejects(f"SELECT sokhach._month_open({c},'2026-10-01','2026-10-31 17:00:00+00')", message="MONTH_LOCKED")
    pg.value(f"SELECT sokhach._month_open({c},'2026-11-01','2026-10-31 17:00:00+00')")
    current = pg.value("SELECT date_trunc('month',clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
    old = pg.value(f"SELECT ({lit(current)}::date-interval '1 month')::date")
    trip = call(pg, "paste_trips", c, 0, "lock-old", old, trip_json(month=old))["trip_ids"][0]
    reject_call(pg, "edit_trip_price", c, 1, "lock-price", trip, 101, None, error="MONTH_LOCKED")
    current_trip = call(pg, "paste_trips", c, 1, "lock-current", current,
                        trip_json(container="LOCK-CURRENT", month=current))["trip_ids"][0]
    a, b = PsqlSession(pg, f"v7_lock_a_{c}"), PsqlSession(pg, f"v7_lock_b_{c}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='locker'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.set_month_lock({c},2,'close-current','{current}',true)")
        require(json.loads(a.line())["version"] == 3, "lock did not stage")
        b.send("BEGIN; SET LOCAL sokhach.actor='writer'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.paste_trips({c},3,'paste-after-lock','{current}',{lit(trip_json(container='LOCK-LATE',month=current))}::jsonb)")
        deadline = time.monotonic()+8
        while time.monotonic()<deadline and pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))")!='t':
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))")=='t', "paste did not wait for customer lock")
        a.send("COMMIT; SELECT 'done'")
        require(a.line()=="done", "lock commit")
        require(json.loads(b.line())["version"]==4, "locked-month paste did not proceed after customer lock")
        b.send("COMMIT; SELECT 'done'")
        require(b.line()=="done", "paste commit")
    finally:
        a.close()
        b.close()
    reject_call(pg, "edit_trip_price", c, 4, "price-locked-current", current_trip, 101, None, error="MONTH_LOCKED")
    before = (version(pg, c), pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}"))
    for name, args in (
            ("edit_trip_info", (current_trip, "carrier", "FAKE NEW")),
            ("delete_trip", (current_trip,)),
            ("adjust_trip", (current_trip, 120, "fake")),
            ("adjust_month", (current, 5, "fake"))):
        reject_call(pg, name, c, 4, "locked-" + name, *args, error="MONTH_LOCKED")
    require((version(pg, c), pg.value(f"SELECT count(*) FROM sokhach.event WHERE customer_id={c}")) == before,
            "locked trip edit wrote audit or version")
    call(pg, "set_month_lock", c, 4, "reopen-current", current, "false")
    a, b = PsqlSession(pg, f"v7_edit_a_{c}"), PsqlSession(pg, f"v7_edit_b_{c}")
    try:
        a.send("BEGIN; SET LOCAL sokhach.actor='locker'; SELECT pg_backend_pid()")
        pid_a = int(a.line())
        a.send(f"SELECT sokhach.set_month_lock({c},5,'close-current-again','{current}',true)")
        require(json.loads(a.line())["version"] == 6, "current-month close did not stage")
        b.send("BEGIN; SET LOCAL sokhach.actor='editor'; SELECT pg_backend_pid()")
        pid_b = int(b.line())
        b.send(f"SELECT sokhach.edit_trip_price({c},6,'edit-after-close',{current_trip},101,NULL)")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") != "t":
            time.sleep(0.05)
        require(pg.value(f"SELECT {pid_a}=ANY(pg_blocking_pids({pid_b}))") == "t", "price edit did not wait for customer lock")
        a.send("COMMIT; SELECT 'done'")
        require(a.line() == "done", "close commit")
        b.proc.wait(timeout=10)
        stderr = b.proc.stderr.read() if b.proc.stderr else ""
        require("MONTH_LOCKED" in stderr and version(pg, c) == 6, "price edit crossed concurrent lock")
    finally:
        a.close()
        b.close()
    empty = pg.value(f"SELECT ({lit(current)}::date-interval '3 month')::date")
    call(pg, "set_month_lock", c, 6, "open-empty", empty, "false")
    ledger = call(pg, "get_ledger", c)
    locks = {r["month"]: r["locked"] for r in ledger["month_locks"]}
    require(ledger["today_month"]==current and locks[current] and not locks[empty]
            and not any(m["month"]==empty for m in ledger["months"]), "GET month lock flags")
    call(pg, "record_receipt", c, version(pg, c), "receipt-while-locked", current, "THU TIỀN", 1)
    return "VN clock boundary; price uses current month; paste serializes without month gate"
