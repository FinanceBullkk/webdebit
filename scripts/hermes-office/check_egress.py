"""Chạy trong container Hermes: thử đi thẳng và đi qua cổng ra. Không gửi dữ liệu gì, không gọi model."""

import os
import socket

# Tên máy giữ sổ truyền lúc chạy, không để trong repo public.
HAO = os.environ.get("OFFICE_TEST_HOST", "hao")


def direct(host: str, port: int) -> str:
    try:
        socket.create_connection((host, port), timeout=4).close()
        return "OPEN"
    except OSError as exc:
        return f"blocked ({type(exc).__name__})"


def via_proxy(target: str) -> str:
    try:
        with socket.create_connection(("egress", 3128), timeout=6) as sock:
            sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
            return sock.recv(200).split(b"\r\n")[0].decode("latin-1")
    except OSError as exc:
        return f"error ({type(exc).__name__})"


for host, port in (("1.1.1.1", 443), ("chatgpt.com", 443), ("host.docker.internal", 22), ("100.64.0.1", 443), (HAO, 8443)):
    print("direct", host, port, "->", direct(host, port))
for target in ("chatgpt.com:443", "auth.openai.com:443", "evil.chatgpt.com:443", "chatgpt.com:80", HAO + ":8443", HAO + ":443",
               "host.docker.internal:22", "host.docker.internal:443", "1.1.1.1:443", "100.64.0.1:443", "github.com:443", "openrouter.ai:443"):
    print("proxy", target, "->", via_proxy(target))
