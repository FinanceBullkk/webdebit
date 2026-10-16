"""Export read-only M1 reconciliation from PostgreSQL into a private directory."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path


REPORTS = {
    "provenance": ("pilot.m1_provenance", "capture_id"),
    "coverage": ("pilot.m1_coverage", "tab_title, sheet_gid"),
    "period_balances": ("pilot.m1_period_balance", "customer, debt_period"),
    "customer_balances": ("pilot.m1_customer_balance", "customer"),
    "period_reconciliation": ("pilot.m1_period_diff", "customer, debt_period"),
    "customer_reconciliation": ("pilot.m1_customer_diff", "customer"),
    "exceptions": ("pilot.m1_exception_detail", "exception_no"),
}
EVENT_KINDS = (
    "opening", "charge", "receipt", "offset", "adjustment_plus", "adjustment_minus",
)


def parse_as_of(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise argparse.ArgumentTypeError("as-of must use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("as-of must be a valid YYYY-MM-DD date") from exc


def period_event_counts_query(capture_id: str, as_of: date) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", capture_id):
        raise ValueError("Invalid capture ID")
    if type(as_of) is not date:
        raise ValueError("Invalid as-of date")
    scope = f"capture_id = '{capture_id}' AND as_of = '{as_of.isoformat()}'::date"
    kinds = ", ".join(f"('{kind}')" for kind in EVENT_KINDS)
    return f"""SELECT p.capture_id, p.as_of, p.customer, p.debt_period, k.kind,
       count(e.event_no) AS event_count,
       count(e.amount_vnd) AS amount_nonnull_count
FROM (
    SELECT capture_id, as_of, customer, debt_period
    FROM pilot.replay_event
    WHERE {scope}
    GROUP BY capture_id, as_of, customer, debt_period
) p
CROSS JOIN (VALUES {kinds}) AS k(kind)
LEFT JOIN pilot.replay_event e
    ON e.capture_id = p.capture_id AND e.as_of = p.as_of
    AND e.customer = p.customer AND e.debt_period = p.debt_period
    AND e.kind = k.kind
GROUP BY p.capture_id, p.as_of, p.customer, p.debt_period, k.kind
ORDER BY p.customer, p.debt_period, k.kind"""


def run_psql(psql: str, dbname: str, sql: str, output: Path, sudo_user: str | None = None) -> None:
    command = [psql, "-X", "-w", "-v", "ON_ERROR_STOP=1", "-d", dbname, "-c", sql]
    if sudo_user:
        command = ["sudo", "-n", "-u", sudo_user, *command]
    with output.open("wb") as stream:
        result = subprocess.run(
            command,
            stdout=stream, stderr=subprocess.PIPE, check=False,
        )
    if result.returncode:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"psql failed: {result.stderr.decode('utf-8', errors='replace').strip()}")


def export(psql: str, dbname: str, capture_id: str, as_of: date, output_dir: Path,
           sudo_user: str | None = None) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", capture_id):
        raise ValueError("Invalid capture ID")
    if type(as_of) is not date:
        raise ValueError("Invalid as-of date")
    repo = Path(__file__).resolve().parents[2]
    if output_dir.resolve().is_relative_to(repo):
        raise ValueError("Financial reports must be written outside the source repository")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Report directory must be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    where = f"capture_id = '{capture_id}' AND as_of = '{as_of.isoformat()}'::date"
    for name, (view, order) in REPORTS.items():
        sql = f"COPY (SELECT * FROM {view} WHERE {where} ORDER BY {order}) TO STDOUT WITH (FORMAT csv, HEADER true)"
        run_psql(psql, dbname, sql, output_dir / f"{name}.csv", sudo_user)
    count_sql = ("COPY (" + period_event_counts_query(capture_id, as_of)
                 + ") TO STDOUT WITH (FORMAT csv, HEADER true)")
    run_psql(psql, dbname, count_sql, output_dir / "period_event_counts.csv", sudo_user)

    rows = {}
    for name in (*REPORTS, "period_event_counts"):
        with (output_dir / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows[name] = list(csv.DictReader(stream))
    coverage = rows["coverage"]
    if len(rows["provenance"]) != 1:
        raise ValueError("Missing or duplicate capture/run provenance")
    if len(coverage) != 4 or any(int(row["missing_rows"]) for row in coverage):
        raise ValueError("PostgreSQL source-decision coverage is incomplete")
    period_counts = Counter(row["result"] for row in rows["period_reconciliation"])
    customer_counts = Counter(row["result"] for row in rows["customer_reconciliation"])
    summary = {
        "capture_id": capture_id,
        "as_of": as_of.isoformat(),
        "baseline_date": rows["provenance"][0]["baseline_date"] or None,
        "comparison_status": "compared" if rows["provenance"][0]["baseline_date"] == as_of.isoformat() else "skipped_as_of_mismatch",
        "source_spreadsheet_id": rows["provenance"][0]["source_spreadsheet_id"],
        "source_workbook_sha256": rows["provenance"][0]["source_workbook_sha256"],
        "engine_sha256": rows["provenance"][0]["engine_sha256"],
        "source_rows": sum(int(row["source_rows"]) for row in coverage),
        "decided_rows": sum(int(row["decided_rows"]) for row in coverage),
        "events": sum(int(row["event_count"]) for row in rows["period_balances"]),
        "periods": len(rows["period_balances"]),
        "event_count_evidence_rows": len(rows["period_event_counts"]),
        "source_customers": sum(int(row["accepted_rows"]) for row in coverage if row["tab_title"] == "Khách hàng"),
        "customers_with_events": len(rows["customer_balances"]),
        "balance_vnd": sum(int(row["balance_vnd"]) for row in rows["customer_balances"]),
        "period_reconciliation": dict(period_counts),
        "customer_reconciliation": dict(customer_counts),
        "exception_counts": dict(Counter(row["code"] for row in rows["exceptions"])),
        "caveat": "Historical Sheet-status replay only; no bank, approval, GL or production posting verification.",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_id")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--as-of", required=True, type=parse_as_of)
    parser.add_argument("--dbname", default=os.environ.get("PGDATABASE", "webdebit_pilot_system"))
    parser.add_argument("--psql", default="psql")
    parser.add_argument("--sudo-user", help="Run psql through cached sudo; never pass a password here")
    args = parser.parse_args()
    print(json.dumps(export(args.psql, args.dbname, args.capture_id, args.as_of,
                            args.output_dir, args.sudo_user), ensure_ascii=False))


if __name__ == "__main__":
    main()
