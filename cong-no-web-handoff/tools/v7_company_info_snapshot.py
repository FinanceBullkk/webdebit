#!/usr/bin/env python3
"""THONG-TIN-CTY-01: đọc Sheet "thông tin khách hàng" thành bản chụp cho tab Thông tin cty và hộp debit note
(specs/v7-thong-tin-cty.md).

Usage: --spreadsheet-id ID --credentials SERVICE_ACCOUNT.json --output /var/lib/webdebit-sheet-sync/company-info.json

Hai tab, chỉ đọc (`spreadsheets.readonly`, cùng tài khoản dịch vụ với sheet_sync_runner.py):
- `THÔNG TIN CTY`: dòng tiêu đề có ô `SHIPPER`; mỗi khách là một khối nhiều dòng (xem parse_customers), ba cột shipper,
  thông tin xuất hóa đơn (tiêu đề có "HOA DON") và ngân hàng của khách (tiêu đề có "NGAN HANG").
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


# Tab khách là các khối nhiều dòng, mỗi dòng một trường; ba cột C/D/E là ba bản của cùng trường (shipper, xuất hóa đơn,
# ngân hàng). Phần đầu tab có tên ngắn ở cột A và nhãn ở cột B (COMPANY:, ADD, TAX CODE…); phần sau không có nhãn:
# dòng tên công ty, địa chỉ, dòng thuế, rồi các dòng DIRECTOR/TEL/EMAIL… và nhiều dòng ngân hàng ở cột E.
TAX_LINE = re.compile(r"^(TAX|MST|MA SO THUE|MA SO DN)\b")
FOLLOW_LINE = re.compile(r"^(TEL|TELL|TELEPHONE|PHONE|SDT|FAX|DIRECTOR|GIAM DOC|EMAIL|E-MAIL|MAIL|REPRESENT|POSITION|CHUC VU|"
                         r"GACC|MA SO CVNM|MA CVNM|HEAD OFFICE|UPDATE|CONTACT|ATTN|NGUOI DAI DIEN)")
UNLABELED = {"COMPANY", "COMPANY:"}   # nhãn cột B không in lại (tên công ty là dòng đầu khối)


def parse_customers(rows: list[list[Any]]) -> tuple[list[dict], int]:
    """(khách, số khối bỏ vì không có chữ ở cả ba cột). Một khối kết thúc khi:
    - gặp dòng trống ở cả năm cột A–E;
    - gặp dòng có tên ở cột A hoặc nhãn COMPANY ở cột B;
    - ở phần không nhãn: gặp dòng cột C không phải dòng phụ (TEL, DIRECTOR…) khi khối đã có dòng thuế,
      hoặc khi giữa dòng C trước và dòng này có dòng C trống (chỉ có D/E)."""
    at = next((index for index, row in enumerate(rows[:6]) if "SHIPPER" in [fold(cell) for cell in row]), None)
    if at is None:
        raise SheetShapeError(f"{CUSTOMERS_TAB}: không thấy dòng tiêu đề có SHIPPER trong 6 dòng đầu")
    heads = [fold(cell) for cell in rows[at]]
    shipper = heads.index("SHIPPER")
    invoice = next((i for i, head in enumerate(heads) if "HOA DON" in head), None)
    bank = next((i for i, head in enumerate(heads) if "NGAN HANG" in head), None)
    if invoice is None:
        raise SheetShapeError(f"{CUSTOMERS_TAB}: không thấy cột thông tin xuất hóa đơn")
    name_col, label_col = (shipper - 2, shipper - 1) if shipper >= 2 else (None, None)
    blocks: list[dict] = []
    current: dict | None = None
    for number, row in enumerate(rows[at + 1:], start=at + 2):
        short, label = one_line(_cell(row, name_col)), one_line(_cell(row, label_col))
        texts = {"shipper": _cell(row, shipper), "invoice": _cell(row, invoice), "bank": _cell(row, bank)}
        if not (short or label or any(texts.values())):
            if current is not None and current.get("bank_lines") and current["bank_lines"][-1]:
                current["bank_lines"].append("")
            current = None
            continue
        if current is None and blocks and not (short or label or texts["shipper"] or texts["invoice"]):
            current = blocks[-1]   # dòng ngân hàng của khách trước, nằm sau một dòng trống
        head = fold(texts["shipper"])
        starts = current is None or bool(short) or fold(label) in UNLABELED
        if not starts and not current["labeled"] and texts["shipper"] and not FOLLOW_LINE.match(head) and not TAX_LINE.match(head):
            starts = current["tax"] or current["gap"]
        if starts:
            current = {"row": number, "short": short, "labeled": bool(short or label), "tax": False, "gap": False,
                       "lines": {"shipper": [], "invoice": [], "bank": []}}
            blocks.append(current)
        if texts["shipper"]:
            current["tax"] = current["tax"] or bool(TAX_LINE.match(head)) or fold(label).startswith("TAX")
            current["gap"] = False
        elif current["lines"]["shipper"]:
            current["gap"] = True
        prefix = f"{label}: " if label and fold(label) not in UNLABELED else ""
        prefix = prefix.replace("::", ":")
        for key, text in texts.items():
            if text:
                current["lines"][key].append(prefix + text if key != "bank" else text)
        # Dòng ngân hàng giữ cả chỗ hở (dòng không có chữ ở cột E) để tách tài khoản: "" là một chỗ hở.
        bank_lines = current.setdefault("bank_lines", [])
        if texts["bank"]:
            bank_lines.extend(texts["bank"].split("\n"))
        elif bank_lines and bank_lines[-1]:
            bank_lines.append("")
        current["end"] = number
    customers, skipped = [], 0
    for block in blocks:
        lines = block["lines"]
        first = next((one_line(lines[key][0]) for key in ("shipper", "invoice") if lines[key]), "")
        if not first:
            skipped += 1
            continue
        name = block["short"] or first
        texts = {key: clean("\n".join(lines[key])) for key in lines}
        header = header_fields(texts["shipper"] or texts["invoice"])
        customers.append({"name": name, "company": first, "rows": [block["row"], block["end"]], **texts, "header": header,
                          "accounts": parse_bank_column(block.get("bank_lines", []), header["name"] or first)})
    return customers, skipped


# TAI-KHOAN-COT-E-01: cột E (THONG TIN NGAN HANG) của một khối là các tài khoản nhận tiền của chính công ty đó, viết tay:
# nhãn nằm trong ô và nhiều kiểu ("NAME OF BANK", "BANK'S ADDRESS", "BENEFICIARY’S BANK", "ACOUNT NUMBER (USD)"), có dòng
# gạch đầu "-", địa chỉ xuống dòng, dòng "RMB ACCOUNT" ở cuối. Đọc theo thứ tự dòng: ADD/ADDRESS trước ngân hàng là địa chỉ
# người nhận, sau ngân hàng là địa chỉ ngân hàng. Tài khoản mới bắt đầu khi một trường đã có lại xuất hiện, hoặc sau chỗ hở /
# dòng không nhãn khi tài khoản đang đọc đã có số.
BANK_LABEL = re.compile(r"^([^:：]{2,40}?)\s*[:：]\s*(.*)$")
CURRENCY_ONLY = re.compile(r"^(USD|VND|CNY|RMB|EUR)\s+(ACCOUNT|ACC)$")
SKIP_LINE = re.compile(r"^(NEW UPDATE|UPDATE|CAP NHAT)\b")
SPLIT_KEYS = ("beneficiary", "bank", "account", "swift")


def _bank_key(label: str, has_bank: bool) -> str | None:
    """Trường của một nhãn trong ô cột E; None là dòng không dùng (TEL, TAX…) hoặc ghi chú."""
    if "SWIFT" in label:
        return "swift"
    if "CURRENCY" in label or "LOAI TIEN" in label:
        return "currency"
    if "BANK" in label or "NGAN HANG" in label:
        return "bank_address" if re.search(r"\bADD|DIA CHI", label) else "bank"
    if re.search(r"\b(ACC|ACCOUNT|ACOUNT)\s*(NAME|HOLDER)\b|^BENEFICIARY$|^BENEFICIARY NAME", label):
        return "beneficiary"
    if re.search(r"\b(ACC|ACCOUNT|ACOUNT|A/C)\b|\bSTK\b|SO TK|SO TAI KHOAN", label):
        return "account"
    if re.match(r"^(NEW )?(ADD|ADDRESS|DIA CHI|DC)\b", label):
        return "bank_address" if has_bank else "address"
    return None


def _currency(text: str) -> str | None:
    match = CURRENCY.search(fold(text))
    return None if match is None else ("CNY" if match.group(1) == "RMB" else match.group(1))


def parse_bank_column(lines: list[str], company: str) -> list[dict]:
    """Tài khoản trong cột E của một khối; chỉ giữ tài khoản có số. Người nhận trống thì lấy tên công ty của khối."""
    accounts: list[dict] = []
    current: dict | None = None
    gap = False

    def start() -> dict:
        item = dict.fromkeys(KEYS) | {"currency": None, "lines": []}
        accounts.append(item)
        return item

    last = None
    for raw in lines:
        line = one_line(raw).lstrip("-•*+ ").strip()
        if not line:
            gap = True
            continue
        folded = fold(line)
        if SKIP_LINE.match(folded):
            continue
        if current is not None and current["account"] and gap:
            current = None
        gap = False
        match = BANK_LABEL.match(line)
        key = _bank_key(fold(match.group(1)), bool(current and current["bank"])) if match else None
        value = match.group(2).strip() if match else line
        if match is None and CURRENCY_ONLY.match(folded):
            if current is not None:
                current["currency"] = current["currency"] or _currency(folded)
                current["lines"].append(line)
            continue
        if match is None:
            if current is not None and last in ("address", "bank_address") and not current["account"]:
                current[last] = f"{current[last]} {line}"   # địa chỉ xuống dòng
                current["lines"].append(line)
                continue
            if current is None or current["account"]:
                current, last = start(), None
            if current["beneficiary"] is None and current["bank"] is None:
                key = "beneficiary"
            elif current["address"] is None and current["bank"] is None:
                key = "address"
        if current is None:
            current = start()
        if key in SPLIT_KEYS and current[key] is not None:   # trường đã có: tài khoản mới
            current = start()
        if key in ("address", "bank_address") and current[key] is not None:
            if match and fold(match.group(1)).startswith("NEW ADD") and value:   # NEW ADD thay địa chỉ cũ
                current[key] = value
            current["lines"].append(line)
            last = key
            continue
        if key == "currency":
            current["currency"] = _currency(value) or current["currency"]
        elif key == "account":
            current["currency"] = _currency(f"{match.group(1)} {value}") or current["currency"]
            current["account"] = re.sub(r"\s*\((USD|VND|CNY|RMB|EUR)\)\s*$", "", value, flags=re.I).strip() or None
        elif key in KEYS and value:
            current[key] = value
        current["lines"].append(line)
        last = key
    out = []
    for item in accounts:
        if not item["account"] or not re.search(r"\d", item["account"]):
            continue
        item["beneficiary"] = item["beneficiary"] or company
        digits = re.sub(r"\D", "", item["account"])
        item["id"] = "e" + hashlib.sha256(f"{fold(item['bank'])}|{digits}".encode()).hexdigest()[:12]
        out.append(item)
    return out


# Đầu trang debit note (tên, địa chỉ, MST, điện thoại, email) tách từ bản shipper (tiếng Anh). Nhãn có thể là cột B đã ghép
# ("NEW ADD: …") hoặc nằm sẵn trong ô ("TAX CODE: …"); địa chỉ ưu tiên NEW ADD, rồi ADD/ADDRESS, không có nhãn thì dòng thứ hai.
LABELED = re.compile(r"^\s*([A-Za-zĐđ ./-]{2,22}?)\s*[:：]\s*(.*)$")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def header_fields(text: str) -> dict:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    out: dict[str, str | None] = dict.fromkeys(("name", "address", "tax_id", "tel", "email"))
    addresses: dict[int, str] = {}
    for index, line in enumerate(lines):
        match = LABELED.match(line)
        label, value = (fold(match.group(1)), match.group(2).strip()) if match else ("", line)
        if index == 0:
            out["name"] = value if label in {"COMPANY", "COMPANY NAME", "NAME"} else line
            continue
        if not label:
            if index == 1 and not TAX_LINE.match(fold(line)):
                addresses.setdefault(3, line)
            continue
        if label.startswith("NEW ADD"):
            addresses.setdefault(0, value)
        elif label in {"ADD", "ADDRESS", "DIA CHI", "DC", "HEAD OFFICE"} or label.startswith("ADDRESS"):
            addresses.setdefault(1, value)
        elif label.startswith("OLD ADD"):
            addresses.setdefault(2, value)
        elif TAX_LINE.match(label) and out["tax_id"] is None:
            out["tax_id"] = value or None
        elif re.match(r"^(TEL|TELL|TELEPHONE|PHONE|SDT|MOBILE|HOTLINE)", label) and out["tel"] is None:
            out["tel"] = EMAIL.sub("", value).strip(" /,;") or None
    out["address"] = addresses[min(addresses)] if addresses else None
    email = EMAIL.search(text)
    out["email"] = email.group(0) if email else None
    return {key: one_line(value) if value else None for key, value in out.items()}


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
