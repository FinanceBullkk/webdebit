"""Trial-only V7 JSON API for an isolated test container, including CT-2SO."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
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
from datetime import datetime  # test đọc `api.datetime`; XUAT-SO-01 lấy giờ của file
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer as HTTPServer
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import v7_access
import v7_ai_explain
import v7_api_doi_chieu
import v7_api_doixe
import v7_api_sheet
import v7_api_zalo
import v7_book_export
import v7_api_khach
import v7_booking_view
import v7_cash_chat
import v7_company_info
import v7_debit_note_config
import v7_doixe_xlsx
import v7_identity
import v7_inbox
import v7_insurance_queue
import v7_machine
import v7_month_missing
import v7_month_report
import v7_nhat_ky
import v7_presence
import v7_read_cache
import v7_role
import v7_sheet_refresh
import v7_telegram
import v7_todo_badge
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
    PAGES,
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
READS = v7_read_cache.ReadCache()   # HIEU-NANG-01: kết quả đọc nặng theo dấu dữ liệu, chỉ cho GET
# XUAT-SO-01: file cả sổ, một lượt mỗi lúc trong tiến trình (mỗi lượt đọc mọi sổ trong một giao dịch).
EXPORT_PATH = "/api/v7/xuat-so.xlsx"
EXPORT_LOCK = threading.Lock()
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
# Hộp ngoại lệ P1 (specs/v7-hop-ngoai-le-p1.md): kết quả chiếu của mọi sổ, tính nền, chỉ trong RAM của tiến trình.
INBOX = v7_inbox.Inbox(
    ledger_projections,
    lambda: (v7_api_sheet.SHEET_SNAPSHOT_PATH, v7_api_sheet.PRICE_SNAPSHOT_PATH,
             v7_api_sheet.RECEIPT_SNAPSHOT_PATH, v7_api_sheet.PS_SNAPSHOT_PATH)
    # road.json (chuyến bộ, NGUON-CHUYEN-01) chỉ có khi runner bật: thiếu file không được làm hộp thành "chưa đọc được".
    + tuple(path for path in (v7_api_sheet.ROAD_SNAPSHOT_PATH,) if os.path.exists(path)),
    lambda: v7_sheet_refresh.status(v7_api_sheet.SHEET_REFRESH_PATH,
                                    (v7_api_sheet.SHEET_SNAPSHOT_PATH, v7_api_sheet.PRICE_SNAPSHOT_PATH), time.time()),
    insurance=v7_api_sheet.insurance_orphans) # BAO-HIEM-ZALO-01: không vào khóa làm mới của hộp (bản chụp riêng)
STREAM_PING = 15.0
STREAM_MAX_SECONDS = 600.0          # luồng SSE tự đóng, trình duyệt tự nối lại
STREAM_MIN_GAP = 0.1                # tối đa 10 lần đẩy mỗi giây
# Từ chối mà chưa đọc thân lệnh: đóng socket ngay thì phần thân tới sau làm Windows hủy luôn phản hồi lỗi đang
# chờ ở client (WinError 10053). Nên trả lời, gửi FIN rồi xả bỏ thân, có trần để từ chối không tốn tài nguyên.
DISCARD_MAX_BYTES = MAX_IMAGE_BODY  # thân hợp lệ lớn nhất vẫn nhận được phản hồi
DISCARD_SECONDS = 2.0               # hạn tổng, client nhỏ giọt cũng không giữ luồng lâu hơn
DISCARD_CHUNK = 64 * 1024
# Media trang Chat (23/11/2026): gửi từng khúc, hạn đặt lại cho từng khúc (~4 KB/s trở lên vẫn nhận đủ), không phải cho cả file.
MEDIA_CHUNK = 64 * 1024
MEDIA_CHUNK_SECONDS = 15.0
# Trần tổng cho một lần gửi: client nhỏ giọt ~4 KB/s không giữ luồng hàng giờ với video lớn. Hạn = max(60 giây, cỡ / 32 KB/s).
MEDIA_MIN_SECONDS = 60.0
MEDIA_MIN_RATE = 32 * 1024
MEDIA_CLOCK = time.monotonic        # test thay đồng hồ để kiểm trần mà không phải chờ
# Audit 23/11/2026 (F1–F3): độ sẵn sàng của hai cổng. Bắt tay TLS của cổng 8445 chạy trong luồng xử lý, tối đa 5 giây
# (trước đây chạy trong luồng nhận kết nối, một kết nối im làm treo cả cổng). Phần đầu yêu cầu có hạn tuyệt đối 10 giây,
# thân lệnh và thân trả lời có hạn theo tốc độ tối thiểu chứ không phải 5 giây cho cả lần gửi.
TLS_HANDSHAKE_SECONDS = 5.0
HEAD_SECONDS = 10.0                 # dòng đầu + header: client nhỏ giọt từng byte không giữ luồng quá hạn này
UPLOAD_MIN_RATE = 16 * 1024         # thân lệnh: hạn = max(HEAD_SECONDS, cỡ / 16 KB/s)
BODY_CHUNK = 256 * 1024             # thân trả lời gửi từng lát, hạn đặt lại cho từng lát (~8,7 KB/s trở lên vẫn nhận đủ)
BODY_CHUNK_SECONDS = 30.0
BODY_MIN_SECONDS = 60.0             # trần tổng một thân trả lời = max(60 giây, cỡ / 32 KB/s)
BODY_MIN_RATE = 32 * 1024
WORKERS = 96                        # luồng xử lý tối đa mỗi cổng; SSE tối đa 40 (v7_presence) vẫn còn chỗ cho trang


def declared_length(value: str, limit: int) -> int | None:
    """Content-Length đã kiểm: sai thì None; vượt `limit` thì limit + 1, không đổi chuỗi số dài thành int."""
    if not value.isascii() or not value.isdecimal():
        return None
    digits = value.lstrip("0")
    return int(digits or "0") if len(digits) <= len(str(limit)) else limit + 1


def body_limit(path: str) -> int:
    """Trần thân POST: ảnh chứng từ lớn nhất, lệnh lưu chặng đội xe (tới 200 dòng dán) lớn hơn lệnh thường."""
    return MAX_IMAGE_BODY if path == IMAGE_PATH else v7_api_doixe.MAX_CHANG_BODY if path == v7_api_doixe.CHANG_PATH else MAX_BODY


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
    """`SELECT 1` qua đúng runner psql của app, kèm tuổi bản chụp Sheet và tình trạng hộp việc (chỉ số đếm); DB lỗi thì 503
    (audit DevOps #6, #14). Hộp việc không làm đỏ kiểm sống: máy canh đọc và tự quyết báo (CANH-BAO-01, bổ sung 18/11/2026)."""
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
    body = {"ok": db_ok, "db": "ok" if db_ok else "error", "sheet_snapshot_age_seconds": age, "inbox": INBOX.health(now)}
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


def asset_versions(name: str, marked: bool = False) -> tuple[bytes, bytes, str]:
    """(nguyên bản, bản gzip, ETag) của một file preview; file dưới GZIP_MIN_BYTES giữ bản gzip bằng nguyên bản.

    marked (QUYEN-01): bản trang HTML cho người dùng, thẻ <html> có data-role="user"; giữ riêng trong bộ nhớ đệm và
    ETag khác bản quản lý, nên trình duyệt không lấy nhầm bản của vai trò kia."""
    path = PREVIEW / name
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    slot = name + "#user" if marked else name
    with _ASSET_LOCK:
        held = _ASSET_CACHE.get(slot)
        if held is not None and held[0] == key:
            return held[1:]
    data = path.read_bytes()
    if marked:
        data = v7_role.mark_html(data)
    packed = gzip.compress(data, compresslevel=6, mtime=0) if len(data) >= GZIP_MIN_BYTES else data
    etag = '"' + hashlib.sha256(data).hexdigest()[:32] + '"'
    with _ASSET_LOCK:
        _ASSET_CACHE[slot] = (key, data, packed, etag)
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
    "/api/v7/cash-chat/review": v7_cash_chat.handle_review,   # ZALO-THU-CHI-01 PR-3: chỉ quản lý (v7_role), không ghi tiền
    "/api/v7/machine/office": v7_machine.handle_office,
    **v7_api_doixe.POST_HANDLERS,   # CHI-PHI-XE-01: đội xe
    "/api/v7/admin/users": v7_access.handle_users,   # QUYEN-02: trang Người dùng, chỉ quản lý (v7_role)
    "/api/v7/admin/customers": v7_api_khach.handle_create,   # KHACH-WEB-01: trang Khách, chỉ quản lý (v7_role)
    "/api/v7/admin/booking-names": v7_api_khach.handle_booking_name,   # KHACH-WEB-01
}
MACHINE_READS = {"/api/v7/machine": v7_machine.view, "/api/v7/machine/now": v7_machine.now_view, "/api/v7/machine/summary": v7_machine.summary}
# Kết quả đọc được gắn cờ demo/real_copy để giao diện ghi rõ nguồn dữ liệu.
FLAGGED_READS = ("get_ledger", "list_customers", "list_offset_sources", "get_dashboard", "get_dashboard_debt", "get_receivables_matrix", "get_receipt_book")


