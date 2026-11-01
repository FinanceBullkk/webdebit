# Group Zalo trên web: dựng lại tin, đánh dấu tin, nối vào trang khách (ZALO-GROUP-01)

Trạng thái: ĐÃ CHỐT (người dùng, 1/11/2026, chat). Người dùng chốt hướng và ba câu trả lời; các mặc định Claude tự chọn ghi ở [`ZALO-GROUP-01`](../docs/decisions/zalo-group-01.md). Người dùng chọn **làm luôn**, không chờ hết đợt tạm dừng tính năng của [PLAN](../PLAN.md).

## Người dùng và luồng (bước 1)

Người dùng là chủ tài khoản Zalo. Khách nợ thường nói chuyện trong **group Zalo chung** mà người dùng được add vào. Ở đó khách hứa trả, báo đã chuyển và gửi ảnh chuyển khoản. Hôm nay muốn biết khách đã nói gì thì phải lục lại Zalo; Sheet và web không giữ dấu vết nào.

### Luồng 1. Chọn group được đưa lên web (máy có Zalo, làm một lần)

1. Ở máy có Zalo PC và `zalo-audit-viewer`, chạy `zalo_web_bundle.py list`. Lệnh in các group kèm tên, số tin, ngày tin cuối và cột **lên web**.
2. Chạy `zalo_web_bundle.py add <tên hoặc 8 ký tự đầu id>` cho từng group muốn hiện trên web.
3. Hội thoại riêng tư (chat 1–1, group không chọn) **không bao giờ rời máy**: gói chỉ có group đã chọn.

### Luồng 2. Đọc lại chat của khách trên web (sếp, người đòi nợ, người dùng)

1. Mở **Chat Zalo** (từ Đòi nợ hoặc nút **Mở chat** ở trang khách).
2. Thấy danh sách group đã chọn, mỗi dòng có tên group, sổ đã gắn, ngày tin cuối, ngày mình nhắn gần nhất.
3. Mở một group thì tin hiện như Zalo:
   - tin của mình bên phải, tin người khác bên trái, kèm tên người gửi;
   - ảnh hiện ngay trong tin, bấm vào xem to;
   - tin cũ hơn tải khi bấm **Tải tin cũ hơn**.

### Luồng 3. Đánh dấu một tin (người dùng)

1. Đang đọc group, thấy khách nhắn "mai em chuyển 50 triệu" hoặc gửi ảnh chuyển khoản.
2. Bấm **Đánh dấu** ở tin đó và chọn một trong ba loại:
   - **Hứa trả**: số tiền, hẹn ngày, ghi chú;
   - **Khách báo đã chuyển**: số tiền, ngày khách nói đã chuyển, ghi chú;
   - **Ghi chú**: một câu (khiếu nại, xin giãn, đổi người liên hệ…).
3. Group gắn một sổ thì sổ đó được chọn sẵn. Gắn nhiều sổ thì phải chọn sổ. Chưa gắn sổ nào thì hộp thoại cho gắn ngay.
4. Bấm **Lưu**. Tin đó có nhãn nhỏ (ví dụ "Hứa trả 50.000.000đ · hẹn 5/11").

### Luồng 4. Xem lại khi theo dõi nợ

1. Ở trang khách, thẻ **Trao đổi**: dòng thời gian có các dấu, mỗi dấu một dòng, có trạng thái máy tự chấm.
2. Bấm vào dấu thì sang Chat Zalo, đúng group, cuộn tới đúng tin và tô sáng tin đó.
3. Dấu sai thì **Bỏ dấu** kèm lý do bắt buộc. Dấu bị bỏ vẫn hiện gạch ngang trong Trao đổi.

Kết quả: lần sau ai mở khách cũng thấy khách đã hứa gì, báo chuyển gì, kèm chính tin nhắn và ảnh làm bằng chứng.

### Bị chặn

- Máy chủ chưa có gói chat: trang báo "Máy chủ chưa có dữ liệu chat" như hiện nay ([`ZALO-CHAT-01`](v7-zalo-chat-viewer.md)).
- Ảnh không còn trên Zalo (CDN đã gỡ) hoặc chưa tải về: ô ảnh ghi "Ảnh không còn trên Zalo"; tin và dấu vẫn xem được.
- Tin đã đánh dấu mà không còn trong gói (bỏ chọn group, dựng lại kho): dấu vẫn hiện bằng đoạn chữ đã lưu kèm, ghi "Tin không còn trên web".
- Không có quyền (Tailscale): 403 như mọi trang.

