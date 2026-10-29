# Hợp đồng đọc Sheet giai đoạn 1 (29/10/2026)

**ĐÃ CHẠY trên `hao` và CHAU_HAO ngày 29/10/2026.** Người dùng cho làm cả ba mục A, B, C trong chat; Claude chạy theo [runbook](../v7-deploy-runbook.md#hợp-đồng-đọc-sheet-giai-đoạn-1--runner-đồng-bộ-theo-release-đổi-tên-tab-ghép-khách-đã-chạy-trên-hao-29102026). Không migration, không đổi DB, không ghi tiền.

| Mục | Nội dung |
| --- | --- |
| Spec | [`v7-sheet-contract`](../../specs/v7-sheet-contract.md) |
| PR | FinanceBullkk/webdebit#167 (đọc `WEB_GHEP_KHACH`, dự phòng tên cũ; release `a7c4bd9`, Deploy hao xanh), PR bỏ tên cũ đi kèm nhật ký này |
| Ghi Sheet | Đổi tên một tab, thêm ba vùng bảo vệ chỉ cảnh báo. Không đổi ô, công thức hay dữ liệu |

## Kết quả

- **A. Runner đồng bộ chuyến chạy từ release.** Bản unit cũ lưu ở `sheet-contract-20261029-124320` trên `hao`. Đã đổi `WorkingDirectory`/`ExecStart` sang `auto-releases/current/cong-no-web-handoff/tools/`; lượt đầu `success`, 5394 dòng như lượt trước. Chuyến có phân loại sầu riêng (`durian_type`): **0 → 1171**. Đây là phần #123 đã merge từ trước nhưng tới giờ mới chạy, vì bản cài tay ở `/opt` dừng ở 24/10.
- **B. Đổi tên tab** `REVIEW_KHACH_2026-10-24` → `WEB_GHEP_KHACH`, giữ `sheetId`. Trước khi đổi, runner có một lần đọc tên cũ, đúng thiết kế. Sau khi đổi, ba runner đều `success`, 0 lần đọc tên cũ, bảng ghép vẫn đủ 87 tên. Bảng PS vẫn 108 dòng.
- **C. Vùng cảnh báo** (`warningOnly`): dòng 1 `WEBDEBIT_EXPORT`, dòng 1–2 `CONT_MASTER`, dòng 1 `WEB_GHEP_KHACH`. Đọc lại qua API thấy đủ ba vùng. `BOOKING_DATA` đã khóa cứng cả tab từ trước nên không thêm.

## Rollback

- A: chép unit đã lưu về `/etc/systemd/system/webdebit-sheet-sync.service`, `daemon-reload`.
- B: đổi tên tab lại **và** trả code về tên cũ cùng lúc (code đã bỏ đường dự phòng).
- C: xóa ba vùng bảo vệ theo ID (`1466277094`, `30825114`, `436551160`).

## CÒN MỞ

- Xóa `/opt/webdebit-sheet-sync` sau một tuần chạy ổn (từ 05/11/2026).
- Giai đoạn 2–3 của spec chưa làm.
