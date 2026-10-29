# ALT-KEY-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chọn: chuyến mới có ô booking trống hoặc chỉ ký hiệu (ví dụ "/") **dùng mã thay thế** thay vì CHỜ KIỂM, thay quy tắc "thiếu booking ở CHỜ KIỂM" của TRIP-KEY.

## Ngày / nguồn

17/10/2026, xác nhận trong chat

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng. ĐỀ XUẤT, chưa chốt chi tiết: mã thay thế = container chuẩn hóa + ngày xe nhập kho, có tiền tố đánh dấu không booking để không lẫn với mã booking thật; vẫn chịu DUP-01 (một charge mỗi mã) và NEWTRIP-01. Thêm CHỜ KIỂM khi cùng container đã có mã booking thật hoặc mã thay thế khác lệch trong 3 ngày (nguy cơ nhập trùng), hoặc container sai định dạng. Khi booking thật xuất hiện sau khi ghi, xử lý theo BOOKING-EDIT-01. Chưa triển khai.