## Đầu ra

1. Công cụ `cong-no-web-handoff/tools/zalo_web_bundle.py` chạy ở máy có Zalo: chọn group, dựng **gói web** chỉ gồm group đã chọn, có tin đã làm sạch và ảnh.
2. Trang Chat Zalo đọc gói web (vẫn đọc được bản xuất cũ): tên người gửi, ảnh, tin hiện kiểu Zalo, mở đúng một tin.
3. Bảng ngoài đường tiền cho **gắn group ↔ sổ** và **dấu tin**, kèm API.
4. Nút Đánh dấu trong chat; thẻ Trao đổi hiện dấu và nối ngược về tin.
5. Đường đẩy gói từ máy có Zalo lên `hao`. **Mở đường ghi mới trên `hao` phải hỏi người dùng trước** (CLAUDE.md: đổi quyền ngoài runbook).

## Đối chiếu dữ liệu và code hiện có (bước 2)

### Nguồn: kho sống của `zalo-audit-viewer` (ngoài repo)

Thư mục `live-sync-20261030/` cập nhật mỗi giây khi Zalo PC chạy. Số liệu đo ngày 1/11/2026, chỉ đếm, không đọc nội dung:

| File | Dùng gì | Ghi chú |
| --- | --- | --- |
| `messages.jsonl` | tin: `message_id, client_message_id, conversation_id, sender_id, timestamp, message_type, status, body, body_state, attachment_metadata`, có thể có `deleted` | 112.999 tin; cùng dạng với bản xuất ZALO-CHAT-01 |
| `conversations.json` | `conversation_id, message_count, participant_ids` | **không có** `display_name` |
| `name-index.json` | `items: {conversation_id: tên}` | 337 tên |
| `conv-meta.json` | `conversations: {id: {is_group, preview}}` | 51 group |
| `user-index.json` | `users: {sender_id: tên}`, `self_user` | 1.717 người; `self_user` thay cách đoán chủ tài khoản |
| `media-index.json` + `media-store/` | ảnh/video Zalo đã lưu ở máy, khớp tin theo `client_message_id` | 270 file; JXL phải đổi sang JPEG |
| `media-url-index.json` | `entries: {message_id: {image: [url…]}}` | 26.496 tin ảnh chỉ còn trên CDN Zalo |

`body` của ảnh (`message_type` 2, 7) là dict có `oriUrl, normalUrl, hdUrl, thumbUrl, params`. Các URL CDN **không bao giờ** vào gói web; công cụ tải ảnh về ở máy có Zalo, chỉ từ host `*.zdn.vn`/`*.zadn.vn` như viewer.

### Code hiện có

- `web/v7_zalo_chat.py`: chỉ mục offset theo hội thoại, trang 0 là mới nhất, tìm không dấu, 3 route GET. Thiếu: tên người gửi, ảnh, chủ tài khoản từ `self_user`, mở trang chứa một tin, nạp lại khi gói đổi.
- `preview/zalo-chat.{html,js,css}`: danh sách + khung tin dạng bảng chữ. Phải đổi sang bong bóng kiểu Zalo.
- `preview/so-khach-v7-contact-ui.js`: thẻ Trao đổi đang có phiếu thu, lần nhắc, hội thoại tìm theo tên. Thiếu: dấu tin, group đã gắn.
- `sokhach.reminder_log` (NHAC-NO-01): mẫu bảng ghi chú ngoài đường tiền, actor lấy từ phiên.
- `sokhach.receipt`: `date`, `amount_vnd`, `voided_on`. Dùng để máy tự chấm dấu, chỉ đọc.

## Thiết kế

### Gói web (máy có Zalo → `hao`)

Lựa chọn group lưu ở `web-groups.json` cạnh thư mục nguồn (`--source`), ngoài mọi repo. File chỉ chứa danh sách `conversation_id`.

`build --out <thư mục>` ghi:

