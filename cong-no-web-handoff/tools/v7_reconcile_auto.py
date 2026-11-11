#!/usr/bin/env python3
"""Máy tự đối soát Sheet–web và tự sửa khi khớp (MAY-DOI-SOAT-01, specs/v7-may-doi-soat.md).

Chạy trên hao dưới user runner (timer v7-reconcile-auto, mỗi giờ từ 7 tới 22 giờ VN), cùng biến môi trường với runner giá:

    v7_reconcile_auto.py --source-dir /srv/v7/so-goc-20261020 [--fix]

Mỗi lượt: tải bản xlsx sổ gốc (chỉ đọc), làm sạch đúng như đối soát chính thức, đọc tổng từng khách trên web. Khách lệch thì tìm đúng
một tổ hợp việc đang chờ (phiếu thu, giá) đưa tổng web về tổng Sheet tới từng đồng, tổng và việc đều lấy từ cùng bản tải. Khách có
trên Sheet mà chưa có sổ web thì tạo sổ khi đủ điều kiện (MAY-TAO-SO-01). Không có --fix thì chỉ báo sẽ ghi gì. Kết quả ghi vào reconcile.json (mode 600, có tên khách và số tiền) để API hiện ở Việc cần làm; bản tải
và bản làm sạch xóa ngay sau lượt. Stdout chỉ có số đếm, không có tên khách hay số tiền.

Mỗi lượt cũng kiểm tab TONG có cộng đủ các tab khách không (KIEM-TONG-01), bằng đúng phép so của audit chuyển hẳn. Chỉ báo, không ghi.
"""

from __future__ import annotations

import argparse
import datetime as dt
import functools
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import sheet_sync_runner
import v7_cutover_audit as audit
import v7_export_clean as clean
import v7_load_real_copy as loader
import v7_price_snapshot as snapshots
import v7_reconcile_sheet as rec
import v7_run_trace as run_trace
import v7_sheet_export_xlsx as exporter
import v7_sheet_log as edit_log

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_reconcile_hints as hints  # dùng v7_price_queue của lớp web
import v7_sheet_fix as fix  # tools may use the web layer; never the reverse
from v7_api_sheet import customer_name_mapping, named_customer
from v7_api_validate import ApiError
from v7_inbox import AUTO_ACTOR
from v7_price_queue import book_rows, container_key, iso, targets
from v7_psql import PsqlDirect

ACTOR = "doi-soat-tu-dong"   # chỉ đọc; lệnh ghi dùng AUTO_ACTOR ("Máy (theo Sheet)")
# Hơn chừng này khách lệch thì có thể Sheet đang sửa hàng loạt hoặc bản tải có vấn đề: chỉ báo, không ghi.
MAX_DIFFERENT = 40
OUTPUT = "/var/lib/webdebit-sheet-sync/reconcile.json"
WORK = "/var/lib/webdebit-sheet-sync/reconcile-work"
# Tab ngoài danh sách mốc 20/10: có phát sinh trước tháng nạp V7 là bản sao, tab nháp đã xem lúc nạp; từ tháng này là khách mới.
OUTSIDE_FROM = "2026-10"
# MAY-TAO-SO-01: hơn chừng này tab mới một lượt thì có thể Sheet đang đổi tên hàng loạt: chỉ báo, không tạo sổ.
NEW_BOOKS_MAX = 5
DONE_REASONS = ("FIXED", "BOOK_CREATED")   # việc máy đã làm: ở lại danh sách tới hết ngày để chủ sổ soát


def now_vn() -> dt.datetime:
    return dt.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))


def failure_code(exc: Exception) -> str:
    """Mã lỗi không lộ dữ liệu: lỗi của loader và của đối soát đã là mã; còn lại chỉ tên loại lỗi."""
    return str(exc) if isinstance(exc, loader.LoadError | rec.InputError) else str(getattr(exc, "code", "") or type(exc).__name__)


def download(spreadsheet_id: str, credentials: str, output: Path) -> Path:
    token = sheet_sync_runner.exchange_token(sheet_sync_runner.load_credentials(credentials), scope=exporter.DRIVE_READONLY)
    exporter.export(spreadsheet_id, token, output)
    return output


