# V7: phân loại phụ phí theo bảng PS của bộ lập bill

Trạng thái: **ĐỀ XUẤT** (Claude, 29/10/2026). Spec con của [`v7-phu-phi-nhieu-loai.md`](v7-phu-phi-nhieu-loai.md), mục "Nhập từ bảng chi phí phát sinh". Chính sách nguồn đã chốt ở [`PHU-PHI-01`](../docs/decisions.md#phu-phi-01) (9)–(11). Chưa có mockup, chưa code. Spec này đổi ba điểm so với phần ĐỀ XUẤT của spec cha; lý do ở mục [Khác spec cha](#khác-spec-cha).

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720), cùng người dán chuyến và ghi giá từ Sheet hằng ngày. Theo `V7-ID`, mỗi lần ghi mang tên người bấm.

**Bối cảnh:** phụ phí trên web hiện chủ yếu là **Khác** hoặc **Phụ phí ban đầu**. Nguyên nhân: dán lô và "Ghi N giá từ Sheet" chỉ biết tổng ba cột phí của tab khách, còn migration tách loại gom phí cũ thành Phụ phí ban đầu. Bộ lập bill có tab `PS_DATA` gom các bảng chi phí phát sinh theo tháng. Bảng này đã chia sẵn từng cont theo Neo, Điện, Ghép, Khác và đánh dấu Health/Kiểm định. Người nhập muốn web biết từng khoản mà không gõ lại.

**Luồng:**
1. Mở sổ khách. Đầu sổ, cạnh "Ghi N giá từ Sheet", có nút **"Tách N phụ phí theo bảng PS"** khi có chuyến tách được.
2. Bấm nút thì mở khung xác nhận ngay dưới đầu sổ (không phải hộp thoại). Mỗi chuyến một dòng gồm cont, ngày và phần trước → sau, ví dụ "Phụ phí ban đầu 2.000.000 → Neo 1.500.000 + Điện 500.000". Cuối khung ghi **"Tổng tiền không đổi"**. Hai nút: **Tách** và **Thôi**.
3. Bấm Tách thì sổ tải lại. Các ô cột riêng (nếu sổ bật Neo/Điện/Ghép) có số, ô Khác giảm tương ứng, tổng còn nợ không đổi. Lịch sử có một dòng "Tách phụ phí theo PS" cho mỗi chuyến, gồm trước → sau và nguồn "PS tab …, dòng …".
4. Những dòng PS không tự tách được nằm ở mục **"PS cần xem: K"**. Bấm vào thì mở danh sách, mỗi dòng ghi lý do và cách xử lý (bảng dưới).
5. Chuyến được PS đánh dấu Health cert hoặc Kiểm định mà chưa có khoản loại đó thì nằm trong "PS cần xem" với lý do "PS đánh dấu Health cert — nhập giá tay". Người nhập ghi khoản trong khung chi tiết phụ phí như hiện nay, sau đó dòng nhắc tự hết.

**Kết quả:** chuyến có trong bảng PS được tách đúng loại sau một lần bấm mỗi khách. Không chuyến nào bị đổi tổng tiền.

**Không tự tách:**

