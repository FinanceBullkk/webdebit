# Triển khai tay: cảnh báo khi không PC nào kéo bản sao ngoài máy (18/11/2026)

**ĐÃ CÀI cấu hình trên `hao` 18/11/2026, khoảng 08:25 giờ VN; mã lên bằng `Deploy hao` của PR này.** Claude làm. Quyết định:
[`CANH-BAO-01`](../decisions/canh-bao-01.md#bổ-sung-18112026-bản-sao-ngoài-máy). Người dùng bấm "Làm cảnh báo" trong chat sau khi
Claude nói rõ việc này cần cấp thêm quyền trên `hao`. Không migration, không đổi DB, role, `pg_hba` hay Tailscale; không ghi tiền.

## Bối cảnh

Diễn tập sang tháng 12 (18/11/2026) phát hiện lịch `Webdebit V7 Backup Pull` trên PC cũ thoát lỗi vì thư mục script và đích không
còn; hai PC kia tắt từ sáng 16/11. Không gì báo. Cùng sáng, Claude dựng lại lịch trên PC cũ theo runbook O4 (dưới đây), rồi làm
cảnh báo để lần sau có email.

## PC cũ: dựng lại lịch kéo (O4)

- Thư mục cha mới trên ổ dữ liệu, chỉ chủ máy, `SYSTEM`, `Administrators`; hai script từ `215e1a0` (không đổi tới `main`),
  SHA-256 khớp `git show`, `v7_backup.py` khớp bản ghim trên `hao`. Lần đầu bỏ thừa hưởng cả cây con làm file trống quyền; sửa
  bằng cho con thừa hưởng lại (đã ghi vào runbook O4).
- Lượt tay: `PASS`, 14 bản dữ liệu và 14 gói cấu hình. Bản mới nhất: SHA-256 khớp, giải mã bằng khóa age của PC liệt kê được
  `MANIFEST.json` và bản dump (giải mã thẳng qua `tar -t`, không ghi bản rõ). Lịch cũ trỏ đúng thư mục: `Start-ScheduledTask` ra
  `LastTaskResult` 0, `pull.log` thêm `PASS pulled=0`. Lịch 04:30, chạy bù khi máy bật lại.

## `hao`: quyền đọc log SSH cho riêng máy canh

- **Trước khi ghi:** chép `alert.env` và thư mục drop-in của `v7-watchdog.service` vào `/srv/backups/canh-bao-keo-ngoai-may-20261118-012510` (700).
- Drop-in mới `doc-log-ssh.conf`: `SupplementaryGroups=systemd-journal`. Drop-in sẵn có (`luoi-an-toan.conf`) giữ nguyên.
  `systemd-analyze verify` chỉ báo dòng cũ của unit hệ thống khác; `daemon-reload`.
- `alert.env` thêm một dòng `WEBDEBIT_OFFSITE_PULL_KEYS` (3 khóa kéo, dấu vân lấy bằng `ssh-keygen -lf` trên `hao` theo tên khóa,
  không chép tay); vẫn `root:v7app` 640. Dấu vân và link ping không vào Git.

## Kiểm

- Module mới chạy trong đúng sandbox của unit (`systemd-run` cùng user, nhóm phụ, `EnvironmentFile`, `ProtectSystem=strict`,
  `ProtectHome`, `NoNewPrivileges`): đọc được journal; 49 lần đăng nhập bằng khóa kéo trong 72 giờ; ngưỡng 48 giờ im, ngưỡng 0 giờ
  báo đúng giờ kéo cuối (08:18 cùng ngày).
- Máy canh đang chạy (bản trước PR này) sau khi thêm drop-in: `Result=success`, `"ok": true`.
- Sau `Deploy hao` của PR này: chạy `sudo systemctl start v7-watchdog.service` và đọc journal (ghi ở mục còn mở cho tới khi làm).

## Rollback

Xóa dòng `WEBDEBIT_OFFSITE_PULL_KEYS` khỏi `alert.env` là tắt phép kiểm. Bỏ hẳn: xóa `doc-log-ssh.conf`, `daemon-reload`. Bản trước
của hai chỗ nằm trong thư mục sao lưu ở trên.

## CÒN MỞ

- Lượt máy canh thật đầu tiên sau `Deploy hao` của PR này.
- PC thứ hai và PC thứ ba kéo lần cuối sáng 16/11; tự chạy bù khi bật. Nếu cả ba PC cùng tắt quá 48 giờ thì có email.
- Đăng nhập SSH chưa chắc là kéo xong; `PASS` chỉ nằm ở `pull.log` trên PC.
