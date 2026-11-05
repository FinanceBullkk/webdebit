# Bảng chi tiết của sổ theo bảng kê gửi khách

Trạng thái: ĐÃ CHỐT (chủ nghiệp vụ, 4–5/11/2026, chat; phạm vi: chỉ xem, sổ có tab chi tiết). Quyết định: [`SO-CHI-TIET-01`](../docs/decisions/so-chi-tiet-01.md).

## Người dùng và luồng

Người theo dõi công nợ mở Sổ khách của một sổ mà Sheet ghi mỗi container hai dòng. Hiện tại sổ hiện hai dòng, dòng thứ hai là "Phí lẻ", nên không đọc được một container tính bao nhiêu và tiền nào là của mình.

1. Mở sổ, chọn tháng: bảng gọn, mỗi container một dòng. Đọc được phép cộng ngay trên cột: Phí mình thu + Cước tàu mình thu = Tổng. Cước khách tự trả đứng ngoài phép cộng.
2. Muốn biết một chuyến tính bao nhiêu: bấm cả dòng, dòng bung tại chỗ thông tin chuyến và từng khoản có dấu + =.
3. Đầu tháng hoặc thanh chuyến báo còn việc: bấm "N chưa giá" hoặc chip Chưa có giá, Đối chiếu bảng kê, Chưa có trên bảng kê để chỉ xem các dòng đó; bấm lại để bỏ.
4. Cần đối chiếu đúng thứ tự file: chọn Đủ cột (15 cột).
5. Cần sửa: bấm nút bút chì "Sửa ở bảng sổ", làm như cũ. Bảng và chế độ xem được nhớ theo trình duyệt.

Người nhập chép tab bảng kê sang Sheet thành tab tên `CHI TIET ...`, chỉ giá trị, giữ nguyên ô. Có bảng kê mới thì dán lại.

## Đầu ra

Sổ có ít nhất một nửa container trong tab chi tiết thì mặc định hiện bảng gọn; sổ khác không đổi. Số nợ, phiếu thu, đối soát, máy tự ghi không đổi.

Vì sao gọn thay cho 15 cột: một nửa số tháng của sổ thật có cả cước mình thu lẫn khách tự trả, nên hai loại phải tách cột; 15 cột chữ nhỏ làm cắt tên kho. Thứ tự chú ý trong khung 1280×560: số chuyến và chip việc còn lại, rồi cột Tổng, rồi trạng thái từng dòng.

## Trạng thái một dòng

Backend xếp mỗi dòng vào đúng một `state`, theo thứ tự ưu tiên dưới đây; trang đọc nguyên, không tự suy.

| `state` | Khi nào | Bảng gọn | Khi bung |
| --- | --- | --- | --- |
| `no_price` | Sổ chưa có giá, kể cả khi bảng kê có số | Nền cam "Chưa có giá", Tổng "–" | "Chờ giá từ Sheet. Chuyến này chưa tính vào nợ." Bảng kê có số thì ghi "Bảng kê ghi" |
| `loose` | Dòng tiền không gắn container | "Phí lẻ", "Không gắn container" | Sổ đang tính |
| `no_detail` | Có container, không có trên bảng kê | Chữ xám "Chưa có trên bảng kê" | Sổ đang tính, gợi ý bảng kê mới có thì tự hiện |
| `differs` | Tổng bảng kê lệch sổ quá 1đ | "Bảng kê hơn/kém <số>", ô Tổng viền cam, nền xám nhạt | Các khoản, Bảng kê ghi, "Sổ đang tính, số nợ theo số này", phần chênh |
| `no_add` | Tổng bảng kê khớp sổ nhưng các khoản không cộng ra (hoặc bảng kê không ghi Tổng) | "Bảng kê không cộng ra Tổng", viền cam | Các khoản, "Các khoản cộng lại", Tổng ghi trên bảng kê, phần chênh; không kết luận bên nào sai |
| `ok` | Các khoản cộng ra Tổng và khớp sổ | Phí, cước mình thu, Tổng | Phép cộng đủ dấu, cước khách tự trả ở ngoài |

