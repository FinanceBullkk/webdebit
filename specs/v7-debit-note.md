# Debit note theo tháng công nợ

Trạng thái: ĐÃ CHỐT. Chọn theo tháng công nợ, xuất PDF và Excel: người dùng, 29/10/2026, [`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md). Bố cục và quy tắc theo mẫu Debit Note v3 sếp duyệt 30/10/2026: [`DEBIT-NOTE-02`](../docs/decisions/debit-note-02.md). Các điểm Claude chọn và điểm CÒN MỞ ghi trong hai file quyết định. Mẫu v4 một trang A4 ngang (10/11/2026, [`DEBIT-NOTE-03`](../docs/decisions/debit-note-03.md)): mục [Mẫu v4](#mẫu-v4-debit-note-03).

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Người nhập (trên 40 tuổi, màn 1280×720) cuối tháng gửi khách debit note của một tháng: PDF là chứng từ chính thức, Excel để khách đối chiếu từng dòng.

1. Mở sổ khách, kéo tới tháng cần gửi, bấm **Debit note** ở dòng tiêu đề tháng.
2. Hộp mở ra. Bên trái là form thông tin chứng từ: số debit note (gợi ý `HTH-yymm-001`), ngày phát hành (mặc định hôm nay, giờ VN), số ngày thanh toán (mặc định 15), dịch vụ, số hóa đơn GTGT, bên phát hành (chọn HTH Logistics, Nông Sản Xanh hoặc công ty khác), khách (tên hiển thị, tên pháp lý, địa chỉ, Attn), thông tin thanh toán, quy đổi USD (tỷ giá, nguồn, ngày lấy). Bên phải là danh sách **Chặn / Cảnh báo / Lưu ý** và bản xem trước đúng như bản in.
3. Lần đầu người lập điền phần còn thiếu; trình duyệt nhớ thông tin công ty (theo bên phát hành) và khách (theo sổ), lần sau điền sẵn.
4. Còn điểm **Chặn** thì hai nút là **In bản nháp** và **Excel bản nháp**: file có chữ DRAFT, tên file thêm `_DRAFT`. Hết chặn nhưng còn **Cảnh báo** thì người lập tích "Tôi đã xem các cảnh báo, phát hành bản chính thức" mới ra bản chính thức. Không còn gì thì ra bản chính thức ngay.
5. **In / Lưu PDF** mở hộp in trình duyệt (chọn "Lưu dưới dạng PDF"; tên file gợi ý theo tiêu đề). **Tải Excel** tải file đối chiếu.
6. **Đóng** (hoặc Esc) về lại sổ, con trỏ trở về nút vừa bấm.

Tháng không có chuyến thì không hiện nút. Chứng từ chỉ đọc dữ liệu sổ đang hiện, không ghi DB.

## Đầu ra

- **PDF** (một file): trang 1 tóm tắt khổ A4 dọc, luôn vừa một trang (nhiều cảng đến thì tự thu nhỏ); các trang chi tiết container khổ A4 ngang, tiêu đề bảng lặp mỗi trang, dòng TOTAL không đứng một mình ở đầu trang. Lề trái/phải 0.45 in, trên 0.4, dưới 0.6; chân trang "<bên phát hành> · Debit Note | Page x of y". Bố cục từng khối theo mục Cấu trúc trang của đặc tả v3 (xem `DEBIT-NOTE-02`).
- **Excel đối chiếu** (một sheet `Statement`): phía trên số chứng từ, ngày, kỳ, bên phát hành, bên mua, tỷ giá; hàng tiêu đề cố định ở hàng 9 (đóng băng, lọc, lặp khi in); cột NO., CONTAINER NO., SHIPPER, DATE, FROM, TO, đủ 8 cột phí theo danh mục, TOTAL (VND); số thật, ngày thật định dạng `dd mmm yyyy` tiếng Anh, không gộp ô; dòng phí không gắn container sau các dòng container; USD chỉ ở dòng tổng.
- **Tên file**: `<số chứng từ>_<khách>_<yyyy-mm>.pdf/.xlsx`; "/" trong số chứng từ thành "-"; chữ không phải ASCII bỏ đi ("KHACH 三川" → "KHACH").

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

Dòng chứng từ lấy từ `GET /api/v7/ledger` trang sổ đã tải; tên khách, mặt hàng, phương thức lấy từ `GET /api/v7/customers` (đã có). Không cần API mới.

| Trường chứng từ | Chuyến web (`trips[]`) | Dòng sổ gốc (`legacy_rows[]`, `kind='trip'`) |
| --- | --- | --- |
| CONTAINER NO. | `container`, viết hoa, bỏ khoảng trắng | `current.container`, không có `current` thì `display.container` |
| B/L NO. | chưa có trên sổ: cột ẩn | như chuyến web |
| LINE, SHIPPER | `carrier`, `shipper` | `current.*` / `display.carrier`, `display.shipper` |
| LOADING DATE | `event_date` | `current.event_date` / `display.date` |
| LOADING PLACE, POD | `origin`, `destination`, chuẩn theo danh mục nơi/cảng, kèm tên tiếng Trung ([`DIA-DIEM-01`](../docs/decisions/dia-diem-01.md)) | `current.*` / `display.from`, `display.to` |
| UNIT PRICE 单价 | `unit_price_vnd`; `is_missing_price` → thiếu | `current.unit_price_vnd` / số trong `display.unit_price` |
| 7 loại phí còn lại và loại ngoài danh mục | `fee_lines` gom theo mã loại phí (bảng ánh xạ ở `DEBIT-NOTE-02`) | như chuyến web |
| AMOUNT | UNIT PRICE + phí của dòng; khác `amount_vnd` của sổ thì chặn | khác `current.counted_vnd` / `source_total_vnd` thì chặn |
| Dòng ADDITIONAL CHARGES | chuyến `is_fee_only`: mỗi khoản phí một dòng (loại, ngày, ghi chú, số tiền) | dòng không có số container, như chuyến web |

Lấy chuyến web `status='confirmed'`, chưa xóa; dòng sổ gốc chưa xóa. Tháng = tháng công nợ (`month`). Thứ tự theo ngày đóng hàng, cùng ngày giữ thứ tự sổ (sổ gốc trước, web sau). Thông tin cấp chứng từ (số, ngày, bên phát hành, khách, thanh toán, tỷ giá) không có trên sổ: người lập điền ở form.

Đặc tả v3 ghi dev đọc dữ liệu từ Sheet "Bộ lập bill". Ở web, nguồn là sổ khách V7 (đã đồng bộ từ Sheet qua luồng duyệt chuyến), như `DEBIT-NOTE-01`.

## Giao tiếp frontend–backend (bước 5, khi có)

Không có lệnh mới. Chứng từ dựng từ bản sổ trang đã tải (`ctx.snapshot`), danh mục phụ phí (`ctx.feeTypes`) và dòng khách (`SoKhachV7Api.customerRow`). Thông tin người lập điền chỉ lưu ở trình duyệt (`localStorage`), không gửi máy chủ.

## Nguồn quyết định

- [`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md): theo tháng công nợ, PDF + Excel, chỉ chuyến của tháng.
- [`DEBIT-NOTE-02`](../docs/decisions/debit-note-02.md): mẫu Debit Note v3 sếp duyệt (bố cục, danh mục phí, quy tắc tính, kiểm tra trước phát hành).
- [`PHU-PHI-01`](../docs/decisions/phu-phi-01.md) (2): chứng từ gửi khách hiện từng khoản phụ phí.
- [`DIA-DIEM-01`](../docs/decisions/dia-diem-01.md): tên tiếng Trung của nơi đóng hàng, cảng đến, cửa khẩu.

