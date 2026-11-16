#!/usr/bin/env python3
"""Kiểm Sheet sổ nợ so với booking mỗi giờ (KIEM-BOOKING-01; NGUON-CHUYEN-01, specs/v7-chuyen-theo-nguon.md).

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
TIMEOUT = 900   # giây; đo 13/11/2026 một lượt khoảng 160 giây, unit đối soát có TimeoutStartSec=1500
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


def snapshot_sources(sea: dict[str, Any], road: dict[str, Any]) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Dòng hai bản chụp thành chuyến nguồn dạng của công cụ GĐ1 (`load_sources`).

    Lấy mọi dòng có container và ngày, kể cả dòng thiếu xe hay nơi đến (vẫn là một chuyến đã đi). Ngày trước năm 2000 là ô rác
    (đo 13/11/2026: 175 dòng CONT_NGUON ra 1899–1902). Hai dòng cùng container, cùng ngày trong một bản chụp là một chuyến; dòng của
    bản chụp sau lặp chuyến (±3 ngày) của bản trước thì bỏ, như `load_sources`.
    """
    rows: list[dict[str, Any]] = []
    stats: Counter[str] = Counter()
    seen: dict[str, list[tuple[dt.date, str]]] = defaultdict(list)
    for tab, family, data, owner, ref in (("CONT_NGUON", "BIEN", sea, "customer_name", "booking"), ("CONT_BO", "BO", road, "owner", "plate")):
        same: set[tuple[str, str]] = set()
        for item in data["rows"]:
            cont, day = match.container_key(item.get("container")), str(item.get("event_date") or "")
            if not cont or not day:
                stats["dong_thieu_cont_hoac_ngay"] += 1
                continue
            if day < "2000":
                stats["dong_ngay_sai"] += 1
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
    return rows, stats


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
    window = window or WINDOW
    sea, road = read_snapshot(sea_path, "SEA", now), read_snapshot(road_path, "ROAD", now)
    source, stats = snapshot_sources(sea, road)
    if not source:
        raise CheckError("SOURCE_EMPTY")
    sheet = match.load_sheet(Path(xlsx))
    end = now.date().isoformat()[:7]
    s_pair, b_pair = match.pair(sheet, source)
    found, dup_counts = match.review(sheet, source, s_pair, b_pair, end, window)
    sheet_index, source_index = {id(s): i for i, s in enumerate(sheet)}, {id(b): j for j, b in enumerate(source)}
    by_cont = defaultdict(list)
    for item in source:
        by_cont[item["cont"]].append(item)
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
        })
    rows.sort(key=lambda row: (ORDER.index(row["group"]), row["container"], row["date"] or (row["source"] or {}).get("date") or ""))
    in_window = [i for i, s in enumerate(sheet) if match.in_window(match.family_of(s["mode"]), s["month"], end, window)]
    if not in_window:   # Sheet đổi cấu trúc thì không được ra "0/0 khớp, không thấy gì lệch"
        raise CheckError("SHEET_EMPTY")
    return {
        "version": 1, "checked_at": now.isoformat(timespec="seconds"), "window": {**window, "end": end},
        "sources": {name: {"created_at": data["runner"]["created_at"], "sha256": data.get("sha256"), "rows": len(data["rows"])}
                    for name, data in (("sea", sea), ("road", road))},
        "source_trips": dict(Counter(b["family"] for b in source)), "source_stats": dict(stats),
        "sheet": {"rows": len(in_window), "paired": sum(1 for i in in_window if i in s_pair)},
        "counts": {group: sum(1 for row in rows if row["group"] == group) for group in ORDER},
        "dup_groups": dup_counts.get("nhom_trung", 0), "hidden": dict(hidden),
        "rows": rows,
    }


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
            "source_trips": result["source_trips"]}


def run_safely(xlsx: Path, output: Path, sea_path: Path, road_path: Path, now: dt.datetime | None = None) -> dict[str, Any]:
    """Lỗi thành mã và `last_error`; kết quả lượt đạt trước vẫn giữ."""
    now, started = now or now_vn(), time.monotonic()
    try:
        result = check(xlsx, sea_path, road_path, now)
        snapshots.write(result, output)
    except Exception as exc:  # noqa: BLE001  (lỗi thành mã, không in dữ liệu)
        code = failure_code(exc)
        print(f"V7 kiểm booking: không kiểm được ({code})", file=sys.stderr, flush=True)
        with contextlib.suppress(Exception):
            record_failure(output, code, now)
        return {"error": code, "seconds": round(time.monotonic() - started)}
    return {**counts_line(result), "seconds": round(time.monotonic() - started)}


@contextlib.contextmanager
def alongside(xlsx: Path, output: Path, sea_path: Path, road_path: Path, *, enabled: bool = True, timeout: float = TIMEOUT):
    """Cho lượt đối soát: chạy phép kiểm ở tiến trình con song song với lượt (đọc xlsx mất khoảng 2,5 phút trên hao, lượt đối soát
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
