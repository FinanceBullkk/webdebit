# THONG-BAO-01 — Thông báo nổi thay băng vàng ở Sổ khách

Trạng thái: ĐÃ CHỐT hướng (người dùng, 13/11/2026: "thông báo hiện ở đó hơi nhà quê… tắt được thì ok hơn", rồi "thiết kế UX UI cho phù hợp và hiện đại nhất"). Phạm vi: chỉ trang Sổ khách live (`so-khach-v7-live.html`). Không đổi luật tiền, API hay câu chữ của từng thông báo.

## Bài toán

- Trước: mọi tin (xong việc, lỗi, cảnh báo, tình trạng kéo dài) dồn vào một băng vàng `.live-notice` ở đầu thẻ Sổ, màu đặt cứng, không tắt được, đẩy bảng xuống và nằm lại tới lần báo sau.
- Người dùng chính trên 40 tuổi, màn 1280×560 hữu dụng: băng chiếm một hàng của sổ mỗi lần ghi.
- Không dùng thông báo của trình duyệt/Windows (Notification API): phải xin quyền, hiện ngoài trang lẫn với ứng dụng khác, dễ bị tắt hẳn và lỡ lỗi về tiền.

## Thiết kế

Chia theo loại tin, không theo nơi phát ra:

| Loại | Nhận biết (theo câu, `CongNoThongBao.kindOf`) | Cách hiện |
|---|---|---|
| Xong | bắt đầu "Đã …", không kèm lưu ý | Nổi góc dưới trái vùng trang, nền trắng, dấu ✓ xanh, tự tắt sau 5–12 giây theo độ dài, có thanh đếm mỏng; rê chuột/tab vào thì dừng đếm |
| Cần xem | "Đã …" kèm *chưa / không tải được / trùng / chờ kiểm / tải lại / lệch / thiếu*; hoặc câu chặn khác ("Sổ vừa thay đổi…", "Tháng … còn ô đang sửa…") | Nổi, nền vàng nhạt, dấu ⚠, **không tự tắt** |
| Lỗi | "Không … được", "Chưa rõ …", "… không hợp lệ" | Nổi, nền đỏ nhạt, `role="alert"`, **không tự tắt** |
| Tình trạng kéo dài | Sheet không đọc được; khách chưa có số dư đầu; còn lệnh chưa rõ kết quả | Băng gọn `.book-status` ở đầu thẻ Sổ (viền trái màu, biểu tượng), mất khi tình trạng hết; lệnh chưa rõ có nút "Thử lại thao tác vừa gửi" ngay trong băng |

- Một thông báo nổi một lúc; tin mới thay tin cũ. Nút × (32px) và phím Esc tắt. Không lấy tiêu điểm khi hiện (không cắt ô đang gõ).
- "Đã lưu." trơn vẫn không báo (kết quả đã thấy trên dòng, góp ý 23/10/2026).
- Vị trí góc dưới trái (cách thanh điều hướng 16px) để không đè ngăn kéo ghi phiếu thu, phụ phí và khung Lịch sử ở bên phải. Dưới 760px trải ngang đáy màn.
- Nằm ngoài `#app` nên vẽ lại sổ (tự tải 60 giây) không làm thông báo nháy hay mất.
- Giảm chuyển động (`prefers-reduced-motion`): bỏ hiệu ứng vào và thanh đếm; in sổ: ẩn.

## Tiêu chí xong

- [x] Tin xong việc hiện nổi và tự tắt; tin lỗi/cần xem giữ tới khi bấm ×.
- [x] Băng vàng cũ không còn; tình trạng kéo dài hiện ở `.book-status`.
- [x] Lệnh chưa rõ kết quả: băng đỏ có nút Thử lại, bấm gửi lại đúng lệnh.
- [x] Các test trình duyệt Sổ khách đọc chữ thông báo ở `.live-notice` vẫn xanh; thêm test cho tự tắt, giữ lỗi, nút ×.
- [ ] Người dùng tự đi luồng ghi trên `hao` và nhận xét (bước cuối `UX-NEN-01`).
