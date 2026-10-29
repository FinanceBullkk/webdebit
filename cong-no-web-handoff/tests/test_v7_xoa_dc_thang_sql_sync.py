"""XOA-DC-THANG-01 SQL copies must stay byte-for-byte aligned after LF normalization."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-xoa-dieu-chinh-thang.sql"
FUNCTIONS = ROOT / "cong-no-web-handoff/tools/v7_backend_functions.sql"
SCHEMA = ROOT / "specs/v7-backend/schema-draft.sql"


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def block(source: str, pattern: str) -> str:
    found = re.search(pattern, source)
    if not found:
        raise AssertionError(f"missing {pattern}")
    return found.group()


class XoaDcThangSqlSync(unittest.TestCase):
    def test_function_view_and_grant_match_canonical(self):
        migration, canonical = text(MIGRATION), text(FUNCTIONS)
        for pattern in (r"(?ms)^-- XOA-DC-THANG-01: xóa điều chỉnh.*?^END \$\$;\n",
                        r"(?ms)^-- Trip adjustments follow current information.*?\);\n",
                        r"(?m)^GRANT EXECUTE ON FUNCTION sokhach\.delete_month_adjustment\(.*\n"):
            with self.subTest(pattern=pattern):
                self.assertIn(block(migration, pattern), canonical)

    def test_column_and_event_constraints_match_schema(self):
        migration, schema = text(MIGRATION), text(SCHEMA)
        self.assertIn("ALTER TABLE sokhach.adjustment ADD COLUMN reverses_adjustment_id bigint UNIQUE "
                      "REFERENCES sokhach.adjustment(id);", schema)
        self.assertIn("ADD COLUMN IF NOT EXISTS reverses_adjustment_id bigint UNIQUE REFERENCES sokhach.adjustment(id);", migration)
        check = re.sub(r"\s+", " ", block(migration, r"(?ms)CONSTRAINT adjustment_reversal_month_only CHECK .*?\)\);"))
        self.assertIn(check, re.sub(r"\s+", " ", schema))
        for name in ("event_kind_check", "event_snapshot_check"):
            with self.subTest(constraint=name):
                body = block(migration, rf"(?ms)ADD CONSTRAINT {name} CHECK .*?;\n")
                self.assertIn("adjust_month_delete", body)
                self.assertIn(body.removeprefix("ADD ").removesuffix(";\n"), schema)


if __name__ == "__main__":
    unittest.main()
