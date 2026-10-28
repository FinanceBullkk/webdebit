# V7 — phụ phí nhiều loại: backend và migration

Trạng thái: ĐỀ XUẤT — chờ Claude (opus) review. Chưa code hoặc triển khai.

## Đầu ra

Lõi PostgreSQL/API lưu nhiều dòng phụ phí theo chuyến hoặc dòng sổ gốc, danh mục và tối đa ba cột riêng theo sổ. Migration chuyển phí cũ, giữ tổng tiền từng dòng/tháng/khách. Không làm UI hoặc đọc bảng PS.

## Đối chiếu dữ liệu và code hiện có

- Chuyến web: phí nằm ở revision mới nhất của `trip_price_rev.other_fee_vnd` cộng `adjustment(field='other_fee_vnd')`. `delete_trip` đang chụp phí hiệu quả theo công thức đó.
- Dòng sổ gốc: `_legacy_current` đọc `legacy_trip_rev.other_fee_vnd` nếu có revision, nếu không parse `legacy_row.display.fee_vnd`. `source_total_vnd` là ô tổng, không chứng minh phần phí. `_change_legacy` ghi chênh lệch vào `adjustment`; opening không đổi.
- `v7_price_queue.py` hiện so phí một số, coi phí âm là `MANUAL`. `v7_ledger_api.py` và test gọi chữ ký cũ của `edit_trip_price`, `adjust_trip`, `edit_legacy_trip`.

## Giao tiếp frontend–backend

Mọi hàm ghi dùng `customer_id`, `expected_version`, `idempotency_key`, khóa hàng khách, actor từ `_actor()`, event trước → sau và phân bổ lại tối đa một lần.

| Bảng | Hợp đồng |
| --- | --- |
| `fee_type` | `id`, `name` unique theo `lower(btrim(name))`, `kind` service/pass_through, `sign` positive/negative/any, `system_key`, `active`, `sort` |
| `book_fee_column` | `customer_id`, `fee_type_id`, `position` 1..3; unique cả hai chiều |
| `trip_fee_line` | `id`, `customer_id`, đúng một `trip_id`/`legacy_row_id`, `fee_type_id`, `amount_vnd bigint` khác 0, `note`, `created_by_event`, `voided_by_event` NULL; chỉ thêm |
| `trip_fee_flag` | đúng một target, `fee_type_id`, `source`, `created_by_event`, `cleared_by_event`, `clear_reason`; không phải tiền |

Danh mục khởi tạo theo thứ tự Neo, Điện, Ghép, Bảo hiểm, Kiểm định, Health cert (dương, service). Loại hệ thống Khác nhận dương; Giảm trừ chỉ nhận âm; Phụ phí ban đầu nhận khác 0 nhưng chỉ migration được tạo mới. Loại inactive không nhận dòng mới.

- `add_trip_fees(customer_id, expected_version, idempotency_key, targets jsonb, fee_type_id, amount_vnd, note)`: 1..N target cùng khách, atomic; một target tháng khóa trả `MONTH_LOCKED` cho cả lệnh; một event gồm mảng target; một lần phân bổ.
- `set_trip_fee_type(customer_id, expected_version, idempotency_key, target jsonb, fee_type_id, amount_vnd bigint NULL)`: void mọi dòng hiệu lực cùng loại, thêm tối đa một dòng; NULL là xóa trắng ô.
- `replace_trip_fee(customer_id, expected_version, idempotency_key, fee_line_id, fee_type_id, amount_vnd, note)`: void cũ, thêm mới trong cùng lệnh/event.
- `void_trip_fee(customer_id, expected_version, idempotency_key, fee_line_id)`: void một dòng.
- `clear_trip_fee_flag(customer_id, expected_version, idempotency_key, flag_id)`: clear cờ và ghi event; ghi dòng đúng loại tự clear cờ.
- Danh mục: `add_fee_type(name, kind)`, `rename_fee_type(fee_type_id, name)`, `set_fee_type_kind(fee_type_id, kind)`, `set_fee_type_active(fee_type_id, active)`.
- `set_book_fee_columns(customer_id, expected_version, idempotency_key, fee_type_ids jsonb)`: 0..3 ID có thứ tự, không đổi tiền nhưng ghi event.
- `v_trip_current.fee` = tổng dòng còn hiệu lực, NULL nếu không có dòng. Có đơn giá + fee NULL tính 0 theo V7-BE; thiếu đơn giá ngoài số dư; dòng phí lẻ không container lấy tổng dòng.
- `paste_trips`: mỗi hàng `fees: [amount_vnd,...]`; dương → Khác, âm → Giảm trừ; `other_fee_vnd` cũ coi như một ô. Chuyến mới dán tháng khóa là ngoại lệ duy nhất.
- `get_ledger`: thêm `fee_lines`, `fee_flags`, `fee_columns`; route danh mục riêng. `delete_trip`/`delete_legacy_trip` chụp dòng phí trong event trước khi xóa.

HTTP: POST `/api/v7/trips/fees/add`, `/fees/set`, `/fees/replace`, `/fees/void`, `/fees/flags/clear`; GET/POST `/api/v7/fee-types`; POST `/api/v7/fee-types/update`, `/api/v7/books/fee-columns`. Lỗi: `MONTH_LOCKED`, `FEE_AMOUNT_INVALID`, `FEE_SIGN_INVALID`, `FEE_TYPE_INACTIVE`, `FEE_TYPE_SYSTEM`, `FEE_TYPE_DUPLICATE`, `FEE_COLUMNS_MAX`, `VERSION_CONFLICT`, `IDEMPOTENCY_CONFLICT`, `TRIP_NOT_FOUND`, `LEGACY_NOT_FOUND`. Tiền trả dạng chuỗi hoặc NULL.

