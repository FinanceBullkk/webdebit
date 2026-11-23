"""XOA-DC-THANG-01 SQL copies must stay byte-for-byte aligned after LF normalization."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-xoa-dieu-chinh-thang.sql"
FUNCTIONS = ROOT / "cong-no-web-handoff/tools/v7_backend_functions.sql"
SCHEMA = ROOT / "specs/v7-backend/schema-draft.sql"
EVENT_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-ps-fee.sql"
# DIEU-CHINH-THEO-GIA-01 (23/11/2026) thay v_adjustment_current sau XOA-DC-THANG-01: khối view so với migration đó.
VIEW_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-11-23-v7-dieu-chinh-theo-gia.sql"


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
                        r"(?m)^GRANT EXECUTE ON FUNCTION sokhach\.delete_month_adjustment\(.*\n"):
            with self.subTest(pattern=pattern):
                self.assertIn(block(migration, pattern), canonical)
        # View: điều kiện ẩn dòng đảo dấu của XOA-DC-THANG-01 còn nguyên trong bản mới nhất, và bản đó trùng file chuẩn.
        view = r"(?ms)^CREATE OR REPLACE VIEW sokhach\.v_adjustment_current AS.*?\);\n"
        self.assertIn("AND a.reverses_adjustment_id IS NULL", block(migration, view))
        latest = block(text(VIEW_MIGRATION), view)
        self.assertIn("AND a.reverses_adjustment_id IS NULL", latest)
        self.assertIn(latest, canonical)

    def test_column_and_event_constraints_match_schema(self):
        migration, schema = text(MIGRATION), text(SCHEMA)
        self.assertIn("ALTER TABLE sokhach.adjustment ADD COLUMN reverses_adjustment_id bigint UNIQUE "
                      "REFERENCES sokhach.adjustment(id);", schema)
        self.assertIn("ADD COLUMN IF NOT EXISTS reverses_adjustment_id bigint UNIQUE REFERENCES sokhach.adjustment(id);", migration)
        check = re.sub(r"\s+", " ", block(migration, r"(?ms)CONSTRAINT adjustment_reversal_month_only CHECK .*?\)\);"))
        self.assertIn(check, re.sub(r"\s+", " ", schema))
        for name in ("event_kind_check", "event_snapshot_check"):
            with self.subTest(constraint=name):
                self.assertIn("adjust_month_delete", block(migration, rf"(?ms)ADD CONSTRAINT {name} CHECK .*?;\n"))
                # Bản chuẩn bằng migration mới nhất dựng lại ràng buộc (tách phụ phí PS chạy sau XOA-DC-THANG-01).
                body = block(text(EVENT_MIGRATION), rf"(?ms)ADD CONSTRAINT {name} CHECK .*?;\n")
                self.assertIn("adjust_month_delete", body)
                self.assertIn(body.removeprefix("ADD ").removesuffix(";\n"), schema)


if __name__ == "__main__":
    unittest.main()
