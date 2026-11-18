# XUAT-SO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Đường lui khi web hỏng sau ngày chuyển hẳn khỏi Sheet sổ nợ (mục F4 của [checklist chuyển hẳn](../chuyen-han-checklist.md)) là
**bản xuất cả sổ web ra bảng tính**, người dùng tự tải về PC. Người dùng chọn ba điều:

1. **Dạng: nút tải trên web.** Nút "Tải cả sổ" ở Tổng quan. Người dùng biết nút không dùng được đúng lúc web hỏng, nên bản xuất là
   thứ tải trước, định kỳ, rồi cất trên PC.
2. **Ai tải: mọi login được mở sổ.** Không thêm quyền riêng: ai trong danh sách cho phép của [`ACCESS-01`](access-01.md) thì tải
   được toàn bộ sổ. Câu hỏi đã nói rõ điều này khi người dùng chọn.
3. **Bố cục: bảng gộp, lọc theo khách.** Tab KIỂM, TỔNG (mỗi khách một dòng), rồi các tab Tháng, Chuyến, Phiếu thu, Phân bổ thu,
   Điều chỉnh; dòng nào cũng có mã và tên sổ, có bộ lọc. Không làm mỗi khách một tab như Sheet.
4. **Nơi giữ: `D:\webdebit-du-phong\` trên PC,** ngoài Git và ngoài OneDrive; mỗi lần một file mang ngày giờ, không xóa bản cũ.
   Máy chủ không giữ bản nào.

Cách làm do Claude đặt (ĐỀ XUẤT trong phạm vi người dùng giao), chi tiết ở [spec](../../specs/v7-xuat-ca-so.md): đọc mọi sổ trong
một giao dịch chỉ đọc (một ảnh dữ liệu, như [`LUOI-AN-TOAN-01`](luoi-an-toan-01.md)), không thêm hàm SQL; bản xuất tự kiểm tổng các
sổ với Còn phải thu trên Tổng quan, từng sổ với Tổng quan, phiếu thu chia đủ và file đọc lại khớp `get_ledger`. Lệch thì vẫn trả
file (có số còn hơn không) nhưng tên có đuôi `-CO-LECH`, tab KIỂM ghi chỗ lệch và trang báo đỏ: không xuất im lặng.

## Ngày / nguồn

18/11/2026, chat. Claude hỏi ba câu (cách xuất, bố cục, nơi giữ), mỗi câu có phương án khuyên. Người dùng chọn "Nút tải trên
web" (không chọn phương án khuyên "Lệnh trên hao, khi cần" hay "Lệnh + tự chạy mỗi đêm"), "Bảng gộp, lọc theo khách" và "Thư
mục riêng ổ D".

## Hiệu lực và giới hạn

ĐÃ CHỐT dạng, quyền tải, bố cục, nơi giữ. Không đổi luật tiền, DB hay quyền ghi. Chưa có nhắc tải định kỳ: máy chủ không biết
người dùng đã cất file chưa. Khi cả `hao` hỏng thì bản tải gần nhất trên PC và bản sao lưu mã hóa hằng đêm (diễn tập phục hồi
là mục E1, CHƯA làm) là hai đường còn lại.
