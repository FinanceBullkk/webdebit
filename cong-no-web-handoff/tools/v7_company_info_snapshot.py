#!/usr/bin/env python3
"""THONG-TIN-CTY-01: đọc Sheet "thông tin khách hàng" thành bản chụp cho tab Thông tin cty và hộp debit note
(specs/v7-thong-tin-cty.md).

Usage: --spreadsheet-id ID --credentials SERVICE_ACCOUNT.json --output /var/lib/webdebit-sheet-sync/company-info.json

Hai tab, chỉ đọc (`spreadsheets.readonly`, cùng tài khoản dịch vụ với sheet_sync_runner.py):
- `THÔNG TIN CTY`: bảng, dòng tiêu đề có ô `SHIPPER`; cột thông tin xuất hóa đơn (tiêu đề có "HOA DON") và cột ngân hàng
  của khách (tiêu đề có "NGAN HANG"), mỗi ô một khối nhiều dòng.
- `TÀI KHOẢN USD`: mỗi tài khoản là một khối; cột B (gộp dọc) là tên khối, cột C nhãn song ngữ, cột D giá trị.
Sai cấu trúc (không thấy tiêu đề, không có tài khoản nào có số tài khoản) thì thoát mã 1 và giữ nguyên file cũ.
File đầu ra có tên khách và số tài khoản: ngoài Git, mode 600. Stdout chỉ có số đếm.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

import sheet_sync_runner as runner

API = "https://sheets.googleapis.com/v4/spreadsheets/"
DEFAULT_OUTPUT = "/var/lib/webdebit-sheet-sync/company-info.json"
CUSTOMERS_TAB = "THÔNG TIN CTY"
ACCOUNTS_TAB = "TÀI KHOẢN USD"
TITLE_COL, LABEL_COL, VALUE_COL = 1, 2, 3   # B, C, D của tab tài khoản
MAX_TEXT = 2000
# Nhãn nhận theo chữ Anh của ô nhãn; thứ tự quan trọng: "BANK ADDRESS" trước "ADDRESS", "BANK NAME" trước "ACC NAME".
FIELDS = (("BANK ADDRESS", "bank_address"), ("BANK NAME", "bank"), ("ACCOUNT NUMBER", "account"), ("ACCOUNT NO", "account"),
          ("ACC NO", "account"), ("SWIFT", "swift"), ("ACC NAME", "beneficiary"), ("ACCOUNT NAME", "beneficiary"),
          ("BENEFICIARY", "beneficiary"), ("ADDRESS", "address"))
KEYS = ("beneficiary", "address", "bank", "bank_address", "account", "swift")
CURRENCY = re.compile(r"\b(USD|VND|CNY|RMB|EUR)\b")
CJK = re.compile(r"[㐀-鿿]")


class SheetShapeError(ValueError):
    """Sheet không đúng cấu trúc đã biết; thông báo không chứa dữ liệu ô."""


def fold(text: Any) -> str:
    """Bỏ dấu, chữ hoa, gộp khoảng trắng: so tiêu đề và nhãn mà không lệ thuộc NFC/NFD hay xuống dòng."""
    plain = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(plain.upper().split())


def clean(value: Any) -> str:
    """Chữ trong ô: giữ xuống dòng, bỏ ký tự điều khiển khác, bỏ dòng trống thừa, cắt ở MAX_TEXT."""
    text = unicodedata.normalize("NFC", str(value if value is not None else "")).replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ord(ch) >= 32)
    lines = [line.strip() for line in text.split("\n")]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text[:MAX_TEXT]


def one_line(value: Any) -> str:
    return " ".join(clean(value).split())


def _cell(row: list[Any], index: int | None) -> str:
    return clean(row[index]) if index is not None and index < len(row) else ""


def parse_customers(rows: list[list[Any]]) -> tuple[list[dict], int]:
    """(khách, số dòng bỏ vì thiếu tên shipper mà vẫn có chữ)."""
    at = next((index for index, row in enumerate(rows[:6]) if "SHIPPER" in [fold(cell) for cell in row]), None)
    if at is None:
        raise SheetShapeError(f"{CUSTOMERS_TAB}: không thấy dòng tiêu đề có SHIPPER trong 6 dòng đầu")
    heads = [fold(cell) for cell in rows[at]]
    shipper = heads.index("SHIPPER")
    invoice = next((i for i, head in enumerate(heads) if "HOA DON" in head), None)
    bank = next((i for i, head in enumerate(heads) if "NGAN HANG" in head), None)
    if invoice is None:
        raise SheetShapeError(f"{CUSTOMERS_TAB}: không thấy cột thông tin xuất hóa đơn")
    customers, skipped = [], 0
    for row in rows[at + 1:]:
        name, invoice_text, bank_text = one_line(_cell(row, shipper)), _cell(row, invoice), _cell(row, bank)
        if not name:
            skipped += bool(invoice_text or bank_text)
            continue
        customers.append({"shipper": name, "invoice": invoice_text, "bank": bank_text})
    return customers, skipped


def field_key(label: str) -> str | None:
    folded = fold(label)
    return next((key for needle, key in FIELDS if needle in folded), None)


def account_number(value: str) -> str:
    """Ô số định dạng có dấu phẩy nghìn (1,044,009,194) trả về chuỗi số trơn; chữ khác giữ nguyên."""
    text = one_line(value)
    return text.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", text) else text


def short_title(title: str) -> str:
    """Phần dễ đọc của tên khối: bỏ dòng chữ Hán, dòng "ACCOUNT NUMBER INFORMATION" và dòng chỉ là (VND)."""
    keep = [line.strip() for line in title.split("\n")
            if line.strip() and not CJK.search(line) and "INFORMATION" not in fold(line) and not re.fullmatch(r"\(\s*\w{3}\s*\)", line.strip())]
    return " ".join(keep)


def parse_accounts(rows: list[list[Any]]) -> tuple[list[dict], int]:
    """(tài khoản, số khối bỏ vì không có số tài khoản)."""
    blocks: list[dict] = []
    for row in rows:
        title, label, value = _cell(row, TITLE_COL), _cell(row, LABEL_COL), _cell(row, VALUE_COL)
        if title:
            blocks.append({"title": title, "lines": []})
        if blocks and label and value:
            blocks[-1]["lines"].append({"label": label, "value": value})
    accounts, skipped, seen = [], 0, set()
    for block in blocks:
        fields: dict[str, str | None] = dict.fromkeys(KEYS)
        for line in block["lines"]:
            key = field_key(line["label"])
            if key and fields[key] is None:
                fields[key] = account_number(line["value"]) if key == "account" else line["value"]
        if not fields["account"]:
            skipped += 1
            continue
        match = CURRENCY.search(fold(block["title"]))
        currency = None if match is None else ("CNY" if match.group(1) == "RMB" else match.group(1))
        name = short_title(block["title"]) or one_line(fields["bank"] or "")
        base = "a" + hashlib.sha256(f"{fold(fields['bank'])}|{fields['account']}".encode()).hexdigest()[:12]
        ident, number = base, 2
        while ident in seen:
            ident, number = f"{base}-{number}", number + 1
        seen.add(ident)
        accounts.append({"id": ident, "title": block["title"], "label": " · ".join(part for part in (currency, name) if part),
                         "currency": currency, **fields, "lines": block["lines"]})
    if not accounts:
        raise SheetShapeError(f"{ACCOUNTS_TAB}: không có khối nào có số tài khoản")
    return accounts, skipped


def build(customer_rows: list[list[Any]], account_rows: list[list[Any]]) -> dict:
    customers, skipped_customers = parse_customers(customer_rows)
    accounts, skipped_accounts = parse_accounts(account_rows)
    return {"accounts": accounts, "customers": customers,
            "counts": {"accounts": len(accounts), "customers": len(customers),
                       "skipped_accounts": skipped_accounts, "skipped_customers": skipped_customers},
            "runner": {"created_at": dt.datetime.now(dt.UTC).isoformat(), "mode": "read-only"}}


def fetch(spreadsheet_id: str, token: str, tabs: tuple[str, str],
          opener: Callable[..., Any] = urllib.request.urlopen) -> list[list[list[Any]]]:
    """Giá trị của các tab, tìm tab theo tên đã bỏ dấu (tên tab trên Sheet có lúc ở dạng NFD)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", spreadsheet_id):
        raise ValueError("invalid spreadsheet ID")

    def get(url: str) -> dict:
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with opener(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    base = API + urllib.parse.quote(spreadsheet_id)
    titles = [sheet["properties"]["title"] for sheet in get(base + "?fields=" + urllib.parse.quote("sheets.properties.title")).get("sheets", [])]
    chosen = []
    for wanted in tabs:
        found = [title for title in titles if fold(title) == fold(wanted)]
        if len(found) != 1:
            raise SheetShapeError(f"không thấy đúng một tab {wanted}")
        chosen.append(found[0])
    query = [("ranges", "'" + title.replace("'", "''") + "'") for title in chosen] + [
        ("valueRenderOption", "FORMATTED_VALUE"), ("majorDimension", "ROWS")]
    ranges = get(base + "/values:batchGet?" + urllib.parse.urlencode(query)).get("valueRanges", [])
    if len(ranges) != len(chosen):
        raise ValueError("Sheets API returned a different number of tabs")
    out = []
    for value_range in ranges:
        start = re.search(r"!\$?[A-Z]+\$?(\d+)", value_range.get("range", ""))
        rows = value_range.get("values", [])
        out.append([[]] * (int(start.group(1)) - 1 if start else 0) + rows)
    return out


def run_once(credentials_path: str, spreadsheet_id: str, output_path: str, tabs: tuple[str, str] = (CUSTOMERS_TAB, ACCOUNTS_TAB),
             token_exchange: Callable[[dict[str, str]], str] = runner.exchange_token, opener: Callable[..., Any] | None = None) -> dict:
    credentials = runner.load_credentials(credentials_path)

    def read() -> list[list[list[Any]]]:
        token = token_exchange(credentials)
        return fetch(spreadsheet_id, token, tabs, **({"opener": opener} if opener else {}))

    customer_rows, account_rows = runner.with_timeout_retry(read)
    snapshot = build(customer_rows, account_rows)   # sai cấu trúc thì ném lỗi trước khi ghi: file cũ còn nguyên
    runner.write_snapshot(snapshot, output_path)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Read the company-info Sheet into the snapshot the V7 API serves")
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_COMPANY_SHEET_ID"))
    parser.add_argument("--output", default=os.getenv("WEBDEBIT_COMPANY_INFO_PATH", DEFAULT_OUTPUT))
    parser.add_argument("--customers-tab", default=CUSTOMERS_TAB)
    parser.add_argument("--accounts-tab", default=ACCOUNTS_TAB)
    args = parser.parse_args()
    if not args.credentials or not args.spreadsheet_id:
        parser.error("set --credentials/WEBDEBIT_GOOGLE_CREDENTIALS and --spreadsheet-id/WEBDEBIT_COMPANY_SHEET_ID")
    try:
        snapshot = run_once(args.credentials, args.spreadsheet_id, args.output, (args.customers_tab, args.accounts_tab))
    except SheetShapeError as exc:
        print(f"company-info: Sheet sai cấu trúc, giữ bản cũ: {exc}", file=sys.stderr, flush=True)
        return 1
    print(json.dumps({"output": args.output, **snapshot["counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
