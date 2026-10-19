# P0-02 — Phê duyệt theo phiên bản và danh tính

Trạng thái: **Quy tắc Q02 và mô hình danh tính Q01 ĐÃ CHỐT ngày 15/10/2026; chưa triển khai.** App self-host trên máy này, chỉ truy cập qua tailnet của chủ máy; mỗi người có tài khoản app riêng, session server-side xác định actor, maker/checker là hai người khác nhau. Chi tiết kỹ thuật về account lifecycle, proxy trust, app-role và DB audit mapping cần hoàn thiện trước implementation.

## Hiện trạng được xác nhận tĩnh

Tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, `cong-no-web-handoff/tools/pg_ledger_schema.sql`:

- `ledger.approve_entry(bigint)` yêu cầu `session_user` thuộc `ledger_checker`, khóa proposal bằng `FOR UPDATE`, từ chối self-approval theo `proposal.maker`, rồi đọc các `proposal_line` hiện tại để tạo posting.
- Không lưu revision/hash đã được checker duyệt; function không so sánh nội dung đã xem với nội dung post. Không có test PostgreSQL trong repo kiểm stale approval.
- `ledger.submit_entry(...)` ghi `maker=session_user`; `audit.actor` và `posting.checker` cũng lấy từ `session_user`. Đây là login PostgreSQL của phiên, không chứng minh danh tính con người hay xác thực ứng dụng.
- Schema cấp role `NOLOGIN`; đường ánh xạ login người dùng/service vào role chưa có trong repo. Role thành viên có quyền đọc/execute function được grant, không được grant DML trực tiếp trên bảng trong script này; chủ DB/superuser vẫn có quyền sửa bảng. Không mô tả test harness bằng role giả như bằng chứng auth người thật.

## Quy tắc đã chốt

Theo `docs/business-rules.md` và D01 trong `docs/decisions.md`: người nhập phải khác người duyệt; approval phải hợp lệ cho nội dung nghiệp vụ. Người dùng chốt Q02 ngày 15/10/2026: approval gắn với revision bất biến; thay đổi nghiệp vụ cần revision và approval mới; sửa trình bày không đổi nghĩa thì không. Người dùng cũng chốt self-host một máy, chỉ vào login khi nối Tailscale, và giao chọn mô hình danh tính phù hợp nghiệp vụ: mỗi người có tài khoản app riêng. Ứng dụng xác minh actor từ session server-side, không coi kết nối tailnet hay request header tự khai là maker/checker identity. Cấu hình Tailscale/proxy phải chặn bypass trực tiếp tới app. Nếu chỉ có một actor vận hành thì maker không thể tự duyệt/post.

## Hướng triển khai theo quyết định

Mỗi lần submit tạo revision bất biến hoặc hash chuẩn hóa trên toàn bộ trường tác động quyết định và tiền: khách/kỳ/loại/tổng và các dòng, ngày nghiệp vụ/ngày ghi sổ, source/evidence reference và hash, lý do cùng metadata quyết định. Approval ghi revision/hash chính xác; thay đổi các trường này tạo revision mới và approval cũ không còn hiệu lực cho bản mới. Chỉ chỉnh sửa trình bày không đổi nội dung thì không cần duyệt lại. Server/DB lấy actor từ session app đã xác thực ở boundary tin cậy; bỏ qua actor tự khai từ request payload. Lưu tách app actor, tài khoản/service kỹ thuật và DB role trong audit; kiểm chứng ánh xạ và quyền proxy/DB trước khi bật ghi.

## Câu hỏi và acceptance tương lai

Ví dụ giả: checker xem receipt 100 cho kỳ 2026-01; maker đổi thành 101 trước khi post. Đề xuất yêu cầu submit/duyệt revision mới; giữ approval cũ có thể ghi nội dung checker chưa duyệt.

Acceptance cần kiểm: duyệt đúng revision; sửa trường nghiệp vụ tạo revision mới và approval cũ bị từ chối; nội dung không đổi giữ đúng approval; thay đổi trình bày không làm phát sinh approval mới; maker tự duyệt bị từ chối; role sai/actor thiếu/actor payload giả bị từ chối; session người này không thể giả actor người khác; app không tới được qua đường ngoài Tailscale. Test PostgreSQL chỉ chứng minh cơ chế DB/role fixture; xác thực người thật và Tailscale boundary cần kiểm riêng ở ứng dụng/môi trường. Q01/Q02 đã chốt ở mức chính sách, nhưng implementation vẫn cần design/review trước khi viết DDL.
