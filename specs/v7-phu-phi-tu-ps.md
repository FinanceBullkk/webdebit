# V7: phân loại phụ phí theo bảng PS của bộ lập bill

Trạng thái: **ĐỀ XUẤT** (Claude, 29/10/2026); PR-1 backend ĐÃ CODE; migration ĐÃ TRIỂN KHAI trên `hao` 29/10/2026 ([nhật ký](../docs/deploys/2026-10-29-xoa-dc-ps-fee.md)), runner bản chụp PS ĐÃ CÀI cùng ngày (timer 15 phút; quyền đọc `CONT_MASTER` đã có sẵn), chưa có giao diện (mục Tiến độ). Spec con của [`v7-phu-phi-nhieu-loai.md`](v7-phu-phi-nhieu-loai.md), mục "Nhập từ bảng chi phí phát sinh". Chính sách nguồn đã chốt ở [`PHU-PHI-01`](../docs/decisions.md#phu-phi-01) (9)–(11). Nguồn đọc là tab tổng hợp `CONT_MASTER` của bộ lập bill: người dùng xác nhận trong chat 29/10/2026 rằng số PS ở tab này mới đúng, thay cho tab gom thô `PS_DATA`. Giao diện (PR-2): mockup dữ liệu giả [`preview/mockups/tach-phu-phi-ps`](../cong-no-web-handoff/preview/mockups/tach-phu-phi-ps/index.html) **CHỜ DUYỆT** (29/10/2026), chưa code. Spec này đổi ba điểm so với phần ĐỀ XUẤT của spec cha; lý do ở mục [Khác spec cha](#khác-spec-cha).

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720), cùng người dán chuyến và ghi giá từ Sheet hằng ngày. Theo `V7-ID`, mỗi lần ghi mang tên người bấm.

**Bối cảnh:** phụ phí trên web hiện chủ yếu là **Khác** hoặc **Phụ phí ban đầu**. Nguyên nhân: dán lô và "Ghi N giá từ Sheet" chỉ biết tổng ba cột phí của tab khách, còn migration tách loại gom phí cũ thành Phụ phí ban đầu. Bộ lập bill có tab `CONT_MASTER`, mỗi cont (số cont + ngày đóng) một dòng, đã khớp sẵn các bảng chi phí phát sinh vào booking và chia theo Neo, Điện, Ghép, Khác, Bảo hiểm, cờ Health/Kiểm định. Người nhập muốn web biết từng khoản mà không gõ lại.

**Luồng:**
1. Mở sổ khách. Đầu sổ, cạnh "Ghi N giá từ Sheet", có nút **"Tách N phụ phí theo bảng PS"** khi có chuyến tách được.
2. Bấm nút thì mở khung xác nhận ngay dưới đầu sổ (không phải hộp thoại). Mỗi chuyến một dòng gồm cont, ngày và phần trước → sau, ví dụ "Phụ phí ban đầu 2.000.000 → Neo 1.500.000 + Điện 500.000". Cuối khung ghi **"Tổng tiền không đổi"**. Hai nút: **Tách** và **Thôi**.
3. Bấm Tách thì sổ tải lại. Các ô cột riêng (nếu sổ bật Neo/Điện/Ghép) có số, ô Khác giảm tương ứng, tổng còn nợ không đổi. Lịch sử có một dòng "Tách phụ phí theo PS" cho mỗi chuyến, gồm trước → sau và nguồn (khóa cont của bộ lập bill, bảng PS gốc).
4. Những cont không tự tách được nằm ở mục **"PS cần xem: K"**. Bấm vào thì mở danh sách, mỗi dòng ghi lý do và cách xử lý (bảng dưới).
5. Chuyến được PS đánh dấu Health cert hoặc Kiểm định mà chưa có khoản loại đó thì nằm trong "PS cần xem" với lý do "PS đánh dấu Health cert — nhập giá tay". Người nhập ghi khoản trong khung chi tiết phụ phí như hiện nay, sau đó dòng nhắc tự hết.

**Kết quả:** chuyến có số PS trong bộ lập bill được tách đúng loại sau một lần bấm mỗi khách. Không chuyến nào bị đổi tổng tiền.

