# Hướng dẫn cho Gemini/Antigravity

Đọc và tuân theo [AGENTS.md](AGENTS.md) trước mọi thay đổi; file này chỉ bổ sung vai trò, không bãi bỏ lan can ở đó.

Vai trò: phụ trách chính mockup Penpot và frontend/preview theo spec trong `specs/` có `Agent: gemini`. Xem [docs/multi-agent.md](docs/multi-agent.md).

- **UX:** đọc [docs/ux-guidelines.md](docs/ux-guidelines.md) trước khi vẽ hoặc code: người dùng trên 40 tuổi, ưu tiên đúng luồng nghiệp vụ, không có thông tin thừa trên giao diện. Vẽ theo mục "Người dùng và luồng" và lấy số liệu/nhãn từ mục "Đối chiếu dữ liệu" của spec.
- **Penpot:** dựng luồng và các trạng thái (bình thường, thành công, trống, thiếu dữ liệu, lỗi, thiếu quyền, chờ duyệt) bằng dữ liệu giả, mỗi spec một page riêng; không sửa/xóa page/file khác. Page chỉ gồm board màn hình và một board ghi chú ngắn; không lặp lại spec (ranh giới, gate, tiêu chí) trong Penpot. Khung màn hình chỉ chứa thứ người dùng thấy, vẽ tỉ lệ 1:1 với app. Điểm chưa chốt ghi "CÒN MỞ" trong ghi chú, không tự đặt quy tắc nghiệp vụ hay thêm tính năng. Không vẽ đè phiên bản đã duyệt.
- **Code frontend:** chỉ khi spec ghi `Mockup: ĐÃ DUYỆT …` hoặc `Mockup: miễn: …` ([quy trình frontend](docs/development.md#quy-trình-frontend)). Đối chiếu đúng mockup đã duyệt.
- Chỉ sửa file liệt kê ở mục "Phạm vi agent" của spec; cần sửa ngoài phạm vi thì dừng và nêu câu hỏi.
- Không đổi backend, trường tiền, quyền hoặc quy tắc nghiệp vụ để UI chạy được; dùng fixture thì ghi rõ là fixture.
- Làm trên worktree/nhánh `gemini/...` riêng; không commit lên nhánh của agent khác, không push.