| Trường hợp (mã) | Hiện trong "PS cần xem" | Người nhập làm gì |
| --- | --- | --- |
| Khớp đúng 1 chuyến, tổng PS = tổng phụ phí web, web còn khoản chưa phân loại, tháng mở (`READY`) | Không hiện; nằm trong nút "Tách N" | Bấm Tách |
| Như trên nhưng tháng khóa (`MONTH_LOCKED`) | "Tháng 7 đang khóa" | Nút "Mở khóa tháng 7" (ổ khóa có sẵn), sau đó dòng vào nút Tách |
| Tổng khác nhau, web đã có phụ phí (`TOTAL_DIFF`) | "Web 1.500.000 · PS 2.000.000" | Kiểm tab khách trên Sheet (sổ chính thức). Sửa tay trong khung chi tiết nếu web sai |
| Web chưa có phụ phí, PS có (`WEB_NO_FEE`) | "PS 1.500.000 · web chưa có phụ phí" | Ghi phí trên Sheet hoặc web như hiện nay (giá từ Sheet sẽ tự đưa lên); lần sau thành `READY` |
| Khớp nhiều chuyến, hoặc nhiều dòng PS cùng một chuyến (`AMBIGUOUS`) | "Dòng PS 214 khớp 2 chuyến" | Phân loại tay trong khung chi tiết |
| Ô tiền dưới 1.000đ, ví dụ Ghép = 1 (`PS_TYPO`, `PHU-PHI-01` (11)) | "Ghép = 1 trên PS, có thể gõ sai" | Sửa bảng PS hoặc phân loại tay |
| Ô tiền có số lẻ hoặc không đọc được (`PS_BAD_AMOUNT`) | "Khác = 315.789,5 trên PS" | Như trên |
| Ô Health+KĐ gộp có tiền (`PS_COMBINED`) | "PS gộp Health+KĐ 3.000.000, cần tách tay" | Tách tay trong khung chi tiết |
| PS đánh dấu Health/KĐ, chuyến chưa có khoản loại đó (`NEED_HEALTH`, `NEED_KD`) | "PS đánh dấu Health cert — nhập giá tay" | Thêm khoản trong khung chi tiết |
| Đã phân loại khớp PS (`DONE`), hoặc PS không có tiền (`PS_EMPTY`) | Không hiện | — |
| Không ra được khách, hoặc không tìm thấy chuyến (`NO_CUSTOMER`, `NOT_FOUND`) | Chỉ có trong báo cáo, không hiện trên sổ khách | Admin bổ sung tên phụ cho khách |

## Đầu ra

Sổ khách có nút "Tách N phụ phí theo bảng PS". Bấm một lần thì cả lô được tách: mỗi chuyến đổi các khoản Khác / Phụ phí ban đầu thành các khoản đúng loại, **tổng tiền không đổi**. Trường hợp không chắc chắn được liệt kê riêng và không bao giờ tự ghi. Web không cộng tiền từ PS.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Tab `PS_DATA`** (đo chỉ đọc 29/10/2026, số đếm; dữ liệu ngoài Git):
- 13 cột: `Tab phí`, `Cont chuẩn`, `Neo`, `Điện`, `Ghép`, `Health+KD`, `Health`, `Kiểm định`, `Khác`, `Dòng phí` (số dòng ở tab nguồn), `Ngày đóng phí`, `Chủ hàng phí`. Ô M2 là tổng số dòng, không phải dữ liệu.
- 6.117 dòng từ 6 tab tháng (T5 → tháng 10). Có 1.904 dòng có cont, trong đó khoảng 140 dòng có tiền: Neo 94, Điện 12, Ghép 7, Health+KĐ gộp 8 (chỉ tab T6), Khác 24. Mỗi tháng chỉ vài chục dòng có tiền.
- Tiền là chuỗi có dấu phẩy (`1,500,000`) hoặc số trơn. Có ô `0` (bỏ qua), `1` (gõ sai) và số lẻ ở cột Khác (`315789.5`, tab tháng 7).
- Cột **Khác** lẫn số tiền với chữ ghi chú (ví dụ giải thích số giờ chạy điện, tuyến ghép). Chữ là ghi chú, không phải tiền.
- `Health` / `Kiểm định` là ô đánh dấu từ tháng 8: 1.220 ô, chỉ 2 ô bật (`TRUE`, `Có`); Kiểm định chưa bật lần nào.
- `Ngày đóng phí`: T5, T6 dạng `dd/mm` không năm; từ tháng 7 dạng `dd/mm/yy`. 13 dòng có cont nhưng trống ngày.
- `Chủ hàng phí`: 103 tên khác nhau, kiểu tên chủ hàng trên booking (kèm mã số, có chữ Hán), không phải tên tab khách.
- 20 cont xuất hiện ở hai tab; phần lớn chỉ một bên có tiền, 2 cont có tiền ở cả hai tab.

