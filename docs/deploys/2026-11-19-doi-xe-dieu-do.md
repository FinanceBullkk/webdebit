# Đội xe: schema và lệnh ghi phân công lên `hao` (19/11/2026)

**ĐÃ CHẠY trên `hao` lúc 10:13 giờ VN**, sau khi merge. Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), [`DOI-XE-DIEU-DO-01`](../decisions/doi-xe-dieu-do-01.md) (bước 3 phần 1 của [spec](../../specs/doi-xe-dieu-do-01.md); gói B1 của [`DOI-XE-CAU-TRUC-01`](../decisions/doi-xe-cau-truc-01.md)) và [runbook](../v7-deploy-runbook.md).

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Người dùng chốt luồng phân công 19/11/2026; triển khai tay theo `DEPLOY-CLAUDE-01`. Phiên điều phối Đội xe xếp lượt merge |
| PR / release | #500, merge `3555e3e`; release tay `3555e3e` |
| CI | 18/18 check của #500 xanh trên head `6f060dd`, gồm `postgres-doixe` (thêm `test_pg_doixe_dieu_do.py`) và `postgres-v7-backend` (`--migration-test`) |
| Migration | `2026-11-19-v7-doi-xe-dieu-do.sql`, SHA-256 `c0a71ccd77cb3f70e37b1d9c02991c4839504f996232400fbe96a1cc940a7e52` (trùng bản trên `main`) |
| Ghi tiền | Không. Thêm hai cột NULL của `doixe.chang` (`ngay_dong`, `nguon`), bảng `doixe.ma_nha_xe` (rỗng), hàm nối việc ↔ chặng, `get_dieu_do`, bốn lệnh phân công, `nap_nha_xe` (không cấp cho app); `xoa_chang` chuyển thân sang hàm chung, hành vi giữ nguyên. Không đổi `sokhach` |

## Thử trên bản sao (09:41)

- Backup toàn phần `webdebit_v7` (972 mục), khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC.
- Migration hai lượt (148 ms, 124 ms); lượt hai chạy lại được.
- Dấu vân trước/sau trùng (8 dòng): số sổ, md5 nợ từng sổ từng tháng, số dòng Lịch sử `sokhach`; chặng, dòng phí, số dư từng người, Lịch sử `doixe`.
- 219/219 chặng có sẵn giữ `nguon` NULL ("có trước điều độ"); `ma_nha_xe` rỗng.
- `v7_app` gọi 29 hàm `doixe`, không gọi được `nap_nha_xe`; PUBLIC không gọi được hàm nào; app không có quyền trên bảng nào. `v7_post_deploy_check.sql` 9/9 OK.
- Smoke dưới `v7_app` trong giao dịch quay lui, container giả: `get_dieu_do`, `phan_xe` tạo một chặng `nguon = dieu_do`, gọi lại cùng mã yêu cầu trả cùng chặng, `get_dieu_do` nối đúng chặng hàng, `bo_phan_cong` ẩn chặng, hai dòng Lịch sử. Sau quay lui không còn chặng hay Lịch sử giả. Đã xóa DB thử.

## DB thật (10:13)

- Không kết nối nào khác vào `webdebit_v7`; `doixe` không có ghi nào trong 30 phút trước. Máy đối soát giờ đang chạy lúc áp, nhưng chỉ ghi `sokhach`; migration chỉ khóa bảng `doixe`.
- Backup lần nữa ngay trước khi áp (972 mục).
- Áp với `ON_ERROR_STOP`: 131 ms. Không cần cửa sổ dừng ghi.
- Dấu vân trùng trước/sau. `v7_post_deploy_check.sql` 9/9 OK. Smoke như bản thử, quay lui sạch.

## Release

- Release tay `3555e3e` bằng đúng gói (`git archive`) và script của `Deploy hao`: `/healthz` 200, unit active, `.release-sha` = `3555e3e`. Script cảnh báo không dọn được vài release cũ có file của user khác (đã có từ trước).
- `Deploy hao` của `3555e3e` sẽ dừng ở gate vì diff có `tools/migrations/`; đó là chủ ý.
- App chưa gọi hàm mới nào (API thuộc gói B2), nên release cũ và mới đều chạy được với DB mới.

## Nạp mã nhà xe (10:18)

- Người dùng đồng ý trong chat 19/11/2026: chọn "Dùng hai mã đã đo" (Claude đo lại, báo mã rồi mới nạp), rồi trả lời "Nạp hai mã" qua phiên điều phối Đội xe. Hai mã đo bằng chặng hàng tháng 10 trên `hao`; một mã khác chứa chữ của mã đội xe nhưng không có chặng nào, nên không nạp (so nguyên mã). Mã thật không ghi vào repo.
- Không kết nối nào khác vào `webdebit_v7`. Backup toàn phần trước khi nạp (1008 mục, tăng so với 972 vì các đối tượng migration vừa thêm).
- `doixe.nap_nha_xe` một lần trong giao dịch, `ON_ERROR_STOP`: `ma_nha_xe` từ 0 lên 2 dòng, cả hai đang dùng; Lịch sử thêm đúng một sự kiện `nap` (danh sách trước 0, sau 2).
- Dấu vân tiền trùng trước/sau; chỉ dòng đếm Lịch sử `doixe` tăng 1. `get_dieu_do` dưới `v7_app` thấy 2 mã.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261119-dieu-do/` trên `hao` (thư mục 700): `v7-truoc-thu.dump`, `v7-truoc-ap.dump`, `v7-truoc-nap-nha-xe.dump`, dấu vân trước/sau, kịch bản `thu.sh`, `ap.sh`, `smoke.sql`, `nap-nha-xe.sh`.

## Rollback

Code: revert #500 (app không gọi hàm mới). DB không cần gỡ: hai cột mới NULL. Ngừng nhận một mã: `nap_nha_xe` với `dang_dung = false` (bảng không cho xóa dòng). Muốn gỡ hẳn khi chưa có chặng nào `nguon = 'dieu_do'`: chạy lại định nghĩa `xoa_chang` và ràng buộc `su_kien_viec` của `2026-11-18-v7-doi-xe.sql`/`-thu.sql`, `DROP FUNCTION` các hàm mới, `DROP TABLE doixe.ma_nha_xe`, `ALTER TABLE doixe.chang DROP COLUMN ngay_dong, DROP COLUMN nguon`.

## Còn mở

- Tab `CONT_NGUON` đã có bốn cột Nhà xe, Số seal, Nhiệt độ, Tên tàu (19/11/2026); bộ đọc của web chưa đọc (gói B2).
- `xoa_chang` của đợt 1 chưa kiểm bảng kê đã gửi; vá ở gói B3d theo `DOI-XE-MO-HINH-01`.
