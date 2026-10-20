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
import v7_export_clean as exporter
import v7_load_real_copy as loader
from test_v7_load_real_copy import FAKE_AMOUNT, FAKE_NAME, csv_file, fixture


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
        self.assertEqual(manifest["counts"]["anchor_total_vnd"], FAKE_AMOUNT)
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
        with unittest.mock.patch.object(exporter.Path, "resolve", return_value=blocked):
            with self.assertRaises(loader.LoadError):
                exporter.outside_repo(self.out)  # resolved junction/symlink target is checked
        self.assertFalse(blocked.exists())
        self.out.mkdir()
        keep = self.out / "keep.txt"
        keep.write_text("keep", encoding="utf-8")
        with self.assertRaises(loader.LoadError):
            exporter.export([], {}, self.out, Path("fake.xlsx"), ())
        self.assertEqual(keep.read_text(encoding="utf-8"), "keep")

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
