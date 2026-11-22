"""Công cụ tầng A của bot (ZALO-BOT-01 Phần 3): mỗi công cụ đọc API web đang chạy qua `WebApi` (chỉ GET) và rút gọn kết quả.

Mỗi kết quả có `trang`, `link`, `du_lieu_luc` (giờ bot đọc, giờ VN) và `as_of` của máy chủ nếu có; kết quả về một khách có
thêm `doi_soat` (khớp Sheet hay lệch, lần đối soát, có cũ không). Tiền là chuỗi số nguyên trong trường tên `*_vnd`, để bộ kiểm
số điền và đối chiếu (verify.py). Chữ tự do (ghi chú, chữ tin chat, số tài khoản, email người thao tác) bị bỏ trước khi gửi model.
Công cụ admin chỉ được đưa cho người quyền admin (QUYEN-01); API còn mở `/inbox`, `/activity`, `/sheet/doi-chieu` cho mọi
login nên bot tự giữ quyền theo trang. Mỗi kết quả tối đa khoảng 12 KB; dài hơn thì cắt danh sách và báo `da_cat`.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
import unicodedata
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from .config import User
from .webapi import ApiError, Route, WebApi

VN = ZoneInfo("Asia/Ho_Chi_Minh")
MAX_CHARS = 12_000
MAX_ROWS = 30
INBOX_TTL = 60          # /inbox có thể đẩy lượt tính lại của máy sớm hơn: bot giữ kết quả 60 giây
DIGITS = re.compile(r"\d{1,9}")
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")
DAY = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
MONTH01 = re.compile(r"\d{4}-(0[1-9]|1[0-2])-01")
YEAR = re.compile(r"20\d{2}")
# Trường chữ tự do hay định danh người thao tác: không gửi model (spec Phần 5).
DROP = frozenset({
    "note", "notes", "review_reason", "shipper", "carrier", "reference", "void_reason", "display", "actor", "before", "after",
    "message_excerpt", "message_sender", "created_by", "cancelled_by", "cancel_reason", "text", "media", "image", "sender_name",
    "conversation_name", "avatar", "owner", "ref", "findings", "hints", "details", "edit_log", "method", "ghi_chu", "ly_do",
    "auto", "by_actor", "office", "book_shippers", "allocations", "items", "legacy_rows", "sheet_sync", "sheet_prices",
    "sheet_receipts", "ps_fees", "insurance", "sheet_road", "sheet_details", "outgoing_offsets", "opening", "version",
})
ROUTES = {
    "customers": Route("/api/v7/customers"),
    "dashboard": Route("/api/v7/dashboard"),
    "debt": Route("/api/v7/dashboard/debt"),
    "matrix": Route("/api/v7/receivables/matrix", {"year": YEAR}),
    "detail": Route("/api/v7/receivables/detail", {"customer": DIGITS, "month": MONTH01}),
    "ledger": Route("/api/v7/ledger", {"customer": DIGITS}),
    "events": Route("/api/v7/ledger/events", {"customer": DIGITS}),
    "price_table": Route("/api/v7/price-table", {"customer": DIGITS}),
    "price_status": Route("/api/v7/price-table/status", {"customer": DIGITS}),
    "receipt_book": Route("/api/v7/receipt-book", {"month": MONTH01}),
    "marks": Route("/api/v7/marks", {"customer": DIGITS}),
    "report": Route("/api/v7/report/month", {"month": MONTH}),
    "report_missing": Route("/api/v7/report/month/missing", {"month": MONTH}),
    "conversations": Route("/api/v7/zalo/conversations", {"q": re.compile(r"[^\x00-\x1f&#]{1,100}")}),
    "inbox": Route("/api/v7/inbox"),
    "doi_chieu": Route("/api/v7/sheet/doi-chieu", {"customer": DIGITS}, admin=True),
    "activity": Route("/api/v7/activity", {"day": DAY}, admin=True),
    "machine": Route("/api/v7/machine/now", admin=True),
    "booking": Route("/api/v7/machine/booking", admin=True),
    "doixe": Route("/api/v7/doixe", {"thang": MONTH01}, admin=True),
    "doixe_so": Route("/api/v7/doixe/so", {"loai": re.compile(r"nguoi|xe"), "id": DIGITS, "thang": MONTH01}, admin=True),
    "doixe_bang_ke": Route("/api/v7/doixe/bang-ke", {"thang": MONTH01}, admin=True),
    "cash_chat": Route("/api/v7/cash-chat", {"from": DAY, "to": DAY}, admin=True),
    "nhat_ky": Route("/api/v7/nhat-ky", admin=True),
}
class _InboxCache:
    """Kết quả /inbox gần nhất, dùng chung giữa các câu hỏi trong `INBOX_TTL` giây."""

    at = 0
    data: object = None


def reset_cache() -> None:
    _InboxCache.at, _InboxCache.data = 0, None


class ToolError(ValueError):
    """Tham số sai hay không có dữ liệu: `str(error)` là mã ngắn, trả về model như kết quả lỗi."""


@dataclass
class Context:
    api: WebApi
    user: User
    now: float = field(default_factory=time.time)
    link_base: str = ""
    memo: dict[tuple, object] = field(default_factory=dict)

    def get(self, key: str, **params: str) -> object:
        cache_key = (key, tuple(sorted(params.items())))
        if cache_key not in self.memo:
            if key == "inbox" and _InboxCache.data is not None and self.now - _InboxCache.at < INBOX_TTL:
                self.memo[cache_key] = _InboxCache.data
            else:
                self.memo[cache_key] = self.api.get(ROUTES[key], params, login=self.user.login, role=self.user.role)
                if key == "inbox":
                    _InboxCache.at, _InboxCache.data = int(self.now), self.memo[cache_key]
        return self.memo[cache_key]

    def link(self, path: str) -> str:
        return f"{self.link_base}{path}"

    def stamp(self, page: str, path: str | None, data: object = None) -> dict:
        out = {"trang": page, "link": self.link(path) if path else None,
               "du_lieu_luc": dt.datetime.fromtimestamp(self.now, VN).isoformat(timespec="minutes")}
        if isinstance(data, dict) and isinstance(data.get("as_of"), str):
            out["as_of"] = data["as_of"]
        return out


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: dict[str, dict]
    required: tuple[str, ...]
    run: Callable[[Context, dict], dict]
    admin: bool = False

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description,
                "input_schema": {"type": "object", "properties": self.params, "required": list(self.required), "additionalProperties": False}}


def fold(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt, gộp khoảng trắng: để tìm tên khách không phân biệt dấu."""
    plain = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return " ".join("".join(ch for ch in plain if unicodedata.category(ch) != "Mn").split())


