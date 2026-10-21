# V7 M2-11 — Kiểm trùng chuyến mới với bản mốc và với sổ web

Trạng thái: ĐỀ XUẤT (Claude, 21/10/2026, đóng tiêu chí M2-11 của `specs/m2-tieu-chi-v7.md`)

## Đầu ra

`paste_trips` không còn cộng nợ hai lần khi dán lại chuyến đã có trong bản mốc hoặc đã ghi trên web. Mỗi chuyến có container được kiểm trùng trước khi tính nợ: trùng mã (booking+container chuẩn hóa) hoặc cùng container lệch ngày xe ≤3 ngày với một dòng trong tập tham chiếu bản mốc, hoặc trùng mã với một chuyến web đã ghi (bất kỳ trạng thái), thì chuyến vào trạng thái **CHỜ KIỂM**, ngoài số dư — không bị từ chối, không tự tính nợ. Thiếu tập tham chiếu cho mốc đang active của khách thì `paste_trips` chặn toàn bộ lệnh, không coi là "không trùng". Khắc phục lỗ hổng C1 trong `worktrees/m2-review-2026-10-21.md`: probe dán cùng container hai lần hiện cộng nợ 200 thay vì 100.

## Đối chiếu dữ liệu và code hiện có

- `cong-no-web-handoff/tools/v7_backend_functions.sql`: `paste_trips` (dòng 40–106) hiện nhận mỗi dòng chuyến gồm `container`, `carrier`, `from`, `to`, `date`, `note`, `src`, `unitPriceVnd`, `otherFeeVnd` — **không có trường booking**. Không có kiểm trùng nào: mỗi lần gọi chỉ `nextval` id mới rồi insert thẳng. `sokhach._baseline(customer_id)` (dòng 281) chỉ kiểm khách có `cutover_customer`/`cutover` đang `active`, không liên quan tới tập tham chiếu từng chuyến.
- `specs/v7-backend/schema-draft.sql`: `sokhach.trip` (dòng 152–170) không có cột `booking` hay cột trạng thái; `sokhach.v_outstanding_month` (`v7_backend_functions.sql` dòng 5–30, qua CTE `latest_price`) cộng nợ mọi dòng `trip` đang có giá, không lọc trạng thái. Không có bảng tập tham chiếu bản mốc (`baseline_trip_ref` hay tương đương).
- `tools/test_pg_v7_backend.py`: chưa có case kiểm trùng chuyến; case tiếp theo rảnh là số thứ tự chưa dùng (7.16b trở đi đã dùng tới 7.19; chọn số rảnh tiếp theo, không đè case cũ). Không có `SKIPPED_OPEN`/`NEEDS_FUNCTION` nào đang gán cho M2-11 — tiêu chí này đang hoàn toàn thiếu code, không phải case bị skip.
- Quyết định nguồn: `MOC-CHUYEN-MOI`, `NEWTRIP-01`, `ALT-KEY-01`, `BOOKING-EDIT-01`, `TRIP-KEY`, `DUP-01`, `V7-TONG` trong `docs/decisions.md`. `TRIP-KEY` định nghĩa mã chuyến = số booking + số container, chuẩn hóa viết hoa + bỏ mọi khoảng trắng (kể cả khoảng trắng Unicode).

## Nguồn quyết định

