# DONG-MO-BOOKING-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Sổ khách cho người dùng biết **chuyến của tháng có đủ theo booking chưa**, ngay ở bảng chuyến, theo tiêu chí số 1 của [`DU-CHUYEN-01`](du-chuyen-01.md).

Người dùng chốt cách hiện:

- **Chuyến booking có mà sổ chưa có** hiện thành **một dòng mờ ở cuối bảng chuyến** của tháng ngày booking. Dòng có cùng cột với dòng thật: container, nhãn `CHƯA VÀO SỔ`, ngày booking, và link "Xem" ở cột Thành tiền.
- **Khi khớp, màn không đổi gì.** Không có dấu ✓, nhãn, màu hay chấm mới.

Hai bản phác thảo trước (một nhãn cạnh tiêu đề "Chuyến trong tháng", rồi bản rút còn icon và con số) bị loại vì nhiều chữ và gây rối. Lệch chỉ xảy ra hiếm (đo 24/11/2026: 4 chuyến tháng 11 trên toàn bộ sổ), nên tín hiệu chỉ hiện khi có ngoại lệ, và hiện bằng chính dạng dòng của bảng.

Phần cách làm (Claude chọn, ĐỀ XUẤT):

- **Nguồn:** file `booking-web.json` của lượt so sổ web mỗi giờ. Dòng nhóm `CHUA_TINH` (tháng trước) và `THANG_CUOI` (tháng này) mang mã sổ gợi ý (`suggest.customer_id`). Job gắn mã này theo tên sổ; tên trùng hai sổ thì không gắn. Chủ hàng chưa có sổ vẫn đi qua thẻ Khách ([`KHACH-WEB-01`](khach-web-01.md)), không hiện ở sổ nào.
- **Không hiện chuyến sổ đã có.** `GET /api/v7/ledger` trả `booking_missing`, sau khi bỏ chuyến mà sổ đã có: cùng container, lệch không quá 3 ngày; dòng không ngày thì cùng tháng. Chuyến "chờ kiểm" và "đã loại" tính là đã có, vì người đã kết luận. Nhờ vậy chuyến máy hay người vừa thêm không phải chờ tới lượt sau mới hết hiện mờ.
- **Không lặp với dòng Sheet.** Chuyến đã hiện thành dòng Sheet chờ ("CHỜ DUYỆT", "CHỜ TAB SHEET") thì không vẽ thêm dòng mờ.
- **Chữ:** chỉ một nhãn trên màn. Câu giải thích ở chữ rê chuột, khác nhau giữa tháng từ 10/2026 (máy thường tự đưa vào ở lượt sau) và tháng cũ (máy không tự thêm, chủ sổ kết luận theo `DU-CHUYEN-01` (3)).
- **Không có nút ghi.** "Xem" mở danh sách "web chưa có" của Báo cáo tháng ([`BAO-CAO-THANG-01`](bao-cao-thang-01.md), BAO-CAO-THANG-02), nơi ghi vì sao máy chưa đưa chuyến vào sổ.
- Dòng mờ không đổi số chuyến ở tiêu đề, không thêm việc trên chip tháng, không hiện trên điện thoại (như dòng "CHỜ TAB SHEET") và không hiện ở bảng chi tiết.

## Ngày / nguồn

25/11/2026, chat. Người dùng: "sheet sổ khách này mình nghĩ là nơi người dùng vào nhiều nhất. Chúng ta nên có 1 cái chỉ báo để người dùng biết số cont ở tháng này có đúng = số trên booking ko?" Claude phác thảo hai bản. Người dùng chê "nhiều chữ", rồi "gây rối và confused user ở màn này". Claude đề xuất hai hướng: dòng mờ trong bảng, hoặc không hiện ở Sổ mà chỉ ở Việc cần làm. Người dùng chọn "Dòng mờ trong bảng", rồi "Làm đi".

## Hiệu lực và giới hạn

ĐÃ CHỐT cách hiện. Cách làm là ĐỀ XUẤT. Chỉ đọc: không ghi sổ, DB hay Sheet, không đổi luật tiền hay luật ghép, không có migration.

Mã:
- `v7_booking_check.book_ids`;
- `v7_booking_view.book_missing`, `load_web`;
- `booking_projection` trong `v7_api_sheet.ledger_projections`;
- `bookingMissingRows` (`so-khach-v7-trips-ui.js`), lọc theo tháng ở `so-khach-v7-month-ui.js`.

Giới hạn:
- Kết quả theo lượt mỗi giờ (7–22 giờ). Chuyến vừa vào một **sổ khác** vẫn hiện mờ ở sổ gợi ý tới lượt sau.
- Sau khi triển khai, dòng mờ chỉ có từ lượt đối soát đầu tiên chạy mã mới; file cũ không có mã sổ thì không hiện gì.
- Chỉ loại "booking có, sổ chưa có". Các nhóm "trên sổ, booking không có" và "nghi tính hai lần" chưa hiện ở Sổ khách; phần lớn nằm ở tháng cũ đang chờ chủ sổ kết luận (`DU-CHUYEN-01`, CÒN MỞ).
- CÒN MỞ: người dùng tự xem dòng mờ trên `hao`.
