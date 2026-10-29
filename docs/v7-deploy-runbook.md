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

## Đối soát tổng khách cuối ngày — SONG-SONG-02

Người nhập chạy cuối ngày; chủ nghiệp vụ xem tổng kết cuối tuần/cuối tháng.
Dùng **bản xuất Sheet mới nhất** qua `v7_export_clean.py`, không dùng lại bản mốc
`clean-v2` để kết luận phát sinh sau mốc đã khớp. Công cụ chỉ đọc hai CSV
`clean_customers.csv` (`anchor_vnd`) và `clean_months.csv`; không tự xuất Sheet,
không nạp DB, không sửa Sheet hay web. Manifest của exporter có `format_version`;
đối soát đọc theo tên cột và ghi hash hai CSV, không xác minh toàn bộ manifest
hay khách bị loại/giữ ở khâu xuất. Phải xem báo cáo xuất riêng.

```text
python cong-no-web-handoff/tools/v7_reconcile_sheet.py --sheet-dir <latest_clean_dir> --ledger-json <ledger_json_dir> --out <new_outside_repo_dir> --totals-only --brief
```

Hoặc thay `--ledger-json <ledger_json_dir>` bằng
`--api https://<serve_fqdn>:<serve_port> --serve-host <serve_fqdn>:<serve_port>`.
Chỉ GET `/api/v7/customers` rồi `/api/v7/ledger?customer=<id>`; không ghi DB.
JSON offline là phản hồi ledger chưa bọc, tên file (bỏ `.json`) là tên khách.
Ghép tên chỉ chuẩn hóa khoảng trắng, không đoán/gộp khách gần giống.

Hợp đồng: `--totals-only` so tổng từng khách, bỏ qua khác biệt/ô trống ở bucket
tháng khi tổng đã rõ; cấu trúc đầu vào vẫn phải hợp lệ. Không đổi chế độ kiểm
tháng mặc định phục vụ nạp. `NO_BASELINE` hoặc tổng trống/NULL là `THIEU_SO`,
không đổi thành 0. Tổng lệch là `LECH_TONG`; thiếu một phía là `CHI_CO_SHEET`
hoặc `CHI_CO_WEB`; còn lại `KHOP`. Chênh lệch = web trừ Sheet, VND nguyên chính xác.
Mã thoát 0 = khớp, 1 = lệch/thiếu, 2 = lỗi đầu vào/đầu ra; lỗi không được coi là đạt.

`reconcile_customer.csv` ghi tên, tổng hai phía, chênh lệch và trạng thái;
`reconcile_index.csv` nối số thứ tự với tên; `summary.json` ghi đếm/hash và
`comparison_scope=customer_totals`; `reconcile_month.csv` chỉ có header trong
chế độ này. Thư mục kết quả bắt buộc mới và ngoài mọi repo. Console mặc định
im lặng; `--brief` chỉ in trạng thái/đếm/số thứ tự, không tên hay tiền.
Không đưa báo cáo thật vào Git. Không tự sửa lệch hay tạo lịch chạy.

Map kiểm: lệnh trên → `v7_reconcile_sheet.main/read_sheet/read_api/reconcile`
→ `tests/test_v7_reconcile_sheet.py` → `npm run check` (dữ liệu giả, không kiểm
Sheet/API/DB thật). GET nhiều lần không tạo snapshot đồng thời: chạy lúc hai
bên đã ngừng nhập, nếu còn thay đổi thì đối soát lại; chưa có bằng chứng snapshot
liên hệ thống hay kiểm thay đổi từng dòng sau mốc.

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

## Giao diện sửa/xóa tại ô — chỉ đổi release app (ĐÃ CHẠY trên hao 22/10/2026)

**Đã triển khai 22/10/2026** (commit `a72712b`, PR #71, CI xanh đúng SHA sau khi chạy lại job
`postgres-v7-grants-direct` lỗi hạ tầng "database system is starting up"). Chỉ đổi 4 file
`cong-no-web-handoff/preview/so-khach-v7-*` (giao diện nối 4 route NHAP-SHEET-01 đã có từ đợt trước);
không migration, không đổi API/SQL. Trình tự: backup `webdebit_v7` và restore thử vào DB mới
(số dư từng khách khớp); gói release mới từ `git archive` đúng commit, kiểm hash; diff với release
đang chạy chỉ có các file preview dự kiến; đổi đường dẫn release trong unit, `daemon-reload`, restart.
Đạt: service active chạy từ release mới, checker OK (236 khách, 877 kỳ), số dư 236/236 khách không đổi,
không có event/chuyến/phiếu mới, trang live tải giao diện mới. Không ghi thử trên sổ thật nên
**chưa kiểm** sửa/xóa qua giao diện với dữ liệu thật. Rollback: trả đường dẫn release cũ trong unit
(bản unit trước lưu ở thư mục evidence), `daemon-reload`, restart; DB không cần restore.

## Ghi giá từ Sheet — đổi release app và thêm runner bản chụp giá

Phạm vi: PR FinanceBullkk/webdebit#109, spec [`specs/v7-price-queue.md`](../specs/v7-price-queue.md). Soạn 27/10/2026.

