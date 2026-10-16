# P0-02 — Phê duyệt theo phiên bản và danh tính

Trạng thái: **ĐỀ XUẤT**. Nguyên tắc maker/checker khác nhau đã chốt; danh tính chuẩn, quyền vận hành và hiệu lực approval còn mở.

## Hiện trạng được xác nhận tĩnh

Tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, `cong-no-web-handoff/tools/pg_ledger_schema.sql`:

- `ledger.approve_entry(bigint)` yêu cầu `session_user` thuộc `ledger_checker`, khóa proposal bằng `FOR UPDATE`, từ chối self-approval theo `proposal.maker`, rồi đọc các `proposal_line` hiện tại để tạo posting.
- Không lưu revision/hash đã được checker duyệt; function không so sánh nội dung đã xem với nội dung post. Không có test PostgreSQL trong repo kiểm stale approval.
- `ledger.submit_entry(...)` ghi `maker=session_user`; `audit.actor` và `posting.checker` cũng lấy từ `session_user`. Đây là login PostgreSQL của phiên, không chứng minh danh tính con người hay xác thực ứng dụng.
- Schema cấp role `NOLOGIN`; đường ánh xạ login người dùng/service vào role chưa có trong repo. Role thành viên có quyền đọc/execute function được grant, không được grant DML trực tiếp trên bảng trong script này; chủ DB/superuser vẫn có quyền sửa bảng. Không mô tả test harness bằng role giả như bằng chứng auth người thật.

## Quy tắc đã chốt

Theo `docs/business-rules.md` và D01 trong `docs/decisions.md` tại cùng revision: người nhập phải khác người duyệt; approval phải hợp lệ cho nội dung nghiệp vụ. Cách xác thực actor, ủy quyền/tài khoản chia sẻ và xử lý sửa nội dung sau submit chưa chốt.

## Đề xuất

Mỗi lần submit tạo revision bất biến hoặc hash chuẩn hóa trên toàn bộ trường tác động quyết định và tiền, gồm lines, kỳ, nguồn, bằng chứng tham chiếu và scope phù hợp. Approval ghi revision/hash chính xác; mọi thay đổi tạo revision mới và vô hiệu approval cũ. Server/DB lấy actor từ principal đã xác thực ở boundary tin cậy; bỏ qua actor tự khai từ request payload. Phân biệt người thật, tài khoản ứng dụng/service và DB role trong audit.

## Câu hỏi và acceptance tương lai

Ví dụ giả: checker xem receipt 100 cho kỳ 2026-01; maker đổi thành 101 trước khi post. Đề xuất yêu cầu submit/duyệt revision mới; giữ approval cũ có thể ghi nội dung checker chưa duyệt.

Kiểm stale revision, không đổi revision, cùng actor, role sai, actor thiếu và actor payload giả. Test PostgreSQL chỉ chứng minh cơ chế DB/role fixture; xác thực người thật cần kiểm riêng ở ứng dụng/SSO. Xem [Q01](decisions-needed.md#q01--nguồn-danh-tính-makerchecker) và [Q02](decisions-needed.md#q02--approval-gắn-với-nội-dung-nào) trước task implementation.
