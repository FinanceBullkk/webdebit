"""Audit 23/11/2026 (F4): ở chế độ Serve, header `Tailscale-User-Login` chỉ được tin khi socket client loopback thuộc
tailscaled (uid 0, tra /proc/net/tcp*), hoặc thuộc uid khai là "chỉ đọc" (bot Zalo) và yêu cầu là GET.

Phần /proc dùng file giả nên chạy cả trên Windows; phép thử socket thật chỉ chạy trên Linux (CI ubuntu, hao).
"""

import http.client
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_identity as identity
import v7_ledger_api as api

HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
LOGIN = "owner@example.test"
ALLOWED = frozenset({LOGIN})


def v4(ip: str, port: int) -> str:
    """Địa chỉ như kernel little-endian in trong /proc/net/tcp."""
    return bytes(reversed(socket.inet_aton(ip))).hex().upper() + f":{port:04X}"


def row(local: str, remote: str, state: str = "01", uid: int = 0, inode: int = 4242) -> str:
    return f"   0: {local} {remote} {state} 00000000:00000000 00:00000000 00000000 {uid:>5} 0 {inode} 1 0000 20 4 30 10 -1\n"


@unittest.skipUnless(sys.byteorder == "little", "bảng /proc giả viết theo máy little-endian (x86, như hao)")
class ProcTableTest(unittest.TestCase):
    def table(self, tcp: str, tcp6: str = "") -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        paths = (os.path.join(folder.name, "tcp"), os.path.join(folder.name, "tcp6"))
        for path, body in zip(paths, (tcp, tcp6), strict=True):
            Path(path).write_text(HEADER + body, encoding="ascii")
        patcher = patch.object(identity, "PROC_NET", paths)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_owner_of_the_client_socket(self):
        # Hai đầu của cùng kết nối đều có trong bảng: dòng của máy chủ (local 8780) thuộc uid của API, không được lấy nhầm.
        self.table(row(v4("127.0.0.1", 8780), v4("127.0.0.1", 50000), uid=998)
                   + row(v4("127.0.0.1", 50000), v4("127.0.0.1", 8780), uid=0)
                   + row(v4("127.0.0.1", 50001), v4("127.0.0.1", 8780), uid=1001))
        self.assertEqual(identity.loopback_peer_uid("127.0.0.1", 50000, 8780), 0)
        self.assertEqual(identity.loopback_peer_uid("127.0.0.1", 50001, 8780), 1001)

    def test_unknown_closed_or_wrong_port_is_none(self):
        self.table(row(v4("127.0.0.1", 50000), v4("127.0.0.1", 8780), state="04", uid=0)          # FIN_WAIT1
                   + row(v4("127.0.0.1", 50001), v4("127.0.0.1", 8780), uid=0, inode=0)          # mồ côi: uid 0 giả
                   + row(v4("127.0.0.1", 50002), v4("127.0.0.1", 9999), uid=0)                   # cổng khác
                   + row(v4("100.101.102.103", 50003), v4("127.0.0.1", 8780), uid=0)             # không phải loopback
                   + "garbage line\n")
        for port in (50000, 50001, 50002, 50003, 50004):
            with self.subTest(port=port):
                self.assertIsNone(identity.loopback_peer_uid("127.0.0.1", port, 8780))
        self.assertIsNone(identity.loopback_peer_uid("not-an-ip", 50000, 8780))

    def test_ipv6_loopback(self):
        loop6 = "00000000000000000000000001000000"   # ::1 theo từng từ 32 bit little-endian
        self.table("", row(f"{loop6}:C350", f"{loop6}:224C", uid=0))
        self.assertEqual(identity.loopback_peer_uid("::1", 50000, 8780), 0)

    def test_missing_proc_is_none(self):
        with patch.object(identity, "PROC_NET", ("/khong/co/tcp", "/khong/co/tcp6")):
            self.assertIsNone(identity.loopback_peer_uid("127.0.0.1", 50000, 8780))


