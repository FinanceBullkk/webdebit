"""No-database checks for direct socket guards and shared API errors."""
import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_ledger_api as api  # noqa: E402


class DirectTests(unittest.TestCase):
    def setUp(self):
        self.handler = patch.object(api, "Handler", type("DirectHandler", (api.Handler,), {}))
        self.handler.start()
        self.addCleanup(self.handler.stop)
        self.original_env = os.environ.copy()
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.command = patch.object(api.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "t|t", ""))
        self.run = self.command.start()
        self.addCleanup(self.command.stop)

    def direct(self, socket="/var/run/postgresql", database="fake_v7", role="v7_app"):
        return api.PsqlDirect(socket, database, role)

    def test_socket_role_database_guards(self):
        for socket in ("relative", "localhost", "127.0.0.1", "::1", "/tmp:5432"):
            with self.subTest(socket=socket), self.assertRaises(ValueError):
                self.direct(socket=socket)
        for role in ("", "postgres", "bad-role", "a b", "a;select"):
            with self.subTest(role=role), self.assertRaises(ValueError):
                self.direct(role=role)
        for database in ("", "webdebit_ledger", "bad-db", "a;select"):
            with self.subTest(database=database), self.assertRaises(ValueError):
                self.direct(database=database)
        self.run.assert_not_called()

    def test_password_environment_and_passfile(self):
        with patch.dict(os.environ, {"PGPASSWORD": "secret"}), self.assertRaises(ValueError) as caught:
            self.direct()
        self.assertNotIn("secret", str(caught.exception))
        with patch.object(api, "Path") as constructor, patch.dict(os.environ, {"PGPASSFILE": "placeholder"}):
            file = constructor.return_value
            file.is_symlink.return_value = False
            file.is_file.return_value = False
            with self.assertRaises(ValueError):
                self.direct()
            file.is_file.return_value = True
            file.stat.return_value.st_mode = 0o100600
            self.direct()
            file.is_symlink.return_value = True
            with self.assertRaises(ValueError):
                self.direct()
            file.is_symlink.return_value = False
            with patch.object(api.os, "name", "posix"):
                file.stat.return_value.st_mode = 0o100644
                with self.assertRaises(ValueError):
                    self.direct()

    def test_preflight_and_argv(self):
        runner = self.direct()
        for result in ("f|t", "t|f", "", "unexpected"):
            self.run.return_value = subprocess.CompletedProcess([], 0, result, "secret")
            with self.assertRaisesRegex(ValueError, "preflight rejected"):
                self.direct()
        self.run.return_value = subprocess.CompletedProcess([], 0, "{}", "")
        runner.run("get_ledger", {"customer_id": 1}, "fake")
        argv = self.run.call_args.args[0]
        self.assertNotIn("-p", argv)
        self.assertNotIn("secret", repr(argv))
        self.assertIn("-h", argv)
        self.assertIn("/var/run/postgresql", argv)
        self.assertIn("PGOPTIONS", self.run.call_args.kwargs["env"])

    def test_shared_error_table_and_timeouts(self):
        runner = self.direct()
        for code, (status, _) in api.ERRORS.items():
            self.run.return_value = subprocess.CompletedProcess([], 3, "", f"psql:<stdin>:3: ERROR:  P0001: {code}\nDETAIL:  {{\"available_credit_vnd\":\"123\"}}\n")
            with self.subTest(code=code), self.assertRaises(api.ApiError) as caught:
                runner.run("record_offset", {}, "fake")
            self.assertEqual((caught.exception.status, caught.exception.code), (status, code))
            if code == "OFFSET_EXCEEDS_CREDIT":
                self.assertEqual(caught.exception.extra, {"available_credit_vnd": "123"})
        self.run.side_effect = subprocess.TimeoutExpired([], 25)
        for function, expected in (("get_ledger", "DB_UNAVAILABLE"), ("record_receipt", "RESULT_UNKNOWN")):
            with self.assertRaises(api.ApiError) as caught:
                runner.run(function, {}, "fake")
            self.assertEqual(caught.exception.code, expected)

    def test_cli_target_and_explicit_database(self):
        for flags in (["--container", "fake", "--direct-socket-dir", "/var/run/postgresql"],
                      ["--direct-socket-dir", "/var/run/postgresql"],
                      ["--direct-socket-dir", "/var/run/postgresql", "--database", "webdebit_ledger"], []):
            with patch.object(sys, "argv", ["api", *flags]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                api.main()
        with patch.object(sys, "argv", ["api", "--direct-socket-dir", "/var/run/postgresql", "--database", "fake_v7"]), patch.object(api, "PsqlDirect") as runner, patch.object(api, "ThreadingHTTPServer"):
            api.main()
            runner.assert_called_once_with("/var/run/postgresql", "fake_v7", "v7_app")

    def test_harness_list_without_docker(self):
        self.command.stop()
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "test_pg_v7_direct.py"), "--list"], capture_output=True, text=True, check=False, env=self.original_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 3)
        self.assertIn("direct.loader", result.stdout)
