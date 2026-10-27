#!/usr/bin/env python3
"""Turn one Sheet XLSX export into the price snapshot the V7 API reads (specs/v7-price-queue.md).

Usage: --xlsx SHEET.xlsx --output /var/lib/webdebit-sheet-sync/prices.json

Read-only on the Sheet side. The snapshot holds customer-tab trip rows (tab, row, container,
date, unit price, fees, TOTAL); its hash covers the rows only, so re-exporting an unchanged
Sheet keeps the same hash and an approved batch is not reported stale. The file holds names
and money: keep it outside Git with mode 600. Stdout carries counts only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile

import v7_price_match as match


def build(xlsx: pathlib.Path) -> dict:
    rows = match.sheet_rows(xlsx)
    canonical = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {"source": {"xlsx_sha256": hashlib.sha256(xlsx.read_bytes()).hexdigest()},
            "rows": rows, "row_count": len(rows), "sha256": hashlib.sha256(canonical).hexdigest(),
            "runner": {"created_at": dt.datetime.now(dt.UTC).isoformat(), "mode": "read-only"}}


def write(snapshot: dict, output: pathlib.Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                     prefix=".price-snapshot-", delete=False) as stream:
        temporary = pathlib.Path(stream.name)
        json.dump(snapshot, stream, ensure_ascii=False)
        stream.write("\n")
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)   # readers never see a half-written file
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path,
                        default=pathlib.Path(os.getenv("WEBDEBIT_PRICE_SNAPSHOT_PATH", "sheet-prices.json")))
    args = parser.parse_args(argv)
    try:
        snapshot = build(args.xlsx)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 2
    write(snapshot, args.output)
    print(json.dumps({"ok": True, "row_count": snapshot["row_count"], "sha256": snapshot["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
