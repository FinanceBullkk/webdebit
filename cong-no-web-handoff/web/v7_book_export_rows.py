"""Một sổ (`get_ledger` bỏ Lịch sử) thành các hàng của bản xuất cả sổ (XUAT-SO-01, specs/v7-xuat-ca-so.md).

Tiền là int VND; ô không có số là None, không bao giờ 0. Thành tiền như web: chuyến web lấy `amount_vnd`; dòng chuyến sổ gốc lấy
`counted_vnd`, trống khi chưa có đơn giá mà `counted_vnd` là 0 (cùng luật debit note). `expected()` lấy số đối chiếu thẳng từ
`get_ledger`, không qua các hàng, để phép kiểm so với file đã ghi.
"""

from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from v7_xlsx_writer import Month, clean_text

VN = ZoneInfo("Asia/Ho_Chi_Minh")
BOOK = [("Mã sổ", "count", 8), ("Tên sổ", "text", 30)]
COLUMNS = {
    "TỔNG": BOOK + [("Tên hiển thị", "text", 26), ("Trạng thái", "text", 18), ("Mặt hàng", "text", 14), ("Cảng/bộ", "text", 9),
                    ("Nợ còn lại", "money", 16), ("Tháng nợ cũ nhất còn nợ", "month", 13),
                    ("Chuyến chưa giá hoặc chờ kiểm", "count", 13)],
    "THÁNG": BOOK + [("Tháng", "month", 10), ("Nợ các tháng trước", "money", 16), ("Phát sinh", "money", 16),
                     ("Đã thu", "money", 16), ("Còn nợ cuối tháng", "money", 16), ("Nợ còn lại của tháng", "money", 16),
                     ("Số dư đầu khi nạp sổ", "money", 16), ("Khóa", "text", 7)],
    "CHUYẾN": BOOK + [("Nguồn", "text", 8), ("Mã dòng", "count", 9), ("Tháng", "month", 10), ("Ngày", "date", 11),
                      ("Container", "text", 14), ("Booking", "text", 14), ("Hãng tàu", "text", 12), ("Shipper", "text", 16),
                      ("Nơi đi", "text", 14), ("Nơi đến", "text", 14), ("Đơn giá", "money", 14), ("Phụ phí", "money", 13),
                      ("Thành tiền", "money", 14), ("Chưa giá", "text", 9), ("Trạng thái", "text", 11),
                      ("Các khoản phụ phí", "text", 30), ("Ghi chú", "text", 30)],
    "PHIẾU THU": BOOK + [("Nguồn", "text", 10), ("Mã phiếu", "text", 14), ("Mã dòng", "count", 9), ("Ngày", "date", 11),
                         ("Hình thức", "text", 12), ("Tham chiếu, ghi chú", "text", 30), ("Số tiền", "money", 15),
                         ("Đã hủy", "text", 24), ("Cấn trừ với", "text", 24), ("Trừ vào tháng", "text", 20)],
    "PHÂN BỔ THU": BOOK + [("Mã phiếu", "text", 14), ("Mã dòng phiếu", "count", 10), ("Ngày phiếu", "date", 11),
                           ("Trừ vào tháng", "month", 12), ("Loại", "text", 10), ("Số tiền", "money", 15)],
    "ĐIỀU CHỈNH": BOOK + [("Mã dòng", "count", 9), ("Tháng", "month", 10), ("Số tiền", "money", 15), ("Gắn với", "text", 22),
                          ("Ghi chú", "text", 36), ("Ngày ghi", "date", 11)],
}
TABS = tuple(COLUMNS)
DETAIL_TABS = TABS[1:]
AMOUNT = {"CHUYẾN": "Thành tiền", "PHIẾU THU": "Số tiền", "PHÂN BỔ THU": "Số tiền", "ĐIỀU CHỈNH": "Số tiền"}
STATUS = {"active": "Đang dùng", "NO_BASELINE": "Chưa có số dư đầu"}
TRANSPORT = {"CANG": "cảng", "BO": "bộ"}
TRIP_STATUS = {"confirmed": "Tính tiền", "pending_review": "Chờ kiểm", "rejected": "Đã loại"}
LINE_KIND = {"debt": "nợ", "advance": "ứng trước"}


def vnd(value) -> int | None:
    """Tiền dạng chữ số nguyên của DB; None giữ None. Chữ khác là dữ liệu hỏng: báo lỗi, không đoán."""
    if value is None:
        return None
    if isinstance(value, bool) or not re.fullmatch(r"-?[0-9]+", str(value)):
        raise ValueError("VND_FORMAT")
    return int(value)


