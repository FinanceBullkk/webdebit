"""ZALO-AGENT-01 Phần 3: tiến trình con OCR, sống lâu, chạy `easyocr` thay cho agent (review M7).

Torch hay thư viện gốc có thể chết bằng lỗi native hoặc hết bộ nhớ; chạy ở tiến trình riêng thì agent (bundle, insurance, nhịp tim) không
chết theo. Giao thức: mỗi dòng stdin là một yêu cầu JSON `{"path": "<ảnh PNG đã thu nhỏ>"}`, mỗi dòng trả lời là đúng một JSON
`{"boxes": [{"b": [x0, y0, x1, y1], "t": chữ, "c": độ tin cậy, "p": [[x, y] × 4]}]}` (`p` là 4 góc theo thứ tự trên-trái, trên-phải, dưới-phải,
dưới-trái, để biết ô có nghiêng không) hoặc `{"error": mã}` với mã là `unavailable` (thiếu thư viện, lỗi nạp DLL), `model_missing` (chưa có model ở
`~/.EasyOCR`; **không tự tải**, `download_enabled=False`), `bad_request` hoặc `failed` (riêng ảnh đó). Tọa độ luôn là số nguyên Python (easyocr trả
số của numpy, `json` không in được). Nạp thư viện và model ở yêu cầu đầu tiên. Thiếu thư viện hay model thì trả lời rồi thoát; stdin đóng (agent
chết) thì thoát.

Kênh trả lời là một **bản sao của fd 1 lấy trước khi import torch**, rồi fd 1 và `sys.stdout` được nối sang stderr: mọi thứ thư viện (kể cả mã
native) in ra stdout đều đi chỗ khác, không chen vào giao thức. Tệp này chỉ dùng thư viện chuẩn trước khi nạp easyocr, không import gì của `zalo_agent`.
"""
import json
import os
import sys


def main() -> int:
    channel = os.fdopen(os.dup(1), "wb")   # kênh trả lời: bản sao của stdout gốc
    os.dup2(2, 1)                          # fd 1 (kể cả của mã native) nối sang stderr
    sys.stdout = sys.stderr
    threads = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
    reader = None

    def reply(value: dict) -> None:
        channel.write(json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n")
        channel.flush()

    for line in sys.stdin.buffer:
        try:
            path = json.loads(line)["path"]
        except (ValueError, KeyError, TypeError):
            reply({"error": "bad_request"})
            continue
        if reader is None:
            try:
                import easyocr
                import numpy
                import torch
                from PIL import Image
                torch.set_num_threads(threads)   # máy 6 nhân: để dành phần còn lại cho Zalo PC và live-sync
                reader = easyocr.Reader(["vi", "en"], gpu=False, verbose=False, download_enabled=False)
            except FileNotFoundError:
                reply({"error": "model_missing"})
                return 0
            except Exception:  # noqa: BLE001  (ImportError, OSError nạp DLL, thiếu bộ nhớ…: máy này chưa đọc OCR được)
                reply({"error": "unavailable"})
                return 0
        try:
            with Image.open(path) as source:
                found = reader.readtext(numpy.asarray(source.convert("RGB")))
            boxes = []
            for points, text, confidence in found:
                # `int(...)` rõ ràng dù `round` đã trả số nguyên: easyocr trả tọa độ numpy, `json.dumps` không in được np.int32/np.float32
                corners = [[int(round(point[0])), int(round(point[1]))] for point in points][:4]  # noqa: RUF046
                xs, ys = [corner[0] for corner in corners], [corner[1] for corner in corners]
                boxes.append({"b": [min(xs), min(ys), max(xs), max(ys)], "t": str(text), "c": int(round(confidence * 1000)) / 1000, "p": corners})  # noqa: RUF046
            reply({"boxes": boxes})
        except Exception:  # noqa: BLE001
            reply({"error": "failed"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
