# Máy tự đối soát Sheet–web và tự sửa khi khớp

Trạng thái: ĐÃ CHỐT (người dùng, 4/11/2026, [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md))

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Chủ sổ (trên 40 tuổi, laptop 1280×720) mở tab Việc cần làm, mang theo ba câu hỏi: web có đúng với Sheet không; máy vừa tự sửa gì; còn gì mình phải quyết.

1. Đầu tab có một dòng: lần đối soát gần nhất lúc mấy giờ, bao nhiêu khách khớp và chiếm bao nhiêu phần trăm số nợ, hôm nay máy đã sửa bao nhiêu khách, bao nhiêu khách web đi trước Sheet, bao nhiêu khách cần xem. Xanh khi không còn gì phải xem; vàng khi có khách cần xem, có tab khách còn nợ mà máy chưa tạo được sổ, lần chạy lỗi, hoặc kết quả đã cũ; đỏ khi máy ghi xong mà không khớp. Tab chưa tạo được sổ luôn hiện thành một câu ngay dưới dòng này, kèm tên tab, số còn nợ và lý do, vì tỷ lệ khớp chưa tính tới chúng.
2. Bấm "Xem": danh sách các khách đó, khách cần xem trước, mỗi dòng có số lệch (web − Sheet, triệu), một câu kết luận và đường mở sổ.
3. Bảng việc bên dưới mặc định ẩn sổ đã khớp Sheet, có dòng báo đã ẩn bao nhiêu sổ và nút hiện lại. Chờ kiểm, số dư đầu, mặt hàng vẫn hiện.
4. Việc máy đã ghi hiện ở "Máy đã tự làm hôm nay" và trong Lịch sử từng sổ, người làm "Máy (theo Sheet)".

Không còn gì cần xem thì chủ sổ không phải làm gì.

## Đầu ra

- `tools/v7_reconcile_auto.py`: mỗi giờ từ 7 tới 22 giờ VN (timer `v7-reconcile-auto` trên `hao`) tải xlsx sổ gốc, làm sạch, so tổng từng khách, tự sửa khách lệch khi khớp đúng. Không có `--fix` thì chỉ báo sẽ ghi gì.
- `web/v7_sheet_fix.py`: gom việc thành nhóm, chọn tổ hợp, ghi bằng lệnh có sẵn. `apply_fix` bắt buộc chỉ rõ người làm: lượt đối soát là `may-theo-sheet`, gọi tay là người ra lệnh; mở/khóa tháng vẫn ghi là máy để lượt nền khóa lại được nếu nơi gọi chết giữa chừng.
- `reconcile.json` (mode 600, có tên khách và số tiền) và `reconcile-log.jsonl` (mỗi lượt một dòng, chỉ số đếm và tổng tiền) trong `/var/lib/webdebit-sheet-sync/`.
- `GET /api/v7/inbox` thêm `reconcile` và `sheet_matched` của từng sổ; tab Việc cần làm hiện kết quả.
- `v7_reconcile_sheet.py --can-du-months`: so từng tháng theo cách web tính ([`CAN-DU-01`](../docs/decisions/can-du-01.md)).
- `tools/v7_reconcile_hints.py`: máy đoán chỗ gây lệch khi không tự sửa được ([`CHAN-DOAN-LECH-01`](../docs/decisions/chan-doan-lech-01.md)), mục dưới.
- Mỗi lượt kiểm thêm tab TONG có cộng đủ các tab khách không ([`KIEM-TONG-01`](../docs/decisions/kiem-tong-01.md)), mục dưới. Chỉ báo.

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

