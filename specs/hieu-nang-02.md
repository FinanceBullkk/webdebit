# Tổng quan nhanh hơn: `get_dashboard_debt` chạy với JIT tắt (HIEU-NANG-02)

Trạng thái: ĐÃ CHỐT. Việc do phiên MO-SO-NHANH-03 giao ngày 18/11/2026 (mục CÒN MỞ "`get_dashboard_debt` cũng bị JIT" trong [MO-SO-NHANH-03](mo-so-nhanh-03.md)): đo các hàm đọc nặng còn lại của V7, hàm nào thật sự tốn JIT thì tắt JIT trong khai báo hàm. Claude chọn cách làm theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md). Phạm vi: cấu hình của một hàm đọc là `get_dashboard_debt`. Không đổi thân hàm, luật tiền, bảng, view, dữ liệu, quyền, giao diện, cấu hình cụm, DB hay role. ĐÃ TRIỂN KHAI trên `hao` 18/11/2026 lúc 10:19, bản `da1708b`, [nhật ký](../docs/deploys/2026-11-18-tong-quan-tat-jit.md).

Tiếp [HIEU-NANG-01](hieu-nang-01.md) (bộ nhớ đọc theo dấu dữ liệu: chỉ tính lại sau mỗi lệnh ghi) và [MO-SO-NHANH-03](mo-so-nhanh-03.md) (`get_ledger` chạy với JIT tắt).

## Người dùng và luồng

Người dùng mở Tổng quan hoặc Việc cần làm, còn menu thì hiện huy hiệu trên mọi trang. Các chỗ này gọi `GET /api/v7/dashboard/debt`, và API chạy `get_dashboard_debt` qua bộ nhớ đọc. Sau mỗi lệnh ghi, hoặc khi API vừa khởi động, lần đọc kế tiếp phải tính lại bằng một psql mới. Vì vậy lần tính lại nào cũng lập kế hoạch riêng và chịu JIT. Máy canh còn gọi `get_safety_net` mỗi 15 phút, và hàm này gọi `get_dashboard_debt`. Màn hình không đổi gì.

## Số đo trước khi làm

Bản sao trên PC được khôi phục từ bản backup mỗi giờ lúc 09:00 ngày 18/11/2026 (khớp manifest: 34 bảng, 242 sổ). Bản sao dùng image PostgreSQL 18.6 của harness, cấu hình JIT mặc định giống `hao` (`jit=on`, `jit_above_cost` 100.000, `jit_inline_above_cost` và `jit_optimize_above_cost` 500.000), và đã `ANALYZE`. Mỗi lượt đo là một psql mới dưới `v7_app`, đúng khuôn câu của API (`BEGIN`, `SET LOCAL sokhach.actor`, câu `SELECT` của `v7_api_tables.py`; riêng `get_safety_net` dùng giao dịch REPEATABLE READ READ ONLY như máy canh). Số đo là giờ của câu `SELECT` (`\timing`), 3 lượt mỗi cột, xen kẽ hai chế độ. Câu bị JIT và chi phí ước tính lấy từ `auto_explain` (`log_nested_statements`, `log_analyze`).

| Hàm (đối số) | Hôm nay | JIT tắt cả phiên | Câu bị JIT | Chi phí ước tính lớn nhất |
| --- | ---: | ---: | --- | ---: |
| `get_dashboard_debt()` | 325–356 ms | 87–93 ms | 1 (JIT 224 ms, 645 hàm) | 175.102 |
| `get_dashboard()` | 65–71 ms | 64–75 ms | 0 | 46.654 |
| `get_receivables_matrix(2026)` | 50–55 ms | 51–54 ms | 0 | 34.963 |
| `get_receivables_detail(104, 11/2026)` | 173–179 ms | 169–173 ms | 0 | 797.119 (trong `get_ledger`, đã tắt JIT) |
| `get_receivables_detail(79, 10/2026)` | 225–233 ms | 218–226 ms | 0 | 206.298 (như trên) |
| `get_receipt_book(NULL)` | 60–65 ms | 60–81 ms | 0 | 14.174 |
| `get_trip_month(11/2026)` | 29–30 ms | 29–32 ms | 0 | 93.532 |
| `get_activity(NULL)` | 17–18 ms | 16–17 ms | 0 | 3.094 |
| `get_safety_net`, phần sổ 0/8 | 1.395–1.468 ms | 1.122–1.189 ms | 1 (câu của `get_dashboard_debt`) | 797.119 (`get_ledger`) |
| `get_safety_net`, không so sổ | 804–870 ms | 555–590 ms | 1 (như trên) | 175.102 |

