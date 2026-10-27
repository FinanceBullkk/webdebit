# V7: sync shipper qua các hàm ghi, mở lại dán chuyến tháng khóa, intent phí adjust_trip

Trạng thái: ĐÃ CHỐT (Claude theo nhiệm vụ audit 27/10/2026 của người dùng; phạm vi sửa lỗi P1/P2 đã báo cáo, không đổi chính sách mới)

## Bối cảnh

Audit 27/10/2026 tìm thấy ba lỗi ở chuỗi migration V7 và một lỗi ở đường đọc Sheet:

1. **P1 (regression shipper):** `2026-10-24-v7-locked-trip-edit.sql` ghi đè `edit_trip_info`, `delete_trip`, `_change_legacy`, `review_trip` của `2026-10-24-v7-shipper.sql` bằng bản không có cột `shipper`; file chuẩn `v7_backend_functions.sql` và `schema-draft.sql` cũng thiếu shipper. Dựng lại DB từ repo theo runbook sẽ làm shipper biến mất khỏi `get_ledger` ngay lần sửa/duyệt/xóa đầu tiên và dán không ghi được shipper. DB thật `hao` hiện an toàn vì migration shipper đã được chạy lại sau.
2. **P1 (dán chuyến tháng khóa):** bản `paste_trips` đang chạy trên `hao` (từ migration shipper) có `_month_open` → dán vào tháng khóa bị `MONTH_LOCKED`, trái `NHAP-SHEET-01` (7) mà mục "Cập nhật khóa tháng 24/10/2026" giữ nguyên, và trái assertion `check_locks` của chính repo. Migration shipper còn lùi `paste_trips` về bản dán theo tháng tham số, mất hành vi "chuyến vào tháng của ngày chuyến" (`NHAP-SHEET-01` (5)) đã có từ `2026-10-22-v7-nhap-sheet.sql`.
3. **P2 (mâu thuẫn chính sách review_trip):** code + test + `decisions.md` mục 24/10 nói chặn; comment SQL, comment test và dòng `NEWTRIP-01` nói không chặn. Chiều đúng là chiều 24/10 (mới nhất, ĐÃ CHỐT); các tài liệu tham chiếu cũ phải đồng bộ.
4. **P2 (intent phí adjust_trip):** `v_fee` chỉ lấy adjustment phí sau price revision mới nhất; phí cũ trước lần sửa giá vẫn nằm trong tổng tiền nên intent "phí = X" không rơi đúng số hiệu quả. `delete_trip` chụp ảnh phí theo cùng mẫu lỗi.
5. **P2 (lọc "2026" trong `v7_sheet_queue.py`):** dòng READY không chứa chuỗi "2026" bị bỏ im lặng — sang 2027, chuyến mới sẽ biến mất khỏi hàng chờ mà không ai biết.

## Đầu ra

- Migration `2026-10-27-v7-shipper-write-sync.sql`: thêm cột `shipper` (IF NOT EXISTS), định nghĩa lại `v_trip_current` và 8 hàm (`_legacy_current`, `paste_trips`, `edit_trip_info`, `delete_trip`, `_change_legacy`, `adjust_trip`, `review_trip`, `get_ledger`) đúng theo file chuẩn sau sửa.
- `schema-draft.sql` + `v7_backend_functions.sql` = trạng thái cuối kỳ vọng: có shipper ở bảng/view/hàm, `paste_trips` theo tháng từng dòng và không chặn tháng khóa, guard tháng khóa ở các hàm sửa/xóa/điều chỉnh/kết luận giữ nguyên theo quyết định 24/10.
- `adjust_trip`: phí hiệu quả = phí revision + tổng delta phí (không lọc theo event); `delete_trip` chụp ảnh theo cùng công thức, giữ NULL khi chưa từng có phí.
- `v7_sheet_queue.py`: parse năm thật từ ngày ISO, đếm dòng bị bỏ vào `skipped_out_of_scope` trả về client.
- `decisions.md`, comment SQL, comment test đồng bộ chiều "tháng khóa chặn kết luận CHỜ KIỂM".

## Hành vi và bất biến

- VND nguyên (bigint); NULL khác 0 — snapshot phí của `delete_trip` chỉ hiện 0 khi có chỉnh phí tường minh.
- Dán lô: từng chuyến vào tháng của ngày chuyến; dán vào tháng khóa KHÔNG chặn (ngoại lệ `NHAP-SHEET-01` (7)); sửa/xóa/điều chỉnh/kết luận CHỜ KIỂM tháng khóa vẫn chặn (quyết định 24/10).
- Phiếu thu: nhập/sửa/hủy tháng khóa không đổi.
- Dedup `NEWTRIP-01`, phân bổ lại FIFO, idempotency, actor phiên máy chủ: không đổi.
- `review_trip`: bắt buộc lý do, chặn tháng khóa (24/10), ghi Lịch sử.

## Giao tiếp frontend–backend

- `get_ledger` trả thêm trường `shipper` cho từng chuyến (khớp contract của migration `2026-10-26-v7-ledger-shipper-read.sql`).
- `/api/v7/sheet-queue` trả thêm `skipped_out_of_scope` (số nguyên); các trường cũ không đổi.

## Tiêu chí nghiệm thu

- [ ] `npm run test:unit` xanh (test JS về SQL `adjust_trip` cập nhật theo công thức mới).
- [ ] Harness PostgreSQL: case mới `7.26` (shipper sống qua dán/kết luận/sửa, cả trường hợp pending) và `7.27` (intent phí sau price revision: +7, sửa giá (100,30), phí=10 → tổng 110, delta −27) pass; `check_csm_migration` áp thêm migration mới hai lần và catalog hàm bằng file chuẩn; khối characterization vẫn tái lập regression và vá.
- [ ] `ruff check` sạch cho file Python thay đổi.
- [ ] Không DDL/import/deploy thật; nâng `hao` theo runbook (backup, bản sao, gate người dùng) là bước riêng ngoài PR.

## Phạm vi

- Được sửa: `specs/v7-backend/schema-draft.sql`, `cong-no-web-handoff/tools/v7_backend_functions.sql`, `cong-no-web-handoff/tools/migrations/2026-10-27-v7-shipper-write-sync.sql` (mới), `cong-no-web-handoff/tools/test_pg_v7_backend.py`, `cong-no-web-handoff/preview/test-so-khach-v7-api.js`, `cong-no-web-handoff/web/v7_sheet_queue.py`, `docs/decisions.md`.
- Cấm: DDL/import/deploy/submit thật; đổi quyền role; đổi luật tiền khác; sửa file migration đã chạy.

## Hoàn tác

Revert PR; DB thật rollback bằng restore backup trước khi áp migration mới.

## Bằng chứng

- Harness: `python cong-no-web-handoff/tools/test_pg_v7_backend.py --strict` (PostgreSQL 18.6 container dùng một lần).
- Live `hao`: chưa áp migration mới; sau khi người dùng duyệt, chạy theo `docs/v7-deploy-runbook.md` (backup → bản sao → `psql -f` → `v7_post_deploy_check.sql`).
