# V7: báo chuyến web còn mà Sheet không còn dòng

Trạng thái: **ĐÃ CHỐT** phạm vi (phiên điều phối giao Claude 30/10/2026 theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md)). Bổ sung cho [`SONG-SONG-01`](../docs/decisions.md#song-song-01) và [`NHAP-SHEET-02`](../docs/decisions.md#nhap-sheet-02): chỉ **báo**, người nhập quyết định. **Không đổi luật tiền**, không migration, không bảng mới.

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720 CSS) đang chạy song song Sheet – web. Sheet là sổ chính thức.

**Bối cảnh:** chuyến vào web từ hàng chờ Sheet ("Duyệt … chuyến mới"). Trước bản này, nếu sau đó dòng trên Sheet bị **xóa** (nhập nhầm, trùng, sai khách) thì web không biết: chuyến vẫn tính nợ, chỉ lộ ra ở [đối soát cuối ngày](../docs/doi-soat-cuoi-ngay.md) dưới dạng "web nhiều hơn Sheet" mà không chỉ ra dòng nào.

**Luồng:**
1. Người nhập mở sổ khách. Dưới đầu sổ có dải **"Sheet không còn dòng của N chuyến đang tính trên web [Xem]"**.
2. Bấm **Xem**: sổ cuộn tới dòng chuyến đó (bấm lại sang chuyến kế tiếp). Dòng tô **tím nhạt**, dưới số container ghi **"Sheet không còn dòng này"** và hai nút **"Xóa trên web"**, **"Giữ"**.
3. Bấm **"Xóa trên web"**:
   - Tháng đang mở: hiện dòng hỏi "Sheet không còn dòng này. Xóa hẳn chuyến X (ngày, thành tiền Y) trên web? Lịch sử ghi người xóa. [Xóa hẳn] [Thôi]". "Xóa hẳn" gọi đúng lệnh xóa chuyến có sẵn (`/api/v7/trips/delete` → `sokhach.delete_trip`), phân bổ lại phiếu thu như xóa ở ô STT.
   - Tháng khóa: không có nút xóa. Dòng hỏi báo "Tháng M/YYYY đang khóa nên chưa xóa được … Mở khóa tháng rồi bấm lại" kèm nút **"Mở khóa tháng M"** (lệnh mở khóa có sẵn, ghi Lịch sử) và **"Thôi"**. Không bỏ qua chặn khóa ([quyết định 24/10/2026](../docs/decisions/khoa-thang-2026-10-24.md)).
4. Bấm **"Giữ"** (Sheet sẽ thêm lại, hoặc web đúng): dòng hết tô, dải bớt một. Chỉ nhớ **trên máy này** cho **bản chụp Sheet hiện tại**; bản chụp Sheet mới (hash khác) thì sổ hỏi lại.

**Kết quả:** người nhập thấy ngay chuyến nào làm web nhiều hơn Sheet và xử lý trong 2–3 cú bấm.

**Không thay đổi:** không tự xóa hay ghi đè theo Sheet; chuyến được báo vẫn tính nợ cho tới khi người nhập xóa; "Giữ" không ghi gì lên server.

## Đầu ra

`GET /api/v7/ledger` trả thêm `sheet_sync.removed_items` và `sheet_sync.removed_count`; sổ khách tô và cho xử lý các chuyến đó. `/api/v7/sheet-queue` và các trường cũ của `sheet_sync` (`items`, `new_count`, `conflict_count`, `trip_types`) không đổi.

## Đối chiếu dữ liệu và code hiện có (bước 2)

- `web/v7_sheet_queue.py`: `build_queue` dựng mọi dòng bản chụp (`status` READY/INVALID…, `customer_id` sau ghép tên); `project_customer` so dòng READY của khách với sổ web (NEW/CONFLICT, ngưỡng ±3 ngày hoặc cùng booking).
- **Nhận chuyến lấy từ Sheet:** `source_ref` dạng `sheet:<sha256>:<dòng>` (xem `_source_row`) **hoặc** ghi chú `Chuyến đồng bộ` (chỉ `approve_sheet` đặt). Đọc code 30/10/2026: `get_ledger` có `source_ref` ở migration `2026-10-22-v7-nhap-sheet.sql` nhưng các bản `get_ledger` sau (từ `2026-10-22-v7-trip-review.sql` tới `2026-10-29-v7-phu-phi-b-p2.sql`) **không trả** trường này, nên trên `hao` chỉ ghi chú nhận được. Chuyến nhập tay trước `NHAP-SHEET-02` (không ghi chú, không `source_ref`) không xét.
- Ổ khóa: trường `info_editable` của chuyến trong `get_ledger` = tháng đang mở (cùng quy tắc `_month_open`).
- Xóa: `delete_trip(customer_id, expected_version, idempotency_key, trip_id)` — **không có tham số lý do**; event `trip_delete` ghi người làm và ảnh trước. Dòng hỏi `.delete-prompt` và nút `.confirm-delete` do `so-khach-v7-edit-ui.js` xử lý sẵn.
- Đầu sổ không còn bộ đếm "Chờ xử lý" (bỏ theo góp ý 23/10/2026, test giữ chặn chữ này); số chuyến hiện ở dải riêng như "Giá từ Sheet cần xem".

