# Thiết kế backend sổ khách V7 (ĐỀ XUẤT — bản nháp 1)

Trạng thái: **ĐỀ XUẤT** (bản nháp gốc 19/10/2026; sửa theo quyết định 20/10/2026). Là bước 3 trong [spec backend](../v7-backend-so-khach.md) mục 6. [Schema](schema-draft.sql), [thân hàm](../../cong-no-web-handoff/tools/v7_backend_functions.sql) và [harness](../../cong-no-web-handoff/tools/test_pg_v7_backend.py) đã có; Claude báo run10 trên container giả còn lỗi 7.05b/7.14b trước vòng sửa này. Chưa chạy lại PostgreSQL, chưa kiểm dữ liệu thật, chưa là migration hay nghiệm thu ghi tiền. Không đụng `hao` hoặc Sheet.

Quyết định người dùng đã chốt mà thiết kế này dựa vào (19/10/2026): không có duyệt, nhập là tính nợ; ổ khóa từng tháng (không quy tắc ngày 5, không ghi vết mở/khóa); điều chỉnh không cần lý do và tính tiền ngay; điều chỉnh/sửa giá/dán lô/sửa ngày phiếu thì phân bổ lại thu theo nợ cũ trước (xếp theo ngày phiếu rồi mã phiếu), hủy phiếu thì không phân bổ lại; hủy phiếu bắt buộc lý do; khách trả dư ghi trong sổ và hiện số âm; mỗi người một danh tính Tailscale; V7 là màn một khách. Nguồn hành vi chuẩn: `so-khach-v7-model.js` + 40 test (bản thử trong tab).

## 1. Nguyên tắc

1. **Không sửa đè sự thật đã ghi.** Mọi thay đổi tiền là một **sự kiện** chỉ-thêm (`event`) kèm dữ liệu trước → sau; mở/khóa tháng là ngoại lệ V7 đã chốt. Bảng gốc không có `UPDATE`/`DELETE` trực tiếp từ ứng dụng.
2. **Server tính, client không.** Client gửi ý định và số người dùng gõ; server tính hiệu số, phân bổ, tổng. Không nhận phân bổ, tổng hay actor từ client.
3. **Một khách = một đơn vị tuần tự hóa.** Mọi lệnh ghi khóa hàng khách (`FOR UPDATE`) trong giao dịch; hai lệnh cùng khách xếp hàng, khác khách chạy song song.
4. **Nguyên tử.** Một lệnh = một giao dịch: hoặc ghi đủ dữ liệu + phân bổ + sự kiện, hoặc không gì cả.
5. **VND `bigint`**, cột số tiền có `CHECK`; `NULL` giữ nguyên trong nguồn/lưu trữ. ĐÃ CHỐT (người dùng, 20/10/2026): có đơn giá, phụ phí NULL tính 0; thiếu đơn giá vẫn chưa biết, ngoài tiền và giữ cờ thiếu giá.
6. **Danh tính từ phiên máy chủ**, không từ body request (xem mục 6).

## 2. Mô hình dữ liệu

Chi tiết cột/ràng buộc: [schema-draft.sql](schema-draft.sql). Lược đồ riêng `sokhach` (không dùng `ledger` của bản cũ vì bản đó theo mô hình maker-checker/proposal đã bị V6 thay).

| Bảng | Vai trò | Ghi được bằng |
| --- | --- | --- |
| `commodity` | Danh mục mặt hàng (`LOAI HANG` của tab `TONG`: THANH LONG, CHUOI, SAU RIENG (gộp "SAU RIENG CANG/BO"), XOAI (gộp "XOAI- BỘ"; "TLONG- BỘ" gộp vào THANH LONG), BUOI, DỪA, GỪNG TƯƠI, MIT, NHAN, KHOAI LANG, BAN CUOC, HANG NHAP, CHUA PHAN LOAI) | owner/import, ngoài lệnh nghiệp vụ |
| `customer` | Khách = một sổ = một dòng `TONG`; `commodity_id` (NULL được) là mặt hàng của sổ, `transport_mode` (`CANG`/`BO`, NULL được) là phương thức vận chuyển, `archived` (mặc định false) là cờ lưu trữ; `version` tăng mỗi lệnh ghi (kiểm đồng thời lạc quan) | lệnh |
| `month_state` | Cờ ghi đè mở/khóa từng (khách, tháng); thiếu hàng: chỉ tháng hiện tại theo giờ Việt Nam mở | `set_month_lock` (không ghi `event`) |
| `trip` | Chuyến, **bất biến** về danh tính (id, khách, tháng nợ, ngày nghiệp vụ) | chỉ thêm |
| `trip_price_rev` | Lịch sử đơn giá/phụ phí của chuyến; bản mới nhất là giá hiện tại (sửa đè ở tháng mở = thêm revision) | chỉ thêm |
| `adjustment` | Điều chỉnh có dấu: theo chuyến (`trip_id`) hoặc cả tháng (`trip_id` rỗng); ghi chú tùy chọn | chỉ thêm |
| `receipt` | Phiếu thu: `pid`, ngày, hình thức, tổng tiền, trạng thái hủy (lý do, ngày hủy, người) | thêm; chỉ cột ngày/hình thức/hủy đổi qua lệnh, mỗi lần có `event` |
| `receipt_line` | Dòng phân bổ của phiếu theo tháng, gồm dòng `ỨNG TRƯỚC`; **có phiên bản**: phân bổ lại tạo bộ dòng mới và đóng bộ cũ (`superseded_by_event`) | chỉ thêm + đóng |
| `event` | Nhật ký chỉ-thêm: loại, khách, người, thời điểm, `before`/`after` (jsonb), khóa idempotency | chỉ thêm |
| `idempotency` | (khóa, khách) → băm yêu cầu + kết quả trả về | chỉ thêm |
| `cutover` | Mốc đóng băng nguồn, SHA-256, tổng kiểm toàn mốc; trạng thái `draft → verified → active` | tạo, rồi chuyển trạng thái qua gate đề xuất |
| `cutover_customer`, `cutover_month_check` | Gate theo khách và tháng, gồm mỏ neo, bucket, chứng cứ, ngoại lệ; cả khách số dư 0 cần baseline tường minh | import nháp, đối soát, kích hoạt đề xuất |
| `opening_balance` | Số dư đầu **có dấu** theo khách × tháng × mốc; tham chiếu tab + dòng mỏ neo | chỉ thêm qua `import_cutover` |
| `legacy_row` | Dòng chuyến/thu từ Sheet để xem, kèm tham chiếu tab + dòng và thành tiền theo ô tổng gốc | chỉ thêm qua `import_cutover` |

