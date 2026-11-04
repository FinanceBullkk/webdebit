# MAY-TAO-SO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **máy tự tạo sổ cho khách mới**, thay vì chỉ báo để Claude tạo tay từng lần. Khách mới là tab khách trên Sheet đã có trên TONG mà web chưa có sổ. Người nhập vẫn chỉ làm trên Sheet: thêm tab, thêm tên vào TONG như vẫn làm.

Máy chỉ tạo sổ khi đủ mọi điều kiện dưới đây, kiểm trong lượt đối soát mỗi giờ ([`MAY-DOI-SOAT-01`](may-doi-soat-01.md)):

1. Tên tab có ở **khối mới nhất của TONG thật** trong bản tải (khối ngoài cùng bên phải), đúng tên khi đã chuẩn hóa dấu và khoảng trắng.
2. **Số cuối tháng trên TONG bằng số cuối tháng đó trên tab**, tới từng đồng. Lệch thì hiểu là đang nhập dở, chưa tạo.
3. Tab đọc được trọn vẹn: qua hết các cổng kiểm của bộ đọc sổ gốc.
4. Web chưa có sổ tên đó, và **không container nào của tab nằm ở sổ khác** cách không quá 3 ngày (dòng không ngày thì cùng tháng). Có thì có thể là đổi tên hoặc tách sổ, để người xem.
5. Không quá 5 sổ mới trong một lượt, và lượt đó không vướng ngưỡng "quá nhiều khách lệch".

Sổ mới làm **đúng đường nạp mốc** ([`OPENING-SO-GOC`](opening-so-goc.md)): một mốc riêng cho sổ đó, số dư đầu và dòng sổ gốc lấy từ tab, qua đủ cổng kiểm từng tháng trong DB (`import_cutover`, `verify_cutover_customer`, `activate_cutover`, `activate_cutover_customer`), tất cả trong một giao dịch. Nên tạo xong tổng sổ bằng đúng tổng tab, và từ đó sổ chạy như mọi khách cũ: chuyến mới, giá, phiếu đi theo các đường máy đã có.

Tên sổ theo tab. Mặt hàng và phương thức vận chuyển theo nhãn trên TONG; nhãn lạ thì để trống, không đoán. Người làm trong Lịch sử là "Máy (theo Sheet)".

Không đủ điều kiện thì máy không ghi gì và báo ở đầu tab Việc cần làm (`outside_tabs`), kèm lý do: chưa có trên TONG, số trên TONG khác số trên tab, hoặc tab có chỗ chưa đọc được. Chỉ báo tab còn nợ có phát sinh từ tháng 10/2026; tab cũ hơn là bản sao, tab nháp đã xem lúc nạp.

## Thay thế

- Trong [`DEPLOY-CLAUDE-01`](deploy-claude-01.md), vế "hỏi trước khi nạp dữ liệu hoặc mốc" không áp dụng cho đúng đường này: một sổ mới, tên chưa từng có, đủ các điều kiện trên. Mọi kiểu nạp khác vẫn phải hỏi.

## Ngày / nguồn

4/11/2026, chat. Khi rà độ tin cậy, Claude thấy 2 tab mới còn nợ khoảng 335 triệu mà web chưa có sổ, và từ mốc nạp 21/10 web không có lệnh tạo sổ. Claude hỏi khách mới vào web theo cách nào, nêu hai cách; người dùng chọn "Máy tự tạo sổ".

Claude đặt các điều kiện 1–5 và cách làm (đường nạp mốc thay vì sổ rỗng rồi chờ các máy khác), không đổi quy tắc tiền. Cũng trong lúc này Claude phát hiện máy đang so "có trên TONG" với danh sách đóng băng từ mốc 20/10 chứ không phải TONG thật, nên câu báo "chưa có trên TONG" trước đó là sai; 2 tab đó đã có trên TONG và số khớp.

## Hiệu lực và giới hạn

ĐÃ CHỐT. ĐÃ TRIỂN KHAI trên `hao` 4/11/2026 ([nhật ký](../deploys/2026-11-04-may-tao-so.md)). Chi tiết ở [spec](../../specs/v7-may-tao-so.md). Thêm một hàm SQL `create_book_from_sheet` cấp cho app, không có route trên web, chỉ máy đối soát gọi. Không đổi quy tắc tiền hay phân bổ. Không ghi Sheet.

Giới hạn:

- Tên trên TONG khác tên tab thì không nhận được, kể cả khi là cùng một khách. Khi đó máy báo, người hoặc Claude xử lý.
- Tab mới chỉ lên TONG khi người nhập thêm khối tháng mới, nên khách có chuyến đầu trong tháng này có thể phải chờ tới lúc đó. Trong lúc chờ, tab hiện ở dòng báo nếu đã còn nợ.
- Trùng chuyến giữa sổ mới và sổ cũ về sau thì chỉ hàng chờ báo, vì hàm `paste_trips` so tham chiếu theo từng mốc.
