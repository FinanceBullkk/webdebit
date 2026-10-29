"""Pure unittest checks plus optional real PostgreSQL 18 / Docker rehearsal."""
from __future__ import annotations

import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

try:
    from . import test_pg_v7_backend as harness
    from . import v7_backup as backup
except ImportError:  # python tools/test_v7_backup.py
    import test_pg_v7_backend as harness
    import v7_backup as backup


def manifest_for(dump):
    return {"format_version": 1, "schema": "sokhach", "dump_file": backup.DUMP,
            "dump_sha256": backup.sha256(dump), "pg_dump_version": "pg_dump (PostgreSQL) 18.6",
            "server_version": "18.6", "created_at_vn": "2026-10-21T10:00:00+07:00",
            "table_row_counts": {"customer": 3, "trip": 2},
            "customer_totals": {"1": "9007199254740993", "2": None, "3": "-25"}}


@contextmanager
def temporary_directory(prefix):
    # Python 3.13 mkdir(mode=0o700), used by TemporaryDirectory, excludes the
    # Windows sandbox token. Default inherited ACL works for fake test rows.
    folder = Path(tempfile.gettempdir()) / (prefix + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        shutil.rmtree(folder)


class BackupUnitTests(unittest.TestCase):
    def setUp(self):
        self.folder = self.enterContext(temporary_directory("v7-backup-unit-"))
        self.dump = self.folder / backup.DUMP
        self.dump.write_bytes(b"PGDMP fake bytes\x00\xff\n")
        self.manifest = manifest_for(self.dump)
        self.write_manifest()

    def write_manifest(self):
        (self.folder / backup.MANIFEST).write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_verify_offline_preserves_large_signed_and_null_money(self):
        with patch.object(backup.Pg, "run", side_effect=AssertionError("DB access forbidden")):
            actual = backup.verify(self.folder)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(backup.main(["verify", "--from", str(self.folder)]), 0)
        self.assertEqual(actual["customer_totals"], self.manifest["customer_totals"])

    def test_hash_mismatch_stops_before_database_access(self):
        self.dump.write_bytes(b"corrupt")
        with patch.object(backup.Pg, "sql", side_effect=AssertionError("DB access forbidden")),                 self.assertRaisesRegex(backup.BackupError, "SHA-256 MISMATCH"):
            backup.restore(self.folder, "fake_target")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(backup.main(["verify", "--from", str(self.folder)]), 2)

    def test_manifest_rejects_invalid_missing_and_unsafe_fields(self):
        invalid = [
            ("format_version", True), ("format_version", 2), ("schema", "ledger"),
            ("dump_file", "../outside"), ("dump_file", "C:\\outside.dump"),
            ("dump_sha256", "f" * 63), ("created_at_vn", "2026-10-21T10:00:00"),
            ("created_at_vn", "2026-10-21T10:00:00+00:00"), ("pg_dump_version", ""),
            ("table_row_counts", {"customer": True}), ("table_row_counts", {"customer": -1}),
            ("customer_totals", {"1": 9007199254740993}),
            ("customer_totals", {"1": 1.5}), ("customer_totals", {"1": "1.5"}),
            ("customer_totals", {"1": "9223372036854775808"}),
            ("customer_totals", {"1": "-0"}), ("customer_totals", {"1": "00"}),
            ("customer_totals", {"01": "1"}), ("customer_totals", {}),
        ]
        for key, value in invalid:
            with self.subTest(key=key, value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest[key] = value
                with self.assertRaises(backup.BackupError):
                    backup.validate_manifest(manifest)
        for key in self.manifest:
            with self.subTest(missing=key):
                manifest = dict(self.manifest)
                del manifest[key]
                with self.assertRaises(backup.BackupError):
                    backup.validate_manifest(manifest)

    def test_bad_json_duplicate_keys_and_missing_files(self):
        path = self.folder / backup.MANIFEST
        for text in ('{', '[]', '{"schema":"sokhach","schema":"ledger"}'):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(backup.BackupError):
                    backup.verify(self.folder)
        self.write_manifest()
        self.dump.unlink()
        with self.assertRaises(backup.BackupError):
            backup.verify(self.folder)
        path.unlink()
        with self.assertRaises(backup.BackupError):
            backup.verify(self.folder)

    def test_destination_new_empty_nonempty_and_file(self):
        roots = {backup.ROOT}
        with patch.object(backup, "repository_roots", return_value=roots):
            fresh = self.folder / "fresh"
            self.assertEqual(backup.prepare_output(fresh), fresh.resolve())
            self.assertEqual(backup.prepare_output(fresh), fresh.resolve())
            (fresh / "owned").write_text("keep", encoding="utf-8")
            with self.assertRaises(backup.BackupError):
                backup.prepare_output(fresh)
            with self.assertRaises(backup.BackupError):
                backup.prepare_output(self.dump)
            self.assertEqual((fresh / "owned").read_text(encoding="utf-8"), "keep")

    def test_destination_rejects_primary_repo_and_all_worktrees(self):
        roots = backup.repository_roots()
        self.assertIn(backup.ROOT, roots)
        for root in roots:
            with self.subTest(root=root), self.assertRaisesRegex(backup.BackupError, "outside repository"):
                backup.prepare_output(root / "must-not-create-backup")

    def test_destination_resolves_links(self):
        link = self.folder / "linked-worktree"
        try:
            link.symlink_to(backup.ROOT, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"OS does not permit test symlink: {exc}")
        with self.assertRaisesRegex(backup.BackupError, "outside repository"):
            backup.prepare_output(link / "must-not-create-backup")

    def test_compare_exact_counts_totals_and_missing_null_customer(self):
        self.assertEqual(backup.compare(self.manifest, copy.deepcopy(self.manifest)), [])
        changed = copy.deepcopy(self.manifest)
        changed["table_row_counts"]["trip"] += 1
        changed["customer_totals"]["1"] = "9007199254740994"
        changed["customer_totals"]["2"] = "0"
        changed["customer_totals"]["4"] = None
        del changed["customer_totals"]["3"]
        differences = backup.compare(self.manifest, changed)
        self.assertEqual(len(differences), 5)
        self.assertIn("expected=None actual='0'", "\n".join(differences))
        self.assertIn("expected=MISSING actual=None", "\n".join(differences))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(backup.report(self.manifest, changed), 1)
        self.assertTrue(output.getvalue().startswith("MISMATCH\n"))
        with redirect_stdout(output):
            self.assertEqual(backup.report(self.manifest, self.manifest), 0)
        self.assertIn("MATCH\n", output.getvalue())

    def test_restore_refuses_existing_schema_and_connstring(self):
        pg = backup.Pg()
        with patch.object(backup.Pg, "sql", return_value="t\n"), patch.object(backup.Pg, "run") as run:
            with self.assertRaisesRegex(backup.BackupError, "restore refused"):
                backup.restore(self.folder, "fake_target", pg)
            run.assert_not_called()
        for name in ("postgresql://localhost/db", "dbname=x password=y", "x'", "-x", "a" * 64):
            with self.subTest(name=name), self.assertRaisesRegex(backup.BackupError, "plain database name"):
                backup.restore(self.folder, name)

    def test_restore_cli_match_and_mismatch_exit_codes(self):
        class FakeSnapshot:
            def __init__(self, pg):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                pass

        for mismatch in (False, True):
            actual = copy.deepcopy(self.manifest)
            if mismatch:
                actual["customer_totals"]["1"] = "42"
            with self.subTest(mismatch=mismatch), patch.object(backup.Pg, "sql", return_value="f\n"), \
                    patch.object(backup.Pg, "run") as run, patch.object(backup, "Snapshot", FakeSnapshot), \
                    patch.object(backup, "database_state", return_value=actual):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = backup.main(["restore", "--from", str(self.folder), "--target-db", "fake_target"])
                self.assertEqual(code, int(mismatch))
                self.assertEqual(output.getvalue().splitlines()[0], "MISMATCH" if mismatch else "MATCH")
                args = run.call_args.args
                self.assertIn("--single-transaction", args)
                self.assertNotIn("--clean", args)

    def test_backup_uses_exported_snapshot_and_hashes_written_bytes(self):
        state = {key: self.manifest[key] for key in ("table_row_counts", "customer_totals")}

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

        def run(program, *args, **kwargs):
            if args == ("--version",):
                return "pg_dump (PostgreSQL) 18.6\n"
            self.assertEqual(program, "pg_dump")
            self.assertIn("-Fc", args)
            self.assertIn("--schema=sokhach", args)
            self.assertIn("--snapshot", args)
            self.assertIn("FAKE-SNAPSHOT", args)
            kwargs["stdout"].write(b"fake exported snapshot dump")

        out = self.folder / "backup"
        with patch.object(backup, "Snapshot", FakeSnapshot), patch.object(backup, "database_state", return_value=state), \
                patch.object(backup.Pg, "run", side_effect=run), redirect_stdout(io.StringIO()):
            created = backup.backup(out)
        self.assertEqual(backup.verify(out), created)
        self.assertEqual(created["customer_totals"]["1"], "9007199254740993")
        failed = self.folder / "failed"

        def fail_dump(program, *args, **kwargs):
            version = run(program, *args, **kwargs)
            if "--version" in args:
                return version
            raise backup.BackupError("fake pg_dump failure")

        with patch.object(backup, "Snapshot", FakeSnapshot), patch.object(backup, "database_state", return_value=state), \
                patch.object(backup.Pg, "run", side_effect=fail_dump),                 self.assertRaisesRegex(backup.BackupError, "fake pg_dump failure"):
            backup.backup(failed)
        self.assertFalse((failed / backup.MANIFEST).exists())
        self.assertTrue((failed / backup.DUMP).exists())

    def test_snapshot_pipe_protocol_and_error_cleanup_without_database(self):
        # Small child process tests pipe framing/EOF cleanup, never contacts DB.
        code = ("import sys,json\n"
                "for line in sys.stdin:\n"
                " if 'pg_export_snapshot' in line: print(json.dumps('FAKE-SNAPSHOT'),flush=True)\n"
                " elif 'broken' in line: print('fake SQL error',file=sys.stderr);sys.exit(1)\n"
                " else: print(json.dumps({'total':None}),flush=True)\n")
        pg = backup.Pg(prefix=[sys.executable, "-u", "-c", code])
        with backup.Snapshot(pg) as snapshot:
            self.assertEqual(snapshot.id, "FAKE-SNAPSHOT")
            self.assertEqual(snapshot.query("SELECT fake;"), {"total": None})
        self.assertEqual(snapshot.process.returncode, 0)
        with self.assertRaisesRegex(backup.BackupError, "fake SQL error"), backup.Snapshot(pg) as failed:
            failed.query("SELECT broken;")
        self.assertEqual(failed.process.returncode, 1)


class DockerEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("docker"):
            raise unittest.SkipTest("Docker CLI unavailable; PostgreSQL 18 end-to-end not run")
        try:
            result = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                                    capture_output=True, timeout=20, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise unittest.SkipTest(f"Docker unavailable: {exc}; PostgreSQL 18 end-to-end not run") from exc
        if result.returncode:
            reason = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
            raise unittest.SkipTest(f"Docker unavailable: {reason}; PostgreSQL 18 end-to-end not run")

    def test_backup_restore_and_new_manifest_detects_changed_source(self):
        run_id = uuid.uuid4().hex
        name = volume = "webdebit-v7-backup-" + run_id
        volume_created = False
        container_id = None
        try:
            harness.run(["docker", "volume", "create", "--label", f"{harness.LABEL_TEST}={harness.LABEL_VALUE}",
                         "--label", f"{harness.LABEL_RUN}={run_id}", volume])
            volume_created = True
            harness.inspect_volume(volume, run_id)
            harness.run(["docker", "run", "--detach", "--name", name,
                         "--label", f"{harness.LABEL_TEST}={harness.LABEL_VALUE}",
                         "--label", f"{harness.LABEL_RUN}={run_id}", "--network", "none",
                         "--volume", f"{volume}:/var/lib/postgresql", "--env",
                         "POSTGRES_HOST_AUTH_METHOD=trust", harness.IMAGE], timeout=240)
            container_id = harness.inspect_owned(name, volume, run_id)
            self.assertIsNotNone(container_id)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                logs = harness.run(["docker", "logs", container_id], check=False, timeout=10)
                if "PostgreSQL init process complete; ready for start up." in logs.stdout + logs.stderr:
                    break
                time.sleep(0.25)
            else:
                self.fail("PostgreSQL init marker timed out")
            prefix = ["docker", "exec", "-i", "--env", "PGUSER=postgres", "--env", "PGCLIENTENCODING=UTF8",
                      "--env", f"PGAPPNAME=codex_v7_backup_{run_id}", container_id]
            # Host libpq settings must never leak into a test connection.
            env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
            pg = backup.Pg(harness.DATABASE, prefix=prefix, env=env)
            for db in (harness.DATABASE, "v7_restore", "v7_mismatch"):
                pg.at("postgres").sql(f"CREATE DATABASE {db};")
            pg.at("v7_restore").sql("CREATE SCHEMA unrelated; CREATE TABLE unrelated.keep(value integer); "
                                    "INSERT INTO unrelated.keep VALUES(42);")
            pg.sql(harness.SCHEMA.read_text(encoding="utf-8"))
            pg.sql(harness.FUNCTIONS.read_text(encoding="utf-8"))
            fixture = harness.Pg(name, run_id)
            customer = harness.new_book(fixture, ("2026-01-01", 9007199254740993))
            negative = harness.new_book(fixture, ("2026-01-01", -25))
            no_baseline = int(fixture.value("INSERT INTO sokhach.customer(name) VALUES ('FAKE NO BASELINE') RETURNING id"))
            harness.call(fixture, "set_month_lock", customer, 0, "fake-open", "2026-01-01", "false")
            trips = json.dumps([json.loads(harness.trip_json())[0],
                                json.loads(harness.trip_json(None, container="FAKE-PENDING"))[0]])
            pasted = harness.call(fixture, "paste_trips", customer, 1, "fake-paste", "2026-01-01", trips)
            harness.call(fixture, "record_receipt", customer, 2, "fake-receipt", "2026-01-04", "THU TIỀN", 50)
            with temporary_directory("v7-backup-e2e-") as raw:
                first_dir, second_dir = Path(raw) / "first", Path(raw) / "second"
                with redirect_stdout(io.StringIO()):
                    first = backup.backup(first_dir, pg)
                self.assertEqual(backup.verify(first_dir), first)
                self.assertEqual(first["customer_totals"][str(customer)], "9007199254741043")
                self.assertEqual(first["customer_totals"][str(negative)], "-25")
                self.assertIsNone(first["customer_totals"][str(no_baseline)])
                daily_root = Path(raw) / "daily"
                daily_root.mkdir()
                with redirect_stdout(io.StringIO()):
                    made = backup.daily(daily_root, 1, 0, pg)
                self.assertEqual(backup.verify(made)["customer_totals"], first["customer_totals"])
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(backup.restore(first_dir, "v7_restore", pg), 0)
                self.assertTrue(output.getvalue().startswith("MATCH\n"))
                target = pg.at("v7_restore")
                self.assertEqual(target.sql("SELECT value FROM unrelated.keep;").strip(), "42")
                self.assertEqual(target.sql("SELECT other_fee_vnd IS NULL FROM sokhach.trip_price_rev ORDER BY id LIMIT 1;").strip(), "t")
                # Same exported snapshot remains stable across a concurrent live write.
                with backup.Snapshot(pg) as held:
                    before = backup.database_state(held)
                    harness.call(fixture, "edit_trip_price", customer, 3, "fake-change",
                                 pasted["trip_ids"][0], 101, None)
                    self.assertEqual(backup.database_state(held), before)
                with redirect_stdout(io.StringIO()):
                    second = backup.backup(second_dir, pg)
                self.assertEqual(second["table_row_counts"]["trip_price_rev"], first["table_row_counts"]["trip_price_rev"] + 1)
                self.assertEqual(second["customer_totals"][str(customer)], "9007199254741044")
                with backup.Snapshot(target) as restored:
                    output = io.StringIO()
                    with redirect_stdout(output):
                        self.assertEqual(backup.report(second, backup.database_state(restored)), 1)
                    self.assertTrue(output.getvalue().startswith("MISMATCH\n"))
                # Old dump is intact, but newly recorded source manifest differs.
                # Build a valid hash-bound package to exercise restore's mismatch exit.
                package = Path(raw) / "mismatch"
                package.mkdir()
                shutil.copyfile(first_dir / backup.DUMP, package / backup.DUMP)
                mismatch = {**second, "dump_sha256": backup.sha256(package / backup.DUMP)}
                (package / backup.MANIFEST).write_text(json.dumps(mismatch), encoding="utf-8")
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(backup.restore(package, "v7_mismatch", pg), 1)
                self.assertTrue(output.getvalue().startswith("MISMATCH\n"))
                self.assertIn(f"customer_totals.{customer}", output.getvalue())
                with self.assertRaisesRegex(backup.BackupError, "restore refused"):
                    backup.restore(first_dir, "v7_restore", pg)
        finally:
            owned = harness.inspect_owned(name, volume, run_id, container_id) if volume_created else None
            if owned:
                harness.run(["docker", "rm", "--force", owned])
            if volume_created:
                harness.inspect_volume(volume, run_id)
                harness.run(["docker", "volume", "rm", volume])
                remaining = harness.run(["docker", "volume", "ls", "--quiet", "--filter", f"name=^{volume}$"]).stdout.strip()
                self.assertEqual(remaining, "", "owned volume remains after cleanup")


if __name__ == "__main__":
    unittest.main()
