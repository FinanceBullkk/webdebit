# V7 — phụ phí nhiều loại: danh mục, dòng phụ phí từng chuyến, cột theo sổ

Trạng thái: chính sách **ĐÃ CHỐT** ở [`PHU-PHI-01`](../docs/decisions.md#phu-phi-01) (người dùng, chat 28/10/2026, gồm (9)–(11) về bảng chi phí phát sinh của bộ lập bill). Thiết kế màn hình và backend trong spec này là **ĐỀ XUẤT** (Claude, 28/10/2026). Chưa có mockup Penpot, chưa code, chưa đổi schema.

Bản xem: canvas Design "Phụ phí hướng C" (riêng tư, của người dùng; 2 màn: sổ khách và cài đặt loại phụ phí; DỮ LIỆU GIẢ). Bản xem lệch spec ở bốn chỗ, Penpot phải theo spec: chưa áp khóa tháng 24/10; còn nhãn "sổ gốc" dưới container (bỏ theo [`SO-GON-01`](../docs/decisions.md#so-gon-01)); danh mục và cột mặc định là dữ liệu giả; còn phần gán cột `G H I` (bỏ theo `PHU-PHI-01` (8)).

## Vì sao đổi

Mỗi chuyến hiện chỉ có **một số phụ phí** (`trip_price_rev.other_fee_vnd`, cộng các `adjustment` có `field='other_fee_vnd'`). Thực tế có nhiều loại (neo, điện, ghép, health, kiểm định, bảo hiểm…). Tab khách trên Sheet có ba cột phí (`G H I`, tiêu đề chung "OTHER FEE"/"PHU PHI", không có nghĩa cố định) và khi nạp được cộng thành một số, nên không biết số đó gồm khoản gì. Thêm cột cố định cho mọi loại làm bảng quá rộng, phần lớn ô trống.

Hướng C: **danh mục loại phụ phí** dùng chung + **dòng phụ phí** từng chuyến (một chuyến nhiều dòng) + **mỗi sổ chọn tối đa 3 loại hiện thành cột riêng**, còn lại gộp vào cột **Khác**.

## Người dùng và luồng (bước 1)

Người nhập trên 40 tuổi, nhập theo lô, một lô một khách, 10–50 container/ngày, màn 1280×720 ([UX](../docs/ux-guidelines.md)). Thường dán từ tab khách trên Sheet; phụ phí hay đến sau khi xe đã nhập.

| Việc | Thao tác | Số thao tác |
| --- | --- | --- |
| Ghi phụ phí loại có cột riêng | Bấm ô cột riêng → gõ số → Enter | **1** |
| Ghi phụ phí loại khác | Bấm ô **Khác** → khung bên phải mở → chọn loại, gõ số, ghi chú (tùy) → **Thêm** | **3** |
| Xem phụ phí gồm những gì | Bấm ô **Khác** (khung hiện mọi dòng, kể cả loại có cột riêng) | **1** |
| Phân loại khoản dán từ Sheet (đang là Khác) | Trong khung, chọn loại mới ở ô loại của dòng | **1** |
| Sửa số một khoản | Trong khung, bấm ô số tiền của dòng → gõ đè → Enter | **1** |
| Xóa một khoản | Trong khung, bấm thùng rác của dòng | **1** |
| Một khoản cho cả lô | Đánh dấu các chuyến → **Thêm một khoản phụ phí cho N chuyến** → chọn loại, số tiền → **Thêm cho N chuyến** | **3 + số chuyến đánh dấu** |
| Phí theo lô/tháng không gắn container | Dòng phí lẻ như hiện nay (để trống container, đơn giá) → khung phụ phí của dòng đó → chọn loại, số tiền | như dòng phí lẻ + **3** |
| Dán lô từ Sheet | Như [`v7-nhap-kieu-sheet.md`](v7-nhap-kieu-sheet.md); mỗi ô phí có số thành một dòng **Khác** | không đổi |
| Chọn cột riêng cho sổ | Cài đặt loại phụ phí → bật/tắt **Cột riêng trên sổ này** | **1 mỗi loại** |
| Thêm loại mới | Cài đặt loại phụ phí → gõ tên, chọn tính chất → **Thêm loại** | **3** |

Bị chặn: tháng khóa (mục Hành vi), số tiền không đọc được, bằng 0 hoặc sai dấu, loại trùng tên, cột riêng thứ tư.

## Đầu ra

- Sổ khách có cụm cột **PHỤ PHÍ** = các cột riêng của sổ (0–3) + **Khác**; dòng Tổng tháng có tổng từng cột. Thành tiền = đơn giá + tổng mọi dòng phụ phí.
- Khung **Chi tiết phụ phí** bên phải: dòng phụ phí của chuyến (loại, số tiền, ghi chú, nhãn "cột riêng" / "chi hộ"), tổng, form thêm; đổi loại, sửa số, xóa từng dòng; chế độ áp cho nhiều chuyến.
- Màn **Cài đặt loại phụ phí**: danh mục, tính chất (phí dịch vụ / chi hộ), số chuyến đang dùng ở sổ này, bật cột riêng (tối đa 3), thêm loại, đổi tên, ngừng dùng.
- Backend lưu từng dòng phụ phí, mọi thao tác ghi Lịch sử trước → sau và người làm; tổng tiền, phân bổ, số dư như hiện nay.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Phần | Hiện có | Dùng được / thiếu |
| --- | --- | --- |
| Lưu phụ phí | `trip_price_rev.other_fee_vnd` (một số, NULL được) + `adjustment(field='other_fee_vnd')` | Thiếu loại, ghi chú, nhiều dòng |
| Tính tiền | `v_trip_current`: có đơn giá → giá + `coalesce(fee,0)`; dòng phí lẻ không container → `other_fee_vnd` | Giữ công thức, thay `fee` bằng tổng dòng |
| Ghi | `paste_trips`, `edit_trip_price`, `adjust_trip`, `edit_legacy_trip(field='other_fee_vnd')`, `delete_trip` (chụp phí hiệu quả) | Cần lệnh dòng phụ phí; các lệnh cũ phải đi qua dòng |
| Nạp Sheet | `v7_load_real_copy.py`: cột tiêu đề bắt đầu "OTHER FEE"/"PHU PHI" → cộng thành `fee` | Giữ đọc từng ô để tách thành từng dòng |
| Ghi giá từ Sheet | [`v7-price-queue.md`](v7-price-queue.md): ghi tổng phụ phí; phí âm → `MANUAL` | Ghi theo dòng; phí âm thành dòng Giảm trừ |
| So giá | [`v7-price-match.md`](v7-price-match.md): so phụ phí tổng; dòng sổ gốc so `counted_vnd` | So theo tổng, không đổi |
| Dòng sổ gốc | `legacy_row` + `_legacy_current` (có trường phụ phí đọc từ `fee_vnd` lúc nạp); sửa qua `_change_legacy`, phần chênh so với bản mốc chỉ ghi Lịch sử (`SO-GON-01`) | Thêm dòng phụ phí trên cùng cơ chế phần chênh |
| Giao diện | `so-khach-v7-ui.js`, `so-khach-v7-model.js` (`tripAmount`), `so-khach-v7-api.js`: một ô Phụ phí | Cụm cột, khung chi tiết, màn cài đặt |
| Tổng quan, ma trận phải thu | `get_dashboard`, `get_receivables_*` đọc tổng chuyến | Không đổi |

## Nguồn quyết định

- [`PHU-PHI-01`](../docs/decisions.md#phu-phi-01): hướng C và tám điểm chốt ngày 28/10/2026.
- [`V7-BE`](../docs/decisions.md#v7-be): có đơn giá thì phụ phí trống tính 0; thiếu đơn giá vẫn chưa biết.
- [Cập nhật khóa tháng 24/10/2026](../docs/decisions.md#cập-nhật-khóa-tháng-24102026): tháng khóa, bảng chuyến chỉ đọc; muốn sửa thì mở khóa.
- [`NHAP-SHEET-01`](../docs/decisions.md#nhap-sheet-01) (7): dán chuyến mới vào tháng khóa được.
- [`SO-GON-01`](../docs/decisions.md#so-gon-01): không nhãn "sổ gốc"; phần chênh dòng sổ gốc chỉ ghi Lịch sử.
- [`SONG-SONG-01`](../docs/decisions.md#song-song-01): Sheet là sổ chính thức tới ngày chuyển hẳn; đối soát theo tổng từng khách.

## Hành vi và bất biến

**Danh mục.** Một danh mục dùng chung mọi sổ. Mỗi loại: tên (duy nhất, không phân biệt hoa thường), tính chất `dịch vụ` hoặc `chi hộ`, dấu số tiền, trạng thái dùng/ngừng. Danh mục ban đầu (`PHU-PHI-01` (5)), theo đúng thứ tự cột phí trên bill gửi khách của bộ lập bill: **Neo, Điện, Ghép, Bảo hiểm, Kiểm định, Health cert** (tính chất dịch vụ, số dương; người dùng tự đổi sang chi hộ trong cài đặt). Thứ tự này là thứ tự hiện trong khung chi tiết và gợi ý thứ tự cột riêng. Ba loại hệ thống, không xóa, không đổi tên:

- **Khác** (cột "Other fee" trên bill): số dương; nơi vào của ô phí dán từ Sheet.
- **Giảm trừ**: chỉ nhận **số âm** (`PHU-PHI-01` (4)); nơi vào của ô phí âm dán từ Sheet.
- **Phụ phí ban đầu**: số khác 0; chỉ do migration tạo (phụ phí đã có trước khi tách loại), không chọn được cho dòng mới; dòng loại này đổi loại, sửa số, xóa được như dòng khác.

Ngừng dùng một loại thì không chọn được cho dòng mới; dòng cũ giữ nguyên. Đổi tên không đổi số.

**Cột riêng theo sổ.** Mỗi sổ chọn 0–3 loại, có thứ tự; mặc định **0** — chỉ có cột Khác (`PHU-PHI-01` (6)). Bỏ cột riêng không mất số: các dòng của loại đó hiện ở cột Khác. Đổi cột riêng chỉ đổi cách hiện, không phải thao tác tiền; vẫn ghi Lịch sử của sổ.

**Dòng phụ phí.** Mỗi dòng: chuyến (hoặc dòng sổ gốc), loại, số tiền VND nguyên khác 0 đúng dấu của loại, ghi chú tùy chọn. Một chuyến có nhiều dòng, kể cả nhiều dòng cùng loại. Không sửa đè dòng đã ghi: đổi loại, sửa số hoặc ghi chú = bỏ dòng cũ + ghi dòng mới trong **một lệnh**; xóa = đánh dấu bỏ, vẫn giữ trong Lịch sử.

**Tiền.** Phụ phí của chuyến = tổng các dòng còn hiệu lực (Giảm trừ làm giảm). Không có dòng nào thì phụ phí **trống** (không phải 0); theo `V7-BE`, có đơn giá thì tính 0. Thiếu đơn giá: chuyến vẫn ngoài số dư, cờ thiếu giá giữ nguyên; dòng phụ phí vẫn ghi được và hiện, chưa cộng. Dòng phí lẻ không container, không đơn giá: tiền = tổng dòng (`PHU-PHI-01` (3)). Thành tiền âm (giảm trừ lớn hơn giá + phí) là hợp lệ về tính toán, ô tô vàng cảnh báo, không chặn. Mỗi lệnh đổi tiền phân bổ lại phiếu chưa hủy theo nợ cũ trước (`V7-SO`).

**Ô cột riêng.** Hiện tổng các dòng của loại đó. Gõ số mới → một lệnh "đặt loại X = số": bỏ mọi dòng hiệu lực loại X ở chuyến đó, ghi một dòng số mới (ghi chú trống). Xóa trắng ô → bỏ mọi dòng loại X. Chuyến có nhiều dòng loại X: ô vẫn sửa được, Lịch sử ghi đủ các dòng bị thay.

**Ô Khác.** Hiện tổng các dòng không có cột riêng + nhãn "n khoản", hoặc "+ thêm" khi chưa có. Bấm → mở khung chi tiết của chuyến, viền xanh ô đang mở.

**Khung chi tiết.** Mỗi dòng: ô chọn loại (đổi là lưu), số tiền (bấm để sửa, Enter lưu, Esc trả lại), ghi chú, nhãn "cột riêng" nếu loại đó có cột riêng ở sổ này, "chi hộ" nếu loại là chi hộ, nút xóa. Dưới cùng: tổng phụ phí, form thêm. Chi hộ chỉ là nhãn, vẫn cộng nợ (`PHU-PHI-01` (1)).

**Áp cho nhiều chuyến.** Đánh dấu bằng ô chọn đầu dòng (chuyến ở tháng đang mở). Thanh trên bảng: "Đã chọn N chuyến · Thêm một khoản phụ phí cho N chuyến · Bỏ chọn". Thêm = **một lệnh**, mỗi chuyến một dòng cùng loại, cùng số, cùng ghi chú; tất cả vào hoặc không chuyến nào. Xong thì bỏ chọn, báo "Đã thêm <loại> <số> cho N chuyến".

**Tháng khóa** (quyết định 24/10/2026). Ô cột riêng chỉ đọc; khung chi tiết vẫn mở để xem, ẩn form thêm, ô loại/số và nút xóa thành chỉ đọc, hiện "Tháng đã khóa — mở khóa tháng để sửa phụ phí". Chuyến tháng khóa không đánh dấu được. Ngoại lệ: chuyến mới dán vào tháng khóa (`NHAP-SHEET-01` (7)) mang theo dòng phụ phí từ vùng dán.

**Dán từ Sheet** (`PHU-PHI-01` (8)). Ba cột phí không có nghĩa cố định. Mỗi ô phí có số thành **một dòng**: số dương → **Khác**, số âm → **Giảm trừ**, ghi chú trống. Ô trống thì không có dòng. Ô phí không đọc được vẫn là lỗi tại ô như hiện nay. Hàng nháp hiện ô Khác như dòng đã lưu. Phân loại làm sau trong khung chi tiết.

**Ghi giá từ Sheet** ([`v7-price-queue`](v7-price-queue.md)). Sheet là sổ chính thức trong lúc chạy song song, nên so **tổng phụ phí** của Sheet (cộng các ô phí) với tổng các dòng trên web:

- Bằng nhau → không ghi gì (phân loại trên web giữ nguyên).
- Web chưa có dòng nào → ghi các dòng như khi dán (dương → Khác, âm → Giảm trừ). Phí âm không còn là `MANUAL`.
- Khác nhau và web đã có dòng → `MANUAL`, hiện cả hai tổng; người nhập sửa dòng trên web. Không tự đè phân loại đã làm.

**Nhập từ bảng chi phí phát sinh (PS) của bộ lập bill** (ĐỀ XUẤT, làm ở spec con riêng sau phần lõi). Bộ lập bill có bảng gom chi phí phát sinh từng cont theo tháng, khớp vào booking theo số cont + ngày đóng, đã chia sẵn theo loại (Neo, Điện, Ghép, cờ Health, cờ Kiểm định, ghi chú). Số trong đó là **tiền tính cho khách** (`PHU-PHI-01` (9)). Web đọc bảng này (chỉ đọc, như hàng chờ giá từ Sheet) để **phân loại**, không để cộng thêm tiền, vì tab khách trên Sheet (sổ chính thức khi chạy song song) đã có các số này trong ba cột phí:

- Khớp chuyến web theo số cont + ngày đóng và sổ khách (tên chủ hàng trong bảng PS có mã kèm theo, cần bảng đối chiếu tên như [`v7-customer-name-mapping.md`](v7-customer-name-mapping.md)). Không khớp hoặc khớp nhiều chuyến → danh sách cần kiểm, không ghi.
- Ô tiền Neo, Điện, Ghép: bỏ ô trống và ô 0. Ô có số nhỏ hơn 1.000đ (ví dụ Ghép = "1") là **nhập sai** (`PHU-PHI-01` (11)) → danh sách cần kiểm, không ghi.
- So **tổng phụ phí** của chuyến trên web với tổng các ô tiền PS:
  - Chuyến chưa có dòng nào → ghi các dòng đúng loại.
  - Tổng bằng nhau và chuyến còn dòng Khác → thay các dòng Khác bằng các dòng đúng loại trong một lệnh; tổng chuyến không đổi.
  - Tổng bằng nhau và đã phân loại → không làm gì.
  - Khác nhau → `MANUAL`, hiện cả hai bên; người nhập xử lý tay. Không tự đổi tiền.
- Cột ghi chú của bảng PS (chữ, ví dụ giải thích số giờ chạy điện) thành ghi chú của dòng tương ứng; không rõ dòng nào thì ghi vào dòng Điện nếu có, không thì hiện trong danh sách cần kiểm.
- **Health cert, Kiểm định** (`PHU-PHI-01` (10)): bảng PS chỉ có ô đánh dấu (TRUE/FALSE/"Có") và một cột tiền gộp không dùng được. Web **không tạo tiền** từ đây; chỉ gắn **cờ "cần nhập Health cert" / "cần nhập Kiểm định"** cho chuyến. Bộ lập bill có ô "Không tính Health cert / kiểm định" theo cont: đánh dấu thì không gắn cờ.

**Cờ cần nhập phí.** Chuyến có cờ thì ô Khác hiện nhãn cam "cần Health" / "cần KĐ"; khung chi tiết hiện dòng nhắc kèm nút điền nhanh loại đó vào form. Cờ tự hết khi chuyến có dòng của loại đó; người nhập cũng bỏ cờ được ("Không tính"), ghi Lịch sử. Cờ không phải tiền, không chặn số dư; đầu sổ đếm "n chuyến cần nhập phí" cạnh số chuyến thiếu giá.

**Dữ liệu cũ.** Khi triển khai, phụ phí hiệu quả hiện tại của mỗi chuyến web (`other_fee_vnd` của bản giá mới nhất + tổng `adjustment` phí, đúng công thức `delete_trip` dùng) và của mỗi dòng sổ gốc (`_legacy_current`) thành **một dòng "Phụ phí ban đầu"**. Phụ phí trống thì không có dòng. Tổng tiền từng chuyến, từng tháng, từng khách phải **không đổi tới từng đồng**. Đây là migration riêng có gate (mục Phạm vi agent), không chạy từ spec này.

**Dòng sổ gốc** (`PHU-PHI-01` (7)). Có dòng phụ phí như chuyến web: thêm, đổi loại, sửa, xóa. Số dư đầu **không bị viết lại**: tổng mới của dòng sổ gốc đi qua cơ chế phần chênh so với bản mốc hiện có (`_change_legacy`), phần chênh chỉ ghi Lịch sử (`SO-GON-01`). Không có nhãn "sổ gốc" trên dòng hay trong khung.

**Gửi khách** (`PHU-PHI-01` (2)). Khi làm phiếu/bảng đối soát gửi khách, mỗi chuyến liệt kê từng dòng phụ phí (loại, số tiền, ghi chú). Spec này chỉ bảo đảm dữ liệu đủ cho việc đó; phiếu gửi khách là spec riêng.

**Bất biến.** VND `bigint`, không `float`. NULL khác 0, ngoài ngoại lệ `V7-BE`. Opening và lịch sử trong opening không cộng lại. Mọi thao tác dòng phụ phí ghi `event` (người làm, trước → sau, chuyến, loại, số). Idempotency key + `expected_version` như các lệnh V7 khác. Cờ NO_BASELINE, chênh 600đ, thiếu giá giữ nguyên. Đối soát với Sheet theo tổng từng khách không đổi.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT cho Codex)

Tên bảng, tên hàm là đề xuất; Codex chốt khi viết spec backend, reviewer Claude duyệt.

| Thành phần | Đề xuất |
| --- | --- |
| Bảng `fee_type` | `id`, `name` (unique theo `lower`), `kind` (`service`/`pass_through`), `sign` (`positive`/`negative`/`any`), `system_key` (`khac`/`giam_tru`/`ban_dau`/NULL), `active`, `sort` |
| Bảng `book_fee_column` | `customer_id`, `fee_type_id`, `position` 1..3, unique cả hai chiều |
| Bảng `trip_fee_line` | `id`, `customer_id`, đúng một trong `trip_id` / `legacy_row_id`, `fee_type_id`, `amount_vnd bigint CHECK (amount_vnd <> 0)` + kiểm dấu theo `fee_type.sign` trong hàm, `note`, `created_by_event`, `voided_by_event` NULL; chỉ thêm, `voided_by_event` đặt một lần |
| Bảng `trip_fee_flag` | `customer_id`, đúng một trong `trip_id` / `legacy_row_id`, `fee_type_id`, `source` (`ps`/`manual`), `created_by_event`, `cleared_by_event` NULL, `clear_reason` (`has_line`/`not_charged`); không phải tiền |
| `v_trip_current` | `fee` = tổng dòng chưa bỏ, NULL khi không có dòng; công thức `amount_vnd` giữ nguyên |
| `add_trip_fees(customer_id, expected_version, idempotency_key, targets jsonb, fee_type_id, amount_vnd, note)` | 1..N chuyến/dòng sổ gốc cùng khách; một mục ở tháng khóa → `MONTH_LOCKED`, cả lệnh không vào; một lần phân bổ lại |
| `set_trip_fee_type(customer_id, expected_version, idempotency_key, target, fee_type_id, amount_vnd NULL)` | Ô cột riêng: bỏ mọi dòng loại đó, ghi một dòng mới nếu `amount_vnd` có |
| `replace_trip_fee(customer_id, expected_version, idempotency_key, fee_line_id, fee_type_id, amount_vnd, note)` | Đổi loại / sửa số / sửa ghi chú: bỏ dòng cũ, ghi dòng mới |
| `void_trip_fee(customer_id, expected_version, idempotency_key, fee_line_id)` | Xóa một dòng |
| `paste_trips` | Mỗi hàng nhận `fees: [amount_vnd, …]` (các ô phí có số); hàm tạo dòng Khác/Giảm trừ theo dấu; còn nhận `other_fee_vnd` cũ thì coi là một ô (tương thích trong lúc chuyển) |
| `edit_trip_price`, `adjust_trip` (phần phí), `edit_legacy_trip(field='other_fee_vnd')` | Không ghi một số phụ phí nữa; Codex chọn bỏ tham số phí hay chuyển thành `set_trip_fee_type(Khác)`, ghi rõ trong spec backend |
| `delete_trip`, `delete_legacy_trip` | Chụp danh sách dòng phụ phí vào Lịch sử |
| `clear_trip_fee_flag(customer_id, expected_version, idempotency_key, flag_id)` | Người nhập bỏ cờ "Không tính"; cờ cũng tự hết trong các lệnh ghi dòng của loại đó |
| Nhập từ bảng PS | Spec con riêng: đọc chỉ đọc như `v7_sheet_queue` / `v7_price_queue`, ra danh sách đề xuất (ghi mới / phân loại lại / gắn cờ / cần kiểm); người nhập bấm áp, mỗi chuyến một lệnh `replace`/`add`/cờ |
| `get_ledger` | Mỗi chuyến/dòng sổ gốc thêm `fee_lines: [{id, fee_type_id, amount_vnd, note}]` và `fee_flags: [{id, fee_type_id}]`; sổ thêm `fee_columns`; danh mục ở route riêng |
| Danh mục, cài đặt sổ | `add_fee_type(name, kind)`, `rename_fee_type`, `set_fee_type_kind`, `set_fee_type_active`, `set_book_fee_columns(customer_id, expected_version, idempotency_key, fee_type_ids[])` (≤ 3); ghi `event`, không đổi tiền |
| HTTP | `POST /api/v7/trips/fees/add`, `/fees/set`, `/fees/replace`, `/fees/void`; `GET /api/v7/fee-types`; `POST /api/v7/fee-types`, `/fee-types/update`; `POST /api/v7/books/fee-columns` |
| Lỗi | `MONTH_LOCKED` "Tháng đã khóa — mở khóa tháng để sửa phụ phí"; `FEE_AMOUNT_INVALID` "Nhập số tiền khác 0"; `FEE_SIGN_INVALID` "Giảm trừ nhập số âm" / "Loại này nhập số dương"; `FEE_TYPE_INACTIVE`; `FEE_TYPE_SYSTEM` "Không chọn được loại này cho khoản mới"; `FEE_TYPE_DUPLICATE` "Đã có loại …"; `FEE_COLUMNS_MAX` "Mỗi sổ tối đa 3 cột riêng"; `VERSION_CONFLICT` như hiện nay |

## Ngoài phạm vi

- Phiếu/bảng đối soát gửi khách (yêu cầu hiện từng khoản đã chốt, làm ở spec riêng).
- Bảng giá phụ phí mặc định theo khách (tự điền số).
- Báo cáo theo loại phí; tách chi hộ khỏi doanh thu (chốt: chỉ là nhãn).
- Thay đổi tổng quan và ma trận phải thu (đọc tổng, không đổi).
- Ghi ngược lên Sheet.

## Tiêu chí nghiệm thu

Backend (Codex, DB test dùng một lần):

- [ ] Migration dữ liệu cũ trên bản sao: tổng tiền từng chuyến, dòng sổ gốc, tháng, khách trước = sau tới từng đồng; phụ phí trống không có dòng; chạy lại lần hai không đổi gì.
- [ ] Có đơn giá, không dòng → phụ phí tính 0, lưu trống; thiếu đơn giá + có dòng → ngoài số dư, cờ thiếu giá; dòng phí lẻ → tổng dòng. So với `tripAmount` của model.
- [ ] `add_trip_fees` 20 chuyến: một lệnh, 20 dòng, một lần phân bổ lại; một chuyến ở tháng khóa → `MONTH_LOCKED`, không dòng nào vào.
- [ ] `set_trip_fee_type` thay đúng mọi dòng cùng loại; xóa trắng bỏ hết; `replace_trip_fee` đổi loại giữ tổng; Lịch sử có trước → sau.
- [ ] Gọi lại cùng key → một kết quả; khác key trên dòng đã bỏ → lỗi.
- [ ] Số tiền 0, sai dấu theo loại, tràn `bigint`, không phải số → từ chối; loại hệ thống "Phụ phí ban đầu" không chọn được cho dòng mới.
- [ ] Dán lô: ô dương → Khác, ô âm → Giảm trừ; `other_fee_vnd` cũ → một dòng.
- [ ] Dòng sổ gốc: thêm/xóa khoản đổi tổng đúng, số dư đầu không đổi, phần chênh ghi Lịch sử.
- [ ] Ghi giá từ Sheet: tổng bằng → không ghi; web chưa có dòng → ghi dòng; khác và đã có dòng → `MANUAL`.
- [ ] Tháng khóa: mọi lệnh dòng phụ phí bị chặn, trừ dòng đi theo chuyến mới dán vào tháng khóa.
- [ ] `delete_trip` / `delete_legacy_trip` chụp danh sách dòng; phân bổ lại đúng.
- [ ] Cờ cần nhập: ghi dòng Health cert → cờ Health tự hết; bỏ cờ tay ghi Lịch sử; cờ không đổi số dư.
- [ ] Nhập từ bảng PS (spec con): chuyến chưa có dòng → dòng đúng loại; tổng bằng + còn Khác → phân loại lại, tổng chuyến không đổi; tổng khác → `MANUAL`; Ghép = 1 → cần kiểm; Health/KĐ đánh dấu → chỉ gắn cờ, không tạo tiền; "không tính" → không cờ.
- [ ] Quyền: role app chỉ EXECUTE hàm, không DML bảng mới.

Frontend (Gemini, sau khi Penpot được duyệt):

- [ ] Sổ mặc định chỉ có cột Khác; ba cột riêng: bảng 1280×720 không cuộn ngang.
- [ ] Gõ ô cột riêng + Enter → lưu, Thành tiền và Tổng tháng đổi đúng; Esc trả lại.
- [ ] Bấm Khác → khung đúng chuyến; thêm, đổi loại, sửa số, xóa dòng; tổng khung = cột riêng + Khác.
- [ ] Dán 3 hàng có ô phí dương và âm → dòng Khác và Giảm trừ; đổi loại một dòng Khác → sang đúng cột riêng nếu có.
- [ ] Đánh dấu 5 chuyến → thêm một khoản → 5 dòng; bấm lặp nút Thêm không tạo trùng.
- [ ] Tháng khóa: ô chỉ đọc, khung không có form, không đánh dấu được.
- [ ] Cài đặt: bật cột thứ tư bị tắt kèm lý do; bỏ cột riêng → số sang Khác, Thành tiền không đổi; loại hệ thống không xóa/đổi tên được.
- [ ] Bàn phím: Tab tới ô chọn, ô cột riêng, nút Khác, các ô trong khung; khung đóng bằng nút Đóng; mất mạng → báo lỗi, không mất số đang gõ.
- [ ] Không có chữ "sổ gốc" trên màn sổ.
- [ ] Người dùng tự đi hết luồng trên bản thử và xác nhận.
- [ ] Giao diện khớp đúng phiên bản Penpot đã duyệt.

## Phạm vi agent

Spec này là spec tổng; giao việc bằng hai spec con theo [`_template.md`](_template.md): backend + migration (Codex) trước, frontend (Gemini) sau khi Penpot được duyệt.

- Agent: codex (backend + migration dữ liệu cũ), gemini (frontend)
- Mockup: ĐÃ DUYỆT — bản xem HTML dữ liệu giả [`preview/mockups/phu-phi-nhieu-loai`](../cong-no-web-handoff/preview/mockups/phu-phi-nhieu-loai/index.html), người dùng duyệt trong chat 29/10/2026 ("Duyệt, code luôn"); chưa qua Penpot, như các vòng mockup HTML khác
- Review: opus (đổi đường ghi tiền, phân bổ, migration dữ liệu)
- Được sửa (dự kiến, chốt ở spec con): `cong-no-web-handoff/tools/v7_backend_functions.sql`, `specs/v7-backend/schema-draft.sql`, migration mới trong `cong-no-web-handoff/tools/migrations/`, `cong-no-web-handoff/web/v7_ledger_api.py`, `cong-no-web-handoff/web/v7_price_queue.py`, `cong-no-web-handoff/tools/v7_load_real_copy.py`, `cong-no-web-handoff/preview/so-khach-v7-*.js`, `so-khach-v7-live.html`, test tương ứng
- Lệnh kiểm: `npm run check`; DB test qua harness PostgreSQL dùng một lần (`cong-no-web-handoff/tools/test_pg_v7_backend.py`)
- Cấm: chạy DDL, migration hay import lên `hao` hoặc DB thật; đổi quy tắc khóa tháng, phân bổ, opening; ghi dữ liệu khách thật vào repo.

## Hoàn tác

Spec: revert commit. Khi đã code: migration có bước ngược (gộp dòng về một số phụ phí, kiểm tổng bằng nhau trước khi xóa bảng mới); không đụng `legacy_row` gốc, opening.

## Bằng chứng

Giao diện (29/10/2026, Claude): ĐÃ CODE theo mockup đã duyệt (`so-khach-v7-fee-ui.js` + cụm cột trong `so-khach-v7-ui.js`, hàm tính hiển thị trong `so-khach-v7-model.js`); ĐÃ KIỂM CHỨNG bằng `npm run check` (unit model/API, Playwright máy chủ giả `test-so-khach-v7-fee-browser.js`). Hai phần chưa làm: dán lô vẫn gửi một ô phụ phí (backend tạo một khoản Khác, chưa tách G/H/I thành từng khoản); cờ "cần nhập Health/KĐ" chờ spec nhập bảng PS. Chưa thử tay trên sổ thật.

## Câu hỏi mở (kỹ thuật, Codex trả lời trong spec backend)

1. Trường phụ phí của dòng sổ gốc: `_legacy_current` đọc từ đâu, có tách được khỏi `counted_vnd` cho mọi dòng không; dòng không tách được thì migration làm gì.
2. Tham số phụ phí của `edit_trip_price` / `adjust_trip` / `edit_legacy_trip`: bỏ hay chuyển thành `set_trip_fee_type(Khác)`; ảnh hưởng tới `v7-price-queue` và test hiện có.
3. Lịch sử: một `event` cho cả lệnh áp lô hay một `event` mỗi chuyến; hiển thị trong Lịch sử sổ thế nào cho gọn.
4. Bảng PS: các tab tháng đầu đọc vùng khác các tab sau và ghi ngày đóng phí không có năm; Bảo hiểm nằm ở bảng nhập giá của bộ lập bill chứ không ở bảng PS — có đọc luôn không. Trả lời trong spec con nhập từ PS.
