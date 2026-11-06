# TINH-HINH-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Thẻ Tình hình của trang khách là **bản đọc để quyết** cho sếp hoặc người quản lý: trong một màn 1280×560 trả lời đủ khách nợ bao nhiêu, có đang trả không, còn đi hàng không, nợ tăng hay giảm. Người xem tự quyết gọi, thúc đòi hay giữ quan hệ; màn không gợi ý việc.

Người dùng chọn phương án A, người xem chính là sếp, và xác nhận cả bốn chỗ vướng. Thay đổi so với bố cục `TinhHinh.dc.html` (2/11/2026):

1. **Bỏ khối Việc tiếp theo.** Từ khi ẩn nhắc nợ ([`NHAC-NO-01`](nhac-no-01.md), 4/11/2026), "Liên hệ khách" chỉ còn nút sang thẻ Trao đổi, nơi không có cách liên hệ, và câu "có nợ quá hạn" chỉ lặp lại thanh đỏ.
2. **Bỏ ba thẻ chỉ số** (Trễ trung bình, Doanh thu, Đi hàng) và việc bấm thẻ để đổi hình. Trễ trung bình trở lại khi có B1 ([`TRANG-KHACH-01`](trang-khach-01.md)).
3. **Thêm dải bốn dữ kiện luôn hiện:** Trả gần nhất, Thu tháng này trên phát sinh, Đi hàng gần nhất, Quá hạn lâu nhất. Nhãn rủi ro thành chữ không bấm, vì dữ kiện tạo ra nhãn đã nằm ngay dưới.
4. **"+N việc cần xem" thành dòng nói rõ:** "Còn nợ chưa tính: 2 chuyến chưa có giá", bấm là tới đúng chỗ trong thẻ Sổ.
5. **Hoạt động thành "Tiền về và hứa trả":** chỉ phiếu thu, khoản thu sổ gốc, hứa trả và báo đã chuyển; hứa trả đang chờ đứng đầu. Bỏ bốn tab lọc và số đếm. Số chuyến xem theo tháng ở bong bóng và dải ghim của hình, chi tiết từng chuyến ở thẻ Sổ.
6. **Một dòng "Số trên web lúc hh:mm"** ở đầu màn. Dòng này chỉ nói lúc đọc số trên web, không khẳng định Sheet mới tới đâu.

Giữ của [`TUONG-TAC-01`](tuong-tac-01.md): bấm Quá hạn, Đến hạn, Chưa đến hạn mở từng tháng tại chỗ; rê tháng hiện số; bấm tháng ghim tại chỗ rồi mới Mở sổ; bấm dòng tiền mở chi tiết. Thay của quyết định đó: thẻ Doanh thu, Đi hàng đổi hình; cột nhỏ Đi hàng ghim tháng; khung dữ kiện của nhãn rủi ro; khung việc cần xem; tab lọc Hoạt động.

Không đổi số tiền, luật rủi ro của [`DASH-03`](dash-03.md), phân bổ hay quyền ghi. Thẻ Trao đổi và Hồ sơ giữ nguyên.

## Ngày / nguồn

6/11/2026, chat. Người dùng gửi ảnh thẻ và nói "tab này thấy chưa hiệu quả trong các thiết kế luồng cho người dùng". Claude đi thử luồng thật trên `hao` (chỉ đọc), đưa hai phương án kèm phác thảo. Người dùng chọn "A. Bản đọc để quyết", "Sếp/quản lý xem nhanh", và chọn cả bốn chỗ vướng: Việc tiếp theo vô ích, phải cuộn và bấm, ba thẻ chỉ số thừa, trùng với thẻ khác.

Số đo lúc chốt (khung 1265×560, sổ nợ lớn nhất): hình bắt đầu ở y=518, dòng Hoạt động đầu tiên ở y=551, nên gần như không có gì của hai khối này trên màn đầu; 206 trên 214 dòng Hoạt động là chuyến; 52 trên 69 sổ đang nợ có quá hạn; cả hệ thống có 1 sổ đã gắn group Zalo; trên `hao` chưa có bản xuất chat.

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng và bố cục. Chỉ đổi trang, không có migration, không ghi tiền. Chi tiết ở [spec trang khách](../../specs/v7-trang-khach.md) và [spec tương tác](../../specs/v7-tuong-tac.md).

CÒN MỞ:
- Sếp tự đi hết luồng trên `hao`.
- Phương án B (bàn làm việc đòi nợ: ghi lần liên hệ, hứa trả, người liên hệ) chưa làm; xét lại khi có người đòi nợ dùng web hằng ngày.
- Thẻ Trao đổi vẫn liệt kê phiếu đã hủy và không có khoản thu sổ gốc, nên danh sách thu của nó khác "Tiền về và hứa trả".

**Cập nhật 6/11/2026:** nhãn mức rủi ro của thẻ đổi thành tên tình trạng theo [`DASH-06`](dash-06.md). Chưa code.