def compact(node: object, rows: int = MAX_ROWS) -> object:
    """Bỏ trường chữ tự do (DROP), giữ số, ngày, mã, tiền; danh sách dài cắt ở `rows` phần tử kèm số đếm."""
    if isinstance(node, dict):
        return {key: compact(value, rows) for key, value in node.items() if key not in DROP}
    if isinstance(node, list):
        kept = [compact(item, rows) for item in node[:rows]]
        return kept if len(node) <= rows else [*kept, {"con_lai": len(node) - rows}]
    return node


def fit(result: dict, limit: int = MAX_CHARS) -> dict:
    """Cắt đôi danh sách dài nhất tới khi kết quả dưới `limit` ký tự JSON; có cắt thì đặt `da_cat`."""
    def size(value: object) -> int:
        return len(json.dumps(value, ensure_ascii=False))

    def lists(node: object, path: tuple = ()) -> list[tuple[int, tuple]]:
        found: list[tuple[int, tuple]] = []
        if isinstance(node, dict):
            for key, value in node.items():
                found += lists(value, (*path, key))
        elif isinstance(node, list):
            found.append((size(node), path))
            for index, value in enumerate(node):
                found += lists(value, (*path, index))
        return found

    while size(result) > limit:
        candidates = [item for item in lists(result) if item[1]]
        if not candidates:
            break
        _size, path = max(candidates, key=lambda item: item[0])
        parent = result
        for part in path[:-1]:
            parent = parent[part]
        items = parent[path[-1]]
        if len(items) <= 1:
            break
        parent[path[-1]] = items[: max(len(items) // 2, 1)]
        result["da_cat"] = True
    return result


def _customer_id(args: dict) -> int:
    value = args.get("khach_id")
    if not isinstance(value, int) or isinstance(value, bool) or not 0 < value < 10**9:
        raise ToolError("khach_id_sai")
    return value


def _pattern(args: dict, key: str, pattern: re.Pattern, *, required: bool = False) -> str | None:
    value = args.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ToolError(f"{key}_sai")
    return value


def _vn_today(ctx: Context) -> dt.date:
    return dt.datetime.fromtimestamp(ctx.now, VN).date()


def _names(ctx: Context) -> dict[int, dict]:
    data = ctx.get("customers")
    rows = data.get("customers", []) if isinstance(data, dict) else []
    return {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), int)}


