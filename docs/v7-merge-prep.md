# Chuẩn bị PR V7 — 21/10/2026

## Vòng 3 — gom về một nhánh, 21/10/2026

Gom từ `test/pg18-schema-characterization` (checkout `repo/`), các worktree còn thay đổi chưa commit và tip V7 `codex/v7-opening-read`. Thay đổi chưa commit được lưu trước ở `patches/2026-10-21/` (ngoài Git, kèm SHA-256); các worktree đã gỡ có tag `archive/2026-10-21/<nhánh>` cho nhánh nào còn công việc riêng. Không push, không PR.

**Đã gộp (commit trên nhánh này):**

| Nhóm | Nguồn | Ghi chú |
| --- | --- | --- |
| `npm run check` (`scripts/check.js`, `business-rules.js`, `check-business-rules.js`, `test-business-rules.js`, `eslint.config.js`, `ruff.toml`, `requirements-dev.txt`, workflow, `package.json`/lock, `AGENTS.md`, `README.md`, `docs/development.md`) | `test/pg18-schema-characterization` | Ba-way với `main`; `test:unit` giữ hai test V7 của nhánh này, bỏ test V5 không nhập |
| Sửa ruff cho 17 file cũ | cùng nhánh | Ba-way từng file, giữ thay đổi mới của `main` |
| Khai báo global V7 cho eslint, `_balance` ở `renderMonth` | mới | Hai tên model/fixture V7 là global theo thẻ script |
| Spec cấn trừ hai sổ (3 file, dòng `CT-2SO`, mục trong `specs/README.md`) | `docs/can-tru-hai-so` (chưa commit) | Ghép tay vào `decisions.md`/README |
| Tài liệu agent (`CLAUDE.md`, `GEMINI.md`, `docs/multi-agent.md`, `agent-environment.md`, `ux-guidelines.md`) và `scripts/agent-run.ps1`, `codex-detached.ps1`, `open-penpot.ps1`, `ui-capture.js` | `repo/` (chưa theo dõi) | Đã quét: thay địa chỉ proxy, cổng và đường dẫn thư mục người dùng trong `agent-environment.md` bằng chỗ giữ chỗ; không hostname/SSH/ID Sheet/tên khách/số tiền thật |
| 12 spec của việc đã vào `main` | `repo/` (chưa theo dõi) | `_template`, `allocation-edge-tests`, `fu-*` (4), `harness-psql-stdin`, `ledger-migration-f1f3`, `remove-draft-rows`, `table-scroll-keyboard`, `workbench-readability` |

**Cố ý không gộp:**

- **Code V7 `f9fd099`:** đã thử, rồi hoàn lại. Bản bốn spec V7 ở `f9fd099` là bản chưa lọc (tên tab khách, tổng tiền thật, số khách); không đưa vào Git. `v7_export_clean.py` và hai test V7 trên nhánh này cùng logic xuất với `f9fd099` nhưng đã có thêm chặn ghi vào trong repo và ghi nhật ký test ra thư mục tạm. Bản xuất sạch 21/10 do `f9fd099` xuất; logic nạp/xuất không đổi giữa hai bản. Cần quyết định có muốn khớp từng byte `f9fd099` không (mất rào chặn).
- `v7_opening_app.py`, `test_v7_opening_app.py`, `so-khach-v7-opening.js` (viewer chỉ đọc 20/10): hiện cờ `NO_BASELINE` cho người dùng, trái `V7-COPY` (1); gọi thẳng `ssh hao ... psql` để đọc `hao`, trái lan can của việc gom; đọc lược đồ `ledger.opening` cũ. Chỉ lưu patch.
- `ux-v3-so-cong-no`, `ux-v4-so-khach` (luồng gửi duyệt đã bị V6 thay), `backend-nhap-chuyen-chot-thang` (đi cùng `m1w-p0`): chỉ lưu patch.
- `v7-isolated-read`, `m1w-p0`, V6-THU (hai worktree), `p0-actor-revisions`, `pg-ledger-characterization.json`, dòng V7-COPY thừa ở `decisions.md` của `repo/`: chỉ lưu patch.
- Tài liệu V5/V6 và preview V5/V6 như mục trước.

