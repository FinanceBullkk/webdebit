# PostgreSQL characterization hoàn tất và bước P0 tiếp theo

**Trạng thái harness hiện tại (15/10/2026):** PR #3 `test/pg18-schema-characterization` vẫn OPEN/Draft, head `75d9ff994ab803b18932f8f306a507f181356c71`, base PR #2 `docs/p0-write-path-specs`. GitHub run [`38695774411`](https://github.com/FinanceBullkk/webdebit/actions/runs/38695774411) đạt 7/7 jobs trên đúng head này; artifact `pg-ledger-characterization` ghi 9 assertion và cleanup `verified_and_removed`. Stale-content vẫn mang nhãn `repro_success`, không phải acceptance. Run này **không gồm** bốn thay đổi tài liệu chưa commit trong checkout PR #3. PR #1/#2/#3 hiện đều OPEN/Draft.

**Bước Q01/Q02 trong worktree riêng:** prototype acceptance fixture đã chạy cục bộ trên PostgreSQL 18.6 pinned digest `sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`, `--network none`, không port/volume mount; 58 assertion đạt và container được xác minh rồi xóa. Chi tiết hash/runner ở `docs/verification.md`. Kết quả là test fixture của thiết kế, không phải CI của diff hiện tại, login/session/Tailscale thật hay DB/service/Sheet thật. Bốn thay đổi tài liệu gốc được giữ nguyên ở checkout PR #3; bản làm tiếp nằm trong nhánh `feature/p0-actor-revisions`.

## Mục tiêu và giới hạn

Phần này ghi lại mục tiêu harness đã hoàn tất: characterization có nhãn cho transaction atomicity và approval/role của schema gốc. Tách behavior hiện tại khỏi defect repro và acceptance tương lai. Các kiểm tra phiên bản/danh tính hiện được thiết kế riêng trong [P0-02](02-versioned-approval-identity.md) và [spec kỹ thuật](07-identity-revision-implementation.md); không kết luận auth người thật, policy receipt hay production readiness.

## Baseline chính xác

