# CANH-BAO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chọn: **khi máy công nợ lỗi hoặc dừng thì báo qua email.** Khi không còn người nhập mở web hằng ngày, đây là cách duy nhất để biết máy đã ngừng theo Sheet.

Cách làm do Claude đặt:

1. **Một máy canh trên `hao`** (`v7_watchdog.py`, timer `v7-watchdog`, 15 phút một lần) kiểm tại chỗ, chỉ đọc:
   - web và DB còn trả lời (`/healthz`);
   - lượt đối soát còn mới, không báo lỗi ghi. Cùng luật "có thể cũ" với tab Việc cần làm: trong ngày quá 3 giờ, hoặc lúc nào cũng quá 14 giờ;
   - bản chụp Sheet không cũ quá 60 phút;
   - các timer còn bật; sao lưu không lỗi và không quá hạn;
   - đĩa còn trên 10% trống.
2. **Máy canh báo về một check trên healthchecks.io:** ổn thì ping thường, có việc thì ping `/fail` kèm danh sách. Dịch vụ đó gửi email tới tài khoản của chủ sổ khi chuyển sang lỗi và khi hết lỗi. **`hao` tắt hay mất mạng thì không còn ping, dịch vụ tự gửi email** sau thời gian chờ.
3. **Nội dung gửi đi chỉ có mã và số đếm,** không tên khách, không số tiền.

Chưa cấu hình link ping thì máy canh chỉ ghi journal, không làm gì khác.

**Vì sao không dùng cách khác:**

- Uptime Kuma nằm trên chính `hao`, nên `hao` tắt thì không báo được. `hao` là laptop 2011 không pin, đây là rủi ro thật.
- Gửi trực tiếp bằng Gmail phải để mật khẩu ứng dụng trên `hao`. Mật khẩu đó mở được cả hộp thư, trong khi link ping lộ ra chỉ làm báo sai.

**Không báo các việc sau**, vì không phải máy hỏng và đã có ở đầu tab Việc cần làm: khách cần xem, web đi trước Sheet, tab chưa tạo được sổ.

## Ngày / nguồn

4/11/2026, chat. Claude hỏi kênh cảnh báo khi máy lỗi hoặc dừng, người dùng chọn "Email". Audit DevOps 31/10/2026 mục 2 ghi "không có cảnh báo nào". Claude chọn healthchecks.io, gói miễn phí tới 20 check, theo các lý do trên.

## Hiệu lực và giới hạn

ĐÃ CHỐT kênh email. Chi tiết ở [spec](../../specs/v7-canh-bao.md), cách cài ở [runbook](../v7-deploy-runbook.md#máy-canh-báo-email-canh-bao-01--timer-v7-watchdog). Không đổi DB, quyền hay tiền. Không có tên khách trong nội dung gửi đi.

Giới hạn:

- Phải có người tạo tài khoản healthchecks.io và đặt link ping lên `hao`; Claude không tự tạo tài khoản.
- Đang báo lỗi mà có thêm lỗi khác thì không có email mới, vì dịch vụ chỉ gửi khi đổi trạng thái. Danh sách mới nhất nằm ở trang của check và ở journal.
- Lỗi lẻ tự lành trong ngưỡng thì không báo, có chủ đích để không nhiễu.
- Dịch vụ ngoài hỏng thì không có email. Tab Việc cần làm vẫn hiện trạng thái đối soát.
