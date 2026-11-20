"""ZALO-AGENT-01 Phần 4: che thông tin trong ảnh trước khi gửi ra ngoài, theo **danh sách trắng, hỏng thì che** (review 20/11/2026).

Cách cũ (dò cái nhận ra là nhạy cảm rồi tô đen) rò rỉ mỗi khi OCR bỏ sót hoặc đọc sai một ô: tên xuống dòng, số tài khoản cách đôi, mã QR,
nhãn lạ. Cách mới đảo chiều: ảnh ra là **một tấm đen cùng kích thước**, rồi chỉ dán lại từ ảnh gốc những ô chữ được **chứng minh là an toàn**.
Mọi thứ còn lại (tên, nội dung chuyển khoản, số tài khoản, QR, logo, vùng OCR không thấy chữ, ô OCR đọc sai hay lẫn nhiều thứ) vẫn đen.

Một ô chữ được dán lại khi toàn bộ chữ của nó tách được thành các thành phần trong danh sách trắng và không còn gì khác:

- **số tiền**: có dấu phân cách hàng nghìn (`1.500.000`, `1,500,000`), hoặc 4-10 chữ số liền kèm đơn vị VND/đ/₫; không bắt đầu bằng 0;
- **nhãn đã biết**: `Số tiền`, `Thời gian`, `Ngày`, `Giờ`, `Giao dịch thành công`, `Chuyển khoản`, `Phí`, `Mã giao dịch`… và tên ngân hàng trong danh sách,
  chỉ là nhãn, không kèm giá trị;
- **ngày giờ**: `dd/mm/yyyy`, `hh:mm`, `hh:mm:ss`;
- dấu phân cách `: ; , - –` giữa các thành phần.

Ô số tiền nằm chung ô với chữ khác (`TK 0071… +5,000,000VND … ND: NGUYEN VAN A`), ô cắt chữ lẫn với ô nhạy cảm (hai hình chữ nhật chạm nhau)
đều không được dán. **Không dán lại được ô số tiền nào thì không gửi** (trả None, Q3), cũng như không có ô chữ nào hoặc ảnh đã đổi kích thước
so với lúc đọc. Ảnh ra là JPEG tạo mới từ điểm ảnh (không EXIF, XMP hay chú thích), tọa độ trên ảnh đã thu nhỏ ≤ 1600 px của
`ocr.prepare_image`. Cần Pillow; thiếu thì `ocr.OcrUnavailable`.
"""
from __future__ import annotations

import io
import re

from zalo_web_bundle import fold

from . import ocr

PAD = 2          # điểm ảnh lấy thêm quanh ô an toàn: OCR hay cắt lẹm nét chữ vài điểm
QUALITY = 85
LABELS = ("so tien", "thoi gian giao dich", "thoi gian", "ngay giao dich", "ngay", "gio", "giao dich thanh cong", "chuyen khoan thanh cong",
          "chuyen tien thanh cong", "chuyen khoan", "chuyen tien", "giao dich", "thanh cong", "phi giao dich", "phi", "ma giao dich", "ngan hang",
          "vnd", *ocr.BANKS)
AMOUNT = r"(?:[+-]\s?)?(?!0)(?:\d{1,3}(?:[.,]\d{3})+(?:\s?(?:vnd|d|₫))?|\d{4,10}\s?(?:vnd|d|₫))"
DATE = r"\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}"
TIME = r"\d{1,2}:\d{2}(?::\d{2})?"
LABEL = "(?:" + "|".join(re.escape(label) for label in sorted(LABELS, key=len, reverse=True)) + ")"
PART = rf"(?<![a-z0-9]){LABEL}(?![a-z0-9])|{AMOUNT}(?!\d)|(?<!\d){DATE}(?!\d)|(?<!\d){TIME}(?!\d)"
SAFE = re.compile(rf"(?:\s|[:;,\-–])*(?:(?:{PART})(?:\s|[:;,\-–])*)+")
HAS_AMOUNT = re.compile(rf"(?<![\d.,]){AMOUNT}(?!\d)")


def safe(text: str) -> bool:
    """Toàn bộ chữ của ô tách được thành thành phần trong danh sách trắng (không còn chữ lạ nào)."""
    return bool(SAFE.fullmatch(fold(text)))


def holds_amount(text: str) -> bool:
    return bool(HAS_AMOUNT.search(fold(text)))


def overlap(a: list[int], b: list[int], pad: int = 0) -> bool:
    return a[0] - pad < b[2] and b[0] < a[2] + pad and a[1] - pad < b[3] and b[1] < a[3] + pad


def safe_boxes(read: dict) -> list[list[int]]:
    """Các ô được dán lại. Ô an toàn mà chạm một ô không an toàn thì bỏ (có thể dính nét chữ của ô nhạy cảm)."""
    boxes = read.get("boxes") or []
    wanted = [box["b"] for box in boxes if isinstance(box.get("t"), str) and safe(box["t"])]
    hidden = [box["b"] for box in boxes if not (isinstance(box.get("t"), str) and safe(box["t"]))]
    return [item for item in wanted if not any(overlap(item, other, PAD) for other in hidden)]


def pasted(read: dict) -> tuple[list[list[int]], bool]:
    """(các ô sẽ dán, có ô số tiền trong đó không)."""
    chosen = safe_boxes(read)
    amounts = any(holds_amount(box["t"]) for box in read.get("boxes") or [] if box["b"] in chosen and isinstance(box.get("t"), str))
    return chosen, amounts


def redact(data: bytes, read: dict, prepare=ocr.prepare_image) -> tuple[bytes, int] | None:
    """(JPEG đã che, số ô đã dán lại) hoặc None khi không được phép gửi: không có ô chữ, ảnh đã đổi kích thước so với lúc đọc, hoặc không dán
    lại được ô số tiền nào. Mọi lỗi khi vẽ cũng là không gửi (người gọi coi ngoại lệ là không che được)."""
    if not read.get("boxes"):
        return None
    chosen, has_amount = pasted(read)
    if not has_amount:
        return None
    image, size = prepare(data)
    if list(size) != list(read.get("size") or ()):
        return None
    try:
        from PIL import Image
    except ImportError as exc:
        raise ocr.OcrUnavailable("pillow") from exc
    canvas = Image.new("RGB", image.size, (0, 0, 0))
    for x0, y0, x1, y1 in chosen:
        region = (max(0, x0 - PAD), max(0, y0 - PAD), min(image.width, x1 + PAD), min(image.height, y1 + PAD))
        if region[2] > region[0] and region[3] > region[1]:
            canvas.paste(image.crop(region), region[:2])
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=QUALITY)   # tấm vẽ mới: không mang info, EXIF, XMP hay chú thích của ảnh gốc
    return out.getvalue(), len(chosen)
