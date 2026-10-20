# Kết nối giao diện V7 với HTTP API — bản thử có API

**20/10/2026 — người dùng cho phép nối giao diện V7 vào backend thử.** Đã viết trong worktree này, **chưa commit**: trang `preview/so-khach-v7-live.html`, client `preview/so-khach-v7-api.js`, renderer chung trong `preview/so-khach-v7-ui.js` và allowlist file tĩnh ở `web/v7_ledger_api.py`, cùng origin localhost cổng thử 8780. Bản fixture trong tab vẫn dùng model và handler cũ; trang live chỉ nhận số GET. POST chỉ gửi ý định, version và key; retry kết quả chưa rõ giữ nguyên key. Cờ nguồn chỉ tô màu kèm chữ, không chặn nếu khách active. `legacy_rows` chỉ tham khảo.

**ĐÃ KIỂM CHỨNG (Claude, 20/10/2026, sau vòng sửa review; chỉ dữ liệu giả):**
- Node `node --test --test-isolation=none preview/test-so-khach-v7-model.js preview/test-so-khach-v7-api.js`: 29/29 đạt.
- Python `-m unittest tests.test_v7_ledger_api`: 6 đạt, 1 bỏ qua (case Docker giả cần `V7_API_DOCKER_TEST=1`).
- Harness `tools/test_pg_v7_backend.py` trên PostgreSQL 18.6, container dùng một lần `--network none`: SCHEMA 10/10, BEHAVIOR 20/20, 2 case `SKIPPED_OPEN`; dọn đúng container/volume. Case 7.08 có thêm khẳng định cho `today_month`/`month_locks`.
- Trình duyệt (browser pane, 1280×720) với demo dữ liệu giả của `v7_live_demo.py`: tên khách, nợ các tháng trước, phát sinh, đã thu từng tháng vẽ từ GET và **giữ nguyên sau khi bấm Lịch sử**; mở khóa tháng 2 (không có chuyến) hiện 🔓 và ô dán; ghi thu 100.000 ở tháng hiện tại trừ vào tháng nợ cũ nhất, tổng nợ giảm đúng.
- Chưa kiểm: khối tháng hiện tại khi khách chưa có dữ liệu tháng này chỉ được kiểm bằng test Node (demo giả đều có chuyến tháng 10). Chưa có DB thật, dữ liệu thật hay nghiệm thu ghi tiền.

**Hợp đồng GET bổ sung (20/10/2026):** mỗi tháng có `prior_months_vnd`, `charges_vnd`, `received_vnd`, `outstanding_vnd`, `end_of_month_vnd`; gốc có `today_month` (tháng hiện tại theo giờ VN do server tính) và `month_locks` (cờ khóa đã ghi của mọi tháng, kể cả tháng không chuyến; thiếu hàng thì chỉ `today_month` mở). Giao diện luôn có khối tháng hiện tại để ghi thu/dán chuyến, kể cả khi GET chưa có tháng đó (ô tổng hiện `–` vì server chưa có số). Tên khách lấy từ `/api/v7/customers` và vẽ lại qua renderer, không chép đè DOM.

**Kiểm sau vòng 3 (Claude, 20/10/2026, chỉ dữ liệu giả):** Node 36/36 đạt; Python 10 đạt, 1 bỏ qua; harness PostgreSQL 18.6 container dùng một lần: SCHEMA 10/10, BEHAVIOR 24/24 (gồm 7.19–7.22 đã thực thi), 2 `SKIPPED_OPEN`, dọn sạch. Công thức Nợ trước + Phát sinh − Đã thu = Còn nợ được kiểm ở mọi lần `get_ledger` trong harness. Trình duyệt 1280×720 với demo giả: bốn tháng khách nhiều kỳ đều khớp công thức trên màn hình; hủy phiếu giữ dòng, gạch ngang, `ĐÃ HỦY`, không mở lại hộp hủy, không sửa được ngày phiếu đã hủy; ngày thu 21/10/2026 bị từ chối với câu “Ngày trả không được sau hôm nay.”, tổng nợ không đổi; khóa tháng 10 rồi sửa đơn giá (+50.000, có ghi chú) và phụ phí (+20.000) sinh hai dòng điều chỉnh, lần sau tính từ thành tiền hiện hành; Lịch sử hiện giờ VN, người, thao tác tiếng Việt, trước → sau, ghi chú/lý do.

**CÒN MỞ sau vòng 4:** (a)–(c) đã sửa và Claude đã kiểm harness + trình duyệt (mục “Bằng chứng thực chạy vòng 4”); phần V7 nối giao diện đã commit `6fe342a`. Bản sao dữ liệu thật: xem mục cuối. Chưa nghiệm thu nghiệp vụ; không suy kết quả dữ liệu giả thành xác nhận dữ liệu thật.

## Vòng 4 — 20/10/2026, mã chưa commit

Phạm vi đúng 6 file cho phép; giữ mọi thay đổi đang có. `git status` đầu vòng xác nhận nhánh `codex/v7-opening-read`, UI sửa dở cùng các file vòng trước chưa theo dõi. Hash UI/SQL đầu vòng khớp vòng 3. Không commit/stash/reset/push, không chạy Docker, không chạm hao/Sheet/captures/dữ liệu thật hay hai công cụ nạp/đối soát bản sao. Sửa hiển thị nhỏ, không đổi luồng; không cần mockup mới.

| Điểm | ĐÃ SỬA (file, test) | KHÔNG LÀM (lý do) / CÒN MỞ |
| --- | --- | --- |
| 1 — (a) | `preview/so-khach-v7-ui.js`, chỉ `initLive()`: Lịch sử dán lô gọi ngày là **Ngày chuyến**; khi cùng chuyến có cả `date`/`event_date` chỉ hiện `event_date`. Phiếu vẫn **Ngày trả**. Node `paste history labels one trip date; receipt history keeps payment date` **đỏ trước, xanh sau**, kiểm cả chuyến chỉ có một trong hai trường ngày. | Không kiểm trình duyệt theo phân công; Claude kiểm phần hiển thị. Không bỏ phần sửa nào. |
| 2 — (b) | Cùng file UI: ghép từng cặp trước → sau, ví dụ **Đơn giá: 300.000 → 350.000 · Thành tiền: 300.000 → 350.000 · Điều chỉnh: +50.000**. Phụ phí tương tự; sửa tổng trực tiếp không có phần trường. Node `trip adjustment history pairs field and amount before to after with signed server delta` **đỏ trước, xanh sau**; có delta âm, tổng trực tiếp, tiền trên 2^53, thiếu số và delta cố ý khác hiệu hai tổng để chứng minh UI chỉ định dạng số server. | Không tính tiền trong trình duyệt; không kiểm trình duyệt theo phân công. Không bỏ phần sửa nào. |
| 3 — (c) | `specs/v7-backend/schema-draft.sql`: thêm `adjustment.field text` nullable, CHECK chỉ `unit_price_vnd`/`other_fee_vnd`; `new_value_vnd bigint` nullable, CHECK ≥ 0; CHECK hai cột cùng NULL hoặc cùng có giá trị. `tools/v7_backend_functions.sql`: `adjust_trip` ghi hai cột, đọc phụ phí từ adjustment mới nhất của đúng khách/chuyến có `field='other_fee_vnd'`, `created_by_event` sau revision giá mới nhất; không đọc event để tính. Điều chỉnh tháng/tổng trực tiếp giữ hai cột NULL; event before/after giữ nguyên. Node `adjust_trip SQL stores field intent in adjustment; fee source is table not audit` **đỏ trước, xanh sau — chỉ kiểm tĩnh nguồn SQL**. `tools/test_pg_v7_backend.py` thêm **7.23**, giữ nguyên 7.19–7.22. | **chưa chạy PostgreSQL**: không có bằng chứng hành vi DB đỏ/xanh vòng 4. Case 7.23 chờ Claude chạy; kiểm tĩnh/py_compile không thay thực thi SQL. Không đổi model tiền/FIFO. |

