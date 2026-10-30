# DEBIT-NOTE-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chuyển yêu cầu của sếp (30/10/2026): mẫu "COMMERCIAL INVOICE" đang gửi khách xấu và cũ, làm lại theo các mẫu commercial invoice chuyên nghiệp. Bố cục mới của debit note (cả bản in/PDF lẫn file Excel), giữ nguyên **16 cột và dữ liệu** của [DEBIT-NOTE-01](debit-note-01.md):

1. Đầu trang: tên công ty, địa chỉ, email bên trái; chữ COMMERCIAL INVOICE và phụ đề "Bảng kê công nợ · 对账单" bên phải; một gạch xanh đậm ngăn với phần dưới.
2. Khối **BILL TO · 客户** (tên khách cỡ lớn) bên trái; khối thông tin phiếu bên phải: Ngày · 日期 (dd/mm/yyyy), Kỳ công nợ · 账期 (Tháng m/yyyy · yyyy年m月), Tiền tệ · 币种 (VND).
3. Bảng chuyến có **dòng nhóm cột**: THÔNG TIN CHUYẾN (7 cột) · PHỤ PHÍ (7 cột) · THÀNH TIỀN (2 cột) nền xanh đậm chữ trắng; dòng tên cột nền xanh nhạt, tên Việt trên, chữ Hán nhỏ dưới; thân bảng chỉ kẻ ngang mảnh, số canh phải; bỏ viền đen và nền vàng/xanh dương của mẫu cũ.
4. Dòng **TỔNG CỘNG · 总计 (VND)** gạch trên đậm, số to; dưới là nhãn ĐÃ CHỐT (xanh lá) hoặc CHƯA CHỐT (cam) như cũ.
5. Ô ký: "Người lập · 制表" và "Xác nhận của khách hàng · 客户确认".
6. Excel: in khổ A4 ngang vừa bề rộng, hai dòng tiêu đề cột lặp ở mỗi trang (Print_Titles), chân trang "Trang x / y"; bản in trình duyệt cũng lặp tiêu đề cột và không cắt ngang dòng.

Một bảng màu: xanh đậm `#1B3A5C`, xanh nhạt `#E9EEF4`, kẻ `#D5DBE3`, chữ phụ `#5F6B7A`; chữ Arial.

## Ngày / nguồn

30/10/2026, chat: người dùng gửi ảnh mẫu hiện tại và lời sếp. Tham khảo: hướng dẫn thiết kế hóa đơn (ít màu, phân cấp bằng cỡ/độ đậm chữ, bảng kẻ nhẹ, số canh phải, khối tổng nổi bật, ô ký) và mẫu commercial invoice của các hãng giao nhận.

## Hiệu lực và giới hạn

ĐÃ CHỐT yêu cầu làm lại (sếp, qua người dùng). Bố cục cụ thể (1)–(6) do Claude chọn theo `CLAUDE-ALL-01`; **CÒN MỞ: sếp duyệt bản thử** (ảnh/PDF và file Excel mẫu đã gửi người dùng 30/10/2026); sếp muốn đổi gì thì sửa tại `debit-note-xlsx.js` và CSS trong `so-khach-v7-debit-ui.js`. Không đổi dữ liệu, cột, quy tắc tiền hay trạng thái CHỐT của DEBIT-NOTE-01. Chưa có số phiếu (Invoice No.) vì sổ chưa cấp số; thêm sau nếu sếp cần.
