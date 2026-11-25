"""SO-TIEN P0-a lát 2: bộ đọc file sao kê theo mẫu → lô StatementLine v1 (specs/van-hanh-tai-chinh/F1-kien-truc-ky-thuat.md mục 5.1).

Mỗi mẫu có tên@phiên bản (khớp `statement_template` của tài khoản) và một hàm đọc byte → kỳ, số dư đầu/cuối, ngày cuối đã trọn
và các dòng. Lỗi cấu trúc file (thiếu dòng kỳ, ngày không đọc được, số dư sai dạng) là ParseError kèm số dòng của file; giá trị
dòng sai về nghiệp vụ (chiều, số tiền) vẫn chuyển xuống SQL để thành lỗi dòng như lát 1 (LINE_DIRECTION, LINE_AMOUNT). Thư viện
chuẩn, không chạy công thức hay macro.

Mẫu VCB thật chưa có: chờ file mẫu ở Discovery (QD-07). `demo-csv@1` chỉ dùng cho dữ liệu bịa (test, máy dev) và chỉ bật khi
WEBDEBIT_TIEN_DEMO=1; không đặt biến này trên hao.
"""

from __future__ import annotations

import csv
import io
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_ROWS = 20000
CSV_TYPE = "text/csv"
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
MINOR = re.compile(r"0|-?[1-9][0-9]{0,17}")
DEMO_HEADER = ["date", "ref", "description", "debit", "credit", "balance"]


class ParseError(ValueError):
    def __init__(self, message: str, line: int | None = None):
        super().__init__(message)
        self.message, self.line = message, line


@dataclass
class Parsed:
    period_from: str
    period_to: str
    last_day_complete: bool
    opening_minor: str | None
    closing_minor: str | None
    lines: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class Template:
    id: str
    label: str
    media_type: str
    extension: str
    parse: Callable[[bytes, str], Parsed]
    demo: bool = False


def _day(value: str, line: int) -> str:
    if not DATE.fullmatch(value):
        raise ParseError("Ngày phải viết dạng năm-tháng-ngày (YYYY-MM-DD).", line)
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ParseError("Ngày không có thật.", line) from None
    return value


def _minor(value: str, line: int, what: str) -> str:
    if not MINOR.fullmatch(value):
        raise ParseError(f"{what} phải là số nguyên, không dấu chấm, phẩy hay khoảng trắng.", line)
    return value


def parse_demo_csv(data: bytes, currency: str) -> Parsed:
    """Mẫu thử: CSV UTF-8. Trước tiêu đề là các dòng thông tin `#period,từ,đến,complete|partial` (bắt buộc), `#opening,số` và
    `#closing,số` (tùy chọn); rồi tiêu đề `date,ref,description,debit,credit,balance` và mỗi dòng một giao dịch (ghi nợ là tiền ra,
    ghi có là tiền vào, đơn vị nhỏ nhất của tiền tệ tài khoản)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("File phải là chữ UTF-8.") from None
    if "\x00" in text:   # PostgreSQL không lưu được NUL trong chữ (review lát 2, Thấp)
        raise ParseError("File có ký tự lạ (NUL); tải lại file từ ngân hàng.")
    period: tuple[str, str, bool] | None = None
    opening = closing = None
    header = False
    lines: list[dict] = []
    try:
        for row_no, row in enumerate(csv.reader(io.StringIO(text, newline="")), start=1):
            if not any(cell.strip() for cell in row):
                continue
            cells = [cell.strip() for cell in row]
            if not header and cells[0].startswith("#"):
                key = cells[0][1:]
                if key == "period" and len(cells) == 4 and period is None:
                    if cells[3] not in ("complete", "partial"):
                        raise ParseError("Dòng #period: ô cuối phải là complete (ngày cuối đã trọn) hoặc partial.", row_no)
                    period = (_day(cells[1], row_no), _day(cells[2], row_no), cells[3] == "complete")
                elif key == "opening" and len(cells) == 2 and opening is None:
                    opening = _minor(cells[1], row_no, "Số dư đầu")
                elif key == "closing" and len(cells) == 2 and closing is None:
                    closing = _minor(cells[1], row_no, "Số dư cuối")
                else:
                    raise ParseError("Dòng thông tin lạ hoặc lặp lại.", row_no)
                continue
            if not header:
                if cells != DEMO_HEADER:
                    raise ParseError("Thiếu dòng tiêu đề date,ref,description,debit,credit,balance.", row_no)
                header = True
                continue
            if len(cells) != 6:
                raise ParseError("Dòng giao dịch phải đủ 6 ô.", row_no)
            if len(lines) >= MAX_ROWS:
                raise ParseError("File quá 20000 dòng giao dịch; tải kỳ ngắn hơn.", row_no)
            day, ref, description, debit, credit, balance = cells
            if len(description) > 1000 or len(ref) > 100:
                raise ParseError("Nội dung hoặc mã giao dịch quá dài.", row_no)
            direction = "out" if debit and not credit else "in" if credit and not debit else None
            lines.append({
                "line_no": len(lines) + 1, "booking_date": _day(day, row_no), "direction": direction,
                "amount_minor": (debit or credit) if direction else None, "currency": currency,
                "description": description or None, "bank_ref": ref or None,
                "balance_after_minor": _minor(balance, row_no, "Số dư sau") if balance else None,
                "cells": dict(zip(DEMO_HEADER, row, strict=True)),
            })
    except csv.Error as exc:
        raise ParseError(f"File CSV hỏng: {exc}.") from None
    if period is None:
        raise ParseError("Thiếu dòng #period (kỳ của sao kê).")
    if not header:
        raise ParseError("Thiếu dòng tiêu đề date,ref,description,debit,credit,balance.")
    if period[0] > period[1]:
        raise ParseError("Ngày đầu kỳ sau ngày cuối kỳ.")
    return Parsed(period[0], period[1], period[2], opening, closing, lines)


TEMPLATES = {
    "demo-csv@1": Template("demo-csv@1", "Mẫu thử CSV (chỉ dữ liệu giả)", CSV_TYPE, ".csv", parse_demo_csv, demo=True),
}


def demo_enabled() -> bool:
    return os.environ.get("WEBDEBIT_TIEN_DEMO") == "1"


def available() -> list[Template]:
    """Mẫu dùng được lúc này: mẫu thử chỉ khi bật WEBDEBIT_TIEN_DEMO=1."""
    return [t for t in TEMPLATES.values() if not t.demo or demo_enabled()]


def get(template_id: object) -> Template | None:
    template = TEMPLATES.get(template_id) if isinstance(template_id, str) else None
    return template if template is not None and (not template.demo or demo_enabled()) else None
