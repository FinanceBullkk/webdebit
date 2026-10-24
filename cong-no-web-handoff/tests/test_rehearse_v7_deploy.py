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


if __name__ == '__main__':
    unittest.main()
