# Task tiếp theo — harness PostgreSQL cô lập và characterization P0

**Trạng thái:** ĐỀ XUẤT, chưa thực hiện. Task này chỉ kiểm hành vi schema hiện hữu và tái hiện thiếu guard; không triển khai guard/schema mới. Chỉ sau khi task này được giao/duyệt mới thêm integration runner/test. Không DDL lên `hao`, production, Sheet hoặc service thật.

## Mục tiêu và giới hạn

Tạo harness PostgreSQL riêng tái lập được cho schema đang có, rồi characterization có nhãn rõ cho transaction atomicity và approval/role hiện trạng. Xác nhận test chạy đúng database giả. Tách test mô tả behavior đang có khỏi repro lỗi và khỏi acceptance của thiết kế tương lai. Không kết luận auth người thật, chính sách tiền dư/FIFO, hay production readiness.

## Baseline chính xác

- Repo revision: `8365e8aa5ae2517959dedcc52ed8384232458b75` (base PR #1/spec khi soạn task).
- Schema baseline: `cong-no-web-handoff/tools/pg_ledger_schema.sql` đúng tại revision này; không viết lại schema mẫu hoặc đổi nội dung baseline để làm test xanh.
- Dependency trong repo: Docker/Podman runner chưa được cấu hình; schema cần quyền tạo role/schema/table/function trong database trống. Python repo hiện có unittest nhưng không có PostgreSQL integration harness.
- Trước triển khai phải xác nhận revision và hash file schema trên nhánh task mới. Nếu schema đổi, ghi diff và review lại test trước khi chạy.

## Môi trường và cô lập

- Dùng container image PostgreSQL **18.x** (major 18), chọn bản minor đang được hỗ trợ tại ngày chạy và pin image theo digest trong bằng chứng. Lý do: kiểm trên PostgreSQL thật, cùng major hiện đại, không phụ thuộc dịch vụ DB/fixture giả; không dùng embedded/PGlite để tuyên bố concurrency.
- Container và volume tạm có label duy nhất của test run; database tên `webdebit_p0_test_<run-id>`, chỉ bind port loopback ngẫu nhiên. Không trỏ tới host service hoặc DB name khác.
- Credentials random, chỉ tồn tại trong env/secret của test process/container, không log/commit. Không lấy env `.env`, shell profile, production credential, `hao` hay Google Sheet. Harness phải fail closed trừ khi xác nhận container marker + tên database test đúng.
- Tạo login giả riêng (`maker_a`, `checker_b`, `maker_c`) chỉ trong container; các `ledger_maker`/`ledger_checker` của schema tiếp tục là `NOLOGIN` role membership. Seed customer/period/receipt bằng dữ liệu giả nhỏ. Login giả chỉ kiểm DB role/session semantics, không chứng minh người thật.
- Teardown chỉ xóa container/volume do chính test run tạo, kiểm tra label + run-id cụ thể trước khi xóa. Không có lệnh wildcard, dọn volume chung hoặc cleanup theo prefix rộng.

## Test scope và phân loại

1. **Characterization hành vi hiện tại:** nạp đúng schema gốc trên DB trống; ghi nhận PostgreSQL version/image digest; tạo dữ liệu giả; kiểm `submit_entry`/`approve_entry` happy path, maker khác checker theo `session_user`, self-approval bị từ chối, và cùng proposal không sinh posting set thứ hai. Các assertions nói về schema này tại baseline, không phải thiết kế đích.
2. **Repro thiếu guard (kết quả có thể là lỗi mong đợi):** dùng DB owner/test-only mutation để đổi proposal line sau submit rồi gọi approve; chứng minh schema chưa ràng approval với revision/hash. Cố tình tạo hai proposal cùng tiêu thụ một receipt để kiểm tổng allocation; nếu cả hai được post thì lưu repro cap thiếu. Label rõ là defect repro, không policy acceptance. Không mutate baseline file.
3. **Atomicity characterization:** dùng trigger/constraint chỉ trong harness để gây lỗi trễ sau insert posting (ví dụ khi ghi audit); xác nhận statement thất bại và không còn posting/status/audit dở dang. Đây là kiểm transaction của function trong PostgreSQL, không dự đoán mất response sau commit.
4. **Future-design acceptance:** stale-version phải bị chặn, client không tự khai actor, payload key conflict, allocation concurrency, reversal, close-period race chưa được viết như pass criteria cho schema hiện tại. Sau này tạo task implementation riêng khi Q01/Q02 chốt trước approval; Q03–Q08 chặn policy/test tương ứng.

## Điều phối, lệnh và đầu ra

CI/local runner phải có hai connection PostgreSQL độc lập cho concurrency repro. Dùng barrier/advisory test gate hoặc explicit lock để buộc cả hai transaction tới điểm tranh chấp; thả gate theo thứ tự đã định rồi query tổng sau commit. Không dựa vào `sleep` để giả đồng thời. Repro concurrency chỉ cần trong phạm vi lấy receipt; không mở rộng mọi race ở task đầu.

Mẫu lệnh khi triển khai (thay placeholder bằng run-id, secret env và digest đã xác minh; không commit secret): `docker run --detach --name webdebit-p0-test-<run-id> --label codex.test=webdebit-p0 --label codex.run=<run-id> --publish 127.0.0.1::5432 --env POSTGRES_PASSWORD=<generated-random-secret> postgres:18@sha256:<verified-digest>`. Sau readiness check, tạo `webdebit_p0_test_<run-id>` trong đúng container, assert server/database marker, nạp `psql -v ON_ERROR_STOP=1 -d <test-db> -f cong-no-web-handoff/tools/pg_ledger_schema.sql`, seed fixture và gọi runner với connection string dựng từ cổng loopback được Docker cấp. Tách báo cáo nhóm `characterization`, `defect_repro`, `atomicity`. Khi hoàn tất lấy `docker inspect`/SQL version evidence, rồi kiểm label và run-id khớp chính xác trước `docker rm -f webdebit-p0-test-<run-id>`; mọi volume gắn vào container phải được tạo riêng theo cùng run-id và chỉ volume đó mới được xóa. Runner/README task sau phải ghi các lệnh chạy thực tế và không in password. Không chạy lệnh này trong lượt chuẩn bị spec.

Hoàn thành khi: (a) harness fail-closed nếu nhầm DB/port; (b) đúng SQL baseline tải thành công trên container trống; (c) test phân loại và kết quả đúng dự kiến ở trên; (d) mọi fixture/container/volume chỉ thuộc run-id; (e) teardown chỉ dọn tài nguyên riêng; (f) log có commit, schema SHA-256, PostgreSQL `version()`, image digest, lệnh chạy, expected/actual, exit code và giới hạn; (g) không có bí mật/data thật và `git diff` chỉ gồm task.

**Sau task này:** chủ nghiệp vụ quyết Q01 (principal/quyền) và Q02 (revision/content approval), cập nhật spec; rồi mới mở task riêng triển khai guard versioned approval. Atomicity test không chứng minh client nhận response sau commit; actor fixture không chứng minh xác thực người thật. Q03–Q08 tiếp tục chặn nghiệm thu allocation/FIFO, idempotency nguồn, reversal và khóa kỳ theo policy.
