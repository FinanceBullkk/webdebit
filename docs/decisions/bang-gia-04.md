# BANG-GIA-04

[← Sổ quyết định](../decisions.md)

## Quyết định

Trong bảng giá, **Nơi đến không bắt buộc**. Người dùng: “có cái thì phải set theo cả nơi đến, nhưng có cái thì nơi đi là ok rồi”. Thay câu “ô trống không có nghĩa là mọi nơi đến” của [BANG-GIA-03](bang-gia-03.md).

1. Dòng có Nơi đến trống là **giá chung** của nơi đi: áp cho mọi chuyến từ nơi đi đó, kể cả chuyến thiếu nơi đến.
2. Dòng có Nơi đến cụ thể thắng giá chung khi đợt của nó phủ ngày chuyến. Đợt riêng đó thiếu nhóm giá cần dùng (khách/TT) thì báo thiếu giá, không lấy giá chung thay — cùng nguyên tắc không lấy giá nhóm kia thay.
3. Đợt riêng không phủ ngày chuyến thì dùng giá chung nếu giá chung phủ ngày đó.
4. Trùng ngày chỉ xét trong cùng nơi đi, cùng nơi đến (trống tính là một nơi đến), cùng nhóm giá. Giá chung và giá riêng cùng ngày không trùng nhau.

Giữ nguyên: giá gõ tay/giá Sheet không bị ghi đè; tháng khóa giữ giá đang ghi; lưu bảng tự đổi chuyến đang theo bảng ở tháng mở theo [BANG-GIA-02](bang-gia-02.md).

## Ngày / nguồn

13/11/2026, yêu cầu trong chat. Thứ tự ưu tiên giá riêng hơn giá chung do Claude chọn theo `CLAUDE-ALL-01`, vì người dùng nói nơi đến chỉ cần ở “có cái”.

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. Migration `2026-11-13-v7-noi-den-tuy-chon.sql` chỉ thay thân `_lookup_price` và `save_price_table`, không đổi bảng, giá chuyến hay số dư. 142 dòng giá cũ còn Nơi đến trống từ 10/11 trở thành giá chung: chuyến chưa có giá thấy gợi ý “bảng …” và nút điền giá, nhưng tiền chỉ đổi khi người dùng bấm điền giá hoặc lưu bảng. ĐÃ TRIỂN KHAI trên `hao` 13/11/2026 09:15 tại `222fd77` ([nhật ký](../deploys/2026-11-13-noi-den-tuy-chon.md)). ĐÃ KIỂM CHỨNG: `npm run check`, CI gồm PostgreSQL, migration hai lượt và rollback trên bản sao, DB thật số dư từng khách không đổi; 46/80 chuyến tra được giá bảng, không chuyến nào đổi tiền. CÒN MỞ: người dùng lưu thử một dòng Nơi đến trống trên giao diện có đăng nhập.
