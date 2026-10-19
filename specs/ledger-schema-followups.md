# Ledger schema: các điểm còn lại sau audit F1–F3

Trạng thái: ĐÃ CHỐT giao việc. Người dùng duyệt ngày 16/10/2026 trong chat, sau khi đọc review PR #13. Phạm vi chỉ gồm schema cho DB mới và harness PostgreSQL trên dữ liệu giả. Không migration, không deploy.

## Đầu ra

`tools/pg_ledger_schema.sql` xử lý thêm hai điểm:

- `ledger.balance_as_of` báo lỗi `ledger cutover missing` khi thiếu cutover. Hiện tại nó âm thầm bỏ số opening.
- `request_reversal` lấy ngày nghiệp vụ theo giờ Việt Nam, không theo giờ máy chủ.

Harness kiểm thêm: mọi hàm mà màn hình viewer đọc trong một câu lệnh phải giữ loại STABLE. Đây là điều kiện để F1 (đọc một snapshot) còn đúng.

## Nguồn quyết định

- F3 trong PR #13: thiếu cutover phải báo lỗi, không được bỏ qua ngưỡng. Mục này áp cùng nguyên tắc cho đường đọc.
- FUTURE-01 trong [sổ quyết định](../docs/decisions.md): "hôm nay" là ngày theo giờ Asia/Ho_Chi_Minh.
- Phát hiện 1, 3, 4 trong review PR #13 ngày 16/10/2026.

## Hành vi và bất biến

- `ledger.balance_as_of` vẫn là `LANGUAGE sql STABLE`. Bỏ subquery `(SELECT as_of FROM ledger.cutover WHERE singleton)` và thay bằng hàm mới `ledger.cutover_as_of()`. Hàm mới là `plpgsql STABLE SET search_path = pg_catalog, ledger`, trả `as_of` và RAISE `ledger cutover missing` khi không có dòng cutover. Viết theo mẫu `ledger.first_posting_date()`.
- Cấp `GRANT EXECUTE ON FUNCTION ledger.cutover_as_of()` cho `ledger_maker`, `ledger_checker`, `ledger_reader`. Lý do: `balance_as_of` không phải SECURITY DEFINER nên người đọc cần quyền gọi hàm này.
- `request_reversal`: đổi `event_date` từ `current_date` sang `ledger.business_today()`. Không đổi gì khác.
- Khi có cutover, số liệu không đổi: opening, movement và balance giữ nguyên kết quả. VND nguyên; NULL opening vẫn là NULL.
- Không đổi view `ledger.balance`, `submit_entry`, `approve_entry`, `reject_entry`, quyền hiện có và code viewer.

## Tiêu chí nghiệm thu

Thêm các case sau vào `tools/test_pg_ledger_schema.py`, dùng hàm `record(...)` sẵn có:

- [ ] `volatility/read_functions_stable`: `pg_proc.provolatile = 's'` cho `ledger.balance_as_of`, `ledger.cutover_as_of`, `ledger.first_posting_date`, `ledger.business_today`.
- [ ] `missing_cutover/balance_as_of_rejected`: chạy với vai trò `reader`/role đọc có sẵn trong harness. Khi đã xóa cutover, `SELECT * FROM ledger.balance_as_of(<date>)` lỗi P0001 `ledger cutover missing`. Đặt case trong khối đã xóa và khôi phục cutover hiện có.
- [ ] `balance/opening_unchanged_with_cutover`: khi có cutover, tổng `balance_as_of` bằng giá trị đã kiểm trước khi sửa. Dùng lại số liệu harness đang có, không thêm fixture mới nếu không cần.
- [ ] `reversal/event_date_is_vietnam_today`: proposal reversal mới có `event_date` bằng `(now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date`. Tính độc lập với hàm của schema, giống cách case `posting_date` hiện có đang làm.
- [ ] Toàn bộ harness exit 0. Các case cũ vẫn pass; riêng `repro_success` có sẵn từ trước vẫn giữ nguyên.
- [ ] Unittest đạt và code viewer không đổi.

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: codex
- Được sửa:
  - `cong-no-web-handoff/tools/pg_ledger_schema.sql`
  - `cong-no-web-handoff/tools/test_pg_ledger_schema.py`
- Ngân sách diff: 100 dòng
- Lệnh kiểm:
  - `{python} cong-no-web-handoff/tools/test_pg_ledger_schema.py --report %TEMP%\codex-ledger-schema-followups.json`
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests`
  - `git diff --quiet HEAD -- cong-no-web-handoff/web`
- Cấm:
  - Sửa `web/`, `tests/`, fixture P0 hoặc tài liệu.
  - Thêm dependency, framework, helper hay file mới ngoài hàm `ledger.cutover_as_of()`.
  - Đổi view `ledger.balance`, chữ ký hàm có sẵn, quyền có sẵn hoặc cách tính tiền.
  - Viết migration. Việc này thuộc spec `ledger-migration-f1f3` sau.
  - Chạy DDL ngoài harness container, chạm `hao`, Sheet hay DB thật.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; ghi câu hỏi ở mục "Câu hỏi mở" bên dưới.

## Hoàn tác

Revert commit. Thay đổi chỉ ở script schema dùng cho DB mới, không đụng dữ liệu.

## Bằng chứng

<Agent ghi lệnh đã chạy và kết quả. Reviewer kiểm thêm: chạy harness mới với schema trước khi sửa phải fail ở các case mới.>

## Câu hỏi mở

- (chưa có)
