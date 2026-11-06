#!/usr/bin/env python3
"""Cổng ra duy nhất của container Hermes: chỉ cho CONNECT tới đúng máy chủ model, cổng 443 (MAY-CHAY-01).

Hermes nằm trên mạng internal không có đường ra; tiến trình này đứng ở cả hai mạng. Không đọc được nội dung vì chỉ chuyển TLS. Log chỉ có
tên máy và quyết định.
"""

from __future__ import annotations

import ipaddress
import os
import re
import select
import socket
import socketserver
import sys
from typing import ClassVar

HOST_NAME = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")


def decide(request_line: str, allow: set[str]) -> tuple[str, int] | None:
    """(máy, cổng) nếu được đi, None nếu không. Chỉ khớp đúng tên trong danh sách, không khớp tên miền con, không nhận địa chỉ IP."""
    parts = request_line.split()
    if len(parts) != 3 or parts[0] != "CONNECT":
        return None
    host, _, port = parts[1].rpartition(":")
    host = host.lower()
    if port != "443" or not HOST_NAME.match(host):
        return None
    try:
        ipaddress.ip_address(host)
        return None
    except ValueError:
        pass
    return (host, 443) if host in allow else None


class Handler(socketserver.StreamRequestHandler):
    timeout = 30
    allow: ClassVar[set[str]] = set()

    def handle(self) -> None:
        try:
            line = self.rfile.readline(1024).decode("latin-1").strip()
            while self.rfile.readline(4096).strip():
                pass
        except OSError:
            return
        target = decide(line, self.allow)
        shown = line.split()[1][:80] if len(line.split()) > 1 else "?"
        if target is None:
            print(f"DENY {shown}", flush=True)
            self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
            return
        print(f"ALLOW {shown}", flush=True)
        try:
            upstream = socket.create_connection(target, timeout=15)
        except OSError:
            self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            return
        with upstream:
            self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            self.wfile.flush()
            self.connection.settimeout(None)
            upstream.settimeout(None)
            pipes = {self.connection: upstream, upstream: self.connection}
            try:
                while True:
                    ready, _, _ = select.select(list(pipes), [], [], 300)
                    if not ready:
                        return
                    for side in ready:
                        data = side.recv(65536)
                        if not data:
                            return
                        pipes[side].sendall(data)
            except OSError:   # bên kia ngắt giữa chừng là chuyện thường của kết nối TLS
                return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    Handler.allow = {item.strip().lower() for item in os.environ.get("EGRESS_ALLOW", "").split(",") if item.strip()}
    print(f"egress: {len(Handler.allow)} máy được đi", flush=True)
    with Server(("0.0.0.0", 3128), Handler) as server:
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
