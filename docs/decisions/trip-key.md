# TRIP-KEY

[← Sổ quyết định](../decisions.md)

## Quyết định

(**Sửa 20/10/2026:** mốc 14/10 trong dòng này thay bởi [`MOC-CHUYEN-MOI`](moc-chuyen-moi.md) — mã chuyến bắt buộc cho mọi chuyến nhập web, tức chuyến chưa có trong bản sổ gốc v2; chuyến có trong bản đó là chuyến cũ, không cần mã chuyến.) Người dùng/chủ nghiệp vụ chốt mã chuyến ổn định = số booking + số container của chuyến, chuẩn hóa bằng cách viết hoa và bỏ mọi khoảng trắng. Bắt buộc cho mọi charge có ngày xe nhập kho từ 14/10/2026 (xem OPENING-FINAL). Chuyến mới thiếu container ở CHỜ KIỂM, ngoài số dư; thiếu booking dùng mã thay thế theo ALT-KEY-01 (17/10/2026). Chuyến trước 14/10 là chuyến cũ: nợ nằm trong opening, không cần mã chuyến.

## Ngày / nguồn

15/10/2026, xác nhận trong chat hiện tại, sau khi kiểm chỉ đọc tab booking của sheet vận hành (ID và dữ liệu giữ ngoài repo)

## Hiệu lực và giới hạn

ĐÃ CHỐT định danh cho chuyến có booking. Cơ sở: trong bản booking ngày 15/10, 5.273 cặp booking + container thật không trùng, còn một container có thể thuộc nhiều booking. Ô booking chỉ ghi ký hiệu, không có chữ hay số (ví dụ "/"), được coi là thiếu booking. Container, ngày hoặc khách đơn lẻ vẫn không là khóa. Sổ công nợ lịch sử không ghi booking: bảng nối dòng opening 13/10 ↔ mã chuyến là ĐỀ XUẤT, lưu trong hồ sơ có quyền riêng ngoài repo, chỉ có hiệu lực khi chủ nghiệp vụ duyệt; quy tắc chọn booking theo ngày khi container có nhiều booking chưa được duyệt. Cách lưu (ĐỀ XUẤT theo SIMPLIFY, đã cài trong fixture CI ở PR #10): fixture tính `trip_key` trong DB từ `booking_no` + `container_no` thô, bỏ mọi khoảng trắng kể cả khoảng trắng Unicode; mỗi `trip_key` chỉ post một lần (luật bảo thủ cho tới khi chốt chặn trùng) ([P0-02](../../specs/p0-write-path/07-identity-revision-implementation.md)). Ngày 17/10/2026: chuyến thiếu booking (trống hoặc chỉ ký hiệu như "/") dùng mã thay thế theo [ALT-KEY-01](alt-key-01.md); booking sửa sau khi ghi theo [BOOKING-EDIT-01](booking-edit-01.md); chặn trùng theo DUP-01. Chưa triển khai trong app/DB thật; M2 vẫn chưa đạt.
