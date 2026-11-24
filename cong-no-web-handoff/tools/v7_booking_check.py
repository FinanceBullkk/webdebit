#!/usr/bin/env python3
"""Kiểm sổ so với booking mỗi giờ: sổ web (DU-CHUYEN-01, tiêu chí số 1) và Sheet sổ nợ (KIEM-BOOKING-01;
NGUON-CHUYEN-01, specs/v7-chuyen-theo-nguon.md).

Phần sổ web (`run_web_safely`) chạy trong lượt đối soát sau khi lượt đọc sổ mọi khách, ghi `booking-web.json` cạnh file kiểm
Sheet. Phần Sheet dưới đây giữ như trước.

Chạy trong lượt đối soát máy (`v7_reconcile_auto.py`), trên chính bản xlsx sổ gốc lượt đó vừa tải, nên không tải Sheet thêm lần nào.
Nguồn booking là hai bản chụp timer `webdebit-sheet-sync` ghi: `snapshot.json` (CONT_NGUON, chuyến biển) và `road.json` (CONT_BO,
chuyến bộ). Ghép và phân nhóm bằng đúng luật của công cụ GĐ1 (`v7_trip_source_match`), chỉ trong khoảng hai bản chụp phủ (`WINDOW`).

Chỉ đọc: không vào DB, không ghi sổ, không ghi Sheet. Kết quả ghi `booking-check.json` (mode 600, có tên tab khách và số tiền) để
API `GET /api/v7/machine/booking` trả sau xác thực; stdout và log chỉ có số đếm. Bản chụp nguồn thiếu, hỏng, rỗng hoặc cũ thì không
kiểm: giữ kết quả lượt trước, thêm `last_error` để trang báo lỗi chứ không báo "không có gì lệch".

Chạy tay (bản tải theo runbook, thư mục ngoài Git):

    v7_booking_check.py --xlsx SO_GOC.xlsx [--snapshot snapshot.json --road road.json] --output DIR/booking-check.json
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import v7_load_real_copy as loader
import v7_price_snapshot as snapshots
import v7_trip_source_match as match

VN = ZoneInfo("Asia/Ho_Chi_Minh")
FOLDER = Path("/var/lib/webdebit-sheet-sync")
# Tháng đầu hai bản chụp phủ đủ, đo trên hao 13/11/2026: CONT_NGUON 11/2025 mới 87 chuyến rồi từ 12/2025 mỗi tháng 349–704;
# CONT_BO từ 08/2025 (07/2025 có 2 chuyến). Trước các tháng này không báo "không có nguồn" hay "booking có, sổ chưa tính".
WINDOW = {"BIEN": "2025-12", "BO": "2025-08"}
SOURCE_MAX_AGE = dt.timedelta(hours=3)   # timer bản chụp 15 phút một lần; quá 3 giờ là timer hỏng, nguồn thiếu chuyến mới
TIMEOUT = 900   # giây; đo 13/11/2026 một lượt khoảng 250 giây, unit đối soát có TimeoutStartSec=1500
# Mã nhóm của công cụ GĐ1 -> nhóm trên trang, theo thứ tự chủ sổ hỏi: bốn nhóm đầu đụng tiền, ba nhóm sau chỉ để biết.
# Không lên trang, chỉ đếm: TRUOC_KHI_CO_SO (chuyến trước tháng đầu của tab khách nằm trong số dư đầu kỳ; đo 13/11/2026: 550 chuyến,
# toàn bộ 08–12/2025) và GIA_KHAC (bản chụp CONT_NGUON không có cột giá chữ nên không sinh ra).
GROUPS = {
    "TRUNG": "dup", "TRUNG_GAN": "dup", "TRUNG_DAO_NGAY": "dup",
    "CHUA_TINH": "missing", "CHU_HANG_CHUA_GHEP": "missing",
    "KHAC_KHACH": "other", "KHONG_NGUON": "nosource",
    "LECH_NGAY": "date", "NGAY_TU_NGUON": "nodate", "THANG_CUOI": "recent",
}
ORDER = ("dup", "missing", "other", "nosource", "date", "nodate", "recent")
# Bản chép 0đ trong báo cáo tháng: cùng ngưỡng 31 ngày với nhóm lệch ngày của công cụ GĐ1. Đo 16/11/2026: khối tháng cũ để 0đ ngày 07/10
# cho chuyến đã tính ở khối sau ngày 26/10 (19 ngày). Dòng 0đ không mang tiền nên nới ngưỡng không che được tiền tính hai lần.
COPY_DAYS = 31
# Khoảng đếm chuyến booking và dòng sổ cùng container quanh một chuyến "booking có, sổ chưa tính" (lọc nhiễu 24/11/2026).
NEAR_COUNT_DAYS = 45


class CheckError(Exception):
    """Mã lỗi không lộ dữ liệu."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def now_vn() -> dt.datetime:
    return dt.datetime.now(VN)


