# V7 — phụ phí nhiều loại: backend và migration

Trạng thái: ĐỀ XUẤT — chờ Claude (opus) review. Chưa code hoặc triển khai.

## Đầu ra

Lõi PostgreSQL/API lưu nhiều dòng phụ phí theo chuyến hoặc dòng sổ gốc, danh mục và tối đa ba cột riêng theo sổ. Migration chuyển phí cũ, giữ tổng tiền từng dòng/tháng/khách. Không làm UI hoặc đọc bảng PS.

## Đối chiếu dữ liệu và code hiện có

- Chuyến web: phí nằm ở revision mới nhất của `trip_price_rev.other_fee_vnd` cộng `adjustment(field='other_fee_vnd')`. `v_outstanding_month` cộng adjustment riêng vào dư nợ; nếu chuyển cả adjustment phí thành dòng mới mà không loại phần cũ, nợ bị cộng hai lần.
- Dòng sổ gốc: `_legacy_current` đọc `legacy_trip_rev.other_fee_vnd` nếu có revision, nếu không parse `legacy_row.display.fee_vnd`. `source_total_vnd` là ô tổng, không chứng minh phần phí. `_change_legacy` ghi chênh lệch vào `adjustment`; opening không đổi.
- `v7_price_queue.py` hiện so phí một số, coi phí âm là `MANUAL`. `v7_ledger_api.py` và test gọi chữ ký cũ của `edit_trip_price`, `adjust_trip`, `edit_legacy_trip`.

## Giao tiếp frontend–backend

Lệnh ghi trên sổ dùng `customer_id`, `expected_version`, `idempotency_key`, khóa hàng khách, actor từ `_actor()`, event trước → sau và phân bổ lại tối đa một lần khi đổi tiền. Lệnh danh mục toàn cục khóa hàng danh mục và ghi `fee_type_audit`, không giả gắn vào khách.

| Bảng | Hợp đồng |
| --- | --- |
| `fee_type` | `id`, `name` unique theo `lower(btrim(name))`, `kind` service/pass_through, `sign` positive/negative/any, `system_key`, `active`, `sort` |
| `book_fee_column` | `customer_id`, `fee_type_id`, `position` 1..3; unique cả hai chiều |
| `trip_fee_line` | `id`, `customer_id`, đúng một `trip_id`/`legacy_row_id`, `fee_type_id`, `amount_vnd bigint` khác 0, `note`, `created_by_event`, `voided_by_event` NULL; chỉ thêm; khách phải khớp khách của target, kiểm bằng trigger/hàm |
| `fee_type_audit` | vết danh mục toàn cục: actor từ phiên, trước → sau, thời điểm, `idempotency_key` unique và payload để phát hiện cùng key khác nội dung; không thuộc event của khách |
| `adjustment.fee_absorbed` | boolean mặc định false; chỉ migration chuyển true một lần cho adjustment phí đã gộp, kể cả tổng phí hiệu quả bằng 0 nên không có dòng mới; adjustment giữ làm chứng cứ nhưng bị loại khỏi `v_adjustment_current` và mọi phép cộng tiền |

`trip_fee_line` có partial index `(trip_id) WHERE voided_by_event IS NULL` và `(legacy_row_id) WHERE voided_by_event IS NULL`. Danh mục sửa bằng khóa `FOR UPDATE` trên `fee_type`; thêm loại dùng một advisory lock cố định. `set_book_fee_columns` vẫn ghi event của khách.

Danh mục khởi tạo theo thứ tự Neo, Điện, Ghép, Bảo hiểm, Kiểm định, Health cert (dương, service). Loại hệ thống Khác nhận dương; Giảm trừ chỉ nhận âm; Phụ phí ban đầu nhận khác 0 nhưng chỉ migration được tạo mới. Loại inactive không nhận dòng mới.

