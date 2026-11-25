"""SO-TIEN P0-a lát 2: file Excel sổ tiền cho kế toán đối chiếu với phần mềm kế toán (QD-09; specs/so-tien-p0a-lat2.md, mục Xuất Excel).

Dựng từ đúng dữ liệu `tien.export_rows` (người xuất phải có tien_review): ba tab Giao dịch, Phân bổ, Ngày. Không tính tiền ngoài
dữ liệu máy chủ gửi; ô thiếu là ô trống, không thành 0. Ô chữ ghi dạng chữ (inlineStr), không bao giờ là công thức, nên nội dung
chuyển khoản bắt đầu bằng "=" vẫn chỉ là chữ. P0 chỉ có tài khoản VND (tiền là đồng nguyên); tiền tệ khác dừng ở ExportError.
"""

from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from v7_xlsx_writer import Sheet, Styled, write_workbook

VN = ZoneInfo("Asia/Ho_Chi_Minh")

STATUS = {"unidentified": "Chưa rõ khách", "unapplied": "Biết khách, chưa rõ khoản", "partial": "Phân bổ một phần",
          "applied": "Đã phân bổ đủ", "unmatched": "Chưa ghép", "matched": "Đã ghép đủ"}
TARGET = {"ar_book": "Sổ nợ khách", "customer_unapplied": "Tiền khách chưa rõ khoản", "internal_transfer": "Chuyển nội bộ",
          "internal_transfer_pending": "Chuyển nội bộ chờ ghép", "cash_withdrawal": "Rút tiền mặt", "bank_fee": "Phí ngân hàng",
          "interest": "Lãi ngân hàng", "customer_funds_pending": "Tiền hàng khách chờ", "fleet": "Đội xe",
          "expense_category": "Mục chi", "other": "Khác"}
REF_LABEL = {"customer_id": "Mã sổ khách", "transaction_id": "Giao dịch đối ứng", "category": "Mục"}
COVERAGE = {"full": "Đủ", "partial": "Chưa trọn", "missing": "Thiếu sao kê"}
SIGN = {"signed": "Đã ký", "reopened": "Mở lại", "unconfirmed": "Chưa ký", "open": "Chưa ký"}
SAFE = re.compile(r"[^A-Za-z0-9-]")

TX_COLUMNS = [("Ngày ghi sổ", "date", 12), ("Ngày hiệu lực", "date", 12), ("Mã giao dịch NH", "text", 18), ("Nội dung", "text", 46),
              ("Thu", "money", 15), ("Chi", "money", 15), ("Trạng thái", "text", 22), ("Đã phân bổ", "money", 15),
              ("Còn lại", "money", 15), ("Lô nguồn", "text", 12)]
ALLOC_COLUMNS = [("Mã giao dịch", "count", 12), ("Ngày ghi sổ", "date", 12), ("Thu/Chi", "text", 8), ("Loại", "text", 26),
                 ("Đích", "text", 30), ("Số tiền", "money", 15), ("Ghi chú", "text", 40)]
DAY_COLUMNS = [("Ngày", "date", 12), ("Sao kê", "text", 14), ("Ký số dư", "text", 12), ("Ký đối soát", "text", 12)]


class ExportError(ValueError):
    pass


def _money(value: str | None) -> int | None:
    return None if value is None else int(value)


def _day(value: str | None) -> dt.date | None:
    return None if value is None else dt.date.fromisoformat(value)


def _vn(value: str) -> str:
    return dt.date.fromisoformat(value).strftime("%d/%m/%Y")


def _target(ref: dict) -> str:
    return ", ".join(f"{REF_LABEL.get(key, key)} {value}" for key, value in sorted(ref.items()))


def build(data: dict) -> tuple[str, bytes]:
    """(tên file, byte .xlsx)."""
    account = data["account"]
    if account["currency"] != "VND":
        raise ExportError("P0 chỉ xuất tài khoản VND")
    start, end = data["from"], data["to"]
    stamp = dt.datetime.fromisoformat(data["generated_at"]).astimezone(VN).strftime("%d/%m/%Y %H:%M")
    # Tài khoản tiền mặt không có mã ngân hàng, 4 số cuối (review lát 2, Thấp).
    label = f"{account['bank_code']} ••••{account['account_last4']}" if account.get("bank_code") else f"tiền mặt #{account['id']}"
    opening = (Styled(_money(data["opening_minor"]), "money") if data["opening_minor"] is not None
               else Styled(f"chưa có: sổ bắt đầu ngày {_vn(data['opening_as_of'])}" if data.get("opening_as_of") else "chưa có số dư mở", "text"))
    top = [[Styled(f"Sổ tiền {label} ({account['currency']})", "title")],
           [Styled(f"{account['legal_entity_name']} · kỳ {_vn(start)} – {_vn(end)}", "bold")],
           [Styled("Số dư sổ đầu kỳ", "bold"), None, None, None, opening],
           [Styled("Số dư sổ cuối kỳ", "bold"), None, None, None, Styled(_money(data["closing_minor"]), "money")],
           [Styled(f"Xuất bởi {data['actor']} lúc {stamp}. Số dư sổ tính từ sao kê đã nhập, chưa phải số dư kế toán.", "text")]]
    rows = []
    for tx in data["transactions"]:
        amount = _money(tx["amount_minor"])
        rows.append([_day(tx["booking_date"]), _day(tx["value_date"]), tx["bank_ref"], tx["description"],
                     amount if tx["direction"] == "in" else None, amount if tx["direction"] == "out" else None,
                     STATUS.get(tx["status"], tx["status"]), _money(tx["allocated_minor"]), _money(tx["unallocated_minor"]),
                     ", ".join(str(i) for i in tx["imports"])])
    allocations = [[line["transaction_id"], _day(line["booking_date"]), "Thu" if line["direction"] == "in" else "Chi",
                    TARGET.get(line["target_kind"], line["target_kind"]), _target(line["target_ref"]), _money(line["amount_minor"]),
                    line["note"]] for line in data["allocations"]]
    days = [[_day(day["date"]), COVERAGE.get(day["coverage"], day["coverage"]), SIGN.get(day["coverage_status"], day["coverage_status"]),
             SIGN.get(day["business_status"], day["business_status"])] for day in data["days"]]
    body = write_workbook([Sheet("Giao dịch", TX_COLUMNS, rows, top=top), Sheet("Phân bổ", ALLOC_COLUMNS, allocations),
                           Sheet("Ngày", DAY_COLUMNS, days)])
    who = (f"{SAFE.sub('', account['bank_code'])}-{SAFE.sub('', account['account_last4'] or '')}" if account.get("bank_code")
           else f"tien-mat-{account['id']}")
    name = f"so-tien-{who}-{start}-{end}.xlsx"
    return name, body
