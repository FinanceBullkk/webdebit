# Kiểm tab trước khi ghi, danh tính máy, hết báo chung

Trạng thái: ĐỀ XUẤT (Claude, 16/11/2026, theo yêu cầu người dùng "viết đề xuất kiến trúc"). Chưa chốt, chưa code.

## Vì sao

Ngày 16/11/2026 Claude xử lý tab Việc cần làm trên `hao` và gặp tám chỗ bất cập. Ba chỗ có thể làm sai tiền hoặc làm sai Lịch sử. Năm chỗ làm việc tồn mãi không đóng được. Gốc chung: máy đọc Sheet, đoán rồi đề xuất ghi tiền, nhưng **không có bước nào hỏi "tab này có đủ lành để tin không"** trước khi cho ghi.

| # | Chỗ bất cập | Ca thật 16/11 | Hậu quả |
| --- | --- | --- | --- |
| 1 | Bảng đối chiếu coi mọi dòng "có tiền, không container" là phí riêng (`fee_groups`, `web/v7_sheet_fix.py`) | Sổ 239: khối T10 của tab có tiền nằm lệch xuống một dòng so với container. Bảng đề xuất +44.710.920 và +42.546.330, người dùng bấm ghi lúc 08:32 | Sổ có thể tính trùng 87,26 tr (254,76 tr so với 167,5 tr ở khối T11 của tab) |
| 2 | `v7_api_doi_chieu.write` không xét khách có đang bị giữ (`HELD`) hay không | Cũng sổ 239: lượt đối soát xếp khách vào `HELD` (`MISSING_TRIP_AMOUNT`), nhưng bảng đối chiếu vẫn cho ghi | Máy đối soát biết tab hỏng mà đường bấm tay không biết |
| 3 | Mọi lệnh qua Tailscale Serve mang tên theo tài khoản Tailscale (`v7_identity.resolve_actor`) | Không phân biệt được lệnh 08:32 là người dùng bấm hay một phiên AI chạy trên cùng máy | Lịch sử không trả lời được "ai đã làm" khi có nhiều phiên AI |
| 4 | Web không có loại nghiệp vụ "trả lại tiền dư cho khách" | Sổ 228: Sheet ghi ô thu −164.833.232 | Khách bị giữ mãi (`INVALID_RECEIPT_AMOUNT`) |
| 5 | Nhiều việc không có nút đóng: dòng `AMBIGUOUS` (giá, PS), chuyến cũ ở tháng khóa, dòng ghi "VAT" | 12 việc không bấm được gì, gồm sổ 94, 119, 120, 143 và 239 | Việc cần làm ngày càng nhiễu, người dùng quen bỏ qua |
| 6 | Chuỗi rỗng và NULL bị coi khác nhau giữa Python và SQL | Trip 493: `shipper = ''`, phần đọc coi là trống, `resolve_sheet_conflict` so `IS DISTINCT FROM` | Nút "Theo Sheet" luôn báo "Sổ đã thay đổi" |
| 7 | Container chỉ khớp khi ô ghi đúng nguyên chuỗi | Ô `YMLU5506443-mã chưa up` (tab đã tính 50,6 tr) không được nhận | Dòng CONT_NGUON cùng container hiện thành "chuyến mới"; duyệt vào là có nguy cơ tính trùng |
| 8 | Lời giải thích khi gãy số dư (`chain_break`) chỉ nêu tháng | Sổ 79: ô M848 thiếu `=SUM(...)`. Sổ 162: ô N45 bị gõ đè 0 lúc 09:04 | Phải mở Sheet dò tay, trong khi máy đã có đủ dữ liệu để chỉ đúng ô |

Kèm theo một việc dữ liệu cũ: ngày đảo ngày/tháng khi nạp sổ gốc (SNHU8016690: tab ghi 4/9, web ghi 9/4) vẫn còn. Lỗi này đã được ghi từ [MOC-CHUYEN-MOI](../docs/decisions/moc-chuyen-moi.md) nhưng chưa đo hết.

## Đầu ra

Một **kết luận sức khỏe tab** dùng chung cho mọi đường ghi theo Sheet. Tab không lành thì không đường nào được đề xuất ghi tiền cho khách đó, và màn chỉ hiện "Sheet cần sửa ô X". Lệnh của máy và của AI mang tên riêng trong Lịch sử. Mọi việc trong Việc cần làm đều có ít nhất một cách đóng.

## Hiện trạng code (đã đọc 16/11/2026, `main` 75cfb21)