def text(value) -> str | None:
    return None if value is None or value == "" else clean_text(str(value))


def day(value) -> dt.date | None:
    """Ngày ISO (có thể kèm giờ, đổi sang ngày giờ VN) hoặc dd/mm/yyyy của sổ gốc; không đọc được thì None."""
    if not value:
        return None
    raw = str(value)
    try:
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw):
            return dt.date.fromisoformat(raw)
        if found := re.fullmatch(r"([0-9]{2})/([0-9]{2})/([0-9]{4})", raw):
            return dt.date(int(found[3]), int(found[2]), int(found[1]))
        stamp = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return (stamp.astimezone(VN) if stamp.tzinfo else stamp).date()


def month(value) -> Month | None:
    found = day(value)
    return Month(found.year, found.month, 1) if found else None


def month_text(values) -> str | None:
    """Các tháng dạng mm/yyyy, bỏ trùng, giữ thứ tự; không tháng nào đọc được thì None."""
    found = [f"{m:%m/%Y}" for m in map(month, values) if m]
    return text(", ".join(dict.fromkeys(found)))


def money_text(amount: int | None) -> str:
    return "—" if amount is None else f"{amount:,}".replace(",", ".")


def legacy_amount(current: dict) -> int | None:
    unit, counted = vnd(current.get("unit_price_vnd")), vnd(current.get("counted_vnd"))
    return None if unit is None and counted in (None, 0) else counted


def current_lines(receipt: dict) -> list[dict]:
    return [line for line in receipt.get("allocations") or [] if line.get("superseded_by_event") is None]


def _fees(lines, names: dict[int, str]) -> str | None:
    parts = [f"{names.get(line.get('fee_type_id')) or 'Phụ phí'}{' (' + line['note'] + ')' if line.get('note') else ''}: "
             f"{money_text(vnd(line.get('amount_vnd')))}" for line in lines or []]
    return text("; ".join(parts))


def _void(voided: bool, reason) -> str | None:
    return ("Đã hủy: " + text(reason) if text(reason) else "Đã hủy") if voided else None


def _legacy(ledger: dict, kind: str) -> list[dict]:
    return [row for row in ledger.get("legacy_rows") or [] if row.get("kind") == kind]


def summary_row(customer: dict, ledger: dict) -> list:
    months = ledger.get("months") or []
    oldest = next((month(m["month"]) for m in months if (vnd(m.get("outstanding_vnd")) or 0) > 0), None)
    status = ledger.get("status")   # get_ledger tự xét mốc nạp đang hiệu lực: đúng hơn cột của danh sách khách
    return [customer["id"], text(customer.get("name")), text(customer.get("display_name")), STATUS.get(status, text(status)),
            text(customer.get("commodity")), TRANSPORT.get(customer.get("transport_mode"), text(customer.get("transport_mode"))),
            vnd(ledger.get("total_outstanding_vnd")), oldest, ledger.get("pending_count")]