Tên file UI/test/tools trong bảng tính từ `cong-no-web-handoff/`; đường dẫn `specs/` tính từ gốc worktree. Ba test Node mới nằm trong `preview/test-so-khach-v7-api.js`.

**Case PostgreSQL 7.23 đã thêm, chưa thực thi:** kiểm hai cột được ghi đúng theo thứ tự đơn giá → phụ phí → đơn giá (120, 7, 130), delta +20, +7, +10 và tổng 137; giữ giá gốc 100/phụ phí NULL. Owner chỉ trong DB giả dùng một lần tắt trigger immutable, sửa `event.after.new_value_vnd` của lần phụ phí thành 999, bật lại trigger trong cùng transaction; lần chỉnh đơn giá sau vẫn phải +10. Kiểm hai cột NULL cho tổng trực tiếp/tháng, từ chối thiếu một cột/trường lạ/giá trị âm, nhận phụ phí 0. Thêm revision giá rồi chỉnh đơn giá để kiểm bỏ qua phụ phí ở adjustment trước revision đó. Không nới trigger/quyền ở mã ứng dụng.

### Bằng chứng thực chạy vòng 4

Chạy tại `cong-no-web-handoff/`:

```powershell
node --test --test-isolation=none preview/test-so-khach-v7-model.js preview/test-so-khach-v7-api.js
..\..\..\repo\.venv\Scripts\python.exe -m unittest tests.test_v7_ledger_api -v
..\..\..\repo\.venv\Scripts\python.exe tools/test_pg_v7_backend.py --list
..\..\..\repo\.venv\Scripts\python.exe -m py_compile tools/test_pg_v7_backend.py
node --check preview/so-khach-v7-ui.js
```

- Đầu vòng: Node **36/36 đạt**, Python **10 đạt + 1 bỏ qua**. Trước sửa nguồn, chạy riêng đúng ba test Node mới: **0 đạt, 3 fail**; lỗi đúng nhãn ngày trùng, chuỗi điều chỉnh và nguồn đọc `FROM sokhach.event`.
- Sau sửa: Node **39/39 đạt** (22 model + 17 API/UI, gồm 1 kiểm tĩnh SQL); Python **10 đạt + 1 bỏ qua** (case Docker). `--list` liệt kê **37 case: 10 SCHEMA, 25 BEHAVIOR, 2 SKIPPED_OPEN**, không phải 37 case đạt. `py_compile`, `node --check` và `git diff --check` đạt.
- Fixture qua cùng VM renderer giữ SHA-256 vòng 3: `58265f6d23ad38c4bc7654d8ff9295e5d35bbf78e0318b7c153e362b053e19c4` (test fixture xanh). Mã UI ngoài `initLive()` giữ nguyên; case/hàm kiểm 7.19–7.22 giữ nguyên. Chỉ 6 file cho phép đổi so đầu vòng; giữ file dirty/untracked khác.
- **Claude kiểm sau vòng 4 (20/10/2026, chỉ dữ liệu giả):** Node 39/39; Python 10 đạt, 1 bỏ qua; harness PostgreSQL 18.6 container dùng một lần **SCHEMA 10/10, BEHAVIOR 25/25** (gồm 7.23: sửa `event.after` thành 999 không đổi hiệu số lần chỉnh sau), 2 `SKIPPED_OPEN`, dọn sạch. Trình duyệt 1280×720 với demo giả: Lịch sử “Dán lô chuyến” ghi “Ngày chuyến”, không còn “Ngày trả”; “Ghi thu” vẫn ghi “Ngày trả”; khóa tháng 10, sửa đơn giá 300.000 → 350.000 rồi phụ phí → 20.000 hiện đúng hai mục “Đơn giá: 300.000 → 350.000 · Thành tiền: 300.000 → 350.000 · Điều chỉnh: +50.000” và “Phụ phí: 0 → 20.000 · Thành tiền: 350.000 → 370.000 · Điều chỉnh: +20.000”, tổng tháng 370.000. Chưa có xác nhận DB/live/dữ liệu thật.

Môi trường kiểm: Windows PowerShell, Python từ `D:\webdebit\repo\.venv\Scripts\python.exe`, worktree `D:\webdebit\worktrees\codex-v7-opening-read`; HEAD nền `e091d4a83cd315ccfecb5bfbd9e0f2dab1893b56` cộng mã chưa commit. SHA-256 toàn file vòng 4 (byte gốc, không chuẩn hóa xuống dòng):

- UI: `84255ae7dd4d1ba9de7c4d2ee9dfd95926de14ffac2681483ed617703902a450`.
- Test Node: `72965d59849c72233fcd41263ce5e10a0d00461d795638a7e91e18ecc5c03d3b`.
- Functions SQL: `d2bb3af501d400fce91951b51c16009e24b78afdd34b5de4be76c02edd328900`.
- Harness: `517d608929438fbc9fa320be9427db60b15115ac25c1ebfbb834185fc49fbfe0`.
- Schema: `4eaecbe45b85cc8fecbc1f209de4d6fd09baddbec3c0629af295f432d24c3349`.

## Vòng 3 — 20/10/2026, mã chưa commit

Phạm vi: đúng 8 file cho phép trong yêu cầu; mục 5–6 được giữ trong yêu cầu gửi. Giữ thay đổi vòng 2, không commit/stash/reset/push; không dùng cổng 8777, không chạy Docker, không chạm dữ liệu thật/hao/Sheet/captures hoặc công cụ nạp/đối soát bản sao. Chỉ sửa `initLive()` trong UI; đoạn fixture/renderer dùng chung bên ngoài hàm giữ nguyên. HEAD nền: `e091d4a83cd315ccfecb5bfbd9e0f2dab1893b56` cộng thay đổi chưa commit.

