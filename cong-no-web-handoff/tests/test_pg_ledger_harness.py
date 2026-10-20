"""Offline regression checks; Docker and DB commands are mocked."""

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import pg_ledger_verify
from tools import test_pg_ledger_schema as runner


class LedgerVerifyTest(unittest.TestCase):
    def test_explicit_expectations_and_row_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)
            rows = [{"customer": "FAKE", "debt_period": "2026-01", "balance_vnd": 125,
                     "event_count": 2, "result": "NO_BASELINE"}]
            for name, data in (("period_balances.csv", rows), ("period_reconciliation.csv", rows),
                               ("export.csv", [{**rows[0], "replay_event_count": 2,
                                                "comparison_status": "NO_BASELINE"}])):
                with (report / name).open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=data[0])
                    writer.writeheader()
                    writer.writerows(data)
            expected = {"expect_periods": 1, "expect_total_vnd": 125, "expect_no_baseline": 1}
            self.assertEqual(pg_ledger_verify.verify(report, report / "export.csv", **expected),
                             {"periods": 1, "balance_vnd": 125, "no_baseline": 1})
            export = report / "export.csv"
            original = export.read_text(encoding="utf-8")
            for invalid in (original.replace("125", ""), original.replace("125", "124"),
                            original.replace("NO_BASELINE", "MATCH")):
                export.write_text(invalid, encoding="utf-8")
                with self.assertRaises(ValueError):
                    pg_ledger_verify.verify(report, export, **expected)
            export.write_text(original, encoding="utf-8")
            for key in expected:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    pg_ledger_verify.verify(report, report / "export.csv", **{**expected, key: 3})
            for name in ("period_balances.csv", "period_reconciliation.csv", "export.csv"):
                (report / name).write_text("customer,debt_period\n", encoding="utf-8")
            for periods, total, no_baseline in ((0, 0, 0), (0, 125, 0), (1, 0, 0), (1, 125, -1), (1, 125, 2)):
                with (self.subTest(periods=periods, total=total, no_baseline=no_baseline),
                        self.assertRaisesRegex(ValueError, "expectations must be positive")):
                    pg_ledger_verify.verify(report, export, expect_periods=periods,
                                            expect_total_vnd=total, expect_no_baseline=no_baseline)
            with patch.object(pg_ledger_verify, "verify", return_value={}) as verify:
                argv = ["verify", str(report), str(report / "export.csv")]
                for missing in expected:
                    options = [part for key, value in expected.items() if key != missing
                               for part in ("--" + key.replace("_", "-"), str(value))]
                    with (patch.object(sys, "argv", argv + options), redirect_stderr(io.StringIO()),
                            self.assertRaises(SystemExit) as exc):
                        pg_ledger_verify.main()
                    self.assertEqual(exc.exception.code, 2)
                verify.assert_not_called()
                options = [part for key, value in expected.items()
                           for part in ("--" + key.replace("_", "-"), str(value))]
                with patch.object(sys, "argv", argv + options), redirect_stdout(io.StringIO()):
                    pg_ledger_verify.main()
                verify.assert_called_once_with(report, report / "export.csv", **expected)


class HarnessTest(unittest.TestCase):
    def test_volume_create_failure_still_cleans_and_reports(self):
        for failure in (subprocess.TimeoutExpired("docker", 30), runner.HarnessError("CLI failed")):
            removed = []
            # `failure` và `removed` là biến vòng lặp; buộc vào tham số mặc định
            # để closure luôn dùng đúng vòng đã tạo ra nó.
            def fake_run(args, *, _failure=failure, _removed=removed, **kwargs):
                if args[0] == "git":
                    return subprocess.CompletedProcess(args, 0, "fake-revision", "")
                if args[1:3] == ["volume", "create"]:
                    raise _failure
                if args[1:3] == ["ps", "--all"]:
                    return subprocess.CompletedProcess(args, 0, "", "")
                name = runner.CONTAINER
                if args[1:3] == ["volume", "ls"]:
                    self.assertIn(f"name=^{name}$", args)
                    return subprocess.CompletedProcess(args, 0, name + "\n", "")
                if args[1:3] == ["volume", "inspect"]:
                    value = [{"Name": name, "Labels": {runner.LABEL_TEST: runner.LABEL_VALUE,
                              runner.LABEL_RUN: name.removeprefix("webdebit-pg-ledger-")}}]
                    return subprocess.CompletedProcess(args, 0, json.dumps(value), "")
                if args[1:3] == ["volume", "rm"]:
                    _removed.append(args[-1])
                    return subprocess.CompletedProcess(args, 0, "", "")
                self.fail(f"unexpected command: {args}")
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as tmp:
                report = Path(tmp) / "report.json"
                with patch.object(sys, "argv", ["harness", "--report", str(report)]), \
                     patch.object(runner.shutil, "which", return_value="docker"), \
                     patch.object(runner, "run", side_effect=fake_run), \
                     patch.object(runner, "CONTAINER", ""), redirect_stdout(io.StringIO()):
                    self.assertEqual(runner.main(), 1)
                    self.assertEqual(removed, [runner.CONTAINER])
                self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["cleanup"],
                                 "verified_and_removed")

    def test_volume_identity_mismatch_refuses_removal(self):
        labels = {runner.LABEL_TEST: runner.LABEL_VALUE, runner.LABEL_RUN: "run"}
        for changes in ({"Name": "other"}, {"Labels": {}},
                        {"Labels": {**labels, runner.LABEL_RUN: "other"}},
                        {"Labels": {**labels, runner.LABEL_TEST: "other"}}):
            inspected = [{"Name": "volume", "Labels": labels, **changes}]
            with self.subTest(changes=changes), patch.object(runner, "run", side_effect=[
                    subprocess.CompletedProcess([], 0, "volume\n", ""),
                    subprocess.CompletedProcess([], 0, json.dumps(inspected), "")]) as run:
                with self.assertRaisesRegex(runner.HarnessError, "refusing volume cleanup"):
                    runner.cleanup_owned_volume(["docker"], "volume", "run")
                self.assertEqual(run.call_count, 2)

    def test_absent_volume_and_failed_discovery(self):
        with patch.object(runner, "run", return_value=subprocess.CompletedProcess([], 0, "", "")) as run:
            self.assertFalse(runner.cleanup_owned_volume(["docker"], "volume", "run"))
            self.assertEqual(run.call_count, 1)
        with (patch.object(runner, "run", side_effect=runner.HarnessError("discovery failed")),
              self.assertRaises(runner.HarnessError)):
            runner.cleanup_owned_volume(["docker"], "volume", "run")

    def test_blocking_pids_are_exact_integers(self):
        pids = runner.blocking_pids("2|12:{123},124:{123,456}")
        self.assertEqual(pids, {123, 456})
        self.assertNotIn(12, pids)
        self.assertEqual(runner.blocking_pids(""), set())
