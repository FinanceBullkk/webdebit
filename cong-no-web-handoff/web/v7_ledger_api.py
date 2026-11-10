"""Trial-only V7 JSON API for an isolated test container, including CT-2SO."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import ipaddress
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
from datetime import datetime  # noqa: F401  test đọc `api.datetime`
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer as HTTPServer
from urllib.parse import parse_qs, urlsplit

import v7_ai_explain
import v7_api_doi_chieu
import v7_api_sheet
import v7_api_zalo
import v7_debit_note_config
import v7_identity
import v7_inbox
import v7_machine
import v7_presence
import v7_sheet_refresh
import v7_zalo_chat
from v7_api_sheet import (
    apply_sheet_price,
    approve_price_conflicts,
    approve_prices,
    approve_ps_fees,
    approve_receipts,
    approve_sheet,
    assign_sheet_trip,
    customer_name_mapping,  # noqa: F401
    keep_sheet_task,
    ledger_projections,
    named_customer,  # noqa: F401
    refresh_sheet,
    resolve_sheet_conflict,
    review_sheet_receipt,
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
# Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): kết quả chiếu của mọi sổ, tính nền, chỉ trong RAM của tiến trình.
INBOX = v7_inbox.Inbox(
    ledger_projections,
    lambda: (v7_api_sheet.SHEET_SNAPSHOT_PATH, v7_api_sheet.PRICE_SNAPSHOT_PATH,
             v7_api_sheet.RECEIPT_SNAPSHOT_PATH, v7_api_sheet.PS_SNAPSHOT_PATH)
    # road.json (chuyến bộ, NGUON-CHUYEN-01) chỉ có khi runner bật: thiếu file không được làm hộp thành "chưa đọc được".
    + tuple(path for path in (v7_api_sheet.ROAD_SNAPSHOT_PATH,) if os.path.exists(path)),
    lambda: v7_sheet_refresh.status(v7_api_sheet.SHEET_REFRESH_PATH,
                                    (v7_api_sheet.SHEET_SNAPSHOT_PATH, v7_api_sheet.PRICE_SNAPSHOT_PATH), time.time()))
STREAM_PING = 15.0
STREAM_MAX_SECONDS = 600.0          # luồng SSE tự đóng, trình duyệt tự nối lại
STREAM_MIN_GAP = 0.1                # tối đa 10 lần đẩy mỗi giây
# Từ chối mà chưa đọc thân lệnh: đóng socket ngay thì phần thân tới sau làm Windows hủy luôn phản hồi lỗi đang
# chờ ở client (WinError 10053). Nên trả lời, gửi FIN rồi xả bỏ thân, có trần để từ chối không tốn tài nguyên.
DISCARD_MAX_BYTES = MAX_IMAGE_BODY  # thân hợp lệ lớn nhất vẫn nhận được phản hồi
DISCARD_SECONDS = 2.0               # hạn tổng, client nhỏ giọt cũng không giữ luồng lâu hơn
DISCARD_CHUNK = 64 * 1024


def declared_length(value: str, limit: int) -> int | None:
    """Content-Length đã kiểm: sai thì None; vượt `limit` thì limit + 1, không đổi chuỗi số dài thành int."""
    if not value.isascii() or not value.isdecimal():
        return None
    digits = value.lstrip("0")
    return int(digits or "0") if len(digits) <= len(str(limit)) else limit + 1


def checked_host(value, port, host, behind_tailscale_serve=False, serve_hosts=()):
    if value.lower() in {f"127.0.0.1:{port}", f"localhost:{port}", f"{host}:{port}"}:
        return value.lower()
    if behind_tailscale_serve and value in serve_hosts:
        return value
    raise ApiError(400, "INVALID_HOST", "Địa chỉ truy cập không hợp lệ.")


HEALTHZ_PATH = "/healthz"


def healthz_allowed(client_ip: str, headers, port: int) -> bool:
    """Kiểm sống chỉ dành cho curl trên chính máy chủ: loopback, Host loopback, không danh tính/proxy.

    Qua Tailscale Serve thì Host là tên ts.net và có header `Tailscale-*`, nên bị từ chối (ACCESS-01 giữ nguyên).
    """
    names = {name.lower() for name in headers}
    return (loopback(client_ip)
            and headers.get("Host", "").lower() in {f"127.0.0.1:{port}", f"localhost:{port}"}
            and not any(name.startswith("tailscale-") or name in ("x-forwarded-for", "forwarded") for name in names))


def healthz(runner: Psql, now: float) -> tuple[int, dict]:
    """`SELECT 1` qua đúng runner psql của app, kèm tuổi bản chụp Sheet; DB lỗi thì 503 (audit DevOps #6, #14)."""
    times = []
    for path in (v7_api_sheet.SHEET_SNAPSHOT_PATH, v7_api_sheet.PRICE_SNAPSHOT_PATH):
        try:
            times.append(os.stat(path).st_mtime)
        except OSError:
            times.append(None)
    # Như nút Làm mới: tuổi tính theo bản cũ hơn trong hai file; thiếu file thì null. Không làm đỏ kiểm sống.
    age = None if None in times else max(0, int(now - min(times)))
    try:
        db_ok = runner.run("healthz", {}, "healthz") == 1
    except ApiError:
        db_ok = False
    body = {"ok": db_ok, "db": "ok" if db_ok else "error", "sheet_snapshot_age_seconds": age}
    return (200 if db_ok else 503), body


def with_actor_names(ledger: dict) -> dict:
    """SO-GON-04 (L6): Lịch sử ghi tên ngắn người làm theo bảng tên của PRESENCE-01, không phải login. Chỉ thêm `actor_name`."""
    events = ledger.get("events")
    if not isinstance(events, list):
        return ledger
    names = PRESENCE.names()
    return {**ledger, "events": [{**event, "actor_name": v7_presence.display_name(event["actor"], names)}
                                 if isinstance(event, dict) and isinstance(event.get("actor"), str) else event
                                 for event in events]}


def public_ledger(ledger: dict) -> dict:
    """MO-SO-NHANH-02: thân GET sổ không có Lịch sử (nạp riêng khi mở khung) và ô Sheet thô `display.cells` (không màn nào đọc).

    Chỉ cắt ở tầng HTTP, sau khi chiếu hàng chờ: `sheet_projection` cần `events`, công cụ đọc `cells` qua runner. Không sửa dict vào.
    """
    body = {key: value for key, value in ledger.items() if key != "events"}
    rows = ledger.get("legacy_rows")
    if isinstance(rows, list):
        body["legacy_rows"] = [{**row, "display": {key: value for key, value in row["display"].items() if key != "cells"}}
                               if isinstance(row, dict) and isinstance(row.get("display"), dict) else row for row in rows]
    return body


# MO-SO-NHANH-01 (4/11/2026): file JS/CSS đọc một lần rồi giữ (nguyên bản, bản gzip, ETag) trong tiến trình; đọc lại khi
# mtime hoặc kích thước đổi. Deploy thay cả thư mục release và khởi động lại dịch vụ nên bộ nhớ này không giữ bản cũ.
GZIP_MIN_BYTES = 1024
_ASSET_CACHE: dict[str, tuple[tuple[int, int], bytes, bytes, str]] = {}
_ASSET_LOCK = threading.Lock()


def accepts_gzip(accept_encoding: str | None) -> bool:
    """`Accept-Encoding` có gzip và không bị tắt bằng q=0."""
    for token in (accept_encoding or "").split(","):
        name, _, params = token.strip().partition(";")
        if name.strip().lower() == "gzip" and not re.search(r"q\s*=\s*0(?:\.0+)?\s*$", params):
            return True
    return False


def asset_versions(name: str) -> tuple[bytes, bytes, str]:
    """(nguyên bản, bản gzip, ETag) của một file preview; file dưới GZIP_MIN_BYTES giữ bản gzip bằng nguyên bản."""
    path = PREVIEW / name
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    with _ASSET_LOCK:
        held = _ASSET_CACHE.get(name)
        if held is not None and held[0] == key:
            return held[1:]
    data = path.read_bytes()
    packed = gzip.compress(data, compresslevel=6, mtime=0) if len(data) >= GZIP_MIN_BYTES else data
    etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
    with _ASSET_LOCK:
        _ASSET_CACHE[name] = (key, data, packed, etag)
    return data, packed, etag


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


def touch_inbox(raw: bytes) -> None:
    """Sau một lệnh ghi thành công: đánh dấu các sổ trong thân lệnh để hộp ngoại lệ tính lại ở lần đọc sau."""
    try:
        body = json.loads(raw)
    except ValueError:
        return
    if isinstance(body, dict):
        INBOX.mark_dirty(*(body.get(key) for key in ("customer_id", "source_customer_id", "target_customer_id")))


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
    "/api/v7/sheet/trips/assign": assign_sheet_trip,
    "/api/v7/sheet/receipts/review": review_sheet_receipt,
    "/api/v7/sheet/tasks/price": apply_sheet_price,
    "/api/v7/sheet/tasks/keep": keep_sheet_task,
    "/api/v7/sheet/approve": approve_sheet,
    "/api/v7/sheet/resolve": resolve_sheet_conflict,
    "/api/v7/sheet/prices": approve_prices,
    "/api/v7/sheet/prices/conflicts": approve_price_conflicts,
    "/api/v7/sheet/doi-chieu/ghi": v7_api_doi_chieu.write,
    "/api/v7/sheet/doi-chieu/giu": v7_api_doi_chieu.keep,
    "/api/v7/sheet/doi-chieu/hoan-tac": v7_api_doi_chieu.undo,
    "/api/v7/sheet/receipts": approve_receipts,
    "/api/v7/ps/fees": approve_ps_fees,
    "/api/v7/sheet/refresh": lambda raw, runner, actor: refresh_sheet("POST", raw, actor),
    "/api/v7/presence": lambda raw, runner, actor: report_presence(raw, actor),
    "/api/v7/reminders": handle_reminder,
    "/api/v7/zalo/link": v7_api_zalo.handle_link,
    "/api/v7/zalo/unlink": lambda raw, runner, actor: v7_api_zalo.handle_link(raw, runner, actor, unlink=True),
    "/api/v7/marks": v7_api_zalo.handle_mark,
    "/api/v7/marks/cancel": v7_api_zalo.handle_cancel,
    "/api/v7/machine/office": v7_machine.handle_office,
}
MACHINE_READS = {"/api/v7/machine": v7_machine.view, "/api/v7/machine/now": v7_machine.now_view, "/api/v7/machine/summary": v7_machine.summary}
# Kết quả đọc được gắn cờ demo/real_copy để giao diện ghi rõ nguồn dữ liệu.
FLAGGED_READS = ("get_ledger", "list_customers", "list_offset_sources", "get_dashboard", "get_dashboard_debt", "get_receivables_matrix", "get_receipt_book")


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
        if parts.path == "/api/v7/ai/explain":
            return v7_ai_explain.explain(raw, runner, actor)
        special = POST_HANDLERS.get(parts.path)
        if special is not None:
            status, body = special(raw, runner, actor)
            touch_inbox(raw)
            return status, body
        function, payload = validate(parts.path, raw)
    elif parts.path == "/api/v7/sheet/refresh":
        if parts.query:
            bad()
        return refresh_sheet("GET", raw, actor)
    elif parts.path == "/api/v7/presence":
        return 200, {"people": PRESENCE.view(actor, presence_tab(parts.query))}
    elif parts.path == "/api/v7/inbox":
        if parts.query:
            bad()
        return 200, INBOX.view(runner)
    elif parts.path in MACHINE_READS:
        # MAY-CHAY-01: đọc file của job, không qua DB; vẫn sau xác thực danh tính như mọi route.
        if parts.query:
            bad()
        body = MACHINE_READS[parts.path]()
        # Bản cho Hermes không được có chữ lấy từ Sheet, nên việc của hộp chờ chỉ đi cùng hai route cho trang.
        return 200, body if parts.path == "/api/v7/machine/summary" else {**body, "auto": INBOX.auto_today()}
    elif parts.path == "/api/v7/sheet/doi-chieu":
        _, payload = validate_get("/api/v7/ledger", parts.query)
        return 200, v7_api_doi_chieu.statement(payload["customer_id"], runner, actor)
    elif parts.path == "/api/v7/ai/preview":
        _, payload = validate_get("/api/v7/ledger", parts.query)
        return 200, v7_ai_explain.preview(payload["customer_id"], runner, actor)
    elif parts.path == "/api/v7/debit-note/config":
        # DEBIT-NOTE-03: file cấu hình ngoài DB (mẫu, công ty, ngân hàng, tên phí); vẫn sau xác thực danh tính.
        try:
            return v7_debit_note_config.handle_get(parts.query)
        except v7_debit_note_config.ConfigError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc
    elif parts.path == "/api/v7/marks":
        function, payload = v7_api_zalo.parse_marks(parts.query)
    elif parts.path.startswith("/api/v7/zalo/") and parts.path != "/api/v7/zalo/links":
        # ZALO-CHAT-01: đọc bản xuất chat ngoài DB; vẫn qua xác thực danh tính như mọi route.
        # /api/v7/zalo/links (ZALO-GROUP-01) là bảng gắn sổ trong DB nên đi đường đọc DB như mọi route.
        try:
            return v7_zalo_chat.handle_get(parts.path, parts.query)
        except v7_zalo_chat.ChatError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc
    else:
        function, payload = validate_get(parts.path, parts.query)
    result = runner.run(function, payload, actor)
    if method == "POST":
        touch_inbox(raw)
    if function == "list_customers" and parts.path == "/api/v7/customers":
        result = with_display_names(result)
    if parts.path == "/api/v7/sheet-queue":
        return 200, sheet_queue(result, parts.query)
    if function == "get_ledger":
        result = public_ledger(ledger_projections(runner, result, actor))
    if function in ("get_ledger_events", "get_activity"):
        result = with_actor_names(result)
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
    body_taken = False

    def unread_body_bytes(self) -> int:
        headers = getattr(self, "headers", None)  # dòng đầu hoặc header hỏng: chưa từng có headers
        if self.body_taken or headers is None:
            return 0
        lengths = headers.get_all("Content-Length", [])
        if headers.get("Transfer-Encoding") or len(lengths) > 1:
            return DISCARD_MAX_BYTES
        if not lengths:
            return 0
        declared = declared_length(lengths[0], DISCARD_MAX_BYTES)
        return DISCARD_MAX_BYTES if declared is None else min(declared, DISCARD_MAX_BYTES)

    def discard_unread_body(self) -> None:
        remaining = self.unread_body_bytes()
        if not remaining:
            return
        deadline = time.monotonic() + DISCARD_SECONDS
        try:
            self.connection.shutdown(socket.SHUT_WR)
            while remaining > 0 and (left := deadline - time.monotonic()) > 0:
                self.connection.settimeout(left)
                # read1 chứ không recv: một phần thân có thể đã nằm trong buffer của rfile lúc đọc header.
                chunk = self.rfile.read1(min(remaining, DISCARD_CHUNK))
                if not chunk:
                    return
                remaining -= len(chunk)
        except OSError:
            pass  # client đã đi hoặc hết hạn: phản hồi đã gửi xong, không còn gì để làm

    def finish(self) -> None:
        # Ở đây chứ không ở request(): cả phản hồi của lớp cha (501 khi không có do_X) cũng đi qua.
        self.discard_unread_body()
        super().finish()

    def asset(self) -> bool:
        route = urlsplit(self.path).path
        if self.command != "GET" or route not in ASSETS:
            return False
        checked_host(self.headers.get("Host", ""), self.port, self.bind_host,
                     self.behind_tailscale_serve, self.serve_hosts)
        name, kind = ASSETS[route]
        data, packed, etag = asset_versions(name)
        # MO-SO-NHANH-01 (4/11/2026): trình duyệt giữ file và chỉ hỏi "còn mới không" (ETag → 304) thay vì tải lại
        # 650 KB JS/CSS mỗi lần mở sổ; no-cache (không phải no-store) nên sau deploy lượt mở kế đã lấy bản mới.
        # Bản gzip có ETag riêng vì là một biểu diễn khác (Vary: Accept-Encoding).
        gz = len(packed) < len(data) and accepts_gzip(self.headers.get("Accept-Encoding"))
        if gz:
            data, etag = packed, etag[:-1] + '-gz"'
        caching = (("ETag", etag), ("Cache-Control", "private, no-cache"), ("Vary", "Accept-Encoding"))
        if etag in [tag.strip() for tag in self.headers.get("If-None-Match", "").split(",")]:
            self.send_response(304)
            for header, value in caching:
                self.send_header(header, value)
            self.end_headers()
            return True
        self.send_response(200)
        for header, value in (("Content-Type", kind), ("Content-Length", str(len(data))),
                              *((("Content-Encoding", "gzip"),) if gz else ()), *caching,
                              ("X-Content-Type-Options", "nosniff"),
                              ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                              ("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                               "style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' blob:; media-src 'self'; base-uri 'none'; frame-ancestors 'none'")):
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(data)
        return True

    def reply(self, status: int, value: dict) -> None:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        # JSON lớn (sổ 400 KB) nén nhanh khi trình duyệt nhận gzip: mức 1 đủ nhỏ 5–8 lần, vài mili giây.
        gz = len(data) >= GZIP_MIN_BYTES and accepts_gzip(self.headers.get("Accept-Encoding"))
        if gz:
            data = gzip.compress(data, compresslevel=1, mtime=0)
        self.send_response(status)
        for name, field in (("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(data))),
                            *((("Content-Encoding", "gzip"),) if gz else ()), ("Vary", "Accept-Encoding"),
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
            self._request()
        except (BrokenPipeError, ConnectionResetError) as exc:
            # Client ngắt giữa chừng (audit DevOps 31/10, #15): một dòng log, không traceback, không trả lời nữa.
            self.close_connection = True
            print(f"V7 API: client ngắt kết nối ({type(exc).__name__}) {self.command} {urlsplit(self.path).path}",
                  file=sys.stderr, flush=True)

    def _request(self) -> None:
        try:
            self.connection.settimeout(5)
            for name in ("Host", "Origin", "Content-Length", "Content-Type", "Tailscale-User-Login"):
                if len(self.headers.get_all(name, [])) > 1:
                    raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            if self.headers.get("Transfer-Encoding"):
                raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            if urlsplit(self.path).path == HEALTHZ_PATH:
                # Trước bước giải danh tính: kiểm sống sau deploy không có login Tailscale.
                if self.command != "GET" or not healthz_allowed(self.client_address[0], self.headers, self.port):
                    raise ApiError(403, "HEALTHZ_LOOPBACK_ONLY", "Chỉ kiểm sống từ chính máy chủ.")
                self.reply(*healthz(self.runner, time.time()))
                return
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
            if self.command == "GET" and route.path.startswith(v7_zalo_chat.MEDIA_PREFIX):
                # ZALO-GROUP-01: ảnh của gói chat, sau xác thực danh tính như mọi /api/v7/*.
                try:
                    kind, data = v7_zalo_chat.handle_media(route.path, route.query)
                except v7_zalo_chat.ChatError as exc:
                    raise ApiError(exc.status, exc.code, exc.message) from exc
                self.send_response(200)
                for name, field in (("Content-Type", kind), ("Content-Length", str(len(data))),
                                    ("Cache-Control", "private, max-age=86400"), ("X-Content-Type-Options", "nosniff")):
                    self.send_header(name, field)
                self.end_headers()
                self.wfile.write(data)
                return
            raw = b""
            if self.command == "POST":
                limit = MAX_IMAGE_BODY if urlsplit(self.path).path == IMAGE_PATH else MAX_BODY
                length_value = declared_length(self.headers.get("Content-Length", ""), limit)
                if length_value is None:
                    bad()
                if length_value > limit:
                    raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
                self.body_taken = True  # kể cả khi đọc hết giờ (408): client chậm không được giữ thêm luồng để xả
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
        except (BrokenPipeError, ConnectionResetError):
            raise  # request() ghi một dòng; không cố gửi 503 vào kết nối đã đứt
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
    # socketserver mặc định chỉ xếp hàng 5 kết nối; trang sổ nạp 33 file cùng lúc qua Tailscale Serve, kết nối thứ 6
    # trở đi bị bỏ rồi chờ 1 giây mới kết nối lại (đo trên `hao` 1/11/2026: 3.842 lần bỏ, trang chờ 1,9 giây).
    request_queue_size = 128

    def __init__(self, server_address, handler, *, default_actor=None, dev_actor_mode=None,
                 bind_and_activate=True, tailnet_https=False):
        name = handler.default_actor if default_actor is None else default_actor
        mode = handler.dev_actor_mode if dev_actor_mode is None else dev_actor_mode
        # ponytail: legacy local tools opt in by named actor; remove after callers pass explicit mode.
        enabled = name is not None if mode is None else mode
        if (enabled or handler.behind_tailscale_serve) and not loopback(server_address[0]) and not tailnet_https:
            raise ValueError("dev actor and Tailscale Serve require a loopback bind")
        if tailnet_https and (enabled or not handler.behind_tailscale_serve or
                             ipaddress.ip_address(server_address[0]) not in ipaddress.ip_network("100.64.0.0/10")):
            raise ValueError("tailnet HTTPS requires verified identity and no dev actor")
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
    parser.add_argument("--tailnet-https-ip", default=os.getenv("V7_TAILNET_HTTPS_IP"),
                        help="Bind a second HTTPS listener to this node's Tailscale IPv4")
    parser.add_argument("--tailnet-https-port", type=int, default=8445)
    parser.add_argument("--tailnet-https-host", default=os.getenv("V7_TAILNET_HTTPS_HOST"))
    parser.add_argument("--tailnet-tls-cert", default=os.getenv("V7_TAILNET_TLS_CERT"))
    parser.add_argument("--tailnet-tls-key", default=os.getenv("V7_TAILNET_TLS_KEY"))
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
    if any((args.tailnet_https_ip, args.tailnet_https_host, args.tailnet_tls_cert, args.tailnet_tls_key)):
        if not all((args.tailnet_https_ip, args.tailnet_https_host, args.tailnet_tls_cert, args.tailnet_tls_key)):
            parser.error("tailnet HTTPS requires IP, host, certificate and key")
        if not args.behind_tailscale_serve or args.insecure_dev_actor is not None:
            parser.error("tailnet HTTPS requires Serve mode and no dev actor")
        if not 1 <= args.tailnet_https_port <= 65535:
            parser.error("invalid tailnet HTTPS port")
        try:
            node_ip = subprocess.run(["tailscale", "ip", "-4"], check=True, capture_output=True,
                                     text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            parser.error(f"cannot verify Tailscale IP: {type(exc).__name__}")
        if args.tailnet_https_ip != node_ip:
            parser.error("tailnet HTTPS IP does not match this Tailscale node")
    accepted_hosts = args.serve_host + ([args.tailnet_https_host] if args.tailnet_https_host else [])
    for value in accepted_hosts:
        try:
            port_value = urlsplit("//" + value).port or 443
        except ValueError:
            port_value = 0
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]*(?::[1-9][0-9]{0,4})?", value) or not 1 <= port_value <= 65535:
            parser.error("--serve-host requires lowercase fqdn[:port]")
    if args.tailnet_https_host and not args.tailnet_https_host.endswith(f":{args.tailnet_https_port}"):
        parser.error("tailnet HTTPS host must include the listener port")
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
    # API HTTP stays loopback-only; optional HTTPS binds only this node's Tailscale IPv4.
    if not loopback(args.host):
        parser.error("V7 API HTTP only binds loopback; expose it with tailscale serve")
    Handler.runner = (
        PsqlDirect(args.direct_socket_dir, args.database, args.db_user)
        if args.direct_socket_dir
        else Psql(args.container, args.database, args.db_user)
    )
    Handler.bind_host, Handler.port = args.host, args.port
    Handler.default_actor = args.insecure_dev_actor
    Handler.dev_actor_mode = args.insecure_dev_actor is not None
    Handler.behind_tailscale_serve = args.behind_tailscale_serve
    Handler.serve_hosts = tuple(accepted_hosts)
    Handler.allowed_logins = allowed_logins
    Handler.demo = args.demo
    Handler.real_copy = args.real_copy
    v7_zalo_chat.warm()
    secure = None
    if args.tailnet_https_ip:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tailnet_tls_cert, args.tailnet_tls_key)
        secure = ThreadingHTTPServer((args.tailnet_https_ip, args.tailnet_https_port), Handler, tailnet_https=True)
        secure.socket = context.wrap_socket(secure.socket, server_side=True)
    plain = ThreadingHTTPServer((args.host, args.port), Handler)
    INBOX.start(Handler.runner)   # tính sẵn hộp ngoại lệ ở nền ngay khi khởi động
    INBOX.keep_fresh(Handler.runner)   # rồi tính lại theo từng đợt Sheet, kể cả khi không ai mở Việc cần làm
    if secure is not None:
        threading.Thread(target=secure.serve_forever, daemon=True).start()
    plain.serve_forever()


if __name__ == "__main__":
    main()
