# Triển khai tay: bản sao backup V7 ra PC (29/10/2026)

**ĐÃ CÀI trên `hao` và PC chính ngày 29/10/2026, 20:45–20:57 giờ VN.** Người dùng chọn đích trong chat (PC Windows chính
trong tailnet) rồi duyệt cài ("Cài luôn"), vì thêm khóa SSH, unit systemd và lịch Windows là đổi ngoài runbook theo
[`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Không migration, không đổi DB, không ghi tiền.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#175 (`f796d94`): `v7_backup.py offsite`, `tools/v7_offsite_pull.py`, runbook O1–O6 |
| Quy trình | [Runbook — Bản sao ngoài máy](../v7-deploy-runbook.md#bản-sao-ngoài-máy--timer-v7-backup-offsite) |
| Vì sao | dữ liệu PostgreSQL và `/srv/v7-backup-daily` nằm trên cùng một ổ của `hao` |

## Đã làm

- **O1 (PC):** khóa age và khóa SSH để kéo, cả hai trong `.ssh` của chủ máy, ACL chỉ chủ máy, `SYSTEM`, `Administrators`.
  Thư mục script và thư mục đích trên ổ dữ liệu, ngoài OneDrive, cạnh bản Vaultwarden.
- **O2 (`hao`):** bản ghim `v7_backup.py` chép từ blob của `f796d94` (`b386b56e…` → `d00e29c8…`); `verify` bản
  `v7-20261029-194852` dưới `postgres`: MATCH. Recipient `/etc/webdebit-backup/v7-offsite.recipients` (root, 644); hộp chờ
  `/srv/v7-backup-offsite` (`postgres`, nhóm user quản trị, 2750). `authorized_keys` của user quản trị thêm đúng một dòng
  (so trước/sau). Kiểm từ PC bằng khóa mới: lệnh `id` không chạy, `pwd` là hộp chờ, `put` bị từ chối; khóa quản trị cũ vẫn
  đăng nhập.
- **O3 (`hao`):** hai unit đúng nguyên văn runbook ở `f796d94` (hash khớp bản trích); `systemd-analyze verify` không báo
  lỗi ở hai unit. `systemctl start` 20:55: `Result=success`, JSON `"ok": true`, `sealed` `v7-20261029-194852.tar.age`
  1.925.784 byte; hai tệp 640; `sha256sum -c` OK. Timer enabled, lượt kế 30/10 03:00 giờ VN.
- **O4 (PC):** hai script chép từ `f796d94`, `Get-FileHash` khớp (`d00e29c8…`, `3e338ade…`). Lượt tay: `PASS pulled=1`,
  2 giây, SHA-256 khớp. Lịch `Webdebit V7 Backup Pull` (`pythonw.exe`, chạy khi chủ máy đăng nhập, `StartWhenAvailable`,
  tối đa 30 phút, 04:30): chạy thử `LastTaskResult=0`, `PASS pulled=0`; lượt kế 30/10 04:30.
- **O5:** trên PC: SHA-256 khớp, `age` 1.3.1 giải mã, `tar` giải nén, `verify` MATCH (dump 1.909.164 byte). Thư mục giải
  nén chép sang máy chạy Claude, phục hồi vào PostgreSQL 18.6 Docker `--network none`, ba role NOLOGIN tạo trước: `restore`
  mã thoát 0, `MATCH`, số dòng 31 bảng và tổng nợ 236 khách khớp `MANIFEST.json`, 5 giây. Đã xóa container, volume và bản
  rõ ở cả PC lẫn máy chạy Claude.

Bằng chứng: thư mục `v7-backup-offsite-install-20261029-204836` cạnh thư mục backup của các đợt nâng trên `hao`
(`authorized_keys` trước/sau, hash bản ghim và unit, journal lượt đầu, báo cáo restore có id khách và tổng nợ, tóm tắt),
700/600, ngoài Git.

## Rollback

`sudo systemctl disable --now v7-backup-offsite.timer`; trên PC `Disable-ScheduledTask -TaskName 'Webdebit V7 Backup Pull'`;
xóa dòng `webdebit-v7-offsite-pull` trong `authorized_keys` của user quản trị (bản trước khi sửa nằm trong thư mục bằng
chứng). Giữ các bản đã chép. Bản ghim cũ `0ca04eb` cũng nằm ở đó nếu cần trả lại.

## CÒN MỞ

- Lượt tự động đầu: `hao` 30/10 03:00, PC 04:30. Đạt khi journal có `"sealed": "v7-20261030-…"` và `pull.log` có
  `PASS pulled=1 newest=v7-20261030-…`.
- Chủ máy chép khóa age ra USB hoặc giấy, cất riêng: chưa làm.
- PC và `hao` cùng một nơi (cháy, mất trộm vẫn mất cả hai); chưa có cảnh báo khi lượt lỗi; lịch chỉ chạy khi PC bật và chủ
  máy đăng nhập.