| File | Nội dung |
| --- | --- |
| `conversations.json` | `[{conversation_id, display_name, is_group, participant_ids}]`, chỉ group đã chọn |
| `users.json` | `{"self_user": id, "users": {sender_id: tên}}`, chỉ người có tin trong group đã chọn |
| `messages.jsonl` | tin của group đã chọn, xếp theo thời gian; `body` đã làm sạch (dưới); thêm `media: [sha256…]` |
| `media/<sha256>.<jpg\|png\|gif\|mp4>` | ảnh/video đã kiểm sha256; JXL đổi sang JPEG |
| `media.json` | `{sha256: {mime, bytes, width, height}}` |
| `export-report.json` | `status, built_at, conversation_count, message_count, media_count, media_missing, media_failed`, và `bundle_sha256` (sha của ba file đầu) |

Làm sạch `body`:
- chuỗi: giữ nguyên;
- dict hoặc list: chỉ giữ `title`, `description` và thời lượng (`params.duration`) như `body_text` hiện có, bỏ mọi khóa URL (`oriUrl, normalUrl, hdUrl, thumbUrl, thumb, href, params` thô);
- `attachment_metadata`: bỏ (băm URL không có ích trên web).

Ảnh: lấy từ `media-store` nếu có, không thì tải CDN, cache theo sha256 của URL trong `<out>/media-cache.json`. Lỗi 404 ghi lại, 7 ngày sau mới thử lại. Mỗi lượt tải tối đa `--max-fetch` (mặc định 300) để không dội CDN, **tin mới nhất trước**. Đổi JXL cần `pillow-jxl-plugin` (đã cài cho viewer). Thiếu gói thì đếm vào `media_failed`, không dừng; JXL ở máy không đổi được thì lấy bản của CDN.

**CDN của Zalo chỉ giữ ảnh khoảng 2–3 tuần.** Đo ngày 1/11/2026, mỗi mốc 3 ảnh: 3, 5, 7, 10, 14 ngày đều tải được; 21, 30, 45, 60, 90, 180 ngày đều 404 hoặc host không còn. Hệ quả:
- ảnh cũ chỉ còn nếu Zalo PC đã lưu ở máy (`media-store` của viewer);
- công cụ không gọi CDN cho ảnh cũ hơn `--max-age-days` (mặc định 30), tính là "không còn";
- gói phải dựng **thường xuyên** (ít nhất mỗi ngày) thì ảnh mới mới không mất. Lịch chạy quyết ở G5.

Chạy thử với kho thật, 3 group có tin gần nhất (thư mục nháp, không ghi lựa chọn vào kho): 5.485 tin, 190 ảnh/video (153 có ở máy, 60 tải mới; JXL đổi JPEG được), 13 giây, 95 MB.

Ghi nguyên tử: dựng vào `<out>.tmp-<pid>` rồi đổi tên; `media/` dùng lại giữa các lượt.

### Đọc gói trên web (`v7_zalo_chat.py`)

- Có `users.json` thì lấy `self_user` làm chủ tài khoản, `users` làm tên người gửi; không có thì giữ cách đoán cũ (bản xuất 30/10 vẫn chạy).
- Mỗi tin trả thêm `sender_name` và `media: [{id, mime, width, height}]`, chỉ những sha có trong `media.json`.
- `GET /api/v7/zalo/media/<sha256>`: trả file từ `media/`, kiểu theo `media.json`, `Cache-Control: private, max-age=86400`, `nosniff`. Sha không có trong `media.json` thì 404. Không đọc đường dẫn nào khác.
- `GET /api/v7/zalo/messages?conversation=&message=<id>`: trả trang chứa tin đó (`page` tính sẵn) và `focus: <id>`. Tin không có thì 404 `MESSAGE_NOT_FOUND`.
- Nạp lại: mỗi yêu cầu `stat` file `export-report.json`. Đổi `mtime_ns` hoặc kích thước thì lập chỉ mục lại; trong lúc đó vẫn dùng chỉ mục cũ.

### Bảng ngoài đường tiền (migration `2026-11-01-v7-zalo-group.sql`)

