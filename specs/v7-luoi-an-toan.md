# Lưới an toàn: kiểm sổ thật định kỳ (LUOI-AN-TOAN-01)

Trạng thái: ĐÃ CHỐT làm (người dùng chọn 18/11/2026, mục F5 của [checklist chuyển hẳn](../docs/chuyen-han-checklist.md)).
Cách làm, ngưỡng và chỗ giữ mốc do Claude đặt ([`LUOI-AN-TOAN-01`](../docs/decisions/luoi-an-toan-01.md)). Chỉ đọc sổ:
không đổi hàm ghi, bảng, quyền bảng, role, pg_hba hay quy tắc tiền.

## Đầu ra

Máy canh ([`CANH-BAO-01`](../docs/decisions/canh-bao-01.md), 15 phút một lượt) có thêm mục "lưới an toàn": bốn phép
kiểm trên sổ thật ở `hao`, sai thì báo qua email như các mục khác. Đây là phép kiểm thay cho "khớp Sheet" khi bỏ Sheet:
đối soát Sheet cho biết web có giống Sheet không, còn lưới an toàn cho biết sổ web có tự giữ đúng quy tắc của chính nó
không.

| # | Phép kiểm | Báo khi | Cần mốc lượt trước |
| --- | --- | --- | --- |
| 1 | Phiếu thu chia đủ | Phiếu chưa hủy có dòng chia còn hiệu lực cộng khác tiền phiếu hoặc không có dòng nào; phiếu hủy còn dòng; tiền ứng trước không nằm ở tháng phát sinh cuối; dòng chia không khớp Lịch sử. Đúng ba luật của `sokhach._check_allocations`, nay chạy cho mọi sổ có phiếu | Không |
| 2 | Số tổng khớp | "Còn phải thu", "khách trả thừa", bảng theo mặt hàng (`get_dashboard`), dải hạn trả và danh sách khách nợ (`get_dashboard_debt`) khác tổng các sổ (`v_outstanding_month`); sổ lưu trữ còn số dư (Tổng quan bỏ sót); tổng của `get_ledger` một sổ khác tổng sổ đó | Chỉ phần `get_ledger` |
| 3 | Sổ không tự đổi khi không có lệnh | Dữ liệu tiền của một sổ khác lượt trước mà `customer.version` không tăng; `version` lùi; sổ biến mất | Có |
| 4 | Lịch sử chỉ thêm | Dòng `sokhach.event` đã thấy ở lượt trước bị sửa, xóa hoặc chen thêm | Có |

Nội dung báo chỉ có mã sổ, tên phần dữ liệu, số đếm và giờ: không tên khách, không số tiền.

## Đối chiếu dữ liệu và code hiện có

- **Đường vào DB.** Máy canh chạy dưới `v7app`; peer map cho user này vào role `v7_app` (thành viên `sokhach_app`),
  như API và máy đối soát (`v7_reconcile_auto.py` dùng `PsqlDirect`). Role app chỉ có EXECUTE từng hàm, không SELECT
  bảng nào ([schema](v7-backend/schema-draft.sql), [checker](../cong-no-web-handoff/tools/v7_post_deploy_check.sql)).
  Nên cần một hàm `SECURITY DEFINER` chỉ đọc: `sokhach.get_safety_net(jsonb)`, cấp cho `sokhach_app`, không cấp
  `sokhach_reader`. Không thêm role, không đổi pg_hba. Gọi qua adapter `web/v7_psql.py` (luật ARCH-01).
- **Một ảnh dữ liệu.** Adapter có thêm chế độ `read_only=True`: `BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY`.
  Hàm từ chối chạy ngoài kiểu giao dịch đó (`SNAPSHOT_REQUIRED`): mọi phần kể cả `get_dashboard`, `get_ledger` thấy
  cùng một lúc của sổ, nên không báo nhầm khi máy đối soát đang ghi; và giao dịch không ghi được gì kể cả khi hàm lỗi.
- **Mọi lệnh ghi tăng `version`.** Rà 18/11/2026 mọi hàm ghi bảng tiền trong `v7_backend_functions.sql`: lệnh một sổ
  qua `_finish_command`; cấn trừ hai sổ tăng cả hai (`_finish_offset` cho sổ nguồn, `record_receipt`/`_void_receipt`/
  `_edit_receipt_meta` cho sổ đích); `reallocate`, `_sync_trip_fee`, `_compat_trip_fee`, `_reprice_from_table` chỉ chạy
  bên trong lệnh và không cấp cho app; `create_book_from_sheet` tạo sổ mới (lượt sau lấy mốc). Nên dữ liệu tiền đổi mà
  `version` đứng yên chỉ có thể do đường ngoài lệnh: sửa tay DB, migration, loader, phục hồi bản sao.
