# DIEN-THOAI-DEBIT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Dưới 760px, hộp Debit note (mẫu v3 và v4) phủ cả màn và thành một cột cuộn dọc:

1. Đầu hộp: tên tháng và trạng thái một dòng, ba nút In / Lưu PDF · Tải Excel · Đóng chia đều một hàng, cao 44px.
2. Ngay dưới là các dòng Chặn/Cảnh báo/Lưu ý và ô xác nhận cảnh báo, để người lập thấy vì sao nút xuất đang khóa.
3. Rồi form, ô nhập cao 44px, chữ 16px (Safari không tự phóng to khi chạm).
4. Cuối là bản xem trước, thu vừa bề ngang khung để thấy cả trang, không cuộn ngang.

Nút xuất đang khóa (còn dòng Chặn, hoặc còn Cảnh báo chưa xác nhận) mờ đi ở mọi cỡ màn; trước đây nút In vẫn tô xanh đậm như bấm được.

Không đổi: màn từ 760px trở lên (hai cột, cỡ xem trước .6/.82), nội dung chứng từ, phép kiểm, cách chia trang, file PDF/Excel.

## Ngày / nguồn

12/11/2026, chat: người dùng báo "UI trên điện thoại cho xuất debit note đang lỗi". Đo ở 390×844 với dữ liệu giả: hộp giữ bố cục màn rộng, form cố định 320px nên cột kiểm và xem trước chỉ còn 46px; nút In bị khóa nhưng trông như bấm được.

## Hiệu lực và giới hạn

Đã sửa theo báo lỗi; người dùng chưa thử trên điện thoại thật. Chỉ giao diện, không đổi số. Chưa kiểm trên điện thoại thật: hộp in của trình duyệt khi bấm In / Lưu PDF (in từ khung ẩn) — Chrome Android và Safari iOS có thể xử lý khác máy tính.
