# P0 đề xuất: đường ghi sổ công nợ

Ngày lập: 15/10/2026. Trạng thái: **ĐỀ XUẤT**; chưa là chính sách được duyệt hay thiết kế triển khai cuối. Không cho phép ghi tiền.

## Phạm vi, nguồn và trạng thái

Nhánh `docs/p0-write-path-specs` được tách tại `8365e8aa5ae2517959dedcc52ed8384232458b75`, hiện trùng head `fix/reproducible-development`. PR #1 đang OPEN/Draft, base `main`; PR này phụ thuộc PR #1 và phải dùng base `fix/reproducible-development`. Đây là trạng thái GitHub được đọc ngày 15/10/2026.

Review đối chiếu mã tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, đặc biệt `cong-no-web-handoff/tools/pg_ledger_schema.sql` và các tài liệu `docs/business-rules.md`, `docs/decisions.md`, `docs/architecture.md`. Nhận định từ mã là **kiểm tra tĩnh**, không phải test PostgreSQL. Repo không có test PostgreSQL cho schema này. Probe được nhắc trong feedback workspace-only `design/2026-10-15/feedback/response.md` thuộc `schema-draft.sql` ngoài repo; không gán kết quả probe đó cho SQL trong repo. Xem [review](review.md) để biết phát hiện, mức độ, bằng chứng, ảnh hưởng và trạng thái.

Task 1–2 của PR #1 được người dùng báo đã nghiệm thu; đây là ghi nhận từ yêu cầu hiện tại, không phải kiểm chứng độc lập mới. Không chạy lại test dự án chỉ vì chỉnh Markdown.

## Quy tắc nghiệp vụ đã chốt

Theo `docs/business-rules.md` và `docs/decisions.md` tại revision trên: số dư theo khách + kỳ nợ; opening lịch sử không cộng lại; ngày xe nhập kho là ngày nghiệp vụ chuyến; maker khác checker; receipt tách allocation; thu mới ưu tiên kỳ nợ cũ trước; pending không làm đổi số dư đã ghi; VND nguyên chính xác; posting đã ghi không sửa đè. Các nguyên tắc này không tự quyết danh tính đăng nhập, tiền dư, ngoại lệ FIFO, đảo một phần, nhập muộn hay reopen kỳ.

## Tài liệu con

- [T1 — Hợp đồng nghiệp vụ cho charge chuyến đầu tiên](00-first-charge-contract.md)
- [P0-01 Ghi sổ nguyên tử](01-atomic-posting.md)
- [P0-02 Phê duyệt theo phiên bản và danh tính](02-versioned-approval-identity.md)
- [P0-03 Phân bổ đồng thời](03-concurrent-allocation.md)
- [P0-04 Idempotency](04-idempotency.md)
- [P0-05 Đảo giao dịch](05-reversal.md)
- [P0-06 Khóa kỳ và ngày ghi sổ](06-period-posting-lock.md)
- [Quyết định còn mở](decisions-needed.md)
- [Task PostgreSQL tiếp theo](next-task.md)
- [Review tài liệu](review.md)

## Ranh giới đề xuất

Các tiêu chí dưới đây là yêu cầu cho thiết kế tương lai, không phải hành vi đã triển khai. Mỗi thay đổi cần kiểm thành công, từ chối, lỗi/rollback và retry/đồng thời phù hợp với phạm vi. Không chạy DDL hoặc test trên `hao`, Sheet hay service thật. Task đầu tiên được đề xuất chỉ dựng harness riêng và môил tả hành vi của schema hiện tại; không triển khai guard mới. Đường ghi tiền cần quyết định nghiệp vụ, duyệt spec, review độc lập và gate triển khai riêng.