- Đọc tab: cả lượt đối soát (`v7_export_clean`, `v7_reconcile_auto.py`) lẫn bản chụp giá và phiếu 15 phút (`tools/v7_price_snapshot.py`) đều đi qua `v7_load_real_copy.scan_workbook` / `scan_tabs`. Bộ quét đã đếm lỗi từng tab (`issues`: `MISSING_TRIP_AMOUNT`, `INVALID_RECEIPT_AMOUNT`; `reasons`: `ANCHOR_CHAIN_MISMATCH`…). Nhưng chỉ lượt đối soát dùng các lỗi này để giữ khách (`reason="HELD"`). Bản chụp giá và phiếu bỏ chúng đi.
- Đường ghi theo Sheet: lượt đối soát (`apply_fix`), bảng đối chiếu (`/api/v7/sheet/doi-chieu/ghi` → `apply_fix`), giá Sheet (`/api/v7/sheet/prices`, `/api/v7/sheet/tasks/price`), phiếu thu Sheet (`/api/v7/sheet/receipts`), duyệt chuyến (`/api/v7/sheet/approve`, máy P3b trong `v7_inbox`), tách PS (`/api/v7/ps/fees`).
- Hết báo: `keep_sheet_task` nhận `task_kind ∈ {price, removed, ps}` và bắt buộc `target_id` dương, nên dòng chưa gắn được vào chuyến nào (`AMBIGUOUS`) thì không đóng được. Chuyến mới (`NEW`) chỉ có Duyệt.
- Danh tính: `resolve_actor` lấy `Tailscale-User-Login` do Serve gắn vào. Cùng một máy thì người và AI có cùng login. Lệnh chạy trên `hao` bằng `PsqlDirect(...).run(..., actor)` thì tự đặt được tên (`may-theo-sheet`, `claude`).

## Đề xuất

### K1. Kết luận sức khỏe tab (gốc của 1, 2, 8)

1. Bộ quét trả thêm `health` cho từng tab: `ok` hoặc `broken`, kèm danh sách `findings`. Mỗi `finding` có loại, ô (A1), câu giải thích và cách sửa gợi ý. Các loại:
   - `chain_break`: đã có, thêm ô gây gãy. So công thức ô tổng với mẫu các khối khác của cùng tab; ô trống hoặc là số gõ tay thay cho công thức thì nêu thẳng ô đó.
   - `row_shift`: một dòng có container mà không có tiền, ngay dưới là dòng có tiền mà không container (hoặc ngược lại), trong cùng khối tháng.
   - `negative_receipt`: số âm ở cột thu.
   - `duplicate_container`: cùng container hai dòng trong một tab mà một dòng không có tiền.
   - Các lỗi đang có của `issues` và `reasons`.
2. Kết luận được ghi vào bản chụp giá, phiếu và PS (cùng một lượt quét) và vào `reconcile.json`. Mọi đường ghi ở mục Hiện trạng đọc **cùng một hàm** `tab_health(customer)`.
3. Tab `broken` thì:
   - máy không ghi gì cho khách đó, như `HELD` hiện nay;
   - bảng đối chiếu, giá Sheet, phiếu Sheet không đề xuất nhóm ghi tiền; API trả `409 TAB_BROKEN` nếu vẫn bị gọi;
   - Việc cần làm hiện một khối "Sheet cần sửa" gồm từng ô và cách sửa, có nút mở đúng ô trên Sheet (nếu có quyền).
4. Duyệt chuyến mới không đổi tiền nên **không** bị chặn.

Không đổi luật tiền và không thêm hàm SQL ghi tiền. Chỉ thêm điều kiện chặn trước các lệnh đã có.

### K2. Danh tính máy và AI (gốc của 3)

Đề xuất mặc định: AI không ghi qua Serve bằng phiên Tailscale của người dùng. AI chỉ ghi bằng lệnh chạy trên `hao` qua `PsqlDirect` với tên `claude:<tên phiên>` (đã dùng ngày 16/11). API thêm một chặn mềm: lệnh ghi phải mang header `X-Webdebit-Client: ui` mà chỉ trang web gửi. Thiếu header thì trả `403 CLIENT_REQUIRED`, để `curl` hoặc script vô tình gọi bằng phiên người dùng bị từ chối thay vì ghi tên người dùng.

CÒN MỞ: header là quy ước, không phải bảo mật (AI vẫn giả được). Nếu cần chặt hơn thì cho AI một thiết bị Tailscale riêng (gắn tag) và `allowed_logins` phân biệt theo thiết bị. Việc này đổi cấu hình Tailscale nên phải hỏi người dùng trước.

