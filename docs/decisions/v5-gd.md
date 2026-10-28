# V5-GD

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt bản ghép V5 đang có trong repo làm mốc giao diện đã duyệt của sổ công nợ

## Ngày / nguồn

18/10/2026, xác nhận trong chat sau khi xem ảnh chụp màn hình

## Hiệu lực và giới hạn

ĐÃ CHỐT **bố cục, câu chữ và ngữ nghĩa hiển thị** của `cong-no-web-handoff/preview/so-cong-no-v5.html` + `so-cong-no-v5-ui.js` tại merge `790fa1e`; đổi bố cục hoặc câu chữ từ đây cần quyết định mới. ĐÃ KIỂM CHỨNG ở mức bản thử chạy trong tab: `npm run test:unit` 17/17 PASS (18/10/2026), 18 trạng thái chụp đã review hai tầng. CÒN MỞ: người dùng chưa tự đi ba luồng trên bản thử; bốn điểm còn mở trong `specs/v5-giao-dien.md` (`../specs/v5-giao-dien.md`, hồ sơ nhánh nguồn, chưa nhập) chưa chốt; không có backend, không mở đường ghi tiền, không thay nghiệm thu lớp 3. **Sửa 18/10/2026:** mục này ghi khi hiểu nhầm ảnh người dùng duyệt là trang trong repo. Phần còn hiệu lực: model tiền, các guard chốt tháng, cách hiển thị tiền và trạng thái chứng từ. Phần **hết hiệu lực**: bố cục khoản thu — thay bởi `V6`.