**Có sẵn, dùng lại:**
- Đọc Sheet: `tools/v7_sheets_api_reader.py` (Sheets API, `UNFORMATTED_VALUE`), cùng tài khoản dịch vụ `spreadsheets.readonly` với `sheet_sync_runner.py` và `v7_price_snapshot.py`. File chứa `PS_DATA` cũng chứa `WEBDEBIT_EXPORT`, `BOOKING_DATA` và bảng duyệt tên khách mà runner đồng bộ chuyến đang đọc. Vì vậy nhiều khả năng quyền đọc đã có (CÒN MỞ, kiểm trên `hao`).
- Ghép chuyến: quy tắc của `web/v7_price_queue.py`, dùng cho cả chuyến web lẫn dòng sổ gốc: cùng khách, cùng cont, đúng ngày trước rồi tới lệch ≤ 3 ngày, mỗi đích một dòng nguồn. Tên khách → sổ: tên/tên phụ như hàng chờ giá, cộng bảng duyệt tên khách của runner đồng bộ chuyến (`webdebit_export_connector.parse_review_mapping`). Hàm này nằm ở `tools/`, nên tầng web không được import (`ARCH-02`): runner PS đọc bảng duyệt tên và ghi kèm vào bản chụp, giống cách hàng chờ giá chuyển lõi sang `web/`.
- Phụ phí trên sổ: `get_ledger` trả `fee_lines` (loại, số, ghi chú), `fee_columns`, cờ `has_typed_fee`, `counted_differs`; danh mục ở `get_fee_types()`.
- Bản chụp và nút làm mới: mẫu `prices.json` (hash theo dòng, ghi nguyên tử, mode 600) và [`v7-sheet-refresh`](v7-sheet-refresh.md) (tín hiệu `.path`).
- Giao diện: nút "Ghi N giá từ Sheet", khung xác nhận và "Cần xem" trong `so-khach-v7-ui.js` (`planSheetPrices` trong model).

**Còn thiếu:**
- **Lệnh SQL tách nguyên khối.** Các lệnh hiện có (`add_trip_fees`, `set_trip_fee_type`, `replace_trip_fee`, `void_trip_fee`) mỗi lệnh chỉ đổi một loại hoặc một khoản. Muốn đổi "Phụ phí ban đầu 2.000.000" thành "Neo 1.500.000 + Điện 500.000" thì phải gọi nhiều lệnh. Giữa các lệnh tổng tiền bị đổi tạm, phân bổ chạy lại nhiều lần, và nếu hỏng giữa chừng thì tổng sai. Với dòng sổ gốc còn tệ hơn: mỗi lệnh đi qua `_change_legacy` tính lại ô TOTAL. Khi `counted_differs` bật, TOTAL bị đổi dù tổng phụ phí giữ nguyên.
- Runner bản chụp PS, API hàng chờ, giao diện.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT)

**Bản chụp.** `tools/v7_ps_snapshot.py` đọc `PS_DATA!A1:L20000` bằng một lệnh `values:get` (`UNFORMATTED_VALUE`, `SERIAL_NUMBER`), rồi ghi `/var/lib/webdebit-sheet-sync/ps.json` (`WEBDEBIT_PS_SNAPSHOT_PATH`) gồm `{created_at, sha256, row_count, rows}`. Hash tính trên các dòng. Mỗi dòng có `source_tab`, `source_row`, `container`, `date` (ISO hoặc NULL), `owner`, `fees: {neo, dien, ghep, khac}` (VND nguyên hoặc NULL), `combined_vnd`, `health`, `kd` (bool), `note`, `problems: [...]`. Bản chụp kèm `customer_aliases` đọc từ bảng duyệt tên khách cùng file.

Quy tắc đọc:
- Kiểm tiêu đề đúng 12 cột; sai thì runner lỗi, không ghi file.
- Tiền: bỏ dấu phẩy ngăn nghìn. Trống hoặc `0` → NULL. Số nguyên ≥ 1.000 → tiền. Dưới 1.000 → `PS_TYPO`. Số lẻ, số âm hoặc chuỗi không phải số ở cột Neo/Điện/Ghép → `PS_BAD_AMOUNT`.
- Cột Khác: số thì như trên; chữ thì thành `note`.
- Ngày: `dd/mm/yy` → `20yy`. `dd/mm` không năm thì suy năm từ tháng của tên tab: tháng tab ≤ tháng hiện tại (giờ VN) → năm nay, ngược lại → năm trước. Trống → NULL, khi đó ghép theo cont như dòng không ngày của hàng chờ giá.
- Health/KĐ: `TRUE`, `Có` → bật; còn lại → tắt.

