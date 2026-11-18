#!/usr/bin/env python3
"""Audit chỉ đọc trước khi chuyển hẳn khỏi Sheet sổ nợ (specs/v7-cutover-audit.md, docs/chuyen-han-checklist.md).

Không ghi gì. Phía web lấy bằng GET qua API (hoặc thư mục JSON đã tải), phía Sheet lấy từ một bản tải xlsx (hoặc bản chụp của runner giá):

    v7_cutover_audit.py --api https://<serve> --serve-host <serve> --xlsx so-goc.xlsx --reconcile reconcile.json \
        --since 2026-11-01 --until 2026-11-30 --out <thư mục mới ngoài repo>
    v7_cutover_audit.py --web-dir <thư mục JSON> --prices prices.json --receipts receipts.json [--tong tong.json] --out <...>

Thư mục JSON: customers.json, ledgers/<id>.json (đúng thân GET /api/v7/ledger), activity/<yyyy-mm-dd>.json (GET /api/v7/activity).

Bốn phép kiểm:
  dòng     từng dòng chuyến Sheet với sổ web, phát sinh từng tháng, tổng thu từng sổ. Lời giải thích chỉ được nhận khi khớp tới từng đồng;
           không khớp thì là CHƯA GIẢI THÍCH, không có "gần đúng".
  TONG     khối mới nhất của tab TONG với sổ web: TONG cuối tháng = web hôm nay − web đi trước − phát sinh các tháng sau trên Sheet
           + thu ghi ở khối các tháng sau. Sổ còn số dư mà TONG để trống thì nêu tên.
  nhật ký  lệnh máy đã ghi (phiếu bị hủy, dòng điều chỉnh bị xóa, giá bị đè rồi quay lại) và thao tác nào đã có người thật làm.
  sổ       tháng cũ đang mở, chuyến chưa giá, chuyến chờ kiểm, cấn trừ hai sổ, việc treo.

--out nhận báo cáo có tên khách và số tiền (bao-cao.txt, chi-tiet.json): thư mục mới, ngoài mọi repo. Stdout chỉ có số đếm.
Mã thoát: 0 không còn mục tiền nào phải có người xem; 1 còn; 2 lỗi đầu vào.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from urllib.request import ProxyHandler, build_opener

import v7_reconcile_sheet as rec

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import v7_price_queue as pq  # tools may use the web layer; never the reverse

MACHINE = "may-theo-sheet"   # AUTO_ACTOR của web/v7_inbox.py; test giữ hai chỗ khớp nhau
FLAG_CARRY, FLAG_SPREAD, FLAG_ROUNDED = "YEAR_END_CARRY_ADJUSTED", "TOTAL_SPREAD_OVER_TRIPS", "ROUNDED_VND"
UNEXPLAINED = "CHUA_GIAI_THICH"
# Thao tác người dùng → loại lệnh trong sokhach.event. Test đối chiếu với tools/v7_backend_functions.sql để danh sách không cũ đi.
OPERATIONS = {
    "Dán chuyến": ("paste",), "Sửa thông tin chuyến": ("trip_edit",), "Xóa chuyến": ("trip_delete",), "Sửa giá chuyến": ("price_edit",),
    "Điều chỉnh theo chuyến": ("adjust_trip",), "Điều chỉnh cả tháng": ("adjust_month",), "Xóa dòng điều chỉnh": ("adjust_month_delete",),
    "Ghi phiếu thu": ("receipt",), "Sửa ngày, hình thức phiếu": ("receipt_edit",), "Hủy phiếu": ("void",), "Mở, khóa tháng": ("month_lock",),
    "Kết luận chuyến chờ kiểm": ("trip_review",), "Phụ phí": ("add_trip_fees", "replace_trip_fee", "void_trip_fee", "set_trip_fee_type", "rewrite_trip_fees"),
    "Bảng giá": ("price_table_edit", "price_table_apply"), "Sửa, xóa dòng sổ gốc": ("legacy_edit", "legacy_delete"),
    "Ảnh chứng từ": ("receipt_image", "receipt_image_remove"), "Thuộc tính sổ": ("customer_attr", "set_book_fee_columns"),
    "Quyết lệch chữ Sheet–web": ("sheet_conflict_resolved",),
}
SYSTEM_KINDS = frozenset({"import", "reallocation", "fee_migration"})   # hệ thống tự ghi, không phải thao tác của người
QUEUES = (("sheet_sync", ("new_count", "conflict_count", "waiting_count", "removed_count")), ("sheet_prices", ("ready_count", "review_count")),
          ("sheet_receipts", ("ready_count", "review_count")), ("ps_fees", ("ready_count", "review_count")), ("sheet_road", ("new_count", "conflict_count")))


# ---------------------------------------------------------------- đầu vào

class WebDir:
    """Thư mục JSON đã tải bằng GET; dùng cho test và khi chạy lại trên một bản đã lưu."""

    def __init__(self, folder: Path) -> None:
        if not folder.is_dir():
            raise rec.InputError("web-dir must be directory")
        self.folder = folder

    def _read(self, path: Path) -> dict:
        try:
            return rec.decode(path.read_bytes())
        except OSError as exc:
            raise rec.InputError(f"missing {path.name}") from exc

    def customers(self) -> list[dict]:
        return self._read(self.folder / "customers.json").get("customers") or []

    def ledger(self, customer_id: int) -> dict:
        return self._read(self.folder / "ledgers" / f"{customer_id}.json")

    def activity(self, since: dt.date | None, until: dt.date | None) -> list[dict]:
        days = []
        for path in sorted((self.folder / "activity").glob("*.json")):
            day = dt.date.fromisoformat(path.stem)
            if (since is None or day >= since) and (until is None or day <= until):
                days.append(self._read(path))
        return days


class WebApi:
    """GET qua API V7: loopback có cổng, hoặc host Serve được nêu đích danh (cùng luật với v7_reconcile_sheet)."""

    def __init__(self, base: str, serve_hosts: list[str]) -> None:
        self.base = rec.api_base(base, serve_hosts)
        self.opener = build_opener(ProxyHandler({}), rec.NoRedirect())

    def _get(self, route: str) -> dict:
        with self.opener.open(self.base + route, timeout=120) as response:
            return rec.decode(response.read())

    def customers(self) -> list[dict]:
        return self._get("/api/v7/customers").get("customers") or []

    def ledger(self, customer_id: int) -> dict:
        return self._get(f"/api/v7/ledger?customer={customer_id}")

    def activity(self, since: dt.date | None, until: dt.date | None) -> list[dict]:
        if since is None or until is None:
            return []
        return [self._get(f"/api/v7/activity?day={since + dt.timedelta(days=offset)}") for offset in range((until - since).days + 1)]


def read_tong(xlsx: Path) -> dict[str, Any]:
    """Khối mới nhất (ngoài cùng bên phải) của tab TONG, giữ tên như Sheet ghi. Cùng cách tìm cột với `live_tong` của máy đối soát."""
    import v7_load_real_copy as loader  # nạp muộn: chỉ cần khi có --xlsx

    empty: dict[str, Any] = {"month": None, "rows": []}
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
        found = [{"name": " ".join(str(cells[name_col]).split()), "end_vnd": loader.integer(cells.get(balance_col))}
                 for number, cells in rows if number > header[0] and str(cells.get(name_col) or "").strip()]
        return {"month": f"{title.group(2)}-{int(title.group(1)):02d}", "rows": found}
    return empty


def load_json(path: Path) -> dict:
    try:
        return rec.decode(path.read_bytes())
    except OSError as exc:
        raise rec.InputError(f"cannot read {path.name}") from exc


# ---------------------------------------------------------------- tiền và khóa

def as_int(value: Any) -> int:
    """Tiền để cộng: ô trống tính 0 trong PHÉP CỘNG của báo cáo; so từng dòng thì trống vẫn là trống."""
    return int(value) if value not in (None, "") else 0


def sheet_money(row: dict) -> int | None:
    total = row.get("sheet_total_vnd")
    if total is None and row.get("sheet_unit_price_vnd") is not None:
        total = row["sheet_unit_price_vnd"] + (row.get("sheet_other_fee_vnd") or 0)
    return total


def sheet_months(rows: list[dict], receipt_rows: list[dict]) -> tuple[dict[str, int], dict[str, int]]:
    """Phát sinh và thu của một tab theo tháng nợ; ô trống tính 0 trong phép cộng. Phép kiểm TONG của máy đối soát dùng chung (KIEM-TONG-01)."""
    charge: Counter[str] = Counter()
    for row in rows:
        charge[month_key(row.get("debt_month"))] += sheet_money(row) or 0
    paid: Counter[str] = Counter()
    for row in receipt_rows:
        paid[month_key(row.get("debt_month"))] += row.get("amount_vnd") or 0
    return dict(charge), dict(paid)


def target_money(target: dict) -> int | None:
    if target["kind"] == "legacy":
        return target["total"]
    return None if target["price"] is None else target["price"] + (target["fee"] or 0)


def month_key(value: Any) -> str:
    return str(value or "")[:7]


def tong_key(text: Any) -> str:
    """Tên trên TONG hay khác tên tab ở dấu, khoảng trắng, gạch nối: so bằng chữ và số đã bỏ dấu."""
    plain = unicodedata.normalize("NFD", str(text or "").upper().replace("Đ", "D"))
    return re.sub(r"[^0-9A-Z一-鿿]+", "", "".join(ch for ch in plain if not unicodedata.combining(ch)))


def candidates(row: dict, pool: list[dict]) -> list[dict]:
    """Các dòng web mà một dòng Sheet có thể trỏ tới: chính luật ghép của hàng chờ giá (`v7_price_queue.candidates`)."""
    return pq.candidates(row, pool)[0]


# ---------------------------------------------------------------- phép kiểm dòng

def audit_book(customer: dict, ledger: dict, rows: list[dict], receipt_rows: list[dict]) -> dict[str, Any]:
    """Một sổ: trạng thái ghép từng dòng, phát sinh từng tháng, tổng thu, và các dấu vết dùng để giải thích chỗ khác."""
    pool = pq.targets(ledger)
    by_target = {(target["kind"], target["id"]): target for target in pool}
    flags = {row.get("id"): ((row.get("display") or {}).get("flags") or []) for row in ledger.get("legacy_rows", [])}
    results = pq.mark_shared([pq.classify(row, pool) for row in rows])
    pointed = Counter((result["target_kind"], result["target_id"]) for result in results if result["target_id"] != "")
    statuses: Counter[str] = Counter()
    touched: set[tuple] = set()
    not_found, row_diffs, ambiguous = [], [], 0
    shared_sheet: Counter[tuple] = Counter()
    shared_month: dict[tuple, str] = {}
    spread_diff: Counter[str] = Counter()
    sheet_charge, sheet_paid = sheet_months(rows, receipt_rows)
    for row, result in zip(rows, results, strict=True):
        money, month = sheet_money(row), month_key(row.get("debt_month"))
        statuses[result["status"]] += 1
        found = candidates(row, pool) if pq.container_key(row.get("container")) else []
        touched.update((target["kind"], target["id"]) for target in found)
        if result["status"] == "NOT_FOUND":
            if money:
                not_found.append({"month": month, "container": pq.container_key(row.get("container")), "money_vnd": money, "source_row": row.get("source_row")})
            continue
        key = (result["target_kind"], result["target_id"])
        if len(found) != 1 or key not in by_target:
            ambiguous += len(found) > 1
            continue
        web = target_money(by_target[key])
        if pointed[key] > 1:   # nhiều dòng Sheet cùng trỏ một dòng web: so cả nhóm với một lần số web đang tính
            shared_sheet[key] += money or 0
            shared_month[key] = month
            continue
        if (money or 0) != (web or 0):
            spread = key[0] == "legacy" and FLAG_SPREAD in flags.get(key[1], ())
            row_diffs.append({"month": month, "container": by_target[key]["container"], "sheet_vnd": money, "web_vnd": web, "source_row": row.get("source_row"),
                              "kind": key[0], "id": key[1], "why": "TONG_TRAI_DEU_LUC_NAP" if spread else UNEXPLAINED})
            if spread:
                spread_diff[month] += (web or 0) - (money or 0)
    duplicate_extra: Counter[str] = Counter()
    for key, total in shared_sheet.items():
        duplicate_extra[shared_month[key]] += total - (target_money(by_target[key]) or 0)
    web_only = [{"month": target["month"], "container": target["container"], "money_vnd": target_money(target), "kind": target["kind"], "id": target["id"]}
                for key, target in by_target.items() if key not in touched and target_money(target)]
    carry_charge: Counter[str] = Counter()
    carry_receipt = rounded = 0
    for row in ledger.get("legacy_rows", []):
        current = row.get("current") or {}
        marks = (row.get("display") or {}).get("flags") or []
        if current.get("deleted"):
            continue
        rounded += FLAG_ROUNDED in marks
        if FLAG_CARRY in marks and row.get("kind") == "receipt":
            carry_receipt += as_int(row.get("source_total_vnd"))
        elif FLAG_CARRY in marks:
            carry_charge[month_key(current.get("month") or row.get("month"))] += as_int(current.get("counted_vnd"))
    web_charge = {month_key(month["month"]): as_int(month.get("charges_vnd")) for month in ledger.get("months", [])}
    month_adjustments: dict[str, list[int]] = defaultdict(list)
    for item in ledger.get("adjustments", []):
        if item.get("legacy_row_id") is None and item.get("trip_id") is None:
            month_adjustments[month_key(item.get("month"))].append(as_int(item.get("amount_vnd")))
    return {
        "id": customer["id"], "name": customer["name"], "web_total_vnd": as_int(ledger.get("total_outstanding_vnd")), "statuses": statuses,
        "ambiguous": ambiguous, "not_found": not_found, "web_only": web_only, "row_diffs": row_diffs,
        "month_diffs": [{"month": month, "sheet_vnd": sheet_charge.get(month, 0), "web_vnd": web_charge.get(month, 0), "diff_vnd": web_charge.get(month, 0) - sheet_charge.get(month, 0)}
                        for month in sorted(set(sheet_charge) | set(web_charge)) if sheet_charge.get(month, 0) != web_charge.get(month, 0)],
        "sheet_charge": sheet_charge, "sheet_paid": sheet_paid, "sheet_receipt_rows": len(receipt_rows),
        "paid_diff_vnd": sum(as_int(month.get("received_vnd")) for month in ledger.get("months", [])) - sum(sheet_paid.values()),
        "duplicate_extra": {month: value for month, value in duplicate_extra.items() if value}, "spread_diff": dict(spread_diff),
        "carry_charge": dict(carry_charge), "carry_receipt_vnd": carry_receipt, "rounded_rows": rounded, "month_adjustments": dict(month_adjustments),
    }


def explain(books: list[dict], ahead: dict[int, int]) -> None:
    """Gắn lời giải thích cho từng chỗ khác; mỗi lời giải thích là một đẳng thức đúng tới từng đồng. Sửa `books` tại chỗ."""
    web_index: dict[tuple, list[tuple[int, dict]]] = defaultdict(list)
    for book in books:
        for item in book["web_only"]:
            item["why"] = UNEXPLAINED
            web_index[(item["container"], item["month"], item["money_vnd"])].append((book["id"], item))
    for book in books:
        adjustments = {month: list(values) for month, values in book["month_adjustments"].items()}
        for item in book["not_found"]:
            item["why"] = UNEXPLAINED
            elsewhere = next((other for owner, other in web_index[(item["container"], item["month"], item["money_vnd"])]
                              if owner != book["id"] and other["why"] == UNEXPLAINED), None)
            twin = next((other for other in book["web_only"] if other["why"] == UNEXPLAINED and other["month"] == item["month"] and other["money_vnd"] == item["money_vnd"]), None)
            if elsewhere is not None:   # cùng container, cùng tháng, cùng tiền, nằm ở sổ khác trên web
                item["why"] = elsewhere["why"] = "DOI_SANG_SO_KHAC"
            elif twin is not None:      # cùng sổ, cùng tháng, cùng tiền, chỉ khác chữ ở ô container
                item["why"] = twin["why"] = "KHAC_CHU_O_CONTAINER"
            elif item["money_vnd"] in adjustments.get(item["month"], []):
                adjustments[item["month"]].remove(item["money_vnd"])
                item["why"] = "DA_GHI_BANG_DIEU_CHINH"
    for book in books:
        # Web đi trước: chuyến web có giá mà Sheet chưa có dòng, hoặc dòng Sheet còn trống tiền. Chỉ nhận khi cộng lại đúng số máy đối soát báo.
        open_ahead = [item for item in book["web_only"] if item["why"] == UNEXPLAINED and item["kind"] == "trip"]
        open_ahead += [item for item in book["row_diffs"] if item["why"] == UNEXPLAINED and item["kind"] == "trip" and not item["sheet_vnd"]]
        book_ahead = ahead.get(book["id"], 0)
        ahead_by_month: Counter[str] = Counter()
        if book_ahead and sum(item.get("money_vnd", item.get("web_vnd")) or 0 for item in open_ahead) == book_ahead:
            for item in open_ahead:
                item["why"] = "WEB_DI_TRUOC"
                ahead_by_month[item["month"]] += item.get("money_vnd", item.get("web_vnd")) or 0
        for item in book["month_diffs"]:
            month, diff = item["month"], item["diff_vnd"]
            if ahead_by_month.get(month) == diff:
                item["why"] = "WEB_DI_TRUOC"
            elif book["duplicate_extra"].get(month) and diff == -book["duplicate_extra"][month]:
                item["why"] = "DONG_LAP_TREN_SHEET"
            elif book["spread_diff"].get(month) and diff == book["spread_diff"][month]:
                item["why"] = "TONG_TRAI_DEU_LUC_NAP"
            elif book["carry_charge"].get(month) and diff == book["carry_charge"][month]:
                item["why"] = "BU_SO_DU_CHUYEN_NAM"
            else:
                item["why"] = UNEXPLAINED
        diff = book["paid_diff_vnd"]
        if not diff:
            book["paid_why"] = None
        elif book["carry_receipt_vnd"] and diff == book["carry_receipt_vnd"]:
            book["paid_why"] = "BU_SO_DU_CHUYEN_NAM"
        elif book["rounded_rows"] and abs(diff) <= book["sheet_receipt_rows"]:
            book["paid_why"] = "LAM_TRON_DONG"
        else:
            book["paid_why"] = UNEXPLAINED


def audit_rows(customers: list[dict], ledgers: dict[int, dict], prices: dict, receipts: dict, ahead: dict[int, int],
               ignored_tabs: frozenset[str] = frozenset()) -> dict[str, Any]:
    owned = pq.owners([{**customer, "key": customer["id"]} for customer in customers])
    tabs: Counter[str] = Counter(pq.name_key(row.get("customer_tab")) for row in prices["rows"])
    tabs.update(pq.name_key(row.get("customer_tab")) for row in receipts["rows"])
    with_tab = {owner[0] for tab, owner in owned.items() if tab in tabs}
    books = [audit_book(customer, ledgers[customer["id"]], pq.book_rows(prices, customer["id"], customers), pq.book_rows(receipts, customer["id"], customers))
             for customer in customers]
    explain(books, ahead)
    loose = sorted(tab for tab in tabs if tab not in owned)
    return {"books": books, "tabs_without_book": [tab for tab in loose if tab not in ignored_tabs], "tabs_ignored": sum(1 for tab in loose if tab in ignored_tabs),
            "books_without_tab": [customer["id"] for customer in customers if customer["id"] not in with_tab]}


# ---------------------------------------------------------------- phép kiểm TONG

def audit_tong(tong: dict, books: list[dict], ahead: dict[int, int], aliases: dict[str, str]) -> dict[str, Any]:
    """Khối TONG với từng sổ. `books` chỉ cần id, name, web_total_vnd, sheet_charge, sheet_paid. Máy đối soát mỗi giờ gọi đúng hàm này
    (KIEM-TONG-01): sửa ở đây là sửa cả hai."""
    month = tong.get("month")
    if not month:
        return {"month": None, "skipped": "TONG_KHONG_DOC_DUOC"}
    by_key: dict[str, list[dict]] = defaultdict(list)
    for book in books:
        by_key[tong_key(book["name"])].append(book)
    expected = {}
    for book in books:
        later_charge = sum(value for key, value in book["sheet_charge"].items() if key > month)
        later_paid = sum(value for key, value in book["sheet_paid"].items() if key > month)
        expected[book["id"]] = book["web_total_vnd"] - ahead.get(book["id"], 0) - later_charge + later_paid
    used: set[int] = set()
    matched = 0
    differs, unknown_names = [], []
    for row in tong.get("rows", []):
        found = by_key.get(tong_key(aliases.get(tong_key(row["name"]), row["name"])), [])
        if len(found) != 1 or found[0]["id"] in used:
            if row.get("end_vnd"):
                unknown_names.append({"name": row["name"], "end_vnd": row["end_vnd"]})
            continue
        if row.get("end_vnd") is None:
            continue   # có tên mà ô trống: xét ở danh sách "để trống" bên dưới
        used.add(found[0]["id"])
        if row["end_vnd"] == expected[found[0]["id"]]:
            matched += 1
        else:
            differs.append({"name": row["name"], "book": found[0]["id"], "tong_vnd": row["end_vnd"], "expected_vnd": expected[found[0]["id"]]})
    blank = [{"book": book["id"], "name": book["name"], "expected_vnd": expected[book["id"]]} for book in books if book["id"] not in used and expected[book["id"]]]
    tong_sum = sum(row.get("end_vnd") or 0 for row in tong.get("rows", []))
    return {"month": month, "matched": matched, "differs": differs, "unknown_names": unknown_names, "blank_on_tong": blank,
            "tong_sum_vnd": tong_sum, "expected_sum_vnd": sum(expected.values()), "gap_vnd": tong_sum - sum(expected.values())}


# ---------------------------------------------------------------- nhật ký và trạng thái sổ

def is_person(event: dict) -> bool:
    return "@" in str(event.get("actor") or "")


def minutes_between(first: dict, second: dict) -> int:
    return int((dt.datetime.fromisoformat(second["at"]) - dt.datetime.fromisoformat(first["at"])).total_seconds() // 60)


def audit_activity(days: list[dict]) -> dict[str, Any]:
    events = sorted((event for day in days for event in day.get("events", [])), key=lambda event: event["id"])
    capped = [str(day.get("day")) for day in days if day.get("total") not in (None, len(day.get("events", [])))]
    people = Counter(event["actor"] for event in events if is_person(event))
    by_kind: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        by_kind[event["kind"]]["person" if is_person(event) else "machine" if event.get("actor") == MACHINE else "other"] += 1
    operations = {label: {"person": sum(by_kind[kind]["person"] for kind in kinds), "machine": sum(by_kind[kind]["machine"] for kind in kinds),
                          "other": sum(by_kind[kind]["other"] for kind in kinds)} for label, kinds in OPERATIONS.items()}
    offsets = sum(1 for event in events if event["kind"] == "receipt" and event.get("counterparty_name"))
    machine = [event for event in events if event.get("actor") == MACHINE]
    receipts = {event["after"].get("receipt"): event for event in events if event["kind"] == "receipt"}
    voided_machine = [{"customer_id": event.get("customer_id"), "pid": event["after"].get("pid"), "amount_vnd": event["before"].get("amount_vnd"), "reason": event["after"].get("void_reason")}
                      for event in events if event["kind"] == "void" and (receipts.get(event["after"].get("receipt")) or {}).get("actor") == MACHINE]
    deleted = {((event["before"].get("adjustment") or {}).get("id")): event for event in events if event["kind"] == "adjust_month_delete"}
    machine_adjustments = [event for event in machine if event["kind"] == "adjust_month"]
    lifetimes = sorted(minutes_between(event, deleted[event["after"].get("adjustment")]) for event in machine_adjustments if event["after"].get("adjustment") in deleted)
    chains: dict[tuple, list[dict]] = defaultdict(list)
    for event in events:
        if event["kind"] == "price_edit":
            chains[(event.get("customer_id"), event["after"]["price"].get("trip_id"))].append(event)
    fills = 0
    overwrites, flipped, corrected = [], [], []
    for (customer_id, trip_id), chain in chains.items():
        for index, event in enumerate(chain):
            if event.get("actor") != MACHINE:
                continue
            before, after = event["before"]["price"], event["after"]["price"]
            if before.get("unit_price_vnd") is None and before.get("other_fee_vnd") is None:
                fills += 1
                continue
            item = {"customer_id": customer_id, "trip_id": trip_id, "at": event["at"], "before": [before.get("unit_price_vnd"), before.get("other_fee_vnd")],
                    "after": [after.get("unit_price_vnd"), after.get("other_fee_vnd")]}
            overwrites.append(item)
            if any(later["after"]["price"].get("unit_price_vnd") == before.get("unit_price_vnd") and later["after"]["price"].get("other_fee_vnd") == before.get("other_fee_vnd")
                   for later in chain[index + 1:]):
                flipped.append(item)
        last_machine = max((index for index, event in enumerate(chain) if event.get("actor") == MACHINE), default=None)
        if last_machine is not None:
            base = chain[last_machine]["after"]["price"].get("unit_price_vnd")
            corrected += [{"customer_id": customer_id, "trip_id": trip_id, "at": event["at"]} for event in chain[last_machine + 1:]
                          if is_person(event) and event["after"]["price"].get("unit_price_vnd") != base]
    pasted = {trip.get("trip_id"): str(event.get("actor") or "") for event in events if event["kind"] == "paste" for trip in event["after"].get("trips", [])}

    def origin(trip_id: Any) -> str:
        actor = pasted.get(trip_id, "")
        return "machine" if actor == MACHINE else "person" if "@" in actor else "other"

    removed = Counter(origin(event["after"]["trip"].get("id")) for event in events if event["kind"] == "trip_delete")
    locks: dict[tuple, list[dict]] = defaultdict(list)
    for event in machine:
        if event["kind"] == "month_lock":
            locks[(event.get("customer_id"), event["after"].get("month"))].append(event)
    left_open = sum(1 for chain in locks.values() if sum(1 for event in chain if event["after"].get("locked") is False) != sum(1 for event in chain if event["after"].get("locked") is True))
    return {
        "events": len(events), "days": len(days), "capped_days": capped, "people": len(people), "person_events": sum(people.values()),
        "operations": operations, "never_by_person": [label for label, count in operations.items() if not count["person"]],
        "never_by_anyone": [label for label, count in operations.items() if not sum(count.values())], "offset_events": offsets,
        "unknown_kinds": sorted(set(by_kind) - {kind for kinds in OPERATIONS.values() for kind in kinds} - SYSTEM_KINDS),
        "machine": {"events": len(machine), "by_kind": dict(Counter(event["kind"] for event in machine)),
                    "receipts": sum(1 for event in machine if event["kind"] == "receipt"),
                    "receipts_vnd": sum(as_int(event["after"].get("amount_vnd")) for event in machine if event["kind"] == "receipt"),
                    "receipts_voided": voided_machine, "adjustments": len(machine_adjustments), "adjustments_deleted": len(lifetimes),
                    "adjustment_minutes": [lifetimes[0], lifetimes[len(lifetimes) // 2], lifetimes[-1]] if lifetimes else [],
                    "price_fills": fills, "price_overwrites": overwrites, "price_flipped_back": flipped, "price_corrected_by_person": corrected,
                    "trips_pasted": sum(1 for actor in pasted.values() if actor == MACHINE), "months_left_open": left_open},
        "trips_deleted_by_origin": dict(removed),
    }


def audit_state(customers: list[dict], ledgers: dict[int, dict]) -> dict[str, Any]:
    open_months, missing_price, queues = [], Counter(), Counter()
    pending = offsets = receipts = voided = 0
    for customer in customers:
        ledger = ledgers[customer["id"]]
        today = month_key(ledger.get("today_month"))
        open_months += [{"book": customer["id"], "name": customer["name"], "month": month_key(lock.get("month"))} for lock in ledger.get("month_locks", [])
                        if lock.get("locked") is False and month_key(lock.get("month")) < today]
        for trip in ledger.get("trips", []):
            if trip.get("deleted") or trip.get("status") == "rejected":
                continue
            pending += trip.get("status") == "pending_review"
            if trip.get("status") != "pending_review" and trip.get("is_missing_price"):
                missing_price[month_key(trip.get("month"))] += 1
        receipts += len(ledger.get("receipts", []))
        voided += sum(1 for receipt in ledger.get("receipts", []) if receipt.get("voided_on"))
        offsets += len(ledger.get("outgoing_offsets") or []) + sum(1 for receipt in ledger.get("receipts", []) if receipt.get("offset_pair_id"))
        for key, counts in QUEUES:
            for count in counts:
                queues[f"{key}.{count}"] += (ledger.get(key) or {}).get(count) or 0
    return {"open_old_months": open_months, "missing_price": dict(sorted(missing_price.items())), "pending_review": pending, "receipts": receipts,
            "receipts_voided": voided, "offsets": offsets, "queues": {key: value for key, value in queues.items() if value}}


# Lý do mà phần web đi trước được nhận là giải thích trọn chỗ khách còn lệch. FIXED: máy vừa tự sửa khách đó ở chính lượt ấy và khách vẫn
# còn đúng phần đi trước; `settle` của máy đối soát ghi FIXED đè lên WEB_AHEAD, con số thì như nhau.
AHEAD_REASONS = frozenset({"WEB_AHEAD", "FIXED"})


def audit_reconcile(reconcile: dict | None) -> dict[str, Any]:
    if not reconcile:
        return {"skipped": "KHONG_CO_RECONCILE", "ahead": {}}
    ahead, unexplained, other, earlier = {}, 0, [], 0
    for row in reconcile.get("customers", []):
        if row.get("fixed_at") not in (None, reconcile.get("checked_at")):
            earlier += 1   # việc máy làm ở lượt trước trong ngày, máy giữ lại cho chủ sổ soát: số của dòng là số lúc đó, không phải của lượt này
            continue
        if row.get("status") == "KHOP":
            continue
        web_ahead = as_int(row.get("web_ahead_vnd"))
        gap = as_int(row.get("difference_vnd")) - web_ahead
        if row.get("reason") in AHEAD_REASONS and web_ahead and not gap and row.get("customer_id"):
            ahead[row["customer_id"]] = web_ahead
        else:
            unexplained += abs(gap)
            other.append({"customer_id": row.get("customer_id"), "customer": row.get("customer"), "status": row.get("status"), "reason": row.get("reason"), "gap_vnd": gap})
    return {"checked_at": reconcile.get("checked_at"), "mode": reconcile.get("mode"), "counts": reconcile.get("counts"), "total": reconcile.get("total"),
            "all_web_vnd": as_int(reconcile.get("all_web_vnd")), "ahead": ahead, "ahead_vnd": sum(ahead.values()), "unexplained_vnd": unexplained,
            "not_matched": other, "fixed_earlier": earlier, "months_differ": len(reconcile.get("months_differ") or []),
            "outside_tabs": len(reconcile.get("outside_tabs") or []), "last_error": reconcile.get("last_error")}


# ---------------------------------------------------------------- báo cáo

def summarize(result: dict[str, Any]) -> dict[str, Any]:
    """Số đếm cho stdout: không có tên khách, không có số tiền."""
    books = result["rows"]["books"]
    statuses: Counter[str] = Counter()
    for book in books:
        statuses.update(book["statuses"])
    month_diffs = [item for book in books for item in book["month_diffs"]]
    row_items = [item for book in books for item in (*book["not_found"], *book["web_only"])]
    row_diffs = [item for book in books for item in book["row_diffs"]]
    tong, activity, state, reconcile = result["tong"], result["activity"], result["state"], result["reconcile"]
    must_explain = {
        "month_diffs": sum(1 for item in month_diffs if item["why"] == UNEXPLAINED),
        "paid_diffs": sum(1 for book in books if book["paid_why"] == UNEXPLAINED),
        "row_items": sum(1 for item in row_items if item["why"] == UNEXPLAINED),
        "row_money_diffs": sum(1 for item in row_diffs if item["why"] == UNEXPLAINED),
        "tabs_without_book": len(result["rows"]["tabs_without_book"]), "books_without_tab": len(result["rows"]["books_without_tab"]),
        "reconcile_not_matched": len(reconcile.get("not_matched", [])),
        "tong_differs": len(tong.get("differs", [])), "tong_unknown_names": len(tong.get("unknown_names", [])), "tong_blank": len(tong.get("blank_on_tong", [])),
        "machine_receipts_voided": len(activity.get("machine", {}).get("receipts_voided", [])), "machine_price_flipped_back": len(activity.get("machine", {}).get("price_flipped_back", [])),
        "machine_months_left_open": activity.get("machine", {}).get("months_left_open", 0),
    }
    return {
        "ok": not any(must_explain.values()), "books": len(books), "sheet_rows": sum(statuses.values()), "row_statuses": dict(statuses.most_common()),
        "month_diffs": dict(Counter(item["why"] for item in month_diffs)), "paid_diffs": dict(Counter(book["paid_why"] for book in books if book["paid_why"])),
        "row_items": dict(Counter(item["why"] for item in row_items)), "must_explain": must_explain,
        "reconcile": {key: reconcile.get(key) for key in ("checked_at", "counts", "months_differ", "outside_tabs", "fixed_earlier") if key in reconcile},
        "tong": {key: tong.get(key) for key in ("month", "matched", "skipped") if key in tong},
        "people": activity.get("people"), "never_by_person": len(activity.get("never_by_person", [])), "capped_days": len(activity.get("capped_days", [])),
        "open_old_months": len(state["open_old_months"]), "missing_price": sum(state["missing_price"].values()), "pending_review": state["pending_review"],
        "offsets": state["offsets"], "queues": state["queues"],
    }


def money(value: Any) -> str:
    return "trống" if value is None else f"{int(value):,}".replace(",", ".")


def render(result: dict[str, Any], summary: dict[str, Any]) -> str:
    books = {book["id"]: book for book in result["rows"]["books"]}
    reconcile, tong, activity, state = result["reconcile"], result["tong"], result["activity"], result["state"]
    lines = ["AUDIT TRƯỚC CHUYỂN HẲN (chỉ đọc). Có tên khách và số tiền: giữ ngoài Git.", f"Kết luận máy: {'không còn mục tiền nào phải có người xem' if summary['ok'] else 'CÒN mục phải có người xem'}", ""]
    lines += ["== A1. Lượt đối soát gần nhất", f"  {reconcile.get('checked_at')} {reconcile.get('counts')} | web đi trước {money(reconcile.get('ahead_vnd', 0))} | chưa giải thích {money(reconcile.get('unexplained_vnd', 0))}"
              f" | việc máy đã làm ở lượt trước trong ngày (không tính) {reconcile.get('fixed_earlier', 0)} dòng"]
    lines += [f"  CHƯA KHỚP sổ {row['customer_id']} {row['customer']}: {row['status']} {row['reason']} chênh {money(row['gap_vnd'])}" for row in reconcile.get("not_matched", [])]
    lines += ["", "== A3. Từng dòng", f"  {summary['sheet_rows']} dòng chuyến Sheet: {summary['row_statuses']}", "  Tháng mà phát sinh Sheet khác web:"]
    for book in books.values():
        lines += [f"    sổ {book['id']} {book['name']} {item['month']}: Sheet {money(item['sheet_vnd'])} / web {money(item['web_vnd'])} ({money(item['diff_vnd'])}) → {item['why']}" for item in book["month_diffs"]]
    lines.append("  Tổng thu Sheet khác web:")
    lines += [f"    sổ {book['id']} {book['name']}: web − Sheet {money(book['paid_diff_vnd'])} → {book['paid_why']}" for book in books.values() if book["paid_why"]]
    lines.append("  Dòng có tiền chỉ một bên có:")
    for book in books.values():
        lines += [f"    sổ {book['id']} {book['name']} {item['month']} {item['container']} {money(item['money_vnd'])} (chỉ Sheet, dòng {item['source_row']}) → {item['why']}" for item in book["not_found"]]
        lines += [f"    sổ {book['id']} {book['name']} {item['month']} {item['container']} {money(item['money_vnd'])} (chỉ web, {item['kind']} {item['id']}) → {item['why']}" for item in book["web_only"]]
    lines.append("  Dòng ghép được mà tiền khác:")
    for book in books.values():
        lines += [f"    sổ {book['id']} {book['name']} {item['month']} {item['container']}: Sheet {money(item['sheet_vnd'])} / web {money(item['web_vnd'])} (dòng {item['source_row']}) → {item['why']}"
                  for item in book["row_diffs"]]
    lines += [f"  Tab Sheet không ứng sổ nào: {result['rows']['tabs_without_book']} (đã kết luận, bỏ qua: {result['rows']['tabs_ignored']})",
              f"  Sổ web không có tab: {[books[book]['name'] for book in result['rows']['books_without_tab']]}", ""]
    lines.append("== A2. Tab TONG")
    if tong.get("month"):
        lines += [f"  Khối tháng {tong['month']}: {tong['matched']} dòng khớp | cộng TONG {money(tong['tong_sum_vnd'])} | sổ web quy về cùng mốc {money(tong['expected_sum_vnd'])} | chênh {money(tong['gap_vnd'])}"]
        lines += [f"    LỆCH {row['name']} (sổ {row['book']}): TONG {money(row['tong_vnd'])} / kỳ vọng {money(row['expected_vnd'])}" for row in tong["differs"]]
        lines += [f"    TÊN TRÊN TONG KHÔNG ỨNG SỔ NÀO: {row['name']} {money(row['end_vnd'])}" for row in tong["unknown_names"]]
        lines += [f"    TONG ĐỂ TRỐNG sổ {row['book']} {row['name']}: {money(row['expected_vnd'])}" for row in sorted(tong["blank_on_tong"], key=lambda row: -abs(row["expected_vnd"]))]
    else:
        lines.append(f"  Bỏ qua: {tong.get('skipped')}")
    machine = activity.get("machine", {})
    lines += ["", "== A5. Lệnh máy đã ghi", f"  {machine.get('events', 0)} lệnh: {machine.get('by_kind')}",
              f"  Phiếu thu {machine.get('receipts', 0)} ({money(machine.get('receipts_vnd', 0))}), bị hủy {len(machine.get('receipts_voided', []))}: {machine.get('receipts_voided')}",
              f"  Dòng điều chỉnh {machine.get('adjustments', 0)}, đã xóa {machine.get('adjustments_deleted', 0)}, tuổi thọ phút (ngắn nhất, giữa, dài nhất) {machine.get('adjustment_minutes')}",
              f"  Điền giá {machine.get('price_fills', 0)}, đè giá {len(machine.get('price_overwrites', []))}: {machine.get('price_overwrites')}",
              f"  Đè rồi quay lại {machine.get('price_flipped_back')} | người sửa lại sau máy {machine.get('price_corrected_by_person')}",
              f"  Chuyến máy dán {machine.get('trips_pasted', 0)} | chuyến bị xóa theo người dán {activity.get('trips_deleted_by_origin')} | tháng máy mở chưa khóa {machine.get('months_left_open', 0)}"]
    lines += ["", "== C2. Thao tác đã có người thật làm", f"  {activity.get('people')} login người, {activity.get('person_events')} lệnh trong {activity.get('days')} ngày ({activity.get('events')} lệnh mọi nguồn); ngày bị API cắt bớt {activity.get('capped_days')}"]
    lines += [f"    {label}: người {count['person']}, máy {count['machine']}, khác {count['other']}" for label, count in activity.get("operations", {}).items()]
    lines += [f"  Cấn trừ hai sổ: {state['offsets']} (theo trạng thái sổ), {activity.get('offset_events', 0)} (theo nhật ký)", f"  Loại lệnh lạ chưa có trong danh sách: {activity.get('unknown_kinds')}", ""]
    lines += ["== Trạng thái sổ", f"  Tháng cũ đang mở: {[(row['book'], row['name'], row['month']) for row in state['open_old_months']]}",
              f"  Chuyến chưa giá theo tháng: {state['missing_price']} | chờ kiểm {state['pending_review']} | phiếu web {state['receipts']}, đã hủy {state['receipts_voided']}", f"  Việc treo: {state['queues']}"]
    return "\n".join(lines) + "\n"


def run(web, prices: dict, receipts: dict, tong: dict | None, reconcile: dict | None, since: dt.date | None, until: dt.date | None,
        aliases: dict[str, str], ignored_tabs: frozenset[str] = frozenset()) -> dict[str, Any]:
    customers = [row for row in web.customers() if isinstance(row, dict) and type(row.get("id")) is int and isinstance(row.get("name"), str)]
    if not customers:
        raise rec.InputError("no customers")
    ledgers = {customer["id"]: web.ledger(customer["id"]) for customer in customers}
    if any(ledger.get("customer_id") != customer_id for customer_id, ledger in ledgers.items()):
        raise rec.InputError("ledger customer mismatch")
    summary = audit_reconcile(reconcile)
    rows = audit_rows(customers, ledgers, prices, receipts, summary["ahead"], ignored_tabs)
    return {"reconcile": summary, "rows": rows, "tong": audit_tong(tong, rows["books"], summary["ahead"], aliases) if tong else {"month": None, "skipped": "KHONG_CO_TONG"},
            "activity": audit_activity(web.activity(since, until)), "state": audit_state(customers, ledgers)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--api", help="HTTP loopback có cổng, hoặc HTTPS Serve")
    source.add_argument("--web-dir", type=Path, help="thư mục JSON đã tải: customers.json, ledgers/, activity/")
    parser.add_argument("--serve-host", action="append", default=[], help="host Serve được phép, dạng fqdn[:port]; lặp được")
    parser.add_argument("--xlsx", type=Path, help="bản tải sổ gốc: lấy dòng chuyến, dòng thu và tab TONG từ cùng một bản")
    parser.add_argument("--prices", type=Path, help="bản chụp prices.json của runner giá (khi không có --xlsx)")
    parser.add_argument("--receipts", type=Path, help="bản chụp receipts.json (khi không có --xlsx)")
    parser.add_argument("--tong", type=Path, help='khối TONG đã chép: {"month": "yyyy-mm", "rows": [{"name": ..., "end_vnd": ...}]} (khi không có --xlsx)')
    parser.add_argument("--tong-alias", action="append", default=[], help="TÊN TRÊN TONG=TÊN SỔ, cho tên không tự ghép được; lặp được")
    parser.add_argument("--ignore-tab", action="append", default=[], help="tab không có sổ mà chủ sổ đã kết luận là bản sao, tab cũ; lặp được")
    parser.add_argument("--reconcile", type=Path, help="reconcile.json của lượt đối soát gần nhất")
    parser.add_argument("--since", type=dt.date.fromisoformat, help="ngày đầu của nhật ký (yyyy-mm-dd)")
    parser.add_argument("--until", type=dt.date.fromisoformat, help="ngày cuối của nhật ký; với --api thì bắt buộc khi có --since")
    parser.add_argument("--out", type=Path, required=True, help="thư mục mới, ngoài mọi repo")
    args = parser.parse_args(argv)
    try:
        if bool(args.xlsx) == bool(args.prices or args.receipts) or bool(args.prices) != bool(args.receipts):
            raise rec.InputError("need --xlsx, or both --prices and --receipts")
        if args.api and bool(args.since) != bool(args.until):
            raise rec.InputError("--api needs both --since and --until")
        out = rec.output_path(args.out)
        aliases = {}
        for item in args.tong_alias:
            left, separator, right = item.partition("=")
            if not separator or not left.strip() or not right.strip():
                raise rec.InputError("invalid --tong-alias")
            aliases[tong_key(left)] = right.strip()
        if args.xlsx:
            import v7_price_snapshot as snapshots  # nạp muộn: chỉ cần khi có --xlsx

            prices, receipts = snapshots.build_all(args.xlsx)
            tong = read_tong(args.xlsx)
        else:
            prices, receipts, tong = load_json(args.prices), load_json(args.receipts), load_json(args.tong) if args.tong else None
        web = WebApi(args.api, args.serve_host) if args.api else WebDir(args.web_dir)
        result = run(web, prices, receipts, tong, load_json(args.reconcile) if args.reconcile else None, args.since, args.until, aliases,
                     frozenset(pq.name_key(tab) for tab in args.ignore_tab))
    except (rec.InputError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"ok": False, "reason": str(exc) if isinstance(exc, rec.InputError) else type(exc).__name__}))
        return 2
    summary = summarize(result)
    out.mkdir(parents=True)
    (out / "bao-cao.txt").write_text(render(result, summary), encoding="utf-8", newline="\n")
    (out / "chi-tiet.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
