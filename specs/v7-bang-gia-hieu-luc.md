# V7: bảng giá theo ngày hiệu lực

Trạng thái: chính sách **ĐÃ CHỐT** ở [`BANG-GIA-01`](../docs/decisions.md#bang-gia-01) (người dùng trả lời Q1–Q6 trong chat 29/10/2026, xem [Câu đã chốt](#câu-đã-chốt-2910)). Thiết kế màn hình và backend là **ĐỀ XUẤT** (Claude, 29/10/2026). Claude làm cả backend và giao diện theo [`CLAUDE-ALL-01`](../docs/decisions.md#claude-all-01); không cần mockup Penpot. Chưa code, chưa đổi schema.

## Vì sao làm

Trên Sheet, vài khách có **bảng báo giá** đặt cạnh sổ tháng (tab khách, vùng cột bên phải). Mỗi dòng bảng giá: hiệu lực từ, hiệu lực đến (trống = còn hiệu lực), kho đi, **giá khách**, **giá TT**; kèm danh sách shipper của TT (shipper trong danh sách lấy giá TT, còn lại lấy giá khách). Cột UNIT PRICE của từng chuyến là công thức tra bảng đó theo shipper, ngày và kho đi; không có dòng khớp thì ra "CHƯA CÓ GIÁ".

Web hiện không có bảng giá: đơn giá nhập tay, dán, hoặc ghi từ Sheet qua [`v7-price-queue.md`](v7-price-queue.md). Sau ngày chuyển hẳn (`SONG-SONG-01`) không còn Sheet tính giá hộ, nên web phải tự tra được. Trong lúc chạy song song, bảng giá trên web còn dùng để **kiểm chéo** giá Sheet.

Công thức Sheet hiện có mấy chỗ dễ sai, web phải tránh (đọc công thức 29/10/2026, chưa kiểm trên toàn bộ tab):

| Chỗ dễ sai trên Sheet | Web làm thế nào |
| --- | --- |
| Shipper so khớp tuyệt đối. Viết khác một chữ ("… PHAT" so với không có "PHAT") thì **lặng lẽ** lấy giá khách thay vì giá TT | Vẫn theo quy tắc chốt (không thuộc TT thì giá khách), nhưng tên shipper chuẩn hóa khoảng trắng/hoa thường, ô giá ghi rõ "giá TT"/"giá khách", và màn Bảng giá liệt kê shipper trong sổ đang lấy giá khách để soát tên viết lệch |
| Ô ngày là ngày thật (không phải chữ) có thể bị đảo ngày/tháng khi đọc lại | Dùng `event_date` kiểu `date` của chuyến, không đọc lại chuỗi |
| Kho chỉ có giá TT, trống giá khách: chuyến shipper khác ra ô trống/0 | Thiếu giá là NULL, cờ thiếu giá như hiện nay |
| Hai dòng chồng ngày: dòng trên thắng, không báo | Chặn lưu khi chồng ngày |
| Vùng tra cố định theo số dòng; thêm dòng ngoài vùng bị bỏ | Bảng giá là dữ liệu riêng, không giới hạn số dòng |
| Sửa bảng giá là tính lại giá mọi chuyến cũ | Giá đã ghi vào chuyến giữ nguyên; sửa bảng chỉ tạo đề xuất áp lại |

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720, [UX](../docs/ux-guidelines.md)); người sửa bảng giá: mọi người vào được app (Q1). Theo `V7-ID`, mọi lần ghi mang tên người bấm.

**Bối cảnh:** chỉ vài khách có bảng giá; mỗi bảng khoảng 10–30 dòng; giá đổi theo đợt (ví dụ đợt mới hiệu lực từ ngày 10), đợt cũ được đóng bằng ngày "hiệu lực đến". Bảng giá hiện nằm trên Sheet nên cách nhập quen thuộc nhất là **dán**.

