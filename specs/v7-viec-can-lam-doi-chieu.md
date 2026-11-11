# Việc cần làm: số nợ lệch, bảng đối chiếu, ba tab

Trạng thái: ĐÃ CHỐT (người dùng, 6/11/2026, [`VIEC-DOI-CHIEU-01`](../docs/decisions/viec-doi-chieu-01.md)). Bản thử trên canvas, trang "Việc cần làm: kiến trúc mới".

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Chủ sổ (trên 40 tuổi, màn thấy 1280×560) mở tab khi được báo có khách lệch hoặc khi cần tin số nợ. Câu hỏi theo thứ tự:

1. Số nợ hôm nay có đúng không? → dòng đầu trang.
   - Tab TONG trên Sheet có cộng đủ các tab khách không? → một ý trong dòng đầu khi khớp; một dòng riêng ngay dưới khi chưa khớp, bấm ra danh sách chỗ phải sửa trên Sheet ([`KIEM-TONG-01`](../docs/decisions/kiem-tong-01.md), 11/11/2026).
2. Khách nào lệch, bao nhiêu, vì sao? → tab Số nợ lệch, bảng khách.
3. Do khoản nào, ghi khoản đó thì còn lệch bao nhiêu? → bảng đối chiếu.
4. Tiền đúng rồi còn gì chưa gọn? → tab Dọn chi tiết.
5. Máy và người đã ghi gì, hôm nay hay ngày khác? → tab Đã làm ([`HOAT-DONG-01`](../docs/decisions/hoat-dong-01.md)).

Luồng chính: mở trang → khách lệch lớn nhất đã mở sẵn → tích khoản, số Còn lệch đổi ngay → Ghi → xem nợ trước → sau và tháng khóa → Xác nhận → số mới, có Hoàn tác. Không làm gì thì máy xem lại ở lượt sau.

## Đối chiếu dữ liệu và code hiện có (bước 2, bắt buộc với frontend)

