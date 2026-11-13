# PS-TAI-HANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Câu hỏi "Phụ phí PS cần trả lời" ([PS-HOI-01](ps-hoi-01.md)) **nằm ngay dưới hàng chuyến của nó**, như duyệt chuyến mới tại hàng ([DUYET-TAI-HANG-01](duyet-tai-hang-01.md)):

1. Mỗi chuyến có câu hỏi có một hàng nền vàng nhạt ngay dưới: nhãn "Phụ phí PS", PS ghi gì; dòng dưới là câu hỏi, nút "… hết báo" và cách làm nếu trả lời ngược lại. Một chuyến nhiều câu thì nhiều dòng trong cùng hàng đó.
2. Cùng một khoản PS chia cho nhiều cont: mỗi hàng ghi "(cùng khoản với …)", nút trả lời "(n cont)" trả lời cả nhóm như cũ.
3. Câu không trả lời bằng nút được (tháng khóa, container khớp nhiều chuyến, thiếu loại phí) cũng nằm ở hàng, kèm nút Mở khóa tháng khi có.
4. Thanh việc đầu sổ chỉ còn "Phụ phí PS cần trả lời: n" và nút **Đến dòng (tiếp)**: mở đúng tháng, cuộn tới hàng, con trỏ vào nút của hàng đó. Không còn khung lớn chen giữa đầu sổ và bảng chuyến.
5. Dòng PS không gắn được chuyến nào (ví dụ lỗi của bộ lập bill) không có hàng để đặt: thanh việc ghi "n dòng không gắn chuyến" kèm nút Xem mở danh sách nhỏ.

Không đổi: câu chữ, nút, luật "hết báo" của PS-HOI-01, lệnh ghi, luật tiền. Các khung khác cùng kiểu (Giá từ Sheet cần xem, Phiếu thu Sheet cần xem) giữ nguyên tới khi người dùng thử cách này.

## Ngày / nguồn

13/11/2026, chat. Người dùng gửi ảnh khung "Phụ phí PS cần trả lời: 6" của một sổ và nói chỗ đặt các việc cần xử lý của sổ chưa hợp lý. Claude đo trên máy chủ giả ở khung 1280×560: mở khung là kín màn, bảng chuyến bị đẩy khuất, trả lời mà không thấy chuyến. Claude đưa ba cách (tại hàng chuyến, ngăn bên phải, chuyển sang Việc cần làm); người dùng chọn "Tại hàng chuyến (đề xuất)" và "Chỉ Phụ phí PS trước".

## Hiệu lực và giới hạn

ĐÃ CHỐT theo lựa chọn của người dùng. Chỉ đổi giao diện trang live (`so-khach-v7-ps-ui.js`, `so-khach-v7-ps.css`); không đổi API, DB hay luật tiền. CÒN MỞ: người dùng tự đi hết luồng trên `hao`; có làm cùng cách cho các khung còn lại không.
