"""Read-only UI for the independent PostgreSQL receivables ledger."""

from __future__ import annotations

import html
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from zoneinfo import ZoneInfo

from ledger_db import HistoryDB, LedgerDB, LedgerUnavailable

STYLE = Path(__file__).with_name("style.css").read_bytes()
CAPTURE = "2026-10-13-debit-2026-1791884418948"
OPENING_DATE = date(2026, 10, 13)
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


def page(title: str, body: str, selected_date: date, wide: bool = False) -> bytes:
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · Sổ công nợ HTH</title><link rel="stylesheet" href="/style.css"></head>
<body><a class="skip" href="#main">Đến nội dung</a>
<header class="topbar"><div class="topbar-inner"><a class="brand" href="/">
<span class="brand-mark">H</span><span>HTH <small>Sổ công nợ</small></span></a>
<nav aria-label="Điều hướng chính"><a href="/">Công nợ</a><a href="/pending">Khoản chờ</a>
<a href="/postings">Đã ghi sổ</a></nav><span class="read-only">Xem đến {selected_date.strftime('%d/%m/%Y')}</span></div></header>
<main id="main" class="container{' wide' if wide else ''}">{body}</main>
<footer class="container"><details class="site-notes"><summary>Nguồn dữ liệu và giới hạn</summary>
<p>Sổ PostgreSQL độc lập. Số mở sổ từ snapshot {CAPTURE}. Kỳ thiếu mốc đối soát vẫn được gắn cờ.
Web chỉ đọc; nguồn replay và dữ liệu ngân hàng chưa được xác minh thay cho chứng từ gốc.</p></details></footer>
</body></html>""".encode()


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


def render_overview(db: LedgerDB, as_of: date, search: str, period: str = "2026-10") -> str:
    t = db.totals(as_of)
    customers = db.overview(as_of, period, search)
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
    alerts = []
    if t["no_baseline"]:
        alerts.append(f'{int(t["no_baseline"])} kỳ thiếu mốc đối soát')
    if t["pending"]:
        alerts.append(anchor(f'{int(t["pending"])} khoản chờ duyệt', "/pending"))
    if alerts:
        content += '<p class="attention-line">Cần kiểm tra: ' + ' · '.join(alerts) + '</p>'
    rows = []
    for item in customers:
        customer_url = href("/customer", name=item["customer"], as_of=as_of.isoformat())
        balance = int(item["period_balance_vnd"])
        status = ('Thiếu mốc' if item["comparison_status"] == 'NO_BASELINE' else
                  'Còn nợ' if balance > 0 else 'Dư có' if balance < 0 else
                  'Đã tất toán' if item["comparison_status"] else 'Chưa có kỳ')
        tone = 'warn' if item["comparison_status"] == 'NO_BASELINE' else ('good' if balance == 0 else 'neutral')
        rows.append(f'<tr><th scope="row">{esc(item["customer"])}</th>'
                    f'<td class="amount" data-label="Còn nợ kỳ">{money(item["period_balance_vnd"])}</td>'
                    f'<td class="amount" data-label="Tổng còn nợ">{money(item["total_balance_vnd"])}</td>'
                    f'<td data-label="Tình trạng"><span class="badge {tone}">{esc(status)}</span></td>'
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


def source_value(values: list, index: int):
    """Ô thứ `index` của dòng nguồn, None nếu dòng ngắn hơn."""
    return values[index] if index < len(values) else None


def month_rows(events: list[dict], postings: list[dict], carried: int) -> tuple[str, int, int, int]:
    """Render independent debt and payment lists with no implied allocation."""
    charges, payments = [], []
    for event in events:
        signed = int(event["signed_amount_vnd"])
        values = event.get("source_values") or []
        value = partial(source_value, values)
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
    customers = db.customers(as_of, name)
    row = next((item for item in customers if item["customer"] == name), None)
    if row is None:
        return None
    all_periods = db.periods(as_of, name)
    ascending_periods = list(reversed(all_periods))
    carried_by_period = {}
    carried = 0
    for item in ascending_periods:
        carried_by_period[item["debt_period"]] = carried
        carried += int(item["balance_vnd"])
    periods = [item for item in reversed(ascending_periods)
               if not first_period or item["debt_period"] >= first_period]
    pending = db.pending_for_customer(name)
    history_error = False
    try:
        replay_events = (history.events_for_customer(CAPTURE, name, first_period) if history else [])
    except LedgerUnavailable:
        replay_events, history_error = [], True
    history_truncated = len(replay_events) > 2000
    replay_events = replay_events[:2000]
    history_by_period = {}
    for event in replay_events:
        history_by_period.setdefault(event["debt_period"], []).append(event)
    new_postings = db.postings(as_of, name, limit=1001)
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
    if history_error:
        content += '<p class="attention-line"><b>Thiếu chi tiết lịch sử.</b> Số dư kỳ vẫn lấy từ sổ chính; mở đối soát kỳ để kiểm nguồn.</p>'
    if history_truncated:
        content += '<p class="attention-line"><b>Chi tiết lịch sử chưa đủ.</b> Danh sách vượt 2.000 sự kiện; mở đối soát kỳ để xem tiếp.</p>'
    if postings_truncated:
        content += '<p class="attention-line"><b>Bút toán mới chưa đủ.</b> Danh sách vượt 1.000 dòng; mở Đã ghi sổ để xem tiếp.</p>'
    for item in periods:
        period = item["debt_period"]
        period_url = href("/period", name=name, period=period, as_of=as_of.isoformat())
        events = history_by_period.get(period, [])
        postings = postings_by_period.get(period, [])
        expected_events = int(item["replay_event_count"] or 0)
        replay_sum = sum(int(event["signed_amount_vnd"]) for event in events)
        posting_sum = sum(int(posting["signed_amount_vnd"]) for posting in postings)
        complete = (not history_error and len(events) == expected_events
                    and replay_sum == int(item["opening_vnd"] or 0)
                    and posting_sum == int(item["movement_vnd"] or 0)
                    and not history_truncated and not postings_truncated)
        month_carry = carried_by_period[period]
        detail_rows, charge_total, payment_total, detail_end = month_rows(
            events, postings, month_carry)
        current_end = month_carry + int(item["balance_vnd"])
        incomplete = not complete or detail_end != current_end
        period_badge = status_badge(item["comparison_status"]) if item["comparison_status"] != "MATCH" else ""
        detail_badge = '<span class="badge alert">Thiếu chi tiết</span>' if incomplete else ''
        expanded = ' open' if item is periods[0] else ''
        content += (f'<details class="panel month-panel" id="period-{esc(period)}"{expanded}>'
                    f'<summary class="month-band"><span>Tháng {esc(period[5:7])}/{esc(period[:4])}</span>'
                    f'<strong>Còn nợ kỳ {money(item["balance_vnd"])}</strong>'
                    f'{period_badge}{detail_badge}</summary>'
                    f'<div class="period-totals"><span>Phát sinh nợ <b>{money(charge_total) if complete else "—"}</b></span>'
                    f'<span>Đã thu / giảm <b>{money(payment_total) if complete else "—"}</b></span></div>')
        if incomplete:
            content += (f'<div class="replay-warning">Chi tiết hiển thị chưa đối chiếu đủ với sổ chính '
                        f'({len(events)}/{expected_events} sự kiện replay; {money(replay_sum)} / '
                        f'{money(item["opening_vnd"] or 0)} mở sổ kỳ). '
                        f'Dùng số dư kỳ từ sổ chính và mở đối soát kỳ để kiểm nguồn.</div>')
        content += detail_rows
        content += (f'<details class="period-explanation"><summary>Cách tính và nguồn số dư</summary>'
                    f'<p>Nợ các kỳ trước {money(month_carry)} · Số mở sổ kỳ {money(item["opening_vnd"] or 0)} '
                    f'· Bút toán mới {money(item["movement_vnd"] or 0)} · '
                    f'Còn nợ đến kỳ {money(current_end)}. '
                    f'{anchor("Xem đối soát kỳ →", period_url)}</p></details></details>')
    if not periods:
        content += '<section class="panel empty">Không có kỳ công nợ từ tháng đã chọn.</section>'
    return content


def render_period(db: LedgerDB, as_of: date, name: str, period: str) -> str | None:
    rows = db.period(as_of, name, period)
    if not rows:
        return None
    row = rows[0]
    content = (f'<div class="customer-title">'
               f'{anchor("← Sổ khách", href("/customer", name=name, as_of=as_of.isoformat()))}'
               f'<h1>{esc(name)} · {esc(period[5:7])}/{esc(period[:4])}</h1></div>')
    content += (f'<section class="customer-balance"><span>Còn nợ kỳ</span>'
                f'<strong>{money(row["balance_vnd"])}</strong></section>')
    if row["comparison_status"] == "NO_BASELINE":
        content += (f'<p class="attention-line">{status_badge(row["comparison_status"])} '
                    f'Cần kiểm tra mốc đối soát của kỳ này.</p>')
    elif row["comparison_status"] != "MATCH":
        content += (f'<p class="attention-line">{status_badge(row["comparison_status"])} '
                    f'Chưa có mốc lịch sử để so sánh.</p>')
    replay_link = anchor("Xem dòng lịch sử ↗", "http://127.0.0.1:8765" + href("/period", name=name, period=period))
    content += (f'<details class="period-explanation period-page-explanation">'
                f'<summary>Cách tính và dòng nguồn</summary><p>Số mở sổ kỳ '
                f'{money(row["opening_vnd"] or 0)} · Bút toán sau mở sổ '
                f'{money(row["movement_vnd"] or 0)} · '
                f'{int(row["replay_event_count"] or 0)} dòng lịch sử. {replay_link}</p></details>')
    postings = db.postings(as_of, name, period)
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
    found = db.proposal(proposal_id)
    if not found:
        return None
    item = found[0]
    lines = db.proposal_lines(proposal_id)
    audits = db.proposal_audit(proposal_id)
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
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
        raise ValueError("invalid period")
    return value


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
            cutover = self.db.cutover()
            if len(cutover) != 1 or cutover[0]["capture_id"] != CAPTURE or cutover[0]["as_of"] != OPENING_DATE.isoformat():
                raise LedgerUnavailable("opening provenance mismatch")
            if parsed.path == "/health":
                total = self.db.totals(today())
                ok = int(total["opening_periods"]) == 496 and int(total["opening_vnd"]) == 65051673578
                payload = json.dumps({"ok": ok, "database": "webdebit_ledger", "capture_id": CAPTURE,
                                      "opening_periods": total["opening_periods"], "opening_vnd": total["opening_vnd"],
                                      "balance_vnd": total["balance_vnd"], "pending": total["pending"]}).encode()
                self.send(200 if ok else 503, payload, "application/json; charset=utf-8", body)
                return
            as_of = as_of_arg(query)
            if parsed.path == "/":
                rendered = render_overview(self.db, as_of, arg(query, "q", 120), period_arg(query))
                title = "Tổng quan"
            elif parsed.path == "/customer":
                name = arg(query, "name")
                rendered = render_customer(self.db, as_of, name, period_arg(query, "first_period", True), self.history) if name else None
                title = name
            elif parsed.path == "/period":
                name, period = arg(query, "name"), arg(query, "period", 7)
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
                    raise ValueError("invalid period")
                rendered = render_period(self.db, as_of, name, period) if name else None
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
        except ValueError:
            self.send(400, page("Yêu cầu sai", heading("400", "Tham số không hợp lệ", ""), today()), body=body)
        except LedgerUnavailable:
            self.send(503, page("Lỗi dữ liệu", heading("503", "Chưa đọc được sổ PostgreSQL", ""), today()), body=body)

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
    cutover = db.cutover()
    if len(cutover) != 1 or cutover[0]["capture_id"] != CAPTURE or cutover[0]["as_of"] != OPENING_DATE.isoformat():
        raise RuntimeError("unexpected ledger cutover")
    t = db.totals(today())
    if int(t["opening_periods"]) != 496 or int(t["opening_vnd"]) != 65051673578 or int(t["no_baseline"]) != 46:
        raise RuntimeError("unexpected opening balances")
    LedgerHandler.db, LedgerHandler.history, LedgerHandler.port = db, HistoryDB(), port
    server = ThreadingHTTPServer(("127.0.0.1", port), LedgerHandler)
    server.daemon_threads = True
    print(f"ledger viewer listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