**ĐÃ CHỐT (người dùng, 20/10/2026) — mặt hàng:** một sổ chỉ có một mặt hàng (gắn theo sổ, không theo chuyến); sầu riêng là một mặt hàng, cảng/bộ là phương thức vận chuyển riêng (`transport_mode`); mục đích dùng: lọc danh sách khách và giúp xác định tab/sổ nào khi nhập liệu. **ĐÃ CHỐT thêm (người dùng, 20/10/2026):** "BAN CUOC" và "HANG NHAP" cứ gán làm giá trị `commodity` như các loại khác; `transport_mode` áp dụng cho sầu riêng, xoài và thanh long (nhóm "BỘ" trên `TONG`). Sổ có dòng trên `TONG` là đang dùng (available). **Archive** chỉ áp dụng cho tab vừa không có dòng `TONG` vừa không có số dư mở: xem được, không tính vào thống kê. Sửa lại cùng ngày: kiểm `hao` thấy 23 khách có số dư mở (9,12 tỷ đồng) nằm ở tab không có dòng `TONG`; người dùng xác nhận họ có nợ thật nên **vẫn tính vào thống kê**, không archive. Mặt hàng của 23 khách này chưa có nguồn trên `TONG`: người dùng chốt 20/10 gán tạm giá trị `CHUA PHAN LOAI` cho cả 23 để review sau (cột gợi ý theo tên tab giữ trong bảng cục bộ); mặt hàng thật CÒN MỞ. **ĐÃ CHỐT (người dùng, 20/10/2026): thêm cờ `customer.archived`.** Đối chiếu 20/10/2026 (chỉ đọc Sheet): 152 dòng `TONG`, 251 tab, 99 tab archive; 145 dòng khớp tên tab đúng, 5 dòng sửa tay do trùng/lệch tên, 1 dòng chưa có tab, 1 dòng có 2 tab cùng tên (cần chọn). Bảng đối chiếu nằm ngoài repo (`design/2026-10-20/`). Phần còn lại dưới đây vẫn là ĐỀ XUẤT thiết kế, chưa triển khai; CÒN MỞ: chặn nhập vào khách archived, và chưa có thân hàm/harness cho phần này.

**Đề xuất gốc (20/10/2026, hướng A):** gắn mặt hàng vào sổ khách (`customer.commodity_id`), không gắn từng chuyến, không tách "công ty". Lý do: Sheet ghi `LOAI HANG` theo dòng `TONG`; cùng một công ty (NEWAY, TAM XUYEN, CHANG HONG…) có nhiều sổ khác mặt hàng, nợ và mỏ neo tính theo từng sổ. Mặt hàng chỉ phân loại/hiển thị/lọc, không đổi cách tính nợ; NULL được và không chặn. Đã xử lý cùng ngày: lệnh gán/đổi là `set_customer_attributes` (ĐỀ XUẤT, mục 3); đã đối chiếu `LOAI HANG` với 132 kỳ trên `hao` (đoạn dưới). Chưa có thân hàm hay harness cho mục này.

**ĐÃ CHỐT (người dùng, 19/10/2026):** phương án chuyển lai: lấy số dư đầu theo khách và tháng còn nợ từ mỏ neo `SỐ CÒN PHẢI THU CUỐI THÁNG`, hiển thị chi tiết lịch sử của tháng còn nợ/tháng mở, tháng cũ đã trả đủ chỉ để xem. Dòng lịch sử giữ ô tổng của sổ gốc; dòng nhập mới trên web cộng đơn giá + phụ phí. Dòng phí lẻ không container, không ngày nhưng có tiền cộng vào phát sinh tháng. **ĐỀ XUẤT cấu trúc:** tách `legacy_row` khỏi `trip`/`receipt`, không có FK từ nó sang `receipt_line` và không đưa nó vào view tính tiền. Vì vậy không thể vô tình cộng hay phân bổ lại dòng lịch sử bằng truy vấn tính nợ. `opening_balance` là nguồn tiền duy nhất của phần đã chuyển; không sửa lại lịch sử/opening sau nhập. `event` loại `import` có ràng buộc duy nhất (khách, mốc), chặn nhập lại cả trường hợp không có dòng opening. Nháp còn chặn một khách nhập mốc thứ hai để view không cộng hai opening; cách chuyển lại cần quyết riêng.

