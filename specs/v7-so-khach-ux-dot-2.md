# Sổ khách: một sổ, một tháng đang làm (UX đợt 2)

Trạng thái: **ĐÃ CHỐT** luồng L1–L7 và sáu lựa chọn H1–H6 (người dùng, 31/10/2026, chat: "Chốt theo đề xuất") — [`SO-GON-04`](../docs/decisions/so-gon-04.md). Spec do Claude viết theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md), là đợt 2 của [audit UX 31/10](../docs/ux-audit-2026-10-31.md) (mục 4.2 và 5). Chưa code. Spec chỉ đổi giao diện trang live `so-khach-v7-live.html`: không đổi luật tiền, phân bổ, khóa tháng, API hay DB. Trang mẫu fixture `so-khach-v7.html` giữ nguyên như các đợt trước.

Phạm vi theo mã audit: **P0-1** (nhảy tháng), **P0-2** (cỡ chữ), **P0-4** (khung ghi phiếu và "+ thêm" lặp), **P0-5** (xem lại trước khi ghi), **P1-4** (Lịch sử viết thành câu), **P1-8** (thanh trên và màu riêng của sổ khách), **P1-10** (bàn phím). Ngoài phạm vi: hộp thư việc, trang chọn khách, hộp thoại dùng chung, ma trận, Đòi nợ (đợt 3); từ điển giao diện vẫn chờ chốt, nhưng chữ mới trong đợt này dùng từ của bảng 4.5 trong audit.

Sửa so với audit: mục 4.2.6 (hàng nhập chuyến theo `NHAP-SHEET-01`) **bỏ khỏi đợt 2**. Ngày 29/10/2026 người dùng đã bỏ bảng nhập chuyến ([`NHAP-SHEET-02`](../docs/decisions/nhap-sheet-02.md)): chuyến mới lấy từ Sheet. Audit viết sau nhưng chưa đối chiếu quyết định này. Đường nhập chuyến khi chuyển hẳn sang web là việc riêng, xét lại theo `NHAP-SHEET-02`.

## Người dùng và luồng (bước 1)

Người dùng: **người nhập** (ghi phiếu thu, sửa giá, kết luận chờ kiểm, khóa tháng; cuối ngày đối soát) và **chủ nghiệp vụ** (mở sổ từ Tổng quan hoặc Đòi nợ để xem nợ một khách). Trên 40 tuổi, màn 1280×720 (khoảng 1280×560 nhìn thấy trong Chrome), chữ thân ≥ 16px, vùng bấm ≥ 40px ([hướng dẫn UX](../docs/ux-guidelines.md)). Đang chạy song song: Sheet là sổ chính thức, sổ web nhận chuyến, giá và phiếu thu từ Sheet ([`SONG-SONG-01`](../docs/decisions/song-song-01.md)).

Khối lượng thật (đo trên `hao` 31/10/2026, chỉ đọc): sổ nợ nhiều nhất có 9 tháng, 387 dòng chuyến, trang cao 17.734px (khoảng 25 màn hình), một tháng riêng đã 126 dòng. Phần dính đầu trang hiện là 56 (thanh trên) + 70 (đầu sổ) + 38 (tiêu đề cột) + 42 (thanh tháng) = 206px.

### L1. Mở sổ và tới đúng tháng

1. Người dùng mở sổ từ ô tìm khách, Tổng quan, Công nợ theo tháng, Việc cần làm hoặc Đòi nợ.
2. Sổ hiện **tháng hiện tại và tháng liền trước** mở sẵn (H1). Mỗi tháng cũ gập thành một dòng: tên tháng, ổ khóa, số chuyến, Còn nợ cuối tháng, nút Debit note, nút "Mở tháng".
3. **Thanh tháng** dính dưới đầu sổ: mỗi tháng một chip "T9/2026" kèm Còn nợ cuối tháng và ổ khóa; chip của tháng đang ở giữa màn hình được tô. Tháng có việc chờ (chuyến chưa có giá, chờ kiểm, chuyến Sheet chờ duyệt) thì chip có chấm cam và số việc, bấm vào thấy chữ "2 chưa có giá".
4. Bấm chip: tháng gập thì mở ra, rồi cuộn tới thanh của tháng đó. Thanh tháng thay "DANH SÁCH THÁNG" bên phải (đang bị ẩn dưới 1440px).
5. Địa chỉ `?customer=…&month=2026-09` mở sẵn và cuộn tới tháng đó. Ngăn kéo ma trận (Công nợ theo tháng) gửi tháng đang xem; Đòi nợ gửi tháng nợ cũ nhất còn nợ. Hai đường này là hai dòng sửa link, nằm trong cùng PR.
6. Đi vào bằng `?loc=thieu-gia|cho-kiem` thì mọi tháng có dòng cần xử lý tự mở; "Đến dòng tiếp ›" đi qua cả các tháng đó.

