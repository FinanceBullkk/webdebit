# Mở sổ lớn nhanh hơn: `get_ledger` chạy với JIT tắt (MO-SO-NHANH-03)

Trạng thái: ĐÃ CHỐT. Việc do phiên lưới an toàn giao ngày 18/11/2026 (mục CÒN MỞ "Sổ 104 mở chậm" trong [nhật ký LUOI-AN-TOAN-01](../docs/deploys/2026-11-18-luoi-an-toan.md)); Claude chọn cách làm theo [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md). Phạm vi: cấu hình của một hàm đọc là `get_ledger`. Không đổi thân hàm, luật tiền, bảng, view, dữ liệu, quyền hay giao diện. ĐÃ TRIỂN KHAI trên `hao` 18/11/2026 lúc 08:55, bản `6b93a4e`, [nhật ký](../docs/deploys/2026-11-18-mo-so-tat-jit.md).

Tiếp [MO-SO-NHANH-02](mo-so-nhanh-02.md) (phần "bước 3: thời gian SQL `get_ledger` sổ lớn") và [HIEU-NANG-01](hieu-nang-01.md) (bộ nhớ đọc theo dấu dữ liệu: chỉ tính lại sau mỗi lệnh ghi).

## Người dùng và luồng

Người nhập mở Sổ khách của một sổ lớn (104, 79, 149…) và chờ bảng hiện. Trang gọi `GET /api/v7/ledger`; API chạy `get_ledger` (qua bộ nhớ đọc, chỉ tính lại khi dữ liệu đã đổi) rồi chiếu hàng chờ Sheet/PS. Hàm này còn chạy ở hộp Việc cần làm (API vừa khởi động thì tính lại mọi sổ), máy canh (lưới an toàn, mỗi 15 phút 1/8 số sổ), backup (tổng từng sổ) và máy đối soát. Không đổi gì ở màn hình.

## Số đo trước khi làm

- `hao`, 18/11/2026 khoảng 06:40 (phiên lưới an toàn, chỉ đọc): `get_ledger(104)` mất 8,3 giây lúc API vừa khởi động lại và đang tính lại hộp việc; cả 242 sổ mất 22,6 giây lúc đó, 10,9 giây trên bản sao lúc máy rảnh.
- Bản sao trên PC, khôi phục từ bản backup mỗi giờ lúc 08:00 ngày 18/11 (khớp manifest: 34 bảng, 242 sổ), dùng image PostgreSQL 18.6 của harness và cấu hình JIT mặc định giống `hao` (`jit=on`, `jit_above_cost` 100.000, `jit_inline_above_cost` và `jit_optimize_above_cost` 500.000), `ANALYZE` sau khôi phục:

| Sổ | `get_ledger` hôm nay | JIT tắt | Thân JSON |
| --- | ---: | ---: | ---: |
| 104 | 3.114 ms | 135 ms | 1,30 MB |
| 79 | 1.005 ms | 205 ms | 1,50 MB |
| 149 | 313 ms | 139 ms | 0,99 MB |
| 80 | 168 ms | 133 ms | 1,17 MB |
| 155 | 167 ms | 166 ms | 1,39 MB |
| Cả 242 sổ | 9,1 giây | 5,1 giây | |

Sổ 155 có thân JSON lớn hơn sổ 104 mà chỉ mất 167 ms, nên độ lớn của sổ không giải thích được độ chậm.

- Bản sao trên `hao` (dump `webdebit_v7` lúc 08:36 ngày 18/11, khôi phục vào DB thử): mỗi sổ đo trong một phiên psql mới, như API gọi.

| Sổ | Hôm nay (lần 1, lần 2) | JIT tắt (lần 1, 2, 3) |
| --- | ---: | ---: |
| 104 | 8.876 ms, 8.737 ms | 431, 382, 366 ms |
| 79 | 1.108 ms, 1.097 ms | 611, 599, 582 ms |
| 149 | 872 ms, 376 ms | 368, 370, 349 ms |

## Nguyên nhân

Bật `auto_explain` (`log_nested_statements`, `log_analyze`, `log_buffers`) rồi gọi `get_ledger(104)` trên bản sao:

