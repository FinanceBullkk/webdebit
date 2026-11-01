# SO-GON-05

[← Sổ quyết định](../decisions.md)

## Quyết định

Sổ khách live hiện **một tháng trên màn hình** (UX bước 04, spec [`v7-so-khach-mot-thang.md`](../../specs/v7-so-khach-mot-thang.md)):

1. Hàng chip tháng là chỗ chọn tháng duy nhất; bấm chip thì sổ đổi sang tháng đó. Bỏ các thanh tháng gập và nút "Xem chi tiết"/"Thu gọn".
2. Tháng mở sẵn: tháng của `?month=`, rồi tháng của `?loc=`, rồi tháng hiện tại nếu có số liệu, rồi tháng gần nhất có số liệu.
3. Thanh của tháng có dòng tóm tắt: Nợ đầu tháng + Phát sinh − Đã thu = Còn nợ cuối tháng (số lấy nguyên từ GET), cạnh ổ khóa và Debit note.
4. Bảng sổ co giãn theo bề ngang màn hình (tối thiểu như khổ cũ); ô Khác chỉ hiện số, số khoản vào chữ rê chuột.

## Ngày / nguồn

1/11/2026, chat. Người dùng gửi ảnh màn sổ ("UI đang không ổn"); Claude nêu 7 lỗi và đề xuất đưa bản bấm thử "Sổ một tháng" vào màn thật; người dùng chọn "Làm theo hướng này".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thay H1 của [`SO-GON-04`](so-gon-04.md) (tháng hiện tại và tháng trước mở sẵn, tháng cũ gập một dòng). Các điểm khác của `SO-GON-04` giữ nguyên, kể cả H4: không ẩn cột (ô cột phụ phí riêng là chỗ gõ phụ phí theo [`PHU-PHI-01`](phu-phi-01.md)). Chỉ đổi giao diện trang live; không đổi luật tiền, khóa tháng, lệnh ghi hay DB.
