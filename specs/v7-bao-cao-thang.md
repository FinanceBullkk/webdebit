# Báo cáo tháng: khách, cont, đối chiếu booking ↔ Sheet ↔ web

Trạng thái: ĐÃ CHỐT (người dùng, 16/11/2026, [`BAO-CAO-THANG-01`](../docs/decisions/bao-cao-thang-01.md)): bố cục, cột Web, tháng theo ngày chuyến, bản chép 0đ. Cách làm là ĐỀ XUẤT của Claude.

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Người mở: chủ sổ, sếp (trên 40 tuổi, Chrome thấy khoảng 1280×560). Chỉ xem, không ghi. Gắn với chỉ số M2 của [`UX-NEN-01`](../docs/decisions/ux-nen-01.md): mỗi container của booking có đúng một chuyến.

Câu hỏi mang tới, theo thứ tự:

1. Tháng này booking có bao nhiêu cont, Sheet và web đã ghi bao nhiêu, thiếu mấy? (bảng tổng)
2. Có những khách nào, mỗi khách loại gì, đi bao nhiêu cont? (bảng theo khách)
3. Khách nào lệch, lệch cont nào, sửa ở đâu? (chip Cần xem, bung danh sách cont, link Mở sổ)

Luồng:

1. Mở mục **Báo cáo tháng** ở menu trái. Mặc định là tháng hiện tại.
2. Nhìn thứ nhất: bảng tổng Booking / Sheet sổ nợ / Web, theo Biển, Bộ, Tổng. Hai hàng lệch ("Booking có, Sheet chưa ghi", "Sheet có, web chưa có") tô đỏ khi khác 0.
3. Nhìn thứ hai: bảng theo khách. Cột: Khách (kèm mặt hàng), Loại, Booking, Sheet, Web, Cần xem, Tiền trên Sheet. Khách có lệch lên đầu. Có ô "Chỉ khách cần xem" và nút lọc Tất cả / Biển / Bộ.
4. Bấm một khách: bung danh sách cont. Cột: Container, Ngày chuyến, Booking (ngày, số booking), Sheet (dòng, khối tháng nếu khác, tiền), Web (ngày), Tình trạng. Dưới danh sách có link "Mở sổ tháng …". Bấm lại thì thu.
5. Đổi tháng bằng ‹ › hoặc ô chọn tháng. Tháng, ô lọc và biển/bộ giữ trên địa chỉ để gửi link.

Sửa ở đâu: Sheet vẫn là sổ chính thức tới ngày chuyển hẳn ([`SONG-SONG-01`](../docs/decisions/song-song-01.md)), nên chỗ thiếu sửa trên Sheet. Lượt máy sau tự cập nhật. Chuyến web sửa trong sổ.

Không có điều kiện bị chặn vì trang không ghi gì.

## Đầu ra

- Trang `/bao-cao-thang.html`, mục thứ năm của menu trái.
- Đọc `GET /api/v7/report/month?month=YYYY-MM`.
- Tháng 10/2026 trên `hao` cho cùng số với file Excel đối chiếu đã gửi người dùng: booking 463, Sheet 460–461, thiếu 2–3, tùy Sheet sửa thêm.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- **Booking ↔ Sheet:** `tools/v7_booking_check.py` đã đọc sổ gốc và hai bản chụp mỗi giờ (KIEM-BOOKING-01). `evaluate()` trả thêm `month_report()`, ghi `booking-report.json` cạnh `booking-check.json`, cùng lượt đạt; lượt lỗi giữ file cũ.
  - Mỗi dòng có: `tab`, `row`, `block` (khối tháng Sheet), `cont`, `family` (`BIEN`/`BO`/null), `amount_vnd` (chuỗi hoặc null), `date` (ngày Sheet), `status`, `booking` {`date`, `owner`, `ref`}.
- **Trạng thái:**
  - `khop`: Sheet ghép booking.
  - `lech_ngay`: lệch 4–31 ngày.
  - `khong_booking`: Sheet có ngày, booking không có.
  - `khong_ngay`: Sheet không ngày.
  - `chep`: bản chép 0đ.
  - `ngoai`: hàng nhập, bán cước.
  - `thieu`: booking có, Sheet chưa ghi.
  - Chuyến trước tháng đầu của tab khách chỉ đếm ở `before_book`.
