# V7 — Tổng quan v4: màn theo dõi công nợ cho C-level (DASH-06)

Trạng thái: **ĐÃ CHỐT** ba điểm của [`DASH-06`](../docs/decisions/dash-06.md) (người dùng 6/11/2026, chat: "ok theo bạn đề xuất"): chia khách theo bốn tình trạng thay ba mức rủi ro, hình 12 tháng cả công ty, mốc "vẫn đi hàng" 30 ngày; và **hàng sổ lớn lên đầu khối khách** (người dùng 6/11/2026, chat: "Chọn B", sau khi bấm thử bản xem ba phương án). **ĐỀ XUẤT**, chờ người dùng: chỗ đặt và cách vẽ hình 12 tháng (mục Bố cục, phần 2); mốc 10% của sổ lớn. **CÒN MỞ**: luật "còn nợ cũ" (cuối spec). Chưa code, chưa triển khai. Bản xem dữ liệu giả: [`preview/mockups/tong-quan-v4/`](../cong-no-web-handoff/preview/mockups/tong-quan-v4/index.html).

Spec này thay **khối khách** của [`v7-tong-quan-v3.md`](v7-tong-quan-v3.md) (DASH-05) và **thẻ Thu tháng**; dải đầu, thanh tiêu đề, menu trái, lọc theo nhóm hạn trả và mặt hàng giữ như v3. Quy tắc tính của [`DASH-03`](../docs/decisions/dash-03.md) giữ, trừ mục 2 (mức rủi ro) và mục 4 (không so tháng trước).

## Bài toán (bước 1)

| Người xem | Lúc nào | Câu hỏi (theo thứ tự) | Khối trả lời |
| --- | --- | --- | --- |
| C-level (sếp, người quản lý) | Mở web xem nhanh; trước khi bàn chuyện tiền với khách hoặc trong buổi họp | 1. Khách đang nợ bao nhiêu, bao nhiêu đã quá hạn, quá bao lâu? | Dải đầu (giữ v3) |
| | | 2. Nợ đang tăng hay giảm? Thu có theo kịp phát sinh không? | Thẻ "Còn phải thu 12 tháng" |
| | | 3. Tiền quá hạn nằm ở đâu: sổ lớn nào, còn lại loại khách nào? | Hàng sổ lớn, hàng ô tình trạng |
| | | 4. Đó là những khách nào, đang thế nào? | Thẻ sổ lớn, bảng chia nhóm → bấm tên mở thẻ Tình hình |
| Người nhập | Cuối ngày | Còn việc gì? | Tab Việc cần làm, không đổi |

Mỗi nhóm ứng với một loại việc sếp tự quyết; màn không ghi việc, không gợi ý ([`TINH-HINH-01`](../docs/decisions/tinh-hinh-01.md)):

- **Vẫn đi hàng, không trả**: tiền nợ vẫn đang tăng thêm → có cho nợ tiếp không.
- **Ngừng đi hàng, không trả**: khách đã đi, còn nợ → thu hồi thế nào.
- **Vẫn trả, còn nợ cũ**: khách trả nhưng chậm hơn phát sinh, nợ dồn từ 3 tháng → có siết lịch trả không.
- **Vẫn trả, quá hạn ngắn**: khách trả đều, nợ quá hạn dưới 3 tháng → từng khách thường không cần sếp, nhưng sếp vẫn cần thấy tổng tiền: trên `hao` đây là nhóm giữ nhiều tiền quá hạn nhất (mục Số thật).
- **Không quá hạn**: không cần sếp.

Vấn đề của bản đang chạy (v3) và hai bản team đề xuất ngày 6/11/2026:

- Cả ba trả lời câu "gọi ai trước" của người đi đòi nợ. Spec DASH-03/v3 ghi người xem là "chủ nghiệp vụ, trước khi gọi đòi nợ"; người dùng nói rõ ngày 6/11 màn này để C-level theo dõi công nợ công ty.
- Nhãn Rủi ro cao không tách được ai: trên `hao` ngày 4/11 có 50/63 khách đang nợ ở Rủi ro cao, bản mẫu của team là 10/12. Chỉ cần một khoản quá hạn từ 3 tháng là vào nhóm, nên khách vừa trả 3 ngày trước, vừa đi hàng 2 ngày trước đứng chung với khách 300 ngày không trả. Lý do của nhãn chỉ nằm trong màu thanh.
- Không chỗ nào trên Tổng quan cho biết nợ tăng hay giảm (DASH-03 mục 4 chốt không so tháng trước).
- Bản team chia theo ngày từ chuyến cuối thì khách vẫn chạy hàng mà không trả nằm ở ô xanh "Đang đi hàng"; nhãn "Khó đòi" trùng từ kế toán (nợ quá hạn từ 6 tháng, Thông tư 48/2019) nhưng tính theo chuyến cuối; "% kẹt" và "thường 80%" không có định nghĩa.

