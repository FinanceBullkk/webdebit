# Diễn tập dựng lại `hao` trên máy trống (E1, 25/11/2026)

Lý do: từ 1/12/2026 web là sổ duy nhất ([`WEB-CHINH-01`](../decisions/web-chinh-01.md)), không còn Sheet để dựng lại dữ liệu,
nên RPO/RTO thành việc đầu. Phiên điều phối giao; làm theo [rebuild-hao.md](../rebuild-hao.md) bản 23/11. **Không đụng `hao`
thật**: chỉ đọc vài thông số trên `hao` (bản OS, cổng đang nghe, chủ và locale của DB) để so. Không đổi DB, quyền hay tiền.

| Mục | Nội dung |
| --- | --- |
| Máy | PC kéo `msi`; Docker 29.7, ảnh chính thức `ubuntu:26.04`, `/sbin/init` (systemd) trong container `--privileged`, mạng `none` (chỉ `lo`) |
| Bản dùng | Cặp mới nhất PC đã kéo lúc 04:50: bản dữ liệu 02:40 và gói cấu hình 02:50 ngày 25/11, `sha256sum -c` cả hai OK |
| Mã | `main` `a648abc8` (release); `v7_backup.py` của nhánh PR này (thêm `--hourly`) để thử unit bản giờ |
| Dọn | Xóa container, ảnh, thư mục giải mã trên PC ngay sau diễn tập; bản đã mã hóa trên PC không đổi |

Mạng: chỉ bật hai lần, trước khi có file cấu hình nào chạy, để `apt-get` (bước B6 và lần cài `locales`, `ssl-cert`). Sau đó
mạng `none` tới hết: các khóa thật trong gói (Google, healthchecks.io, Cloudflare) không thể gọi ra ngoài.

## Số phút (giờ PC)

| Phần | Từ → tới | Kết quả |
| --- | --- | --- |
| A. kiểm hash, giải mã, `config-verify`, `verify` | 17:49:29 → 17:49:30 | `MATCH config archive: 118 files, 12 links, 1 missing` (`lvm`); bản dữ liệu `MATCH`, 246 khách, 36 bảng |
| B. cài gói | 17:49:45 → 17:51:06 | PostgreSQL 18.6, Python 3.14.4, age 1.2.1, certbot 4.0.0: cùng bản `hao` |
| B. khởi động systemd, user, sshd/sudoers | 17:51 → 17:56 | `visudo -c`, `sshd -t` đạt. Phần lớn thời gian là gỡ cách chạy systemd trong Docker, không phải lỗi của trang |
| D. PostgreSQL, role, DB V7, legacy | 17:56:02 → 17:58:07 | cấu hình của `hao` không chạy được tới khi có locale (dưới); 13 role; restore `MATCH`, 246 khách trong khoảng 10 giây; hai DB legacy đủ bảng |
| E. cấu hình app, unit, release | 17:58:52 → 18:00:00 | release `a648abc8` lên, API không lên tới khi tạo thư mục trạng thái (dưới) |
| F20. API | 18:00:00 → 18:00:28 | `/healthz` 200, `db: ok`, 246 sổ; phải tạm bỏ drop-in 8445 (không có Tailscale) |
| F21. checker + tổng khách | 18:00:37 → 18:01:25 | checker báo lệch catalog tới khi áp lại migration sau giờ bản (dưới); sau đó thoát 0; tổng nợ 246/246 khách bằng `MANIFEST.json` |
| F23. sao lưu | 18:01:52 → 18:02:05 | `hourly`, `daily`, `offsite`, `offsite-hourly` đạt; bản giờ niêm trong máy diễn tập giải mã và `verify` được trên PC; `config` lỗi vì không có `tailscale` (đúng dự kiến) |
| F25. máy canh `--dry-run` | 18:02:21 → 18:02:33 | chạy hết các phép kiểm, báo đúng phần chưa bật (bản chụp Sheet, timer, nhóm journal) |

Lõi dữ liệu, từ giải mã tới web trả đúng số: **khoảng 13 phút** (17:49:29 → 18:02:33), kể cả các lần sửa dưới đây.

## Trang hướng dẫn sai hoặc thiếu (đã sửa trong cùng PR)

1. **Locale và chứng chỉ snakeoil.** `postgresql.conf` của `hao` đặt `lc_*` = `en_US.UTF-8` và `ssl = on` với snakeoil; máy
   trống thiếu cả hai nên PostgreSQL không khởi động. Thêm bước cài `locales` (sinh `en_US.UTF-8`) và `ssl-cert` trước
   `postgresql-18`.
2. **PostgreSQL từ kho Ubuntu 26.04**, không phải PGDG như trang cũ ghi.
3. **UID 1000 đã có** (user `ubuntu` của ảnh); trang ghi rõ tên phải giữ, UID thì không.
4. **`globals.sql` 600 root**: `psql -f` dưới `postgres` không đọc được; đưa qua stdin.
5. **Chủ, locale, quyền của từng DB không có trong gói.** Phải đọc trên `hao`. Gói cấu hình thêm `databases.txt`.
6. **Migration sau giờ của bản.** Bản 02:40, migration của #655 merge và áp tay 03:13: checker báo `catalog differs from repo
   manifest: get_ledger(bigint)`. Thêm bước D13b: liệt kê migration sau `created_at_vn` của bản, áp lại theo thứ tự.
7. **Thư mục trạng thái không có trong gói.** Unit API có `ReadWritePaths` tới `nhat-ky`, `office`…; thiếu là `226/NAMESPACE`.
   Thêm bước tạo thư mục và bảng kê `inventory/dirs.txt` trong gói.
8. **Thứ tự unit và release.** Script release restart API nên unit phải có trước release; trang cũ chép unit ở F19, sau release.
9. **API thoát khi IP tailnet không khớp** (`cannot verify Tailscale IP`), kéo theo cả web cổng 8443. Trang ghi: đặt lại IP cũ
   cho node mới, hoặc sửa drop-in, DNS, compose, `HAO_SSH_HOST`.
10. **`v7_post_deploy_check.sql` không có trong gói release** (đúng thiết kế); lấy bằng `git show`.
11. **Thiếu hẳn:** cổng 8445 (`/etc/letsencrypt` chưa có trong gói: chứng chỉ chép trong `tailnet-tls` có, cách gia hạn và token
    DNS thì không), các cổng Serve khác và app Docker, `authorized_keys` (unit gói chạy `ProtectHome=true`), `/var/lib/v7-watchdog`.
    Gói thêm `/etc/letsencrypt`, `/var/lib/v7-watchdog`, `/usr/local/sbin`, compose của app; `authorized_keys` dựng lại từ `.pub`.

## Chưa thử (ghi trong trang)

Cài Ubuntu lên máy thật; Tailscale (đăng nhập, IP, Serve) và cổng 8445 với DNS thật, `certbot renew --dry-run`; runner Sheet,
máy đối soát ghi thật, máy canh gửi thật (cần mạng và khóa thật); gói cấu hình trên máy mới; app Docker; PC kéo lại từ máy mới,
`Deploy hao` với khóa mới.

## RPO/RTO

- RPO trước PR này: tới khoảng 26 giờ (bản giờ chỉ trên ổ `hao`). Sau khi cài bản giờ ra ngoài: tối đa khoảng 1 giờ 45 phút
  trong 6–22 giờ khi có PC bật; ngoài giờ là bản ngày.
- RTO: lõi 13 phút đo được; ước cả máy thật lần đầu 2–3 giờ (cài OS, Tailscale/DNS/GitHub cần người dùng đăng nhập).
