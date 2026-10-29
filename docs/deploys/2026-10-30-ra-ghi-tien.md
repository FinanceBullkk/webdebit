# Triển khai tay: rà đường ghi tiền V7 (30/10/2026)

**ĐÃ CHẠY trên `hao` ngày 30/10/2026 (06:45–06:50 giờ VN)**. Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md); người dùng bấm "Triển khai hao" trong chat sau khi PR merge. Lượt `Deploy hao` của `485f634` đỏ ở cổng SQL là chủ ý (diff có migration, `v7_backend_functions.sql`, checker).

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#189 (`485f634`) |
| Quyết định | [`FUTURE-01`](../decisions/future-01.md) (áp vào V7), [`V7-SO`](../decisions/v7-so.md) (phiếu mới cũng phân bổ lại), [`BANG-GIA-01`](../decisions/bang-gia-01.md) (server giữ giá gõ tay) |
| Migration | `2026-10-29-v7-ra-ghi-tien.sql`: chỉ `CREATE OR REPLACE` sáu hàm + tạo lại trigger `trip_sheet_cross_customer`; không đổi bảng, ràng buộc, loại event, dữ liệu. Chạy sau `matrix-drawer-receipts`; `tong-quan-quan-ly-no` (DASH-03) đã có trên `hao` từ trước, độc lập. |
| Release app | `5f04bc4` → `485f634` (CI `main` 12/12 xanh đúng SHA) |
| Ghi tiền | Không ghi. Đổi luật ba hàm ghi: `paste_trips` chặn ngày xe nhập kho sau hôm nay giờ VN (`FUTURE_DATE`); `record_receipt` phân bổ lại phiếu chưa hủy theo (ngày, mã phiếu) ngay khi ghi; `apply_price_table` không ghi đè đơn giá gõ tay (`PRICE_TYPED_PRICE`, API trả 409). Ba hàm Sheet (`list_sheet_trip_refs`, `guard_sheet_cross_customer`, `resolve_sheet_conflict`) thân không đổi so với bản đang có. |

## Trước

`hao` chạy `5f04bc4`; migration DASH-03 đã áp (có `get_dashboard_debt`). Ba hàm ghi còn thân cũ: không có `FUTURE_DATE` trong `paste_trips`, `record_receipt` chỉ `_check_allocations`, `apply_price_table` không có `PRICE_TYPED_PRICE`. DB `webdebit_v7` 35 MB, 236 khách, 877 kỳ mở đầu; đĩa `/srv` còn 373 GB.

## Bản sao thử

- Dump `webdebit_v7` đang chạy (1,6 MB, `pg_restore --list` 569 mục), hash lưu cạnh dump.
- Restore vào DB thử (thu hồi CONNECT của PUBLIC). Dấu vân tay (`md5` của `v_outstanding_month`, `v_trip_current`, `v_adjustment_current`, `v_receipt_line_active`), số dư 236 khách và số dòng 30 bảng của DB thử khớp DB thật.
- Chạy migration hai lượt qua stdin (thư mục bằng chứng 700 của root nên `postgres` không đọc file trực tiếp). `md5` toàn bộ `pg_get_functiondef` + trigger của lược đồ `sokhach` sau lượt 1 và lượt 2 trùng nhau: chạy lại được.
- Sau migration: dấu vân tay, số dư, số dòng không đổi; ba hàm có logic mới; trigger có; role app EXECUTE được `resolve_sheet_conflict`, `list_sheet_trip_refs`, không EXECUTE hàm trigger.
- `v7_post_deploy_check.sql` 9/9 OK trên DB thử. Đã xóa DB thử.

Hai lần chạy đầu dừng trước khi đụng DB thử: lần một vì shell thường không mở được thư mục 700 của root (chmod glob), lần hai vì SIGPIPE khi đếm mục `pg_restore --list` dưới `pipefail`. Cả hai chỉ đọc DB thật.

## Cửa sổ dừng ghi (06:49:18–06:49:23 giờ VN)

- Dừng `v7-ledger-api.service`. Đo lại dấu vân tay/số dư/số dòng: bằng bản trước. Dump lần hai và hash.
- Áp migration một transaction: 0,14 giây, một `COMMIT`. `md5` catalog sau áp trùng với bản thử. Dấu vân tay, số dư 236/236 khách, số dòng không đổi. Checker 9/9 OK.
- Bật lại API: `active`, loopback 403 (sống). API gián đoạn 5 giây.

## Đổi release

- `git archive 485f634 … | webdebit-release.sh deploy` dưới user deploy (06:49:37 giờ VN; script tự restart và kiểm sống). `.release-sha` = `485f634`; không còn file do root sở hữu trong `RELEASES_DIR`.
- Hash `migrations/2026-10-29-v7-ra-ghi-tien.sql`, `v7_backend_functions.sql`, `v7_ledger_api.py` trong release trùng bản `main` ở máy; API có mã lỗi `PRICE_TYPED_PRICE`.

## Sau

- Số dư 236 khách sau đổi release bằng sau migration; `md5` của `v_outstanding_month` giữ nguyên suốt đợt. Checker chạy từ file trong release 9/9 OK.
- Journal API chỉ có dừng/khởi động theo đúng hai mốc trên, không lỗi.
- DB thật hiện có 5 phiếu thu nhưng 0 dòng phân bổ hiệu lực (`v_receipt_line_active`), nên phân bổ lại khi ghi phiếu chưa có gì để chạy trên dữ liệu đang có; lần ghi phiếu web đầu tiên trên một sổ có phiếu lệch thứ tự ngày sẽ sinh event `reallocation` như runbook nêu.
- **Bằng chứng:** thư mục `backup-20261030-ra-ghi-tien` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700): dump trước và dump lúc dừng kèm sha256, sha256 migration và checker, dấu vân tay/số dư/số dòng mỗi mốc, log áp migration thử và thật, kết quả checker thử/thật/sau release.

## Rollback

- App: trỏ `CURRENT_LINK` về release `5f04bc4` rồi restart. Release cũ chạy được với hàm mới (chỉ không dịch mã lỗi `PRICE_TYPED_PRICE` thành câu tiếng Việt).
- DB: hàm không đổi dữ liệu nên để nguyên được. Muốn quay lại thân cũ thì áp lại ba hàm từ migration liền trước theo runbook mục "Rà đường ghi tiền 29/10", hoặc restore `v7-stopped.dump` vào DB mới (quy trình M2-11).

## CÒN MỞ

- Chưa thử tay trên web ba luồng mới (dán chuyến ngày mai bị chặn, ghi phiếu lệch thứ tự ngày, áp bảng giá lên chuyến đã gõ tay): chỉ có harness dữ liệu giả và kiểm catalog trên `hao`. Không tạo giao dịch thật trên sổ để thử.
- Các điểm P2/P3 còn lại của đợt rà (`PRICE-ZERO` đơn giá 0đ, `OFFSET_SOURCE_ARCHIVED`, xóa trống đơn giá dòng sổ gốc) chờ người dùng chốt, chưa đổi code.