- Repo revision ban đầu: `315d2d150d17ac77cda31f0ef3b61f696cd20ea5` (đầu PR #2 hiện hành khi task bắt đầu).
- Schema baseline: `cong-no-web-handoff/tools/pg_ledger_schema.sql` nguyên bản trong checkout của nhánh task; ghi revision và SHA-256 ở báo cáo chạy. Không viết lại schema mẫu hoặc đổi nội dung baseline để làm test xanh.
- Dependency trong repo: Docker/Podman runner chưa được cấu hình; schema cần quyền tạo role/schema/table/function trong database trống. Python repo hiện có unittest nhưng không có PostgreSQL integration harness.
- Trước triển khai phải xác nhận revision và hash file schema trên nhánh task mới. Nếu schema đổi, ghi diff và review lại test trước khi chạy.

## Môi trường và cô lập

- Dùng container image PostgreSQL **18.x** (major 18), chọn bản minor đang được hỗ trợ tại ngày chạy và pin image theo digest trong bằng chứng. Lý do: kiểm trên PostgreSQL thật, cùng major hiện đại, không phụ thuộc dịch vụ DB/fixture giả; không dùng embedded/PGlite để tuyên bố concurrency.
- Container và volume tạm có label duy nhất của test run; chỉ tạo database `webdebit_ledger` vì schema gốc ghi cứng tên này trong `REVOKE`/`GRANT`. Không publish port, dùng `--network none`, không trỏ tới host service hoặc DB khác.
- Dùng PostgreSQL 18.6 với digest đã xác minh trong registry; harness chuẩn Python + Docker CLI/`docker exec`/`psql`. Không lấy env `.env`, shell profile, production credential, `hao` hay Google Sheet. Trước mọi DDL, fail closed nếu container ID/labels/volume, database hoặc durable run marker không đúng.
- Tạo login giả riêng (`maker_a`, `checker_b`, `maker_checker` có cả hai role) chỉ trong container; các `ledger_maker`/`ledger_checker` của schema tiếp tục là `NOLOGIN` role membership. Seed cutover/customer/kỳ/chứng cứ bằng dữ liệu giả. Login giả chỉ kiểm DB role/session semantics, không chứng minh người thật.
- Teardown chỉ xóa container/volume do chính test run tạo, kiểm tra label + run-id cụ thể trước khi xóa. Không có lệnh wildcard, dọn volume chung hoặc cleanup theo prefix rộng.

## Test scope và phân loại

1. **Characterization hành vi hiện tại:** nạp đúng schema gốc trên DB trống; ghi nhận PostgreSQL version/image digest; tạo dữ liệu giả; kiểm `submit_entry`/`approve_entry` happy path, maker khác checker theo `session_user`, self-approval bị từ chối, và cùng proposal không sinh posting set thứ hai. Các assertions nói về schema này tại baseline, không phải thiết kế đích.
2. **Repro thiếu guard (kết quả có thể là lỗi mong đợi):** dùng DB owner/test-only mutation để đổi proposal line sau submit rồi gọi approve; chứng minh schema chưa ràng approval với revision/hash. Schema baseline không có receipt entity hoặc allocation ledger riêng, nên bỏ test “hai proposal cùng tiêu thụ một receipt”; chỉ ghi khoảng trống mô hình để task allocation sau Q03–Q04 kiểm tiếp. Không dùng hai receipt độc lập để tuyên bố cùng-receipt cap bị vượt. Label rõ là defect repro, không policy acceptance. Không mutate baseline file.
3. **Atomicity characterization:** dùng trigger/constraint chỉ trong harness để gây lỗi trễ sau insert posting (ví dụ khi ghi audit); xác nhận statement thất bại và không còn posting/status/audit dở dang. Đây là kiểm transaction của function trong PostgreSQL, không dự đoán mất response sau commit.
4. **Future-design acceptance:** không gán các yêu cầu sau cho schema gốc/PR #3. Q01/Q02 có ma trận riêng ở `07-identity-revision-implementation.md`; fixture PostgreSQL 18 tách biệt kiểm assertion actor, revision, approval, posting và rollback. Q03–Q08 cùng Q09 tiếp tục chặn policy/acceptance tương ứng; Q09 đặc biệt chưa cho phép receipt eligibility.

## Điều phối, lệnh và đầu ra

CI/local runner phải có hai connection PostgreSQL độc lập cho concurrency repro. Giữ row lock tường minh, quan sát checker đang chờ bằng `pg_blocking_pids`, rồi thả lock theo thứ tự xác định và query sau commit. Không dùng `sleep` làm bằng chứng đồng thời. Hai checker cùng approve một proposal là serialization characterization, không phải allocation-cap acceptance.

Lệnh chuẩn: `python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report <path>`. Runner tự tạo container/volume run-id, `--network none`, database `webdebit_ledger`, xác minh identity/marker, nạp SQL gốc với `ON_ERROR_STOP`, và chỉ teardown tài nguyên có tên chính xác, ID, label và run-id khớp. Cleanup luôn dò container kể cả khi `docker run --detach` lỗi/timeout sau khi Docker đã tạo container; test fault-injection mô phỏng timeout sau tạo và xác nhận chỉ container đúng run bị xóa, đồng thời xác nhận label run-id lệch thì từ chối xóa. Digest PostgreSQL 18.6 được pin trong runner và CI. Không ghi log bí mật.

Các run lịch sử `38683750234`, `38684269409`, `38686717095`, `38686910554` và `38687477502` vẫn được giữ trong [hồ sơ kiểm chứng](../../docs/verification.md); run hiện tại là `38695774411` trên head PR #3. Đây là bằng chứng code/CI của schema gốc, không bao gồm dirty diff. Bước kế tiếp đã tách riêng khỏi PR #3 để không đổi mục đích characterization.

## Bước tiếp theo sau harness

Q01/Q02 đã chốt về nghiệp vụ; [spec kỹ thuật](07-identity-revision-implementation.md) và fixture prototype nay có để review. Fixture chỉ áp dụng cho payload `charge_fixture` giả, actor assertion và immutable revision. Nó không được nối vào viewer, không là migration, và không mở đường ghi thật.

- **Q01:** tài khoản cá nhân, server-side session, role/account lifecycle, loopback sau Tailscale Serve và HMAC assertion actor→DB được định nghĩa ở mức đề xuất. Login/session thật, bootstrap/offboarding, CSRF, tailnet ACL/proxy/firewall và audit vận hành vẫn chưa triển khai/kiểm.
- **Q02:** canonicalization v1, revision append-only, approval/post gắn revision/hash, no-op presentation và stale approval được định nghĩa; PG18 fixture là bằng chứng riêng cho prototype.
- **Q03–Q08 và Q09:** còn mở; không đưa quy tắc dư/FIFO ngoại lệ/reversal/close kỳ/receipt verification vào fixture hoặc tuyên bố acceptance.

Không xem `repro_success` là đạt. CI run `38695774411` không kiểm dirty docs hoặc fixture mới; PostgreSQL fixture local không chứng minh runtime auth/network hay service thật. Mọi migration/route ghi tiếp theo cần review độc lập và gate riêng.