**Ghép (server, từ bản chụp đúng hash).** Mỗi dòng PS có tiền hoặc có cờ Health/KĐ được gán sổ khách theo `owner`, rồi ghép một đích (chuyến web hoặc dòng sổ gốc) theo quy tắc của hàng chờ giá. Gọi `ps_total` là tổng các ô tiền PS, `web_total` là tổng `fee_lines` hiệu lực. "Khoản chưa phân loại" là loại Khác, Phụ phí ban đầu hoặc Giảm trừ (đúng nhóm của `FEE_LINES_TYPED`). Trạng thái:
- `READY`: ghép duy nhất, không `problems`, không gộp Health+KĐ, `ps_total = web_total`, có ít nhất một khoản chưa phân loại, các khoản đã phân loại không mâu thuẫn PS, và kế hoạch sau khác hiện tại.
- Kế hoạch sau: mỗi ô PS có số thành một khoản đúng loại. Ô Khác có số thành khoản Khác. `note` gắn vào khoản Điện nếu có, không thì vào khoản đầu tiên. Các khoản đã phân loại trùng loại và số với PS được giữ nguyên.
- Tháng khóa → `MONTH_LOCKED`; đã khớp → `DONE`; còn lại theo bảng ở bước 1.
- Có Giảm trừ trên web thì tổng web nhỏ hơn PS, nên rơi vào `TOTAL_DIFF`. PS không có giảm trừ.
- Cờ Health/KĐ chỉ tạo `NEED_HEALTH` / `NEED_KD` khi đích chưa có khoản loại đó. Không tạo tiền, không lưu cờ trong DB.

**API.**
- `get_ledger` trả thêm `ps_fees: {snapshot_sha256, ready: [...], review: [...], ready_count, review_count}`. Mỗi mục có `source_tab`, `source_row`, `target_kind`, `target_id`, `month`, `before: [{fee_type_id, amount_vnd, note}]`, `after: [...]`, `ps_total`, `web_total`, `status`. Thiếu bản chụp thì trả `{unavailable: true}`, sổ vẫn đọc được.
- `POST /api/v7/ps/fees {customer_id, expected_version, snapshot_sha256, idempotency_key}`: server tính lại `READY` từ bản chụp đúng hash; lệch hash thì `STALE_SHEET` ("Bảng PS đã đổi. Tải lại rồi tách."). Mỗi đích một lệnh SQL, khóa con suy từ khóa lô + hash + đích. Trả `{written, skipped, version, complete}`. Hỏng giữa lô không làm sai tiền vì mỗi lệnh giữ tổng; lần sau các đích đã tách thành `DONE`.

**Lệnh SQL mới** `rewrite_trip_fees(customer_id, expected_version, idempotency_key, target jsonb, expected_line_ids jsonb, lines jsonb)`:
- Khóa khách, đọc `_fee_target` (chặn tháng khóa, CHỜ KIỂM, dòng sổ gốc thiếu đơn giá như các lệnh phí khác).
- `expected_line_ids` phải đúng bằng tập khoản hiệu lực hiện tại. Lệch → `FEE_LINES_CHANGED` ("Phụ phí chuyến này vừa đổi. Tải lại rồi tách.").
- `lines`: 1..10 khoản `{fee_type_id, amount_vnd, note}`, kiểm loại, dấu, khác 0 như `_change_trip_fees`. Không chọn được Phụ phí ban đầu. Tổng `lines` phải **bằng** tổng hiện tại, khác → `FEE_TOTAL_CHANGED`.
- Một `event` `rewrite_trip_fees` với trước → sau và nguồn (`source: {kind: 'ps', tab, row, snapshot_sha256}`), void các khoản cũ, ghi các khoản mới.
- Chuyến web: gọi `_sync_trip_fee`; tổng không đổi nên không ghi revision. Dòng sổ gốc: **không** gọi `_change_legacy`, vì tổng phụ phí không đổi nên TOTAL (`counted_vnd`) giữ nguyên kể cả khi `counted_differs`.
- Không phân bổ lại (tiền không đổi). Idempotency, `expected_version` như lệnh V7 khác. Role app chỉ EXECUTE.

Lỗi giữ câu có sẵn: `MONTH_LOCKED`, `VERSION_CONFLICT`, `STALE_SHEET`, `TRIP_PENDING_REVIEW`, `LEGACY_NO_UNIT_PRICE`; thêm `FEE_LINES_CHANGED`, `FEE_TOTAL_CHANGED`.

