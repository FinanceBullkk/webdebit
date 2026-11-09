# DUYET-TAI-HANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng yêu cầu: chuyến mới từ Sheet **duyệt ngay ở hàng của chuyến đó**, không bằng nút lô ở góc trên ("Duyệt n chuyến mới"), vì không biết chuyến mới nằm ở đâu.

1. Hàng CHỜ DUYỆT có nút **Duyệt** ở cột Thành tiền, chỉ duyệt đúng chuyến đó (`POST /api/v7/sheet/approve` thêm `source_rows`). Chuyến vào sổ chưa có giá như duyệt lô, nên lúc duyệt tổng còn nợ không đổi; vì vậy không hỏi lại một bước (thay khung xác nhận L4 của [SO-GON-04](../../specs/v7-so-khach-ux-dot-2.md)).
2. Hàng ghi ngắn **vì sao máy chưa tự duyệt**, cùng điều kiện với máy (`v7_inbox._auto_trips`): ngày sau hôm nay (không có nút, tới ngày máy tự duyệt), Sheet chưa ghi mặt hàng, mặt hàng khác sổ, tháng cũ đang khóa, chưa chắc sổ.
3. Thanh việc đầu sổ chỉ báo "n chuyến mới từ Sheet chờ duyệt" kèm nút **Đến chuyến**: mở đúng tháng, cuộn tới hàng, đặt con trỏ vào nút Duyệt.
4. Lệch booking: câu giải thích "Sheet sửa booking sau khi chuyến đã vào sổ. Sổ giữ booking cũ, tiền không đổi" và nút "Đã xem, hết báo" (vẫn là `keep_web` theo [BOOKING-EDIT-01](booking-edit-01.md)).

## Ngày / nguồn

9/11/2026, chat (ảnh chụp thanh "Duyệt 2 chuyến mới" và hàng KHÁC booking). Claude đề xuất cách làm và làm luôn.

## Hiệu lực và giới hạn

ĐÃ CHỐT theo yêu cầu người dùng. Không đổi luật tiền, không đổi đường ghi (`paste_sheet_rows`). Không còn nút duyệt cả lô trên sổ; máy vẫn tự duyệt chuyến chắc chắn. "Phụ phí PS cần xem" là việc riêng (PR sau).
