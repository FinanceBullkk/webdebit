"""Báo cáo tháng (BAO-CAO-THANG-01): tháng này có những khách nào, đi bao nhiêu cont, đối chiếu booking, Sheet sổ nợ và sổ web.

Booking và Sheet: file `booking-report.json` do phép kiểm booking ghi mỗi giờ trong lượt đối soát máy (`tools/v7_booking_check.py`),
mỗi chuyến đã có trạng thái theo tháng ngày chuyến. Web: hàm đọc `get_trip_month` (chuyến có container của mọi sổ đang hoạt động, rộng
ra 3 ngày hai đầu tháng). File này ghép chuyến web với dòng Sheet theo tên tab = tên sổ, cùng container, lệch không quá 3 ngày, rồi
đếm theo khách. Chỉ đọc; số tiền là chuỗi VND nguyên như mọi API, cộng bằng int.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import v7_booking_view
import v7_machine
from v7_api_validate import bad

MONTH = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
ISO = re.compile(r"[A-Z]{4}[0-9]{7}")
PAIR_DAYS = 3   # cùng luật ghép của NGUON-CHUYEN-01 (1)
SHEET_TRIP = ("khop", "lech_ngay", "khong_booking", "ngoai")   # dòng Sheet là một chuyến có ngày
BOOKING_TRIP = ("khop", "lech_ngay", "thieu")
FAMILY_OF_MODE = {"CANG": "BIEN", "BO": "BO"}


def path() -> Path:
    return Path(os.getenv("WEBDEBIT_BOOKING_REPORT_PATH") or v7_machine.base_dir() / "booking-report.json")


def container_key(raw: Any) -> str:
    """Như `v7_trip_source_match.container_key` (web không được nhập tools/, ARCH-02)."""
    text = re.sub(r"[^A-Z0-9]", "", str(raw or "").upper())
    tokens = ISO.findall(text)
    return tokens[0] if len(tokens) == 1 else text


def name_key(name: Any) -> str:
    """Như trang Máy chạy (may-chay-booking.js): bỏ khoảng trắng thừa, giữ hoa thường và dấu."""
    return " ".join(str(name or "").split())


def parse_month(query: str, now: datetime) -> str:
    current = now.astimezone(v7_machine.VN).date().isoformat()[:7]
    if not query:
        return current
    fields = dict(part.split("=", 1) if "=" in part else (part, "") for part in query.split("&"))
    month = fields.get("month", "")
    if set(fields) != {"month"} or not MONTH.fullmatch(month) or month > current:
        bad("INVALID_MONTH", "Tháng phải có dạng YYYY-MM và không sau tháng hiện tại.")
    return month


def read_report() -> dict[str, Any] | None:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("months"), dict) else None


def report_state(report: dict[str, Any] | None, now: datetime) -> str:
    if report is None:
        return "none"
    try:
        checked = datetime.fromisoformat(str(report.get("checked_at")))
    except ValueError:
        return "none"
    if checked.tzinfo is None:
        return "none"
    return "stale" if checked < v7_booking_view.previous_slot(v7_booking_view.last_slot(now)) else "ok"


def _gap(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def _row_day(row: dict[str, Any]) -> str | None:
    return (row.get("booking") or {}).get("date") or row.get("date")


def build(month: str, report: dict[str, Any] | None, web: dict[str, Any], now: datetime) -> dict[str, Any]:
    state = report_state(report, now)
    covered = report is not None and str(report.get("start", "9999")) <= month <= str(report.get("end", ""))
    rows = [dict(row) for row in (report or {}).get("months", {}).get(month, [])] if covered else []
    books = {book["id"]: book for book in web.get("books", [])}
    by_name: dict[str, Any] = {}
    for book in books.values():
        key = name_key(book["name"])
        by_name[key] = None if key in by_name else book["id"]   # hai sổ trùng tên thì không ghép
    trips = defaultdict(list)   # (book, container) -> chuyến web chưa ghép
    for trip in web.get("trips", []):
        if trip.get("date"):
            trips[(trip["customer_id"], container_key(trip["container"]))].append(trip)

    def take(book: int | None, row: dict[str, Any]) -> dict[str, Any] | None:
        pool, day = trips.get((book, row["cont"])), _row_day(row)
        if not pool:
            return None
        near = [t for t in pool if (_gap(t["date"], day) <= PAIR_DAYS if day else t["date"][:7] == month)]
        if not near:
            return None
        best = min(near, key=lambda t: (_gap(t["date"], day) if day else 0, t["date"]))
        pool.remove(best)
        return {"date": best["date"], "source": best["source"]}

    for row in rows:
        row["book_id"] = by_name.get(name_key(row["tab"])) if row.get("tab") else None
    # Dòng có ngày lấy chuyến web trước; dòng Sheet không ngày (ghép theo tháng) sau, để không giành chuyến của dòng có ngày cùng
    # container (đo 16/11/2026: dòng không ngày ở khối cũ lấy mất chuyến web của dòng đã tính ở khối sau); bản chép 0đ lấy phần còn lại.
    for status_group in (("khop", "lech_ngay", "khong_booking", "ngoai", "thieu"), ("khong_ngay",), ("chep",)):
        for row in rows:
            if row["status"] in status_group:
                row["web"] = take(row["book_id"], row)
    for (book, cont), pool in trips.items():
        for trip in pool:
            if trip["date"][:7] == month:
                info = books.get(book) or {}
                rows.append({"tab": info.get("name"), "book_id": book, "row": None, "block": None, "cont": cont,
                             "family": FAMILY_OF_MODE.get(info.get("transport_mode")), "amount_vnd": None, "date": None,
                             "status": "chi_web", "web": {"date": trip["date"], "source": trip["source"]}})

    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = name_key(row["tab"]) if row.get("tab") else f"? {(row.get('booking') or {}).get('owner') or ''}".strip()
        group = groups.setdefault(key, {"name": row.get("tab"), "owner": None if row.get("tab") else (row.get("booking") or {}).get("owner"),
                                        "book_id": row.get("book_id"), "rows": []})
        group["rows"].append(row)
    customers = []
    for group in groups.values():
        info = books.get(group["book_id"]) or {}
        counts = summary(group["rows"], covered, month)
        families = sorted({row["family"] for row in group["rows"] if row["family"]}) or (
            [FAMILY_OF_MODE[info["transport_mode"]]] if info.get("transport_mode") in FAMILY_OF_MODE else [])
        group["rows"].sort(key=lambda row: (_row_day(row) or (row.get("web") or {}).get("date") or "9999", row["cont"]))
        customers.append({**group, **counts, "commodity": info.get("commodity"), "families": families})
    customers.sort(key=lambda item: (-item["issues"], -(item["booking"] or 0), -item["web"], name_key(item["name"] or item["owner"])))
    totals = {family: summary([row for row in rows if row["family"] == family], covered, month) for family in ("BIEN", "BO")}
    totals["ALL"] = summary(rows, covered, month)
    return {"month": month, "state": state if covered else ("none" if report is None else "outside"),
            "checked_at": (report or {}).get("checked_at"), "now": now.isoformat(timespec="seconds"),
            "start": (report or {}).get("start"), "end": (report or {}).get("end"),
            "current": month == now.astimezone(v7_machine.VN).date().isoformat()[:7],
            "before_book": (report or {}).get("before_book", {}).get(month, 0) if covered else 0,
            "totals": totals, "customers": customers}


def summary(rows: list[dict[str, Any]], covered: bool, month: str) -> dict[str, Any]:
    """Booking và Sheet đếm chuyến (bản chép 0đ và dòng không ngày không là chuyến); Web đếm chuyến web có ngày trong tháng."""
    def count(*statuses: str) -> int:
        return sum(1 for row in rows if row["status"] in statuses)

    out = {
        "booking": count(*BOOKING_TRIP) if covered else None,
        "sheet": count(*SHEET_TRIP) if covered else None,
        "web": sum(1 for row in rows if row.get("web") and row["web"]["date"][:7] == month),
        "thieu": count("thieu"), "khong_booking": count("khong_booking"), "lech_ngay": count("lech_ngay"),
        "khong_ngay": count("khong_ngay"), "chep": count("chep"), "ngoai": count("ngoai"), "chi_web": count("chi_web"),
        "web_thieu": sum(1 for row in rows if row["status"] in SHEET_TRIP and not row.get("web")),
        "amount_vnd": str(sum(int(row["amount_vnd"]) for row in rows
                              if row["status"] in (*SHEET_TRIP, "khong_ngay") and row.get("amount_vnd"))),
    }
    out["issues"] = sum(out[key] for key in ("thieu", "khong_booking", "lech_ngay", "khong_ngay", "chi_web", "web_thieu"))
    return out


def handle_get(query: str, runner, reads, actor: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(v7_machine.VN)
    month = parse_month(query, now)
    web = reads.run(runner, "get_trip_month", {"month": f"{month}-01"}, actor)
    return build(month, read_report(), web if isinstance(web, dict) else {}, now)