**Kết quả `npm run check` (Windows, Python 3.13 trong `.venv`, Node 24):**

| Bước | Kết quả |
| --- | --- |
| `test:py` unittest | ĐẠT, 161 test |
| `test:js` node --test | ĐẠT, 75/75 |
| `test:js` playwright | ĐẠT, 6/6 |
| `test:js` viewer | ĐẠT, 11/11 |
| `lint:js` eslint | ĐẠT |
| `lint:py` ruff | **ĐỎ**, 74 lỗi, toàn bộ ở 10 file V7 chưa từng qua lint (`v7_load_real_copy.py` 33, `test_v7_load_real_copy.py` 9, `v7_ledger_api.py` 6, `test_pg_v7_backend.py` 5, `v7_export_clean.py` 5, `test_v7_ledger_api.py` 5, `test_v7_export_clean.py` 4, `v7_live_demo.py` 3, `v7_reconcile_real_copy.py` 2, `v7_profile_xlsx.py` 1); nhiều nhất B023, RUF021, BLE001, I001, E402 |
| `lint:biz` luật nghiệp vụ | **ĐỎ**, 17 vi phạm trên code V7: VND-02 (`float()` ở `v7_load_real_copy.py:143`), DATE-01 (`so-khach-v7-ui.js:34`, lấy ngày không khai múi giờ), ARCH-01 (15 chỗ gọi `psql` ngoài tầng DB: `v7_ledger_api.py`, `v7_live_demo.py`, `v7_load_real_copy.py`, 2 test và `test_pg_v7_backend.py`) |

Hai bước đỏ là code V7 gặp công cụ lint lần đầu, không do gộp (trước khi gộp tooling, nhánh này không có lint). Đỏ sẵn từ trước nên không sửa trong lượt này: sửa nghĩa là đổi code V7 hoặc đổi luật; luật nghiệp vụ không tắt theo `docs/development.md`. CI chạy `npm run check` sẽ đỏ tới khi V7 được sửa lint hoặc có quyết định ngoại lệ (ví dụ cho `web/v7_ledger_api.py` vào danh sách `PSQL_ALLOWED` nếu nó là tầng DB của V7).

## Vòng 2

Nền: `integration/v7-m1-m2-docs`, worktree `codex/v7-import-round2`. Chỉ đọc blob đã commit bằng `git show`; không merge nguyên lịch sử, không đọc file chưa commit ở worktree nguồn.

Đã kiểm `git show --stat` từng SHA: `dcb46a1` — 3 file, +183/-27; `d162c63` — 3 file, +23/-2; `451efa2` — 4 file, +44/-3; `f9fd099` — 3 file, +228/-0. Đây là diff commit nguồn, không phải thống kê bản nhập đã lọc.

| SHA | File phân loại | Xử lý |
| --- | --- | --- |
| `dcb46a1` | `cong-no-web-handoff/tests/test_v7_load_real_copy.py` (test), `cong-no-web-handoff/tools/v7_load_real_copy.py` (mã) | Nhập logic làm sạch số lẻ đồng, chia lại theo tổng, bảo hiểm âm và carry TOTAL 0; fixture không chứa dữ liệu nguồn thật. |
| `dcb46a1` | `specs/v7-backend/ket-noi-giao-dien.md` (tài liệu) | Nhập phần quy tắc đã lọc; bỏ tên khách, số tiền/số đếm nguồn, đường dẫn capture và kết quả quét thật. |
| `d162c63` | Cùng test/mã/tài liệu | Nhập thử cách đọc bảo hiểm theo chuỗi mỏ neo; tài liệu chỉ giữ quy tắc và cờ, bỏ log nguồn thật. |
| `451efa2` | Hai file test/mã, `tools/v7_reconcile_real_copy.py`, tài liệu | Nhập `--sheet-is-truth`, cờ lệch CSV/opening và FIFO theo Sheet; bỏ tên khách, số liệu, tên file xuất và kết luận quét nguồn. |
| `f9fd099` | `cong-no-web-handoff/tests/test_v7_export_clean.py`, `tools/v7_export_clean.py` (test/mã), tài liệu | Nhập exporter/manifest/hash. Giữ đích bắt buộc ngoài repo; bổ sung chặn tại `export()`, `write_csv()` và thư mục staging sau resolve để không có đường ghi vào repo/worktree Git. Test chỉ fixture giả. |

