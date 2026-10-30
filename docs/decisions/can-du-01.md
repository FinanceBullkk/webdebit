# CAN-DU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt trình bày nợ còn lại từng tháng **theo chuẩn tuổi nợ**: trong cùng một khách, khoản dư của tháng âm (khách trả trước, số dư đầu âm, điều chỉnh âm, trả dư) **cấn vào tháng còn nợ cũ nhất trước**, như một khoản thu. Sau khi cấn, mỗi tháng chỉ còn nợ dương thật sự treo; một khách không đồng thời có tháng "dư" và tháng "nợ". Cấn hết nợ mà vẫn dư thì phần dư là **khách trả trước**, nằm ở **tháng cuối** của sổ (cùng chỗ khoản trả dư `advance` theo `V7-SO`). Áp cho mọi chỗ đọc nợ còn lại từng tháng: danh sách tháng trong sổ khách, ma trận Công nợ theo tháng và ngăn kéo, tổng quan/tuổi nợ, tháng nợ cũ nhất.

**Không đổi:** tổng còn nợ mỗi khách; "Còn nợ cuối tháng" (chuỗi cộng dồn như Sheet, `DA-THU-01`); cách ghi và phân bổ lại dòng phân bổ phiếu thu (`V7-SO`: theo ngày phiếu rồi mã phiếu, chỉ trừ tháng có nợ dương); số dư đầu, dữ liệu và Lịch sử. Thay vế "bỏ qua tháng âm" của [`V7-BE`](v7-be.md) (6) ở **số nợ từng tháng**; vế "giữ số âm nguyên trong sổ" vẫn đúng với dữ liệu gốc (view thô `v_outstanding_month_raw`).

## Ngày / nguồn

30/10/2026, trong chat: người dùng thấy danh sách tháng của một khách hiện một tháng cũ "dư" cạnh các tháng sau vẫn còn nợ đủ, hỏi cách biểu diễn chuẩn kế toán/công nợ, rồi chốt "ok làm theo chuẩn".

## Hiệu lực và giới hạn

ĐÃ CHỐT. ĐÃ CODE: view `v_outstanding_month` (cấn khoản dư) trên view thô `v_outstanding_month_raw`, `record_receipt` xếp tạm theo số thô, `get_receivables_detail` thêm `credit_applied_vnd`, ngăn kéo ma trận hiện dòng khoản dư; file chuẩn và migration `2026-10-30-v7-can-du.sql` (chỉ đổi view đọc và hai hàm). Spec: [`specs/v7-can-du.md`](../../specs/v7-can-du.md). ĐÃ TRIỂN KHAI trên `hao` 30/10/2026 (release `f0bd7df`; bản thử và DB thật khớp tổng từng khách, 21/236 khách có kỳ đổi số nợ): [nhật ký](../deploys/2026-10-30-can-du.md). Chưa thử tay trên web. CÒN MỞ: cột "Trả trước" riêng trên ma trận (hiện phần trả trước nằm ở tháng cuối, ô ghi "dư"); giữ tiền ứng trước cho đúng một chuyến/hợp đồng (chưa có, mặc định vẫn cấn cũ trước); trang mẫu fixture `so-khach-v7.html` vẫn theo cách cũ.
