#!/usr/bin/env python3
"""Read-only report: which Sheet unit prices could be written to which web trip.

Usage: --xlsx SHEET.xlsx (--ledger-json DIR | --api URL [--serve-host HOST]) --out NEW_DIR

Measures the match rate before any price queue or write path exists. Each Sheet trip
row (customer tab) is matched to one web trip or original-book row of the customer
with the same tab name: same container, exact date first, then within 3 days.
Customer tabs carry no booking column, so booking cannot be part of the key.
Nothing is written to Sheet, API or DB. Names and money go only into files in a
new folder outside the repository; stdout carries counts only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from html import escape
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import v7_load_real_copy as loader
import v7_reconcile_sheet as rec

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_price_queue as queue  # tools may use the web layer; never the reverse

DATE_WINDOW_DAYS = queue.DATE_WINDOW_DAYS
STATUSES = ("READY", "PRICE_UNCHANGED", "CONFLICT", "MONTH_LOCKED", "MANUAL", "PENDING_REVIEW",
            "AMBIGUOUS", "AMBIGUOUS_PRICED", "NOT_FOUND", "NO_CUSTOMER", "SHEET_NO_PRICE", "NO_CONTAINER")
LABELS = {"READY": "Ghi được (web chưa có giá)", "PRICE_UNCHANGED": "Giá đã giống",
          "CONFLICT": "Web có giá khác Sheet", "MONTH_LOCKED": "Ghi được nhưng tháng khóa",
          "MANUAL": "Phụ phí đã phân loại hoặc giá âm: nhập trong sổ",
          "PENDING_REVIEW": "Chuyến đang CHỜ KIỂM", "AMBIGUOUS": "Khớp nhiều dòng",
          "AMBIGUOUS_PRICED": "Khớp nhiều dòng, đều đã có giá",
          "NOT_FOUND": "Không tìm thấy trên web", "NO_CUSTOMER": "Không có khách trên web",
          "SHEET_NO_PRICE": "Sheet chưa có giá", "NO_CONTAINER": "Dòng không container"}
FIELDS = ["customer_tab", "source_row", "debt_month", "container", "date", "sheet_unit_price_vnd",
          "sheet_other_fee_vnd", "sheet_total_vnd", "customer_basis", "status", "match_basis", "target_kind",
          "target_id", "web_unit_price_vnd", "web_other_fee_vnd", "web_total_vnd"]


def sheet_rows(xlsx: Path) -> list[dict]:
    return rows_from_scan(loader.scan_workbook(xlsx))


def rows_from_scan(scan: dict[str, dict]) -> list[dict]:
    """Trip rows of customer tabs from `scan_tabs` output, whichever reader produced the cells."""
    rows = []
    for tab, data in scan.items():
        for record in data.get("records", []):
            if record["kind"] != "trip":
                continue
            details = record.get("details", {})
            rows.append({"customer_tab": tab, "source_row": record["row"], "debt_month": record["month"],
                         "container": queue.container_key(record.get("container")), "date": record.get("date"),
                         "sheet_unit_price_vnd": details.get("unit_price"),
                         "sheet_other_fee_vnd": details.get("fee"), "sheet_total_vnd": record.get("amount")})
    return rows


def match(rows: list[dict], ledgers: dict[str, dict]) -> list[dict]:
    """Ledgers keyed by web customer name; `_display_name`/`_aliases` come from /api/v7/customers."""
    owned = queue.owners([{"key": key, "name": key, "display_name": ledger.get("_display_name"),
                           "aliases": ledger.get("_aliases")} for key, ledger in ledgers.items()])
    pools = {key: queue.targets(ledger) for key, ledger in ledgers.items()}
    results = []
    for row in rows:
        key, basis = owned.get(queue.name_key(row["customer_tab"]), (None, ""))
        results.append(queue.classify(row, pools.get(key)) | {"customer_basis": basis})
    return queue.mark_shared(results)


def read_ledger_dir(folder: Path) -> tuple[dict, dict]:
    if not folder.is_dir():
        raise rec.InputError("ledger-json must be directory")
    ledgers, hashes = {}, {}
    for path in sorted(folder.glob("*.json")):
        content = path.read_bytes()
        key = rec.name(path.stem)
        if key in ledgers:
            raise rec.InputError("duplicate web customer")
        ledgers[key] = rec.decode(content)
        hashes[path.name] = hashlib.sha256(content).hexdigest()
    return ledgers, hashes


def read_ledger_api(value: str, serve_hosts=()) -> tuple[dict, dict]:
    base = rec.api_base(value, serve_hosts)
    opener = build_opener(ProxyHandler({}), rec.NoRedirect())
    ledgers, hashes = {}, {}

    def get(route):
        with opener.open(base + route, timeout=10) as response:
            raw = response.read()
        hashes[route] = hashlib.sha256(raw).hexdigest()
        return rec.decode(raw)
    rows = get("/api/v7/customers").get("customers")
    if not isinstance(rows, list):
        raise rec.InputError("missing API customers")
    for row in rows:
        if not isinstance(row, dict) or type(row.get("id")) is not int:
            raise rec.InputError("invalid API customer")
        key = rec.name(row.get("name"))
        if key in ledgers:
            raise rec.InputError("duplicate API customer")
        ledgers[key] = {**get(f"/api/v7/ledger?customer={row['id']}"),
                        "_display_name": row.get("display_name"), "_aliases": row.get("aliases") or []}
    return ledgers, hashes


def write_html(path: Path, results: list[dict], counts: Counter) -> None:
    def vnd(value):
        return "—" if value is None else f"{value:,}".replace(",", ".")
    shown = [r for r in results if r["status"] not in ("PRICE_UNCHANGED", "NO_CONTAINER", "AMBIGUOUS_PRICED")]
    rows = "".join(
        f"<tr><td>{escape(str(r['customer_tab']))}</td><td>{r['source_row']}</td><td>{escape(str(r['container']))}</td>"
        f"<td>{escape(str(r['date'] or '—'))}</td><td>{vnd(r['sheet_unit_price_vnd'])}</td><td>{vnd(r['web_unit_price_vnd'])}</td>"
        f"<td>{escape(LABELS[r['status']])}</td><td>{escape(r['match_basis'])}</td></tr>" for r in shown)
    summary = "".join(f"<tr><td>{escape(LABELS[s])}</td><td>{counts[s]}</td></tr>" for s in STATUSES)
    path.write_text(
        '<!doctype html><meta charset="utf-8"><title>Ghép giá Sheet–web</title>'
        "<style>body{font:14px/1.4 Segoe UI,system-ui,sans-serif;margin:24px;color:#17324d}"
        "table{border-collapse:collapse;margin:12px 0}th,td{border:1px solid #cbd8e5;padding:5px 8px}th{background:#e8f1fa}</style>"
        "<h1>Ghép giá Sheet → web (chỉ đọc)</h1><p>Không ghi gì. Dòng giá đã giống và dòng không container không liệt kê.</p>"
        f"<table><tr><th>Trạng thái</th><th>Số dòng</th></tr>{summary}</table>"
        "<table><tr><th>Tab</th><th>Dòng</th><th>Container</th><th>Ngày</th><th>Giá Sheet</th><th>Giá web</th>"
        f"<th>Trạng thái</th><th>Ghép theo</th></tr>{rows}</table>", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--ledger-json", type=Path, help="JSON directory; filename stems are customer names")
    source.add_argument("--api", help="HTTP loopback with port or HTTPS Serve base URL")
    parser.add_argument("--serve-host", action="append", default=[])
    parser.add_argument("--out", type=Path, required=True, help="new directory outside repositories")
    args = parser.parse_args(argv)
    try:
        out = rec.output_path(args.out)
        ledgers, hashes = (read_ledger_dir(args.ledger_json) if args.ledger_json
                           else read_ledger_api(args.api, args.serve_host))
        results = match(sheet_rows(args.xlsx), ledgers)
    except (rec.InputError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 2
    counts = Counter(r["status"] for r in results)
    basis = Counter(r["match_basis"] for r in results if r["match_basis"])
    basis.update(f"customer_{r['customer_basis']}" for r in results if r["customer_basis"] == "alias")
    out.mkdir(parents=True)
    rec.write_csv(out / "price_match_rows.csv", FIELDS, results)
    summary = {"counts": {s: counts[s] for s in STATUSES}, "match_basis": dict(basis), "rows": len(results),
               "web_customers": len(ledgers), "date_window_days": DATE_WINDOW_DAYS,
               "source_xlsx_sha256": hashlib.sha256(args.xlsx.read_bytes()).hexdigest(), "web_input_sha256": hashes}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_html(out / "price_match_report.html", results, counts)
    print(json.dumps({"ok": True, "rows": len(results), "counts": summary["counts"], "match_basis": dict(basis)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