| Điểm | Trạng thái, file và hành vi | Test chứng minh / giới hạn |
| --- | --- | --- |
| 1 | **ĐÃ SỬA mã**: `tools/v7_backend_functions.sql`, `get_ledger.charges_vnd` cộng opening đúng khách/kỳ/cutover hiệu lực; giữ `outstanding_vnd`, `end_of_month_vnd`. | Python `test_get_opening_and_void_contract_sql` đỏ trên bản trước, xanh sau sửa: kiểm tĩnh SQL. Harness mới **7.19** có opening dương/âm, thu và điều chỉnh; helper `call(get_ledger)` kiểm công thức ở **mọi tháng GET** trong toàn bộ harness. **Chưa chạy PostgreSQL**. |
| 2 | **ĐÃ SỬA mã**: SQL trả `voided_by_event`; `preview/so-khach-v7-ui.js` giữ dòng hủy đúng tháng tại lúc hủy, ngày/tiền gạch ngang, chữ `ĐÃ HỦY`, không sửa/hủy lại; dòng vết đủ tiền/ngày phiếu/ngày hủy/lý do. Phân bổ cũ do phân bổ lại bị loại. | Node `void keeps only allocations superseded by void event, with struck date/money and dated trace` đỏ trước, xanh sau; kiểm cả bấm dòng đã hủy. Harness mới **7.22** đối chiếu GET sau phân bổ lại rồi hủy; **chưa chạy PostgreSQL**. |
| 3 | **ĐÃ SỬA mã**: UI dùng nhãn Việt, giờ VN `dd/mm/yyyy HH:mm`, người, trước → sau, ghi chú/lý do; duyệt whitelist trường trình bày, không in JSON/mã loại. SQL GET chuyển tiền trong snapshot giá sang chuỗi để giữ chính xác cả trên 2^53. | Node `history formats every SQL event kind, snapshots and VN timestamp; hides unknown codes` và `history presents actual nested price/paste/void snapshots and escapes notes` đỏ trước, xanh sau; có số lớn, ngày/tháng, snapshot lồng, escape ghi chú. Case 7.20 thêm kiểm chuỗi tiền giá trong GET, **chưa chạy PostgreSQL**. |
| 4 | **ĐÃ SỬA mã**: UI, `preview/so-khach-v7-api.js`, `web/v7_ledger_api.py`, SQL nhận trường/số mới/ghi chú tùy chọn; server tính hiệu số từ giá hiện hành. Giữ đường thành tiền cũ. Thiếu giá giữ lỗi tiếng Việt `TRIP_HAS_NO_PRICE`, không lấy 0. | Node `locked edit asks clicked field, sends note and field intent only`, Python `test_field_adjustment_boundary` đỏ trước, xanh sau. Harness mới **7.20**: đơn giá 100→120→130 cho +20,+10; phụ phí NULL→7→9 cho +7,+2; đổi đơn giá tiếp; giữ giá gốc/NULL, ghi chú, retry/key khác payload, thiếu giá, trường sai/âm/tràn, đường tổng cũ rồi quay lại trường. **Chưa chạy PostgreSQL**. |
| 5 | **ĐÃ SỬA mã**: SQL hai hàm thu đọc `clock_timestamp()` giờ VN sau khóa khách; API ánh xạ 422, client trả lỗi nghiệp vụ để UI hiện cạnh ô ngày khi ghi hoặc sửa phiếu. | Node `future receipt error appears beside date and releases pending command`, `saved receipt date shows future-date error in clicked cell`; Python `test_future_receipt_guards_and_error`: đỏ trước, xanh sau. Mapping Psql cũng được test với mã lỗi mới. Harness mới **7.21**: hôm nay hợp lệ, ngày mai bị từ chối khi ghi/sửa và GET/version không đổi; kiểm thứ tự khóa/đồng hồ. **Chưa chạy PostgreSQL**. |
| 6 | **ĐÃ SỬA mã**: API thêm CLI `--real-copy`, loại trừ `--demo`; chuyển cờ tới Handler. Banner đã có ở client, nay bật được từ CLI. | Python `test_real_copy_cli_and_demo_exclusion` đỏ trước (không nhận cờ), xanh sau, kiểm cả từ chối hai cờ trước khi tạo runner. Node `real copy banner uses exact warning from GET` kiểm chữ/hiện banner. Chỉ dùng mock, **không chạy bản sao dữ liệu thật**. |

Tên file trong bảng tính từ `cong-no-web-handoff/`. Các test Node nằm trong `preview/test-so-khach-v7-api.js`; test Python trong `tests/test_v7_ledger_api.py`; case PostgreSQL trong `tools/test_pg_v7_backend.py`. **KHÔNG LÀM:** chạy PostgreSQL/trình duyệt/live ở vòng này theo phân công trong yêu cầu; không có điểm 1–6 bị bỏ khỏi mã.

### Hợp đồng GET/POST bổ sung vòng 3

- GET `months[*].charges_vnd` gồm opening hiệu lực + phát sinh chuyến đã biết giá + điều chỉnh. `prior_months_vnd + charges_vnd − received_vnd = end_of_month_vnd`; số tiền đều chuỗi VND. Không cộng `legacy_rows` lần nữa.
- GET `receipts[*].voided_by_event`: ID sự kiện hủy hoặc NULL. Khi chưa hủy chỉ hiện allocation `superseded_by_event IS NULL`; khi hủy chỉ hiện allocation có `superseded_by_event = voided_by_event`. Dòng vết dùng đúng tập đó. GET `events[*].before/after.price` trả `unit_price_vnd`, `other_fee_vnd` dạng chuỗi hoặc NULL, kể cả event giá cũ lưu JSON số; không sửa event đã lưu.
- POST `/api/v7/trips/adjust`: common fields như trước + `trip_id`, `field` (`unit_price_vnd` hoặc `other_fee_vnd`), `new_value_vnd` (chuỗi VND nguyên không âm), `note` tùy chọn. Không gửi `new_amount_vnd` cùng ý định theo trường. Đường cũ `trip_id` + `new_amount_vnd` + `note` vẫn nhận. Hàm SQL thêm hai tham số mặc định NULL ở cuối, không overload; 6 đối số cũ vẫn gọi được, payload idempotency cũ giữ nguyên. `field`/`new_value_vnd` được ghi vào before/after event cùng tổng và delta. **Vòng 4:** hai giá trị còn được lưu vào cột nullable của `adjustment`; server đọc phụ phí hiệu lực từ dòng adjustment của chuyến có `field='other_fee_vnd'` sau revision giá gần nhất, lấy mới nhất theo `created_by_event`, không lấy tiền từ event; phần đơn giá hiệu lực là tổng hiện hành trừ phụ phí hiệu lực. Không sửa giá gốc, không đổi FIFO, không phân bổ lại opening/lịch sử.
- Thiếu đơn giá của chuyến bình thường: `TRIP_HAS_NO_PRICE`, HTTP 422, “Chuyến chưa có giá.”. Phụ phí NULL của chuyến đã có giá tính 0 nhưng lưu NULL. Ý định sai trường/thiếu số/trộn hai dạng bị API từ chối 422 trước runner; số tiền vẫn kiểm chuỗi nguyên/giới hạn bigint.
- POST `/api/v7/receipts` và `/api/v7/receipts/meta`: ngày sau hôm nay giờ VN trả `FUTURE_RECEIPT_DATE`, HTTP **422**, “Ngày trả không được sau hôm nay.”. Mã lỗi duy nhất thêm ở vòng này. Giao diện giữ ô nhập và đặt lỗi cạnh ngày; lệnh lỗi nghiệp vụ giải phóng pending. Retry chưa rõ kết quả vẫn dùng key/payload cũ.
- CLI `--real-copy`: GET `real_copy: true`, banner **“Dữ liệu thật · bản sao cô lập, chưa phải prod”**. `--real-copy --demo` bị argparse từ chối. Cờ không mở thêm quyền kết nối DB, không bỏ kiểm container cô lập.

### Nhãn Lịch sử

Đã liệt kê cả **9 kind các hàm SQL hiện ghi**, test tự đối chiếu danh sách INSERT với bảng nhãn:

| kind | Nhãn |
| --- | --- |
| `paste` | Dán lô chuyến |
| `price_edit` | Sửa giá |
| `adjust_trip` | Điều chỉnh chuyến |
| `adjust_month` | Điều chỉnh cả tháng |
| `receipt` | Ghi thu |
| `receipt_edit` | Sửa ngày/hình thức phiếu |
| `void` | Hủy phiếu |
| `reallocation` | Phân bổ lại |
| `import` | Nhập số dư đầu |

Kind chưa có hàm ghi như `customer_attr` (mới có trong schema đề xuất) hoặc kind lạ: **Thao tác khác**, không lộ mã. Trước → sau chỉ định dạng trường đã biết trong snapshot, không tính tiền; thiếu dữ liệu hiện “Chưa có”/“–”. Mở/khóa tháng tiếp tục không tạo event.

### Bằng chứng thực chạy vòng 3

Chạy từ `cong-no-web-handoff/` trong worktree này:

```powershell
node --test --test-isolation=none preview/test-so-khach-v7-model.js preview/test-so-khach-v7-api.js
..\..\..\repo\.venv\Scripts\python.exe -m unittest tests.test_v7_ledger_api -v
..\..\..\repo\.venv\Scripts\python.exe tools/test_pg_v7_backend.py --list
..\..\..\repo\.venv\Scripts\python.exe -m py_compile web/v7_ledger_api.py tests/test_v7_ledger_api.py tools/test_pg_v7_backend.py
```