**Không tự tách:**

| Trường hợp (mã) | Hiện trong "PS cần xem" | Người nhập làm gì |
| --- | --- | --- |
| Khớp đúng 1 chuyến, tổng PS = tổng phụ phí web, web còn khoản chưa phân loại, tháng mở (`READY`) | Không hiện; nằm trong nút "Tách N" | Bấm Tách |
| Như trên nhưng tháng khóa (`MONTH_LOCKED`) | "Tháng 7 đang khóa" | Nút "Mở khóa tháng 7" (ổ khóa có sẵn), sau đó dòng vào nút Tách |
| Tổng khác nhau, web đã có phụ phí (`TOTAL_DIFF`) | "Web 1.500.000 · PS 2.000.000" | Kiểm tab khách trên Sheet (sổ chính thức). Sửa tay trong khung chi tiết nếu web sai |
| Web chưa có phụ phí, PS có (`WEB_NO_FEE`) | "PS 1.500.000 · web chưa có phụ phí" | Ghi phí trên Sheet hoặc web như hiện nay (giá từ Sheet sẽ tự đưa lên); lần sau thành `READY` |
| Khớp nhiều chuyến web (`AMBIGUOUS`) | "Cont … khớp 2 chuyến" | Phân loại tay trong khung chi tiết |
| Bộ lập bill báo lỗi ở dòng cont, ví dụ PS trùng dòng hoặc ngày đóng sai (`PS_SOURCE_ERROR`) | Nguyên văn cột Lỗi của bộ lập bill | Sửa trong bộ lập bill; lần đọc sau tự cập nhật |
| Ô tiền dưới 1.000đ, ví dụ Ghép = 1 (`PS_TYPO`, `PHU-PHI-01` (11)) | "Ghép = 1 trên PS, có thể gõ sai" | Sửa bảng PS hoặc phân loại tay |
| Ô tiền không đọc được (`PS_BAD_AMOUNT`) | "Neo = … không đọc được" | Như trên |
| Ô Health+KĐ gộp có tiền (`PS_COMBINED`) | "PS gộp Health+KĐ 3.000.000, cần tách tay" | Tách tay trong khung chi tiết |
| PS đánh dấu Health/KĐ, chuyến chưa có khoản loại đó (`NEED_HEALTH`, `NEED_KD`) | "PS đánh dấu Health cert — nhập giá tay" | Thêm khoản trong khung chi tiết |
| Đã phân loại khớp PS (`DONE`), hoặc cont không có số PS (`PS_EMPTY`) | Không hiện | — |
| Không ra được khách, hoặc không tìm thấy chuyến (`NO_CUSTOMER`, `NOT_FOUND`) | Chỉ có trong báo cáo, không hiện trên sổ khách | Admin bổ sung tên phụ cho khách |

## Đầu ra

Sổ khách có nút "Tách N phụ phí theo bảng PS". Bấm một lần thì cả lô được tách: mỗi chuyến đổi các khoản Khác / Phụ phí ban đầu thành các khoản đúng loại, **tổng tiền không đổi**. Trường hợp không chắc chắn được liệt kê riêng và không bao giờ tự ghi. Web không cộng tiền từ PS.

## Đối chiếu dữ liệu và code hiện có (bước 2)