```
sokhach.zalo_link(id, conversation_id text 64 hex, customer_id → customer,
                  linked_by, linked_at, unlinked_by, unlinked_at, unlink_reason)
  một cặp (conversation_id, customer_id) chỉ một dòng còn hiệu lực; một group gắn nhiều sổ, một sổ nhiều group được.

sokhach.contact_mark(id, customer_id → customer, kind ∈ {promise, paid_claim, note},
                     amount_vnd bigint > 0 (bắt buộc với promise/paid_claim, NULL với note),
                     on_date date (promise: hẹn ngày; paid_claim: ngày khách nói đã chuyển; note: NULL),
                     note text,
                     conversation_id, message_id, message_at timestamptz, message_sender text, message_excerpt text ≤ 300 ký tự,
                     created_by, created_at, cancelled_by, cancelled_at, cancel_reason)
```

- Đây là bảng **B2 Hứa trả** của TRANG-KHACH-01 (K4), mở rộng thêm hai loại. Hứa trả gõ tay ở thẻ Trao đổi (không từ tin) cũng ghi vào đây, các cột tin để NULL.
- Không có cột hay hàm nào chạm `v_outstanding_month`, phân bổ, khóa tháng, `customer.version`.
- Hàm `SECURITY DEFINER`, actor từ `sokhach._actor()` như `record_reminder`:
  - `link_zalo(conversation_id, customer_id)`: gắn trùng thì trả dòng đang có;
  - `unlink_zalo(conversation_id, customer_id, reason)`: lý do bắt buộc;
  - `get_zalo_links()`: mọi cặp đang gắn, kèm tên sổ;
  - `record_mark(payload)` với `idempotency_key`: gửi lặp cùng khóa không tạo dòng mới;
  - `cancel_mark(id, reason)`: lý do bắt buộc; bỏ hai lần trả lỗi `MARK_ALREADY_CANCELLED`;
  - `get_marks(customer_id | conversation_id)`: dấu kèm **trạng thái tính khi đọc** (không lưu).

Trạng thái tính khi đọc, chỉ đọc `sokhach.receipt` chưa hủy của đúng sổ:

| Loại | Trạng thái |
| --- | --- |
| Hứa trả | **giữ lời**: tổng phiếu thu từ ngày ghi dấu (giờ VN) tới hẹn ≥ số hứa. **lỡ hẹn**: quá hẹn mà chưa đủ, kèm số đã trả. **đang chờ**: còn lại |
| Khách báo đã chuyển | **đã có phiếu thu**: có phiếu thu đúng số tiền, ngày phiếu trong [ngày báo − 3, ngày báo + 7], kèm `pid`. **chưa thấy phiếu thu**: hôm nay > ngày báo + 3 mà chưa có. **đang chờ**: còn lại |
| Ghi chú | không có trạng thái |

### API (qua xác thực như mọi `/api/v7/*`)

| Route | Thân / query | Trả về | Lỗi |
| --- | --- | --- | --- |
| `GET /api/v7/zalo/links` | — | `{links:[{conversation_id, customer_id, customer_name, linked_at, linked_by}]}` | |
| `POST /api/v7/zalo/link` | `{conversation_id, customer_id}` | dòng gắn | 400, 404 `CUSTOMER_NOT_FOUND` |
| `POST /api/v7/zalo/unlink` | `{conversation_id, customer_id, reason}` | `{ok}` | 400 `REASON_REQUIRED`, 404 `LINK_NOT_FOUND` |
| `GET /api/v7/marks?customer=` hoặc `?conversation=` | đúng một trong hai | `{marks:[…]}`, mới nhất trước | 400 |
| `POST /api/v7/marks` | `{customer_id, kind, amount_vnd, on_date, note, conversation_id, message_id, message_at, message_sender, message_excerpt, idempotency_key}` | dấu vừa ghi | 400 `INVALID_MARK`, 404 |
| `POST /api/v7/marks/cancel` | `{id, reason}` | dấu sau khi bỏ | 400 `REASON_REQUIRED`, 409 `MARK_ALREADY_CANCELLED` |

Kiểm ở API trước khi gọi DB: `amount_vnd` là số nguyên dương (VND nguyên, không chuỗi, không số lẻ); `on_date` dạng `YYYY-MM-DD`; promise không cho hẹn ngày trước hôm nay khi tạo; paid_claim không cho ngày báo sau hôm nay (giờ VN). `note` ≤ 500 ký tự, `message_excerpt` ≤ 300. Mỗi `message_id` phải đi cùng `conversation_id`.

