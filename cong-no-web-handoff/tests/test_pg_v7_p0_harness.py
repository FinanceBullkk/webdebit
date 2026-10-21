"""Offline registration contract; --list must never invoke Docker."""
import json
import subprocess
import sys
import unittest
from pathlib import Path


class P0RegistrationTest(unittest.TestCase):
    def test_list_contract(self):
        script = Path(__file__).parents[1] / "tools" / "test_pg_v7_p0_harness.py"
        result = subprocess.run([sys.executable, str(script), "--list"],
                                capture_output=True, text=True, check=True)
        rows = [line.split("\t") for line in result.stdout.splitlines()]
        ids = [row[0] for row in rows]
        expected = {
            f"idem.{command}{suffix}"
            for command in ("record_receipt", "paste_trips", "edit_trip_price", "adjust_month", "adjust_trip",
                            "edit_receipt_meta", "void_receipt", "set_month_lock")
            for suffix in ("", ".concurrent")
        } | {"race.double_void", "inverse.restore_and_replace", "inverse.preserve_later",
             "policy.refund_transfer"} | {
                 f"race.{kind}{suffix}" for kind in ("void_record", "record_paste", "record_price")
                 for suffix in ("", ".reverse")}
        self.assertEqual(set(ids), expected)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(len(row) == 3 for row in rows))
        self.assertEqual(sum(row[1] == "BEHAVIOR" for row in rows), 25)
        self.assertEqual(sum(row[1] == "SKIPPED_OPEN" for row in rows), 1)

    def test_registry_has_checks_and_open_reasons_without_docker(self):
        tools = Path(__file__).parents[1] / "tools"
        code = ("import json, sys; "
                "sys.path.insert(0, sys.argv[1]); import test_pg_v7_p0_harness as h; "
                "print(json.dumps([(c['id'], bool(c['open_reason']) if "
                "c['label']=='SKIPPED_OPEN' else callable(h.CHECKS[c['check']])) "
                "for c in h.CASES]))")
        result = subprocess.run([sys.executable, "-c", code, str(tools)],
                                capture_output=True, text=True, check=True)
        self.assertTrue(all(valid for _, valid in json.loads(result.stdout)))
