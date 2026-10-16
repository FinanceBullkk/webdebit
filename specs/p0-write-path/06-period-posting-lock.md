# P0-06 — Khóa kỳ và ngày ghi sổ

Trạng thái: **ĐỀ XUẤT**. D07 và workflow close/reopen còn mở.

## Hiện trạng được xác nhận tĩnh

Tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, `cong-no-web-handoff/tools/pg_ledger_schema.sql` có `event_date`, `posting_date`, `debt_period` tách riêng. `ledger.submit_entry(...)` và `ledger.approve_entry(...)` chỉ chặn `posting_date` trước `cutover.first_posting_date`; `ledger.balance_as_of(date)` lọc posting theo `posting_date`. Schema không có bảng trạng thái kỳ/ngày, close/reopen API hay lock chung giữa approve và close. Chưa có test PostgreSQL boundary/concurrency trong repo.

## Quy tắc đã chốt và đề xuất

`docs/business-rules.md` tại cùng revision chốt ngày xe nhập kho là event date của chuyến; ngày nhập, duyệt, ghi sổ, kỳ nợ và ngày chốt khác nhau. Không suy posting date hoặc debt period từ event date.

Đề xuất: post và close kỳ dùng chung serialization point/lock, để thao tác cạnh tranh tuyến tính rõ ràng; khi close đã thắng thì post vào kỳ đó bị từ chối. Reopen phải có quyền, lý do và audit hoặc thay bằng adjustment kỳ đang mở theo policy.

## Ví dụ và acceptance sau quyết định

Chuyến vào kho 31/01, nhập 03/02 sau close tháng 01: giữ event date 31/01; posting date và debt period theo chính sách được chốt, không tự chọn backdate. Approve đồng thời close không được lọt posting sau khóa. Q07/Q08 chặn policy; test kỹ thuật có thể kiểm serialization sau khi contract xác định outcome.
