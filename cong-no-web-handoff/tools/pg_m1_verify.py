"""Compare a PostgreSQL M1 report to the fixed, file-based replay and raw rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def verify(capture_dir: Path, replay_dir: Path, db_report_dir: Path) -> dict:
    expected = json.loads((replay_dir / "summary.json").read_text(encoding="utf-8"))
    actual = json.loads((db_report_dir / "summary.json").read_text(encoding="utf-8"))
    run = expected["run"]
    for field in ("capture_id", "source_spreadsheet_id", "source_workbook_sha256", "engine_sha256", "as_of"):
        if actual[field] != run[field]:
            raise ValueError(f"DB provenance differs from replay: {field}")
    if (actual["baseline_date"] != expected["reconciliation"]["baseline_date"]
            or actual["comparison_status"] != "compared"):
        raise ValueError("DB baseline date is missing or differs from replay as-of")
    if (actual["source_rows"] != actual["decided_rows"]
            or actual["events"] != expected["totals"]["events_replayed"]
            or actual["periods"] != expected["totals"]["periods"]
            or actual["source_customers"] != expected["totals"]["customers"]
            or actual["balance_vnd"] != expected["totals"]["balance_vnd"]):
        raise ValueError("DB coverage or aggregate totals differ from replay")

    for row in csv_rows(db_report_dir / "coverage.csv"):
        source = expected["coverage"][row["tab_title"]]
        for key in ("accepted", "replayed", "quarantined", "excluded_as_of"):
            if int(row[key + "_rows"]) != source.get(key, 0):
                raise ValueError(f"DB coverage differs: {row['tab_title']} {key}")

    old_periods = {(r["customer"], r["period"]): r for r in csv_rows(replay_dir / "period_balances.csv")}
    db_periods = {(r["customer"], r["debt_period"]): r for r in csv_rows(db_report_dir / "period_balances.csv")}
    if old_periods.keys() != db_periods.keys():
        raise ValueError("DB period keys differ from replay")
    components = ("opening", "charge", "receipt", "offset", "adjustment_plus", "adjustment_minus", "balance")
    for key, old in old_periods.items():
        db = db_periods[key]
        for component in components:
            column = component + "_vnd"
            if int(old[column] or 0) != int(db[column] or 0):
                raise ValueError(f"DB period component differs: {key} {component}")
    old_customers = {r["customer"]: int(r["balance_vnd"]) for r in csv_rows(replay_dir / "customer_balances.csv")}
    db_customers = {r["customer"]: int(r["balance_vnd"]) for r in csv_rows(db_report_dir / "customer_balances.csv")}
    if old_customers != db_customers:
        raise ValueError("DB customer balances differ from replay")

    period_recon = csv_rows(db_report_dir / "period_reconciliation.csv")
    customer_recon = csv_rows(db_report_dir / "customer_reconciliation.csv")
    if any(r["delta_vnd"] and int(r["delta_vnd"]) != 0 for r in period_recon + customer_recon):
        raise ValueError("Nonzero DB baseline difference")
    no_baseline = {(r["customer"], r["debt_period"]) for r in period_recon if r["result"] == "NO_BASELINE"}
    expected_no_baseline = {(r["customer"], r["period"]) for r in csv_rows(replay_dir / "period_keys_without_baseline.csv")}
    if no_baseline != expected_no_baseline:
        raise ValueError("Unmatched period baseline keys differ")
    if sum(int(r["old_book_delta_vnd"] or 0) for r in customer_recon) != expected["reconciliation"]["old_book_new_minus_old_vnd"]:
        raise ValueError("Historical old-book difference changed")

    manifest = json.loads((capture_dir / "manifest.json").read_text(encoding="utf-8"))
    raw_hashes = {}
    for tab in manifest["tabs"]:
        with (capture_dir / tab["jsonl_file"]).open("rb") as stream:
            for line in stream:
                record = json.loads(line)
                raw_hashes[(record["sheet_gid"], record["source_row"])] = hashlib.sha256(line).hexdigest()
    db_exceptions = csv_rows(db_report_dir / "exceptions.csv")
    old_exceptions = [json.loads(line) for line in (replay_dir / "exceptions.jsonl").read_text(encoding="utf-8").splitlines()]
    db_keys = Counter((r["code"], int(r["sheet_gid"]), int(r["source_row"]), r["detail"]) for r in db_exceptions)
    old_keys = Counter((r["code"], r["sheet_gid"], r["source_row"], r["detail"]) for r in old_exceptions)
    if db_keys != old_keys:
        raise ValueError("DB exceptions differ from replay")
    for row in db_exceptions:
        key = (int(row["sheet_gid"]), int(row["source_row"]))
        if row["row_sha256"] != raw_hashes.get(key):
            raise ValueError(f"Exception raw-row hash differs: {key}")
        expected_url = f"https://docs.google.com/spreadsheets/d/{run['source_spreadsheet_id']}/edit#gid={key[0]}&range=A{key[1]}"
        if row["source_url"] != expected_url:
            raise ValueError(f"Exception source URL differs: {key}")
    return {"periods_checked": len(old_periods), "customers_checked": len(old_customers),
            "exceptions_checked": len(db_exceptions), "period_keys_without_baseline": len(no_baseline),
            "old_book_delta_vnd": expected["reconciliation"]["old_book_new_minus_old_vnd"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("replay_dir", type=Path)
    parser.add_argument("db_report_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.capture_dir, args.replay_dir, args.db_report_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