**Lịch chạy.** `webdebit-ps-snapshot.service` + `.timer` 15 phút một lần, cùng user, env và tài khoản dịch vụ với hai runner hiện có. Nút "↻ Làm mới" (`webdebit-sheet-refresh.service`) thêm `Wants=` runner này. Mỗi lượt 1 yêu cầu Sheets API.

## Nguồn quyết định

- [`PHU-PHI-01`](../docs/decisions.md#phu-phi-01): (5) danh mục; (9) số PS là tiền tính cho khách; (10) Health/KĐ không giá cố định, chỉ nhắc nhập; (11) ô PS số quá nhỏ là gõ sai, không nhập tự động.
- [`SONG-SONG-01`](../docs/decisions.md#song-song-01): Sheet là sổ chính thức tới ngày chuyển hẳn; đối soát theo tổng từng khách.
- [Khóa tháng 24/10/2026](../docs/decisions.md#cập-nhật-khóa-tháng-24102026): tháng khóa chặn mọi lệnh dòng phụ phí.
- [`SO-GON-01`](../docs/decisions.md#so-gon-01): số dư đầu không bị viết lại; không nhãn "sổ gốc".
- [`V7-ID`](../docs/decisions.md#v7-id): người làm từ phiên server.

## Hành vi và bất biến

- **PS không bao giờ đổi tiền.** Mọi lệnh từ PS giữ nguyên tổng phụ phí từng chuyến, tổng tháng, tổng khách và ô TOTAL dòng sổ gốc tới từng đồng. Không phân bổ lại phiếu thu.
- Không ghi khi ghép không duy nhất, có ô gõ sai, số lẻ, ô gộp, tổng lệch, tháng khóa hoặc CHỜ KIỂM.
- Không đè khoản đã phân loại tay mà khác PS: nhánh `TOTAL_DIFF` hoặc mâu thuẫn → người nhập xử lý.
- VND `bigint`, không `float`; NULL khác 0. Cờ NO_BASELINE, chênh 600đ, thiếu giá giữ nguyên.
- Không ghi ngược lên Sheet hay bảng PS. Runner chỉ đọc.

## Khác spec cha

Spec cha (ĐỀ XUẤT 28/10/2026) ghi ba điểm khác. Spec này thay như sau:

1. **"Chuyến chưa có dòng nào → ghi các dòng đúng loại"** đổi thành `WEB_NO_FEE`, chỉ nhắc. Lý do: theo `SONG-SONG-01`, tiền vào web theo Sheet (tab khách). Nếu PS tự cộng tiền thì web có thể lệch Sheet khi tab khách chưa điền, đối soát cuối ngày báo sai. Khi tab khách có phí, "Ghi N giá từ Sheet" đưa tổng lên, sau đó PS tách.
2. **Cờ Health/KĐ lưu bảng `trip_fee_flag`** đổi thành nhắc tính khi đọc sổ, không có bảng hay lệnh "Không tính". Lý do: 6 tháng chỉ có 2 ô bật, không đáng thêm bảng và migration. Nếu số tăng thì làm bảng cờ ở spec sau.
3. **Ghi chú không rõ dòng → cần kiểm** đổi thành gắn vào khoản Điện hoặc khoản đầu tiên. Lý do: ghi chú không phải tiền, không nên chặn việc tách.

Khi spec này được duyệt thì sửa mục tương ứng ở spec cha cho khớp.

## Tiêu chí nghiệm thu

- [ ] Unit bộ đọc PS (dữ liệu giả): tiêu đề sai → lỗi; `1,500,000`, `1500000`, `0`, `1`, `315789.5`, chữ ở Khác, `dd/mm`, `dd/mm/yy`, ngày trống, Health `TRUE`/`Có`/`FALSE`; hash không đổi khi tải lại cùng dữ liệu.
- [ ] Unit ghép: mỗi trạng thái của bảng bước 1 có ít nhất một ca; hai dòng PS cùng một chuyến → `AMBIGUOUS`; Giảm trừ trên web → `TOTAL_DIFF`; khoản Neo đã có, đúng số → giữ, chỉ tách phần còn lại.
- [ ] Harness PostgreSQL `rewrite_trip_fees`: chuyến web và dòng sổ gốc giữ tổng tới từng đồng; dòng sổ gốc có `counted_differs` giữ nguyên `counted_vnd`; `expected_line_ids` lệch → `FEE_LINES_CHANGED`; tổng khác → `FEE_TOTAL_CHANGED`; tháng khóa → `MONTH_LOCKED`; gọi lại cùng khóa → một kết quả; không phân bổ lại; role app chỉ EXECUTE; quét `prosrc` vẫn chỉ `_sync_trip_fee`, `_change_legacy` ghi `other_fee_vnd`.
- [ ] API: chỉ `READY` được ghi; bấm lặp cùng khóa không ghi thêm; hash đổi → `STALE_SHEET`; thiếu bản chụp → `unavailable`.
- [ ] Playwright 1280×720, máy chủ giả: nút đúng số; khung xác nhận ghi "Tổng tiền không đổi"; tách xong các ô cột riêng có số, Thành tiền và tổng còn nợ không đổi; "PS cần xem" đủ các loại; bàn phím; lỗi mạng giữ trạng thái.
- [ ] `npm run check`, `node scripts/check-secrets.js` xanh.
- [ ] Trên `hao` (sau gate SQL): đọc thử bản chụp; số `READY`/cần xem theo khách; số dư từng khách trước = sau một lần tách thật.
- [ ] Người dùng tự đi hết luồng trên bản thử và xác nhận.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`). Review: opus (đường ghi phụ phí, dòng sổ gốc).
- Tách PR:
  - **PR-1 (backend):** `rewrite_trip_fees` trong `tools/v7_backend_functions.sql` + migration mới trong `tools/migrations/`, `tools/v7_ps_snapshot.py`, `web/v7_ps_queue.py`, route trong `web/v7_ledger_api.py`, test Python và harness. Có file `.sql`, nên phải hỏi người dùng trước khi merge, rồi triển khai tay theo runbook.
  - **PR-2 (giao diện):** `so-khach-v7-ui.js`, `so-khach-v7-model.js`, `so-khach-v7-api.js`, test Playwright; mockup HTML dữ liệu giả cho người dùng duyệt trước khi code.
- Ngân sách diff: mỗi PR ≤ 800 dòng logic.
- Lệnh kiểm: `npm run check`; harness `cong-no-web-handoff/tools/test_pg_v7_backend.py` khi sửa SQL.
- Cấm: cộng hoặc đổi tiền từ PS; đổi quy tắc khóa tháng, phân bổ, opening; ghi Sheet; DDL/import trên `hao` ngoài gate runbook; đưa dữ liệu PS thật, tên chủ hàng, Sheet ID vào repo.

## Hoàn tác

Spec: revert commit. Khi đã code: tắt timer runner PS (sổ trả `unavailable`). Các lần tách đã ghi là thao tác giữ tổng, muốn bỏ thì đổi loại lại trong khung chi tiết. Hàm SQL bỏ bằng migration ngược, không đụng dữ liệu.

## Câu hỏi mở

1. **Tháng khóa.** Phần lớn dòng PS có tiền thuộc tháng 5–9, đang khóa. Theo quy tắc khóa 24/10, mỗi tháng phải mở khóa rồi mới tách được. Có cho ngoại lệ "tách giữ tổng tiền làm được ở tháng khóa" không? Mặc định spec: **không**, giữ quy tắc khóa, giao diện nhắc mở khóa. Đây là câu hỏi cho người dùng.
2. **Quyền đọc file bộ lập bill trên `hao`.** Cần kiểm `WEBDEBIT_SHEET_ID` có trỏ đúng file chứa `PS_DATA` không. Nếu không, cần thêm biến `WEBDEBIT_PS_SHEET_ID` và người dùng chia sẻ file (chỉ xem) cho tài khoản dịch vụ. Kiểm trước PR-1.
3. **Gán khách theo "Chủ hàng phí".** Chưa đo tỉ lệ 103 tên ra được sổ qua tên phụ + bảng duyệt tên. Đo chỉ đọc trên `hao` ở PR-1; tỉ lệ thấp thì cân nhắc ghép theo cont trên mọi sổ rồi dùng tên chủ hàng để kiểm chéo.
4. **Ngày đóng phí so với ngày chuyến web** (ngày xe nhập kho): chưa đo độ lệch. Nếu nhiều dòng lệch quá 3 ngày thì xét nới cửa sổ riêng cho PS.