- Node **36/36 đạt** (22 model cũ + 14 API/UI); Python **10 đạt, 1 bỏ qua** (Docker). `--list` liệt kê **36 case: 10 SCHEMA, 24 BEHAVIOR, 2 SKIPPED_OPEN**; chỉ liệt kê, không phải 36 case đạt. `py_compile` đạt. **Chưa chạy PostgreSQL**; py_compile không kiểm cú pháp/hành vi SQL. Claude sẽ chạy harness thật và kiểm trình duyệt theo yêu cầu người dùng.
- Đã chạy bộ test mới với nguồn trước vòng 3 trong thư mục tạm riêng: Node 30 đạt, **6 fail**; Python 6 đạt, **2 fail + 2 error**, 1 bỏ qua. Đỏ đúng các test mô tả ở bảng; giữ checkout hiện tại nguyên trạng trong phép thử. Với điểm 1, bằng chứng đỏ/xanh hiện chỉ là kiểm hợp đồng SQL tĩnh; case tiền trên PostgreSQL chưa thực thi nên chưa có bằng chứng hành vi đỏ/xanh DB.
- Fixture HTML đầu trang so hash SHA-256 trước/sau qua cùng VM renderer: `58265f6d23ad38c4bc7654d8ff9295e5d35bbf78e0318b7c153e362b053e19c4`; assertion nằm trong test fixture. Đối chiếu nguồn xác nhận toàn bộ code ngoài `initLive()` không đổi so đầu vòng. Chưa chụp/kiểm bố cục browser vòng 3.
- `node --check` cho UI/client và `git diff --check` đạt. Ruff scoped 3 file Python báo **10 lỗi đã có từ đầu vòng**; so baseline qua cùng config/code/dòng nguồn cho thấy **0 lỗi lint mới**. Không sửa lint cũ ngoài phạm vi. Không gọi `npm run check` vì nhánh này không có script đó; dùng đúng các lệnh scoped người dùng yêu cầu.

- Dấu vân tay SHA-256 toàn file đã kiểm (đối chiếu mã chưa commit trước khi chạy harness):
  - `cong-no-web-handoff/preview/so-khach-v7-ui.js`: `19cad4025f327e99f7c813cc3a7ca3a75525e37cd48107d13d854980292a7e57`.
  - `cong-no-web-handoff/preview/so-khach-v7-api.js`: `56d9f86b441aebb5c685e9c8800c1923e8aac146f021fa78c161e219bb04fe06`.
  - `cong-no-web-handoff/web/v7_ledger_api.py`: `8e526a791844e888fe2ae8af5fc4635aecf0bb6a2405f204ff43dfa71d840327`.
  - `cong-no-web-handoff/tools/v7_backend_functions.sql`: `b3b6685320dec8b22212ad51136ef8884f131590bf135f5f5652d3f05b6fbcb9`.

## Demo dữ liệu giả cho người dùng

`tools/v7_live_demo.py` dùng stdlib và hàm container của `tools/test_pg_v7_backend.py`. Tạo volume/container riêng có nhãn run ID, `--network none`, không publish port; nạp schema + functions vào DB test. Seed ba khách hoàn toàn giả: opening active nhiều kỳ qua import → verify customer → verify cutover → activate cutover → activate customer, có hai phiếu thu; khách `NO_BASELINE`; khách opening active có cờ `MISSING_PRICE`, chuyến thiếu giá và phí lẻ không ngày. Gate verify tự động với dữ liệu giả không phải phê duyệt opening thật. API chạy trên host `127.0.0.1:8780`, truy DB bằng `docker exec`; GET có `demo: true`, trang hiện banner “Dữ liệu thử · DỮ LIỆU GIẢ · Không phải sổ thật”. URL `?customer=<id>` mở từng khách. Ctrl+C hoặc kết thúc lỗi dọn đúng ID/container/volume của run sau kiểm nhãn. Nếu dọn lỗi, script in run ID để xử lý riêng.

Chạy từ `cong-no-web-handoff/`:

```powershell
..\.venv\Scripts\python.exe tools\v7_live_demo.py
..\.venv\Scripts\python.exe tools\v7_live_demo.py --once-seed-only
```

`--once-seed-only` kiểm seed rồi xóa tài nguyên; URL in ra không còn hoạt động. Ngày 20/10/2026 Claude đã chạy demo này với Docker (cổng phụ 8781 qua launcher tạm ngoài repo, vì 8780 đang bận) và kiểm banner, khách nhiều kỳ, khách thiếu giá/phí lẻ, rồi dọn đúng container/volume của run; chưa kiểm khách `NO_BASELINE` trên trình duyệt. Demo chỉ localhost và không dùng Sheet/hao/dữ liệu thật. Công cụ nạp bản sao dữ liệu thật (`tools/v7_load_real_copy.py`, `tools/v7_reconcile_real_copy.py`) là bản viết dở, chưa chạy lần nào.

`docs/ux-guidelines.md` được nhắc trong yêu cầu nhưng không có trong checkout này; giữ CSS gốc và đối chiếu `specs/v7-so-khach-theo-sheet.md` cho màn 1280×720.

Ngày khảo sát: 20/10/2026. Phạm vi: bản mới; không đổi bản thử trong tab hoặc viewer số dư đầu. Không có quyền ghi tiền trên dữ liệu thật.

## Kết luận khảo sát

`preview/so-khach-v7-ui.js` gắn trực tiếp `SO_KHACH_V7_MAU` với `SoKhachV7Model`. Khi vẽ, `render()` gọi `monthChain`, `outstandingByMonth`, `pendingCounts` để **tính lại tiền ở trình duyệt**. Các handler sửa trực tiếp `book`/`months` rồi gọi `reallocate()`/`render()`; gồm dán chuyến, sửa giá, điều chỉnh chuyến/tháng, ghi/sửa/hủy phiếu, mở/khóa tháng và lịch sử. Thay `book` bằng dữ liệu GET không ngăn các handler tiếp tục tự ghi và tự tính. Chỉ bọc `fetch` quanh UI hiện tại có thể hiển thị số khác server hoặc coi lệnh chưa lưu là đã lưu.

Hợp đồng dữ liệu cũng khác: `GET /api/v7/ledger` trả `opening`, `legacy_rows`, `trips`, `receipts` và `allocations` theo ID/chuỗi VND; UI đòi `book.months[*].trips/receipts/adjustments` theo dòng, ngày `dd/mm/yyyy`, cờ `locks`, và tổng do model tính. `source_exceptions` và `status: NO_BASELINE` phải hiện cờ nghi ngờ theo từng kỳ; không được tô thành số 0 hay coi `legacy_rows` là phát sinh mới. `v7_ledger_api.py` hiện chỉ phục vụ `/api/v7/*`, chưa phục vụ HTML/JS cùng origin. `v7_opening_app.py` phục vụ cổng 8777 và chỉ đọc; không dùng cho trang này.

Khảo sát trước khi người dùng mở phạm vi sửa UI: chỉ thêm hai file mới sẽ tạo hai bản giao diện lớn dễ lệch. Người dùng đã cho phép sửa renderer dùng chung trong lượt này.

## Phương án tối thiểu được triển khai trong bản thử

