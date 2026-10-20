#!/usr/bin/env python3
"""V7 backup/restore via psql, pg_dump and pg_restore on PATH (stdlib only).

Connection uses libpq environment variables / pgpass, never CLI passwords.
Backup keeps one exported REPEATABLE READ snapshot alive for dump + manifest.
Restore preserves owners/ACLs: provision target DB and referenced roles first;
this tool does not create roles or grant permissions.
Failed backups retain partial files without MANIFEST.json; do not reuse them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DUMP = "sokhach.dump"
MANIFEST = "MANIFEST.json"
VN = timezone(timedelta(hours=7))
VND = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")


class BackupError(RuntimeError):
    pass


def quote_name(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


class Pg:
    """prefix is for the disposable Docker harness; CLI always uses libpq."""

    def __init__(self, database=None, *, prefix=(), env=None):
        self.database = database
        self.prefix = list(prefix)
        self.env = dict(os.environ if env is None else env)
        self.env.setdefault("PGCONNECT_TIMEOUT", "15")
        self.env["PGCLIENTENCODING"] = "UTF8"

    def at(self, database):
        return Pg(database, prefix=self.prefix, env=self.env)

    def args(self, program, *args):
        database = ["--dbname", self.database] if self.database is not None else []
        return [*self.prefix, program, *args, *database]

    def run(self, program, *args, text=None, stdin=None, stdout=None):
        try:
            result = subprocess.run(
                self.args(program, *args), env=self.env,
                input=text.encode("utf-8") if text is not None else None,
                stdin=stdin, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=300, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackupError(f"{program} unavailable/timed out") from exc
        if result.returncode:
            raise BackupError(f"{program} failed ({result.returncode}): "
                              + result.stderr.decode("utf-8", errors="replace")[-2000:].strip())
        return result.stdout.decode("utf-8") if result.stdout is not None else ""

    def sql(self, sql):
        return self.run("psql", "-X", "-qAt", "-w", "-v", "ON_ERROR_STOP=1", text=sql)


class Snapshot:
    """One read-only psql session; line protocol carries one JSON result/query."""

    def __init__(self, pg):
        self.pg = pg

    def __enter__(self):
        self.errors = tempfile.TemporaryFile()
        self.lines = queue.Queue()
        try:
            self.process = subprocess.Popen(
                self.pg.args("psql", "-X", "-qAt", "-w", "-v", "ON_ERROR_STOP=1"),
                env=self.pg.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self.errors, text=True, encoding="utf-8", bufsize=1)
        except OSError as exc:
            self.errors.close()
            raise BackupError("psql unavailable") from exc

        def read():
            try:
                for line in self.process.stdout:
                    self.lines.put(line)
            finally:
                self.lines.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            self.id = self.query("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY; "
                                 "SET LOCAL sokhach.actor='v7_backup'; "
                                 "SELECT to_json(pg_export_snapshot());")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def query(self, sql):
        try:
            self.process.stdin.write(sql + "\n")
            self.process.stdin.flush()
            line = self.lines.get(timeout=60)
        except (OSError, queue.Empty) as exc:
            raise BackupError("snapshot query failed/timed out") from exc
        if line is None:
            self.errors.seek(0)
            detail = self.errors.read().decode("utf-8", errors="replace")[-2000:]
            raise BackupError("snapshot session failed: " + detail.strip())
        try:
            return json.loads(line)
        except ValueError as exc:
            raise BackupError("unexpected snapshot response") from exc

    def __exit__(self, *exc):
        # Closing stdin rolls back the read-only transaction and releases snapshot.
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.reader.join(timeout=10)
        self.process.stdout.close()
        self.errors.close()


def database_state(snapshot):
    tables = snapshot.query("SELECT coalesce(json_agg(c.relname ORDER BY c.relname),'[]'::json) "
                            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                            "WHERE n.nspname='sokhach' AND c.relkind IN ('r','p');")
    if "customer" not in tables:
        raise BackupError("sokhach.customer missing")
    counts = {name: snapshot.query(f"SELECT to_json(count(*)) FROM sokhach.{quote_name(name)};")
              for name in tables}
    totals = snapshot.query(
        "SELECT coalesce(json_object_agg(c.id::text, "
        "sokhach.get_ledger(c.id)->'total_outstanding_vnd'),'{}'::json) "
        "FROM sokhach.customer c;")
    return {"table_row_counts": counts, "customer_totals": totals}


def repository_roots():
    """Reject primary repo and every registered worktree, including linked ones."""
    try:
        result = subprocess.run(["git", "-C", str(ROOT), "worktree", "list", "--porcelain", "-z"],
                                capture_output=True, timeout=15, check=False)
        if result.returncode:
            raise BackupError("cannot determine repository/worktree roots")
        roots = [Path(os.fsdecode(item[len(b'worktree '):])).resolve()
                 for item in result.stdout.split(b"\0") if item.startswith(b"worktree ")]
        if not roots:
            raise BackupError("no repository/worktree roots found")
        return {ROOT, *roots}
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BackupError("git required to protect repository from backup data") from exc


def prepare_output(path):
    path = Path(path).expanduser().resolve()
    if any(path.is_relative_to(root) for root in repository_roots()):
        raise BackupError("backup destination must be outside repository and worktrees")
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise BackupError("backup destination must be a new or empty directory")
    else:
        path.mkdir(parents=True)
    return path


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_state(state):
    counts, totals = state.get("table_row_counts"), state.get("customer_totals")
    if not isinstance(counts, dict) or "customer" not in counts or any(
            not isinstance(k, str) or not k or type(v) is not int or v < 0
            for k, v in counts.items()):
        raise BackupError("invalid manifest table_row_counts")
    if not isinstance(totals, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r"[1-9][0-9]*", k)
            or (v is not None and (not isinstance(v, str) or not VND.fullmatch(v)
                                  or not -(2**63) <= int(v) < 2**63))
            for k, v in totals.items()):
        raise BackupError("invalid manifest customer_totals: VND must be integer text or null")
    if len(totals) != counts["customer"]:
        raise BackupError("manifest customer count does not match customer_totals")


def validate_manifest(value):
    keys = {"format_version", "schema", "dump_file", "dump_sha256", "pg_dump_version",
            "server_version", "created_at_vn", "table_row_counts", "customer_totals"}
    if not isinstance(value, dict) or set(value) != keys:
        raise BackupError("invalid manifest fields")
    if type(value["format_version"]) is not int or value["format_version"] != 1:
        raise BackupError("unsupported manifest format_version")
    if value["schema"] != "sokhach" or value["dump_file"] != DUMP:
        raise BackupError("invalid manifest schema/dump_file")
    if not isinstance(value["dump_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["dump_sha256"]):
        raise BackupError("invalid manifest dump_sha256")
    for key in ("pg_dump_version", "server_version"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise BackupError(f"invalid manifest {key}")
    try:
        stamp = datetime.fromisoformat(value["created_at_vn"])
        if stamp.utcoffset() != timedelta(hours=7):
            raise ValueError("expected Vietnam UTC+07:00")
    except (ValueError, TypeError) as exc:
        raise BackupError("invalid manifest created_at_vn (requires UTC+07:00)") from exc
    validate_state(value)
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError(f"duplicate manifest key: {key}")
        result[key] = value
    return result


def verify(folder):
    folder = Path(folder).expanduser().resolve()
    try:
        manifest = validate_manifest(json.loads((folder / MANIFEST).read_text(encoding="utf-8"),
                                                 object_pairs_hook=_unique_object))
        dump = folder / DUMP
        if dump.is_symlink() or not dump.resolve().is_relative_to(folder):
            raise BackupError("dump must stay inside backup directory")
        actual = sha256(dump)
    except (OSError, ValueError) as exc:
        raise BackupError("cannot read backup manifest/dump: " + str(exc)) from exc
    if actual != manifest["dump_sha256"]:
        raise BackupError(f"SHA-256 MISMATCH expected={manifest['dump_sha256']} actual={actual}")
    return manifest


def compare(expected, actual):
    """Absent customer is different from an existing customer with NULL total."""
    differences = []
    for group in ("table_row_counts", "customer_totals"):
        before, after = expected[group], actual[group]
        for key in sorted(before.keys() | after.keys()):
            if key not in before or key not in after or before[key] != after[key]:
                old = repr(before[key]) if key in before else "MISSING"
                new = repr(after[key]) if key in after else "MISSING"
                differences.append(f"{group}.{key}: expected={old} actual={new}")
    return differences


def report(expected, actual):
    differences = compare(expected, actual)
    print("MISMATCH" if differences else "MATCH")
    if differences:
        for detail in differences:
            print(detail)
    else:
        print(f"{len(actual['table_row_counts'])} tables; {len(actual['customer_totals'])} customers")
        for group in ("table_row_counts", "customer_totals"):
            for key, value in sorted(actual[group].items()):
                print(f"{group}.{key}={value!r}")
    return int(bool(differences))


def backup(out, pg=None):
    out = prepare_output(out)
    pg = pg or Pg()
    # --version must not inherit --dbname; pg_dump rejects that combination.
    version = Pg(prefix=pg.prefix, env=pg.env).run("pg_dump", "--version").strip()
    with Snapshot(pg) as snapshot:
        state = database_state(snapshot)
        validate_state(state)
        server = snapshot.query("SELECT to_json(current_setting('server_version'));")
        with (out / DUMP).open("xb") as stream:
            pg.run("pg_dump", "-w", "-Fc", "--schema=sokhach", "--snapshot", snapshot.id, stdout=stream)
    manifest = {"format_version": 1, "schema": "sokhach", "dump_file": DUMP,
                "dump_sha256": sha256(out / DUMP), "pg_dump_version": version,
                "server_version": server, "created_at_vn": datetime.now(VN).isoformat(), **state}
    validate_manifest(manifest)
    with (out / MANIFEST).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"BACKUP {out}")
    return manifest


def restore(folder, target_db, pg=None):
    # libpq accepts connstrings/URIs as dbname: reject them rather than bypass env.
    if not isinstance(target_db, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", target_db):
        raise BackupError("target-db must be a plain database name (1..63 ASCII characters)")
    folder = Path(folder).expanduser().resolve()
    expected = verify(folder)  # Hash/manifest verified before any DB connection.
    pg = pg or Pg()
    target = pg.at(target_db)
    present = target.sql("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='sokhach');").strip()
    if present != "f":
        raise BackupError("target already has sokhach, or schema check failed; restore refused")
    # CREATE SCHEMA also detects a concurrent restore; failure rolls back everything.
    with (folder / DUMP).open("rb") as stream:
        target.run("pg_restore", "-w", "--exit-on-error", "--single-transaction", stdin=stream)
    with Snapshot(target) as snapshot:
        actual = database_state(snapshot)
    return report(expected, actual)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup").add_argument("--out", required=True, type=Path)
    command = commands.add_parser("restore")
    command.add_argument("--from", dest="folder", required=True, type=Path)
    command.add_argument("--target-db", required=True)
    commands.add_parser("verify").add_argument("--from", dest="folder", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            backup(args.out)
        elif args.command == "verify":
            verify(args.folder)
            print("MATCH SHA-256 and manifest structure (offline)")
        else:
            return restore(args.folder, args.target_db)
        return 0
    except (BackupError, OSError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
