# Quyết định còn hiệu lực: đọc ở đâu

Chỉ là con trỏ, không chép nội dung quyết định. Nguồn sống là [`docs/decisions.md`](../docs/decisions.md) (mục lục, mỗi
quyết định một file) và [`docs/business-rules.md`](../docs/business-rules.md). Cập nhật 28/11/2026; bản 22/10/2026 tóm tắt nội
dung đã cũ, xem lịch sử Git.

| Khi sửa | Đọc trước |
| --- | --- |
| Tiền, số dư, FIFO, phụ phí trống, ngày ghi sổ | [`V7-BE`](../docs/decisions/v7-be.md), [`CAN-DU-01`](../docs/decisions/can-du-01.md), [`FUTURE-01`](../docs/decisions/future-01.md), [`OPENING-SO-GOC`](../docs/decisions/opening-so-goc.md) |
| Khóa tháng | [`V7-SO`](../docs/decisions/v7-so.md), [khóa tháng 24/10/2026](../docs/decisions/khoa-thang-2026-10-24.md), [`KHOA-CHU-01`](../docs/decisions/khoa-chu-01.md), [`V7-CSM`](../docs/decisions/v7-csm.md) |
| Người làm, đăng nhập, quyền trang | [`V7-ID`](../docs/decisions/v7-id.md), [`ACCESS-01`](../docs/decisions/access-01.md), [`QUYEN-01`](../docs/decisions/quyen-01.md); không có người duyệt thứ hai: [`V6-DB`](../docs/decisions/v6-db.md) |
| Chuyến vào sổ, khách mới | [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md), [`DU-CHUYEN-01`](../docs/decisions/du-chuyen-01.md), [`NHAP-SHEET-02`](../docs/decisions/nhap-sheet-02.md), [`KHACH-WEB-01`](../docs/decisions/khach-web-01.md) |
| Phiếu thu, cấn trừ | [`PHIEU-WEB-01`](../docs/decisions/phieu-web-01.md), [`CT-2SO`](../docs/decisions/ct-2so.md) |
| Sheet sổ nợ, máy theo Sheet, ngày 1/12 | [`WEB-CHINH-01`](../docs/decisions/web-chinh-01.md) (thay vế (1) của [`SONG-SONG-01`](../docs/decisions/song-song-01.md)), [`MAY-DOI-SOAT-01`](../docs/decisions/may-doi-soat-01.md) |
| Cảnh báo, kiểm định kỳ, đường lui | [`CANH-BAO-01`](../docs/decisions/canh-bao-01.md), [`LUOI-AN-TOAN-01`](../docs/decisions/luoi-an-toan-01.md), [`XUAT-SO-01`](../docs/decisions/xuat-so-01.md) |
| Cách Claude làm việc, triển khai lên `hao` | [`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md), [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md), [`TU-LAM-01`](../docs/decisions/tu-lam-01.md); không ghi dữ liệu sổ tiền: [`SO-TIEN-01`](../docs/decisions/so-tien-01.md) mục (5) |

Không suy trạng thái live từ tài liệu: kiểm lại trên `hao`.