Mỗi mốc có `control_total_vnd` toàn nguồn; mỗi lệnh `import_cutover` nhận tổng kiểm riêng của **khách**, so với tổng các dòng opening của khách đến từng đồng. **ĐÃ CHỌN (người dùng, 19/10/2026, phương án A):** chạy lại thu trừ nợ cũ trước trên các khối tháng của từng khách để chia mỏ neo cộng dồn thành nợ từng tháng; tổng các tháng phải bằng mỏ neo, lệch thì cách ly. `source_tab` chỉ là dấu vết nguồn, không tự quyết việc gộp một khách nhiều tab.

**ĐỀ XUẤT — gate số dư đầu:** `import_cutover` chỉ ghi `draft`; `opening_balance` nháp không vào số dư hiệu lực. `cutover_month_check` giữ mỏ neo đầu, phát sinh có dấu và thu từng tháng, mỏ neo cuối tháng, bucket nhập và bucket chuẩn. Gate dựng khoản nợ mỏ neo đầu vào **tháng đầu**, thêm phát sinh từng tháng, trừ thu theo nợ dương cũ trước; so bucket FIFO tính lại với `standard_bucket_vnd = bucket_vnd = opening_balance.amount_vnd` từng tháng. Chuỗi `mỏ neo đầu + Σ(phát sinh - thu)` phải khớp từng mỏ neo cuối; tổng **mọi** bucket phải bằng đúng mỏ neo cuối và tổng kiểm khách. Ví dụ phát sinh `[100,200]`, thu tháng 2 là 150: mỏ neo `[100,150]`, bucket `[0,150]`, không phải `[100,50]`. `replay_cumulative_vnd` chỉ chẩn đoán. Hash/ref, số đếm nguồn và tính đủ vẫn được kiểm cơ học; nguồn nhập hiện chưa tự chứng minh đủ mọi dòng nguồn (mục Câu hỏi mở). Cờ `NO_BASELINE`, thiếu giá/cache, chênh 600 VND và ngoại lệ nguồn giữ nguyên trong `exception_codes`, được trả qua `get_ledger`, không chặn khi phép tính khớp. NULL tiền/chứng cứ bắt buộc vẫn chặn; khách chưa active không có số dư hiệu lực.

**ĐỀ XUẤT — lệnh và thứ tự chuyển trạng thái:** `verify_cutover_customer(customer_id, cutover_id, expected_version, idempotency_key, signoff_ref)` khóa mốc rồi khách, đối soát FIFO/tổng/chuỗi mỏ neo/chứng cứ bắt buộc; đạt thì tự chuyển `draft → verified`. `verify_cutover` kiểm mọi khách và tổng toàn mốc; `activate_cutover` rồi `activate_cutover_customer` kiểm lại gate và kích hoạt. Không có người ký nhận; `signoff_ref` là tham số tương thích cũ, không tham gia điều kiện. View chỉ lấy khách khi **cả mốc và khách active**. Mọi lệnh chuyển atomic, kiểm actor và idempotency; lệnh theo khách kiểm version. Khóa mốc trước khách; `expected_version` của verify đọc ở client trước khi chờ khóa vẫn phải chịu `STALE_LEDGER` nếu import khác đã commit trước. Bản thử chưa chứng minh nguồn thật đầy đủ.

**ĐỀ XUẤT — bất biến chứng cứ:** từ lúc **khách** `verified` hoặc `active`, cấm INSERT/UPDATE/DELETE `cutover_month_check`, `opening_balance`, `legacy_row` của khách đó; từ lúc **mốc** `verified` hoặc `active`, cấm tương tự với mọi khách trong mốc. Trigger chặn thay đổi cả khi có quyền DML trực tiếp; `cutover` khóa nguồn/hash/tổng từ lúc tạo, `cutover_customer` khóa tổng/hash báo cáo và số dòng sau import, `opening_balance`/`legacy_row` không sửa/xóa ở mọi trạng thái. Lệnh chuyển trạng thái phải khóa mốc trước khách; trigger chứng cứ kiểm lại trạng thái dưới khóa để không lọt thay đổi trong lúc verify. Chủ DB/superuser vẫn vượt được rào. Sửa chứng cứ sau verified cần quy trình mốc mới **CÒN MỞ**, không cập nhật đè.

**ĐỀ XUẤT — chống nhập chồng:** dưới cùng khóa khách, mọi lệnh ghi tiền (kể cả `record_receipt`, sửa, hủy, điều chỉnh, dán lô) phải thấy baseline `active`, nếu không trả `NO_BASELINE`. `import_cutover` từ chối nếu khách đã có `trip`, `adjustment`, `receipt` hoặc event ghi tiền sống; một khách chỉ thuộc một mốc. Chuyển lại sau phát sinh sống là quy trình CÒN MỞ, không tự nhập opening chồng lên phát sinh.

**Vì sao `receipt_line` lưu thay vì tính lại mỗi lần.** Quy tắc đã chốt là *hủy phiếu không kéo phiếu khác lùi về trả thay*, nên phân bổ không phải hàm thuần của các phiếu còn sống: sau khi hủy, chỗ trống ở tháng cũ phải còn đó cho tới khi có sự kiện phân bổ lại (điều chỉnh, sửa giá, dán lô, đổi ngày phiếu). Do đó phân bổ là **trạng thái có phiên bản**. Mỗi lần tính lại, so bộ dòng hiệu lực theo `(debt_month, kind, amount_vnd)` của **từng phiếu**, không chỉ tập tháng; phiếu đổi số dù không đổi tháng vẫn có snapshot trước/sau trong event `reallocation`. `void_receipt` phải gắn `superseded_by_event` bằng **chính event void** cho từng dòng gốc đang hiệu lực của phiếu, mọi tháng, trước commit; không chỉ dựa view lọc phiếu hủy. Mọi lệnh đổi phân bổ kiểm lại trong cùng giao dịch: mỗi phiếu sống có đúng một bộ dòng hiện hành, tổng dòng = tổng phiếu, `advance` chỉ ở tháng cuối, event đóng dòng đúng phiếu/khách và đúng loại `reallocation` hoặc `void`; phiếu hủy không có dòng hiệu lực **và không còn dòng gốc nào `superseded_by_event IS NULL`**. Kiểm thất bại thì rollback cả lệnh.

