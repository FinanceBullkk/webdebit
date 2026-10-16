import csv
import copy
import json
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tools import pg_m1_report, pg_m1_verify


CAPTURE = "fake-capture"
AS_OF = "2026-10-15"
KINDS = pg_m1_verify.EVENT_KINDS


def write_csv(path, headers, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class M1ExportVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.capture = self.root / "capture"
        self.replay = self.root / "replay"
        self.report = self.root / "report"
        for directory in (self.capture, self.replay, self.report):
            directory.mkdir()
        self.build_fixture()

    def tearDown(self):
        self.temp.cleanup()

    def build_fixture(self):
        self.events = [
            {"customer": "FAKE", "period": "2026-10", "posting_date": AS_OF,
             "kind": "charge", "amount_vnd": 125, "signed_amount_vnd": 125,
             "sheet_gid": 0, "source_row": 7},
            {"customer": "FAKE", "period": "2026-10", "posting_date": AS_OF,
             "kind": "receipt", "amount_vnd": 0, "signed_amount_vnd": 0,
             "sheet_gid": 1, "source_row": 8},
        ]
        (self.replay / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.events), encoding="utf-8"
        )
        summary = {
            "run": {"capture_id": CAPTURE, "source_spreadsheet_id": "fake-spreadsheet",
                    "source_workbook_sha256": "a" * 64, "engine_sha256": "b" * 64,
                    "as_of": AS_OF},
            "reconciliation": {"baseline_date": AS_OF, "old_book_new_minus_old_vnd": 0},
            "totals": {"events_replayed": 2, "periods": 1, "customers": 1, "balance_vnd": 125},
            "coverage": {"Fake": {"accepted": 0, "replayed": 0, "quarantined": 0, "excluded_as_of": 0}},
        }
        (self.replay / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
        source_values = {kind: 0 for kind in KINDS}
        source_values.update(charge=125, receipt=0)
        write_csv(self.replay / "period_balances.csv",
                  ("customer", "period", *(kind + "_vnd" for kind in KINDS), "balance_vnd"),
                  [{"customer": "FAKE", "period": "2026-10", **{kind + "_vnd": amount for kind, amount in source_values.items()}, "balance_vnd": 125}])
        write_csv(self.replay / "customer_balances.csv", ("customer", "balance_vnd"),
                  [{"customer": "FAKE", "balance_vnd": 125}])
        write_csv(self.replay / "period_keys_without_baseline.csv", ("customer", "period"), [])
        write_csv(self.replay / "customer_diffs.csv", ("customer", "baseline_row"), [])
        (self.replay / "exceptions.jsonl").write_text("", encoding="utf-8")

        db_values = {kind: "" for kind in KINDS}
        db_values.update(charge=125, receipt=0)
        write_csv(self.report / "period_balances.csv",
                  ("customer", "debt_period", "event_count", *(kind + "_vnd" for kind in KINDS), "balance_vnd"),
                  [{"customer": "FAKE", "debt_period": "2026-10", "event_count": 2,
                    **{kind + "_vnd": amount for kind, amount in db_values.items()}, "balance_vnd": 125}])
        self.write_counts()
        write_csv(self.report / "coverage.csv",
                  ("tab_title", "source_rows", "decided_rows", "accepted_rows", "replayed_rows", "quarantined_rows", "excluded_as_of_rows"),
                  [{"tab_title": "Fake", "source_rows": 0, "decided_rows": 0,
                    "accepted_rows": 0, "replayed_rows": 0, "quarantined_rows": 0, "excluded_as_of_rows": 0}])
        write_csv(self.report / "customer_balances.csv", ("customer", "balance_vnd"),
                  [{"customer": "FAKE", "balance_vnd": 125}])
        self.write_reconciliation()
        write_csv(self.report / "exceptions.csv", ("code", "sheet_gid", "source_row", "detail", "row_sha256", "source_url"), [])
        (self.capture / "manifest.json").write_text(json.dumps({"tabs": []}), encoding="utf-8")
        self.actual_summary = {
            "capture_id": CAPTURE, "as_of": AS_OF, "source_spreadsheet_id": "fake-spreadsheet",
            "source_workbook_sha256": "a" * 64, "engine_sha256": "b" * 64,
            "baseline_date": AS_OF, "comparison_status": "compared", "source_rows": 0,
            "decided_rows": 0, "events": 2, "periods": 1, "source_customers": 1,
            "balance_vnd": 125, "event_count_evidence_rows": 6,
        }
        self.save_actual_summary()

    def write_counts(self, changes=None, *, headers=None, rows=None):
        if rows is None:
            rows = []
            for kind in KINDS:
                count = sum(event["kind"] == kind for event in self.events)
                rows.append({"capture_id": CAPTURE, "as_of": AS_OF, "customer": "FAKE",
                             "debt_period": "2026-10", "kind": kind, "event_count": count,
                             "amount_nonnull_count": count})
        if changes:
            for row in rows:
                if row["kind"] in changes:
                    row.update(changes[row["kind"]])
        write_csv(self.report / "period_event_counts.csv",
                  headers or ("capture_id", "as_of", "customer", "debt_period", "kind", "event_count", "amount_nonnull_count"), rows)

    def write_reconciliation(self, period=None, customer=None):
        write_csv(self.report / "period_reconciliation.csv", ("customer", "debt_period", "result", "delta_vnd"),
                  [{"customer": "FAKE", "debt_period": "2026-10", "result": "MATCH", "delta_vnd": 0}]
                  if period is None else period)
        write_csv(self.report / "customer_reconciliation.csv", ("customer", "result", "delta_vnd", "old_book_delta_vnd"),
                  [{"customer": "FAKE", "result": "MATCH", "delta_vnd": 0, "old_book_delta_vnd": 0}]
                  if customer is None else customer)

    def save_actual_summary(self):
        (self.report / "summary.json").write_text(json.dumps(self.actual_summary), encoding="utf-8")

    def update_source_events(self):
        (self.replay / "events.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.events), encoding="utf-8"
        )

    def update_db_period(self, **changes):
        path = self.report / "period_balances.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            headers, rows = reader.fieldnames, list(reader)
        rows[0].update(changes)
        write_csv(path, headers, rows)

    def test_valid_no_event_null_and_true_zero_amount(self):
        result = pg_m1_verify.verify(self.capture, self.replay, self.report)
        self.assertEqual(result["events_checked"], 2)
        self.assertEqual(result["event_count_rows_checked"], 6)
        self.assertEqual(self.read_db_component("opening_vnd"), "")
        self.assertEqual(self.read_db_component("receipt_vnd"), "0")

    def read_db_component(self, field):
        with (self.report / "period_balances.csv").open(encoding="utf-8", newline="") as stream:
            return next(csv.DictReader(stream))[field]

    def test_missing_source_amount_fails_as_missing_evidence(self):
        self.events[0].pop("amount_vnd")
        self.update_source_events()
        with self.assertRaisesRegex(ValueError, "Source event amount missing"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_db_nonnull_count_below_event_count_fails(self):
        self.write_counts({"charge": {"amount_nonnull_count": 0}})
        with self.assertRaisesRegex(ValueError, "DB event amount missing"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_present_event_with_null_aggregate_fails(self):
        self.update_db_period(charge_vnd="")
        with self.assertRaisesRegex(ValueError, "DB amount aggregate missing"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_missing_count_file_requires_fresh_export(self):
        (self.report / "period_event_counts.csv").unlink()
        with self.assertRaisesRegex(ValueError, "Incomplete M1 count evidence; export again"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_missing_count_column_requires_fresh_export(self):
        path = self.report / "period_event_counts.csv"
        rows = pg_m1_verify.csv_rows(path)
        write_csv(path, ("capture_id", "as_of", "customer", "debt_period", "kind", "event_count"),
                  [{key: value for key, value in row.items() if key != "amount_nonnull_count"} for row in rows])
        with self.assertRaisesRegex(ValueError, "missing columns.*amount_nonnull_count"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_missing_count_row_requires_fresh_export(self):
        rows = pg_m1_verify.csv_rows(self.report / "period_event_counts.csv")[:-1]
        self.write_counts(rows=rows)
        with self.assertRaisesRegex(ValueError, "Missing or extra period/kind count evidence"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_negative_fractional_and_inconsistent_counts_fail(self):
        for value in ("-1", "1.5"):
            with self.subTest(value=value):
                self.write_counts({"charge": {"event_count": value}})
                message = "Invalid count evidence values" if value == "-1" else "integer amount/count"
                with self.assertRaisesRegex(ValueError, message):
                    pg_m1_verify.verify(self.capture, self.replay, self.report)
        self.write_counts({"charge": {"event_count": 1, "amount_nonnull_count": 2}})
        with self.assertRaisesRegex(ValueError, "Invalid count evidence values"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        self.write_counts({"charge": {"event_count": 0, "amount_nonnull_count": 0},
                           "receipt": {"event_count": 2, "amount_nonnull_count": 2}})
        with self.assertRaisesRegex(ValueError, "Source and DB event counts differ"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_nonmatching_counts_fail(self):
        self.write_counts({"charge": {"event_count": 0, "amount_nonnull_count": 0}})
        with self.assertRaisesRegex(ValueError, "count evidence.*totals differ"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_duplicate_count_row_fails(self):
        rows = pg_m1_verify.csv_rows(self.report / "period_event_counts.csv")
        rows.append(dict(rows[0]))
        self.write_counts(rows=rows)
        with self.assertRaisesRegex(ValueError, "Duplicate count evidence row"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_scope_capture_and_as_of_are_required_and_matched(self):
        path = self.report / "period_event_counts.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        original_rows = copy.deepcopy(rows)
        for field in ("capture_id", "as_of"):
            headers = [key for key in rows[0] if key != field]
            with self.subTest(missing=field):
                write_csv(path, headers, [{key: val for key, val in row.items() if key != field} for row in rows])
                with self.assertRaisesRegex(ValueError, "missing columns"):
                    pg_m1_verify.verify(self.capture, self.replay, self.report)
        rows = original_rows
        for field, wrong in (("capture_id", "other-capture"), ("as_of", "2026-10-14")):
            with self.subTest(wrong=field):
                changed = [dict(row) for row in rows]
                changed[0][field] = wrong
                self.write_counts(rows=changed)
                with self.assertRaisesRegex(ValueError, "scope differs"):
                    pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_bad_kind_and_nonzero_aggregate_without_events_fail(self):
        rows = pg_m1_verify.csv_rows(self.report / "period_event_counts.csv")
        rows[0]["kind"] = "unknown"
        self.write_counts(rows=rows)
        with self.assertRaisesRegex(ValueError, "Invalid count evidence key or kind"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        self.write_counts()
        self.update_db_period(opening_vnd="1")
        with self.assertRaisesRegex(ValueError, "Nonzero aggregate without"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_source_event_fields_types_keys_kind_and_snapshot_are_validated(self):
        for field, value, message in (
            ("kind", "unknown", "Invalid source event kind"),
            ("period", "0000-10", "Invalid source event period"),
            ("sheet_gid", -1, "Invalid source event key sheet_gid"),
            ("source_row", 0, "Invalid source event key source_row"),
            ("posting_date", "2026-10-16", "outside as-of snapshot"),
            ("amount_vnd", 1.5, "Invalid source event amount"),
        ):
            with self.subTest(field=field):
                self.events[0][field] = value
                self.update_source_events()
                with self.assertRaisesRegex(ValueError, message):
                    pg_m1_verify.verify(self.capture, self.replay, self.report)
                self.build_fixture()

    def test_summary_must_attest_count_evidence_row_total(self):
        del self.actual_summary["event_count_evidence_rows"]
        self.save_actual_summary()
        with self.assertRaisesRegex(ValueError, "Count evidence row total missing"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_amount_mismatch_and_null_balance_fail(self):
        self.update_db_period(charge_vnd="124")
        with self.assertRaisesRegex(ValueError, "DB amount aggregate differs"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        self.update_db_period(charge_vnd="125", balance_vnd="")
        with self.assertRaisesRegex(ValueError, "Missing integer amount/count"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_source_missing_amount_aggregate_fails(self):
        path = self.replay / "period_balances.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            headers, rows = reader.fieldnames, list(reader)
        rows[0]["charge_vnd"] = ""
        write_csv(path, headers, rows)
        with self.assertRaisesRegex(ValueError, "Source amount aggregate missing"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_blank_delta_or_failed_baseline_result_is_not_a_pass(self):
        base = {"customer": "FAKE", "debt_period": "2026-10", "result": "MATCH", "delta_vnd": 0}
        for changes, message in (
            ({"result": "INVALID_BASELINE", "delta_vnd": ""}, "baseline result is not acceptable"),
            ({"result": "DUPLICATE_BASELINE"}, "baseline result is not acceptable"),
            ({"result": "MISMATCH", "delta_vnd": 5}, "baseline result is not acceptable"),
            ({"delta_vnd": ""}, "baseline delta missing"),
            ({"delta_vnd": 3}, "Nonzero DB baseline difference"),
        ):
            with self.subTest(changes=changes):
                self.write_reconciliation(period=[{**base, **changes}])
                with self.assertRaisesRegex(ValueError, message):
                    pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_reconciliation_must_cover_every_replayed_key(self):
        self.write_reconciliation(period=[])
        with self.assertRaisesRegex(ValueError, "Period reconciliation lacks rows"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        self.write_reconciliation(customer=[])
        with self.assertRaisesRegex(ValueError, "Customer reconciliation lacks rows"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        duplicate = {"customer": "FAKE", "debt_period": "2026-10", "result": "MATCH", "delta_vnd": 0}
        self.write_reconciliation(period=[duplicate, dict(duplicate)])
        with self.assertRaisesRegex(ValueError, "Duplicate Period reconciliation key"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_blank_old_book_delta_fails_for_baselined_customer(self):
        row = {"customer": "FAKE", "result": "MATCH", "delta_vnd": 0, "old_book_delta_vnd": ""}
        self.write_reconciliation(customer=[row])
        with self.assertRaisesRegex(ValueError, "Old book delta missing for a baselined customer"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        # No baseline: the delta is legitimately unknown and contributes nothing.
        write_csv(self.replay / "customer_diffs.csv", ("customer", "baseline_row"),
                  [{"customer": "FAKE", "baseline_row": ""}])
        self.write_reconciliation(customer=[{**row, "result": "NO_BASELINE", "delta_vnd": ""}])
        self.assertEqual(pg_m1_verify.verify(self.capture, self.replay, self.report)["old_book_delta_vnd"], 0)
        write_csv(self.replay / "customer_diffs.csv", ("customer", "baseline_row"), [])
        self.write_reconciliation(customer=[{**row, "old_book_delta_vnd": 7}])
        with self.assertRaisesRegex(ValueError, "old-book difference changed"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_customer_no_baseline_must_match_replay(self):
        row = {"customer": "FAKE", "result": "NO_BASELINE", "delta_vnd": "", "old_book_delta_vnd": ""}
        self.write_reconciliation(customer=[row])  # DB says no baseline, replay says baselined
        with self.assertRaisesRegex(ValueError, "Unmatched customer baseline keys differ"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        write_csv(self.replay / "customer_diffs.csv", ("customer", "baseline_row"),
                  [{"customer": "FAKE", "baseline_row": ""}])
        self.write_reconciliation()  # replay says no baseline, DB says MATCH
        with self.assertRaisesRegex(ValueError, "Unmatched customer baseline keys differ"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)
        (self.replay / "customer_diffs.csv").unlink()
        with self.assertRaisesRegex(ValueError, "missing customer_diffs.csv"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_old_period_export_without_event_count_column_requires_fresh_export(self):
        path = self.report / "period_balances.csv"
        rows = pg_m1_verify.csv_rows(path)
        write_csv(path, [name for name in rows[0] if name != "event_count"],
                  [{k: v for k, v in row.items() if k != "event_count"} for row in rows])
        with self.assertRaisesRegex(ValueError, "export again.*missing columns.*event_count"):
            pg_m1_verify.verify(self.capture, self.replay, self.report)

    def test_export_query_and_csv_format_include_scoped_six_kind_counts(self):
        query = pg_m1_report.period_event_counts_query(CAPTURE, date.fromisoformat(AS_OF))
        self.assertIn("pilot.replay_event", query)
        self.assertIn("count(e.event_no) AS event_count", query)
        self.assertIn("count(e.amount_vnd) AS amount_nonnull_count", query)
        self.assertIn(f"capture_id = '{CAPTURE}'", query)
        self.assertIn(f"as_of = '{AS_OF}'::date", query)
        for kind in KINDS:
            self.assertIn(f"('{kind}')", query)

        outputs = {
            "provenance.csv": "capture_id,as_of,source_spreadsheet_id,source_title,source_workbook_sha256,engine_sha256,baseline_date\nfake-capture,2026-10-15,fake-spreadsheet,Fake,aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa,bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb,2026-10-15\n",
            "coverage.csv": "tab_title,source_rows,decided_rows,missing_rows,accepted_rows,replayed_rows,quarantined_rows,excluded_as_of_rows\nKhách hàng,1,1,0,1,0,0,0\nSố dư đầu,0,0,0,0,0,0,0\nChuyến hàng,0,0,0,0,0,0,0\nThu & cấn trừ,0,0,0,0,0,0,0\n",
            "period_balances.csv": "customer,debt_period,event_count,balance_vnd\nFAKE,2026-10,2,125\n",
            "customer_balances.csv": "customer,balance_vnd\nFAKE,125\n",
            "period_reconciliation.csv": "result\n",
            "customer_reconciliation.csv": "result,old_book_delta_vnd\n",
            "exceptions.csv": "code\n",
        }
        queries = []

        def fake_psql(psql, dbname, sql, output, sudo_user=None):
            queries.append(sql)
            if output.name == "period_event_counts.csv":
                output.write_text(
                    "capture_id,as_of,customer,debt_period,kind,event_count,amount_nonnull_count\n"
                    "fake-capture,2026-10-15,FAKE,2026-10,charge,1,1\n", encoding="utf-8"
                )
            else:
                output.write_text(outputs[output.name], encoding="utf-8")

        output = self.root / "export"
        with patch.object(pg_m1_report, "run_psql", side_effect=fake_psql):
            result = pg_m1_report.export("psql", "fake-db", CAPTURE, date.fromisoformat(AS_OF), output)
        self.assertEqual(result["event_count_evidence_rows"], 1)
        self.assertEqual(len(queries), len(pg_m1_report.REPORTS) + 1)
        self.assertTrue((output / "period_event_counts.csv").is_file())
        self.assertIn("count(e.amount_vnd)", queries[-1])

    def test_export_rejects_worktree_output_before_creating_it_or_querying(self):
        root = Path(pg_m1_report.__file__).resolve().parents[2]
        output = root / f".t10-output-guard-{uuid.uuid4().hex}"
        with patch.object(pg_m1_report, "run_psql") as run_psql:
            with self.assertRaisesRegex(ValueError, "outside the source repository"):
                pg_m1_report.export("psql", "fake-db", CAPTURE, date.fromisoformat(AS_OF), output)
        run_psql.assert_not_called()
        self.assertFalse(output.exists())

    def test_count_query_rejects_invalid_scope_input(self):
        with self.assertRaisesRegex(ValueError, "Invalid capture ID"):
            pg_m1_report.period_event_counts_query("bad'capture", date.fromisoformat(AS_OF))
        with self.assertRaisesRegex(ValueError, "Invalid as-of date"):
            pg_m1_report.period_event_counts_query(CAPTURE, "2026-10-15")
        with self.assertRaisesRegex(pg_m1_report.argparse.ArgumentTypeError, "YYYY-MM-DD"):
            pg_m1_report.parse_as_of("20261015")


if __name__ == "__main__":
    unittest.main()
