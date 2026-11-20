"""ZALO-AGENT-01 Phần 4: che thông tin trong ảnh trước khi gửi ra ngoài, theo **danh sách trắng, hỏng thì che** (review 20/11/2026).

Cách cũ (dò cái nhận ra là nhạy cảm rồi tô đen) rò rỉ mỗi khi OCR bỏ sót hoặc đọc sai một ô: tên xuống dòng, số tài khoản cách đôi, mã QR,
nhãn lạ. Cách mới đảo chiều: ảnh ra là **một tấm đen cùng kích thước**, rồi chỉ dán lại từ ảnh gốc những ô chữ được **chứng minh là an toàn**.
Mọi thứ còn lại (tên, nội dung chuyển khoản, số tài khoản, QR, logo, vùng OCR không thấy chữ, ô OCR đọc sai hay lẫn nhiều thứ) vẫn đen.

Một ô chữ được dán lại khi cả bốn điều cùng đúng:

1. **Toàn bộ chữ tách được** thành các thành phần trong danh sách trắng, không còn gì khác:
   - **số tiền**: từ 2 nhóm dấu phân cách hàng nghìn trở lên (`1.500.000`, `1,500,000`, tối đa 12 chữ số), hoặc 1 nhóm kèm đơn vị VND/đ/₫ đứng ngay
     sau (`1.100 VND`); không bắt đầu bằng 0; **số liền không dấu phân cách thì không bao giờ được nhận** (dễ là mã);
   - **nhãn nguyên cụm đã biết**: `Số tiền`, `Thời gian`, `Giao dịch thành công`, `Chuyển khoản thành công`, `Phí giao dịch`, `Mã giao dịch`…
     và tên ngân hàng trong danh sách, chỉ là nhãn không kèm giá trị. Nhãn một từ (`Phí`, `Giờ`, `Ngày`) chỉ nhận khi có dấu `:` ngay sau
     (`Phí:`), vì đứng riêng nó có thể là một dòng của tên (`PHÍ THÀNH CÔNG`);
   - **ngày giờ hợp lệ**: ngày 1-31, tháng 1-12, năm 2000-2100, giờ 0-23, phút và giây 0-59;
   - dấu phân cách `: ; , - –` giữa các thành phần.
2. Nếu ô có số tiền thì **mọi số tiền trong ô phải bằng đúng `read["amount_vnd"]`** (số OCR đã đọc): phí, số dư, số tiền khác giá trị giữ đen.
   OCR không có `amount_vnd` thì ô số tiền nào cũng giữ đen, và ảnh không được gửi.
3. Độ tin cậy của ô ≥ `MIN_CONF` (0,5) và ô **không nghiêng quá `MAX_TILT` (5°)** theo 4 góc OCR gửi về (ô nghiêng thì khung chữ nhật lấn sang dòng
   trên dưới, có thể kéo theo nét chữ của dòng nhạy cảm).
4. Không chạm (kể cả cách `PAD + 1` điểm ảnh) một ô không an toàn nào.

**Không dán lại được ô số tiền nào thì không gửi** (trả None, Q3), cũng như không có ô chữ nào hoặc ảnh đã đổi kích thước so với lúc đọc. Ảnh ra là
JPEG tạo mới từ điểm ảnh (không EXIF, XMP hay chú thích), tọa độ trên ảnh đã thu nhỏ ≤ 1600 px của `ocr.prepare_image`. `RULE` là phiên bản luật
che: nó nằm trong tên thư mục ảnh đã che (`redacted-w1/`) và trong `money-reads.json`, nên đổi luật là ảnh đã che theo luật cũ không bao giờ được dùng
lại. Cần Pillow; thiếu thì `ocr.OcrUnavailable`.
"""
from __future__ import annotations

import io
import math
import re

from zalo_web_bundle import fold

from . import ocr

RULE = "w1"      # phiên bản luật che; đổi luật thì đổi mã này (tên thư mục ảnh đã che và `money-reads.json` mang nó)
PAD = 2          # điểm ảnh lấy thêm quanh ô an toàn: OCR hay cắt lẹm nét chữ vài điểm
QUALITY = 85
MIN_CONF = 0.5   # độ tin cậy tối thiểu của ô được dán lại
MAX_TILT = 5     # độ: ô nghiêng hơn thì không dán
LABELS = ("so tien giao dich", "so tien", "thoi gian giao dich", "thoi gian", "ngay giao dich", "giao dich thanh cong", "chuyen khoan thanh cong",
          "chuyen tien thanh cong", "phi giao dich", "ma giao dich", "ngan hang", "vnd", *ocr.BANKS)