def live_tong(xlsx: Path) -> dict[str, Any]:
    """Khối mới nhất (ngoài cùng bên phải) của tab TONG thật trong bản tải: tháng và số cuối tháng theo tên đã chuẩn hóa.

    `in_summary` của bộ đọc sổ gốc chỉ so với CSV đóng băng từ mốc 20/10, không thấy tab mới. Bố cục lạ thì trả rỗng; tên trùng hay ô
    không phải số thì số là None. Cả hai đều không có tab nào được nhận.
    """
    empty: dict[str, Any] = {"month": None, "rows": {}}
    for tab, data in loader.workbook_rows(xlsx):
        if loader.normalized(tab) != "TONG":
            continue
        rows = list(data)
        header = next(((number, cells) for number, cells in rows if any(loader.normalized(value) == "LOAI HANG" for value in cells.values())), None)
        if header is None:
            return empty
        heads = {col: loader.normalized(value) for col, value in header[1].items()}
        names = [col for col in heads if heads[col] == "TEN KHACH HANG" and heads.get(loader.col_name(loader.col_num(col) - 1)) == "LOAI HANG"]
        if not names:
            return empty
        name_col = max(names, key=loader.col_num)
        after = sorted((col for col in heads if loader.col_num(col) > loader.col_num(name_col)), key=loader.col_num)
        balance_col = next((col for col in after if heads[col] == "SO CON PHAI THU CUOI THANG"), None)
        title = next((match for col in after if (match := re.search(r"THANG (\d{1,2}) (20\d{2})", heads[col]))), None)
        if balance_col is None or title is None:
            return empty
        found: dict[str, int | None] = {}
        for number, cells in rows:
            key = loader.normalized(cells.get(name_col, ""))
            if number > header[0] and key:
                found[key] = None if key in found else loader.integer(cells.get(balance_col))
        return {"month": f"{title.group(2)}-{int(title.group(1)):02d}", "rows": found}
    return empty


def tong_agrees(book: dict, tong: dict[str, Any]) -> bool:
    """Tab có ở khối mới nhất của TONG và số cuối tháng đó trên TONG bằng số trên tab tới từng đồng."""
    expected = tong["rows"].get(loader.normalized(book["name"]))
    check = next((item for item in book["checks"] if str(item["debt_month"])[:7] == tong["month"]), None)
    return expected is not None and check is not None and check["source_cumulative_vnd"] == expected


def admit_new_tabs(books: list[dict], tong: dict[str, Any], known: set[str]) -> None:
    """Tab ngoài danh sách mốc 20/10 được so như mọi khách khi đã có sổ web, hoặc khi đủ điều kiện tạo sổ (MAY-TAO-SO-01). Sửa `books`
    tại chỗ. Mỗi tab kiểm riêng trước khi nhận, để một tab mới lỗi không làm hỏng cả lượt."""
    for book in books:
        if book["in_summary"]:
            continue
        name = rec.name(book["name"])
        others = set(book["reasons"]) - {"NOT_ON_TONG"}
        if name not in known and (others or not tong_agrees(book, tong)):
            continue
        book["in_summary"] = True
        del book["reasons"]["NOT_ON_TONG"]
        if others:
            continue   # đã có sổ mà tab đọc không được: thành khách bị giữ như mọi khách
        try:
            loader.validate_books([book], book["anchor"])
        except loader.LoadError as exc:
            book["reasons"][str(exc)] += 1
            if name not in known:
                book["in_summary"] = False


def outside_tabs(books: list[dict], tong: dict[str, Any]) -> list[dict]:
    """Tab khách còn nợ, có phát sinh từ tháng nạp V7 mà máy chưa nhận được: tổng Sheet lẫn web đều chưa tính nên phép so từng khách
    không thấy (đo trên `hao` 4/11/2026: một tab mới còn nợ hơn 300 triệu). Chỉ báo kèm lý do, không tự gắn vào sổ nào."""
    rows = []
    for book in books:
        active = [str(check["debt_month"])[:7] for check in book["checks"] if check.get("source_charge_vnd") or check.get("source_receipt_vnd")]
        if not book["in_summary"] and book["anchor"] and active and max(active) >= OUTSIDE_FROM:
            on_tong = loader.normalized(book["name"]) in tong["rows"]
            reason = "NOT_ON_TONG" if not on_tong else "TAB_UNREADABLE" if set(book["reasons"]) - {"NOT_ON_TONG"} else "TONG_DIFFERS"
            rows.append({"customer": rec.name(book["name"]), "sheet_total_vnd": str(book["anchor"]), "last_month": max(active), "reason": reason})
    return rows


