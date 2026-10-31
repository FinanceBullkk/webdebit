"""v7_backup `config` (globals + hao config files, age seal). Fake commands and fake age, no DB."""

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
sys.stdout.buffer.write({HEADER!r} + sys.stdin.buffer.read())
"""
ENV_LINE = "GOOGLE_PRIVATE_KEY=fake-secret-value"


@contextmanager
def temporary_directory(prefix):
    # Same reason as tools/test_v7_backup.py: TemporaryDirectory's mkdir(0o700)
    # excludes the Windows sandbox token; the default ACL is fine for fake files.
    folder = Path(tempfile.gettempdir()) / (prefix + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        shutil.rmtree(folder)


def echo(text):
    return (sys.executable, "-I", "-c", f"import sys; sys.stdout.buffer.write({text.encode()!r})")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.base = self.enterContext(temporary_directory("v7-backup-config-"))
        self.outbox, self.etc = self.base / "outbox", self.base / "etc"
        self.outbox.mkdir()
        (self.etc / "webdebit").mkdir(parents=True)
        (self.etc / "webdebit" / "sheet.env").write_bytes(f"{ENV_LINE}\n".encode())
        (self.etc / "webdebit" / "nested").mkdir()
        (self.etc / "webdebit" / "nested" / "sa.json").write_bytes(b'{"private_key_id": "fake"}\n')
        (self.etc / "sshd_config").write_bytes(b"PasswordAuthentication no\n")
        self.paths = (str(self.etc / "webdebit"), str(self.etc / "ssh*"), str(self.etc / "absent-*"))
        self.commands = (("globals.sql", echo("CREATE ROLE sokhach_app;\n"), None),
                         ("tailscale-serve.json", echo('{"TCP": {}}'), None))
        self.recipients = self.base / "recipients.txt"
        self.recipients.write_text("age1fakepublickey\n", encoding="utf-8")
        script = self.base / "fake_age.py"
        script.write_text(FAKE_AGE, encoding="utf-8")
        self.enterContext(patch.object(backup, "AGE", [sys.executable, "-I", str(script)]))

    def config(self, keep=14, databases=(), commands=None):
        output = io.StringIO()
        with redirect_stdout(output):
            archive = backup.config(self.outbox, self.recipients, keep, databases, self.paths,
                                    self.commands if commands is None else commands)
        return archive, json.loads(output.getvalue().splitlines()[-1])

    def plain(self, archive):
        """Fake age output is the header then the tar stream."""
        data = archive.read_bytes()
        self.assertTrue(data.startswith(HEADER))
        plain = self.base / "plain.tar"
        plain.write_bytes(data[len(HEADER):])
        return plain

    def names(self):
        return sorted(entry.name for entry in self.outbox.iterdir())

    def test_seals_command_output_and_files_with_hashes_and_no_plaintext_left(self):
        link = self.etc / "webdebit" / "unit.timer"
        try:
            link.symlink_to("/etc/systemd/system/v7-backup-daily.timer")
        except OSError:
            link = None  # OS without symlink permission: the rest still holds
        archive, summary = self.config()
        self.assertRegex(archive.name, r"^v7-config-[0-9]{8}-[0-9]{6}\.tar\.age$")
        self.assertEqual(self.names(), [archive.name, f"{archive.name}.sha256"])
        self.assertEqual((self.outbox / f"{archive.name}.sha256").read_bytes(),
                         f"{backup.sha256(archive)}  {archive.name}\n".encode("ascii"))
        plain = self.plain(archive)
        manifest = backup.verify_config(plain)
        top = archive.name.removesuffix(".tar.age")
        etc = "files/" + self.etc.relative_to(self.etc.anchor).as_posix()
        expected = {"globals.sql", "tailscale-serve.json", f"{etc}/webdebit/sheet.env",
                    f"{etc}/webdebit/nested/sa.json", f"{etc}/sshd_config"}
        self.assertEqual(set(manifest["files"]), expected)
        self.assertEqual(manifest["missing"], [str(self.etc / "absent-*")])
        self.assertEqual(manifest["links"], {f"{etc}/webdebit/unit.timer":
                                             "/etc/systemd/system/v7-backup-daily.timer"} if link else {})
        with tarfile.open(plain, mode="r:") as stream:
            names = stream.getnames()
            self.assertEqual(names[:2], [top, f"{top}/{backup.CONFIG_MANIFEST}"])
            self.assertIn(f"{top}/{etc}/webdebit/nested", names)  # directory entry keeps its mode
            env = stream.extractfile(f"{top}/{etc}/webdebit/sheet.env").read().decode()
            self.assertEqual(stream.extractfile(f"{top}/globals.sql").read(), b"CREATE ROLE sokhach_app;\n")
        self.assertEqual(env, ENV_LINE + "\n")
        self.assertEqual((summary["ok"], summary["sealed"], summary["files"], summary["kept"]),
                         (True, archive.name, 5, 1))
        self.assertEqual(summary["links"], 1 if link else 0)
        self.assertEqual(summary["archive_bytes"], archive.stat().st_size)
        self.assertNotIn("fake-secret-value", json.dumps(summary))

    def test_database_dumps_run_pg_dump_as_postgres(self):
        calls = []

        def fake_capture(argv, user):
            calls.append((tuple(argv), user))
            return b"PGDMP fake"

        with patch.object(backup, "capture", fake_capture):
            archive, summary = self.config(databases=["webdebit_ledger"], commands=())
        self.assertEqual(calls, [(("pg_dump", "--no-password", "-Fc", "--dbname=webdebit_ledger"), "postgres")])
        manifest = backup.verify_config(self.plain(archive))
        self.assertIn("databases/webdebit_ledger.dump", manifest["files"])
        self.assertEqual(summary["files"], 4)
        self.assertEqual(backup.CONFIG_COMMANDS[0][1:], (("pg_dumpall", "--globals-only", "--no-password"),
                                                         "postgres"))
        with self.assertRaisesRegex(backup.BackupError, "plain database name"):
            backup.config(self.outbox, self.recipients, 1, ["postgres://x"], self.paths, ())

    def test_command_or_age_failure_writes_nothing(self):
        failing = (("globals.sql", (sys.executable, "-I", "-c", "import sys; sys.stderr.write('peer fail'); sys.exit(3)"),
                    None),)
        with self.assertRaisesRegex(backup.BackupError, "failed \\(3\\): peer fail"):
            backup.config(self.outbox, self.recipients, 1, (), self.paths, failing)
        empty = (("globals.sql", echo(""), None),)
        with self.assertRaisesRegex(backup.BackupError, "printed nothing"):
            backup.config(self.outbox, self.recipients, 1, (), self.paths, empty)
        self.recipients.write_text("FAIL\n", encoding="utf-8")
        with self.assertRaisesRegex(backup.BackupError, "age/tar failed.*fake age: bad recipient"):
            backup.config(self.outbox, self.recipients, 1, (), self.paths, self.commands)
        self.assertEqual(self.names(), [])

    def test_prunes_only_config_archives(self):
        for name in ("v7-config-20200101-025000.tar.age", "v7-config-20200102-025000.tar.age",
                     "v7-20200102-024000.tar.age"):
            (self.outbox / name).write_bytes(b"old")
            (self.outbox / f"{name}.sha256").write_bytes(b"old")
        (self.outbox / "notes.txt").write_text("keep", encoding="utf-8")
        archive, summary = self.config(keep=2)
        self.assertEqual(summary["pruned"], ["v7-config-20200101-025000.tar.age"])
        self.assertEqual(self.names(), sorted([
            "notes.txt", "v7-20200102-024000.tar.age", "v7-20200102-024000.tar.age.sha256",
            "v7-config-20200102-025000.tar.age", "v7-config-20200102-025000.tar.age.sha256",
            archive.name, f"{archive.name}.sha256"]))
        self.assertEqual(backup.sealed(self.outbox), ["v7-20200102-024000.tar.age"])  # offsite family untouched

    def test_verify_config_rejects_tampered_or_foreign_archives(self):
        archive, _ = self.config()
        plain = self.plain(archive)
        top = archive.name.removesuffix(".tar.age")
        with tarfile.open(plain, mode="r:") as stream:
            members = [(member, stream.extractfile(member).read() if member.isreg() else None)
                       for member in stream.getmembers()]

        def rewrite(change):
            target = self.base / f"case-{uuid.uuid4().hex}.tar"
            with tarfile.open(target, mode="w:") as stream:
                for original, payload in members:
                    member, data = change(original, payload)
                    if member is not None:
                        if data is not None:
                            member.size = len(data)
                        stream.addfile(member, io.BytesIO(data) if data is not None else None)
            return target

        def corrupt(member, data):
            return member, (b"tampered" if member.name == f"{top}/globals.sql" else data)

        def drop(member, data):
            return (None, None) if member.name == f"{top}/tailscale-serve.json" else (member, data)

        def rename(member, data):
            member.name = member.name.replace(top, "v7-config-x", 1)
            return member, data

        for change, message in ((corrupt, "does not match CONFIG.json"), (drop, "does not match CONFIG.json"),
                                (rename, "exactly one v7-config")):
            with self.subTest(change=change.__name__), self.assertRaisesRegex(backup.BackupError, message):
                backup.verify_config(rewrite(change))
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(backup.main(["config-verify", "--tar", str(plain)]), 0)
        self.assertEqual(output.getvalue(), "MATCH config archive: 5 files, 0 links, 1 missing patterns\n")

    @unittest.skipIf(os.name == "nt", "POSIX permission bits")
    def test_outbox_files_follow_umask_so_the_pull_group_can_read(self):
        previous = os.umask(0o027)
        try:
            archive, _ = self.config()
        finally:
            os.umask(previous)
        for path in (archive, self.outbox / f"{archive.name}.sha256"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_cli_rejects_bad_keep_and_paths(self):
        base = ["config", "--outbox", str(self.outbox), "--recipients", str(self.recipients)]
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            backup.main([*base, "--keep", "0"])
        self.assertEqual(raised.exception.code, 2)
        cases = [([*base[:2], str(self.base / "missing"), *base[3:]], "existing directory"),
                 ([*base[:4], str(self.base / "missing.txt")], "recipients file missing")]
        for args, message in cases:
            with self.subTest(message=message), redirect_stderr(io.StringIO()) as error:
                self.assertEqual(backup.main(args), 2)
            self.assertIn(message, error.getvalue())
        self.assertEqual(self.names(), [])


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "age not installed")
class RealAgeRoundTrip(unittest.TestCase):
    def test_config_archive_decrypts_to_a_verifiable_tar(self):
        base = self.enterContext(temporary_directory("v7-backup-config-age-"))
        outbox, etc = base / "outbox", base / "etc"
        outbox.mkdir()
        etc.mkdir()
        (etc / "sheet.env").write_text(ENV_LINE, encoding="utf-8")
        identity, recipients = base / "identity.txt", base / "recipients.txt"
        subprocess.run(["age-keygen", "-o", str(identity)], check=True, capture_output=True)
        recipients.write_bytes(subprocess.run(["age-keygen", "-y", str(identity)], check=True,
                                              capture_output=True).stdout)
        with redirect_stdout(io.StringIO()):
            archive = backup.config(outbox, recipients, 1, (), (str(etc),),
                                    (("globals.sql", echo("CREATE ROLE x;\n"), None),))
        plain = base / "plain.tar"
        subprocess.run(["age", "--decrypt", "-i", str(identity), "-o", str(plain), str(archive)], check=True,
                       capture_output=True)
        self.assertEqual(len(backup.verify_config(plain)["files"]), 2)


if __name__ == "__main__":
    unittest.main()
