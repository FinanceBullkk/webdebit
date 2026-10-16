# P0-02 — Thiết kế danh tính và duyệt theo revision

Ngày: 15/10/2026; cập nhật hợp đồng fixture 16/10/2026. Trạng thái: **ĐỀ XUẤT KỸ THUẬT để review**. Q01/Q02 đã chốt ở mức nguyên tắc; thiết kế này cụ thể hóa một phương án triển khai. Fixture PostgreSQL kèm theo là prototype cô lập, không phải migration, app login, hay đường ghi tiền được bật.

## Phạm vi và bằng chứng nền

- Ứng dụng self-host trên một máy. Chỉ thiết bị trong tailnet của chủ máy tới được trang login. Mỗi người có app account riêng; maker và checker là hai người khác nhau; actor xuất phát từ session server-side.
- Q02: approval gắn với nội dung của revision bất biến. Mọi đổi nghĩa nghiệp vụ tạo revision mới và cần approval mới. Chỉnh sửa trình bày không đổi nghĩa không tạo revision.
- Viewer hiện tại `cong-no-web-handoff/web/ledger_app.py` chỉ đọc và bind `127.0.0.1`; chưa có login/session hoặc route ghi. `tools/pg_ledger_schema.sql` lấy maker, checker và audit actor từ `session_user`; proposal lines có thể được đọc lúc duyệt sau khi owner sửa. Đây là kiểm tra mã tại checkout, không phải runtime.
- PR #3 characterization đã chạy trên PostgreSQL 18.6; stale-content là `repro_success`, không phải acceptance của guard. Chi tiết revision/run nằm trong `docs/verification.md`.

Q03–Q08 và Q09 vẫn mở. Fixture chỉ còn một loại proposal: **charge** (`schema_version=3`). Mọi charge vào ở `review_needed` và chỉ post được khi có đủ: xác nhận kỳ của maker, xác nhận giá, checker khác maker và khác người xác nhận giá, kỳ còn mở, TRIP-KEY hợp lệ và một dòng `trip_opening_resolution` trạng thái `ABSENT_FROM_OPENING_APPROVED`. Bảng resolution **rỗng ngoài test** nên mặc định mọi charge bị chặn (CHỜ KIỂM). Receipt không được nhận; fixture không chọn chính sách tiền dư/FIFO ngoại lệ/reversal/khóa kỳ/receipt verification và không được nối vào viewer.

### Quyết định áp dụng cho fixture (ĐÃ CHỐT 16/10/2026, người dùng, phạm vi fixture và hợp đồng charge đầu tiên)

| ID | Nội dung | Tác động lên fixture |
|---|---|---|
| OPENING-FINAL | Opening 13/10/2026 16:44 đủ và chốt cho mọi chuyến có ngày xe nhập kho trước 14/10/2026; hệ thống mới chỉ nhận charge có ngày xe nhập kho từ 14/10/2026. | `warehouse_in_date < 2026-10-14` bị từ chối khi submit với thông báo "chuyến cũ, nợ thuộc opening 13/10". |
| PRICE-ZERO | Cấu phần 0đ khi tổng > 0 và cấu phần khớp tổng chỉ cảnh báo. Tổng 0 hoặc trống vẫn là CHỜ KIỂM. | `COMPONENT_AMOUNT_ZERO_WARNING` không chặn xác nhận giá; `TOTAL_ZERO`/`TOTAL_MISSING` vẫn chặn. |
| PRICE-MAKER | Người xác nhận giá phải có role `price_owner` (chủ nghiệp vụ). Maker được phép đồng thời là `price_owner` và tự xác nhận giá chuyến mình nhập. Người xác nhận giá không được làm checker của cùng revision; maker khác checker (D01). | `confirm_price` yêu cầu role `price_owner` (role `maker` không đủ); `approve` và `post` từ chối nếu checker là người xác nhận giá của revision đó. |
| SIMPLIFY | Đơn giản hóa fixture ngay, không chờ M3. | Mục "App actor → DB audit" và "Kind, role DB" bên dưới. |

Chính sách v1 **ĐÃ CHỐT** theo [DUP-01, JOIN-01](../../docs/decisions.md): mỗi `trip_key` một charge và chính sách duyệt bảng nối opening ↔ mã chuyến; fixture CI đã có `UNIQUE(posting.trip_key)`.