Phần loại: không nhập `captures/`, XLSX/CSV/DB/log chạy thật, tên khách, số tiền hoặc số đếm nguồn, Sheet URL/ID, SSH/Tailscale/DB credential. Tài liệu nguồn chỉ giữ hợp đồng mã, cờ và giới hạn; không coi fixture hay quét nguồn là opening/live/production.

Kiểm trên nền `b24460a` cộng đúng bảy file vòng này, Windows, Python 3.13.6, Node v24.16.0. Dùng venv/dependency có sẵn theo đường dẫn người dùng cấp: `PATH` thêm `D:\webdebit\repo\.venv\Scripts`, `WEBDEBIT_PYTHON=D:\webdebit\repo\.venv\Scripts\python.exe`, `NODE_PATH=D:\webdebit\repo\node_modules`, `PYTHONIOENCODING=utf-8`. Không cài thêm dependency.

| Lệnh thực chạy | Kết quả |
| --- | --- |
| Từ `cong-no-web-handoff/`: `python -m unittest discover -s tests` | Exit 0, 161 test: **160 pass, 1 Docker skipped**; lượt cuối 34.563s. Có `ResourceWarning` file đọc CSV chưa đóng trong test exporter nguồn; thông báo argparse loại trừ `--demo`/`--real-copy` là case từ chối chủ ý. Không có assertion failure. |
| Từ gốc: `node --test cong-no-web-handoff/preview/test-*.js` | Exit 0, **61/61 pass**, gồm test browser preview và model/API fixture. |
| Từ gốc: `node --test cong-no-web-handoff/tests/test-viewer-browser.js` | Exit 0, **11/11 pass**, viewer fixture desktop/mobile/bàn phím. Không phải nghiệm thu V7 live. |
| `python -m unittest discover -s tests -p test_v7_export_clean.py` | Exit 0, **4/4 pass**: manifest/hash/stdout, giữ khách, đích hợp lệ/bị chặn/thiếu bằng chứng đầu vào. |
| `git diff --check` | Đạt. |

Logic loader/reconcile khớp byte blob `f9fd099`. Ngoại lệ có giới hạn: exporter kiểm mọi điểm ghi/staging sau resolve, mở file độc quyền để tránh ghi đè; test exporter thêm case đường ghi trực tiếp, TEMP trong repo, repo khác, đích resolve vào repo, thiếu tham số và bảo toàn file có sẵn. Một test subprocess loader gán `LOG_DIR` vào fixture tạm qua bootstrap thay vì ghi log ngoài phạm vi worktree; vẫn chạy `main()` trong tiến trình riêng, giữ toàn bộ assertions/guard nghiệp vụ. Không sửa test để né lỗi hay ép pass.

SHA-256 bytes mã/test đã kiểm (đường dẫn dưới `cong-no-web-handoff/`):

```text
tools/v7_load_real_copy.py 643365ebadf1466a9f634035fcc4df74abab4436a395ae24a0b957f307bfaf3e
tools/v7_reconcile_real_copy.py 023bd4079914e5cb61e8b6ee8ff3a38792f4ac1ecad0e506ebfc745f2cb03d8a
tools/v7_export_clean.py 88d9bed6a09560516d43376476927ec4078ec40f3bfc228e5e498741b5d6147f
tests/test_v7_load_real_copy.py ac4cd42a0e09d027e308f83b58676c00e95ee1795fb212499269739635413133
tests/test_v7_export_clean.py c3e81e10c3c8d91b133c8d0bb2358ade39cf5ac38e8e3a395f821e9832746e08
```

