# V7 — nhập chuyến kiểu Sheet: hàng trống, dán tự trải vào ô

Trạng thái: **ĐỀ XUẤT** (Claude, 22/10/2026). Ba hướng đã **người dùng chốt trong chat ngày 22/10/2026**: (1) dữ liệu vào hàng nháp, bấm **Lưu** một lần mới ghi sổ; (2) bảng nhập **chỉ nhận chuyến**, không tạo khoản thu; (3) duyệt bằng bản xem HTML dữ liệu giả trước khi code vào trang live. Chưa code vào trang live, chưa đổi API.

Bản xem: [`cong-no-web-handoff/preview/mockups/nhap-kieu-sheet/index.html`](../cong-no-web-handoff/preview/mockups/nhap-kieu-sheet/index.html) (DỮ LIỆU GIẢ, chạy trong tab, không gọi API).

## Vì sao đổi

Người dùng thử trang live ngày 22/10/2026: ô "Dán các dòng từ Sheet vào đây" không hợp lý. Copy 6 hàng từ Sheet thì cả 6 bị từ chối với lỗi "cần đúng 7 cột". Nguyên nhân:

- Ô dán chỉ nhận đúng 7 cột theo thứ tự của web (container, hãng tàu, ngày, nơi đi, nơi đến, **đơn giá, phụ phí**).
- Tab khách trên Sheet xếp khác: `A` STT · `B` container · `C` hãng tàu/số xe · `D` ngày · `E` nơi đi · `F` nơi đến · `G H I` **ba cột phí** · `J` **đơn giá** · `K` thành tiền · từ `L` là phần tiền khách trả. Đọc 61 tab trên `hao` ngày 22/10/2026: đa số theo đúng thứ tự này; một số tab có thêm một cột nhãn ở đầu (đã ghi ở `MOC-CHUYEN-MOI`). Copy nguyên hàng ra 10–11 cột, nên không bao giờ khớp 7.
- Ô dán là một ô chữ riêng, không giống bảng; sai ở đâu chỉ báo "Dòng n" chung chung.

Người dùng muốn như Excel/Google Sheet: luôn có một hàng trống; dán vào thì dữ liệu tự trải ra các ô; gõ tay cũng được.

## Người dùng và luồng (bước 1)

Người dùng trên 40 tuổi, nhập theo lô, mỗi lô một khách, 10–50 container/ngày, thường copy từ tab khách trên Sheet. Màn 1280×720.

| Việc | Thao tác | Số thao tác |
| --- | --- | --- |
| Dán một lô từ Sheet | Bôi đen các hàng trên Sheet (từ cột STT hoặc cột container, kéo tới đâu cũng được) → Ctrl+C → bấm **ô bất kỳ** của hàng trống → Ctrl+V → kiểm → **Lưu n chuyến** | **3** |
| Gõ tay một chuyến | Bấm ô container của hàng trống → gõ, Tab sang ô kế → … → Enter → **Lưu** | theo số ô |
| Sửa một ô nháp trước khi lưu | Bấm ô → gõ đè | **1** |
| Bỏ cả lô nháp | **Bỏ nháp** → xác nhận | **2** |

## Hành vi (bước 2)

**Vị trí.** Mỗi tháng **đang mở** (ổ khóa mở) có bảng nhập ngay trên dòng `Cộng tháng`, thay ô dán cũ. Trong tháng đó các dòng xếp theo thứ tự đọc của Sheet: dòng số dư đầu → các dòng từ sổ gốc → chuyến đã ghi trên web → **hàng nháp** → **một hàng trống**. Tháng khóa không có bảng nhập (giữ quy tắc `V7-SO`).

**Hàng trống.** Cùng 13 cột với sổ. Chỉ các ô chuyến nhập được: Số container, Hãng tàu / số xe, Ngày chuyến, Nơi đi, Nơi đến, Đơn giá, Phụ phí. STT, Thành tiền tự hiện; khối TIỀN KHÁCH TRẢ và NỢ của hàng nhập để xám, không nhập. Gõ vào hàng trống thì nó thành hàng nháp và **tự mọc thêm một hàng trống** bên dưới.

**Dán (Ctrl+V vào ô bất kỳ của bảng nhập).** Mỗi dòng của vùng copy thành một hàng nháp, đè từ hàng đang bấm trở xuống; thiếu hàng thì tự thêm. Cách trải vào cột:

