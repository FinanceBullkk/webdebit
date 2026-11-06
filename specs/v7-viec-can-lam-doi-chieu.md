# Việc cần làm: số nợ lệch, bảng đối chiếu, ba tab

Trạng thái: ĐÃ CHỐT (người dùng, 6/11/2026, [`VIEC-DOI-CHIEU-01`](../docs/decisions/viec-doi-chieu-01.md)). Bản thử trên canvas, trang "Việc cần làm: kiến trúc mới".

## Người dùng và luồng (bước 1, bắt buộc với frontend)

Chủ sổ (trên 40 tuổi, màn thấy 1280×560) mở tab khi được báo có khách lệch hoặc khi cần tin số nợ. Câu hỏi theo thứ tự:

1. Số nợ hôm nay có đúng không? → dòng đầu trang.
2. Khách nào lệch, bao nhiêu, vì sao? → tab Số nợ lệch, bảng khách.
3. Do khoản nào, ghi khoản đó thì còn lệch bao nhiêu? → bảng đối chiếu.
4. Tiền đúng rồi còn gì chưa gọn? → tab Dọn chi tiết.
5. Máy vừa ghi gì? → tab Máy đã làm.

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
| Máy đã làm | `inbox.auto.*_items` có `at`, `reconcile` khách `FIXED` | Đã có |

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

## Tiêu chí nghiệm thu

- Ở 1280×560, trang đóng khoản chi tiết thấy đủ: dòng đầu, ba tab, dòng khách, các khoản, Còn lệch, nút Ghi.
- Khoản tháng khóa ghi xong đúng số, tháng khóa lại, Lịch sử mang tên người bấm ở lệnh ghi.
- 18 dòng chỉ khác phụ phí hiện phụ phí web → Sheet, không còn hai số bằng nhau.
- `npm run check` xanh; kiểm trên `hao` chỉ đọc, không tự bấm ghi trên sổ thật.
- Người dùng tự đi hết luồng trên `hao` (CÒN MỞ).
