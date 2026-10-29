# V7-TONG

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: tab không có tên trên `TONG` thì **loại** khỏi bản sạch và khỏi sổ nạp, kể cả khi tab còn số dư. Quy tắc này thay vế "khách có nợ ở tab không có dòng `TONG` vẫn tính vào thống kê" trong [`V7-MH`](v7-mh.md). Bản sạch `format_version 2` (`captures/2026-10-21-clean-v2/`, ngoài Git) là bản **tổng duyệt định dạng mới**, không phải mốc chuyến: bộ nạp `--from-clean` chỉ đọc bản sạch và kiểm SHA-256 manifest trước khi chạm DB. Hash manifest `b55d95a0…` (SHA-256 đầy đủ nằm trong báo cáo nạp ngoài Git). Số tiền và tên khách ở ngoài Git.

## Ngày / nguồn

21/10/2026, người dùng chốt trong chat

## Hiệu lực và giới hạn

ĐÃ CHỐT (quy tắc loại). ĐÃ KIỂM CHỨNG: nạp bản v2 vào bản sao Docker cô lập, đối soát từng khách với bản sạch đều KHỚP (bằng chứng ngoài Git). CHƯA triển khai lên `hao` — mốc chuyến vẫn theo [`MOC-CHUYEN-MOI`](moc-chuyen-moi.md).
