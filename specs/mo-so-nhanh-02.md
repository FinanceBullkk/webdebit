# Mở Sổ khách nhanh hơn, bước 2: Lịch sử nạp khi mở khung, bỏ ô Sheet thô khỏi bản đọc mặc định (MO-SO-NHANH-02)

Trạng thái: ĐÃ CHỐT (người dùng, 4/11/2026, "Chốt theo đề xuất": phương án A, bỏ `display.cells`, chấp nhận giảm 2,5 lần, khung đang mở không tự tải; phạm vi thân JSON của `GET /api/v7/ledger`, khung Lịch sử của trang Sổ khách, không đổi luật tiền, kết quả `get_ledger` giữ nguyên). ĐÃ TRIỂN KHAI trên `hao` 4/11/2026, bản `943d8f2`, [nhật ký](../docs/deploys/2026-11-04-ledger-events.md).

Tiếp [MO-SO-NHANH-01](mo-so-nhanh-01.md) (ETag/304, gzip, đọc sổ song song với tải JS; lên `hao` 4/11/2026, bản `473bb0a`). Bước 1 không đổi thời gian server của GET sổ; bước này giảm kích thước thân GET và việc trình duyệt phải nhận, giải nén, phân tích mỗi 60 giây.

## Người dùng và luồng

Người nhập mở Sổ khách, đợi bảng hiện, làm việc trên bảng. Khung **Lịch sử** (nút trong menu ⋯ ở đầu trang) chỉ mở khi cần soát ai sửa gì; phần lớn phiên không mở. Trang tự tải lại sổ mỗi 60 giây khi không bận (khung Lịch sử đang mở cũng tính là bận, không tự tải).

Hôm nay mỗi lần GET sổ mang theo toàn bộ Lịch sử (`events`, mọi thao tác kèm trước → sau) và với mỗi dòng sổ gốc cả 27 ô Sheet thô (`display.cells`, A…AA, phần lớn rỗng) mà không màn nào đọc.

Luồng sau khi làm:

1. Mở sổ: GET như cũ nhưng thân không có `events`, dòng sổ gốc không có `display.cells`. Bảng, chip tháng, phiếu thu, hàng chờ Sheet hiện y như trước.
2. Bấm **Lịch sử**: khung mở ngay với dòng "Đang tải lịch sử…", trang gọi `GET /api/v7/ledger/events?customer=`; về thì thay bằng danh sách và bộ lọc đúng như hôm nay (SO-GON-04 L6). Đóng rồi mở lại khi sổ chưa đổi (`version` không đổi) thì không gọi lại.
3. Đang mở khung mà làm một lệnh (ghi phiếu, sửa ô…): sổ đọc lại như cũ; `version` đổi nên khung nạp lại Lịch sử, giữ bộ lọc đang chọn.
4. Lỗi khi nạp Lịch sử: trong khung hiện "Không tải được lịch sử." và nút **Thử lại**; sổ bên ngoài không bị ảnh hưởng.
5. Bản fixture (`customer-ledger-workbench.html`) giữ Lịch sử tự ghi trong trang như nay, không gọi API.

Đo trên `hao` 4/11/2026 (bản `473bb0a`), từ trình duyệt máy làm việc qua Tailscale và từ chính `hao` (SQL, Python):

| Sổ | Thân JSON | gzip trên dây | `events` | `legacy_rows` (trong đó `current` / `display` / riêng `display.cells`) | GET từ trình duyệt | SQL `get_ledger` | Chiếu Sheet/PS (`ledger_projections`) | Python `loads`+`dumps`+gzip |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 176 (thường) | 54 KB | 8 KB | 23,5 KB (37 sự kiện) | 23,8 KB (6,5 / 13,0 / 7,3) | 218–249 ms | 92 ms | 82 ms | ~9 ms |
| 14 (bước 1 gọi là lớn nhất) | 401 KB | 33 KB | 189 KB (186 sự kiện, 170 là máy điền shipper) | 205 KB (62 / 105 / 49) | 384–468 ms | 155–230 ms | 124–195 ms | ~35 ms |
| 79 (lớn nhất thật) | 1.397 KB | 92 KB | 649 KB (658 sự kiện) | 638 KB | 1.864–1.903 ms | 1.060–1.230 ms | 560–580 ms | ~90 ms |

