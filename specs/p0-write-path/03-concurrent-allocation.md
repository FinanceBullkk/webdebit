# P0-03 — Phân bổ đồng thời

Trạng thái: **ĐỀ XUẤT**. FIFO kỳ nợ cũ trước đã chốt; hạn mức, ngoại lệ và concurrency chưa được nghiệm thu.

## Hiện trạng được xác nhận tĩnh

Tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, `cong-no-web-handoff/tools/pg_ledger_schema.sql`, `ledger.submit_entry(...)` kiểm tổng các line của **một proposal** bằng `total_vnd`. Nó không tính tổng allocation đã post từ proposal/receipt khác, không khóa receipt/customer-period dùng chung. `ledger.approve_entry(...)` chỉ khóa proposal row đang duyệt. Chưa có PostgreSQL test đồng thời trong repo.

Probe F02/T03 được ghi trong workspace-only `design/2026-10-15/feedback/response.md` thuộc `design/2026-10-15/schema-draft.sql` ngoài repo; đó là báo cáo probe lịch sử về schema khác, không phải test của schema trên.

## Quy tắc đã chốt và đề xuất

`docs/business-rules.md` tại revision trên chốt thu mới ưu tiên kỳ nợ cũ trước, tách receipt khỏi allocation, giữ số dư theo khách + kỳ. Không quyết tiền dư, override FIFO, thiếu baseline hoặc concurrency.

Đề xuất: trong transaction duy nhất, khóa/serialize nguồn tiền và các bucket dư nợ theo thứ tự xác định, đọc lại số đã commit, áp hạn mức rồi ghi. Nếu hai yêu cầu cạnh tranh, kết quả phải tuyến tính: một yêu cầu thành công, yêu cầu kia đọc lại và thành công trong phần còn lại hoặc bị từ chối/retry rõ ràng.

## Ví dụ và acceptance sau khi chốt policy

Receipt 100 phân bổ 80+20 trong cùng receipt có tổng đúng 100; hai receipt/proposal đồng thời cùng đòi 80 từ receipt 100 không được làm tổng vượt 100. Hai receipt 70 và 50 cùng nhắm khoản nợ 100 không được làm phân bổ tổng vượt mức cho phép đã duyệt. Cần hai connection DB độc lập với barrier/lock coordination, không sleep tùy ý; kiểm kết quả sau commit của cả hai.

Q03/Q04 trong [quyết định còn mở](decisions-needed.md) chặn nghiệm thu production policy. Test harness có thể tái hiện thiếu aggregate guard mà không chọn chính sách tiền dư/override.
