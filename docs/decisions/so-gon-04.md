# SO-GON-04

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt luồng sổ khách V7 "một sổ, một tháng đang làm" theo spec [`v7-so-khach-ux-dot-2.md`](../../specs/v7-so-khach-ux-dot-2.md) (đợt 2 của [audit UX 31/10/2026](../ux-audit-2026-10-31.md)), lấy đúng phương án Claude đề xuất cho sáu câu hỏi:

1. **H1 · Tháng mở sẵn:** lúc mở sổ chỉ có tháng hiện tại (giờ VN) và tháng liền trước. Các tháng cũ thu gọn thành một dòng (tên tháng, ổ khóa, số chuyến, Còn nợ cuối tháng, Debit note, nút "Xem chi tiết"); có thanh chip tháng dính ở đầu sổ. Chip của tháng đang xem được tô, làm thay việc "dính đầu khi cuộn" của thanh tháng trong [`SO-GON-03`](so-gon-03.md) (1): thanh của từng bảng tháng không dính nữa, để phần dính đầu trang còn ≤ 180px như tiêu chí của spec.
2. **H2 · Chỗ ghi phiếu thu:** một nút chính "Ghi phiếu thu" ở đầu sổ mở khung bên phải, theo mẫu ngăn phụ phí. Bỏ khung "Ghi phiếu mới" ở cuối từng tháng.
3. **H3 · Sửa phiếu vừa ghi nhầm:** băng kết quả có nút "Hủy phiếu vừa ghi". Nút này mở dòng hủy phiếu đang có, lý do điền sẵn "Ghi nhầm, hủy ngay sau khi ghi" (sửa được); người dùng tự bấm Hủy phiếu. **Không** có "Hoàn tác" một chạm, nên quy tắc hủy phiếu bắt buộc lý do của [`V7-SO`](v7-so.md) không có ngoại lệ.
4. **H4 · Cỡ chữ khi 16px không vừa 1280:** số tiền giữ 16px, cột chữ (container, hãng tàu, nơi đi/đến) được xuống 15px. Không làm ẩn/hiện cột trong đợt này.
5. **H5 · Phân bổ phiếu thu:** bước xem lại trước khi ghi chỉ hiện tổng còn nợ trước → sau, kèm câu "khách dư" hoặc "tháng đang khóa" khi có. Phân bổ từng tháng hiện ngay sau khi ghi, theo đúng `allocations` server trả về. Không thêm hàm đọc thử ở DB.
6. **H6 · Hỏi lại khi khóa/mở tháng:** hỏi cả khi khóa lẫn khi mở khóa, kể cả nút "Mở khóa tháng" trong khung giá Sheet.

**Sửa 31/10/2026 (đầu sổ, L7 của spec — PR 2c):** người dùng đồng ý ba điểm Claude làm khác spec khi code ("Đồng ý, merge"):
(a) không có menu "Thêm ▾": đầu sổ dính giữ ô tìm khách, nút chính Ghi phiếu thu, nút phụ Lịch sử và Tổng còn nợ; Cài đặt phụ phí,
Bảng giá và các nút việc chờ nằm ở một dải ngay dưới đầu sổ, luôn thấy; (b) "Làm mới" và "Ẩn con trỏ" ở bên phải dải đó, không có
menu "Đang xem"; thanh xanh trên cùng chỉ còn tên trang và điều hướng; (c) chưa nạp chung `cong-no-theme.css` cho cả trang sổ khách.

## Ngày / nguồn

31/10/2026, chat. Claude đưa spec kèm sáu câu hỏi, mỗi câu có một phương án ghi "(đề xuất)" ([PR FinanceBullkk/webdebit#227](https://github.com/FinanceBullkk/webdebit/pull/227)); người dùng trả lời "Chốt theo đề xuất".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thanh tháng và thu gọn tháng (PR FinanceBullkk/webdebit#228), khung Ghi phiếu thu (PR FinanceBullkk/webdebit#231) đã triển khai trên `hao` 31/10/2026; cỡ chữ và đầu sổ (PR FinanceBullkk/webdebit#232) triển khai khi merge; Lịch sử viết thành câu và bàn phím (PR 2d) chưa code. Chỉ đổi giao diện trang live `so-khach-v7-live.html` và các phần `so-khach-v7-*-ui.js`. Không đổi luật tiền, phân bổ, khóa tháng, API hay DB: mọi số vẫn lấy nguyên từ GET. Trang mẫu fixture `so-khach-v7.html` giữ nguyên. Thay hai điểm của [`SO-GON-01`](so-gon-01.md): phần "hàng nhập phiếu thu nằm ở hàng kế tiếp sau phiếu cuối của tháng" (sửa 23/10) và phần "danh sách tháng" bên phải của trang live. Thay vế "dính đầu khi cuộn" của thanh tháng trong [`SO-GON-03`](so-gon-03.md) (1); nội dung thanh tháng (tên tháng, ổ khóa, Còn nợ cuối tháng, rê chuột xem cách tính) giữ nguyên. Các điểm khác của `SO-GON-01`/`-02`/`-03` giữ nguyên. Hàng nhập chuyến của mục 4.2.6 trong audit không thuộc quyết định này vì [`NHAP-SHEET-02`](nhap-sheet-02.md) đã bỏ bảng nhập chuyến. Còn mở: phần dính đầu trang ≤ 110px (cần thu thanh xanh trên cùng ở mọi trang); đợt này nhắm ≤ 180px.
