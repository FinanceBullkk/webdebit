# DIEN-THOAI-THANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Trên điện thoại (dưới 760px), Công nợ theo tháng thay ma trận 15 cột bằng **danh sách theo khách** (phương án A trên canvas, trang "Theo tháng trên điện thoại"):

1. Mỗi khách một dòng: tên, tổng còn nợ (cột Mọi năm, triệu đồng, số âm trong ngoặc như ma trận), câu "Nợ từ T6 · 2 tháng" (tháng sớm nhất còn nợ của năm đang xem; có nợ trước năm đang xem thì "Nợ từ trước 2026"), dải 12 ô màu theo cùng thang màu ô ma trận.
2. Chạm khách: bung các tháng còn số (cũ trước), mỗi tháng chạm vào mở đúng ngăn kéo chi tiết như bấm ô ma trận; có dòng nợ ngoài năm đang xem (không mở được) và "Mở trang khách".
3. Nhóm theo mặt hàng, xếp, lọc mặt hàng, lọc tên, "Chỉ khách còn nợ", nhóm tuổi nợ từ Tổng quan (`?tuoi=`), khách được chỉ tới (`?khach=`) giữ nguyên như ma trận. Cuối danh sách: Phải thu, Trừ trả trước, Phải thu ròng như dòng tổng ma trận.
4. Mọi số lấy từ cùng bản GET của ma trận, không tính thêm; màn từ 760px trở lên giữ ma trận.

## Ngày / nguồn

12/11/2026, chat: sau [`DIEN-THOAI-SEP-01`](dien-thoai-sep-01.md) người dùng chọn làm tiếp ma trận cho điện thoại. Claude dựng trên canvas bản hiện tại, A theo khách, B theo tháng (chip tháng); người dùng chọn A.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thay ý 4 (mở sẵn ở tháng hiện tại) của `DIEN-THOAI-SEP-01` cho màn hẹp vì ma trận không còn hiện ở đó. Quy tắc tuổi nợ và cấn khoản dư theo [`CAN-DU-01`](can-du-01.md) không đổi.