| Việc | Thao tác | Số thao tác |
| --- | --- | --- |
| Mở bảng giá của sổ | Đầu sổ khách → **Bảng giá** | 1 |
| Nạp bảng giá lần đầu | Copy vùng bảng giá trên Sheet → dán vào bảng giá web → xem trước → **Lưu** | 3 |
| Thêm đợt giá mới | **Thêm đợt giá** → gõ "hiệu lực từ" → dán hoặc gõ giá từng kho → **Lưu**. Web hỏi "Đóng đợt cũ ngày …?" (ngày trước ngày mới một ngày) | 4 |
| Khai shipper của TT | Bảng giá → khu **Shipper áp giá TT** → thêm tên. Ngay dưới có danh sách "Shipper trong sổ đang lấy giá khách" để soát tên viết lệch | 2 |
| Nhập/dán chuyến | Như [`v7-nhap-kieu-sheet.md`](v7-nhap-kieu-sheet.md). Ô Đơn giá trống thì web **tự điền giá theo bảng**, chữ nghiêng kèm nhãn "theo bảng" cho đến khi Lưu | 0 thêm |
| Áp giá cho chuyến đã có mà chưa có giá | Đầu sổ: "**Áp giá theo bảng cho N chuyến**" → khung xác nhận dưới đầu sổ (số chuyến, tổng tăng, tháng bị ảnh hưởng) → **Ghi** | 2 |
| Thấy chuyến lệch bảng giá | Ô Đơn giá tô màu kèm chữ "khác bảng giá: 85.000.000"; bấm thì thấy dòng bảng giá đã tra | 1 |
| Sửa bảng giá sau khi đã ghi chuyến | Lưu bảng giá → web báo "N chuyến đã ghi theo giá cũ" → **Áp lại giá mới cho N chuyến** hoặc **Giữ giá đã ghi** | 2 |

**Kết quả:** chuyến của khách có bảng giá được điền đúng giá theo kho, ngày xe nhập kho và nhóm shipper, không phải gõ lại; mọi chỗ không chắc chắn để trống và hiện lý do.

**Bị chặn hoặc không điền (hiện bằng chữ, không chỉ màu):**

| Trường hợp | Hiện | Hành động |
| --- | --- | --- |
| Sổ không có bảng giá | Không hiện gì mới | Như hiện nay |
| Chuyến thiếu ngày hoặc thiếu kho đi | "Thiếu ngày/kho đi để tra giá" | Điền ngày/kho, web tra lại |
| Kho đi không có trong bảng giá (kể cả tên khác chưa gắn) | "Kho chưa có trong bảng giá" | Thêm kho, hoặc gắn tên khác cho kho có sẵn (ví dụ "DAKLAK" → "DAK LAK") |
| Không có đợt giá phủ ngày xe nhập kho | "Ngày … chưa có giá" | Thêm/sửa đợt giá |
| Đợt giá có kho đó nhưng ô giá của nhóm cần dùng trống | "Kho … chưa có giá nhóm …" | Điền giá nhóm |
| Chuyến đang CHỜ KIỂM | Không áp | Kết luận CHỜ KIỂM trước |
| Tháng khóa | "Tháng … đang khóa" | Mở khóa (ổ khóa có sẵn) rồi áp; dán chuyến mới vào tháng khóa vẫn được theo `NHAP-SHEET-01` (7) |
| Lưu bảng giá có hai đợt chồng ngày cùng kho | Lỗi tại dòng: "Trùng ngày với đợt từ … đến …" | Sửa ngày |
| Giá không đọc được, âm hoặc không phải số nguyên | Lỗi tại ô | Sửa số |

## Đầu ra

- Mỗi sổ khách có thể có **một bảng giá**: các đợt giá (hiệu lực từ, hiệu lực đến), mỗi đợt nhiều dòng kho đi × nhóm giá; danh sách shipper theo nhóm; tên khác của kho.
- Khi nhập/dán chuyến, đơn giá trống được điền theo bảng; đơn giá người nhập gõ hoặc dán luôn thắng.
- Chuyến ghi giá theo bảng lưu kèm **nguồn** (dòng bảng giá đã dùng); sửa bảng giá không đổi chuyến đã ghi, chỉ tạo đề xuất áp lại.
- Sổ khách hiện cờ "khác bảng giá" khi đơn giá đang ghi khác giá tra được; cờ chỉ tô màu, không chặn (như các cờ V7-BE).
- Lịch sử ghi mọi thay đổi bảng giá (trước → sau, người làm) và mọi lần áp giá ("Nguồn: bảng giá, đợt từ …").
- Trong lúc chạy song song: hàng chờ giá từ Sheet ([`v7-price-queue.md`](v7-price-queue.md)) hiện thêm giá theo bảng khi khác giá Sheet, để bắt lỗi shipper/ngày trên Sheet.

