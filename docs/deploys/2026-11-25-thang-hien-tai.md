# Tháng hiện tại luôn có dòng trong GET sổ (SK-C1) lên hao (25/11/2026)

**ĐÃ CHẠY trên `hao` lúc 03:24 UTC (10:24 giờ VN) ngày 25/11/2026**, ngay sau khi merge. Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [runbook](../v7-deploy-runbook.md) mục "Tháng hiện tại luôn có dòng trong GET sổ (SK-C1)". Spec [`v7-thang-hien-tai`](../../specs/v7-thang-hien-tai.md); mục SK-C1, SK-N8, SK-N11 của [audit Sổ khách](../ux-audit-so-khach-2026-11-25.md).

| Mục | Kết quả |
| --- | --- |
| PR / release | ThienThanhLogs/webdebit#655, merge `24d14fc0` qua merge queue; release tay `24d14fc0` (trước đó `1f29058a`) |
| CI | 22 check của head `5e0fde68` xanh (1 bỏ qua), gồm `postgres-v7-backend` (ca `SK-C1.01`), `postgres-v7-fifo`, `postgres-v7-bat-bien`, `postgres-v7-luoi-an-toan`; lượt `merge_group` xanh |
| Migration | `2026-11-25-v7-thang-hien-tai.sql`, SHA-256 `2adccfe0bce0f1c4…`, trùng bản trên `main` và bản đã thử |
| Checker / bảng băm | `v7_post_deploy_check.sql` `e54394194f64…`, `v7_catalog_manifest.json` `0d02f2c6a9f0…` (cùng commit merge) |
| Ghi tiền | Không. Chỉ thay thân hàm đọc `get_ledger`; dữ liệu trước = sau |

## Thay đổi hành vi

- `get_ledger` của sổ có mốc luôn có dòng `months` cho tháng hiện tại (giờ VN). Tháng chưa có gì: phát sinh, đã thu, còn nợ của kỳ đều 0; Nợ đầu tháng = Còn nợ cuối tháng = cuối tháng trước. `total_outstanding_vnd`, phân bổ, số mọi tháng khác không đổi.
- Trang Sổ khách: thẻ tháng hiện tại có số thay "–"; chip tháng ghi năm theo chip đứng trước, khoảng trống có "… N tháng"; ổ khóa và nút điều chỉnh tắt nói rõ trạng thái, lý do.

## Thử trên bản sao (trước merge, 02:4x UTC)

- Dump `webdebit_v7` (list 1079 mục), khôi phục vào DB thử, thu `CONNECT` của PUBLIC, `ANALYZE`.
- Migration hai lượt: 392 ms, 153 ms.
- Dấu vân (số sổ, nợ từng khách từng tháng, tổng từng khách, số event, version mọi sổ, chuyến, phiếu thu, dòng phân bổ, mốc, khóa lệnh) trùng trước/sau.
- So `get_ledger` mọi sổ trước/sau: 250 sổ, 196 sổ có thêm đúng một dòng tháng hiện tại (toàn 0, Nợ đầu tháng = Còn nợ cuối tháng = cuối của dòng liền trước, dòng cuối bằng tổng), 54 sổ không đổi (đã có dòng tháng này, hoặc chưa có mốc), 0 lỗi; mọi phần ngoài `months` trùng.
- Checker 10/10 (có `catalog_manifest`). Sổ 10 trên bản sao: Nợ đầu tháng = Còn nợ cuối tháng = tổng còn nợ. Đã xóa DB thử.

## DB thật (cửa sổ 03:24:38–03:25:13 UTC)

- Trước cửa sổ: 0 phiên đang chạy khác vào `webdebit_v7`, không lượt đối soát nào đang chạy; giờ chọn xa watchdog (:32), backup (:00) và đối soát (:05).
- Dừng timer đối soát và API, dump trong cửa sổ (1079 mục, SHA-256 `243f814d8f69ccc7…`), áp với `ON_ERROR_STOP`: 124 ms.
- Dấu vân trùng trước/sau (10 dòng như trên). So `get_ledger` 250 sổ: 196 thêm dòng tháng hiện tại, 54 không đổi, 0 lỗi.
- Checker 10/10. Bật lại API và timer; API dừng khoảng 35 giây (gồm dump và hai lượt chụp sổ).

## Release và kiểm sau

- Release tay `24d14fc0` lúc 03:25 UTC bằng đúng gói `scripts/deploy/release-paths.txt` của commit merge qua `webdebit-release.sh deploy` dưới `webdebit-deploy`: `.release-sha` = `24d14fc0`, `/healthz` 200. Script cảnh báo không dọn được vài release cũ có file của user khác (có từ trước).
- `Deploy hao`: lượt push của `24d14fc0` dừng ở cổng SQL là chủ ý; lượt `workflow_run` báo xanh (bỏ qua vì release đã mới hơn).
- Lưới an toàn `--dry-run` từ release mới dưới `v7app`: `ok`, 0 mục, `catalog` khớp, 250 sổ (lượt này so phần 5/8 của `get_ledger`; phép so 250 sổ ở trên phủ mọi sổ).
- Mở sổ 10 trên `hao` (chỉ xem): thẻ tháng 11/2026 có Nợ đầu tháng khác 0, bằng Còn nợ cuối tháng và bằng "Tổng còn nợ" ở đầu trang; không còn "–". Chip: "T6/2025 · T7 · … 2 tháng · T10 · … 12 tháng · Tháng 11/2026". Ổ khóa: `title` = `aria-label` = "Đang mở · bấm để khóa tháng 11/2026".

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261125-thang-hien-tai/` trên `hao` (thư mục 700). Gồm `v7-truoc-thu.dump`, `v7-truoc-ap.dump` kèm sha256, dấu vân và ảnh `get_ledger` trước/sau của bản sao và DB thật, kết quả so, checker, các kịch bản `thu.sh`, `ap.sh`, `fp.sql`, `ledger.sql`, `so.py`.

## Rollback

- **DB:** chạy lại `2026-11-23-v7-so-gon.sql` dưới `sokhach_owner` (bản `get_ledger` đó đã mang `SET jit = off`); thẻ tháng hiện tại về "–", số khác không đổi. Hoặc khôi phục `v7-truoc-ap.dump`.
- **Code:** `webdebit-release.sh deploy 1f29058a712c4dae72407777ca069c179c6955b9`. Release cũ vẽ được dòng tháng mới (trang đã có chip giữ chỗ cho tháng hiện tại).

## Còn mở

- Không.