Đã biết: dữ kiện để chia nhóm đã có ở API (`pay_days`, `trip_days`, `overdue_vnd`, `long_overdue_vnd`); số 12 tháng từng sổ đã có ở `get_ledger`. Giả định: C-level xem cùng khung 1280×560 như người dùng khác (CÒN MỞ, xem cuối spec).

## Số thật trên `hao` (6/11/2026, chỉ đọc, sau khi người dùng chốt)

Áp quy tắc tình trạng lên `get_dashboard_debt` trong giao dịch chỉ đọc; số khách cộng đủ 69, tiền quá hạn cộng đủ tổng của `summary`. Bản xem đầu tiên dùng 12 khách của bản team đề xuất nên tỷ trọng khác hẳn (nhóm Vẫn trả, quá hạn ngắn chỉ 2%). Từ 6/11/2026 bản xem dùng dữ liệu giả theo đúng tỷ trọng dưới đây:

| Tình trạng | Khách | % tiền quá hạn |
| --- | --- | --- |
| Vẫn đi hàng, không trả | 3 | 2% |
| Ngừng đi hàng, không trả | 27 | 22% |
| Vẫn trả, còn nợ cũ | 10 | 28% |
| Vẫn trả, quá hạn ngắn | 12 | 48% |
| Không quá hạn | 17 | – |

- Bốn nhóm có tách được: 40 khách Rủi ro cao thành 3 / 27 / 10; hôm đo, 12 khách Theo dõi trùng đúng nhóm Vẫn trả, quá hạn ngắn.
- **Tiền tập trung:** 3 sổ có quá hạn từ 10% tổng quá hạn giữ 61% tiền quá hạn cả công ty: 33% và 11% ở nhóm Vẫn trả, quá hạn ngắn, 17% ở nhóm Vẫn trả, còn nợ cũ. Hai sổ của nhóm đầu chiếm 90% tiền nhóm đó; 11/12 khách của nhóm còn đi hàng trong 30 ngày. Theo thứ tự bảng, ba sổ này nằm sau hai nhóm "không trả" (CÒN MỞ, cuối spec).
- **Luật "nợ cũ" còn bắt khoản rất nhỏ:** sổ 17% vào nhóm Vẫn trả, còn nợ cũ chỉ vì 1% nợ của nó đã từ 3 tháng, trong khi nhóm này có khách 74%. Đây cùng dạng lỗi của nhãn Rủi ro cao: chỉ cần một khoản (CÒN MỞ, cuối spec).
- Mốc 30 ngày ít ảnh hưởng hôm nay: chỉ 2 khách đang nợ có chuyến cách 31–60 ngày, 1 khách trong số đó ở nhóm Ngừng đi hàng.
- 20/69 khách có ngày trả là ngày tạm (`last_receipt_exact = false`): 13 ở hai nhóm "không trả", 3 ở Vẫn trả, quá hạn ngắn, 4 ở Không quá hạn. Tình trạng của các khách này có thể lệch khi có ngày thật.

Số đổi theo ngày; đo lại trước khi dùng. Spec chỉ ghi tỷ lệ và số khách, không ghi tên hay số tiền từng khách.

## Bố cục (bước 2) — thứ tự nhìn trong 1280×560