## Đối chiếu dữ liệu và code hiện có (bước 2)

| Phần | Hiện có | Dùng được / thiếu |
| --- | --- | --- |
| Chuyến | `sokhach.trip`: `customer_id` (= sổ), `event_date` (ngày xe nhập kho, `DATE`), `origin`, `destination`, `shipper` (từ 24/10), `status` | Đủ khóa tra: sổ, kho đi, ngày, shipper. `origin` là chữ tự do (cùng kho nhiều cách viết, có khi kèm chữ Trung), cần chuẩn hóa |
| Giá chuyến | `trip_price_rev(unit_price_vnd, other_fee_vnd)`, ghi qua `paste_trips`, `edit_trip_price`, `adjust_trip` | Thiếu trường nguồn giá (đâu là giá theo bảng) |
| Dòng sổ gốc | `legacy_row` + `_legacy_current`, sửa qua `edit_legacy_trip` | Ngoài phạm vi áp tự động (Q5) |
| Tính tiền | `v_trip_current`, `so-khach-v7-model.js` (`tripAmount`) | Không đổi: bảng giá chỉ sinh đơn giá, tiền vẫn tính như cũ |
| Phụ phí | `PHU-PHI-01`, dòng phụ phí theo loại | Ngoài phạm vi: bảng giá chỉ cho đơn giá |
| Ghi giá từ Sheet | `v7_price_queue.py`, `POST /api/v7/sheet/prices` | Thêm so với giá theo bảng (giai đoạn 2) |
| Nhập kiểu Sheet | `so-khach-v7-draft-ui.js` (nhãn cột có `shipper`, `from`, `price`) | Thêm tự điền ô Đơn giá và nhãn "theo bảng" |
| Bảng giá trên Sheet | Vùng cột phải của tab khách, nằm ngang khối tháng; vị trí khác nhau giữa các tab | Không dựng bộ đọc tự động vị trí; người nhập dán vùng đó (luồng "Nạp bảng giá") |

Dữ liệu mockup: dùng tên kho thật (tỉnh), giá và tên shipper **giả**. Không đưa tên khách, tên shipper hay giá thật vào repo.

## Mô hình dữ liệu (giai đoạn 1 ĐÃ CODE, 29/10/2026)

Bảng trong `specs/v7-backend/schema-draft.sql`, hàm trong `cong-no-web-handoff/tools/v7_backend_functions.sql`, migration `cong-no-web-handoff/tools/migrations/2026-10-29-v7-bang-gia.sql`.

- Nhóm giá cố định hai giá trị theo Q3: `tier` = `khach` (giá khách) hoặc `tt` (giá TT). Không có bảng nhóm riêng.
- `price_tt_shipper(customer_id, name, shipper_key)`: shipper của TT. `shipper_key` = `_price_key(name)`: viết hoa, gộp mọi khoảng trắng (kể cả NBSP) thành một, bỏ đầu cuối.
- `price_location(id, customer_id, name, name_key)` và `price_location_alias(customer_id, location_id, alias, alias_key)`: kho và tên khác. Tên kho và tên khác dùng chung một không gian khóa trong sổ (một cách viết chỉ trỏ một kho).
- `price_period(id, customer_id, valid_from, valid_to)`: `valid_to` NULL là còn hiệu lực; hai đầu đều tính.
- `price_rate(period_id, location_id, customer_id, tier, unit_price_vnd bigint >= 0)`: ô trống không lưu dòng (NULL ≠ 0).
- `trip_price_source(price_rev_id, customer_id, rate jsonb, created_by_event)`: đánh dấu revision giá do bảng giá ghi, kèm dòng giá đã dùng; bất biến. Đơn giá hiện tại "theo bảng" khi revision nguồn còn cùng đơn giá với revision mới nhất (sửa phụ phí sau đó không làm mất nguồn; sửa tay đơn giá thì mất).
- Bảng cấu hình thay cả bảng mỗi lần lưu; vết trước → sau ở `event` kiểu `price_table_edit`. Áp giá ghi `event` kiểu `price_table_apply`.
- K1: chặn chồng ngày trong `save_price_table` (theo cùng kho và cùng loại giá, `daterange` hai đầu tính), không cần extension `btree_gist`.
- K2: nguồn giá ở bảng riêng `trip_price_source`, không thêm cột vào `trip_price_rev`.
- K3: không bóc chữ Trung/dấu gạch tự động; cách viết khác (ví dụ "DAKLAK-…") khai trong tên khác của kho.