1. Tách phần dựng bảng khỏi các handler của `so-khach-v7-ui.js` thành renderer nhận snapshot server; giữ bản thử dùng adapter fixture. Render trực tiếp tổng/tháng/phân bổ từ GET, không gọi hàm tính tiền của model trong trang live. Bản thử trong tab phải giữ hành vi cũ.
2. `so-khach-v7-api.js` chỉ gửi ý định: GET `/api/v7/ledger?customer=<id>`; POST `/api/v7/trips/paste`, `/api/v7/trips/price`, `/api/v7/trips/adjust`, `/api/v7/months/adjust`, `/api/v7/receipts`, `/api/v7/receipts/meta`, `/api/v7/receipts/void`, `/api/v7/months/lock`. VND gửi dạng chuỗi, giữ `null` khác `"0"`; mỗi POST có `customer_id`, `expected_version`, `idempotency_key` tạo một lần cho thao tác. Không gửi `actor`, tổng hay phân bổ. Chỉ vẽ lại sau GET thành công. `STALE_LEDGER`: GET lại, báo “Sổ vừa thay đổi. Kiểm tra dữ liệu mới rồi thực hiện lại.”; không tự phát lại ý định cũ. Lỗi mạng/`RESULT_UNKNOWN`: giữ nguyên payload và key để người dùng thử lại; không tạo key mới trước khi xác định kết quả.
3. `so-khach-v7-live.html` cần cùng origin với API trên cổng thử riêng, không dùng 8777. Chỉ bật thao tác sau khi GET có `status: active`; `NO_BASELINE` chặn ghi và nêu thiếu mốc. Hiện `source_exceptions` theo kỳ bằng nền/màu kèm chữ, không chỉ dùng màu. `legacy_rows` hiển thị lịch sử riêng, không cộng tiền lần nữa. Cần quyết định cách trình bày `source_exceptions` thiếu hoặc không đủ kỳ trước khi coi UI đã phủ cờ nghi ngờ.
4. Kiểm bằng fixture PostgreSQL cô lập: thao tác → endpoint → GET mới → so số dư/phân bổ, phiên bản, lịch sử và cờ; thử `STALE_LEDGER`, `RESULT_UNKNOWN`, retry cùng key, thiếu nguồn, lỗi mạng và bàn phím. Bằng chứng mock/Docker không thay cho phê duyệt dữ liệu thật hoặc quyền ghi production.

## Điểm đã chốt cho bản thử

- Người dùng cho phép sửa `so-khach-v7-ui.js` để giữ renderer chung và bản fixture nguyên luồng.
- `v7_ledger_api.py` phục vụ HTML/JS trên cùng origin localhost:8780. Actor do cấu hình server lấy; trang không gửi actor. Cơ chế tài khoản người thật còn mở, không coi cổng thử là môi trường vận hành.

## Bản sao dữ liệu thật — vòng 1, 20/10/2026

**ĐÃ SỬA mã, chỉ kiểm bằng dữ liệu giả.** Gate bắt đầu: vòng ui4 có kiểm sau vòng 4 ở trên, người dùng đã commit thành `6fe342a` trên `codex/v7-opening-read`. Hai công cụ vốn chưa được Git theo dõi; vòng này chỉ sửa hai công cụ, thêm test và cập nhật mục này. Không commit/stash/reset/push. Các ghi chú “chưa chạy lần nào/bản viết dở” ở trên là trạng thái trước vòng này; **chưa chạy trên nguồn thật** vẫn còn đúng.

| Điểm | ĐÃ SỬA và kiểm | KHÔNG LÀM / CÒN MỞ |
| --- | --- | --- |
| 1 — đủ dòng, ngày | `tools/v7_load_real_copy.py`: quét mọi tab khách/cột của XLSX bằng XML stdlib, nhận tiêu đề thay vị trí cố định, chịu cột nhãn đầu. Đọc inline/shared strings và cache công thức. So đa tập `(dòng vật lý, số tiền gốc)` riêng chuyến/thu với CSV từng tab: kiểm chặt hơn chỉ số dòng/tổng. Lệch thì cách ly nguyên khách **trước mọi SQL**. Ngày lấy trực tiếp XLSX theo khối tháng; đảo chỉ khi khớp khối, không dùng ngày CSV để đoán. | Không mở XLSX/CSV thật. Bố cục không nhận diện, tháng trùng, hệ ngày 1904 bị giữ lại/từ chối; chưa khẳng định parser phủ mọi biến thể nguồn thật. |
| 2 — thiếu giá/tiền thu | Thiếu đơn giá chuyến thường đóng góp 0 phát sinh, giữ `source_total_vnd` gốc (kể cả NULL), ô nguồn và `MISSING_PRICE` trong lịch sử. Phí lẻ không container/đơn giá giữ tổng gốc. Thu thiếu tiền giữ NULL trong bằng chứng, cách ly khách với `MISSING_RECEIPT_AMOUNT`. | Không quyết khi chuyến lịch sử thiếu giá được báo giá sau này thì sửa lịch sử hay nhập chuyến mới, theo MOC-CHUYEN-MOI (b). |
| 3 — gate từng khách | Mỏ neo cuối lấy trực tiếp tab khách, bỏ `TONG` khi tính số. Tổng bucket CSV phải bằng mỏ neo đó; tính FIFO độc lập từ mỏ neo đầu tường minh và phát sinh/thu XLSX; so từng bucket, từng mỏ neo cuối tháng và số chuyển sang nếu có. Thiếu mỏ neo đầu/cuối thì cách ly, **không suy ngược từ tổng cuối, không lấy NULL làm 0**. Bucket tháng không có trong CSV chỉ qua nếu FIFO chứng minh đúng 0. Giữ `NO_BASELINE`, `HISTORICAL_DELTA_600`; chưa gán mặt hàng thì giữ `CHUA_PHAN_LOAI`/commodity NULL. `tools/v7_reconcile_real_copy.py` dùng lại các gate, so cả tập tháng và tổng với bản sao. | Không sửa SQL/API/UI. Schema chỉ nhận mã cờ cũ: cờ ngày mới giữ đúng mã ở `legacy.display.flags`/báo cáo, tháng dùng `OTHER`; chưa kiểm cách UI trình bày các cờ ngày này. Không tự suy mặt hàng từ tên/tab. |
| 4 — truy nguồn | SHA-256 cả 7 file đầu vào, kiểm lại sau đọc để bắt nguồn thay đổi; nguồn XLSX là hash chứng cứ cho gate tháng. Báo cáo luôn có câu nguồn cố định dưới đây. | Hash bản xuất không chứng minh đây là đúng bản v2 đã nạp lên hao. |
| 5 — vận hành | `--check-source` chỉ đọc/đối soát, stdout + JSON ngoài repo. Khách cách ly chỉ có ordinal theo tên tab đã sắp xếp, ổn định với cùng tập nguồn; không có bảng ánh xạ tên trong log. Báo cáo chỉ số đếm khách/tháng/dòng/cờ/lý do, ordinal, run ID, hash và câu nguồn. `--port` mặc định 8782, bind cố định `127.0.0.1`, cấm 8777. Giữ Docker `--network none`, không publish; dọn bằng full ID/nhãn/volume đúng run; lỗi vẫn dọn khi có `--keep`. Đối soát kiểm quyền sở hữu container trước đọc DB. | Không gọi Docker trong vòng này; kiểm lệnh/cổng/dọn tài nguyên bằng mock. `--keep` chỉ dùng khi người dùng yêu cầu rõ. Chưa có bằng chứng runtime PostgreSQL/HTTP của hai công cụ. |
| 6 — test | `tests/test_v7_load_real_copy.py` dựng CSV/XLSX giả trong thư mục tạm, gồm mọi ca bắt buộc và công thức thiếu cache, chuỗi tháng độc lập, FIFO, số nguyên lớn, báo cáo không lộ dữ liệu, CLI cấm cổng, dọn tài nguyên sai nhãn/lỗi. Có chạy thật subprocess `--check-source` trên fixture giả. | Không kiểm dữ liệu thật, không chạm captures/hao/Sheet; không chạy nghiệm thu bước 8 thay người dùng. |

Câu nguồn bắt buộc trong mọi báo cáo:

> Nguồn là bản xuất trong captures/2026-10-20-so-goc; chưa xác nhận trùng đúng bản v2 đã nạp lên hao

Mã thêm trong vòng này (mã đang có giữ nguyên):

