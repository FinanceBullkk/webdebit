# Cập nhật khóa tháng 24/10/2026

[← Sổ quyết định](../decisions.md)

**ĐÃ CHỐT** bởi người dùng trong chat: tháng khóa vẫn nhập/sửa phiếu thu; từ STT đến Thành tiền của bảng chuyến và dòng sổ gốc chỉ đọc. Muốn sửa, xóa chuyến, kết luận CHỜ KIỂM hoặc điều chỉnh tiền chuyến/tháng thì mở khóa trước. Chuyến mới nhập bù theo `NHAP-SHEET-01` (7) giữ ngoại lệ đã chốt. Quy tắc này thay `V7-SO` (sửa giá tháng khóa bằng điều chỉnh), `NHAP-SHEET-01` (3) và phần nhập phiếu thu tháng khóa của `SO-GON-01`. Code ở nhánh sửa lỗi; chưa triển khai hoặc kiểm trên `hao`. **Cập nhật 27/10/2026 (audit):** migration `2026-10-24-v7-locked-trip-edit.sql` đã chạy trên `webdebit_v7` (kiểm schema `hao` 27/10: các hàm ghi chuyến đều có guard tháng khóa); `2026-10-27-v7-shipper-write-sync.sql` sửa tiếp regression shipper của chuỗi migration và mở lại ngoại lệ dán chuyến tháng khóa theo `NHAP-SHEET-01` (7).
