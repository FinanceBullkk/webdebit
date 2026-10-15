# Quy tắc nghiệp vụ v1 — 15/10/2026

Bản tóm tắt đã lọc các quy tắc người dùng xác nhận trong nguồn S17/S22/S23 và chỉ dẫn workspace; không duyệt thêm quy tắc. Người quyết định: người dùng/chủ nghiệp vụ; thời điểm và phạm vi ở [sổ quyết định](decisions.md). [Danh mục nguồn](source-register.md) giữ hash hồ sơ đối chiếu.

| Khái niệm | Quy tắc và phạm vi |
| --- | --- |
| Sổ hiện hành | Replay 13/10/2026 16:44 được chọn làm opening PostgreSQL. Sheet giữ lịch sử; không ghi ngược. Quyết định lịch sử không phải kiểm service hôm nay. |
| Lịch sử/opening | Dòng lịch sử đã nằm trong opening chỉ giải thích mở sổ, không cộng lần nữa vào biến động mới. |
| Khách/kỳ | Số dư truy theo khách + kỳ nợ + ngày chốt. Container không là khóa duy nhất, không tự gộp chuyến trùng container. |
| Ngày | Ngày nghiệp vụ chuyến là ngày xe nhập kho. Ngày nhập hệ thống, duyệt, ghi sổ và kỳ nợ giữ riêng. Trong payload charge ngày xe nhập kho dự kiến là trường `warehouse_in_date` (ĐỀ XUẤT, chưa cài; fixture tại `0e1330b` còn gọi `event_date`); `posting_date` là ngày ghi sổ. Backend viewer đang lọc `posting_date`; chưa xác nhận đổi sang ngày nghiệp vụ. |
| Phê duyệt | Người nhập khác người duyệt. Approval gắn với đúng revision nội dung; thay đổi trường nghiệp vụ tạo revision mới và cần duyệt lại, không sửa đè revision đã gửi/duyệt. Chỉ khoản đủ tiền/loại/kỳ/nguồn/chứng cứ/phê duyệt hợp lệ mới ghi sổ. Danh tính người thật/quyền vận hành vẫn chưa được triển khai xác minh. |
| Chuyến cũ | Chuyến có ngày xe nhập kho trước 14/10/2026 là chuyến cũ; nợ của chúng nằm trong opening 13/10 16:44, kể cả chuyến không có booking ([LEGACY-A, OPENING-FINAL](decisions.md)). Không cần mã chuyến, không nhập lại, không đẩy ra khỏi số dư. |
| Charge chuyến mới | Chỉ nhận chuyến có ngày xe nhập kho từ 14/10/2026. Mã chuyến = số booking + số container, viết hoa và bỏ mọi khoảng trắng ([TRIP-KEY](decisions.md)). Chuyến mới thiếu booking hoặc container phải CHỜ KIỂM; không suy định danh từ container/ngày/khách. Sổ opening không ghi booking: một chuyến chỉ được coi là vắng khỏi opening khi có resolution được chủ nghiệp vụ duyệt theo mã chuyến. Chủ nghiệp vụ duyệt danh sách cấu phần và số tiền riêng cho từng chuyến, không dùng công thức chung; maker được tự xác nhận giá nhưng người xác nhận giá không làm checker cùng revision ([PRICE-MAKER](decisions.md), ĐÃ CHỐT 16/10/2026). Cấu phần 0đ khi tổng > 0 và khớp chỉ là cảnh báo ([PRICE-ZERO](decisions.md), ĐÃ CHỐT 16/10/2026). Fixture chưa cài đúng các chính sách này (CÒN MỞ). `debt_period` xác nhận riêng và kỳ phải mở; xem [hợp đồng T1](../specs/p0-write-path/00-first-charge-contract.md). |
| Thu mới | Phân bổ kỳ nợ cũ trước. Không phân bổ lại lịch sử, không suy cùng receipt từ một hàng hoặc cùng số tiền. |
| Receipt/allocation | Tiền thực nhận khác phân bổ theo kỳ; cấn trừ, điều chỉnh tăng/giảm là loại riêng. Chứng từ tiền không tự chứng minh thu đã xác minh. |
| Pending | Nháp/chờ giá/chờ xác nhận/chờ duyệt nhìn thấy nhưng không đổi số dư đã ghi. |
| Tiền chưa rõ | VND nguyên chính xác, không làm tròn để ép khớp. Blank/NULL/chưa biết giữ là chưa biết, không tự dùng 0. |
| Sửa sai | Posting không sửa đè; đảo/điều chỉnh có lý do/audit, sau khi workflow được duyệt và kiểm. |
| Ngoại lệ | Giữ NO_BASELINE, chênh lịch sử 600đ, khoản thiếu giá. Tổng khớp hay nhãn KHỚP không chứng minh đủ nguồn từng kỳ/tiền ngân hàng. |

UI đặt chuyến và thu cạnh nhau để so sánh; chung hàng hiển thị không tạo quan hệ tất toán. Số fixture không là opening thật. Không áp dụng phương án trả dư/số âm chỉ vì prototype có lựa chọn đó.