- **Đo trên `hao` 18/11/2026, chỉ đọc:** 242 sổ, 39 sổ có phiếu thu; mở cả 242 sổ bằng `get_ledger` mất 23 giây;
  `get_dashboard` cộng `get_dashboard_debt` 0,9 giây; 10.486 dòng Lịch sử (10 MB); khoảng 26 nghìn dòng dữ liệu tiền.
  Tính dấu vân cả hai phần dưới 0,1 giây. `systemd` 259; máy canh chưa có thư mục ghi nào.

## Cách so

### Kiểm 1, kiểm 2

Không cần mốc: mỗi lượt đúng hay sai tại chỗ. Kiểm 1 gọi `_check_allocations` cho từng sổ có phiếu, gom mã lỗi theo
sổ. Kiểm 2 cộng `v_outstanding_month` theo sổ (sổ có mốc nạp đang hiệu lực) rồi so với các con số Tổng quan hiển thị:

| Mã | Tổng quan | Bằng |
| --- | --- | --- |
| `RECEIVABLE_TOTAL`, `RECEIVABLE_COUNT` | `get_dashboard().receivable` | tổng và số sổ chưa lưu trữ có số dư dương |
| `CREDIT_TOTAL`, `CREDIT_COUNT` | `get_dashboard().credit` | tổng và số sổ chưa lưu trữ có số dư âm |
| `COMMODITY_TOTAL` | tổng `get_dashboard().by_commodity` | tổng số dư dương |
| `DEBT_TOTAL`, `DEBT_TIERS` | `get_dashboard_debt().receivable_vnd`, tổng năm nhóm hạn trả | tổng số dư dương |
| `DEBT_LIST` | `get_dashboard_debt().customers` (mã sổ, số dư) | đúng tập sổ dư dương, đúng số dư từng sổ |
| `ARCHIVED_BALANCE` | (Tổng quan bỏ sổ lưu trữ) | không sổ lưu trữ nào còn số dư |
| `LEDGER_TOTAL` | `get_ledger(sổ).total_outstanding_vnd` | tổng `v_outstanding_month` của sổ đó |

Mở cả 242 sổ mất 23 giây, nên phần `LEDGER_TOTAL` chia 8: lượt nào so
các sổ có `mã sổ mod 8` bằng `(giờ Unix / 900) mod 8`, khoảng 30 sổ. Mỗi sổ được so ít nhất 2 giờ một lần. Kết quả
từng phần giữ trong mốc để lượt sau vẫn báo tới khi phần đó so lại sạch.

Câu đọc nền (`read_only`) được chạy tới 60 giây (lệnh của người dùng vẫn 15 giây). Đo trên `hao` 18/11/2026 lúc API vừa
khởi động lại và đang tính lại hộp việc: một sổ lớn mất 8 giây mở bằng `get_ledger`, phần sổ chứa nó 11 giây; lượt chạy tay
`--full` đầu tiên có một phần quá 15 giây và lỗi. Bình thường một lượt máy canh 3–5 giây.

### Kiểm 3: sổ không tự đổi

Mỗi lượt, hàm trả cho từng sổ: `version` và dấu vân md5 của từng phần dữ liệu tiền, tính trên mọi dòng của sổ
(`jsonb_strip_nulls(to_jsonb(dòng))`, giờ UTC, thứ tự khóa cố định): số dư đầu (`opening_balance`), dòng sổ gốc
(`legacy_row`) và bản sửa của nó (`legacy_trip_rev`), chuyến (`trip`), bản sửa chuyến (`trip_info_rev`), giá chuyến
(`trip_price_rev`), phụ phí (`trip_fee_line`), điều chỉnh (`adjustment`), phiếu thu (`receipt`), dòng chia phiếu
(`receipt_line`), cấn trừ đi (`offset_pair` theo sổ nguồn), khóa tháng (`month_state`), mốc nạp sổ
(`cutover_customer`). So với mốc lượt trước:

| Lượt trước → lượt này | Kết luận |
| --- | --- |
| `version` tăng | Có lệnh ghi, bình thường; nhận mốc mới |
| `version` bằng, mọi dấu vân bằng | Không đổi |
| `version` bằng, có phần khác | `BOOK_CHANGED`: đổi ngoài đường lệnh, kèm tên phần |
| `version` nhỏ hơn | `VERSION_BACK`: thường là DB vừa phục hồi từ bản cũ |
| Sổ có ở lượt trước, lượt này không | `BOOK_GONE` |
| Sổ mới | Lấy mốc |

