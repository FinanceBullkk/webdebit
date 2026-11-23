# Dựng lại `hao` từ bản sao lưu

| Trạng thái | Phạm vi |
| --- | --- |
| ĐỀ XUẤT | Checklist này, viết 23/11/2026 theo audit vận hành (O5). Dựa trên gói cấu hình (`v7_backup.py config`) và bản dữ liệu (`offsite`) mà các PC kéo về mỗi ngày |
| ĐÃ KIỂM CHỨNG | Từng mảnh: phục hồi dump ra DB mới trên `hao` (29/10/2026) và trong Docker trên PC (O5, K4 của [runbook](v7-deploy-runbook.md)); test sao lưu → khôi phục thật chạy trong CI từ 23/11/2026 |
| CÒN MỞ | **Chưa diễn tập cả máy trên máy khác** (E1 của [checklist chuyển hẳn](chuyen-han-checklist.md)): chưa có số phút thật, chưa biết bước nào thiếu. Cần một PC/VM trống, x86_64 |

Dùng khi ổ của `hao` hỏng, máy chết hẳn, hoặc để diễn tập. Không chạy trên `hao` đang sống. Mỗi bước có **Đạt khi**; không đạt
thì dừng, ghi vào nhật ký, không đoán. Cái gì đang chạy ở đâu: [van-hanh.md](van-hanh.md).

**Mất gì khi ổ chết:** dữ liệu sau bản ngày gần nhất mà PC đã kéo (02:40 mỗi ngày; bản mỗi giờ không rời ổ `hao`). Tiền đi từ Sheet
(chuyến, giá, phiếu thu) máy tự theo lại sau khi chạy; dữ liệu chỉ có trên web trong khoảng đó thì mất: Đội xe, dấu đã xem, thay
đổi danh sách đăng nhập, kết luận CHỜ KIỂM. Ghi lại cho người dùng biết phải nhập lại gì.

**Cần có trước:** một PC kéo có khóa age (`webdebit-v7-backup-age-key.txt`) và `pull.log` mới; tài khoản Tailscale, GitHub
(quyền sửa secret/variable của repo), healthchecks.io; máy mới x86_64, ổ ≥ 250 GB, cài được Ubuntu Server cùng bản lớn với
`inventory/packages.txt`.

## A. Lấy bản và kiểm (trên PC)

1. Chọn cặp mới nhất trong `<pc_dir>`: `v7-<ngày>.tar.age` và `v7-config-<ngày>.tar.age` (`pull.log` dòng cuối `PASS`, có
   `newest=` và `config_newest=`). **Đạt khi** cả hai cùng ngày hoặc gói cấu hình mới hơn.
2. Giải mã và kiểm gói cấu hình theo K4 của runbook (`age --decrypt`, `v7_backup.py config-verify`). **Đạt khi** `MATCH config
   archive`, số `missing` chỉ gồm mẫu đã biết (ví dụ `command:inventory/lvm.txt`).
3. Giải mã và kiểm bản dữ liệu theo O5 (`v7_backup.py verify --from`). **Đạt khi** `MATCH`. Ghi số khách và giờ bản.
4. Đọc `inventory/packages.txt`, `apt-manual.txt`, `passwd.txt`, `group.txt`, `lsblk.json`, `lvm.txt`, `unit-files.txt`,
   `timers.txt` trong gói (`tar -xf <tar> <thành_viên>`). Đây là danh sách phải dựng lại.

## B. Máy và hệ điều hành

5. Cài Ubuntu Server cùng bản lớn; chia đĩa theo `lsblk.json` / `lvm.txt` (các mount `/`, `/srv`, `/var/lib/postgresql`).
   Hostname theo `files/etc/hostname`. User quản trị như cũ, khóa SSH của PC quản trị. **Đạt khi** SSH vào được bằng khóa.
6. Nguồn apt theo `files/etc/apt/` (PGDG cho PostgreSQL 18, Tailscale), rồi cài gói trong `apt-manual.txt`. Tối thiểu:
   `postgresql-18`, `python3` (3.14 như `hao`), `age`, `tailscale`, `curl`, `ufw`, `openssh-server`, `nodejs` (chỉ khi cài bot
   Zalo). **Đạt khi** `psql --version` ra 18.x, `python3 --version` ra 3.14.x.
7. User và nhóm hệ thống theo `passwd.txt` / `group.txt` (tên giữ nguyên, UID có thể khác): `v7app`, `webdebit-deploy`, các
   nhóm của chúng; user bot Zalo chỉ khi đã cài bot. **Đạt khi** `id v7app`, `id webdebit-deploy` đúng nhóm như bảng kê.

## C. Mạng

8. `tailscale up` (người dùng đăng nhập), đặt tên máy `hao` trên trang quản trị tailnet để tên `hao.<tailnet>.ts.net` giữ
   nguyên; gắn lại tag như máy cũ. Xóa node cũ trên trang quản trị. **Đạt khi** PC quản trị `ping hao` qua tailnet.
9. Dựng Tailscale Serve theo `tailscale-serve.json` (cổng 8443 → `127.0.0.1:8780`). **Đạt khi** `tailscale serve status`
   giống bản cũ.
10. Chép `files/etc/ssh/sshd_config*`, `files/etc/ufw/user*.rules`, `files/etc/sudoers.d/*` về đúng chỗ, chủ và quyền theo
    `tar -tvf`; `visudo -c`, `sshd -t`, rồi reload. **Đạt khi** cả hai lệnh kiểm không lỗi và SSH vẫn vào được.

## D. PostgreSQL và dữ liệu

11. Chép `files/etc/postgresql/18/main/` (giữ `pg_hba.conf`, `postgresql.conf`), restart. **Đạt khi** `pg_lsclusters` báo
    18/main online, chỉ socket `/var/run/postgresql`.
