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
import v7_commodity_sql as commodity_sql  # noqa: E402
import v7_export_clean as exporter  # noqa: E402  (sys.path set above)
import v7_load_real_copy as loader  # noqa: E402
from test_v7_load_real_copy import FAKE_AMOUNT, FAKE_NAME, TONG_HEAD, fixture  # noqa: E402


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
        # --hold-out (đối soát cuối tháng): xuất phần còn lại, ghi khách bị giữ ra held.csv, không in tên.
        code, printed = self.run_export("--hold-out")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(printed)["held_customers"], 1)
        self.assertNotIn(FAKE_NAME, printed)
        held = list(csv.DictReader((self.out / "held.csv").open(encoding="utf-8-sig")))
        self.assertEqual([h["customer"] for h in held], [FAKE_NAME])
        self.assertIn("ANCHOR_CHAIN_MISMATCH", held[0]["reasons"])
        self.assertEqual(json.loads((self.out / "manifest.json").read_text(encoding="utf-8"))["counts"]["customers"], 0)
        with self.assertRaisesRegex(loader.LoadError, "CLEAN_HAS_HELD_CUSTOMERS"):
            loader.clean_data(self.out)

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

    def test_commodity_round_trips_and_is_counted_without_names(self):
        fixture(self.folder, tong={6: TONG_HEAD, 8: {"D": "SAU RIENG CANG", "E": FAKE_NAME}})
        code, output = self.run_export()
        self.assertEqual(code, 0)
        self.assertNotIn(FAKE_NAME, output)
        self.assertEqual(json.loads(output)["commodity_counts"], {"NHAN_LA": 0, "Sầu riêng CANG": 1})
        book = loader.clean_data(self.out)[0][0]
        self.assertEqual((book["commodity"], book["transport_mode"]), ("Sầu riêng", "CANG"))

    def test_bad_commodity_metadata_rejected(self):
        fixture(self.folder)
        self.run_export()
        bad_values = ({"commodity": ""}, {"commodity": "Xoài", "transport_mode": "TAU"},
                      {"transport_mode": "BO"}, {"commodity": 1}, {"other": True})
        for index, bad in enumerate(bad_values):
            out = Path(self.temp.name) / f"bad-{index}"
            out.mkdir()
            for name in (*loader.CLEAN_FILES, "manifest.json"):
                (out / name).write_bytes((self.out / name).read_bytes())
            path = out / "clean_customers.csv"
            rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
            rows[0]["metadata"] = json.dumps(bad)
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            manifest["files_sha256"]["clean_customers.csv"] = exporter.sha256(path)
            (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(loader.LoadError, "CLEAN_METADATA"):
                loader.clean_data(out)

    def test_commodity_sql_fills_only_unset_books_and_hides_names(self):
        sql, counts = commodity_sql.statements(
            [FAKE_NAME, "FAKE OTHER", "FAKE UNKNOWN"],
            {FAKE_NAME: "TLONG- BỘ", "FAKE UNKNOWN": "FAKE NEW FRUIT"})
        self.assertNotIn(FAKE_NAME, sql)
        self.assertIn(FAKE_NAME.encode().hex(), sql)
        self.assertIn(b"Thanh long".hex(), sql)
        self.assertEqual(sql.count("UPDATE sokhach.customer"), 1)
        self.assertIn("AND commodity_id IS NULL AND transport_mode IS NULL", sql)
        self.assertIn("transport_mode='BO'", sql)
        self.assertEqual(sql.splitlines()[2], "BEGIN;")
        self.assertTrue(sql.rstrip().endswith("COMMIT;"))
        self.assertEqual(counts, {"Thanh long BO": 1, "CHUA_PHAN_LOAI": 1, "NHAN_LA": 1})

    def test_commodity_sql_cli_refuses_repo_and_existing_output(self):
        fixture(self.folder, tong={6: TONG_HEAD, 8: {"D": "CHUOI", "E": FAKE_NAME}})
        self.run_export()
        xlsx = self.folder / "source-google-export.xlsx"
        inside = ROOT / "mh01-should-not-exist.sql"
        for out in (inside, self.folder / "trips_so_goc.csv"):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(commodity_sql.main(["--xlsx", str(xlsx), "--clean", str(self.out),
                                                     "--out", str(out)]), 1)
        self.assertFalse(inside.exists())
        target = Path(self.temp.name) / "mh01.sql"
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(commodity_sql.main(["--xlsx", str(xlsx), "--clean", str(self.out),
                                                 "--out", str(target)]), 0)
        self.assertNotIn(FAKE_NAME, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["commodity_counts"], {"Chuối": 1})
        self.assertIn(FAKE_NAME.encode().hex(), target.read_text(encoding="utf-8"))

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
