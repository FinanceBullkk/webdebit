#!/usr/bin/env python3
"""Máy tự đối soát Sheet–web và tự sửa khi khớp (MAY-DOI-SOAT-01, specs/v7-may-doi-soat.md).

Chạy trên hao dưới user runner (timer v7-reconcile-auto, mỗi giờ từ 7 tới 22 giờ VN), cùng biến môi trường với runner giá:

    v7_reconcile_auto.py --source-dir /srv/v7/so-goc-20261020 [--fix]

Mỗi lượt: tải bản xlsx sổ gốc (chỉ đọc), làm sạch đúng như đối soát chính thức, đọc tổng từng khách trên web. Khách lệch thì tìm đúng
một tổ hợp việc đang chờ (phiếu thu, giá) đưa tổng web về tổng Sheet tới từng đồng, tổng và việc đều lấy từ cùng bản tải. Không có
--fix thì chỉ báo sẽ ghi gì. Kết quả ghi vào reconcile.json (mode 600, có tên khách và số tiền) để API hiện ở Việc cần làm; bản tải
và bản làm sạch xóa ngay sau lượt. Stdout chỉ có số đếm, không có tên khách hay số tiền.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import sheet_sync_runner
import v7_export_clean as clean
import v7_load_real_copy as loader
import v7_price_snapshot as snapshots
import v7_reconcile_sheet as rec
import v7_sheet_export_xlsx as exporter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_sheet_fix as fix  # tools may use the web layer; never the reverse
from v7_api_sheet import customer_name_mapping, named_customer
from v7_api_validate import ApiError
from v7_inbox import AUTO_ACTOR
from v7_psql import PsqlDirect

ACTOR = "doi-soat-tu-dong"   # chỉ đọc; lệnh ghi dùng AUTO_ACTOR ("Máy (theo Sheet)")
# Hơn chừng này khách lệch thì có thể Sheet đang sửa hàng loạt hoặc bản tải có vấn đề: chỉ báo, không ghi.
MAX_DIFFERENT = 40
OUTPUT = "/var/lib/webdebit-sheet-sync/reconcile.json"
WORK = "/var/lib/webdebit-sheet-sync/reconcile-work"


def now_vn() -> dt.datetime:
    return dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))


def failure_code(exc: Exception) -> str:
    """Mã lỗi không lộ dữ liệu: lỗi của loader và của đối soát đã là mã; còn lại chỉ tên loại lỗi."""
    return str(exc) if isinstance(exc, loader.LoadError | rec.InputError) else str(getattr(exc, "code", "") or type(exc).__name__)


def download(spreadsheet_id: str, credentials: str, output: Path) -> Path:
    token = sheet_sync_runner.exchange_token(sheet_sync_runner.load_credentials(credentials), scope=exporter.DRIVE_READONLY)
    exporter.export(spreadsheet_id, token, output)
    return output


def read_sheet(xlsx: Path, source_dir: Path, out: Path) -> tuple[dict, list[dict]]:
    """Đúng các bước của `v7_export_clean --hold-out` rồi `v7_reconcile_sheet`; khách bị giữ không có tổng Sheet."""
    books, digests = clean.build_books(source_dir, xlsx, ())
    held = [book for book in books if book["in_summary"] and book["reasons"]]
    clean.export([book for book in books if book not in held], digests, out, xlsx, ())
    sheet, _ = rec.read_sheet(out)
    return sheet, [{"name": rec.name(book["name"]), "reasons": dict(book["reasons"])} for book in held]


def read_web(db) -> tuple[list[dict], dict, dict]:
    rows = db.run("list_customers", {}, ACTOR).get("customers", [])
    web, ids = {}, {}
    for row in rows:
        key = rec.name(row["name"])
        if key in web:
            raise rec.InputError("duplicate web customer")
        web[key] = rec.ledger(db.run("get_ledger", {"customer_id": row["id"]}, ACTOR))
        ids[key] = row["id"]
    return rows, web, ids


def brief(group: dict[str, Any], chosen: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": group["kind"], "month": group["month"], "count": len(group["rows"]), "delta_vnd": str(group["delta_vnd"]),
            "chosen": any(group is item for item in chosen)}


def settle(db, row: dict[str, Any], customer_id: int, customers: list[dict], prices: dict, receipts: dict, today: dt.date,
           *, write: bool) -> None:
    """Kết luận cho một khách lệch; `write` thì ghi đúng tổ hợp đã chọn rồi đọc lại sổ để kiểm. Cập nhật `row` tại chỗ."""
    ledger = db.run("get_ledger", {"customer_id": customer_id}, ACTOR)
    sheet, total = row["sheet_total_vnd"], int(ledger["total_outstanding_vnd"])
    row["web_total_vnd"] = total
    row["difference_vnd"] = total - sheet
    if total == sheet:   # ai đó vừa sửa sau lúc đọc
        row.update(status="KHOP", reason="KHOP")
        return
    groups, ahead, shuffled = fix.plan(prices, receipts, ledger, customers, today)
    row["web_ahead_vnd"] = ahead
    if shuffled:
        row["shuffled_months"] = shuffled
    target = sheet + ahead
    if total == target:
        row.update(reason="WEB_AHEAD", groups=[brief(group, []) for group in groups])
        return
    verdict, chosen = fix.choose(groups, target - total)
    row["groups"] = [brief(group, chosen) for group in groups]
    if verdict != "FIX":
        row["reason"] = "SHEET_SHUFFLED" if shuffled else verdict
        return
    if not write:
        row["reason"] = "WOULD_FIX"
        return
    try:
        row["written"] = fix.apply_fix(db, customer_id, ledger, chosen, prices["sha256"], today)
    except ApiError as exc:
        print(f"V7 đối soát máy: sổ {customer_id} lỗi {exc.code} khi ghi", file=sys.stderr, flush=True)
        row.update(reason="WRITE_ERROR", error=exc.code)
        return
    finally:
        row["web_total_vnd"] = int(db.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["total_outstanding_vnd"])
        row["difference_vnd"] = row["web_total_vnd"] - sheet
    if row["web_total_vnd"] != target:
        print(f"V7 đối soát máy: sổ {customer_id} ghi xong mà không khớp", file=sys.stderr, flush=True)
        row["reason"] = "VERIFY_FAILED"
    else:
        row.update(reason="FIXED", status="KHOP" if target == sheet else "LECH_TONG")


def money_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Tiền ra file là chuỗi số nguyên chính xác, NULL giữ null (cùng hợp đồng với get_ledger)."""
    return {key: (str(value) if key.endswith("_vnd") and value is not None else value) for key, value in row.items()}


