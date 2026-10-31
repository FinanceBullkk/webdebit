"""Đồng bộ Sheet/PS → sổ web của API V7: chiếu hàng chờ (chuyến, giá, phiếu thu, phụ phí PS), duyệt theo lô, xử lý xung đột, yêu cầu lấy Sheet.

Đường ghi vẫn là các hàm `sokhach.*` qua runner; module này chỉ chọn hàng NEW/READY và gọi từng
lệnh với khóa idempotency riêng. Tách từ `v7_ledger_api.py` 31/10/2026: bốn hàm `approve_*` dùng
chung `approve_request`, phần còn lại giữ nguyên. Đường snapshot và các hàm chiếu là biến toàn cục
của module này: test muốn vá (patch) thì vá ở đây, không vá bản re-export trong `v7_ledger_api`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import v7_sheet_refresh
from v7_api_tables import ERRORS, MAX_BIGINT
from v7_api_validate import ApiError, bad, no_duplicates, positive_int
from v7_price_queue import load_price_snapshot, project_prices
from v7_ps_queue import load_ps_snapshot, project_ps
from v7_psql import Psql
from v7_receipt_queue import METHOD as RECEIPT_METHOD
from v7_receipt_queue import load_receipt_snapshot, project_receipts
from v7_receipt_queue import reference as receipt_reference
from v7_sheet_queue import build_queue, load_baseline, load_snapshot, project_customer

SHEET_SNAPSHOT_PATH = os.getenv("WEBDEBIT_SNAPSHOT_PATH", "/var/lib/webdebit-sheet-sync/snapshot.json")
PRICE_SNAPSHOT_PATH = os.getenv("WEBDEBIT_PRICE_SNAPSHOT_PATH", "/var/lib/webdebit-sheet-sync/prices.json")
PS_SNAPSHOT_PATH = os.getenv("WEBDEBIT_PS_SNAPSHOT_PATH", "/var/lib/webdebit-sheet-sync/ps.json")
# Runner giá ghi phiếu thu cạnh prices.json (THU-SHEET-01), nên mặc định đi theo đường giá.
RECEIPT_SNAPSHOT_PATH = os.getenv("WEBDEBIT_RECEIPT_SNAPSHOT_PATH") or str(Path(PRICE_SNAPSHOT_PATH).with_name("receipts.json"))
SHEET_REFRESH_PATH = os.getenv("WEBDEBIT_SHEET_REFRESH_PATH")   # chưa đặt: nút Làm mới không đọc Sheet
SHEET_BASELINE_PATH = os.getenv("WEBDEBIT_BASELINE_REFS_PATH", "/var/lib/webdebit-sheet-sync/baseline-refs.json")
CUSTOMER_NAME_MAPPING_PATH = os.getenv("WEBDEBIT_CUSTOMER_NAME_MAPPING_PATH")


def customer_name_mapping() -> dict[str, dict]:
    if not CUSTOMER_NAME_MAPPING_PATH:
        return {}
    try:
        data = json.loads(Path(CUSTOMER_NAME_MAPPING_PATH).read_text(encoding="utf-8"))
        if type(data) is not dict or data.get("version") != 1 or type(data.get("customers")) is not dict:
            raise ValueError("invalid mapping format")
        for key, entry in data["customers"].items():
            if not re.fullmatch(r"[1-9][0-9]*", key) or int(key) > MAX_BIGINT or type(entry) is not dict:
                raise ValueError("invalid customer id")
            if any(type(entry.get(field)) is not str or not entry[field].strip() or len(entry[field]) > 200
                   for field in ("v7_name",)) or ("display_name" in entry and
                   (type(entry["display_name"]) is not str or not entry["display_name"].strip() or
                    len(entry["display_name"]) > 200)):
                raise ValueError("invalid customer name")
            aliases = entry.get("aliases", [])
            if type(aliases) is not list or any(type(alias) is not str or not alias.strip() or len(alias) > 200
                                               for alias in aliases):
                raise ValueError("invalid aliases")
            if "commodity" in entry and (type(entry["commodity"]) is not str or
                                         not entry["commodity"].strip() or len(entry["commodity"]) > 80):
                raise ValueError("invalid commodity")
            if "transport_mode" in entry and entry["transport_mode"] not in ("CANG", "BO"):
                raise ValueError("invalid transport mode")
        return data["customers"]
    except (OSError, UnicodeError, ValueError, TypeError):
        # Display metadata must never block reading a ledger.
        return {}


def named_customer(row: dict, mapping: dict[str, dict]) -> dict:
    entry = mapping.get(str(row["id"]))
    if not entry:
        return row
    if row["name"] != entry["v7_name"]:
        return row
    result = {**row, "aliases": entry.get("aliases", [])}
    if entry.get("display_name"):
        result["display_name"] = entry["display_name"]
    if row.get("commodity") is None and entry.get("commodity_review") == "OK" and entry.get("commodity"):
        result["commodity"] = entry["commodity"]
        if row.get("transport_mode") is None and entry.get("transport_mode"):
            result["transport_mode"] = entry["transport_mode"]
    return result


def with_display_names(customers: dict) -> dict:
    """`GET /api/v7/customers`: gắn tên hiển thị và tên khác từ bảng ánh xạ; id và tên V7 không đổi."""
    mapping = customer_name_mapping()
    return {**customers, "customers": [named_customer(row, mapping) for row in customers.get("customers", [])]}


def sheet_queue(customers: dict, parts_query: str) -> dict:
    """`GET /api/v7/sheet-queue`: hàng chờ chuyến từ Sheet cho mọi khách, hoặc một khách theo `?customer=` đã kiểm."""
    try:
        snapshot = load_snapshot(SHEET_SNAPSHOT_PATH)
        baseline = load_baseline(SHEET_BASELINE_PATH)
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", str(exc)) from exc
    queue = build_queue(snapshot, customers.get("customers", []), baseline)
    if parts_query:
        customer = int(parse_qs(parts_query, keep_blank_values=True)["customer"][0])
        queue["items"] = [item for item in queue["items"] if item["customer_id"] == customer]
        queue["row_count"] = len(queue["items"])
        queue["review_count"] = queue["row_count"]
    return queue


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


def approve_request(raw: bytes, runner: Psql, actor: str) -> tuple[int, int, str, str, dict]:
    """Phần chung của bốn lệnh duyệt theo lô: đọc thân JSON, kiểm đúng bốn trường, đọc sổ, so trạng thái và phiên bản.

    Trả (customer_id, expected_version, snapshot_sha256, idempotency_key, sổ); mọi lỗi ném `ApiError`
    đúng như bốn bản chép tay trước khi gộp (31/10/2026).
    """
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    if not isinstance(request, dict) or set(request) != {"customer_id", "expected_version", "snapshot_sha256", "idempotency_key"}:
        bad()
    customer, version = request["customer_id"], request["expected_version"]
    digest, key = request["snapshot_sha256"], request["idempotency_key"]
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
    return customer, version, digest, key, ledger


def approve_sheet(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    customer, version, digest, key, ledger = approve_request(raw, runner, actor)
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


def price_projection(runner: Psql, ledger: dict, actor: str) -> dict:
    snapshot = load_price_snapshot(PRICE_SNAPSHOT_PATH)
    mapping = customer_name_mapping()
    customers = [named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    return project_prices(snapshot, ledger, customers)


def approve_prices(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Write every READY Sheet price of one customer through the existing price commands."""
    customer, version, digest, key, ledger = approve_request(raw, runner, actor)
    try:
        projection = price_projection(runner, ledger, actor)
    except ValueError as exc:
        raise ApiError(503, "SHEET_PRICES_UNAVAILABLE", "Không đọc được giá từ Sheet.") from exc
    if projection["snapshot_sha256"] != digest:
        raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi ghi.")
    written = commands_done = 0
    for item in projection["ready"]:
        price, fee = str(item["sheet_unit_price_vnd"]), item["sheet_other_fee_vnd"]
        if item["target_kind"] == "trip":
            commands = [("edit_trip_price", {"trip_id": item["target_id"], "unit_price_vnd": price,
                                             "other_fee_vnd": None if fee is None else str(fee)})]
        else:
            commands = []
            if item.get("web_unit_price_vnd") is None or str(item["web_unit_price_vnd"]) != price:
                commands.append(("edit_legacy_trip", {"legacy_row_id": item["target_id"],
                                                     "field": "unit_price_vnd", "value": price}))
            if fee is not None:
                commands.append(("edit_legacy_trip", {"legacy_row_id": item["target_id"], "field": "other_fee_vnd",
                                                      "value": str(fee)}))
        for function, fields in commands:
            # One key per target and field: a repeated click replays the stored result, never a second write.
            command_key = hashlib.sha256(
                f"{key}:{digest}:{item['target_kind']}:{item['target_id']}:{fields.get('field', 'price')}".encode()).hexdigest()
            try:
                result = runner.run(function, {"customer_id": customer, "expected_version": version,
                                               "idempotency_key": command_key, **fields}, actor)
            except ApiError as exc:
                if exc.code == "FEE_LINES_TYPED":
                    return 200, {"written": written, "remaining": len(projection["ready"]) - written,
                                 "complete": False, "error": exc.code,
                                 "review": [{**item, "status": "MANUAL"}]}
                if not commands_done:
                    raise   # nothing written yet: a plain error, same as one price edit
                return 200, {"written": written, "remaining": len(projection["ready"]) - written,
                             "complete": False, "error": exc.code}
            version = result["version"] if type(result.get("version")) is int else                 runner.run("get_ledger", {"customer_id": customer}, actor)["version"]
            commands_done += 1
        written += 1
    return 200, {"written": written, "remaining": 0, "complete": True, "version": version}