**Tab `CONT_MASTER`** (đo chỉ đọc 29/10/2026, chỉ ghi số đếm; dữ liệu ngoài Git). Bộ lập bill tự sinh tab này, ghi chú ở dòng 1 là không sửa tay.
- Dòng 1 là tên nhóm cột, dòng 2 là tiêu đề, dữ liệu từ dòng 3. Có 29 cột theo bốn nhóm: [A] vận hành (booking), [B] tham khảo, [C] nhập tay, trạng thái. Các cột dùng: `Khóa` (`<cont>|<yyyy-mm-dd>`, không trùng), `Số cont`, `Ngày đóng` (`dd/mm/yyyy`), `Tháng bill`, `Chủ hàng`, `Booking`, `PS: số dòng khớp`, `PS Neo`, `PS Điện`, `PS Ghép`, `PS Health+KĐ`, `PS cờ Health`, `PS cờ KĐ`, `PS Khác`, `PS nguồn`, `Bảo hiểm`, `Lỗi`.
- 5.394 cont, tháng bill 11/2025 → 10/2026. 1.877 cont khớp 1 dòng PS, 6 cont khớp 2 dòng (cột Lỗi ghi "PS trùng dòng"), còn lại 0.
- 108 cont có tiền PS, tập trung ở tháng 5–6/2026 (92 cont): Neo 82, Điện 9, Ghép 6 (một ô `1`), Health+KĐ gộp 7, Khác 17. Cờ Health bật 1 (`CÓ`), cờ KĐ chưa bật lần nào.
- Tiền dạng chuỗi có dấu phẩy ngăn nghìn. Cột Khác đã được bộ lập bill làm tròn thành số nguyên (các ô lẻ `315789.5` của bảng PS gốc thành `315,790` / `315,789`), không còn chữ ghi chú.
- `Bảo hiểm` và `Đơn giá` (nhóm nhập tay) hiện trống ở mọi dòng.
- 45 dòng có Lỗi: ngày đóng trống/sai 23, mặt hàng chưa rõ 14, PS trùng dòng 6, ngày đóng lệch tab booking 2.
- So với `PS_DATA` (tab gom thô): 14 dòng PS có tiền không vào `CONT_MASTER` (không khớp booking hoặc trùng cont giữa hai tháng), tổng 33.000.000đ. Web theo `CONT_MASTER` vì đây là số bộ lập bill dùng để làm bill.
- `Chủ hàng` lấy từ booking: cùng kiểu tên với `BOOKING_DATA` mà runner đồng bộ chuyến đã gán sổ, không phải tên tab khách.

**Có sẵn, dùng lại:**
- Đọc Sheet: `tools/v7_sheets_api_reader.py` (Sheets API, `UNFORMATTED_VALUE`), cùng tài khoản dịch vụ `spreadsheets.readonly` với `sheet_sync_runner.py` và `v7_price_snapshot.py`. File chứa `CONT_MASTER` cũng chứa `WEBDEBIT_EXPORT`, `BOOKING_DATA` và bảng duyệt tên khách mà runner đồng bộ chuyến đang đọc. Quyền đọc đã có: kiểm trên `hao` 29/10/2026 đọc được 108 dòng.
- Ghép chuyến: quy tắc của `web/v7_price_queue.py`, dùng cho cả chuyến web lẫn dòng sổ gốc: cùng khách, cùng cont, đúng ngày trước rồi tới lệch ≤ 3 ngày, mỗi đích một dòng nguồn. Tên khách → sổ: tên/tên phụ như hàng chờ giá, cộng bảng duyệt tên khách của runner đồng bộ chuyến (`webdebit_export_connector.parse_review_mapping`). Hàm này nằm ở `tools/`, nên tầng web không được import (`ARCH-02`): runner PS đọc bảng duyệt tên và ghi kèm vào bản chụp, giống cách hàng chờ giá chuyển lõi sang `web/`.
- Phụ phí trên sổ: `get_ledger` trả `fee_lines` (loại, số, ghi chú), `fee_columns`, cờ `has_typed_fee`, `counted_differs`; danh mục ở `get_fee_types()`.
- Bản chụp và nút làm mới: mẫu `prices.json` (hash theo dòng, ghi nguyên tử, mode 600) và [`v7-sheet-refresh`](v7-sheet-refresh.md) (tín hiệu `.path`).
- Giao diện: nút "Ghi N giá từ Sheet", khung xác nhận và "Cần xem" trong `so-khach-v7-ui.js` (`planSheetPrices` trong model).

