# V7: Đã thu theo ngày thu, còn nợ cộng dồn như Sheet (DA-THU-01)

Trạng thái: ĐÃ CHỐT (người dùng trong chat 28/10/2026, sau khi xem bản xem dữ liệu giả `cong-no-web-handoff/preview/mockups/da-thu-theo-ngay-thu/`).

## Bối cảnh

Sổ khách đặt phiếu thu và ô "Đã thu" ở **kỳ được trừ nợ** (trừ nợ cũ trước). Phiếu 100tr ngày 15/10 trả nợ tháng 8 và 9 hiện ở tháng 8 và 9, tháng 10 "Đã thu" = 0; còn nợ cuối tháng 8, 9 bị sửa lùi. Sheet ghi tiền thu ở tháng có ngày thu nên không đối soát từng tháng được.

## Đầu ra

- `get_ledger` (file chuẩn `v7_backend_functions.sql` + migration `2026-10-28-v7-da-thu-theo-ngay-thu.sql`, `CREATE OR REPLACE`, chạy lại an toàn): mỗi tháng trả
  - `received_vnd` = tổng `receipt.amount_vnd` chưa hủy có `date` trong tháng − cấn trừ đi trong tháng, cộng `source_receipt_vnd` nếu tháng có số Sheet trong mốc đang hiệu lực;
  - `charges_vnd` = `source_charge_vnd` (tháng có số Sheet) hoặc số dư đầu của tháng, cộng chuyến đã xác nhận và điều chỉnh;
  - `end_of_month_vnd` = tổng còn nợ − Σ(phát sinh − đã thu) của các tháng sau; `prior_months_vnd` = `end_of_month_vnd` − phát sinh + đã thu;
  - danh sách tháng thêm tháng của ngày thu phiếu chưa hủy.
- Trang live: phiếu vẽ ở tháng của ngày thu với đủ số tiền; chữ nhỏ "Trừ nợ …" khi phiếu trừ nợ tháng khác hoặc nhiều tháng; dòng Tổng tháng vẽ nguyên số server, bỏ `sheetMonthTotals`.

## Bất biến

- VND nguyên; tháng cuối `end_of_month_vnd` = `total_outstanding_vnd`; mỗi tháng `prior + charges − received = end`.
- Không đổi: phân bổ nợ cũ trước, `receipt_line`, `outstanding_vnd` từng kỳ, `v_outstanding_month`, `v_month_chain`, `get_receivables_matrix/detail`, dashboard, `v7_reconcile_sheet.py` (so `outstanding_vnd` và tổng).
- Không DDL bảng, không ghi tiền, không đổi quyền.

## Tiêu chí nghiệm thu

- [ ] `npm run check` xanh (test trang live: phiếu theo ngày thu, chữ "Trừ nợ", số Tổng tháng vẽ nguyên).
- [ ] Harness PostgreSQL `--strict`: đồng nhất từng tháng, tháng cuối bằng tổng, phiếu tháng sau không đổi còn nợ tháng trước, số Sheet thay số dư đầu; migration áp hai lần, catalog hàm bằng file chuẩn.
- [ ] Không triển khai `hao` trong PR; triển khai theo `docs/v7-deploy-runbook.md` khi người dùng cho phép.

## Hoàn tác

Revert PR; trên DB áp lại định nghĩa `get_ledger` của `2026-10-27-v7-shipper-write-sync.sql` (hàm đọc, không đụng dữ liệu).
