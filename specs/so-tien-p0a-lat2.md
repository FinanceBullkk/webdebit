# Sổ tiền P0-a, lát 2: file gốc, ký ngày, API sau cờ, hai màn hình, xuất Excel

Trạng thái: hướng nghiệp vụ **ĐÃ CHỐT** ([`SO-TIEN-01`](../docs/decisions/so-tien-01.md)); lát 2 **code xong** trên nhánh `claude/so-tien-p0a-lat2`, PR nháp xếp trên lát 1 ([spec lát 1](so-tien-p0a.md)); **ĐÃ KIỂM CHỨNG** trên DB dùng một lần và trình duyệt với dữ liệu giả (mục [Bằng chứng](#bằng-chứng)); **chưa triển khai**. Như lát 1: **không merge, không chạy migration trên `hao`, chỉ dữ liệu bịa** cho tới khi có file sao kê mẫu và người dùng đồng ý triển khai (người dùng 25/11/2026: "Làm lát 2 ở đây"; bố cục hai trang chọn cùng ngày).

Thiết kế gốc: [F1](van-hanh-tai-chinh/F1-kien-truc-ky-thuat.md) mục 3, 4, 5.2, 6 (I-3), 7, 9, 11; [B mục 5](van-hanh-tai-chinh/B-quy-trinh-as-is-to-be.md#5-to-be-cuối-ngày-eod); [D](van-hanh-tai-chinh/D-business-rules.md) BR-IM11–13, BR-DC2–5; [E mục 6](van-hanh-tai-chinh/E-prd-p0.md#6-màn-hình-p0-tối-thiểu-5-màn-mới--2-chỗ-sửa). File này chỉ ghi phần của lát 2 và chỗ chốt cụ thể hơn F1.

## Đầu ra

1. Migration `2026-11-25-tien-p0a-lat2.sql` (+ file lùi), chạy sau lát 1: lưu file sao kê gốc, bằng chứng số dư ngân hàng nhập tay, review ngày hai chữ ký có mở lại, chặn ghi/hủy giao dịch của ngày đã ký, hàm đọc cho API và màn hình, dữ liệu xuất cho kế toán. Harness `test_pg_tien.py` chạy cả hai migration.
2. API `/api/v7/tien/*` sau cờ `WEBDEBIT_TIEN`, login DB riêng, cổng vai sổ tiền (không theo vai quản lý QUYEN-01), chặn bot chỉ-đọc ở mọi route kể cả GET.
3. Bộ đọc file theo mẫu (`web/v7_tien_import.py`): khung chung + mẫu thử `demo-csv@1` chỉ bật khi `WEBDEBIT_TIEN_DEMO=1` (test, máy dev). Mẫu VCB làm sau Discovery.
4. Hai trang: **Sổ tiền** (`so-tien.html`) và **Đối soát ngày** (`doi-soat-ngay.html`).
5. File Excel cho kế toán (`GET .../export.xlsx`) bằng `web/v7_xlsx_writer.py`.

## Phạm vi

| Trong lát 2 | Lát sau |
| --- | --- |
| `statement_file`, cột `statement_import.file_id`; xem trước nhận file gốc | Bộ đọc VCB (chờ mẫu, QD-07), "không phải bản gốc" (BR-IM14) |
| `balance_evidence`, `day_review`; ký số dư, ký đối soát, mở lại | `exception_case` (FR-09), tóm tắt tuần (FR-15) |
| Độ phủ ngày suy từ lô đã commit (không bảng riêng) | Máy canh, sao lưu thêm `tien`, runbook login `tien_api` |
| Hàm đọc: tài khoản của tôi, thẻ tài khoản, độ phủ, ngày, lô, giao dịch, file gốc, dữ liệu xuất | Tổng quan tiền cho sếp (FR-11), luật gợi ý (FR-14) |
| API đọc/ghi cho nhập lô, phân bổ, bằng chứng, ký, mở lại; xuất Excel | Màn quản trị: pháp nhân, tài khoản (HMAC số tài khoản), số dư mở, cấp vai |
| Trang Sổ tiền, Đối soát ngày; mục "Sổ tiền" trên menu khi cờ `on` | Xem trước lại từ file đã lưu khi lô cũ hết hạn |

## SQL lát 2

### Bảng (đều chỉ thêm: trigger chặn UPDATE/DELETE/TRUNCATE)

- `statement_file(id, account_id, file_sha256, byte_size ≤ 4 MiB, file_name, media_type ∈ {xlsx, csv}, content bytea, created_event)`; CHECK băm và cỡ đúng nội dung; một file một lần cho mỗi tài khoản `(account_id, file_sha256)`. `statement_import.file_id` (NULL được, khóa ngoại cùng tài khoản, không đổi sau khi ghi).
- `balance_evidence(id, account_id, as_of_date, amount_minor, source ∈ {bank_pdf, bank_app, bank_paper, other}, note, role_overlap, created_event)`: số dư **cuối ngày** theo ngân hàng do người xem tận mắt; bản mới nhất của ngày là bản dùng.
- `day_review(id, account_id, business_date, track ∈ {coverage, business}, action ∈ {sign, reopen}, role_overlap, snapshot, note, created_event)`: nhật ký ký/mở lại; trạng thái hiện tại của mỗi (ngày, mạch) là dòng mới nhất. `coverage`: chưa có dòng → `unconfirmed`; `business`: → `open`.

### Độ phủ ngày (BR-IM11, BR-IM12)

Ngày D của tài khoản, tính từ lô `committed` (lô hủy không tính): **đủ** khi có lô phủ D mà D trước ngày cuối của lô hoặc lô ghi ngày cuối đã trọn; **chưa trọn** khi chỉ có lô mà D là ngày cuối chưa trọn; **thiếu** khi không lô nào phủ. Ngày trước số dư mở: ngoài sổ. "Dữ liệu tới" = ngày cuối lớn nhất của lô đã commit.

### Kiểm ngày (I-3, BR-DC3, BR-DC4) — một hàm cho cả màn hình và lệnh ký

Ngày D sẵn sàng ký số dư khi không có lý do nào sau:

| Lý do | Khi |
| --- | --- |
| `NO_OPENING` | Tài khoản chưa có số dư mở |
| `DAY_FUTURE` / `BEFORE_OPENING` | D sau hôm nay (giờ VN) / trước ngày số dư mở |
| `DAY_INCOMPLETE` / `DAY_MISSING` | D chưa trọn / thiếu |
| `MISSING_DAYS_BEFORE` | Có ngày không đủ trong [ngày số dư mở, D − 1] (số dư cuối D chưa chứng minh được) |
| `PENDING_IMPORT` | Có lô `validated` có ngày đầu ≤ D (lô chờ có thể thêm giao dịch làm đổi số dư D) |
| `NO_EVIDENCE` | Không có bằng chứng số dư cuối D |
| `BALANCE_DIFFERENCE` | Có bằng chứng khác số dư sổ cuối D |

- **Số dư sổ cuối D** = số dư mở + Σ giao dịch chưa hủy có ngày ghi sổ ≤ D (vào cộng, ra trừ).
- **Bằng chứng từ file:** mỗi lô đã commit phủ **trọn** D và **có số dư cuối** cho một giá trị: số dư cuối của file − Σ dòng của file có ngày > D. Chỉ số dư cuối chứng minh file đủ dòng (file cụt mà có số dư cuối thì commit gãy `CLOSING_MISMATCH`); số dư đầu + dòng luôn bằng sổ vì commit đã kiểm liền mạch, nên file chỉ có số dư đầu không là bằng chứng (review độc lập lát 2, mức TB).
- **Bằng chứng dùng để ký** (`current`): của lô mới nhất (mã lô lớn nhất) phủ trọn D — lô đó không có số dư cuối thì không có bằng chứng file, phải nhập tay — cùng bản nhập tay mới nhất của D; cái nào có cũng phải bằng số dư sổ. Lô cũ hơn chỉ hiện để xem: ngân hàng có thể ghi lùi ngày một giao dịch sau khi file cũ đã tải, file cũ khi đó là ảnh chụp lỗi thời chứ không phải lỗi của sổ (nếu bắt mọi file khớp, ngày đó sẽ không bao giờ ký được).
- `role_overlap` khi ký số dư: người ký là người xem trước hoặc commit một lô đã commit phủ D, hoặc người nhập bằng chứng tay đang dùng; trùng vai của bản nhập tay tính lại mỗi lần đọc (người nhập bằng chứng cũng nhập lô phủ D, kể cả lô nhập sau). Khi ký đối soát: người ký nhập lô phủ D hoặc đã phân bổ giao dịch của D. Trùng vai được phép, có đánh dấu (QD-06, QD-24).

### Chặn đổi tiền của ngày đã ký (BR-IM13)

Số dư cuối một ngày là tổng dồn từ số dư mở, nên giao dịch của **mọi ngày trước** cũng làm đổi số dư ngày đã ký. Trigger trên `bank_transaction`: thêm giao dịch, hoặc hủy (đặt `voided_event`) giao dịch, có ngày ghi sổ ≤ một ngày đang **đã ký số dư** → `DAY_SIGNED`, DETAIL là ngày đã ký sớm nhất từ ngày của giao dịch trở đi (`_signed_from`) — ngày cần mở lại. Mở lại số dư một ngày kéo theo mọi ngày sau đang ký số dư (kèm chữ ký đối soát của chúng) trong một sự kiện, nên mở lại đúng ngày DETAIL là đủ (review độc lập lát 2, mức TB: bản đầu chỉ chặn đúng ngày). Commit lô chỉ xác nhận trùng (không tạo giao dịch) vẫn được. Phân bổ không đổi tiền nên không bị chặn; ký đối soát lưu số đếm lúc ký.

### Hàm lệnh mới hoặc thay

| Hàm | Vai | Việc | Lỗi |
| --- | --- | --- | --- |
| `preview_import` (thay bản lát 1) | `tien_nhap` | Như lát 1, thêm khóa tùy chọn `file: {name, media_type, content_base64}`: băm nội dung phải bằng `file_sha256`; cùng file đã lưu ở tài khoản thì dùng lại; file báo ngày cuối đã trọn mà ngày cuối là hôm nay → từ chối (hôm nay chưa hết ngày, BR-IM11); kết quả thêm `file_id` và `signed_days` (với mỗi dòng mới/nghi trùng: ngày đã ký sớm nhất từ ngày của dòng trở đi) | như lát 1 |
| `record_balance_evidence` | `tien_review` | Ghi số dư cuối ngày theo ngân hàng (ngày từ số dư mở tới hôm nay), nguồn, ghi chú bắt buộc | `NO_OPENING`, `REASON_REQUIRED`, `INVALID_COMMAND` |
| `sign_day_coverage` | `tien_review` | Ký số dư khi kiểm ngày sẵn sàng; `expected_version` = version tài khoản đã xem; đã ký → trả lại, không ghi | `STALE_VERSION`, `DAY_NOT_READY` (DETAIL: lý do) |
| `sign_day_business` | `tien_review` | Ký đối soát khi số dư đã ký; lưu số giao dịch theo trạng thái lúc ký (được ký khi còn khoản chưa phân bổ, BR-DC2) | `DAY_NOT_READY` (`COVERAGE_NOT_SIGNED`) |
| `reopen_day` | `tien_review` | Mở lại `coverage` của D kéo theo mọi ngày sau đang ký số dư và chữ ký đối soát của các ngày đó; `business` chỉ mở D; lý do bắt buộc; kết quả `reopened_days` | `REASON_REQUIRED`, `INVALID_COMMAND` |

Mọi lệnh như lát 1: người làm từ `tien.actor`, khóa lặp, khóa dòng tài khoản trước mọi kiểm, vết `balance_evidence` / `day_sign_coverage` / `day_sign_business` / `day_reopen` (trước → sau).

### Hàm đọc mới (cần một vai bất kỳ ở phạm vi tài khoản, trừ khi ghi khác)

`my_access()` (mọi người: vai của chính mình) · `list_accounts()` · `get_account_card(account)` (tóm tắt lát 1 + dữ liệu tới, ngày thiếu, lô chờ, ngày ký gần nhất) · `get_coverage(account, from, to)` (≤ 93 ngày: độ phủ + hai trạng thái ký) · `get_day(account, date)` (kiểm ngày, bằng chứng, chênh, lịch sử ký, số giao dịch theo trạng thái, version) · `list_imports(account)` (100 lô gần nhất) · `get_import(import)` (lô `validated`: phân loại lại như commit, có `stale`; lô khác: dòng → giao dịch) · `get_transaction(tx)` (nguồn, phân bổ hiện tại, lịch sử phân bổ) · `get_statement_file(file)` (`tien_nhap`/`tien_review`) · `export_rows(account, from, to)` (`tien_review`, ≤ 366 ngày; số dư đầu kỳ NULL khi kỳ bắt đầu trước ngày số dư mở). Mô tả, ô gốc chỉ trả cho `tien_nhap`/`tien_review` (QD-08). Quyền chạy: năm hàm tóm tắt (`my_access`, `list_accounts`, `get_account_card`, `get_coverage`, `get_day`) cấp cho `tien_app` và `tien_reader`; năm hàm có nội dung (lô, giao dịch, file gốc, xuất) chỉ `tien_app`.

## API

- **Cờ** `WEBDEBIT_TIEN` = `off` (mặc định) | `shadow` | `on`, đọc lúc khởi động; giá trị lạ coi như `off`. `off`: mọi `/api/v7/tien/*` trả 404 `TIEN_OFF`. `shadow`: chỉ login có vai `tien_review` hoặc `tien_quan_tri` (ở đâu cũng được) dùng được, người khác 403 `TIEN_FORBIDDEN`; không có mục menu. `on`: theo vai.
- **Login DB riêng:** runner thứ hai `PsqlDirect(..., role=tien_api)` (`--tien-db-user`, mặc định `tien_api`, thành viên `tien_app` do runbook tạo). Kiểm trước không qua thì module tắt và ghi journal, sổ nợ chạy bình thường. Mỗi câu SQL đặt `SET LOCAL tien.actor`, `tien.actor_kind = 'human'`.
- **Cổng:** route và trang sổ tiền mở cho cả hai vai QUYEN-01; quyền thật ở `access_grant` trong hàm SQL. Bot chỉ-đọc bị `READ_ONLY_PEER` ở mọi route `/api/v7/tien` kể cả GET.
- **Lỗi:** thêm vào `ERRORS` mọi mã của `tien` (câu tiếng Việt, mã HTTP); `BALANCE_CHAIN_BROKEN`, `DAY_NOT_READY`, `DAY_SIGNED` trả kèm `detail` (chuỗi mã, ngày). `DAY_SIGNED` có ngày thì câu báo nói rõ "Ngày dd/mm/yyyy đã ký số dư … Mở lại ngày dd/mm/yyyy ở Đối soát ngày". Thân lệnh có ký tự điều khiển (kể cả NUL, xuống dòng trong khóa), mã số quá lớn → 422 trước khi tới DB.
- **Log truy cập (NFR-03):** tải file gốc, xuất Excel, mở lô có ô gốc và đọc giao dịch có nội dung chuyển khoản ghi một dòng journal: login, việc, mã đối tượng hoặc kỳ; không nội dung.

| Route | Gọi | Ghi chú |
| --- | --- | --- |
| `GET /api/v7/tien/me` | `my_access` | `{mode, grants, templates}`; shadow mà không đủ vai → `visible: false` (không 403) để trang báo đúng |
| `GET /accounts`, `/accounts/{id}` | `list_accounts`, `get_account_card` | |
| `GET /accounts/{id}/coverage?from=&to=` | `get_coverage` | Mặc định 93 ngày tới hôm nay |
| `GET /accounts/{id}/days/{YYYY-MM-DD}` | `get_day` | |
| `GET /accounts/{id}/imports`, `/imports/{id}` | `list_imports`, `get_import` | |
| `GET /accounts/{id}/transactions?from=&to=`, `/transactions/{id}` | `list_transactions` (lát 1), `get_transaction` | |
| `GET /files/{id}` | `get_statement_file` | Tải file gốc, `Content-Disposition: attachment` |
| `GET /accounts/{id}/export.xlsx?from=&to=` | `export_rows` | File Excel |
| `POST /imports/preview` | bộ đọc → `preview_import` | `{account_id, template, file_name, content_base64}`; thân tối đa 6 MiB, file tối đa 4 MiB |
| `POST /imports/commit`, `/imports/reject`, `/imports/void` | lát 1 | |
| `POST /allocations` | `set_allocation` | |
| `POST /balance-evidence` | `record_balance_evidence` | |
| `POST /days/sign-coverage`, `/days/sign-business`, `/days/reopen` | ba hàm ký | |

**Bộ đọc file:** mẫu nằm trong sổ đăng ký `TEMPLATES` (tên@phiên bản → hàm đọc bytes → kỳ, số dư đầu/cuối, ngày cuối đã trọn, dòng StatementLine v1). Lỗi cấu trúc file → 422 `IMPORT_PARSE_ERROR` kèm dòng; mẫu lạ hoặc chưa bật → 422 `TEMPLATE_UNKNOWN`. Giá trị dòng sai (ngày, chiều, số tiền) vẫn đi xuống SQL để thành lỗi dòng như lát 1. `demo-csv@1` (CSV UTF-8, chỉ dữ liệu bịa): dòng `#period,YYYY-MM-DD,YYYY-MM-DD,complete|partial`, dòng `#opening,<số>`, dòng `#closing,<số>` (tùy chọn), rồi tiêu đề `date,ref,description,debit,credit,balance`.

## Màn hình (thiết kế theo skill `thiet-ke-ux`)

**Bài toán.** Kế toán (trên 40 tuổi, màn 1280×720, thấy ~1280×560) mỗi ngày làm việc lúc 17h: tải sao kê gốc → nhập → ghi vào sổ → phân loại → ký; người đối chiếu (có thể là chính kế toán, có đánh dấu) quyết dòng nghi trùng và ký. Giá trị số 1: không ghi tiền hai lần, không mất giao dịch, số dư sổ = ngân hàng trước khi ký. Câu hỏi theo thứ tự: số dư theo sao kê là bao nhiêu, tới ngày nào, có ngày thiếu không → file mới có gì mới/nghi trùng/lỗi → ngày nào chưa ký, vì sao → giao dịch nào chưa rõ.

**Cấu trúc (người dùng chọn 25/11/2026: hai trang theo việc).**

1. **Sổ tiền** — mục tiêu: đưa sao kê vào sổ đúng một lần và thấy số dư.
   - Đầu trang: chọn tài khoản (một tài khoản thì chỉ là nhãn) + thẻ "Số dư theo sao kê … tới hết ngày …", dòng phụ: ngày chưa trọn, số ngày thiếu, lô chờ ghi. Chưa có số dư mở → câu báo, không số.
   - Khối **Nhập sao kê** (người có `tien_nhap`): nút chọn file (.xlsx/.csv, ≤ 4 MiB) → xem trước: kỳ, số dòng theo lớp, số dư đầu/cuối khớp hay gãy (câu thường, không mã), danh sách **chỉ các dòng cần quyết** (nghi trùng, giao dịch cũ file không có) và dòng lỗi; bảng đủ dòng mở khi bấm. Người có `tien_review` chọn "Giao dịch mới" / "Trùng giao dịch …" cho từng dòng nghi trùng (ứng viên: ứng viên mềm của dòng và giao dịch file chưa nhận cùng ngày, chiều, số tiền) và ghi lý do giữ cho giao dịch cũ; người chỉ có `tien_nhap` thấy câu "… cần xác nhận: người có vai đối chiếu mở lô này". Luật của `commit_import` (lát 1): **mọi** giao dịch đã có trong kỳ mà file chưa nhận chắc chắn (giao dịch file không có và ứng viên mềm) phải là đích "trùng" của một dòng hoặc được giữ có lý do — chọn "mới" cho dòng nghi trùng thì ứng viên mềm của nó cũng phải giữ có lý do; câu hỏi giữ chỉ hiện khi giao dịch không còn là lựa chọn của dòng chưa quyết; hai dòng không trùng cùng một giao dịch. Nút chính **Ghi vào sổ**, phụ **Bỏ lô** (lý do). Ngày đã ký sẽ bị đổi số dư → khối **cảnh báo** (vàng, không chặn: dòng chọn "trùng" không tạo giao dịch nên vẫn ghi được); máy chủ chặn thì câu báo nói ngày cần mở lại. Chỗ chặn thật (đỏ): lô hết hạn, dòng lỗi (ô số tiền sai dạng hiện nguyên văn), gãy số dư (câu thường, tối đa 5).
   - Khối **Lô đã nhập**: kỳ, trạng thái, người, lúc; tải file gốc (`tien_nhap`/`tien_review`); hủy lô (`tien_review`, lý do).
   - Khối **Giao dịch**: lọc kỳ (mặc định tháng hiện tại) và trạng thái; bấm dòng mở ngăn chi tiết (nguồn, phân bổ, lịch sử); nút Xuất Excel (`tien_review`).
2. **Đối soát ngày** — mục tiêu: chốt từng ngày.
   - Cột trái: danh sách ngày (mới nhất trên, từ số dư mở, cửa sổ 93 ngày; nút "Ngày trước …" và "Về các ngày gần nhất"), mỗi ngày hai chữ trạng thái "Số dư: đã ký / chưa ký / thiếu sao kê / chưa trọn / mở lại" và "Đối soát: …"; hôm nay chưa có sao kê ghi "Chưa tải sao kê", không tô đỏ. Mặc định mở ngày cũ nhất đủ sao kê còn việc. Đọc ngày lỗi thì báo lỗi, không để số của ngày trước dưới nhãn ngày mới.
   - Bên phải, ngày đang chọn: ① **Số dư**: số dư sổ cuối ngày, từng bằng chứng ngân hàng và chênh; lý do chưa ký bằng câu thường; form "Nhập số dư ngân hàng" (`tien_review`); nút **Ký số dư**. ② **Giao dịch trong ngày**: bảng có trạng thái phân loại, nút **Phân bổ** (`tien_phan_bo`) mở hộp phân bổ (đích, số tiền, ghi chú; còn lại tính sẵn; bỏ/đổi dòng cũ đòi lý do; sổ khách chỉ hiện sổ đang dùng, xếp theo tên; chuyển nội bộ ghi mã giao dịch chân kia — mã `#id` hiện ở bảng giao dịch; lỗi máy chủ hiện ngay trong hộp, dòng đang sửa còn nguyên); nút **Ký đối soát** kèm số khoản chưa phân bổ. ③ Lịch sử ký, nút **Mở lại** (lý do; mở lại số dư nói trước là các ngày sau đang ký mở lại theo, câu báo kê các ngày đã mở).
- **Trạng thái:** đang tải; chưa bật module; chưa có vai; chưa có tài khoản; chưa số dư mở; mất mạng (giữ dữ liệu đã nhập, cùng mã yêu cầu khi gửi lại); lô hết hạn (sổ đã đổi từ lúc xem trước) → câu báo + Bỏ lô; NULL hiện `—`; trùng vai hiện nhãn "Người ký cũng là người nhập (trùng vai)"; dữ liệu sao kê cũ hơn hôm qua → nhãn "Chưa có sao kê từ ngày …". Lý do, ghi chú người gõ gộp xuống dòng và khoảng trắng thừa trước khi gửi (API từ chối ký tự điều khiển).
- **Hệ thị giác:** token `cong-no-theme.css`, chữ thân ≥ 15px như trang hiện có, nút ≥ 40px, trạng thái luôn có chữ; tiền nhóm nghìn, căn phải, `tabular-nums`; số tiền tính ở SQL hoặc file `*-model.js`, không tính trong `*-ui.js` (ARCH-03).

## Xuất Excel cho kế toán

`GET /api/v7/tien/accounts/{id}/export.xlsx?from=&to=` (`tien_review`, ≤ 366 ngày, chỉ VND ở P0). Ba sheet: **Giao dịch** (ngày ghi sổ, ngày hiệu lực, mã giao dịch ngân hàng, nội dung, thu, chi, trạng thái, đã phân bổ, còn lại, lô nguồn), **Phân bổ** (mã giao dịch, ngày, loại đích, đích, số tiền, ghi chú), **Ngày** (ngày, độ phủ, ký số dư, ký đối soát). Đầu sheet: tài khoản (ngân hàng, 4 số cuối; tài khoản tiền mặt ghi `tiền mặt #id`), kỳ, số dư sổ đầu và cuối kỳ (kỳ bắt đầu trước ngày số dư mở thì ô số dư đầu ghi "chưa có: sổ bắt đầu ngày …", không ghi 0), người xuất, lúc xuất. Ô chữ ghi dạng chữ, không công thức.

## Tiêu chí nghiệm thu

- [x] Harness: lát 1 + lát 2 chạy hai lần trên DB trống; mọi ca lát 1 vẫn xanh với `preview_import` mới; file lùi lát 2 tự dừng khi đã có dữ liệu lát 2, chạy được khi chưa, rồi chạy lại lát 1 + lát 2 được.
- [x] Xem trước có file: lưu file một lần, cùng file lần hai dùng lại; băm sai, base64 sai → `INVALID_COMMAND`; quá 4 MiB → API 413 `FILE_TOO_LARGE` trước DB (cột `byte_size` có CHECK làm lớp hai); `get_statement_file` chỉ vai nhập/review.
- [x] Độ phủ: file 1–3 (ngày 3 chưa trọn) → 1, 2 đủ, 3 chưa trọn, 4 thiếu; file 3–5 → 3, 4 đủ; hủy lô → ngày trở lại thiếu.
- [x] Ký số dư: từng lý do của bảng Kiểm ngày gây `DAY_NOT_READY` đúng mã; bằng chứng file và tay khớp → ký được; `keep_existing` làm sổ lệch file → `BALANCE_DIFFERENCE`; sai version → `STALE_VERSION`; ký lặp → không ghi thêm; người nhập tự ký → `role_overlap`.
- [x] Ngày đã ký: commit lô có dòng mới ở ngày đó → `DAY_SIGNED`; lô chỉ trùng → commit được; hủy lô làm mất giao dịch ngày đó → `DAY_SIGNED`; mở lại (lý do) → commit được.
- [x] Ký đối soát khi chưa ký số dư → `DAY_NOT_READY`; ký được khi còn khoản chưa phân bổ, số đếm vào snapshot; mở lại số dư kéo theo đối soát.
- [x] Vai: người chỉ `tien_xem` đọc được thẻ, ngày, giao dịch không mô tả; không đọc file gốc, không xuất; mọi lệnh ký cần `tien_review`.
- [x] API (unittest): cờ off → 404; shadow chặn người không đủ vai; bot chỉ-đọc bị chặn cả GET; thân lệnh lạ → 422 trước DB; mọi mã `RAISE` của hai migration có trong `ERRORS`; bộ đọc `demo-csv@1` đúng/sai; Excel ba sheet đọc lại đúng.
- [ ] Trình duyệt (dữ liệu giả): đi hết luồng nhập → quyết nghi trùng → ghi; ký số dư; phân bổ; ký đối soát; mở lại; mất mạng giữ dữ liệu; vai thiếu không thấy nút; xem ở 1280×720.
- [ ] `npm run check` xanh; `node scripts/check-secrets.js` sạch; harness có trong CI.

## Bằng chứng

ĐÃ KIỂM CHỨNG ngày 25/11/2026 trên máy dev, dữ liệu bịa, chưa đụng `hao`:

- **Harness** `tools/test_pg_tien.py` (PostgreSQL 18.6 dùng một lần, chạy lát 1 + lát 2): 40 nhóm ca xanh, 53,7 giây, container và volume đã dọn (`verified_and_removed`).
- **Đột biến SQL** (sửa hỏng đúng chỗ, harness phải đỏ): m1 trigger ngày đã ký không làm gì, m2 mọi file đều "dùng để ký", m3 bỏ lý do `PENDING_IMPORT`, m4 chỉ chặn đúng ngày đã ký, m5 tính file chỉ có số dư đầu là bằng chứng — cả năm đỏ đúng nhóm ca.
- **Chuỗi migration V7** `test_pg_v7_backend.py --migration-test` (file lát 2 ở `outside_chain`): SCHEMA 10/10, BEHAVIOR 78/78, 2 SKIPPED_OPEN có từ trước.
- **`npm run check`** (bản sau review): ruff, luật nghiệp vụ, link tài liệu, cỡ chữ, `check-secrets --all`, eslint xanh; unittest 2083 ca OK (19 bỏ qua có từ trước); test JS 350/350.
- **Trình duyệt** (máy chủ giả làm theo luật `commit_import`, `set_allocation`, `reopen_day` thật): `test-so-tien-model.js` 7/7, `test-so-tien-browser.js` 12/12; ảnh 1280×720 đã xem (thẻ số dư, xem trước lô, cảnh báo ngày đã ký, Đối soát ngày, hộp phân bổ). **Đột biến giao diện** — U chỉ gồm giao dịch file không có, mã chân kia gửi dạng số, bỏ cả hai lớp chặn số ngày cũ, lý do chỉ cắt hai đầu, cảnh báo ngày đã ký thành chỗ chặn — cả năm làm ca liên quan đỏ.

## Phạm vi agent

- Agent: claude ([`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md)). Review độc lập: SQL + API, giao diện.
- Được sửa: hai file migration lát 2 (mới); `tools/test_pg_tien.py`; `tools/test_pg_v7_backend.py` (`outside_chain`); `web/v7_api_tien.py`, `web/v7_tien_import.py`, `web/v7_tien_xlsx.py` (mới); `web/v7_ledger_api.py`, `web/v7_api_tables.py`, `web/v7_psql.py`, `web/v7_role.py`, `web/v7_presence.py` (nối route, lỗi, cờ, trang); `preview/so-tien*`, `preview/doi-soat-ngay*` (mới), `preview/app-nav.js`, `eslint.config.js`; test mới trong `tests/`, `preview/`; `docs/development.md`, `MAP.md`, `specs/README.md`, file này.
- Lệnh kiểm: harness `test_pg_tien.py`; `test_pg_v7_backend.py --migration-test`; `npm run check`; `node scripts/check-secrets.js`.
- Cấm: đụng schema/role/hàm `sokhach`, `doixe`; ssh, `hao`; dữ liệu thật; thư viện mới; merge.

## Câu hỏi mở

Chỗ spec chưa nói rõ, agent chọn khi làm (ĐỀ XUẤT):

- Độ phủ không lưu bảng `coverage_segment` như F1 vẽ: suy thẳng từ lô đã commit để không có hai nguồn lệch nhau.
- Bằng chứng từ file chỉ dùng số dư đầu/cuối của file, không dùng số dư sau từng dòng (thứ tự dòng trong ngày của ngân hàng chưa khảo sát). Bộ đọc VCB tự suy số dư đầu/cuối nếu file chỉ có số dư sau từng dòng.
- Bằng chứng dùng để ký là file mới nhất phủ trọn ngày và bản nhập tay mới nhất (nhập bản mới để sửa bản tay nhập sai); file cũ lệch chỉ hiện để xem. Ngân hàng ghi lùi ngày làm số dư các ngày sau đổi theo: ngày nào file mới nhất còn là file cũ thì báo lệch tới khi tải file mới phủ ngày đó.
- Ký số dư đòi `expected_version` (đã xem gì thì ký đúng cái đó); ký đối soát không đòi vì không chứng nhận số tiền.
- Hủy lô làm mất bằng chứng file của ngày đã ký mà không mất giao dịch thì vẫn được; màn Đối soát báo "đã ký nhưng hiện không còn khớp" khi kiểm hiện tại không qua.
- **CÒN MỞ** (review lát 2, Thấp, chưa đổi): lô chờ cũ (hết hạn vì sổ đã đổi) vẫn chặn ký mọi ngày từ ngày đầu của lô (`PENDING_IMPORT`) tới khi có người bỏ lô, mà bỏ lô cần `tien_nhap` — người chỉ có `tien_review` không tự gỡ được. Câu lý do trên màn nói rõ ai bỏ được lô. Cách khác (lô hết hạn không chặn, hoặc cho `tien_review` bỏ lô) đổi luật quyền của lát 1 nên chờ người dùng chọn khi chạy thử với kế toán.
- Lý do/ghi chú gõ nhiều dòng được gộp thành một dòng trước khi gửi (API từ chối ký tự điều khiển để psql không lỗi); nếu kế toán cần xuống dòng trong lý do thì đổi cách truyền tham số psql, không nới kiểm.
