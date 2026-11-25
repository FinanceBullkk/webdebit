# Dựng lại `hao` từ bản sao lưu

| Trạng thái | Phạm vi |
| --- | --- |
| ĐÃ KIỂM CHỨNG | Diễn tập 25/11/2026 trên máy trống (Docker Ubuntu 26.04 có systemd, không mạng, trên PC kéo), từ cặp bản 25/11 đã kéo về: A, B (trừ cài OS lên máy thật), D, E, F20, F21, sao lưu ở F23 đạt; web trả `/healthz` 200 và tổng nợ cả 246 khách bằng `MANIFEST.json`. Lõi dữ liệu (giải mã → web chạy đúng số) mất khoảng 13 phút ([nhật ký](deploys/2026-11-25-dien-tap-dung-lai-hao.md)) |
| CHƯA THỬ | Cài Ubuntu lên máy thật; Tailscale (đăng nhập, IP, Serve), cổng 8445 với DNS thật, gia hạn chứng chỉ; runner Sheet, máy đối soát, máy canh gửi thật (cần mạng và khóa thật); app Docker; PC kéo lại từ máy mới. Lần dựng thật hoặc diễn tập sau làm những phần này |
| CÒN MỞ | Dữ liệu app Docker ngoài Vaultwarden (Uptime Kuma, AdGuard, pgAdmin, techies-bcm) không có bản sao; chưa ai chốt có cần không |

Dùng khi ổ của `hao` hỏng, máy chết hẳn, hoặc để diễn tập. Không chạy trên `hao` đang sống. Mỗi bước có **Đạt khi**; không đạt
thì dừng, ghi vào nhật ký, không đoán. Cái gì đang chạy ở đâu: [van-hanh.md](van-hanh.md).