def handle(method: str, target: str, headers: dict[str, str], raw: bytes, runner: Psql, *,
           port: int, host: str, default_actor: str | None = None, actor: str | None = None,
           source_ip: str = "", source_port: int = 0, localapi=None, behind_tailscale_serve: bool = False,
           demo: bool = False, real_copy: bool = False, serve_hosts: tuple[str, ...] = (),
           allowed_logins: frozenset[str] | None = None, local_port: int = 0,
           read_only_uids: frozenset[int] = frozenset()) -> tuple[int, dict]:
    headers = {name.lower(): value for name, value in headers.items()}
    request_host = checked_host(headers.get("host", ""), port, host, behind_tailscale_serve, serve_hosts)
    if method == "POST":
        expected_origin = f"https://{request_host}" if behind_tailscale_serve and request_host in serve_hosts else f"http://{request_host}"
        if headers.get("origin") != expected_origin:
            raise ApiError(403, "INVALID_ORIGIN", "Nguồn yêu cầu không hợp lệ.")
        if headers.get("content-type", "").lower() != "application/json":
            raise ApiError(415, "INVALID_CONTENT_TYPE", "Cần gửi JSON.")
        parts = urlsplit(target)
        if len(raw) > body_limit(parts.path):
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
                                          behind_tailscale_serve=behind_tailscale_serve, allowed_logins=allowed_logins,
                                          local_port=local_port, read_only_uids=read_only_uids, write=method != "GET")
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
    elif parts.path == "/api/v7/todo-badge":   # số đệm menu Quản trị: ba nguồn của Việc cần làm, chỉ phần hàm đếm cần
        return 200, v7_todo_badge.handle_get(parts.query, runner, READS, INBOX, actor)
    elif parts.path == "/api/v7/machine/booking":
        # KIEM-BOOKING-01: kết quả kiểm Sheet sổ nợ so với booking (file của lượt đối soát), sau xác thực danh tính. Dòng
        # "tháng này chưa lên sổ" được gắn chuyến web qua get_trip_month (bộ nhớ đọc), để tách chuyến máy đã đưa vào sổ web.
        if parts.query:
            bad()
        return 200, v7_booking_view.with_web(v7_booking_view.view(), runner, READS, actor)
    elif parts.path == "/api/v7/cash-chat":
        # ZALO-THU-CHI-01: khoản thu/chi/ứng báo trong nhóm Zalo đã chọn, đối chiếu chỉ đọc với phiếu thu và Đội xe; tin chat không vào model.
        return 200, v7_cash_chat.handle_get(parts.query, runner, actor)
    elif parts.path == "/api/v7/cash-chat/targets":
        # Luồng 3: danh sách sổ, xe, tài xế cho ô "Gắn sổ/xe"; chỉ đọc qua list_customers và doixe_get_tong.
        return 200, v7_cash_chat.handle_targets(parts.query, runner, actor)
    elif parts.path == "/api/v7/report/month":
        # BAO-CAO-THANG-01: chuyến theo tháng ngày chuyến, booking ↔ Sheet (file của phép kiểm booking) ↔ web (get_trip_month).
        return 200, v7_month_report.handle_get(parts.query, runner, READS, actor)
    elif parts.path == "/api/v7/report/month/missing":
        # BAO-CAO-THANG-02: chuyến booking có mà web chưa có, kèm lý do máy giữ; trang chỉ gọi khi người dùng mở danh sách.
        return 200, v7_month_missing.handle_get(parts.query, runner, READS, actor)
    elif parts.path in MACHINE_READS:
        # MAY-CHAY-01: đọc file của job, không qua DB; vẫn sau xác thực danh tính như mọi route.
        if parts.query:
            bad()
        body = MACHINE_READS[parts.path]()
        # Bản cho Hermes không được có chữ lấy từ Sheet, nên việc của hộp chờ chỉ đi cùng hai route cho trang.
        return 200, body if parts.path == "/api/v7/machine/summary" else {**body, "auto": INBOX.auto_today()}
    elif parts.path == "/api/v7/sheet/doi-chieu":
        _, payload = validate_get("/api/v7/ledger", parts.query)
        return 200, v7_api_doi_chieu.statement(payload["customer_id"], v7_read_cache.CachedReads(runner, READS), actor)
    elif parts.path == "/api/v7/sheet/vung-o":
        # KIEM-TAB-01 3c: vùng ô của một chỗ sai để dựng lại; chỉ đọc Sheet, vùng do server tính, không nhận A1.
        return 200, v7_api_doi_chieu.region(parts.query, v7_read_cache.CachedReads(runner, READS), actor)
    elif parts.path == "/api/v7/ai/preview":
        _, payload = validate_get("/api/v7/ledger", parts.query)
        return 200, v7_ai_explain.preview(payload["customer_id"], runner, actor)
    elif parts.path == "/api/v7/debit-note/config":
        # DEBIT-NOTE-03: file cấu hình ngoài DB (mẫu, công ty, ngân hàng, tên phí); vẫn sau xác thực danh tính.
        try:
            return v7_debit_note_config.handle_get(parts.query)
        except v7_debit_note_config.ConfigError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc
    elif parts.path == "/api/v7/company-info":
        # THONG-TIN-CTY-01: bản chụp Sheet thông tin khách hàng do timer ghi, ngoài DB; vẫn sau xác thực danh tính.
        try:
            return v7_company_info.handle_get(parts.query)
        except v7_company_info.InfoError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc
    elif parts.path == v7_api_doixe.PREFIX or parts.path.startswith(v7_api_doixe.PREFIX + "/"):
        # CHI-PHI-XE-01: đọc đội xe (schema doixe), thẳng runner như mọi đọc không nằm trong bộ nhớ đọc; tên ngắn cho người làm.
        names = PRESENCE.names()
        # DOI-XE-CHANG-01: mục Chặng gộp bản chụp booking (ngoài DB) với get_dieu_do và get_chang_tai_chinh.
        result = v7_api_doixe.read_route(parts.path, parts.query, runner, actor)
        if result is None:
            function, payload = v7_api_doixe.parse_get(parts.path, parts.query)
            result = runner.run(function, payload, actor)
        return 200, v7_api_doixe.with_names(result, lambda login: v7_presence.display_name(login, names))
    elif parts.path == "/api/v7/admin/users":
        # QUYEN-02: danh sách login được vào sổ, ngoài DB; v7_role chặn người không phải quản lý trước khi tới đây.
        if parts.query:
            bad()
        return 200, v7_access.view_users(actor)
    elif parts.path == "/api/v7/admin/customers":
        # KHACH-WEB-01: mọi sổ kèm tên chủ hàng booking và chủ hàng chưa có sổ; v7_role chặn người không phải quản lý trước khi tới đây.
        if parts.query:
            bad()
        return 200, v7_api_khach.view(runner, actor)
    elif parts.path == "/api/v7/nhat-ky":
        # NHAT-KY-01: PR đã merge của repo do luồng nền đọc từ GitHub, ngoài DB; vẫn sau xác thực danh tính.
        if parts.query:
            bad()
        return 200, v7_nhat_ky.view()
    elif parts.path == "/api/v7/marks":
        function, payload = v7_api_zalo.parse_marks(parts.query)
    elif parts.path.startswith("/api/v7/zalo/") and parts.path != "/api/v7/zalo/links":
        # ZALO-CHAT-01: đọc bản xuất chat ngoài DB; vẫn qua xác thực danh tính như mọi route.
        # /api/v7/zalo/links (ZALO-GROUP-01) là bảng gắn sổ trong DB nên đi đường đọc DB như mọi route.
        try:
            status, body = v7_zalo_chat.handle_get(parts.path, parts.query)
        except v7_zalo_chat.ChatError as exc:
            raise ApiError(exc.status, exc.code, exc.message) from exc
        if parts.path == "/api/v7/zalo/report":
            # Giờ dựng gói chỉ đổi lúc dựng lại đầy đủ; tin lên liên tục qua delta. Trang Chat Zalo cần nhịp tim máy Zalo để ghi
            # "cập nhật lúc …" cho đúng và "lần cuối" khi máy im (ZALO-THU-CHI-01 "Bị chặn"), cùng luật trang Thu chi.
            body = {**body, "zalo": v7_machine.zalo_brief()}
        return status, body
    else:
        function, payload = validate_get(parts.path, parts.query)
    # HIEU-NANG-01: GET đọc nặng qua bộ nhớ theo dấu dữ liệu (dấu mới mỗi lượt: đọc ngay sau ghi thấy bản mới); POST đi thẳng.
    result = READS.run(runner, function, payload, actor) if method == "GET" else runner.run(function, payload, actor)
    if method == "POST" and function != "preview_price_table":   # xem trước không ghi gì
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


