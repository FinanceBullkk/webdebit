#!/usr/bin/env python3
"""Write SQL that sets commodity/transport mode on books already loaded into V7 (MH-01).

Book names come from the clean bundle that was loaded (hash-checked); labels from the LOAI HANG
column of the TONG tab, matched exactly as the loader does. Never connects to a database: the
operator runs the file with psql after a backup. Customer names go into the file (hex-encoded) and
never to stdout, so the file must be outside the repository like captures/.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import v7_load_real_copy as loader
from v7_export_clean import outside_repo


def statements(names: list[str], labels: dict[str, str | None]) -> tuple[str, Counter]:
    """Exact book names; fills only books with neither commodity nor mode, so reruns are harmless."""
    counts = Counter()
    lines = ["-- MH-01: gán mặt hàng từ cột LOAI HANG của TONG. Sinh bởi tools/v7_commodity_sql.py.",
             "-- Chứa tên khách (mã hex): giữ ngoài Git. Chạy bằng psql -X -v ON_ERROR_STOP=1 sau backup.",
             "BEGIN;", "SET LOCAL ROLE sokhach_owner;"]
    for name in sorted(names):
        label = labels.get(loader.normalized(name))
        commodity = loader.commodity_of(label)
        if commodity is None:
            counts["NHAN_LA" if label else "CHUA_PHAN_LOAI"] += 1
            continue
        counts[commodity[0] + (f" {commodity[1]}" if commodity[1] else "")] += 1
        value = loader.text_sql(commodity[0])
        mode = f"'{commodity[1]}'" if commodity[1] else "NULL"
        lines += [f"INSERT INTO sokhach.commodity(name) VALUES ({value}) ON CONFLICT (name) DO NOTHING;",
                  f"UPDATE sokhach.customer SET commodity_id=(SELECT id FROM sokhach.commodity WHERE name={value}),"
                  f" transport_mode={mode} WHERE name={loader.text_sql(name)}"
                  " AND commodity_id IS NULL AND transport_mode IS NULL;"]
    lines += ["COMMIT;", ""]
    return "\n".join(lines), counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True, help="bản xuất Sheet có tab TONG")
    parser.add_argument("--clean", type=Path, required=True, help="thư mục bản sạch đã nạp vào DB")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        out = outside_repo(args.out)
        if out.exists():
            raise loader.LoadError("output file exists; nothing is overwritten")
        books = loader.clean_data(args.clean)[0]
        sql, counts = statements([b["name"] for b in books], loader.tong_commodities(args.xlsx))
        out.write_text(sql, encoding="utf-8")
    except (loader.LoadError, OSError) as exc:
        print(json.dumps({"ok": False, "reason": loader.reason(exc)}))
        return 1
    print(json.dumps({"ok": True, "commodity_counts": dict(sorted(counts.items()))}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