**Tháng của chuyến** là cột riêng (`debt_month`), không suy từ ngày nghiệp vụ (`event_date`). Dòng phí lẻ không container, không đơn giá nhưng có phụ phí được để `event_date NULL`; chuyến thường vẫn cần ngày. Đổi kỳ nợ của chuyến đã ghi CÒN MỞ.

**ĐỀ XUẤT — thứ tự khóa duy nhất:** mọi lệnh/trigger liên quan mốc lấy khóa hàng `cutover` trước, rồi `customer` theo ID tăng dần nếu nhiều khách; `import_cutover` cũng theo thứ tự này, sau khóa khách mới tra idempotency rồi version. Không giữ khóa khách để đợi mốc. Lệnh ghi chứng cứ lấy hai khóa trước DML; trigger kiểm lại trạng thái dưới khóa. `BEFORE ROW` trigger trên UPDATE/DELETE có thể gặp hàng chứng cứ đã khóa trước khi chạy trigger: phải kiểm đường DML trực tiếp về deadlock, hoặc đổi cơ chế trước khi cấp quyền. Lệnh không liên quan mốc chỉ khóa khách.

## 3. Lệnh (hàm PostgreSQL, SECURITY DEFINER)

Ứng dụng hiện **chưa được cấp** `EXECUTE` trong schema nháp. Các lệnh ghi theo khách nhận `customer_id`, `expected_version`, `idempotency_key`; lệnh toàn mốc dùng khóa idempotency namespace tạm. `get_ledger(customer_id)` đọc `version` và `source_exceptions`. Gate cơ học nằm trong các hàm chuyển trạng thái; không có hàm chính sách ký nhận. Chưa có nghiệm thu ghi tiền thật.

| Hàm | Làm gì | Ghi `event` loại |
| --- | --- | --- |
| `paste_trips` | Kiểm toàn lô (cả lô hoặc không), cấp `trip_id`, thêm `trip` + `trip_price_rev`; chỉ vào tháng đang mở; rồi phân bổ lại | `paste`, `reallocation` |
| `edit_trip_price` | Chỉ tháng **mở**: thêm `trip_price_rev`; rồi phân bổ lại | `price_edit`, `reallocation` |
| `adjust_trip` | Nhận **số đúng**, tính hiệu số từ giá hiện hành (giá + mọi điều chỉnh), thêm `adjustment` (hiệu số 0 → từ chối), phân bổ lại. Quy tắc tháng mở CÒN MỞ (P2-4, mục 8); bản thử hiện cho phép. | `adjust_trip`, `reallocation` |
| `adjust_month` | Số có dấu, khác 0, ghi chú tùy chọn; phân bổ lại | `adjust_month`, `reallocation` |
| `record_receipt` | Phân bổ nợ cũ trước vào chỗ còn nợ (kể cả chỗ trống sau khi hủy), phần dư thành một dòng `ỨNG TRƯỚC` ở tháng cuối; mã phiếu do server cấp; trả bảng phân bổ để giao diện hiện dòng báo | `receipt` |
| `import_cutover` | Một giao dịch cho một khách × mốc: kiểm nguồn, tổng `openings` = `expected_control_total` từng đồng và kiểm từng bucket với mỏ neo; **retry cùng key + cùng payload trả kết quả cũ**, chỉ lần nhập **mới** bị chặn; thêm opening/dòng lịch sử **nháp** + vết; không ghi `trip`/`receipt` sống | `import` |
| `edit_receipt_meta` | Chỉ ngày và hình thức, cả phiếu; đổi ngày thì phân bổ lại | `receipt_edit`, `reallocation` |
| `void_receipt` | Lý do bắt buộc; đóng mọi dòng phân bổ gốc hiện hành ở mọi tháng bằng event `void`, rồi hủy phiếu; **không** phân bổ lại | `void` |
| `set_month_lock` | Đổi cờ mở/khóa | (không ghi `event`, theo quyết định) |
| `set_customer_attributes` | ĐỀ XUẤT 20/10: gán/đổi mặt hàng, phương thức vận chuyển, cờ `archived`; kiểm `expected_version`, tăng version; `archived=true` bị từ chối nếu khách có số dư mở khác 0; ghi event để giữ vết người làm (theo quyết định "ai cũng thao tác, vẫn ghi actor"); nhập chuyến/thu vào khách archived bị từ chối (ĐỀ XUẤT) | `customer_attr` |
| `verify_cutover_customer`, `verify_cutover` | Đối soát và khóa chứng cứ khách, rồi toàn mốc | vết gate riêng, chưa có bảng |
| `activate_cutover`, `activate_cutover_customer` | Kích hoạt mốc, rồi từng khách đã verified | vết gate riêng, chưa có bảng |
| `get_ledger` | Chỉ đọc: trả sổ đã tính (dòng, tháng, tổng, đếm Chờ xử lý) cùng `version` | — |

