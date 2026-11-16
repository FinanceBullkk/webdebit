# Triển khai "Đã xem, hết báo" theo dấu vân dòng Sheet (KIEM-TAB-01 đợt 4, K3) (16/11/2026)

**ĐÃ CHẠY trên `hao` ngày 16/11/2026 (migration 10:54:00–10:54:05 UTC, tức 17:54 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md); phiên điều phối báo CI xanh và nhắc tránh phút :05–:15. Đề xuất [KIEM-TAB-01, K3](../../specs/v7-kiem-tab-truoc-khi-ghi.md#k3-hết-báo-chung-theo-dấu-vân-dòng-sheet-gốc-của-5).

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#451 (merge `a0934ce`); mọi check xanh (15/15), gồm `postgres-v7-backend` với `--migration-test` |
| Migration | `2026-11-16-v7-nguon-het-bao.sql` (sha256 `a127e5b2ae5e…`, trùng blob trên `main`): chỉ `CREATE OR REPLACE sokhach.keep_sheet_task` nhận thêm `task_kind = 'source'`. Không đổi bảng, view, hàm khác, event cũ, quyền hay dữ liệu |
| Release app | `8fd0d4b` → `a0934ce`, đưa tay (job `Deploy hao` dừng đúng ở cổng SQL) lúc 10:54:30 UTC; `/healthz` 200, unit `active` |
| Ghi tiền | Không. Hàm mới chỉ ghi một event `sheet_conflict_resolved` (`task_source`) khi người bấm nút; chưa bấm lần nào trên dữ liệu thật |

## Trước

- Máy đối soát `v7-reconcile-auto.service` `inactive`, lượt tới 11:05 UTC; cửa sổ dừng ghi xong lúc 10:54:05.
- Journal `sudo` 30 phút trước chỉ có lệnh của phiên này và `systemctl restart` API của đợt #449; event cuối cùng 10:14 UTC (id 10.463), không có ghi xen vào.

## Bản sao thử (10:49 UTC, trước khi merge)

Dump (`pg_restore -l` đọc lại được, 34 bảng), restore vào DB tạm, migration hai lượt (87 ms, 84 ms; một `COMMIT` mỗi lượt). Đã xóa DB tạm.

- Catalog ổn định giữa hai lượt và khác bản trước (đúng: thay một hàm); dấu vân tay không đổi; checker 9/9.
- Kiểm `keep_sheet_task(..., 'source', NULL, NULL, <dấu vân>, {"scope":"price"})` trong giao dịch rồi `ROLLBACK`: đúng một event `task_source`, tổng nợ không đổi (57.922.175.077 đ), gửi lại cùng khóa nhận cùng kết quả, 9 ca sai (có đích, đích kèm, dấu vân sai hoặc NULL, scope lạ, thừa khóa, `{}`, mảng, loại lạ) đều `INVALID_SHEET_RESOLUTION`.
- Rollback bằng áp lại `2026-11-09-v7-ps-khong-thu.sql`: dấu vân tay không đổi. Catalog sau rollback **không trùng từng byte** với bản đang chạy vì hàm đang chạy có ký tự `\r` (CRLF) do lần triển khai 9/11 chép từ cây làm việc Windows; migration và git đều LF. Thân hàm trùng từng token (đã so). Không ảnh hưởng hành vi.

## Cửa sổ dừng ghi (10:54:00–10:54:04 UTC)

- Dừng timer `v7-reconcile-auto` và API, không còn kết nối. Dấu vân tay, dump kèm hash, đọc lại được (34 bảng).
- Áp migration với `ON_ERROR_STOP`: 101 ms, một `COMMIT`. Catalog sau áp trùng bản thử; hàm nhận `'source'`.
- **Đối soát tổng khách: dấu vân tay không đổi**; 242 sổ, tổng 57.922.175.077 đ, 10.455 event. Checker 9/9.
- Bật lại API và timer: `active`, loopback 403 (sống). API gián đoạn 4 giây.

Thứ tự: migration trước release. Release cũ chạy được với hàm mới (chỉ thêm một giá trị được nhận).

## Kiểm sau (qua Tailscale Serve, chỉ đọc)

- `so-khach-v7-ps-ui.js` và `viec-can-lam-table.js` mới được phục vụ; journal API không có lỗi. Hộp việc tính lại sau khởi động xong lúc 10:55:50 UTC.
- `GET /api/v7/ledger` của các sổ có việc cho thấy `closable` đúng thiết kế trên dữ liệu thật: giá `AMBIGUOUS`/`MANUAL` (sổ 94, 104, 119, 120, 143), PS `AMBIGUOUS` (143), chuyến `NEW` ở tháng khóa (144, 157, 199, 228, 235), `AMBIGUOUS_MATCH` (143). **Không** có ở `TOTAL_DIFF` và `WEB_NO_FEE` (đã có "Không thu, hết báo" theo chuyến) và không ở chuyến `NEW` tháng đang mở (105).
- `GET /api/v7/sheet/doi-chieu?customer=239` và `=143` có `closed_sources` (rỗng). Không có event `task_source` nào trong DB; chưa bấm nút nào.

**Bằng chứng:** thư mục `backup-20261116-nguon-het-bao` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700): dump trước và lúc dừng kèm sha256, SQL kèm sha256, hai script, dấu vân tay, catalog, kết quả kiểm `source`, log áp, checker, so hàm trước và sau rollback.

## Rollback

- DB: áp lại `2026-11-09-v7-ps-khong-thu.sql` (đã thử trên bản sao). Các dòng đã "hết báo" khi đó hiện lại ở bản app mới; event `task_source` vẫn trong Lịch sử, không đổi tiền.
- App: `webdebit-release.sh deploy 8fd0d4b8a2a24b08f9f8874b4667ca33b5305c12`.

## CÒN MỞ

- Người dùng tự đi hết luồng trên `hao`: mở một sổ có dòng đóng được (ví dụ sổ 94, 119, 120, 143), bấm "Đã xem, hết báo", xác nhận, thấy dòng biến mất và nợ không đổi; và ở bảng đối chiếu bấm ở "Chỗ máy tìm ra".
- Chưa đo tải khi nhiều dòng đóng cùng lúc: mỗi lần bấm đọc lại hàng chờ của một sổ một lần.
