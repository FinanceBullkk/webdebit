# Gợi ý giá booking cho chuyến biển chưa giá (GIA-BOOKING-01)

Trạng thái: nguyên tắc **ĐÃ CHỐT** (người dùng, 24/11/2026, chat: "Gợi ý, người bấm ghi", [`GIA-BOOKING-01`](../docs/decisions/gia-booking-01.md)). Cách làm dưới đây là **ĐỀ XUẤT** của Claude. Không đổi luật giá, lệnh ghi, DB hay quyền.

## Người dùng và luồng (bước 1)

**Ai, khi nào:** người nhập, cuối ngày, ở tab Việc cần làm → Dọn chi tiết → mở một sổ → nhóm "Chưa giá" ([GIA-TUYEN-01](v7-gia-theo-tuyen.md)). Người dùng trên 40 tuổi. Màn thật 1280×720, Chrome chỉ thấy khoảng 1280×560 (Windows 150%).

**Câu hỏi mang tới:** "chuyến này giá bao nhiêu?". Hôm nay người mở Sheet hay file booking để tra, rồi gõ giá. File booking CHAU_HAO có cột "Giá + phí (gốc)" ghi bằng chữ ("38TR+1"). Web đã đọc tab `CONT_NGUON` 15 phút một lần nhưng bỏ qua cột này.

**Bằng chứng** (số đo chỉ đọc trên `hao` 24/11/2026, đủ ở quyết định):
- Phần lớn chuyến biển tới 6/2026 có ghi ô này; từ 7/2026 ô thưa dần.
- Ô đọc được: 2.564/3.672 chuyến có phần đầu là đơn giá và phần sau là phụ phí, đúng như tab khách. 831 chuyến Sheet dồn cả vào đơn giá, 207 chuyến khác hẳn.
- Kết luận: gợi ý tốt, không đủ chắc để máy ghi.

**Luồng:**

1. Mở sổ ở Dọn chi tiết. Chuyến có giá booking đọc được có nút **"Giá booking 38 tr + 1 tr"** ngay trước ô giá. Đây cũng là chỗ của nút "Giá gần nhất" ở hàng tuyến.
2. Bấm nút: ô giá của chuyến thành "38", tiêu điểm vào ô. Không gửi lệnh nào. Ô này tính như người đã tự sửa: gõ ở hàng tuyến không đè.
3. Bấm "Ghi giá": dòng đổi thành dòng xem lại "Ghi giá 38 tr + phụ phí 1 tr · nợ 679 → 718 tr", với hai nút Xác nhận / Thôi (tiêu điểm vào Thôi), như hiện nay.
4. Xác nhận: máy chạy lệnh ghi giá đang có, đơn giá 38 tr, phụ phí 1 tr. Ghi xong, chuyến rời danh sách.
5. Tuyến có từ 2 chuyến sửa được mà mọi chuyến cùng một gợi ý: nút nằm ở **hàng tuyến**, dòng chuyến không lặp lại nút.
   - Bấm thì điền ô tuyến, rồi điền xuống các chuyến chưa tự sửa, như gõ ở ô tuyến.
   - "Ghi giá 2 chuyến" mở dòng xem lại "Ghi 2 chuyến 42 tr + phụ phí 0,5 tr · nợ … → …".
   - Xác nhận ghi từng chuyến bằng lệnh đang có.
6. Ô booking ghi chữ mà máy không đọc chắc ("38TR+1 (TẾT)", "HC +38TR", có USD): **không có nút**. Dòng hiện "Booking ghi: 38TR+1 (TẾT)" để người đọc rồi tự gõ.
7. Bấm nút rồi gõ số khác vào ô: giá là của người. Dòng xem lại không nhắc phụ phí booking, lệnh giữ phụ phí đang có của chuyến.

Số trên các câu ở đây là dữ liệu giả của test trình duyệt.

**Không có gợi ý:**
- Chuyến tháng khóa: không có ô giá, vẫn "Mở trong sổ".
- Chuyến ghép từ hai dòng booking trở lên, hay dòng booking ghép từ hai chuyến của sổ trở lên (kể cả chuyến chờ kiểm).
- Dòng booking chưa gắn đúng sổ: khách chưa ghép tên, khách khác, sổ khác của cùng khách.
- Ô có đơn giá đọc được mà ngoài 1 triệu – 1 tỷ đ (khoảng của [`GIA-DON-VI-01`](../docs/decisions/gia-don-vi-01.md)), hay phụ phí trên 1 tỷ đ: chỉ hiện chữ.