`record_receipt` đọc `v_outstanding_month`: số dư đầu + chuyến sống + điều chỉnh − phân bổ hiệu lực; chọn tháng có nợ dương theo thứ tự tháng cũ trước. Hàm phân bổ lại dùng chung (`sokhach.reallocate`) gom phiếu còn sống, sắp (ngày, mã phiếu), rải FIFO lên nền nợ từng tháng **gồm opening** + phát sinh + điều chỉnh; không rải lại dòng lịch sử hay sửa opening. Phiếu đã hủy giữ nguyên. Đây là phần mở rộng của `planReallocation` trong model V7, vốn chưa có opening. **ĐÃ CHỐT cho bản thử (người dùng, 20/10/2026):** giữ số âm nguyên trong view/sổ; khoản trả mới chỉ trừ các tháng có nợ dương theo thứ tự cũ trước, bỏ qua tháng âm. Phần dư của phiếu mới ở tháng cuối theo quyết định V7 hiện có. Cách xử lý chuyển tiền âm giữa các sổ/hoàn tiền vẫn CÒN MỞ. Test fixture không opening vẫn phải khớp model JS (mục 7).

**Đồng thời và nhất quán.** (a) Lệnh theo mốc khóa `cutover` trước rồi `customer`; lệnh không theo mốc chỉ khóa `customer`; (b) tra `idempotency` theo khách/khóa và băm payload chuẩn hóa: trùng khóa + băm → trả nguyên kết quả đã lưu, **kể cả `expected_version` cũ**; trùng khóa + băm khác → `IDEMPOTENCY_CONFLICT`, kể cả version cũ; (c) chỉ lệnh **mới** so `version` với `expected_version`, lệch → `STALE_LEDGER`; (d) kiểm gate, làm và kiểm mọi bất biến sau thay đổi; (e) tăng `version`, ghi đủ `event`, lưu kết quả idempotency. Mọi bước cùng một giao dịch. Băm payload không chứa `expected_version` dùng để kiểm tuần tự, nhưng chứa đầy đủ ý định nghiệp vụ và mốc import; quy tắc chuẩn hóa cụ thể còn cần chốt trước mã.

## 4. Quy tắc tháng khóa phía server

**ĐÃ CHỐT cho V7 (người dùng, 19/10/2026): mặc định chỉ tháng hiện tại mở.** Lệnh lấy khóa khách trước; **sau khi lấy khóa** mới đọc `clock_timestamp()` tại server một lần, tính `date_trunc('month', clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date` cho lần kiểm đó; không dùng `transaction_timestamp()` cố định từ lúc bắt đầu giao dịch. Thiếu hàng `month_state` thì tháng này mở, mọi tháng khác khóa. Hàng ghi đè do `set_month_lock` tồn tại thì cờ đó thắng mặc định. `edit_trip_price` và `paste_trips` kiểm cờ hiệu lực **trong cùng giao dịch** (không tin cờ client); `set_month_lock` dùng cùng khóa khách nên không lọt giữa kiểm và ghi. Tháng khóa → `MONTH_LOCKED`. `set_month_lock` ai cũng gọi được trong bản thử; không ghi event theo V7.

## 5. Danh tính và quyền

- Người thao tác = danh tính Tailscale của người đó (quyết định 19/10/2026, mỗi người một danh tính).
- Bản thử cho mọi người đã vào app thao tác, không có ACL theo người. Ranh giới app/Tailscale xác minh phiên trước khi đặt actor; phần kết nối runtime chưa nghiệm thu.
- Trong giao dịch, **chỉ app server** trên kết nối DB riêng đặt `SET LOCAL sokhach.actor` từ phiên. PostgreSQL **không xác minh** custom setting hay danh tính Tailscale. Không cấp kết nối DB/SQL tùy ý cho client; không nhận actor từ tham số lệnh. Hàm từ chối actor rỗng; harness kiểm actor và quyền DB, chưa chứng minh phiên người thật.
- **Ma trận quyền ĐỀ XUẤT:** `sokhach_owner` NOLOGIN sở hữu schema/bảng/view/hàm; role migration riêng dùng owner. `sokhach_app` chỉ `USAGE` và `EXECUTE` hàm lệnh khi cấp cho login app server; `sokhach_reader` chỉ `get_ledger`. Không SELECT/DML/DDL bảng/view trực tiếp; `PUBLIC` không quyền. `SECURITY DEFINER` cố định `search_path`. Bản thử không lọc khách theo actor. Chưa nối/cấp quyền runtime; chủ DB/superuser vượt rào.

**Liên kết vết bắt buộc:** `trip`/`trip_price_rev`, `adjustment`, `receipt` và `receipt_line` mang FK `(event_id, customer_id)` tới event tạo; các UPDATE được cho phép (`receipt` metadata/hủy, `receipt_line` đóng) chỉ do hàm lệnh thực hiện và có event cùng khách, cùng phiếu. `event.before` và `event.after` đều NOT NULL JSON object. `paste`, `receipt`, `import`: `before={}` và `after` chứa ID cùng snapshot; `price_edit`, `adjust_*`, `receipt_edit`, `void`, `reallocation`: cả trước/sau chứa ID, giá trị và bộ dòng phân bổ liên quan. Một lệnh không trả thành công khi thiếu event, sai loại, sai liên kết hoặc thiếu snapshot; kiểm trong cùng giao dịch rồi rollback. `set_month_lock` là ngoại lệ đã chốt, không tạo event tiền.

## 6. Đọc

