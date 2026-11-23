"""Bộ kiểm số (ZALO-BOT-01 Phần 4): số trong câu trả lời phải lấy đúng từ kết quả công cụ của chính lượt đó.

1. **Điền chỗ trống.** Model không gõ số tiền mà viết `{t2.tong_no_vnd}` hay `{t1.rows.0.no_vnd}`: kết quả công cụ thứ 2, đường
   dẫn trong JSON (số là vị trí trong danh sách). Bot điền giá trị; trường `*_vnd` là tiền, định dạng như web (`1.234.567 đ`).
   Chỉ trích được các loại trường trong danh sách cho phép (`field_kind`): tiền, tên sổ, ngày/tháng, số đếm, tỉ lệ. Trường
   chữ khác (tên trò chuyện Zalo, lý do, tóm tắt…) không trích được, để chữ người ngoài đặt không đi qua chỗ trống mà né bộ kiểm.
   Chỗ trống trỏ tới trường không có hay không được phép thì bản nháp bị trả lại.
2. **Kiểm mọi số còn lại theo danh sách trắng.** Chữ được chuẩn hóa trước (bỏ dấu, chữ số toàn khổ, nhóm bằng `.`, `,`, khoảng
   trắng hay `'`), rồi mỗi số phải thuộc một trường hợp được phép:
   - số có đơn vị tiền (`đ`, `đồng`, `VND`) hay đơn vị lớn (`nghìn`, `k`, `triệu`, `tr`, `trđ`, `M`, `tỷ`, `tỉ`, `B`, kể cả viết
     liền `1tỷ2`) phải bằng một giá trị tiền trong kết quả công cụ; số làm tròn phải có ít nhất hai chữ số có nghĩa, có chữ
     "khoảng/gần/hơn…" ngay trước và đúng chiều ("hơn" thì số thật không nhỏ hơn, "gần" thì không lớn hơn); `0 đ` gõ tay luôn bị
     chặn (số 0 phải là chỗ trống); số âm gõ tay phải có đúng giá trị âm đó;
   - số nhóm chữ số không kèm đơn vị, và số trơn từ 4 chữ số, phải trùng một giá trị trong kết quả công cụ (năm 2000–2099 được);
   - số nhỏ (tới 3 chữ số) trơn phải trùng một số trong kết quả công cụ, hoặc đứng cạnh từ đếm ("3 chuyến", "tháng 10");
   - phần trăm phải trùng một tỉ lệ trong kết quả công cụ (công cụ `tinh`).
   Phần bot vừa điền từ trường tiền và tên được che trước khi kiểm; ngày, giờ dạng dd/mm/yyyy, hh:mm, yyyy-mm-dd cũng được che.

Giới hạn (spec Phần 4): bộ kiểm chặn số không có nguồn, không bắt được số thật đặt sai chỗ khi model chọn sai trường; dòng
"Sổ: …" và "Kỳ: …" bot tự thêm (model.py) để người đọc thấy số đó của sổ nào, kỳ nào.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
PLACEHOLDER = re.compile(r"\{t(\d{1,2})((?:\.[A-Za-z0-9_]{1,40}){1,6})\}")
# Đơn vị lớn, viết trên chữ đã bỏ dấu: trđ → trd, tỷ → ty.
UNITS = {"nghin": 10**3, "ngan": 10**3, "k": 10**3, "trieu": 10**6, "trd": 10**6, "tr": 10**6, "m": 10**6,
         "ty": 10**9, "ti": 10**9, "b": 10**9}
# Chữ trước số làm tròn: hai phía, hay một phía (hơn/trên: số thật ≥ số ghi; gần/dưới: số thật ≤ số ghi).
APPROX = re.compile(r"(khoảng|khoang|xấp xỉ|xap xi|chừng|tầm|cỡ|độ|gần|gan|dưới|duoi|hơn|hon|trên|tren)\s*$")
ABOVE = ("hơn", "hon", "trên", "tren")
BELOW = ("gần", "gan", "dưới", "duoi")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:[+-]\d{2}:\d{2}|Z)?)?\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"
                  r"|\b\d{1,2}/\d{4}\b|\b\d{1,2}:\d{2}\b|\b\d{4}-\d{2}\b")
NUMBER = re.compile(
    r"(?<![\w.,'’])(-\s?)?"
    r"(\d{1,3}(?:([.,'’ ])\d{3})(?:\3\d{3})*(?![\d])|\d+(?:[.,]\d+)?)"     # nhóm 3 chữ số cùng một dấu, hoặc số trơn/thập phân
    r"(?:\s*(nghin|ngan|trieu|trd|tr|ty|ti|k|m|b)(?:(\d{1,3})(?![\d.,])|(?![a-z])))?")
CURRENCY = re.compile(r"\s*(đồng|vnđ|vnd|đ|dong|d)(?![a-zà-ỹđ0-9])")
AMOUNT_AFTER = re.compile(r"\s*(triệu|trieu|tỷ|tỉ|ty|nghìn|ngàn|nghin|tr|k|đồng|đ|vnd)(?![a-zà-ỹđ])")
# Số tiền viết bằng chữ ("năm trăm triệu"): đơn vị lớn có dấu đứng một mình, không sau chữ số. "tỉ lệ" không phải tiền.
SCALE_WORD = re.compile(r"(?<![a-zà-ỹđ])(triệu|tỷ|tỉ(?! lệ)|nghìn|ngàn)(?![a-zà-ỹđ])")
PERCENT = re.compile(r"\s*(%|phần trăm|phan tram)")
COUNT_AFTER = re.compile(
    r"\s*(chuyen|khach|so|phieu|thang|ngay|tuan|nam|gio|phut|giay|lan|cont|container|xe|tai xe|nguoi|tin|nhom|muc|dong|hang|"
    r"cau|viec|booking|buoc|ky|lo|tab|tieng|cot|loai|mat hang|file|trang|thao tac|dieu chinh|khoan|cuoc|bang|ban)(?![a-z])")
COUNT_BEFORE = re.compile(r"(thang|ngay|nam|quy|tuan|lan|lan thu|ma|so|top|hang|buoc|muc|ky|thu|phien|tab|trang|nhom|lo)\s*$")
YEARS = range(2000, 2100)
URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")

# Trường trích được qua chỗ trống (theo tên khóa cuối của đường dẫn).
NAME_FIELDS = frozenset({"ten", "name", "display_name", "customer_name", "mat_hang", "van_chuyen"})
DATE_FIELDS = frozenset({"thang", "ngay", "tu_ngay", "den_ngay", "tra_lan_cuoi", "chuyen_gan_nhat", "thang_no_cu_nhat", "luc",
                         "as_of", "month", "date", "day", "at", "checked_at", "finished_at", "started_at"})
COUNT_FIELDS = frozenset({"nam", "tong", "khach_id", "customer_id", "count", "total", "ready_count", "reapply_count"})


class FillError(ValueError):
    """Chỗ trống trỏ tới trường không có hay không được trích. `str(error)` là chỗ trống đó (kèm lý do), để trả lại model sửa."""


@dataclass(frozen=True)
class Problem:
    # unknown_amount | zero_typed | rounded_without_approx | rounded_too_coarse | unknown_number | unknown_percent
    code: str
    text: str          # đoạn chữ có số bị bắt, để trả lại model


def format_vnd(value: int) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value):,}".replace(",", ".") + " đ"


def strip_urls(text: str) -> str:
    """Bỏ link model tự viết: link duy nhất trong câu trả lời là dòng "Mở:" bot thêm từ kết quả công cụ."""
    return URL.sub("", text)


def field_kind(key: str) -> str | None:
    """Loại trường được trích qua chỗ trống: money | name | date | count | percent; None là không được trích."""
    if key.endswith("_vnd"):
        return "money"
    if key in NAME_FIELDS:
        return "name"
    if key in DATE_FIELDS or key.endswith(("_luc", "_at", "_date", "_month")) or key.startswith("ngay_"):
        return "date"
    if key.startswith("ti_le") or key.endswith("_pct"):
        return "percent"
    if key in COUNT_FIELDS or key.startswith(("so_", "dem_")) or key.endswith(("_count", "_days", "_so")):
        return "count"
    return None


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


def format_date(value: object) -> str | None:
    """"2026-10" → "10/2026", "2026-10-05" → "05/10/2026", giờ ISO → "HH:MM dd/mm/yyyy" giờ VN; khác khuôn: None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text):
        return f"{text[5:7]}/{text[:4]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return dt.date.fromisoformat(text).strftime("%d/%m/%Y")
        except ValueError:
            return None
    try:
        at = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if at.tzinfo is not None:
        at = at.astimezone(VN)
    return at.strftime("%H:%M %d/%m/%Y")


