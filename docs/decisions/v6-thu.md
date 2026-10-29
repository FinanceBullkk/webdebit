# V6-THU

[← Sổ quyết định](../decisions.md)

## Quyết định

(**HẾT HIỆU LỰC 19/10/2026** — người dùng chọn gõ tiền thu ở cột tiền bên phải theo `V6`; bố cục bảng thu riêng không dùng. Giữ dòng này để còn truy được vì sao có `specs/v6-bang-thu-rieng.md` và `specs/v6-model-phan-bo-tung-khoan.md`.) Người dùng chốt tách **khoản thu thành bảng riêng** dưới bảng chuyến, theo wireframe người dùng tự dựng ngoài Penpot: nhập khoản thu chỉ ở dòng trống đầu bảng thu (bỏ các cột thu trên dòng chuyến); mỗi khoản có Ngày thực nhận · Cách thu · Tham chiếu · Số tiền · Trạng thái · Phân bổ; bấm xem phân bổ thì bung ngay dưới dòng, liệt kê từng kỳ nợ bị trừ; khoản thu nằm ở bảng thu của **tháng nhận tiền**, cột Phân bổ ghi rõ nó trừ cho kỳ nào

## Ngày / nguồn

18/10/2026, xác nhận trong chat; mốc hình tại `cong-no-web-handoff/preview/mockups/ux-v6-bang-thu-rieng-chatgpt.png` (`../cong-no-web-handoff/preview/mockups/ux-v6-bang-thu-rieng-chatgpt.png`, hồ sơ nhánh nguồn, chưa nhập)

## Hiệu lực và giới hạn

ĐÃ CHỐT **bố cục và luồng nhập khoản thu**; thay phần tương ứng của `V5-GD`. Chưa triển khai. Giữ nguyên `V5-UX` và `D03`: khoản thu thuộc sổ + kỳ nợ, thu mới trừ nợ cũ trước, không phân bổ lại lịch sử, khoản chưa có ngày thực nhận không vào số dư. Người dùng duyệt wireframe ngoài Penpot nên lần này **miễn bước mockup Penpot**; miễn trừ chỉ áp dụng cho thay đổi này. CÒN MỞ: ai được xác nhận chứng từ và căn cứ gì; sửa/xóa một khoản thu đã lưu; tiền dư. Không mở đường ghi tiền.