Cả 238 sổ: 21,1 MB thân JSON, trong đó `events` 8,3 MB (39%), `legacy_rows` 11,8 MB (56%); trung vị một sổ 19 KB. Mười sổ trên 600 KB, năm sổ trên 1 MB (id 79, 155, 104, 80, 235), GET 1,1–3,3 giây.

Riêng trong SQL (đo tách từ thân `get_ledger` đang chạy, giao dịch chỉ đọc): phần dựng `events` chỉ 9,5 ms (sổ 14) và 33 ms (sổ 79); phần dựng `legacy_rows` 101 ms và 342 ms. Tức là **Lịch sử nặng về kích thước, không nặng về thời gian SQL**; thời gian của sổ lớn nằm ở phần còn lại của `get_ledger` (dòng sổ gốc, chuyến) và ở chiếu Sheet — việc của bước 3, không thuộc bước này.

## Đầu ra

- `GET /api/v7/ledger`: thân không có `events`; mỗi `legacy_rows[*].display` không có `cells`. Mọi khóa khác giữ nguyên. Dự kiến: sổ 14 từ 401 KB còn 163 KB (gzip 24 → 16 KB), sổ 79 từ 1.397 KB còn 607 KB, sổ 176 từ 54 KB còn 23 KB; mỗi 60 giây tự tải lại cũng nhẹ đi từng ấy. GET không chậm hơn: server bớt ~20 ms (sổ 14) đến ~55 ms (sổ 79) việc `json`/gzip, trình duyệt bớt việc phân tích; phần SQL giữ nguyên vì `get_ledger` không đổi.
- `GET /api/v7/ledger/events?customer=<id>` mới: `{ "customer_id", "version", "events": [ … như hôm nay, có "actor_name" ] }`. Chỉ gọi khi khung Lịch sử mở hoặc khi `version` đổi lúc khung đang mở.
- Khung Lịch sử hiện đủ và đúng như trước (cùng câu, cùng bộ lọc, cùng thứ tự mới nhất trước); chỉ thêm trạng thái "Đang tải lịch sử…" và lỗi có Thử lại.

## Đối chiếu dữ liệu và code hiện có

**Ai đọc `events` của một sổ** (nguồn: `grep` 4/11/2026):

| Nơi | Đọc gì | Lấy `events` từ đâu | Ảnh hưởng |
| --- | --- | --- | --- |
| `web/v7_api_sheet.py` `sheet_projection` (dòng 269) | `sheet_conflict_resolved` có `after.field = task_assignment` → chuyến Sheet đã gán | `ledger` truyền vào `ledger_projections` (kết quả `get_ledger`) | Không đổi: server bỏ `events` khỏi thân **sau** khi chiếu xong |
| `web/v7_api_sheet.py` `keep_sheet_task` (688), `assign_sheet_trip` (741) | khóa idempotency theo `request_key` | tự gọi `get_ledger` trong POST | Không đổi |
| `web/v7_ledger_api.py` `with_actor_names` | gắn `actor_name` theo bảng tên PRESENCE-01 | kết quả GET | Chuyển sang gắn cho thân của route events |
| `web/v7_inbox.py` (161, 183), `web/v7_sheet_queue.py` (217, 329), `web/v7_sheet_task_keep.py` (20), `tools/v7_reconcile_auto.py`, `tools/v7_fill_fee_gap.py` | tháng máy mở, việc máy làm, hàng chờ, gán việc | `runner.run("get_ledger")` trực tiếp | Không đổi |
| `preview/viec-can-lam.js`, `tools/v7_price_match.py`, `tools/v7_reconcile_sheet.py`, `tools/rehearse_v7_deploy.py` | đọc sổ qua HTTP nhưng không đọc `events` hay `display.cells` (kiểm bằng `grep` khi code) | `GET /api/v7/ledger` | Không đổi |
| UI `so-khach-v7-history-ui.js` `historyList(events)` | vẽ khung Lịch sử | `renderSnapshot` của `so-khach-v7-ui.js` dòng 418: `historyList(data.events ?? [])` | **Đổi**: nạp riêng theo `historyOpen` và `version` |
| UI `so-khach-v7-edit-ui.js` | không đọc `events`; chỉ bật/tắt `ctx.historyOpen` rồi `redraw()` (dòng 145–149) | — | Không đổi |
| UI `so-khach-v7-sheet-ui.js`, `-model.js`, các phần khác | không đọc `events` (đọc `snapshot.sheet_sync`, `sheet_prices`, `version`) | — | Không đổi |
| Test | `preview/test-so-khach-v7-api.js` (8 ca truyền `events` trong thân sổ), `test-so-khach-v7-keys-browser.js` 143–190, `test-so-khach-v7-edit-browser.js` 104, 190, 280–296, `test-so-khach-v7-offset-browser.js` 100, `tests/test_v7_ledger_api.py::test_ledger_history_names_actor_by_short_name_not_login` | mở khung, đọc chữ trong `#history-panel` | xem Tiêu chí nghiệm thu |

