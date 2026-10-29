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
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

DATE_WINDOW_DAYS = 3
REVIEW = ("MONTH_LOCKED", "CONFLICT", "AMBIGUOUS", "MANUAL")
XLSX_DROPPED = str.maketrans("", "", "/\\?*[]:'")
NUMBER_CELL = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:E\+?[0-9]{1,2})?")


def name_key(value: Any) -> str:
    return " ".join(str(value or "").translate(XLSX_DROPPED).split())


def container_key(value: Any) -> str:
    text = "".join(str(value or "").upper().split())
    if ("." in text or "E" in text) and NUMBER_CELL.fullmatch(text):
        number = Decimal(text)
        if number == number.to_integral_value():
            return str(int(number))   # "4.2E7" and "42000000.0" read as 42000000; digits keep leading zeros
    return text


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
    try:
        with open(path, encoding="utf-8") as stream:
            snapshot = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError("Sheet price snapshot unavailable") from exc
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("rows"), list):
        raise ValueError("Sheet price snapshot invalid")
    if not isinstance(snapshot.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"]):
        raise ValueError("Sheet price snapshot hash missing")
    if snapshot.get("row_count") != len(snapshot["rows"]):
        raise ValueError("Sheet price snapshot row count mismatch")
    return snapshot


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
                    "total": None, "pending": trip.get("status") == "pending_review"})
    for row in ledger.get("legacy_rows", []):
        current = row.get("current") or {}
        if row.get("kind") != "trip" or current.get("deleted"):
            continue
        out.append({"kind": "legacy", "id": row.get("id"), "container": container_key(current.get("container")),
                    "date": iso(current.get("event_date")), "price": money(current.get("unit_price_vnd")),
                    "fee": money(current.get("other_fee_vnd")), "typed_fee": bool(current.get("has_typed_fee", row.get("has_typed_fee"))), "locked": locked(current.get("month") or row.get("month")),
                    "total": money(current.get("counted_vnd")), "pending": False})
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


def classify(row: dict, pool: list[dict] | None) -> dict:
    result = {**row, "status": None, "match_basis": "", "target_kind": "", "target_id": "",
              "web_unit_price_vnd": None, "web_other_fee_vnd": None, "web_total_vnd": None}
    container = container_key(row.get("container"))
    sheet_date = iso(row.get("date"))
    if not container:
        return result | {"status": "NO_CONTAINER"}
    if pool is None:
        return result | {"status": "NO_CUSTOMER"}
    same = [t for t in pool if t["container"] == container]
    found, basis = [t for t in same if sheet_date and t["date"] == sheet_date], "exact_date"
    if not found and sheet_date:
        found, basis = [t for t in same if t["date"] and abs((t["date"] - sheet_date).days) <= DATE_WINDOW_DAYS], "near_date"
    if not found and not sheet_date:
        # Undated Sheet rows (mostly old history): container alone; several rows stay AMBIGUOUS.
        found, basis = same, "container_only"
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


def mark_shared(results: list[dict]) -> list[dict]:
    """Two Sheet rows pointing at one web row cannot both be written."""
    used = Counter((r["target_kind"], r["target_id"]) for r in results if r["target_id"] != "")
    return [r | {"status": "AMBIGUOUS"} if r["target_id"] != "" and used[(r["target_kind"], r["target_id"])] > 1 else r
            for r in results]


def project_prices(snapshot: dict, ledger: dict, customers: list[dict]) -> dict:
    """Rows of this ledger's customer: READY for the batch button, REVIEW for "Cần xem"."""
    owned = owners([{**c, "key": c["id"]} for c in customers if type(c.get("id")) is int])
    customer = ledger.get("customer_id")
    rows = [row for row in snapshot["rows"] if owned.get(name_key(row.get("customer_tab")), (None,))[0] == customer]
    pool = targets(ledger)
    results = mark_shared([classify(row, pool) for row in rows])
    keep = ("customer_tab", "source_row", "container", "date", "sheet_unit_price_vnd", "sheet_other_fee_vnd",
            "status", "target_kind", "target_id", "web_unit_price_vnd", "web_other_fee_vnd")
    money_fields = ("sheet_unit_price_vnd", "sheet_other_fee_vnd", "web_unit_price_vnd", "web_other_fee_vnd")

    def public(result: dict) -> dict:
        # Money leaves the API as exact decimal strings, NULL stays null (same contract as get_ledger).
        return {k: (None if result[k] is None else str(result[k])) if k in money_fields else result[k] for k in keep}
    ready = [public(r) for r in results if r["status"] == "READY"]
    review = [public(r) for r in results if r["status"] in REVIEW]
    return {"snapshot_sha256": snapshot["sha256"], "snapshot_created_at": (snapshot.get("runner") or {}).get("created_at"),
            "ready": ready, "review": review, "ready_count": len(ready), "review_count": len(review)}
