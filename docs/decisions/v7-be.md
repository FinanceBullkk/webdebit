# V7-BE

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt cho backend V7: (1) chuyến **đã có đơn giá** mà phụ phí để trống thì phụ phí tính 0, giá trị lưu vẫn NULL; thiếu đơn giá vẫn là chưa biết, ngoài số dư, giữ cờ thiếu giá; (2) bucket số dư đầu mỗi tháng theo nợ còn lại sau thu FIFO, không theo hiệu hai mỏ neo; mỏ neo đầu khác 0 vào bucket tháng đầu; tổng bucket bằng đúng mỏ neo cuối của khách; (3) dòng phí lẻ không container, không đơn giá, có phụ phí được để trống ngày nghiệp vụ (`event_date` NULL), tháng nợ vẫn bắt buộc; chuyến thường thiếu ngày bị từ chối; (4) số dư đầu tự chuyển "đã kiểm" rồi "hiệu lực" khi mọi kiểm tra cơ học đạt, không có bước người ký nhận; (5) cờ `NO_BASELINE`, thiếu giá, chênh 600đ và ngoại lệ nguồn được giữ và hiển thị (tô màu), không chặn khi phép tính đúng; (6) giữ số âm nguyên trong sổ; khoản trả mới chỉ trừ tháng có nợ dương theo thứ tự cũ trước, bỏ qua tháng âm

## Ngày / nguồn

20/10/2026, xác nhận trong chat; chi tiết ở `specs/v7-backend/thiet-ke.md` (mục 1, 3, 7.18 và "Quyết định đã chốt bổ sung") trên nhánh `codex/v7-opening-read`

## Hiệu lực và giới hạn

ĐÃ CHỐT **nghĩa tiền và gate** cho các trường hợp nêu; không duyệt import hay ghi tiền thật. (1) là **ngoại lệ có phạm vi** của quy tắc "NULL/blank không phải 0": chỉ phụ phí của chuyến đã có đơn giá; mọi chỗ khác NULL vẫn là chưa biết, chứng cứ số tiền NULL vẫn không đoán thành 0 (cùng hướng `V5-UX` "ô phí trống nghĩa là không phát sinh"). Gate cơ học (tổng, FIFO, chuỗi mỏ neo) vẫn bắt buộc. Chưa triển khai; theo thiết kế nháp, harness PostgreSQL chưa chạy lại sau vòng sửa cuối. CÒN MỞ: luật `TRIP-DATE-01` (chặn `p_event_date` NULL) cần ngoại lệ cho dòng phí lẻ khi mã V7 vào nhánh này; chuyển tiền âm giữa các sổ; hoàn tiền.