**Ai đọc `legacy_rows[*]`** (dòng sổ gốc, mỗi dòng có `display` = cột Sheet đã đọc lúc nạp và `current` = bản đang dùng khi dòng sửa được):

| Khóa | Ai đọc | Kết luận |
| --- | --- | --- |
| `current.{container, carrier, shipper, origin, destination, event_date, unit_price_vnd, counted_vnd, deleted}` | `so-khach-v7-trips-ui.js` (hàng chuyến sổ gốc, ô sửa được), `-model.js` 617–619 và 808–816 (bảng tháng), `-month-ui.js` 185, `-overview-ui.js` 135–138, `-ui.js` 402 (cột Shipper), `-edit-ui.js` 36, `-fee-ui.js` 64, `-history-ui.js` 55; server `v7_sheet_queue.py` 207, 393 | **Giữ**: đây là dữ liệu bảng đang vẽ, không phải phần "nặng" bỏ được. `current` chỉ 15% thân sổ 14 (62 KB). |
| `display.{row, stt, container, carrier, shipper, date, raw_date, from, to, unit_price, flags}` | `trips-ui` (dòng "Theo sổ gốc", ngày chữ của Sheet), `month-ui` 101–104 và 176 (ghép chuyến–khoản thu theo `row`), `model` 619, 810, `edit-ui` 128; server `v7_sheet_queue.py`, `v7_receipt_queue.py` 104 (`raw_date`) | Giữ |
| `display.cells` (27 ô A…AA của dòng Sheet, 3.486/5.132 ô rỗng ở sổ 14) | **Không ai** trong `web/` hay `preview/`. Chỉ `tools/v7_fill_fee_gap.py` 67 và loader, đọc qua `runner.run("get_ledger")`, không qua HTTP | **Bỏ khỏi thân GET**: 49 KB ở sổ 14, 7 KB ở sổ 176 |
| `display.{tab, note, fee_vnd, source_kind, source_flags}`, `current.{customer_id, legacy_row_id, debt_month, created_by_event, id}` | Không ai ở UI; server đọc qua runner | ~37 KB ở sổ 14; **không bỏ trong bước này** (câu hỏi 3) |
| `fee_lines` | `trips-ui`, `fee-ui`, `model`, `history-ui` | Giữ (chỉ 2 KB ở sổ 14) |

Phần `legacy_rows` còn lại sau khi bỏ `cells` là bảng người dùng đang nhìn; không có khóa nào vừa nặng vừa không đọc.

## Giao tiếp frontend–backend

**`GET /api/v7/ledger?customer=<id>`** (đổi thân, không đổi tham số, mã lỗi, ETag/gzip của bước 1):

