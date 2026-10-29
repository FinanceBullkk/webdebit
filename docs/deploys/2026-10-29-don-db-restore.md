# Dọn DB restore/tổng duyệt cũ trên `hao` (29/10/2026)

**ĐÃ CHẠY trên `hao` ngày 29/10/2026, 20:21 giờ VN.** Người dùng duyệt xóa cả 14 DB trong bảng kiểm kê dưới đây (cùng ngày).
Không phải đợt nâng release/migration: không đụng `webdebit_v7`, `webdebit_ledger`, `webdebit_pilot_system`, không ghi tiền,
không DDL trên DB thật.

## Vì sao

- Các đợt 13/10–29/10/2026 để lại DB restore/tổng duyệt. Runbook [mục 2](../v7-deploy-runbook.md#2-backup-toàn-phần-trước-mọi-ghi-dbcấu-hình)
  và [B4](../v7-deploy-runbook.md#b4-phục-hồi-thử-ra-db-mới-c2) bắt drop DB thử ngay sau khi đếm khớp (kỳ vọng còn 0).
- Mỗi DB là một bản sao dữ liệu khách nằm ngoài vòng backup. Ba DB để quyền mặc định (PUBLIC được CONNECT):
  `webdebit_postboot_restore_test`, `webdebit_v7_m211_restore`, `webdebit_v7_shipper_final_restore_20261025`.
  `webdebit_v7_sheet_conflict_restore` cấp CONNECT cho `v7_app` và `v7_loader`.
- Rollback ở mọi đợt là restore dump vào DB mới, không dùng DB giữ lại. Dump của từng đợt vẫn nằm trong thư mục backup của
  đợt trên `hao`, cùng bản hằng ngày `/srv/v7-backup-daily`.

## Kiểm kê trước (chỉ đọc)

- 0 phiên mở ở cả 14 DB. Không unit systemd, cron, file trong `/etc/webdebit` hay code trong repo nào nhắc tên các DB.
- Đợt xác định theo thời điểm tạo DB (mtime `PG_VERSION`), đối chiếu với thời điểm dump và nhật ký của đợt.
- `t5_v7_dashboard_1792751027` không có trong danh sách thấy lúc cài backup hằng ngày; tìm ra khi kiểm kê, cùng loại
  (bản sao V7 lúc kiểm dashboard T5), người dùng duyệt chung.

| DB | Đợt (tạo lúc, giờ VN) | MB |
| --- | --- | ---: |
| `v7_prb_restore_20261029-0550` | PR-B phụ phí (29/10 12:48) | 29 |
| `v7_prb_rehearsal_20261029_0550` | PR-B phụ phí, tổng duyệt (29/10 12:52) | 29 |
| `v7_prb_final_20261029_0605` | PR-B phụ phí (29/10 12:59) | 30 |
| `v7_prbp2_rehearsal_20261029_0629` | PR-B P2 (29/10 13:29) | 30 |
| `webdebit_v7_phuphi_restore_20261028` | Phụ phí PR-A (28/10 15:50) | 29 |
| `webdebit_v7_phuphi_prerestore_20261028` | Phụ phí PR-A (28/10 15:54) | 28 |
| `webdebit_v7_price_restore_20261027` | Ghi giá từ Sheet (27/10 23:33) | 28 |
| `webdebit_v7_sheet_conflict_restore` | Xung đột Sheet (25/10 07:20) | 28 |
| `webdebit_v7_shipper_final_restore_20261025` | Shipper + backfill (25/10 05:20) | 32 |
| `webdebit_v7_shipper_restore_20261025` | Shipper (25/10 04:51) | 23 |
| `t5_v7_dashboard_1792751027` | Kiểm dashboard T5 (23/10 17:23) | 23 |
| `webdebit_v7_ui_restore` | Giao diện sửa/xóa tại ô (22/10 22:26) | 23 |
| `webdebit_v7_m211_restore` | M2-11 (22/10 10:31) | 23 |
| `webdebit_postboot_restore_test` | Thử restore sau khởi động máy, bản sao `webdebit_pilot_system` (13/10 19:24) | 27 |

Tổng 400.350.834 byte (~382 MB) lúc xóa. Ổ chứa cluster còn 70 GB nên chỗ trống không phải lý do chính.

## Xóa

- Từng DB: đối OID với bảng kiểm kê, kiểm 0 phiên, rồi `sudo -u postgres dropdb -h /var/run/postgresql <tên>` (không `--force`).
  14/14 xóa được trong 8 giây (13:21:03–13:21:11 UTC).
- Kiểm lại: `SELECT count(*) FROM pg_database WHERE datname IN (<14 tên>)` = 0. Cluster còn `postgres`, `template0`,
  `template1`, `webdebit_ledger`, `webdebit_pilot_system`, `webdebit_v7`. `v7-ledger-api.service` active.
- Bằng chứng: bảng trên và kết quả lệnh (chỉ tên DB, OID, kích thước), không có thư mục bằng chứng riêng trên `hao`.

## Rollback

Không hoàn tác bằng lệnh. Cần lại một bản sao thì restore dump của đợt đó vào DB mới theo runbook mục 2 (thu hồi CONNECT của
PUBLIC trước khi dùng). Riêng `webdebit_postboot_restore_test` là bản sao `webdebit_pilot_system` ngày 13/10; DB gốc vẫn chạy.

## CÒN MỞ

- Chưa có kiểm tự động báo DB thử bị bỏ lại trên cluster (ĐỀ XUẤT, chưa làm).
- Dump nguồn của DB Shipper đầu nằm trong `/var/tmp`, có thể bị hệ thống tự dọn; đợt Shipper vẫn còn dump đầy đủ ở `/var/backups`.