**Bị chặn:** khi tuyến đang xem lại hay đang ghi, nút booking của các chuyến trong tuyến khóa, như ô giá.

## Đầu ra

Chuyến biển chưa giá có giá booking: người điền giá bằng một lần bấm thay vì tra Sheet, rồi ghi qua đúng bước xem lại và Xác nhận đang có. Trước khi ghi, người thấy rõ đơn giá, phụ phí và nợ trước → sau. Máy không ghi gì khi người chưa Xác nhận.

## Cấu trúc và thị giác (skill `thiet-ke-ux`, bước 2–4)

Đây là thay đổi nhỏ trên một màn có sẵn, nên không đưa hai phương án. Quyết định chính là đặt nút ở đâu.

- **Nút đứng ngay trước ô giá**, cùng kiểu viên thuốc với "Giá gần nhất": viền `#b9c3cf`, chữ `#1c5cab`, 14px đậm 600, cao 38px.
  - Lý do: nút điền ô thì đặt cạnh ô. Lại cùng chỗ với nút gợi ý đã có, người không phải học chỗ mới.
  - Không chọn cột mô tả giữa dòng: mắt phải nhảy từ giữa sang ô bên phải, và cột này cắt chữ bằng "…" nên nút có thể bị che.
- **Chữ máy không đọc chắc thì hiện, không ẩn.** Hiện bằng chữ thường ở cột mô tả, không phải nút: chỉ để đọc, không có thao tác.
  - Lý do hiện: giá là thứ người đang cần; ẩn đi thì người phải mở Sheet.
  - Lý do không làm nút: máy không đoán số từ chữ như "(TẾT)" hay "USD".
  - Chữ dài cắt bằng "…", đủ chữ ở chú thích khi rê chuột.
- **Bỏ chữ "sổ chưa có giá gợi ý"** khi chuyến có giá booking, để không có hai câu ngược nhau trên một dòng.
- **Chuyến đã có phụ phí:** nút ghi "Giá booking 38 tr" (không "+ 1 tr"), vì bấm chỉ điền đơn giá và giữ phụ phí của sổ. Nhãn nút nói đúng việc bấm sẽ làm.
- **Hàng tuyến có nút booking luôn hai dòng:** nút gợi ý ở dòng trên, ô giá và "Ghi giá" ở dòng dưới. Cột thao tác chỉ rộng bằng dòng nút, nên tên tuyến giữ ít nhất 240px. Hai nút Xác nhận / Thôi của dòng xem lại vẫn chung một dòng.
- **Dòng chuyến có nút:** cột thao tác co theo nội dung. Ô giá vẫn thẳng mép phải với các dòng khác. Màn hẹp thì nút lên dòng trên.
- Nút "Giá gần nhất" đổi chữ từ 13,5px lên 14px cho cùng cỡ với nút mới (chữ trong bảng ≥ 14px).