**CÒN MỞ**: dấu "/" trong ô booking, booking bị sửa sau khi ghi, ngưỡng ngày cụ thể của JOIN-01, nâng khóa lên chuyến + loại phí khi có danh mục loại phí được duyệt; bảng resolution production chưa triển khai.

## Kind và role DB

Fixture không còn `kind`: không có `revision_fixture`, không có role `p0_fixture_identity_test_api`. Chỉ có một role API `p0_fixture_api` và một login giả `webdebit_app` thuộc role đó. Role API không có quyền đọc bảng hay DML trực tiếp, chỉ `EXECUTE` sáu hàm nghiệp vụ (`submit_revision`, `set_presentation_title`, `confirm_price_revision`, `confirm_period_revision`, `approve_revision`, `post_revision`). Hàm kiểm `pg_has_role(session_user, 'p0_fixture_api', 'member')` trước mọi thao tác; login ngoài role bị từ chối dù được cấp `EXECUTE`. Bảng `trip_opening_resolution` chỉ owner/superuser ghi; không có hàm API nào ghi bảng này. Role ứng dụng của actor: `maker`, `checker`, `price_owner`, `admin`.

Ghi chú về giới hạn: `pg_has_role(..., 'member')` luôn đúng với superuser; fixture dùng login thường để kiểm ranh giới này.

## Ranh giới tin cậy đề xuất

### Mạng và proxy

1. Chạy web app sau **Tailscale Serve** với upstream loopback; app chỉ bind `127.0.0.1`. Không bật Funnel, port-forward, listener LAN/WAN hay rule firewall cho DB. Tailnet ACL giới hạn nhóm thiết bị được tới máy chủ.
2. Trang login vẫn yêu cầu app account. Tailscale chỉ chứng minh khả năng tới mạng, không là actor và không là approval.
3. Không nhận actor, role, hoặc trạng thái đăng nhập từ query, body, cookie tự giải mã, hay header `X-Forwarded-*`/header danh tính proxy. Serve không được coi là nguồn principal ứng dụng.
4. DB không listen trên tailnet. Chỉ process web trên máy chủ được dùng DB socket/loopback bằng DB role dịch vụ; role này không có DML trực tiếp, chỉ `EXECUTE` các hàm nghiệp vụ được duyệt.
5. Khởi động phải kiểm host/bind/config; nếu không xác nhận loopback và proxy dự kiến, fail closed. Cấu hình thật chưa được tạo hoặc kiểm.

### Account, session và role

Đề xuất triển khai app account trong DB riêng với các trạng thái `active`, `disabled`; không cho tự đăng ký. Quản trị viên tạo account cá nhân, cấp hoặc thu hồi `maker`/`checker`; quyền `admin` chỉ quản lý account, không tự mang quyền maker/checker. Một người có thể giữ cả hai role, nhưng cùng một actor không bao giờ lập rồi duyệt chính proposal đó. Không tạo tài khoản người dùng chung.

- Bootstrap: lệnh local một lần trên máy chủ tạo admin đầu tiên; lệnh yêu cầu terminal tương tác, chỉ chạy khi chưa có admin và xóa trạng thái bootstrap sau thành công. Không có account mặc định hoặc endpoint bootstrap từ mạng.
- Mật khẩu: lưu salted `scrypt` verifier (N=32768, r=8, p=1, 32-byte result) bằng `hashlib.scrypt`; so sánh constant-time. Reset đặt mật khẩu mới, tăng `auth_epoch` và thu hồi mọi session của actor.
- Session: token ngẫu nhiên 256-bit; chỉ lưu SHA-256 token hash ở server. Cookie `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`; rotate sau login và đổi quyền. Đề xuất TTL idle 30 phút, absolute 12 giờ; kiểm active account, epoch, expiry và quyền ở mỗi thao tác ghi. Logout, disable, reset mật khẩu hoặc đổi quyền thu hồi session ngay.
- Mọi POST có CSRF token gắn session. Login lỗi trả thông báo chung và rate-limit theo account cùng nguồn mạng; log không ghi mật khẩu, cookie hoặc nội dung chứng từ.
- Audit account ghi actor quản trị, account bị tác động, thay đổi role/status và thời điểm. Không tự cho admin vượt maker/checker hoặc sửa posting.

