# Triển khai tay: khóa truy cập web V7 theo danh sách login (31/10/2026)

**ĐÃ CHẠY trên `hao` ngày 31/10/2026 (00:35 giờ VN)**, Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md)
sau khi người dùng chọn "P0: khóa truy cập" trong chat audit hạ tầng. Không migration, không đổi DB, không ghi tiền;
chỉ thêm một drop-in cho unit API và siết quyền ba file cấu hình của một dịch vụ khác trên cùng máy.

| Mục | Nội dung |
| --- | --- |
| Quyết định | [`ACCESS-01`](../decisions/access-01.md) |
| Mã | PR nhánh `feat/access-allowlist`: `web/v7_identity.py`, `web/v7_ledger_api.py`, test; triển khai tự động qua `Deploy hao` khi merge |
| Trên `hao` | Drop-in `/etc/systemd/system/v7-ledger-api.service.d/allowed-logins.conf` (root, 644, SHA-256 `59a18c37…51bd5`): `Environment=WEBDEBIT_ALLOWED_LOGINS=<một login chủ sổ>` |
| Thứ tự | Drop-in cài **trước** khi merge: bản đang chạy (`c39ac7b`) bỏ qua biến này; lượt `Deploy hao` của PR restart service với mã mới và biến đã có, nên không có khoảng trống nào API chạy chế độ Serve mà thiếu danh sách |

## Đã làm

1. `systemd-analyze verify v7-ledger-api.service` không báo lỗi ở unit; `systemctl daemon-reload`; `systemctl show -p Environment`
   đã thấy `WEBDEBIT_ALLOWED_LOGINS`. Service **không restart** ở bước này (`is-active` = active, release `c39ac7b`).
2. Ba file của runner GitHub tự host của dự án khác trong thư mục nhà của tài khoản quản trị (`.credentials`, `.runner`, `.env`)
   đổi từ 664 về 600; runner vẫn `active` (chạy bằng chính tài khoản đó). Phần này không thuộc webdebit, ghi để có vết.

## Kiểm sau khi `Deploy hao` xanh

Chạy trên `hao`, không ghi tiền (loopback ở chế độ Serve tin header, nên dùng được để thử chính danh sách):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: <serve_fqdn>:8443' -H 'Tailscale-User-Login: stranger@example.test' http://127.0.0.1:8780/api/v7/customers
```

Đạt: `403`, journal có dòng `ACCESS-01: từ chối login ngoài danh sách: stranger@example.test`; cùng lệnh với login trong
danh sách trả `200`; từ trình duyệt của chủ sổ qua Serve vẫn mở được sổ.

## Rollback

Xóa `allowed-logins.conf` **không** đủ: mã mới ở chế độ Serve sẽ từ chối khởi động khi thiếu danh sách (fail-closed, đúng thiết kế).
Quay lại hành vi cũ = trỏ `CURRENT_LINK` về release trước PR (`c39ac7b` hoặc mới hơn nhưng trước ACCESS-01) rồi
`systemctl restart v7-ledger-api.service`; drop-in để nguyên vô hại. Mở rộng danh sách thay vì rollback: sửa drop-in,
`daemon-reload`, restart.

## CÒN MỞ

- Danh sách chỉ có một login (chủ sổ). Ai khác (kể cả tài khoản phụ) mở web sẽ nhận 403 cho tới khi được thêm; journal cho biết login nào.
- Tailscale ACL cho người dùng được chia sẻ chưa thu hẹp (việc trong admin console, người dùng làm).
- Khóa SSH của máy cũ `MSI` trong `authorized_keys` chưa gỡ (chờ người dùng xác nhận máy đã nghỉ).
