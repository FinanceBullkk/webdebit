# Sổ quyết định v1

| ID | Quyết định / người quyết định | Ngày / nguồn | Hiệu lực và giới hạn |
| --- | --- | --- | --- |
| W01 | Người dùng chọn GitHub để dev/AI phát triển chung, checkout chính trong workspace | 15/10/2026, xác nhận chat hiện tại | ĐÃ CHỐT quy trình; không đồng nghĩa đã push/CI đã chạy. |
| OPENING | Người dùng chọn replay làm opening độc lập, Sheet là lịch sử | 13/10/2026, S17 | ĐÃ CHỐT; nguồn có triển khai lịch sử, không tái nhập vào biến động mới. |
| D01 | Người dùng chốt tách người nhập/duyệt | S17, chỉ dẫn workspace | ĐÃ CHỐT nguyên tắc; cấp quyền và workflow thật CÒN MỞ. |
| Q01-SCOPE | Người dùng chốt self-host trên máy này; cần kết nối Tailscale với người dùng trước khi vào màn hình đăng nhập | 15/10/2026, xác nhận trong chat hiện tại | ĐÃ CHỐT phạm vi máy đơn và tailnet là điều kiện mạng để truy cập. Chưa quyết định tài khoản/identity riêng, role maker-checker, ACL/tài khoản chia sẻ hoặc cách ứng dụng xác minh actor từ Tailscale; các phần đó CÒN MỞ. Tailscale reachability tự nó không là audit approval. |
| Q02 | Người dùng chốt approval gắn với revision bất biến; mọi thay đổi nội dung nghiệp vụ tạo revision mới và phải duyệt lại. Chỉnh sửa chỉ trình bày, không đổi nghĩa nghiệp vụ, không cần duyệt lại. | 15/10/2026, xác nhận trong chat hiện tại | ĐÃ CHỐT quy tắc nghiệp vụ; chưa triển khai. Revision bao gồm nội dung tài chính/đối tượng/kỳ/ngày/nguồn/chứng cứ và dữ liệu quyết định; approval cũ không áp dụng cho revision mới. Không tự suy ra quyền/auth người thật. |
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