Đây là thiết kế đề xuất; chưa có account/session code. TTL, cơ chế rate-limit và vận hành bootstrap cần được chủ vận hành review trước khi bật login.

## App actor → DB audit

DB session login vẫn là `webdebit_app` dùng chung cho process, nên `session_user` chỉ chứng minh service account. Không ghi nó như bằng chứng người bấm duyệt.

**Hợp đồng fixture hiện tại (SIMPLIFY 16/10/2026):** web app dựng `actor_id` và `session_id` từ session server-side đã xác thực (Q01) rồi truyền thẳng làm tham số hàm API. Không có chữ ký HMAC, nonce, khóa ký hay bảng nonce. Mỗi hàm gọi `p0_fixture.require_actor(actor_id, session_id, role)`: actor còn active, có đúng role cho thao tác, và `session_user` thuộc `p0_fixture_api`. Role theo thao tác: submit/presentation/xác nhận kỳ → `maker`; xác nhận giá → `price_owner`; approve/post → `checker`. Một actor có thể giữ nhiều role (ví dụ maker kiêm price_owner).

Lý do bỏ HMAC từng lệnh: app là bên giữ khóa ký, nên chữ ký không chứng minh thêm điều gì khi app process bị chiếm; còn khi chỉ có credential DB mà không có app thì ranh giới là `EXECUTE` + membership role. Hệ quả cần ghi nhận: **bất kỳ ai có credential của login `webdebit_app` đều có thể gọi hàm API với actor bất kỳ đang active**. Bảo vệ khỏi việc này thuộc về cách giữ credential (loopback, secret store, ACL máy chủ) và login/session thật ở M3, chưa có trong fixture. Audit vẫn là app-attested actor, không phải chữ ký không thể chối bỏ của con người.

Audit lưu: `app_actor_id`, `app_session_id`, action, proposal, revision ID và content hash, `database_session_user` (service login) và thời gian DB. Request body/header không được chọn `actor_id`.

## Canonical business revision

### Fixture payload v3

Mỗi revision giữ một object payload với `schema_version` rõ. Fixture chỉ nhận `schema_version=3`; v1 và v2 bị từ chối ("expected version 3"). Đây là fixture mới/cô lập: không migrate dữ liệu thật và không diễn giải lại hash cũ. Tập field (allowlist cố định; field lạ bị từ chối):

- bắt buộc: `schema_version`, `customer_id`, `debt_period`, `warehouse_in_date`, `posting_date`, `reason`, `lines`;
- `warehouse_in_date` là **ngày xe nhập kho** (thay `event_date`);
- `lines`: đúng một debt line với `line_no` nguyên dương, `customer_id`/`debt_period` trùng header, `amount_vnd` (có thể null);
- tùy chọn (thiếu và JSON null cùng hash): `total_vnd`, `source_ref`, `evidence_ref`, `evidence_sha256`, `booking_no`, `container_no`, `price_components`, `period_override_reason`, `period_override_evidence_ref`, `period_override_evidence_sha256`.

Đã bỏ khỏi v2: `kind`, `trip_code`, `opening_snapshot_ref`, `opening_absence_evidence_ref`. Bằng chứng chuyến không nằm trong payload mà ở bảng `trip_opening_resolution`.

**Tiền** chỉ nhận JSON integer dạng chuẩn (`0` hoặc `[1-9][0-9]{0,14}`). `100.0`, `100.00`, `1e2`, `-0`, chuỗi, boolean, số âm, phân số bị **từ chối**, không chuẩn hóa. Hàm submit kiểm văn bản gốc (sau khi bỏ nội dung chuỗi) vì `jsonb` đã tự chuẩn hóa `1e2` thành `100`. Số trong chuỗi như `"ghi chú 1.5"` không bị ảnh hưởng. NULL/vắng là chưa biết và khác 0.

**Ngày** chỉ nhận ASCII `YYYY-MM-DD`; PostgreSQL dựng ngày bằng `make_date` từ thành phần đã kiểm, không phụ thuộc `DateStyle`. `warehouse_in_date` trước `2026-10-14` bị từ chối với thông báo "chuyến cũ, nợ thuộc opening 13/10" (OPENING-FINAL).

