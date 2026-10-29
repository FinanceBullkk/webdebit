# DASH-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Trang tổng quan công nợ V7 là **trang đầu khi vào web**, chỉ đọc, gồm: tổng còn phải thu (kèm tiền khách đang dư), theo mặt hàng, nợ theo tháng phát sinh (tháng này · 1–2 · 3–6 · trên 6 tháng), 10 khách nợ nhiều nhất, việc cần làm (chuyến **web** thiếu giá — dòng sổ gốc thiếu giá không tính —, CHỜ KIỂM, khách chưa có số dư đầu, sổ đang dư), hôm nay (theo **ngày ghi trên web**, giờ VN, chia theo người làm). Không đối chiếu Sheet trên trang. Chi tiết và hợp đồng API: [spec](../../specs/v7-dashboard.md).

## Ngày / nguồn

23/10/2026, người dùng chọn trong chat

## Hiệu lực và giới hạn

ĐÃ CHỐT nội dung. Backend giao Codex (ĐỀ XUẤT hợp đồng `GET /api/v7/dashboard`); giao diện chờ mockup Penpot được duyệt. Chưa code, chưa triển khai.

Cập nhật 29/10/2026 (người dùng chốt trong chat, mockup v5.3, PR FinanceBullkk/webdebit#134): Tổng quan có tương tác — bấm nhóm tuổi nợ / mặt hàng lọc danh sách khách tại chỗ, bấm khách mở ngăn kéo; Việc cần làm thêm nhóm "Cần gán mặt hàng / cảng-bộ". Chi tiết ở spec, mục Bằng chứng.