## Hành vi và bất biến

- VND nguyên (BigInt), mọi tổng tính ở model từ dòng chi tiết (ARCH-03), không số nào nhập tay. NULL không thành 0: thiếu giá thì ô trống, tổng trống ("—") và chặn bản chính thức.
- TOTAL DUE = tổng thành tiền container + tổng dòng phí không gắn container; Subtotal trang 1 phải bằng TOTAL DUE.
- Số container chỉ đếm dòng container; dòng phí không gắn container không đánh số.
- USD: chia tổng VND cho một tỷ giá một lần, làm tròn nửa lên 2 số lẻ; không quy đổi từng dòng.
- Hạn thanh toán = ngày phát hành + số ngày thanh toán. Ngày in "01 Dec 2025" ở mọi nơi; 0 in "–", số âm trong ngoặc đơn.
- Không cộng phiếu thu, nợ cũ, điều chỉnh cả tháng vào chứng từ.

## Module và kiểm

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Dòng chứng từ, tổng, tóm tắt cảng, USD, số bằng chữ, ISO 6346, kiểm tra trước phát hành | `preview/so-khach-v7-model.js` `debitNote`, `debitNoteChecks` | `test-so-khach-v7-model.js` (các trường hợp kiểm thử của đặc tả v3) |
| Bản in (HTML/CSS, thu nhỏ trang 1) | `preview/debit-note-print.js` | `test-debit-note-xlsx.js` |
| File Excel đối chiếu | `preview/debit-note-xlsx.js` | `test-debit-note-xlsx.js` (mở zip, CRC, XML) |
| Form, xem trước, in, tải, nhớ thông tin | `preview/so-khach-v7-debit-ui.js` | `test-so-khach-v7-debit-browser.js` |

