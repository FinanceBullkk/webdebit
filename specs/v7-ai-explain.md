# AI giải thích một ngoại lệ đối soát

Trạng thái: ĐỀ XUẤT / đã làm trên nhánh `codex/ai-exception-explain`; chưa triển khai `hao`.

## Kết quả cần thấy

Ở Việc cần làm, mở một khách lệch và bấm **Giải thích với AI**. Web hiện đúng gói dữ liệu một khách sắp gửi Anthropic: tổng Sheet/web, phần web đi trước, lý do máy, tối đa 12 nhóm và 30 dòng giá/phiếu có số hàng nguồn. Người dùng bấm **Đồng ý gửi và hỏi Claude** thì mới dùng API credit. Câu trả lời nêu quan sát, giả thuyết, hàng cần kiểm và phần chưa biết; không có nút AI nào ghi sổ.

## Đường đi và ranh giới

| Thao tác | Mã | Kiểm |
| --- | --- | --- |
| Mở đối chiếu | `preview/viec-can-lam.js`, `v7_api_doi_chieu.statement` | Test bảng đối chiếu hiện có |
| Xem trước AI | `GET /api/v7/ai/preview` → `v7_ai_explain.preview` | Một customer ID; bỏ ghi chú, giới hạn nhóm/dòng; không gọi Claude |
| Đồng ý gửi | `POST /api/v7/ai/explain` → `v7_ai_explain.explain` | Same-origin, actor Tailscale, `consent: true`, fingerprint khớp gói được dựng lại, 5 lượt/giờ và cách nhau 60 giây mỗi actor |
| Trả lời | Anthropic Messages API trực tiếp trên server | API key chỉ ở server; 512 output tokens; lỗi trả mã an toàn; không lưu nội dung câu hỏi/trả lời |

Không đổi máy đối soát, thuật toán ghi, DB, Sheet, quyền hiện có hoặc quy tắc tài chính. Thay đổi ở Webdebit UI chỉ dùng khi có API key server. Key có thể đọc từ file do `WEBDEBIT_ANTHROPIC_KEY_FILE` trỏ tới (trên Linux phải là mode 600); không đưa key vào repo, browser hoặc URL. Mỗi lần POST kiểm lại dữ liệu; nếu phiên bản sổ hoặc snapshot thay, trả 409 để xem trước lại. Prompt đánh dấu dữ liệu Sheet là dữ liệu, không phải chỉ dẫn. Chứng cứ bị cắt có `partial: true`.

## Chứng cứ và giới hạn

Kiểm bằng fixture: thiếu consent, fingerprint cũ và giới hạn lượt không gọi Claude; một yêu cầu hợp lệ gọi đúng một lần; không gọi lệnh DB ghi. Chạy `npm run check` và kiểm trình duyệt theo luồng nút trước khi coi code đạt. Live API/Claude và `hao` chỉ được xác nhận sau khi cài key và kiểm trên service thật. AI không được dùng làm căn cứ tự ghi tiền; kết quả máy đối soát vẫn là nguồn số học.

## Bật trên `hao` sau khi duyệt

Triển khai release trước, để nút gửi ở trạng thái khóa khi chưa có key. Người vận hành đặt API key vào tệp ngoài release/repo, chỉ user chạy service đọc được, mode `600`; cấu hình `WEBDEBIT_ANTHROPIC_KEY_FILE` trỏ đến tệp đó và restart service theo runbook. Không đặt key trong lệnh shell, URL, Git, log hay file môi trường của repo. Kiểm `GET /api/v7/ai/preview?customer=ID` với một ngoại lệ được chọn: `enabled: true`, gói đúng khách, không chứa ghi chú hoặc quá 30 dòng. Chỉ chủ sổ bấm đồng ý sau khi xem gói mới gọi Claude và dùng credit. Nếu chưa có ngoại lệ cần giải thích, chờ lượt đối soát có ca phù hợp; không tạo dữ liệu tài chính giả trên production.
