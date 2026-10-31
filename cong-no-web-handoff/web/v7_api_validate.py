"""Kiểm dữ liệu vào của API V7: lỗi API, thân JSON của POST (`validate`) và chuỗi truy vấn của GET (`validate_get`).

Mỗi hàm trả (tên hàm `sokhach.*`, payload) hoặc ném `ApiError`; không gọi DB, không biết actor.
Tách nguyên từ `v7_ledger_api.py` 31/10/2026: điều kiện kiểm, mã lỗi và thông điệp giữ nguyên;
phần GET chuyển từ chuỗi if/elif trong `handle()` thành bảng `GET_ROUTES`.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from v7_api_tables import (
    ARGUMENTS,
    BASE64,
    COMMON,
    ERRORS,
    IMAGE_TYPES,
    MAX_BIGINT,
    MAX_IMAGE_BYTES,
    ROUTES,
    TRIP_FIELDS,
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def bad(code: str = "INVALID_REQUEST", message: str = "Dữ liệu gửi không hợp lệ.") -> None:
    raise ApiError(422, code, message)


def positive_int(value: object) -> bool:
    return type(value) is int and 0 < value <= MAX_BIGINT


def vnd(value: object, *, signed: bool = False, nullable: bool = False) -> bool:
    if value is None:
        return nullable
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)" if not signed else r"(?:0|-?[1-9][0-9]*)", value):
        return False
    digits = value.lstrip("-")
    limit = str(MAX_BIGINT + (value.startswith("-")))
    return len(digits) < len(limit) or (len(digits) == len(limit) and digits <= limit)


def valid_date(value: object, *, month: bool = False, trip: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    fmt = "%d/%m/%Y" if trip else "%Y-%m-%d"
    if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}" if trip else r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return False
    try:
        parsed = datetime.strptime(value, fmt).date()
    except ValueError:
        return False
    return not month or parsed.day == 1


def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            bad()
        result[key] = value
    return result


def validate_fee(function: str, body: dict) -> tuple[str, dict]:
    update = function == "fee_type_update"
    if update:
        function = body.get("command")
        if type(function) is not str or function not in ("rename_fee_type", "set_fee_type_kind", "set_fee_type_active"):
            bad()
    catalog = function in ("add_fee_type", "rename_fee_type", "set_fee_type_kind", "set_fee_type_active")
    required = set(ARGUMENTS[function]) | (set() if catalog else COMMON)
    optional = {"note"} if function in ("add_trip_fees", "replace_trip_fee") else set()
    if set(body) - (required | ({"command"} if update else set())) or not set(body) >= required - optional:
        bad()
    key = body.get("idempotency_key")
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.strip() or any(ord(c) < 32 for c in key):
        bad()
    if not catalog and (not positive_int(body.get("customer_id")) or type(body.get("expected_version")) is not int
                        or not 0 <= body["expected_version"] <= MAX_BIGINT):
        bad()
    for field in ("fee_type_id", "fee_line_id"):
        if field in required and not positive_int(body.get(field)):
            bad()
    if "amount_vnd" in required:
        amount = body["amount_vnd"]
        if not vnd(amount, signed=True, nullable=function == "set_trip_fee_type") or amount == "0":
            bad("FEE_AMOUNT_INVALID", ERRORS["FEE_AMOUNT_INVALID"][1])
    if "note" in body and body["note"] is not None and (type(body["note"]) is not str or len(body["note"]) > 2000):
        bad()
    targets = body.get("targets") if function == "add_trip_fees" else [body["target"]] if "target" in body else []
    if type(targets) is not list or (function == "add_trip_fees" and not targets):
        bad()
    for target in targets:
        if type(target) is not dict or set(target) not in ({"trip_id"}, {"legacy_row_id"}) or not positive_int(next(iter(target.values()))):
            bad()
    if len({json.dumps(t, sort_keys=True) for t in targets}) != len(targets):
        bad()
    if function == "set_book_fee_columns":
        ids = body["fee_type_ids"]
        if type(ids) is not list or any(not positive_int(i) for i in ids) or len(set(ids)) != len(ids):
            bad()
        if len(ids) > 3:
            bad("FEE_COLUMNS_MAX", ERRORS["FEE_COLUMNS_MAX"][1])
    if "name" in required and (type(body["name"]) is not str or not body["name"].strip() or len(body["name"]) > 200):
        bad()
    if "kind" in required and body["kind"] not in ("service", "pass_through"):
        bad()
    if "active" in required and type(body["active"]) is not bool:
        bad()
    return function, {k: v for k, v in body.items() if k != "command"}


def image_bytes(content_type: object, data: object) -> bytes:
    """Kiểm ảnh trước khi tới DB; DB kiểm lại đầu file và kích thước."""
    if content_type not in IMAGE_TYPES or not isinstance(data, str) or len(data) % 4 or not BASE64.fullmatch(data):
        bad("IMAGE_INVALID", ERRORS["IMAGE_INVALID"][1])
    image = base64.b64decode(data, validate=True)
    if len(image) > MAX_IMAGE_BYTES:
        bad("IMAGE_TOO_LARGE", ERRORS["IMAGE_TOO_LARGE"][1])
    magic = IMAGE_TYPES[content_type]
    if not image.startswith(magic[0]) or (len(magic) > 1 and image[8:12] != magic[1]):
        bad("IMAGE_INVALID", ERRORS["IMAGE_INVALID"][1])
    return image


def validate(path: str, raw: bytes) -> tuple[str, dict]:
    if path not in ROUTES:
        raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_float=lambda _: bad(), parse_constant=lambda _: bad())
        json.dumps(body, ensure_ascii=False).encode("utf-8")
    except (UnicodeError, ValueError, TypeError, RecursionError):
        bad()
    if not isinstance(body, dict):
        bad()
    function, fields = ROUTES[path]
    if "/fees/" in path or path.startswith("/api/v7/fee-types") or path.endswith("/fee-columns"):
        return validate_fee(function, body)
    offset = function in ("record_offset", "void_offset", "edit_offset_date")
    common = set() if offset else COMMON
    if set(body) - (common | fields) or not set(body) >= ((fields - {"reference"}) if offset else COMMON):
        bad()
    fields = fields | common
    required_numeric = ("customer_id", "target_customer_id", "source_customer_id")
    if any(name in fields and (not positive_int(body.get(name))) for name in required_numeric):
        bad()
    for name in ("expected_version", "target_version", "source_version", "other_version"):
        if name in fields and (type(body.get(name)) is not int or not 0 <= body[name] <= MAX_BIGINT):
            bad()
    key = body["idempotency_key"]
    if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.strip() or any(ord(c) < 32 for c in key):
        bad()
    for name in ("trip_id", "legacy_row_id", "adjustment_id"):
        if name in fields and (name not in body or not positive_int(body[name])):
            bad()
    for name in ("debt_month", "month"):
        if name in fields and (name not in body or not valid_date(body[name], month=True)):
            bad()
    if function in ("edit_trip_info", "edit_legacy_trip"):
        allowed = {"container", "carrier", "shipper", "origin", "destination", "event_date", "unit_price_vnd", "other_fee_vnd"}
        if function == "edit_trip_info":
            allowed -= {"unit_price_vnd", "other_fee_vnd"}
        if not isinstance(body.get("field"), str) or body["field"] not in allowed:
            bad("INVALID_FIELD", ERRORS["INVALID_FIELD"][1])
        if "value" not in body or not isinstance(body["value"], str):
            bad()
        if body["field"] == "event_date" and not valid_date(body["value"]):
            bad("INVALID_DATE", ERRORS["INVALID_DATE"][1])
        if body["field"] in ("unit_price_vnd", "other_fee_vnd") and body["value"].strip() and not vnd(body["value"], signed=body["field"] == "other_fee_vnd"):
            bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    if function == "adjust_trip":
        by_field = "field" in body or "new_value_vnd" in body
        if by_field:
            if (body.get("field") not in ("unit_price_vnd", "other_fee_vnd")
                    or not vnd(body.get("new_value_vnd"), signed=body.get("field") == "other_fee_vnd") or "new_amount_vnd" in body):
                bad()
        elif not vnd(body.get("new_amount_vnd")):
            bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    for name in ("amount_vnd", "unit_price_vnd", "other_fee_vnd"):
        if name in fields and (name not in body or not vnd(body[name], signed=(name == "amount_vnd" and function == "adjust_month") or name == "other_fee_vnd",
                                                      nullable=name in ("unit_price_vnd", "other_fee_vnd"))):
            bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    if function == "record_offset" and body["amount_vnd"] == "0":
        bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    for name in ("offset_pair_id",):
        if name in fields and not positive_int(body.get(name)):
            bad()
    if function == "paste_trips":
        trips = body.get("trips")
        if not isinstance(trips, list) or not trips or len(trips) > 200:
            bad()
        for trip_row in trips:
            if not isinstance(trip_row, dict) or set(trip_row) - TRIP_FIELDS:
                bad()
            if "date" in trip_row and trip_row["date"] is not None and not valid_date(trip_row["date"], trip=True):
                bad()
            for name in ("unitPriceVnd", "otherFeeVnd"):
                if name in trip_row and not vnd(trip_row[name], signed=name == "otherFeeVnd", nullable=True):
                    bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
            if "fees" in trip_row and (not isinstance(trip_row["fees"], list)
                                       or trip_row.get("otherFeeVnd") is not None
                                       or any(not vnd(fee, signed=True) or fee in ("0", "-0") for fee in trip_row["fees"])):
                bad("INVALID_VND", "Phụ phí phải là mảng chuỗi số nguyên VND khác 0.")
            if any(type(value) is not str and value is not None for name, value in trip_row.items() if name != "fees"):
                bad()
    for name in ("date",):
        if not offset and name in fields and ((name not in body and function == "record_receipt") or (name in body and body[name] is not None and not valid_date(body[name]))):
            bad()
    if function in ("record_offset", "edit_offset_date") and not valid_date(body.get("date")):
        bad("INVALID_DATE", "Ngày không hợp lệ.")
    if function == "void_offset" and (not isinstance(body.get("reason"), str) or not body["reason"].strip() or len(body["reason"]) > 500):
        bad("VOID_REASON_REQUIRED", "Cần ghi lý do hủy cấn trừ.")
    for name in ("method", "pid", "reason", "note", "reference"):
        if name in fields and name in body and body[name] is not None and (not isinstance(body[name], str) or len(body[name]) > 500):
            bad()
    if function == "record_receipt" and (not isinstance(body.get("method"), str) or not body["method"] or body["amount_vnd"] == "0"):
        bad()
    if function == "edit_receipt_meta" and not any(body.get(name) is not None for name in ("date", "method", "reference")):
        bad()
    if function in ("edit_receipt_meta", "void_receipt") and not isinstance(body.get("pid"), str):
        bad()
    if function == "void_receipt" and not isinstance(body.get("reason"), str):
        bad()
    if function == "attach_receipt_image":
        image_bytes(body.get("content_type"), body.get("data_base64"))
        if not isinstance(body.get("pid"), str) or not body["pid"].strip():
            bad()
    if function == "remove_receipt_image":
        if not positive_int(body.get("image_id")):
            bad()
        if not isinstance(body.get("reason"), str) or not body["reason"].strip():
            bad("IMAGE_REMOVE_REASON_REQUIRED", ERRORS["IMAGE_REMOVE_REASON_REQUIRED"][1])
    if function == "set_month_lock" and type(body.get("locked")) is not bool:
        bad()
    if function == "review_trip" and body.get("decision") not in ("confirm", "reject"):
        bad()
    if function == "review_trip" and (not isinstance(body.get("reason"), str) or not body["reason"].strip()):
        bad("REVIEW_REASON_REQUIRED", "Cần ghi lý do kết luận chuyến CHỜ KIỂM.")
    # Bảng giá: chỉ kiểm hình dạng; nội dung (ngày, giá, kho, chồng ngày) do save_price_table kiểm.
    if function == "save_price_table" and type(body.get("price_table")) is not dict:
        bad()
    if function == "apply_price_table":
        ids = body.get("trip_ids")
        if (type(ids) is not list or not 1 <= len(ids) <= 500
                or any(not positive_int(i) for i in ids) or len(set(ids)) != len(ids)):
            bad()
    return function, body


# GET: mỗi đường dẫn một hàm đọc chuỗi truy vấn và trả (hàm SQL, payload). Điều kiện kiểm giữ nguyên
# từ chuỗi if/elif cũ trong handle() (31/10/2026): đường không nhận tham số mà có tham số thì 404 như
# trước (rơi khỏi mọi nhánh); tham số sai dạng ở đường có tham số là 422.
def not_found() -> None:
    raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")


def _no_query(function: str):
    def parse(parts_query: str) -> tuple[str, dict]:
        if parts_query:
            not_found()
        return function, {}
    return parse


def _matrix(parts_query: str) -> tuple[str, dict]:
    query = parse_qs(parts_query, keep_blank_values=True)
    values = query.get("year")
    current_year = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).year
    if (set(query) != {"year"} or len(values or []) != 1
            or not re.fullmatch(r"[0-9]{4}", values[0] if values else "")
            or not 2000 <= int(values[0]) <= current_year + 1):
        bad("INVALID_YEAR", ERRORS["INVALID_YEAR"][1])
    return "get_receivables_matrix", {"year": int(values[0])}


def _detail(parts_query: str) -> tuple[str, dict]:
    query = parse_qs(parts_query, keep_blank_values=True)
    if (set(query) != {"customer", "month"} or len(query.get("customer", [])) != 1
            or len(query.get("month", [])) != 1
            or not re.fullmatch(r"[1-9][0-9]*", query["customer"][0])
            or len(query["customer"][0]) > 19 or int(query["customer"][0]) > MAX_BIGINT):
        bad()
    if not valid_date(query["month"][0], month=True):
        bad("INVALID_MONTH", ERRORS["INVALID_MONTH"][1])
    return "get_receivables_detail", {"customer_id": int(query["customer"][0]), "month": query["month"][0]}


def _sheet_queue(parts_query: str) -> tuple[str, dict]:
    query = parse_qs(parts_query, keep_blank_values=True)
    if query and (set(query) != {"customer"} or len(query["customer"]) != 1 or
                  not re.fullmatch(r"[1-9][0-9]*", query["customer"][0]) or
                  len(query["customer"][0]) > 19 or int(query["customer"][0]) > MAX_BIGINT):
        bad()
    return "list_customers", {}


def _receipt_images(parts_query: str, *, with_id: bool) -> tuple[str, dict]:
    query = parse_qs(parts_query, keep_blank_values=True)
    names = {"customer", "id"} if with_id else {"customer"}
    if set(query) != names or any(len(query[name]) != 1 or not re.fullmatch(r"[1-9][0-9]{0,18}", query[name][0])
                                  or int(query[name][0]) > MAX_BIGINT for name in names):
        bad()
    payload = {"customer_id": int(query["customer"][0])}
    if with_id:
        return "get_receipt_image", {**payload, "image_id": int(query["id"][0])}
    return "list_receipt_images", payload


def _find_image(parts_query: str) -> tuple[str, dict]:
    query = parse_qs(parts_query, keep_blank_values=True)
    if set(query) != {"sha256"} or len(query["sha256"]) != 1 or not re.fullmatch(r"[0-9a-f]{64}", query["sha256"][0]):
        bad()
    return "find_receipt_image", {"sha256": query["sha256"][0]}


def _by_customer(function: str, key: str):
    def parse(parts_query: str) -> tuple[str, dict]:
        query = parse_qs(parts_query, keep_blank_values=True)
        if set(query) != {"customer"} or len(query["customer"]) != 1 or not re.fullmatch(r"[1-9][0-9]*", query["customer"][0]):
            bad()
        customer_text = query["customer"][0]
        if len(customer_text) > 19 or (len(customer_text) == 19 and customer_text > str(MAX_BIGINT)):
            bad()
        return function, {key: int(customer_text)}
    return parse


GET_ROUTES = {
    "/api/v7/fee-types": _no_query("get_fee_types"),
    "/api/v7/dashboard": _no_query("get_dashboard"),
    "/api/v7/dashboard/debt": _no_query("get_dashboard_debt"),
    "/api/v7/reminders": _no_query("get_reminders"),
    "/api/v7/customers": _no_query("list_customers"),
    "/api/v7/receivables/matrix": _matrix,
    "/api/v7/receivables/detail": _detail,
    "/api/v7/sheet-queue": _sheet_queue,
    "/api/v7/receipt-images": lambda parts_query: _receipt_images(parts_query, with_id=False),
    "/api/v7/receipt-image": lambda parts_query: _receipt_images(parts_query, with_id=True),
    "/api/v7/receipt-images/find": _find_image,
    "/api/v7/ledger": _by_customer("get_ledger", "customer_id"),
    "/api/v7/offset-sources": _by_customer("list_offset_sources", "target_customer_id"),
    "/api/v7/price-table": _by_customer("get_price_table", "customer_id"),
    "/api/v7/price-table/status": _by_customer("get_price_status", "customer_id"),
}


def validate_get(path: str, parts_query: str) -> tuple[str, dict]:
    """Chuỗi truy vấn GET → (hàm SQL, payload); đường lạ là 404 như `validate()` của POST."""
    parse = GET_ROUTES.get(path)
    if parse is None:
        not_found()
    return parse(parts_query)
