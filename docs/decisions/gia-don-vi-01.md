# GIA-DON-VI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Mọi đường nhập **đơn giá chuyến** trên web hỏi lại tại chỗ, trước khi gửi, khi giá nằm ngoài khoảng 1.000.000 đ đến 1 tỷ đ một chuyến:

1. Luật nằm ở model dùng chung (`priceDoubt`, `priceDoubtText` trong `so-khach-v7-model.js`); ô gõ ở Sổ khách, dán lô giá và ô triệu của Việc cần làm cùng gọi, không mỗi nơi một ngưỡng.
2. Chỉ là câu hỏi, không chặn: Sổ khách hỏi dưới dòng với nút "Sửa lại" (lấy tiêu điểm) và "Ghi <số> đ"; dán lô ghi cờ vào dòng xem lại; Việc cần làm nêu "Kiểm lại đơn vị" ở đầu bước xem lại.
3. Hiện đơn vị cạnh ô nhập: "đồng, không phải triệu" ở Sổ khách, "triệu" ở Việc cần làm.
4. Không đổi luật tiền phía máy chủ: máy chủ vẫn không chặn khoảng giá.

Cùng đợt, mọi ô gõ số tiền (Thu chi "Số đúng", Chat Zalo "Đánh dấu", Sổ khách) đọc bằng một bộ đọc chặt (`CongNoFormat.readVnd`): chỉ chữ số hoặc nhóm ngăn nghìn đều; số lẻ như "1,5" hay "45.000.000,50" bị từ chối, không bỏ dấu rồi đọc thành số khác.

## Lý do

Ô Đơn giá của Sổ khách tính bằng đồng, ô giá của Việc cần làm tính bằng triệu. Gõ "45" ở Sổ khách ghi 45 đồng, nợ thấp khoảng 45 triệu, không ai được hỏi (audit 23/11/2026). Giá trị số 1 của sản phẩm là hết ghi nhầm tiền: máy chặn sai trước khi hỏi người.

## Ngày / nguồn

23/11/2026, audit frontend F1, F2 và yêu cầu sửa của người dùng.

## Hiệu lực và giới hạn

ĐÃ CHỐT 23/11/2026. Bảng giá (so-khach-v7-price-ui.js) chưa dùng luật này; ô phụ phí chưa có ngưỡng.