1. **Thanh tiêu đề, menu trái:** giữ v3.
2. **Dải đầu**, nền xanh nhạt:
   - Trái, giữ v3: Còn phải thu (số 40px) + nút đếm; ngoặc Trong hạn / Quá hạn; thanh 5 đoạn chỉ là hình; 5 ô nhóm hạn trả; bấm đoạn hoặc ô = lọc bảng.
   - Phải (**ĐỀ XUẤT**), thẻ trắng **"Còn phải thu 12 tháng"** thay thẻ Thu tháng, cùng chiều cao dải. Hai hình chồng, mỗi hình một thang, không hai trục trên một hình:
     - trên: đường **còn phải thu cuối tháng** có vùng nhạt, thang từ số thấp nhất tới số cao nhất trong 12 tháng; chấm và số ở điểm thấp nhất và điểm cuối;
     - dưới, cách một vạch mảnh: **cột kép phát sinh (xám `#8494a9`) và đã thu (navy `#1e4e8c`)**, thang từ 0; chú giải hai màu ở góc phải tiêu đề thẻ;
     - hàng tên tháng T12 … T11; rê hoặc focus một tháng thì chú thích ghi tháng, phát sinh, đã thu, còn phải thu cuối tháng;
     - dòng dưới hình: "T11 đến 6/11: đã thu **X** · phát sinh **Y**" và link "Bảng thu ›" (giữ câu hỏi "thu tháng này có kịp phát sinh" của v3 mà không cần rê chuột).

     Phương án khác đã cân nhắc: để thẻ Thu tháng và đặt hình 12 tháng thành một hàng riêng dưới dải đầu. Bị loại vì đẩy hàng ô tình trạng xuống dưới mép 560px.
3. **Khối "Nợ quá hạn nằm ở đâu"** rộng cả trang, nền trắng:
   - Đầu khối: tên khối, nút lịch sang Công nợ theo tháng (giữ v3). Từ 9/11/2026 ([`DASH-07`](../docs/decisions/dash-07.md)) không còn select mặt hàng: khối Công nợ theo mặt hàng nằm giữa dải đầu và khối này, lọc mặt hàng bằng bấm dòng của khối đó; số đo y ở dưới phải đo lại khi code.
   - **Hàng sổ lớn** (đã chốt, phương án B): nhãn "Sổ lớn · từ 10% quá hạn" bên trái, rồi mỗi sổ một thẻ, nhiều tiền trước. Thẻ dòng 1: tên, tiền quá hạn bằng tỷ, tỷ lệ trên tổng quá hạn; dòng 2: chấm màu và tên tình trạng, số ngày từ lần trả và chuyến gần nhất; Còn nợ ở chú thích. Bấm thẻ mở thẻ Tình hình như bấm dòng bảng. Không có sổ nào đạt mốc thì ẩn cả hàng. Phương án đã loại: A đánh dấu trong ô và dòng (phải đọc số phụ, tên sổ nằm dưới mép 560px), C xếp nhóm theo tiền (thứ tự đổi theo ngày, đẩy nhóm "không trả" xuống).
   - **Hàng 5 ô tình trạng** thay hàng chip mức rủi ro, **không kể sổ lớn**: bốn ô nhóm quá hạn rộng bằng nhau, ô Không quá hạn hẹp hơn (`repeat(4,1fr) .7fr`). Mỗi ô: chấm màu + tên nhóm (dòng 1); hình người + số khách và **tiền quá hạn bằng tỷ, hai số lẻ** cho cả hàng (dòng 2; ô Không quá hạn chỉ có số khách). Bấm ô = lọc bảng, bấm lại = bỏ; không còn chip "Tất cả".
   - **Bảng chia nhóm**, không có dòng cho sổ lớn: mỗi nhóm một dòng tiêu đề (chấm, tên nhóm, định nghĩa ngắn bằng chữ nhỏ, thêm "không kể sổ lớn" khi hàng sổ lớn đang có), thứ tự Vẫn đi hàng, không trả → Ngừng đi hàng, không trả → Vẫn trả, còn nợ cũ → Vẫn trả, quá hạn ngắn → Không quá hạn. Cột: **Khách** · **Quá hạn** (triệu) · **Quá hạn lâu nhất** · **Trả gần nhất** (ngày trước) · **Đi hàng gần nhất** (ngày trước) · **Còn nợ** (triệu) · ›. Đầu cột hai dòng: tên và đơn vị. Bỏ cột thanh "Theo hạn trả" và chấm màu đầu dòng.
   - Ô dữ kiện làm khách vào nhóm được tô: Trả gần nhất (viên đỏ) ở hai nhóm "không trả"; Đi hàng gần nhất (viên đỏ) ở nhóm Ngừng đi hàng; Quá hạn lâu nhất (chữ đỏ đậm) ở nhóm Vẫn trả, còn nợ cũ. Ô khác chữ thường.
   - Mỗi nhóm hiện 5 dòng đầu, thêm nút "Hiện cả N khách" trong nhóm khi nhiều hơn.

