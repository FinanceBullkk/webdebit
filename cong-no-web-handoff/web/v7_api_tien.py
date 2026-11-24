"""SO-TIEN P0-a lát 2: API sổ tiền `/api/v7/tien/*` (specs/so-tien-p0a-lat2.md, mục API).

Cờ `WEBDEBIT_TIEN` (off | shadow | on, đọc một lần lúc khởi động trong v7_ledger_api.main): off → mọi route 404 TIEN_OFF; shadow →
chỉ login có vai tien_review hoặc tien_quan_tri (ở đâu cũng được) dùng được, người khác 403 TIEN_FORBIDDEN; on → theo vai. Gọi hàm
schema `tien` qua runner riêng (login DB tien_api, thành viên tien_app; câu SQL đặt tien.actor/tien.actor_kind ở v7_api_tables).

Quyền thật nằm ở access_grant trong hàm SQL: route mở cho cả hai vai QUYEN-01; bot chỉ-đọc bị chặn ở mọi route kể cả GET
(v7_ledger_api giải danh tính với write=True cho đường dẫn này). Thân lệnh kiểm hình dạng ở đây (trường lạ, kiểu, độ dài) để DB không
nhận chuỗi lạ; hàm SQL kiểm lại và giữ mọi luật tiền. Tải file gốc, xuất Excel và mở lô có ô gốc ghi một dòng journal (login, việc,
mã đối tượng), không nội dung (NFR-03).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, quote
from zoneinfo import ZoneInfo

import v7_tien_import
import v7_tien_xlsx
from v7_api_tables import ERRORS, MAX_BIGINT
from v7_api_validate import ApiError, bad, no_duplicates

PREFIX = "/api/v7/tien"
PREVIEW_PATH = PREFIX + "/imports/preview"
MAX_PREVIEW_BODY = 6 * 1024 * 1024        # file ≤ 4 MiB thành base64 ~5,6 MB cộng vài trường
MODES = ("off", "shadow", "on")
SHADOW_ROLES = frozenset({"tien_review", "tien_quan_tri"})
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
KEY_LIMIT = 128
MAX_DECISIONS = 20000
MAX_ALLOCATION_LINES = 50
DAY = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
HASH = re.compile(r"[0-9a-f]{64}")
SIGNED = re.compile(r"0|-?[1-9][0-9]{0,17}")
POSITIVE = re.compile(r"[1-9][0-9]{0,17}")
TARGETS = ("ar_book", "customer_unapplied", "internal_transfer", "internal_transfer_pending", "cash_withdrawal", "bank_fee", "interest",
           "customer_funds_pending", "fleet", "expense_category", "other")
SOURCES = ("bank_pdf", "bank_app", "bank_paper", "other")
_N = r"([1-9][0-9]{0,17})"
GET_ROUTES = (
    (re.compile(r"/accounts"), "accounts"),
    (re.compile(rf"/accounts/{_N}"), "card"),
    (re.compile(rf"/accounts/{_N}/coverage"), "coverage"),
    (re.compile(rf"/accounts/{_N}/days/([0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}})"), "day"),
    (re.compile(rf"/accounts/{_N}/imports"), "imports"),
    (re.compile(rf"/accounts/{_N}/transactions"), "transactions"),
    (re.compile(rf"/imports/{_N}"), "import"),
    (re.compile(rf"/transactions/{_N}"), "transaction"),
)
FILE_ROUTE = re.compile(re.escape(PREFIX) + rf"/files/{_N}")
EXPORT_ROUTE = re.compile(re.escape(PREFIX) + rf"/accounts/{_N}/export\.xlsx")


@dataclass
class Config:
    mode: str = "off"
    runner: object | None = None   # None chỉ khi test: dùng runner truyền vào handle; máy thật luôn đặt runner login tien_api


CONFIG = Config()


def mode_from_env(value: str | None) -> str:
    """Giá trị lạ hay thiếu coi như off (thiếu cấu hình thì module tắt, NFR-02)."""
    return value if value in MODES else "off"


def under(path: str) -> bool:
    return path == PREFIX or path.startswith(PREFIX + "/")


def binary_route(path: str) -> bool:
    return FILE_ROUTE.fullmatch(path) is not None or EXPORT_ROUTE.fullmatch(path) is not None


def _log(actor: str, what: str, ref: object) -> None:
    print(f"SO-TIEN: {actor} {what} {ref}", file=sys.stderr, flush=True)


def _forbidden() -> ApiError:
    return ApiError(403, "TIEN_FORBIDDEN", ERRORS["TIEN_FORBIDDEN"][1])


def _runner(runner):
    if CONFIG.mode not in ("shadow", "on"):
        raise ApiError(404, "TIEN_OFF", ERRORS["TIEN_OFF"][1])
    return CONFIG.runner or runner


def _roles(db, actor: str) -> tuple[dict, set[str]]:
    access = db.run("tien_my_access", {}, actor, consistent=True)
    return access, {g["role"] for g in access["grants"]}


def _gate(db, actor: str) -> None:
    if CONFIG.mode == "shadow" and not _roles(db, actor)[1] & SHADOW_ROLES:
        raise _forbidden()


# ---- kiểm thân lệnh và tham số ---------------------------------------------------------------------------------------------

def _body(raw: bytes) -> dict:
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_float=lambda _: bad(), parse_constant=lambda _: bad())
    except (UnicodeError, ValueError, TypeError, RecursionError):
        bad()
    if not isinstance(body, dict):
        bad()
    return body


def _fields(body: dict, required: set[str], optional: frozenset[str] | set[str] = frozenset()) -> None:
    if not required <= set(body) <= required | optional | {"idempotency_key"} or "idempotency_key" not in body:
        bad()
    key = body["idempotency_key"]
    if not isinstance(key, str) or not 1 <= len(key) <= KEY_LIMIT or not key.strip() or any(ord(c) < 32 for c in key):
        bad()


def _id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_BIGINT:
        bad()
    return value


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_BIGINT:
        bad()
    return value


def _day(value: object) -> str:
    if not isinstance(value, str) or not DAY.fullmatch(value):
        bad()
    try:
        date.fromisoformat(value)
    except ValueError:
        bad()
    return value


def _text(value: object, limit: int, *, optional: bool = True) -> None:
    if value is None and optional:
        return
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        bad()


def _query(query: str, allowed: set[str]) -> dict[str, str]:
    try:
        values = parse_qs(query, keep_blank_values=True, strict_parsing=bool(query))
    except ValueError:
        bad()
    if not set(values) <= allowed or any(len(v) != 1 for v in values.values()):
        bad()
    return {key: value[0] for key, value in values.items()}


def _range(q: dict[str, str], *, default_days: int, max_days: int) -> tuple[str, str]:
    """Khoảng ngày của tham số from/to; thiếu thì tới hôm nay (giờ VN), lùi default_days ngày."""
    end = _day(q["to"]) if "to" in q else datetime.now(VN).date().isoformat()
    start = _day(q["from"]) if "from" in q else (date.fromisoformat(end) - timedelta(days=default_days)).isoformat()
    if start > end or (date.fromisoformat(end) - date.fromisoformat(start)).days > max_days:
        bad()
    return start, end


# ---- đọc -------------------------------------------------------------------------------------------------------------------

def _me(db, actor: str) -> dict:
    access, roles = _roles(db, actor)
    visible = bool(roles) if CONFIG.mode == "on" else bool(roles & SHADOW_ROLES)
    return {"mode": CONFIG.mode, "visible": visible, "actor": access["actor"], "grants": access["grants"] if visible else [],
            "templates": [{"id": t.id, "label": t.label, "media_type": t.media_type, "extension": t.extension}
                          for t in v7_tien_import.available()]}


def _get(rest: str, query: str, db, actor: str) -> dict:
    found = next(((match, name) for pattern, name in GET_ROUTES if (match := pattern.fullmatch(rest))), None)
    if found is None:
        raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")
    match, name = found
    if name in ("coverage", "transactions"):
        q = _query(query, {"from", "to"})
    else:
        _query(query, set())
    def read(function: str, payload: dict) -> dict:
        return db.run(function, payload, actor, consistent=True)

    if name == "accounts":
        return read("tien_list_accounts", {})
    ref = int(match[1])
    if name == "card":
        return read("tien_get_account_card", {"account_id": ref})
    if name == "coverage":
        start, end = _range(q, default_days=44, max_days=92)
        return read("tien_get_coverage", {"account_id": ref, "from": start, "to": end})
    if name == "day":
        return read("tien_get_day", {"account_id": ref, "date": _day(match[2])})
    if name == "imports":
        return read("tien_list_imports", {"account_id": ref})
    if name == "transactions":
        start, end = _range(q, default_days=30, max_days=366)
        return read("tien_list_transactions", {"account_id": ref, "from": start, "to": end})
    if name == "import":
        result = read("tien_get_import", {"import_id": ref})
        if result.get("raw_visible"):
            _log(actor, "mở lô có ô gốc", ref)
        return result
    return read("tien_get_transaction", {"transaction_id": ref})


# ---- ghi -------------------------------------------------------------------------------------------------------------------

def _file_name(value: object) -> str:
    if not isinstance(value, str):
        bad()
    name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 200 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        bad()
    return name


def _preview(raw: bytes, db, actor: str) -> dict:
    body = _body(raw)
    _fields(body, {"account_id", "template", "file_name", "content_base64"})
    account = _id(body["account_id"])
    template = v7_tien_import.get(body["template"])
    if template is None:
        raise ApiError(422, "TEMPLATE_UNKNOWN", ERRORS["TEMPLATE_UNKNOWN"][1])
    name = _file_name(body["file_name"])
    encoded = body["content_base64"]
    if not isinstance(encoded, str) or len(encoded) > (v7_tien_import.MAX_FILE_BYTES + 2) // 3 * 4 + 4:
        raise ApiError(413, "FILE_TOO_LARGE", ERRORS["FILE_TOO_LARGE"][1])
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        bad()
    if not data:
        bad()
    if len(data) > v7_tien_import.MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", ERRORS["FILE_TOO_LARGE"][1])
    # Tiền tệ từng dòng là tiền tệ của tài khoản; đọc thẻ cũng kiểm người gửi có vai ở tài khoản trước khi đọc file.
    currency = db.run("tien_get_account_card", {"account_id": account}, actor, consistent=True)["account"]["currency"]
    try:
        parsed = template.parse(data, currency)
    except v7_tien_import.ParseError as exc:
        raise ApiError(422, "IMPORT_PARSE_ERROR", exc.message, {} if exc.line is None else {"line": exc.line}) from exc
    payload = {"idempotency_key": body["idempotency_key"], "account_id": account, "file_sha256": hashlib.sha256(data).hexdigest(),
               "template": template.id, "period_from": parsed.period_from, "period_to": parsed.period_to,
               "last_day_complete": parsed.last_day_complete, "opening_minor": parsed.opening_minor,
               "closing_minor": parsed.closing_minor, "lines": parsed.lines,
               "file": {"name": name, "media_type": template.media_type, "content_base64": base64.b64encode(data).decode("ascii")}}
    return db.run("tien_preview_import", payload, actor)


def _check_commit(body: dict) -> None:
    _id(body["import_id"])
    if not isinstance(body["expected_preview_hash"], str) or not HASH.fullmatch(body["expected_preview_hash"]):
        bad()
    decisions, keep = body.get("suspect_decisions", []), body.get("keep_existing", [])
    if not isinstance(decisions, list) or not isinstance(keep, list) or len(decisions) + len(keep) > MAX_DECISIONS:
        bad()
    for item in decisions:
        if not isinstance(item, dict) or not {"line_no", "decision"} <= set(item) <= {"line_no", "decision", "transaction_id"}:
            bad()
        _id(item["line_no"])
        if item["decision"] not in ("new", "duplicate_of") or (item["decision"] == "duplicate_of") != ("transaction_id" in item):
            bad()
        if "transaction_id" in item:
            _id(item["transaction_id"])
    for item in keep:
        if not isinstance(item, dict) or not {"transaction_id"} <= set(item) <= {"transaction_id", "reason"}:
            bad()
        _id(item["transaction_id"])
        _text(item.get("reason"), 500)


def _check_reason(body: dict) -> None:
    _id(body["import_id"])
    _text(body.get("reason"), 500)


def _check_allocation(body: dict) -> None:
    _id(body["transaction_id"])
    _count(body["expected_version"])
    _text(body.get("reason"), 500)
    lines = body["lines"]
    if not isinstance(lines, list) or len(lines) > MAX_ALLOCATION_LINES:
        bad()
    for line in lines:
        if not isinstance(line, dict) or not {"target_kind", "target_ref", "amount_minor"} <= set(line) <= {
                "target_kind", "target_ref", "amount_minor", "note"}:
            bad()
        if line["target_kind"] not in TARGETS or not isinstance(line["amount_minor"], str) or not POSITIVE.fullmatch(line["amount_minor"]):
            bad()
        ref = line["target_ref"]
        if not isinstance(ref, dict) or len(ref) > 4 or any(not isinstance(k, str) or len(k) > 40 for k in ref):
            bad()
        for value in ref.values():
            if isinstance(value, bool) or not isinstance(value, (str, int)) or (isinstance(value, str) and len(value) > 200):
                bad()
        _text(line.get("note"), 500)


def _check_evidence(body: dict) -> None:
    _id(body["account_id"])
    _day(body["as_of_date"])
    if not isinstance(body["amount_minor"], str) or not SIGNED.fullmatch(body["amount_minor"]) or body["source"] not in SOURCES:
        bad()
    _text(body.get("note"), 500)


def _check_day(body: dict) -> None:
    _id(body["account_id"])
    _day(body["business_date"])
    if "expected_version" in body:
        _count(body["expected_version"])
    if "track" in body and body["track"] not in ("coverage", "business"):
        bad()
    _text(body.get("note"), 500)
    _text(body.get("reason"), 500)


def _write(function: str, required: set[str], check, optional: frozenset[str] = frozenset()):
    def handler(raw: bytes, db, actor: str) -> dict:
        body = _body(raw)
        _fields(body, required, optional)
        check(body)
        return db.run("tien_" + function, body, actor)
    return handler


POST_HANDLERS = {
    "/imports/preview": _preview,
    "/imports/commit": _write("commit_import", {"import_id", "expected_preview_hash"}, _check_commit,
                              frozenset({"suspect_decisions", "keep_existing"})),
    "/imports/reject": _write("reject_import", {"import_id"}, _check_reason, frozenset({"reason"})),
    "/imports/void": _write("void_import", {"import_id"}, _check_reason, frozenset({"reason"})),
    "/allocations": _write("set_allocation", {"transaction_id", "expected_version", "lines"}, _check_allocation,
                           frozenset({"reason"})),
    "/balance-evidence": _write("record_balance_evidence", {"account_id", "as_of_date", "amount_minor", "source"},
                                _check_evidence, frozenset({"note"})),
    "/days/sign-coverage": _write("sign_day_coverage", {"account_id", "business_date", "expected_version"}, _check_day,
                                  frozenset({"note"})),
    "/days/sign-business": _write("sign_day_business", {"account_id", "business_date"}, _check_day, frozenset({"note"})),
    "/days/reopen": _write("reopen_day", {"account_id", "business_date", "track"}, _check_day, frozenset({"reason"})),
}


def handle(method: str, path: str, query: str, raw: bytes, runner, actor: str) -> tuple[int, dict]:
    """GET và POST JSON của /api/v7/tien (v7_ledger_api đã kiểm Host, Origin, Content-Type, cỡ thân và giải danh tính)."""
    db = _runner(runner)
    rest = path[len(PREFIX):]
    if method == "GET":
        if rest == "/me":
            _query(query, set())
            return 200, _me(db, actor)
        _gate(db, actor)
        return 200, _get(rest, query, db, actor)
    handler = POST_HANDLERS.get(rest)
    if handler is None:
        raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")
    _gate(db, actor)
    return 200, handler(raw, db, actor)


def binary(path: str, query: str, runner, actor: str) -> tuple[str, str, bytes]:
    """(Content-Type, tên file, byte) của file gốc hoặc file Excel; cùng cờ, cổng shadow và quyền SQL như route JSON."""
    db = _runner(runner)
    _gate(db, actor)
    match = FILE_ROUTE.fullmatch(path)
    if match:
        _query(query, set())
        found = db.run("tien_get_statement_file", {"file_id": int(match[1])}, actor, consistent=True)
        data = base64.b64decode(found["content_base64"])
        if hashlib.sha256(data).hexdigest() != found["file_sha256"]:
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        _log(actor, "tải file gốc", f"{found['id']} (tài khoản {found['account_id']})")
        return found["media_type"], found["file_name"], data
    match = EXPORT_ROUTE.fullmatch(path)
    if match is None:
        raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")
    start, end = _range(_query(query, {"from", "to"}), default_days=30, max_days=365)
    rows = db.run("tien_export_rows", {"account_id": int(match[1]), "from": start, "to": end}, actor, consistent=True)
    try:
        filename, data = v7_tien_xlsx.build(rows)
    except (v7_tien_xlsx.ExportError, KeyError, TypeError, ValueError) as exc:
        print(f"SO-TIEN: {actor} xuất Excel lỗi {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise ApiError(503, "EXPORT_FAILED", "Chưa xuất được file Excel. Báo quản trị kiểm.") from exc
    _log(actor, "xuất Excel", f"tài khoản {match[1]} {start}..{end}")
    return XLSX_TYPE, filename, data


def disposition(filename: str) -> str:
    """Content-Disposition tải về: tên ASCII cho trình duyệt cũ + filename* UTF-8 (RFC 6266) cho tên có dấu."""
    plain = "".join(c if c.isascii() and (c.isalnum() or c in "._-") else "_" for c in filename) or "tep"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename, safe='')}"
