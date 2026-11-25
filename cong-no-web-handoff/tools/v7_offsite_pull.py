#!/usr/bin/env python3
"""Pull age-encrypted V7 backups from hao over read-only SFTP (stdlib only).

Task Scheduler entry on the off-host PC; pairs with `v7_backup.py offsite`
and `v7_backup.py config`. Copies `v7-YYYYMMDD-HHMMSS.tar.age` and
`v7-config-YYYYMMDD-HHMMSS.tar.age` + `.sha256` pairs missing here, keeps a
file only after its SHA-256 matches, prunes each family beyond `--keep` when
the run had no error, appends one line to `pull.log`. Never decrypts. Host,
user and key come from arguments, never from the repo.

`--ping-url-file` (audit vận hành 23/11/2026, O8): a file holding this PC's own
healthchecks.io URL. After the log line the run pings it (PASS) or `<url>/fail`
(FAIL), so a pull that logs in but keeps nothing (disk full, hash mismatch)
mails like a missed one. The body carries counts and file names only.

`--hourly` (RPO 25/11/2026): pull only `v7-hourly-YYYYMMDD-HHMMSS.tar.age`
pairs (`v7_backup.py offsite --hourly`) from the same outbox. Run it as its own
task into its own `--dest`, with its own `pull.log` and check, so an hourly run
never deletes the `.partial` files of a daily run or prunes its family.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ARCHIVE = re.compile(r"v7-[0-9]{8}-[0-9]{6}\.tar\.age\Z")
CONFIG = re.compile(r"v7-config-[0-9]{8}-[0-9]{6}\.tar\.age\Z")  # optional: older outboxes have none
HOURLY = re.compile(r"v7-hourly-[0-9]{8}-[0-9]{6}\.tar\.age\Z")
FAMILIES = (("", ARCHIVE), ("config_", CONFIG))  # (pull.log prefix, names); the first one must not be empty
HOURLY_FAMILIES = (("", HOURLY),)
CHECKSUM = re.compile(r"([0-9a-f]{64})  (v7-(?:config-|hourly-)?[0-9]{8}-[0-9]{6}\.tar\.age)\n\Z")
LOG = "pull.log"
VN = timezone(timedelta(hours=7))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # pythonw under Task Scheduler: no console flash


class PullError(RuntimeError):
    pass


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def sftp(args, commands):
    """One batch session in the destination folder; `-b -` stops at the first failing command."""
    try:
        result = subprocess.run(
            [args.sftp, "-b", "-", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
             "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes", "-i", str(args.identity),
             f"{args.user}@{args.host}"],
            input="".join(f"{command}\n" for command in commands), capture_output=True,
            encoding="utf-8", errors="replace", cwd=args.dest, timeout=1800, check=False,
            creationflags=NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PullError("sftp unavailable/timed out") from exc
    if result.returncode:
        raise PullError(f"sftp failed ({result.returncode}): {result.stderr.strip()[-500:]}")
    return result.stdout


def remote_names(args):
    """One listing of the outbox (the forced command starts there)."""
    return {line.strip() for line in sftp(args, ["ls -1"]).splitlines()}


def remote_pairs(names, pattern):
    """Archives whose checksum is also in the outbox."""
    return sorted(name for name in names if pattern.fullmatch(name) and f"{name}.sha256" in names)


def local_pairs(dest, pattern=ARCHIVE):
    return sorted(entry.name for entry in dest.iterdir() if pattern.fullmatch(entry.name)
                  and entry.is_file() and (dest / f"{entry.name}.sha256").is_file())


def fetch(args, name):
    """Both files to `.partial`; archive replaces first so a lone checksum never looks complete."""
    archive, checksum = args.dest / f"{name}.partial", args.dest / f"{name}.sha256.partial"
    try:
        sftp(args, [f'get "{name}.sha256" "{checksum.name}"', f'get "{name}" "{archive.name}"'])
        match = CHECKSUM.fullmatch(checksum.read_bytes().decode("ascii", errors="replace"))
        if not match or match[2] != name:
            raise PullError(f"bad checksum file for {name}")
        if sha256(archive) != match[1]:
            raise PullError(f"SHA-256 MISMATCH {name}")
        os.replace(archive, args.dest / name)
        os.replace(checksum, args.dest / f"{name}.sha256")
    finally:
        archive.unlink(missing_ok=True)
        checksum.unlink(missing_ok=True)


def pull(args):
    """Returns the PASS summary; raises PullError listing every pair that failed."""
    if not args.dest.is_dir():
        raise PullError("dest must be an existing directory")
    families = HOURLY_FAMILIES if getattr(args, "hourly", False) else FAMILIES
    for entry in args.dest.iterdir():  # leftovers of a run killed mid-transfer
        stem = entry.name.removesuffix(".partial").removesuffix(".sha256")
        if entry.name.endswith(".partial") and entry.is_file() and any(
                pattern.fullmatch(stem) for _, pattern in families):
            entry.unlink()
    names = remote_names(args)
    if not remote_pairs(names, families[0][1]):
        raise PullError("no sealed backup in the outbox")
    errors, pulled = [], {}
    for prefix, pattern in families:
        have = local_pairs(args.dest, pattern)
        # Only what the window keeps: a short --keep never re-downloads pruned pairs.
        wanted = sorted({*have, *remote_pairs(names, pattern)})[-args.keep:]
        pulled[prefix] = [name for name in wanted if name not in have]
        for name in pulled[prefix]:
            try:
                fetch(args, name)
            except PullError as exc:
                errors.append(str(exc))
    if errors:
        raise PullError("; ".join(errors))
    summary = []
    for prefix, pattern in families:  # prune only after a run without any error
        pairs = local_pairs(args.dest, pattern)
        pruned = pairs[:-args.keep]
        for name in pruned:
            (args.dest / f"{name}.sha256").unlink()
            (args.dest / name).unlink()
        summary.append(f"{prefix}pulled={len(pulled[prefix])} {prefix}newest={pairs[-1] if pairs else '-'} "
                       f"{prefix}kept={len(pairs) - len(pruned)} {prefix}pruned={len(pruned)}")
    return "PASS " + " ".join(summary)


def ping(url_file, line, failed, opener=None):
    """POST to this PC's check; errors are returned, never raised (the pull result stands)."""
    try:
        url = Path(url_file).read_text(encoding="utf-8").strip()
        if not url.startswith("https://"):
            return "ping URL must start with https://"
        body = ("FAIL" if failed else line).encode("utf-8")   # FAIL detail (sftp stderr) stays in pull.log
        with (opener or urllib.request.urlopen)(urllib.request.Request(url + ("/fail" if failed else ""), data=body, method="POST"), timeout=20):
            return None
    except (OSError, ValueError) as exc:
        return f"ping failed ({type(exc).__name__})"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--dest", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=30)
    parser.add_argument("--sftp", default="sftp")
    parser.add_argument("--ping-url-file", type=Path, help="file with this PC's healthchecks.io URL (O8)")
    parser.add_argument("--hourly", action="store_true", help="pull only v7-hourly-… pairs (own task, own --dest)")
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error("--keep must be >= 1")
    args.dest = args.dest.expanduser().resolve()
    try:
        line, code = pull(args), 0
    except (PullError, OSError) as exc:
        line, code = f"FAIL {exc}", 2
    stamp = datetime.now(VN).isoformat(timespec="seconds")
    if args.ping_url_file:
        problem = ping(args.ping_url_file, line, failed=bool(code))
        line += f" | {problem}" if problem else " | pinged"
    try:
        with (args.dest / LOG).open("a", encoding="utf-8") as stream:
            stream.write(f"{stamp} {line}\n")
    except OSError as exc:
        print(f"ERROR: cannot write {LOG}: {exc}", file=sys.stderr)
        code = 2
    print(line, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
