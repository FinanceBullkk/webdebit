"""ZALO-AGENT-01 Phần 3: đọc chữ trong ảnh bằng OCR tại máy có Zalo và phân tích "có phải ảnh tiền, số tiền bao nhiêu".

Engine là đối tượng có `name`, `version` và `read(ảnh PIL) -> [{"b": [x0, y0, x1, y1], "t": chữ, "c": độ tin cậy}]`; `easyocr`
chỉ được nạp khi đọc ảnh đầu tiên (nạp model mất vài giây và vài trăm MB), nên import module này không kéo torch vào test hay vào
vòng lặp của agent. `version` có đuôi `+ANALYSIS`: đổi cách tiền xử lý hay cách phân tích thì đổi `ANALYSIS`, kho sinh file mới
(`<engine>@<version>.json`) và kết quả cũ vẫn nằm cạnh để so (`reread`).

Chữ OCR và vị trí ô chữ chỉ nằm trong kho tại máy; thứ ra khỏi máy chỉ là số tiền, giờ, ngân hàng (Phần 3 của spec).
"""
from __future__ import annotations

import io
import os
import re
from datetime import datetime
from importlib import metadata

from zalo_web_bundle import fold

ANALYSIS = "a1"        # đổi khi đổi tiền xử lý hoặc luật phân tích: kho đọc lại theo phiên bản mới
MAX_SIDE = 1600        # cạnh dài tối đa khi đọc VÀ khi gửi ra ngoài (Phần 4): tọa độ ô chữ dùng chung cho cả che ảnh
THREADS = 2
CONFIDENCE_T = 0.6     # T: độ tin cậy tối thiểu của ô số tiền để OCR được coi là "chắc" (P0: 20/20 ảnh đọc đúng, độ tin cậy 0,42-0,9, trung vị 0,73); đổi bằng ZALO_AGENT_OCR_CONFIDENCE
RIVAL = 0.85           # ứng viên số tiền khác trị mà điểm >= RIVAL * điểm cao nhất thì không còn "một ứng viên đứng đầu"

BANKS = ("vietcombank", "techcombank", "mb bank", "mbbank", "bidv", "vietinbank", "acb", "tpbank", "vpbank", "sacombank",
         "agribank", "momo", "hdbank", "shb", "ocb", "msb", "vib", "seabank", "eximbank")
KEYWORDS = ("chuyen khoan", "chuyen tien", "giao dich thanh cong", "thanh cong", "so tien", "nguoi nhan", "tai khoan",
            "ma giao dich", "noi dung", "vnd", "napas", "nguoi chuyen", "phi giao dich", *BANKS)
KEYWORD_RE = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(k) for k in sorted(KEYWORDS, key=len, reverse=True)) + r")(?![a-z0-9])")
# Số có dấu phân cách hàng nghìn (đơn vị tùy chọn), hoặc 4-10 chữ số liền với đơn vị bắt buộc: không nhặt năm hay giờ làm số tiền.
AMOUNT_RE = re.compile(r"(?<![\d.,])[+-]?\s?(?:(\d{1,3}(?:[.,]\d{3})+)(?:\s?(vnd|vnđ|đ|d))?|(\d{4,10})\s?(vnd|vnđ|đ))(?!\d)", re.IGNORECASE)
DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})(?!\d)")
TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?(?!\d)")


class OcrUnavailable(Exception):
    """Thiếu easyocr/torch/Pillow ở máy này: bộ xử lý báo `ocr_unavailable`, không phải lỗi của ảnh."""


def threshold() -> float:
    try:
        return float(os.environ.get("ZALO_AGENT_OCR_CONFIDENCE", CONFIDENCE_T))
    except ValueError:
        return CONFIDENCE_T


