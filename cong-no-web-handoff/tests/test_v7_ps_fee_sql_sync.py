"""Tách phụ phí theo PS: SQL copies must stay byte-for-byte aligned after LF normalization."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-ps-fee.sql"
FUNCTIONS = ROOT / "cong-no-web-handoff/tools/v7_backend_functions.sql"
SCHEMA = ROOT / "specs/v7-backend/schema-draft.sql"
NAMES = ("_rewrite_trip_fees", "rewrite_trip_fees")


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def function(source: str, name: str) -> str:
    found = re.search(rf"(?ms)^CREATE OR REPLACE FUNCTION sokhach\.{name}\(.*?\$\$;", source)
    if not found:
        raise AssertionError(f"missing FUNCTION {name}")
    return found.group()


class PsFeeSqlSync(unittest.TestCase):
    def test_functions_match_canonical(self):
        migration, canonical = text(MIGRATION), text(FUNCTIONS)
        for name in NAMES:
            with self.subTest(name=name):
                self.assertEqual(function(migration, name), function(canonical, name))

    def test_event_constraints_match_schema(self):
        # The newest migration that rewrites the event constraints carries the whole schema list.
        migration, schema = text(MIGRATION), text(SCHEMA)
        for name, end in (("event_kind_check", r"\)\)"), ("event_snapshot_check", r"ELSE false END\)")):
            with self.subTest(constraint=name):
                body = re.search(rf"(?ms)ADD CONSTRAINT {name} (CHECK .*?{end});", migration).group(1)
                self.assertIn(f"CONSTRAINT {name} {body},", schema)
                # Chạy sau XOA-DC-THANG-01 trên hao: thiếu loại của bên kia thì chạy migration này sẽ làm mất nó.
                for kind in ("rewrite_trip_fees", "adjust_month_delete", "receipt_image", "price_table_apply"):
                    self.assertIn(f"'{kind}'", body)

    def test_grants(self):
        migration, canonical = text(MIGRATION), text(FUNCTIONS)
        grants = [line for line in migration.splitlines() if line.startswith("GRANT")]
        self.assertEqual(grants, ["GRANT EXECUTE ON FUNCTION sokhach.rewrite_trip_fees(bigint,bigint,text,jsonb,jsonb,jsonb,jsonb) TO sokhach_app;"])
        self.assertIn(grants[0], canonical)
        self.assertNotIn("_rewrite_trip_fees", "".join(grants))


if __name__ == "__main__":
    unittest.main()
