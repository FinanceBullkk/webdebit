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


def commodity_counts(books: list[dict]) -> dict:
    """Books per commodity/mode (MH-01); no customer names, safe for stdout."""
    counts = Counter("CHUA_PHAN_LOAI" if not b.get("commodity") else
                     b["commodity"] + (f" {b['transport_mode']}" if b.get("transport_mode") else "")
                     for b in books)
    counts["NHAN_LA"] = sum(bool(b.get("commodity_label_unknown")) for b in books)
    return dict(sorted(counts.items()))


def export(books: list[dict], digests: dict, out: Path, xlsx: Path, raw_tabs: tuple[str, ...]) -> dict:
    out = output_folder(out)
    eligible = [b for b in books if b["in_summary"] and not b["reasons"]]
    control_total = sum(b["anchor"] for b in eligible)
    loader.validate_books(eligible, control_total)
    customers, months, rows, flag_customers = [], [], [], Counter()
    def structured(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    for item in eligible:
        name = item["name"]
        used = {flag: count for flag, count in item["flags"].items() if flag in CLEANING_FLAGS and count}
        flag_customers.update(used.keys())
        customers.append({"customer": name, "ordinal": item["ordinal"], "anchor_vnd": item["anchor"],
                          "months": len(item["checks"]), "rows": len(item["legacy"]),
                          "cleaning": ";".join(f"{flag}:{count}" for flag, count in sorted(used.items())),
                          "flags": structured(item["flags"]), "csv_only": structured(item.get("csv_only", [])),
                          "row_counts": structured(item["row_counts"]),
                          "metadata": structured({k: item[k] for k in ("has_insurance", "commodity", "transport_mode")
                                                  if k in item})})
        for check, opening in zip(item["checks"], item["openings"], strict=True):
            months.append({"customer": name, "debt_month": check["debt_month"][:7],
                           "opening_anchor_vnd": check["opening_anchor_vnd"],
                           "charge_vnd": check["source_charge_vnd"], "receipt_vnd": check["source_receipt_vnd"],
                           "month_end_vnd": check["replay_cumulative_vnd"],
                           "sheet_month_end_vnd": check["source_cumulative_vnd"],
                           "bucket_vnd": opening["amount_vnd"],
                           **{k: check[k] for k in ("source_evidence_sha256", "standard_bucket_vnd",
                                                   "standard_source_ref", "standard_source_sha256")},
                           "exception_codes": structured(check["exception_codes"]),
                           "source_tab": opening["source_tab"], "source_row": opening["source_row"]})
        for legacy in item["legacy"]:
            display = legacy["display"]
            rows.append({"customer": name, "debt_month": legacy["debt_month"][:7], "kind": legacy["kind"],
                         "source_tab": legacy["source_tab"], "source_row": legacy["source_row"],
                         "amount_vnd": legacy["source_total_vnd"],
                         **{k: structured(display[k]) if k in ("cells", "flags") else display[k]
                            for k in loader.DISPLAY_FIELDS},
                         "null_fields": structured([k for k in loader.DISPLAY_FIELDS if display[k] is None])})
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "clean_customers.csv", ["customer", "ordinal", "anchor_vnd", "months", "rows", "cleaning",
                                          "flags", "csv_only", "row_counts", "metadata"], customers)
    write_csv(out / "clean_months.csv", ["customer", "debt_month", "opening_anchor_vnd", "charge_vnd", "receipt_vnd",
                                       "month_end_vnd", "sheet_month_end_vnd", "bucket_vnd", "exception_codes",
                                       "source_evidence_sha256", "standard_bucket_vnd", "standard_source_ref",
                                       "standard_source_sha256", "source_tab", "source_row"], months)
    write_csv(out / "clean_rows.csv", ["customer", "debt_month", "kind", "source_tab", "source_row", "amount_vnd",
                                     *loader.DISPLAY_FIELDS, "null_fields"], rows)
    manifest = {"created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "notice": NOTICE, "tool": git_state(),
                "options": {"sheet_is_truth": True, "raw_tabs_given": len(raw_tabs)},
                "source": {"xlsx_file_name": xlsx.name, "xlsx_sha256": digests["source-google-export.xlsx"],
                           "csv_inputs_sha256": {k: v for k, v in digests.items() if k.endswith(".csv")}},
                "format_version": loader.CLEAN_FORMAT_VERSION,
                "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "control_total_vnd": control_total,
                "excluded_counts": dict(Counter(reason for b in books if b not in eligible
                                                for reason in (["NOT_ON_TONG"] if not b["in_summary"]
                                                               else b["reasons"].keys()))),
                "counts": loader.clean_counts(eligible),
                "customers_per_cleaning_rule": dict(sorted(flag_customers.items())),
                "commodity_counts": commodity_counts(eligible),
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
    parser.add_argument("--hold-out", action="store_true",
                        help="đối soát: bỏ khách bị giữ, ghi tên và lý do vào held.csv; không dùng để nạp")
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
    reason_counts = dict(sum((b["reasons"] for b in held), Counter()))
    if held and not args.hold_out:
        print(json.dumps({"ok": False, "held_customers": len(held), "reason_counts": reason_counts}))
        return 2
    try:
        manifest = export([b for b in books if b not in held], digests, out, args.xlsx, tuple(args.raw_tab))
        if held:
            # Bản đối soát thiếu khách: đối soát sẽ báo họ là CHI_CO_WEB, không bao giờ "đạt" thay họ.
            write_csv(out / "held.csv", ["customer", "reasons"],
                      [{"customer": b["name"], "reasons": json.dumps(dict(b["reasons"]), sort_keys=True)}
                       for b in held])
    except loader.LoadError as exc:
        print(json.dumps({"ok": False, "reason": loader.reason(exc)}))
        return 2
    counts = {k: v for k, v in manifest["counts"].items() if k != "anchor_total_vnd"}  # no money on stdout
    print(json.dumps({"ok": True, "counts": counts,
                      **({"held_customers": len(held), "reason_counts": reason_counts} if held else {}),
                      "customers_per_cleaning_rule": manifest["customers_per_cleaning_rule"],
                      "commodity_counts": manifest["commodity_counts"]}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
