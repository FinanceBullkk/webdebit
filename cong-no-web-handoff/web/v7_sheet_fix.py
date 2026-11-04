"""Máy tự sửa sổ lệch Sheet (MAY-DOI-SOAT-01, specs/v7-may-doi-soat.md): chỉ ghi khi ghi xong tổng khách khớp Sheet tới từng đồng.

Gom việc Sheet → web đang chờ của một sổ (phiếu thu, giá) thành nhóm; mỗi nhóm biết trước làm tổng nợ đổi bao nhiêu. Tìm đúng một
tổ hợp nhóm đưa tổng web về tổng Sheet: có thì ghi bằng các lệnh có sẵn như nút bấm; không có, hoặc có nhiều tổ hợp, thì không ghi
gì và để lại lý do. Người làm trong Lịch sử là "Máy (theo Sheet)". Tổng Sheet và hàng chờ phải đọc từ cùng một bản tải Sheet.
"""

from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import itertools
from collections import Counter
from typing import Any

from v7_api_sheet import write_price_items
from v7_api_validate import ApiError
from v7_inbox import AUTO_ACTOR, in_month
from v7_price_queue import (
    classify,
    container_key,
    mark_shared,
    name_key,
    owners,
    project_prices,
    targets,
)
from v7_receipt_queue import METHOD, project_receipts, reference, review_reference

MAX_GROUPS = 16   # 65.535 tổ hợp; sổ nhiều nhóm hơn thì để chủ sổ xem, không dò
PRICE_STATUSES = ("READY", "MONTH_LOCKED", "CONFLICT")   # nhiều chuyến khớp, phụ phí gõ tay, chờ kiểm, "Giữ giá web" vẫn để người
NO_DATE_NOTE = " · ngày theo cuối tháng khối Sheet"
FEE_NOTE = "Theo Sheet: dòng có tiền, không container"
APPLY_ORDER = {"receipts_edited": 0, "receipts": 1, "receipts_no_date": 2, "prices": 3, "fee_rows": 4, "fee_undo": 5}


def _vnd(value: Any) -> int | None:
    return None if value is None else int(value)


def month_end(month: str, today: dt.date) -> str:
    """Phiếu Sheet không ghi ngày: ngày cuối tháng của khối Sheet chứa phiếu, không sau hôm nay (chủ sổ chốt 4/11/2026)."""
    year, number = int(month[:4]), int(month[5:7])
    return min(dt.date(year, number, calendar.monthrange(year, number)[1]), today).isoformat()


