# Kiểm chứng thay đổi ngày 15/10/2026

## Harness PostgreSQL schema ghi sổ — nhánh phụ thuộc PR #2

Nhánh `test/pg18-schema-characterization` bắt đầu từ `315d2d150d17ac77cda31f0ef3b61f696cd20ea5`, cùng head PR #2 khi bắt đầu. SHA-256 schema `cong-no-web-handoff/tools/pg_ledger_schema.sql` theo nội dung LF chuẩn hóa: `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`. Runner chuẩn hóa CRLF/LF trước hash và nạp chính nội dung đó, để revision giống nhau có cùng hash trên Windows/Linux. PostgreSQL image được pin `postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`; registry trả HTTP 200 cho manifest digest này. Chưa có `version()` từ server trong lượt local vì daemon không khởi động.

Runner: `python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report <path>`. Mỗi lượt dùng volume/container riêng có run-id label, `--network none`, không publish port; database đích duy nhất là `webdebit_ledger`. SQL gốc được truyền nguyên bản với `ON_ERROR_STOP`. Fixture toàn bộ là giả. Báo cáo JSON giữ expected/actual, SQLSTATE và số posting/status/audit sau mỗi case. Schema không có receipt entity/allocation ledger riêng; kiểm allocation cùng receipt được để lại cho task sau Q03–Q04.

| Kiểm | Kết quả thực chạy |
|---|---|
| `py_compile` runner (Python 3.13.6) | Đạt. |
| `git diff --check` | Đạt. |
| `python -m unittest discover -s tests -v` trong `cong-no-web-handoff/` | 23/23 đạt. Đây là fixture suite hiện có, tách biệt PostgreSQL. |
| Runner local trên Windows | Exit 1 đúng kỳ vọng fail-closed; report run `e176f428ad934d5a953b51811fd8473f`, không tạo container/volume và không chạy DDL. Docker Desktop process đã mở nhưng daemon named pipe không có; service `com.docker.service` không thể khởi động do quyền môi trường. PostgreSQL local chưa được kiểm. |
| PostgreSQL 18.6 CI job | Chờ lượt CI của draft PR; chỉ ghi thành công sau khi runner hoàn tất và artifact chứa `version()`/case results. |

**Kết luận hiện tại:** characterization/defect repro/rollback/locking trên PostgreSQL thật chưa có kết quả. Kết quả fail-closed local không được diễn giải thành test PostgreSQL đạt. Nếu PR #2 đổi trước hoặc trong lượt CI, so diff của schema/task và chạy lại CI trên head mới.

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
