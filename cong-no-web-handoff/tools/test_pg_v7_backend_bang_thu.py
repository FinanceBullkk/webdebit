"""BANG-THU-01: get_receipt_book — tiền về theo ngày qua mọi sổ, chỉ đọc."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from pg_v7_harness import (
    Pg,
    actor_sql,
    call,
    cutover_book,
    fixture_open_month,
    import_data,
    lit,
    new_book,
    reject_call,
    require,
    version,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from v7_receipt_queue import pay_date, reference, review_reference

NO_DATE_NOTE = " · ngày theo cuối tháng khối Sheet"  # tests/test_v7_bang_thu.py giữ chuỗi này khớp v7_sheet_fix.NO_DATE_NOTE
# Cùng bộ ví dụ cho pay_date (Python) và _legacy_pay_date (SQL): hai nơi phải đọc ngày giống hệt nhau.
DATE_TEXTS = ("45870", "45870.0", "2026-10-22", "2026-10-22 00:00:00", "2026-13-01", "23/10/2026", "1/2/2026", "23/10/2026 tt",
              "DA TT 30/10/2026", "CK 5.10.2026 VCB", "5-10-2026", "32/13/2026", "31/02/2026", "22210/2026", "123/10/2026 1/2/2026",
              "30/7", "da tt", "", "  ", "  23/10/2026  ", "1/10/20261")


def _rows(book: dict) -> list[dict]:
    return [row for day in book["days"] for row in day["rows"]] + book["undated"]


def _book(pg: Pg, month: str | None = None) -> dict:
    return call(pg, "get_receipt_book", month)


def _with_sheet_rows(pg: Pg, rows: list[tuple[str, int, str, str]], charges: list[int]) -> int:
    """Sổ có dòng thu sổ gốc: (tháng khối, số tiền, raw_date, note). Số dư đầu là phát sinh sau khi trừ thu vào tháng cũ nhất trước."""
    months = [f"2026-{n:02d}-01" for n in range(1, len(charges) + 1)]
    receipts = [sum(amount for month, amount, _, _ in rows if month == m) for m in months]
    left = sum(receipts)
    balances = []
    for charge in charges:
        used = min(left, charge)
        balances.append(charge - used)
        left -= used
    total = sum(balances)
    customer, cutover = cutover_book(pg, total)
    openings, _, checks = import_data(balances, charges=charges, receipts=receipts)
    legacy = json.dumps([{"debt_month": month, "kind": "receipt", "display": {"row": n, "raw_date": raw, "note": note},
                          "source_total_vnd": amount, "source_tab": "FAKE", "source_row": n}
                         for n, (month, amount, raw, note) in enumerate(rows, 100)])
    call(pg, "import_cutover", customer, 0, f"bang-thu-import-{customer}", cutover, openings, legacy, checks, total, "a" * 64)
    call(pg, "verify_cutover_customer", customer, cutover, version(pg, customer), f"bang-thu-verify-{customer}", "FAKE-SIGNOFF")
    call(pg, "verify_cutover", cutover, f"bang-thu-verify-all-{customer}", "FAKE-SIGNOFF")
    call(pg, "activate_cutover", cutover, f"bang-thu-activate-all-{customer}", "FAKE-SIGNOFF")
    call(pg, "activate_cutover_customer", customer, cutover, version(pg, customer), f"bang-thu-activate-{customer}", "FAKE-SIGNOFF")
    return customer


def check_bang_thu(pg: Pg) -> None:
    # Hai nơi đọc ngày cho cùng kết quả.
    for text in DATE_TEXTS:
        expected = pay_date(text)
        got = pg.value(f"SELECT sokhach._legacy_pay_date({lit(text)})")
        require((got or None) == (expected.isoformat() if expected else None), f"date rule differs for {text!r}: sql {got!r}, python {expected}")

    today = date.fromisoformat(pg.value("SELECT (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date"))
    this_month = today.replace(day=1).isoformat()
    before = _book(pg)
    debt_before = call(pg, "get_dashboard_debt")["this_month"]
    require(before["month"] == this_month and before["today_month"] == this_month and before["as_of"] == today.isoformat(), f"default month: {before}")

    # Dòng Sheet nằm khối T9 nhưng tiền về T10; khối T8 có đủ các kiểu ngày.
    sheet = _with_sheet_rows(pg, [
        ("2026-09-01", 100, "05/10/2026 tt", "05/10/2026 tt"),
        ("2026-09-01", 200, "06/10/2026", "06/10/2026"),
        ("2026-08-01", 30, "da tt", "da tt"),
        ("2026-08-01", 40, "", ""),
        ("2026-08-01", 50, "03/07/2099", "03/07/2099"),        # sau lúc nạp sổ
        ("2026-08-01", 60, "01/01/2020 tt", "01/01/2020 tt"),  # trước tháng của khối hơn 12 tháng
        ("2026-08-01", 70, "45870", "2025-08-01 00:00:00"),    # serial 01/08/2025: đúng 12 tháng trước khối, vẫn nhận
        ("2026-08-01", 80, "10/08/2026", "ghi chu rieng"),
        ("2026-08-01", 90, "11/08/2026", "11/08/2026"),        # sẽ xóa
    ], [1000] * 9)

    october = _book(pg, "2026-10-01")
    mine = [row for row in _rows(october) if row["customer_id"] == sheet]
    require([(row["date"], row["amount_vnd"], row["note"], row["book_month"], row["source"]) for row in mine]
            == [("2026-10-06", "200", None, "2026-09-01", "sheet"), ("2026-10-05", "100", "05/10/2026 tt", "2026-09-01", "sheet")],
            f"Sheet rows must sit at the money date and drop a date-only note: {mine}")
    require(all(day["date"].startswith("2026-10-") for day in october["days"]), f"days outside the month: {october['days']}")
    september = _book(pg, "2026-09-01")
    require(not [row for row in _rows(september) if row["customer_id"] == sheet], f"row of block T9 paid in T10 must leave T9: {september}")

    august = _book(pg, "2026-08-01")
    dated = {row["amount_vnd"]: row for day in august["days"] for row in day["rows"] if row["customer_id"] == sheet}
    undated = {row["amount_vnd"]: row for row in august["undated"] if row["customer_id"] == sheet}
    require(set(dated) == {"80", "90"} and dated["80"]["note"] == "ghi chu rieng" and dated["90"]["note"] is None, f"dated rows: {dated}")
    require({amount: row["note"] for amount, row in undated.items()}
            == {"30": "da tt", "40": None, "50": "03/07/2099", "60": "01/01/2020 tt"},
            f"undated rows keep what was typed and never count as a date: {undated}")
    require(all(row["date"] is None and row["book_month"] == "2026-08-01" for row in undated.values()), f"undated placement: {undated}")
    serial = _book(pg, "2025-08-01")
    require([(row["date"], row["amount_vnd"], row["note"]) for row in _rows(serial) if row["customer_id"] == sheet] == [("2025-08-01", "70", None)],
            f"serial date inside 12 months: {serial}")
    summary = august["summary"]
    require(summary["has_sheet"] is True and int(summary["undated_vnd"]) >= 180 and summary["undated_count"] >= 4, f"summary: {summary}")
    require(int(summary["total_vnd"]) == sum(int(row["amount_vnd"]) for day in august["days"] for row in day["rows"]),
            f"undated must stay out of the month total: {summary}")
    for day in august["days"]:
        require(day["count"] == len(day["rows"]) and int(day["total_vnd"]) == sum(int(row["amount_vnd"]) for row in day["rows"]), f"day total: {day}")
    index = {item["month"]: item for item in august["months"]}
    require(index["2026-08-01"]["total_vnd"] == summary["total_vnd"] and index["2026-08-01"]["undated_vnd"] == summary["undated_vnd"], f"month index: {index}")
    require(this_month in index and list(index) == sorted(index, reverse=True), f"month index must include this month, newest first: {list(index)}")

    # Khoản thu sổ gốc đã xóa rời bảng.
    legacy = call(pg, "get_ledger", sheet)["legacy_rows"]
    target = next(row["id"] for row in legacy if row["kind"] == "receipt" and row["source_total_vnd"] == "90")
    fixture_open_month(pg, sheet, "2026-08-01")
    call(pg, "delete_legacy_trip", sheet, version(pg, sheet), "bang-thu-delete", target)
    require("90" not in {row["amount_vnd"] for row in _rows(_book(pg, "2026-08-01")) if row["customer_id"] == sheet}, "deleted Sheet receipt still listed")

    # Phiếu web: hôm nay, phiếu máy đặt ngày, phiếu hủy, phân bổ, ghi chú đã sạch.
    web = new_book(pg, ("2026-08-01", 500), ("2026-09-01", 500))
    day = today.isoformat()
    call(pg, "record_receipt", web, version(pg, web), "bang-thu-r1", day, "THU TIỀN", 600, reference("23/10/2026 tt"))
    call(pg, "record_receipt", web, version(pg, web), "bang-thu-r2", day, "KHÁC", 50, f"{day[8:10]}/{day[5:7]}/{day[:4]}")
    no_date = (review_reference("abc123") + "da tt" + NO_DATE_NOTE)[:500]
    call(pg, "record_receipt", web, version(pg, web), "bang-thu-r3", day, "THU TIỀN", 70, no_date)
    call(pg, "record_receipt", web, version(pg, web), "bang-thu-r4", day, "THU TIỀN", 11, "Sheet")
    call(pg, "record_receipt", web, version(pg, web), "bang-thu-r5", day, "THU TIỀN", 13, None)
    gone = next(item["pid"] for item in call(pg, "get_ledger", web)["receipts"] if item["amount_vnd"] == "13")
    call(pg, "void_receipt", web, version(pg, web), "bang-thu-void", gone, "nhập trùng")

    now = _book(pg)
    rows = {row["amount_vnd"]: row for row in _rows(now) if row["customer_id"] == web}
    require(set(rows) == {"600", "50", "70", "11"}, f"voided receipt must leave the list: {rows}")
    require(rows["600"]["note"] == "23/10/2026 tt" and rows["600"]["date"] == day and rows["600"]["source"] == "web" and rows["600"]["pid"], f"web row: {rows['600']}")
    require(rows["600"]["allocations"] == [{"month": "2026-08-01", "kind": "debt", "amount_vnd": "500"}, {"month": "2026-09-01", "kind": "debt", "amount_vnd": "100"}],
            f"allocations: {rows['600']}")
    require(rows["50"]["note"] is None and rows["50"]["method"] == "KHÁC", f"date-only reference equal to the row date is not repeated: {rows['50']}")
    require(rows["70"]["date"] is None and rows["70"]["note"] == "da tt" and rows["70"]["book_month"] == this_month, f"machine date is not a money date: {rows['70']}")
    require(rows["11"]["note"] is None, f"bare Sheet reference: {rows['11']}")
    require(not any("abc123" in json.dumps(row) for row in rows.values()), "row fingerprint must not reach the page")
    voided = [row for row in now["voided"] if row["customer_id"] == web]
    require(len(voided) == 1 and voided[0]["amount_vnd"] == "13" and voided[0]["void_reason"] == "nhập trùng" and voided[0]["voided_on"], f"voided: {voided}")
    require(int(now["summary"]["today_vnd"]) - int(before["summary"]["today_vnd"]) == 661 and now["summary"]["today_count"] - before["summary"]["today_count"] == 3,
            f"today: {now['summary']}")
    who = [item for item in now["customers"] if item["customer_id"] == web]
    require(len(who) == 1 and (who[0]["total_vnd"], who[0]["count"], who[0]["undated_vnd"], who[0]["undated_count"], who[0]["last_date"], who[0]["book_month"])
            == ("661", 3, "70", 1, day, this_month), f"customer row: {who}")

    # Cấn trừ: không phải tiền mới vào, hai đầu đều không có dòng riêng, liệt kê riêng.
    source = new_book(pg, ("2026-08-01", 100))
    call(pg, "record_receipt", source, version(pg, source), "bang-thu-src", day, "THU TIỀN", 300)
    receiver = new_book(pg, ("2026-08-01", 100))
    call(pg, "record_offset", receiver, version(pg, receiver), source, version(pg, source), "bang-thu-offset", day, 40, None)
    after = _book(pg)
    require(not [row for row in _rows(after) if row["customer_id"] == receiver], "offset target must not be listed as money in")
    offsets = [row for row in after["offsets"] if row["target_customer_id"] == receiver]
    require(len(offsets) == 1 and (offsets[0]["source_customer_id"], offsets[0]["amount_vnd"], offsets[0]["date"]) == (source, "40", day), f"offset: {offsets}")

    # Đẳng thức cả đời: mỗi sổ, cộng mọi tháng = cộng received_vnd của get_ledger; cấn trừ chỉ chuyển giữa hai sổ.
    books = (sheet, web, source, receiver)
    listed = dict.fromkeys(books, 0)
    for item in after["months"]:
        for row in _rows(_book(pg, item["month"])):
            if row["customer_id"] in listed:
                listed[row["customer_id"]] += int(row["amount_vnd"])
    received = {book: sum(int(month["received_vnd"]) for month in call(pg, "get_ledger", book)["months"]) for book in books}
    require(listed[sheet] == received[sheet] and listed[web] == received[web], f"all-time total differs: listed {listed}, ledgers {received}")
    require(listed[source] - received[source] == 40 and received[receiver] - listed[receiver] == 40, f"offset moves money between books only: listed {listed}, ledgers {received}")

    # Đẳng thức tháng hiện tại với Tổng quan: phần tăng từ đầu case phải bằng nhau.
    debt_after = call(pg, "get_dashboard_debt")["this_month"]
    grew = int(after["summary"]["total_vnd"]) + int(after["summary"]["undated_vnd"]) - int(before["summary"]["total_vnd"]) - int(before["summary"]["undated_vnd"])
    require(grew == int(debt_after["received_vnd"]) - int(debt_before["received_vnd"]), f"this month differs from the dashboard: {grew} vs {debt_before} → {debt_after}")

    # Tháng trống, tháng sai, không có người làm; hàm chỉ đọc không đổi phiên bản sổ.
    empty_month = (today.replace(day=1) + timedelta(days=62)).replace(day=1).isoformat()
    empty = _book(pg, empty_month)
    require(empty["days"] == [] and empty["undated"] == [] and empty["customers"] == [] and empty["summary"]["total_vnd"] == "0" and empty["summary"]["has_sheet"] is False,
            f"empty month: {empty}")
    reject_call(pg, "get_receipt_book", "2026-10-15", error="INVALID_MONTH")
    pg.rejects("SELECT sokhach.get_receipt_book(NULL)", message="ACTOR_REQUIRED")
    stamp = version(pg, web)
    pg.value(actor_sql("SELECT sokhach.get_receipt_book(NULL)"))
    require(version(pg, web) == stamp, "reading must not bump customer.version")
