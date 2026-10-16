# Review P0 write-path specs

Ngày: 15/10/2026. Reviewer: cùng tác nhân đã sửa bộ tài liệu; đây là **self-review**, không phải review độc lập hoặc phê duyệt nghiệp vụ. Phạm vi: 9 file spec hiện có, cross-reference trong repo, và đối chiếu tĩnh với SQL/docs tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`. Không chạy PostgreSQL, DDL, code test hay truy cập hệ thống thật. Repo không có PostgreSQL integration test cho schema này.

## Phát hiện

| ID / mức | Bằng chứng tại revision | Ảnh hưởng | Trạng thái xử lý |
|---|---|---|---|
| R01 / P1 | `cong-no-web-handoff/tools/pg_ledger_schema.sql`, `ledger.approve_entry(bigint)`: posting insert, proposal status update và audit nằm trong cùng function/statement; chưa có test tích hợp chứng minh rollback khi lỗi trễ. | Spec không được gọi transaction DB là bằng chứng test; commit thành công nhưng response mất cần retry-safe contract riêng. | Đã ghi ranh giới transaction vs client response, lỗi trễ/rollback và giới hạn test tại `01-atomic-posting.md`, `next-task.md`. Chưa chạy test. |
| R02 / P1 | Cùng SQL, `ledger.proposal_line` có thể được đọc lại khi approve; không có content revision/hash. Role thường không được grant DML trực tiếp, nhưng owner/superuser có thể sửa; không có guard/hash bảo đảm approval đúng nội dung. | Approval có thể ghi nội dung khác nếu sửa qua quyền có thể truy cập; cần bảo vệ cả version và quyền, không suy từ row lock. | Đã tách cơ chế DB role khỏi xác thực người thật và thêm stale-content repro/decision Q01–Q02. Chưa kiểm runtime auth. |
| R03 / P1 | `submit_entry` kiểm sum line trong một proposal; schema không có receipt entity/allocation ledger riêng hoặc aggregate guard xuyên proposal; `approve_entry` chỉ khóa proposal row. | Không chứng minh tổng phân bổ xuyên request, concurrency cap hoặc FIFO. | Đã nêu rõ scope hiện tại, phân biệt test lỗi với acceptance tương lai. Probe F02 ở `design/2026-10-15/feedback/response.md` thuộc DDL khác, không được gán cho SQL repo. |
| R04 / P1 | `request_reversal` lấy một `posting_id`, tạo một proposal line; `posting_one_reversal` unique trên `original_posting_id`; `event_date=current_date`. | Guard là theo từng posting line, không đảo nguyên tử toàn receipt nhiều line; không được mô tả nhầm là whole-receipt reversal. | Đã sửa `05-reversal.md` và thêm Q06; policy whole/partial/refund còn mở. |
| R05 / P1 | `proposal.request_key` unique; không có payload hash/result replay. `proposal_receipt_source_once` áp dụng riêng theo `source_ref` receipt chưa rejected. | Duplicate key fail thay vì trả kết quả cũ; key khác có thể tái nhập cùng source; amount không phải identity. | Đã tách key/source identity/receipt/allocation trong `04-idempotency.md` và Q05. |
| R06 / P1 | `submit_entry`/`approve_entry` chỉ so `posting_date` với `cutover.first_posting_date`; không có close/reopen table/API hay lock. | Không có cơ chế khóa kỳ và không chứng minh race close-vs-post an toàn. | Đã ghi giới hạn hiện trạng và acceptance tương lai ở `06-period-posting-lock.md`, Q07–Q08. |
| R07 / P2 | Repo SQL có ba ngày `event_date`, `posting_date`, `debt_period`; `balance_as_of` lọc posting theo `posting_date`. | Không được gộp ngày nghiệp vụ/ngày ghi sổ/kỳ nợ; fixture hoặc lịch sử probe không quyết định policy nhập muộn. | Đã tách thuật ngữ và giữ Q07 mở. |
| R08 / P2 | `docs/business-rules.md`/`docs/decisions.md` tại revision nêu trên đã chốt maker/checker, FIFO cũ trước, opening và posting bất biến; chưa chốt Q01–Q08. | Không hỏi lại nguyên tắc đã chốt; cũng không biến fixture thành policy. | Đã dẫn nguồn, giữ câu hỏi thiếu với ví dụ, lựa chọn/hệ quả, đề xuất, owner, trạng thái và mức chặn. |

## Nhất quán và kiểm tra tài liệu

- Thuật ngữ tách `event_date`, `posting_date`, `debt_period`, `submitted_at/created_at`, `decided_at`, receipt, allocation, source identity và idempotency key.
- Dependency: Q01/Q02 chặn triển khai danh tính/versioned approval; Q03/Q04 allocation/FIFO; Q05 nguồn/idempotency; Q06 reversal; Q07/Q08 period lock. Harness characterization hiện trạng không cần tự chọn các policy đó.
- Task kế tiếp dùng chính schema repo tại revision đã nêu, phân biệt characterization, defect repro và future acceptance; không tuyên bố đạt guard chưa có. Docker/PostgreSQL test chưa chạy và không có command runner hiện hữu được khẳng định.
- Chưa có review độc lập. Draft PR cần reviewer khác xem các nhận định kỹ thuật, nhất là role/grants, transaction boundary và scope reversal, trước khi merge hoặc dùng làm contract triển khai.
