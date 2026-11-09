# PS-HOI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng phản ánh "Phụ phí PS cần xem" không hiểu là gì và không biết làm gì. Từ nay khung này là **danh sách câu hỏi có nút trả lời**:

1. Mỗi dòng nói bằng câu PS ghi gì, sổ khách tính gì (ví dụ "PS ghi 1.500.000 đ phụ phí, sổ khách chưa thu"; "PS ghi Khác = 315789.5, không phải số đồng nguyên nên máy không đọc"), rồi một câu hỏi ("Có thu thêm khách khoản này không?") và cách làm nếu trả lời ngược lại.
2. Nút **"… hết báo"** (Không thu / Sổ khách đúng / Không tính / Bỏ qua, tùy câu) ghi một dòng Lịch sử `sheet_conflict_resolved` với `task_ps`, **không đổi tiền**. Dòng đó ẩn tới khi ô PS của dòng hoặc đơn giá/phụ phí của chuyến trên web đổi, khi ấy máy hỏi lại.
3. Nhiều cont cùng một câu (một khoản PS chia cho nhiều cont) gom một khối, một nút cho cả nhóm.
4. Có thu thì làm như mọi khi: ghi phí trên tab khách ở Sheet (sổ chính thức theo [SONG-SONG-01](song-song-01.md)); web tự cập nhật. Web không cộng tiền theo PS ([MAY-PS-01](may-ps-01.md)).
5. Không trả lời được bằng nút: tháng khóa (máy tự tách lượt sau), container khớp nhiều chuyến, thiếu loại phí trong danh mục.

## Ngày / nguồn

9/11/2026, chat (ảnh 6 dòng "Khác = 315789.5 không đọc được" của LINSHUN). Đo chỉ đọc `ps.json` trên `hao`: 8 dòng `PS_BAD_AMOUNT`, đều là `315789.5` ở cột Khác của CHI PHÍ PS tháng 7 (một khoản chia đều cho nhiều cont); tab khách không thu. Trước đó 5/11 người dùng đã trả lời một ca tương tự (OTPU6666931 không thu) mà web không có chỗ ghi.

## Hiệu lực và giới hạn

ĐÃ CHỐT theo yêu cầu người dùng. Migration [`2026-11-09-v7-ps-khong-thu.sql`](../../cong-no-web-handoff/tools/migrations/2026-11-09-v7-ps-khong-thu.sql) chỉ cho `keep_sheet_task` nhận thêm `task_kind = 'ps'`. Máy không tự trả lời thay người.