class _DeadlineReader(io.RawIOBase):
    """rfile của Handler (audit 23/11/2026, F3): mỗi lần recv có hạn = min(hạn nghỉ của lớp, thời gian còn tới mốc tuyệt đối).

    Hạn của socket chỉ tính cho từng lần recv, nên client gửi một byte mỗi 4 giây giữ luồng mãi. Mốc `read_deadline` do
    Handler đặt: HEAD_SECONDS cho phần đầu, theo cỡ cho thân lệnh, hạn xả cho thân bị từ chối.
    """

    def __init__(self, handler: Handler):
        super().__init__()
        self.handler = handler

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        left = self.handler.read_deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("request read deadline")
        self.handler.connection.settimeout(min(self.handler.timeout, left))
        return self.handler.connection.recv_into(buffer)


class Handler(BaseHTTPRequestHandler):
    runner: Psql
    bind_host = "127.0.0.1"
    port = 8780
    default_actor = None
    dev_actor_mode = None
    behind_tailscale_serve = False
    serve_hosts: tuple[str, ...] = ()
    allowed_logins: frozenset[str] | None = None  # ACCESS-01; None only outside Serve mode
    admin_logins: frozenset[str] | None = None  # QUYEN-01; None: every allowed login is admin
    localapi = None
    read_only_uids: frozenset[int] = frozenset()   # F4: uid cục bộ được dùng header danh tính chỉ để đọc (bot Zalo)
    demo = False
    real_copy = False
    body_taken = False
    response_started = False   # đầu trả lời đã gửi: lỗi sau đó chỉ còn cách đóng kết nối, không trả lời lần hai
    status_sent: int | None = None
    actor: str | None = None
    read_deadline = 0.0
    # Audit 19/11/2026 (A10): StreamRequestHandler.setup đặt hạn này cho socket TRƯỚC khi đọc dòng đầu và header. Trước đây
    # hạn 5 giây chỉ đặt trong _request, tức sau khi header đã đọc xong: client gửi header dở dang giữ một luồng mãi mãi.
    # Hết hạn lúc đọc header thì handle_one_request đóng kết nối; kết nối keep-alive rảnh quá hạn cũng đóng như vậy.
    timeout = 5

    def setup(self) -> None:
        super().setup()
        self.read_deadline = time.monotonic() + HEAD_SECONDS
        self.rfile.close()
        self.rfile = io.BufferedReader(_DeadlineReader(self))

    def send_response(self, code: int, message: str | None = None) -> None:
        self.status_sent = code
        super().send_response(code, message)

    def end_headers(self) -> None:
        self.response_started = True   # trước khi gửi: lỗi giữa chừng vẫn coi như client đã nhận một phần
        super().end_headers()

    def send_body(self, data: bytes) -> None:
        """Thân trả lời theo lát (audit 23/11/2026, F2): hạn đặt lại cho từng lát, trần tổng theo cỡ.

        Hạn của socket áp cho cả lần sendall: một lần ghi 8 MB trên mạng điện thoại bị cắt sau 5 giây. Ghi từng lát thì
        client chậm mà đều vẫn nhận đủ; client đứng im quá BODY_CHUNK_SECONDS hoặc quá trần tổng thì kết nối bị đóng.
        """
        view = memoryview(data)
        deadline = time.monotonic() + max(BODY_MIN_SECONDS, len(data) / BODY_MIN_RATE)
        try:
            for start in range(0, len(view), BODY_CHUNK):
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("response write deadline")
                self.connection.settimeout(min(BODY_CHUNK_SECONDS, left))
                self.wfile.write(view[start:start + BODY_CHUNK])
        finally:
            self.connection.settimeout(self.timeout)

    def fail(self, status: int, value: dict) -> None:
        """Trả lời lỗi; đầu trả lời đã đi rồi thì chỉ đóng kết nối (thân đã hứa Content-Length, chèn JSON là hỏng file)."""
        if self.response_started:
            self.close_connection = True
            print(f"V7 API: bỏ dở trả lời {self.status_sent} {self.command} {urlsplit(self.path).path} "
                  f"({value.get('error')})", file=sys.stderr, flush=True)
            return
        self.reply(status, value)

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
        deadline = self.read_deadline = time.monotonic() + DISCARD_SECONDS
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

    def asset(self, role: str = v7_role.ADMIN) -> bool:
        route = urlsplit(self.path).path
        if self.command != "GET" or route not in ASSETS:
            return False
        checked_host(self.headers.get("Host", ""), self.port, self.bind_host,
                     self.behind_tailscale_serve, self.serve_hosts)
        name, kind = ASSETS[route]
        data, packed, etag = asset_versions(name, marked=role == v7_role.USER and route in PAGES)
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
        self.send_body(data)
        return True

    def forbidden_page(self) -> None:
        """QUYEN-01: người dùng gõ địa chỉ trang quản lý thì thấy một câu và link về Tổng quan, không phải JSON."""
        data = v7_role.FORBIDDEN_PAGE
        self.send_response(403)
        for name, field in (("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(data))),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                            ("X-Frame-Options", "DENY"),
                            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")):
            self.send_header(name, field)
        self.end_headers()
        self.send_body(data)

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
        self.send_body(data)

    def send_export(self, actor: str) -> None:
        """XUAT-SO-01: dựng file cả sổ rồi gửi; kết quả tự kiểm ở header `X-Xuat-So`, journal ghi một dòng số đếm."""
        if not EXPORT_LOCK.acquire(blocking=False):
            raise ApiError(429, "EXPORT_BUSY", "Đang có một lượt xuất khác. Chờ khoảng một phút rồi bấm lại.")
        started = time.monotonic()
        prefix = "so-web-du-lieu-gia" if self.demo else "so-web-ban-sao" if self.real_copy else "so-web"
        try:
            result = v7_book_export.export(self.runner, actor, datetime.now(VN), names=with_display_names, prefix=prefix)
        except ApiError:
            raise
        except Exception as exc:   # dữ liệu sổ khác hình dạng đã biết hay lỗi dựng file: báo gọn, không gửi nửa file
            print(f"XUAT-SO-01: {actor} xuất lỗi {type(exc).__name__}", file=sys.stderr, flush=True)
            raise ApiError(503, "EXPORT_FAILED", "Chưa xuất được cả sổ. Báo quản trị kiểm.") from exc
        finally:
            EXPORT_LOCK.release()
        found = ",".join(problem["code"] for problem in result.problems) or "khớp"
        print(f"XUAT-SO-01: {actor} tải cả sổ: {result.books} sổ, kiểm {found}, {len(result.data)} byte, "
              f"{time.monotonic() - started:.1f} giây", file=sys.stderr, flush=True)
        self.send_response(200)
        for name, field in (("Content-Type", XLSX_TYPE), ("Content-Length", str(len(result.data))),
                            ("Content-Disposition", f'attachment; filename="{result.filename}"'),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                            ("X-Xuat-So", result.header())):
            self.send_header(name, field)
        self.end_headers()
        self.send_body(result.data)

    def send_doixe_xlsx(self, actor: str, query: str) -> None:
        """DOI-XE-THU-01: file Excel bảng kê tháng gửi HTH, dựng từ đúng dữ liệu đọc của màn Bảng kê."""
        function, payload = v7_api_doixe.parse_get(v7_api_doixe.XLSX_PATH, query)
        data = self.runner.run(function, payload, actor)
        try:
            filename, body = v7_doixe_xlsx.build(data)
        except (v7_doixe_xlsx.ExportError, KeyError, TypeError, ValueError) as exc:
            print(f"DOI-XE-THU-01: {actor} xuất bảng kê lỗi {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            raise ApiError(503, "EXPORT_FAILED", "Chưa xuất được bảng kê. Báo quản trị kiểm.") from exc
        self.send_response(200)
        for name, field in (("Content-Type", XLSX_TYPE), ("Content-Length", str(len(body))),
                            ("Content-Disposition", f'attachment; filename="{filename}"'),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")):
            self.send_header(name, field)
        self.end_headers()
        self.send_body(body)

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

    def send_media(self, kind: str, path: os.PathLike[str], range_header: str | None) -> None:
        """Media của trang Chat: một khoảng Range → 206, ngoài cỡ → 416, còn lại 200; gửi từng khúc từ file.

        Safari iOS chỉ phát <video>/<audio> khi máy chủ nhận `Range` (nó hỏi `bytes=0-1` trước). Hạn 5 giây của
        _request áp cho cả lần sendall, nên video lớn trên mạng chậm bị cắt: ở đây hạn được đặt lại cho từng khúc.
        """
        with open(path, "rb") as handle:
            size = os.fstat(handle.fileno()).st_size   # cỡ của chính file đang mở, không phải của lần stat trước
            status, first, last = 200, 0, size - 1
            try:
                window = v7_zalo_chat.byte_range(range_header, size)
            except v7_zalo_chat.RangeNotSatisfiable:
                status = 416
            else:
                if window is not None:
                    status, (first, last) = 206, window
            length = 0 if status == 416 else last - first + 1
            fields = [("Content-Type", kind), ("Accept-Ranges", "bytes"), ("Content-Length", str(length)),
                      ("Cache-Control", "private, max-age=86400"), ("X-Content-Type-Options", "nosniff")]
            if status == 416:
                fields.append(("Content-Range", f"bytes */{size}"))
            elif status == 206:
                fields.append(("Content-Range", f"bytes {first}-{last}/{size}"))
            self.send_response(status)
            for name, field in fields:
                self.send_header(name, field)
            self.end_headers()
            if not length:
                return
            handle.seek(first)
            remaining = length
            deadline = MEDIA_CLOCK() + max(MEDIA_MIN_SECONDS, length / MEDIA_MIN_RATE)
            self.close_connection = True   # đã hứa Content-Length: bỏ dở giữa chừng thì chỉ có đóng kết nối là báo được cho client
            try:
                while remaining:
                    left = deadline - MEDIA_CLOCK()
                    chunk = handle.read(min(remaining, MEDIA_CHUNK)) if left > 0 else b""
                    if not chunk:   # quá trần tổng, hoặc file ngắn đi giữa chừng: dừng, không giữ luồng/treo client
                        return
                    self.connection.settimeout(min(MEDIA_CHUNK_SECONDS, left))
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except TimeoutError:
                pass   # client đứng quá hạn khúc: đầu trả lời đã đi, không chèn JSON 408 vào thân
            finally:
                self.connection.settimeout(self.timeout)   # máy chủ chạy HTTP/1.0: kết nối đóng sau yêu cầu, đặt lại hạn thường cho phần dọn dẹp

    def request(self) -> None:
        started = time.monotonic()
        try:
            self._request()
        except OSError as exc:
            # Client ngắt giữa chừng (audit DevOps 31/10, #15), hoặc ghi quá hạn/TLS hỏng khi đang gửi (audit 23/11, F2):
            # một dòng log, không traceback, không trả lời nữa.
            self.close_connection = True
            print(f"V7 API: client ngắt kết nối ({type(exc).__name__}) {self.command} {urlsplit(self.path).path}",
                  file=sys.stderr, flush=True)
            return   # đã có một dòng cho yêu cầu này
        self.log_outcome(started)

    def log_outcome(self, started: float) -> None:
        """F11: một dòng journal cho mỗi POST và mỗi trả lời không 2xx/304 (không thân, không query: có thể chứa mã sổ)."""
        status = self.status_sent
        if self.command == "POST" or status is None or not (200 <= status < 300 or status == 304):
            print(f"V7 API: {self.command} {urlsplit(self.path).path} -> {status or 'không trả lời'} "
                  f"{self.actor or '-'} {(time.monotonic() - started) * 1000:.0f} ms", file=sys.stderr, flush=True)

    def _request(self) -> None:
        try:
            self.connection.settimeout(5)
            for name in ("Host", "Origin", "Content-Length", "Content-Type", "Tailscale-User-Login", "Sec-Fetch-Site"):
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
            # Audit 23/11/2026 (F7): trang khác mở trong trình duyệt của người được phép không được gọi /api/ (kể cả GET:
            # không đọc được kết quả nhưng vẫn bắt máy chủ làm việc). Trình duyệt không gửi header này (curl, bot) thì cho qua.
            if (urlsplit(self.path).path.startswith("/api/")
                    and self.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none")):
                raise ApiError(403, "CROSS_SITE", "Yêu cầu từ trang khác bị chặn.")
            # QUYEN-02: danh sách có hiệu lực gộp phần cố định (cấu hình unit) với file sửa trên trang Người dùng.
            # Chưa đặt file thì giữ đúng danh sách của lớp Handler (test thay thuộc tính lớp).
            store = v7_access.STORE
            allowed_logins, admin_logins = (store.lists() if store is not None and store.path is not None
                                            else (self.allowed_logins, self.admin_logins))
            actor = self.server.dev_actor
            if actor is None:
                actor = v7_identity.resolve_actor(self.client_address[0], self.headers, self.localapi,
                                                  source_port=self.client_address[1], behind_tailscale_serve=self.behind_tailscale_serve,
                                                  allowed_logins=allowed_logins, local_port=self.connection.getsockname()[1],
                                                  read_only_uids=self.read_only_uids, write=self.command != "GET")
            self.actor = actor
            route = urlsplit(self.path)
            role = v7_role.role(actor, admin_logins)
            if not v7_role.allowed(route.path, role, PAGES):
                if route.path in PAGES:
                    self.forbidden_page()
                    return
                raise ApiError(403, "ADMIN_ONLY", v7_role.FORBIDDEN_MESSAGE)
            if self.command == "GET" and route.path == "/api/v7/presence/stream":
                self.stream(actor, presence_tab(route.query))
                return
            if self.asset(role):
                return
            if self.command == "GET" and route.path.startswith(v7_zalo_chat.MEDIA_PREFIX):
                # ZALO-GROUP-01: ảnh của gói chat, sau xác thực danh tính như mọi /api/v7/*.
                try:
                    kind, media = v7_zalo_chat.handle_media(route.path, route.query)
                except v7_zalo_chat.ChatError as exc:
                    raise ApiError(exc.status, exc.code, exc.message) from exc
                ranges = self.headers.get_all("Range", [])
                self.send_media(kind, media, ranges[0] if len(ranges) == 1 else None)
                return
            if self.command == "GET" and route.path.startswith(v7_insurance_queue.CERT_PREFIX):
                # BAO-HIEM-ZALO-01: PDF giấy bảo hiểm, sau xác thực danh tính như mọi /api/v7/*; chỉ giấy trong bản chụp hiện tại.
                if route.query:
                    bad()
                data = v7_api_sheet.insurance_cert(route.path.removeprefix(v7_insurance_queue.CERT_PREFIX))
                self.send_response(200)
                for name, field in (("Content-Type", "application/pdf"), ("Content-Length", str(len(data))),
                                    ("Content-Disposition", 'inline; filename="giay-bao-hiem.pdf"'),
                                    ("Cache-Control", "private, no-store"), ("X-Content-Type-Options", "nosniff"),
                                    ("Referrer-Policy", "no-referrer")):
                    self.send_header(name, field)
                self.end_headers()
                self.send_body(data)
                return
            if self.command == "GET" and route.path == v7_api_doixe.XLSX_PATH:
                self.send_doixe_xlsx(actor, route.query)
                return
            if self.command == "GET" and route.path == EXPORT_PATH:
                # XUAT-SO-01: file cả sổ, sau xác thực danh tính như mọi /api/v7/*.
                if route.query:
                    bad()
                self.send_export(actor)
                return
            raw = b""
            if self.command == "POST":
                limit = body_limit(urlsplit(self.path).path)
                length_value = declared_length(self.headers.get("Content-Length", ""), limit)
                if length_value is None:
                    bad()
                if length_value > limit:
                    raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
                self.body_taken = True  # kể cả khi đọc hết giờ (408): client chậm không được giữ thêm luồng để xả
                # F3: hạn tuyệt đối theo cỡ thân (tối thiểu 16 KB/s), không phải 5 giây cho mỗi lần recv.
                self.read_deadline = time.monotonic() + max(HEAD_SECONDS, length_value / UPLOAD_MIN_RATE)
                raw = self.rfile.read(length_value)
                if len(raw) != length_value:
                    bad()
            status, value = handle(self.command, self.path, dict(self.headers), raw, self.runner,
                                   port=self.port, host=self.bind_host, default_actor=self.default_actor,
                                   actor=actor, demo=self.demo, real_copy=self.real_copy,
                                   serve_hosts=self.serve_hosts, behind_tailscale_serve=self.behind_tailscale_serve,
                                   allowed_logins=allowed_logins)
            self.reply(status, value)
        except v7_identity.IdentityError as exc:
            if exc.code == "LOGIN_NOT_ALLOWED":
                # ACCESS-01: the login goes to the journal (so the admin knows whom to add), never to the client.
                print(f"ACCESS-01: từ chối login ngoài danh sách: {exc.detail} (peer {self.client_address[0]})",
                      file=sys.stderr, flush=True)
                v7_access.DENIED.record(exc.detail)   # QUYEN-02: trang Người dùng cho vào bằng một bấm
                self.fail(403, {"error": exc.code,
                                "message": "Tài khoản này chưa được cấp quyền dùng sổ. Báo quản trị thêm vào danh sách."})
            else:
                if exc.code in ("UNTRUSTED_LOCAL_PEER", "READ_ONLY_PEER"):
                    # F4: tiến trình cục bộ không phải tailscaled gửi header danh tính; uid vào journal, không vào trả lời.
                    print(f"ACCESS-01: từ chối header danh tính từ tiến trình cục bộ ({exc.code}, {exc.detail}) "
                          f"{self.command} {urlsplit(self.path).path}", file=sys.stderr, flush=True)
                self.fail(403, {"error": exc.code})
        except TimeoutError:
            self.fail(408, {"error": "REQUEST_TIMEOUT", "message": "Yêu cầu gửi quá chậm."})
        except ApiError as exc:
            self.fail(exc.status, {"error": exc.code, "message": exc.message, **exc.extra})
        except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
            raise  # request() ghi một dòng; không cố gửi 503 vào kết nối đã đứt
        except OSError:
            self.fail(503, {"error": "ASSET_UNAVAILABLE", "message": "Không đọc được trang thử."})
        except Exception as exc:  # noqa: BLE001  mọi lỗi lạ vẫn có trả lời 500, không traceback
            # F6: lỗi bất ngờ (ví dụ file của job khác hình dạng) vẫn có trả lời và mã lỗi; journal một dòng, không traceback.
            print(f"V7 API: lỗi bất ngờ {type(exc).__name__} {self.command} {urlsplit(self.path).path} {self.actor or '-'}",
                  file=sys.stderr, flush=True)
            self.fail(500, {"error": "INTERNAL", "message": "Máy chủ gặp lỗi. Báo quản trị kiểm."})

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
        if enabled and handler.behind_tailscale_serve:
            # F8: mọi người tới được Serve sẽ là `dev:<tên>` có quyền ghi; hai chế độ không bao giờ đi cùng nhau.
            raise ValueError("dev actor cannot be combined with Tailscale Serve mode")
        self.dev_actor = None
        if enabled:
            if not isinstance(name, str) or not name.strip() or len(name) > 252 or any(ord(c) < 32 for c in name):
                raise ValueError("invalid dev actor")
            self.dev_actor = "dev:" + name.strip()
        self.slots = threading.BoundedSemaphore(WORKERS)
        super().__init__(server_address, handler, bind_and_activate=bind_and_activate)
        if enabled:
            print("WARNING: insecure dev actor enabled; identity verification bypassed (loopback only)", file=sys.stderr)

    def process_request(self, request, client_address) -> None:
        # F3: tối đa WORKERS luồng xử lý. Hết chỗ thì luồng nhận kết nối chờ: kết nối mới nằm ở hàng đợi của kernel
        # (request_queue_size) thay vì mở luồng không giới hạn; mọi hạn đọc/ghi bảo đảm chỗ được trả lại.
        self.slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class TailnetHTTPSServer(ThreadingHTTPServer):
    """Cổng HTTPS trực tiếp trên IP tailnet (8445): luồng nhận kết nối chỉ accept TCP, bắt tay TLS trong luồng xử lý.

    Audit 23/11/2026 (F1): trước đây socket nghe được bọc TLS, nên accept() bắt tay ngay trong luồng nhận kết nối, không
    có hạn: một kết nối TCP im (máy quét cổng, điện thoại mất sóng giữa chừng) làm treo cả cổng cho mọi người. Nay mỗi
    bắt tay có hạn tuyệt đối TLS_HANDSHAKE_SECONDS (hạn của socket tính cho cả lần do_handshake), hỏng thì đóng lặng lẽ.
    """

    def __init__(self, server_address, handler, context: ssl.SSLContext, *, bind_and_activate=True):
        self.tls_context = context
        super().__init__(server_address, handler, tailnet_https=True, bind_and_activate=bind_and_activate)

    def finish_request(self, request, client_address) -> None:
        try:
            request.settimeout(TLS_HANDSHAKE_SECONDS)
            secure = self.tls_context.wrap_socket(request, server_side=True)
        except OSError:   # gồm ssl.SSLError, TimeoutError, client đóng giữa chừng; shutdown_request đóng socket gốc
            return
        try:
            super().finish_request(secure, client_address)
        finally:
            self.shutdown_request(secure)   # socket gốc đã tách sang `secure`; lớp cha chỉ còn đóng vỏ rỗng


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
    # F8 (audit 23/11/2026): chỉ bật bằng cờ dòng lệnh, không bằng biến môi trường (dễ sót trong drop-in hay profile).
    parser.add_argument("--insecure-dev-actor")
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
    parser.add_argument("--admin-login", action="append", default=[],
                        help="Tailscale login that sees the admin pages (QUYEN-01); repeatable, merged with "
                             "WEBDEBIT_ADMIN_LOGINS. Unset: every allowed login is admin")
    parser.add_argument("--read-only-peer-uid", action="append", default=[],
                        help="Local uid allowed to send the Tailscale identity header for GET only (F4, e.g. the Zalo bot); "
                             "repeatable, merged with WEBDEBIT_READ_ONLY_PEER_UIDS. uid 0 (tailscaled) is always trusted")
    parser.add_argument("--access-file", default=os.getenv("WEBDEBIT_ACCESS_FILE"),
                        help="JSON file of logins managed on the Người dùng page (QUYEN-02); added to the fixed lists")
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
    if args.insecure_dev_actor is not None and args.behind_tailscale_serve:
        parser.error("--insecure-dev-actor cannot be combined with Tailscale Serve mode (F8)")
    peer_env = os.getenv("WEBDEBIT_READ_ONLY_PEER_UIDS")
    try:
        read_only_uids = v7_identity.parse_peer_uids(" ".join([*args.read_only_peer_uid, peer_env or ""]))
    except v7_identity.IdentityError:
        parser.error("read-only peer uids must be positive integers other than 0 (F4)")
    if read_only_uids and not args.behind_tailscale_serve:
        parser.error("--read-only-peer-uid requires --behind-tailscale-serve")
    if any((args.tailnet_https_ip, args.tailnet_https_host, args.tailnet_tls_cert, args.tailnet_tls_key)):
        if not all((args.tailnet_https_ip, args.tailnet_https_host, args.tailnet_tls_cert, args.tailnet_tls_key)):
            parser.error("tailnet HTTPS requires IP, host, certificate and key")
        if not args.behind_tailscale_serve:
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
    if args.behind_tailscale_serve and not allowed_logins:
        parser.error("--behind-tailscale-serve requires at least one allowed login "
                     "(--allowed-login or WEBDEBIT_ALLOWED_LOGINS; ACCESS-01)")
    # QUYEN-01: admin list lives next to the allowlist on the host. Each admin must also be allowed, or the list is a typo.
    admin_env = os.getenv("WEBDEBIT_ADMIN_LOGINS")
    admin_raw = None
    if args.admin_login or admin_env is not None:
        admin_raw = ",".join([*args.admin_login, admin_env or ""])
    try:
        admin_logins = v7_identity.parse_allowed_logins(admin_raw)
    except v7_identity.IdentityError as exc:
        parser.error(f"admin logins invalid: {exc.code}")
    if admin_logins is not None and not admin_logins:
        parser.error("admin logins set but empty (QUYEN-01)")
    if admin_logins and allowed_logins is not None and not admin_logins <= allowed_logins:
        parser.error("every admin login must also be an allowed login (QUYEN-01)")
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
    Handler.admin_logins = admin_logins
    Handler.read_only_uids = read_only_uids
    if args.access_file and not os.path.isdir(os.path.dirname(os.path.abspath(args.access_file))):
        parser.error("access file folder does not exist (QUYEN-02)")
    v7_access.STORE = v7_access.AccessStore(args.access_file, allowed_logins, admin_logins)
    Handler.demo = args.demo
    Handler.real_copy = args.real_copy
    v7_zalo_chat.warm()
    secure = None
    if args.tailnet_https_ip:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.tailnet_tls_cert, args.tailnet_tls_key)
        # F1: socket nghe để trần; mỗi kết nối bắt tay TLS trong luồng của nó, có hạn (TailnetHTTPSServer).
        secure = TailnetHTTPSServer((args.tailnet_https_ip, args.tailnet_https_port), Handler, context)
    plain = ThreadingHTTPServer((args.host, args.port), Handler)
    INBOX.start(Handler.runner)   # tính sẵn hộp ngoại lệ ở nền ngay khi khởi động
    INBOX.keep_fresh(Handler.runner)   # rồi tính lại theo từng đợt Sheet, kể cả khi không ai mở Việc cần làm
    v7_nhat_ky.journal().start()       # NHAT-KY-01: hỏi GitHub PR mới mỗi 5 phút
    v7_telegram.start(Handler.runner)  # TELEGRAM-01: chỉ chạy khi WEBDEBIT_TELEGRAM=1 và có /etc/webdebit/telegram.env (mặc định tắt)
    if secure is not None:
        threading.Thread(target=secure.serve_forever, daemon=True).start()
    plain.serve_forever()


if __name__ == "__main__":
    main()