Quét toàn bộ file đổi, kể cả file mới: không thấy token/private key/Sheet URL-ID/SSH-Tailscale/DB URL có mật khẩu/tên khách hoặc số liệu nguồn đã biết. Các đường dẫn mặc định nguồn/log của loader đã có từ nền, không thêm hay chạy nguồn thật; số lớn trong test là fixture đã đánh dấu giả. Review thủ công các vị trí đường dẫn, số dài và toàn diff bổ sung; không coi quét mẫu là bảo đảm phát hiện mọi bí mật.

CÒN MỞ: các test vẫn là fixture/mock; chưa có DB PostgreSQL thật, tích hợp V7 live, nguồn Sheet/hao, import/deploy hay nghiệm thu tài chính. Quyết định opening tiếp theo và quyền áp dụng dữ liệu Sheet mới nhất là việc riêng. Không loại toàn bộ SHA nào trong bốn SHA được giao; chỉ loại nội dung nhạy cảm. Không nhập SHA mới hơn, không push/deploy/DDL/import thật.

## Hồ sơ vòng trước — giữ nguyên làm lịch sử

Các đoạn bên dưới mô tả vòng chuẩn bị trước khi đã có commit tích hợp; trạng thái quyền metadata và kết quả sandbox cũ không mô tả vòng 2.

**Chưa hoàn tất gộp Git/commit:** metadata worktree nằm ngoài vùng được phép ghi. Nội dung review đã có trong worktree, chưa stage; không push/mở PR/deploy. Không chạy Docker, DDL/import/submit hay truy cập DB/Sheet/hao/captures/release.

Diff chuẩn bị (gồm file mới chưa stage): **28 file, +9.932/-32**, gồm 4 file tracked sửa và 24 file mới. Đây là thống kê nội dung worktree so với HEAD, không phải commit diff.

## Nền và cách nhập

- Worktree/nhánh đích: `codex/v7-merge-prep`; ban đầu sạch, HEAD/origin/main `ae8f8f7`.
- Mốc nguồn cố định `011819e` của `codex/v7-opening-read`: **58 commit**, gồm **34 commit V5/V6** và **24 commit V7**. Diff nguồn ba chấm: **60 file, +15.088/-8**. Không fetch; origin/main là ref local được cung cấp.
- Sau khi bắt đầu kiểm, nhánh nguồn chuyển tới `dcb46a1` (làm tròn số lẻ đồng). **Không nhập commit mới này**; cần review/chốt phạm vi riêng. 17 file mã/test nhập khớp byte với commit `011819e`, không lấy file đang sửa hay file chưa theo dõi của worktree nguồn.
- Lấy nội dung đã commit bằng `git show <SHA>:<path>`; chưa có merge/cherry-pick thành công. Merge squash bị chặn tại `ORIG_HEAD.lock`; checkout bị chặn tại `index.lock` dưới Git metadata của checkout chính. Không đổi `.git`, không ghi sang checkout chính để vượt giới hạn. Không có conflict marker; chưa tuyên bố merge hoàn tất.
- Chỉ nhập 23 file V7, lọc tài liệu nguồn; V5/V6 không nhập. Giữ AGENTS.md và runner browser/viewer của main. Package chỉ thêm model/API V7 vào `test:unit`.
- `docs/decisions.md` và business-rules lấy nền committed `test/pg18-schema-characterization` tại `cfa10f1`, giữ quyết định cũ cùng ghi chú bị thay thế; không dùng bản cũ của nhánh V7. Riêng dòng `V7-COPY` từ file quyết định đang sửa tại checkout chính (chưa commit), đã bỏ số đếm nguồn; ghi rõ provenance ngay đầu sổ quyết định. Không lấy phần sửa khác.

## Trạng thái và giới hạn nghiệp vụ