def read_sheet(xlsx: Path, source_dir: Path, out: Path, known: set[str]) -> tuple[dict, list[dict], list[dict], list[dict], str]:
    """Đúng các bước của `v7_export_clean --hold-out` rồi `v7_reconcile_sheet`; khách bị giữ không có tổng Sheet."""
    books, digests = clean.build_books(source_dir, xlsx, ())
    tong = live_tong(xlsx)
    admit_new_tabs(books, tong, known)
    held = [book for book in books if book["in_summary"] and book["reasons"]]
    clean.export([book for book in books if book not in held], digests, out, xlsx, ())
    sheet, _ = rec.read_sheet(out)
    return (sheet, [{"name": rec.name(book["name"]), "reasons": dict(book["reasons"]), "chain_break": hints.chain_break(book["checks"])}
                    for book in held], outside_tabs(books, tong),
            [book for book in books if book["in_summary"] and not book["reasons"]], digests["source-google-export.xlsx"])


def read_web(db, rows: list[dict], on_row=lambda _done: None) -> tuple[dict, dict, dict]:
    """(tổng từng sổ, id theo tên, chuyến mọi sổ theo container để kiểm tab mới có đụng sổ khác không)."""
    web, ids, seen = {}, {}, {}
    for done, row in enumerate(rows):
        on_row(done)
        key = rec.name(row["name"])
        if key in web:
            raise rec.InputError("duplicate web customer")
        ledger = db.run("get_ledger", {"customer_id": row["id"]}, ACTOR)
        web[key] = rec.ledger(ledger)
        ids[key] = row["id"]
        for target in targets(ledger):
            seen.setdefault(target["container"], []).append((row["id"], target["date"], target["month"]))
    return web, ids, seen


def overlap_ids(book: dict, seen: dict) -> list[int]:
    """Sổ khác đã có chuyến của tab này: cùng container, cách không quá 3 ngày, dòng không ngày thì cùng tháng. Khách mới thật thì không
    có; có là dấu hiệu đổi tên hay tách sổ."""
    found = set()
    for row in book["legacy"]:
        container = container_key(row["display"].get("container")) if row["kind"] == "trip" else ""
        if not container:
            continue
        day, month = iso(row["display"].get("date")), str(row["debt_month"])[:7]
        for customer_id, other_day, other_month in seen.get(container, ()):
            if abs((day - other_day).days) <= 3 if day and other_day else month == other_month:
                found.add(customer_id)
    return sorted(found)


def create_new_books(db, rows: list[dict], books: dict[str, dict], seen: dict, digest: str, ids: dict, *, write: bool) -> None:
    """Khách có trên Sheet mà chưa có sổ web: tạo sổ theo đúng đường nạp mốc (MAY-TAO-SO-01). Cập nhật `rows` và `ids` tại chỗ."""
    for row in rows:
        book = books.get(row["customer"])
        if book is None:
            continue
        if len(rows) > NEW_BOOKS_MAX:
            row["reason"] = "TOO_MANY_NEW_BOOKS"
            continue
        others = overlap_ids(book, seen)
        if others:
            row.update(reason="BOOK_OVERLAP", overlap_ids=others)
            continue
        if not write:
            row["reason"] = "WOULD_CREATE_BOOK"
            continue
        try:
            created = db.run("create_book_from_sheet", {
                "book_name": row["customer"], "commodity_name": book.get("commodity"), "book_mode": book.get("transport_mode"),
                "openings": book["openings"], "legacy": book["legacy"], "month_checks": book["checks"],
                "control_total": book["anchor"], "report_sha256": digest}, AUTO_ACTOR)
        except ApiError as exc:
            print(f"V7 đối soát máy: lỗi {exc.code} khi tạo sổ", file=sys.stderr, flush=True)
            row.update(reason="WRITE_ERROR", error=exc.code)
            continue
        ids[row["customer"]] = created["customer_id"]
        total = int(db.run("get_ledger", {"customer_id": created["customer_id"]}, AUTO_ACTOR)["total_outstanding_vnd"])
        row.update(web_total_vnd=total, difference_vnd=total - row["sheet_total_vnd"])
        if total == row["sheet_total_vnd"]:
            row.update(status="KHOP", reason="BOOK_CREATED")
        else:
            print(f"V7 đối soát máy: sổ {created['customer_id']} tạo xong mà không khớp", file=sys.stderr, flush=True)
            row["reason"] = "VERIFY_FAILED"