- [`MOC-CHUYEN-MOI`](../docs/decisions.md#moc-chuyen-moi): mốc là bản sổ gốc đã nạp vào V7 trên `hao`; chuyến có trong bản đó thuộc số dư đầu, chuyến chưa có thì nhập web và kiểm trùng với chính bản đó, xét theo có mặt trong bản xuất chứ không theo ngày xe.
- [`NEWTRIP-01`](../docs/decisions.md#newtrip-01): chuyến chưa có trong bản mốc tự động coi là không nằm trong opening, **trừ khi** kiểm trùng thấy dấu hiệu đã có trong sổ cũ (mã chuyến đã xuất hiện, hoặc cùng container lệch ngày ≤3 ngày) — có dấu hiệu thì CHỜ KIỂM, ngoài số dư. Tập tham chiếu là dữ liệu chỉ đọc, có hash/thời điểm.
- [`ALT-KEY-01`](../docs/decisions.md#alt-key-01): chuyến thiếu booking (trống hoặc chỉ ký hiệu) dùng mã thay thế = container chuẩn hóa + ngày xe nhập kho, có tiền tố đánh dấu không-booking; vẫn chịu `DUP-01` và `NEWTRIP-01`.
- [`BOOKING-EDIT-01`](../docs/decisions.md#booking-edit-01): booking sửa sau khi đã ghi nợ không đổi mã chuyến/phiếu đã ghi.
- [`DUP-01`](../docs/decisions.md#dup-01) (tinh thần, áp cho V7): mỗi mã chuyến chỉ nên có một charge; charge thứ hai cùng mã CHỜ KIỂM, ngoài số dư.
- [`TRIP-KEY`](../docs/decisions.md#trip-key): mã chuyến = booking + container, chuẩn hóa viết hoa + bỏ mọi khoảng trắng.

## Hành vi và bất biến

- **Phạm vi kiểm trùng:** chỉ áp cho chuyến có container (`v_fee_only = false` trong logic hiện tại của `paste_trips`). Dòng phí lẻ (không container, không đơn giá, có phụ phí) không có mã chuyến, không qua kiểm trùng.
- **Trường `booking` mới:** `paste_trips` nhận thêm khóa JSON tùy chọn `booking` (text) trong mỗi phần tử `trips`. Chuẩn hóa: viết hoa (`upper`), bỏ mọi khoảng trắng kể cả khoảng trắng Unicode (dùng cùng cách chuẩn hóa `regexp_replace` đã áp cho `container`/`booking`, nhất quán một hàm `_normalize_key(text)` dùng lại cho cả hai). Booking trống, NULL, hoặc chỉ gồm ký tự không phải chữ/số sau khi bỏ khoảng trắng (ví dụ `"/"`) → coi là thiếu booking.
- **Mã thay thế (ALT-KEY-01):** khi thiếu booking, `booking_norm` thay bằng mã thay thế có tiền tố cố định (ví dụ `ALT:` + container chuẩn hóa + `:` + `event_date` dạng `YYYYMMDD`); không áp được khi thiếu cả `event_date` hoặc thiếu `container` — trường hợp đó vẫn theo luật cũ của `paste_trips` (thiếu container với chuyến không phải phí lẻ bị `INVALID_TRIP`).
- **Mã chuyến (`trip_code`)** = `booking_norm || '|' || container_norm`, dùng để so khớp trùng mã.
- **Tập tham chiếu bản mốc:** bảng mới `sokhach.baseline_trip_ref`, mỗi dòng gắn `cutover_id` (FK `sokhach.cutover`), `booking_norm`, `container_norm`, `event_date` (có thể NULL nếu nguồn không rõ ngày — dòng đó chỉ dùng để so trùng mã, không dùng cho so lệch ngày ±3 ngày); không có cột tiền, không có tên khách thật trong schema (dữ liệu nạp thật nằm ngoài repo, chỉ fixture giả trong test). Bảng chỉ thêm (không UPDATE/DELETE qua app, giống `legacy_row`/`opening_balance`).
- **Thiếu tập tham chiếu chặn, không coi là vắng:** nếu cutover đang active của khách (`sokhach._baseline` đã xác nhận có) không có bất kỳ dòng `baseline_trip_ref` nào, `paste_trips` phải `RAISE EXCEPTION 'BASELINE_REF_MISSING'` cho toàn bộ lệnh — không tự kết luận "chuyến không có trong mốc nên là chuyến mới". Việc nạp `baseline_trip_ref` thật (script đọc bản mốc, tính hash) **ngoài phạm vi spec này**; test chỉ insert fixture giả trực tiếp.
- **Luật quyết định CHỜ KIỂM cho mỗi chuyến có container, theo thứ tự:**
  1. Nếu tồn tại dòng `baseline_trip_ref` cùng cutover đang active với `booking_norm` + `container_norm` khớp chính xác → CHỜ KIỂM (trùng mã với bản mốc).
  2. Ngược lại, nếu tồn tại dòng `baseline_trip_ref` cùng cutover với `container_norm` khớp và `event_date` khác NULL và lệch tuyệt đối ≤3 ngày với `event_date` của chuyến đang dán (áp cả khi chuyến đang dán thiếu `event_date`? — không: thiếu `event_date` cho chuyến có container là `INVALID_TRIP` theo luật cũ, không đổi) → CHỜ KIỂM (cùng container, lệch ngày trong ngưỡng).
  3. Ngược lại, nếu tồn tại dòng `sokhach.trip` đã ghi (bất kỳ trạng thái, cùng khách) có `trip_code` khớp chính xác (so sánh trên `booking`/`container` đã lưu, chuẩn hóa lại khi so) → CHỜ KIỂM (trùng với chuyến web đã ghi, DUP-01).
  4. Ngược lại, nếu hai phần tử trong **cùng một lệnh paste** có `trip_code` trùng nhau → phần tử thứ hai trở đi CHỜ KIỂM (trùng trong cùng lô dán).
  5. Không khớp điều kiện nào → trạng thái bình thường (`confirmed`), tính nợ ngay như hiện tại.
- **Cột trạng thái:** thêm `sokhach.trip.status text NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed','pending_review'))`. Chuyến CHỜ KIỂM lưu `status='pending_review'`, vẫn insert đủ `trip`/`trip_price_rev` (giữ vết), nhưng **ngoài số dư**: sửa `sokhach.v_outstanding_month` (CTE `latest_price`) thêm điều kiện `t.status='confirmed'`. Không ảnh hưởng chuyến `legacy_row`/opening — bảng đó không có cột này.
- **Trả về:** `paste_trips` phải trả thêm trong kết quả (bên cạnh `trip_ids`, `reallocated`) danh sách chuyến bị đánh CHỜ KIỂM kèm lý do (ví dụ `pending_review: [{"trip_id":…, "reason":"BASELINE_CODE_MATCH"|"BASELINE_DATE_WINDOW"|"WEB_DUPLICATE"|"BATCH_DUPLICATE"}]`), để không phải suy ngược từ `status`.
- **Không đổi:** `reallocate` chỉ chạy trên chuyến `confirmed` (tự nhiên vì `v_outstanding_month` đã lọc; không cần sửa `reallocate` trừ khi nó đọc trực tiếp `trip` thay vì qua view — kiểm lại trước khi sửa, không sửa nếu không cần). Không đổi `DUP-01`/`BOOKING-EDIT-01` cho chuyến đã `confirmed`. Không thêm bước duyệt CHỜ KIỂM thành `confirmed` trong spec này (đó là thao tác khác, CÒN MỞ — chỉ cần trạng thái tồn tại và ngoài số dư, giống các trạng thái "chờ" khác đã có trong hệ thống).

## Tiêu chí nghiệm thu

- [ ] Fixture: 1 chuyến có `booking`+`container` khớp đúng một dòng `baseline_trip_ref` của cutover active → `status='pending_review'`, không có trong `v_outstanding_month`.
- [ ] Fixture: cùng container với một dòng `baseline_trip_ref`, ngày xe lệch 3 ngày (biên) → CHỜ KIỂM; lệch 4 ngày → không CHỜ KIỂM vì lý do này (biên ngưỡng, cả hai hướng ngày sớm/muộn hơn).
- [ ] Probe tái hiện C1: dán cùng `container` hai lần với hai `idempotency_key` khác nhau → lần thứ hai CHỜ KIỂM (trùng với chuyến web đã ghi hoặc trong cùng lô), `total_outstanding_vnd` chỉ cộng một lần (= 100, không phải 200).
- [ ] Hai dòng trùng `trip_code` trong cùng một lệnh `paste_trips` (một lô) → dòng thứ hai CHỜ KIỂM, dòng đầu `confirmed`.
- [ ] Chuyến thiếu `booking` (trống hoặc `"/"`), có `container` + `event_date` → dùng mã thay thế ALT-KEY-01, vẫn đi qua đủ 4 bước kiểm trùng ở trên (ví dụ hai chuyến thiếu booking, cùng container, cùng ngày → CHỜ KIỂM vì trùng mã thay thế).
- [ ] Khách có cutover active nhưng `baseline_trip_ref` rỗng cho cutover đó → `paste_trips` raise `BASELINE_REF_MISSING`, không ghi gì (rollback), không tính là "không trùng".
- [ ] Chuyến phí lẻ (`v_fee_only`) không qua kiểm trùng, hành vi cũ giữ nguyên (không bị gán `status` ảnh hưởng số dư).
- [ ] Chuyến không trùng gì (`booking`/`container` mới hoàn toàn) → `status='confirmed'`, tính nợ ngay như hiện tại; không có regression trên các case `paste_trips` hiện có của `test_pg_v7_backend.py` (7.10b, 7.16b, các case `opening_fifo`…).
- [ ] `tools/test_pg_v7_backend.py`: case mới cho M2-11 gắn nhãn `BEHAVIOR` (không phải `SKIPPED_OPEN`/`NEEDS_FUNCTION`), chạy qua `py -3.13 -m unittest` và script Docker `--network none` hiện có của repo, không cần DB thật.
- [ ] `npm run check` xanh (không đổi code JS/preview, nhưng lệnh này vẫn phải chạy sạch sau khi sửa SQL/test Python).

## Phạm vi agent

- Agent: codex
- Review (model Claude review chốt): opus — đường ghi tiền/kiểm trùng ảnh hưởng số dư.
- Được sửa:
  - `cong-no-web-handoff/tools/v7_backend_functions.sql`
  - `specs/v7-backend/schema-draft.sql`
  - `cong-no-web-handoff/tools/test_pg_v7_backend.py`
- Ngân sách diff: 500 dòng
- Lệnh kiểm:
  - `cd cong-no-web-handoff && py -3.13 -m unittest discover -s tests -v`
  - `py -3.13 tools/test_pg_v7_backend.py` (hoặc đúng lệnh Docker `--network none` đã dùng trong CI cho harness này — xem `.github/workflows/`; agent dùng đúng lệnh CI hiện có, không tự chế cách chạy container mới)
- Cấm:
  - Sửa `cong-no-web-handoff/web/v7_ledger_api.py`, bất kỳ workflow CI, hay `preview/so-khach-v7-*.js` (đang có phiên khác sửa PR #44).
  - Viết script nạp `baseline_trip_ref` thật từ bản mốc (`v7_export_clean.py`/loader) — ngoài phạm vi; chỉ cần bảng và logic đọc nó, dữ liệu test là fixture giả insert trực tiếp.
  - Thêm bước duyệt CHỜ KIỂM → `confirmed` (hàm `resolve_pending`/tương tự) — không có trong tiêu chí M2-11, để spec khác.
  - Đổi `DUP-01`/`ALT-KEY-01`/`NEWTRIP-01` quá phạm vi đã nêu ở trên; đổi schema khác ngoài bảng/cột đã liệt kê; đổi quyền GRANT ngoài việc cấp EXECUTE cho hàm đã sửa nếu ký hiệu hàm đổi.
  - Chạy DDL/import/deploy, chạm `hao`/Sheet/dữ liệu thật; thêm tên khách/số tiền thật vào test hay commit.
- Khi cần vượt phạm vi (ví dụ phát hiện `reallocate` cần sửa để bỏ qua `pending_review`): dừng, ghi vào "Câu hỏi mở" bên dưới, không tự mở rộng ngân sách diff.

## Hoàn tác

Revert commit/PR của nhánh `claude/v7-m2-11-dedup`; không đụng `hao`, Sheet hay dữ liệu thật — thay đổi chỉ ở schema-draft/hàm DRAFT/test, chưa triển khai production.

## Bằng chứng

Revision worktree tại thời điểm viết spec: `c7a572a` (sau `git fetch && merge --ff-only origin/main`, gồm PR #43/#45). Kết quả chạy `scripts/agent-run.ps1` và review chốt sẽ ghi tiếp ở đây sau khi Codex hoàn tất.

## Câu hỏi mở

- Tên cột/bảng cụ thể (`baseline_trip_ref`, `status`, mã lý do CHỜ KIỂM) là đề xuất của spec này, Codex có thể đổi tên nếu có lý do kỹ thuật rõ, nhưng phải giữ đúng ngữ nghĩa bốn bước kiểm trùng và ghi lại tên cuối trong báo cáo để review chốt đối chiếu.
- Việc chốt định dạng tập tham chiếu bản mốc *thật* (nạp từ `captures/2026-10-21-clean-v2/` hay bản mốc `SONG-SONG-01` sau này) là quyết định nghiệp vụ riêng, ngoài phạm vi spec này — spec này chỉ đóng gate kỹ thuật "có tập tham chiếu mới được dán, dán thì kiểm trùng đúng luật".
