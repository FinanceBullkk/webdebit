# VCL-GIU-01 — Giữ giá web và giữ chuyến

ĐÃ CHỐT bởi người dùng trong chat ngày 2/11/2026: quyết định giữ có hiệu lực đến khi dòng liên quan trên Sheet đổi. Sửa dòng khác hoặc đọc lại cùng nội dung không làm mất quyết định.

- Lưu trên server theo ID sổ, loại việc, loại/ID dòng web và dấu nội dung nguồn; ghi người làm trong Lịch sử. Không phụ thuộc trình duyệt hay hash toàn bộ bản chụp.
- Giá: đối chiếu container, ngày, đơn giá, phụ phí và tổng của dòng giá nguồn; giữ phân biệt NULL với 0. Chỉ nhận dòng xung đột khớp duy nhất, không nhận dòng mơ hồ hoặc có phụ phí chi tiết cần xử lý riêng.
- Chuyến bị xóa trên Sheet: đối chiếu những dòng cùng container, kể cả dòng được chuyển sang sổ khác. Không dùng số thứ tự dòng hay thời gian đọc làm dấu nội dung.
- Giá hoặc thông tin chuyến web thay đổi thì cần đối chiếu lại. Quyết định chỉ ẩn việc cần xem, không đổi giá, chuyến, phiếu thu, phân bổ hay số dư. Tháng khóa vẫn giữ được vì không ghi tiền.
- Mất kết nối giữ nguyên khóa/yêu cầu; gửi lại trả kết quả lệnh cũ. Sổ hoặc dòng nguồn đổi trước khi xác nhận thì báo tải lại.

Phạm vi code: `keep_sheet_task`, hàng chờ giá/chuyến, Việc cần làm và nút Giữ trong sổ khách. Có migration, chưa áp vào DB thật. Triển khai theo gate migration hiện hành; chưa merge hoặc triển khai trong task này.

Kiểm: `test_v7_sheet_task_keep.py`, `test_pg_v7_backend_sheet_keep.py`, `test-viec-can-lam-table-browser.js`. Kết quả từng môi trường ghi trong PR; kiểm fixture không thay nghiệm thu dữ liệu thật.
