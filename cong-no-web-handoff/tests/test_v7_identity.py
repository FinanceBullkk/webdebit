"""Offline V7 identity boundary checks; all LocalAPI responses are fake."""

import io
import json
import sys
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_identity as identity


class FakeLocalAPI:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def whois(self, addr):
        self.calls.append(addr)
        if self.error is not None:
            raise self.error
        return self.result


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeLocalAPI({"UserProfile": {"LoginName": " User@EXAMPLE.TEST "}})

    def assert_code(self, code, call):
        with self.assertRaises(identity.IdentityError) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def test_valid_whois_normalizes_domain_only(self):
        self.assertEqual(identity.resolve_actor("100.101.102.103", {}, self.client,
                                                source_port=43210), "User@example.test")
        self.assertEqual(self.client.calls, ["100.101.102.103:43210"])

    def test_spoofed_header_ignored_by_default(self):
        headers = {"Tailscale-User-Login": "attacker@example.test"}
        self.assertEqual(identity.resolve_actor("100.101.102.103", headers, self.client),
                         "User@example.test")
        self.assertEqual(len(self.client.calls), 1)

    def test_non_loopback_header_ignored_even_with_serve(self):
        for ip in ("100.101.102.103", "192.0.2.1", "127.0.0.2", "::ffff:127.0.0.1"):
            with self.subTest(ip=ip):
                self.assertEqual(identity.resolve_actor(
                    ip, {"Tailscale-User-Login": "attacker@example.test"}, self.client,
                    behind_tailscale_serve=True), "User@example.test")
        self.assertEqual(len(self.client.calls), 4)

    def test_serve_header_from_both_loopbacks(self):
        for ip in ("127.0.0.1", "::1"):
            with self.subTest(ip=ip):
                self.assertEqual(identity.resolve_actor(
                    ip, {"tAiLsCaLe-UsEr-LoGiN": " Served@EXAMPLE.TEST "}, self.client,
                    behind_tailscale_serve=True), "Served@example.test")
        self.assertEqual(self.client.calls, [])

    def test_loopback_header_requires_explicit_serve_mode(self):
        self.assertEqual(identity.resolve_actor(
            "127.0.0.1", {"Tailscale-User-Login": "attacker@example.test"}, self.client),
            "User@example.test")
        self.assertEqual(len(self.client.calls), 1)

    def test_forwarded_ip_cannot_enable_header_trust(self):
        headers = {"Tailscale-User-Login": "attacker@example.test",
                   "X-Forwarded-For": "127.0.0.1", "Forwarded": "for=127.0.0.1"}
        self.assertEqual(identity.resolve_actor("192.0.2.1", headers, self.client,
                                                behind_tailscale_serve=True),
                         "User@example.test")

    def test_timeout_and_localapi_failure_have_no_fallback(self):
        for error, code in ((TimeoutError(), "LOCALAPI_TIMEOUT"),
                            (OSError(), "LOCALAPI_ERROR"),
                            (identity.IdentityError("NOT_TAILNET"), "NOT_TAILNET")):
            with self.subTest(code=code):
                client = FakeLocalAPI(error=error)
                self.assert_code(code, lambda client=client: identity.resolve_actor(
                    "192.0.2.1", {"Tailscale-User-Login": "attacker@example.test"}, client,
                    behind_tailscale_serve=True))

    def test_missing_user_and_malformed_response(self):
        for result in ({}, {"UserProfile": None}, {"UserProfile": {}}):
            with self.subTest(result=result):
                self.assert_code("NO_USER", lambda result=result: identity.resolve_actor(
                    "100.101.102.103", {}, FakeLocalAPI(result)))
        for result in (None, [], {"UserProfile": "wrong"}):
            with self.subTest(result=result):
                self.assert_code("LOCALAPI_INVALID_RESPONSE", lambda result=result: identity.resolve_actor(
                    "100.101.102.103", {}, FakeLocalAPI(result)))

    def test_empty_and_invalid_login_from_both_sources(self):
        for login, code in (("", "EMPTY_LOGIN"), ("   ", "EMPTY_LOGIN"),
                            (None, "INVALID_LOGIN"), (42, "INVALID_LOGIN")):
            with self.subTest(login=login):
                client = FakeLocalAPI({"UserProfile": {"LoginName": login}})
                self.assert_code(code, lambda client=client: identity.resolve_actor("100.101.102.103", {}, client))
                self.assert_code(code, lambda login=login: identity.resolve_actor(
                    "::1", {"Tailscale-User-Login": login}, self.client,
                    behind_tailscale_serve=True))

    def test_control_characters_rejected_before_trimming(self):
        for char in ("\0", "\r", "\n", "\t", "\x7f", "\x85", "\u202e"):
            for login in (char + "user@example.test", "user" + char + "@example.test"):
                with self.subTest(login=repr(login)):
                    self.assert_code("INVALID_LOGIN", lambda login=login: identity.resolve_actor(
                        "100.101.102.103", {}, FakeLocalAPI({"UserProfile": {"LoginName": login}})))
                    self.assert_code("INVALID_LOGIN", lambda login=login: identity.resolve_actor(
                        "127.0.0.1", {"Tailscale-User-Login": login}, self.client,
                        behind_tailscale_serve=True))

    def test_duplicate_serve_header_rejected(self):
        headers = Message()
        headers["Tailscale-User-Login"] = "first@example.test"
        headers["tailscale-user-login"] = "second@example.test"
        self.assert_code("AMBIGUOUS_LOGIN", lambda: identity.resolve_actor(
            "::1", headers, self.client, behind_tailscale_serve=True))

    def test_missing_serve_header_uses_whois(self):
        self.assertEqual(identity.resolve_actor("::1", {}, self.client,
                                                behind_tailscale_serve=True), "User@example.test")
        self.assertEqual(self.client.calls, ["[::1]:0"])

    def test_ipv6_whois_address(self):
        identity.resolve_actor("fd7a:115c:a1e0::1234", {}, self.client, source_port=12345)
        self.assertEqual(self.client.calls, ["[fd7a:115c:a1e0::1234]:12345"])

    def test_invalid_peer_and_config_fail_before_lookup(self):
        for ip in ("localhost", "127.0.0.1:80", "127.0.0.1\n", "::1%lo", ""):
            with self.subTest(ip=ip):
                self.assert_code("INVALID_SOURCE", lambda ip=ip: identity.resolve_actor(ip, {}, self.client))
        for port in (-1, 65536, "80", True):
            with self.subTest(port=port):
                self.assert_code("INVALID_SOURCE", lambda port=port: identity.resolve_actor(
                    "127.0.0.1", {}, self.client, source_port=port))
        self.assert_code("INVALID_CONFIG", lambda: identity.resolve_actor(
            "127.0.0.1", {}, self.client, behind_tailscale_serve="false"))
        self.assertEqual(self.client.calls, [])

    def test_default_client_is_used(self):
        with patch.object(identity, "TailscaleLocalAPI", return_value=self.client):
            self.assertEqual(identity.resolve_actor("100.101.102.103", {}), "User@example.test")