def read_snapshot(path: Path, label: str, now: dt.datetime) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CheckError(f"{label}_MISSING") from exc
    except (OSError, ValueError) as exc:
        raise CheckError(f"{label}_UNREADABLE") from exc
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        raise CheckError(f"{label}_UNREADABLE")
    if not data["rows"]:
        raise CheckError(f"{label}_EMPTY")
    try:
        created = dt.datetime.fromisoformat(str((data.get("runner") or {}).get("created_at")))
    except ValueError as exc:
        raise CheckError(f"{label}_UNREADABLE") from exc
    if created.tzinfo is None or now - created > SOURCE_MAX_AGE:
        raise CheckError(f"{label}_STALE")
    return data


def snapshot_sources(sea: dict[str, Any], road: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str], list[dict[str, Any]]]:
    """Dòng hai bản chụp thành chuyến nguồn dạng của công cụ GĐ1 (`load_sources`), cộng các dòng booking người giữ booking phải sửa.

    Lấy mọi dòng có container và ngày, kể cả dòng thiếu xe hay nơi đến (vẫn là một chuyến đã đi). Hai dòng cùng container, cùng ngày
    trong một bản chụp là một chuyến; dòng của bản chụp sau lặp chuyến (±3 ngày) của bản trước thì bỏ, như `load_sources`.

    Dòng không thành chuyến chia hai loại (lọc nhiễu 24/11/2026, KIEM-BOOKING-01):
    - `dong_khong_phai_chuyen`: ô container trống, hoặc không phải số container hay biển số mà cũng không có ngày đọc được. Đo 24/11/2026:
      190 dòng CONT_NGUON, là dòng cuối của từng tab tháng (container trống, ngày 1900) và dòng tiêu đề mặt hàng ("THANHLONG" ở cột
      container, ngày trống hoặc 1900). Không phải lỗi. Ô container lạ mà có ngày vẫn là chuyến như trước (có thể là số gõ thiếu).
    - `dong_thieu_ngay`: có số container mà ô ngày trống, không đọc được hoặc trước năm 2000 (ô rác). Đây là chuyến thật không so được
      với sổ: trả về trong danh sách thứ ba kèm tab nguồn và dòng nguồn để người giữ booking sửa (đo 24/11/2026: 23 dòng biển, 14 dòng bộ).
    """
    rows: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    fix: list[dict[str, Any]] = []
    seen: dict[str, list[tuple[dt.date, str]]] = defaultdict(list)
    for tab, family, data, owner, ref in (("CONT_NGUON", "BIEN", sea, "customer_name", "booking"), ("CONT_BO", "BO", road, "owner", "plate")):
        same: set[tuple[str, str]] = set()
        for item in data["rows"]:
            cont, day = match.container_key(item.get("container")), str(item.get("event_date") or "")
            if not cont or ((not day or day < "2000") and not match.trip_like(cont)):
                stats["dong_khong_phai_chuyen"] += 1
                continue
            if not day or day < "2000":
                stats["dong_thieu_ngay"] += 1
                # Chuyến biển: CONT_NGUON chép từ tab tháng của file booking, người sửa ở tab đó ("Tab nguồn", "Dòng nguồn").
                fix.append({"family": family, "tab": str(item.get("source_tab") or tab), "line": item.get("source_line") or item.get("source_row"),
                            "cont": cont, "owner": str(item.get(owner) or ""), "ref": str(item.get(ref) or ""),
                            "raw_date": str(item.get("source_date") or "")})
                continue
            if (cont, day) in same:
                stats["dong_lap_cung_ngay"] += 1
                continue
            when = dt.date.fromisoformat(day)
            if any(other != tab and abs((when - old).days) <= match.PAIR_DAYS for old, other in seen[cont]):
                stats["dong_lap_tab_truoc"] += 1
                continue
            same.add((cont, day))
            seen[cont].append((when, tab))
            rows.append({"family": family, "tab": tab, "line": item.get("source_row"), "cont": cont, "date": day,
                         "owner": str(item.get(owner) or ""), "ref": str(item.get(ref) or ""), "price": ""})
    fix.sort(key=lambda row: (row["family"] != "BIEN", row["tab"], int(str(row["line"])) if str(row["line"]).isdigit() else 0))
    return rows, stats, fix