**TRIP-KEY.** Payload mang `booking_no` và `container_no` thô (chuỗi hoặc null). DB tính `trip_key = upper(bỏ mọi khoảng trắng(booking || container))`, lưu vào revision, canonical payload (nên nằm trong hash) và posting. "Khoảng trắng" gồm khoảng trắng ASCII/locale và các ký tự Unicode hay lọt vào khi dán từ Sheet: NBSP U+00A0, U+1680, U+2000-U+200F (gồm ZWSP U+200B), U+2028/2029, U+202F, U+205F, U+2060, U+3000, BOM U+FEFF. Booking hoặc container trống sau khi bỏ khoảng trắng → `trip_key` NULL. Ví dụ `" abc 123 "` + `"cont 9"` và `"ABC123"` + `"CONT9"` cho cùng key `ABC123CONT9`. Bảng resolution từ chối key có khoảng trắng hoặc chữ thường.

Charge có thể lưu revision bất biến ở `review_needed` khi trường tiền hoặc bằng chứng còn thiếu: total thiếu/null/0; component list thiếu/null/rỗng; amount component thiếu/null; tổng component hoặc line lệch khi hai vế đã biết; source/evidence, period override hoặc TRIP-KEY thiếu. Khi tháng `debt_period` khác tháng `warehouse_in_date`, kỳ chỉ được maker xác nhận nếu có đủ lý do override, tham chiếu chứng cứ override và SHA-256 chứng cứ; `reason` chung không thay thế ba field này. Không điền tiền, làm tròn, đổi chuỗi thành số hoặc suy định danh. Reference rỗng được giữ nguyên để review nhưng tính là thiếu; hash không-null sai dạng bị từ chối.

Database tự tính reason codes và lưu snapshot bất biến cùng business revision; payload client không được cấp reason codes. Projection owner/test runner tách `submit_time_reasons` bất biến khỏi `warnings` và `current_blockers` tính lại cho revision hiện hành. Revision cũ đánh dấu stale, không sửa snapshot. Hai xác nhận (kỳ, giá) append-only, gắn revision/hash. App API không có SELECT bảng hay EXECUTE projection. Line chuẩn hóa theo số dòng; object key order/whitespace không đổi nghĩa; reference opaque giữ nguyên codepoint.

### Charge review reasons

| Code | Loại | Điều kiện |
|---|---|---|
| `TOTAL_MISSING` | chặn xác nhận giá | `total_vnd` null hoặc vắng |
| `TOTAL_ZERO` | chặn xác nhận giá | `total_vnd` bằng 0 |
| `PRICE_COMPONENTS_MISSING` | chặn xác nhận giá | `price_components` null, vắng hoặc rỗng |
| `COMPONENT_AMOUNT_MISSING` | chặn xác nhận giá | Có component với `amount_vnd` null/vắng |
| `COMPONENT_AMOUNT_ZERO_WARNING` | **cảnh báo, không chặn** (PRICE-ZERO) | Có component amount bằng 0 |
| `COMPONENT_TOTAL_MISMATCH` | chặn xác nhận giá | Total đã biết, mọi component amount đã biết, tổng khác total |
| `LINE_AMOUNT_MISSING` | chặn xác nhận giá | Debt line amount null/vắng |
| `LINE_TOTAL_MISMATCH` | chặn xác nhận giá | Line amount và total đều đã biết nhưng khác nhau |
| `SOURCE_EVIDENCE_MISSING` | chặn xác nhận giá | Source/evidence ref null/rỗng/trắng hoặc evidence hash null |
| `PERIOD_OVERRIDE_EVIDENCE_MISSING` | chặn xác nhận kỳ | Tháng nợ khác tháng nhập kho nhưng thiếu reason, evidence ref hoặc hash của override |
| `TRIP_KEY_MISSING` | chặn duyệt | Booking hoặc container trống |
| `BOOKING_PLACEHOLDER` | chặn duyệt (ĐỀ XUẤT, CÒN MỞ) | Booking chỉ là dấu "/" |
| `DUPLICATE_TRIP_KEY` | chặn duyệt, **tính động** trong projection (ĐỀ XUẤT, CÒN MỞ); không unique cứng ở proposal | Có proposal khác ở trạng thái `approved`/`posted` mà revision hiện hành cùng `trip_key` (trừ booking "/"). Không lưu vào snapshot; biến mất khi proposal kia đổi key |
| `OPENING_RESOLUTION_MISSING` | chặn duyệt; chỉ tính trong projection | `trip_key` không có dòng `ABSENT_FROM_OPENING_APPROVED` (không có dòng, `IN_OPENING`, `UNRESOLVED`, hoặc key NULL) |