**Mất gì khi ổ chết (RPO):** dữ liệu sau bản mới nhất mà một PC đã kéo. Trong 6–22 giờ là bản giờ (niêm :20, PC kéo :35–:45,
[O7 của runbook](v7-deploy-runbook.md#o7-bản-giờ-ra-ngoài--timer-v7-backup-offsite-hourly-bổ-sung-25112026)), tức tối đa
khoảng 1 giờ 45 phút khi có PC bật; ngoài giờ là bản ngày 02:40. Từ 1/12/2026 web là sổ duy nhất
([`WEB-CHINH-01`](decisions/web-chinh-01.md)): phần mất phải nhập lại tay. Ghi lại cho người dùng biết khoảng giờ đó.

**Bao lâu (RTO):** lõi dữ liệu đo được 13 phút khi máy đã có OS. Ước cả máy thật, lần đầu theo trang này: cài OS 30–45 phút, lõi
30 phút, Tailscale/DNS/GitHub/PC 30–60 phút có người dùng đăng nhập; khoảng 2–3 giờ.

**Cần có trước:** một PC kéo có khóa age (`webdebit-v7-backup-age-key.txt`) và `pull.log` mới; tài khoản Tailscale (quản trị
tailnet), Cloudflare (DNS của tên miền cổng 8445), GitHub (quyền sửa secret/variable của repo), healthchecks.io; máy mới
x86_64, ổ ≥ 250 GB, cài được Ubuntu Server cùng bản với `inventory/packages.txt` (26.04 lúc viết). Một checkout `main` để lấy
script và file SQL.

## A. Lấy bản và kiểm (trên PC)

1. Chọn bản mới nhất: so `newest=` trong `pull.log` của `<pc_dir>` (bản ngày) và `<pc_dir>\gio` (bản giờ, `v7-hourly-…`);
   lấy bản có giờ muộn hơn, cùng gói cấu hình `v7-config-…` mới nhất. **Đạt khi** dòng cuối cả hai `pull.log` là `PASS`.
2. `sha256sum -c` từng `.sha256`, giải mã bằng khóa age, `v7_backup.py config-verify --tar` cho gói cấu hình (K4 của runbook).
   **Đạt khi** `MATCH config archive`, `missing` chỉ gồm mẫu đã biết (ví dụ `command:inventory/lvm.txt`).
3. Giải nén bản dữ liệu (thư mục ra luôn tên `v7-<ngày>-<giờ>`, kể cả bản giờ) và `v7_backup.py verify --from`. **Đạt khi**
   `MATCH`. Ghi số khách và `created_at_vn` trong `MANIFEST.json`: bước D13b cần giờ này.
4. Đọc trong gói (giải nén ở máy Linux; Windows không tạo được liên kết của `files/etc/systemd/system/*.wants`):
   `inventory/packages.txt`, `apt-manual.txt`, `passwd.txt`, `group.txt`, `lsblk.json`, `unit-files.txt`, `timers.txt`,
   `dirs.txt` (thư mục, chủ, quyền), `databases.txt` (chủ, locale, quyền từng DB). Gói trước 25/11/2026 chưa có hai file sau.

Diễn tập 25/11: A mất khoảng 1 phút.

## B. Máy và hệ điều hành

5. Cài Ubuntu Server cùng bản; chia đĩa theo `lsblk.json` (`/`, `/srv` riêng, `/var/lib/postgresql`). Hostname theo
   `files/etc/hostname`, `files/etc/hosts` (thiếu dòng tên máy thì `sudo` báo `unable to resolve host`). User quản trị như
   cũ, khóa SSH của PC quản trị. **Đạt khi** SSH vào được bằng khóa.
6. **Trước** `postgresql-18`: cài `locales`, mở `en_US.UTF-8` trong `/etc/locale.gen`, `locale-gen`; cài `ssl-cert`. Thiếu hai
   thứ này thì `postgresql.conf` của `hao` không chạy được (`invalid value for parameter "lc_messages"`, chứng chỉ snakeoil),
   và cụm tạo trước locale sẽ không cùng locale với DB cũ. Rồi cài theo `apt-manual.txt`; tối thiểu `postgresql-18` (từ kho
   Ubuntu 26.04, không phải PGDG), `python3` (3.14), `age`, `curl`, `sudo`, `ufw`, `openssh-server`, `jq`, `certbot`,
   `python3-certbot-dns-cloudflare`, `tailscale` (kho theo `files/etc/apt/sources.list.d/tailscale.list`), `docker.io`,
   `docker-compose-v2` (app Docker, mục H). **Đạt khi** `psql --version` 18.x, `python3 --version` 3.14.x, `locale -a` có
   `en_US.utf8`.
7. User và nhóm theo `passwd.txt` / `group.txt`; tên phải giữ, UID thì không (ảnh Ubuntu có sẵn user `ubuntu` UID 1000):
   `aohanh` (nhóm `sudo`, `docker`), `v7app` (hệ thống, `nologin`), `webdebit-deploy`. **Đạt khi** `id` từng user đúng nhóm.

Diễn tập: cài gói 81 giây (mạng PC), user 1 phút.

## C. Mạng

8. `tailscale up` (người dùng đăng nhập), đặt tên máy `hao` trên trang quản trị tailnet; xóa node cũ trước để tên giữ nguyên.
   **Đặt lại IP tailnet cũ cho node mới** (trang quản trị → máy → Edit IPv4 address; IP cũ là `V7_TAILNET_HTTPS_IP` trong
   `files/etc/systemd/system/v7-ledger-api.service.d/tailnet-https.conf`). Lý do: API kiểm IP này lúc khởi động và **thoát hẳn**
   nếu máy không mang nó (`cannot verify Tailscale IP`), tức cả web cổng 8443 cũng tắt; compose của app Docker cũng gắn cổng
   vào IP đó. Không giữ được IP cũ thì sửa `V7_TAILNET_HTTPS_IP` trong drop-in, bản ghi A của tên miền 8445 trên Cloudflare,
   cổng trong `/srv/services/compose.yaml`, và biến `HAO_SSH_HOST` của repo (bước E16). **Đạt khi** `tailscale ip -4` ra đúng
   IP đó và PC quản trị `ping hao` được.
9. Dựng Tailscale Serve theo `tailscale-serve.json`: `:8443` → `127.0.0.1:8780` (API), `:443` → `127.0.0.1:8080`
   (Vaultwarden), `:8444` → `127.0.0.1:8081` (tailfleet của `aohanh`), `:10000` → `127.0.0.1:5174` và `/bcm-api` →
   `127.0.0.1:3010` (techies-bcm). Chỉ `:8443` là của sổ nợ; các cổng khác chờ app ở mục H. **Đạt khi** `tailscale serve
   status` giống bản cũ.
10. Chép `files/etc/ssh/sshd_config*`, `files/etc/ufw/user*.rules`, `files/etc/sudoers`, `files/etc/sudoers.d/*` về đúng chỗ,
    chủ và quyền theo `tar -tvf`; `visudo -c`, `sshd -t`, rồi reload. **Đạt khi** cả hai lệnh kiểm không lỗi và SSH vẫn vào được.
11. `~aohanh/.ssh/authorized_keys` **không có trong gói** (unit gói cấu hình chạy `ProtectHome=true`). Dựng lại từ `.pub` trên
    từng PC, đủ các loại dòng: khóa quản trị của từng PC (thường); mỗi PC kéo một dòng `restrict,from="<pc_ip>",command="/usr/lib/openssh/sftp-server -R -d /srv/v7-backup-offsite"`
    ([O2](v7-deploy-runbook.md#o2-trên-hao-mã-recipient-hộp-chờ-khóa-ssh)); các khóa của app khác (tailfleet, Vaultwarden) lấy
    lại từ máy dùng chúng. Khóa deploy ở `~webdebit-deploy/.ssh/authorized_keys` làm ở E16. Sửa `WEBDEBIT_OFFSITE_PULL_KEYS`
    trong `alert.env` nếu dấu vân đổi. **Đạt khi** mỗi PC `sftp` liệt kê được hộp chờ, `put` bị từ chối.
12. Cổng 8445 (tên miền riêng, chứng chỉ Let's Encrypt qua DNS Cloudflare): gói từ 25/11/2026 có `/etc/letsencrypt` (khóa
    tài khoản, chứng chỉ, `cloudflare/*.ini` chứa token DNS, cấu hình gia hạn, hook `renewal-hooks/deploy/webdebit-tailnet.sh`)
    và `/etc/webdebit/tailnet-tls/` (bản chép mà API đọc). Chép cả hai, giữ quyền (`cloudflare` 700 root, `tailnet-tls` 750
    root:v7app). Chạy `/etc/letsencrypt/renewal-hooks/deploy/webdebit-tailnet.sh --copy-only` để chép lại chứng chỉ cho API.
    Gói cũ hơn không có `/etc/letsencrypt`: chứng chỉ trong `tailnet-tls` vẫn dùng được tới hạn; xin lại bằng `certbot
    certonly --dns-cloudflare` với token mới tạo trên Cloudflare. **Đạt khi** `certbot renew --dry-run` không lỗi và
    `curl -sI https://<ten_mien_8445>:8445/` từ PC trong tailnet ra mã HTTP.

## D. PostgreSQL và dữ liệu

13. Chép `files/etc/postgresql/18/main/` (giữ `pg_hba.conf`, `postgresql.conf`, `conf.d/`), restart. **Đạt khi**
    `pg_lsclusters` báo 18/main online, chỉ socket `/var/run/postgresql`.
14. `sudo -u postgres psql -X -f - < globals.sql` (file 600 của root nên đưa qua stdin; dòng `role "postgres" already exists`
    là bình thường). **Đạt khi** đủ role như máy cũ (`\du`; 25/11: 13 role ngoài `pg_*`).
15. Tạo DB V7 rỗng theo `databases.txt` (chủ `postgres`, `TEMPLATE template0 ENCODING UTF8 LOCALE 'en_US.UTF-8'`), rồi quyền
    như cột cuối: `REVOKE ALL ON DATABASE <db_v7> FROM PUBLIC`, `GRANT TEMPORARY … TO PUBLIC`, `GRANT CONNECT … TO v7_app,
    v7_loader`. Chép bản dữ liệu sang thư mục `postgres` đọc được, `sudo -u postgres env PGHOST=/var/run/postgresql python3 -I
    <v7_backup.py> restore --from <thư mục> --target-db <db_v7>`. **Đạt khi** dòng 1 `MATCH`, số khách bằng bước 3.
    Diễn tập: 10 giây.
16. **Migration sau giờ của bản (D13b).** Bản là ảnh lúc `created_at_vn`; migration áp tay lên `hao` sau giờ đó không có trong
    bản, nên checker ở F21 sẽ báo `catalog differs from repo manifest`. Ở checkout `main`: `git log --since="<created_at_vn>"
    --format='%h %ad %s' -- cong-no-web-handoff/tools/migrations`, đối chiếu nhật ký `docs/deploys/` cùng ngày, rồi áp từng
    file theo thứ tự với `ON_ERROR_STOP=1` như nhật ký đó (lấy file bằng `git show <sha>:<đường dẫn>`, so SHA-256). Diễn tập
    25/11: bản 02:40, migration của #655 merge 03:13, áp lại 124 ms thì checker đạt. **Đạt khi** không còn migration nào sau
    giờ của bản.
17. Hai DB legacy (`webdebit_ledger`, `webdebit_pilot_system`): tạo DB như bước 15 với quyền theo `databases.txt`, `pg_restore
    --exit-on-error -d <db> < databases/<db>.dump`. **Đạt khi** số bảng trong DB bằng số dòng `TABLE` (không tính `TABLE
    DATA`) của `pg_restore -l`.

## E. Cấu hình app

18. Chép về đúng đường dẫn, chủ và quyền theo tar: `/etc/webdebit/` (env, khóa tài khoản dịch vụ Google, `alert.env`),
    `/etc/webdebit-backup/`, `/etc/webdebit-deploy.conf`, `/srv/v7/customer-name-mapping.json`, `/srv/v7/so-goc-20261020/`,
    `/var/lib/webdebit-sheet-sync/access/access.json`, `/var/lib/webdebit-sheet-sync/baseline-refs.json`, `/var/lib/v7-watchdog/`
    (mốc lưới an toàn; thiếu thì lượt đầu ghi mốc mới), `/usr/local/sbin/`, crontab nếu có.
19. **Thư mục trạng thái** theo `inventory/dirs.txt`, tối thiểu: `/var/lib/webdebit-sheet-sync` và các con `office`, `nhat-ky`,
    `export`, `reconcile-work`, `access` (700 `v7app`), file `refresh.request` (644 `v7app`); `/var/lib/v7-watchdog` (700
    `v7app`); `/srv/v7-backup-offsite` (2750 `postgres:aohanh`); `/srv/v7-backup-daily`, `/srv/v7-backup-hourly` (700
    `postgres`); `/srv/v7/zalo-agent`, `zalo-bundle`, `zalo-reads`, `insurance` (2750 `aohanh:v7app`). Thiếu một thư mục trong
    `ReadWritePaths` thì unit không lên (`226/NAMESPACE`, diễn tập gặp ở `nhat-ky`). **Đạt khi** `ls -ld` khớp bảng kê.
20. Chép unit, timer, drop-in từ `files/etc/systemd/system/` (cả các liên kết `*.wants`), `systemctl daemon-reload`. **Làm trước
    release** vì script release restart API. Chưa `enable`/`start` timer nào; liên kết `*.wants` đã chép nghĩa là máy khởi động
    lại sẽ bật hết, nên đừng khởi động lại tới khi xong F.
21. Thư mục release (`RELEASES_DIR` trong `/etc/webdebit-deploy.conf`) thuộc `webdebit-deploy`; cài `scripts/deploy/hao-release.sh`
    từ `main` vào `/usr/local/sbin/webdebit-release.sh` (root, 755) như [cài đặt một lần](hao-auto-deploy.md#cài-đặt-một-lần-người-dùngadmin-ngoài-repo),
    kiểm SHA-256. Tạo cặp khóa deploy mới, dòng `authorized_keys` có `command=` như cũ, cập nhật secret `HAO_SSH_KEY_B64`,
    biến `HAO_SSH_KNOWN_HOSTS` (khóa máy mới) và `HAO_SSH_HOST` nếu IP tailnet đổi.
22. Release đầu tay: ở checkout `main`, `git archive <sha> $(grep -v -e '^#' -e '^$' scripts/deploy/release-paths.txt) >
    release.tar`, chép lên, `sudo -u webdebit-deploy env SSH_ORIGINAL_COMMAND="deploy <sha>" /usr/local/sbin/webdebit-release.sh
    < release.tar`. Kiểm sống lỗi (exit 5) mà `current` đã trỏ bản mới thì sửa nguyên nhân rồi `systemctl start v7-ledger-api`;
    chạy lại release chỉ in `đã chạy <sha>, bỏ qua`. **Đạt khi** `cat /srv/v7/auto-releases/current/.release-sha` là `<sha>`.
23. Ghim `v7_backup.py` vào `/opt/webdebit-backup/cong-no-web-handoff/tools/` (root, 644) theo B1 của runbook. **Đạt khi** hash
    khớp `git show`.

Diễn tập: E (cả hai lần sửa) khoảng 2 phút.

## F. Bật máy theo thứ tự

24. Bật API (`systemctl start v7-ledger-api`). Cần IP tailnet đúng (bước 8): chưa có Tailscale thì tạm chuyển
    `tailnet-https.conf` ra ngoài, `daemon-reload`, bật lại khi xong C. **Đạt khi** `curl -s http://127.0.0.1:8780/healthz`
    ra 200 với `"db": "ok"` và `inbox.books` bằng số sổ, web mở được qua Serve.
25. **Đối soát tổng khách** trước mọi máy ghi. `v7_post_deploy_check.sql` và `v7_catalog_manifest.json` không nằm trong gói
    release: lấy bằng `git show <sha>:cong-no-web-handoff/tools/<file>` vào thư mục `postgres` đọc được, chạy như
    [mục post-deploy của runbook](v7-deploy-runbook.md) (`-v db_v7=… -v loader_role=v7_loader -v manifest=…`). Rồi so tổng nợ
    từng khách với `customer_totals` của `MANIFEST.json`: `get_ledger(id)->'total_outstanding_vnd'` trong giao dịch
    `BEGIN READ ONLY; SET LOCAL sokhach.actor='…'`. **Đạt khi** checker thoát 0 và 0 khách lệch (25/11: 246/246).
26. Bật runner chỉ đọc: `webdebit-sheet-sync`, `webdebit-ps-snapshot`, `webdebit-company-info`, `.path` làm mới
    (`webdebit-sheet-prices` chỉ khi chưa tắt Sheet sổ nợ theo `WEB-CHINH-01`). **Đạt khi** bản chụp trong
    `/var/lib/webdebit-sheet-sync` mới dưới 15 phút.
27. Bật sao lưu (`v7-backup-hourly`, `-daily`, `-config`, `-offsite`, `-offsite-hourly`), chạy tay mỗi cái một lượt.
    `-config` cần Tailscale (`tailscale serve status`), nên sau C. **Đạt khi** mọi `Result=success` và hộp chờ có
    `v7-<…>.tar.age`, `v7-hourly-<…>.tar.age`, `v7-config-<…>.tar.age`. Diễn tập: bốn unit đầu và bản giờ đạt trong 13 giây,
    bản giờ niêm trong máy diễn tập giải mã và `verify` được trên PC.
28. Bật máy ghi tiền cuối cùng: `v7-reconcile-auto.timer` (chạy tay một lượt, đọc `reconcile.json`) và cờ `WEBDEBIT_AUTO_SHEET`
    của API (drop-in `auto-sheet.conf` đã chép ở bước 20). **Đạt khi** lượt đối soát không có `VERIFY_FAILED`/`WRITE_ERROR` và
    tổng khách vẫn khớp.
29. Bật máy canh `v7-watchdog.timer`. **Đạt khi** `journalctl -u v7-watchdog.service -n 1 -o cat` ra `"ok": true` và mọi check
    trên healthchecks.io xanh. Diễn tập chạy `--dry-run` không mạng: máy canh chạy hết, báo đúng các phần chưa bật.

## G. Ngoài `hao`

30. Mỗi PC kéo: thay khóa máy của `hao` trong `known_hosts`, chạy task kéo ngày và task kéo giờ một lượt. **Đạt khi** cả hai
    `pull.log` có `PASS` và check của PC, check bản giờ trên healthchecks.io xanh.
31. Máy Zalo (`msi`): agent đẩy lên đúng tên `hao` (tên tailnet giữ nguyên thì không đổi gì). **Đạt khi** tab Máy chạy có nhịp
    tim mới.
32. GitHub: lượt `Deploy hao` kế tiếp xanh với khóa và known_hosts mới.

## H. App Docker cùng máy (không phải sổ nợ)

| App | Compose / dữ liệu | Bản sao |
| --- | --- | --- |
| Vaultwarden (`:443`, `127.0.0.1:8080`) | `/opt/vaultwarden/compose.yaml` (trong gói từ 25/11/2026), dữ liệu `/srv/appdata/vaultwarden` | `vaultwarden-backup.timer` 03:30 niêm age vào `/srv/backups/vaultwarden` (khóa age riêng), PC kéo bằng task riêng; phục hồi theo hướng dẫn của bản đó |
| Uptime Kuma, AdGuard Home | `/srv/services/compose.yaml` (trong gói từ 25/11/2026), dữ liệu `/srv/appdata/uptime-kuma`, `/srv/appdata/adguard` | không có: dựng mới, cấu hình lại tay |
| pgAdmin | container không có compose, dữ liệu `/srv/appdata/pgadmin` | không có |
| techies-bcm (`:10000`) | `/home/aohanh/techies-bcm` (dự án riêng) | không có trong gói; hỏi chủ dự án |
| tailfleet (`:8444`) | `tailfleet.service` của `aohanh`, Node trong `~/.nvm` | không có trong gói |

Bật sau khi sổ nợ đã chạy (F). **Đạt khi** `tailscale serve status` trỏ tới cổng đang nghe.

## Sau khi dựng

Ghi nhật ký `docs/deploys/<ngày>-dung-lai-hao.md`: giờ bắt đầu/kết thúc từng phần A–H (số phút), bước nào thiếu, khoảng giờ
dữ liệu phải nhập lại. Sửa trang này theo cái vừa học.