Năm 2025, tháng 10 của `get_receipt_book` và `get_trip_month`, ngày 17/11 của `get_activity` và phần sổ 3/8 của `get_safety_net` cho cùng kết luận. Kết quả ở chế độ JIT tắt trùng băm với chế độ hôm nay.

DB thật trên `hao` được đo lúc 09:52 ngày 18/11/2026, chỉ đọc. Mỗi lượt là một psql mới dưới `v7_app` trong giao dịch chỉ đọc, như API gọi. `auto_explain` chạy trong giao dịch chỉ đọc và hạ quyền về `v7_app` sau khi nạp.

| Hàm | Giờ câu `SELECT` (3 lượt) | Câu bị JIT | Chi phí ước tính lớn nhất |
| --- | ---: | --- | ---: |
| `get_dashboard_debt()` | 784–788 ms | 1 (JIT 525 ms, 623 hàm) | 182.418 |
| `get_dashboard()` | 178–183 ms | 0 | 33.730 |
| `get_receivables_matrix(2026)` | 135–136 ms | 0 | 36.429 |
| `get_receivables_detail(104, 11/2026)` | 444–448 ms | 0 | 548.389 (`get_ledger`) |
| `get_receipt_book(NULL)` | 194–201 ms | 0 | 14.311 |
| `get_trip_month(11/2026)` | 95–96 ms | 0 | 94.701 |
| `get_activity(NULL)` | 18–21 ms | 0 | 2.667 |
| `get_safety_net`, phần sổ 0/8 | 3.626–3.632 ms | 1 (câu của `get_dashboard_debt`, JIT 527 ms) | 548.389 (`get_ledger`) |
| `get_safety_net`, không so sổ | 2.104–2.111 ms | 1 (như trên, JIT 524 ms) | 182.418 |

## Nguyên nhân

