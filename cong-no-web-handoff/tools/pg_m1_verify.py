"""Compare a PostgreSQL M1 report to the fixed, file-based replay and raw rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


EVENT_KINDS = (
    "opening", "charge", "receipt", "offset", "adjustment_plus", "adjustment_minus",
)
COMPONENTS = EVENT_KINDS + ("balance",)
COUNT_COLUMNS = (
    "capture_id", "as_of", "customer", "debt_period", "kind", "event_count", "amount_nonnull_count",
)


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def strict_csv_rows(path: Path, required: tuple[str, ...], *, count_evidence: bool = False) -> list[dict]:
    prefix = "Incomplete M1 count evidence; export again" if count_evidence else "Invalid M1 report"
    try:
        stream = path.open(encoding="utf-8-sig", newline="")
    except FileNotFoundError as exc:
        raise ValueError(f"{prefix}: missing {path.name}") from exc
    with stream:
        reader = csv.reader(stream)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{prefix}: missing header in {path.name}") from exc
        if len(header) != len(set(header)):
            raise ValueError(f"{prefix}: duplicate columns in {path.name}")
        missing = set(required) - set(header)
        if missing:
            raise ValueError(f"{prefix}: missing columns in {path.name}: {', '.join(sorted(missing))}")
        positions = {name: header.index(name) for name in required}
        rows = []
        for row_no, values in enumerate(reader, 2):
            if len(values) != len(header):
                raise ValueError(f"{prefix}: malformed row {row_no} in {path.name}")
            rows.append({name: values[index] for name, index in positions.items()})
        return rows


def integer(value, label: str, *, nullable: bool = False) -> int | None:
    if value is None or value == "":
        if nullable:
            return None
        raise ValueError(f"Missing integer amount/count: {label}")
    if isinstance(value, bool):
        raise ValueError(f"Invalid integer amount/count: {label}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?(0|[1-9][0-9]*)", value):
        return int(value)
    raise ValueError(f"Invalid integer amount/count: {label}")


def iso_date(value, label: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError(f"Invalid date: {label}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid date: {label}") from exc


def valid_period(value) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", value):
        return False
    try:
        date.fromisoformat(value + "-01")
    except ValueError:
        return False
    return True


def unique_periods(path: Path, *, source: bool) -> dict[tuple[str, str], dict]:
    required = ("customer", "period", "balance_vnd", *(kind + "_vnd" for kind in EVENT_KINDS)) if source else (
        "customer", "debt_period", "event_count", "balance_vnd",
        *(kind + "_vnd" for kind in EVENT_KINDS),
    )
    rows = strict_csv_rows(path, required)
    result = {}
    for row in rows:
        customer = row["customer"]
        period = row["period"] if source else row["debt_period"]
        if not customer or not valid_period(period):
            raise ValueError(f"Invalid period key in {path.name}")
        key = (customer, period)
        if key in result:
            raise ValueError(f"Duplicate period key in {path.name}")
        values = {}
        for component in COMPONENTS:
            values[component] = integer(row[component + "_vnd"], component, nullable=component != "balance")
        if not source:
            count = integer(row["event_count"], "event_count")
            if count < 0:
                raise ValueError("Invalid negative period event_count")
            values["event_count"] = count
        result[key] = values
    return result


def read_source_events(replay_dir: Path, as_of: str):
    path = replay_dir / "events.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError("Source event evidence missing: events.jsonl") from exc
    counts = Counter()
    nonnull = Counter()
    amounts = defaultdict(int)
    snapshot = iso_date(as_of, "run.as_of")
    for line_no, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid source event JSON at line {line_no}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"Invalid source event at line {line_no}: expected object")
        required = ("customer", "period", "posting_date", "kind", "signed_amount_vnd", "sheet_gid", "source_row")
        missing = [name for name in required if name not in event]
        if missing:
            raise ValueError(f"Invalid source event at line {line_no}: missing {', '.join(missing)}")
        customer, period, kind = event["customer"], event["period"], event["kind"]
        if not isinstance(customer, str) or not customer:
            raise ValueError(f"Invalid source event customer at line {line_no}")
        if not valid_period(period):
            raise ValueError(f"Invalid source event period at line {line_no}")
        if kind not in EVENT_KINDS:
            raise ValueError(f"Invalid source event kind at line {line_no}")
        posting_date = iso_date(event["posting_date"], f"events.jsonl:{line_no} posting_date")
        if posting_date > snapshot:
            raise ValueError(f"Source event is outside as-of snapshot at line {line_no}")
        if type(event["sheet_gid"]) is not int or event["sheet_gid"] < 0:
            raise ValueError(f"Invalid source event key sheet_gid at line {line_no}")
        if type(event["source_row"]) is not int or event["source_row"] <= 0:
            raise ValueError(f"Invalid source event key source_row at line {line_no}")
        signed = event["signed_amount_vnd"]
        if type(signed) is not int:
            raise ValueError(f"Invalid source event signed amount at line {line_no}")
        key = (customer, period, kind)
        counts[key] += 1
        amount = event.get("amount_vnd")
        if amount is not None:
            if type(amount) is not int:
                raise ValueError(f"Invalid source event amount at line {line_no}")
            nonnull[key] += 1
            amounts[key] += amount
    return counts, nonnull, amounts


def read_db_counts(path: Path, period_keys: set[tuple[str, str]], capture_id: str, as_of: str) -> dict:
    rows = strict_csv_rows(path, COUNT_COLUMNS, count_evidence=True)
    result = {}
    for row in rows:
        customer, period, kind = row["customer"], row["debt_period"], row["kind"]
        if row["capture_id"] != capture_id or row["as_of"] != as_of:
            raise ValueError("Count evidence capture/as-of scope differs from replay; export again")
        if not customer or not valid_period(period) or kind not in EVENT_KINDS:
            raise ValueError("Invalid count evidence key or kind; export again")
        key = (customer, period, kind)
        if key in result:
            raise ValueError("Duplicate count evidence row; export again")
        total = integer(row["event_count"], "event_count")
        nonnull = integer(row["amount_nonnull_count"], "amount_nonnull_count")
        if total < 0 or nonnull < 0 or nonnull > total:
            raise ValueError("Invalid count evidence values; export again")
        result[key] = (total, nonnull)
    required = {(customer, period, kind) for customer, period in period_keys for kind in EVENT_KINDS}
    if result.keys() != required:
        raise ValueError("Missing or extra period/kind count evidence; export again")
    return result


def verify(capture_dir: Path, replay_dir: Path, db_report_dir: Path) -> dict:
    expected = json.loads((replay_dir / "summary.json").read_text(encoding="utf-8"))
    actual = json.loads((db_report_dir / "summary.json").read_text(encoding="utf-8"))
    run = expected["run"]
    for field in ("capture_id", "source_spreadsheet_id", "source_workbook_sha256", "engine_sha256", "as_of"):
        if actual.get(field) != run[field]:
            raise ValueError(f"DB provenance differs from replay: {field}")
    if (actual.get("baseline_date") != expected["reconciliation"]["baseline_date"]
            or actual.get("comparison_status") != "compared"):
        raise ValueError("DB baseline date is missing or differs from replay as-of")
    summary_counts = {
        "DB source_rows": actual.get("source_rows"),
        "DB decided_rows": actual.get("decided_rows"),
        "DB events": actual.get("events"),
        "DB periods": actual.get("periods"),
        "DB source_customers": actual.get("source_customers"),
        "Replay events_replayed": expected["totals"].get("events_replayed"),
        "Replay periods": expected["totals"].get("periods"),
        "Replay customers": expected["totals"].get("customers"),
    }
    if any(type(value) is not int for value in summary_counts.values()):
        raise ValueError("Summary count fields must be exact integers")
    db_balance = actual.get("balance_vnd")
    replay_balance = expected["totals"].get("balance_vnd")
    if type(db_balance) is not int or type(replay_balance) is not int:
        raise ValueError("Summary balance fields must be exact integer VND")
    if (actual["source_rows"] != actual["decided_rows"]
            or actual["events"] != summary_counts["Replay events_replayed"]
            or actual["periods"] != summary_counts["Replay periods"]
            or actual["source_customers"] != summary_counts["Replay customers"]
            or db_balance != replay_balance):
        raise ValueError("DB coverage or aggregate totals differ from replay")

    for row in csv_rows(db_report_dir / "coverage.csv"):
        source = expected["coverage"][row["tab_title"]]
        for key in ("accepted", "replayed", "quarantined", "excluded_as_of"):
            if integer(row[key + "_rows"], f"coverage {key}") != source.get(key, 0):
                raise ValueError(f"DB coverage differs: {row['tab_title']} {key}")

    old_periods = unique_periods(replay_dir / "period_balances.csv", source=True)
    db_periods = unique_periods(db_report_dir / "period_balances.csv", source=False)
    if old_periods.keys() != db_periods.keys():
        raise ValueError("DB period keys differ from replay")
    period_keys = set(old_periods)
    source_counts, source_nonnull, source_amounts = read_source_events(replay_dir, run["as_of"])
    source_periods = {(customer, period) for customer, period, _ in source_counts}
    if source_periods != period_keys:
        raise ValueError("Source event period keys differ from replay; export/replay evidence is incomplete")
    db_counts = read_db_counts(db_report_dir / "period_event_counts.csv", period_keys, run["capture_id"], run["as_of"])
    count_total = sum(total for total, _ in db_counts.values())
    source_total = sum(source_counts.values())
    if source_total != count_total or count_total != sum(row["event_count"] for row in db_periods.values()):
        raise ValueError("Source, DB count evidence, and period event totals differ")
    if count_total != summary_counts["DB events"]:
        raise ValueError("DB count evidence differs from summary event total")
    evidence_rows = actual.get("event_count_evidence_rows")
    if type(evidence_rows) is not int or evidence_rows != len(db_counts):
        raise ValueError("Count evidence row total missing or differs; export again")

    for customer, period in period_keys:
        period_total = 0
        for kind in EVENT_KINDS:
            key = (customer, period, kind)
            source_count = source_counts[key]
            source_amount_count = source_nonnull[key]
            db_count, db_amount_count = db_counts[key]
            if source_count != source_amount_count:
                raise ValueError("Source event amount missing; event-count evidence is incomplete")
            if db_count != db_amount_count:
                raise ValueError("DB event amount missing; database amount evidence is incomplete")
            if (source_count, source_amount_count) != (db_count, db_amount_count):
                raise ValueError("Source and DB event counts differ")
            period_total += db_count
            source_aggregate = old_periods[(customer, period)][kind]
            db_aggregate = db_periods[(customer, period)][kind]
            if source_count == 0:
                if source_aggregate not in (None, 0) or db_aggregate not in (None, 0):
                    raise ValueError("Nonzero aggregate without source or DB events")
                continue
            if source_aggregate is None:
                raise ValueError("Source amount aggregate missing despite event count")
            if db_aggregate is None:
                raise ValueError("DB amount aggregate missing despite event count")
            event_amount = source_amounts[key]
            if source_aggregate != event_amount:
                raise ValueError("Source event amount differs from replay aggregate")
            if db_aggregate != event_amount:
                raise ValueError("DB amount aggregate differs from source events")
        if period_total != db_periods[(customer, period)]["event_count"]:
            raise ValueError("DB period event count differs from count evidence")
        old_balance = old_periods[(customer, period)]["balance"]
        db_balance = db_periods[(customer, period)]["balance"]
        if old_balance is None or db_balance is None:
            raise ValueError("Period balance missing")
        if old_balance != db_balance:
            raise ValueError("DB period balance differs from replay")

    old_customers = {r["customer"]: integer(r["balance_vnd"], "source customer balance")
                     for r in csv_rows(replay_dir / "customer_balances.csv")}
    db_customers = {r["customer"]: integer(r["balance_vnd"], "DB customer balance")
                    for r in csv_rows(db_report_dir / "customer_balances.csv")}
    if old_customers != db_customers:
        raise ValueError("DB customer balances differ from replay")

    period_recon = csv_rows(db_report_dir / "period_reconciliation.csv")
    customer_recon = csv_rows(db_report_dir / "customer_reconciliation.csv")
    if any(r["delta_vnd"] and integer(r["delta_vnd"], "period/customer delta") != 0
           for r in period_recon + customer_recon):
        raise ValueError("Nonzero DB baseline difference")
    no_baseline = {(r["customer"], r["debt_period"]) for r in period_recon if r["result"] == "NO_BASELINE"}
    expected_no_baseline = {(r["customer"], r["period"]) for r in csv_rows(replay_dir / "period_keys_without_baseline.csv")}
    if no_baseline != expected_no_baseline:
        raise ValueError("Unmatched period baseline keys differ")
    if sum(integer(r["old_book_delta_vnd"] or "0", "old book delta") for r in customer_recon) != expected["reconciliation"]["old_book_new_minus_old_vnd"]:
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
    db_keys = Counter((r["code"], integer(r["sheet_gid"], "exception sheet_gid"), integer(r["source_row"], "exception source_row"), r["detail"]) for r in db_exceptions)
    old_keys = Counter((r["code"], r["sheet_gid"], r["source_row"], r["detail"]) for r in old_exceptions)
    if db_keys != old_keys:
        raise ValueError("DB exceptions differ from replay")
    for row in db_exceptions:
        key = (integer(row["sheet_gid"], "exception sheet_gid"), integer(row["source_row"], "exception source_row"))
        if row["row_sha256"] != raw_hashes.get(key):
            raise ValueError(f"Exception raw-row hash differs: {key}")
        expected_url = f"https://docs.google.com/spreadsheets/d/{run['source_spreadsheet_id']}/edit#gid={key[0]}&range=A{key[1]}"
        if row["source_url"] != expected_url:
            raise ValueError(f"Exception source URL differs: {key}")
    return {"periods_checked": len(old_periods), "customers_checked": len(old_customers),
            "exceptions_checked": len(db_exceptions), "period_keys_without_baseline": len(no_baseline),
            "old_book_delta_vnd": expected["reconciliation"]["old_book_new_minus_old_vnd"],
            "event_count_rows_checked": len(db_counts), "events_checked": source_total}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("replay_dir", type=Path)
    parser.add_argument("db_report_dir", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.capture_dir, args.replay_dir, args.db_report_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
