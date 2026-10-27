# V7: hàng chờ Sheet qua năm mới, giải quyết lệch ngày/booking

Trạng thái: ĐÃ CHỐT phạm vi sửa lỗi (người dùng yêu cầu trong chat 27/10/2026; Claude chốt chi tiết theo quyền người dùng trao 21/10/2026). Không đổi luật tiền.

## Bối cảnh

1. `v7_sheet_queue.py` chỉ nhận dòng Sheet năm 2026. Từ 01/01/2027 mọi chuyến mới chỉ còn là con số `skipped_out_of_scope`, không vào hàng chờ duyệt.
2. Hàng chờ báo lệch `event_date` và `booking`, nhưng API/hàm `resolve_sheet_conflict` chỉ nhận hãng tàu, shipper, nơi đi, nơi đến. Dòng lệch ngày/booking nằm mãi ở trạng thái KHÁC, không có nút xử lý.
3. Phát hiện thêm khi sửa: "Lấy Sheet" của bốn trường cũ ghi đè chuyến mà không kiểm ổ khóa tháng, trái mục [Cập nhật khóa tháng 24/10/2026](../docs/decisions.md#cập-nhật-khóa-tháng-24102026).

## Đầu ra

- Hàng chờ: giữ mốc dưới `QUEUE_FIRST_YEAR = 2026` (dòng trước đó thuộc số dư đầu), bỏ mốc trên. Dòng ngoài phạm vi vẫn được đếm.
- Lệch **booking**: chỉ "Giữ booking đã ghi" (`keep_web`), theo [`BOOKING-EDIT-01`](../docs/decisions.md#booking-edit-01). Chỉ áp cho chuyến web; dòng sổ gốc không có booking.
- Lệch **ngày**: "Giữ web" ghi `sheet_conflict_resolved`, không đổi chuyến. "Lấy Sheet" không đi qua `resolve_sheet_conflict` mà mở ô ngày và lưu như gõ tay (`edit_trip_info`/`edit_legacy_trip`). Nhờ vậy vẫn hỏi lại khi sang tháng khác, chặn tháng khóa, phân bổ lại và ghi Lịch sử như `NHAP-SHEET-01`. Tháng đang khóa thì báo mở khóa, không gửi lệnh.
- `resolve_sheet_conflict` (migration `2026-10-27-v7-sheet-conflict-date-booking.sql`, chỉ thay hàm): nhận thêm `event_date`, `booking` với `keep_web`; từ chối `use_sheet` cho hai trường này; `use_sheet` của bốn trường cũ gọi `_month_open`.

## Kiểm

- `npm run check`: test hàng chờ qua năm, API từ chối `use_sheet` ngày/booking, Playwright cho nút booking và "Lấy Sheet" ngày (tháng mở và tháng khóa).
- Harness PostgreSQL (`test_pg_v7_backend.py`, case `CSM.03`): áp hai migration Sheet trên bản sao theo thứ tự `hao`, kiểm `keep_web` ngày/booking không đổi chuyến hay số dư, từ chối `use_sheet`, `use_sheet` tháng khóa bị `MONTH_LOCKED`.

## CÒN MỞ

- `resolve_sheet_conflict` và ràng buộc `sheet_conflict_resolved` chưa có trong file chuẩn `schema-draft.sql`/`v7_backend_functions.sql` (có từ 25/10, chỉ ở migration). Harness kiểm trên bản sao migration.
- Chưa triển khai `hao`: cần backup, chạy migration theo runbook và người dùng cho phép.
