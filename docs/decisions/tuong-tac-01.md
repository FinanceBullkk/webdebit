# TUONG-TAC-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Khối Thu tháng của Bảng thu và thẻ Tình hình của trang khách dùng chung một cách tương tác: **bấm là lọc hoặc mở chi tiết ngay tại chỗ, có cách bỏ rõ ràng, rồi mới có nút Mở sổ.** Ba hành vi người dùng chốt, thay hành vi cũ:

1. **Bấm một tháng trên hình 12 tháng của Tình hình thì ghim tháng đó tại chỗ:** hiện số của tháng, có nút Mở sổ, và Hoạt động chỉ còn tháng đó. Không nhảy thẳng sang thẻ Sổ nữa.
2. **Bấm tên khách ở các tab gom nhóm của Bảng thu (Theo khách, Theo mặt hàng, Theo tháng nợ) thì mở phiếu của khách ngay tại dòng.** Mũi tên cuối dòng và link trong phần mở mới mở sổ. Tab Theo ngày vẫn bấm dòng là mở sổ, vì mỗi dòng đã là một phiếu.
3. **Dải ngày hiện ở mọi tab của Bảng thu trừ 12 tháng.** Bấm một ngày thì số lớn, chip và bảng chỉ còn ngày đó; bộ lọc giữ khi đổi tab.

Chi tiết hành vi và trạng thái ở [spec](../../specs/v7-tuong-tac.md). Không đổi số tiền, luật phân bổ, cách tính tháng của [`BANG-THU-01`](bang-thu-01.md) hay luật rủi ro của [`DASH-03`](dash-03.md).

## Ngày / nguồn

5/11/2026, chat. Người dùng đưa ảnh hai khối, nói "chưa có interactive", yêu cầu dựng lại bằng Claude Design. Sau khi xem trang Tương tác của canvas, người dùng chọn đủ ba hành vi trên theo đề xuất của Claude. Hướng chung nối tiếp lựa chọn 29/10/2026 cho Tổng quan: lọc tại chỗ có chip ✕, xem nhanh trước khi Mở sổ.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Triển khai tự động khi merge qua `Deploy hao`. Chỉ đổi trang, không có migration, không ghi tiền. Trễ trung bình sau hạn vẫn hiện `—` và không bấm được cho tới khi có B1 ([`TRANG-KHACH-01`](trang-khach-01.md)). CÒN MỞ: người dùng tự đi hết luồng trên `hao`.
