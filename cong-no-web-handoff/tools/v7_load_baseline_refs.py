#!/usr/bin/env python3
"""Part B: manifest-bound baseline references. PLAN never connects to DB."""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

from test_pg_v7_backend import lit
from v7_load_real_copy import LoadError, clean_data


def normalize(value):
    return re.sub(r"[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]", "", value or "").upper()


def split_trips(books):
    """Return (refs, skipped). A trip without a container cannot be matched by container,
    so it is counted and reported, never silently dropped and never given a reference."""
    result = []
    skipped = 0
    for book in books:
        for row in book["legacy"]:
            if row["kind"] != "trip":
                continue
            display = row["display"]
            container = normalize(display["container"])
            if not container:
                skipped += 1
                continue
            day = date.fromisoformat(display["date"]) if display["date"] else None
            booking = f"ALT:{container}:{day.strftime('%Y%m%d') if day else 'UNKNOWN'}"
            result.append((booking, container, day.isoformat() if day else None))
    return result, skipped


def references(books):
    return split_trips(books)[0]


def apply(pg, refs, digest, cutover, skipped=0):
    """Caller owns transaction. Serialize against application customer locks and other loaders."""
    pg.sql("SET LOCAL ROLE sokhach_owner; SET LOCAL statement_timeout='120s'; "
           "LOCK TABLE sokhach.customer IN ACCESS EXCLUSIVE MODE; "
           "LOCK TABLE sokhach.baseline_trip_ref IN ACCESS EXCLUSIVE MODE")
    pg.true(f"EXISTS (SELECT FROM sokhach.cutover WHERE id={cutover} AND status='active' "
            f"AND source_sha256={lit(digest)})", "BASELINE_MANIFEST_MISMATCH")
    pg.sql("CREATE TEMP TABLE incoming_refs(booking_norm text,container_norm text,event_date date) ON COMMIT DROP")
    for start in range(0, len(refs), 500):
        values = ["(" + ",".join("NULL" if x is None else lit(x) for x in r) + ")"
                  for r in refs[start:start + 500]]
        pg.sql("INSERT INTO incoming_refs VALUES " + ",".join(values))
    # Verify multiset against immutable legacy already imported; wrong bundle cannot populate references.
    pg.true(f"(SELECT count(*) FROM sokhach.legacy_row WHERE cutover_id={cutover} AND kind='trip')={len(refs) + skipped}",
            "BASELINE_LEGACY_COUNT_MISMATCH")
    legacy = ("SELECT sokhach._booking_key(NULL,display->>'container',nullif(display->>'date','')::date),"
              "sokhach._normalize_key(display->>'container'),nullif(display->>'date','')::date "
              f"FROM sokhach.legacy_row WHERE cutover_id={cutover} AND kind='trip' "
              "AND sokhach._normalize_key(display->>'container')<>''")
    pg.true("NOT EXISTS ((SELECT * FROM incoming_refs EXCEPT ALL " + legacy + ") UNION ALL (" +
            legacy + " EXCEPT ALL SELECT * FROM incoming_refs))", "BASELINE_LEGACY_MISMATCH")
    count = int(pg.value(f"SELECT count(*) FROM sokhach.baseline_trip_ref WHERE cutover_id={cutover}"))
    if count:
        pg.true(f"NOT EXISTS ((SELECT * FROM incoming_refs EXCEPT ALL "
                f"SELECT booking_norm,container_norm,event_date FROM sokhach.baseline_trip_ref WHERE cutover_id={cutover}) "
                f"UNION ALL (SELECT booking_norm,container_norm,event_date FROM sokhach.baseline_trip_ref WHERE cutover_id={cutover} "
                "EXCEPT ALL SELECT * FROM incoming_refs))", "BASELINE_REF_CONFLICT")
        return "UNCHANGED"
    before = pg.value("SELECT coalesce(jsonb_object_agg(customer_id,total),'{}') FROM "
                      "(SELECT customer_id,sum(outstanding_vnd)::text total FROM sokhach.v_outstanding_month GROUP BY customer_id) s")
    pg.sql(f"INSERT INTO sokhach.baseline_trip_ref SELECT {cutover},* FROM incoming_refs")
    after = pg.value("SELECT coalesce(jsonb_object_agg(customer_id,total),'{}') FROM "
                     "(SELECT customer_id,sum(outstanding_vnd)::text total FROM sokhach.v_outstanding_month GROUP BY customer_id) s")
    if json.loads(before) != json.loads(after):
        raise LoadError("BASELINE_BALANCE_CHANGED")
    return "LOADED"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clean_dir", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--database", default="webdebit_v7")
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--cutover-id", type=int, required=True)
    args = parser.parse_args()
    try:
        if args.cutover_id <= 0:
            raise LoadError("INVALID_CUTOVER")
        books, digests, manifest = clean_data(args.clean_dir)
        refs, skipped = split_trips(books)
        if not refs or len(refs) + skipped != manifest["counts"]["trips"]:
            raise LoadError("BASELINE_TRIP_COUNT_MISMATCH")
        result = {"mode": "APPLY" if args.apply else "PLAN", "trips": len(refs),
                  "skipped_no_container": skipped,
                  "manifest_sha256": digests["manifest.json"]}
        if args.apply:
            from v7_load_direct import DirectPg
            pg = DirectPg(args.socket_dir, args.database, "v7_loader")
            try:
                result["result"] = apply(pg, refs, digests["manifest.json"], args.cutover_id, skipped)
                pg.close(commit=True)
            except Exception:
                pg.close()
                raise
        print(json.dumps(result))
        return 0
    except (LoadError, OSError, ValueError, KeyError):
        # No source strings, customer names or connection details in operator output.
        print("BASELINE_LOAD_FAILED", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
