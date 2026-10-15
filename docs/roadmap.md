# Roadmap web công nợ HTH

Cập nhật: 15/10/2026. Phạm vi: sổ công nợ phải thu; Google Sheet giữ nguồn lịch sử. Roadmap này theo **đầu ra có thể kiểm**, không dùng phần trăm hoàn thành hoặc ngày hẹn khi còn thiếu quyết định nghiệp vụ. Trạng thái service trên `hao` phải được kiểm lại trước khi báo là đang chạy.

| Mốc | Đầu ra và điều kiện đạt | Trạng thái hiện tại | Bằng chứng / việc còn thiếu |
| --- | --- | --- | --- |
| M0 · Nền dữ liệu | Snapshot có provenance, replay đối chiếu theo khách + kỳ, opening không cộng lại lịch sử | **Đã kiểm trên snapshot 13/10** | [Quy tắc](business-rules.md), [nguồn](source-register.md); giữ `NO_BASELINE`, chênh 600đ và khoản thiếu giá. Không suy thành Sheet/live hiện tại đã khớp. |
| M1 · Web xem sổ | Mở sổ theo khách/kỳ, thấy opening, biến động, pending và cảnh báo nguồn; người dùng truy cập được bản chỉ đọc | **Có pilot lịch sử; live chưa tái kiểm** | [Kiến trúc](architecture.md), [kiểm chứng](verification.md). Cần kiểm đúng service, DB, dữ liệu/as-of và đường truy cập dự kiến trước khi bàn giao bản xem. |
| M2 · Hợp đồng ghi an toàn | Quyết định cho loại giao dịch đầu tiên được chốt; spec/guard được review; fixture chứng minh từ chối sai revision, actor, tiền và rollback | **Đang review, chưa đủ hợp đồng ghi** | [Q01/Q02 prototype](../specs/p0-write-path/07-identity-revision-implementation.md) đạt [CI 8/8 trên `3925af1`](https://github.com/FinanceBullkk/webdebit/actions/runs/38710057538). [Q03–Q09](../specs/p0-write-path/decisions-needed.md) còn mở theo phạm vi; Q09 chặn receipt. Prototype chưa nối web/DB thật. |
| M3 · Web giao dịch trên bản sao | Account/session cá nhân, maker khác checker, API/DB transaction, idempotency và các guard P0 liên quan; test lỗi, retry, đồng thời trên PostgreSQL; đối chiếu số dư | **Chưa triển khai** | Cần review M2, migration riêng trên DB test, kiểm HTTP/auth và chứng cứ cho từng loại giao dịch. [P0-01–06](../specs/p0-write-path/README.md) là yêu cầu, chưa là code chạy thật. |
| M4 · Pilot vận hành và chuyển sổ | Truy cập Tailscale được kiểm, backup/restore, đối soát dữ liệu, hai người dùng thật thử quy trình; chủ nghiệp vụ duyệt phạm vi và thời điểm cutover | **Chưa triển khai** | Cần nghiệm thu M3 và gate vận hành riêng. Không tự freeze Sheet, deploy hay mở ghi tiền từ CI xanh. |

## Mốc gần nhất

1. Review độc lập thiết kế Q01/Q02 và chốt Q09 cùng các quyết định áp dụng cho giao dịch đầu tiên. Chủ trì: chủ nghiệp vụ/kế toán và người review kỹ thuật.
2. Tái kiểm bản xem chỉ đọc trên môi trường dự kiến dùng; ghi service revision, nguồn/as-of, quyền truy cập và các cảnh báo còn mở. Chủ trì: vận hành + người giữ sổ.
3. Sau hai việc trên, chọn phạm vi M3 và lập ước lượng có điều kiện. Chưa có ngày cam kết cho web ghi/duyệt thật.

## Cách cập nhật tiến độ

Chỉ đổi trạng thái mốc khi có link đến quyết định hoặc kết quả kiểm **đúng revision và môi trường**. Mỗi cập nhật ghi ngày, đầu ra đã kiểm, việc chặn và người chịu trách nhiệm tiếp theo. [Verification](verification.md) giữ log kỹ thuật; [decisions](decisions.md) giữ chính sách; roadmap chỉ tổng hợp trạng thái. Nhánh `feature/p0-actor-revisions` đã push nhưng chưa merge; PR #1–#4 còn Draft tại lần kiểm 15/10/2026. `main` chưa chứa prototype Q01/Q02.
