# V7 backend — sửa trường chữ/ngày, xóa chuyến, sửa/xóa dòng sổ gốc (NHAP-SHEET-01)

Trạng thái: **ĐỀ XUẤT** (Claude, 22/10/2026). Chính sách **ĐÃ CHỐT** ở [`NHAP-SHEET-01`](../docs/decisions.md#nhap-sheet-01); giao diện ở [`v7-nhap-kieu-sheet.md`](v7-nhap-kieu-sheet.md). Chưa code, chưa migration, chưa chạy gì trên `hao`. Người code: Codex (backend) theo [phân vai](../docs/multi-agent.md); Claude review.

## Mục tiêu

Bốn lệnh ghi mới, cùng khuôn với các lệnh V7 hiện có (`_begin_command`/`_finish_command`, version, idempotency, actor, event trước → sau, `reallocate`):

| Lệnh | Việc | Route |
| --- | --- | --- |
| `edit_trip_info` | Sửa một ô chữ/ngày của chuyến web: container, hãng tàu, nơi đi, nơi đến, ngày chuyến. Đổi ngày sang tháng khác thì chuyến sang kỳ nợ tháng đó | `POST /api/v7/trips/info` |
| `delete_trip` | Xóa hẳn một chuyến web (mọi trạng thái, mọi tháng) | `POST /api/v7/trips/delete` |
| `edit_legacy_trip` | Sửa một ô của dòng chuyến từ sổ gốc, kể cả đơn giá/phụ phí và ngày | `POST /api/v7/legacy/edit` |
| `delete_legacy_trip` | Xóa một dòng chuyến từ sổ gốc | `POST /api/v7/legacy/delete` |

Sửa **tiền** của chuyến web giữ nguyên hai lệnh đang có: tháng mở `edit_trip_price`, tháng khóa `adjust_trip` (`V7-SO`). Giao diện chọn lệnh theo cờ khóa như hiện nay.

## Hiện trạng phải đổi

- `sokhach.trip` và `sokhach.adjustment` có trigger `reject_immutable_change` (`specs/v7-backend/schema-draft.sql` dòng 412–417): không UPDATE/DELETE. Bảng `trip` là "danh tính chuyến chỉ thêm".
- `trip.debt_month` ghi lúc dán, chú thích "không suy ra kỳ nợ từ `event_date`". `NHAP-SHEET-01` (5) đổi: **kỳ nợ = tháng của ngày chuyến**, đổi ngày thì đổi kỳ.
- `adjustment` có FK `(trip_id, customer_id, debt_month)` → `trip(id, customer_id, debt_month)`.
- `legacy_row` bất biến, "không cột nào tham gia công thức tiền" (`schema-draft.sql` dòng 123–138, trigger dòng 591–596). `get_ledger` trả `editable:false`.
- Các chỗ đọc tiền chuyến trực tiếp từ `trip`: `v_outstanding_month` (`v7_backend_functions.sql` đầu file), CTE `charges` trong `reallocate`, tổng tháng và danh sách chuyến trong `get_ledger`, kiểm tháng có dữ liệu trong `adjust_month`, kiểm trùng trong `paste_trips`.
- Nhánh `claude/v7-pending-review` (chưa merge lúc viết) thêm `review_trip`, trạng thái `rejected`, cột `reviewed_by_event` và guard chỉ cho đổi `trip.status` một lần. Spec này **xây trên nhánh đó** sau khi nó vào `main`.

## Thiết kế

Giữ nguyên nguyên tắc chỉ-thêm: không UPDATE/DELETE `trip`, `adjustment`, `legacy_row`, `opening_balance`. Thay đổi đi vào bảng revision mới; giá trị hiện tại là revision mới nhất.

### 1. Chuyến web: `trip_info_rev` + view `v_trip_current`

```sql
CREATE TABLE sokhach.trip_info_rev (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    event_date date,
    container text, carrier text, origin text, destination text,
    status text NOT NULL CHECK (status IN ('confirmed','pending_review','rejected')),
    deleted boolean NOT NULL DEFAULT false,
    created_by_event bigint NOT NULL,
    FOREIGN KEY (trip_id, customer_id) REFERENCES sokhach.trip(id, customer_id),
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id)
);  -- trigger reject_immutable_change; index (trip_id, id DESC)
```

`v_trip_current`: mỗi `trip` lấy revision mới nhất (`ORDER BY id DESC LIMIT 1`), không có thì lấy chính hàng `trip`. Cột: `id, customer_id, origin_month` (= `trip.debt_month`, giữ cho FK), `debt_month` (hiện tại), `event_date, container, carrier, origin, destination, booking, status, deleted`.

- **Mọi chỗ đọc tiền/hiển thị chuyến đổi sang `v_trip_current` và lọc `NOT deleted`**: `v_outstanding_month`, `reallocate`, `get_ledger`, `adjust_month`, `paste_trips` (kiểm trùng so với chuyến web hiện tại, bỏ chuyến đã xóa), `edit_trip_price`/`adjust_trip` (kiểm khóa theo `debt_month` **hiện tại**).
- **Dòng điều chỉnh gắn chuyến đi theo chuyến:** `adjustment.debt_month` của dòng có `trip_id` vẫn ghi `origin_month` (giữ FK, không sửa bảng). Khi cộng tiền, view lấy tháng **hiện tại** của chuyến qua `v_trip_current`; chuyến đã xóa thì bỏ cả các dòng điều chỉnh của nó. Điều chỉnh cả tháng (`trip_id IS NULL`) giữ tháng ghi.
- **Trạng thái:** `review_trip` của nhánh pending-review phải đọc/ghi trạng thái qua revision (ghi một `trip_info_rev` mới với status kết luận) thay cho UPDATE có guard — hoặc giữ guard và `v_trip_current` ưu tiên `trip.status` khi `reviewed_by_event` mới hơn revision. Chọn một khi gộp hai nhánh; đề xuất cách đầu (một nguồn sự thật).

### 2. `edit_trip_info(customer_id, expected_version, idempotency_key, trip_id, field, value text)`

- `field` ∈ `container, carrier, origin, destination, event_date`; khác → `INVALID_FIELD`. Chuyến không có hoặc đã xóa → `TRIP_NOT_FOUND`.
- Chuẩn hóa: chữ `btrim`, rỗng → lỗi `INVALID_TRIP_INPUT` cho container/carrier/origin/destination của chuyến có container (phí lẻ giữ luật hiện tại). Container viết hoa, bỏ khoảng trắng như `paste_trips`. Ngày `YYYY-MM-DD`; sau hôm nay (giờ VN) → `FUTURE_DATE`.
- **Không kiểm khóa tháng** (`NHAP-SHEET-01` (3)): sửa đè được ở tháng mở và khóa, kể cả chuyển ra/vào tháng khóa (5).
- Đổi `event_date` sang tháng khác → `debt_month` mới = `date_trunc('month', event_date)`.
- Đổi container hoặc ngày của chuyến `confirmed` → chạy lại kiểm trùng `NEWTRIP-01` như `paste_trips` (so bản mốc và chuyến web hiện tại khác chính nó). Có dấu hiệu trùng → revision mang `status='pending_review'`, chuyến ra khỏi số dư, kết quả trả `pending_review:true` kèm lý do. Lệnh sửa **không bao giờ** tự đưa `pending_review` về `confirmed` (việc đó của `review_trip`).
- Giá trị không đổi → `NO_CHANGE`.
- Ghi event `trip_edit`: before `{trip:{id, field, value, debt_month, status}}`, after `{trip:{id, field, value, debt_month, status}, moved_from_month?, moved_to_month?}`; thêm revision; `reallocate`.

### 3. `delete_trip(customer_id, expected_version, idempotency_key, trip_id)`

- Mọi trạng thái, mọi tháng (`NHAP-SHEET-01` (4)). Đã xóa → `TRIP_NOT_FOUND`.
- Event `trip_delete`: before = ảnh đủ chuyến hiện tại (các ô, giá hiện tại, thành tiền gồm điều chỉnh, tháng, trạng thái); after `{trip:{id, deleted:true}}`. Thêm revision `deleted=true`; `reallocate`.
- Không hoàn tác ở vòng này (nhập lại nếu xóa nhầm). Phiếu thu đã phân bổ vào chuyến không bị ảnh hưởng ngoài việc phân bổ lại theo nợ cũ trước.

### 4. Dòng sổ gốc: `legacy_trip_rev` + điều chỉnh gắn dòng

Số dư đầu và `legacy_row` **không đổi**. Phần chênh đi vào `adjustment` như mọi điều chỉnh khác, nên view tiền, `reallocate`, đối soát tổng khách **không cần đường tính mới**.

```sql
CREATE TABLE sokhach.legacy_trip_rev (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    legacy_row_id bigint NOT NULL REFERENCES sokhach.legacy_row(id),
    customer_id bigint NOT NULL,
    debt_month date NOT NULL CHECK (EXTRACT(DAY FROM debt_month) = 1),
    event_date date,
    container text, carrier text, origin text, destination text,
    unit_price_vnd bigint CHECK (unit_price_vnd >= 0),
    other_fee_vnd bigint CHECK (other_fee_vnd >= 0),
    deleted boolean NOT NULL DEFAULT false,
    counted_vnd bigint NOT NULL,          -- số dòng này đang góp vào nợ sau revision
    created_by_event bigint NOT NULL,
    FOREIGN KEY (created_by_event, customer_id) REFERENCES sokhach.event(id, customer_id)
);  -- trigger reject_immutable_change
ALTER TABLE sokhach.adjustment ADD COLUMN legacy_row_id bigint REFERENCES sokhach.legacy_row(id);
ALTER TABLE sokhach.adjustment ADD CONSTRAINT adjustment_one_target CHECK (trip_id IS NULL OR legacy_row_id IS NULL);
```

**Mốc so sánh của một dòng** (trước mọi revision): tháng = `legacy_row.debt_month`, số đang góp = `coalesce(source_total_vnd, 0)` — chính số Sheet đã cộng khi ra số dư đầu. Các ô ban đầu đọc từ `display` (`container, carrier, date, from, to, unit_price, fee_vnd`); ô `display` không đọc được thì để NULL.

**`edit_legacy_trip(customer_id, expected_version, idempotency_key, legacy_row_id, field, value text)`**

- `field` ∈ `container, carrier, origin, destination, event_date, unit_price_vnd, other_fee_vnd`. Dòng `kind='receipt'` → `LEGACY_NOT_TRIP`; không thuộc cutover active của khách → `LEGACY_NOT_FOUND`; đã xóa → `LEGACY_NOT_FOUND`.
- Tiền: chuỗi chữ số; rỗng = NULL. Số góp mới = `unit_price + coalesce(other_fee, 0)` khi có đơn giá, **0 khi chưa có giá** (chưa có giá vẫn ngoài số dư; `V7-BE` cho phụ phí trống).
- Ngày: như `edit_trip_info`; đổi tháng thì `debt_month` mới theo ngày.
- Không kiểm khóa tháng (`NHAP-SHEET-01` (3), (6)).
- Ghi: event `legacy_edit` (before/after: ô, tháng, số góp), một revision đủ ảnh, rồi **dòng điều chỉnh** `legacy_row_id = …, trip_id NULL`:
  - cùng tháng: một dòng `số góp mới − số góp cũ` (bỏ nếu 0);
  - đổi tháng: dòng `−số góp cũ` ở tháng cũ và `+số góp mới` ở tháng mới (bỏ dòng bằng 0).
  - Đổi ô chữ không đổi tiền → chỉ event + revision, không có dòng điều chỉnh.
- `reallocate`.

**`delete_legacy_trip(customer_id, expected_version, idempotency_key, legacy_row_id)`**: event `legacy_delete` (ảnh đủ dòng), revision `deleted=true, counted_vnd=0`, điều chỉnh `−số góp cũ` ở tháng hiện tại của dòng, `reallocate`.

Ví dụ (khớp bản xem): dòng tháng 9 Sheet tính 60.000.000, sửa đơn giá 65.000.000 → +5.000.000 tháng 9; rồi xóa → −65.000.000 tháng 9 (tổng chênh −60.000.000). Dòng tháng 10 chưa có giá (Sheet tính 0), điền 70.000.000 → +70.000.000 tháng 10. Dòng tháng 10 có 93.000.000 đổi ngày sang 28/09 → −93.000.000 tháng 10, +93.000.000 tháng 9.

### 5. `event.kind`

Thêm `trip_edit`, `trip_delete`, `legacy_edit`, `legacy_delete` vào CHECK, mỗi loại có khóa tối thiểu: `trip_edit`/`legacy_edit` có `before ? 'trip'|'legacy'` và `after ? 'trip'|'legacy'`; `*_delete` có ảnh đủ ở `before` và `after->'deleted' = true`.

### 6. `get_ledger`

- `trips`: từ `v_trip_current`, bỏ `deleted`; `month` = tháng hiện tại; `editable` (tiền) giữ theo khóa tháng hiện tại; thêm `info_editable:true`.
- `legacy_rows` (`kind='trip'`): thêm `current` = ô hiện tại (`container, carrier, event_date, origin, destination, unit_price_vnd, other_fee_vnd, month, counted_vnd`), `editable:true`; dòng đã xóa không trả. `display` gốc giữ nguyên để đối chiếu; `month` của dòng = tháng hiện tại.
- `adjustments`: thêm `legacy_row_id`. Giao diện cộng các dòng có `legacy_row_id` theo tháng thành dòng "Điều chỉnh do sửa/xóa dòng sổ gốc tháng này".
- `events`: thêm nhãn cho 4 loại mới.

### 7. `paste_trips`: kỳ nợ theo ngày chuyến

`NHAP-SHEET-01` (5): mỗi chuyến dán vào kỳ nợ = tháng của ngày chuyến; phí lẻ không ngày dùng `debt_month` của lệnh. Tham số `debt_month` giữ cho phí lẻ và tương thích. Kiểm khóa: **ĐÃ CHỐT** (người dùng, chat 22/10/2026, `NHAP-SHEET-01` (7)): chuyến có ngày thuộc **tháng đã khóa vẫn vào thẳng tháng đó**, không chặn, không cần mở khóa. Bỏ `_month_open` khỏi `paste_trips`; kiểm thêm: dán lô có chuyến tháng khóa và tháng mở trong cùng lệnh → mỗi chuyến vào đúng tháng của nó, một event `paste`.

### 8. API (`cong-no-web-handoff/web/v7_ledger_api.py`)

```python
"/api/v7/trips/info":    ("edit_trip_info",     {"trip_id", "field", "value"}),
"/api/v7/trips/delete":  ("delete_trip",        {"trip_id"}),
"/api/v7/legacy/edit":   ("edit_legacy_trip",   {"legacy_row_id", "field", "value"}),
"/api/v7/legacy/delete": ("delete_legacy_trip", {"legacy_row_id"}),
```

Lỗi mới: `INVALID_FIELD` (422), `LEGACY_NOT_FOUND` (422, "Không tìm thấy dòng sổ gốc."), `LEGACY_NOT_TRIP` (422, "Dòng sổ gốc này là khoản thu, không sửa ở đây."). Dùng lại `TRIP_NOT_FOUND`, `FUTURE_DATE`, `INVALID_DATE`, `INVALID_VND`, `NO_CHANGE`, `STALE_LEDGER`. `GRANT EXECUTE` 4 hàm mới cho `sokhach_app`, cập nhật `test_pg_v7_grants.py`.

## Migration và triển khai

- Một file `cong-no-web-handoff/tools/migrations/2026-10-xx-v7-nhap-sheet.sql`, một transaction, chạy lặp được, cùng khuôn với migration M2-11/trip-review: chụp tổng nợ từng khách trước, tạo bảng/cột/trigger/view/hàm, so lại tổng **phải bằng nhau** (migration không đổi tiền), lệch thì ROLLBACK.
- Thêm kiểm vào `v7_post_deploy_check.sql`: `adjustment_one_target`; mọi `legacy_trip_rev.counted_vnd` mới nhất của dòng = mốc + tổng điều chỉnh của dòng; không chuyến nào có revision mà thiếu event.
- Runbook: backup trước, đối soát `DOI SOAT` 236 khách sau, theo gate riêng. **Spec này không cho phép chạy gì trên `hao`.**

## Kiểm (DB test dùng một lần, `test_pg_v7_backend.py`)

- [ ] `edit_trip_info` từng trường, tháng mở và khóa: event đúng trước → sau; version tăng; idempotency lặp trả cùng kết quả, khác nội dung → `IDEMPOTENCY_CONFLICT`.
- [ ] Đổi ngày sang tháng khác: chuyến và **các dòng điều chỉnh của nó** sang tháng mới; tổng khách không đổi; phiếu phân bổ lại theo nợ cũ trước; tháng chưa có dữ liệu hiện ra trong `get_ledger`.
- [ ] Đổi container thành container trùng bản mốc → `pending_review`, ra khỏi số dư; lệnh sửa không bao giờ ra `confirmed` từ `pending_review`.
- [ ] Ngày tương lai → `FUTURE_DATE`; field lạ → `INVALID_FIELD`; giá trị như cũ → `NO_CHANGE`.
- [ ] `delete_trip` ở tháng mở, khóa, chuyến có điều chỉnh, chuyến CHỜ KIỂM: tổng giảm đúng thành tiền hiện tại (gồm điều chỉnh); `paste_trips` sau đó không coi chuyến đã xóa là trùng web.
- [ ] `edit_legacy_trip`: điền giá dòng thiếu giá (+đủ số); sửa giá (+/− chênh); đổi ngày khác tháng (− tháng cũ, + tháng mới); sửa ô chữ (không có dòng tiền); dòng `receipt` → `LEGACY_NOT_TRIP`; dòng của cutover khác → `LEGACY_NOT_FOUND`.
- [ ] `delete_legacy_trip` sau khi đã sửa giá: tổng chênh của dòng = −số Sheet ban đầu.
- [ ] `opening_balance`, `legacy_row`, `trip`, `adjustment` không có UPDATE/DELETE nào (trigger vẫn chặn).
- [ ] Ví dụ ở mục 4 cho đúng từng đồng.
- [ ] Migration: chạy trên DB có dữ liệu giả M2-11 + trip-review, tổng từng khách trước = sau; chạy lần hai không đổi gì.
- [ ] `paste_trips` có chuyến ngày thuộc tháng khóa: ghi vào tháng đó, không lỗi `MONTH_LOCKED`; lô trộn tháng mở/khóa ghi đúng từng tháng.
- [ ] API unit (`test_v7_ledger_api.py`): 4 route, chỉ nhận đúng trường, lỗi map đúng.

## Rủi ro

- **Hiệu năng:** `v_trip_current` thêm một LATERAL mỗi chuyến trong view tiền; khách lớn ~500 chuyến. Đo trên DB thử; index `(trip_id, id DESC)` dự kiến đủ cho cỡ này (không thêm cột con trỏ vào `trip` vì bảng bất biến).
- **Đối soát Sheet–web theo khách** (PR #54): tổng vẫn đúng vì chênh nằm ở `adjustment`; nhưng trong thời gian chạy song song, sửa dòng sổ gốc trên web mà không sửa Sheet sẽ làm lệch — đúng ý `SONG-SONG-01` (mọi sửa trên Sheet sau mốc dán lên web), người nhập phải sửa cả hai nơi.
- **Số Sheet `source_total_vnd` sai** (cờ chênh 600đ, ô tổng lệch đơn giá+phí): lấy đúng số Sheet đã cộng làm mốc nên tổng khách không lệch; phần sai lộ ra ở lần sửa đầu (chênh lớn hơn dự kiến). Ghi rõ trong Lịch sử: "Sheet tính X, nay Y".

## Câu hỏi còn mở

1. Gộp với `review_trip`: trạng thái ghi qua revision (đề xuất) hay giữ guard UPDATE một lần.
2. Hoàn tác xóa (khôi phục chuyến/dòng sổ gốc đã xóa) — chưa làm ở vòng này.