@unittest.skipUnless(os.path.exists("/proc/net/tcp") and hasattr(os, "getuid"), "chỉ Linux có /proc/net/tcp")
class RealProcTest(unittest.TestCase):
    def test_finds_own_uid_for_a_real_loopback_connection(self):
        with socket.create_server(("127.0.0.1", 0)) as server, socket.create_connection(server.getsockname()):
            accepted, peer = server.accept()
            with accepted:
                uid = identity.loopback_peer_uid(peer[0], peer[1], server.getsockname()[1])
        self.assertEqual(uid, os.getuid())


class ResolveTest(unittest.TestCase):
    def resolve(self, uid, *, write=False, read_only=frozenset(), allowed=ALLOWED, login=LOGIN):
        localapi = Mock()
        with patch.object(identity, "loopback_peer_uid", return_value=uid) as lookup:
            try:
                return identity.resolve_actor("127.0.0.1", {"Tailscale-User-Login": login}, localapi, source_port=50000,
                                              behind_tailscale_serve=True, allowed_logins=allowed, local_port=8780,
                                              read_only_uids=read_only, write=write)
            finally:
                lookup.assert_called_once_with("127.0.0.1", 50000, 8780)
                localapi.whois.assert_not_called()   # header có mặt: không rơi sang whois

    def test_tailscaled_reads_and_writes(self):
        self.assertEqual(self.resolve(0), LOGIN)
        self.assertEqual(self.resolve(0, write=True), LOGIN)

    def test_other_local_process_is_refused(self):
        for uid in (1001, None):
            with self.subTest(uid=uid), self.assertRaises(identity.IdentityError) as caught:
                self.resolve(uid)
            self.assertEqual((caught.exception.code, caught.exception.detail), ("UNTRUSTED_LOCAL_PEER", f"uid {uid}"))

    def test_read_only_peer_gets_only_reads(self):
        self.assertEqual(self.resolve(1001, read_only=frozenset({1001})), LOGIN)
        with self.assertRaises(identity.IdentityError) as caught:
            self.resolve(1001, write=True, read_only=frozenset({1001}))
        self.assertEqual(caught.exception.code, "READ_ONLY_PEER")
        with self.assertRaises(identity.IdentityError) as caught:   # danh sách login vẫn áp dụng cho bot
            self.resolve(1001, read_only=frozenset({1001}), login="stranger@example.test")
        self.assertEqual(caught.exception.code, "LOGIN_NOT_ALLOWED")

    def test_no_header_still_goes_to_whois(self):
        localapi = Mock()
        localapi.whois.side_effect = identity.IdentityError("NOT_TAILNET")
        with patch.object(identity, "loopback_peer_uid") as lookup, self.assertRaises(identity.IdentityError) as caught:
            identity.resolve_actor("127.0.0.1", {}, localapi, source_port=50000, behind_tailscale_serve=True,
                                   allowed_logins=ALLOWED, local_port=8780)
        self.assertEqual(caught.exception.code, "NOT_TAILNET")
        lookup.assert_not_called()

    def test_bad_config_types(self):
        for options in ({"write": 1}, {"read_only_uids": {1001}}):
            with self.subTest(options=options), self.assertRaises(identity.IdentityError):
                identity.resolve_actor("127.0.0.1", {}, Mock(), behind_tailscale_serve=True, **options)

    def test_parse_peer_uids(self):
        self.assertEqual(identity.parse_peer_uids(None), frozenset())
        self.assertEqual(identity.parse_peer_uids(" 1001, 1002 1001 "), frozenset({1001, 1002}))
        for value in ("0", "1001,0", "-5", "abc", "1.5", "١٢", 1001):
            with self.subTest(value=value), self.assertRaises(identity.IdentityError):
                identity.parse_peer_uids(value)


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, function, payload, actor, **_):
        self.calls.append((function, actor))
        return {"function": function, "actor": actor}


