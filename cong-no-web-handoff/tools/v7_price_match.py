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
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import v7_load_real_copy as loader
import v7_reconcile_sheet as rec

DATE_WINDOW_DAYS = 3
STATUSES = ("READY", "PRICE_UNCHANGED", "CONFLICT", "MONTH_LOCKED", "PENDING_REVIEW",
            "AMBIGUOUS", "NOT_FOUND", "NO_CUSTOMER", "SHEET_NO_PRICE", "NO_CONTAINER")
LABELS = {"READY": "Ghi được (web chưa có giá)", "PRICE_UNCHANGED": "Giá đã giống",
          "CONFLICT": "Web có giá khác Sheet", "MONTH_LOCKED": "Ghi được nhưng tháng khóa",
          "PENDING_REVIEW": "Chuyến đang CHỜ KIỂM", "AMBIGUOUS": "Khớp nhiều dòng",
          "NOT_FOUND": "Không tìm thấy trên web", "NO_CUSTOMER": "Không có khách trên web",
          "SHEET_NO_PRICE": "Sheet chưa có giá", "NO_CONTAINER": "Dòng không container"}
FIELDS = ["customer_tab", "source_row", "debt_month", "container", "date", "sheet_unit_price_vnd",
          "sheet_other_fee_vnd", "sheet_total_vnd", "customer_basis", "status", "match_basis", "target_kind",
          "target_id", "web_unit_price_vnd", "web_other_fee_vnd", "web_total_vnd"]


def container_key(value) -> str:
    return "".join(str(value or "").upper().split())


def iso(value) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def money(value) -> int | None:
    try:
        return rec.vnd(value)
    except (rec.InputError, ValueError):
        return None


def sheet_rows(xlsx: Path) -> list[dict]:
    rows = []
    for tab, data in loader.scan_workbook(xlsx).items():
        for record in data.get("records", []):
            if record["kind"] != "trip":
                continue
            details = record.get("details", {})
            rows.append({"customer_tab": tab, "source_row": record["row"], "debt_month": record["month"],
                         "container": container_key(record.get("container")), "date": record.get("date"),
                         "sheet_unit_price_vnd": details.get("unit_price"),
                         "sheet_other_fee_vnd": details.get("fee"), "sheet_total_vnd": record.get("amount")})
    return rows


def targets(ledger: dict) -> list[dict]:
    locks = {str(row.get("month"))[:7]: row.get("locked") for row in ledger.get("month_locks", [])}
    today = str(ledger.get("today_month") or "")[:7]

    def locked(month):
        key = str(month or "")[:7]
        return locks.get(key, key != today)

    out = []
    for trip in ledger.get("trips", []):
        if trip.get("deleted") or trip.get("status") == "rejected":
            continue
        out.append({"kind": "trip", "id": trip.get("id"), "container": container_key(trip.get("container")),
                    "date": iso(trip.get("event_date")), "price": money(trip.get("unit_price_vnd")),
                    "fee": money(trip.get("other_fee_vnd")), "locked": locked(trip.get("month")),
                    "total": None, "pending": trip.get("status") == "pending_review"})
    for row in ledger.get("legacy_rows", []):
        current = row.get("current") or {}
        if row.get("kind") != "trip" or current.get("deleted"):
            continue
        out.append({"kind": "legacy", "id": row.get("id"), "container": container_key(current.get("container")),
                    "date": iso(current.get("event_date")), "price": money(current.get("unit_price_vnd")),
                    "fee": money(current.get("other_fee_vnd")), "locked": locked(current.get("month") or row.get("month")),
                    "total": money(current.get("counted_vnd")), "pending": False})
    return [target for target in out if target["container"]]


