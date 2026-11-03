"""Which psql requests may share a kept connection, and how a reply is cut at its marker (no Docker)."""
import queue
import sys
import unittest
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

# Append, not insert: tools/ also has test_pg_v7_grants.py, and discovery must keep loading tests/'s copy.
sys.path.append(str(Path(__file__).resolve().parents[1] / "tools"))
import docker_exec_channel as channel

PSQL = ["docker", "exec", "-i", "--env", "PGAPPNAME=t", "c", "psql", "-X", "-qAt", "-U", "postgres", "-d", "db"]


class FakeKept:
    """Stands in for _KeptPsql: records what would reach psql."""

    sent: ClassVar[list[bytes]] = []

    def __init__(self, container, env, argv):
        self.lock = channel.threading.Lock()

    def alive(self):
        return True

    def close(self):
        pass

    def run(self, sql, timeout):
        FakeKept.sent.append(sql)
        return 0, b"1\n", b""


class KeptPsqlRoutingTests(unittest.TestCase):
    def setUp(self):
        FakeKept.sent = []
        patcher = patch.object(channel, "_KeptPsql", FakeKept)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(channel._kept.clear)

    def test_meta_commands_and_other_argv_fall_back(self):
        # `\set` variables would outlive the request on a kept connection.
        self.assertIsNone(channel.run_kept_psql(PSQL, input_text="\\set db x\nSELECT 1;\n", timeout=1))
        self.assertIsNone(channel.run_kept_psql(PSQL, input_text="SELECT 1;\n  \\gset\n", timeout=1))
        self.assertIsNone(channel.run_kept_psql(["docker", "exec", "-i", "c", "pg_isready"], input_text="", timeout=1))
        self.assertIsNone(channel.run_kept_psql(["docker", "exec", "-u", "x", "c", "psql"], input_text="", timeout=1))
        self.assertEqual(FakeKept.sent, [])

    def test_backslash_inside_sql_text_is_not_a_meta_command(self):
        p = channel.run_kept_psql(PSQL, input_text="SELECT E'a\\nb';\n", timeout=1)
        self.assertEqual((p.returncode, p.stdout), (0, "1\n"))
        self.assertEqual(FakeKept.sent, [b"SELECT E'a\\nb';\n"])

    def test_leading_bom_is_dropped_like_psql_does_at_input_start(self):
        channel.run_kept_psql(PSQL, input_text="\ufeffBEGIN; SELECT 1; COMMIT;\n", timeout=1)
        self.assertEqual(FakeKept.sent, [b"BEGIN; SELECT 1; COMMIT;\n"])

    def test_database_ddl_closes_kept_connections_first(self):
        # rehearse_v7_deploy drops a restored database; an open kept connection would block DROP DATABASE.
        channel.run_kept_psql(PSQL, input_text="SELECT 1;\n", timeout=1)
        self.assertEqual(len(channel._kept), 1)
        for sql in ("DROP DATABASE v7_restore_before;\n", "alter database x rename to y;\n",
                    "CREATE DATABASE b TEMPLATE a;\n"):
            channel.run_kept_psql(PSQL, input_text="SELECT 1;\n", timeout=1)
            self.assertIsNone(channel.run_kept_psql(PSQL, input_text=sql, timeout=1, share=False))
            self.assertEqual(channel._kept, {}, sql)
        self.assertEqual(FakeKept.sent, [b"SELECT 1;\n"] * 4)

    def test_busy_connection_falls_back(self):
        channel.run_kept_psql(PSQL, input_text="SELECT 1;\n", timeout=1)
        kept = next(iter(channel._kept.values()))
        with kept.lock:   # another thread holds it: lock/contention checks keep their own psql
            self.assertIsNone(channel.run_kept_psql(PSQL, input_text="SELECT 2;\n", timeout=1))


class UntilTests(unittest.TestCase):
    def test_reply_stops_at_marker_and_keeps_later_lines(self):
        lines = queue.Queue()
        for line in (b"a\n", b"__end__\r\n", b"next\n"):
            lines.put(line)
        self.assertEqual(channel._until(lines, b"__end__", 1), (b"a\n", True))
        self.assertEqual(lines.get_nowait(), b"next\n")

    def test_process_end_before_marker_returns_output_so_far(self):
        lines = queue.Queue()
        for line in (b"ERROR: x\n", None):
            lines.put(line)
        self.assertEqual(channel._until(lines, b"__end__", 1), (b"ERROR: x\n", False))
        self.assertIsNone(lines.get_nowait())  # the end stays visible to the other reader


if __name__ == "__main__":
    unittest.main()
