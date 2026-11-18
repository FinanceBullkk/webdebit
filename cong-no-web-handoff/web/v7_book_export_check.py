"""Tự kiểm của bản xuất cả sổ (XUAT-SO-01, specs/v7-xuat-ca-so.md).

Sáu phép kiểm, mỗi phép một mã ASCII. Header `X-Xuat-So` chỉ mang mã, số đếm và mã sổ; chi tiết có số tiền chỉ nằm trong tab
KIỂM của file. Phép 1–4 chạy trên ảnh dữ liệu đã đọc; phép 5 trên file đọc lại từ chính byte sẽ gửi.
"""

from __future__ import annotations

from v7_book_export_rows import AMOUNT, COLUMNS, current_lines, money_text, vnd
from v7_xlsx_writer import Sheet, plain_rows

CHECKS = {
    "TONG_QUAN_PHAI_THU": "Tổng các sổ còn nợ bằng Còn phải thu trên Tổng quan",
    "TONG_QUAN_KHACH_DU": "Tổng các sổ khách dư bằng Khách trả thừa trên Tổng quan",
    "SO_LECH_TONG_QUAN": "Nợ còn lại từng sổ bằng số Tổng quan dùng cho sổ đó",
    "SO_LECH_THANG": "Cộng các tháng của sổ bằng nợ còn lại của sổ",
    "PHIEU_CHIA_LECH": "Mỗi phiếu thu chia đủ vào các tháng",
    "FILE_LECH": "File ghi ra đọc lại khớp từng sổ",
}
SHOW = 5        # số mã sổ tối đa trong header
LIST = 50       # số mã sổ tối đa trong một ô chi tiết của tab KIỂM


class Findings:
    def __init__(self):
        self.failed: dict[str, tuple[list[int], list[str]]] = {}

    def add(self, code: str, book: int | None = None, note: str | None = None) -> None:
        books, notes = self.failed.setdefault(code, ([], []))
        if book is not None and book not in books:
            books.append(book)
        if note and note not in notes:
            notes.append(note)

    @property
    def ok(self) -> bool:
        return not self.failed

    def problems(self) -> list[dict]:
        """Cho header: mã, số sổ lệch (1 khi lệch không theo sổ), tối đa SHOW mã sổ."""
        return [{"code": code, "count": len(self.failed[code][0]) or 1, "books": sorted(self.failed[code][0])[:SHOW]}
                for code in CHECKS if code in self.failed]

    def lines(self):
        """(phép kiểm, ĐẠT/LỆCH, chi tiết) cho tab KIỂM."""
        for code, label in CHECKS.items():
            if code not in self.failed:
                yield label, "ĐẠT", None
                continue
            books, notes = self.failed[code]
            ids = sorted(books)
            listed = f"{len(ids)} sổ: " + ", ".join(map(str, ids[:LIST])) + ("…" if len(ids) > LIST else "") if ids else ""
            yield label, "LỆCH", "; ".join([*notes, *([listed] if listed else [])])


def overview_figures(dashboard: dict, debt: dict) -> dict[int, int]:
    """Số Tổng quan dùng cho từng sổ: danh sách khách nợ, danh sách khách dư; sổ không có mặt là 0."""
    figures = {row["customer_id"]: vnd(row["outstanding_vnd"]) for row in debt.get("customers") or []}
    figures.update({row["customer_id"]: vnd(row["credit_vnd"]) for row in (dashboard.get("todo") or {}).get("credit") or []})
    return figures


def check_book(found: Findings, book: int, ledger: dict, figures: dict[int, int]) -> None:
    """Phép 2–4 cho một sổ có số dư đầu."""
    if ledger.get("status") != "active":
        return
    total = vnd(ledger.get("total_outstanding_vnd"))
    if figures.get(book, 0) != total:
        found.add("SO_LECH_TONG_QUAN", book)
    months = ledger.get("months") or []
    if (sum(vnd(m.get("outstanding_vnd")) or 0 for m in months) != total
            or (months and vnd(months[-1].get("end_of_month_vnd")) != total)):
        found.add("SO_LECH_THANG", book)
    for receipt in ledger.get("receipts") or []:
        lines = current_lines(receipt)
        if receipt.get("voided_on") is None:
            wrong = not lines or sum(vnd(line.get("amount_vnd")) or 0 for line in lines) != vnd(receipt.get("amount_vnd"))
        else:
            wrong = bool(lines)
        if wrong:
            found.add("PHIEU_CHIA_LECH", book)
            return


