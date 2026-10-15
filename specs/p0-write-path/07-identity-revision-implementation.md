# P0-02 — Thiết kế danh tính và duyệt theo revision

Ngày: 15/10/2026. Trạng thái: **ĐỀ XUẤT KỸ THUẬT để review**. Q01/Q02 đã chốt ở mức nguyên tắc; thiết kế này cụ thể hóa một phương án triển khai. Fixture PostgreSQL kèm theo là prototype cô lập, không phải migration, app login, hay đường ghi tiền được bật.

## Phạm vi và bằng chứng nền

- Ứng dụng self-host trên một máy. Chỉ thiết bị trong tailnet của chủ máy tới được trang login. Mỗi người có app account riêng; maker và checker là hai người khác nhau; actor xuất phát từ session server-side.
- Q02: approval gắn với nội dung của revision bất biến. Mọi đổi nghĩa nghiệp vụ tạo revision mới và cần approval mới. Chỉnh sửa trình bày không đổi nghĩa không tạo revision.
- Viewer hiện tại `cong-no-web-handoff/web/ledger_app.py` chỉ đọc và bind `127.0.0.1`; chưa có login/session hoặc route ghi. `tools/pg_ledger_schema.sql` lấy maker, checker và audit actor từ `session_user`; proposal lines có thể được đọc lúc duyệt sau khi owner sửa. Đây là kiểm tra mã tại checkout, không phải runtime.
- PR #3 characterization đã chạy trên PostgreSQL 18.6; stale-content là `repro_success`, không phải acceptance của guard. Chi tiết revision/run nằm trong `docs/verification.md`.

Q03–Q08 và Q09 vẫn mở. Prototype chỉ dùng một operation fixture giả kiểu `charge_fixture`, không nhận receipt, không chọn chính sách tiền dư/FIFO ngoại lệ/reversal/khóa kỳ/receipt verification và không được nối vào viewer.

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
- Mọi POST có CSRF token gắn session. Login lỗi trả thông báo chung và rate-limit theo account cùng nguồn mạng; log không ghi mật khẩu, cookie, signing key hoặc nội dung chứng từ.
- Audit account ghi actor quản trị, account bị tác động, thay đổi role/status và thời điểm. Không tự cho admin vượt maker/checker hoặc sửa posting.

Đây là thiết kế đề xuất; chưa có account/session code. TTL, cơ chế rate-limit và vận hành bootstrap cần được chủ vận hành review trước khi bật login.

## App actor → DB audit

DB session login vẫn là `webdebit_app` dùng chung cho process, nên `session_user` chỉ chứng minh service account. Không ghi nó như bằng chứng người bấm duyệt.

Mỗi request ghi được server dựng từ principal đã xác thực trong session store: `actor_id`, `session_id`, role đang có, action, nonce một lần, thời điểm phát hành và operation scope. App ký assertion HMAC-SHA-256 bằng key riêng của service. DB role không đọc được key registry và chỉ gọi API `SECURITY DEFINER`; hàm DB xác minh chữ ký, actor đang active, role, action, scope, tuổi assertion và nonce chưa dùng. Request body/header không được chọn `actor_id`.

Audit lưu tách:

- `app_actor_id`, `app_session_id`, action, entity/proposal, revision ID và content hash;
- `session_user` DB (service login), `key_id`, assertion nonce và thời gian DB.

HMAC bảo vệ khỏi client chỉ có DB service credential nhưng không có signing key; không bảo vệ khi app process, signing key hoặc DB owner/superuser bị chiếm. Đây là app-attested actor, không phải chữ ký không thể chối bỏ của con người. Signing key đặt trong secret store/ACL riêng, key rotation có `key_id` và thời gian overlap; không đưa key vào repo. Prototype dùng key giả chỉ trong container.

## Canonical business revision

### Payload v1

Mỗi revision giữ một object payload với schema version rõ. Tập business field cần được version hóa và review trước khi thêm:

