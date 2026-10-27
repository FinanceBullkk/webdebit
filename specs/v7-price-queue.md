# V7: điền giá từ Sheet ("Ghi N giá")

Trạng thái: **ĐÃ CHỐT** luồng và mockup (người dùng duyệt trong chat 27/10/2026: "Mockup được, chọn nguồn giá B"). Backend **ĐÃ CODE** phần đọc và ghi lô (xem Tiến độ), **chưa triển khai** `hao`, chưa có giao diện thật. Không đổi luật tiền.

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720), cùng người dán chuyến và nhập phiếu thu hằng ngày. Theo `V7-ID`, mỗi lần ghi mang tên người bấm.

**Bối cảnh:** trong thời gian chạy song song, Sheet là sổ chính thức. Chuyến đồng bộ từ Sheet lên web đến **không có đơn giá**: bản chụp đồng bộ chỉ có container, ngày, hãng tàu, nơi đi/đến, booking. Giá được điền trên tab khách của Sheet, thường muộn hơn vài ngày. Hiện người nhập phải gõ lại giá từng chuyến trên web; quên thì đối soát cuối ngày báo lệch.

**Luồng:**
1. Trang Tổng quan, mục "Việc cần làm", có dòng "**N giá từ Sheet chờ ghi** · ở K khách". Bấm vào thì mở khách đầu tiên.
2. Sổ khách: đầu sổ có nút "**Ghi N giá từ Sheet**", đặt cạnh nút "Duyệt … chuyến mới" đang có. Trong bảng, các chuyến chờ ghi tô vàng; ô Đơn giá và Phụ phí hiện **giá Sheet** bằng chữ nghiêng, kèm nhãn "giá Sheet".
3. Người nhập nhìn qua, bấm "Ghi N giá từ Sheet". Một khung xác nhận ngay dưới đầu sổ (không phải hộp thoại) ghi: số chuyến, tổng tiền tăng thêm, tháng bị ảnh hưởng. Hai nút: "Ghi" và "Thôi".
4. Ghi xong, sổ tải lại: giá thành số thường, tổng còn nợ cập nhật, phiếu thu tự phân bổ lại theo nợ cũ trước, Lịch sử có một dòng sửa giá cho mỗi chuyến kèm "Nguồn: Sheet tab …, dòng …".
5. Trường hợp không tự ghi (xem bảng dưới) hiện dưới đầu sổ thành dòng "**Cần xem: X**". Bấm vào thì mở danh sách, mỗi dòng có hành động riêng.

**Kết quả:** chuyến có giá trên Sheet thì có giá trên web sau một lần bấm mỗi khách. Không có dòng nào được ghi khi việc ghép không chắc chắn.

**Bị chặn hoặc không ghi:**
| Trường hợp (mã công cụ đo) | Hiện cho người dùng | Hành động |
| --- | --- | --- |
| Ghép đúng 1 chuyến, web chưa có giá, tháng mở (`READY`) | Tô vàng, có trong nút "Ghi N giá" | Ghi cả lô |
| Như trên nhưng tháng khóa (`MONTH_LOCKED`) | Trong "Cần xem": "Tháng 9 đang khóa" | Nút "Mở khóa tháng 9" (dùng ổ khóa có sẵn), rồi dòng vào lô |
| Web đã có giá khác Sheet (`CONFLICT`) | "Web 1.400.000 đ · Sheet 1.500.000 đ" | "Giữ web" (ghi nhận, không hỏi lại) hoặc "Lấy Sheet" (ghi giá Sheet, một chuyến) |
| Khớp nhiều chuyến hoặc nhiều dòng Sheet cùng một chuyến (`AMBIGUOUS`) | "Dòng Sheet 214 khớp 2 chuyến" | Không ghi tự động. Người nhập điền giá tay tại ô như hiện nay |
| Chuyến đang CHỜ KIỂM (`PENDING_REVIEW`) | Không hiện trong lô | Kết luận CHỜ KIỂM trước |
| Sheet chưa có giá (`SHEET_NO_PRICE`) | Không hiện gì | Giữ trống, không phải 0 |
| Giá đã giống (`PRICE_UNCHANGED`) | Không hiện gì | — |
| Không tìm thấy hoặc tab không có khách web (`NOT_FOUND`, `NO_CUSTOMER`) | Chỉ ở báo cáo, không trên sổ khách | Admin bổ sung tên phụ cho khách |

