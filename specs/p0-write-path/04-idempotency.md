# P0-04 — Idempotency và retry an toàn

Trạng thái: **ĐỀ XUẤT**.

## Hiện trạng được xác nhận tĩnh

Tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`, `cong-no-web-handoff/tools/pg_ledger_schema.sql`, `ledger.proposal.request_key` là unique và `ledger.submit_entry(...)` lưu proposal/lines/audit trong cùng function. Không có bảng payload hash hay resource kết quả theo key; key trùng phát sinh unique violation, không trả lại kết quả hiện có. `proposal_receipt_source_once` là guard riêng theo `source_ref` cho receipt chưa rejected; không thay idempotency chung. Chưa có test PostgreSQL retry/timeout trong repo.

## Quy tắc và đề xuất

Không tạo giao dịch tiền lặp do retry; không suy receipt trùng chỉ từ cùng số tiền. Đề xuất lưu key theo scope caller/operation đã chốt, canonical payload hash và resource/status trong cùng transaction với proposal. Cùng key+cùng hash trả lại cùng resource; cùng key+payload khác trả conflict không đổi dữ liệu. Hai request cùng key phải serialize qua unique constraint/claim row rồi nhận cùng kết quả.

Phân biệt bốn khái niệm: idempotency key (retry request), source identity (chứng từ/nguồn), receipt (tiền nhận) và allocation (phân bổ vào kỳ). Source identity chống nhập trùng là policy riêng cần chốt.

## Ví dụ và acceptance tương lai

Sau timeout, server đã commit receipt 100 nhưng client chưa nhận response; cùng key/payload phải trả đúng proposal đã commit. Cùng key nhưng amount 101 phải bị conflict; key mới với cùng source identity phải theo policy chống nhập trùng nguồn. Kiểm lỗi trước commit và mất response sau commit riêng biệt. Canonicalization cần xác định thứ tự lines/encoding và mọi field ảnh hưởng tiền, kỳ, source/evidence và actor scope.

Q05 trong [quyết định còn mở](decisions-needed.md) chặn việc chốt semantics source identity; cơ chế key/hash kỹ thuật có thể đặc tả mà chưa tự quyết policy chống receipt trùng.
