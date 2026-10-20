# Migration ledger cho DB đang chạy: F2/F3 và các sửa sau đó

Trạng thái: ĐÃ CHỐT giao việc. Người dùng duyệt ngày 16/10/2026 trong chat. **Chỉ chạy sau khi spec [ledger-schema-followups](ledger-schema-followups.md) đã được commit**, vì migration phải gồm cả phần sửa đó. Chỉ viết và kiểm trên container; việc áp lên `hao` là bước riêng, cần người dùng duyệt.

## Đầu ra

File migration `cong-no-web-handoff/tools/migrations/2026-10-16-ledger-f2f3.sql`. Áp nó lên một DB tạo bằng schema trước PR #13 (`7bd5d21`) thì cho ra các hàm và quyền giống hệt DB tạo mới bằng `pg_ledger_schema.sql` hiện tại.

## Nguồn quyết định

- FUTURE-01 trong [sổ quyết định](../docs/decisions.md). F3 trong PR #13.
- Spec [ledger-schema-followups](ledger-schema-followups.md).

## Hành vi và bất biến

- Toàn bộ migration nằm trong một transaction (`BEGIN; … COMMIT;`, có `\set ON_ERROR_STOP on`).
- Chỉ dùng `CREATE OR REPLACE FUNCTION` cho các hàm mới hoặc đã đổi: `first_posting_date`, `business_today`, `cutover_as_of`, `submit_entry`, `approve_entry`, `request_reversal`, `balance_as_of`. Thân hàm chép nguyên văn từ `pg_ledger_schema.sql`.
- Sau đó REVOKE và GRANT đúng như cuối `pg_ledger_schema.sql` cho các hàm này.
- Không tạo hay xóa role, bảng, view hay dữ liệu. Không đụng `opening`, `posting`, `proposal`, `audit`, `cutover`.
- Chạy lại lần hai không lỗi và không đổi kết quả.

## Tiêu chí nghiệm thu

- [ ] Harness `tools/test_pg_ledger_schema.py` nhận thêm tham số `--base-schema PATH --migration PATH`. Khi có hai tham số này, harness tạo DB bằng base schema rồi áp migration (hai lần), thay vì tạo bằng schema hiện tại. Không đổi hành vi mặc định khi không truyền tham số.
- [ ] Ở chế độ migration, toàn bộ case hiện có vẫn pass. Riêng `repro_success` có sẵn từ trước vẫn giữ nguyên.
- [ ] Ở chế độ migration, harness tạo thêm một DB thứ hai bằng `pg_ledger_schema.sql` hiện tại trong cùng container. Sau đó so `pg_get_functiondef` và `proacl` của mọi hàm trong schema `ledger` giữa hai DB; phải khớp hoàn toàn.
- [ ] Chế độ mặc định (không có tham số) vẫn exit 0.

## Phạm vi agent

Mục này là hợp đồng với agent thực hiện; `scripts/agent-run.ps1` đọc nó để kiểm diff.

- Agent: codex
- Được sửa:
  - `cong-no-web-handoff/tools/migrations/2026-10-16-ledger-f2f3.sql`
  - `cong-no-web-handoff/tools/test_pg_ledger_schema.py`
- Ngân sách diff: 320 dòng
- Lệnh kiểm:
  - `git show 7bd5d21:cong-no-web-handoff/tools/pg_ledger_schema.sql > %TEMP%\ledger-schema-7bd5d21.sql && {python} cong-no-web-handoff/tools/test_pg_ledger_schema.py --base-schema %TEMP%\ledger-schema-7bd5d21.sql --migration cong-no-web-handoff/tools/migrations/2026-10-16-ledger-f2f3.sql --report %TEMP%\codex-ledger-migration.json`
  - `{python} cong-no-web-handoff/tools/test_pg_ledger_schema.py --report %TEMP%\codex-ledger-default.json`
  - `cd cong-no-web-handoff && {python} -m unittest discover -s tests`
  - `git diff --quiet HEAD -- cong-no-web-handoff/tools/pg_ledger_schema.sql cong-no-web-handoff/web`
- Cấm:
  - Sửa `pg_ledger_schema.sql`, `web/`, fixture P0 hoặc tài liệu.
  - Thêm dependency, framework hay công cụ migration. Chỉ dùng một file SQL thuần.
  - Áp migration lên bất kỳ DB nào ngoài harness container; chạm `hao`, Sheet hay DB thật.
- Khi cần vượt phạm vi: dừng, không tự mở rộng; ghi câu hỏi ở mục "Câu hỏi mở" bên dưới.

## Hoàn tác

Revert commit. Migration chưa áp ở đâu ngoài container test.

## Bằng chứng

<Agent ghi lệnh đã chạy và kết quả.>

## Câu hỏi mở

- CÒN MỞ: DB trên `hao` có đúng là schema `7bd5d21` không. Người dùng hoặc Claude phải kiểm chỉ đọc (so `pg_get_functiondef`) trước khi duyệt áp migration.