def receipt_groups(receipts: dict[str, Any], ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Phiếu sẵn sàng; phiếu không ngày theo tháng; và tháng Sheet đã sửa phiếu cũ: thay khoản thu sổ gốc Sheet không còn bằng
    đúng các phiếu Sheet đang ghi. Khoản thu sổ gốc có số đã trừ khác số Sheet thì không tính trước được, để người."""
    groups: list[dict[str, Any]] = []
    ready = list(receipts.get("ready") or [])
    if ready:
        groups.append({"kind": "receipts", "month": None, "rows": ready, "delta_vnd": -sum(int(r["amount_vnd"]) for r in ready)})
    months: dict[str, list[dict[str, Any]]] = {}
    for row in receipts.get("review") or []:
        if row["status"] in ("NO_DATE", "SHEET_EDITED"):
            months.setdefault(str(row["debt_month"])[:7], []).append(row)
    differs = {row.get("id") for row in ledger.get("legacy_rows") or [] if row.get("counted_differs")}
    for month, rows in sorted(months.items()):
        paid = sum(int(r["amount_vnd"]) for r in rows)
        orphans = next((r["web_legacy"] for r in rows if r["status"] == "SHEET_EDITED"), None)
        if orphans is None:
            groups.append({"kind": "receipts_no_date", "month": month, "rows": rows, "delta_vnd": -paid})
        elif not any(orphan["id"] in differs for orphan in orphans):
            groups.append({"kind": "receipts_edited", "month": month, "rows": rows, "orphans": orphans,
                           "delta_vnd": sum(int(orphan["amount_vnd"]) for orphan in orphans) - paid})
    return groups


def price_delta(row: dict[str, Any]) -> int | None:
    """Tổng nợ đổi bao nhiêu khi ghi một dòng giá, đúng như `write_price_items` sẽ ghi; None khi không tính trước được hoặc
    không có lệnh nào để ghi. Dòng sổ gốc tính lại bằng đơn giá + phụ phí, cũ là `counted_vnd`; chưa có đơn giá thì chưa tính nợ."""
    unit, fee = int(row["sheet_unit_price_vnd"]), _vnd(row["sheet_other_fee_vnd"])
    web_unit, web_fee = _vnd(row["web_unit_price_vnd"]), _vnd(row["web_other_fee_vnd"])
    if row["target_kind"] == "trip":
        return unit + (fee or 0) - (0 if web_unit is None else web_unit + (web_fee or 0))
    old = _vnd(row["web_total_vnd"])
    if old is None:
        return None
    fee_written = (web_fee or 0) != (fee or 0) if row["status"] == "CONFLICT" else fee is not None
    if web_unit == unit and not fee_written:
        return None
    return unit + ((fee if fee_written else web_fee) or 0) - old


def _sheet_rows(snapshot: dict[str, Any], ledger: dict[str, Any], customers: list[dict[str, Any]]) -> tuple[list, list, dict]:
    """(dòng giá Sheet của sổ đã phân loại, kể cả loại hàng chờ không hiện; đích ở web; đích theo khóa)."""
    owned = owners([{**c, "key": c["id"]} for c in customers if type(c.get("id")) is int])
    rows = [row for row in snapshot["rows"] if owned.get(name_key(row.get("customer_tab")), (None,))[0] == ledger.get("customer_id")]
    pool = targets(ledger)
    return mark_shared([classify(row, pool) for row in rows]), pool, {(target["kind"], target["id"]): target for target in pool}


def total_only_rows(results: list[dict[str, Any]], by_target: dict) -> list[dict[str, Any]]:
    """Dòng Sheet có TỔNG mà đơn giá trống, chuyến web chưa có giá và chưa tính đồng nào: lấy TỔNG làm đơn giá (chủ sổ chốt 4/11/2026).

    Dòng sổ gốc chưa có đơn giá mà đã có số tính nợ thì tiền đã ở trong sổ, không phải việc này (đo trên `hao` 4/11/2026: 78 dòng
    của một sổ đã khớp sẽ cộng sai 274 triệu nếu ghi).
    """
    rows = []
    for result in results:
        target = by_target.get((result["target_kind"], result["target_id"]))
        total = result.get("sheet_total_vnd")
        if (result["status"] == "SHEET_NO_PRICE" and target and target["price"] is None and not target["total"]
                and not target["pending"] and not target["typed_fee"] and type(total) is int and total > 0):
            rows.append({"status": "READY", "month": target["month"], "target_kind": target["kind"], "target_id": target["id"],
                         "sheet_unit_price_vnd": str(total), "sheet_other_fee_vnd": None, "web_unit_price_vnd": None,
                         "web_other_fee_vnd": None if target["fee"] is None else str(target["fee"]),
                         "web_total_vnd": None if target["total"] is None else str(target["total"])})
    return rows


def shuffled_months(prices: dict[str, Any]) -> list[str]:
    """Tháng có đơn giá đổi chỗ vòng tròn giữa các chuyến: Sheet xếp lại một phần cột (container đi một đằng, giá ở lại) thì tổng
    vẫn đúng mà giá từng container sai, phép khớp tổng không thấy (đo trên `hao` 4/11/2026: một sổ có 3 đơn giá đổi vòng).

    Mỗi dòng giá khác đơn giá là một cạnh từ giá web sang giá Sheet; có vòng là có đổi chỗ. Web chưa có giá thì không có gì để so.
    """
    graphs: dict[str, dict[str, set[str]]] = {}
    for row in prices.get("review") or []:
        web, sheet = row["web_unit_price_vnd"], row["sheet_unit_price_vnd"]
        if row["status"] == "CONFLICT" and row.get("month") and web is not None and web != sheet:
            graphs.setdefault(row["month"], {}).setdefault(web, set()).add(sheet)

    def has_cycle(graph: dict[str, set[str]]) -> bool:
        done: set[str] = set()

        def visit(node: str, path: set[str]) -> bool:
            if node in path:
                return True
            if node in done:
                return False
            found = any(visit(next_node, path | {node}) for next_node in graph.get(node, ()))
            done.add(node)
            return found
        return any(visit(node, set()) for node in graph)
    return sorted(month for month, graph in graphs.items() if has_cycle(graph))


def price_groups(prices: dict[str, Any], total_only: list[dict[str, Any]], skip_months: tuple | list = ()) -> list[dict[str, Any]]:
    """Giá Sheet theo tháng nợ của chuyến đích, mọi tháng (chủ sổ chốt 4/11/2026); dòng đã bấm "Giữ giá web" không có ở đây."""
    months: dict[str, dict[str, Any]] = {}
    for row in list(prices.get("ready") or []) + list(prices.get("review") or []) + total_only:
        delta = price_delta(row) if row["status"] in PRICE_STATUSES and row.get("month") and row["month"] not in skip_months else None
        if delta is not None:
            group = months.setdefault(row["month"], {"kind": "prices", "month": row["month"], "rows": [], "delta_vnd": 0})
            group["rows"].append(row)
            group["delta_vnd"] += delta
    return [months[month] for month in sorted(months)]


def fee_groups(results: list[dict[str, Any]], ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Dòng Sheet có tiền mà không có container theo tháng, ghi thành dòng điều chỉnh (chủ sổ chốt 4/11/2026). Dòng đã có trong sổ gốc
    (dòng không container cùng tháng, cùng số) hoặc đã có dòng điều chỉnh của máy cùng tháng, cùng số thì không phải việc.

    Dòng như vậy có thể chỉ là chuyến chưa nhập xong (đo trên `hao` 4/11/2026: một dòng có container sau vài giờ, máy đưa thành chuyến
    thật). Dòng điều chỉnh của máy mà Sheet không còn dòng tương ứng thành nhóm hủy, để tổ hợp khớp tổng tự gỡ phần tính trùng.
    """
    booked: Counter[tuple[str, str]] = Counter()
    for row in ledger.get("legacy_rows") or []:
        current = row.get("current") or {}
        if row.get("kind") == "trip" and not current.get("deleted") and not current.get("container"):
            booked[(str(current.get("month") or row.get("month"))[:7], str(current.get("counted_vnd")))] += 1
    written: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in ledger.get("adjustments") or []:
        if str(row.get("note") or "").startswith(FEE_NOTE):
            written.setdefault((str(row.get("month"))[:7], str(row.get("amount_vnd"))), []).append(row)
    months: dict[tuple[str, str], dict[str, Any]] = {}

    def add(kind: str, month: str, row: dict[str, Any], delta: int) -> None:
        group = months.setdefault((month, kind), {"kind": kind, "month": month, "rows": [], "delta_vnd": 0})
        group["rows"].append(row)
        group["delta_vnd"] += delta
    for result in results:
        total = result.get("sheet_total_vnd")
        if result["status"] != "NO_CONTAINER" or type(total) is not int or total == 0:
            continue
        key = (str(result.get("debt_month") or "")[:7], str(total))
        if booked[key] > 0:
            booked[key] -= 1
        elif written.get(key):
            written[key].pop()
        elif key[0]:
            add("fee_rows", key[0], {"source_row": result.get("source_row"), "amount_vnd": str(total)}, total)
    for (month, amount), rows in written.items():
        for row in rows:
            add("fee_undo", month, row, -int(amount))
    return [months[key] for key in sorted(months)]


def web_ahead(results: list[dict[str, Any]], pool: list[dict[str, Any]], by_target: dict) -> int:
    """Tiền của chuyến web đã có giá mà Sheet chưa ghi: dòng Sheet chưa có giá lẫn TỔNG, hoặc chưa có dòng nào của container đó. Web
    đi trước Sheet, không có gì để ghi; số này cộng vào tổng Sheet khi xét khớp (chủ sổ chốt 4/11/2026). Dòng sổ gốc không tính."""
    total = 0
    for result in results:
        target = by_target.get((result["target_kind"], result["target_id"]))
        if (result["status"] == "SHEET_NO_PRICE" and target and target["kind"] == "trip" and target["price"] is not None
                and not target["pending"] and not result.get("sheet_total_vnd")):
            total += target["price"] + (target["fee"] or 0)
    on_sheet = {container_key(result.get("container")) for result in results}
    for target in pool:
        if target["kind"] == "trip" and target["price"] is not None and not target["pending"] and target["container"] not in on_sheet:
            total += target["price"] + (target["fee"] or 0)
    return total


def plan(prices: dict[str, Any], receipts: dict[str, Any], ledger: dict[str, Any], customers: list[dict[str, Any]],
         today: dt.date) -> tuple[list[dict[str, Any]], int, list[str]]:
    """(các nhóm việc của sổ, tiền web đi trước Sheet, tháng có đơn giá đổi chỗ), từ hai bản chụp của cùng bản tải với tổng Sheet.
    Tháng có đơn giá đổi chỗ thì không có nhóm giá: tổng có khớp cũng không ghi giá theo Sheet đang xếp lệch."""
    results, pool, by_target = _sheet_rows(prices, ledger, customers)
    projected = project_prices(prices, ledger, customers)
    shuffled = shuffled_months(projected)
    groups = receipt_groups(project_receipts(receipts, ledger, customers, today), ledger)
    groups += price_groups(projected, total_only_rows(results, by_target), shuffled)
    groups += fee_groups(results, ledger)
    return groups, web_ahead(results, pool, by_target), shuffled


def choose(groups: list[dict[str, Any]], need: int) -> tuple[str, list[dict[str, Any]]]:
    """(kết luận, các nhóm sẽ ghi) để tổng web đổi đúng `need` đồng; nhóm không đổi tiền không ghi."""
    active = [group for group in groups if group["delta_vnd"]]
    if not active:
        return "NOTHING_TO_WRITE", []
    if len(active) > MAX_GROUPS:
        return "TOO_MANY_GROUPS", []
    found = [combo for size in range(1, len(active) + 1) for combo in itertools.combinations(active, size)
             if sum(group["delta_vnd"] for group in combo) == need]
    if not found:
        return "NO_EXACT_FIX", []
    return ("AMBIGUOUS_FIX", []) if len(found) > 1 else ("FIX", list(found[0]))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _version(runner, customer_id: int, result: dict[str, Any]) -> int:
    if type(result.get("version")) is int:
        return result["version"]
    return runner.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["version"]


def apply_fix(runner, customer_id: int, ledger: dict[str, Any], groups: list[dict[str, Any]], digest: str,
              today: dt.date) -> dict[str, int]:
    """Ghi các nhóm đã chọn bằng lệnh có sẵn; tháng khóa thì mở, ghi, khóa lại. Lệnh lỗi thì dừng sổ và ném lỗi, lượt sau tính lại.

    Khóa chống ghi trùng gắn phiên bản sổ lúc bắt đầu: cùng một lượt chạy lại trả kết quả cũ, lượt sau là lệnh mới, còn phiếu đã ghi
    thì hàng chờ đã ghép và không chọn lại.
    """
    version = ledger["version"]
    base = f"{AUTO_ACTOR}:doi-soat:{customer_id}:{version}"
    done = {"receipts": 0, "prices": 0, "legacy_deleted": 0, "fee_rows": 0, "fee_undone": 0}

    def receipt(row: dict[str, Any], at: int) -> int:
        if row["status"] == "NO_DATE":
            day, text = month_end(str(row["debt_month"]), today), (review_reference(row["source_fingerprint"]) + row["note"] + NO_DATE_NOTE)[:500]
        else:
            day, text = row["date"], reference(row["note"])
        result = runner.run("record_receipt", {
            "customer_id": customer_id, "expected_version": at, "date": day, "method": METHOD, "amount_vnd": row["amount_vnd"],
            "idempotency_key": _sha(f"{base}:{row['customer_tab']}:{row['source_row']}:{row['amount_vnd']}:{day}"),
            "reference": text}, AUTO_ACTOR)
        done["receipts"] += 1
        return _version(runner, customer_id, result)

    for group in sorted(groups, key=lambda item: (APPLY_ORDER[item["kind"]], item["month"] or "")):
        if group["kind"] == "receipts_edited":
            def delete(at: int, orphans: list[dict[str, Any]] = group["orphans"]) -> int:
                for orphan in orphans:
                    result = runner.run("delete_legacy_trip", {"customer_id": customer_id, "expected_version": at,
                                                               "idempotency_key": _sha(f"{base}:xoa:{orphan['id']}"),
                                                               "legacy_row_id": orphan["id"]}, AUTO_ACTOR)
                    done["legacy_deleted"] += 1
                    at = _version(runner, customer_id, result)
                return at
            version = in_month(runner, customer_id, version, ledger, group["month"], base, delete)
        if group["kind"] == "prices":
            def write(at: int, rows: list[dict[str, Any]] = group["rows"]) -> int:
                for conflict in (False, True):
                    batch = [row for row in rows if (row["status"] == "CONFLICT") is conflict]
                    if batch:
                        out = write_price_items(batch, customer_id, at, digest, f"{base}:gia", runner, AUTO_ACTOR, conflict=conflict)[1]
                        done["prices"] += out.get("written", 0)
                        if not out.get("complete"):
                            raise ApiError(409, str(out.get("error") or "INCOMPLETE"), "Máy chưa ghi hết giá của tháng.")
                        at = out["version"]
                return at
            version = in_month(runner, customer_id, version, ledger, group["month"], base, write)
        elif group["kind"] == "fee_rows":
            def adjust(at: int, rows: list[dict[str, Any]] = group["rows"], month: str = group["month"]) -> int:
                for row in rows:
                    result = runner.run("adjust_month", {
                        "customer_id": customer_id, "expected_version": at, "debt_month": month + "-01", "amount_vnd": row["amount_vnd"],
                        "idempotency_key": _sha(f"{base}:phi:{month}:{row['source_row']}:{row['amount_vnd']}"),
                        "note": f"{FEE_NOTE}, dòng {row['source_row']}"}, AUTO_ACTOR)
                    done["fee_rows"] += 1
                    at = _version(runner, customer_id, result)
                return at
            version = in_month(runner, customer_id, version, ledger, group["month"], base, adjust)
        elif group["kind"] == "fee_undo":
            def undo(at: int, rows: list[dict[str, Any]] = group["rows"]) -> int:
                for row in rows:
                    result = runner.run("delete_month_adjustment", {"customer_id": customer_id, "expected_version": at,
                                                                    "idempotency_key": _sha(f"{base}:huy-phi:{row['id']}"),
                                                                    "adjustment_id": row["id"]}, AUTO_ACTOR)
                    done["fee_undone"] += 1
                    at = _version(runner, customer_id, result)
                return at
            version = in_month(runner, customer_id, version, ledger, group["month"], base, undo)
        else:
            for row in group["rows"]:
                version = receipt(row, version)
    return done
