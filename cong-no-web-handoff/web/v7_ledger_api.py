"""Trial-only V7 JSON API for an isolated test container, including CT-2SO."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess  # noqa: F401  test vá `api.subprocess.run`; lệnh psql dựng ở v7_psql
import sys
import time
from datetime import datetime  # noqa: F401  test đọc `api.datetime`
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer as HTTPServer
from urllib.parse import parse_qs, urlsplit

import v7_identity
import v7_presence
import v7_zalo_chat
from v7_api_sheet import (
    approve_prices,
    approve_ps_fees,
    approve_receipts,
    approve_sheet,
    customer_name_mapping,  # noqa: F401
    ledger_projections,
    named_customer,  # noqa: F401
    refresh_sheet,
    resolve_sheet_conflict,
    sheet_queue,
    with_display_names,
)
from v7_api_tables import (
    ASSETS,
    CAST,  # noqa: F401
    ERRORS,
    IMAGE_MARK,  # noqa: F401
    IMAGE_PATH,
    MAX_BIGINT,  # noqa: F401
    MAX_BODY,
    MAX_IMAGE_BODY,
    MAX_IMAGE_BYTES,  # noqa: F401
    PREVIEW,
    ROUTES,  # noqa: F401
    SQL,  # noqa: F401
)
from v7_api_validate import (
    ApiError,
    bad,
    positive_int,
    validate,
    validate_get,
    vnd,  # noqa: F401
)
from v7_psql import (
    Psql,
    PsqlDirect,
    _PsqlRunner,  # noqa: F401
)

# Bố cục từ 31/10/2026: file này là điểm vào (`python v7_ledger_api.py`, systemd trên hao) và tầng HTTP:
# `handle` nối route với hàm, `Handler` phục vụ HTTP/SSE/file tĩnh, `main` đọc tham số. Bảng tra ở
# `v7_api_tables.py`, kiểm dữ liệu ở `v7_api_validate.py`, psql ở `v7_psql.py`, đồng bộ Sheet/PS ở
# `v7_api_sheet.py`. Tên ghi `noqa: F401` không dùng trong file này: chỉ re-export cho test và công cụ
# gọi qua `api.`. Muốn vá (patch) một biến toàn cục thì vá ở module định nghĩa nó.

PRESENCE = v7_presence.Presence()   # PRESENCE-01: chỉ trong RAM của tiến trình
STREAM_PING = 15.0
STREAM_MAX_SECONDS = 600.0          # luồng SSE tự đóng, trình duyệt tự nối lại
STREAM_MIN_GAP = 0.1                # tối đa 10 lần đẩy mỗi giây


def checked_host(value, port, host, behind_tailscale_serve=False, serve_hosts=()):
    if value.lower() in {f"127.0.0.1:{port}", f"localhost:{port}", f"{host}:{port}"}:
        return value.lower()
    if behind_tailscale_serve and value in serve_hosts:
        return value
    raise ApiError(400, "INVALID_HOST", "Địa chỉ truy cập không hợp lệ.")


def presence_tab(query: str) -> str:
    values = parse_qs(query, keep_blank_values=True)
    if set(values) != {"tab"} or len(values["tab"]) != 1 or not v7_presence.TAB.fullmatch(values["tab"][0]):
        bad()
    return values["tab"][0]


def report_presence(raw: bytes, actor: str) -> tuple[int, dict]:
    try:
        report = v7_presence.parse(raw)
        PRESENCE.report(actor, report)
    except v7_presence.PresenceError as exc:
        if str(exc) == "BODY_TOO_LARGE":
            raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.") from exc
        if str(exc) == "TOO_MANY_TABS":
            raise ApiError(429, "TOO_MANY_TABS", "Đang mở quá nhiều tab.") from exc
        bad()
    return 200, {"people": PRESENCE.view(actor, report["tab"])}


def handle_reminder(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    # NHAC-NO-01: ghi mốc "đã nhắc" đòi nợ. Ghi chú ngoài đường tiền: không version/idempotency.
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if (not isinstance(body, dict) or set(body) != {"customer_id", "source"}
            or not positive_int(body.get("customer_id"))
            or body.get("source") not in ("copy-button", "manual", "zalo")):
        bad("INVALID_REMINDER", ERRORS["INVALID_REMINDER"][1])
    return 200, runner.run("record_reminder", {"customer_id": body["customer_id"], "source": body["source"]}, actor)


# POST ngoài bảng ROUTES: thân JSON riêng, không qua validate(); mỗi hàm tự kiểm và trả (status, body).
POST_HANDLERS = {
    "/api/v7/sheet/approve": approve_sheet,
    "/api/v7/sheet/resolve": resolve_sheet_conflict,
    "/api/v7/sheet/prices": approve_prices,
    "/api/v7/sheet/receipts": approve_receipts,
    "/api/v7/ps/fees": approve_ps_fees,
    "/api/v7/sheet/refresh": lambda raw, runner, actor: refresh_sheet("POST", raw, actor),
    "/api/v7/presence": lambda raw, runner, actor: report_presence(raw, actor),
    "/api/v7/reminders": handle_reminder,
}
# Kết quả đọc được gắn cờ demo/real_copy để giao diện ghi rõ nguồn dữ liệu.
FLAGGED_READS = ("get_ledger", "list_customers", "list_offset_sources", "get_dashboard", "get_dashboard_debt", "get_receivables_matrix")


def handle(method: str, target: str, headers: dict[str, str], raw: bytes, runner: Psql, *,
           port: int, host: str, default_actor: str | None = None, actor: str | None = None,
           source_ip: str = "", source_port: int = 0, localapi=None, behind_tailscale_serve: bool = False,
           demo: bool = False, real_copy: bool = False, serve_hosts: tuple[str, ...] = (),
           allowed_logins: frozenset[str] | None = None) -> tuple[int, dict]:
    headers = {name.lower(): value for name, value in headers.items()}
    request_host = checked_host(headers.get("host", ""), port, host, behind_tailscale_serve, serve_hosts)
    if method == "POST":
        expected_origin = f"https://{request_host}" if behind_tailscale_serve and request_host in serve_hosts else f"http://{request_host}"
        if headers.get("origin") != expected_origin:
            raise ApiError(403, "INVALID_ORIGIN", "Nguồn yêu cầu không hợp lệ.")
        if headers.get("content-type", "").lower() != "application/json":
            raise ApiError(415, "INVALID_CONTENT_TYPE", "Cần gửi JSON.")
        parts = urlsplit(target)
        if len(raw) > (MAX_IMAGE_BODY if parts.path == IMAGE_PATH else MAX_BODY):
            raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
        if parts.query:
            bad()
    elif method == "GET":
        parts = urlsplit(target)
    else:
        raise ApiError(405, "METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ.")
    # Danh tính giải một lần, sau kiểm Host/Origin/Content-Type/kích thước và trước khi đọc thân lệnh.
    # Handler luôn giải danh tính trước khi gọi vào đây, nên chỉ test hoặc công cụ gọi thẳng handle()
    # không truyền actor mới tới nhánh này.
    if actor is None:
        actor = v7_identity.resolve_actor(source_ip, headers, localapi, source_port=source_port,
                                          behind_tailscale_serve=behind_tailscale_serve, allowed_logins=allowed_logins)
    if method == "POST":
        special = POST_HANDLERS.get(parts.path)
        if special is not None:
            return special(raw, runner, actor)
        function, payload = validate(parts.path, raw)
    elif parts.path == "/api/v7/sheet/refresh":
        if parts.query:
            bad()
        return refresh_sheet("GET", raw, actor)
    elif parts.path == "/api/v7/presence":
        return 200, {"people": PRESENCE.view(actor, presence_tab(parts.query))}
    elif parts.path.startswith("/api/v7/zalo/"):
        # ZALO-CHAT-01: đọc bản xuất chat ngoài DB; vẫn qua xác thực danh tính như mọi route.
        try:
            return v7_zalo_chat.handle_get(parts.path, parts.query)
        except v7_zalo_chat.ChatError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc
    else:
        function, payload = validate_get(parts.path, parts.query)
    result = runner.run(function, payload, actor)
    if function == "list_customers" and parts.path == "/api/v7/customers":
        result = with_display_names(result)
    if parts.path == "/api/v7/sheet-queue":
        return 200, sheet_queue(result, parts.query)
    if function == "get_ledger":
        result = ledger_projections(runner, result, actor)
    if function == "list_offset_sources":
        result = {"sources": result}
    if demo and function in FLAGGED_READS:
        result = {**result, "demo": True}
    if real_copy and function in FLAGGED_READS:
        result = {**result, "real_copy": True}
    return 200, result


class Handler(BaseHTTPRequestHandler):
    runner: Psql
    bind_host = "127.0.0.1"
    port = 8780
    default_actor = None
    dev_actor_mode = None
    behind_tailscale_serve = False
    serve_hosts: tuple[str, ...] = ()
    allowed_logins: frozenset[str] | None = None  # ACCESS-01; None only outside Serve mode
    localapi = None
    demo = False
    real_copy = False

    def asset(self) -> bool:
        route = urlsplit(self.path).path
        if self.command != "GET" or route not in ASSETS:
            return False
        checked_host(self.headers.get("Host", ""), self.port, self.bind_host,
                     self.behind_tailscale_serve, self.serve_hosts)
        name, kind = ASSETS[route]
        data = (PREVIEW / name).read_bytes()
        self.send_response(200)
        for header, value in (("Content-Type", kind), ("Content-Length", str(len(data))),
                              ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                              ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                              ("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                               "style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' blob:; base-uri 'none'; frame-ancestors 'none'")):
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(data)
        return True

    def reply(self, status: int, value: dict) -> None:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        for name, field in (("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(data))),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")):
            self.send_header(name, field)
        self.end_headers()
        self.wfile.write(data)

    def stream(self, actor: str, tab: str) -> None:
        """SSE: đẩy toàn bộ danh sách người khác mỗi khi đổi, ping khi im lặng (PRESENCE-01)."""
        presence = PRESENCE
        if not presence.open_stream(actor):
            raise ApiError(503, "PRESENCE_BUSY", "Quá nhiều kết nối. Trang sẽ tự hỏi định kỳ.")
        try:
            self.close_connection = True
            self.connection.settimeout(20)
            self.send_response(200)
            for name, field in (("Content-Type", "text/event-stream; charset=utf-8"), ("Cache-Control", "no-store"),
                                ("X-Content-Type-Options", "nosniff"), ("X-Accel-Buffering", "no")):
                self.send_header(name, field)
            self.end_headers()
            started = last_write = time.monotonic()
            version, last = -1, None
            while time.monotonic() - started < STREAM_MAX_SECONDS:
                version = presence.wait(version, 1.0)
                people = presence.view(actor, tab)
                now = time.monotonic()
                if people != last:
                    data = json.dumps({"people": people}, ensure_ascii=False, separators=(",", ":"))
                    self.wfile.write(f"event: presence\ndata: {data}\n\n".encode())
                    last = people
                elif now - last_write >= STREAM_PING:
                    self.wfile.write(b": ping\n\n")
                else:
                    continue
                self.wfile.flush()
                last_write = now
                time.sleep(STREAM_MIN_GAP)
        except OSError:
            pass
        finally:
            presence.close_stream(actor)

    def request(self) -> None:
        try:
            self.connection.settimeout(5)
            for name in ("Host", "Origin", "Content-Length", "Content-Type", "Tailscale-User-Login"):
                if len(self.headers.get_all(name, [])) > 1:
                    raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            if self.headers.get("Transfer-Encoding"):
                raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            checked_host(self.headers.get("Host", ""), self.port, self.bind_host,
                         self.behind_tailscale_serve, self.serve_hosts)
            actor = self.server.dev_actor
            if actor is None:
                actor = v7_identity.resolve_actor(self.client_address[0], self.headers, self.localapi,
                                                  source_port=self.client_address[1], behind_tailscale_serve=self.behind_tailscale_serve,
                                                  allowed_logins=self.allowed_logins)
            route = urlsplit(self.path)
            if self.command == "GET" and route.path == "/api/v7/presence/stream":
                self.stream(actor, presence_tab(route.query))
                return
            if self.asset():
                return
            raw = b""
            if self.command == "POST":
                length = self.headers.get("Content-Length", "")
                if not length.isascii() or not length.isdecimal():
                    bad()
                limit = MAX_IMAGE_BODY if urlsplit(self.path).path == IMAGE_PATH else MAX_BODY
                length_value = int(length.lstrip("0") or "0") if len(length.lstrip("0")) <= len(str(limit)) else limit + 1
                if length_value > limit:
                    raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
                raw = self.rfile.read(length_value)
                if len(raw) != length_value:
                    bad()
            status, value = handle(self.command, self.path, dict(self.headers), raw, self.runner,
                                   port=self.port, host=self.bind_host, default_actor=self.default_actor,
                                   actor=actor, demo=self.demo, real_copy=self.real_copy,
                                   serve_hosts=self.serve_hosts, behind_tailscale_serve=self.behind_tailscale_serve,
                                   allowed_logins=self.allowed_logins)
            self.reply(status, value)
        except v7_identity.IdentityError as exc:
            if exc.code == "LOGIN_NOT_ALLOWED":
                # ACCESS-01: the login goes to the journal (so the admin knows whom to add), never to the client.
                print(f"ACCESS-01: từ chối login ngoài danh sách: {exc.detail} (peer {self.client_address[0]})",
                      file=sys.stderr, flush=True)
                self.reply(403, {"error": exc.code,
                                 "message": "Tài khoản này chưa được cấp quyền dùng sổ. Báo quản trị thêm vào danh sách."})
            else:
                self.reply(403, {"error": exc.code})
        except TimeoutError:
            self.reply(408, {"error": "REQUEST_TIMEOUT", "message": "Yêu cầu gửi quá chậm."})
        except ApiError as exc:
            self.reply(exc.status, {"error": exc.code, "message": exc.message, **exc.extra})
        except OSError:
            self.reply(503, {"error": "ASSET_UNAVAILABLE", "message": "Không đọc được trang thử."})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = request

    def log_message(self, format: str, *args: object) -> None:
        pass


def loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class ThreadingHTTPServer(HTTPServer):
    def __init__(self, server_address, handler, *, default_actor=None, dev_actor_mode=None,
                 bind_and_activate=True):
        name = handler.default_actor if default_actor is None else default_actor
        mode = handler.dev_actor_mode if dev_actor_mode is None else dev_actor_mode
        # ponytail: legacy local tools opt in by named actor; remove after callers pass explicit mode.
        enabled = name is not None if mode is None else mode
        if (enabled or handler.behind_tailscale_serve) and not loopback(server_address[0]):
            raise ValueError("dev actor and Tailscale Serve require a loopback bind")
        self.dev_actor = None
        if enabled:
            if not isinstance(name, str) or not name.strip() or len(name) > 252 or any(ord(c) < 32 for c in name):
                raise ValueError("invalid dev actor")
            self.dev_actor = "dev:" + name.strip()
        super().__init__(server_address, handler, bind_and_activate=bind_and_activate)
        if enabled:
            print("WARNING: insecure dev actor enabled; identity verification bypassed (loopback only)", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("V7_API_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("V7_API_PORT", "8780"))
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--container")
    target.add_argument("--direct-socket-dir")
    parser.add_argument("--database")
    # ponytail: fake harness has no app EXECUTE grants; switch to v7_app after grants exist.
    parser.add_argument("--db-user")
    parser.add_argument(
        "--insecure-dev-actor", default=os.getenv("V7_API_INSECURE_DEV_ACTOR")
    )
    parser.add_argument(
        "--behind-tailscale-serve",
        action="store_true",
        default=os.getenv("V7_API_BEHIND_TAILSCALE_SERVE", "0") == "1",
        help="Trust identity supplied by Tailscale Serve on a loopback listener",
    )
    parser.add_argument("--serve-host", action="append", default=[],
                        help="Exact Host value accepted from Tailscale Serve; requires --behind-tailscale-serve")
    parser.add_argument("--allowed-login", action="append", default=[],
                        help="Tailscale login allowed to use the ledger (ACCESS-01); repeatable, merged with "
                             "WEBDEBIT_ALLOWED_LOGINS (comma/space separated). Serve mode requires at least one")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--demo", action="store_true", help="Mark GET snapshots as fake demo data"
    )
    source.add_argument(
        "--real-copy",
        action="store_true",
        help="Mark isolated real-data copy; not production",
    )
    args = parser.parse_args()
    if args.serve_host and not args.behind_tailscale_serve:
        parser.error("--serve-host requires --behind-tailscale-serve")
    for value in args.serve_host:
        try:
            port_value = urlsplit("//" + value).port or 443
        except ValueError:
            port_value = 0
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]*(?::[1-9][0-9]{0,4})?", value) or not 1 <= port_value <= 65535:
            parser.error("--serve-host requires lowercase fqdn[:port]")
    # ACCESS-01: the allowlist lives in the unit drop-in on the host, never in Git. Serve mode without it
    # must not start: every tailnet identity reaching Serve would otherwise be a valid ledger actor.
    allowed_env = os.getenv("WEBDEBIT_ALLOWED_LOGINS")
    allowed_raw = None
    if args.allowed_login or allowed_env is not None:
        allowed_raw = ",".join([*args.allowed_login, allowed_env or ""])
    try:
        allowed_logins = v7_identity.parse_allowed_logins(allowed_raw)
    except v7_identity.IdentityError as exc:
        parser.error(f"allowed logins invalid: {exc.code}")
    if args.behind_tailscale_serve and args.insecure_dev_actor is None and not allowed_logins:
        parser.error("--behind-tailscale-serve requires at least one allowed login "
                     "(--allowed-login or WEBDEBIT_ALLOWED_LOGINS; ACCESS-01)")
    if args.direct_socket_dir:
        if not args.database or args.database == "webdebit_ledger":
            parser.error("direct mode requires explicit non-legacy database")
        args.db_user = args.db_user or "v7_app"
    else:
        args.container = args.container or os.getenv("V7_API_CONTAINER")
        if not args.container:
            parser.error("one of --container or --direct-socket-dir is required")
        args.database = args.database or os.getenv(
            "V7_API_DATABASE", "webdebit_v7_test"
        )
        args.db_user = args.db_user or os.getenv("V7_API_DB_USER", "postgres")
    if args.port == 8777:
        parser.error("port 8777 belongs to the read-only opening app")
    # Trial API (DB user postgres) stays loopback-only; real access goes through tailscale serve -> loopback.
    if not loopback(args.host):
        parser.error("V7 trial API only binds loopback; expose it with tailscale serve")
    Handler.runner = (
        PsqlDirect(args.direct_socket_dir, args.database, args.db_user)
        if args.direct_socket_dir
        else Psql(args.container, args.database, args.db_user)
    )
    Handler.bind_host, Handler.port = args.host, args.port
    Handler.default_actor = args.insecure_dev_actor
    Handler.dev_actor_mode = args.insecure_dev_actor is not None
    Handler.behind_tailscale_serve = args.behind_tailscale_serve
    Handler.serve_hosts = tuple(args.serve_host)
    Handler.allowed_logins = allowed_logins
    Handler.demo = args.demo
    Handler.real_copy = args.real_copy
    v7_zalo_chat.warm()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