**Còn thiếu:**
- **Lệnh SQL tách nguyên khối.** Các lệnh hiện có (`add_trip_fees`, `set_trip_fee_type`, `replace_trip_fee`, `void_trip_fee`) mỗi lệnh chỉ đổi một loại hoặc một khoản. Muốn đổi "Phụ phí ban đầu 2.000.000" thành "Neo 1.500.000 + Điện 500.000" thì phải gọi nhiều lệnh. Giữa các lệnh tổng tiền bị đổi tạm, phân bổ chạy lại nhiều lần, và nếu hỏng giữa chừng thì tổng sai. Với dòng sổ gốc còn tệ hơn: mỗi lệnh đi qua `_change_legacy` tính lại ô TOTAL. Khi `counted_differs` bật, TOTAL bị đổi dù tổng phụ phí giữ nguyên.
- Runner bản chụp PS, API hàng chờ, giao diện.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT)

**Bản chụp.** `tools/v7_ps_snapshot.py` đọc `CONT_MASTER!A2:AC20000` và bảng duyệt tên khách bằng một lệnh `values:batchGet` (`UNFORMATTED_VALUE`, `SERIAL_NUMBER`), rồi ghi `/var/lib/webdebit-sheet-sync/ps.json` (`WEBDEBIT_PS_SNAPSHOT_PATH`). File gồm `{created_at, sha256, row_count, rows, customer_aliases}`; hash tính trên các dòng. Runner chỉ giữ dòng có tiền PS, có Bảo hiểm hoặc có cờ Health/KĐ (hiện khoảng 110 dòng). Mỗi dòng có `key`, `source_row`, `container`, `date`, `bill_month`, `owner`, `booking`, `ps_match_count`, `fees: {neo, dien, ghep, khac, bao_hiem}` (VND nguyên hoặc NULL), `combined_vnd`, `health`, `kd` (bool), `ps_source`, `source_error`, `problems: [...]`.

Quy tắc đọc:
- Dòng 2 phải đúng tên các cột dùng ở trên (tìm theo tên, không theo vị trí); thiếu cột thì runner lỗi, không ghi file.
- Tiền: số, hoặc chuỗi chỉ gồm chữ số và dấu phẩy ngăn nghìn. Trống hoặc `0` → NULL. ≥ 1.000 → tiền. Dưới 1.000 → `PS_TYPO`. Số lẻ, số âm hoặc chuỗi khác → `PS_BAD_AMOUNT`. Không tự làm tròn: làm tròn là việc của bộ lập bill.
- `Ngày đóng`: số sê-ri ngày hoặc `dd/mm/yyyy`; không đọc được → NULL kèm `source_error` nếu bộ lập bill chưa báo.
- Cờ: `TRUE`, `CÓ`, `Có` → bật; còn lại → tắt.
- `Lỗi` khác trống → `source_error` giữ nguyên văn.

**Ghép (server, từ bản chụp đúng hash).** Mỗi dòng được gán sổ khách theo `owner`, rồi ghép một đích (chuyến web hoặc dòng sổ gốc) theo quy tắc của hàng chờ giá. `booking` dùng để kiểm chéo khi chuyến web có booking: khác booking thì không ghép. Gọi `ps_total` là tổng các ô tiền (Neo, Điện, Ghép, Khác, Bảo hiểm), `web_total` là tổng `fee_lines` hiệu lực. "Khoản chưa phân loại" là loại Khác, Phụ phí ban đầu hoặc Giảm trừ (đúng nhóm của `FEE_LINES_TYPED`). Trạng thái:
- `READY`: ghép duy nhất, không `source_error`, không `problems`, `ps_match_count` ≤ 1, không gộp Health+KĐ, `ps_total = web_total`, có ít nhất một khoản chưa phân loại, các khoản đã phân loại không mâu thuẫn PS, và kế hoạch sau khác hiện tại.
- Kế hoạch sau: mỗi ô có số thành một khoản đúng loại (Neo, Điện, Ghép, Bảo hiểm; ô Khác thành khoản Khác), ghi chú trống. Các khoản đã phân loại trùng loại và số với PS được giữ nguyên.
- Tháng khóa → `MONTH_LOCKED`; đã khớp → `DONE`; còn lại theo bảng ở bước 1.
- Có Giảm trừ trên web thì tổng web nhỏ hơn PS, nên rơi vào `TOTAL_DIFF`. PS không có giảm trừ.
- Cờ Health/KĐ chỉ tạo `NEED_HEALTH` / `NEED_KD` khi đích chưa có khoản loại đó. Không tạo tiền, không lưu cờ trong DB.

