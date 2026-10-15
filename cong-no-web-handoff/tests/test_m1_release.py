"""Package/preflight checks for the M1 viewer runtime. Temporary git repo and fake data only."""

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import m1_release

GIT = shutil.which("git")
RUNTIME = {
    "cong-no-web-handoff/web/ledger_app.py": b"VALUE = 1\n",
    "cong-no-web-handoff/web/ledger_db.py": b"OTHER = 2\n",
    "cong-no-web-handoff/web/style.css": b"body { margin: 0; }\n",
}
EXCLUDED = {
    "cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql": b"-- fixture\n",
    "cong-no-web-handoff/tests/test_x.py": b"import unittest\n",
    "cong-no-web-handoff/preview/page.html": b"<p>preview</p>\n",
    "cong-no-web-handoff/web/app.py": b"OLD = 1\n",
    "captures/raw.csv": b"fake,1\n",
    "docs/note.md": b"note\n",
}


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
        capture_output=True, check=True).stdout.decode().strip()


@unittest.skipUnless(GIT, "git is required")
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        for name, data in {**RUNTIME, **EXCLUDED}.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "fake runtime")
        self.out = base / "package"
        self.base = base

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        return m1_release.build(self.repo, self.out)

    def test_package_has_only_allowlisted_files_and_exact_hashes(self):
        manifest = self.build()
        files = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())
        self.assertEqual(files, ["MANIFEST.json", "web/ledger_app.py", "web/ledger_db.py", "web/style.css"])
        self.assertEqual(manifest["commit"], git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(manifest["tree"], git(self.repo, "rev-parse", "HEAD^{tree}"))
        for entry in manifest["files"]:
            data = (self.out / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(entry["bytes"], len(data))
        self.assertEqual(json.loads((self.out / "MANIFEST.json").read_text()), manifest)
        for banned in ("fixture", "test_", "preview", "captures", ".sql"):
            self.assertFalse([f for f in files if banned in f])

    def test_build_is_deterministic(self):
        self.build()
        first = (self.out / "MANIFEST.json").read_bytes()
        shutil.rmtree(self.out)
        self.build()
        self.assertEqual((self.out / "MANIFEST.json").read_bytes(), first)

    def test_build_refuses_unsafe_targets_and_unclean_or_missing_sources(self):
        with self.assertRaisesRegex(m1_release.ReleaseError, "outside the source repository"):
            m1_release.build(self.repo, self.repo / "package")
        self.out.mkdir()
        (self.out / "old.txt").write_text("x")
        with self.assertRaisesRegex(m1_release.ReleaseError, "empty or new"):
            self.build()
        shutil.rmtree(self.out)
        (self.repo / "cong-no-web-handoff/web/ledger_app.py").write_bytes(b"VALUE = 99\n")
        with self.assertRaisesRegex(m1_release.ReleaseError, "commit or revert"):
            self.build()
        self.assertFalse(self.out.exists())
        git(self.repo, "checkout", "--", ".")
        git(self.repo, "rm", "-q", "cong-no-web-handoff/web/style.css")
        git(self.repo, "commit", "-q", "-m", "drop css")
        with self.assertRaisesRegex(m1_release.ReleaseError, "missing in commit"):
            self.build()

    def test_build_rejects_python_syntax_error(self):
        (self.repo / "cong-no-web-handoff/web/ledger_db.py").write_bytes(b"def broken(:\n")
        git(self.repo, "commit", "-qam", "bad")
        with self.assertRaisesRegex(m1_release.ReleaseError, "syntax error"):
            self.build()

    def snapshot(self, root):
        return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
                for p in sorted(root.rglob("*")) if p.is_file()}

    def test_preflight_is_read_only_and_never_ready_without_acl_check(self):
        self.build()
        installed = self.base / "installed"
        (installed / "web").mkdir(parents=True)
        (installed / "web/ledger_app.py").write_bytes(RUNTIME["cong-no-web-handoff/web/ledger_app.py"])
        (installed / "web/ledger_db.py").write_bytes(b"OTHER = 0\n")
        before = (self.snapshot(self.out), self.snapshot(installed))
        result = m1_release.preflight(self.out, installed)
        self.assertEqual((self.snapshot(self.out), self.snapshot(installed)), before)
        self.assertEqual(result["package"], "ok")
        self.assertFalse(result["ready_for_deploy"])
        self.assertEqual(result["acl"]["status"], "not_checked")
        states = {row["path"]: row["state"] for row in result["installed"]}
        self.assertEqual(states, {"web/ledger_app.py": "identical", "web/ledger_db.py": "different",
                                  "web/style.css": "missing"})

    def test_preflight_rejects_tampering(self):
        manifest = self.build()
        (self.out / "web/ledger_app.py").write_bytes(b"VALUE = 2\n")
        with self.assertRaisesRegex(m1_release.ReleaseError, "ledger_app.py: SHA-256 differs"):
            m1_release.preflight(self.out)
        (self.out / "web/ledger_app.py").write_bytes(RUNTIME["cong-no-web-handoff/web/ledger_app.py"])
        extra = self.out / "web/pg_versioned_approval_fixture.sql"
        extra.write_text("-- fixture")
        with self.assertRaisesRegex(m1_release.ReleaseError, "extra=.*fixture"):
            m1_release.preflight(self.out)
        extra.unlink()
        (self.out / "web/style.css").unlink()
        with self.assertRaisesRegex(m1_release.ReleaseError, "missing=.*style.css"):
            m1_release.preflight(self.out)
        (self.out / "web/style.css").write_bytes(RUNTIME["cong-no-web-handoff/web/style.css"])
        manifest["files"].append({"path": "web/extra.sql", "sha256": "0" * 64, "bytes": 0})
        (self.out / "MANIFEST.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(m1_release.ReleaseError, "allowlist"):
            m1_release.preflight(self.out)
        (self.out / "MANIFEST.json").write_text("{")
        with self.assertRaisesRegex(m1_release.ReleaseError, "MANIFEST.json"):
            m1_release.preflight(self.out)

    def test_preflight_rejects_syntax_error_even_with_matching_hash(self):
        manifest = self.build()
        data = b"def broken(:\n"
        (self.out / "web/ledger_db.py").write_bytes(data)
        for entry in manifest["files"]:
            if entry["path"] == "web/ledger_db.py":
                entry.update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        (self.out / "MANIFEST.json").write_text(json.dumps(manifest))
        with self.assertRaisesRegex(m1_release.ReleaseError, "syntax error"):
            m1_release.preflight(self.out)

    def test_acl_check_gates_readiness_and_reports_503_risk(self):
        self.build()
        queries = []

        def granted(psql, dbname, sql):
            queries.append(sql)
            return [{"view": view, "select": True} for view in m1_release.M1_VIEWS]

        result = m1_release.preflight(self.out, db="pilot_db", rows=granted)
        self.assertTrue(result["ready_for_deploy"])
        self.assertEqual(result["acl"]["status"], "ok")
        self.assertEqual(len(queries), 1)
        self.assertRegex(queries[0], r"^SELECT .*has_table_privilege")
        self.assertNotRegex(queries[0], r"(?i)\b(grant|revoke|insert|update|delete|alter|create|drop)\b")

        def denied(psql, dbname, sql):
            return [{"view": "pilot.m1_provenance", "select": True},
                    {"view": "pilot.m1_exception_detail", "select": False}]

        result = m1_release.preflight(self.out, db="pilot_db", rows=denied)
        self.assertFalse(result["ready_for_deploy"])
        self.assertEqual(result["acl"]["status"], "denied")
        self.assertFalse(result["acl"]["views"]["pilot.m1_customer_diff"])
        self.assertIn("/health would return 503", result["warning"])

        def broken(psql, dbname, sql):
            raise m1_release.ReleaseError("database check failed")

        result = m1_release.preflight(self.out, db="pilot_db", rows=broken)
        self.assertFalse(result["ready_for_deploy"])
        self.assertEqual(result["acl"]["status"], "error")

    def test_cli_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(m1_release.main(["build", str(self.out), "--repo", str(self.repo)]), 0)
            self.assertEqual(m1_release.main(["preflight", str(self.out)]), 1)  # ACL not checked
            (self.out / "web/style.css").write_bytes(b"x")
            self.assertEqual(m1_release.main(["preflight", str(self.out)]), 2)
            self.assertEqual(m1_release.main(["preflight", str(self.out), "--check-db", "bad name;"]), 2)


if __name__ == "__main__":
    unittest.main()
