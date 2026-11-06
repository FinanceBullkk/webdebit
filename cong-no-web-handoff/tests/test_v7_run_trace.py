"""Tín hiệu từng bước: đúng nội dung, không có tên khách, và mọi lỗi đều bị nuốt."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import v7_run_trace as run_trace


class RunTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name, "reconcile-run.json")

    def read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_records_stages_counts_and_customers(self) -> None:
        trace = run_trace.RunTrace(self.path, "fix")
        self.assertEqual((self.read()["state"], self.read()["mode"]), ("running", "fix"))
        trace.stage("doc", total=10)
        self.assertEqual((self.read()["stage"], self.read()["total"], self.read()["done"]), ("doc", 10, 0))
        trace.customer(7, decided=True, before_vnd=1000, target_vnd=900)
        trace.customer(7, done=True, after_vnd=900, reason="FIXED")
        row = self.read()["customers"]["7"]
        self.assertEqual((row["before_vnd"], row["after_vnd"], row["target_vnd"], row["reason"]), ("1000", "900", "900", "FIXED"))
        trace.customer(None, reason="CHI_CO_SHEET")
        trace.finish(ok=True, counts={"KHOP": 9}, books=10, fixed=1, created=0)
        final = self.read()
        self.assertEqual((final["state"], final["stage"], final["unlinked"], final["fixed"]), ("done", None, {"CHI_CO_SHEET": 1}, 1))
        self.assertEqual(len(self.path.with_name("reconcile-run-history.jsonl").read_text(encoding="utf-8").splitlines()), 1)

    def test_tick_does_not_write_every_time(self) -> None:
        trace = run_trace.RunTrace(self.path)
        trace.stage("doc", total=100)
        with mock.patch.object(run_trace.RunTrace, "_write") as write:
            for done in range(50):
                trace.tick(done)
        self.assertLessEqual(write.call_count, 1)
        self.assertEqual(trace.data["done"], 49)

    def test_no_path_writes_nothing(self) -> None:
        trace = run_trace.RunTrace(None)
        trace.stage("tai")
        trace.finish(ok=True)
        self.assertFalse(self.path.exists())

    def test_every_failure_is_swallowed(self) -> None:
        with mock.patch.object(run_trace.RunTrace, "_write", side_effect=OSError("đĩa đầy")), mock.patch.object(run_trace.RunTrace, "_append_history", side_effect=OSError("x")):
            trace = run_trace.RunTrace(self.path)
            trace.stage("tai")
            trace.tick(1)
            trace.customer(1, reason="FIXED")
            trace.mark(too_many=True)
            trace.finish(ok=True)
        self.assertTrue(trace.broken)

    def test_unknown_stage_and_unwritable_folder_do_not_raise(self) -> None:
        run_trace.RunTrace(self.path).stage("khong-co")
        blocked = Path(self.path.parent, "a-file")
        blocked.write_text("x", encoding="utf-8")
        trace = run_trace.RunTrace(blocked / "sub" / "reconcile-run.json")
        trace.stage("tai")
        self.assertTrue(trace.broken)

    def test_history_is_pruned(self) -> None:
        history = self.path.with_name("reconcile-run-history.jsonl")
        history.write_text("".join(f'{{"n": {number}}}\n' for number in range(run_trace.PRUNE_AT)), encoding="utf-8")
        run_trace.RunTrace(self.path).finish(ok=True)
        lines = history.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), run_trace.KEEP_RUNS)
        self.assertEqual(json.loads(lines[-1])["state"], "done")

    @unittest.skipIf(os.name == "nt", "quyền file chỉ đo được trên Linux")
    def test_file_is_private(self) -> None:
        run_trace.RunTrace(self.path).finish(ok=True)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.with_name("reconcile-run-history.jsonl").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
