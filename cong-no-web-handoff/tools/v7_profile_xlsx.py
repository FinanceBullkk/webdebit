#!/usr/bin/env python3
"""Structure-only profile of the Sheet export for fixing the V7 xlsx reader.

Prints layout patterns only: no tab names, no amounts, no text that appears in
fewer than MIN_TABS tabs (customer-specific text never repeats that widely).
Digits inside text become 9; numeric cells become N.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from v7_load_real_copy import LOG_DIR, SOURCE, normalized, workbook_rows

MIN_TABS = 5
KEYWORDS = ("THANG", "CONTAINER", "TOTAL", "NGAY", "DON GIA", "UNIT", "PRICE", "PHAI THU",
            "CON NO", "NO TRUOC", "CHUYEN SANG", "SO DU", "DA THU", "UNG TRUOC", "TONG", "PHI", "FEE")


def mask(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", text):
        return "N"
    return re.sub(r"[0-9]", "9", text)[:60]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=SOURCE)
    args = parser.parse_args()
    texts = defaultdict(set)          # masked text -> tab ids
    signatures = defaultdict(set)     # masked keyword-row signature -> tab ids
    titles = defaultdict(set)         # masked month-title text -> tab ids
    title_columns = Counter()
    first_title_row = Counter()
    tabs = 0
    for index, (tab, data) in enumerate(workbook_rows(args.source_dir / "source-google-export.xlsx")):
        if normalized(tab) == "TONG":
            continue
        tabs += 1
        seen_title = False
        for row_no, cells in data:
            masked = {col: mask(v) for col, v in cells.items() if v}
            for col, value in masked.items():
                if value != "N":
                    texts[value].add(index)
                if "THANG" in normalized(cells[col]) and re.search(r"[0-9]", cells[col]):
                    titles[value].add(index)
                    title_columns[col] += 1
                    if not seen_title:
                        first_title_row[min(row_no, 20)] += 1
                        seen_title = True
            if any(key in normalized(v) for v in cells.values() if v for key in KEYWORDS):
                signature = " | ".join(f"{col}:{value}" for col, value in sorted(
                    masked.items(), key=lambda item: (len(item[0]), item[0])))
                signatures[signature].add(index)
    def common(table):
        return sorted(((k, len(v)) for k, v in table.items() if len(v) >= MIN_TABS),
                      key=lambda item: -item[1])

    result = {
        "tabs_profiled": tabs, "min_tabs_for_text": MIN_TABS,
        "month_title_forms": common(titles)[:40],
        "month_title_columns": title_columns.most_common(10),
        "first_month_title_row_hist": sorted(first_title_row.items()),
        "keyword_row_signatures": common(signatures)[:80],
        "common_texts": common(texts)[:150],
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / "xlsx-profile.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"tabs={tabs} titles={len(result['month_title_forms'])} "
          f"signatures={len(result['keyword_row_signatures'])} -> {LOG_DIR / 'xlsx-profile.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