def run(args: argparse.Namespace) -> dict[str, Any]:
    today = now_vn().date()
    work_root = Path(args.work_dir)
    work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=work_root, prefix="lan-") as folder:
        work = Path(folder)
        xlsx = args.xlsx or download(args.spreadsheet_id, args.credentials, work / "sheet.xlsx")
        sheet, held = read_sheet(Path(xlsx), args.source_dir, work / "sach")
        db = PsqlDirect(args.socket_dir, args.database, args.db_user)
        rows, web, ids = read_web(db)
        results, _, _ = rec.reconcile(sheet, web, compare_months=False)
        by_month, _, _ = rec.reconcile(sheet, web, compare_months=True, can_du=True)
        months_differ = [row["customer"] for row in by_month if row["status"] == "CHI_LECH_THANG"]
        different = [row for row in results if row["status"] == "LECH_TONG"]
        too_many = len(different) > MAX_DIFFERENT
        if different and not too_many:
            prices, receipts = snapshots.build_all(Path(xlsx))
            mapping = customer_name_mapping()
            customers = [named_customer(row, mapping) for row in rows]
            for row in different:
                try:
                    settle(db, row, ids[row["customer"]], customers, prices, receipts, today, write=args.fix)
                except Exception as exc:  # noqa: BLE001  một sổ lỗi không chặn sổ khác; lượt sau tính lại
                    code = failure_code(exc)
                    print(f"V7 đối soát máy: sổ {ids[row['customer']]} lỗi {code} khi kiểm", file=sys.stderr, flush=True)
                    row.update(reason="CHECK_ERROR", error=code)
    held_names = {item["name"]: item["reasons"] for item in held}
    for row in results:
        row["customer_id"] = ids.get(row["customer"])
        if row["status"] == "LECH_TONG" and too_many:
            row["reason"] = "TOO_MANY_DIFFERENT"
        elif row["customer"] in held_names:
            row.update(reason="HELD", held_reasons=held_names[row["customer"]])
        elif row["status"] != "LECH_TONG":
            row.setdefault("reason", row["status"])
    matched = [row for row in results if row["status"] == "KHOP"]
    checked_at = now_vn().isoformat(timespec="seconds")
    for row in results:
        if row.get("reason") == "FIXED":
            row["fixed_at"] = checked_at
    listed = [money_fields(row) for row in results if row["status"] != "KHOP" or row.get("reason") == "FIXED"]
    named = {row["customer"] for row in listed}
    return {
        "version": 1, "checked_at": checked_at, "mode": "fix" if args.fix else "report",
        "counts": dict(Counter(row["status"] for row in results)), "total": len(results),
        "matched_web_vnd": str(sum(row["web_total_vnd"] for row in matched)),
        "all_web_vnd": str(sum(row["web_total_vnd"] or 0 for row in results)),
        "matched": {str(row["customer_id"]): str(row["web_total_vnd"]) for row in matched if row["customer_id"]},
        "customers": listed + [row for row in fixed_earlier_today(args.output, checked_at[:10]) if row["customer"] not in named],
        "months_differ": months_differ,
    }


