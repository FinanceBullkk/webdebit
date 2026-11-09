"""Máy đoán vì sao một khách lệch mà máy không tự sửa (CHAN-DOAN-LECH-01, specs/v7-may-doi-soat.md).

Chỉ đọc, không ghi gì. Mỗi gợi ý là một chỗ cụ thể trên web hay trên Sheet, kèm số tiền web đổi nếu sửa chỗ đó theo Sheet
(`delta_vnd`, cùng chiều với `tổng Sheet − tổng web`). Bốn kiểu, đều gặp thật ngày 9/11/2026:

- `receipt_twice`: hai phiếu chưa hủy cùng ngày, cùng số tiền, mà tab Sheet có ít khoản thu số đó hơn (phiếu ghi tay rồi Sheet dời
  ô, máy ghi thêm phiếu mới). Khách trả hai lần cùng số trong một ngày thì Sheet cũng có hai dòng, không báo.
- `price_review`: dòng hàng giá cần người (`MANUAL`, `CONFLICT`, `MONTH_LOCKED`) mà Sheet tính khác web.
- `sheet_row_missing`: dòng Sheet có tiền và có chữ ở ô container mà web không có dòng nào (ví dụ "… 取消").
- `chain_break`: khách bị giữ vì số cuối một tháng trên Sheet khác số tháng trước chuyển sang + phát sinh − thu.

`explains` cho biết có tổ hợp gợi ý cộng lại đúng bằng số cần đổi; gợi ý chỉ để người xem, máy không ghi theo nó.
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations

import v7_price_queue as pq

REVIEW = ("MANUAL", "CONFLICT", "MONTH_LOCKED")   # AMBIGUOUS: không biết dòng web nào nên không tính được chênh
MAX_HINTS = 8          # sổ có quá nhiều chỗ thì danh sách không còn giúp người đọc
MAX_SUBSET = 12        # dò tổ hợp đủ nhỏ để không làm chậm lượt
_int = pq.money        # chuỗi số nguyên hoặc int; khác thì None (NULL không phải 0)


def receipt_twice(ledger: dict, sheet_receipts: list[dict] | None = None) -> list[dict]:
    """Phiếu chưa hủy, không phải cấn trừ, trùng cả ngày lẫn số tiền. Có `sheet_receipts` (khoản thu của tab, bản chụp phiếu) thì bỏ
    nhóm mà Sheet có đủ số dòng cùng số tiền: Sheet hay thiếu ngày nên chỉ so số tiền."""
    on_sheet: dict[int, int] = defaultdict(int)
    for row in sheet_receipts or []:
        if _int(row.get("amount_vnd")):
            on_sheet[_int(row["amount_vnd"])] += 1
    same: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for receipt in ledger.get("receipts") or []:
        amount = _int(receipt.get("amount_vnd"))
        if receipt.get("voided_on") or receipt.get("offset_pair_id") or not amount or not receipt.get("date"):
            continue
        same[(str(receipt["date"])[:10], amount)].append(receipt)
    return [{"kind": "receipt_twice", "date": date, "amount_vnd": amount, "pids": [r.get("pid") for r in group],
             "delta_vnd": amount * (len(group) - 1)}
            for (date, amount), group in sorted(same.items())
            if len(group) > 1 and (sheet_receipts is None or on_sheet[amount] < len(group))]


def _sheet_total(row: dict) -> int | None:
    total = _int(row.get("sheet_total_vnd"))
    if total is not None:
        return total
    price = _int(row.get("sheet_unit_price_vnd"))
    return None if price is None else price + (_int(row.get("sheet_other_fee_vnd")) or 0)


def price_rows(snapshot_rows: list[dict], ledger: dict) -> list[dict]:
    """`price_review` và `sheet_row_missing` từ các dòng Sheet của sổ, so với chuyến và dòng sổ gốc trên web."""
    out = []
    for result in pq.mark_shared([pq.classify(row, pq.targets(ledger)) for row in snapshot_rows]):
        sheet = _sheet_total(result)
        if not sheet:
            continue
        base = {"row": result.get("source_row"), "container": result.get("container") or "", "date": result.get("date"),
                "sheet_vnd": sheet}
        if result["status"] == "NOT_FOUND":
            out.append({"kind": "sheet_row_missing", **base, "delta_vnd": sheet})
        elif result["status"] in REVIEW:
            web = _int(result.get("web_total_vnd"))
            if web is None and _int(result.get("web_unit_price_vnd")) is not None:
                web = _int(result["web_unit_price_vnd"]) + (_int(result.get("web_other_fee_vnd")) or 0)
            if web is not None and web != sheet:
                out.append({"kind": "price_review", "status": result["status"], **base, "web_vnd": web, "delta_vnd": sheet - web})
    return out


def explains(hints: list[dict], needed: int) -> bool:
    if not needed or not hints or len(hints) > MAX_SUBSET:
        return False
    deltas = [hint["delta_vnd"] for hint in hints]
    return any(sum(pick) == needed for size in range(1, len(deltas) + 1) for pick in combinations(deltas, size))


def for_book(ledger: dict, snapshot_rows: list[dict], needed: int, sheet_receipts: list[dict] | None = None) -> tuple[list[dict], bool]:
    """Gợi ý cho một sổ lệch: (danh sách, có tổ hợp cộng đúng bằng `needed` không). Gợi ý gần số cần đổi nhất lên trước."""
    hints = receipt_twice(ledger, sheet_receipts) + price_rows(snapshot_rows, ledger)
    hints.sort(key=lambda hint: abs(abs(needed) - abs(hint["delta_vnd"])))
    return hints[:MAX_HINTS], explains(hints, needed)


def chain_break(checks: list[dict]) -> dict | None:
    """Tháng đầu tiên số cuối tháng trên Sheet khác số dựng lại; các tháng sau lệch theo nên không kể."""
    for check in checks:
        sheet, replay = check.get("source_cumulative_vnd"), check.get("replay_cumulative_vnd")
        if sheet is not None and replay is not None and sheet != replay:
            return {"kind": "chain_break", "month": str(check["debt_month"])[:7], "sheet_end_vnd": sheet,
                    "expected_end_vnd": replay, "delta_vnd": sheet - replay}
    return None


def money_fields(hint: dict) -> dict:
    """Ra file: tiền là chuỗi số nguyên chính xác."""
    return {key: str(value) if key.endswith("_vnd") and value is not None else value for key, value in hint.items()}
