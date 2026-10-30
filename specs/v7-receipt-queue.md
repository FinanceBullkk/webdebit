# V7: ghi phiếu thu từ Sheet ("Ghi N phiếu thu")

Trạng thái: **ĐÃ CHỐT** hướng (người dùng chọn "Làm đồng bộ phiếu thu" trong chat 30/10/2026, sau đối soát chỉ đọc cùng ngày). Quy tắc ghép và giao diện dưới đây là **ĐỀ XUẤT** của Claude theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md); người dùng đi hết luồng trên bản thật rồi mới coi là nghiệm thu. Quyết định: [`THU-SHEET-01`](../docs/decisions/thu-sheet-01.md). Không đổi luật tiền: ghi bằng lệnh `record_receipt` có sẵn.

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720). Mỗi lần ghi mang tên người bấm (`V7-ID`).

**Bối cảnh:** chạy song song thì Sheet là sổ chính thức ([`SONG-SONG-01`](../docs/decisions/song-song-01.md)). Chuyến và giá đã có đường từ Sheet lên web; phiếu thu thì chưa, nên mọi phiếu thu trên Sheet phải gõ lại trên web. Đối soát 30/10/2026 cho thấy đây là nguyên nhân chính của lệch tổng (9/12 khách lệch).

Trên Sheet, phiếu thu nằm ngay trên dòng chuyến của tab khách: ô ngày thu là chữ tự gõ ("23/10/2026 tt", "da tt") hoặc ô ngày, ô số tiền thu là số.

**Luồng:**
1. Sổ khách: đầu sổ có nút "**Ghi N phiếu thu từ Sheet**", cạnh nút "Ghi N giá từ Sheet".
2. Bấm nút: khung xác nhận ngay dưới đầu sổ liệt kê từng phiếu (ngày thu, số tiền, ghi chú Sheet), tổng tiền, tổng còn nợ từ … xuống …. Hai nút "Ghi N phiếu" và "Thôi".
3. Ghi xong, sổ tải lại: phiếu mới có trong danh sách phiếu thu, phân bổ theo nợ cũ trước, Lịch sử có một dòng "Ghi phiếu thu" cho mỗi phiếu kèm người làm. Ô chứng từ của phiếu ghi "Sheet: <ghi chú trên Sheet>".
4. Trường hợp không tự ghi hiện thành dòng "**Phiếu thu Sheet cần xem: K**", bấm "Xem" để mở danh sách.

**Không tự ghi:**

| Trường hợp (mã) | Hiện cho người dùng | Hành động |
| --- | --- | --- |
| Phiếu Sheet chưa có trên web, đọc được ngày thu, ngày không sau hôm nay (`READY`) | Trong nút "Ghi N phiếu thu" | Ghi cả lô |
| Sheet không ghi ngày thu ("da tt", trống) (`NO_DATE`) | "Sheet không ghi ngày thu" + số tiền, tháng | Nhập tay ở hàng nhập phiếu thu, hỏi ngày thu |
| Ngày thu sau hôm nay (`FUTURE_DATE`) | "Ngày thu sau hôm nay" | Sửa ngày trên Sheet; web chặn ngày tương lai |
| Cùng tháng, web còn dòng thu sổ gốc không thấy trên Sheet (`SHEET_EDITED`) | "Sheet đã sửa phiếu thu tháng M: web A · Sheet B" | Xóa dòng thu sổ gốc cũ (lệnh có sẵn, [`XOA-THU-GOC-01`](../docs/decisions/xoa-thu-goc-01.md)); lần đọc sau phiếu Sheet thành `READY` |
| Phiếu trùng dòng thu sổ gốc mà web đã xóa (`WEB_DELETED`) | "Web đã xóa khoản thu này, Sheet vẫn còn" | Người nhập xem Sheet; muốn trừ lại thì nhập phiếu tay |
| Đã có trên web (`MATCHED_LEGACY`, `MATCHED_WEB`) | Không hiện | — |
| Tab khách có lỗi cấu trúc, hoặc tab không có khách web | Không hiện trên sổ | Admin sửa tab hoặc thêm tên phụ |

## Đầu ra

