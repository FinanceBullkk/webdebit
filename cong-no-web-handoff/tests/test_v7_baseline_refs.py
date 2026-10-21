"""Fake clean bundle checks: PLAN, NULL date, missing evidence, tamper."""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import test_v7_export_clean as export_tests
import v7_load_baseline_refs as refs


class BaselineRefsTest(unittest.TestCase):
    setUp = export_tests.ExportCleanTest.setUp
    run_export = export_tests.ExportCleanTest.run_export

    def test_plan_validates_bundle_without_db(self):
        export_tests.fixture(self.folder, bucket_delta=1)
        self.run_export()
        with patch.object(sys, "argv", ["refs", str(self.out), "--cutover-id", "1"]), \
                patch("v7_load_direct.DirectPg", side_effect=AssertionError("PLAN touched DB")), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(refs.main(), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report["mode"], "PLAN")
        self.assertGreater(report["trips"], 0)
        (self.out / "clean_rows.csv").write_text("tampered", encoding="utf-8")
        with patch.object(sys, "argv", ["refs", str(self.out), "--cutover-id", "1"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refs.main(), 1)
        (self.out / "manifest.json").unlink()
        with patch.object(sys, "argv", ["refs", str(self.out), "--cutover-id", "1"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(refs.main(), 1)

    def test_unknown_date_stays_null_and_missing_container_stops(self):
        books = [{"legacy": [{"kind": "trip", "display": {"container": " a\u00a0b ", "date": None}}]}]
        self.assertEqual(refs.references(books), [("ALT:AB:UNKNOWN", "AB", None)])
        books[0]["legacy"][0]["display"]["container"] = ""
        with self.assertRaises(refs.LoadError):
            refs.references(books)
