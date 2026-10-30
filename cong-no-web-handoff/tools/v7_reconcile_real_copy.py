#!/usr/bin/env python3
"""Recheck isolated V7 copy using the same independent XLSX source gates."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import v7_load_real_copy as loader
from test_pg_v7_backend import Pg, inspect_owned
from v7_load_real_copy import (
    SOURCE,
    LoadError,
    integer,
    reason,
    report,
    source_data,
    write_report,
)


def reconcile(pg: Pg, source: Path) -> dict:
    books, digests, _ = source_data(source)
    # Never log these rows: customer identity and amounts stay in memory only.
    # Raw buckets (CAN-DU-01): compare each opening bucket as loaded, before credit is applied to older debt.
    found = json.loads(pg.value("""SELECT coalesce(jsonb_agg(jsonb_build_object(
        'name',c.name,'active',cc.status='active' AND co.status='active',
        'months',(SELECT coalesce(jsonb_object_agg(v.debt_month::text,
             v.outstanding_vnd::text),'{}'::jsonb) FROM sokhach.v_outstanding_month_raw v
             WHERE v.customer_id=c.id))),'[]'::jsonb)
        FROM sokhach.customer c
        LEFT JOIN sokhach.cutover_customer cc ON cc.customer_id=c.id
        LEFT JOIN sokhach.cutover co ON co.id=cc.cutover_id"""))
    by_name = {row["name"].strip(): row for row in found}
    if len(by_name) != len(found):
        raise LoadError("DUPLICATE_CUSTOMER")
    for item in books:
        live = by_name.get(item["name"])
        if item["reasons"]:
            if live and live["active"]:
                item["reasons"]["QUARANTINED_CUSTOMER_ACTIVE"] += 1
            continue
        if live is None:
            item["reasons"]["MISSING_CUSTOMER"] += 1
        elif not live["active"]:
            item["reasons"]["INACTIVE_CUSTOMER"] += 1
        else:
            actual = {month: integer(amount) for month, amount in live["months"].items()}
            expected = {row["debt_month"]: row["amount_vnd"] for row in item["openings"]}
            if actual != expected:
                item["reasons"]["PERIOD_MISMATCH"] += 1
            if any(value is None for value in actual.values()) or sum(
                    value for value in actual.values() if value is not None) != item["anchor"]:
                item["reasons"]["CUSTOMER_MISMATCH"] += 1
            if not item["reasons"]:
                item["status"] = "active"
    result = report(books, digests, pg.run_id, loaded=True)
    extras = len(set(by_name) - {item["name"] for item in books})
    if extras:
        result["reason_counts"]["EXTRA_CUSTOMER"] = extras
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", required=True)
    parser.add_argument("--source-dir", type=Path, default=SOURCE)
    parser.add_argument("--raw-tab", action="append", default=[], metavar="EXACT_NAME",
                        help="same choice as the loader, so both read the same tabs")
    parser.add_argument("--sheet-is-truth", action="store_true", help="same as the loader")
    args = parser.parse_args()
    loader.PREFERRED_RAW_TABS = tuple(args.raw_tab)
    loader.SHEET_IS_TRUTH = args.sheet_is_truth
    match = re.fullmatch(r"webdebit-v7-real-([0-9a-f]{32})", args.container)
    if not match:
        parser.error("container must be this loader's real-copy name")
    run_id = match[1]
    try:
        if inspect_owned(args.container, args.container, run_id) is None:
            raise LoadError("CONTAINER_MISSING")
        result = reconcile(Pg(args.container, run_id), args.source_dir)
    except Exception as exc:  # noqa: BLE001  (any failure becomes a coded reason in the report)
        result = report([], {}, run_id)
        result["reason_counts"][reason(exc)] = 1
        write_report(result, f"real-reconcile-{run_id}.json")
        return 1
    write_report(result, f"real-reconcile-{run_id}.json")
    return 2 if result["reason_counts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