## Quy tắc tra giá

Đầu vào: sổ, `event_date`, `origin`, `shipper`. Đầu ra: một đơn giá **hoặc** một lý do không có giá (bảng ở mục Bị chặn).

1. Sổ không có bảng giá → không tra.
2. `event_date` NULL hoặc `origin` trống → `NO_DATE` / `NO_ORIGIN`.
3. `origin` → `alias_key` → kho. Không có → `UNKNOWN_LOCATION`.
4. Nhóm (Q3): shipper (chuẩn hóa `upper/btrim`, gộp khoảng trắng) có trong danh sách shipper của TT → **giá TT**; mọi trường hợp khác, kể cả shipper trống → **giá khách**. Không có lý do "shipper chưa xếp nhóm".
5. Đợt: `valid_from <= event_date` và (`valid_to` NULL hoặc `event_date <= valid_to`), có giá cho kho đó. Không có đợt phủ ngày → `NO_PERIOD`. Có đợt nhưng ô của nhóm cần dùng trống → `NO_RATE` (không lấy giá nhóm kia thay).
6. Không xét nơi đến (Q4: hiện giá không khác theo cảng đích). Khi cần thì thêm sau, không làm trước.

Tra giá là hàm đọc thuần ở DB (`sokhach._lookup_price`), dùng chung cho trạng thái giá và lệnh áp giá; model JS **không** tự tra lại để tránh hai nguồn quy tắc (ARCH-03 giữ tiền ở model, nhưng tra bảng là dữ liệu server).

## Hành vi và bất biến

- **Gõ tay thắng.** Đơn giá người nhập gõ/dán, hoặc ghi từ Sheet, không bao giờ bị bảng giá ghi đè; chỉ ô trống mới được điền.
- **Không tự sửa chuyến đã ghi.** Sửa/xóa đợt giá không đổi `trip_price_rev` nào. Web chỉ đếm chuyến ghi theo dòng bị đổi và mời áp lại; áp lại là một lệnh ghi giá bình thường (phân bổ lại phiếu theo nợ cũ trước, Lịch sử, chặn tháng khóa).
- **NULL không phải 0.** Không tra được → đơn giá NULL, cờ thiếu giá như hiện nay; không điền 0. Giá 0 trong bảng là giá thật 0 (theo `PRICE-ZERO` chỉ cảnh báo).
- Ngày tra là **ngày xe nhập kho** (`DATE`), không phải ngày ghi sổ hay ngày dán. Đổi ngày chuyến (sang tháng khác theo `NHAP-SHEET-01`) mà giá đang là giá theo bảng: web tra lại và hiện đề xuất, không tự đổi.
- Không áp lên opening/lịch sử (`legacy_row`) và không phân bổ lại opening.
- Không chặn khi phép tính đúng: cờ "khác bảng giá" chỉ tô màu.
- Tháng khóa: bảng giá sửa được bất kỳ lúc nào (không phải dữ liệu tiền); áp giá vào chuyến tháng khóa bị chặn như mọi sửa giá (khóa tháng 24/10).
- Idempotency và `expected_version` như mọi lệnh ghi V7; bấm lặp không ghi hai lần.

## Giao tiếp frontend–backend (giai đoạn 1 ĐÃ CODE)

Mọi lệnh ghi theo khuôn V7: `customer_id`, `expected_version`, `idempotency_key`, người làm lấy từ phiên máy chủ; lệnh ghi tăng `version` của sổ.

