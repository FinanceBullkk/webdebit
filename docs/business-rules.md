# Quy tắc nghiệp vụ v1 — 15/10/2026

Bản tóm tắt đã lọc các quy tắc người dùng xác nhận trong nguồn S17/S22/S23 và chỉ dẫn workspace; không duyệt thêm quy tắc. Người quyết định: người dùng/chủ nghiệp vụ; thời điểm và phạm vi ở [sổ quyết định](decisions.md). [Danh mục nguồn](source-register.md) giữ hash hồ sơ đối chiếu.

| Khái niệm | Quy tắc và phạm vi |
| --- | --- |
| Sổ hiện hành | Replay 13/10/2026 16:44 được chọn làm opening PostgreSQL. Sheet giữ lịch sử; không ghi ngược. Quyết định lịch sử không phải kiểm service hôm nay. |
| Lịch sử/opening | Dòng lịch sử đã nằm trong opening chỉ giải thích mở sổ, không cộng lần nữa vào biến động mới. |
| Khách/kỳ | Số dư truy theo khách + kỳ nợ + ngày chốt. Container không là khóa duy nhất, không tự gộp chuyến trùng container. |
| Ngày | Ngày nghiệp vụ chuyến là ngày xe nhập kho. Ngày nhập hệ thống, duyệt, ghi sổ và kỳ nợ giữ riêng. Backend đang lọc `posting_date`; chưa xác nhận đổi sang ngày nghiệp vụ. |
| Phê duyệt | **Bãi bỏ theo V6 (18/10/2026):** không tách người nhập/duyệt; chuyến và khoản thu nhập xong là tính vào nợ, không có bước chốt tháng. Sửa số của tháng trước không sửa đè mà ghi dòng điều chỉnh có lý do và lưu vết. Xem [quyết định V6](../specs/ux-v6-quyet-dinh-2026-10-18.md). |
| Thu mới | Phân bổ kỳ nợ cũ trước. Không phân bổ lại lịch sử **trong opening (dữ liệu chuyển từ Sheet)**, không suy cùng receipt từ một hàng hoặc cùng số tiền. Trong sổ web, khi một tháng được điều chỉnh thì các khoản thu được **phân bổ lại theo nợ cũ trước** (V6-3d, 18/10/2026). |
| Receipt/allocation | Tiền thực nhận khác phân bổ theo kỳ; cấn trừ, điều chỉnh tăng/giảm là loại riêng. Chứng từ tiền không tự chứng minh thu đã xác minh. |
| Pending | Nháp/chờ giá/chờ xác nhận/chờ duyệt nhìn thấy nhưng không đổi số dư đã ghi. |
| Tiền chưa rõ | VND nguyên chính xác, không làm tròn để ép khớp. Blank/NULL/chưa biết giữ là chưa biết, không tự dùng 0. |
| Sửa sai | Posting không sửa đè; đảo/điều chỉnh có lý do/audit, sau khi workflow được duyệt và kiểm. |
| Ngoại lệ | Giữ NO_BASELINE, chênh lịch sử 600đ, khoản thiếu giá. Tổng khớp hay nhãn KHỚP không chứng minh đủ nguồn từng kỳ/tiền ngân hàng. |

UI đặt chuyến và thu cạnh nhau để so sánh; chung hàng hiển thị không tạo quan hệ tất toán. Số fixture không là opening thật. Số âm ở còn phải thu cuối tháng nghĩa là khách ứng trước, hiện số âm trần (V6, 18/10/2026).
