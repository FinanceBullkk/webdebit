#!/usr/bin/env python3
"""Match the Sheet ledger's trips with the booking sources (NGUON-CHUYEN-01, specs/v7-chuyen-theo-nguon.md GĐ1).

Usage: v7_trip_source_match.py --xlsx SO_GOC.xlsx --source NEWEST.json [--source OLDER.json ...] --out DIR
                               [--end-month YYYY-MM]

Read-only. A source file holds Sheets API values per tab: {"tabs": {title: [[header...], [cells...]]}, "year": 2025}
("year" only fills "dd/mm" cells). The tab title picks the layout: CONT_NGUON (sea or road by its "Loại"),
CONT_BO / "CONT BỘ" (road), "THÁNG m/yyyy" (sea, booking file), "ĐƯỜNG SẮT" (counted with sea), "SẦU … ĐƯỜNG BỘ"
(road). Give the sources newest first: a row repeating a trip kept from an earlier tab (same container, at most
3 days apart) is dropped; rows of one tab never drop each other.

Rule (1): a Sheet trip and a source trip pair when the container matches and the dates are at most 3 days apart; a
Sheet row without a date pairs within its debt month. Each source trip pairs once, smallest gap first. Prints counts
only (no names, no money), so the output may go into a deploy log or a spec. DIR must be outside the repository: it
gets sheet_rows.csv, source_rows.csv and can_xem.csv, which carry customer names. Exit 0 on success, 2 on bad input.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

import v7_load_real_copy as loader

REPO = pathlib.Path(__file__).resolve().parents[2]
ISO = re.compile(r"[A-Z]{4}\d{7}")
PAIR_DAYS = 3   # rule (1), same window as BASELINE_DATE_WINDOW
NEAR_DAYS = 31  # unpaired, same container, 4-31 days apart: maybe a mistyped date, a person decides
# First month each family has sources, measured 3/11/2026 (booking 2025 + CONT_NGUON + CONT_BO).
START = {"BIEN": "2025-01", "BO": "2025-03"}
LAYOUTS = {  # field -> headers after loader.normalized, first one found wins; date2 is the per-row fallback
    "NGUON": {"cont": ["SO CONT"], "date": ["NGAY DONG"], "owner": ["CHU HANG CHUAN"], "ref": ["BOOKING"],
              "price": ["GIA PHI GOC"], "kind": ["LOAI"]},
    "BO": {"cont": ["SO CONT"], "date": ["NGAY DONG HANG"], "date2": ["NGAY KHOI HANH"], "owner": ["CHU HANG"],
           "ref": ["SO XE"], "price": ["GIA"]},
    "MONTH": {"cont": ["SO CONT"], "date": ["NGAY DONG HANG"], "owner": ["CHU HANG"], "ref": ["BOOKING"],
              "price": ["GIA NEO DIEN GHEP", "GIA"]},
    "RAIL": {"cont": ["SO CONT"], "date": ["NGAY DONG HANG"], "owner": ["CHU HANG"], "price": ["GIA"]},
    "DURIAN_ROAD": {"cont": ["SO CONT"], "date": ["NGAY LEN KHO"], "date2": ["NGAY XUAT PHAT"], "owner": ["KHACH"],
                    "ref": ["SO XE"], "price": ["THU KHACH"]},
}
FAMILY = {"BO": "BO", "MONTH": "BIEN", "RAIL": "BIEN", "DURIAN_ROAD": "BO"}  # NGUON: by its "Loại" column


def container_key(raw: Any) -> str:
    text = re.sub(r"[^A-Z0-9]", "", str(raw or "").upper())
    tokens = ISO.findall(text)
    return tokens[0] if len(tokens) == 1 else text


def day_first(text: Any, year: int | None = None) -> str | None:
    """d/m/yyyy (or d/m/yy) as the booking files write it; "dd/mm" only with `year`. Years before 2000 are junk."""
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2}|\d{4}))?", str(text or "").strip())
    if not m or (m.group(3) is None and year is None):
        return None
    y = int(m.group(3)) if m.group(3) else year
    try:
        found = date(y + 2000 if y < 100 else y, int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None
    return found.isoformat() if found.year >= 2000 else None


def owner_key(name: Any) -> str:
    """'NGUYỄN VĂN A 12', 'Nguyen Van A' and 'NGUYEN VAN A HTH12' compare equal: no marks, digits or HTH/TTH codes."""
    text = re.sub(r"\b(?:HTH|TTH)\s*\d+\b", " ", loader.normalized(str(name or "")))
    return re.sub(r"[^A-Z]", "", text)


def price_vnd(text: Any) -> int | None:
    """Booking price text '38TR+1' -> 39000000 (every part in millions); None when a part is not a number."""
    total = 0
    for part in str(text or "").upper().replace(" ", "").replace(",", ".").split("+"):
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(?:TR|TRIEU|M)?", part)
        if not m:
            return None
        try:
            total += int(Decimal(m.group(1)) * 1_000_000)
        except InvalidOperation:
            return None
    return total


def tab_kind(title: str) -> str | None:
    n = loader.normalized(title)
    if n in ("CONT NGUON", "CONT BO"):
        return "NGUON" if n == "CONT NGUON" else "BO"
    if re.fullmatch(r"THANG \d{1,2} \d{4}", n):
        return "MONTH"
    if n == "DUONG SAT":
        return "RAIL"
    return "DURIAN_ROAD" if n.startswith("SAU ") and n.endswith("DUONG BO") else None


def columns(header: list[Any], layout: dict[str, list[str]], title: str) -> dict[str, int]:
    names = [loader.normalized(str(h or "")) for h in header]
    found = {field: names.index(w) for field, wanted in layout.items() for w in reversed(wanted) if w in names}
    missing = {"cont", "date"} - found.keys()
    if missing:
        raise ValueError(f"{title}: thiếu cột {sorted(missing)}")
    return found


def load_sources(paths: list[pathlib.Path]) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    seen: dict[str, list[tuple[date, tuple[str, str]]]] = defaultdict(list)
    for path in paths:
        payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("tabs"), dict):
            raise ValueError(f"{pathlib.Path(path).name}: thiếu 'tabs'")
        for title, values in payload["tabs"].items():
            kind = tab_kind(title)
            if not kind or not values:
                stats["tab_bo_qua"] += 1
                continue
            col, tab_id = columns(values[0], LAYOUTS[kind], title), (str(path), title)
            for line, cells in enumerate(values[1:], start=2):
                got = {f: str(cells[i]).strip() if i < len(cells) else "" for f, i in col.items()}
                cont = container_key(got.get("cont"))
                day = day_first(got.get("date"), payload.get("year")) or day_first(got.get("date2"), payload.get("year"))
                if not cont or not day:
                    stats["dong_thieu_cont_hoac_ngay"] += 1
                    continue
                when = date.fromisoformat(day)
                if any(t != tab_id and abs((when - old).days) <= PAIR_DAYS for old, t in seen[cont]):
                    stats["dong_lap_tab_truoc"] += 1
                    continue
                seen[cont].append((when, tab_id))
                family = FAMILY.get(kind) or ("BO" if loader.normalized(got.get("kind", "")) == "BO" else "BIEN")
                rows.append({"family": family, "tab": title, "line": line, "cont": cont, "date": day,
                             "owner": got.get("owner", ""), "ref": got.get("ref", ""), "price": got.get("price", "")})
    return rows, stats


def mode_of(tab: str, tong: dict[str, str | None]) -> str:
    found = loader.commodity_of(tong.get(loader.normalized(tab)))
    if found and found[1]:
        return found[1]
    n = loader.normalized(tab)
    if "DUONG BO" in n or n.endswith(" BO"):
        return "BO"
    if n.startswith("BAN CUOC"):
        return "BAN_CUOC"
    return "NHAP" if n.startswith("HANG NHAP") or "NHAP TRA VE" in n else "CANG"


def load_sheet(xlsx: pathlib.Path) -> list[dict[str, Any]]:
    tong = loader.tong_commodities(xlsx)
    rows = []
    for tab, result in loader.scan_tabs(loader.workbook_rows(xlsx)).items():
        n = loader.normalized(tab)
        if re.fullmatch(r"SHEET\d+", n) or n.startswith("COPY ") or "AMBIGUOUS_SOURCE_TAB" in result.get("issues", {}):
            continue
        mode = mode_of(tab, tong)
        for r in result.get("records", []):
            if r["kind"] == "trip" and str(r["container"] or "").strip():
                rows.append({"tab": tab, "row": r["row"], "month": r["month"], "date": r["date"],
                             "raw_date": r["raw_date"], "cont": container_key(r["container"]), "mode": mode,
                             "amount": (r["amount"] or 0) + r.get("spread", 0)})
    return rows


def days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def pair(sheet: list[dict[str, Any]], source: list[dict[str, Any]]) -> tuple[dict[int, int], dict[int, int]]:
    """Rule (1), one-to-one, smallest gap first; dated pairs before undated (same debt month) ones."""
    by_cont = defaultdict(list)
    for j, b in enumerate(source):
        by_cont[b["cont"]].append(j)
    candidates = []
    for i, s in enumerate(sheet):
        for j in by_cont.get(s["cont"], ()):
            if s["date"] and days(s["date"], source[j]["date"]) <= PAIR_DAYS:
                candidates.append(((0, days(s["date"], source[j]["date"])), i, j))
            elif not s["date"] and source[j]["date"][:7] == s["month"]:
                candidates.append(((1, abs(int(source[j]["date"][8:]) - 15)), i, j))
    s_pair: dict[int, int] = {}
    b_pair: dict[int, int] = {}
    for _, i, j in sorted(candidates):
        if i not in s_pair and j not in b_pair:
            s_pair[i], b_pair[j] = j, i
    return s_pair, b_pair


def family_of(mode: str) -> str | None:
    return {"CANG": "BIEN", "BO": "BO"}.get(mode)


def in_window(family: str | None, month: str, end: str) -> bool:
    return family is not None and START[family] <= month <= end


def swapped(day: str) -> str | None:
    d = date.fromisoformat(day)
    try:
        other = date(d.year, d.day, d.month)
    except ValueError:
        return None
    return other.isoformat() if other != d else None


def review(sheet, source, s_pair, b_pair, end) -> tuple[list[tuple[str, dict | None, dict | None, str]], dict[str, int]]:
    """Rows of can_xem.csv as (group, sheet row, source row, note), plus duplicate-group counts."""
    out: list[tuple[str, dict | None, dict | None, str]] = []
    by_cont = defaultdict(list)
    for j, b in enumerate(source):
        by_cont[b["cont"]].append(j)

    def closest(js, day, limit):
        best = min(((days(day, source[j]["date"]), j) for j in js), default=None)
        return best[1] if best and best[0] <= limit else None

    def where(j):
        s = sheet[b_pair[j]]
        return f"chuyến nguồn {source[j]['date']} đã ghép {s['tab']} dòng {s['row']}"

    groups = defaultdict(list)
    for s in sheet:
        if s["date"] and ISO.fullmatch(s["cont"]):
            groups[(s["cont"], s["date"])].append(s)
    in_dup, counts = set(), Counter()
    for (cont, day), rows in groups.items():
        if sum(1 for s in rows if s["amount"]) > 1:
            near = sum(1 for j in by_cont.get(cont, ()) if days(day, source[j]["date"]) <= PAIR_DAYS)
            counts["nhom_trung"] += 1
            counts["nhom_trung_nguon_mot_chuyen"] += near == 1
            for s in rows:
                in_dup.add(id(s))
                out.append(("TRUNG", s, None, f"{len(rows)} dòng cùng container + ngày; nguồn có {near} chuyến ±3 ngày"))
    paired_js = defaultdict(list)
    for j in b_pair:
        paired_js[source[j]["cont"]].append(j)
    used_near = set()
    for i, s in enumerate(sheet):
        if i in s_pair:
            continue
        # A free source trip within 31 days explains the row better (mistyped date) than a swapped duplicate.
        free = closest([j for j in by_cont.get(s["cont"], ()) if j not in b_pair], s["date"], NEAR_DAYS) if s["date"] else None
        if s["date"] and s["amount"] and id(s) not in in_dup:
            hit = closest(paired_js[s["cont"]], s["date"], PAIR_DAYS)
            if hit is not None:
                out.append(("TRUNG_GAN", s, source[hit], where(hit)))
                continue
            other = swapped(s["date"]) if free is None else None
            hit = closest(paired_js[s["cont"]], other, PAIR_DAYS) if other else None
            if hit is not None:
                out.append(("TRUNG_DAO_NGAY", s, source[hit], where(hit)))
                continue
        if not in_window(family_of(s["mode"]), s["month"], end):
            continue
        if s["cont"] not in by_cont:
            out.append(("KHONG_NGUON", s, None, ""))
        elif free is not None:
            used_near.add(free)
            out.append(("LECH_NGAY", s, source[free], f"chưa ghép: lệch {days(s['date'], source[free]['date'])} ngày"))
    tab_owner, owner_tab, first = defaultdict(Counter), defaultdict(Counter), {}
    for s in sheet:
        first[s["tab"]] = min(first.get(s["tab"], "9999-99"), s["month"])
    for i, j in s_pair.items():
        tab_owner[sheet[i]["tab"]][owner_key(source[j]["owner"])] += 1
        owner_tab[owner_key(source[j]["owner"])][sheet[i]["tab"]] += 1
    for i, j in s_pair.items():
        s, b = sheet[i], source[j]
        if not s["date"]:
            out.append(("NGAY_TU_NGUON", s, b, f"ngày theo nguồn {b['date']}"))
        elif s["date"] != b["date"]:
            out.append(("LECH_NGAY", s, b, f"lệch {days(s['date'], b['date'])} ngày"))
        top, key = tab_owner[s["tab"]].most_common(1)[0][0], owner_key(b["owner"])
        if key and top and key not in top and top not in key:
            out.append(("KHAC_KHACH", s, b, "chủ hàng nguồn khác khách của sổ"))
        price = price_vnd(b["price"]) if b["family"] == "BIEN" else None
        if price is not None and s["amount"] and price != s["amount"]:
            out.append(("GIA_KHAC", s, b, f"nguồn ghi {b['price']}"))
    for j, b in enumerate(source):
        month = b["date"][:7]
        if j in b_pair or j in used_near or not in_window(b["family"], month, end):
            continue
        tabs = owner_tab.get(owner_key(b["owner"]))
        main_tab = tabs.most_common(1)[0][0] if tabs else None
        if month == end:
            group = "THANG_CUOI"
        elif main_tab is None:
            group = "CHU_HANG_CHUA_GHEP"
        else:
            group = "TRUOC_KHI_CO_SO" if month < first[main_tab] else "CHUA_TINH"
        out.append((group, None, b, f"sổ gợi ý {main_tab} (từ {first[main_tab]})" if main_tab else ""))
    return out, dict(counts)


def summarize(sheet, source, stats, s_pair, review_rows, dup_counts, end) -> dict[str, Any]:
    table: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    start = min(START.values())
    for i, s in enumerate(sheet):
        keys = [f"{s['month'][:4]} {s['mode']}"]
        if family_of(s["mode"]) and start <= s["month"] <= end:
            keys.append(f"{start}..{end} CANG+BO")
        for key in keys:
            cell = table[key]
            cell[0] += 1
            cell[2] += s["amount"]
            if i in s_pair:
                cell[1] += 1
                cell[3] += s["amount"]
    same_day = Counter()
    for i, j in s_pair.items():
        if sheet[i]["date"]:
            same_day[(source[j]["family"], sheet[i]["date"] == source[j]["date"])] += 1
    pct = lambda part, whole: round(100 * part / whole, 1) if whole else None  # noqa: E731
    return {
        "end_month": end, "sheet_trip_rows": len(sheet), "source_trips": dict(Counter(b["family"] for b in source)),
        "source_stats": dict(stats),
        "coverage": {k: {"rows": v[0], "paired": v[1], "pct_rows": pct(v[1], v[0]), "pct_amount": pct(v[3], v[2])}
                     for k, v in sorted(table.items())},
        "same_day_pct": {f: pct(same_day[(f, True)], same_day[(f, True)] + same_day[(f, False)]) for f in ("BIEN", "BO")},
        "groups": dict(Counter(g for g, *_ in review_rows)), **dup_counts,
    }


def write_csv(path: pathlib.Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def previous_month_vn() -> str:
    first = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date().replace(day=1)
    return (first - timedelta(days=1)).isoformat()[:7]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xlsx", required=True, type=pathlib.Path, help="sổ gốc tải theo runbook")
    parser.add_argument("--source", required=True, action="append", type=pathlib.Path, help="newest first")
    parser.add_argument("--out", required=True, type=pathlib.Path, help="outside the repository: the files carry names")
    parser.add_argument("--end-month", help="last month with sources (default: month before today, VN time)")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    if out == REPO or REPO in out.parents:
        print(json.dumps({"ok": False, "reason": "OUT_INSIDE_REPO"}))
        return 2
    end = args.end_month or previous_month_vn()
    try:
        source, stats = load_sources(args.source)
        sheet = load_sheet(args.xlsx)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, loader.LoadError) as exc:
        print(json.dumps({"ok": False, "reason": type(exc).__name__}))
        return 2
    s_pair, b_pair = pair(sheet, source)
    rows, dup_counts = review(sheet, source, s_pair, b_pair, end)
    out.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(sheet):
        b = source[s_pair[i]] if i in s_pair else {}
        s.update(source_tab=b.get("tab", ""), source_line=b.get("line", ""), source_date=b.get("date", ""),
                 source_owner=b.get("owner", ""))
    write_csv(out / "sheet_rows.csv", ["tab", "row", "month", "date", "raw_date", "cont", "mode", "amount",
                                       "source_tab", "source_line", "source_date", "source_owner"], sheet)
    for j, b in enumerate(source):
        b.update(sheet_tab=sheet[b_pair[j]]["tab"] if j in b_pair else "", sheet_row=sheet[b_pair[j]]["row"] if j in b_pair else "")
    write_csv(out / "source_rows.csv", ["family", "tab", "line", "cont", "date", "owner", "ref", "price",
                                        "sheet_tab", "sheet_row"], source)
    write_csv(out / "can_xem.csv", ["nhom", "tab", "dong", "thang_khoi", "ngay_so", "container", "tien_vnd",
                                    "chu_hang_nguon", "nguon", "dong_nguon", "ngay_nguon", "ghi_chu"],
              [{"nhom": g, "tab": (s or {}).get("tab", ""), "dong": (s or {}).get("row", ""),
                "thang_khoi": (s or {}).get("month", ""), "ngay_so": (s or {}).get("date") or (s or {}).get("raw_date", ""),
                "container": (s or b or {}).get("cont", ""), "tien_vnd": (s or {}).get("amount", ""),
                "chu_hang_nguon": (b or {}).get("owner", ""), "nguon": (b or {}).get("tab", ""),
                "dong_nguon": (b or {}).get("line", ""), "ngay_nguon": (b or {}).get("date", ""), "ghi_chu": note}
               for g, s, b, note in rows])
    print(json.dumps(summarize(sheet, source, stats, s_pair, rows, dup_counts, end), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