- Cách ly: `SOURCE_ROW_MISMATCH`, `SOURCE_LAYOUT_UNSUPPORTED`, `DUPLICATE_MONTH_BLOCK`, `MISSING_SOURCE_TAB`, `MISSING_OPENING_ANCHOR`, `MISSING_MONTH_ANCHOR`, `MISSING_RECEIPT_AMOUNT`, `MISSING_TRIP_AMOUNT`, `INVALID_RECEIPT_AMOUNT`, `INVALID_TRIP_AMOUNT`, `ANCHOR_CHAIN_MISMATCH`, `FIFO_BUCKET_MISMATCH`.
- Từ chối toàn nguồn: `UNSUPPORTED_DATE_SYSTEM`, `SOURCE_CHANGED_DURING_READ` (các lỗi cũ `SOURCE_FILE_MISSING`, `DUPLICATE_SOURCE_TAB`, `AMBIGUOUS_SOURCE_TAB`, `INVALID_OPENING_PERIOD` vẫn có).
- Cờ không tự chặn: `DATE_SWAPPED`, `DATE_OUT_OF_BLOCK`, `MISSING_DATE`, `CHUA_PHAN_LOAI` (nhãn nghiệp vụ `CHUA PHAN LOAI`), `SUMMARY_ANCHOR_DIFFERS`. Giữ `NO_BASELINE`, `MISSING_PRICE`, `MISSING_CACHE`, `HISTORICAL_DELTA_600`, `OTHER`; cờ nguồn tự do giữ trong lịch sử, báo cáo chỉ đếm `OTHER` để tránh lộ nội dung.
- Đối soát thêm: `QUARANTINED_CUSTOMER_ACTIVE`, `INACTIVE_CUSTOMER`, `CONTAINER_MISSING`; giữ `DUPLICATE_CUSTOMER`, `MISSING_CUSTOMER`, `EXTRA_CUSTOMER`, `CUSTOMER_MISMATCH`, `PERIOD_MISMATCH`. Lỗi vận hành giữ `DOCKER_UNAVAILABLE`, `POSTGRES_INIT_TIMEOUT`, `IMPORT_ERROR`, `TEARDOWN_FAILED` và whitelist mã `CUTOVER_*` có thật trong SQL; không in thông điệp lỗi chứa dữ liệu.

Báo cáo lưu `D:\webdebit\worktrees\_logs\v7\source-check-<run_id>.json`, `real-load-<run_id>.json`, `real-reconcile-<run_id>.json`; không cho đổi output vào repo. `--check-source` trả 0 khi không khách cách ly, 2 khi có cách ly, 1 khi lỗi đọc/chạy. `loaded_customers=0` trong check nguồn; `eligible_customers` là số qua gate nguồn, chưa phải số đã nạp DB. Công cụ đối soát dành cho bản sao vừa nạp, trước thao tác thử; phát sinh sau nạp sẽ hiện lệch nguồn.

**ĐÃ KIỂM CHỨNG cục bộ trên Windows, nền `6fe342a` cộng đúng bốn file vòng này, chỉ giả:**

```powershell
# Từ cong-no-web-handoff/ trong worktree
..\..\..\repo\.venv\Scripts\python.exe -m unittest tests.test_v7_load_real_copy tests.test_v7_ledger_api -v
..\..\..\repo\.venv\Scripts\python.exe -m py_compile tools/v7_load_real_copy.py tools/v7_reconcile_real_copy.py
node --test --test-isolation=none preview/test-so-khach-v7-model.js preview/test-so-khach-v7-api.js
# Từ gốc worktree
npm run test:unit
git diff --check
```

Kết quả: Python **30 đạt, 1 bỏ qua** (20 test công cụ mới + 10 API; case API Docker bỏ qua theo yêu cầu); Node V7 **39/39**, Node unit cũ **40/40**; `py_compile` và `git diff --check` đạt. Subprocess `--check-source` trên fixture giả: **exit 0, 1 khách đủ điều kiện, 0 cách ly, 0 khách đã nạp**, đủ 7 hash; ca CSV thiếu dòng exit 2 và không gọi Docker. Dọn tài nguyên/cổng là bằng chứng mock; không thay bằng chứng Docker/DB thật.

**CÒN MỞ:** người có quyền đọc nguồn thật chạy check sau đồng ý của người dùng, xử lý khách bị cách ly (gồm nguồn không có ô mỏ neo đầu rõ ràng), xác định đúng bản v2 bằng chứng nguồn, rồi mới chạy bản sao dùng một lần và người dùng tự nghiệm thu. Không suy test giả thành xác nhận nguồn thật hoặc sổ trên hao.

**Review của Claude (20/10/2026, chỉ đọc mã và chạy test giả, chưa đọc nguồn thật):** Python `tests.test_v7_load_real_copy` + `tests.test_v7_ledger_api` 30 đạt, 1 bỏ qua; Node 39/39. Đã sửa một lỗi chặn: `RealHandler` không đặt `port`, nên kiểm Host/Origin so với cổng mặc định 8780 trong khi server nghe `--port` (mặc định 8782) — mọi yêu cầu bị `INVALID_HOST`; nay `port = args.port` (đã thử: Host `127.0.0.1:8782` qua kiểm). Ghi chú còn lại: (1) mọi khách đều mang cờ `CHUA_PHAN_LOAI` vì công cụ chưa đọc mặt hàng từ dòng `TONG` (V7-MH), nên mọi tháng bị tô cờ `OTHER` — chỉ tô màu, không chặn, nhưng làm cờ mất ý nghĩa; (2) chuyến có ô thành tiền nhưng trống đơn giá bị coi là thiếu giá, tiền bị loại khỏi chuỗi nên khách đó sẽ bị cách ly `ANCHOR_CHAIN_MISMATCH` — an toàn (không nạp số sai) nhưng có thể giữ lại nhiều khách; (3) ngày ngoài khối tháng để trống ngày, giữ ô gốc trong `display`.

## Bản sao dữ liệu thật — chạy thật 20/10/2026 (Claude)

**Đã chạy** trên `captures/2026-10-20-so-goc` (người dùng cho phép, thêm quyền riêng cho đúng lệnh), container dùng một lần `--network none`, chỉ `127.0.0.1:8782`, không chạm `hao`/Sheet. Lần cuối: **190/246 khách nạp**, 56 bị giữ; các gate phía DB đều đạt. Báo cáo số đếm ở `worktrees/_logs/v7/real-load-*.json` (ngoài Git). Người dùng xem sổ nhiều khách (FANTA, FENG BO, FANYA, KK…) và nhận xét "có vẻ ok". Chưa phải nghiệm thu nghiệp vụ.

**Bộ đọc xlsx viết lại theo bố cục thật** (khảo sát cấu trúc bằng `tools/v7_profile_xlsx.py`, chỉ in mẫu xuất hiện ≥5 tab, số thay bằng N): tiêu đề "SỔ CHI TIẾT … PHẢI THU THÁNG m.yyyy" chỉ ở cột A–C; tiêu đề cột có hậu tố tháng; bảng phụ bên phải không lấy cột (cột trái nhất thắng); dòng TỔNG có hoặc không nhãn (tổng = tổng các dòng trên) là dòng cộng, mỏ neo lấy ở đó; dòng mẫu chỉ có công thức 0 bị bỏ; ô mô tả lệch cột thì dò ngày và dịch; số nợ chuyển sang có nhãn hoặc nằm ở cột "còn phải thu" trên chuyến đầu; ngày serial ngoài khối lấy một cách đọc theo đa số trong tab. Thêm `--explain NAME` và `--dump-tab NAME` (chỉ in cho khách được hỏi, số thay bằng N).

