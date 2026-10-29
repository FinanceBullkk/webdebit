import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "tools"))
import v7_sheet_export_xlsx as exporter


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class SheetExportXlsxTests(unittest.TestCase):
    def test_writes_xlsx_once_with_hash_and_rejects_non_xlsx(self):
        sheet = "S" * 30
        urls = []

        def opener(body):
            def open_(request, timeout):
                urls.append((request.full_url, request.get_header("Authorization")))
                return Response(body)
            return open_
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "so-goc.xlsx"
            result = exporter.export(sheet, "tok", out, opener(b"PK" + b"x" * 10))
            self.assertEqual(result["bytes"], 12)
            self.assertEqual(len(result["sha256"]), 64)
            self.assertEqual(urls[0], (f"https://docs.google.com/spreadsheets/d/{sheet}/export?format=xlsx", "Bearer tok"))
            with self.assertRaises(FileExistsError):
                exporter.export(sheet, "tok", out, opener(b"PK"))
            html = Path(temp) / "login.xlsx"
            with self.assertRaisesRegex(ValueError, "not an xlsx"):
                exporter.export(sheet, "tok", html, opener(b"<html>"))
            self.assertFalse(html.exists())
        with self.assertRaisesRegex(ValueError, "spreadsheet ID"):
            exporter.export("bad/id", "tok", Path("unused"), opener(b"PK"))


if __name__ == "__main__":
    unittest.main()
