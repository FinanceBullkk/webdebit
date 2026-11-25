# KHACH-WEB-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt (24/11/2026): **quản lý tạo sổ khách mới và gán tên chủ hàng trên booking vào sổ ngay trên web**, để chuyến booking của khách đó tự vào đúng sổ mà không cần tab khách trên Sheet sổ nợ. Hai câu chọn, cả hai theo đề xuất của Claude:

- **"Quản lý tạo, lưu trên web":** chỉ tài khoản quản lý (`QUYEN-01`) thấy và gửi được lệnh. Tên chủ hàng trên booking lưu trong DB web, mỗi lần gán hay bỏ có một dòng Lịch sử ở sổ đó. Bảng `WEB_GHEP_KHACH` của file booking vẫn được đọc như cũ.
- **"Thẻ mới Khách trong Quản trị":** một trang riêng. Trên cùng là chủ hàng booking chưa có sổ, mỗi tên có nút gán vào sổ có sẵn hoặc tạo sổ mới. Dưới là mọi sổ đang hoạt động kèm tên trên booking của từng sổ, thêm hay bỏ được.

Claude chọn phần cách làm (ĐỀ XUẤT, áp dụng trong phạm vi trên):

1. **Một tên chủ hàng chỉ ứng một sổ.** Tên chuẩn hóa như hàng chờ so: viết hoa, NFC, gộp mọi khoảng trắng (kể cả NBSP); ký tự vô hình hay điều khiển bị từ chối. Gán tên đã ở sổ khác thì bị từ chối; muốn chuyển thì bỏ ở sổ cũ trước.
   **Không gán tên đang đưa chuyến vào sổ khác** (`BOOKING_NAME_ROUTED`): tên trùng tên sổ hay tên khách của sổ khác; bảng `WEB_GHEP_KHACH` ghép tên vào sổ khác; chuyến bộ của tên đã vào sổ khác theo tab Sheet, hay đã vào từ hai sổ trở lên (thường là kho); tên gần trùng tên booking của sổ khác theo khóa chuyến bộ. Lỡ tay gán thì mọi chuyến của tên đó sẽ chuyển sổ mà sổ cũ không có dòng Lịch sử nào.
2. **Chuyến biển** (`CONT_NGUON`): tên gán ở sổ không ghi là đi bộ thắng bảng `WEB_GHEP_KHACH` khi trùng tên. Dòng PS của các chuyến đó gắn cùng sổ (`MAY-PS-01`). Từ đó luật chọn sổ của P3b giữ nguyên: máy chỉ tự dán khi mặt hàng booking trùng mặt hàng sổ (`COMMODITY_OK`); không trùng thì chuyến hiện ở Việc cần làm của sổ để người bấm Duyệt.
3. **Chuyến bộ** (`CONT_BO`) chưa ở tab nào: chủ hàng đã gán tên ở sổ không ghi là đi biển thì vào sổ đó (tab Sheet đã đưa chủ hàng này vào sổ khác thì tên web không thắng), không cần đủ `OWNER_MIN_TRIPS` chuyến tab đã xếp như luật chủ hàng (`CHUYEN-BO-CHU-HANG-01`). Tab xếp được thì tab vẫn thắng. Tab có dòng cùng container lệch ngày chưa ai nhận thì vẫn chờ (`TAB_FAR`). Hai dòng cùng container cách nhau không quá 3 ngày thì không thành hai chuyến (`AMBIGUOUS_SOURCE`).
4. **Sổ mới:** khách mới chưa có nợ, nên mốc riêng có một số dư đầu 0 ở tháng tạo (giờ VN), qua đủ chuỗi cổng của mốc như sổ máy tạo (`MAY-TAO-SO-01`). **Tên sổ phải sạch như tên tab trong file Sheet xuất ra** (NFC, khoảng trắng gộp, không có `/ \ ? * [ ] : '` hay ký tự lạ; `INVALID_BOOK_NAME`), vì máy đối soát so tên sổ với tên tab trong file đó. **Sổ có sẵn trùng theo khóa gộp mọi khóa tên của các máy** (bỏ các dấu đó, gộp khoảng trắng, không phân biệt hoa thường), kể cả trùng tên khách của sổ khác, là `BOOK_EXISTS`: máy đối soát gặp hai sổ một tên thì dừng cả lượt mỗi giờ, bảng ghép giá bỏ tab đó. Sheet có tab cùng khóa thì sổ lấy đúng chữ tab. Tên sổ mới không được là tên booking của sổ khác hay tên `WEB_GHEP_KHACH` đang ghép vào sổ khác. Trang điền sẵn tên sổ máy sẽ tạo cho tab Sheet đang ghi các chuyến của chủ hàng đó, nếu tab chưa có sổ. Phương thức (biển/bộ) bắt buộc. **Mặt hàng chỉ chọn trong danh mục** (`INVALID_COMMODITY`): gõ tự do thì danh mục thêm nhóm lạ và sổ không bao giờ trùng mặt hàng booking. Mặt hàng không bắt buộc, nhưng chuyến biển chỉ tự vào sổ khi có mặt hàng trùng booking.
   **Không tạo tay sổ trùng tên một tab Sheet đã có dòng từ tháng trước** (`SHEET_TAB_HAS_HISTORY`, không phân biệt hoa thường). Sổ tạo tay bắt đầu từ nợ 0 nên sẽ mất số dư cũ; tab đó để máy tạo sổ theo Sheet. Tab chỉ có dòng tháng này (khách mới tháng này) thì cho tạo. Khi đã thôi đọc Sheet (không còn bản chụp giá) thì không chặn.