def _name(ctx: Context, customer: int) -> str | None:
    row = _names(ctx).get(customer)
    return (row.get("display_name") or row.get("name")) if row else None


def reconcile(ctx: Context, customer: int) -> dict:
    """Trạng thái khớp Sheet của một khách theo lượt đối soát gần nhất (/inbox). "Cũ": quá 14 giờ, hoặc quá 3 giờ trong
    10:00–22:00 giờ VN (luật của máy canh). Không đọc được thì `khong_ro`, không đoán."""
    try:
        data = ctx.get("inbox")
    except ApiError:
        return {"trang_thai": "khong_ro"}
    block = data.get("reconcile") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return {"trang_thai": "khong_ro"}
    checked = block.get("checked_at")
    out: dict[str, object] = {"luc": checked}
    try:
        at = dt.datetime.fromisoformat(checked)
        age_hours = (ctx.now - at.timestamp()) / 3600
        hour = dt.datetime.fromtimestamp(ctx.now, VN).hour
        out["cu"] = age_hours > 14 or (10 <= hour < 22 and age_hours > 3)
    except (TypeError, ValueError):
        out["cu"] = True
    if customer in (block.get("matched_ids") or []):
        return {"trang_thai": "khop", **out}
    for row in block.get("customers") or []:
        if isinstance(row, dict) and row.get("customer_id") == customer:
            return {"trang_thai": str(row.get("status", "")).lower() or "khong_ro", "ly_do": row.get("reason"),
                    "lech_vnd": row.get("difference_vnd"), "sheet_vnd": row.get("sheet_total_vnd"), "web_vnd": row.get("web_total_vnd"), **out}
    return {"trang_thai": "chua_doi_soat", **out}


def _book(ctx: Context, customer: int, page: str, path: str, data: object) -> dict:
    return {**ctx.stamp(page, path, data), "khach_id": customer, "ten": _name(ctx, customer), "doi_soat": reconcile(ctx, customer)}


# ---- Công cụ người dùng thường (sáu trang của QUYEN-01) ----

def tim_khach(ctx: Context, args: dict) -> dict:
    query = args.get("ten")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100:
        raise ToolError("ten_sai")
    needle = fold(query)
    found = []
    for row in _names(ctx).values():
        names = [row.get("name"), row.get("display_name"), *(row.get("aliases") or [])]
        if any(isinstance(name, str) and needle in fold(name) for name in names):
            found.append({"khach_id": row["id"], "ten": row.get("display_name") or row.get("name"), "mat_hang": row.get("commodity"),
                          "van_chuyen": row.get("transport_mode"), "trang_thai": row.get("status")})
    found.sort(key=lambda item: (fold(item["ten"] or "") != needle, item["khach_id"]))
    return {**ctx.stamp("Tìm khách", None), "so_ket_qua": len(found), "khach": found[:10],
            **({"goi_y": "nhiều sổ khớp: hỏi lại người dùng muốn sổ nào"} if len(found) > 1 else {})}


