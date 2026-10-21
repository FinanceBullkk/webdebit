"""Read-only replay and reconciliation of an HTH debt-sheet capture.

This is a historical calculation on exported source rows, not an approval or
posting system. It never connects to or writes to Google Sheets.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

SHEET_NAMES = ("Khách hàng", "Số dư đầu", "Chuyến hàng", "Thu & cấn trừ")
PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TYPES = {"THỰC NHẬN": "receipt", "CẤN TRỪ": "offset", "ĐIỀU CHỈNH +": "adjustment_plus", "ĐIỀU CHỈNH -": "adjustment_minus"}
NEGATIVE = {"receipt", "offset", "adjustment_minus"}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def money(value) -> int:
    if value is None or value == "" or isinstance(value, bool):
        raise ValueError("missing amount")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("VND amount is not an integer")
    return int(number)


def day(value) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError("missing date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError("invalid date") from exc


def period(value) -> str:
    if not isinstance(value, str) or not PERIOD_RE.fullmatch(value):
        raise ValueError("invalid debt period")
    return value


def load_capture(root: Path):
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if file_hash(root / manifest["source_workbook"]) != manifest["source_workbook_sha256"]:
        raise ValueError("Source workbook hash mismatch")
    tabs = {}
    for meta in manifest["tabs"]:
        path = root / meta["jsonl_file"]
        if file_hash(path) != meta["jsonl_sha256"]:
            raise ValueError(f"Tab hash mismatch: {meta['title']}")
        rows = []
        seen = set()
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line, parse_float=Decimal)
                if (record["capture_id"] != manifest["capture_id"]
                    or record["source_file_id"] != manifest["source_spreadsheet_id"]
                    or record["sheet_gid"] != meta["gid"]):
                    raise ValueError(f"Provenance mismatch: {meta['title']}")
                source_row = record["source_row"]
                if source_row in seen or len(record["values"]) != meta["grid_column_count"]:
                    raise ValueError(f"Duplicate row or width mismatch: {meta['title']}")
                seen.add(source_row)
                rows.append(record)
        if len(rows) != meta["nonempty_export_rows"]:
            raise ValueError(f"Row count mismatch: {meta['title']}")
        tabs[meta["title"]] = (meta, rows)
    if not all(name in tabs for name in SHEET_NAMES):
        raise ValueError("Missing input tab")
    return manifest, tabs


def data_rows(tabs, title):
    meta, rows = tabs[title]
    return [row for row in rows if row["source_row"] > meta["header_row"] and row["values"][0] not in (None, "")]


def input_rows(tabs, title):
    meta, rows = tabs[title]
    return [row for row in rows if row["source_row"] > meta["header_row"]]


def cell(tabs, title, row_number, column_number):
    for record in tabs[title][1]:
        if record["source_row"] == row_number:
            return record["values"][column_number - 1]
    return None


def build(root: Path, as_of: date):
    manifest, tabs = load_capture(root)
    coverage = {name: Counter() for name in SHEET_NAMES}
    decisions = []
    events = []
    exceptions = []
    balances = defaultdict(Counter)

    def exception(code, title, row, detail, customer=None, debt_period=None):
        exceptions.append({
            "code": code, "status": "CẦN KT", "resolution_status": "MỚI", "owner": None,
            "approval_evidence": None, "sheet": title,
            "sheet_gid": tabs[title][0]["gid"], "source_row": row,
            "customer": customer, "period": debt_period, "detail": detail,
        })

    def decide(title, record, result, reason=None):
        coverage[title][result] += 1
        decisions.append({
            "sheet_gid": tabs[title][0]["gid"], "source_row": record["source_row"],
            "result": result, "reason": reason,
        })

    def add_event(title, record, customer, debt_period, posting_date, kind, amount):
        signed = -amount if kind in NEGATIVE else amount
        event = {
            "customer": customer, "period": debt_period, "posting_date": posting_date.isoformat(),
            "kind": kind, "amount_vnd": amount, "signed_amount_vnd": signed,
            "sheet_gid": tabs[title][0]["gid"], "source_row": record["source_row"],
        }
        events.append(event)
        balances[(customer, debt_period)][kind] += amount

    customers = set()
    for record in input_rows(tabs, "Khách hàng"):
        row = record["values"]
        name = row[0]
        if not isinstance(name, str) or not name.strip() or name in customers or row[3] != "OK":
            decide("Khách hàng", record, "quarantined", "duplicate, blank, or failed check")
            exception("CUSTOMER_CHECK", "Khách hàng", record["source_row"], "Customer name/check requires review", name)
        else:
            customers.add(name)
            decide("Khách hàng", record, "accepted")

    def shared(title, record, customer, debt_period, posting_date, amount, kind, status_ok):
        row_no = record["source_row"]
        try:
            if customer not in customers:
                raise ValueError("customer is not in Khách hàng tab; no fuzzy match")
            p = period(debt_period)
            d = day(posting_date)
            a = money(amount)
            if not status_ok:
                raise ValueError("source row is not posted/OK")
            if d > as_of:
                decide(title, record, "excluded_as_of", "posting date after as-of")
                return
            if a < 0 and kind != "opening":
                raise ValueError("negative source amount needs classification")
            if title == "Chuyến hàng" and a == 0:
                decide(title, record, "quarantined", "zero charge needs approval evidence")
                exception("ZERO_TOTAL", title, row_no, "Source total is 0; approval evidence is not established", customer, p)
                return
        except ValueError as exc:
            decide(title, record, "quarantined", str(exc))
            code = "MISSING_TOTAL" if title == "Chuyến hàng" and amount in (None, "") else "INVALID_ROW"
            exception(code, title, row_no, str(exc), customer, debt_period)
            return
        decide(title, record, "replayed")
        add_event(title, record, customer, p, d, kind, a)

    for record in input_rows(tabs, "Số dư đầu"):
        v = record["values"]
        shared("Số dư đầu", record, v[0], v[1], v[2], v[3], "opening", v[5] == "ĐÃ GHI SỔ" and v[6] == "OK")

    for record in input_rows(tabs, "Chuyến hàng"):
        v = record["values"]
        shared("Chuyến hàng", record, v[0], v[1], v[12], v[11], "charge", v[14] == "OK")
        if v[11] not in (None, ""):
            try:
                total = money(v[11])
                components = sum(money(item) for item in (v[7], v[8], v[9], v[10]) if item not in (None, ""))
                if total != components:
                    exception("COMPONENT_DIFF", "Chuyến hàng", record["source_row"], f"total minus stated components = {total-components} VND", v[0], v[1])
            except ValueError:
                pass
        note = v[15]
        if isinstance(note, str) and any(flag in note for flag in ("GIẢ ĐỊNH", "SUY RA", "CẦN XÁC MINH", "CẦN KT", "NGÀY NGOÀI KỲ")):
            exception("SOURCE_DATE_OR_CLASSIFICATION_WARNING", "Chuyến hàng", record["source_row"], note, v[0], v[1])

    for record in input_rows(tabs, "Thu & cấn trừ"):
        v = record["values"]
        kind = TYPES.get(v[4])
        if kind is None:
            decide("Thu & cấn trừ", record, "quarantined", "unsupported transaction type")
            exception("UNSUPPORTED_TYPE", "Thu & cấn trừ", record["source_row"], str(v[4]), v[0], v[1])
            continue
        shared("Thu & cấn trừ", record, v[0], v[1], v[3], v[5], kind, v[6] == "ĐÃ GHI SỔ" and v[9] == "OK")

    for title in SHEET_NAMES:
        expected = len(input_rows(tabs, title))
        if sum(coverage[title].values()) != expected:
            raise AssertionError(f"Coverage mismatch: {title}")

    period_results = []
    customer_totals = Counter()
    for (customer, p), kinds in sorted(balances.items()):
        amount = kinds["opening"] + kinds["charge"] + kinds["adjustment_plus"] - kinds["receipt"] - kinds["offset"] - kinds["adjustment_minus"]
        customer_totals[customer] += amount
        period_results.append({"customer": customer, "period": p, **{key + "_vnd": kinds[key] for key in ("opening", "charge", "receipt", "offset", "adjustment_plus", "adjustment_minus")}, "balance_vnd": amount})

    baseline_date = day(cell(tabs, "17 Đối soát theo khách", 4, 2))
    compare_historical = baseline_date == as_of
    expected_periods = {}
    legacy_period_label_conflicts = []
    for record in data_rows(tabs, "07 Đối soát"):
        v = record["values"]
        if isinstance(v[0], str) and isinstance(v[1], str) and PERIOD_RE.fullmatch(v[1]):
            key = (v[0], v[1])
            if key in expected_periods:
                exception("DUPLICATE_BASELINE_PERIOD", "07 Đối soát", record["source_row"], "Repeated customer-period baseline", *key)
                continue
            try:
                expected_periods[key] = (money(v[9]), record["source_row"], v[11], money(v[10]) if v[10] not in (None, "") else None)
                if v[11] == "KHỚP" and v[10] not in (None, "") and money(v[10]) != 0:
                    legacy_period_label_conflicts.append({"customer": v[0], "period": v[1], "source_row": record["source_row"], "new_minus_old_vnd": money(v[10])})
            except ValueError:
                exception("INVALID_BASELINE_PERIOD", "07 Đối soát", record["source_row"], "No numeric cached period balance", *key)

    actual_periods = {(r["customer"], r["period"]): r["balance_vnd"] for r in period_results}
    period_diffs = []
    if compare_historical:
        for key, expected in sorted(expected_periods.items()):
            actual = actual_periods.get(key, 0)
            if expected[0] != actual:
                period_diffs.append({"customer": key[0], "period": key[1], "sheet_balance_vnd": expected[0], "replayed_balance_vnd": actual, "delta_vnd": actual - expected[0], "baseline_row": expected[1], "baseline_label": expected[2], "old_book_delta_vnd": expected[3]})
    period_keys_without_baseline = sorted(set(actual_periods) - set(expected_periods)) if compare_historical else []

    expected_customers = {}
    for record in data_rows(tabs, "17 Đối soát theo khách"):
        v = record["values"]
        if isinstance(v[0], str):
            with contextlib.suppress(ValueError):
                expected_customers[v[0]] = (money(v[5]), record["source_row"], money(v[7]))
    customer_diffs = []
    if compare_historical:
        for customer in sorted(set(expected_customers) | set(customer_totals)):
            expected = expected_customers.get(customer)
            actual = customer_totals.get(customer, 0)
            if expected is None or expected[0] != actual:
                customer_diffs.append({"customer": customer, "sheet_balance_vnd": expected[0] if expected else None, "replayed_balance_vnd": actual, "delta_vnd": actual - expected[0] if expected else None, "baseline_row": expected[1] if expected else None, "old_book_delta_vnd": expected[2] if expected else None})

    old_book_delta = money(cell(tabs, "17 Đối soát theo khách", 5, 8))
    old_book_nonzero_customers = [
        {"customer": name, "source_row": baseline[1], "new_minus_old_vnd": baseline[2]}
        for name, baseline in sorted(expected_customers.items()) if baseline[2] != 0
    ]
    overview_as_of = day(cell(tabs, "Tổng quan", 4, 5))
    statement_as_of = day(cell(tabs, "06 Phiếu công nợ", 4, 8))
    statement_customer = cell(tabs, "06 Phiếu công nợ", 4, 2)
    statement_period = period(cell(tabs, "06 Phiếu công nợ", 4, 5))
    statement_rollforward = sum(value for (customer, p), value in actual_periods.items() if customer == statement_customer and p <= statement_period)
    derived_checks = {
        "overview_all_periods": {"selected_as_of": overview_as_of.isoformat(), "sheet_vnd": money(cell(tabs, "Tổng quan", 7, 10)), "replayed_vnd": sum(customer_totals.values()) if overview_as_of == as_of else None},
        "statement_selected": {"customer": statement_customer, "period": statement_period, "selected_as_of": statement_as_of.isoformat(), "sheet_rollforward_vnd": money(cell(tabs, "06 Phiếu công nợ", 7, 12)), "replayed_rollforward_vnd": statement_rollforward if statement_as_of == as_of else None, "sheet_all_periods_vnd": money(cell(tabs, "06 Phiếu công nợ", 8, 12)), "replayed_all_periods_vnd": customer_totals.get(statement_customer, 0) if statement_as_of == as_of else None},
    }

    return {
        "run": {"capture_id": manifest["capture_id"], "source_spreadsheet_id": manifest["source_spreadsheet_id"], "source_workbook_sha256": manifest["source_workbook_sha256"], "as_of": as_of.isoformat(), "generated_at_utc": datetime.now(UTC).isoformat(), "engine_sha256": file_hash(Path(__file__))},
        "coverage": {title: dict(counts) for title, counts in coverage.items()},
        "totals": {"customers": len(customers), "periods": len(period_results), "events_replayed": len(events), "balance_vnd": sum(customer_totals.values())},
        "reconciliation": {"baseline_date": baseline_date.isoformat(), "comparison_status": "compared" if compare_historical else "skipped_as_of_mismatch", "period_baseline_rows": len(expected_periods), "period_diffs": period_diffs, "period_keys_without_baseline": [{"customer": customer, "period": p, "replayed_balance_vnd": actual_periods[(customer, p)]} for customer, p in period_keys_without_baseline], "customer_baseline_rows": len(expected_customers), "customer_diffs": customer_diffs, "old_book_new_minus_old_vnd": old_book_delta, "old_book_nonzero_customers": old_book_nonzero_customers, "legacy_period_label_conflicts": legacy_period_label_conflicts, "derived_view_checks": derived_checks},
        "exceptions": exceptions,
        "decisions": decisions,
        "events": events,
        "period_balances": period_results,
        "customer_balances": [{"customer": key, "balance_vnd": value} for key, value in sorted(customer_totals.items())],
        "caveat": "Historical Sheet-status replay only. No independent approval, bank evidence, GL reconciliation, or production posting is claimed.",
    }


def write_jsonl(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_csv(path: Path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def save(result, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    for field in ("decisions", "events", "exceptions"):
        write_jsonl(output_dir / f"{field}.jsonl", result[field])
    write_csv(output_dir / "period_balances.csv", result["period_balances"], ("customer", "period", "opening_vnd", "charge_vnd", "receipt_vnd", "offset_vnd", "adjustment_plus_vnd", "adjustment_minus_vnd", "balance_vnd"))
    write_csv(output_dir / "customer_balances.csv", result["customer_balances"], ("customer", "balance_vnd"))
    write_csv(output_dir / "period_diffs.csv", result["reconciliation"]["period_diffs"], ("customer", "period", "sheet_balance_vnd", "replayed_balance_vnd", "delta_vnd", "baseline_row", "baseline_label", "old_book_delta_vnd"))
    write_csv(output_dir / "period_keys_without_baseline.csv", result["reconciliation"]["period_keys_without_baseline"], ("customer", "period", "replayed_balance_vnd"))
    write_csv(output_dir / "customer_diffs.csv", result["reconciliation"]["customer_diffs"], ("customer", "sheet_balance_vnd", "replayed_balance_vnd", "delta_vnd", "baseline_row", "old_book_delta_vnd"))
    summary = {key: value for key, value in result.items() if key not in ("decisions", "events", "exceptions", "period_balances", "customer_balances")}
    summary["exception_counts"] = dict(Counter(item["code"] for item in result["exceptions"]))
    summary["exception_count"] = len(result["exceptions"])
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output_dir": str(output_dir), "totals": result["totals"], "coverage": result["coverage"], "period_diffs": len(result["reconciliation"]["period_diffs"]), "customer_diffs": len(result["reconciliation"]["customer_diffs"]), "exception_counts": summary["exception_counts"]}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--as-of", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    save(build(args.capture, args.as_of), args.output_dir)


if __name__ == "__main__":
    main()
