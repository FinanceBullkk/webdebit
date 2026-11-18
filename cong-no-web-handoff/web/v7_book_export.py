"""Xuất cả sổ web ra bảng tính, tự kiểm (XUAT-SO-01, specs/v7-xuat-ca-so.md). Chỉ đọc.

`export()` đọc mọi sổ trong một giao dịch chỉ đọc (`run_snapshot` của adapter), dựng tab KIỂM, TỔNG, THÁNG, CHUYẾN, PHIẾU THU,
PHÂN BỔ THU, ĐIỀU CHỈNH, ghi xlsx trong bộ nhớ, đọc lại chính byte đó rồi tự kiểm. Lệch thì vẫn trả file (đường lui có số còn hơn
không) nhưng tên file có đuôi -CO-LECH, tab KIỂM ghi chỗ lệch và header có `ok:false`: không bao giờ xuất im lặng.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
from collections.abc import Callable
from dataclasses import dataclass, field

import v7_book_export_check as check
import v7_book_export_rows as rows
from v7_api_validate import ApiError
from v7_xlsx_writer import Sheet, Styled, plain_rows, read_workbook, write_workbook

HEAD_READS = ("get_dashboard", "get_dashboard_debt", "list_customers", "get_fee_types")
GUIDE = (
    "Tab TỔNG: mỗi sổ một dòng; Nợ còn lại là số web đang ghi cho khách.",
    "Tab THÁNG: Còn nợ cuối tháng là số cộng dồn tới cuối tháng, như dòng Tổng tháng trên web; Nợ còn lại của tháng là phần "
    "nợ của tháng đó còn lại sau khi trừ các khoản thu theo nợ cũ trước.",
    "Tab PHIẾU THU và PHÂN BỔ THU: mỗi phiếu và từng tháng phiếu trừ vào; phiếu đã hủy không còn dòng chia.",
    "Ô trống là chưa có số (ví dụ chuyến chưa giá), không phải 0.",
    "Mã sổ, mã dòng, mã phiếu giữ như trên web để đối chiếu; bật bộ lọc ở hàng tiêu đề để xem riêng một khách.",
    "File có tên khách và số tiền: cất ở thư mục dự phòng, không gửi ra ngoài.",
)


@dataclass
class Export:
    data: bytes
    filename: str
    ok: bool
    books: int
    problems: list[dict] = field(default_factory=list)

    def header(self) -> str:
        """Giá trị header `X-Xuat-So`: chữ ASCII, chỉ mã, số đếm và mã sổ."""
        return json.dumps({"ok": self.ok, "books": self.books, "problems": self.problems}, ensure_ascii=True,
                          separators=(",", ":"))


class _ListChanged(Exception):
    def __init__(self, ids: list[int]):
        super().__init__("book list changed")
        self.ids = ids


def _ids(listing: dict) -> list[int]:
    """Mã sổ theo thứ tự danh sách, bỏ trùng (một sổ có nhiều mốc nạp thì `list_customers` có thể trả hai dòng)."""
    return list(dict.fromkeys(row["id"] for row in listing.get("customers") or []))


def export(db, actor: str, now: dt.datetime, *, names: Callable[[dict], dict] = lambda listing: listing,
           prefix: str = "so-web") -> Export:
    """`now`: giờ VN của lượt xuất (tên file, tab KIỂM). `names` gắn tên hiển thị như GET /api/v7/customers."""
    ids = _ids(db.run("list_customers", {}, actor, read_only=True))
    for _ in range(2):   # vừa tạo hay xóa sổ giữa lần lấy danh sách và giao dịch: đọc lại cả lượt một lần
        try:
            return _build(db, actor, ids, now, names, prefix)
        except _ListChanged as exc:
            ids = exc.ids
    raise ApiError(503, "DB_UNAVAILABLE", "Danh sách sổ đổi trong lúc xuất. Thử lại sau ít phút.")


def _build(db, actor, ids, now, names, prefix) -> Export:
    calls = [(name, {}) for name in HEAD_READS] + [("get_ledger_export", {"customer_id": book}) for book in ids]
    tabs = {tab: [] for tab in rows.TABS}
    expected, totals, found = {}, [], check.Findings()
    with contextlib.closing(db.run_snapshot(calls, actor)) as results:
        dashboard, debt, listing, fee_types = (next(results) for _ in HEAD_READS)
        customers = {row["id"]: row for row in names(listing).get("customers") or []}
        if sorted(customers) != sorted(ids):
            raise _ListChanged(_ids(listing))
        fee_names = {row["id"]: row.get("name") for row in fee_types.get("fee_types") or []}
        figures = check.overview_figures(dashboard, debt)
        for book in ids:
            ledger = next(results)
            customer = customers[book]
            tabs["TỔNG"].append(rows.summary_row(customer, ledger))
            for tab, lines in rows.book_rows(customer, ledger, fee_names).items():
                tabs[tab] += lines
            expected[book] = rows.expected(ledger)
            check.check_book(found, book, ledger, figures)
            if ledger.get("status") == "active":
                totals.append(rows.vnd(ledger.get("total_outstanding_vnd")))
        if next(results, None) is not None:   # đọc tới hết: lỗi psql ở cuối lượt (COMMIT, mã thoát) nổi lên ở đây
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
    check.check_totals(found, dashboard, debt, totals)
    sheets = [Sheet(tab, rows.COLUMNS[tab], tabs[tab]) for tab in rows.TABS]
    check.check_file(found, read_workbook(write_workbook(sheets)), sheets, expected)
    statuses = [row[3] for row in tabs["TỔNG"]]
    guide = _guide(found, now, actor, len(ids), statuses, dashboard, totals)
    data = write_workbook([guide, *sheets])
    back = read_workbook(data)   # lần ghi cuối thêm tab KIỂM; các tab dữ liệu phải ra y hệt lần đã kiểm
    if any(back.get(sheet.name) != plain_rows(sheet) for sheet in (guide, *sheets)):
        found.add("FILE_LECH", note="bản ghi cuối đọc lại khác bản đã kiểm")
    name = f"{prefix}-{now:%Y%m%d-%H%M}{'' if found.ok else '-CO-LECH'}.xlsx"
    return Export(data, name, found.ok, len(ids), found.problems())


def _guide(found, now, actor, books, statuses, dashboard, totals) -> Sheet:
    receivable, credit = dashboard.get("receivable") or {}, dashboard.get("credit") or {}
    active = statuses.count(rows.STATUS["active"])
    lines = [
        [Styled("BẢN XUẤT CẢ SỔ WEB", "title")],
        [Styled("Kết quả tự kiểm", "bold"), Styled("KHỚP", "good") if found.ok else Styled("CÓ LỆCH", "bad"),
         None if found.ok else "Xem các phép kiểm bên dưới; báo quản trị trước khi dùng file này."],
        ["Lúc xuất (giờ VN)", f"{now:%d/%m/%Y %H:%M}"],
        ["Người tải", rows.text(actor)],
        ["Số sổ", books, f"{active} sổ đang dùng, {books - active} sổ chưa có số dư đầu"],
        ["Còn phải thu (Tổng quan)", rows.vnd(receivable.get("total_vnd")), f"{receivable.get('customers')} khách còn nợ"],
        ["Khách trả thừa (Tổng quan)", rows.vnd(credit.get("total_vnd")), f"{credit.get('customers')} khách"],
        ["Tổng các sổ (nợ trừ dư)", sum(totals)],
        [],
        [Styled("Phép kiểm", "bold"), Styled("Kết quả", "bold"), Styled("Chi tiết", "bold")],
        *[[label, Styled(state, "good" if state == "ĐẠT" else "bad"), detail] for label, state, detail in found.lines()],
        [],
        [Styled("Cách đọc", "bold")],
        *[[line] for line in GUIDE],
    ]
    return Sheet("KIỂM", [("", "text", 46), ("", "auto", 20), ("", "text", 90)], lines, table=False)