Thêm cột cho phép NULL vào các bảng này không đổi dấu vân (bỏ khóa NULL); thêm cột có mặc định khác NULL thì đổi.

### Kiểm 4: Lịch sử chỉ thêm

Dòng `sokhach.event` chia khối 1000 id; dấu vân mỗi khối là md5 nối md5 từng dòng theo id, kèm số dòng. Mốc giữ khối
của mọi dòng có id tới `upto`. Lượt sau tính lại các khối đó **chỉ trên dòng id ≤ upto**: khác số dòng hay khác dấu vân
là có dòng cũ bị sửa, xóa, hoặc chen vào sau (`EVENTS_CHANGED`, kèm khoảng id).

Chỉ đưa vào mốc dòng đã "lắng": `upto` là id lớn nhất trong các dòng có `at` cũ hơn 10 phút. Lý do: id cấp lúc chèn còn
dòng chỉ hiện ra lúc giao dịch commit, nên giao dịch đang chạy có thể còn giữ một id nhỏ hơn dòng đã thấy; chụp ngay
thì lượt sau sẽ thấy "dòng cũ mới xuất hiện" và báo nhầm. Lệnh ghi có giới hạn 15 giây mỗi câu, nên dòng chưa hiện sau
10 phút chỉ có thể đến từ một giao dịch dài hơn 5 phút. Dòng bị sửa ngay trong 10 phút đầu thì không thấy (giới hạn).

### Mốc giữa hai lượt

File `luoi-an-toan.json` (mode 600) trong `$STATE_DIRECTORY` mà systemd đặt cho máy canh: drop-in
`StateDirectory=v7-watchdog`, `StateDirectoryMode=0700` → `/var/lib/v7-watchdog`, chủ `v7app`, ghi được dù unit có
`ProtectSystem=strict`. Ghi bằng file tạm rồi đổi tên; khóa `flock` để lượt timer và lượt chạy tay không chen nhau.

Đã cân nhắc và bỏ:
- **Bảng trong DB:** máy canh phải ghi chính DB nó kiểm (không còn chỉ đọc), và phục hồi DB từ bản cũ sẽ phục hồi cả
  mốc, che đúng việc đáng báo nhất.
- **So trong một lượt** (cột hệ thống `xmin` của dòng mới hơn của dòng `customer`): không thấy dòng bị xóa, mà kiểm 4
  vẫn cần mốc; phục hồi bản sao hay migration sẽ báo cả 242 sổ mà không có cách chấp nhận.

Chưa có drop-in (biến `STATE_DIRECTORY` trống) thì kiểm 3, kiểm 4 và phần giữ kết quả `LEDGER_TOTAL` nghỉ, không báo;
kiểm 1, kiểm 2 vẫn chạy.

### Báo nhắc lại và chấp nhận

Kiểm 1, 2 tự hết báo khi sổ đúng lại. Kiểm 3, 4 là dấu vết của việc đã xảy ra nên **báo mãi** tới khi có người xem và
chấp nhận, kể cả khi sổ đó có lệnh ghi mới sau đó (mục chờ nằm trong mốc). Chấp nhận:

```text
sudo -u v7app python3 -B /srv/v7/auto-releases/current/cong-no-web-handoff/tools/v7_safety_net.py --state-dir /var/lib/v7-watchdog --accept
```

Lệnh in các mục được chấp nhận (mã sổ, phần, giờ thấy), xóa chúng, lấy mốc mới. Sau một migration hay loader đổi dữ
liệu sổ hoặc Lịch sử mà không qua lệnh: chạy `--dry-run` xem danh sách có đúng phạm vi migration không, rồi `--accept`.
Lượt máy canh lỡ chạy trước thì có một email; chấp nhận xong thì lượt kế báo ổn lại.

Mốc hỏng (không đọc được JSON): lấy mốc mới và để một mục chờ `STATE_RESET`, vì thay đổi trước lúc đó không còn so được.

## Câu báo (chỉ mã sổ, phần, số đếm, giờ)

