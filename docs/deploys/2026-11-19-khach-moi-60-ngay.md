# Triển khai: mốc sổ mới 60 ngày (19/11/2026)

**ĐÃ CHẠY trên `hao` lúc 16:16 giờ VN.** Theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md), quyết định [`KHACH-MOI-01`](../decisions/khach-moi-01.md) và [runbook](../v7-deploy-runbook.md#mốc-sổ-mới-60-ngày-khach-moi-01--nâng-db-đã-chạy-trên-hao-19112026). Đợt trước của cùng quyết định: [cờ khách mới](2026-11-19-khach-moi.md).

| Mục | Kết quả |
| --- | --- |
| Người cho chạy | Người dùng chọn "Cả hai 2 tháng" 19/11/2026 sau khi xem số đo (9 → 7 sổ mới, 3 → 2 sổ cần để ý); triển khai tay theo `DEPLOY-CLAUDE-01`, lượt do phiên điều phối merge cấp |
| PR / release | #524, merge `b891b57`; release tay `b891b57` thay cho `4d7fcc4` (giữa hai SHA chỉ có #524) |
| CI | Mọi check của PR xanh, gồm `postgres-v7-backend` (`--migration-test`, `v7_schema_snapshot.py --check`) và `postgres-v7-luoi-an-toan` |
| Review | Review độc lập (subagent sonnet): không lỗi logic; bốn chỗ chữ còn ghi mốc 90 đã sửa trong PR |
| Migration | `2026-11-19-v7-khach-moi-60-ngay.sql`, SHA-256 `c971304946b130c312f033438a1f6ce280c42d4e2c456be25cdb979b17c95efd`, trùng bản trên `main` và bản đã thử |
| Ghi tiền | Không. Chỉ thay hàm đọc `get_dashboard_debt` (`d-90` → `d-60`, `rule.new_days` 60), vẫn `jit=off` |

## Thử trên bản sao (15:42–15:45)

- Dump `webdebit_v7`, khôi phục vào DB thử riêng, thu `CONNECT` của PUBLIC, `ANALYZE`. Áp migration hai lượt (107 ms, 104 ms), hoàn tác bằng `2026-11-19-v7-khach-moi.sql`, rồi nâng lại.
- JSON `get_dashboard_debt` bỏ các trường khách mới, `get_dashboard`, `get_safety_net` trùng từng byte trước/sau và sau khi nâng lại; hoàn tác thì trùng cả JSON đầy đủ; dấu vân dữ liệu trùng; catalog chỉ đổi thân `get_dashboard_debt`; checker 9/9. Đã xóa DB thử.
- Sổ mới đang nợ 9 → 7; "chưa trả lần nào" giữ 2; "chuyến chậm trả" 1 → 0. Thời gian hàm không đổi (250–263 ms).

## DB thật, 16:16

- Chờ lượt máy đối soát 16:05 chạy xong (16:13). Không có kết nối nào khác vào `webdebit_v7`.
- Backup toàn phần ngay trước khi áp; `pg_restore --list` đọc được (1027 dòng).
- Áp với `ON_ERROR_STOP`: 140 ms. Không cần cửa sổ dừng ghi.
- Trường cũ của `get_dashboard_debt`, `get_dashboard`, `get_safety_net` và dấu vân dữ liệu trùng từng byte trước/sau. Catalog chỉ đổi thân `get_dashboard_debt`; `proconfig` vẫn có `jit=off`. Checker 9/9.
- Sau khi nâng: 7 trong 63 sổ đang nợ là sổ mới; 2 sổ "chưa trả lần nào", 0 sổ "chuyến chậm trả". `get_dashboard_debt` dưới `v7_app`: 252–256 ms.

## Release

- Release tay `b891b57` lúc 16:16 bằng đúng gói (`git archive`) và `webdebit-release.sh` dưới `webdebit-deploy`: `/healthz` 200, unit active, `.release-sha` = `b891b57`. Script cảnh báo không dọn được vài release cũ (đã có từ trước).
- Lưới an toàn `--dry-run`: `"ok": true`, không mục nào (so với lượt 16:02).
- Trên trang Tổng quan: ô lọc ghi "Khách mới 7 · 2 cần để ý", chú thích "sổ có chuyến đầu trong 60 ngày"; bấm lọc ra đúng 7 sổ, 2 sổ cần để ý đứng đầu; không cuộn ngang.

## Rollback

Chạy lại `2026-11-19-v7-khach-moi.sql` dưới `postgres` với `ON_ERROR_STOP` (đã thử trên bản sao). Giao diện đọc `rule.new_days` nên tự về chữ 90 ngày, không cần đổi release.

Bằng chứng gốc ngoài Git: `/srv/v7/backup-20261119-khach-moi-60/` trên `hao` (quyền 700). Gồm dump trước khi thử và trước khi nâng kèm sha256, SQL và script đã chạy, dấu vân, băm, catalog, checker và số đo.
