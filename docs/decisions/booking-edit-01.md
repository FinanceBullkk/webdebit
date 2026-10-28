# BOOKING-EDIT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chốt: booking bị sửa sau khi chuyến đã ghi nợ thì **giữ nguyên phiếu và mã chuyến đã ghi**, giữ snapshot nguồn lúc ghi; nếu ảnh hưởng số tiền/khách/kỳ thì lập phiếu điều chỉnh hoặc đảo có người duyệt, không sửa đè.

## Ngày / nguồn

17/10/2026, xác nhận trong chat

## Hiệu lực và giới hạn

ĐÃ CHỐT nguyên tắc. Chi tiết phiếu điều chỉnh/đảo thuộc P0-05/D07, vẫn CÒN MỞ. Chưa triển khai. **Sửa 20/10/2026:** vế "có người duyệt" hết hiệu lực theo `V6-DB`; cách điều chỉnh theo [`V7-SO`](v7-so.md) (tính tiền ngay, có vết người làm). Phần giữ phiếu, mã chuyến và snapshot nguồn lúc ghi vẫn hiệu lực.