## Đầu ra

Sổ khách có nút "Ghi N giá từ Sheet" khi Sheet có giá cho chuyến web chưa có giá. Bấm một lần ghi cả lô qua đúng hàm ghi giá hiện có. Trường hợp không chắc chắn được liệt kê riêng và không bao giờ tự ghi. Tổng quan đếm việc này.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Số đo thật (27/10/2026, bản tải Sheet 27/10, sổ web trên `hao`, công cụ `v7_price_match.py`, chỉ đọc; chi tiết ngoài Git):**
- 10.358 dòng chuyến ở tab khách. Ghép đúng ngày 9.377 dòng, không dòng nào cần lệch ±3 ngày. Dòng không ngày ghép theo container 586.
- `READY` 36 (22 chuyến web, 14 dòng sổ gốc; đều tháng 10, tháng mở). `PRICE_UNCHANGED` 9.163. `CONFLICT` 3. `AMBIGUOUS` 262 (232 là dòng lịch sử không ngày). `NOT_FOUND` 8. `NO_CUSTOMER` 149 (7 tab). `SHEET_NO_PRICE` 499. `NO_CONTAINER` 238.
- Nghĩa là khối lượng thường ngày nhỏ (vài chục dòng), tập trung ở tháng hiện tại; ngoại lệ thực sự cần người xem chỉ vài dòng mỗi lần.

**Có sẵn, dùng lại:**
- Ghép và phân loại: `cong-no-web-handoff/tools/v7_price_match.py` (`match`, `targets`, `unchanged`). Đã có test dữ liệu giả.
- Đọc tab khách: `v7_load_real_copy.scan_workbook` (đơn giá `details.unit_price`, phụ phí cộng các cột `details.fee`, ô TOTAL `amount`).
- Ghi giá chuyến web: `POST /api/v7/trips/price` → `edit_trip_price(trip_id, unit_price_vnd, other_fee_vnd)`. Server tự tính thành tiền, phân bổ lại, ghi Lịch sử `price_edit` với người làm; có chặn tháng khóa (24/10) và chống ghi trùng bằng `idempotency_key` + `expected_version`.
- Ghi giá dòng sổ gốc: `POST /api/v7/legacy/edit` → `edit_legacy_trip(legacy_row_id, field, value)` với `field` là `unit_price_vnd` hoặc `other_fee_vnd`, mỗi lệnh một trường.
- Mẫu giao diện: nút "Duyệt N chuyến mới" (`sheet-approve`) và khung đối chiếu "Giữ web / Lấy Sheet" (`sheet-detail`) trong `so-khach-v7-ui.js`. Mục "Việc cần làm" của Tổng quan (`DASH-01`).

**Còn thiếu:**
- **Nguồn giá trên server (CÒN MỞ, cần người dùng chọn):**
  - **A.** Thêm cột "Đơn giá" và "Phụ phí" vào tab `WEBDEBIT_EXPORT` của Sheet. Bản chụp đồng bộ có sẵn giá, ít code nhất. Nhưng chỉ phủ chuyến có trong tab export, không phủ dòng sổ gốc (14/36 dòng `READY` lần đo này).
  - **B.** Runner đồng bộ đọc thêm các tab khách (như công cụ đo). Phủ cả dòng sổ gốc, khớp đúng cách đã đo. Nhưng nặng hơn: 247 tab, cần quyền đọc cả workbook.
  - **ĐÃ CHỐT B** (người dùng, 27/10/2026).
- API mới: `GET` kèm danh sách giá chờ trong `get_ledger` (như `sheet_sync`), và `POST /api/v7/sheet/prices` ghi cả lô cho một khách.
- Nguồn trong Lịch sử: `price_edit` hiện không có trường tab/dòng Sheet. Cần thêm vào ghi chú sự kiện hoặc mở rộng snapshot (bước 5).

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT)

