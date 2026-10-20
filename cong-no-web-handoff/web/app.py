"""Internal, read-only viewer for the fixed M1 PostgreSQL pilot snapshot."""

from __future__ import annotations

import html
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from db import Database, DatabaseUnavailable

STYLE = (Path(__file__).with_name("style.css")).read_bytes()
PER_PAGE = 50
EVENTS_PER_PAGE = 100
KIND_LABELS = {
    "opening": "Số dư đầu", "charge": "Phát sinh", "receipt": "Thực nhận phân bổ",
    "offset": "Cấn trừ", "adjustment_plus": "Điều chỉnh +",
    "adjustment_minus": "Điều chỉnh −",
}
STATUS_LABELS = {
    "MATCH": "Khớp số", "NO_BASELINE": "Thiếu mốc kỳ",
    "NO_DB_EVENTS": "Mốc 0 · chưa có sự kiện",
    "MISMATCH": "Lệch số", "INVALID_BASELINE": "Mốc chưa rõ",
    "DUPLICATE_BASELINE": "Mốc trùng",
}
EXCEPTION_LABELS = {
    "COMPONENT_DIFF": "Tổng khác cấu phần",
    "SOURCE_DATE_OR_CLASSIFICATION_WARNING": "Ngày hoặc loại cần kiểm",
    "ZERO_TOTAL": "Tổng 0 chưa duyệt",
    "MISSING_TOTAL": "Thiếu tổng tiền",
}


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def money(value) -> str:
    if value is None:
        return "—"
    amount = int(value)
    sign = "−" if amount < 0 else ""
    return f"{sign}{abs(amount):,}".replace(",", ".") + " ₫"


def link(path: str, **params) -> str:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return path + ("?" + query if query else "")


def anchor(label: str, href: str, css: str = "") -> str:
    cls = f' class="{esc(css)}"' if css else ""
    return f'<a href="{esc(href)}"{cls}>{esc(label)}</a>'


def status_badge(code: str) -> str:
    tone = "good" if code == "MATCH" else ("alert" if code in ("MISMATCH", "INVALID_BASELINE", "DUPLICATE_BASELINE") else "warn")
    return f'<span class="badge {tone}">{esc(STATUS_LABELS.get(code, code))}</span>'


def nav_page(title: str, body: str, as_of: str, capture_id: str, active: str = "") -> str:
    overview = 'aria-current="page"' if active == "overview" else ""
    exceptions = 'aria-current="page"' if active == "exceptions" else ""
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · HTH công nợ</title><link rel="stylesheet" href="/style.css"></head>
<body><a class="skip" href="#main">Đến nội dung</a>
<header class="topbar"><div class="topbar-inner">
  <a class="brand" href="/"><span class="brand-mark">H</span><span>HTH <small>Đối soát công nợ</small></span></a>
  <nav aria-label="Điều hướng chính"><a {overview} href="/">Tổng quan</a><a {exceptions} href="/exceptions">Ngoại lệ</a><a href="http://127.0.0.1:8766/">Sổ hiện hành</a></nav>
  <span class="read-only">● Chỉ đọc</span>
</div></header>
<div class="snapshot"><div class="container"><strong>Replay lịch sử từ Google Sheet</strong>
  <span>Snapshot {esc(as_of)}</span><span class="snapshot-id" title="{esc(capture_id)}">ID {esc(capture_id)}</span>
  <span>Sổ PostgreSQL độc lập là sổ hiện hành</span></div></div>