`v_outstanding_month` cộng **chỉ opening của mốc/khách active** có dấu, chuyến sống có giá, điều chỉnh, trừ dòng phân bổ hiệu lực; `v_month_chain` cộng dồn theo tháng, giữ số âm. `get_ledger` trả: dòng chuyến (số tiền chuỗi chữ số), điều chỉnh, dòng thu (kể cả đã hủy, kèm nhãn), số dư đầu, dòng `legacy_row` có cờ `lịch sử`/`editable=false`, tổng từng tháng, tổng nợ, đếm Chờ xử lý, `version`, và với dòng sống cờ `editable` (tháng mở). Khi chưa active, trả trạng thái `NO_BASELINE` và báo cáo đối soát riêng; không trình số draft như số dư hiệu lực. Giao diện chỉ hiển thị, không tính. Lịch sử thao tác đọc từ `event` (mới nhất trước), không có mục mở/khóa; `legacy_row` là lịch sử nguồn, khác nhật ký thao tác.

### Liên hệ với V7 giao diện

Model `so-khach-v7-model.js` và giao diện hiện chưa có số dư đầu theo tháng hay dòng lịch sử nguồn. Việc nối/hiển thị hai phần này là bước sau; bản nháp backend **chưa triển khai** thay đổi giao diện.

## 7. Kiểm thử trước khi cài đặt (viết trước mã)

Chạy trên PostgreSQL cô lập theo [harness P0](../p0-write-path/next-task.md) (container riêng, `--network none`, dữ liệu giả). Mỗi hạng mục dưới đây là một test phải **viết trước** hàm:

1. **Golden:** nạp fixture V7 vào bảng (script nạp chỉ cho test) → `get_ledger` ra tổng 2.411.645.000, 11 dòng Cộng tháng đúng bảng spec, tháng 06 là 1.381.510.000, PH-101 gom 600.694.000 hai tháng.
2. **Tương đương model:** chạy lại chuỗi thao tác của 40 test JS (điều chỉnh 2 lần, điều chỉnh cả tháng, đổi ngày phiếu, hủy rồi ghi lại…) qua hàm SQL, so từng con số (tổng nợ, nợ từng tháng, danh sách phiếu đổi tháng) với model JS.
3. **Nguyên tử:** gây lỗi giữa chừng (sau khi ghi một dòng phân bổ) → không còn phiếu/dòng/event dở dang.
4. **Idempotency:** retry cùng khóa/payload sau commit với `expected_version` cũ → nguyên kết quả cũ; cùng khóa khác payload cũng với version cũ → `IDEMPOTENCY_CONFLICT`; lệnh mới version cũ → `STALE_LEDGER`.
5. **Đồng thời:** hai `record_receipt` cùng khách trên hai kết nối, quan sát bằng `pg_blocking_pids` (không dùng `sleep`) → tổng trừ không vượt nợ, dư đúng một lần; lệnh dựa `version` cũ → `STALE_LEDGER`.
6. **Không sửa đè:** UPDATE/DELETE trực tiếp lên bảng bất biến bằng `sokhach_app` bị từ chối; không có đường nào đổi số tiền của dòng đã ghi.
7. **Hủy:** chụp ID **từng dòng gốc hiện hành** của phiếu nhiều tháng trước hủy; sau `void_receipt`, từng ID đó có `superseded_by_event` là đúng event `void`, không dòng gốc nào còn NULL, snapshot `before`/`after` ghi đủ; kiểm trực tiếp bảng bên cạnh view. Lý do rỗng/hủy hai lần bị từ chối; phiếu khác không đổi tháng. Gây lỗi sau khi đóng một dòng phải rollback cả dòng lẫn trạng thái phiếu/event.
8. **Khóa:** tháng hiện tại theo giờ VN mở mặc định cả khi thiếu hàng; tháng khác khóa; ghi đè bằng `set_month_lock`. Cho giao dịch bắt đầu trước nửa đêm đầu tháng chờ khóa khách tới sau nửa đêm; `edit_trip_price`/`paste_trips` phải lấy `clock_timestamp()` **sau khóa** và từ chối tháng cũ `MONTH_LOCKED` nếu không có hàng ghi đè mở; ca ngược ở tháng mới mở. Hai kết nối tranh khóa khách giữa `set_month_lock` và lệnh sửa/dán → kết quả theo thứ tự khóa, không lọt ghi tháng khóa.
9. **Danh tính/quyền bản thử:** actor rỗng bị từ chối; hai actor đọc cùng khách; event ghi actor từ phiên, hàm lệnh không nhận tham số actor. Role app/reader không SELECT/DML bảng/view, không EXECUTE hàm riêng; `search_path` độc hại không đổi object. Ranh giới HTTP/Tailscale chưa có test runtime.
10. **Số liệu:** không `float`/`numeric` lẻ; `NULL` giữ nguyên trong nguồn/lưu trữ, phép tính phụ phí theo mục 18; nhập `-0`, số quá lớn (`bigint` tràn) bị từ chối.
11. **Nhập số dư đầu/gate:** import `draft` không vào sổ hiệu lực. Verify tự động khi đủ mỏ neo đầu, phát sinh/thu từng tháng, hash/ref, FIFO từng bucket, chuỗi mỏ neo, tổng khách và toàn mốc, tính đủ theo chứng cứ đã nhập. `bucket_vnd = standard_bucket_vnd = opening_balance.amount_vnd` từng tháng. `[100,200]` phát sinh, thu 150 tháng 2: `[0,150]` đạt, `[100,50]` bị bác. Mỏ neo đầu 50 phải vào bucket tháng đầu; opening `[100,200]` với mỏ neo cuối 350 bị bác, `[150,200]` đạt. Cờ ngoại lệ còn nguyên, không chặn phép tính đúng. `activate_cutover` rồi `activate_cutover_customer` mới đưa số vào view; khách 0 cũng cần gate.
12. **FIFO qua opening:** thu mới trừ opening tháng cũ trước phát sinh tháng mới; điều chỉnh ở tháng có opening làm lại phân bổ theo nợ cũ trước, opening và `legacy_row` bất biến.
13. **Tách lịch sử:** thêm dòng `legacy_row` chuyến/thu với `source_total_vnd` khác công thức giá không đổi bất kỳ tổng nào; thử UPDATE/DELETE bị trigger từ chối.
14. **Chặn nhập sai/lặp:** retry `import_cutover` cùng key/payload sau commit, kể cả version cũ → nguyên kết quả cũ; lần nhập mới cùng khách × mốc bị từ chối; key mới version cũ → `STALE_LEDGER`; tổng sai một đồng bị từ chối. Cờ nguồn còn trong báo cáo và sổ sau active. Ghi tiền khi `NO_BASELINE` bị chặn; import sau phát sinh sống bị chặn. **Đồng thời import vs verify:** khóa `cutover` trước khách, quan sát bằng `pg_blocking_pids`, không deadlock. Nếu verify mang version lấy trước import rồi đợi khóa, import commit trước → `STALE_LEDGER`; verify đi trước khi chưa có import → `CUTOVER_TRANSITION_ORDER`, import sau đó thành công.
15. **Tháng âm và hủy:** opening âm giữ nguyên; thu mới bỏ qua bucket âm, trừ nợ dương cũ trước, phần dư ở tháng cuối; hủy không đổi opening/phiếu khác. Chuyển âm giữa sổ và hoàn tiền vẫn CÒN MỞ.
16. **Phân bổ/vết:** đổi số phân bổ cùng tập tháng vẫn phát sinh snapshot trước/sau. Gây lỗi giữa chừng ở `record_receipt`, `edit_receipt_meta`, `void_receipt`, `adjust_trip`, `adjust_month`, `edit_trip_price`, `paste_trips`: rollback đủ; sau mỗi lệnh kiểm đúng một bộ dòng hiện hành, tổng bằng phiếu, `advance` đúng tháng cuối, event thay thế đúng khách/phiếu/loại, mọi dòng tiền có event và snapshot bắt buộc. Kiểm cả ca thiếu event hoặc thiếu `before`/`after` bị từ chối.
17. **Chứng cứ bất biến:** khi khách còn draft, thử sửa `cutover_month_check` rồi verify; sau khách verified/active, `INSERT/UPDATE/DELETE` check/opening/legacy của khách đều bị trigger chặn. Sau mốc verified/active, thử với khách đã verified/active cũng bị chặn; UPDATE/DELETE nguồn/hash/tổng của mốc, báo cáo/tổng/dòng nguồn của khách bị chặn. Cho ghi check chạy đồng thời với verify: chỉ một thứ tự commit hợp lệ; không có sửa chứng cứ sau verified. Test bằng role có DML trong container giả, không coi quyền `sokhach_app` bị từ chối là bằng chứng trigger.
18. **Phụ phí NULL — ĐÃ CHỐT:** chuyến có đơn giá và phụ phí NULL tính đúng đơn giá, phụ phí tính 0, không tăng Chờ xử lý; cột lưu trữ vẫn NULL. Thiếu đơn giá và có container: `amount_vnd IS NULL`, ngoài số dư, `isMissingPrice=true`/tăng Chờ xử lý. Dòng phí lẻ không container, không đơn giá nhưng có phụ phí là trường hợp riêng. So cả ba ca với `so-khach-v7-model.js` `tripAmount` và SQL view.