- `get_ledger` trả thêm `sheet_prices: {snapshot_sha256, ready: [...], review: [...]}`. Mỗi dòng có `source_tab`, `source_row`, `target_kind`, `target_id`, giá Sheet, giá web, `status`. Server tính bằng hàm ghép của công cụ đo, không tin dữ liệu client.
- `POST /api/v7/sheet/prices {customer_id, expected_version, snapshot_sha256, idempotency_key}`: server tính lại `READY` từ bản chụp đúng hash. Lệch hash thì `STALE_SHEET` ("Sheet đã đổi. Tải lại rồi ghi."). Ghi từng chuyến bằng `edit_trip_price` / `edit_legacy_trip`, khóa con suy từ khóa lô + hash + đích (bấm lại không ghi trùng). Trả `{written, skipped, version}`.
- `POST /api/v7/sheet/price-conflict {…, decision: keep_web | use_sheet}` cho `CONFLICT`, cùng mẫu `resolve_sheet_conflict` (`keep_web` ghi nhận, `use_sheet` qua hàm ghi giá nên vẫn bị chặn tháng khóa).
- Lỗi giữ câu có sẵn: `MONTH_LOCKED`, `STALE_LEDGER`, `STALE_SHEET`, `NO_BASELINE`.

## Nguồn quyết định