**Quyết định người dùng 20/10/2026:**
- (b) Tháng có lịch sử hiện dòng "Theo sổ gốc" (phát sinh, đã thu, còn nợ của Sheet từ `cutover_month_check`, qua `get_ledger.source_exceptions`) dưới "Cộng tháng"; số dư vẫn từ bucket. Dòng lịch sử hiện đúng 14 cột như Sheet.
- Cờ/guard kỹ thuật của khâu nạp không hiện trên sổ người dùng, chỉ giữ trong DB và báo cáo nạp; sổ chỉ hiện "chưa có giá" và trạng thái khách chưa có số dư đầu. **Thay phần "hiển thị (tô màu)" của `V7-BE` (5)** — cần ghi vào `docs/decisions.md`.
- Khi tổng khớp mỏ neo Sheet nhưng cách chia tháng của bảng số dư đầu (bản đã nạp lên `hao`) khác FIFO từ Sheet, bản sao chia theo Sheet (`BUCKETS_FROM_SHEET`).

**ĐÃ CHỐT (người dùng 20/10/2026, `V7-COPY` trong docs/decisions.md):** dòng lịch sử giữ ô TOTAL của Sheet kể cả thiếu đơn giá (cờ thiếu giá); ô chuyển sang trống/không có coi là 0 và luôn kiểm bằng mỏ neo cuối tháng; CSV cũ thiếu dòng so với xlsx chỉ ghi cờ.

**CÒN MỞ:** 56 khách bị giữ (bố cục lạ, lệch chuỗi, thiếu mỏ neo, ô tiền không đọc được, 1 tab trùng tên); 11 khách có tháng nợ trên `hao` không có trong Sheet và 36 tháng phải chia lại theo Sheet — cần kiểm cách chia tháng của số dư đầu trên `hao` (chưa đụng `hao`); mặt hàng chưa đọc từ `TONG`. Kiểm: Python 38 đạt + 1 bỏ qua; Node 39/39; harness PostgreSQL 10/10, 25/25.

**Xử lý khách bị giữ (20/10/2026, sau cùng):** bộ đọc nhận thêm tiêu đề "THÁNG 2+3.2024" (lấy tháng cuối) và "THÁNG 122025"; cột ngày "ETA"; đơn giá có hậu tố; số ngoài bảng chỉ ghi cờ; nhãn TỔNG/CHUYỂN SANG chỉ xét trong vùng bảng chính (bảng phụ bên phải ghi "TỔNG"/"CÒN LẠI" từng làm đóng khối sớm); tab không có trên `TONG` ghi lý do `NOT_ON_TONG`, không nạp. Kiểm nguồn lần cuối: còn 33 bị giữ (23 khách thật + 10 tab không có trên `TONG`); lần nạp cuối bị dừng theo yêu cầu người dùng trước khi in báo cáo. Bản sao đã dừng, container/volume đã xóa. CÒN MỞ: 23 khách (ô công thức mất giá trị trong file xuất, khối lặp tháng, tab trùng tên, chuỗi lệch) — một phần cần xuất lại Sheet có giá trị công thức.

**Giảm khách bị giữ — vòng sửa bộ đọc (20/10/2026, chỉ sửa `tools/v7_load_real_copy.py` + test giả, không chạm `hao`/Sheet/Docker):** kiểm nguồn lại bằng `--explain HELD`: **23 → 5 khách thật bị giữ** (cộng 10 tab không có trên `TONG` vẫn chỉ báo `NOT_ON_TONG`, không nạp). Các chốt đối soát (chuỗi mỏ neo, FIFO, tổng opening, ô tiền không đọc được → giữ) giữ nguyên; mọi kiểu bố cục mới dưới đây vẫn phải qua chuỗi mỏ neo, nên đọc sai sẽ lộ thành `ANCHOR_CHAIN_MISMATCH`. Đã gỡ (18 khách) nhờ mười sửa tổng quát, không viết riêng cho tên khách:
- tiêu đề tháng gõ thừa ký tự phân cách (`1\.2026`, `2..2026`) được đọc; tiêu đề gõ sai tháng/năm (`782026`, `4.205`) chỉ lấy tháng từ ngày chuyến khi mọi dòng có ngày cùng cho đúng một tháng và các chữ số gõ chứa số tháng đó, ghi cờ `TITLE_MONTH_FROM_DATES`; khác thì vẫn giữ (`LAYOUT_BAD_MONTH_TITLE`);
- tiêu đề bảng phụ (hóa đơn bên phải) xuất hiện ở dòng sau, kể cả ngay trên một dòng chuyến, không còn thay cột bảng chính (làm lệch cả cột TOTAL, mất dòng chuyến, dòng cộng không nhãn bị đọc thành chuyến) — cờ `SIDE_TABLE_HEADER_IGNORED`;
- khối có tiêu đề cột nhưng không có tiêu đề tháng chỉ được bỏ khi hoàn toàn trống (không dòng, mỏ neo/số chuyển sang là 0) — `UNTITLED_EMPTY_BLOCK`; có tiền thì vẫn `LAYOUT_HEADER_MISSING_BLOCK`;
- khối tháng lặp lại *giống hệt* (cùng mỏ neo, số chuyển sang và từng dòng) chỉ tính một lần — `DUPLICATE_BLOCK_IDENTICAL`; khác nội dung vẫn `DUPLICATE_MONTH_BLOCK`;
- dòng chỉ có đơn giá (không container, ngày, TOTAL, phí) là ghi chú giá, bỏ qua và ghi cờ `PRICE_ONLY_ROW_IGNORED`; nếu Sheet thực ra có tính, chuỗi mỏ neo vỡ và khách vẫn bị giữ;
- dòng tín dụng âm không container (đơn giá và TOTAL cùng âm) được giữ có dấu (`source_charge_vnd` có dấu, SQL đã cho) — `NEGATIVE_CREDIT_ROW`; âm kèm container vẫn `INVALID_TRIP_AMOUNT`;
- CSV cũ đếm dòng cộng không nhãn của xlsx thành chuyến: bỏ qua đúng dòng đó khi số dòng và số tiền khớp dòng cộng đã nhận — `CSV_COUNTED_TOTAL_ROW`; tiêu đề cột TOTAL có ghi chú gõ kèm (`TOTAL(VND) …`) và nhãn cột ngày `PACKING` được nhận;
- ô công thức có kết quả lưu là chuỗi rỗng (`t="str"` kèm `<v></v>`) là ô trống, không phải công thức mất giá trị. Chỉ công thức không có `<v>` mới là `FORMULA_CACHE_MISSING`. Kiểm bằng cách đọc Sheet sống (chỉ đọc) cho thấy hai khách từng bị coi là mất giá trị chỉ có công thức trả ô trống.
- **ĐÃ CHỐT bởi người dùng 20/10/2026** — chuyển năm: số chuyển sang của tháng 1 gõ trong Sheet là đúng; chênh so với số cuối tháng trước (tháng 12, hoặc tháng gần nhất của năm trước) là khoản chưa vào sổ chi tiết. Bộ đọc ghi đúng một dòng điều chỉnh có cờ `YEAR_END_CARRY_ADJUSTED` (thiếu hụt là khoản thu, FIFO trừ kỳ cũ trước; dư là phát sinh, hiện trong lịch sử với nguồn `…:year-end-carry`) và chuỗi mỏ neo vẫn phải đóng. Chỉ áp cho tháng 1 có khối năm trước; tháng khác lệch vẫn bị giữ;
- **ĐÃ CHỐT** — ô TOTAL của dòng tổng có tiền mà các dòng chuyến không có giá: chia đều cho các chuyến chưa có giá (đồng nguyên, dư 1 đồng cho các dòng đầu), cờ `TOTAL_SPREAD_OVER_TRIPS`; không có gì để chia thì không đổi;
- tiêu đề tháng lặp nhưng ngày chuyến dưới nó nói một tháng sau còn trống: lấy tháng đó (`TITLE_MONTH_FROM_DATES`); bản sao thật giữ vai khối lặp.

