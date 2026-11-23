"""Phần không cần DB của v7_schema_snapshot: định dạng quyền và chỗ đặt file sinh tự động.

File trạng thái hiện hành chỉ để đọc: không được rơi vào cổng SQL của Deploy hao, không nằm trong gói release và không
bị luật nghiệp vụ (chỉ quét .sql/.py/.js) đọc như mã nguồn. So nội dung với PostgreSQL thật chạy ở job harness CI.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_schema_snapshot as snap  # noqa: E402 - tools are flat modules

REPO = ROOT.parent
DEPLOY = (REPO / ".github" / "workflows" / "deploy-hao.yml").read_text(encoding="utf-8")
CI = (REPO / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")


class SnapshotFormatTests(unittest.TestCase):
    def test_grants_grouped_by_role_in_stable_order(self):
        self.assertEqual(
            snap.grants([["sokhach_reader", "SELECT"], ["sokhach_app", "UPDATE"], ["sokhach_app", "SELECT"]], "TABLE sokhach.x"),
            ["GRANT SELECT, UPDATE ON TABLE sokhach.x TO sokhach_app;", "GRANT SELECT ON TABLE sokhach.x TO sokhach_reader;"])

    def test_function_revoked_from_public_says_so(self):
        fn = {"signature": "sokhach.f(bigint)", "kind": "f", "owner": "sokhach_owner", "default_acl": False,
              "acl": [["sokhach_app", "EXECUTE"]], "comment": None,
              "definition": "CREATE OR REPLACE FUNCTION sokhach.f(p bigint)\n RETURNS int\nAS $$ SELECT 1 $$\n"}
        out = snap.render_function(fn)
        self.assertEqual(out[0], "-- FUNCTION sokhach.f(bigint)")
        self.assertIn("REVOKE ALL ON FUNCTION sokhach.f(bigint) FROM PUBLIC;", out)
        self.assertIn("GRANT EXECUTE ON FUNCTION sokhach.f(bigint) TO sokhach_app;", out)
        default = snap.render_function({**fn, "default_acl": True, "acl": []})
        self.assertFalse(any(line.startswith("REVOKE") for line in default))

    def test_comment_quotes_are_escaped(self):
        self.assertEqual(snap.comment_line("TABLE", "sokhach.x", "it's"), ["COMMENT ON TABLE sokhach.x IS 'it''s';"])


class SnapshotPlacementTests(unittest.TestCase):
    rel = snap.OUTPUT.relative_to(REPO).as_posix()

    def test_output_is_not_caught_by_deploy_sql_gate(self):
        gate = re.search(r"if grep -E '([^']+)' <<< \"\$changed\"", DEPLOY)
        self.assertIsNotNone(gate, "không tìm thấy cổng SQL trong deploy-hao.yml")
        self.assertIsNotNone(re.search(gate.group(1), "cong-no-web-handoff/tools/v7_backend_functions.sql"))
        self.assertIsNone(re.search(gate.group(1), self.rel), self.rel)
        self.assertNotEqual(snap.OUTPUT.suffix, ".sql")

    def test_output_is_outside_release_archive(self):
        archive = re.search(r'git archive "\$SHA" ([^|\\]+)', DEPLOY)
        self.assertIsNotNone(archive, "không tìm thấy git archive trong deploy-hao.yml")
        paths = archive.group(1).split()
        self.assertIn("cong-no-web-handoff/tools", paths)
        self.assertFalse(any(self.rel == p or self.rel.startswith(p.rstrip("/") + "/") for p in paths), paths)

    def test_committed_file_is_marked_generated(self):
        head = snap.OUTPUT.read_text(encoding="utf-8").splitlines()[:8]
        self.assertIn("-- SINH TỰ ĐỘNG, không sửa tay, không chạy trên hao.", head)
        self.assertTrue(any(snap.REGENERATE in line for line in head))

    def test_ci_harness_job_runs_the_check(self):
        job = CI.split("\n  postgres-v7-backend:", 1)[1].split("\n  postgres-v7-p0:", 1)[0]
        self.assertIn("cong-no-web-handoff/tools/v7_schema_snapshot.py --check", job)


if __name__ == "__main__":
    unittest.main()


class ManifestPlacementTests(unittest.TestCase):
    """Audit SQL 23/11/2026 (F1): bảng băm phải đi theo release (lưới an toàn trên hao đọc nó) và không kích cổng SQL."""
    rel = snap.MANIFEST.relative_to(REPO).as_posix()

    def test_manifest_ships_in_release_archive(self):
        archive = re.search(r'git archive "\$SHA" ([^|\\]+)', DEPLOY)
        self.assertIsNotNone(archive, "không tìm thấy git archive trong deploy-hao.yml")
        paths = archive.group(1).split()
        self.assertTrue(any(self.rel.startswith(p.rstrip("/") + "/") for p in paths), paths)

    def test_manifest_is_not_caught_by_deploy_sql_gate(self):
        gate = re.search(r"if grep -E '([^']+)' <<< \"\$changed\"", DEPLOY)
        self.assertIsNotNone(gate, "không tìm thấy cổng SQL trong deploy-hao.yml")
        self.assertIsNone(re.search(gate.group(1), self.rel), self.rel)

    def test_manifest_sits_next_to_the_safety_net(self):
        import v7_safety_net  # noqa: PLC0415 - tools are flat modules
        self.assertEqual(v7_safety_net.MANIFEST, snap.MANIFEST)