<main id="main" class="container">{body}</main>
<footer class="container">Số liệu replay theo trạng thái Sheet tại ngày chốt. Chưa xác minh chứng cứ ngân hàng, phê duyệt hoặc GL.</footer>
</body></html>"""


def page_heading(eyebrow: str, title: str, description: str = "") -> str:
    return f'<div class="page-heading"><p class="eyebrow">{esc(eyebrow)}</p><h1>{esc(title)}</h1><p class="muted">{esc(description)}</p></div>'


def metric(label: str, value: str, hint: str = "", href: str | None = None, tone: str = "") -> str:
    content = f'<span class="metric-label">{esc(label)}</span><strong>{esc(value)}</strong><small>{esc(hint)}</small>'
    if href:
        return f'<a class="metric {esc(tone)}" href="{esc(href)}">{content}</a>'
    return f'<div class="metric {esc(tone)}">{content}</div>'


def paginate(path: str, page: int, total: int, size: int, **params) -> str:
    if total <= size:
        return ""
    max_page = (total + size - 1) // size
    previous = anchor("← Trước", link(path, page=page - 1, **params), "button subtle") if page > 1 else ""
    following = anchor("Sau →", link(path, page=page + 1, **params), "button subtle") if page < max_page else ""
    return f'<nav class="pager" aria-label="Phân trang">{previous}<span>Trang {page} / {max_page}</span>{following}</nav>'


def render_overview(db: Database, q: str, as_of: str) -> str:
    provenance = db.provenance()
    if not provenance:
        raise DatabaseUnavailable("capture missing")
    coverage = db.coverage()
    customers = db.customers(q)
    all_customers = customers if not q else db.customers()
    statuses = {row["result"]: int(row["n"]) for row in db.period_status_counts()}
    exception_counts = {row["code"]: int(row["n"]) for row in db.exception_counts()}
    total = sum(int(row["db_balance_vnd"]) for row in all_customers if row["db_balance_vnd"] is not None)
    old_delta_notice = "Chưa có mốc đối soát khớp ngày xem nên chưa cộng chênh sổ cũ"
    if len(provenance) == 1 and provenance[0]["baseline_date"] == as_of:
        confirmed = [row for row in all_customers if row["result"] in ("MATCH", "MISMATCH")
                     and row["old_book_delta_vnd"] is not None]
        old_delta = sum(int(row["old_book_delta_vnd"]) for row in confirmed)
        old_delta_notice = f"<b>{esc(money(old_delta))}</b> chênh sổ cũ đã biết · {len(confirmed)} khách"
    source_rows = sum(int(row["source_rows"]) for row in coverage)
    decided = sum(int(row["decided_rows"]) for row in coverage)
    periods = sum(statuses.values())
    header = page_heading("M1 · ẢNH CHỤP 13/10/2026", "Đối soát công nợ",
                          "Từ tổng khách đến từng kỳ và dòng chứng cứ tại ngày mở sổ. Số dư hiện hành xem ở Sổ công nợ.")
    cards = '<section class="metrics" aria-label="Chỉ số tổng quan">' + "".join((
        metric("Số dư replay", money(total), "151 khách có sự kiện"),
        metric("Dòng nguồn đã phân loại", f"{decided:,}/{source_rows:,}".replace(",", "."), "4 tab đầu vào"),
        metric("Hồ sơ kỳ đối chiếu", str(periods),
               f"{periods - statuses.get('NO_DB_EVENTS', 0)} kỳ có sự kiện + "
               f"{statuses.get('NO_DB_EVENTS', 0)} mốc 0", "/#customers", "warn"),
        metric("Ngoại lệ", f"{sum(exception_counts.values()):,}".replace(",", "."),
               "Chưa tự duyệt", "/exceptions", "warn"),
    )) + "</section>"
    warning = f"""<section class="notice" aria-label="Mục cần kiểm"><strong>Các điểm còn mở</strong>
      <div class="notice-grid"><span><b>{statuses.get('NO_BASELINE', 0)}</b> kỳ chưa có baseline 07</span>
      <span>{old_delta_notice}</span>
      <span>{anchor(str(exception_counts.get('ZERO_TOTAL', 0)) + ' chuyến tổng 0', link('/exceptions', code='ZERO_TOTAL'))}</span>
      <span>{anchor(str(exception_counts.get('MISSING_TOTAL', 0)) + ' chuyến thiếu tổng', link('/exceptions', code='MISSING_TOTAL'))}</span></div>
    </section>"""
    query = f"""<form class="search" action="/" method="get"><label for="q">Tìm khách hàng</label>
      <div><input id="q" name="q" type="search" value="{esc(q)}" maxlength="120" placeholder="Nhập tên khách…">
      <button type="submit">Tìm</button></div></form>"""
    customer_rows = []
    for row in customers:
        href = link("/customer", name=row["customer"])
        customer_rows.append(f"<tr><th scope=\"row\">{anchor(row['customer'], href)}</th>"
                             f"<td class=\"amount\">{esc(money(row['db_balance_vnd']))}</td>"
                             f"<td class=\"amount\">{esc(money(row['sheet_balance_vnd']))}</td>"
                             f"<td>{status_badge(row['result'])}</td></tr>")
    table = f"""<section id="customers" class="panel"><div class="panel-head"><div><h2>Khách hàng</h2>
      <p>{len(customers)} kết quả · chọn khách để xem các kỳ và dòng nguồn</p></div></div>{query}
      <div class="table-wrap"><table><thead><tr><th>Khách hàng</th><th class="amount">Replay</th>
      <th class="amount">Mốc Sheet</th><th>Đối soát</th></tr></thead><tbody>{''.join(customer_rows)}</tbody></table></div></section>"""
    return header + cards + warning + table


def render_customer(db: Database, name: str) -> str | None:
    rows = db.periods(name)
    if not rows:
        return None
    total = sum(int(row["db_balance_vnd"]) for row in rows if row["db_balance_vnd"] is not None)
    heading = page_heading("KHÁCH HÀNG", name, "Các kỳ theo snapshot; khoản thu giữ nguyên kỳ được phân bổ trong nguồn.")
    crumbs = f'<div class="breadcrumbs">{anchor("Tổng quan", "/")}<span>/</span><span>{esc(name)}</span></div>'
    details = f"""<div class="summary-strip"><div><small>Số dư replay</small><strong>{esc(money(total))}</strong></div>
      <div><small>Số kỳ trong đối soát</small><strong>{len(rows)}</strong></div>
      <div>{anchor("Xem ngoại lệ khách này →", link('/exceptions', customer=name), 'button subtle')}</div></div>"""
    body = []
    for row in rows:
        href = link("/period", name=name, period=row["debt_period"])
        body.append(f"<tr><th scope=\"row\">{anchor(row['debt_period'], href)}</th>"
                    f"<td class=\"amount\">{esc(money(row['db_balance_vnd']))}</td>"
                    f"<td class=\"amount\">{esc(money(row['sheet_balance_vnd']))}</td>"
                    f"<td class=\"amount\">{esc(row['event_count'] if row['event_count'] is not None else '—')}</td>"
                    f"<td>{status_badge(row['result'])}</td></tr>")
    table = f"""<section class="panel"><div class="panel-head"><h2>Các kỳ công nợ</h2></div>
      <div class="table-wrap"><table><thead><tr><th>Kỳ</th><th class="amount">Replay</th>
      <th class="amount">Mốc Sheet</th><th class="amount">Sự kiện</th><th>Đối soát</th></tr></thead>
      <tbody>{''.join(body)}</tbody></table></div></section>"""
    return crumbs + heading + details + table


def render_period(db: Database, name: str, debt_period: str, page: int) -> str | None:
    rows = db.period(name, debt_period)
    if not rows:
        return None
    row = rows[0]
    event_count = int(row["event_count"] or 0)
    events = db.events(name, debt_period, EVENTS_PER_PAGE, (page - 1) * EVENTS_PER_PAGE)
    crumbs = (f'<div class="breadcrumbs">{anchor("Tổng quan", "/")}<span>/</span>'
              f'{anchor(name, link("/customer", name=name))}<span>/</span><span>{esc(debt_period)}</span></div>')
    heading = page_heading("CHI TIẾT KỲ", f"{name} · {debt_period}",
                           "Số dư đến ngày chốt lấy từ cùng tập sự kiện replay của PostgreSQL.")
    figures = '<section class="metrics compact" aria-label="Cấu phần số dư">' + "".join((
        metric("Số dư đầu", money(row["opening_vnd"])),
        metric("Phát sinh", money(row["charge_vnd"])),
        metric("Thực nhận phân bổ", money(row["receipt_vnd"])),
        metric("Cấn trừ", money(row["offset_vnd"])),
        metric("Điều chỉnh +", money(row["adjustment_plus_vnd"])),
        metric("Điều chỉnh −", money(row["adjustment_minus_vnd"])),
    )) + "</section>"
    comparison = f"""<section class="panel comparison"><div><small>Số dư replay</small>
      <strong>{esc(money(row['db_balance_vnd']))}</strong></div>
      <div><small>Mốc Sheet 07</small><strong>{esc(money(row['sheet_balance_vnd']))}</strong></div>
      <div>{status_badge(row['result'])}</div></section>"""
    event_rows = []
    for event in events:
        source = link("/source", gid=event["sheet_gid"], row=event["source_row"])
        label = f"{event['tab_title']} · hàng {event['source_row']}"
        event_rows.append(f"<tr><td>{esc(event['posting_date'])}</td>"
                          f"<td>{esc(KIND_LABELS.get(event['kind'], event['kind']))}</td>"
                          f"<td class=\"amount\">{esc(money(event['signed_amount_vnd']))}</td>"
                          f"<td>{anchor(label, source)}</td></tr>")
    empty = '<tr><td colspan="4" class="empty">Không có sự kiện replay cho kỳ này.</td></tr>'
    table = f"""<section class="panel"><div class="panel-head"><div><h2>Dòng nguồn tạo số dư</h2>
      <p>{event_count} sự kiện · bấm hàng nguồn để xem giá trị gốc và hash</p></div></div>
      <div class="table-wrap"><table><thead><tr><th>Ngày ghi sổ</th><th>Loại</th>
      <th class="amount">Giá trị có dấu</th><th>Nguồn</th></tr></thead>
      <tbody>{''.join(event_rows) or empty}</tbody></table></div>
      {paginate('/period', page, event_count, EVENTS_PER_PAGE, name=name, period=debt_period)}</section>"""
    return crumbs + heading + comparison + figures + table


def render_exceptions(db: Database, code: str, customer: str, page: int) -> str:
    counts = db.exception_counts()
    total = int(db.exception_total(code, customer))
    rows = db.exceptions(code, customer, PER_PAGE, (page - 1) * PER_PAGE)
    heading = page_heading("HÀNG CHỜ KIỂM", "Ngoại lệ cần xem",
                           "Cảnh báo từ bản replay. Trạng thái ở đây không phải quyết định duyệt hoặc điều chỉnh số.")
    filters = ['<div class="chips">', anchor("Tất cả", "/exceptions", "chip" + (" selected" if not code else ""))]
    for item in counts:
        label = EXCEPTION_LABELS.get(item["code"], item["code"])
        filters.append(anchor(f"{label} · {item['n']}", link('/exceptions', code=item['code']),
                              "chip" + (" selected" if code == item["code"] else "")))
    filters.append("</div>")
    search = f"""<form class="search inline" action="/exceptions" method="get"><label for="customer">Lọc đúng tên khách</label>
      <div><input id="customer" name="customer" type="search" value="{esc(customer)}" maxlength="250" placeholder="Tên khách như trong nguồn">
      <input type="hidden" name="code" value="{esc(code)}"><button type="submit">Lọc</button></div></form>"""
    body = []
    for item in rows:
        source = link("/source", gid=item["sheet_gid"], row=item["source_row"])
        customer_link = anchor(item["customer"], link("/customer", name=item["customer"])) if item["customer"] else "—"
        body.append(f"<tr><td><strong>{esc(EXCEPTION_LABELS.get(item['code'], item['code']))}</strong>"
                    f"<small>{esc(item['detail'])}</small></td><td>{customer_link}</td>"
                    f"<td>{esc(item['debt_period'] or '—')}</td>"
                    f"<td>{anchor(item['tab_title'] + ' · hàng ' + str(item['source_row']), source)}</td></tr>")
    empty = '<tr><td colspan="4" class="empty">Không có ngoại lệ theo bộ lọc này.</td></tr>'
    table = f"""<section class="panel"><div class="panel-head"><div><h2>Danh sách</h2>
      <p>{total} ngoại lệ · trang {page}</p></div></div>{''.join(filters)}{search}
      <div class="table-wrap"><table><thead><tr><th>Cần kiểm</th><th>Khách</th><th>Kỳ</th><th>Dòng nguồn</th></tr></thead>
      <tbody>{''.join(body) or empty}</tbody></table></div>
      {paginate('/exceptions', page, total, PER_PAGE, code=code, customer=customer)}</section>"""
    return heading + table


def column_label(index: int) -> str:
    label = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


def render_source(db: Database, gid: int, row_number: int) -> str | None:
    rows = db.source_row(gid, row_number)
    if not rows:
        return None
    row = rows[0]
    values = row["source_values"] or []
    body = []
    for index, value in enumerate(values, 1):
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
        body.append(f"<tr><th scope=\"row\">{column_label(index)}</th><td>{esc(text) if text not in (None, '') else '<span class=\"muted\">Trống</span>'}</td></tr>")
    heading = page_heading("DÒNG NGUỒN", f"{row['tab_title']} · hàng {row_number}",
                           "Giá trị cached từ bản xuất đã kiểm hash; mở Sheet gốc để xem công thức, ảnh và chú thích còn lại.")
    detail = f"""<section class="panel source-meta"><div><small>GID / hàng</small>
      <strong>{gid} / {row_number}</strong></div><div><small>SHA-256 dòng raw</small>
      <code>{esc(row['row_sha256'])}</code></div><div>{anchor('Mở dòng trong Google Sheet ↗', row['source_url'], 'button')}</div></section>"""
    table = f"""<section class="panel"><div class="panel-head"><h2>Giá trị nguồn</h2></div>
      <div class="table-wrap"><table class="source-table"><thead><tr><th>Cột</th><th>Giá trị cached</th></tr></thead>
      <tbody>{''.join(body)}</tbody></table></div></section>"""
    return heading + detail + table


def query_arg(query: dict, key: str, limit: int = 250) -> str:
    value = query.get(key, [""])[0]
    if len(value) > limit:
        raise ValueError("query value too long")
    return value


def page_arg(query: dict) -> int:
    raw = query_arg(query, "page", 6) or "1"
    if not raw.isascii() or not raw.isdigit():
        raise ValueError("invalid page")
    page = int(raw)
    if page < 1 or page > 10000:
        raise ValueError("invalid page")
    return page


class ViewerHandler(BaseHTTPRequestHandler):
    db: Database
    capture_id: str
    as_of: str
    port: int

    def _send(self, status: int, data: bytes, content_type: str = "text/html; charset=utf-8", body: bool = True):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        if body:
            self.wfile.write(data)

    def _html(self, status: int, title: str, body: str, active: str = "", send_body: bool = True):
        page = nav_page(title, body, self.as_of, self.capture_id, active)
        self._send(status, page.encode("utf-8"), body=send_body)

    def _handle(self, send_body: bool):
        host = self.headers.get("Host", "").lower()
        if host not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            self._send(400, b"Invalid Host", "text/plain; charset=utf-8", send_body)
            return
        if len(self.path) > 4096:
            self._send(414, b"URL too long", "text/plain; charset=utf-8", send_body)
            return
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        try:
            if parsed.path == "/style.css":
                self._send(200, STYLE, "text/css; charset=utf-8", send_body)
                return
            if parsed.path == "/favicon.ico":
                self._send(204, b"", body=send_body)
                return
            if parsed.path == "/health":
                provenance = self.db.provenance()
                ok = bool(provenance and provenance[0]["baseline_date"] == self.as_of)
                data = json.dumps({"ok": ok, "capture_id": self.capture_id,
                                   "as_of": self.as_of}, ensure_ascii=False).encode("utf-8")
                self._send(200 if ok else 503, data, "application/json; charset=utf-8", send_body)
                return
            if parsed.path == "/":
                q = query_arg(query, "q", 120)
                self._html(200, "Tổng quan", render_overview(self.db, q, self.as_of), "overview", send_body)
                return
            if parsed.path == "/customer":
                name = query_arg(query, "name")
                content = render_customer(self.db, name) if name else None
                if content:
                    self._html(200, name, content, send_body=send_body)
                else:
                    self._html(404, "Không tìm thấy khách", page_heading("404", "Không tìm thấy khách"), send_body=send_body)
                return
            if parsed.path == "/period":
                name = query_arg(query, "name")
                period = query_arg(query, "period", 7)
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
                    raise ValueError("invalid period")
                page = page_arg(query)
                content = render_period(self.db, name, period, page) if name else None
                if content:
                    self._html(200, period, content, send_body=send_body)
                else:
                    self._html(404, "Không tìm thấy kỳ", page_heading("404", "Không tìm thấy kỳ"), send_body=send_body)
                return
            if parsed.path == "/exceptions":
                code = query_arg(query, "code", 80)
                customer = query_arg(query, "customer")
                page = page_arg(query)
                self._html(200, "Ngoại lệ", render_exceptions(self.db, code, customer, page),
                           "exceptions", send_body)
                return
            if parsed.path == "/source":
                gid_text = query_arg(query, "gid", 20)
                row_text = query_arg(query, "row", 10)
                if not gid_text.isascii() or not gid_text.isdigit() or not row_text.isascii() or not row_text.isdigit():
                    raise ValueError("invalid source")
                gid, row_number = int(gid_text), int(row_text)
                if gid <= 0 or row_number <= 0:
                    raise ValueError("invalid source")
                content = render_source(self.db, gid, row_number)
                if content:
                    self._html(200, "Dòng nguồn", content, send_body=send_body)
                else:
                    self._html(404, "Không tìm thấy dòng", page_heading("404", "Không tìm thấy dòng nguồn"), send_body=send_body)
                return
            self._html(404, "Không tìm thấy trang", page_heading("404", "Không tìm thấy trang"), send_body=send_body)
        except ValueError:
            self._html(400, "Yêu cầu không hợp lệ", page_heading("400", "Tham số không hợp lệ"), send_body=send_body)
        except DatabaseUnavailable:
            self._html(503, "Tạm chưa đọc được dữ liệu", page_heading("503", "Tạm chưa đọc được PostgreSQL",
                       "Hãy kiểm tra dịch vụ và capture đã chọn."), send_body=send_body)

    def do_GET(self):
        self._handle(True)

    def do_HEAD(self):
        self._handle(False)

    def do_POST(self):
        self._send(405, b"Read only", "text/plain; charset=utf-8")

    def log_message(self, format, *args):
        # Avoid logging customer names, raw source rows and query strings.
        return


def main() -> None:
    capture_id = os.environ["WEBDEBIT_CAPTURE_ID"]
    as_of = os.environ["WEBDEBIT_AS_OF"]
    port = int(os.environ.get("WEBDEBIT_PORT", "8765"))
    if not 1024 <= port <= 65535:
        raise ValueError("invalid port")
    db = Database(os.environ.get("WEBDEBIT_DB", "webdebit_pilot_system"), capture_id, as_of)
    provenance = db.provenance()
    coverage = db.coverage()
    if (len(provenance) != 1 or provenance[0]["baseline_date"] != as_of
            or len(coverage) != 4 or any(int(row["missing_rows"]) for row in coverage)):
        raise RuntimeError("capture, baseline date or row coverage is not verified")
    ViewerHandler.db = db
    ViewerHandler.capture_id = capture_id
    ViewerHandler.as_of = as_of
    ViewerHandler.port = port
    server = ThreadingHTTPServer(("127.0.0.1", port), ViewerHandler)
    server.daemon_threads = True
    print(f"webdebit viewer listening on 127.0.0.1:{port} for {capture_id} as-of {as_of}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