def _render(kind: str, value: object) -> str | None:
    if kind == "money":
        money = _as_vnd(value)
        return format_vnd(money) if money is not None else None
    if kind == "name":
        return value.strip() if isinstance(value, str) and value.strip() else None
    if kind == "date":
        return format_date(value)
    if kind == "count":
        number = _as_vnd(value)
        return str(number) if number is not None else None
    if kind == "percent" and isinstance(value, (int, str)) and not isinstance(value, bool) \
            and re.fullmatch(r"-?\d{1,6}(?:[.,]\d{1,3})?", str(value)):
        return str(value).replace(".", ",")
    return None


def fill(draft: str, results: list[object]) -> tuple[str, list[tuple[int, int]]]:
    """Điền chỗ trống bằng giá trị trong kết quả công cụ (đánh số từ 1 theo thứ tự gọi). Trả chữ đã điền và các khoảng được
    che khi kiểm số: phần điền từ trường tiền và tên. Ngày, số đếm, tỉ lệ vẫn đi qua bộ kiểm như chữ model viết."""
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
        kind = field_kind(path[-1])
        if kind is None:
            raise FillError(f"{match.group(0)} (trường này không trích được; tiền, tên sổ, ngày, số đếm mới được)")
        text = _render(kind, value) if not isinstance(value, (dict, list)) else None
        if text is None:
            raise FillError(match.group(0))
        before = draft[last:match.start()]
        out.append(before)
        length += len(before)
        out.append(text)
        if kind in ("money", "name"):
            spans.append((length, length + len(text)))
        length += len(text)
        last = match.end()
    out.append(draft[last:])
    return "".join(out), spans


