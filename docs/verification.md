# Kiểm chứng thay đổi ngày 15/10/2026

## Phạm vi và revision

Mã cơ sở: `69a84a41382217265f745c1c9ae87cba9e557c16` (34 file). Thay đổi hiện tại: dependency/runner/CI, hồ sơ nghiệp vụ đã lọc, cảnh báo chuyến chờ duyệt trên fixture. Diff/commit của thay đổi là ranh giới revision; kết quả dưới đây chỉ cho môi trường được nêu, không chứng minh live.

## Kết quả cục bộ

Windows, Python 3.13, Node 24.16.0, npm 12.0.2, Playwright 1.64.1, Chromium 156 (revision 1248). Dependency cài bằng lock; browser tải mới vào thư mục project riêng, không dùng cache Hermes.

| Kiểm | Kết quả thực chạy |
| --- | --- |
| Python: `python -m unittest discover -s tests -v` từ handoff trong repo | 23/23 đạt trên Python 3.13. Lần đầu dùng interpreter có sẵn tzdata; chưa đủ chứng minh Python sạch (xem lỗi CI bên dưới). Không cần DB thật. |
| `npm run test:unit` | 4 file, 16 kiểm đạt. Hai file script assertion được Node tính mỗi file là một test; không phải toàn bộ số assertion. |
| `npm run test:browser` | 4/4 đạt trong Chromium headless; không có pageerror. |
| Regression cảnh báo shipment | Trước sửa: thất bại vì không có `#pending-shipment`. Sau sửa: đạt; mở tháng/đích, lọc kỳ/ngày, số dư không đổi. |
| Model pending | Giá hợp lệ lưu thành draft, approved total vẫn null; thiếu giá tách riêng; tiền thập phân giữ lỗi và số dư không đổi. |
| Render Chromium fixture | 1440 và 500 px: scrollWidth bằng viewport; đã xem ảnh 500 px. Ảnh fixture giả không đưa vào Git. |

## Checkout mới và CI

ĐÃ KIỂM CHỨNG revision mã `75b3ecc4ee023705473cb240841097adc42c48ac` bằng clone Git mới (không hardlink), đường dẫn có dấu cách. Cài mới npm cache, `node_modules`, Chromium/headless shell; `NODE_PATH` trống. 16/16 Node và 4/4 Chromium đạt; Playwright resolve trong clone mới, Git status sạch. Python 23/23 dùng interpreter 3.13.6 toàn cục, có sẵn tzdata 2025.2: đây là giới hạn được CI phát hiện, không phải bằng chứng venv sạch.

Run CI `38677432296` trên `592c145` tái hiện `ZoneInfoNotFoundError: Asia/Ho_Chi_Minh` ở cả hai Windows/Python 3.12/3.13; Linux đạt. Sửa bằng dependency `tzdata==2026.5` khóa SHA-256, cài trong setup/CI; không thay múi giờ ứng dụng hoặc bỏ test. Kết quả venv sạch và CI của bản sửa được ghi trong PR và hồ sơ workspace.

Đã tạo venv mới, xác nhận `base_prefix != prefix` và chưa có tzdata trước cài. Cài đúng wheel/hash từ `requirements.txt` rồi chạy lại 23/23 test Python đạt. README yêu cầu venv, không còn giả định thư viện chuẩn đủ trên Windows.

Workflow định nghĩa Windows/Linux, Python 3.12/3.13 và Node 24/Chromium; trạng thái GitHub thực chạy phải đọc ở PR/commit checks. Thêm YAML không là một lượt CI đạt. Kết quả CI cuối cùng và URL run được ghi trong mô tả PR.

## Giới hạn

Không kiểm DB/service, quyền người thật, ghi tiền, migration, ngân hàng hoặc nguồn Sheet sống. Không chạy DDL/profiler trên capture. Bộ nội bộ ngoài repo có 29 test Python (đã chạy đạt trên Python 3.13), bao gồm maker/importer không thuộc repo; không cộng vào 23 test ở đây. P0 tài chính trong [sổ quyết định](decisions.md) vẫn CÒN MỞ.
