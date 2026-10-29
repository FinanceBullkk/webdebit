# Triển khai tay: xóa điều chỉnh cả tháng + tách phụ phí PS (29/10/2026)

**ĐÃ CHẠY trên `hao` ngày 29/10/2026**, Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) (người dùng cho Claude tự triển khai SQL/migration, cùng ngày). Lượt `Deploy hao` của `d1636f6` đỏ ở cổng SQL là chủ ý.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#161 (XOA-DC-THANG-01, `d1636f6`), FinanceBullkk/webdebit#160 (tách phụ phí PS PR-1, `f7d4817`) |
| Quyết định / spec | [`XOA-DC-THANG-01`](../decisions/xoa-dc-thang-01.md), [`v7-phu-phi-tu-ps`](../../specs/v7-phu-phi-tu-ps.md) |
| Migration, **đúng thứ tự** | 1. `2026-10-29-v7-xoa-dieu-chinh-thang.sql` 2. `2026-10-29-v7-ps-fee.sql` |
| Release app | `310ee69` → `f7d4817` (CI `main` xanh đúng SHA) |
| Ghi tiền | Không. Thêm cột `adjustment.reverses_adjustment_id` (NULL), hai loại event, ba hàm, thay view `v_adjustment_current`; không đổi dữ liệu có sẵn |

## Trước

`hao` chạy `310ee69`. Cả hai migration chưa áp: không có cột `reverses_adjustment_id`, không có hàm `rewrite_trip_fees`. DB `webdebit_v7` ~30 MB, 236 khách, đĩa còn 70 GB.

## Bản sao thử

Dump `webdebit_v7` đang chạy, restore vào DB thử (thu hồi CONNECT của PUBLIC). Dấu vân tay số dư khớp DB thật. Chạy `xoa-dieu-chinh-thang.sql` hai lượt rồi `ps-fee.sql` hai lượt, mỗi lượt dưới 1 giây. Sau đó các mục sau đều giữ nguyên:

- dấu vân tay số dư (`md5` của `v_outstanding_month`);
- số dư từng khách (236);
- số dòng khách/event/phiếu thu/chuyến/điều chỉnh/`v_adjustment_current`.

`event_kind_check` có đủ `adjust_month_delete`, `rewrite_trip_fees` và các loại ảnh chứng từ. `v7_post_deploy_check.sql` 9/9 OK. Đã xóa DB thử.

Lần chạy thử đầu dừng trước bước migration vì `postgres` không đọc được thư mục 700 của root. Sửa bằng cách đưa SQL qua stdin, xóa DB thử đó rồi chạy lại. DB thật không bị đụng ở lần đó.

## Cửa sổ dừng ghi

- Dừng `v7-ledger-api.service`, đo lại dấu vân tay/số dòng/số dư từng khách, dump lần hai và hash.
- Áp hai migration (mỗi file tự một transaction), tổng 1 giây. Dấu vân tay, số dư 236/236 khách và số dòng không đổi; ràng buộc có đủ loại.
- Đổi release bằng `webdebit-release.sh deploy f7d4817` dưới user deploy (script tự restart và kiểm sống). `.release-sha` = `f7d4817`.

## Sau

- `v7_post_deploy_check.sql` 9/9 OK (236 khách, 877 kỳ mở đầu). Cổng loopback 403 (sống). Dấu vân tay số dư không đổi sau khi đổi release.
- `delete_month_adjustment`, `rewrite_trip_fees`: role app được EXECUTE, reader không. `_rewrite_trip_fees`: không ai được EXECUTE.
- **Bằng chứng:** thư mục backup `v7-xoa-dc-ps-fee-20261029-175657` trên `hao` (dump trước, dump lúc dừng, hash migration, dấu vân tay, số dư, log áp migration, kết quả checker), ngoài Git.

## Rollback

- App: trỏ `CURRENT_LINK` về release `310ee69` trong `RELEASES_DIR` rồi restart. DB mới tương thích release cũ vì chỉ thêm: cột mới để trống, view cho kết quả như cũ khi chưa có dòng đảo.
- DB: hàm mới không đổi dữ liệu nên để nguyên được. Nếu đã có lệnh xóa hoặc tách phí và cần quay lại hẳn, restore `v7-stopped.dump` vào DB mới (quy trình M2-11), không viết SQL "down" tay.

## CÒN MỞ

- **Runner bảng PS chưa cài** (runbook mục tách phụ phí PS, bước 0): chạy thử đọc dưới user runner trả `HTTPError`. Tức là tài khoản dịch vụ chưa đọc được file bộ lập bill. Cần người dùng chia sẻ file bộ lập bill (chỉ xem) cho email tài khoản dịch vụ, và đặt `WEBDEBIT_PS_SHEET_ID` trong env runner (không ghi vào repo). Tới lúc đó, sổ trả `ps_fees.unavailable`, chức năng khác không ảnh hưởng.
- Chưa thử tay trên web: xóa một dòng điều chỉnh cả tháng (hai dòng thử ghi trước đó giờ mới ẩn được).
