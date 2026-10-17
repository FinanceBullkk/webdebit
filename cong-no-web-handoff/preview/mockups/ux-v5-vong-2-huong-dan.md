# Mockup công nợ V5 · vòng 2

## Mở bản HTML

Tải `index.html` rồi mở trực tiếp bằng trình duyệt Chrome hoặc Edge. Đây là **một file duy nhất** chứa HTML, CSS và JavaScript, không dùng thư viện bên ngoài, không yêu cầu internet, không lưu vào máy chủ và không ghi vào dữ liệu công nợ thật.

Góc trên của trang có ô **Khung đang xem** với 10 trạng thái mẫu. Nút **Xem đủ 10 khung để chụp ảnh** mở chế độ liệt kê cả 10 section trên cùng trang. Mỗi section có ID `khung-01` … `khung-10` để dễ chụp tự động. Cũng có thể mở trực tiếp `index.html?scene=10` cho khung thứ 10, hoặc `index.html?gallery=1` cho tất cả.

## Nội dung của 10 khung

| Khung | Trạng thái |
|---|---|
| 01 | Sổ mặc định, thiếu giá DEMO-103, ba giá 40.000.000 / 30.000.000 / 20.000.000 |
| 02 | Bung chuyến, hiển thị 7 trường và công thức Thành tiền |
| 03 | Dán 11 cột; Thành tiền nguồn chỉ để đối chiếu |
| 04 | Gõ bốn trường khoản thu ngay tại dòng DEMO-105 |
| 05 | Thu 120.000.000, còn Đã chốt 0 / Đang mở 65.000.000 |
| 06 | Hai lý do chặn chốt đồng thời |
| 07 | Người chốt hợp lệ; 4 chuyến 105.000.000, chứng từ 5.000.000 vẫn treo |
| 08 | Lọc `Chưa chốt` ra 2 / 5 sổ mẫu |
| 09 | Xác nhận bỏ DEMO-103 cùng chứng từ chưa xác nhận; thao tác có lịch sử |
| 10 | Thu 200.000.000; dư −15.000.000, phải trả lại |

## Thao tác có thể thử

- Chọn khách hoặc bộ lọc ở cột trái; mở/thu gọn một tháng.
- Bấm mã container để bung chi tiết; dùng menu `⋮` ở dòng để ghi tiền hoặc bỏ dòng.
- Dán tối đa 50 dòng, đúng 11 cột Tab, trực tiếp vào dòng trống cuối bảng. Hoặc dùng hộp `Dán từ bảng tính`. Nếu Thành tiền nguồn không trùng phép tự cộng, hệ thống giữ dữ liệu và báo khoản lệch.
- Ở khung 04, sửa các ô khoản thu rồi chọn **Xem kết quả mô phỏng**, có thể thử 120.000.000 và 200.000.000.
- Ở khung 09, bấm xác nhận bỏ dòng để xem lịch sử hành động. Sau khi tải lại trang, dữ liệu giả trở về ban đầu.

## Quy tắc mô phỏng

`Thành tiền = Đơn giá + Phí khác + Phí cắm điện cảng + Phí áp tải`. Phí trống hiển thị `—` và được coi là không phát sinh phí khi cộng. Giá chưa biết vẫn là `Chưa có dữ liệu`, không cộng vào tổng. Khoản thu chưa có ngày thực nhận nằm ngoài số dư. Tiền thu áp dụng cho sổ khách × loại hàng và tháng; dòng chuyến chỉ là điểm nhập. Tiền thu ưu tiên nợ cũ, sau đó trừ phần đang mở. Nếu vượt tổng nợ, khoản còn thừa nằm trong chính sổ đó và hiện số âm kèm chữ `khách trả dư · phải trả lại`.

Số dư lịch sử 01 / 02 / 03 vẫn là **40.000.000 / 70.000.000 / 95.000.000** trên tất cả các khung.

## Bốn vấn đề còn mở

1. Chưa xác minh thứ tự 11 cột với bảng tính thật.
2. Chưa quyết định ai có quyền xác nhận khoản thu và cần căn cứ gì; không có nút xác nhận.
3. Khoản trả dư mặc định không tự sử dụng cho sổ khác cùng khách.
4. Trong màn lọc, sổ chưa mở tạm không được tính là chưa chốt.

Đây là **prototype front-end**, không phải ứng dụng công nợ thật. Các nút lưu/chốt/xóa thay đổi trạng thái trong bộ nhớ trang cho mục đích minh họa, không có bảo đảm giao dịch hoặc nhật ký lưu bền.