def tong_quan(ctx: Context, args: dict) -> dict:
    board, debt = ctx.get("dashboard"), ctx.get("debt")
    summary = debt.get("summary", {}) if isinstance(debt, dict) else {}
    return {**ctx.stamp("Tổng quan", "/dashboard-v7.html", debt),
            "tong_no_vnd": (board.get("receivable") or {}).get("total_vnd"), "so_khach_no": (board.get("receivable") or {}).get("customers"),
            "qua_han_vnd": summary.get("overdue_vnd"), "qua_han_lau_vnd": summary.get("long_overdue_vnd"),
            "so_khach_qua_han": summary.get("overdue_customers"), "theo_han": compact(debt.get("due_tiers")),
            "khach_no_nhieu_nhat": compact(board.get("top_debtors"), 10),
            "thu_thang_nay_theo_thang_sheet_vnd": (debt.get("this_month") or {}).get("received_vnd"),
            "hom_nay": compact(board.get("today")), "viec_cho": compact(board.get("todo"))}


def no_khach(ctx: Context, args: dict) -> dict:
    customer = _customer_id(args)
    debt = ctx.get("debt")
    row = next((r for r in debt.get("customers", []) if isinstance(r, dict) and r.get("customer_id") == customer), None)
    out = _book(ctx, customer, "Sổ khách", f"/so-khach-v7-live.html?customer={customer}", debt)
    if row is None:
        ledger = ctx.get("ledger", customer=str(customer))
        return {**out, "no_vnd": ledger.get("total_outstanding_vnd"), "ghi_chu_bot": "khách không có trong danh sách đang nợ của Tổng quan"}
    return {**out, "no_vnd": row.get("outstanding_vnd"), "qua_han_vnd": row.get("overdue_vnd"), "theo_han_vnd": row.get("tiers_vnd"),
            "thang_no_cu_nhat": row.get("oldest_open_month"), "tra_lan_cuoi": row.get("last_receipt_date"),
            "tra_lan_cuoi_chinh_xac": row.get("last_receipt_exact"), "so_ngay_tu_lan_tra": row.get("pay_days"),
            "chuyen_gan_nhat": row.get("last_trip_date"), "so_ngay_tu_chuyen": row.get("trip_days"), "muc": row.get("risk"),
            "theo_thang": compact(row.get("months"), 24)}


def no_theo_thang(ctx: Context, args: dict) -> dict:
    customer = _customer_id(args)
    month = _pattern(args, "thang", MONTH)
    if month:
        data = ctx.get("detail", customer=str(customer), month=f"{month}-01")
        return {**_book(ctx, customer, "Công nợ theo tháng", f"/so-khach-v7-live.html?customer={customer}&month={month}", data),
                "thang": month, **compact({key: data.get(key) for key in ("outstanding_vnd", "charges_vnd", "received_vnd",
                                                                            "allocated_vnd", "credit_applied_vnd", "receipts", "trips")})}
    year = str(_vn_today(ctx).year)
    data = ctx.get("matrix", year=year)
    row = next((r for r in data.get("customers", []) if isinstance(r, dict) and r.get("customer_id") == customer), None)
    return {**_book(ctx, customer, "Công nợ theo tháng", f"/cong-no-theo-thang.html?khach={customer}", data), "nam": year,
            "theo_thang_vnd": (row or {}).get("months"), "tong_nam_vnd": (row or {}).get("total_year_vnd"),
            "tong_moi_nam_vnd": (row or {}).get("total_all_vnd"), "thang_no_cu_nhat": (row or {}).get("oldest_open_month")}


def _in_month(row: dict, month: str) -> bool:
    return any(isinstance(value, str) and value.startswith(month) for key, value in row.items() if "date" in key or "month" in key)


def so_khach_thang(ctx: Context, args: dict) -> dict:
    customer = _customer_id(args)
    month = _pattern(args, "thang", MONTH, required=True)
    data = ctx.get("ledger", customer=str(customer))

    def pick(key: str) -> list[dict]:
        return [row for row in data.get(key, []) if isinstance(row, dict) and _in_month(row, month)]

    summary = next((row for row in data.get("months", []) if isinstance(row, dict) and str(row.get("month", "")).startswith(month)), None)
    return {**_book(ctx, customer, "Sổ khách", f"/so-khach-v7-live.html?customer={customer}&month={month}", data), "thang": month,
            "tong_no_vnd": data.get("total_outstanding_vnd"), "thang_nay": compact(summary), "chuyen": compact(pick("trips")),
            "phieu_thu": compact(pick("receipts")), "dieu_chinh": compact(pick("adjustments"))}


