# Kiểm chứng thay đổi ngày 15/10/2026

## Harness PostgreSQL schema ghi sổ — nhánh phụ thuộc PR #2

Nhánh `test/pg18-schema-characterization` bắt đầu từ `315d2d150d17ac77cda31f0ef3b61f696cd20ea5`, cùng head PR #2 khi bắt đầu. Commit nhánh: `2317553f3cadd40f87e754714fbd203ff1844ad5`; draft PR #3 phụ thuộc PR #2. PR #2 vẫn mở tại head `315d2d150d17ac77cda31f0ef3b61f696cd20ea5` ở lần đối chiếu cuối. SHA-256 schema `cong-no-web-handoff/tools/pg_ledger_schema.sql` theo nội dung LF chuẩn hóa: `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`. Runner chuẩn hóa CRLF/LF trước hash và nạp chính nội dung đó, để revision giống nhau có cùng hash trên Windows/Linux. PostgreSQL image được pin `postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`; registry trả HTTP 200 cho manifest digest này.

Runner: `python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report <path>`. Mỗi lượt dùng volume/container riêng có run-id label, `--network none`, không publish port; database đích duy nhất là `webdebit_ledger`. SQL gốc được truyền nguyên bản với `ON_ERROR_STOP`. Fixture toàn bộ là giả. Báo cáo JSON giữ expected/actual, SQLSTATE và số posting/status/audit sau mỗi case. Schema không có receipt entity/allocation ledger riêng; kiểm allocation cùng receipt được để lại cho task sau Q03–Q04.

CI mới nhất đã kiểm tra: run [38686910554](https://github.com/FinanceBullkk/webdebit/actions/runs/38686910554), workflow `Tests`, source head `e50451a2f69f83e1d2e4f9058dc9be39e7a61cf8`; trạng thái tổng thể và cả 7 job đều success. Artifact `pg-ledger-characterization` có 9 assertion trên PostgreSQL 18.6; report revision là merge commit CI `62e9da42059329508ba746174980fd60535343c7`, schema SHA-256 LF-normalized giữ nguyên `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`, image digest giữ nguyên ở trên. Cleanup được xác minh `verified_and_removed`, container ID đầy đủ được ghi trong artifact, runner exit 0. Năm characterization, atomicity và hai contention assertion là `pass`; stale-content assertion là `repro_success`, tái hiện submit 100 rồi checker post 101. `repro_success` chỉ là tái hiện defect, không là acceptance. Xem [artifact/run](https://github.com/FinanceBullkk/webdebit/actions/runs/38686910554) để biết chi tiết SQLSTATE, counts và `pg_blocking_pids`.

Lượt CI trên commit trung gian `566cc7d` (run `38686717095`) phát hiện `docker ps --quiet` rút container ID còn 12 ký tự; kiểm tra identity vì vậy từ chối cleanup an toàn và report ghi `cleanup: failed`. Đã sửa discovery với `--no-trunc`; run `38686910554` trên `e50451a` xác nhận lại 9 assertion và cleanup `verified_and_removed`. Đây là kiểm lỗi harness, không phải lỗi characterization PostgreSQL.

Giới hạn vẫn vậy: đây là CI PostgreSQL trên revision được nêu, không phải kiểm Docker local hay DB/service thật. Report trước đó từ run `38684269409`, `38683750234` và các kiểm local bên dưới được giữ làm lịch sử; kết quả mới không đổi giới hạn của chúng.

| Kiểm lịch sử | Kết quả thực chạy |
|---|---|
| `py_compile` runner (Python 3.13.6) | Đạt. |
| `git diff --check` | Đạt. |
| `python -m unittest discover -s tests -v` trong `cong-no-web-handoff/` | 23/23 đạt. Đây là fixture suite hiện có, tách biệt PostgreSQL. |
| Runner local trên Windows | Exit 1 đúng kỳ vọng fail-closed; report run `e176f428ad934d5a953b51811fd8473f`, không tạo container/volume và không chạy DDL. Docker Desktop process đã mở nhưng daemon named pipe không có; service `com.docker.service` không thể khởi động do quyền môi trường. PostgreSQL local chưa được kiểm. |
| PostgreSQL 18.6 CI job | Run `38683750234`, report run-id `fc86c8db1b99483f9a570f78d57b9a94`, GitHub PR merge revision `b8ac417ae6f6aa2beaa5fe3456dda6a87589464e` (branch commit `2317553f3cadd40f87e754714fbd203ff1844ad5`). `version()`: PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2), x86_64. Image digest: `sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`. Lệnh: `python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report pg-ledger-characterization.json`. Runner exit 0; container ID `1079978b0cc02025fac80f665341371c3897f0ee5810fcac2b3265214e64dcf4`; cleanup `verified_and_removed`. Artifact: [workflow run](https://github.com/FinanceBullkk/webdebit/actions/runs/38683750234). |

Các assertion CI trên PostgreSQL 18.6 ở run `38683750234`: characterization 5/5 đạt; defect repro `owner_mutation_after_submit_posts_unreviewed_content` có nhãn `repro_success` — đã submit 100, sau owner mutation checker post 101; atomicity trigger lỗi với SQLSTATE `P0001` và proposal vẫn `pending`, 0 posting, 0 approval audit; contention 2 checker sessions được quan sát bằng `pg_blocking_pids` (`420:{392}`, `421:{420}`), đúng một call thành công, call còn lại `P0001`, đúng 1 posting. Đây là mô tả baseline; defect repro không phải acceptance đạt. Không test chung receipt vì schema không có receipt entity/allocation ledger riêng. Nếu PR #2 đổi schema trước merge/chạy lại, so diff và chạy job trên revision mới.

**Kết luận lịch sử:** PostgreSQL thật đã chạy và chứng cứ nêu trên thuộc revision CI được ghi. Cả 7 job của workflow (PostgreSQL riêng, Python 3.12/3.13 Windows/Linux, JavaScript Windows/Linux) đều pass trên run `38683750234`; JavaScript Windows hoàn tất sau 4m57s. Máy local vẫn chưa kiểm PostgreSQL vì Docker daemon không khởi động; report fail-closed local không thay thế CI. Trạng thái CI mới nhất được ghi ở đầu mục này.

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