Luôn hiện: dải đầu, thẻ 12 tháng, hàng sổ lớn, hàng ô tình trạng, đầu bảng. Chỉ mở khi cần: số từng tháng (chú thích), dòng thứ 6 trở đi của mỗi nhóm, trang khách.

Số đo trên bản xem (Segoe UI thật trên Windows, khung 1280×560 và 1265×560 cho thanh cuộn Windows): dải đầu y 73–298, hàng sổ lớn y 379–431, hàng ô y 439–501, đầu bảng y 507–556; không cuộn ngang ở cả hai bề rộng; tên năm ô và nội dung thẻ không bị cắt. Dòng đầu của bảng nằm dưới mép 560px; đây là đánh đổi đã chọn. Đầu bảng chỉ còn cách mép 4px, nên PR frontend phải giữ phép đo này ở cả font rộng trên CI.

### Mỗi số một chỗ

| Số | Chỗ duy nhất | Kiểm cộng |
| --- | --- | --- |
| Còn phải thu, số khách đang nợ | Dải đầu | = điểm cuối đường 12 tháng |
| Tiền từng nhóm hạn trả | 5 ô của dải đầu | 5 ô = `receivable_vnd` |
| Phát sinh, đã thu, còn phải thu từng tháng | Hình 12 tháng (chú thích từng tháng) | tháng cuối = `this_month`; điểm cuối = `receivable_vnd` |
| Đã thu, phát sinh tháng này | Dòng dưới hình | = `this_month` |
| Tiền quá hạn từng sổ lớn | Thẻ sổ lớn | Sổ lớn không có dòng bảng và không tính vào ô |
| Số khách, tiền quá hạn theo tình trạng | Hàng ô tình trạng, không kể sổ lớn | Số thẻ sổ lớn + 5 ô khách = số khách đang nợ; tiền thẻ sổ lớn + 4 ô tiền (+ phần quá hạn âm của khách Không quá hạn) = ngoặc Quá hạn |
| Từng khách khác | Một dòng bảng | Nợ theo tháng, hứa trả, nhắc nợ ở trang khách |

## Quy tắc (DASH-06)

- **Tình trạng** (server tính, chỉ khách đang nợ; ngưỡng đọc từ `rule`, không viết cứng):
  - quá hạn ≤ 0 → `ok` (**Không quá hạn**);
  - còn lại, `pay_days` null hoặc > `no_pay_days` (60): `trip_days` không null và ≤ `active_trip_days` (30) → `ship_unpaid` (**Vẫn đi hàng, không trả**); ngược lại → `stop_unpaid` (**Ngừng đi hàng, không trả**);
  - còn lại, `long_overdue_vnd` > 0 (quá hạn từ `long_overdue_months` = 3 tháng) → `pay_old` (**Vẫn trả, còn nợ cũ**);
  - còn lại → `pay_recent` (**Vẫn trả, quá hạn ngắn**).
