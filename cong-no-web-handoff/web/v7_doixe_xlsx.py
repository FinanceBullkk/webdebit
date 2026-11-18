"""DOI-XE-THU-01: file Excel bảng kê tháng gửi HTH, cùng cột với file debit đang làm (STT … CHECK LÝ DO), có dòng "Kính gửi".

Dựng từ đúng dữ liệu đọc của màn Bảng kê (`doixe.get_bang_ke`): bảng kê đã gửi lấy các dòng chép lúc gửi; tháng chưa gửi là
bản nháp, ghi rõ ở tên văn bản. Không tính tiền ngoài cộng các ô đã có: CƯỚC TỔNG = cước + đóng ghép + phát sinh của dòng; điều
chỉnh khi đối chiếu vào cột "+ - TIỀN" kèm lý do. Tổng cộng lại phải bằng tổng máy chủ gửi kèm, lệch thì không dựng file. Ô trống
là ô trống, không thành 0. GHI CHÚ chỉ có các khoản phát sinh đã đọc ("_ Tên khoản số k"), không lộ ghi chú chi phí của tài xế.
"""

from __future__ import annotations

import datetime as dt

from v7_xlsx_writer import Sheet, Styled, write_workbook

COLUMNS = [
    ("STT", "count", 6), ("NGÀY", "date", 11), ("SỐ CONT", "text", 14), ("CONT KÉO", "text", 18), ("TỈNH", "text", 18),
    ("KHO ĐÓNG HÀNG", "text", 18), ("TÀI XẾ", "text", 16), ("SỐ XE", "text", 12), ("NƠI LẤY", "text", 14), ("NƠI HẠ", "text", 14),
    ("TÊN HÀNG", "text", 14), ("CƯỚC", "money", 14), ("ĐÓNG GHÉP", "money", 12), ("PHÁT SINH", "money", 12), ("GHI CHÚ", "text", 34),
    ("CƯỚC TỔNG", "money", 15), ("KẾ TOÁN NOTE", "text", 16), ("+ - TIỀN", "money", 13), ("CHECK LÝ DO", "text", 34),
]
PHU = {"chuyen_cang": "CHUYỂN CẢNG", "tra_rong": "TRẢ RỖNG", "rut_mooc": "RÚT MOOC", "tha_mooc": "THẢ MOOC", "khac": "KHÁC"}
CUOC, GHEP, PS, TONG, DC = 11, 12, 13, 15, 17


class ExportError(ValueError):
    pass


def _int(value: str | None) -> int | None:
    return None if value is None else int(value)


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(value)


def _row(line: dict) -> list:
    items = [item for item in line.get("ps") or [] if "loi" not in item]
    cuoc, ghep, ps = _int(line.get("cuoc_vnd")), _int(line.get("ghep_vnd")), _int(line.get("ps_vnd"))
    tong = None if cuoc is None and ghep is None and ps is None else (cuoc or 0) + (ghep or 0) + (ps or 0)
    adjust = line.get("dieu_chinh") or []
    ghep_text = next((item["ten"] for item in items if item.get("cot") == "ghep" and item.get("ten") not in (None, "Đóng ghép")), None)
    loai = line.get("loai")
    return [
        line.get("stt"), _date(line["ngay"]), line.get("container"), ghep_text, line.get("tinh"), line.get("kho"), line.get("tai_xe"),
        line.get("so_xe"), line.get("noi_lay"), line.get("noi_ha"), line.get("ten_hang") or PHU.get(loai),
        cuoc, ghep, ps, "\n".join("_ " + item["goc"] for item in items) or None, tong,
        "Chưa có giá" if cuoc is None else None,
        _int(line.get("dc_vnd")),
        # File gửi công ty khác: chỉ lý do, không ghi người làm hay giờ (Lịch sử trên web giữ ai, lúc nào).
        "; ".join(a["ly_do"] for a in adjust) or None,
    ]


def rows(data: dict) -> tuple[list[list], list[list]]:
    """(hàng phía trên tiêu đề, hàng dữ liệu + tổng). Ném ExportError khi tổng cộng lại lệch tổng máy chủ."""
    month = _date(data["thang"])
    ben, book, tong = data["ben"], data.get("bang_ke"), data["tong"]
    draft = book is None
    title = f"{ben['tieu_de']} THÁNG {month.month:02d}/{month.year}" + (" (BẢN NHÁP, CHƯA GỬI)" if draft else "")
    sent = (f"Số bảng kê {book['so']} · gửi ngày {_date(book['gui_ngay']):%d/%m/%Y}" if not draft
            else f"Bản nháp ngày {_date(data['hom_nay']):%d/%m/%Y}: chặng chưa có giá để trống, chưa tính")
    top = [[Styled(title, "title")], [Styled(f"Kính gửi: {ben['kinh_gui']}", "bold")], [sent]]
    lines = data["dong"]
    body = []
    for index, line in enumerate(lines, start=1):
        row = _row({**line, "stt": line.get("stt") or index})
        body.append(row)
    sums = {col: sum(row[col] or 0 for row in body) for col in (CUOC, GHEP, PS, TONG, DC)}
    want = {CUOC: tong["cuoc_vnd"], GHEP: tong["ghep_vnd"], PS: tong["ps_vnd"], DC: tong["dc_vnd"]}
    for col, value in want.items():
        if sums[col] != int(value):
            raise ExportError(f"tổng cột {COLUMNS[col][0]} lệch: {sums[col]} ≠ {value}")
    doi = sums[TONG] + sums[DC]
    if doi != int(tong["doi_vnd"]):
        raise ExportError(f"đòi HTH lệch: {doi} ≠ {tong['doi_vnd']}")
    total = [None] * len(COLUMNS)
    total[2] = Styled(f"TỔNG {len(body)} chặng", "bold")
    for col in (CUOC, GHEP, PS, TONG, DC):
        total[col] = Styled(sums[col], "bold")
    body.append(total)
    body.append([None] * len(COLUMNS))
    for label, value in (("ĐÒI HTH (sau điều chỉnh)", doi), ("HTH ĐÃ TRẢ", int(tong["tra_vnd"])), ("CÒN PHẢI THU", int(tong["con_vnd"]))):
        line = [None] * len(COLUMNS)
        line[2] = Styled(label, "bold")
        line[TONG] = Styled(value, "bold")
        body.append(line)
    return top, body


def build(data: dict) -> tuple[str, bytes]:
    """(tên file, nội dung .xlsx) của bảng kê tháng trong `data` (kết quả `doixe.get_bang_ke`)."""
    top, body = rows(data)
    month = _date(data["thang"])
    name = f"BangKe_{data['ben']['ten']}_T{month.month:02d}_{month.year}{'_nhap' if data.get('bang_ke') is None else ''}.xlsx"
    sheet = Sheet(f"T{month.month:02d}-{month.year}", COLUMNS, body, top=top)
    return name, write_workbook([sheet])
