# Kiểm chứng thay đổi ngày 15–16/10/2026

## Nền tích hợp và chuỗi PR

Nền tích hợp dùng cho hồ sơ M1 là head PR #7 `c439d13c2794e7bda5f8567816bf80db8396f931` trên nhánh `fix/m1-review-readiness`; đây là SHA mới nhất của PR #7, không phải `worktrees/foundation`. Chuỗi phụ thuộc chính dự kiến là **#1 → #2 → #3 → #5 → #6 → #7**; PR #4 OpenSpec là nhánh riêng, không tự nhập. PR #8–#11 là chuỗi foundation đã gộp vào nhánh M1 này, gồm fixture M2, viewer M1 và hồ sơ ACL.

Đường merge tiếp theo: review/hoàn tất PR #7 trên base `fix/m2-review-hardening`, sau đó chỉ merge theo thứ tự dependency đã duyệt vào nhánh đích; cuối cùng mới cập nhật `main`. Bước này chỉ tạo diff tài liệu trên worktree `codex/a01-a04-docs`, chưa merge, commit hoặc push.

## Tóm tắt T02–T10 (review khắc phục M1/M2, 15–16/10/2026)

Cập nhật: 16/10/2026. Nguồn: các handoff và bảng điều phối của đợt review khắc phục, lưu ngoài Git. Mọi dòng dưới đây trừ T07 là kết quả **CI fixture dữ liệu giả** trên đúng SHA nêu ở cột "Output SHA", **không phải kiểm live**; T07 là kiểm chỉ đọc trên máy chủ thật (15/10/2026). Với các dòng CI: không có DB, Sheet, service, ACL, ngân hàng hay người thật. Docker cục bộ không chạy, nên PostgreSQL chỉ chạy trong container cô lập của CI (image PostgreSQL 18.6 ghim digest, không mạng, dọn xong được xác minh). T01 (SHA `59413fd`, run 38751000719 8/8, fixture 122/122) đã ghi ở mục T01 phía dưới.

PR #6 (T01–T06) và PR #7 (T08–T10) vẫn là draft, chưa merge. Quyết định 16/10/2026 ([SIMPLIFY](decisions.md)) thay một phần thiết kế mà các fixture dưới đây kiểm (HMAC từng lệnh, kind generic, canonical v2); 565/565 chỉ mô tả fixture tại `87917ff`. Kết quả sau khi sửa theo SIMPLIFY ở mục "Nền móng 16/10" ngay dưới bảng.

