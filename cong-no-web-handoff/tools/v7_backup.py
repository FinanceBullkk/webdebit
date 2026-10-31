#!/usr/bin/env python3
"""V7 backup/restore via psql, pg_dump and pg_restore on PATH (stdlib only).

Connection uses libpq environment variables / pgpass, never CLI passwords.
Backup keeps one exported REPEATABLE READ snapshot alive for dump + manifest.
Restore preserves owners/ACLs: provision target DB and referenced roles first;
this tool does not create roles or grant permissions.
Failed backups retain partial files without MANIFEST.json; do not reuse them.
`daily` is the timer entry: dated folder under one root, disk check, retention
(the hourly timer runs it too, on its own root).
`offsite` age-encrypts the newest daily backup into an outbox that an off-host
PC pulls (v7_offsite_pull.py); decrypting needs the identity kept on that PC.
`config` (root) seals PostgreSQL globals and hao config files into the same outbox.
"""
from __future__ import annotations

import argparse
import contextlib
import glob
import hashlib
import io
import json
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DUMP = "sokhach.dump"
MANIFEST = "MANIFEST.json"
CONFIG_MANIFEST = "CONFIG.json"
VN = timezone(timedelta(hours=7))
VND = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")
STAMP = re.compile(r"v7-[0-9]{8}-[0-9]{6}\Z")
SEALED = re.compile(r"v7-[0-9]{8}-[0-9]{6}\.tar\.age\Z")
CONFIG_TOP = re.compile(r"v7-config-[0-9]{8}-[0-9]{6}\Z")
CONFIG_SEALED = re.compile(r"v7-config-[0-9]{8}-[0-9]{6}\.tar\.age\Z")
DB_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")
AGE = ["age"]  # on PATH (/usr/bin/age on hao); tests swap in a fake
# What a rebuild of hao needs besides the dump. Globs only: the values (env files,
# service-account keys) exist only inside the age archive. No match is reported.
CONFIG_PATHS = (
    "/etc/systemd/system/v7-*", "/etc/systemd/system/webdebit-*",
    "/etc/systemd/system/*.wants/v7-*", "/etc/systemd/system/*.wants/webdebit-*",
    "/etc/webdebit", "/etc/webdebit-backup", "/srv/v7/customer-name-mapping.json",
    "/etc/ssh/sshd_config", "/etc/ssh/sshd_config.d", "/etc/sudoers", "/etc/sudoers.d",
    "/etc/postgresql/18/main", "/etc/ufw/user.rules", "/etc/ufw/user6.rules",
)
# (member, argv, OS user): stdout kept in memory. Root drops to postgres for peer auth.
CONFIG_COMMANDS = (
    ("globals.sql", ("pg_dumpall", "--globals-only", "--no-password"), "postgres"),
    ("tailscale-serve.json", ("tailscale", "serve", "status", "--json"), None),
)


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
    """Reject primary repo and every registered worktree, including linked ones.

    A git-archive copy (no .git in ROOT or any parent, like the pinned copy the
    daily timer runs on hao) has no worktrees: only ROOT itself is protected.
    """
    if not any((folder / ".git").exists() for folder in (ROOT, *ROOT.parents)):
        return {ROOT}
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


def stamped(root):
    """Dated folders directly under root, oldest first; links and files ignored."""
    return sorted((entry for entry in root.iterdir() if STAMP.fullmatch(entry.name)
                   and entry.is_dir() and not entry.is_symlink()), key=lambda entry: entry.name)


