# SO-GON-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chốt nhóm P0 của audit giao diện sổ khách V7, theo bản xem [`preview/mockups/so-khach-p0`](../../cong-no-web-handoff/preview/mockups/so-khach-p0/index.html) (dữ liệu giả), **phương án A**:

1. **Phiếu thu là danh sách riêng bên phải**, vẫn đặt cạnh chuyến như Sheet nhưng không chung hàng với chuyến. Mục đích: không còn đọc nhầm "chuyến này trả số tiền này". Thứ tự trong danh sách: khoản thu Sheet (giữ thứ tự Sheet), phiếu web, hàng nhập phiếu ở cuối như [`SO-GON-01`](so-gon-01.md). Danh sách dính dưới dòng tháng khi cuộn, nếu cả danh sách vừa màn hình. Điểm này thay cách ghim từng ô thu của góp ý ngày 28/10.
2. **Phiếu đã hủy** rời danh sách phiếu và gom thành một dòng mờ "n phiếu đã hủy, không tính tiền · Xem". Bấm Xem thì hiện từng phiếu: số tiền gạch · ngày phiếu · ngày hủy · lý do. Bỏ các dòng vết hủy kéo hết bề ngang dưới tháng.
3. **Bỏ cột "Còn nợ cộng dồn"** (cột này luôn trống). Thanh tháng ghi: nợ các tháng trước · phát sinh · đã thu · còn nợ cuối tháng. Dòng Tổng tháng ghi đã thu và còn nợ cuối tháng ở vùng phiếu thu. **Sửa 29/10/2026:** thanh tháng chỉ còn còn nợ cuối tháng, dòng Tổng tháng chỉ còn đã thu — xem [`SO-GON-03`](so-gon-03.md). Dòng vừa chuyển tháng ghi "↪ Vừa chuyển từ Tn" ở một dòng mảnh ngay dưới dòng đó.
4. **Phụ phí trống** luôn hiện "–" màu nhạt, giống nhau giữa chuyến web và dòng sổ gốc. Ô phụ phí vẫn rỗng khi sửa. Thiếu đơn giá vẫn tô cam.
5. **Mỗi chuyến chỉ một hàng.** Chữ dài ở các cột container … nơi đến bị cắt "…", rê chuột xem đủ. Số container dùng font đều chữ. Phiếu chưa có tham chiếu không còn ghi "Tham chiếu: –", chỉ còn dấu "+" nhỏ để thêm tham chiếu.

## Ngày / nguồn

29/10/2026, audit UX trong chat. Người dùng xem bản mockup có hai phương án đặt phiếu thu, hỏi ý kiến Claude, rồi chọn "A".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi phần hiển thị của trang live (`so-khach-v7-ui.js`, các phần `so-khach-v7-*-ui.js`, `so-khach-v7-live.html`). Không đổi luật tiền, API hay DB: mọi số vẫn lấy nguyên từ GET. Trang mẫu fixture `so-khach-v7.html` giữ bố cục cũ. Cột phụ phí sẽ đổi theo [`PHU-PHI-01`](phu-phi-01.md), và quy tắc "trống ghi –" áp dụng cho mọi cột phụ phí. Các mục P1/P2 của audit (xếp chuyến theo ngày, danh sách tháng, cỡ chữ) CÒN MỞ, chưa thuộc quyết định này.