def lich_su_so(ctx: Context, args: dict) -> dict:
    customer = _customer_id(args)
    today = _vn_today(ctx)
    start = _pattern(args, "tu_ngay", DAY) or (today - dt.timedelta(days=7)).isoformat()
    end = _pattern(args, "den_ngay", DAY) or today.isoformat()
    data = ctx.get("events", customer=str(customer))
    rows = [row for row in data.get("events", []) if isinstance(row, dict) and start <= str(row.get("at", ""))[:10] <= end]
    rows.sort(key=lambda row: str(row.get("at", "")), reverse=True)
    return {**_book(ctx, customer, "Sổ khách: Lịch sử", f"/so-khach-v7-live.html?customer={customer}", data), "tu_ngay": start,
            "den_ngay": end, "so_thao_tac": len(rows), "thao_tac": compact(rows, 50)}


def bang_gia(ctx: Context, args: dict) -> dict:
    customer = _customer_id(args)
    table, status = ctx.get("price_table", customer=str(customer)), ctx.get("price_status", customer=str(customer))
    differs = [row for row in status.get("trips", []) if isinstance(row, dict) and row.get("differs")]
    return {**_book(ctx, customer, "Sổ khách: Bảng giá", f"/so-khach-v7-live.html?customer={customer}", status),
            "co_bang_gia": status.get("has_table"), "bang_gia": compact((table.get("price_table") or {}).get("periods")),
            "chuyen_khac_bang_gia": compact(differs), "so_chuyen_san_sang": status.get("ready_count"),
            "tien_san_sang_vnd": status.get("ready_total_vnd"), "so_chuyen_can_ap_lai": status.get("reapply_count")}


def bang_thu(ctx: Context, args: dict) -> dict:
    month = _pattern(args, "thang", MONTH) or _vn_today(ctx).strftime("%Y-%m")
    day = _pattern(args, "ngay", DAY)
    customer = args.get("khach_id")
    if customer is not None:
        customer = _customer_id(args)
    data = ctx.get("receipt_book", month=f"{month}-01")
    days = [row for row in data.get("days", []) if isinstance(row, dict)]
    out = {**ctx.stamp("Bảng thu", f"/bang-thu.html?month={month}" + (f"&ngay={day}" if day else ""), data), "thang": month,
           "tong_thang": compact(data.get("summary")), "ghi_chu_bot": "Bảng thu tính theo ngày tiền về, không theo tháng của Sheet"}
    if day:
        hit = next((row for row in days if row.get("date") == day), {"date": day, "rows": []})
        out["ngay"] = compact(hit)
    elif customer is not None:
        out["khach_id"] = customer
        out["phieu_cua_khach"] = compact([row for d in days for row in d.get("rows", []) if isinstance(row, dict) and row.get("customer_id") == customer])
    else:
        out["theo_ngay"] = [{"date": d.get("date"), "total_vnd": d.get("total_vnd"), "so_phieu": len(d.get("rows", []))} for d in days]
    return out


def hua_tra(ctx: Context, args: dict) -> dict:
    customer = _customer_id(args)
    data = ctx.get("marks", customer=str(customer))
    return {**_book(ctx, customer, "Sổ khách: Tình hình", f"/so-khach-v7-live.html?customer={customer}&the=tinh-hinh", data),
            "hua_va_bao_chuyen": compact(data.get("marks"))}


def bao_cao_thang(ctx: Context, args: dict) -> dict:
    month = _pattern(args, "thang", MONTH) or _vn_today(ctx).strftime("%Y-%m")
    data = ctx.get("report", month=month)
    customers = [{key: value for key, value in row.items() if key != "rows"} for row in data.get("customers", []) if isinstance(row, dict)]
    out = {**ctx.stamp("Báo cáo tháng", f"/bao-cao-thang.html?month={month}", data), "thang": month, "trang_thai": data.get("state"),
           "booking_luc": data.get("checked_at"), "tong": compact(data.get("totals")), "theo_khach": compact(customers)}
    if args.get("thieu") is True:
        out["chuyen_thieu"] = compact(ctx.get("report_missing", month=month).get("rows"))
    return out


