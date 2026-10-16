# P0-01 — Ghi sổ nguyên tử

Trạng thái: **ĐỀ XUẤT**, chưa được duyệt làm thiết kế cuối.

## Hiện trạng được xác nhận tĩnh

Tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, `cong-no-web-handoff/tools/pg_ledger_schema.sql`, function `ledger.approve_entry(bigint)` chèn các dòng posting, cập nhật proposal và thêm audit trong cùng lời gọi SQL. Lỗi trong function làm thất bại statement/transaction của caller; nếu caller đã bọc nhiều thao tác trong một transaction rộng hơn, ranh giới commit do caller điều khiển. Chưa có test PostgreSQL trong repo chứng minh rollback line cuối. `ledger.submit_entry(...)` lưu proposal, lines và audit trong cùng function nhưng cũng chưa có test tích hợp. Đây là đọc mã, không phải kết quả chạy.

## Quy tắc đã chốt

Posting bất biến sau ghi; pending không đổi số dư; chỉ nghiệp vụ đủ nguồn/chứng cứ/duyệt mới được tính; opening không được cộng lại.

## Đề xuất và ranh giới transaction

Một lệnh post nên kiểm tra quyền, trạng thái/version và kỳ; ghi trọn bộ posting lines; chuyển trạng thái; và ghi audit trong **một transaction DB**. Nếu bất cứ bước nào lỗi trước commit, toàn bộ thay đổi của thao tác phải rollback. Không cấp quyền DML trực tiếp cho role ứng dụng.

Commit thành công nhưng kết nối mất trước khi client nhận response là trạng thái không chắc chắn đối với client. Client phải retry bằng idempotency key để truy vấn lại kết quả, không tạo posting thứ hai. Idempotency contract nằm ở [P0-04](04-idempotency.md).

## Câu hỏi và test

Ví dụ giả: proposal có 3 line, line 3 lỗi constraint. Đề xuất all-or-nothing: không posting line nào, trạng thái vẫn pending và không có audit approve. Chấp nhận ghi một phần sẽ làm trạng thái/approval/balance không đại diện cùng nghiệp vụ.

Acceptance tương lai: happy path có đúng N lines + status + audit; lỗi line cuối rollback cả ba; approve lặp không sinh set posting mới; role ứng dụng không thể sửa/xóa posting. Cần test PostgreSQL riêng. Quyền DML cụ thể phụ thuộc mô hình role được chốt khi thiết kế.
