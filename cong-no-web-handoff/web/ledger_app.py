"""Read-only UI for the independent PostgreSQL receivables ledger."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from ledger_db import HistoryDB, LedgerDB, LedgerUnavailable


STYLE = Path(__file__).with_name("style.css").read_bytes()
CAPTURE = "2026-10-19-so-goc"
OPENING_DATE = date(2026, 10, 19)
# Opening re-built from the original old-book customer tabs on 19/10/2026 (owner chose the original
# book as the standard; the 13/10 replay opening is kept only as a backup dump). Startup and /health
# both reject any other value. Every period is NO_BASELINE: the original book has no independent
# per-period baseline, only per-customer totals, which the opening matches.
OPENING_INVARIANTS = {"opening_periods": 132, "opening_vnd": 65_099_410_165, "no_baseline": 132}
# The M1 replay history (trip/receipt detail, source exceptions) belongs to the 13/10 opening and has
# no provenance for the 19/10 opening, so it is not attached. Balances still come from PostgreSQL.
HISTORY_ENABLED = False
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
KIND = {"opening": "Số mở kỳ lịch sử", "charge": "Phát sinh", "receipt": "Thực nhận", "offset": "Cấn trừ",
        "adjustment_plus": "Điều chỉnh +", "adjustment_minus": "Điều chỉnh −", "reversal": "Đảo bút toán"}


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def today() -> date:
    return datetime.now(VN_TZ).date()


def money(value: object) -> str:
    if value is None:
        return "—"
    amount = int(value)
    return ("−" if amount < 0 else "") + f"{abs(amount):,}".replace(",", ".") + " ₫"


def href(path: str, **values: object) -> str:
    values = {key: value for key, value in values.items() if value not in (None, "")}
    return path + ("?" + urlencode(values) if values else "")


def anchor(label: object, path: str, css: str = "") -> str:
    class_attr = f' class="{esc(css)}"' if css else ""
    return f'<a href="{esc(path)}"{class_attr}>{esc(label)}</a>'


def exception_href(filters: dict, page_number: int = 1) -> str:
    values = {f"{key}_mode": filters[f"{key}_mode"]
              for key in ("customer", "period", "code")}
    for key in ("customer", "period", "code"):
        if filters[f"{key}_mode"] == "exact":
            values[key] = filters[key]
    values["page"] = page_number
    return "/exceptions?" + urlencode(values)


def web_source_url(value: object) -> str | None:
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None):
            return None
    except ValueError:
        return None
    return value


def count_text(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError, OverflowError):
        return "—"


def amount_integer(value: object) -> int | None:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return None


def reconciliation_text(item: dict | None) -> str:
    if not item:
        return "Chênh sổ cũ theo khách: chưa có dòng đối chiếu."
    status = item.get("reconciliation_status")
    delta_status = item.get("old_book_delta_status")
    delta = item.get("old_book_delta_vnd")
    if status == "NO_BASELINE" or delta_status == "NO_BASELINE":
        return "Sổ cũ: NO_BASELINE; chênh lệch chưa biết."
    if status in {"DUPLICATE_BASELINE", "INVALID_BASELINE"}:
        base = "mốc cũ trùng" if status == "DUPLICATE_BASELINE" else "mốc cũ không hợp lệ"
        value = f" Giá trị chênh lệch {money(delta)} có sẵn nhưng chưa được xác nhận." if delta_status == "AVAILABLE" and delta is not None else ""
        return f"Sổ cũ: {base}; chưa xác nhận.{value}"
    if delta_status == "MISSING" or delta is None:
        return f"Sổ cũ: thiếu chênh lệch ({status or 'UNKNOWN'}); chưa thể kết luận."
    if delta_status == "AVAILABLE":
        prefix = "Không có sự kiện DB; " if status == "NO_DB_EVENTS" else ""
        return f"{prefix}Chênh sổ cũ cấp khách: {money(delta)} · {status or 'UNKNOWN'}."
    return f"Sổ cũ: chưa thể xác nhận ({status or 'UNKNOWN'})."


def reconciliation_overview(items: list[dict], baseline_available: bool = True) -> str:
    known = [(item, amount_integer(item.get("old_book_delta_vnd"))) for item in items
             if item.get("old_book_delta_status") == "AVAILABLE"
             and item.get("reconciliation_status") in {"MATCH", "MISMATCH"}]
    known = [(item, value) for item, value in known if value is not None]
    missing = sum(item.get("old_book_delta_status") == "MISSING" for item in items)
    no_baseline = sum(item.get("old_book_delta_status") == "NO_BASELINE"
                      or item.get("reconciliation_status") == "NO_BASELINE" for item in items)
    invalid = sum(item.get("reconciliation_status") in {"DUPLICATE_BASELINE", "INVALID_BASELINE"}
                  for item in items)
    no_events = sum(item.get("reconciliation_status") == "NO_DB_EVENTS" for item in items)
    pending = missing + no_baseline + invalid + no_events
    if not baseline_available:
        prefix = "Chưa có mốc đối soát khớp ngày xem, nên chưa cộng chênh lệch sổ cũ."
    elif known:
        prefix = f"Tổng chênh sổ cũ đã biết: {money(sum(value for _, value in known))} từ {len(known)} khách."
    else:
        prefix = "Chưa có chênh lệch số đã biết để cộng."
    suffix = (f" Tổng phần đã biết; còn {missing} khách thiếu chênh lệch, {no_baseline} NO_BASELINE, "
              f"{invalid} mốc trùng/không hợp lệ và {no_events} khách chưa có sự kiện DB."
              if pending else "" if not baseline_available else " Toàn bộ dòng có giá trị số đã được kiểm trạng thái.")
    return prefix + suffix + " Chênh lệch chỉ thuộc khách, không phân bổ xuống kỳ."


def total_anomaly_text(summary: dict) -> str:
    codes = {group.get("code"): group for group in summary.get("by_code", [])}
    missing = codes.get("MISSING_TOTAL", {}).get("exception_count", 0)
    zero = codes.get("ZERO_TOTAL", {}).get("exception_count", 0)
    return (f"Tổng nguồn thiếu: {count_text(missing)} ngoại lệ · "
            f"Tổng nguồn bằng 0: {count_text(zero)} ngoại lệ.")


def source_warning(summary: dict | None, reconciliations: list[dict] | None,
                   target: str = "/exceptions", detail: str | None = None,
                   baseline_available: bool = True) -> str:
    if not HISTORY_ENABLED:  # no replay source exceptions exist for this opening
        return ""
    if summary is None or reconciliations is None:
        return (f'<div class="source-warning unavailable" role="status">'
                f'<strong>Chưa kiểm được ngoại lệ nguồn.</strong> '
                f'Số dư hiển thị vẫn lấy từ sổ PostgreSQL. {anchor("Mở ngoại lệ", target)}</div>')
    counts = (f'{count_text(summary.get("exception_count"))} ngoại lệ · '
              f'{count_text(summary.get("source_row_count"))} dòng nguồn · '
              f'{count_text(summary.get("trip_source_row_count"))} chuyến có ngoại lệ.')
    detail_text = detail or (total_anomaly_text(summary) + " " + reconciliation_overview(reconciliations, baseline_available))
    return (f'<div class="source-warning" role="status"><span><strong>Ngoại lệ nguồn:</strong> '
            f'{esc(counts)} {anchor("Xem ngoại lệ", target)}</span>'
            f'<small>{esc(detail_text)}</small></div>')


def customer_source_warning(summary: dict | None, reconciliation: dict | None,
                            target: str = "/exceptions") -> str:
    if not HISTORY_ENABLED:
        return ""
    if summary is None:
        return source_warning(None, None, target)
    detail = reconciliation_text(reconciliation)
    if reconciliation is None:
        detail = "Đối chiếu sổ cũ theo khách: chưa có dòng đối chiếu."
    counts = (f'{count_text(summary.get("exception_count"))} ngoại lệ · '
              f'{count_text(summary.get("source_row_count"))} dòng nguồn · '
              f'{count_text(summary.get("trip_source_row_count"))} chuyến có ngoại lệ.')
    detail = total_anomaly_text(summary) + " " + reconciliation_text(reconciliation)
    return (f'<div class="source-warning" role="status"><span><strong>Ngoại lệ khách (mọi kỳ):</strong> '
            f'{esc(counts)} {anchor("Xem ngoại lệ", target)}</span>'
            f'<small>{esc(detail)}</small></div>')


def period_source_warning(group: dict | None, target: str) -> str:
    if not HISTORY_ENABLED:
        return ""
    if group is None:
        return source_warning(None, None, target)
    counts = (f'{count_text(group.get("exception_count"))} ngoại lệ · '
              f'{count_text(group.get("source_row_count"))} dòng nguồn · '
              f'{count_text(group.get("trip_source_row_count"))} chuyến có ngoại lệ.')
    return (f'<div class="period-source-warning" role="status"><strong>Ngoại lệ kỳ:</strong> '
            f'{esc(counts)} {anchor("Xem ngoại lệ", target)} '
            '<small>Chênh sổ cũ chỉ thuộc khách, không phân bổ xuống kỳ.</small></div>')


def filtered_exception_summary(summary: dict, key: str, value: str) -> dict:
    field = {"customer": "customer", "period": "period", "code": "code"}[key]
    for group in summary.get(f"by_{key}", []):
        if group.get("group_status") == "UNCLASSIFIED" and not value.strip(" \t\n\r\f\v"):
            return group
        if group.get(field) == value:
            return group
    return {"exception_count": 0, "source_row_count": 0, "trip_source_row_count": 0}


def page(title: str, body: str, selected_date: date, wide: bool = False) -> bytes:
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Sổ công nợ HTH</title><link rel="stylesheet" href="/style.css"></head>
<body><a class="skip" href="#main">Đến nội dung</a>
<header class="topbar"><div class="topbar-inner"><a class="brand" href="/">
<span class="brand-mark">H</span><span>HTH <small>Sổ công nợ</small></span></a>
<nav aria-label="Điều hướng chính"><a href="/">Công nợ</a><a href="/pending">Khoản chờ</a>
<a href="/postings">Đã ghi sổ</a>{'<a href="/exceptions">Ngoại lệ nguồn</a>' if HISTORY_ENABLED else ''}</nav>
<span class="read-only">Xem đến {selected_date.strftime('%d/%m/%Y')}</span></div></header>
<main id="main" class="container{' wide' if wide else ''}">{body}</main>
<footer class="container"><details class="site-notes"><summary>Nguồn dữ liệu và giới hạn</summary>
<p>Sổ PostgreSQL độc lập. Số mở sổ từ snapshot {CAPTURE}. Kỳ thiếu mốc đối soát vẫn được gắn cờ.
Web chỉ đọc; nguồn replay và dữ liệu ngân hàng chưa được xác minh thay cho chứng từ gốc.</p></details></footer>
</body></html>""".encode("utf-8")