Cam nền chỉ dành cho chưa có giá. Dòng `differs` mà các khoản cũng không cộng ra thì khi bung ghi "Các khoản cộng lại" rồi mới "Bảng kê ghi": dấu = chỉ đứng trước số đúng là kết quả phép cộng.

Lọc: Chưa có giá (`no_price`), Đối chiếu bảng kê (`differs`, `no_add`), Chưa có trên bảng kê (`no_detail`). Không có chip "Tất cả"; số 0 thì ẩn; tháng đủ số không hiện chip; lọc không đánh lại STT; lọc thuộc tháng đang xem; hết dòng khớp thì về đủ bảng. Khi lọc Đối chiếu có một dòng báo phần chênh, không gồm chuyến chưa giá. Tự tải lại giữ lọc và dòng đang mở; mỗi lúc mở một dòng.

Chế độ Đủ cột: 15 cột theo thứ tự file, cùng chip lọc; dòng khác `ok` ghi trạng thái bằng chữ thay năm cột tiền, không bung, số bảng kê ở chữ rê chuột.

`so-khach-bang` trong trình duyệt: `gon` (mặc định, cả giá trị cũ `chi-tiet`), `du`, `so`.

Chữ "Bảng kê" trên trang chỉ đặt ở một hằng trong `so-khach-v7-detail-ui.js`, vì có thể đổi thành "Debit".

## Đối chiếu dữ liệu

| Nhu cầu | Nguồn |
| --- | --- |
| Bill, tên tàu, ETD, ETA, phí phát sinh, phí DV hải quan, cước nội địa, OF, VAT, Tổng | Tab `CHI TIET ...`, tìm cột theo tiêu đề; không có trong tab sổ |
| Dòng chuyến, ngày, tháng, số đang tính | `legacy_rows`, `trips`, `months` của GET sổ |
| Cước tàu mình thu hay khách trả | So Tổng với phần còn lại: OF nằm trong Tổng là mình thu. Mẫu ủy thác luôn là khách trả |

Đo trên dữ liệu thật 5/11/2026 (467 container, chỉ đọc): 8 tháng đầu lệch 0đ với số phát sinh của sổ; 2 tháng sau lệch đúng 2 container vừa sửa trên Sheet; tháng mới nhất lệch vì bảng kê đã cũ.

Hai mẫu: bảng kê (một hoặc hai dòng mỗi container; dòng chưa có phí mà dòng dưới có phí là nửa trên, không cần ô gộp) và bảng ủy thác (một dòng, Tổng = cước xe + phí dịch vụ + VAT của hai khoản đó; số OF hiện gồm cả VAT của OF).

## Giao tiếp frontend–backend

`GET /api/v7/ledger` thêm `sheet_details`: `{rows: [...], months: {"yyyy-mm": {...}}}`, chỉ đọc. Hỏng file thì `{unavailable: true, rows: [], months: {}}`, không chặn đọc sổ. Sổ không đủ điều kiện: `rows` rỗng.

- Dòng: `kind`, `id`, `month`, `container` (rỗng: Phí lẻ), `has_detail`, `day`, `bill`, `ship`, `etd`, `eta`, `from`, `to`, `of_counted`, `differs`, `fee_vnd`, `service_vnd`, `truck_vnd`, `of_vnd`, `vat_vnd`, `total_vnd` (số của sổ, chưa có giá thì null), `sheet_total_vnd` (Tổng trên bảng kê, null nếu không có), `ledger_vnd`.
- Dòng, để đọc mà trang không phải cộng (ARCH-03), không vào nợ: `state` (bảng trên), `phi_vnd` (phí phát sinh + DV + nội địa + VAT), `parts_vnd` (`phi_vnd` + cước nếu mình thu), `adds_up` (`parts_vnd` khớp `sheet_total_vnd`, cho lệch 1đ do làm tròn VAT), `adds_diff_vnd` (`parts_vnd` trừ `sheet_total_vnd` khi không cộng ra, null nếu cộng ra hoặc không có Tổng), `sheet_diff_vnd` (`sheet_total_vnd` trừ sổ, null nếu không có Tổng).
- Tháng: cộng từng cột, `of_counted_vnd`, `of_customer_vnd`, `total_vnd` (cộng số của sổ các dòng), `no_detail`, `differs`, `sheet_diff_vnd` (bảng kê trừ sổ ở các dòng khác sổ, gồm cả dòng sổ chưa giá), `charges_vnd`, `diff_vnd` (`charges_vnd` trừ `total_vnd`), `compare_differs`, `compare_diff_vnd`, `compare_no_add` (số dòng `differs`, phần chênh của chúng, số dòng `no_add`).

