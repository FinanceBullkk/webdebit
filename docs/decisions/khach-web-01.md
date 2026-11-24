# KHACH-WEB-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt (24/11/2026): **quản lý tạo sổ khách mới và gán tên chủ hàng trên booking vào sổ ngay trên web**, để chuyến booking của khách đó tự vào đúng sổ mà không cần tab khách trên Sheet sổ nợ. Hai câu chọn, cả hai theo đề xuất của Claude:

- **"Quản lý tạo, lưu trên web":** chỉ tài khoản quản lý (`QUYEN-01`) thấy và gửi được lệnh. Tên chủ hàng trên booking lưu trong DB web, mỗi lần gán hay bỏ có một dòng Lịch sử ở sổ đó. Bảng `WEB_GHEP_KHACH` của file booking vẫn được đọc như cũ.
- **"Thẻ mới Khách trong Quản trị":** một trang riêng. Trên cùng là chủ hàng booking chưa có sổ, mỗi tên có nút gán vào sổ có sẵn hoặc tạo sổ mới. Dưới là mọi sổ đang hoạt động kèm tên trên booking của từng sổ, thêm hay bỏ được.

Claude chọn phần cách làm (ĐỀ XUẤT, áp dụng trong phạm vi trên):

1. **Một tên chủ hàng chỉ ứng một sổ.** Tên chuẩn hóa như hàng chờ so: viết hoa, NFC, gộp khoảng trắng. Gán tên đã ở sổ khác thì bị từ chối; muốn chuyển thì bỏ ở sổ cũ trước.
2. **Chuyến biển** (`CONT_NGUON`): tên gán trên web thắng bảng `WEB_GHEP_KHACH` khi trùng tên. Từ đó luật chọn sổ của P3b giữ nguyên: máy chỉ tự dán khi mặt hàng booking trùng mặt hàng sổ (`COMMODITY_OK`); không trùng thì chuyến hiện ở Việc cần làm của sổ để người bấm Duyệt.
3. **Chuyến bộ** (`CONT_BO`) chưa ở tab nào: chủ hàng đã gán tên thì vào sổ đó, không cần đủ `OWNER_MIN_TRIPS` chuyến tab đã xếp như luật chủ hàng (`CHUYEN-BO-CHU-HANG-01`). Tab xếp được thì tab vẫn thắng. Tab có dòng cùng container lệch ngày chưa ai nhận thì vẫn chờ (`TAB_FAR`). Hai dòng cùng container cách nhau không quá 3 ngày thì không thành hai chuyến (`AMBIGUOUS_SOURCE`).
4. **Sổ mới:** khách mới chưa có nợ, nên mốc riêng có một số dư đầu 0 ở tháng tạo (giờ VN), qua đủ chuỗi cổng của mốc như sổ máy tạo (`MAY-TAO-SO-01`). Tên sổ giữ như gõ. Khi chạy song song, tên sổ nên đúng tên tab trên Sheet, để máy đối soát ghép sổ đó với tab chứ không tạo sổ thứ hai. Trang điền sẵn tên tab Sheet đang ghi các chuyến của chủ hàng đó, nếu tab chưa có sổ. Phương thức (biển/bộ) bắt buộc. Mặt hàng không bắt buộc, nhưng chuyến biển chỉ tự vào sổ khi có mặt hàng trùng booking.
5. **Không đụng tiền.** Chuyến vào sổ ở lượt máy sau, chưa có giá. Giá vẫn theo các đường đang có (`MAY-GIA-01` khi Sheet còn chạy, hoặc người ghi ở Việc cần làm).

## Ngày / nguồn

24/11/2026, chat. Người dùng giao bốn việc để bỏ được Sheet sổ nợ; việc 4 gồm "khách mới nhập thẳng trên web". Claude đo chỉ đọc trên `hao` (báo cáo tháng, lượt kiểm 08:05). Tháng 11/2026, booking có 220 chuyến biển, web có 214. 11 chuyến không vào web, đều do tên chủ hàng: 6 chuyến của 4 tên chưa ứng sổ nào, 5 chuyến của một khách có tab trên Sheet mà chưa có sổ web. Claude hỏi hai câu (ai tạo, tên lưu ở đâu; trang đặt ở đâu), người dùng chọn đúng đề xuất.

## Hiệu lực và giới hạn

ĐÃ CHỐT hai lựa chọn của người dùng; phần cách làm là ĐỀ XUẤT. Chi tiết ở [spec](../../specs/v7-khach-web.md). Migration `2026-11-24-v7-khach-web.sql` thêm:

- bảng `booking_name`;
- hai lệnh `create_customer`, `set_booking_name` cấp cho app;
- hàm phụ `_booking_names`.

`list_customers` trả thêm `booking_names`. Không đổi quy tắc tiền, phân bổ, khóa tháng hay quyền xem sổ. Không ghi Sheet hay file booking.

Giới hạn:

- **Một khách nhiều sổ theo mặt hàng:** một tên booking chỉ ứng một sổ. Nếu cùng tên chở hai mặt hàng vào hai sổ, gán tên vào sổ chính. Sổ cùng tên khách (`display_name`) thì luật họ sổ của P3b vẫn chọn theo mặt hàng.
- **Chủ hàng là kho đóng hàng cho nhiều khách:** đừng gán tên. Gán là mọi chuyến bộ chưa ở tab nào của tên đó vào một sổ.
- **Danh sách "chưa có sổ"** chỉ tính chuyến từ tháng nạp V7 (10/2026), như máy dán chuyến. Danh sách có chuyến biển hàng chờ chưa ứng sổ nào và chuyến bộ `NO_TAB`. Chuyến đã vào web bằng đường khác (ví dụ máy đối soát dán theo tab Sheet) vẫn có thể có trong danh sách tới khi tên được gán.
- **Sổ tạo nhầm** chưa có lệnh xóa trên web. Sổ không có chuyến thì không tính vào nợ.