1. Tìm cột **container** trong dòng dán: ô đầu tiên có dạng 4 chữ + 7 số (bỏ khoảng trắng). Không thấy thì coi ô của cột đang bấm là container (dán theo thứ tự cột của web, kiểu Excel).
2. Thấy container ở vị trí `c`, đọc theo bố cục tab khách: `c+1` hãng tàu, `c+2` ngày, `c+3` nơi đi, `c+4` nơi đến, `c+5..c+7` ba cột phí, `c+8` đơn giá, `c+9` thành tiền. Ô trước `c` (STT, cột nhãn) bỏ qua.
3. **Phụ phí** = cộng các ô phí có số; cả ba trống thì phụ phí trống (giá trị lưu NULL; khi đã có đơn giá thì tính 0 theo `V7-BE`).
4. **Thành tiền** của Sheet (`c+9`) không lưu, chỉ để so: lệch với đơn giá + phụ phí thì ô Thành tiền tô vàng kèm số của Sheet, **không chặn**.
5. Cột từ `c+10` trở đi (ngày trả, số tiền trả…) **bỏ qua**, hiện một dòng nhắc: "Phần tiền khách trả không nhập ở đây — ghi ở ô Ngày trả / Số tiền trả."
6. Dòng dán không có chữ nào (hàng trống, hàng cộng của Sheet có chữ "Cộng"/"TỔNG") bỏ qua.

Dán **một ô** (không có Tab, không xuống dòng) thì chỉ vào đúng ô đang bấm, như Excel.

**Bàn phím.** Tab / Shift+Tab sang ô kế / ô trước; Enter xuống ô cùng cột hàng dưới; mũi tên lên/xuống đổi hàng; Delete xóa ô; Ctrl+Z không bắt buộc ở vòng này.

**Đọc giá trị.** Ngày nhận `d/m/yyyy` hoặc `dd/mm/yyyy`, hiện lại `dd/mm/yyyy`. Số tiền nhận `75.000.000`, `75,000,000`, `75000000`; ô ghi chữ (ví dụ "chưa có giá") ở cột đơn giá coi là chưa có giá. Container chuẩn hóa viết hoa, bỏ khoảng trắng khi so trùng (giữ cách hiện tại của server).

**Lỗi ngay tại ô.** Ô sai viền đỏ, rê chuột / focus thấy lý do: thiếu container, hãng tàu, nơi đi, nơi đến; ngày không đọc được; ngày ở tương lai; số tiền không đọc được. Đơn giá trống **không** là lỗi: ô cam "chưa có giá", ngoài số dư như hiện nay.

**Lưu.** Thanh dưới bảng nhập: "n chuyến nháp · m ô cần sửa" + nút **Lưu n chuyến** (tắt khi còn ô đỏ) + **Bỏ nháp**. Lưu gửi **một lệnh dán lô** như hiện nay (`paste_trips`, một idempotency key, kiểm trùng `NEWTRIP-01`): cả lô vào hoặc không dòng nào vào. Sau khi lưu, chuyến có dấu hiệu trùng hiện CHỜ KIỂM như hiện tại; trang báo "Đã lưu n chuyến (k chuyến CHỜ KIỂM)".

**Sửa chuyến đã lưu tại chỗ** (người dùng duyệt bản xem 22/10/2026: dán đúng, nhưng lưu xong vẫn phải sửa được). Chuyến đã ghi trên web trong **tháng đang mở** hiện như hàng của bảng: mọi ô chuyến (container, hãng tàu, ngày, nơi đi, nơi đến, đơn giá, phụ phí) bấm vào là gõ đè được, như Sheet. Rời ô hoặc Enter là **lưu ngay ô đó** (không qua nháp): một ô = một lệnh, ghi Lịch sử "trước → sau" và người làm, phân bổ lại phiếu thu theo nợ cũ trước như sửa giá hiện nay (`V7-SO`). Esc trả lại giá trị cũ. Giá trị sai thì ô đỏ, không lưu. Ngày phải trong tháng của khối. Đổi container thành container đã có trong sổ thì chuyến thành CHỜ KIỂM, ngoài số dư (`NEWTRIP-01`). Enter xuống chuyến dưới; quá chuyến cuối thì vào hàng nhập.

**Nháp chưa lưu.** Chỉ sống trong tab: tải lại trang hoặc đổi khách thì hỏi "Còn n chuyến nháp chưa lưu, bỏ đi?". Không lưu nháp lên server.

## Ngoài phạm vi