- `GET /api/v7/price-table?customer=` → `get_price_table`: `{customer_id, version, price_table, book_shippers}`. `price_table` = `{tt_shippers: [tên], locations: [{name, aliases: [tên]}], periods: [{valid_from, valid_to, rates: [{location, tier, unit_price_vnd}]}]}` (tiền là chuỗi). `book_shippers` = shipper đang có trong sổ kèm `tier` đang áp và số chuyến, để soát tên viết lệch.
- `POST /api/v7/price-table` → `save_price_table(customer_id, expected_version, idempotency_key, price_table)`: thay cả bảng, đúng hình dạng như `GET` trả (`valid_to` null được; `aliases` tùy chọn; `rates[].location` là tên kho chuẩn). Bảng rỗng là xóa bảng giá của sổ. Trả `{price_table, affected_trips, version}`; `affected_trips` = chuyến đang theo bảng mà giá tra mới khác đơn giá đang ghi (không đổi chuyến nào). Lỗi: `INVALID_PRICE_TABLE`, `PRICE_INVALID_PERIOD`, `PRICE_INVALID_AMOUNT`, `PRICE_UNKNOWN_LOCATION`, `PRICE_DUPLICATE_ALIAS`, `PRICE_DUPLICATE_SHIPPER`, `PRICE_DUPLICATE_RATE`, `PRICE_PERIOD_OVERLAP`, `NO_CHANGE`, `STALE_LEDGER`, `IDEMPOTENCY_CONFLICT`.
- `GET /api/v7/price-table/status?customer=` → `get_price_status`: `{customer_id, version, has_table, trips: [{trip_id, unit_price_vnd, from_table, lookup, ready, differs}], ready_count, ready_total_vnd, ready_months, reapply_count}`. `lookup` là `{unit_price_vnd, tier, location, valid_from, valid_to}` hoặc `{reason}` với `NO_TABLE`, `NO_DATE`, `NO_ORIGIN`, `UNKNOWN_LOCATION`, `NO_PERIOD`, `NO_RATE`. `ready` = chuyến đã tính vào sổ, tháng mở, chưa có đơn giá, tra được. `differs` = đơn giá đang ghi khác giá tra được (cờ "khác bảng giá"). `ready_total_vnd` = tổng tăng thêm khi áp (đơn giá + phụ phí, phụ phí trống tính 0 theo `V7-BE`).
- `POST /api/v7/price-table/apply` → `apply_price_table(customer_id, expected_version, idempotency_key, trip_ids)`: 1–500 chuyến, tất cả hoặc không. Server tra lại, không nhận giá từ client; giữ nguyên phụ phí; một `event`, phân bổ lại một lần. Lỗi: `TRIP_NOT_FOUND` (kể cả dòng phí lẻ không container), `TRIP_PENDING_REVIEW`, `MONTH_LOCKED`, `PRICE_NOT_FOUND`, `NO_CHANGE`, `INVALID_TRIPS`, `STALE_LEDGER`.
- Không đổi `get_ledger` và `paste_trips`. Dán lô để trống đơn giá như hiện nay; giao diện gọi `apply_price_table` cho các chuyến mới chưa có giá (ô người gõ giữ nguyên vì chuyến đó đã có giá). Thay cho cờ `price_from_table` trong bản đề xuất.

## Giai đoạn