def unchanged(row: dict, target: dict) -> bool:
    if target["price"] != row["sheet_unit_price_vnd"]:
        return False
    if target["kind"] == "legacy":
        # Original-book rows keep the Sheet TOTAL (counted_vnd); fee columns such as negative
        # discounts are not stored separately, so the charged total is what must agree.
        return target["total"] is not None and target["total"] == row["sheet_total_vnd"]
    # V7-BE: with a known price a blank fee counts as 0, so blank and 0 are the same charge.
    return (row["sheet_other_fee_vnd"] or 0) == (target["fee"] or 0)


def customer_pools(ledgers: dict[str, dict]) -> tuple[dict, dict]:
    """Ledger name first, then Sheet display name and aliases; a name shared by two books is dropped."""
    primary = {rec.name(key): key for key in ledgers}
    extra: dict[str, set] = {}
    for key, ledger in ledgers.items():
        for alias in [ledger.get("_display_name"), *(ledger.get("_aliases") or [])]:
            if isinstance(alias, str) and alias.strip() and rec.name(alias) not in primary:
                extra.setdefault(rec.name(alias), set()).add(key)
    by_alias = {alias: next(iter(keys)) for alias, keys in extra.items() if len(keys) == 1}
    return primary, by_alias


def match(rows: list[dict], ledgers: dict[str, dict]) -> list[dict]:
    pools = {key: targets(ledger) for key, ledger in ledgers.items()}
    primary, by_alias = customer_pools(ledgers)
    out = []
    for row in rows:
        result = {**row, "status": None, "customer_basis": "", "match_basis": "", "target_kind": "",
                  "target_id": "", "web_unit_price_vnd": None, "web_other_fee_vnd": None, "web_total_vnd": None}
        out.append(result)
        tab = rec.name(row["customer_tab"]) if str(row["customer_tab"]).strip() else ""
        key = primary.get(tab) or by_alias.get(tab)
        result["customer_basis"] = "" if key is None else "name" if tab in primary else "alias"
        pool = pools.get(key)
        sheet_date = iso(row["date"])
        if not row["container"]:
            result["status"] = "NO_CONTAINER"
            continue
        if pool is None:
            result["status"] = "NO_CUSTOMER"
            continue
        same = [t for t in pool if t["container"] == row["container"]]
        found = [t for t in same if sheet_date and t["date"] == sheet_date]
        result["match_basis"] = "exact_date" if found else ""
        if not found and sheet_date:
            found = [t for t in same if t["date"] and abs((t["date"] - sheet_date).days) <= DATE_WINDOW_DAYS]
            result["match_basis"] = "near_date" if found else ""
        if not found and not sheet_date:
            # Undated Sheet rows (mostly old history): container alone, only within this customer;
            # several rows with that container stay AMBIGUOUS below.
            found = same
            result["match_basis"] = "container_only" if found else ""
        if not found:
            result["status"] = "NOT_FOUND"
            continue
        if len(found) > 1:
            result["status"] = "AMBIGUOUS"
            continue
        target = found[0]
        result.update(target_kind=target["kind"], target_id=target["id"],
                      web_unit_price_vnd=target["price"], web_other_fee_vnd=target["fee"], web_total_vnd=target["total"])
        if row["sheet_unit_price_vnd"] is None:
            result["status"] = "SHEET_NO_PRICE"   # blank stays NULL; nothing to write
        elif unchanged(row, target):
            result["status"] = "PRICE_UNCHANGED"
        elif target["pending"]:
            result["status"] = "PENDING_REVIEW"
        elif target["price"] is not None:
            result["status"] = "CONFLICT"
        else:
            result["status"] = "MONTH_LOCKED" if target["locked"] else "READY"
    # Two Sheet rows pointing at one web row cannot both be written.
    used = Counter((r["target_kind"], r["target_id"]) for r in out if r["target_id"] != "")
    for result in out:
        if result["target_id"] != "" and used[(result["target_kind"], result["target_id"])] > 1:
            result["status"] = "AMBIGUOUS"
    return out


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
    shown = [r for r in results if r["status"] not in ("PRICE_UNCHANGED", "NO_CONTAINER")]
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
