# Kiểm 47 chuyến booking tháng cũ, sửa nhóm 1 và 2 (25/11/2026)

**ĐÃ CHẠY trên `hao` ngày 25/11/2026, 05:33–05:40 giờ VN.** Theo [`TU-LAM-01`](../decisions/tu-lam-01.md) (sửa dữ liệu, tạo sổ không hỏi trước, backup trước, đối soát tổng khách sau). Người dùng hỏi có xử lý luôn các tháng trước 10/2026 không ([`DU-CHUYEN-01`](../decisions/du-chuyen-01.md) (3)), chọn "audit và kiểm tra giúp", rồi chọn "Sửa nhóm 1 và 2" trong chat cùng ngày.

| Mục | Kết quả |
| --- | --- |
| Code | Không đổi. Release đang chạy `19780181` |
| DB | 5 lệnh `edit_legacy_trip` (người làm `claude`), mỗi lệnh mở rồi khóa lại đúng tháng của dòng; 1 lệnh `create_book_from_sheet` (sổ 248) |
| Backup | `v7-20261125-053302` (backup giờ chạy tay ngay trước, thành công) |
| Bằng chứng | `/srv/v7/backup-20261125-kiem-thang-cu/` trên `hao` (thư mục 700): kịch bản, chạy thử, kết quả ghi, tổng từng sổ trước/sau, danh sách thiếu sau khi sửa |

## Kiểm 47 chuyến (chỉ đọc)

Đầu vào: `booking-web.json` của lượt 05:05, bản chụp booking (`CONT_NGUON`, `CONT_BO`), bản chụp giá (tab Sheet sổ nợ), chuyến web mọi sổ lấy trong giao dịch `READ ONLY`. Mỗi chuyến được so với cả ba nguồn: dòng booking cùng container, dòng web cùng container ở mọi sổ (dòng nào đã có dòng booking khác nhận), dòng tab cùng container. Danh sách có tên khách và số tiền giữ ngoài Git.

| Nhóm | Số chuyến | Kết luận |
| --- | ---: | --- |
| 1. Đã có trên sổ web, chỉ ghi khác | 10 | Ngày sai năm, ngày lạ, đảo ngày/tháng, ô container có chữ thừa, hoặc sổ ghi ở tháng nợ khác tháng của ngày booking |
| 2. Sheet có, web chưa có sổ | 1 | Tab một chuyến, khách đã trả đủ; khối mới nhất của TONG không có tên nên máy tạo sổ ([`MAY-TAO-SO-01`](../decisions/may-tao-so-01.md)) bỏ qua |
| 3. Booking ghi lặp | 5 | Cùng xe, cùng container, cách 2–5 ngày; sổ và tab chỉ có một chuyến |
| 4. Có thể là chuyến thật chưa tính tiền | 14 | Container chạy lại sau 7–31 ngày mà tab không ghi; gồm một chuyến bộ tháng 8/2025, lúc đầu xếp vào nhóm 1, xem lại thì booking chuyến bộ chỉ bắt đầu từ 8/2025 nên hai dòng web tháng 7 không phải chuyến này |
| 5. Không có ở đâu | 17 | Cả sổ web lẫn tab đều không có container quanh ngày đó |

## Sửa nhóm 1 (chỉ dòng giữ nguyên tháng nợ)

`edit_legacy_trip` đổi ô ngày thì tháng nợ đổi theo ngày mới (đọc định nghĩa hàm trên `hao`), nên chỉ sửa dòng mà ngày theo booking vẫn nằm trong tháng nợ đang ghi:

| Sổ | Ô | Trước → sau |
| --- | --- | --- |
| 144 | ngày | ngày tab khác tháng nợ → ngày booking, cùng tháng nợ |
| 176 | ngày | năm 1909 → ngày booking |
| 149 | ngày | năm trước → cùng ngày, đúng năm |
| 43 | ngày | đảo ngày/tháng → ngày booking |
| 121 | container | số container kèm ghi chú → chỉ số container |

Không sửa 5 dòng của một sổ mà booking ghi tháng sau tháng nợ (đổi ngày sẽ chuyển tiền sang tháng khác), cũng không điền ngày cho dòng sổ 121 (cùng lý do). Chủ sổ quyết tháng nào đúng.

Mỗi lệnh: kiểm giá trị cũ đúng như đã đọc, mở tháng, sửa, khóa lại trong `finally`, đọc lại sổ. Tổng nợ và từng tháng (phát sinh, đã thu, còn nợ, cuối tháng) của mỗi sổ giống hệt trước khi sửa. Cả 5 tháng đã khóa lại (đọc lại sau cùng).

## Sửa nhóm 2: tạo sổ 248

- Đọc tab và TONG trong bản tải mới của Sheet sổ nợ (tài khoản máy, chỉ đọc): khối tháng 7/2026 của TONG có tên tab, phát sinh bằng đã thu, còn 0.
- Dựng sổ bằng đúng bộ đọc của máy tạo sổ (`v7_export_clean.build_books`): 1 dòng chuyến, 1 dòng thu cùng tháng, số dư 0. Bộ đọc giữ tab với lý do duy nhất `NOT_ON_TONG` (chỉ xét khối mới nhất). Kịch bản nhận tab như `admit_new_tabs` làm khi tab có trên TONG, rồi chạy `validate_books`, sau đó `create_book_from_sheet` (người làm `claude`).
- Sổ 248 tạo xong: số dư 0 bằng số trên tab, 1 chuyến.

## Kiểm sau cùng

- Tổng nợ mọi sổ: 247 sổ trước, 248 sổ sau, tổng không đổi một đồng; không sổ cũ nào đổi số dư.
- So sổ web với booking (cùng `evaluate_web`, bản chụp lượt 05:05, chạy ngay sau khi sửa): thiếu 47 → 42; chuyến booking đã có trên web tăng đúng 5. Dòng sổ 121 vẫn trong nhóm thiếu (tháng nợ trước tháng booking), đúng dự kiến.

## Rollback

- Sổ 144, 176, 149, 43, 121: sửa lại ô về giá trị cũ bằng `edit_legacy_trip` (giá trị cũ ghi trong `evidence-write.json` và Lịch sử của từng sổ), mở và khóa lại tháng như trên.
- Sổ 248: lưu trữ sổ (số dư 0). Backup `v7-20261125-053302` là bản trước.

## CÒN MỞ

- Nhóm 3: xóa 5 dòng lặp ở `CONT_BO` (việc của người giữ file booking).
- Nhóm 4 và 5 (31 chuyến): chủ sổ xác nhận chuyến thật, chuyến hủy hay không tính tiền. Có hai chuyến bộ giá cao không có ở sổ hay tab nào.
- Nhóm 1 còn lại: 5 dòng sổ ghi tháng nợ trước tháng booking, và dòng sổ 121; chủ sổ quyết tháng.
- Chuyến sau này của chủ hàng sổ 248 cần gán tên booking ở thẻ Khách ([`KHACH-WEB-01`](../decisions/khach-web-01.md)) nếu muốn tự vào sổ.
