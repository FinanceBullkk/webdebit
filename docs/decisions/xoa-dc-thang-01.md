# XOA-DC-THANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng cho **xóa dòng điều chỉnh cả tháng** trên sổ V7, thay vế "Dòng đã ghi không có nút sửa/xóa; sai thì thêm dòng ngược dấu" của điều 11 trong [`specs/v7-so-khach-theo-sheet.md`](../../specs/v7-so-khach-theo-sheet.md). Claude chốt cách làm theo quyền điều phối ngày 21/10, theo khuôn xóa tại ô của [`NHAP-SHEET-01`](nhap-sheet-01.md) và [`XOA-THU-GOC-01`](xoa-thu-goc-01.md):

1. Tháng đang mở: bấm ô số tiền của dòng "Điều chỉnh cả tháng" → hỏi xác nhận → **Xóa hẳn**. Tháng khóa không có nút; mở khóa trước (như lúc thêm điều chỉnh cả tháng).
2. Xóa là thêm một dòng đảo dấu trỏ về dòng gốc; bảng điều chỉnh vẫn chỉ thêm, không sửa/xóa hàng. Cặp gốc + đảo cùng tháng, tổng 0, và **cả hai ẩn khỏi sổ**. Nợ tháng bỏ đúng số của dòng; phân bổ lại phiếu chưa hủy theo nợ cũ trước.
3. Lịch sử ghi "Xóa điều chỉnh cả tháng", số và ghi chú của dòng → 0, người làm. Không có nút hoàn tác; muốn lại thì thêm điều chỉnh mới.
4. Chỉ dòng điều chỉnh cả tháng. Điều chỉnh chuyến, điều chỉnh do sửa/xóa dòng sổ gốc và phần chênh khi sửa giá tháng khóa không xóa theo lối này.

## Ngày / nguồn

29/10/2026, chat: người dùng hỏi hai dòng "Điều chỉnh cả tháng · test" (100 và −100) có xóa được không, rồi chọn "Cho xóa".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Code: hàm `delete_month_adjustment`, cột `adjustment.reverses_adjustment_id`, loại sự kiện `adjust_month_delete`, migration `2026-10-29-v7-xoa-dieu-chinh-thang.sql` (chạy sau `2026-10-29-v7-chung-tu.sql`), API `POST /api/v7/months/adjust/delete`, UI sổ khách. Có migration nên phải triển khai tay trên `hao` theo runbook; CHƯA TRIỂN KHAI. Hai dòng thử đã ghi trước đó chỉ ẩn được sau khi migration chạy.