**Trạng thái:**
- Đang tải hay lỗi đọc sổ: như cũ, chưa có chi tiết thì chưa có nút.
- Đang hiện bản cũ của tab: mọi nút ghi khóa, nút booking cũng khóa.
- Bản chụp Sheet hỏng: không có gợi ý, gõ tay như cũ.
- Màn 390px: bảng cuộn ngang trong khung như cũ, dòng chật thì xuống dòng, không cắt nút.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- **Nguồn.** `CONT_NGUON`, cột "Giá + phí (gốc)". Runner đọc vùng A1:Z bằng `read_source`. Cột tìm theo tên tiêu đề, như bốn cột đội xe (`OPTIONAL_SOURCE_COLUMNS`). Thiếu cột thì ô trống, còn `columns` ghi `booking_price` khi có cột. Dấu `sha256` của bản chụp không đổi, vì đã băm cả vùng.
- **Hàng chờ.** `build_queue` giữ chữ giá của dòng READY trong map riêng `booking_prices`, theo `source_row`. Map này không vào dòng hàng chờ: `removed_identity` băm cả dòng, nên thêm một trường là đổi dấu vân của mọi chuyến người đã "Giữ".
- **Đọc chữ.** `booking_price_vnd` (web, `Decimal`) đọc như `price_vnd` của `tools/v7_trip_source_match.py`. Web không import `tools/` (ARCH-02). Mỗi phần có thể có đuôi `TR`, `TRIEU`, `TRIỆU` hay `M`, tối đa sáu số lẻ triệu, tức tới từng đồng.
- **Ghép.** `project_booking_prices` xét chuyến web `confirmed`, chưa xóa, chưa có đơn giá, có container và ngày. Dòng hàng chờ phải READY, cùng `customer_id` của sổ, cùng container, ngày lệch không quá 3 ngày. Phải đúng một dòng cho chuyến, và dòng đó đúng một chuyến của sổ. Chuyến dùng để đếm là chuyến chưa xóa, chưa loại, kể cả chờ kiểm. Dòng sổ gốc không xét. Hàng chờ dùng bản trước khi sổ đầu tiên của cùng khách nhận các dòng chưa gắn sổ, nên chỉ dòng gắn đúng sổ này mới tính.
- **Giao diện.**
  - `InboxTable.bookingHint` cho gợi ý một chuyến, `groupBooking` cho gợi ý cả tuyến.
  - `millionInput` và `parseMillions` như ô triệu hiện có.
  - Tiền chuyến tính bằng `SoKhachV7Model.tripAmount`.
  - Lệnh `POST /api/v7/trips/price` có sẵn.

## Giao tiếp frontend–backend (bước 5)

Không thêm lệnh ghi. `GET /api/v7/ledger?customer=<id>` thêm `booking_prices` trong `sheet_sync`, chỉ cho chuyến chưa có đơn giá:

```json
"booking_prices": {"<trip_id>": {"text": "38TR+1", "unit_price_vnd": "38000000", "other_fee_vnd": "1000000"}}
```

- Số tiền là chuỗi, như mọi API. `unit_price_vnd` là null khi máy không đọc chắc chữ; lúc đó `other_fee_vnd` cũng null.
- `other_fee_vnd` là null khi ô không có phần sau "+": trống, không phải 0.
- Bản chụp Sheet hỏng: `sheet_sync` là bản trống, có `booking_prices: {}`.
- `GET /api/v7/sheet-queue` không mang map này (chữ giá của mọi dòng).

Ghi vẫn bằng `POST /api/v7/trips/price` `{customer_id, expected_version, idempotency_key, trip_id, unit_price_vnd, other_fee_vnd}`, như GIA-TUYEN-01. `other_fee_vnd` là phụ phí booking khi đủ ba điều kiện: người đã bấm nút, ô còn đúng đơn giá đã điền, chuyến chưa có phụ phí. Còn lại giữ phụ phí đang có của chuyến. Lỗi, mất mạng, thử lại cùng khóa: như luồng ghi giá hiện có.

## Nguồn quyết định

- [`GIA-BOOKING-01`](../docs/decisions/gia-booking-01.md): quyết định này.
- [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md): (1) luật ghép ±3 ngày; (3) giá theo sổ gốc.
- [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md), [`MAY-GIA-01`](../docs/decisions/may-gia-01.md), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md): giá Sheet vẫn là chuẩn khi chạy song song.
- [`GIA-DON-VI-01`](../docs/decisions/gia-don-vi-01.md): khoảng 1 triệu – 1 tỷ đ.
- `V7-BE`: phụ phí trống của chuyến có đơn giá tính 0, giá trị lưu vẫn NULL.

## Hành vi và bất biến

- VND nguyên: đọc bằng `Decimal`, không số thực. Phụ phí không có là null, không phải 0.
- Không có lệnh ghi nào trước Xác nhận. Máy không tự ghi giá booking.
- Không đè phụ phí đang có của chuyến.
- Lịch sử, phân bổ lại phiếu theo nợ cũ trước, khóa tháng, Hoàn tác: như lệnh ghi giá hiện có.
- Chữ từ Sheet luôn thoát HTML khi hiện.

## Tiêu chí nghiệm thu