- Câu dựng `months` (các CTE `month_keys`, `figures`, `chain`) chiếm 2.975 ms trong tổng 3.164 ms. Riêng **JIT** đã mất 2.974 ms: 592 hàm, Generation 35 ms, Inlining 74 ms, Optimization 1.631 ms, Emission 1.234 ms. Phần chạy thật chỉ khoảng 10 ms, toàn bộ 18.517 buffer đều trúng bộ đệm, không đọc đĩa.
- Kế hoạch của câu này có chi phí ước tính 797.122, vượt `jit_above_cost` và cả hai ngưỡng 500.000, nên PostgreSQL biên dịch LLVM có inline và tối ưu đầy đủ. Ước tính bị phồng vì `month_keys` được đoán 188 dòng (thật có 10). Mỗi dòng lại kéo các truy vấn con tương quan qua view (`v_outstanding_month` khoảng 800 đơn vị chi phí mỗi lần, `v_adjustment_current` khoảng 580), cộng thêm hai cửa sổ (`sum() OVER ()` và khung `1 FOLLOWING … UNBOUNDED FOLLOWING`) tính biểu thức theo từng khung. Sổ 104 có nhiều dòng điều chỉnh nhất (160) nên vượt ngưỡng tối ưu. Sổ 79 và 149 vượt ngưỡng JIT ở mức thấp hơn.
- Lần mở sổ nào cũng chịu JIT, vì API chạy mỗi lượt đọc bằng một psql mới. plpgsql giữ kế hoạch theo từng phiên: 5 lần gọi đầu dùng kế hoạch riêng theo mã sổ (chi phí phồng, bị JIT), từ lần thứ 6 mới chuyển sang kế hoạch chung (ước tính dưới ngưỡng, không JIT). Trên bản sao ở PC, gọi sổ 104 tám lần trong một phiên: lần 1–5 khoảng 3,1 giây, lần 6–8 khoảng 130 ms; ép kế hoạch riêng (`plan_cache_mode = force_custom_plan`) thì lần 6–8 vẫn 3,2 giây. Vì vậy đo "cả 242 sổ trong một phiên" (10,9 giây ở phiên lưới an toàn, 9,5 giây trên bản sao ở `hao`) gần như không thấy JIT, còn mỗi lần người dùng mở sổ 104 thì mất 8–9 giây trên `hao`.
- `hao` chậm hơn PC khoảng 3 lần ở phần biên dịch: biên dịch LLVM chỉ tốn CPU, và `hao` là laptop cũ 4 lõi. Lúc API vừa khởi động lại, hộp việc tính lại mọi sổ cùng lúc (mỗi sổ một psql mới), nên các sổ lớn cùng biên dịch một lúc.
- Giả thuyết ban đầu không đúng. Khi JIT tắt, dựng `events` (`_ledger_events`) khoảng 14 ms, dòng sổ gốc (`_legacy_current` cho từng dòng) khoảng 80 ms, các truy vấn con theo tháng trong `figures` khoảng 35 ms. Không phần nào gây ra 3–8 giây. Phải giữ `events` trong `get_ledger`, vì phép chiếu Sheet đọc `sheet_conflict_resolved` ([MO-SO-NHANH-02](mo-so-nhanh-02.md)); API chỉ cắt `events` khỏi thân trả về sau khi chiếu xong.
- `get_dashboard_debt` cũng bị JIT: trên bản sao 358 ms, tắt JIT còn 86 ms. Việc này nằm ngoài phạm vi spec (xem CÒN MỞ).

## Đầu ra

- `get_ledger` khai báo `SET jit = off` cạnh `SET search_path` (trong `tools/v7_backend_functions.sql` và bản chép ở `specs/v7-backend/schema-draft.sql`). Mọi câu trong hàm, kể cả câu trong các hàm con nó gọi, được lập kế hoạch không JIT, bất kể cấu hình của phiên hay của cụm.
- Migration `tools/migrations/2026-11-18-v7-mo-so-tat-jit.sql`: `ALTER FUNCTION sokhach.get_ledger(bigint) SET jit = off;` dưới `sokhach_owner`, chạy lại được.
- Không đổi `postgresql.conf`, cấu hình role hay DB. Các hàm khác vẫn theo cấu hình cụm.
- Trên bản sao ở `hao`: sổ 104 từ khoảng 8,8 giây còn khoảng 0,4 giây mỗi lần mở; sổ 79 từ 1,1 còn 0,6 giây. Hộp việc và máy canh gọi từng sổ bằng psql riêng nên cũng nhẹ đi như vậy.

## Hành vi và bất biến