UNIT = r"(?:vnd|d|₫)"
AMOUNT = rf"(?:[+-]\s?)?(?!0)(?:\d{{1,3}}(?:[.,]\d{{3}}){{2,3}}(?:\s?{UNIT})?|\d{{1,3}}[.,]\d{{3}}\s?{UNIT})"
DATE = r"(?:0?[1-9]|[12]\d|3[01])[/.\-](?:0?[1-9]|1[0-2])[/.\-](?:20\d\d|2100)"
TIME = r"(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?"
LABEL = "(?:" + "|".join(re.escape(label) for label in sorted(LABELS, key=len, reverse=True)) + ")"
PART = rf"(?<![a-z0-9]){LABEL}(?![a-z0-9])|(?<![a-z0-9])(?:phi|gio|ngay)\s*:|(?<![\d.,]){AMOUNT}(?!\d)|(?<!\d){DATE}(?!\d)|(?<!\d){TIME}(?!\d)"
SAFE = re.compile(rf"(?:\s|[:;,\-–])*(?:(?:{PART})(?:\s|[:;,\-–])*)+")
HAS_AMOUNT = re.compile(rf"(?<![\d.,]){AMOUNT}(?!\d)")


def norm(text: str) -> str:
    """Bỏ dấu, chữ thường; `Ð`/`ð` (OCR hay đọc nhầm `Đ`) về `d`. `₫` giữ nguyên."""
    return fold(text).replace("ð", "d")


def safe(text: str) -> bool:
    """Toàn bộ chữ của ô tách được thành thành phần trong danh sách trắng (không còn chữ lạ nào)."""
    return bool(SAFE.fullmatch(norm(text)))


def amount_values(text: str) -> list[int]:
    """Giá trị mọi số tiền trong ô (theo luật số tiền ở trên)."""
    return [int(re.sub(r"\D", "", found.group(0))) for found in HAS_AMOUNT.finditer(norm(text))]


def holds_amount(text: str) -> bool:
    return bool(amount_values(text))


def tilted(box: dict) -> bool:
    """Ô nghiêng quá MAX_TILT độ theo cạnh trên và cạnh trái của 4 góc (trên-trái, trên-phải, dưới-phải, dưới-trái). Không có 4 góc thì coi là thẳng."""
    corners = box.get("p")
    if not corners:
        return False
    (x0, y0), (x1, y1), _, (x3, y3) = corners
    top = abs(math.degrees(math.atan2(y1 - y0, x1 - x0)))
    left = abs(math.degrees(math.atan2(x3 - x0, y3 - y0)))
    return top > MAX_TILT or left > MAX_TILT


def overlap(a: list[int], b: list[int], pad: int = 0) -> bool:
    return a[0] - pad < b[2] and b[0] < a[2] + pad and a[1] - pad < b[3] and b[1] < a[3] + pad


def acceptable(box: dict, amount) -> bool:
    text = box.get("t")
    if not isinstance(text, str) or not safe(text) or (box.get("c") if box.get("c") is not None else 1) < MIN_CONF or tilted(box):
        return False
    values = amount_values(text)
    return not values or (amount is not None and all(value == amount for value in values))


def safe_boxes(read: dict) -> list[dict]:
    """Các ô được dán lại. Ô an toàn mà chạm một ô không an toàn thì bỏ (có thể dính nét chữ của ô nhạy cảm)."""
    boxes = read.get("boxes") or []
    amount = read.get("amount_vnd")
    wanted = [box for box in boxes if acceptable(box, amount)]
    hidden = [box["b"] for box in boxes if not acceptable(box, amount)]
    return [box for box in wanted if not any(overlap(box["b"], other, PAD + 1) for other in hidden)]


def pasted(read: dict) -> tuple[list[dict], bool]:
    """(các ô sẽ dán, có ô số tiền trong đó không)."""
    chosen = safe_boxes(read)
    return chosen, any(holds_amount(box["t"]) for box in chosen)


def redact(data: bytes, read: dict, prepare=ocr.prepare_image) -> tuple[bytes, int] | None:
    """(JPEG đã che, số ô đã dán lại) hoặc None khi không được phép gửi: không có ô chữ, ảnh đã đổi kích thước so với lúc đọc, OCR không có số tiền,
    hoặc không dán lại được ô số tiền nào (đúng bằng số OCR đã đọc)."""
    if not read.get("boxes") or not read.get("amount_vnd"):
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
    for box in chosen:
        x0, y0, x1, y1 = box["b"]
        region = (max(0, x0 - PAD), max(0, y0 - PAD), min(image.width, x1 + PAD), min(image.height, y1 + PAD))
        if region[2] > region[0] and region[3] > region[1]:
            canvas.paste(image.crop(region), region[:2])
    out = io.BytesIO()
    canvas.save(out, "JPEG", quality=QUALITY)   # tấm vẽ mới: không mang info, EXIF, XMP hay chú thích của ảnh gốc
    return out.getvalue(), len(chosen)