class AllowlistTest(unittest.TestCase):
    """ACCESS-01: only configured logins may act; None keeps the pre-allowlist behaviour."""

    def setUp(self):
        self.client = FakeLocalAPI({"UserProfile": {"LoginName": "Owner@EXAMPLE.TEST"}})

    def test_parse_allowed_logins(self):
        self.assertIsNone(identity.parse_allowed_logins(None))
        self.assertEqual(identity.parse_allowed_logins(""), frozenset())
        self.assertEqual(identity.parse_allowed_logins(" , \n"), frozenset())
        self.assertEqual(identity.parse_allowed_logins("A@EXAMPLE.TEST,b@example.test  c@Example.Test\n"),
                         frozenset({"A@example.test", "b@example.test", "c@example.test"}))
        for value, code in ((42, "INVALID_CONFIG"), ("ok@example.test,\x7fbad@example.test", "INVALID_LOGIN")):
            with self.subTest(value=value), self.assertRaises(identity.IdentityError) as caught:
                identity.parse_allowed_logins(value)
            self.assertEqual(caught.exception.code, code)

    def test_whois_login_outside_allowlist_fails_closed(self):
        with self.assertRaises(identity.IdentityError) as caught:
            identity.resolve_actor("100.101.102.103", {}, self.client, source_port=1,
                                   allowed_logins=frozenset({"someone-else@example.test"}))
        self.assertEqual((caught.exception.code, caught.exception.detail), ("LOGIN_NOT_ALLOWED", "Owner@example.test"))
        self.assertEqual(str(caught.exception), "LOGIN_NOT_ALLOWED")  # response text never carries the login

    def test_serve_header_login_outside_allowlist_fails_closed(self):
        headers = {"Tailscale-User-Login": "stranger@example.test"}
        with self.assertRaises(identity.IdentityError) as caught:
            identity.resolve_actor("127.0.0.1", headers, self.client, behind_tailscale_serve=True,
                                   allowed_logins=frozenset({"Owner@example.test"}))
        self.assertEqual((caught.exception.code, caught.exception.detail), ("LOGIN_NOT_ALLOWED", "stranger@example.test"))
        self.assertEqual(self.client.calls, [])

    def test_allowed_login_passes_after_normalization(self):
        allowed = frozenset({"Owner@example.test"})
        self.assertEqual(identity.resolve_actor("100.101.102.103", {}, self.client, allowed_logins=allowed),
                         "Owner@example.test")
        self.assertEqual(identity.resolve_actor("::1", {"Tailscale-User-Login": " Owner@EXAMPLE.test "}, self.client,
                                                behind_tailscale_serve=True, allowed_logins=allowed), "Owner@example.test")

    def test_empty_allowlist_denies_everyone_and_none_allows_any_verified_login(self):
        with self.assertRaises(identity.IdentityError) as caught:
            identity.resolve_actor("100.101.102.103", {}, self.client, allowed_logins=frozenset())
        self.assertEqual(caught.exception.code, "LOGIN_NOT_ALLOWED")
        self.assertEqual(identity.resolve_actor("100.101.102.103", {}, self.client, allowed_logins=None),
                         "Owner@example.test")

    def test_allowlist_must_be_a_frozenset(self):
        for value in ({"a@example.test"}, ["a@example.test"], "a@example.test"):
            with self.subTest(value=value), self.assertRaises(identity.IdentityError) as caught:
                identity.resolve_actor("100.101.102.103", {}, self.client, allowed_logins=value)
            self.assertEqual(caught.exception.code, "INVALID_CONFIG")
        self.assertEqual(self.client.calls, [])