def near_counts(day: str, trips: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, int]:
    """Số chuyến booking (`trips`) và số dòng sổ mọi tab (`rows`) của cùng container quanh một chuyến booking chưa ghép, trong
    ±`NEAR_COUNT_DAYS` ngày (dòng sổ không ngày: khối tháng đó hoặc liền kề). Booking nhiều chuyến hơn sổ thì có thể sót một chuyến hoặc
    booking ghi lặp; sổ không có dòng nào thì chuyến chưa ở sổ nào. Chỉ để người xem đọc, không đổi nhóm."""
    when = dt.date.fromisoformat(day)
    first = when.replace(day=1)
    months = {(first - dt.timedelta(days=1)).isoformat()[:7], day[:7], (first + dt.timedelta(days=32)).isoformat()[:7]}
    close = lambda other: abs((dt.date.fromisoformat(other) - when).days) <= NEAR_COUNT_DAYS  # noqa: E731
    return {"booking": sum(1 for b in trips if close(b["date"])),
            "sheet": sum(1 for s in rows if (close(s["date"]) if s["date"] else s["month"] in months))}


def shown(code: str, sheet_row: dict | None, source_row: dict | None, window: dict[str, str]) -> bool:
    """Chỉ trong khoảng hai bản chụp phủ: dòng sổ theo tháng khối, chuyến nguồn theo ngày nguồn. Dòng sổ không thuộc biển hay bộ
    (hàng nhập, bán cước) theo mốc muộn hơn. Khách khác chỉ xét chuyến biển: chuyến bộ lấy khách theo sổ (NGUON-CHUYEN-01 (2))."""
    if code not in GROUPS or (code == "KHAC_KHACH" and (source_row or {}).get("family") != "BIEN"):
        return False
    family = match.family_of(sheet_row["mode"]) if sheet_row else source_row["family"]
    month = sheet_row["month"] if sheet_row else source_row["date"][:7]
    return month >= window.get(family or "", max(window.values()))


def check(xlsx: Path, sea_path: Path, road_path: Path, now: dt.datetime, window: dict[str, str] | None = None) -> dict[str, Any]:
    """Tên sổ là tên tab khách trên Sheet; trang ghép với sổ web theo tên như lượt đối soát."""
    return evaluate(xlsx, sea_path, road_path, now, window)[0]


