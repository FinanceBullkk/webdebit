# SIMPLIFY

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chọn đơn giản hóa fixture ghi ngay: bỏ HMAC từng lệnh, bỏ kind generic và cặp role riêng, thu hẹp canonical; resolver opening dựa trên bảng resolution (rỗng ngoài test).

## Ngày / nguồn

16/10/2026, xác nhận trong chat sau review độc lập

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng làm; fixture đã triển khai trong PR #10 và được kiểm CI trên dữ liệu giả. Chưa triển khai trong app/DB production; không mở ghi tiền thật. Bảng resolution production theo [NEWTRIP-01](newtrip-01.md) (17/10/2026), không chờ duyệt từng dòng bảng nối lịch sử.
