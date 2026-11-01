# Triển khai tay: chặn tính trùng ở hàng chờ chuyến mới (1/11/2026)

**ĐÃ CHẠY trên `hao` ngày 1/11/2026 (14:24–14:27 giờ VN).** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md); người dùng bấm "Merge và triển khai", rồi "Tiếp tục triển khai" khi CI của PR xanh.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#240 (`2116bd4`); tài liệu nền FinanceBullkk/webdebit#239 |
| Căn cứ | [UX bước 02](../ux-luong-du-lieu.md) mục 3.3 và 8; áp luật [`DUP-01`](../decisions/dup-01.md) cho cả hàng chờ; mục tiêu M2 của [`UX-NEN-01`](../decisions/ux-nen-01.md) |
| Migration | `2026-11-01-v7-chan-trung-hang-cho.sql`: thêm `_legacy_undated_match` (nội bộ) và `list_legacy_trip_refs` (chỉ cấp cho app), thay thân `paste_trips`. Không đổi bảng, ràng buộc, loại event, dữ liệu hay quyền cũ. |
| Release app | `4b5a9f1` → `2116bd4`. Cây mã của `2116bd4` trùng cây đầu nhánh PR `3e20b3e` (`0bd53277…`), đã qua 15/15 check của PR. |
| Ghi tiền | Không ghi. Đổi luật `paste_trips`: chuyến cùng container với dòng sổ gốc còn hiệu lực, **không có ngày**, cùng tháng nợ, ở bất kỳ sổ nào, vào chờ kiểm (`BASELINE_UNDATED_MONTH`). |

## Trước

- `hao` chạy `4b5a9f1`.
- DB `webdebit_v7`: 236 khách, tổng nợ trên web 67.701.771.688 đ, 6.555 event; lần ghi cuối 30/10/2026.
- Không phiên nào nối vào DB. Phiên Claude khác đang chạy không đụng `hao` (kiểm `ListAgents`, `pg_stat_activity`).

Hàng chờ đo bằng hàm chiếu của API trên cả 236 sổ (chỉ đọc):
- 341 "chuyến mới", trong đó 234 dòng thuộc tháng 1–9;
- 226 dòng tháng 1–9 đã nằm ở sổ gốc của sổ khác.

## Bản sao thử

- **Lần 1 (bản đầu của PR).** Dump, restore vào DB thử: dấu vân tay và số dòng chính xác khớp DB thật. Migration hai lượt: 0,11 giây, catalog không đổi giữa hai lượt, dữ liệu không đổi.
  - Phép đo thời gian bắt được `_legacy_undated_match` mất khoảng 0,2 giây mỗi lần. Một lô dán 50 chuyến mất 9,75 giây, sát `statement_timeout` 15 giây.
  - Đã sửa trong PR (commit thứ hai): lọc theo tháng và container trước khi đọc bản sửa. Đo lại trên bản sao: 50 lần còn 0,36 giây; `list_legacy_trip_refs` 20 container còn 0,13 giây. Kết quả trên 300 container mẫu giống hệt bản đầu.
- **Lần 2 (bản cuối).** Dump mới, restore, migration hai lượt: catalog `b528f5d2…` ổn định; dấu vân tay, số dư, số dòng không đổi; checker 9/9 OK. App EXECUTE được `list_legacy_trip_refs`, không EXECUTE được `_legacy_undated_match`.
- Mã băm migration và checker trong commit merge trùng với bản lần 2 (`09a6265e…`, `a75aa608…`).
- Đã xóa các DB thử.

## Cửa sổ dừng ghi (14:24:10–14:24:14 giờ VN)

- Dừng `v7-ledger-api.service`. Ghi dấu vân tay, dump lần nữa kèm hash.
- Áp migration một transaction: 0,13 giây, một `COMMIT`.
- Catalog sau áp trùng bản thử. Dấu vân tay, 236/236 khách, tổng nợ, số dòng chính xác và số event không đổi. Checker 9/9 OK.
- Bật lại API: `active`, loopback 403 (sống). API gián đoạn 4 giây.

## Đổi release

- `git archive 2116bd4 | webdebit-release.sh deploy 2116bd4…` dưới user `webdebit-deploy` (14:27:23 giờ VN). `.release-sha` = `2116bd4`. Không còn file do root sở hữu trong `RELEASES_DIR`.
- Migration và checker trong release trùng hash bản đã chạy.

## Sau

- Checker chạy từ file trong release: 9/9 OK.
- 236 khách, tổng nợ 67.701.771.688 đ và 6.555 event bằng trước đợt.
- Role `v7_app` gọi được `list_legacy_trip_refs`. Journal API không lỗi.
- Hàng chờ đo lại bằng mã mới, cả 236 sổ, chỉ đọc, không sổ nào lỗi chiếu:

| | Trước | Sau |
| --- | ---: | ---: |
| "Chuyến mới" tháng 1–9 | 234 | 14 |
| "Chuyến mới" tháng 10–11 | 107 | 86 |
| Đánh dấu "đã có ở sổ gốc của sổ khác" (`OTHER_BOOK_LEGACY`) | — | 241 |
| Tổng "chuyến mới" chờ duyệt | 341 | 100 |

- 14 dòng tháng 1–9 còn lại:
  - 6 dòng là container có ở sổ khác với ngày lệch hơn 3 ngày, có thể là container dùng lại; cố ý không chặn;
  - 8 dòng không có ở sổ nào: chuyến sót hoặc số container gõ khác giữa booking sheet và Sheet công nợ.
- 21 dòng tháng 10 bị đánh dấu là chuyến trước mốc nạp 21/10, đã nằm ở sổ khác mặt hàng.

**Bằng chứng:** thư mục `backup-20261101-chan-trung` trong `/srv/v7` trên `hao`, ngoài Git (quyền 700). Gồm dump trước (hai lần) và dump lúc dừng kèm sha256, sha256 migration/checker, dấu vân tay mỗi mốc, log áp thử và thật, kết quả checker thử và thật.

## Rollback

- App: `webdebit-release.sh deploy 4b5a9f1c938c8a370cbf71045da7ea2727b72520`. Release cũ không gọi hai hàm mới, chạy được với DB mới.
- DB: áp lại `paste_trips` từ `2026-10-29-v7-ra-ghi-tien.sql` (chỉ thay thân hàm). Hai hàm mới để lại không ảnh hưởng. Hoặc restore `v7-stopped.dump` vào DB mới.

## CÒN MỞ

- **Gán đúng sổ theo mặt hàng (Q4 của bước 02).** Đây là gốc của 241 dòng. Chưa biết booking sheet có cột mặt hàng không; cần người dùng trả lời.
- `edit_trip_info` (sửa container/ngày tại ô) có cùng kẽ hở với dòng sổ gốc không ngày. Để PR riêng sau khi đối chiếu bản hàm trên `hao`.
- 8 dòng "không có ở sổ nào" và 6 dòng lệch ngày xa cần người nhập xem.
- Chưa thử tay trên web (mở một sổ có dòng `OTHER_BOOK_LEGACY`, thấy nhãn "đã có ở sổ gốc của sổ khác" và không có nút Duyệt). Chỉ có test và phép đo hàm chiếu trên `hao`.
