# Trang khách: một khách, bốn thẻ

Trạng thái: **ĐỀ XUẤT** (Claude, 31/10/2026), chưa chốt, chưa code. Người dùng yêu cầu viết spec trong chat ngày 31/10/2026, sau khi xem bản xem bấm thử. Nhu cầu gốc: sếp muốn cải thiện luồng người dùng, nhất là khi một người quản lý mở một khách thì xem được gì. Spec do Claude viết theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md). Tám câu K1–K8 ở cuối, mỗi câu có một phương án ghi "(đề xuất)". Bản xem dữ liệu giả: [`preview/mockups/trang-khach`](../cong-no-web-handoff/preview/mockups/trang-khach/index.html).

Thời điểm: [PLAN](../PLAN.md) đang tạm dừng tính năng mới cho tới khi chạy song song; spec này để duyệt hướng. Thẻ Sổ chính là sổ khách của [`SO-GON-04`](../docs/decisions/so-gon-04.md) (UX đợt 2, đang làm), nên giai đoạn A chỉ bắt đầu sau PR 2c của đợt đó (cùng sửa đầu sổ).

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
4. Giai đoạn B2, nếu K4 chốt: khách hứa trả thì bấm **Ghi hứa trả** (số tiền, hẹn ngày, ghi chú).

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

### Đầu trang (dính, một dòng, cao ≤ 44px)

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

**Hứa trả** (nếu K4 chốt):
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

## Đầu ra

**Giai đoạn A**, trên máy chủ giả rồi trên `hao`:
- Mở `?customer=<id>&the=tinh-hinh` thấy các khối 1, 2, 4, 5 và phần A của khối 6. Mọi số khớp với Sổ và Tổng quan.
- Thẻ Trao đổi có phiếu thu, lần nhắc gần nhất, Copy tin nhắc, Chat tìm theo tên.
- Thẻ Hồ sơ có mặt hàng, giá, cột phụ phí, ảnh chứng từ, hạn trả.
- Mọi link cũ vẫn mở thẻ Sổ như trước.
- Tổng quan, ma trận và Đòi nợ có đường vào đúng thẻ.

**Giai đoạn B và C**: theo từng spec backend riêng, sau khi các câu K liên quan đã chốt.

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

**Giai đoạn B:** hợp đồng đề xuất, sẽ viết chi tiết thành spec backend riêng khi K4–K7 chốt.

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
- CÒN MỞ: K1–K8 ở cuối spec.

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

Giai đoạn B: mỗi mục B1–B4 một spec backend, một migration và một PR giao diện, theo thứ tự người dùng chốt ở K4–K7. Giai đoạn C để sau K1.

## Tiêu chí nghiệm thu

PR A1:
- [ ] Mọi địa chỉ cũ (`?customer=`, `&month=`, `&loc=`) mở thẻ Sổ y như trước: mọi số tiền trong `#app` bằng nhau giữa bản `main` và bản PR.
- [ ] `the=tinh-hinh|so|trao-doi|ho-so` mở đúng thẻ. Bấm thẻ thì địa chỉ đổi mà không tải lại trang; Back về trang trước.
- [ ] Thẻ Sổ ở 1280×720: phần dính ≤ 180px, không cuộn ngang. Tên khách dài nhất của sổ giả không bị cắt.
- [ ] Bàn phím: Tab tới thanh thẻ, mũi tên trái/phải đổi thẻ, Enter mở; vùng bấm ≥ 40px.
- [ ] Đang gõ dở trong khung Ghi phiếu thu mà bấm sang thẻ khác rồi quay lại: số đã gõ còn nguyên.

PR A2:
- [ ] Bốn số bằng đúng: Còn nợ = `total_outstanding_vnd`; Quá hạn = `overdue_vnd` của khách; Thu tháng này = `received_vnd` của `today_month`.
- [ ] Hình 12 tháng: mỗi cột và mỗi điểm bằng `charges_vnd`, `received_vnd`, `end_of_month_vnd` của tháng đó. Tháng không có trong `months[]` không có cột. Bấm cột thì sang thẻ Sổ với `month=` đúng.
- [ ] Đi hàng: số chuyến tháng bằng số dòng chuyến web và sổ gốc của tháng; chuyến đã loại không đếm.
- [ ] Còn gì làm số chưa đúng: mỗi dòng mở Sổ với `loc` đúng; số đếm khớp chip tháng của SO-GON-04.
- [ ] Khách chưa có số dư đầu thì hiện câu thay số; khách dư thì hiện "Khách đang dư …", không hiện quá hạn.
- [ ] `dashboard/debt` lỗi (`page.route` abort): khối 1 hiện Còn nợ từ ledger, phần quá hạn báo lỗi kèm Thử lại; các khối khác vẫn hiện.

