# Chat Zalo trên web: xem lại hội thoại với khách từ bản xuất (ZALO-CHAT-01)

Trạng thái: ĐÃ CHỐT (người dùng, 30/10/2026, chat: "tính năng đòi nợ đang không đúng ý… xem bundle rồi build"). Thay hướng *metadata-only* của [`NHAC-NO-01`](../docs/decisions/nhac-no-01.md): web hiện **nội dung** chat từ bản xuất đã giải mã sẵn, không còn helper đọc RAM Zalo.

## Người dùng và luồng (bước 1)

- **Sếp / người đi đòi** mở tab **Đòi nợ**, bấm **Chat** ở dòng khách → sang trang **Chat Zalo** với ô tìm đã điền tên khách; nếu chỉ còn một hội thoại khớp thì mở luôn. Đọc tin mới nhất ở cuối, bấm **Tải tin cũ hơn** để lùi về trước; gõ vào **Tìm trong hội thoại** để lọc tin có chữ đó (không phân biệt dấu/hoa thường, có tô vàng chữ khớp).
- Không có tên khách trong bản xuất (48 hội thoại) thì hiện "Chưa rõ tên · 8 ký tự đầu id"; vẫn mở xem được.
- Mỗi hội thoại trong danh sách: tên, số tin, ngày tin cuối, **ngày mình nhắn gần nhất** (= mốc "đã nhắc" đọc thẳng từ chat, không cần ai ghi).
- Điện thoại: một cột; chọn hội thoại thì sang màn tin nhắn, nút ← về danh sách.

Bị chặn: máy chủ chưa có bản xuất → trang báo rõ cách bật, không treo "Đang tải"; hội thoại không còn trong bản xuất → báo; không có quyền (Tailscale) → 403 như mọi trang.

## Đầu ra

Trang `/zalo-chat.html` (con của Đòi nợ, nav vẫn tô "Đòi nợ") đọc 104.387 tin / 331 hội thoại của bản xuất mà trình duyệt chỉ nhận từng trang ≤ 100 tin. Tab Đòi nợ có nút **Chat** ở mỗi dòng khách.

## Đối chiếu dữ liệu và code hiện có (bước 2)

Nguồn: bundle `zalo-web-handoff-20261030` (HermesAgent xuất 30/10/2026, ngoài repo): `conversations.json` (331 hội thoại, 283 có `display_name`), `messages.jsonl` (104.387 dòng, 113 MB; mỗi dòng `message_id, conversation_id, sender_id, timestamp (ms, chuỗi số), message_type, status, body (chuỗi | thẻ dict | list), body_state, attachment_metadata`), `export-report.json`. ID đã băm HMAC, URL/đường dẫn media bị rút, không có file media.

Thống kê đã đo trên bản xuất (dùng để đặt nhãn): `message_type` 1 văn bản (70.307), 2 ảnh, 3 ghi âm, 4 sticker, 6 cuộc gọi, 7 GIF, 17 vị trí, 18 video, 19 tệp, 20 thu hồi, 21 thẻ liên kết, −4 thông báo nhóm; `status` 2 ↔ 100% tin chủ tài khoản gửi, 4 ↔ tin nhận (88 tin status 1 giữ số). Chủ tài khoản không được ghi trong bản xuất: suy ra là `sender_id` có mặt ở nhiều hội thoại nhất (238/331). Đính kèm: 25.035 tin khớp bảng media, 1.655 tin có liên kết băm nhưng chưa khớp media (sticker và cuộc gọi không tính là đính kèm). `body` null: 0 ở bản này, vẫn hiện "Không đọc được nội dung" nếu có.

Code dùng lại: khung trang (`cong-no-theme.css`, `dashboard-v7.css`, nav), server `web/v7_ledger_api.py` (`PAGES`, xác thực danh tính, `log_message` không ghi gì), `presence.js`. Thiếu: module đọc bản xuất, 3 route API, trang + JS + CSS, nút Chat ở Đòi nợ.

## Giao tiếp frontend–backend (bước 5)

Module `web/v7_zalo_chat.py` (stdlib, chỉ đọc). Thư mục bản xuất lấy từ biến môi trường `WEBDEBIT_ZALO_EXPORT_DIR`; chưa đặt → mọi route trả `503 ZALO_EXPORT_UNAVAILABLE`. Khởi động server (`main()` của `v7_ledger_api`) lập chỉ mục trong luồng nền (~1 giây cho 113 MB); yêu cầu đầu tiên chưa xong thì chờ khóa.