### K3. Hết báo chung theo dấu vân dòng Sheet (gốc của 5)

Thêm `task_kind` mới `source` cho `keep_sheet_task`: đóng một việc theo `source_fingerprint` của dòng Sheet, không cần `target_id`. Áp cho `AMBIGUOUS` (giá, PS), `NEW` ở tháng khóa và dòng không phải chuyến ("VAT"). Dòng Sheet đổi thì dấu vân đổi, máy tự hỏi lại, đúng cách `PS-HOI-01` đang làm. Cần migration nhỏ: mở rộng ràng buộc `task_kind` và cho phép `target` rỗng khi `task_kind='source'`.

### K4. Chuẩn hóa ở biên (gốc của 6, 7)

Một module `web/v7_normalize.py` là chỗ duy nhất quyết:
- chữ: cắt khoảng trắng, chuỗi rỗng thành NULL. Áp ở bộ đọc Sheet **và** trước khi gửi `target_value` xuống SQL;
- container: tách mã theo mẫu 4 chữ + 7 số (ISO 6346) trong ô, giữ phần chữ còn lại làm ghi chú;
- ngày: ô ngày mà cả hai cách đọc ngày/tháng đều hợp lệ và lệch tháng với khối thì gắn cờ `date_ambiguous`, không tự chọn.

SQL thêm `nullif(btrim(...), '')` ở các chỗ so trước–sau của `resolve_sheet_conflict` và `edit_trip_info`, để hai lớp cùng một luật.

### K5. Nghiệp vụ còn thiếu: trả tiền dư cho khách (gốc của 4)

Cần người dùng chốt trước khi code. Hai phương án:
- (a) Loại phiếu mới "Chi trả khách" (số dương, giảm phần khách dư), có ngày, cách trả, chứng từ. Bộ đọc nhận số âm ở cột thu là loại này.
- (b) Dùng dòng điều chỉnh tháng như hiện nay, bộ đọc nhận số âm và đề xuất điều chỉnh.

Khuyến nghị (a): đây là dòng tiền thật đi ra, nên Bảng thu và báo cáo cần thấy nó riêng.

### K6. Việc dữ liệu: đo ngày đảo

Lệnh chỉ đọc so `event_date` của dòng sổ gốc với ngày trên tab hiện tại, đếm số dòng bị đảo và số dòng vì thế nằm sai tháng. Báo con số trước, sửa sau theo quyết định của người dùng.

### Để sau

`tools/v7_backend_functions.sql` (4.008 dòng), `web/v7_inbox.py` và `web/v7_api_sheet.py` (khoảng 850 dòng mỗi file) nên tách theo nghiệp vụ (thu, chuyến, phí, đối soát) khi có dịp sửa lớn. Không tách riêng chỉ để dọn.

## Thứ tự đề xuất

| Đợt | Nội dung | Đổi schema | Vì sao trước |
| --- | --- | --- | --- |
| 1 | K1 bước 1–3 cho `row_shift` và `HELD` + chặn ở `doi-chieu/ghi` và `apply_fix` | Không | Chặn đúng đường đã làm sai tiền hôm nay |
| 2 | K4 (NULL/chuỗi rỗng, tách container) | Không (chỉ sửa hàm SQL) | Lỗi nhỏ, sửa dứt điểm, giảm "chuyến mới" giả |
| 3 | K1 phần còn lại (`chain_break` chỉ ô, số âm, container lặp) + khối "Sheet cần sửa" | Không | Biến việc tồn thành việc sửa Sheet cụ thể |
| 4 | K3 hết báo chung | Có (migration nhỏ) | Dọn việc không đóng được |
| 5 | K2 danh tính | Không (header) / Có (Tailscale, phải hỏi) | Cần người dùng chọn mức chặt |
| 6 | K5 sau khi chốt, K6 đo | Có thể | Cần quyết định nghiệp vụ |

## Nguồn quyết định

