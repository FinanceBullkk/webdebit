"""v7_backup `daily` (timer entry) and git-archive copies. Fake rows, no DB/Docker."""

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_backup as backup  # noqa: E402  (sys.path set above)

STATE = {"table_row_counts": {"customer": 2, "trip": 1},
         "customer_totals": {"1": "9007199254740993", "2": None}}


@contextmanager
def temporary_directory(prefix):
    # Same reason as tools/test_v7_backup.py: TemporaryDirectory's mkdir(0o700)
    # excludes the Windows sandbox token; the default ACL is fine for fake rows.
    folder = Path(tempfile.gettempdir()) / (prefix + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        shutil.rmtree(folder)


class FakeSnapshot:
    id = "FAKE-SNAPSHOT"

    def __init__(self, pg):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def query(self, sql):
        return "18.6"


def fake_run(program, *args, **kwargs):
    if args == ("--version",):
        return "pg_dump (PostgreSQL) 18.6\n"
    kwargs["stdout"].write(b"fake dump bytes")
    return ""


class GitArchiveCopyTests(unittest.TestCase):
    def setUp(self):
        self.folder = self.enterContext(temporary_directory("v7-backup-copy-")).resolve()

    def test_copy_without_git_protects_only_its_root_and_never_runs_git(self):
        release = self.folder / "release"
        (release / "cong-no-web-handoff" / "tools").mkdir(parents=True)
        if any((folder / ".git").exists() for folder in release.parents):
            self.skipTest("temporary directory sits inside a git checkout")
        with patch.object(backup, "ROOT", release), \
                patch.object(backup.subprocess, "run", side_effect=AssertionError("git must not run")):
            self.assertEqual(backup.repository_roots(), {release})
            with self.assertRaisesRegex(backup.BackupError, "outside repository"):
                backup.prepare_output(release / "inside")
            self.assertEqual(backup.prepare_output(self.folder / "outside"), self.folder / "outside")

    def test_checkout_whose_worktree_list_fails_still_refuses(self):
        checkout = self.folder / "checkout"
        (checkout / ".git").mkdir(parents=True)
        failed = subprocess.CompletedProcess([], 128, b"", b"fatal: fake")
        with patch.object(backup, "ROOT", checkout), \
                patch.object(backup.subprocess, "run", return_value=failed), \
                self.assertRaisesRegex(backup.BackupError, "cannot determine"):
            backup.repository_roots()


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.root = self.enterContext(temporary_directory("v7-backup-daily-"))
        self.enterContext(patch.object(backup, "repository_roots", return_value={backup.ROOT}))
        self.enterContext(patch.object(backup, "Snapshot", FakeSnapshot))
        self.enterContext(patch.object(backup, "database_state", return_value=STATE))
        self.run_mock = self.enterContext(patch.object(backup.Pg, "run", side_effect=fake_run))

    def folder(self, name, complete=True, dump=b"old"):
        path = self.root / name
        path.mkdir()
        (path / backup.DUMP).write_bytes(dump)
        if complete:
            (path / backup.MANIFEST).write_text("{}", encoding="utf-8")
        return path

    def daily(self, keep, min_free_mb=0):
        output = io.StringIO()
        with redirect_stdout(output):
            out = backup.daily(self.root, keep, min_free_mb)
        return out, json.loads(output.getvalue().splitlines()[-1])

    def names(self):
        return sorted(entry.name for entry in self.root.iterdir())

    def test_verified_backup_then_prunes_only_old_dated_folders(self):
        for name in ("v7-20200101-024000", "v7-20200102-024000", "v7-20200104-024000"):
            self.folder(name)
        self.folder("v7-20200103-024000", complete=False)  # failed, older than oldest kept
        self.folder("v7-20200105-024000", complete=False)  # failed, recent: kept to inspect
        self.folder("v7-manual-before-deploy")
        (self.root / "v7-20200101-000000").write_text("not a folder", encoding="utf-8")
        out, summary = self.daily(keep=2)
        self.assertRegex(out.name, backup.STAMP)
        self.assertEqual(backup.verify(out)["customer_totals"], STATE["customer_totals"])
        self.assertEqual(self.names(), sorted([
            "v7-20200101-000000", "v7-20200104-024000", "v7-20200105-024000",
            "v7-manual-before-deploy", out.name]))
        self.assertEqual(summary["pruned"], ["v7-20200101-024000", "v7-20200102-024000",
                                             "v7-20200103-024000"])
        self.assertEqual((summary["ok"], summary["backup"], summary["kept"], summary["customers"]),
                         (True, out.name, 2, 2))
        self.assertNotIn("9007199254740993", json.dumps(summary))

    def test_backup_named_before_existing_ones_is_still_kept(self):
        self.folder("v7-29991231-235959")  # clock stepped back after this one
        out, summary = self.daily(keep=1)
        self.assertEqual(self.names(), sorted([out.name, "v7-29991231-235959"]))
        self.assertEqual((summary["kept"], summary["pruned"]), (2, []))

    def test_links_matching_the_pattern_are_not_followed_or_deleted(self):
        target = self.enterContext(temporary_directory("v7-backup-daily-target-"))
        (target / "precious").write_text("keep", encoding="utf-8")
        link = self.root / "v7-20200101-024000"
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"OS does not permit test symlink: {exc}")
        self.daily(keep=1)
        self.assertTrue(link.is_symlink())
        self.assertEqual((target / "precious").read_text(encoding="utf-8"), "keep")

    def test_low_disk_stops_before_any_write_or_prune(self):
        old = self.folder("v7-20200101-024000", dump=b"x" * 10)
        for free, min_free_mb in ((29, 0), (2**20 - 1, 1)):  # 3x last dump; minimum MB
            with self.subTest(free=free, min_free_mb=min_free_mb), \
                    patch.object(backup.shutil, "disk_usage", return_value=SimpleNamespace(free=free)), \
                    self.assertRaisesRegex(backup.BackupError, "low disk"):
                backup.daily(self.root, 1, min_free_mb)
            self.assertEqual(self.names(), [old.name])
        self.run_mock.assert_not_called()
        with patch.object(backup.shutil, "disk_usage", return_value=SimpleNamespace(free=30)):
            out, summary = self.daily(keep=1)
        self.assertEqual((self.names(), summary["pruned"]), ([out.name], [old.name]))

    def test_failed_backup_prunes_nothing(self):
        for name in ("v7-20200101-024000", "v7-20200102-024000"):
            self.folder(name)

        def fail_dump(program, *args, **kwargs):
            if args == ("--version",):
                return "pg_dump (PostgreSQL) 18.6\n"
            raise backup.BackupError("fake pg_dump failure")

        self.run_mock.side_effect = fail_dump
        with self.assertRaisesRegex(backup.BackupError, "fake pg_dump failure"):
            backup.daily(self.root, 1, 0)
        names = self.names()
        self.assertEqual(names[:2], ["v7-20200101-024000", "v7-20200102-024000"])
        self.assertEqual(len(names), 3)
        self.assertFalse((self.root / names[2] / backup.MANIFEST).exists())

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_backup_is_private_even_with_open_umask(self):
        previous = os.umask(0o022)
        try:
            out, _ = self.daily(keep=1)
            self.assertEqual(os.umask(0o022), 0o022)  # daily restored the caller's umask
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
        for name in (backup.DUMP, backup.MANIFEST):
            self.assertEqual(stat.S_IMODE((out / name).stat().st_mode), 0o600)

    def test_cli_rejects_bad_retention_and_missing_root(self):
        for args in (["--keep", "0"], ["--min-free-mb", "-1"]):
            with self.subTest(args=args), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as raised:
                backup.main(["daily", "--root", str(self.root), *args])
            self.assertEqual(raised.exception.code, 2)
        with redirect_stderr(io.StringIO()) as error:
            self.assertEqual(backup.main(["daily", "--root", str(self.root / "missing")]), 2)
        self.assertIn("existing directory", error.getvalue())
        self.run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