- [x] `npm run check` xanh.
- [x] Unit Python, `tests/test_sheet_queue.py`:
  - đọc chữ: các dạng đo được, chữ lạ là None, sáu số lẻ;
  - map chữ giá ngoài dòng hàng chờ;
  - ghép đúng một – một, ±3 ngày, chỉ dòng READY của sổ;
  - chuyến đã có giá, chờ kiểm, đã xóa, đã loại;
  - chữ không đọc chắc hay ngoài khoảng chỉ còn `text`;
  - `sheet_projection` trả `booking_prices` của sổ, `sheet-queue` không trả.
- [x] Unit Python, `tests/test_webdebit_export_connector.py`: đọc cột theo tên, thiếu cột thì trống, `columns` có `booking_price`.
- [x] Trình duyệt, `test-viec-can-lam-gia-tuyen-browser.js` (dữ liệu giả, 1265×560 = 1280 trừ thanh cuộn):
  - nút ở đúng chuyến; hàng tuyến có nút khi cả tuyến cùng gợi ý; chuyến không gợi ý hay tháng khóa không có nút;
  - chữ lạ hiện nguyên chữ, không chèn được HTML;
  - bấm chỉ điền ô, không có POST nào trước Xác nhận;
  - xem lại nêu đơn giá + phụ phí, POST đúng phụ phí; chuyến đã có phụ phí giữ phụ phí;
  - sửa ô thì không kèm phụ phí booking;
  - nút hàng tuyến điền cả tuyến và ghi từng chuyến kèm phụ phí;
  - đang xem lại thì nút booking trong tuyến khóa;
  - Xác nhận / Thôi chung một dòng; không cuộn ngang; ô giá thẳng mép; chữ nút 14px.
- [x] Xem ảnh render (dữ liệu giả) ở 1265×560 và 390, gồm cả trạng thái sau khi bấm và dòng xem lại.
- [ ] Bước 8: người nhập bấm thử trên `hao` một chuyến có giá booking, kiểm Lịch sử và tổng nợ.

## Việc sau (chưa làm)

- **Tách nhóm tuyến theo hãng tàu cho sổ biển.** Giá biển đổi theo hãng tàu, nhưng chưa làm. Ô `carrier` của chuyến bộ là số xe (NGUON-CHUYEN-01), chuyến bộ có thể nằm trong sổ không phải sổ "Bộ", và GET sổ chưa có trường cho biết chuyến biển hay bộ. Thêm hãng tàu vào khóa nhóm lúc này sẽ tách mỗi chuyến bộ thành một nhóm. Cần một cờ biển/bộ theo chuyến trước.
- Nút booking ở ô Đơn giá của Sổ khách.
- Chuyến trước năm 2026 (ngoài `QUEUE_FIRST_YEAR`) không có gợi ý.

## Phạm vi agent

- Agent: claude
- Review: opus (đụng đường ghi giá)
- Được sửa:
  - `cong-no-web-handoff/tools/webdebit_export_connector.py`
  - `cong-no-web-handoff/web/v7_sheet_queue.py`
  - `cong-no-web-handoff/web/v7_api_sheet.py`
  - `cong-no-web-handoff/preview/viec-can-lam.js`
  - `cong-no-web-handoff/preview/viec-can-lam-table.js`
  - `cong-no-web-handoff/preview/viec-can-lam.css`
  - `cong-no-web-handoff/preview/test-viec-can-lam-gia-tuyen-browser.js`
  - `cong-no-web-handoff/tests/test_sheet_queue.py`
  - `cong-no-web-handoff/tests/test_webdebit_export_connector.py`
  - `docs/decisions/gia-booking-01.md`, `docs/decisions.md`, `docs/decisions/nguon-chuyen-01.md`, `specs/v7-gia-booking.md`
- Cấm: thêm dependency; đổi lệnh ghi, schema, quyền; chạm `hao`, Sheet, DB thật.

## Hoàn tác

Revert PR. Không có migration, không có lệnh ghi mới, không đụng dữ liệu. Bản chụp Sheet có thêm trường `booking_price` ở mỗi dòng; bản cũ của web bỏ qua trường này.

## Bằng chứng

Fixture: unit Python và test trình duyệt trên dữ liệu giả; ảnh render để ngoài repo. Chưa có bằng chứng tích hợp hay live: chưa chạy trên `hao`.

## Câu hỏi mở

- Có cần nút booking ở Sổ khách không? Hỏi sau khi người nhập dùng ở Việc cần làm.
