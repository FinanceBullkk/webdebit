# Kế hoạch triển khai V7 lên `hao` — ĐỀ XUẤT

Tài liệu kế hoạch, không phải quyền chạy. Không DDL/deploy/submit thật, không SSH vào `hao`, không
đụng Sheet/dữ liệu thật từ việc viết tài liệu này. Lệnh chạy tay thuộc
[Runbook triển khai V7](../../docs/v7-deploy-runbook.md) (các bước 0–8); tài liệu này chỉ sắp xếp thứ tự,
đối chiếu với [Sổ quyết định](../../docs/decisions.md) và chỉ ra CÒN MỞ. Khi hai tài liệu lệch nhau,
runbook là nguồn cho lệnh/placeholder, sổ quyết định là nguồn cho chính sách; tài liệu này không chốt thêm.

## Nguồn

- [docs/decisions.md](../../docs/decisions.md): [`SONG-SONG-01`](../../docs/decisions.md#song-song-01),
  [`MOC-CHUYEN-MOI`](../../docs/decisions.md#moc-chuyen-moi), [`OPENING-SO-GOC`](../../docs/decisions.md#opening-so-goc),
  [`V7-ID`](../../docs/decisions.md#v7-id), [`V7-CSM`](../../docs/decisions.md#v7-csm),
  [Gate chưa đóng](../../docs/decisions.md#gate-chưa-đóng).
- [docs/v7-deploy-runbook.md](../../docs/v7-deploy-runbook.md): ĐÃ KIỂM CHỨNG bản sao Docker 21/10/2026
  (`status=pass` bước 1–7 kể cả rollback B/C, dữ liệu sạch thật 236 khách/877 dòng và dữ liệu giả); CÒN MỞ
  peer/pg_hba thật, systemd, Tailscale Serve, dung lượng/thời gian thật trên máy chủ.
- `cong-no-web-handoff/tools/rehearse_v7_deploy.py`, `test_pg_v7_backend.py`, `test_pg_v7_grants.py`,
  `test_pg_v7_direct.py`, `test_pg_v7_p0_harness.py`: bộ kiểm chạy trên PostgreSQL 18.6 trong container dùng
  một lần, không chạm `hao`.
- `specs/v7-backend/schema-draft.sql`, `cong-no-web-handoff/tools/v7_backend_functions.sql`: lược đồ `sokhach`
  và 11 hàm ghi + hàm đọc hiện có trong repo, dùng để đối chiếu xem từng chính sách V7-CSM đã có thân hàm chưa
  (xem mục 4).

## 1. Thứ tự các bước triển khai

Giữ đúng số bước của runbook; cột "Chính sách/nguồn" đối chiếu quyết định đang áp dụng ở bước đó.

| # | Bước | Module/lệnh (runbook) | Chính sách/nguồn | Kiểm | Bằng chứng |
| --- | --- | --- | --- | --- | --- |
| 0 | Gate, commit, gói mã | `git archive` + `sha256sum -c` | — | CI xanh đúng SHA, hash khớp | `release.sha256`, URL CI, không chép tên khách/tiền vào PR |
| 1 | Preflight chỉ đọc | `systemctl is-active`, `ss -lxnp/-ltnp`, `counts.sql` | Chỉ unix socket (ĐÃ CHỐT 21/10, bảng runbook) | 18.x, không TCP, DB/role V7 chưa có, đủ dung lượng, legacy baseline count | `preflight.txt`, `baseline.counts` |
| 2 | Backup toàn phần | `pg_dumpall --globals-only`, `pg_dump -Fc`, restore thử vào `<restore_db>` | — | restore khớp exact counts, hash + quyền 600 | `globals.sql`, `ledger.dump`, `backup.sha256` |
| 3 | Provision một lần | `schema-draft.sql` → `v7_backend_functions.sql` → tạo role `v7_app`/`<loader_role>` → `pg_hba`/`pg_ident` peer → `v7_post_deploy_check.sql` | Schema `sokhach`, không maker/checker (`V6-DB`); danh tính Tailscale riêng người (`V7-ID`) | Hai role login peer đúng OS user; checker 0 khách/0 opening | `config.sha256`, output checker |
| 4 | Kế hoạch và nạp mốc | `v7_export_clean.py` (ngoài runbook, chạy trước) → `v7_load_direct.py --from-clean` (PLAN) → so hash/manifest/count → `--apply` | Mốc = bản xuất Sheet mới nhất ngày bắt đầu song song qua `v7_export_clean.py`, nạp vào V7 (`SONG-SONG-01` (2), **sửa 21/10 thay bản v2 20/10 của `MOC-CHUYEN-MOI`**) | PLAN count khách/tháng/dòng khớp manifest; `--apply` rồi checker count đúng | `clean.sha256`, `load-plan.json`, `load-apply.json` |
| 5 | Service API + danh tính | `v7_ledger_api.py --behind-tailscale-serve` qua `systemd` + `tailscale serve --bg --https=<serve_port>` | Danh tính Tailscale riêng người, actor từ phiên server (`V7-ID`) | unit active; peer `v7_app`; hai người khác nhau ghi actor khác nhau (kiểm riêng ngoài Docker) | `serve.after.json`, log systemd |
| 6 | Kiểm sau triển khai | `v7_post_deploy_check.sql` với `expect_customers/openings`, `curl /api/v7/customers`, `curl /api/v7/ledger`, `v7_reconcile_sheet.py --api` | Đối soát theo tổng từng khách (`SONG-SONG-01` (4)) | checker OK, GET 200, `DOI SOAT: DAT`, legacy count không đổi | `customers.json`, `ledger.json`, reconcile report ngoài repo |

Bước 4 phụ thuộc một bước không nằm trong runbook: chạy `v7_export_clean.py` trên bản xuất Sheet **đúng ngày
bắt đầu song song** rồi mới nạp — đây là điểm "mốc" theo `SONG-SONG-01`, không phải bản tổng duyệt 21/10 (bản
đó chỉ để kiểm công cụ). Thứ tự 0→6 là tuần tự, không bước nào chạy song song với bước trước nó; dừng ở bất
kỳ bước nào theo đúng gate của runbook (xem cột "Dừng" trong runbook) thì rollback mức tương ứng (A/B) trước
khi thử lại, không sửa SQL/API/nạp để né lỗi.

## 2. Điều kiện an toàn trước khi chạy thật

- **Backup trước nạp:** bước 2 (backup toàn phần + restore thử) phải ĐẠT và có hash trước khi chạm bước 3
  (provision) — runbook đã đặt đúng thứ tự này, không đảo bước.
- **Rollback nếu lỗi:**
  - Lỗi ở bước 1–2 (preflight/backup): dừng, không provision.
  - Lỗi ở bước 3 (provision) hoặc 4 (nạp) trước khi mở API: rollback mức B (xóa DB/role V7, gỡ `pg_hba`/`pg_ident`
    đã thêm, giữ nguyên `webdebit_ledger`) — runbook §7B. Không chạy lại schema sau lỗi provision mà chưa rollback.
  - Lỗi ở bước 5–6 (API/đối soát): rollback mức A (tắt route Serve + unit, giữ DB V7 để điều tra) — runbook §7A;
    chỉ xuống mức B sau khi đã lưu hồ sơ cần giữ.
  - Mức C (sự cố `webdebit_ledger`) chỉ dùng khi legacy lệch baseline — không thuộc luồng triển khai bình thường,
    cần gate khẩn cấp riêng theo runbook §7C.
- **Không gián đoạn viewer cũ:** `webdebit_ledger` và service xem sổ cũ (M1) không bị chạm ở bước 0–6 (DB V7
  là DB riêng `<db_v7>`, role riêng, pg_hba chỉ thêm hai dòng mới). Trước bước 1, kiểm `pg_stat_activity` trên
  `webdebit_ledger` để chọn cửa sổ ít người đang xem (runbook: "nếu viewer có writer khác thì dừng, chọn cửa sổ
  không ghi" — áp cho backup; khuyến nghị áp cùng cho toàn bộ 0–6 vì bước 3 `reload` PostgreSQL ảnh hưởng mọi
  kết nối mới trong khoảnh khắc reload). Sau bước 6, chạy lại `counts.sql` trên `webdebit_ledger` và diff với
  baseline bước 1 — count không đổi là điều kiện ĐẠT của bước 6, không phải việc làm thêm.
  **CÒN MỞ:** chưa có cách báo trước cho người đang xem sổ cũ biết có bảo trì ngắn lúc reload; để sau, không
  chặn bắt đầu song song (reload PostgreSQL không ngắt kết nối đã mở, chỉ áp từ kết nối mới).

## 3. Danh tính Tailscale (V7-ID) — tối thiểu để mở ghi tiền thật

`V7-ID` đã chốt hướng (danh tính riêng từng người qua Tailscale, actor lấy từ phiên server, không nhận actor
từ client) nhưng để ngỏ "cách app đọc danh tính Tailscale tin cậy" và "quản lý ai được vào/thu hồi" cho sau.
Để bắt đầu `SONG-SONG-01` an toàn mà không chờ giải pháp đầy đủ, tối thiểu cần:

1. **Serve, không Funnel:** `tailscale serve --https=<serve_port> http://127.0.0.1:<port>` (runbook bước 5) —
   chỉ phục vụ trong tailnet của chủ máy, không public. Đã có trong runbook; điều kiện bắt buộc trước khi mở
   bước 6 (GET/reconcile) cho người thật dùng.
2. **API đọc actor qua Serve, không qua header client tự khai:** `v7_ledger_api.py --behind-tailscale-serve`
   (đối lập `--insecure-dev-actor` chỉ dùng trong Docker/dev). Runbook đã ghi rõ "Header client tự khai không
   là bằng chứng" — là điều kiện cần kiểm bằng cách gửi hai kết nối từ hai máy/tài khoản Tailscale khác nhau
   và xem log actor khác nhau, trước khi coi bước 5 ĐẠT (runbook đã liệt mục này trong "Đạt" của bước 5 nhưng
   chưa có bằng chứng thật — CÒN MỞ (4) của runbook).
3. **Danh sách ai được vào tailnet này:** không cần UI quản trị, chỉ cần người dùng/chủ nghiệp vụ tự duyệt
   danh sách thiết bị/tài khoản Tailscale admin console trước khi mở bước 5 — việc này nằm ngoài code, không
   chặn bởi runbook/schema, nhưng là điều kiện thủ công bắt buộc (nếu bất kỳ ai nối được vào tailnet đều thao
   tác được ghi tiền theo `V7-ID` "bản thử", thì tailnet đó phải chỉ gồm người được phép).
4. **Không cần ngay** (để sau, không chặn bắt đầu song song): phân quyền theo người (ai xem gì, ai sửa gì) —
   `V7-ID` đã chốt "bản thử: ai vào app cũng thao tác được"; thu hồi quyền tức thời; UI quản lý người dùng.

Tối thiểu 1–3 đủ để chặn truy cập trái phép từ ngoài tailnet và chặn giả actor; không đủ để phân quyền nội bộ
— rủi ro còn lại (một người trong tailnet sửa sổ người khác) đã được `V7-ID`/`V6-DB` chấp nhận như đánh đổi
đã chốt, không phải lỗ hổng mới của kế hoạch này.

## 4. Gate CÒN MỞ bắt buộc đóng trước triển khai vs để sau

Đối chiếu [Gate chưa đóng](../../docs/decisions.md#gate-chưa-đóng) với lược đồ/hàm hiện có trong repo
(`specs/v7-backend/schema-draft.sql`, `cong-no-web-handoff/tools/v7_backend_functions.sql`):

| Gate | Chính sách | Trạng thái code | Bắt buộc đóng trước deploy? |
| --- | --- | --- | --- |
| D04 (dư/âm/ứng trước/hoàn tiền/tranh chấp) | ĐÃ CHỐT 21/10 (`V7-CSM` (1)) | `record_offset`/`void_offset`/`edit_offset_date` (cấn trừ hai sổ) đã có hàm trong `v7_backend_functions.sql`; không có đường hoàn tiền/trạng thái tranh chấp (đúng theo chính sách — không cần) | Không chặn — hàm cấn trừ đã có, chính sách không yêu cầu đường hoàn tiền |
| D05/D06 (tham chiếu, VND thực nhận) | ĐÃ CHỐT 21/10 (`V7-CSM` (2): ô "Tham chiếu" không bắt buộc) | **Không thấy cột tham chiếu trên `sokhach.receipt`** (`specs/v7-backend/schema-draft.sql` dòng ~225–244 chỉ có `pid, date, method, amount_vnd, void_*`) | **CÒN MỞ thật, nhưng không chặn bắt đầu song song**: thiếu cột là thiếu tiện ích đối soát (số giao dịch), không thiếu đúng-sai số tiền; thêm cột sau cũng không ảnh hưởng dữ liệu đã nạp. Khuyến nghị đóng trước khi coi là "xong M4", không bắt buộc trước M-song-song |
| D07 (mở/khóa tháng, ghi Lịch sử) | ĐÃ CHỐT 21/10 (`V7-CSM` (3): mỗi lần mở/khóa ghi một dòng Lịch sử) | **Chưa triển khai**: `sokhach.event` có comment tường minh "không ghi sự kiện mở/khóa tháng" (`schema-draft.sql`); `set_month_lock` chỉ `UPSERT` `month_state(locked, changed_by, changed_at)`, mất lịch sử các lần mở/khóa trước đó (ghi đè, không phải log) | **CÒN MỞ thật**, nhưng không chặn bắt đầu song song ở quy mô nhỏ: `changed_by/changed_at` vẫn cho biết lần mở/khóa *gần nhất*, đủ để vận hành thủ công ban đầu; mất khi có kiểm toán nhiều lần mở/khóa trong một tháng. Khuyến nghị đóng trước khi coi `V7-CSM` là ĐÃ TRIỂN KHAI đầy đủ, nhưng không cần trước khi mở ghi tiền thật đầu tiên |
| P0 (procedure atomic, idempotency, FIFO dưới đồng thời, đảo chính xác, khóa kỳ, snapshot phiếu) | Approval hết hiệu lực (`V6-DB`); phần còn lại vẫn mở | `_begin_command`/`_finish_command` có idempotency + version check (optimistic lock qua `expected_version`); `test_pg_v7_backend.py`/`test_pg_v7_p0_harness.py` kiểm trên container một lần, không phải trên tải đồng thời thật của `hao` | **Bắt buộc đóng trước deploy production nhiều người ghi đồng thời**: báo cáo tổng duyệt 21/10 chưa đo đồng thời thật (nhiều session ghi cùng khách cùng lúc trên hạ tầng thật). Với `SONG-SONG-01` khởi động (số người ghi ít, một người/một sổ tại một thời điểm theo thực tế vận hành), rủi ro thấp nhưng CÒN MỞ — không tự đóng bằng test container |
| Vận hành: role/auth, DB integration, nghiệm thu, quyền deploy | Người duyệt thứ hai hết hiệu lực (`V6-DB`); ai xem Lịch sử chốt 21/10 (`V7-CSM` (4): ai mở sổ thì xem Lịch sử sổ đó) | Runbook đã có role/peer/ACL (bước 3); chưa có trên máy thật (CÒN MỞ của runbook: "peer/pg_hba thực tế... nghiệm thu danh tính/service") | **Bắt buộc đóng trước deploy**: đây chính là bước 3 và 5 của kế hoạch này — không phải gate riêng, là một phần của việc triển khai. "Ai xem Lịch sử" (mục 4 `V7-CSM`) đã có answer chính sách (ai mở sổ thì xem hết), nhưng chưa có UI/API lọc theo quyền — CÒN MỞ, không chặn vì hiện "ai vào app cũng thao tác được" (`V7-ID`) nên chưa có khái niệm "không mở được sổ" để phân biệt |

Tóm lại, **bắt buộc đóng trước khi bắt đầu `SONG-SONG-01`**: bước 3/5 của runbook chạy thật trên `hao` (role,
peer, pg_hba, Tailscale Serve — hiện CÒN MỞ vì chỉ kiểm trong Docker) và mục 3 (danh tính tối thiểu) ở trên.
**Có thể để sau, không chặn bắt đầu song song:** cột tham chiếu (D05/D06), log Lịch sử mở/khóa tháng (D07),
đo P0 dưới tải đồng thời thật — miễn là vận hành ban đầu ở quy mô nhỏ, ít người ghi cùng lúc, và người dùng
được báo rõ ba điểm này chưa có trước khi dùng thật.

## 5. Tiêu chí "xong" và bằng chứng từng bước

Lấy từ cột "Đạt"/"Thời gian" của từng mục runbook, rút gọn, **không ghi số khách/tiền thật vào bằng chứng
lưu trong repo hay PR** — chỉ ghi count, hash, timestamp, tên lệnh (theo `AGENTS.md` mục cấm raw capture).

| Bước | Xong khi | Bằng chứng ghi lại (không nhạy cảm) |
| --- | --- | --- |
| 0 | CI xanh đúng SHA; hash `release.sha256` khớp `sha256sum -c` | SHA commit, URL CI, nội dung `release.sha256` (đường dẫn + hash, không nội dung file) |
| 1 | PostgreSQL 18.x; không TCP listener; DB/role V7 chưa tồn tại; đủ dung lượng ≥ 3× `pg_database_size` | `preflight.txt` (version/setting), `baseline.counts` (tên bảng + số dòng, không nội dung dòng) |
| 2 | `pg_restore` thử khớp `baseline.counts`; `<restore_db>` đã xóa; hash + quyền 600 | `backup.sha256`, kết quả `diff` rỗng |
| 3 | Hai role login peer đúng OS user; checker báo 0 khách/0 opening; không đổi legacy | Output `v7_post_deploy_check.sql` (PASS/FAIL, không số liệu), `config.sha256` |
| 4 | PLAN count khách/tháng/dòng khớp manifest; `--apply` xong; checker count đúng số đã nạp | `load-plan.json`/`load-apply.json` (chỉ count + hash, không bảng khách), `clean.sha256` |
| 5 | systemd unit active; `tailscale serve status` đúng route; hai actor khác nhau ghi log khác nhau | `serve.after.json`, log actor (ID/tên Tailscale, không kèm số tiền) |
| 6 | Checker OK đúng count kỳ vọng; GET 200; `DOI SOAT: DAT`; legacy count không đổi | `customers.json`/`ledger.json` (JSON trả về từ API — cần tự kiểm trước khi lưu, không chứa tên/tiền thật nếu định đưa vào PR; nếu có thì chỉ giữ ngoài Git theo `AGENTS.md`), kết quả `diff` baseline/after |

Thời gian từng bước **chưa đo trên `hao`** (runbook ghi rõ các cột thời gian "chưa đo"); không coi thời gian
đo trong Docker (`rehearse_v7_deploy.py --report`) là thời gian thật.

## 6. Thứ tự chạy `SONG-SONG-01` sau khi deploy xong

Theo bốn vế đã chốt của `SONG-SONG-01`, đề xuất thứ tự:

1. **Xác nhận bước 6 (đối soát) ĐẠT** trên đúng mốc đã nạp — chủ nghiệp vụ (người dùng) tự xem `ledger.json`
   của một vài khách quen và so bằng mắt với Sheet, không chỉ tin `DOI SOAT: DAT`. Người xác nhận: chủ nghiệp vụ.
2. **Dán bù phần dồn từ mốc tới lúc web nhập được** (vế (3)): dùng chính các hàm ghi (`paste_trips`,
   `record_receipt`…) qua API, kiểm trùng với mốc theo `NEWTRIP-01` trước khi dán. Người làm: người thao tác
   hằng ngày (maker); không cần người duyệt thứ hai (`V6-DB`).
3. **Bắt đầu gõ song song**: Sheet vẫn chính thức; mọi thứ gõ mới vào Sheet sau mốc (chuyến, thu, sửa dòng cũ
   như điền giá) đưa lên web theo `V7-SO`. Người làm: người nhập hằng ngày; không cần chờ người khác duyệt.
4. **Đối soát định kỳ theo tổng từng khách** (vế (4)): hằng ngày hoặc hằng tuần — tần suất cụ thể và người
   phụ trách **CÒN MỞ**, cần người dùng chọn (runbook/`SONG-SONG-01` không ghi tần suất). Lệch theo từng tháng
   do thứ tự trừ nợ cũ trước không tính là lỗi; lệch tổng khách là lỗi phải tra trước khi tiếp tục dán bù.
5. **Theo dõi gate để sau** (mục 4 ở trên: cột tham chiếu, Lịch sử mở/khóa, P0 đồng thời) — không chặn bước
   1–4, nhưng cần đóng trước khi đề nghị chuyển hẳn.
6. **Điều kiện chuyển hẳn** (đã chốt, không lặp lại ở đây): ít nhất một lần cuối tháng khớp; mọi khách khớp
   hoặc lệch đã giải thích được; người dùng đã quen thao tác; sau đó khóa Sheet chỉ xem. Người quyết: chủ
   nghiệp vụ, tại thời điểm M4 — không tự đóng bằng kết quả kỹ thuật của kế hoạch này.

## CÒN MỞ cần người dùng/chủ nghiệp vụ quyết

Phát hiện khi viết spec này, chưa có trong `docs/decisions.md`:

- **Tần suất và người phụ trách đối soát định kỳ** (mục 6.4): `SONG-SONG-01` chốt "hằng ngày hoặc hằng tuần"
  như hai lựa chọn, chưa chọn một; chưa chỉ định ai chạy `v7_reconcile_sheet.py` và ai xem kết quả.
- **Mốc thời điểm cụ thể bắt đầu song song**: `SONG-SONG-01`/`MOC-CHUYEN-MOI` chốt "ngày bắt đầu chạy song
  song" làm mốc, nhưng chưa có ngày cụ thể — phụ thuộc khi nào bước 3/5 (role, peer, Tailscale Serve) chạy
  xong thật trên `hao`, chưa xảy ra.
- **D05/D06 cột tham chiếu và D07 Lịch sử mở/khóa chưa có thân hàm/cột** (mục 4): chính sách đã chốt nhưng
  chưa triển khai trong `schema-draft.sql`/`v7_backend_functions.sql`. Đề xuất trong tài liệu này (không chặn
  bắt đầu song song) là ĐỀ XUẤT của người viết spec, chưa phải quyết định của chủ nghiệp vụ — cần xác nhận có
  đồng ý trì hoãn hai việc này hay phải đóng trước khi mở ghi tiền thật.
- **Cách báo người đang xem web cũ trước lúc reload PostgreSQL** (mục 2): chưa có quy trình; đề xuất ở đây
  (chọn cửa sổ ít người dùng) là suy luận từ runbook, chưa được chủ nghiệp vụ xác nhận là đủ.
