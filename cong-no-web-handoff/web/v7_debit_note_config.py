"""DEBIT-NOTE-03: cấu hình mẫu debit note (mẫu đang dùng, thông tin công ty, ngân hàng, tên phí Anh/Trung).

Bản mặc định `debit-note-config.default.json` nằm cạnh file này, chỉ có thông tin công khai; ô chưa có dữ liệu là null
(trang in "[Tên trường]"). Thông tin ngân hàng thật nằm ngoài repo (repo public): file JSON ở `WEBDEBIT_DEBIT_NOTE_CONFIG`
ghi đè từng nhóm của bản mặc định. Chỉ đọc, đọc lại mỗi lần gọi để team sửa file là có hiệu lực, không cần khởi động lại.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("debit-note-config.default.json")
TEMPLATES = ("v3", "v4")
GROUPS = ("company", "payment", "fees")
MAX_TEXT = 300


class ConfigError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _text(value, where: str):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_TEXT or any(ord(ch) < 32 for ch in value):
        raise ConfigError(500, "DEBIT_NOTE_CONFIG_INVALID", f"Cấu hình debit note sai ở {where}.")
    return value.strip() or None


def _fee(code: str, value) -> dict:
    if not isinstance(value, dict) or set(value) - {"en", "cn", "width"}:
        raise ConfigError(500, "DEBIT_NOTE_CONFIG_INVALID", f"Cấu hình debit note sai ở fees.{code}.")
    width = value.get("width")
    if not isinstance(width, int) or isinstance(width, bool) or not 40 <= width <= 200:
        raise ConfigError(500, "DEBIT_NOTE_CONFIG_INVALID", f"Cấu hình debit note sai ở fees.{code}.width.")
    return {"en": _text(value.get("en"), f"fees.{code}.en"), "cn": _text(value.get("cn"), f"fees.{code}.cn"), "width": width}


def merge(base: dict, override: dict) -> dict:
    """Bản mặc định + file riêng: khóa cấp 1 thay hẳn, nhóm company/payment/fees ghi đè từng khóa."""
    if not isinstance(override, dict) or set(override) - {"template", "show_place_cn", *GROUPS}:
        raise ConfigError(500, "DEBIT_NOTE_CONFIG_INVALID", "Cấu hình debit note có khóa lạ.")
    out = {**base, **{key: value for key, value in override.items() if key not in GROUPS}}
    for group in GROUPS:
        if group in override:
            if not isinstance(override[group], dict):
                raise ConfigError(500, "DEBIT_NOTE_CONFIG_INVALID", f"Cấu hình debit note sai ở {group}.")
            out[group] = {**base.get(group, {}), **override[group]}
    return out


def clean(config: dict) -> dict:
    if config.get("template") not in TEMPLATES or not isinstance(config.get("show_place_cn"), bool):
        raise ConfigError(500, "DEBIT_NOTE_CONFIG_INVALID", "Cấu hình debit note sai ở template hoặc show_place_cn.")
    company = {key: _text(config["company"].get(key), f"company.{key}") for key in ("name", "address", "tax_id", "tel", "email")}
    payment = {key: _text(config["payment"].get(key), f"payment.{key}")
               for key in ("beneficiary", "bank", "account_label_en", "account_label_cn", "account", "swift")}
    fees = {str(code): _fee(str(code), value) for code, value in config["fees"].items()}
    return {"template": config["template"], "show_place_cn": config["show_place_cn"], "company": company, "payment": payment, "fees": fees}


def load(private_path: str | None = None) -> dict:
    with DEFAULT_PATH.open(encoding="utf-8") as handle:
        config = json.load(handle)
    path = private_path if private_path is not None else os.getenv("WEBDEBIT_DEBIT_NOTE_CONFIG")
    if path:
        try:
            with open(path, encoding="utf-8") as handle:
                config = merge(config, json.load(handle))
        except (OSError, ValueError) as exc:
            raise ConfigError(503, "DEBIT_NOTE_CONFIG_UNAVAILABLE", "Không đọc được file cấu hình debit note của máy chủ.") from exc
    return clean(config)


def handle_get(query: str, private_path: str | None = None) -> tuple[int, dict]:
    """GET /api/v7/debit-note/config: không nhận tham số."""
    if query:
        raise ConfigError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
    return 200, {"config": load(private_path)}
