"""PR-A SQL copies must stay byte-for-byte aligned after LF normalization."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-28-v7-phu-phi-core-a.sql"
PR_B_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-phu-phi-b.sql"
# Bản chuẩn get_ledger phải bằng migration mới nhất thay nó (PR-B P2 sau DA-THU-01, PR-B).
LEDGER_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-phu-phi-b-p2.sql"
# v_adjustment_current: bản chuẩn bằng migration mới nhất thay nó (XOA-DC-THANG-01 sau PR-A).
VIEW_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-xoa-dieu-chinh-thang.sql"
# Rà đường ghi tiền 29/10/2026: bản chuẩn của sáu hàm này bằng migration mới nhất thay chúng.
AUDIT_MIGRATION = ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-ra-ghi-tien.sql"
FUNCTIONS = ROOT / "cong-no-web-handoff/tools/v7_backend_functions.sql"
SCHEMA = ROOT / "specs/v7-backend/schema-draft.sql"


def definition(source: str, kind: str, name: str) -> str:
    pattern = rf"(?ms)^CREATE OR REPLACE {kind} sokhach\.{name}\b.*?" + (r"\$\$;" if kind == "FUNCTION" else r";")
    found = re.search(pattern, source)
    if not found:
        raise AssertionError(f"missing {kind} {name}")
    return found.group().replace("\r\n", "\n")


class FeeSqlSync(unittest.TestCase):
    def test_migration_matches_canonical(self):
        migration = MIGRATION.read_text(encoding="utf-8")
        canonical = FUNCTIONS.read_text(encoding="utf-8")
        for name in ("_fee_cache_check", "_sync_trip_fee", "v7_fee_migration_dry_run",
                     "_compat_trip_fee",
                     "edit_trip_price", "adjust_trip"):
            with self.subTest(name=name):
                self.assertEqual(definition(migration, "FUNCTION", name),
                                 definition(canonical, "FUNCTION", name))
        audit = AUDIT_MIGRATION.read_text(encoding="utf-8")
        for name in ("paste_trips", "record_receipt", "apply_price_table",
                     "list_sheet_trip_refs", "guard_sheet_cross_customer", "resolve_sheet_conflict"):
            with self.subTest(name=name):
                self.assertEqual(definition(audit, "FUNCTION", name), definition(canonical, "FUNCTION", name))
        with self.subTest(name="get_ledger"):
            self.assertEqual(definition(LEDGER_MIGRATION.read_text(encoding="utf-8"), "FUNCTION", "get_ledger"),
                             definition(canonical, "FUNCTION", "get_ledger"))
        self.assertEqual(definition(VIEW_MIGRATION.read_text(encoding="utf-8"), "VIEW", "v_adjustment_current"),
                         definition(canonical, "VIEW", "v_adjustment_current"))
        schema = SCHEMA.read_text(encoding="utf-8")
        for name in ("fee_type", "book_fee_column", "trip_fee_line", "fee_type_audit"):
            with self.subTest(table=name):
                pattern = rf"(?ms)^CREATE TABLE IF NOT EXISTS sokhach\.{name}\b.*?;"
                self.assertEqual(re.search(pattern, migration).group().replace("\r\n", "\n"),
                                 re.search(pattern, schema).group().replace("\r\n", "\n"))
        for pattern in (r"(?ms)^CREATE INDEX IF NOT EXISTS trip_fee_line_.*?;",
                        r"(?ms)^INSERT INTO sokhach\.fee_type\(name,kind,sign,system_key,sort\).*?;",
                        r"(?m)^DO \$\$ BEGIN ALTER TABLE sokhach\.trip_fee_line ADD CONSTRAINT fee_line_.*?END \$\$;"):
            for statement in re.findall(pattern, migration):
                with self.subTest(statement=statement.splitlines()[0]):
                    self.assertIn(statement.replace("\r\n", "\n"), schema.replace("\r\n", "\n"))
        for trigger in ("trip_fee_cache_check", "trip_price_cache_check", "fee_line_guard"):
            blocks = re.findall(r"(?ms)^DO \$\$ BEGIN IF NOT EXISTS\(SELECT 1 FROM pg_trigger.*?END \$\$;", migration)
            block = next(s for s in blocks if f"tgname='{trigger}'" in s)
            with self.subTest(trigger=trigger):
                self.assertIn(block.replace("\r\n", "\n"), canonical.replace("\r\n", "\n"))

    def test_pr_b_all_function_copies_match(self):
        canonical = FUNCTIONS.read_text(encoding="utf-8")
        schema = SCHEMA.read_text(encoding="utf-8")
        pattern = r"(?ms)^CREATE OR REPLACE FUNCTION sokhach\.(\w+)\(.*?\$\$;"
        later = LEDGER_MIGRATION.read_text(encoding="utf-8")
        replaced = {m.group(1) for m in re.finditer(pattern, later)}
        self.assertEqual(replaced, {"_change_trip_fees", "get_ledger"})
        blocks = [m.group() for m in re.finditer(pattern, PR_B_MIGRATION.read_text(encoding="utf-8"))
                  if m.group(1) not in replaced]
        blocks += [m.group() for m in re.finditer(pattern, later)]
        self.assertGreaterEqual(len(blocks), 17)
        for block in blocks:
            with self.subTest(signature=block.split(" RETURNS")[0]):
                self.assertIn(block, canonical)
                self.assertIn(block, schema)

    def test_matrix_drawer_matches_canonical(self):
        migration = (ROOT / "cong-no-web-handoff/tools/migrations/2026-10-29-v7-matrix-drawer-receipts.sql").read_text(encoding="utf-8")
        self.assertEqual(definition(migration, "FUNCTION", "get_receivables_detail"),
                         definition(FUNCTIONS.read_text(encoding="utf-8"), "FUNCTION", "get_receivables_detail"))


if __name__ == "__main__":
    unittest.main()
