"""Sheet receipts waiting to be written to one customer ledger (read-only projection).

The queue is specs/v7-receipt-queue.md (THU-SHEET-01). A receipt on a customer tab is the
payment cells of a trip row: a free-text or date cell for the payment date ("23/10/2026 tt",
"da tt", a date serial) and an amount. It is already on the web when it matches an
original-book receipt row (same block month, amount and payment-date text) or a web receipt
(same amount, same date, else within 3 days). What is left is READY when its date reads and
is not in the future, and its month has no original-book receipt the Sheet no longer shows
(the Sheet edited an old receipt: writing the new one would count both).
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

from v7_price_queue import name_key, owners

DATE_WINDOW_DAYS = 3
REVIEW = ("NO_DATE", "FUTURE_DATE", "SHEET_EDITED", "WEB_DELETED")
METHOD = "THU TIỀN"
SERIAL = re.compile(r"[0-9]{5}(?:\.0+)?")
DAY_FIRST = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)")
ISO = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")


def note_key(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def pay_date(note: Any) -> dt.date | None:
    """Date cell (serial) or a date at the start of the note; anything else is no date."""
    text = str(note or "").strip()
    try:
        if SERIAL.fullmatch(text):
            return dt.date(1899, 12, 30) + dt.timedelta(days=int(text.split(".")[0]))
        if match := ISO.match(text):
            year, month, day = map(int, match.groups())
        elif match := DAY_FIRST.match(text):
            day, month, year = map(int, match.groups())
        else:
            return None
        return dt.date(year, month, day)
    except (ValueError, OverflowError):
        return None


def rows_from_scan(scan: dict[str, dict]) -> list[dict]:
    """Receipt rows of customer tabs from `scan_tabs`; a tab with any structural issue is left out.

    Rows come from the month blocks, as the cutover load read them: a block typed twice
    identically keeps its rows in the tab-wide `records` only, and counting both copies
    would write a receipt the web already has.
    """
    rows = []
    for tab, data in scan.items():
        if any(data.get("issues", {}).values()):
            continue
        for block in data.get("blocks", {}).values():
            for record in block.get("records", []):
                if record["kind"] == "receipt" and type(record.get("amount")) is int and record["amount"] > 0:
                    rows.append({"customer_tab": tab, "source_row": record["row"], "debt_month": record["month"],
                                 "amount_vnd": record["amount"], "note": str(record.get("raw_date") or "").strip()})
    return rows


def load_receipt_snapshot(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as stream:
            snapshot = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError("Sheet receipt snapshot unavailable") from exc
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("rows"), list):
        raise ValueError("Sheet receipt snapshot invalid")
    if not isinstance(snapshot.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"]):
        raise ValueError("Sheet receipt snapshot hash missing")
    if snapshot.get("row_count") != len(snapshot["rows"]):
        raise ValueError("Sheet receipt snapshot row count mismatch")
    return snapshot


def _int(value: Any) -> int | None:
    text = str(value if value is not None else "").strip()
    return int(text) if re.fullmatch(r"-?[0-9]+", text) else None


def classify(rows: list[dict], ledger: dict, today: dt.date) -> list[dict]:
    """Status for each Sheet receipt row of one customer, in Sheet order."""
    rows = sorted(rows, key=lambda r: (str(r.get("debt_month")), r.get("source_row") or 0))
    results = [{**row, "date": pay_date(row.get("note")), "status": None} for row in rows]
    legacy: dict[tuple, list[int]] = {}
    deleted: set[tuple] = set()
    for item in ledger.get("legacy_rows", []):
        if item.get("kind") != "receipt":
            continue
        key = (str(item.get("month") or "")[:7], _int(item.get("source_total_vnd")),
               note_key((item.get("display") or {}).get("raw_date")))
        if (item.get("current") or {}).get("deleted"):
            deleted.add(key)
        else:
            legacy.setdefault(key, []).append(item.get("id"))
    # Exact amount first; then 1 dong either way: a cell holding a fraction of a dong was rounded
    # by the cutover load with the month's remainder spread over its rows (ROUNDING_APPORTIONED).
    for slack in (0, 1):
        for result in results:
            if result["status"]:
                continue
            month, note = str(result["debt_month"])[:7], note_key(result["note"])
            key = next((k for k in legacy if legacy[k] and k[0] == month and k[2] == note
                        and k[1] is not None and abs(k[1] - result["amount_vnd"]) <= slack), None)
            if key:
                legacy[key].pop(0)
                result["status"] = "MATCHED_LEGACY"
    orphans: dict[str, list[dict]] = {}
    for (month, amount, _), ids in legacy.items():
        for legacy_id in ids:
            orphans.setdefault(month, []).append({"id": legacy_id, "amount_vnd": str(amount)})
    web = [{"date": dt.date.fromisoformat(str(r["date"])[:10]), "amount": _int(r.get("amount_vnd"))}
           for r in ledger.get("receipts", []) if not r.get("voided_by_event") and r.get("date")]
    # Exact dates first for every row, so a near match never takes another row's exact one.
    for near in (False, True):
        for result in results:
            if result["status"] or result["date"] is None:
                continue
            found = [w for w in web if w["amount"] == result["amount_vnd"]
                     and (abs((w["date"] - result["date"]).days) <= DATE_WINDOW_DAYS if near else w["date"] == result["date"])]
            if found:
                web.remove(min(found, key=lambda w: abs((w["date"] - result["date"]).days)))
                result["status"] = "MATCHED_WEB"
    for result in results:
        if result["status"]:
            continue
        month = str(result["debt_month"])[:7]
        if (month, result["amount_vnd"], note_key(result["note"])) in deleted:
            result["status"] = "WEB_DELETED"
        elif result["date"] is None:
            result["status"] = "NO_DATE"
        elif result["date"] > today:
            result["status"] = "FUTURE_DATE"
        elif orphans.get(month):
            result |= {"status": "SHEET_EDITED", "web_legacy": orphans[month]}
        else:
            result["status"] = "READY"
    return results


def project_receipts(snapshot: dict, ledger: dict, customers: list[dict], today: dt.date) -> dict:
    """Rows of this ledger's customer: READY for the batch button, REVIEW for "Cần xem"."""
    owned = owners([{**c, "key": c["id"]} for c in customers if type(c.get("id")) is int])
    customer = ledger.get("customer_id")
    rows = [row for row in snapshot["rows"] if owned.get(name_key(row.get("customer_tab")), (None,))[0] == customer]
    keep = ("customer_tab", "source_row", "debt_month", "amount_vnd", "note", "date", "status")

    def public(result: dict) -> dict:
        # Money leaves the API as exact decimal strings (same contract as get_ledger).
        out = {k: result[k] for k in keep} | {"amount_vnd": str(result["amount_vnd"]),
                                                "date": result["date"].isoformat() if result["date"] else None}
        return out | ({"web_legacy": result["web_legacy"]} if "web_legacy" in result else {})
    results = classify(rows, ledger, today)
    ready = sorted((public(r) for r in results if r["status"] == "READY"), key=lambda r: (r["date"], r["source_row"]))
    review = [public(r) for r in results if r["status"] in REVIEW]
    return {"snapshot_sha256": snapshot["sha256"], "snapshot_created_at": (snapshot.get("runner") or {}).get("created_at"),
            "ready": ready, "review": review, "ready_count": len(ready), "review_count": len(review)}


def reference(note: str) -> str:
    return ("Sheet: " + note if note else "Sheet")[:500]