Không tính mismatch khi thiếu một trong hai vế hoặc component sum có amount null. `OPENING_RESOLUTION_MISSING` và `DUPLICATE_TRIP_KEY` không được lưu vào snapshot vì dữ liệu liên quan đổi sau submit. Với hai proposal pending cùng key, projection chỉ hiện cảnh báo `DUPLICATE_TRIP_KEY_PENDING_WARNING` (không chặn); khi một proposal được duyệt, proposal còn lại bị chặn duyệt và hiện blocker `DUPLICATE_TRIP_KEY`. Thay cho `SOURCE_RESOLVER_UNAVAILABLE` cố định của bản trước (mọi charge luôn bị chặn bằng một câu `RAISE`).

### Gate theo bước

| Bước | Điều kiện (bất kỳ điều nào sai → từ chối, không ghi gì ngoài giao dịch bị hủy) |
|---|---|
| `confirm_price` | role `price_owner` (maker kiêm price_owner tự xác nhận được; price_owner khác cũng được; maker không có role này bị từ chối); revision hiện hành, đúng hash, không NULL; không có reason chặn giá |
| `confirm_period` | đúng maker của proposal; revision hiện hành; đủ override nếu khác tháng; kỳ `open` (khóa `FOR SHARE`) |
| `approve` | role `checker`; checker khác maker; revision hiện hành đúng hash; mọi kỳ `open`; có xác nhận kỳ; `trip_key` không NULL và booking không phải "/"; có xác nhận giá; checker không phải người xác nhận giá; resolution `ABSENT_FROM_OPENING_APPROVED`; chưa có proposal khác `approved`/`posted` cùng `trip_key` |
| `post` | như approve cho approval/maker/checker; kiểm lại kỳ mở, xác nhận kỳ và giá đúng revision/hash, resolution vẫn `ABSENT_FROM_OPENING_APPROVED`, checker không phải người xác nhận giá của revision, chưa có posting khác cùng `trip_key` (và `UNIQUE(trip_key)` làm chốt chặn) |

Approve tuần tự hóa theo `trip_key` bằng advisory lock theo giao dịch và từ chối khi proposal khác đã `approved`/`posted` cùng key. Post cũng lấy advisory lock và kiểm posting cùng key. Advisory lock + EXISTS chỉ đúng với READ COMMITTED; giao dịch REPEATABLE READ/SERIALIZABLE không thấy posting vừa commit nên `posting.trip_key` có ràng buộc `UNIQUE` làm chốt chặn cuối. Đây là **luật bảo thủ tạm thời**: một posting cho mỗi key, cho đến khi chủ nghiệp vụ chốt chặn trùng theo chuyến hay theo chuyến + loại phí (CÒN MỞ; khi có loại phí, khóa đổi thành `(trip_key, fee_type)`). Hàm nhận NULL revision/hash bị chặn bằng guard rõ ràng; so sánh revision/hash dùng `IS DISTINCT FROM`.

### Canonical bytes và hash

Database tạo canonical JSONB từ allowlist cố định; format/amount/date được kiểm trước khi đưa vào canonical object. Hash v3 là SHA-256 của UTF-8 `webdebit.business-payload.v3\n` + `canonical_jsonb::text` trên PostgreSQL đã pin, tính bằng `sha256()` dựng sẵn (không cần `pgcrypto`). DB là nơi duy nhất tính authoritative hash; app nhận và lưu kết quả. Field tùy chọn bị lược chuẩn hóa thành JSON null.

Hash định danh nội dung, không xác minh actor hoặc nguồn tiền. Nâng chuẩn hóa tạo version mới; không tái diễn giải hash cũ bằng code mới. Presentation data (nhãn hiển thị, thứ tự sort UI, trạng thái mở/đóng) ở bảng/cột riêng, không nằm trong business payload.

### Storage, approval và posting

