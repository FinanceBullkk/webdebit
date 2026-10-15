# Web đọc replay

**Trạng thái:** bộ xem chỉ đọc từ replay; DB/role thật cần cấp riêng. Xem [kiến trúc](../architecture.md).

- Luồng: HTTP request → `web/app.py:ViewerHandler` → hàm `render_*` → `web/db.py` → HTML.
- Kiểm: `cong-no-web-handoff/tests/test_web.py` dùng fake DB và cổng loopback ngẫu nhiên.
- Bất biến: trang nguồn/ngoại lệ phải giữ đường dẫn chứng cứ; thông tin chưa rõ hiển thị là chưa rõ.
- Giới hạn: HTTP test không chứng minh truy vấn DB/service thật hay quyền truy cập production.