| Cần | Lấy từ | Ghi chú |
| --- | --- | --- |
| Tổng Sheet từng khách | `v7_export_clean.build_books` + `export`, rồi `v7_reconcile_sheet.read_sheet` | Đúng đường của đối soát chính thức; khách bị giữ như `--hold-out` |
| Tổng web từng khách | `get_ledger` qua `PsqlDirect`, `v7_reconcile_sheet.ledger` | Không đi qua HTTP nên không cần danh tính Tailscale |
| So tổng, so tháng | `v7_reconcile_sheet.reconcile` | So tháng dùng `can_du=True` |
| Hàng chờ phiếu, giá | `project_receipts`, `project_prices` trên bản chụp dựng từ **cùng bản tải** (`v7_price_snapshot.build_all`) | Tổng và việc cùng một trạng thái Sheet, nên phép khớp có nghĩa |
| Dòng chỉ có TỔNG, dòng không container, web đi trước | `v7_price_queue.classify` trả `SHEET_NO_PRICE`, `NO_CONTAINER` | Hàng chờ giá không hiện các loại này |
| Lệnh ghi | `record_receipt`, `delete_legacy_trip` (khoản thu sổ gốc, `XOA-THU-GOC-01`), `write_price_items`, `adjust_month`, `delete_month_adjustment`, `set_month_lock` | Không thêm hàm SQL |
| Phiếu không ngày đã ghi được nhận lại | Tham chiếu `Sheet #<dấu dòng>: …`, như `review_sheet_receipt` | Hàng chờ ghép bằng tiền tố này |
| Dòng không container đã ghi được nhận lại | Dòng điều chỉnh có ghi chú bắt đầu bằng `FEE_NOTE`, cùng tháng, cùng số | Dòng sổ gốc không container cùng tháng, cùng số cũng là đã có. Dòng điều chỉnh của máy mà Sheet không còn dòng tương ứng thành nhóm hủy (`delete_month_adjustment`) |
| Biết trước tổng đổi bao nhiêu | Chuyến: `đơn giá + phụ phí` trừ số đang tính (chưa có giá là 0). Dòng sổ gốc: `_change_legacy` tính lại `counted_vnd = đơn giá + phụ phí`, xóa khoản thu cộng lại đúng `counted_vnd` | Khoản thu có `counted_differs` thì không tính trước được, không vào nhóm |

Đo trên `hao` lúc thiết kế (chỉ đọc): một lượt khoảng 9 phút ở `Nice=10` (làm sạch 4 phút, đọc giá và phiếu 2,5 phút, đọc 236 sổ 1,5 phút), bộ nhớ khoảng 125 MB. Bản giả và ảnh chụp không dùng số khách thật.

## Giao tiếp frontend–backend (bước 5, khi có)

`GET /api/v7/inbox` thêm:

```json
{"reconcile": {"version": 1, "checked_at": "2026-11-04T08:05:00+07:00", "mode": "fix", "counts": {"KHOP": 233, "LECH_TONG": 3},
  "total": 236, "matched_web_vnd": "…", "all_web_vnd": "…", "matched_ids": [1, 3],
  "customers": [{"customer": "…", "customer_id": 2, "status": "LECH_TONG", "reason": "NO_EXACT_FIX", "sheet_total_vnd": "…",
                 "web_total_vnd": "…", "difference_vnd": "…", "web_ahead_vnd": "0",
                 "groups": [{"kind": "receipts_edited", "month": "2026-07", "count": 8, "delta_vnd": "-117", "chosen": false}]}],
  "months_differ": [], "outside_tabs": [{"customer": "…", "sheet_total_vnd": "…", "last_month": "2026-10", "reason": "TONG_DIFFERS"}],
  "tong": {"month": "2026-10", "matched": 64, "blank_on_tong": [{"book": 7, "name": "…", "expected_vnd": "…"}], "differs": [],
           "unknown_names": [{"name": "…", "end_vnd": "…"}], "tong_sum_vnd": "…", "expected_sum_vnd": "…", "gap_vnd": "…"},
  "last_error": {"at": "…", "reason": "HTTPError"}},
 "books": [{"customer_id": 1, "sheet_matched": true}]}
```

