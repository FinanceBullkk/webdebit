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

Khối tổng tháng; Tình hình, Trao đổi, Hồ sơ. (Bảng kê và phiếu thu: xem phần mở rộng bên dưới.)

## Mở rộng 12/11/2026: bảng kê và phiếu thu

Quyết định: ý 6–7 của `DIEN-THOAI-CHUYEN-01`. Không thêm API, không đổi số.

- Bảng kê (`SO-CHI-TIET-01`) dưới 760px: luôn bảng gọn (`so-khach-v7-detail-ui.js` không vẽ "Đủ cột", lựa chọn đã nhớ giữ nguyên cho máy tính); ba cột Số container · Ngày đóng · = Tổng; nhãn tình trạng dưới container; bấm dòng bung tại chỗ; dòng cộng ghi cả cước khách tự trả (không tính).
- Phiếu thu: mỗi phiếu hai dòng (ngày, số tiền; rồi hình thức · tham chiếu · phân bổ).

Tiêu chí: 390×844 không cuộn ngang, không ô nào của bảng kê ra ngoài màn, hàng ≥ 44px, không gửi lệnh khi bấm dòng; số tiền phiếu thu nằm trong màn, cùng dòng với ngày; 1280 giữ bảng như cũ. Test: `test-so-khach-v7-phone-browser.js`.

## Mở rộng 12/11/2026: hộp Debit note

Quyết định: [`DIEN-THOAI-DEBIT-01`](../docs/decisions/dien-thoai-debit-01.md). Không thêm API, không đổi số hay chứng từ.

- Dưới 760px hộp phủ cả màn, một cột cuộn dọc: dòng Chặn/Cảnh báo và ô xác nhận ngay dưới ba nút, rồi form, rồi bản xem trước thu vừa khung (`so-khach-v7-debit-ui.js` đặt zoom theo bề ngang khung; màn rộng giữ .6 cho v4, .82 cho v3).
- Nút xuất đang khóa mờ đi ở mọi cỡ màn.

Tiêu chí: 390×844 hộp đúng 390×844, ba nút ≥ 44px nằm trong màn, cột kiểm rộng 390px và nằm trên form, không cuộn ngang trong hộp lẫn trong khung xem trước; 1280 về hai cột, form 320px. Test: `test-so-khach-v7-debit-v4-browser.js`.
