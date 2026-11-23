"""ZALO-AGENT-01 Phần 3: đọc chữ trong ảnh bằng OCR tại máy có Zalo và phân tích "có phải ảnh tiền, số tiền bao nhiêu".

Engine là đối tượng có `name`, `version` và `read(ảnh PIL) -> [{"b": [x0, y0, x1, y1], "t": chữ, "c": độ tin cậy}]`; `easyocr`
chạy ở tiến trình con (`ocr_child.py`), nên agent không import torch và torch chết thì agent vẫn sống.

Hai phiên bản tách nhau (A1, 23/11/2026): `version` = `<easyocr>+PREPARE` gắn với **ô chữ** (engine và tiền xử lý ảnh), là tên file trong kho
(`<engine>@<version>.json`); đổi engine hay tiền xử lý thì đổi `PREPARE`, kho đọc lại ảnh và giữ file cũ cạnh bên để so (`reread`). `ANALYSIS`
gắn với **luật phân tích** (`analyse`), lưu trong file ở trường `analysis`; đổi luật thì `refresh` chạy lại `analyse` trên ô chữ đã lưu, không gọi
engine (OCR một ảnh mất 15-19 giây, phân tích vài mili giây). File cũ không có trường `analysis` là kết quả của luật `LEGACY_ANALYSIS`.

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
PREPARE = "a2"         # phiên bản tiền xử lý ảnh trước OCR (MAX_SIDE, xoay EXIF), nằm trong tên file kho: đổi thì OCR lại mọi ảnh.
                       # Giữ "a2" (tên cũ của chuỗi gộp) để kho `easyocr@1.7.2+a2.json` đã có dùng tiếp.
ANALYSIS = "a3"        # phiên bản luật phân tích (`analyse`): đổi thì phân tích lại từ ô chữ đã lưu, không OCR lại
LEGACY_ANALYSIS = "a2" # file kho chưa có trường `analysis` (trước A1) được phân tích bằng luật này
ENGINE_FIELDS = ("engine", "version", "read_at", "size", "boxes")   # phần của engine trong một lượt đọc; còn lại là kết quả `analyse`
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
# Giờ ngay sau ngày trên cùng dòng; sau ngày thì nhận cả `12.30` (MB in giờ bằng dấu chấm) và `10:.35` (OCR đọc dư dấu).
# Không để hai `\s*` liền nhau (bậc hai trên dãy khoảng trắng dài): khoảng trắng sau từ nối nằm trong nhóm tùy chọn.
DATE_TIME_RE = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\s*(?:(?:luc|-|,)\s*)?([01]?\d|2[0-3])\s?[:.]{1,2}\s?([0-5]\d)(?!\d)")
# Luật `a3` (A3, 23/11/2026), rút từ 42 ảnh có dấu hiệu tiền trên máy có Zalo. Dấu hiệu giao dịch ĐÃ XONG: thiếu thì không "chắc" (bảng kê
# hóa đơn, đề nghị thanh toán, mã QR, màn nhập người hưởng có số tiền và tên ngân hàng mà tiền chưa đi). "Transaction successful",
# "Transaction confirmed", "Đã phê duyệt" có trên ảnh thật; các cụm "thành công" đã có trong từ khóa ngân hàng từ P0; các cụm còn lại thêm
# theo review #599 (biên lai phổ biến). Một chữ "thành công" đứng riêng cũng là đã xong: chỉ để nâng ảnh lên "chắc" khi đủ các điều khác.
DONE = ("thanh cong", "successful", "payment successful", "transfer completed", "transaction completed", "transaction confirmed",
        "da phe duyet", "da chuyen tien")
IN_WORDS = ("nhan tien", "tien vao", "da nhan", "ghi co", "received", "credited")
OUT_WORDS = ("chuyen tien", "chuyen khoan", "money transfer", "nguoi thu huong", "nguoi huong", "beneficiary", "ghi no", "debited")
# Nhãn giờ giao dịch theo thứ tự ưu tiên: màn duyệt của ngân hàng doanh nghiệp có "Ngày yêu cầu" và "Ngày phê duyệt", tiền đi lúc duyệt.
TIME_LABELS = ("thoi gian giao dich", "ngay giao dich", "transaction time", "transaction date", "ngay phe duyet", "thoi gian", "ngay gio")
REF_LABELS = ("ma giao dich", "so giao dich", "so tham chieu", "ma tham chieu", "reference number", "reference no", "transaction id",
              "transfer code", "ma gd", "so gd")


def words(phrases) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(k) for k in sorted(phrases, key=len, reverse=True)) + r")(?![a-z0-9])")


DONE_RE, IN_RE, OUT_RE, REF_LABEL_RE = words(DONE), words(IN_WORDS), words(OUT_WORDS), words(REF_LABELS)
# Dòng có nhãn mã giao dịch mà cũng là tài khoản hay lời nhắn (ô "Nội dung" ghép dòng, "nội dung: ma gd ...") thì không lấy mã.
REF_SKIP = re.compile(r"tai khoan|account|noi dung|loi nhan|dien giai|ghi chu|content|message|description|remark")
PHONE = re.compile(r"(?:84|0)[35789]\d{8}")   # số di động Việt Nam: không bao giờ là mã giao dịch
# Ký hiệu tiền khác VND trong ô số hoặc ô sát bên cùng hàng: số đó không bao giờ là `amount_vnd` (ảnh WeChat có ô "USD 67,435.89").
FOREIGN = {"USD": re.compile(r"(?<![a-z])usd(?![a-z])|us\$|\$\s?\d|\d\s?\$|^\s*\$\s*$"), "CNY": re.compile(r"(?<![a-z])(?:cny|rmb)(?![a-z])|¥|￥|人民币|元"),
           "EUR": re.compile(r"(?<![a-z])eur(?![a-z])|€")}


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
                self.cached = f"{metadata.version('easyocr')}+{PREPARE}"   # không import easyocr chỉ để biết phiên bản; nhớ vì step() hỏi mỗi giây
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


def lines(boxes: list[dict]) -> list[str]:
    """Các dòng chữ đã bỏ dấu theo thứ tự đọc (trên xuống, trái sang): ô có tâm dọc nằm trong chiều cao của ô đầu dòng thì cùng dòng. OCR hay
    tách một nhãn thành vài ô lệch thứ tự (`Đã`, `duyệt`, `phê`): ghép theo dòng thì đọc lại đúng."""
    rows: list[list[dict]] = []
    for box in sorted(boxes, key=lambda item: (item["b"][1] + item["b"][3], item["b"][0])):
        middle = (box["b"][1] + box["b"][3]) / 2
        row = next((row for row in rows if row[0]["b"][1] <= middle <= row[0]["b"][3]), None)
        if row is None:
            rows.append([box])
        else:
            row.append(box)
    return [" ".join(fold(box["t"]).strip() for box in sorted(row, key=lambda item: item["b"][0])) for row in rows]


def stamp(day: int, month: int, year: int, hour: int | None = None, minute: int | None = None) -> str | None:
    """ISO 8601 +07:00 (chỉ có ngày thì `YYYY-MM-DD`), hoặc None khi ngày không hợp lệ."""
    try:
        moment = datetime(year, month, day)
    except ValueError:
        return None
    return moment.date().isoformat() if hour is None else moment.replace(hour=hour, minute=minute).isoformat() + "+07:00"


def pair(line: str) -> str | None:
    """Ngày kèm giờ trên CÙNG một dòng: giờ ngay sau ngày (`19/11/2026 15:02`, `05/11/2026 12.30`) hoặc giờ có dấu `:` ở chỗ khác của dòng."""
    found = DATE_TIME_RE.search(line)
    if found:
        return stamp(int(found[1]), int(found[2]), int(found[3]), int(found[4]), int(found[5]))
    day, clock = DATE_RE.search(line), TIME_RE.search(line)
    return stamp(int(day[1]), int(day[2]), int(day[3]), int(clock[1]), int(clock[2])) if day and clock else None


def when(rows: list[str] | str) -> str | None:
    """Giờ giao dịch (ISO +07:00, hoặc `YYYY-MM-DD` khi chỉ có ngày), hoặc None. Ưu tiên dòng có nhãn thời gian giao dịch (thứ tự
    `TIME_LABELS`), rồi dòng đầu tiên có cả ngày lẫn giờ, rồi ngày đầu tiên. Không ghép ngày của dòng này với giờ của dòng khác (đồng hồ thanh
    trạng thái, giờ yêu cầu khác giờ duyệt). Chỉ nhận ngày giờ hợp lệ."""
    rows = [rows] if isinstance(rows, str) else rows
    for label in TIME_LABELS:
        for row in rows:
            if label in row and (found := pair(row)):
                return found
    for row in rows:
        if found := pair(row):
            return found
    for row in rows:
        day = DATE_RE.search(row)
        if day and (found := stamp(int(day[1]), int(day[2]), int(day[3]))):
            return found
    return None


def reference(rows: list[str]) -> str | None:
    """Mã giao dịch (chữ in hoa) **ngay sau** nhãn mã giao dịch trên cùng dòng (nhãn theo thứ tự `REF_LABELS`): 6-30 ký tự chữ-số, ít nhất
    6 chữ số và nhiều nhất 4 chữ cái (`FT...`, dãy số tham chiếu), không có dạng số di động. Dòng nhắc tới tài khoản, nội dung, lời nhắn thì
    bỏ: không lấy nhầm số tài khoản, số điện thoại hay tên trong lời nhắn. Chỉ lưu trong kho tại máy, không xuất (review #599)."""
    for label in REF_LABELS:
        for row in rows:
            found = REF_LABEL_RE.search(row)
            if not found or found[1] != label or REF_SKIP.search(row):
                continue
            token = re.match(r"[A-Za-z0-9]+", row[found.end():].lstrip(" :.#-"))
            value = token[0] if token else ""
            digits, letters = sum(ch.isdigit() for ch in value), sum(ch.isalpha() for ch in value)
            if 6 <= len(value) <= 30 and digits >= 6 and letters <= 4 and not PHONE.fullmatch(value):
                return value.upper()
    return None


def direction(boxes: list[dict], rows: list[str], amount: int | None) -> str | None:
    """`in` (tiền vào), `out` (tiền ra) hoặc None, theo góc nhìn người chụp ảnh. Dấu +/− dính ô số tiền đứng đầu thắng; không có dấu thì theo
    từ ngữ, có cả hai phía hoặc không phía nào thì None. Chỉ là thông tin: `hao` chưa dùng để đếm hay đổi chiều thu/chi."""
    if amount is not None:
        for box in boxes:
            for match in AMOUNT_RE.finditer(box["t"]):
                sign = match[0].lstrip()[:1]
                if sign not in ("+", "-"):   # dấu trừ Unicode (−, –) đứng trước số: AMOUNT_RE chỉ nhận + và - ASCII
                    sign = "-" if box["t"][:match.start()].rstrip()[-1:] in ("−", "–") else ""
                if sign in ("+", "-") and int(re.sub(r"\D", "", match[1] or match[3])) == amount:
                    return "in" if sign == "+" else "out"
    text = " ".join(rows)
    incoming, outgoing = bool(IN_RE.search(text)), bool(OUT_RE.search(text))
    return "in" if incoming and not outgoing else "out" if outgoing and not incoming else None


def beside_unit(boxes: list[dict], index: int, folded: list[str]) -> bool:
    """Chữ VND/đ nằm thành ô riêng ngay bên phải cùng hàng với ô số."""
    x0, y0, x1, y1 = boxes[index]["b"]
    return any(folded[j] in ("vnd", "d") and boxes[j]["b"][0] >= x0 + (x1 - x0) / 2 and abs((boxes[j]["b"][1] + boxes[j]["b"][3]) - (y0 + y1)) <= (y1 - y0)
               for j in range(len(boxes)) if j != index)


def foreign(boxes: list[dict], index: int, folded: list[str]) -> str | None:
    """Mã tiền khác VND (`USD`, `CNY`, `EUR`) ghi trong ô số hoặc ô cùng hàng sát bên trái/phải (cách không quá một chiều cao ô), hoặc None."""
    x0, y0, x1, y1 = boxes[index]["b"]
    near = [index] + [j for j in range(len(boxes)) if j != index and abs((boxes[j]["b"][1] + boxes[j]["b"][3]) - (y0 + y1)) <= (y1 - y0)
                      and (0 <= boxes[j]["b"][0] - x1 <= y1 - y0 or 0 <= x0 - boxes[j]["b"][2] <= y1 - y0)
                      and "vnd" not in folded[j]]   # ô sát bên ghi cả VND ("Amount (USD/VND)") không quyết được đơn vị
    return next((code for j in near for code, pattern in FOREIGN.items() if pattern.search(folded[j])), None)


def analyse(boxes: list[dict]) -> dict:
    """Từ các ô chữ: có dấu hiệu tiền không, số tiền ứng viên đứng đầu (ô to nhất, ưu tiên có VND/đ), độ tin cậy ô đó, số từ khóa,
    có đúng một ứng viên đứng đầu không, giờ và ngân hàng (nếu thấy); từ luật `a3` thêm `done` (có dấu hiệu giao dịch đã xong), `direction`,
    `txn_ref` (mã giao dịch) và `currency` (đơn vị của số đứng đầu: `VND`, `USD`, `CNY`, `EUR` hoặc None khi không ghi). Số đứng đầu mang đơn vị
    khác VND thì `amount_vnd` là None. Không có số ứng viên nào thì không phải ảnh tiền (`is_money` sai). Không quyết "chắc hay không": xem `is_confident`."""
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
            other = None if unit else foreign(boxes, index, folded)
            candidates.append({"value": value, "score": height * weight, "confidence": box["c"], "currency": other or ("VND" if unit else None)})
    best = max(candidates, key=lambda item: item["score"], default=None)
    rivals = [item for item in candidates if best and item["value"] != best["value"] and item["score"] >= RIVAL * best["score"]]
    rows = lines(boxes)
    vnd = best is not None and best["currency"] in ("VND", None)
    amount = best["value"] if vnd else None
    done = bool(DONE_RE.search(" ".join(rows)))
    # Dấu hiệu tiền cần một số ứng viên (A3): màn "Thông tin người hưởng" có từ khóa mà không có số nào thì không phải ảnh tiền chờ xem.
    # Trừ khi ảnh có dấu hiệu giao dịch đã xong và đủ từ khóa: biên lai thật mà OCR làm rơi dấu chấm ("5000000", "VND" ô riêng) vẫn chờ người xem.
    signal = len(hits) >= 2 or with_unit or any(item["currency"] not in ("VND", None) for item in candidates)
    return {"is_money": (bool(candidates) and signal) or (done and len(hits) >= 2), "amount_vnd": amount,
            "confidence": best["confidence"] if vnd else None, "currency": best and best["currency"],
            "hits": len(hits), "unique": not rivals, "txn_time": when(rows), "bank": bank,
            "done": done, "direction": direction(boxes, rows, amount), "txn_ref": reference(rows)}


def stamped(boxes: list[dict]) -> dict:
    """Kết quả phân tích ô chữ kèm phiên bản luật đã dùng: phần ghi vào kho cạnh ô chữ."""
    return {**analyse(boxes), "analysis": ANALYSIS}


def refresh(read: dict | None) -> dict | None:
    """Lượt đọc OCR với kết quả theo luật phân tích hiện tại. Đã đúng `ANALYSIS` (hoặc không có ô chữ, như lượt đọc của Gemini) thì trả
    nguyên đối tượng; lệch thì trả đối tượng mới = phần của engine + `analyse` chạy lại trên ô chữ đã lưu. Không gọi engine, không ghi đĩa."""
    if not read or not isinstance(read.get("boxes"), list) or read.get("analysis", LEGACY_ANALYSIS) == ANALYSIS:
        return read
    return {**{key: read[key] for key in ENGINE_FIELDS if key in read}, **stamped(read["boxes"])}


def is_confident(read: dict, limit: Decimal | float | None = None) -> bool:
    """"OCR chắc" (ANH-GEMINI-01): ô số tiền đủ tin cậy, >= 2 từ khóa ngân hàng, một ứng viên đứng đầu, và (luật `a3`) có dấu hiệu giao
    dịch đã xong (`done`). Tính từ trường đã lưu nên đổi T không cần đọc lại ảnh; lượt đọc theo luật cũ chưa có `done` thì phải qua `refresh`."""
    limit = threshold() if limit is None else limit
    return bool(read.get("is_money") and read.get("amount_vnd") and (read.get("confidence") or 0) >= limit
                and read.get("hits", 0) >= 2 and read.get("unique") and read.get("done"))


def verdict(read: dict | None) -> str:
    """none = không dấu hiệu tiền (không rời máy); ocr = OCR chắc; unsure = có dấu hiệu tiền mà OCR không chắc."""
    if not read or not read.get("is_money"):
        return "none"
    return "ocr" if is_confident(read) else "unsure"
