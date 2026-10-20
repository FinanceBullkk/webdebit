#!/usr/bin/env python3
"""Export the cleaned book (what the loader would put in the copy) to a folder outside the repo.

User 21/10/2026: the cleaned data, not the raw xlsx, is the baseline for later comparisons. Reads
only; writes new files into an empty folder that must be outside the repository. Customer names and
amounts go into the files (sensitive, like captures/) and never to stdout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import v7_load_real_copy as loader

REPO = Path(__file__).resolve().parents[2]
CLEANING_FLAGS = (
    "ROUNDED_VND", "ROUNDING_APPORTIONED", "ROUNDED_MONTH_TOTALS", "TOTAL_SPREAD_OVER_TRIPS",
    "YEAR_END_CARRY_ADJUSTED", "INSURANCE_AS_RECEIPT", "TITLE_MONTH_FROM_DATES",
    "DUPLICATE_BLOCK_IDENTICAL", "UNTITLED_EMPTY_BLOCK", "PRICE_ONLY_ROW_IGNORED",
    "NEGATIVE_CREDIT_ROW", "SIDE_TABLE_HEADER_IGNORED", "UNLABELED_TOTAL_ROW", "CARRY_ROW_UNLABELED",
    "CSV_COUNTED_TOTAL_ROW", "CSV_STALE_ROWS", "OPENING_TOTAL_DIFFERS_FROM_HAO", "BUCKETS_FROM_SHEET",
    "OPENING_BLANK_AS_ZERO", "OPENING_ROW_ABSENT_AS_ZERO")
NOTICE = ("Dữ liệu đã làm sạch từ bản xuất Sheet; không phải bản xuất thô. Chứa tên khách và số tiền: "
          "giữ ngoài Git như captures/.")


def outside_repo(path: Path) -> Path:
    path = path.resolve()
    if path == REPO or REPO in path.parents or any((p / ".git").exists() for p in (path, *path.parents)):
        raise loader.LoadError("output must be outside the repository")
    return path


def output_folder(path: Path) -> Path:
    path = outside_repo(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise loader.LoadError("output folder is not empty; nothing is overwritten")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_books(source_dir: Path, xlsx: Path, raw_tabs: tuple[str, ...]):
    """Clean books from `xlsx` with the CSV inputs of `source_dir`; flags make the Sheet the truth."""
    temp_root = outside_repo(Path(tempfile.gettempdir()))
    with tempfile.TemporaryDirectory(dir=temp_root) as temp:
        stage = outside_repo(Path(temp))
        for name in loader.FILES:
            source = xlsx if name == "source-google-export.xlsx" else source_dir / name
            if not source.is_file():
                raise loader.LoadError("SOURCE_FILE_MISSING")
            shutil.copyfile(source, stage / name)
        previous = loader.PREFERRED_RAW_TABS, loader.SHEET_IS_TRUTH
        loader.PREFERRED_RAW_TABS, loader.SHEET_IS_TRUTH = raw_tabs, True
        try:
            books, digests, _ = loader.source_data(stage)
        finally:
            loader.PREFERRED_RAW_TABS, loader.SHEET_IS_TRUTH = previous
    return books, digests


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with outside_repo(path).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def git_state() -> dict:
    def run(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, timeout=30, check=False).stdout.strip()
    try:
        return {"commit": run("rev-parse", "HEAD"), "dirty": bool(run("status", "--porcelain", "--", "cong-no-web-handoff/tools"))}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def export(books: list[dict], digests: dict, out: Path, xlsx: Path, raw_tabs: tuple[str, ...]) -> dict:
    out = output_folder(out)
    eligible = [b for b in books if b["in_summary"] and not b["reasons"]]
    customers, months, rows, flag_customers = [], [], [], Counter()
    for item in sorted(eligible, key=lambda b: b["name"]):
        name = item["name"]
        used = {flag: count for flag, count in item["flags"].items() if flag in CLEANING_FLAGS and count}
        flag_customers.update(used.keys())
        customers.append({"customer": name, "anchor_vnd": item["anchor"], "months": len(item["checks"]),
                          "rows": len(item["legacy"]),
                          "cleaning": ";".join(f"{flag}:{count}" for flag, count in sorted(used.items()))})
        for check, opening in zip(item["checks"], item["openings"], strict=True):
            months.append({"customer": name, "debt_month": check["debt_month"][:7],
                           "opening_anchor_vnd": check["opening_anchor_vnd"],
                           "charge_vnd": check["source_charge_vnd"], "receipt_vnd": check["source_receipt_vnd"],
                           "month_end_vnd": check["replay_cumulative_vnd"],
                           "sheet_month_end_vnd": check["source_cumulative_vnd"],
                           "bucket_vnd": opening["amount_vnd"]})
        for legacy in item["legacy"]:
            rows.append({"customer": name, "debt_month": legacy["debt_month"][:7], "kind": legacy["kind"],
                         "source_tab": legacy["source_tab"], "source_row": legacy["source_row"],
                         "amount_vnd": legacy["source_total_vnd"],
                         "flags": ";".join(legacy["display"].get("flags", []))})
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "clean_customers.csv", ["customer", "anchor_vnd", "months", "rows", "cleaning"], customers)
    write_csv(out / "clean_months.csv", ["customer", "debt_month", "opening_anchor_vnd", "charge_vnd", "receipt_vnd",
                                         "month_end_vnd", "sheet_month_end_vnd", "bucket_vnd"], months)
    write_csv(out / "clean_rows.csv", ["customer", "debt_month", "kind", "source_tab", "source_row", "amount_vnd",
                                       "flags"], rows)
    manifest = {"created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "notice": NOTICE, "tool": git_state(),
                "options": {"sheet_is_truth": True, "raw_tabs_given": len(raw_tabs)},
                "source": {"xlsx_file_name": xlsx.name, "xlsx_sha256": digests["source-google-export.xlsx"],
                           "csv_inputs_sha256": {k: v for k, v in digests.items() if k.endswith(".csv")}},
                "counts": {"customers": len(customers), "months": len(months), "rows": len(rows),
                           "anchor_total_vnd": sum(c["anchor_vnd"] or 0 for c in customers),
                           "not_on_tong_tabs_skipped": sum(1 for b in books if not b["in_summary"])},
                "customers_per_cleaning_rule": dict(sorted(flag_customers.items())),
                "files_sha256": {name: sha256(out / name) for name in
                                 ("clean_customers.csv", "clean_months.csv", "clean_rows.csv")}}
    with outside_repo(out / "manifest.json").open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True, help="Sheet export to clean")
    parser.add_argument("--source-dir", type=Path, default=loader.SOURCE, help="folder with the CSV inputs")
    parser.add_argument("--out", type=Path, required=True, help="new or empty folder outside the repository")
    parser.add_argument("--raw-tab", action="append", default=[], metavar="EXACT_NAME")
    args = parser.parse_args(argv)
    try:
        out = output_folder(args.out)
    except loader.LoadError as exc:
        parser.error(str(exc))
    try:
        books, digests = build_books(args.source_dir, args.xlsx, tuple(args.raw_tab))
    except Exception as exc:  # noqa: BLE001  (any failure becomes a coded reason, never a traceback with data)
        print(json.dumps({"ok": False, "reason": loader.reason(exc)}))
        return 1
    held = [b for b in books if b["in_summary"] and b["reasons"]]
    if held:
        print(json.dumps({"ok": False, "held_customers": len(held),
                          "reason_counts": dict(sum((b["reasons"] for b in held), Counter()))}))
        return 2
    manifest = export(books, digests, out, args.xlsx, tuple(args.raw_tab))
    counts = {k: v for k, v in manifest["counts"].items() if k != "anchor_total_vnd"}  # no money on stdout
    print(json.dumps({"ok": True, "counts": counts,
                      "customers_per_cleaning_rule": manifest["customers_per_cleaning_rule"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
