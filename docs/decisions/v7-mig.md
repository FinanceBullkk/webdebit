# V7-MIG

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt chuyển dữ liệu: migrate và làm sạch từ Sheet đang dùng theo **phương án lai** — số dư đầu theo khách × tháng còn nợ lấy từ mỏ neo "SỐ CÒN PHẢI THU CUỐI THÁNG"; tháng còn nợ/tháng mở hiện chi tiết lịch sử, tháng cũ đã trả đủ chỉ để xem; dòng lịch sử giữ ô tổng của sổ gốc, dòng nhập mới trên web cộng đơn giá + phụ phí; dòng không container, không ngày nhưng có tiền cộng vào phát sinh của tháng khối như phí lẻ. **Phương án A:** chạy lại thu trừ nợ cũ trước trên các khối tháng để chia mỏ neo thành nợ từng tháng; tổng các tháng phải bằng mỏ neo, lệch thì cách ly

## Ngày / nguồn

19/10/2026, xác nhận trong chat; chi tiết ở `specs/v7-migration-sheet.md` và `specs/v7-backend/thiet-ke.md` trên nhánh `codex/v7-opening-read`

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng. Thiết kế backend (lược đồ mới `sokhach`, dòng lịch sử tách khỏi chuyến/thu, không maker/checker) là ĐỀ XUẤT; chưa chạy migration, chưa đụng `hao`/Sheet từ thiết kế này. CÒN MỞ: cách V7 dùng opening đã nạp theo [`OPENING-SO-GOC`](opening-so-goc.md); chứng cứ đủ dòng nguồn (manifest); một khách nhiều tab; hình thức thu từ ghi chú; giờ đóng băng; quy trình chuyển lại ở mốc thứ hai.