- `add_trip_fees(customer_id, expected_version, idempotency_key, targets jsonb, fee_type_id, amount_vnd, note)`: 1..N target cùng khách, atomic; một target tháng khóa trả `MONTH_LOCKED` cho cả lệnh; một event gồm mảng target; một lần phân bổ.
- `set_trip_fee_type(customer_id, expected_version, idempotency_key, target jsonb, fee_type_id, amount_vnd bigint NULL)`: void mọi dòng hiệu lực cùng loại, thêm tối đa một dòng; NULL là xóa trắng ô.
- `replace_trip_fee(customer_id, expected_version, idempotency_key, fee_line_id, fee_type_id, amount_vnd, note)`: void cũ, thêm mới trong cùng lệnh/event.
- `void_trip_fee(customer_id, expected_version, idempotency_key, fee_line_id)`: void một dòng.
- Cờ `trip_fee_flag` và `clear_trip_fee_flag` dời sang spec nhập bảng PS; giai đoạn 1 chưa có nguồn tạo cờ.
- Danh mục: `add_fee_type(idempotency_key, name, kind)`, `rename_fee_type(idempotency_key, fee_type_id, name)`, `set_fee_type_kind(idempotency_key, fee_type_id, kind)`, `set_fee_type_active(idempotency_key, fee_type_id, active)`; dùng khóa và vết toàn cục, không `customer_id`/`expected_version` của sổ.
- `set_book_fee_columns(customer_id, expected_version, idempotency_key, fee_type_ids jsonb)`: 0..3 ID có thứ tự, không đổi tiền nhưng ghi event.
- `v_trip_current.fee` = tổng dòng còn hiệu lực, NULL nếu không có dòng. Có đơn giá + fee NULL tính 0 theo V7-BE; thiếu đơn giá ngoài số dư; dòng phí lẻ không container lấy tổng dòng.
- `paste_trips`: mỗi hàng `fees: [amount_vnd,...]`; dương → Khác, âm → Giảm trừ; `other_fee_vnd` cũ coi như một ô. Chuyến mới dán tháng khóa là ngoại lệ duy nhất.
- `get_ledger`: thêm `fee_lines`, `fee_columns`; route danh mục riêng. `delete_trip`/`delete_legacy_trip` chụp dòng phí trong event trước khi xóa.

