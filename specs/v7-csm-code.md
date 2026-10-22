# V7-CSM (2), (3): hợp đồng triển khai

Người dùng giao code ngày 21/10/2026 trên `codex/v7-csm-code`; yêu cầu trực tiếp gồm UI tham chiếu, sửa tại chỗ, cảnh báo và lịch sử. Dùng khuôn nhập/sửa hiện có; không đổi luồng thu/cấn trừ.

- Tham chiếu text tùy chọn; trim hai đầu, blank lưu NULL. Sửa: thiếu/null giữ nguyên, chuỗi rỗng xóa. API giới hạn 500 ký tự như ghi chú hiện có. Không ảnh, không tính ngoại tệ/tỷ giá.
- Trùng text sau trim, phân biệt hoa/thường, trong cùng sổ, kể cả phiếu đã hủy: response `duplicate_reference` cảnh báo sau lưu, không chặn. Nhiều dòng phân bổ vẫn là một phiếu. Phiếu cấn trừ lưu tham chiếu ở sổ nhận; sửa tham chiếu không đổi ngày/tiền của cặp.
- Mỗi lệnh mở/khóa thành công, kể cả cùng trạng thái, ghi `event.kind=month_lock`: actor phiên máy chủ, thời điểm, tháng, trạng thái trước/sau. Retry cùng key không ghi thêm. Stale/invalid/rollback không để event.
- Migration riêng, transaction, giữ dữ liệu, payload idempotency cũ khi không có tham chiếu và quyền execute tối thiểu. Chỉ kiểm DB tạm qua bộ điều phối ngoài sandbox.

| Thao tác | Module | Kiểm |
| --- | --- | --- |
| Ghi/sửa tham chiếu | UI/API/model V7, `record_receipt`, `edit_receipt_meta` | node, API unittest, Playwright, PostgreSQL harness |
| Mở/khóa và xem Lịch sử | `set_month_lock`, `get_ledger`, UI | harness actor/tháng/thời điểm/retry/rollback; Playwright hai dòng riêng |
| Nâng schema | `tools/migrations/2026-10-21-v7-csm.sql` | harness nâng từ schema trước thay đổi, đối chiếu định nghĩa hàm |

Kiểm bắt buộc: `npm run check`, `node scripts/check-secrets.js`, harness backend/grants. Không SSH, DDL/import/deploy/submit thật, Sheet/dữ liệu thật. Không sửa D04, quyền xem lịch sử, nguồn đóng băng/case 7.11c. Nhãn SKIPPED_OPEN cũ về D04 chưa phản ánh V7-CSM (1): ghi rõ khoảng trống trong PR, không tự mở rộng nhiệm vụ. Kiểm live và nghiệm thu production ngoài phạm vi.
