# DIEN-THOAI-NUT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Dưới 760px, mọi nút, ô chọn và ô đánh dấu người dùng phải chạm có vùng bấm cao ít nhất **40px**; ô lọc, ô chọn và nút trên thanh công cụ của Công nợ theo tháng cao **44px**. Áp cho:

1. Sổ khách: thẻ tháng (40px, tháng đang xem 46px), nút trên thanh chuyến, nút Ghi phiếu thu (44px), nút Xem/Đóng ở dải "cần xem".
2. Công nợ theo tháng: khung ô lọc, nút năm trước/sau, hai ô chọn, Làm mới, ô "Chỉ khách còn nợ" (ô 22px, bấm được cả nhãn).
3. Máy chạy: chọn nhân viên, máy quay, hai tab, ô giờ của lượt (56×40px), Làm mới.

Không đổi: màn từ 760px trở lên; vùng bấm đã đủ nhờ cả hàng bấm được (dòng Bảng thu, dòng bảng kê, viên số của Tổng quan). Cảnh văn phòng của Máy chạy vẫn cuộn ngang vì chữ trên tranh không đọc được khi thu còn 360px.

## Ngày / nguồn

12/11/2026, chat: người dùng giao "tối ưu cho điện thoại mọi tính năng và màn". Claude đo 11 màn trên `hao` ở 390×844 (chỉ đọc, chặn mọi lệnh ghi): không màn nào tràn ngang, nhưng 63 nút ở Máy chạy, 11 ở Công nợ theo tháng, 13 ở Sổ thấp hơn 40px. Mốc 40px theo [audit UX](../ux-audit-2026-10-31.md) và người dùng trên 40 tuổi.

## Hiệu lực và giới hạn

ĐỀ XUẤT đã triển khai theo giao việc chung; người dùng chưa thử trên điện thoại thật. Chỉ CSS, không đổi luồng hay số.
