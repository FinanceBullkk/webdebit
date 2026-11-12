# Sổ khách trên điện thoại: bảng chuyến ba cột

Quyết định: [`DIEN-THOAI-CHUYEN-01`](../docs/decisions/dien-thoai-chuyen-01.md). Bản thiết kế: canvas Claude Design, trang "Chuyến trên điện thoại" (phương án B, dữ liệu giả).

## Người dùng và câu hỏi

Chủ nghiệp vụ hoặc sếp mở sổ một khách trên điện thoại, thường lúc đang trao đổi với khách. Câu hỏi theo thứ tự:

1. Tháng này mấy chuyến, cộng bao nhiêu (bằng Phát sinh)?
2. Chuyến nào chưa tính tiền, vì sao?
3. Container X tính bao nhiêu, gồm những khoản gì?
4. Đi ngày nào, tuyến nào, xe/hãng tàu nào?

Không làm trên điện thoại: sửa ô, xóa dòng, duyệt chuyến, thêm điều chỉnh.

## Luồng

1. Dưới 760px, bảng chuyến của tháng hiện ba cột: Ngày chuyến, Số container, Thành tiền. Đầu cột cùng ba nhãn đó.
2. Hàng chưa có giá: "Chưa có giá"; hàng Sheet mới: "Chờ duyệt"; hàng Sheet chưa nối được vào sổ: "Sheet khác"; chờ kiểm, đã loại giữ nhãn đang có.
3. Bấm (hoặc Enter) một hàng: khung chi tiết từ dưới lên, tiêu đề là số container, dòng phụ "Chuyến <STT> · <ngày>". Nội dung:
   - Hãng tàu, Shipper (khi sổ có cột này), Tuyến;
   - Đơn giá, từng cột phụ phí riêng của sổ, Khác, = Thành tiền;
   - câu trạng thái khi chuyến chưa tính vào nợ hoặc Sheet ghi khác;
   - "Sửa chuyến trên máy tính.";
   - nút Chuyến trước / Chuyến sau (theo thứ tự hàng trên bảng), nút Đóng; Esc hoặc bấm nền tối cũng đóng.
4. Sổ tự tải lại khi khung đang mở: khung đọc lại hàng cùng khóa; hàng không còn thì đóng.
5. Dòng điều chỉnh: nhãn và số tiền. Dòng cộng: "Cộng tháng, bằng Phát sinh" và số tổng.

## Dữ liệu

Không thêm API. Khung chi tiết đọc nguyên chữ của các ô đã vẽ (số tiền từ GET qua `fmt`), không cộng trừ lại (ARCH-03). Nhãn cột lấy từ hàng tiêu đề của sổ.

## Tiêu chí xong

- 390×844: trang không cuộn ngang; bảng chuyến không có ô ngoài ba cột; hàng cao ≥ 44px.
- Bấm hàng mở khung, không gửi lệnh nào (không POST), không mở ô sửa.
- Khung hiện đúng Đơn giá, phụ phí, Thành tiền như bảng máy tính của cùng hàng.
- 1280: số đo bố cục sổ không đổi so với trước.
- Test trình duyệt cho các ý trên; `npm run check` xanh.

## Ngoài phạm vi

Sổ có bảng chi tiết theo bảng kê (`SO-CHI-TIET-01`); khối tổng tháng; phiếu thu; Tình hình, Trao đổi, Hồ sơ.