Sổ khách có nút "Ghi N phiếu thu từ Sheet" khi Sheet có phiếu chưa có trên web. Một lần bấm ghi cả lô qua `record_receipt`. Phiếu không chắc chắn được liệt kê riêng, không bao giờ tự ghi.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Số đo thật** (bản tải Sheet 12:46 ngày 30/10/2026 giờ VN, sổ `hao` qua API GET, chỉ đọc; chi tiết ngoài Git):
- 1.220 phiếu thu ở các tab khách đọc được. 1.207 trùng dòng thu sổ gốc theo (tháng, số tiền, chữ ngày thu).
- Còn 13: 9 có ngày thu đọc được và chưa có trên web (5 ngày từ 21/10, 4 ngày trước 21/10 nhưng không có trong bản nạp mốc, tức ghi lên Sheet sau mốc với ngày lùi), 4 không có ngày.
- 19 dòng thu sổ gốc không còn phiếu Sheet: 17 ở khách tab lỗi cấu trúc (bị giữ, [`SONG-SONG-03`](../docs/decisions/song-song-03.md)), 2 ở hai khách mà Sheet đã sửa số tiền phiếu cũ. Ở một khách, đối soát báo web thu nhiều hơn Sheet đúng bằng phần Sheet sửa giảm.
- Hệ quả: **không cắt theo ngày mốc** (sẽ bỏ sót 4 phiếu ghi lùi ngày); chống ghi trùng bằng ghép với dòng sổ gốc, và tháng còn dòng sổ gốc "mồ côi" thì không tự ghi (`SHEET_EDITED`).

**Có sẵn, dùng lại:**
- Đọc tab khách: `v7_load_real_copy.scan_tabs` đã tách dòng thu (`kind: receipt`, tháng khối, dòng, số tiền, chữ ngày thu). Runner giá đã đọc mọi tab khách qua Sheets API 15 phút một lần.
- Ghi phiếu: `record_receipt(date, method, amount_vnd, reference)`: chặn ngày tương lai, phân bổ nợ cũ trước, phân bổ lại mọi phiếu, Lịch sử có người làm, chống ghi trùng bằng `idempotency_key`.
- Xóa dòng thu sổ gốc: `delete_legacy_trip` (XOA-THU-GOC-01).
- Mẫu lô: `POST /api/v7/sheet/prices` và `so-khach-v7-sheet-ui.js`.

## Quy tắc ghép

Theo từng khách (tab ↔ sổ như đường giá: tên hoặc tên phụ, bỏ ký tự Excel cấm):
1. Bỏ tab có lỗi cấu trúc (`issues` của `scan_tabs` khác rỗng): tiền thu không chắc thì không đưa lên.
2. **Ngày thu**: ô ngày (số sê-ri) hoặc `dd/mm/yyyy` ở đầu ô chữ (`.`/`-` cũng được), hoặc `yyyy-mm-dd`. Khác thì không có ngày.
3. Ghép **dòng thu sổ gốc** chưa xóa: cùng tháng khối, cùng số tiền, cùng chữ ngày thu (gộp khoảng trắng, không phân biệt hoa thường). Trùng dòng sổ gốc đã xóa thì `WEB_DELETED`.
4. Ghép **phiếu web** chưa hủy: cùng số tiền, cùng ngày; rồi cùng số tiền lệch ngày ≤ 3 ngày (người nhập gõ ngày khác chút). Mỗi phiếu web chỉ ghép một lần.
5. Còn lại: không ngày → `NO_DATE`; ngày sau hôm nay (giờ VN) → `FUTURE_DATE`; tháng khối có dòng thu sổ gốc chưa ghép ở bước 3 → `SHEET_EDITED`; còn lại `READY`.

Hình thức phiếu: `THU TIỀN`. Chứng từ: "Sheet: " + chữ ngày thu trên Sheet (tối đa 500 ký tự).

## Giao tiếp frontend–backend

- Runner giá (`v7_price_snapshot.py`) ghi thêm bản chụp phiếu thu `receipts.json` cạnh `prices.json` (hoặc `WEBDEBIT_RECEIPT_SNAPSHOT_PATH`), cùng lượt đọc, không thêm yêu cầu API. Hash tính trên các dòng.
- `get_ledger` trả thêm `sheet_receipts: {snapshot_sha256, ready, review, ready_count, review_count}`. Thiếu bản chụp thì `unavailable: true`, sổ vẫn đọc được. Mỗi dòng: `customer_tab`, `source_row`, `debt_month`, `amount_vnd` (chuỗi), `note`, `date` (hoặc null), `status`, và với `SHEET_EDITED` thêm `web_legacy` (id, số tiền các dòng sổ gốc mồ côi cùng tháng).
- `POST /api/v7/sheet/receipts {customer_id, expected_version, snapshot_sha256, idempotency_key}`: server tính lại `READY` từ bản chụp đúng hash; lệch hash thì `STALE_SHEET`. Ghi từng phiếu bằng `record_receipt`, khóa con suy từ khóa lô + hash + tab + dòng + số tiền + ngày. Hỏng giữa lô thì `complete: false` với số đã ghi; lần sau phiếu đã ghi thành `MATCHED_WEB`. Trả `{written, remaining, complete, version}`.

