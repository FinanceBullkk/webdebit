# V7: bảng giá theo ngày hiệu lực

Trạng thái: **ĐỀ XUẤT** (Claude, 29/10/2026, theo yêu cầu người dùng "viết spec để làm lên web"). Chưa có quyết định trong [`decisions.md`](../docs/decisions.md), chưa có mockup Penpot, chưa code, chưa đổi schema. Các điểm cần người dùng chốt nằm ở mục [CÒN MỞ](#còn-mở-cần-người-dùng-chốt).

## Vì sao làm

Trên Sheet, vài khách có **bảng báo giá** đặt cạnh sổ tháng (tab khách, vùng cột bên phải). Mỗi dòng bảng giá: hiệu lực từ, hiệu lực đến (trống = còn hiệu lực), kho đi, giá thường, giá cho nhóm shipper riêng; kèm danh sách shipper áp giá riêng. Cột UNIT PRICE của từng chuyến là công thức tra bảng đó theo shipper, ngày và kho đi; không có dòng khớp thì ra "CHƯA CÓ GIÁ".

Web hiện không có bảng giá: đơn giá nhập tay, dán, hoặc ghi từ Sheet qua [`v7-price-queue.md`](v7-price-queue.md). Sau ngày chuyển hẳn (`SONG-SONG-01`) không còn Sheet tính giá hộ, nên web phải tự tra được. Trong lúc chạy song song, bảng giá trên web còn dùng để **kiểm chéo** giá Sheet.

Công thức Sheet hiện có mấy chỗ dễ sai, web phải tránh (đọc công thức 29/10/2026, chưa kiểm trên toàn bộ tab):

| Chỗ dễ sai trên Sheet | Web làm thế nào |
| --- | --- |
| Shipper so khớp tuyệt đối. Viết khác một chữ ("… PHAT" so với không có "PHAT") thì **lặng lẽ** lấy giá thường | Shipper chưa xếp nhóm thì không tự điền, hiện "Shipper chưa xếp nhóm giá" |
| Ô ngày là ngày thật (không phải chữ) có thể bị đảo ngày/tháng khi đọc lại | Dùng `event_date` kiểu `date` của chuyến, không đọc lại chuỗi |
| Kho chỉ có giá nhóm riêng, trống giá thường: chuyến shipper thường ra ô trống/0 | Thiếu giá là NULL, cờ thiếu giá như hiện nay |
| Hai dòng chồng ngày: dòng trên thắng, không báo | Chặn lưu khi chồng ngày |
| Vùng tra cố định theo số dòng; thêm dòng ngoài vùng bị bỏ | Bảng giá là dữ liệu riêng, không giới hạn số dòng |
| Sửa bảng giá là tính lại giá mọi chuyến cũ | Giá đã ghi vào chuyến giữ nguyên; sửa bảng chỉ tạo đề xuất áp lại |

## Người dùng và luồng (bước 1)

**Người thao tác:** người nhập (trên 40 tuổi, màn 1280×720, [UX](../docs/ux-guidelines.md)); người sửa bảng giá: CÒN MỞ (Q1). Theo `V7-ID`, mọi lần ghi mang tên người bấm.

**Bối cảnh:** chỉ vài khách có bảng giá; mỗi bảng khoảng 10–30 dòng; giá đổi theo đợt (ví dụ đợt mới hiệu lực từ ngày 10), đợt cũ được đóng bằng ngày "hiệu lực đến". Bảng giá hiện nằm trên Sheet nên cách nhập quen thuộc nhất là **dán**.

| Việc | Thao tác | Số thao tác |
| --- | --- | --- |
| Mở bảng giá của sổ | Đầu sổ khách → **Bảng giá** | 1 |
| Nạp bảng giá lần đầu | Copy vùng bảng giá trên Sheet → dán vào bảng giá web → xem trước → **Lưu** | 3 |
| Thêm đợt giá mới | **Thêm đợt giá** → gõ "hiệu lực từ" → dán hoặc gõ giá từng kho → **Lưu**. Web hỏi "Đóng đợt cũ ngày …?" (ngày trước ngày mới một ngày) | 4 |
| Xếp shipper vào nhóm giá | Bảng giá → khu **Shipper áp giá riêng** → thêm tên | 2 |
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
| Shipper trống hoặc chưa xếp nhóm, khi sổ có nhóm giá riêng | "Shipper chưa xếp nhóm giá" | Xếp shipper vào nhóm (hoặc vào nhóm thường) |
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

## Mô hình dữ liệu (ĐỀ XUẤT cho Codex, chốt ở spec backend)

- `sokhach.price_tier(id, customer_id, name, is_default)`: nhóm giá của sổ. Mỗi sổ có bảng giá có đúng một nhóm mặc định ("Giá thường"); sổ như ví dụ có thêm một nhóm riêng. Không giới hạn cứng hai nhóm.
- `sokhach.price_tier_shipper(customer_id, shipper_key, tier_id)`: shipper → nhóm. `shipper_key` = `upper(btrim)` và gộp khoảng trắng. Một shipper một nhóm trong một sổ.
- `sokhach.price_location(id, customer_id, name)` và `sokhach.price_location_alias(customer_id, alias_key, location_id)`: kho chuẩn và tên khác. `alias_key` chuẩn hóa như shipper; tên chuẩn tự là một alias.
- `sokhach.price_period(id, customer_id, valid_from date NOT NULL, valid_to date NULL)`: một đợt giá, `valid_to >= valid_from`, hai đầu đều tính.
- `sokhach.price_rate(period_id, location_id, tier_id, unit_price_vnd bigint NOT NULL CHECK (>= 0))`: ô trống không lưu dòng (NULL ≠ 0). VND nguyên theo `VND-01`.
- Không chồng ngày: hai đợt của cùng sổ có cùng kho không được giao nhau. Chặn trong hàm ghi (khóa sổ như các lệnh ghi khác); ràng buộc loại trừ bằng `btree_gist` là câu hỏi kỹ thuật (K1).
- Nguồn giá trên chuyến: thêm `price_rate_ref` (period, location, tier) vào `trip_price_rev` hoặc vào payload `event`. Ghi khi giá đến từ bảng; NULL khi gõ tay/dán/Sheet.
- Mọi thay đổi bảng giá: một `event` kiểu mới (`price_table_edit`) với trước → sau, người làm, `idempotency_key`, `expected_version` của sổ.

## Quy tắc tra giá

Đầu vào: sổ, `event_date`, `origin`, `shipper`. Đầu ra: một đơn giá **hoặc** một lý do không có giá (bảng ở mục Bị chặn).

1. Sổ không có bảng giá → không tra.
2. `event_date` NULL hoặc `origin` trống → `NO_DATE` / `NO_ORIGIN`.
3. `origin` → `alias_key` → kho. Không có → `UNKNOWN_LOCATION`.
4. Nhóm: sổ chỉ có nhóm mặc định → nhóm mặc định. Có nhóm riêng: shipper có trong `price_tier_shipper` → nhóm đó; shipper trống hoặc chưa xếp → `SHIPPER_UNGROUPED` (không đoán giá thường; khác Sheet, xem Q3).
5. Đợt: `valid_from <= event_date` và (`valid_to` NULL hoặc `event_date <= valid_to`), có giá cho kho đó. Không có đợt phủ ngày → `NO_PERIOD`. Có đợt nhưng ô của nhóm trống → `NO_RATE`.
6. Không xét nơi đến (Sheet hiện không xét; Q4).

Tra giá là hàm đọc thuần ở DB (`sokhach.lookup_price(...)`), gọi được cho một chuyến hoặc một lô; model JS **không** tự tra lại để tránh hai nguồn quy tắc (ARCH-03 giữ tiền ở model, nhưng tra bảng là dữ liệu server).

## Hành vi và bất biến

- **Gõ tay thắng.** Đơn giá người nhập gõ/dán, hoặc ghi từ Sheet, không bao giờ bị bảng giá ghi đè; chỉ ô trống mới được điền.
- **Không tự sửa chuyến đã ghi.** Sửa/xóa đợt giá không đổi `trip_price_rev` nào. Web chỉ đếm chuyến ghi theo dòng bị đổi và mời áp lại; áp lại là một lệnh ghi giá bình thường (phân bổ lại phiếu theo nợ cũ trước, Lịch sử, chặn tháng khóa).
- **NULL không phải 0.** Không tra được → đơn giá NULL, cờ thiếu giá như hiện nay; không điền 0. Giá 0 trong bảng là giá thật 0 (theo `PRICE-ZERO` chỉ cảnh báo).
- Ngày tra là **ngày xe nhập kho** (`DATE`), không phải ngày ghi sổ hay ngày dán. Đổi ngày chuyến (sang tháng khác theo `NHAP-SHEET-01`) mà giá đang là giá theo bảng: web tra lại và hiện đề xuất, không tự đổi.
- Không áp lên opening/lịch sử (`legacy_row`) và không phân bổ lại opening.
- Không chặn khi phép tính đúng: cờ "khác bảng giá" chỉ tô màu.
- Tháng khóa: bảng giá sửa được bất kỳ lúc nào (không phải dữ liệu tiền); áp giá vào chuyến tháng khóa bị chặn như mọi sửa giá (khóa tháng 24/10).
- Idempotency và `expected_version` như mọi lệnh ghi V7; bấm lặp không ghi hai lần.

## Giao tiếp frontend–backend (bước 5, ĐỀ XUẤT)

- `GET /api/v7/price-table?customer_id=` → `{version, tiers, shippers, locations(aliases), periods[{id, valid_from, valid_to, rates[{location_id, tier_id, unit_price_vnd}]}]}`.
- `POST /api/v7/price-table` → `save_price_table(customer_id, expected_version, idempotency_key, table jsonb)`: thay cả bảng của sổ trong một lệnh (bảng nhỏ, dễ kiểm chồng ngày). Trả `{version, affected_trips: N}` (chuyến đã ghi theo dòng bị đổi). Lỗi: `PRICE_PERIOD_OVERLAP` (kèm hai đợt), `PRICE_INVALID_AMOUNT`, `PRICE_DUPLICATE_ALIAS`, `PRICE_SHIPPER_TWO_TIERS`, `VERSION_CONFLICT`.
- `POST /api/v7/price-table/lookup` → `lookup_price(customer_id, rows jsonb)` cho bảng nháp nhập chuyến: mỗi dòng `{date, origin, shipper}` → `{unit_price_vnd, ref}` hoặc `{reason}`. Chỉ đọc.
- `get_ledger` trả thêm cho mỗi chuyến `price_table: {unit_price_vnd, ref} | {reason}` và `price_source: 'table' | 'manual' | 'sheet' | null`; thêm `price_apply: {ready_count, total_delta_vnd, months}`.
- `POST /api/v7/price-table/apply` → `apply_price_table(customer_id, expected_version, idempotency_key, trip_ids bigint[])`: ghi giá theo bảng cho chuyến được chọn (chưa có giá, hoặc đề xuất áp lại). Server tra lại, không tin giá client gửi. Chặn chuyến CHỜ KIỂM, tháng khóa (`MONTH_LOCKED`), chuyến không tra được.
- `paste_trips` nhận thêm cờ cho từng dòng `price_from_table: true` khi ô đơn giá do web điền; server tra lại và ghi `ref`. Ô người gõ không có cờ.

## Giai đoạn

1. **Backend + bảng giá + áp tay** (Codex): schema, `save_price_table`, `lookup_price`, `apply_price_table`, `get_ledger` trả cờ; harness PostgreSQL.
2. **Giao diện** (sau Penpot duyệt): màn Bảng giá (dán, đợt, nhóm shipper, tên khác kho), nút "Áp giá theo bảng cho N chuyến", cờ "khác bảng giá", tự điền ở bảng nhập kiểu Sheet.
3. **Kiểm chéo với Sheet** trong lúc chạy song song: hàng chờ giá hiện thêm giá theo bảng khi khác giá Sheet.

## Ngoài phạm vi

- Phụ phí theo bảng (neo, điện, ghép…): theo `PHU-PHI-01`, nhập tay.
- Bảng giá dùng chung nhiều sổ (Q2): giai đoạn đầu mỗi sổ một bảng, có nút chép từ sổ khác nếu chốt cần.
- Tỷ giá/giá ngoại tệ: chỉ VND.
- Tự đọc vùng bảng giá từ file Sheet bằng công cụ nạp.

## CÒN MỞ (cần người dùng chốt)

- **Q1.** Ai được sửa bảng giá: mọi người vào được app (như `V7-ID` hiện nay), hay chỉ chủ nghiệp vụ (`PRICE-MAKER`: người xác nhận giá là chủ nghiệp vụ)?
- **Q2.** Một bảng giá có dùng chung cho nhiều sổ không (ví dụ cùng một bảng cho khách và nhóm khách liên quan)?
- **Q3.** Shipper chưa xếp nhóm: web để trống và báo (đề xuất), hay lấy giá thường như Sheet đang làm?
- **Q4.** Giá có khi nào khác theo nơi đến (cảng đích) không? Hiện Sheet không xét.
- **Q5.** Có cần áp bảng giá cho dòng sổ gốc thiếu giá (opening) không? Đề xuất: không, giữ nhập tay.
- **Q6.** Khi thêm đợt mới, có tự đóng đợt cũ vào ngày trước một ngày không (đề xuất: hỏi, mặc định có)?

## Câu hỏi kỹ thuật (Codex trả lời trong spec backend)

- **K1.** Chặn chồng ngày bằng hàm hay ràng buộc `EXCLUDE USING gist` (cần extension `btree_gist` trên `hao`)?
- **K2.** Nguồn giá lưu ở `trip_price_rev` (cột mới) hay payload `event`; cách `get_ledger` đếm "chuyến đã ghi theo dòng bị đổi" cho nhanh.
- **K3.** `origin` hiện có kèm chữ Trung/dấu gạch ("DAKLAK-…"): chuẩn hóa thêm gì ngoài `upper/btrim`, hay để hết cho bảng tên khác.

## Tiêu chí nghiệm thu

- [ ] Harness PostgreSQL: tra đúng theo đợt ở hai đầu ngày (`valid_from`, `valid_to`, `valid_to` NULL); shipper nhóm riêng/nhóm thường/chưa xếp; tên khác kho; mỗi lý do không có giá ra đúng mã và đơn giá NULL.
- [ ] Lưu bảng giá chồng ngày bị `PRICE_PERIOD_OVERLAP`; bảng giữ nguyên.
- [ ] Sửa đợt giá không đổi `trip_price_rev` nào; `affected_trips` đếm đúng.
- [ ] `apply_price_table`: ghi giá, phân bổ lại phiếu theo nợ cũ trước, Lịch sử có nguồn; chặn CHỜ KIỂM, tháng khóa; gọi lặp cùng `idempotency_key` không ghi hai lần.
- [ ] Dán lô: ô gõ tay giữ nguyên; ô trống được điền và ghi `ref`; giá client gửi kèm `price_from_table` sai thì server dùng giá tra lại.
- [ ] `npm run check` xanh.
- [ ] Frontend: khớp mockup Penpot đã duyệt; bàn phím/focus ở màn bảng giá; dán vùng có ô trống, số có dấu chấm/phẩy; bấm lặp; tháng khóa.
- [ ] Người dùng đối chiếu trên bản thử: một khách có bảng giá, một tháng chuyến, giá web theo bảng khớp cột UNIT PRICE trên Sheet trừ các dòng đã biết lỗi Sheet.

## Phạm vi agent

Spec tổng; giao việc bằng spec con theo [`_template.md`](_template.md).

- Agent: codex (giai đoạn 1), gemini (giai đoạn 2 sau Penpot), claude (review, giai đoạn 3)
- Mockup: CHỜ DUYỆT — chưa có
- Review: opus (đường ghi giá, phân bổ lại, schema)
- Được sửa (dự kiến, chốt ở spec con): `specs/v7-backend/schema-draft.sql`, `cong-no-web-handoff/tools/v7_backend_functions.sql`, migration mới trong `cong-no-web-handoff/tools/migrations/`, `cong-no-web-handoff/tools/test_pg_v7_backend_*.py`, `cong-no-web-handoff/web/v7_ledger_api.py`, `cong-no-web-handoff/web/v7_price_queue.py`, `cong-no-web-handoff/preview/so-khach-v7-*.js`, `so-khach-v7-live.html`, test tương ứng
- Lệnh kiểm: `npm run check`; harness `cong-no-web-handoff/tools/test_pg_v7_backend.py`
- Cấm: chạy DDL/migration/import lên `hao` hoặc DB thật; tự áp giá vào chuyến thật; đổi quy tắc khóa tháng, phân bổ, opening; đưa tên khách, shipper, giá thật vào repo.

## Hoàn tác

Spec: revert commit. Khi đã code: migration có bước ngược xóa các bảng `price_*`; giá đã áp vào chuyến là `trip_price_rev` bình thường, giữ nguyên, sửa bằng lệnh sửa giá như mọi chuyến.

## Bằng chứng

Chưa có. Nguồn quy tắc: công thức cột UNIT PRICE và bảng giá trên tab khách người dùng gửi trong chat 29/10/2026 (ảnh, không lưu vào repo).