| Mốc | Phạm vi | Output SHA | Run CI | Số case | Giới hạn |
|---|---|---|---|---|---|
| T02 | Canonical v2: ngày ASCII ISO, tiền numeric chính xác, từ chối v1 | `8b82cd9` | [38756849363](https://github.com/FinanceBullkk/webdebit/actions/runs/38756849363), 8/8 job | Fixture PG 181/181; Python 32/32 | Chỉ CI fixture; chưa có mã chuyến TRIP-KEY, resolver. |
| T03 | Charge thiếu căn cứ lưu thành bản ghi `review_needed` bất biến, có reason code | `09a9236` | [38761007433](https://github.com/FinanceBullkk/webdebit/actions/runs/38761007433), 8/8 | Fixture PG 370/370; 15 charge nháp, đều từ chối duyệt/post | Chỉ CI fixture; `trip_code` còn mờ đục. |
| T04 | Xác nhận kỳ và giá gắn revision/hash; chứng cứ lệch kỳ; kỳ đóng chặn | `dddf561` | [38764738544](https://github.com/FinanceBullkk/webdebit/actions/runs/38764738544), 8/8 | Fixture PG 507/507; 18 charge nháp, đều từ chối duyệt/post | Chỉ CI fixture; resolver cố định vẫn chặn mọi charge. |
| T05 | `posted_balance` chỉ tính từ posting; 4 kịch bản tranh chấp có PID/blocker thật | `1157155` | [38770149510](https://github.com/FinanceBullkk/webdebit/actions/runs/38770149510), 8/8 | Fixture PG 565/565; đối chứng dương +102 VND trên kind generic | Chỉ CI fixture; đối chứng không phải charge thật. |
| T06 | Review độc lập mã M2; sửa tài liệu phân biệt TRIP-KEY đã chốt với phần cài đặt còn mở | `87917ff` | [38774482374](https://github.com/FinanceBullkk/webdebit/actions/runs/38774482374), 8/8 | Fixture PG 565/565; 18/18 charge nháp vẫn bị chặn | Review PASS trong phạm vi T06; **M2 CHƯA ĐẠT**, cổng tài chính còn mở. Chỉ CI fixture. |
| T07 | Kiểm chỉ đọc live (15/10/2026), tại mã nền `bfd65f2` | Không đổi mã | Không có CI | Không có số case | Quan sát thời điểm kiểm, không là trạng thái hôm nay. Opening live khớp (496 kỳ, 65.051.673.578 VND, 46 `NO_BASELINE`, 0 proposal/posting). **M1-3 CÒN MỞ:** một login thường có đường ghi qua role maker; viewer thiếu `SELECT` ba view tổng hợp M1. Hai đề xuất ACL chưa chạy, chưa duyệt; chi tiết đối tượng DB giữ ngoài repo. |
| T08 | Truy vấn ngoại lệ/provenance chỉ đọc cho M1 | `9e7de1e` | [38779011097](https://github.com/FinanceBullkk/webdebit/actions/runs/38779011097), 9/9 | M1 truy vấn PG 13/13; M2 565/565; Python 32/32; `npm test` 20/20 | Chỉ CI fixture; không đổi viewer live hay quyền. |
| T09 | Viewer: trang `/exceptions`, cảnh báo, bỏ giới hạn 250 khách/kỳ, health kiểm provenance | `79deb8c` | [38785897368](https://github.com/FinanceBullkk/webdebit/actions/runs/38785897368), 9/9 | M1 PG 15/15; M2 565/565; Python 49/49; `npm test` 20/20 | Chỉ CI fixture; chưa test browser trên viewer thật. |
| T10 | Exporter/verifier M1: NULL chỉ tính 0 khi nguồn và DB cùng chứng minh không có sự kiện | `0e1330b` | [38794658173](https://github.com/FinanceBullkk/webdebit/actions/runs/38794658173), 9/9 | M1 PG 16/16; Python 68/68; `npm test` 20/20 | Chỉ fake replay và PG cô lập; chưa review độc lập mã T10; không chạm capture, Sheet hay DB thật. |

Đọc kết quả: tại `0e1330b` baseline nhánh nền là Python 68/68 và `npm test` 20/20 (chạy cục bộ), CI 9/9 (ĐÃ KIỂM CHỨNG bằng CI fixture; phiên điều phối ghi đã kiểm lại ngày 16/10). Ở mọi mốc có artifact PostgreSQL, `tested_tree` khớp tree của head và cleanup là `verified_and_removed`. T11–T13 của đợt Codex không chạy; phần việc tương ứng được làm lại ở mục dưới. Tại thời điểm các run này M1 live chưa được kiểm; hồ sơ triển khai/kiểm hiện tại nằm ở mục M1 live bên dưới. M2 vẫn CHƯA ĐẠT.

## Nền móng 16/10/2026 (PR #8, #9, #10 đã gộp vào `fix/m1-review-readiness`)

Mỗi PR do một phiên Sonnet viết và một phiên Opus review chỉ đọc; review lần hai cho PASS cả ba, không còn P0/P1. Người dùng merge ngày 16/10/2026. Tất cả là **CI fixture dữ liệu giả**, không phải live.

| PR | Phạm vi | Head đã review | Run CI | Kết quả |
|---|---|---|---|---|
| #8 | Ghi các quyết định 15–16/10 vào docs/spec | `e36a55c` | [38807114396](https://github.com/FinanceBullkk/webdebit/actions/runs/38807114396), 9/9 | Docs, không đổi mã. |
| #10 | Fixture M2 theo SIMPLIFY: bỏ HMAC và kind generic, `trip_key` tính trong DB, bảng resolution, UNIQUE `posting.trip_key`, cấu phần 0đ cảnh báo, vai trò `price_owner` | `a15c7bf` | [38808180498](https://github.com/FinanceBullkk/webdebit/actions/runs/38808180498), 9/9 | Fixture PG 213/213, có đường charge thành công với resolution giả và case mặc định bị chặn; 7 kịch bản tranh chấp có PID/blocker thật. Review đã tái hiện và đóng lỗi ghi trùng posting dưới REPEATABLE READ. |
| #9 | Viewer M1: review T10 (delta sổ cũ trống là lỗi), gọn bộ lọc `/exceptions`, invariant health dùng chung, test browser trên `LedgerHandler` thật (desktop và 390px), gói deploy có manifest/preflight/rollback, đề xuất ACL năm view | `c3e145c` | [38807717483](https://github.com/FinanceBullkk/webdebit/actions/runs/38807717483), 9/9 | M1 PG 16/16. Không deploy, không GRANT/REVOKE. |

Sau khi gộp #8–#10: head `eb32866`, [run 38810285870](https://github.com/FinanceBullkk/webdebit/actions/runs/38810285870) 9/9 job. Artifact có `tested_tree` `70cb999` khớp tree của head; fixture M2 213/213, M1 PG 16/16, characterization ledger 8 pass cộng 1 `repro_success` lịch sử; cleanup `verified_and_removed`. Python 79/79 chạy cục bộ trên cùng tree. PR #11 bổ sung hồ sơ ACL/five-view gate và được gộp thành head tích hợp `c439d13`; bằng chứng live nằm ở mục dưới.

CÒN MỞ: bảng nối opening ↔ mã chuyến chưa duyệt (mọi charge thật vẫn bị chặn); M1 đã triển khai trên `hao`, forwarding lịch sử đã được duyệt/kiểm nhưng còn checklist người dùng; login thật, receipt/FIFO, đảo bút toán thuộc M3. Gộp nguồn/lịch sử qua một origin là cải tiến sau, chưa làm.

## M1 live — triển khai và kiểm sau triển khai, 16/10/2026

Hồ sơ ngoài Git tại `D:\webdebit\verification\m1-predeploy-2026-10-16\DEPLOYMENT.md` ghi triển khai đúng commit `c439d13c2794e7bda5f8567816bf80db8396f931`, tree `8c6bc5167b4871a42107d50a7553bcda858b7ade`. Đây là bằng chứng runtime/DB live đúng thời điểm, không phải fixture CI.

- ACL thật đạt: viewer đọc đủ năm view pilot, `CONNECT`/`USAGE` giữ nguyên; login thường bị gỡ membership maker và các đường `EXECUTE` ghi. Không gọi hàm ghi.
- Runtime ba file khớp manifest; health HTTP 200, bảy component đều `ok`; hai service active, `NRestarts=0` tại quan sát cuối.
- Relay Windows `127.0.0.1:8766` đạt; HTTP bảy route đạt và Host sai trả 400; browser thật đã kiểm overview, exceptions, phân trang, bộ lọc, sổ khách và trang kỳ.
- Số liệu trước/sau giữ nguyên: 155 khách, 496 kỳ, `65.051.673.578 VND`, 46 `NO_BASELINE`, opening NULL=0, 0 proposal/posting/audit.
- Forwarding lịch sử **ĐÃ CHỐT + ĐÃ TRIỂN KHAI trên `hao`**: người dùng xác nhận đã duyệt khoảng 06:24 ngày 16/10/2026 (Asia/Saigon), tự áp khoảng 06:27. Phạm vi đúng hai đích loopback `127.0.0.1:8766` và `127.0.0.1:8765`, `PermitListen none`, không forwarding Unix socket. Hồ sơ chi tiết và biên bản kiểm khoảng 06:30 giữ ngoài Git, được dẫn từ `DEPLOYMENT.md` nêu trên; không đổi code dịch vụ.
- Đối chiếu lại 08:07:39: file cấu hình khớp chính xác script đã áp và phạm vi hai đích; không thay server. Biên bản 06:30 ghi effective-policy/reload và probe ngoài phạm vi bị từ chối; lần này không tái chạy kiểm đặc quyền đó. Launcher Windows mở các cổng còn thiếu với `ExitOnForwardFailure`, giữ relay hợp lệ hiện hữu; chạy thử 08:08:39–08:08:40, GET `/` và `/health` cả hai cổng đều HTTP 200. Cold start được kiểm bằng fixture launcher, lần live tái sử dụng relay đang chạy. Bằng chứng readback/HTTP nằm trong hồ sơ ngoài Git.
- **Nghiệm thu 16/10/2026 08:10–08:17**: sáu mục B05 được kiểm mẫu trên trình duyệt, chỉ GET: health; một khách còn nợ và trang kỳ (tổng các kỳ khớp tổng quan); khoản chờ rỗng; ngoại lệ (2 thiếu tổng, 86 tổng 0, chênh 600 ₫); link dòng nguồn qua `8765` khớp khoản trong sổ, trang lịch sử cùng số dư replay; `/postings` rỗng, số dư không đổi. Người dùng xác nhận “M1 đạt nghiệm thu” với phạm vi trên. Kiểm mẫu, không duyệt mọi dòng nguồn; đường lỗi 503 khi mất DB không kiểm trên live. Phương án A **CÒN MỞ** như cải tiến gộp nguồn/lịch sử qua một origin `8766`; chưa sửa code, build hoặc deploy.

Kết luận: **M1 ĐÃ NGHIỆM THU** (web xem sổ chỉ đọc trên `hao` tại `c439d13`, gồm link lịch sử qua `8765`). Bằng chứng này không mở M2, không chứng minh app login/session maker-checker, không chứng minh Sheet/nguồn ngân hàng hiện tại hay đường ghi tiền.

## T5 — Tổng hợp M2 và kiểm live M1

Cập nhật: 15/10/2026. Kết luận M2: **CHƯA ĐẠT cho charge đầu tiên**. Không có mã chuyến ổn định; chưa có source key và cách đối chiếu từng chuyến với opening replay `13/10/2026 16:44`. Theo quyết định chủ nghiệp vụ lúc đó, chuyến chưa phân giải phải ở `CHỜ KIỂM`, ngoài số dư (ghi chú 16/10/2026: đã được thay bằng [LEGACY-A và OPENING-FINAL](decisions.md); chỉ còn áp dụng cho chuyến có ngày xe từ 14/10, chuyến trước đó giữ nợ trong opening); không suy định danh từ container, ngày hoặc khách. Cấu phần và số tiền phải được chủ nghiệp vụ duyệt riêng theo từng chuyến, không áp công thức giá chung.

- **T1** — hợp đồng tại commit `44d813ba93c0022eeab93469c5d00930cc286baa`; chính sách charge được chốt nhưng source key/opening resolver và triển khai chưa có. Xem [hợp đồng charge](../specs/p0-write-path/00-first-charge-contract.md).
- **T2** — review độc lập đúng T1 SHA `44d813ba93c0022eeab93469c5d00930cc286baa`. P0 còn chặn nghiệm thu charge: định danh nguồn và đối chiếu opening, xác nhận cấu phần/tổng giá theo revision, kiểm kỳ đang mở. T2 cũng ghi blocker M3: schema tích hợp còn stale approval, fixture Q01/Q02 chưa nối app/DB; login/session người thật, quyền DB và rollback đầy đủ chưa được kiểm.
- **T3** — code commit `3599bc6ef7a2668eede1654f715860659a825ba2`; fixture PostgreSQL 18.6 `84/84`, Python `30/30`. Charge thiếu mã/đối chiếu opening, dùng reference opaque, thiếu xác nhận kỳ/giá hoặc dùng xác nhận cũ sau edit đều fail-closed ở `review_needed`, không có approval/posting. Schema tích hợp giữ nguyên SHA-256 LF-normalized `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`.
- **CI T3** — workflow `Tests`, [run 38722630386](https://github.com/FinanceBullkk/webdebit/actions/runs/38722630386), `8/8` job success trên đúng code SHA `3599bc6ef7a2668eede1654f715860659a825ba2`. Artifact PostgreSQL charge fixture `84/84`; report SHA-256 `3967813175be0f0c045098ad8585c803950fe84677b33a84dd4550ae9e05abf5`. T3 docs commit `0972eb007d1035e8e6545dc0c22e783d5581cd2f` chỉ ghi nhận CI, không đổi code.
- **T4 — M1, chỉ đọc trên `hao`** — kiểm lúc `15/10/2026 16:55 Asia/Saigon`: `webdebit-ledger-view.service` active, health OK, DB `webdebit_ledger`, snapshot `13/10/2026`, 496 kỳ; opening/balance `65.051.673.578 VND`, 46 kỳ `NO_BASELINE`, 0 proposal và 0 posting. Role viewer có SELECT, không có quyền ghi hay maker/checker, `default_transaction_read_only=on` (chỉ nói về role viewer; kiểm sâu hơn của T07 ngày 15/10 phát hiện một login thường có đường ghi qua role maker và viewer thiếu `SELECT` ba view tổng hợp M1: M1-3, CÒN MỞ). Ba file runtime khớp release `ledger-two-sided-monthly-2026-10-13`: `ledger_app.py` SHA-256 `b3c6cf7f49991bccd0e9184e5873e043ca6490c15f83943b978720c288fb80c2`, `ledger_db.py` `e3ea1bce0cba40976892829876fae06a3087358e3aedc876d6abd27c8256c98c`, `style.css` `481648126722485ebfdfeb51ad9cfd03339a394b4422368db8204ca721b5efb7`. Đây là kết quả live của lần kiểm T4, không phải xác nhận trạng thái hiện tại sau thời điểm đó.
- **Giới hạn M1 lịch sử** — T4 ngày 15/10 chưa có listener relay tại `127.0.0.1:8766`; browser chưa kiểm trang khách. Hồ sơ triển khai ngày 16/10 đã kiểm relay/browser, nhưng health/DB readback không thay nghiệm thu nghiệp vụ.

**M2 chưa đạt:** T3 chứng minh guard fixture từ chối thiếu căn cứ; không tạo source key, không chứng minh một chuyến thật vắng mặt trong opening, và không có charge eligible/post. T2 review bám T1, không phải review độc lập sau thay đổi T3. CI xanh chứng minh các job trên code SHA nêu trên; không là nghiệm thu nghiệp vụ, DB/runtime thật, người thật hay quyền ghi.

**M3** là giai đoạn tích hợp app account/session, HTTP write API, migration và kiểm DB thật/bản sao, gồm quyền DB/rollback đầy đủ. Chưa triển khai. Receipt/Q09 và nhập muộn nằm ngoài charge đầu tiên.

## Prototype actor và revision Q01/Q02 — worktree riêng

### T3 — gate charge theo chuyến

Kiểm cục bộ trước commit trên branch `feature/p0-actor-revisions`, baseline HEAD `44d813ba93c0022eeab93469c5d00930cc286baa`; các file dưới đây có thay đổi chưa commit khi chạy. Sau commit, so lại SHA-256 với revision được push. Không dùng DB, Sheet, service hoặc `hao`; fixture chỉ chạy PostgreSQL cô lập.

- Python 3.13 suite trong venv của worktree: `30/30` đạt. `git diff --check` và `py_compile` cho actor helper, actor test và PostgreSQL runner đều đạt.
- Fixture PostgreSQL 18.6: run `0e20901efe3e40169f7a53ce2621df71`, `84/84` assertion đạt, image `postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`; `--network none`, không publish port/volume mount, cleanup `verified_and_removed`. Report SHA-256 `7225e12ea8284834d46c46892abf6153730eeabcb6323a120eff75212c6d881b` (report nằm trong thư mục temp cục bộ, không commit).
- File hash của nội dung được test: fixture `757052383b81c7533ab1b2a2b4ac10c1510b30075a9a1e2cd268b7b3c6c865de`; runner `620275d2a3b4efea280eca046d90d68b6e8d797dedfbd812cb35cacda811685f`; helper dùng chung `b77e8703c9143103944d29bcd0ee3e30d40b9db7295bab5b41ab49efe601ccdb`; `actor_assertion.py` `68e4bad0e3c99578855368575e4b820a1d0b1010b564d800096ec94b3b2c67f` (LF-normalized).
- `pg_ledger_schema.sql` không đổi; SHA-256 LF-normalized vẫn `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`.
- Nội dung kiểm: charge thiếu mã chuyến/đối chiếu opening hoặc dùng tham chiếu opaque vẫn ở `review_needed`, không có approval/posting; kỳ đóng/chưa xác nhận, giá thiếu/lệch và xác nhận cũ sau edit đều fail-closed. Generic Q01/Q02 coverage giữ nguyên.
- CI `Tests`: [run 38722630386](https://github.com/FinanceBullkk/webdebit/actions/runs/38722630386), `8/8` job đạt trên commit `3599bc6ef7a2668eede1654f715860659a825ba2`. Job `pg18-versioned-approval-fixture` đạt `84/84`, report run-id `9129ebc93632420eb4611dd8e6974dc6`, SHA-256 `3967813175be0f0c045098ad8585c803950fe84677b33a84dd4550ae9e05abf5`; cleanup `verified_and_removed`. Đây kiểm code commit nêu trên; commit tài liệu ghi nhận kết quả không đổi code.

Phạm vi kiểm trước commit: branch `feature/p0-actor-revisions`, HEAD nền `75d9ff994ab803b18932f8f306a507f181356c71`; nội dung code/fixture được nhận diện bằng hash dưới đây. Không áp dụng DDL lên `hao`, service, Sheet hoặc DB nào khác.

- Python suite: `..\.venv\Scripts\python.exe -m unittest discover -s tests -v` từ `cong-no-web-handoff/`, Python 3.13.6 trong venv mới của worktree — **30/30 đạt**.
- Hash hỗ trợ Python suite (LF-normalized): test actor `b06aa84829c76a4fa73c04a4036374bcddde63fb389a51d70579ad858610cd63`; runner PostgreSQL dùng chung `b77e8703c9143103944d29bcd0ee3e30d40b9db7295bab5b41ab49efe601ccdb`.
- Actor/revision fixture: `.\.venv\Scripts\python.exe cong-no-web-handoff\tools\test_pg_versioned_approval.py --report <temp-path>` — run `73238af638e24f0b942c6b89b0ecb584`, **58/58 đạt**, PostgreSQL 18.6, image `postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`. Runner ghi `--network none`, không publish port/volume mount và dùng tmpfs tạm; cleanup `verified_and_removed`. SHA-256 report `cf667c3aeb057541ceb350dbb04b5578ea33ab3f6380e5be4b6fb51a394282cf`; fixture `c5681a95ff007af7c44a990dbb44f8bfff1e3becfd14cd7d3ad5104c2c1de03c`, runner `269edd81ff8c713b62001da33b7e153ae92ab008049f1703eaa626f26d3c8237`, shared container helper `b77e8703c9143103944d29bcd0ee3e30d40b9db7295bab5b41ab49efe601ccdb`, actor helper `86836745bfd05bf6d82485b67cfba54018a1ffa60e78deceecb9215283773162` (LF-normalized). Canonicalization giữ nguyên codepoint của reference; subprocess decode UTF-8 tường minh để kiểm được Unicode trên Windows. Report lưu ở thư mục tạm cục bộ, không commit vào repo.
- Schema characterization riêng: `.\.venv\Scripts\python.exe cong-no-web-handoff\tools\test_pg_ledger_schema.py --report <temp-path>` trên cùng HEAD — run `837329e303074db095f748d39fb0aafe`, 8 case `pass` và 1 case `repro_success`; cleanup `verified_and_removed`. SHA-256 report `4e2daa7d571974973db7a1b23edf88214f85e0494378ea4e1efbb0120167a381`, schema LF-normalized `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`. `repro_success` tái hiện approval stale của schema cũ, không phải acceptance đạt.
- CI `38695774411` đạt 7/7 job trên HEAD `75d9ff9`; đây là CI characterization trước diff Q01/Q02 trong worktree. Tại thời điểm kiểm trước commit, workflow đã thêm job versioned-approval-fixture nhưng chưa có run GitHub cho diff đó.

Giới hạn: fixture chỉ dùng `charge_fixture` giả và chứng minh helper/SQL prototype tại revision/hash nêu trên. Login/session thật, CSRF, account lifecycle, Tailscale/proxy, kiểm tra từ ngoài tailnet, nguồn ngân hàng và service thật chưa được kiểm. Q09 vẫn mở; receipt path không có trong fixture. Đây không phải migration, đường ghi tiền hay production readiness.

### T01 — hardening kind và actor fixture

- Code/spec commit `3f5f245c4cafcc4ca6cb77baa45665cbac9a6dc8`; Python 3.13 trong venv sạch, requirements cài bằng hash: `32/32` unittest đạt; `py_compile` và `git diff --check` đạt. Regression epoch mới đỏ trên input SHA trước sửa.
- CI [run 38750059028](https://github.com/FinanceBullkk/webdebit/actions/runs/38750059028) đạt `8/8` job trên head commit nêu trên. Job PostgreSQL fixture đạt `122/122`; baseline có 84 case, cả 62 tên check cũ còn nguyên. Artifact report SHA-256 `40a3632d88b9972590cecf565119f8c6e665caf8e70554e94160955772b1d24f`; fixture SHA-256 `42eb3d425ed49ccc06a75121333d46756492afb2fc007c5d0c6826f00c643605`.
- Report revision merge commit `af6ebc5cf6330a60fe6def580801319d372d23b1`; tree `578772541dd1c21210d181803645828c96e8f57a` khớp tree của head commit. Image PostgreSQL 18.6 pin digest; runner dùng `--network none`, không port/mount; cleanup `verified_and_removed`. Assertion cuối cho 0 charge được approve/post.
- PostgreSQL local: **NOT RUN** vì Docker daemon không có named pipe. Fixture được kiểm trong CI. Không sửa `pg_ledger_schema.sql`, viewer, DB/Sheet/service thật; source key/opening resolver vẫn chặn mọi charge.

## Harness PostgreSQL schema ghi sổ — nhánh phụ thuộc PR #2

Nhánh `test/pg18-schema-characterization` bắt đầu từ `315d2d150d17ac77cda31f0ef3b61f696cd20ea5`, cùng head PR #2 khi bắt đầu. Commit nhánh: `2317553f3cadd40f87e754714fbd203ff1844ad5`; draft PR #3 phụ thuộc PR #2. PR #2 vẫn mở tại head `315d2d150d17ac77cda31f0ef3b61f696cd20ea5` ở lần đối chiếu cuối. SHA-256 schema `cong-no-web-handoff/tools/pg_ledger_schema.sql` theo nội dung LF chuẩn hóa: `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`. Runner chuẩn hóa CRLF/LF trước hash và nạp chính nội dung đó, để revision giống nhau có cùng hash trên Windows/Linux. PostgreSQL image được pin `postgres:18.6@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`; registry trả HTTP 200 cho manifest digest này.

Runner: `python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report <path>`. Mỗi lượt dùng volume/container riêng có run-id label, `--network none`, không publish port; database đích duy nhất là `webdebit_ledger`. SQL gốc được truyền nguyên bản với `ON_ERROR_STOP`. Fixture toàn bộ là giả. Báo cáo JSON giữ expected/actual, SQLSTATE và số posting/status/audit sau mỗi case. Schema không có receipt entity/allocation ledger riêng; kiểm allocation cùng receipt được để lại cho task sau Q03–Q04.

Run CI lịch sử [38686910554](https://github.com/FinanceBullkk/webdebit/actions/runs/38686910554), workflow `Tests`, source head `e50451a2f69f83e1d2e4f9058dc9be39e7a61cf8`; trạng thái tổng thể và cả 7 job đều success. Artifact `pg-ledger-characterization` có 9 assertion trên PostgreSQL 18.6; report revision là merge commit CI `62e9da42059329508ba746174980fd60535343c7`, schema SHA-256 LF-normalized giữ nguyên `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`, image digest giữ nguyên ở trên. Cleanup được xác minh `verified_and_removed`, container ID đầy đủ được ghi trong artifact, runner exit 0. Năm characterization, atomicity và hai contention assertion là `pass`; stale-content assertion là `repro_success`, tái hiện submit 100 rồi checker post 101. `repro_success` chỉ là tái hiện defect, không là acceptance. Xem [artifact/run](https://github.com/FinanceBullkk/webdebit/actions/runs/38686910554) để biết chi tiết SQLSTATE, counts và `pg_blocking_pids`.

Run CI schema characterization sau đó là [38695774411](https://github.com/FinanceBullkk/webdebit/actions/runs/38695774411) trên branch head `75d9ff994ab803b18932f8f306a507f181356c71`, đạt 7/7 job; artifact có 8 case `pass` và một `repro_success`. Nó không chứa diff Q01/Q02 chưa commit trong worktree.

Lượt CI trên commit trung gian `566cc7d` (run `38686717095`) phát hiện `docker ps --quiet` rút container ID còn 12 ký tự; kiểm tra identity vì vậy từ chối cleanup an toàn và report ghi `cleanup: failed`. Đã sửa discovery với `--no-trunc`; run `38686910554` trên `e50451a` xác nhận lại 9 assertion và cleanup `verified_and_removed`. Đây là kiểm lỗi harness, không phải lỗi characterization PostgreSQL.

Giới hạn vẫn vậy: các run CI PostgreSQL thuộc revision được nêu, không phải kiểm DB/service thật. Report trước đó từ run `38684269409`, `38683750234` và các kiểm local bên dưới được giữ làm lịch sử; xem phần prototype Q01/Q02 phía trên để biết kiểm cục bộ trên worktree riêng.

| Kiểm lịch sử | Kết quả thực chạy |
|---|---|
| `py_compile` runner (Python 3.13.6) | Đạt. |
| `git diff --check` | Đạt. |
| `python -m unittest discover -s tests -v` trong `cong-no-web-handoff/` | 23/23 đạt. Đây là fixture suite hiện có, tách biệt PostgreSQL. |
| Runner local trên Windows | Exit 1 đúng kỳ vọng fail-closed; report run `e176f428ad934d5a953b51811fd8473f`, không tạo container/volume và không chạy DDL. Docker Desktop process đã mở nhưng daemon named pipe không có; service `com.docker.service` không thể khởi động do quyền môi trường. PostgreSQL local chưa được kiểm. |
| PostgreSQL 18.6 CI job | Run `38683750234`, report run-id `fc86c8db1b99483f9a570f78d57b9a94`, GitHub PR merge revision `b8ac417ae6f6aa2beaa5fe3456dda6a87589464e` (branch commit `2317553f3cadd40f87e754714fbd203ff1844ad5`). `version()`: PostgreSQL 18.6 (Debian 18.6-1.pgdg13+2), x86_64. Image digest: `sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336`. Lệnh: `python cong-no-web-handoff/tools/test_pg_ledger_schema.py --report pg-ledger-characterization.json`. Runner exit 0; container ID `1079978b0cc02025fac80f665341371c3897f0ee5810fcac2b3265214e64dcf4`; cleanup `verified_and_removed`. Artifact: [workflow run](https://github.com/FinanceBullkk/webdebit/actions/runs/38683750234). |

Các assertion CI trên PostgreSQL 18.6 ở run `38683750234`: characterization 5/5 đạt; defect repro `owner_mutation_after_submit_posts_unreviewed_content` có nhãn `repro_success` — đã submit 100, sau owner mutation checker post 101; atomicity trigger lỗi với SQLSTATE `P0001` và proposal vẫn `pending`, 0 posting, 0 approval audit; contention 2 checker sessions được quan sát bằng `pg_blocking_pids` (`420:{392}`, `421:{420}`), đúng một call thành công, call còn lại `P0001`, đúng 1 posting. Đây là mô tả baseline; defect repro không phải acceptance đạt. Không test chung receipt vì schema không có receipt entity/allocation ledger riêng. Nếu PR #2 đổi schema trước merge/chạy lại, so diff và chạy job trên revision mới.

**Kết luận lịch sử:** PostgreSQL thật đã chạy và chứng cứ nêu trên thuộc revision CI được ghi. Cả 7 job của workflow (PostgreSQL riêng, Python 3.12/3.13 Windows/Linux, JavaScript Windows/Linux) đều pass trên run `38683750234`; JavaScript Windows hoàn tất sau 4m57s. Máy local vẫn chưa kiểm PostgreSQL vì Docker daemon không khởi động; report fail-closed local không thay thế CI. Trạng thái CI mới nhất được ghi ở đầu mục này.

## Phạm vi và revision

Mã cơ sở: `69a84a41382217265f745c1c9ae87cba9e557c16` (34 file). Thay đổi hiện tại: dependency/runner/CI, hồ sơ nghiệp vụ đã lọc, cảnh báo chuyến chờ duyệt trên fixture. Diff/commit của thay đổi là ranh giới revision; kết quả dưới đây chỉ cho môi trường được nêu, không chứng minh live.

## Kết quả cục bộ

Windows, Python 3.13, Node 24.16.0, npm 12.0.2, Playwright 1.64.1, Chromium 156 (revision 1248). Dependency cài bằng lock; browser tải mới vào thư mục project riêng, không dùng cache Hermes.

| Kiểm | Kết quả thực chạy |
| --- | --- |
| Python: `python -m unittest discover -s tests -v` từ handoff trong repo | 23/23 đạt trên Python 3.13. Lần đầu dùng interpreter có sẵn tzdata; chưa đủ chứng minh Python sạch (xem lỗi CI bên dưới). Không cần DB thật. |
| `npm run test:unit` | 4 file, 16 kiểm đạt. Hai file script assertion được Node tính mỗi file là một test; không phải toàn bộ số assertion. |
| `npm run test:browser` | 4/4 đạt trong Chromium headless; không có pageerror. |
| Regression cảnh báo shipment | Trước sửa: thất bại vì không có `#pending-shipment`. Sau sửa: đạt; mở tháng/đích, lọc kỳ/ngày, số dư không đổi. |
| Model pending | Giá hợp lệ lưu thành draft, approved total vẫn null; thiếu giá tách riêng; tiền thập phân giữ lỗi và số dư không đổi. |
| Render Chromium fixture | 1440 và 500 px: scrollWidth bằng viewport; đã xem ảnh 500 px. Ảnh fixture giả không đưa vào Git. |

## Checkout mới và CI

ĐÃ KIỂM CHỨNG revision mã `75b3ecc4ee023705473cb240841097adc42c48ac` bằng clone Git mới (không hardlink), đường dẫn có dấu cách. Cài mới npm cache, `node_modules`, Chromium/headless shell; `NODE_PATH` trống. 16/16 Node và 4/4 Chromium đạt; Playwright resolve trong clone mới, Git status sạch. Python 23/23 dùng interpreter 3.13.6 toàn cục, có sẵn tzdata 2025.2: đây là giới hạn được CI phát hiện, không phải bằng chứng venv sạch.

Run CI `38677432296` trên `592c145` tái hiện `ZoneInfoNotFoundError: Asia/Ho_Chi_Minh` ở cả hai Windows/Python 3.12/3.13; Linux đạt. Sửa bằng dependency `tzdata==2026.5` khóa SHA-256, cài trong setup/CI; không thay múi giờ ứng dụng hoặc bỏ test. Kết quả venv sạch và CI của bản sửa được ghi trong PR và hồ sơ workspace.

Đã tạo venv mới, xác nhận `base_prefix != prefix` và chưa có tzdata trước cài. Cài đúng wheel/hash từ `requirements.txt` rồi chạy lại 23/23 test Python đạt. README yêu cầu venv, không còn giả định thư viện chuẩn đủ trên Windows.

Workflow định nghĩa Windows/Linux, Python 3.12/3.13 và Node 24/Chromium; trạng thái GitHub thực chạy phải đọc ở PR/commit checks. Thêm YAML không là một lượt CI đạt. Kết quả CI cuối cùng và URL run được ghi trong mô tả PR.

## Giới hạn

Không kiểm DB/service, quyền người thật, ghi tiền, migration, ngân hàng hoặc nguồn Sheet sống. Không chạy DDL/profiler trên capture. Bộ nội bộ ngoài repo có 29 test Python (đã chạy đạt trên Python 3.13), bao gồm maker/importer không thuộc repo; không cộng vào 23 test ở đây. P0 tài chính trong [sổ quyết định](decisions.md) vẫn CÒN MỞ.
