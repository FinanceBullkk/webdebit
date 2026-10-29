# CT-2SO

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt cấn trừ giữa hai sổ: chọn `CẤN TRỪ` ở sổ được trả nợ thì chọn sổ lấy tiền trong danh sách mọi sổ đang dư (sổ cùng khách lên đầu); vượt số dư của sổ lấy tiền thì chặn; giữ lựa chọn Ngoài sổ (chỉ trừ sổ đang ghi); mockup tính năng này làm HTML qua ChatGPT thay Penpot, người dùng vẫn duyệt trước khi code giao diện. Sau khi soát mockup vòng 1: cấn quá số nợ của sổ nhận thì cho phép (phần thừa thành `ỨNG TRƯỚC`); mỗi sổ một mã phiếu theo dãy `PH-` riêng; hủy cặp hỏi lý do ngay trong bảng như hủy phiếu V7

## Ngày / nguồn

20/10/2026, xác nhận trong chat (hai lượt); chi tiết tại [`specs/can-tru-hai-so.md`](../../specs/can-tru-hai-so.md)

## Hiệu lực và giới hạn

ĐÃ CHỐT sáu điểm nghiệp vụ/giao diện và đường mockup. Thay mặc định D04 "dư nằm lại trong sổ" **chỉ** cho cấn trừ hai sổ; hoàn tiền và chuyển dư khác vẫn thuộc D04. Người dùng duyệt mockup (vòng 3, 21/10/2026; danh sách sổ lấy tiền xếp A→Z, chưa nhóm); mockup lưu ở `cong-no-web-handoff/preview/mockups/can-tru-hai-so/`. Model đọc hợp đồng backend đã thêm vào `so-khach-v7-model.js` kèm `planOffsetPreview` (BigInt, chỉ để hiện số dư sau cấn trừ trong khung xác nhận; server vẫn kiểm lại dưới khóa, Claude chốt theo quyền người dùng trao 21/10/2026); giao diện thật trong sổ khách V7 (`so-khach-v7-ui.js`, `so-khach-v7-api.js`) đã nối ba lệnh cấn trừ và đọc danh sách sổ nguồn, ĐÃ KIỂM CHỨNG bằng test node và Playwright 1280×720 với máy chủ giả (dữ liệu giả; chưa chạy với PostgreSQL/`hao`, chưa triển khai). ĐỀ XUẤT (chờ duyệt cùng mockup): ghi hai sổ một lệnh, hủy cả cặp, phiếu cấn trừ cũ là Ngoài sổ. **Chốt 21/10/2026:** không khóa nhận "cùng khách" — cho chọn bất kỳ sổ nào đang dư làm sổ lấy tiền (đúng mục đích cấn trừ giữa các khách khác nhau); danh sách chỉ ưu tiên xếp sổ cùng khách lên đầu, không giới hạn lựa chọn.