5. **Không đụng tiền.** Chuyến vào sổ ở lượt máy sau, chưa có giá. Giá vẫn theo các đường đang có (`MAY-GIA-01` khi Sheet còn chạy, hoặc người ghi ở Việc cần làm).
6. **Sổ lưu trữ** không nhận tên mới (`CUSTOMER_ARCHIVED`), tên cũ của nó không dẫn chuyến; bỏ tên vẫn được.

## Review độc lập (24/11/2026)

Review trước merge nêu một điểm nặng: DB chỉ chặn trùng tên sổ bằng `lower()`, trong khi máy đối soát, bảng ghép giá và hàng chờ so tên theo ba khóa khác nhau. Một sổ gõ thêm dấu cách đôi hay khác hoa thường sẽ làm máy đối soát dừng cả lượt. Đã sửa bằng khóa gộp ở cả API và DB (mục 4), cùng các điểm vừa: tên đang vào sổ khác, tên kho, biển/bộ, danh mục mặt hàng, sổ lưu trữ, dòng PS, khóa chống ghi trùng ở trang khi chưa rõ đã ghi. Số đo chỉ đọc trên `hao` cùng ngày: 0 cặp sổ trùng khóa gộp (luật mới không chặn sổ nào có sẵn); 22 tên chủ hàng biển trùng đúng tên một sổ (rủi ro gán nhầm có thật); 1 chủ hàng bộ đã vào từ hai sổ; 2/252 tab có dấu file bỏ và 3 tab có chữ thường. Locale DB `en_US.UTF-8` nên `lower()` đúng với chữ Việt.

## Ngày / nguồn

24/11/2026, chat. Người dùng giao bốn việc để bỏ được Sheet sổ nợ; việc 4 gồm "khách mới nhập thẳng trên web". Claude đo chỉ đọc trên `hao` (báo cáo tháng, lượt kiểm 08:05). Tháng 11/2026, booking có 220 chuyến biển, web có 214. 11 chuyến không vào web, đều do tên chủ hàng: 6 chuyến của 4 tên chưa ứng sổ nào, 5 chuyến của một khách có tab trên Sheet mà chưa có sổ web. Claude hỏi hai câu (ai tạo, tên lưu ở đâu; trang đặt ở đâu), người dùng chọn đúng đề xuất.

## Hiệu lực và giới hạn

ĐÃ CHỐT hai lựa chọn của người dùng; phần cách làm là ĐỀ XUẤT. ĐÃ TRIỂN KHAI trên `hao` 24/11/2026 (FinanceBullkk/webdebit#631, migration áp tay, [nhật ký](../deploys/2026-11-24-khach-web.md)); người dùng chưa đi thử luồng trên màn thật. Chi tiết ở [spec](../../specs/v7-khach-web.md). Migration `2026-11-24-v7-khach-web.sql` thêm:

- bảng `booking_name`;
- hai lệnh `create_customer`, `set_booking_name` cấp cho app;
- hàm phụ `_booking_names`.

`list_customers` trả thêm `booking_names` và `archived`. Không đổi quy tắc tiền, phân bổ, khóa tháng hay quyền xem sổ. Không ghi Sheet hay file booking.

Giới hạn:

- **Một khách nhiều sổ theo mặt hàng:** một tên booking chỉ ứng một sổ. Nếu cùng tên chở hai mặt hàng vào hai sổ, gán tên vào sổ chính. Sổ cùng tên khách (`display_name`) thì luật họ sổ của P3b vẫn chọn theo mặt hàng.
- **Chủ hàng là kho đóng hàng cho nhiều khách:** trang không cho gán khi tab Sheet đã đưa chuyến bộ của tên đó vào từ hai sổ. Kho chưa có lịch sử tab thì vẫn đừng gán: gán là mọi chuyến bộ chưa ở tab nào của tên đó vào một sổ.
- **Khách có cả sổ biển và sổ bộ:** một tên chỉ một sổ, nên tên web chỉ dẫn được đường của sổ đó. Đo 24/11/2026 trên `hao`: chưa họ sổ nào có cả hai, chưa tên chủ hàng nào có ở cả hai booking từ 10/2026.
- **Danh sách "chưa có sổ"** chỉ tính chuyến từ tháng nạp V7 (10/2026), như máy dán chuyến. Danh sách có chuyến biển hàng chờ chưa ứng sổ nào và chuyến bộ `NO_TAB`. Chuyến đã vào web bằng đường khác (ví dụ máy đối soát dán theo tab Sheet) vẫn có thể có trong danh sách tới khi tên được gán.
- **Sổ tạo nhầm** chưa có lệnh xóa trên web. Sổ không có chuyến thì không tính vào nợ.

**Cập nhật 25/11/2026 (máy đối soát):** sổ tạo trên web không có tab Sheet nên máy đối soát mỗi giờ xếp vào "Có sổ trên web, không thấy trên Sheet" và đưa lên tab Sổ nợ lệch, dù đó là đúng thiết kế (hai sổ đầu tiên tạo sáng 25/11 hiện ngay ở đó). Người dùng hỏi Claude xử lý giúp danh sách lệch và chọn "Làm luôn". Từ nay sổ có tên booking gán trên web mà không có tab mang kết luận `WEB_BOOK` ("Sổ tạo trên web, không cần tab Sheet"), không vào danh sách Sổ nợ lệch. Trạng thái so vẫn là `CHI_CO_WEB` nên số "x/y khách khớp Sheet" không đổi. Sổ không có tên booking mà mất tab vẫn báo như cũ, vì có thể là tab bị đổi tên còn giữ nợ. Không đổi DB, quyền, tiền.
