# Tên miền riêng cho V7 qua Tailscale

## Kết quả và ranh giới

Người dùng mở `https://congno.hthlogistics.top:8445` trên thiết bị đã kết nối Tailscale. Thanh địa chỉ giữ tên miền này, HTTPS có chứng chỉ tin cậy, API ghi đúng login Tailscale và vẫn áp danh sách `ACCESS-01`. Thiết bị ngoài tailnet không vào được. Đường Serve hiện tại tiếp tục hoạt động.

Chỉ thêm listener HTTPS trên **IP Tailscale của chính node**, trong cùng tiến trình API; không mở cổng WAN/LAN, Funnel, Cloudflare Tunnel hoặc đổi DB/Sheet. DNS `congno` là bản ghi A **DNS only** tới IP Tailscale. Bản ghi `game`, `@`, `*` giữ nguyên.

## Đường kiểm

| Thao tác | Điểm vào | Kiểm |
| --- | --- | --- |
| Mở trang từ thiết bị tailnet | HTTPS listener `v7_ledger_api.py` cổng 8445 | Chứng chỉ đúng host, GET trả trang, login lấy bằng LocalAPI `whois` từ socket peer |
| Gửi lệnh | `Handler._request` → `handle` | `Host`/`Origin` HTTPS khớp, login trong allowlist, không tin `Tailscale-User-Login` tự khai từ peer tailnet |
| Từ ngoài tailnet | DNS A tới IP Tailscale | Không thiết lập được kết nối TCP; không có listener public |
| Khởi động sai cấu hình | `main` | Thiếu chứng chỉ/host, host sai cổng, IP khác `tailscale ip -4`, hoặc thiếu allowlist thì từ chối khởi động |

## Triển khai và quay lui

1. Lấy chứng chỉ Let's Encrypt bằng DNS-01 qua Cloudflare. Token chỉ có `Zone:DNS:Edit` cho zone này; lưu ở máy chủ, quyền root 0600, không đưa Git/log/chat. Cài `certbot` và `python3-certbot-dns-cloudflare` từ Ubuntu apt. Chứng chỉ phải tự gia hạn; deploy hook chép `fullchain.pem`/`privkey.pem` vào thư mục chỉ root và service group đọc, rồi restart `v7-ledger-api.service` khi cert đổi.
2. Thêm drop-in systemd ngoài Git với `V7_TAILNET_HTTPS_IP`, `V7_TAILNET_HTTPS_HOST`, `V7_TAILNET_TLS_CERT`, `V7_TAILNET_TLS_KEY`. Chỉ bật sau khi mã mới và chứng chỉ có mặt. Kiểm `systemctl is-active`, đường Serve cũ và HTTPS mới bằng `curl --resolve` từ tailnet trước khi đổi DNS.
3. Trên Cloudflare tạo bản ghi A `congno` ở chế độ **DNS only**; giữ các bản ghi khác. Kiểm DNS có hiệu lực, chứng chỉ, mở trang bằng trình duyệt tailnet; header danh tính giả không đổi actor đã tra từ Tailscale. Không tạo giao dịch tiền thử.
4. Quay lui: xóa riêng bản ghi A `congno`, bỏ drop-in HTTPS, restart service; giữ chứng chỉ/token đến khi xác nhận đường cũ ổn rồi thu hồi token. Không đổi cấu hình Serve cũ.

`npm run check` kiểm mã/fixture; nghiệm thu tên miền cần DNS, chứng chỉ, máy chủ và trình duyệt thật. Không coi CI là bằng chứng live.
