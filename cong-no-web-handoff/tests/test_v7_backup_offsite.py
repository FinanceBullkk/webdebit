"""v7_backup `offsite` (age seal for the off-host pull). Fake rows and fake age, no DB."""

import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
import uuid
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_backup as backup  # noqa: E402  (sys.path set above)

HEADER = b"FAKE-AGE\n"
FAKE_AGE = f"""
import sys
args = sys.argv[1:]
recipients = args[args.index("--recipients-file") + 1]
if open(recipients, encoding="utf-8").read().strip() == "FAIL":
    sys.stderr.write("fake age: bad recipient\\n")
    sys.exit(1)
sys.stdout.buffer.write({HEADER!r} + " ".join(args).encode() + b"\\n" + sys.stdin.buffer.read())
"""
TOTALS = {"1": "9007199254740993", "2": None, "3": "-25"}


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


def make_backup(root, name, dump=b"PGDMP fake\x00\xff\n", complete=True):
    folder = root / name
    folder.mkdir()
    (folder / backup.DUMP).write_bytes(dump)
    if complete:
        manifest = {"format_version": 1, "schema": "sokhach", "dump_file": backup.DUMP,
                    "dump_sha256": backup.sha256(folder / backup.DUMP),
                    "pg_dump_version": "pg_dump (PostgreSQL) 18.6", "server_version": "18.6",
                    "created_at_vn": "2026-10-29T02:40:00+07:00",
                    "table_row_counts": {"customer": 3, "trip": 2}, "customer_totals": TOTALS}
        (folder / backup.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def plain_tar(archive):
    """Fake age output: header, the age argv line, then the tar stream."""
    data = archive.read_bytes()
    assert data.startswith(HEADER)
    argv, _, payload = data[len(HEADER):].partition(b"\n")
    return argv.decode(), payload


class OffsiteTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(temporary_directory("v7-backup-offsite-"))
        self.root, self.outbox = self.base / "daily", self.base / "outbox"
        self.root.mkdir()
        self.outbox.mkdir()
        self.recipients = self.base / "recipients.txt"
        self.recipients.write_text("age1fakepublickey\n", encoding="utf-8")
        script = self.base / "fake_age.py"
        script.write_text(FAKE_AGE, encoding="utf-8")
        self.enterContext(patch.object(backup, "AGE", [sys.executable, "-I", str(script)]))

    def offsite(self, keep=14):
        output = io.StringIO()
        with redirect_stdout(output):
            archive = backup.offsite(self.root, self.outbox, self.recipients, keep)
        return archive, json.loads(output.getvalue().splitlines()[-1])

    def names(self):
        return sorted(entry.name for entry in self.outbox.iterdir())

    def test_seals_newest_complete_backup_as_tar_of_manifest_and_dump(self):
        make_backup(self.root, "v7-20200101-024000")
        newest = make_backup(self.root, "v7-20200102-024000", dump=b"newest dump")
        make_backup(self.root, "v7-20200103-024000", complete=False)  # failed run: never sealed
        archive, summary = self.offsite()
        name = "v7-20200102-024000.tar.age"
        self.assertEqual(self.names(), [name, f"{name}.sha256"])
        self.assertEqual((self.outbox / f"{name}.sha256").read_bytes(),
                         f"{backup.sha256(archive)}  {name}\n".encode("ascii"))
        argv, payload = plain_tar(archive)
        self.assertEqual(argv, f"--encrypt --recipients-file {self.recipients}")
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as stream:
            members = stream.getmembers()
            self.assertEqual([member.name for member in members],
                             [newest.name, f"{newest.name}/MANIFEST.json", f"{newest.name}/sokhach.dump"])
            self.assertTrue(members[0].isdir())
            for member in members[1:]:
                self.assertTrue(member.isreg())
                self.assertEqual((member.mode, member.uid, member.gid, member.uname), (0o600, 0, 0, ""))
            restored = self.base / "restored"
            restored.mkdir()
            stream.extractall(restored, filter="data")
        manifest = backup.verify(restored / newest.name)
        self.assertEqual(manifest["customer_totals"], TOTALS)
        self.assertEqual((restored / newest.name / backup.DUMP).read_bytes(), b"newest dump")
        self.assertEqual((summary["ok"], summary["source"], summary["sealed"], summary["kept"]),
                         (True, newest.name, name, 1))
        self.assertEqual(summary["archive_bytes"], archive.stat().st_size)
        self.assertNotIn("9007199254740993", json.dumps(summary))

    def test_rerun_seals_nothing_and_damaged_pair_is_sealed_again(self):
        make_backup(self.root, "v7-20200102-024000")
        archive, _ = self.offsite()
        before = archive.read_bytes()
        _, summary = self.offsite()
        self.assertIsNone(summary["sealed"])
        self.assertEqual(archive.read_bytes(), before)
        archive.write_bytes(before[:-1])  # damaged after sealing: checksum no longer matches
        _, summary = self.offsite()
        self.assertEqual(summary["sealed"], archive.name)
        self.assertEqual(archive.read_bytes(), before)

    def test_hash_mismatch_or_age_failure_writes_and_prunes_nothing(self):
        make_backup(self.root, "v7-20200101-024000")
        self.offsite(keep=1)
        newest = make_backup(self.root, "v7-20200102-024000")
        before = self.names()
        (newest / backup.DUMP).write_bytes(b"corrupt")
        with self.assertRaisesRegex(backup.BackupError, "SHA-256 MISMATCH"):
            backup.offsite(self.root, self.outbox, self.recipients, 1)
        self.assertEqual(self.names(), before)
        shutil.rmtree(newest)
        make_backup(self.root, "v7-20200102-024000")
        self.recipients.write_text("FAIL\n", encoding="utf-8")
        with self.assertRaisesRegex(backup.BackupError, "age/tar failed.*fake age: bad recipient"):
            backup.offsite(self.root, self.outbox, self.recipients, 1)
        self.assertEqual(self.names(), before)

    def test_unreadable_member_kills_age_and_leaves_no_partial(self):
        make_backup(self.root, "v7-20200102-024000")
        real_open, opened = Path.open, []

        def flaky_open(path, *args, **kwargs):
            # By name: offsite() resolves paths, and a runner's TEMP may be an 8.3 short path.
            if path.name == backup.DUMP:
                opened.append(path)
                if len(opened) == 2:  # 1st: verify() hashes it; 2nd: seal() streams it
                    raise PermissionError("fake unreadable dump")
            return real_open(path, *args, **kwargs)

        with patch.object(Path, "open", flaky_open), \
                self.assertRaisesRegex(backup.BackupError, "fake unreadable dump"):
            backup.offsite(self.root, self.outbox, self.recipients, 1)
        self.assertEqual(self.names(), [])

    def test_prunes_old_pairs_and_leaves_other_files_and_links(self):
        for day in ("01", "02", "03"):
            make_backup(self.root, f"v7-202001{day}-024000")
            self.offsite()
        (self.outbox / "notes.txt").write_text("keep", encoding="utf-8")
        (self.outbox / "v7-manual.tar.age").write_text("keep", encoding="utf-8")
        target = self.base / "precious.tar.age"
        target.write_text("keep", encoding="utf-8")
        link = self.outbox / "v7-19990101-024000.tar.age"
        try:
            link.symlink_to(target)
        except OSError:
            link = None  # OS without symlink permission: the rest still holds
        make_backup(self.root, "v7-20200104-024000")
        _, summary = self.offsite(keep=2)
        expected = ["notes.txt", "v7-20200103-024000.tar.age", "v7-20200103-024000.tar.age.sha256",
                    "v7-20200104-024000.tar.age", "v7-20200104-024000.tar.age.sha256", "v7-manual.tar.age"]
        if link:
            expected.insert(1, link.name)
        self.assertEqual(self.names(), expected)
        self.assertEqual(summary["pruned"], ["v7-20200101-024000.tar.age", "v7-20200102-024000.tar.age"])
        self.assertEqual(target.read_text(encoding="utf-8"), "keep")

    def test_archive_named_before_existing_ones_is_still_kept(self):
        make_backup(self.root, "v7-20200101-024000")
        self.offsite()
        (self.outbox / "v7-29991231-235959.tar.age").write_bytes(b"clock stepped back")
        _, summary = self.offsite(keep=1)
        self.assertEqual((summary["kept"], summary["pruned"]), (2, []))

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_outbox_files_follow_umask_so_the_pull_group_can_read(self):
        make_backup(self.root, "v7-20200102-024000")
        previous = os.umask(0o027)
        try:
            archive, _ = self.offsite()
        finally:
            os.umask(previous)
        for path in (archive, self.outbox / f"{archive.name}.sha256"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_cli_rejects_bad_keep_paths_and_empty_root(self):
        base = ["offsite", "--root", str(self.root), "--outbox", str(self.outbox),
                "--recipients", str(self.recipients)]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            backup.main([*base, "--keep", "0"])
        self.assertEqual(raised.exception.code, 2)
        cases = [
            (base, "no complete backup"),
            ([*base[:4], str(self.base / "missing")] + base[5:], "existing directories"),
            ([*base[:4], str(self.root / "inner")] + base[5:], "contain each other"),
            ([*base[:6], str(self.base / "missing.txt")], "recipients file missing"),
        ]
        (self.root / "inner").mkdir()
        for args, message in cases:
            with self.subTest(message=message), redirect_stderr(io.StringIO()) as error:
                self.assertEqual(backup.main(args), 2)
            self.assertIn(message, error.getvalue())
        self.assertEqual(self.names(), [])


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "age not installed")
class RealAgeRoundTrip(unittest.TestCase):
    def test_sealed_archive_decrypts_to_a_verifiable_backup(self):
        base = self.enterContext(temporary_directory("v7-backup-offsite-age-"))
        root, outbox = base / "daily", base / "outbox"
        root.mkdir()
        outbox.mkdir()
        make_backup(root, "v7-20200102-024000")
        identity, recipients = base / "identity.txt", base / "recipients.txt"
        subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
        recipients.write_bytes(subprocess.run(["age-keygen", "-y", str(identity)], check=True,
                                              capture_output=True).stdout)
        with redirect_stdout(io.StringIO()):
            archive = backup.offsite(root, outbox, recipients, 1)
        payload = subprocess.run(["age", "--decrypt", "-i", str(identity), str(archive)], check=True,
                                 capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as stream:
            stream.extractall(base / "restored", filter="data")
        self.assertEqual(backup.verify(base / "restored" / "v7-20200102-024000")["customer_totals"], TOTALS)


if __name__ == "__main__":
    unittest.main()
