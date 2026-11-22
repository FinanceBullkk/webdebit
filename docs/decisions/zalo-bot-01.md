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

22/11/2026, chat.

1. Người dùng hỏi làm bot Zalo vào nhóm để thu ảnh và tin. Claude nêu bot chính thức chỉ nhận tin @nhắc trong nhóm, nên thu tin giữ đường `zalo-agent`, còn bot chỉ hỏi đáp.
2. Người dùng chọn hỏi tự do bằng AI và chỉ mình dùng thử.
3. Người dùng chọn zca-js với nick phụ, sau khi biết bot chính thức có gói Basic miễn phí.
4. Chưa có nick phụ, người dùng nói "bạn có thể tham khảo code và kỹ thuật trong repo đó để build cho chúng ta".

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng làm ngày 22/11/2026. Chưa code.

- Không thay [`ZALO-THU-CHI-01`](zalo-thu-chi-01.md) mục 1: thu tin vẫn qua `zalo-agent`. Đưa nick phụ vào nhóm khách hoặc dùng nick phụ để thu tin thì cần quyết định riêng.
- Không bao giờ chạy zca-js bằng nick làm việc với khách.
- Bot chỉ đọc. Tin chat không ghi tiền; tin chat của khách không vào model ([`ZALO-THU-CHI-01`](zalo-thu-chi-01.md) mục 3).

CÒN MỞ, chốt với người dùng trước khi bật (lúc người dùng tạo khóa API ở P0):

- **Q4:** trần chi phí (đề xuất 3 USD mỗi ngày trong lúc thử);
- **Q5:** dữ liệu gửi Anthropic theo từng câu hỏi (tên khách, mã sổ, số tiền, ngày, trạng thái).