def prepare_image(data: bytes):
    """(ảnh PIL RGB, (rộng, cao)) với cạnh dài <= MAX_SIDE, đã xoay theo EXIF. Dùng chung cho đọc OCR và che ảnh để tọa độ khớp nhau."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise OcrUnavailable("pillow") from exc
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    scale = min(1.0, MAX_SIDE / max(image.size))
    if scale < 1:
        image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))))
    return image, image.size


class EasyOcr:
    name = "easyocr"

    def __init__(self, threads: int = THREADS):
        self.threads, self.reader, self.cached = threads, None, None

    @property
    def version(self) -> str:
        if self.cached is None:
            try:
                self.cached = f"{metadata.version('easyocr')}+{ANALYSIS}"   # không import easyocr chỉ để biết phiên bản; nhớ vì step() hỏi mỗi giây
            except metadata.PackageNotFoundError as exc:
                raise OcrUnavailable("easyocr") from exc
        return self.cached

    def read(self, image) -> list[dict]:
        if self.reader is None:
            try:
                import easyocr
                import numpy
                import torch
            except ImportError as exc:
                raise OcrUnavailable("easyocr") from exc
            torch.set_num_threads(self.threads)   # máy 6 nhân: để dành phần còn lại cho Zalo PC và live-sync
            self.reader = easyocr.Reader(["vi", "en"], gpu=False, verbose=False)
            self.numpy = numpy
        boxes = []
        for points, text, confidence in self.reader.readtext(self.numpy.asarray(image)):
            xs, ys = [point[0] for point in points], [point[1] for point in points]
            boxes.append({"b": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))], "t": text, "c": round(float(confidence), 3)})
        return boxes


ENGINES = {EasyOcr.name: EasyOcr}


def when(text: str) -> str | None:
    """Giờ giao dịch dạng ISO 8601 +07:00 (chỉ có ngày thì `YYYY-MM-DD`), hoặc None. Chỉ nhận ngày giờ hợp lệ."""
    found, clock = DATE_RE.search(text), TIME_RE.search(text)
    if not found:
        return None
    try:
        day = datetime(int(found[3]), int(found[2]), int(found[1]))
    except ValueError:
        return None
    if not clock:
        return day.date().isoformat()
    return day.replace(hour=int(clock[1]), minute=int(clock[2])).isoformat() + "+07:00"


def beside_unit(boxes: list[dict], index: int, folded: list[str]) -> bool:
    """Chữ VND/đ nằm thành ô riêng ngay bên phải cùng hàng với ô số."""
    x0, y0, x1, y1 = boxes[index]["b"]
    return any(folded[j] in ("vnd", "d") and boxes[j]["b"][0] >= x0 + (x1 - x0) / 2 and abs((boxes[j]["b"][1] + boxes[j]["b"][3]) - (y0 + y1)) <= (y1 - y0)
               for j in range(len(boxes)) if j != index)


def analyse(boxes: list[dict]) -> dict:
    """Từ các ô chữ: có dấu hiệu tiền không, số tiền ứng viên đứng đầu (ô to nhất, ưu tiên có VND/đ), độ tin cậy ô đó, số từ khóa,
    có đúng một ứng viên đứng đầu không, giờ và ngân hàng (nếu thấy). Không quyết "chắc hay không": xem `is_confident`."""
    folded = [fold(box["t"]).strip() for box in boxes]
    text = " ".join(folded)
    found = KEYWORD_RE.findall(text)
    hits = sorted(set(found))
    bank = next((word.upper() for word in found if word in BANKS), None)
    candidates, with_unit = [], False
    for index, box in enumerate(boxes):
        for match in AMOUNT_RE.finditer(box["t"]):
            digits = re.sub(r"\D", "", match[1] or match[3])
            value = int(digits)
            if value < 1000:
                continue
            unit = bool(match[2] or match[4]) or beside_unit(boxes, index, folded)
            with_unit = with_unit or unit
            height = box["b"][3] - box["b"][1]
            weight = 1.5 if unit or "vnd" in folded[index] or "so tien" in folded[index] else 1.0
            candidates.append({"value": value, "score": height * weight, "confidence": box["c"]})
    best = max(candidates, key=lambda item: item["score"], default=None)
    rivals = [item for item in candidates if best and item["value"] != best["value"] and item["score"] >= RIVAL * best["score"]]
    return {"is_money": len(hits) >= 2 or with_unit, "amount_vnd": best and best["value"], "confidence": best and best["confidence"],
            "hits": len(hits), "unique": not rivals, "txn_time": when(text), "bank": bank}


def is_confident(read: dict, limit: float | None = None) -> bool:
    """"OCR chắc" (ANH-GEMINI-01): ô số tiền đủ tin cậy, >= 2 từ khóa ngân hàng, một ứng viên đứng đầu. Tính từ trường đã lưu
    nên đổi T không cần đọc lại ảnh."""
    limit = threshold() if limit is None else limit
    return bool(read.get("is_money") and read.get("amount_vnd") and (read.get("confidence") or 0) >= limit
                and read.get("hits", 0) >= 2 and read.get("unique"))


def verdict(read: dict | None) -> str:
    """none = không dấu hiệu tiền (không rời máy); ocr = OCR chắc; unsure = có dấu hiệu tiền mà OCR không chắc."""
    if not read or not read.get("is_money"):
        return "none"
    return "ocr" if is_confident(read) else "unsure"
