"""Offline rehearsal contract checks; no Docker or external source data."""
import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import rehearse_v7_deploy as rehearsal  # noqa: E402 - tools are flat modules


class RehearsalTests(unittest.TestCase):
    def test_sql_allowlist_matches_catalog_harness(self):
        spec = importlib.util.spec_from_file_location(
            'v7_grants_catalog_harness', ROOT / 'tools/test_pg_v7_grants.py')
        grants = importlib.util.module_from_spec(spec)
        # Discovery may already cache tests/test_pg_v7_grants.py under this name.
        with patch.dict(sys.modules, {'test_pg_v7_grants': unittest}):
            spec.loader.exec_module(grants)
        sql = rehearsal.CHECK.read_text(encoding='utf-8')
        allowlist = sql.split('expected text[] := ARRAY[', 1)[1].split('];', 1)[0]
        self.assertEqual(set(re.findall(r"'([^']+)'", allowlist)), grants.READ | grants.APP_READ | grants.WRITE)
        reader = sql.split('expected_reader text[] := ARRAY[', 1)[1].split('];', 1)[0]
        self.assertEqual(set(re.findall(r"'([^']+)'", reader)), grants.READ)
        self.assertIn('BEGIN READ ONLY;', sql)
        self.assertIn('ROLLBACK;', sql)

    def test_command_templates_match_runbook(self):
        text = (ROOT.parent / 'docs/v7-deploy-runbook.md').read_text(encoding='utf-8-sig')
        for name, command in rehearsal.COMMANDS.items():
            with self.subTest(command=name):
                self.assertIn(command, text)

    def test_list_never_invokes_docker(self):
        with patch.object(rehearsal, 'run', side_effect=AssertionError('unexpected command')), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(rehearsal.main(['--list']), 0)
        self.assertIn('rollback_C', out.getvalue())

    def test_fake_bundle_has_debt_and_advance(self):
        with tempfile.TemporaryDirectory() as folder:
            clean = rehearsal.fake_clean(Path(folder))
            books, _, manifest = rehearsal.clean_data(clean)
            self.assertEqual(len(books), 2)
            self.assertTrue(any(b['anchor'] > 0 for b in books))
            self.assertTrue(any(b['anchor'] < 0 for b in books))
            self.assertEqual(manifest['counts']['customers'], 2)

    def test_hash_tamper_rejected_before_docker(self):
        with tempfile.TemporaryDirectory() as folder:
            clean = rehearsal.fake_clean(Path(folder))
            path = clean / 'clean_customers.csv'
            path.write_bytes(path.read_bytes() + b'\n')
            with self.assertRaisesRegex(rehearsal.exporter.loader.LoadError, 'CLEAN_HASH_MISMATCH'):
                rehearsal.clean_data(clean)

    def test_failure_report_redacts_source_and_always_cleans(self):
        secret = 'PRIVATE CUSTOMER 987654321 /private/source'
        with tempfile.TemporaryDirectory() as folder:
            report = Path(folder) / 'report.json'
            with patch.object(rehearsal, 'fake_clean', return_value=Path(folder)), \
                 patch.object(rehearsal.Rehearsal, 'execute', side_effect=RuntimeError(secret)), \
                 patch.object(rehearsal.Rehearsal, 'cleanup') as cleanup, \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(rehearsal.main(['--strict', '--report', str(report)]), 1)
            cleanup.assert_called_once()
            self.assertNotIn(secret, report.read_text())
            self.assertNotIn(secret, out.getvalue())
            self.assertEqual(json.loads(report.read_text())['status'], 'fail')

    def test_cli_list(self):
        result = subprocess.run([sys.executable, str(ROOT / 'tools/rehearse_v7_deploy.py'), '--list'],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


# Runs in a fresh interpreter: tools/ and tests/ both have a test_pg_v7_grants module.
STARTUP_DRIVER = r'''
import contextlib, importlib, io, itertools, json, subprocess, sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, sys.argv[1])
ready_on_poll = int(sys.argv[3])  # 0: the server never accepts connections
import pg_v7_harness
harness = importlib.import_module(sys.argv[2])
events, polls = [], itertools.count(1)

def fake_run(args, input_text=None, **_):
    stdout = ''
    code = 0
    if 'logs' in args:
        stdout = 'PostgreSQL init process complete; ready for start up.'
    elif 'pg_isready' in args:
        code = 0 if next(polls) == ready_on_poll else 1
        events.append('rejected' if code else 'ready')
    elif input_text is not None:  # only SQL statements are sent on stdin
        events.append('sql')
        raise harness.HarnessError('stop after first SQL')
    return subprocess.CompletedProcess(args, code, stdout, '')

clock = itertools.count()
out = io.StringIO()
error = None
with patch.object(harness, 'run', fake_run), patch.object(pg_v7_harness, 'run', fake_run), \
     patch.object(harness, 'inspect_owned', lambda *a: 'cid'), \
     patch.object(harness, 'inspect_volume', lambda *a: None), \
     patch('time.sleep', lambda _: None), patch('time.monotonic', lambda: next(clock)), \
     patch.object(sys, 'argv', [sys.argv[2]]), contextlib.redirect_stdout(out):
    if hasattr(harness, 'Rehearsal'):
        try:
            harness.Rehearsal({'run_id': 'fake', 'executed_commands': []}, Path('.')).start()
        except harness.HarnessError as exc:
            error = str(exc)
    else:
        harness.main()
        error = json.loads(out.getvalue())['error']
print(json.dumps({'events': events, 'error': error}))
'''


class StartupReadinessTests(unittest.TestCase):
    """The init marker precedes the final restart, so SQL must wait for pg_isready."""

    HARNESSES = ('rehearse_v7_deploy', 'test_pg_v7_direct', 'test_pg_v7_grants')

    def drive(self, harness, ready_on_poll):
        result = subprocess.run(
            [sys.executable, '-c', STARTUP_DRIVER, str(ROOT / 'tools'), harness, str(ready_on_poll)],
            capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.splitlines()[-1])

    def test_first_sql_waits_until_server_accepts_connections(self):
        for harness in self.HARNESSES:
            with self.subTest(harness=harness):
                self.assertEqual(self.drive(harness, 3)['events'], ['rejected', 'rejected', 'ready', 'sql'])

    def test_server_that_never_starts_times_out_without_sql(self):
        for harness in self.HARNESSES:
            with self.subTest(harness=harness):
                state = self.drive(harness, 0)
                self.assertNotIn('sql', state['events'])
                self.assertEqual(state['error'], 'PostgreSQL readiness timed out')


if __name__ == '__main__':
    unittest.main()
