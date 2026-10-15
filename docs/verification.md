# Kiểm chứng thay đổi ngày 15/10/2026

## T5 — Tổng hợp M2 và kiểm live M1

Cập nhật: 15/10/2026. Kết luận M2: **CHƯA ĐẠT cho charge đầu tiên**. Không có mã chuyến ổn định; chưa có source key và cách đối chiếu từng chuyến với opening replay `13/10/2026 16:44`. Theo quyết định chủ nghiệp vụ, chuyến chưa phân giải phải ở `CHỜ KIỂM`, ngoài số dư; không suy định danh từ container, ngày hoặc khách. Cấu phần và số tiền phải được chủ nghiệp vụ duyệt riêng theo từng chuyến, không áp công thức giá chung.

- **T1** — hợp đồng tại commit `44d813ba93c0022eeab93469c5d00930cc286baa`; chính sách charge được chốt nhưng source key/opening resolver và triển khai chưa có. Xem [hợp đồng charge](../specs/p0-write-path/00-first-charge-contract.md).
- **T2** — review độc lập đúng T1 SHA `44d813ba93c0022eeab93469c5d00930cc286baa`. P0 còn chặn nghiệm thu charge: định danh nguồn và đối chiếu opening, xác nhận cấu phần/tổng giá theo revision, kiểm kỳ đang mở. T2 cũng ghi blocker M3: schema tích hợp còn stale approval, fixture Q01/Q02 chưa nối app/DB; login/session người thật, quyền DB và rollback đầy đủ chưa được kiểm.
- **T3** — code commit `3599bc6ef7a2668eede1654f715860659a825ba2`; fixture PostgreSQL 18.6 `84/84`, Python `30/30`. Charge thiếu mã/đối chiếu opening, dùng reference opaque, thiếu xác nhận kỳ/giá hoặc dùng xác nhận cũ sau edit đều fail-closed ở `review_needed`, không có approval/posting. Schema tích hợp giữ nguyên SHA-256 LF-normalized `bfc869c0afd2c7cf2bec161e5e90b01d0f3a97581e4ef58da957541f5471c156`.
- **CI T3** — workflow `Tests`, [run 38722630386](https://github.com/FinanceBullkk/webdebit/actions/runs/38722630386), `8/8` job success trên đúng code SHA `3599bc6ef7a2668eede1654f715860659a825ba2`. Artifact PostgreSQL charge fixture `84/84`; report SHA-256 `3967813175be0f0c045098ad8585c803950fe84677b33a84dd4550ae9e05abf5`. T3 docs commit `0972eb007d1035e8e6545dc0c22e783d5581cd2f` chỉ ghi nhận CI, không đổi code.
- **T4 — M1, chỉ đọc trên `hao`** — kiểm lúc `15/10/2026 16:55 Asia/Saigon`: `webdebit-ledger-view.service` active, health OK, DB `webdebit_ledger`, snapshot `13/10/2026`, 496 kỳ; opening/balance `65.051.673.578 VND`, 46 kỳ `NO_BASELINE`, 0 proposal và 0 posting. Viewer role có SELECT, không có quyền ghi hay maker/checker, `default_transaction_read_only=on`. Ba file runtime khớp release `ledger-two-sided-monthly-2026-10-13`: `ledger_app.py` SHA-256 `b3c6cf7f49991bccd0e9184e5873e043ca6490c15f83943b978720c288fb80c2`, `ledger_db.py` `e3ea1bce0cba40976892829876fae06a3087358e3aedc876d6abd27c8256c98c`, `style.css` `481648126722485ebfdfeb51ad9cfd03339a394b4422368db8204ca721b5efb7`. Đây là kết quả live của lần kiểm T4, không phải xác nhận trạng thái hiện tại sau thời điểm đó.
- **Giới hạn M1** — Windows không có listener relay tại `127.0.0.1:8766`; browser chưa kiểm trang khách. Health/DB readback không thay kiểm UI trên browser.

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
