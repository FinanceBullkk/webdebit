# Triển khai tay: phiếu thu trong ngăn kéo Công nợ theo tháng (29/10/2026)

**ĐÃ CHẠY trên `hao` ngày 29/10/2026 (khoảng 22:26–22:31 giờ VN)**. Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md). Lượt `Deploy hao` của `f528c7c` đỏ ở cổng SQL là chủ ý.

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#181 (UI ngăn kéo, `93ff0ef`, đã tự lên qua `Deploy hao`), FinanceBullkk/webdebit#183 (phiếu thu, `f528c7c`) |
| Spec | [`v7-cong-no-theo-thang-de-xuat`](../../specs/v7-cong-no-theo-thang-de-xuat.md), mục "Ngăn kéo chi tiết tháng — audit UI 29/10/2026" |
| Migration | `2026-10-29-v7-matrix-drawer-receipts.sql`: chỉ `CREATE OR REPLACE` `get_receivables_detail`. Bản `2026-10-29-v7-matrix-drawer-so-goc.sql` đã có trên `hao` từ trước. |
| Release app | `1ea04c9` → `f528c7c` (Tests `main` xanh đúng SHA) |
| Ghi tiền | Không. Hàm chỉ đọc, thêm trường `receipts`; không đổi dữ liệu |

## Bản sao thử

- Dump `webdebit_v7` đang chạy rồi kiểm đọc lại được (`pg_restore --list`).
- Restore vào DB thử, thu hồi CONNECT của PUBLIC. Chạy migration hai lượt.
- Dấu vân tay số dư (`md5` của `v_outstanding_month`), số dư 236 khách và số dòng khách/event/phiếu/dòng phân bổ/chuyến đều giữ nguyên.
- 236/236 sổ trả trường `receipts` cho tháng hiện tại. `v7_post_deploy_check.sql` 9/9 OK.
- Đã xóa DB thử.

Hai lần đầu không tính: lần một file migration rỗng vì máy chưa fetch `f528c7c`, nên migration không chạy. Lần hai checker không đọc được file trong thư mục 700. Cả hai lần chỉ đọc DB thật. Sửa bằng cách fetch và đưa SQL qua stdin.

## Cửa sổ dừng ghi

- Dừng `v7-ledger-api.service`. Đo lại dấu vân tay, số dư và số dòng. Dump lần hai và ghi hash.
- Áp migration (một transaction, 0,13 giây). Dấu vân tay, số dư 236/236 khách và số dòng không đổi. Checker 9/9 OK.
- Bật lại API. Đổi release bằng `webdebit-release.sh deploy f528c7c` dưới user deploy. `.release-sha` = `f528c7c`; cổng loopback trả 403 (sống).

## Sau

- Dấu vân tay số dư sau khi đổi release vẫn như trước. Trên DB thật, 236/236 sổ trả `receipts`.
- Mở trang thật qua Tailscale, bấm một ô tháng 10:
  - chuyến xếp theo ngày, có nhãn "sổ gốc";
  - dòng tổng chuyến có tính bằng phát sinh tháng;
  - chuyến chờ kiểm/chưa có giá có ghi chú riêng;
  - ô đang mở được tô viền.
- **Bằng chứng:** thư mục backup `v7-drawer-receipts-20261029-222617` trên `hao`, ngoài Git. Gồm:
  - dump trước và dump lúc dừng, kèm hash;
  - hash migration;
  - dấu vân tay, số dư, số dòng;
  - log áp migration, kết quả checker thử và thật.

## Dọn release cũ

Lượt `Deploy hao` của `1ea04c9` báo đỏ dù release đã lên. Nguyên nhân: `webdebit-release.sh` không xóa được `__pycache__` do root sở hữu trong release cũ. Trước khi đổi release, Claude đã `chown` cho `webdebit-deploy` mọi file root trong `/srv/v7/auto-releases`, và lượt đổi release tay đã dọn xong. File `.pyc` của root sẽ còn sinh ra nếu một dịch vụ chạy bằng root import mã từ release.

## Rollback

- App: trỏ `CURRENT_LINK` về release `1ea04c9` rồi restart. Release cũ bỏ qua trường `receipts`.
- DB: hàm chỉ đọc, để nguyên được. Muốn quay hẳn thì chạy lại `2026-10-29-v7-matrix-drawer-so-goc.sql` (cũng chỉ thay hàm này), hoặc restore `v7-stopped.dump` vào DB mới.

## CÒN MỞ

- Chưa thấy tận mắt bảng phiếu thu trên dữ liệu thật: tháng đã mở thử không có phiếu web (DB đang có 5 phiếu).
- Tìm dịch vụ chạy bằng root đang ghi `__pycache__` vào release, để `Deploy hao` không đỏ ở bước dọn.
