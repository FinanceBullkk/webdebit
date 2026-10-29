# Triển khai tay: backup V7 hằng ngày (29/10/2026)

**ĐÃ CÀI trên `hao` ngày 29/10/2026**, Claude chạy sau khi người dùng duyệt trong chat ("Cài luôn"), vì cài unit systemd mới
là đổi ngoài runbook theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Không migration, không đổi DB, không ghi tiền.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#169 (`0ca04eb`): lệnh `v7_backup.py daily`, sửa `repository_roots` cho bản sao không có `.git`, mẫu unit trong runbook |
| Quy trình | [Runbook — Backup hằng ngày](../v7-deploy-runbook.md#backup-hằng-ngày--timer-v7-backup-daily), bước B1–B5 |
| Checklist | [C1, C2](../song-song-checklist.md#c-vận-hành) |

## Đã làm

- **B1:** bản ghim `/opt/webdebit-backup/cong-no-web-handoff/tools/v7_backup.py` (root, 644) chép từ blob của `0ca04eb`;
  SHA-256 trên `hao` khớp `git show 0ca04eb:…` (`b386b56e…f4e3`). Thư mục gốc `/srv/v7-backup-daily` (chủ `postgres`, 700).
  Vấp: shell admin để `umask 077` nên `install -d` tạo hai thư mục cha 700 (chỉ thư mục cuối nhận `-m 755`), `postgres`
  không vào được. Đã đặt lại 755 cho từng cấp trước lượt chạy đầu và sửa lệnh trong runbook.
- **B2:** hai unit đúng nguyên văn runbook (hash khớp bản trích từ runbook ở `0ca04eb`). `systemd-analyze verify` không
  báo lỗi ở hai unit; lịch kế tiếp 02:40 giờ VN.
- **B3:** `systemctl start v7-backup-daily.service` lúc 19:48 giờ VN: 8 giây, `Result=success`. Journal `"ok": true`,
  31 bảng, 236 khách, dump 1.909.164 byte. Thư mục `v7-20261029-194852` 700, `sokhach.dump` và `MANIFEST.json` 600, chủ
  `postgres`; `verify` in `MATCH`. `MANIFEST.json` đủ trường, `format_version` 1, PostgreSQL và `pg_dump` 18.6,
  236 tổng nợ, không tổng nào NULL.
- **B4:** phục hồi thử bản đó vào một DB tạm mới (thu hồi CONNECT của PUBLIC): `restore` mã thoát 0, `MATCH`, số dòng
  31 bảng và tổng nợ 236 khách khớp `MANIFEST.json`, 10 giây. Đã xóa DB tạm, kiểm còn 0.
- **B5:** `v7-backup-daily.timer` enabled, active; NEXT 30/10 02:40 giờ VN (19:40 UTC ngày 29/10).

Bằng chứng: thư mục `v7-backup-daily-install-20261029-194749` cạnh thư mục backup của các đợt nâng trên `hao` (hash bản
ghim và unit, journal lượt đầu, tóm tắt manifest, báo cáo restore có id khách và tổng nợ), 700/600, ngoài Git.
Bản backup lượt đầu: `/srv/v7-backup-daily/v7-20261029-194852`.

## Rollback

`sudo systemctl disable --now v7-backup-daily.timer`, giữ các bản đã có. Gỡ hẳn theo runbook.

## CÒN MỞ

- C1 đạt khi có thêm bản của lượt timer 30/10 02:40 (ngày thứ hai liên tiếp).
- Bản sao ra máy khác: dữ liệu PostgreSQL và `/srv` cùng một ổ vật lý. Chưa có cảnh báo khi lượt backup lỗi.
- Trên `hao` còn 13 DB restore/tổng duyệt của các đợt trước (`v7_prb_*`, `webdebit_v7_*restore*`, …), mỗi DB là một bản sao
  dữ liệu khách. Không thuộc việc này nên chưa xóa; cần người dùng quyết.