- **Sổ lớn** (server tính): khách có `overdue_vnd` × 100 ≥ `summary.overdue_vnd` × `big_share_pct` (10), lấy tối đa `big_max` (4) sổ nhiều tiền quá hạn nhất; bằng tiền thì xếp theo tên rồi id. Sổ đạt mốc nhưng ngoài 4 sổ đó vẫn ở nhóm của nó. Sổ lớn vẫn có `situation` riêng, thẻ Tình hình dùng tên tình trạng như mọi khách. Tổng quá hạn ≤ 0 thì không có sổ lớn.
- Ngày trả và ngày đi hàng giữ cách đọc của DASH-03 mục 3 (ngày tiền về thật, PR #344). NULL là "chưa", không phải 0, và coi là lâu nhất khi xếp. Ngày tạm (`last_receipt_exact`, `last_trip_exact` là false) vẫn dùng để chia nhóm như DASH-03, nhưng chú thích dòng ghi "khoảng T…" như v3, không ghi như ngày chắc chắn.
- **Quá hạn lâu nhất** = nhóm hạn trả của tháng nợ cũ nhất còn tiền (`oldest_open_month`, cùng hàm `tierOfMonth`), ghi bằng tên ngắn của 5 ô ("1–2 tháng", "3–6 tháng", "> 6 tháng") kèm ô vuông màu nhóm; chú thích ghi tháng nợ. Không quá hạn ghi "–".
- **12 tháng:** 12 tháng lịch tới tháng của `as_of` (giờ VN), tháng này tính tới hôm nay. Phát sinh và đã thu từng tháng = cộng `charges_vnd`, `received_vnd` trong `months[]` của `get_ledger` qua mọi sổ đang hoạt động (cùng số hình 12 tháng của thẻ Tình hình; "đã thu" theo [`DA-THU-01`](../docs/decisions/da-thu-01.md)). Còn phải thu cuối tháng = cộng phần dương của `end_of_month_vnd` từng sổ (khách trả thừa tính riêng, như dải đầu); sổ không có dòng tháng đó lấy số cuối tháng gần nhất trước đó, không cộng phát sinh / đã thu giả bằng 0. Vì chỉ cộng phần dương, "cuối tháng trước + phát sinh − đã thu = cuối tháng" không còn đúng ở tháng có sổ đổi dấu hoặc đang dư; bản xem kiểm được đẳng thức này chỉ vì dữ liệu giả không có sổ dư. Màn không hiện phép cộng đó và không kiểm nó trên số thật.
- Tiền: dải đầu, nhãn hình và dòng dưới hình `F.short(…, 'tr')`; hàng ô tình trạng `F.billions` + " tỷ" (một đơn vị, hai số lẻ cho cả hàng); bảng `F.millions`, đơn vị ở đầu cột.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Thông tin trên màn | Nguồn | Tình trạng |
| --- | --- | --- |
| Dải đầu, 5 nhóm hạn trả, ngoặc, nút đếm | `GET /api/v7/dashboard`, `GET /api/v7/dashboard/debt` | Có, giữ v3 |
| Tình trạng từng khách | Tính được từ `customers[].pay_days`, `trip_days`, `overdue_vnd`, `long_overdue_vnd` và `rule` đang có | **Chưa có trường**; thêm ở server cạnh `risk` (cùng CTE `ranked` của `get_dashboard_debt`) |
| Sổ lớn | Tính được từ `customers[].overdue_vnd`, `summary.overdue_vnd` | **Chưa có trường**; thêm cùng chỗ với tình trạng |
| Số khách, tiền quá hạn theo tình trạng và sổ lớn để đối chiếu | `summary` mới | **Chưa có** |
| Quá hạn lâu nhất | `customers[].oldest_open_month` + `DashboardModel.tierOfMonth` | Có |
| 12 tháng cả công ty | Từng sổ: `months[]` của `get_ledger` (thẻ Tình hình đang dùng) | **Chưa có hàm cộng mọi sổ**; không gọi `get_ledger` 236 lần từ trình duyệt |
| Đã thu, phát sinh tháng này | `dashboard/debt` `.this_month` | Có |
| Ngưỡng 60 / 30 ngày, 3 tháng | `dashboard/debt` `.rule` (`no_pay_days`, `active_trip_days`, `long_overdue_months`) | Có |

Bản xem dùng bộ khách giả trong [`data.js`](../cong-no-web-handoff/preview/mockups/tong-quan-v4/data.js): 69 khách "Mẫu …", tên và số tiền hư cấu, chỉ giữ tỷ trọng ở mục Số thật. Bản xem tự kiểm 5 nhóm = còn phải thu = điểm cuối hình, mỗi tháng = cuối tháng trước + phát sinh − đã thu, tiền sổ lớn + các nhóm tình trạng = tổng quá hạn.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT)

- `GET /api/v7/dashboard/debt` (hàm `get_dashboard_debt`, chỉ đổi hàm đọc):
  - thêm `customers[].situation` ∈ `ship_unpaid` · `stop_unpaid` · `pay_old` · `pay_recent` · `ok`;
  - thêm `customers[].big_book` (true/false) và `rule.big_share_pct`, `rule.big_max`;
  - thêm `summary.situations`: `[{situation, customers, overdue_vnd}]` đủ năm giá trị, theo thứ tự trên, **không kể sổ lớn**;
  - thêm `summary.big_books`: `{customers, overdue_vnd}`;
  - giữ `risk`, `summary.high_*` tới khi thẻ Tình hình và `doi-no.js` đổi xong, rồi bỏ ở một PR sau.
