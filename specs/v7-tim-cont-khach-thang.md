# Tìm số cont và khách theo tháng

Trạng thái: ĐÃ CHỐT (người dùng, 28/11/2026: tìm cont ở ô Tìm khách của menu; Tổng quan xem theo tháng là tiền theo khách, tháng là một lọc của cả trang). Quyết định: [`TIM-CONT-01`](../docs/decisions/tim-cont-01.md), [`KHACH-THANG-01`](../docs/decisions/khach-thang-01.md).

## Người dùng và luồng

Người nhập và quản lý (mọi login, `QUYEN-01`), trên máy tính 1280×720 và điện thoại.

1. **Tìm theo số cont.** Khách gọi hỏi một cont; người dùng gõ số cont (đủ hoặc vài số cuối, có hay không khoảng trắng) vào ô Tìm khách ở menu trái, hoặc hộp đổi khách của Sổ khách. Dưới các khách khớp tên có khối "Số cont": mỗi chuyến một dòng "SỐ CONT · sổ · ngày" (thêm "chờ kiểm" / "sổ gốc"; rê chuột thấy nơi đi → nơi đến). Bấm dòng mở Sổ khách đúng tháng nợ, dòng chuyến có số cont đó được tô vàng, thanh việc có "Đến dòng tiếp" và nút bỏ đánh dấu.
2. **Tháng đó có những khách nào.** Trên thanh đầu Tổng quan, bấm nút "Tất cả tháng" để mở bảng 12 tháng và chọn thẳng một tháng (hoặc ‹ › lùi/tiến một tháng; × bỏ lọc): tháng thành một lọc của cả trang (người dùng chọn 28/11/2026, thay khối riêng cuối trang; audit cùng ngày dời bộ chọn từ thẻ Thu tháng lên thanh đầu). Thẻ ra đã thu / phát sinh của tháng; dải Còn phải thu, khối mặt hàng chỉ tính sổ có số trong tháng; bảng khách còn các sổ đó (cả sổ đã hết nợ) với Phát sinh · Đã thu · Còn nợ của tháng, xếp phát sinh nhiều trước; lọc mức rủi ro, mặt hàng, khách mới chồng lên; chip "T10/2026 ×" để bỏ. Bấm dòng mở Sổ khách tháng đó. `?thang=yyyy-mm` giữ lọc khi gửi link hay tải lại.

Bị chặn: chuỗi tìm ngắn hơn 4 hoặc dài hơn 20 ký tự (bỏ khoảng trắng) hay không có chữ số thì không hỏi máy chủ; không sang tháng sau tháng hiện tại.

## Đầu ra

- Hàm đọc `sokhach.find_container(text)`: chuyến web chưa xóa, không bị loại (cả chờ kiểm) và dòng chuyến sổ gốc theo bản sửa mới nhất, chưa xóa, của mọi sổ đang hoạt động, có số cont chứa chuỗi tìm sau khi bỏ khoảng trắng và viết hoa. Nguyên số trước, rồi ngày chuyến mới trước; tối đa 30 dòng, cờ `more`.
- Hàm đọc `sokhach.get_month_customers(date)`: mỗi sổ có phát sinh, đã thu hoặc còn nợ khác 0 ở tháng đó (trống là tháng hiện tại giờ VN). Phát sinh, đã thu cùng phép tính `this_month` của `get_dashboard_debt` (dòng Tổng tháng của sổ, `DA-THU-01`); còn nợ của tháng là `v_outstanding_month` (như ô Công nợ theo tháng).
- API `GET /api/v7/containers/find?q=` và `GET /api/v7/month-customers[?month=yyyy-mm-01]`, mở cho mọi login; khách theo tháng đi qua bộ nhớ đọc (`HIEU-NANG-01`).
- Migration `2026-11-28-v7-tim-cont-khach-thang.sql`: chỉ thêm hai hàm và quyền `EXECUTE` cho `sokhach_app`, `sokhach_reader`.

## Đối chiếu dữ liệu và code hiện có

- Chuyến web: `v_trip_current` (bản sửa thông tin mới nhất); dòng sổ gốc: `legacy_row.display` hoặc `legacy_trip_rev` mới nhất, như `get_trip_month`, `list_legacy_trip_refs`.
- Phát sinh/đã thu theo tháng đã có cho tháng hiện tại trong `get_dashboard_debt.this_month.customers`; hàm mới tính cùng phép cho tháng bất kỳ (chép CTE `keyed`, `flow_c`; ca harness so hai hàm để hai bản không lệch nhau).
- Tên sổ lấy từ `list_customers` như ô tìm khách (`customerLabels`); sổ không có trong danh sách ghi "Sổ N".
- Sổ khách đã có cơ chế tô dòng `?loc=` (`so-khach-v7-loc-ui.js`); `?cont=` dùng chung thanh và nút.