- **ĐỀ XUẤT:** thiết kế/schema `sokhach`, API/hàm/công cụ thử, chưa là migration hay nghiệm thu tài chính.
- **ĐÃ CHỐT theo hồ sơ nguồn:** V6-DB, V7-SO/ID/MIG/BE/MH; V7-COPY có nguồn chưa commit nêu trên. Task này không chốt thêm chính sách.
- **ĐÃ TRIỂN KHAI:** mã thử trong worktree; mô tả live cũ trong tài liệu chỉ là hồ sơ theo ngày, chưa kiểm lại. API thử có POST, không phải API chỉ đọc.
- **ĐÃ KIỂM CHỨNG:** đúng kiểm cục bộ dưới đây, trên file của snapshot này; không có CI mới/DB PostgreSQL/browser/live acceptance.
- **CÒN MỞ:** quyền ghi Git metadata để commit; kiểm đầy đủ ngoài sandbox; xác nhận nhận dòng V7-COPY chưa commit; review commit mới dcb46a1 riêng. Các quyết định về số lẻ đồng, lịch sử thiếu giá, Sheet nhập song song, nguồn đúng mốc v2 và nghiệm thu vẫn giữ gate riêng.

## Kiểm thực chạy

Môi trường: Windows, Node v24.16.0, Python 3.13.6 từ `.venv` có sẵn; `NODE_PATH=D:\webdebit\repo\node_modules`, `WEBDEBIT_PYTHON=D:\webdebit\repo\.venv\Scripts\python.exe`, `PYTHONIOENCODING=utf-8`. Không cài dependency/framework.

| Lệnh | Kết quả thật |
| --- | --- |
| `npm run check` | Exit 1: `Missing script: "check"`; main và nhánh nguồn đều không có script này |
| `npm test` | Exit 1: test runner không spawn được worker (`spawn EPERM`), chưa chạy assertions |
| `node --test --test-isolation=none` với sáu file trong `test:unit` | **55/55 pass**; hai model cũ còn có assert riêng và in PASS |
| Từ `cong-no-web-handoff/`: `D:\webdebit\repo\.venv\Scripts\python.exe -m unittest discover -s tests -p test_v7_ledger_api.py -v` | Exit 0: **10 pass, 1 skipped**; `V7_API_DOCKER_TEST=0`, HTTP fake Psql, không Docker |
| Python unittest discover toàn bộ, lọc đúng test subprocess ghi log ngoài worktree | Không đạt. Lượt cuối từ đúng handoff cwd với TMP trong worktree: **152 test: 44 pass, 107 PermissionError, 1 skipped**, 0 assertion failure; không coi bộ đọc nguồn đã đạt. Lượt trước từ sai cwd có thêm 3 lỗi import tools, đã sửa cwd để chạy lại |
| Browser/viewer chạy trực tiếp với `--test-isolation=none` | Exit 1, 17 case không vào assertions do setup `spawn EPERM`; chưa kiểm browser |
| `node --check` các file JS V7/model/API/test | Đạt |
| Python `compile(..., 'exec')` mọi file Python mới | Đạt cú pháp; không thực thi SQL. Một lệnh py_compile trước đó nhầm đưa `.sql` vào danh sách đã exit 1; không dùng làm bằng chứng |
| `git diff --check` | Đạt; chỉ bao phủ tracked diff. File mới kiểm whitespace riêng ở lượt cuối |

Lệnh Node unit đầy đủ:

```powershell
node --test --test-isolation=none cong-no-web-handoff/preview/test-so-cong-no-model.js cong-no-web-handoff/preview/test-monthly-ledger-model.js cong-no-web-handoff/preview/test-customer-ledger-workbench.js cong-no-web-handoff/preview/test-customer-ledger-requirements.js cong-no-web-handoff/preview/test-so-khach-v7-model.js cong-no-web-handoff/preview/test-so-khach-v7-api.js
```