- Trong cả tám hàm chỉ có một câu bị JIT: câu chính của `get_dashboard_debt` (các CTE `act`…). Câu này có chi phí ước tính khoảng 175.000 trên bản sao và 182.000 trên `hao`. Mức đó vượt `jit_above_cost` (100.000) nhưng dưới hai ngưỡng inline/optimize (500.000), nên PostgreSQL chỉ sinh mã LLVM cho biểu thức, khoảng 620–645 hàm. Phần sinh mã mất 224 ms trên PC và 525 ms trên `hao`, trong khi phần chạy thật chỉ khoảng 90 ms trên PC.
- Lần tính lại nào cũng chịu JIT, vì API chạy mỗi lượt đọc bằng một psql mới (xem [MO-SO-NHANH-03](mo-so-nhanh-03.md#nguyên-nhân)). Bộ nhớ đọc của HIEU-NANG-01 làm số lần tính lại ít đi, nhưng không làm mỗi lần nhẹ hơn: sau mỗi lệnh ghi, lần mở Tổng quan hay huy hiệu menu kế tiếp lại chịu lại phần này.
- `get_safety_net` chịu JIT chỉ qua lần gọi `get_dashboard_debt`. Các câu riêng của nó không bị JIT, và `get_ledger` mà nó gọi đã tắt JIT.
- Sáu hàm còn lại không có câu nào bị JIT. Câu lớn nhất của `get_receivables_detail` nằm trong `get_ledger`, nên được cấu hình của `get_ledger` che. Hàm gần ngưỡng nhất là `get_trip_month` (93.532 trên bản sao, 94.701 trên `hao`, khoảng 95% ngưỡng). Chi phí của nó chủ yếu đến từ vòng lặp qua khoảng 10 nghìn dòng chuyến sổ gốc, gần như cố định; phần chuyến web chỉ khoảng 1.800. Spec này không sửa hàm đó (xem CÒN MỞ).

## Đầu ra

- `get_dashboard_debt` khai báo `SET jit = off` cạnh `SET search_path` trong `tools/v7_backend_functions.sql`. Hàm này không có bản chép trong `specs/v7-backend/schema-draft.sql`. File sinh tự động `schema/v7_schema_current.pgsql` được sinh lại và chỉ thêm đúng một dòng `SET jit TO 'off'`.
- Migration `tools/migrations/2026-11-18-v7-tong-quan-tat-jit.sql` chỉ có `ALTER FUNCTION sokhach.get_dashboard_debt() SET jit = off;` dưới `sokhach_owner`, và chạy lại được.
- Mọi câu trong hàm, kể cả khi `get_safety_net` gọi hàm, được lập kế hoạch không JIT, bất kể cấu hình của phiên hay của cụm. `get_safety_net` không cần cấu hình riêng: sau khi nâng, `auto_explain` thấy không câu nào trong nó bị JIT.
- Không đổi `postgresql.conf`, cấu hình role hay cấu hình DB. Các hàm khác vẫn theo cấu hình cụm.
- Trên bản sao ở PC, `get_dashboard_debt` từ 325–356 ms còn 89–96 ms, còn `get_safety_net` không so sổ từ 804–870 ms còn 554–576 ms.

## Hành vi và bất biến

- Kết quả trùng từng byte trước và sau: băm JSON của cả tám hàm (thêm `get_ledger` mọi sổ) trùng ở mọi đối số đã thử. JIT chỉ đổi cách chạy, không đổi kết quả.
- Không đổi thân hàm, chủ, ACL, `SECURITY DEFINER` hay `search_path`.
- Chạy lại `2026-11-09-v7-thu-thang-theo-so.sql`, hay migration cũ hơn có `CREATE OR REPLACE` cho `get_dashboard_debt` (`2026-11-06-v7-ngay-tra-that.sql`, `2026-10-29-v7-tong-quan-quan-ly-no.sql`), sẽ xóa cấu hình hàm. Khi đó phải chạy lại file này; điều này đã ghi ở đầu file và trong runbook. Chuỗi migration của harness chạy file này sau cả ba file đó.
- Thứ tự với release: độc lập, vì release cũ và mới gọi cùng một hàm.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_fee_sql_sync.py`: `get_dashboard_debt` chuẩn bằng bản DASH-08 (`2026-11-09-v7-thu-thang-theo-so.sql`) cộng đúng một mệnh đề `SET jit = off`; migration chỉ gồm `ALTER FUNCTION` trong một giao dịch.
- [x] Harness case `HIEU-NANG.02`: `proconfig` là `search_path` cộng `jit=off`. Khi phiên ép JIT cho mọi câu (`jit_above_cost = 0`), `auto_explain` chỉ thấy câu `SELECT` ngoài cùng có JIT; câu chính lồng trong `get_dashboard_debt` không có. Phép thử của MO-SO-NHANH-03 chuyển sang cùng module `tools/test_pg_v7_backend_jit_off.py` và dùng chung hàm dò.
- [x] `test_pg_v7_backend.py --migration-test` xanh (83 đạt, 2 bỏ qua là 7.11c và 7.15c, mục mở từ trước): chuỗi nâng của backend, locks và price có file mới, và catalog hàm trùng bản khởi tạo mới. `test_pg_v7_luoi_an_toan.py` xanh, `v7_schema_snapshot.py --check` khớp, `npm run check` xanh, `node scripts/check-secrets.js` sạch. CI của #470 xanh 17/17.
- [x] Bản sao trên PC: băm 814/814 lần gọi trùng trước và sau khi chạy migration hai lượt, sau `RESET jit` và sau khi nâng lại. Dấu vân dữ liệu trùng. Catalog chỉ đổi cấu hình `get_dashboard_debt`, còn chủ và quyền giữ nguyên. Số đo sau ở mục Đầu ra.
- [x] Bản sao trên `hao` (dump 10:13): băm 94/94 lần gọi trùng ở cả bốn mốc như trên; dấu vân trùng; catalog chỉ đổi cấu hình `get_dashboard_debt`; checker 9/9; `get_dashboard_debt` từ 816–867 ms còn 235–236 ms; DB thử đã xóa.
- [x] DB thật (10:19): backup và kiểm đọc lại, áp với `ON_ERROR_STOP` (116 ms), dấu vân và băm 94/94 trùng trước/sau, checker 9/9. Tổng quan (`get_dashboard_debt`, mỗi lần một psql mới như API) từ 784–788 ms còn 236–249 ms; không câu nào bị JIT; lưới an toàn `--dry-run` không báo ([nhật ký](../docs/deploys/2026-11-18-tong-quan-tat-jit.md)).

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`)
- Được sửa: `cong-no-web-handoff/tools/v7_backend_functions.sql`, `cong-no-web-handoff/schema/v7_schema_current.pgsql` (sinh lại), `cong-no-web-handoff/tools/migrations/2026-11-18-v7-tong-quan-tat-jit.sql`, `cong-no-web-handoff/tests/test_v7_fee_sql_sync.py`, `cong-no-web-handoff/tools/test_pg_v7_backend.py`, `test_pg_v7_backend_jit_off.py`, `test_pg_v7_backend_ledger_events.py`, `test_pg_v7_backend_locks.py`, `test_pg_v7_backend_price.py`, `docs/v7-deploy-runbook.md`, `specs/mo-so-nhanh-03.md` (trỏ mục CÒN MỞ), spec này, nhật ký trong `docs/deploys/`
- Cấm: đổi thân `get_dashboard_debt`; đổi cấu hình cụm, role hay DB; tắt JIT cho hàm chưa tốn JIT trong đợt này.

## Hoàn tác

Chạy `ALTER FUNCTION sokhach.get_dashboard_debt() RESET jit;` dưới `sokhach_owner`. Kết quả không đổi, chỉ chậm lại như trước. Revert PR để bỏ khỏi file chuẩn.

## Bằng chứng

- 18/11/2026, bản sao trên PC (backup giờ 09:00): số đo và `auto_explain` ở các bảng trên; băm, dấu vân và catalog như tiêu chí.
- 18/11/2026 09:52, DB thật trên `hao` (chỉ đọc): bảng thứ hai ở trên. Bằng chứng ngoài Git ở `/srv/v7/backup-20261118-tong-quan-tat-jit/` (quyền 700).
- 18/11/2026 10:13–10:16, bản sao trên `hao`; 10:19, DB thật; 10:21, release `da1708b`: [nhật ký triển khai](../docs/deploys/2026-11-18-tong-quan-tat-jit.md).

## CÒN MỞ

- `get_trip_month` (Báo cáo tháng) đang ở khoảng 95% ngưỡng JIT nhưng chưa bị JIT. Chi phí sẽ vượt ngưỡng khi có thêm khoảng 600–700 dòng chuyến sổ gốc (ví dụ sổ mới tạo từ Sheet) hoặc vài tháng chuyến web. Khi đó cách sửa cũng là một `ALTER FUNCTION … SET jit = off`. Đợt này không làm, vì việc giao chỉ sửa hàm đang thật sự tốn JIT.
- Phần còn lại của `get_dashboard_debt` (khoảng 90 ms trên PC) là phần chạy thật. Chưa cần làm.