def collect_values(results: Iterable[object]) -> tuple[set[int], set[int]]:
    """(giá trị tiền, mọi số nguyên) có trong kết quả công cụ, trị tuyệt đối: tiền là trường `*_vnd`; số nguyên gồm cả số đếm, mã."""
    money, numbers, _signed, _percents = _collect(results)
    return money, numbers


def _collect(results: Iterable[object]) -> tuple[set[int], set[int], set[int], set[Decimal]]:
    money: set[int] = set()
    numbers: set[int] = set()
    signed: set[int] = set()
    percents: set[Decimal] = set()

    def walk(node: object, key: str = "") -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                walk(child, str(child_key))
        elif isinstance(node, list):
            for child in node:
                walk(child, key)
        else:
            if field_kind(key) == "percent" and isinstance(node, (int, str)) and not isinstance(node, bool):
                number = _decimal(str(node))
                if number is not None:
                    percents.add(abs(number))
            value = _as_vnd(node)
            if value is None:
                return
            numbers.add(abs(value))
            if key.endswith("_vnd"):
                money.add(abs(value))
                signed.add(value)

    for result in results:
        walk(result)
    return money, numbers, signed, percents


def _fold_char(ch: str) -> str:
    """Một ký tự → một ký tự: chữ số toàn khổ về ASCII, chữ thường, bỏ dấu tiếng Việt (đ → d). Giữ nguyên độ dài để vị trí khớp."""
    norm = unicodedata.normalize("NFKC", ch)
    if len(norm) != 1:
        return "_"
    low = norm.lower()
    if low == "đ":
        return "d"
    base = unicodedata.normalize("NFD", low)[0]
    return base if base.isascii() else low


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _masked(text: str, spans: list[tuple[int, int]]) -> str:
    """Chữ thường, chữ số ASCII; thay phần bot vừa điền và các ngày, giờ bằng khoảng trắng cùng độ dài."""
    chars = [unicodedata.normalize("NFKC", ch).lower() if len(unicodedata.normalize("NFKC", ch)) == 1 else "_" for ch in text]
    for start, end in spans:
        chars[start:end] = " " * (end - start)
    masked = "".join(chars)
    # Ngày ngay trước đơn vị tiền ("12/11 triệu") không phải ngày: để bộ kiểm thấy số.
    return DATE.sub(lambda m: m.group(0) if AMOUNT_AFTER.match(masked, m.end()) else " " * len(m.group(0)), masked)


@dataclass(frozen=True)
class _Number:
    start: int
    end: int
    value: Decimal          # giá trị đồng (đã nhân đơn vị) hoặc số trơn
    digits: str             # chữ số gốc, để đếm chữ số có nghĩa
    decimals: int
    unit: int               # 1 nếu không có đơn vị lớn
    grouped: bool
    currency: bool
    percent: bool
    negative: bool