- `GET /api/v7/dashboard/months` (mới, chỉ đọc, cùng cờ và quyền như `dashboard/debt`, thêm vào `FLAGGED_READS`): `{as_of, months: [{month: "YYYY-MM-01", charges_vnd, received_vnd, end_vnd}]}` đủ 12 tháng, cũ trước; tiền là chuỗi VND nguyên; tháng không sổ nào có dòng thì `charges_vnd`, `received_vnd` là `null`. Hàm SQL tính theo tập (không lặp `get_ledger` từng sổ); kết quả phải bằng cộng `months[]` của `get_ledger` qua mọi sổ (test harness). Đo thời gian trên `hao` chỉ đọc trước khi merge.
- Địa chỉ trang: `?tt=di-hang-khong-tra|ngung-khong-tra|tra-no-cu|tra-qua-han-ngan|khong-qua-han` thay `?muc=`; `?han=`, `?mh=`, `?xep=` giữ; `?muc=` cũ bị bỏ qua và xóa khi đổi lọc.

## Hành vi và trạng thái

- **Lọc tại chỗ** kết hợp: nhóm hạn trả (ô hoặc đoạn thanh), tình trạng (ô), mặt hàng (select); xếp theo Quá hạn (mặc định), Còn nợ, Trả, Đi hàng, luôn xếp **trong từng nhóm**. Lọc nhóm hạn trả thì cột Quá hạn đổi thành "Nhóm này" (như v3). Nhóm không còn dòng nào thì ẩn cả dòng tiêu đề nhóm; không còn khách nào: "Không có khách nào khớp bộ lọc." Lọc không đổi dải đầu, thẻ 12 tháng và số trên ô. Thẻ sổ lớn: lọc mặt hàng hoặc nhóm hạn trả thì ẩn thẻ không khớp, số trên thẻ vẫn là toàn bộ quá hạn của sổ; lọc ô tình trạng không ẩn thẻ vì ô không kể sổ lớn.
- **Bấm tên khách** (hoặc dòng) mở `so-khach-v7-live.html?customer=<id>&the=tinh-hinh` (giữ v3).
- **Không đối chiếu được**: như v3, thêm điều kiện ô tình trạng phải bằng `summary.situations` và thẻ sổ lớn phải bằng `summary.big_books`; lệch thì khóa ô và select, dưới hàng ô một dòng "Số từng khách chưa khớp tổng; xem chi tiết ở Công nợ theo tháng."
- **API 12 tháng lỗi hoặc chậm**: thẻ ghi "Chưa tải được số 12 tháng. Bấm Làm mới để thử lại."; dòng thu / phát sinh tháng này vẫn hiện từ `this_month`. Tháng không có số: không có cột, tên tháng xám.
- **API debt lỗi**: như v3 (dải đầu chỉ còn số tổng, bảng báo chưa tải được, ẩn ô và select).
- **Khách quá hạn âm** (dư ở nợ cũ, còn nợ mới): ở Không quá hạn như v3; chú thích ngoặc Quá hạn giữ.
- **Dữ liệu dài**: tên khách dài hoặc có chữ Hán cắt bằng dấu "…" và có chú thích tên đủ; ô tình trạng không xuống dòng ở 1265px. Dưới 700px: thẻ sổ lớn mỗi thẻ một dòng, ô tình trạng hai cột và tên ô được xuống dòng (cắt tên thì "Vẫn trả, còn nợ cũ" và "Vẫn trả, quá hạn ngắn" khó phân biệt), thẻ 12 tháng xuống dưới dải trái, bảng cuộn ngang trong khung như v3.
- Tự tải mỗi 60 giây, PRESENCE-01, số trên mục Việc cần làm: giữ.
- **Thẻ Tình hình** của trang khách: nhãn chữ đổi từ Rủi ro cao / Theo dõi / Không quá hạn sang tên tình trạng, cùng màu chấm với Tổng quan; dải bốn dữ kiện đã có đủ dữ kiện tạo ra nhãn nên không đổi.

## Tiêu chí nghiệm thu

