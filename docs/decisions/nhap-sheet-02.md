# NHAP-SHEET-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Bỏ **bảng nhập chuyến** (hàng trống, nháp, nút "Lưu N chuyến"/"Bỏ nháp") khỏi sổ khách V7. Chuyến mới vào sổ web từ Sheet: runner đọc Sheet (lịch 15 phút hoặc nút "↻ Làm mới", [spec](../../specs/v7-sheet-refresh.md)) đưa chuyến mới thành dòng chờ, người nhập duyệt trên sổ như hiện nay. Thay vế (1) của [`NHAP-SHEET-01`](nhap-sheet-01.md) ở phần giao diện nhập; các vế (2)–(7) (sửa đè tại ô, xóa chuyến, đổi ngày sang tháng khác, sửa/xóa dòng sổ gốc, tháng khóa) giữ nguyên. Hàng nhập phiếu thu không đổi.

## Ngày / nguồn

29/10/2026, người dùng trong chat: "giờ chúng ta sync chuyến từ sheet rồi ko cần nhập tay nữa, nên là giờ bỏ cái nhập này đi".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi giao diện: bỏ `so-khach-v7-draft-ui.js`, CSS và hàm đọc vùng dán/kiểm nháp trong `so-khach-v7-model.js`. Backend (`paste_trips`, `POST /api/v7/trips/paste`) không đổi; không đổi luật tiền. Chuyến chưa có trên Sheet thì nhập vào Sheet trước rồi lấy về web, đúng [`SONG-SONG-01`](song-song-01.md) (Sheet là sổ chính thức tới ngày chuyển hẳn). Xét lại khi chuyển hẳn sang web.