Bỏ có chủ ý đúng test `RealCopyTest.test_check_source_subprocess_on_fake_files`: gọi subprocess ghi log cố định ngoài worktree. Test khác của loader dùng fixture giả/mocks nhưng chưa qua do quyền tempfile. Không sửa test hoặc guard để lấy pass. Log lỗi giả ở `test-results/python-check-correct-cwd.log` (ignored, không đưa Git).

## Quét nhạy cảm và review diff

Kiểm danh mục file, tài liệu có nội dung nhạy cảm và hash mã; quét mọi file thay đổi và untracked dự định đưa Git, không chỉ tracked diff. Mẫu: private key, GitHub/OpenAI/AWS token, Sheet URL ID thật, SSH/Tailscale address, DB URL có credential, tên khách đã thấy ở tài liệu nguồn và số tiền/số đếm nhạy cảm. Không phát hiện mẫu sau lọc. Không có XLSX/CSV/DB/dump/ảnh/raw capture mới. Đây là quét mẫu + review, không bảo đảm phát hiện mọi bí mật có thể có.

Bỏ danh sách tên/số tiền khách khỏi migration/thiet-ke, bỏ nhật ký run nguồn thật và viết lại hợp đồng API; giữ quyết định và câu hỏi mở. `captures` chỉ còn là đường dẫn nguồn/chỉ dẫn ngoài Git, chưa đọc trong task. Fixture và test ghi rõ dữ liệu giả. Không merge nguyên lịch sử: commit nguồn có nội dung nhạy cảm, chỉ nên tạo commit mới từ diff đã lọc.

## PR đề xuất (chưa mở)

Tiêu đề: `V7: them prototype so khach, API thu va thiet ke sokhach`

Mô tả:

> Thêm prototype một khách V7, model tiền/fixture, API thử có POST, schema/hàm và harness sokhach để review. Đồng bộ hồ sơ V6-DB/V7 mới hơn, loại tên/số liệu nguồn; giữ runner viewer của main.
>
> Kiểm cục bộ: Node unit 55/55; Python API 10 pass + 1 Docker skipped; cú pháp JS/Python đạt. Chưa đạt check tổng: thiếu script check, sandbox chặn spawn/tempfile. Chưa chạy PostgreSQL hay nghiệm thu browser/dữ liệu thật; chưa cấp quyền ghi tiền/deploy.

Commit cục bộ đề xuất sau khi có quyền metadata: tách tài liệu/quyết định (`V7: nhap ho so da loc de review`) và mã/test (`V7: nhap prototype va API thu kem test`). Chưa có commit nào tạo trong phiên này.

## Danh sách commit nguồn (thứ tự cũ đến mới)

