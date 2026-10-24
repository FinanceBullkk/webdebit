"""Read-only adapter for the WEBDEBIT_EXPORT Google Sheet tab."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

EXPORT_RANGE = "WEBDEBIT_EXPORT!A1:E20000"
BOOKING_RANGE = "BOOKING_DATA!A1:K20000"
MAPPING_RANGE = "REVIEW_KHACH_2026-10-24!A1:F1000"
HEADERS = ("Số container", "Hãng tàu", "Ngày chuyến", "Nơi đi", "Nơi đến")
BOOKING_HEADERS = ("Số cont", "Chủ hàng (chuẩn)", "Ngày đóng", "Booking", "Tab nguồn", "Dòng nguồn", "Chủ hàng (gốc)", "Shipper", "Hãng tàu", "Kho", "Cảng đến")
_SPACE_RE = re.compile(r"\s+")


def normalize_customer_name(value: Any) -> str:
    return _SPACE_RE.sub(" ", unicodedata.normalize("NFC", str(value or "").strip().upper()))


def normalize_container(value: Any) -> str:
    return _SPACE_RE.sub("", str(value or "").strip().upper())


def parse_date(value: Any) -> str | None:
    text = str(value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _row_status(row: dict[str, Any]) -> str:
    if not row["container"] or not row["event_date"]:
        return "INVALID"
    if any(not row[field] for field in ("carrier", "origin", "destination")):
        return "INVALID"
    return "READY"


def parse_values(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values or tuple(values[0][:5]) != HEADERS:
        raise ValueError("WEBDEBIT_EXPORT header mismatch")
    rows: list[dict[str, Any]] = []
    for row_number, raw in enumerate(values[1:], start=2):
        cells = list(raw[:5]) + [""] * max(0, 5 - len(raw))
        if not any(str(cell or "").strip() for cell in cells):
            continue
        item = {
            "source_row": row_number,
            "container": normalize_container(cells[0]),
            "carrier": str(cells[1] or "").strip(),
            "source_date": str(cells[2] or "").strip(),
            "event_date": parse_date(cells[2]),
            "origin": str(cells[3] or "").strip(),
            "destination": str(cells[4] or "").strip(),
        }
        item["status"] = _row_status(item)
        rows.append(item)
    by_key: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for item in rows:
        key = (item["container"], item["event_date"])
        if item["status"] == "READY":
            by_key.setdefault(key, []).append(item)
    for matches in by_key.values():
        if len(matches) > 1:
            for item in matches:
                item["status"] = "DUPLICATE"
    return rows


def parse_booking_values(values: list[list[Any]]) -> list[dict[str, Any]]:
    if not values or tuple(values[0][:len(BOOKING_HEADERS)]) != BOOKING_HEADERS:
        raise ValueError("BOOKING_DATA header mismatch")
    rows = []
    for source_row, raw in enumerate(values[1:], start=2):
        cells = list(raw[:len(BOOKING_HEADERS)]) + [""] * max(0, len(BOOKING_HEADERS) - len(raw))
        if not any(str(cell or "").strip() for cell in cells):
            continue
        rows.append({
            "source_row": source_row,
            "container": normalize_container(cells[0]),
            "customer_name": str(cells[1] or "").strip(),
            "booking_date": parse_date(cells[2]),
            "booking": _SPACE_RE.sub("", str(cells[3] or "").strip().upper()),
            "carrier": str(cells[8] or "").strip(),
            "origin": str(cells[9] or "").strip(),
            "destination": str(cells[10] or "").strip(),
        })
    return rows


def merge_booking_rows(export_rows: list[dict[str, Any]], booking_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index: dict[tuple[str, str | None, str, str, str], list[dict[str, Any]]] = {}
    for booking in booking_rows:
        key = (booking["container"], booking["booking_date"], booking["carrier"], booking["origin"], booking["destination"])
        index.setdefault(key, []).append(booking)
    merged = []
    for row in export_rows:
        key = (row["container"], row["event_date"], row["carrier"], row["origin"], row["destination"])
        matches = index.get(key, []) if row["status"] == "READY" else []
        item = dict(row)
        if len(matches) == 1:
            item.update({"booking": matches[0]["booking"], "customer_name": matches[0]["customer_name"], "booking_source_row": matches[0]["source_row"]})
            if not matches[0]["customer_name"]:
                item["status"] = "NO_CUSTOMER"
        elif len(matches) > 1:
            item["status"] = "AMBIGUOUS_BOOKING"
        elif row["status"] == "READY":
            item["status"] = "NO_BOOKING_MATCH"
        merged.append(item)
    return merged


def parse_review_mapping(values: list[list[Any]]) -> dict[str, str]:
    if not values or values[0][0] != "Chủ hàng từ BOOKING_DATA" or len(values[0]) < 6 or values[0][5] != "Khách chuẩn trên hao (bạn điền)":
        raise ValueError("customer review header mismatch")
    aliases = {}
    for cells in values[1:]:
        source = normalize_customer_name(cells[0] if cells else "")
        target = str(cells[5] if len(cells) > 5 else "").strip()
        if source and target:
            if source in aliases and aliases[source] != target:
                raise ValueError("conflicting customer review mapping")
            aliases[source] = target
    return aliases


def merge_customers(rows: list[dict[str, Any]], response: dict[str, Any],
                    aliases: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Match BOOKING_DATA's standard customer name to a unique active V7 customer."""
    customers = response.get("customers")
    if not isinstance(customers, list):
        raise ValueError("V7 customer list missing")
    by_name: dict[str, list[dict[str, Any]]] = {}
    for customer in customers:
        if not isinstance(customer, dict) or type(customer.get("id")) is not int or customer["id"] <= 0 or not isinstance(customer.get("name"), str):
            raise ValueError("invalid V7 customer")
        by_name.setdefault(normalize_customer_name(customer["name"]), []).append(customer)
    merged = []
    for row in rows:
        item = dict(row)
        if item["status"] == "READY":
            source_name = normalize_customer_name(item.get("customer_name", ""))
            matches = by_name.get(normalize_customer_name((aliases or {}).get(source_name, source_name)), [])
            if len(matches) > 1:
                item["status"] = "AMBIGUOUS_CUSTOMER"
            elif not matches:
                item["status"] = "NO_CUSTOMER_MATCH"
            elif matches[0].get("status") != "active":
                item["status"] = "NO_BASELINE_CUSTOMER"
            else:
                item["customer_id"] = matches[0]["id"]
        merged.append(item)
    return merged