## Hành vi và bất biến

- Chỉ thêm phiếu thu; không sửa, không hủy phiếu có sẵn, không đụng chuyến.
- Không ghi khi không chắc: không ngày, ngày tương lai, Sheet đã sửa phiếu cũ, web đã xóa, tab lỗi.
- Một phiếu Sheet ghi tối đa một lần: lần đọc sau nó ghép với phiếu web vừa ghi.
- Phân bổ theo nợ cũ trước như mọi phiếu (`V7-SO`); tháng trên Sheet không quyết định tháng phân bổ.
- Phiếu thu không bị chặn bởi tháng khóa (như nhập tay).

## Tiêu chí nghiệm thu

- [ ] Test ghép (`test_v7_receipt_queue.py`, dữ liệu giả): đủ các mã; sổ gốc trùng nhiều dòng; phiếu web lệch ngày; tháng có dòng mồ côi; tab lỗi bị bỏ.
- [ ] Test API lô: chỉ `READY` được ghi; bấm lặp cùng khóa không ghi thêm; hash đổi thì từ chối; lỗi giữa lô trả `complete: false`.
- [ ] Test model và Playwright 1280×720 (máy chủ giả): nút đúng số, khung xác nhận đúng tổng, ghi xong nút biến mất, "Cần xem" đủ loại.
- [ ] `npm run check` xanh.
- [ ] Trên `hao`: đo lại chỉ đọc sau triển khai, số `READY` khớp số đo ở trên (trừ phiếu đã nhập tay sau đó).
- [ ] Người dùng đi hết luồng ghi trên sổ thật và xác nhận; chạy lại đối soát, các khách lệch vì phiếu thu về `KHOP`.

## Tiến độ (30/10/2026)

**ĐÃ CODE**, kiểm bằng dữ liệu giả (`npm run check`):
- `web/v7_receipt_queue.py`: đọc dòng thu từ các khối tháng của tab (khối lặp y hệt và dòng TOTAL không tính, như bản nạp mốc), ghép, phân loại.
- `tools/v7_price_snapshot.py`: một lần đọc Sheet ghi cả `prices.json` và `receipts.json`; hash giá không đổi.
- `GET /api/v7/ledger` trả `sheet_receipts`; `POST /api/v7/sheet/receipts` ghi lô qua `record_receipt`.
- Sổ khách: nút "Ghi N phiếu thu từ Sheet", khung xác nhận liệt kê từng phiếu và tổng còn nợ trước → sau, dải "Phiếu thu Sheet cần xem" với nút "Xem khoản cũ" tới ô xóa khoản thu sổ gốc.
- Test: `tests/test_v7_receipt_queue.py`, `test-so-khach-v7-model.js`, `test-so-khach-v7-receipt-browser.js` (Playwright 1280×720).

**Đo chỉ đọc bằng chính code này trên dữ liệu thật** (cùng bản tải 30/10, sổ `hao`, 238 khách; chi tiết ngoài Git): bản chụp 1.206 phiếu; `READY` 6 phiếu ở 6 khách; `SHEET_EDITED` 3 phiếu ở 2 khách; `NO_DATE` 4. Bản đo thử đầu tiên đọc cả dòng của khối tháng lặp y hệt và lệch 1 đ do làm tròn; đã sửa (đọc theo khối, ghép sổ gốc cho lệch ≤ 1 đ cùng tháng, cùng chữ ngày).

**Triển khai:** không SQL, không migration, không đổi unit. Runner giá trên `hao` chạy từ release nên lượt kế tiếp sau khi `Deploy hao` xanh tự ghi `receipts.json` cạnh `prices.json`; API mặc định đọc cùng thư mục.

## Câu hỏi mở

- Đếm "N phiếu thu từ Sheet chờ ghi" ở Tổng quan (như giá, CÒN MỞ).
- Ghi chú Sheet có "cấn trừ"/"trừ USD": hiện vẫn ghi hình thức `THU TIỀN`; đổi khi người dùng muốn phân loại.
