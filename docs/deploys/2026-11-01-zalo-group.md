# Triển khai tay: group Zalo — gắn sổ và dấu tin (1/11/2026)

**ĐÃ CHẠY trên `hao` ngày 1/11/2026.** Claude chạy theo [`DEPLOY-CLAUDE-01`](../decisions/deploy-claude-01.md); người dùng chọn "Làm luôn" cho [`ZALO-GROUP-01`](../decisions/zalo-group-01.md). `Deploy hao` của commit merge dừng ở cổng SQL là chủ ý (diff có `tools/migrations/`, `.sql`, `specs/v7-backend/`).

| Mục | Nội dung |
| --- | --- |
| PR | FinanceBullkk/webdebit#244 (G3) |
| Quyết định | [`ZALO-GROUP-01`](../decisions/zalo-group-01.md), spec [`v7-zalo-group-web`](../../specs/v7-zalo-group-web.md), mục runbook "Group Zalo: gắn sổ và dấu tin" |
| Migration | `2026-11-01-v7-zalo-group.sql` (sha256 `a573d5ac…`): thêm bảng `zalo_link`, `contact_mark` và 7 hàm. Chỉ THÊM, ngoài đường tiền: không đổi bảng tiền, ràng buộc, loại event, view nợ, phân bổ, dữ liệu hay quyền cũ. Chạy lại được. |
| Ghi tiền | Không ghi, không đổi. Tổng từng khách và số event không đổi. |

## Trước

- `hao` chạy release `443b3d4` (G2, FinanceBullkk/webdebit#243, `Deploy hao` xanh).
- DB `webdebit_v7`: 236 khách, 6.555 event, tổng nợ trên web 67.701.771.688 đ. Dấu vân tay tổng từng khách (`md5` tổng `v_outstanding_month` theo khách) `8e3314…`.
- Không phiên nào nối vào DB; nhật ký `sudo` 30 phút chỉ có hai lượt `Deploy hao` của G1, G2 và lệnh đọc của đợt này.

## Bản sao thử

- Dump `webdebit_v7` (`-Fc`, 571 mục), sha256 lưu cạnh dump; restore vào DB thử (thu hồi CONNECT của PUBLIC).
- Migration **hai lượt** (`psql -X -v ON_ERROR_STOP=1`): 147 ms rồi 110 ms; lượt hai chỉ báo "đã có, bỏ qua".
- Dấu vân tay, số event, số khách, tổng nợ trước = sau. `v7_post_deploy_check.sql` **9/9 OK**.
- Quyền:
  - app gọi được `record_mark`, `link_zalo`;
  - reader gọi được `get_marks`, không gọi được `record_mark`;
  - app không gọi được `_mark_json`, không đọc thẳng được bảng.
- Gọi thử dưới role `v7_app` trong một transaction rồi ROLLBACK: `get_zalo_links`, `link_zalo`, `record_mark` (ghi chú), `get_marks` đều chạy. Dấu vân tay không đổi. Đã xóa DB thử.

## Cửa sổ dừng ghi (08:01:35–08:01:37 UTC, 15:01 giờ VN)

- Hash migration và checker trong commit merge `fc7a927` trùng bản đã thử (`a573d5ac…`, `34aad15a…`). Các phiên Claude khác đều nghỉ (`ListAgents`).
- Dừng `v7-ledger-api.service`. Dấu vân tay lúc dừng bằng lúc thử; script tự dừng nếu lệch. Dump lần hai (`v7-stopped.dump`) kèm sha256.
- Áp migration một transaction: 261 ms.
- Dấu vân tay, 236 khách, 6.555 event, tổng nợ 67.701.771.688 đ không đổi. Checker 9/9 OK; hai bảng mới có mặt.
- Bật lại API: `active`. API gián đoạn 2 giây.

## Đổi release

- `git archive fc7a927 … | webdebit-release.sh deploy fc7a927…` dưới user `webdebit-deploy`. Script tự restart và kiểm sống. `.release-sha` = `fc7a927` (trước: `443b3d4`).
- Sau đổi release:
  - `/healthz` loopback 200;
  - checker chạy từ file trong release 9/9 OK;
  - journal API 5 phút không có lỗi.
- Qua Tailscale Serve, chỉ GET:
  - `/api/v7/zalo/links` → `{"links":[]}`;
  - `/api/v7/marks?customer=1` → `{"marks":[]}`;
  - `/zalo-chat.html` → 200;
  - `/api/v7/zalo/report` → 503 `ZALO_EXPORT_UNAVAILABLE`, đúng vì chưa có gói chat.

## Bằng chứng

Thư mục `backup-20261101-zalo-group` trong `/srv/v7` trên `hao`, ngoài Git, quyền 700, chủ `postgres`. Gồm dump trước và dump lúc dừng kèm sha256, bản migration và checker đã chạy.

## Rollback

- DB: `DROP TABLE sokhach.contact_mark, sokhach.zalo_link` và `DROP FUNCTION` các hàm `link_zalo`, `unlink_zalo`, `get_zalo_links`, `record_mark`, `cancel_mark`, `get_marks`, `_mark_json` dưới `sokhach_owner`; không gì tham chiếu tới. Hoặc restore `v7-stopped.dump` vào DB mới.
- App: `webdebit-release.sh deploy 443b3d455fe79caa2cc485f8bd81d1e9bc711137`. Release cũ không gọi bảng hay hàm mới.

## G5: đường đẩy gói chat

Người dùng đồng ý trong chat 1/11/2026 ("Đồng ý làm G5"), sau khi Claude nêu đủ ba việc: thư mục trên `hao`, biến môi trường cho API, lịch đẩy 15 phút. Đây là đổi systemd ngoài runbook nên phải hỏi theo `DEPLOY-CLAUDE-01`.

- 08:37 UTC:
  - tạo `/srv/v7/zalo-bundle` (`drwxr-s---`, chủ `aohanh`, nhóm `v7app`);
  - thêm drop-in `/etc/systemd/system/v7-ledger-api.service.d/zalo-bundle.conf` với `Environment=WEBDEBIT_ZALO_EXPORT_DIR=/srv/v7/zalo-bundle`;
  - `daemon-reload`, restart API.
- Sau restart:
  - `active`, `/healthz` 200;
  - `v7app` đọc được thư mục;
  - `/api/v7/zalo/report` báo 503 "không đọc được conversations.json", đúng vì chưa có gói.
- Thử đường đẩy thật (ssh + tar) bằng **gói bịa** của test, vào thư mục tạm trên `hao`, rồi xóa:
  - lượt 1 gửi 4 ảnh, lượt 2 không gửi lại ảnh;
  - group bỏ chọn bị xóa phía `hao`;
  - thư mục khớp từng file với máy này.

  Không dữ liệu chat thật nào lên `hao` trước khi người dùng chọn group.

Rollback G5: tắt task `WebdebitZaloSync`; xóa `zalo-bundle.conf`, `daemon-reload`, restart API; xóa `/srv/v7/zalo-bundle`.

## CÒN MỞ

- Người dùng chọn group đưa lên web (`zalo_web_bundle.py add`). Tới lúc đó lượt đồng bộ chỉ ghi "bỏ qua: chưa chọn group nào".
- Người dùng tự đi hết luồng trên web thật: đọc chat, đánh dấu, gắn sổ, xem ở thẻ Trao đổi.
