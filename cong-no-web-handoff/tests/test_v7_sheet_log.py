"""Bộ đọc log sửa Sheet (SHEET-LOG-01): API giả, không cần Google thật."""

import datetime as dt
import io
import json
import sys
import unittest
import urllib.parse
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_sheet_log as log  # noqa: E402

NOW = dt.datetime(2026, 11, 5, 4, 30, tzinfo=dt.UTC)   # 11:30 giờ VN
LOG_ID = "fake-log-id"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Google:
    """Giả Sheets API: mỗi dòng log một list theo đúng cột A:K."""

    def __init__(self, rows, headers=log.HEADERS, title="EVENTS"):
        self.rows, self.headers, self.title = rows, headers, title
        self.urls = []

    def __call__(self, request, timeout=None):
        assert request.get_method() == "GET"
        url = urllib.parse.unquote(request.full_url)
        self.urls.append(url)
        if "values:batchGet" in url:
            ranges = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)["ranges"]
            body = {"valueRanges": [{"values": [[self.rows[int(item.split("!K")[1]) - 2][10]]]} for item in ranges]}
        elif "/values/" in url:
            first, last = url.rsplit("!", 1)[1].split(":")
            if first == "A1":
                body = {"values": [list(self.headers)]}
            else:
                start, end = int(first[1:]), int(last[1:])
                body = {"values": [row[:10] for row in self.rows[start - 2:end - 1]]}
        else:
            body = {"sheets": [{"properties": {"title": "Sheet1", "gridProperties": {"rowCount": 1000}}},
                               {"properties": {"title": self.title, "gridProperties": {"rowCount": len(self.rows) + 1}}}]}
        return Response(json.dumps(body).encode())


def line(at="2026-11-05T04:00:00.000Z", kind="EDIT", tab="KHACH A", cell="M5", payload="{}"):
    return ["id", at, kind, "1", tab, cell, "", "group", "1", "1", payload]


def event(minutes_ago, kind="EDIT", tab="KHACH A"):
    return {"row": 2, "at": NOW - dt.timedelta(minutes=minutes_ago), "kind": kind, "tab": tab, "range": "M5"}


class ReadTailTest(unittest.TestCase):
    def test_reads_only_the_tail_and_never_the_payload_column(self):
        google = Google([line(tab=f"T{n}") for n in range(50)])
        events = log.read_tail(LOG_ID, "token", google, rows=10)
        self.assertEqual([e["row"] for e in events], list(range(42, 52)))
        self.assertEqual(events[0]["tab"], "T40")
        self.assertTrue(any(url.endswith("EVENTS!A42:J51") for url in google.urls))
        self.assertFalse(any("K" in url.rsplit("!", 1)[-1] for url in google.urls if "/values/" in url))

    def test_changed_header_or_missing_tab_fails_instead_of_guessing_columns(self):
        with self.assertRaisesRegex(ValueError, "EDIT_LOG_FORMAT"):
            log.read_tail(LOG_ID, "token", Google([line()], headers=("id", "kind", *log.HEADERS[2:])))
        with self.assertRaisesRegex(ValueError, "EDIT_LOG_NO_TAB"):
            log.read_tail(LOG_ID, "token", Google([line()], title="KHAC"))

    def test_row_without_valid_time_is_skipped_and_short_rows_are_read(self):
        short = ["id", "2026-11-05T04:00:00.000Z", "INVENTORY"]
        events = log.read_tail(LOG_ID, "token", Google([line(at="không phải giờ"), short]))
        self.assertEqual([(e["kind"], e["tab"]) for e in events], [("INVENTORY", "")])

    def test_rejects_a_strange_spreadsheet_id(self):
        with self.assertRaisesRegex(ValueError, "invalid spreadsheet ID"):
            log.read_tail("a/b", "token", Google([line()]))


class SummarizeTest(unittest.TestCase):
    def test_keeps_the_latest_edit_per_tab_and_ignores_other_kinds(self):
        state, edits = log.summarize([event(30), event(5, kind="SNAPSHOT"), event(20), event(10, tab="KHACH B")], NOW)
        self.assertEqual(edits, {"KHACH A": NOW - dt.timedelta(minutes=20), "KHACH B": NOW - dt.timedelta(minutes=10)})
        self.assertEqual(state, {"status": "OK", "last_event_at": "2026-11-05T11:25:00+07:00"})

    def test_daily_sweep_keeps_the_log_alive_and_silence_is_stale(self):
        self.assertEqual(log.summarize([event(25 * 60, kind="INVENTORY")], NOW)[0]["status"], "OK")
        self.assertEqual(log.summarize([event(27 * 60, kind="INVENTORY")], NOW)[0]["status"], "STALE")
        self.assertEqual(log.summarize([], NOW), ({"status": "STALE", "last_event_at": None}, {}))


