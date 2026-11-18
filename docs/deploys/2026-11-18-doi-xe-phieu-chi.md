# Đội xe: phiếu chi mới lên `hao` (18/11/2026)

**ĐÃ CHẠY trên `hao` lúc 17:07 giờ VN**, trước khi merge. Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), [`CHI-PHI-XE-01`](../decisions/chi-phi-xe-01.md) (mục Phiếu chi xe mới trong [spec](../../specs/chi-phi-xe-01.md#phiếu-chi-xe-mới-từ-112026)) và [runbook](../v7-deploy-runbook.md).

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Người dùng gửi mẫu phiếu chi mới rồi chọn "Làm phần chắc chắn" (18/11/2026); triển khai tay theo `DEPLOY-CLAUDE-01` |
| PR / release | #486, merge `68d220b`; release tay `2216e11` (main lúc đó, thêm #487 chỉ tài liệu) |
| CI | 18/18 check của #486 xanh, gồm `postgres-doixe` và `postgres-v7-backend` (`--migration-test`) |
| Migration | `2026-11-18-v7-doi-xe-phieu-chi.sql`, SHA-256 `f59c493bfb560365f2c8f567b6bce6417ff1dfa67cda93b8323a066ffa0e2ef6` (trùng bản trên `main`) |
| Ghi tiền | Không. Thêm loại phí `hasom`, ba cột số lượng NULL của `doixe.chang`, viết lại `_chang_ds`, `luu_chang`, `sua_chang`, thêm hàm phụ `_sl` (không cấp ai). Không đổi `sokhach` |

## Vì sao áp trước khi merge

Màn mới luôn gửi `neo_ngay`, `may_gio`, `km` trong lệnh lưu chặng. `luu_chang` cũ từ chối khóa lạ, nên nếu code lên trước DB thì lưu chặng sẽ hỏng tới lúc áp. Migration tương thích ngược: code cũ không gửi ô mới. Từ lúc áp tới lúc release (17:07–17:23), màn cũ có hiện cột Hạ sớm/KH ở Đủ cột nhưng API cũ chưa nhận mã này.

## Thử trên bản sao (17:03)

- Backup toàn phần `webdebit_v7` (806 mục), khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC.
- Migration hai lượt, 113 ms mỗi lượt; lượt hai chạy lại được.
- Dấu vân trước/sau trùng: số sổ, md5 nợ từng sổ từng tháng, số dòng Lịch sử `sokhach`; chặng, dòng phí, số dư từng người, Lịch sử `doixe`.
- 16 loại phí, 3 cột mới; `v7_app` gọi đúng 11 hàm `doixe`, PUBLIC không gọi được hàm nào.
- Gọi thử dưới `v7_app` trong giao dịch quay lui: sửa km một chặng (ghi đè), lưu một chặng giả có Hạ sớm/KH, ngày neo, giờ máy, km; đọc lại đúng. Sau quay lui không còn chặng giả. Đã xóa DB thử.

## DB thật (17:07)

- Không kết nối nào khác đang chạy vào `webdebit_v7`. Máy đối soát giờ (:05) đang chạy, nhưng nó chỉ ghi `sokhach`; migration chỉ khóa bảng `doixe`.
- Backup lần nữa ngay trước khi áp (806 mục).
- Áp với `ON_ERROR_STOP`: 238 ms. Không cần cửa sổ dừng ghi.
- Dấu vân trùng trước/sau, như bản thử. `v7_post_deploy_check.sql` 9/9 OK. `get_tong` dưới `v7_app` trả 16 loại phí.

## Release

- `Deploy hao` dừng ở gate như thiết kế: diff có `tools/migrations/` (run 44283211697 cho `68d220b`, 44284650561 cho `2216e11`). Gate chặn theo diff, không biết DB đã áp; một phiên điều phối nhắc khi thấy hai run đỏ.
- Release tay `2216e11` lúc 17:23 bằng đúng gói (`git archive`) và script của `Deploy hao`: `/healthz` 200, unit active, `.release-sha` = `2216e11`. Script cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước).
- `doi-xe-model.js` do `hao` phục vụ là bản mới; `GET /api/v7/doixe` qua Tailscale trả 16 loại phí, mã cuối `hasom`.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261118-phieu-chi/` trên `hao` (thư mục 700): `v7-truoc-thu.dump`, `v7-truoc-ap.dump`, dấu vân trước/sau.

## Rollback

Code: revert #486 (màn và API cũ không gửi ô mới). DB không cần gỡ vì cột mới để NULL. Muốn gỡ hẳn: chạy lại phần định nghĩa `_chang_ds`, `luu_chang`, `sua_chang` của `2026-11-18-v7-doi-xe.sql`, rồi `ALTER TABLE doixe.chang DROP COLUMN neo_ngay, DROP COLUMN may_gio, DROP COLUMN km; DROP FUNCTION doixe._sl(jsonb, integer);`. Xóa `hasom` chỉ được khi chưa dòng phí nào dùng mã này.

## Còn mở

- 218 chặng bản thử T10–T11 vẫn để giờ máy phát trong ghi chú. Chuyển sang cột Giờ máy là nạp dữ liệu, cần người dùng đồng ý riêng.
- Câu 6, 17, 18, 19 trong spec: tiền nổ máy, dòng Hoá đơn, Sheet tab tài xế có đổi cột, cont cắt + cont kéo.
