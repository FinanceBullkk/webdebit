"""Synthetic-only checks for the cleaned-book export. No captures, no Docker."""

import csv
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_export_clean as exporter  # noqa: E402  (sys.path set above)
import v7_load_real_copy as loader  # noqa: E402
from test_v7_load_real_copy import FAKE_AMOUNT, FAKE_NAME, fixture  # noqa: E402


class ExportCleanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "source"
        self.folder.mkdir()
        self.out = Path(self.temp.name) / "clean"

    def run_export(self, *extra):
        output = io.StringIO()
        with redirect_stdout(output):
            code = exporter.main(["--xlsx", str(self.folder / "source-google-export.xlsx"),
                                  "--source-dir", str(self.folder), "--out", str(self.out), *extra])
        return code, output.getvalue()

    def test_export_writes_cleaned_book_manifest_and_prints_no_private_data(self):
        fixture(self.folder, bucket_delta=1)  # hao opening differs from the Sheet: the Sheet wins
        code, printed = self.run_export()
        self.assertEqual(code, 0)
        for secret in (FAKE_NAME, str(FAKE_AMOUNT), "FAKE-CONT-XY"):
            self.assertNotIn(secret, printed)
        manifest = json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["counts"]["customers"], 1)
        self.assertEqual(manifest["control_total_vnd"], FAKE_AMOUNT)
        self.assertEqual(manifest["customers_per_cleaning_rule"]["OPENING_TOTAL_DIFFERS_FROM_HAO"], 1)
        self.assertEqual(manifest["source"]["xlsx_sha256"], exporter.sha256(self.folder / "source-google-export.xlsx"))
        for name, digest in manifest["files_sha256"].items():
            self.assertEqual(exporter.sha256(self.out / name), digest)
        months = list(csv.DictReader((self.out / "clean_months.csv").open(encoding="utf-8-sig")))
        self.assertEqual([(m["customer"], m["debt_month"], int(m["bucket_vnd"])) for m in months],
                         [(FAKE_NAME, "2026-10", FAKE_AMOUNT)])
        self.assertTrue((self.out / "clean_rows.csv").read_text(encoding="utf-8-sig").count("\n") >= 2)
        # The loader's global switches are restored after the export.
        self.assertFalse(loader.SHEET_IS_TRUTH)
        self.assertEqual(loader.PREFERRED_RAW_TABS, ())

    def test_refuses_repo_folder_nonempty_folder_and_held_customers(self):
        fixture(self.folder)
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), \
                unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            exporter.main(["--xlsx", str(self.folder / "source-google-export.xlsx"),
                           "--source-dir", str(self.folder), "--out", str(exporter.REPO / "export-test")])
        self.out.mkdir()
        (self.out / "keep.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), \
                unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
            self.run_export()
        (self.out / "keep.txt").unlink()
        # A customer whose month-end chain does not close is never exported.
        fixture(self.folder, months=[("2026-10", "03/10/2026", FAKE_AMOUNT, FAKE_AMOUNT + 1)])
        code, printed = self.run_export()
        self.assertEqual(code, 2)
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertNotIn(FAKE_NAME, printed)

    def test_all_write_entries_and_temp_stage_reject_repository_paths(self):
        blocked = exporter.REPO / "export-test"
        with self.assertRaises(loader.LoadError):
            exporter.export([], {}, blocked, Path("fake.xlsx"), ())
        with self.assertRaises(loader.LoadError):
            exporter.write_csv(blocked / "fake.csv", ["customer"], [])
        with unittest.mock.patch.object(tempfile, "gettempdir", return_value=str(exporter.REPO)), \
                unittest.mock.patch.object(exporter.shutil, "copyfile") as copy:
            with self.assertRaises(loader.LoadError):
                exporter.build_books(self.folder, self.folder / "fake.xlsx", ())
            copy.assert_not_called()
        other_repo = Path(self.temp.name) / "other-repo"
        other_repo.mkdir()
        (other_repo / ".git").write_text("gitdir: fake", encoding="utf-8")
        with self.assertRaises(loader.LoadError):
            exporter.export([], {}, other_repo / "clean", Path("fake.xlsx"), ())
        with unittest.mock.patch.object(exporter.Path, "resolve", return_value=blocked),                 self.assertRaises(loader.LoadError):
            exporter.outside_repo(self.out)  # resolved junction/symlink target is checked
        self.assertFalse(blocked.exists())
        self.out.mkdir()
        keep = self.out / "keep.txt"
        keep.write_text("keep", encoding="utf-8")
        with self.assertRaises(loader.LoadError):
            exporter.export([], {}, self.out, Path("fake.xlsx"), ())
        self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

    def test_round_trip_preserves_complete_books(self):
        fixture(self.folder, missing_price=True, extra_tab=True)
        books, digests = exporter.build_books(self.folder, self.folder / "source-google-export.xlsx", ())
        manifest = exporter.export(books, digests, self.out, Path("fake.xlsx"), ())
        restored, _, _ = loader.clean_data(self.out)
        self.assertEqual(restored, [b for b in books if b["in_summary"] and not b["reasons"]])
        self.assertEqual(manifest["excluded_counts"]["NOT_ON_TONG"], 1)
        self.assertEqual(manifest["format_version"], 2)
        with unittest.mock.patch.object(loader, "source_data", side_effect=AssertionError("raw read")), \
                unittest.mock.patch.object(loader, "write_report"), \
                unittest.mock.patch.object(loader, "Pg") as db:
            self.assertEqual(loader.main(["--from-clean", str(self.out), "--check-source"]), 0)
            db.assert_not_called()

    def test_fractional_month_totals_round_trip_without_extra_receipts(self):
        fixture(self.folder, receipt="1", receipt_date="03/10/2026",
                months=[("2026-09", "03/09/2026", 100, 99), ("2026-10", "03/10/2026", 100, 198), ("2026-11", "03/11/2026", 100, 296)])
        tabs = list(loader.workbook_rows(self.folder / "source-google-export.xlsx"))
        for _, records in tabs:
            for row, cells in records:
                if row in (3, 13, 23):
                    cells["H"] = "1.5"
        with unittest.mock.patch.object(loader, "workbook_rows", return_value=tabs):
            books, digests = exporter.build_books(self.folder, self.folder / "source-google-export.xlsx", ())
        self.assertFalse(books[0]["reasons"])
        receipts = [r for r in books[0]["legacy"] if r["kind"] == "receipt"]
        self.assertEqual([r["source_total_vnd"] for r in receipts], [1, 1, 2])
        self.assertIn("ROUNDING_APPORTIONED", receipts[2]["display"]["flags"])
        exporter.export(books, digests, self.out, Path("fake.xlsx"), ())
        self.assertEqual(loader.clean_data(self.out)[0], books)

    def test_hash_and_old_format_rejected_before_db(self):
        fixture(self.folder)
        self.run_export()
        target = self.out / "clean_rows.csv"
        target.write_bytes(target.read_bytes() + b"x")
        with self.assertRaisesRegex(loader.LoadError, "CLEAN_HASH_MISMATCH"):
            loader.clean_data(self.out)
        with unittest.mock.patch.object(loader, "Pg") as db, \
                unittest.mock.patch.object(loader, "run") as docker, \
                unittest.mock.patch.object(loader, "write_report"):
            self.assertEqual(loader.main(["--from-clean", str(self.out)]), 1)
            db.assert_not_called()
            docker.assert_not_called()
        path = self.out / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["format_version"] = 1
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(loader.LoadError, "CLEAN_FORMAT_VERSION"):
            loader.clean_data(self.out)

    def test_cli_uses_manifest_control_and_shared_cutover(self):
        fixture(self.folder)
        self.run_export()
        manifest_hash = exporter.sha256(self.out / "manifest.json")
        with unittest.mock.patch.object(loader, "source_data", side_effect=AssertionError("raw read")), \
                unittest.mock.patch.object(loader, "run", return_value=unittest.mock.Mock(
                    stdout="PostgreSQL init process complete; ready for start up.", stderr="")), \
                unittest.mock.patch.object(loader.shutil, "which", return_value="fake"), \
                unittest.mock.patch.object(loader, "inspect_volume"), \
                unittest.mock.patch.object(loader, "inspect_owned", return_value="owned"), \
                unittest.mock.patch.object(loader, "Pg") as db, \
                unittest.mock.patch.object(loader, "call") as call, \
                unittest.mock.patch.object(loader, "version", return_value=0), \
                unittest.mock.patch.object(loader, "write_report"):
            db.return_value.value.return_value = "1"
            self.assertEqual(loader.main(["--from-clean", str(self.out), "--seed-only"]), 0)
        sql = [c.args[0] for c in db.return_value.value.call_args_list]
        cutovers = [q for q in sql if "INSERT INTO sokhach.cutover(" in q]
        self.assertEqual(len(cutovers), 1)
        self.assertIn(manifest_hash, cutovers[0])
        self.assertIn(str(FAKE_AMOUNT), cutovers[0])
        functions = [c.args[1] for c in call.call_args_list]
        self.assertEqual(functions, ["import_cutover", "verify_cutover_customer", "verify_cutover",
                                     "activate_cutover", "activate_cutover_customer"])

    def test_export_gates_fail_before_writing(self):
        import copy

        fixture(self.folder)
        books, digests = exporter.build_books(self.folder, self.folder / "source-google-export.xlsx", ())
        for field, code in (("source_charge_vnd", "CLEAN_MONTH_TOTAL"),
                            ("source_cumulative_vnd", "CLEAN_ANCHOR_CHAIN"),
                            ("bucket_vnd", "CLEAN_BUCKET_TOTAL")):
            broken = copy.deepcopy(books)
            broken[0]["checks"][0][field] += 1
            with self.subTest(field=field), self.assertRaisesRegex(loader.LoadError, code):
                exporter.export(broken, digests, self.out, Path("fake.xlsx"), ())
            self.assertFalse(self.out.exists())
        with self.assertRaisesRegex(loader.LoadError, "CLEAN_CONTROL_TOTAL"):
            loader.validate_books(books, books[0]["anchor"] + 1)

    def test_missing_required_paths_never_read_source(self):
        for args in ([], ["--xlsx", "fake.xlsx"], ["--out", str(self.out)]):
            with self.subTest(args=args), unittest.mock.patch.object(exporter, "build_books") as build, \
                    unittest.mock.patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as raised:
                    exporter.main(args)
                self.assertEqual(raised.exception.code, 2)
                build.assert_not_called()
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