def check_totals(found: Findings, dashboard: dict, debt: dict, totals: list[int]) -> None:
    """Phép 1: tổng các sổ có số dư đầu so với con số Tổng quan hiển thị."""
    positive, negative = [t for t in totals if t > 0], [t for t in totals if t < 0]
    receivable, credit = dashboard.get("receivable") or {}, dashboard.get("credit") or {}
    if vnd(receivable.get("total_vnd")) != sum(positive) or receivable.get("customers") != len(positive):
        found.add("TONG_QUAN_PHAI_THU", note=f"Tổng quan {money_text(vnd(receivable.get('total_vnd')))} ở "
                                             f"{receivable.get('customers')} sổ, các sổ {money_text(sum(positive))} ở {len(positive)} sổ")
    if vnd(debt.get("receivable_vnd")) != sum(positive):
        found.add("TONG_QUAN_PHAI_THU", note=f"bảng hạn trả {money_text(vnd(debt.get('receivable_vnd')))}, "
                                             f"các sổ {money_text(sum(positive))}")
    if vnd(credit.get("total_vnd")) != sum(negative) or credit.get("customers") != len(negative):
        found.add("TONG_QUAN_KHACH_DU", note=f"Tổng quan {money_text(vnd(credit.get('total_vnd')))} ở "
                                             f"{credit.get('customers')} sổ, các sổ {money_text(sum(negative))} ở {len(negative)} sổ")


def _cell(row: list, index: int):
    return row[index] if index < len(row) else None


def aggregate(back: dict[str, list[list]]) -> dict[int, dict]:
    """Số đối chiếu từng sổ tính lại từ file đọc lại, cùng dạng `v7_book_export_rows.expected()`."""
    out: dict[int, dict] = {}

    def slot(book) -> dict:
        return out.setdefault(book, {"total": None, "THÁNG": [], **dict.fromkeys(AMOUNT, (0, 0))})

    def index(tab: str, title: str) -> int:
        return [name for name, _, _ in COLUMNS[tab]].index(title)

    for row in back.get("TỔNG", [])[1:]:
        slot(_cell(row, 0))["total"] = _cell(row, index("TỔNG", "Nợ còn lại"))
    for row in back.get("THÁNG", [])[1:]:
        slot(_cell(row, 0))["THÁNG"].append(tuple(_cell(row, i) for i in range(2, 8)))
    for tab, title in AMOUNT.items():
        at = index(tab, title)
        for row in back.get(tab, [])[1:]:
            count, total = slot(_cell(row, 0))[tab]
            value = _cell(row, at)
            slot(_cell(row, 0))[tab] = (count + 1, total + (value if isinstance(value, int) else 0))
    return out


def check_file(found: Findings, back: dict[str, list[list]], sheets: list[Sheet], expected: dict[int, dict]) -> None:
    """Phép 5: mọi ô đọc lại đúng như đã ghi, và từng sổ trong file khớp số đối chiếu lấy từ `get_ledger`."""
    for sheet in sheets:
        if back.get(sheet.name) != plain_rows(sheet):
            found.add("FILE_LECH", note=f"tab {sheet.name} đọc lại khác bản đã ghi")
    got = aggregate(back)
    for book, want in expected.items():
        have = got.get(book) or {}
        if any(have.get(key) != value for key, value in want.items()):
            found.add("FILE_LECH", book)
    for book in got.keys() - expected.keys():
        found.add("FILE_LECH", book if isinstance(book, int) else None, note="file có sổ không có trong ảnh dữ liệu")
