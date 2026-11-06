"""Cổng ra của container Hermes: chỉ đúng tên máy trong danh sách, cổng 443, không IP."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "hermes-office"))
import egress_proxy

ALLOW = {"chatgpt.com"}


class EgressDecisionTests(unittest.TestCase):
    def test_allows_exact_host_on_443(self) -> None:
        self.assertEqual(egress_proxy.decide("CONNECT chatgpt.com:443 HTTP/1.1", ALLOW), ("chatgpt.com", 443))
        self.assertEqual(egress_proxy.decide("CONNECT ChatGPT.com:443 HTTP/1.1", ALLOW), ("chatgpt.com", 443))

    def test_refuses_everything_else(self) -> None:
        for line in ("CONNECT evil.chatgpt.com:443 HTTP/1.1", "CONNECT chatgpt.com.evil.net:443 HTTP/1.1", "CONNECT chatgpt.com:80 HTTP/1.1",
                     "CONNECT chatgpt.com:22 HTTP/1.1", "GET http://chatgpt.com/ HTTP/1.1", "CONNECT 1.1.1.1:443 HTTP/1.1", "CONNECT [::1]:443 HTTP/1.1",
                     "CONNECT hao:443 HTTP/1.1", "CONNECT chatgpt.com", ""):
            with self.subTest(line=line):
                self.assertIsNone(egress_proxy.decide(line, ALLOW))

    def test_empty_allow_list_refuses_all(self) -> None:
        self.assertIsNone(egress_proxy.decide("CONNECT chatgpt.com:443 HTTP/1.1", set()))


if __name__ == "__main__":
    unittest.main()