HTTP: POST `/api/v7/trips/fees/add`, `/fees/set`, `/fees/replace`, `/fees/void`; GET/POST `/api/v7/fee-types`; POST `/api/v7/fee-types/update`, `/api/v7/books/fee-columns`. Lỗi: `MONTH_LOCKED`, `FEE_AMOUNT_INVALID`, `FEE_SIGN_INVALID`, `FEE_TYPE_INACTIVE`, `FEE_TYPE_SYSTEM`, `FEE_TYPE_DUPLICATE`, `FEE_LINES_TYPED`, `FEE_COLUMNS_MAX`, `VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `TRIP_NOT_FOUND`, `LEGACY_NOT_FOUND`, `TRIP_PENDING_REVIEW`. Tiền trả dạng chuỗi hoặc NULL.

## Ba quyết định kỹ thuật

1. **Sổ gốc:** tiền hiện tại là `counted_vnd` của ô TOTAL, không phải đơn giá + phí. Migration chỉ tạo dòng Phụ phí ban đầu để xem; không ghi `legacy_trip_rev`, không ghi adjustment, không đổi `counted_vnd`. Mỗi lệnh fee trên legacy đi qua `_change_legacy`: tính lại `counted_vnd` theo đơn giá + tổng dòng, ghi revision và adjustment phần chênh, event có counted trước/sau. `display.fee_vnd` chỉ parse số dương; phí âm thành NULL, không tạo dòng. Báo cáo migration chỉ ghi ID và số đếm, lưu ngoài repo; phải đọc trước gate deploy.
2. **Lệnh cũ:** giữ chữ ký để không phá caller, nhưng tham số là **tổng phí chuyến**. Nếu target chỉ có dòng Khác/Giảm trừ/Phụ phí ban đầu hoặc không có dòng, bỏ hết các dòng đó rồi ghi một dòng theo dấu (`X>0` Khác, `X<0` Giảm trừ, `X=0/NULL` không dòng). Chỉ khi có dòng loại khác ngoài ba loại này mới từ chối `FEE_LINES_TYPED` với thông báo sửa trong khung chi tiết; price queue xếp `MANUAL`. Đường tương thích nhận số âm. Không tiếp tục ghi phí mới vào revision/adjustment một số. Snapshot Sheet giai đoạn 1 chỉ có tổng: ghi đúng một dòng theo dấu tổng, không giả tách các ô.
3. **Nguồn phí dùng chung:** tạo `v_trip_fee(trip_id, fee_vnd)` (NULL khi không có dòng) và nguồn legacy tương ứng. `v_outstanding_month`, `adjust_trip`, `delete_trip`, `get_ledger`, `get_dashboard`, `get_receivables_*`, các định nghĩa hàm từng đến từ migration dashboard/receivables, `web/v7_price_queue.py` và `tools/v7_price_match.py` đều đọc nguồn này; không đọc trực tiếp `other_fee_vnd` để tính tiền sau migration. Migration mới thay định nghĩa hàm cuối, không sửa migration lịch sử. Adjustment phí đã gộp có `fee_absorbed=true` và bị loại khỏi `v_adjustment_current`; adjustment không có field giữ nguyên.
4. **Lịch sử:** một `event` cho cả lệnh áp lô, before/after chứa từng target, loại, số, ghi chú và `batch_count`; lịch sử mở được danh sách chuyến. Lệnh đơn một event.

## Migration và hoàn tác

Transaction, idempotent. Web dùng phí hiệu quả = revision mới nhất + adjustment phí; tạo dòng Phụ phí ban đầu nếu khác 0 rồi đánh dấu adjustment phí bằng `fee_absorbed=true`, để không cộng hai lần. Legacy chỉ tạo dòng để xem, không đổi tiền. Phí hiệu quả bằng 0 không tạo dòng; chuyến có đơn giá giữ tổng như NULL theo V7-BE. Dry-run đếm (a) dòng phí lẻ không container/không đơn giá có phí 0 và (b) chuyến có container, đơn giá hiện tại NULL nhưng có adjustment phí. Nếu có dòng ở một trong hai nhóm thì dừng hỏi trước khi hấp thụ adjustment hoặc áp migration; không tự đổi tổng. Kiểm trước/sau trên `v_outstanding_month` và tổng `get_ledger` theo khách/tháng tới từng đồng, thêm kiểm từng target; chạy lần hai không đổi. Rollback chỉ sau khi gộp dòng và kiểm tổng từng target/tháng/khách; không rollback nếu đã phân loại sau migration.

## Bảng chuyển đổi nguồn đọc

| Nơi đọc cũ | Sau migration |
| --- | --- |
| `v_trip_current`, `v_outstanding_month` | `v_trip_fee` + adjustment chưa hấp thụ; fee NULL vẫn theo V7-BE |
| `adjust_trip`, `delete_trip` | tổng `v_trip_fee`; snapshot ghi các dòng và counted trước/sau |
| `get_ledger`, `get_dashboard`, `get_receivables_*` | view/hàm phí dùng chung, không `other_fee_vnd` |
| định nghĩa hàm dashboard/receivables từ migration cũ | migration mới thay định nghĩa cuối để gọi nguồn phí chung |
| `web/v7_price_queue.py`, `tools/v7_price_match.py` | tổng dòng phí; snapshot chỉ có tổng thì ghi một dòng theo dấu |

Chuyến `pending_review` bị chặn như lệnh sửa giá hiện hành (`TRIP_PENDING_REVIEW`), trừ dòng fee đi kèm `paste_trips`. `replace_trip_fee` được giữ loại Phụ phí ban đầu khi chỉ sửa số/ghi chú; không chọn loại này cho dòng mới hoặc đổi loại khác sang nó. `add_trip_fees` có thể gồm legacy; mỗi legacy vẫn ghi revision/adjustment riêng cùng event.

## Nguồn quyết định

[`PHU-PHI-01`](../docs/decisions.md#phu-phi-01), [`V7-BE`](../docs/decisions.md#v7-be), [`V7-SO`](../docs/decisions.md#v7-so), [`NHAP-SHEET-01`](../docs/decisions.md#nhap-sheet-01) (7), [`SO-GON-01`](../docs/decisions.md#so-gon-01), [khóa tháng 24/10](../docs/decisions.md#cập-nhật-khóa-tháng-24102026), [spec tổng](v7-phu-phi-nhieu-loai.md).

## Hành vi và bất biến

VND bigint nguyên; NULL khác 0 trừ V7-BE. Số 0, sai dấu, overflow, kiểu không phải số, loại hệ thống cấm chọn bị từ chối. Dòng chỉ thêm/void. Không đổi opening, khóa tháng, FIFO, NEWTRIP-01. Role app chỉ EXECUTE hàm, không DML bảng mới. Không chạy DDL trên DB thật.

## Tách PR

- PR-A: schema, migration, nguồn phí dùng chung, loại adjustment đã hấp thụ, mọi chỗ đọc tiền, lệnh cũ, price queue/match.
- PR-B: lệnh add/set/replace/void, danh mục, cột riêng, HTTP và test tương ứng.
- PR-B chờ PR-A pass harness và review. Mỗi PR có diff/nghiệm thu riêng.

## Tiêu chí nghiệm thu

- [ ] Harness PostgreSQL dùng một lần: migration giữ tổng từng target/tháng/khách; NULL không thành 0; lần hai bất biến; rollback có kiểm tổng.
- [ ] `v_outstanding_month` và tổng `get_ledger` từng khách/tháng bằng nhau trước/sau tới từng đồng; adjustment phí đã hấp thụ không còn trong `v_adjustment_current`.
- [ ] Chuyến có adjustment phí cũ + sửa đơn giá sau migration không cộng trùng.
- [ ] Legacy TOTAL khác đơn giá + phí: migration không đổi tổng; thêm phí tạo `counted_vnd` mới và adjustment chênh đúng.
- [ ] Lệnh cũ trên chuyến đã tách loại trả `FEE_LINES_TYPED`; price queue xếp `MANUAL`; số âm ghi Giảm trừ.
- [ ] Price queue ghi hai tổng phí âm khác nhau liên tiếp trên cùng chuyến: lần hai thay dòng Giảm trừ, không trả `FEE_LINES_TYPED` hoặc `MANUAL`.
- [ ] Dry-run đếm dòng phí lẻ 0; nếu có dòng thì dừng trước áp dụng.
- [ ] Dry-run đếm chuyến có adjustment phí nhưng đơn giá hiện tại NULL và có container; nếu có thì dừng trước hấp thụ.
- [ ] Harness quét `pg_proc.prosrc` và định nghĩa view sau migration: ngoài đường tương thích/migration, không hàm/view nào tính tiền từ `other_fee_vnd` cũ.
- [ ] Danh mục: replay cùng `idempotency_key` trả kết quả cũ; cùng key khác payload bị từ chối. Dòng phí có `customer_id` lệch target bị từ chối.
- [ ] Ba ca V7-BE so với `tripAmount` trong `so-khach-v7-model.js`.
- [ ] Áp 20 chuyến một lệnh, một lần phân bổ; một tháng khóa → không dòng nào vào.
- [ ] Từ chối 0, sai dấu, overflow, loại hệ thống, replay cùng key khác payload; khóa/version/actor.
- [ ] Paste dương/âm, tham số cũ, legacy giữ opening, delete chụp dòng, queue 3 nhánh, quyền app EXECUTE.
- [ ] `npm run check`; `node scripts/check-secrets.js`; CI PR xanh. Local/CI không chứng minh `hao`.

## Phạm vi agent

- Agent: codex. Mockup: miễn vì không sửa UI. Review: opus.
- Được sửa sau review: `cong-no-web-handoff/tools/v7_backend_functions.sql`, `specs/v7-backend/schema-draft.sql`, một migration mới trong `cong-no-web-handoff/tools/migrations/`, `cong-no-web-handoff/web/v7_ledger_api.py`, `cong-no-web-handoff/web/v7_price_queue.py`, `cong-no-web-handoff/tools/v7_price_match.py`, `cong-no-web-handoff/tools/test_pg_v7_backend.py`, test Python liên quan, runbook nếu migration cần. Migration lịch sử chỉ đọc. Spec này là file duy nhất sửa trong PR spec.
- Ngân sách diff: spec ≤ 250 dòng; PR-A và PR-B mỗi PR ≤ 1000 dòng, vượt thì review scope trước.
- Lệnh kiểm: `npm run check`; `node scripts/check-secrets.js`; DB harness PostgreSQL dùng một lần theo runner/harness trong repo và CI, không chạy Docker trực tiếp từ agent.
- Cấm: UI, PS, dependency/framework mới, DB thật/`hao`, thay opening/lock/FIFO/NEWTRIP-01, dữ liệu thật trong repo.

## Bằng chứng

Chưa code; chưa chạy harness.

## Câu hỏi mở

- Không còn câu hỏi chặn PR-A theo review opus. Báo cáo ID legacy không tách được phí lưu ngoài repo; người chạy phải đọc báo cáo trước gate deploy trên `hao`.