- Server: `handle()` trong `web/v7_ledger_api.py` vẫn gọi `get_ledger` rồi `ledger_projections(runner, result, actor)` với đủ `events` (chiếu Sheet cần), **sau đó** mới cắt: `result.pop("events")` và `display.pop("cells")` từng dòng sổ gốc; không còn `with_actor_names` ở đây. Hàm cắt là một hàm thuần `public_ledger(ledger) -> dict` để test riêng.
- `so-khach-v7-prefetch.js`, `create().read()` trong `so-khach-v7-api.js` giữ nguyên.

**`GET /api/v7/ledger/events?customer=<id>`** (mới):

- Tham số như `/api/v7/ledger` (`_by_customer` trong `web/v7_api_validate.py`); sai thì 422 `INVALID_REQUEST` (`bad()`), đường lạ 404 `NOT_FOUND` như mọi GET.
- Thân 200: `{"customer_id": 14, "version": 123, "events": [...]}`; mỗi sự kiện đúng các khóa `get_ledger` đang trả (`id, kind, actor, label, counterparty_customer_id, counterparty_name, at, before, after`) cộng `actor_name` (chuyển `with_actor_names` sang đây). Sổ chưa có số dư đầu (`status = NO_BASELINE`) trả `events: []`, `version` như `get_ledger` trả.
- `Cache-Control: no-store`, gzip khi ≥ 1 KB (đã có từ bước 1). Không gắn `demo`/`real_copy` (không phải màn hình riêng).
- Nguồn dữ liệu, **hai phương án** (câu hỏi 1):
  - **A — hàm SQL riêng (đề xuất):** `sokhach.get_ledger_events(customer_id bigint) RETURNS jsonb`, `SECURITY DEFINER`, cùng kiểm `sokhach.actor` và quyền như `get_ledger`, trả `{customer_id, version, events}`; biểu thức dựng `events` tách thành `sokhach._ledger_events(customer_id)` và `get_ledger` gọi lại hàm này (kết quả `get_ledger` **giống hệt byte** — kiểm bằng băm JSON cả 238 sổ trước/sau trên bản sao, như đợt #317). Thêm `"get_ledger_events"` vào `SQL` của `web/v7_api_tables.py` và `GET_ROUTES`. Chi phí mở Lịch sử: 10–33 ms SQL + một lần psql (~50 ms) ≈ 100 ms. Là thay đổi SQL: một migration `tools/migrations/2026-11-04-v7-ledger-events.sql` (chỉ thêm hàm và thay thân `get_ledger` bằng lời gọi, không đổi bảng/cột/dữ liệu/quyền ngoài `GRANT EXECUTE` cho app), cập nhật `specs/v7-backend/schema-draft.sql` và `tools/v7_backend_functions.sql`, chạy harness PostgreSQL ở máy, tự triển khai theo [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md) (backup, `ON_ERROR_STOP`, `v7_post_deploy_check.sql`, đối soát tổng khách, nhật ký `docs/deploys/`). Thứ tự: DB trước (bản app cũ vẫn chạy vì `get_ledger` không đổi kết quả), rồi release.
  - **B — không đổi SQL:** route gọi lại `get_ledger` và chỉ trả `{customer_id, version, events}`. Không migration, không harness. Nhược: mở Lịch sử ở sổ lớn tốn cả một lần `get_ledger` (sổ 79: ~1,2 giây SQL, hôm nay mở là có ngay), và mỗi lần `version` đổi khi khung đang mở lại thêm một lần đọc cả sổ.

**Hợp đồng ctx (`so-khach-v7-ctx.js`)** — đổi ba dòng FIELDS, không thêm phần:

- `api`: thêm `history` vào người đọc (gọi `ctx.api.readEvents()`).
- `historyOpen`: thêm `history` vào người đọc (chỉ nạp khi khung mở).
- `historyList`: ý nghĩa "danh sách trong khung Lịch sử từ bản GET đang vẽ; không có `events` trong bản GET thì nạp qua `api.readEvents()` theo `version`, vẽ trạng thái chờ/lỗi trong khung". Chữ ký đổi từ `historyList(events)` sang `historyList(snapshot)`; `so-khach-v7-ui.js` dòng 418 gọi `historyList(data)`.
- `test-so-khach-v7-ctx.js` tự đối chiếu nên khai thiếu là đỏ.

**`so-khach-v7-api.js`**: thêm `readEvents()` trong `create()`: GET `/api/v7/ledger/events?customer=` với `cache: 'no-store'`, trả thân đã kiểm `customer_id` khớp và `version` là số nguyên an toàn (như `read()`), lỗi thì ném để phần history hiện câu lỗi. Không ghi vào `snapshot`, không ảnh hưởng `hasPending()`.

**`so-khach-v7-history-ui.js`**: giữ bộ nhớ `{ version, events }`; `historyList(snapshot)`: nếu `Array.isArray(snapshot.events)` (fixture, server cũ) dùng thẳng như nay; nếu không và khung đóng trả khung rỗng; nếu khung mở và `version` khớp bộ nhớ thì vẽ từ bộ nhớ; khác thì vẽ "Đang tải lịch sử…" và gọi `api.readEvents()`, về thì **thay nội dung trong `#history-panel` tại chỗ** (không vẽ lại cả sổ, giữ tiêu điểm và bộ lọc). Lỗi: câu lỗi + nút Thử lại trong khung. Hai lần gọi chồng nhau (mở/đóng nhanh) chỉ nhận kết quả mới nhất.

## Nguồn quyết định

- Không đụng quyết định nghiệp vụ nào trong [`docs/decisions.md`](../docs/decisions.md); Lịch sử vẫn ghi người làm, trước → sau (V6/V7-SO/V7-CSM), chỉ đổi lúc nào trình duyệt tải nó.
- Phương án A đi theo [`DEPLOY-CLAUDE-01`](../docs/decisions/deploy-claude-01.md) (Claude tự merge và tự triển khai SQL khi đủ điều kiện).
- Bước 3 (thời gian SQL `get_ledger` sổ lớn và chiếu Sheet; cache theo `version`) CÒN MỞ, không thuộc spec này.

## Hành vi và bất biến

- Không cache JSON ở trình duyệt; số dư luôn đọc từ server (như bước 1). Bộ nhớ Lịch sử trong trang gắn với `version` của bản GET đang vẽ; `version` đổi là nạp lại.
- `get_ledger` (SQL) trả y nguyên như hôm nay cho mọi nơi gọi qua runner (hộp thư máy, hàng chờ Sheet, đối soát, công cụ): bỏ `events`/`cells` chỉ ở tầng HTTP của `GET /api/v7/ledger`.
- Chiếu Sheet (`sheet_projection`) vẫn nhận đủ `events` (chuyến Sheet đã gán không hiện lại).
- Thân mới là tập con của thân cũ: không khóa nào đổi tên hay đổi kiểu. Trang JS cũ gặp server mới chỉ thấy Lịch sử trống cho tới lần tải trang kế (ETag `no-cache` của bước 1 lấy JS mới ngay sau deploy); trang JS mới gặp server cũ vẫn dùng `events` trong thân.
- Khung Lịch sử mở vẫn chặn tự tải 60 giây (`BUSY_OPEN` giữ nguyên).
- Không đổi luật tiền, không ghi tiền, không chạm dữ liệu.

## Tiêu chí nghiệm thu

- [x] `tests/test_v7_ledger_api.py`: GET `/api/v7/ledger` không có `events`, không có `display.cells`, các khóa khác bằng kết quả trước khi cắt; `ledger_projections` nhận bản còn đủ `events` (patch và soi tham số); `public_ledger` không sửa dict vào (tránh đụng bộ nhớ dùng chung). GET `/api/v7/ledger/events`: 200 đúng thân, `actor_name` theo bảng tên (chuyển ca `test_ledger_history_names_actor_by_short_name_not_login`), 422 khi thiếu/sai `customer`, không gắn `demo`/`real_copy`. GET sổ không thêm lần gọi psql nào (thân và `ledger_projections` không đổi đường đọc; `test_v7_ledger_read_cost.py` giữ xanh).
- [x] Phương án A: `tools/test_pg_v7_backend.py` (và `--migration-test`) xanh ở máy; ca mới: `get_ledger_events` trả đúng `events` của `get_ledger` cùng `version`, sổ `NO_BASELINE` trả `[]`, reader không gọi được; `get_ledger` trước/sau migration giống hệt trên fixture harness.
- [x] `preview/test-so-khach-v7-api.js`: `readEvents()` gọi đúng đường, từ chối thân sai khách; trang không có `events` trong thân: mở khung → gọi events một lần, đóng/mở lại không gọi thêm, `version` đổi thì gọi lại, lỗi thì có Thử lại; các ca đang truyền `events` trong thân vẫn xanh (đường fixture/server cũ).
- [x] `preview/test-so-khach-v7-ctx.js` xanh với ba dòng FIELDS mới.
- [x] Test trình duyệt: `so-khach-v7-browser-world.js` bỏ `events` khỏi thân GET sổ và thêm route `GET /api/v7/ledger/events` trả `world.events`; các ca ở `keys-browser` (bộ lọc, đếm, thêm sự kiện rồi làm mới), `edit-browser`, `offset-browser` đọc `#history-panel` **sau khi** danh sách về (chờ `.history-items`), không đọc ngay sau click; tải lại trang bằng `reload(page)` của world. Thêm ca: mở sổ không gọi route events; mở khung thì gọi; đóng/mở lại không gọi; sau một lệnh khi khung mở thì gọi lại.
- [x] `npm run check` xanh; `.venv/Scripts/python.exe -m ruff check .` sạch; `node scripts/check-secrets.js` sạch.
- [x] Trên `hao` sau deploy: đo lại sổ 14, 176, 79 bằng `performance.getEntriesByType('resource')`: thân GET sổ 14 ≤ 165 KB, GET không chậm hơn bảng trên; mở Lịch sử sổ 79 ≤ 300 ms (A) và danh sách khớp số sự kiện; ghi số vào PR.
- [ ] Người dùng tự mở Lịch sử trên `hao` ở một sổ lớn, lọc, làm một lệnh rồi thấy dòng mới trong khung.

## Phạm vi agent

- Agent: claude
- Review: sonnet medium (không đụng phân bổ, opening, quyền ghi tiền); nếu phương án A thì phần SQL review opus
- Được sửa:
  - `cong-no-web-handoff/web/v7_ledger_api.py`
  - `cong-no-web-handoff/web/v7_api_validate.py`, `cong-no-web-handoff/web/v7_api_tables.py`, `cong-no-web-handoff/web/v7_psql.py` (câu lỗi khi hết giờ đọc)
  - `cong-no-web-handoff/preview/so-khach-v7-api.js`, `so-khach-v7-history-ui.js`, `so-khach-v7-ui.js` (một dòng gọi `historyList`), `so-khach-v7-ctx.js`, `so-khach-v7-browser-world.js`, `so-khach-v7.css` (nút Thử lại)
  - `cong-no-web-handoff/tests/test_v7_ledger_api.py`
  - `cong-no-web-handoff/preview/test-so-khach-v7-api.js`, `test-so-khach-v7-keys-browser.js`, `test-so-khach-v7-edit-browser.js` (`offset-browser` có máy chủ giả riêng trả `events` trong thân, giữ làm ca đường server cũ)
  - Phương án A thêm: `cong-no-web-handoff/tools/migrations/2026-11-04-v7-ledger-events.sql` và `.rollback.sql`, `specs/v7-backend/schema-draft.sql`, `specs/v7-backend/ket-noi-giao-dien.md`, `cong-no-web-handoff/tools/v7_backend_functions.sql`, `cong-no-web-handoff/tools/v7_post_deploy_check.sql`, `cong-no-web-handoff/tools/test_pg_v7_backend.py`, `test_pg_v7_backend_ledger_events.py`, `test_pg_v7_backend_schema.py`, `test_pg_v7_backend_locks.py`, `test_pg_v7_backend_price.py` (chuỗi migration), `cong-no-web-handoff/tests/test_v7_fee_sql_sync.py`, `docs/v7-deploy-runbook.md`, `docs/deploys/2026-11-04-ledger-events.md`
- Ngân sách diff: 450 dòng (A), 300 dòng (B); không tính phần migration chép lại nguyên thân `get_ledger` và rollback (khoảng 420 dòng), do sync test bắt buộc
- Lệnh kiểm: `npm run check`; phương án A thêm `tools/test_pg_v7_backend.py` ở máy
- Cấm: đổi `current`/`display` ngoài `cells`; đổi luật tiền; đổi thân `get_ledger` ngoài việc gọi `_ledger_events` (A); thêm dependency.

## Hoàn tác

Revert PR. Phương án A: release cũ chạy được với DB đã có hàm mới (hàm thừa không ai gọi); gỡ hàm bằng `DROP FUNCTION` theo mục rollback của runbook nếu muốn sạch. Không đụng dữ liệu.

## Bằng chứng

- 4/11/2026, `hao` bản `473bb0a`: số đo ở bảng trên. Trình duyệt: 5 lần GET mỗi sổ qua `fetch` + `performance.getEntriesByType('resource')` (`encodedBodySize`, `decodedBodySize`, `responseStart`); cả 238 sổ quét một lượt 3 luồng song song. Server: script chỉ đọc chạy bằng `sudo -u v7app python3 -B -I -` với `SET LOCAL transaction_read_only=on` (đo `get_ledger`, `ledger_projections`, `json.dumps/loads`, `gzip.compress`, kích thước thân sau khi bỏ `events` + `cells`); phần SQL tách riêng chạy trong giao dịch chỉ đọc bằng `psql` với `\timing`. Không ghi gì, không chép dữ liệu khách ra ngoài `hao`.

- 4/11/2026, sau triển khai `943d8f2`: thân sổ 14 163,3 KB, GET 408–458 ms; sổ 79 607 KB, 1.854–1.889 ms; sổ 176 23,2 KB, 216–236 ms; mở Lịch sử sổ 79 225 ms, 658 dòng. Chi tiết ở [nhật ký](../docs/deploys/2026-11-04-ledger-events.md). Tích kiểm: harness máy 78 đạt, 2 bỏ qua; `npm run check` xanh trừ ruff báo giả trong worktree, chạy riêng sạch; CI 14/14. Mục người dùng tự thử còn mở.

## Câu hỏi đã chốt (người dùng, 4/11/2026: theo cả bốn đề xuất)

1. **Nguồn cho route Lịch sử:** A — thêm hàm SQL `get_ledger_events` (một migration nhỏ, Claude tự triển khai theo DEPLOY-CLAUDE-01, mở Lịch sử ~100 ms kể cả sổ lớn) hay B — không đổi SQL, route gọi lại cả `get_ledger` (mở Lịch sử sổ 79 mất ~1,2 giây, sổ thường ~0,1–0,2 giây)? **Đề xuất A.**
2. **Bỏ `display.cells` khỏi thân GET sổ** (27 ô Sheet thô mỗi dòng sổ gốc, không màn nào đọc; công cụ vẫn đọc qua runner): đồng ý? **Đề xuất có.**
3. **Mục tiêu "giảm ít nhất 3 lần" cho sổ 14:** bỏ `events` + `cells` được 401 → 163 KB (2,5 lần; sổ 79: 2,3 lần). Để đạt 3 lần phải bỏ thêm các trường UI không đọc trong `display`/`current` (ước còn ~126 KB, 3,2 lần) nhưng hợp đồng dòng sổ gốc đổi rộng hơn và lợi ích nhỏ (gzip chỉ bớt thêm ~2 KB). Chấp nhận 2,5 lần và giữ hợp đồng dòng sổ gốc, hay làm thêm? **Đề xuất chấp nhận 2,5 lần.**
4. Khung Lịch sử đang mở vẫn **không tự tải 60 giây** như hôm nay (tránh danh sách nhảy khi đang đọc); giữ vậy? **Đề xuất giữ.**
