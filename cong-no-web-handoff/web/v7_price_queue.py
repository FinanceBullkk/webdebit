"""Sheet prices waiting to be written to one customer ledger (read-only projection).

Matching rules are measured in specs/v7-price-match.md; the queue is specs/v7-price-queue.md.
A Sheet trip row (customer tab) points at one web trip or original-book row of the
same customer: same container, exact date first, then within 3 days; undated rows by
container alone. A unique, unpriced, open-month match is READY; a changed negative
fee with the same unit price can also replace its existing discount.

Books were named from Google's .xlsx download, the price runner reads the same tabs through
the Sheets API, and the two disagree (audit 29/10/2026): the download drops "/" and "'" from
tab names ("KHACH A/B" becomes "KHACH AB"; the other characters Excel forbids in a sheet name
are dropped here too) and writes a number typed in the container cell as "4.2E7" where the
API returns 42000000. Keys below compare both forms alike; the snapshot keeps the tab name
exactly as the Sheet shows it.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import v7_normalize as normalize
from v7_sheet_queue import read_snapshot
from v7_sheet_task_keep import kept, price_identity, source_kept

DATE_WINDOW_DAYS = 3
REVIEW = ("MONTH_LOCKED", "CONFLICT", "AMBIGUOUS", "MANUAL")
SOURCE_CLOSABLE = ("AMBIGUOUS", "MANUAL")   # K3: máy không tự ghi được và không có số web để giữ: người chỉ "Đã xem, hết báo" theo dấu vân dòng Sheet
XLSX_DROPPED = str.maketrans("", "", "/\\?*[]:'")


@lru_cache(maxsize=4096)
def _normal_name(text: str) -> str:
    return " ".join(text.translate(XLSX_DROPPED).split())


def name_key(value: Any) -> str:
    # Mở một sổ gọi hơn 11.000 lần cho vài trăm tên tab, nên nhớ kết quả theo chuỗi (hàm thuần).
    return _normal_name(str(value or ""))


def container_key(value: Any) -> str:
    """Khóa container Sheet–web; luật chung ở `v7_normalize.container_key` (số khoa học, mã ISO kèm chữ ghi chú)."""
    return normalize.container_key(value)


def iso(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def money(value: Any) -> int | None:
    if type(value) is int:
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
        return int(value)
    return None


def load_price_snapshot(path: str | Path) -> dict[str, Any]:
    return read_snapshot(path, "Sheet price snapshot")


def owners(customers: list[dict]) -> dict[str, tuple[Any, str]]:
    """Tab name -> (customer key, "name" | "alias"). Ledger names win; a name or alias on two books is dropped."""
    primary: dict[str, set] = {}
    for customer in customers:
        primary.setdefault(name_key(customer["name"]), set()).add(customer["key"])
    extra: dict[str, set] = {}
    for customer in customers:
        for alias in [customer.get("display_name"), *(customer.get("aliases") or [])]:
            if isinstance(alias, str) and alias.strip() and name_key(alias) not in primary:
                extra.setdefault(name_key(alias), set()).add(customer["key"])
    return {key: (next(iter(keys)), basis) for basis, found in (("name", primary), ("alias", extra))
            for key, keys in found.items() if len(keys) == 1}


def targets(ledger: dict) -> list[dict]:
    locks = {str(row.get("month"))[:7]: row.get("locked") for row in ledger.get("month_locks", [])}
    today = str(ledger.get("today_month") or "")[:7]

    def locked(month: Any) -> bool:
        key = str(month or "")[:7]
        return locks.get(key, key != today)

    out = []
    for trip in ledger.get("trips", []):
        if trip.get("deleted") or trip.get("status") == "rejected":
            continue
        out.append({"kind": "trip", "id": trip.get("id"), "container": container_key(trip.get("container")),
                    "date": iso(trip.get("event_date")), "price": money(trip.get("unit_price_vnd")),
                    "fee": money(trip.get("other_fee_vnd")), "typed_fee": bool(trip.get("has_typed_fee")), "locked": locked(trip.get("month")),
                    "month": str(trip.get("month") or "")[:7], "total": None, "pending": trip.get("status") == "pending_review"})
    for row in ledger.get("legacy_rows", []):
        current = row.get("current") or {}
        if row.get("kind") != "trip" or current.get("deleted"):
            continue
        month = current.get("month") or row.get("month")
        out.append({"kind": "legacy", "id": row.get("id"), "container": container_key(current.get("container")),
                    "date": iso(current.get("event_date")), "price": money(current.get("unit_price_vnd")),
                    "fee": money(current.get("other_fee_vnd")), "typed_fee": bool(current.get("has_typed_fee", row.get("has_typed_fee"))), "locked": locked(month),
                    "month": str(month or "")[:7], "total": money(current.get("counted_vnd")), "pending": False})
    return [target for target in out if target["container"]]


def unchanged(row: dict, target: dict) -> bool:
    if target["price"] != row["sheet_unit_price_vnd"]:
        return False
    if target["kind"] == "legacy":
        # Original-book rows keep the Sheet TOTAL (counted_vnd); fee columns such as negative
        # discounts are not stored separately, so the charged total is what must agree.
        return target["total"] is not None and target["total"] == row.get("sheet_total_vnd")
    # V7-BE: with a known price a blank fee counts as 0, so blank and 0 are the same charge.
    return (row["sheet_other_fee_vnd"] or 0) == (target["fee"] or 0)


def candidates(row: dict, pool: list[dict]) -> tuple[list[dict], str]:
    """(web rows one Sheet row may point at, how they were found). The one matching rule; the cutover audit reuses it."""
    container = container_key(row.get("container"))
    sheet_date = iso(row.get("date"))
    same = [t for t in pool if t["container"] == container]
    found, basis = [t for t in same if sheet_date and t["date"] == sheet_date], "exact_date"
    if not found and sheet_date:
        found, basis = [t for t in same if t["date"] and abs((t["date"] - sheet_date).days) <= DATE_WINDOW_DAYS], "near_date"
    if not found and not sheet_date:
        # Undated Sheet rows (mostly old history): container alone; several rows stay AMBIGUOUS.
        found, basis = same, "container_only"
        # GHEP-KHONG-NGAY-01: an undated web row that already charges exactly this priced Sheet row is its copy; the other
        # rows of a reused container are not candidates. Taken only where the rule above would ask (some candidate still
        # unpriced), and a copy is never written, so no write is added or removed.
        if row.get("sheet_unit_price_vnd") is not None and any(t["price"] is None for t in same):
            copies = [t for t in same if t["date"] is None and unchanged(row, t)]
            if copies:
                found, basis = copies, "undated_copy"
    return found, basis


def classify(row: dict, pool: list[dict] | None) -> dict:
    result = {**row, "status": None, "match_basis": "", "target_kind": "", "target_id": "",
              "web_unit_price_vnd": None, "web_other_fee_vnd": None, "web_total_vnd": None}
    if not container_key(row.get("container")):
        return result | {"status": "NO_CONTAINER"}
    if pool is None:
        return result | {"status": "NO_CUSTOMER"}
    found, basis = candidates(row, pool)
    if not found:
        return result | {"status": "NOT_FOUND"}
    result["match_basis"] = basis
    if len(found) > 1:
        # Every candidate already priced: nothing to write, so it is not shown for review.
        return result | {"status": "AMBIGUOUS_PRICED" if all(t["price"] is not None for t in found) else "AMBIGUOUS"}
    target = found[0]
    result.update(target_kind=target["kind"], target_id=target["id"], web_unit_price_vnd=target["price"],
                  web_other_fee_vnd=target["fee"], web_total_vnd=target["total"])
    price = row["sheet_unit_price_vnd"]
    if price is None:
        status = "SHEET_NO_PRICE"   # blank stays NULL; nothing to write
    elif unchanged(row, target):
        status = "PRICE_UNCHANGED"
    elif target.get("typed_fee"):
        status = "MANUAL"
    elif target["pending"]:
        status = "PENDING_REVIEW"
    elif target["price"] is not None:
        # ponytail: requeue only changed negative totals at the same unit price;
        # widen after conflict decisions gain a price-write route.
        discount_update = (target["price"] == price and target["fee"] is not None
                           and target["fee"] < 0 and row["sheet_other_fee_vnd"] is not None
                           and row["sheet_other_fee_vnd"] < 0)
        status = ("MONTH_LOCKED" if target["locked"] else "READY") if discount_update else "CONFLICT"
    elif price < 0:
        status = "MANUAL"
    else:
        status = "MONTH_LOCKED" if target["locked"] else "READY"
    return result | {"status": status}


def sheet_money(result: dict) -> bool:
    """Dòng Sheet có tiền (tổng hoặc đơn giá); dòng trống tiền không có gì để báo."""
    return bool(result.get("sheet_total_vnd") or result.get("sheet_unit_price_vnd"))


def mark_shared(results: list[dict]) -> list[dict]:
    """Two Sheet rows pointing at one web row cannot both be written."""
    used = Counter((r["target_kind"], r["target_id"]) for r in results if r["target_id"] != "")
    return [r | {"status": "AMBIGUOUS"} if r["target_id"] != "" and used[(r["target_kind"], r["target_id"])] > 1 else r
            for r in results]


def merge_two_row_pairs(rows: list[dict], snapshot: dict, pool: list[dict]) -> list[dict]:
    """Bố cục hai dòng đã duyệt (KIEM-TAB-01, `v7_tab_health.TWO_ROW_LAYOUT_TABS`): dòng container không tiền và dòng tiền không
    container ngay dưới là MỘT chuyến. Khi web đã có chuyến web (không phải dòng sổ gốc) của container đó, gộp hai dòng thành một dòng Sheet (container của dòng trên,
    ngày và tiền của dòng dưới): tiền thành giá của chuyến, không còn là "phí lẻ" để ghi thêm một dòng điều chỉnh nữa (cộng đôi). Dòng
    điều chỉnh "Theo Sheet" cũ của cùng khoản không còn dòng tương ứng nên `fee_groups` đưa vào nhóm hủy. Web chưa có chuyến thì giữ hai
    dòng như cũ: tiền vào dòng điều chỉnh. Cặp đọc từ `tabs` của bản chụp (phát hiện mức `note`, `two_row_layout`)."""
    pairs = [(tab, found["rows"]) for tab, health in (snapshot.get("tabs") or {}).items()
             for found in health.get("findings") or [] if found.get("kind") == "two_row_layout" and len(found.get("rows") or ()) == 2]
    if not pairs:
        return rows
    by_row = {(row.get("customer_tab"), row.get("source_row")): row for row in rows}
    merged: dict[tuple, dict] = {}
    dropped: set[tuple] = set()
    for tab, (holder_no, money_no) in pairs:
        holder, money = by_row.get((tab, holder_no)), by_row.get((tab, money_no))
        if (holder is None or money is None or not container_key(holder.get("container")) or container_key(money.get("container"))
                or holder.get("sheet_total_vnd") not in (None, 0) or holder.get("sheet_unit_price_vnd") is not None
                or money.get("sheet_total_vnd") in (None, 0) or money.get("sheet_unit_price_vnd") is not None):
            continue   # không đúng hình cặp (đã đổi giữa lúc quét): để hai dòng như cũ
        joined = {**holder, "date": money.get("date"), "debt_month": money.get("debt_month") or holder.get("debt_month"),
                  "sheet_total_vnd": money["sheet_total_vnd"], "sheet_other_fee_vnd": money.get("sheet_other_fee_vnd")}
        if any(target["kind"] == "trip" for target in candidates(joined, pool)[0]):   # dòng sổ gốc đã ghi tiền thành dòng "Phí lẻ" riêng: gộp là tính đôi
            merged[(tab, holder_no)] = joined
            dropped.add((tab, money_no))
    return [merged.get((row.get("customer_tab"), row.get("source_row")), row) for row in rows
            if (row.get("customer_tab"), row.get("source_row")) not in dropped]


def book_rows(snapshot: dict, customer: Any, customers: list[dict]) -> list[dict]:
    """Rows of the customer tab that belongs to this book."""
    owned = owners([{**c, "key": c["id"]} for c in customers if type(c.get("id")) is int])
    return [row for row in snapshot["rows"] if owned.get(name_key(row.get("customer_tab")), (None,))[0] == customer]


def project_prices(snapshot: dict, ledger: dict, customers: list[dict], *, include_kept=False) -> dict:
    """Rows of this ledger's customer: READY for the batch button, REVIEW for "Cần xem"."""
    pool = targets(ledger)
    rows = merge_two_row_pairs(book_rows(snapshot, ledger.get("customer_id"), customers), snapshot, pool)
    by_target = {(target["kind"], target["id"]): target for target in pool}
    results = mark_shared([classify(row, pool) for row in rows])
    keep = ("customer_tab", "source_row", "container", "date", "sheet_unit_price_vnd", "sheet_other_fee_vnd",
            "status", "target_kind", "target_id", "web_unit_price_vnd", "web_other_fee_vnd", "web_total_vnd", "batchable")
    money_fields = ("sheet_unit_price_vnd", "sheet_other_fee_vnd", "web_unit_price_vnd", "web_other_fee_vnd", "web_total_vnd")

    def public(result: dict) -> dict:
        # Money leaves the API as exact decimal strings, NULL stays null (same contract as get_ledger).
        target = by_target.get((result["target_kind"], result["target_id"]))
        price, fee = result["sheet_unit_price_vnd"], result["sheet_other_fee_vnd"]
        changed = target is not None and (price != target["price"] or (fee or 0) != (target["fee"] or 0))
        sheet_total = result.get("sheet_total_vnd")
        total_matches = price is not None and (sheet_total is None or sheet_total == price + (fee or 0))
        batchable = (result["status"] == "CONFLICT" and target is not None and not target["locked"] and changed
                     and total_matches and (target["kind"] == "trip" or (target["total"] is not None
                         and sheet_total is not None)))
        row = {k: batchable if k == "batchable" else
               ((None if result[k] is None else str(result[k])) if k in money_fields else result[k]) for k in keep}
        row["source_fingerprint"] = price_identity(result)
        row["month_locked"] = target["locked"] if target else True
        row["month"] = target["month"] if target else ""   # yyyy-mm của chuyến đích: máy mở đúng tháng đó (MAY-GIA-01)
        return row
    ready = [public(r) for r in results if r["status"] == "READY"]
    review = [{**public(r), "closable": r["status"] in SOURCE_CLOSABLE} for r in results if r["status"] in REVIEW]
    # Dòng Sheet có tiền mà máy không ghi được (kể cả dòng không khớp chuyến nào, như "… 取消"): người đóng được theo dấu vân dòng.
    closable = sorted({price_identity(r) for r in results if r["status"] in (*SOURCE_CLOSABLE, "NOT_FOUND") and sheet_money(r)})
    if not include_kept:
        review = [r for r in review if not (r["closable"] and source_kept(ledger, "price", r["source_fingerprint"])) and not kept(
            ledger, "price", r["target_kind"], r["target_id"], r["source_fingerprint"],
            {"unit_price_vnd": r["web_unit_price_vnd"], "other_fee_vnd": r["web_other_fee_vnd"]})]
    return {"snapshot_sha256": snapshot["sha256"], "snapshot_created_at": (snapshot.get("runner") or {}).get("created_at"),
            "ready": ready, "review": review, "ready_count": len(ready), "review_count": len(review), "closable_sources": closable}
