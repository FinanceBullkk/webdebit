# PLAN — hiện tại (cập nhật 28/11/2026)

Mục tiêu gần nhất: **từ 1/12/2026 web là nơi nhập duy nhất của sổ nợ** ([`WEB-CHINH-01`](docs/decisions/web-chinh-01.md)).
Web đã là sổ chính thức từ 25/11/2026. Tới hết 30/11 người nhập vẫn gõ Sheet, máy chép theo nhưng chỉ *thêm* cái web chưa có,
không đè cái web đã có. Cái gì chạy ở đâu, ai biết khi nó dừng: [van-hanh.md](docs/van-hanh.md). Lộ trình theo mốc:
[roadmap](docs/roadmap.md).

Mỗi dòng ghi trạng thái kèm ngày của chính nó; dòng nào ngày cũ thì kiểm lại trước khi dựa vào. Bản 23/11/2026 (web chạy theo
Sheet, chờ xét cuối tháng) xem lịch sử Git.

## Trước và trong ngày 1/12

| # | Việc | Ai | Trạng thái 28/11 | Bằng chứng cần |
| --- | --- | --- | --- | --- |
| P1 | Người nhập đi thử từng đường nhập trên `hao` bằng login của mình | Người nhập, chủ sổ ở cạnh | CHƯA: bảng kết quả của [bài làm thử](docs/bai-thu-nhap-web.md) còn trống. Lịch sử 7 ngày tới 28/11: 14/208 dòng do người, cùng 1 login; danh sách cho phép có 3 login | Bảng kết quả điền đủ; Lịch sử ra đúng tên từng người |
| P2 | Đối soát cuối tháng 11, lượt so Sheet cuối cùng còn giá trị | Máy mỗi giờ; chủ sổ đọc kết quả | Lượt 16:15 ngày 28/11: 242/251 sổ khớp, 5 lệch tổng, 4 chỉ có trên web | `reconcile.json` của lượt cuối 30/11 chép vào thư mục bằng chứng (bước 1 của runbook ở P4) |
| P3 | Giữ tháng 11 mở ở sổ còn chuyến chưa giá, khóa lại sau 15/12 | Máy: timer `webdebit-giu-mo-thang`, `webdebit-khoa-lai-thang` | Lịch đặt 25/11, cả hai timer đang bật (kiểm 28/11); lượt ghi đầu 23:30 ngày 30/11 ([nhật ký](docs/deploys/2026-11-25-giu-mo-thang-11.md)) | Dòng Lịch sử người làm `giu-mo-thang` |
| P4 | Tắt máy theo Sheet sổ nợ, giữ máy theo booking | Claude theo [`DEPLOY-CLAUDE-01`](docs/decisions/deploy-claude-01.md); cần SSH và sudo trên `hao` | CHƯA CHẠY. 7 bước và cách lùi ở [runbook](docs/v7-deploy-runbook.md#tắt-máy-theo-sheet-sổ-nợ-ngày-1122026-web-chinh-01--chưa-chạy) | Nhật ký trong `docs/deploys/`; lượt 08:05 ngày 1/12 thoát 0 ở chế độ `booking-only` |
| P5 | Khóa Sheet sổ nợ, chỉ cho xem | Chủ sổ | CÒN MỞ, đề xuất làm cùng ngày 1/12 | Quyền chia sẻ của file |
| P6 | Chỗ ghi tạm khi `hao` sập giữa ngày | Chủ sổ chọn cách, Claude viết trang | CHƯA có quy trình (E2 của [checklist chuyển hẳn](docs/chuyen-han-checklist.md)). Ngày 28/11 `hao` tắt từ 04:48 tới 13:38 sau một lần mất điện | Quy trình một trang |

Sếp hay ai khác muốn tự xem web thì cần thêm login vào danh sách cho phép ([`ACCESS-01`](docs/decisions/access-01.md)).

## Bàn giao vận hành

| Việc | Trạng thái 28/11 |
| --- | --- |
| Người quản trị thứ hai cho tổ chức GitHub, tailnet Tailscale, healthchecks.io; email cảnh báo tới hơn một người | CHƯA. Tổ chức GitHub có 1 thành viên, cũng là admin. Tailnet và healthchecks.io dùng tài khoản của chủ dự án; mọi email cảnh báo tới một hộp thư. Chưa kiểm danh sách quản trị tailnet |
| Bản khóa age thứ hai (USB hoặc giấy) và ít nhất một PC kéo bản sao ở lại công ty | Không có bằng chứng trong repo ([runbook O6](docs/v7-deploy-runbook.md#o6-theo-dõi-và-rollback)) |
| Nguồn điện cho `hao` (laptop không pin, một ổ HDD) | CHƯA |
| Các tài khoản dịch vụ khác cần người giữ: Cloudflare (DNS cổng 8445), Google Cloud (tài khoản dịch vụ đọc Sheet), key Anthropic của trang Nhật ký | Chưa kê ai giữ |

## Sau 1/12, không chặn

- Gỡ mã và giao diện theo Sheet sổ nợ sau khi tắt máy: chép giá, chép phiếu, đối soát so Sheet, [`KIEM-TONG-01`](docs/decisions/kiem-tong-01.md), audit chuyển hẳn.
- Người dùng tự đi hết luồng trên `hao`: xuất debit note đối chiếu mẫu ([`DEBIT-NOTE-02`](docs/decisions/debit-note-02.md)), xóa một dòng điều chỉnh ([`XOA-DC-THANG-01`](docs/decisions/xoa-dc-thang-01.md)), kết luận CHỜ KIỂM, cấn trừ hai sổ.
- 17 tháng cũ đang mở ở 9 sổ (đo 28/11): khóa lại.
- Khách còn mở của [`SONG-SONG-03`](docs/decisions/song-song-03.md) mục (2): chủ nghiệp vụ xác định số phải thu.
- Sổ tiền ([`SO-TIEN-01`](docs/decisions/so-tien-01.md)): P0-a ở hai PR nháp ThienThanhLogs/webdebit#639, ThienThanhLogs/webdebit#649, chưa chạy trên `hao`.
- Thu chi tự sinh: bản bấm thử ThienThanhLogs/webdebit#632.
- Đội xe đợt 3 (dầu, sửa chữa, định phí, lãi lỗ): chưa làm, câu hỏi mở trong [spec](specs/chi-phi-xe-01.md).
- Bot Zalo hỏi đáp ([`ZALO-BOT-01`](docs/decisions/zalo-bot-01.md)): mã đã merge, chưa cài trên `hao`. Báo thu chi qua Telegram ([`TELEGRAM-01`](docs/decisions/telegram-01.md)): code xong, cờ tắt.
- Mã cũ thời V6/M1 (`pg_ledger_schema.sql`, `pg_versioned_approval_fixture.sql`, `pg_m1_*`, `webdebit_export_connector.py`) và các job CI của nó: đánh dấu lịch sử hoặc gỡ.
- Mục chưa đạt khác của [checklist chuyển hẳn](docs/chuyen-han-checklist.md): hai người cùng sửa một sổ, tốc độ khi dán nhiều chuyến, dựng lại trên máy thật.

Cập nhật bảng khi trạng thái đổi.
