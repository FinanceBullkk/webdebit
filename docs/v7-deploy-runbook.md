# Runbook triển khai V7 — ĐỀ XUẤT

**Chưa triển khai, chưa chạy trên máy chủ thật. Không bước nào tự chạy.**
Người dùng chạy trên máy chủ sau thông báo/gate riêng của phiên điều phối chính.
Đây không phải quyền chạy DDL từ task tài liệu. Không ghi/đổi cấu hình DB `webdebit_ledger`.

| Trạng thái | Phạm vi |
| --- | --- |
| ĐỀ XUẤT | Quy trình 0–8; SQL schema còn nhãn DRAFT, cần review commit và gate triển khai riêng |
| ĐÃ CHỐT | Người dùng + phiên điều phối, 21/10/2026: PostgreSQL 18 trực tiếp/systemd, chỉ unix socket `/var/run/postgresql`; DB V7 riêng; app/loader dùng OS user riêng, peer, không mật khẩu |
| ĐÃ KIỂM CHỨNG (bản sao Docker) | Tổng duyệt 21/10/2026 trên PostgreSQL 18.6 dùng một lần (`--network none`, xác thực trust, API chạy ở máy chạy kịch bản): `status=pass` đủ bước 1–7 kể cả rollback B/C và dọn sạch, với bản sạch thật 236 khách / 877 dòng mở đầu (báo cáo và hash ở thư mục log ngoài repo) và với bản giả; đo thời gian từng bước ghi trong báo cáo. KHÔNG phải kiểm máy chủ thật: peer, systemd, Tailscale chưa thử |
| CÒN MỞ | Peer/pg_hba thực tế; dung lượng thật; lịch backup V7; quyền người chạy; nghiệm thu danh tính/service; triển khai chính sách mới còn gate |

