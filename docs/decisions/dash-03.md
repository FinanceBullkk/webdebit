# DASH-03

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan chỉ phục vụ một mục tiêu: bức tranh công nợ. Còn bốn khối: **Còn phải thu** (kèm đã thu/phát sinh tháng này, số khách rủi ro cao; ghi rõ chưa tính chuyến thiếu đơn giá và tiền khách đang dư), **Nợ theo hạn trả**, **Khách cần đòi trước** (xếp theo tiền quá hạn, nhãn rủi ro và một câu lý do), **Phân loại khách đang nợ** (theo mức rủi ro, lần trả gần nhất, lần đi hàng gần nhất, quy mô, mặt hàng). "Việc cần làm" và "Hôm nay" chuyển sang tab riêng **Việc cần làm** có số đếm trên thanh điều hướng. Quy tắc (người dùng chọn mặc định của đề xuất):

1. **Hạn trả:** nợ tháng M đến hạn cuối tháng M+1, một quy tắc chung cho mọi sổ. Nhóm theo tháng nợ (giờ VN): chưa đến hạn · đến hạn cuối tháng này · quá hạn 1–2 tháng · 3–6 tháng · trên 6 tháng.
2. **Rủi ro cao** = có nợ quá hạn và ít nhất một: quá hạn từ 3 tháng, hơn 60 ngày chưa trả (hoặc chưa trả lần nào), hơn 90 ngày không đi hàng (hoặc chưa có chuyến). Có nợ quá hạn còn lại là **theo dõi**; không có nợ quá hạn là **trong hạn**. Chỉ tô màu và lọc, không chặn thao tác.
3. **Lần trả gần nhất** tính cả phiếu cấn trừ (sổ đó đã được trừ nợ) và dòng thu sổ gốc chưa xóa; dòng không có ngày lấy cuối tháng của dòng.
4. **Đã thu / phát sinh tháng này** đúng như dòng Tổng tháng của sổ khách ([`DA-THU-01`](da-thu-01.md)) cộng qua mọi sổ; chỉ số của tháng hiện tại, không so tháng trước.

Giữ các điểm tương tác đã chốt ở [`DASH-01`](dash-01.md) ngày 29/10/2026: bấm nhóm để lọc danh sách khách tại chỗ, bấm khách mở ngăn kéo, soi sâu ở Công nợ theo tháng. Spec: [`specs/v7-tong-quan-quan-ly-no.md`](../../specs/v7-tong-quan-quan-ly-no.md).

## Ngày / nguồn

29/10/2026, người dùng góp ý Tổng quan trong chat ("các thông tin trên cùng một tab nên nhất quán và phục vụ chung một mục tiêu"), xem bản xem dữ liệu giả rồi chọn "Duyệt, dùng mặc định".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thay nội dung sáu khối của `DASH-01` (tương tác giữ nguyên). Chưa có hạn trả riêng từng khách, hạn mức nợ, gộp nhiều sổ của một công ty — không có dữ liệu, để sau. Trạng thái triển khai ghi theo lượt `Deploy hao` và nhật ký trong [`docs/deploys/`](../deploys/README.md).
