# Debit note theo tháng công nợ

Trạng thái: ĐÃ CHỐT. Chọn theo tháng công nợ, xuất PDF và Excel: người dùng, 29/10/2026, [`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md). Bố cục và quy tắc theo mẫu Debit Note v3 sếp duyệt 30/10/2026: [`DEBIT-NOTE-02`](../docs/decisions/debit-note-02.md). Các điểm Claude chọn và điểm CÒN MỞ ghi trong hai file quyết định.

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
| LOADING PLACE, POD | `origin`, `destination`, chuẩn theo danh mục nơi/cảng | `current.*` / `display.from`, `display.to` |
| LUMP-SUM | `unit_price_vnd`; `is_missing_price` → thiếu | `current.unit_price_vnd` / số trong `display.unit_price` |
| 7 loại phí còn lại và loại ngoài danh mục | `fee_lines` gom theo mã loại phí (bảng ánh xạ ở `DEBIT-NOTE-02`) | như chuyến web |
| AMOUNT | LUMP-SUM + phí của dòng; khác `amount_vnd` của sổ thì chặn | khác `current.counted_vnd` / `source_total_vnd` thì chặn |
| Dòng ADDITIONAL CHARGES | chuyến `is_fee_only`: mỗi khoản phí một dòng (loại, ngày, ghi chú, số tiền) | dòng không có số container, như chuyến web |

Lấy chuyến web `status='confirmed'`, chưa xóa; dòng sổ gốc chưa xóa. Tháng = tháng công nợ (`month`). Thứ tự theo ngày đóng hàng, cùng ngày giữ thứ tự sổ (sổ gốc trước, web sau). Thông tin cấp chứng từ (số, ngày, bên phát hành, khách, thanh toán, tỷ giá) không có trên sổ: người lập điền ở form.

Đặc tả v3 ghi dev đọc dữ liệu từ Sheet "Bộ lập bill". Ở web, nguồn là sổ khách V7 (đã đồng bộ từ Sheet qua luồng duyệt chuyến), như `DEBIT-NOTE-01`.

## Giao tiếp frontend–backend (bước 5, khi có)

Không có lệnh mới. Chứng từ dựng từ bản sổ trang đã tải (`ctx.snapshot`), danh mục phụ phí (`ctx.feeTypes`) và dòng khách (`SoKhachV7Api.customerRow`). Thông tin người lập điền chỉ lưu ở trình duyệt (`localStorage`), không gửi máy chủ.

## Nguồn quyết định

- [`DEBIT-NOTE-01`](../docs/decisions/debit-note-01.md): theo tháng công nợ, PDF + Excel, chỉ chuyến của tháng.
- [`DEBIT-NOTE-02`](../docs/decisions/debit-note-02.md): mẫu Debit Note v3 sếp duyệt (bố cục, danh mục phí, quy tắc tính, kiểm tra trước phát hành).
- [`PHU-PHI-01`](../docs/decisions/phu-phi-01.md) (2): chứng từ gửi khách hiện từng khoản phụ phí.

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

## Hoàn tác

Revert PR; không đụng dữ liệu. Thông tin đã nhớ ở trình duyệt nằm dưới khóa `debit-note:v3:*`, xóa được bằng xóa dữ liệu trang.