## Giao tiếp frontend–backend

`sheet_sync.removed_items[]`: `{trip_id, container, event_date (ISO), month, status, amount_vnd (chuỗi VND hoặc null), month_locked}`; `removed_count` = độ dài. Khi không đọc được bản chụp, `sheet_sync` dự phòng trả `removed_items: []`, `removed_count: 0`. Lỗi xóa (`MONTH_LOCKED`, `STALE_LEDGER`…) hiện trong dòng hỏi như xóa ở ô STT.

## Hành vi và bất biến

- Một chuyến được báo khi: là chuyến web lấy từ Sheet, chưa xóa, không `rejected`, có container và ngày hợp lệ, năm ≥ `QUEUE_FIRST_YEAR`; và bản chụp **không còn dòng READY nào của khách đó** cùng container (bỏ khoảng trắng, không phân biệt hoa thường) với ngày lệch ≤ 3 ngày **hoặc** cùng booking.
- Không xét dòng sổ gốc (`legacy_rows`) và chuyến không có nguồn Sheet.
- Bản chụp **không có dòng READY nào** (đọc rỗng, đổi tên tab) thì không báo gì, để một lỗi đọc không tô cả sổ.
- Dòng Sheet đổi sang khách khác hoặc thành INVALID (thiếu container…) thì chuyến web bị báo: với khách này Sheet không còn dòng đó.
- Dòng READY chưa ghép được khách (tên lạ, `NEEDS_CUSTOMER`) vẫn giữ chuyến cùng container: dòng còn trên Sheet, chỉ chưa ghép tên, nên một lỗi ghép tên không tô cả sổ khách.
- Chuyến CHỜ KIỂM được báo với "chưa tính vào số dư"; số tiền lấy nguyên từ server, trang không tính.

## Tiêu chí nghiệm thu

- [x] `tests/test_sheet_queue.py` (`RemovedSheetTripTests`): còn/không còn dòng Sheet, lệch 3 ngày (giữ) và 4 ngày (báo), cùng booking, chuyến theo `source_ref`, dòng của khách khác không khớp, dòng chưa ghép khách vẫn giữ, chuyến sổ gốc/nhập tay/đã loại/năm cũ không báo, bản chụp rỗng không báo.
- [x] `preview/test-so-khach-v7-sheet-browser.js` (Playwright 1280×720, máy chủ giả): dải đếm và nút Xem đưa focus tới dòng; "Xóa trên web" mở dòng hỏi, Thôi không gửi gì, Xóa hẳn gửi đúng `/api/v7/trips/delete`; bấm nút không mở sửa ô container; tháng khóa không có nút xóa, nút mở khóa gửi lệnh khóa có sẵn; Giữ không gửi gì, nhớ qua tải lại, hiện lại khi hash bản chụp đổi.
- [x] `npm run check` xanh (30/10/2026, đủ 8 bước gồm Playwright).
- [ ] Người nhập tự đi hết luồng trên bản thử sau deploy và xác nhận.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`)
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/web/v7_sheet_queue.py`
  - `cong-no-web-handoff/web/v7_ledger_api.py` (chỉ `sheet_sync` dự phòng)
  - `cong-no-web-handoff/tests/test_sheet_queue.py`
  - `cong-no-web-handoff/preview/so-khach-v7-sheet-ui.js`, `so-khach-v7-ui.js` (một dòng gọi), `so-khach-v7-live.html` (CSS)
  - `cong-no-web-handoff/preview/test-so-khach-v7-sheet-browser.js`
  - `docs/doi-soat-cuoi-ngay.md`, spec này
- Cấm: đổi schema/hàm SQL, luật tiền, quyền; tự xóa theo Sheet.

## Hoàn tác

Revert PR. Không có dữ liệu mới trên server; "Giữ" chỉ nằm trong `localStorage` của trình duyệt (khóa `sokhach-v7-sheet-giu:<khách>:<hash>`).

## Câu hỏi mở

- **Lý do khi xóa:** nhiệm vụ nêu "có lý do", nhưng `delete_trip` không nhận lý do và luật `V7-SO` chỉ bắt lý do khi hủy phiếu. Bản này không hỏi lý do; dòng hỏi ghi rõ "Sheet không còn dòng này", Lịch sử ghi người xóa và ảnh trước. Muốn lưu lý do vào Lịch sử cần migration thêm tham số cho `delete_trip`: CÒN MỞ.
- **`source_ref` không còn trong `get_ledger`:** khớp trực tiếp theo dòng Sheet trong `project_customer` và `trip_types` (sầu riêng cấp đông/tươi) vì vậy chỉ chạy trong test, trên `hao` rơi về khớp container + ngày. Trả lại trường này cần migration `get_ledger`: CÒN MỞ, việc riêng.
