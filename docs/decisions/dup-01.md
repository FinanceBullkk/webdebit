# DUP-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chọn C04-A cho charge đầu tiên v1: mỗi mã chuyến (`trip_key`) chỉ được ghi một charge. Charge thứ hai cùng mã chuyến (kể cả phí bổ sung) ở CHỜ KIỂM, ngoài số dư, cho tới khi có chính sách phí bổ sung riêng.

## Ngày / nguồn

16/10/2026, xác nhận trong chat sau khi so sánh C04-A/B/C

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. Fixture CI (PR #10) đã có `UNIQUE(posting.trip_key)` trên dữ liệu giả; chưa có migration/app production. Có thể nâng lên khóa theo chuyến + loại phí khi danh mục loại phí được duyệt.