Thử trên bản sao `webdebit_v7` (28/11/2026, chỉ đọc, đã xóa DB thử): migration hai lượt; tìm cont khoảng 150 ms một lượt, khớp chuyến web và dòng sổ gốc; khách theo tháng tháng hiện tại lệch 0 sổ so với `get_dashboard_debt.this_month`, tháng 10/2026 lệch 0 sổ so với cột tháng 10 của `get_receivables_matrix(2026)`.

## Hành vi và bất biến

- Chỉ đọc: không đổi tiền, phân bổ, version sổ hay dữ liệu.
- VND là chuỗi số nguyên; số 0 hiện "–", số đầy đủ ở chữ rê chuột.
- Container không là khóa duy nhất: cùng số cont ở nhiều sổ/tháng hiện đủ các dòng.
- Sổ đã lưu trữ hoặc chưa có mốc đang hoạt động không có trong kết quả.

## Tiêu chí nghiệm thu

- [x] Harness `TIM-CONT.01` (`tools/test_pg_v7_backend_tim_cont.py`): tìm qua sổ, chuẩn hóa chuỗi, dòng sổ gốc, nguyên số trước, sửa số cont, chuyến xóa bị bỏ, chuỗi sai bị chặn; khách theo tháng bằng `this_month` và ma trận; đọc không đổi version.
- [x] Unittest route (`tests/test_v7_tim_cont_khach_thang.py`), đồng bộ file chuẩn (`tests/test_v7_fee_sql_sync.py`), quyền (`tools/test_pg_v7_grants.py`).
- [x] Trình duyệt: Tổng quan (‹ › lọc cả trang, cột tháng, sổ hết nợ, lọc chồng mức rủi ro, chip bỏ lọc, ?thang=, lỗi + Thử lại, 390px không cuộn ngang; ô tìm cont, phím ↓), Sổ khách (`?cont=` tô chuyến web và dòng sổ gốc, không còn khớp, hộp đổi khách).
- [ ] Người dùng tự đi hết hai luồng trên `hao`.

## Sổ tháng (KHACH-THANG-02, 28/11/2026)

Người dùng chốt phương án A ([`KHACH-THANG-02`](../docs/decisions/khach-thang-02.md)): mỗi bảng khách của Tổng quan một mốc thời gian. Bảng lọc tháng cũ trộn phát sinh và đã thu của tháng với "Còn nợ Tx" (nợ của riêng phát sinh tháng, luôn bằng phát sinh khi khách còn nợ cũ vì thu trừ nợ cũ trước) và các số hôm nay, nên cộng trừ theo hàng không ra.

- **Đầu ra:** `get_month_customers` thêm `prior_months_vnd` (nợ đầu tháng) và `end_of_month_vnd` (còn nợ cuối tháng) mỗi sổ, cùng phép và cùng tên với `months[]` của `get_ledger` (cuối tháng tính lùi từ tổng còn nợ trừ phát sinh − đã thu các tháng sau, cùng tập tháng `month_keys`); giữ mọi trường cũ và tập sổ. Migration `2026-11-28-v7-khach-thang-so-thang.sql` chỉ thay hàm đọc đó.
- **Trang, lọc tháng:** cột Nợ đầu tháng · + Phát sinh · − Đã thu · = Còn nợ cuối tháng, cả bốn bấm để xếp (`?xep=no-dau|phat-sinh|da-thu|no-cuoi`, mặc định phát sinh); tiêu đề "Khách tháng M/YYYY"; không còn Quá hạn, Còn nợ, Trả, Đi hàng. Nợ âm ghi "dư …"; máy chủ cũ thiếu hai số thì ô "—". Điện thoại bỏ cột Nợ đầu tháng để Còn nợ cuối tháng luôn trong màn.
- **Trang, không lọc:** "Trả gần nhất", "Chuyến gần nhất" ghi "27 ngày trước" (quá 90 ngày đếm tháng; "chưa có"), ngày cụ thể ở chú thích, chú giải màu hiện sẵn dưới bảng.
- **Bất biến:** mỗi dòng nợ đầu + phát sinh − đã thu = còn nợ cuối, bằng thanh tháng của Sổ khách cùng sổ, cùng tháng; tháng hiện tại còn nợ cuối tháng = còn nợ hôm nay.

Nghiệm thu:

- [x] Harness `TIM-CONT.01`, phần `check_so_thang`: hai sổ giả, tháng 1/2026 và tháng hiện tại, so `get_ledger` và `get_dashboard_debt`, đẳng thức từng dòng (chạy ở CI: job `postgres-v7-backend` xanh trên PR và commit merge).
- [x] Test model (`monthRows`, `dayCell`, xếp bốn cột tháng) và trình duyệt (cột, thứ tự, xếp, chú thích, chú giải, 390px).
- [x] Bản sao `webdebit_v7` (28/11/2026, đã xóa DB thử): 23 tháng từ 1/2025, 834 dòng sổ × tháng, lệch với `get_ledger` 0, sai đẳng thức 0, tập sổ và ba số cũ không đổi, tháng hiện tại 44/44 sổ khớp còn nợ hôm nay; áp hai lượt khoảng 100 ms, dấu vân DB trùng.
- [ ] Người dùng tự xem trên `hao`.
