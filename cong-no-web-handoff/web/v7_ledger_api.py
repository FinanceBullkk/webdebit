"""Trial-only V7 JSON API for an isolated test container, including CT-2SO."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer as HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import v7_identity
from v7_sheet_queue import build_queue, load_baseline, load_snapshot, project_customer

MAX_BODY = 64 * 1024
MAX_BIGINT = 9223372036854775807
PREVIEW = Path(__file__).resolve().parents[1] / "preview"
SHEET_SNAPSHOT_PATH = os.getenv("WEBDEBIT_SNAPSHOT_PATH", "/var/lib/webdebit-sheet-sync/snapshot.json")
SHEET_BASELINE_PATH = os.getenv("WEBDEBIT_BASELINE_REFS_PATH", "/var/lib/webdebit-sheet-sync/baseline-refs.json")
ASSETS = {
    "/": ("dashboard-v7.html", "text/html; charset=utf-8"),
    "/dashboard-v7.html": ("dashboard-v7.html", "text/html; charset=utf-8"),
    "/dashboard-v7.css": ("dashboard-v7.css", "text/css; charset=utf-8"),
    "/dashboard-v7.js": ("dashboard-v7.js", "text/javascript; charset=utf-8"),
    "/cong-no-theo-thang.html": ("cong-no-theo-thang.html", "text/html; charset=utf-8"),
    "/cong-no-theo-thang.css": ("cong-no-theo-thang.css", "text/css; charset=utf-8"),
    "/cong-no-theo-thang.js": ("cong-no-theo-thang.js", "text/javascript; charset=utf-8"),
    "/so-khach-v7-live.html": ("so-khach-v7-live.html", "text/html; charset=utf-8"),
    "/sheet-trip-queue.html": ("sheet-trip-queue-live.html", "text/html; charset=utf-8"),
    "/sheet-trip-queue-live.js": ("sheet-trip-queue-live.js", "text/javascript; charset=utf-8"),
    "/so-khach-v7-ui.js": ("so-khach-v7-ui.js", "text/javascript; charset=utf-8"),
    "/so-khach-v7-model.js": ("so-khach-v7-model.js", "text/javascript; charset=utf-8"),
    "/so-khach-v7-api.js": ("so-khach-v7-api.js", "text/javascript; charset=utf-8"),
}
ROUTES = {
    "/api/v7/offsets": ("record_offset", {"target_customer_id", "target_version", "source_customer_id", "source_version", "idempotency_key", "date", "amount_vnd", "reference"}),
    "/api/v7/offsets/void": ("void_offset", {"customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "reason"}),
    "/api/v7/offsets/date": ("edit_offset_date", {"customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "date"}),
    "/api/v7/trips/paste": ("paste_trips", {"debt_month", "trips"}),
    "/api/v7/trips/price": ("edit_trip_price", {"trip_id", "unit_price_vnd", "other_fee_vnd"}),
    "/api/v7/trips/adjust": ("adjust_trip", {"trip_id", "new_amount_vnd", "field", "new_value_vnd", "note"}),
    "/api/v7/months/adjust": ("adjust_month", {"debt_month", "amount_vnd", "note"}),
    "/api/v7/receipts": ("record_receipt", {"date", "method", "amount_vnd", "reference"}),
    "/api/v7/receipts/meta": ("edit_receipt_meta", {"pid", "date", "method", "reference"}),
    "/api/v7/receipts/void": ("void_receipt", {"pid", "reason"}),
    "/api/v7/months/lock": ("set_month_lock", {"month", "locked"}),
    "/api/v7/trips/review": ("review_trip", {"trip_id", "decision", "reason"}),
    "/api/v7/trips/info": ("edit_trip_info", {"trip_id", "field", "value"}),
    "/api/v7/trips/delete": ("delete_trip", {"trip_id"}),
    "/api/v7/legacy/edit": ("edit_legacy_trip", {"legacy_row_id", "field", "value"}),
    "/api/v7/legacy/delete": ("delete_legacy_trip", {"legacy_row_id"}),
}
COMMON = {"customer_id", "expected_version", "idempotency_key"}
TRIP_FIELDS = {"date", "booking", "container", "carrier", "shipper", "from", "to", "note", "src", "unitPriceVnd", "otherFeeVnd"}
ERRORS = {
    "INVALID_SHEET_RESOLUTION": (422, "Không thể xử lý ô này."),
    "INVALID_FIELD": (422, "Ô không được sửa."),
    "LEGACY_NOT_FOUND": (422, "Không tìm thấy dòng sổ gốc."),
    "LEGACY_NOT_TRIP": (422, "Dòng sổ gốc này là khoản thu, không sửa ở đây."),
    "STALE_LEDGER": (409, "Sổ đã thay đổi. Tải lại rồi thử tiếp."),
    "MONTH_LOCKED": (409, "Tháng đang khóa."),
    "IDEMPOTENCY_CONFLICT": (409, "Mã yêu cầu đã dùng cho nội dung khác."),
    "NO_BASELINE": (409, "Khách chưa có số dư đầu hiệu lực."),
    "RECEIPT_ALREADY_VOID": (409, "Phiếu đã hủy."),
    "NO_CHANGE": (409, "Nội dung không thay đổi."),
    "CUSTOMER_NOT_FOUND": (422, "Không tìm thấy khách."),
    "TRIP_NOT_FOUND": (422, "Không tìm thấy chuyến."),
    "TRIP_HAS_NO_PRICE": (422, "Chuyến chưa có giá."),
    "TRIP_PENDING_REVIEW": (409, "Chuyến chưa được tính vào sổ (CHỜ KIỂM hoặc đã loại)."),
    "TRIP_NOT_PENDING": (409, "Chuyến không còn CHỜ KIỂM."),
    "SHEET_CROSS_CUSTOMER_MATCH": (409, "Chuyến đã có ở khách khác. Tải lại để kiểm tra."),
    "REVIEW_REASON_REQUIRED": (422, "Cần ghi lý do kết luận chuyến CHỜ KIỂM."),
    "RECEIPT_NOT_FOUND": (422, "Không tìm thấy phiếu."),
    "MONTH_NOT_FOUND": (422, "Không tìm thấy tháng."),
    "NO_MONTH_FOR_RECEIPT": (422, "Chưa có tháng để ghi phiếu."),
    "VOID_REASON_REQUIRED": (422, "Cần ghi lý do hủy phiếu."),
    "FUTURE_RECEIPT_DATE": (422, "Ngày trả không được sau hôm nay."),
    "OFFSET_SAME_BOOK": (422, "Không thể cấn trừ cùng sổ."),
    "OFFSET_EXCEEDS_CREDIT": (422, "Số tiền vượt số dư được cấn trừ."),
    "OFFSET_SOURCE_ARCHIVED": (409, "Sổ nguồn đã lưu trữ."),
    "OFFSET_NOT_FOUND": (422, "Không tìm thấy cặp cấn trừ."),
    "OFFSET_PAIR_REQUIRED": (409, "Cần thao tác cả cặp cấn trừ."),
    "OFFSET_ALREADY_VOID": (409, "Cặp cấn trừ đã hủy."),
    "FUTURE_DATE": (422, "Ngày không được sau hôm nay."),
    "INVALID_DATE": (422, "Ngày không hợp lệ."),
    "INVALID_YEAR": (422, "Năm không hợp lệ."),
    "INVALID_MONTH": (422, "Tháng không hợp lệ."),
}
for _code in ("INVALID_VND", "INVALID_ADJUSTMENT", "INVALID_COMMAND", "INVALID_METHOD",
              "INVALID_MONTH", "INVALID_MONTH_LOCK", "INVALID_RECEIPT", "INVALID_TRIP",
              "INVALID_TRIP_DATE", "INVALID_TRIP_INPUT", "INVALID_TRIPS", "INVALID_REVIEW"):
    ERRORS[_code] = (422, "Dữ liệu nhập không hợp lệ.")


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
    for name in ("trip_id", "legacy_row_id"):
        if name in fields and (name not in body or not positive_int(body[name])):
            bad()
    for name in ("debt_month", "month"):
        if name in fields and (name not in body or not valid_date(body[name], month=True)):
            bad()
    if function in ("edit_trip_info", "edit_legacy_trip"):
        allowed = {"container", "carrier", "origin", "destination", "event_date", "unit_price_vnd", "other_fee_vnd"}
        if function == "edit_trip_info":
            allowed -= {"unit_price_vnd", "other_fee_vnd"}
        if not isinstance(body.get("field"), str) or body["field"] not in allowed:
            bad("INVALID_FIELD", ERRORS["INVALID_FIELD"][1])
        if "value" not in body or not isinstance(body["value"], str):
            bad()
        if body["field"] == "event_date" and not valid_date(body["value"]):
            bad("INVALID_DATE", ERRORS["INVALID_DATE"][1])
        if body["field"] in ("unit_price_vnd", "other_fee_vnd") and body["value"].strip() and not vnd(body["value"]):
            bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    if function == "adjust_trip":
        by_field = "field" in body or "new_value_vnd" in body
        if by_field:
            if (body.get("field") not in ("unit_price_vnd", "other_fee_vnd")
                    or not vnd(body.get("new_value_vnd")) or "new_amount_vnd" in body):
                bad()
        elif not vnd(body.get("new_amount_vnd")):
            bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
    for name in ("amount_vnd", "unit_price_vnd", "other_fee_vnd"):
        if name in fields and (name not in body or not vnd(body[name], signed=name == "amount_vnd" and function == "adjust_month",
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
                if name in trip_row and not vnd(trip_row[name], nullable=True):
                    bad("INVALID_VND", "Số tiền phải là chuỗi số nguyên VND.")
            if any(type(value) is not str and value is not None for value in trip_row.values()):
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
    if function == "set_month_lock" and type(body.get("locked")) is not bool:
        bad()
    if function == "review_trip" and body.get("decision") not in ("confirm", "reject"):
        bad()
    if function == "review_trip" and (not isinstance(body.get("reason"), str) or not body["reason"].strip()):
        bad("REVIEW_REASON_REQUIRED", "Cần ghi lý do kết luận chuyến CHỜ KIỂM.")
    return function, body


# Fixed SQL; psql :'payload' and :'actor' quote variable values as SQL literals.
SQL = {
    "list_offset_sources": "SELECT sokhach.list_offset_sources((:'payload'::jsonb->>'target_customer_id')::bigint);",
    "get_ledger": "SELECT sokhach.get_ledger((:'payload'::jsonb->>'customer_id')::bigint);",
    "list_customers": "SELECT sokhach.list_customers();",
    "get_dashboard": "SELECT sokhach.get_dashboard();",
    "get_receivables_matrix": "SELECT sokhach.get_receivables_matrix((:'payload'::jsonb->>'year')::int);",
    "get_receivables_detail": "SELECT sokhach.get_receivables_detail((:'payload'::jsonb->>'customer_id')::bigint,(:'payload'::jsonb->>'month')::date);",
    "list_sheet_trip_refs": "SELECT sokhach.list_sheet_trip_refs();",
    "resolve_sheet_conflict": "WITH j AS (SELECT :'payload'::jsonb AS p) SELECT sokhach.resolve_sheet_conflict((p->>'customer_id')::bigint,(p->>'expected_version')::bigint,p->>'idempotency_key',p->>'snapshot_sha256',(p->>'source_row')::bigint,p->>'target_kind',(p->>'target_id')::bigint,p->>'field',p->>'target_value',p->>'sheet_value',p->>'decision') FROM j;",
}
ARGUMENTS = {
    "record_offset": ("target_customer_id", "target_version", "source_customer_id", "source_version", "idempotency_key", "date", "amount_vnd", "reference"),
    "void_offset": ("customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "reason"),
    "edit_offset_date": ("customer_id", "expected_version", "other_version", "idempotency_key", "offset_pair_id", "date"),
    "paste_trips": ("debt_month", "trips"),
    "edit_trip_price": ("trip_id", "unit_price_vnd", "other_fee_vnd"),
    "adjust_trip": ("trip_id", "new_amount_vnd", "note", "field", "new_value_vnd"),
    "adjust_month": ("debt_month", "amount_vnd", "note"),
    "record_receipt": ("date", "method", "amount_vnd", "reference"),
    "edit_receipt_meta": ("pid", "date", "method", "reference"),
    "void_receipt": ("pid", "reason"),
    "set_month_lock": ("month", "locked"),
    "review_trip": ("trip_id", "decision", "reason"),
    "edit_trip_info": ("trip_id", "field", "value"),
    "delete_trip": ("trip_id",),
    "edit_legacy_trip": ("legacy_row_id", "field", "value"),
    "delete_legacy_trip": ("legacy_row_id",),
}
CAST = {"debt_month": "date", "month": "date", "date": "date", "trip_id": "bigint",
        "legacy_row_id": "bigint",
        "target_customer_id": "bigint", "target_version": "bigint", "source_customer_id": "bigint", "source_version": "bigint",
        "customer_id": "bigint", "expected_version": "bigint", "other_version": "bigint", "offset_pair_id": "bigint",
        "unit_price_vnd": "bigint", "other_fee_vnd": "bigint", "new_amount_vnd": "bigint",
        "amount_vnd": "bigint", "new_value_vnd": "bigint", "trips": "jsonb", "locked": "boolean"}
for _name, _fields in ARGUMENTS.items():
    _args = ["(j->>'customer_id')::bigint", "(j->>'expected_version')::bigint", "j->>'idempotency_key'"]
    if _name in ("record_offset", "void_offset", "edit_offset_date"):
        _args = []
    _args += [f"(j{'->' if field == 'trips' else '->>'}'{field}')::{CAST[field]}" if field in CAST
              else f"j->>'{field}'" for field in _fields]
    SQL[_name] = f"WITH b AS (SELECT :'payload'::jsonb AS j) SELECT sokhach.{_name}({', '.join(_args)}) FROM b;"


class _PsqlRunner:
    def _run_psql(
        self, argv: list[str], function: str, payload: dict, actor: str
    ) -> dict:
        sql = (
            "BEGIN;\nSET LOCAL sokhach.actor = :'actor';\n"
            + SQL[function]
            + "\nCOMMIT;\n"
        )
        env = os.environ.copy()
        env["PGOPTIONS"] = "-c statement_timeout=15000 -c lock_timeout=12000"
        try:
            result = subprocess.run(
                argv
                + [
                    "-v",
                    "payload="
                    + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    "-v",
                    "actor=" + actor,
                ],
                input=sql,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=25,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApiError(
                503,
                "DB_UNAVAILABLE"
                if function in ("get_ledger", "list_offset_sources")
                else "RESULT_UNKNOWN",
                "Sổ tạm thời không truy cập được."
                if function in ("get_ledger", "list_offset_sources")
                else "Chưa rõ lệnh đã lưu. Thử lại với cùng mã yêu cầu.",
            ) from exc
        except OSError as exc:
            raise ApiError(
                503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được."
            ) from exc
        if result.returncode:
            match = re.search(
                r"(?m)^psql:.*: ERROR:  P0001: ([A-Z_]+)\s*$", result.stderr
            )
            if match and match.group(1) in ERRORS:
                status, message = ERRORS[match.group(1)]
                extra = {}
                if match.group(1) == "OFFSET_EXCEEDS_CREDIT":
                    detail = re.search(r"(?m)^DETAIL:\s+(.*)$", result.stderr)
                    if detail:
                        try:
                            data = json.loads(
                                detail.group(1), object_pairs_hook=no_duplicates
                            )
                            if isinstance(data, dict) and vnd(
                                data.get("available_credit_vnd")
                            ):
                                extra["available_credit_vnd"] = data[
                                    "available_credit_vnd"
                                ]
                        except (ValueError, ApiError):
                            pass
                raise ApiError(status, match.group(1), message, extra)
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        try:
            return json.loads(result.stdout.strip())
        except ValueError as exc:
            raise ApiError(
                503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được."
            ) from exc


class Psql(_PsqlRunner):
    def __init__(self, container: str, database: str, user: str):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
            raise ValueError("invalid container name")
        if not all(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (database, user)
        ):
            raise ValueError("invalid database or user")
        try:
            inspected = subprocess.run(
                ["docker", "inspect", "--type=container", container],
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=8,
                check=True,
            )
            info = json.loads(inspected.stdout)[0]
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
            raise ValueError("test container unavailable") from exc
        labels = info.get("Config", {}).get("Labels") or {}
        if (
            labels.get("codex.test") != "webdebit-v7-backend"
            or not labels.get("codex.run")
            or info.get("HostConfig", {}).get("NetworkMode") != "none"
            or not re.fullmatch(r"[0-9a-f]{64}", info.get("Id", ""))
        ):
            raise ValueError("target is not isolated V7 test container")
        self.container, self.database, self.user = info["Id"], database, user

    def run(self, function: str, payload: dict, actor: str) -> dict:
        return self._run_psql(
            [
                "docker",
                "exec",
                "-i",
                "--env",
                "PGOPTIONS=-c statement_timeout=15000 -c lock_timeout=12000",
                self.container,
                "psql",
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                "VERBOSITY=verbose",
                "-U",
                self.user,
                "-d",
                self.database,
                "-f",
                "-",
            ],
            function,
            payload,
            actor,
        )


class PsqlDirect(_PsqlRunner):
    def __init__(
        self,
        socket_dir: str,
        database: str,
        role: str,
        *,
        psql_command: list[str] | None = None,
    ):
        if (
            not isinstance(socket_dir, str)
            or not socket_dir.startswith("/")
            or ":" in socket_dir
        ):
            raise ValueError("invalid socket directory")
        if role == "postgres" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
            raise ValueError("invalid role")
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database)
            or database == "webdebit_ledger"
        ):
            raise ValueError("invalid database")
        if "PGPASSWORD" in os.environ:
            raise ValueError("PGPASSWORD is forbidden")
        if "PGPASSFILE" in os.environ:
            p = Path(os.environ["PGPASSFILE"])
            if (
                p.is_symlink()
                or not p.is_file()
                or (os.name != "nt" and p.stat().st_mode & 0o177)
            ):
                raise ValueError("invalid PGPASSFILE")
        self.socket_dir, self.database, self.user = socket_dir, database, role
        self.psql_command = list(psql_command or ["psql"])
        probe = self.psql_command + [
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            socket_dir,
            "-U",
            role,
            "-d",
            database,
            "-c",
            "SELECT current_user='"
            + role
            + "' AND current_user=(SELECT rolname FROM pg_roles WHERE rolname=current_user AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls), EXISTS (SELECT 1 FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='get_ledger')",
        ]
        try:
            check = subprocess.run(
                probe,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env={**os.environ, "PGOPTIONS": "-c statement_timeout=15000 -c lock_timeout=12000"},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("direct database unavailable") from exc
        if check.returncode or check.stdout.strip() != "t|t":
            raise ValueError("direct database preflight rejected")

    def run(self, function: str, payload: dict, actor: str) -> dict:
        return self._run_psql(
            self.psql_command
            + [
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                "VERBOSITY=verbose",
                "-h",
                self.socket_dir,
                "-U",
                self.user,
                "-d",
                self.database,
                "-f",
                "-",
            ],
            function,
            payload,
            actor,
        )


def checked_host(value, port, host, behind_tailscale_serve=False, serve_hosts=()):
    if value.lower() in {f"127.0.0.1:{port}", f"localhost:{port}", f"{host}:{port}"}:
        return value.lower()
    if behind_tailscale_serve and value in serve_hosts:
        return value
    raise ApiError(400, "INVALID_HOST", "Địa chỉ truy cập không hợp lệ.")


def sheet_projection(runner: Psql, ledger: dict, actor: str) -> dict:
    snapshot = load_snapshot(SHEET_SNAPSHOT_PATH)
    baseline = load_baseline(SHEET_BASELINE_PATH)
    customers = runner.run("list_customers", {}, actor).get("customers", [])
    refs = runner.run("list_sheet_trip_refs", {}, actor).get("items")
    if not isinstance(refs, list):
        raise ValueError("web trip references unavailable")
    other_containers = set()
    for ref in refs:
        if not isinstance(ref, dict) or type(ref.get("customer_id")) is not int or not isinstance(ref.get("container"), str):
            raise ValueError("web trip references invalid")
        if ref["customer_id"] != ledger.get("customer_id"):
            other_containers.add("".join(ref["container"].upper().split()))
    return project_customer(build_queue(snapshot, customers, baseline), ledger, other_containers)


def approve_sheet(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    if not isinstance(request, dict) or set(request) != {"customer_id", "expected_version", "snapshot_sha256", "idempotency_key"}:
        bad()
    customer = request["customer_id"]
    version = request["expected_version"]
    digest = request["snapshot_sha256"]
    key = request["idempotency_key"]
    if (not positive_int(customer) or type(version) is not int or not 0 <= version <= MAX_BIGINT
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.strip()
            or any(ord(char) < 32 for char in key)):
        bad()
    ledger = runner.run("get_ledger", {"customer_id": customer}, actor)
    if ledger.get("status") != "active":
        raise ApiError(409, "NO_BASELINE", "Khách chưa có số dư đầu hiệu lực.")
    if ledger.get("version") != version:
        raise ApiError(409, "STALE_LEDGER", ERRORS["STALE_LEDGER"][1])
    try:
        projection = sheet_projection(runner, ledger, actor)
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", str(exc)) from exc
    if projection["snapshot_sha256"] != digest:
        raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi duyệt.")
    rows = [item for item in projection["items"] if item["sync_state"] == "NEW"]
    if not rows:
        return 200, {"approved": 0, "remaining": 0}
    months: dict[str, list[dict]] = {}
    for row in rows:
        month = row["event_date"][:7] + "-01"
        months.setdefault(month, []).append(row)
    approved = 0
    processed = 0
    pending = []
    # ponytail: commands are atomic per 200 rows/month; add one DB bulk function if cross-month atomicity becomes required.
    for month in sorted(months):
        values = sorted(months[month], key=lambda row: row["source_row"])
        for start in range(0, len(values), 200):
            batch = values[start:start + 200]
            trips = [{"date": row["event_date"][8:10] + "/" + row["event_date"][5:7] + "/" + row["event_date"][:4],
                      "booking": row.get("booking") or "", "container": row["container"], "carrier": row["carrier"],
                      "from": row["origin"], "to": row["destination"], "shipper": row.get("shipper"), "unitPriceVnd": None,
                      "otherFeeVnd": None, "note": "Chuyến đồng bộ",
                      "src": f"sheet:{digest}:{row['source_row']}"} for row in batch]
            command_key = hashlib.sha256(f"{key}:{digest}:{month}:{batch[0]['source_row']}".encode()).hexdigest()
            try:
                result = runner.run("paste_trips", {"customer_id": customer, "expected_version": version,
                                    "idempotency_key": command_key, "debt_month": month, "trips": trips}, actor)
            except ApiError as exc:
                if not processed:
                    raise
                return 200, {"approved": approved, "remaining": len(rows) - processed,
                             "review_count": len(pending), "complete": False, "error": exc.code}
            processed += len(batch)
            newly_pending = result.get("pending_review", [])
            pending.extend(newly_pending)
            approved += len(batch) - len(newly_pending)
            if processed < len(rows):
                version = runner.run("get_ledger", {"customer_id": customer}, actor)["version"]
    return 200, {"approved": approved, "remaining": 0, "complete": True,
                 "review_count": len(pending), "pending_review": pending}


def resolve_sheet_conflict(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    required = {"customer_id", "expected_version", "snapshot_sha256", "source_row",
                "target_kind", "target_id", "field", "decision", "idempotency_key"}
    if not isinstance(request, dict) or set(request) != required:
        bad("INVALID_SHEET_RESOLUTION")
    if (not positive_int(request["customer_id"]) or type(request["expected_version"]) is not int
            or not 0 <= request["expected_version"] <= MAX_BIGINT
            or not re.fullmatch(r"[0-9a-f]{64}", str(request["snapshot_sha256"]))
            or not positive_int(request["source_row"]) or not positive_int(request["target_id"])
            or request["target_kind"] not in ("trip", "legacy")
            or request["field"] not in ("carrier", "shipper", "origin", "destination")
            or request["decision"] not in ("keep_web", "use_sheet")
            or not isinstance(request["idempotency_key"], str)
            or not 1 <= len(request["idempotency_key"]) <= 128
            or not request["idempotency_key"].strip()
            or any(ord(char) < 32 for char in request["idempotency_key"])):
        bad("INVALID_SHEET_RESOLUTION")
    ledger = runner.run("get_ledger", {"customer_id": request["customer_id"]}, actor)
    if ledger.get("version") != request["expected_version"]:
        raise ApiError(409, "STALE_LEDGER", ERRORS["STALE_LEDGER"][1])
    try:
        projection = sheet_projection(runner, ledger, actor)
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", str(exc)) from exc
    if projection["snapshot_sha256"] != request["snapshot_sha256"]:
        raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi thử lại.")
    rows = [row for row in projection["items"] if row.get("sync_state") == "CONFLICT"
            and row.get("source_row") == request["source_row"]
            and row.get("existing_kind") == request["target_kind"]
            and row.get("existing_id") == request["target_id"]]
    if len(rows) != 1 or request["field"] not in rows[0].get("changed_fields", []):
        raise ApiError(409, "STALE_SHEET", "Dòng đối chiếu đã đổi. Tải lại rồi thử lại.")
    row = rows[0]
    sheet_value = row.get(request["field"])
    target_value = (row.get("existing_values") or {}).get(request["field"])
    if not isinstance(sheet_value, str) or (target_value is not None and not isinstance(target_value, str)):
        bad("INVALID_SHEET_RESOLUTION")
    try:
        if load_snapshot(SHEET_SNAPSHOT_PATH)["sha256"] != request["snapshot_sha256"]:
            raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi thử lại.")
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", str(exc)) from exc
    result = runner.run("resolve_sheet_conflict", {**request,
        "target_value": target_value, "sheet_value": sheet_value}, actor)
    return 200, {"resolved": True, "decision": request["decision"], "field": request["field"],
                 "version": result["version"]}


def handle(method: str, target: str, headers: dict[str, str], raw: bytes, runner: Psql, *,
           port: int, host: str, default_actor: str | None = None, actor: str | None = None,
           source_ip: str = "", source_port: int = 0, localapi=None, behind_tailscale_serve: bool = False,
           demo: bool = False, real_copy: bool = False, serve_hosts: tuple[str, ...] = ()) -> tuple[int, dict]:
    headers = {name.lower(): value for name, value in headers.items()}
    request_host = checked_host(headers.get("host", ""), port, host, behind_tailscale_serve, serve_hosts)
    if method == "POST":
        expected_origin = f"https://{request_host}" if behind_tailscale_serve and request_host in serve_hosts else f"http://{request_host}"
        if headers.get("origin") != expected_origin:
            raise ApiError(403, "INVALID_ORIGIN", "Nguồn yêu cầu không hợp lệ.")
        if headers.get("content-type", "").lower() != "application/json":
            raise ApiError(415, "INVALID_CONTENT_TYPE", "Cần gửi JSON.")
        if len(raw) > MAX_BODY:
            raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
        parts = urlsplit(target)
        if parts.query:
            bad()
        if parts.path == "/api/v7/sheet/approve":
            if actor is None:
                actor = v7_identity.resolve_actor(source_ip, headers, localapi, source_port=source_port,
                                                  behind_tailscale_serve=behind_tailscale_serve)
            return approve_sheet(raw, runner, actor)
        if parts.path == "/api/v7/sheet/resolve":
            if actor is None:
                actor = v7_identity.resolve_actor(source_ip, headers, localapi, source_port=source_port,
                                                  behind_tailscale_serve=behind_tailscale_serve)
            return resolve_sheet_conflict(raw, runner, actor)
        function, payload = validate(parts.path, raw)
    elif method == "GET":
        parts = urlsplit(target)
        if parts.path == "/api/v7/dashboard" and not parts.query:
            function, payload = "get_dashboard", {}
        elif parts.path == "/api/v7/receivables/matrix":
            query = parse_qs(parts.query, keep_blank_values=True)
            values = query.get("year")
            current_year = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).year
            if (set(query) != {"year"} or len(values or []) != 1
                    or not re.fullmatch(r"[0-9]{4}", values[0] if values else "")
                    or not 2000 <= int(values[0]) <= current_year + 1):
                bad("INVALID_YEAR", ERRORS["INVALID_YEAR"][1])
            function, payload = "get_receivables_matrix", {"year": int(values[0])}
        elif parts.path == "/api/v7/receivables/detail":
            query = parse_qs(parts.query, keep_blank_values=True)
            if (set(query) != {"customer", "month"} or len(query.get("customer", [])) != 1
                    or len(query.get("month", [])) != 1
                    or not re.fullmatch(r"[1-9][0-9]*", query["customer"][0])
                    or len(query["customer"][0]) > 19 or int(query["customer"][0]) > MAX_BIGINT):
                bad()
            if not valid_date(query["month"][0], month=True):
                bad("INVALID_MONTH", ERRORS["INVALID_MONTH"][1])
            function, payload = "get_receivables_detail", {"customer_id": int(query["customer"][0]), "month": query["month"][0]}
        elif parts.path == "/api/v7/sheet-queue":
            query = parse_qs(parts.query, keep_blank_values=True)
            if query and (set(query) != {"customer"} or len(query["customer"]) != 1 or
                          not re.fullmatch(r"[1-9][0-9]*", query["customer"][0]) or
                          len(query["customer"][0]) > 19 or int(query["customer"][0]) > MAX_BIGINT):
                bad()
            function, payload = "list_customers", {}
        elif parts.path == "/api/v7/customers" and not parts.query:
            function, payload = "list_customers", {}
        elif parts.path not in ("/api/v7/ledger", "/api/v7/offset-sources"):
            raise ApiError(404, "NOT_FOUND", "Không có đường dẫn này.")
        else:
            query = parse_qs(parts.query, keep_blank_values=True)
            if set(query) != {"customer"} or len(query["customer"]) != 1 or not re.fullmatch(r"[1-9][0-9]*", query["customer"][0]):
                bad()
            customer_text = query["customer"][0]
            if len(customer_text) > 19 or (len(customer_text) == 19 and customer_text > str(MAX_BIGINT)):
                bad()
            customer = int(customer_text)
            if parts.path == "/api/v7/offset-sources":
                function, payload = "list_offset_sources", {"target_customer_id": customer}
            else:
                function, payload = "get_ledger", {"customer_id": customer}
    else:
        raise ApiError(405, "METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ.")
    if actor is None:
        actor = v7_identity.resolve_actor(source_ip, headers, localapi, source_port=source_port,
                                          behind_tailscale_serve=behind_tailscale_serve)
    result = runner.run(function, payload, actor)
    if parts.path == "/api/v7/sheet-queue":
        try:
            snapshot = load_snapshot(SHEET_SNAPSHOT_PATH)
            baseline = load_baseline(SHEET_BASELINE_PATH)
        except ValueError as exc:
            raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", str(exc)) from exc
        queue = build_queue(snapshot, result.get("customers", []), baseline)
        if parts.query:
            customer = int(query["customer"][0])
            queue["items"] = [item for item in queue["items"] if item["customer_id"] == customer]
            queue["row_count"] = len(queue["items"])
            queue["review_count"] = queue["row_count"]
        return 200, queue
    if function == "get_ledger":
        try:
            result = {**result, "sheet_sync": sheet_projection(runner, result, actor)}
        except (ValueError, ApiError):
            result = {**result, "sheet_sync": {"unavailable": True, "items": [], "new_count": 0, "conflict_count": 0}}
    if function == "list_offset_sources":
        result = {"sources": result}
    if demo and function in ("get_ledger", "list_customers", "list_offset_sources", "get_dashboard", "get_receivables_matrix"):
        result = {**result, "demo": True}
    if real_copy and function in ("get_ledger", "list_customers", "list_offset_sources", "get_dashboard", "get_receivables_matrix"):
        result = {**result, "real_copy": True}
    return 200, result


class Handler(BaseHTTPRequestHandler):
    runner: Psql
    bind_host = "127.0.0.1"
    port = 8780
    default_actor = None
    dev_actor_mode = None
    behind_tailscale_serve = False
    serve_hosts: tuple[str, ...] = ()
    localapi = None
    demo = False
    real_copy = False

    def asset(self) -> bool:
        route = urlsplit(self.path).path
        if self.command != "GET" or route not in ASSETS:
            return False
        checked_host(self.headers.get("Host", ""), self.port, self.bind_host,
                     self.behind_tailscale_serve, self.serve_hosts)
        name, kind = ASSETS[route]
        data = (PREVIEW / name).read_bytes()
        self.send_response(200)
        for header, value in (("Content-Type", kind), ("Content-Length", str(len(data))),
                              ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
                              ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                              ("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                               "style-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")):
            self.send_header(header, value)
        self.end_headers()
        self.wfile.write(data)
        return True

    def reply(self, status: int, value: dict) -> None:
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        for name, field in (("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(data))),
                            ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff")):
            self.send_header(name, field)
        self.end_headers()
        self.wfile.write(data)

    def request(self) -> None:
        try:
            self.connection.settimeout(5)
            for name in ("Host", "Origin", "Content-Length", "Content-Type", "Tailscale-User-Login"):
                if len(self.headers.get_all(name, [])) > 1:
                    raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            if self.headers.get("Transfer-Encoding"):
                raise ApiError(400, "INVALID_REQUEST", "Dữ liệu gửi không hợp lệ.")
            checked_host(self.headers.get("Host", ""), self.port, self.bind_host,
                         self.behind_tailscale_serve, self.serve_hosts)
            actor = self.server.dev_actor
            if actor is None:
                actor = v7_identity.resolve_actor(self.client_address[0], self.headers, self.localapi,
                                                  source_port=self.client_address[1], behind_tailscale_serve=self.behind_tailscale_serve)
            if self.asset():
                return
            raw = b""
            if self.command == "POST":
                length = self.headers.get("Content-Length", "")
                if not length.isascii() or not length.isdecimal():
                    bad()
                length_value = int(length.lstrip("0") or "0") if len(length.lstrip("0")) <= len(str(MAX_BODY)) else MAX_BODY + 1
                if length_value > MAX_BODY:
                    raise ApiError(413, "BODY_TOO_LARGE", "Dữ liệu gửi quá lớn.")
                raw = self.rfile.read(length_value)
                if len(raw) != length_value:
                    bad()
            status, value = handle(self.command, self.path, dict(self.headers), raw, self.runner,
                                   port=self.port, host=self.bind_host, default_actor=self.default_actor,
                                   actor=actor, demo=self.demo, real_copy=self.real_copy,
                                   serve_hosts=self.serve_hosts, behind_tailscale_serve=self.behind_tailscale_serve)
            self.reply(status, value)
        except v7_identity.IdentityError as exc:
            self.reply(403, {"error": exc.code})
        except TimeoutError:
            self.reply(408, {"error": "REQUEST_TIMEOUT", "message": "Yêu cầu gửi quá chậm."})
        except ApiError as exc:
            self.reply(exc.status, {"error": exc.code, "message": exc.message, **exc.extra})
        except OSError:
            self.reply(503, {"error": "ASSET_UNAVAILABLE", "message": "Không đọc được trang thử."})

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = request

    def log_message(self, format: str, *args: object) -> None:
        pass


def loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class ThreadingHTTPServer(HTTPServer):
    def __init__(self, server_address, handler, *, default_actor=None, dev_actor_mode=None,
                 bind_and_activate=True):
        name = handler.default_actor if default_actor is None else default_actor
        mode = handler.dev_actor_mode if dev_actor_mode is None else dev_actor_mode
        # ponytail: legacy local tools opt in by named actor; remove after callers pass explicit mode.
        enabled = name is not None if mode is None else mode
        if (enabled or handler.behind_tailscale_serve) and not loopback(server_address[0]):
            raise ValueError("dev actor and Tailscale Serve require a loopback bind")
        self.dev_actor = None
        if enabled:
            if not isinstance(name, str) or not name.strip() or len(name) > 252 or any(ord(c) < 32 for c in name):
                raise ValueError("invalid dev actor")
            self.dev_actor = "dev:" + name.strip()
        super().__init__(server_address, handler, bind_and_activate=bind_and_activate)
        if enabled:
            print("WARNING: insecure dev actor enabled; identity verification bypassed (loopback only)", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.getenv("V7_API_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("V7_API_PORT", "8780"))
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--container")
    target.add_argument("--direct-socket-dir")
    parser.add_argument("--database")
    # ponytail: fake harness has no app EXECUTE grants; switch to v7_app after grants exist.
    parser.add_argument("--db-user")
    parser.add_argument(
        "--insecure-dev-actor", default=os.getenv("V7_API_INSECURE_DEV_ACTOR")
    )
    parser.add_argument(
        "--behind-tailscale-serve",
        action="store_true",
        default=os.getenv("V7_API_BEHIND_TAILSCALE_SERVE", "0") == "1",
        help="Trust identity supplied by Tailscale Serve on a loopback listener",
    )
    parser.add_argument("--serve-host", action="append", default=[],
                        help="Exact Host value accepted from Tailscale Serve; requires --behind-tailscale-serve")
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--demo", action="store_true", help="Mark GET snapshots as fake demo data"
    )
    source.add_argument(
        "--real-copy",
        action="store_true",
        help="Mark isolated real-data copy; not production",
    )
    args = parser.parse_args()
    if args.serve_host and not args.behind_tailscale_serve:
        parser.error("--serve-host requires --behind-tailscale-serve")
    for value in args.serve_host:
        try:
            port_value = urlsplit("//" + value).port or 443
        except ValueError:
            port_value = 0
        if not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]*(?::[1-9][0-9]{0,4})?", value) or not 1 <= port_value <= 65535:
            parser.error("--serve-host requires lowercase fqdn[:port]")
    if args.direct_socket_dir:
        if not args.database or args.database == "webdebit_ledger":
            parser.error("direct mode requires explicit non-legacy database")
        args.db_user = args.db_user or "v7_app"
    else:
        args.container = args.container or os.getenv("V7_API_CONTAINER")
        if not args.container:
            parser.error("one of --container or --direct-socket-dir is required")
        args.database = args.database or os.getenv(
            "V7_API_DATABASE", "webdebit_v7_test"
        )
        args.db_user = args.db_user or os.getenv("V7_API_DB_USER", "postgres")
    if args.port == 8777:
        parser.error("port 8777 belongs to the read-only opening app")
    # Trial API (DB user postgres) stays loopback-only; real access goes through tailscale serve -> loopback.
    if not loopback(args.host):
        parser.error("V7 trial API only binds loopback; expose it with tailscale serve")
    Handler.runner = (
        PsqlDirect(args.direct_socket_dir, args.database, args.db_user)
        if args.direct_socket_dir
        else Psql(args.container, args.database, args.db_user)
    )
    Handler.bind_host, Handler.port = args.host, args.port
    Handler.default_actor = args.insecure_dev_actor
    Handler.dev_actor_mode = args.insecure_dev_actor is not None
    Handler.behind_tailscale_serve = args.behind_tailscale_serve
    Handler.serve_hosts = tuple(args.serve_host)
    Handler.demo = args.demo
    Handler.real_copy = args.real_copy
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