def brief(group: dict[str, Any], chosen: list[dict[str, Any]]) -> dict[str, Any]:
    return {"kind": group["kind"], "month": group["month"], "count": len(group["rows"]), "delta_vnd": str(group["delta_vnd"]),
            "chosen": any(group is item for item in chosen)}


def settle(db, row: dict[str, Any], customer_id: int, customers: list[dict], prices: dict, receipts: dict, today: dt.date,
           *, write: bool, trace: run_trace.RunTrace | None = None) -> None:
    """Kết luận cho một khách lệch; `write` thì ghi đúng tổ hợp đã chọn rồi đọc lại sổ để kiểm. Cập nhật `row` tại chỗ."""
    trace = trace or run_trace.RunTrace(None)
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
    if ahead:
        attach_ahead_check(row, ledger, prices, customers, today)
    target = sheet + ahead
    if total == target:
        row.update(reason="WEB_AHEAD", groups=[brief(group, []) for group in groups])
        return
    verdict, chosen = fix.choose(groups, target - total)
    row["groups"] = [brief(group, chosen) for group in groups]
    trace.customer(customer_id, decided=True, before_vnd=total, target_vnd=target)
    if verdict != "FIX":
        row["reason"] = "SHEET_SHUFFLED" if shuffled else verdict
        attach_hints(row, ledger, prices, receipts, customers, target - total)
        return
    if not write:
        row["reason"] = "WOULD_FIX"
        return
    trace.stage("ghi")
    trace.customer(customer_id, writing=True)
    try:
        row["written"] = fix.apply_fix(db, customer_id, ledger, chosen, prices["sha256"], today, actor=AUTO_ACTOR)
    except ApiError as exc:
        print(f"V7 đối soát máy: sổ {customer_id} lỗi {exc.code} khi ghi", file=sys.stderr, flush=True)
        row.update(reason="WRITE_ERROR", error=exc.code)
        return
    finally:
        row["web_total_vnd"] = int(db.run("get_ledger", {"customer_id": customer_id}, AUTO_ACTOR)["total_outstanding_vnd"])
        row["difference_vnd"] = row["web_total_vnd"] - sheet
        trace.customer(customer_id, done=True, after_vnd=row["web_total_vnd"])
    if row["web_total_vnd"] != target:
        print(f"V7 đối soát máy: sổ {customer_id} ghi xong mà không khớp", file=sys.stderr, flush=True)
        row["reason"] = "VERIFY_FAILED"
    else:
        row.update(reason="FIXED", status="KHOP" if target == sheet else "LECH_TONG")


def attach_hints(row: dict[str, Any], ledger: dict, prices: dict, receipts: dict, customers: list[dict], needed: int) -> None:
    """Máy đoán chỗ gây lệch để người sửa (CHAN-DOAN-LECH-01). Chỉ để giải thích: lỗi ở đây không đổi kết luận hay làm hỏng lượt."""
    try:
        book = ledger.get("customer_id")
        found, explained = hints.for_book(ledger, book_rows(prices, book, customers), needed, book_rows(receipts, book, customers))
    except Exception as exc:  # noqa: BLE001
        print(f"V7 đối soát máy: không đoán được lý do lệch ({type(exc).__name__})", file=sys.stderr, flush=True)
        return
    if found:   # chuyến đi trước cần xem (nếu có) đứng sau các chỗ gây lệch
        row.update(hints=[*(hints.money_fields(hint) for hint in found), *(row.get("hints") or [])], hints_explain=explained)


def attach_ahead_check(row: dict[str, Any], ledger: dict, prices: dict, customers: list[dict], today: dt.date) -> None:
    """Chuyến web đi trước để lâu hoặc Sheet ghi ở tab sổ khác: thêm câu để người xem (MAY-DOI-SOAT-01, 10/11/2026). Không đổi phép
    tính hay kết luận; lỗi ở đây không làm hỏng lượt."""
    try:
        found = fix.ahead_to_check(prices, ledger, customers, today)
    except Exception as exc:  # noqa: BLE001
        print(f"V7 đối soát máy: không xét được chuyến đi trước ({type(exc).__name__})", file=sys.stderr, flush=True)
        return
    if found:
        row["hints"] = [hints.money_fields(hint) for hint in found]