| Mã | Câu |
| --- | --- |
| `ALLOCATION_INVARIANT` | Phiếu thu chia không khớp tiền phiếu ở N sổ (sổ …). |
| `ADVANCE_MONTH_INVARIANT` | Tiền ứng trước nằm sai tháng ở N sổ (sổ …). |
| `ALLOCATION_EVENT_INVARIANT` | Dòng chia phiếu thu không khớp Lịch sử ở N sổ (sổ …). |
| Kiểm 2 | Tổng quan không khớp tổng các sổ: <phần> (sổ …). / N sổ lưu trữ còn số dư, Tổng quan không tính (sổ …). / Tổng trong sổ khác tổng Tổng quan dùng ở N sổ (sổ …). |
| `BOOK_CHANGED` | Sổ X: <phần> đổi mà không qua lệnh nào, thấy lúc HH:MM ngày dd/mm. Cần xem rồi chấp nhận. (từ 4 sổ: gộp một câu, 5 mã sổ đầu) |
| `VERSION_BACK`, `BOOK_GONE` | Số lần ghi của N sổ bị lùi (DB có thể vừa phục hồi từ bản cũ) … / N sổ biến mất … |
| `EVENTS_CHANGED` | Lịch sử có dòng cũ bị sửa hoặc xóa (id A–B) … |
| `STATE_RESET` | Mốc lưới an toàn hỏng, đã lấy mốc mới … |

Hàm SQL chưa có (trước đợt nâng DB) thì mục này im, journal ghi "chưa có hàm". Lỗi khác (không vào được DB, hàm lỗi,
không ghi được mốc) thành dòng "Không kiểm được phần lưới an toàn (<lỗi>)" như mọi mục của máy canh.

## Nguồn quyết định

- [`LUOI-AN-TOAN-01`](../docs/decisions/luoi-an-toan-01.md); kênh báo [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md).
- Phân bổ thu và ứng trước: [`V7-SO`](../docs/decisions/v7-so.md), [`V7-BE`](../docs/decisions/v7-be.md),
  [`CAN-DU-01`](../docs/decisions/can-du-01.md). Lịch sử chỉ thêm, `version` tăng mỗi lệnh: [thiết kế V7](v7-backend/thiet-ke.md).
- Triển khai SQL tay: [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md).

## Hành vi và bất biến

- Chỉ đọc sổ. Giao dịch `READ ONLY`, hàm từ chối chạy ngoài giao dịch đó. Máy canh chỉ ghi file mốc của chính nó.
- Kết quả hàm và câu báo không có tên khách, số tiền; chỉ mã sổ, mã lỗi, số đếm, phiên bản, dấu vân.
- Một phép kiểm hỏng không che phép khác: mục "lưới an toàn" là một mục riêng trong `collect()`, import muộn, lỗi thành
  một dòng "Không kiểm được"; trong mục, kiểm 1–4 cùng một câu SQL nên hỏng thì hỏng cả mục.
- `--dry-run` của máy canh và của lệnh tay không ghi mốc. Lệnh tay có thư mục mốc từ chối chạy bằng root: file mốc, khóa của
  root làm máy canh (`v7app`) không ghi được nữa.
- Lượt đầu chỉ lấy mốc, không báo kiểm 3, 4.

## Giới hạn (không bắt được)

- Lệnh ghi đúng đường mà ra số sai (lỗi logic): lưới chỉ thấy khi phá luật kiểm 1, 2. Trước deploy đã có
  [FIFO ngẫu nhiên](v7-fifo-ngau-nhien.md); số sai so với thực tế cần đối chiếu booking và xác nhận của khách.
