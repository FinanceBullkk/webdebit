# SO-GON-03

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng thấy sổ khách V7 "rất nhiều thông tin về tiền và rất rối": mỗi tháng cùng một số tiền hiện 2–3 lần (phát sinh = tổng Thành tiền; đã thu và còn nợ ở cả thanh tháng lẫn dòng Tổng tháng; nợ các tháng trước = còn nợ của tháng ngay trên). Người dùng đồng ý phương án Claude đề xuất: **mỗi số tiền của tháng hiện một lần**.

1. **Thanh tháng** (dính đầu khi cuộn) chỉ còn tên tháng, ổ khóa và **Còn nợ cuối tháng**. Rê chuột vào số này thấy cách tính: nợ các tháng trước + phát sinh − đã thu.
2. **Dòng Tổng tháng** chỉ cộng cột: các cột phụ phí, Thành tiền, **Đã thu** (vùng phiếu thu). Bỏ "Còn nợ" ở dòng này.

Điểm này thay phần "thanh tháng ghi bốn số" và "dòng Tổng tháng ghi còn nợ cuối tháng" trong mục (3) của [`SO-GON-02`](so-gon-02.md); phần bỏ cột "Còn nợ cộng dồn" giữ nguyên.

## Ngày / nguồn

29/10/2026, góp ý trong chat kèm ảnh chụp sổ khách; người dùng trả lời "đồng ý" với bản phác Claude đưa.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi phần hiển thị của trang live (`so-khach-v7-ui.js`, `so-khach-v7-live.html`). Không đổi luật tiền, API hay DB: các số vẫn lấy nguyên từ GET (`prior_months_vnd`, `charges_vnd`, `received_vnd`, `end_of_month_vnd`). Trang mẫu fixture `so-khach-v7.html` và các mockup cũ giữ nguyên.