1. **Backend + bảng giá + áp tay** (ĐÃ CODE 29/10/2026, chưa triển khai `hao`): schema, `save_price_table`, `apply_price_table`, `get_price_table`, `get_price_status`, API; harness PostgreSQL case `BANG-GIA.01`.
2. **Giao diện** (bản đầu ĐÃ CODE 29/10/2026, thay bằng giao diện lưới cùng ngày — xem dưới; `so-khach-v7-price-ui.js`, test `test-so-khach-v7-price-browser.js`): nút **Bảng giá** ở đầu sổ mở khung gồm *Dán bảng giá từ Sheet* (5 cột Từ ngày · Đến ngày · Kho · Giá khách · Giá TT, dòng tiêu đề tự bỏ), *Shipper của TT* (kèm danh sách shipper trong sổ đang lấy giá khách và nút "Thêm vào TT"), *Kho và tên khác*, *Đợt giá* (thêm đợt mới mặc định đóng đợt đang áp dụng vào ngày liền trước, chép giá để sửa). Nút **Áp giá theo bảng cho N chuyến** mở khung hỏi lại (số chuyến, tháng, tổng tăng từ server) rồi mới ghi. Ô Đơn giá có chữ nhỏ: "bảng: X (TT/khách)" cho chuyến chưa có giá tra được, "khác bảng: X" (tô vàng) cho giá đang ghi khác bảng, "theo bảng (…)" cho giá ghi từ bảng, hoặc lý do không tra được. Bảng giá đổi thì có dải "Áp lại giá mới". Lịch sử có nhãn "Sửa bảng giá" và "Áp giá theo bảng". Dán lô chuyến không tự điền giá: lưu lô xong, chuyến mới chưa có giá hiện ngay trong nút áp giá (một lần bấm, có hỏi lại) — đổi so với bản đề xuất "tự điền khi dán" để không ghi tiền khi người nhập chưa xem.
   **Giao diện lưới (29/10/2026, thay khung cũ):** người dùng báo khung cũ (shipper của TT, kho và tên khác, đợt giá tách riêng) "không dùng được, không ai hiểu"; người dùng thử mockup v2 và chốt "Ổn, làm thật" (29/10/2026). Khung Bảng giá giờ là **lưới giống vùng bảng giá trên Sheet**: mỗi dòng Từ ngày · Đến ngày · Nơi đi · Giá khách · Giá TT, cột Tình trạng (Đang dùng / Hết hạn / Sắp áp dụng hoặc lỗi của dòng: ngày sai, trùng ngày dòng N), cột riêng **Shipper áp giá TT** bên phải. Dán vùng Sheet (kể cả dòng tiêu đề và cột SHIPPER ÁP GIÁ TT sau một cột trống) vào ô bất kỳ là tự trải, luôn còn 3 hàng trống; bảng trống hiện hình vùng Sheet cần chọn. Dòng cùng Từ/Đến ngày gộp thành một đợt khi gửi server; tên khác của nơi đi đã lưu giữ nguyên (không còn ô sửa trên màn). "Đổi giá từ ngày…" cho dòng đang dùng kết thúc ngày liền trước và thêm dòng chép giá (tô vàng). Lưu xong khung đóng; trên sổ có nút **Điền giá theo bảng (N chuyến)**, khung hỏi lại liệt kê từng chuyến (container, ngày, nơi đi, shipper, đơn giá, loại giá) và tổng còn nợ tăng. Ô Đơn giá: "bảng X" (chưa có giá, tra được), "bảng X" tô vàng (khác bảng), "theo bảng", hoặc lý do ngắn: "ngoài bảng giá", "thiếu giá TT/giá khách", "ngoài ngày có giá". Lịch sử: "Điền giá theo bảng". Chữ trong khung 16px, nút 40px ([UX](../docs/ux-guidelines.md)). Test: `test-so-khach-v7-price-browser.js` 4 case.
3. **Kiểm chéo với Sheet** trong lúc chạy song song: hàng chờ giá hiện thêm giá theo bảng khi khác giá Sheet.

## Ngoài phạm vi

- Phụ phí theo bảng (neo, điện, ghép…): theo `PHU-PHI-01`, nhập tay.
- Bảng giá dùng chung nhiều sổ (Q2: không): mỗi sổ một bảng riêng.
- Áp bảng giá cho dòng sổ gốc (Q5: không): dòng sổ gốc thiếu giá vẫn nhập tay.
- Giá theo cảng đích (Q4: hiện không có).
- Tỷ giá/giá ngoại tệ: chỉ VND.
- Tự đọc vùng bảng giá từ file Sheet bằng công cụ nạp.

## Câu đã chốt (29/10)