PR A3:
- [ ] Trao đổi: phiếu thu (kể cả cấn trừ) đúng ngày, số tiền, tháng trừ nợ theo `allocations` hiện hành; phiếu hủy hiện gạch, có lý do.
- [ ] Copy tin nhắc ghi đúng một dòng `reminder_log` như ở Đòi nợ. Bấm lặp trong một ngày không tạo dòng mới (`UNIQUE` theo ngày).
- [ ] Hồ sơ: giá đang áp bằng bảng giá trong sổ ở ngày hôm nay; cột phụ phí riêng đúng cài đặt của sổ.

PR A4:
- [ ] Ngăn kéo Tổng quan có "Trang khách" mở `the=tinh-hinh`; tên khách ở ma trận mở `the=tinh-hinh`; tên khách ở Đòi nợ mở `the=trao-doi`. Các link khác giữ như cũ.

Chung (bước 7–8):
- [ ] `npm run check` xanh ở từng PR; `test-so-khach-v7-ctx.js` xanh.
- [ ] Sếp hoặc chủ nghiệp vụ tự đi luồng 1 trên `hao` với một khách thật và xác nhận đọc đúng; người đòi nợ đi luồng 2 một lần.

## Hoàn tác

Mỗi PR của giai đoạn A revert riêng được, vì chỉ đổi file giao diện. Triển khai tự động khi merge; rollback bằng revert PR rồi để `Deploy hao` chạy lại. Không đụng dữ liệu. Giai đoạn B: migration chỉ thêm bảng và hàm ngoài đường tiền; rollback theo runbook trong spec backend của từng mục.

## Bằng chứng

Chưa có (spec). Hiện trạng đối chiếu trên mã tại `d65be02`. Bản xem chỉ dùng dữ liệu giả, không gọi API.

## Câu hỏi mở

- **K1 · Trang khách theo sổ hay theo khách?** Đề xuất: theo sổ ở giai đoạn A và B; thêm gộp sổ ở giai đoạn C sau khi chủ nghiệp vụ gán 236 sổ vào khách. Không đoán theo tên, vì tên trùng không có nghĩa là cùng khách. Phương án khác: làm khóa nhóm sổ ngay từ đầu.
- **K2 · Thẻ mở mặc định khi địa chỉ không ghi thẻ?** Đề xuất: Sổ, để giữ thói quen người nhập và để mọi link cũ giữ nghĩa. Phương án khác: Tình hình; hoặc nhớ thẻ dùng lần trước trên máy.
- **K3 · Tên mục trên thanh điều hướng?** Đề xuất: giữ "Sổ khách" tới khi chốt từ điển giao diện (audit 4.5). Phương án khác: đổi thành "Khách".
- **K4 · Có ghi hứa trả không?** Đề xuất: có. Người đòi nợ ghi tay; máy tự chấm giữ lời hay lỡ hẹn theo phiếu thu; không cộng vào số nào. Phương án khác: không làm, giữ đúng phạm vi NHAC-NO-01 v1.
- **K5 · Đo trả chậm thế nào?** Đề xuất: số ngày từ hạn trả tới ngày trả xong của từng tháng nợ, theo quy tắc ở mục đối chiếu; tháng trả xong trước mốc nạp thì không đo. Phương án khác: bỏ khối 3.
- **K6 · Gắn hội thoại Zalo với khách?** Đề xuất: gắn tay một lần ở thẻ Hồ sơ hoặc từ trang Chat Zalo. Phương án khác: tiếp tục tìm theo tên.
- **K7 · Ghi lại lần xuất debit note?** Đề xuất: có; mỗi lần bấm xuất ghi tháng, số debit note, tổng tiền và người làm. Phương án khác: không ghi.
- **K8 · Quyền xem cho sếp?** Đề xuất: giữ V7-ID ở giai đoạn này (ai vào app cũng thao tác như nhau). Phân quyền "chỉ xem" là việc riêng, cần spec danh tính. Phương án khác: làm phân quyền trước trang khách.

Ngoài phạm vi, ghi lại để xét ở đợt 3 của audit: ma trận "Công nợ theo tháng" nhóm theo tuổi tháng, còn Tổng quan và trang khách nhóm theo hạn trả. Hai cách cùng chữ "1–2 tháng" nhưng lệch nhau một tháng (mục Vì sao cần, điểm 5).
