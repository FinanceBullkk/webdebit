# Quy tắc nghiệp vụ v1 — 15/10/2026

Bản tóm tắt đã lọc các quy tắc người dùng xác nhận trong nguồn S17/S22/S23 và chỉ dẫn workspace; không duyệt thêm quy tắc. Người quyết định: người dùng/chủ nghiệp vụ; thời điểm và phạm vi ở [sổ quyết định](decisions.md). [Danh mục nguồn](source-register.md) giữ hash hồ sơ đối chiếu.

| Khái niệm | Quy tắc và phạm vi |
| --- | --- |
| Sổ hiện hành | Replay 13/10/2026 16:44 được chọn làm opening PostgreSQL. Sheet giữ lịch sử; không ghi ngược. Quyết định lịch sử không phải kiểm service hôm nay. |
| Lịch sử/opening | Dòng lịch sử đã nằm trong opening chỉ giải thích mở sổ, không cộng lần nữa vào biến động mới. |
| Khách/kỳ | Số dư truy theo khách + kỳ nợ + ngày chốt. Container không là khóa duy nhất, không tự gộp chuyến trùng container. |
| Ngày | Ngày nghiệp vụ chuyến là ngày xe nhập kho. Ngày nhập hệ thống, duyệt, ghi sổ và kỳ nợ giữ riêng. Backend đang lọc `posting_date`; chưa xác nhận đổi sang ngày nghiệp vụ. |
| Phê duyệt | Người nhập khác người duyệt. Approval gắn với đúng revision nội dung; thay đổi trường nghiệp vụ tạo revision mới và cần duyệt lại, không sửa đè revision đã gửi/duyệt. Chỉ khoản đủ tiền/loại/kỳ/nguồn/chứng cứ/phê duyệt hợp lệ mới ghi sổ. Danh tính người thật/quyền vận hành vẫn chưa được triển khai xác minh. |
| Charge chuyến mới | Hiện chưa có mã chuyến ổn định; chuyến thiếu mã phải CHỜ KIỂM, không suy định danh từ container/ngày/khách. Chưa chốt source key và đối chiếu opening 13/10/2026 16:44; ngày xe từ 14/10 trở đi không chứng minh chuyến chưa nằm trong opening. Chủ nghiệp vụ duyệt danh sách cấu phần và số tiền riêng cho từng chuyến, không dùng công thức chung; xác nhận gắn revision. `debt_period` xác nhận riêng và kỳ phải mở; xem [hợp đồng T1](../specs/p0-write-path/00-first-charge-contract.md). |
| Thu mới | Phân bổ kỳ nợ cũ trước. Không phân bổ lại lịch sử, không suy cùng receipt từ một hàng hoặc cùng số tiền. |
| Receipt/allocation | Tiền thực nhận khác phân bổ theo kỳ; cấn trừ, điều chỉnh tăng/giảm là loại riêng. Chứng từ tiền không tự chứng minh thu đã xác minh. |
| Pending | Nháp/chờ giá/chờ xác nhận/chờ duyệt nhìn thấy nhưng không đổi số dư đã ghi. |
| Tiền chưa rõ | VND nguyên chính xác, không làm tròn để ép khớp. Blank/NULL/chưa biết giữ là chưa biết, không tự dùng 0. |
| Sửa sai | Posting không sửa đè; đảo/điều chỉnh có lý do/audit, sau khi workflow được duyệt và kiểm. |
| Ngoại lệ | Giữ NO_BASELINE, chênh lịch sử 600đ, khoản thiếu giá. Tổng khớp hay nhãn KHỚP không chứng minh đủ nguồn từng kỳ/tiền ngân hàng. |

UI đặt chuyến và thu cạnh nhau để so sánh; chung hàng hiển thị không tạo quan hệ tất toán. Số fixture không là opening thật. Không áp dụng phương án trả dư/số âm chỉ vì prototype có lựa chọn đó.