Runner giá ghi `details.json` cạnh `prices.json` từ cùng một lần đọc (`WEBDEBIT_DETAIL_SNAPSHOT_PATH` nếu cần đổi). Không có lệnh ghi mới.

## Hành vi và bất biến

- Không có đường nào từ tab chi tiết vào tiền: `scan_tabs` không đọc được tab này thành khối tháng, không lệnh ghi nào dùng `details.json`.
- Cột Tổng theo sổ: mọi dòng hiện số của sổ; dòng cộng là Phát sinh của tháng, cùng số với đầu tháng, ghi "Cộng cả tháng, bằng Phát sinh". Cộng các dòng khác Phát sinh (điều chỉnh tháng) thì dòng cuối ghi "Phát sinh của sổ" và một dòng báo phần lệch.
- Khác sổ chỉ báo: chữ trên dòng, viền cam ở ô Tổng, rê chuột thấy số của bảng kê. Sổ chưa có giá mà bảng kê có giá: Tổng "–", tính là chưa giá, không vào phần chênh của Đối chiếu.
- Chưa có giá: máy lấy giá theo Sheet (`CHUYEN-HAN-01`), nên gợi ý chờ giá từ Sheet, không gợi ý nhập ở bảng sổ.
- Trống không phải 0: chuyến chưa có giá hiện "Chưa có giá", Tổng "–"; chuyến chưa có trên bảng kê ghi rõ.
- VAT lẻ trên bảng kê làm tròn đồng để hiện; lệch tới 1đ không báo.
- Container dùng lại: lần cuối trong sổ ứng với lần cuối trên bảng kê.
- Không ghi tên khách trong code: bật theo số container trùng.
- `?loc=` luôn hiện bảng sổ vì cần hàng để cuộn tới.

## Nguồn quyết định

- [`SO-CHI-TIET-01`](../docs/decisions/so-chi-tiet-01.md); `V7-COPY` (tiền theo sổ gốc); ARCH-03 (trang không tính tiền).

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_detail_queue.py`: hai mẫu, OF trong/ngoài Tổng, dòng tổng, ghép dòng, dùng lại container, ngày đảo, tab không sinh dòng tiền, đủ sáu `state`, cộng được lệch 1đ, phần chênh tháng không gồm chuyến chưa giá.
- [x] `preview/test-so-khach-v7-detail-browser.js`: cột, màu, chữ từng trạng thái, bung dòng, chip lọc, nhãn "N chưa giá", tháng đủ số, cộng lệch Phát sinh, Đủ cột, nhớ lựa chọn, tự tải lại giữ lọc và dòng mở, đầu bảng dính, `?loc=`, sổ không có bảng.
- [x] Khung 1280 và 1265 (thanh cuộn 15px), cả font Verdana: không cuộn ngang, số không tràn cột, vùng bấm ≥40px, dòng ≥44px; đã xem ảnh render dữ liệu giả.
- [ ] Sau deploy: `details.json` có trên `hao`, sổ thật hiện đúng cột, số nợ không đổi, đối soát không đổi.
- [ ] Người dùng tự đi hết luồng bảng gọn trên `hao` và xác nhận.

## CÒN MỞ

- Bản bảng kê hiện có đã cũ so với Sheet (báo lệch tới khi dán lại).
- Tháng có dòng tiền máy ghi thành điều chỉnh tháng: sổ không biết thuộc container nào, nên bảng chỉ so ở mức tháng.
- Dòng có Tổng chỉ tính một phần cước: chủ nghiệp vụ chưa xác nhận có cố ý không, nên nhãn giữ trung tính.
- Có đổi chữ "Bảng kê" thành "Debit" không.