def to_paste_trip(row: dict[str, Any]) -> dict[str, Any]:
    """Map one READY export row to the V7 paste payload shape.

    Caller must review status, customer, period, and pricing before posting.
    """
    if row.get("status") != "READY" or row.get("review_status", "READY_TO_PREVIEW") != "READY_TO_PREVIEW":
        raise ValueError("only READY rows can become paste trips")
    return {
        "container": row["container"],
        "carrier": row["carrier"],
        "from": row["origin"],
        "to": row["destination"],
        "date": dt.date.fromisoformat(row["event_date"]).strftime("%d/%m/%Y"),
        **({"booking": row["booking"]} if row.get("booking") else {}),
        "src": "WEBDEBIT_EXPORT",
        "note": f"WEBDEBIT_EXPORT row {row['source_row']}",
    }


def _fetch_values(spreadsheet_id: str, access_token: str, opener: Callable[..., Any], range_a1: str = EXPORT_RANGE) -> list[list[Any]]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", spreadsheet_id):
        raise ValueError("invalid spreadsheet ID")
    encoded_range = urllib.parse.quote(range_a1, safe="!:$")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with opener(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    values = payload.get("values")
    if not isinstance(values, list):
        raise ValueError("Google Sheets response missing values")
    return values


def read_export(spreadsheet_id: str, access_token: str, opener: Callable[..., Any] = urllib.request.urlopen,
                *, include_booking: bool = False, include_mapping: bool = False) -> dict[str, Any]:
    if include_mapping and not include_booking:
        raise ValueError("customer mapping requires booking")
    values = _fetch_values(spreadsheet_id, access_token, opener)
    rows = parse_values(values)
    sources = {"export": values}
    if include_booking:
        # ponytail: two Sheets reads are not atomic; re-read both before any approved posting flow.
        booking_values = _fetch_values(spreadsheet_id, access_token, opener, BOOKING_RANGE)
        rows = merge_booking_rows(rows, parse_booking_values(booking_values))
        sources["booking"] = booking_values
    aliases = None
    if include_mapping:
        mapping_values = _fetch_values(spreadsheet_id, access_token, opener, MAPPING_RANGE)
        aliases = parse_review_mapping(mapping_values)
        sources["customer_mapping"] = mapping_values
    canonical = json.dumps(sources, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {
        "source": {"spreadsheet_id": spreadsheet_id, "range": EXPORT_RANGE,
                   **({"booking_range": BOOKING_RANGE} if include_booking else {})},
        "rows": rows,
        "row_count": len(rows),
        "sha256": hashlib.sha256(canonical).hexdigest(),
        **({"customer_aliases": aliases} if include_mapping else {}),
    }


def paste_preview(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Show candidate trip fields without creating a financial-write request."""
    return {
        **snapshot,
        "rows": [
            {**row, "candidate": to_paste_trip(row) if row["status"] == "READY" and
             row.get("review_status", "READY_TO_PREVIEW") == "READY_TO_PREVIEW" else None}
            for row in snapshot["rows"]
        ],
    }


def build_review_queue(rows: list[dict[str, Any]], baseline_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify rows for human review without creating a write request."""
    if not baseline_refs:
        raise ValueError("baseline references required")
    by_code = {(normalize_container(ref.get("container_norm")), str(ref.get("booking_norm") or "").upper())
               for ref in baseline_refs}
    by_container: dict[str, list[dt.date]] = {}
    for ref in baseline_refs:
        if ref.get("event_date"):
            by_container.setdefault(normalize_container(ref.get("container_norm")), []).append(
                dt.date.fromisoformat(ref["event_date"]))
    queue = []
    for row in rows:
        item = dict(row)
        container = normalize_container(row.get("container"))
        booking = str(row.get("booking") or "").upper()
        date = dt.date.fromisoformat(row["event_date"]) if row.get("event_date") else None
        if row.get("status") != "READY":
            item.update({"review_status": row.get("status", "INVALID"), "review_reasons": [row.get("status", "INVALID")]})
        elif ((booking and (container, booking) in by_code) or
              (date and any(abs((date - old).days) <= 3 for old in by_container.get(container, ())))):
            item.update({"review_status": "BASELINE_REVIEW", "review_reasons": ["BASELINE_MATCH"]})
        elif not row.get("customer_id"):
            item.update({"review_status": "NEEDS_CUSTOMER", "review_reasons": ["CUSTOMER_MAPPING"]})
        elif not row.get("reviewed_new_trip"):
            item.update({"review_status": "NEW_TRIP_REVIEW", "review_reasons": ["NOT_IN_BASELINE"]})
        elif row.get("unit_price_vnd") in (None, ""):
            item.update({"review_status": "NEEDS_PRICE", "review_reasons": ["PRICE_REQUIRED"]})
        else:
            item.update({"review_status": "READY_TO_PREVIEW", "review_reasons": []})
        queue.append(item)
    return queue


def main() -> int:
    parser = argparse.ArgumentParser(description="Read WEBDEBIT_EXPORT as JSON")
    parser.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--preview-paste", action="store_true", help="include review-only paste candidates")
    parser.add_argument("--with-booking", action="store_true", help="join BOOKING_DATA without writing")
    parser.add_argument("--customers-json", help="read-only /api/v7/customers response saved as JSON")
    parser.add_argument("--review-queue", action="store_true", help="classify rows for review without posting")
    parser.add_argument("--baseline-refs-json", help="read-only baseline reference rows saved as JSON")
    args = parser.parse_args()
    if args.customers_json and not args.with_booking:
        parser.error("--customers-json requires --with-booking")
    if args.review_queue and (not args.with_booking or not args.customers_json or not args.baseline_refs_json):
        parser.error("--review-queue requires --with-booking, --customers-json and --baseline-refs-json")
    access_token = os.getenv("WEBDEBIT_GOOGLE_ACCESS_TOKEN")
    if not args.spreadsheet_id or not access_token:
        parser.error("set WEBDEBIT_SHEET_ID and WEBDEBIT_GOOGLE_ACCESS_TOKEN")
    snapshot = read_export(args.spreadsheet_id, access_token, include_booking=args.with_booking,
                           include_mapping=args.review_queue)
    if args.customers_json:
        with open(args.customers_json, encoding="utf-8") as stream:
            snapshot["rows"] = merge_customers(snapshot["rows"], json.load(stream), snapshot.get("customer_aliases"))
    if args.review_queue:
        with open(args.baseline_refs_json, encoding="utf-8") as stream:
            snapshot["rows"] = build_review_queue(snapshot["rows"], json.load(stream))
    print(json.dumps(paste_preview(snapshot) if args.preview_paste else snapshot, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