| Route (GET, qua xác thực như mọi `/api/v7/*`) | Trả về | Lỗi |
|---|---|---|
| `/api/v7/zalo/report` | `conversation_count, message_count, named_conversations, owner_conversations, body_missing, attachment_matched, attachment_unmatched, skipped_lines, status` | 400 nếu có query |
| `/api/v7/zalo/conversations?q=` | `{conversations:[{conversation_id, display_name, name_status, message_count, last_message_at, last_own_message_at, participant_count}], total}` xếp theo tin cuối mới nhất; `q` khớp tên không dấu hoặc tiền tố id | 400 tham số lạ |
| `/api/v7/zalo/messages?conversation=<64 hex>&page=0&limit=50&q=` | `{messages:[…], total, page, limit, pages, has_older, query}`; **trang 0 = tin mới nhất**, trong trang xếp tăng dần theo thời gian; `limit` 1..100; `q` lọc theo chữ của tin (không dấu) | 400 tham số sai, 404 `CONVERSATION_NOT_FOUND` |

Mỗi tin: `message_id, sender_id, is_own, timestamp_ms, message_type, type_label, status, status_label, body_kind (text|card|missing), body_text, body_state, attachment (null | {state: matched|unmatched, title, url_count, media_items:[{source_table, ext_type, title, file_size, width, height}]})`. Không bao giờ trả `url_sha256`, `path_hmac`, `params` thô.

Chạy thử tại máy có bản xuất, không cần PostgreSQL (các trang sổ khác trả 503):

```bash
python cong-no-web-handoff/web/v7_zalo_chat.py --export-dir <thư mục data của bundle> --port 8781
```

Trên `hao`: chép thư mục `data/` của bundle ra ngoài release (ví dụ `/var/lib/webdebit-zalo/`), đặt `Environment=WEBDEBIT_ZALO_EXPORT_DIR=…` trong unit rồi restart. **Việc chép dữ liệu chat lên `hao` là quyết định của người dùng** (dữ liệu riêng tư), không làm tự động trong deploy.

## Nguồn quyết định

- [`NHAC-NO-01`](../docs/decisions/nhac-no-01.md) (sửa đổi 30/10/2026: bỏ helper metadata-only, đọc bản xuất đầy đủ), [`DASH-03`](../docs/decisions/dash-03.md).
- CÒN MỞ: map hội thoại ↔ sổ khách (hiện nối bằng tìm tên); cập nhật bản xuất định kỳ (bundle là ảnh chụp một lần 30/10/2026); có ghi "đã nhắc" từ `last_own_message_at` vào `reminder_log` hay không.

## Hành vi và bất biến

- Chỉ đọc: không sửa file bản xuất, không có route ghi; test kiểm byte file trước/sau không đổi.
- Trình duyệt không bao giờ nhận cả `messages.jsonl`; mỗi lượt ≤ 100 tin.
- Không log nội dung tin ra console/telemetry (server `log_message` rỗng; test trình duyệt kiểm console).
- Dữ liệu chat không vào repo: test chỉ dùng fixture bịa; `.gitignore` không thay review.
- Truy cập qua lớp danh tính hiện có của `/api/v7/*` (Tailscale); bản chạy thử bind loopback.
- Không khôi phục ID Zalo gốc; không hiện URL/đường dẫn media.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_zalo_chat.py`: chỉ mục, nhận chủ tài khoản, danh sách + tìm không dấu, phân trang (trang 0 mới nhất, `has_older`), tìm trong hội thoại, 400/404/503, file nguồn không đổi, trang được phục vụ.
- [x] `preview/test-zalo-chat-browser.js`: danh sách, mở hội thoại, tải tin cũ hơn, tìm, `?q=` tự mở, 503 báo rõ, màn điện thoại.
- [x] Bước 7: xem với bản xuất thật tại máy (30/10/2026): lập chỉ mục 1,0 giây; tìm trong hội thoại 33.391 tin 0,5 giây; trang 1280×720 và 375×812 đi hết luồng.
- [ ] Bước 8: người dùng tự đi hết luồng trên bản thử (`python web/v7_zalo_chat.py --export-dir …`) và quyết định có chép bản xuất lên `hao`.

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`)
- Được sửa: `web/v7_zalo_chat.py`, `web/v7_ledger_api.py`, `web/v7_presence.py`, `preview/zalo-chat.{html,js,css}`, `preview/doi-no.{js,css}`, `preview/presence.js`, `preview/test-zalo-chat-browser.js`, `tests/test_v7_zalo_chat.py`, spec này, `docs/decisions/nhac-no-01.md`, `docs/decisions.md`.
- Lệnh kiểm: `npm run check`, `node scripts/check-secrets.js`.
- Cấm: thêm dependency; chép dữ liệu chat vào repo; đụng đường tiền.

## Hoàn tác

Revert PR; không có dữ liệu hay schema nào thay đổi.

## Bằng chứng

Ghi ở PR: `npm run check` xanh, ảnh chụp bản thử với bản xuất thật (không đính kèm nội dung chat vào repo).