## Tiêu chí nghiệm thu

- [x] `npm run check` xanh.
- [x] Các trường hợp kiểm thử của đặc tả v3: 409,500,000; 8,309,100,000 và tổng từng loại phí tháng 8; 320,196.53 / 322,683.50 USD; ba câu số bằng chữ; hạn 14 Nov 2026.
- [x] Hộp mở/đóng bằng bàn phím, Esc trả focus về nút; tải Excel ra file mở được; In dựng đủ dòng.
- [ ] Người dùng xuất một tháng của sổ thật trên `hao`, đối chiếu với bản v3 đã duyệt (CÒN MỞ).

## Mẫu v4 (DEBIT-NOTE-03)

Trạng thái: ĐÃ CHỐT 10/11/2026 ([`DEBIT-NOTE-03`](../docs/decisions/debit-note-03.md)), ĐÃ CODE; mặc định vẫn mẫu v3 tới khi team duyệt. Thiết kế: [`docs/debit-note-v4/SPEC.md`](../docs/debit-note-v4/SPEC.md) và trang mẫu `docs/debit-note-v4/reference/*.html` (CSS chép gần như nguyên văn).

### Luồng

1. Bấm **Debit note** ở tiêu đề tháng như v3. Trang đọc `GET /api/v7/debit-note/config`: `template` là `v4` (hoặc địa chỉ trang có `?debit=v4`) thì mở hộp v4.
2. Bên trái người lập điền số debit note (gợi ý `HTH-yymm-001`), ngày phát hành (trống thì in `[Issue date]`), tên khách Latin và tiếng Trung, tên pháp lý và địa chỉ, người liên hệ; trình duyệt nhớ phần khách theo sổ. Công ty, ngân hàng, tên phí lấy từ cấu hình, không điền ở hộp.
3. Bên phải là danh sách **Chặn / Cảnh báo / Lưu ý** và bản xem trước đã chia trang. Còn **Chặn** (một trong 6 phép kiểm sai, thiếu giá, thiếu số tháng của máy chủ, không đọc được cấu hình) thì **In / Lưu PDF** và **Tải Excel** bị khóa. Còn **Cảnh báo** thì tích "Tôi đã xem các cảnh báo, cho xuất".
4. **In / Lưu PDF** chia trang lại trong khung in rồi mở hộp in (A4 ngang, lề 0); **Tải Excel** tải `<số>_<khách>_<yyyy-mm>.xlsx`.

