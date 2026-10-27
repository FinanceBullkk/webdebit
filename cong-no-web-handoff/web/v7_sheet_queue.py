"""Read-only projection of Sheet trips; every row stays outside ledger balance."""

from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def _name(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value or "")).strip().upper().split())


def _container(value: Any) -> str:
    return "".join(str(value or "").upper().split())


def _source_row(value: Any) -> int | None:
    match = re.fullmatch(r"sheet:[0-9a-f]{64}:(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _row_year(value: Any) -> int | None:
    text = str(value or "").strip()[:10]
    try:
        return dt.date.fromisoformat(text).year
    except ValueError:
        return None


def load_snapshot(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as stream:
            snapshot = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError("Sheet snapshot unavailable") from exc
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("rows"), list):
        raise ValueError("Sheet snapshot invalid")
    if not isinstance(snapshot.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot["sha256"]):
        raise ValueError("Sheet snapshot hash missing")
    if snapshot.get("row_count") != len(snapshot["rows"]):
        raise ValueError("Sheet snapshot row count mismatch")
    return snapshot


def load_baseline(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as stream:
            baseline = json.load(stream)
    except (OSError, ValueError) as exc:
        raise ValueError("baseline references unavailable") from exc
    if not isinstance(baseline, dict) or type(baseline.get("cutover_id")) is not int:
        raise ValueError("baseline references invalid")
    if not isinstance(baseline.get("refs"), list) or not baseline["refs"] or baseline.get("count") != len(baseline["refs"]):
        raise ValueError("baseline reference count mismatch")
    return baseline


def build_queue(snapshot: dict[str, Any], customers: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    names: dict[str, list[dict[str, Any]]] = {}
    for customer in customers:
        if isinstance(customer, dict) and type(customer.get("id")) is int and isinstance(customer.get("name"), str):
            names.setdefault(_name(customer["name"]), []).append(customer)
    aliases = snapshot.get("customer_aliases") or {}
    items = []
    skipped_out_of_scope = 0
    for source in snapshot["rows"]:
        if not isinstance(source, dict):
            raise ValueError("Sheet row invalid")
        if source.get("status") == "READY" and _row_year(source.get("event_date") or source.get("source_date")) != 2026:
            # Out of scope by year, but never silently: the API reports the count so
            # new years stay visible instead of disappearing from the queue.
            skipped_out_of_scope += 1
            continue
        item = {key: source.get(key) for key in (
            "source_row", "container", "carrier", "event_date", "origin", "destination",
            "booking", "customer_name", "source_date", "status")}
        if "shipper" in source:
            item["shipper"] = source.get("shipper")
        status = source.get("status") or "INVALID"
        reasons: list[str] = []
        matches = names.get(_name(aliases.get(_name(source.get("customer_name")), source.get("customer_name"))), [])
        match = matches[0] if len(matches) == 1 and matches[0].get("status") == "active" else None
        if status != "READY":
            review_status = status
            reasons.append(status)
        else:
            if match is None:
                review_status = "NEEDS_CUSTOMER"
                reasons.append("CUSTOMER_MAPPING")
            else:
                review_status = "NEEDS_PRICE"
                reasons.extend(("PRICE_REQUIRED", "NEW_TRIP_REVIEW"))
            # Baseline was reconciled once at cutover. It remains provenance, not
            # a per-row realtime gate; source-row matching below handles changes.
        item.update({"customer_id": match["id"] if match else None,
                     "review_status": review_status, "review_reasons": reasons})
        items.append(item)
    return {"source": snapshot.get("source"), "snapshot_sha256": snapshot["sha256"],
            "snapshot_created_at": (snapshot.get("runner") or {}).get("created_at"),
            "baseline_cutover_id": baseline["cutover_id"], "items": items,
            "row_count": len(items), "ready_count": 0, "review_count": len(items),
            "skipped_out_of_scope": skipped_out_of_scope}


def project_customer(queue: dict[str, Any], ledger: dict[str, Any], other_customer_containers: set[str] | None = None) -> dict[str, Any]:
    """Show only new or changed Sheet rows inside one customer ledger."""
    existing = []
    for trip in ledger.get("trips", []):
        existing.append({"kind": "trip", "id": trip.get("id"), "container": trip.get("container"),
                         "event_date": trip.get("event_date"), "carrier": trip.get("carrier"), "shipper": trip.get("shipper"),
                         "origin": trip.get("origin"), "destination": trip.get("destination"),
                         "booking": trip.get("booking"), "source_row": _source_row(trip.get("source_ref"))})
    for legacy in ledger.get("legacy_rows", []):
        if legacy.get("kind") != "trip":
            continue
        current = legacy.get("current") or {}
        display = legacy.get("display") or {}
        existing.append({"kind": "legacy", "id": legacy.get("id"),
                         "container": current.get("container") or display.get("container"),
                         "event_date": current.get("event_date") or display.get("date"),
                         "carrier": current.get("carrier") or display.get("carrier"),
                         "shipper": current.get("shipper") or display.get("shipper"),
                         "origin": current.get("origin") or display.get("from"),
                         "destination": current.get("destination") or display.get("to")})
    resolved = {}
    for event in ledger.get("events", []):
        if event.get("kind") != "sheet_conflict_resolved":
            continue
        after = event.get("after") or {}
        target = after.get("target") or {}
        field = after.get("field")
        if field and target.get("kind") in ("trip", "legacy") and type(target.get("id")) is int:
            resolved[(after.get("source_row"), target["kind"], target["id"], field)] = (
                after.get("target_value"), after.get("sheet_value"))
    visible = []
    for row in queue["items"]:
        if row.get("customer_id") != ledger.get("customer_id"):
            continue
        if row.get("review_status") not in ("NEEDS_PRICE",):
            continue
        container = _container(row.get("container"))
        date = dt.date.fromisoformat(row["event_date"])
        booking = _container(row.get("booking"))
        direct_matches = [old for old in existing if old.get("source_row") == row.get("source_row")]
        matches = direct_matches if len(direct_matches) == 1 else []
        candidates = [] if matches else existing
        same_container = []
        for old in candidates:
            if _container(old.get("container")) != container:
                continue
            same_container.append(old)
            if not old.get("event_date"):
                continue
            try:
                old_date = dt.date.fromisoformat(str(old["event_date"])[:10])
            except ValueError:
                continue
            if (booking and old.get("booking") and booking == _container(old["booking"])) or abs((date - old_date).days) <= 3:
                matches.append(old)
        if container in (other_customer_containers or set()):
            state = "CONFLICT"
            reason = "OTHER_CUSTOMER"
            changed = []
        elif len(matches) == 1:
            old = matches[0]
            changed = [field for field in ("event_date", "origin", "destination")
                       if _name(row.get(field)) != _name(old.get(field))]
            if old["kind"] != "legacy" and _name(row.get("carrier")) != _name(old.get("carrier")):
                changed.append("carrier")
            old_shipper = old.get("shipper") or (old.get("carrier") if old["kind"] == "legacy" else None)
            if row.get("shipper") and _name(row["shipper"]) != _name(old_shipper):
                changed.append("shipper")
            elif old["kind"] == "legacy" and not row.get("shipper"):
                changed.append("shipper_unavailable")
            if old.get("booking") and booking != _container(old["booking"]):
                changed.append("booking")
            changed = [field for field in changed if not (
                (key := (row.get("source_row"), old["kind"], old["id"], field)) in resolved
                and _name(old.get(field)) == _name(resolved[key][0])
                and _name(row.get(field)) == _name(resolved[key][1]))]
            if not changed:
                continue
            state = "CONFLICT"
            reason = "DIFFERENT_FIELDS"
        elif matches or same_container:
            state = "CONFLICT"
            reason = "AMBIGUOUS_MATCH" if matches else "CONTAINER_REUSED_OR_CHANGED"
            changed = []
        else:
            state = "NEW"
            reason = ""
            changed = []
        visible.append({**row, "sync_state": state, "sync_reason": reason,
                        "changed_fields": changed,
                        "existing_kind": old["kind"] if len(matches) == 1 and reason == "DIFFERENT_FIELDS" else None,
                        "existing_id": old["id"] if len(matches) == 1 and reason == "DIFFERENT_FIELDS" else None,
                        "existing_values": {field: (old.get("shipper") or
                                                    (old.get("carrier") if old["kind"] == "legacy" else None))
                                            if field == "shipper" else old.get(field)
                                            for field in changed} if len(matches) == 1 and reason == "DIFFERENT_FIELDS" else None})
    return {"snapshot_sha256": queue["snapshot_sha256"], "items": visible,
            "new_count": sum(row["sync_state"] == "NEW" for row in visible),
            "conflict_count": sum(row["sync_state"] == "CONFLICT" for row in visible)}


def plan_shipper_backfill(queue: dict[str, Any], ledger: dict[str, Any]) -> list[dict[str, Any]]:
    """Read-only proposals; only unique customer, container and exact date matches."""
    customer_id = ledger.get("customer_id")
    sources: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in queue["items"]:
        if row.get("customer_id") != customer_id or row.get("status") != "READY":
            continue
        if not row.get("carrier") or not row.get("shipper") or not row.get("event_date"):
            continue
        key = (_container(row.get("container")), str(row["event_date"])[:10])
        sources.setdefault(key, []).append(row)
    targets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in ledger.get("trips", []):
        key = (_container(row.get("container")), str(row.get("event_date") or "")[:10])
        targets.setdefault(key, []).append({"kind": "trip", "id": row.get("id"), "data": row})
    for row in ledger.get("legacy_rows", []):
        if row.get("kind") != "trip":
            continue
        current = row.get("current") or {}
        display = row.get("display") or {}
        key = (_container(current.get("container") or display.get("container")),
               str(current.get("event_date") or display.get("date") or "")[:10])
        targets.setdefault(key, []).append({"kind": "legacy", "id": row.get("id"), "data": current or display})
    result = []
    for key, matches in sources.items():
        if not key[0] or len(matches) != 1 or len(targets.get(key, [])) != 1:
            continue
        source, target = matches[0], targets[key][0]
        old = target["data"]
        if old.get("shipper"):
            continue
        old_carrier = _name(old.get("carrier"))
        if old_carrier not in ("", _name(source["shipper"]), _name(source["carrier"])):
            continue
        result.append({"kind": target["kind"], "id": target["id"],
                       "source_row": source["source_row"],
                       "before": {"carrier": old.get("carrier"), "shipper": old.get("shipper")},
                       "after": {"carrier": source["carrier"], "shipper": source["shipper"]}})
    return result
