"""Direct HTTPS listener stays on the current Tailscale node and keeps actor checks."""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_identity as identity
import v7_ledger_api as api


class TailnetHttpsTest(unittest.TestCase):
    def test_https_listener_rejects_public_bind(self):
        with patch.object(api.Handler, "default_actor", None), \
                patch.object(api.Handler, "dev_actor_mode", False), \
                patch.object(api.Handler, "behind_tailscale_serve", True), \
                self.assertRaises(ValueError):
            api.ThreadingHTTPServer(("0.0.0.0", 8445), api.Handler, tailnet_https=True)

    def test_direct_peer_uses_whois_not_client_identity_header(self):
        localapi = Mock()
        localapi.whois.return_value = {"UserProfile": {"LoginName": "owner@example.test"}}
        actor = identity.resolve_actor("100.101.102.200", {"Tailscale-User-Login": "forged@example.test"},
                                       localapi, source_port=41321, behind_tailscale_serve=True,
                                       allowed_logins=frozenset({"owner@example.test"}))
        self.assertEqual(actor, "owner@example.test")
        localapi.whois.assert_called_once_with("100.101.102.200:41321")

    def test_rejects_incomplete_or_wrong_node_configuration(self):
        runner_name = api.Psql.__name__
        base = ["api", "--container", "fake", "--behind-tailscale-serve",
                "--serve-host", "congno.example.test:8445", "--allowed-login", "owner@example.test"]
        for extra in (["--tailnet-https-ip", "100.101.102.103"],
                      ["--tailnet-https-ip", "100.101.102.104", "--tailnet-tls-cert", "cert",
                       "--tailnet-tls-key", "key", "--tailnet-https-host", "congno.example.test:8445"],
                      ["--tailnet-https-ip", "100.101.102.103", "--tailnet-tls-cert", "cert",
                       "--tailnet-tls-key", "key", "--tailnet-https-host", "congno.example.test:8443"]):
            with self.subTest(extra=extra), patch.dict(os.environ, {}, clear=True), \
                    patch.object(sys, "argv", base + extra), patch.object(api, runner_name), \
                    patch.object(api.subprocess, "run",
                                 return_value=Mock(stdout="100.101.102.103\n")), \
                    self.assertRaises(SystemExit):
                api.main()

    def test_starts_second_tls_listener_with_same_handler(self):
        runner_name = api.Psql.__name__
        args = ["api", "--container", "fake", "--behind-tailscale-serve",
                "--serve-host", "congno.example.test:8445", "--allowed-login", "owner@example.test",
                "--tailnet-https-ip", "100.101.102.103", "--tailnet-https-port", "8445",
                "--tailnet-tls-cert", "cert", "--tailnet-tls-key", "key",
                "--tailnet-https-host", "congno.example.test:8445"]
        secure = Mock(socket=Mock())
        raw_socket = secure.socket
        plain = Mock()
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", args), \
                patch.object(api, runner_name), \
                patch.object(api.subprocess, "run",
                    return_value=subprocess.CompletedProcess([], 0, "100.101.102.103\n")), \
                patch.object(api, "ThreadingHTTPServer", side_effect=[secure, plain]) as server, \
                patch.object(api.ssl, "SSLContext") as context, patch.object(api.threading, "Thread") as thread, \
                patch.object(api.Handler, "serve_hosts", ()), \
                patch.object(api.INBOX, "start"), patch.object(api.INBOX, "keep_fresh"), \
                patch.object(api.v7_zalo_chat, "warm"):
            api.main()
            self.assertIn("congno.example.test:8445", api.Handler.serve_hosts)
        self.assertEqual(server.call_args_list[0].args[:2], (("100.101.102.103", 8445), api.Handler))
        self.assertEqual(server.call_args_list[0].kwargs, {"tailnet_https": True})
        self.assertEqual(server.call_args_list[1].args[:2], (("127.0.0.1", 8780), api.Handler))
        context.return_value.load_cert_chain.assert_called_once_with("cert", "key")
        context.return_value.wrap_socket.assert_called_once_with(raw_socket, server_side=True)
        thread.return_value.start.assert_called_once()
        plain.serve_forever.assert_called_once()


if __name__ == "__main__":
    unittest.main()