class LocalAPITransportTest(unittest.TestCase):
    def test_http_request_and_response_errors_without_io(self):
        cases = ((200, b'{"UserProfile":{"LoginName":"user@example.test"}}', None),
                 (404, b"", "NOT_TAILNET"), (500, b"", "LOCALAPI_ERROR"),
                 (200, b"not json", "LOCALAPI_INVALID_RESPONSE"),
                 (200, b"[]", "LOCALAPI_INVALID_RESPONSE"),
                 (200, b" " * (identity.MAX_RESPONSE + 1), "LOCALAPI_INVALID_RESPONSE"))
        for status, body, code in cases:
            with self.subTest(status=status, code=code):
                connection = Mock()
                response = io.BytesIO(body)
                response.status = status
                connection.getresponse.return_value = response
                with patch.object(identity, "_LocalConnection", return_value=connection):
                    client = identity.TailscaleLocalAPI()
                    if code:
                        with self.assertRaises(identity.IdentityError) as caught:
                            client.whois("[fd7a::1]:1234")
                        self.assertEqual(caught.exception.code, code)
                    else:
                        self.assertEqual(client.whois("[fd7a::1]:1234")["UserProfile"]["LoginName"],
                                         "user@example.test")
                    self.assertEqual(connection.request.call_args.args[:2],
                                     ("GET", "/localapi/v0/whois?addr=%5Bfd7a%3A%3A1%5D%3A1234"))
                    connection.close.assert_called_once()

    def test_unix_socket_connect_and_cleanup(self):
        with (patch.object(identity.os, "name", "posix"),
              patch.object(identity.socket, "AF_UNIX", 1, create=True),
              patch.object(identity.socket, "socket") as factory):
            connection = identity._LocalConnection("/fake/tailscaled.sock", 1.5)
            connection.connect()
            factory.return_value.settimeout.assert_called_once_with(1.5)
            factory.return_value.connect.assert_called_once_with("/fake/tailscaled.sock")
            connection.close()
            factory.return_value.close.assert_called_once()

    def test_windows_pipe_selected_without_opening_it(self):
        with patch.object(identity.os, "name", "nt"), patch.object(identity, "_PipeSocket") as pipe:
            connection = identity._LocalConnection(None, 2)
            connection.connect()
            pipe.assert_called_once_with(r"\\.\pipe\ProtectedPrefix\Administrators\Tailscale\tailscaled", 2)
            connection.close()

    def test_windows_overlapped_pipe_io_and_timeout(self):
        operation = Mock(event=99)
        operation.GetOverlappedResult.return_value = (3, 0)
        operation.getbuffer.return_value = b"abc"
        winapi = SimpleNamespace(
            CreateFile=Mock(return_value=10), CloseHandle=Mock(),
            WriteFile=Mock(return_value=(operation, 997)),
            ReadFile=Mock(return_value=(operation, 997)),
            WaitForSingleObject=Mock(return_value=0))
        with patch.dict(sys.modules, {"_winapi": winapi}):
            pipe = identity._PipeSocket(r"\\.\pipe\fake", 1)
            pipe.sendall(b"abc")
            buffer = bytearray(3)
            self.assertEqual(pipe.readinto(buffer), 3)
            self.assertEqual(buffer, b"abc")
            self.assertEqual(winapi.WriteFile.call_args.args, (10, b"abc", True))
            winapi.WaitForSingleObject.return_value = 258
            with self.assertRaises(TimeoutError):
                pipe.readinto(buffer)
            operation.cancel.assert_called_once()
            pipe.close()
            pipe.close()
            winapi.CloseHandle.assert_called_once_with(10)

    def test_full_http_over_fake_windows_pipe(self):
        body = json.dumps({"UserProfile": {"LoginName": "User@EXAMPLE.TEST"}}).encode()
        for framing in (b"Content-Length: " + str(len(body)).encode(), b"Transfer-Encoding: chunked"):
            with self.subTest(framing=framing):
                payload = (f"{len(body):x}\r\n".encode() + body + b"\r\n0\r\n\r\n"
                           if b"chunked" in framing else body)
                response = io.BytesIO(b"HTTP/1.1 200 OK\r\nConnection: close\r\n" + framing + b"\r\n\r\n" + payload)

                def operation(data):
                    return SimpleNamespace(GetOverlappedResult=lambda wait: (len(data), 0),
                                           getbuffer=lambda: data), 0

                winapi = SimpleNamespace(
                    CreateFile=Mock(return_value=10), CloseHandle=Mock(),
                    WriteFile=Mock(side_effect=lambda handle, data, overlapped: operation(data)),
                    ReadFile=Mock(side_effect=lambda handle, size, overlapped, response=response: operation(response.read(size))))
                with patch.dict(sys.modules, {"_winapi": winapi}), patch.object(identity.os, "name", "nt"):
                    self.assertEqual(identity.resolve_actor("100.101.102.103", {}), "User@example.test")
                self.assertIn(b"GET /localapi/v0/whois?addr=100.101.102.103%3A0 HTTP/1.1\r\n",
                              winapi.WriteFile.call_args.args[1])
                winapi.CloseHandle.assert_called_once_with(10)


if __name__ == "__main__":
    unittest.main()