Người dùng trả lời trong chat 29/10/2026; ghi ở [`BANG-GIA-01`](../docs/decisions.md#bang-gia-01).

- **Q1.** Ai sửa bảng giá: **mọi người** vào được app; mọi thay đổi ghi Lịch sử và người làm.
- **Q2.** Bảng giá dùng chung nhiều sổ: **không**, mỗi sổ một bảng.
- **Q3.** Bảng giá có hai giá: **giá TT** cho shipper của TT, **giá khách** cho mọi shipper còn lại.
- **Q4.** Giá khác theo cảng đích: **hiện tại không**.
- **Q5.** Áp bảng giá cho dòng sổ gốc thiếu giá: **không**.
- **Q6.** Thêm đợt mới thì web hỏi và mặc định **đóng đợt cũ** vào ngày liền trước: **đồng ý**.

## Tiêu chí nghiệm thu

- [x] Harness PostgreSQL: tra đúng theo đợt ở hai đầu ngày (`valid_from`, `valid_to`, `valid_to` NULL); shipper của TT ra giá TT, shipper khác và shipper trống ra giá khách, tên viết khác khoảng trắng/hoa thường vẫn khớp; tên khác kho; mỗi lý do không có giá ra đúng mã và đơn giá NULL.
- [x] Lưu bảng giá chồng ngày bị `PRICE_PERIOD_OVERLAP`; bảng giữ nguyên.
- [x] Sửa đợt giá không đổi `trip_price_rev` nào; `affected_trips` đếm đúng.
- [x] `apply_price_table`: ghi giá, phân bổ lại phiếu theo nợ cũ trước, Lịch sử có nguồn; chặn CHỜ KIỂM, tháng khóa; gọi lặp cùng `idempotency_key` không ghi hai lần.
- [x] Dán lô (giai đoạn 2): ô gõ tay giữ nguyên; chuyến mới chưa có giá vào nút "Áp giá theo bảng" sau khi lưu lô (test trình duyệt, máy chủ giả).
- [ ] `npm run check` xanh.
- [x] Frontend (test trình duyệt 1280×720, máy chủ giả): dán vùng có ô trống, số có dấu phẩy, ngày một chữ số; ngày sai báo tại khung; lỗi server giữ nguyên bảng đang sửa; hỏi lại trước khi áp; Esc đóng khung. Tháng khóa do server chặn (`MONTH_LOCKED`), chưa có test trình duyệt riêng.
- [ ] Người dùng đối chiếu trên bản thử: một khách có bảng giá, một tháng chuyến, giá web theo bảng khớp cột UNIT PRICE trên Sheet trừ các dòng đã biết lỗi Sheet.

## Phạm vi agent

- Agent: claude (cả ba giai đoạn, `CLAUDE-ALL-01`)
- Review: opus (đường ghi giá, phân bổ lại, schema)
- Được sửa (dự kiến): `specs/v7-backend/schema-draft.sql`, `cong-no-web-handoff/tools/v7_backend_functions.sql`, migration mới trong `cong-no-web-handoff/tools/migrations/`, `cong-no-web-handoff/tools/test_pg_v7_backend_*.py`, `cong-no-web-handoff/web/v7_ledger_api.py`, `cong-no-web-handoff/web/v7_price_queue.py`, `cong-no-web-handoff/preview/so-khach-v7-*.js`, `so-khach-v7-live.html`, test tương ứng
- Lệnh kiểm: `npm run check`; harness `cong-no-web-handoff/tools/test_pg_v7_backend.py`
- Cấm: chạy DDL/migration/import lên `hao` hoặc DB thật; tự áp giá vào chuyến thật; đổi quy tắc khóa tháng, phân bổ, opening; đưa tên khách, shipper, giá thật vào repo.

## Hoàn tác

Spec: revert commit. Khi đã code: migration có bước ngược xóa các bảng `price_*`; giá đã áp vào chuyến là `trip_price_rev` bình thường, giữ nguyên, sửa bằng lệnh sửa giá như mọi chuyến.

## Bằng chứng

Giai đoạn 1 (backend), 29/10/2026, máy Windows của người dùng, dữ liệu giả, không chạm DB thật:

- `test_pg_v7_backend.py` (PostgreSQL 18.6 dùng một lần): 10 SCHEMA + 54 BEHAVIOR pass, 2 SKIPPED_OPEN như trước. Case `BANG-GIA.01` kiểm tra giá theo hai đầu đợt, tên khác kho, shipper TT/khác/trống, các lý do không tra được, mọi lỗi lưu bảng (bảng giữ nguyên khi bị từ chối), áp lô tất cả-hoặc-không, giữ phụ phí, một event, gọi lặp, tháng khóa, nguồn giá sau sửa phụ phí/sửa tay, sửa bảng không đổi chuyến đã ghi, và migration: chạy lại không đổi lược đồ, lỗi giữa chừng thì rollback, áp lên `main` trước PR (`58c43dd`) cho đúng lược đồ mới.
- `test_pg_v7_grants.py --strict`: pass (quyền app/reader của 4 hàm mới, hàm phụ không ai gọi được).
- `npm run check`: xanh.

Chưa triển khai `hao`: migration `2026-10-29-v7-bang-gia.sql` phải chạy tay theo runbook, có gate người dùng. Chưa có giao diện (giai đoạn 2).
