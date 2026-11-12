# DIEN-THOAI-SEP-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Các màn sếp xem ([`DASH-06`](dash-06.md), [`TINH-HINH-01`](tinh-hinh-01.md), [`HOAT-DONG-01`](hoat-dong-01.md), Bảng thu, Công nợ theo tháng) đọc được trên điện thoại (dưới 760px; Tổng quan theo mốc 700px sẵn có) mà không phải vuốt ngang để thấy số. Cùng nguyên tắc với [`DIEN-THOAI-CHUYEN-01`](dien-thoai-chuyen-01.md): bớt cột, giữ số, thông tin chỉ có khi rê chuột thì ghi ra hoặc chạm để xem.

1. **Tổng quan:** bảng "Khách cần đòi trước" chỉ còn Khách · Quá hạn · Còn nợ; bỏ thanh hạn trả (chỉ có số khi rê chuột) và hai cột ngày Trả, Đi hàng (chấm màu trước tên đã gộp mức rủi ro). Ba viên số cạnh Còn phải thu ghi chữ ("66 khách đang nợ", "83 chuyến chưa giá", "… khách trả thừa").
2. **Tình hình:** câu dưới biểu đồ trên màn cảm ứng là "Chạm một tháng để xem số"; nhãn tháng chỉ ghi T1…T12, bỏ phần năm và "đến ngày" để không đè nhau.
3. **Đã làm:** mỗi việc thành một khối: giờ · người làm · sổ · Mở sổ; việc; chi tiết; ghi chú.
4. **Công nợ theo tháng:** ma trận mở sẵn ở tháng hiện tại (một lần mỗi năm đang xem, tự tải lại không kéo về); bỏ dòng "Cập nhật … tự tải mỗi 60 giây".
5. **Bảng thu:** năm cách xem trên một hàng vuốt ngang; cột số tiền đủ chỗ cho số hàng tỷ.

Màn rộng không đổi.

## Ngày / nguồn

12/11/2026, chat: sau `DIEN-THOAI-CHUYEN-01` người dùng hỏi "các màn khác thì sao, improve UX cho các màn mà sếp sẽ xem". Claude đo năm màn trên `hao` ở 390×844 (chỉ đọc), thấy số nợ từng khách ở Tổng quan và cột Việc ở Đã làm nằm ngoài màn, ma trận mở ở Tháng 1. Cách sửa do Claude quyết theo [`CLAUDE-ALL-01`](claude-all-01.md): chỉ bớt cột và xếp lại trên màn hẹp, không đổi số hay luồng.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Ngoài phạm vi: bảng chi tiết theo bảng kê ([`SO-CHI-TIET-01`](so-chi-tiet-01.md)), ma trận theo tháng vẫn là bảng cuộn ngang (chỉ mở sẵn ở tháng hiện tại), nút nhỏ hơn 40px ở Công nợ theo tháng và Bảng thu.
