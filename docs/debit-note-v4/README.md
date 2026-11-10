# Gói thiết kế debit note HTH v4.0 (1 trang A4 ngang)

Giải nén vào repo WebDebit tại `docs/debit-note-v4/`.

- `SPEC.md`: đặc tả, đọc trước tiên. Gồm quy tắc dữ liệu, cột, định dạng, sang trang, 6 phép kiểm tra và tiêu chí nghiệm thu.
- `reference/`: trang HTML tĩnh khổ A4 ngang (nguồn sự thật về giao diện), kèm ảnh PNG (2×) và PDF render từ chính các trang đó.
  - `1-trang-14-container`: mẫu chuẩn.
  - `30-container-trang-1` / `-trang-2`: ví dụ sang trang.
  - `8-container-an-cot-HC-fee`: ví dụ ẩn cột phí có tổng bằng 0.
  - `guideline-v4.0.pdf`: design guideline.
- `data/`: dữ liệu mẫu (không phải dữ liệu thật) và kết quả mong đợi để viết test. Trường `null` nghĩa là chưa có dữ liệu, in ra dạng `[Tên trường]`.

Mở file HTML bằng Chrome để xem. In thử: Ctrl+P, khổ A4 ngang, lề 0, bật "Background graphics".

## Bản trong repo

Repo public nên bản trong repo đã bỏ thông tin ngân hàng: trong `reference/*.html`, người thụ hưởng, ngân hàng, số tài khoản và SWIFT thay bằng `[Beneficiary]`, `[Bank]`, `[Account no.]`, `[SWIFT code]`; SPEC mục 8 không ghi tên người thụ hưởng. Ảnh chuẩn `reference/*.png`, `*.pdf` và `guideline-v4.0.pdf` có số tài khoản nên **không** đưa vào repo; bản đầy đủ nằm ngoài git ở `D:\webdebit\design\debit-note-v4\` (máy MSI). Test so ảnh đọc thư mục đó qua biến `DEBIT_NOTE_V4_REFERENCE`, không có thì bỏ qua phần so ảnh.
