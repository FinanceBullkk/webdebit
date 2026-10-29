"""CHUNG-TU-01 SQL copies must stay byte-for-byte aligned after LF normalization."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-chung-tu.sql"
ROLLBACK = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-chung-tu.rollback.sql"
FUNCTIONS = ROOT / "cong-no-web-handoff/tools/v7_backend_functions.sql"
SCHEMA = ROOT / "specs/v7-backend/schema-draft.sql"
# Ràng buộc event trong bản chuẩn bằng migration mới nhất dựng lại chúng (XOA-DC-THANG-01 sau CHUNG-TU-01).
EVENT_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-xoa-dieu-chinh-thang.sql"
NAMES = ("_guard_receipt_image", "_receipt_image_matches", "attach_receipt_image", "remove_receipt_image",
         "list_receipt_images", "get_receipt_image", "find_receipt_image")


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def function(source: str, name: str) -> str:
    found = re.search(rf"(?ms)^CREATE OR REPLACE FUNCTION sokhach\.{name}\(.*?\$\$;", source)
    if not found:
        raise AssertionError(f"missing FUNCTION {name}")
    return found.group()


class ChungTuSqlSync(unittest.TestCase):
    def test_functions_match_canonical(self):
        migration, canonical = text(MIGRATION), text(FUNCTIONS)
        for name in NAMES:
            with self.subTest(name=name):
                self.assertEqual(function(migration, name), function(canonical, name))
        trigger = re.search(r"(?m)^DO \$\$ BEGIN IF NOT EXISTS\(SELECT 1 FROM pg_trigger WHERE tgrelid='sokhach\.receipt_image'.*\n.*\n",
                            migration).group()
        self.assertIn(trigger, canonical)

    def test_table_and_event_constraints_match_schema(self):
        migration, schema = text(MIGRATION), text(SCHEMA)
        table = re.search(r"(?ms)^CREATE TABLE IF NOT EXISTS sokhach\.receipt_image\b.*?^CREATE INDEX IF NOT EXISTS receipt_image_customer.*?;\n",
                          migration).group()
        self.assertIn(table, schema)
        migration = text(EVENT_MIGRATION)
        for name, end in (("event_kind_check", r"\)\)"), ("event_snapshot_check", r"ELSE false END\)")):
            with self.subTest(constraint=name):
                body = re.search(rf"(?ms)ADD CONSTRAINT {name} (CHECK .*?{end});", migration).group(1)
                self.assertIn(f"CONSTRAINT {name} {body},", schema)
                self.assertIn("receipt_image", body)

    def test_grants_and_rollback(self):
        migration, canonical, rollback = text(MIGRATION), text(FUNCTIONS), text(ROLLBACK)
        grants = [line for line in migration.splitlines() if line.startswith("GRANT")]
        self.assertEqual(len(grants), 5)
        for line in grants:
            self.assertIn(line, canonical)
        self.assertNotIn("_receipt_image_matches", "".join(grants))
        self.assertIn("RECEIPT_IMAGES_PRESENT", rollback)
        self.assertNotIn("receipt_image'", re.search(r"(?ms)ADD CONSTRAINT event_kind_check.*?;", rollback).group())


if __name__ == "__main__":
    unittest.main()
