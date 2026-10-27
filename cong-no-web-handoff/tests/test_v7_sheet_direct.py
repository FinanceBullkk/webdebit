"""Direct Sheet reader keeps source rows and unknown money without old CSV inputs."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_sheet_direct as direct  # noqa: E402
from test_v7_load_real_copy import fixture  # noqa: E402


class DirectSheetTest(unittest.TestCase):
    def test_reads_trip_and_receipt_from_xlsx_without_old_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            fixture(source, receipt="20", receipt_date="03/10/2026", missing_price=True)
            for path in source.glob("*.csv"):
                path.unlink()
            summary, rows = direct.inspect(source / "source-google-export.xlsx")
            self.assertEqual((summary["trip_rows"], summary["receipt_rows"]), (1, 1))
            self.assertEqual([r["amount_vnd"] for r in rows], [876543219, 20])
            self.assertIn("MISSING_PRICE", json.loads(rows[0]["flags"]))
            output = root / "output"
            self.assertEqual(direct.main(["--xlsx", str(source / "source-google-export.xlsx"), "--out", str(output)]), 0)
            with (output / "source_rows.csv").open(encoding="utf-8-sig", newline="") as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual([r["kind"] for r in saved], ["trip", "receipt"])
            with self.assertRaises(SystemExit):
                direct.main(["--xlsx", str(source / "source-google-export.xlsx"), "--out", str(output)])


if __name__ == "__main__":
    unittest.main()
