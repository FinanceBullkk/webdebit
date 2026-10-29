# V7-COPY

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt cho sổ V7 và bản sao dữ liệu thật: (1) cờ/guard kỹ thuật của khâu nạp (`NO_BASELINE`, chênh 600đ, ngày đảo, lệch cột, ngày ngoài tháng, "khác"…) được xử lý ở khâu nạp và chỉ giữ trong DB và báo cáo nạp, **không hiện trên sổ người dùng**; sổ chỉ hiện điều người dùng phải làm (ô "chưa có giá", khách chưa có số dư đầu thì chưa ghi được); (2) tháng có lịch sử trong số dư đầu hiện thêm dòng "Theo sổ gốc" (phát sinh, đã thu, còn nợ cuối tháng của Sheet) dưới "Cộng tháng", chỉ để đối chiếu, số dư vẫn từ bucket; dòng lịch sử hiện đúng các cột như Sheet; (3) quy tắc đọc Sheet: dòng lịch sử giữ ô TOTAL của Sheet kể cả thiếu đơn giá (chỉ cờ thiếu giá); ô "SỐ DƯ THÁNG CHUYỂN SANG" trống hoặc không có thì coi là 0 nhưng luôn kiểm bằng số còn phải thu cuối tháng của Sheet, lệch thì giữ khách; danh sách CSV cũ thiếu dòng so với file xuất chỉ ghi cờ; (4) tổng khớp Sheet mà cách chia tháng của bảng số dư đầu khác FIFO từ Sheet thì bản sao chia theo Sheet

## Ngày / nguồn

20/10/2026, xác nhận trong chat khi xem bản sao dữ liệu thật

## Hiệu lực và giới hạn

ĐÃ CHỐT. **Sửa 23/10/2026:** phần hiển thị (2) (dòng "Theo sổ gốc") thay bởi [`SO-GON-01`](so-gon-01.md). **Thay phần "hiển thị (tô màu)" của [`V7-BE`](v7-be.md) (5)**; phần "giữ cờ, không chặn khi phép tính đúng" vẫn hiệu lực. ĐÃ TRIỂN KHAI ở bản sao cô lập `127.0.0.1:8782` (nhánh `codex/v7-opening-read`, commit `4a3ea1b`); số đếm nguồn giữ ngoài Git; chưa phải nghiệm thu nghiệp vụ, chưa đụng `hao`/Sheet. CÒN MỞ: khách bị giữ và cách chia tháng của số dư đầu; chi tiết giữ ngoài Git.
