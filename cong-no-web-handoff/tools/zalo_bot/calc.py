"""Công cụ tính của bot (ZALO-BOT-01 Phần 3): cộng, trừ, tỉ lệ trên số nguyên VND, kết quả chính xác để model trích dẫn.

Chỉ nhận số tiền đã có trong kết quả công cụ của chính lượt đó (hoặc kết quả tính trước trong lượt), để công cụ tính không
thành chỗ "rửa" một số bịa qua bộ kiểm số.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal

OPS = ("cong", "tru", "ti_le")
MAX_VALUES = 50


class CalcError(ValueError):
    """Phép tính sai: `str(error)` là mã ngắn."""


def _vnd(value: object) -> int:
    if isinstance(value, bool):
        raise CalcError("bad_value")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d{1,18}", value):
        return int(value)
    raise CalcError("bad_value")


def calculate(op: str, values: list[object], allowed: set[int]) -> dict[str, str]:
    """`cong`: tổng; `tru`: số đầu trừ các số sau; `ti_le`: số đầu chiếm bao nhiêu phần trăm số sau (một chữ số thập phân).

    `allowed` là các giá trị tiền (trị tuyệt đối) có trong kết quả công cụ và phép tính trước của lượt."""
    if op not in OPS:
        raise CalcError("bad_op")
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_VALUES:
        raise CalcError("bad_values")
    numbers = [_vnd(value) for value in values]
    if any(abs(number) not in allowed for number in numbers):
        raise CalcError("value_not_from_tools")
    if op == "cong":
        return {"ket_qua_vnd": str(sum(numbers))}
    if op == "tru":
        return {"ket_qua_vnd": str(numbers[0] - sum(numbers[1:]))}
    if len(numbers) != 2 or numbers[1] == 0:
        raise CalcError("bad_values")
    percent = (Decimal(numbers[0]) * 100 / Decimal(numbers[1])).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return {"ti_le_phan_tram": str(percent).replace(".", ",")}
