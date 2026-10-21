"""Trial-only V7 JSON API for a disposable PostgreSQL Docker container."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer as HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import v7_identity

MAX_BODY = 64 * 1024
MAX_BIGINT = 9223372036854775807
PREVIEW = Path(__file__).resolve().parents[1] / "preview"
ASSETS = {
    "/so-khach-v7-live.html": ("so-khach-v7-live.html", "text/html; charset=utf-8"),
    "/so-khach-v7-ui.js": ("so-khach-v7-ui.js", "text/javascript; charset=utf-8"),
    "/so-khach-v7-model.js": ("so-khach-v7-model.js", "text/javascript; charset=utf-8"),
    "/so-khach-v7-api.js": ("so-khach-v7-api.js", "text/javascript; charset=utf-8"),
}
ROUTES = {
    "/api/v7/trips/paste": ("paste_trips", {"debt_month", "trips"}),
    "/api/v7/trips/price": ("edit_trip_price", {"trip_id", "unit_price_vnd", "other_fee_vnd"}),
    "/api/v7/trips/adjust": ("adjust_trip", {"trip_id", "new_amount_vnd", "field", "new_value_vnd", "note"}),
    "/api/v7/months/adjust": ("adjust_month", {"debt_month", "amount_vnd", "note"}),
    "/api/v7/receipts": ("record_receipt", {"date", "method", "amount_vnd"}),
    "/api/v7/receipts/meta": ("edit_receipt_meta", {"pid", "date", "method"}),
    "/api/v7/receipts/void": ("void_receipt", {"pid", "reason"}),
    "/api/v7/months/lock": ("set_month_lock", {"month", "locked"}),
}
COMMON = {"customer_id", "expected_version", "idempotency_key"}
TRIP_FIELDS = {"date", "container", "carrier", "from", "to", "note", "src", "unitPriceVnd", "otherFeeVnd"}
ERRORS = {
    "STALE_LEDGER": (409, "Sổ đã thay đổi. Tải lại rồi thử tiếp."),
    "MONTH_LOCKED": (409, "Tháng đang khóa."),
    "IDEMPOTENCY_CONFLICT": (409, "Mã yêu cầu đã dùng cho nội dung khác."),
    "NO_BASELINE": (409, "Khách chưa có số dư đầu hiệu lực."),
    "RECEIPT_ALREADY_VOID": (409, "Phiếu đã hủy."),
    "NO_CHANGE": (409, "Nội dung không thay đổi."),
    "CUSTOMER_NOT_FOUND": (422, "Không tìm thấy khách."),
    "TRIP_NOT_FOUND": (422, "Không tìm thấy chuyến."),
    "TRIP_HAS_NO_PRICE": (422, "Chuyến chưa có giá."),
    "RECEIPT_NOT_FOUND": (422, "Không tìm thấy phiếu."),
    "MONTH_NOT_FOUND": (422, "Không tìm thấy tháng."),
    "NO_MONTH_FOR_RECEIPT": (422, "Chưa có tháng để ghi phiếu."),
    "VOID_REASON_REQUIRED": (422, "Cần ghi lý do hủy phiếu."),
    "FUTURE_RECEIPT_DATE": (422, "Ngày trả không được sau hôm nay."),
}
for _code in ("INVALID_VND", "INVALID_ADJUSTMENT", "INVALID_COMMAND", "INVALID_METHOD",
              "INVALID_MONTH", "INVALID_MONTH_LOCK", "INVALID_RECEIPT", "INVALID_TRIP",
              "INVALID_TRIP_DATE", "INVALID_TRIP_INPUT", "INVALID_TRIPS"):
    ERRORS[_code] = (422, "Dữ liệu nhập không hợp lệ.")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def bad(code: str = "INVALID_REQUEST", message: str = "Dữ liệu gửi không hợp lệ.") -> None:
    raise ApiError(422, code, message)


def positive_int(value: object) -> bool:
    return type(value) is int and 0 < value <= MAX_BIGINT


def vnd(value: object, *, signed: bool = False, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)" if not signed else r"(?:0|-?[1-9][0-9]*)", value):
        return False
    digits = value.lstrip("-")
    limit = str(MAX_BIGINT + (value.startswith("-")))
    return len(digits) < len(limit) or (len(digits) == len(limit) and digits <= limit)


def valid_date(value: object, *, month: bool = False, trip: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    fmt = "%d/%m/%Y" if trip else "%Y-%m-%d"
    if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}" if trip else r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        parsed = datetime.strptime(value, fmt).date()
    except ValueError:
        return False
    return not month or parsed.day == 1


def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            bad()
        result[key] = value
    return result


def validate(path: str, raw: bytes) -> tuple[str, dict]:
    if path not in ROUTES:
        raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_float=lambda _: bad(), parse_constant=lambda _: bad())
        json.dumps(body, ensure_ascii=False).encode("utf-8")
    except (UnicodeError, ValueError, TypeError, RecursionError):
        bad()
    if not isinstance(body, dict):
        bad()
    function, fields = ROUTES[path]
    if set(body) - (COMMON | fields) or not set(body) >= COMMON:
        bad()
    if not positive_int(body["customer_id"]) or type(body["expected_version"]) is not int or not 0 <= body["expected_version"] <= MAX_BIGINT:
        bad()
    key = body["idempotency_key"]
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.strip() or any(ord(c) < 32 for c in key):
        bad()
    for name in ("trip_id",):
        if name in fields and (name not in body or not positive_int(body[name])):
            bad()
    for name in ("debt_month", "month"):
        if name in fields and (name not in body or not valid_date(body[name], month=True)):
            bad()
    if function == "adjust_trip":
        by_field = "field" in body or "new_value_vnd" in body
        if by_field:
            if (body.get("field") not in ("unit_price_vnd", "other_fee_vnd")
                    or not vnd(body.get("new_value_vnd")) or "new_amount_vnd" in body):
                bad()
        elif not vnd(body.get("new_amount_vnd")):
            bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    for name in ("amount_vnd", "unit_price_vnd", "other_fee_vnd"):
        if name in fields and (name not in body or not vnd(body[name], signed=name == "amount_vnd" and function == "adjust_month",
                                                      nullable=name in ("unit_price_vnd", "other_fee_vnd"))):
            bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    if function == "paste_trips":
        trips = body.get("trips")
        if not isinstance(trips, list) or not trips or len(trips) > 200:
            bad()
        for trip_row in trips:
            if not isinstance(trip_row, dict) or set(trip_row) - TRIP_FIELDS:
                bad()
            if "date" in trip_row and trip_row["date"] is not None and not valid_date(trip_row["date"], trip=True):
                bad()
            for name in ("unitPriceVnd", "otherFeeVnd"):
                if name in trip_row and not vnd(trip_row[name], nullable=True):
                    bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
            if any(type(value) is not str and value is not None for value in trip_row.values()):
                bad()
    for name in ("date",):
        if name in fields and ((name not in body and function == "record_receipt") or (name in body and body[name] is not None and not valid_date(body[name]))):
            bad()
    for name in ("method", "pid", "reason", "note"):
        if name in fields and name in body and body[name] is not None and (not isinstance(body[name], str) or len(body[name]) > 500):
            bad()
    if function == "record_receipt" and (not isinstance(body.get("method"), str) or not body["method"] or body["amount_vnd"] == "0"):
        bad()
    if function == "edit_receipt_meta" and not any(body.get(name) is not None for name in ("date", "method")):
        bad()
    if function in ("edit_receipt_meta", "void_receipt") and not isinstance(body.get("pid"), str):
        bad()
    if function == "void_receipt" and not isinstance(body.get("reason"), str):
        bad()
    if function == "set_month_lock" and type(body.get("locked")) is not bool:
        bad()
    return function, body


# Fixed SQL; psql :'payload' and :'actor' quote variable values as SQL literals.
SQL = {
    "get_ledger": "SELECT sokhach.get_ledger((:'payload'::jsonb->>'customer_id')::bigint);",
    "list_customers": "SELECT jsonb_build_object('customers',coalesce(jsonb_agg(jsonb_build_object('id',id,'name',name,'status',status) ORDER BY name COLLATE \"C\",id),'[]'::jsonb)) FROM (SELECT c.id,c.name,CASE WHEN cc.status='active' AND co.status='active' THEN 'active' ELSE 'NO_BASELINE' END AS status FROM sokhach.customer c LEFT JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id LEFT JOIN sokhach.cutover co ON co.id=cc.cutover_id) q;",
}
ARGUMENTS = {
    "paste_trips": ("debt_month", "trips"),
    "edit_trip_price": ("trip_id", "unit_price_vnd", "other_fee_vnd"),
    "adjust_trip": ("trip_id", "new_amount_vnd", "note", "field", "new_value_vnd"),
    "adjust_month": ("debt_month", "amount_vnd", "note"),
    "record_receipt": ("date", "method", "amount_vnd"),
    "edit_receipt_meta": ("pid", "date", "method"),
    "void_receipt": ("pid", "reason"),
    "set_month_lock": ("month", "locked"),
}
CAST = {"debt_month": "date", "month": "date", "date": "date", "trip_id": "bigint",
        "unit_price_vnd": "bigint", "other_fee_vnd": "bigint", "new_amount_vnd": "bigint",
        "amount_vnd": "bigint", "new_value_vnd": "bigint", "trips": "jsonb", "locked": "boolean"}
for _name, _fields in ARGUMENTS.items():
    _args = ["(j->>'customer_id')::bigint", "(j->>'expected_version')::bigint", "j->>'idempotency_key'"]
    _args += [f"(j{'->' if field == 'trips' else '->>'}'{field}')::{CAST[field]}" if field in CAST
              else f"j->>'{field}'" for field in _fields]
    SQL[_name] = f"WITH b AS (SELECT :'payload'::jsonb AS j) SELECT sokhach.{_name}({', '.join(_args)}) FROM b;"


class Psql:
    def __init__(self, container: str, database: str, user: str):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
            raise ValueError("invalid container name")
        if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (database, user)):
            raise ValueError("invalid database or user")
        try:
            inspected = subprocess.run(["docker", "inspect", "--type=container", container],
                                       text=True, encoding="utf-8", capture_output=True, timeout=8, check=True)
            info = json.loads(inspected.stdout)[0]
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
            raise ValueError("test container unavailable") from exc
        labels = info.get("Config", {}).get("Labels") or {}
        if (labels.get("codex.test") != "webdebit-v7-backend" or not labels.get("codex.run")
                or info.get("HostConfig", {}).get("NetworkMode") != "none"
                or not re.fullmatch(r"[0-9a-f]{64}", info.get("Id", ""))):
            raise ValueError("target is not isolated V7 test container")
        self.container, self.database, self.user = info["Id"], database, user

    def run(self, function: str, payload: dict, actor: str) -> dict:
        sql = "BEGIN;\nSET LOCAL sokhach.actor = :'actor';\n" + SQL[function] + "\nCOMMIT;\n"
        try:
            result = subprocess.run(
                ["docker", "exec", "-i", "--env", "PGOPTIONS=-c statement_timeout=15000 -c lock_timeout=12000",
                 self.container, "psql", "-X", "-qAt", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=verbose",
                 "-v", "payload=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                 "-v", "actor=" + actor, "-U", self.user, "-d", self.database, "-f", "-"],
                input=sql, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=25,
                check=False)
        except subprocess.TimeoutExpired as exc:
            if function == "get_ledger":
                raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.") from exc
            raise ApiError(503, "RESULT_UNKNOWN", "Chưa rõ lệnh đã lưu. Thử lại với cùng mã yêu cầu.") from exc
        except OSError as exc:
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.") from exc
        if result.returncode:
            match = re.search(r"(?m)^psql:.*: ERROR:  P0001: ([A-Z_]+)\s*$", result.stderr)
            if match and match.group(1) in ERRORS:
                status, message = ERRORS[match.group(1)]
                raise ApiError(status, match.group(1), message)
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        try:
            return json.loads(result.stdout.strip())
        except ValueError as exc:
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.") from exc


def handle(method: str, target: str, headers: dict[str, str], raw: bytes, runner: Psql, *,
           port: int, host: str, default_actor: str | None = None, actor: str | None = None,
           source_ip: str = "", source_port: int = 0, localapi=None, behind_tailscale_serve: bool = False,
           demo: bool = False, real_copy: bool = False) -> tuple[int, dict]:
    headers = {name.lower(): value for name, value in headers.items()}
    allowed = {f"127.0.0.1:{port}", f"localhost:{port}", f"{host}:{port}"}
    request_host = headers.get("host", "").lower()
    if request_host not in allowed:
        raise ApiError(400, "INVALID_HOST", "Địa chỉ truy cập không hợp lệ.")
    if method == "POST":
        if headers.get("origin") != f"http://{request_host}":
            raise ApiError(403, "INVALID_ORIGIN", "Nguồn yêu cầu không hợp lệ.")
        if headers.get("content-type", "").lower() != "application/json":
            raise ApiError(415, "INVALID_CONTENT_TYPE", "Cần gửi JSON.")
        if len(raw) > MAX_BODY:
            raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
        parts = urlsplit(target)
        if parts.query:
            bad()
        function, payload = validate(parts.path, raw)
    elif method == "GET":
        parts = urlsplit(target)
        if parts.path == "/api/v7/customers" and not parts.query:
            function, payload = "list_customers", {}
        elif parts.path != "/api/v7/ledger":
            raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")
        else:
            query = parse_qs(parts.query, keep_blank_values=True)
            if set(query) != {"customer"} or len(query["customer"]) != 1 or not re.fullmatch(r"[1-9][0-9]*", query["customer"][0]):
                bad()
            customer_text = query["customer"][0]
            if len(customer_text) > 19 or (len(customer_text) == 19 and customer_text > str(MAX_BIGINT)):
                bad()
            customer = int(customer_text)
            function, payload = "get_ledger", {"customer_id": customer}
    else:
        raise ApiError(405, "METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ.")
    if actor is None:
        actor = v7_identity.resolve_actor(source_ip, headers, localapi, source_port=source_port,
                                          behind_tailscale_serve=behind_tailscale_serve)
    result = runner.run(function, payload, actor)
    if demo and function in ("get_ledger", "list_customers"):
        result = {**result, "demo": True}
    if real_copy and function in ("get_ledger", "list_customers"):
        result = {**result, "real_copy": True}
    return 200, result


class Handler(BaseHTTPRequestHandler):
    runner: Psql
    bind_host = "127.0.0.1"
    port = 8780
    default_actor = None
    dev_actor_mode = None
    behind_tailscale_serve = False
    localapi = None
    demo = False
    real_copy = False

    def asset(self) -> bool:
        route = urlsplit(self.path).path
        if self.command != "GET" or route not in ASSETS:
            return False
        allowed = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        if self.headers.get("Host", "").lower() not in allowed:
            raise ApiError(400, "INVALID_HOST", "Địa chỉ truy cập không hợp lệ.")
        name, kind = ASSETS[route]
        data = (PREVIEW / name).read_bytes()
        self.send_response(200)
        for header, value in (("Content-Type", kind), ("Content-Length", str(len(data))),
                              ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                              ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                              ("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                               "style-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")):
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

    def request(self) -> None:
        try:
            self.connection.settimeout(5)
            for name in ("Host", "Origin", "Content-Length", "Content-Type", "Tailscale-User-Login"):
                if len(self.headers.get_all(name, [])) > 1:
                    raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            if self.headers.get("Transfer-Encoding"):
                raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            actor = self.server.dev_actor
            if actor is None:
                actor = v7_identity.resolve_actor(self.client_address[0], self.headers, self.localapi,
                                                  source_port=self.client_address[1], behind_tailscale_serve=self.behind_tailscale_serve)
            if self.asset():
                return
            raw = b""
            if self.command == "POST":
                length = self.headers.get("Content-Length", "")
                if not length.isascii() or not length.isdecimal():
                    bad()
                length_value = int(length.lstrip("0") or "0") if len(length.lstrip("0")) <= len(str(MAX_BODY)) else MAX_BODY + 1
                if length_value > MAX_BODY:
                    raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
                raw = self.rfile.read(length_value)
                if len(raw) != length_value:
                    bad()
            status, value = handle(self.command, self.path, dict(self.headers), raw, self.runner,
                                   port=self.port, host=self.bind_host, default_actor=self.default_actor,
                                   actor=actor, demo=self.demo, real_copy=self.real_copy)
            self.reply(status, value)
        except v7_identity.IdentityError as exc:
            self.reply(403, {"error": exc.code})
        except TimeoutError:
            self.reply(408, {"error": "REQUEST_TIMEOUT", "message": "Yêu cầu gửi quá chậm."})
        except ApiError as exc:
            self.reply(exc.status, {"error": exc.code, "message": exc.message})
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
    parser.add_argument("--port", type=int, default=int(os.getenv("V7_API_PORT", "8780")))
    parser.add_argument("--container", default=os.getenv("V7_API_CONTAINER"), required="V7_API_CONTAINER" not in os.environ)
    parser.add_argument("--database", default=os.getenv("V7_API_DATABASE", "webdebit_v7_test"))
    # ponytail: fake harness has no app EXECUTE grants; switch to v7_app after grants exist.
    parser.add_argument("--db-user", default=os.getenv("V7_API_DB_USER", "postgres"))
    parser.add_argument("--insecure-dev-actor", default=os.getenv("V7_API_INSECURE_DEV_ACTOR"))
    parser.add_argument("--behind-tailscale-serve", action="store_true",
                        default=os.getenv("V7_API_BEHIND_TAILSCALE_SERVE", "0") == "1",
                        help="Trust identity supplied by Tailscale Serve on a loopback listener")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--demo", action="store_true", help="Mark GET snapshots as fake demo data")
    source.add_argument("--real-copy", action="store_true", help="Mark isolated real-data copy; not production")
    args = parser.parse_args()
    if args.port == 8777:
        parser.error("port 8777 belongs to the read-only opening app")
    # Trial API (DB user postgres) stays loopback-only; real access goes through tailscale serve -> loopback.
    if not loopback(args.host):
        parser.error("V7 trial API only binds loopback; expose it with tailscale serve")
    Handler.runner = Psql(args.container, args.database, args.db_user)
    Handler.bind_host, Handler.port = args.host, args.port
    Handler.default_actor = args.insecure_dev_actor
    Handler.dev_actor_mode = args.insecure_dev_actor is not None
    Handler.behind_tailscale_serve = args.behind_tailscale_serve
    Handler.demo = args.demo
    Handler.real_copy = args.real_copy
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
