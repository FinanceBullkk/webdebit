"""ZALO-AGENT-01 Phần 3: đọc chữ trong ảnh bằng OCR tại máy có Zalo và phân tích "có phải ảnh tiền, số tiền bao nhiêu".

Engine là đối tượng có `name`, `version` và `read(ảnh PIL) -> [{"b": [x0, y0, x1, y1], "t": chữ, "c": độ tin cậy}]`; `easyocr`
chạy ở tiến trình con (`ocr_child.py`), nên agent không import torch và torch chết thì agent vẫn sống. `version` có đuôi `+ANALYSIS`: đổi cách tiền xử lý hay cách phân tích thì đổi `ANALYSIS`, kho sinh file mới
(`<engine>@<version>.json`) và kết quả cũ vẫn nằm cạnh để so (`reread`).

Chữ OCR và vị trí ô chữ chỉ nằm trong kho tại máy; thứ ra khỏi máy chỉ là số tiền, giờ, ngân hàng (Phần 3 của spec).
"""
from __future__ import annotations

import atexit
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from decimal import Decimal, InvalidOperation
from importlib import metadata
from pathlib import Path

from zalo_web_bundle import fold

CHILD = Path(__file__).with_name("ocr_child.py")
ANALYSIS = "a2"        # đổi khi đổi tiền xử lý hoặc luật phân tích: kho đọc lại theo phiên bản mới
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


def threshold() -> Decimal:
    """T là xác suất, không phải tiền; dùng Decimal (luật VND-02 cấm số thực ở đường tính tiền). So được trực tiếp với số thực của JSON."""
    try:
        return Decimal(os.environ.get("ZALO_AGENT_OCR_CONFIDENCE", str(CONFIDENCE_T)))
    except InvalidOperation:
        return Decimal(str(CONFIDENCE_T))


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


class OcrFailure(Exception):
    """Tiến trình OCR chết, quá giờ hoặc trả lời hỏng khi đọc một ảnh: lỗi của lần đọc, không phải thiếu engine. `code` là mã ngắn."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class EasyOcr:
    """easyocr chạy ở **tiến trình con sống lâu** (`ocr_child.py`), agent chính không import torch. Con chết hoặc quá `timeout` giây
    thì bị giết, lần đọc sau tạo lại. Thiếu thư viện hay model (`~/.EasyOCR`, không tự tải) là `OcrUnavailable`; con chết giữa chừng là
    `OcrFailure`. Chỉ một luồng gọi `read` mỗi lúc (bộ xử lý chạy một việc một lần)."""
    name = "easyocr"

    def __init__(self, threads: int = THREADS, command: list[str] | None = None, timeout: float = 300, work: str | None = None):
        self.threads, self.timeout, self.work, self.cached = threads, timeout, work, None
        self.registered = False
        if work:   # ảnh PNG tạm nằm ở thư mục riêng của agent (không phải %TEMP%); file sót của lần chạy trước bị dọn khi khởi động
            Path(work).mkdir(parents=True, exist_ok=True)
            for leftover in Path(work).glob("ocr-*.png"):
                with contextlib.suppress(OSError):
                    leftover.unlink()
        self.command = command or [self.interpreter(), "-X", "utf8", "-I", str(CHILD), str(threads)]
        self.child = None

    @staticmethod
    def interpreter() -> str:
        """`pythonw.exe` không có luồng chuẩn: con chạy bằng `python.exe` cùng thư mục (cờ CREATE_NO_WINDOW không mở cửa sổ)."""
        exe = Path(sys.executable)
        return str(exe.with_name("python.exe")) if exe.name.lower() == "pythonw.exe" else str(exe)

    @property
    def version(self) -> str:
        if self.cached is None:
            try:
                self.cached = f"{metadata.version('easyocr')}+{ANALYSIS}"   # không import easyocr chỉ để biết phiên bản; nhớ vì step() hỏi mỗi giây
            except metadata.PackageNotFoundError as exc:
                raise OcrUnavailable("easyocr") from exc
        return self.cached

    def close(self) -> None:
        child, self.child = self.child, None
        if child is not None:
            with contextlib.suppress(OSError):
                child.kill()
            with contextlib.suppress(OSError, subprocess.SubprocessError):
                child.wait(timeout=10)

    def spawn(self):
        try:
            self.child = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            raise OcrUnavailable("child") from exc
        if not self.registered:   # đăng ký đúng một lần dù con được tạo lại nhiều lần
            atexit.register(self.close)   # agent thoát thì con không mồ côi (con cũng tự thoát khi stdin đóng)
            self.registered = True
        return self.child

    def ask(self, path: str) -> dict:
        child = self.child if self.child is not None and self.child.poll() is None else self.spawn()
        timer = threading.Timer(self.timeout, child.kill)
        timer.start()
        try:
            child.stdin.write(json.dumps({"path": path}).encode("utf-8") + b"\n")
            child.stdin.flush()
            line = child.stdout.readline()
        except OSError:
            line = b""
        finally:
            timer.cancel()
        try:
            reply = json.loads(line) if line else None
        except ValueError:
            reply = None
        if not isinstance(reply, dict):   # chết, bị giết vì quá giờ, hoặc nói rác
            self.close()
            raise OcrFailure("child_died")
        if reply.get("error") in ("unavailable", "model_missing"):
            self.close()
            raise OcrUnavailable(reply["error"])
        return reply

    def read(self, image) -> list[dict]:
        handle, path = tempfile.mkstemp(prefix="ocr-", suffix=".png", dir=self.work)
        os.close(handle)
        try:
            image.save(path, "PNG")
            reply = self.ask(path)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(path)
        boxes = reply.get("boxes")
        if not isinstance(boxes, list):
            raise OcrFailure("failed")
        clean = []
        for item in boxes:   # kiểm khuôn: ô chữ từ tiến trình con là dữ liệu, không tin
            where, text, confidence = (item.get("b"), item.get("t"), item.get("c")) if isinstance(item, dict) else (None, None, None)
            corners = item.get("p") if isinstance(item, dict) else None
            if not (isinstance(where, list) and len(where) == 4 and all(isinstance(value, int) for value in where)
                    and isinstance(text, str) and isinstance(confidence, (int, float)) and 0 <= confidence <= 1
                    and (corners is None or (isinstance(corners, list) and len(corners) == 4 and all(
                        isinstance(corner, list) and len(corner) == 2 and all(isinstance(value, int) for value in corner) for corner in corners)))):
                raise OcrFailure("bad_reply")
            clean.append({"b": where, "t": text, "c": confidence, **({"p": corners} if corners else {})})
        return clean


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


def is_confident(read: dict, limit: Decimal | float | None = None) -> bool:
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
