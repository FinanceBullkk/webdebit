"""THONG-TIN-CTY-01: GET /api/v7/company-info trả bản chụp Sheet "thông tin khách hàng" cho tab Thông tin cty và hộp debit note.

Bản chụp do `tools/v7_company_info_snapshot.py` (timer trên `hao`) ghi ở `WEBDEBIT_COMPANY_INFO_PATH`, ngoài repo, mode 600. Chưa có file
là chưa bật job (`available: false`); file hỏng là lỗi máy chủ. Chỉ đọc, đọc lại khi file đổi.
"""

from __future__ import annotations

import json
import os
import threading

DEFAULT_PATH = "/var/lib/webdebit-sheet-sync/company-info.json"
ACCOUNT_KEYS = ("beneficiary", "address", "bank", "bank_address", "account", "swift")
HEADER_KEYS = ("name", "address", "tax_id", "tel", "email")   # đầu trang debit note khi chọn công ty phát hành
_CACHE: dict = {}
_LOCK = threading.Lock()


class InfoError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _broken() -> InfoError:
    return InfoError(503, "COMPANY_INFO_UNAVAILABLE", "Không đọc được bản Thông tin cty của máy chủ.")


def _text(value, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise _broken()
    return value


def clean(raw: dict) -> dict:
    """Chỉ đưa ra các trường trang cần, đúng kiểu; sai kiểu là file hỏng."""
    if not isinstance(raw, dict) or not isinstance(raw.get("accounts"), list) or not isinstance(raw.get("customers"), list):
        raise _broken()
    accounts = []
    for item in raw["accounts"]:
        if not isinstance(item, dict) or not isinstance(item.get("lines"), list):
            raise _broken()
        accounts.append({"id": _text(item.get("id")), "title": _text(item.get("title")), "label": _text(item.get("label")),
                         "currency": _text(item.get("currency"), optional=True),
                         **{key: _text(item.get(key), optional=True) for key in ACCOUNT_KEYS},
                         "lines": [{"label": _text(line.get("label")), "value": _text(line.get("value"))}
                                   for line in item["lines"] if isinstance(line, dict)]})
    customers = []
    for item in raw["customers"]:
        rows = item.get("rows") if isinstance(item, dict) else None
        if not isinstance(rows, list) or len(rows) != 2 or not all(isinstance(row, int) and not isinstance(row, bool) for row in rows):
            raise _broken()
        header = item.get("header") if isinstance(item.get("header"), dict) else {}
        customers.append({"name": _text(item.get("name")), "company": _text(item.get("company")), "rows": rows,
                          **{key: _text(item.get(key)) for key in ("shipper", "invoice", "bank")},
                          "header": {key: _text(header.get(key), optional=True) for key in HEADER_KEYS}})
    runner = raw.get("runner") if isinstance(raw.get("runner"), dict) else {}
    return {"available": True, "read_at": _text(runner.get("created_at"), optional=True), "accounts": accounts, "customers": customers,
            "counts": {key: value for key, value in (raw.get("counts") or {}).items() if isinstance(value, int)}}


def load(path: str) -> dict | None:
    """Bản đã làm sạch, hoặc None khi chưa có file. Giữ một bản theo (mtime, size, inode)."""
    try:
        stat = os.stat(path)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _broken() from exc
    stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    with _LOCK:
        hit = _CACHE.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    try:
        with open(path, encoding="utf-8") as handle:
            value = clean(json.load(handle))
    except (OSError, ValueError) as exc:
        raise _broken() from exc
    with _LOCK:
        _CACHE[path] = (stamp, value)
    return value


def handle_get(query: str, path: str | None = None) -> tuple[int, dict]:
    """GET /api/v7/company-info: không nhận tham số."""
    if query:
        raise InfoError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
    body = load(path or os.getenv("WEBDEBIT_COMPANY_INFO_PATH", DEFAULT_PATH))
    return 200, body if body is not None else {"available": False}