- [ ] Harness PostgreSQL: `situation` đúng ở các biên (trả đúng 60 / 61 ngày, chưa trả lần nào, đi hàng đúng 30 / 31 ngày, chưa có chuyến, quá hạn ≤ 0, có / không nợ từ 3 tháng); `big_book` đúng ở các biên (đúng 10%, dưới 10%, hơn 4 sổ đạt mốc, tổng quá hạn ≤ 0); `summary.situations` cộng `summary.big_books` về `overdue_customers` và `overdue_vnd`; `get_dashboard_months` bằng cộng `months[]` của `get_ledger` mọi sổ trên fixture, tháng cuối bằng `this_month`, điểm cuối bằng `receivable_vnd`; có ca sổ đổi dấu giữa hai tháng và sổ đang dư (phần âm không trừ vào đường còn phải thu).
- [ ] `test-dashboard-v7-model.js`: gom ô tình trạng và thẻ sổ lớn, đối chiếu với `summary.situations` và `summary.big_books`, sổ lớn không có dòng bảng, lọc kết hợp và xếp trong nhóm, nhãn Quá hạn lâu nhất, chuỗi 12 tháng (null không thành 0).
- [ ] `test-v7-dashboard-browser.js` ở 1280×560 và 1265×560: dải đầu, thẻ 12 tháng, hàng sổ lớn, hàng ô tình trạng và đầu bảng nằm trọn trong khung; ẩn hàng khi không có sổ lớn; 4 thẻ và tên dài không vỡ hàng; số trên trang bằng số API; không cuộn ngang ở 1280 và 390; nút ≥ 40px; chú thích tháng; API 12 tháng lỗi; link cũ `?muc=`.
- [ ] Thẻ Tình hình hiện tên tình trạng đúng với dòng của khách ở Tổng quan.
- [ ] `npm run check` và `node scripts/check-secrets.js` xanh; ảnh trước / sau bằng dữ liệu giả trong PR.
- [ ] Người dùng tự đi hết luồng trên `hao`.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`). Hai PR theo thứ tự:
  1. **Backend**: migration mới chỉ thay `get_dashboard_debt` và thêm `get_dashboard_months` (cập nhật `tools/v7_backend_functions.sql`), `web/v7_api_tables.py`, `web/v7_api_validate.py`, `FLAGGED_READS`, harness PostgreSQL; triển khai tay theo `DEPLOY-CLAUDE-01`.
  2. **Frontend**: `preview/dashboard-v7.{html,js,css}`, `preview/dashboard-v7-model.js`, nhãn ở `so-khach-v7-overview-ui.js`, chấm ở `doi-no.js`, các test tương ứng.
- Cấm: hàm ghi tiền, phân bổ, dữ liệu, quyền, dependency mới. Mỗi lúc chỉ một phiên sửa SQL.

## Hoàn tác

Revert PR frontend; revert PR backend bằng migration chạy lại bản `get_dashboard_debt` trước đó và xóa `get_dashboard_months`. Chỉ đổi hàm đọc, không đụng dữ liệu.

## Câu hỏi mở

- CÒN MỞ: C-level xem trên máy nào (cùng màn 1280×720 logic, điện thoại hay màn họp) và bao lâu một lần; nếu xem trên điện thoại cần bố cục riêng.
- CÒN MỞ: cột "Đã thu" theo DA-THU-01, nên các tháng còn khối Sheet là số ĐÃ THU của khối tháng, không phải tiền về theo ngày ([`BANG-THU-01`](../docs/decisions/bang-thu-01.md)); từ T11/2026 hai cách bằng nhau. Mặc định giữ DA-THU-01 cho khớp thẻ Tình hình.
- ĐỀ XUẤT, chờ người dùng xem bản xem: hình 12 tháng thay chỗ thẻ Thu tháng, vẽ hai hình chồng.
- ĐỀ XUẤT: mốc sổ lớn 10% và tối đa 4 thẻ. Người dùng chọn phương án B trên bản xem có mốc này, chưa nói riêng về mốc. Một sổ có thể ra vào hàng khi tỷ lệ qua mốc; nếu thấy nhảy nhiều thì xét lại.
- CÒN MỞ, chờ người dùng, trước PR backend (`situation` phụ thuộc luật này): có đổi luật "còn nợ cũ" không (đang là chỉ cần có nợ từ 3 tháng, sổ 17% bị xếp vào nhóm này chỉ vì 1% nợ). Ví dụ: tính khi nợ từ 3 tháng chiếm từ một tỷ lệ tiền quá hạn trở lên. Đổi luật thì `DASH-06` điểm 1 phải ghi lại.