### Giao diện

- Chat Zalo: bong bóng kiểu Zalo (theo đo đạc của viewer), tên người gửi ở tin đầu mỗi cụm, giờ ở cuối cụm, ảnh trong tin, bấm ảnh xem to (Esc đóng).
- Mỗi tin có nút **Đánh dấu**. Trên máy tính nút hiện khi rê chuột hoặc focus; trên điện thoại chạm vào tin thì hiện. Nút cao ≥ 40px, chữ 16px theo [UX](../docs/ux-guidelines.md).
- Đầu khung tin: tên group, các sổ đã gắn (chip, bấm sang trang khách), nút **Gắn sổ**.
- Tin đã có dấu: nhãn dưới bong bóng, bấm vào mở chi tiết dấu, có nút Bỏ dấu.
- `?c=<conversation>&m=<message>` mở đúng tin và tô sáng 3 giây.
- Thẻ Trao đổi: thêm loại mục **Hứa trả**, **Khách báo đã chuyển**, **Ghi chú**; thêm bộ lọc "Hứa trả"; Mở chat dùng group đã gắn trước, tìm theo tên sau.

## Nguồn quyết định

- [`ZALO-GROUP-01`](../docs/decisions/zalo-group-01.md) (1/11/2026): chốt hướng và các mặc định.
- [`TRANG-KHACH-01`](../docs/decisions/trang-khach-01.md) K4 (hứa trả), K6 (gắn hội thoại tay), B2 và B3 do spec này làm.
- [`ZALO-CHAT-01`](v7-zalo-chat-viewer.md), [`NHAC-NO-01`](../docs/decisions/nhac-no-01.md): trang chat đọc bản xuất, chỉ đọc.
- [`UX-NEN-01`](../docs/decisions/ux-nen-01.md) M1: không thêm chỗ ghi tiền thứ hai.

## Hành vi và bất biến

- **Dấu không phải tiền.** Không dấu nào cộng vào số dư, đổi phân bổ, khóa tháng hay bump `customer.version`. "Khách báo đã chuyển" chỉ là việc chờ đối chiếu; tiền chỉ vào sổ bằng phiếu thu.
- Riêng tư: gói chỉ có group trong `web-groups.json`; `hao` không bao giờ nhận hội thoại khác. Test kiểm gói không chứa tin của hội thoại không chọn.
- Gói không chứa URL CDN, đường dẫn máy, key, cookie hay băm URL.
- Công cụ gói chỉ đọc kho viewer: không ghi vào `live-sync-20261030/` ngoài `web-groups.json`. Test kiểm byte trước/sau.
- Trình duyệt nhận ≤ 100 tin mỗi lượt; ảnh tải theo từng tin.
- Không log nội dung tin hay dấu ra console hoặc log server.
- Mọi dấu và gắn sổ ghi người làm (actor từ phiên); bỏ dấu và bỏ gắn bắt buộc lý do, giữ vết.
- VND nguyên; số tiền trống không phải 0: note không có số, promise/paid_claim bắt buộc số.

## Tiêu chí nghiệm thu