def lan_cuoi_noi_chuyen(ctx: Context, args: dict) -> dict:
    query = args.get("ten")
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100 or re.search(r"[\x00-\x1f&#]", query):
        raise ToolError("ten_sai")
    data = ctx.get("conversations", q=query.strip())
    rows = []
    for row in data.get("conversations", [])[:10]:
        if not isinstance(row, dict):
            continue
        when = {key: dt.datetime.fromtimestamp(row[key] / 1000, VN).isoformat(timespec="minutes")
                for key in ("last_message_at", "last_own_message_at") if isinstance(row.get(key), int)}
        rows.append({"cuoc_tro_chuyen": row.get("display_name"), "la_nhom": row.get("is_group"), "so_tin": row.get("message_count"), **when})
    return {**ctx.stamp("Chat Zalo", f"/zalo-chat.html?q={urllib.parse.quote(query.strip())}"), "so_ket_qua": data.get("total"), "cuoc_tro_chuyen": rows,
            "ghi_chu_bot": "chỉ giờ và số tin; bot không đọc chữ tin chat"}


# ---- Công cụ admin ----

def doi_soat(ctx: Context, args: dict) -> dict:
    data = ctx.get("inbox")
    block = data.get("reconcile") if isinstance(data, dict) and isinstance(data.get("reconcile"), dict) else {}
    out = {**ctx.stamp("Việc cần làm: đối chiếu Sheet", "/viec-can-lam.html"), "doi_soat_luc": block.get("checked_at"),
           "dem": compact(block.get("counts")), "loi_luot_gan_nhat": bool(block.get("last_error")),
           "khach_lech": compact([{key: row.get(key) for key in ("customer_id", "status", "reason", "sheet_total_vnd", "web_total_vnd", "difference_vnd")}
                                  for row in block.get("customers") or [] if isinstance(row, dict)])}
    if args.get("khach_id") is not None:
        customer = _customer_id(args)
        detail = ctx.get("doi_chieu", customer=str(customer))
        out["khach"] = {"khach_id": customer, "ten": _name(ctx, customer),
                        **compact({key: detail.get(key) for key in ("web_vnd", "sheet_total_vnd", "checked_at", "reason", "sheet_editing", "web_ahead_vnd")}),
                        "nhom_lech": [{key: g.get(key) for key in ("kind", "month", "count", "delta_vnd")} for g in detail.get("groups", []) if isinstance(g, dict)]}
    return out


def viec_da_lam(ctx: Context, args: dict) -> dict:
    day = _pattern(args, "ngay", DAY)
    data = ctx.get("activity", **({"day": day} if day else {}))
    events = [row for row in data.get("events", []) if isinstance(row, dict)]
    kinds: dict[str, int] = {}
    people: dict[str, int] = {}
    for row in events:
        kinds[str(row.get("kind"))] = kinds.get(str(row.get("kind")), 0) + 1
        people[str(row.get("actor_name") or "máy")] = people.get(str(row.get("actor_name") or "máy"), 0) + 1
    return {**ctx.stamp("Đã làm", None), "ngay": data.get("day"), "tong": data.get("total"), "theo_loai": kinds, "theo_nguoi": people,
            "thao_tac": compact([{key: row.get(key) for key in ("customer_id", "customer", "kind", "actor_name", "at")} for row in events])}


def may_chay(ctx: Context, args: dict) -> dict:
    now, booking = ctx.get("machine"), ctx.get("booking")
    return {**ctx.stamp("Máy chạy", "/may-chay.html"), "luot_doi_soat": compact(now.get("run")), "viec": compact(now.get("jobs")),
            "may_zalo": compact(now.get("zalo")),
            "kiem_booking": {key: booking.get(key) for key in ("state", "checked_at", "counts")}}


