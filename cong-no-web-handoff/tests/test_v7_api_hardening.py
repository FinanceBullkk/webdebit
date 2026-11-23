"""Audit 23/11/2026 (api-findings F1–F3, F5–F8, F11, F12): độ sẵn sàng của hai cổng và các lỗi nhỏ của tầng HTTP/DB.

Các phép thử F1–F3 chạy trên socket thật (loopback) với Handler thật; thời hạn được thu nhỏ bằng patch để test nhanh.
"""

import contextlib
import http.client
import io
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_book_export_rows as rows
import v7_ledger_api as api
import v7_psql
import v7_xlsx_writer as xlsx
from v7_api_validate import ApiError, validate


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor, **_):
        self.calls.append(function)
        return 1 if function == "healthz" else {"function": function}


def handler_class(**attributes):
    """Handler thử trên loopback, dev actor (không qua Serve), runner giả."""
    base = {"runner": FakeRunner(), "default_actor": "x", "dev_actor_mode": True, "behind_tailscale_serve": False,
            "serve_hosts": (), "allowed_logins": None, "admin_logins": None}
    return type("TrialHandler", (api.Handler,), base | attributes)


class ServerCase(unittest.TestCase):
    def start(self, server):
        handler = server.RequestHandlerClass
        handler.port = server.server_port
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def plain(self, handler):
        with patch.object(sys, "stderr", io.StringIO()):   # cảnh báo dev actor lúc khởi động
            server = api.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        for patcher in (patch.object(api.v7_access, "STORE", None),):
            patcher.start()
            self.addCleanup(patcher.stop)
        return self.start(server)

    def quiet(self):
        errors = io.StringIO()
        patcher = patch.object(sys, "stderr", errors)
        patcher.start()
        self.addCleanup(patcher.stop)
        return errors

    def get(self, server, path, headers=None, method="GET", body=None, timeout=5):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=timeout)
        conn.request(method, path, body=body, headers={"Host": f"127.0.0.1:{server.server_port}", **(headers or {})})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data


def find_openssl() -> str | None:
    found = shutil.which("openssl")
    git = shutil.which("git")
    if found is None and git:   # Git for Windows mang theo openssl nhưng không để trên PATH của Windows
        for candidate in (Path(git).resolve().parents[1] / "mingw64" / "bin" / "openssl.exe",
                          Path(git).resolve().parents[1] / "usr" / "bin" / "openssl.exe"):
            if candidate.exists():
                return str(candidate)
    return found


