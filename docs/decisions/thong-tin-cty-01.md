# THONG-TIN-CTY-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web có tab **Thông tin cty**, chỉ xem, lấy dữ liệu từ Google Sheet "thông tin khách hàng" của công ty (tab `THÔNG TIN CTY`: shipper, thông tin xuất hóa đơn, ngân hàng của khách; tab `TÀI KHOẢN USD`: các tài khoản nhận tiền). Hộp debit note mẫu v4 chọn khách và tài khoản nhận tiền từ danh bạ này. Spec: [`specs/v7-thong-tin-cty.md`](../../specs/v7-thong-tin-cty.md).

1. **Sheet là nơi sửa duy nhất.** Một job trên `hao` (`webdebit-company-info.timer`, mỗi giờ, user `v7app`, tài khoản dịch vụ chỉ đọc) đọc hai tab và ghi bản chụp ngoài repo; web chỉ đọc bản chụp. Mã Sheet chỉ nằm trong file biến môi trường trên `hao`. Người dùng không phải chủ Sheet gốc nên không chia sẻ được cho tài khoản dịch vụ; người dùng chọn (12/11/2026, "Tạo Sheet cầu") một Sheet cầu trong Drive của mình lấy hai tab bằng `IMPORTRANGE`, chia sẻ Viewer cho tài khoản dịch vụ, thay vì đặt tài khoản Gmail cá nhân lên `hao` (đọc được mọi Sheet của người dùng).
2. **Dữ liệu không đi qua repo hay chat**: repo public chỉ có code và dữ liệu giả.
3. **Debit note**: ô *Chọn từ Thông tin cty* nằm ở khối **Công ty phát hành (đầu trang)**: chọn một công ty thì đầu trang in tên, địa chỉ, MST, điện thoại, email tách từ bản shipper (tiếng Anh; trống thì bản xuất hóa đơn), bỏ dấu khi in; không chọn thì theo cấu hình máy chủ. BILL TO vẫn do người lập điền (người dùng sửa 12/11/2026: "thông tin cty phải thay cái này mới đúng, chứ k phải là chỗ bill to", kèm ảnh đầu trang HTH). Chọn tài khoản thì PAYMENT INFORMATION in theo tài khoản đó (ghi đè cấu hình máy chủ cho riêng chứng từ). Không tự chọn tài khoản thay người lập; chưa chọn thì cảnh báo cần xác nhận. Trình duyệt nhớ lựa chọn theo sổ.
4. Ngân hàng của khách (cột E) chỉ hiện ở tab, không in lên debit note.

## Ngày / nguồn

12/11/2026, chat: người dùng cần danh sách khách và thông tin ngân hàng để chọn khi xuất debit note mà không lộ thông tin; đề xuất dùng runner đọc Sheet, gửi link Sheet, chọn "Cả hai" (khách từ `THÔNG TIN CTY`, tài khoản từ `TÀI KHOẢN USD`) và "Một ô nhiều dòng" cho cột hóa đơn, rồi đề xuất tab Thông tin cty trên web và "Làm đi". Cách đọc, giờ chạy, cảnh báo khi chưa chọn tài khoản do Claude chọn theo [`CLAUDE-ALL-01`](claude-all-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Code theo PR; job cần cài tay trên `hao` theo [runbook](../v7-deploy-runbook.md#thông-tin-cty-thong-tin-cty-01--timer-webdebit-company-info) và Sheet phải chia sẻ Viewer cho tài khoản dịch vụ. Địa chỉ HTH: cấu hình cũ ghi "20/21/15 Le Cong Phap, … Binh Tan District", khác khối tài khoản trên Sheet; người dùng chốt theo Sheet (chat 12/11/2026, "Theo Sheet"): "21/20/15 Le Cong Phep Street, An Lac Ward, Ho Chi Minh City, Vietnam", sửa ở `debit-note-config.default.json` (mẫu v4) và bên phát hành HTH của mẫu v3. Còn lại: Sheet sửa xong chậm tối đa một giờ mới lên web.