- kind, customer ID và debt period;
- từng line có line number ổn định, customer/period, amount VND nguyên;
- total VND nguyên, event date và posting date;
- source reference, evidence reference/hash, reason;
- các field quyết định được thêm hợp lệ cho operation tương ứng (ví dụ original posting khi reversal hoặc allocation khi receipt).

Trong prototype `charge_fixture`, danh sách field hẹp được kiểm chặt; receipt/reversal không được nhận. Một field lạ bị từ chối, không bị bỏ khỏi hash. Line được chuẩn hóa theo line number; line number trùng bị từ chối. Object key order và whitespace không có nghĩa; array line order chỉ được chuẩn hóa khi line number tường minh. Chuỗi opaque như customer/source/evidence reference và reason giữ nguyên codepoint; prototype không NFC-normalize để hai reference khác byte không bị gộp.

### Canonical bytes và hash

Database tạo canonical JSONB từ allowlist field cố định; format/amount/date được kiểm trước khi đưa vào canonical object. V1 bytes là UTF-8 của `webdebit.business-payload.v1\n` + `canonical_jsonb::text` trên PostgreSQL đã pin. `SHA-256(bytes)` là `content_hash`. DB là nơi duy nhất tính authoritative hash; app nhận và lưu kết quả, không tự tạo hash khác.

Không dùng float cho VND; NULL khác 0. Hash định danh nội dung, không xác minh actor hoặc nguồn tiền. Nâng chuẩn hóa tạo version mới; không tái diễn giải hash cũ bằng code mới. Presentation data (nhãn hiển thị, thứ tự sort UI, trạng thái mở/đóng) ở bảng/cột riêng, không nằm trong business payload và không được dùng để thay nghĩa dữ liệu.

### Storage, approval và posting

1. `proposal_revision` append-only: `(proposal_id, revision_no)`, canonical payload, hash, maker app actor/session, timestamp. Không UPDATE/DELETE qua API role. Sửa nghiệp vụ chèn revision kế tiếp; proposal trỏ revision hiện hành. Cùng payload/hash là no-op, không tạo revision mới.
2. Approval event là append-only và tham chiếu chính xác `(proposal_id, revision_id, content_hash, checker_actor_id, checker_session_id)`. Actor maker phải khác checker.
3. Chỉ revision hiện hành có approval khớp cả ID lẫn hash mới được post. Post đọc payload từ revision đã duyệt, không đọc lại bảng staging mutable; posting lưu revision ID/hash và actor maker/checker.
4. Mỗi lần đổi nghiệp vụ khi chưa post đổi current revision và đưa trạng thái về pending; approval cũ còn để audit nhưng không cho post revision mới. Đổi presentation giữ nguyên revision/approval.
5. Khi tích hợp thật, post + trạng thái + posting lines + audit phải nằm trong cùng transaction; lỗi bất kỳ rollback toàn bộ. Fixture hiện chỉ lưu một posting row chứa canonical payload, chưa có posting lines. Unique constraint chặn post lần hai cho cùng proposal. Posting và approval không sửa/xóa bởi API role.
6. `UPDATE/DELETE` trigger và grants bảo vệ app path. DB owner/superuser vẫn có thể phá rào; đây là privileged-admin risk cần audit/backup controls, không được gọi là cryptographic immutability.

Prototype PostgreSQL cố tình là acceptance fixture có table riêng; không sửa `pg_ledger_schema.sql` đang được PR #3 characterize và không tạo migration cho `hao`.

## Ma trận acceptance

