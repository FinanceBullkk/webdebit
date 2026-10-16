# Sổ quyết định v1

| ID | Quyết định / người quyết định | Ngày / nguồn | Hiệu lực và giới hạn |
| --- | --- | --- | --- |
| W01 | Người dùng chọn GitHub để dev/AI phát triển chung, checkout chính trong workspace | 15/10/2026, xác nhận chat hiện tại | ĐÃ CHỐT quy trình; không đồng nghĩa đã push/CI đã chạy. |
| OPENING | Người dùng chọn replay làm opening độc lập, Sheet là lịch sử | 13/10/2026, S17 | ĐÃ CHỐT; nguồn có triển khai lịch sử, không tái nhập vào biến động mới. |
| D01 | Người dùng chốt tách người nhập/duyệt | S17, chỉ dẫn workspace | ĐÃ CHỐT nguyên tắc; cấp quyền và workflow thật CÒN MỞ. |
| Q01 | Người dùng chốt self-host trên máy này; phải nối vào tailnet của chủ máy mới vào được màn hình đăng nhập. Theo yêu cầu người dùng chọn phương án phù hợp nghiệp vụ, mỗi người có tài khoản ứng dụng riêng; Tailscale chỉ là cổng mạng, session server-side là nguồn actor. Không dùng chung tài khoản; maker và checker phải là hai người/tài khoản khác nhau. | 15/10/2026, xác nhận phạm vi trong chat; lựa chọn mô hình theo yêu cầu người dùng | ĐÃ CHỐT phạm vi máy đơn, Tailscale gate và mô hình danh tính ứng dụng riêng theo từng người. Tài khoản, mật khẩu/session lifecycle, phân quyền/cấp-thu hồi, ánh xạ actor ứng dụng sang audit DB và cấu hình proxy vẫn cần thiết kế/kiểm chứng trước khi triển khai. Nếu hiện chỉ có một người thì không được tự duyệt/post; cần checker khác. Kết nối Tailscale tự nó không là audit approval. |
| Q02 | Người dùng chốt approval gắn với revision bất biến; mọi thay đổi nội dung nghiệp vụ tạo revision mới và phải duyệt lại. Chỉnh sửa chỉ trình bày, không đổi nghĩa nghiệp vụ, không cần duyệt lại. | 15/10/2026, xác nhận trong chat hiện tại | ĐÃ CHỐT quy tắc nghiệp vụ; chưa có implementation production. Prototype acceptance riêng ở [P0-02](../specs/p0-write-path/07-identity-revision-implementation.md) đã chạy trên fixture PostgreSQL, không thay đổi schema hay service thật. Revision bao gồm nội dung tài chính/đối tượng/kỳ/ngày/nguồn/chứng cứ và dữ liệu quyết định; approval cũ không áp dụng cho revision mới. Không tự suy ra quyền/auth người thật. |
| CHARGE-01 | Người dùng/chủ nghiệp vụ chốt hợp đồng cho một charge chuyến mới: đối chiếu không trùng opening, xác nhận riêng kỳ nợ và xác nhận giá theo revision; thiếu/lệch nguồn hoặc giá thì chờ ngoài số dư. | 15/10/2026, xác nhận trong chat gốc và giao T1 | ĐÃ CHỐT trong phạm vi [hợp đồng T1](../specs/p0-write-path/00-first-charge-contract.md); chưa triển khai hay kiểm chứng. Định danh chuyến chốt riêng ở TRIP-KEY; không quyết định danh mục cấu phần giá hoặc cách cài đặt. |
| TRIP-KEY | Người dùng/chủ nghiệp vụ chốt mã chuyến ổn định = số booking + số container của chuyến, chuẩn hóa bằng cách viết hoa và bỏ mọi khoảng trắng. Áp dụng cho chuyến có booking. Chuyến không có booking ở CHỜ KIỂM, ngoài số dư; chủ nghiệp vụ quyết sau. | 15/10/2026, xác nhận trong chat hiện tại, sau khi kiểm chỉ đọc tab booking của sheet vận hành (ID và dữ liệu giữ ngoài repo) | ĐÃ CHỐT định danh cho chuyến có booking. Cơ sở: trong bản booking ngày 15/10, 5.283 cặp booking + container không trùng, còn một container có thể thuộc nhiều booking. Container, ngày hoặc khách đơn lẻ vẫn không là khóa. Sổ công nợ lịch sử không ghi booking: bảng nối dòng opening 13/10 ↔ mã chuyến là ĐỀ XUẤT, lưu trong hồ sơ có quyền riêng ngoài repo, chỉ có hiệu lực khi chủ nghiệp vụ duyệt; quy tắc chọn booking theo ngày khi container có nhiều booking chưa được duyệt. CÒN MỞ: định danh chuyến không có booking; chặn trùng theo chuyến hay theo chuyến + loại phí khi một chuyến có nhiều khoản; xử lý booking bị sửa sau khi ghi; định dạng lưu mã. Chưa triển khai trong fixture/app/DB; M2 vẫn chưa đạt. |
| DATE | Người dùng làm rõ ngày xe nhập kho là ngày nghiệp vụ chuyến | 14/10/2026, S22/S23 | ĐÃ CHỐT; có ở preview, chưa kiểm backend/runtime đã đổi. |
| D03 | Người dùng xác nhận thu mới giảm kỳ nợ cũ trước | 14/10/2026, S22/S23 | ĐÃ CHỐT nguyên tắc, có test fixture; đồng thời/ngoại lệ/backend thật chưa nghiệm thu. |

## Gate chưa đóng

Nguồn S15R ghi thiết kế `NOT_ACCEPTED_FOR_FINANCIAL_WRITES`. Tóm tắt này không thay hợp đồng chi tiết để xây đường ghi tiền.

- D04: tiền dư, số âm, tiền chưa phân bổ, tín dụng/ứng trước, tranh chấp và hoàn tiền.
- D05/D06: chứng cứ xác minh receipt/cấn trừ, chính sách VND/tỷ giá được duyệt.
- D07: nhập muộn, kỳ khóa, mở lại và phiếu điều chỉnh; ảnh hưởng ngày chốt.
- P0: procedure ghi tiền atomic; approval đúng phiên bản/nội dung/danh tính; cap allocation/FIFO dưới ghi đồng thời; idempotency cùng key khác payload; đảo chính xác, khóa kỳ, snapshot phiếu.
- Vận hành: người duyệt riêng, role/auth, DB integration, nghiệm thu và quyền deploy riêng.

Probe DDL đơn phiên đã tái hiện thiếu guard. Không coi fixture, CHECK/FK, command thành công hoặc báo cáo cũ là nghiệm thu các mục trên. Quyết định mới ghi người chốt, ngày, phạm vi, ví dụ cạnh biên, code/test tác động và liên kết bằng chứng có quyền riêng.
