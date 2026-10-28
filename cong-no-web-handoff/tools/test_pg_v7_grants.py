"""Exact V7 application grants and API behavior in one disposable fake database."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from test_pg_v7_backend import (
    DATABASE,
    FUNCTIONS,
    IMAGE,
    LABEL_RUN,
    LABEL_TEST,
    LABEL_VALUE,
    SCHEMA,
    SHEET_MIGRATION,
    HarnessError,
    Pg,
    actor_sql,
    inspect_owned,
    inspect_volume,
    lit,
    new_book,
    require,
    run,
    trip_json,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
from v7_ledger_api import ROUTES, Psql, validate

READ = {'get_ledger(bigint)', 'list_offset_sources(bigint)', 'list_customers()',
        'get_dashboard()', 'get_receivables_matrix(integer)', 'get_receivables_detail(bigint,date)'}
APP_READ = {'list_sheet_trip_refs()'}
WRITE = {
    'edit_trip_info(bigint,bigint,text,bigint,text,text)',
    'delete_trip(bigint,bigint,text,bigint)',
    'edit_legacy_trip(bigint,bigint,text,bigint,text,text)',
    'delete_legacy_trip(bigint,bigint,text,bigint)',

    'paste_trips(bigint,bigint,text,date,jsonb)',
    'edit_trip_price(bigint,bigint,text,bigint,bigint,bigint)',
    'adjust_trip(bigint,bigint,text,bigint,bigint,text,text,bigint)',
    'adjust_month(bigint,bigint,text,date,bigint,text)',
    'record_receipt(bigint,bigint,text,date,text,bigint,text)',
    'edit_receipt_meta(bigint,bigint,text,text,date,text,text)',
    'void_receipt(bigint,bigint,text,text,text)',
    'set_month_lock(bigint,bigint,text,date,boolean)',
    'review_trip(bigint,bigint,text,bigint,text,text)',
    'record_offset(bigint,bigint,bigint,bigint,text,date,bigint,text)',
    'void_offset(bigint,bigint,bigint,text,bigint,text)',
    'edit_offset_date(bigint,bigint,bigint,text,bigint,date)',
}


def functions(pg):
    return json.loads(pg.value("SELECT coalesce(jsonb_agg(jsonb_build_object('oid',p.oid,"
        "'signature',p.proname||'('||replace(oidvectortypes(p.proargtypes),', ', ',')||')',"
        "'args',p.pronargs,'trigger',p.prorettype='trigger'::regtype)), '[]') FROM pg_proc p WHERE pronamespace='sokhach'::regnamespace"))


KNOWN_FUNCTIONS = {'list_sheet_trip_refs', 'guard_sheet_cross_customer', '_trip_date', '_legacy_current', '_change_legacy', 'edit_trip_info', 'delete_trip', 'edit_legacy_trip', 'delete_legacy_trip', 'import_cutover', 'check_offset_pid', 'guard_cutover_evidence', 'record_offset', 'adjust_month', 'list_customers', 'guard_offset_pair', 'guard_cutover_status', '_lines', '_finish_cutover', '_next_pid', '_begin_offset', 'verify_cutover_customer', 'edit_receipt_meta', 'verify_cutover', '_actor', 'check_trip_missing_date', 'paste_trips', 'record_receipt', '_void_receipt', '_finish_offset', '_change_offset', 'guard_receipt_line_change', 'void_receipt', '_check_allocations', 'activate_cutover_customer', 'list_offset_sources', '_finish_command', 'check_offset_pair', 'reject_immutable_change', 'guard_receipt_change', '_check_cutover_customer', 'activate_cutover', 'adjust_trip', '_begin_cutover', 'edit_offset_date', '_baseline', '_begin_command', 'edit_trip_price', 'set_month_lock', 'guard_cutover_customer_status', '_month_open', 'reallocate', 'get_ledger', '_check_cutover', '_edit_receipt_meta', 'void_offset', '_normalize_key', '_booking_key', 'review_trip', 'guard_trip_change'}


KNOWN_FUNCTIONS.add('get_dashboard')
KNOWN_FUNCTIONS.add('get_receivables_matrix')
KNOWN_FUNCTIONS.add('get_receivables_detail')
KNOWN_FUNCTIONS.update({'_compat_trip_fee', '_sync_trip_fee', '_guard_fee_line',
                        '_fee_cache_check', 'v7_fee_migration_dry_run'})

def check_catalog(pg):
    inventory = functions(pg)
    require({f['signature'].split('(')[0] for f in inventory} == KNOWN_FUNCTIONS,
            'function inventory changed; classify new functions explicitly before granting')
    require(len(inventory) == len(KNOWN_FUNCTIONS), 'unexpected function overload')
    for role, expected in [('v7_app', READ | APP_READ | WRITE), ('v7_reader', READ)]:
        actual = {f['signature'] for f in inventory if pg.value(
            f"SELECT has_function_privilege('{role}',{f['oid']},'EXECUTE')") == 't'}
        require(actual == expected, f'{role}: missing={expected-actual}, extra={actual-expected}')
    pg.true("NOT EXISTS (SELECT 1 FROM pg_proc p CROSS JOIN LATERAL "
        "aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a "
        "WHERE p.pronamespace='sokhach'::regnamespace AND a.grantee=0 "
        "AND a.privilege_type='EXECUTE')", 'PUBLIC function EXECUTE')
    relations = json.loads(pg.value("SELECT jsonb_agg(jsonb_build_object('oid',oid,'kind',relkind)) "
        "FROM pg_class WHERE relnamespace='sokhach'::regnamespace AND relkind IN ('r','p','v','m','f','S')"))
    for role in ('v7_app', 'v7_reader'):
        for rel in relations:
            privileges = ('USAGE','SELECT','UPDATE') if rel['kind'] == 'S' else (
                'SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')
            checker = 'has_sequence_privilege' if rel['kind'] == 'S' else 'has_table_privilege'
            for privilege in privileges:
                pg.true(f"NOT {checker}('{role}',{rel['oid']},'{privilege}')", f'{role} {rel} {privilege}')
            if rel['kind'] != 'S':
                for privilege in ('SELECT','INSERT','UPDATE','REFERENCES'):
                    pg.true(f"NOT has_any_column_privilege('{role}',{rel['oid']},'{privilege}')",
                            f'{role} column privilege {rel} {privilege}')


def check_denials(pg):
    rows = json.loads(pg.value("SELECT jsonb_agg(jsonb_build_object('name',quote_ident(c.relname),'kind',c.relkind,"
        "'column',(SELECT quote_ident(attname) FROM pg_attribute WHERE attrelid=c.oid "
        "AND attnum>0 AND NOT attisdropped AND attidentity='' AND attgenerated='' "
        "ORDER BY attnum DESC LIMIT 1))) FROM pg_class c "
        "WHERE relnamespace='sokhach'::regnamespace AND relkind IN ('r','p','v','m','f')"))
    for row in rows:
        table, col = 'sokhach.' + row['name'], row['column']
        require(col is not None, f'no writable probe column for {table}')
        # Views may reject DML during rewrite, before ACL checks. Catalog checks
        # above still require every relation DML privilege to be false.
        for statement in (f'SELECT * FROM {table}', f'INSERT INTO {table} DEFAULT VALUES',
                          f'UPDATE {table} SET {col}=DEFAULT WHERE false', f'DELETE FROM {table} WHERE false'):
            message = 'permission denied' if row['kind'] in ('r', 'p') or statement.startswith('SELECT ') else ''
            try:
                pg.rejects(actor_sql(statement), user='v7_app', message=message)
            except HarnessError as exc:
                raise HarnessError(f'{statement}: {exc}') from exc
    for f in functions(pg):
        name = f['signature'].split('(')[0]
        statement = f"SELECT sokhach.{name}({','.join(['NULL'] * f['args'])})"
        if f['signature'] not in READ | APP_READ | WRITE and not f['trigger']:
            pg.rejects(actor_sql(statement), user='v7_app', message='permission denied')
        if f['signature'] in WRITE:
            pg.rejects(actor_sql(statement), user='v7_reader', message='permission denied')


def check_api(pg):
    require(Psql(pg.name, DATABASE, 'v7_app').run('list_customers', {}, 'fake') ==
            {'customers': []}, 'empty customers JSON')
    c = new_book(pg, ('2026-01-01', 1000))
    source = new_book(pg, ('2026-01-01', -500))
    pg.sql(f"UPDATE sokhach.customer SET name='fake z' WHERE id={c}; "
           f"UPDATE sokhach.customer SET name='FAKE A',archived=true WHERE id={source}; "
           "INSERT INTO sokhach.customer(name) VALUES ('fake a'); "
           "INSERT INTO sokhach.commodity(name) VALUES ('Sầu riêng'); "
           f"UPDATE sokhach.customer SET commodity_id=(SELECT id FROM sokhach.commodity), transport_mode='BO' "
           f"WHERE id={c}")
    runner = Psql(pg.name, DATABASE, 'v7_app')
    reader = Psql(pg.name, DATABASE, 'v7_reader')
    actor = 'fake-grants-actor'
    def invoke(name, **payload):
        for path, (function, _) in ROUTES.items():
            if function == name:
                validate(path, json.dumps(payload).encode('utf-8'))
                break
        return runner.run(name, payload, actor)
    def ledger(customer=c):
        return invoke('get_ledger', customer_id=customer)
    def balance(expected, customer=c):
        require(ledger(customer)['total_outstanding_vnd'] == str(expected), f'balance {customer} != {expected}')
    def write(name, **payload):
        before = ledger()['version']
        result = invoke(name, customer_id=c, expected_version=before,
                        idempotency_key='fake-' + name, **payload)
        require(ledger()['version'] == before + 1, f'{name}: version did not increment')
        return result
    expected = json.loads(pg.value("SELECT jsonb_build_object('customers',coalesce(jsonb_agg("
        "jsonb_build_object('id',id,'name',name,'status',status,'commodity',commodity,"
        "'transport_mode',transport_mode) ORDER BY name COLLATE \"C\",id),'[]'::jsonb)) "
        "FROM (SELECT c.id,c.name,CASE WHEN cc.status='active' AND co.status='active' THEN 'active' "
        "ELSE 'NO_BASELINE' END AS status,m.name AS commodity,c.transport_mode FROM sokhach.customer c "
        "LEFT JOIN sokhach.commodity m ON m.id=c.commodity_id LEFT JOIN sokhach.cutover_customer cc "
        "ON cc.customer_id=c.id LEFT JOIN sokhach.cutover co ON co.id=cc.cutover_id) q"))
    require(invoke('list_customers') == expected, 'customer JSON differs from original query')
    listed = {row['id']: row for row in expected['customers']}
    require((listed[c]['commodity'], listed[c]['transport_mode']) == ('Sầu riêng', 'BO')
            and (listed[source]['commodity'], listed[source]['transport_mode']) == (None, None),
            'commodity/transport_mode not listed')
    for name, payload in [('list_customers', {}), ('get_ledger', {'customer_id': c}),
                          ('list_offset_sources', {'target_customer_id': c})]:
        require(reader.run(name, payload, actor) == runner.run(name, payload, actor), 'reader result differs')
    # Archived customers remain listed, as in the original fixed API query.
    pg.sql(f"UPDATE sokhach.customer SET archived=false WHERE id={source}")
    for name, arguments in [('list_customers', ''), ('get_ledger', str(c)), ('list_offset_sources', str(c))]:
        pg.rejects(f'SELECT sokhach.{name}({arguments})', user='v7_app', message='ACTOR_REQUIRED')
    write('set_month_lock', month='2026-01-01', locked=False)
    balance(1000)
    trip = write('paste_trips', debt_month='2026-01-01',
                 trips=json.loads(trip_json()))['trip_ids'][0]
    balance(1100)
    write('edit_trip_price', trip_id=trip, unit_price_vnd='120', other_fee_vnd=None)
    balance(1120)
    write('adjust_trip', trip_id=trip, new_amount_vnd='130', note='fake')
    balance(1130)
    write('adjust_month', debt_month='2026-01-01', amount_vnd='20', note='fake')
    balance(1150)
    receipt = write('record_receipt', date='2026-01-02', method='THU TIỀN', amount_vnd='50', reference='FAKE TXN')
    require(ledger()['receipts'][0]['reference'] == 'FAKE TXN', 'app API lost receipt reference')
    balance(1100)
    write('edit_receipt_meta', pid=receipt['pid'], date='2026-01-03', method='THU TIỀN', reference='FAKE EDIT')
    require(ledger()['receipts'][0]['reference'] == 'FAKE EDIT', 'app API lost edited reference')
    balance(1100)
    write('void_receipt', pid=receipt['pid'], reason='fake')
    balance(1150)
    def offset(name, **payload):
        before, other = ledger()['version'], ledger(source)['version']
        if name == 'record_offset':
            args = {'target_customer_id': c, 'target_version': before, 'source_customer_id': source, 'source_version': other}
        else:
            args = {'customer_id': c, 'expected_version': before, 'other_version': other}
        result = invoke(name, **args, idempotency_key='fake-' + name, **payload)
        require((ledger()['version'], ledger(source)['version']) == (before+1, other+1), f'{name} pair versions')
        return result
    require(any(r['customer_id'] == source for r in invoke('list_offset_sources', target_customer_id=c)), 'source missing')
    pair = offset('record_offset', date='2026-01-02', amount_vnd='100', reference='FAKE OFFSET')
    require(next(r for r in ledger()['receipts'] if r['pid'] == pair['target_pid'])['reference'] == 'FAKE OFFSET',
            'offset target lost reference')
    other_version = ledger(source)['version']
    invoke('edit_receipt_meta', customer_id=c, expected_version=ledger()['version'],
           idempotency_key='fake-offset-reference', pid=pair['target_pid'], reference='FAKE OFFSET EDIT')
    require(ledger(source)['version'] == other_version, 'reference edit changed source book')
    balance(1050)
    balance(-400, source)
    offset('edit_offset_date', offset_pair_id=pair['offset_pair_id'], date='2026-01-03')
    balance(1050)
    balance(-400, source)
    offset('void_offset', offset_pair_id=pair['offset_pair_id'], reason='fake')
    balance(1150)
    balance(-500, source)
    write('edit_trip_info', trip_id=trip, field='carrier', value='FAKE EDIT')
    balance(1150)
    write('delete_trip', trip_id=trip)
    balance(1020)
    cut = pg.value(f"SELECT cutover_id FROM sokhach.cutover_customer WHERE customer_id={c}")
    event = pg.value(f"SELECT id FROM sokhach.event WHERE customer_id={c} AND kind='import'")
    pg.sql("ALTER TABLE sokhach.legacy_row DISABLE TRIGGER legacy_row_insert_guard")
    try:
        legacy = int(pg.value("INSERT INTO sokhach.legacy_row(customer_id,cutover_id,debt_month,kind,display,"
            "source_total_vnd,source_tab,source_row,created_by_event) "
            f"VALUES({c},{cut},'2026-01-01','trip','{{}}',0,'FAKE',100,{event}) RETURNING id"))
    finally:
        pg.sql("ALTER TABLE sokhach.legacy_row ENABLE TRIGGER legacy_row_insert_guard")
    write('edit_legacy_trip', legacy_row_id=legacy, field='unit_price_vnd', value='70')
    balance(1090)
    write('delete_legacy_trip', legacy_row_id=legacy)
    balance(1020)
    pg.true(f"NOT EXISTS (SELECT 1 FROM sokhach.event WHERE customer_id IN ({c},{source}) "
            f"AND kind <> 'import' AND actor <> {lit(actor)})", 'wrong event actor')


CHECKS = {'catalog': check_catalog, 'denials': check_denials, 'api': check_api}
CASES = [{'id': 'grants.' + name, 'label': 'BEHAVIOR', 'title': title, 'check': name,
          'functions': (), 'open_reason': ''} for name, title in [
    ('catalog', 'Exact function allowlists, PUBLIC and all relation privileges'),
    ('denials', 'Direct DML/read and private, cutover, reader write calls denied'),
    ('api', 'All API operations, actor, versions and exact fake balances')]]

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="list cases without Docker")
    ap.add_argument("--report", type=Path, help="write JSON report")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--expect-red", action="store_true", default=True,
                      help="default: missing command functions may fail")
    mode.add_argument("--strict", action="store_true", help="require every case to pass")
    args = ap.parse_args()
    if args.list:
        for c in CASES:
            print(f"{c['id']}\t{c['label']}\t{c['title']}")
        return 0
    run_id = uuid.uuid4().hex
    name = f"webdebit-v7-grants-{run_id}"
    volume = name
    report = {"revision": run(["git", "rev-parse", "HEAD"], cwd=SCHEMA.parents[2]).stdout.strip(),
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "run_id": run_id, "image": IMAGE, "schema": str(SCHEMA),
              "schema_sha256": hashlib.sha256(SCHEMA.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "functions": str(FUNCTIONS),
              "functions_sha256": hashlib.sha256(FUNCTIONS.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
              "sql_hash_normalization": "CRLF to LF",
              "cases": [], "cleanup": "not_started"}
    volume_created = False
    container_id = None
    fatal = None
    try:
        require(shutil.which("docker") is not None, "Docker CLI unavailable")
        run(["docker", "volume", "create", "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", volume])
        volume_created = True
        inspect_volume(volume, run_id)
        run(["docker", "run", "--detach", "--name", name, "--label", f"{LABEL_TEST}={LABEL_VALUE}",
             "--label", f"{LABEL_RUN}={run_id}", "--network", "none", "--volume",
             f"{volume}:/var/lib/postgresql", "--env", "POSTGRES_HOST_AUTH_METHOD=trust", IMAGE], timeout=240)
        container_id = inspect_owned(name, volume, run_id)
        require(container_id is not None, "container absent after Docker run")
        report["container_id"] = container_id
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            logs = run(["docker", "logs", name], check=False, timeout=10)
            if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                break
            time.sleep(0.25)  # readiness polling only; never contention evidence
        else:
            raise HarnessError("PostgreSQL init marker timed out")
        pg = Pg(name, run_id)
        require(pg.sql("SELECT current_database()", database="postgres").stdout.strip() == "postgres",
                "unexpected initial database")
        inspect_owned(name, volume, run_id, container_id)
        inspect_volume(volume, run_id)
        pg.sql(f"CREATE DATABASE {DATABASE}", database="postgres")
        marker = f"codex_v7_run_id={run_id}"
        pg.sql(f"COMMENT ON DATABASE {DATABASE} IS '{marker}'")
        require(pg.value("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()") == marker,
                "database marker mismatch")
        inspect_owned(name, volume, run_id, container_id)
        inspect_volume(volume, run_id)
        pg.sql(SCHEMA.read_text(encoding="utf-8"))
        pg.sql(FUNCTIONS.read_text(encoding="utf-8"))
        pg.sql(SHEET_MIGRATION.read_text(encoding="utf-8"))
        report["postgres_version"] = pg.value("SHOW server_version")
        pg.sql("CREATE ROLE v7_app LOGIN IN ROLE sokhach_app; CREATE ROLE v7_reader LOGIN IN ROLE sokhach_reader")
        # Existing schema checks share customer 1; run before isolated behavioral books.
        ordered = sorted(CASES, key=lambda c: 0 if c["label"] == "SCHEMA" else 1)
        for c in ordered:
            row = {"id": c["id"], "label": c["label"], "result": "fail", "reason": ""}
            try:
                if c["label"] == "SKIPPED_OPEN":
                    row.update(result="skipped", reason=c["open_reason"])
                elif c["label"] in ("NEEDS_FUNCTION", "BEHAVIOR"):
                    missing = [f for f in c["functions"] if pg.value(
                        f"SELECT count(*) FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='{f}'") == "0"]
                    if missing:
                        row["reason"] = "function does not exist: " + ", ".join(missing)
                    else:
                        require(c["check"] in CHECKS, "function present but no behavioral assertion")
                        row["executed"] = True
                        evidence = CHECKS[c["check"]](pg)
                        row.update(result="pass", reason=evidence or "PostgreSQL behavioral assertion passed")
                else:
                    evidence = CHECKS[c["check"]](pg)
                    row.update(result="pass", reason=evidence or "PostgreSQL schema assertion passed")
            except (HarnessError, ValueError, KeyError, TypeError, AssertionError,
                    subprocess.TimeoutExpired) as exc:
                row["reason"] = str(exc)
            report["cases"].append(row)
        position = {c["id"]: i for i, c in enumerate(CASES)}
        report["cases"].sort(key=lambda row: position[row["id"]])
    except (HarnessError, OSError, ValueError) as exc:
        fatal = str(exc)
        report["error"] = fatal
    finally:
        try:
            owned = inspect_owned(name, volume, run_id, container_id) if volume_created else None
            if owned:
                run(["docker", "rm", "--force", owned])
            if volume_created:
                inspect_volume(volume, run_id)
                run(["docker", "volume", "rm", volume])
            report["cleanup"] = "verified_and_removed" if volume_created else "nothing_created"
        except (HarnessError, OSError, ValueError) as exc:
            report["cleanup"] = "failed: " + str(exc)
            fatal = str(exc)
        if len(report["cases"]) < len(CASES):
            done = {c["id"] for c in report["cases"]}
            for c in CASES:
                if c["id"] not in done:
                    report["cases"].append({
                        "id": c["id"], "label": c["label"],
                        "result": "skipped" if c["label"] == "SKIPPED_OPEN" else "fail",
                        "reason": c["open_reason"] if c["label"] == "SKIPPED_OPEN"
                        else "harness did not reach case: " + (fatal or "unknown setup failure")})
        counts = {label: {result: sum(c["label"] == label and c["result"] == result for c in report["cases"])
                          for result in ("pass", "fail", "skipped")}
                  for label in ("SCHEMA", "BEHAVIOR", "NEEDS_FUNCTION", "SKIPPED_OPEN")}
        report["summary"] = counts
        report["exit_code"] = int(bool(fatal) or len(report["cases"]) != len(CASES)
                                  or any(c["result"] != "pass" for c in report["cases"]
                                         if (c["label"] != "SKIPPED_OPEN" and (args.strict or c["label"] in ("SCHEMA", "BEHAVIOR")))
                                         or c.get("executed")))
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
