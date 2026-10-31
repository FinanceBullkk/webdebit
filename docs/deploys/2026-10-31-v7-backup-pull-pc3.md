# Triển khai tay: PC thứ ba kéo bản V7 ngoài máy (31/10/2026)

**ĐÃ CÀI trên `hao` và PC thứ ba ngày 31/10/2026, 15:31–15:45 giờ VN.** Claude làm. Người dùng chuyển máy làm việc chính
sang PC thứ ba cùng ngày và duyệt trong chat ("mình duyệt", rồi "Cho phép, bạn chạy") việc thêm một recipient age và một
dòng `authorized_keys` chỉ SFTP đọc, vì là đổi ngoài runbook theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md).
Hai PC đang kéo (PC cũ 04:30, PC thứ hai 04:40) giữ nguyên. Không migration, không đổi DB, role, `pg_hba` hay Tailscale;
không ghi tiền.

| Mục | Nội dung |
| --- | --- |
| Mã | không đổi; script PC từ `215e1a0` (FinanceBullkk/webdebit#223), cùng bản ghim trên `hao` |
| Quy trình | Runbook [bản sao ngoài máy](../v7-deploy-runbook.md#bản-sao-ngoài-máy--timer-v7-backup-offsite) O1, O2 (recipient, khóa), O4, O5 và [K4](../v7-deploy-runbook.md#k4-kiểm-trên-pc-sau-khi-cài-và-hằng-tháng-cùng-o5) cho PC thứ ba |
| Vì sao | PC thứ hai hay tự khởi động lại; máy làm việc chính chuyển về PC thứ ba và cần tự có bản ngoài máy giải mã được |

## Đã làm

- **Trước khi ghi:** journal `sudo` 30 phút chỉ có lệnh chỉ đọc của phiên này; không phiên PostgreSQL nào khác. Bản trước
  của file recipient và `authorized_keys` chép vào thư mục bằng chứng.
- **Khóa trên PC (O1):** `age` 1.3.2 (winget, phạm vi user); khóa age và khóa SSH ed25519 riêng
  (`webdebit-v7-offsite-pull-msi`, không passphrase, kiểm bằng `ssh-keygen -y -P ''`) trong `.ssh` của chủ máy; ACL chỉ chủ
  máy, `SYSTEM`, `Administrators`.
- **Trên `hao` (O2):** recipient thêm một dòng (`tee -a`, 2 → 3 dòng); `authorized_keys` thêm đúng một dòng
  `restrict,from=…,command="…sftp-server -R -d /srv/v7-backup-offsite"` (6 → 7 dòng, `diff` trước/sau chỉ có dòng mới).
  Kiểm bằng khóa mới: `id` không in `uid=`, thư mục làm việc là hộp chờ, `ls` được, `put` bị từ chối; khóa quản trị vẫn
  đăng nhập.
- **Bản giải mã được ngay:** chạy tay `offsite` dưới `postgres` (`umask 0027`) với gốc `/srv/v7-backup-hourly`:
  `v7-20261031-150016.tar.age`, ba stanza X25519, `sha256sum -c` OK, `pruned` rỗng. Chạy tay `v7-backup-config.service`:
  `Result=success`, `v7-config-20261031-154206.tar.age`, 55 tệp, 11 symlink, `missing` rỗng. Từ lượt 02:50/03:00 ngày
  1/11 cả hai họ tự mã hóa cho ba PC.
- **Kéo về PC thứ ba (O4):** hai script từ `215e1a0`, SHA-256 khớp `git show` (`v7_backup.py` `7d151719…`, như bản ghim).
  Thư mục script và đích trên ổ dữ liệu, ngoài OneDrive và mọi checkout, ACL chỉ chủ máy (bỏ thừa hưởng). Lượt tay
  `PASS pulled=5 … config_pulled=1`. Lịch `Webdebit V7 Backup Pull` **04:50** (`pythonw.exe`, chạy khi chủ máy đăng nhập,
  `StartWhenAvailable`, tối đa 30 phút): `Start-ScheduledTask` → `LastTaskResult=0`, `PASS pulled=0`; lượt kế 1/11 04:50.
- **Phục hồi thử trên PC (O5/K4):** SHA-256 khớp; `age` giải mã bằng khóa PC thứ ba; `verify` `MATCH`. PostgreSQL 18.6
  Docker `--network none`, ba role NOLOGIN: `restore` mã thoát 0, `MATCH`, 32 bảng, 236 khách, 5 giây. Gói cấu hình mới:
  `config-verify` `MATCH config archive: 55 files, 11 links, 0 missing patterns`. Đã xóa container, volume và mọi bản rõ.
- **Vấp:** PowerShell 5.1 đọc file `.ps1` không BOM theo mã ANSI, mô tả lịch có dấu tiếng Việt làm hỏng cú pháp; lưu
  `.ps1` dạng UTF-8 có BOM (gõ thẳng lệnh trong cửa sổ PowerShell như runbook O4 thì không gặp).

Bằng chứng: `/srv/backups/v7-backup-pull-msi-20261031-083100` trên `hao` (bản trước/sau của hai file đổi), 700 root; báo
cáo restore có id khách và tổng nợ ở thư mục bằng chứng cạnh thư mục đích trên PC thứ ba. Ngoài Git.

## Rollback

PC thứ ba: `Disable-ScheduledTask -TaskName 'Webdebit V7 Backup Pull'`. Trên `hao`: xóa dòng
`webdebit-v7-offsite-pull-msi` trong `authorized_keys` và dòng recipient thứ ba (bản trước nằm trong thư mục bằng chứng);
giữ các bản đã có.

## CÒN MỞ

- Lượt tự động đầu 1/11: PC thứ ba kéo 04:50. Đạt khi `pull.log` có `config_newest=v7-config-20261101-…` và
  `newest=v7-20261101-…`.
- **Chủ máy chép khóa age của PC thứ ba ra USB hoặc giấy, cất riêng** (như hai khóa kia, vẫn CÒN MỞ).
- Khi bỏ hẳn PC thứ hai: tắt lịch trên PC đó, xóa dòng `webdebit-v7-offsite-pull-desktop` và recipient của nó trên `hao`;
  giữ khóa age của nó tới khi bản mã hóa bằng nó hết hạn giữ.
- Ba PC cùng một nơi với `hao`; chưa có cảnh báo khi lượt lỗi (audit #2).