- Sheet là sổ chính thức khi chạy song song: [`SONG-SONG-01`](../docs/decisions.md#song-song-01).
- Tháng khóa: cột giá chỉ đọc, mở khóa trước: [Cập nhật khóa tháng 24/10/2026](../docs/decisions.md#cập-nhật-khóa-tháng-24102026).
- Phụ phí trống = 0 khi có đơn giá: [`V7-BE`](../docs/decisions.md#v7-be). NULL khác 0.
- Người làm từ phiên server: [`V7-ID`](../docs/decisions.md#v7-id).
- Booking đã ghi giữ nguyên: [`BOOKING-EDIT-01`](../docs/decisions.md#booking-edit-01) (công cụ không đổi booking, container hay ngày).
- Nguồn giá: B, runner đọc tab khách (người dùng chốt 27/10/2026). CÒN MỞ: ai thấy nút (mặc định ai mở được sổ là ghi được, như mọi thao tác V7).

## Hành vi và bất biến

- Chỉ ghi đơn giá và phụ phí; không đổi container, ngày, booking, khách.
- Không ghi khi ghép không duy nhất, khi Sheet trống giá, khi chuyến CHỜ KIỂM.
- Giá trống trên Sheet giữ NULL trên web, không thành 0.
- Tháng khóa: backend chặn như hiện nay, giao diện chỉ nhắc mở khóa.
- Mỗi chuyến một sự kiện Lịch sử có người làm, giá trước → sau, nguồn Sheet.
- Phân bổ lại theo nợ cũ trước sau khi ghi (hàm ghi giá đã làm).

## Tiêu chí nghiệm thu

- [ ] Test ghép giá (`test_v7_price_match.py`) và test API lô giá với dữ liệu giả: chỉ `READY` được ghi; bấm lặp cùng khóa không ghi thêm; hash Sheet đổi thì từ chối.
- [ ] Harness PostgreSQL: ghi lô giá qua hàm có sẵn, tổng nợ và phân bổ đúng, tháng khóa bị `MONTH_LOCKED`, Lịch sử đủ dòng.
- [ ] Playwright 1280×720: nút có đúng số, khung xác nhận, ghi xong không còn dòng vàng; "Cần xem" có đủ ba loại; bàn phím; lỗi mạng giữ nguyên trạng thái.
- [ ] Người dùng đi hết luồng trên bản thử và xác nhận.
- [ ] Giao diện khớp mockup đã duyệt.

## Mockup

`cong-no-web-handoff/preview/mockups/ghi-gia-tu-sheet/index.html` (HTML, dữ liệu giả, 1280×720). Chọn trạng thái ở thanh trên mockup:
1. Có giá chờ ghi
2. Khung xác nhận
3. Đã ghi
4. Cần xem (lệch giá, tháng khóa, khớp nhiều chuyến)
5. Không có giá chờ
6. Lỗi khi ghi

Mockup **ĐÃ DUYỆT** (người dùng, 27/10/2026, chat; bản tại commit `b5de96d`). Theo `docs/development.md`, Penpot là nơi duyệt chuẩn; các mockup gần đây (sổ khách gọn, cấn trừ hai sổ) đã được duyệt bằng HTML.

## Câu hỏi mở

- Có cần nút "Ghi giá cho mọi khách" ở Tổng quan không, hay ghi từng khách là đủ (36 dòng lần đo này rải trên nhiều khách)?

## Tiến độ backend (27/10/2026)

**ĐÃ CODE và kiểm bằng dữ liệu giả** (`npm run check`):
- `web/v7_price_queue.py`: lõi ghép (chuyển từ công cụ đo sang tầng web theo ARCH-02; `tools/v7_price_match.py` gọi lại lõi này). Thêm hai trạng thái:
  - `MANUAL`: giá hoặc phụ phí âm trên Sheet. Lệnh ghi giá chỉ nhận số không âm, nên dòng này phải nhập tay.
  - `AMBIGUOUS_PRICED`: khớp nhiều chuyến nhưng mọi chuyến đã có giá, nên không có gì để ghi và không hiện trong "Cần xem".
- `tools/v7_price_snapshot.py`: biến một bản tải `.xlsx` thành bản chụp giá (`WEBDEBIT_PRICE_SNAPSHOT_PATH`, mặc định `/var/lib/webdebit-sheet-sync/prices.json`). Hash tính trên các dòng, nên tải lại Sheet không đổi thì hash không đổi. Ghi nguyên tử, mode 600.
- `GET /api/v7/ledger` trả thêm `sheet_prices {snapshot_sha256, ready, review, ready_count, review_count}`. Thiếu bản chụp thì trả `unavailable: true`, sổ vẫn đọc được.
- `POST /api/v7/sheet/prices {customer_id, expected_version, snapshot_sha256, idempotency_key}`:
  - Server tính lại `READY` từ bản chụp đúng hash; lệch hash thì `STALE_SHEET`.
  - Chuyến web ghi bằng `edit_trip_price`; dòng sổ gốc ghi bằng `edit_legacy_trip`, mỗi trường một lệnh.
  - Mỗi lệnh có khóa cố định theo lô, hash, đích và trường, nên bấm lại không ghi trùng.
  - Hỏng giữa lô thì trả `complete: false` với số đã ghi; lần sau các dòng đã ghi thành `PRICE_UNCHANGED`.

**Kiểm chỉ đọc trên dữ liệu thật** (bản tải 27/10, sổ `hao` qua API GET, kết quả ngoài Git): bản chụp 10.358 dòng; hàng chờ từng khách cho tổng `READY` 36 ở 3 khách (khớp số đo); "Cần xem" 43 dòng ở 10 khách (40 khớp nhiều chuyến có chuyến chưa giá, 3 lệch giá).

**CÒN MỞ:**
- **Runner tự lấy file Sheet:** bản tải đầy đủ nặng khoảng 32MB, vượt giới hạn 10MB của API xuất file Google Drive. Cần chọn: đọc từng tab qua Sheets API rồi viết thêm bộ chuyển sang dạng loader đọc được (đường chính thức, nhiều code hơn); hoặc dùng địa chỉ tải `.xlsx` của Google Docs bằng token quyền `drive.readonly` (ít code, nhưng không phải API được cam kết). Trong lúc chờ, bản chụp tạo được từ file `.xlsx` tải tay (cùng file dùng cho đối soát cuối ngày).
- `CONFLICT` "Giữ web" cần lưu sự kiện (mở rộng `resolve_sheet_conflict` hoặc sự kiện riêng); "Lấy Sheet" dùng được ngay bằng lệnh ghi giá một chuyến.
- Ghi nguồn tab/dòng Sheet vào Lịch sử `price_edit`.
- Đếm "N giá từ Sheet chờ ghi" ở Tổng quan (cần tính trên mọi khách).
- Giao diện thật theo mockup đã duyệt; harness PostgreSQL cho lô giá; triển khai `hao` (đặt bản chụp, biến môi trường) cần người dùng cho phép.
