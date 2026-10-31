"""Audit DevOps 31/10/2026: /healthz chạm DB (#6), client ngắt kết nối không traceback (#15), kiểm sống deploy."""

import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))
import v7_api_sheet  # noqa: E402
import v7_ledger_api as api  # noqa: E402

AUTHORITY = "demo.tail-example.ts.net:8443"


class FakeRunner:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def run(self, function, payload, actor):
        self.calls.append((function, payload, actor))
        if self.fail:
            raise api.ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        return 1 if function == "healthz" else {"function": function}


class HealthzTest(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.localapi = Mock()
        self.localapi.whois.return_value = {"UserProfile": {"LoginName": "configured"}}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.sheet = Path(directory.name) / "snapshot.json"
        self.prices = Path(directory.name) / "prices.json"
        for path, mtime in ((self.sheet, 1_000_000), (self.prices, 1_000_600)):
            path.write_text("{}", encoding="utf-8")
            os.utime(path, (mtime, mtime))
        for name, value in (("SHEET_SNAPSHOT_PATH", str(self.sheet)), ("PRICE_SNAPSHOT_PATH", str(self.prices))):
            patcher = patch.object(v7_api_sheet, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_healthz_runs_select_1_through_runner_and_reports_snapshot_age(self):
        status, body = api.healthz(self.runner, 1_000_900)
        self.assertEqual(status, 200)
        # Tuổi theo bản cũ hơn trong hai file, như nút Làm mới.
        self.assertEqual(body, {"ok": True, "db": "ok", "sheet_snapshot_age_seconds": 900})
        self.assertEqual(self.runner.calls, [("healthz", {}, "healthz")])
        self.assertEqual(api.SQL["healthz"], "SELECT 1;")

    def test_healthz_db_failure_is_503_and_missing_snapshot_is_null(self):
        self.prices.unlink()
        status, body = api.healthz(FakeRunner(fail=True), 1_000_900)
        self.assertEqual(status, 503)
        self.assertEqual(body, {"ok": False, "db": "error", "sheet_snapshot_age_seconds": None})

    def test_healthz_db_through_psql_path_maps_failures_to_503(self):
        # Đúng PsqlDirect.run của app (bỏ qua preflight lúc khởi tạo): trả "1" là sống; exit != 0 là 503.
        direct = api.PsqlDirect.__new__(api.PsqlDirect)
        direct.psql_command, direct.socket_dir, direct.database, direct.user = (
            ["fake-client"], "/run/postgresql", "webdebit_v7", "v7_app")
        ok = Mock(returncode=0, stdout="1\n", stderr="")
        with patch.object(api.subprocess, "run", return_value=ok) as run:
            self.assertEqual(api.healthz(direct, 1_000_900)[0], 200)
        self.assertEqual(run.call_args.args[0][0], "fake-client")
        self.assertIn("SELECT 1;", run.call_args.kwargs["input"])
        broken = Mock(returncode=2, stdout="", stderr="error: connection to server failed")
        with patch.object(api.subprocess, "run", return_value=broken):
            self.assertEqual(api.healthz(direct, 1_000_900)[0], 503)
        with patch.object(api.subprocess, "run", side_effect=FileNotFoundError("no client")):
            self.assertEqual(api.healthz(direct, 1_000_900)[0], 503)

    def test_healthz_allowed_only_for_plain_loopback(self):
        plain = {"Host": "127.0.0.1:8780"}
        self.assertTrue(api.healthz_allowed("127.0.0.1", plain, 8780))
        self.assertTrue(api.healthz_allowed("::1", {"Host": "localhost:8780"}, 8780))
        for client, headers in (
            ("100.64.0.5", plain),                                              # không loopback
            ("127.0.0.1", {"Host": AUTHORITY}),                                  # đi qua Tailscale Serve
            ("127.0.0.1", plain | {"Tailscale-User-Login": "a@example.test"}),   # có danh tính
            ("127.0.0.1", plain | {"X-Forwarded-For": "100.64.0.5"}),           # qua proxy
            ("127.0.0.1", {"Host": "127.0.0.1:9999"}),                          # sai cổng
        ):
            with self.subTest(client=client, headers=headers):
                self.assertFalse(api.healthz_allowed(client, headers, 8780))

    def serve(self, runner):
        class ServeHandler(api.Handler):
            behind_tailscale_serve = True
            serve_hosts = (AUTHORITY,)
            allowed_logins = frozenset({"serve-user@example.test"})
            default_actor = None
            dev_actor_mode = False
        ServeHandler.runner = runner
        ServeHandler.localapi = self.localapi
        server = api.ThreadingHTTPServer(("127.0.0.1", 0), ServeHandler)
        ServeHandler.port = server.server_port
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()

        def stop():
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
        self.addCleanup(stop)
        return server.server_port

    def request(self, port, path, headers, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(method, path, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def test_http_healthz_loopback_without_identity_gets_200(self):
        port = self.serve(self.runner)
        status, data = self.request(port, "/healthz", {"Host": f"127.0.0.1:{port}"})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["sheet_snapshot_age_seconds"], int)
        self.localapi.whois.assert_not_called()

    def test_http_healthz_db_down_gets_503(self):
        port = self.serve(FakeRunner(fail=True))
        status, data = self.request(port, "/healthz", {"Host": f"127.0.0.1:{port}"})
        self.assertEqual((status, data["db"]), (503, "error"))

    def test_http_healthz_rejects_serve_identity_and_post(self):
        port = self.serve(self.runner)
        for method, headers in (("GET", {"Host": AUTHORITY, "Tailscale-User-Login": "serve-user@example.test"}),
                                ("GET", {"Host": f"127.0.0.1:{port}", "Tailscale-User-Login": "x@example.test"}),
                                ("POST", {"Host": f"127.0.0.1:{port}", "Content-Length": "0"})):
            with self.subTest(method=method, headers=headers):
                status, data = self.request(port, "/healthz", headers, method)
                self.assertEqual((status, data["error"]), (403, "HEALTHZ_LOOPBACK_ONLY"))
        self.assertEqual(self.runner.calls, [])

    def test_access_01_unchanged_login_outside_allowlist_still_403(self):
        port = self.serve(self.runner)
        with patch.object(sys, "stderr", io.StringIO()):
            status, data = self.request(port, "/api/v7/customers",
                                        {"Host": AUTHORITY, "Tailscale-User-Login": "stranger@example.test"})
        self.assertEqual((status, data["error"]), (403, "LOGIN_NOT_ALLOWED"))
        self.assertEqual(self.request(port, "/api/v7/customers",
                                     {"Host": AUTHORITY, "Tailscale-User-Login": "serve-user@example.test"})[0], 200)


class ClientDisconnectTest(unittest.TestCase):
    def handler(self, failure):
        handler = api.Handler.__new__(api.Handler)
        handler.command, handler.path = "GET", "/preview/v7-real-copy.html?x=1"
        handler.client_address = ("127.0.0.1", 43210)
        handler.close_connection = False
        handler._request = Mock(side_effect=failure)
        handler.reply = Mock()
        return handler

    def test_broken_pipe_and_reset_log_one_line_without_503(self):
        for failure in (BrokenPipeError(32, "Broken pipe"), ConnectionResetError(104, "Connection reset by peer")):
            with self.subTest(failure=type(failure).__name__):
                handler = self.handler(failure)
                errors = io.StringIO()
                with patch.object(sys, "stderr", errors):
                    handler.request()
                lines = errors.getvalue().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertIn(type(failure).__name__, lines[0])
                self.assertIn("/preview/v7-real-copy.html", lines[0])
                self.assertNotIn("x=1", lines[0])
                self.assertNotIn("Traceback", errors.getvalue())
                handler.reply.assert_not_called()
                self.assertTrue(handler.close_connection)

    def test_inner_handler_does_not_answer_503_on_broken_pipe(self):
        # Ghi trang tĩnh thất bại vì client đã đi: không được rơi vào nhánh OSError → 503 ASSET_UNAVAILABLE.
        handler = api.Handler.__new__(api.Handler)
        handler.command, handler.path = "GET", "/healthz"
        handler.client_address = ("127.0.0.1", 43210)
        handler.headers = http.client.parse_headers(io.BytesIO(b"Host: 127.0.0.1:8780\r\n\r\n"))
        handler.port = 8780
        handler.connection = Mock()
        handler.runner = FakeRunner()
        handler.close_connection = False
        replies = []

        def reply(status, value):
            replies.append(status)
            raise BrokenPipeError(32, "Broken pipe")
        handler.reply = reply
        errors = io.StringIO()
        with patch.object(sys, "stderr", errors):
            handler.request()
        self.assertEqual(replies, [200])
        self.assertIn("BrokenPipeError", errors.getvalue())

    def test_other_os_errors_still_answer_503(self):
        handler = self.handler(None)
        del handler._request
        handler.command, handler.path = "GET", "/healthz"
        handler.headers = http.client.parse_headers(io.BytesIO(b"Host: 127.0.0.1:8780\r\n\r\n"))
        handler.port = 8780
        handler.connection = Mock()
        handler.runner = Mock()
        with patch.object(api, "healthz", side_effect=FileNotFoundError("gone")):
            handler.request()
        handler.reply.assert_called_once()
        self.assertEqual(handler.reply.call_args.args[0], 503)


@unittest.skipIf(os.name == "nt" or not shutil.which("bash") or not shutil.which("flock"),
                 "script deploy chạy trên Linux (hao, CI ubuntu)")
class DeployAliveTest(unittest.TestCase):
    """`hao-release.sh` chỉ coi 200 từ /healthz là sống; 403 (trước đây được nhận) giờ làm quay lại bản cũ."""

    SCRIPT = ROOT.parent / "scripts" / "deploy" / "hao-release.sh"

    def run_deploy(self, healthz_code):
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        releases, stubs = directory / "releases", directory / "bin"
        releases.mkdir()
        stubs.mkdir()
        old = releases / ("a" * 40)
        old.mkdir()
        (old / ".release-sha").write_text("a" * 40 + "\n")
        current = directory / "current"
        current.symlink_to(old)
        log = directory / "curl.log"
        stub = {
            # curl ghi URL được gọi và trả mã cấu hình; chỉ /healthz được 200/503, route khác 403.
            "curl": f'#!/bin/sh\nfor a; do url=$a; done\necho "$url" >> "{log}"\n'
                    f'case $url in */healthz) printf %s "{healthz_code}";; *) printf 403;; esac\n',
            "systemctl": "#!/bin/sh\nexit 0\n",
            "sudo": "#!/bin/sh\nexit 0\n",
            "sleep": "#!/bin/sh\nexit 0\n",
        }
        for name, body in stub.items():
            (stubs / name).write_text(body)
            (stubs / name).chmod(0o755)
        conf = directory / "deploy.conf"
        conf.write_text(f'RELEASES_DIR={releases}\nCURRENT_LINK={current}\nUNIT=fake.service\n'
                        'HEALTH_URL=http://127.0.0.1:8780/api/v7/customers\n')
        package = io.BytesIO()
        with tarfile.open(fileobj=package, mode="w") as tar:
            info = tarfile.TarInfo("README")
            info.size = 2
            tar.addfile(info, io.BytesIO(b"ok"))
        result = subprocess.run(["bash", str(self.SCRIPT), "deploy", "b" * 40], input=package.getvalue(),
                                capture_output=True, timeout=60, check=False,
                                env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}",
                                     "WEBDEBIT_DEPLOY_CONF": str(conf), "SSH_ORIGINAL_COMMAND": ""})
        return result, current.resolve().name, log.read_text().split()

    def test_healthz_200_switches_release(self):
        result, running, urls = self.run_deploy(200)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(running, "b" * 40)
        self.assertEqual(set(urls), {"http://127.0.0.1:8780/healthz"})

    def test_healthz_403_or_503_rolls_back(self):
        for code in (403, 503):
            with self.subTest(code=code):
                result, running, _ = self.run_deploy(code)
                self.assertEqual(result.returncode, 5, result.stderr.decode())
                self.assertEqual(running, "a" * 40)


if __name__ == "__main__":
    unittest.main()
