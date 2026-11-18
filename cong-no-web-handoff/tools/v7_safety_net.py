#!/usr/bin/env python3
"""Lưới an toàn: kiểm sổ thật, chỉ đọc (LUOI-AN-TOAN-01, specs/v7-luoi-an-toan.md).

Máy canh (`v7_watchdog.py`, 15 phút một lượt) gọi `check()`. Một câu SQL (`sokhach.get_safety_net`, giao dịch REPEATABLE READ
READ ONLY) trả kết quả bốn phép kiểm trên cùng một ảnh dữ liệu:

1. Phiếu thu chia đủ: luật của `_check_allocations`, cho mọi sổ có phiếu.
2. Số tổng khớp: con số Tổng quan so với tổng các sổ; mỗi lượt so thêm tổng `get_ledger` của 1/8 số sổ.
3. Sổ không tự đổi: dữ liệu tiền một sổ khác lượt trước mà `version` không tăng (đổi ngoài đường lệnh).
4. Lịch sử chỉ thêm: dòng `sokhach.event` đã thấy ở lượt trước không bị sửa, xóa hay chen thêm.

Kiểm 3, 4 và phần giữ kết quả `get_ledger` cần mốc của lượt trước: file `luoi-an-toan.json` trong `$STATE_DIRECTORY` (drop-in
`StateDirectory=v7-watchdog` của máy canh). Chưa có thư mục đó thì các phần này nghỉ. Kiểm 3, 4 báo mãi tới khi có người chấp nhận.

Chạy tay trên hao dưới user v7app (`-B`: không ghi __pycache__ vào release):

    python3 -B v7_safety_net.py --state-dir /var/lib/v7-watchdog [--dry-run | --accept] [--full]

Câu báo chỉ có mã sổ, tên phần dữ liệu, số đếm và giờ: không tên khách, không số tiền.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import fcntl
except ImportError:  # Windows khi chạy test: không khóa
    fcntl = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))  # tools dùng được tầng web, không có chiều ngược lại
from v7_api_validate import ApiError

ACTOR = "may-canh"
SOCKET_DIR = "/var/run/postgresql"
DATABASE = "webdebit_v7"
DB_USER = "v7_app"
STATE_FILE = "luoi-an-toan.json"
FORMAT = 1
SLICES = 8           # 242 sổ mở bằng get_ledger mất 23 giây trên hao (18/11/2026): mỗi lượt ~30 sổ, mỗi sổ 2 giờ một lần
SETTLE_SECONDS = 600  # dòng Lịch sử mới hơn 10 phút chưa vào mốc (giao dịch còn chạy có thể chen id nhỏ hơn)
SHOW = 5             # số mã sổ tối đa trong một câu báo
VN = ZoneInfo("Asia/Ho_Chi_Minh")

PARTS = {"opening_balance": "số dư đầu", "legacy_row": "dòng sổ gốc", "legacy_trip_rev": "bản sửa dòng sổ gốc", "trip": "chuyến",
         "trip_info_rev": "bản sửa chuyến", "trip_price_rev": "giá chuyến", "trip_fee_line": "phụ phí", "adjustment": "điều chỉnh",
         "receipt": "phiếu thu", "receipt_line": "dòng chia phiếu thu", "offset_pair": "cấn trừ hai sổ", "month_state": "khóa tháng",
         "cutover_customer": "mốc nạp sổ"}
ALLOCATION = {"ALLOCATION_INVARIANT": "Phiếu thu chia không khớp tiền phiếu",
              "ADVANCE_MONTH_INVARIANT": "Tiền ứng trước nằm sai tháng",
              "ALLOCATION_EVENT_INVARIANT": "Dòng chia phiếu thu không khớp Lịch sử"}
TOTALS = {"RECEIVABLE_TOTAL": "tổng Còn phải thu", "RECEIVABLE_COUNT": "số khách còn nợ", "CREDIT_TOTAL": "tổng khách trả thừa",
          "CREDIT_COUNT": "số khách trả thừa", "COMMODITY_TOTAL": "bảng theo mặt hàng", "DEBT_TOTAL": "tổng ở dải hạn trả",
          "DEBT_TIERS": "năm nhóm hạn trả", "DEBT_LIST": "danh sách khách nợ"}
ACCEPT_HINT = "Cần xem rồi chấp nhận."


def now_vn() -> dt.datetime:
    return dt.datetime.now(VN)


def state_dir_from_env() -> Path | None:
    """systemd đặt `STATE_DIRECTORY` khi unit có `StateDirectory=`; nhiều thư mục thì cách nhau bằng `os.pathsep` (`:`)."""
    first = (os.getenv("STATE_DIRECTORY") or "").split(os.pathsep)[0]
    return Path(first) if first else None


def connect(socket_dir: str = SOCKET_DIR, database: str = DATABASE, user: str = DB_USER):
    # Chỉ adapter của tầng DB được dựng lệnh psql (ARCH-01); import muộn để test không cần nó.
    from v7_psql import PsqlDirect
    return PsqlDirect(socket_dir, database, user)


def slot(moment: dt.datetime, slices: int = SLICES) -> int:
    """Phần sổ so get_ledger lượt này: lượt 15 phút liền nhau lấy phần liền nhau."""
    return int(moment.timestamp()) // 900 % slices


def scan(db, options: dict[str, Any]) -> dict[str, Any] | None:
    """Kết quả của hàm SQL; None khi DB chưa nâng (chưa có hàm): mục này im trong lúc chờ đợt nâng DB tay."""
    try:
        return db.run("get_safety_net", options, ACTOR, read_only=True)
    except ApiError:
        if not db.run("has_safety_net", {}, ACTOR).get("ok"):
            return None
        raise


def books_text(ids) -> str:
    ids = sorted(int(value) for value in ids)
    tail = "…" if len(ids) > SHOW else ""
    return "sổ " + ", ".join(str(value) for value in ids[:SHOW]) + tail


def when(moment: str) -> str:
    return f"{dt.datetime.fromisoformat(moment).astimezone(VN):%H:%M ngày %d/%m}"


def allocation_lines(rows: list[dict]) -> list[str]:
    by_code: dict[str, list[int]] = {}
    for row in rows:
        by_code.setdefault(row["code"], []).append(row["customer_id"])
    return [f"{ALLOCATION.get(code, f'Phiếu thu lỗi kiểm ({code})')} ở {len(ids)} sổ ({books_text(ids)})."
            for code, ids in sorted(by_code.items())]


def total_lines(totals: dict, ledger_ids: list[int]) -> list[str]:
    codes = totals.get("codes") or []
    lines = []
    wrong = [TOTALS.get(code, code) for code in codes if code != "ARCHIVED_BALANCE"]
    if wrong:
        listed = totals.get("customers") or []
        tail = f" ({books_text(listed)})" if listed else ""
        lines.append(f"Tổng quan không khớp tổng các sổ: {', '.join(wrong)}{tail}.")
    archived = totals.get("archived") or []
    if "ARCHIVED_BALANCE" in codes:
        lines.append(f"{len(archived)} sổ lưu trữ còn số dư nên Tổng quan không tính ({books_text(archived)}).")
    if ledger_ids:
        lines.append(f"Tổng trong sổ khác tổng Tổng quan dùng ở {len(ledger_ids)} sổ ({books_text(ledger_ids)}).")
    return lines


def merge_ledger(kept: dict | None, ledgers: list[dict | None]) -> tuple[dict, list[int]]:
    """Giữ kết quả get_ledger từng phần sổ tới khi phần đó được so lại, để báo không tắt ở các lượt so phần khác."""
    kept = {"slices": kept.get("slices"), "found": dict(kept.get("found") or {})} if kept else {"slices": None, "found": {}}
    for ledger in ledgers:
        if not ledger:
            continue
        if kept["slices"] != ledger["slices"]:
            kept = {"slices": ledger["slices"], "found": {}}
        kept["found"][str(ledger["slice"])] = sorted(ledger["customers"])
    return kept, sorted({value for found in kept["found"].values() for value in found})


def book_findings(before: dict, after: dict) -> list[dict]:
    """Kiểm 3: so `version` và dấu vân từng phần của mỗi sổ với lượt trước."""
    found = []
    for key, old in before.items():
        new = after.get(key)
        if new is None:
            found.append({"code": "BOOK_GONE", "customer_id": int(key)})
        elif new["version"] < old["version"]:
            found.append({"code": "VERSION_BACK", "customer_id": int(key)})
        elif new["version"] == old["version"] and new["parts"] != old["parts"]:
            parts = sorted(name for name in old["parts"].keys() | new["parts"].keys()
                           if old["parts"].get(name) != new["parts"].get(name))
            found.append({"code": "BOOK_CHANGED", "customer_id": int(key), "parts": parts})
    return found


def event_findings(before: dict, after: dict) -> list[dict]:
    """Kiểm 4: khối Lịch sử đã giữ (dòng id <= upto) phải y hệt khi tính lại trên đúng các dòng đó."""
    if before.get("upto") is None or after.get("check") is None:
        return []
    old, new = before.get("blocks") or {}, after["check"]
    blocks = sorted(int(key) for key in old.keys() | new.keys() if old.get(key) != new.get(key))
    return [{"code": "EVENTS_CHANGED", "blocks": blocks}] if blocks else []


def merge_pending(pending: list[dict], found: list[dict], moment: str) -> list[dict]:
    """Mục chờ cộng dồn tới khi chấp nhận; thấy lại cùng sổ thì gộp phần/khối, giữ giờ thấy đầu tiên."""
    merged = [dict(item) for item in pending]
    for item in found:
        same = next((old for old in merged if (old["code"], old.get("customer_id")) == (item["code"], item.get("customer_id"))), None)
        if same is None:
            merged.append({**item, "since": moment})
            continue
        for field in ("parts", "blocks"):
            if field in item:
                same[field] = sorted(set(same.get(field) or []) | set(item[field]))
    return merged


def pending_lines(pending: list[dict]) -> list[str]:
    def first(items):
        return when(min(item["since"] for item in items))

    def of(code):
        return [item for item in pending if item["code"] == code]

    lines = []
    changed = of("BOOK_CHANGED")
    if len(changed) <= 3:
        for item in changed:
            names = ", ".join(PARTS.get(part, part) for part in item.get("parts") or [])
            lines.append(f"Sổ {item['customer_id']}: {names} đổi mà không qua lệnh nào, thấy lúc {when(item['since'])}. {ACCEPT_HINT}")
    else:
        lines.append(f"Dữ liệu tiền đổi mà không qua lệnh nào ở {len(changed)} sổ ({books_text(i['customer_id'] for i in changed)}), "
                     f"thấy từ {first(changed)}. {ACCEPT_HINT}")
    if back := of("VERSION_BACK"):
        lines.append(f"Số lần ghi của {len(back)} sổ bị lùi ({books_text(i['customer_id'] for i in back)}): DB có thể vừa phục hồi "
                     f"từ bản cũ, thấy lúc {first(back)}. {ACCEPT_HINT}")
    if gone := of("BOOK_GONE"):
        lines.append(f"{len(gone)} sổ biến mất ({books_text(i['customer_id'] for i in gone)}), thấy lúc {first(gone)}. {ACCEPT_HINT}")
    if events := of("EVENTS_CHANGED"):
        blocks = sorted({block for item in events for block in item["blocks"]})
        low, high = max(1, blocks[0] * 1000), blocks[-1] * 1000 + 999
        lines.append(f"Lịch sử có dòng cũ bị sửa hoặc xóa (id {low}–{high}), thấy lúc {first(events)}. {ACCEPT_HINT}")
    if reset := of("STATE_RESET"):
        lines.append(f"Mốc lưới an toàn hỏng, đã lấy mốc mới lúc {first(reset)}: thay đổi trước đó không so được. {ACCEPT_HINT}")
    return lines


def evaluate(result: dict, ledgers: list[dict | None], state: dict | None, now: dt.datetime, *,
             keep: bool, reset: bool = False) -> tuple[dict | None, list[str], list[dict]]:
    """(mốc mới hoặc None khi không giữ mốc, câu báo kiểm 1–2, mục chờ kiểm 3–4)."""
    kept, ledger_ids = merge_ledger((state or {}).get("ledger") if keep else None, ledgers)
    problems = allocation_lines(result["allocations"]) + total_lines(result["totals"], ledger_ids)
    if not keep:
        return None, problems, []
    moment = now.isoformat()
    pending = list((state or {}).get("pending") or [])
    if reset:
        pending = merge_pending(pending, [{"code": "STATE_RESET"}], moment)
    if state is not None:
        found = book_findings(state.get("books") or {}, result["fingerprints"])
        found += event_findings(state.get("events") or {}, result["events"])
        pending = merge_pending(pending, found, moment)
    events = result["events"]
    new_state = {"format": FORMAT, "checked_at": moment, "books": result["fingerprints"],
                 "events": {"upto": events["settled"], "blocks": events["store"]}, "ledger": kept, "pending": pending}
    return new_state, problems, pending


@contextlib.contextmanager
def locked(folder: Path | None) -> Iterator[None]:
    """Lượt timer và lượt chạy tay (--accept) không chen nhau khi đọc rồi ghi mốc."""
    if folder is None or fcntl is None:
        yield
        return
    with open(folder / ".lock", "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def load(folder: Path | None) -> tuple[dict | None, bool]:
    """(mốc, mốc hỏng). Chưa có file là lượt đầu; JSON hỏng thì lấy mốc mới và để mục chờ STATE_RESET."""
    if folder is None:
        return None, False
    try:
        text = (folder / STATE_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, False
    try:
        state = json.loads(text)
    except ValueError:
        return None, True
    return (state, False) if isinstance(state, dict) and state.get("format") == FORMAT else (None, True)


def save(folder: Path, state: dict) -> None:
    temp = folder / (STATE_FILE + ".tmp")
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        json.dump(state, out, ensure_ascii=False, separators=(",", ":"))
    os.replace(temp, folder / STATE_FILE)


def run(now: dt.datetime, *, db=None, state_dir: Path | str | None = None, save_state: bool = True,
        accept: bool = False, full: bool = False, slices: int = SLICES) -> dict[str, Any]:
    folder = Path(state_dir) if state_dir else None
    with locked(folder):
        state, reset = load(folder)
        db = db or connect()
        current = slot(now, slices)
        options = {"event_upto": ((state or {}).get("events") or {}).get("upto"), "ledger_slice": current,
                   "ledger_slices": slices, "settle_seconds": SETTLE_SECONDS}
        result = scan(db, options)
        if result is None:
            return {"ok": True, "problems": [], "accepted": [], "summary": {"skipped": "DB chưa có hàm get_safety_net"}}
        ledgers = [result["ledger"]]
        if full:  # chạy tay: mỗi phần một câu SQL, mỗi câu trong giới hạn 60 giây của câu đọc nền (READ_ONLY_STATEMENT_TIMEOUT)
            ledgers += [scan(db, {**options, "ledger_slice": other})["ledger"] for other in range(slices) if other != current]
        new_state, problems, pending = evaluate(result, ledgers, state, now, keep=folder is not None, reset=reset)
        accepted = []
        if accept and new_state is not None:
            accepted, pending = pending_lines(pending), []
            new_state["pending"] = []
        if new_state is not None and save_state:
            save(folder, new_state)
    problems = problems + pending_lines(pending)
    if folder is None:
        baseline = "không giữ mốc"
    elif state is None:
        baseline = "mốc hỏng, lấy mốc mới" if reset else "lần đầu, lấy mốc"
    else:
        baseline = f"so với lượt {when(state['checked_at'])}"
    summary = {"books": result["books"], "ledger": f"phần {current}/{slices}: {(result['ledger'] or {}).get('checked', 0)} sổ",
               "events_upto": result["events"]["settled"], "baseline": baseline, "pending": len(pending)}
    return {"ok": not problems, "problems": problems, "accepted": accepted, "summary": summary}


def check(now: dt.datetime, *, db=None, state_dir: Path | str | None = None, save_state: bool = True) -> list[str]:
    """Mục "lưới an toàn" của máy canh. Tóm tắt (số đếm) ra stderr cho journal; danh sách câu báo trả về cho máy canh gửi đi."""
    try:
        report = run(now, db=db, state_dir=state_dir if state_dir is not None else state_dir_from_env(), save_state=save_state)
    except ApiError as exc:  # máy canh chỉ ghi tên lỗi vào câu báo; mã lỗi của adapter để ở journal
        print(f"lưới an toàn: lỗi DB {exc.code}", file=sys.stderr)
        raise
    print("lưới an toàn: " + json.dumps(report["summary"], ensure_ascii=False), file=sys.stderr)
    return report["problems"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--state-dir", type=Path, default=state_dir_from_env(), help="thư mục giữ mốc (máy canh: /var/lib/v7-watchdog)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="so và in ra, không ghi mốc")
    mode.add_argument("--accept", action="store_true", help="chấp nhận các mục chờ của kiểm 3, 4 rồi lấy mốc mới")
    parser.add_argument("--full", action="store_true", help="so get_ledger của mọi sổ, không chỉ phần của lượt này")
    parser.add_argument("--socket-dir", default=SOCKET_DIR)
    parser.add_argument("--database", default=DATABASE)
    parser.add_argument("--db-user", default=DB_USER)
    args = parser.parse_args(argv)
    if args.accept and args.state_dir is None:
        parser.error("--accept cần --state-dir")
    if args.state_dir is not None and getattr(os, "geteuid", lambda: -1)() == 0:
        parser.error("chạy bằng user v7app (sudo -u v7app …): file mốc và khóa của root làm máy canh không ghi được nữa")
    report = run(now_vn(), db=connect(args.socket_dir, args.database, args.db_user), state_dir=args.state_dir,
                 save_state=not args.dry_run, accept=args.accept, full=args.full)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
