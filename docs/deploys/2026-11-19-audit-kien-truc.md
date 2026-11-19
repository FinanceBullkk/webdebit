# Triển khai: hai kiểm thiếu của lệnh ghi từ audit kiến trúc (19/11/2026)

**ĐÃ CHẠY trên `hao` lúc 13:54 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [runbook](../v7-deploy-runbook.md) (mục "Hai kiểm thiếu của lệnh ghi từ audit kiến trúc 19/11").

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Người dùng trả lời "Merge and deploy" 19/11/2026 cho sáu PR của audit kiến trúc; lượt merge do phiên điều phối merge cấp |
| PR / release | #516, merge `35f93a9`; release tay `35f93a9` thay cho `a022ac2` |
| CI | Mọi check của head `d6243d6` xanh, gồm `postgres-v7-backend` (`--migration-test`, `v7_schema_snapshot.py --check`) |
| Review | Hai lượt review độc lập (subagent) trên diff tích hợp sáu PR; harness PostgreSQL ở máy trên bản ghép với `main` `a9ac3ef`: backend 75 ca hành vi + 10 ca migration, P0, grants, bất biến tiền 200 chuỗi / 4.990 lệnh, xuất sổ, lưới an toàn đều qua |
| Migration | `2026-11-19-v7-audit-kien-truc.sql`, SHA-256 `020ad80c3b4b786d5a521422b188bc5a305ca51818e998811f47758f326213dc`, trùng bản trên `main` và bản đã thử |
| Ghi tiền | Không. Chỉ thay thân `edit_trip_info` (A12: thêm luật `BASELINE_UNDATED_MONTH` như `paste_trips`) và `record_mark` (A08: cùng khóa mà nội dung khác thì `IDEMPOTENCY_CONFLICT`) |

## Thử trên bản sao (13:49)

- Dump `webdebit_v7` (`pg_restore --list` 1027 dòng), khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC, `ANALYZE`.
- Migration hai lượt (92 và 91 ms). Hoàn tác bằng `2026-11-16-v7-chuan-hoa-chu.sql` và `2026-11-01-v7-zalo-group.sql`: catalog trùng bản trước; nâng lại: catalog trùng bản sau.
- Dấu vân dữ liệu (`_safety_fingerprints`, md5 số dư từng khách theo tháng, số dòng mọi bảng `sokhach`) trùng trước, sau và sau hoàn tác.
- Catalog chỉ đổi thân hai hàm; chủ và quyền giữ nguyên. Checker 9/9. Đã xóa DB thử.
- Chuyến `confirmed` hiện có khớp luật mới: 0. Luật chỉ xét khi sửa container hoặc ngày về sau, không quét lại chuyến cũ.

## DB thật, 13:54

- Lượt máy đối soát kế tiếp lúc 14:05; không có kết nối nào khác vào `webdebit_v7`.
- Backup toàn phần ngay trước khi áp; `pg_restore --list` đọc được (1027 dòng).
- Áp với `ON_ERROR_STOP`: 125 ms. Không cần cửa sổ dừng ghi vì chỉ thay thân hàm.
- Dấu vân dữ liệu trước và sau trùng nhau. Catalog trùng bản thử sau khi nâng. Checker 9/9.

## Release

- Release tay `35f93a9` lúc 13:55 bằng `git archive` và `webdebit-release.sh` dưới `webdebit-deploy`: `/healthz` 200, unit active, `.release-sha` = `35f93a9`. Script cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước).
- Bản đang phục vụ có câu báo mới của hộp đánh dấu Zalo; hai hàm trên DB thật mang thân mới.
- Journal API chỉ có cảnh báo "chưa có bản xuất chat Zalo", đã có từ trước.
- Lưới an toàn `--dry-run`: `"ok": true`, không mục nào, 244 sổ.

## Rollback

Chạy lại `2026-11-16-v7-chuan-hoa-chu.sql` rồi `2026-11-01-v7-zalo-group.sql` dưới `postgres` với `ON_ERROR_STOP` (đã thử trên bản sao: catalog về đúng bản trước). Release cũ chạy được với DB mới.

## CÒN MỞ

- Năm PR còn lại của audit (#517–#521) theo hàng merge; #521 cần cài lại tay `hao-release.sh` sau merge.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261119-audit-kien-truc/` trên `hao` (quyền 700). Gồm dump trước khi thử và trước khi nâng kèm sha256, SQL và script đã chạy, dấu vân, catalog, checker và nhật ký hai lượt.
