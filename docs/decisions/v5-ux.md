# V5-UX

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt 9 điểm thiết kế sổ công nợ sau review mockup V5: khoản thu thuộc sổ (khách × loại hàng) + kỳ nợ chứ không thuộc chuyến; không có cột số lượng; thành tiền = đơn giá + ba loại phí do hệ thống cộng; ô phí trống nghĩa là không phát sinh; cho chốt tháng khi còn chứng từ chưa xác nhận; bỏ dòng chuyến đã lưu thì bỏ cả chứng từ chưa xác nhận trên đó; khách trả dư hiện số âm kèm chữ phải trả lại, tiền dư nằm lại trong sổ

## Ngày / nguồn

17/10/2026, xác nhận trong chat; chi tiết tại `specs/ux-v5-quyet-dinh-2026-10-17.md` (`../specs/ux-v5-quyet-dinh-2026-10-17.md`, hồ sơ nhánh nguồn, chưa nhập)

## Hiệu lực và giới hạn

ĐÃ CHỐT phạm vi **thiết kế màn hình và ngữ nghĩa số liệu**. Không phải migration, không mở đường ghi tiền, không thay nghiệm thu backend. Chỉ phần hiển thị/ngữ nghĩa của D04 được chốt; gate D04 (hoàn tiền, tranh chấp, tín dụng/ứng trước, tiền chưa phân bổ ở mức ghi sổ) vẫn mở, D05/D06 vẫn mở. Việc bỏ chứng từ theo dòng chỉ áp dụng cho chứng từ **chưa xác nhận**; khoản đã xác nhận/đã phân bổ chỉ xử lý bằng đảo có lưu vết.