def evaluate(xlsx: Path, sea_path: Path, road_path: Path, now: dt.datetime,
             window: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Kết quả kiểm cho tab Máy chạy và báo cáo tháng (BAO-CAO-THANG-01) từ cùng một lần đọc và ghép."""
    window = window or WINDOW
    sea, road = read_snapshot(sea_path, "SEA", now), read_snapshot(road_path, "ROAD", now)
    source, stats, fix = snapshot_sources(sea, road)
    if not source:
        raise CheckError("SOURCE_EMPTY")
    sheet = match.load_sheet(Path(xlsx))
    end = now.date().isoformat()[:7]
    s_pair, b_pair = match.pair(sheet, source)
    found, dup_counts = match.review(sheet, source, s_pair, b_pair, end, window)
    rows, hidden, in_window = page_rows(sheet, source, s_pair, b_pair, found, end, window)
    if not in_window:   # Sheet đổi cấu trúc thì không được ra "0/0 khớp, không thấy gì lệch"
        raise CheckError("SHEET_EMPTY")
    result = {
        **head(now, window, end, sea, road, source, stats),
        "sheet": {"rows": len(in_window), "paired": sum(1 for i in in_window if i in s_pair)},
        "counts": {group: sum(1 for row in rows if row["group"] == group) for group in ORDER},
        "dup_groups": dup_counts.get("nhom_trung", 0), "hidden": dict(hidden),
        "rows": rows,
        # Chuyến có số container mà ô ngày booking trống hay sai: người giữ booking sửa ở tab nguồn (người dùng chọn 24/11/2026).
        "booking_fix": fix,
    }
    return result, month_report(sheet, source, s_pair, found, now, window)


def head(now: dt.datetime, window: dict[str, str], end: str, sea: dict, road: dict, source: list[dict], stats: Counter) -> dict[str, Any]:
    return {"version": 1, "checked_at": now.isoformat(timespec="seconds"), "window": {**window, "end": end},
            "sources": {name: {"created_at": data["runner"]["created_at"], "sha256": data.get("sha256"), "rows": len(data["rows"])}
                        for name, data in (("sea", sea), ("road", road))},
            "source_trips": dict(Counter(b["family"] for b in source)), "source_stats": dict(stats)}


def page_rows(sheet: list[dict], source: list[dict], s_pair: dict[int, int], b_pair: dict[int, int], found: list, end: str,
              window: dict[str, str]) -> tuple[list[dict[str, Any]], Counter[str], list[int]]:
    """Dòng cho trang (đã lọc theo khoảng kiểm), số dòng ẩn theo mã, và chỉ số các dòng sổ trong khoảng kiểm. Dòng sổ mang
    `customer_id` (sổ web) thì dòng trang mang theo, để trang mở đúng sổ không cần ghép tên."""
    sheet_index, source_index = {id(s): i for i, s in enumerate(sheet)}, {id(b): j for j, b in enumerate(source)}
    by_cont, sheet_by_cont = defaultdict(list), defaultdict(list)
    for item in source:
        by_cont[item["cont"]].append(item)
    for item in sheet:
        sheet_by_cont[item["cont"]].append(item)
    rows, hidden = [], Counter()
    for code, s, matched, _note in found:
        b = matched
        if not shown(code, s, b, window):
            hidden[code] += 1
            continue
        pair, near = None, None
        if code == "TRUNG":   # công cụ GĐ1 không gắn nguồn cho nhóm này: dòng đã ghép thì lấy chuyến của nó, kèm số chuyến quanh ngày
            b = source[s_pair[sheet_index[id(s)]]] if sheet_index[id(s)] in s_pair else None
            near = sum(1 for item in by_cont.get(s["cont"], ()) if match.days(s["date"], item["date"]) <= match.PAIR_DAYS)
        if code in ("TRUNG_GAN", "TRUNG_DAO_NGAY"):
            other = sheet[b_pair[source_index[id(b)]]]
            pair = {"tab": other["tab"], "row": other["row"], "date": other["date"]}
        rows.append({
            "group": GROUPS[code], "code": code,
            "tab": s["tab"] if s else None, "row": s["row"] if s else None, "month": s["month"] if s else b["date"][:7],
            "date": s["date"] if s else None, "raw_date": (s.get("raw_date") or None) if s and not s["date"] else None,
            "container": (s or b)["cont"], "amount_vnd": str(s["amount"]) if s and s["amount"] else None,
            "source": {"kind": b["family"], "date": b["date"], "owner": b["owner"], "ref": b["ref"], "tab": b["tab"], "line": b["line"]} if b else None,
            "suggest": {"tab": b["suggest_tab"], "from": b.get("suggest_from")} if b and not s and b.get("suggest_tab") else None,
            "pair": pair, "paired": s is not None and sheet_index[id(s)] in s_pair, "near_trips": near,
            "gap_days": match.days(s["date"], b["date"]) if s and b and s["date"] else None,
            "near": near_counts(b["date"], by_cont[b["cont"]], sheet_by_cont[b["cont"]]) if GROUPS[code] == "missing" else None,
            **({"customer_id": s["customer_id"]} if s and s.get("customer_id") is not None else {}),
        })
    rows.sort(key=lambda row: (ORDER.index(row["group"]), row["container"], row["date"] or (row["source"] or {}).get("date") or ""))
    in_window = [i for i, s in enumerate(sheet) if match.in_window(match.family_of(s["mode"]), s["month"], end, window)]
    return rows, hidden, in_window


def web_rows(books: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chuyến của sổ web (chuyến web và dòng chuyến sổ gốc, bản hiện hành, chưa xóa) thành dòng sổ dạng công cụ GĐ1 (DU-CHUYEN-01).

    `books`: mỗi sổ `{"id", "name", "transport_mode", "trips"}` với `trips` là `v7_price_queue.targets` của `get_ledger` (lượt đối soát
    đã đọc sẵn, không vào DB thêm). Biển hay bộ theo `transport_mode` của sổ; sổ chưa gán thì theo tên như sổ gốc (`mode_of`). Tiền:
    đơn giá của chuyến web, tổng đã tính của dòng sổ gốc; chưa có thì 0, chỉ để ưu tiên dòng mang tiền khi ghép (công cụ GĐ1 cũng gộp
    như vậy)."""
    rows = []
    for book in books:
        mode = book.get("transport_mode")
        mode = mode if mode in ("CANG", "BO") else match.mode_of(str(book.get("name") or ""), {})
        for trip in book.get("trips") or ():
            day = trip.get("date")
            money = trip.get("total") if trip.get("kind") == "legacy" else trip.get("price")
            rows.append({"tab": str(book.get("name") or ""), "row": f"{trip.get('kind')}:{trip.get('id')}", "customer_id": book.get("id"),
                         "month": str(trip.get("month") or "")[:7], "date": day.isoformat() if hasattr(day, "isoformat") else (day or None),
                         "raw_date": "", "cont": match.container_key(trip.get("container")), "mode": mode, "amount": int(money or 0)})
    return [row for row in rows if row["cont"] and len(row["month"]) == 7]


def evaluate_web(books: list[dict[str, Any]], sea_path: Path, road_path: Path, now: dt.datetime,
                 window: dict[str, str] | None = None) -> dict[str, Any]:
    """Sổ web so với booking (DU-CHUYEN-01: đủ chuyến booking là tiêu chí số 1), cùng luật ghép và nhóm như phép kiểm Sheet.

    `booking`: số chuyến booking trong khoảng kiểm (trừ chuyến trước tháng đầu của sổ, nằm trong số dư đầu kỳ) và số đã có trên web.
    `web`: số dòng chuyến web trong khoảng kiểm và số ghép được booking."""
    window = window or WINDOW
    sea, road = read_snapshot(sea_path, "SEA", now), read_snapshot(road_path, "ROAD", now)
    source, stats, fix = snapshot_sources(sea, road)
    if not source:
        raise CheckError("SOURCE_EMPTY")
    sheet = web_rows(books)
    end = now.date().isoformat()[:7]
    s_pair, b_pair = match.pair(sheet, source)
    found, dup_counts = match.review(sheet, source, s_pair, b_pair, end, window)
    rows, hidden, in_window = page_rows(sheet, source, s_pair, b_pair, found, end, window)
    if not in_window:   # đọc sổ web hỏng thì không được ra "0/0, không thấy gì lệch"
        raise CheckError("WEB_EMPTY")
    early = {id(b) for code, s, b, _note in found if s is None and code == "TRUOC_KHI_CO_SO"}
    counted = [j for j, b in enumerate(source) if match.in_window(b["family"], b["date"][:7], end, window) and id(b) not in early]
    return {
        **head(now, window, end, sea, road, source, stats), "compare": "web",
        "booking": {"trips": len(counted), "on_web": sum(1 for j in counted if j in b_pair)},
        "web": {"rows": len(in_window), "paired": sum(1 for i in in_window if i in s_pair)},
        "counts": {group: sum(1 for row in rows if row["group"] == group) for group in ORDER},
        "dup_groups": dup_counts.get("nhom_trung", 0), "hidden": dict(hidden),
        "rows": rows, "booking_fix": fix,
    }


def web_path(output: Path) -> Path:
    """File kết quả so sổ web, cạnh file kiểm Sheet."""
    return output.with_name("booking-web.json")


def run_web_safely(books: list[dict[str, Any]], output: Path, sea_path: Path, road_path: Path,
                   now: dt.datetime | None = None) -> dict[str, Any]:
    """Cho lượt đối soát, sau khi đọc sổ mọi khách: ghép ngay trong tiến trình (vài giây, không đọc xlsx). Lỗi thành mã và
    `last_error`, kết quả lượt đạt trước vẫn giữ; không bao giờ ném ra (lượt có thể đã ghi tiền)."""
    now, started = now or now_vn(), time.monotonic()
    try:
        result = evaluate_web(books, sea_path, road_path, now)
        snapshots.write(result, output)
    except Exception as exc:  # noqa: BLE001  (lỗi thành mã, không in dữ liệu)
        code = failure_code(exc)
        print(f"V7 kiểm booking với sổ web: không kiểm được ({code})", file=sys.stderr, flush=True)
        with contextlib.suppress(Exception):
            record_failure(output, code, now)
        return {"error": code, "seconds": round(time.monotonic() - started)}
    return {"counts": result["counts"], "booking": result["booking"], "web_rows": result["web"]["rows"],
            "paired": result["web"]["paired"], "seconds": round(time.monotonic() - started)}


def month_report(sheet: list[dict], source: list[dict], s_pair: dict[int, int], found: list, now: dt.datetime,
                 window: dict[str, str]) -> dict[str, Any]:
    """Báo cáo tháng (BAO-CAO-THANG-01): mọi chuyến theo tháng NGÀY CHUYẾN, từ tháng cả hai bản chụp cùng phủ tới tháng hiện tại.

    Mỗi dòng là một chuyến (hoặc một dòng Sheet không thành chuyến), trạng thái:
    - `khop`: dòng Sheet ghép được chuyến booking; tháng theo ngày booking (NGUON-CHUYEN-01: ngày theo nguồn).
    - `chep`: dòng Sheet 0đ không ghép được, mà cùng container đã có dòng Sheet khác ghép booking cách không quá `COPY_DAYS` ngày (ví dụ một tab chép
      chuyến của tab khác cùng khách, hay khối tháng cũ để 0đ khi chuyến đã tính ở khối sau). Không đếm là chuyến.
    - `khong_booking`: dòng Sheet có ngày, không ghép được, không phải bản chép. `khong_ngay`: dòng Sheet không ngày, không ghép được;
      tháng theo khối tháng của Sheet. `ngoai`: dòng Sheet không thuộc biển hay bộ (hàng nhập, bán cước), không có booking để so.
    - `lech_ngay`: dòng Sheet chưa ghép nhưng có chuyến booking cùng container lệch 4–31 ngày (nhóm LECH_NGAY của công cụ GĐ1): vẫn
      là một chuyến ở cả hai bên, chỉ lệch ngày; tháng theo ngày booking.
    - `thieu`: chuyến booking không dòng Sheet nào ghép; tab là sổ máy đoán (có thể trống). Chuyến trước tháng đầu của tab khách nằm
      trong số dư đầu kỳ, không cộng lại (AGENTS.md): chỉ đếm ở `before_book`, không thành dòng.
    """
    start, end = max(window.values()), now.date().isoformat()[:7]
    early = {id(b) for code, s, b, _note in found if s is None and b is not None and code == "TRUOC_KHI_CO_SO"}
    unpaired = {id(s) for i, s in enumerate(sheet) if i not in s_pair}
    holder = {id(source[j]): sheet[i] for i, j in s_pair.items()}
    near, copied = {}, set()
    for code, s, b, _note in found:
        if code == "LECH_NGAY" and s is not None and id(s) in unpaired:
            near[id(s)] = b
            if id(b) in holder:   # a 0đ copy took the trip and this row charges it: the trip is this row's, the copy is `chep`
                copied.add(id(holder[id(b)]))
    paired_at = defaultdict(list)   # container -> ngày của các dòng Sheet đã ghép, để nhận bản chép 0đ
    for i, j in s_pair.items():
        paired_at[sheet[i]["cont"]].append(source[j]["date"])
    months: dict[str, list[dict[str, Any]]] = {}
    before = Counter()

    def put(month: str | None, row: dict[str, Any]) -> None:
        if month and start <= month <= end:
            months.setdefault(month, []).append(row)

    for i, s in enumerate(sheet):
        family = match.family_of(s["mode"])
        row = {"tab": s["tab"], "row": s["row"], "block": s["month"], "cont": s["cont"], "family": family,
               "amount_vnd": str(s["amount"]) if s["amount"] else None, "date": s["date"]}
        if i in s_pair and id(s) not in copied:
            b = source[s_pair[i]]
            put(b["date"][:7], {**row, "status": "khop", "family": b["family"], "booking": {"date": b["date"], "owner": b["owner"], "ref": b["ref"]}})
        elif id(s) in near:
            b = near[id(s)]
            put(b["date"][:7], {**row, "status": "lech_ngay", "family": b["family"], "booking": {"date": b["date"], "owner": b["owner"], "ref": b["ref"]}})
        elif not s["date"]:
            put(s["month"], {**row, "status": "khong_ngay"})
        elif family is None:
            put(s["date"][:7], {**row, "status": "ngoai"})
        elif not s["amount"] and any(match.days(s["date"], day) <= COPY_DAYS for day in paired_at.get(s["cont"], ())):
            put(s["date"][:7], {**row, "status": "chep"})
        else:
            put(s["date"][:7], {**row, "status": "khong_booking"})
    paired, close = set(s_pair.values()), {id(b) for b in near.values()}
    for j, b in enumerate(source):
        if j in paired or id(b) in close:
            continue
        if id(b) in early:
            before[b["date"][:7]] += 1
            continue
        put(b["date"][:7], {"tab": b.get("suggest_tab"), "row": None, "block": None, "cont": b["cont"], "family": b["family"],
                            "amount_vnd": None, "date": None, "status": "thieu",
                            "booking": {"date": b["date"], "owner": b["owner"], "ref": b["ref"]}})
    for rows in months.values():
        rows.sort(key=lambda row: (row["tab"] or "", (row.get("booking") or {}).get("date") or row["date"] or "", row["cont"]))
    return {"version": 1, "checked_at": now.isoformat(timespec="seconds"), "start": start, "end": end,
            "before_book": {month: count for month, count in sorted(before.items()) if start <= month <= end},
            "months": dict(sorted(months.items()))}


def report_path(output: Path) -> Path:
    return output.with_name("booking-report.json")


def failure_code(exc: Exception) -> str:
    if isinstance(exc, CheckError):
        return exc.code
    return str(exc) if isinstance(exc, loader.LoadError) else type(exc).__name__


def record_failure(output: Path, reason: str, now: dt.datetime) -> None:
    """Giữ kết quả lượt đạt gần nhất, thêm lỗi của lượt này."""
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict):
        data = {"version": 1}
    data["last_error"] = {"at": now.isoformat(timespec="seconds"), "reason": reason}
    snapshots.write(data, output)