- Sửa tay một sổ trong cùng 15 phút với một lệnh ghi trên sổ đó: `version` đã tăng nên coi như lệnh làm.
- Sửa dòng Lịch sử trong 10 phút đầu sau khi ghi.
- Bảng ngoài danh sách dữ liệu tiền ở trên (bảng giá, ảnh chứng từ, ghi chú đòi nợ, gắn Zalo): không thuộc số dư.
- Người có quyền ghi cả DB lẫn file mốc có thể sửa cả hai. Lưới chống tai nạn, không chống người cố ý có quyền root.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_safety_net.py` (không DB): lượt đầu lấy mốc; từng mã báo đúng, không tên khách, không số tiền; lệnh
      ghi hợp lệ không báo; mục chờ còn sau lệnh ghi mới, `--accept` xóa; phần `LEDGER_TOTAL` giữ qua các lượt phần khác;
      chưa có thư mục mốc thì kiểm 3, 4 nghỉ; hàm chưa có thì im; mốc hỏng; `--dry-run` không ghi.
- [x] `tests/test_v7_watchdog.py`: mục lưới an toàn hỏng không che mục khác; `--dry-run` không ghi mốc.
- [x] `tools/test_pg_v7_luoi_an_toan.py` (PostgreSQL 18.6 dùng một lần, gọi bằng `v7_app` qua adapter): sổ giả sạch qua
      nhiều lệnh ghi thì không báo; **mỗi phép kiểm có một vi phạm cố ý làm nó đỏ**: sửa tay dòng chia phiếu (kiểm 1 và
      3), sổ lưu trữ còn nợ và hàm Tổng quan, `get_ledger` bị làm sai trong container (kiểm 2), sửa tay khóa tháng, giá
      chuyến và lùi `version` (kiểm 3), sửa và xóa dòng Lịch sử (kiểm 4); chạy ngoài `READ ONLY` bị từ chối; kết quả
      không có tên sổ hay khóa `_vnd`. CI: job `postgres-v7-luoi-an-toan`.
- [x] Migration chạy hai lần được; `--migration-test` so catalog khớp file chuẩn; harness quyền và checker sau triển
      khai có hàm mới cho app, không cho reader.
- [x] `npm run check`, `node scripts/check-secrets.js` xanh (ở máy; CI theo PR).
- [x] Trên `hao`: nâng DB theo runbook, cài drop-in, một lượt máy canh thật chạy lưới an toàn (ổn, hoặc danh sách lệch kèm
      lời giải thích) và lượt sau so với mốc.

## Phạm vi file

- Thêm: `cong-no-web-handoff/tools/migrations/2026-11-18-v7-luoi-an-toan.sql`, `cong-no-web-handoff/tools/v7_safety_net.py`,
  `cong-no-web-handoff/tests/test_v7_safety_net.py`, `cong-no-web-handoff/tools/test_pg_v7_luoi_an_toan.py`, spec này,
  `docs/decisions/luoi-an-toan-01.md`.
- Sửa: `cong-no-web-handoff/tools/v7_backend_functions.sql` (thêm ba hàm và quyền), `cong-no-web-handoff/web/v7_psql.py`
  (chế độ `read_only`), `cong-no-web-handoff/web/v7_api_tables.py` (hai câu SQL), `cong-no-web-handoff/tools/v7_watchdog.py`
  (một mục), `cong-no-web-handoff/tools/v7_post_deploy_check.sql`, các harness khai hàm hoặc chuỗi migration
  (`test_pg_v7_backend.py`, `test_pg_v7_backend_locks.py`, `test_pg_v7_backend_price.py`, `test_pg_v7_grants.py`,
  `test_pg_v7_backend_schema.py`), `tests/test_v7_fee_sql_sync.py`, `tests/test_v7_ledger_api.py`, `tests/test_v7_watchdog.py`,
  `.github/workflows/test.yml`, `docs/decisions.md`, `docs/decisions/canh-bao-01.md`, `docs/development.md`,
  `docs/v7-deploy-runbook.md`, `docs/chuyen-han-checklist.md`, `specs/v7-canh-bao.md`.

## Hoàn tác

Tắt mục mà không gỡ gì: xóa drop-in và `daemon-reload` (kiểm 3, 4 nghỉ), hoặc revert PR (máy canh không còn mục này).
Gỡ hàm: `DROP FUNCTION sokhach.get_safety_net(jsonb), sokhach._safety_fingerprints(), sokhach._safety_events(bigint,interval);`
— không gì phụ thuộc, không đụng dữ liệu. Xóa `/var/lib/v7-watchdog` nếu muốn.

## Bằng chứng

Ở máy (Windows, Docker Desktop, PostgreSQL 18.6 dùng một lần), 18/11/2026, trên nhánh trước khi mở PR:

- `tools/test_pg_v7_luoi_an_toan.py`: pass, 7 nhóm case, 19,5 giây, dọn container và volume.
- `test_pg_v7_backend.py --migration-test`: migration pass, SCHEMA 10/10, BEHAVIOR 71/71, 2 case CÒN MỞ bỏ qua như trước.
  Case 7.02 (so mô hình JS) chỉ xanh khi `node` thật đứng trước trong PATH: shim Volta của máy này nuốt script `node -e`
  nhiều dòng (thoát 0, không in gì). CI không bị.
- `test_pg_v7_grants.py --strict`, `test_pg_v7_direct.py --strict`, `rehearse_v7_deploy.py --strict`: pass.
- `npm run check` xanh (ruff, luật nghiệp vụ, link tài liệu, bí mật, eslint, unittest, ba bộ test JS);
  `node scripts/check-secrets.js` trên diff đã stage: sạch.

CI #461 xanh. Trên `hao` 18/11/2026: [nhật ký triển khai](../docs/deploys/2026-11-18-luoi-an-toan.md). Lượt đầu sạch cả bốn phép kiểm (không phiếu thu nào chia lệch, Tổng quan khớp tổng các sổ, cả 242 sổ khớp `get_ledger`); từ lượt 06:47 mỗi lượt so với mốc lượt trước.
