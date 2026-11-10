"""Bảng đối chiếu một khách ở Việc cần làm (VIEC-DOI-CHIEU-01, specs/v7-viec-can-lam-doi-chieu.md).

Đọc: số nợ web ± các khoản Sheet còn chờ = số nợ Sheet. Khoản lấy từ `v7_sheet_fix.plan`, tức đúng các nhóm máy đối soát đang xét.
Ghi: người chọn khoản rồi xác nhận, đi đúng đường của máy (`apply_fix`), người làm là người bấm. Server tính lại mọi khoản và so với
số người đã xem; khác thì không ghi gì. Không thêm hàm SQL.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from v7_api_sheet import (
    PRICE_SNAPSHOT_PATH,
    RECEIPT_SNAPSHOT_PATH,
    cached_load,
    customer_name_mapping,
    keep_sheet_task,
    named_customer,
)
from v7_api_tables import MAX_BIGINT
from v7_api_validate import ApiError, bad, no_duplicates, positive_int
from v7_inbox import _locked_months, in_month, reconcile_result
from v7_price_queue import load_price_snapshot
from v7_psql import Psql
from v7_receipt_queue import load_receipt_snapshot
from v7_sheet_fix import apply_fix, plan, price_delta

UNDOABLE = {"prices", "receipts", "receipts_no_date"}   # `undo_sheet_batch` chỉ khôi phục giá và phiếu
MAX_ROWS = 500
SHA = re.compile(r"[0-9a-f]{64}")
MONTH = re.compile(r"[0-9]{4}-[0-9]{2}")
PRICE_FIELDS = ("customer_tab", "status", "container", "date", "source_row", "web_unit_price_vnd", "web_other_fee_vnd",
                "sheet_unit_price_vnd", "sheet_other_fee_vnd", "source_fingerprint")
RECEIPT_FIELDS = ("customer_tab", "status", "source_row", "date", "debt_month", "amount_vnd", "note")


def _today():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def _key(row: dict[str, Any]) -> str:
    return f"{row['target_kind']}:{row['target_id']}"


def _group_id(group: dict[str, Any]) -> str:
    return f"{group['kind']}:{group['month'] or ''}"


def _read(customer: int, runner: Psql, actor: str) -> tuple[dict, dict, dict, list, int, list]:
    """(sổ, bản chụp giá, bản chụp phiếu, các nhóm, tiền web đi trước, tháng đơn giá đổi chỗ); giá và phiếu mới nhất của runner."""
    ledger = runner.run("get_ledger", {"customer_id": customer}, actor)
    try:
        prices = cached_load(load_price_snapshot, PRICE_SNAPSHOT_PATH)
        receipts = cached_load(load_receipt_snapshot, RECEIPT_SNAPSHOT_PATH)
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", "Không đọc được Sheet để đối chiếu.") from exc
    mapping = customer_name_mapping()
    customers = [named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    groups, ahead, shuffled = plan(prices, receipts, ledger, customers, _today())
    return ledger, prices, receipts, groups, ahead, shuffled


def _public_row(group: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    if group["kind"] == "prices":
        return {"key": _key(row), "delta_vnd": str(price_delta(row)), **{name: row.get(name) for name in PRICE_FIELDS}}
    if group["kind"] in ("receipts", "receipts_no_date", "receipts_edited"):
        return {name: row.get(name) for name in RECEIPT_FIELDS}
    return {name: row.get(name) for name in ("id", "source_row", "amount_vnd", "note")}


def statement(customer: int, runner: Psql, actor: str) -> dict[str, Any]:
    ledger, prices, receipts, groups, ahead, shuffled = _read(customer, runner, actor)
    result = reconcile_result() or {}
    row = next((r for r in result.get("customers") or [] if r.get("customer_id") == customer), {})
    return {"customer_id": customer, "version": ledger["version"], "web_vnd": str(ledger["total_outstanding_vnd"]),
            "sheet_total_vnd": row.get("sheet_total_vnd"), "checked_at": result.get("checked_at"), "reason": row.get("reason"),
            "sheet_editing": bool(row.get("sheet_editing")), "sheet_last_edit_at": row.get("sheet_last_edit_at"),
            "web_ahead_vnd": str(ahead), "shuffled_months": shuffled,
            "prices_sha256": prices["sha256"], "receipts_sha256": receipts["sha256"],
            "groups": [{"id": _group_id(group), "kind": group["kind"], "month": group["month"], "count": len(group["rows"]),
                        "delta_vnd": str(group["delta_vnd"]), "undoable": group["kind"] in UNDOABLE,
                        "locked": bool(group["month"] and _locked_months(ledger, {group["month"]})),
                        "replaces": len(group.get("orphans") or []),
                        "rows": [_public_row(group, row) for row in group["rows"]]} for group in groups if group["delta_vnd"]]}


def _body(raw: bytes, fields: set[str]) -> dict[str, Any]:
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    if not isinstance(request, dict) or set(request) != fields or not positive_int(request["customer_id"]) \
            or type(request["expected_version"]) is not int or not 0 <= request["expected_version"] <= MAX_BIGINT:
        bad()
    return request


def _idempotency(value: Any) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.strip() or any(ord(c) < 32 for c in value):
        bad()


def _pick(item: Any, groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Nhóm người đã chọn, sau khi kiểm số tiền đúng số người đã xem; `rows` chọn bớt chuyến trong nhóm giá."""
    if (not isinstance(item, dict) or set(item) != {"id", "delta_vnd", "rows"} or not isinstance(item["id"], str)
            or not isinstance(item["delta_vnd"], str) or not re.fullmatch(r"-?[0-9]+", item["delta_vnd"])):
        bad()
    group = groups.get(item["id"])
    if group is None:
        raise ApiError(409, "STALE_SHEET", "Khoản đã đổi. Tải lại rồi chọn lại.")
    if item["rows"] is not None:
        rows = item["rows"]
        if (group["kind"] != "prices" or type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS
                or not all(isinstance(key, str) for key in rows) or len(set(rows)) != len(rows)):
            bad()
        chosen = [row for row in group["rows"] if _key(row) in set(rows)]
        if len(chosen) != len(rows):
            raise ApiError(409, "STALE_SHEET", "Dòng giá đã đổi. Tải lại rồi chọn lại.")
        group = {**group, "rows": chosen, "delta_vnd": sum(price_delta(row) for row in chosen)}
    if str(group["delta_vnd"]) != item["delta_vnd"]:
        raise ApiError(409, "STALE_SHEET", "Số của khoản đã đổi. Tải lại rồi xem lại.")
    return group