def doi_xe(ctx: Context, args: dict) -> dict:
    month = _pattern(args, "thang", MONTH) or _vn_today(ctx).strftime("%Y-%m")
    kind = _pattern(args, "loai", re.compile(r"nguoi|xe"))
    path = f"/doi-xe.html?thang={month}"
    if kind:
        ident = args.get("id")
        if not isinstance(ident, int) or isinstance(ident, bool) or not 0 < ident < 10**9:
            raise ToolError("id_sai")
        data = ctx.get("doixe_so", loai=kind, id=str(ident), thang=f"{month}-01")
        return {**ctx.stamp("Đội xe", f"{path}&{kind}={ident}"), "thang": month, **compact({k: data.get(k) for k in ("the", "ung", "dot", "chang")})}
    data, bang_ke = ctx.get("doixe", thang=f"{month}-01"), ctx.get("doixe_bang_ke", thang=f"{month}-01")
    return {**ctx.stamp("Đội xe", path), "thang": month, "tai_xe": compact(data.get("nguoi")), "xe": compact(data.get("xe")),
            "cong_no_bang_ke_vnd": bang_ke.get("cong_no_vnd")}


def thu_chi(ctx: Context, args: dict) -> dict:
    start, end = _pattern(args, "tu_ngay", DAY), _pattern(args, "den_ngay", DAY)
    data = ctx.get("cash_chat", **{k: v for k, v in (("from", start), ("to", end)) if v})
    totals = data.get("totals") or {}
    items = [{"huong": row.get("direction"), "so_tien_vnd": str(row["amount_vnd"]) if isinstance(row.get("amount_vnd"), int) else None,
              "trang_thai": row.get("status"), "doi_tuong": (row.get("target") or {}).get("label"), "ngay": row.get("day")}
             for row in data.get("items", []) if isinstance(row, dict)]
    return {**ctx.stamp("Thu chi", "/thu-chi.html"), "tu_ngay": data.get("from"), "den_ngay": data.get("to"),
            "tong": {key: str(value) for key, value in totals.items() if isinstance(value, int) and not isinstance(value, bool)},
            "dem": compact(data.get("counts")), "khoan": compact(items), "ghi_chu_bot": "không có chữ gốc tin chat hay ảnh"}


def nhat_ky_web(ctx: Context, args: dict) -> dict:
    data = ctx.get("nhat_ky")
    days = data.get("days") if isinstance(data.get("days"), dict) else {}
    recent = sorted(days.items(), reverse=True)[:7]
    return {**ctx.stamp("Nhật ký công việc", "/nhat-ky-cong-viec.html"),
            "ngay": [{"ngay": day, "so_thay_doi": (info or {}).get("changes"), "tom_tat": (info or {}).get("headline")} for day, info in recent]}