- **Web:** hàm đọc mới `sokhach.get_trip_month(date)` trả:
  - `books` (id, tên, mặt hàng, biển/bộ của mọi sổ đang hoạt động);
  - `trips` (sổ, ngày, container, nguồn web/sổ gốc) có container, ngày từ 3 ngày trước tới 3 ngày sau tháng.

  Không có hàm sẵn nào đếm chuyến theo sổ và tháng ngày chuyến: các hàm đang có đều theo tháng nợ.
- **Ghép tên tab ↔ sổ:** theo tên, bỏ khoảng trắng thừa, như `may-chay-booking.js`. Tên trùng thì không ghép.
- **Định dạng:** `CongNoFormat.short`, `dateText`, `monthTitle`, `loadError`. Thanh đầu, nút tháng theo Bảng thu.

## Giao tiếp frontend–backend (bước 5)

`GET /api/v7/report/month[?month=YYYY-MM]`, sau xác thực danh tính như mọi route. Không có `month` thì lấy tháng hiện tại theo giờ VN. Tháng sai dạng, sau tháng hiện tại, hoặc có tham số khác: 422 `INVALID_MONTH`.

Trả về:
- `month`, `now`, `checked_at`, `start`, `end`, `current`, `before_book`.
- `state`:
  - `ok`;
  - `stale`: lượt đạt gần nhất cũ hơn lượt liền trước lượt theo lịch;
  - `none`: chưa có file;
  - `outside`: tháng ngoài khoảng có booking.
- `totals.{BIEN,BO,ALL}` có các trường:
  - `booking`, `sheet`: null khi chưa có số;
  - `web`, `thieu`, `khong_booking`, `lech_ngay`, `khong_ngay`, `chep`, `ngoai`, `chi_web`, `web_thieu`;
  - `amount_vnd` (chuỗi), `issues`.
- `customers[]`: các trường như trên, kèm `name` (tên tab, hoặc null), `owner` (chủ hàng khi chưa rõ sổ), `book_id`, `commodity`, `families`, `rows` (từng cont, thêm `web` {`date`, `source`} hoặc null).

Lỗi tải thì trang hiện câu theo mẫu `loadError` và nút Thử lại.

## Hành vi và bất biến

- Chỉ đọc: không ghi DB, sổ hay Sheet. Không đổi luật tiền, luật ghép hay điều kiện máy ghi.
- NULL khác 0: tháng chưa có booking thì Booking/Sheet hiện "—", không hiện 0. Ô tiền trống hiện "—".
- VND nguyên: tiền là chuỗi, cộng bằng int ở API. UI chỉ định dạng (ARCH-03).
- Bản chép 0đ không đếm là chuyến. Dòng không ngày không đếm là chuyến nhưng tiền vẫn vào cột tiền.
- Chuyến trong số dư đầu kỳ không cộng lại.
- File báo cáo có tên tab khách và số tiền: mode 600, chỉ trên `hao`. Stdout và journal chỉ có số đếm.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_booking_check.py` (`MonthReportTests`): mọi trạng thái, tháng theo ngày booking, bản chép lệch 19 ngày, trước sổ chỉ đếm, file giữ khi lượt lỗi.
- [x] `tests/test_v7_month_report.py`: đếm theo khách và biển/bộ, ghép web lệch 2 ngày, tên sổ khác khoảng trắng, chuyến chỉ trên web, tháng ngoài khoảng, file cũ, route và tháng sai.
- [x] `tests/test_v7_fee_sql_sync.py`: hàm trong migration trùng file chuẩn. Hàm đọc nằm trong danh sách quyền (grants, schema, post-deploy check).
- [x] `preview/test-bao-cao-thang-model.js`, `preview/test-bao-cao-thang-browser.js`: bảng tổng, chip, bung cont, link mở sổ, lọc, đổi tháng, lỗi và Thử lại, menu tám mục lọt 1265×560, không cuộn ngang.
- [x] `npm run check` xanh.
- [ ] Harness PostgreSQL (`tools/test_pg_v7_*.py`) trên CI.
- [ ] Trên `hao`: tháng 10/2026 ra cùng số với lần đối chiếu tay; tháng 11 có "Chưa lên Sheet".
- [ ] Người dùng tự đi hết trang trên `hao` và xác nhận.