class TlsHandshakeTest(ServerCase):
    """F1: một kết nối TCP im không làm treo cổng HTTPS trực tiếp; bắt tay hỏng/quá hạn thì đóng lặng lẽ."""

    @classmethod
    def setUpClass(cls):
        openssl = find_openssl()
        if openssl is None:
            raise unittest.SkipTest("không có openssl để tạo chứng chỉ thử")
        cls.folder = tempfile.TemporaryDirectory()
        cls.cert, cls.key = (os.path.join(cls.folder.name, name) for name in ("cert.pem", "key.pem"))
        subprocess.run([openssl, "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                        "-keyout", cls.key, "-out", cls.cert, "-days", "1", "-subj", "/CN=localhost"],
                       check=True, capture_output=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def tls_server(self):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.key)
        handler = handler_class(behind_tailscale_serve=True, default_actor=None, dev_actor_mode=False,
                                allowed_logins=frozenset({"owner@example.test"}))
        # Cổng thật chỉ nhận IP tailnet; test kiểm điều kiện đó trên địa chỉ khai rồi bind loopback.
        server = api.TailnetHTTPSServer(("100.64.0.1", 0), handler, context, bind_and_activate=False)
        server.server_address = ("127.0.0.1", 0)
        server.server_bind()
        server.server_activate()
        return self.start(server)

    def https_healthz(self, server):
        context = ssl.create_default_context()
        context.check_hostname, context.verify_mode = False, ssl.CERT_NONE
        conn = http.client.HTTPSConnection("127.0.0.1", server.server_port, timeout=4, context=context)
        started = time.monotonic()
        conn.request("GET", "/healthz", headers={"Host": f"127.0.0.1:{server.server_port}"})
        response = conn.getresponse()
        body = json.loads(response.read())
        conn.close()
        return response.status, body, time.monotonic() - started

    def test_silent_connection_does_not_block_others(self):
        self.quiet()
        with patch.object(api, "TLS_HANDSHAKE_SECONDS", 1.0):
            server = self.tls_server()
            with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as silent:
                time.sleep(0.2)   # luồng nhận kết nối đã accept kết nối im
                status, body, seconds = self.https_healthz(server)
                self.assertEqual((status, body["ok"]), (200, True))
                self.assertLess(seconds, 1.0, "trước F1: chờ tới khi kết nối im tự đi")
                started = time.monotonic()
                with contextlib.suppress(ConnectionResetError):
                    self.assertEqual(silent.recv(1), b"")   # máy chủ đóng sau hạn bắt tay
                self.assertLess(time.monotonic() - started, 4)

    def test_plain_http_on_tls_port_is_closed_and_port_keeps_working(self):
        self.quiet()
        server = self.tls_server()
        with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as wrong:
            wrong.sendall(b"GET / HTTP/1.0\r\n\r\n")
            with contextlib.suppress(ConnectionResetError):
                wrong.recv(100)
        self.assertEqual(self.https_healthz(server)[0], 200)


class SlowBodyTest(ServerCase):
    """F2: thân trả lời gửi theo lát, hạn cho từng lát; client đứng im thì đóng, không trả lời lần hai."""

    def export_server(self, size):
        result = SimpleNamespace(data=b"x" * size, problems=[], books=1, filename="so-web.xlsx", header=lambda: "{}")

        class Small(handler_class()):
            def setup(self):
                super().setup()
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 32 * 1024)
        patcher = patch.object(api.v7_book_export, "export", return_value=result)
        patcher.start()
        self.addCleanup(patcher.stop)
        return self.plain(Small)

    def raw_get(self, server, path):
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024)
        sock.settimeout(10)
        sock.connect(("127.0.0.1", server.server_port))
        sock.sendall(f"GET {path} HTTP/1.0\r\nHost: 127.0.0.1:{server.server_port}\r\n\r\n".encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += sock.recv(1)
        length = int(next(line.split(b":")[1] for line in head.split(b"\r\n") if line.lower().startswith(b"content-length")))
        return sock, head, length

    def test_steady_slow_reader_gets_every_byte(self):
        self.quiet()
        size = 2 * 1024 * 1024
        with patch.object(api, "BODY_CHUNK", 64 * 1024), patch.object(api, "BODY_CHUNK_SECONDS", 0.5):
            server = self.export_server(size)
            sock, head, length = self.raw_get(server, api.EXPORT_PATH)
            started, got = time.monotonic(), 0
            with sock:
                while chunk := sock.recv(32 * 1024):
                    got += len(chunk)
                    time.sleep(0.02)
        self.assertIn(b" 200 ", head.split(b"\r\n")[0])
        self.assertEqual((length, got), (size, size))
        self.assertGreater(time.monotonic() - started, 0.5, "tổng thời gian vượt hạn một lát mà vẫn nhận đủ")

    def test_stalled_reader_is_closed_without_a_second_reply(self):
        errors = self.quiet()
        size = 32 * 1024 * 1024
        with patch.object(api, "BODY_CHUNK", 64 * 1024), patch.object(api, "BODY_CHUNK_SECONDS", 0.5):
            server = self.export_server(size)
            sock, _, length = self.raw_get(server, api.EXPORT_PATH)
            time.sleep(2.5)   # không đọc: máy chủ hết hạn một lát
            got = b""
            with sock:
                try:
                    while chunk := sock.recv(1024 * 1024):
                        got += chunk
                except (ConnectionResetError, ConnectionAbortedError):
                    pass
        self.assertLess(len(got), length)
        self.assertNotIn(b"REQUEST_TIMEOUT", got)   # không chèn JSON 408 vào giữa file
        deadline = time.monotonic() + 3
        while "bỏ dở trả lời 200" not in errors.getvalue() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIn("bỏ dở trả lời 200 GET /api/v7/xuat-so.xlsx", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())


class RequestDeadlineTest(ServerCase):
    """F3: phần đầu yêu cầu có hạn tuyệt đối; số luồng xử lý có trần."""

    def test_trickling_head_is_closed_at_the_deadline(self):
        self.quiet()
        with patch.object(api, "HEAD_SECONDS", 1.0):
            server = self.plain(handler_class())
            started = time.monotonic()
            with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as sock:
                closed = False
                for byte in b"GET /api/v7/customers HTTP/1.0\r\n":
                    try:
                        sock.sendall(bytes([byte]))
                        time.sleep(0.3)   # dưới hạn nghỉ 5 giây của mỗi lần recv
                    except OSError:
                        closed = True
                        break
                    if time.monotonic() - started > 4:
                        break
                if not closed:
                    sock.settimeout(2)
                    try:
                        closed = sock.recv(100) == b""
                    except (ConnectionResetError, ConnectionAbortedError):
                        closed = True
                    except TimeoutError:
                        closed = False
        self.assertTrue(closed)
        self.assertLess(time.monotonic() - started, 5, "trước F3: client nhỏ giọt giữ luồng mãi")

    def test_post_body_read_has_a_deadline_by_size(self):
        self.quiet()
        with patch.object(api, "HEAD_SECONDS", 0.5):
            server = self.plain(handler_class())
            with socket.create_connection(("127.0.0.1", server.server_port), timeout=5) as sock:
                sock.sendall(f"POST /api/v7/months/lock HTTP/1.0\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                             f"Origin: http://127.0.0.1:{server.server_port}\r\nContent-Type: application/json\r\n"
                             "Content-Length: 100\r\n\r\n{".encode())
                started = time.monotonic()
                data = b""
                try:
                    while chunk := sock.recv(4096):
                        data += chunk
                except (ConnectionResetError, ConnectionAbortedError):
                    pass
        self.assertIn(b" 408 ", data.split(b"\r\n")[0])
        self.assertLess(time.monotonic() - started, 3)

    def test_worker_cap(self):
        self.quiet()
        active, seen, lock = [0], [0], threading.Lock()

        class Counted(handler_class()):
            def setup(self):
                with lock:
                    active[0] += 1
                    seen[0] = max(seen[0], active[0])
                super().setup()

            def finish(self):
                try:
                    super().finish()
                finally:
                    with lock:
                        active[0] -= 1
        with patch.object(api, "WORKERS", 2), patch.object(api, "HEAD_SECONDS", 0.7):
            server = self.plain(Counted)
            idle = [socket.create_connection(("127.0.0.1", server.server_port), timeout=5) for _ in range(5)]
            try:
                status, _ = self.get(server, "/api/v7/customers", timeout=10)
            finally:
                for sock in idle:
                    sock.close()
        self.assertEqual(status, 200)
        self.assertLessEqual(seen[0], 2)


class ErrorPathTest(ServerCase):
    def test_unexpected_exception_gets_500_and_one_line(self):   # F6
        errors = self.quiet()
        server = self.plain(handler_class())
        with patch.object(api, "handle", side_effect=KeyError("rows")):
            status, data = self.get(server, "/api/v7/report/month?thang=2026-10")
        self.assertEqual(status, 500)
        self.assertEqual(json.loads(data)["error"], "INTERNAL")
        self.assertIn("lỗi bất ngờ KeyError GET /api/v7/report/month dev:x", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())
        self.assertNotIn("thang=", errors.getvalue())

    def test_cross_site_api_calls_are_refused(self):   # F7
        self.quiet()
        runner = FakeRunner()
        server = self.plain(handler_class(runner=runner))
        for value, status in (("cross-site", 403), ("same-site", 403), ("same-origin", 200), ("none", 200), (None, 200)):
            with self.subTest(value=value):
                runner.calls.clear()
                got, data = self.get(server, "/api/v7/customers", {"Sec-Fetch-Site": value} if value else {})
                self.assertEqual(got, status)
                self.assertEqual(runner.calls, [] if status == 403 else ["list_customers"])
                if status == 403:
                    self.assertEqual(json.loads(data)["error"], "CROSS_SITE")
        got, _ = self.get(server, "/healthz", {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(got, 200)   # chỉ /api/; kiểm sống có luật riêng

    def test_request_log_for_posts_and_errors_only(self):   # F11
        errors = self.quiet()
        finished = threading.Semaphore(0)

        class Watched(handler_class()):
            def finish(self):
                try:
                    super().finish()
                finally:
                    finished.release()
        server = self.plain(Watched)
        origin = {"Origin": f"http://127.0.0.1:{server.server_port}", "Content-Type": "application/json"}
        body = json.dumps({"customer_id": 1, "expected_version": 0, "idempotency_key": "log", "month": "2026-10-01",
                           "locked": True})
        # Dòng log ghi sau khi trả lời đã gửi (log_outcome có thời gian và kết cục thật của lượt), nên client nhận xong
        # trả lời có thể trước khi luồng máy chủ ghi log: chờ luồng xử lý kết thúc rồi mới gửi lượt kế và đọc stderr.
        for path, extra, method, status in (("/api/v7/customers", None, "GET", 200),
                                            ("/api/v7/months/lock", origin, "POST", 200),
                                            ("/api/v7/khong-co?customer_id=9", None, "GET", 404)):
            self.assertEqual(self.get(server, path, extra, method=method, body=body if method == "POST" else None)[0], status)
            self.assertTrue(finished.acquire(timeout=10), path)
        lines = [line for line in errors.getvalue().splitlines() if line.startswith("V7 API: ")]
        self.assertEqual(len(lines), 2, lines)
        self.assertRegex(lines[0], r"^V7 API: POST /api/v7/months/lock -> 200 dev:x \d+ ms$")
        self.assertRegex(lines[1], r"^V7 API: GET /api/v7/khong-co -> 404 dev:x \d+ ms$")
        self.assertNotIn("customer_id", errors.getvalue())


class ValidateAndExportTest(unittest.TestCase):
    """F5: ký tự điều khiển trong chữ tự do bị từ chối 422; bản xuất không bao giờ ghi ra XML hỏng hay báo lệch vì CR."""

    def test_validator_rejects_control_characters(self):
        base = {"customer_id": 1, "expected_version": 0, "idempotency_key": "v", "pid": "P1"}
        for reason in ("a\x0bb", "a\x00b", "a\x01", "a\x7f", "\x1fx"):
            with self.subTest(reason=reason), self.assertRaises(ApiError) as caught:
                validate("/api/v7/receipts/void", json.dumps(base | {"reason": reason}).encode())
            self.assertEqual(caught.exception.status, 422)
        function, payload = validate("/api/v7/receipts/void", json.dumps(base | {"reason": "dòng 1\ndòng 2\tcột\r\n"}).encode())
        self.assertEqual((function, payload["reason"]), ("void_receipt", "dòng 1\ndòng 2\tcột\r\n"))

    def test_workbook_round_trip_with_control_characters(self):
        sheet = xlsx.Sheet("A", [("Cột", "text", 10)], [["x\r\ny"], ["a\x0bb\x01"], [xlsx.Styled("c\rd", "bold")]])
        data = xlsx.write_workbook([sheet])
        back = xlsx.read_workbook(data)["A"]
        self.assertEqual(back, [["Cột"], ["x\ny"], ["ab"], ["c\nd"]])
        self.assertEqual(back, xlsx.plain_rows(sheet))   # bản tự kiểm của XUAT-SO-01 không còn báo lệch

    def test_void_reason_is_cleaned(self):
        self.assertEqual(rows._void(True, "khách\x0b trả\r\nlại"), "Đã hủy: khách trả\nlại")
        self.assertEqual(rows._void(True, ""), "Đã hủy")
        self.assertIsNone(rows._void(False, "x"))


class PsqlTest(unittest.TestCase):
    """F12: payload là hằng dollar-quote trong SQL gửi qua stdin; F3: tối đa DB_SLOTS tiến trình psql; F11: log SQLSTATE."""

    class Runner(v7_psql._PsqlRunner):
        def _argv(self):
            return ["fake-db-client"]

    def test_literal_tag_never_appears_in_text(self):
        with patch.object(v7_psql.secrets, "token_hex", side_effect=["a" * 16, "b" * 16, "c" * 16]):
            text = "x $v7_" + "a" * 16 + "$ y $v7_" + "b" * 16   # thẻ thứ hai chỉ thiếu dấu $ cuối
            self.assertEqual(v7_psql.sql_literal(text), "$v7_" + "c" * 16 + "$" + text + "$v7_" + "c" * 16 + "$")

    def test_payload_replaces_every_variable_and_never_goes_to_argv(self):
        payload = {"reason": "a' $$ :'actor' \\! `x`", "big": "z" * 200_000}
        with patch.object(v7_psql.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, "{}", "")) as command:
            self.Runner().run("get_receipt_image", payload | {"customer_id": 1, "image_id": 2}, "nguoi-xem")
        args, sql = command.call_args.args[0], command.call_args.kwargs["input"]
        self.assertEqual(args, ["fake-db-client", "-v", "actor=nguoi-xem"])
        self.assertNotIn(":'payload'", sql)
        self.assertEqual(sql.count("z" * 200_000), 2)   # hai chỗ dùng payload trong câu

    def test_db_slots_queue_then_refuse(self):
        slots = v7_psql.threading.BoundedSemaphore(1)
        with patch.object(v7_psql, "DB_SLOTS", slots), patch.object(v7_psql, "DB_WAIT_SECONDS", 0.05), \
                patch.object(sys, "stderr", io.StringIO()), \
                patch.object(v7_psql.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "{}", "")) as command:
            slots.acquire()
            with self.assertRaises(ApiError) as caught:
                self.Runner().run("get_reminders", {}, "a")
            self.assertEqual((caught.exception.status, caught.exception.code), (503, "DB_BUSY"))
            command.assert_not_called()
            slots.release()
            self.assertEqual(self.Runner().run("get_reminders", {}, "a"), {})
            command.side_effect = subprocess.TimeoutExpired([], 25)
            with self.assertRaises(ApiError):
                self.Runner().run("get_reminders", {}, "a")
            self.assertTrue(slots.acquire(blocking=False), "chỗ được trả lại cả khi psql quá giờ")
            slots.release()

    def test_unmapped_failure_logs_sqlstate_only(self):
        for stderr, expected in (
                ("psql:<stdin>:3: ERROR:  22P05: unsupported Unicode escape sequence\nDETAIL: tên khách\n", "SQLSTATE 22P05"),
                ("psql:<stdin>:3: ERROR:  P0001: SOMETHING_NEW\n", "SQLSTATE P0001 SOMETHING_NEW"),
                ("psql: error: connection to server failed\n", "psql: error: connection to server failed")):
            errors = io.StringIO()
            with self.subTest(expected=expected), patch.object(sys, "stderr", errors), \
                    patch.object(v7_psql.subprocess, "run", return_value=subprocess.CompletedProcess([], 3, "", stderr)), \
                    self.assertRaises(ApiError) as caught:
                self.Runner().run("get_reminders", {}, "a")
            self.assertEqual(caught.exception.code, "DB_UNAVAILABLE")
            self.assertEqual(errors.getvalue(), f"V7 API: psql lỗi get_reminders: {expected}\n")


if __name__ == "__main__":
    unittest.main()
