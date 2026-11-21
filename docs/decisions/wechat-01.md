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

ĐÃ CHỐT 20/11/2026. ĐÃ KIỂM CHỨNG chỉ-đọc trên máy `msi` (số đếm trong nhật ký PR). ĐÃ TRIỂN KHAI trên `msi`:

- `--wechat` từ 22/11/2026 01:56 (người dùng bấm "Bật WeChat (chữ)"), một nhóm được chọn; `status.json` trên `hao` lúc 04:42 ngày 22/11 có bộ xử lý `wechat` không lỗi, 53 tin.
- `--wechat-images` từ 22/11/2026 04:12, chạy bản đầu của phần đọc ảnh (viết bằng Codex, chưa commit trong `D:\webdebit\repo`). Người dùng dán kết quả vào phiên Claude và giao Claude đưa vào repo ("Bạn làm luôn"). ĐÃ KIỂM CHỨNG 04:19 (đếm trong kho của agent): 12/12 tin ảnh có ảnh, nhưng 4 ảnh là ảnh thu nhỏ (cạnh dài 157–210 điểm ảnh).
- Bản trong repo (thử lại ảnh, nâng ảnh thu nhỏ, chặn gắn nhầm ảnh) thay bản đầu khi kéo `main` về `D:\webdebit\repo` rồi chạy lại task `ZaloAgent`.

Vẫn phải hỏi người dùng trước khi thêm nhóm WeChat nào khác vào danh sách chọn.

**Ảnh WeChat (22/11/2026):** đọc bằng khóa suy ngoại tuyến từ tên file `kvcomm` của WeChat và wxid, kiểm trên file `.dat` thật của máy; không quét bộ nhớ (các lượt quét bộ nhớ Weixin.exe trước đó không tìm ra khóa ảnh). Khóa vẫn chỉ ở máy, chỉ trong bộ nhớ của tiến trình đọc, không ghi vào file, log, repo, `status.json` hay `hao`. Tin ảnh còn thiếu ảnh được thử lại mỗi lượt cửa sổ; ảnh thu nhỏ được thay bằng bản lớn hơn khi WeChat có (không bao giờ lùi); lượt đầu sau khi agent chạy thử lại ảnh của 7 ngày. Ảnh chỉ được giải khi chắc đúng tin (số `local_id` lặp giữa các mảnh DB). Chi tiết: spec, mục nguồn WeChat. Việc đọc bộ nhớ để lấy khóa DB của upstream không đổi (`extract_master_key()` khi `cfg_dword is None`, `extract_keys()` khi có mảnh DB chưa có khóa; `db.py` khoảng dòng 715–728), nên bộ đọc vẫn giữ một tiến trình sống lâu để đọc một lần.

CÒN MỞ:

- **Ảnh còn thiếu cũ hơn 7 ngày** (khóa hỏng lâu rồi mới sửa) không tự bổ sung; phải làm tay.
- **Thu hồi chưa kiểm chứng với tin thật:** cách WeChat 4.x ghi thu hồi chưa quan sát được (nhóm chưa có tin thu hồi). Đã dựng cách an toàn cho cả hai khả năng (đọc lại cửa sổ 6 giờ, dòng bị sửa tại chỗ thành tin hệ thống thu hồi thì phát dòng xóa); cần một tin thu hồi thật để xác nhận.
- ~~**Tách tiền tệ RMB**~~ (xong ở PR-W2, #568): khoản có đơn vị tệ (元, 块, ¥, RMB, tệ) có `currency: "CNY"`, `amount_cny`, tổng riêng `totals.cny`, không vào tổng VND.
- **Nhóm chỉ có tin từ lúc được thêm vào:** lịch sử trước đó không có; số tin đo được còn ít nên chưa biết độ phủ mẫu `thu|chi|ứng`.
- ~~**Máy chạy / máy canh**~~ (xong): `hao` liệt kê `wechat` từ #568 (ổn hay lỗi, kèm số tin đã nhập); từ 22/11/2026 tab Máy chạy ghi "WeChat: Đang chạy, N tin đã nhập" và Zalo chưa mở không làm dòng WeChat thành "Zalo chưa mở" (WeChat đọc kho riêng).
- **Mất khóa ảnh không có cảnh báo:** `image_keys` chỉ nằm trong dòng `end` của tiến trình con, chưa lên `status.json`; khóa hỏng thì ảnh mới về "chưa đọc được" mà máy canh không báo.
- **Chưa có nhóm Zalo nào được chọn** thì `bundle` không chạy (cả hai nguồn dùng chung bản dựng); hiện luôn có nhóm Zalo nên chưa chặn.