## 8. Câu hỏi mở (CÒN MỞ — không chốt hộ)

- **Câu hỏi mở về chứng cứ nguồn:** `source_charge_vnd` và `source_receipt_vnd` mới là tổng do client nộp; hash/ref chưa chứng minh chúng gồm đủ từng dòng nguồn đóng băng, đúng khách/kỳ, và không đếm trùng. `source_rows` hiện đếm chính JSON import, chưa đối chiếu tập khách/tổng dòng nguồn ngoài. **ĐỀ XUẤT** bảng `source_movement(customer_id, debt_month, kind, amount_vnd, source_ref, source_hash)` chỉ-thêm, có khóa chống lặp, cùng bảng manifest tập khách/dòng/hash của nguồn đóng băng; gate tính tổng phát sinh/thu từ bảng đó và so manifest. Chưa có nguồn này thì phép FIFO đã độc lập với opening nhập nhưng chưa là đối soát nguồn thật độc lập.
- Ranh giới HTTP/Tailscale lấy actor từ phiên server chưa nối bản thử; cần kiểm giả mạo header/phiên trước khi dùng thật. Q01 **quy tắc quyền bản thử đã chốt**; phần triển khai/xác thực runtime còn chưa kiểm.
- D04: hoàn tiền, ứng trước giữa các sổ (đã chốt riêng: dư ghi trong sổ, hiện âm).
- "Khoản thu chưa chắc" (đang luôn 0), đổi tháng nợ của một chuyến đã ghi, màn Tổng nhiều khách.
- Có ghi vết mở/khóa khi có kiểm toán thật.
- Nhập dữ liệu thật từ Sheet: **hướng đã chốt (người dùng, 19/10/2026): migrate và làm sạch dữ liệu từ Sheet đang dùng.** [Spec chuyển dữ liệu](../v7-migration-sheet.md) đã có nhưng còn các quyết định mở và gate đối soát; bản nháp này chưa cho phép chạm dữ liệu thật.
- Cách nối với `web/ledger_*.py` hiện có (đọc replay/opening) — thiết kế này tách lược đồ mới; việc ghép giữ cho bước sau.
- Chuyển Sheet theo [spec chuyển dữ liệu](../v7-migration-sheet.md): định nghĩa khoản thu trong khối cũ, một khách nhiều tab, hình thức thu từ ghi chú, giờ đóng băng, cách hiển thị dòng lịch sử. Cần ví dụ nguồn/tháng âm và đối soát trước import thật.
- Gate bản thử tự động, còn thiếu chứng cứ tập khách/dòng nguồn thật và quy trình sửa sai/nhập lại ở mốc thứ hai. Harness PostgreSQL chưa chạy lại vòng sửa; UI chưa nối backend.

