# ZALO-BOT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Làm bot hỏi đáp công nợ qua Zalo theo spec [`zalo-bot.md`](../../specs/zalo-bot.md).

Người dùng chọn ngày 22/11/2026:

1. Hỏi tự do bằng AI; bot hiểu toàn bộ dữ liệu và các trang của web.
2. Giai đoạn đầu chỉ người dùng dùng thử.
3. Kênh là zca-js (API Zalo Web không chính thức) với một nick Zalo phụ, không dùng bot chính thức của Zalo.
4. Build ngay, tham khảo mã và kỹ thuật của zalo-agent-cli. Người dùng chưa có nick phụ, nên phần chạy thử P0 chờ.

Claude chốt theo quyền người dùng trao 21/10, đúng đề xuất trong spec:

- **Q1:** chọn model bằng số đo. Chạy bộ câu hỏi mẫu trên Haiku 5.5, Sonnet 5.5 và Opus 5.5; người dùng chọn model khi có số.
- **Q2:** vòng gọi công cụ chạy ở tiến trình bộ não trên `hao`, gọi Messages API bằng SDK chính thức trong venv riêng; không dùng Managed Agents.
- **Q6:** nhật ký hỏi đáp giữ 90 ngày trên `hao`, không vào repo.
- **Q7:** truy vấn tự do (tầng C) chỉ làm sau khi tầng A và B đạt số đo, có spec con.
- **Q8:** chỉ chat riêng; không trả lời trong nhóm có khách; nick phụ không vào nhóm khách.

## Rủi ro đã nêu, người dùng chấp nhận

- zca-js không chính thức: nick dùng nó có thể bị khóa. Zalo đổi giao thức thì thư viện gãy tới khi có bản sửa. Hậu quả giới hạn ở nick phụ và việc hỏi đáp.
- Câu hỏi và câu trả lời nằm trong lịch sử chat Zalo của nick chính, như mọi tin chat.

## Ngày / nguồn

22/11/2026, chat. Q4, Q5: 24/11/2026, người dùng nhờ Claude chốt.

1. Người dùng hỏi làm bot Zalo vào nhóm để thu ảnh và tin. Claude nêu bot chính thức chỉ nhận tin @nhắc trong nhóm, nên thu tin giữ đường `zalo-agent`, còn bot chỉ hỏi đáp.
2. Người dùng chọn hỏi tự do bằng AI và chỉ mình dùng thử.
3. Người dùng chọn zca-js với nick phụ, sau khi biết bot chính thức có gói Basic miễn phí.
4. Chưa có nick phụ, người dùng nói "bạn có thể tham khảo code và kỹ thuật trong repo đó để build cho chúng ta".

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng làm ngày 22/11/2026. Mã đã merge (PR-1 đến PR-3c, sửa theo audit 23/11/2026), **chưa cài trên `hao`, chưa bật** (chờ nick phụ, P0).

- Không thay [`ZALO-THU-CHI-01`](zalo-thu-chi-01.md) mục 1: thu tin vẫn qua `zalo-agent`. Đưa nick phụ vào nhóm khách hoặc dùng nick phụ để thu tin thì cần quyết định riêng.
- Không bao giờ chạy zca-js bằng nick làm việc với khách.
- Bot chỉ đọc. Tin chat không ghi tiền; tin chat của khách không vào model ([`ZALO-THU-CHI-01`](zalo-thu-chi-01.md) mục 3).

## Q4, Q5 — ĐÃ CHỐT 24/11/2026

Người dùng nhờ Claude chốt (24/11/2026, qua phiên điều phối "Kiểm toàn bộ website"); Claude chốt đúng đề xuất trong spec. Phạm vi: bot hỏi đáp Zalo trong lúc người dùng thử; đổi model, trần hay danh sách trường cần quyết định mới.

- **Q4, trần chi phí:** 3 USD mỗi ngày trong lúc thử, tính theo ngày giờ Việt Nam. Chạm trần thì bot không gọi model, trả câu "Hôm nay đã hết hạn mức hỏi, mai hỏi lại giúp mình.", nhật ký và bộ đếm ghi `over_budget`, máy canh báo email. Mã: `Budget` (`tools/zalo_bot/budget.py`) cộng chi phí theo token thật mỗi lượt gọi; cấu hình chặn trần trên 3 USD (`CAP_MAX`). Một câu đang chạy có thể vượt trần tối đa một lượt gọi, vì trần kiểm trước mỗi lượt.
- **Q5, dữ liệu gửi Anthropic:** mỗi câu hỏi chỉ gửi đúng các trường cần để trả lời: tên khách, mã sổ, số tiền, ngày, trạng thái (kèm số đếm, mã lý do máy, tên địa điểm bảng giá, tên trò chuyện Zalo và đoạn trích tài liệu dự án như danh sách trong [spec Q5](../../specs/zalo-bot.md#câu-hỏi-cần-chốt)). Không gửi số điện thoại, số tài khoản ngân hàng, ảnh, tin chat của khách, ghi chú hay lý do gõ tay. Mã: danh sách giữ lại `KEEP` (`tools/zalo_bot/tools.py`, từ #608); khóa `reason`/`error` chỉ mang mã máy, chữ khác thành rỗng; test chặn các trường cấm ở mọi công cụ.
