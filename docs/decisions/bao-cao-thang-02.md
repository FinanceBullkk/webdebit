# BAO-CAO-THANG-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Báo cáo tháng trả lời thêm một câu: **chuyến nào booking có mà web chưa có, và vì sao**. Bổ sung cho [`BAO-CAO-THANG-01`](bao-cao-thang-01.md), vẫn chỉ xem.

Người dùng chốt **chỗ hiện là tab Báo cáo tháng**. Hai phương án không chọn:
- **Việc cần làm:** tab đó trả lời "số nợ có khớp Sheet không" ([`VIEC-DOI-CHIEU-01`](viec-doi-chieu-01.md)). Chuyến booking chưa lên web thường cũng chưa lên Sheet nên không làm lệch số nợ; đặt vào đó làm loãng mục tiêu của tab ([`DASH-03`](dash-03.md)).
- **Máy chạy:** khối kiểm booking ở đó so booking với Sheet, không so với web ([`KIEM-BOOKING-01`](kiem-booking-01.md)).

Claude chọn phần cách làm (ĐỀ XUẤT, áp dụng trong phạm vi trên):

1. **Bảng tổng thêm hàng "Booking có, web chưa có"**, theo Biển, Bộ, Tổng. Hàng này đếm mọi chuyến booking của tháng không có chuyến web nào ghép, kể cả chuyến Sheet đã ghi. Bấm tên hàng thì mở danh sách chuyến ngay dưới bảng tổng; địa chỉ giữ `webchua=1`.
2. **Mỗi chuyến trong danh sách có lý do máy chưa đưa vào web và ai phải làm.** Lý do đọc từ chính các hàng chờ máy dùng để tự dán chuyến ([`HANG-CHO-01`](hang-cho-01.md), [`NGUON-CHUYEN-01`](nguon-chuyen-01.md), [`CHUYEN-BO-CHU-HANG-01`](chuyen-bo-chu-hang-01.md)), nên trang nói đúng điều máy đang thấy, không đặt luật mới. Bốn nhóm:
   - **Tự hết khi Sheet ghi:** container đã dùng ở chuyến trước của sổ ([`CONTAINER-DUNG-LAI-01`](container-dung-lai-01.md)); chuyến bộ chưa tab khách nào ghi.
   - **Cần người:** tên chủ hàng trên booking chưa gắn sổ web nào (khách mới hoặc tên khác); mặt hàng booking khác sổ; tháng khóa trước 10/2026; khác thông tin với sổ.
   - **Máy tự làm:** đủ điều kiện, chờ lượt máy tới; ngày chuyến sau hôm nay.
   - **Xem trong sổ:** sổ đã có chuyến ở ngày khác.

   Không đọc được lý do thì ghi "Chưa đọc được lý do", không đoán.
3. **Chuyến booking Sheet chưa ghi ghép chuyến web ở mọi sổ.** Trước đây báo cáo chỉ ghép chuyến web trong sổ đoán theo tên chủ hàng. Trong khi đó máy đặt chuyến theo mặt hàng hay chủ hàng, nên chuyến đã ở sổ khác bị đếm là "web chưa có" và lặp lại ở "Chỉ có trên web". Nay chuyến đó ghép chuyến web cùng container, lệch không quá 3 ngày, ở sổ nào cũng được, và dòng chuyển sang sổ đó. Dòng Sheet đã ghi vẫn chỉ ghép trong sổ của tab, để chuyến web nằm sai sổ so với Sheet vẫn hiện là lệch.
4. **Chữ trạng thái từng cont** nói rõ "Chưa lên Sheet, web chưa có" khác "Chưa lên Sheet" (web đã có). Chip "Web chưa có" của khách cộng cả chuyến booking Sheet chưa ghi.
5. **Lý do tải riêng khi mở danh sách** (`GET /api/v7/report/month/missing`). Chiếu hàng chờ một sổ mất 0,1–1,2 giây (đo trên `hao` 19/11/2026), nên bảng tổng vẫn mở nhanh như cũ. Mỗi lần chiếu tối đa 40 sổ.

## Ngày / nguồn

19/11/2026, chat. Người dùng xem bảng tổng tháng 11 và hỏi vì sao web chưa theo kịp booking. Claude đo chỉ đọc trên `hao`: trong 211 chuyến booking có 13 chuyến thật sự chưa lên web, đều do máy cố ý giữ:
- 5 chuyến container đã dùng;
- 4 chuyến khách chưa có sổ;
- 3 chuyến tên booking chưa ghép sổ;
- 1 chuyến sai mặt hàng.

Ngoài ra 7 chuyến đã có trên web nhưng ở sổ khác sổ đoán, nên báo cáo đếm nhầm. Người dùng hỏi "hiện tại không có chỗ nào để check những chuyến booking có mà web không có hả", rồi bảo tìm màn phù hợp. Claude đưa hai phương án kèm phác thảo, người dùng chọn "Báo cáo tháng (Đề xuất)".

Chạy thử mã mới trên dữ liệu `hao` (chỉ đọc, tháng 11/2026): hàng mới ra 13, đúng 13 chuyến và đúng lý do như lần đối chiếu tay. "Chỉ có trên web" giảm từ 9 xuống 2, là hai chuyến web thật không có booking.

## Hiệu lực và giới hạn

ĐÃ CHỐT chỗ hiện. Phần cách làm là ĐỀ XUẤT. Chỉ đọc: không ghi DB, sổ hay Sheet. Không đổi luật tiền, luật ghép của máy hay điều kiện máy ghi. Hàng chờ chuyến bộ chỉ thêm danh sách `skipped` (container, ngày, mã lý do) bên cạnh `stats` sẵn có, để báo cáo đọc được lý do từng chuyến; chuyến được xếp sổ không đổi.

- Trang không có nút ghi. Gắn tên chủ hàng vào sổ hay tạo sổ vẫn làm ở chỗ cũ. Muốn bấm ngay trong báo cáo thì cần quyết định riêng.
- Lý do theo bản chụp booking và Sheet mới nhất, còn số đếm theo lượt máy gần nhất, nên có thể lệch nhau trong vòng một giờ.
- CÒN MỞ: người dùng tự đi hết luồng trên `hao`.

Spec: [`specs/v7-bao-cao-thang.md`](../../specs/v7-bao-cao-thang.md).