- Nhập khoản thu từ bảng nhập (đã chốt chỉ nhận chuyến). Thu vẫn ghi ở ô Ngày trả / Hình thức / Số tiền trả.
- Sửa dòng từ sổ gốc (điền giá chuyến cũ thiếu giá) — CÒN MỞ ở `MOC-CHUYEN-MOI` (b) / `SONG-SONG-01`.
- Cột booking: Sheet tab khách không có cột booking; chuyến web dùng mã thay thế theo `ALT-KEY-01`, giữ như hiện nay.
- Ctrl+Z, kéo chọn nhiều ô, kéo điền (fill handle).

## Câu hỏi còn mở

1. Ngày chuyến khác tháng của khối (ví dụ dán chuyến 30/09 vào khối tháng 10): hiện server ghi theo tháng của khối. Có cần nhắc vàng tại ô ngày không?
2. Tab có bố cục khác hẳn (không theo thứ tự `B..K` ở trên): đọc thử từng tab trên bản xem trước khi code; tab lệch thì cần một cách chọn bố cục hay chỉ báo lỗi?
3. Tháng đã khóa: đơn giá/phụ phí vẫn sửa bằng dòng điều chỉnh như hiện nay (`V7-SO`); các ô chữ (container, hãng tàu, nơi đi/đến) và ngày của tháng khóa có cho sửa đè không? Bản xem chỉ có tháng đang mở.
4. Đổi ngày sang tháng khác (chuyển chuyến sang khối khác) và xóa hẳn một chuyến đã lưu: chưa có trong bản xem; cần quyết định trước khi code.
5. Dòng từ sổ gốc vẫn chỉ đọc cho tới khi chốt `MOC-CHUYEN-MOI` (b).

## Tiêu chí duyệt bản xem

- [ ] Copy 6 hàng từ tab khách (từ cột STT tới cột thành tiền), bấm ô bất kỳ của hàng trống, Ctrl+V: ra 6 hàng nháp đúng cột, phụ phí là tổng ba cột phí, thêm một hàng trống bên dưới.
- [ ] Copy từ cột container thay vì từ STT: kết quả như trên.
- [ ] Copy cả phần tiền khách trả: chuyến vào đúng, có dòng nhắc, không tạo khoản thu.
- [ ] Gõ tay một chuyến bằng Tab/Enter, không dùng chuột sau ô đầu.
- [ ] Ô ngày sai và ô thiếu nơi đến tô đỏ, nút Lưu tắt; sửa xong nút bật.
- [ ] Thành tiền Sheet lệch: ô vàng, không chặn Lưu.
- [ ] Lưu: hàng nháp thành chuyến đã ghi, tổng tháng đổi; chuyến trùng container với dòng sổ gốc thành CHỜ KIỂM, không cộng nợ.
- [ ] Chuyến đã lưu: bấm ô, gõ đè, Enter → lưu ngay, Lịch sử có trước → sau; điền giá cho chuyến chưa có giá thì tổng tháng tăng; ngày khác tháng → ô đỏ, Esc trả lại.
- [ ] 1280×720: không cuộn ngang.

## Khi code vào trang live (sau khi duyệt)

Map thao tác → module → kiểm:

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Đọc vùng dán theo bố cục tab khách | `so-khach-v7-model.js` (hàm thay `parsePastedTrips`) | unit: 7/10/11 cột, cột nhãn đầu, phí cộng, phí trống, thành tiền lệch, hàng tổng, ngày 1 chữ số |
| Bảng nhập, bàn phím, ô lỗi | `so-khach-v7-ui.js`, `so-khach-v7-live.html` | browser (Playwright): dán, Tab/Enter, Lưu tắt/bật, 1280×720 không cuộn ngang |
| Lưu | `so-khach-v7-api.js` → `/api/v7/trips/paste` (không đổi API) | unit: một lệnh, một key; dán trùng → CHỜ KIỂM |
| Sửa ô chuyến đã lưu | đơn giá/phụ phí: `/api/v7/trips/price` (đã có). Container, hãng tàu, ngày, nơi đi/đến: **cần lệnh mới** (backend, `v7_backend_functions.sql` + `v7_ledger_api.py`) ghi event trước → sau, kiểm trùng lại khi đổi container/ngày | DB test: sửa từng trường, Lịch sử đúng, đổi container trùng → CHỜ KIỂM, tháng khóa bị chặn theo quyết định câu 3 |
