# THONG-TIN-CTY-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web có tab **Thông tin cty**, chỉ xem, lấy dữ liệu từ Google Sheet "thông tin khách hàng" của công ty (tab `THÔNG TIN CTY`: shipper, thông tin xuất hóa đơn, ngân hàng của khách; tab `TÀI KHOẢN USD`: các tài khoản nhận tiền). Hộp debit note mẫu v4 chọn khách và tài khoản nhận tiền từ danh bạ này. Spec: [`specs/v7-thong-tin-cty.md`](../../specs/v7-thong-tin-cty.md).

1. **Sheet là nơi sửa duy nhất.** Một job trên `hao` (`webdebit-company-info.timer`, mỗi giờ, user `v7app`, tài khoản dịch vụ chỉ đọc) đọc hai tab và ghi bản chụp ngoài repo; web chỉ đọc bản chụp. Mã Sheet chỉ nằm trong file biến môi trường trên `hao`.
2. **Dữ liệu không đi qua repo hay chat**: repo public chỉ có code và dữ liệu giả.
3. **Debit note**: chọn khách thì điền khối thông tin xuất hóa đơn vào *Tên pháp lý và địa chỉ*; chọn tài khoản thì PAYMENT INFORMATION in theo tài khoản đó (ghi đè cấu hình máy chủ cho riêng chứng từ). Không tự chọn tài khoản thay người lập; chưa chọn thì cảnh báo cần xác nhận. Trình duyệt nhớ lựa chọn theo sổ.
4. Ngân hàng của khách (cột E) chỉ hiện ở tab, không in lên debit note.

## Ngày / nguồn

12/11/2026, chat: người dùng cần danh sách khách và thông tin ngân hàng để chọn khi xuất debit note mà không lộ thông tin; đề xuất dùng runner đọc Sheet, gửi link Sheet, chọn "Cả hai" (khách từ `THÔNG TIN CTY`, tài khoản từ `TÀI KHOẢN USD`) và "Một ô nhiều dòng" cho cột hóa đơn, rồi đề xuất tab Thông tin cty trên web và "Làm đi". Cách đọc, giờ chạy, cảnh báo khi chưa chọn tài khoản do Claude chọn theo [`CLAUDE-ALL-01`](claude-all-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Code theo PR; job cần cài tay trên `hao` theo [runbook](../v7-deploy-runbook.md#thông-tin-cty-thong-tin-cty-01--timer-webdebit-company-info) và Sheet phải chia sẻ Viewer cho tài khoản dịch vụ. CÒN MỞ: địa chỉ HTH trong `debit-note-config.default.json` ("20/21/15 Le Cong Phap") khác địa chỉ ở khối tài khoản trên Sheet (số nhà đảo thứ tự, tên đường viết khác), chờ người dùng xác nhận bản đúng; Sheet sửa xong chậm tối đa một giờ mới lên web.