def receipt_projection(runner: Psql, ledger: dict, actor: str) -> dict:
    snapshot = load_receipt_snapshot(RECEIPT_SNAPSHOT_PATH)
    mapping = customer_name_mapping()
    customers = [named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    return project_receipts(snapshot, ledger, customers, datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date())


def approve_receipts(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Record every READY Sheet receipt of one customer through record_receipt (THU-SHEET-01)."""
    customer, version, digest, key, ledger = approve_request(raw, runner, actor)
    try:
        projection = receipt_projection(runner, ledger, actor)
    except ValueError as exc:
        raise ApiError(503, "SHEET_RECEIPTS_UNAVAILABLE", "Không đọc được phiếu thu từ Sheet.") from exc
    if projection["snapshot_sha256"] != digest:
        raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi ghi.")
    written = 0
    for item in projection["ready"]:
        # One key per Sheet receipt: a repeated click replays the stored result, never a second receipt.
        command_key = hashlib.sha256(
            f"{key}:{digest}:{item['customer_tab']}:{item['source_row']}:{item['amount_vnd']}:{item['date']}".encode()).hexdigest()
        try:
            result = runner.run("record_receipt", {
                "customer_id": customer, "expected_version": version, "idempotency_key": command_key,
                "date": item["date"], "method": RECEIPT_METHOD, "amount_vnd": item["amount_vnd"],
                "reference": receipt_reference(item["note"])}, actor)
        except ApiError as exc:
            if not written:
                raise   # nothing written yet: a plain error, same as one receipt
            # Each receipt stands alone; the rest stays READY and the next read matches what was written.
            return 200, {"written": written, "remaining": len(projection["ready"]) - written,
                         "complete": False, "error": exc.code}
        version = result["version"] if type(result.get("version")) is int else \
            runner.run("get_ledger", {"customer_id": customer}, actor)["version"]
        written += 1
    return 200, {"written": written, "remaining": 0, "complete": True, "version": version}


def ps_projection(runner: Psql, ledger: dict, actor: str) -> dict:
    snapshot = load_ps_snapshot(PS_SNAPSHOT_PATH)
    mapping = customer_name_mapping()
    customers = [named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    return project_ps(snapshot, ledger, customers, runner.run("get_fee_types", {}, actor).get("fee_types", []))


def approve_ps_fees(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Split every READY PS row of one customer; each target is one total-preserving command."""
    customer, version, digest, key, ledger = approve_request(raw, runner, actor)
    try:
        projection = ps_projection(runner, ledger, actor)
    except ValueError as exc:
        raise ApiError(503, "PS_FEES_UNAVAILABLE", "Không đọc được bảng PS.") from exc
    if projection["snapshot_sha256"] != digest:
        raise ApiError(409, "STALE_SHEET", "Bảng PS đã đổi. Tải lại rồi tách.")
    written = 0
    for item in projection["ready"]:
        target = {"trip_id" if item["target_kind"] == "trip" else "legacy_row_id": item["target_id"]}
        # One key per target: a repeated click replays the stored result, never a second split.
        command_key = hashlib.sha256(f"{key}:{digest}:{item['target_kind']}:{item['target_id']}".encode()).hexdigest()
        try:
            result = runner.run("rewrite_trip_fees", {
                "customer_id": customer, "expected_version": version, "idempotency_key": command_key,
                "target": target, "expected_line_ids": [line["id"] for line in item["before"]],
                "lines": [{k: line[k] for k in ("fee_type_id", "amount_vnd", "note")} for line in item["after"]],
                "source": {"kind": "ps", "key": item["key"], "ps_source": item["ps_source"], "snapshot_sha256": digest}}, actor)
        except ApiError as exc:
            if not written:
                raise   # nothing written yet: a plain error, same as one fee edit
            # Every split keeps totals, so stopping half way leaves no money wrong; the rest stays READY.
            return 200, {"written": written, "remaining": len(projection["ready"]) - written,
                         "complete": False, "error": exc.code}
        version = result["version"] if type(result.get("version")) is int else \
            runner.run("get_ledger", {"customer_id": customer}, actor)["version"]
        written += 1
    return 200, {"written": written, "remaining": 0, "complete": True, "version": version}


def refresh_sheet(method: str, raw: bytes, actor: str) -> tuple[int, dict]:
    """Status of, or a request for, an immediate read-only Sheet run (specs/v7-sheet-refresh.md)."""
    paths = (SHEET_SNAPSHOT_PATH, PRICE_SNAPSHOT_PATH)
    if method == "GET":
        return 200, v7_sheet_refresh.status(SHEET_REFRESH_PATH, paths, time.time())
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    if request != {}:
        bad()
    try:
        return 200, v7_sheet_refresh.request(SHEET_REFRESH_PATH, paths, actor, time.time())
    except OSError as exc:
        raise ApiError(503, "SHEET_REFRESH_UNAVAILABLE", "Chưa gửi được yêu cầu lấy từ Sheet.") from exc


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
            or request["field"] not in ("carrier", "shipper", "origin", "destination", "event_date", "booking")
            or request["decision"] not in ("keep_web", "use_sheet")
            # Sheet date goes through the normal date edit; posted booking is kept (BOOKING-EDIT-01).
            or (request["field"] in ("event_date", "booking") and request["decision"] != "keep_web")
            or (request["field"] == "booking" and request["target_kind"] != "trip")
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
    if request["field"] == "booking" and sheet_value is None:
        sheet_value = ""  # Sheet booking left blank still differs from the posted booking.
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


def ledger_projections(runner: Psql, ledger: dict, actor: str) -> dict:
    """`GET /api/v7/ledger`: gắn bốn hàng chờ Sheet/PS vào sổ; nguồn nào hỏng chỉ đánh dấu `unavailable`, không chặn đọc sổ."""
    result = ledger
    try:
        result = {**result, "sheet_sync": sheet_projection(runner, result, actor)}
    except (ValueError, ApiError):
        result = {**result, "sheet_sync": {"unavailable": True, "items": [], "new_count": 0, "conflict_count": 0,
                                            "removed_items": [], "removed_count": 0}}
    try:
        result = {**result, "sheet_prices": price_projection(runner, result, actor)}
    except (ValueError, ApiError):
        result = {**result, "sheet_prices": {"unavailable": True, "ready": [], "review": [],
                                             "ready_count": 0, "review_count": 0}}
    try:
        result = {**result, "sheet_receipts": receipt_projection(runner, result, actor)}
    except (ValueError, ApiError):
        result = {**result, "sheet_receipts": {"unavailable": True, "ready": [], "review": [],
                                               "ready_count": 0, "review_count": 0}}
    try:
        result = {**result, "ps_fees": ps_projection(runner, result, actor)}
    except (ValueError, ApiError):
        result = {**result, "ps_fees": {"unavailable": True, "ready": [], "review": [],
                                        "ready_count": 0, "review_count": 0}}
    return result