class HttpPeerTest(unittest.TestCase):
    """Qua socket thật tới Handler: tiến trình cục bộ không phải tailscaled bị chặn trước mọi lần gọi DB, uid vào journal."""

    AUTHORITY = "congno.example.test:8443"

    def serve(self, uid, read_only=frozenset()):
        runner = FakeRunner()

        class PeerHandler(api.Handler):
            behind_tailscale_serve = True
            serve_hosts = (self.AUTHORITY,)
            allowed_logins = ALLOWED
            admin_logins = ALLOWED
            read_only_uids = read_only
            default_actor = None
            dev_actor_mode = False
        PeerHandler.runner = runner
        server = api.ThreadingHTTPServer(("127.0.0.1", 0), PeerHandler)
        PeerHandler.port = server.server_port
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        for patcher in (patch.object(api.v7_access, "STORE", None), patch.object(identity, "loopback_peer_uid", return_value=uid)):
            patcher.start()
            self.addCleanup(patcher.stop)
        return server, runner

    def call(self, server, method):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        headers = {"Host": self.AUTHORITY, "Tailscale-User-Login": LOGIN}
        body = None
        if method == "POST":
            body = json.dumps({"customer_id": 1, "expected_version": 0, "idempotency_key": "peer", "month": "2026-10-01",
                               "locked": True})
            headers |= {"Origin": f"https://{self.AUTHORITY}", "Content-Type": "application/json"}
        conn.request(method, "/api/v7/months/lock" if method == "POST" else "/api/v7/customers", body=body, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def test_untrusted_local_process_gets_403_and_journal_line(self):
        server, runner = self.serve(uid=1001)
        errors = io.StringIO()
        with patch.object(sys, "stderr", errors):
            for method in ("GET", "POST"):
                self.assertEqual(self.call(server, method), (403, {"error": "UNTRUSTED_LOCAL_PEER"}))
        self.assertEqual(runner.calls, [])
        self.assertIn("UNTRUSTED_LOCAL_PEER, uid 1001", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())

    def test_read_only_peer_reads_but_cannot_write(self):
        server, runner = self.serve(uid=1001, read_only=frozenset({1001}))
        with patch.object(sys, "stderr", io.StringIO()):
            status, data = self.call(server, "GET")
            self.assertEqual((status, data["actor"]), (200, LOGIN))
            self.assertEqual(self.call(server, "POST"), (403, {"error": "READ_ONLY_PEER"}))
        self.assertEqual(runner.calls, [("list_customers", LOGIN)])

    def test_tailscaled_writes(self):
        server, runner = self.serve(uid=0)
        with patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(self.call(server, "POST")[0], 200)
        self.assertEqual(runner.calls, [("set_month_lock", LOGIN)])


class CliTest(unittest.TestCase):
    def test_read_only_uid_flag_and_env(self):
        saved = {name: value for name, value in vars(api.Handler).items() if not name.startswith("__")}
        self.addCleanup(lambda: [setattr(api.Handler, name, value) for name, value in saved.items()])
        self.addCleanup(setattr, api.v7_access, "STORE", api.v7_access.STORE)
        base = ["api", "--container", "fake", "--behind-tailscale-serve", "--allowed-login", LOGIN]
        with patch.dict(os.environ, {"WEBDEBIT_READ_ONLY_PEER_UIDS": "1002"}, clear=True), \
                patch.object(sys, "argv", [*base, "--read-only-peer-uid", "1001"]), patch.object(api, api.Psql.__name__), \
                patch.object(api, "ThreadingHTTPServer"), patch.object(api.INBOX, "start"), \
                patch.object(api.INBOX, "keep_fresh"), patch.object(api.v7_nhat_ky, "journal"), \
                patch.object(api.v7_telegram, "start"), patch.object(api.v7_zalo_chat, "warm"):
            api.main()
        self.assertEqual(api.Handler.read_only_uids, frozenset({1001, 1002}))
        for argv in ([*base, "--read-only-peer-uid", "0"], [*base, "--read-only-peer-uid", "bot"],
                     ["api", "--container", "fake", "--read-only-peer-uid", "1001"]):
            with self.subTest(argv=argv), patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", argv), \
                    patch.object(api, api.Psql.__name__) as runner, patch.object(sys, "stderr", io.StringIO()), \
                    self.assertRaises(SystemExit):
                api.main()
            runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
