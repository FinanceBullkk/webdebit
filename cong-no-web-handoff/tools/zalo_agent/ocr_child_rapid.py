"""ZALO-AGENT-01 Phần 3: tiến trình con OCR thứ hai, `rapidocr-onnxruntime` (PP-OCR ONNX), cùng giao thức với `ocr_child.py`.

Dùng làm "lần đọc thứ hai" cạnh easyocr (số đo 23/11/2026): hai engine độc lập cùng ra một số tiền thì chắc hơn một engine
tin cậy thấp. Giao thức y hệt `ocr_child.py`: mỗi dòng stdin `{"path": "<PNG>"}`, mỗi dòng trả lời `{"boxes": [{b, t, c, p}]}` hoặc
`{"error": "unavailable" | "model_missing" | "bad_request" | "failed"}`; kênh trả lời là bản sao của fd 1 lấy trước khi nạp thư viện, fd 1 và
`sys.stdout` nối sang stderr. Khác easyocr: model ONNX nằm trong wheel `rapidocr-onnxruntime` nên **không có gì để tải** (thiếu file model là
`model_missing`), và số luồng đặt bằng cách bọc `onnxruntime.SessionOptions` trước khi nạp `rapidocr_onnxruntime` (thư viện nhận `**kwargs` nhưng
bỏ qua tham số luồng, mặc định dùng hết nhân). Ảnh vào là PNG đã thu nhỏ của agent; RapidOCR nhận mảng BGR.

Chỉ dùng thư viện chuẩn trước khi nạp onnxruntime, không import gì của `zalo_agent`.
"""
import json
import os
import sys
from decimal import Decimal


def main() -> int:
    channel = os.fdopen(os.dup(1), "wb")   # kênh trả lời: bản sao của stdout gốc
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    threads = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
    engine = None

    def reply(value: dict) -> None:
        channel.write(json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n")
        channel.flush()

    for line in sys.stdin.buffer:
        try:
            path = json.loads(line)["path"]
        except (ValueError, KeyError, TypeError):
            reply({"error": "bad_request"})
            continue
        if engine is None:
            try:
                import numpy
                import onnxruntime
                from PIL import Image

                def limited(original=onnxruntime.SessionOptions):   # máy 6 nhân: để dành phần còn lại cho Zalo PC và live-sync
                    options = original()
                    options.intra_op_num_threads, options.inter_op_num_threads = threads, 1
                    return options

                onnxruntime.SessionOptions = limited   # trước khi nạp rapidocr_onnxruntime (nó `from onnxruntime import SessionOptions`)
                from rapidocr_onnxruntime import RapidOCR
                engine = RapidOCR()
            except FileNotFoundError:
                reply({"error": "model_missing"})
                return 0
            except Exception:  # noqa: BLE001  (ImportError, OSError nạp DLL, thiếu bộ nhớ…: máy này chưa đọc OCR được)
                reply({"error": "unavailable"})
                return 0
        try:
            with Image.open(path) as source:
                rgb = numpy.asarray(source.convert("RGB"))
            found, _ = engine(numpy.ascontiguousarray(rgb[:, :, ::-1]))
            boxes = []
            for points, text, confidence in found or []:
                corners = [[int(round(point[0])), int(round(point[1]))] for point in points][:4]  # noqa: RUF046
                xs, ys = [corner[0] for corner in corners], [corner[1] for corner in corners]
                score = min(Decimal(1), max(Decimal(0), Decimal(str(confidence))))   # RapidOCR trả chuỗi hoặc số thực tùy phiên bản
                boxes.append({"b": [min(xs), min(ys), max(xs), max(ys)], "t": str(text), "c": int(round(score * 1000)) / 1000, "p": corners})  # noqa: RUF046
            reply({"boxes": boxes})
        except Exception:  # noqa: BLE001
            reply({"error": "failed"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
