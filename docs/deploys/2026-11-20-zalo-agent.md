# Triển khai tay: bật `zalo-agent` thay task 15 phút (ZALO-AGENT-01, bước Chuyển, 20/11/2026)

**ĐÃ CHẠY trên máy có Zalo (`msi`) và `hao` ngày 20/11/2026.** Bước Chuyển của [`ZALO-AGENT-01`](../decisions/zalo-agent-01.md); người dùng bấm "Merge và bật agent" trong chat. Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md) và [spec](../../specs/zalo-agent.md#kế-hoạch-chia-pr-và-cổng).

| Mục | Nội dung |
| --- | --- |
| Code | PR-0 FinanceBullkk/zalo-audit-viewer#1 (`b52fe44`); spec FinanceBullkk/webdebit#540; PR-2 FinanceBullkk/webdebit#542 (`8dc3d53`, `Deploy hao` xanh); PR-1 FinanceBullkk/webdebit#543 (`a3f4fb6`) |
| SQL, DB | Không. Không đổi bảng, hàm, quyền DB hay dữ liệu tiền |
| Ghi tiền | Không |

## PR-0 áp lên thư mục live-sync (09:52)

- Dừng `watchdog.py`, `live_sync.py --interval 1`, `server.py --port 8766`; `git merge --ff-only origin/main` ở `D:\zalo-audit-viewer`.
- Xóa `logs/heap-probe.log` cũ (khoảng 530 MB, mỗi lần dò in nguyên hai file JSON) và `blocker.json` cũ không mảnh nào đọc.
- Bật lại watchdog bằng chính lối tắt Startup `ZaloAuditWatchdog.lnk`.
- Kiểm: heap probe `exit=0`, in một dòng số đếm; poller gắn lại, đọc tiếp revision; `poller.log` cũ 22 MB xoay thành `.1`; `logs/` khoảng 23 MB.

## Trên `hao`

- `install -d -o aohanh -g v7app -m 2750 /srv/v7/zalo-agent`: chủ là tài khoản ssh đẩy, nhóm `v7app` chỉ đọc, setgid.
- Trước khi bật, thử kênh đẩy chung của PR-1 ở thư mục tạm `/srv/v7/zalo-agent-test` (cùng cách dựng), ba lượt dữ liệu bịa: mọi thư mục `drwxr-s---` nhóm `v7app`, file `0640`, 0 mục sai nhóm, 0 thư mục mất setgid, lượt hai dọn đúng thư mục và ảnh cũ, lượt ba y hệt không gửi tar, `v7app` đọc được. Đã xóa thư mục tạm.

## Trên máy có Zalo

- **Giữ ảnh cũ:** gói mới dựng trong `D:\zalo-agent\bundle`. Đã chép `media/` (77 ảnh) và `media-cache.json` từ `D:\zalo-web-bundle` sang trước lượt đầu. Nếu không, ảnh chỉ còn trong bộ nhớ đó (CDN Zalo giữ ảnh 2–3 tuần) sẽ thiếu và bị dọn khỏi `hao`.
- Lượt `--dry-run`: 367 tin, 77 ảnh (37 từ bộ nhớ, 58 có ở máy), `bundle_sha256` trùng gói của task cũ.
  - `--dry-run` lưu con trỏ như đã xong (`reason: first_run`). Đã xóa `state/bundle.json`, `status.json`, `identity.json` trước lượt thật. CÒN MỞ: dry-run không nên lưu con trỏ.
- Tắt (không xóa) task `WebdebitZaloSync` sau khi chắc nó không đang chạy; lần chạy cuối 10:41, thành công.
- Lượt thật `run --once` từ checkout `main` (`a3f4fb6`): dựng lại, đẩy 409.600 byte. Trên `hao`: `/srv/v7/zalo-bundle` và `/srv/v7/zalo-agent` đều đúng quyền, 0 sai nhóm, không sót `.incoming`.
- Task Scheduler `ZaloAgent`:
  - lệnh: `pythonw -X utf8 -I D:\webdebit\repo\cong-no-web-handoff\tools\zalo_agent run`, thư mục làm việc `D:\webdebit\repo`, Python 3.13 của máy (có `pillow_jxl`);
  - trigger: lúc đăng nhập, và lặp 15 phút làm lưới an toàn (khóa tiến trình chặn bản thứ hai);
  - chạy cả khi dùng pin, `IgnoreNew`, không giới hạn thời gian, tự chạy lại sau 1 phút tới 999 lần.

## Kiểm

- `status.json` trên `hao` tự cập nhật mỗi phút (10:52:54 → 10:55:22), `push` không lỗi, `identity: attached`.
- Tab Máy chạy: "Máy Zalo báo lúc 10:55 · 1 nhóm đã chọn", "Gói chat — Đang chạy, kịp tin mới".
- Chat Zalo trên `hao`: 367 tin không trùng, 77/77 ảnh trả 200.
- Ghi nhận: `hao` nạp lại gói kiểu lười. Yêu cầu đầu tiên sau khi gói đổi kích hoạt việc nạp lại ở luồng nền và vẫn nhận bản cũ; yêu cầu sau thì đúng. Đây là nguyên nhân của hiện tượng "API chậm một lượt" thấy sáng cùng ngày.

## CI `main` đỏ sau khi merge PR-1

`Tests` của `a3f4fb6` đỏ ở job `javascript (windows-latest)`, nên `Deploy hao` của commit đó bị bỏ qua (agent chạy ở máy Zalo nên không bị ảnh hưởng).

- Gốc: test `test_media_and_users_replaced_in_place_reach_new_delta_messages` (PR-2) ghi lại `export-report.json` cùng cỡ chỉ vài mili giây sau lần trước. `v7_zalo_chat` nhận biết gói đổi bằng `(mtime, cỡ)`, nên trên Windows hai lần ghi cùng nhịp đồng hồ thì không thấy đổi. Đo trên `msi`: 14/200 cặp ghi liền nhau cho cùng `(mtime, cỡ)`.
- Sửa: nhận biết bằng băm nội dung `export-report.json`, kèm test ép cùng cỡ và cùng giờ.

## CÒN MỞ

- Đo một ngày làm việc: tin mới lên web trong 30 giây (p95), khởi động lại máy rồi mở Zalo thì agent tự đuổi kịp (tiêu chí bước Chuyển).
- `--dry-run` không nên lưu con trỏ.
- PR-3: chuyển đường đẩy bảo hiểm vào agent rồi tắt `ZaloInsurancePush` (hỏi người dùng trước khi tắt).

## Rollback

- Máy có Zalo: `Disable-ScheduledTask ZaloAgent`, `Enable-ScheduledTask WebdebitZaloSync`. Gói trên `hao` vẫn đọc được vì thiếu phần thêm thì chỉ đọc gói gốc.
- `hao`: `/srv/v7/zalo-agent` xóa được; thiếu `status.json` thì tab Máy chạy hiện "Chưa có máy Zalo báo về", máy canh im.
