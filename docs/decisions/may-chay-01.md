# MAY-CHAY-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chọn: **có tab Máy chạy dạng văn phòng nhân viên, và đưa Hermes Agent vào làm quản lý công việc của văn phòng đó.** Thử Hermes trên PC MSI, model GPT đăng nhập bằng tài khoản ChatGPT.

Cách làm do Claude đặt:

1. **Mỗi nhân viên là một trạm thật của job.** Hình chỉ cử động theo tín hiệu thật hoặc khi người xem bấm phát lại. Hết lượt thì đứng yên. Mất kết nối thì báo và thôi vẽ tiếp.
2. **Job vẫn là script theo luật, Hermes không nằm trong vòng đối soát.** Hermes là nhân viên duy nhất là AI; nó đọc tóm tắt, viết thẻ việc cho chủ sổ, không ra lệnh cho job.
3. **Hermes không có đường ghi sổ.** Ranh giới đặt ở quyền, không đặt ở lời dặn: container khóa, không mount ổ đĩa, không có khóa SSH, ra ngoài chỉ qua cổng danh sách trắng, công cụ chỉ đọc tóm tắt và ghi thẻ.
4. **Bản tóm tắt cho Hermes chỉ có mã khách, mã lý do và số đếm.** Không tên, không tiền, không chữ tự do lấy từ Sheet hay Zalo. Web đổi mã thành tên khi hiện cho người xem.
5. **Bảng việc tách khỏi DB sổ.** Lỗi ở bảng việc không đụng được tiền.
6. **Tín hiệu từng bước lỗi thì mất tín hiệu, không làm hỏng lượt ghi tiền.** Có test ép lỗi: lượt vẫn ghi đúng y hệt.
7. **Trực tiếp là mặc định, xem lại là phụ** (người dùng, chat, 6/11/2026: "muốn real time, không hẳn chỉ để xem lại"). Mở tab là thấy máy lúc này; xem lại chỉ khi bấm một lượt, có nút về trực tiếp. Hình vẫn chỉ cử động theo việc thật: máy nghỉ thì đồng hồ chạy, nhân viên ngồi yên.

**Vì sao không làm 3D, không cho AI quyết tiền:** xem [spec](../../specs/v7-may-chay.md). Máy hiện an toàn vì chỉ ghi khi có đúng một tổ hợp khớp tới từng đồng; phép đó tính ra được, không đoán.

## Ngày / nguồn

6/11/2026, chat. Người dùng chọn phương án C, chọn Hermes làm quản lý, chọn chạy thử trên PC MSI, chọn GPT OAuth, rồi bảo làm tiếp.

## Hiệu lực và giới hạn

ĐÃ CHỐT hình C và vai trò quản lý của Hermes. Không đổi luật tiền, điều kiện ghi của máy, quyền ghi hay DB.

CÒN MỞ: nơi chạy Hermes lâu dài (PC tắt là quản lý nghỉ, job vẫn chạy); điều khoản OpenAI về gói ChatGPT cá nhân dùng cho việc tự động chưa xác minh; chấm chất lượng thẻ trên các ca đã biết; kênh báo.

Bước nghiệm thu cuối là người dùng tự đi hết luồng trên `hao`, chưa làm.
