# WECHAT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 20/11/2026 ("Làm nguồn WeChat ngay", sau khi chọn trước đó "Làm, đo nhóm này trước"). Spec: [`zalo-agent.md`](../../specs/zalo-agent.md#nguồn-wechat-wechat-01).

1. **WeChat là nguồn thứ hai của `zalo-agent`**, cạnh Zalo, qua bộ xử lý `wechat`. Bật bằng `--wechat` (mặc định TẮT).
2. **Chỉ nhóm người dùng chọn.** Hiện chỉ nhóm nội bộ "HTH THU- CHI" (13 thành viên, nhóm thu chi công ty dùng sẵn). Danh sách chọn nằm ngoài repo (`D:\zalo-agent\wechat-groups.json`), thêm/bỏ bằng `zalo_agent wechat-add|wechat-remove <tên>`, xem bằng `wechat-list`. Nhóm chưa chọn thì không đọc, không lên `hao`.
3. **Đọc tại máy, chỉ đọc**, qua bộ đọc của `wechat-mcp-pilot` (`db_adapter.open_database()`) trong tiến trình con riêng, bằng venv riêng của dự án đó. Không điều khiển giao diện WeChat, không gửi tin, không đọc hay chép `private-state`.
4. **Không gửi chữ tin nào vào model.** Cùng luật của [`ZALO-GROUP-01`](zalo-group-01.md) (chỉ nhóm đã chọn rời máy; đường ssh chung), [`ANH-GEMINI-01`](anh-gemini-01.md) (chữ của tin không vào model nào) và `TELEGRAM-01` (nguồn thứ hai theo cùng khuôn kênh đẩy chung).
5. **Cùng gói chat, `hao` không phải sửa:** nhóm WeChat là một hội thoại bình thường ("WeChat · <tên>") trong gói `/srv/v7/zalo-bundle`; tin vào cùng `messages.jsonl` khi dựng đầy đủ và cùng `messages-delta.jsonl` giữa hai lần dựng, theo luật "bản mới nhất thắng".
6. Sửa câu "WeChat ngoài phạm vi" của [`ZALO-THU-CHI-01`](zalo-thu-chi-01.md): WeChat được đọc nhưng chỉ nhóm đã chọn; bot trả lời trong nhóm và nối ngân hàng vẫn ngoài phạm vi.

## Ngày / nguồn

20/11/2026, chat. Người dùng được thêm vào nhóm WeChat nội bộ nói trên (mới vào nên chỉ có tin từ lúc được thêm). Claude hỏi có đưa WeChat vào cùng đường đọc như Zalo không; người dùng chọn "Làm, đo nhóm này trước", rồi "Làm nguồn WeChat ngay".

## Hiệu lực và giới hạn

ĐÃ CHỐT 20/11/2026. ĐÃ KIỂM CHỨNG chỉ-đọc trên máy `msi` (số đếm trong nhật ký PR). Chưa bật: agent chưa chạy với `--wechat` trên máy thật.

Vẫn phải hỏi người dùng trước khi bật `--wechat` trong lệnh của task `ZaloAgent`, và trước khi thêm nhóm WeChat nào khác vào danh sách chọn.

CÒN MỞ:

- **Giải mã ảnh WeChat:** upstream có bộ giải mã `.dat` (`MediaDownloader`), nhưng khóa AES chỉ suy ra được từ cấu hình WeChat khi có `cfg_dword`; máy này chưa có, nên tin ảnh hiện "Ảnh WeChat (chưa đọc được)". Đường còn lại là quét bộ nhớ tiến trình Weixin.exe (chưa dùng, cần người dùng cho phép riêng). Cờ `--wechat-images` đã có nhưng mặc định tắt.
- **Tách tiền tệ RMB:** khoản có đơn vị tệ (元, 块, ¥, RMB, tệ) phải tách khỏi tổng VND ở trang Thu chi (`web/v7_cash_chat.py` chưa sửa; PR sau).
- **Nhóm chỉ có tin từ lúc được thêm vào:** lịch sử trước đó không có; số tin đo được còn ít nên chưa biết độ phủ mẫu `thu|chi|ứng`.
- **Máy chạy / máy canh:** `hao` mới liệt kê bộ xử lý `bundle`, `insurance`, `money_images`; dòng `wechat` trong `status.json` chưa hiện ở tab Máy chạy (PR sau).
- **Chưa có nhóm Zalo nào được chọn** thì `bundle` không chạy (cả hai nguồn dùng chung bản dựng); hiện luôn có nhóm Zalo nên chưa chặn.
