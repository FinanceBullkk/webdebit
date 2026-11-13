# DEBIT-NOTE-04

[← Sổ quyết định](../decisions.md)

## Quyết định

Debit note v4 xuất từ sổ (bản in/PDF và Excel) **luôn có bảy cột phí** theo mẫu Excel của người dùng, đúng thứ tự: Storage `早装产生费用`, Trucking `拼柜`, Generator / electricity fee `发电机/电费`, Overstay `押车`, HC fee `卫生证`, Cancellation fee `取消订柜费`, AMD fee `改单费`. Cột bằng 0 cả tháng vẫn in, ô và dòng Total ghi `–`.

1. Khoản phụ phí vào cột theo **tên loại phụ phí** (`dnFeeCode`: Neo → Overstay, Điện → Generator, Ghép → Trucking, Health cert và Health + KĐ → HC fee, Hủy → Cancellation, Sửa bill → AMD…), không cần là cột riêng của sổ nữa. Thay điểm 1 "cột phí theo cột phụ phí của sổ" của [DEBIT-NOTE-03](debit-note-03.md).
2. Loại ngoài bảy cột: cột riêng của sổ (Bảo hiểm, Kiểm định, Giảm trừ) in sau bảy cột khi có số; mọi loại còn lại (Phụ phí ban đầu, Khác…) vào Other fees, cột này chỉ in khi có số.
3. Bảng không vừa A4 ngang thì lần lượt: cột phí hẹp theo số dài nhất của cột, tiêu đề Anh tối đa hai dòng; chữ cả bảng thu nhỏ đều từng 5%, nhỏ nhất 80% (như Excel "vừa một trang ngang"); tên Trung của nơi/cảng xuống dòng dưới tên Latin. Tên Trung cùng dòng vẫn ưu tiên và không nhỏ hơn 9px ([DEBIT-NOTE-03](debit-note-03.md)). Chứng từ ít cột (dữ liệu mẫu) in như cũ.

Không đổi: Sổ khách (vẫn tối đa 3 cột riêng + Khác theo [PHU-PHI-01](phu-phi-01.md)), số tiền, phép kiểm, mẫu v3.

## Ngày / nguồn

13/11/2026, chat: người dùng gửi ảnh tiêu đề cột Excel (STORAGE, TRUCKING, GENERATOR / ELECTRICITY FEE, OVERSTAY, HC FEE, CANCELLATION FEE, AMD FEE) và yêu cầu "trong sổ và xuất debit luôn hiện các cột này". Claude báo Sổ ở màn 1280 chỉ còn khoảng 300px cho cột phụ phí, 7 cột cần khoảng 600px; người dùng chọn **chỉ debit note**. Cách co bảng ở điểm 3 là Claude chọn, kiểm bằng bản dựng 3/18/60 container dữ liệu giả, có và không có tên Trung: không cột nào tràn.

## Hiệu lực và giới hạn

Trên `hao` ngày 13/11/2026, phần lớn phụ phí trong sổ là loại "Phụ phí ban đầu" (1.996 dòng, nạp từ cột OTHER FEE/PHỤ PHÍ của Sheet, không tách loại) hoặc "Khác" (575 dòng); chỉ Neo, Điện, Ghép, Health + KĐ đã có dòng (36 dòng). Vì vậy bảy cột hầu hết là `–`, tiền vẫn ở Other fees cho tới khi phụ phí được gán đúng loại. Danh mục chưa có loại cho Storage, Cancellation, AMD; thêm loại tên "Lưu bãi"/"Storage", "Phí hủy", "Sửa bill"/"AMD" ở Cài đặt phụ phí thì khoản sẽ vào đúng cột.
