# Triển khai tay: đọc dòng sổ gốc theo container (4/11/2026)

**ĐÃ CHẠY trên `hao` ngày 4/11/2026 (20:54 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Việc do phiên đo `GET /api/v7/ledger` (#316) tách ra; không đổi quy tắc tiền nên không có quyết định mới.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#317 (`8946881`) |
| Migration | `2026-11-04-v7-index-container.sql` (sha256 `fcfbb4ec…`): thêm hai index biểu thức, `ANALYZE` hai bảng, thay thân `list_legacy_trip_refs`. Không đổi cột, ràng buộc, loại event, dữ liệu hay quyền. |
| Release app | `449ff8f` → `8946881` |
| Ghi tiền | Không. |

## Kết quả

`list_legacy_trip_refs` trên DB thật. Đầu vào là danh sách container đang chờ thật của 113 sổ, mỗi đầu vào 3 lần, mỗi lần một kết nối mới như API; thời gian tính trong server.

| | Trước | Sau |
| --- | ---: | ---: |
| Trung vị | 158 ms | 9,2 ms |
| p90 | 172 ms | 23 ms |
| Lớn nhất | 198 ms | 49 ms |

**JSON của hàm giống hệt:** mã băm trùng 113/113 đầu vào giữa lần đo ngay trước cửa sổ và lần đo sau, không có event mới ở giữa. Hai index đều được dùng (`idx_scan` tăng).

Đọc cả sổ (`get_ledger` + hàng chờ, chưa gồm mạng), quét 238 sổ, 0 lỗi: trung vị 178 ms, p90 341 ms, lớn nhất 2.083 ms. Sau #316 phiên trước đo được trung vị 311 ms, p90 500 ms. Hai lần dùng script khác nhau nên chỉ so được tương đối.

## Trước

- `hao` chạy `449ff8f`. DB `webdebit_v7`: 238 sổ, 9.373 event.
- Phiên "Tối ưu tốc độ tải sổ khách" đang chạy cùng lúc: chỉ đọc và đo, không ghi DB, xác nhận không đụng hàm này.

## Bản sao thử

Dump, restore vào DB tạm trên `hao`. Đã xóa DB tạm và đầu vào trong RAM sau khi thử.

- **Chỉ thêm index thì không có tác dụng:** trung vị vẫn 164 ms, `idx_scan` = 0. Với hash semi join, planner gần như không tính chi phí `_normalize_key` nên vẫn quét tuần tự. Đổi `IN (SELECT ...)` thành `= ANY(mảng)` thì mới dùng index.
- **Chọn index toàn bảng, không dùng `WHERE kind='trip'`:** planner không dùng thống kê của index một phần. Trung vị 9,4 ms so với 14 ms.
- **Migration hai lượt:** 0,7 giây và 0,5 giây. Catalog ổn định giữa hai lượt, dấu vân tay không đổi, checker 9/9 (DB tạm phải bỏ `CONNECT` của `PUBLIC` như DB thật thì checker mới chạy hết).
- **So kết quả:** trùng 113/113 đầu vào thật và 18/18 đầu vào lạ (mọi container của sổ gốc, chữ thường, khoảng trắng, NBSP, chuỗi rỗng, lặp, số không tồn tại, 2.000 phần tử).
- **Restore:** dump DB đã có index restore được sang DB khác, index hợp lệ, kết quả trùng.
- **Rủi ro tìm thấy:** chưa có thống kê thì hàm chậm hơn cả bản cũ (234 ms), kết quả vẫn đúng. `pg_dump` không mang thống kê nên sau restore cần `ANALYZE` hoặc đợi autovacuum; đã ghi vào runbook.

## Cửa sổ dừng ghi (20:54:30–20:54:36 giờ VN)

- Dừng timer `v7-reconcile-auto` và API, không còn kết nối khác, ghi dấu vân tay, dump kèm hash, đọc lại được (637 mục).
- Áp migration với `ON_ERROR_STOP`, một `COMMIT`.
- Dấu vân tay (số dư từng khách, tổng nợ, số dòng các bảng) không đổi. Checker 9/9 OK. Hai index hợp lệ. App gọi được hàm, reader không.
- Bật lại API và timer. API gián đoạn 6 giây; `healthz` 200.

## Đổi release

`git archive 8946881 … | webdebit-release.sh deploy 8946881…` dưới user `webdebit-deploy`. `.release-sha` = `8946881`, `/healthz` 200, không có file do root sở hữu, migration trong release trùng hash bản đã chạy, journal API không có lỗi.

Lệnh đầu tiên hỏng vì tôi truyền thừa ký tự vào `git archive`: gói rỗng, script từ chối, release cũ chạy nguyên, không restart.

Script báo không dọn hết hai release cũ (`4592a2d`, `e4f3a56`) vì có file của user khác. Hai thư mục này có từ trước đợt này.

**Bằng chứng:** thư mục `backup-20261104-index-so-goc` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700). Gồm dump lúc dừng kèm sha256, file SQL, script, dấu vân tay, log áp thật, checker, đầu vào thật và mã băm từng lần đo. Đầu vào có số container nên không chép ra khỏi `hao`.

## Rollback

- App: `webdebit-release.sh deploy 449ff8f82cc1b5e9957b7d8919b5f7a71ddea89c`. Release cũ chạy được với DB mới.
- DB: xem [runbook](../v7-deploy-runbook.md#đọc-dòng-sổ-gốc-theo-container--nâng-db-đang-có-đã-chạy-trên-hao-4112026).

## CÒN MỞ

- `get_ledger` ở sổ lớn: sổ chậm nhất vẫn khoảng 2 giây. Không thuộc đợt này.
- Chi phí ghi của hai index (mỗi dòng sổ gốc mới thêm một lần chạy `_normalize_key`) chưa đo riêng. Dự kiến rất nhỏ so với phần còn lại của lệnh ghi; harness ghi tiền xanh.
