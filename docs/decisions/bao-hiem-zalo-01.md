# BAO-HIEM-ZALO-01

[← Sổ quyết định](../decisions.md)

## Quyết định (ĐỀ XUẤT)

Claude đề xuất ngày 19/11/2026, **chưa chốt**: giấy chứng nhận bảo hiểm hàng xuất gửi trong group Zalo là **nguồn phụ, không cộng tiền**, giống bảng PS ([`MAY-PS-01`](may-ps-01.md)). Web dùng giấy theo ba cách, không đổi tổng còn nợ của khách:

1. **Nhắc:** chuyến (booking + container) có giấy mà Sheet và web chưa có khoản bằng số giấy thì hiện "Bảo hiểm cần xem"; người nhập ghi số vào cột `BẢO HIỂM` của tab khách, máy đối soát đưa lên web như mọi phí Sheet.
2. **Phân loại:** chuyến có đúng một khoản Khác hoặc Phụ phí ban đầu bằng đúng số giấy, chưa có khoản Bảo hiểm, thì máy đổi loại khoản đó thành Bảo hiểm bằng `rewrite_trip_fees` (tổng giữ nguyên tới từng đồng); tháng khóa thì mở, ghi, khóa lại như [`MAY-KHOA-01`](may-khoa-01.md).
3. **Chứng cứ:** khoản Bảo hiểm khớp giấy có số giấy và nút mở PDF gốc.

Số so là **tổng có VAT** trên giấy (người dùng chốt 19/11/2026). Giấy thiếu booking, khớp nhiều chuyến, có nhiều container hoặc chưa qua kiểm phép cộng chỉ hiện cho người xem; không gắn giấy vào chuyến chỉ theo container và ngày ([`NEWTRIP-01`](newtrip-01.md)).

## Ngày / nguồn

19/11/2026, chat. Người dùng hỏi phí bảo hiểm đã được tự điền vào webdebit chưa. Claude kiểm: dự án `zalo-audit-viewer` ở máy có Zalo đã đọc được giấy thành `insurance-snapshot.json` (cập nhật 15 phút một lần) nhưng webdebit chưa đọc file này. Claude nêu ba vướng (Sheet có thể đã ghi bảo hiểm nên dễ tính trùng, mã chuyến cần booking mà một phần giấy không có, chưa chốt khách trả là ai). Người dùng trả lời "Viết spec".

Lý do không cộng tiền: [`SONG-SONG-01`](song-song-01.md) và [`CHUYEN-HAN-01`](chuyen-han-01.md) giữ Sheet là sổ chính thức; [`MAY-DOI-SOAT-01`](may-doi-soat-01.md) đưa web về đúng tổng Sheet mỗi giờ, nên khoản web tự cộng sẽ thành lệch.

## Hiệu lực và giới hạn

ĐỀ XUẤT; chưa code, chưa triển khai. Chi tiết, trạng thái từng giấy và tiêu chí ở [spec](../../specs/v7-bao-hiem-zalo.md). Chờ người dùng trả lời Q1–Q4 của spec: khách trả là ai (đề xuất: chủ sổ của chuyến, không so tên); máy có tự đổi loại không (đề xuất: có, kể cả tháng khóa); mở đường đẩy dữ liệu từ máy có Zalo lên `hao` (cần đồng ý riêng); web có tự ghi tiền theo giấy sau khi chuyển hẳn không (để sau).

Không đổi DB, quyền hay luật phân bổ. `hao` chỉ nhận bản gọn của giấy (số giấy, container, booking, số tiền, ngày, trạng thái) và PDF, không nhận tên hay mã số thuế.