| ID | Hành vi cần có | Điểm kiểm | Trạng thái hiện tại |
|---|---|---|---|
| I01 | Không có/expired/revoked session không thao tác được | HTTP app + session store | Chưa triển khai |
| I02 | Actor trong request body/header bị bỏ qua; actor lấy từ session server-side | HTTP integration | Chưa triển khai; DB assertion fixture kiểm chữ ký gắn actor/action/scope |
| I03 | Actor disabled, thiếu role, assertion sai/già/sai scope hoặc nonce replay bị từ chối | DB API + app auth | Prototype kiểm trên PG18; auth thật chưa có |
| I04 | Maker tự duyệt bị từ chối; maker/checker khác actor được nhận | PG function + role fixture | Prototype kiểm trên PG18 |
| I05 | Một DB service login không bị trình bày nhầm thành người dùng | Audit query/review | Prototype lưu riêng app actor và DB service principal |
| N01 | App chỉ loopback sau Tailscale Serve; không có Funnel/port-forward | host config + từ tailnet/ngoài tailnet | Chưa triển khai/kiểm live |
| N02 | Direct DB/HTTP ngoài tailnet không tới được; spoof proxy headers không đặt actor | network smoke + HTTP integration | Chưa triển khai/kiểm live |
| R01 | JSON key order/whitespace tương đương cùng hash; line array chuẩn theo line_no; source ref khác codepoint tạo revision | canonicalization PG18 | Prototype kiểm trên PG18 |
| R02 | Business field được kiểm tạo revision/hash mới; input không hợp lệ bị từ chối | revision function PG18 | Prototype kiểm tổng, khách, kỳ, ngày, source/evidence, reason và line; unknown field, VND lẻ và tổng lệch bị từ chối. Fixture chỉ nhận `charge_fixture` v1 |
| R03 | Trình bày đổi nhưng business hash/revision không đổi, approval giữ hiệu lực | presentation API + PG query | Prototype kiểm trên PG18 |
| R04 | Edit sau approval làm approval revision cũ stale; stale revision không post | approve/edit/post PG18 | Prototype kiểm trên PG18 |
| R05 | Post lưu đúng payload/hash/actor của revision đã duyệt; duplicate post bị từ chối | transaction/constraints PG18 | Prototype kiểm trên PG18 |
| R06 | Lỗi trễ khi post rollback status, posting và post audit | deferred trigger PG18 | Prototype kiểm trên PG18 |
| R07 | App role không UPDATE/DELETE revision, approval, posting hay audit | PostgreSQL grants/triggers | Fixture kiểm direct read/update và các mutation append-only đại diện trên revision, approval, posting, audit. Owner/superuser nằm ngoài bảo đảm |
| R08 | Thiếu evidence reference hoặc evidence hash sai định dạng bị từ chối | payload validation PG18 | Prototype kiểm cả hai trường hợp thiếu/sai |
| G01 | Receipt chỉ post khi được xác minh theo policy được duyệt | Q09, receipt workflow | CÒN MỞ; không có receipt path trong prototype |

Đạt các hàng PG18 chỉ là bằng chứng fixture cho SQL prototype và revision cụ thể. Chúng không chứng minh app login, Tailscale boundary, account operations, người thật, nguồn ngân hàng, hoặc production readiness.

## Hướng tích hợp sau review

1. Review độc lập spec, canonical field registry, HMAC trust boundary và acceptance.
2. Sau review, xây app account/session store và route đăng nhập theo sơ đồ trên; dùng server-side session để ký actor assertion. Thêm HTTP tests cho cookie/CSRF/expiry/disable/header spoof.
3. Chỉ sau khi P0 write-path và Q03–Q09 policy tương ứng được duyệt, lập migration riêng, review grants/ownership/rollback, chạy trên DB test mới. Không nối fixture vào viewer hoặc DB thật.
4. Trước vận hành cần kiểm cấu hình Tailscale Serve/ACL/firewall và thử từ client trong/ngoài tailnet; tài liệu hay CI không thay bằng chứng mạng.

## Files và lệnh kiểm fixture

- DDL chỉ-fixture: `cong-no-web-handoff/tools/pg_versioned_approval_fixture.sql`.
- Runner chỉ-fixture: `python cong-no-web-handoff/tools/test_pg_versioned_approval.py --report <path>`.
- Test chạy PostgreSQL 18.6 pinned digest trong container tạm; không mount volume, không publish port, dùng `--network none`. Kết quả được phân loại riêng với characterization PR #3.
