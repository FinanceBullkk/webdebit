# DEBIT-NOTE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: từ sổ khách xuất được **debit note** theo đúng mẫu "COMMERCIAL INVOICE" đang gửi khách (bảng chuyến: container, hãng tàu, shipper, ngày, kho, cảng đến, Neo, Phí điện, Đóng ghép, Other fee, Bảo hiểm, Kiểm định, Health cert, Đơn giá, Tổng). (1) Chọn theo **tháng công nợ** của sổ. (2) Xuất **cả Excel và bản in PDF**. (3) Chuyến **chưa có giá thì để trống** Đơn giá và Tổng. (4) **Health cert là tiền**; chữ "Yes" trong mẫu chỉ là đánh dấu tạm vì mẫu chưa phải bản chính. (5) **Chỉ liệt kê công nợ các chuyến của tháng đó**: không ghi nợ cũ, tiền đã thu hay số còn phải trả. Spec: [`specs/v7-debit-note.md`](../../specs/v7-debit-note.md).

## Ngày / nguồn

29/10/2026, chat: gửi ảnh mẫu, hỏi "từ công nợ của sổ khách … xuất ra được một cái debit note như này", rồi trả lời năm câu hỏi ở trên.

## Hiệu lực và giới hạn

ĐÃ CHỐT (1)–(5). Từ 30/10/2026 bố cục và điểm (3) thay bởi [DEBIT-NOTE-02](debit-note-02.md) (mẫu Debit Note v3 sếp duyệt): thiếu giá thì chặn bản chính thức, chỉ ra bản nháp. Claude chọn theo quyền `CLAUDE-ALL-01` các điểm sau, người dùng sửa được khi xem bản thử: chuyến CHỜ KIỂM/ĐÃ LOẠI không lên phiếu; dòng phí lẻ của tháng có lên phiếu; còn một chuyến thiếu giá thì dòng TỔNG để trống và ghi **CHƯA CHỐT**, đủ giá thì ghi tổng và **ĐÃ CHỐT**; loại phụ phí ngoài sáu loại có cột riêng trong mẫu (kể cả Khác, Giảm trừ, Phụ phí ban đầu) cộng vào **Other fee**; dòng điều chỉnh cả tháng không lên phiếu (hộp xuất báo số dòng). Chỉ đọc dữ liệu sổ đang hiện, không ghi gì vào DB. ĐÃ CODE ở trang sổ khách; triển khai tự động khi merge qua `Deploy hao`. CÒN MỞ: người dùng chưa đối chiếu phiếu xuất từ sổ thật với mẫu.
