# THANH-THANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Thanh chọn tháng của Sổ khách là **một dải liên tục chia nhóm theo năm**:

1. Năm là nhãn đứng trước nhóm tháng của năm đó; chip tháng chỉ ghi "T5". Chip đang xem chỉ đổi màu, không đổi chữ.
2. Tháng không có số liệu nằm giữa hai tháng có số liệu vẫn có ô mờ không bấm được, để vị trí tháng cố định và thấy rõ khoảng trống. Bỏ dấu "… N tháng".
3. Sổ trải không quá 16 tháng thì hiện hết. Sổ dài hơn: năm của tháng đang xem và năm mới nhất hiện đủ, các năm khác gom thành nút "Xem ›" cạnh nhãn năm; bấm thì sang tháng cuối có số liệu của năm đó.
4. Dấu khóa và chấm việc chờ trên chip giữ như trước.

## Ngày / nguồn

26/11/2026, Telegram. Người dùng gửi ảnh thanh tháng ("UI phần này vẫn chưa tốt", "nên architect lại cái phần thời gian các tháng năm"); Claude đưa ba hướng (A dải nhóm theo năm, B chọn năm + lưới 12 tháng, C nút lùi tới); người dùng chọn A.

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng A. Ngưỡng 16 tháng là ĐỀ XUẤT của Claude (vừa một hàng ở 1280). Thay cách ghi năm trên chip và dấu "… N tháng" của mục SK-N8 trong [audit Sổ khách 25/11](../ux-audit-so-khach-2026-11-25.md). Giữ nguyên [`SO-GON-05`](so-gon-05.md) (một tháng trên màn hình, chip là chỗ chọn tháng duy nhất, tháng mở sẵn). Chỉ đổi giao diện; không đổi luật tiền, khóa tháng, lệnh ghi hay DB.
