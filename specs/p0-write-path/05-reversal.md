# P0-05 — Đảo giao dịch bất biến

Trạng thái: **ĐỀ XUẤT**. Không sửa đè posting đã ghi; phạm vi và chính sách đảo/hoàn tiền còn mở.

## Hiện trạng được xác nhận tĩnh

Tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, `cong-no-web-handoff/tools/pg_ledger_schema.sql`:

- `ledger.request_reversal(...)` đọc đúng một row `ledger.posting`, tạo một proposal line từ row đó; không dựng một proposal bao trọn các line của receipt gốc. Nếu receipt được post thành nhiều line, caller hiện phải yêu cầu đảo từng posting line riêng.
- `posting_one_reversal` unique trên `posting.original_posting_id` chặn đảo trùng từng posting line khi approve, nhưng không cung cấp một thao tác nguyên tử đảo cả receipt nhiều line. `request_reversal` đọc row gốc không `FOR UPDATE`; concurrency và retry chưa được test.
- Hàm đặt `event_date=current_date`; không nhận ngày nghiệp vụ từ caller. Reversal proposal được approve thành signed amount đối dấu theo line gốc.
- Chưa có test PostgreSQL cho exact inverse, đảo một phần hay hoàn tiền thực tế.

## Quy tắc đã chốt và quyết định còn mở

Posting bất biến, sửa sai bằng đảo/điều chỉnh có lý do/audit là nguyên tắc trong `docs/business-rules.md` tại cùng revision. Chưa chốt đảo whole document hay một line, cách xử lý khi đã có allocation liên quan, hoặc quan hệ với hoàn tiền ngân hàng.

## Đề xuất và ví dụ

Mỗi reversal phải tham chiếu đối tượng gốc, tạo signed inverse chính xác trên phạm vi được duyệt và lưu lý do/chứng cứ/actor. Không xóa lịch sử. Ví dụ giả: receipt 100 gồm line 60 và line 40; phát hiện line 40 sai. Đảo line 40 giữ line 60, nhưng cần quyết định quyền/phiếu; đảo cả receipt rồi lập lại rõ audit nhưng tạo biến động nhiều hơn. Hoàn tiền ngân hàng 20 là cash movement riêng, không tự suy từ bút toán đảo.

Q06 chặn acceptance policy. Khi đã chốt, test single/double/concurrent reversal, rollback nhiều line và giao dịch cash refund riêng; mọi thao tác nhiều line phải có ranh giới transaction nguyên tử.