**ĐÃ TRIỂN KHAI trên `hao` tối 27/10/2026.** Kiểm chỉ đọc lúc 11:41 ngày 28/10/2026 (giờ VN), bằng `systemctl`, `journalctl` và `ls` trên `hao`:
- Release V7 `current` trỏ tới `522556f` (commit merge #109), đổi lúc 23:54 ngày 27/10 (giờ VN). `v7-ledger-api.service` đang chạy.
- `webdebit-sheet-prices.timer` bật, `OnCalendar=*:0/15`, `RandomizedDelaySec=60`, `Persistent=true`: cùng nhịp 15 phút với `webdebit-sheet-sync.timer`. Runner chạy từ `current`, chỉ đọc Sheet qua Sheets API.
- `prices.json` mode 600, chủ `v7app`, cùng thư mục với `snapshot.json`; cập nhật mỗi lượt.
- Log runner: lúc cài có vài lượt lỗi và một lượt `row_count` 0, sau đó 40 lượt liên tiếp `"ok": true` từ 00:28 ngày 28/10 (giờ VN), mỗi lượt 10.358 dòng, khoảng 21 giây.
- Người dùng thấy trên sổ khách nút "Ghi N giá từ Sheet" và dòng vàng "giá Sheet / chưa tính" (ảnh chụp trong chat 28/10/2026).

**Chưa kiểm trong lần đối chiếu này:** bằng chứng P2 (backup), P4 (so bản chụp API với `.xlsx` cùng thời điểm) và lần ghi thật đầu tiên ở P5 không có trong repo; kiểm ở thư mục bằng chứng ngoài Git. Các bước dưới giữ làm hồ sơ và để làm lại khi cần.
- **Không migration, không đổi schema hay hàm SQL.** Ghi giá đi qua `edit_trip_price` và `edit_legacy_trip` đã có trên `hao`.
- Thêm route `GET /api/v7/ledger` → `sheet_prices` và `POST /api/v7/sheet/prices`.
- Thêm một runner chỉ đọc Sheet, ghi file `prices.json`.

Ai làm: admin trên `hao`; chủ nghiệp vụ cho phép từng mốc (P1–P5).

**Vì sao không dùng luồng tự triển khai:** diff có `cong-no-web-handoff/tools/v7_load_real_copy.py`. Bộ lọc của `deploy-hao.yml` gặp `tools/v7_load*` thì **dừng** ([hao-auto-deploy](hao-auto-deploy.md#phạm-vi-và-những-gì-bị-chặn)), nên làm tay như mục "Giao diện sửa/xóa tại ô". Thay đổi trong loader chỉ tách `scan_tabs` khỏi `scan_workbook`, hành vi giữ nguyên: test nạp thật vẫn xanh. Không chạy lại nạp mốc.

**Thứ tự với PR #107:** hai PR ghép không xung đột (kiểm 27/10 bằng `git merge-tree`). #107 có migration `2026-10-27-v7-sheet-conflict-date-booking.sql`, nên đi theo trình tự nâng DB (backup, chạy trên bản sao, rồi DB thật). Nếu triển khai cùng đợt thì chạy #107 trước, rồi đổi release lên SHA `main` chứa cả hai.

### P1. Gate trước khi đụng `hao`

- #109 đã merge; `Tests` xanh trên đúng SHA `main` sẽ triển khai.
- Đã có quyết định chủ nghiệp vụ cho mở đường ghi mới (nút "Ghi N giá").
- Ghi SHA, giờ bắt đầu và người chạy vào thư mục bằng chứng `<evidence_dir>` (ngoài Git).

### P2. Backup trước, dù release không đổi DB

Lý do: từ lúc nút xuất hiện, người dùng có thể ghi giá thật. Dùng đúng lệnh backup và restore thử ở [mục 2](#2-backup-toàn-phần-trước-mọi-ghi-dbcấu-hình). Đạt khi số dư 236 khách của bản restore khớp bản đang chạy.

### P3. Đổi release app

Như mục "Giao diện sửa/xóa tại ô":
1. Gói `git archive <sha>`, kiểm hash.
2. Diff với release đang chạy chỉ được có các file dưới đây. Có file khác thì **dừng**.
   - `cong-no-web-handoff/web/v7_ledger_api.py`, `web/v7_price_queue.py`
   - `cong-no-web-handoff/preview/so-khach-v7-{ui,model}.js`, `so-khach-v7-live.html`
   - `cong-no-web-handoff/tools/v7_{price_match,price_snapshot,sheets_api_reader,load_real_copy}.py`
   - test, spec, mockup
3. Đặt symlink `CURRENT_LINK` sang release mới, ghi `.release-sha` = SHA.
4. `sudo systemctl restart <unit>`.

Chưa có `prices.json` thì sổ vẫn đọc bình thường: `sheet_prices.unavailable = true`, không hiện nút.

Kiểm chỉ đọc qua URL Serve, **không bấm ghi**:
- `GET /api/v7/customers` trả 200.
- `GET /api/v7/ledger?customer=<id>` có khóa `sheet_prices` với `unavailable: true`.
- Checker sau triển khai OK; số dư từng khách không đổi so với P2.

### P4. Runner bản chụp giá

Chạy cùng OS user, cùng file biến môi trường và cùng tài khoản dịch vụ với runner đồng bộ chuyến hiện có (`sheet_sync_runner.py`, chỉ `spreadsheets.readonly`). Không xin thêm quyền Google.

File do runner ghi có mode 600, nên API phải đọc được bằng chính user đó. Dùng đúng cách đã làm cho `snapshot.json`: cùng thư mục `/var/lib/webdebit-sheet-sync/`.

| Biến | Giá trị | Ghi chú |
| --- | --- | --- |
| `WEBDEBIT_SHEET_ID` | ID Sheet sổ chính | đã có trong env của runner đồng bộ; không ghi vào repo |
| `WEBDEBIT_GOOGLE_CREDENTIALS` | đường dẫn JSON tài khoản dịch vụ | đã có; mode 600 |
| `WEBDEBIT_PRICE_SNAPSHOT_PATH` | `/var/lib/webdebit-sheet-sync/prices.json` | runner và API cùng mặc định này; chỉ đặt nếu đổi chỗ, khi đó đặt ở **cả hai** unit |

Mẫu `webdebit-sheet-prices.service`:

```ini
[Unit]
Description=V7 Sheet price snapshot (read-only Sheets API)
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=oneshot
User=<os_user_sheet_sync>
EnvironmentFile=<env_file_sheet_sync>
WorkingDirectory=<current_link>
ExecStart=<python> <current_link>/cong-no-web-handoff/tools/v7_price_snapshot.py --output /var/lib/webdebit-sheet-sync/prices.json
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/webdebit-sheet-sync
TimeoutStartSec=300
```

Mẫu `webdebit-sheet-prices.timer`:

```ini
[Unit]
Description=V7 Sheet price snapshot schedule

[Timer]
OnCalendar=*:0/15
RandomizedDelaySec=60
Persistent=true

[Install]
WantedBy=timers.target
```

- Nhịp chạy lấy theo timer đồng bộ chuyến hiện có (15 phút trên `hao`), để giá và chuyến cùng độ mới. Giá gõ trên Sheet hiện lên web chậm nhất khoảng 15 phút cộng thời gian chạy, sau khi tải lại sổ; không phải thời gian thực. Mỗi lượt khoảng 11 yêu cầu Sheets API (1 lấy danh sách tab, 25 tab mỗi `batchGet`), không chạm hạn mức.
- Ghi file nguyên tử: người đọc không thấy file dở.
- `ProtectHome=true`: nếu file JSON tài khoản dịch vụ nằm trong `/home` thì làm như unit đồng bộ chuyến (cùng tùy chọn bảo vệ), không nới riêng unit này.

Chạy lần đầu **bằng tay**, chưa bật timer:

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl start webdebit-sheet-prices.service
```

```bash
sudo journalctl -u webdebit-sheet-prices.service -n 20 --no-pager
```

Đạt khi:
- Log có `{"ok": true, "row_count": N, "sha256": …}`, với N cùng cỡ bản tải gần nhất (27/10: 10.358).
- `prices.json` mode 600, chủ là user runner.
- Log không có tên khách hay số tiền.

Có `"ok": false` thì **dừng**, đọc `reason`:
- `HTTPError` hoặc `URLError`: quyền chia sẻ Sheet hoặc mạng.
- `ValueError`: phản hồi khác dạng mong đợi.

**So với bản tải `.xlsx` cùng thời điểm** (lần đầu là bước bắt buộc). Hai đường đã được kiểm tương đương bằng dữ liệu mô phỏng, chưa kiểm bằng Sheets API thật:
1. Tải `.xlsx` ngay sau khi runner chạy.
2. Tạo bản chụp ra thư mục tạm ngoài repo: `v7_price_snapshot.py --xlsx <file> --output <tmp>/prices-xlsx.json`.
3. So hai bản bằng lệnh dưới. Lệnh chỉ in số đếm, không in tên hay tiền.

```bash
<python> -c "import json,sys; a,b=(json.load(open(p, encoding='utf-8')) for p in sys.argv[1:]); k=lambda r:(r['customer_tab'],r['source_row']); A={k(r):r for r in a['rows']}; B={k(r):r for r in b['rows']}; f=('sheet_unit_price_vnd','sheet_other_fee_vnd','sheet_total_vnd','date'); print(len(A),len(B),len(A.keys()^B.keys()),sum(1 for x in A.keys()&B.keys() if any(A[x][g]!=B[x][g] for g in f)))" /var/lib/webdebit-sheet-sync/prices.json <tmp>/prices-xlsx.json
```

Đạt khi in ra `N N 0 0`: cùng số dòng, không lệch khóa, không lệch giá, phụ phí, tổng hay ngày. Ô container có thể khác ở dòng gõ số (đã gặp `4.2E7` và `42000000`); lệnh không so container. Lệch thì **dừng**, giữ timer tắt, báo Claude kèm 4 con số.

Đạt rồi mới bật timer:

```bash
sudo systemctl enable --now webdebit-sheet-prices.timer
```

### P5. Kiểm sau khi có bản chụp, vẫn không ghi

- `GET /api/v7/ledger?customer=<id>` của một khách có giá chờ: `sheet_prices.ready_count` lớn hơn 0, `snapshot_sha256` khớp log.
- Số lần đo 27/10 để đối chiếu: 36 dòng ghi được ở 3 khách; "Cần xem" 43 dòng ở 10 khách. Số thật đổi theo Sheet.
- Mở sổ khách đó trên máy người dùng (1280×720): có nút "Ghi N giá từ Sheet", dòng vàng có "giá Sheet / chưa tính", tổng còn nợ **không đổi**.
- Số dư từng khách vẫn bằng P2; không có event mới.

**Lần ghi thật đầu tiên:**
- Do người nhập bấm, chủ nghiệp vụ chứng kiến, chọn khách ít dòng.
- Sau đó kiểm:
  - Lịch sử có một dòng sửa giá cho mỗi chuyến, ghi đúng tên người bấm.
  - Tổng còn nợ tăng đúng số trong khung xác nhận.
  - Đối soát tổng khách của khách đó không lệch thêm.

### Rollback

- **Runner:**
  - `sudo systemctl disable --now webdebit-sheet-prices.timer`.
  - Đổi tên `prices.json` thành `prices.json.disabled` (giữ làm bằng chứng). API tự về `unavailable`, nút biến mất.
- **App:** trỏ `CURRENT_LINK` về release trước (giữ 5 bản), restart unit. DB không cần restore.
- **Giá đã ghi sai:** sửa lại bằng chính ô giá trên sổ; mọi lần sửa có Lịch sử. Chỉ restore backup P2 khi ghi sai hàng loạt và chủ nghiệp vụ quyết định; sau restore phải đối soát lại.

### Còn mở sau triển khai

- Nút "Giữ web" cho dòng lệch giá chưa có.
- Ghi nguồn tab/dòng Sheet vào Lịch sử chưa có.
- Số đếm ở trang Tổng quan chưa có.
- Harness PostgreSQL cho lệnh ghi lô chưa có: lệnh ghi lô chỉ gọi hai hàm SQL đã có test.

## Nút "Làm mới" đọc Sheet ngay — cài unit `.path` (ĐÃ CHẠY trên hao 28/10/2026)

Phạm vi: spec [`specs/v7-sheet-refresh.md`](../specs/v7-sheet-refresh.md). Không migration, không đổi DB, không thêm quyền đọc Sheet.

**Đã chạy 28/10/2026** (người dùng cho phép trong chat): cài R1–R2 lúc 12:41 (giờ VN), release `5e0b184` lên lúc 12:54. Bấm thật lúc 12:56 trên sổ khách: chữ "Đang lấy từ Sheet…" rồi "Sheet vừa lấy lúc 12:56"; log có lượt ngoài lịch, chuyến 12 giây rồi giá 25 giây, `"ok": true`; file tín hiệu ghi đúng người bấm; dữ liệu `/api/v7/dashboard` trước và sau giống hệt. Trạng thái unit trước khi sửa lưu ở thư mục bằng chứng ngoài Git.

**Lỗi gặp khi triển khai:** `v7-ledger-api.service` chạy với `ProtectSystem=strict`, nên lần bấm đầu API trả 503 `SHEET_REFRESH_UNAVAILABLE` (không ghi được file tín hiệu). Đã sửa bằng `ReadWritePaths` cho đúng một file ở R2. File tín hiệu phải có sẵn trước khi khởi động API (systemd bind đúng file đó).

**Đổi release:** code chỉ nằm trong `cong-no-web-handoff/{web,preview}`, nên luồng [tự triển khai](hao-auto-deploy.md) đưa lên sau khi merge. Chưa đặt biến môi trường thì API trả `unavailable`, nút "Làm mới" giữ cách cũ. Các bước dưới cần người dùng cho phép riêng.

### R1. Unit nhận tín hiệu

`/etc/systemd/system/webdebit-sheet-refresh.path`:

```ini
[Unit]
Description=V7 manual Sheet refresh signal

[Path]
PathChanged=/var/lib/webdebit-sheet-sync/refresh.request
Unit=webdebit-sheet-refresh.service

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/webdebit-sheet-refresh.service`:

```ini
[Unit]
Description=V7 manual Sheet refresh (starts the two read-only runners)
Wants=webdebit-sheet-sync.service webdebit-sheet-prices.service

[Service]
Type=oneshot
ExecStart=/bin/true
```

Hai runner chạy song song, không đặt thứ tự: hàng chờ giá ghép với sổ web trong DB, không đọc bản chụp chuyến. (Bản đầu có drop-in `webdebit-sheet-prices.service.d/after-sync.conf` với `After=webdebit-sheet-sync.service`; bỏ ngày 28/10/2026 để nút nhanh hơn. Gỡ: xóa file đó rồi `sudo systemctl daemon-reload`.)

- `PathChanged` bắt sự kiện đóng file sau khi ghi; API ghi thẳng, không đổi tên file.
- Hai runner giữ nguyên unit, user `v7app`, quyền chỉ đọc. Đang chạy thì systemd gộp yêu cầu vào lượt đang chạy.

### R2. Bật cho API

Drop-in cho `v7-ledger-api.service` (cùng thư mục với `customer-name-mapping.conf`):

```ini
[Service]
Environment=WEBDEBIT_SHEET_REFRESH_PATH=/var/lib/webdebit-sheet-sync/refresh.request
# ProtectSystem=strict: chỉ mở ghi đúng file tín hiệu, không mở cả thư mục bản chụp.
ReadWritePaths=/var/lib/webdebit-sheet-sync/refresh.request
```

API chạy bằng `v7app`. Tạo sẵn file tín hiệu (chủ `v7app`) trước khi restart API, ví dụ `sudo -u v7app touch /var/lib/webdebit-sheet-sync/refresh.request`; lệnh này cũng làm runner chạy một lượt. Sau đó:

```bash
sudo systemctl daemon-reload
```

```bash
sudo systemctl enable --now webdebit-sheet-refresh.path
```

```bash
sudo systemctl restart v7-ledger-api.service
```

### R3. Kiểm

- `GET /api/v7/sheet/refresh` trả `state: idle` và `sheet_at` bằng giờ lượt 15 phút gần nhất.
- Bấm "↻ Làm mới" trên sổ khách: chữ đổi "Đang lấy từ Sheet…"; `journalctl -u webdebit-sheet-sync.service -u webdebit-sheet-prices.service` có một lượt ngoài phút 00/15/30/45, hai runner bắt đầu cùng lúc; xong cả hai thì chữ đổi "Sheet vừa lấy lúc …". Bấm lại ngay sau đó phải chạy được lượt mới.
- Số dư từng khách không đổi, không có event mới (nút không ghi sổ).

### Rollback

- `sudo systemctl disable --now webdebit-sheet-refresh.path`, xóa drop-in của API rồi `daemon-reload` và restart API: nút về cách cũ. Lịch 15 phút không bị ảnh hưởng.

## Tách phụ phí theo bảng PS — migration + runner bản chụp (migration ĐÃ CHẠY trên hao 29/10/2026; runner chưa cài)

Spec [`v7-phu-phi-tu-ps`](../specs/v7-phu-phi-tu-ps.md). Migration `cong-no-web-handoff/tools/migrations/2026-10-29-v7-ps-fee.sql`
chỉ thêm loại event `rewrite_trip_fees` và hai hàm (`rewrite_trip_fees` cho app, `_rewrite_trip_fees` không ai được EXECUTE);
không đổi hàm cũ, tiền, phân bổ hay dữ liệu. Chạy lại được. **Thứ tự bắt buộc: `2026-10-29-v7-chung-tu.sql` →
`2026-10-29-v7-xoa-dieu-chinh-thang.sql` (mục [Xóa điều chỉnh cả tháng](#xóa-điều-chỉnh-cả-tháng--nâng-db-đang-có-đã-chạy-trên-hao-29102026)) →
`2026-10-29-v7-ps-fee.sql`.** Migration PS dựng lại `event_kind_check`/`event_snapshot_check` gồm mọi loại tới nay, cả
`adjust_month_delete` lẫn `rewrite_trip_fees`; chạy lại một migration cũ hơn sau nó sẽ làm mất loại `rewrite_trip_fees` (và
ngược lại). Auto-deploy dừng ở gate SQL; chỉ chạy khi người dùng cho phép.

0. **Quyền đọc bộ lập bill (CHỈ ĐỌC):** dưới user runner chạy một lần
   `v7_ps_snapshot.py --output /tmp/ps-thu.json`. `ok: true` là tài khoản dịch vụ đọc được `CONT_MASTER`; lỗi `HTTPError`
   (403/404) nghĩa là `WEBDEBIT_SHEET_ID` trỏ file khác: đặt `WEBDEBIT_PS_SHEET_ID` = ID file bộ lập bill trong env runner
   (không ghi vào repo) và người dùng chia sẻ file đó (chỉ xem) cho email tài khoản dịch vụ. Xóa `/tmp/ps-thu.json` sau khi xem số dòng.
1. **Bản sao trước:** dump `webdebit_v7`, restore vào DB thử, chạy migration hai lượt; số dư từng khách/tháng và số dòng mọi
   bảng cũ không đổi; `v7_post_deploy_check.sql` OK (app thêm `rewrite_trip_fees`; `_rewrite_trip_fees` không được EXECUTE).
2. **Cửa sổ dừng ghi:** như các đợt trước (dừng API, dump + hash, chạy migration một transaction, kiểm số dư, đổi release).
3. **Runner:** `webdebit-ps-snapshot.service` giống mẫu `webdebit-sheet-prices.service` ở P4 (cùng user, `EnvironmentFile`,
   `ReadWritePaths`), `ExecStart=<python> <current_link>/cong-no-web-handoff/tools/v7_ps_snapshot.py --output /var/lib/webdebit-sheet-sync/ps.json`;
   `.timer` 15 phút như runner giá. Thêm `Wants=webdebit-ps-snapshot.service` vào `webdebit-sheet-refresh.service` để nút
   "↻ Làm mới" đọc luôn bảng PS. API đọc `WEBDEBIT_PS_SNAPSHOT_PATH` (mặc định đúng đường dẫn trên). Mỗi lượt 1 yêu cầu Sheets API.
4. **Kiểm sau (chỉ đọc):** `GET /api/v7/ledger?customer=<id>` có khóa `ps_fees` (không còn `unavailable`); ghi số `ready`/`review`
   theo vài khách vào nhật ký. Không bấm tách thật khi chưa có giao diện (PR-2) và lệnh người dùng.

Rollback: tắt timer runner (sổ trả `ps_fees.unavailable`, không ảnh hưởng chức năng khác). Hàm mới không đổi dữ liệu nên để
nguyên được; cần gỡ hẳn thì restore dump trước nâng. Các lần tách đã ghi giữ tổng tiền; muốn bỏ thì đổi loại trong khung chi tiết.

## Xóa điều chỉnh cả tháng — nâng DB đang có (ĐÃ CHẠY trên hao 29/10/2026)

Migration `cong-no-web-handoff/tools/migrations/2026-10-29-v7-xoa-dieu-chinh-thang.sql` ([`XOA-DC-THANG-01`](decisions.md#xoa-dc-thang-01)).
Thêm cột `sokhach.adjustment.reverses_adjustment_id` (NULL với mọi dòng cũ), loại event `adjust_month_delete`, hàm
`delete_month_adjustment`, và thay view `v_adjustment_current` để ẩn cặp gốc + đảo. Không đổi dữ liệu có sẵn; chưa có
dòng đảo nào thì view trả đúng như cũ, số dư không đổi. Chạy lại được. **Chạy sau `2026-10-29-v7-chung-tu.sql`** (dựng lại
`event_kind_check`/`event_snapshot_check` gồm loại event ảnh). Auto-deploy dừng ở gate SQL; chỉ chạy khi người dùng cho phép.

1. **Bản sao trước:** dump `webdebit_v7`, restore vào DB thử, chạy migration hai lượt; số dư từng khách/tháng và số dòng
   `v_adjustment_current` không đổi; `v7_post_deploy_check.sql` OK (app thêm `delete_month_adjustment`).
2. **Cửa sổ dừng ghi:** như các đợt trước (dừng API, dump + hash, chạy migration một transaction, kiểm số dư, đổi release).

Rollback: chưa có lệnh xóa nào thì trỏ release về bản trước là đủ (cột mới để trống, view cho kết quả như cũ); đã có
dòng đảo thì giữ DB (cặp vẫn tổng 0) hoặc restore dump trước nâng.

## Ảnh chứng từ phiếu thu — nâng DB đang có (CHƯA CHẠY)

Migration `cong-no-web-handoff/tools/migrations/2026-10-29-v7-chung-tu.sql` ([`CHUNG-TU-01`](decisions.md#chung-tu-01),
spec [`v7-dan-chung-tu`](../specs/v7-dan-chung-tu.md)). Chỉ thêm bảng `sokhach.receipt_image`, hai loại event và bảy hàm;
không đổi hàm cũ, tiền, phân bổ hay dữ liệu có sẵn. Chạy lại được. **Chạy sau PR-B và PR-B P2** (migration này dựng lại
`event_kind_check`/`event_snapshot_check` gồm cả loại event phụ phí; chạy PR-B sau nó sẽ làm mất hai loại event ảnh).
Auto-deploy dừng ở gate SQL; chỉ chạy khi người dùng cho phép.

1. **Bản sao trước:** dump `webdebit_v7`, restore vào DB thử, chạy migration hai lượt; số dư từng khách/tháng và số dòng
   mọi bảng cũ không đổi; `v7_post_deploy_check.sql` OK (app thêm `attach_receipt_image`, `remove_receipt_image`;
   app và reader thêm `list_receipt_images`, `get_receipt_image`, `find_receipt_image`; hai helper không được EXECUTE).
2. **Cửa sổ dừng ghi:** như các đợt trước (dừng API, dump + hash, chạy migration một transaction, kiểm số dư, đổi release).
3. **Dung lượng:** ảnh lưu `bytea` ngay trong DB nên `v7_backup.py` sao lưu luôn ảnh. Ước tính 10–30 ảnh/ngày, mỗi ảnh
   tối đa 2 MB (thường 200–500 KB): khoảng 1–5 GB/năm. Kiểm chỗ trống đĩa và thời gian dump trước khi bật.

Rollback: `2026-10-29-v7-chung-tu.rollback.sql` chỉ chạy khi chưa có ảnh hay event ảnh nào (có thì dừng
`RECEIPT_IMAGES_PRESENT`, không xóa chứng từ); đã có ảnh thì tắt giao diện là đủ, hoặc restore dump trước nâng.

## Đã thu theo ngày thu — nâng DB đang có (ĐÃ CHẠY trên hao 28/10/2026)

Migration `cong-no-web-handoff/tools/migrations/2026-10-28-v7-da-thu-theo-ngay-thu.sql` (PR #125, [`DA-THU-01`](decisions.md#da-thu-01)),
chỉ thay hàm đọc `get_ledger`, chạy sau hai migration phụ phí và xóa khoản thu sổ gốc. Auto-deploy dừng ở gate SQL như
thiết kế; người dùng cho chạy tay 28/10/2026 ("Chạy triển khai thật"). Trình tự như đợt phụ phí:

1. **Bản sao trước:** dump `webdebit_v7` đang chạy, restore vào DB thử (thu hồi CONNECT của PUBLIC), chạy migration hai lượt;
   số dư 236/236 khách không đổi; 0/236 sổ lệch đẳng thức `nợ tháng trước + phát sinh − đã thu = cộng dồn` và
   tháng cuối = tổng còn nợ; checker 9/9 OK trước và sau migration; xóa DB thử.
2. **Cửa sổ dừng ghi** (API dừng khoảng 12 giây): dừng `v7-ledger-api.service`, dump + hash, restore thử khớp số dư và số dòng,
   chạy migration (một transaction), kiểm số dư/số dòng không đổi và đẳng thức từng sổ, rồi `webdebit-release.sh deploy c407664`.
3. **Kết quả:** release `c407664`, service active, cổng loopback 403 (sống); số dư không đổi sau release; checker 9/9 OK.
   Script, dump và log ở thư mục evidence/backup ngày 28/10 (`-da-thu`) trên `hao`, ngoài Git.

Rollback: áp lại `get_ledger` của `2026-10-28-v7-phu-phi-core-a.sql` (hàm đọc, không đụng dữ liệu) và trỏ release về `b846240`;
hoặc restore dump trước nâng vào DB mới theo quy trình M2-11. CÒN MỞ: chưa thử tay trên web sau nâng.

## Phụ phí PR-A — nâng DB đang có (ĐÃ CHẠY trên hao 28/10/2026)

Migration `cong-no-web-handoff/tools/migrations/2026-10-28-v7-phu-phi-core-a.sql` (PR #117), spec
[`specs/v7-phu-phi-backend.md`](../specs/v7-phu-phi-backend.md). Auto-deploy dừng ở gate SQL như thiết kế;
người dùng cho chạy tay 28/10/2026 ("ok xử lý đi"), Claude chạy theo trình tự các đợt trước.

1. **Bản sao trước:** dump `webdebit_v7` đang chạy, restore vào DB thử (thu hồi CONNECT của PUBLIC), chạy migration
   hai lượt (~18 s, ~15 s): số dư từng khách không đổi, lượt hai không đổi số dòng, dry-run sau là `0|0`.
2. **Cửa sổ dừng ghi** (API tắt 23 giây): dừng `v7-ledger-api.service`, dump + hash, restore thử khớp số dư và số dòng
   với DB thật, chạy migration (một transaction, tự đối chiếu `v_outstanding_month` và `get_ledger` từng khách/tháng),
   rồi đổi release app bằng `webdebit-release.sh deploy <sha>` (chạy dưới user deploy; script tự restart và kiểm sống).
3. **Kết quả:** số dư 236/236 khách không đổi sau migration và sau đổi release; 122 event `fee_migration`;
   2117 dòng phí sổ gốc chỉ để xem, 0 dòng phí chuyến web; checker 9/9 OK. Bằng chứng, dump và báo cáo ID ở thư mục
   evidence/backup ngày 28/10 trên `hao`, ngoài Git.
4. **Checker:** bản trên `main` lúc đó báo nhầm `legacy counted amount mismatch` cho dòng thu sổ gốc đã xóa
   (điều chỉnh của dòng thu đảo dấu theo XOA-THU-GOC-01; nợ khách đúng, chỉ phép kiểm thiếu dấu). Lỗi có trước migration.
   Đợt này dùng bản checker đã vá dấu; bản vá vào `main` cùng PR ghi mục này.

Rollback: file `.rollback.sql` cùng tên (một transaction, kiểm tổng; dừng nếu dòng phí đã phân loại hoặc giá đã sửa sau
migration), hoặc restore dump trước nâng vào DB mới theo quy trình M2-11. Release cũ còn trong `RELEASES_DIR`.
CÒN MỞ: giao diện phụ phí (PR-B) chưa có; chưa thử tay trên web sau nâng.

## Kết luận CHỜ KIỂM — nâng DB đang có (ĐÃ CHẠY trên hao 22/10/2026)

Chạy `cong-no-web-handoff/tools/migrations/2026-10-22-v7-trip-review.sql` sau migration CSM,
theo đúng trình tự đợt nâng 22/10: backup và restore thử, chạy trên bản sao, rồi DB thật khi
người dùng xác nhận; nâng service API lên cùng commit (route `/api/v7/trips/review`). Đạt:
checker sau triển khai OK (danh sách hàm có `review_trip`), số dư từng khách không đổi,
`DOI SOAT: DAT`. Migration không đổi dòng tiền; chuyến đang CHỜ KIỂM giữ nguyên trạng thái.
Rollback: restore backup trước nâng. Spec: [`specs/v7-trip-review.md`](../specs/v7-trip-review.md).

## M2-11 — nâng DB đang có (phần B, đã chạy trên hao trước đợt nâng 22/10/2026)

Người dùng cho phép chuẩn bị; Claude review, người dùng merge, Claude triển khai sau gate riêng.
Bước này nâng `webdebit_v7` đã có schema, không chạy lại schema-draft và không đụng `webdebit_ledger`.
Chuẩn bị release mới từ commit được duyệt, gồm migration cùng toàn bộ tools; giữ release cũ và backup.
Giá trị 236 khách / 877 kỳ / 10.165 chuyến là mốc người dùng cung cấp ngày 21/10, không phải kết quả task này.

1. Dừng service V7 và chặn mọi writer/loader khác suốt backup → migration → nạp → kiểm. Nếu chưa dừng được, DỪNG.
2. Backup **webdebit_v7**, hash và restore thử vào DB mới. Dừng khi backup/restore/count khác nhau.
3. Lưu số dư từng khách trước; chạy migration trên bản sao trước rồi trên DB đích theo gate. Migration dùng một transaction, lock khách, tự đối chiếu tổng từng khách và đủ 14 hàm app. Chạy lại cùng migration không đổi kết quả.
4. PLAN kiểm đủ ba CSV với manifest; chỉ dùng đúng clean-v2 đã nạp. APPLY chạy OS user/role `v7_loader`; cutover_id và SHA manifest phải khớp DB active. Chuyến không có container (thường là phí lẻ) không thể so trùng theo container nên không có dòng tham chiếu: loader đếm và in `skipped_no_container`, PLAN kiểm `trips + skipped_no_container` = manifest, APPLY kiểm số dòng legacy khớp cả hai phần; không bỏ âm thầm (người dùng đồng ý 21/10/2026 sau khi bản mốc có 230 chuyến như vậy; các chuyến này không được chặn dán trùng). Ngày chưa rõ giữ NULL, không đoán.
5. So số dư từng khách trước/sau, checker và reconcile; chỉ restart khi tất cả đạt. Dán thử chuyến mốc/chuyến mới chỉ trên DB bản sao, không trên sổ thật.

Lệnh khung Linux, thay placeholder theo quy ước ở đầu tài liệu, chạy từ gốc release mới:

```bash
sudo systemctl stop <unit>.service
sudo -u postgres pg_dump -h /var/run/postgresql -Fc webdebit_v7 > <backup_dir>/v7-before-m211.dump
sha256sum <backup_dir>/v7-before-m211.dump > <evidence_dir>/v7-before-m211.sha256
sudo -u postgres createdb -h /var/run/postgresql <restore_db>
sudo -u postgres pg_restore -h /var/run/postgresql --exit-on-error --single-transaction -d <restore_db> < <backup_dir>/v7-before-m211.dump
```

Lưu cùng truy vấn trước và sau; tệp nằm ngoài repo, quyền 600. Dùng LEFT JOIN để giữ khách chưa có số dư, NULL không đổi thành 0:

```sql
SELECT c.id, v.total FROM sokhach.customer c LEFT JOIN
 (SELECT customer_id,sum(outstanding_vnd)::text total FROM sokhach.v_outstanding_month GROUP BY customer_id) v
 ON v.customer_id=c.id ORDER BY c.id;
```

```bash
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d webdebit_v7 -f specs/v7-backend/migrations/001-m2-11-dedup.sql
sudo -u <loader_os_user> python3 cong-no-web-handoff/tools/v7_load_baseline_refs.py <clean_dir> --database webdebit_v7 --cutover-id <active_cutover_id>
sudo -u <loader_os_user> python3 cong-no-web-handoff/tools/v7_load_baseline_refs.py <clean_dir> --database webdebit_v7 --cutover-id <active_cutover_id> --apply
sudo -u postgres psql -X -v ON_ERROR_STOP=1 -h /var/run/postgresql -d webdebit_v7 -v db_v7=webdebit_v7 -v loader_role=v7_loader -v expect_customers=236 -v expect_openings=877 -f cong-no-web-handoff/tools/v7_post_deploy_check.sql
diff -u <evidence_dir>/v7-before.balances <evidence_dir>/v7-after.balances
```

Đạt: PLAN trips + skipped_no_container khớp manifest (mốc cung cấp: 10.165), số tham chiếu khớp multiset legacy cùng cutover, retry không nhân dòng; checker xanh, số dư từng khách không đổi, reconcile với clean-v2 đạt. DB thử phải chứng minh dán mốc `pending_review`, chuyến mới `confirmed`, chuyến chờ ngoài tiền và không sửa được. Không lấy test giả thay cho kết quả 236 khách thật. API hiện không nhận trường booking; đường hiện tại dùng ALT-KEY-01. Không đổi API/UI trong M2-11.

Dừng: thiếu hash/bản mốc, container rỗng, khác cutover, khác số dòng, thiếu quyền, SQL lỗi, số dư lệch, checker/reconcile lỗi hoặc chưa có backup phục hồi thử. Giữ service dừng; không chạy tiếp để né lỗi. Migration lỗi tự rollback transaction; loader lỗi rollback toàn bộ lô.

Rollback sau migration đã commit: giữ dump sự cố và DB nâng lỗi để điều tra; giữ service dừng, restore `v7-before-m211.dump` vào DB mới, đối chiếu counts/số dư/checker cũ. Sau gate phục hồi, chuyển cấu hình service sang DB phục hồi và release cũ, rồi mới start. Không drop/ghi đè DB nâng lỗi, không chạy SQL “down” xóa cột khi đã có chuyến pending. Giữ cả hai DB tới khi người dùng chốt phục hồi.

Kiểm bản sao (chạy qua orchestrator, dữ liệu giả, Docker `--network none`):

```text
py -3.13 cong-no-web-handoff/tools/test_pg_v7_backend.py --migration-test --report <outside_repo_report>.json
```

Harness cần đối tượng Git `460882d9d5d60c3fc8eeac5161a0058219dc09d4` để dựng đúng schema/hàm CŨ; thiếu đối tượng thì dừng, không thay bằng schema mới. So catalog hàm/cột/view với khởi tạo mới; checker 14 quyền; migration chạy hai lần; loader dùng role thật trên DB giả. Peer/systemd/hao và số dư thật còn gate triển khai.
# PR-B phụ phí nhiều loại — runbook kiểm chứng (chưa triển khai)

ĐÃ CODE: migration `2026-10-29-v7-phu-phi-b.sql`, hàm/API PR-B, danh mục và cột phí.
ĐÃ KIỂM CHỨNG cục bộ: `npm run check`, unit/API, SQL copy và `check-secrets`; PostgreSQL 18.6 dùng một lần: 10 ca schema + 53 ca hành vi đạt, 0 lỗi. Hai mục `SKIPPED_OPEN` có sẵn (7.11c, 7.15c) vẫn chưa được chứng minh; `--strict` toàn bộ trả 1 vì hai mục này. Harness chạy qua `codex-check-loop.ps1`; lệnh CI backend dùng chế độ mặc định.
CHƯA TRIỂN KHAI: không chạy `hao`/DB thật. Trước gate deploy, chạy harness backend hai lượt theo lệnh CI, harness quyền `test_pg_v7_grants.py --strict`, kiểm snapshot tổng từng khách/tháng, review diff cuối trước khi mở PR.
Quyết định bổ sung 29/10/2026: dòng sổ gốc thiếu đơn giá bị chặn với `LEGACY_NO_UNIT_PRICE` khi add/set/replace/void hoặc sửa tổng phí cũ; bổ sung đơn giá trước, giữ nguyên TOTAL, opening và adjustment khi bị từ chối. Xóa chuyến/dòng sổ gốc chụp đầy đủ `fee_lines` trong event. Người dùng đã bỏ gate opus; vẫn giữ gate kiểm cục bộ và CI.
Thứ tự nâng: PR-A (gồm chuyển dữ liệu) trước PR-B, rồi `2026-10-29-v7-phu-phi-b-p2.sql` (chỉ thay `_change_trip_fees` và `get_ledger`: mã `FEE_LINE_NOT_FOUND`, cờ `counted_differs`; không đổi dữ liệu, chạy lại được); không chạy lại phần tạo dòng Phụ phí ban đầu của PR-A sau khi đã nạp trigger PR-B. Loại phí ngừng dùng vẫn giữ cột sổ đã chọn và lịch sử; chỉ chặn chọn mới, không tự dọn cấu hình sổ.
Phục hồi: PR-B và PR-B P2 **không có** file `.rollback.sql` như PR-A. Lỗi trong transaction thì tự rollback; nếu đã commit mà cần quay lại, restore dump chụp ngay trước khi nâng vào DB mới (như mục rollback M2-11), không viết SQL “down” tay. Không chạy `2026-10-28-v7-phu-phi-core-a.rollback.sql` sau khi đã có lệnh phí PR-B (nó dừng ở `ROLLBACK_CLASSIFIED_LINES`).
Trước khi làm giao diện phụ phí: đếm trên bản sao `hao` số dòng sổ gốc có `counted_differs` (chỉ đếm, báo cáo ngoài repo).
Sau đợt nâng tay được duyệt riêng, phải chạy `v7_post_deploy_check.sql`: app chỉ EXECUTE chữ ký công khai, reader chỉ đọc (gồm `get_fee_types()`); toàn bộ helper/dry-run không được cấp EXECUTE cho hai role. Checker không cấp quyền hay sửa dữ liệu.

# Ngăn kéo Công nợ theo tháng đọc sổ gốc (29/10/2026)

Migration `2026-10-29-v7-matrix-drawer-so-goc.sql` chỉ thay `get_receivables_detail` (chạy sau `2026-10-29-v7-phu-phi-b-p2.sql`; không đổi dữ liệu, giữ quyền EXECUTE, chạy lại được). Hàm đọc số tháng từ `get_ledger`: phát sinh/đã thu như dòng Tổng tháng (tháng sổ gốc lấy số Sheet), danh sách gồm chuyến web và dòng chuyến sổ gốc (`historical`); `outstanding_vnd` vẫn là ô ma trận, thêm `allocated_vnd` là thu đã phân bổ vào kỳ.
ĐÃ KIỂM CHỨNG cục bộ: `test_pg_v7_matrix.py` (ca D1–D4), harness backend gồm lượt nâng migration hai lần so catalog với khởi tạo mới. CHƯA TRIỂN KHAI: nâng tay trên `hao` cần người dùng duyệt; sau nâng chạy `v7_post_deploy_check.sql` và mở thử ngăn kéo một tháng sổ gốc, một tháng có chuyến web.

# Migration NHAP-SHEET-01 — sửa/xóa chuyến (22/10/2026)

**Đã triển khai 22/10/2026** (commit `723d1ac`, CI xanh đúng SHA): trip-review rồi nhap-sheet chạy trên `webdebit_v7` thật
trong cửa sổ dừng ghi, sau backup, restore thử và chạy thử hai lượt trên bản sao. Cả hai migration mã thoát 0,
checker sau triển khai OK (236 khách, 877 kỳ), số dư 0/236 khách lệch, `DOI SOAT: DAT` 236/236.
Chưa đo thời gian khóa bảng trên dữ liệu thật; chưa kiểm nhập/sửa/xóa chuyến qua giao diện.
Lưu ý khi dựng DB restore thử: `createdb` để PUBLIC có CONNECT, cần thu hồi trước khi chạy checker.

Phạm vi mã: `cong-no-web-handoff/tools/migrations/2026-10-22-v7-nhap-sheet.sql`;
chạy sau M2-11, CSM và trip-review. Mục này là hướng dẫn cho gate triển khai riêng,
không cho phép chạy trên `hao` trong task backend.

1. Backup trước; restore vào PostgreSQL dùng một lần và chạy migration hai lượt.
   Kiểm `test_pg_v7_backend.py`, `test_pg_v7_grants.py --strict`,
   `rehearse_v7_deploy.py --strict` và `npm run check` qua bộ điều phối.
2. Dừng ghi trong cửa sổ triển khai đã được duyệt. Chạy bằng `psql -X -v ON_ERROR_STOP=1`.
   Migration giữ khóa bảng trong một transaction (`NOWAIT`: còn giao dịch đang dùng
   bảng thì dừng ngay), chụp tổng nợ **từng khách** trước/sau;
   lỗi `NHAP_SHEET_BALANCE_CHANGED` làm transaction thất bại, phải ROLLBACK.
   Không sửa `opening_balance`, `legacy_row`, `trip` hay các dòng `adjustment` cũ.
3. Chạy `v7_post_deploy_check.sql`: kiểm quyền, `adjustment_one_target`, số góp dòng
   sổ gốc và event của revision. Đối soát Sheet–web theo tổng từng khách:
   yêu cầu `DOI SOAT: DAT` đủ 236 khách của mốc đang dùng, giữ báo cáo ngoài Git.
4. Chỉ mở ghi sau khi kiểm và đối soát đạt, theo gate triển khai riêng. Nếu lỗi,
   giữ dừng ghi; dùng backup và quy trình rollback hiện có. Không xóa revision hoặc
   sửa opening để ép tổng khớp. Giao diện nhập kiểu Sheet triển khai riêng.

Chuẩn bị kiểm tại gốc worktree: kích hoạt venv đã cài requirements theo README,
chạy `npm ci --ignore-scripts` để cài đúng dependency trong lockfile, rồi
`npx playwright install chromium` nếu chưa có browser. Sau đó chạy `npm run check`
qua bộ điều phối; runner này tự chạy unittest từ `cong-no-web-handoff`.
Không thêm dependency hoặc sửa test để bù môi trường thiếu package.

Nếu dùng venv ngoài worktree trên Windows, đặt đủ biến môi trường trong tiến trình
bộ điều phối trước khi gọi kiểm (thay `<venv>` bằng đường dẫn venv đã cài requirements):

```powershell
$env:VIRTUAL_ENV = '<venv>'
$env:WEBDEBIT_PYTHON = Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe'
$env:PATH = (Join-Path $env:VIRTUAL_ENV 'Scripts') + ';' + $env:PATH
$handoffPath = Join-Path (Get-Location).Path 'cong-no-web-handoff'
$env:PYTHONPATH = $handoffPath + [IO.Path]::PathSeparator + $env:PYTHONPATH
& $env:WEBDEBIT_PYTHON -c "import tools, pilot; print('imports OK')"
ruff --version
& $env:WEBDEBIT_PYTHON -m unittest discover -s cong-no-web-handoff/tests
npm run check
```

`VIRTUAL_ENV` phục vụ runner chính; viewer dùng `WEBDEBIT_PYTHON`, còn ruff cần
thư mục `Scripts` trên `PATH`. Chỉ đặt `VIRTUAL_ENV` không đủ cho hai bước này.
`PYTHONPATH` cho phép giữ nguyên lệnh unittest từ gốc worktree trong spec.
Kiểm import và phiên bản trên là kiểm setup, không thay kết quả test.

Cách khác cho unittest riêng: đặt thư mục làm việc là
`<worktree>/cong-no-web-handoff`, dùng Python của venv và chạy:

```text
<venv_python> -m unittest discover -s tests
```

Nếu không đặt `PYTHONPATH`, lệnh `-m unittest discover -s cong-no-web-handoff/tests`
từ gốc worktree thiếu `cong-no-web-handoff` trên đường import, gây `No module named 'tools'`
và `No module named 'pilot'`. Đây là yêu cầu thư mục chạy của bộ test hiện có;
không thay đổi backend hoặc bốn test ngoài phạm vi để né lỗi import.