- `reconcile` là `null` khi chưa có lượt nào hoặc file hỏng; hộp việc vẫn chạy.
- `customers` gồm khách chưa khớp và mọi khách máy đã sửa trong ngày (`fixed_at`). Tiền là chuỗi số nguyên; chưa biết là `null`, không phải 0.
- `reason`: `FIXED`, `WOULD_FIX`, `WEB_AHEAD`, `NO_EXACT_FIX`, `SHEET_SHUFFLED`, `AMBIGUOUS_FIX`, `NOTHING_TO_WRITE`, `TOO_MANY_GROUPS`, `TOO_MANY_DIFFERENT`, `WRITE_ERROR`, `CHECK_ERROR`, `VERIFY_FAILED`, `HELD`, `CHI_CO_SHEET`, `CHI_CO_WEB`, `THIEU_SO`. `FIXED` với `status` `LECH_TONG` là đã sửa, phần còn lại là web đi trước Sheet.
- `outside_tabs`: tab khách còn nợ, có phát sinh (tiền chuyến hoặc tiền thu) từ tháng 10/2026, tức từ tháng nạp V7, mà máy chưa tạo được sổ ([`MAY-TAO-SO-01`](../docs/decisions/may-tao-so-01.md)). `reason` là `NOT_ON_TONG`, `TONG_DIFFERS` hoặc `TAB_UNREADABLE`. Tab cũ hơn là bản sao, tab nháp đã xem lúc nạp. Bản `reconcile.json` trước khi có trường này thì coi như rỗng.
- `tong`: phép kiểm tab TONG ([`KIEM-TONG-01`](../docs/decisions/kiem-tong-01.md)), mục dưới. `month` là tháng (yyyy-mm) của khối TONG mới nhất; `matched` là số dòng TONG bằng đúng số kỳ vọng của sổ; `blank_on_tong` (`book`, `name`, `expected_vnd`) là sổ có số kỳ vọng khác 0 mà TONG không có số; `differs` (`name` trên TONG, `book`, `tong_vnd`, `expected_vnd`) là dòng TONG khác số kỳ vọng; `unknown_names` (`name`, `end_vnd`) là tên có số mà không ứng với đúng một sổ; `gap_vnd` là cộng TONG trừ cộng số kỳ vọng. Không kiểm được thì chỉ có `month: null` và `skipped`. Bản `reconcile.json` trước khi có trường này thì coi như chưa kiểm.
- `last_error`: lần chạy mới nhất hỏng, phần còn lại là kết quả lần đạt trước.
- `edit_log`, và `sheet_last_edit_at`, `sheet_editing` ở từng khách: tab vừa được sửa thì không tính "cần xem", xem [`SHEET-LOG-01`](../docs/decisions/sheet-log-01.md) và [spec](sheet-log-doi-soat.md).
- `hints`, `hints_explain` ở từng khách: xem mục "Máy đoán chỗ lệch" dưới. Bản cũ không có thì màn hiện như trước.
- `sheet_matched`: sổ có trong `matched` của lượt gần nhất, tổng hiện tại bằng tổng lúc đó, và không còn dòng giá khác giá Sheet (`prices_conflict`).

## Máy đoán chỗ lệch (CHAN-DOAN-LECH-01)

Khách `LECH_TONG` mà kết luận không phải `FIX` hay `WEB_AHEAD`, và khách `HELD`, có thêm `hints` (tối đa 8, gần số cần đổi nhất lên trước). `hints_explain` là `true` khi có tổ hợp trong **danh sách trả về** có `delta_vnd` cộng đúng bằng `tổng Sheet + web đi trước − tổng web`. Giao diện nói “Có tổ hợp gợi ý khớp số tiền lệch, cần kiểm chứng”: khớp số học chưa xác nhận nguyên nhân, cũng không khẳng định mọi gợi ý cộng lại khớp. `delta_vnd` là số nợ web đổi nếu giả thuyết đúng; tiền là chuỗi số nguyên.

Gợi ý về sổ có `hints_basis = {version, prices_sha256, receipts_sha256, web_total_vnd, sheet_total_vnd}` từ chính dữ liệu dùng chẩn đoán. Dòng đang đóng chỉ hiện gợi ý khi phiên bản sổ trong inbox bằng `hints_basis.version` và tổng web, tổng Sheet của dòng bằng basis; mở đối chiếu thì cần thêm phiên bản sổ của dữ liệu chi tiết, hai hash nguồn và hai tổng của dữ liệu chi tiết đang hiện cùng khớp. Tổng NULL hoặc thiếu bằng chứng giữ là chưa biết, không xác nhận gợi ý. Khi tải lại đang chờ hoặc lỗi, giữ số đang xem nhưng ẩn gợi ý cho tới khi đọc thành công; dữ liệu đổi thì chờ lượt đối soát mới. Chỉ ẩn ba kiểu tính tiền (`receipt_twice`, `price_review`, `sheet_row_missing`); hai kiểu `ahead_*` không có basis, không phải lời khuyên sửa tiền, nên giữ. Gợi ý `chain_break` của khách `HELD` chỉ mô tả chuỗi số trên Sheet ở lượt đã ghi thời điểm, không phụ thuộc phiên bản sổ web.

