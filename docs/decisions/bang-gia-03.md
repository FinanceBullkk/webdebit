# BANG-GIA-03

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng yêu cầu bảng giá có **Nơi đến**. Giá tra theo cả nơi đi và nơi đến; thay Q4 của [BANG-GIA-01](bang-gia-01.md). Với dòng giá cũ chưa có nơi đến, người dùng chọn **chỉ áp giá khi bổ sung nơi đến**. Ô trống không có nghĩa là mọi nơi đến.

Quy tắc giữ nguyên: giá gõ tay/giá Sheet không bị ghi đè; tháng khóa giữ giá đang ghi; lưu bảng có thể tự đổi chuyến đang theo bảng ở tháng mở theo [BANG-GIA-02](bang-gia-02.md).

## Ngày / nguồn

10/11/2026, yêu cầu trong chat kèm ảnh lưới Bảng giá; người dùng chọn “Chỉ khi bổ sung nơi đến”.

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. ĐÃ CODE trong worktree từ `3e90f28`; ĐÃ KIỂM CHỨNG cục bộ 10/11/2026: `npm run check` qua 8/8 bước; PostgreSQL dùng một lần qua 10 ca lược đồ, 69 ca hành vi, 2 mục mở được bỏ qua, 0 lỗi. [Spec](../../specs/v7-bang-gia-noi-den.md) nêu phạm vi. Chưa triển khai `hao`, chưa nạp hay sửa bảng giá thật.
