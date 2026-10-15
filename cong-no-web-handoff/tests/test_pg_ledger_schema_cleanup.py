"""Fault-injection checks for PostgreSQL harness resource cleanup."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


RUNNER = Path(__file__).resolve().parents[1] / "tools" / "test_pg_ledger_schema.py"
SPEC = importlib.util.spec_from_file_location("pg_ledger_schema_runner", RUNNER)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class ContainerCleanupTest(unittest.TestCase):
    def test_removes_owned_container_left_by_timed_out_docker_run(self):
        run_id = "run-123"
        name = f"webdebit-pg-ledger-{run_id}"
        container_id = "a" * 64
        inspected = [{
            "Id": container_id,
            "Name": f"/{name}",
            "Config": {"Labels": {
                runner.LABEL_TEST: runner.LABEL_VALUE,
                runner.LABEL_RUN: run_id,
            }},
        }]
        removed: list[list[str]] = []

        def fake_run(args, **kwargs):
            if args[1:3] == ["run", "--detach"]:
                # Docker created the container, but its CLI never returned success.
                raise subprocess.TimeoutExpired(args, timeout=240)
            if args[1:3] == ["ps", "--all"]:
                return subprocess.CompletedProcess(args, 0, container_id + "\n", "")
            if args[1] == "inspect":
                return subprocess.CompletedProcess(args, 0, json.dumps(inspected), "")
            if args[1:3] == ["rm", "--force"]:
                removed.append(args)
                return subprocess.CompletedProcess(args, 0, container_id + "\n", "")
            self.fail(f"unexpected Docker command: {args}")

        with patch.object(runner, "run", side_effect=fake_run):
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run(["docker", "run", "--detach", "--name", name])
            self.assertTrue(runner.cleanup_owned_container(["docker"], name, run_id))

        self.assertEqual(len(removed), 1)
        self.assertEqual(removed[0][-1], container_id)

    def test_refuses_container_with_mismatched_run_label(self):
        run_id = "run-123"
        name = f"webdebit-pg-ledger-{run_id}"
        inspected = [{
            "Id": "b" * 64,
            "Name": f"/{name}",
            "Config": {"Labels": {
                runner.LABEL_TEST: runner.LABEL_VALUE,
                runner.LABEL_RUN: "another-run",
            }},
        }]

        def fake_run(args, **kwargs):
            if args[1:3] == ["ps", "--all"]:
                return subprocess.CompletedProcess(args, 0, "b" * 64 + "\n", "")
            if args[1] == "inspect":
                return subprocess.CompletedProcess(args, 0, json.dumps(inspected), "")
            self.fail(f"unsafe cleanup command reached: {args}")

        with patch.object(runner, "run", side_effect=fake_run):
            with self.assertRaisesRegex(runner.HarnessError, "refusing container cleanup"):
                runner.cleanup_owned_container(["docker"], name, run_id)


if __name__ == "__main__":
    unittest.main()