def daily(root, keep, min_free_mb, pg=None):
    """Timer entry: new dated backup under an existing root, verify, then prune.

    Stops before writing when free space is under min_free_mb or 3x the last
    dump. Prunes only after a verified backup, and only dated folders: complete
    ones beyond the newest `keep`, failed ones older than the oldest kept.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise BackupError("daily root must be an existing directory")
    complete = [entry for entry in stamped(root) if (entry / MANIFEST).is_file()]
    last = (complete[-1] / DUMP).stat().st_size if complete and (complete[-1] / DUMP).is_file() else 0
    need, free = max(min_free_mb * 2**20, 3 * last), shutil.disk_usage(root).free
    if free < need:
        raise BackupError(f"low disk: free={free} need={need} bytes; backup not started")
    umask = os.umask(0o077)  # folder 700, files 600 even if the unit forgets UMask.
    try:
        out = root / datetime.now(VN).strftime("v7-%Y%m%d-%H%M%S")
        manifest = backup(out, pg)
        verify(out)
    finally:
        os.umask(umask)
    complete = [entry for entry in stamped(root) if (entry / MANIFEST).is_file()]
    kept = {out, *complete[-keep:]}  # A clock step back never prunes today's backup.
    oldest = min(entry.name for entry in kept)
    pruned = [entry.name for entry in stamped(root) if entry not in kept
              and ((entry / MANIFEST).is_file() or entry.name < oldest)]
    for name in pruned:
        shutil.rmtree(root / name)
    print(json.dumps({"ok": True, "backup": out.name, "dump_bytes": (out / DUMP).stat().st_size,
                      "tables": len(manifest["table_row_counts"]),
                      "customers": len(manifest["customer_totals"]), "kept": len(kept),
                      "pruned": pruned, "free_bytes": shutil.disk_usage(root).free}))
    return out


def encrypt(stream, recipients, add):
    """`add(tar)` writes members into a tar piped straight into age: no plaintext copy on disk.

    Any failure kills age, so a truncated tar is never left looking complete.
    """
    with tempfile.TemporaryFile() as errors:
        try:
            process = subprocess.Popen([*AGE, "--encrypt", "--recipients-file", str(recipients)],
                                       stdin=subprocess.PIPE, stdout=stream, stderr=errors)
        except OSError as exc:
            raise BackupError("age unavailable") from exc
        failure = None
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|", format=tarfile.PAX_FORMAT) as archive:
                add(archive)
            process.stdin.close()
            process.wait(timeout=300)
        except (OSError, BackupError, tarfile.TarError, subprocess.TimeoutExpired) as exc:
            failure = exc
            process.kill()
            process.wait()
            with contextlib.suppress(OSError):
                process.stdin.close()
        if failure or process.returncode:
            errors.seek(0)
            detail = errors.read().decode("utf-8", errors="replace")[-2000:].strip()
            raise BackupError(f"age/tar failed ({process.returncode}): {detail or failure}") from failure


def seal(source, stream, recipients):
    """Tar `<name>/` (MANIFEST.json + dump) of one daily backup into age."""
    def add(archive):
        folder = tarfile.TarInfo(source.name)
        folder.type, folder.mode, folder.mtime = tarfile.DIRTYPE, 0o700, int(source.stat().st_mtime)
        archive.addfile(folder)
        for name in (MANIFEST, DUMP):
            info = archive.gettarinfo(source / name, f"{source.name}/{name}")
            if not info.isreg():
                raise BackupError(f"{name} must be a regular file")
            info.mode, info.uid, info.gid, info.uname, info.gname = 0o600, 0, 0, "", ""
            with (source / name).open("rb") as data:
                archive.addfile(info, data)

    encrypt(stream, recipients, add)


def publish(outbox, name, write):
    """`write(stream)` fills `<name>`, then `<name>.sha256` (sha256sum format) is written.

    Both go through `.partial` and the archive is renamed first, so a reader
    never sees a checksum without its archive; a failure leaves neither.
    """
    archive, checksum = outbox / name, outbox / f"{name}.sha256"
    parts = (outbox / f"{archive.name}.partial", outbox / f"{checksum.name}.partial")
    try:
        for part in parts:
            part.unlink(missing_ok=True)
        with parts[0].open("xb") as stream:
            write(stream)
        parts[1].write_bytes(f"{sha256(parts[0])}  {archive.name}\n".encode("ascii"))
        os.replace(parts[0], archive)
        os.replace(parts[1], checksum)
    finally:
        for part in parts:
            part.unlink(missing_ok=True)
    return archive


def sealed(outbox, pattern=SEALED):
    """Archives matching `pattern` directly under outbox, oldest first; links ignored."""
    return sorted(entry.name for entry in outbox.iterdir() if pattern.fullmatch(entry.name)
                  and entry.is_file() and not entry.is_symlink())


def prune_sealed(outbox, pattern, keep, current):
    """Keep the newest `keep` of one family plus `current` (a clock step back never prunes it)."""
    names = sealed(outbox, pattern)
    kept = {current, *names[-keep:]}
    pruned = [name for name in names if name not in kept]
    for name in pruned:
        (outbox / f"{name}.sha256").unlink(missing_ok=True)
        (outbox / name).unlink()
    return kept, pruned


def offsite(root, outbox, recipients, keep):
    """Timer entry after `daily`: age-encrypt the newest complete backup for an off-host pull.

    Verifies the source hash, then writes `<name>.tar.age` before its
    `.sha256` (sha256sum format), so a reader never sees a checksum without its
    archive; an intact pair is not sealed again. Prunes only after success:
    archives beyond the newest `keep`, checksum first. Nothing here decrypts.
    """
    root, outbox = (Path(path).expanduser().resolve() for path in (root, outbox))
    if not root.is_dir() or not outbox.is_dir():
        raise BackupError("offsite root and outbox must be existing directories")
    if outbox.is_relative_to(root) or root.is_relative_to(outbox):
        raise BackupError("offsite outbox and daily root must not contain each other")
    if not Path(recipients).is_file():
        raise BackupError("offsite recipients file missing")
    complete = [entry for entry in stamped(root) if (entry / MANIFEST).is_file()]
    if not complete:
        raise BackupError("no complete backup to seal")
    source = complete[-1]
    verify(source)
    archive = outbox / f"{source.name}.tar.age"
    checksum = outbox / f"{archive.name}.sha256"
    new = not (archive.is_file() and checksum.is_file()
               and checksum.read_bytes() == f"{sha256(archive)}  {archive.name}\n".encode("ascii"))
    if new:
        publish(outbox, archive.name, lambda stream: seal(source, stream, recipients))
    kept, pruned = prune_sealed(outbox, SEALED, keep, archive.name)
    print(json.dumps({"ok": True, "source": source.name, "sealed": archive.name if new else None,
                      "archive_bytes": archive.stat().st_size, "kept": len(kept), "pruned": pruned,
                      "free_bytes": shutil.disk_usage(outbox).free}))
    return archive


def capture(argv, user):
    """stdout of one short command; as `user` (no supplementary groups) when given."""
    drop = {"user": user, "group": user, "extra_groups": []} if user else {}
    try:
        result = subprocess.run(list(argv), capture_output=True, timeout=300, check=False, **drop)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise BackupError(f"{argv[0]} unavailable/timed out") from exc
    if result.returncode:
        raise BackupError(f"{argv[0]} failed ({result.returncode}): "
                          + result.stderr.decode("utf-8", errors="replace")[-2000:].strip())
    if not result.stdout:
        raise BackupError(f"{argv[0]} printed nothing")
    return result.stdout


def collect(patterns):
    """Matched paths plus everything under matched directories; links kept, not followed."""
    found, missing = set(), []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if not matches:
            missing.append(pattern)
        for match in matches:
            path = Path(match)
            found.add(path)
            if path.is_dir() and not path.is_symlink():
                for folder, dirs, files in os.walk(path):
                    found.update(Path(folder) / name for name in (*dirs, *files))
    return sorted(found), missing  # parents sort before children


def config_members(top, outputs, paths):
    """(TarInfo, bytes or None) for every member except CONFIG.json, all read up front."""
    now = int(datetime.now(VN).timestamp())
    members, files, links = [], {}, {}

    def generated(name, data):
        info = tarfile.TarInfo(f"{top}/{name}")
        info.size, info.mode, info.mtime = len(data), 0o600, now
        members.append((info, data))

    for name, data in outputs.items():
        generated(name, data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    with tarfile.TarFile(fileobj=io.BytesIO(), mode="w") as probe:  # gettarinfo needs a TarFile
        for path in paths:
            name = "files/" + path.relative_to(path.anchor).as_posix()
            info = probe.gettarinfo(path, f"{top}/{name}")  # lstat: owner, mode, link target
            if info.isreg():
                data = path.read_bytes()
                info.size = len(data)
                files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                members.append((info, data))
            elif info.issym() or info.isdir():
                if info.issym():
                    links[name] = info.linkname
                members.append((info, None))
            else:
                raise BackupError(f"unsupported file type: {path}")
    return members, files, links


def config(outbox, recipients, keep, databases=(), paths=CONFIG_PATHS, commands=CONFIG_COMMANDS):
    """Timer entry (root): PostgreSQL globals, hao config files, optional DB dumps, into age.

    Command output and file bytes go from memory into the age stream, so env
    files, service-account keys and role password hashes never land in
    plaintext. CONFIG.json lists SHA-256 of every file and each link target;
    a pattern matching nothing is listed under `missing`, not fatal. Prunes
    only after success, and only `v7-config-…` archives.
    """
    outbox = Path(outbox).expanduser().resolve()
    if not outbox.is_dir():
        raise BackupError("config outbox must be an existing directory")
    if not Path(recipients).is_file():
        raise BackupError("config recipients file missing")
    for database in databases:
        if not isinstance(database, str) or not DB_NAME.fullmatch(database):
            raise BackupError("database must be a plain database name (1..63 ASCII characters)")
    stamp = datetime.now(VN)
    top = stamp.strftime("v7-config-%Y%m%d-%H%M%S")
    commands = [*commands, *((f"databases/{name}.dump",
                              ("pg_dump", "--no-password", "-Fc", f"--dbname={name}"), "postgres")
                             for name in databases)]
    outputs = {member: capture(argv, user) for member, argv, user in commands}
    found, missing = collect(paths)
    members, files, links = config_members(top, outputs, found)
    manifest = json.dumps({"format_version": 1, "kind": "config", "host": socket.gethostname(),
                           "created_at_vn": stamp.isoformat(), "files": files, "links": links,
                           "missing": missing}, ensure_ascii=False, indent=2, sort_keys=True)

    def add(archive):
        folder = tarfile.TarInfo(top)
        folder.type, folder.mode, folder.mtime = tarfile.DIRTYPE, 0o700, int(stamp.timestamp())
        archive.addfile(folder)
        listing = tarfile.TarInfo(f"{top}/{CONFIG_MANIFEST}")
        text = (manifest + "\n").encode("utf-8")
        listing.size, listing.mode, listing.mtime = len(text), 0o600, folder.mtime
        archive.addfile(listing, io.BytesIO(text))
        for info, data in members:
            archive.addfile(info, io.BytesIO(data) if data is not None else None)

    archive = publish(outbox, f"{top}.tar.age", lambda stream: encrypt(stream, recipients, add))
    kept, pruned = prune_sealed(outbox, CONFIG_SEALED, keep, archive.name)
    print(json.dumps({"ok": True, "sealed": archive.name, "archive_bytes": archive.stat().st_size,
                      "files": len(files), "links": len(links), "missing": missing,
                      "kept": len(kept), "pruned": pruned, "free_bytes": shutil.disk_usage(outbox).free}))
    return archive


def verify_config(path):
    """Decrypted config tar: one `v7-config-…/` folder, every file and link as CONFIG.json says."""
    tops, files, links, manifest = set(), {}, {}, None
    try:
        with tarfile.open(path, mode="r:") as archive:
            for member in archive:
                top, _, name = member.name.partition("/")
                tops.add(top)
                if member.isreg():
                    data = archive.extractfile(member).read()
                    if name == CONFIG_MANIFEST:
                        manifest = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
                    else:
                        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                elif member.issym():
                    links[name] = member.linkname
    except (OSError, ValueError, tarfile.TarError) as exc:
        raise BackupError("cannot read config archive: " + str(exc)) from exc
    if len(tops) != 1 or not CONFIG_TOP.fullmatch(next(iter(tops))):
        raise BackupError("config archive must hold exactly one v7-config-YYYYMMDD-HHMMSS folder")
    if (not isinstance(manifest, dict) or manifest.get("format_version") != 1
            or manifest.get("kind") != "config" or not isinstance(manifest.get("missing"), list)):
        raise BackupError("missing or unsupported CONFIG.json")
    if manifest.get("files") != files or manifest.get("links") != links:
        raise BackupError("config archive does not match CONFIG.json")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup").add_argument("--out", required=True, type=Path)
    command = commands.add_parser("restore")
    command.add_argument("--from", dest="folder", required=True, type=Path)
    command.add_argument("--target-db", required=True)
    commands.add_parser("verify").add_argument("--from", dest="folder", required=True, type=Path)
    command = commands.add_parser("daily")
    command.add_argument("--root", required=True, type=Path)
    command.add_argument("--keep", type=int, default=30)
    command.add_argument("--min-free-mb", type=int, default=2048)
    command = commands.add_parser("offsite")
    command.add_argument("--root", required=True, type=Path)
    command.add_argument("--outbox", required=True, type=Path)
    command.add_argument("--recipients", required=True, type=Path)
    command.add_argument("--keep", type=int, default=14)
    command = commands.add_parser("config")
    command.add_argument("--outbox", required=True, type=Path)
    command.add_argument("--recipients", required=True, type=Path)
    command.add_argument("--keep", type=int, default=14)
    command.add_argument("--database", action="append", default=[], help="also pg_dump -Fc this DB")
    commands.add_parser("config-verify").add_argument("--tar", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "daily" and (args.keep < 1 or args.min_free_mb < 0):
        parser.error("daily needs --keep >= 1 and --min-free-mb >= 0")
    if args.command in ("offsite", "config") and args.keep < 1:
        parser.error(f"{args.command} needs --keep >= 1")
    try:
        if args.command == "backup":
            backup(args.out)
        elif args.command == "daily":
            daily(args.root, args.keep, args.min_free_mb)
        elif args.command == "offsite":
            offsite(args.root, args.outbox, args.recipients, args.keep)
        elif args.command == "config":
            config(args.outbox, args.recipients, args.keep, args.database)
        elif args.command == "config-verify":
            manifest = verify_config(args.tar)
            print(f"MATCH config archive: {len(manifest['files'])} files, {len(manifest['links'])} links, "
                  f"{len(manifest['missing'])} missing patterns")
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
