# V7 — thấy ai đang online, đang ở đâu, con trỏ của người khác

Trạng thái: hướng **ĐÃ CHỐT** ở [`PRESENCE-01`](../docs/decisions/presence-01.md) (người dùng, chat 29/10/2026: "cả 1 và 2"). Chi tiết dưới đây là **ĐỀ XUẤT** (Claude, 29/10/2026). Chưa code, chưa có bản xem; frontend chờ duyệt bản xem dữ liệu giả theo [quy trình frontend](../docs/development.md#quy-trình-frontend).

## Vì sao

Từ khi chạy song song có nhiều người mở web cùng lúc. Người dùng muốn giống Google Sheets: biết ai đang mở sổ nào, đang chọn ô nào, và thấy con trỏ chuột của họ di chuyển. Mục đích chính là tránh hai người sửa cùng một chỗ mà không biết.

## Người dùng và luồng (bước 1)

Người nhập và chủ nghiệp vụ, trên 40 tuổi, màn 1280×720 ([UX](../docs/ux-guidelines.md)). Mọi người là người nội bộ vào qua Tailscale ([`V7-ID`](../docs/decisions/v7-id.md)).

| Tình huống | Người dùng thấy gì | Thao tác |
| --- | --- | --- |
| Mở bất kỳ trang nào | Góc trên phải: vòng tròn chữ cái đầu của từng người đang mở web, mỗi người một màu cố định. Rê chuột → "Tên · đang mở sổ <khách>, tháng 9/2026" | 0 |
| Ở Tổng quan / Công nợ theo tháng | Chấm màu cạnh tên khách đang có người mở sổ | 0 |
| Mở sổ khách có người khác cũng mở | Vòng tròn của họ đứng đầu dãy; ô họ đang chọn có **viền màu** của họ và nhãn tên nhỏ (mức 1) | 0 |
| Người kia đang gõ vào một ô | Viền nét đứt + nhãn "Tên đang sửa…" | 0 |
| Người kia di chuột trên bảng sổ | **Mũi tên màu kèm tên** di chuyển theo chuột họ (mức 2) | 0 |
| Muốn tới chỗ người kia | Bấm vòng tròn của họ → cuộn tới ô họ đang chọn, ô nháy viền một lần | 1 |
| Thấy rối mắt | Nút **Ẩn con trỏ người khác** cạnh dãy vòng tròn; nhớ theo trình duyệt. Chỉ ẩn mũi tên chuột, vẫn giữ viền ô và vòng tròn | 1 |
| Bắt đầu sửa ô người khác đang sửa | Nhắc ngay ô: "Tên đang sửa ô này" — **không chặn** | 0 |

Không có khóa ô, không xin quyền sửa. Chống ghi đè vẫn là cơ chế phiên bản sổ hiện có (xem dưới).

## Đầu ra

- **Mức 1 (vị trí):** danh sách người online trên mọi trang V7; trên sổ khách thấy ô người khác đang chọn/sửa, trễ ≤ 1 giây.
- **Mức 2 (con trỏ):** trên bảng của sổ khách, mũi tên chuột người khác di chuyển mượt, trễ ≤ 0,5 giây, đúng ô dù hai máy khác cỡ màn hình, mức zoom hay vị trí cuộn.
- Không có gì được ghi xuống DB hay log; tắt server là mất hết, đúng ý đồ.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Cần | Hiện có | Ghi chú |
| --- | --- | --- |
| Biết ai | `v7_identity.resolve_actor` lấy login Tailscale phía server cho mọi request ([`web/v7_identity.py`](../cong-no-web-handoff/web/v7_identity.py)) | Dùng lại, **không** nhận tên từ client. Chạy dev/demo (`dev_actor`) thì mọi tab cùng một actor → phân biệt bằng mã tab, hiện "Người dùng 1, 2…" |
| Tên hiển thị | Chỉ có login dạng email | ĐỀ XUẤT: lấy phần trước `@`. CÒN MỞ: bảng đổi login → tên ngắn nếu người dùng muốn |
| Server | `ThreadingHTTPServer` stdlib, một tiến trình, mỗi request một luồng, `connection.settimeout(5)` ([`web/v7_ledger_api.py`](../cong-no-web-handoff/web/v7_ledger_api.py)) | Trạng thái giữ trong RAM của tiến trình là đủ. Luồng SSE phải bỏ timeout 5 giây |
| Đẩy về trình duyệt | Chưa có; trang tự làm mới sổ mỗi 60 giây (`so-khach-v7-ui.js`) | Thêm SSE (`text/event-stream`) bằng stdlib. Không dùng WebSocket vì stdlib không có, không thêm dependency |
| Khóa dòng ổn định | Snapshot `get_ledger` có mã chuyến/phiếu/dòng sổ gốc | Con trỏ và ô chọn neo theo **khóa dòng + tên cột**, không theo tọa độ màn hình. CÒN MỞ: kiểm mọi loại dòng hiển thị (dòng điều chỉnh, dòng cộng tháng) đều có khóa; dòng không có khóa thì neo vào dòng gần nhất có khóa |
| Hàng nháp / hàng trống | Chỉ có ở trình duyệt người nhập (`so-khach-v7-draft-ui.js`), chưa lưu | Người khác không thấy các hàng này → gửi vị trí dạng "khu nhập tháng 9/2026"; người xem hiện viền quanh khu nhập của tháng đó, không hiện mũi tên |
| Chống ghi đè | Mọi lệnh ghi gửi `expected_version`; sổ đã đổi thì server trả `STALE_LEDGER`, trang tải lại và báo "Sổ vừa thay đổi…" (`so-khach-v7-api.js`) | **Đã có**, giữ nguyên. Thêm: nếu lúc đó có người khác đang mở sổ thì câu báo kèm tên họ |

## Giao tiếp frontend–backend (bước 5)

Module mới `web/v7_presence.py` (thuần Python, không DB), hai route mới trong `v7_ledger_api.py`. Cả hai qua đúng kiểm Host/danh tính như route hiện có.

**`POST /api/v7/presence`** — trình duyệt báo vị trí của mình.

```json
{"tab": "k3f9…", "page": "so-khach", "customer_id": 12, "month": "2026-09",
 "cell": {"row": "trip:4812", "col": "unit_price", "editing": false},
 "pointer": {"row": "trip:4812", "col": "unit_price", "fx": 420, "fy": 600}}
```

- `tab`: chuỗi ngẫu nhiên tạo một lần mỗi tab. `page` ∈ `dashboard | cong-no-theo-thang | so-khach | sheet-queue`. `cell`, `pointer` có thể `null`. `fx`, `fy` là vị trí trong ô tính theo phần nghìn (số nguyên 0–1000, không dùng số thực).
- Server tự gắn `actor` và giờ nhận; bỏ trường lạ; thân > 2 KB hoặc sai kiểu → 400. Trả `200` kèm danh sách người khác như luồng SSE (`{"people": […]}`), nên nhịp giữ chỗ cũng là đường dự phòng khi mất SSE. Một actor tối đa 20 tab, cả server 200 tab; vượt thì `429`.
- Gửi khi: mở trang; đổi ô chọn / bắt đầu hoặc thôi gõ (ngay, gộp 150 ms); chuột di trên bảng (tối đa 5 lần/giây, chỉ khi có di chuyển); nhịp giữ chỗ mỗi 10 giây; `pagehide` gửi `page: null` qua `sendBeacon`.
- Tab ẩn (`document.hidden`) thì bỏ `pointer`, giữ nhịp 10 giây.

**`GET /api/v7/presence/stream`** — SSE, server đẩy danh sách người khác.

```
event: presence
data: {"people":[{"id":"a1","name":"lan","color":3,"page":"so-khach","customer_id":12,
       "month":"2026-09","cell":{…},"pointer":{…},"age_ms":180}]}
```

- Mỗi lần đẩy là **toàn bộ** danh sách (không gửi phần chênh), nên mất một gói không sao. `id` là mã ổn định theo actor + tab, không lộ login; `name` là tên hiển thị; `color` là chỉ số 0–7 tính từ actor.
- Người mở sổ khách nhận `cell`/`pointer` của người cùng sổ; người ở trang khác chỉ nhận `page`, `customer_id`, `month`.
- Tối đa 10 lần đẩy/giây mỗi luồng (gộp thay đổi). Không có gì mới thì 15 giây gửi một dòng chú thích `: ping` để giữ kết nối.
- Hết hạn: không nghe báo 30 giây thì người đó biến mất; `pointer` cũ hơn 3 giây thì ẩn mũi tên.
- Giới hạn 40 luồng SSE cả server, 6 luồng mỗi actor; vượt thì trả `503`. Trình duyệt mất SSE thì chuyển sang hỏi `GET /api/v7/presence?tab=…` (cùng dữ liệu, JSON) mỗi 2 giây, chỉ còn mức 1, thử nối lại SSE sau 30 giây.
- Luồng SSE là luồng daemon; tắt server không chờ chúng.

**Phía trình duyệt:** một file dùng chung `preview/presence.js` + `presence.css`, nạp bằng thẻ `<script>`/`<link>` trong bốn trang của `PAGES`. Sổ khách cài thêm một phần `SoKhachV7LiveParts.presence` để đọc ô đang chọn, khóa dòng và vẽ lớp phủ (viền ô, mũi tên) bằng một lớp `position:absolute; pointer-events:none` trên bảng. Mũi tên trượt giữa hai vị trí bằng `transition` 200 ms. Không tính tiền ở đây (ARCH-03 không bị đụng).

## Nguồn quyết định

- [`PRESENCE-01`](../docs/decisions/presence-01.md): làm cả mức 1 và mức 2.
- [`V7-ID`](../docs/decisions/v7-id.md): danh tính lấy phía server, không nhận actor từ client.
- [`NHAP-SHEET-01`](../docs/decisions/nhap-sheet-01.md): sửa tại ô, hàng nháp — nơi viền ô và nhắc "đang sửa" hiện.
- CÒN MỞ: tên hiển thị; có cần ai được thấy ai không (hiện tại ai vào app cũng thấy hết mọi người).

## Hành vi và bất biến

- Chỉ là chỉ báo: không khóa, không chặn lưu, không đổi lệnh ghi tiền, không đổi DB/SQL/migration.
- Danh tính lấy từ server; client không tự khai tên hay màu.
- Không lưu vị trí xuống đĩa, không ghi log vị trí (`log_message` vẫn tắt).
- Mất kết nối presence không làm hỏng trang: sổ vẫn đọc/ghi bình thường, chỉ dãy vòng tròn mờ đi kèm chữ "Không thấy được người khác".
- Mình không thấy chính mình; tab thứ hai của cùng người hiện như một người khác có cùng tên và màu.

## Tiêu chí nghiệm thu

- [ ] `tests/test_v7_presence.py`: hết hạn 30 giây/3 giây; gộp theo actor + tab; lọc `cell`/`pointer` theo sổ; bỏ trường lạ, chặn thân lớn; giới hạn luồng SSE trả 503; actor lấy từ server dù thân gửi kèm tên.
- [ ] Test luồng SSE trên server thật cục bộ: hai client, một bên POST, bên kia nhận `event: presence` ≤ 1 giây; ngắt client không giữ luồng quá 15 giây.
- [ ] Test trình duyệt (Playwright, máy chủ giả): hai trang cùng sổ, khác cỡ cửa sổ (1280×720 và 1920×1080) và vị trí cuộn; mũi tên và viền ô của trang A hiện đúng ô ở trang B; tháng đang thu gọn ở B thì hiện ở tiêu đề tháng; nút Ẩn con trỏ nhớ sau tải lại; mất SSE chuyển sang hỏi định kỳ.
- [ ] `npm run check` xanh.
- [ ] Bản xem HTML dữ liệu giả (dãy vòng tròn, viền ô, đang sửa, mũi tên, chấm màu ở Tổng quan) được người dùng duyệt trước khi code frontend.
- [ ] Sau `Deploy hao`: hai người dùng thật mở cùng sổ qua Tailscale thấy nhau. Kiểm riêng là `tailscale serve` chuyển SSE ngay, không gom đệm (CÒN MỞ tới lúc đó).

## Cách chia PR

1. Spec + quyết định (PR này).
2. Backend: `web/v7_presence.py`, hai route, test Python. Không đụng trang. Tự triển khai được (không SQL).
3. Bản xem HTML dữ liệu giả → người dùng duyệt.
4. Frontend mức 1: dãy vòng tròn, chấm ở Tổng quan, viền ô, "đang sửa", câu báo STALE kèm tên.
5. Frontend mức 2: mũi tên chuột, nút Ẩn con trỏ.

## Phạm vi agent

- Agent: claude
- Mockup: CHỜ DUYỆT (bản xem HTML dữ liệu giả, PR 3)
- Review: opus
- Được sửa:
  - `cong-no-web-handoff/web/v7_presence.py`
  - `cong-no-web-handoff/web/v7_ledger_api.py`
  - `cong-no-web-handoff/tests/test_v7_presence.py`
  - `cong-no-web-handoff/preview/presence.js`, `presence.css`, `so-khach-v7-presence-ui.js`, test trình duyệt tương ứng
  - bốn trang HTML trong `PAGES` (chỉ thêm thẻ nạp file)
- Ngân sách diff: backend 300 dòng; mỗi PR frontend 400 dòng
- Lệnh kiểm: `npm run check`
- Cấm: thêm dependency (kể cả thư viện WebSocket); đổi SQL, schema, lệnh ghi tiền; ghi vị trí xuống đĩa/log; nhận danh tính từ client.

## Hoàn tác

Revert PR. Không có dữ liệu để dọn.

## Bằng chứng

Chưa có.

## Câu hỏi mở

- Tên hiển thị: phần trước `@` của login Tailscale, hay một bảng tên ngắn do người dùng đặt?
- Có trang nào không muốn người khác thấy mình đang mở không?
