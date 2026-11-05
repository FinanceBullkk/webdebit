# Bảng chi tiết của sổ theo bảng kê gửi khách

Trạng thái: ĐÃ CHỐT (chủ nghiệp vụ, 4–5/11/2026, chat; phạm vi: chỉ xem, sổ có tab chi tiết). Quyết định: [`SO-CHI-TIET-01`](../docs/decisions/so-chi-tiet-01.md).

## Người dùng và luồng

Người theo dõi công nợ mở Sổ khách của một sổ mà Sheet ghi mỗi container hai dòng. Hiện tại sổ hiện hai dòng, dòng thứ hai là "Phí lẻ", nên không đọc được một container tính bao nhiêu và tiền nào là của mình.

1. Mở sổ, chọn tháng: bảng theo đúng cột bảng kê gửi khách, mỗi container một dòng.
2. Nhìn màu: xanh là mình thu, tính vào Tổng; cam là khách tự trả cước tàu, không tính. Chú thích và dòng cuối bảng ghi bằng chữ.
3. Cần sửa: bấm "Xem bảng sổ để sửa", làm như cũ. Lựa chọn được nhớ theo trình duyệt.

Người nhập chép tab bảng kê sang Sheet thành tab tên `CHI TIET ...`, chỉ giá trị, giữ nguyên ô. Có bảng kê mới thì dán lại.

## Đầu ra

Sổ có ít nhất một nửa container trong tab chi tiết thì mặc định hiện bảng chi tiết; sổ khác không đổi. Số nợ, phiếu thu, đối soát, máy tự ghi không đổi.

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
- Tháng: cộng từng cột, `of_counted_vnd`, `of_customer_vnd`, `total_vnd` (cộng số của sổ các dòng), `no_detail`, `differs`, `sheet_diff_vnd` (bảng kê trừ sổ ở các dòng khác sổ), `charges_vnd`, `diff_vnd` (`charges_vnd` trừ `total_vnd`).

Runner giá ghi `details.json` cạnh `prices.json` từ cùng một lần đọc (`WEBDEBIT_DETAIL_SNAPSHOT_PATH` nếu cần đổi). Không có lệnh ghi mới.

## Hành vi và bất biến

- Không có đường nào từ tab chi tiết vào tiền: `scan_tabs` không đọc được tab này thành khối tháng, không lệnh ghi nào dùng `details.json`.
- Cột Tổng theo sổ: mọi dòng hiện số của sổ; dòng cộng là Phát sinh của tháng, cùng số với đầu tháng. Các cột phí vẫn theo bảng kê, nên dòng khác sổ không cộng ngang được; dòng cộng cũng vậy khi có dòng chưa có trên bảng kê.
- Khác sổ chỉ báo: dòng tóm tắt nêu các container và phần chênh, viền cam ở ô Tổng kèm chữ giải thích ở chân bảng, rê chuột thấy số của bảng kê. Sổ chưa có giá mà bảng kê có giá: Tổng "–", tính là chưa giá, viền cam. Cộng các dòng khác Phát sinh (điều chỉnh tháng) thì dòng tóm tắt báo riêng.
- Trống không phải 0: chuyến chưa có giá hiện "chưa có giá", Tổng "–"; chuyến chưa có trên bảng kê ghi rõ.
- VAT lẻ trên bảng kê làm tròn đồng để hiện; lệch tới 1đ không báo.
- Container dùng lại: lần cuối trong sổ ứng với lần cuối trên bảng kê.
- Không ghi tên khách trong code: bật theo số container trùng.
- `?loc=` luôn hiện bảng sổ vì cần hàng để cuộn tới.

## Nguồn quyết định

- [`SO-CHI-TIET-01`](../docs/decisions/so-chi-tiet-01.md); `V7-COPY` (tiền theo sổ gốc); ARCH-03 (trang không tính tiền).

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_detail_queue.py`: hai mẫu, OF trong/ngoài Tổng, dòng tổng, ghép dòng, dùng lại container, ngày đảo, tab không sinh dòng tiền.
- [x] `preview/test-so-khach-v7-detail-browser.js`: cột, màu, thiếu dữ liệu, báo lệch, đổi bảng, nhớ lựa chọn, `?loc=`, sổ không có bảng.
- [x] Khung 1280: không cuộn ngang; đã xem ảnh render dữ liệu giả; số ở chân bảng không tràn cột.
- [ ] Sau deploy: `details.json` có trên `hao`, sổ thật hiện đúng cột, số nợ không đổi, đối soát không đổi.
- [ ] Người dùng tự xem các tháng trên `hao` và xác nhận.

## CÒN MỞ

- Bản bảng kê hiện có đã cũ so với Sheet (báo lệch tới khi dán lại).
- Tháng có dòng tiền máy ghi thành điều chỉnh tháng: sổ không biết thuộc container nào, nên bảng chỉ so ở mức tháng.