1. `business_revision` append-only: `(proposal_id, revision_no)`, canonical payload, hash, `trip_key`, reason snapshot, maker app actor/session, timestamp. Không UPDATE/DELETE qua API role. Sửa nghiệp vụ chèn revision kế tiếp; proposal trỏ revision hiện hành. Cùng payload/hash là no-op (có audit `submit_noop`).
2. Approval event append-only và tham chiếu chính xác `(proposal_id, revision_id, content_hash, checker_actor_id, checker_session_id)`. Xác nhận kỳ (maker) và xác nhận giá được ghi thành event riêng, cũng theo revision/hash.
3. Chỉ revision hiện hành có approval khớp ID và hash mới được post. Approve và post khóa, kiểm trạng thái open của kỳ header và mọi kỳ line theo thứ tự ổn định; thiếu state hoặc kỳ đóng đều fail closed.
4. Mỗi lần đổi nghiệp vụ khi chưa post đổi current revision và đưa trạng thái về `review_needed`; approval và xác nhận cũ còn để audit nhưng không áp dụng cho revision mới. Đổi presentation giữ nguyên revision/approval.
5. Khi tích hợp thật, post + trạng thái + posting lines + audit phải nằm trong cùng transaction; lỗi bất kỳ rollback toàn bộ (fixture kiểm bằng deferred constraint trigger). Fixture hiện chỉ lưu một posting row chứa canonical payload; `posted_balance` chỉ tính từ posting, charge pending/approved không vào số dư. Unique constraint chặn post lần hai cho cùng proposal.
6. `UPDATE/DELETE` trigger và grants bảo vệ app path. DB owner/superuser vẫn có thể phá rào; đây là privileged-admin risk cần audit/backup controls, không được gọi là cryptographic immutability.

Prototype PostgreSQL cố tình là acceptance fixture có table riêng; không sửa `pg_ledger_schema.sql` đang được PR #3 characterize và không tạo migration cho `hao`. Bảng `trip_opening_resolution` của fixture **không phải thiết kế production**: bảng production (M3) chỉ được thiết kế sau khi chủ nghiệp vụ duyệt bảng nối opening ↔ mã chuyến.

## Ma trận acceptance

Trạng thái "Fixture" nghĩa là runner `test_pg_versioned_approval.py` có nhóm case tương ứng; kết quả đạt/chưa đạt của một revision cụ thể chỉ nằm ở CI run và `docs/verification.md`, không ghi cứng ở đây.

