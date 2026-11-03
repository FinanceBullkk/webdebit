# Trang khách: một khách, bốn thẻ

Trạng thái: **ĐÃ CHỐT** kiến trúc và tám lựa chọn K1–K8 (người dùng, 31/10/2026, chat: "Chốt theo đề xuất"), xem [`TRANG-KHACH-01`](../docs/decisions/trang-khach-01.md). **PR A1 (vỏ trang khách) đã code** và lên `hao` (1/11/2026, mục Bằng chứng); **PR A2 (thẻ Tình hình) đã code** và lên `hao` cùng ngày (FinanceBullkk/webdebit#236); **PR A3 (thẻ Trao đổi và Hồ sơ) đã code** và lên `hao` cùng ngày (FinanceBullkk/webdebit#237); **PR A4 (đường vào) đã code** (1/11/2026, kiểm trên máy chủ giả), nên giai đoạn A đã code xong. Người dùng yêu cầu viết spec trong chat ngày 31/10/2026, sau khi xem bản xem bấm thử. Nhu cầu gốc: sếp muốn cải thiện luồng người dùng, nhất là khi một người quản lý mở một khách thì xem được gì. Spec do Claude viết theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md). Bản xem dữ liệu giả: [`preview/mockups/trang-khach`](../cong-no-web-handoff/preview/mockups/trang-khach/index.html).

### Giao diện Tình hình theo bản HTML người dùng cấp 02/11/2026

Người dùng đưa bản xem `TinhHinh.dc.html` và yêu cầu code theo đúng thiết kế. Bố cục mới của thẻ Tình hình: thanh sổ/khách và bốn thẻ ở trên; dải **Còn nợ** + cơ cấu theo hạn trả + **Việc tiếp theo**; ba thẻ chỉ số; hình **Còn nợ 12 tháng** cạnh **Hoạt động gần đây**. Việc chờ là nút mở thẻ Sổ. Nội dung khối 5–6 của bản A2 chuyển vào việc chờ và hoạt động; thẻ Trao đổi vẫn giữ chi tiết.

- Tiền và rủi ro lấy từ API sổ/Tổng quan, hứa trả từ dấu Zalo, không dùng các số và tên giả trong bản xem. Nhãn **Doanh thu** ghi rõ bên dưới là phát sinh đã ghi sổ trong 12 tháng; không suy ra doanh thu từ chuyến chưa giá hoặc chờ kiểm. Tháng thiếu dữ liệu không biến thành 0.
- **Trễ trung bình sau hạn** hiện `—` cho tới khi B1 có API; không dựng số từ ví dụ. Khi không đọc được dấu hứa trả, Việc tiếp theo ghi chưa xác định và có Thử lại, không tự bảo nhắc ngay.
- **Vẫn nhắc nợ** dùng đúng lệnh Copy tin nhắc sẵn có ở thẻ Trao đổi. Bấm tháng mở Sổ đúng tháng, không tải lại. Không đổi đường ghi tiền, Sheet hay DB.
- **Nút của Việc tiếp theo** (sửa sau review 3/11/2026, bản đầu bị đảo): *Nhắc nợ ngay* → nút chính xanh **Copy tin nhắc nợ** + **Xem Trao đổi**; *Chờ hứa trả* → **Vẫn nhắc nợ** (nút phụ) + **Xem Trao đổi**; *Chưa cần làm gì* hoặc chưa xác định → chỉ **Xem Trao đổi**. Copy tin nhắc nợ và Vẫn nhắc nợ cùng một lệnh của thẻ Trao đổi. Tháng đang chạy dưới hình 12 tháng ghi thêm "đến dd/mm" (hôm nay, giờ VN).
- Kiểm trên máy chủ giả: số Còn nợ/cơ cấu, thiếu opening, khách trả trước, dấu hứa trả, lỗi nguồn phụ, 1280×720 và màn hẹp; ảnh chụp chỉ dùng khách và số giả. Đây là tiêu chí cho code giao diện, không là bằng chứng đã triển khai `hao`.

Thời điểm: [PLAN](../PLAN.md) đang tạm dừng tính năng mới cho tới khi chạy song song; quyết định này chốt hướng, chưa code. Thẻ Sổ chính là sổ khách của [`SO-GON-04`](../docs/decisions/so-gon-04.md) (UX đợt 2, đang làm), nên giai đoạn A chỉ bắt đầu sau PR 2c của đợt đó (cùng sửa đầu sổ).

## Vì sao cần

Trên Google Sheet, mỗi khách là một tab: mở tab là thấy hết khách, vì Sheet chỉ hiện được các dòng. Web đang chép đúng điều đó: "mở khách" là mở cuốn sổ. Hiện trạng tại `d65be02`:

1. Mọi đường vào khách đều là `so-khach-v7-live.html?customer=<id>` (ma trận, Đòi nợ, Việc cần làm, ngăn kéo Tổng quan). Sổ nợ nhiều nhất trên `hao` cao 17.734px, khoảng 25 màn hình ([audit UX](../docs/ux-audit-2026-10-31.md), P0-1).
2. Những gì cho biết khách đang thế nào nằm rải năm chỗ: mức rủi ro, lần trả và lần đi hàng gần nhất ở Tổng quan (`get_dashboard_debt`); lần nhắc ở Đòi nợ (`get_reminders`); tin nhắn ở Chat Zalo (tìm theo tên); giá ở bảng giá trong sổ; ảnh chứng từ trong từng phiếu.
3. Sổ khách không có đường ra theo khách: ngoài thanh điều hướng, từ sổ không sang được Đòi nợ, Chat Zalo hay mức rủi ro của chính khách đó (không file `so-khach-v7-*.js` nào có link tới `doi-no.html` hay `zalo-chat.html`).
4. Không chỗ nào trả lời ba câu "nợ đang tăng hay giảm", "khách trả có chậm dần không", "khách còn đi hàng không" cho một khách, dù phần lớn số đã có trong `GET /api/v7/ledger` và `GET /api/v7/dashboard/debt`.
5. Cùng chữ "1–2 tháng" nhưng khác tháng: Tổng quan nhóm theo hạn trả ([`DASH-03`](../docs/decisions/dash-03.md) (1)): ngày 31/10, "Quá hạn 1–2 tháng" là nợ T7–T8 (`tierOfMonth` trong `dashboard-v7-model.js`). Ma trận nhóm theo tuổi tháng: "1–2 tháng trước" là nợ T8–T9 (`ageOf` trong `cong-no-theo-thang.js`). Trang khách dùng nhóm hạn trả như Tổng quan; chuyện ma trận ghi ở Câu hỏi mở.

Ý chính của spec: **khách là trung tâm, sổ là một thẻ bên trong**. Trang khách gom về một chỗ những gì đã có, rồi thêm dần phần còn thiếu theo ba giai đoạn:
- **A**: chỉ dùng dữ liệu và API đã có, không đổi DB.
- **B**: thêm bảng hoặc hàm ngoài đường tiền.
- **C**: cần quyết định nghiệp vụ trước khi làm.

## Người dùng và luồng (bước 1)

Người dùng:
- **chủ nghiệp vụ / sếp**: xem một khách để quyết định thúc đòi, gọi điện hay giữ quan hệ;
- **người đòi nợ**: có thể là người nhập;
- **người nhập**: ghi phiếu, sửa giá, xử lý việc chờ.

Tất cả trên 40 tuổi, màn 1280×720 (khoảng 1280×560 nhìn thấy trong Chrome), chữ thân ≥ 16px, vùng bấm ≥ 40px ([hướng dẫn UX](../docs/ux-guidelines.md)). Đang chạy song song: Sheet là sổ chính thức ([`SONG-SONG-01`](../docs/decisions/song-song-01.md)).

### Luồng 1. Sếp xem một khách (thẻ Tình hình)

1. Ở Tổng quan, bấm tên khách: ngăn kéo mở như hiện nay ([`DASH-01`](../docs/decisions/dash-01.md)). Ngăn kéo có thêm nút **"Trang khách"** cạnh "Mở sổ", mở `?customer=<id>&the=tinh-hinh`. Hoặc gõ tên ở ô tìm khách rồi bấm thẻ Tình hình.
2. Thẻ Tình hình trả lời sáu câu, đọc từ trên xuống (bảng ở mục Kiến trúc trang).
3. Muốn xem nguồn một con số:
   - bấm một tháng trên hình 12 tháng: sang thẻ Sổ đúng tháng đó (`month=`);
   - bấm "Quá hạn": sang thẻ Sổ ở tháng nợ cũ nhất;
   - bấm một việc chờ: sang thẻ Sổ với `loc=`.
4. Muốn biết đã đòi tới đâu: sang thẻ Trao đổi.

Kết quả: khoảng 30 giây là trả lời được khách nợ bao nhiêu, quá hạn bao nhiêu, nợ đang tăng hay giảm, khách còn chạy hàng không, lần cuối nói gì; không phải cuộn sổ.

### Luồng 2. Người đòi nợ chuẩn bị nhắc (thẻ Trao đổi)

1. Ở Đòi nợ, bấm tên khách: mở `?customer=<id>&the=trao-doi`.
2. Thấy dòng thời gian của khách: phiếu thu, lần nhắc, tin Zalo. Giai đoạn B thêm debit note đã gửi và hứa trả.
3. Bấm **Copy tin nhắc** (giống Đòi nợ, tự ghi `source: copy-button`) hoặc **Mở chat** (trang Chat Zalo, đúng hội thoại).
4. Giai đoạn B2 (K4): khách hứa trả thì bấm **Ghi hứa trả** (số tiền, hẹn ngày, ghi chú).

Kết quả: lần sau ai mở khách cũng thấy đã nhắc khi nào, khách nói gì, hứa gì.

### Luồng 3. Người nhập làm việc trên sổ (thẻ Sổ)

Giữ nguyên SO-GON-04, luồng L1–L7. Trang khách chỉ đổi dòng đầu sổ thành đầu trang có thanh thẻ (mục Đầu trang). Mọi đường vào cũ (`?customer=`, `month=`, `loc=`) vẫn mở thẻ Sổ như hôm nay (K2).

### Luồng 4. Khách thắc mắc một con số

- Thẻ Tình hình: bấm tháng, sang thẻ Sổ đúng tháng để xem Tổng tháng, dòng "Theo sổ gốc", Lịch sử từng dòng, ảnh chứng từ.
- Thẻ Hồ sơ: xem giá đang áp theo ngày hiệu lực ([`BANG-GIA-01`](../docs/decisions/bang-gia-01.md)).
- Thẻ Trao đổi: xem debit note đã gửi (giai đoạn B4).

### Luồng 5. Xem hồ sơ khách (thẻ Hồ sơ)

Mặt hàng, cảng/bộ, giá đang áp, cột phụ phí riêng, ảnh chứng từ, hạn trả. Giai đoạn B3 thêm gắn hội thoại Zalo. Giai đoạn C thêm các sổ của cùng khách, hạn mức, người liên hệ.

### Bị chặn và trường hợp đặc biệt

- **Khách chưa có số dư đầu** (`status: NO_BASELINE` của `list_customers`): thẻ Tình hình hiện câu giống sổ, không hiện số ([`V7-COPY`](../docs/decisions/v7-copy.md) (1)).
- **Khách đang dư** (tổng còn nợ âm): bốn số đổi thành "Khách đang dư … (trả trước)" theo [`CAN-DU-01`](../docs/decisions/can-du-01.md); không có quá hạn.
- **Chưa có bản xuất chat trên `hao`:** khối Zalo ghi "Chưa có dữ liệu chat trên máy chủ" ([`NHAC-NO-01`](../docs/decisions/nhac-no-01.md), sửa đổi 30/10).
- **Một API phụ lỗi** (`dashboard/debt`, `reminders`, `zalo`): chỉ khối đó báo lỗi kèm nút Thử lại, theo ba mức phản hồi của audit (mục 4.6). Nếu `GET /api/v7/ledger` lỗi thì cả trang báo lỗi như sổ hiện nay.

## Kiến trúc trang

### Địa chỉ và thẻ mặc định

- Giữ địa chỉ `so-khach-v7-live.html?customer=<id>`: mọi link hiện có giữ nguyên nghĩa. Trang khách là trang sổ khách được mở rộng, không phải trang thứ hai. Như vậy vẫn chỉ một chỗ tải sổ, một hợp đồng `ctx`, một presence.
- Thêm tham số `the=tinh-hinh|so|trao-doi|ho-so`.
  - Không có `the` thì mở thẻ **Sổ** (K2).
  - Có `month=` hoặc `loc=` thì luôn mở thẻ Sổ.
- Đổi thẻ thì cập nhật địa chỉ bằng `history.replaceState`: không tải lại trang, và nút Back vẫn về trang trước chứ không lùi từng thẻ.

Đường vào:

| Từ | Bấm | Mở |
| --- | --- | --- |
| Ô tìm khách (mọi trang) | chọn khách | `?customer=` → Sổ (như nay) |
| Tổng quan | ngăn kéo → "Trang khách" (mới) | `the=tinh-hinh` |
| Tổng quan | ngăn kéo → "Mở sổ" (giữ) | Sổ |
| Công nợ theo tháng | tên khách | `the=tinh-hinh` |
| Công nợ theo tháng | ô tháng, ngăn kéo | `month=` (SO-GON-04 L1.5) |
| Đòi nợ | tên khách | `the=trao-doi` |
| Đòi nợ | số quá hạn | Sổ, tháng nợ cũ nhất (SO-GON-04 L1.5) |
| Việc cần làm | một việc | Sổ với `loc=` (như nay) |
| Chat Zalo | "Trang khách" (khi hội thoại đã gắn khách, B3) | `the=trao-doi` |

**Khi code (PR A4, 1/11/2026), Claude làm như sau** — không đổi tiền, API hay lựa chọn K1–K8:

1. **Ngăn kéo Tổng quan:** ba nút một dòng: **Mở sổ khách** (nút chính, giữ như cũ) · **Trang khách** · Xem ở ma trận.
2. **Đòi nợ:** tên khách mở thẻ Trao đổi. Trước A4, tên khách mở Sổ ở tháng nợ cũ nhất (SO-GON-04); link đó chuyển sang số quá hạn:
   - số thành link; rê chuột thấy số đồng chính xác và tháng sẽ mở;
   - vùng bấm cao 40px mà dòng không cao thêm.
3. **Không đổi:** ô tìm khách (`?customer=`), Việc cần làm (`loc=`), ô tháng và ngăn kéo ma trận (`month=`), nút Chat ở Đòi nợ.

### Đầu trang (dính, một dòng, cao ≤ 44px)

**Thay bằng chuẩn chung 3/11/2026** (canvas Claude Design, khung UuTien; phiên điều phối review thấy bốn thẻ mỗi thẻ một kiểu đầu trang): mọi thẻ dùng một thanh trắng cao 52px — **Sổ khách / Tên ▾** (bấm mở hộp đổi khách) · bốn thẻ · nút **⋯** ở phải (Lịch sử, Cài đặt, Tổng còn nợ mọi tháng). Không còn dòng mặt hàng dưới tên: mặt hàng · vận chuyển chỉ ở đầu thẻ Hồ sơ. Menu trái 76px và đầu trang giống nhau ở bốn thẻ, thẻ Tình hình không có kiểu riêng. Phần dưới đây là bản A1, giữ để biết lịch sử.

- Một dòng, từ trái sang phải:
  - **← Quay lại**, theo trang vừa đến (audit 4.1);
  - **tên khách** viết đủ, không cắt (audit P1-1); tên quá dài thì xuống dòng;
  - mặt hàng · cảng/bộ;
  - **thanh bốn thẻ**: thẻ Sổ kèm số việc chờ, cùng cách đếm với chấm cam trên chip tháng của SO-GON-04 L1.3;
  - **Tổng còn nợ**;
  - nút chính **Ghi phiếu thu** và **Thêm ▾** (SO-GON-04 L7).
- Ô tìm khách lên thanh trên cùng như mọi trang (audit 4.1) để đầu trang đủ chỗ.
- Đầu trang thay đúng dòng đầu sổ của L7, không thêm dòng. Nhờ vậy ở thẻ Sổ, phần dính (thanh trên + đầu trang + thanh tháng + tiêu đề cột) vẫn ≤ 180px như SO-GON-04.
- Bấm Ghi phiếu thu khi đang ở thẻ khác thì chuyển sang thẻ Sổ rồi mở khung bên phải (SO-GON-04 L2).

**Khi code (PR A1, 1/11/2026), Claude làm như sau** — không đổi tiền, API hay lựa chọn K1–K8:

1. **Không có "Thêm ▾":** giữ nút phụ **Lịch sử** như SO-GON-04 L7 đã chốt khi code PR 2c (bỏ menu, Cài đặt phụ phí và Bảng giá ở dải đầu thẻ Sổ). Đầu trang: ← Quay lại · tên khách · mặt hàng · bốn thẻ · Tổng còn nợ · Ghi phiếu thu · Lịch sử. Khung Lịch sử mở được ở mọi thẻ.
2. **← Quay lại** là nút Back của tab: máy chủ gửi `Referrer-Policy: no-referrer` nên trang không biết trang trước là trang nào. Tab mới mở, chưa có trang trước, thì nút ghi "← Tổng quan".
3. **Tổng còn nợ** hai dòng chữ (nhãn 14px trên, số 18px dưới; bỏ "(mọi tháng)") để cả đầu trang vừa một dòng ở 1280. Tên khách dài xuống dòng, mặt hàng chảy liền sau tên, tên trên 30 ký tự chữ nhỏ một cỡ (16px).
4. **Bàn phím** theo mẫu thanh thẻ WAI-ARIA đúng tiêu chí nghiệm thu: mũi tên trái/phải (vòng), Home/End chỉ chuyển tiêu điểm; Enter/Space mới mở thẻ. Bản xem đổi thẻ ngay khi bấm mũi tên.
5. **Đổi thẻ chỉ ẩn/hiện**: thẻ đang mở ghi ở `<body data-the>`, CSS ẩn thẻ Sổ cùng khung Ghi phiếu thu, ngăn phụ phí, khung ảnh chứng từ khi sang thẻ khác. DOM giữ nguyên nên chữ đang gõ không mất và quay lại thẻ Sổ đúng chỗ cuộn cũ. Mở khung Ghi phiếu thu bằng bất cứ đường nào (nút ở đầu trang, dán ảnh) thì sang thẻ Sổ trước.
6. **Địa chỉ:** rời thẻ Sổ thì bỏ `month=` và `loc=` (hai tham số đó luôn mở Sổ); về thẻ Sổ thì bỏ `the=`.
7. **Ba thẻ chưa có nội dung** (Tình hình, Trao đổi, Hồ sơ) tới PR A2, A3 hiện một câu thẻ sẽ trả lời gì và nút "Mở thẻ Sổ".

### Bốn thẻ, mỗi thẻ một mục tiêu

Theo tinh thần [`DASH-03`](../docs/decisions/dash-03.md): mỗi tab một mục tiêu.

| Thẻ | Câu hỏi | Ai dùng nhiều | Ghi tiền? |
| --- | --- | --- | --- |
| Tình hình | Khách này đang thế nào | sếp, người đòi nợ | không, chỉ đọc |
| Sổ | Từng dòng chuyến, phiếu, giá | người nhập | có, như SO-GON-04 |
| Trao đổi | Đã nói gì, hứa gì, gửi gì | người đòi nợ | không ghi tiền; B2 ghi hứa trả, ngoài đường tiền |
| Hồ sơ | Khách là ai, giá nào, điều khoản | mọi người | không; B3/C gắn Zalo, liên hệ |

### Thẻ Tình hình

Đọc từ trên xuống. Trình bày theo [`DASH-04`](../docs/decisions/dash-04.md): mỗi câu hỏi một hình, số nằm trong hình, không câu kết luận. Màu theo [DESIGN](../cong-no-web-handoff/preview/mockups/DESIGN.md): xám + một navy, đỏ chỉ cho nợ quá hạn hoặc chưa trả.

| # | Tiêu đề khối (câu hỏi) | Hiện gì | Giai đoạn |
| --- | --- | --- | --- |
| 1 | Khách đang nợ mình bao nhiêu | Bốn số: Còn nợ · Quá hạn (các tháng, lâu nhất N ngày) · Đến hạn cuối tháng này · Thu tháng này trên phát sinh tháng này. Nhãn mức rủi ro kèm dữ kiện tạo ra nhãn ("trả gần nhất 15/10", "đi hàng gần nhất 29/10") | A |
| 2 | Nợ đang tăng hay giảm? | 12 tháng gần nhất: cột kép phát sinh (xám) và đã thu (navy), đường Còn nợ cuối tháng; ghi số ở điểm thấp nhất và điểm cuối. Bấm một tháng thì sang Sổ tháng đó | A |
| 3 | Khách trả có chậm dần không? | Số ngày trả sau hạn của từng tháng nợ trong 12 tháng. Tháng chưa trả đủ ghi "N+ · chưa trả" (đỏ) | B1 |
| 4 | Khách còn đi hàng không? | Số chuyến mỗi tháng trong 6 tháng, lần đi hàng gần nhất | A |
| 5 | Còn gì làm số chưa đúng? | Chuyến chưa có giá, chờ kiểm, chuyến/giá/phiếu thu từ Sheet đang chờ, phụ phí PS cần xem. Mỗi dòng mở Sổ đúng chỗ. Kèm câu "Còn nợ ở trên chưa tính các dòng này" | A |
| 6 | Lần cuối nói chuyện với khách | Lần nhắc gần nhất (ngày, cách nhắc), tin Zalo gần nhất; B2 thêm hứa trả đang chờ. Link sang thẻ Trao đổi | A một phần, B |

**Khi code (PR A2, 1/11/2026), Claude làm như sau** — không đổi tiền, API hay lựa chọn K1–K8:

1. **Đọc API phụ khi cần:** `dashboard/debt` và `reminders` chỉ đọc khi thẻ Tình hình đang mở (lần đầu mở, khi sổ đổi phiên bản, hoặc lần đọc đã quá 60 giây). Người chỉ dùng thẻ Sổ không gọi thêm API nào.
2. **Khối 1:** Còn nợ và Thu tháng này lấy ở sổ; Quá hạn, Đến hạn và mức rủi ro lấy dòng của khách ở Tổng quan. Ô Đến hạn ghi ngày như Tổng quan ("Đến hạn 30/11"), dòng dưới ghi tháng nợ và khoản kế tiếp. Bấm dòng tháng quá hạn thì sang thẻ Sổ ở tháng quá hạn lâu nhất. Dữ kiện của mức rủi ro: lần trả và lần đi hàng gần nhất, cùng chữ với ngăn kéo Tổng quan. Sổ không có dòng ở Tổng quan (không nợ) thì Quá hạn 0 đ.
3. **Thu tháng này khi tháng hiện tại chưa có dòng nào:** 0 đ, như dòng Tổng tháng của tháng đang làm ở thẻ Sổ, kèm câu "chưa có chuyến hay phiếu thu".
4. **Khối 2:** không vẽ trục số; số ghi ở điểm thấp nhất và điểm cuối, rê chuột xem số từng cột. Tháng có dòng bấm được ở cả cột trên hình và hàng tên tháng bên dưới (nút 40px, Tab tới được). Bấm thì sang thẻ Sổ, ghi `month=` lên địa chỉ và hiện chi tiết tháng đó, không tải lại trang.
5. **Khối 4:** đếm dòng chuyến web (trừ đã xóa, đã loại, phí lẻ) và dòng chuyến sổ gốc chưa xóa. Lần đi hàng gần nhất lấy ở Tổng quan; sổ không có ở Tổng quan thì lấy ngày chuyến mới nhất trong sổ.
6. **Khối 5:** chuyến chưa có giá, chờ kiểm và chuyến từ Sheet đếm như chấm cam trên chip tháng. Hai dòng đầu mở thẻ Sổ với `loc=` ngay trong trang (`showLoc` của `so-khach-v7-loc-ui.js`). Dòng Sheet, giá và phiếu thu từ Sheet, phụ phí PS tới nút của lô ở dải đầu thẻ Sổ. Câu "Còn nợ ở trên chưa tính các dòng này" không kể phụ phí PS, vì tách theo PS không đổi tổng tiền.
7. **Khối 6 phần A:** chỉ có lần nhắc gần nhất (ngày, cách nhắc, số lần) và nút sang thẻ Trao đổi. Tin Zalo gần nhất để PR A3, cùng chỗ tìm hội thoại theo tên của thẻ Trao đổi.
8. **Trường hợp đặc biệt:** khách dư có hai ô, "Khách đang dư … trả trước" và Thu tháng này. Khách chưa có số dư đầu: một câu như sổ, không đọc Tổng quan.

### Thẻ Sổ

Giữ nguyên SO-GON-04 (L1–L7, H1–H6):
- một tháng đang làm, có thanh tháng;
- một khung Ghi phiếu thu, bước xem lại chỉ hiện tổng còn nợ trước → sau (H5: **không** hiện phân bổ từng tháng trước khi ghi);
- Lịch sử viết thành câu.

Trang khách không thêm gì vào bên trong thẻ Sổ.

### Thẻ Trao đổi

Dòng thời gian của một khách, mới nhất ở trên. Lọc theo loại: Tất cả · Hứa trả · Nhắc và Zalo · Thu tiền · Debit note. Nút: **Copy tin nhắc** (như Đòi nợ), **Mở chat**, và **Ghi hứa trả** (B2).

| Loại mục | Nguồn | Giai đoạn |
| --- | --- | --- |
| Thu tiền, cấn trừ (ngày, số tiền, trừ nợ tháng nào) | `receipts[]` và `allocations[]` của `GET /api/v7/ledger` | A |
| Lần nhắc gần nhất, số lần nhắc | `GET /api/v7/reminders` | A |
| Từng lần nhắc, có ghi chú ngắn | `reminder_log` thêm cột ghi chú, hàm đọc theo khách | B4 |
| Tin Zalo | bản xuất chat; A tìm hội thoại theo tên như nút Chat ở Đòi nợ; B3 theo hội thoại đã gắn | A, B3 |
| Debit note đã xuất | bảng ghi mới, ghi khi bấm xuất | B4 |
| Hứa trả | bảng mới | B2 (K4) |

**Hứa trả** (K4):
- Người dùng ghi tay số tiền (VND nguyên), hẹn ngày và ghi chú.
- Máy tự chấm theo phiếu thu chưa hủy, tính từ ngày ghi tới ngày hẹn:
  - đủ số hứa thì là **giữ lời**;
  - tới hẹn mà chưa đủ thì là **lỡ hẹn**, kèm số đã trả;
  - chưa tới hẹn thì là **đang chờ**.
- Hứa trả không cộng vào số nào, không đổi phân bổ, không khóa tháng. Nó là ghi chú ngoài đường tiền, giống `reminder_log`.
- Hứa trả khác "dự báo tiền về" mà NHAC-NO-01 v1 đã bỏ: không đọc nội dung tin, không dự báo, chỉ ghi lại điều khách đã nói.

### Thẻ Hồ sơ

| Khối | Nguồn | Giai đoạn |
| --- | --- | --- |
| Mặt hàng, cảng/bộ | `list_customers` (`commodity`, `transport_mode`) | A |
| Giá đang áp theo ngày hiệu lực | `GET /api/v7/price-table` (BANG-GIA-01) | A |
| Cột phụ phí riêng của sổ | `GET /api/v7/books/fee-columns` | A |
| Ảnh chứng từ | `receipts[]` và ảnh của phiếu ([`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md)) | A |
| Hạn trả | quy tắc chung DASH-03 (1), `rule.due_after_months` của `dashboard/debt` | A |
| Hội thoại Zalo đã gắn | bảng gắn mới | B3 (K6) |
| Các sổ của cùng khách | khóa nhóm sổ mới | C (K1) |
| Hạn mức nợ, hạn trả riêng | mới | C |
| Người liên hệ, ghi chú nội bộ | mới; dữ liệu cá nhân, chỉ nằm trong DB trên `hao` | C |

**Khi code (PR A3, 1/11/2026), Claude làm như sau** — không đổi tiền, API, DB hay lựa chọn K1–K8:

1. **Dòng thời gian của thẻ Trao đổi:** phiếu thu và cấn trừ vào sổ (`receipts[]`), khoản cấn trừ sang sổ khác (`outgoing_offsets[]`), lần nhắc gần nhất, hội thoại Zalo; xếp theo ngày, mới nhất ở trên. Khoản thu sổ gốc (trước khi lên web) không vào dòng thời gian; một câu dưới danh sách chỉ sang thẻ Sổ.
2. **Phiếu thu:** số tiền nguyên của phiếu. Tháng trừ nợ lấy dòng phân bổ có `superseded_by_event` trống; một tháng thì chỉ ghi tháng, như danh sách phiếu ở thẻ Sổ; dòng `kind = advance` ghi "ứng trước". Phiếu hủy gạch số tiền, ghi ngày hủy và lý do. Phiếu có ảnh có nút 📎: bấm thì sang thẻ Sổ, khung xem ảnh mở ở đó. Xem và đính ảnh vẫn chỉ ở thẻ Sổ.
3. **Zalo phần A:** tìm hội thoại theo tên Sheet của sổ (`display_name`, rồi `name`), như nút Chat ở Đòi nợ.
   - Mỗi hội thoại khớp là một mục ở ngày tin cuối (giờ VN), kèm số tin, lần mình nhắn gần nhất và link mở đúng hội thoại. Tối đa ba hội thoại; nhiều hơn thì bấm Mở chat.
   - Không hiện nội dung tin: đọc tin ở trang Chat Zalo.
   - Máy chủ chưa có bản xuất chat thì một câu "Chưa có dữ liệu chat trên máy chủ", không báo lỗi.
   - Khối 6 của thẻ Tình hình thêm "Zalo gần nhất dd/mm/yyyy · tên hội thoại", phần A2 để lại.
4. **Copy tin nhắc:**
   - Tin soạn bằng cùng một hàm với Đòi nợ (`CongNoFormat.reminderText`), từ dòng của khách ở Tổng quan. Dòng đó đọc lại ngay lúc bấm để số gửi khách là số mới nhất.
   - "Kính gửi" dùng tên Sheet, không kèm "· sổ N" như Đòi nợ khi hai sổ trùng tên.
   - Ghi "đã nhắc" bằng đúng lệnh của Đòi nợ (`POST /api/v7/reminders`, `source: copy-button`), rồi đọc lại lần nhắc từ server, không tự cộng số lần.
   - Khách không còn nợ thì không có tin. Không chép được vào bộ nhớ tạm thì tin hiện trong ô để copy tay.
5. **Thẻ Hồ sơ:**
   - Giá đang áp là các dòng "Đang dùng" của khung Bảng giá: Từ ngày ≤ hôm nay (giờ VN) ≤ Đến ngày, Đến ngày trống là chưa hết hạn; cùng thứ tự. Kèm shipper áp giá TT và ngày có giá mới.
   - Nút Mở Bảng giá và Cài đặt phụ phí sang thẻ Sổ rồi mở khung đó: sửa vẫn ở thẻ Sổ.
   - Hạn trả ghi quy tắc chung, kèm ví dụ bằng tháng hiện tại.
   - Ảnh chứng từ: các phiếu có ảnh, mới nhất trước.
6. **Đọc API phụ khi cần**, như thẻ Tình hình:
   - Thẻ Trao đổi đọc `reminders` và `zalo/conversations`; thẻ Hồ sơ đọc `dashboard/debt` (quy tắc hạn trả) và `price-table`. Chỉ đọc khi thẻ đang mở.
   - Copy tin nhắc đọc `dashboard/debt` lúc bấm.
   - Hai thẻ chỉ dựng nội dung khi đang mở: dòng thời gian dài không dựng lại mỗi lần sổ vẽ lại.
7. **Lọc:** Tất cả · Nhắc và Zalo · Thu tiền, kèm số mục. Hứa trả và Debit note chờ giai đoạn B.

## Đầu ra

**Giai đoạn A**, trên máy chủ giả rồi trên `hao`:
- Mở `?customer=<id>&the=tinh-hinh` thấy các khối 1, 2, 4, 5 và phần A của khối 6. Mọi số khớp với Sổ và Tổng quan.
- Thẻ Trao đổi có phiếu thu, lần nhắc gần nhất, Copy tin nhắc, Chat tìm theo tên.
- Thẻ Hồ sơ có mặt hàng, giá, cột phụ phí, ảnh chứng từ, hạn trả.
- Mọi link cũ vẫn mở thẻ Sổ như trước.
- Tổng quan, ma trận và Đòi nợ có đường vào đúng thẻ.

**Giai đoạn B và C**: theo từng spec backend riêng của mỗi mục.

## Đối chiếu dữ liệu và code hiện có (bước 2)

Đối chiếu tại `d65be02`. Trang khách không tự tính tiền. Mọi số tiền lấy nguyên từ GET; model chỉ cộng và định dạng (ARCH-03), như sổ khách.

| Cần trên màn hình | Lấy từ | Đã có | Ghi chú |
| --- | --- | --- | --- |
| Còn nợ | `GET /api/v7/ledger` → `total_outstanding_vnd` | có | Cùng số ở đầu sổ |
| Quá hạn, tháng nợ cũ nhất, mức rủi ro, lần trả và lần đi hàng gần nhất | `GET /api/v7/dashboard/debt` → dòng của khách trong `customers[]`: `overdue_vnd`, `oldest_open_month`, `risk`, `last_receipt_date`/`last_receipt_exact`, `last_trip_date`/`last_trip_exact`, `no_pay_days`, `no_trip_days`, `tiers_vnd` | có | `get_dashboard_debt` (migration `2026-10-29-v7-tong-quan-quan-ly-no.sql`) trả mọi sổ. Giai đoạn A lọc ở trình duyệt; nếu chậm thì thêm tham số `customer` (chỉ đọc, không đổi số) |
| Đến hạn cuối tháng này | nhóm `due_this_month` trong `tiers_vnd` | có | Hạn của nợ tháng M là cuối tháng M + `due_after_months` (DASH-03 (1)). Không còn khoản đến hạn thì hiện khoản kế tiếp (nhóm `not_due`, hạn cuối tháng sau) |
| Thu tháng này và phát sinh | phần tử `months[]` của tháng `today_month`: `received_vnd`, `charges_vnd` | có | Đúng dòng Tổng tháng ([`DA-THU-01`](../docs/decisions/da-thu-01.md)) |
| Nợ 12 tháng | `months[].charges_vnd`, `months[].received_vnd`, `months[].end_of_month_vnd` | có | Tháng trước mốc dùng số Sheet trong mốc (`cutover_month_check`), cùng nguồn với dòng "Theo sổ gốc" (V7-COPY). Tháng không có trong `months[]` không vẽ cột (không phải 0); đường giữ Còn nợ cuối tháng của tháng trước đó |
| Đi hàng | đếm `trips[]` (trừ `status = 'rejected'`) và dòng chuyến `legacy_rows[]` theo tháng; lần gần nhất là `last_trip_date` | có | Đếm, không phải tiền. Chuyến chưa có giá và chuyến chờ kiểm vẫn là chuyến đã chạy |
| Còn gì làm số chưa đúng | `trips[].is_missing_price`, `trips[].status = 'pending_review'`, `sheet_sync`, `sheet_prices`, `sheet_receipts`, `ps_fees` của `GET /api/v7/ledger` | có | Cùng điều kiện với chip tháng (SO-GON-04 L1.3) và `?loc=` |
| Lần nhắc gần nhất | `GET /api/v7/reminders`: `last_reminded`, `reminder_count`, `last_source` | có | Chỉ có lần gần nhất. Danh sách từng lần cần hàm đọc mới (B4) |
| Tin Zalo | `GET /api/v7/zalo/conversations?q=<tên>`, `GET /api/v7/zalo/messages` | có, chưa gắn khách | Như nút Chat ở Đòi nợ (tìm theo tên). Bản xuất là bản chụp tĩnh và chưa có trên `hao` |
| Phiếu thu và phân bổ | `receipts[]`, `allocations[]`; dòng phân bổ hiện hành là dòng có `superseded_by_event` trống | có | |
| Ảnh chứng từ | ảnh của phiếu (`/api/v7/receipt-images`) | có | |
| Giá đang áp | `GET /api/v7/price-table` | có | Bảng giá theo sổ (`price_period.customer_id`) |
| Cột phụ phí riêng | `GET /api/v7/books/fee-columns` | có | |
| Mặt hàng, cảng/bộ, chưa có số dư đầu | `list_customers`: `commodity`, `transport_mode`, `status` | có | |
| Trả sau hạn theo tháng nợ | — | **không** | Cần hàm đọc mới (B1), quy tắc đề xuất ngay dưới bảng |
| Hứa trả | — | **không** | Bảng mới (B2, K4) |
| Gắn hội thoại Zalo với khách | — | **không** | Bảng mới (B3, K6). Kiến trúc gốc của NHAC-NO-01, phần (B) "map group ↔ khách", chưa từng làm |
| Debit note đã xuất | — | **không** | Debit note xuất ngay ở trình duyệt, không gọi API (`so-khach-v7-debit-ui.js`). Cần ghi lại khi bấm xuất (B4, K7) |
| Các sổ của cùng khách | — | **không** | `sokhach.customer` là một sổ. Hàm `list_offset_sources` ghi rõ chưa có khóa nhóm (`tools/v7_backend_functions.sql`) (C, K1) |
| Hạn mức, hạn trả riêng, người liên hệ | — | **không** | DASH-03 ghi "không có dữ liệu, để sau" (C) |

**Quy tắc đề xuất cho "trả sau hạn" (B1).** Với mỗi tháng nợ M của sổ trong 12 tháng gần nhất:

- Hạn của M là cuối tháng M + `due_after_months` (DASH-03 (1)).
- Nếu M còn nợ (`months[].outstanding_vnd` > 0, đã áp CAN-DU-01): ghi là **chưa trả**, số ngày = hôm nay (giờ VN) − hạn. Chưa tới hạn thì không hiện.
- Nếu M hết nợ và có dòng phân bổ hiện hành vào M (phiếu chưa hủy, mọi hình thức kể cả cấn trừ, như DASH-03 (3)): ngày trả xong là ngày lớn nhất của các phiếu đó. Số ngày = ngày trả xong − hạn; số âm ghi "đúng hạn".
- Nếu M hết nợ mà không có dòng phân bổ nào (trả xong trước mốc nạp, hoặc về 0 nhờ khoản dư theo CAN-DU-01, hoặc nhờ điều chỉnh): **không đo**. Hình ghi "trả trước mốc", không bịa ngày.

Hệ quả: ngay khi bắt đầu, hình chỉ có tháng còn nợ và tháng trả xong sau mốc; các tháng khác dần có số theo thời gian. Ca biên cần test ở spec backend: phiếu bị hủy rồi phân bổ lại, một phiếu trả nhiều tháng, cấn trừ hai sổ, tháng khóa có dòng điều chỉnh.

Dữ liệu cho test: máy chủ giả `so-khach-v7-browser-world.js`. Thêm `GET /api/v7/dashboard/debt` và `GET /api/v7/reminders` cho các sổ giả nếu chưa có. Cần một sổ giả trên 12 tháng có tháng chưa có giá, chờ kiểm, khách dư, và một sổ chưa có số dư đầu. Dữ liệu đều bịa, không chép số khách thật.

## Giao tiếp frontend–backend (bước 5)

**Giai đoạn A:** không thêm API, không đổi DB. Đọc bằng các lệnh đang có:
- `GET /api/v7/ledger`
- `GET /api/v7/dashboard/debt`
- `GET /api/v7/reminders`
- `GET /api/v7/price-table`
- `GET /api/v7/books/fee-columns`
- ảnh chứng từ
- `GET /api/v7/zalo/*`

Copy tin nhắc gọi đúng lệnh ghi `reminder_log` mà Đòi nợ đang dùng. Quyền như hiện nay ([`V7-ID`](../docs/decisions/v7-id.md): ai vào app cũng thao tác như nhau, actor lấy từ phiên).

**Giai đoạn B** (K4–K7 đã chốt): hợp đồng đề xuất; mỗi mục viết chi tiết thành spec backend riêng trước khi làm.

| Mục | API đề xuất | DB đề xuất |
| --- | --- | --- |
| B1 Trả sau hạn | `GET /api/v7/customer/lateness?customer=<id>` → `{as_of, due_after_months, months: [{month, due_on, paid_off_on, days_late, open}]}` | hàm đọc `sokhach.get_payment_lateness(customer_id)` |
| B2 Hứa trả | `POST /api/v7/promises` `{customer_id, amount_vnd, due_on, note}`; `POST /api/v7/promises/cancel` `{id, reason}` (lý do bắt buộc) | bảng `sokhach.promise_to_pay`; trạng thái tính khi đọc, không lưu |
| B3 Gắn Zalo | `POST /api/v7/zalo/link` `{customer_id, conversation_id}` và bỏ gắn | bảng gắn một hội thoại với một sổ, đổi có vết |
| B4 Debit note, nhắc | `POST /api/v7/debit-notes/log` `{customer_id, month, number, total_vnd}`, gọi khi bấm xuất; thêm ghi chú cho lần nhắc | bảng ghi debit note; cột ghi chú ở `reminder_log`; hàm đọc dòng thời gian theo khách |

Mọi bảng của giai đoạn B nằm ngoài đường tiền: không vào `v_outstanding_month`, không đổi phân bổ, không khóa tháng. Mỗi bảng có actor lấy từ phiên và có vết; lệnh ghi theo cách các lệnh hiện có (`idempotency_key`). Triển khai theo runbook [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md): backup trước, chạy kiểm sau triển khai, đối soát tổng khách không đổi.

**Giai đoạn C:** cần quyết định nghiệp vụ và dữ liệu trước (K1); spec này không thiết kế.

## Nguồn quyết định

- Nền đã chốt:
  - [`SO-GON-04`](../docs/decisions/so-gon-04.md): thẻ Sổ, đầu sổ L7, H5.
  - [`DASH-01`](../docs/decisions/dash-01.md), [`DASH-03`](../docs/decisions/dash-03.md), [`DASH-04`](../docs/decisions/dash-04.md): ngăn kéo, hạn trả, mức rủi ro, trình bày.
  - [`DA-THU-01`](../docs/decisions/da-thu-01.md), [`CAN-DU-01`](../docs/decisions/can-du-01.md), [`V7-COPY`](../docs/decisions/v7-copy.md), [`V7-BE`](../docs/decisions/v7-be.md): cách tính số tháng.
  - [`NHAC-NO-01`](../docs/decisions/nhac-no-01.md): Đòi nợ, Copy tin nhắc, Chat Zalo từ bản xuất.
  - [`CHUNG-TU-01`](../docs/decisions/chung-tu-01.md), [`BANG-GIA-01`](../docs/decisions/bang-gia-01.md), [`DEBIT-NOTE-02`](../docs/decisions/debit-note-02.md).
  - [`V7-ID`](../docs/decisions/v7-id.md), [`V7-SO`](../docs/decisions/v7-so.md).
- Đề xuất: [audit UX 31/10/2026](../docs/ux-audit-2026-10-31.md), mục 4.1 (điều hướng, ô tìm toàn cục, link mang tháng), P1-1 (không cắt tên), 4.6 (phản hồi và lỗi).
- Đã chốt cho spec này: [`TRANG-KHACH-01`](../docs/decisions/trang-khach-01.md) (kiến trúc và K1–K8).

## Hành vi và bất biến

- Trang khách không tạo số tiền mới.
  - Mọi số trên Tình hình phải bằng số cùng loại ở Sổ hoặc Tổng quan: Còn nợ = đầu sổ, Quá hạn = Tổng quan, Thu tháng này = Tổng tháng.
  - Test so số, không so ảnh.
- Thẻ Tình hình, Trao đổi, Hồ sơ không có lệnh ghi tiền. Ghi tiền chỉ ở thẻ Sổ, qua đúng các lệnh của SO-GON-04.
- NULL khác 0:
  - tháng không có dòng thì không vẽ cột;
  - chuyến chưa có giá không cộng vào phát sinh, và khối 5 ghi rõ "chưa tính";
  - chuyến chờ kiểm nằm ngoài số dư.
- Hứa trả, ghi lần nhắc, gắn Zalo, ghi debit note: ngoài đường tiền. Không có VND nào đi vào số dư.
- Dữ liệu chat và liên hệ không vào repo hay log. Bản xem chỉ dùng dữ liệu giả.
- Thẻ Sổ giữ mọi tiêu chí của SO-GON-04. Phần dính ở thẻ Sổ không vượt 180px.
- Đổi thẻ khi đang có phần mở dở ở thẻ Sổ (ô sửa, khung ghi phiếu có số, nháp ảnh): không mất số đã gõ. Hoặc giữ nguyên DOM của thẻ Sổ khi ẩn, hoặc hỏi lại, theo `ctx.busyChecks`.
- "Hôm nay" và hạn trả tính theo giờ VN.
- Không thêm thư viện, framework hay bước build. Hình vẽ bằng SVG/CSS như trang Tổng quan.

## Chia PR

Giai đoạn A gồm bốn PR, mỗi PR chỉ đổi file giao diện và tự xanh `npm run check`. Bắt đầu sau PR 2c của SO-GON-04, vì A1 sửa cùng đầu sổ.

| PR | Nội dung | File chính | Ngân sách |
| --- | --- | --- | --- |
| **A1 · Vỏ trang khách** | Đầu trang một dòng có thanh thẻ, tham số `the=`, thẻ Sổ là sổ hiện có | `so-khach-v7-live.html`, `so-khach-v7-ui.js` (`renderShell`), file mới `so-khach-v7-tabs-ui.js`, `so-khach-v7-ctx.js`, `so-khach-v7.css` | 300 dòng |
| **A2 · Thẻ Tình hình** | Khối 1, 2, 4, 5, phần A của khối 6 | file mới `so-khach-v7-overview-ui.js`; phép cộng chuỗi tháng trong `so-khach-v7-model.js` (có test); đọc `dashboard/debt` và `reminders` ở `so-khach-v7-api.js` | 450 dòng |
| **A3 · Trao đổi và Hồ sơ** | Phần A của hai thẻ | file mới `so-khach-v7-contact-ui.js`, dùng lại Copy tin nhắc từ `doi-no.js` | 350 dòng |
| **A4 · Đường vào** | "Trang khách" trong ngăn kéo Tổng quan; tên khách ở ma trận và Đòi nợ | `dashboard-v7.js`, `cong-no-theo-thang.js`, `doi-no.js` | 80 dòng |

Giai đoạn B: mỗi mục B1–B4 một spec backend, một migration và một PR giao diện; thứ tự làm do người dùng chọn khi tới giai đoạn B. Giai đoạn C chờ dữ liệu gán sổ vào khách (K1).

## Tiêu chí nghiệm thu

PR A1 (đã kiểm trên máy chủ giả, mục Bằng chứng):
- [x] Mọi địa chỉ cũ (`?customer=`, `&month=`, `&loc=`) mở thẻ Sổ y như trước: mọi số tiền trong `#app` bằng nhau giữa bản `main` và bản PR.
- [x] `the=tinh-hinh|so|trao-doi|ho-so` mở đúng thẻ. Bấm thẻ thì địa chỉ đổi mà không tải lại trang; Back về trang trước.
- [x] Thẻ Sổ ở 1280×720: phần dính ≤ 180px, không cuộn ngang. Tên khách dài nhất của sổ giả không bị cắt.
- [x] Bàn phím: Tab tới thanh thẻ, mũi tên trái/phải đổi thẻ, Enter mở; vùng bấm ≥ 40px.
- [x] Đang gõ dở trong khung Ghi phiếu thu mà bấm sang thẻ khác rồi quay lại: số đã gõ còn nguyên.

PR A2 (đã kiểm trên máy chủ giả, mục Bằng chứng):
- [x] Bốn số bằng đúng: Còn nợ = `total_outstanding_vnd`; Quá hạn = `overdue_vnd` của khách; Thu tháng này = `received_vnd` của `today_month`.
- [x] Hình 12 tháng: mỗi cột và mỗi điểm bằng `charges_vnd`, `received_vnd`, `end_of_month_vnd` của tháng đó. Tháng không có trong `months[]` không có cột. Bấm cột thì sang thẻ Sổ với `month=` đúng.
- [x] Đi hàng: số chuyến tháng bằng số dòng chuyến web và sổ gốc của tháng; chuyến đã loại không đếm.
- [x] Còn gì làm số chưa đúng: mỗi dòng mở Sổ với `loc` đúng; số đếm khớp chip tháng của SO-GON-04.
- [x] Khách chưa có số dư đầu thì hiện câu thay số; khách dư thì hiện "Khách đang dư …", không hiện quá hạn.
- [x] `dashboard/debt` lỗi (`page.route` abort): khối 1 hiện Còn nợ từ ledger, phần quá hạn báo lỗi kèm Thử lại; các khối khác vẫn hiện.

PR A3 (đã kiểm trên máy chủ giả, mục Bằng chứng):
- [x] Trao đổi: phiếu thu (kể cả cấn trừ) đúng ngày, số tiền, tháng trừ nợ theo `allocations` hiện hành; phiếu hủy hiện gạch, có lý do.
- [x] Copy tin nhắc ghi đúng một dòng `reminder_log` như ở Đòi nợ. Bấm lặp trong một ngày không tạo dòng mới (`UNIQUE` theo ngày).
- [x] Hồ sơ: giá đang áp bằng bảng giá trong sổ ở ngày hôm nay; cột phụ phí riêng đúng cài đặt của sổ.

PR A4 (đã kiểm trên máy chủ giả, mục Bằng chứng):
- [x] Ngăn kéo Tổng quan có "Trang khách" mở `the=tinh-hinh`; tên khách ở ma trận mở `the=tinh-hinh`; tên khách ở Đòi nợ mở `the=trao-doi`. Các link khác giữ như cũ.

Chung (bước 7–8):
- [x] `npm run check` xanh ở từng PR; `test-so-khach-v7-ctx.js` xanh.
- [ ] Sếp hoặc chủ nghiệp vụ tự đi luồng 1 trên `hao` với một khách thật và xác nhận đọc đúng; người đòi nợ đi luồng 2 một lần.

## Hoàn tác

Mỗi PR của giai đoạn A revert riêng được, vì chỉ đổi file giao diện. Triển khai tự động khi merge; rollback bằng revert PR rồi để `Deploy hao` chạy lại. Không đụng dữ liệu. Giai đoạn B: migration chỉ thêm bảng và hàm ngoài đường tiền; rollback theo runbook trong spec backend của từng mục.

## Bằng chứng

Spec: hiện trạng đối chiếu trên mã tại `d65be02`. Bản xem chỉ dùng dữ liệu giả, không gọi API; đã chạy Playwright ở 1280×720, đạt 25/25 kiểm (ghi trong [PR FinanceBullkk/webdebit#229](https://github.com/FinanceBullkk/webdebit/pull/229)).

**PR A1 (vỏ trang khách), 1/11/2026** — máy chủ giả, 1280×720, dữ liệu giả; chưa đo trên `hao`:
- `test-so-khach-v7-tabs-browser.js`, 8 test:
  1. `the=` và K2 qua tám địa chỉ, kể cả `the=` đi cùng `month=`/`loc=` và thẻ lạ.
  2. Bấm thẻ: địa chỉ đổi, trang không tải lại, không đọc lại sổ, `history.length` không đổi; Back và "← Quay lại" về trang trước.
  3. Bàn phím: Tab, mũi tên vòng, Home/End, Enter/Space; mọi nút ở đầu trang ≥ 40px.
  4. Đầu trang 44px; tên khách giả 43 ký tự cùng mặt hàng nằm gọn trong đầu trang; phần dính 176px, thanh tháng dính ở 100px; không cuộn ngang.
  5. Khung Ghi phiếu thu đang gõ dở ẩn khi sang thẻ khác, quay lại còn nguyên số; bấm Ghi phiếu thu ở thẻ khác thì mở thẻ Sổ.
  6. Sổ tự cập nhật lúc đang ở thẻ khác: quay lại thẻ Sổ đúng chỗ cuộn, danh sách phiếu dính và chip tháng đo lại đúng. Đã thử ngược: bỏ bước đo lại thì test đỏ.
  7. Ô tìm khách ở thanh trên: gõ thì hiện danh sách, rời ô thì đóng, không tràn mép; sổ đọc lỗi vẫn tìm được khách.
  8. Số việc chờ trên thẻ Sổ bằng tổng chấm cam trên các chip tháng.
- Sửa test cũ theo đầu trang mới: `test-so-khach-v7-api.js` (khuôn đầu trang), `test-so-khach-v7-chu-browser.js` (nút ngoài thanh thẻ), `test-so-khach-v7-month-browser.js` (thanh tháng dính ở 100px thay 104px).
- So mọi ô số tiền của `#app` giữa `main` (`5cf0ac0`) và bản PR, mở hết tháng, trên hai sổ giả: 608 ô (31 + 577) trùng khớp.
- `npm run check` xanh (ruff chạy bằng venv của checkout chính).

**PR A2 (thẻ Tình hình), 1/11/2026** — máy chủ giả, 1280×720, dữ liệu giả, đồng hồ trang ghim 15/11/2026 (giờ VN); chưa đo trên `hao`:
- `monthSeries` và `creditOf` trong `so-khach-v7-model.js`, hai test model: tháng thiếu không có cột, điểm còn nợ giữ tháng trước (kể cả tháng trước cửa sổ), sổ dư đặt số 0 giữa thang, chưa có tháng nào thì không có điểm, qua năm, số sai báo lỗi.
- `test-so-khach-v7-overview-browser.js`, 6 test trên sổ giả 16 tháng (thiếu tháng 5, có chuyến thiếu giá, chờ kiểm, đã loại, phí lẻ, chuyến và giá từ Sheet):
  1. Bốn số bằng `total_outstanding_vnd`, `overdue_vnd`, `tiers_vnd`, `received_vnd` của `today_month`; mức rủi ro và dữ kiện; lần nhắc; không cuộn ngang, mọi nút ≥ 40px, chữ thân 16px; bấm dòng quá hạn sang Sổ tháng quá hạn lâu nhất.
  2. Mỗi cột, mỗi điểm bằng số của tháng; tháng 5 không có cột; số ở điểm thấp nhất và điểm cuối; bấm tên tháng và bấm cột trên hình sang thẻ Sổ với `month=`, không đọc lại sổ.
  3. Số chuyến 6 tháng bằng số chuyến của tháng thu gọn ở thẻ Sổ và số dòng chuyến tính được của tháng đang mở; mở thẻ Sổ trước thì chưa đọc `dashboard/debt` hay `reminders`.
  4. Việc chờ khớp chấm cam và số trên thẻ Sổ; dòng thiếu giá, chờ kiểm mở Sổ với `loc=` (dòng được tô); dòng Sheet, giá Sheet tới đúng nút; không gửi lệnh nào.
  5. Khách chưa có số dư đầu: một câu, không đọc Tổng quan; khách dư: "Khách đang dư", không có chữ quá hạn.
  6. `dashboard/debt` cắt một lần (`page.route` abort `times: 1`): Còn nợ và Thu tháng này vẫn hiện, quá hạn báo lỗi kèm Thử lại, các khối khác còn; Thử lại thì có số. `reminders` cắt một lần: chỉ khối 6 báo lỗi.
- So mọi ô số tiền của thẻ Sổ (`#app` trừ khung Tình hình) giữa `main` (`a6cb0d1`) và bản PR, cùng máy chủ giả, mở hết tháng, trên hai sổ giả: 161 ô (85 + 76) trùng khớp; đã thử ngược bằng một bản cố ý sai thì phép so báo lệch.
- `npm run check` xanh (ruff chạy bằng venv của checkout chính).

**PR A3 (thẻ Trao đổi và Hồ sơ), 1/11/2026** — máy chủ giả, 1280×720, dữ liệu giả, đồng hồ trang ghim 15/11/2026 (giờ VN); chưa đo trên `hao`:
- `test-so-khach-v7-contact-browser.js`, 4 test trên sổ giả có phiếu hủy, cấn trừ vào và ra, phiếu có dòng phân bổ đã bị thay, phần ứng trước, một hội thoại Zalo khớp tên và một không khớp:
  1. Trao đổi:
     - Bảy mục đúng ngày, số tiền, tháng trừ nợ; dòng phân bổ đã bị thay không hiện; phiếu hủy gạch số tiền, có ngày hủy và lý do.
     - Phần trừ nợ trùng chữ ở danh sách phiếu thẻ Sổ.
     - Hội thoại tìm theo tên Sheet; link Mở chat, Mở hội thoại đúng tên và đúng hội thoại.
     - Lọc theo loại giữ tiêu điểm; không cuộn ngang, nút ≥ 40px, chữ thân 16px; không gửi lệnh nào.
     - Khối 6 của thẻ Tình hình có Zalo gần nhất.
  2. Copy tin nhắc:
     - Bộ nhớ tạm có đúng tin của Đòi nợ; gửi một lệnh `POST /api/v7/reminders` `{customer_id, source: copy-button}`.
     - Lần nhắc đọc lại thành 15/11/2026 · đã nhắc 4 lần.
     - Bấm lần hai cùng ngày gửi lệnh giống hệt; máy chủ giả giữ `UNIQUE` theo ngày như `reminder_log` nên không thêm dòng, vẫn 4 lần. Phiên bản sổ không đổi.
  3. Hồ sơ:
     - Mặt hàng, hạn trả kèm ví dụ.
     - Giá đang áp bằng các dòng "Đang dùng" của khung Bảng giá, mở bằng nút ở thẻ Hồ sơ.
     - Cột phụ phí riêng bằng tiêu đề cột của sổ; nút 📎 mở khung xem ảnh ở thẻ Sổ.
  4. Lỗi:
     - `reminders` cắt một lần (`page.route` abort `times: 1`): chỉ dòng lần nhắc báo lỗi kèm Thử lại, phiếu thu vẫn hiện.
     - Máy chủ chưa có bản xuất chat: một câu "Chưa có dữ liệu chat trên máy chủ." ở cả thẻ Trao đổi và Tình hình.
     - `price-table` cắt một lần: chỉ khối giá báo lỗi.
- Ở DB, bấm lặp không thêm dòng nhờ `UNIQUE(customer_id, source, reminded_at)` và `ON CONFLICT DO NOTHING` của `record_reminder`. Harness `tools/test_pg_v7_backend_doi_no.py` đã kiểm điều này; PR không đổi SQL.
- `test-cong-no-format.js`: `reminderText` cho đúng tin Đòi nợ cũ; `vnDay` qua nửa đêm giờ VN.
- Sửa test cũ: `test-so-khach-v7-tabs-browser.js` đổi nút "Mở thẻ Sổ" của thẻ chưa có nội dung thành nút "Xem thẻ Trao đổi" của thẻ Tình hình.
- So mọi ô số tiền của thẻ Sổ (`#app` trừ ba khung ngoài Sổ) giữa `main` (`1d3bfac`) và bản PR, cùng máy chủ giả, mở hết tháng: 182 ô (85 + 21 + 76) trùng khớp. Sổ thứ ba có phiếu hủy, cấn trừ vào và ra, ứng trước, ảnh chứng từ. Đã thử ngược bằng một bản cố ý sai thì phép so báo lệch.
- `npm run check` xanh (ruff chạy bằng venv của checkout chính).

**PR A4 (đường vào), 1/11/2026** — máy chủ giả, 1280×720, dữ liệu giả; chưa đo trên `hao`:
- `test-v7-dashboard-browser.js`:
  - ngăn kéo có "Trang khách" `?customer=2&the=tinh-hinh` giữa "Mở sổ khách" (`?customer=2`, giữ) và "Xem ở ma trận";
  - ba nút một dòng, cao 42px, chữ không tràn.
  - Test cũ vẫn xanh: ô tìm khách mở `?customer=`, Việc cần làm mở `loc=`.
- `test-v7-receivables-matrix-browser.js`: tên khách mở `&the=tinh-hinh`, không còn tên nào mở thẳng Sổ; ngăn kéo vẫn `month=` (test cũ).
- `test-doi-no-browser.js`:
  - tên khách mở `&the=trao-doi`;
  - số quá hạn mở `&month=2026-08` (tháng nợ cũ nhất), title ghi số đồng chính xác và tháng, vùng bấm ≥ 40px;
  - nút Chat giữ link cũ; các cột vẫn thẳng tiêu đề.
- Thử ngược: ba file test mới chạy trên code của `main` (`65433ec`) thì ba test đỏ đúng ở dòng kiểm link.
- `npm run check` xanh (ruff chạy bằng venv của checkout chính).

## Lựa chọn đã chốt

Người dùng chốt ngày 31/10/2026 trong chat, chọn đúng phương án Claude đề xuất cho cả tám câu ([`TRANG-KHACH-01`](../docs/decisions/trang-khach-01.md)). Phương án không chọn ghi lại để sau này biết đã cân nhắc gì.

- **K1 · Theo sổ hay theo khách:** theo sổ ở giai đoạn A và B; gộp sổ ở giai đoạn C, sau khi chủ nghiệp vụ gán 236 sổ vào khách. Không đoán theo tên, vì tên trùng không có nghĩa là cùng khách. Không chọn: làm khóa nhóm sổ ngay từ đầu.
- **K2 · Thẻ mặc định khi địa chỉ không ghi thẻ:** Sổ, để giữ thói quen người nhập và nghĩa của mọi link cũ. Không chọn: Tình hình; nhớ thẻ dùng lần trước trên máy.
- **K3 · Tên mục trên thanh điều hướng:** giữ "Sổ khách" tới khi chốt từ điển giao diện (audit 4.5). Không chọn: đổi thành "Khách".
- **K4 · Hứa trả:** có. Người đòi nợ ghi tay; máy tự chấm giữ lời hay lỡ hẹn theo phiếu thu; không cộng vào số nào. Không chọn: không làm, giữ đúng phạm vi NHAC-NO-01 v1.
- **K5 · Đo trả chậm:** số ngày từ hạn trả tới ngày trả xong của từng tháng nợ, theo quy tắc ở mục đối chiếu; tháng trả xong trước mốc nạp thì không đo. Không chọn: bỏ khối 3.
- **K6 · Hội thoại Zalo:** gắn tay một lần, ở thẻ Hồ sơ hoặc từ trang Chat Zalo. Không chọn: tiếp tục tìm theo tên.
- **K7 · Debit note:** ghi lại mỗi lần bấm xuất (tháng, số debit note, tổng tiền, người làm). Không chọn: không ghi.
- **K8 · Quyền:** giữ V7-ID ở giai đoạn này. Phân quyền "chỉ xem" cho sếp là việc riêng, cần spec danh tính. Không chọn: làm phân quyền trước trang khách.

## Câu hỏi mở

- Ngoài phạm vi, xét ở đợt 3 của audit: ma trận "Công nợ theo tháng" nhóm theo tuổi tháng, còn Tổng quan và trang khách nhóm theo hạn trả. Hai cách cùng chữ "1–2 tháng" nhưng lệch nhau một tháng (mục Vì sao cần, điểm 5).
