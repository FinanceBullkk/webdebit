# DA-THU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt sổ khách V7 hiện tiền thu **như Sheet** để đối soát từng tháng: (1) phiếu thu nằm ở **tháng của ngày thu**, hiện đủ số tiền một lần (không tách theo kỳ được trừ nợ); phiếu trừ nợ tháng khác hoặc chia nhiều tháng thì có chữ nhỏ "Trừ nợ T8/2026 70.000.000 · T9/2026 30.000.000"; (2) dòng Tổng tháng: **Đã thu** = tổng phiếu chưa hủy có ngày thu trong tháng (trừ cấn trừ đi trong tháng; xóa khoản thu sổ gốc theo [`XOA-THU-GOC-01`](xoa-thu-goc-01.md) làm giảm Đã thu của tháng đó, không tăng phát sinh); tháng có số Sheet trong mốc thì phát sinh/đã thu lấy số Sheet (`source_charge_vnd`/`source_receipt_vnd`) cộng thao tác web; **Còn nợ cộng dồn** = tháng trước + phát sinh − đã thu, tính lùi từ tổng còn nợ nên tháng cuối luôn bằng tổng; "Nợ các tháng trước" = còn nợ cuối tháng trước; (3) **không đổi** cách trừ nợ cũ trước khi ghi/phân bổ lại phiếu, nợ còn lại từng kỳ (`outstanding_vnd`), tuổi nợ, ma trận công nợ theo tháng, tổng quan, đối soát tổng và tổng còn nợ. Thay cách dời số `sheetMonthTotals` của [`SO-GON-01`](so-gon-01.md) (1). Spec: [`specs/v7-da-thu-theo-ngay-thu.md`](../../specs/v7-da-thu-theo-ngay-thu.md); bản xem dữ liệu giả [`preview/mockups/da-thu-theo-ngay-thu`](../../cong-no-web-handoff/preview/mockups/da-thu-theo-ngay-thu/index.html).

## Ngày / nguồn

28/10/2026, góp ý trong chat ("hiện tại thì khó để đối soát với sheet"), duyệt bản xem ("Ổn, sửa thật")

## Hiệu lực và giới hạn

ĐÃ CHỐT. ĐÃ CODE: `get_ledger` (file chuẩn + migration `2026-10-28-v7-da-thu-theo-ngay-thu.sql`, chỉ đổi hàm đọc), trang live. ĐÃ KIỂM CHỨNG bằng `npm run check` và harness PostgreSQL dùng một lần (xem PR). **ĐÃ TRIỂN KHAI trên `hao` 28/10/2026** (người dùng: "Chạy triển khai thật"): migration trên `webdebit_v7` và release app `c407664`, API dừng khoảng 12 giây; số dư 236/236 khách và số dòng mọi bảng không đổi, mỗi sổ đúng đẳng thức tháng (0/236 lệch), checker 9/9 OK trước/sau trên bản sao và sau release; chi tiết ở [runbook](../v7-deploy-runbook.md#đã-thu-theo-ngày-thu--nâng-db-đang-có-đã-chạy-trên-hao-28102026). Chưa thử tay trên web sau triển khai. CÒN MỞ: trang mẫu fixture `so-khach-v7.html` vẫn vẽ phiếu theo kỳ trừ nợ.
