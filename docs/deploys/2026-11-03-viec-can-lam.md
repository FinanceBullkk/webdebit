# Triển khai tay: Việc cần làm xử lý tại dòng (3/11/2026)

**ĐÃ CHẠY trên `hao` ngày 3/11/2026 (14:19 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Người dùng chốt hai điểm quy tắc trong chat ngày 2/11/2026: chọn sổ chỉ áp dụng "Riêng chuyến đó"; hoàn tác lô "Đồng ý cách hiện tại".

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#270 (`6e325be`), thay FinanceBullkk/webdebit#267 do Codex làm dở |
| Căn cứ | [spec Việc cần làm](../../specs/v7-viec-can-lam-bang.md); [`VCL-GIU-01`](../decisions/vcl-giu-01.md) |
| Migration | Năm file `2026-11-02-v7-*.sql`, theo thứ tự: `giu-viec-sheet` (`keep_sheet_task`), `lay-gia-sheet` (`apply_sheet_price`), `gan-mat-hang` (`set_customer_commodity`), `chon-so-chuyen` (`assign_sheet_trip`), `hoan-tac-lo` (`undo_sheet_batch`). Chỉ THÊM năm hàm, cấp cho `sokhach_app`, thu hồi từ `PUBLIC` và `sokhach_reader`. Không đổi bảng, ràng buộc, loại event, dữ liệu hay hàm cũ. |
| Release app | `833a4ae` → `6e325be` |
| Ghi tiền | Đợt nâng không ghi. Ba hàm mới ghi tiền khi người dùng bấm (lấy giá Sheet, chọn sổ cho chuyến, hoàn tác lô), đều qua lệnh sẵn có. |

## Trước

- `hao` chạy `833a4ae`. DB `webdebit_v7`: 236 khách, tổng nợ trên web 67.131.162.261 đ, 8.269 event; lần ghi cuối 13:49.
- Không phiên nào nối vào DB, không lệnh sudo của phiên khác trong 30 phút; các phiên Claude khác offline hoặc idle (`ListAgents`).

## Bản sao thử

- Chạy hai lần: 2/11 tối và 3/11 ngay trước cửa sổ, trên dữ liệu mới.
- Dump, restore vào DB thử: dấu vân tay khớp DB thật.
- Năm migration hai lượt, mỗi lượt khoảng 0,47 giây, 5 `COMMIT`. Catalog `1c476c75…` ổn định giữa hai lượt và giữa hai ngày.
- Số dư từng khách, 880 dòng tháng, số event, số dòng mọi bảng không đổi. Checker 9/9 OK. `v7_app` gọi được cả năm hàm, `sokhach_reader` không.
- Đã xóa DB thử.
- Mã băm năm migration và checker trong commit merge trùng bản đã thử.

Bản sao thử lần đầu bắt được lỗi: `v7_post_deploy_check.sql` chưa có năm hàm trong danh sách hàm app được gọi, nên checker sẽ báo lỗi sau khi nâng. Đã sửa trong PR, cùng bốn danh sách harness khác (`KNOWN_FUNCTIONS`, `WRITE`, chuỗi migration BANG-GIA, luật ghi cache phụ phí CSM.03).

## Cửa sổ dừng ghi (14:19:35–14:19:39 giờ VN)

- Dừng `v7-ledger-api.service`, kiểm không còn kết nối, ghi dấu vân tay, dump kèm hash.
- Áp năm migration với `ON_ERROR_STOP`: 0,52 giây, 5 `COMMIT`.
- Catalog sau áp trùng bản thử. Dấu vân tay (236 khách, tổng nợ, tháng, event, số dòng) không đổi. Checker 9/9 OK.
- Bật lại API: `active`, loopback 403 (sống). API gián đoạn 4 giây.

## Đổi release

- `git archive 6e325be | webdebit-release.sh deploy 6e325be…` dưới user `webdebit-deploy`. API khởi động lại 14:19:52. `.release-sha` = `6e325be`. Không có file do root sở hữu trong thư mục release.
- Migration và checker trong release trùng hash bản đã chạy.

## Sau

- Checker chạy từ file trong release: 9/9 OK.
- 236 khách, tổng nợ 67.131.162.261 đ, 8.269 event và số dòng mọi bảng bằng trước đợt.
- Journal API không lỗi.

**Bằng chứng:** thư mục `backup-20261102-viec-can-lam` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700). Gồm dump trước và dump lúc dừng kèm sha256, bản sao các file SQL kèm sha256, script bản sao thử và cửa sổ dừng, dấu vân tay, catalog, log áp thật và log checker.

## Rollback

- App: `webdebit-release.sh deploy 833a4ae96631f82aa4b234d87c90f3cad560781c`. Release cũ không gọi năm hàm mới, chạy được với DB mới.
- DB: `DROP FUNCTION` năm hàm dưới `sokhach_owner` trong một transaction, rồi gỡ chúng khỏi checker. Hoặc restore `v7-stopped.dump` vào DB mới. Việc người dùng đã ghi qua các hàm này nằm trong Lịch sử; muốn đảo lại thì sửa tại ô như mọi sửa đổi khác.

## CÒN MỞ

- Chưa thử tay trên web các nút mới: Giữ giá web, Giữ chuyến, Lấy giá Sheet, ghi phiếu thiếu ngày, gán mặt hàng, chọn sổ cho chuyến, hoàn tác lô. Mới có test trình duyệt và harness.
- Giới hạn đã biết ghi trong spec: quyết định Giữ có hiệu lực lại khi dòng Sheet đổi A → B → A; lô ghi mất phản hồi rồi gửi lại có thể báo STALE_LEDGER thay vì trả kết quả cũ (không ghi trùng).
