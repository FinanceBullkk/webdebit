# PLAN — hiện tại (5/11/2026)

Mục tiêu gần nhất: **web tự chạy theo Sheet, không cần người nhập thao tác trên web** ([`MAY-DOI-SOAT-01`](docs/decisions/may-doi-soat-01.md), người dùng chốt 4/11/2026), và giữ đối soát khớp liền một tháng theo [`SONG-SONG-01`](docs/decisions/song-song-01.md). Tháng song song đầu tiên là tháng 11/2026, lần xét đầu là đối soát cuối tháng 11 (F2, ĐÃ CHỐT 5/11).

So với bản 31/10: máy tự đối soát mỗi giờ từ 7 tới 22 giờ trên `hao`, và tự sửa khi đúng một tổ hợp việc đưa tổng khách về đúng tổng Sheet tới từng đồng; kết quả ở đầu tab Việc cần làm ([nhật ký](docs/deploys/2026-11-04-may-doi-soat.md)). Việc còn lại chủ yếu là **vận hành và quyết định của chủ sổ**.

## Việc còn lại trước khi coi là chạy được không cần người

| # | Việc | Ai | Trạng thái 4/11 | Bằng chứng cần |
| --- | --- | --- | --- | --- |
| A2 | Web khớp tổng từng khách với Sheet | Máy, mỗi giờ | Lượt 14:45: 238/238 khớp, gồm 2 sổ mới máy vừa tạo ([`MAY-TAO-SO-01`](docs/decisions/may-tao-so-01.md), [nhật ký](docs/deploys/2026-11-04-may-tao-so.md)) | `reconcile-log.jsonl` trên `hao`; đối soát cuối tháng khớp |
| Cảnh báo | Máy lỗi hoặc dừng thì có người biết (audit DevOps #2) | Chủ sổ chọn kênh, Claude cài | CHƯA: hiện chỉ thấy ở đầu tab Việc cần làm và journal | Một lần thử cảnh báo tới được người nhận |
| E1 | Một lần kết luận CHỜ KIỂM thật trên `hao` | Chủ sổ | Nút đã có; chờ lần phát sinh đầu | Dòng Lịch sử của lần kết luận |
| F2 | Chốt ngày tính tháng song song | Chủ nghiệp vụ | ĐÃ CHỐT 5/11: tính cả tháng 11, từ 1/11/2026 | [`SONG-SONG-02`](docs/decisions/song-song-02.md) |
| F4 | Cách chuyển hẳn khi Sheet vẫn là nơi nhập | Chủ nghiệp vụ | Chưa chuyển, giữ Sheet; xét lại sau đối soát cuối tháng 11 | [`CHUYEN-HAN-01`](docs/decisions/chuyen-han-01.md); quyết định chuyển hẳn sau lần xét |

B1, B2 (mỗi người nhập một tài khoản) và C4 (người nhập tự chạy đối soát) không còn chặn theo hướng này; xem [checklist](docs/song-song-checklist.md). Sếp hay ai khác muốn tự xem web thì cần thêm login vào danh sách cho phép ([`ACCESS-01`](docs/decisions/access-01.md)).

## Không chặn — làm trong lúc chạy song song, xong trước ngày chuyển hẳn

- Người dùng tự đi hết luồng trên web thật: xuất Debit Note đối chiếu mẫu (`DEBIT-NOTE-02`), xóa một dòng điều chỉnh (`XOA-DC-THANG-01`).
- Khách còn mở của `SONG-SONG-03` (2): chủ nghiệp vụ xác định số phải thu trước F4.
- Chép bản xuất chat Zalo lên `hao` để trang Chat Zalo có dữ liệu (`NHAC-NO-01`, sửa đổi ZALO-CHAT-01).
- Bỏ đường export cũ khi Sheet xóa ba tab (sau khi đồng bộ chuyến đã đọc `CONT_NGUON` ổn định).
- Tạm dừng thêm tính năng mới cho tới khi song song đã chạy. Ngoại lệ do người dùng chốt 1/11/2026: group Zalo trên web ([`ZALO-GROUP-01`](docs/decisions/zalo-group-01.md)); 3/11/2026: chuyến theo nguồn booking ([`NGUON-CHUYEN-01`](docs/decisions/nguon-chuyen-01.md), bốn giai đoạn trong [spec](specs/v7-chuyen-theo-nguon.md)); 4/11/2026: máy tự đối soát ([`MAY-DOI-SOAT-01`](docs/decisions/may-doi-soat-01.md)).
- Chủ sổ tự đi hết luồng đối soát trên `hao` ([spec](specs/v7-may-doi-soat.md)); khóa lại các tháng cũ đang để mở.

Cập nhật bảng khi trạng thái đổi; lộ trình ở `docs/roadmap.md`, điều kiện khởi động ở `docs/song-song-checklist.md`.
