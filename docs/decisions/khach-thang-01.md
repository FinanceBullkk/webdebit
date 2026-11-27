# KHACH-THANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan xem được **theo tháng**: chọn một tháng thì thấy tháng đó có những khách nào và tiền của từng khách. Người dùng chốt 28/11/2026 (chọn qua câu hỏi trong phiên):

1. Nội dung là **tiền theo khách**: phát sinh, đã thu, còn nợ của tháng (không thêm số cont; số cont theo tháng đã có ở [Báo cáo tháng](bao-cao-thang-01.md)).
2. Bố cục: **khối riêng cuối trang** "Khách theo tháng", có ‹ › đổi tháng, một dòng tổng, bảng khách. Phần đầu Tổng quan giữ nguyên. Phương án gắn bộ chọn tháng vào thẻ Thu tháng không chọn.

Claude chọn phần cách làm (ĐỀ XUẤT, trong phạm vi trên):

- Mỗi sổ đang hoạt động có phát sinh, đã thu hoặc còn nợ khác 0 ở tháng đó. Phát sinh và đã thu tính như dòng Tổng tháng của Sổ khách ([`DA-THU-01`](da-thu-01.md)), cùng phép với thẻ Thu tháng; còn nợ là phần phát sinh của tháng chưa được trả, như ô của Công nợ theo tháng.
- Mặc định tháng hiện tại (giờ VN); không sang tháng sau; `?thang=yyyy-mm` giữ tháng trên địa chỉ.
- Xếp phát sinh nhiều trước; 10 dòng đầu và nút "Hiện cả N khách"; số 0 hiện "–"; bấm dòng mở Sổ khách tháng đó.

## Phạm vi

Chỉ đọc. Hàm `sokhach.get_month_customers(date)`, API `GET /api/v7/month-customers`, mở cho mọi login (`QUYEN-01`). Spec: [`v7-tim-cont-khach-thang`](../../specs/v7-tim-cont-khach-thang.md).

## Trạng thái

ĐÃ CHỐT 28/11/2026 (nội dung, bố cục). Cách làm ở trên là ĐỀ XUẤT của Claude.