| `kind` | Lấy từ | Trường |
| --- | --- | --- |
| `receipt_twice` | `receipts` của sổ: chưa hủy, không phải cấn trừ, cùng ngày, cùng số; Sheet có ngày đọc được thì so đúng ngày bằng bộ đọc ngày của hàng chờ phiếu; số phiếu chưa rõ ngày được tính là khả năng đối ứng cho mỗi nhóm để tránh báo nhầm | `date`, `amount_vnd`, `pids`, `delta_vnd` = số × (số phiếu web − max(1, số phiếu Sheet đúng ngày + số phiếu Sheet chưa rõ ngày)); chỉ báo khi dương |
| `price_review` | Dòng Sheet của sổ qua `v7_price_queue.classify`, trạng thái `MANUAL`, `CONFLICT`, `MONTH_LOCKED`, Sheet tính khác web | `status`, `row`, `container`, `date`, `sheet_vnd`, `web_vnd` |
| `sheet_row_missing` | Như trên, trạng thái `NOT_FOUND`, có tiền | `row`, `container`, `date`, `sheet_vnd` |
| `chain_break` | `checks` của sổ bị giữ: tháng đầu tiên `source_cumulative_vnd` ≠ `replay_cumulative_vnd` | `month`, `sheet_end_vnd`, `expected_end_vnd` |
| `ahead_other_book` | Chuyến đang tính là web đi trước mà Sheet ghi ở tab của sổ khác: cùng container, lệch không quá 3 ngày (thiếu ngày thì cùng tháng) | `container`, `date`, `amount_vnd`, `other` (tên sổ kia, hoặc tên tab nếu chưa có sổ) |
| `ahead_old` | Chuyến đang tính là web đi trước, quá 14 ngày kể từ ngày chuyến mà tab của sổ vẫn chưa có | `container`, `date`, `amount_vnd`, `days` |

Hai kiểu `ahead_*` (từ 10/11/2026) không phải lời đoán chỗ lệch: không có `delta_vnd`, không tính vào `hints_explain`, và có ở mọi khách có tiền web đi trước, kể cả `WEB_AHEAD` và `FIXED`. Tối đa 8, chuyến ở tab sổ khác lên trước rồi tới chuyến để lâu nhất, đứng sau các lời đoán khác. Khách có gợi ý kiểu này thì màn xếp vào "Số nợ lệch" thay vì "web đi trước, không cần làm gì"; cột Lệch giữ nguyên web − Sheet.

Lời đoán không đổi `reason`, không làm máy ghi. Đoán lỗi thì bỏ qua, in mã lỗi ra stderr, lượt chạy tiếp. Giá Sheet rõ là 0 vẫn so với web; chỉ số chưa biết mới bỏ qua. Màn: cột "Vì sao" hiện tối đa hai câu và số chỗ còn lại; bảng đối chiếu khi mở có khung "Chỗ máy tìm ra" với đủ các câu còn hiệu lực.

Đo trên bản tải và sổ thật 9/11/2026 (chỉ đọc): khách thứ nhất ra `receipt_twice` + `sheet_row_missing`, cộng đúng bằng số lệch; khách thứ hai ra `price_review` đúng bằng số lệch; khách bị giữ ra `chain_break` đúng tháng và đúng số đồng Sheet bỏ mất.

Độ nhiễu, đo cùng ngày trên cả 239 sổ thật (đều đang khớp): nếu sổ nào cũng bị coi là lệch, chỉ 3 sổ có gợi ý, cả 6 gợi ý là `sheet_row_missing` (dòng tháng 3 không ở sổ này, phí hủy cont đã tính kiểu khác). Không có `receipt_twice` thừa: điều kiện so với Sheet loại 4 cặp phiếu thật của 2 sổ. Gợi ý chỉ hiện ở sổ đang lệch, và `hints_explain` cho người đọc biết lời đoán có đủ hay không.

## Kiểm tab TONG (KIEM-TONG-01)

Mỗi lượt, sau khi máy sửa và tạo sổ, máy đọc khối mới nhất của tab TONG trong cùng bản tải và so với từng sổ web bằng đúng `read_tong`, `audit_tong` của lệnh audit chuyển hẳn ([spec](v7-cutover-audit.md)). Phát sinh và thu từng tháng của tab lấy từ bản chụp giá và phiếu dựng từ cùng bản tải, qua `sheet_months`, cũng dùng chung với audit.