| ID | Hành vi cần có | Điểm kiểm | Trạng thái hiện tại |
|---|---|---|---|
| I01 | Không có/expired/revoked session không thao tác được | HTTP app + session store | Chưa triển khai |
| I02 | Actor trong request body/header bị bỏ qua; actor lấy từ session server-side | HTTP integration | Chưa triển khai; fixture chỉ kiểm actor/role/session ở tầng DB |
| I03 | Actor disabled, thiếu role, login ngoài role API, session thiếu bị từ chối | DB API fixture | Fixture; auth thật chưa có |
| I04 | Maker tự duyệt bị từ chối; maker/checker khác actor được nhận | PG function + role fixture | Fixture |
| I05 | Một DB service login không bị trình bày nhầm thành người dùng | Audit query/review | Fixture lưu riêng app actor và DB service principal |
| N01 | App chỉ loopback sau Tailscale Serve; không có Funnel/port-forward | host config + từ tailnet/ngoài tailnet | Chưa triển khai/kiểm live |
| N02 | Direct DB/HTTP ngoài tailnet không tới được; spoof proxy headers không đặt actor | network smoke + HTTP integration | Chưa triển khai/kiểm live |
| R01 | Key order/whitespace cùng hash; source ref khác codepoint tạo revision | canonicalization PG18 | Fixture |
| R02 | Business field được kiểm tạo revision/hash mới; input sai cấu trúc bị từ chối; charge thiếu bằng chứng lưu `review_needed` | revision function PG18 | Fixture |
| R03 | Trình bày đổi nhưng business hash/revision không đổi, approval giữ hiệu lực | presentation API + PG query | Fixture |
| R04 | Edit sau approval làm approval/xác nhận revision cũ stale; stale revision không post | approve/edit/post PG18 | Fixture |
| R05 | Post lưu đúng payload/hash/actor của revision đã duyệt; post lần hai bị từ chối | transaction/constraints PG18 | Fixture |
| R06 | Lỗi trễ khi post rollback status, posting và post audit | deferred trigger PG18 | Fixture |
| R07 | App role không đọc bảng, không UPDATE/DELETE; bảng lịch sử append-only | grants/triggers PG18 | Fixture; owner/superuser nằm ngoài bảo đảm |
| C01 | Charge hợp lệ đi hết nhập → xác nhận → duyệt → post và `posted_balance` tăng đúng số tiền khi có resolution `ABSENT_FROM_OPENING_APPROVED` | success path PG18 | Fixture dữ liệu giả; không là bằng chứng dữ liệu thật |
| C02 | Không có resolution, `IN_OPENING` hoặc `UNRESOLVED` thì không duyệt/post được; số dư không đổi | resolution gate PG18 | Fixture; mặc định chặn |
| C03 | TRIP-KEY: chuẩn hóa khoảng trắng (cả Unicode)/hoa thường; thiếu key; booking "/"; trùng key động; cờ trùng hết khi proposal kia đổi key | trip-key PG18 | Fixture; "/" và quy tắc trùng còn CÒN MỞ |
| C04 | Ngày nhập kho < 14/10/2026 bị từ chối; từ 14/10/2026 được nhận | date PG18 | Fixture (OPENING-FINAL) |
| C05 | Tiền chỉ nhận integer chuẩn; `100.0`/`1e2` bị từ chối; NULL khác 0 | canonical PG18 | Fixture |
| C06 | Cấu phần 0đ chỉ cảnh báo; tổng 0/null và các lệch khác chặn xác nhận giá | price PG18 | Fixture (PRICE-ZERO) |
| C07 | Chỉ role `price_owner` xác nhận giá, maker kiêm price_owner tự xác nhận được; người xác nhận giá không làm checker (approve và post) cùng revision | price/approve/post PG18 | Fixture (PRICE-MAKER) |
| C08 | Maker xác nhận kỳ mở; khác tháng cần đủ ba field override; kỳ đóng ở xác nhận/duyệt/post bị từ chối | period PG18 | Fixture |
| C09 | Tranh chấp có `pg_blocking_pids` và PID thật: sửa/duyệt, đóng kỳ/xác nhận kỳ, post song song cùng key (advisory lock), đóng kỳ trước/sau post, đổi resolution trước/sau post; REPEATABLE READ không qua được `UNIQUE(trip_key)` | concurrency PG18 | Fixture |
| G01 | Receipt chỉ post khi được xác minh theo policy được duyệt | Q09, receipt workflow | CÒN MỞ; không có receipt path trong prototype |

Đạt các hàng trên chỉ là bằng chứng fixture cho SQL prototype và revision cụ thể. Chúng không chứng minh app login, Tailscale boundary, account operations, người thật, nguồn ngân hàng, bảng nối opening ↔ mã chuyến thật, hay production readiness.

## Hướng tích hợp sau review

1. Review độc lập spec, canonical field registry, ranh giới tin cậy (đặc biệt hệ quả bỏ HMAC) và acceptance.
2. Sau review, xây app account/session store và route đăng nhập theo sơ đồ trên; dùng server-side session để cung cấp actor/session cho API. Thêm HTTP tests cho cookie/CSRF/expiry/disable/header spoof.
3. Chỉ sau khi P0 write-path, Q03–Q09 policy tương ứng và bảng nối opening ↔ mã chuyến được duyệt, lập migration riêng, review grants/ownership/rollback, chạy trên DB test mới. Không nối fixture vào viewer hoặc DB thật.
4. Trước vận hành cần kiểm cấu hình Tailscale Serve/ACL/firewall và thử từ client trong/ngoài tailnet; tài liệu hay CI không thay bằng chứng mạng.

## Files và lệnh kiểm fixture

- DDL chỉ-fixture: `cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql`.
- Runner chỉ-fixture: `python cong-no-web-handoff/tools/test_pg_versioned_approval.py --report <path>`; báo cáo JSON có `groups`, `success_path`, `failed_cases`, `group_errors`, `cleanup`.
- Test chạy PostgreSQL 18.6 pinned digest trong container tạm; không mount volume, không publish port, dùng `--network none`. Kết quả được phân loại riêng với characterization PR #3.
- `web/actor_assertion.py` và `tests/test_actor_assertion.py` đã bị xóa cùng HMAC (chỉ fixture dùng).