- [ ] `tests/test_zalo_web_bundle.py` (fixture bịa): chỉ group đã chọn vào gói; body không còn URL; ảnh local và ảnh CDN (giả lập) vào `media/` đúng sha; thiếu `pillow-jxl` thì đếm `media_failed`; nguồn không đổi byte; ghi nguyên tử.
- [x] `tests/test_v7_zalo_chat.py`: tên người gửi, `self_user`, `media` trong tin, route media (200, 404 sha lạ, không đọc ngoài `media/`), `message=` trả đúng trang, nạp lại khi gói đổi, bản xuất cũ vẫn chạy (G2).
- [x] `preview/test-zalo-chat-browser.js` phần G2: tên người gửi theo cụm, ảnh, xem lớn và Esc, "Ảnh không còn trên Zalo", `?c=&m=` mở đúng tin ở trang giữa và tải được tin mới hơn/cũ hơn, tin không còn thì báo, khung tin tự cuộn ở 1280×720.
- [x] G2 bước 7 (1/11/2026, gói thật 3 group ở thư mục nháp, máy chủ chạy thử không PostgreSQL): 5.485 tin, 190 ảnh/video hiện được; mở hội thoại đứng ở tin mới nhất; 375×812 không tràn ngang. Phát hiện và sửa lỗi có từ ZALO-CHAT-01: `.chat { flex: 1 }` làm trình duyệt bỏ `height`, cả trang dài theo số tin (5.900px) nên mở hội thoại không thấy tin mới nhất.
- [ ] `tools/test_pg_v7_backend_zalo_group.py`: gắn/bỏ gắn, ghi dấu, idempotency, bỏ dấu, trạng thái giữ lời / lỡ hẹn / đang chờ / đã có phiếu thu / chưa thấy phiếu thu, phiếu hủy không tính, không bump version, tổng nợ không đổi.
- [ ] Grants và `v7_post_deploy_check.sql` có các hàm mới.
- [ ] `preview/test-zalo-chat-browser.js`: bong bóng, ảnh, xem to, Đánh dấu ba loại, chọn sổ, gắn sổ, mở `?c=&m=`, bấm lặp Lưu không tạo hai dấu, mất mạng khi lưu, màn 1280×720 và 375×812.
- [ ] `preview/test-so-khach-v7-contact-browser.js`: dấu trong Trao đổi, trạng thái, bấm sang đúng tin, Bỏ dấu.
- [ ] Bước 7: dựng gói thật ở máy này, chạy thử web với gói, đi hết luồng 2–4.
- [ ] Bước 8: người dùng chọn group thật, tự đi hết luồng và quyết định đẩy lên `hao`.

## Kế hoạch PR

| PR | Nội dung | Ghi chú |
| --- | --- | --- |
| G1 | Spec, quyết định, `zalo_web_bundle.py` + test | không đụng `hao` |
| G2 | `v7_zalo_chat.py` đọc gói, route media, `message=`, nạp lại; giao diện chat kiểu Zalo có ảnh | tự deploy khi merge; `hao` chưa có gói nên vẫn báo chưa có dữ liệu |
| G3 | Migration `zalo_link` + `contact_mark`, hàm, API, harness PG | triển khai tay theo runbook ([`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md)) |
| G4 | Đánh dấu, gắn sổ trong chat; dấu trong thẻ Trao đổi | |
| G5 | Đẩy gói lên `hao` | **hỏi người dùng trước** khi mở đường ghi |

## Phạm vi agent

- Agent: claude (`CLAUDE-ALL-01`)
- Review: opus (bảng mới cạnh đường tiền, dữ liệu riêng tư)
- Được sửa: spec này, `docs/decisions/zalo-group-01.md`, `docs/decisions.md`, `PLAN.md`, `cong-no-web-handoff/tools/zalo_web_bundle.py`, `cong-no-web-handoff/tests/test_zalo_web_bundle.py`, `web/v7_zalo_chat.py`, `web/v7_ledger_api.py`, `web/v7_api_tables.py`, `web/v7_api_validate.py`, `preview/zalo-chat.*`, `preview/so-khach-v7-contact-ui.js`, `preview/so-khach-v7-contact.css`, `preview/so-khach-v7-browser-world.js`, test tương ứng, migration mới, `tools/v7_backend_functions.sql`, `tools/v7_post_deploy_check.sql`, các file test PG liên quan.
- Lệnh kiểm: `npm run check`, `node scripts/check-secrets.js`; harness PG ở G3.
- Cấm: thêm dependency vào repo; chép dữ liệu chat vào repo (test chỉ dùng fixture bịa); đụng hàm hoặc bảng tiền; ghi vào thư mục Zalo hay kho viewer.

## Hoàn tác

- G1, G2, G4: revert PR.
- G3: `DROP` hai bảng và các hàm mới theo runbook (chỉ thêm, không gì tham chiếu tới).
- G5: xóa thư mục gói trên `hao`, bỏ biến môi trường.

## Câu hỏi mở

- CÒN MỞ: một group thường ứng với một khách hay nhiều khách? Thiết kế cho phép cả hai (gắn nhiều sổ); hỏi lại người dùng khi nghiệm thu.
- CÒN MỞ: tự đẩy gói lên `hao` theo lịch (mỗi 5 phút?) hay bấm tay. Quyết ở G5.