| Cần | Lấy từ | Ghi chú |
| --- | --- | --- |
| Khớp bao nhiêu, khách nào lệch, lý do | `GET /api/v7/inbox` → `reconcile` | Đã có |
| Tổng Sheet của khách | `reconcile.customers[].sheet_total_vnd` | Lượt đối soát gần nhất |
| Tổng web, phiên bản sổ | `get_ledger` | Đọc mới mỗi lần |
| Khoản và số tiền từng khoản | `v7_sheet_fix.plan` trên bản chụp giá và phiếu mới nhất | Cùng đường của máy |
| Từng dòng, số dòng Sheet | Dòng trong nhóm của `plan` | Không có link Sheet vì thiếu `gid` |
| Ghi | `v7_sheet_fix.apply_fix(..., actor=người bấm)` | Tháng khóa: `in_month` mở, ghi, khóa lại |
| Giữ số web | `keep_sheet_task` từng dòng | Nợ không đổi |
| Hoàn tác | `undo_sheet_batch` trong `in_month` | Chỉ giá và phiếu; không thêm hàm SQL |
| Đã làm (HOAT-DONG-01) | `GET /api/v7/activity?day=` → `get_activity(date)`: event của ngày (giờ VN), mọi sổ, kèm tên sổ, container, số phiếu, tên loại phụ phí | Thêm 9/11/2026 |
| Số trên nhãn tab Đã làm | `inbox.auto.today_*`, `reconcile` khách `FIXED` | Đã có, giữ |
| Tab TONG cộng đủ không (KIEM-TONG-01) | `reconcile.tong` của máy đối soát: tháng, `matched`, `blank_on_tong`, `differs`, `unknown_names`, `gap_vnd` ([spec máy](v7-may-doi-soat.md#kiểm-tab-tong-kiem-tong-01)) | Không thêm API; gộp "chỉ khác tên" và xếp thứ tự ở model |

## Đầu ra

- `web/v7_api_doi_chieu.py`: `GET /api/v7/sheet/doi-chieu?customer=ID`, `POST /api/v7/sheet/doi-chieu/ghi`, `/giu`, `/hoan-tac`.
- `web/v7_sheet_fix.py`: `apply_fix` thêm tham số thu khóa lệnh để hoàn tác.
- `preview/viec-can-lam-doi-chieu-model.js` (tính tiền, không DOM), `preview/viec-can-lam-doi-chieu.js` (vẽ), sửa `viec-can-lam.js`, `-table.js`, `-inbox.js`, `.css`, `.html`.
- Test: `tests/test_v7_api_doi_chieu.py`, `preview/test-viec-can-lam-doi-chieu.js`, `preview/test-viec-can-lam-doi-chieu-browser.js`.

## Giao tiếp frontend–backend

`GET /api/v7/sheet/doi-chieu?customer=7`:

```json
{"customer_id": 7, "version": 12, "web_vnd": "5210000000", "sheet_total_vnd": "5274200000", "checked_at": "2026-11-06T10:12:00+07:00",
 "reason": "NO_EXACT_FIX", "sheet_editing": true, "sheet_last_edit_at": "2026-11-06T10:00:00+07:00", "web_ahead_vnd": "0", "shuffled_months": [],
 "prices_sha256": "…", "receipts_sha256": "…",
 "groups": [{"id": "prices:2026-10", "kind": "prices", "month": "2026-10", "count": 18, "delta_vnd": "58400000", "locked": true, "undoable": true,
             "rows": [{"key": "legacy:21", "status": "CONFLICT", "container": "…", "date": "2026-10-03", "source_row": 412, "web_unit_price_vnd": "60000000", "web_other_fee_vnd": "3400000",
                       "sheet_unit_price_vnd": "60000000", "sheet_other_fee_vnd": "12900000", "delta_vnd": "9500000", "source_fingerprint": "…"}]}]}
```

- Khách không có trong `reconcile.customers` thì `sheet_total_vnd` là `null`, không phải 0. `null` hiện `—`.
- `POST …/ghi`: `{"customer_id", "expected_version", "prices_sha256", "receipts_sha256", "items": [{"id", "delta_vnd", "rows": ["legacy:21"] | null}]}`. `rows` chỉ cho nhóm giá, `null` là cả nhóm. Trả `{"complete": true, "version", "before_vnd", "after_vnd", "written", "undo": {"command_keys", "months"} | null}`.
- `POST …/giu`: `{"customer_id", "expected_version", "idempotency_key", "rows": [{"target_kind", "target_id", "source_fingerprint"}]}`.
- `POST …/hoan-tac`: `{"customer_id", "expected_version", "idempotency_key", "command_keys", "months"}`.
- Lỗi: `STALE_LEDGER` (sổ đổi), `STALE_SHEET` (bản chụp đổi, hoặc số của khoản khác số người đã xem), `SHEET_SNAPSHOT_UNAVAILABLE` (503).

## Hành vi và bất biến

- Không có khoản nào được chọn sẵn; nút Ghi tắt tới khi chọn.
- Số tiền là số nguyên VND dạng chuỗi; cộng bằng BigInt ở model. Lệch khác 0 mà nhỏ hơn 0,05 triệu thì ghi đủ đồng, không làm tròn thành 0.
- Server tính lại mọi khoản và so với số người đã xem; khác thì không ghi gì.
- Mất kết nối khi ghi: "Thử lại" gửi lại đúng yêu cầu; lần trước đã ghi thì phiên bản sổ đã đổi nên server từ chối, không ghi hai lần, rồi tải lại số thật.
- Ghi lỗi giữa chừng: tháng đã mở vẫn được khóa lại; trang tải lại để thấy số thật.
- Đang hiện bản gần nhất của tab thì mọi nút ghi khóa, vẫn xem và đổi tab được.
- Tải nền không đè lựa chọn đang tích; khoản không còn thì bỏ khỏi lựa chọn.
- Trạng thái: chưa có lượt đối soát, máy lỗi, kết quả cũ, ghi xong không khớp, tab chưa có sổ, không có khách lệch, đọc khoản lỗi có Thử lại.

## Dòng tab TONG (KIEM-TONG-01)

Chỉ đọc: việc sửa nằm trên Sheet, web không ghi gì. Số lấy từ cùng lượt đối soát của dòng đầu trang (`DoiChieuModel.tongView`).

- **Khớp đủ:** chỉ thêm "TONG tháng 10 khớp" vào các ý của dòng đầu. Chỉ có tên khác tên tab mà số khớp thì thêm ", 1 tên khác tên tab". Không thêm dòng.
- **Chưa khớp:** một dòng riêng ngay dưới, cùng nhịp với dòng đầu, vừa một dòng ở 1280: câu trả lời trước ("Tab TONG tháng 10 thiếu 326,7 tr so với các sổ", thừa nếu TONG nhiều hơn), rồi đếm từng loại (sổ để trống, dòng khác sổ, tên lạ, tên khác tên tab), nút "Xem N dòng". Không đổi màu dòng đầu, vì dòng đầu nói về web so với Sheet.
- **Danh sách khi mở:** bốn cột Khách · Trên TONG · Theo sổ, cuối tháng · Cần làm trên Sheet. Thứ tự: dòng TONG khác sổ, sổ để trống, tên lạ (mỗi nhóm số lớn trước, kể cả số âm), rồi dòng chỉ khác tên. Ô trống ghi "trống", không có số thì `—`. Tên sổ mở sổ; tên lạ không có link. Dưới bảng: cộng TONG, cộng các sổ quy về cuối tháng, số dòng khớp.
- **Chỉ khác tên:** tên trên TONG không ứng sổ nào mà số bằng đúng tới từng đồng số của đúng một sổ để trống, và không tên lạ nào khác cùng số, thì gộp thành một dòng của sổ đó, kèm "Trên TONG: <tên>". Lệch một đồng, hai sổ cùng số hay hai tên cùng số thì không gộp.
- **Sổ đang lệch Sheet** (có trong danh sách khách lệch): số theo sổ tính từ web nên có thể chưa đúng; cột Cần làm nói xem khách đó ở bảng dưới trước.
- **Không đọc được tab TONG** hoặc lượt đó lỗi: chỉ một ý "chưa đọc được tab TONG" / "lượt này chưa kiểm được tab TONG" trong dòng đầu, không lộ mã. Quá nhiều khách lệch hoặc file cũ chưa có `tong`: không nói gì về TONG.
- Danh sách mở hay đóng giữ qua các lần tự tải lại; nút giữ chỗ bấm sau khi vẽ lại, bấm được cả khi đang hiện bản gần nhất.

## Tab Đã làm (HOAT-DONG-01)

- `GET /api/v7/activity` (hôm nay) hoặc `?day=yyyy-mm-dd`; sai dạng hoặc ngày sau hôm nay → 422 `INVALID_DAY`. Trả `{day, today, prev_day, next_day, total, events[], trips[], legacy_rows[], receipts[], fee_types[]}`; `events` mới trước, tối đa 2.000, cùng hình dạng Lịch sử của sổ, thêm `customer`, `actor_name`. `prev_day`/`next_day` là ngày gần nhất có việc.
- Lô dán chỉ giữ `trip_id, container, event_date, date, unitPriceVnd, status, note` từng chuyến.
- Câu chữ dùng chung `preview/so-khach-v7-lich-su-cau.js` với khung Lịch sử của sổ.
- Hiện thành bảng cột Giờ · Người làm · Sổ · Việc · Chi tiết · Ghi chú · Mở sổ, chia nhóm theo loại việc như bộ lọc Lịch sử của sổ (`groupOf`): Chuyến, Thu tiền, Giá và phụ phí, Khóa tháng, Việc khác. Tiêu đề nhóm có số việc và số từng việc; trong nhóm, cùng việc đứng liền nhau, mới nhất trước. Cột Ghi chú bỏ chữ "Ghi chú:" và gộp ghi chú trùng của lô nhiều chuyến (9/11/2026, người dùng yêu cầu).
- Tab đọc khi mở; hôm nay đọc lại theo nhịp tự tải 60 giây, ngày cũ đọc một lần. Lỗi đọc có Thử lại.

## Tiêu chí nghiệm thu

- Ở 1280×560, trang đóng khoản chi tiết thấy đủ: dòng đầu, ba tab, dòng khách, các khoản, Còn lệch, nút Ghi.
- Khoản tháng khóa ghi xong đúng số, tháng khóa lại, Lịch sử mang tên người bấm ở lệnh ghi.
- 18 dòng chỉ khác phụ phí hiện phụ phí web → Sheet, không còn hai số bằng nhau.
- `npm run check` xanh; kiểm trên `hao` chỉ đọc, không tự bấm ghi trên sổ thật.
- Dòng TONG: `preview/test-viec-can-lam-tong.js` (thứ tự, gộp chỉ khác tên và các ca không gộp, sổ đang lệch Sheet, không có kết quả), `preview/test-viec-can-lam-tong-browser.js` (dòng vừa một dòng ở 1280, mở và đóng danh sách, giữ chỗ bấm, 1280×560 vẫn thấy dòng đầu, dòng TONG, ba tab và khách lệch, màn hẹp không tràn ngang, tên chữ Hán dài, các trạng thái khớp, chưa đọc được, lỗi, bỏ qua).
- Người dùng tự đi hết luồng trên `hao` (CÒN MỞ).