def fixed_earlier_today(output: Path, day: str) -> list[dict[str, Any]]:
    """Khách máy đã sửa ở các lượt trước trong ngày: giữ trên danh sách để chủ sổ soát đủ việc của cả ngày, không chỉ lượt cuối."""
    try:
        previous = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in previous.get("customers", []) if row.get("reason") == "FIXED"] if str(previous.get("checked_at"))[:10] == day else []


def record_failure(output: Path, reason: str) -> None:
    """Giữ kết quả lần đạt gần nhất, thêm lỗi của lần này để API báo."""
    try:
        data = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {"version": 1}
    data["last_error"] = {"at": now_vn().isoformat(timespec="seconds"), "reason": reason}
    snapshots.write(data, output)


def append_log(output: Path, result: dict[str, Any]) -> None:
    """Sổ theo dõi: mỗi lượt một dòng, chỉ số đếm và tổng tiền, không có tên khách."""
    line = {key: result[key] for key in ("checked_at", "mode", "counts", "total", "matched_web_vnd", "all_web_vnd")}
    line["fixed"] = sum(row.get("fixed_at") == result["checked_at"] for row in result["customers"])
    descriptor = os.open(output.with_name("reconcile-log.jsonl"), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(line, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-dir", type=Path, required=True, help="thư mục CSV của mốc sổ gốc (như v7_export_clean)")
    parser.add_argument("--output", type=Path, default=Path(os.getenv("WEBDEBIT_RECONCILE_PATH") or OUTPUT))
    parser.add_argument("--work-dir", default=WORK, help="chỗ để bản tải trong lúc chạy; xóa ngay sau lượt")
    parser.add_argument("--xlsx", type=Path, help="dùng bản tải có sẵn thay vì tải Sheet")
    parser.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--database", default="webdebit_v7")
    parser.add_argument("--db-user", default="v7_app")
    parser.add_argument("--fix", action="store_true", help="ghi tổ hợp đã chọn; không có thì chỉ báo")
    args = parser.parse_args(argv)
    if not args.xlsx and (not args.spreadsheet_id or not args.credentials):
        parser.error("cần --xlsx, hoặc --spreadsheet-id và --credentials (biến môi trường của runner)")
    started = time.monotonic()
    try:
        result = run(args)
    except Exception as exc:  # noqa: BLE001  (lỗi thành mã, không in dữ liệu)
        reason = failure_code(exc)
        record_failure(args.output, reason)
        print(json.dumps({"ok": False, "reason": reason}))
        return 2
    snapshots.write(result, args.output)
    append_log(args.output, result)
    reasons = Counter(row["reason"] for row in result["customers"])
    print(json.dumps({"ok": True, "mode": result["mode"], "counts": result["counts"], "reasons": reasons,
                      "months_differ": len(result["months_differ"]), "seconds": round(time.monotonic() - started)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