def write(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    request = _body(raw, {"customer_id", "expected_version", "prices_sha256", "receipts_sha256", "items"})
    items = request["items"]
    if (type(items) is not list or not 1 <= len(items) <= 32
            or not all(isinstance(request[name], str) and SHA.fullmatch(request[name]) for name in ("prices_sha256", "receipts_sha256"))):
        bad()
    customer = request["customer_id"]
    ledger, prices, receipts, groups, _, _ = _read(customer, runner, actor)
    if ledger["version"] != request["expected_version"]:
        raise ApiError(409, "STALE_LEDGER", "Sổ vừa thay đổi. Tải lại rồi xem lại.")
    if prices["sha256"] != request["prices_sha256"] or receipts["sha256"] != request["receipts_sha256"]:
        raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi xem lại.")
    by_id = {_group_id(group): group for group in groups if group["delta_vnd"]}
    if len({item.get("id") if isinstance(item, dict) else None for item in items}) != len(items):
        bad()
    chosen = [_pick(item, by_id) for item in items]
    keys: list[str] = []
    done = apply_fix(runner, customer, ledger, chosen, prices["sha256"], _today(), actor=actor, undo_keys=keys)
    after = runner.run("get_ledger", {"customer_id": customer}, actor)
    undoable = all(group["kind"] in UNDOABLE for group in chosen) and keys
    months = sorted({group["month"] for group in chosen if group["month"]})
    return 200, {"complete": True, "version": after["version"], "before_vnd": str(ledger["total_outstanding_vnd"]),
                 "after_vnd": str(after["total_outstanding_vnd"]), "written": done,
                 "undo": {"command_keys": keys, "months": months} if undoable else None}


def keep(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Giữ số web cho nhiều dòng giá: từng dòng là một lệnh `keep_sheet_task`, gửi lại thì nhận kết quả cũ. Nợ không đổi."""
    request = _body(raw, {"customer_id", "expected_version", "idempotency_key", "rows"})
    _idempotency(request["idempotency_key"])
    rows = request["rows"]
    if (type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS or any(
            not isinstance(row, dict) or set(row) != {"target_kind", "target_id", "source_fingerprint"} for row in rows)):
        bad()
    version = request["expected_version"]
    for row in rows:
        target = f"{row['target_kind']}:{row['target_id']}"
        body = {"customer_id": request["customer_id"], "expected_version": version, "task_kind": "price",
                "idempotency_key": hashlib.sha256(f"{request['idempotency_key']}:{target}".encode()).hexdigest(), **row}
        keep_sheet_task(json.dumps(body).encode(), runner, actor)
        # Dòng đã giữ ở lần gửi trước trả kết quả cũ: phiên bản phải đọc lại, không lấy từ kết quả đó.
        version = runner.run("get_ledger", {"customer_id": request["customer_id"]}, actor)["version"]
    return 200, {"complete": True, "kept": len(rows), "version": version}


def undo(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Hoàn tác lần vừa ghi bằng `undo_sheet_batch`; tháng khóa thì mở, chạy, khóa lại như lúc ghi."""
    request = _body(raw, {"customer_id", "expected_version", "idempotency_key", "command_keys", "months"})
    _idempotency(request["idempotency_key"])
    keys, months = request["command_keys"], request["months"]
    if (type(keys) is not list or not 1 <= len(keys) <= 1000 or not all(isinstance(key, str) and SHA.fullmatch(key) for key in keys)
            or type(months) is not list or len(months) > 32 or not all(isinstance(month, str) and MONTH.fullmatch(month) for month in months)):
        bad()
    customer = request["customer_id"]
    ledger = runner.run("get_ledger", {"customer_id": customer}, actor)
    if ledger["version"] != request["expected_version"]:
        raise ApiError(409, "STALE_LEDGER", "Sổ đã đổi sau lần ghi. Mở sổ để sửa.")
    base = f"doi-chieu-hoan-tac:{customer}:{request['idempotency_key']}"

    def run(index: int, at: int) -> int:
        if index == len(months):
            result = runner.run("undo_sheet_batch", {"customer_id": customer, "expected_version": at, "command_keys": keys,
                                                     "idempotency_key": hashlib.sha256(base.encode()).hexdigest()}, actor)
            return result["version"] if type(result.get("version")) is int else runner.run("get_ledger", {"customer_id": customer}, actor)["version"]
        return in_month(runner, customer, at, ledger, months[index], base, lambda version: run(index + 1, version))
    version = run(0, ledger["version"])
    return 200, {"complete": True, "undone": len(keys), "version": version}