- Kết quả `get_ledger` trùng từng byte trước và sau ở mọi sổ (băm JSON). JIT chỉ đổi cách chạy, không đổi kết quả.
- Không đổi thân hàm, chủ, ACL, `SECURITY DEFINER`, `search_path`.
- Chạy lại `2026-11-04-v7-ledger-events.sql`, hay migration cũ hơn có `CREATE OR REPLACE` cho `get_ledger`, sẽ xóa cấu hình hàm, nên phải chạy lại file này (ghi ở đầu file và trong runbook). Harness `--migration-test` làm đúng thứ tự đó.
- Thứ tự với release: độc lập. Release cũ và mới gọi cùng một hàm.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_fee_sql_sync.py`: `get_ledger` chuẩn trùng bản trong schema-draft; bằng bản MO-SO-NHANH-02 cộng đúng một mệnh đề `SET jit = off`; migration chỉ gồm `ALTER FUNCTION` trong một giao dịch.
- [x] Harness case `MO-SO-NHANH.03`: `proconfig` là `search_path` + `jit=off`; khi phiên ép JIT cho mọi câu (`jit_above_cost = 0`), `auto_explain` thấy chỉ câu SELECT ngoài cùng có JIT, không câu nào lồng trong `get_ledger` có. Bỏ cấu hình thì cả 269 câu lồng của một sổ thật bị JIT (đã thử ngược trên bản sao ở PC).
- [x] `test_pg_v7_backend.py --migration-test`: chuỗi nâng có file mới, chạy lại sau `ledger-events` (và trong case phí, nơi chạy lại migration cũ trên DB chung); catalog hàm trùng bản khởi tạo mới. Chuỗi trong harness locks/price có file mới. `test_pg_v7_luoi_an_toan.py` xanh. `npm run check` xanh, `node scripts/check-secrets.js` sạch.
- [x] Bản sao trên `hao`: băm `get_ledger` 242/242 sổ trùng trước và sau khi chạy migration hai lượt (98 ms, 91 ms), sau hoàn tác rồi nâng lại; dấu vân dữ liệu trùng; catalog chỉ đổi cấu hình `get_ledger` (chủ, quyền giữ nguyên); checker 9/9; DB thử đã xóa. Số đo ở bảng trên.
- [x] DB thật: backup và kiểm đọc lại, áp với `ON_ERROR_STOP`, dấu vân và băm trước/sau, checker; đo lại sổ 104; lưới an toàn `--dry-run` không báo. Sổ 104 (mỗi lần một psql mới như API) từ 8.520–8.550 ms còn 534–549 ms ([nhật ký](../docs/deploys/2026-11-18-mo-so-tat-jit.md)).

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`)
- Review: opus (đụng hàm đọc tiền chính, dù không đổi thân)
- Được sửa: `cong-no-web-handoff/tools/v7_backend_functions.sql`, `specs/v7-backend/schema-draft.sql`, `cong-no-web-handoff/tools/migrations/2026-11-18-v7-mo-so-tat-jit.sql`, `cong-no-web-handoff/tests/test_v7_fee_sql_sync.py`, `cong-no-web-handoff/tools/test_pg_v7_backend.py`, `test_pg_v7_backend_ledger_events.py`, `test_pg_v7_backend_locks.py`, `test_pg_v7_backend_price.py`, `docs/v7-deploy-runbook.md`, `docs/deploys/2026-11-18-mo-so-tat-jit.md`, `docs/deploys/2026-11-18-luoi-an-toan.md` (trỏ mục CÒN MỞ), spec này
- Cấm: đổi thân `get_ledger`, đổi cấu hình cụm/role/DB, tắt JIT cho hàm khác trong đợt này.

## Hoàn tác

`ALTER FUNCTION sokhach.get_ledger(bigint) RESET jit;` dưới `sokhach_owner`. Kết quả không đổi, chỉ chậm lại như trước. Revert PR để bỏ khỏi file chuẩn.

## Bằng chứng

- 18/11/2026, bản sao trên PC (backup giờ 08:00): số đo ở bảng trên; `auto_explain` như mục Nguyên nhân. Đặt `SET jit = off` trên hàm cho băm `get_ledger` trùng 242/242 sổ so với trước.
- 18/11/2026, harness ở máy: `test_pg_v7_backend.py --migration-test` 82 đạt, 2 bỏ qua (7.11c, 7.15c, mục mở từ trước); `test_pg_v7_luoi_an_toan.py` đạt. `npm run check`: mọi bước xanh trừ ruff, vì ruff 0.16.3 trên PATH máy này báo I001 ở file không sửa; chạy bằng bản ghim của CI (`uvx ruff@0.17.3 check .`) thì sạch.
- 18/11/2026 08:36–08:39, bản sao trên `hao`: như tiêu chí ở trên; bằng chứng ngoài Git ở `/srv/v7/backup-20261118-mo-so-tat-jit/` (quyền 700).
- 18/11/2026 08:55, DB thật và release `6b93a4e`: [nhật ký triển khai](../docs/deploys/2026-11-18-mo-so-tat-jit.md).

## CÒN MỞ

- `get_dashboard_debt` (Tổng quan, Việc cần làm, huy hiệu menu) cũng tốn thời gian chủ yếu cho JIT (bản sao: 358 ms, tắt JIT còn 86 ms). Đã đo tám hàm đọc nặng ở [HIEU-NANG-02](hieu-nang-02.md): chỉ `get_dashboard_debt` có câu bị JIT (`get_safety_net` chịu JIT qua lần gọi hàm này), nên chỉ tắt JIT trong `get_dashboard_debt`, không đổi cấu hình DB.
- 135 ms còn lại của sổ 104: dòng sổ gốc khoảng 60%, bảng tháng khoảng 30%. Chưa cần làm.
