# ACCESS-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web V7 chỉ phục vụ **login Tailscale có trong danh sách**. Login đã xác minh (qua header của Tailscale Serve hoặc
`whois`) nhưng ngoài danh sách nhận 403 `LOGIN_NOT_ALLOWED` ở mọi đường: đọc, ghi, asset, presence. Danh sách là
cấu hình vận hành trên máy chạy — biến `WEBDEBIT_ALLOWED_LOGINS` (phân cách bằng dấu phẩy hoặc khoảng trắng) trong
drop-in của unit API, hoặc cờ `--allowed-login` lặp — và **nằm ngoài Git** vì chứa login. Ở chế độ Serve
(`--behind-tailscale-serve`) không có danh sách thì API **từ chối khởi động** (fail-closed); chỉ chế độ dev actor
(`--insecure-dev-actor`, loopback thử nghiệm) mới bỏ qua. Login bị từ chối được ghi vào journal của unit
(dòng `ACCESS-01: từ chối login ngoài danh sách: <login>`), còn phản hồi cho trình duyệt chỉ có mã lỗi và câu
"Tài khoản này chưa được cấp quyền dùng sổ".

## Ngày / nguồn

31/10/2026, chat audit DevOps/hạ tầng: người dùng chọn "P0: khóa truy cập". Bối cảnh: `hao` được chia sẻ (Tailscale
node sharing) cho thiết bị của người dùng ngoài để dùng Vaultwarden; ufw không có tác dụng với lưu lượng tailnet; API
nhận mọi danh tính tailnet làm actor, nên trước đó Tailscale ACL là lớp bảo vệ duy nhất của sổ tiền.

## Hiệu lực và giới hạn

ĐÃ CODE: `web/v7_identity.py` (`parse_allowed_logins`, `resolve_actor(..., allowed_logins)`), `web/v7_ledger_api.py`
(`--allowed-login`, biến môi trường, 403 kèm thông báo, ghi journal), test `tests/test_v7_identity.py` và
`tests/test_v7_ledger_api.py`. Triển khai tự động khi merge qua `Deploy hao`; drop-in trên `hao` cài trước
([nhật ký](../deploys/2026-10-31-khoa-truy-cap.md)), nên lượt deploy đầu tiên sau merge là lúc danh sách có hiệu lực.

Danh sách ban đầu: **một login chủ sổ**, là login người duy nhất đã ghi `sokhach.event` từ 22 đến 30/10/2026
(204 sự kiện; ba actor còn lại là hệ thống: loader, backfill, migration). Thêm người: sửa drop-in, `daemon-reload`,
restart unit; xem journal để biết login nào đang bị từ chối. Quy trình trong [runbook mục 5](../v7-deploy-runbook.md#5-service-api-và-danh-tính).

CÒN MỞ: (1) Tailscale ACL cho người dùng được chia sẻ vẫn phải thu hẹp về cổng Vaultwarden (lớp mạng; danh sách
này là lớp ứng dụng); (2) ở chế độ Serve, API tin header danh tính từ mọi tiến trình loopback trên `hao`, danh sách
chỉ giới hạn *ai* chứ chưa chặn giả danh từ tiến trình cục bộ; (3) chưa có cách tự phục vụ để thêm người, phải sửa
file trên `hao`.
