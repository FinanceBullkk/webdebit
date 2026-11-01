# KHOA-CHU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: ở **tháng đã khóa** vẫn sửa được **bốn ô chữ mô tả** của chuyến, gồm **nơi đi, nơi đến, shipper, hãng tàu**, mà không cần mở khóa tháng.
- Áp cho chuyến web, dòng chuyến của sổ gốc, và lệnh "lấy theo Sheet" khi giải quyết lệch.
- Áp cho người sửa tại ô và cho máy tự lấy theo Sheet ([`HANG-CHO-01`](hang-cho-01.md) Q1).
- Mỗi lần sửa ghi Lịch sử như mọi thao tác: người làm, trước → sau.

Vẫn khóa như cũ ở tháng khóa:
- **tiền**: đơn giá, phụ phí, phiếu thu. Tháng khóa chỉ sửa tiền bằng dòng điều chỉnh, theo [`V7-SO`](v7-so.md);
- **ngày chuyến** (đổi ngày làm chuyến chuyển tháng) và **container** (dùng để kiểm trùng);
- **xóa chuyến**.

Đây là phần "ô chữ" của [`NHAP-SHEET-01`](nhap-sheet-01.md) (3) ("tháng đã khóa cũng sửa đè được các ô chữ và ngày"), nay đưa vào DB. Vế "ngày" của mục (3) **không** làm ở đây: ngày vẫn khóa.

## Ngày / nguồn

1/11/2026, chat. Khi làm P3 của [UX bước 03](../ux-buoc-03-luong-thao-tac.md), Claude đo trên `hao` và thấy cả 944 chỗ lệch chữ Sheet ↔ web nằm ở tháng đã khóa, trong khi DB chặn mọi lần sửa ở tháng khóa kể cả chữ (Lịch sử có 14 lần mở khóa, sửa, khóa lại trong vòng 1 phút). Claude đưa hai cách; người dùng chọn "Cho sửa, ghi Lịch sử".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Triển khai bằng migration `2026-11-01-v7-khoa-chu.sql` (chỉ thay thân `edit_trip_info`, `_change_legacy`, `resolve_sheet_conflict`), kèm giao diện sổ mở bốn ô chữ ở tháng khóa. Trạng thái triển khai ghi ở nhật ký `docs/deploys/`. Không đổi số dư, phân bổ hay quyền.
