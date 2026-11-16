"""Vùng ô của Sheet để dựng lại trên màn "Sheet cần sửa" (KIEM-TAB-01 đợt 3c, specs/v7-sheet-can-sua.md).

Chỉ đọc. Khi người dùng mở một chỗ sai, server gọi `spreadsheets.get` kèm `includeGridData` cho một vùng nhỏ quanh ô lỗi (khoảng 15
dòng, các cột của khối) bằng tài khoản dịch vụ chỉ đọc có sẵn (`spreadsheets.readonly`). Client không gửi A1: vùng do server tính từ
phát hiện của tab, nên chỉ đọc được tab của khách đó. ID Sheet và đường dẫn khóa chỉ qua biến môi trường, không vào repo. Cache ngắn,
trả kèm `read_at`. Không ghi gì lên Sheet.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from v7_api_validate import ApiError

API = "https://sheets.googleapis.com/v4/spreadsheets/"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
CACHE_SECONDS = 60
TIMEOUT_SECONDS = 8   # mỗi lần gọi Google (token và dữ liệu): quá thì màn vẫn hiện chữ, không đợi lâu
TOKEN_SECONDS = 3000   # token sống 3600 giây
SPAN = 7               # số dòng lấy thêm mỗi phía quanh ô
MAX_ROWS = 15
MIN_COLS, MAX_COLS = 18, 20
FIELDS = ("sheets(properties(sheetId,title),merges,data(startRow,startColumn,rowMetadata(pixelSize),columnMetadata(pixelSize),"
          "rowData(values(formattedValue,effectiveValue(numberValue),userEnteredValue(formulaValue),"
          "effectiveFormat(backgroundColor,textFormat(bold),horizontalAlignment,numberFormat(type))))))")
SHEET_ID = re.compile(r"[A-Za-z0-9_-]{20,100}")
CELL = re.compile(r"([A-Z]{1,3})([0-9]{1,6})")
REF = re.compile(r"\$?[A-Z]{1,3}\$?[0-9]{1,6}")
VN = ZoneInfo("Asia/Ho_Chi_Minh")
EPOCH = date(1899, 12, 30)   # ngày 0 của số thứ tự ngày trong Sheet

_lock = threading.Lock()
_token: dict[str, Any] = {"value": None, "until": 0.0}
_cache: dict[tuple, tuple[float, dict]] = {}


def log(*parts: Any) -> None:
    """Một dòng lên stderr (journal): chỉ tên tab, vùng, mã lỗi và thời gian đọc; không bao giờ nội dung ô, công thức hay khóa."""
    print("V7 vùng ô:", *parts, file=sys.stderr, flush=True)


def unavailable(why: str = "Chưa đọc được Sheet lúc này.", code: str = "") -> ApiError:
    if code:
        log("lỗi", code)
    return ApiError(503, "SHEET_REGION_UNAVAILABLE", why)


def config() -> tuple[str, str]:
    """(ID Sheet, đường dẫn khóa tài khoản dịch vụ) từ môi trường; thiếu hay sai thì 503, không đoán."""
    sheet, path = os.getenv("WEBDEBIT_SHEET_ID", ""), os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS", "")
    if not SHEET_ID.fullmatch(sheet) or not path:
        raise unavailable("Chưa cấu hình đọc Sheet cho máy chủ.", "CONFIG")
    return sheet, path


def column_letter(index: int) -> str:
    letters = ""
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def column_index(letters: str) -> int:
    number = 0
    for char in letters:
        number = number * 26 + ord(char) - 64
    return number


def split_cell(a1: str) -> tuple[int, int]:
    """'N45' -> (dòng 45, cột 14)."""
    match = CELL.fullmatch(a1 or "")
    if not match:
        raise ValueError("invalid cell")
    return int(match.group(2)), column_index(match.group(1))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _sign(data: bytes, private_key: str) -> bytes:
    """Chữ ký RS256 bằng `openssl dgst` (như runner). Khóa đi qua bộ nhớ (memfd) nên không chạm đĩa; không có memfd (không phải Linux)
    thì dùng file tạm quyền 600, xóa ngay."""
    if hasattr(os, "memfd_create"):
        fd = os.memfd_create("key")
        try:
            os.write(fd, private_key.encode())
            os.lseek(fd, 0, os.SEEK_SET)
            return subprocess.run(["openssl", "dgst", "-sha256", "-sign", f"/dev/fd/{fd}"], input=data, capture_output=True, check=True,
                                  timeout=TIMEOUT_SECONDS, pass_fds=(fd,)).stdout
        finally:
            os.close(fd)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as key:
        key.write(private_key)
        key_path = key.name
    try:
        return subprocess.run(["openssl", "dgst", "-sha256", "-sign", key_path], input=data, capture_output=True, check=True, timeout=TIMEOUT_SECONDS).stdout
    finally:
        os.unlink(key_path)


def _access_token(credentials_path: str, opener: Callable[..., Any], now: float) -> str:
    with _lock:
        if _token["value"] and now < _token["until"]:
            return _token["value"]
    try:
        with open(credentials_path, encoding="utf-8") as stream:
            credentials = json.load(stream)
        if credentials.get("type") != "service_account" or not credentials.get("client_email") or not credentials.get("private_key"):
            raise ValueError("credential is not a service account")
        issued = int(now)
        header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
        claims = _b64(json.dumps({"iss": credentials["client_email"], "scope": SCOPE, "aud": TOKEN_URL, "iat": issued,
                                  "exp": issued + 3600}, separators=(",", ":")).encode())
        signing_input = f"{header}.{claims}".encode("ascii")
        signature = _sign(signing_input, credentials["private_key"])
        body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                       "assertion": f"{header}.{claims}.{_b64(signature)}"}).encode()
        request = urllib.request.Request(TOKEN_URL, data=body, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            token = json.loads(response.read().decode("utf-8")).get("access_token")
    except (OSError, ValueError, subprocess.SubprocessError, urllib.error.URLError, KeyError) as exc:
        raise unavailable(code=f"TOKEN {type(exc).__name__}") from exc
    if not isinstance(token, str) or not token:
        raise unavailable(code="TOKEN EMPTY")
    with _lock:
        _token.update(value=token, until=now + TOKEN_SECONDS)
    return token


def region_bounds(rows: list[int], cells: list[str]) -> tuple[int, int, int, int]:
    """(dòng đầu, cột đầu, dòng cuối, cột cuối) quanh ô lỗi: SPAN dòng mỗi phía, tối đa MAX_ROWS dòng; các cột từ A tới cột xa nhất của
    ô nêu (ít nhất MIN_COLS, nhiều nhất MAX_COLS). Nhiều dòng cách xa nhau thì lấy quanh dòng đầu."""
    if not rows:
        raise ValueError("finding has no row")
    anchor = min(rows)
    first = max(1, anchor - SPAN)
    last = first + MAX_ROWS - 1
    far = max((split_cell(cell)[1] for cell in cells if CELL.fullmatch(cell)), default=0)
    return first, 1, last, min(MAX_COLS, max(MIN_COLS, far + 2))


def _hex(color: dict | None) -> str | None:
    if not color:
        return None
    parts = [int((Decimal(str(color.get(name, 0))) * 255).to_integral_value()) for name in ("red", "green", "blue")]   # màu, không phải tiền
    return None if parts == [255, 255, 255] else "#{:02x}{:02x}{:02x}".format(*parts)


def _serial_date(value: Any) -> date | None:
    try:
        return EPOCH + timedelta(days=int(value))
    except (TypeError, ValueError, OverflowError):
        return None


def date_swap(cell: dict, month: str | None) -> bool:
    """Ô ngày nghi gõ ngày/tháng mà Sheet đọc tháng/ngày (Sheet hiểu 10/11 là ngày 10 tháng 11 trong khi người gõ muốn 11 tháng 10). Chỉ
    khi cả ba điều kiện cùng đúng, theo `month` (yyyy-mm) của khối: ngày lưu nằm ngoài tháng của khối; đảo ngày với tháng thì rơi vào
    đúng tháng của khối (cùng năm); ngày lẫn tháng đều không quá 12. Không biết tháng khối hay không đọc được ngày lưu thì False."""
    stored = cell.get("serial")
    when = _serial_date(stored) if stored is not None else None
    if cell.get("kind") != "DATE" or when is None or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", month or ""):
        return False
    block_year, block_month = int(month[:4]), int(month[5:7])
    return ((when.year, when.month) != (block_year, block_month) and when.day <= 12 and when.month <= 12
            and when.year == block_year and when.day == block_month)


def date_swap_text(cell: dict, month: str) -> str:
    when = _serial_date(cell["serial"])
    return (f"Ô hiện {cell.get('v')} nhưng Sheet hiểu là ngày {when:%d/%m/%Y}, ngoài tháng {int(month[5:7])} của khối: "
            "có thể gõ ngày/tháng mà Sheet đọc tháng/ngày.")


def shape(formula: str | None) -> str | None:
    """Dáng công thức: số dòng thay bằng '#' để so công thức cùng loại ở các khối ('=SUM(M692:M847)' và '=SUM(M10:M99)' cùng dáng)."""
    return None if not formula else REF.sub(lambda m: re.sub(r"[0-9]+", "#", m.group(0)), formula.replace(" ", "").upper())


def build_region(raw: dict, first: int, col_first: int, last: int, col_last: int, marks: list[dict], month: str | None = None) -> dict:
    """Từ phản hồi `spreadsheets.get` dựng bản gọn cho client: ô (chữ hiện, công thức, nền, đậm, căn), ô gộp, cỡ cột/dòng, cột trống
    liên tiếp gộp thành một cột '…', và các ô nêu trong `marks` kèm cờ đảo ngày (theo `month` của khối)."""
    sheet = raw["sheets"][0]
    grid = sheet["data"][0]
    start_row, start_col = int(grid.get("startRow") or 0), int(grid.get("startColumn") or 0)
    row_data = grid.get("rowData") or []
    count_rows, count_cols = last - first + 1, col_last - col_first + 1
    cells: list[list[dict]] = []
    for r in range(count_rows):
        values = (row_data[r].get("values") or []) if r < len(row_data) else []
        line = []
        for c in range(count_cols):
            cell = values[c] if c < len(values) else {}
            fmt = cell.get("effectiveFormat") or {}
            line.append({"v": cell.get("formattedValue") or "", "f": (cell.get("userEnteredValue") or {}).get("formulaValue"),
                         "bg": _hex(fmt.get("backgroundColor")), "b": bool((fmt.get("textFormat") or {}).get("bold")),
                         "al": fmt.get("horizontalAlignment"), "kind": (fmt.get("numberFormat") or {}).get("type"),
                         "serial": (cell.get("effectiveValue") or {}).get("numberValue")})
        cells.append(line)
    widths = [int(m.get("pixelSize") or 100) for m in (grid.get("columnMetadata") or [])][:count_cols]
    widths += [100] * (count_cols - len(widths))
    heights = [int(m.get("pixelSize") or 21) for m in (grid.get("rowMetadata") or [])][:count_rows]
    heights += [21] * (count_rows - len(heights))
    merges = []
    for merge in sheet.get("merges") or []:
        r1, r2 = int(merge.get("startRowIndex", 0)) - (start_row), int(merge.get("endRowIndex", 0)) - start_row
        c1, c2 = int(merge.get("startColumnIndex", 0)) - start_col, int(merge.get("endColumnIndex", 0)) - start_col
        if r2 > 0 and r1 < count_rows and c2 > 0 and c1 < count_cols:
            merges.append({"r1": max(r1, 0), "c1": max(c1, 0), "r2": min(r2, count_rows), "c2": min(c2, count_cols)})
    flagged = {tuple(split_cell(mark["cell"])): mark for mark in marks if CELL.fullmatch(mark.get("cell", ""))}
    for r, line in enumerate(cells):
        for c, cell in enumerate(line):
            if month and date_swap(cell, month) and (first + r, col_first + c) not in flagged:
                flagged[(first + r, col_first + c)] = {"cell": f"{column_letter(col_first + c)}{first + r}", "level": "suspect",
                                                       "text": date_swap_text(cell, month)}
    mark_list = [{"row": row - first, "col": col - col_first, **mark} for (row, col), mark in sorted(flagged.items())
                 if first <= row <= last and col_first <= col <= col_last]
    busy = {c for line in cells for c, cell in enumerate(line) if cell["v"] or cell["f"]}
    busy |= {m["col"] for m in mark_list}
    groups: list[dict] = []
    for c in range(count_cols):
        if c in busy:
            groups.append({"cols": [c], "collapsed": False})
        elif groups and groups[-1]["collapsed"]:
            groups[-1]["cols"].append(c)
        else:
            groups.append({"cols": [c], "collapsed": True})
    for group in groups:
        if group["collapsed"] and len(group["cols"]) == 1:
            group["collapsed"] = False   # một cột trống đứng một mình vẫn là cột thường
    return {"sheet_id": sheet["properties"]["sheetId"], "first_row": first, "first_col": col_first,
            "col_letters": [column_letter(col_first + c) for c in range(count_cols)], "widths": widths, "heights": heights,
            "cells": [[{k: v for k, v in cell.items() if k not in ("kind", "serial")} for cell in line] for line in cells],
            "merges": merges, "column_groups": groups, "marks": mark_list}


def chain_sample(this_cell: dict, others: list[dict]) -> dict | None:
    """So ô của khối lỗi với ô cùng cột ở các khối khác (đã đọc công thức): dáng công thức phổ biến nhất là mẫu. Ô không có công thức,
    hoặc công thức khác dáng mẫu thì trả {"sample", "shapes", "current"}; giống mẫu hoặc không có mẫu thì None."""
    shapes = Counter(shape(other.get("f")) for other in others if other.get("f"))
    if not shapes:
        return None
    common, _ = shapes.most_common(1)[0]
    example = next(other["f"] for other in others if shape(other.get("f")) == common)
    current = this_cell.get("f")
    if current and shape(current) == common:
        return None
    return {"sample": example, "current": current or (this_cell.get("v") or None), "has_formula": bool(current)}


def fetch_region(tab: str, first: int, col_first: int, last: int, col_last: int, extra: list[str] | None = None, *,
                 opener: Callable[..., Any] = urllib.request.urlopen, now: float | None = None, fresh: bool = False) -> dict:
    """Đọc một vùng (cộng các dải phụ `extra`, A1 đầy đủ không kèm tên tab) có cache 60 giây; `fresh` (nút "Đọc lại") bỏ qua cache."""
    sheet_id, credentials = config()
    stamp = time.time() if now is None else now
    area = f"'{tab.replace(chr(39), chr(39) * 2)}'!{column_letter(col_first)}{first}:{column_letter(col_last)}{last}"
    ranges = [area] + [f"'{tab.replace(chr(39), chr(39) * 2)}'!{a1}" for a1 in extra or []]
    key = (sheet_id, tuple(ranges))
    with _lock:
        hit = _cache.get(key)
    if hit and not fresh and stamp - hit[0] < CACHE_SECONDS:
        return hit[1]
    token = _access_token(credentials, opener, stamp)
    query = [("ranges", r) for r in ranges] + [("includeGridData", "true"), ("fields", FIELDS)]
    request = urllib.request.Request(API + urllib.parse.quote(sheet_id) + "?" + urllib.parse.urlencode(query),
                                     headers={"Authorization": f"Bearer {token}"})
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise unavailable(code=f"HTTP {exc.code} {tab} {area}") from exc
    except (OSError, ValueError, urllib.error.URLError) as exc:
        raise unavailable(code=f"{type(exc).__name__} {tab} {area}") from exc
    if not raw.get("sheets") or not raw["sheets"][0].get("data"):
        raise unavailable("Không thấy tab trên Sheet.", f"NO_TAB {tab}")
    log("đọc", tab, area, f"{len(ranges)} dải", datetime.fromtimestamp(stamp, UTC).isoformat(timespec="seconds"))
    result = {"raw": {"sheets": [{**raw["sheets"][0], "data": raw["sheets"][0]["data"][:1]}]},
              "extra": list(raw["sheets"][0]["data"][1:]),
              "read_at": datetime.fromtimestamp(stamp, UTC).astimezone(VN).isoformat(timespec="seconds")}
    with _lock:
        _cache[key] = (stamp, result)
        if len(_cache) > 64:
            _cache.pop(next(iter(_cache)))
    return result