- Số kỳ vọng của một sổ ở cuối tháng TONG = tổng web lúc lưu − web đi trước − phát sinh các tháng sau trên tab + thu ghi ở khối các tháng sau. Web đi trước chỉ tính khi nó giải thích trọn chỗ lệch của khách ở lượt này (`difference_vnd` bằng `web_ahead_vnd`): như audit đọc `reconcile.json`, thêm khách máy vừa sửa mà còn phần đi trước.
- Tên trên TONG ghép bằng chữ và số đã bỏ dấu, không dùng bảng tên khác. Sổ máy vừa tạo ở lượt này cũng được so.
- Không ghi gì. Không đổi `live_tong`, `tong_agrees`, `admit_new_tabs` hay điều kiện máy ghi.
- Không có tab TONG hoặc bố cục lạ: `skipped` là `TONG_KHONG_DOC_DUOC`, không dựng bản chụp. Hơn 40 khách lệch: `TOO_MANY_DIFFERENT`. Lỗi bất kỳ: `ERROR` kèm `error` là mã (tên loại lỗi), stderr có một dòng mã; lượt vẫn lưu kết quả đối soát như thường.
- Bản chụp giá và phiếu dựng một lần cho cả lượt: lượt có khách lệch dùng lại bản đã dựng cho việc tìm cách sửa, lượt mọi khách khớp thì dựng riêng.
- `reconcile-log.jsonl` và stdout chỉ thêm `tong` là số đếm (`month`, `matched`, `blank`, `differs`, `unknown_names`), hoặc `skipped` và `error`.
- Sổ đang lệch Sheet thì số kỳ vọng vẫn tính theo web, nên dòng TONG "lệch" của sổ đó có thể do sổ web; màn hình nên dẫn tới dòng đối soát của khách đó.

## Nguồn quyết định

- [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md), [`SONG-SONG-01`](../docs/decisions/song-song-01.md), [`GIA-NGUON-01`](../docs/decisions/gia-nguon-01.md), [`MAY-KHOA-01`](../docs/decisions/may-khoa-01.md), [`VCL-GIU-01`](../docs/decisions/vcl-giu-01.md), [`XOA-THU-GOC-01`](../docs/decisions/xoa-thu-goc-01.md), [`CAN-DU-01`](../docs/decisions/can-du-01.md), [`KIEM-TONG-01`](../docs/decisions/kiem-tong-01.md), [`WEB-CHINH-01`](../docs/decisions/web-chinh-01.md).
- CÒN MỞ: cách chuyển hẳn khi Sheet vẫn là nơi nhập (mục F4 của [checklist](../docs/song-song-checklist.md)); kênh cảnh báo khi máy lỗi.

## Hành vi và bất biến

