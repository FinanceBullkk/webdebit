"""v7_offsite_pull (PC side of the off-host copy). Fake SFTP and fake archives, no network."""

import hashlib
import io
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import v7_offsite_pull as pull  # noqa: E402  (sys.path set above)


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


class FakeSftp:
    """Plays the read-only outbox: `ls -1` and `get "remote" "local"` relative to cwd."""

    def __init__(self, remote):
        self.remote, self.calls, self.down = remote, [], False

    def __call__(self, argv, *, input, cwd, **kwargs):
        self.calls.append((argv, input))
        if self.down:
            return subprocess.CompletedProcess(argv, 255, "", "ssh: connect to host: timed out")
        out = []
        for line in input.splitlines():
            out.append(f"sftp> {line}")
            command, *names = shlex.split(line)
            if command == "ls":
                out.extend(sorted(entry.name for entry in self.remote.iterdir()))
            elif command == "get" and (self.remote / names[0]).is_file():
                shutil.copyfile(self.remote / names[0], Path(cwd) / names[1])
            else:
                return subprocess.CompletedProcess(argv, 1, "\n".join(out), f"not found: {line}")
        return subprocess.CompletedProcess(argv, 0, "\n".join(out) + "\n", "")


class PullTests(unittest.TestCase):
    def setUp(self):
        self.remote = self.enterContext(temporary_directory("v7-offsite-remote-"))
        self.dest = self.enterContext(temporary_directory("v7-offsite-dest-"))
        self.sftp = FakeSftp(self.remote)
        self.enterContext(patch.object(pull.subprocess, "run", self.sftp))

    def seal(self, stamp, folder=None, payload=None, good=True):
        folder = folder or self.remote
        name = f"v7-{stamp}.tar.age"
        data = payload or f"encrypted {stamp}".encode()
        (folder / name).write_bytes(data)
        digest = hashlib.sha256(data if good else b"other").hexdigest()
        (folder / f"{name}.sha256").write_bytes(f"{digest}  {name}\n".encode("ascii"))
        return name

    def main(self, *extra, keep="30"):
        argv = ["--host", "hao.example", "--user", "puller", "--identity", "C:/keys/pull",
                "--dest", str(self.dest), "--keep", keep, "--sftp", "sftp-fake", *extra]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return pull.main(argv)

    def log(self):
        return (self.dest / pull.LOG).read_text(encoding="utf-8").splitlines()

    def names(self):
        return sorted(entry.name for entry in self.dest.iterdir() if entry.name != pull.LOG)

    def test_pulls_missing_pairs_only_and_checks_every_hash(self):
        first = self.seal("20200101-030000")
        second = self.seal("20200102-030000", payload=b"\x00\xff binary \r\n bytes")
        (self.remote / "v7-20200103-030000.tar.age").write_bytes(b"no checksum yet")
        (self.remote / "notes.txt").write_text("ignored", encoding="utf-8")
        self.assertEqual(self.main(), 0)
        self.assertEqual(self.names(), [first, f"{first}.sha256", second, f"{second}.sha256"])
        self.assertEqual((self.dest / second).read_bytes(), b"\x00\xff binary \r\n bytes")
        self.assertRegex(self.log()[-1], r"^\S+\+07:00 PASS pulled=2 newest=v7-20200102-030000.tar.age "
                                         r"kept=2 pruned=0$")
        self.assertEqual(self.main(), 0)
        self.assertIn("PASS pulled=0", self.log()[-1])
        argv, _ = self.sftp.calls[-1]
        self.assertEqual(argv[:3], ["sftp-fake", "-b", "-"])
        for option in ("BatchMode=yes", "StrictHostKeyChecking=yes", "IdentitiesOnly=yes"):
            self.assertIn(option, argv)
        self.assertEqual((argv[argv.index("-i") + 1], argv[-1]), (str(Path("C:/keys/pull")), "puller@hao.example"))
        commands = {shlex.split(line)[0] for _, batch in self.sftp.calls for line in batch.splitlines()}
        self.assertEqual(commands, {"ls", "get"})  # read-only verbs only

    def test_mismatch_keeps_nothing_of_that_pair_still_pulls_others_and_skips_prune(self):
        old = [self.seal(f"201912{day}-030000", folder=self.dest) for day in ("29", "30", "31")]
        bad = self.seal("20200101-030000", good=False)
        good = self.seal("20200102-030000")
        self.assertEqual(self.main(keep="3"), 2)
        self.assertNotIn(bad, self.names())
        self.assertIn(good, self.names())
        for name in old:  # failed run: no prune even though 4 pairs > keep 3
            self.assertIn(name, self.names())
        self.assertRegex(self.log()[-1], rf"FAIL SHA-256 MISMATCH {bad}$")
        self.assertFalse([name for name in self.names() if name.endswith(".partial")])

    def test_keep_window_prunes_oldest_and_never_refetches_pruned_pairs(self):
        local = [self.seal(f"2020010{day}-030000", folder=self.dest) for day in "123"]
        remote = [self.seal(f"2020010{day}-030000") for day in "12345"]
        self.assertEqual(self.main(keep="3"), 0)
        self.assertEqual(self.names(), sorted([*remote[2:], *(f"{n}.sha256" for n in remote[2:])]))
        self.assertIn("pulled=2", self.log()[-1])
        self.assertIn("pruned=2", self.log()[-1])
        gets = [line for _, batch in self.sftp.calls for line in batch.splitlines() if line.startswith("get")]
        self.assertFalse([line for line in gets if local[0] in line or local[1] in line])

    def test_connection_failure_logs_fail_and_touches_nothing(self):
        kept = self.seal("20200101-030000", folder=self.dest)
        self.sftp.down = True
        self.assertEqual(self.main(), 2)
        self.assertEqual(self.names(), [kept, f"{kept}.sha256"])
        self.assertIn("FAIL sftp failed (255)", self.log()[-1])

    def test_empty_outbox_and_leftover_partials(self):
        (self.dest / "v7-20200101-030000.tar.age.partial").write_bytes(b"killed mid-transfer")
        (self.dest / "v7-20200101-030000.tar.age.sha256.partial").write_bytes(b"killed")
        (self.dest / "other.partial").write_bytes(b"not ours")
        self.assertEqual(self.main(), 2)
        self.assertIn("FAIL no sealed backup in the outbox", self.log()[-1])
        self.assertEqual(self.names(), ["other.partial"])

    def test_bad_checksum_line_is_rejected(self):
        name = self.seal("20200101-030000")
        (self.remote / f"{name}.sha256").write_bytes(b"deadbeef  " + name.encode() + b"\n")
        self.assertEqual(self.main(), 2)
        self.assertIn(f"FAIL bad checksum file for {name}", self.log()[-1])
        self.assertEqual(self.names(), [])

    def test_cli_rejects_bad_keep_and_missing_dest(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            pull.main(["--host", "h", "--user", "u", "--identity", "k", "--dest", str(self.dest), "--keep", "0"])
        self.assertEqual(raised.exception.code, 2)
        with redirect_stderr(io.StringIO()) as error:
            code = pull.main(["--host", "h", "--user", "u", "--identity", "k",
                              "--dest", str(self.dest / "missing")])
        self.assertEqual(code, 2)
        self.assertIn("cannot write pull.log", error.getvalue())
        self.assertEqual(self.sftp.calls, [])


if __name__ == "__main__":
    unittest.main()
