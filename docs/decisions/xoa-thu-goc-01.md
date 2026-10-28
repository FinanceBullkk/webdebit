# XOA-THU-GOC-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng yêu cầu xóa được khoản thu sổ gốc (dòng thu đọc từ Sheet, `legacy_row` kind `receipt`) trên sổ V7; Claude chốt cách làm theo quyền điều phối ngày 21/10: mở rộng mục "xóa tại ô kể cả sổ gốc" của [`NHAP-SHEET-01`](nhap-sheet-01.md) sang khoản thu. (1) Tháng đang mở: bấm ô số tiền khoản thu sổ gốc → hỏi xác nhận → **Xóa hẳn**; tháng khóa không có nút (mở khóa trước). (2) Số dư đầu không đổi; xóa ghi một dòng điều chỉnh sổ gốc **cộng lại đúng số tiền** vào tháng của dòng thu (dòng ẩn theo [`SO-GON-01`](so-gon-01.md), ghi Lịch sử "Khoản thu sổ gốc … Số đã trừ nợ"), rồi phân bổ lại phiếu web theo nợ cũ trước. (3) Không sửa ô khoản thu sổ gốc (vẫn `LEGACY_NOT_TRIP`), không hoàn tác bằng nút; muốn trừ lại thì ghi phiếu thu web. (4) "Đã thu" ở dòng Tổng tháng của tháng có số dư đầu vẫn tính theo Sheet (`sheetMonthTotals`), nên khi khoản thu đã được chia FIFO vào tháng cũ hơn thì tháng cũ đó vẫn hiện số Sheet; Còn nợ cộng dồn và tổng nợ đúng.

## Ngày / nguồn

28/10/2026, chat (một khoản thu khối T10 đã chia FIFO vào nợ T8)

## Hiệu lực và giới hạn

ĐÃ CHỐT; code ở PR này (hàm `_change_legacy`, migration `2026-10-28-v7-legacy-receipt-delete.sql`, UI sổ khách). CHƯA TRIỂN KHAI `hao`: cần thử migration trên bản sao trước.
