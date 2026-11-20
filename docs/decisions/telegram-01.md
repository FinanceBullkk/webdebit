# TELEGRAM-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 20/11/2026: **`hao` gửi tin báo thu chi vào một nhóm Telegram, kèm ảnh chuyển khoản đã che.** Telegram là chuông báo về điện thoại; nơi đối chiếu vẫn là trang Thu chi trên web ([`ZALO-THU-CHI-01`](zalo-thu-chi-01.md)).

1. **Báo theo sự kiện**, không chép mọi tin chat:
   - có khoản thu/chi/ứng mới (máy đọc từ ảnh chuyển khoản hoặc từ tin gõ theo mẫu);
   - khoản lệch số với sổ;
   - khoản quá 3 ngày chưa vào sổ;
   - một bản tổng cuối ngày.
2. **Nội dung mỗi tin:** khách hoặc nhóm, số tiền, giờ, trạng thái đối chiếu, link mở đúng khoản trên web. Không gửi chữ gốc của tin chat.
3. **Ảnh chuyển khoản đã che**, cùng luật che trước khi gửi Gemini ([`ZALO-AGENT-01`](zalo-agent-01.md) Phần 4): tô đen số tài khoản, số thẻ, tên người chuyển và người nhận. Ảnh không che được thì chỉ gửi chữ, không gửi ảnh. Việc che làm ở máy có Zalo (nơi OCR chạy); `hao` chỉ nhận và gửi ảnh đã che.
4. **Chỉ báo.** Không ghi tiền, không đổi phân bổ hay tháng khóa. Bot không đọc tin trong nhóm Telegram và không nhận lệnh nào từ đó.
5. **Bí mật ngoài repo:** token bot và mã nhóm chỉ nằm ở `hao` (`/etc/webdebit/telegram.env`), không vào Git, log hay nhật ký. Có cờ tắt hẳn việc gửi.

## Rủi ro đã nêu, người dùng chấp nhận

- Tên khách, số tiền và ảnh chuyển khoản đã che nằm trên máy chủ của Telegram.
- Ai trong nhóm Telegram cũng thấy mọi tin; chỉ mời người được xem thu chi.
- Che ảnh dựa vào OCR; một số ô chữ có thể sót. Ảnh không che được thì không gửi.

## Ngày / nguồn

20/11/2026, chat. Người dùng đề xuất "join các group có thanh toán, lấy tin nhắn các group đó, tạo group Telegram và up các tin thanh toán vào đó". Claude đề xuất dùng Telegram làm chuông báo theo sự kiện, web vẫn là nơi đối chiếu, chỉ gửi bản tóm tắt. Người dùng chọn "Làm, kèm ảnh chuyển khoản".

## Hiệu lực và giới hạn

ĐÃ CHỐT 20/11/2026. Chưa code. Phụ thuộc phần máy tự đọc ảnh và che ảnh (ZALO-AGENT-01 PR-4a) và trang Thu chi hiện số máy đọc (PR-4b).

Người dùng tự làm: tạo bot qua @BotFather, tạo nhóm Telegram, thêm bot vào nhóm, đặt token lên `hao`.

CÒN MỞ:

- giờ gửi bản tổng cuối ngày;
- ai ở trong nhóm Telegram;
- nhóm thường hay kênh (channel).
