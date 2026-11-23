# Đội xe DX-05: ứng, hoàn, hủy vào tháng khóa gắn cờ "sau khóa" lên hao (24/11/2026)

**ĐÃ CHẠY trên `hao` lúc 17:54 UTC ngày 23/11 (00:54 giờ VN ngày 24/11)**, sau khi merge. Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [runbook](../v7-deploy-runbook.md). Quyết định: [`DOI-XE-SAU-KHOA-01`](../decisions/doi-xe-sau-khoa-01.md).

| Mục | Kết quả |
| --- | --- |
| PR / release | FinanceBullkk/webdebit#627, merge `1dd33657`; release tay `1dd33657` (trước đó `efd26d56`) |
| CI | Check của #627 xanh trước merge (phiên điều phối merge), gồm harness PostgreSQL mới `test_pg_doixe_sau_khoa.py` |
| Migration | `2026-11-24-v7-doi-xe-sau-khoa.sql`, SHA-256 bắt đầu `ef061d61c31f` (trùng bản trên `main` và bản đã thử) |
| Ghi tiền | Không đổi dữ liệu tiền. Thêm bốn cột cờ (`sau_khoa`, `huy_sau_khoa` ở `doixe.ung` và `doixe.dot_hoan`, mặc định false), `CREATE OR REPLACE` `ghi_ung`, `huy_ung`, `ghi_hoan`, `huy_hoan`, `get_so`. Không đổi quyền, `sokhach` |

## Thử trên bản sao

- Backup toàn phần `webdebit_v7` (1048 mục), khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC.
- Migration hai lượt (112 ms, 128 ms); lượt hai chạy lại được.
- Dấu vân tiền trùng trước/sau (14 dòng: sổ `sokhach`, chặng, dòng phí, số dư, ứng, đợt hoàn, bảng kê, giá, tuyến, tên gốc, Lịch sử, lệnh).
- So định nghĩa hàm `doixe` ngoài danh sách thay, quyền của mọi hàm, cột và quyền của mọi bảng `doixe`: chỉ khác đúng bốn cột mới. Không khoản nào mang cờ true. App gọi 30 hàm như trước, PUBLIC 0.
- `v7_post_deploy_check.sql` 10/10 OK (có `catalog_manifest`).
- Ghi thử dưới `v7_app` trong giao dịch rồi ROLLBACK: ứng ngày tháng trước (đã khóa) trả `sau_khoa=true`, hủy nó trả `true`, ứng hôm nay trả `false`. Đã xóa DB thử.

## DB thật

- Máy đối soát không chạy, không kết nối nào khác đang chạy vào `webdebit_v7`. Không cần cửa sổ dừng ghi.
- Backup lần nữa ngay trước khi áp (1048 mục).
- Áp với `ON_ERROR_STOP`: 406 ms.
- Dấu vân tiền trùng. Hàm, cột, quyền chỉ khác đúng bốn cột mới (307 dòng so). Không khoản nào mang cờ true. `v7_post_deploy_check.sql` 10/10 OK.
- Đọc `get_so` tháng trước cho cả 16 người dưới `v7_app`: 3,04 s trước và 3,04 s sau. Trên bản sao vừa khôi phục, cùng phép đo mất 9–13 s vì bảng chưa có thống kê, không phải do migration.

## Release

- `Deploy hao` của commit merge không tự triển khai được vì diff có `tools/migrations/` (cổng SQL), đúng thiết kế.
- Release tay `1dd33657` bằng đúng gói và script của `Deploy hao` (`git archive` theo `scripts/deploy/release-paths.txt` → `webdebit-release.sh deploy`, dưới user `webdebit-deploy`). Unit `v7-ledger-api` `active`, `/healthz` 200, release có file mới (nhãn "sau khóa" trong `doi-xe-ui.js`, `doi-xe-model.js`). Journal API không có dòng lỗi.
- Mở Đội xe trên `hao`, chỉ đọc: trang tổng và sổ một tài xế vẽ đủ, không lỗi. API sổ người trả trường cờ. Tháng 10 và 11 trên `hao` chưa có lần ứng hay đợt hoàn nào, nên chưa có khoản nào hiện nhãn.
- Từ lúc merge tới lúc áp có vài phút. Trong lúc đó release cũ vẫn chạy với hàm cũ và không đọc trường mới, nên không lệnh nào gãy.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261124-doixe-sau-khoa/` trên `hao` (thư mục 700): `v7-truoc-thu.dump`, `v7-truoc-ap.dump`, dấu vân tiền và định nghĩa trước/sau, kịch bản `thu.sh`, `ap.sh`, `fp.sql`, `ham.sql`, `do.sql`, `ghi_thu.sql`.

**Ghi chú cho lần sau:** `v7_post_deploy_check.sql` (từ #613) cần `-v manifest=` hoặc `-v manifest_json=`. Lệnh chạy dưới `postgres` nên không đọc được file manifest nằm trong thư mục bằng chứng 700. Lần này truyền nội dung bằng `-v manifest_json="$(cat v7_catalog_manifest.json)"`.

## Rollback

Code: `webdebit-release.sh deploy efd26d567fa234d58b2e4d2b9ac4d1cb5948b80e`. Release cũ không đọc trường mới, hàm mới vẫn nhận lệnh cũ. Muốn gỡ hẳn: chạy lại `ghi_ung`, `ghi_hoan` từ `2026-11-23-v7-doi-xe-sua-audit.sql`, `huy_ung`, `huy_hoan`, `get_so` từ `2026-11-18-v7-doi-xe.sql`, rồi `ALTER TABLE doixe.ung DROP COLUMN sau_khoa, DROP COLUMN huy_sau_khoa;` (và như vậy với `doixe.dot_hoan`). Hoặc khôi phục `v7-truoc-ap.dump`.

## Còn mở

- Review nêu, không chặn: chưa có ràng buộc `huy_sau_khoa` ⇒ `huy_luc` khác NULL; test trình duyệt chưa có đường hủy đợt hoàn.
- Chưa người dùng nào đi luồng ghi ứng/hoàn vào tháng khóa trên màn thật.
