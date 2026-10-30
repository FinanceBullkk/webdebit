#!/usr/bin/env python3
"""Compare two trip snapshots of the Sheet sync runner (specs/v7-sheet-contract.md, phase 2a).

Usage: v7_sheet_source_diff.py OLD.json NEW.json [--detail PATH]

OLD is the WEBDEBIT_EXPORT + BOOKING_DATA snapshot, NEW the CONT_NGUON one (or any two runs).
Rows pair on the trip itself (container, date, carrier, origin, destination), never on row numbers,
because the two tabs number rows differently. Prints counts only, so the output may go into a
deploy log. --detail writes the differing keys (they carry customer names) to a file outside Git.
Exit 0 when the READY rows are identical in both snapshots, 1 otherwise, 2 on a bad file.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import unicodedata
from collections import Counter
from typing import Any

FIELDS = ("status", "booking", "customer_name", "shipper", "durian_type")


def _text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFC", str(value if value is not None else "")).upper().split())


def trip_key(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_text(row.get(field)) for field in ("container", "event_date", "carrier", "origin", "destination"))


def load(path: str | pathlib.Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as stream:
        snapshot = json.load(stream)
    rows = snapshot.get("rows") if isinstance(snapshot, dict) else None
    if not isinstance(rows, list) or snapshot.get("row_count") != len(rows):
        raise ValueError("snapshot invalid")
    return rows


def compare(old_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts for the deploy log plus the differing keys for --detail."""
    def index(rows: list[dict[str, Any]]) -> dict[tuple[str, ...], list[dict[str, Any]]]:
        by_key: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in rows:
            by_key.setdefault(trip_key(row), []).append(row)
        return by_key

    old, new = index(old_rows), index(new_rows)
    only_old = [key for key in old if key not in new]
    only_new = [key for key in new if key not in old]
    field_diffs: Counter[str] = Counter()
    differing: list[dict[str, Any]] = []
    for key in old.keys() & new.keys():
        if len(old[key]) != len(new[key]):
            field_diffs["multiplicity"] += 1
            differing.append({"key": key, "reason": "multiplicity", "old": len(old[key]), "new": len(new[key])})
            continue
        for before, after in zip(sorted(old[key], key=lambda r: _text(r.get("booking"))),
                                 sorted(new[key], key=lambda r: _text(r.get("booking"))), strict=True):
            changed = [field for field in FIELDS if _text(before.get(field)) != _text(after.get(field))]
            for field in changed:
                field_diffs[field] += 1
            if changed:
                differing.append({"key": key, "reason": "fields", "fields": changed,
                                  "old": {f: before.get(f) for f in changed}, "new": {f: after.get(f) for f in changed}})

    def ready(rows: list[dict[str, Any]]) -> Counter[tuple[str, ...]]:
        return Counter(trip_key(row) + tuple(_text(row.get(field)) for field in FIELDS[1:])
                       for row in rows if row.get("status") == "READY")

    ready_old, ready_new = ready(old_rows), ready(new_rows)
    ready_only_old, ready_only_new = ready_old - ready_new, ready_new - ready_old
    return {
        "rows": {"old": len(old_rows), "new": len(new_rows)},
        "status": {"old": dict(Counter(r.get("status") for r in old_rows)),
                   "new": dict(Counter(r.get("status") for r in new_rows))},
        "only_old": dict(Counter(old[key][0].get("status") for key in only_old)),
        "only_new": dict(Counter(new[key][0].get("status") for key in only_new)),
        "field_diffs": dict(field_diffs),
        "ready": {"old": sum(ready_old.values()), "new": sum(ready_new.values()),
                  "only_old": sum(ready_only_old.values()), "only_new": sum(ready_only_new.values())},
        "flagged_new": sum(1 for r in new_rows if r.get("source_flag")),
        "identical_ready": not ready_only_old and not ready_only_new,
        "_detail": {"only_old": [list(k) for k in only_old], "only_new": [list(k) for k in only_new],
                    "differing": [{**d, "key": list(d["key"])} for d in differing],
                    "ready_only_old": [list(k) for k in ready_only_old], "ready_only_new": [list(k) for k in ready_only_new]},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old")
    parser.add_argument("new")
    parser.add_argument("--detail", type=pathlib.Path, help="write differing keys here (names inside: keep outside Git)")
    args = parser.parse_args(argv)
    try:
        result = compare(load(args.old), load(args.new))
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 2
    detail = result.pop("_detail")
    if args.detail:
        args.detail.parent.mkdir(parents=True, exist_ok=True)
        args.detail.write_text(json.dumps(detail, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["identical_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
