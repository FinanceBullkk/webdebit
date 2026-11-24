# TU-LAM-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **Claude không cần hỏi trước nữa** với bốn loại việc mà [`CLAUDE.md`](../../CLAUDE.md) và [`DEPLOY-CLAUDE-01`](deploy-claude-01.md) còn bắt hỏi:

1. Nạp dữ liệu hoặc bản mốc (`v7_load*`, cutover, nhập giao dịch).
2. Ghi lên Google Sheet.
3. Thao tác trên DB legacy `webdebit_ledger`.
4. Đổi role/quyền DB, pg_hba, Tailscale, systemd ngoài điều runbook đã ghi.

Việc cần thì Claude tự làm, nhưng vẫn giữ rào chắn:

- Backup hoặc chụp lại bản trước khi ghi DB hay Sheet, kiểm đọc lại được.
- Nạp dữ liệu xong đối soát tổng từng khách trước/sau; lệch thì quay lại và báo người dùng kèm bằng chứng.
- Mỗi đợt ghi một nhật ký mới trong [`docs/deploys/`](../deploys/README.md); không chép bí mật, tên khách, số tiền hay số container thật vào repo.
- Đổi quyền hoặc cấu hình hệ thống thì ghi lại giá trị cũ và cách quay lại trong nhật ký.

**Vẫn hỏi người dùng trước:** force push, xóa nhánh hoặc dữ liệu không thuộc nhiệm vụ, và PR đổi quy tắc tiền hoặc quyết định chưa chốt.

**Ngoại lệ từ 24/11/2026 ([`SO-TIEN-01`](so-tien-01.md) (5)):** dữ liệu nghiệp vụ của sổ tiền (schema `tien`: giao dịch, phân bổ, đề nghị và duyệt chi, ký đối chiếu) Claude không ghi, nạp hay sửa, kể cả khi làm việc vận hành; Claude chỉ triển khai schema và mã theo runbook.

Các chỗ "hỏi người dùng trước" cũ trong spec và quyết định khác (ví dụ [`WECHAT-01`](wechat-01.md), [`ZALO-AGENT-01`](zalo-agent-01.md), [`ZALO-THU-CHI-01`](zalo-thu-chi-01.md)) đọc theo quyết định này khi việc đó thuộc bốn loại trên.

## Ngày / nguồn

22/11/2026, người dùng nói trong chat với phiên điều phối, trả lời danh sách "việc vẫn phải hỏi người dùng (nạp dữ liệu, ghi Google Sheet, DB cũ, đổi quyền ngoài runbook)": "Các việc này k cần hỏi luôn", rồi chọn sửa `CLAUDE.md` theo ý đó.

## Trạng thái

ĐÃ CHỐT 22/11/2026. Đây là thay đổi quyền hạn, không phải bằng chứng việc nào đã chạy. Quyền của công cụ (`.claude/settings.json`, ví dụ lệnh có `psql` vẫn hiện hộp hỏi) không đổi theo quyết định này.
