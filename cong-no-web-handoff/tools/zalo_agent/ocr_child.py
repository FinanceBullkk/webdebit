"""ZALO-AGENT-01 Phần 3: tiến trình con OCR, sống lâu, chạy `easyocr` thay cho agent (review M7).

Torch hay thư viện gốc có thể chết bằng lỗi native hoặc hết bộ nhớ; chạy ở tiến trình riêng thì agent (bundle, insurance, nhịp tim) không
chết theo. Giao thức: mỗi dòng stdin là một yêu cầu JSON `{"path": "<ảnh PNG đã thu nhỏ>"}`, mỗi dòng stdout là đúng một câu trả lời JSON
`{"boxes": [{"b": [x0, y0, x1, y1], "t": chữ, "c": độ tin cậy}]}` hoặc `{"error": mã}` với mã là `unavailable` (thiếu thư viện, lỗi nạp DLL),
`model_missing` (chưa có model ở `~/.EasyOCR`; **không tự tải**, `download_enabled=False`), `bad_request` hoặc `failed` (riêng ảnh đó). Nạp thư
viện và model ở yêu cầu đầu tiên. Thiếu thư viện hay model thì trả lời rồi thoát; stdin đóng (agent chết) thì thoát. Mọi thứ thư viện in ra bị đưa sang
stderr để không làm hỏng giao thức. Tệp này chỉ dùng thư viện chuẩn trước khi nạp easyocr, không import gì của `zalo_agent`.
"""
import json
import sys


def main() -> int:
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    threads = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2
    reader = None

    def reply(value: dict) -> None:
        out.write(json.dumps(value, ensure_ascii=False).encode("utf-8") + b"\n")
        out.flush()

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
                xs, ys = [point[0] for point in points], [point[1] for point in points]
                boxes.append({"b": [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))], "t": str(text),
                              "c": round(confidence * 1000) / 1000})
            reply({"boxes": boxes})
        except Exception:  # noqa: BLE001
            reply({"error": "failed"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
