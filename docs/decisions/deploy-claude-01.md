# DEPLOY-CLAUDE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **Claude tự triển khai cả phần SQL/migration lên `hao`, không cần người dùng duyệt từng lần.** Trước đây ([`CLAUDE.md`](../../CLAUDE.md), 28/10/2026) PR có `specs/v7-backend/`, `tools/migrations/` hoặc file `.sql` thì Claude phải hỏi trước khi merge, và đợt nâng DB tay trên `hao` cần người dùng duyệt riêng. Từ nay Claude tự merge các PR đó khi đủ điều kiện dưới đây, rồi tự chạy đợt triển khai tay theo [runbook](../v7-deploy-runbook.md) trên DB `webdebit_v7`.

Điều kiện bắt buộc cho mỗi đợt (thiếu một điều thì dừng và báo người dùng, không né):

1. Mọi check bắt buộc trên GitHub xanh, gồm harness PostgreSQL. Ở máy đã chạy lượt nâng migration so catalog với khởi tạo mới, theo đúng thứ tự runbook ghi.
2. Backup toàn phần `webdebit_v7` trước khi ghi (runbook mục 2), và kiểm đọc lại được trước khi chạy migration.
3. Chạy bằng `psql -X -v ON_ERROR_STOP=1`, migration theo thứ tự runbook. Xong chạy `v7_post_deploy_check.sql`, đối soát tổng từng khách trước/sau (migration không đổi dữ liệu thì tổng phải giữ nguyên), đặt `.release-sha` để `Deploy hao` có mốc diff đúng.
4. Lỗi hoặc lệch thì quay lại theo runbook mục 7 (mức A/B), giữ backup, báo người dùng kèm bằng chứng.
5. Nhật ký mỗi đợt là một file mới trong [`docs/deploys/`](../deploys/README.md), không ghi bí mật hay số liệu khách.

**Vẫn hỏi người dùng trước:** nạp dữ liệu hoặc bản mốc (`v7_load*`, cutover, nhập giao dịch), mọi ghi lên Google Sheet, mọi thao tác trên DB legacy `webdebit_ledger` (gồm rollback mức C), xóa dữ liệu, đổi role/quyền DB/pg_hba/Tailscale/systemd ngoài điều runbook đã ghi, force push, và đổi quy tắc tiền chưa chốt.

## Ngày / nguồn

29/10/2026, người dùng nói trong chat: "sửa luôn 1 cái là cho claude quyền chạy deploy, ko cần mình duyệt nữa". Claude đặt phạm vi và điều kiện ở trên theo quyền người dùng trao (xem `CLAUDE-ALL-01`).

## Trạng thái

ĐÃ CHỐT. Áp dụng từ đợt triển khai tay đầu tiên sau 29/10/2026. Đây là thay đổi quyền hạn, không phải bằng chứng đợt nào đã chạy.
