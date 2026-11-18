# Triển khai: Tổng quan không JIT (18/11/2026)

**ĐÃ CHẠY trên `hao` lúc 10:19 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), spec [`hieu-nang-02`](../../specs/hieu-nang-02.md) và [runbook](../v7-deploy-runbook.md#tổng-quan-không-jit-hieu-nang-02--nâng-db-đã-chạy-trên-hao-18112026). Không đổi quy tắc tiền nên không có quyết định mới.

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Phiên MO-SO-NHANH-03 giao việc 18/11/2026 (mục CÒN MỞ "`get_dashboard_debt` cũng bị JIT"); triển khai tay theo `DEPLOY-CLAUDE-01` |
| PR / release | #470, merge `da1708b`; release tay `da1708b` thay cho `094ed0e` |
| CI | 17/17 check của #470 xanh trên head `25841ff`, gồm `postgres-v7-backend` (`--migration-test`, `v7_schema_snapshot.py --check`), `postgres-v7-luoi-an-toan`, grants, p0 |
| Migration | `2026-11-18-v7-tong-quan-tat-jit.sql`, SHA-256 `f8b806c1424d67254b181e033153ee0977e4b3e6fe0f33bc3dd58a00d753e743`, trùng bản trên `main` và bản đã thử |
| Ghi tiền | Không. Chỉ đổi cấu hình của một hàm đọc (`get_dashboard_debt`: `jit=off`) |

## Kết quả

Đo trên DB thật đúng như API gọi: mỗi lần một psql mới dưới `v7_app`, trong giao dịch chỉ đọc. Số đo là giờ của câu `SELECT`, 3 lượt.

| Hàm | Trước (09:52) | Sau (10:21, ngay sau khi API khởi động lại) |
| --- | ---: | ---: |
| `get_dashboard_debt` (Tổng quan, Việc cần làm, huy hiệu menu) | 784–788 ms | 236–249 ms |
| `get_safety_net`, phần sổ 0/8 (máy canh) | 3.626–3.632 ms | 3.031–3.047 ms |
| `get_safety_net`, không so sổ | 2.104–2.111 ms | 1.551–1.555 ms |
| `get_dashboard` | 178–183 ms | 180–193 ms |
| `get_receivables_matrix(2026)` | 135–136 ms | 137–159 ms |
| `get_receivables_detail(104, 11/2026)` | 444–448 ms | 443–452 ms |
| `get_receipt_book(NULL)` | 194–201 ms | 194–196 ms |
| `get_trip_month(11/2026)` | 95–96 ms | 94–98 ms |
| `get_activity(NULL)` | 18–21 ms | 18–20 ms |

- Mỗi lần Tổng quan tính lại, phần SQL nhanh khoảng 3,3 lần. Tính cả tiến trình psql thì từ 870–877 ms còn 324–338 ms.
- Sau khi nâng, `auto_explain` trên DB thật không thấy câu nào bị JIT trong 9 lượt gọi. Trước đó câu chính của `get_dashboard_debt` bị JIT (525 ms, 623 hàm LLVM), kể cả khi `get_safety_net` gọi nó.
- Sáu hàm còn lại không đổi, đúng dự kiến, vì chúng không có câu nào bị JIT từ trước.
- Chưa đo lại GET `/api/v7/dashboard/debt` trên trình duyệt. Ngoài hàm SQL, API chỉ đọc dấu dữ liệu và trả chữ JSON từ bộ nhớ đọc ([HIEU-NANG-01](../../specs/hieu-nang-01.md)).

## Thử trên bản sao (10:13–10:16)

- Dump `webdebit_v7` (660 mục), khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC, `ANALYZE`.
- Migration hai lượt: 132 ms và 91 ms. Băm 94/94 lần gọi trùng (tám hàm đọc với nhiều đối số, `get_safety_net` mọi phần sổ) trước và sau, sau `RESET jit` và sau khi nâng lại.
- Dấu vân dữ liệu trùng. Catalog chỉ đổi cấu hình `get_dashboard_debt`; chủ và quyền giữ nguyên. Checker 9/9. Đã xóa DB thử.
- `get_dashboard_debt` từ 816–867 ms còn 235–236 ms. Vì DB thử đã thu `CONNECT`, phép đo đăng nhập `postgres` rồi hạ quyền về `v7_app`.
- Lượt thử đầu dừng ngay bước dump: thư mục bằng chứng thuộc `root` nên `postgres` không ghi được. Lượt đó chưa tạo DB thử nào. Sau khi đổi chủ thư mục thành `postgres:root` như đợt trước, lượt thứ hai chạy hết.

## DB thật, 10:19

- Không có kết nối nào khác vào `webdebit_v7`, và ngoài khung :05–:15 của máy đối soát.
- Backup toàn phần ngay trước khi áp; `pg_restore --list` đọc được (660 mục).
- Áp với `ON_ERROR_STOP`: 116 ms. Không cần cửa sổ dừng ghi vì chỉ đổi cấu hình của một hàm đọc.
- Dấu vân dữ liệu trùng; băm 94/94 lần gọi trùng. Catalog sau: chỉ `get_dashboard_debt` thêm `jit=off`. Checker 9/9.

## Release

- Release tay `da1708b` lúc 10:21 bằng đúng gói (`git archive`) và script của `Deploy hao`: `/healthz` 200, unit active, `.release-sha` = `da1708b`. Script cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước).
- Lượt `Deploy hao` của `da1708b` (10:22) xanh, bỏ qua vì `hao` đã chạy đúng SHA đó.
- Journal API sau khi khởi động lại không có lỗi, chỉ có cảnh báo cũ về bản xuất chat Zalo.
- Lưới an toàn `--dry-run`: `"ok": true`, không mục nào (so với lượt 10:17). Không cần `--accept`, vì dữ liệu không đổi.

## Rollback

`ALTER FUNCTION sokhach.get_dashboard_debt() RESET jit;` dưới `sokhach_owner` (đã thử trên bản sao: băm vẫn trùng). Release cũ chạy được với DB mới, release mới chạy được với DB cũ.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261118-tong-quan-tat-jit/` trên `hao` (quyền 700). Gồm dump trước khi thử và trước khi nâng kèm sha256, SQL và script đã chạy, dấu vân, băm, catalog, checker, số đo và kết quả `auto_explain`.

## Còn mở

- `get_trip_month` (Báo cáo tháng) đang ở khoảng 95% ngưỡng JIT (chi phí ước tính 94.701 trên `hao`) nhưng chưa bị JIT. Khi vượt ngưỡng, cách sửa cũng là một `ALTER FUNCTION` (mục CÒN MỞ của [HIEU-NANG-02](../../specs/hieu-nang-02.md)).