def counts_line(result: dict[str, Any]) -> dict[str, Any]:
    """Cho stdout, journal và sổ theo dõi: không tên, không tiền."""
    return {"counts": result["counts"], "sheet_rows": result["sheet"]["rows"], "paired": result["sheet"]["paired"],
            "source_trips": result["source_trips"], "booking_fix": len(result.get("booking_fix") or ())}


def run_safely(xlsx: Path, output: Path, sea_path: Path, road_path: Path, now: dt.datetime | None = None) -> dict[str, Any]:
    """Lỗi thành mã và `last_error`; kết quả lượt đạt trước vẫn giữ."""
    now, started = now or now_vn(), time.monotonic()
    try:
        result, report = evaluate(xlsx, sea_path, road_path, now)
        snapshots.write(result, output)
        snapshots.write(report, report_path(output))   # cùng lượt đạt: trang Báo cáo tháng không hiện số của lượt hỏng
    except Exception as exc:  # noqa: BLE001  (lỗi thành mã, không in dữ liệu)
        code = failure_code(exc)
        print(f"V7 kiểm booking: không kiểm được ({code})", file=sys.stderr, flush=True)
        with contextlib.suppress(Exception):
            record_failure(output, code, now)
        return {"error": code, "seconds": round(time.monotonic() - started)}
    return {**counts_line(result), "seconds": round(time.monotonic() - started)}


