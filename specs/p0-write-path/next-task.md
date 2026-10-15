# Task tiếp theo — harness PostgreSQL cô lập và characterization P0

**Trạng thái:** Harness và CI đã có trong draft PR #3, nhánh `test/pg18-schema-characterization`; head CI mới nhất được xác minh là `e50451a2f69f83e1d2e4f9058dc9be39e7a61cf8`. Run `38686910554` thành công với 7/7 jobs; artifact PostgreSQL 18.6 có 9 assertion, report revision `62e9da42059329508ba746174980fd60535343c7`, schema SHA-256 LF-normalized `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`, image digest `sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`, cleanup `verified_and_removed`. Stale-content case là `repro_success`, không phải acceptance. Máy local vẫn chưa chạy DB do Docker daemon không khởi động. Không DDL lên `hao`, production, Sheet hoặc service thật.

## Mục tiêu và giới hạn

Tạo harness PostgreSQL riêng tái lập được cho schema đang có, rồi characterization có nhãn rõ cho transaction atomicity và approval/role hiện trạng. Xác nhận test chạy đúng database giả. Tách test mô tả behavior đang có khỏi repro lỗi và khỏi acceptance của thiết kế tương lai. Không kết luận auth người thật, chính sách tiền dư/FIFO, hay production readiness.

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
4. **Future-design acceptance:** stale-version phải bị chặn, client không tự khai actor, payload key conflict, allocation concurrency, reversal, close-period race chưa được viết như pass criteria cho schema hiện tại. Sau này tạo task implementation riêng khi Q01/Q02 chốt trước approval; Q03–Q08 chặn policy/test tương ứng.

## Điều phối, lệnh và đầu ra

CI/local runner phải có hai connection PostgreSQL độc lập cho concurrency repro. Giữ row lock tường minh, quan sát checker đang chờ bằng `pg_blocking_pids`, rồi thả lock theo thứ tự xác định và query sau commit. Không dùng `sleep` làm bằng chứng đồng thời. Hai checker cùng approve một proposal là serialization characterization, không phải allocation-cap acceptance.

Lệnh chuẩn: `python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report <path>`. Runner tự tạo container/volume run-id, `--network none`, database `webdebit_ledger`, xác minh identity/marker, nạp SQL gốc với `ON_ERROR_STOP`, và chỉ teardown tài nguyên có tên chính xác, ID, label và run-id khớp. Cleanup luôn dò container kể cả khi `docker run --detach` lỗi/timeout sau khi Docker đã tạo container; test fault-injection mô phỏng timeout sau tạo và xác nhận chỉ container đúng run bị xóa, đồng thời xác nhận label run-id lệch thì từ chối xóa. Digest PostgreSQL 18.6 được pin trong runner và CI. Không ghi log bí mật.

CI PostgreSQL run `38683750234`, `38684269409`, lần lỗi cleanup đã truy nguyên `38686717095`, và run mới nhất `38686910554` được giữ trong [hồ sơ kiểm chứng](../../docs/verification.md). Run mới nhất có artifact 9 assertion, cleanup verified và 7/7 jobs thành công trên head `e50451a`. Kết quả repro được gắn `repro_success`, không là acceptance. Còn chờ draft PR #3 review/merge; nếu PR #2 đổi schema thì đối chiếu diff và chạy lại trước khi dựa vào kết quả này. Các gate Q01–Q02 và Q03–Q08 vẫn nguyên.

**Bước kế tiếp, chưa triển khai:** chủ nghiệp vụ và chủ vận hành/auth cần chốt Q01–Q02 trong [danh sách quyết định](decisions-needed.md), ghi người chốt, ngày/phạm vi và lựa chọn cụ thể:

- **Q01:** principal chuẩn là gì (ưu tiên tài khoản cá nhân qua SSO hay DB login cá nhân); có cấm tài khoản chia sẻ không; quy trình cấp/thu hồi quyền; ủy quyền và tài khoản service; cách audit principal người thao tác tới DB/service identity; ai được maker/checker và cách cưỡng chế tách vai trò.
- **Q02:** chính xác field nào tạo nội dung được duyệt (khách/kỳ/loại/số tiền/dòng phân bổ/ngày/source/evidence/lý do và metadata liên quan); khi nào nội dung bị đóng băng; mọi sửa đổi có tạo revision mới không; sửa/withdraw/re-submit ra sao; approval gắn revision/hash nào và approval cũ có mất hiệu lực không.

Đề xuất kỹ thuật hiện tại trong Q01/Q02 chưa là quyết định. Chỉ sau khi có quyết định rõ, mới cập nhật spec/acceptance và mở phần triển khai versioned approval; không tự chọn policy hoặc xem `repro_success` là đạt. Atomicity test không chứng minh client nhận response sau commit; actor fixture không chứng minh xác thực người thật. Q03–Q08 tiếp tục chặn nghiệm thu allocation/FIFO, idempotency nguồn, reversal và khóa kỳ theo policy.