def _numbers(low: str, fold: str) -> list[_Number]:
    found = []
    for match in NUMBER.finditer(fold):
        sign, raw, sep, unit_word, tail = match.group(1), match.group(2), match.group(3), match.group(4), match.group(5)
        unit = UNITS[unit_word] if unit_word else 1
        if unit_word and sep and raw.count(sep) == 1:
            raw = raw.replace(sep, ",")           # "1,500 tỷ" là 1,5 tỷ, không phải 1500 tỷ
            sep = None
        if tail:
            raw = f"{raw},{tail}" if not re.search(r"[.,]", raw) else raw + tail   # "1tỷ2" là 1,2 tỷ
        grouped = bool(sep)
        digits = re.sub(r"\D", "", raw)
        if grouped:
            number, decimals = Decimal(digits), 0
        else:
            number = _decimal(raw)
            if number is None:
                continue
            exponent = number.as_tuple().exponent
            decimals = -exponent if isinstance(exponent, int) and exponent < 0 else 0
        end = match.end()
        currency = percent = False
        after = CURRENCY.match(low, end)
        if after and not unit_word:
            currency, end = True, after.end()
        elif after and unit_word:
            end = after.end()
        else:
            after = PERCENT.match(low, end)
            if after and not unit_word:
                percent, end = True, after.end()
        found.append(_Number(match.start(), end, number * unit, digits.lstrip("0") or "0", decimals, unit, grouped, currency or unit > 1,
                             percent, bool(sign)))
    return found


def check(text: str, spans: list[tuple[int, int]], money: set[int], numbers: set[int], *,
          signed: set[int] | None = None, percents: set[Decimal] | None = None) -> list[Problem]:
    """Các số gõ tay không có nguồn trong `text` đã điền, theo thứ tự xuất hiện. Rỗng là qua."""
    low = _masked(text, spans)
    fold = "".join(_fold_char(ch) for ch in low)
    signed = signed if signed is not None else set(money)
    percents = percents or set()
    found: list[tuple[int, Problem]] = []

    def snippet(item: _Number) -> str:
        return text[max(item.start - 12, 0):item.end].strip()

    def add(position: int, problems: list[Problem]) -> None:
        found.extend((position, problem) for problem in problems)

    items = _numbers(low, fold)
    for word in SCALE_WORD.finditer(low):
        if not any(item.start <= word.start() < item.end for item in items):
            add(word.start(), [Problem("amount_in_words", text[max(word.start() - 24, 0):word.end()].strip())])
    for item in items:
        before = low[max(item.start - 12, 0):item.start]
        if item.percent:
            if item.value not in percents:
                add(item.start, [Problem("unknown_percent", snippet(item))])
            continue
        if item.currency:
            add(item.start, _check_amount(item, before, money, signed, snippet(item)))
            continue
        integral = item.value == item.value.to_integral_value()
        value = int(item.value) if integral else None
        if item.grouped or len(item.digits) >= 4:
            if value is not None and (value in money or value in numbers or (not item.grouped and value in YEARS)):
                continue
            add(item.start, [Problem("unknown_number", snippet(item))])
            continue
        if value is not None and value in numbers:
            continue
        if COUNT_AFTER.match(fold, item.end) or COUNT_BEFORE.search(fold[max(item.start - 12, 0):item.start]):
            continue
        add(item.start, [Problem("unknown_number", snippet(item))])
    problems = [problem for _position, problem in sorted(found, key=lambda pair: pair[0])]
    return problems


def _check_amount(item: _Number, before: str, money: set[int], signed: set[int], text: str) -> list[Problem]:
    amount = item.value
    exact = amount == amount.to_integral_value()
    if exact and int(amount) == 0:
        return [Problem("zero_typed", text)]
    if exact and (int(amount) in money if not item.negative else -int(amount) in signed):
        return []
    if item.unit == 1:
        return [Problem("unknown_amount", text)]
    step = Decimal(item.unit) / (Decimal(10) ** item.decimals)
    word = APPROX.search(before)
    marker = word.group(1) if word else ""

    def fits(value: int) -> bool:
        real = Decimal(value)
        if marker in ABOVE:
            return amount <= real < amount + step
        if marker in BELOW:
            return amount - step < real <= amount
        return abs(real - amount) <= step / 2

    if not any(fits(value) for value in money):
        return [Problem("unknown_amount", text)]
    if not word:
        return [Problem("rounded_without_approx", text)]
    if len(item.digits.rstrip("0") if item.decimals else item.digits) < 2:
        return [Problem("rounded_too_coarse", text)]
    return []


def typed_amounts(text: str) -> set[int]:
    """Số tiền gõ tay (có đơn vị tiền hoặc nhóm chữ số) trong câu trả lời đã điền: dùng để chấm bộ câu hỏi mẫu."""
    low = _masked(text, [])
    fold = "".join(_fold_char(ch) for ch in low)
    return {int(item.value) for item in _numbers(low, fold)
            if (item.currency or item.grouped) and item.value == item.value.to_integral_value()}


def check_text(text: str, spans: list[tuple[int, int]], results: Iterable[object]) -> list[Problem]:
    """Gọn cho model.py: gom giá trị từ kết quả công cụ rồi kiểm."""
    money, numbers, signed, percents = _collect(results)
    return check(text, spans, money, numbers, signed=signed, percents=percents)
