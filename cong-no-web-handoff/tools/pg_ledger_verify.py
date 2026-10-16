"""Compare every opening row in a ledger export with the pinned M1 report."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def verify(report: Path, export: Path, *, expect_periods: int, expect_total_vnd: int,
           expect_no_baseline: int) -> dict[str, int]:
    if expect_periods <= 0 or expect_total_vnd <= 0 or not 0 <= expect_no_baseline <= expect_periods:
        raise ValueError("expectations must be positive and no_baseline cannot exceed periods")
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
    if (len(expected) != expect_periods or len(got) != expect_periods
            or len(actual) != expect_periods or got != expected):
        missing = set(expected) - set(got)
        extra = set(got) - set(expected)
        changed = {key for key in set(expected) & set(got) if expected[key] != got[key]}
        raise ValueError(f"ledger opening differs: missing={len(missing)} extra={len(extra)} changed={len(changed)}")
    total = sum(value[0] for value in got.values())
    no_baseline = sum(v[2] == "NO_BASELINE" for v in got.values())
    if total != expect_total_vnd or no_baseline != expect_no_baseline:
        raise ValueError("ledger total or flags differ")
    return {"periods": len(got), "balance_vnd": total,
            "no_baseline": no_baseline}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("export", type=Path)
    parser.add_argument("--expect-periods", type=int, required=True)
    parser.add_argument("--expect-total-vnd", type=int, required=True)
    parser.add_argument("--expect-no-baseline", type=int, required=True)
    args = parser.parse_args()
    print(verify(args.report, args.export, expect_periods=args.expect_periods,
                 expect_total_vnd=args.expect_total_vnd, expect_no_baseline=args.expect_no_baseline))


if __name__ == "__main__":
    main()