Còn **5 khách thật bị giữ**, đều có lý do cụ thể đã xem bằng `--dump-tab` và đối chiếu Sheet sống (chỉ đọc): (a) số tiền không nguyên đồng (chia đôi/chia ba trong công thức) — mã mới `NON_INTEGER_AMOUNT` (3 khách, trong đó 1 khách là 16 ô vốn ghi “không đọc được”; cần quyết định lược đồ/làm tròn); (b) một khách đã được sửa trên Sheet sống sau bản xuất 20/10 nhưng bản xuất chưa có, cần xuất lại; (c) hai tab trùng tên sau khi cắt khoảng trắng (Sheet sống có tên khác nhau ở khoảng trắng đầu; chờ xác nhận tab đang dùng). Kiểm: `tests.test_v7_load_real_copy` + `tests.test_v7_ledger_api` đạt (53 test, 1 bỏ qua); thêm 14 test dữ liệu giả cho các kiểu trên.

**Tab trùng tên chỉ khác khoảng trắng (21/10/2026):** `--raw-tab "<tên đúng nguyên văn>"` (lặp được, cả loader và reconcile) chọn tab người dùng đang dùng; các tab cùng tên sau khi cắt khoảng trắng nhưng khác nguyên văn bị bỏ qua. Tên khách chỉ nằm ở dòng lệnh, không vào Git. Trên bản xuất 20/10 với tab đã chọn, khách này không còn lý do giữ (chưa nạp). Số lẻ đồng (AG LOGISTIC, FENG JIE, XIAOLONG) vẫn còn trong cả Sheet gốc lẫn bản copy khi đọc giá trị thật (hiển thị đã gọn nhưng giá trị chưa làm tròn).

**Làm sạch số lẻ đồng (21/10/2026, ĐÃ CHỐT bởi người dùng: kiểm Sheet và làm sạch trước khi nạp):** ô tiền có phần lẻ (chia đôi/chia ba trong công thức) đọc thành đồng nguyên, cờ `ROUNDED_VND`; giá trị chính xác giữ trong bộ nhớ khi quét.
- Dòng: chuyến làm tròn nửa lên, thu làm tròn nửa xuống, để số dư (phát sinh − thu) vẫn tròn nửa lên như ô số cuối tháng của Sheet. Nếu các số lẻ cộng đúng bằng ô tổng (nguyên đồng) của dòng cộng thì chia lại theo phần dư lớn nhất để dòng khớp tổng (`ROUNDING_APPORTIONED`).
- Tháng: phát sinh tháng = tổng chính xác làm tròn; thu tháng = giá trị làm cho số dư nguyên đồng bằng số dư chính xác làm tròn nửa lên (`ROUNDED_MONTH_TOTALS`). Chuỗi mỏ neo cuối tháng vẫn phải khớp ô Sheet; lệch dù 1 đồng thì khách vẫn bị giữ.
- Thay đổi chốt “VND nguyên chính xác” chỉ ở bước làm sạch nguồn: mọi số đi vào lược đồ vẫn là bigint nguyên; lược đồ không đổi. Mã `NON_INTEGER_AMOUNT` không còn phát sinh.
- Dòng thu “bảo hiểm cộng vào nợ” mà CSV cũ ghi âm: so sánh theo cùng độ lớn với ô xlsx (dương, được tính là phát sinh), vẫn phải bằng nhau.
- Dòng carry có ô TOTAL bằng 0 (công thức mẫu) vẫn là dòng chuyển sang không nhãn.

Kết quả trên bản xuất 20/10 với `--raw-tab` cho tab trùng tên: **còn 1 khách thật bị giữ** (cần xuất lại: Sheet sống đã sửa sau bản xuất). Kiểm: Python 57 đạt, 1 bỏ qua. CÒN MỞ: nạp bản sao bằng file xuất mới, và người dùng nghiệm thu các dòng điều chỉnh/làm tròn trên giao diện.

**Bản xuất 21/10 (`captures/2026-10-21-so-goc/21-10.xlsx`, quét tạm với CSV của 20/10, không sửa captures):** thêm bước chọn cách đọc các khoản “bảo hiểm cộng vào nợ” (kind trong CSV cũ): mặc định là phát sinh; nếu khách còn lý do giữ và Sheet đã đổi cách tính, thử đọc như khoản thu thường và giữ cách đọc đó chỉ khi ít lý do giữ hơn (chuỗi mỏ neo vẫn phải đóng đúng từng tháng, cờ `INSURANCE_AS_RECEIPT`). Kết quả: 5 khách thật còn giữ — LINZONG (file 21/10 vẫn còn số thừa 3 trong cột thu của tháng 5.2026), và 4 khách mà Sheet đã thay đổi sau bản v2 nên tổng opening trên `hao` không còn bằng mỏ neo Sheet (`OPENING_TOTAL_MISMATCH`): hai khách đã được thu sau v2 (opening trên `hao` còn nợ kỳ 9.2026, Sheet nay đã thu hết), một khách có chuyến tháng 10 mới, một khách đã đổi cách tính khoản bảo hiểm. CÒN MỞ: quyết định opening theo v2 (20/10) rồi nhập các thay đổi sau đó trên web (MOC-CHUYEN-MOI), hay cập nhật opening theo Sheet 21/10.

**`--sheet-is-truth` (21/10/2026, ĐÃ CHỐT bởi người dùng: lấy theo dữ liệu Sheet mới nhất, không bám CSV cũ; ví dụ khoản thu nhập ngày 20/10 và chuyến tháng 10 là đúng):** với cờ này (loader và reconcile), dòng CSV khác xlsx chỉ ghi cờ `CSV_STALE_ROWS`, tổng opening trên `hao` khác mỏ neo Sheet chỉ ghi cờ `OPENING_TOTAL_DIFFERS_FROM_HAO`, và các bucket opening lấy theo FIFO từ Sheet (`BUCKETS_FROM_SHEET`). Không cờ thì mọi hành vi cũ giữ nguyên (vẫn giữ khách). Chuỗi mỏ neo cuối tháng, FIFO theo Sheet, ô tiền không đọc được → giữ không đổi. Kết quả trên `21-10-goc.xlsx` (đặt ngoài `captures/`, quét qua thư mục tạm) với `--raw-tab` cho tab trùng tên: **236 khách thật, 0 bị giữ** (10 tab không có trên `TONG` vẫn chỉ báo `NOT_ON_TONG`). Năm khách có cờ vì khác bản v2: hai khách đã thu 20/10 (opening mới 0), một khách có chuyến tháng 10 (opening mới theo Sheet), một khách đổi cách tính bảo hiểm (`INSURANCE_AS_RECEIPT`), một khách chỉ còn dòng CSV cũ. CÒN MỞ: đây là quét nguồn, chưa nạp bản sao; opening trên `hao` (v2) khác bản này ở bốn khách — nạp `hao` là việc riêng cần quyết định.

**Bản gốc đã làm sạch (21/10/2026, ĐÃ CHỐT bởi người dùng: dữ liệu đã làm sạch là bản gốc để so về sau):** `tools/v7_export_clean.py --xlsx <file> --source-dir <CSV đầu vào> --raw-tab ... --out <thư mục mới ngoài repo>` xuất kết quả sau làm sạch (đúng thứ loader sẽ đưa vào bản sao) thành `clean_customers.csv`, `clean_months.csv`, `clean_rows.csv` và `manifest.json` (SHA-256 nguồn và từng file, commit công cụ, số lượng, số khách theo từng quy tắc làm sạch). Chỉ ghi vào thư mục mới/trống ngoài repo; không in tên/số tiền ra stdout; không xuất nếu còn khách thật bị giữ (thoát mã 2). Lần xuất 21/10 từ `21-10-goc.xlsx`: 236 khách, 877 tháng, 11.392 dòng, 10 tab không có trên `TONG` bỏ qua. CÒN MỞ: thư mục đích trong `captures/` không tạo được do quyền (Access denied), bản xuất hiện nằm ở thư mục tạm của phiên chờ người dùng chuyển hoặc cấp quyền; `hao` vẫn giữ opening v2 ở bốn khách.
