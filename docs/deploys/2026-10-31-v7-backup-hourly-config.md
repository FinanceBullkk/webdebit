# Triển khai tay: backup V7 mỗi giờ, gói cấu hình/globals, kéo về PC thứ hai (31/10/2026)

**ĐÃ CÀI trên `hao` và PC thứ hai ngày 31/10/2026, 13:09–14:03 giờ VN.** Claude làm. Người dùng duyệt trong chat cùng ngày
("Cài tất cả": hai unit/timer mới, thêm recipient age, thêm một dòng `authorized_keys` chỉ SFTP đọc, cài `age` và lịch
Windows trên PC; "Dump hằng ngày": hai DB legacy vào gói cấu hình) vì đều là đổi ngoài runbook theo
[`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Phiên điều phối giữ `main` suốt cửa sổ. Không migration, không đổi
DB, role, `pg_hba` hay Tailscale; không ghi tiền.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#223 (`215e1a0`): `v7_backup.py config`/`config-verify`, `v7_offsite_pull.py` kéo hai họ, runbook |
| Quy trình | Runbook: [backup mỗi giờ](../v7-deploy-runbook.md#backup-mỗi-giờ--timer-v7-backup-hourly) H1–H4, [gói cấu hình](../v7-deploy-runbook.md#gói-cấu-hình-và-globals--timer-v7-backup-config) K1–K5, [bản sao ngoài máy](../v7-deploy-runbook.md#bản-sao-ngoài-máy--timer-v7-backup-offsite) O1–O5 cho PC thứ hai |
| Vì sao | audit DevOps 31/10 #4: RPO 24 giờ trước khi người nhập ghi thật song song với Sheet từ 1/11/2026; dump thiếu role và cấu hình máy; bản ngoài máy chỉ ở PC cũ |

## Đã làm

- **Trước khi ghi:** journal `sudo` 30 phút chỉ có lệnh chỉ đọc của phiên này; không phiên PostgreSQL nào khác; sự kiện
  `sokhach` gần nhất từ 30/10. Bản trước của bản ghim, file recipient và `authorized_keys` chép vào thư mục bằng chứng.
- **Bản ghim (B1/K1):** `Deploy hao` của `215e1a0` xanh; `v7_backup.py` chép từ release đó, SHA-256 `7d151719…e809` khớp
  `git show 215e1a0:…` (trước đó `d00e29c8…`). `verify` bản ngày mới nhất `v7-20261031-024009` bằng bản ghim mới: MATCH.
- **PC thứ hai (O1, O2):** `age` 1.3.2 (winget, phạm vi user); khóa age và khóa SSH ed25519 riêng trong `.ssh` của chủ máy
  (ACL chỉ chủ máy, `SYSTEM`, `Administrators`). Recipient thêm một dòng (`tee -a`, 1 → 2 dòng); `authorized_keys` thêm đúng
  một dòng `restrict,from=…,command="…sftp-server -R -d /srv/v7-backup-offsite"` (so trước/sau). Kiểm bằng khóa mới: lệnh `id`
  không chạy, thư mục làm việc là hộp chờ, `ls` được, `put` bị từ chối; khóa quản trị cũ vẫn đăng nhập. Vấp: PowerShell 7
  truyền nguyên `-N '""'` nên khóa SSH có passphrase là hai dấu nháy và `BatchMode` không ký được; đã bỏ passphrase bằng
  `ssh-keygen -p` (cặp khóa không đổi), runbook O1 ghi cách đúng.
- **Unit (H2/K2):** bốn unit đúng nguyên văn runbook ở `215e1a0` (hash khớp bản trích từ runbook); `systemd-analyze verify`
  không báo lỗi ở unit mới; lịch giờ: 06:00–22:00 giờ VN, lượt sau 22:00 là 06:00 hôm sau. `/srv/v7-backup-hourly`
  `postgres` 700.
- **Backup mỗi giờ (H3):** `systemctl start` 13:18: 12 giây, `Result=success`, JSON `"ok": true`, 32 bảng, 236 khách, dump
  2.133.598 byte; thư mục 700, tệp 600; `verify` MATCH. Phục hồi thử bản `v7-20261031-131845` vào DB tạm mới
  `webdebit_v7_restore_test_20261031` (thu hồi CONNECT của PUBLIC): `restore` mã thoát 0, `MATCH`, số dòng 32 bảng và tổng
  nợ 236 khách khớp `MANIFEST.json`, 9 giây; đã `dropdb`, kiểm còn 0. Timer enabled. **Lượt timer đầu** 14:00 giờ VN:
  `v7-20261031-140007`, `Result=success`, `"ok": true`, `verify` MATCH.
- **Gói cấu hình (K3):** `systemctl start` 13:23: 6 giây, `Result=success`, `v7-config-20261031-132302.tar.age` 2.366.314
  byte, 55 tệp, 10 symlink, `missing` rỗng; cặp tệp root nhóm quản trị 640; `sha256sum -c` OK. Timer enabled, lượt kế
  02:50 giờ VN (giữa bản ngày 02:40 và `offsite` 03:00).
- **Bản dữ liệu cho PC thứ hai giải mã được ngay:** các archive cũ trong hộp chờ chỉ mã hóa cho khóa PC cũ, nên chạy tay
  `offsite` một lần dưới `postgres` (`umask 0027`) với gốc `/srv/v7-backup-hourly`: `v7-20261031-131845.tar.age`, mã hóa cho
  hai recipient, giữ 14 không đổi. Từ lượt 03:00 ngày 1/11 bản ngày tự mã hóa cho cả hai.
- **Kéo về PC thứ hai (O4):** script từ `215e1a0` (hash khớp); lượt tay `PASS pulled=4 … config_pulled=1
  config_newest=v7-config-20261031-132302.tar.age`, 6 giây. Lịch `Webdebit V7 Backup Pull` 04:40 (`pythonw.exe`, chạy khi
  chủ máy đăng nhập, `StartWhenAvailable`, tối đa 30 phút): `Start-ScheduledTask` → `LastTaskResult=0`, `PASS pulled=0`;
  lượt kế 1/11 04:40. Thư mục script và thư mục đích trên ổ dữ liệu, ngoài OneDrive và mọi checkout, ACL chỉ chủ máy.
- **Phục hồi thử trên PC (O5/K4):** SHA-256 khớp; `age` giải mã cả hai bằng khóa của PC thứ hai; `verify` bản giờ MATCH;
  `config-verify` `MATCH config archive: 55 files, 10 links, 0 missing patterns`. PostgreSQL 18.6 Docker `--network none`,
  **không** tạo role trước: `psql -f globals.sql` chỉ báo `role "postgres" already exists`, tạo đủ 12 role còn lại; `restore`
  bản giờ mã thoát 0, `MATCH`, 32 bảng, 236 khách, 4 giây. Hai dump legacy: `pg_restore -l` đọc được (72 và 51 mục). Đã xóa
  container, volume và mọi bản rõ.

Bằng chứng: thư mục `v7-backup-hourly-config-install-20261031-060925` cạnh thư mục backup của các đợt nâng trên `hao`
(bản trước/sau của ba file đổi, hash bản ghim và unit, journal lượt đầu, lịch, báo cáo restore có id khách và tổng nợ, tóm
tắt), 700/600, ngoài Git.

## Rollback

`sudo systemctl disable --now v7-backup-hourly.timer v7-backup-config.timer`; giữ các bản đã có. PC thứ hai:
`Disable-ScheduledTask -TaskName 'Webdebit V7 Backup Pull'`, xóa dòng `webdebit-v7-offsite-pull-desktop` trong
`authorized_keys` và dòng recipient thứ hai (bản trước khi sửa nằm trong thư mục bằng chứng). Bản ghim cũ `d00e29c8…` cũng
nằm ở đó; lệnh `daily`/`offsite` của bản mới hành xử như cũ.

## CÒN MỞ

- Lượt tự động đầu của gói cấu hình 1/11 02:50 và bản ngày mã hóa cho hai PC 1/11 03:00; PC thứ hai kéo 04:40. Đạt khi
  journal `v7-backup-config` có `"ok": true` và `pull.log` có `config_newest=v7-config-20261101-…`.
- **Chủ máy chép khóa age của PC thứ hai ra USB hoặc giấy, cất riêng** (khóa PC cũ cũng vậy, CÒN MỞ từ 29/10). Mất cả hai
  khóa là mọi bản ngoài máy vô dụng.
- PC cũ vẫn chạy script kéo của `f796d94`: kéo tiếp bản dữ liệu, bỏ qua gói cấu hình. Muốn PC cũ có cả gói cấu hình thì
  chép script mới sang theo O4.
- Chưa có cảnh báo khi lượt lỗi ở cả hai timer mới (audit #2). Bản giờ không ra khỏi `hao`: hỏng ổ thì RPO vẫn tới bản
  02:40. Hai PC cùng một nơi với `hao`.
