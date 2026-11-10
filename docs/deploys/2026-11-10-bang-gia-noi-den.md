# Triển khai bảng giá có Nơi đến (10/11/2026)

**ĐÃ CHẠY trên `hao` lúc 11:56 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [`BANG-GIA-03`](../decisions/bang-gia-03.md).

| Mục | Kết quả |
| --- | --- |
| PR / release | #373, merge `8d94e49`; từ `70ac204` |
| CI | `ci-ok`, PostgreSQL và các job trên đúng SHA merge xanh |
| Migration | `2026-11-10-v7-bang-gia-noi-den.sql`, SHA-256 `0cc44960a3c5c9cf8560fd7812f95d4d68a7ad0d7e2440e701be92f738ff6e24` |
| Ghi tiền | Không; migration không sửa giá chuyến hoặc số dư |

## Gate và kết quả

- Trước ghi: backup toàn phần `webdebit_v7`, hash khớp, `pg_restore --list` đọc được 34 bảng. Restore vào DB thử riêng, migration chạy hai lượt với `ON_ERROR_STOP=1`; fingerprint số dư từng khách, tháng, event và số dòng không đổi. Catalog ổn định; checker 9/9.
- Trên DB thật: dừng `v7-reconcile-auto.timer` và `v7-ledger-api.service`, không còn kết nối DB khác; chụp backup lần nữa, kiểm hash và đọc lại. Migration một `COMMIT`; fingerprint trước/sau khớp, catalog khớp bản thử, checker 9/9. 142 dòng giá cũ giữ nơi đến trống và chưa áp dụng theo đích.
- Bật lại API và timer, đều `active`. Release `8d94e49`, file migration trong release khớp SHA-256 đã chạy, loopback `/healthz` trả 200. Trang sổ qua loopback trả 403 do cổng danh tính; không coi là lỗi trang hoặc bằng chứng thao tác có đăng nhập.
- `Deploy hao` tự động dừng đúng gate SQL; đổi release tay sau khi nâng DB. Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261110-bang-gia-noi-den/` trên `hao` (quyền 700) và log kiểm cục bộ tại `D:\webdebit\worktrees\_logs\price-destination-20261110`.

## Còn mở

Chưa lưu bảng giá thật sau nâng. Người dùng cần bổ sung Nơi đến vào dòng cũ rồi xem giá đề xuất và Lịch sử sau lần lưu đầu tiên. Chưa kiểm giao diện có đăng nhập trên `hao`; test trình duyệt và kiểm PostgreSQL chỉ xác nhận bản thử.