Kết quả: sổ 9 tháng 387 dòng chỉ vẽ khoảng 180 dòng lúc mở, và tới bất kỳ tháng nào bằng một lần bấm.

### L2. Ghi một phiếu thu

1. Nút chính **"Ghi phiếu thu"** ở đầu sổ (luôn thấy khi cuộn) mở khung bên phải, theo mẫu ngăn phụ phí đã có (H2). Khung "Ghi phiếu mới" ở cuối mỗi tháng **bỏ**: sổ thật hiện có 9 khung giống nhau.
2. Ô: Ngày trả (dd/mm/yyyy, có nút "Hôm nay"), Hình thức, Số tiền (VND), Tham chiếu (tùy chọn), chỗ dán ảnh chứng từ ([`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md)). Enter ở Ngày nhảy sang Số tiền như hiện nay.
3. Enter ở Số tiền hoặc bấm "Xem lại" thì hiện **bước xem lại** trong cùng khung: "Ghi phiếu **50.000.000 đ** · THU TIỀN · ngày 30/10/2026, nằm ở tháng 10/2026. Tổng còn nợ: 1.250.000.000 đ → 1.200.000.000 đ." Nếu tiền vượt tổng nợ: "Khách sẽ dư 15.000.000 đ." Ngày thuộc tháng đã khóa: "Tháng 8/2026 đang khóa; phiếu vẫn ghi được." (như hiện nay: ghi phiếu không xét ổ khóa, `record_receipt` không kiểm khóa tháng) Nút **Ghi phiếu** là tiêu điểm mặc định, nút **Sửa lại** đưa về ô Số tiền. Tổng gõ phím chỉ thêm một Enter, không cần thêm chuột.
4. Ghi xong thì khung đóng. Tháng của phiếu tự mở và cuộn tới, dòng phiếu mới tô xanh 3 giây. Băng báo: "Đã ghi phiếu PH-012 · 50.000.000 đ · trừ nợ T8/2026 1.000.000 · T9/2026 49.000.000", lấy từ kết quả server trả về, kèm nút **"Hủy phiếu vừa ghi"** (H3).
5. "Hủy phiếu vừa ghi" mở dòng hủy phiếu đang có với lý do điền sẵn "Ghi nhầm, hủy ngay sau khi ghi" (sửa được) và nút Hủy phiếu. Đường hủy, lý do bắt buộc và Lịch sử giữ nguyên ([`V7-SO`](../docs/decisions/v7-so.md)).
6. Hình thức CẤN TRỪ: bước 3 thay bằng hộp xác nhận cấn trừ đang có ([`CT-2SO`](../docs/decisions/ct-2so.md)), không thêm bước.

Bị chặn: ngày sau hôm nay thì báo lỗi tại ô Ngày, giữ số đã gõ (như hiện nay, lỗi `FUTURE_RECEIPT_DATE`); sổ đổi dưới tay thì băng "Sổ vừa thay đổi", giữ khung và số đã gõ; mất mạng giữa lệnh ghi thì dùng đường "Thử lại thao tác vừa gửi" đang có (cùng khóa chống trùng).

### L3. Khóa / mở khóa tháng

1. Bấm ổ khóa (trên thanh tháng, chip, hoặc nút "Mở khóa tháng" trong khung giá Sheet) thì hiện một dòng hỏi ngay dưới nút. Khóa: "Khóa tháng 10/2026? Sau khi khóa, sửa tiền trong tháng sẽ thành dòng điều chỉnh." Mở: "Mở khóa tháng 9/2026? Trong tháng mở, sửa ô sẽ ghi đè (vẫn có Lịch sử)."
2. Hai nút **Khóa tháng 10** / **Thôi** (hoặc **Mở khóa tháng 9** / **Thôi**); Esc là Thôi.

### L4. Duyệt chuyến mới từ Sheet

1. Bấm "Duyệt n chuyến mới" thì hiện khung xác nhận theo mẫu "Ghi n phiếu thu từ Sheet": "Duyệt n chuyến mới từ Sheet? Chuyến có giá tính tiền ngay; chuyến chưa có giá chưa tính; chuyến nghi trùng thành chờ kiểm." Nút **Duyệt n chuyến** / **Thôi**.
2. "Lấy từ Sheet / Làm mới" **không** thêm bước hỏi: lệnh này chỉ đọc Sheet vào hàng chờ, không ghi sổ (audit P0-5 xếp chung, nhưng nó không phải hành động tiền).

### L5. Đọc và sửa bảng chuyến

- Chữ trong bảng 16px, tiêu đề cột 15px, hàng 40px; không vừa 1280 thì cột chữ 15px, số tiền giữ 16px (H4).
- "+ thêm" ở ô phụ phí trống chỉ hiện khi rê chuột vào dòng, khi tiêu điểm ở dòng, hoặc khi dòng đang được tick chọn; còn lại ô trống ghi "–" như [`SO-GON-02`](../docs/decisions/so-gon-02.md) (4).
- Trạng thái dòng là nhãn chữ có nền màu trong cột Thành tiền: "chưa có giá" (cam), "chờ kiểm" (vàng; bấm mở dòng kết luận như nút CHỮ HOA hiện nay), "đã loại" (xám gạch).
- Bàn phím: Tab / Shift+Tab sang ô sửa kế trong hàng; Enter ở ô đang sửa thì ghi rồi tiêu điểm xuống ô cùng cột ở hàng dưới; mũi tên lên/xuống đổi hàng khi không đang gõ. Esc đóng mọi dòng hỏi trong bảng (hủy, xóa, chờ kiểm, chuyển tháng, điều chỉnh, khóa tháng) và Lịch sử, rồi trả tiêu điểm về chỗ đã mở.

### L6. Lịch sử đọc như câu

Mỗi sự kiện một dòng: giờ · người làm (tên hiển thị theo [`PRESENCE-01`](../docs/decisions/presence-01.md), không phải login) · câu. Ví dụ: "15/10/2026 10:12 · Thu · **Ghi phiếu thu** 200.000.000 đ ngày 15/10/2026 (trừ T8 1.000.000 · T9 199.000.000)". Lý do chỉ hiện khi có (bỏ "Ghi chú/lý do: –"). Lọc theo loại: Thu · Chuyến · Giá/phụ phí · Khóa tháng · Tất cả. Esc đóng, tiêu điểm về nút Lịch sử.

### L7. Đầu sổ một nút chính

Đầu sổ (một dòng): ô tìm khách · mặt hàng · **Tổng còn nợ** · nút chính **Ghi phiếu thu** · nút "Thêm ▾" gom Lịch sử, Cài đặt phụ phí, Bảng giá. Các nút theo việc chờ (Duyệt n chuyến mới, Ghi n giá từ Sheet, Ghi n phiếu thu từ Sheet, Phụ phí PS cần xem) vẫn ở dải ngay dưới đầu sổ như hiện nay. "↻ Làm mới" và "Ẩn con trỏ" rời thanh xanh trên cùng: Làm mới về dòng đầu sổ như các trang khác, Ẩn con trỏ vào menu "Đang xem" của presence.

## Đầu ra

Trên máy chủ giả và sau đó trên `hao`: sổ mở ở tháng hiện tại với thanh tháng dính; tháng cũ gập; `?month=` mở đúng tháng; một nút Ghi phiếu thu duy nhất có bước xem lại và băng kết quả kèm phân bổ của server; khóa/mở tháng và duyệt chuyến mới có câu hỏi; chữ bảng 16px; "+ thêm" không còn trên mọi dòng; Lịch sử thành câu; đi được bằng Tab/Enter/mũi tên. Mọi số tiền trên màn hình không đổi so với trước (cùng GET).

## Đối chiếu dữ liệu và code hiện có (bước 2)

Mọi số tiền lấy nguyên từ `GET /api/v7/ledger`; model chỉ định dạng và cộng cột phụ phí (ARCH-03). Không cần trường mới.

| Cần trên màn hình | Lấy từ | Đã có | Ghi chú |
| --- | --- | --- | --- |
| Danh sách tháng, Còn nợ cuối tháng từng chip | `months[].month`, `months[].end_of_month_vnd` | có | Như thanh tháng hiện nay (`monthBar`, `so-khach-v7-month-ui.js`) |
| Ổ khóa từng tháng, tháng mở mặc định | `month_locks[]`, `today_month` | có | `bookMonths`/`monthSection`; tháng không có trong `month_locks` thì khóa trừ `today_month` (giữ nguyên) |
| Số chuyến tháng gập | đếm `trips[]` + dòng chuyến `legacy_rows[]` theo tháng | có | Đếm ở phần vẽ, không phải tiền |
| Việc chờ trên chip | `trips[].unit_price_vnd === null`, `status === 'pending_review'`, `sheet_sync.items` chưa vào sổ | có | Cùng điều kiện `so-khach-v7-loc-ui.js` và `sheetPending` |
| Tổng còn nợ trước → sau ở bước xem lại | `total_outstanding_vnd` − số tiền phiếu | có | Cùng phép của `model.planSheetReceipts` (khung "Ghi n phiếu thu từ Sheet"); âm thì ghi "khách dư" |
| Phiếu sẽ nằm ở tháng nào | tháng của ngày phiếu | có | Theo [`DA-THU-01`](../docs/decisions/da-thu-01.md) |
| Phân bổ **trước** khi ghi | — | **không** | `record_receipt` phân bổ theo nợ thô (`v_outstanding_month_raw`) rồi `reallocate` mọi phiếu theo (ngày, mã phiếu); GET chỉ có `months[].outstanding_vnd` đã qua CAN-DU-01. Trang không tự tính lại được cho đúng, nên bước xem lại **không** hiện phân bổ từng tháng (H5) |
| Phân bổ **sau** khi ghi | kết quả `POST` ghi phiếu: `pid`, `allocations[]`, `overpayment_vnd`, `duplicate_reference` | có | `api.lastOutcome().result` (`so-khach-v7-api.js`); băng hiện đúng số server |
| Dòng hủy phiếu, lý do bắt buộc | dòng `.void-prompt` của `so-khach-v7-edit-ui.js`, lệnh `receiptVoid` | có | Chỉ thêm giá trị điền sẵn |
| Ảnh chứng từ của phiếu mới | `ctx.imageEntryBox(month)`, `ctx.afterReceiptSaved(month, pid)` (`so-khach-v7-images-ui.js`) | có | Nháp ảnh đang theo khóa tháng của khung; đổi thành một khóa của khung duy nhất |
| Cấn trừ từ khung ghi phiếu | `startOffset(row)` (`so-khach-v7-offset-ui.js`) | có | Đổi tham số từ hàng của tháng sang khung |
| Câu Lịch sử | `events[]` (`kind`, `actor`, `before`, `after`, `created_at`), `eventLabels` của `so-khach-v7-history-ui.js` | có | Tên hiển thị người làm: bảng tên của `presence.js` |
| Duyệt chuyến mới | `sheet_sync.new_count`, `sheet_sync.snapshot_sha256` | có | Chỉ thêm bước xác nhận trước `POST /api/v7/sheet/approve` |

Câu thông báo đang có, giữ nguyên: "Sổ vừa thay đổi. Kiểm tra dữ liệu mới rồi thực hiện lại.", lỗi ngày tương lai của server, "Cần nhập lý do". Câu thay: băng trơn "Đã lưu." sau khi ghi phiếu thành câu ở bước L2.4; các thao tác khác giữ như cũ.

Dữ liệu cho test: máy chủ giả `so-khach-v7-browser-world.js` (16 khách giả, một sổ 3 tháng). Cần thêm một sổ giả **9 tháng, khoảng 300 dòng** để đo gập tháng, thanh tháng và chiều cao; dữ liệu bịa, không chép số khách thật.

## Giao tiếp frontend–backend (bước 5)

Không thêm và không đổi API. Dùng các lệnh đang có qua `api.submit`: `receipt`, `receiptVoid`, `lock`, `submitOffset`; `POST /api/v7/sheet/approve`. Quyền và điều kiện ghi do backend kiểm như hiện nay; bước xem lại chỉ là giao diện, không thay kiểm ở server. Nếu người dùng chọn hiện phân bổ trước khi ghi (H5), cần một hàm đọc thử ở DB, viết thành spec backend riêng, không thuộc đợt này.

## Nguồn quyết định

- Nền đã chốt: [`SO-GON-01`](../docs/decisions/so-gon-01.md), [`SO-GON-02`](../docs/decisions/so-gon-02.md), [`SO-GON-03`](../docs/decisions/so-gon-03.md) (mỗi số tiền của tháng hiện một lần; thanh tháng chỉ còn Còn nợ cuối tháng), [`NHAP-SHEET-01`](../docs/decisions/nhap-sheet-01.md) (2)–(7), [`NHAP-SHEET-02`](../docs/decisions/nhap-sheet-02.md), [`V7-SO`](../docs/decisions/v7-so.md) (ổ khóa, hủy phiếu bắt buộc lý do), [`V7-CSM`](../docs/decisions/v7-csm.md) (D07: mỗi lần mở/khóa ghi Lịch sử), [`DA-THU-01`](../docs/decisions/da-thu-01.md), [`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md), [`PRESENCE-01`](../docs/decisions/presence-01.md).
- Đề xuất: [audit UX 31/10/2026](../docs/ux-audit-2026-10-31.md), mục P0-1, P0-2, P0-4, P0-5, P1-4, P1-8, P1-10, 4.2, 4.6, 4.7. Phần audit thuộc đợt 2 và sáu lựa chọn H1–H6 đã chốt thành [`SO-GON-04`](../docs/decisions/so-gon-04.md) (31/10/2026).

## Hành vi và bất biến

- Không đổi một số tiền nào trên màn hình: tổng còn nợ, Còn nợ cuối tháng, Thành tiền, Đã thu, tổng cột phụ phí trước và sau phải bằng nhau trên mọi sổ giả (so DOM số, không so ảnh).
- Tháng gập vẫn tính trong tổng; gập chỉ là không vẽ dòng chuyến/phiếu. Tổng còn nợ ở đầu sổ không đổi khi gập/mở.
- Phiếu thu vẫn ghi được với ngày thuộc tháng khóa, như hiện nay; bước xem lại không chặn, chỉ ghi rõ.
- Bước xem lại không gửi lệnh nào. Từ lúc bấm Ghi phiếu tới lúc server trả lời chỉ có **một** `POST` ghi phiếu, kể cả khi bấm hay Enter liên tiếp (khóa chống trùng `idempotency_key` đang có).
- Hủy phiếu luôn có lý do không trống và đi qua lệnh `receiptVoid` đang có; không có đường hủy nào bỏ qua lý do.
- Phần đang mở dở (ô sửa, dòng hỏi, khung ghi phiếu có số, nháp ảnh) chặn tự cập nhật qua `ctx.busyChecks`, như hiện nay; không gập được tháng đang có ô sửa mở.
- Mọi đường tìm dòng trong DOM phải mở tháng chứa dòng trước khi tìm: `?loc`, "Đến dòng tiếp ›", ghost "Xem", "Xem khoản cũ" (`receipt-goto`), nhãn KHÁC của đối chiếu Sheet, tô giá (`decoratePrices`), chọn nhiều chuyến cho phụ phí.
- Thêm phần mới theo hợp đồng `ctx`: khai `FIELDS`/`PARTS` ở `so-khach-v7-ctx.js`; `test-so-khach-v7-ctx.js` phải xanh.
- Không thêm thư viện, framework hay bước build.

## Chia PR

Bốn PR nối tiếp, mỗi PR một vùng file, mỗi PR tự xanh `npm run check` và tự triển khai khi merge (chỉ đổi file giao diện):

| PR | Nội dung | File chính | Ngân sách |
| --- | --- | --- | --- |
| **2a · Thanh tháng và gập tháng** | L1; bỏ `.months-nav`; offset dính mới | `so-khach-v7-month-ui.js`, `so-khach-v7-ui.js` (`renderShell`), `so-khach-v7-loc-ui.js`, `so-khach-v7.css`, `so-khach-v7-ctx.js`, link `?month=` ở `cong-no-theo-thang.js`, `doi-no.js`; sổ giả 9 tháng ở `so-khach-v7-browser-world.js`; test mới `test-so-khach-v7-month-browser.js` | 450 dòng |
| **2b · Một khung ghi phiếu, xem lại, hỏi khóa tháng** | L2, L3, L4 | `so-khach-v7-pay-ui.js`, `so-khach-v7-edit-ui.js` (`saveNewReceipt`, khóa tháng), `so-khach-v7-images-ui.js` (khóa nháp), `so-khach-v7-offset-ui.js` (`startOffset`), `so-khach-v7-sheet-ui.js` (duyệt, mở khóa), `so-khach-v7.css`; cập nhật `test-so-khach-v7-receipt-browser.js`, `-images-`, `-offset-`, `-edit-`, `-sheet-` | 500 dòng |
| **2c · Chữ, "+ thêm", nhãn trạng thái, đầu sổ** | L5 (trừ bàn phím), L7 | `so-khach-v7.css`, `so-khach-v7-trips-ui.js`, `so-khach-v7-fee-ui.js`, `so-khach-v7-ui.js` (đầu sổ), `so-khach-v7-presence-ui.js`, `so-khach-v7-live.html` | 350 dòng |
| **2d · Lịch sử và bàn phím** | L5 bàn phím, L6 | `so-khach-v7-history-ui.js`, `so-khach-v7-edit-ui.js` (tiêu điểm sau ghi), `so-khach-v7-price-ui.js` (mũi tên ở lưới giá) | 350 dòng |

Thứ tự 2a → 2b vì 2b cần biết tháng nào đang mở để cuộn tới phiếu mới; 2c và 2d làm sau 2b vì cùng sửa `so-khach-v7-edit-ui.js`/CSS.

## Tiêu chí nghiệm thu

PR 2a:
- [ ] Sổ giả 9 tháng ở 1280×720: lúc mở chỉ có bảng dòng của tháng hiện tại và tháng liền trước; 7 tháng còn lại là dòng gập có Còn nợ cuối tháng đúng bằng số GET.
- [ ] Thanh tháng có 9 chip, dính khi cuộn; chip của tháng đang ở giữa màn được tô; bấm chip của tháng gập thì tháng mở và thanh tháng của nó nằm ngay dưới phần dính.
- [ ] Tổng chiều cao phần dính ≤ 180px (hiện 206px); không cuộn ngang ở 1280.
- [ ] `?month=2026-05` mở và cuộn tới tháng 5; tháng không có trong sổ thì mở bình thường, không lỗi.
- [ ] `?loc=thieu-gia` trên sổ có dòng chưa có giá ở tháng gập: tháng đó tự mở, "Đến dòng tiếp ›" đi hết mọi dòng như trước.
- [ ] So số trước/sau (bản `main` và bản PR) trên mọi sổ giả: mọi số tiền trong `#app` sau khi mở hết các tháng bằng nhau.

PR 2b:
- [ ] Sổ không còn khung "Ghi phiếu mới" trong từng tháng; nút Ghi phiếu thu ở đầu sổ thấy được ở mọi vị trí cuộn.
- [ ] Ngày + số tiền + Enter → bước xem lại, chưa có `POST`; Enter tiếp → đúng một `POST` ghi phiếu; tiêu điểm mặc định ở Ghi phiếu; Sửa lại hoặc Esc về ô Số tiền, số đã gõ còn nguyên.
- [ ] Bấm Ghi phiếu hai lần nhanh / Enter giữ phím: vẫn một phiếu.
- [ ] Sau khi ghi: băng hiện mã phiếu, số tiền và phân bổ đúng `allocations` server trả; tháng của phiếu mở; dòng mới tô.
- [ ] "Hủy phiếu vừa ghi" mở dòng hủy với lý do điền sẵn; xóa trống lý do thì "Cần nhập lý do", không gửi lệnh.
- [ ] Ngày tương lai → lỗi tại ô Ngày, không có `POST` thứ hai; mất mạng khi ghi (`page.route` abort một lần) → "Thử lại thao tác vừa gửi" ghi đúng một phiếu.
- [ ] Ngày thuộc tháng khóa → bước xem lại có câu tháng khóa, ghi được.
- [ ] Hình thức CẤN TRỪ → hộp cấn trừ như cũ; ảnh dán trong khung được đính vào phiếu vừa ghi.
- [ ] Bấm ổ khóa → dòng hỏi; Thôi/Esc không gửi lệnh; Khóa tháng → một lệnh `lock`. Tương tự cho mở khóa và nút mở khóa ở khung giá Sheet.
- [ ] Duyệt n chuyến mới → khung xác nhận; Thôi không gửi `POST /api/v7/sheet/approve`.

PR 2c:
- [ ] Không chữ nào < 14px trong `.ledger td` và `.pay-list`; số tiền và chữ thân trong bảng 16px; vẫn không cuộn ngang ở 1280 với sổ có Shipper và 3 cột phụ phí riêng.
- [ ] Sổ giả 300 dòng: số chữ "+ thêm" đang hiện = 0 khi không rê chuột; rê vào dòng hoặc Tab tới ô thì hiện; tick chọn dòng thì hiện.
- [ ] Chờ kiểm là nhãn "chờ kiểm" bấm được và mở dòng kết luận như trước; chưa có giá có nhãn chữ, không chỉ tô màu.
- [ ] Thanh trên của sổ khách giống các trang khác (cùng `cong-no-theme.css`): không còn "↻ Làm mới" và "Ẩn con trỏ" trong thanh xanh.

PR 2d:
- [ ] Lịch sử: mỗi sự kiện một câu, có tên hiển thị người làm; không còn "Ghi chú/lý do: –"; lọc theo loại; Esc đóng và trả tiêu điểm về nút mở.
- [ ] Tab sau khi ghi một ô đi tới ô sửa kế (không về `BODY`); Enter xuống ô cùng cột hàng dưới; mũi tên lên/xuống đổi hàng ở bảng chuyến và lưới bảng giá.
- [ ] Esc đóng mọi dòng hỏi trong bảng; tiêu điểm về ô đã mở.

Chung (bước 7–8):
- [ ] `npm run check` xanh ở từng PR; `test-so-khach-v7-ctx.js` xanh.
- [ ] Sau khi 2a–2d triển khai trên `hao`: đo lại sổ nợ nhiều nhất (chỉ đọc) — chiều cao trang lúc mở, chiều cao phần dính, số chữ "+ thêm" đang hiện; ghi vào phần Bằng chứng.
- [ ] Người dùng tự đi L1–L4 trên `hao` một lần với một phiếu thật cần ghi (không ghi thử) và xác nhận; hoặc phiên quan sát 30 phút theo mục 7 của audit.

## Hoàn tác

Mỗi PR revert riêng được (chỉ file giao diện); triển khai tự động khi merge, rollback bằng revert PR rồi để `Deploy hao` chạy lại. Không đụng dữ liệu.

## Bằng chứng

Chưa có (spec). Số đo hiện trạng lấy từ audit 31/10/2026 (mục 7 của audit).

## Lựa chọn đã chốt

Người dùng chốt 31/10/2026 trong chat, chọn đúng phương án Claude đề xuất cho cả sáu câu ([`SO-GON-04`](../docs/decisions/so-gon-04.md)). Phương án không chọn ghi lại để sau này biết đã cân nhắc gì.

- **H1 · Tháng mở sẵn:** tháng hiện tại và tháng liền trước. Không chọn: chỉ tháng hiện tại; mọi tháng còn nợ (sổ nợ lâu gần như không gập được tháng nào).
- **H2 · Chỗ ghi phiếu thu:** nút ở đầu sổ mở khung bên phải, theo mẫu ngăn phụ phí; luôn thấy dù đang cuộn tới đâu. Không chọn: khung cố định ở đầu vùng phiếu của tháng hiện tại.
- **H3 · Sửa phiếu vừa ghi nhầm:** nút "Hủy phiếu vừa ghi" mở dòng hủy với lý do điền sẵn, người dùng bấm thêm một lần; đúng `V7-SO` (hủy phải có lý do do người làm xác nhận). Không chọn: "Hoàn tác" một chạm trong 10 giây với lý do tự ghi, vì đó là ngoại lệ cho quy tắc lý do hủy.
- **H4 · Cỡ chữ bảng nếu 16px không vừa 1280:** số tiền 16px, cột chữ (container, hãng tàu, nơi đi/đến) 15px. Không chọn: ẩn/hiện cột theo sổ.
- **H5 · Phân bổ phiếu thu:** bước xem lại chỉ hiện tổng còn nợ trước → sau; phân bổ từng tháng hiện ngay sau khi ghi, đúng số server; không cần backend. Không chọn: hiện phân bổ trước khi ghi bằng hàm đọc thử ở DB.
- **H6 · Hỏi khi khóa/mở tháng:** hỏi cả khi khóa và khi mở. Không chọn: chỉ hỏi khi khóa.

## Câu hỏi mở

- Phần dính ≤ 110px như audit gợi ý chỉ đạt được khi thanh xanh trên cùng thu lại lúc cuộn trên mọi trang. Đợt này nhắm ≤ 180px; thu thanh trên để sau, nếu người dùng thấy còn chật.