Giới hạn: Sheet vẫn chính thức theo [SONG-SONG-01](decisions.md#song-song-01).
Opening theo [OPENING-SO-GOC](decisions.md#opening-so-goc); mốc chuyến là bản xuất mới nhất
ngày bắt đầu chạy song song, làm sạch bằng `v7_export_clean.py`, không lấy bản tổng duyệt cũ
([MOC-CHUYEN-MOI](decisions.md#moc-chuyen-moi)). Danh tính theo [V7-ID](decisions.md#v7-id).
[Gate chưa đóng](decisions.md#gate-chưa-đóng), gồm triển khai V7-CSM, không được tự đóng bằng test.
VND `bigint`; NULL/blank không thành 0.

## Quy ước và hợp đồng hoàn thành

Thay tất cả `<...>` trước khi chạy; không gõ nguyên placeholder vào shell.
`<db_v7>` khác `webdebit_ledger`, `<restore_db>` là DB mới chưa tồn tại; tên DB/role chỉ ASCII
`[A-Za-z_][A-Za-z0-9_]*`, tối đa 63 ký tự. `<loader_role>` khác `v7_app` và `postgres`.
`<release>` là gói mã từ đúng commit, ngoài repo, chỉ đọc với user app/loader.
`<backup_dir>`, `<evidence_dir>`, `<clean_dir>`, `<new_outside_repo_dir>` ngoài mọi checkout,
không công khai. Backup/evidence quyền 700, tệp 600; lệnh chuyển hướng chạy trong shell admin
đã `umask 077`. PostgreSQL admin ở các lệnh DB dưới đây là OS user `postgres`.
User app không có sudo/role loader. User loader chỉ dùng khi nạp, không chạy service.

Đạt: backup phục hồi thử khớp exact counts; DB riêng có ACL đúng; nạp từ manifest/hash;
GET và đối soát đạt; legacy counts không đổi. Dừng ngay khi lệnh lỗi, thiếu evidence hoặc gate;
không chạy tiếp, không sửa SQL/API/nạp để né lỗi. Không ghi phiếu thử trên dữ liệu thật.
Thời gian các mục **chưa đo**, không phải cam kết; JSON tổng duyệt ghi `steps[].seconds`.

## 0. Gate, commit và gói mã

Mục đích: khóa đúng revision. Ai: người dùng + admin DB. Đạt: lệnh đi tiếp rõ của người dùng,
commit `<commit>` được review và CI xanh đúng SHA (không chỉ xanh nhánh). Dừng: thiếu bất kỳ gate.
Thời gian: chưa đo, lấy log điều phối; phần này không đo bằng Docker.

```bash
umask 077
```

```bash
install -d -m 700 <evidence_dir>
```

Trích gói từ commit, không từ working tree. Gói gồm schema/hàm, checker, toàn bộ tools/web
và preview cần cho API; kiểm lại không có dữ liệu/bí mật. Không dùng gói handoff/release cũ.

```bash
install -d -m 755 <release>
```

```bash
git archive <commit> specs/v7-backend/schema-draft.sql cong-no-web-handoff/tools cong-no-web-handoff/web cong-no-web-handoff/preview | tar -x -C <release>
```

Hash bytes từ `git show`, lưu đường dẫn tương đối + SHA-256 ngoài repo; gồm mã API, identity,
nạp trực tiếp, bộ đọc bản sạch và các module import. Không lấy hash working tree.

```bash
git ls-tree -r --name-only <commit> specs/v7-backend/schema-draft.sql cong-no-web-handoff/tools cong-no-web-handoff/web | while IFS= read -r file; do printf '%s  %s\n' "$(git show "<commit>:$file" | sha256sum | cut -d ' ' -f 1)" "$file"; done > <evidence_dir>/release.sha256
```

```bash
sha256sum -c <evidence_dir>/release.sha256
```

Lệnh kiểm hash chạy với thư mục hiện tại là `<release>`. Ghi commit/tree, CI URL và người chạy
trong hồ sơ ngoài Git. Không copy tên khách, số tiền hoặc cấu hình máy vào PR.

## 1. Preflight CHỈ ĐỌC

Mục đích: chứng minh máy/DB nền đúng trước ghi. Ai: admin DB (sudo hệ thống chỉ cho kiểm service/socket).
Đạt: 18.x; client cùng major; service active; unix socket đúng; không TCP kể cả cổng khác;
DB/roles V7 chưa có; trống ít nhất 3× `pg_database_size('webdebit_ledger')` tại nơi backup và data.
Dừng: khác kỳ vọng hoặc không đủ quyền đọc. Thời gian: chưa đo, xem `preflight.seconds`.

```bash
sudo systemctl is-active <postgres_unit>
```

```bash
sudo ss -lxnp
```

```bash
sudo ss -ltnp
```

Không được có PostgreSQL TCP listener; đặc biệt không có `:5432`. Không coi `grep` rỗng khi
lệnh `ss` lỗi là đạt. Phiên SQL khung dùng dưới đây, nhập câu SQL rồi `\q`:

```bash
psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d postgres
```

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d postgres -c "SELECT current_setting('server_version'),current_setting('listen_addresses'),current_setting('unix_socket_directories'); SELECT datname FROM pg_database ORDER BY datname; SELECT rolname FROM pg_roles WHERE rolname ~ '^(sokhach_|v7_)' OR rolname='<loader_role>'; SELECT pg_database_size('webdebit_ledger');" > <evidence_dir>/preflight.txt
```

```bash
psql --version
```

```bash
pg_dump --version
```

```bash
pg_restore --version
```

```bash
df -B1 <backup_parent>
```

```bash
df -B1 <postgres_data_mount>
```

Lưu script exact counts ngoài repo. Chỉ đọc tên bảng từ catalog và `count(*)`, không đọc khách/tiền.
`<evidence_dir>/counts.sql` chứa:

```sql
SELECT format('SELECT %L, count(*) FROM %I.%I;', schemaname||'.'||tablename,schemaname,tablename)
FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') AND schemaname NOT LIKE 'pg_toast%'
ORDER BY schemaname,tablename
\gexec
```

```bash
sudo -u postgres psql -X -qAt -v ON_ERROR_STOP=1 -h /var/run/postgresql -d webdebit_ledger < <evidence_dir>/counts.sql > <evidence_dir>/baseline.counts
```

Baseline này phải giữ đến rollback. Nếu viewer có writer khác thì dừng, chọn cửa sổ không ghi;
count không chứng minh nội dung từng hàng, backup vẫn là bắt buộc.

## 2. Backup toàn phần trước mọi ghi DB/cấu hình

Mục đích: phục hồi được baseline. Ai: admin DB. Đạt: globals + custom dump, list đọc được,
restore thử khớp exact counts, xóa DB thử và hash mọi tệp backup. Dừng: restore/hash/count lỗi;
giữ backup lỗi, không tái dùng thư mục. Thời gian: chưa đo, `backup_restore.seconds`; dữ liệu thật có thể lâu hơn.

```bash
install -d -m 700 <backup_dir>
```

Lệnh khung chạy dưới OS postgres; shell admin giữ output ngoài repo:

```bash
pg_dumpall -h /var/run/postgresql -U postgres --globals-only
```

```bash
sudo -u postgres pg_dumpall -h /var/run/postgresql -U postgres --globals-only > <backup_dir>/globals.sql
```

```bash
pg_dump -h /var/run/postgresql -U postgres -Fc webdebit_ledger
```

```bash
sudo -u postgres pg_dump -h /var/run/postgresql -U postgres -Fc webdebit_ledger > <backup_dir>/ledger.dump
```

```bash
pg_restore --list < <backup_dir>/ledger.dump > <backup_dir>/restore.list
```

```bash
sudo -u postgres createdb -h /var/run/postgresql <restore_db>
```

```bash
sudo -u postgres pg_restore -h /var/run/postgresql -U postgres --exit-on-error --single-transaction -d <restore_db> < <backup_dir>/ledger.dump
```

```bash
sudo -u postgres psql -X -qAt -v ON_ERROR_STOP=1 -h /var/run/postgresql -d <restore_db> < <evidence_dir>/counts.sql > <evidence_dir>/restore.counts
```

```bash
diff -u <evidence_dir>/baseline.counts <evidence_dir>/restore.counts
```

```bash
sudo -u postgres dropdb -h /var/run/postgresql <restore_db>
```

```bash
sudo -u postgres psql -X -At -h /var/run/postgresql -d postgres -c "SELECT count(*) FROM pg_database WHERE datname='<restore_db>';"
```

Kỳ vọng 0. Không restore globals vào cluster đang chạy. Giữ globals cho sự cố cluster và review riêng.

```bash
sha256sum <backup_dir>/globals.sql <backup_dir>/ledger.dump <backup_dir>/restore.list > <evidence_dir>/backup.sha256
```

```bash
chmod 600 <backup_dir>/globals.sql <backup_dir>/ledger.dump <backup_dir>/restore.list
```

## 3. Provision một lần

Mục đích: DB V7 riêng, least privilege. Ai: admin DB; hệ thống sửa cấu hình sau backup.
Đạt: checker OK; app/loader peer qua đúng OS user; không đổi legacy.
Dừng: role/DB đã tồn tại, DDL/checker lỗi hoặc peer lỗi. Không chạy lại schema sau lỗi; rollback B rồi review.
Thời gian: chưa đo, `provision.seconds`; cấu hình peer không có số đo Docker.

Trong phiên admin SQL bước 1:

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d postgres -c 'CREATE DATABASE <db_v7>;'
```

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -f <release>/specs/v7-backend/schema-draft.sql
```

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -f <release>/cong-no-web-handoff/tools/v7_backend_functions.sql
```

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d <db_v7> -c 'CREATE ROLE v7_app LOGIN IN ROLE sokhach_app; CREATE ROLE <loader_role> LOGIN IN ROLE sokhach_owner; REVOKE CONNECT ON DATABASE <db_v7> FROM PUBLIC; GRANT CONNECT ON DATABASE <db_v7> TO v7_app,<loader_role>;'
```

Không mật khẩu, không SUPERUSER/CREATEROLE/CREATEDB/REPLICATION/BYPASSRLS. DB tạo bằng admin;
app chỉ 14 hàm. Loader có owner membership, không cấp cho app và không dùng `postgres` để nạp.
OS users tạo theo chính sách máy; không tạo trong kịch bản Docker.

Trước sửa, sao lưu cấu hình thật (đường dẫn lấy bằng `SHOW hba_file; SHOW ident_file;`):

```bash
sudo cp --preserve=all <pg_hba_path> <backup_dir>/pg_hba.before
```

```bash
sudo cp --preserve=all <pg_ident_path> <backup_dir>/pg_ident.before
```

Thêm trước rule local tổng quát, giữ nguyên rule quản trị/legacy. `pg_hba.conf`:

```text
local <db_v7> v7_app peer map=v7_peer
local <db_v7> <loader_role> peer map=v7_peer
```

`pg_ident.conf`:

```text
v7_peer <os_user_app> v7_app
v7_peer <os_user_loader> <loader_role>
```

```bash
sha256sum <backup_dir>/pg_hba.before <backup_dir>/pg_ident.before > <evidence_dir>/config.sha256
```

```bash
sudo systemctl reload <postgres_unit>
```

```bash
sudo -u <os_user_app> psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U v7_app -d <db_v7> -c 'SELECT current_user;'
```

```bash
sudo -u <os_user_loader> psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U <loader_role> -d <db_v7> -c 'SELECT current_user;'
```

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -v db_v7=<db_v7> -v loader_role=<loader_role> -f <release>/cong-no-web-handoff/tools/v7_post_deploy_check.sql
```

Thêm `-v expect_customers=0 -v expect_openings=0` trước nạp. Checker chỉ đọc, không in khách/tiền.
Kiểm `pg_hba_file_rules`/`pg_ident_file_mappings` không lỗi; reload thành công chưa chứng minh peer đúng.

## 4. Kế hoạch và nạp mốc

Mục đích: nạp đúng bản xuất ngày bắt đầu song song. Ai: OS loader, không phải user app/admin DB.
Đạt: bản sạch mới nhất qua `v7_export_clean.py`, source XLSX hash/manifest đúng, count khách/tháng/dòng
khớp; plan không đổi DB, apply đạt và checker count đúng. Dừng: hash/count lỗi, thiếu mỏ neo,
ngoại lệ chưa giải quyết hoặc target không rỗng. Không thêm `--allow-nonempty`.
Thời gian: chưa đo, `load.seconds`.

```bash
sha256sum <clean_dir>/manifest.json <clean_dir>/clean_customers.csv <clean_dir>/clean_months.csv <clean_dir>/clean_rows.csv > <evidence_dir>/clean.sha256
```

CLI không có `--plan`/`--report`: mặc định là PLAN, stdout chuyển vào hồ sơ riêng. Lệnh khung:

```bash
python <release>/cong-no-web-handoff/tools/v7_load_direct.py --from-clean <clean_dir> --socket-dir /var/run/postgresql --database <db_v7> --loader-role <loader_role>
```

```bash
sudo -u <os_user_loader> <python> <release>/cong-no-web-handoff/tools/v7_load_direct.py --from-clean <clean_dir> --socket-dir /var/run/postgresql --database <db_v7> --loader-role <loader_role> > <evidence_dir>/load-plan.json
```

Admin kiểm khách/mốc còn 0, so PLAN `books`/`openings` với manifest `counts.customers`/`counts.months`,
so `input_sha256` manifest; không đưa số tiền ra terminal công khai. `clean_data` kiểm cả hash file/count.

```bash
python <release>/cong-no-web-handoff/tools/v7_load_direct.py --from-clean <clean_dir> --socket-dir /var/run/postgresql --database <db_v7> --loader-role <loader_role> --apply
```

```bash
sudo -u <os_user_loader> <python> <release>/cong-no-web-handoff/tools/v7_load_direct.py --from-clean <clean_dir> --socket-dir /var/run/postgresql --database <db_v7> --loader-role <loader_role> --apply > <evidence_dir>/load-apply.json
```

Loader còn lưu báo cáo tại thư mục temp `v7-direct-reports`; người chạy bảo vệ/chuyển vào hồ sơ riêng,
không upload. Kết nối loader là một transaction; lỗi chưa rõ commit thì dừng và đọc lại trạng thái.

## 5. Service API và danh tính

Mục đích: API loopback với peer và danh tính từng người từ Tailscale Serve. Ai: admin hệ thống,
service chạy OS app. Đạt: unit active, peer đúng `v7_app`, người khác nhau ghi actor khác nhau
trong tổng duyệt danh tính riêng; không test ghi trên bản thật. Dừng: port 8777, DB TCP,
dev actor, identity không xác minh hoặc scope Serve đè dịch vụ khác. Thời gian: chưa đo; Docker thay bằng host API.

Mẫu `<unit>.service` (không có biến môi trường mật khẩu):

```ini
[Unit]
Description=V7 ledger API
After=<postgres_unit> tailscaled.service
Requires=<postgres_unit>

[Service]
User=<os_user_app>
WorkingDirectory=<release>
ExecStart=<python> <release>/cong-no-web-handoff/web/v7_ledger_api.py --direct-socket-dir /var/run/postgresql --database <db_v7> --db-user v7_app --behind-tailscale-serve --serve-host <serve_fqdn>:<serve_port> --port <port>
Restart=on-failure
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

`<serve_fqdn>` lấy từ cấu hình Serve được admin kiểm; giá trị chữ thường,
khớp chính xác Host công khai gồm cổng HTTPS (bỏ `:443` nếu URL dùng cổng mặc định).
`--serve-host` lặp được, chỉ dùng cùng `--behind-tailscale-serve`; mặc định rỗng giữ
Host loopback cũ. Không wildcard/suffix, không suy allowlist từ header. API và asset
cùng nhận Host đã cấu hình; POST chỉ nhận Origin `https://<serve-host>` tương ứng.
`<port>` khác 8777, chỉ bind mặc định loopback. Không `--insecure-dev-actor`.
Kiểm cổng trống và lưu `tailscale serve status --json` ngoài repo trước đổi. Dùng cổng HTTPS
riêng chưa có route, không `tailscale serve reset` vì có thể ảnh hưởng viewer.

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl enable --now <unit>.service
```

```bash
sudo tailscale serve --bg --https=<serve_port> http://127.0.0.1:<port>
```

```bash
sudo systemctl is-active <unit>.service
```

```bash
sudo tailscale serve status --json > <evidence_dir>/serve.after.json
```

Serve phải cung cấp danh tính Tailscale tin cậy, tailnet gate riêng theo người; không public Funnel.
Header client tự khai không là bằng chứng. Docker dùng dev actor loopback có tên, chỉ thay thế kiểm DB/API,
không xác nhận systemd/Serve/peer. Quyền truy cập và thu hồi phải review trước mở dùng thật.

## 6. Kiểm sau triển khai, không ghi thử

Mục đích: đọc/đối soát thật mà không tạo tiền thử. Ai: admin DB chạy SQL; user app/chủ nghiệp vụ đọc API.
Đạt: checker OK với `<customer_count>` và `<opening_count>` từ manifest, GET 200, `DOI SOAT: DAT`,
legacy exact counts không đổi. Dừng: sai bất kỳ mục nào, giữ evidence và rollback A.
Thời gian: chưa đo, `api_reconcile.seconds`.

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -v db_v7=<db_v7> -v loader_role=<loader_role> -v expect_customers=<customer_count> -v expect_openings=<opening_count> -f <release>/cong-no-web-handoff/tools/v7_post_deploy_check.sql
```

```bash
curl --fail --silent --show-error https://<serve_fqdn>:<serve_port>/api/v7/customers > <evidence_dir>/customers.json
```

```bash
curl --fail --silent --show-error 'https://<serve_fqdn>:<serve_port>/api/v7/ledger?customer=<customer_id>' > <evidence_dir>/ledger.json
```

Chạy GET và đối soát từ máy trong tailnet qua URL Serve ở trên, xác minh TLS bình thường;
không dùng `-k`, header Host hay header danh tính tự gắn. Serve cung cấp danh tính.
GET loopback trực tiếp không mặc nhiên có actor và có thể trả 403.
Công cụ nhận HTTPS chỉ khi authority (FQDN và cổng như URL) khớp chính xác một
`--serve-host`; lặp được. HTTP loopback có port vẫn dùng cho test/dev cũ.
Mọi redirect bị từ chối, kể cả cùng host. Không thêm header giả/dev actor để né lỗi.

```bash
python <release>/cong-no-web-handoff/tools/v7_reconcile_sheet.py --api https://<serve_fqdn>:<serve_port> --serve-host <serve_fqdn>:<serve_port> --sheet-dir <clean_dir> --out <new_outside_repo_dir> --brief
```

```bash
sudo -u postgres psql -X -qAt -v ON_ERROR_STOP=1 -h /var/run/postgresql -d webdebit_ledger < <evidence_dir>/counts.sql > <evidence_dir>/after.counts
```

```bash
diff -u <evidence_dir>/baseline.counts <evidence_dir>/after.counts
```

## 7. Rollback theo mức

### A — dừng đường truy cập

Mục đích: ngừng phục vụ, giữ dữ liệu để điều tra. Ai: admin hệ thống. Đạt: unit inactive,
route riêng biến mất, port API hết listener. Dừng: không xác định được route thuộc task thì không gỡ route khác.
Thời gian: chưa đo, không mô phỏng systemd/Serve bằng Docker.

```bash
sudo tailscale serve --https=<serve_port> off
```

```bash
sudo systemctl disable --now <unit>.service
```

```bash
sudo systemctl is-active <unit>.service
```

```bash
sudo tailscale serve status --json
```

```bash
sudo ss -ltnp
```

### B — xóa V7, giữ legacy

Mục đích: trở về trước provision. Ai: admin DB/hệ thống, sau A và sau khi lưu hồ sơ V7 cần giữ.
Xóa DB V7 mất dữ liệu V7; chỉ chạy khi người dùng đã chọn rollback mức B.
Đạt: DB/roles V7 hết, config/unit đã gỡ, legacy counts khớp. Dừng: dependencies/phiên DB còn mở;
không `DROP OWNED`/CASCADE rộng. Thời gian: chưa đo, `rollback_B.seconds` chỉ đo phần DB.

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d postgres -c 'DROP DATABASE <db_v7>;'
```

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d postgres -c 'DROP ROLE v7_app; DROP ROLE <loader_role>; DROP ROLE sokhach_app; DROP ROLE sokhach_reader; DROP ROLE sokhach_owner;'
```

Gỡ đúng hai dòng peer và hai map thêm ở bước 3, so với bản sao cấu hình; không chép đè thay đổi
của người khác. Gỡ đúng unit đã tạo, không xóa thư mục release/backup.

```bash
sudo rm -- <systemd_unit_dir>/<unit>.service
```

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl reload <postgres_unit>
```

```bash
sudo -u postgres psql -X -At -v ON_ERROR_STOP=1 -h /var/run/postgresql -d postgres -c "SELECT count(*) FROM pg_database WHERE datname='<db_v7>'; SELECT count(*) FROM pg_roles WHERE rolname ~ '^(sokhach_|v7_)' OR rolname='<loader_role>';"
```

Hai count phải 0; kiểm config hết map/rule task, unit not-found, rồi chạy lại exact counts/diff bước 6.

### C — sự cố legacy (không được xảy ra)

Mục đích: kiểm khả năng phục hồi khi `webdebit_ledger` lệch baseline. Ai: admin DB + người dùng,
gate khẩn cấp riêng. Đạt: hash dump đúng, restore DB tạm khớp baseline và đã xóa DB tạm.
Dừng: mọi lỗi hash/restore/count; không tự ghi đè `webdebit_ledger` hay restore globals toàn cluster.
Thời gian: chưa đo, `rollback_C.seconds` chỉ restore thử.

```bash
sha256sum -c <evidence_dir>/backup.sha256
```

Lặp đầy đủ create/restore/count/diff/drop DB tạm bước 2. Giữ bản lệch và log trước khi phục hồi thật.
Việc thay DB đang phục vụ cần kế hoạch outage/backup hiện trạng/duyệt riêng, không tự động hóa ở runbook này.

Nếu người dùng chọn phục hồi thật mức C: dừng `<legacy_viewer_unit>`, bảo đảm không còn phiên DB,
lưu dump hiện trạng lệch trước; giữ DB lệch bằng đổi tên thay vì xóa. `<quarantine_db>` chưa tồn tại.
Các lệnh dưới đây chỉ cho sự cố này, **không chạy trong triển khai bình thường hoặc tổng duyệt**:

```bash
sudo systemctl stop <legacy_viewer_unit>
```

```bash
sudo -u postgres pg_dump -h /var/run/postgresql -U postgres -Fc webdebit_ledger > <backup_dir>/incident.dump
```

```bash
sudo -u postgres psql -X -At -h /var/run/postgresql -d postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname='webdebit_ledger';"
```

Count phải 0; không terminate phiên của người khác một cách tự động.

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d postgres -c 'ALTER DATABASE webdebit_ledger RENAME TO <quarantine_db>;'
```

```bash
sudo -u postgres createdb -h /var/run/postgresql webdebit_ledger
```

```bash
sudo -u postgres pg_restore -h /var/run/postgresql -U postgres --exit-on-error --single-transaction -d webdebit_ledger < <backup_dir>/ledger.dump
```

Admin khôi phục owner/ACL/thiết lập DB từ globals và hồ sơ bước 1 đã review, không nạp globals toàn cluster.
Chạy lại counts/diff bước 6, kiểm quyền kết nối viewer và kiểm chỉ đọc viewer trước mở dịch vụ.
Nếu restore lỗi, giữ cả DB mới lẫn DB cách ly, không đổi tên ngược khi chưa xử lý dependencies.

```bash
sudo systemctl start <legacy_viewer_unit>
```

```bash
sudo systemctl is-active <legacy_viewer_unit>
```

Chỉ start sau count/ACL/read đạt. Không xóa `<quarantine_db>` trong đợt xử lý.

## 8. Tổng duyệt, lệnh khung và điểm dừng

Chỉ tổng duyệt Docker với API loopback giả (không chứng minh Serve), template cũ giữ riêng:

```bash
python <release>/cong-no-web-handoff/tools/v7_reconcile_sheet.py --api http://127.0.0.1:<port> --sheet-dir <clean_dir> --out <new_outside_repo_dir> --brief
```

`rehearse_v7_deploy.py` dùng PostgreSQL 18.6 pin digest, volume có label/run-id, `--network none`,
không host mount/port publish. Chỉ xóa tài nguyên trùng ID/name/labels/volume; không chạm container có sẵn.
Giả lập legacy từ `pg_ledger_schema.sql` với vài dòng GIẢ; socket trong container; host API dùng
`PsqlDirect(psql_command=["docker","exec","-i",<container>,"psql"])` và dev actor loopback.
Không chứng minh peer/systemd/Tailscale. Mặc định tạo clean GIẢ, `--from-clean` chỉ đọc đường dẫn được cấp;
stdout/JSON không tên khách/tiền/đường dẫn nguồn. File đối soát chi tiết ở temp ngoài repo và được dọn.
Không chạy script này trong sandbox Codex; runner ngoài sandbox/CI chịu trách nhiệm Docker.

```bash
python cong-no-web-handoff/tools/rehearse_v7_deploy.py --list
```

```bash
python cong-no-web-handoff/tools/rehearse_v7_deploy.py --strict --report <outside_repo_report>.json
```

```bash
python cong-no-web-handoff/tools/rehearse_v7_deploy.py --from-clean <clean_dir> --strict --report <outside_repo_report>.json
```

| Thứ tự / mục đích | Kiểm / bằng chứng | Thời gian / dừng an toàn |
| --- | --- | --- |
| 0 Gate/revision/hash | CI đúng commit, hash git show | Chưa đo; trước ghi |
| 1 Preflight | version/socket/no TCP/disk/roles/exact counts | `preflight.seconds`, chưa chạy; trước backup |
| 2 Backup/restore thử | dump/globals/list/hash, restore counts | `backup_restore.seconds`, chưa chạy; trước provision |
| 3 Provision/check | schema/hàm/roles/CONNECT/checker | `provision.seconds`, chưa chạy; rollback B khi lỗi |
| 4 Plan/apply | manifest hash/count, empty target, active openings | `load.seconds`, chưa chạy; không retry mù |
| 5–6 Host API/GET/reconcile | `DOI SOAT: DAT`, legacy nguyên count | `api_reconcile.seconds`, chưa chạy; rollback A |
| Chỉ Docker: thu/hủy/cấn | một phiếu, hủy có lý do, một cấn trên khách đã nạp | `receipt_void_offset.seconds`, chưa chạy |
| 7B Rollback | DB/roles V7 hết, legacy counts khớp | `rollback_B.seconds`, chưa chạy |
| 7C Restore thử | hash + count backup, xóa DB tạm | `rollback_C.seconds`, chưa chạy |

Unittest so nguyên văn mọi template `COMMANDS` với tài liệu; template chuyển vào container bằng
`docker exec -i`, SQL file truyền stdin, dump binary truyền bytes. Các template không tự chạy:

```text
CREATE DATABASE <db_v7>;
```

```text
DROP DATABASE <db_v7>;
```

```text
pg_restore --list
```

```text
pg_restore -h /var/run/postgresql -U postgres --exit-on-error --single-transaction -d <restore_db>
```

```text
psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -f <release>/specs/v7-backend/schema-draft.sql
```

```text
psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -f <release>/cong-no-web-handoff/tools/v7_backend_functions.sql
```

```text
psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -U postgres -d <db_v7> -v db_v7=<db_v7> -v loader_role=<loader_role> -f <release>/cong-no-web-handoff/tools/v7_post_deploy_check.sql
```

CÒN MỞ: peer/pg_hba thật (container dùng trust); dung lượng thật và thời gian restore;
backup định kỳ V7 (người giữ, retention, phục hồi định kỳ); quyền người chạy, route Serve và kiểm
danh tính. Chính sách ai xem Lịch sử đã chốt V7-CSM, việc triển khai/quyền truy cập backup vẫn cần kiểm.
Đường Host/Origin/asset và allowlist HTTPS đối soát có regression test dữ liệu giả
(`test_v7_ledger_api.py`, `test_v7_reconcile_sheet.py`); không chứng minh Serve live.
CÒN MỞ: kiểm hai actor khác nhau cần hai tài khoản tailnet (hiện chỉ một); kiểm
systemd/Serve/GET/đối soát thực tế ở bước 5–6 sau deploy riêng. Tiến trình cục bộ trên
hao vẫn gọi được loopback và nằm trong ranh giới tin cậy Serve của V7-ID bản thử.
Gate V7-CSM chưa triển khai vẫn cần điều phối; không báo sẵn sàng production từ CI xanh.