12. `sudo -u postgres psql -X -f globals.sql` (dòng `role "postgres" already exists` là bình thường). **Đạt khi** có đủ role
    như máy cũ (`\du`).
13. Tạo DB V7 rỗng với tên và chủ như máy cũ, thu `CONNECT` của PUBLIC như B4 của runbook, rồi `v7_backup.py restore --from
    <bản dữ liệu đã giải mã> --target-db <db_v7>`. **Đạt khi** dòng 1 `MATCH`, số khách bằng bước 3.
14. Hai DB legacy: `pg_restore` từ `databases/*.dump` của gói cấu hình vào DB cùng tên. **Đạt khi** `pg_restore -l` và số bảng
    khớp.

## E. Cấu hình app

15. Chép về đúng đường dẫn, chủ và quyền theo tar: `/etc/webdebit/` (env, khóa tài khoản dịch vụ Google, `alert.env`),
    `/etc/webdebit-backup/`, `/etc/webdebit-deploy.conf`, `/srv/v7/customer-name-mapping.json`, `/srv/v7/so-goc-20261020/`,
    `/var/lib/webdebit-sheet-sync/access/access.json`, `/var/lib/webdebit-sheet-sync/baseline-refs.json`, crontab nếu có.
    Tạo thư mục trạng thái như máy cũ (`/var/lib/webdebit-sheet-sync` của `v7app`, `/var/lib/v7-watchdog`, hộp chờ
    `/srv/v7-backup-offsite`, `/srv/v7-backup-daily`, `/srv/v7-backup-hourly`). **Đạt khi** `ls -l` từng chỗ khớp `tar -tvf`.
16. Thư mục release (`RELEASES_DIR` trong `/etc/webdebit-deploy.conf`) thuộc `webdebit-deploy`; cài `scripts/deploy/hao-release.sh`
    từ `main` vào đường dẫn root-owned như [cài đặt một lần](hao-auto-deploy.md#cài-đặt-một-lần-người-dùngadmin-ngoài-repo),
    kiểm SHA-256. Tạo cặp khóa deploy mới, dòng `authorized_keys` có `command=` như cũ, cập nhật secret `HAO_SSH_KEY_B64`,
    biến `HAO_SSH_KNOWN_HOSTS` (khóa máy mới) và `HAO_SSH_HOST` nếu IP tailnet đổi.
17. Release đầu tay (máy mới chưa có `current`, `Deploy hao` sẽ dừng): ở một checkout `main`,
    `git archive <sha> $(grep -v -e '^#' -e '^$' scripts/deploy/release-paths.txt) > release.tar`, chép lên, rồi
    `sudo -u webdebit-deploy env SSH_ORIGINAL_COMMAND="deploy <sha>" <script> < release.tar`. **Đạt khi** dòng `đã chạy <sha>`.
18. Ghim `v7_backup.py` vào `/opt/webdebit-backup` theo B1 của runbook. **Đạt khi** hash khớp `git show`.

## F. Bật máy theo thứ tự

19. Chép unit, timer, drop-in từ `files/etc/systemd/system/`, `daemon-reload`, `systemd-analyze verify` từng unit.
20. Bật API (`v7-ledger-api`) trước. **Đạt khi** `curl -s http://127.0.0.1:8780/healthz` ra 200 và web mở được qua Serve.
21. **Đối soát tổng khách** trước mọi máy ghi: tổng nợ từng khách trên DB mới bằng `customer_totals` trong `MANIFEST.json` của
    bản dữ liệu (chạy `v7_post_deploy_check.sql`). **Đạt khi** mọi khách khớp.
22. Bật runner chỉ đọc: `webdebit-sheet-sync`, `webdebit-sheet-prices`, `webdebit-ps-snapshot`, `webdebit-company-info`,
    `.path` làm mới. **Đạt khi** các bản chụp trong `/var/lib/webdebit-sheet-sync` mới dưới 15 phút.
23. Bật sao lưu (`v7-backup-hourly`, `-daily`, `-config`, `-offsite`), chạy tay mỗi cái một lượt. **Đạt khi** `Result=success`.
24. Bật máy ghi tiền cuối cùng: `v7-reconcile-auto.timer` (chạy một lượt tay, đọc `reconcile.json`) và cờ
    `WEBDEBIT_AUTO_SHEET` của API (drop-in `auto-sheet.conf` đã chép ở bước 19). **Đạt khi** lượt đối soát không có
    `VERIFY_FAILED`/`WRITE_ERROR` và tổng khách vẫn khớp Sheet.
25. Bật máy canh `v7-watchdog.timer`. **Đạt khi** `journalctl -u v7-watchdog.service -n 1 -o cat` ra `"ok": true` và mọi check
    trên healthchecks.io xanh.

## G. Ngoài `hao`

26. Mỗi PC kéo: thay khóa máy của `hao` trong `known_hosts` (khóa máy mới), thêm lại dòng `authorized_keys` của khóa kéo (lấy
    `.pub` trên PC) như O2, sửa `WEBDEBIT_OFFSITE_PULL_KEYS` nếu dấu vân đổi. Chạy task kéo một lượt. **Đạt khi** `pull.log`
    có `PASS` và healthchecks của PC xanh.
27. Máy Zalo (`msi`): agent đẩy lên đúng tên `hao` mới (tên tailnet giữ nguyên thì không đổi gì). **Đạt khi** tab Máy chạy có
    nhịp tim mới.
28. Ghi nhật ký `docs/deploys/<ngày>-dung-lai-hao.md`: giờ bắt đầu/kết thúc từng phần A–G (số phút), bước nào thiếu, dữ liệu
    web phải nhập lại. Sửa checklist này theo cái vừa học. Lần diễn tập đầu đạt thì đóng E1.