```text
a7ea67b mockup: ban HTML V5 vong 2 da duyet
64b6579 spec: ghi moc duyet mockup V5 vong 2
2f13063 model: lop 1 so cong no V5 - tinh tien thuan JS kem test
a2baea4 merge: model tien lop 1 V5 tu codex/v5-model-tien
b5c0f8e spec: trang thai lop 1 - da trien khai va da kiem chung
13d2d04 docs: chot chin quyet dinh UX V5 ngay 17/10/2026
8a542fe preview: tao so-cong-no-v5.html tu mockup da duyet
0e83b40 spec: lop 2 - noi giao dien V5 vao model
fe8f338 spec: chup ca trang cho lop 2
a8112a0 giao dien: noi trang V5 vao model lop 1 (ban gemini, CAN SUA)
c5025f1 spec: lop 2 chuyen sang codex cho vong sua 1
7a0bf28 giao dien: vong sua 1 - sau phat hien cua review
052657f spec: viec con lai vong sua 2 va sua kich ban dan TSV
2c6eddf giao dien: vong sua 2 - bo nhan "da thu du" sai sau chot
f58f737 spec: vong sua 3 - dat khoi bao loi canh dong nhap tien
016e7ce giao dien: vong sua 3 - khoi bao loi nam canh dong nhap tien
790fa1e merge: giao dien V5 lop 2 (gemini dung, codex sua ba vong)
aa23af2 docs: chot giao dien V5 lam moc da duyet (V5-GD)
4eef3f6 docs: chot V6 so cong no theo sheet, bo buoc chot thang
ff0b169 docs: V6-3b ranh gioi thang truoc theo thang lich cong ngay dem
7499967 docs: V6-3c dieu chinh ghi vao thang goc, thang sau tinh lai
443054a docs: V6-3d phan bo lai khoan thu theo no cu truoc sau dieu chinh
c9de869 docs: ngay dem het ngay 5 (ngay lich); AGENTS.md theo V6
df2f7e7 docs: spec lop 1 model V6, spec lop 2 giao dien V6, mockup tinh ux-v6
c110a2f V6 lop 1: model tien va test, opening mang danh sach dong tra cuu
8dc4e3c Spec lop 2: today mac dinh 2026-05-03 thay cho 2026-10-18
50e5e3c Lop 1: dong TONG cua thang, dong opening mang tien hien thi
d50da4b Lop 1: them lineCount cho nhan "n cont"
96dfc14 Spec lop 2: chot nhat ky C6 - hai ban ghi mau, hai do thao tac that
b421ec6 V6 lop 2: giao dien so cong no noi model tien
2527a06 V6: giu kich thuoc bo loc thang tren man Tong
f55b93c V6: lich su mau khop so mo dau
2585801 V6: sap thu tu ban ghi dan lo mau
f0d276c V6: compact ledger and show current opening debt
f12be8b V7: spec so khach theo loi Sheet va fixture an danh
ce6d946 V7: so khach theo Sheet - model tien, giao dien chi trong tab, ghi thu, huy phieu, dieu chinh
a52a599 V7: de xuat spec backend ghi so khach (chua chot, chua trien khai)
21d0aa5 V7: khoa thang theo V6 (dem den het ngay 5), cap nhat spec
4c656b5 V7: dieu chinh thang phan bo lai khoan thu theo no cu truoc (V6-3d), cap nhat spec
cef3f15 V7: ghi cac quyet dinh 19/10/2026 (sua phieu, mot khach, cho am, hinh thuc, du ghi so)
e404678 V7: dieu chinh khong can ly do, sua ngay/hinh thuc phieu, cap nhat spec
086ece7 V7: o khoa tung thang, dieu chinh ca thang, ngan Lich su, cap nhat spec
0492c68 V7 backend: thiet ke (de xuat) va ban nhap DDL schema-draft.sql (chua chay, chua review doc lap)
e716e10 V7: de xuat spec chuyen va lam sach du lieu tu Sheet (phuong an lai, chua chot)
239ad8f V7 migration: ghi quyet dinh phuong an lai, 12 tab het no
8d6b467 V7 migration: quy tac dong phi le khong ro nguon, xac nhan rieng khach (ten da loc)
9b134e3 V7 backend: thiet ke so du dau theo thang, dong lich su, moc chuyen (de xuat, chua chay)
bf524f3 V7: chon phuong an A chia moc neo thanh no tung thang
782db7a V7: them mat hang, phuong thuc van chuyen va co archive vao thiet ke (de xuat, chua chay)
e091d4a V7: ghi event customer_attr cho set_customer_attributes, sua danh muc mat hang
6fe342a V7: noi giao dien so khach voi HTTP API va ham PostgreSQL ban thu
4a3ea1b V7: nap ban sao du lieu that va doc Sheet theo bo cuc that
dce031a V7: doc them cac bo cuc Sheet con lai, giu khach theo ly do cu the
6173390 V7: bo doc xlsx go 12 khach that bi giu, giu nguyen cac chot doi soat
9191fe6 V7: cong thuc tra chuoi rong la o trong, khong phai mat gia tri (go them 2 khach)
a8935c9 V7: dieu chinh chuyen nam (thang 1), chia TOTAL cho chuyen chua co gia, tieu de lap theo ngay (go them 4 khach)
011819e V7: --raw-tab chon tab theo ten nguyen van khi chi khac khoang trang
```

## Phân loại 60 file khác origin/main (snapshot nguồn)

