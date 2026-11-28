# Roadmap — web công nợ phải thu HTH

Cập nhật 28/11/2026. Roadmap theo đầu ra kiểm được, không theo phần trăm. Trạng thái một mốc chỉ đổi khi có bằng chứng đúng
revision và môi trường, ghi ngày. Việc từng tuần ở [PLAN](../PLAN.md); cái gì đang chạy ở [vận hành](van-hanh.md); chính sách ở
[quyết định](decisions.md). Bản 22/10/2026, chi tiết M0–M4 lúc dựng V7, xem lịch sử Git của file này.

## Sổ nợ

| Mốc | Đầu ra | Trạng thái 28/11/2026 | Bằng chứng |
| --- | --- | --- | --- |
| M0 · Nền dữ liệu | Số dư đầu từ sổ gốc, lịch sử trong số dư đầu không cộng lại | XONG: mốc `clean-v2` nạp lên `hao` 21/10 | [`OPENING-SO-GOC`](decisions/opening-so-goc.md), [`SONG-SONG-02`](decisions/song-song-02.md) |
| M1 · Web xem sổ (bản V6) | Xem sổ chỉ đọc | ĐÃ NGHIỆM THU 16/10, đã thay bằng V7; công cụ viewer gỡ khỏi repo 18/11 | [kiểm chứng](verification.md), [gói M1](m1-deploy-rollback.md) |
| M2 · Hợp đồng ghi V7 | Một người nhập và ghi sổ, danh tính Tailscale, FIFO, khóa tháng, vết trước → sau | CHẠY THẬT trên `hao` từ 22/10. [Tiêu chí M2](../specs/m2-tieu-chi-v7.md) vẫn ĐỀ XUẤT, chưa ai chấm từng tiêu chí | Harness PostgreSQL trong CI; lưới an toàn 15 phút ([`LUOI-AN-TOAN-01`](decisions/luoi-an-toan-01.md)) |
| M3 · Web giao dịch trên `hao` | API ghi, migration, đồng thời, sao lưu và phục hồi | ĐÃ TRIỂN KHAI 21–22/10; ghi thật hằng ngày (máy và người). Sao lưu giờ, ngày và ra ngoài máy; diễn tập dựng lại phần lõi 25/11 mất khoảng 13 phút | [runbook](v7-deploy-runbook.md), [dựng lại](rebuild-hao.md), [nhật ký triển khai](deploys/README.md) |
| M4 · Chạy song song Sheet–web | Máy theo Sheet, đối soát tổng từng khách | Tính từ 1/11 ([`SONG-SONG-02`](decisions/song-song-02.md)); máy tự đối soát và tự sửa mỗi giờ từ 4/11 ([`MAY-DOI-SOAT-01`](decisions/may-doi-soat-01.md)). Ngày 25/11 người dùng chốt web là sổ chính thức và thôi gõ Sheet từ 1/12 ([`WEB-CHINH-01`](decisions/web-chinh-01.md)), thay vế (1) của [`SONG-SONG-01`](decisions/song-song-01.md). Lượt so Sheet cuối cùng còn giá trị là đối soát cuối tháng 11 | [checklist chạy song song](song-song-checklist.md), [checklist chuyển hẳn](chuyen-han-checklist.md) |
| M5 · Web là nơi nhập duy nhất | Từ 1/12 mọi đầu vào nhập trên web; máy chỉ còn theo booking; sổ web kiểm theo booking, lưới an toàn và xuất cả sổ | ĐANG LÀM. Mã cho ngày 1/12 merge 25/11; người nhập chưa đi thử; runbook 7 bước CHƯA CHẠY | [PLAN](../PLAN.md), [runbook ngày 1/12](v7-deploy-runbook.md#tắt-máy-theo-sheet-sổ-nợ-ngày-1122026-web-chinh-01--chưa-chạy) |

## Các mảng khác trên cùng web

Trạng thái lấy theo nhật ký triển khai; dòng trạng thái trong vài file quyết định có thể chậm hơn nhật ký.

| Mảng | Quyết định | Trạng thái 28/11/2026 |
| --- | --- | --- |
| Đội xe | [`CHI-PHI-XE-01`](decisions/chi-phi-xe-01.md), [`DOI-XE-THU-01`](decisions/doi-xe-thu-01.md), [`DOI-XE-DIEU-DO-01`](decisions/doi-xe-dieu-do-01.md) | Đợt 1, đợt 2 lên `hao` 18/11 ([nhật ký](deploys/2026-11-18-doi-xe.md)); phân công điều xe lên `hao` 19/11 ([nhật ký](deploys/2026-11-19-doi-xe-dieu-do.md)). Đợt 3 (dầu, sửa chữa, định phí, lãi lỗ) chưa làm |
| Zalo | [`ZALO-GROUP-01`](decisions/zalo-group-01.md), [`ZALO-AGENT-01`](decisions/zalo-agent-01.md), [`ZALO-BOT-01`](decisions/zalo-bot-01.md) | Agent đọc Zalo/WeChat chạy trên PC `msi` từ 20/11, bản ghim theo SHA từ 23/11 ([nhật ký](deploys/2026-11-23-zalo-agent-ban-ghim.md)). Bot hỏi đáp: mã đã merge, chưa cài |
| Thu chi | [`ZALO-THU-CHI-01`](decisions/zalo-thu-chi-01.md), [`TELEGRAM-01`](decisions/telegram-01.md) | Trang Thu chi đã có trên web; báo Telegram code xong, cờ tắt; thu chi tự sinh mới ở bản bấm thử |
| Nhật ký công việc | [`NHAT-KY-01`](decisions/nhat-ky-01.md) | Chạy trên `hao` từ 20/11 |
| Sổ tiền | [`SO-TIEN-01`](decisions/so-tien-01.md) | ĐÃ CHỐT hướng P0-a; mã ở PR nháp, chưa chạy trên `hao` |

## Cách cập nhật

Chỉ đổi trạng thái khi có link tới quyết định hoặc kết quả kiểm đúng revision và môi trường. Mỗi lần cập nhật ghi ngày, đầu ra đã
kiểm và việc còn chặn. [Kiểm chứng](verification.md) giữ log kỹ thuật, [nhật ký triển khai](deploys/README.md) giữ việc tay trên
`hao`; roadmap chỉ tổng hợp.
