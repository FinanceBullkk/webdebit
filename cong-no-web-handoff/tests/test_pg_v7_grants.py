import json
import subprocess
import sys
import unittest
from pathlib import Path


class GrantsRegistrationTest(unittest.TestCase):
    def test_list_ids(self):
        script = Path(__file__).parents[1] / "tools" / "test_pg_v7_grants.py"
        rows = [
            x.split("\t")
            for x in subprocess.run(
                [sys.executable, str(script), "--list"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
        ]
        self.assertEqual(
            [r[0] for r in rows], ["grants.catalog", "grants.denials", "grants.api"]
        )
        self.assertEqual(len(rows), len({r[0] for r in rows}))
        self.assertTrue(all(len(r) == 3 for r in rows))

    def test_registry_checks(self):
        tools = Path(__file__).parents[1] / "tools"
        code = ("import json,sys; sys.path.insert(0,sys.argv[1]); "
                "import test_pg_v7_grants as h; "
                "print(json.dumps([callable(h.CHECKS[c['check']]) for c in h.CASES]))")
        result = subprocess.run([sys.executable, "-c", code, str(tools)],
                                capture_output=True, text=True, check=True)
        self.assertTrue(all(json.loads(result.stdout)))
