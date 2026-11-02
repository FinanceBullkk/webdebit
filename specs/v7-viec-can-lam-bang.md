# Việc cần làm — bảng bốn cột (2/11/2026)

Người dùng yêu cầu code theo bản HTML đã chọn ngày 2/11: `ViecCanLamBang.dc.html`, tiêu đề “BẢN CHÍNH · bảng 4 cột có chữ”. File nguồn giữ ngoài Git trong Downloads; không nhập runtime React của bản thiết kế.

## Hợp đồng hoàn thành

- Người nhập nhìn số sổ còn việc, người đã ghi hôm nay, rồi bảng Khách / Phiếu thu / Giá chuyến / Chuyến cần xử lý / Thiết lập sổ. Một sổ một dòng; bấm mở chi tiết ngay bên dưới. Bộ lọc Tiền vào sổ, Chuyến, Thiết lập sổ đếm sổ, không đếm việc trùng.
- Hợp nhất `/api/v7/inbox`, `/dashboard`, `/dashboard/debt`, `/customers` bằng ID sổ. Không gộp khách theo tên. Chưa lấy được một nguồn phải báo thiếu, không kết luận hết việc.
- Giữ ghi phiếu qua `/sheet/receipts`, xem lại nợ trước/sau, phiên bản, hash Sheet, khóa chống trùng và kết quả riêng từng sổ. Giá đọc chi tiết `/ledger` trước khi xem lại và gọi `/sheet/prices`; không dựng số tiền từ bộ đếm.
- Chọn chung phiếu và giá: đọc mới từng sổ, xem tổng nợ cuối sau cả hai loại; ghi giá rồi phiếu, dùng phiên bản trả về của lệnh trước. Mất mạng giữ nguyên payload của lô chưa rõ, bỏ qua lô đã xong. Lô lỗi/một phần dừng và yêu cầu mở sổ kiểm tra, không gọi tiếp bằng phiên bản cũ.
- Chi tiết dùng lệnh có sẵn: đơn giá nguyên đồng, kết luận chờ kiểm có lý do bắt buộc, duyệt chuyến mới chưa giá, tách PS giữ tổng, xóa chuyến có xem lại. Tháng khóa giữ đường mở sổ; không tự mở khóa. “Giữ” chuyến Sheet xóa chỉ nhớ theo bản chụp trên trình duyệt như sổ hiện hành, không là ghi DB.
- Việc cần đối chiếu sâu mở đúng sổ bằng đường đang có. Không tạo chính sách sửa tiền, thay đổi schema, dữ liệu thật, Sheet hoặc triển khai.
- Kiểm: `npm run check`; browser với fixture ở 1280×560, thanh cuộn dọc, màn hẹp, chữ dài/Hán, dữ liệu trống/thiếu/lỗi, lọc, mở/gập, xem lại/hủy, ghi lỗi và thử lại cùng khóa. Xem ảnh render trước khi bàn giao.

## Map kiểm

| Thao tác | Entry point | Kiểm |
|---|---|---|
| Tải/lọc/mở sổ | `viec-can-lam.js`, `viec-can-lam-inbox.js` | browser bảng bốn cột |
| Ghi phiếu | `viec-can-lam.js` → `/sheet/receipts` | browser P2: lỗi từng sổ, mất mạng/chống trùng |
| Ghi giá | `viec-can-lam.js` → `/ledger` → `/sheet/prices` | browser: xem lại, phiên bản mới, thử lại |
| Chi tiết/soát máy | `viec-can-lam-inbox.js` | browser: đúng ID, không lộ fixture vào production |

Giới hạn: sửa ngày phiếu chưa rõ ngày, giá đang xung đột và thiết lập số dư/mặt hàng dẫn về sổ hiện hành; không giả lập thao tác sửa Sheet hoặc tự đặt nguồn tiền. Giữ nhãn giá và trạng thái thật từ API. Bản thiết kế nhập giá bằng triệu; bản code nhập nguyên đồng và ghi rõ `(đ)` để tái dùng validation của sổ, tránh sai đơn vị. Kiểm fixture không thay kiểm tích hợp hoặc người dùng đi hết luồng trên bản thử.
