#!/usr/bin/env python3
"""Pull age-encrypted V7 backups from hao over read-only SFTP (stdlib only).

Task Scheduler entry on the off-host PC; pairs with `v7_backup.py offsite`.
Copies `v7-YYYYMMDD-HHMMSS.tar.age` + `.sha256` pairs missing here, keeps a
file only after its SHA-256 matches, prunes pairs beyond `--keep` when the run
had no error, appends one line to `pull.log`. Never decrypts. Host, user and
key come from arguments, never from the repo.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ARCHIVE = re.compile(r"v7-[0-9]{8}-[0-9]{6}\.tar\.age\Z")
CHECKSUM = re.compile(r"([0-9a-f]{64})  (v7-[0-9]{8}-[0-9]{6}\.tar\.age)\n\Z")
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


def remote_pairs(args):
    """Archives whose checksum is also in the outbox (the forced command starts there)."""
    names = {line.strip() for line in sftp(args, ["ls -1"]).splitlines()}
    return sorted(name for name in names if ARCHIVE.fullmatch(name) and f"{name}.sha256" in names)


def local_pairs(dest):
    return sorted(entry.name for entry in dest.iterdir() if ARCHIVE.fullmatch(entry.name)
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
    for entry in args.dest.iterdir():  # leftovers of a run killed mid-transfer
        stem = entry.name.removesuffix(".partial").removesuffix(".sha256")
        if entry.name.endswith(".partial") and ARCHIVE.fullmatch(stem) and entry.is_file():
            entry.unlink()
    have = local_pairs(args.dest)
    remote = remote_pairs(args)
    if not remote:
        raise PullError("no sealed backup in the outbox")
    # Only what the window keeps: a short --keep never re-downloads pruned pairs.
    wanted = sorted({*have, *remote})[-args.keep:]
    errors = []
    pulled = [name for name in wanted if name not in have]
    for name in pulled:
        try:
            fetch(args, name)
        except PullError as exc:
            errors.append(str(exc))
    if errors:
        raise PullError("; ".join(errors))
    pairs = local_pairs(args.dest)
    pruned = pairs[:-args.keep]
    for name in pruned:
        (args.dest / f"{name}.sha256").unlink()
        (args.dest / name).unlink()
    return (f"PASS pulled={len(pulled)} newest={pairs[-1]} kept={len(pairs) - len(pruned)} "
            f"pruned={len(pruned)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--identity", required=True, type=Path)
    parser.add_argument("--dest", required=True, type=Path)
    parser.add_argument("--keep", type=int, default=30)
    parser.add_argument("--sftp", default="sftp")
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error("--keep must be >= 1")
    args.dest = args.dest.expanduser().resolve()
    try:
        line, code = pull(args), 0
    except (PullError, OSError) as exc:
        line, code = f"FAIL {exc}", 2
    stamp = datetime.now(VN).isoformat(timespec="seconds")
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
