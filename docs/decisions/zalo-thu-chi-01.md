# ZALO-THU-CHI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ngày 19/11/2026 theo đề xuất của Claude, spec [`zalo-thu-chi-real-time.md`](../../specs/zalo-thu-chi-real-time.md):

1. **Không dùng "con bot add vào nhóm" để đọc.** Đọc nhóm Zalo bằng đường của [`ZALO-GROUP-01`](zalo-group-01.md): máy có Zalo đọc dữ liệu Zalo PC tại chỗ, chỉ nhóm đã chọn rời máy. Lý do:
   - Zalo Bot chính thức đang thử nghiệm phần nhóm và chỉ nhận tin @nhắc.
   - Bot bằng nick cá nhân dễ bị khóa.
   - WeChat cá nhân không có bot chính thức.
2. **Gần thời gian thực.** Tin của nhóm đã chọn lên web trong 30 giây khi máy có Zalo bật. Đường đẩy dùng lại kênh ssh và thư mục G5, đẩy phần thêm. Không thêm DB, không đổi Tailscale. Máy canh báo email khi đường Zalo ngừng quá 15 phút trong giờ làm việc.
3. **Trang Thu chi chỉ đọc.** Trang đọc tin theo mẫu `thu|chi|ứng <số> <đối tượng>` rồi đối chiếu với phiếu thu và sổ Đội xe. **Tin chat không bao giờ ghi tiền**, và nội dung chat không đi vào model nào.

Tám câu Q1–Q8 của spec:

- **Q1:** lập nhóm Zalo nội bộ "Thu chi"; nhóm khách thêm theo danh sách P0.
- **Q2:** bắt gõ theo mẫu trong nhóm Thu chi.
- **Q3:** ai vào được web thì xem được trang Thu chi.
- **Q4:** đọc ảnh bằng OCR ngay trên máy có Zalo, giữ [`CHUNG-TU-01`](chung-tu-01.md) mục 4. **Thay ngày 20/11/2026** bởi [`ANH-GEMINI-01`](anh-gemini-01.md): ảnh của nhóm đã chọn gửi ra Gemini qua hai đường rồi so kết quả.
- **Q5:** máy có Zalo bật 7:00–20:00.
- **Q6:** đối chiếu từ 1 ngày trước tới 3 ngày sau ngày báo.
- **Q7:** nối ngân hàng để sau, làm spec riêng.
- **Q8:** tách riêng loại `ứng`.

## Ngày / nguồn

19/11/2026, chat. Sếp hỏi cần "một cái WeChat hoặc Zalo" để gửi phiếu thanh toán, thu chi vào, để "con bot" đọc được tình hình thu chi thực tế. Sau đó sếp nói rõ: muốn một con bot add vào các nhóm chat. Claude tra khả năng bot của Zalo và WeChat, đánh giá đường ZALO-GROUP-01 rồi đề xuất real-time + thu chi. Người dùng chọn "Spec real-time + thu chi", đọc spec (FinanceBullkk/webdebit#533) và trả lời "Chốt theo đề xuất".

## Hiệu lực và giới hạn

ĐÃ CHỐT 19/11/2026. Chưa code, chưa triển khai; bước đầu là P0 (đo chỉ đọc ở máy có Zalo). Hai việc vẫn phải hỏi người dùng trước:

- thay task 15 phút bằng tiến trình chạy nền (PR-1);
- chọn nhóm đưa lên web.

Bảng xác nhận (PR-3) nằm ngoài đường tiền, triển khai theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md).

CÒN MỞ:

- engine OCR;
- danh sách nhóm (sau P0);
- khoảng ngày cho chi Đội xe (người nhập Đội xe xác nhận);
- bot trả lời trong nhóm, WeChat, nối ngân hàng (ngoài phạm vi).
