# Việc cần làm — bảng bốn cột (2/11/2026)

Người dùng yêu cầu code theo bản HTML đã chọn ngày 2/11: `ViecCanLamBang.dc.html`, tiêu đề “BẢN CHÍNH · bảng 4 cột có chữ”. File nguồn giữ ngoài Git trong Downloads; không nhập runtime React của bản thiết kế.

## Hợp đồng hoàn thành

- Người nhập nhìn số sổ còn việc, người đã ghi hôm nay, rồi bảng Khách / Phiếu thu / Giá chuyến / Chuyến cần xử lý / Thiết lập sổ. Một sổ một dòng; bấm mở chi tiết ngay bên dưới. Bộ lọc Tiền vào sổ, Chuyến, Thiết lập sổ đếm sổ, không đếm việc trùng.
- Hợp nhất `/api/v7/inbox`, `/dashboard`, `/dashboard/debt`, `/customers` bằng ID sổ. Không gộp khách theo tên. Chưa lấy được một nguồn phải báo thiếu, không kết luận hết việc.
- Giữ ghi phiếu qua `/sheet/receipts`, xem lại nợ trước/sau, phiên bản, hash Sheet, khóa chống trùng và kết quả riêng từng sổ. Giá đọc chi tiết `/ledger` trước khi xem lại và gọi `/sheet/prices`; không dựng số tiền từ bộ đếm.
- Chọn chung phiếu và giá: đọc mới từng sổ, xem tổng nợ cuối sau cả hai loại; ghi giá rồi phiếu, dùng phiên bản trả về của lệnh trước. Mất mạng giữ nguyên payload của lô chưa rõ, bỏ qua lô đã xong. Lô lỗi/một phần dừng và yêu cầu mở sổ kiểm tra, không gọi tiếp bằng phiên bản cũ.
- Chi tiết dùng lệnh có sẵn: đơn giá nhập theo triệu đồng (tối đa sáu số lẻ, quy đổi BigInt ra nguyên đồng), kết luận chờ kiểm có lý do bắt buộc, duyệt chuyến mới chưa giá, tách PS giữ tổng, xóa chuyến có xem lại. Tháng khóa giữ đường mở sổ; không tự mở khóa. “Giữ giá web” và “Giữ chuyến” lưu quyết định có người làm trên server theo nội dung dòng liên quan, theo [VCL-GIU-01](../docs/decisions/vcl-giu-01.md). Không thay đổi số dư.
- Việc cần đối chiếu sâu mở đúng sổ bằng đường đang có. Không tự tạo chính sách sửa tiền, ghi dữ liệu thật, sửa Sheet hoặc triển khai. Hàm SQL mới chỉ lưu quyết định Giữ, có migration riêng.
- Kiểm: `npm run check`; browser với fixture ở 1280×560, thanh cuộn dọc, màn hẹp, chữ dài/Hán, dữ liệu trống/thiếu/lỗi, lọc, mở/gập, xem lại/hủy, ghi lỗi và thử lại cùng khóa. Xem ảnh render trước khi bàn giao.

## Map kiểm

| Thao tác | Entry point | Kiểm |
|---|---|---|
| Tải/lọc/mở sổ | `viec-can-lam.js`, `viec-can-lam-inbox.js` | browser bảng bốn cột |
| Ghi phiếu | `viec-can-lam.js` → `/sheet/receipts` | browser P2: lỗi từng sổ, mất mạng/chống trùng |
| Ghi giá | `viec-can-lam.js` → `/ledger` → `/sheet/prices` | browser: xem lại, phiên bản mới, thử lại |
| Chi tiết/soát máy | `viec-can-lam-inbox.js` | browser: đúng ID, không lộ fixture vào production |

Giới hạn: sửa ngày phiếu chưa rõ ngày, giá đang xung đột và thiết lập số dư/mặt hàng dẫn về sổ hiện hành; không giả lập thao tác sửa Sheet hoặc tự đặt nguồn tiền. Giữ nhãn giá và trạng thái thật từ API. Nhập giá theo triệu như package; nhận dấu phẩy hoặc dấu chấm thập phân, không chấp nhận chuỗi có hai dấu. Giá gợi ý chỉ lấy từ `/price-table/status`, giữ đủ độ chính xác khi điền ô. Kiểm fixture không thay kiểm tích hợp hoặc người dùng đi hết luồng trên bản thử.

## Đối chiếu package sau góp ý ngày 2/11

Người dùng yêu cầu giống toàn bộ package, không chỉ dùng bố cục làm cảm hứng. Đã sửa biểu tượng, màu, khoảng cách, nhãn, người ghi dạng chip, bộ lọc có biểu tượng sổ, đếm mục thay cho sổ, tổng tiền phiếu theo triệu, gộp số cần xem, làm mờ cột ngoài nhóm lọc, bảng xem lại và xác nhận tại dòng. Nguồn HTML/runtime giữ ngoài Git; fixture cùng tám khách giả của package kiểm hình học và tổng độc lập. Không coi toàn bộ yêu cầu đã đạt chỉ vì các kiểm này xanh.

Khoảng trống còn phải xử lý trước nghiệm thu toàn bộ package:

- Chưa có API xác nhận ngày của phiếu Sheet thiếu ngày và ghi dấu để hàng chờ không đưa lại; không gọi record_receipt trực tiếp rồi để phiếu vẫn hiện cần xem.
- Giá xung đột: đã nối Giữ giá web có Lịch sử; còn thiếu Lấy giá Sheet. Đường xử lý ô chữ hiện tại không nhận trường giá.
- Chưa có lệnh gán mặt hàng/sổ đích cho chuyến mơ hồ. set_customer_attributes ở schema chỉ là đề xuất, không phải hàm đã có.
- Chưa có hợp đồng hoàn tác lô trả đủ mã phiếu/giá trước và phiên bản để đảo đúng những mục vừa ghi; không làm nút Hoàn tác giả.
- Backend review_trip bắt buộc lý do: chỉ hiện ô lý do khi xác nhận chờ kiểm. Các trường hợp trên hiện giữ đường mở sổ; không tuyên bố giao diện và hành vi giống hoàn toàn.
