#!/usr/bin/env python3
"""Read customer tabs from one Sheet XLSX snapshot without joining old CSV extracts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import v7_load_real_copy as loader

REPO = Path(__file__).resolve().parents[2]


def inspect(xlsx: Path) -> dict:
    tabs = loader.scan_workbook(xlsx)
    issues = Counter()
    trips = receipts = months = 0
    rows = []
    for name, tab in tabs.items():
        issues.update(tab.get("issues", {}))
        months += len(tab.get("blocks", {}))
        trips += sum(row["kind"] == "trip" for row in tab.get("records", []))
        receipts += sum(row["kind"] == "receipt" for row in tab.get("records", []))
        for row in tab.get("records", []):
            rows.append({"customer_tab": name, "source_row": row["row"], "debt_month": row["month"],
                         "kind": row["kind"], "amount_vnd": row.get("spread", row["amount"]),
                         "date": row.get("date"), "container": row.get("container"),
                         "flags": json.dumps(sorted(row.get("flags", ())), ensure_ascii=False)})
    summary = {"source_xlsx_sha256": hashlib.sha256(xlsx.read_bytes()).hexdigest(),
            "customer_tabs": len(tabs), "months": months, "trip_rows": trips,
            "receipt_rows": receipts, "issue_counts": dict(issues),
            "notice": "Read-only direct Sheet scan; no old trips/payments CSV joined."}
    return summary, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.out.resolve()
    if output == REPO or REPO in output.parents or any((p / ".git").exists() for p in (output, *output.parents)):
        parser.error("output must be outside repository")
    if output.exists():
        parser.error("output must be new")
    summary, rows = inspect(args.xlsx)
    output.mkdir(parents=True)
    fields = ["customer_tab", "source_row", "debt_month", "kind", "amount_vnd", "date", "container", "flags"]
    with (output / "source_rows.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
