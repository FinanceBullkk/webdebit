import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import v7_sheet_source_diff as diff


def row(container, date, status="READY", **extra):
    return {"container": container, "event_date": date, "carrier": "WH", "origin": "Kho", "destination": "Port",
            "booking": "BK1", "customer_name": "Khách A", "shipper": "Ship", "durian_type": None, "status": status, **extra}


class SheetSourceDiffTests(unittest.TestCase):
    def test_identical_ready_rows_pass_even_when_row_numbers_and_invalid_rows_differ(self):
        old = [dict(row("ABCU1234567", "2026-10-01"), source_row=2), row("", "", status="INVALID")]
        new = [dict(row("ABCU1234567", "2026-10-01"), source_row=40, source_flag="Thiếu số cont"),
               row("", "", status="INVALID", source_flag="x"), row("", "01/13/2026", status="INVALID")]
        result = diff.compare(old, new)
        self.assertTrue(result["identical_ready"])
        self.assertEqual(result["ready"], {"old": 1, "new": 1, "only_old": 0, "only_new": 0})
        self.assertEqual(result["only_new"], {"INVALID": 1})
        self.assertEqual(result["flagged_new"], 2)

    def test_changed_booking_or_missing_trip_fails(self):
        old = [row("ABCU1234567", "2026-10-01"), row("WXYZ7654321", "2026-10-02")]
        new = [row("ABCU1234567", "2026-10-01", booking="BK2")]
        result = diff.compare(old, new)
        self.assertFalse(result["identical_ready"])
        self.assertEqual(result["field_diffs"], {"booking": 1})
        self.assertEqual(result["only_old"], {"READY": 1})
        self.assertEqual(result["_detail"]["differing"][0]["fields"], ["booking"])

    def test_cli_prints_counts_only_and_writes_detail(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for name, rows in (("old", [row("ABCU1234567", "2026-10-01")]), ("new", [row("ABCU1234567", "2026-10-03")])):
                path = Path(directory) / f"{name}.json"
                path.write_text(json.dumps({"rows": rows, "row_count": len(rows)}), encoding="utf-8")
                paths.append(str(path))
            detail = Path(directory) / "out" / "detail.json"
            import io
            from contextlib import redirect_stdout
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = diff.main([*paths, "--detail", str(detail)])
            self.assertEqual(code, 1)
            printed = buffer.getvalue()
            self.assertNotIn("Khách A", printed)
            self.assertIn('"identical_ready": false', printed)
            self.assertEqual(len(json.loads(detail.read_text(encoding="utf-8"))["only_new"]), 1)
            bad = Path(directory) / "bad.json"
            bad.write_text("{}", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(diff.main([str(bad), paths[1]]), 2)


if __name__ == "__main__":
    unittest.main()
