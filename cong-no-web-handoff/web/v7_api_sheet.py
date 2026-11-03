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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
from v7_receipt_queue import load_receipt_snapshot, project_receipts, review_reference
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


# Bản chụp Sheet/PS đọc một lần cho tới khi file đổi (runner thay file nguyên khối 15 phút một lần). Hàm chiếu chỉ
# đọc bản chụp và chép dòng ra dict mới, nên dùng chung giữa các request là an toàn. Tăng tốc mở sổ 1/11/2026.
_SNAPSHOTS: dict[tuple, tuple] = {}
_SNAPSHOT_LOCK = threading.Lock()


def cached_load(loader, path):
    try:
        stat = os.stat(path)
    except OSError:
        return loader(path)   # để hàm đọc tự báo lỗi đúng của nó
    stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    key = (loader, str(path))
    with _SNAPSHOT_LOCK:
        hit = _SNAPSHOTS.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    value = loader(path)
    with _SNAPSHOT_LOCK:
        _SNAPSHOTS[key] = (stamp, value)
    return value


# Hàng chờ chuyến dựng từ bản chụp chỉ phụ thuộc bản chụp, danh sách khách và bản đối chiếu lúc nạp, nên giống hệt nhau
# ở mọi sổ và mọi lần mở sổ cho tới khi một trong ba đổi. Giữ một bản; `project_customer` chỉ đọc và chép dòng ra dict mới.
_QUEUE: list = [None, None, None, None]   # [snapshot, baseline, khóa danh sách khách, hàng chờ]
_QUEUE_LOCK = threading.Lock()


def cached_queue(snapshot: dict, customers: list, baseline: dict) -> dict:
    key = json.dumps(customers, sort_keys=True, ensure_ascii=False, default=str)
    with _QUEUE_LOCK:
        held_snapshot, held_baseline, held_key, held_queue = _QUEUE
        if held_snapshot is snapshot and held_baseline is baseline and held_key == key:
            return held_queue
    queue = build_queue(snapshot, customers, baseline)
    with _QUEUE_LOCK:
        _QUEUE[:] = [snapshot, baseline, key, queue]
    return queue


class SharedReads:
    """Runner bọc cho một lần mở sổ hoặc một lượt hộp ngoại lệ: ba hàm đọc dùng chung chỉ chạy một lần."""

    SHARED = ("list_customers", "get_fee_types", "list_sheet_trip_refs")

    def __init__(self, runner):
        self.runner, self.cache, self.lock = runner, {}, threading.Lock()

    def run(self, function: str, payload: dict, actor: str) -> dict:
        if function not in self.SHARED:
            return self.runner.run(function, payload, actor)
        with self.lock:
            if function not in self.cache:
                self.cache[function] = self.runner.run(function, payload, actor)
            return self.cache[function]


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
        snapshot = cached_load(load_snapshot, SHEET_SNAPSHOT_PATH)
        baseline = cached_load(load_baseline, SHEET_BASELINE_PATH)
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", str(exc)) from exc
    queue = build_queue(snapshot, with_display_names(customers).get("customers", []), baseline)
    if parts_query:
        customer = int(parse_qs(parts_query, keep_blank_values=True)["customer"][0])
        queue["items"] = [item for item in queue["items"] if item["customer_id"] == customer]
        queue["row_count"] = len(queue["items"])
        queue["review_count"] = queue["row_count"]
    return queue


