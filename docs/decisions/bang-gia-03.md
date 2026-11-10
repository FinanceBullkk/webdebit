# BANG-GIA-03

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng yêu cầu bảng giá có **Nơi đến**. Giá tra theo cả nơi đi và nơi đến; thay Q4 của [BANG-GIA-01](bang-gia-01.md). Với dòng giá cũ chưa có nơi đến, người dùng chọn **chỉ áp giá khi bổ sung nơi đến**. Ô trống không có nghĩa là mọi nơi đến.

Quy tắc giữ nguyên: giá gõ tay/giá Sheet không bị ghi đè; tháng khóa giữ giá đang ghi; lưu bảng có thể tự đổi chuyến đang theo bảng ở tháng mở theo [BANG-GIA-02](bang-gia-02.md).

## Ngày / nguồn

10/11/2026, yêu cầu trong chat kèm ảnh lưới Bảng giá; người dùng chọn “Chỉ khi bổ sung nơi đến”.

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. ĐÃ TRIỂN KHAI trên `hao` 10/11/2026 tại `8d94e49` ([nhật ký](../deploys/2026-11-10-bang-gia-noi-den.md)). ĐÃ KIỂM CHỨNG: `npm run check`, CI gồm PostgreSQL, migration trên bản sao và DB thật; số dư từng khách không đổi. [Spec](../../specs/v7-bang-gia-noi-den.md) nêu phạm vi. Chưa nạp hay sửa bảng giá thật; lần lưu thật đầu tiên và thao tác UI có đăng nhập còn cần người dùng kiểm.