def heading(kicker: str, title: str, detail: str) -> str:
    label = f'<p class="eyebrow">{esc(kicker)}</p>' if kicker else ''
    description = f'<p class="muted">{esc(detail)}</p>' if detail else ''
    return f'<div class="page-heading">{label}<h1>{esc(title)}</h1>{description}</div>'


def metric(label: str, value: str, detail: str = "", target: str = "") -> str:
    content = f'<span class="metric-label">{esc(label)}</span><strong>{esc(value)}</strong><small>{esc(detail)}</small>'
    return f'<a class="metric" href="{esc(target)}">{content}</a>' if target else f'<div class="metric">{content}</div>'


def status_badge(code: str | None) -> str:
    if code == "NO_BASELINE":
        return '<span class="badge warn">Thiếu mốc đối soát</span>'
    if code == "MATCH":
        return '<span class="badge good">Khớp replay</span>'
    return '<span class="badge warn">Kỳ mới sau mở sổ</span>'


def render_overview(db: LedgerDB, as_of: date, search: str, period: str = "2026-10",
                    history: HistoryDB | None = None) -> str:
    t, customers = db.overview_screen(as_of, period, search)
    summary = period_summary = reconciliations = None
    if history:
        try:
            summary = history.exception_summary()
        except LedgerUnavailable:
            pass
        try:
            period_summary = history.exception_summary(period=period)
        except LedgerUnavailable:
            pass
        try:
            reconciliations = history.customer_reconciliations()
        except LedgerUnavailable:
            pass
    reconciliation_items = reconciliations.get("items", []) if reconciliations else None
    content = heading("", "Công nợ", "")
    content += (f'<form class="filterbar" action="/" method="get">'
                f'<label for="q">Tìm khách<input id="q" name="q" type="search" '
                f'maxlength="120" value="{esc(search)}" placeholder="Tên khách hàng"></label>'
                f'<label for="period">Kỳ nợ<input id="period" name="period" type="month" '
                f'value="{esc(period)}" required></label>'
                f'<label for="as_of">Đến ngày<input id="as_of" name="as_of" type="date" '
                f'min="{OPENING_DATE.isoformat()}" max="{today().isoformat()}" '
                f'value="{as_of.isoformat()}" required></label>'
                f'<button type="submit">Xem</button></form>')
    content += (f'<section class="overview-summary" aria-label="Tổng công nợ">'
                f'<div><span>Tổng còn nợ mọi kỳ</span><strong>{money(t["balance_vnd"])}</strong></div>'
                f'<small>{int(t["customers"])} khách · đến {as_of.strftime("%d/%m/%Y")}</small></section>')
    content += source_warning(summary, reconciliation_items, baseline_available=bool(reconciliations)
                              and reconciliations.get("reconciliation_status") == "AVAILABLE")
    period_target = exception_href({"customer_mode": "all", "customer": None,
                                    "period_mode": "exact", "period": period,
                                    "code_mode": "all", "code": None})
    if period_summary is None:
        if summary is not None:  # history fully unreadable: one box is enough
            content += source_warning(None, None, period_target)
    else:
        period_detail = (total_anomaly_text(period_summary) +
                         " Chênh sổ cũ chỉ thuộc khách, không phân bổ xuống kỳ.")
        content += source_warning(period_summary, [], period_target, period_detail)
    alerts = []
    if t["no_baseline"]:
        alerts.append(f'{int(t["no_baseline"])} kỳ thiếu mốc đối soát')
    if t["pending"]:
        alerts.append(anchor(f'{int(t["pending"])} khoản chờ duyệt', "/pending"))
    if alerts:
        content += '<p class="attention-line">Cần kiểm tra: ' + ' · '.join(alerts) + '</p>'
    rows = []
    exception_groups = {group.get("customer"): group
                        for group in (period_summary or {}).get("by_customer", [])}
    reconciliation_by_customer = {item.get("customer"): item
                                  for item in (reconciliation_items or [])}
    for item in customers:
        customer_url = href("/customer", name=item["customer"], as_of=as_of.isoformat())
        balance = int(item["period_balance_vnd"])
        status = ('Thiếu mốc' if item["comparison_status"] == 'NO_BASELINE' else
                  'Còn nợ' if balance > 0 else 'Dư có' if balance < 0 else
                  'Đã tất toán' if item["comparison_status"] else 'Chưa có kỳ')
        tone = 'warn' if item["comparison_status"] == 'NO_BASELINE' else ('good' if balance == 0 else 'neutral')
        customer_group = exception_groups.get(item["customer"])
        customer_reconciliation = reconciliation_by_customer.get(item["customer"])
        row_target = exception_href({"customer_mode": "exact", "customer": item["customer"],
                                     "period_mode": "exact", "period": period,
                                     "code_mode": "all", "code": None})
        customer_source = (period_source_warning(customer_group or {
                            "exception_count": 0, "source_row_count": 0,
                            "trip_source_row_count": 0}, row_target)
                           if period_summary is not None else
                           source_warning(None, None, row_target))
        customer_delta = (f'<small>{esc(reconciliation_text(customer_reconciliation))}</small>'
                          if reconciliation_items is not None else
                          '<small>Chênh sổ cũ cấp khách: chưa kiểm được ngoại lệ nguồn.</small>')
        rows.append(f'<tr><th scope="row">{esc(item["customer"])}</th>'
                    f'<td class="amount" data-label="Còn nợ kỳ">{money(item["period_balance_vnd"])}</td>'
                    f'<td class="amount" data-label="Tổng còn nợ">{money(item["total_balance_vnd"])}</td>'
                    f'<td data-label="Tình trạng"><span class="badge {tone}">{esc(status)}</span>'
                    f'<div class="row-source-warning">{customer_source}{customer_delta}</div></td>'
                    f'<td>{anchor("Xem sổ →", customer_url, "text-link")}</td></tr>')
    content += (f'<section class="panel"><div class="panel-head"><h2>Khách hàng · {esc(period)}</h2>'
                f'<span class="result-count">{len(customers)} khách</span></div>'
                f'<table class="overview-table"><thead><tr><th>Khách hàng</th>'
                f'<th class="amount">Còn nợ kỳ</th><th class="amount">Tổng còn nợ</th>'
                f'<th>Tình trạng</th><th>Sổ khách</th></tr></thead>'
                f'<tbody>{"".join(rows) or "<tr><td colspan=\"5\" class=\"empty\">Không tìm thấy khách.</td></tr>"}</tbody>'
                f'</table></section>')
    return content