def money_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Tiền ra file là chuỗi số nguyên chính xác, NULL giữ null (cùng hợp đồng với get_ledger)."""
    return {key: (str(value) if key.endswith("_vnd") and value is not None else value) for key, value in row.items()}


def check_tong(xlsx: Path, results: list[dict[str, Any]], ids: dict[str, int], rows: list[dict],
               sheet_snapshots: Callable[[], tuple[dict, dict]]) -> dict[str, Any]:
    """Tab TONG có cộng đủ các tab khách không (KIEM-TONG-01): khối mới nhất của TONG so với từng sổ web bằng đúng phép so của audit
    chuyển hẳn (`v7_cutover_audit.read_tong`, `audit_tong`). Chỉ báo: không đổi kết luận, không làm máy ghi; lỗi ở đây không làm hỏng lượt."""
    try:
        tong = audit.read_tong(xlsx)
        if not tong["month"]:
            return audit.audit_tong(tong, [], {}, {})   # không có tab TONG hoặc bố cục lạ: bỏ qua, khỏi dựng bản chụp
        prices, receipts = sheet_snapshots()
        mapping = customer_name_mapping()
        known = {row["id"] for row in rows}
        customers = [named_customer(row, mapping) for row in rows]
        customers += [{"id": book, "name": name} for name, book in ids.items() if book not in known]   # sổ máy vừa tạo ở lượt này
        names = {customer["id"]: customer["name"] for customer in customers}
        # Phần web đi trước giải thích trọn chỗ lệch: như audit đọc reconcile.json, thêm khách máy vừa sửa ở lượt này mà còn phần đi trước.
        ahead = {ids[row["customer"]]: row["web_ahead_vnd"] for row in results if row["customer"] in ids and row["status"] == "LECH_TONG"
                 and row.get("web_ahead_vnd") and row.get("difference_vnd") == row["web_ahead_vnd"]}
        books = []
        for row in results:
            book = ids.get(row["customer"])
            if book is None or row.get("web_total_vnd") is None:
                continue   # chưa có sổ web, hoặc chưa biết tổng web: không so
            charge, paid = audit.sheet_months(book_rows(prices, book, customers), book_rows(receipts, book, customers))
            books.append({"id": book, "name": names[book], "web_total_vnd": row["web_total_vnd"], "sheet_charge": charge, "sheet_paid": paid})
        found = audit.audit_tong(tong, books, ahead, {})
    except Exception as exc:  # noqa: BLE001
        code = failure_code(exc)
        print(f"V7 đối soát máy: không kiểm được tab TONG ({code})", file=sys.stderr, flush=True)
        return {"month": None, "skipped": "ERROR", "error": code}
    return {key: [money_fields(item) for item in value] if isinstance(value, list) else value for key, value in money_fields(found).items()}


def tong_counts(tong: dict[str, Any]) -> dict[str, Any]:
    """Số đếm của phép kiểm TONG cho sổ theo dõi và stdout: không tên khách, không số tiền."""
    if not tong.get("month"):
        return {key: tong[key] for key in ("skipped", "error") if key in tong}
    return {"month": tong["month"], "matched": tong["matched"], "blank": len(tong["blank_on_tong"]), "differs": len(tong["differs"]),
            "unknown_names": len(tong["unknown_names"])}


def note_sheet_edits(args: argparse.Namespace, results: list[dict[str, Any]], downloaded_at: dt.datetime) -> dict[str, Any]:
    """Khách chưa khớp mà tab vừa sửa: đánh dấu để Việc cần làm không báo "cần xem" (SHEET-LOG-01). Đọc cuối lượt để thấy cả lần sửa lúc
    lượt đang chạy. Chỉ để giải thích, không đổi tiền hay kết luận, nên đọc log lỗi không làm hỏng lượt."""
    if not args.edit_log_id or not args.credentials:
        return {"status": "OFF"}
    try:
        token = sheet_sync_runner.exchange_token(sheet_sync_runner.load_credentials(args.credentials))
        events = sheet_sync_runner.with_timeout_retry(lambda: edit_log.read_tail(args.edit_log_id, token))
    except Exception as exc:  # noqa: BLE001
        code = str(getattr(exc, "code", "") or type(exc).__name__)
        print(f"V7 đối soát máy: không đọc được log sửa Sheet ({code})", file=sys.stderr, flush=True)
        return {"status": "UNAVAILABLE", "reason": code}
    state, last_edits = edit_log.summarize(events, now_vn())
    edit_log.annotate(results, last_edits, downloaded_at)
    return state


def run(args: argparse.Namespace, trace: run_trace.RunTrace | None = None) -> dict[str, Any]:
    trace = trace or run_trace.RunTrace(None)
    downloaded_at = now_vn()
    today = downloaded_at.date()
    work_root = Path(args.work_dir)
    work_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=work_root, prefix="lan-") as folder:
        work = Path(folder)
        trace.stage("tai")
        xlsx = args.xlsx or download(args.spreadsheet_id, args.credentials, work / "sheet.xlsx")
        db = PsqlDirect(args.socket_dir, args.database, args.db_user)
        rows = db.run("list_customers", {}, ACTOR).get("customers", [])
        trace.stage("sach")
        sheet, held, outside, books, digest = read_sheet(Path(xlsx), args.source_dir, work / "sach", {rec.name(row["name"]) for row in rows})
        trace.mark(books=len(rows))
        trace.stage("doc", total=len(rows))
        web, ids, seen = read_web(db, rows, trace.tick)
        trace.stage("so", total=len(rows))
        results, _, _ = rec.reconcile(sheet, web, compare_months=False)
        by_month, _, _ = rec.reconcile(sheet, web, compare_months=True, can_du=True)
        months_differ = [row["customer"] for row in by_month if row["status"] == "CHI_LECH_THANG"]
        different = [row for row in results if row["status"] == "LECH_TONG"]
        too_many = len(different) > MAX_DIFFERENT
        trace.mark(books=len(results), counts={"KHOP": sum(row["status"] == "KHOP" for row in results)})
        sheet_snapshots = functools.cache(lambda: snapshots.build_all(Path(xlsx)))   # dựng một lần cho cả lượt: tìm cách sửa và kiểm TONG
        if different:
            trace.stage("chot")
            trace.mark(too_many=too_many, different=len(different))
        if different and not too_many:
            trace.stage("tim", total=len(different))
            prices, receipts = sheet_snapshots()
            mapping = customer_name_mapping()
            customers = [named_customer(row, mapping) for row in rows]
            for row in different:
                if row["customer"] in ids:
                    trace.customer(ids[row["customer"]], difference_vnd=row.get("difference_vnd"))
            for index, row in enumerate(different, 1):
                try:
                    settle(db, row, ids[row["customer"]], customers, prices, receipts, today, write=args.fix, trace=trace)
                    if row.get("reason") not in (None, "KHOP"):   # báo ngay, không đợi cuối lượt; cuối lượt vẫn ghi lại bản đầy đủ
                        trace.customer(ids[row["customer"]], reason=row["reason"], difference_vnd=row.get("difference_vnd"))
                    trace.stage("tim", total=len(different), done=index)
                except Exception as exc:  # noqa: BLE001  một sổ lỗi không chặn sổ khác; lượt sau tính lại
                    code = failure_code(exc)
                    print(f"V7 đối soát máy: sổ {ids[row['customer']]} lỗi {code} khi kiểm", file=sys.stderr, flush=True)
                    row.update(reason="CHECK_ERROR", error=code)
        if not too_many:
            create_new_books(db, [row for row in results if row["status"] == "CHI_CO_SHEET"], {rec.name(book["name"]): book for book in books},
                             seen, digest, ids, write=args.fix)
        # Sau khi máy sửa và tạo sổ, để tổng web là tổng lúc lưu. Hơn 40 khách lệch thì phần đi trước chưa tính, số so không có nghĩa.
        tong = {"month": None, "skipped": "TOO_MANY_DIFFERENT"} if too_many else check_tong(Path(xlsx), results, ids, rows, sheet_snapshots)
    trace.stage("luu")
    held_names = {item["name"]: item for item in held}
    for row in results:
        row["customer_id"] = ids.get(row["customer"])
        if row["status"] == "LECH_TONG" and too_many:
            row["reason"] = "TOO_MANY_DIFFERENT"
        elif row["customer"] in held_names:
            item = held_names[row["customer"]]
            row.update(reason="HELD", held_reasons=item["reasons"])
            if item["chain_break"]:
                row["hints"] = [hints.money_fields(item["chain_break"])]
        elif row["status"] != "LECH_TONG":
            row.setdefault("reason", row["status"])
    edit_state = note_sheet_edits(args, results, downloaded_at)
    for row in results:
        if row["status"] != "KHOP" or row.get("reason") in DONE_REASONS:
            trace.customer(row.get("customer_id"), done=row.get("reason") in DONE_REASONS, reason=row.get("reason") or row["status"], status=row["status"], difference_vnd=row.get("difference_vnd"))
    matched = [row for row in results if row["status"] == "KHOP"]
    checked_at = now_vn().isoformat(timespec="seconds")
    for row in results:
        if row.get("reason") in DONE_REASONS:
            row["fixed_at"] = checked_at
    listed = [money_fields(row) for row in results if row["status"] != "KHOP" or row.get("reason") in DONE_REASONS]
    named = {row["customer"] for row in listed}
    return {
        "version": 1, "checked_at": checked_at, "mode": "fix" if args.fix else "report",
        "counts": dict(Counter(row["status"] for row in results)), "total": len(results),
        "matched_web_vnd": str(sum(row["web_total_vnd"] for row in matched)),
        "all_web_vnd": str(sum(row["web_total_vnd"] or 0 for row in results)),
        "matched": {str(row["customer_id"]): str(row["web_total_vnd"]) for row in matched if row["customer_id"]},
        "customers": listed + [row for row in fixed_earlier_today(args.output, checked_at[:10]) if row["customer"] not in named],
        "months_differ": months_differ, "outside_tabs": outside, "edit_log": edit_state, "tong": tong,
    }


def fixed_earlier_today(output: Path, day: str) -> list[dict[str, Any]]:
    """Khách máy đã sửa ở các lượt trước trong ngày: giữ trên danh sách để chủ sổ soát đủ việc của cả ngày, không chỉ lượt cuối."""
    try:
        previous = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [row for row in previous.get("customers", []) if row.get("reason") in DONE_REASONS] if str(previous.get("checked_at"))[:10] == day else []


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
    today = [row for row in result["customers"] if row.get("fixed_at") == result["checked_at"]]
    line["fixed"] = sum(row["reason"] == "FIXED" for row in today)
    line["created"] = sum(row["reason"] == "BOOK_CREATED" for row in today)
    line["edit_log"] = result["edit_log"]["status"]
    line["editing"] = sum(bool(row.get("sheet_editing")) for row in result["customers"])
    line["tong"] = tong_counts(result["tong"])
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
    parser.add_argument("--edit-log-id", default=os.getenv("WEBDEBIT_EDIT_LOG_ID"), help="file log sửa Sheet (SHEET-LOG-01); không có thì bỏ qua")
    parser.add_argument("--socket-dir", default="/var/run/postgresql")
    parser.add_argument("--database", default="webdebit_v7")
    parser.add_argument("--db-user", default="v7_app")
    parser.add_argument("--fix", action="store_true", help="ghi tổ hợp đã chọn; không có thì chỉ báo")
    args = parser.parse_args(argv)
    if not args.xlsx and (not args.spreadsheet_id or not args.credentials):
        parser.error("cần --xlsx, hoặc --spreadsheet-id và --credentials (biến môi trường của runner)")
    started = time.monotonic()
    trace = run_trace.RunTrace(args.output.with_name("reconcile-run.json"), "fix" if args.fix else "report")
    try:
        result = run(args, trace)
    except Exception as exc:  # noqa: BLE001  (lỗi thành mã, không in dữ liệu)
        reason = failure_code(exc)
        record_failure(args.output, reason)
        trace.finish(ok=False, reason=reason)
        print(json.dumps({"ok": False, "reason": reason}))
        return 2
    snapshots.write(result, args.output)
    append_log(args.output, result)
    today = [row for row in result["customers"] if row.get("fixed_at") == result["checked_at"]]
    trace.finish(ok=True, counts=result["counts"], books=result["total"], fixed=sum(row["reason"] == "FIXED" for row in today), created=sum(row["reason"] == "BOOK_CREATED" for row in today))
    reasons = Counter(row["reason"] for row in result["customers"])
    print(json.dumps({"ok": True, "mode": result["mode"], "counts": result["counts"], "reasons": reasons,
                      "months_differ": len(result["months_differ"]), "edit_log": result["edit_log"]["status"],
                      "tong": tong_counts(result["tong"]), "seconds": round(time.monotonic() - started)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
