# KHOI-KHONG-DON-GIA-01

[← Sổ quyết định](../decisions.md)

## Quyết định

**Khối tháng trên tab khách có thể không có cột đơn giá.** Tiêu đề khối có cột container, ngày, TOTAL, cột đã thu và cột số dư cuối tháng mà thiếu cột `UNIT PRICE`/`ĐƠN GIÁ` thì bộ đọc tab vẫn đọc khối đó, không đánh dấu tab hỏng:

1. Mỗi chuyến đọc như dòng chỉ có TỔNG: số tiền chuyến là ô TOTAL của Sheet, chuyến mang cờ `MISSING_PRICE`; khối mang cờ `NO_PRICE_COLUMN`.
2. Chuỗi số dư cuối tháng vẫn phải khép như mọi khối; không khép thì khách vẫn bị giữ.
3. Các cột không có tên bộ đọc biết (ví dụ cước nội địa, phí dịch vụ, VAT của từng khoản) không thành phụ phí, không bị tách. Máy đối soát lấy TỔNG làm đơn giá theo luật có sẵn của [`MAY-DOI-SOAT-01`](may-doi-soat-01.md) (dòng Sheet chỉ có TỔNG, chuyến web chưa có giá).
4. Thiếu cột ngày, cột đã thu hay cột số dư thì vẫn là bố cục không đọc được (`SOURCE_LAYOUT_UNSUPPORTED`), như trước.

## Ngày / nguồn

24/11/2026, người dùng chọn "Máy đọc mẫu mới" trong chat, sau khi soát danh sách "Booking có, web chưa có" của Báo cáo tháng 11. Ca thật: một tab khách (sổ 123) ghi khối tháng 11 theo mẫu hóa đơn dịch vụ (cước nội địa và phí dịch vụ hải quan, mỗi khoản có VAT), không có cột đơn giá; cả tab bị `broken` theo KIEM-TAB-01 ([spec](../../specs/v7-kiem-tab-truoc-khi-ghi.md)) nên máy không ghi tiền và số nợ của khách chỉ có trên Sheet. Phương án còn lại (kế toán sắp lại khối theo mẫu chuẩn) không chọn.

## Hiệu lực và giới hạn

- Đo trên `hao` 24/11/2026, chỉ đọc, chạy bộ quét cũ và mới trên mọi tab của Sheet sổ nợ: đúng một tab đổi từ `broken` sang `ok`, các tab khác giữ nguyên kết luận; dòng giá giống hệt (cùng mã băm), dòng phiếu thu thêm đúng các phiếu của tab đó.
- Không đổi cách tính tiền của tab đang đọc được. Không đổi schema.
- Mã ở `tools/v7_load_real_copy.py` (file bộ đọc), nên `Deploy hao` dừng ở cổng file bộ đọc và triển khai tay theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md).

## Trạng thái

ĐÃ CHỐT 24/11/2026 (người dùng). Triển khai và kiểm chứng ghi ở nhật ký triển khai khi lên `hao`.
