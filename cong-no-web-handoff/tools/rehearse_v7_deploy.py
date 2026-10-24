"""Rehearse V7 deployment in an owned PostgreSQL 18.6 container; never live DBs."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

from test_pg_v7_backend import (
    FUNCTIONS,
    SHEET_MIGRATION,
    IMAGE,
    LABEL_RUN,
    LABEL_TEST,
    LABEL_VALUE,
    ROOT,
    SCHEMA,
    HarnessError,
    Pg,
    inspect_owned,
    inspect_volume,
    require,
    run,
)
from v7_load_direct import DirectPg
from v7_load_direct import main as load_main
from v7_load_real_copy import clean_data

sys.path.insert(0, str(ROOT / 'cong-no-web-handoff/tests'))
import v7_export_clean as exporter
import v7_ledger_api as api
import v7_reconcile_sheet as reconcile
from test_v7_load_real_copy import fixture

TOOLS = ROOT / 'cong-no-web-handoff/tools'
CHECK = TOOLS / 'v7_post_deploy_check.sql'
DB = 'v7_rehearsal'
LOADER = 'v7_loader'
# These exact templates are shared with the runbook and recorded without paths/data.
COMMANDS = {
    'preflight': 'psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d postgres',
    'globals': 'pg_dumpall -h /var/run/postgresql -U postgres --globals-only',
    'backup': 'pg_dump -h /var/run/postgresql -U postgres -Fc webdebit_ledger',
    'list_backup': 'pg_restore --list',
    'restore': 'pg_restore -h /var/run/postgresql -U postgres --exit-on-error --single-transaction -d <restore_db>',
    'create': 'CREATE DATABASE <db_v7>;',
    'schema': 'psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -f <release>/specs/v7-backend/schema-draft.sql',
    'functions': 'psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -f <release>/cong-no-web-handoff/tools/v7_backend_functions.sql',
    'check': 'psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -v db_v7=<db_v7> -v loader_role=<loader_role> -f <release>/cong-no-web-handoff/tools/v7_post_deploy_check.sql',
    'plan': 'python <release>/cong-no-web-handoff/tools/v7_load_direct.py --from-clean <clean_dir> --socket-dir /var/run/postgresql --database <db_v7> --loader-role <loader_role>',
    'apply': 'python <release>/cong-no-web-handoff/tools/v7_load_direct.py --from-clean <clean_dir> --socket-dir /var/run/postgresql --database <db_v7> --loader-role <loader_role> --apply',
    'reconcile': 'python <release>/cong-no-web-handoff/tools/v7_reconcile_sheet.py --api http://127.0.0.1:<port> --sheet-dir <clean_dir> --out <new_outside_repo_dir> --brief',
    'rollback': 'DROP DATABASE <db_v7>;',
}
STEPS = ('preflight', 'backup_restore', 'provision', 'load', 'api_reconcile',
         'receipt_void_offset', 'rollback_B', 'rollback_C')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def count_sql(schema):
    """Exact counts, not pg_stat estimates. SQL identifiers come only from catalog."""
    return ("SELECT format('SELECT %L, count(*) FROM %I.%I;', schemaname||'.'||tablename,"
            "schemaname,tablename) FROM pg_tables WHERE schemaname="
            + "'" + schema + "' ORDER BY tablename;\n\\gexec\n")


def fake_clean(folder):
    source = folder / 'source'
    source.mkdir()
    fixture(source)
    books, digests = exporter.build_books(source, source / 'source-google-export.xlsx', ())
    # A second independent fake source has a received advance.
    advance = folder / 'advance'
    advance.mkdir()
    fixture(advance, name='FAKE ADVANCE', months=[('2026-10', '03/10/2026', 100, -100)],
            receipt='200', receipt_date='03/10/2026')
    others, _ = exporter.build_books(advance, advance / 'source-google-export.xlsx', ())
    others[0]['ordinal'] = 2
    books.extend(others)
    out = folder / 'clean'
    exporter.export(books, digests, out, source / 'source-google-export.xlsx', ())
    return out


class Rehearsal:
    def __init__(self, report, folder):
        self.report, self.folder = report, folder
        self.run_id = report['run_id']
        self.name = 'webdebit-v7-rehearse-' + self.run_id
        self.volume = self.name
        self.container_id = None
        self.volume_created = False
        self.pg = Pg(self.name, self.run_id)

    @contextmanager
    def step(self, name):
        row = {'id': name, 'result': 'fail'}
        start = time.monotonic()
        self.report['steps'].append(row)
        try:
            yield row
            row['result'] = 'pass'
        finally:
            row['seconds'] = round(time.monotonic() - start, 3)

    def sql(self, text, database=DB):
        self.report['executed_commands'].append({'adapter': 'Pg.sql', 'database': database,
                                                'stdin_sha256': sha(text.encode())})
        return self.pg.sql(text, database=database).stdout.strip()

    def program(self, program, *args, data=None):
        entry = {
            'argv': ['docker', 'exec', '-i', '<container>', program, *args],
            'stdin_sha256': sha(data) if data is not None else None,
        }
        self.report['executed_commands'].append(entry)
        start = time.monotonic()
        result = subprocess.run(['docker', 'exec', '-i', self.name, program, *args],
                                input=data, capture_output=True, timeout=300, check=False)
        entry.update(exit_code=result.returncode, seconds=round(time.monotonic() - start, 3))
        require(result.returncode == 0, 'rehearsal command failed: ' + program)
        return result.stdout

    def start(self):
        run(['docker', 'volume', 'create', '--label', f'{LABEL_TEST}={LABEL_VALUE}',
             '--label', f'{LABEL_RUN}={self.run_id}', self.volume])
        self.volume_created = True
        inspect_volume(self.volume, self.run_id)
        run(['docker', 'run', '--detach', '--name', self.name,
             '--label', f'{LABEL_TEST}={LABEL_VALUE}', '--label', f'{LABEL_RUN}={self.run_id}',
             '--network', 'none', '--volume', self.volume + ':/var/lib/postgresql',
             '--env', 'POSTGRES_HOST_AUTH_METHOD=trust', IMAGE,
             '-c', "listen_addresses="], timeout=240)
        self.container_id = inspect_owned(self.name, self.volume, self.run_id)
        require(self.container_id is not None, 'container missing')
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            logs = run(['docker', 'logs', self.name], check=False)
            if 'PostgreSQL init process complete; ready for start up.' in logs.stdout + logs.stderr:
                break
            time.sleep(.25)
        else:
            raise HarnessError('readiness timeout')
        self.sql('CREATE DATABASE webdebit_ledger', 'postgres')
        self.sql((TOOLS / 'pg_ledger_schema.sql').read_text(encoding='utf-8'), 'webdebit_ledger')
        self.sql("INSERT INTO ledger.customer(customer) VALUES ('FAKE BASELINE');"
                 "INSERT INTO ledger.opening VALUES ('FAKE BASELINE','2026-01',123,1,'NO_BASELINE');",
                 'webdebit_ledger')

    def counts(self, database):
        # Capture the generated SELECT statements separately; no customer data.
        generated = self.sql(count_sql('ledger').split('\n')[0], database)
        return self.sql(generated, database)

    def restore_test(self, name):
        self.sql('CREATE DATABASE ' + name, 'postgres')
        try:
            self.program('pg_restore', '-h', '/var/run/postgresql', '-U', 'postgres',
                         '--exit-on-error', '--single-transaction', '-d', name,
                         data=(self.folder / 'ledger.dump').read_bytes())
            require(self.counts(name) == self.baseline, 'restore baseline mismatch')
        finally:
            self.sql('DROP DATABASE ' + name, 'postgres')

    def check(self, customers=None, openings=None, extra=''):
        variables = '\\set db_v7 ' + DB + '\n\\set loader_role ' + LOADER + '\n'
        if customers is not None:
            variables += '\\set expect_customers ' + str(customers) + '\n'
        if openings is not None:
            variables += '\\set expect_openings ' + str(openings) + '\n'
        self.sql(variables + extra + CHECK.read_text(encoding='utf-8'))

    def checker_regressions(self, customers, openings):
        # Every mutation is transaction-local and rolled back, including failed checks.
        cases = {
            'invalid_extra_execute': ('GRANT EXECUTE ON FUNCTION sokhach.reallocate(bigint,text) TO v7_app;', 'function allowlist mismatch'),
            'invalid_public_connect': ('GRANT CONNECT ON DATABASE ' + DB + ' TO PUBLIC;', 'PUBLIC CONNECT'),
            'invalid_table_select': ('GRANT SELECT ON sokhach.customer TO sokhach_app;', 'relation privilege present'),
            'invalid_role': ('ALTER ROLE v7_app CREATEDB;', 'role missing or elevated'),
            'missing_role': ('ALTER ROLE v7_app NOLOGIN;', 'role missing or elevated'),
            'missing_schema': ('ALTER SCHEMA sokhach RENAME TO hidden;', 'schema missing'),
        }
        # Inject after BEGIN READ ONLY, changing only this probe to a rollback transaction.
        script = CHECK.read_text(encoding='utf-8')
        for name, (mutation, error) in cases.items():
            probe = script.replace('BEGIN READ ONLY;', 'BEGIN; ' + mutation)
            result = self.pg.sql('\\set db_v7 ' + DB + '\n\\set loader_role ' + LOADER + '\n' + probe,
                                 database=DB, check=False)
            require(result.returncode != 0 and error in result.stderr, 'checker wrong rejection ' + name)
        try:
            self.check(customers + 1, openings)
        except HarnessError:
            pass
        else:
            raise HarnessError('checker accepted wrong counts')
        self.report['checker_negative_cases'] = list(cases) + ['invalid_counts']

    def execute(self, clean):
        # Source validation is offline and precedes any Docker action.
        exporter.outside_repo(clean)
        clean_data(clean)
        self.start()
        with self.step('preflight'):
            version = self.sql('SHOW server_version', 'postgres')
            require(version.startswith('18.6'), 'wrong PostgreSQL version')
            require(self.sql('SHOW listen_addresses', 'postgres') == '', 'TCP enabled')
            require('/var/run/postgresql' in self.sql('SHOW unix_socket_directories', 'postgres'), 'socket missing')
            require(self.sql("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'v7_%' OR rolname LIKE 'sokhach_%'", 'postgres') == '0', 'V7 roles present')
            require(self.sql("SELECT count(*) FROM pg_database WHERE datname='" + DB + "'", 'postgres') == '0', 'V7 DB present')
            require('18.6' in run(self.pg.psql_command() + ['--version']).stdout, 'psql major mismatch')
            for program in ('pg_dump', 'pg_restore'):
                require(b'18.6' in self.program(program, '--version'), 'client major mismatch')
            available = self.program('df', '-Pk', '/var/lib/postgresql').decode().splitlines()[-1].split()[3]
            size = self.sql("SELECT pg_database_size('webdebit_ledger')", 'postgres')
            require(int(available) * 1024 >= 3 * int(size), 'insufficient disk')
            self.baseline = self.counts('webdebit_ledger')
            self.report['baseline_sha256'] = sha(self.baseline.encode())
        with self.step('backup_restore'):
            for name, data in (
                ('globals.sql', self.program('pg_dumpall', '-h', '/var/run/postgresql', '-U', 'postgres', '--globals-only')),
                ('ledger.dump', self.program('pg_dump', '-h', '/var/run/postgresql', '-U', 'postgres', '-Fc', 'webdebit_ledger')),
            ):
                (self.folder / name).write_bytes(data)
                self.report['sha256'][name] = sha(data)
            listing = self.program('pg_restore', '--list', data=(self.folder / 'ledger.dump').read_bytes())
            require(bool(listing), 'empty dump list')
            (self.folder / 'restore.list').write_bytes(listing)
            self.report['sha256']['restore.list'] = sha(listing)
            self.restore_test('v7_restore_before')
        with self.step('provision'):
            self.sql('CREATE DATABASE ' + DB, 'postgres')
            self.sql(SCHEMA.read_text(encoding='utf-8'))
            self.sql(FUNCTIONS.read_text(encoding='utf-8'))
            self.sql(SHEET_MIGRATION.read_text(encoding='utf-8'))
            self.sql('CREATE ROLE v7_app LOGIN IN ROLE sokhach_app; CREATE ROLE ' + LOADER +
                     ' LOGIN IN ROLE sokhach_owner; REVOKE CONNECT ON DATABASE ' + DB +
                     ' FROM PUBLIC; GRANT CONNECT ON DATABASE ' + DB + ' TO v7_app,' + LOADER)
            self.check(0, 0)
        with self.step('load') as row:
            books, digests, manifest = clean_data(clean)
            row['customers'] = len(books)
            row['openings'] = sum(len(b['openings']) for b in books)
            self.report['sha256'].update(digests)
            self.report['sha256'].update(manifest['files_sha256'])
            def factory(socket, database, role, **kwargs):
                return DirectPg(socket, database, role, psql_command=self.pg.psql_command(), **kwargs)
            args = ['--from-clean', str(clean), '--database', DB, '--loader-role', LOADER]
            # Loader stdout contains private source details; never forward or put in report.
            with redirect_stdout(io.StringIO()) as private_output:
                self.report['executed_commands'].append({'template': COMMANDS['plan']})
                require(load_main(args, pg_factory=factory) == 0, 'load plan failed')
                self.check(0, 0)
                self.report['executed_commands'].append({'template': COMMANDS['apply']})
                require(load_main(args + ['--apply'], pg_factory=factory) == 0, 'load apply failed')
            # Delete only reports created by this invocation of the existing loader.
            for line in private_output.getvalue().splitlines():
                identifier = json.loads(line).get('run_id', '')
                if len(identifier) == 32 and all(c in '0123456789abcdef' for c in identifier):
                    (Path(tempfile.gettempdir()) / 'v7-direct-reports' / (identifier + '.json')).unlink(missing_ok=True)
            self.check(row['customers'], row['openings'])
            self.checker_regressions(row['customers'], row['openings'])
            require(manifest['counts']['customers'] == len(books), 'manifest count mismatch')
        class Handler(api.Handler):
            def log_message(self, *args):
                pass
        Handler.runner = api.PsqlDirect('/var/run/postgresql', DB, 'v7_app', psql_command=self.pg.psql_command())
        Handler.dev_actor_mode = True
        Handler.default_actor = 'rehearsal'
        with redirect_stdout(io.StringIO()):
            server = api.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        Handler.port = server.server_port
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        from urllib.request import Request, urlopen
        def request(path, payload=None):
            headers = {'Origin': base, 'Content-Type': 'application/json'}
            data = None if payload is None else json.dumps(payload).encode()
            with urlopen(Request(base + path, data=data, headers=headers), timeout=30) as response:
                return json.load(response)
        try:
            with self.step('api_reconcile'):
                customers = request('/api/v7/customers')['customers']
                require(bool(customers), 'no loaded customers')
                request('/api/v7/ledger?customer=' + str(customers[0]['id']))
                with redirect_stdout(io.StringIO()) as output:
                    self.report['executed_commands'].append({'template': COMMANDS['reconcile']})
                    result = reconcile.main(['--api', base, '--sheet-dir', str(clean),
                        '--out', str(self.folder / 'reconcile'), '--brief'])
                require(result == 0 and 'DOI SOAT: DAT' in output.getvalue(), 'reconcile failed')
                self.check()
                require(self.counts('webdebit_ledger') == self.baseline, 'legacy changed')
            with self.step('receipt_void_offset'):
                ledgers = {c['id']: request('/api/v7/ledger?customer=' + str(c['id'])) for c in customers}
                targets = [i for i, value in ledgers.items() if int(value['total_outstanding_vnd']) > 0]
                sources = [i for i, value in ledgers.items() if int(value['total_outstanding_vnd']) < 0]
                require(bool(targets and sources), 'OFFSET_SOURCE_MISSING_IN_BUNDLE')
                target, source = targets[0], sources[0]
                today = self.sql("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date")
                def ledger(i):
                    return request('/api/v7/ledger?customer=' + str(i))
                def write(path, **payload):
                    return request(path, dict(customer_id=target, expected_version=ledger(target)['version'],
                        idempotency_key=uuid.uuid4().hex, **payload))
                before = ledger(target)['total_outstanding_vnd']
                receipt = write('/api/v7/receipts', date=today, method='THU TIỀN', amount_vnd='1')
                write('/api/v7/receipts/void', pid=receipt['pid'], reason='rehearsal only')
                require(ledger(target)['total_outstanding_vnd'] == before, 'void did not restore balance')
                request('/api/v7/offsets', {'target_customer_id': target, 'target_version': ledger(target)['version'],
                    'source_customer_id': source, 'source_version': ledger(source)['version'],
                    'idempotency_key': uuid.uuid4().hex, 'date': today, 'amount_vnd': '1'})
                require(int(ledger(target)['total_outstanding_vnd']) == int(before) - 1, 'offset failed')
        finally:
            server.shutdown()
            thread.join(timeout=10)
            server.server_close()
        with self.step('rollback_B'):
            self.sql('DROP DATABASE ' + DB, 'postgres')
            for role in ('v7_app', LOADER, 'sokhach_app', 'sokhach_reader', 'sokhach_owner'):
                self.sql('DROP ROLE ' + role, 'postgres')
            require(self.sql("SELECT count(*) FROM pg_database WHERE datname='" + DB + "'", 'postgres') == '0', 'DB remains')
            require(self.sql("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'v7_%' OR rolname LIKE 'sokhach_%'", 'postgres') == '0', 'role remains')
            require(self.counts('webdebit_ledger') == self.baseline, 'legacy changed')
        with self.step('rollback_C'):
            require(sha((self.folder / 'ledger.dump').read_bytes()) == self.report['sha256']['ledger.dump'], 'backup hash mismatch')
            self.restore_test('v7_restore_after')

    def cleanup(self):
        owned = inspect_owned(self.name, self.volume, self.run_id, self.container_id) if self.volume_created else None
        if owned:
            run(['docker', 'rm', '--force', owned])
        if self.volume_created:
            inspect_volume(self.volume, self.run_id)
            run(['docker', 'volume', 'rm', self.volume])
            require(inspect_owned(self.name, self.volume, self.run_id) is None, 'container remains')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--from-clean', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--strict', action='store_true')
    args = parser.parse_args(argv)
    if args.list:
        for step in STEPS:
            print(step)
        for command in COMMANDS.values():
            print(command)
        return 0
    report = {'run_id': uuid.uuid4().hex, 'image': IMAGE, 'steps': [],
              'commands': COMMANDS, 'executed_commands': [], 'sha256': {}, 'status': 'fail',
              'limits': ['trust not peer', 'systemd and Tailscale not exercised']}
    report['revision'] = run(['git', 'rev-parse', 'HEAD'], cwd=ROOT).stdout.strip()
    for path in (SCHEMA, FUNCTIONS, CHECK, Path(__file__),
                 TOOLS / 'v7_load_direct.py', TOOLS / 'v7_load_real_copy.py',
                 TOOLS / 'v7_export_clean.py', TOOLS / 'v7_reconcile_sheet.py',
                 ROOT / 'cong-no-web-handoff/web/v7_ledger_api.py'):
        report['sha256'][path.name] = sha(path.read_bytes())
    with tempfile.TemporaryDirectory(prefix='v7-rehearsal-') as folder:
        rehearsal = Rehearsal(report, Path(folder))
        try:
            clean = args.from_clean or fake_clean(Path(folder))
            rehearsal.execute(clean)
            require(tuple(s['id'] for s in report['steps']) == STEPS, 'missing steps')
            report['status'] = 'pass'
        except Exception as exc:  # noqa: BLE001 - never expose private data from subprocess errors
            report['error'] = type(exc).__name__
        finally:
            try:
                rehearsal.cleanup()
                report['cleanup'] = 'verified_removed'
            except Exception as exc:  # noqa: BLE001 - same redaction boundary
                report['cleanup'] = 'fail'
                report['error'] = type(exc).__name__
                report['status'] = 'fail'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
    return int(report['status'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
