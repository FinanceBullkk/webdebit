"""Compare every opening row in a ledger export with the pinned M1 report."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def verify(report: Path, export: Path) -> dict[str, int]:
    source = csv_rows(report / "period_balances.csv")
    comparison = csv_rows(report / "period_reconciliation.csv")
    actual = csv_rows(export)
    flags = {(r["customer"], r["debt_period"]): r["result"] for r in comparison}
    expected = {(r["customer"], r["debt_period"]):
                (int(r["balance_vnd"]), int(r["event_count"]),
                 flags[(r["customer"], r["debt_period"])]) for r in source}
    got = {(r["customer"], r["debt_period"]):
           (int(r["balance_vnd"]), int(r["replay_event_count"]),
            r["comparison_status"]) for r in actual}
    if len(expected) != 496 or len(got) != 496 or len(actual) != 496 or got != expected:
        missing = set(expected) - set(got)
        extra = set(got) - set(expected)
        changed = {key for key in set(expected) & set(got) if expected[key] != got[key]}
        raise ValueError(f"ledger opening differs: missing={len(missing)} extra={len(extra)} changed={len(changed)}")
    total = sum(value[0] for value in got.values())
    if total != 65051673578 or sum(v[2] == "NO_BASELINE" for v in got.values()) != 46:
        raise ValueError("ledger total or flags differ")
    return {"periods": len(got), "balance_vnd": total,
            "no_baseline": 46}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    print(verify(args.report, args.export))


if __name__ == "__main__":
    main()
