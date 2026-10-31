# Hồ sơ phát triển đã lọc

| Tài liệu | Dùng để |
| --- | --- |
| [Nghiệp vụ](business-rules.md) | Quy tắc đã xác nhận và bất biến |
| [Quyết định](decisions.md) | Phạm vi được chốt và gate còn mở |
| [Kiến trúc](architecture.md) | Đường đọc/test hiện có, ranh giới thiết kế nháp |
| [Nguồn và phiên bản](source-register.md) | Truy nguyên bản tóm tắt tới hồ sơ gốc theo hash |
| [Phát triển](development.md) | Checkout chính, thay đổi, review và đồng bộ |
| [Kiểm chứng](verification.md) | Kết quả thực chạy và giới hạn |
| [Spec](../specs/README.md) | Thay đổi cụ thể và tiêu chí nghiệm thu |
| [Định dạng báo cáo M1](m1-report-format.md) | Count evidence và quy tắc phân biệt NULL với 0 |
| [Gói deploy và rollback M1](m1-deploy-rollback.md) | Gói runtime theo allowlist, preflight chỉ đọc và rollback; đã áp dụng trên `hao` tại `c439d13`, còn hồ sơ nghiệm thu |
| [Đề xuất ACL M1](m1-acl-proposal.md) | Cấp quyền đọc năm view cho viewer, thu hồi membership maker; đã áp dụng trong đợt M1, giữ hồ sơ ngoài Git |
| [Runbook triển khai V7](v7-deploy-runbook.md) | Đề xuất deploy DB riêng, backup/rollback và tổng duyệt Docker |
| [Checklist chạy song song](song-song-checklist.md) | Điều kiện bắt đầu chạy song song Sheet–web: ai làm, bằng chứng gì, trạng thái |
| [Đối soát cuối ngày](doi-soat-cuoi-ngay.md) | Các bước người nhập chạy mỗi cuối ngày khi chạy song song |
| [Audit UX/UI và hành trình người dùng](ux-audit-2026-10-31.md) | Phát hiện P0/P1/P2 trên sáu trang, kiến trúc đề xuất (sổ khách một tháng đang làm, hộp thư việc, từ điển giao diện, token), lộ trình ba đợt; ĐỀ XUẤT 31/10/2026 |

Ưu tiên quyết định người dùng có phạm vi rõ hơn đề xuất cũ; code/fixture không tự duyệt chính sách. Hồ sơ này tóm tắt phần được phép chia sẻ từ bằng chứng gốc giữ ngoài repo. Không sao chép bảng khách, số dư từng khách, ID Sheet hoặc chứng từ. Từ mốc chuyển quy trình, thay đổi mới ghi ở repo; hồ sơ gốc là chứng cứ lịch sử, không là bản tài liệu sống thứ hai.