@contextlib.contextmanager
def alongside(xlsx: Path, output: Path, sea_path: Path, road_path: Path, *, enabled: bool = True, timeout: float = TIMEOUT):
    """Cho lượt đối soát: chạy phép kiểm ở tiến trình con song song với lượt (đọc xlsx mất khoảng 4 phút trên hao, lượt đối soát
    chủ yếu chờ DB), nên lượt không dài thêm. Ra khỏi khối thì chờ con xong, `xlsx` phải còn tới lúc đó; hạn `timeout` tính từ lúc
    con bắt đầu. Khối lỗi thì giết con và ghi `RUN_FAILED`, để trang không hiện số cũ như số mới. Mọi lỗi của phần này thành mã ở
    `job["result"]`, không bao giờ làm đổ lượt (lượt có thể đã ghi tiền)."""
    job: dict[str, Any] = {"result": {"skipped": "OFF"}}
    process, deadline = None, time.monotonic() + timeout
    if enabled:
        try:
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--xlsx", str(xlsx), "--output", str(output),
                                        "--snapshot", str(sea_path), "--road", str(road_path)], stdout=subprocess.PIPE, text=True)
        except Exception as exc:  # noqa: BLE001
            job["result"] = fail(output, f"START_{type(exc).__name__}")
    try:
        yield job
    except BaseException:
        if process:
            with contextlib.suppress(Exception):
                process.kill()
                process.communicate()
            fail(output, "RUN_FAILED")
        raise
    if process:
        try:
            job["result"] = finish(process, output, max(deadline - time.monotonic(), 1.0))
        except Exception as exc:  # noqa: BLE001
            job["result"] = fail(output, type(exc).__name__)