def sheet_projection(runner: Psql, ledger: dict, actor: str) -> dict:
    snapshot = cached_load(load_snapshot, SHEET_SNAPSHOT_PATH)
    baseline = cached_load(load_baseline, SHEET_BASELINE_PATH)
    # Tên khách và mặt hàng từ bảng gán tên để chọn sổ theo mặt hàng (P3b), như ba hàm chiếu kia.
    mapping = customer_name_mapping()
    customers = [named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    refs = runner.run("list_sheet_trip_refs", {}, actor).get("items")
    if not isinstance(refs, list):
        raise ValueError("web trip references unavailable")
    other_containers = set()
    for ref in refs:
        if not isinstance(ref, dict) or type(ref.get("customer_id")) is not int or not isinstance(ref.get("container"), str):
            raise ValueError("web trip references invalid")
        if ref["customer_id"] != ledger.get("customer_id"):
            other_containers.add("".join(ref["container"].upper().split()))
    queue = cached_queue(snapshot, customers, baseline)
    current = next((c for c in customers if c["id"] == ledger["customer_id"]), {})
    family = current.get("display_name") or current.get("name")
    candidates = [c for c in customers if c.get("status") == "active" and c.get("transport_mode") != "BO"
                  and (c.get("display_name") or c.get("name")) == family]
    # Show an unmapped family row once, in its first book, for explicit human choice.
    if candidates and ledger["customer_id"] == min(c["id"] for c in candidates):
        from v7_sheet_queue import _name
        aliases = snapshot.get("customer_aliases") or {}
        queue = {**queue, "items": [{**row, "customer_id": ledger["customer_id"], "review_status": "NEEDS_PRICE", "book_match": "COMMODITY_UNKNOWN"}
                 if row.get("customer_id") is None and row.get("review_status") == "NEEDS_CUSTOMER"
                 and _name(aliases.get(_name(row.get("customer_name")), row.get("customer_name"))) == _name(family)
                 else row for row in queue["items"]]}
    waiting = sorted({"".join(str(row.get("container") or "").upper().split()) for row in queue["items"]
                      if row.get("customer_id") == ledger.get("customer_id") and row.get("review_status") == "NEEDS_PRICE"} - {""})
    other_legacy = []
    for start in range(0, len(waiting), 1000):
        items = runner.run("list_legacy_trip_refs", {"containers": waiting[start:start + 1000]}, actor).get("items")
        if not isinstance(items, list):
            raise ValueError("legacy trip references unavailable")
        for ref in items:
            if not isinstance(ref, dict) or type(ref.get("customer_id")) is not int or not isinstance(ref.get("container"), str):
                raise ValueError("legacy trip references invalid")
            if ref["customer_id"] != ledger.get("customer_id"):
                other_legacy.append(ref)
    # Sổ cùng khách (cùng tên khách), kể cả sổ đường bộ: chuyến đã ở sổ gốc của chúng là đã tính, không hiện.
    family_ids = {c["id"] for c in customers if (c.get("display_name") or c.get("name")) == family} - {ledger["customer_id"]}
    result = project_customer(queue, ledger, other_containers, other_legacy, family_ids)
    from v7_sheet_task_keep import trip_identity
    assigned = {}
    for event in ledger.get("events", []):
        after = event.get("after") or {}
        if event.get("kind") != "sheet_conflict_resolved" or after.get("field") != "task_assignment":
            continue
        target_customer = after.get("target_customer_id")
        target = ledger if target_customer == ledger["customer_id"] else runner.run("get_ledger", {"customer_id": target_customer}, actor)
        if any(t.get("id") == after.get("target", {}).get("id") and not t.get("deleted") for t in target.get("trips", [])):
            assigned[after.get("sheet_value")] = True
    items = []
    for row in result["items"]:
        source = trip_identity(row)
        if source in assigned:
            continue
        items.append({**row, "source_fingerprint": source,
                      "candidate_books": [{k: c.get(k) for k in ("id", "name", "display_name", "commodity", "transport_mode", "version")} for c in candidates]})
    return {**result, "items": items, "new_count": sum(r["sync_state"] == "NEW" for r in items),
            "conflict_count": sum(r["sync_state"] == "CONFLICT" for r in items)}


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
    return 200, paste_sheet_rows(runner, customer, version, digest, key, rows, actor)


def paste_sheet_rows(runner: Psql, customer: int, version: int, digest: str, key: str, rows: list[dict],
                     actor: str) -> dict:
    """Dán các dòng Sheet "chuyến mới" của một sổ bằng `paste_trips`, theo tháng, 200 dòng một lệnh, chưa có giá.

    Nút "Duyệt" (`approve_sheet`) và máy (P3b, `v7_inbox`) đi chung đường này. Lỗi ở lệnh đầu ném `ApiError`;
    lỗi sau khi đã ghi một phần thì trả `complete: False` kèm mã lỗi.
    """
    months: dict[str, list[dict]] = {}
    for row in rows:
        month = row["event_date"][:7] + "-01"
        months.setdefault(month, []).append(row)
    approved = 0
    processed = 0
    pending = []
    pasted = []   # (dòng Sheet, mã chuyến) theo thứ tự dán
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
                return {"approved": approved, "remaining": len(rows) - processed, "review_count": len(pending),
                        "complete": False, "error": exc.code, "pending_review": pending, "pasted": pasted}
            processed += len(batch)
            pasted.extend({"source_row": row["source_row"], "trip_id": trip_id}
                          for row, trip_id in zip(batch, result.get("trip_ids", []), strict=False))
            newly_pending = result.get("pending_review", [])
            pending.extend(newly_pending)
            approved += len(batch) - len(newly_pending)
            if processed < len(rows):
                version = runner.run("get_ledger", {"customer_id": customer}, actor)["version"]
    return {"approved": approved, "remaining": 0, "complete": True,
            "review_count": len(pending), "pending_review": pending, "pasted": pasted}


def price_projection(runner: Psql, ledger: dict, actor: str, *, include_kept=False) -> dict:
    snapshot = cached_load(load_price_snapshot, PRICE_SNAPSHOT_PATH)
    mapping = customer_name_mapping()
    customers = [named_customer(row, mapping) for row in runner.run("list_customers", {}, actor).get("customers", [])]
    return project_prices(snapshot, ledger, customers, include_kept=include_kept)


def write_price_items(items: list[dict], customer: int, version: int, digest: str, key: str,
                      runner: Psql, actor: str, *, conflict: bool = False) -> tuple[int, dict]:
    undo_keys = []
    written = commands_done = 0
    for item in items:
        price, fee = str(item["sheet_unit_price_vnd"]), item["sheet_other_fee_vnd"]
        if item["target_kind"] == "trip":
            commands = [("edit_trip_price", {"trip_id": item["target_id"], "unit_price_vnd": price,
                                             "other_fee_vnd": None if fee is None else str(fee)})]
        else:
            commands = []
            if item.get("web_unit_price_vnd") is None or str(item["web_unit_price_vnd"]) != price:
                commands.append(("edit_legacy_trip", {"legacy_row_id": item["target_id"],
                                                     "field": "unit_price_vnd", "value": price}))
            fee_changed = (item.get("web_other_fee_vnd") or "0") != (fee or "0")
            if (conflict and fee_changed) or (not conflict and fee is not None):
                commands.append(("edit_legacy_trip", {"legacy_row_id": item["target_id"], "field": "other_fee_vnd",
                                                      "value": "" if fee is None else str(fee)}))
        for function, fields in commands:
            # One key per target and field: a repeated click replays the stored result, never a second write.
            command_key = hashlib.sha256(
                f"{key}:{digest}:{item['target_kind']}:{item['target_id']}:{fields.get('field', 'price')}".encode()).hexdigest()
            try:
                result = runner.run(function, {"customer_id": customer, "expected_version": version,
                                               "idempotency_key": command_key, **fields}, actor)
            except ApiError as exc:
                if exc.code == "FEE_LINES_TYPED":
                    return 200, {"written": written, "remaining": len(items) - written,
                                 "complete": False, "error": exc.code,
                                 "review": [{**item, "status": "MANUAL"}]}
                if not commands_done:
                    raise   # nothing written yet: a plain error, same as one price edit
                return 200, {"written": written, "remaining": len(items) - written,
                             "complete": False, "error": exc.code}
            version = result["version"] if type(result.get("version")) is int else                 runner.run("get_ledger", {"customer_id": customer}, actor)["version"]
            commands_done += 1
            undo_keys.append(command_key)
        written += 1
    return 200, {"written": written, "remaining": 0, "complete": True, "version": version, "undo_keys": undo_keys}


def approve_prices(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Write every READY Sheet price of one customer through the existing price commands."""
    customer, version, digest, key, ledger = approve_request(raw, runner, actor)
    try:
        projection = price_projection(runner, ledger, actor)
    except ValueError as exc:
        raise ApiError(503, "SHEET_PRICES_UNAVAILABLE", "Không đọc được giá từ Sheet.") from exc
    if projection["snapshot_sha256"] != digest:
        raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi ghi.")
    return write_price_items(projection["ready"], customer, version, digest, key, runner, actor)


def approve_price_conflicts(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Write only explicitly selected, still matching Sheet price conflicts."""
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    if not isinstance(request, dict) or set(request) != {"customer_id", "expected_version", "snapshot_sha256",
                                                     "idempotency_key", "conflicts"}:
        bad()
    selected = request["conflicts"]
    if (type(selected) is not list or not 1 <= len(selected) <= 200 or
            any(type(item) is not dict or set(item) != {"target_kind", "target_id", "source_row"} or
                item["target_kind"] not in ("trip", "legacy") or not positive_int(item["target_id"]) or
                not positive_int(item["source_row"]) for item in selected)):
        bad()
    keys = [(item["target_kind"], item["target_id"], item["source_row"]) for item in selected]
    if len(set(keys)) != len(keys):
        bad()
    base = {name: value for name, value in request.items() if name != "conflicts"}
    customer, version, digest, key, ledger = approve_request(json.dumps(base).encode(), runner, actor)
    try:
        projection = price_projection(runner, ledger, actor)
    except ValueError as exc:
        raise ApiError(503, "SHEET_PRICES_UNAVAILABLE", "Không đọc được giá từ Sheet.") from exc
    if projection["snapshot_sha256"] != digest:
        raise ApiError(409, "STALE_SHEET", "Sheet đã đổi. Tải lại rồi ghi.")
    available = {(item["target_kind"], item["target_id"], item["source_row"]): item
                 for item in projection["review"] if item["status"] == "CONFLICT" and item["batchable"]}
    if any(item not in available for item in keys):
        raise ApiError(409, "STALE_SHEET", "Dòng giá đã đổi hoặc cần xử lý riêng. Tải lại sổ rồi xem lại.")
    return write_price_items([available[item] for item in keys], customer, version, digest, key, runner, actor,
                             conflict=True)


def receipt_projection(runner: Psql, ledger: dict, actor: str) -> dict:
    snapshot = cached_load(load_receipt_snapshot, RECEIPT_SNAPSHOT_PATH)
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
    undo_keys = []
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
        undo_keys.append(command_key)
        written += 1
    return 200, {"written": written, "remaining": 0, "complete": True, "version": version, "undo_keys": undo_keys}


def ps_projection(runner: Psql, ledger: dict, actor: str) -> dict:
    snapshot = cached_load(load_ps_snapshot, PS_SNAPSHOT_PATH)
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


def keep_sheet_task(raw: bytes, runner: Psql, actor: str, *, apply_price=False) -> tuple[int, dict]:
    """Acknowledge a current Sheet difference without changing financial state."""
    from v7_sheet_task_keep import web_value

    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad("INVALID_SHEET_RESOLUTION")
    required = {"customer_id", "expected_version", "idempotency_key", "task_kind", "target_kind", "target_id", "source_fingerprint"}
    if not isinstance(request, dict) or set(request) != required:
        bad("INVALID_SHEET_RESOLUTION")
    key = request["idempotency_key"]
    if (not positive_int(request["customer_id"]) or not positive_int(request["target_id"])
            or type(request["expected_version"]) is not int or not 0 <= request["expected_version"] <= MAX_BIGINT
            or request["task_kind"] not in ("price", "removed") or request["target_kind"] not in ("trip", "legacy")
            or (request["task_kind"] == "removed" and request["target_kind"] != "trip")
            or (apply_price and request["task_kind"] != "price")
            or not isinstance(request["source_fingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", request["source_fingerprint"])
            or not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.strip() or any(ord(c) < 32 for c in key)):
        bad("INVALID_SHEET_RESOLUTION")
    ledger = runner.run("get_ledger", {"customer_id": request["customer_id"]}, actor)
    command = "apply_sheet_price" if apply_price else "keep_sheet_task"
    decision = "use_sheet" if apply_price else "keep_web"
    target = {"kind": request["target_kind"], "id": request["target_id"]}
    for event in ledger.get("events", []):
        after = event.get("after") or {}
        if after.get("request_key") != key:
            continue
        if (event.get("kind") != "sheet_conflict_resolved" or after.get("target") != target
                or after.get("decision") != decision
                or after.get("field") != "task_" + request["task_kind"]
                or after.get("sheet_value") != request["source_fingerprint"]):
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", ERRORS["IDEMPOTENCY_CONFLICT"][1])
        payload = {**request, "web_value": after.get("web_value") if apply_price else after["target_value"]}
        if apply_price:
            payload["sheet_price"] = after["requested_price"]
        return 200, runner.run(command, payload, actor)
    if ledger.get("version") != request["expected_version"]:
        raise ApiError(409, "STALE_LEDGER", ERRORS["STALE_LEDGER"][1])
    try:
        if request["task_kind"] == "price":
            rows = price_projection(runner, ledger, actor, include_kept=True)["review"]
            rows = [r for r in rows if r["status"] == "CONFLICT" and r["target_kind"] == target["kind"] and r["target_id"] == target["id"]]
            current = {"unit_price_vnd": rows[0]["web_unit_price_vnd"], "other_fee_vnd": rows[0]["web_other_fee_vnd"]} if len(rows) == 1 else None
        else:
            rows = [r for r in sheet_projection(runner, ledger, actor)["removed_items"] if r["trip_id"] == target["id"]]
            trip = next((r for r in ledger.get("trips", []) if r["id"] == target["id"]), {})
            current = web_value("removed", trip)
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", "Không đọc được Sheet để đối chiếu.") from exc
    if len(rows) != 1 or rows[0].get("source_fingerprint") != request["source_fingerprint"]:
        raise ApiError(409, "STALE_SHEET", "Dòng Sheet đã đổi. Tải lại rồi thử lại.")
    payload = {**request, "web_value": current}
    if apply_price:
        payload["sheet_price"] = {"unit_price_vnd": rows[0]["sheet_unit_price_vnd"], "other_fee_vnd": rows[0]["sheet_other_fee_vnd"]}
    return 200, runner.run(command, payload, actor)


def apply_sheet_price(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    return keep_sheet_task(raw, runner, actor, apply_price=True)


def assign_sheet_trip(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    required = {"customer_id", "expected_version", "idempotency_key", "target_customer_id", "target_version", "source_fingerprint"}
    if not isinstance(request, dict) or set(request) != required:
        bad()
    if (any(not positive_int(request[k]) for k in ("customer_id", "target_customer_id"))
            or any(type(request[k]) is not int or not 0 <= request[k] <= MAX_BIGINT for k in ("expected_version", "target_version"))
            or not isinstance(request["source_fingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", request["source_fingerprint"])
            or not isinstance(request["idempotency_key"], str) or not 1 <= len(request["idempotency_key"]) <= 128
            or not request["idempotency_key"].strip() or any(ord(c) < 32 for c in request["idempotency_key"])):
        bad()
    ledger = runner.run("get_ledger", {"customer_id": request["customer_id"]}, actor)
    for event in ledger.get("events", []):
        after = event.get("after") or {}
        if after.get("field") == "task_assignment" and after.get("request_key") == request["idempotency_key"]:
            args = after.get("arguments") or {}
            if any(args.get(k) != v for k, v in request.items()):
                raise ApiError(409, "IDEMPOTENCY_CONFLICT", ERRORS["IDEMPOTENCY_CONFLICT"][1])
            return 200, runner.run("assign_sheet_trip", args, actor)
    if ledger.get("version") != request["expected_version"]:
        raise ApiError(409, "STALE_LEDGER", ERRORS["STALE_LEDGER"][1])
    try:
        rows = [r for r in sheet_projection(runner, ledger, actor)["items"]
                if r.get("source_fingerprint") == request["source_fingerprint"] and r.get("sync_state") == "NEW"]
    except ValueError as exc:
        raise ApiError(503, "SHEET_SNAPSHOT_UNAVAILABLE", "Không đọc được chuyến Sheet.") from exc
    if len(rows) != 1 or request["target_customer_id"] not in [c["id"] for c in rows[0].get("candidate_books", [])]:
        raise ApiError(409, "STALE_SHEET", "Dòng Sheet hoặc sổ được chọn đã đổi. Tải lại rồi thử lại.")
    row = {k: rows[0].get(k) for k in ("source_row", "container", "carrier", "shipper", "event_date", "origin", "destination", "booking")}
    return 200, runner.run("assign_sheet_trip", {**request, "source_row": row}, actor)


def review_sheet_receipt(raw: bytes, runner: Psql, actor: str) -> tuple[int, dict]:
    """Supply a missing receipt date; link the written receipt to its source row content."""
    from datetime import date

    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates)
    except (UnicodeError, ValueError, TypeError):
        bad()
    if not isinstance(request, dict) or set(request) != {"customer_id", "expected_version", "idempotency_key", "source_fingerprint", "date"}:
        bad()
    if (not positive_int(request["customer_id"]) or type(request["expected_version"]) is not int
            or not 0 <= request["expected_version"] <= MAX_BIGINT
            or not isinstance(request["source_fingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", request["source_fingerprint"])
            or not isinstance(request["idempotency_key"], str) or not 1 <= len(request["idempotency_key"]) <= 128
            or not request["idempotency_key"].strip() or any(ord(c) < 32 for c in request["idempotency_key"])
            or not isinstance(request["date"], str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", request["date"])):
        bad()
    try:
        chosen = date.fromisoformat(request["date"])
    except ValueError:
        bad()
    if chosen > datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date():
        bad("FUTURE_DATE")
    ledger = runner.run("get_ledger", {"customer_id": request["customer_id"]}, actor)
    prefix = review_reference(request["source_fingerprint"])
    existing = [r for r in ledger.get("receipts", []) if not r.get("voided_by_event") and (r.get("reference") or "").startswith(prefix)]
    if existing:
        if len(existing) != 1 or existing[0].get("date") != request["date"]:
            raise ApiError(409, "STALE_LEDGER", "Phiếu đã ghi với ngày khác. Mở sổ đối chiếu.")
        return 200, {"written": 1, "complete": True, "receipt_id": existing[0]["id"], "version": ledger["version"]}
    if ledger.get("version") != request["expected_version"]:
        raise ApiError(409, "STALE_LEDGER", ERRORS["STALE_LEDGER"][1])
    try:
        rows = [r for r in receipt_projection(runner, ledger, actor)["review"]
                if r["status"] == "NO_DATE" and r.get("source_fingerprint") == request["source_fingerprint"]]
    except ValueError as exc:
        raise ApiError(503, "SHEET_RECEIPTS_UNAVAILABLE", "Không đọc được phiếu Sheet.") from exc
    if len(rows) != 1:
        raise ApiError(409, "STALE_SHEET", "Phiếu Sheet đã đổi. Tải lại rồi thử lại.")
    row = rows[0]
    result = runner.run("record_receipt", {"customer_id": request["customer_id"], "expected_version": request["expected_version"],
        "idempotency_key": request["idempotency_key"], "date": request["date"], "method": RECEIPT_METHOD,
        "amount_vnd": row["amount_vnd"], "reference": (prefix + row["note"])[:500]}, actor)
    return 200, {**result, "written": 1, "complete": True}


def ledger_projections(runner: Psql, ledger: dict, actor: str) -> dict:
    """`GET /api/v7/ledger`: gắn bốn hàng chờ Sheet/PS vào sổ; nguồn nào hỏng chỉ đánh dấu `unavailable`, không chặn đọc sổ.

    Bốn hàm chiếu độc lập (không hàm nào đọc kết quả của hàm khác), nên chạy song song trên cùng một runner đọc chung;
    phần lớn thời gian là chờ psql. Đo trên `hao` 1/11/2026: nối tiếp 0,75 giây, `list_customers` bị gọi 4 lần.
    """
    shared = SharedReads(runner)
    parts = (
        ("sheet_sync", sheet_projection, {"unavailable": True, "items": [], "new_count": 0, "conflict_count": 0,
                                          "removed_items": [], "removed_count": 0}),
        ("sheet_prices", price_projection, {"unavailable": True, "ready": [], "review": [], "ready_count": 0, "review_count": 0}),
        ("sheet_receipts", receipt_projection, {"unavailable": True, "ready": [], "review": [], "ready_count": 0, "review_count": 0}),
        ("ps_fees", ps_projection, {"unavailable": True, "ready": [], "review": [], "ready_count": 0, "review_count": 0}),
    )
    with ThreadPoolExecutor(max_workers=len(parts)) as pool:
        futures = [(key, pool.submit(project, shared, ledger, actor), empty) for key, project, empty in parts]
    result = dict(ledger)
    for key, future, empty in futures:
        try:
            result[key] = future.result()
        except (ValueError, ApiError):
            result[key] = empty
    return result
