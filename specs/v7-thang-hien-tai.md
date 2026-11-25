# GET sổ luôn có dòng tháng hiện tại (SK-C1)

Trạng thái: ĐÃ CHỐT. Người dùng bảo làm theo hướng ĐỀ XUẤT của [audit Sổ khách 25/11/2026](../docs/ux-audit-so-khach-2026-11-25.md) mục SK-C1 (25/11/2026, qua phiên điều phối, đợt 2). Phạm vi: hàm đọc `sokhach.get_ledger` và thẻ tháng của Sổ khách. Không đổi luật tiền, phân bổ, khóa tháng, bảng, view, quyền, hàm ghi hay dữ liệu.

## Người dùng và luồng

Người nhập mở Sổ khách của một sổ còn nợ mà tháng hiện tại (giờ VN) chưa có chuyến, phiếu hay dòng sổ gốc nào, rồi bấm "+ Ghi phiếu thu". Trước bản này thẻ tháng hiện tại in "Nợ đầu tháng –" và "Còn nợ cuối tháng –" (sổ 10 và 68 trên `hao` ngày 25/11/2026): số đã biết hiện như chưa biết, đúng lúc người dùng sắp gõ tiền. Thẻ Sổ không còn chỗ nào khác cho thấy nợ hôm nay (thiết kế 2/11 bỏ dòng "Khách còn nợ" ở đầu sổ).

## Nguyên nhân

`get_ledger` dựng `months` từ tập tháng có số dư theo kỳ (`v_outstanding_month`), có chuyến web hoặc có phiếu thu chưa hủy. Tháng hiện tại chưa có gì thì không có dòng; trang tự thêm chip giữ chỗ (`placeholder`) cho tháng hiện tại nhưng không có `prior_months_vnd`, `end_of_month_vnd`. Theo [`SO-GON-05`](../docs/decisions/so-gon-05.md) (3) số của thẻ tháng lấy nguyên từ GET, trang không tự tính, nên sửa ở GET.

## Đầu ra

- `get_ledger` (sổ `active`) luôn có một dòng `months` cho tháng hiện tại theo giờ VN (`date_trunc('month', clock_timestamp() AT TIME ZONE 'Asia/Ho_Chi_Minh')`, cùng cách tính `today_month`). Tháng đó chưa có gì thì dòng là:
  - `charges_vnd` = 0, `received_vnd` = 0, `outstanding_vnd` = 0;
  - `end_of_month_vnd` theo cùng phép cộng dồn tính lùi như mọi tháng, nên bằng còn nợ cuối của tháng liền trước có dòng (và bằng `total_outstanding_vnd` khi không có tháng nào sau tháng hiện tại);
  - `prior_months_vnd` = `end_of_month_vnd` − 0 + 0.
- Tháng hiện tại đã có dòng: không thêm dòng thứ hai (`UNION`), số không đổi.
- Sổ `NO_BASELINE` vẫn trả `months` rỗng.
- Thẻ tháng hiện tại của Sổ khách in hai số đó thay "–". Tháng mở sẵn không đổi: dòng toàn 0 không tính là "có số liệu" (`hasRows` của `so-khach-v7-month-ui.js`), nên `SO-GON-05` (2) giữ nguyên.

## Không đổi

- `total_outstanding_vnd` = tổng `outstanding_vnd`; dòng thêm có `outstanding_vnd` 0 nên tổng không đổi.
- Số của mọi tháng khác: dòng thêm góp 0 vào phép cộng dồn.
- Phân bổ, tuổi nợ, đối soát, Tổng quan (không đọc `months` của `get_ledger`).
- Bản xuất cả sổ có thêm một dòng tab THÁNG cho tháng hiện tại (số như trên); phép kiểm 5 của bản xuất đọc cùng `get_ledger` nên vẫn khớp. Máy kiểm `v7_book_export_check.py` (tổng `outstanding_vnd` và tháng cuối bằng tổng) vẫn đúng.

## Tiêu chí xong

1. Harness PostgreSQL có ca `SK-C1`: sổ có nợ ở tháng cũ, tháng hiện tại không có dòng → dòng cuối của `months` là tháng hiện tại, Phát sinh 0, Khách trả 0, Nợ đầu tháng = Còn nợ cuối tháng = Còn nợ cuối tháng của tháng có dòng gần nhất = `total_outstanding_vnd`; `total_outstanding_vnd` và các dòng tháng cũ trùng với trước khi thêm. Ghi một phiếu vào tháng hiện tại → vẫn đúng một dòng tháng hiện tại.
2. `--migration-test` xanh với migration `2026-11-25-v7-thang-hien-tai.sql` trong chuỗi; file đọc định nghĩa và bảng băm sinh lại.
3. Test JS: thẻ tháng hiện tại có Nợ đầu tháng và Còn nợ cuối tháng từ GET, không còn "–".
4. Trên `hao` sau triển khai: tổng từng khách trước/sau trùng; sổ 10 (chỉ xem) có Nợ đầu tháng ở tháng hiện tại bằng tổng còn nợ.

## Triển khai

Migration chỉ `CREATE OR REPLACE FUNCTION sokhach.get_ledger` (giữ `SET jit = off`, chủ, quyền). Không tăng `schema_level`. Chạy lại được. Theo [runbook](../docs/v7-deploy-runbook.md) mục "Tháng hiện tại luôn có dòng trong GET sổ (SK-C1)".
