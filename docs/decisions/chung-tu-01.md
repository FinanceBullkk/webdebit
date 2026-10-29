# CHUNG-TU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt làm **dán chứng từ vào phiếu thu** trước, chưa tích hợp Zalo/WeChat (không có API chính thức cho chat cá nhân và nhóm, dễ bị khóa tài khoản):

1. Người nhập dán (Ctrl+V), kéo thả hoặc chọn ảnh chuyển khoản (VND hoặc RMB) vào phiếu thu khi ghi mới hoặc sau khi ghi. **Chỉ đính ảnh, web không đọc số.** Người nhập vẫn gõ ngày, hình thức, số tiền. Ảnh RMB: số tiền ghi VND thực nhận, RMB và tỷ giá ghi ở tham chiếu (`V7-CSM` (2)).
2. Ảnh không đổi số tiền, phân bổ hay tháng khóa, và không có nghĩa là tiền đã về. Gỡ ảnh bắt buộc lý do, ghi Lịch sử, không xóa hẳn. Phiếu hủy giữ ảnh, chỉ xem.
3. Một ảnh đính vào phiếu ở hai sổ được, chỉ cảnh báo. Mọi người vào app đều xem được ảnh.
4. Chỉ giữ bản nén nhẹ (Claude chọn theo quyền người dùng giao): cạnh dài ≤ 2400 px, ≤ 2 MB, tối đa 5 ảnh mỗi phiếu. Ảnh không gửi ra dịch vụ ngoài `hao`.

Spec: [`specs/v7-dan-chung-tu.md`](../../specs/v7-dan-chung-tu.md); bản xem dữ liệu giả [`preview/mockups/dan-chung-tu`](../../cong-no-web-handoff/preview/mockups/dan-chung-tu/index.html).

## Ngày / nguồn

29/10/2026, chat: người dùng hỏi tích hợp Zalo/WeChat, chọn "build cái dán chứng từ trước", trả lời ba câu hỏi phạm vi, rồi duyệt bản xem ("Duyệt, làm tiếp").

## Hiệu lực và giới hạn

ĐÃ CHỐT luồng và phạm vi. Chưa code, chưa triển khai. Cách lưu ảnh (bảng PostgreSQL riêng) là đề xuất kỹ thuật trong spec; migration vẫn hỏi người dùng trước khi merge và chạy trên `hao`. Đọc số từ ảnh, Zalo OA/WeChat và đối chiếu sao kê ngân hàng CÒN MỞ, làm sau.

**Cập nhật 29/10/2026:** backend (migration + hàm + API) ĐÃ TRIỂN KHAI trên `hao` bằng đợt tay, xem [nhật ký](../deploys/2026-10-29-bang-gia-chung-tu.md). Giao diện dán/xem/gỡ ảnh trên sổ khách ĐÃ CODE (`so-khach-v7-images-ui.js`, test trình duyệt giả); triển khai qua auto-deploy khi PR giao diện merge. CÒN MỞ: người dùng tự dán ảnh thật trên bản thử.