### Đối chiếu dữ liệu

| Trên chứng từ | Nguồn |
| --- | --- |
| Dòng container | như v3: chuyến web `confirmed` chưa xóa + dòng sổ gốc `kind='trip'` của tháng công nợ; xếp theo ngày đóng hàng rồi số container |
| Cột phí | `LUMP_SUM` (Unit price) + các cột riêng của sổ (`fee_columns`, theo thứ tự) + Khác (mọi loại còn lại); mã loại qua `dnFeeCode`, tên Anh/Trung và bề rộng ở `config.fees[mã]`; cột chỉ hiện khi có ô khác 0 trên cả chứng từ |
| Amount của dòng | thành tiền của sổ (`amount_vnd`, `counted_vnd`, `source_total_vnd`); phép 1 so với Unit price + phí |
| B/L no. | không có (sổ chưa có số B/L) |
| Opening balance | `months[].prior_months_vnd` của tháng |
| This debit note | Total Amount |
| Payments received | `received_vnd − (charges_vnd − Total)`: thu + cấn trừ + điều chỉnh của tháng; ngày = phiếu thu/cấn trừ đi muộn nhất trong tháng |
| Outstanding balance | `months[].end_of_month_vnd` |
| Công ty, ngân hàng, tên phí | `GET /api/v7/debit-note/config` (`web/debit-note-config.default.json` + file `WEBDEBIT_DEBIT_NOTE_CONFIG` ngoài repo) |

### Module và kiểm

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Dựng chứng từ, 6 phép kiểm, HTML trang, chia trang | `preview/debit-note-v4.js` | `test-debit-note-v4.js` |
| Excel v4, bố cục theo PDF (hai khối cạnh nhau; tháng chỉ có Unit price thì tên khối thành hàng riêng; tên/địa chỉ dài tự ngắt hàng) | `preview/debit-note-v4-xlsx.js` | `test-debit-note-v4.js`; mở bằng Excel thật, xuất PDF xem không có ô `###` |
| PDF bằng Chromium headless (dữ liệu mẫu, `--repeat`, `--long`) | `tools/debit-note-v4-pdf.js` | `test-debit-note-v4-browser.js` |
| Cấu hình | `web/v7_debit_note_config.py`, route trong `web/v7_ledger_api.py` | `tests/test_v7_debit_note_config.py` |
| Hộp v4, công tắc v3/v4 | `preview/so-khach-v7-debit-ui.js` | `test-so-khach-v7-debit-v4-browser.js` |

### Tiêu chí nghiệm thu (SPEC mục 9)

- [x] `data/sample-14.json` 1 trang, Total 1,070,000,000, Outstanding 19,882,128,759; `sample-30.json` 20 + 10, trang 1 "Continued on next page"; `sample-8-an-cot.json` ẩn HC fee.
- [x] Chia trang 16 → 1, 17 → 14 + 3, 30 → 20 + 10, 60 → 20 + 23 + 17; khách tên/địa chỉ dài 15 container một trang.
- [x] PDF A4 ngang (841.9 × 595.0 pt như PDF chuẩn của gói), không trang trắng, font serif đã nhúng.
- [x] 6 phép kiểm chặn ca cố tình sai; phép sai thì không ra PDF.
- [ ] So ảnh trên dữ liệu thật và team duyệt mẫu (CÒN MỞ); bật `"template": "v4"` trên `hao`.

Lệnh xuất thử: `node cong-no-web-handoff/tools/debit-note-v4-pdf.js docs/debit-note-v4/data/sample-14.json ra.pdf --png ra-trang`.

## Hoàn tác

Revert PR; không đụng dữ liệu. Thông tin đã nhớ ở trình duyệt nằm dưới khóa `debit-note:v3:*`, xóa được bằng xóa dữ liệu trang.