Không có file dữ liệu/binary trong diff nguồn; nội dung nhạy cảm nằm bên trong tài liệu đã đánh dấu lọc. Mockup HTML V5/V6 không thuộc V7, để PR khác.

| File | Loại | Xử lý |
| --- | --- | --- |
| `AGENTS.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v5-vong-2-huong-dan.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v5-vong-2.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/A0-tong.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C1-so-khach.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C2-da-luu-khoan-thu.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C3-ghi-dieu-chinh.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C4-da-dieu-chinh.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C5-ngay-dem.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C6-lich-su-sua.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C7-dan-lech.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/C8-loi-so-tien.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/mockups/ux-v6/index.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/so-cong-no-v5-model.js` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/so-cong-no-v5-ui.js` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/so-cong-no-v5.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/so-cong-no-v6-model.js` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/so-cong-no-v6-ui.js` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/so-cong-no-v6.html` | Mã/fixture hoặc mockup | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/so-khach-v7-api.js` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/preview/so-khach-v7-fixture.js` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/preview/so-khach-v7-live.html` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/preview/so-khach-v7-model.js` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/preview/so-khach-v7-ui.js` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/preview/so-khach-v7.html` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/preview/test-so-cong-no-v5-model.js` | Test | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/test-so-cong-no-v6-model.js` | Test | Không nhập: V5/V6 hoặc giữ main |
| `cong-no-web-handoff/preview/test-so-khach-v7-api.js` | Test | Nhập |
| `cong-no-web-handoff/preview/test-so-khach-v7-model.js` | Test | Nhập |
| `cong-no-web-handoff/tests/test_v7_ledger_api.py` | Test | Nhập |
| `cong-no-web-handoff/tests/test_v7_load_real_copy.py` | Test | Nhập |
| `cong-no-web-handoff/tools/test_pg_v7_backend.py` | Test | Nhập |
| `cong-no-web-handoff/tools/v7_backend_functions.sql` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/tools/v7_live_demo.py` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/tools/v7_load_real_copy.py` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/tools/v7_profile_xlsx.py` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/tools/v7_reconcile_real_copy.py` | Mã/fixture hoặc mockup | Nhập |
| `cong-no-web-handoff/web/v7_ledger_api.py` | Mã/fixture hoặc mockup | Nhập |
| `docs/business-rules.md` | Tài liệu/spec | Nền nhánh test mới hơn, lọc/đối chiếu V7 |
| `docs/decisions.md` | Tài liệu/spec | Nền nhánh test mới hơn, lọc/đối chiếu V7 |
| `package.json` | Mã/fixture hoặc mockup | Giữ main, chỉ thêm hai file test V7 |
| `specs/README.md` | Tài liệu/spec | Nhập |
| `specs/p0-write-path/02-versioned-approval-identity.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/p0-write-path/06-period-posting-lock.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/ux-brief-so-cong-no.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/ux-v5-ban-ghep.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/ux-v5-mockup-vong-2-html.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/ux-v5-mockup-vong-2.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/ux-v5-quyet-dinh-2026-10-17.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/ux-v6-quyet-dinh-2026-10-18.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/v5-giao-dien.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/v5-model-tien.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/v6-giao-dien.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/v6-model-tien.md` | Tài liệu/spec | Không nhập: V5/V6 hoặc giữ main |
| `specs/v7-backend-so-khach.md` | Tài liệu/spec | Nhập |
| `specs/v7-backend/ket-noi-giao-dien.md` | Tài liệu/spec | Nhập bản lọc tên/số liệu khách |
| `specs/v7-backend/schema-draft.sql` | Mã/fixture hoặc mockup | Nhập |
| `specs/v7-backend/thiet-ke.md` | Tài liệu/spec | Nhập bản lọc tên/số liệu khách |
| `specs/v7-migration-sheet.md` | Tài liệu/spec | Nhập bản lọc tên/số liệu khách |
| `specs/v7-so-khach-theo-sheet.md` | Tài liệu/spec | Nhập |
