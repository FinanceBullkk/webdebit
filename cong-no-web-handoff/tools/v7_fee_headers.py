"""Phụ phí của dòng tab khách theo tên cột (TACH-PHI-TIEU-DE-01, docs/decisions/tach-phi-tieu-de-01.md). Chỉ đọc.

Bộ nạp và máy giá cộng mọi ô phí của dòng tab thành một khoản Khác (PHU-PHI-01 (8)). Tab có cột mang tên rõ (`PHÍ NEO 押车费`,
`卫生证`, `过磅`, `LOCAL CHARGE 本地费用`...) thì tên cột đã nói loại phí. Module này đọc từng ô theo tên cột; công cụ một lần
`v7_split_fee_by_header.py` và runner giá (`v7_price_snapshot.py`, máy tự tách chuyến mới) dùng chung.
"""

from __future__ import annotations

import sys
import unicodedata
from collections import Counter
from pathlib import Path

import v7_load_real_copy as loader

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))   # tools may use the web layer; never the reverse
from v7_price_queue import container_key

# Tên cột → trường (khóa của `v7_ps_queue.FEE_NAMES`/`FLAG_NAMES`; `kd` là loại Kiểm định). `压车` đồng âm `押车`, `并柜` cùng
# nghĩa `拼柜`, "ÍNURANCE" gõ sai trên Sheet. Một tiêu đề khớp từ hai loại trở lên ("Neo / Phi dien / Dong ghep") là Khác.
# 卫生证 (Health cert) vào loại gộp "Health + KĐ" vì đó là cột HC FEE mặc định của sổ (COT-PHU-PHI-01); debit note in như nhau.
# Bổ sung 19/11/2026: 过磅 là Cân hàng, LOCAL CHARGE 本地费用 là Local charge; Lưu bãi, Phí hủy, Sửa bill theo tên trên debit note.
# Không dùng chữ trần "CAN", "HUY", "WEIGH", "AMD": "CANCEL" chứa "CAN", tên người có "HUY", "OVERWEIGHT" là phí quá tải.
RULES = (("neo", ("NEO", "押车", "压车", "OVERSTAY")),
         ("ghep", ("GHEP", "拼柜", "并柜", "TRUCKING")),
         ("dien", ("DIEN", "发电", "插电", "电费", "GENSET", "GENERATOR")),
         ("combined", ("卫生证", "HEALTH", "HC FEE")),
         ("bao_hiem", ("BAO HIEM", "保险", "INSURANCE", "INURANCE")),
         ("kd", ("KIEM DINH",)),
         ("can_hang", ("过磅", "CAN HANG", "CAN XE")),
         ("local", ("LOCAL", "本地")),
         ("luu_bai", ("LUU BAI", "LUU KHO", "STORAGE", "早装产生")),
         ("huy", ("PHI HUY", "HUY CONT", "CANCEL", "取消")),
         ("sua_bill", ("SUA BILL", "AMD FEE", "AMEND", "改单")))


def fold(text: str) -> str:
    """Hoa, bỏ dấu tiếng Việt, giữ chữ Hán; khác `loader.normalized` (bỏ mọi chữ ngoài A-Z0-9)."""
    text = unicodedata.normalize("NFD", str(text or "").upper().replace("Đ", "D"))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).replace("/", " ").split())


def field_of(header: str) -> str:
    text = fold(header)
    found = {field for field, words in RULES if any(word in text for word in words)}
    return found.pop() if len(found) == 1 else "khac"


def header_columns(cells: dict[str, str]) -> dict[str, str]:
    """Cột của các khóa nhận ra được (cột trái nhất thắng, như bộ nạp)."""
    detected: dict[str, str] = {}
    for col, value in sorted(cells.items(), key=lambda item: loader.col_num(item[0])):
        key = loader.header_key(loader.normalized(value))
        if key and key not in detected:
            detected[key] = col
    return detected


def tab_rows(rows: list, records: list[dict]) -> list[dict]:
    """Dòng chuyến của một tab kèm phụ phí theo tên cột; `records` là kết quả `scan_tabs` của chính tab đó."""
    trips = {r["row"]: r for r in records if r["kind"] == "trip"}
    out, header, keys = [], {}, {}
    for row_no, cells in rows:
        detected = header_columns(cells)
        if {"container", "total", "price"} <= detected.keys() and not (
                keys.get("container") and detected["container"] != keys["container"]):
            header, keys = cells, detected
            continue
        record = trips.get(row_no)
        if record is None or not keys:
            continue
        out.append(fees_of(record, header, keys))
    return out


def fees_of(record: dict, header: dict[str, str], keys: dict[str, str]) -> dict:
    """Một dòng chuyến: `fees` (trường → đồng, không gồm `combined`), `combined_vnd`, `status` SHEET_OK khi tách được."""
    cells, details = record["cells"], record.get("details") or {}
    row = {"source_row": record["row"], "month": record["month"], "container": container_key(record.get("container")),
           "date": record.get("date"), "booking": None, "fees": {}, "combined_vnd": None, "status": "SHEET_OK"}
    unit, total = details.get("unit_price"), record.get("amount")
    if "COLUMN_SHIFTED" in record.get("flags", set()):
        return {**row, "status": "SHEET_SHIFTED"}
    if unit is None or total is None:
        return {**row, "status": "SHEET_NO_PRICE"}
    left = max(loader.col_num(keys[k]) for k in ("date", "from", "to") if keys.get(k)) if any(
        keys.get(k) for k in ("date", "from", "to")) else loader.col_num(keys["container"])
    fees: Counter = Counter()
    for number in range(left + 1, loader.col_num(keys["price"])):
        col = loader.col_name(number)
        value = str(cells.get(col) or "").strip()
        if not value:
            continue
        amount = loader.rounded(value)
        if amount is None:
            return {**row, "status": "SHEET_BAD_CELL"}
        if amount < 0:
            # Giảm trừ trên tab: loại có tên và Khác chỉ nhận số dương; lệnh ghi sẽ báo FEE_SIGN_INVALID và dừng cả sổ.
            return {**row, "status": "SHEET_NEGATIVE"}
        if amount:
            fees[field_of(header.get(col, ""))] += amount
    if sum(fees.values()) != total - unit:
        return {**row, "status": "SHEET_DIFF"}
    if not set(fees) - {"khac"}:
        return {**row, "status": "NO_NAMED"}
    combined = fees.pop("combined", None)
    return {**row, "fees": dict(fees), "combined_vnd": combined}


def scan_fees(tabs: list, scan: dict) -> dict[tuple[str, int], dict]:
    """(tab, dòng) → phụ phí theo tên cột, chỉ dòng tách được (SHEET_OK). `tabs` là các tab thô `scan` đã quét."""
    out = {}
    for name, rows in tabs:
        if name not in scan:
            continue
        for row in tab_rows(rows, scan[name].get("records", [])):
            if row["status"] == "SHEET_OK":
                out[(name, row["source_row"])] = {**row["fees"], **({"combined": row["combined_vnd"]}
                                                                    if row["combined_vnd"] else {})}
    return out
