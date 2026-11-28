# KHACH-THANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan xem được **theo tháng**: chọn một tháng thì thấy tháng đó có những khách nào và tiền của từng khách. Người dùng chốt 28/11/2026 (chọn qua câu hỏi trong phiên):

1. Nội dung là **tiền theo khách**: phát sinh, đã thu, còn nợ của tháng (không thêm số cont; số cont theo tháng đã có ở [Báo cáo tháng](bao-cao-thang-01.md)).
2. **Tháng là một bộ lọc của cả trang**, như hạn trả, mức rủi ro, mặt hàng, khách mới (người dùng chọn cùng ngày, thay bố cục khối riêng cuối trang đã làm trước đó: "để riêng ở dưới không hợp lý, mình muốn nó hoạt động qua bộ lọc"). Bộ chọn tháng nằm trên **thanh đầu trang**, cạnh tên trang (audit cùng ngày, người dùng chọn: hai nút ‹ › không chữ trong thẻ Thu tháng khó thấy và trông như chỉ đổi thẻ đó). Nút có chữ "Tất cả tháng" / "Tháng 10/2026" mở bảng 12 tháng của một năm để chọn thẳng; ‹ › hai bên lùi/tiến một tháng; × bỏ lọc; đang lọc thì nút tô màu nhấn. Chọn tháng thì:
   - thẻ Thu tháng ra đã thu / phát sinh của tháng đó;
   - dải Còn phải thu và khối Công nợ theo mặt hàng chỉ tính sổ có số trong tháng đó;
   - bảng khách chỉ còn các sổ đó, cột thanh Theo hạn trả đổi thành Phát sinh · Đã thu · Còn nợ của tháng;
   - các lọc khác lọc chồng lên; chip "T10/2026 ×" ở hàng chip để bỏ.

Claude chọn phần cách làm (ĐỀ XUẤT, trong phạm vi trên):

- Sổ "có số trong tháng" là sổ đang hoạt động có phát sinh, đã thu hoặc còn nợ khác 0 ở tháng đó. Phát sinh và đã thu tính như dòng Tổng tháng của Sổ khách ([`DA-THU-01`](da-thu-01.md)), cùng phép với thẻ Thu tháng; còn nợ của tháng là phần phát sinh của tháng chưa được trả, như ô của Công nợ theo tháng.
- Bảng khách có cả sổ đã hết nợ có số trong tháng (chấm xám, các cột nợ "–"); lọc mức rủi ro, hạn trả, khách mới bỏ các sổ này, lọc mặt hàng vẫn khớp (mặt hàng lấy từ danh sách sổ). Dải Còn phải thu là nợ hiện tại của các sổ đó.
- Đang lọc tháng thì bảng xếp phát sinh nhiều trước (cột Phát sinh bấm để xếp như các cột khác); bấm dòng mở Sổ khách đúng tháng đó.
- Mặc định không lọc tháng (thẻ ra tháng hiện tại như cũ); không sang tháng sau tháng hiện tại; `?thang=yyyy-mm` giữ lọc trên địa chỉ. Tháng đã qua thì thước không có vạch hôm nay.

## Phạm vi

Chỉ đọc. Hàm `sokhach.get_month_customers(date)`, API `GET /api/v7/month-customers`, mở cho mọi login (`QUYEN-01`). Spec: [`v7-tim-cont-khach-thang`](../../specs/v7-tim-cont-khach-thang.md).

## Trạng thái

ĐÃ CHỐT 28/11/2026 (nội dung, bố cục). Cách làm ở trên là ĐỀ XUẤT của Claude. ĐÃ TRIỂN KHAI trên `hao` 28/11/2026 ([nhật ký](../deploys/2026-11-28-tim-cont-khach-thang.md)); CÒN MỞ: người dùng tự đi hết luồng.