def book_rows(customer: dict, ledger: dict, fee_names: dict[int, str]) -> dict[str, list[list]]:
    head = [customer["id"], text(customer.get("name"))]
    out = {tab: [] for tab in DETAIL_TABS}
    opening: dict[str, int] = {}
    for row in ledger.get("opening") or []:
        opening[row["month"]] = opening.get(row["month"], 0) + vnd(row["amount_vnd"])
    locks = {row["month"]: row["locked"] for row in ledger.get("month_locks") or []}
    for m in ledger.get("months") or []:
        locked = locks.get(m["month"], m["month"] != ledger.get("today_month"))   # thiếu hàng khóa: chỉ tháng hiện tại mở
        out["THÁNG"].append(head + [month(m["month"]), vnd(m.get("prior_months_vnd")), vnd(m.get("charges_vnd")),
                                    vnd(m.get("received_vnd")), vnd(m.get("end_of_month_vnd")), vnd(m.get("outstanding_vnd")),
                                    opening.get(m["month"]), "Khóa" if locked else "Mở"])
    for t in ledger.get("trips") or []:
        out["CHUYẾN"].append(head + ["web", t["id"], month(t.get("month")), day(t.get("event_date")), text(t.get("container")),
                                     text(t.get("booking")), text(t.get("carrier")), text(t.get("shipper")),
                                     text(t.get("origin")), text(t.get("destination")), vnd(t.get("unit_price_vnd")),
                                     vnd(t.get("other_fee_vnd")), vnd(t.get("amount_vnd")),
                                     "chưa giá" if t.get("is_missing_price") else None,
                                     TRIP_STATUS.get(t.get("status"), text(t.get("status"))), _fees(t.get("fee_lines"), fee_names),
                                     text(t.get("note"))])
    for row in _legacy(ledger, "trip"):
        cur = row.get("current") or {}
        amount = legacy_amount(cur)
        out["CHUYẾN"].append(head + ["sổ gốc", row["id"], month(row.get("month")), day(cur.get("event_date")),
                                     text(cur.get("container")), None, text(cur.get("carrier")), text(cur.get("shipper")),
                                     text(cur.get("origin")), text(cur.get("destination")), vnd(cur.get("unit_price_vnd")),
                                     vnd(cur.get("other_fee_vnd")), amount, "chưa giá" if amount is None else None, "Tính tiền",
                                     _fees(row.get("fee_lines"), fee_names), text((row.get("display") or {}).get("note"))])
    for r in ledger.get("receipts") or []:
        voided, lines = r.get("voided_on") is not None, current_lines(r)
        out["PHIẾU THU"].append(head + ["web", text(r.get("pid")), r["id"], day(r.get("date")), text(r.get("method")),
                                        text(r.get("reference")), vnd(r.get("amount_vnd")), _void(voided, r.get("void_reason")),
                                        text(r.get("counterparty_name")),
                                        None if voided else month_text(a.get("month") for a in lines)])
        if not voided:
            out["PHÂN BỔ THU"] += [head + [text(r.get("pid")), r["id"], day(r.get("date")), month(a.get("month")),
                                           LINE_KIND.get(a.get("kind"), text(a.get("kind"))), vnd(a.get("amount_vnd"))]
                                   for a in lines]
    for row in _legacy(ledger, "receipt"):
        shown = row.get("display") or {}
        notes = [text(v) for v in (shown.get("raw_date"), shown.get("note")) if text(v)]
        out["PHIẾU THU"].append(head + ["sổ gốc", None, row["id"], day(shown.get("date")), None,
                                        text(" · ".join(dict.fromkeys(notes))), vnd(row.get("source_total_vnd")), None, None,
                                        month_text([row.get("month")])])
    for o in ledger.get("outgoing_offsets") or []:
        out["PHIẾU THU"].append(head + ["cấn trừ đi", text(o.get("pid")), o.get("offset_pair_id"), day(o.get("date")),
                                        text(o.get("method")), None, vnd(o.get("amount_vnd")),
                                        _void(o.get("voided_by_event") is not None, o.get("void_reason")),
                                        text(o.get("counterparty_name")), None])
    for a in ledger.get("adjustments") or []:
        link = (f"chuyến {a['trip_id']}" if a.get("trip_id") is not None
                else f"dòng sổ gốc {a['legacy_row_id']}" if a.get("legacy_row_id") is not None else "cả tháng")
        out["ĐIỀU CHỈNH"].append(head + [a["id"], month(a.get("month")), vnd(a.get("amount_vnd")), link, text(a.get("note")),
                                         day(a.get("at"))])
    return out


def _count_sum(values) -> tuple[int, int]:
    values = list(values)
    return len(values), sum(value for value in values if value is not None)


def expected(ledger: dict) -> dict:
    """Số đối chiếu của một sổ lấy thẳng từ `get_ledger`: phép kiểm 5 so với file đọc lại."""
    receipts = ledger.get("receipts") or []
    return {
        "total": vnd(ledger.get("total_outstanding_vnd")),
        "THÁNG": [(month(m["month"]), vnd(m.get("prior_months_vnd")), vnd(m.get("charges_vnd")), vnd(m.get("received_vnd")),
                   vnd(m.get("end_of_month_vnd")), vnd(m.get("outstanding_vnd"))) for m in ledger.get("months") or []],
        "CHUYẾN": _count_sum([vnd(t.get("amount_vnd")) for t in ledger.get("trips") or []]
                             + [legacy_amount(row.get("current") or {}) for row in _legacy(ledger, "trip")]),
        "PHIẾU THU": _count_sum([vnd(r.get("amount_vnd")) for r in receipts]
                                + [vnd(row.get("source_total_vnd")) for row in _legacy(ledger, "receipt")]
                                + [vnd(o.get("amount_vnd")) for o in ledger.get("outgoing_offsets") or []]),
        "PHÂN BỔ THU": _count_sum([vnd(a.get("amount_vnd")) for r in receipts if r.get("voided_on") is None
                                   for a in current_lines(r)]),
        "ĐIỀU CHỈNH": _count_sum([vnd(a.get("amount_vnd")) for a in ledger.get("adjustments") or []]),
    }
