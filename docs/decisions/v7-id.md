# V7-ID

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt người thao tác là **danh tính Tailscale riêng của từng người** (19/10/2026). Bản thử: ai đã vào app cũng thao tác được, không phân quyền theo người; vẫn ghi actor từ phiên phía server để có vết, không nhận actor từ client (20/10/2026)

## Ngày / nguồn

19/10 và 20/10/2026, xác nhận trong chat

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng; thay phần "tài khoản ứng dụng riêng" của `Q01`. Chưa triển khai, chưa kiểm runtime. CÒN MỞ: cách app đọc danh tính Tailscale tin cậy (không tin header client tự khai), quản lý ai được vào và thu hồi — người dùng để sau (19/10/2026); ai được xem lưu vết.
