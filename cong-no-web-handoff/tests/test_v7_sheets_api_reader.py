"""Sheets API reader feeds the same parser as the XLSX reader. Fake data, fake HTTP; no network."""
import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import v7_load_real_copy as loader  # noqa: E402
import v7_price_match as match  # noqa: E402
import v7_price_snapshot as snapshot_tool  # noqa: E402
import v7_sheets_api_reader as reader  # noqa: E402
from test_v7_load_real_copy import fixture  # noqa: E402

SHEET_ID = "FAKE_SPREADSHEET_ID_0123456789"


def as_api(text):
    """Raw XLSX cell text -> the JSON value UNFORMATTED_VALUE would return."""
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() and "." not in text else number


def api_payloads(xlsx):
    tabs = {}
    for tab, data in loader.workbook_rows(xlsx):
        grid = [[] for _ in range(max((r for r, _ in data), default=0))]
        for row, cells in data:
            line = [""] * max((loader.col_num(c) for c in cells), default=0)
            for column, text in cells.items():
                line[loader.col_num(column) - 1] = as_api(text)
            grid[row - 1] = line
        tabs[tab] = grid
    return tabs


class FakeOpener:
    def __init__(self, tabs):
        self.tabs, self.urls = tabs, []

    def __call__(self, request, timeout):
        url = request.full_url
        self.urls.append(url)
        assert request.headers["Authorization"] == "Bearer fake-token"
        if "values:batchGet" not in url:
            body = {"sheets": [{"properties": {"title": t}} for t in self.tabs]}
        else:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            assert query["valueRenderOption"] == ["UNFORMATTED_VALUE"]
            assert query["dateTimeRenderOption"] == ["SERIAL_NUMBER"]
            titles = [r[1:-1].replace("''", "'") for r in query["ranges"]]
            body = {"valueRanges": [{"range": f"'{t}'!A1:Z99", "values": self.tabs[t]} for t in titles]}
        return io.BytesIO(json.dumps(body).encode("utf-8"))


class ReaderTest(unittest.TestCase):
    def test_cell_text_matches_xlsx_raw_values(self):
        cases = [(None, ""), ("", ""), (True, "1"), (False, "0"), (12500000, "12500000"), (12500000.0, "12500000"),
                 (46298.5, "46298.5"), (" FAKE TEXT ", "FAKE TEXT"), ("#N/A", "#N/A")]
        for value, text in cases:
            with self.subTest(value=value):
                self.assertEqual(reader.cell_text(value), text)

    def test_grid_rows_keep_row_numbers_and_columns(self):
        self.assertEqual(reader.range_start("'Tab'!C4:Z9"), (4, 3))
        self.assertEqual(reader.grid_rows([["A1"], [], ["", 7]], 4, 3), [(4, {"C": "A1"}), (6, {"D": "7"})])

    def test_api_path_parses_like_the_xlsx_path(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture(Path(temp), extra_tab=True)
            xlsx = Path(temp) / "source-google-export.xlsx"
            opener = FakeOpener(api_payloads(xlsx))
            via_api = match.rows_from_scan(loader.scan_tabs(reader.fetch_tabs(SHEET_ID, "fake-token", opener)))
            self.assertEqual(via_api, match.sheet_rows(xlsx))
            self.assertTrue(via_api)

    def test_quotes_tab_names_batches_and_rejects_short_answers(self):
        tabs = {f"KHÁCH '{n}'": [["x"]] for n in range(reader.BATCH + 2)}
        opener = FakeOpener(tabs)
        self.assertEqual([t for t, _ in reader.fetch_tabs(SHEET_ID, "fake-token", opener)], list(tabs))
        self.assertEqual(sum("batchGet" in u for u in opener.urls), 2)

        class Short(FakeOpener):
            def __call__(self, request, timeout):
                if "batchGet" in request.full_url:
                    return io.BytesIO(b'{"valueRanges": []}')
                return super().__call__(request, timeout)
        with self.assertRaises(ValueError):
            list(reader.fetch_tabs(SHEET_ID, "fake-token", Short(tabs)))
        with self.assertRaises(ValueError):
            list(reader.fetch_tabs("../bad", "fake-token", opener))

    def test_snapshot_from_api_equals_snapshot_from_xlsx(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture(Path(temp))
            xlsx = Path(temp) / "source-google-export.xlsx"
            credentials = Path(temp) / "fake-credentials.json"
            credentials.write_text(json.dumps({"type": "service_account", "client_email": "fake@example.invalid",
                                               "private_key": "FAKE"}), encoding="utf-8")
            from_api = snapshot_tool.build_from_api(SHEET_ID, str(credentials), token_exchange=lambda _: "fake-token",
                                                    opener=FakeOpener(api_payloads(xlsx)))
            self.assertEqual(from_api["sha256"], snapshot_tool.build(xlsx)["sha256"])
            self.assertEqual(from_api["source"], {"kind": "sheets_api"})
            with patch.object(snapshot_tool, "build_from_api", side_effect=KeyError("sheets")):
                self.assertEqual(snapshot_tool.main(["--spreadsheet-id", SHEET_ID, "--credentials", str(credentials),
                                                     "--output", str(Path(temp) / "p.json")]), 2)


if __name__ == "__main__":
    unittest.main()