## Ba quyết định kỹ thuật

1. **Sổ gốc:** phí ở `legacy_trip_rev.other_fee_vnd` hoặc `legacy_row.display.fee_vnd`. Dòng không tách được giữ NULL, không tạo dòng phí, không đoán từ `source_total_vnd`, ghi ID vào báo cáo migration để kiểm thủ công. Migration fail nếu tổng tiền thay đổi. Không viết lại opening.
2. **Lệnh cũ:** giữ chữ ký để không phá `v7_price_queue` và test, nhưng dịch phí sang đặt dòng Khác trong cùng command/event; không tiếp tục ghi phí mới vào revision/adjustment một số. `edit_trip_price` vẫn sửa đơn giá; `adjust_trip(field='other_fee_vnd')` và `edit_legacy_trip(field='other_fee_vnd')` đặt Khác. Queue so tổng dòng: bằng nhau → không ghi; web chưa có dòng → ghi theo dấu; lệch và web đã có dòng → `MANUAL`; phí âm không tự MANUAL.
3. **Lịch sử:** một `event` cho cả lệnh áp lô, before/after chứa từng target, loại, số, ghi chú và `batch_count`; lịch sử mở được danh sách chuyến. Lệnh đơn một event.

## Migration và hoàn tác

Transaction, idempotent. Web dùng phí hiệu quả = revision mới nhất + adjustment phí theo công thức hàm hiện hành. Legacy dùng `_legacy_current.other_fee_vnd`. Khác NULL tạo đúng một dòng Phụ phí ban đầu; NULL không tạo. Kiểm tổng từng trip, legacy row, tháng, khách trước/sau tới từng đồng; chạy lần hai không đổi. Nếu phí hiệu quả bằng 0 thì dừng migration vì `amount_vnd <> 0`, không tự tạo 0. Rollback chỉ sau khi gộp dòng và kiểm tổng từng target/tháng/khách; không rollback nếu đã phân loại sau migration.

## Nguồn quyết định

[`PHU-PHI-01`](../docs/decisions.md#phu-phi-01), [`V7-BE`](../docs/decisions.md#v7-be), [`V7-SO`](../docs/decisions.md#v7-so), [`NHAP-SHEET-01`](../docs/decisions.md#nhap-sheet-01) (7), [`SO-GON-01`](../docs/decisions.md#so-gon-01), [khóa tháng 24/10](../docs/decisions.md#cập-nhật-khóa-tháng-24102026), [spec tổng](v7-phu-phi-nhieu-loai.md).

## Hành vi và bất biến

VND bigint nguyên; NULL khác 0 trừ V7-BE. Số 0, sai dấu, overflow, kiểu không phải số, loại hệ thống cấm chọn bị từ chối. Dòng chỉ thêm/void. Không đổi opening, khóa tháng, FIFO, NEWTRIP-01. Role app chỉ EXECUTE hàm, không DML bảng mới. Không chạy DDL trên DB thật.

## Tiêu chí nghiệm thu

- [ ] Harness PostgreSQL dùng một lần: migration giữ tổng từng target/tháng/khách; NULL không thành 0; lần hai bất biến; rollback có kiểm tổng.
- [ ] Ba ca V7-BE so với `tripAmount` trong `so-khach-v7-model.js`.
- [ ] Áp 20 chuyến một lệnh, một lần phân bổ; một tháng khóa → không dòng nào vào.
- [ ] Từ chối 0, sai dấu, overflow, loại hệ thống, replay cùng key khác payload; khóa/version/actor.
- [ ] Paste dương/âm, tham số cũ, legacy giữ opening, delete chụp dòng, queue 3 nhánh, quyền app EXECUTE.
- [ ] `npm run check`; `node scripts/check-secrets.js`; CI PR xanh. Local/CI không chứng minh `hao`.

## Phạm vi agent

- Agent: codex. Mockup: miễn vì không sửa UI. Review: opus.
- Được sửa sau review: `cong-no-web-handoff/tools/v7_backend_functions.sql`, `specs/v7-backend/schema-draft.sql`, một migration mới trong `cong-no-web-handoff/tools/migrations/`, `cong-no-web-handoff/web/v7_ledger_api.py`, `cong-no-web-handoff/web/v7_price_queue.py`, `cong-no-web-handoff/tools/test_pg_v7_backend.py`, test Python liên quan, runbook nếu migration cần. Spec này là file duy nhất sửa trong PR spec.
- Ngân sách diff: spec ≤ 250 dòng; code/migration ≤ 1800 dòng.
- Lệnh kiểm: `npm run check`; `node scripts/check-secrets.js`; DB harness qua `D:\webdebit\worktrees\_logs\tools\codex-check-loop.ps1` hoặc orchestrator ngoài, không chạy Docker trực tiếp.
- Cấm: UI, PS, dependency/framework mới, DB thật/`hao`, thay opening/lock/FIFO/NEWTRIP-01, dữ liệu thật trong repo.

## Bằng chứng

Chưa code; chưa chạy harness.

## Câu hỏi mở

- Danh mục dùng chung nhưng event cần `customer_id`: chọn sổ khóa và nơi hiển thị Lịch sử danh mục?
- Phí hiệu quả bằng 0 dù nguồn có số: chính sách trước migration vì dòng mới cấm 0.
- Legacy có `source_total_vnd` nhưng không tách `fee_vnd`: báo cáo/flag và gate deploy cụ thể.
- Price snapshot hiện chỉ có tổng phí, không từng ô: mở rộng reader hay dùng một dòng tổng theo dấu giai đoạn 1?