def sheet_date(value: object) -> str:
    if not value:
        return "—"
    raw = str(value)
    try:
        return date.fromisoformat(raw[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return raw


def source_vnd(value: object) -> str:
    if value in (None, ""):
        return "—"
    try:
        amount = Decimal(str(value))
        if amount.is_finite() and amount == amount.to_integral_value():
            return money(int(amount))
    except (InvalidOperation, ValueError, TypeError):
        pass
    return "CẦN KT"


def source_link(event: dict) -> str:
    target = "http://127.0.0.1:8765" + href("/source", gid=event["sheet_gid"], row=event["source_row"])
    return anchor("Dòng nguồn ↗", target, "source-link")


def month_rows(events: list[dict], postings: list[dict], carried: int) -> tuple[str, int, int, int]:
    """Render independent debt and payment lists with no implied allocation."""
    charges, payments = [], []
    for event in events:
        signed = int(event["signed_amount_vnd"])
        values = event.get("source_values") or []
        value = lambda index: values[index] if index < len(values) else None
        kind = event["kind"]
        if signed >= 0:
            if kind == "charge":
                fees = [value(index) for index in (7, 8, 9)]
                fee_values = [x for x in fees if x not in (None, "")]
                try:
                    fee_total = sum(Decimal(str(x)) for x in fee_values) if fee_values else None
                except (InvalidOperation, TypeError):
                    fee_total = "CẦN KT"
                price = source_vnd(value(10))
                fee = source_vnd(fee_total)
                route = (f' · {esc(value(5))} → {esc(value(6))}'
                         if value(5) or value(6) else '')
                review = ' <span class="badge warn">CẦN KT</span>' if "CẦN KT" in (price, fee) else ''
                detail = (f'<strong>{esc(value(3))}</strong>{route}{review}'
                          f'<details class="row-details"><summary>Chi tiết & nguồn</summary>'
                          f'<div>Hãng/xe: {esc(value(4)) or "—"} · Đơn giá: {price} · '
                          f'Phụ phí: {fee} · {source_link(event)}</div></details>')
            else:
                detail = (f'<strong>{esc(KIND.get(kind, kind))}</strong>'
                          f'<details class="row-details"><summary>Nguồn</summary>'
                          f'{source_link(event)}</details>')
            charges.append((sheet_date(value(2)), detail, signed))
        else:
            detail = (f'<strong>{esc(KIND.get(kind, kind))}</strong>'
                      f'<details class="row-details"><summary>Nguồn</summary>'
                      f'{source_link(event)}</details>')
            payments.append((sheet_date(value(2)), detail, -signed))
    for posting in postings:
        signed = int(posting["signed_amount_vnd"])
        link = anchor("Phiếu #" + str(posting["proposal_id"]),
                      href("/proposal", id=posting["proposal_id"]), "source-link")
        label = (f'<strong>{esc(KIND.get(posting["kind"], posting["kind"]))}</strong> '
                 f'<span class="badge neutral">Mới</span>'
                 f'<details class="row-details"><summary>Phiếu</summary>{link}</details>')
        if signed >= 0:
            charges.append((sheet_date(posting["event_date"]), label, signed))
        else:
            payments.append((sheet_date(posting["event_date"]), label, -signed))
    charge_total = sum(item[2] for item in charges)
    payment_total = sum(item[2] for item in payments)

    def section(title: str, rows: list[tuple[str, str, int]]) -> str:
        body = ''.join(
            f'<tr class="history-row"><td>{esc(day)}</td><td>{detail}</td>'
            f'<td class="amount">{money(amount)}</td></tr>'
            for day, detail, amount in rows)
        if not body:
            body = '<tr><td colspan="3" class="empty">Không có khoản trong kỳ.</td></tr>'
        return (f'<section class="ledger-list"><h3>{title} <small>{len(rows)} khoản</small></h3>'
                '<table><thead><tr><th>Ngày</th><th>Nội dung</th>'
                '<th class="amount">Số tiền</th></tr></thead><tbody>'
                f'{body}</tbody></table></section>')

    content = ('<div class="ledger-sections">'
               + section("Phát sinh nợ", charges)
               + section("Đã thu / giảm trừ", payments)
               + '</div>')
    return content, charge_total, payment_total, carried + charge_total - payment_total


def render_customer(db: LedgerDB, as_of: date, name: str, first_period: str = "",
                    history: HistoryDB | None = None) -> str | None:
    screen = db.customer_screen(as_of, name)
    row = next((item for item in screen["customers"] if item["customer"] == name), None)
    if row is None:
        return None
    all_periods = screen["periods"]
    ascending_periods = list(reversed(all_periods))
    carried_by_period = {}
    carried = 0
    for item in ascending_periods:
        carried_by_period[item["debt_period"]] = carried
        carried += int(item["balance_vnd"])
    periods = [item for item in reversed(ascending_periods)
               if not first_period or item["debt_period"] >= first_period]
    pending = screen["pending"]
    history_error = history is None
    customer_summary = customer_reconciliation = None
    if history:
        try:
            customer_summary = history.exception_summary(customer=name)
        except LedgerUnavailable:
            history_error = True
        try:
            result = history.customer_reconciliations(customer=name)
            customer_reconciliation = next(
                (entry for entry in result.get("items", []) if entry.get("customer") == name), None)
        except LedgerUnavailable:
            history_error = True
    try:
        replay_events = (history.events_for_customer(CAPTURE, name, first_period)
                         if history and customer_summary is not None
                         and customer_reconciliation is not None and not history_error else [])
    except LedgerUnavailable:
        replay_events, history_error = [], True
    if history and customer_summary is None:
        history_error = True
    history_truncated = len(replay_events) > 2000
    replay_events = replay_events[:2000]
    history_by_period = {}
    for event in replay_events:
        history_by_period.setdefault(event["debt_period"], []).append(event)
    new_postings = screen["postings"]
    postings_truncated = len(new_postings) > 1000
    postings_by_period = {}
    for item in new_postings[:1000]:
        postings_by_period.setdefault(item["debt_period"], []).append(item)
    content = (f'<div class="customer-title">'
               f'{anchor("← Công nợ", href("/", as_of=as_of.isoformat(), period=first_period or as_of.strftime("%Y-%m")))}'
               f'<h1>{esc(name)}</h1></div>')
    content += (f'<section class="customer-balance" aria-label="Tổng còn nợ">'
                f'<span>Tổng còn nợ</span><strong>{money(row["balance_vnd"])}</strong>'
                f'<details class="balance-details"><summary>Cách tính</summary>'
                f'<div>Số mở sổ {money(row["opening_vnd"])} · '
                f'Bút toán sau mở sổ {money(row["movement_vnd"])}</div></details></section>')
    customer_target = exception_href({"customer_mode": "exact", "customer": name,
                                      "period_mode": "all", "period": None,
                                      "code_mode": "all", "code": None})
    content += customer_source_warning(None if history_error else customer_summary,
                                       customer_reconciliation, customer_target)
    if pending["proposals"]:
        content += (f'<p class="attention-line"><b>{int(pending["proposals"])} khoản chờ duyệt</b> '
                    f'· Chưa vào số dư · {anchor("Xem khoản chờ", "/pending")}</p>')
    customer_options = []
    for customer in db.customers(as_of):
        customer_name = customer["customer"]
        selected = ' selected' if customer_name == name else ''
        customer_options.append(f'<option value="{esc(customer_name)}"{selected}>{esc(customer_name)}</option>')
    filter_summary = (f'Từ tháng {esc(first_period[5:7])}/{esc(first_period[:4])} · Đổi khách / lọc tháng'
                      if first_period else 'Đổi khách hoặc lọc tháng')
    content += (f'<details class="customer-tools"><summary>{filter_summary}</summary>'
                f'<form class="filterbar customer-filter" action="/customer" method="get">'
                f'<input type="hidden" name="as_of" value="{as_of.isoformat()}">'
                f'<label for="customer_name">Khách hàng<select id="customer_name" name="name" required>'
                f'{"".join(customer_options)}</select></label>'
                f'<label for="first_period">Từ tháng<input id="first_period" name="first_period" '
                f'type="month" value="{esc(first_period)}"></label>'
                f'<button type="submit">Xem</button>'
                f'{anchor("Bỏ lọc tháng", href("/customer", name=name, as_of=as_of.isoformat()), "text-link") if first_period else ""}'
                f'</form></details>')
    if history_error and not HISTORY_ENABLED:
        content += ('<p class="attention-line"><b>Sổ mở lại từ sổ gốc ngày 19/10/2026.</b> '
                    'Số dư theo kỳ đọc từ sổ PostgreSQL; chi tiết từng chuyến/khoản thu chưa nạp vào web.</p>')
    elif history_error:
        content += ('<p class="attention-line"><b>Chưa kiểm được ngoại lệ nguồn.</b> '
                    'Số dư vẫn đọc được từ sổ PostgreSQL; chi tiết lịch sử chưa được xác nhận.</p>')
    if history_truncated:
        content += '<p class="attention-line"><b>Chi tiết lịch sử chưa đủ.</b> Danh sách vượt 2.000 sự kiện; mở đối soát kỳ để xem tiếp.</p>'
    if postings_truncated:
        content += '<p class="attention-line"><b>Bút toán mới chưa đủ.</b> Danh sách vượt 1.000 dòng; mở Đã ghi sổ để xem tiếp.</p>'
    for item in periods:
        period = item["debt_period"]
        period_url = href("/period", name=name, period=period, as_of=as_of.isoformat())
        exception_target = exception_href({"customer_mode": "exact", "customer": name,
                                           "period_mode": "exact", "period": period,
                                           "code_mode": "all", "code": None})
        period_group = (filtered_exception_summary(customer_summary, "period", period)
                        if not history_error and customer_summary is not None else None)
        period_warning = (period_source_warning(period_group, exception_target)
                          if period_group is not None else source_warning(None, None, exception_target))
        events = history_by_period.get(period, [])
        postings = postings_by_period.get(period, [])
        expected_events_value = item["replay_event_count"]
        expected_events = int(expected_events_value) if expected_events_value is not None else None
        expected_events_text = count_text(expected_events_value)
        replay_sum = sum(int(event["signed_amount_vnd"]) for event in events)
        posting_sum = sum(int(posting["signed_amount_vnd"]) for posting in postings)
        opening_known = item["opening_vnd"] is not None
        complete = (not history_error and opening_known and expected_events is not None
                    and len(events) == expected_events
                    and replay_sum == int(item["opening_vnd"])
                    and posting_sum == int(item["movement_vnd"] or 0)
                    and not history_truncated and not postings_truncated)
        month_carry = carried_by_period[period]
        detail_rows, charge_total, payment_total, detail_end = month_rows(
            events, postings, month_carry)
        current_end = month_carry + int(item["balance_vnd"])
        incomplete = not complete or detail_end != current_end
        period_badge = status_badge(item["comparison_status"]) if item["comparison_status"] != "MATCH" else ""
        detail_badge = ('<span class="badge alert">Thiếu chi tiết</span>'
                        if incomplete and HISTORY_ENABLED else '')
        expanded = ' open' if item is periods[0] else ''
        content += (f'<details class="panel month-panel" id="period-{esc(period)}"{expanded}>'
                    f'<summary class="month-band"><span>Tháng {esc(period[5:7])}/{esc(period[:4])}</span>'
                    f'<strong>Còn nợ kỳ {money(item["balance_vnd"])}</strong>'
                    f'{period_badge}{detail_badge}</summary>'
                    f'{period_warning}'
                    f'<div class="period-totals"><span>Phát sinh nợ <b>{money(charge_total) if complete else "—"}</b></span>'
                    f'<span>Đã thu / giảm <b>{money(payment_total) if complete else "—"}</b></span></div>')
        if incomplete and HISTORY_ENABLED:
            if opening_known:
                replay_detail = (f'({len(events)}/{expected_events_text} sự kiện replay; '
                                 f'{money(replay_sum)} / {money(item["opening_vnd"])} mở sổ kỳ). ')
            else:
                replay_detail = 'Kỳ mới không có số mở sổ lịch sử; không thể đối chiếu replay với opening. '
            content += (f'<div class="replay-warning">Chi tiết hiển thị chưa đối chiếu đủ với sổ chính '
                        f'{replay_detail}Dùng số dư kỳ từ sổ chính và mở đối soát kỳ để kiểm nguồn.</div>')
        content += detail_rows
        content += (f'<details class="period-explanation"><summary>Cách tính và nguồn số dư</summary>'
                    f'<p>Nợ các kỳ trước {money(month_carry)} · Số mở sổ kỳ {money(item["opening_vnd"])} '
                    f'· Bút toán mới {money(item["movement_vnd"] or 0)} · '
                    f'Còn nợ đến kỳ {money(current_end)}. '
                    f'{anchor("Xem đối soát kỳ →", period_url)}</p></details></details>')
    if not periods:
        content += '<section class="panel empty">Không có kỳ công nợ từ tháng đã chọn.</section>'
    return content


def render_period(db: LedgerDB, as_of: date, name: str, period: str,
                  history: HistoryDB | None = None) -> str | None:
    rows, postings = db.period_screen(as_of, name, period)
    if not rows:
        return None
    row = rows[0]
    summary = reconciliation = None
    if history:
        try:
            summary = history.exception_summary(customer=name, period=period)
            result = history.customer_reconciliations(customer=name)
            reconciliation = next(
                (item for item in result.get("items", []) if item.get("customer") == name), None)
        except LedgerUnavailable:
            summary = reconciliation = None
    exception_target = exception_href({"customer_mode": "exact", "customer": name,
                                       "period_mode": "exact", "period": period,
                                       "code_mode": "all", "code": None})
    content = (f'<div class="customer-title">'
               f'{anchor("← Sổ khách", href("/customer", name=name, as_of=as_of.isoformat()))}'
               f'<h1>{esc(name)} · {esc(period[5:7])}/{esc(period[:4])}</h1></div>')
    content += (f'<section class="customer-balance"><span>Còn nợ kỳ</span>'
                f'<strong>{money(row["balance_vnd"])}</strong></section>')
    if summary is None:
        content += source_warning(None, None, exception_target)
    else:
        reconciliation_detail = (reconciliation_text(reconciliation) if reconciliation else
                                 "Đối chiếu sổ cũ theo khách: chưa có dòng đối chiếu.")
        detail = total_anomaly_text(summary) + " " + reconciliation_detail
        content += source_warning(summary, [reconciliation] if reconciliation else [], exception_target, detail)
    if row["comparison_status"] == "NO_BASELINE":
        content += (f'<p class="attention-line">{status_badge(row["comparison_status"])} '
                    f'Cần kiểm tra mốc đối soát của kỳ này.</p>')
    elif row["comparison_status"] != "MATCH":
        content += (f'<p class="attention-line">{status_badge(row["comparison_status"])} '
                    f'Chưa có mốc lịch sử để so sánh.</p>')
    if row["opening_vnd"] is None:
        content += ('<p class="attention-line">Kỳ mới chưa có số mở sổ lịch sử. '
                    'Dấu — nghĩa là chưa biết, không phải 0; replay không được đối chiếu với opening của kỳ này.</p>')
    replay_link = anchor("Xem dòng lịch sử ↗", "http://127.0.0.1:8765" + href("/period", name=name, period=period))
    content += (f'<details class="period-explanation period-page-explanation">'
                f'<summary>Cách tính và dòng nguồn</summary><p>Số mở sổ kỳ '
                f'{money(row["opening_vnd"])} · Bút toán sau mở sổ '
                f'{money(row["movement_vnd"] or 0)} · '
                f'{count_text(row["replay_event_count"])} dòng lịch sử. {replay_link}</p></details>')
    lines = []
    for item in postings:
        lines.append(f'<tr><td>{esc(item["posting_date"])}</td><td>{esc(KIND.get(item["kind"], item["kind"]))}</td>'
                     f'<td class="amount">{money(item["signed_amount_vnd"])}</td>'
                     f'<td>{anchor("Đề nghị #" + str(item["proposal_id"]), href("/proposal", id=item["proposal_id"]))}</td>'
                     f'<td>{esc(item["maker"])} / {esc(item["checker"])}</td></tr>')
    if lines:
        content += (f'<section class="panel"><div class="panel-head"><h2>Bút toán sau mở sổ</h2></div>'
                    f'<div class="table-wrap"><table><thead><tr><th>Ngày ghi</th><th>Loại</th>'
                    f'<th class="amount">Số tiền</th><th>Phiếu</th><th>Nhập / duyệt</th></tr></thead>'
                    f'<tbody>{"".join(lines)}</tbody></table></div></section>')
    else:
        content += '<p class="empty-line">Chưa có bút toán sau mở sổ.</p>'
    return content


def exception_filter(query: dict, key: str, limit: int) -> tuple[str | None, str, str | None]:
    mode = arg(query, f"{key}_mode", 16)
    present = key in query
    value = arg(query, key, limit)
    if not mode:
        if not present:
            return None, "all", None
        mode = "unclassified" if not value.strip(" \t\n\r\f\v") else "exact"
    if mode == "all":
        return None, mode, None
    if mode == "unclassified":
        return "", mode, None
    if mode != "exact" or not value.strip(" \t\n\r\f\v"):
        raise ValueError(f"invalid {key} filter mode or value")
    return value, mode, value


def exception_filters(query: dict) -> dict:
    filters = {}
    for key, limit in (("customer", 250), ("period", 250), ("code", 250)):
        raw = arg(query, key, limit)
        if "\x00" in raw:
            raise ValueError(f"invalid {key} filter")
        value, mode, display = exception_filter(query, key, limit)
        filters[key], filters[f"{key}_mode"], filters[f"{key}_display"] = value, mode, display
    return filters


def exception_group_list(summary: dict, key: str, filters: dict) -> str:
    field = {"customer": "customer", "period": "period", "code": "code"}[key]
    groups = summary.get(f"by_{key}")
    if not isinstance(groups, list):
        raise LedgerUnavailable("M1 exception summary incomplete")
    rows = []
    for group in groups:
        status = group.get("group_status")
        value = group.get(field)
        label = "Chưa phân loại" if status == "UNCLASSIFIED" else str(value)
        next_filters = dict(filters)
        next_filters[f"{key}_mode"] = "unclassified" if status == "UNCLASSIFIED" else "exact"
        next_filters[key] = "" if status == "UNCLASSIFIED" else value
        target = exception_href(next_filters)
        counts = (f'{count_text(group.get("exception_count"))} ngoại lệ · '
                  f'{count_text(group.get("source_row_count"))} dòng nguồn · '
                  f'{count_text(group.get("trip_source_row_count"))} chuyến có ngoại lệ')
        rows.append(f'<li>{anchor(label, target)} · {esc(counts)}</li>')
    return "".join(rows) or '<li class="empty">Không có nhóm trong bộ lọc này.</li>'


def render_exception_reconciliations(items: list[dict]) -> str:
    rows = []
    for item in items:
        customer = item.get("customer")
        name = "Chưa phân loại" if customer is None or not str(customer).strip(" \t\n\r\f\v") else str(customer)
        customer_cell = esc(name)
        if customer is not None and str(customer).strip(" \t\n\r\f\v"):
            customer_cell = anchor(name, href("/customer", name=customer))
        rows.append(f'<tr><th scope="row">{customer_cell}</th>'
                    f'<td>{esc(reconciliation_text(item))}</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="2" class="empty">Chưa có dòng đối chiếu theo khách.</td></tr>')
    return ('<section class="panel"><div class="panel-head"><h2>Chênh sổ cũ theo khách</h2>'
            '<span class="result-count">Không phân bổ xuống kỳ</span></div>'
            '<div class="table-wrap"><table><thead><tr><th>Khách hàng</th><th>Trạng thái và chênh lệch</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div></section>')


def render_exceptions(history: HistoryDB | None, filters: dict, page_number: int) -> str:
    if history is None:
        raise LedgerUnavailable("M1 history unavailable")
    args = {key: filters[key] for key in ("customer", "period", "code")}
    summary = history.exception_summary(**args)
    result = history.exception_page(**args, page=page_number, page_size=50)
    reconciliation = history.customer_reconciliations(customer=filters["customer"])
    total = amount_integer(result.get("total_results"))
    items = result.get("items")
    reconciliation_items = reconciliation.get("items")
    if total is None or total < 0 or not isinstance(items, list) or not isinstance(reconciliation_items, list):
        raise LedgerUnavailable("M1 history response incomplete")
    if result.get("page") != page_number or result.get("page_size") != 50:
        raise LedgerUnavailable("M1 history page mismatch")

    form_fields = []
    for key, mode_label, input_label in (
            ("customer", "Phạm vi khách", "Tên khách chính xác"),
            ("period", "Phạm vi kỳ", "Giá trị kỳ chính xác"),
            ("code", "Phạm vi mã", "Mã chính xác")):
        mode = filters[f"{key}_mode"]
        options = "".join(f'<option value="{option}"{" selected" if mode == option else ""}>{esc(title)}</option>'
                          for option, title in (("all", "Tất cả"), ("unclassified", "Chưa phân loại"),
                                                ("exact", "Giá trị chính xác")))
        input_type = "search"
        form_fields.append(
            f'<label for="{key}_mode">{esc(mode_label)}<select id="{key}_mode" name="{key}_mode">{options}</select></label>'
            f'<label for="{key}">{esc(input_label)}<input id="{key}" name="{key}" type="{input_type}" '
            f'maxlength="250" value="{esc(filters[f"{key}_display"] or "")}"></label>')
    form = ('<form class="filterbar exception-filters" action="/exceptions" method="get">'
            + "".join(form_fields) + '<button type="submit">Lọc</button></form>')
    total_pages = max(1, (total + 49) // 50)
    pager_links = []
    if page_number > 1:
        pager_links.append(anchor("← Trước", exception_href(filters, page_number - 1)))
    pager_links.append(f'<span>Trang {page_number} / {total_pages} · {total} kết quả · 50 mỗi trang</span>')
    if page_number * 50 < total:
        pager_links.append(anchor("Sau →", exception_href(filters, page_number + 1)))
    pager = f'<nav class="pager" aria-label="Phân trang">{"".join(pager_links)}</nav>'

    rows = []
    for item in items:
        customer_status = item.get("customer_group_status")
        period_status = item.get("period_group_status")
        code_status = item.get("code_group_status")
        if code_status is None and (item.get("code") is None or
                                    not str(item.get("code")).strip(" \t\n\r\f\v")):
            code_status = "UNCLASSIFIED"
        customer = "Chưa phân loại" if customer_status == "UNCLASSIFIED" else item.get("customer")
        period = "Chưa phân loại" if period_status == "UNCLASSIFIED" else item.get("period")
        code = "Chưa phân loại" if code_status == "UNCLASSIFIED" else item.get("code")
        source_url = web_source_url(item.get("source_url"))
        source = anchor("Dòng nguồn ↗", source_url, "source-link") if source_url else "Liên kết nguồn không hợp lệ"
        rows.append(f'<tr><td>{esc(code)}</td><td>{esc(item.get("status"))}</td>'
                    f'<td>{esc(customer)}</td><td>{esc(period)}</td>'
                    f'<td class="exception-detail">{esc(item.get("detail"))}</td><td>{source}</td></tr>')
    if not rows:
        rows.append('<tr><td colspan="6" class="empty">Không có ngoại lệ trong trang này.</td></tr>')
    table = ('<section class="panel"><div class="table-wrap"><table class="exception-table">'
             '<thead><tr><th>Mã</th><th>Trạng thái</th><th>Khách</th><th>Kỳ</th>'
             f'<th>Chi tiết</th><th>Nguồn</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>{pager}</section>')
    detail_text = total_anomaly_text(summary) + " " + reconciliation_overview(
        reconciliation_items, reconciliation.get("reconciliation_status") == "AVAILABLE")
    warning = source_warning(summary, reconciliation_items, exception_href(filters), detail_text)
    groups = ('<section class="exception-groups"><h2>Nhóm trong bộ lọc</h2>'
              + "".join(f'<section><h3>{title}</h3><ul>{exception_group_list(summary, key, filters)}</ul></section>'
                       for key, title in (("customer", "Khách hàng"), ("period", "Kỳ nợ"), ("code", "Mã ngoại lệ")))
              + '</section>')
    return (heading("Nguồn lịch sử", "Ngoại lệ nguồn", "Số ngoại lệ khác số dòng nguồn và khác số chuyến có ngoại lệ.")
            + warning + form + table + groups + render_exception_reconciliations(reconciliation_items))


def render_pending(db: LedgerDB) -> str:
    items = db.proposals("pending")
    content = heading("", "Khoản chờ duyệt", "Các khoản này chưa làm đổi số dư.")
    if not items:
        return content + '<p class="empty-line">Không có khoản chờ.</p>'
    lines = []
    for item in items:
        lines.append(f'<tr><th scope="row">{anchor("#" + str(item["proposal_id"]), href("/proposal", id=item["proposal_id"]))}</th>'
                     f'<td>{esc(KIND.get(item["kind"], item["kind"]))}</td><td class="amount">{money(item["total_vnd"])}</td>'
                     f'<td>{esc(item["posting_date"])}</td></tr>')
    content += (f'<section class="panel"><div class="panel-head"><h2>{len(items)} khoản</h2></div>'
                f'<div class="table-wrap"><table><thead><tr><th>Phiếu</th><th>Loại</th>'
                f'<th class="amount">Số tiền</th><th>Ngày ghi</th></tr></thead>'
                f'<tbody>{"".join(lines)}</tbody></table></div></section>')
    return content


def render_postings(db: LedgerDB, as_of: date) -> str:
    items = db.postings(as_of)
    content = heading("", "Đã ghi sổ", "Giao dịch sau mở sổ đã được duyệt.")
    if not items:
        return content + '<p class="empty-line">Chưa có bút toán mới.</p>'
    lines = []
    for item in items:
        lines.append(f'<tr><td>{esc(item["posting_date"])}</td><td>{anchor(item["customer"], href("/customer", name=item["customer"], as_of=as_of.isoformat()))}</td>'
                     f'<td>{esc(item["debt_period"])}</td><td>{esc(KIND.get(item["kind"], item["kind"]))}</td>'
                     f'<td class="amount">{money(item["signed_amount_vnd"])}</td>'
                     f'<td>{anchor("#" + str(item["proposal_id"]), href("/proposal", id=item["proposal_id"]))}</td></tr>')
    content += (f'<section class="panel"><div class="panel-head"><h2>{len(items)} giao dịch</h2></div>'
                f'<div class="table-wrap"><table><thead><tr><th>Ngày ghi</th><th>Khách</th><th>Kỳ</th>'
                f'<th>Loại</th><th class="amount">Số tiền có dấu</th><th>Phiếu</th></tr></thead><tbody>'
                f'{"".join(lines)}'
                f'</tbody></table></div></section>')
    return content


def render_proposal(db: LedgerDB, proposal_id: int) -> str | None:
    found, lines, audits = db.proposal_screen(proposal_id)
    if not found:
        return None
    item = found[0]
    status = {"pending": "Chờ duyệt", "posted": "Đã ghi sổ", "rejected": "Đã từ chối"}.get(item["status"], item["status"])
    back = "/pending" if item["status"] == "pending" else "/postings"
    content = (f'<div class="customer-title">{anchor("← Danh sách", back)}'
               f'<h1>Phiếu #{proposal_id}</h1></div>')
    content += (f'<section class="customer-balance"><span>{esc(KIND.get(item["kind"], item["kind"]))}</span>'
                f'<strong>{money(item["total_vnd"])}</strong><span class="badge neutral">{esc(status)}</span></section>')
    facts = [("Ngày giao dịch", item["event_date"]), ("Ngày ghi sổ", item["posting_date"]),
             ("Người nhập", item["maker"]),
             ("Người duyệt", item["checker"] or "Chưa có"), ("Nguồn", item["source_ref"]),
             ("Chứng cứ", item["evidence_ref"]), ("Lý do", item["reason"])]
    content += '<section class="panel"><div class="panel-head"><h2>Phân bổ theo kỳ</h2></div><div class="table-wrap"><table>'
    content += '<thead><tr><th>Khách</th><th>Kỳ</th><th class="amount">Giá trị</th></tr></thead><tbody>'
    content += "".join(f'<tr><td>{esc(line["customer"])}</td><td>{esc(line["debt_period"])}</td>'
                       f'<td class="amount">{money(line["amount_vnd"])}</td></tr>' for line in lines)
    content += '</tbody></table></div></section>'
    content += '<details class="panel proposal-details"><summary>Thông tin và bằng chứng</summary><dl class="facts">'
    content += "".join(f'<div><dt>{esc(label)}</dt><dd>{esc(value)}</dd></div>' for label, value in facts) + '</dl></details>'
    if audits:
        content += '<details class="panel proposal-details"><summary>Nhật ký xử lý</summary><div class="table-wrap"><table>'
        content += '<thead><tr><th>Thời gian</th><th>Người</th><th>Hành động</th></tr></thead><tbody>'
        content += "".join(f'<tr><td>{esc(a["at"])}</td><td>{esc(a["actor"])}</td><td>{esc(a["action"])}</td></tr>' for a in audits)
        content += '</tbody></table></div></details>'
    return content


def arg(query: dict, key: str, length: int = 250) -> str:
    value = query.get(key, [""])[0]
    if len(value) > length:
        raise ValueError("query too long")
    return value


def as_of_arg(query: dict) -> date:
    text = arg(query, "as_of", 10)
    if text and (not text.isascii() or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text)):
        raise ValueError("invalid date")
    selected = date.fromisoformat(text) if text else today()
    if selected < OPENING_DATE or selected > today():
        raise ValueError("date outside ledger range")
    return selected


def period_arg(query: dict, key: str = "period", optional: bool = False) -> str:
    value = arg(query, key, 7)
    if optional and not value:
        return ""
    if not value:
        value = today().strftime("%Y-%m")
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("invalid period")
    return value


def exception_page_arg(query: dict) -> int:
    raw = arg(query, "page", 20)
    if not raw:
        return 1
    if not raw.isascii() or not raw.isdigit() or int(raw) < 1:
        raise ValueError("invalid page")
    return int(raw)


def opening_validation(db: LedgerDB, as_of: date) -> dict:
    components = {"cutover": "unavailable", "opening_periods": "unavailable",
                  "opening_vnd": "unavailable", "no_baseline": "unavailable"}
    cutover_row = None
    totals = None
    try:
        rows = db.cutover()
        if (len(rows) == 1 and rows[0].get("capture_id") == CAPTURE
                and rows[0].get("as_of") == OPENING_DATE.isoformat()
                and all(isinstance(rows[0].get(key), str)
                        and re.fullmatch(r"[0-9a-f]{64}", rows[0][key])
                        for key in ("source_workbook_sha256", "engine_sha256"))):
            components["cutover"] = "ok"
            cutover_row = rows[0]
        else:
            components["cutover"] = "invalid"
    except Exception:
        components["cutover"] = "unavailable"
    try:
        totals = db.totals(as_of)
        for key, expected in OPENING_INVARIANTS.items():
            observed = amount_integer(totals.get(key)) if isinstance(totals, dict) else None
            components[key] = "ok" if observed == expected else "invalid"
    except Exception:
        totals = None
    return {"ok": all(status == "ok" for status in components.values()),
            "components": components, "cutover": cutover_row, "totals": totals}


def request_history(db: LedgerDB, configured: HistoryDB | None) -> HistoryDB | None:
    cutovers = db.cutover()
    if (len(cutovers) != 1 or cutovers[0].get("capture_id") != CAPTURE
            or cutovers[0].get("as_of") != OPENING_DATE.isoformat()):
        raise LedgerUnavailable("opening provenance mismatch")
    if isinstance(configured, HistoryDB):
        cutover = cutovers[0]
        if not all(isinstance(cutover.get(key), str) and cutover[key]
                   for key in ("source_workbook_sha256", "engine_sha256")):
            raise LedgerUnavailable("opening provenance incomplete")
        return HistoryDB(dbname=configured.dbname, psql=configured.psql, cutover={
            "capture_id": cutover["capture_id"], "as_of": cutover["as_of"],
            "source_workbook_sha256": cutover["source_workbook_sha256"],
            "engine_sha256": cutover["engine_sha256"],
        })
    return configured


def health_payload(db: LedgerDB, history: HistoryDB | None, as_of: date) -> tuple[int, dict]:
    opening = opening_validation(db, as_of)
    components = dict(opening["components"])
    if opening["ok"] and isinstance(history, HistoryDB):
        history = HistoryDB(dbname=history.dbname, psql=history.psql, cutover={
            "capture_id": opening["cutover"]["capture_id"],
            "as_of": opening["cutover"]["as_of"],
            "source_workbook_sha256": opening["cutover"]["source_workbook_sha256"],
            "engine_sha256": opening["cutover"]["engine_sha256"],
        }) if isinstance(history, HistoryDB) else None
    summary_status = reconciliation_status = "unavailable"
    try:
        if not opening["ok"]:
            raise LedgerUnavailable("opening cutover unavailable")
        if history is None:
            raise LedgerUnavailable("M1 history unavailable")
        history.exception_summary()
        summary_status = "ok"
    except Exception:
        summary_status = "unavailable"
    try:
        if not opening["ok"]:
            raise LedgerUnavailable("opening cutover unavailable")
        if history is None:
            raise LedgerUnavailable("M1 history unavailable")
        history.customer_reconciliations()
        reconciliation_status = "ok"
    except Exception:
        reconciliation_status = "unavailable"
    components["history_exception_summary"] = summary_status
    components["history_customer_reconciliation"] = reconciliation_status
    components["history_provenance"] = ("ok" if summary_status == reconciliation_status == "ok"
                                         else "unavailable")
    if not HISTORY_ENABLED:
        components["history_exception_summary"] = components["history_customer_reconciliation"] = \
            components["history_provenance"] = "not_applicable"
    totals = opening["totals"] if isinstance(opening["totals"], dict) else {}
    ok = opening["ok"] and (not HISTORY_ENABLED or summary_status == reconciliation_status == "ok")
    payload = {"ok": ok, "components": components,
               "data_scope": getattr(db, "data_scope", "configured database contents; may be fixture data"),
               "capture_id": CAPTURE, "as_of": OPENING_DATE.isoformat(),
               "opening_periods": totals.get("opening_periods"),
               "opening_vnd": totals.get("opening_vnd"),
               "no_baseline": totals.get("no_baseline"),
               "balance_vnd": totals.get("balance_vnd"), "pending": totals.get("pending")}
    return (200 if ok else 503), payload


class LedgerHandler(BaseHTTPRequestHandler):
    db: LedgerDB
    history: HistoryDB | None = None
    port: int

    def send(self, code: int, data: bytes, content_type: str = "text/html; charset=utf-8", body: bool = True):
        self.send_response(code)
        for key, value in (("Content-Type", content_type), ("Content-Length", str(len(data))),
                           ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                           ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                           ("Content-Security-Policy", "default-src 'none'; style-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")):
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(data)

    def handle_read(self, body: bool):
        if self.headers.get("Host", "").lower() not in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"):
            self.send(400, b"Invalid Host", "text/plain; charset=utf-8", body)
            return
        if len(self.path) > 4096:
            self.send(414, b"URL too long", "text/plain; charset=utf-8", body)
            return
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        try:
            if parsed.path == "/style.css":
                self.send(200, STYLE, "text/css; charset=utf-8", body)
                return
            if parsed.path == "/favicon.ico":
                self.send(204, b"", body=body)
                return
            if parsed.path == "/health":
                status, payload = health_payload(self.db, self.history, today())
                self.send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", body)
                return
            current_history = request_history(self.db, self.history)
            if parsed.path == "/exceptions" and not HISTORY_ENABLED:
                self.send(404, page("Ngoại lệ nguồn", heading(
                    "404", "Không có ngoại lệ replay cho sổ mở ngày 19/10/2026", ""), today()), body=body)
                return
            if parsed.path == "/exceptions":
                filters = exception_filters(query)
                page_number = exception_page_arg(query)
                rendered = render_exceptions(current_history, filters, page_number)
                self.send(200, page("Ngoại lệ nguồn", rendered, today(), wide=True), body=body)
                return
            as_of = as_of_arg(query)
            if parsed.path == "/":
                rendered = render_overview(self.db, as_of, arg(query, "q", 120),
                                           period_arg(query), current_history)
                title = "Tổng quan"
            elif parsed.path == "/customer":
                name = arg(query, "name")
                rendered = render_customer(self.db, as_of, name, period_arg(query, "first_period", True), current_history) if name else None
                title = name
            elif parsed.path == "/period":
                name, period = arg(query, "name"), arg(query, "period", 7)
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
                    raise ValueError("invalid period")
                rendered = render_period(self.db, as_of, name, period, current_history) if name else None
                title = period
            elif parsed.path == "/pending":
                rendered, title = render_pending(self.db), "Chờ duyệt"
            elif parsed.path == "/postings":
                rendered, title = render_postings(self.db, as_of), "Bút toán"
            elif parsed.path == "/proposal":
                raw_id = arg(query, "id", 18)
                if not raw_id.isascii() or not raw_id.isdigit() or int(raw_id) < 1:
                    raise ValueError("invalid proposal ID")
                rendered, title = render_proposal(self.db, int(raw_id)), "Đề nghị"
            else:
                rendered, title = None, "Không tìm thấy"
            if rendered is None:
                self.send(404, page(title, heading("404", "Không tìm thấy", ""), as_of), body=body)
            else:
                self.send(200, page(title, rendered, as_of), body=body)
        except LedgerUnavailable:
            if parsed.path == "/health":
                payload = {"ok": False, "components": {"opening": "unavailable",
                           "history_provenance": "unavailable"},
                           "data_scope": getattr(self.db, "data_scope", "configured database contents; may be fixture data")}
                self.send(503, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", body)
            elif parsed.path == "/exceptions":
                self.send(503, page("Lỗi dữ liệu", heading("503", "Chưa kiểm được ngoại lệ nguồn", ""), today()), body=body)
            else:
                self.send(503, page("Lỗi dữ liệu", heading("503", "Chưa đọc được sổ PostgreSQL", ""), today()), body=body)
        except ValueError:
            self.send(400, page("Yêu cầu sai", heading("400", "Tham số không hợp lệ", ""), today()), body=body)

    def do_GET(self):
        self.handle_read(True)

    def do_HEAD(self):
        self.handle_read(False)

    def do_POST(self):
        self.send(405, b"Read only", "text/plain; charset=utf-8")

    def log_message(self, format, *args):
        return  # Customer names and source references must not enter access logs.


def main():
    port = int(os.environ.get("WEBDEBIT_LEDGER_PORT", "8766"))
    if not 1024 <= port <= 65535:
        raise ValueError("invalid port")
    db = LedgerDB()
    opening = opening_validation(db, today())
    if not opening["ok"]:
        raise RuntimeError("unexpected ledger opening invariants")
    history = HistoryDB(cutover=opening["cutover"]) if HISTORY_ENABLED else None
    LedgerHandler.db, LedgerHandler.history, LedgerHandler.port = db, history, port
    server = ThreadingHTTPServer(("127.0.0.1", port), LedgerHandler)
    server.daemon_threads = True
    print(f"ledger viewer listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
