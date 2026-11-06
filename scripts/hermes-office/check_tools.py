"""Chạy trong container: in các công cụ Hermes thật sự đưa cho model, gọi thử MCP, thử đường ra ngoài. Không gọi model."""

import json
import os
import pathlib
import socket
import sys

sys.path.insert(0, "/opt/hermes")
from hermes_cli.config import load_config
from tools.mcp_tool_discovery import discover_mcp_tools

# Tên máy giữ sổ truyền lúc chạy, không để trong repo public.
HAO = os.environ.get("OFFICE_TEST_HOST", "hao")
config = load_config()
print("mcp_tools", sorted(discover_mcp_tools()))

from model_tools import get_tool_definitions, handle_function_call  # noqa: E402

ALLOWED = {"mcp__office__office_close_task", "mcp__office__office_get_summary", "mcp__office__office_list_tasks", "mcp__office__office_upsert_task"}
for platform, sets in config["platform_toolsets"].items():
    names = {item["function"]["name"] for item in get_tool_definitions(enabled_toolsets=sets, quiet_mode=True)}
    print("tools_for", platform, sorted(names), "ONLY_OFFICE" if names == ALLOWED else "EXTRA:" + ",".join(sorted(names - ALLOWED)))

sets = ["mcp-office"]
for name, args in (("terminal", {"command": "id"}), ("write_file", {"path": "/tmp/x", "content": "x"}), ("execute_code", {"code": "print(1)"}),
                   ("tool_call", {"name": "terminal", "arguments": {"command": "id"}}), ("mcp__office__office_get_summary", {})):
    print("call", name, "->", handle_function_call(name, args, enabled_toolsets=sets, enabled_tools=sorted(ALLOWED))[:170].replace("\n", " "))

for host, port in (("100.64.0.1", 443), ("1.1.1.1", 443), ("host.docker.internal", 22), (HAO, 8443)):
    try:
        socket.create_connection((host, port), timeout=3).close()
        print("net_OPEN", host, port)
    except OSError as exc:
        print("net_blocked", host, port, type(exc).__name__)

for path in ("/c", "/mnt/c", "/mnt/host", "/host_mnt", "/root/.ssh", "/home/hermes/.ssh"):
    print("path", path, "exists" if pathlib.Path(path).exists() else "absent")
print("uid", os.getuid(), "ssh_env", bool(os.environ.get("SSH_AUTH_SOCK")), "docker_sock", pathlib.Path("/var/run/docker.sock").exists())
for target in ("/office/feed/x", "/office/v7_office_mcp.py", "/opt/data/config.yaml", "/opt/hermes/x"):
    try:
        with open(target, "a"):
            pass
        print("write_OK", target)
    except OSError as exc:
        print("write_blocked", target, type(exc).__name__)
print(json.dumps({"done": True}))