**API.**
- `get_ledger` trả thêm `ps_fees: {snapshot_sha256, ready: [...], review: [...], ready_count, review_count}`. Mỗi mục có `key`, `source_row`, `target_kind`, `target_id`, `month`, `before: [{fee_type_id, amount_vnd, note}]`, `after: [...]`, `ps_total`, `web_total`, `status`, `message`. Thiếu bản chụp thì trả `{unavailable: true}`, sổ vẫn đọc được.
- `POST /api/v7/ps/fees {customer_id, expected_version, snapshot_sha256, idempotency_key}`: server tính lại `READY` từ bản chụp đúng hash; lệch hash thì `STALE_SHEET` ("Bảng PS đã đổi. Tải lại rồi tách."). Mỗi đích một lệnh SQL, khóa con suy từ khóa lô + hash + đích. Trả `{written, skipped, version, complete}`. Hỏng giữa lô không làm sai tiền vì mỗi lệnh giữ tổng; lần sau các đích đã tách thành `DONE`.

**Lệnh SQL mới** `rewrite_trip_fees(customer_id, expected_version, idempotency_key, target jsonb, expected_line_ids jsonb, lines jsonb, source jsonb)`:
- Khóa khách, đọc `_fee_target` (chặn tháng khóa, CHỜ KIỂM, dòng sổ gốc thiếu đơn giá như các lệnh phí khác).
- `expected_line_ids` phải đúng bằng tập khoản hiệu lực hiện tại. Lệch → `FEE_LINES_CHANGED` ("Phụ phí chuyến này vừa đổi. Tải lại rồi tách.").
- `lines`: 1..10 khoản `{fee_type_id, amount_vnd, note}`, kiểm loại, dấu, khác 0 như `_change_trip_fees`. Không chọn được Phụ phí ban đầu. Tổng `lines` phải **bằng** tổng hiện tại, khác → `FEE_TOTAL_CHANGED`.
- Một `event` `rewrite_trip_fees` với trước → sau và `source` (`{kind: 'ps', key, ps_source, snapshot_sha256}`), void các khoản cũ, ghi các khoản mới.
- Chuyến web: gọi `_sync_trip_fee`; tổng không đổi nên không ghi revision. Dòng sổ gốc: **không** gọi `_change_legacy`, vì tổng phụ phí không đổi nên TOTAL (`counted_vnd`) giữ nguyên kể cả khi `counted_differs`.
- Không phân bổ lại (tiền không đổi). Idempotency, `expected_version` như lệnh V7 khác. Role app chỉ EXECUTE.

Lỗi giữ câu có sẵn: `MONTH_LOCKED`, `VERSION_CONFLICT`, `STALE_SHEET`, `TRIP_PENDING_REVIEW`, `LEGACY_NO_UNIT_PRICE`; thêm `FEE_LINES_CHANGED`, `FEE_TOTAL_CHANGED`.

**Lịch chạy.** `webdebit-ps-snapshot.service` + `.timer` 15 phút một lần, cùng user, env và tài khoản dịch vụ với hai runner hiện có. Nút "↻ Làm mới" (`webdebit-sheet-refresh.service`) thêm `Wants=` runner này. Mỗi lượt 1 yêu cầu Sheets API.

## Nguồn quyết định