class AnnotateTest(unittest.TestCase):
    DOWNLOADED = NOW - dt.timedelta(minutes=10)

    def row(self, **extra):
        return {"customer": "KHACH A", "status": "LECH_TONG", "reason": "NO_EXACT_FIX", **extra}

    def annotate(self, row, minutes_before_download):
        log.annotate([row], {"KHACH A": self.DOWNLOADED - dt.timedelta(minutes=minutes_before_download)}, self.DOWNLOADED)
        return row

    def test_editing_starts_exactly_fifteen_minutes_before_the_download(self):
        self.assertTrue(self.annotate(self.row(), 15)["sheet_editing"])
        late = self.annotate(self.row(), 16)
        self.assertNotIn("sheet_editing", late)
        self.assertEqual(late["sheet_last_edit_at"], "2026-11-05T11:04:00+07:00")

    def test_an_edit_during_the_run_counts(self):
        self.assertTrue(self.annotate(self.row(), -5)["sheet_editing"])

    def test_write_failures_still_need_a_person_even_if_the_tab_is_being_edited(self):
        for reason in ("VERIFY_FAILED", "WRITE_ERROR", "CHECK_ERROR", "TOO_MANY_DIFFERENT", "WEB_AHEAD", "BOOK_OVERLAP"):
            row = self.annotate(self.row(reason=reason), 1)
            self.assertNotIn("sheet_editing", row, reason)
            self.assertIn("sheet_last_edit_at", row)

    def test_matching_books_and_unknown_tabs_stay_untouched(self):
        matching = self.row(status="KHOP", reason="KHOP")
        other = self.row(customer="KHACH KHAC")
        log.annotate([matching, other], {"KHACH A": self.DOWNLOADED}, self.DOWNLOADED)
        self.assertEqual(matching, self.row(status="KHOP", reason="KHOP"))
        self.assertEqual(other, self.row(customer="KHACH KHAC"))

    def test_tab_name_with_stray_spaces_still_matches(self):
        row = self.row(customer="KHACH  A")
        log.annotate([row], {log.tab_key(" KHACH A "): self.DOWNLOADED}, self.DOWNLOADED)
        self.assertTrue(row["sheet_editing"])


class ReportTest(unittest.TestCase):
    def payload(self, **fields):
        return json.dumps(fields)

    def test_describe(self):
        one = {"old_value_available": True, "old_value": 1050000.0, "event_value_available": True, "event_value": "10500000", "values": [[10500000]]}
        self.assertEqual(log.describe(self.payload(**one)), "1050000.0 → 10500000")
        self.assertEqual(log.describe(self.payload(old_value_available=False, event_value_available=True, event_value="0", values=[[0]])), "0")
        self.assertEqual(log.describe(self.payload(old_value_available=True, old_value="5", event_value_available=False, values=[[""]])), "5 → (trống)")
        self.assertEqual(log.describe(self.payload(old_value_available=False, event_value_available=False, values=[["a", "b"], ["c", "d"]])), "sửa 4 ô")
        self.assertEqual(log.describe('{"schema":1,"val'), "(nội dung dài hoặc không đọc được)")
        self.assertTrue(log.describe(self.payload(old_value_available=False, event_value_available=True, event_value="x" * 200, values=[["x"]])).endswith("..."))

    def test_one_tab_reads_payloads_of_its_edits_only(self):
        rows = [line(at="2026-11-05T04:07:56.000Z", cell="M82", payload=self.payload(old_value_available=False, event_value_available=True, event_value="1050000", values=[[1050000]])),
                line(at="2026-11-05T04:07:57.000Z", kind="SNAPSHOT", cell="A1:Z9", payload="x" * 20000),
                line(at="2026-11-05T04:07:58.000Z", tab="KHACH B", cell="B2", payload="{}"),
                line(at="2026-10-01T04:07:58.000Z", cell="C3", payload="{}")]
        google = Google(rows)
        events = log.read_tail(LOG_ID, "token", google)
        self.assertEqual(log.report(events, LOG_ID, "token", " KHACH  A ", 24, NOW, google), ["05/11 11:07:56  M82           1050000"])
        batch = [url for url in google.urls if "batchGet" in url]
        self.assertEqual(len(batch), 1)
        self.assertEqual(batch[0].count("ranges="), 1)   # SNAPSHOT, tab khác, lần sửa quá hạn không bị tải

    def test_without_a_tab_lists_tabs_latest_first_without_reading_payloads(self):
        rows = [line(at="2026-11-05T01:00:00.000Z"), line(at="2026-11-05T04:00:00.000Z", tab="KHACH B"), line(at="2026-11-05T02:00:00.000Z")]
        google = Google(rows)
        events = log.read_tail(LOG_ID, "token", google)
        self.assertEqual(log.report(events, LOG_ID, "token", None, 24, NOW, google),
                         ["05/11 11:00:00     1 lần  KHACH B", "05/11 09:00:00     2 lần  KHACH A"])
        self.assertFalse(any("batchGet" in url for url in google.urls))

    def test_main_warns_that_silence_does_not_prove_nothing_changed(self):
        google = Google([line(at="2026-11-05T04:00:00.000Z")])
        printed = io.StringIO()
        real = log.read_tail
        with (patch.object(log.sheet_sync_runner, "load_credentials", return_value={}),
              patch.object(log.sheet_sync_runner, "exchange_token", return_value="token"),
              patch.object(log, "read_tail", side_effect=lambda log_id, token, rows: real(log_id, token, google, rows)),
              patch.object(log.dt, "datetime", wraps=dt.datetime) as clock,
              redirect_stdout(printed)):
            clock.now.return_value = NOW
            self.assertEqual(log.main(["--log-id", LOG_ID, "--credentials", "c.json"]), 0)
        self.assertIn("sửa qua API không vào log", printed.getvalue())
        self.assertIn("KHACH A", printed.getvalue())

    def test_main_needs_the_log_id(self):
        with patch("sys.stderr"), patch.dict("os.environ", {}, clear=True), self.assertRaises(SystemExit):
            log.main([])


if __name__ == "__main__":
    unittest.main()
