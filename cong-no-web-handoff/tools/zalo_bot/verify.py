"""Bộ kiểm số (ZALO-BOT-01 Phần 4): số trong câu trả lời phải lấy đúng từ kết quả công cụ của chính lượt đó.

1. **Điền chỗ trống.** Model không gõ số tiền mà viết `{t2.tong_no_vnd}` hay `{t1.rows.0.no_vnd}`: kết quả công cụ thứ 2, đường
   dẫn trong JSON (số là vị trí trong danh sách). Bot điền giá trị; trường tên `*_vnd` là tiền và được định dạng như web
   (`1.234.567 đ`). Chỗ trống trỏ tới trường không có thì bản nháp bị trả lại.
2. **Kiểm số gõ tay** trong bản đã điền (bỏ qua phần bot vừa điền):
   - số có dạng tiền (nhóm chấm, kèm `đ`/`đồng`/`VND`, hoặc kèm `nghìn`/`triệu`/`tỷ`) phải bằng một giá trị tiền có trong kết quả
     công cụ hoặc công cụ tính; số làm tròn ("khoảng 1,2 tỷ") phải đúng bằng một giá trị đó làm tròn theo đơn vị ghi và có chữ
     "khoảng" (hay "gần", "xấp xỉ", "hơn") ngay trước;
   - số trơn từ 4 chữ số trở lên (không phải năm, không nằm trong ngày) phải trùng một giá trị nào đó trong kết quả công cụ
     (tiền, số đếm hay mã), vì model có thể bỏ chữ `đ` khi chép số tiền.
   Ngày, tháng và số nhỏ (số chuyến, số khách) không kiểm ở đây; bộ câu hỏi mẫu đo phần đó.

Giới hạn (spec Phần 4): bộ kiểm chặn số không có nguồn, không bắt được số thật đặt sai chỗ khi model chọn sai trường.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

PLACEHOLDER = re.compile(r"\{t(\d{1,2})((?:\.[A-Za-z0-9_]{1,40}){1,6})\}")
UNITS = {"nghìn": 10**3, "ngàn": 10**3, "k": 10**3, "triệu": 10**6, "tr": 10**6, "tỷ": 10**9, "tỉ": 10**9}
APPROX = re.compile(r"(khoảng|gần|xấp xỉ|hơn|chừng|tầm|cỡ)\s*$", re.IGNORECASE)
# Ngày dd/mm/yyyy, dd/mm, mm/yyyy và giờ hh:mm: bỏ khỏi phần kiểm số.
DATE = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}/\d{4}\b|\b\d{1,2}:\d{2}\b|\b\d{4}-\d{2}-\d{2}\b")
SCALED = re.compile(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{1,3})?)\s*(nghìn|ngàn|triệu|tr|tỷ|tỉ|k)(?![\wÀ-ỹ])", re.IGNORECASE)
GROUPED = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+)(?![\d,]|\.\d)(\s*(?:đ|đồng|vnd)(?![\wÀ-ỹ]))?", re.IGNORECASE)
PLAIN = re.compile(r"(?<![\d.,])(\d{4,})(?![\d.,]\d)(\s*(?:đ|đồng|vnd)(?![\wÀ-ỹ]))?", re.IGNORECASE)
YEARS = range(2000, 2100)


class FillError(ValueError):
    """Chỗ trống trỏ tới trường không có. `str(error)` là chỗ trống đó, để trả lại model sửa."""


@dataclass(frozen=True)
class Problem:
    code: str          # unknown_amount | rounded_without_approx | rounded_mismatch | unknown_number
    text: str          # đoạn chữ có số bị bắt, để trả lại model


def format_vnd(value: int) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,}".replace(",", ".") + " đ"


def _lookup(result: object, path: list[str]) -> object:
    node = result
    for part in path:
        if isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise KeyError(part)
    return node


def _as_vnd(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,18}", value):
        return int(value)
    return None


def fill(draft: str, results: list[object]) -> tuple[str, list[tuple[int, int]]]:
    """Điền chỗ trống bằng giá trị trong kết quả công cụ (đánh số từ 1 theo thứ tự gọi). Trả chữ đã điền và các khoảng vừa điền."""
    out: list[str] = []
    spans: list[tuple[int, int]] = []
    last = 0
    length = 0
    for match in PLACEHOLDER.finditer(draft):
        index, path = int(match.group(1)), match.group(2).lstrip(".").split(".")
        if not 1 <= index <= len(results):
            raise FillError(match.group(0))
        try:
            value = _lookup(results[index - 1], path)
        except KeyError:
            raise FillError(match.group(0)) from None
        if isinstance(value, (dict, list)) or value is None:
            raise FillError(match.group(0))
        money = _as_vnd(value) if path[-1].endswith("_vnd") else None
        if path[-1].endswith("_vnd") and money is None:
            raise FillError(match.group(0))
        text = format_vnd(money) if money is not None else str(value)
        before = draft[last:match.start()]
        out.append(before)
        length += len(before)
        out.append(text)
        spans.append((length, length + len(text)))
        length += len(text)
        last = match.end()
    out.append(draft[last:])
    return "".join(out), spans


def collect_values(results: Iterable[object]) -> tuple[set[int], set[int]]:
    """(giá trị tiền, mọi số nguyên) có trong kết quả công cụ: tiền là trường `*_vnd`; số nguyên gồm cả số đếm, mã số."""
    money: set[int] = set()
    numbers: set[int] = set()

    def walk(node: object, key: str = "") -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                walk(child, str(child_key))
        elif isinstance(node, list):
            for child in node:
                walk(child, key)
        else:
            value = _as_vnd(node)
            if value is None and isinstance(node, str) and re.fullmatch(r"\d{4,18}", node.strip()):
                value = int(node.strip())
            if value is None:
                return
            numbers.add(abs(value))
            if key.endswith("_vnd"):
                money.add(abs(value))

    for result in results:
        walk(result)
    return money, numbers


def _masked(text: str, spans: list[tuple[int, int]]) -> str:
    """Thay phần bot vừa điền và các ngày, giờ bằng khoảng trắng cùng độ dài, để vị trí trong chữ không đổi."""
    chars = list(text)
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    masked = "".join(chars)
    return DATE.sub(lambda m: " " * len(m.group(0)), masked)


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def check(text: str, spans: list[tuple[int, int]], money: set[int], numbers: set[int]) -> list[Problem]:
    """Các số gõ tay không có nguồn trong `text` đã điền. Rỗng là qua."""
    masked = _masked(text, spans)
    problems: list[Problem] = []
    taken: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < b and a < end for a, b in taken)

    for match in SCALED.finditer(masked):
        number = _decimal(match.group(1))
        unit = UNITS[match.group(2).lower()]
        if number is None:
            continue
        taken.append(match.span())
        amount = number * unit
        if amount == amount.to_integral_value() and int(amount) in money:
            continue
        decimals = -number.as_tuple().exponent if number.as_tuple().exponent < 0 else 0
        step = Decimal(unit) / (Decimal(10) ** decimals)
        near = any(abs(Decimal(value) - amount) <= step / 2 for value in money)
        snippet = text[max(match.start() - 12, 0):match.end()].strip()
        if not near:
            problems.append(Problem("unknown_amount", snippet))
        elif not APPROX.search(masked[max(match.start() - 12, 0):match.start()]):
            problems.append(Problem("rounded_without_approx", snippet))
    for match in GROUPED.finditer(masked):
        if overlaps(*match.span()):
            continue
        taken.append(match.span())
        if int(match.group(1).replace(".", "")) not in money:
            problems.append(Problem("unknown_amount", text[match.start():match.end()].strip()))
    for match in PLAIN.finditer(masked):
        if overlaps(*match.span()):
            continue
        value = int(match.group(1))
        is_money = bool(match.group(2))
        if not is_money and value in YEARS:
            continue
        if (value not in money) if is_money else (value not in numbers):
            problems.append(Problem("unknown_amount" if is_money else "unknown_number", text[match.start():match.end()].strip()))
    return problems
