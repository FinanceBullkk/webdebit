"""Bot Zalo hỏi đáp công nợ (ZALO-BOT-01, specs/zalo-bot.md): bộ não chạy trên hao.

Tiến trình kênh (Node, zca-js, thư mục `kenh/`) giữ phiên nick phụ và chuyển tin qua socket Unix; gói này kiểm từng dòng kênh gửi,
quyết định trả lời, ghi nhật ký và nhịp tim. PR-1 chỉ trả câu cố định; bộ não gọi model và công cụ đọc API ở PR-2.
"""

VERSION = "0.1.0"
