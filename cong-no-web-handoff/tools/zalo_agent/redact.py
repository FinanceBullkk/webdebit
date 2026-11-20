"""ZALO-AGENT-01 Phần 4: che thông tin trong ảnh trước khi gửi ra ngoài (ANH-GEMINI-01, Q3, Q4).

Dùng vị trí ô chữ OCR đã lưu trong kho (Phần 3), nên tọa độ tính trên ảnh đã thu nhỏ ≤ 1600 px của `ocr.prepare_image`: ảnh gửi đi
và ảnh đã đọc là cùng một ảnh, cùng kích thước. Tô đen:

- ô có dãy từ 8 chữ số liền trở lên (số tài khoản, số thẻ, mã giao dịch); khoảng trắng và gạch nối giữa các số không tách dãy, dấu
  `.` `,` thì tách, nên số tiền có dấu phân cách hàng nghìn (`1.500.000`) không bao giờ bị coi là số tài khoản;
- **phần giá trị** của dòng có nhãn tài khoản (`tài khoản`, `STK`, `số TK`, `account`) hoặc nhãn tên (`người nhận`, `người chuyển`,
  `người gửi`, `chủ tài khoản`, `tên`): phần chữ đứng sau nhãn trong cùng ô, các ô bên phải cùng hàng, hoặc ô ngay dưới nhãn;
- ô chứa **số tiền đã đọc** thì luôn được giữ, kể cả khi nằm trong dòng bị che (che nhầm số tiền thì Gemini vô dụng).

Không có ô chữ nào thì không biết che chỗ nào: trả None, người gọi không được gửi ảnh (Q3). Ảnh ra là JPEG mới vẽ lại từ điểm ảnh,
không mang EXIF. Cần Pillow; thiếu thì `ocr.OcrUnavailable`.
"""
from __future__ import annotations

import io
import re

from zalo_web_bundle import fold

from . import ocr

PAD = 4          # điểm ảnh nới thêm quanh ô bị che: chữ OCR hay lệch vài điểm
SLACK = 0.03     # lùi điểm bắt đầu che phần giá trị cùng ô: vị trí ký tự chỉ là tỉ lệ ước lượng
QUALITY = 85
MIN_DIGITS = 8
ACCOUNT = re.compile(r"(?<![a-z0-9])(tai khoan|stk|so tk|account|chu tai khoan)(?![a-z0-9])")
NAME = re.compile(r"(?<![a-z0-9])(nguoi nhan|nguoi chuyen|nguoi gui|ten)(?![a-z0-9])")


def long_digits(text: str) -> bool:
    joined = re.sub(r"(?<=\d)[ \-](?=\d)", "", text)
    return any(len(run) >= MIN_DIGITS for run in re.findall(r"\d+", joined))


def is_amount(text: str, amount) -> bool:
    return bool(amount) and any(int(re.sub(r"\D", "", found[1] or found[3])) == amount for found in ocr.AMOUNT_RE.finditer(text))


def regions(read: dict) -> list[list[int]]:
    """Các hình chữ nhật [x0, y0, x1, y1] phải tô đen, theo ô chữ và số tiền đã đọc của `read`."""
    boxes = read.get("boxes") or []
    keep = {index for index, box in enumerate(boxes) if is_amount(box["t"], read.get("amount_vnd"))}
    out: list[list[int]] = []
    for index, box in enumerate(boxes):
        if index in keep:
            continue
        x0, y0, x1, y1 = box["b"]
        text, folded = box["t"], fold(box["t"])
        if long_digits(text):   # cả ô, có nhãn hay không
            out.append(box["b"])
            continue
        label = ACCOUNT.search(folded) or NAME.search(folded)
        if not label:
            continue
        if folded[label.end():].strip(" :-."):   # giá trị nằm cùng ô với nhãn: che từ cuối nhãn (ước lượng theo tỉ lệ ký tự)
            start = x0 + round((x1 - x0) * max(0.0, label.end() / max(1, len(folded)) - SLACK))
            out.append([start, y0, x1, y1])
            continue
        height = y1 - y0
        beside = [other for other in range(len(boxes)) if other != index and other not in keep
                  and boxes[other]["b"][0] >= x0 + (x1 - x0) / 2 and abs(boxes[other]["b"][1] + boxes[other]["b"][3] - y0 - y1) <= height]
        below = [other for other in range(len(boxes)) if other != index and other not in keep
                 and 0 <= boxes[other]["b"][1] - y1 <= height * 2 and boxes[other]["b"][0] < x1 and boxes[other]["b"][2] > x0]
        if not beside and below:
            beside = [min(below, key=lambda other: boxes[other]["b"][1])]
        out.extend(boxes[other]["b"] for other in beside)
    return out


def redact(data: bytes, read: dict, prepare=ocr.prepare_image) -> tuple[bytes, int] | None:
    """(JPEG đã che, số vùng đã tô) hoặc None khi không được phép gửi: không có ô chữ nào, hoặc ảnh không còn cùng kích thước với lúc đọc."""
    if not read.get("boxes"):
        return None
    image, size = prepare(data)
    if list(size) != list(read.get("size") or ()):
        return None
    try:
        from PIL import ImageDraw
    except ImportError as exc:
        raise ocr.OcrUnavailable("pillow") from exc
    draw = ImageDraw.Draw(image)
    found = regions(read)
    for x0, y0, x1, y1 in found:
        draw.rectangle([x0 - PAD, y0 - PAD, x1 + PAD, y1 + PAD], fill=(0, 0, 0))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=QUALITY)   # vẽ lại từ điểm ảnh, không truyền `exif`: ảnh ra không mang EXIF
    return out.getvalue(), len(found)
