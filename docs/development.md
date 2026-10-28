# Quy trình phát triển chung

## Nguồn sửa chính

Theo lựa chọn người dùng 15/10/2026, GitHub là nơi dev/AI cùng phát triển. Trên PC hiện tại, checkout chính là `repo/` bên trong workspace; đường dẫn cụ thể ở hướng dẫn workspace, không là dependency code/test. Máy khác clone ở vị trí bất kỳ.

Handoff ngoài checkout giữ làm hồ sơ mốc trước chuyển đổi. Release/capture bất biến, không là working tree. Không sửa hai bản song song, không tự copy ngược preview/runtime. Hotfix bên ngoài phải so từng file và có spec/test/provenance trước khi nhập vào nhánh.

Mốc bàn giao `69a84a41382217265f745c1c9ae87cba9e557c16` có 34 file. Bản chia sẻ đổi nhãn fixture, bỏ submit/importer nội bộ và test phụ thuộc. Không lấy số test nội bộ làm số test repo. Chênh CRLF/LF tách khỏi nội dung; `.gitattributes` quy định LF.

## Một vòng thay đổi

1. Kiểm nhánh, HEAD, status/diff, bảo vệ thay đổi của người khác. Một phạm vi một người/agent ghi; khi cần dùng checkout/worktree riêng. Không tự discard/stash/absorb thay đổi chưa rõ chủ.
2. Đọc nghiệp vụ/quyết định, mở spec với tiêu chí quan sát được. Việc nhỏ mô tả trong PR; không cần framework specs.
3. Sửa hẹp, dùng runner hiện có. Regression có ý nghĩa chạy thất bại trước sửa và đạt sau sửa khi khả thi. Map thao tác → entry point → kiểm đúng tầng.
4. Chạy `npm run check` (xem [Lint và lệnh check](#lint-và-lệnh-check)) thay cho việc nhớ từng runner. Nghiệm thu bằng clone sạch, venv mới không kế thừa site-packages, dependency/browser mới; không copy `node_modules` hay dùng cache Hermes/package Python toàn cục làm bằng chứng máy mới.
5. Review mọi diff định đưa lên, kiểm bí mật/nhạy cảm; không copy toàn docs/capture. Commit/PR chỉ gồm phần task khi được phép; review/CI đúng revision trước merge. Không tự push main hoặc mở ghi tiền vì test xanh.
6. Ghi revision/hash, môi trường, kết quả và giới hạn ở `docs/verification.md` hoặc PR. Phân biệt thêm workflow với CI đã chạy; fixture với DB/live.

Nghiệp vụ chia sẻ ở `docs/`, spec ở `specs/`. Hồ sơ ngoài repo là bằng chứng lịch sử theo hash trong [source register](source-register.md). Quyết định mới cập nhật repo, không duy trì hai bản sống. Nội dung nhạy cảm chỉ dẫn tới hồ sơ có quyền riêng, không dán vào issue/CI log/tài liệu.

## Quy trình PR và triển khai

Từ 29/10/2026, để giảm PR lỗi thời và conflict khi nhiều người/agent làm cùng lúc:

1. **Mỗi việc một worktree mới từ `origin/main`**, PR nhỏ, merge trong ngày. Một nhóm file chỉ một người/agent giữ tại một thời điểm.
2. **PR lỗi thời** (main đã có commit mới): bấm *Update branch* trên GitHub hoặc `gh pr update-branch <số>`; conflict thì rebase ở máy. Repo chỉ cho **squash merge**, lịch sử `main` thẳng; required check duy nhất là `ci-ok` ([CI](#ci-trên-runner-github)). PR xếp chồng: retarget PR con về `main` trước khi merge PR cha, rồi rebase PR con.
3. **Quyết định** ghi trong đúng file `docs/decisions/<id>.md` của nó; quyết định mới tạo file mới và thêm một dòng vào bảng của [`decisions.md`](decisions.md). Hai PR sửa hai quyết định khác nhau không còn đụng nhau.
4. **Triển khai app không cần PR tài liệu riêng.** Merge vào `main` là tự triển khai lên `hao`; bằng chứng là lượt `Deploy hao` (bảng *Tóm tắt triển khai*: kết quả, SHA trước/sau, commit trong đợt) và tab *Environments → hao* trên GitHub. Trong PR của tính năng, file quyết định ghi "triển khai tự động khi merge qua `Deploy hao`", không ghi trước "ĐÃ TRIỂN KHAI". Lượt đỏ thì sửa và báo lại, không ghi là đã triển khai.
5. **Triển khai tay** (gate SQL/migration/loader dừng `Deploy hao`): nhật ký mỗi đợt là một file mới trong [`docs/deploys/`](deploys/README.md), không chèn thêm mục vào [runbook](v7-deploy-runbook.md); runbook chỉ giữ quy trình. Đợt đó cập nhật trạng thái trong file quyết định liên quan ở cùng PR.

## Quy trình frontend

ĐÃ CHỐT bởi người dùng/chủ nghiệp vụ ngày 16/10/2026 trong chat: áp dụng đủ các bước dưới đây cho luồng frontend mới hoặc thay đổi đáng kể trong repo. Penpot là nơi duyệt mockup trước khi code frontend. Quy trình không tự cấp quyền triển khai hoặc ghi tiền.

1. **Chốt kết quả nghiệp vụ:** xác định người thao tác, đầu vào, kết quả, điều kiện bị chặn và tiêu chí nghiệm thu. Quy tắc chưa chốt phải ghi CÒN MỞ, không biến lựa chọn trên UI thành chính sách.
2. **Đối chiếu dữ liệu/backend:** đọc nguồn, trường dữ liệu và entry point/API hiện có; ghi phần dùng được, phần thiếu, dữ liệu thật và fixture. Không dựng trường tiền từ giả định.
3. **Dựng luồng và mockup Penpot:** thể hiện màn hình nối nhau và trạng thái bình thường, thành công, trống, thiếu dữ liệu, lỗi, thiếu quyền, chờ duyệt khi áp dụng. Dùng dữ liệu giả trong mockup; không sao chép dữ liệu khách/chứng từ thật vào tài liệu chia sẻ.
4. **Người dùng duyệt mockup:** chốt tên trường, thứ tự thao tác, nguồn và thông báo trước khi code frontend. Ghi liên kết file/page/board, mốc phiên bản và người/ngày/phạm vi duyệt trong spec hoặc PR; không chỉ dẫn bản thiết kế đang thay đổi. Thay đổi luồng sau duyệt phải cập nhật mockup và duyệt lại phần bị ảnh hưởng. Nếu Penpot chưa kết nối hoặc chưa có duyệt, tiếp tục khảo sát/spec/check độc lập; chưa code frontend thuộc phạm vi đó.
5. **Chốt giao tiếp frontend–backend:** thống nhất request/response, validation, lỗi, quyền và trạng thái nghiệp vụ; bổ sung backend cần thiết cho luồng. Backend phải kiểm quyền và điều kiện ghi, không dựa vào nút bị ẩn trên UI.
6. **Code và nối backend:** tái sử dụng thành phần hiện có, đối chiếu mockup đã duyệt. Có thể dùng fixture trước khi API sẵn sàng nhưng phải ghi rõ; chưa coi luồng tích hợp hoàn thành khi vẫn dùng fixture.
7. **Kiểm trình duyệt và tích hợp:** chạy checks hiện có và kiểm bố cục, bàn phím/focus, nhập sai, tải chậm/mất mạng, bấm lặp, thiếu quyền theo phạm vi tác động. Kiểm luồng nối backend trên môi trường thử với dữ liệu giả; phân biệt bằng chứng fixture, tích hợp và live. Không thử ghi trên Sheet/DB thật từ quy trình này.
8. **Nghiệm thu và phát hành:** người dùng đi hết luồng trên môi trường thử, đối chiếu kết quả/nguồn. Ghi revision, môi trường, kết quả và khoảng trống; chỉ phát hành trong phạm vi được phép sau khi tiêu chí đạt. Duyệt mockup không thay nghiệm thu nghiệp vụ, chứng cứ hoặc quyền ghi tiền.

Giữ hồ sơ gọn trong spec/PR hiện có: thao tác → module/API → check → bằng chứng; kèm mockup đã duyệt và các gate còn mở. Không tạo thêm bộ tài liệu song song.

**Sửa nhỏ:** đổi chữ, khoảng cách hoặc sửa lỗi hiển thị mà không đổi luồng, ý nghĩa nghiệp vụ, dữ liệu, quyền hay hành vi không cần mockup/duyệt Penpot mới. Ghi lý do miễn trong PR và kiểm phù hợp phần sửa; không bỏ kiểm accessibility hoặc ranh giới tài chính. Quy trình không buộc làm lại toàn bộ màn hình cũ nếu chúng chưa thuộc phạm vi thay đổi.

**Giới hạn thực thi:** AGENTS.md và quy trình hướng dẫn dev/AI; review phải đối chiếu hồ sơ duyệt và bằng chứng. CI hiện có kiểm code/fixture, chưa tự xác nhận người dùng đã duyệt Penpot hoặc nghiệm thu luồng thật.

## Lint và lệnh check

`npm run check` ở gốc repo chạy tám bước theo thứ tự: `ruff check`, luật nghiệp vụ
(`scripts/check-business-rules.js`), link tài liệu (`scripts/check-doc-links.js`), `eslint`, `unittest` của `cong-no-web-handoff/tests`,
`node --test` cho model JS, rồi hai bộ test trình duyệt Playwright (`test:browser` và `test:viewer`). Chưa tải Chromium thì cả hai bước
Playwright cùng báo SKIP chứ không FAIL, để một thiếu sót môi trường không làm người sửa bỏ luôn thói quen chạy check.
`npm run lint` chạy riêng bốn bước lint khi đang sửa dở.

CI gọi đúng `npm run check` (job `javascript` trong `.github/workflows/test.yml` — kết quả gom vào job `ci-ok`, required check duy nhất). Nếu CI gọi một lệnh
khác thì màu xanh ở máy không còn nói lên điều gì — đổi bước kiểm thì đổi ở `scripts/check.js`,
không đổi riêng trong workflow.

### CI trên runner GitHub

**ĐÃ TRIỂN KHAI** (nguồn: `.github/workflows/test.yml`): từ 21/10/2026 repo chuyển public và mọi job
chạy trên máy của GitHub (`ubuntu-latest`, `windows-latest`), thay cho runner tự host `hao` và
`windows-local` dùng từ commit `98edf29` (18/10/2026).

| Job | Runner | Chạy gì |
|---|---|---|
| `python` | `ubuntu-latest` | unittest `cong-no-web-handoff/tests`, Python 3.12 và 3.13 qua `uv` |
| `postgres-ledger`, `postgres-m1-history-queries`, `pg18-versioned-approval-fixture` | `ubuntu-latest` | ba harness `tools/test_pg_*.py`, mỗi lần dựng một container PostgreSQL 18.6 dùng một lần bằng Docker |
| `javascript` | `ubuntu-latest` và `windows-latest` | `npm run check` với Python 3.13 qua `uv` |
| `ci-ok` | `ubuntu-latest` | gom kết quả mọi job trên; **required check duy nhất** của `main` |

**Luật nhánh `main`** (từ 29/10/2026): required check chỉ còn `ci-ok`, vẫn bắt nhánh cập nhật theo `main`
trước khi merge (`strict`), bật nút Update branch, chỉ cho squash merge và lịch sử thẳng. Thêm job mới vào
workflow thì thêm vào `needs` của `ci-ok`; không cần sửa luật nhánh. PR lỗi thời bấm Update branch hoặc chạy
`gh pr update-branch <số>` (dùng `--rebase` nếu muốn rebase).

Lý do bỏ runner tự host: `hao` là máy chạy DB thật `webdebit_ledger` và web xem sổ; với repo public,
PR từ fork có thể đưa mã lạ chạy trên chính máy đó. Máy GitHub sạch mỗi lượt, không chạm `hao`, nên
rủi ro CÒN MỞ trước đây (chạy mã PR cạnh DB thật) không còn áp dụng cho CI. Lượt cũ của cùng PR bị hủy
khi có commit mới (`concurrency`). Gỡ đăng ký runner tự host khỏi repo là việc trong Settings của
người dùng, không nằm trong workflow.

Chọn luật theo một nguyên tắc: **chỉ bật luật bắt lỗi thật, không bật luật định dạng.** Mã hiện có
451 dòng Python vượt 88 ký tự và dòng JS dài nhất 1878 ký tự; ép định dạng sẽ tạo một diff khổng
lồ không liên quan nghiệp vụ và che mất phát hiện thật. Lý do của từng lựa chọn nằm ngay trong
`ruff.toml` và `eslint.config.js`, gồm cả các luật bị tắt (luật Unicode "nhập nhằng" báo nhầm trên
mọi chuỗi tiếng Việt) và các ngoại lệ theo file.

Thêm luật mới: ưu tiên biến một quy tắc nghiệp vụ đã chốt thành thứ máy kiểm được — luật ruff/eslint
có sẵn, ràng buộc SQL, hoặc một bước mới trong `scripts/check.js`. Luật chỉ nằm trong tài liệu thì
mỗi lần review lại phải soi bằng mắt.

### Khi nào chạy harness PostgreSQL ở máy

Harness `tools/test_pg_*.py` không nằm trong `npm run check`; CI chạy chúng ở các job `postgres-*`
cho mọi PR. Ở máy chỉ chạy tay harness của phạm vi đang sửa:

| Sửa gì | Chạy ở máy |
|---|---|
| UI, preview, model JS, tài liệu | `npm run check`, không chạy harness |
| Python ngoài SQL (adapter, công cụ nạp) | `npm run check`; harness chỉ khi đụng câu SQL gửi đi |
| `v7_backend_functions.sql`, schema, migration, đường ghi tiền | harness V7 liên quan (`test_pg_v7_backend.py`, thêm `test_pg_v7_p0_harness.py`/`test_pg_v7_grants.py` nếu đụng quyền) |

Trên Windows mỗi `docker exec` tốn ~0,4–0,5 giây qua Docker Desktop/WSL (Linux ~0,1 giây), nên harness
chậm chủ yếu vì số lần gọi exec chứ không phải PostgreSQL. Từ 28/10/2026 `run()` của
`test_pg_v7_backend.py` (cũng là đường của p0, grants, direct, rehearse) gửi lệnh `docker exec … psql`
qua `tools/docker_exec_channel.py`: một `docker exec` sống suốt lượt chạy, mỗi lệnh vẫn là một tiến
trình psql mới trong container với cùng argv, env, stdin, mã thoát — tức vẫn một kết nối, một phạm vi
transaction như trước. Đo 28/10/2026 trên máy Windows của người dùng: `test_pg_v7_backend.py` từ 1195 giây xuống 238 giây, cùng 60 case xanh, 2 case CÒN MỞ bỏ qua. Lệnh chạy đồng thời (case lock/tranh chấp) và argv lạ vẫn đi `docker exec` riêng.

### Luật nghiệp vụ máy đã kiểm

`scripts/business-rules.js` giữ các quy tắc **ĐÃ CHỐT** đã code hóa; `scripts/check-business-rules.js`
chạy chúng, và `scripts/test-business-rules.js` chứng minh từng luật bắt được vi phạm bằng fixture
tạm (mỗi luật có một nửa vi phạm phải bị bắt và một nửa sạch phải đi qua — một check chỉ xanh trên
mã hiện tại thì không chứng minh được gì). Thông báo lỗi bằng tiếng Việt, nói rõ luật nào và sửa thế nào.

Bảng dưới đây có hai loại luật, và cột "Nguồn" phân biệt chúng. `VND-*`/`DATE-*`/`FUTURE-*`/
`TRIP-DATE-*` truy về một dòng **ĐÃ CHỐT** trong sổ quyết định. `ARCH-*` thì không: chúng giữ
**ranh giới kiến trúc** — hiện trạng mã đã đo được, chốt lại để lần refactor sau không làm mất êm.
Đổi một ranh giới ARCH là sửa luật kèm lý do, không phải tắt luật.

| Luật | Nội dung kiểm | Nguồn |
| --- | --- | --- |
| `VND-01` | Cột `*_vnd` trong `CREATE TABLE` phải là `numeric(p,0)` hoặc integer/bigint; chặn `numeric(p,s>0)`, `real`, `double precision`, `float`, `money`, và `numeric` không khai scale | `business-rules.md` ô "Tiền chưa rõ" — VND nguyên chính xác |
| `VND-02` | Không `float()` (Python), `parseFloat`/`toFixed` (JS), không gán số thập phân cho tên `*_vnd`/`*Vnd` ở đường tính tiền | cùng nguồn; test được miễn để dựng dữ liệu vi phạm |
| `DATE-01` | "Hôm nay" phải theo `Asia/Ho_Chi_Minh`: chặn `current_date`, `localtimestamp`, `now()::date` trong SQL và `date.today()`, `datetime.now()` trần trong Python. `now()` cho cột timestamptz và `datetime.now(UTC)` cho provenance không bị chặn | `FUTURE-01`, người dùng chốt 16/10/2026 |
| `FUTURE-01` | Mỗi hàm ghi tiền (INSERT vào `proposal`/`posting`) có dính `posting_date` phải so với hôm nay theo giờ VN rồi RAISE ngay trong hàm đó — mọi hàm ghi sổ tự chặn, không trông vào hàm khác. Luật quét từng hàm, không theo bước của luồng, nên vẫn đúng sau khi `V6-DB` (19/10/2026) bỏ bước duyệt | `FUTURE-01` + `specs/p0-fixture-future-posting-date.md` |
| `TRIP-DATE-01` | Hàm ghi tiền nhận `p_event_date` phải chặn NULL — ngày nghiệp vụ chuyến là bắt buộc, blank/NULL giữ là chưa biết | `DATE`, người dùng làm rõ 14/10/2026 |
| `ARCH-01` | Chỉ tầng DB được gọi `psql`. Danh sách cho phép viết tường minh trong `PSQL_ALLOWED` kèm lý do từng file: `web/db.py`, `web/ledger_db.py`, `tools/pg_m1_report.py`, `tools/test_pg_ledger_schema.py`, `tests/test_web.py`. `scripts/` ngoài phạm vi vì là mã của chính bộ kiểm | Ranh giới kiến trúc — hiện trạng đã kiểm 19/10/2026 |
| `ARCH-02` | Tầng web (`web/*.py`) không import ngược vào `tools/` hay `pilot/`: kiểm câu import, `importlib.import_module` và vá `sys.path`. Chiều ngược lại được phép — phụ thuộc chạy một chiều | như trên |
| `ARCH-03` | Tính tiền chỉ ở model: chặn `+ - *` và `+= -= *=` trên tên tiền (`*_vnd`/`*Vnd`), hằng BigInt và `BigInt(...)` trong file `*-ui.js`; so sánh và định dạng được phép. Chỉ tầng JS — xem giới hạn ngay dưới | như trên |

**Mức bằng chứng của `FUTURE-01`** — luật này có *hai* lớp kiểm, và chúng chứng minh hai việc khác
nhau. `lint:biz` là check **tĩnh**: nó chỉ xác nhận guard *có mặt* trong văn bản SQL, không chứng
minh guard chạy đúng trên PostgreSQL. Lớp hành vi nằm ở harness DDL
`cong-no-web-handoff/tools/test_pg_ledger_schema.py`, nhóm case `posting_date`:
`future_posting_date_rejected_on_submit`, `future_posting_date_rejected_on_approve` và
`future_posting_date_rejected_on_reversal` dựng một container PostgreSQL 18.6 dùng một lần, nạp đúng
file schema trong repo, rồi gọi thật `ledger.submit_entry`, `ledger.approve_entry` và
`ledger.request_reversal` với `posting_date` = ngày mai. Ngày mai được tính độc lập với
`ledger.business_today()` và truyền vào dưới dạng literal, nên guard không được lấy đồng hồ của chính
nó làm bằng chứng. Case duyệt chèn sẵn một hàng `pending` bằng quyền owner để mô phỏng đề xuất đã lọt
qua `submit_entry` của bản cũ; case đảo dùng `posting_id` thật của một đề xuất đã duyệt trong fixture.
Case thứ tư, `today_posting_date_accepted`, giữ chiều ngược lại: `posting_date` = **hôm nay** phải
được nhận — một guard chặn oan ca thường thì cũng là guard sai.

Hai điều kiện phải nhớ: harness **cần Docker** và **không nằm trong `npm run check`** — nó dựng
container nên không chạy được ở mọi máy và mọi CI step; ở máy phải gọi tay, còn CI chạy chúng ở các job
PostgreSQL riêng (xem [CI trên runner GitHub](#ci-trên-runner-github)):

    py -3.13 cong-no-web-handoff/tools/test_pg_ledger_schema.py --report <đường-dẫn>.json

ĐÃ KIỂM CHỨNG 19/10/2026 trên PostgreSQL 18.6 (image pin theo digest, container dùng một lần, không
chạm DB thật): cả 13 case xanh với guard tại chỗ. Và để case không xanh rỗng, mỗi guard được bỏ hoặc
làm sai **riêng một lần** rồi chạy lại — bỏ guard ở `submit_entry` thì case nhập FAIL (`exit 0`,
`new_proposals 1`: đề xuất ngày mai được nhận), bỏ guard ở `approve_entry` thì case duyệt FAIL
(`status posted`, `postings 1`: tiền đã ghi với ngày tương lai), bỏ guard ở `request_reversal` thì
case đảo FAIL (`exit 0`, `new_proposals 1`: đề xuất đảo ghi ngày mai được nhận), và đổi guard nhập
thành `>=` thì `today_posting_date_accepted` FAIL (`exit 1`: ngày hôm nay bị chặn oan). Bỏ từng cái
một là cố ý: `record()` raise ngay ở case fail đầu tiên, nên bỏ nhiều guard cùng lúc chỉ chứng minh
được case sớm nhất. Sau mỗi lần, schema trả về nguyên trạng, đối chiếu bằng sha256 của nội dung đã
chuẩn hóa LF (`4f434767…c048718a`).

**Mức bằng chứng của `ARCH-*`** — ba luật này là check **tĩnh** trên văn bản mã, và mỗi luật có cả
case âm (nạp đoạn mã vi phạm, đòi linter bắt được) lẫn case dương trong
`scripts/test-business-rules.js`. Ngoài fixture, ba luật còn được kiểm đột biến trên **file thật**
ngày 19/10/2026: chèn một dòng `psql` vào `web/ledger_app.py`, một `from tools.pg_m1_report import`
vào cùng file, và một phép trừ tiền vào `so-cong-no-v5-ui.js` (file V5, không có trên nhánh này; tương đương V7 là `so-khach-v7-ui.js`) — cả ba đều bị bắt đúng một lần, và
ba luật đều sạch trên bản chưa sửa.

Giới hạn đã biết, ghi ngay cạnh từng luật trong `business-rules.js`:

- `ARCH-02` không bắt được import động dựng tên module từ biến.
- `ARCH-03` nhận tiền qua tên (`*_vnd`/`*Vnd`), hằng BigInt và `BigInt(...)`; ô tiền đặt tên khác
  (`price`, `otherFee` ở workbench) nằm ngoài lưới. Tên **hàm** kết thúc bằng `Vnd` được lọc ra có
  chủ ý: `'…' + fmtVnd(x)` là nối chuỗi quanh bộ định dạng, không phải cộng tiền — không lọc thì
  luật bắt nhầm đúng cái việc nó muốn khuyến khích.
- Cả ba nằm ngoài script nhúng thẳng trong `.html`, vì `collect()` chỉ đọc .sql/.py/.js.

**`ARCH-03` chỉ phủ tầng JS, và đây là ranh giới thật chứ không phải phạm vi cho tiện.** Tầng JS có
cặp `X-model.js` + `X-ui.js` nạp đúng thứ tự đó trong .html, số học tiền nằm trọn ở model — kể cả
chỗ tính lệch giữa số dán và số model cũng gọi `model.allocateReceipt` thay vì tự trừ. Tầng Python
thì **chưa** tách như vậy: `web/ledger_app.py` cộng trừ tiền ngay trong đường render
(`carried + charge_total - payment_total`, và `sum(Decimal(...))` cho phí). Viết một luật rộng rồi
miễn trừ `ledger_app.py` sẽ biến chính chỗ đang sai thành chỗ được luật bảo kê, nên luật khoanh vào
`*-ui.js`. **CÒN MỞ:** có tách model/UI cho tầng Python hay không cần quyết định của người dùng;
nếu tách thì mở rộng `UI_FILE` của `ARCH-03`.

Phần **CÒN MỞ không được code hóa**, và đây là giới hạn của bảng trên, không phải sơ suất:

- Tên trường của ngày xe nhập kho. Sổ quyết định (`DATE`) chốt *ngữ nghĩa* "ngày nghiệp vụ chuyến là
  ngày xe nhập kho" nhưng ghi rõ backend "chưa kiểm runtime đã đổi". Trong mã hiện hành không có cột
  nào tên `warehouse_in_date`: schema dùng `event_date`, preview dùng `row.date` với nhãn
  "Ngày xe nhập kho". Nên `TRIP-DATE-01` chỉ kiểm được *tính bắt buộc*, không kiểm được tên; ép một
  tên cột qua linter là tự đặt chính sách người dùng chưa duyệt.
- Cấm import cross-layer *nói chung*. Ba ranh giới đo được đã code hóa thành `ARCH-01`/`ARCH-02`/
  `ARCH-03` (19/10/2026); một đồ hình tầng đầy đủ cho cả repo thì vẫn CÒN MỞ — xem mục dưới.
- `json.loads` không có `parse_float=Decimal` ở đường đọc tiền (`web/db.py`, `web/ledger_db.py`,
  `tools/pg_m1_verify.py`). Hiện vô hại vì `numeric(20,0)` ra JSON không có dấu thập phân, nhưng
  `pilot/reconcile.py` đã làm đúng cách. Chưa bật thành luật vì sẽ đỏ trên ba file đang có thay đổi
  chưa commit của người khác.

### Ranh giới tầng — ba luật ĐÃ TRIỂN KHAI, đồ hình đầy đủ CÒN MỞ

**Cập nhật 19/10/2026:** ba ranh giới nêu ở cuối mục này đã code hóa thành `ARCH-01`/`ARCH-02`/
`ARCH-03` trong `scripts/business-rules.js`, chạy trong bước `lint:biz` của `npm run check`. Phần
còn lại dưới đây giữ nguyên làm hồ sơ vì sao luật chỉ dừng ở ba ranh giới đó. Một chỗ đã đo lại và
**sai**: mục 3 bên dưới chép rằng số học tiền không nằm ở `app.py`; thực tế `web/ledger_app.py`
cộng trừ tiền trong đường render, nên `ARCH-03` chỉ phủ `*-ui.js` — xem phần giới hạn ở trên.

Luật "cấm import cross-layer" *nói chung* vẫn chưa code hóa được vì repo **chưa có tầng theo nghĩa
import**. Hiện
trạng đo được: các module Python là file phẳng nạp qua `sys.path`, không phải package; toàn repo chỉ
có bốn cạnh import nội bộ — `web/app.py → db`, `web/ledger_app.py → ledger_db` (cùng thư mục), và
test nạp `app`/`db`/`ledger_app`/`pilot.reconcile`. `tools/` và `pilot/` không import gì nội bộ. Phía
JS, `preview/` nạp nhau bằng thẻ `<script>` qua biến toàn cục, khai ở `eslint.config.js`, nên không
có cạnh import để chặn. Đặt một đồ hình tầng lên mã này là tự phát minh ranh giới, nên dừng ở đây.

Ba ranh giới *đã có thật* trong mã, và nay đã thành luật (ghi nguyên văn bản đề xuất để đối chiếu
với luật đã triển khai):

1. **Chỉ module DB được nói chuyện với PostgreSQL.** `psql`/`subprocess` cho DB chỉ xuất hiện trong
   `web/db.py` và `web/ledger_db.py`; `web/app.py` và `web/ledger_app.py` hiện có **0** câu SQL. Kiểm:
   chặn `subprocess`/`psql`/SQL trong tầng trình bày. Rủi ro báo nhầm thấp nhất.
2. **Tầng trình bày không import tầng DDL/harness.** `web/` và `preview/` không được import
   `tools/`. Hiện đúng, và nếu vi phạm thì là lỗi thật (nạp harness Docker vào đường chạy app).
3. **Tính tiền chỉ ở model.** Số học tiền nằm ở `preview/*-model.js` và `pilot/reconcile.py`, không
   ở file `*-ui.js` hay `app.py`. Đây là ranh giới yếu nhất: `so-khach-v7-ui.js` hiện đã có định
   dạng tiền, nên cần người dùng chốt "tính" khác "định dạng" ở đâu trước khi bật.

## Hoàn tác và ranh giới

Thay đổi hiện tại chỉ code/tài liệu/CI. Hoàn tác bằng diff/commit đã review, không xóa capture/release hay đụng DB. CI chỉ chạy fixture và DB thử dùng một lần trên máy của GitHub, không chạm `hao`; xem [CI trên runner GitHub](#ci-trên-runner-github). Ghi tiền/deploy cần scope, policy, DB test và quyền riêng theo gate nghiệp vụ.
