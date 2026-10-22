# V7 — nhập chuyến kiểu Sheet: hàng trống, dán tự trải vào ô

Trạng thái: **ĐỀ XUẤT** (Claude, 22/10/2026), chính sách **ĐÃ CHỐT** ở [`NHAP-SHEET-01`](../docs/decisions.md#nhap-sheet-01) (người dùng, chat 22/10/2026): nháp + **Lưu**; chỉ nhận chuyến; chuyến đã lưu sửa đè tại ô, kể cả tháng khóa; xóa hẳn được; đổi ngày sang tháng khác thì chuyến tự sang bảng tháng đó; dòng sổ gốc sửa/xóa được. Duyệt bằng bản xem HTML dữ liệu giả trước khi code. Chưa code vào trang live, chưa đổi API.

**Cập nhật 22/10/2026 (Claude):** phần **sửa tại ô và xóa hẳn** chuyến web và dòng sổ gốc đã code vào trang live (`so-khach-v7-ui.js`), nối 4 route của [`v7-sua-xoa-chuyen.md`](v7-sua-xoa-chuyen.md): bấm ô → gõ đè → Enter/Tab/rời ô lưu, Esc trả lại; bấm STT → xác nhận → xóa; dòng "Điều chỉnh do sửa/xóa dòng sổ gốc tháng này". Đơn giá/phụ phí chuyến web giữ hai lệnh cũ (sửa đè tháng mở, điều chỉnh tháng khóa). Kiểm: `test-so-khach-v7-edit-browser.js` (máy chủ giả). **Chưa làm:** bảng nhập hàng trống, dán tự trải, nháp. Chưa triển khai lên `hao`.

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

**Sửa tại ô mọi chuyến đã có** (`NHAP-SHEET-01`). Mọi dòng chuyến trong sổ — chuyến web và **dòng từ sổ gốc**, ở **tháng mở lẫn tháng khóa** — bấm ô (container, hãng tàu, ngày, nơi đi, nơi đến, đơn giá, phụ phí) là gõ đè được, như Sheet. Rời ô hoặc Enter là **lưu ngay ô đó**: một ô = một lệnh, ghi Lịch sử trước → sau và người làm, phân bổ lại phiếu thu theo nợ cũ trước (`V7-SO`). Esc trả lại giá trị cũ; giá trị sai thì ô đỏ, không lưu. Enter/mũi tên đi theo cột qua mọi dòng (sổ gốc → web → nháp) như một bảng liền.

- **Tiền ở tháng khóa** (đơn giá/phụ phí): người dùng vẫn gõ đè số mới; hệ thống ghi thành dòng điều chỉnh tính tiền ngay (`V7-SO`), Lịch sử ghi "+/− phần chênh".
- **Dòng sổ gốc**: số dư đầu **không bị viết lại**. Mỗi dòng mang số lúc nạp mốc; sửa tiền ghi phần chênh (số mới − số trong bản mốc) thành điều chỉnh; xóa dòng thì ghi trừ hết số trong bản mốc. Mỗi tháng có dòng **"Điều chỉnh do sửa/xóa dòng sổ gốc tháng này"** hiện tổng phần chênh, để phép cộng tháng nhìn thấy được: số dư đầu + điều chỉnh sổ gốc + chuyến web = Phát sinh. Điền giá cho dòng sổ gốc thiếu giá (chưa nằm trong số dư đầu) là cộng nguyên số mới.
- **Đổi ngày sang tháng khác**: chuyến **tự chuyển sang bảng của tháng đó** (kỳ nợ = tháng của ngày chuyến), chưa có bảng thì bảng tháng đó tự hiện. Với dòng sổ gốc, phần trong bản mốc vẫn trừ ở tháng cũ, số hiện tại cộng ở tháng mới.
- **Xóa hẳn**: bấm số STT của chuyến → xác nhận "Xóa hẳn chuyến … (ngày, thành tiền)?" → dòng biến mất, Lịch sử ghi lại đủ thông tin chuyến.
- **Đổi container** của chuyến web thành container đã có trong sổ → CHỜ KIỂM, ngoài số dư (`NEWTRIP-01`).
- Hàng nháp lưu cũng vào bảng của tháng theo ngày chuyến của từng hàng, **kể cả tháng đã khóa** (vào thẳng, không cần mở khóa — `NHAP-SHEET-01` (7)).

**Nháp chưa lưu.** Chỉ sống trong tab: tải lại trang hoặc đổi khách thì hỏi "Còn n chuyến nháp chưa lưu, bỏ đi?". Không lưu nháp lên server.

## Ngoài phạm vi

- Nhập khoản thu từ bảng nhập (đã chốt chỉ nhận chuyến). Thu vẫn ghi ở ô Ngày trả / Hình thức / Số tiền trả.
- Cột booking: Sheet tab khách không có cột booking; chuyến web dùng mã thay thế theo `ALT-KEY-01`, giữ như hiện nay.
- Ctrl+Z, kéo chọn nhiều ô, kéo điền (fill handle).

## Câu hỏi còn mở

1. Tab có bố cục khác hẳn (không theo thứ tự `B..K` ở trên): đọc thử từng tab trên bản xem trước khi code; tab lệch thì cần một cách chọn bố cục hay chỉ báo lỗi?
2. Backend: cách ghi kỹ thuật điều chỉnh gắn dòng sổ gốc (bảng/sự kiện mới, gắn `legacy_row`), và phân bổ lại phiếu khi chuyến đổi tháng hoặc bị xóa — cần spec backend riêng trước khi code.

## Tiêu chí duyệt bản xem

- [ ] Copy 6 hàng từ tab khách (từ cột STT tới cột thành tiền), bấm ô bất kỳ của hàng trống, Ctrl+V: ra 6 hàng nháp đúng cột, phụ phí là tổng ba cột phí, thêm một hàng trống bên dưới.
- [ ] Copy từ cột container thay vì từ STT: kết quả như trên.
- [ ] Copy cả phần tiền khách trả: chuyến vào đúng, có dòng nhắc, không tạo khoản thu.
- [ ] Gõ tay một chuyến bằng Tab/Enter, không dùng chuột sau ô đầu.
- [ ] Ô ngày sai và ô thiếu nơi đến tô đỏ, nút Lưu tắt; sửa xong nút bật.
- [ ] Thành tiền Sheet lệch: ô vàng, không chặn Lưu.
- [ ] Lưu: hàng nháp thành chuyến đã ghi, tổng tháng đổi; chuyến trùng container với dòng sổ gốc thành CHỜ KIỂM, không cộng nợ.
- [ ] Chuyến đã lưu: bấm ô, gõ đè, Enter → lưu ngay, Lịch sử có trước → sau; Esc trả lại.
- [ ] Tháng khóa: sửa nơi đến và đơn giá dòng sổ gốc → lưu được, Lịch sử ghi điều chỉnh, dòng "Điều chỉnh do sửa/xóa dòng sổ gốc" đúng phần chênh.
- [ ] Điền giá dòng sổ gốc thiếu giá → tổng tháng tăng đúng số đó.
- [ ] Đổi ngày chuyến sang tháng khác → chuyến sang bảng tháng đó, tổng cả sổ không đổi; tháng chưa có bảng thì bảng tự hiện.
- [ ] Bấm STT → xác nhận → chuyến biến mất, tổng giảm đúng, Lịch sử ghi lại.
- [ ] 1280×720: không cuộn ngang.

## Khi code vào trang live (sau khi duyệt)

Backend cho sửa trường chữ/ngày, xóa chuyến và sửa/xóa dòng sổ gốc: [`v7-sua-xoa-chuyen.md`](v7-sua-xoa-chuyen.md).

Map thao tác → module → kiểm:

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Đọc vùng dán theo bố cục tab khách | `so-khach-v7-model.js` (hàm thay `parsePastedTrips`) | unit: 7/10/11 cột, cột nhãn đầu, phí cộng, phí trống, thành tiền lệch, hàng tổng, ngày 1 chữ số |
| Bảng nhập, bàn phím, ô lỗi | `so-khach-v7-ui.js`, `so-khach-v7-live.html` | browser (Playwright): dán, Tab/Enter, Lưu tắt/bật, 1280×720 không cuộn ngang |
| Lưu | `so-khach-v7-api.js` → `/api/v7/trips/paste` (không đổi API) | unit: một lệnh, một key; dán trùng → CHỜ KIỂM |
| Sửa ô chuyến web | đơn giá/phụ phí: `/api/v7/trips/price` và `/api/v7/trips/adjust` (đã có). Container, hãng tàu, ngày, nơi đi/đến: **cần lệnh mới** (`v7_backend_functions.sql` + `v7_ledger_api.py`), cả tháng khóa; đổi ngày khác tháng thì đổi kỳ nợ và phân bổ lại | DB test: sửa từng trường ở tháng mở và khóa, Lịch sử đúng, đổi container trùng → CHỜ KIỂM, đổi tháng giữ tổng khách |
| Xóa chuyến | **cần lệnh mới**; tháng khóa ghi điều chỉnh | DB test: xóa ở tháng mở/khóa, tổng giảm đúng, Lịch sử đủ thông tin |
| Sửa/xóa dòng sổ gốc | **cần bảng/lệnh mới** gắn `legacy_row`, không sửa `opening_balance` | DB test: phần chênh, xóa, đổi tháng; đối soát với bản mốc vẫn đọc được |