## Quyết định đã chốt bổ sung

- **Người dùng, 20/10/2026, trong chat:** chuyến đã có đơn giá nhưng phụ phí để trống (`NULL`) tính phụ phí 0. Lưu giá trị nguồn vẫn `NULL`; phép cộng trong `tripAmount` và SQL view dùng 0 cho trường hợp này. Thiếu đơn giá vẫn chưa biết, không cộng vào số dư và giữ cờ thiếu giá. Quyết định chỉ chốt nghĩa tiền của trường hợp này, không duyệt import hay ghi tiền thật.
- **N1/N2 — người dùng, 20/10/2026, trong chat:** bucket số dư đầu theo nợ còn lại từng tháng sau thu FIFO, không theo hiệu hai mỏ neo. Mỏ neo đầu khác 0 vào bucket tháng đầu; tổng bucket bằng đúng mỏ neo cuối khách.
- **(a) — người dùng, 20/10/2026, trong chat:** dòng phí lẻ không ngày có `trip.event_date NULL` khi không container, không đơn giá, có phụ phí; `debt_month` vẫn là tháng nợ. Chuyến thường thiếu ngày bị từ chối.
- **(b) — người dùng, 20/10/2026, trong chat:** số dư đầu tự `verified` rồi `active` khi mọi kiểm tra cơ học đạt; không cần người ký. Bỏ `_cutover_policy`.
- **(c) — người dùng, 20/10/2026, trong chat:** cờ `NO_BASELINE`, thiếu giá/cache, chênh 600 VND và ngoại lệ nguồn được giữ/hiển thị, không chặn gate nếu các phép tính đúng. Chứng cứ số tiền NULL vẫn không được đoán thành 0.
- **(d)/Q01 bản thử — người dùng, 20/10/2026, trong chat:** ai đã vào app cũng thao tác, không phân quyền theo người; actor vẫn từ phiên server để lưu vết, không từ tham số.

## 9. Thứ tự tiếp theo

1. Claude chạy lại harness PostgreSQL cô lập trên đúng SHA schema + thân hàm sau vòng sửa cuối, review kết quả từng case.
2. Bổ sung chứng cứ dòng nguồn/manifest để kiểm đầy đủ độc lập trước import thật.
3. Gate triển khai riêng trước khi đụng `hao` hay dữ liệu thật.

## Nhật ký review

- **review1 — Codex, 20/10/2026: CHẶN (trạng thái lúc review).** Đã sửa hợp đồng nháp cho phát hiện **1–13**: thứ tự idempotency/version (1), gate draft/active (2), baseline/chặn nhập chồng (3), đối soát bucket và ngoại lệ (4), bất biến phân bổ (5), ma trận quyền/search_path (6), ranh giới actor (7), event/snapshot (8), so bộ `(tháng, loại, số tiền)` (9), khóa tháng theo giờ VN (10), version import (11), chữ ký đọc (12), test tháng âm (13); thêm test mục 7. **CÒN MỞ:** chính sách xử lý nguồn thiếu/chênh, người ký nhận/gate chuyển thật, Q01 xác minh và quyền truy cập khách, chuyển âm giữa sổ/hoàn tiền, quy trình chuyển lại. Lúc đó SQL chưa có thân hàm hoặc DB test; xem trạng thái hiện tại ở đầu tài liệu.
- **review2 — Codex, 20/10/2026: CHẶN (trạng thái lúc review).** Sửa hợp đồng nháp: lệnh/thứ tự gate và trigger khóa chứng cứ; retry import; `clock_timestamp()` sau khóa; đóng từng dòng gốc khi hủy; điều kiện mảng ngoại lệ; test mục 7. Lúc đó chưa có hàm lệnh hoặc DB test; chính sách ký nhận/ngoại lệ và nghiệm thu ghi tiền vẫn CÒN MỞ. Nghĩa phụ phí NULL đã được người dùng chốt sau review.
- **review3 — 20/10/2026: CHẶN, 3 P1 (trạng thái lúc review).** Bản nháp ghi bucket chuẩn độc lập từng tháng và nguồn mỏ neo, thống nhất khóa mốc trước khách cả import/verify/activate/trigger, chốt phụ phí NULL theo quyết định người dùng; bổ sung ca đồng thời và bucket sai bù nhau. Lúc đó chưa có thân hàm hoặc test PostgreSQL; đến nay vẫn chưa có bằng chứng nguồn thật.

### Review độc lập 20/10/2026 — bổ sung

- **P1-2 lịch sử, thay bởi N1/N2 20/10/2026:** cách lấy hiệu mỏ neo liên tiếp và chính sách từ chối mặc định đã bỏ. Gate hiện tính FIFO từ phát sinh/thu theo tháng và mỏ neo đầu; tổng bucket bằng mỏ neo cuối.
- **P2-1:** mã phiếu cùng ngày xếp theo thứ tự chuỗi JS, tương ứng `pid COLLATE "C"` ở PostgreSQL. `PH-1000 < PH-999` là hành vi chủ ý của JS.
- **P2-4 CÒN MỞ:** `adjust_trip` cho phép ở tháng mở là lệch có chủ ý so với JS; chưa chốt thay đổi quy tắc.
