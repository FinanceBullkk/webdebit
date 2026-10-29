# PHU-PHI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chốt phụ phí nhiều loại theo hướng C ([`specs/v7-phu-phi-nhieu-loai.md`](../../specs/v7-phu-phi-nhieu-loai.md)): danh mục loại phí dùng chung, mỗi chuyến nhiều dòng phụ phí, mỗi sổ chọn tối đa 3 loại hiện thành cột riêng, còn lại vào cột **Khác**. (1) **Chi hộ** chỉ là nhãn, vẫn cộng nợ khách như mọi phụ phí. (2) Phiếu/bảng đối soát gửi khách **hiện từng khoản** phụ phí (yêu cầu cho lúc làm phiếu gửi khách). (3) Phí theo lô/tháng ghi bằng **dòng phí lẻ** không container như hiện nay, có loại phí. (4) Giảm trừ là loại **"Giảm trừ"** nhận số âm; loại khác chỉ nhận số dương. (5) Danh mục ban đầu: Neo, Điện, Ghép, Health, Kiểm định, Bảo hiểm, Khác. (6) Sổ mặc định **chỉ có cột Khác**. (7) Dòng sổ gốc thêm/xóa được từng khoản. (8) Ba cột phí `G H I` trên tab khách **không có nghĩa cố định**: dán vào đều là Khác, phân loại tay sau. Bổ sung cùng ngày sau khi xem bộ lập bill (bảng chi phí phát sinh PS và bill gửi khách): (9) số trong bảng PS là **tiền tính cho khách**; (10) **Health cert** và **Kiểm định** không có giá cố định: web chỉ hiện cont nào có Health/Kiểm định, người nhập tự nhập giá; (11) ô PS có số quá nhỏ (ví dụ Ghép = "1") là **nhập sai**, không nhập tự động.

## Ngày / nguồn

28/10/2026, trả lời câu hỏi trong chat sau khi duyệt bản xem hướng C; (9)–(11) trả lời sau khi đọc bộ lập bill

## Hiệu lực và giới hạn

ĐÃ CHỐT chính sách. Chưa có Penpot, chưa code, chưa đổi schema; thiết kế backend và đường nhập từ bảng PS trong spec là ĐỀ XUẤT.
