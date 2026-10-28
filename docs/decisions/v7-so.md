# V7-SO

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt màn sổ khách V7 theo tab sổ khách của Sheet đang dùng; V7 thay màn sổ khách của V6, không thay model tiền V6. V7 là màn một khách. **Ổ khóa từng tháng thay quy tắc ngày 5 của V6:** mặc định chỉ tháng hiện tại (giờ Việt Nam) mở, ai cũng mở/khóa được, mở/khóa không ghi Lịch sử. Tháng mở sửa đè trực tiếp; tháng khóa gõ số mới thì sinh dòng điều chỉnh theo hiệu số so với giá hiện hành. **Điều chỉnh không cần lý do**, tính tiền ngay, ghi chú tùy chọn, một chuyến được nhiều dòng điều chỉnh; có điều chỉnh cả tháng (số có dấu); cho phép tháng âm. Điều chỉnh, sửa giá, dán lô, đổi ngày phiếu thì phân bổ lại các phiếu chưa hủy theo nợ cũ trước (xếp theo ngày phiếu rồi mã phiếu). **Hủy phiếu bắt buộc lý do** và không phân bổ lại phiếu khác. Sửa tại chỗ ngày và hình thức của phiếu đã lưu, không sửa số tiền. Bốn hình thức thu: `THU TIỀN`, `CẤN TRỪ`, `ỨNG TRƯỚC`, `KHÁC`. Khách trả dư ghi trong sổ, hiện số âm. Ngăn Lịch sử riêng: thời điểm, người, loại thao tác, trước → sau

## Ngày / nguồn

19/10/2026, xác nhận trong chat; chi tiết ở `specs/v7-so-khach-theo-sheet.md` và `specs/v7-backend-so-khach.md` trên nhánh `codex/v7-opening-read` (được nhập vào bản chuẩn bị gộp này)

## Hiệu lực và giới hạn

(**Sửa 21/10/2026:** vế "mở/khóa không ghi Lịch sử" thay bởi [`V7-CSM`](v7-csm.md) (3): mỗi lần mở/khóa ghi một dòng Lịch sử; D04 hoàn tiền/ứng trước giữa các sổ chốt ở `V7-CSM` (1).) ĐÃ CHỐT **luật màn sổ và luật sửa số**. ĐÃ TRIỂN KHAI ở bản thử trong tab (`so-khach-v7-model.js`, nhánh trên); chưa có backend, chưa mở ghi tiền. Thay phần ngày đệm và "điều chỉnh có lý do" của `V6`. CÒN MỞ: điều chỉnh theo chuyến ở tháng mở (P2-4 của thiết kế backend); "khoản thu chưa chắc"; đổi tháng nợ của chuyến đã ghi; màn Tổng nhiều khách; ghi vết mở/khóa khi có kiểm toán; D04 (hoàn tiền, ứng trước giữa các sổ).