- [MAY-DOI-SOAT-01](../docs/decisions/may-doi-soat-01.md), [CHAN-DOAN-LECH-01](../docs/decisions/chan-doan-lech-01.md): máy chỉ ghi khi khớp đúng; lời đoán chỉ giải thích.
- [VIEC-DOI-CHIEU-01](../docs/decisions/viec-doi-chieu-01.md): bảng đối chiếu và "Mở, ghi, khóa lại".
- [PS-HOI-01](../docs/decisions/ps-hoi-01.md): mẫu "hết báo" hỏi lại khi dòng nguồn đổi.
- [SONG-SONG-01](../docs/decisions/song-song-01.md): Sheet là sổ chính thức tới ngày chuyển hẳn.
- [BOOKING-EDIT-01](../docs/decisions/booking-edit-01.md): giữ booking đã ghi.
- CÒN MỞ: K2 (mức chặt của danh tính), K5 (phương án trả tiền dư).

## Hành vi và bất biến

- Không đổi cách tính nợ, phân bổ hay opening. K1 chỉ thêm điều kiện chặn trước lệnh ghi đã có.
- VND nguyên; NULL khác 0. K4 chỉ gộp chuỗi rỗng với NULL cho trường chữ, không bao giờ cho trường tiền.
- Tab `broken` vẫn được đọc, xem và duyệt chuyến (không đổi tiền). Chỉ đề xuất ghi tiền là bị chặn.
- Kết luận sức khỏe tính từ cùng một lượt quét với dữ liệu nó bảo vệ (cùng `sha256` bản chụp), để không có khoảng hở giữa lúc kiểm và lúc ghi.

## Tiêu chí nghiệm thu

- [ ] Fixture tái hiện sổ 239 (tiền lệch một dòng): `plan` không trả nhóm `fee_rows`, `health` = `broken` với `row_shift` nêu đúng hai ô; `POST /api/v7/sheet/doi-chieu/ghi` trả `409 TAB_BROKEN`.
- [ ] Fixture khách `HELD`: mọi đường ghi theo Sheet ở mục Hiện trạng đều từ chối, trừ duyệt chuyến.
- [ ] Fixture sổ 79 (ô tổng thu thiếu công thức) và sổ 162 (ô số dư gõ đè): `findings` nêu đúng ô và công thức mẫu.
- [ ] Trip có `shipper = ''`: "Theo Sheet" ghi được; test SQL trên harness PostgreSQL.
- [ ] Ô `YMLU5506443-mã chưa up` khớp container `YMLU5506443`; dòng CONT_NGUON cùng container không còn là `NEW`.
- [ ] `keep_sheet_task` với `task_kind='source'` đóng được một dòng `AMBIGUOUS`; sửa ô nguồn thì việc hiện lại.
- [ ] Đo trên `hao` (chỉ đọc, như cách đo ở [v7-may-doi-soat](v7-may-doi-soat.md)): số tab `broken` và phân loại `findings`, trước khi bật chặn.
- [ ] `npm run check` xanh; harness PostgreSQL chạy tay cho đợt có sửa SQL.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`)
- Review: opus (đụng đường ghi tiền)
- Được sửa: chia theo đợt, mỗi đợt một PR và một spec con hoặc mục con của spec này. Đợt 1 dự kiến: `cong-no-web-handoff/tools/v7_load_real_copy.py`, `cong-no-web-handoff/tools/v7_price_snapshot.py`, `cong-no-web-handoff/web/v7_sheet_fix.py`, `cong-no-web-handoff/web/v7_api_doi_chieu.py`, test tương ứng.
- Cấm: đổi luật tiền, phân bổ, opening; chạy loader `v7_load*` hoặc nạp dữ liệu thật; ghi Google Sheet; đổi cấu hình Tailscale khi chưa hỏi người dùng.

## Hoàn tác

Mỗi đợt revert được riêng. Đợt 4 có migration thì kèm câu lệnh đảo (thu hẹp lại ràng buộc `task_kind` sau khi xóa các dòng `source`).

## Bằng chứng

Ca thật đọc chỉ đọc trên `hao` ngày 16/11/2026, khoảng 13:00–13:40 giờ VN: `GET /api/v7/inbox`, `GET /api/v7/ledger` của 241/242 sổ, bản xuất xlsx sổ chính (đã xóa trên `hao` sau khi chép), `sokhach.event` của các sổ nêu trên, log sửa Sheet (`v7_sheet_log.py --tab`). Không có dữ liệu thật nào trong repo ngoài số sổ, số dòng, số tiền đã nêu.

## Câu hỏi mở

- K2: chọn header quy ước hay thiết bị Tailscale riêng cho AI?
- K5: phương án (a) hay (b) cho tiền trả lại khách?
- K1: khi tab `broken` mà người dùng vẫn muốn ghi ngay (Sheet chưa sửa kịp), có cần lối vượt có lý do không, hay bắt buộc sửa Sheet trước?