ID_PARAM = {"khach_id": {"type": "integer", "description": "mã sổ khách (lấy bằng tim_khach)"}}
MONTH_PARAM = {"type": "string", "description": "tháng YYYY-MM"}
DAY_PARAM = {"type": "string", "description": "ngày YYYY-MM-DD"}
TOOLS: tuple[Tool, ...] = (
    Tool("tim_khach", "Tìm sổ khách theo tên (không cần dấu). Dùng trước mọi công cụ cần khach_id. Nhiều sổ khớp thì hỏi lại người dùng.",
         {"ten": {"type": "string"}}, ("ten",), tim_khach),
    Tool("tong_quan", "Tổng nợ mọi khách, nợ theo hạn trả, quá hạn, khách nợ nhiều nhất, việc chờ, hôm nay (trang Tổng quan).", {}, (), tong_quan),
    Tool("no_khach", "Một khách còn nợ bao nhiêu, quá hạn bao nhiêu, trả lần cuối khi nào, nợ từng tháng, kèm trạng thái khớp Sheet.",
         ID_PARAM, ("khach_id",), no_khach),
    Tool("no_theo_thang", "Nợ của một khách theo tháng trong năm nay; có `thang` thì chi tiết tháng đó (phát sinh, đã thu, chuyến, phiếu).",
         {**ID_PARAM, "thang": MONTH_PARAM}, ("khach_id",), no_theo_thang),
    Tool("so_khach_thang", "Chuyến, phiếu thu, điều chỉnh của một khách trong một tháng (trang Sổ khách).",
         {**ID_PARAM, "thang": MONTH_PARAM}, ("khach_id", "thang"), so_khach_thang),
    Tool("lich_su_so", "Ai sửa gì trong sổ một khách, mặc định 7 ngày gần nhất, tối đa 50 thao tác.",
         {**ID_PARAM, "tu_ngay": DAY_PARAM, "den_ngay": DAY_PARAM}, ("khach_id",), lich_su_so),
    Tool("bang_gia", "Bảng giá của một khách và các chuyến khác bảng giá.", ID_PARAM, ("khach_id",), bang_gia),
    Tool("bang_thu", "Tiền thu theo ngày tiền về: tổng tháng, một ngày, hoặc phiếu của một khách trong tháng (trang Bảng thu).",
         {"thang": MONTH_PARAM, "ngay": DAY_PARAM, **ID_PARAM}, (), bang_thu),
    Tool("hua_tra", "Khách hứa trả khi nào, đã báo chuyển chưa, hứa có giữ không.", ID_PARAM, ("khach_id",), hua_tra),
    Tool("bao_cao_thang", "Số chuyến theo booking, Sheet, web của một tháng; `thieu` = true để kèm danh sách chuyến thiếu (chậm hơn).",
         {"thang": MONTH_PARAM, "thieu": {"type": "boolean"}}, (), bao_cao_thang),
    Tool("lan_cuoi_noi_chuyen", "Lần cuối nhắn với khách trên Zalo (chỉ giờ và số tin, không có chữ tin).",
         {"ten": {"type": "string"}}, ("ten",), lan_cuoi_noi_chuyen),
    Tool("doi_soat", "Web có khớp Sheet không, khách nào lệch và vì sao; có khach_id thì chi tiết lệch của khách đó.",
         ID_PARAM, (), doi_soat, admin=True),
    Tool("viec_da_lam", "Máy và người đã ghi gì trong một ngày (mặc định hôm nay).", {"ngay": DAY_PARAM}, (), viec_da_lam, admin=True),
    Tool("may_chay", "Máy có chạy không: lượt đối soát, các việc định kỳ, máy Zalo, kiểm booking.", {}, (), may_chay, admin=True),
    Tool("doi_xe", "Đội xe trong tháng: tài xế còn ứng, xe còn phí; có `loai` (nguoi|xe) và `id` thì sổ của người hay xe đó.",
         {"thang": MONTH_PARAM, "loai": {"type": "string", "enum": ["nguoi", "xe"]}, "id": {"type": "integer"}}, (), doi_xe, admin=True),
    Tool("thu_chi", "Khoản thu, chi, ứng khách báo qua Zalo và trạng thái đối chiếu với sổ (không có chữ tin hay ảnh).",
         {"tu_ngay": DAY_PARAM, "den_ngay": DAY_PARAM}, (), thu_chi, admin=True),
    Tool("nhat_ky_web", "Web mới thêm gì trong 7 ngày gần nhất.", {}, (), nhat_ky_web, admin=True),
)
BY_NAME = {tool.name: tool for tool in TOOLS}


def for_role(role: str) -> list[Tool]:
    return [tool for tool in TOOLS if role == "admin" or not tool.admin]


def run(ctx: Context, name: str, args: object) -> tuple[dict, bool]:
    """Chạy một công cụ → (kết quả, có phải lỗi). Lỗi là mã ngắn để model sửa tham số hay báo không tra được."""
    tool = BY_NAME.get(name)
    if tool is None or (tool.admin and ctx.user.role != "admin"):
        return {"loi": "khong_co_cong_cu_nay"}, True
    if not isinstance(args, dict):
        return {"loi": "tham_so_sai"}, True
    try:
        return fit(tool.run(ctx, args)), False
    except ToolError as error:
        return {"loi": str(error)}, True
    except ApiError as error:
        return {"loi": f"api_{error.code}"}, True
    except (KeyError, TypeError, AttributeError, ValueError):
        return {"loi": "du_lieu_api_la"}, True
