"""Chuẩn hóa ở biên, một chỗ duy nhất (KIEM-TAB-01, K4, specs/v7-kiem-tab-truoc-khi-ghi.md).

Hai luật, mọi nơi đọc Sheet hoặc gửi giá trị chữ xuống SQL dùng chung:

- Chữ mô tả (hãng tàu, chủ hàng, nơi đi, nơi đến): cắt khoảng trắng hai đầu; chuỗi rỗng là NULL (`text_or_none`). Không bao giờ áp cho
  trường tiền: ô tiền trống là NULL, không phải 0, và chuỗi "0" vẫn là chữ "0".
- Mã container: một ô có đúng một mã theo mẫu 4 chữ + 7 số (ISO 6346) kèm chữ đi cùng ("MAUU5500001-mã chưa up") thì mã là phần ISO,
  phần còn lại là ghi chú (`split_container`). Ô có hai mã hoặc không có mã ISO thì giữ nguyên, không đoán.

SQL giữ cùng luật ở chỗ so trước–sau (`nullif(btrim(...),'')` trong `resolve_sheet_conflict` và `edit_trip_info`).
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

# Không nhận khúc giữa của chuỗi dài hơn ("FAKEU0000001" có năm chữ, "MAUU55000011" tám số): trước mã không có chữ hay số, sau mã không có số.
ISO_CONTAINER = re.compile(r"(?<![A-Z0-9])[A-Z]{4}[0-9]{7}(?![0-9])")
NUMBER_CELL = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:E\+?[0-9]{1,2})?")


def text_or_none(value: Any) -> str | None:
    """Chữ đã cắt khoảng trắng hai đầu; rỗng hoặc None thì None. Chỉ cho trường chữ."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def container_code(value: Any) -> str | None:
    """Mã ISO duy nhất trong ô; không có hoặc nhiều hơn một thì None. Tìm trước trên chữ giữ các từ tách nhau ("chờ - TCNU1234567"),
    không thấy mới bỏ khoảng trắng ("TCNU 1234567")."""
    upper = " ".join(str(value or "").upper().split())
    for text in (upper, upper.replace(" ", "")):
        found = ISO_CONTAINER.findall(text)
        if found:
            return found[0] if len(found) == 1 else None
    return None


def split_container(value: Any) -> tuple[str, str]:
    """(mã container, ghi chú đi kèm). Ô không tách được thì mã là chính ô viết hoa bỏ khoảng trắng và ghi chú rỗng. Ghi chú giữ chữ
    như người gõ, đã bỏ khoảng trắng và dấu ngăn ở hai đầu; mã bị dấu xen giữa ("MAUU-5500001") thì không có ghi chú."""
    spaced = " ".join(str(value or "").split())
    code = container_code(spaced)
    if code is None:
        return "".join(spaced.split()).upper(), ""
    at = spaced.upper().find(code)
    rest = spaced[:at] + " " + spaced[at + len(code):] if at >= 0 else ""
    return code, " ".join(re.sub(r"^[\W_]+|[\W_]+$", "", rest.strip()).split())


def container_key(value: Any) -> str:
    """Khóa so khớp container giữa Sheet và web. Ô số dạng khoa học ("4.2E7", "42000000.0") đọc thành số nguyên; ô có đúng một mã ISO
    kèm chữ thì lấy mã ISO; còn lại là ô viết hoa bỏ khoảng trắng (chữ số đầu số 0 giữ nguyên)."""
    text = "".join(str(value or "").upper().split())
    if ("." in text or "E" in text) and NUMBER_CELL.fullmatch(text):
        number = Decimal(text)
        if number == number.to_integral_value():
            return str(int(number))
    return container_code(value) or text