def fail(output: Path, code: str) -> dict[str, str]:
    """Ghi mã lỗi cho trang; chính việc ghi lỗi cũng không được ném ra."""
    print(f"V7 kiểm booking: không kiểm được ({code})", file=sys.stderr, flush=True)
    with contextlib.suppress(Exception):
        record_failure(output, code, now_vn())
    return {"error": code}


def finish(process: subprocess.Popen, output: Path, timeout: float) -> dict[str, Any]:
    try:
        printed, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        return fail(output, "TIMEOUT")
    try:
        line = json.loads(printed.strip().splitlines()[-1])
    except (ValueError, IndexError):
        line = None
    if not isinstance(line, dict):
        return fail(output, f"EXIT_{process.returncode}")
    if line.get("ok"):
        return {key: value for key, value in line.items() if key != "ok"}
    if "error" in line:
        return {"error": str(line["error"])}   # con đã ghi last_error
    return fail(output, str(line.get("reason") or f"EXIT_{process.returncode}"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xlsx", required=True, type=Path, help="bản tải sổ gốc")
    parser.add_argument("--snapshot", type=Path, default=Path(os.getenv("WEBDEBIT_SNAPSHOT_PATH") or FOLDER / "snapshot.json"))
    parser.add_argument("--road", type=Path, default=Path(os.getenv("WEBDEBIT_ROAD_SNAPSHOT_PATH") or FOLDER / "road.json"))
    parser.add_argument("--output", type=Path, required=True, help="file kết quả; có tên khách, phải ngoài Git")
    args = parser.parse_args(argv)
    out = args.output.resolve()
    if match.REPO in out.parents:
        print(json.dumps({"ok": False, "reason": "OUT_INSIDE_REPO"}))
        return 2
    line = run_safely(args.xlsx, out, args.snapshot, args.road)
    print(json.dumps({"ok": "error" not in line, **line}, ensure_ascii=False))
    return 2 if "error" in line else 0


if __name__ == "__main__":
    raise SystemExit(main())