- **Từ 25/11/2026 máy chỉ tự ghi phần thêm** ([`WEB-CHINH-01`](../docs/decisions/web-chinh-01.md) (3): web là sổ chính thức). Tổ hợp vẫn tìm trên mọi nhóm như dưới đây, rồi `machine_part` tách: máy ghi phiếu sẵn sàng, phiếu không ngày và dòng giá `adds_only` (web chưa có đơn giá, phụ phí web trống hoặc bằng Sheet, dòng sổ gốc đã tính thì số tính lại bằng đúng số cũ); còn `receipts_gone`, `receipts_edited`, `fee_rows`, `fee_undo` và dòng giá đè số web (giá Sheet khác giá web, đổi giảm trừ âm, thay phụ phí web, đổi số sổ gốc đã tính) để người. Họ phiếu (`receipts*`) hay họ chuyến (`prices`, `fee_*`) có phần để người thì phần thêm cùng họ cũng để người: phiếu Sheet mới cạnh phiếu Sheet bỏ có thể là chính phiếu đó bị sửa số, giá vào chuyến cạnh dòng điều chỉnh chưa hủy là tính đôi. Có phần để người thì kết luận `WEB_KEPT` kèm `kept` (loại, tháng, số dòng, tiền đổi); đích đọc lại sau khi ghi trừ phần để người; khách `KHOP` có `WEB_KEPT` không vào `matched`. Chế độ chỉ kiểm vẫn báo `WOULD_FIX` khi có phần thêm, kèm `kept`. Bảng đối chiếu vẫn ghi được mọi nhóm dưới tên người bấm. Các bullet dưới về ghi giá khác, hủy phiếu, dòng điều chỉnh tả việc người bấm ghi hoặc cách máy tính tổ hợp, không còn là việc máy tự ghi.
- Chỉ ghi khi đúng một tổ hợp nhóm có tổng đổi bằng đúng `tổng Sheet + web đi trước − tổng web`. Lệch 1 đồng là không ghi. Nhóm không đổi tiền không ghi. Từ 19/11/2026 ([`THAY-PHIEU-SHEET-01`](../docs/decisions/thay-phieu-sheet-01.md)): **mọi nhóm cộng lại** bằng đúng số đó thì ghi hết, dù một phần nhỏ hơn cũng ra đúng số. Ghi hết là web theo Sheet tới từng dòng; phần nhỏ hơn là trùng số tình cờ (sổ thật 19/11: Sheet đổi giá hai chuyến và đổi phiếu bù nhau, cùng lúc có một phiếu mới đúng bằng số lệch; máy chỉ ghi phiếu mới, tổng khớp mà chi tiết sai).
- Nhóm `receipts_gone`: phiếu web ghi từ Sheet mà Sheet không còn dòng đó ([spec hàng chờ phiếu](v7-receipt-queue.md), bước 7). Nợ tăng đúng tổng các phiếu. Ghi trước mọi nhóm khác bằng `void_receipt`, lý do `GONE_REASON`, không xét ổ khóa tháng; hoàn tác ở bảng đối chiếu không khôi phục được hủy phiếu nên tổ hợp có nhóm này không có nút Hoàn tác.
- **Khách đã khớp tổng** cũng được xét (`settle_matched`, từ 19/11/2026): Sheet sửa hai chỗ bù nhau thì tổng không đổi, trước đây máy không bao giờ nhìn tới. Có việc chờ mà mọi nhóm cộng lại bằng đúng phần web đi trước (thường là 0) thì ghi hết, kết luận `FIXED`. Không bù đủ, hoặc tháng có đơn giá đổi chỗ, thì không ghi, kết luận `DETAIL_DIFFERS`: dòng vẫn `KHOP` nhưng nằm trong danh sách, hiện ở "Số nợ lệch", không vào `matched` nên việc chờ của sổ không bị ẩn, và audit chuyển hẳn tính là chưa khớp. Từ 27/11/2026 nhóm giá tổng 0 mà có dòng đổi tiền (Sheet sửa giá vài chuyến cùng tháng bù nhau) vẫn là việc chờ (`has_work`), không bị bỏ như nhóm không đổi tiền; theo WEB-CHINH-01 đó là phần để người, kết luận `WEB_KEPT`. `details` trong `reconcile.json` đếm số khách đã xét và kết luận. Dựng bản chụp hỏng thì chỉ bỏ phần này (`details.skipped`), lượt vẫn đạt.
- Web đi trước không tính tháng có dòng điều chỉnh trừ đúng bằng phần đó, vì tiền đã ra khỏi sổ. Trừ không đúng bằng thì không suy ra được dòng điều chỉnh là của chuyến nào, tính như thường.
- Chuyến web đi trước để quá 14 ngày, hoặc Sheet ghi ở tab của sổ khác, vẫn được cộng vào đích như cũ (máy vẫn ghi việc đúng khác của khách), nhưng khách có thêm gợi ý `ahead_old` / `ahead_other_book` và màn xếp là phải xem (`ahead_to_check`). Container dùng lại ở chuyến khác, cách xa ngày, không tính là "ở tab sổ khác".
- Tháng có đơn giá đổi chỗ vòng tròn (`shuffled_months`) không có nhóm giá: khớp tổng không phân biệt được giá của container nào, nên không ghi và báo `SHEET_SHUFFLED`. Kiểu này chỉ bắt được khi web đã có giá để so.
- Đơn giá trượt qua một ô trống (`handed_on_months`) cũng vào `shuffled_months` của kết quả: chuyến web có giá mà dòng Sheet của nó trống giá lẫn TỔNG, và cùng tháng có dòng `CONFLICT` mà giá Sheet bằng đúng giá web của chuyến đó. Không có luật này thì phần hở của vòng được tính là web đi trước và tổ hợp vẫn khớp.
- Dòng Sheet có tiền mà không container, trùng tháng và trùng số với một chuyến web có giá mà tab không còn container đó (`lost_container_money`), là cùng một khoản tiền: mỗi dòng ghép một chuyến, chuyến không tính là đi trước, dòng không thành `fee_rows`. Dòng điều chỉnh máy đã ghi cho dòng đó thành `fee_undo`. Khác tháng hoặc khác số thì vẫn là hai việc riêng.
- `--booking-only` (từ 25/11/2026, dùng sau khi thôi theo Sheet sổ nợ ngày 1/12, [runbook](../docs/v7-deploy-runbook.md#tắt-máy-theo-sheet-sổ-nợ-ngày-1122026-web-chinh-01--chưa-chạy)): chỉ đọc DB và bản chụp booking, chạy phép so sổ web ↔ booking (DU-CHUYEN-01) rồi ghi `booking-web.json`; không tải Sheet, không đọc hay ghi `reconcile.json`, không đi cùng `--fix`/`--xlsx`; `--source-dir` chỉ bắt buộc ở chế độ đối soát.
- Không ghi Sheet. Không đổi hàm SQL, quyền, luật phân bổ. Mọi lệnh có `expected_version`: người vừa sửa sổ thì lệnh lỗi `STALE_LEDGER`, lượt sau tính lại.
- Khóa chống ghi trùng gắn phiên bản sổ lúc bắt đầu lượt; phiếu đã ghi thì hàng chờ đã ghép, không chọn lại.
- Phiếu ghi từ một dòng Sheet rồi bị hủy trên web: hàng chờ phiếu xếp dòng đó là `WEB_VOIDED` ([spec hàng chờ phiếu](v7-receipt-queue.md)), không vào nhóm nào, nên máy không ghi lại. Khách lệch đúng bằng số đó và hiện là cần xem.
- Tháng khóa: mở, ghi, khóa lại; lệnh lỗi vẫn khóa lại; API tắt giữa chừng thì lượt nền của API khóa lại sau 10 phút (`machine_left_open`).
- Stdout không có tên khách hay số tiền. Bản tải và bản làm sạch nằm trong thư mục tạm, xóa ngay sau lượt.
- Lần chạy lỗi không xóa kết quả cũ, chỉ thêm `last_error`; unit thoát khác 0.
- VND nguyên chính xác; NULL không phải 0.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_sheet_fix.py`: nhóm việc, số tổng đổi, chọn tổ hợp (lệch 1 đồng, nhiều tổ hợp, nhóm không đổi tiền), đơn giá đổi chỗ, thứ tự ghi, tháng khóa, phiếu không ngày ghi xong rời hàng chờ, gọi tay ghi đúng người làm và giữ nguyên khóa chống ghi trùng; đơn giá trượt qua ô trống không có nhóm giá (trước và sau khi máy giá ghi dòng sẵn sàng), dòng mất container ghép với chuyến web cùng tháng cùng số; chuyến đi trước cần xem (để lâu, ở tab sổ khác, đúng 14 ngày thì chưa hỏi, container dùng lại, tiền đã trừ bằng điều chỉnh). `preview/test-viec-can-lam-doi-chieu*.js`: khách có gợi ý `ahead_*` nằm ở "Số nợ lệch", câu từng kiểu, khung khi mở không tô "Khớp".
- [x] `tests/test_v7_reconcile_auto.py`: cả lượt từ xlsx giả: khớp, chỉ báo, sửa rồi khớp, không khớp thì không ghi, lỗi ghi, web đi trước, khách bị giữ, quá nhiều khách lệch, lần chạy lỗi giữ kết quả cũ, phiếu máy ghi bị người hủy thì lượt sau không ghi lại.
- [x] `tests/test_v7_reconcile_sheet.py`: `--can-du-months`.
- [x] `tests/test_v7_inbox.py`: `reconcile`, `sheet_matched`, file hỏng.
- [x] WEB-CHINH-01 (25/11/2026): `tests/test_v7_sheet_fix.py` (`MachinePartTests`: tách dòng giá thêm/đè, luật cùng họ), `tests/test_v7_reconcile_auto.py` (`WebKeptTests` trên `settle`/`settle_matched`: phiếu mới ghi còn giá Sheet khác chờ người, chuyến chưa giá vẫn nhận giá, phiếu Sheet bỏ hay sửa không hủy và không ghi phiếu mới, dòng tiền không container và hủy dòng điều chỉnh không ghi, khách khớp có thay đổi bù nhau không ghi, chế độ chỉ kiểm, sổ 104 tháng 10 vẫn `SHEET_SHUFFLED`, sổ 134 chuyến đã chuyển sổ chỉ báo lệch), `tests/test_v7_inbox.py` (máy giá 15 phút chỉ ghi dòng `adds_only`). Cho `machine_part` trả cả tổ hợp như trước thì 7 trong 10 ca `WebKeptTests` đỏ.
- [x] Nhóm giá bù nhau trong tháng (27/11/2026, sổ 141): `WebKeptTests.test_matched_book_whose_price_changes_cancel_out_in_one_month_waits_for_a_person`, `tests/test_v7_api_doi_chieu.py` (nhóm tổng 0 vẫn hiện và ghi được, nhóm rỗng không hiện), `preview/test-viec-can-lam-doi-chieu-browser.js` (câu "tổng tháng bằng nhau", xem từng chuyến). Bỏ vế nhóm giá của `has_work` thì hai ca Python đỏ; bỏ câu mới thì ca trình duyệt đỏ.
- [x] `tests/test_v7_reconcile_hints.py`, `tests/test_v7_reconcile_auto.py`: bốn kiểu đoán, lệch 1 đồng thì không "giải thích được", khách bị giữ, đoán lỗi không đổi kết luận; `preview/test-viec-can-lam-doi-chieu*.js`: câu từng kiểu, cột Vì sao, khung khi mở, không tràn ở 1280.
- [x] Hồi quy 10/11/2026: `tests/test_v7_reconcile_hints_regression.py` kiểm số phiếu thừa, phiếu khác ngày, thiếu ngày/số, giá 0 và tổ hợp sau giới hạn danh sách; `preview/test-viec-can-lam-hints-browser.js` kiểm phiên bản sổ, hash nguồn, tổng web/Sheet, thiếu bằng chứng và đang tải; `preview/test-viec-can-lam-doi-chieu-browser.js` kiểm luồng tải đầy đủ khi tổng Sheet đổi hoặc request mới lỗi; `tests/test_v7_reconcile_auto.py` kiểm nguồn chẩn đoán và không phát sinh lệnh ghi. Gộp lại trên `main` 18/11/2026 (sau KIEM-TAB-01, MAY-DOI-SOAT-01 chuyến đi trước): dòng đóng so phiên bản sổ, giữ gợi ý `ahead_*`. Dữ liệu giả.
- [x] `preview/test-viec-can-lam-table-browser.js`: dải kết quả, thứ tự danh sách, ẩn và hiện sổ đã khớp, sổ ẩn không bị chọn ngầm, các trạng thái xanh, vàng, đỏ, lỗi, cũ, chưa có lượt nào; không tràn ngang ở 1280.
- [x] Thử trên bản sao DB của `hao`: tổng khách sửa khớp đúng, khách khác không đổi, mọi tháng máy mở đã khóa lại, chạy lại không ghi thêm, checker đạt ([nhật ký](../docs/deploys/2026-11-04-may-doi-soat.md)).
- [x] Bật trên `hao`, đối soát chính thức sau lượt đầu cho kết quả như dự kiến (cùng nhật ký).
- [ ] Chủ sổ tự đi hết luồng trên `hao`: đọc dải, mở danh sách, mở sổ, soát phiếu máy ghi.
- [x] `tests/test_v7_reconcile_auto.py`, kiểm TONG: khớp (tên khác dấu, gạch, khoảng trắng vẫn ghép), quy các tháng sau về tháng TONG, để trống (ô trống và không có dòng), tên không ứng sổ nào, dòng lệch, so với tổng sau khi máy sửa và dựng bản chụp một lần, trừ web đi trước, sổ vừa tạo, bố cục lạ thì bỏ qua và không dựng bản chụp, lỗi chỉ thành mã, hơn 40 khách lệch thì bỏ qua; số đếm ra log và stdout không có tên. Phá từng luật trong bộ nhớ (bỏ phần đi trước, không trừ tháng sau, dùng tổng trước khi sửa, bỏ sổ vừa tạo, dựng bản chụp hai lần, để lỗi lọt ra) thì test đỏ.
- [x] Đo chỉ đọc trên `hao` 11/11/2026 (bản tải 19:12 giờ VN, mã nhánh chép vào thư mục thử, lượt không `--fix`, `--output` và `--work-dir` riêng, 445 giây): khối tháng 10, 63 dòng khớp, 15 sổ để trống, 0 dòng lệch, 1 tên không ứng sổ nào. `v7_cutover_audit.py` của `main` chạy trên cùng bản tải và cùng `reconcile.json` (không `--tong-alias`) ra giống hệt: cùng id sổ, cùng số kỳ vọng, cùng cộng và chênh. Tên lạ đó là tên khác của một trong 15 sổ, số khớp tới từng đồng; audit có `--tong-alias` thì ra 64 dòng khớp, 14 sổ để trống.
- [x] Đầu tab Việc cần làm hiện kết quả kiểm TONG: một ý trong dòng đầu khi khớp, một dòng riêng và danh sách khi chưa khớp ([spec màn](v7-viec-can-lam-doi-chieu.md#dòng-tab-tong-kiem-tong-01), `preview/test-viec-can-lam-tong*.js`, dữ liệu giả). Chủ sổ tự xem trên `hao`: CÒN MỞ.
