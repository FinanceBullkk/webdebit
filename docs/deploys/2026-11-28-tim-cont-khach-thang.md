# Tìm số cont và khách theo tháng lên hao (28/11/2026)

**ĐÃ CHẠY trên `hao` lúc 20:04 UTC ngày 27/11/2026 (03:04 giờ VN ngày 28/11/2026)**, ngay sau khi merge. Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [runbook](../v7-deploy-runbook.md) mục "Tìm số cont và khách theo tháng". Quyết định [`TIM-CONT-01`](../decisions/tim-cont-01.md), [`KHACH-THANG-01`](../decisions/khach-thang-01.md); spec [`v7-tim-cont-khach-thang`](../../specs/v7-tim-cont-khach-thang.md).

| Mục | Kết quả |
| --- | --- |
| PR / release | ThienThanhLogs/webdebit#688, merge `e4ba2592` qua merge queue; release tay `e4ba2592` (trước đó `33203bc`) |
| CI | 22 check của head `09f9eb7` xanh (1 bỏ qua), gồm `postgres-v7-backend` (ca `TIM-CONT.01`) |
| Migration | `2026-11-28-v7-tim-cont-khach-thang.sql`, SHA-256 `9c42fba0a222de8b…`, lấy từ commit merge |
| Checker / bảng băm | `v7_post_deploy_check.sql` `d51590d6b547…`, `v7_catalog_manifest.json` `3f4e65d02d98…` (cùng commit merge) |
| Ghi tiền | Không. Chỉ thêm hai hàm đọc; dữ liệu trước = sau |

## Thử trên bản sao (trước merge)

- Dump `webdebit_v7` (1079 mục), khôi phục vào DB thử, thu `CONNECT` của PUBLIC, `ANALYZE`; migration hai lượt.
- `find_container` khoảng 150 ms một lượt; khớp chuyến web và dòng chuyến sổ gốc.
- `get_month_customers(NULL)` lệch 0 sổ so với `get_dashboard_debt.this_month`; tháng 10/2026 lệch 0 sổ so với cột tháng 10 của `get_receivables_matrix(2026)`.
- md5 `pg_get_functiondef` hai hàm mới lấy từ bản sao (PostgreSQL 18.6) cho manifest; md5 `get_trip_month` trên bản sao trùng manifest trong repo. Đã xóa DB thử.

## DB thật (cửa sổ 20:04:13–20:04:17 UTC)

- Trước cửa sổ: 0 phiên đang chạy khác vào `webdebit_v7`. Dừng timer đối soát và API, dump trong cửa sổ (1079 mục, SHA-256 `c5fe545e4d361082…`), áp với `ON_ERROR_STOP`: 278 ms. API dừng khoảng 3,5 giây.
- Dấu vân (số sổ, nợ từng khách từng tháng, tổng từng khách, event, version mọi sổ, chuyến, phiếu thu, dòng phân bổ, mốc, khóa lệnh) trùng trước/sau.
- Checker 10/10 có `catalog_manifest`. Lượt đầu báo "manifest is not JSON" vì file manifest nằm trong thư mục 700 mà `postgres` không đọc được; chạy lại với bản chép ở `/tmp` (như các đợt trước) thì đạt. Không phải lỗi DB.
- Dưới `v7_app`: khách theo tháng hiện tại lệch 0 sổ so với thẻ Thu tháng; 44 sổ có số tháng 11/2026; tìm "1234" ra 4 chuyến.

## Release và kiểm sau

- Release tay `e4ba2592` bằng gói `scripts/deploy/release-paths.txt` của commit merge qua `webdebit-release.sh deploy` dưới `webdebit-deploy`: `current` → `e4ba2592`, `/healthz` 200. Script cảnh báo không dọn được vài release cũ có file của user khác (có từ trước).
- `Deploy hao` lượt push của `e4ba2592` dừng ở cổng SQL là chủ ý.
- Mở trên `hao` qua tailnet (chỉ xem, trình duyệt trong app): `/api/v7/month-customers` 200 (tháng 11/2026: 44 sổ; tháng 10/2026: 41 sổ), `/api/v7/containers/find?q=12` 422 `INVALID_QUERY`. Tổng quan có khối "Khách theo tháng" (Tháng 11/2026, 10 dòng, nút "Hiện cả 44 khách"), không cuộn ngang. Ô Tìm khách gõ "1234": khối "Số cont" 4 dòng; bấm dòng đầu mở Sổ khách đúng tháng, 1 dòng được tô, thanh "Đến dòng tiếp".

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261128-tim-cont/` trên `hao` (thư mục 700): `v7-truoc-thu.dump`, `v7-truoc-ap.dump` kèm sha256, dấu vân trước/sau, log migration, checker, kết quả so, các kịch bản `thu.sh`, `def.sh`, `ap.sh`.

## Rollback

- **DB:** `DROP FUNCTION sokhach.find_container(text); DROP FUNCTION sokhach.get_month_customers(date);` dưới `sokhach_owner`. Hoặc khôi phục `v7-truoc-ap.dump`.
- **Code:** `webdebit-release.sh deploy 33203bc24d6810e3c30c43462c61764a8c55d896` (release trước). Release cũ chạy được với DB mới.

## Còn mở

- Người dùng tự đi hết hai luồng (tìm cont, khách theo tháng) trên `hao`.
