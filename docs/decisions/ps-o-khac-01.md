# PS-O-KHAC-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Thay cách đặt của [PS-TAI-HANG-01](ps-tai-hang-01.md): phụ phí phát sinh cần xem **nằm ngay trong ô Khác** của chuyến, không chen hàng chữ dưới chuyến.

1. Ô Khác của chuyến có một **nhãn cam viền đứt**: số chênh ("+315.789"), chữ bảng chi phí ghi khi là số lẻ ("315789.5 ?"), hoặc chữ ngắn ("Health ?", "loại ?", "chờ tách"). Một chuyến nhiều câu thì nhãn ghi thêm số câu. Ô đã có số thì nhãn nằm dòng trên, số dòng dưới.
2. Bấm nhãn mở **hộp nhỏ cạnh ô** (bấm nhãn không mở chi tiết phụ phí của ô). Hộp ghi ba số đặt thẳng hàng: **Bảng chi phí ghi**, **Sổ khách đang tính**, **Chênh**; hoặc một câu ngắn khi không có số. Hai nút ngang nhau: "Không tính khách" (hoặc "Sổ khách đúng", "Số đúng, bỏ qua"…) và "Tính khách…". Nút "Tính khách…" chỉ hiện cách làm (ghi trên tab khách ở Sheet), vì web không cộng tiền theo bảng chi phí; khoản theo loại (Health cert, Kiểm định, chia loại) thì nút mở thẳng chi tiết phụ phí của chuyến.
3. Cùng một khoản chia cho nhiều cont: hộp có ô tick "Trả lời luôn cho … (cùng khoản)", tick sẵn; bỏ tick thì chỉ trả lời chuyến đang mở.
4. Chữ trên màn gọi là **phụ phí phát sinh** và **bảng chi phí**; bỏ "PS", "hết báo", "cùng khoản với".
5. Thanh việc: "n cont có phụ phí phát sinh cần xem · **Đến cont tiếp**" mở đúng tháng, cuộn tới chuyến và mở hộp. Dòng không gắn được chuyến nào vẫn mở bằng nút Xem.
6. GET sổ thêm `ps_field`, `ps_value` cho dòng gõ sai/số lẻ để hộp ghi đúng ô và chữ bảng chi phí ghi.

Không đổi: luật "không tính" của [PS-HOI-01](ps-hoi-01.md) (chỉ ghi Lịch sử, không đổi tiền, bảng chi phí đổi thì hỏi lại), lệnh ghi, luật tiền. Điện thoại không có ô Khác nên chỉ hiện số đếm.

## Ngày / nguồn

13/11/2026, chat. Sau khi PS-TAI-HANG-01 lên `hao`, người dùng gửi ảnh hàng hỏi và nói "thiết kế và ghi chú như hiện tại thì sẽ không người dùng nào hiểu, không trực quan và không hợp lý". Claude nêu ba chỗ khó hiểu (chữ của máy, số không nằm ở cột tiền nào, chỉ có nút "Không thu"), người dùng chọn tên "Phụ phí phát sinh" và xin mockup trên canvas; Claude vẽ bốn khung (bây giờ, bảng so sánh riêng, số trong ô Khác, sang Việc cần làm), người dùng chọn "B · Trong ô Khác".

## Hiệu lực và giới hạn

ĐÃ CHỐT theo lựa chọn của người dùng. Thay PS-TAI-HANG-01 mục 1–4. Chỉ đổi giao diện trang live và thêm hai trường đọc ở GET sổ; không đổi DB hay luật tiền. CÒN MỞ: người dùng tự đi hết luồng trên `hao`; các khung Giá/Phiếu thu từ Sheet chưa đổi.