- [`PHU-PHI-01`](../docs/decisions.md#phu-phi-01): (5) danh mục; (9) số PS là tiền tính cho khách; (10) Health/KĐ không giá cố định, chỉ nhắc nhập; (11) ô PS số quá nhỏ là gõ sai, không nhập tự động.
- Người dùng, chat 29/10/2026: số PS ở tab tổng hợp `CONT_MASTER` mới đúng; web đọc tab này, không đọc `PS_DATA`.
- [`SONG-SONG-01`](../docs/decisions.md#song-song-01): Sheet là sổ chính thức tới ngày chuyển hẳn; đối soát theo tổng từng khách.
- [Khóa tháng 24/10/2026](../docs/decisions.md#cập-nhật-khóa-tháng-24102026): tháng khóa chặn mọi lệnh dòng phụ phí. Người dùng giữ nguyên quy tắc này cho việc tách theo PS (chat 29/10/2026).
- [`SO-GON-01`](../docs/decisions.md#so-gon-01): số dư đầu không bị viết lại; không nhãn "sổ gốc".
- [`V7-ID`](../docs/decisions.md#v7-id): người làm từ phiên server.

## Hành vi và bất biến

- **PS không bao giờ đổi tiền.** Mọi lệnh từ PS giữ nguyên tổng phụ phí từng chuyến, tổng tháng, tổng khách và ô TOTAL dòng sổ gốc tới từng đồng. Không phân bổ lại phiếu thu.
- Không ghi khi ghép không duy nhất, bộ lập bill báo lỗi, có ô gõ sai, ô gộp, tổng lệch, tháng khóa hoặc CHỜ KIỂM.
- Không đè khoản đã phân loại tay mà khác PS: nhánh `TOTAL_DIFF` hoặc mâu thuẫn → người nhập xử lý.
- VND `bigint`, không `float`; NULL khác 0. Cờ NO_BASELINE, chênh 600đ, thiếu giá giữ nguyên.
- Không ghi ngược lên Sheet hay bộ lập bill. Runner chỉ đọc.

## Khác spec cha

Spec cha (ĐỀ XUẤT 28/10/2026) ghi ba điểm khác. Spec này thay như sau:

1. **"Chuyến chưa có dòng nào → ghi các dòng đúng loại"** đổi thành `WEB_NO_FEE`, chỉ nhắc. Lý do: theo `SONG-SONG-01`, tiền vào web theo Sheet (tab khách). Nếu PS tự cộng tiền thì web có thể lệch Sheet khi tab khách chưa điền, đối soát cuối ngày báo sai. Khi tab khách có phí, "Ghi N giá từ Sheet" đưa tổng lên, sau đó PS tách.
2. **Cờ Health/KĐ lưu bảng `trip_fee_flag`** đổi thành nhắc tính khi đọc sổ, không có bảng hay lệnh "Không tính". Lý do: tới nay chỉ 1 cont được đánh dấu, không đáng thêm bảng và migration. Nếu số tăng thì làm bảng cờ ở spec sau.
3. **Đọc bảng PS thô, tự khớp theo cont + ngày đóng, chép ghi chú** đổi thành đọc `CONT_MASTER`. Bộ lập bill đã khớp vào booking, làm tròn số và đánh dấu lỗi; web không làm lại phần này. Ghi chú chữ của bảng PS không có trong `CONT_MASTER`, nên khoản tách ra có ghi chú trống.

Khi spec này được duyệt thì sửa mục tương ứng ở spec cha cho khớp.

## Tiêu chí nghiệm thu

- [ ] Unit bộ đọc (dữ liệu giả): thiếu cột → lỗi; cột đổi chỗ vẫn đọc đúng theo tên; `1,500,000`, `1500000`, `0`, `1`, `315789.5`, chuỗi chữ; ngày sê-ri và `dd/mm/yyyy`; cờ `TRUE`/`CÓ`/`FALSE`; Lỗi khác trống; hash không đổi khi đọc lại cùng dữ liệu.
- [ ] Unit ghép: mỗi trạng thái của bảng bước 1 có ít nhất một ca; `ps_match_count` = 2 → không `READY`; booking khác → không ghép; Giảm trừ trên web → `TOTAL_DIFF`; khoản Neo đã có, đúng số → giữ, chỉ tách phần còn lại; Bảo hiểm có số → khoản Bảo hiểm.
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

## Tiến độ PR-1 backend (29/10/2026, Claude)

**ĐÃ CODE**, chưa merge, chưa triển khai:
- SQL: `rewrite_trip_fees` (+ `_rewrite_trip_fees`) trong `tools/v7_backend_functions.sql`, loại event `rewrite_trip_fees` trong `specs/v7-backend/schema-draft.sql`, migration `tools/migrations/2026-10-29-v7-ps-fee.sql` (sinh từ hai file chuẩn; `tests/test_v7_ps_fee_sql_sync.py` giữ khớp từng byte). Lệnh trả thêm `NO_CHANGE` khi kế hoạch trùng các khoản đang có.
- Runner `tools/v7_ps_snapshot.py`: một lệnh `values:batchGet` đọc `CONT_MASTER` và bảng duyệt tên khách, tìm cột theo tên ở dòng tiêu đề, chỉ giữ dòng có tiền PS, Bảo hiểm hoặc cờ Health/KĐ; hash gồm cả dòng lẫn bảng tên.
- Hàng chờ `web/v7_ps_queue.py` và API: `get_ledger` trả `ps_fees`; `POST /api/v7/ps/fees`. Thêm trạng thái `TYPED_CONFLICT` (web đã phân loại khác PS) và `FEE_TYPE_MISSING` (danh mục thiếu loại) vào "PS cần xem"; `PENDING_REVIEW`, `NOT_FOUND`, `NO_CUSTOMER` không hiện trên sổ.
- Lịch sử sổ khách có nhãn "Tách phụ phí theo PS" (dùng chung câu trước → sau của lệnh phụ phí); nút tách và "PS cần xem" để PR-2.
- Runbook: [mục Tách phụ phí theo bảng PS](../docs/v7-deploy-runbook.md#tách-phụ-phí-theo-bảng-ps--migration--runner-bản-chụp-đã-chạy-trên-hao-29102026).

**ĐÃ KIỂM CHỨNG (máy dev, dữ liệu giả):** harness PostgreSQL 18.6 dùng một lần `test_pg_v7_backend.py`: 66 ca đạt (gồm `PS-FEE.01`: giữ tổng chuyến web và dòng sổ gốc có `counted_differs`, không phân bổ lại, không ghi revision/điều chỉnh sổ gốc, các mã lỗi, quyền), 2 ca bỏ qua cũ (7.11c, 7.15c); `test_pg_v7_grants.py --strict` đạt; `npm run check` đạt. **CÒN MỞ:** chưa đọc `CONT_MASTER` thật bằng tài khoản dịch vụ trên `hao`, chưa thử trên bản sao DB thật.

## Hoàn tác

Spec: revert commit. Khi đã code: tắt timer runner PS (sổ trả `unavailable`). Các lần tách đã ghi là thao tác giữ tổng, muốn bỏ thì đổi loại lại trong khung chi tiết. Hàm SQL bỏ bằng migration ngược, không đụng dữ liệu.

## Câu hỏi mở

1. **Tháng khóa — ĐÃ TRẢ LỜI** (người dùng, chat 29/10/2026: "Giữ khóa tháng"). Không có ngoại lệ: tách phụ phí ở tháng khóa vẫn bị chặn như mọi lệnh dòng phụ phí. Muốn tách thì mở khóa tháng; giao diện có nút "Mở khóa tháng N" trong "PS cần xem". 92/108 cont có tiền PS thuộc tháng 5–6/2026 nên sẽ cần mở khóa hai tháng này.
2. **Quyền đọc file bộ lập bill trên `hao`.** Cần kiểm `WEBDEBIT_SHEET_ID` có trỏ đúng file chứa `CONT_MASTER` không. Nếu không, cần thêm biến `WEBDEBIT_PS_SHEET_ID` và người dùng chia sẻ file (chỉ xem) cho tài khoản dịch vụ. Kiểm trước PR-1.
3. **Gán khách theo `Chủ hàng`.** Chưa đo tỉ lệ tên chủ hàng của 108 cont ra được sổ qua tên phụ + bảng duyệt tên. Đo chỉ đọc trên `hao` ở PR-1; tỉ lệ thấp thì cân nhắc ghép theo cont trên mọi sổ rồi dùng tên chủ hàng để kiểm chéo.
4. **Ngày đóng so với ngày chuyến web** (ngày xe nhập kho): chưa đo độ lệch. Nếu nhiều dòng lệch quá 3 ngày thì xét nới cửa sổ riêng cho PS.
5. **14 dòng PS có tiền không vào `CONT_MASTER`** (33.000.000đ, tháng 5–6): web không thấy các khoản này. Nếu chúng là phí thật thì phải sửa trong bộ lập bill (khớp booking), không sửa ở web.
