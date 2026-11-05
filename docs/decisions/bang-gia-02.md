# BANG-GIA-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **lưu bảng giá thì chuyến đang theo bảng tự đổi sang giá mới, không phải bấm "Áp lại giá mới".** Thay nguyên tắc "sửa bảng giá không tự đổi chuyến đã ghi" (đề xuất của Claude trong [`BANG-GIA-01`](bang-gia-01.md), chưa từng là câu người dùng chốt).

| Chuyến | Khi lưu bảng giá |
| --- | --- |
| Đang theo bảng, đã tính vào sổ, tháng mở, tra được giá mới | **Tự đổi** trong cùng lệnh lưu, ghi Lịch sử trước → sau, phiếu thu phân bổ lại theo nợ cũ trước |
| Đang theo bảng, tháng khóa | Không đổi. Báo số chuyến; mở khóa tháng rồi bấm "Áp lại giá mới" |
| Đang theo bảng, bảng mới không còn giá cho chuyến đó | Giữ giá đang ghi (không thành trống, không thành 0). Báo số chuyến |
| Giá gõ tay hoặc lấy từ Sheet | Không đổi, chỉ tô "khác bảng" như cũ. Gõ tay vẫn thắng bảng |
| Chưa có giá | Vẫn bấm "Điền giá theo bảng", vì đây là cộng thêm nợ mới |

Mọi chuyến đang theo bảng và lệch giá đều được đổi khi lưu, kể cả chuyến lệch từ trước vì sửa ngày, nơi đi hoặc shipper. Sửa thông tin chuyến không tự đổi giá; dải "Áp lại giá mới" vẫn là đường cho trường hợp đó và cho tháng vừa mở khóa. Dòng sổ gốc vẫn ngoài phạm vi bảng giá.

## Ngày / nguồn

5/11/2026, người dùng hỏi "ko tự đổi theo bảng giá dc hả" khi thấy thông báo sau lưu, đọc bảng năm loại chuyến ở trên rồi chọn "Có, tự đổi" trong chat.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Migration `2026-11-05-v7-gia-tu-doi.sql` thay thân `save_price_table`, thêm hàm nội bộ `_reprice_from_table`; không đổi bảng, ràng buộc, loại event hay quyền. Trạng thái triển khai ghi ở nhật ký `docs/deploys/`.

Khác Sheet: công thức Sheet tính lại mọi chuyến kể cả tháng cũ và giá đã sửa tay; web giữ tháng khóa và giá gõ tay. Trong lúc chạy song song (`SONG-SONG-01`) giá tự đổi trên web không ghi ngược lên Sheet; nếu Sheet giữ giá khác thì lệch được đối soát như mọi lệch khác.

Tiêu chí và hợp đồng API: [`specs/v7-bang-gia-hieu-luc.md`](../../specs/v7-bang-gia-hieu-luc.md).
