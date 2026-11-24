# Sổ tiền P0-a, lát 1: schema `tien`, nhập lô, giao dịch, phân bổ (SQL + harness)

Trạng thái: hướng nghiệp vụ **ĐÃ CHỐT** ([`SO-TIEN-01`](../docs/decisions/so-tien-01.md)); lát 1 **ĐANG LÀM** trên nhánh `claude/so-tien-p0a`, PR nháp, **không merge, không chạy migration trên `hao`** cho tới khi có file sao kê mẫu và người dùng đồng ý triển khai (người dùng 24/11/2026: "Làm phần đó trước" — dựng phần không cần file sao kê, chạy bằng dữ liệu bịa). Lý do không merge: PR có `.sql` làm `Deploy hao` dừng chờ triển khai tay, chặn lượt tự triển khai của mọi PR khác.

Thiết kế gốc: [F1 kiến trúc](van-hanh-tai-chinh/F1-kien-truc-ky-thuat.md), [F2 ADR](van-hanh-tai-chinh/F2-adr.md), [D quy tắc](van-hanh-tai-chinh/D-business-rules.md). File này chỉ ghi phần của lát 1 và các chỗ chốt cụ thể hơn F1.

## Đầu ra

Một migration tạo schema `tien` (bảng, trigger, hàm lệnh, hàm đọc, quyền) và một harness PostgreSQL dùng một lần chứng minh: nhập lô có xem trước và commit idempotent, chống trùng hai tầng, kiểm số dư liên tục, hủy lô không làm mất tiền thật, phân bổ nhiều–nhiều có trần và phiên bản, kiểm vai và phạm vi pháp nhân ngay trong hàm SQL, bảng chỉ thêm. Không API, không giao diện, không bộ đọc file VCB.

## Phạm vi

| Trong lát 1 | Lát sau |
| --- | --- |
| `currency`, `legal_entity`, `financial_account`, `account_opening`, `access_grant` | `ar_book_entity` và kiểm pháp nhân của sổ nợ (QD-17) |
| `statement_import`, `raw_statement_line`, `bank_transaction`, `bank_transaction_source` | `statement_file` (lưu file gốc, QD-08), bộ đọc VCB |
| `allocation` với các đích P0 trừ `payment_request`, `ar_receipt` | Đề nghị chi, duyệt (P0-b); nối sổ nợ (P0-c) |
| `event`, `idempotency`, trigger chỉ thêm | `coverage_segment`, `balance_evidence`, `day_review`, `exception_case` |
| Hàm lệnh: thực thể, tài khoản, số dư mở, cấp/thu vai, xem trước, commit, bỏ lô, hủy lô, phân bổ | API `/api/v7/tien`, cờ `WEBDEBIT_TIEN`, màn hình, máy canh, sao lưu |
| Hàm đọc: tóm tắt tài khoản, danh sách giao dịch | Xuất xlsx cho kế toán |

## Vai trò DB

`tien_owner` (sở hữu schema), `tien_app` (chỉ EXECUTE hàm lệnh và hàm đọc), `tien_reader` (chỉ EXECUTE hàm đọc), đều NOLOGIN. Login cho API tạo ở runbook triển khai (lát sau), không trong migration. Không cấp quyền bảng cho `tien_app`/`tien_reader`; hàm `SECURITY DEFINER`, `SET search_path TO 'pg_catalog', 'tien', 'pg_temp'`, `REVOKE ALL ... FROM PUBLIC` như `sokhach` (ví dụ `schema/v7_schema_current.pgsql:5705-5780`). Migration không đụng schema, role hay hàm nào của `sokhach`/`doixe`.

## Danh tính và vai nghiệp vụ

- Người làm lấy từ `current_setting('tien.actor', true)` (bắt buộc, không rỗng → `ACTOR_REQUIRED`) và `current_setting('tien.actor_kind', true)` ∈ {`human`, `machine`} (sai → `ACTOR_REQUIRED`). API đặt hai biến này bằng `SET LOCAL` (lát sau).
- `access_grant(login, role, legal_entity_id, account_id NULL, created_event, revoked_event NULL)`; vai ∈ {`tien_xem`, `tien_nhap`, `tien_phan_bo`, `tien_review`, `tien_quan_tri`}. Một cấp vai hiệu lực khi `revoked_event IS NULL` và (`account_id` = tài khoản, hoặc `account_id IS NULL` và `legal_entity_id` = pháp nhân của tài khoản).
- `_require(role, account_id)`: không có cấp vai đúng → `TIEN_FORBIDDEN` nếu login không có vai đó ở đâu cả, `ENTITY_SCOPE` nếu có vai đó nhưng ở pháp nhân/tài khoản khác. Hàm đọc cần `tien_xem` (hoặc bất kỳ vai nào khác ở cùng phạm vi).
- Cấp vai đầu tiên (`tien_quan_tri` của một pháp nhân) do người chạy migration chèn tay theo runbook; trong harness chèn bằng role owner. `grant_role` cần `tien_quan_tri` ở pháp nhân đó và **không** cấp cho chính mình (`SELF_GRANT`).

## Hàm lệnh (một tham số `jsonb`, trả `jsonb`)

Mọi lệnh ghi: có `idempotency_key`; bảng `idempotency(scope, key, request_hash, result)` với scope = `account:<id>` hoặc `entity:<id>`; cùng khóa cùng nội dung trả lại kết quả cũ, khác nội dung → `IDEMPOTENCY_CONFLICT` (băm nội dung không gồm người làm). Lệnh trên tài khoản khóa dòng `financial_account` (`FOR NO KEY UPDATE`) trước mọi kiểm. Mỗi lệnh ghi đúng các event của nó (trước → sau, `actor`, `actor_kind`, `idempotency_key`).

| Hàm | Vai | Việc chính | Lỗi chính |
| --- | --- | --- | --- |
| `create_legal_entity` | `tien_quan_tri` (bất kỳ phạm vi) | Tạo pháp nhân (mã duy nhất) | `INVALID_COMMAND` |
| `create_account` | `tien_quan_tri` của pháp nhân | Tạo tài khoản: loại, mã ngân hàng, 4 số cuối, HMAC hex 64, tiền tệ, chủ sở hữu, mẫu file, `bank_ref_stable` (mặc định false; true thì bắt buộc có mẫu file, CHECK `NOT bank_ref_stable OR statement_template IS NOT NULL`) | `INVALID_COMMAND`, `DUPLICATE_ACCOUNT` |
| `set_opening` | `tien_quan_tri` | Số dư mở một lần cho mỗi tài khoản (`as_of`, `amount_minor`, ghi chú bằng chứng không rỗng) | `OPENING_EXISTS` |
| `grant_role`, `revoke_role` | `tien_quan_tri` | Cấp/thu vai | `SELF_GRANT` |
| `preview_import` | `tien_nhap` | Kiểm và phân loại dòng (mục dưới), lưu lô `validated` + dòng gốc; cùng tài khoản + cùng `file_sha256` đã commit → trả lô cũ, `new` = 0; `period_to` sau hôm nay (giờ VN) bị từ chối | `NO_OPENING`, `INVALID_COMMAND` |
| `commit_import` | Lô không có quyết định: `tien_nhap`. Có `suspect_decisions` hoặc `keep_existing`: `tien_review` (người đối chiếu tự commit được, không cần thêm `tien_nhap`) | Phân loại lại dưới khóa; nhận `expected_preview_hash`, `suspect_decisions: [{line_no, decision: new \| duplicate_of, transaction_id?}]`, `keep_existing: [{transaction_id, reason}]`; ghi giao dịch và dòng nguồn; quyết định và giao dịch giữ (kèm lý do) vào event; lô `committed`; `financial_account.version + 1` | `IMPORT_PREVIEW_STALE`, `IMPORT_HAS_ERRORS`, `BALANCE_CHAIN_BROKEN`, `IMPORT_SUSPECT_UNRESOLVED`, `DUPLICATE_TARGET_INVALID`, `REASON_REQUIRED`, `INVALID_COMMAND`, `TIEN_FORBIDDEN`/`ENTITY_SCOPE` |
| `reject_import` | `tien_nhap` | Lô `validated` → `rejected`, lý do bắt buộc | `REASON_REQUIRED` |
| `void_import` | `tien_review` | Lô `committed` → `voided`, lý do bắt buộc; giao dịch chỉ bị hủy khi không còn dòng nguồn ở lô khác chưa hủy; chặn nếu giao dịch sẽ hủy còn phân bổ hiệu lực | `REASON_REQUIRED`, `VOID_WOULD_LOSE_ALLOCATED` |
| `set_allocation` | `tien_phan_bo` | Thay cả bộ dòng phân bổ của một giao dịch; `expected_version` của giao dịch | `STALE_VERSION`, `OVER_ALLOCATION`, `REASON_REQUIRED`, `TRANSACTION_VOID`, `INVALID_COMMAND` |

Hàm đọc: `get_account_summary(account_id)` (số dư mở, Σ vào, Σ ra, số dư sổ tiền, ngày ghi sổ mới nhất, số giao dịch theo trạng thái phân loại), `list_transactions(account_id, from, to)` (mỗi giao dịch: số tiền, chiều, ngày, `bank_ref`, đã/chưa phân bổ, trạng thái, nguồn, `version`). Mô tả chuyển khoản chỉ trả khi người đọc có `tien_nhap` hoặc `tien_review`.

## Phân loại dòng (xem trước và commit dùng đúng một hàm)

Đầu vào mỗi dòng theo `StatementLine v1` ([F1 §5.1](van-hanh-tai-chinh/F1-kien-truc-ky-thuat.md#51-statementline-v1--đầu-ra-bộ-đọc)): `line_no`, `booking_date`, `value_date?`, `direction`, `amount_minor` (chuỗi số nguyên), `currency`, `description?`, `bank_ref?`, `balance_after_minor?`, `cells` (object chữ nguyên văn).

1. **Kiểm dòng** → lớp `error` kèm mã: `LINE_DUPLICATE_NO`, `LINE_OUT_OF_PERIOD`, `LINE_FUTURE_DATE` (sau hôm nay theo `Asia/Ho_Chi_Minh`), `LINE_BEFORE_OPENING` (trước `as_of` của số dư mở), `LINE_DIRECTION`, `LINE_AMOUNT` (không phải số nguyên dương vừa `bigint`), `LINE_CURRENCY`.
2. **Dấu vân** = SHA-256 của `account_id | booking_date | direction | amount_minor | mô tả chuẩn hóa` (mô tả: `normalize(..., NFC)`, bỏ khoảng trắng đầu cuối, gộp khoảng trắng, chữ thường; biểu thức chính quy dùng lớp `[[:space:]]`, không dấu gạch chéo, nên không đổi theo `standard_conforming_strings` của phiên gọi). **Không** gồm số dư sau.
3. Tài khoản `bank_ref_stable` và dòng có `bank_ref`: `duplicate` nếu đã có giao dịch chưa hủy cùng (tài khoản, `source_family`, `bank_ref`) **và** cùng ngày ghi sổ, chiều, số tiền; ngược lại `new`. Cùng mã mà khác ngày/chiều/số tiền là ngân hàng dùng lại mã, không phải trùng: dòng `new` rồi qua bước 4b. Nhiều dòng cùng khóa (mã, ngày, chiều, số tiền): dòng thứ k (theo `line_no`) ghép giao dịch thứ k (theo `id`), dòng thừa `new`.
4. Còn lại: nhóm dòng hợp lệ theo dấu vân; E = số giao dịch chưa hủy của tài khoản cùng dấu vân (xếp theo `id`), F = số dòng cùng dấu vân (xếp theo `line_no`). E = 0 → mọi dòng `new`. E > 0 → min(E, F) dòng đầu là `duplicate` với ứng viên là giao dịch thứ k; F − E dòng còn lại (nếu F > E) là `suspect`.

   **4b. Ghép mềm** (BR-IM8, ADR-TIEN-03: mô tả có thể đổi giữa hai lần tải). U = giao dịch chưa hủy của tài khoản có ngày ghi sổ trong [`period_from`, `period_to`] chưa là ứng viên của dòng nào ở bước 3–4. Dòng đang `new` ghép được với giao dịch U cùng ngày ghi sổ, chiều, số tiền, trừ khi cả dòng lẫn giao dịch đều có mã ngân hàng ở tài khoản `bank_ref_stable` (mã khác là giao dịch khác). Mỗi nhóm dòng `new` (ngày, chiều, số tiền, có mã hay không) có F dòng và E giao dịch U ghép được: F ≤ E → dòng thứ k (theo `line_no`) là `suspect` với ứng viên mềm là giao dịch thứ k (theo `id`); F > E → mọi dòng của nhóm là `suspect`, `candidate` để trống, `soft_candidates` liệt kê cả E giao dịch (không gán theo thứ tự). Giao dịch U không là ứng viên mềm của dòng nào → mỗi giao dịch một chỗ gãy `UNMATCHED_EXISTING` (`transaction_id`, ngày, chiều, số tiền).
5. **Số dư:** số dư đầu kỳ vọng = số dư mở + Σ giao dịch chưa hủy có ngày ghi sổ < `period_from`. File có số dư đầu mà khác → gãy `OPENING_MISMATCH`. Mọi dòng hợp lệ có số dư sau → đi theo `line_no` từ số dư đầu (của file, không có thì kỳ vọng): lệch → gãy `RUNNING_BALANCE` ở dòng đó. File có số dư cuối: số dư đầu + Σ mọi dòng hợp lệ ≠ cuối → gãy `CLOSING_MISMATCH`.
6. `preview_hash` = SHA-256 của JSON chuẩn gồm lớp + ứng viên + ứng viên mềm từng dòng, các chỗ gãy (kể cả U còn lại), toàn bộ U và `financial_account.version`.

`commit_import` chạy lại 1–6 trên dòng gốc đã lưu; version tài khoản khác lúc xem trước hoặc băm khác `expected_preview_hash` → `IMPORT_PREVIEW_STALE`; `period_to` sau hôm nay → `INVALID_COMMAND`. Gãy số dư (`OPENING_MISMATCH`, `RUNNING_BALANCE`, `CLOSING_MISMATCH`) → `BALANCE_CHAIN_BROKEN`, DETAIL liệt kê mã. Quyết định cho dòng `suspect` (`suspect_decisions`): `new`, hoặc `duplicate_of` một giao dịch chưa hủy, cùng tài khoản, cùng ngày ghi sổ, chiều, số tiền với dòng, không là ứng viên của dòng `duplicate` khác và không là đích của quyết định khác trong lô (không xét mô tả); sai → `DUPLICATE_TARGET_INVALID`. MỌI giao dịch của U (kể cả giao dịch đang là ứng viên mềm của một dòng `suspect`) phải là đích `duplicate_of` hoặc có trong `keep_existing` (id thuộc U và không là đích `duplicate_of`, sai → `INVALID_COMMAND`; lý do không rỗng, thiếu → `REASON_REQUIRED`); còn sót → `BALANCE_CHAIN_BROKEN` với DETAIL `UNMATCHED_EXISTING`. Vì vậy quyết `new` cho dòng nghi trùng mềm buộc người quyết ghi rõ vì sao giữ giao dịch cũ. Dòng `new` tạo giao dịch + nguồn `origin` (mã giao dịch cấp theo thứ tự dòng); dòng `duplicate` tạo nguồn `duplicate_confirmed` trỏ ứng viên; giao dịch giữ không có nguồn mới, chỉ vào event.

## Phân bổ

Đích lát 1: `ar_book`, `customer_unapplied` (cả hai cần `target_ref.customer_id` là chuỗi số nguyên dương; chưa nối `sokhach`), `internal_transfer` (`target_ref.transaction_id` của giao dịch ngược chiều ở tài khoản khác cùng pháp nhân), `internal_transfer_pending`, `cash_withdrawal`, `bank_fee`, `interest`, `customer_funds_pending`, `fleet`, `expense_category` (`target_ref.category` không rỗng), `other`. Σ dòng ≤ số tiền giao dịch; mỗi dòng > 0; bỏ hay đổi bất kỳ dòng đang hiệu lực nào → `reason` bắt buộc; bộ mới y hệt bộ cũ → trả kết quả, không ghi. Trạng thái suy ra: vào `unidentified`/`unapplied`/`partial`/`applied`, ra `unmatched`/`partial`/`matched` (F1 §4).

## Bất biến (kiểm cuối mỗi lệnh và trong harness)

I-1 số dư = mở + vào − ra của giao dịch chưa hủy · I-2 không commit khi gãy chuỗi · I-4 Σ phân bổ hiệu lực ≤ số tiền · I-5 mỗi dòng phân bổ truy được event tạo/thay · I-6 mỗi giao dịch chưa hủy có ≥ 1 nguồn ở lô chưa hủy, mỗi dòng gốc là nguồn của nhiều nhất một giao dịch · I-7 bảng chỉ thêm · I-8 giao dịch, phân bổ cùng tài khoản và tiền tệ · I-10 khóa lặp.

## Tiêu chí nghiệm thu (harness `tools/test_pg_tien.py`)

- [ ] Migration chạy hai lần trên DB trống không lỗi (lần hai báo đã có hoặc không đổi gì, như harness Đội xe).
- [ ] AT-02.1 `tien_app` không INSERT/UPDATE/DELETE trực tiếp được bảng nào; owner UPDATE/DELETE bảng chỉ thêm bị trigger chặn.
- [ ] AT-02.2 hủy lô không lý do; hủy lô có giao dịch đang phân bổ → bị từ chối.
- [ ] AT-02.3 lô A commit, lô B chồng kỳ xác nhận trùng; hủy A → giao dịch còn, số dư không đổi.
- [ ] AT-03.1 cùng file hai lần → lô cũ, 0 giao dịch mới.
- [ ] AT-03.2 kỳ 1–15 rồi 10–31 → chỉ 16–31 mới; số dư cuối đúng.
- [ ] AT-03.3 hai giao dịch giống hệt trong một file → hai giao dịch.
- [ ] AT-03.4 vùng chồng kỳ có thêm một dòng cùng dấu vân → `suspect`; commit thiếu quyết định → `IMPORT_SUSPECT_UNRESOLVED`; quyết định `new` → thêm một giao dịch.
- [ ] AT-03.5 hai lô chồng kỳ xem trước trước, commit lần lượt → lô sau `IMPORT_PREVIEW_STALE`, không ghi trùng.
- [ ] AT-03.6 cùng khóa khác nội dung → `IDEMPOTENCY_CONFLICT`; cùng khóa cùng nội dung → kết quả cũ.
- [ ] AT-05.1 vượt số tiền → `OVER_ALLOCATION`; AT-05.2 sai `expected_version` → `STALE_VERSION`; AT-05.4 bỏ dòng không lý do → `REASON_REQUIRED`; AT-05.5 ví dụ 350/100/50 (số bịa) → `partial`.
- [ ] AT-06.x / AT-08.2 người có vai ở pháp nhân A gọi lệnh trên tài khoản pháp nhân B → `ENTITY_SCOPE`; không có vai → `TIEN_FORBIDDEN`; cấp vai cho chính mình → `SELF_GRANT`.
- [ ] AT-12.1/12.2 dòng ngày tương lai, ngoài kỳ → lớp `error`; commit → `IMPORT_HAS_ERRORS`. Gãy chuỗi số dư → commit `BALANCE_CHAIN_BROKEN`.
- [ ] Đồng thời: hai phiên cùng commit một lô → đúng một lần ghi (khuôn kiểm chặn của `pg_v7_harness`).
- [ ] Sau review độc lập 24/11/2026: lô 1 có "CK ABC" ngày 12, lô 2 kỳ 10–20 có cùng giao dịch mô tả "CK ABC FT123" → dòng `suspect` (ứng viên mềm); commit không quyết định → `IMPORT_SUSPECT_UNRESOLVED`; người review quyết `duplicate_of` đúng giao dịch → commit, số dư bằng số dư cuối ngân hàng (không ghi hai lần).
- [ ] File thiếu một giao dịch đã có trong kỳ → `UNMATCHED_EXISTING`; commit không xử lý → `BALANCE_CHAIN_BROKEN`; `keep_existing` thiếu lý do → `REASON_REQUIRED`; có lý do (vai review) → commit.
- [ ] `duplicate_of` hợp lệ commit được; đích khác số tiền, khác ngày, đã hủy, đã bị dòng khác nhận → `DUPLICATE_TARGET_INVALID`.
- [ ] Người chỉ có `tien_nhap` gửi `suspect_decisions`/`keep_existing` → `TIEN_FORBIDDEN` (có vai review ở pháp nhân khác → `ENTITY_SCOPE`); người chỉ có `tien_review` commit lô có quyết định → thành công; lô không có quyết định mà chỉ có `tien_review` → `TIEN_FORBIDDEN`.
- [ ] Review lượt 2 — D2: dòng nghi trùng mềm quyết `new`, không `keep_existing` → `BALANCE_CHAIN_BROKEN` (`UNMATCHED_EXISTING`); giữ có lý do → commit, sổ có cả giao dịch cũ và mới.
- [ ] D3: hai dòng cùng ngày/chiều/số tiền, U chỉ có một giao dịch → cả hai `suspect`, không gán theo thứ tự; quyết đúng → số dư sổ cuối ngày bằng ngân hàng.
- [ ] R2: tài khoản mã ổn định, mã cũ đã có, file chỉ có mã khác cùng ngày/số tiền → dòng `new`, giao dịch mã cũ thành `UNMATCHED_EXISTING`.
- [ ] Review lượt 3 — R3: tài khoản mã ổn định, ngân hàng dùng lại mã cũ cho giao dịch khác ngày và số tiền (giao dịch cũ nằm ngoài kỳ) → dòng `new`, không gãy, commit tạo giao dịch, số dư sổ = số dư cuối file.
- [ ] `create_account` có `bank_ref_stable` mà không mẫu file → `INVALID_COMMAND`; nhiều dòng cùng mã ngân hàng trong một lô ghép đúng từng giao dịch.
- [ ] Phiên gọi đặt `standard_conforming_strings = off` → dấu vân không đổi, dòng trùng vẫn `duplicate`.
- [ ] `period_to` là ngày mai → `INVALID_COMMAND`.
- [ ] Hủy lô khi giao dịch còn nguồn ở lô khác và đang có phân bổ → hủy được, giao dịch và phân bổ còn nguyên.
- [ ] Hoàn tác khi mới chỉ có tài khoản + số dư mở → `TIEN_HAS_DATA`.
- [ ] Mọi event có `before`/`after` là object; mỗi lệnh ghi đúng số event mong đợi.
- [ ] `npm run check` xanh; `node scripts/check-secrets.js` sạch; harness chạy ở máy và có bước trong `.github/workflows/test.yml`.

## Phạm vi agent

- Agent: claude ([`CLAUDE-ALL-01`](../docs/decisions/claude-all-01.md)). Review: opus (ghi tiền).
- Được sửa: `cong-no-web-handoff/tools/migrations/2026-11-24-tien-p0a-lat1.sql`, `cong-no-web-handoff/tools/migrations/2026-11-24-tien-p0a-lat1.rollback.sql`, `cong-no-web-handoff/tools/test_pg_tien.py`, `.github/workflows/test.yml` (thêm đúng một bước chạy harness), `cong-no-web-handoff/tools/test_pg_v7_backend.py` (thêm file migration vào `outside_chain` của `--migration-test`), `docs/development.md` (một dòng cho `test_pg_tien.py` ở bảng harness), file này (mục Hàm lệnh, Phân loại dòng, Tiêu chí, danh sách này, Bằng chứng, Câu hỏi mở — sửa theo review độc lập 24/11/2026).
- Ngân sách: khoảng 1.600 dòng (SQL ~900, harness ~600).
- Lệnh kiểm: `D:/webdebit/repo/.venv/Scripts/python.exe cong-no-web-handoff/tools/test_pg_tien.py`; `test_pg_v7_backend.py --migration-test`; `npm run check` (đặt `WEBDEBIT_PYTHON`, `VIRTUAL_ENV`, PATH tới `.venv` như ghi chú worktree); `node scripts/check-secrets.js`.
- Cấm: đụng schema/role/hàm `sokhach`, `doixe`; API, giao diện; ssh, `hao`, mạng; dữ liệu thật; thêm thư viện; merge; chạy migration ngoài DB dùng một lần của harness.

## Hoàn tác

Lát 1 chưa triển khai: đóng PR. Khi đã triển khai mà chưa có dữ liệu thật: chạy file `.rollback.sql` (xóa schema `tien` và ba role) theo runbook có sao lưu trước. Có dữ liệu thật thì không xóa; tắt cờ.

## Bằng chứng

ĐÃ KIỂM CHỨNG ở máy Windows (Docker Desktop, PostgreSQL 18.6 dùng một lần, `--network none`), 24/11/2026, nhánh `claude/so-tien-p0a`. Chưa chạy trên `hao`. Lượt sau review độc lập lượt 3 (cùng ngày):

- `D:/webdebit/repo/.venv/Scripts/python.exe cong-no-web-handoff/tools/test_pg_tien.py` → thoát 0, `"result": "pass"`, `"cleanup": "verified_and_removed"`, 29 nhóm ca, 32,1 giây (lượt cuối; lượt 3 thêm R3, lượt 2 thêm D2, D3, R2 và người chỉ có `tien_review` commit lô có quyết định). Mỗi ô của mục Tiêu chí nghiệm thu có nhóm ca riêng trong báo cáo JSON (`--report <file>.json`): migration lỗi giữa chừng quay lại hết, chạy hai lần, hoàn tác rồi chạy lại; AT-02.1 (thử thật INSERT/UPDATE/DELETE/SELECT/TRUNCATE bằng login thành viên `tien_app`/`tien_reader`, UPDATE/DELETE/TRUNCATE bằng chủ schema); AT-02.2, 02.3; AT-03.1–03.6; AT-05.1, 05.2, 05.4, 05.5; AT-06.x/AT-08.2; AT-12.1/12.2 và `BALANCE_CHAIN_BROKEN`; hai phiên commit cùng lô (phiên sau chờ khóa tài khoản, thấy qua `pg_blocking_pids`); các ca sau review (mô tả đổi, `UNMATCHED_EXISTING` + `keep_existing`, đích `duplicate_of`, vai review cho quyết định, mẫu file cho mã ổn định, nhiều dòng cùng mã, `standard_conforming_strings = off`, `period_to` ngày mai, hủy lô khi giao dịch còn nguồn khác và có phân bổ, hoàn tác khi chỉ có tài khoản + số dư mở); số event và khóa lặp của từng lệnh; I-1, I-4, I-5, I-6, I-8, I-10 tính thẳng từ bảng; catalog `sokhach` không đổi.
- Thử phá có chủ ý: bỏ `FOR NO KEY UPDATE` trong `_lock_account` → harness đỏ ở nhóm ca hai phiên commit cùng lô; đưa lại `\s` vào biểu thức chuẩn hóa mô tả → harness đỏ đúng ở ca `standard_conforming_strings = off` (ba dòng thành `suspect` thay vì `duplicate`); đưa bước 3 về bản ghép chỉ theo mã → harness đỏ đúng ở ca R3 (dòng thành `duplicate` của giao dịch mã cũ ngoài kỳ, không chỗ gãy nào). Khôi phục rồi chạy lại xanh.
- `D:/webdebit/repo/.venv/Scripts/python.exe cong-no-web-handoff/tools/test_pg_v7_backend.py --migration-test` → thoát 0, `"migration": "pass"`, SCHEMA 10/10, BEHAVIOR 77/77, 2 mục `SKIPPED_OPEN` có sẵn (7.11c, 7.15c), `"cleanup": "verified_and_removed"`.
- `npm run check` (đặt `WEBDEBIT_PYTHON`, `VIRTUAL_ENV`, PATH tới `.venv`) → thoát 0, 9/9 bước OK, không bước nào SKIP, không dòng `CHƯA ĐỦ`; unittest 2027 ca OK (19 ca tự bỏ sẵn có trong bộ), `node --test` 343/343, Playwright 565/565.
- `node scripts/check-secrets.js --all` → `sạch (toàn bộ file đã theo dõi)`, danh sách tên khách 318 tên. Lệnh này chỉ quét file Git đã theo dõi: ba file mới và file spec này chưa stage nên chưa nằm trong lượt quét; trước commit chạy `node scripts/check-secrets.js` trên diff đã stage. Đã soát tay các file: không số tiền nhóm chấm, số container, tên khách hay khóa bí mật.
- CI: thêm bước `So tien P0-a lat 1 on isolated PostgreSQL` vào job `postgres-doixe` của `.github/workflows/test.yml`, cùng cách gọi `uv run --python 3.14 python cong-no-web-handoff/tools/test_pg_tien.py`.

## Câu hỏi mở

Chỗ spec chưa nói rõ, agent đã chọn khi làm lát 1 (ĐỀ XUẤT, reviewer xác nhận hoặc sửa):

- **Ghép mềm (bước 4b, sửa sau review lượt 1 và 2):** ở tài khoản `bank_ref_stable`, dòng có mã không ghép mềm với giao dịch có mã (giao dịch đó vào `UNMATCHED_EXISTING` nếu file không có); dòng không mã vẫn ghép với mọi giao dịch cùng ngày/chiều/số tiền. Nhóm dòng chia theo (ngày, chiều, số tiền, có mã hay không) nên khi một ngày có cả dòng có mã lẫn dòng không mã cùng số tiền, ứng viên mềm của hai nhóm có thể trùng nhau — chỉ là gợi ý; quyết định trỏ cùng giao dịch hai lần bị `DUPLICATE_TARGET_INVALID`. Dòng `suspect` thừa của bước 4 không có ứng viên mềm nhưng vẫn được `duplicate_of` một giao dịch của U nếu cùng ngày, chiều, số tiền. Ứng viên mềm của dòng khác chỉ bị khóa khi dòng đó quyết `duplicate_of` nó. `keep_existing` cố ý để số dư sổ tiền khác số dư cuối của file (người review giữ giao dịch file không có), lý do vào event. Khóa payload đổi từ `decisions` thành `suspect_decisions`.
- **Mã lỗi:** chỉ dùng mã của spec. Đối tượng không có (tài khoản, lô, giao dịch, vai), chuyển trạng thái sai (bỏ lô không còn `validated`, hủy lô chưa `committed`, thu vai đã thu) và mã pháp nhân trùng → `INVALID_COMMAND`; commit lô không còn `validated` → `IMPORT_PREVIEW_STALE`.
- **Event và khóa lặp:** thêm loại event `entity_create` (F1 mục 9 chưa có) cho `create_legal_entity`, khóa lặp của lệnh này dùng phạm vi `global`. Băm nội dung bỏ `idempotency_key` và `expected_version` (F1 mục 8): gửi lại cùng khóa sau khi không rõ kết quả, kể cả với version mới, trả kết quả cũ. Lệnh không đổi gì (bộ phân bổ y hệt, cấp lại vai đang có, cùng file đã commit) không ghi event, không tăng version, vẫn lưu khóa lặp.
- **Lỗi dòng và lỗi lệnh:** chỉ bảy mã của spec là lỗi dòng, xét theo thứ tự `LINE_DUPLICATE_NO` → `LINE_FUTURE_DATE` → `LINE_OUT_OF_PERIOD` → `LINE_BEFORE_OPENING` → `LINE_DIRECTION` → `LINE_AMOUNT` → `LINE_CURRENCY` (mã đầu tiên thắng; mọi dòng cùng `line_no` đều lỗi). Sai cấu trúc StatementLine v1 (thiếu khóa, khóa lạ, `line_no` không nguyên dương, ngày không phải `YYYY-MM-DD` hợp lệ, số tiền là số JSON, `balance_after_minor` sai dạng, ô `cells` không phải chữ) → từ chối cả lệnh `INVALID_COMMAND`.
- **Số dư sau:** đi liền từ số dư đầu, không đặt lại sau chỗ lệch, nên một dòng thiếu làm mọi dòng sau có số dư sau cũng báo `RUNNING_BALANCE`.
- **Mã ngân hàng ổn định (bước 3):** nhiều dòng cùng (mã, ngày, chiều, số tiền) ghép lần lượt với giao dịch thứ k như bước 4; dòng thừa là `new` (không `suspect`), rồi qua bước 4b (chỉ ghép mềm với giao dịch không mã). Giao dịch đã là ứng viên theo mã không được tính lại ở bước 4 để một lô không có hai dòng trỏ cùng giao dịch (BR-IM6). Khóa ghép gồm cả ngày, chiều, số tiền nên ngân hàng đổi thứ tự các dòng cùng mã giữa hai lần tải chỉ có thể gắn chéo nguồn giữa các dòng giống hệt nhau (số tiền sổ không đổi), còn ngân hàng dùng lại mã cho giao dịch khác thì dòng là `new` (review lượt 3) — vẫn cần xác nhận ở Discovery mã có duy nhất cho mỗi giao dịch không.
- **Dấu vân:** chữ thường theo `COLLATE pg_c_utf8` (bảng Unicode dựng sẵn của PostgreSQL 17+, không theo locale máy) để dấu vân không đổi khi khôi phục sang máy khác; cần DB mã UTF8 và PostgreSQL ≥ 17 trên `hao` (đang là 18).
- **Phân bổ chuyển nội bộ:** chân kia ở pháp nhân khác → `ENTITY_SCOPE` (ADR-TIEN-06); cùng tài khoản, cùng chiều, đã hủy, không có → `INVALID_COMMAND`. Chưa kiểm tiền tệ chân kia, chưa đòi người phân bổ có vai ở tài khoản chân kia, hủy lô của chân kia sau đó không bị chặn (lát 1 chưa giữ hai chân nhất quán). Đích không có trường riêng (`bank_fee`, `fleet`, `other`…) chỉ nhận `target_ref` rỗng; mỗi dòng có thể kèm `note`.
- **Hàm đọc:** theo spec, mọi vai ở cùng phạm vi đều đọc được, kể cả `tien_quan_tri` (F1 mục 7 ghi quản trị không có quyền xem). Hàm đọc vẫn kiểm vai của `tien.actor`, nên máy canh (login `tien_reader`) cần một vai `tien_xem` cho người làm máy, trái câu "tài khoản máy không có vai nào" của E mục 3 — cần chốt trước lát máy canh. Giao dịch đã hủy vẫn hiện trong danh sách với trạng thái `voided`.
- **Tài khoản và số dư mở:** `statement_template` chỉ bắt buộc khi `bank_ref_stable` (sửa sau review: mã ngân hàng chỉ là khóa trong đúng một họ nguồn); có thì mẫu của lô phải trùng đúng (BR-IM2), đổi phiên bản mẫu sẽ cần lệnh sửa tài khoản (lát sau). `as_of` là số dư đầu ngày đó, không sau hôm nay; chưa ép ngày 1 của tháng (QD-10) trong SQL. `revoke_role` nhận lý do tùy chọn; thu vai của chính mình cũng `SELF_GRANT`.
- **Chưa làm ở lát 1 dù F1 có:** cột đối tác (HMAC, 4 số cuối), `role_overlap`, `evidence`/`rule_id` của phân bổ, trạng thái lô `draft` và `statement_file`.
- **Hoàn tác (sửa sau review):** file `.rollback.sql` tự dừng (`TIEN_HAS_DATA`) khi đã có bất kỳ tài khoản nào; chỉ còn pháp nhân và cấp vai khởi tạo thì được xóa.
- **CI:** điều phối đã thêm file migration vào `outside_chain` của `test_pg_v7_backend.py --migration-test` (schema riêng, không nâng theo chuỗi `sokhach`).
- **Ngân sách dòng:** SQL khoảng 1.330 dòng, harness khoảng 920 dòng, vượt mức ước 1.600 vì kiểm hình dạng payload, bất biến cuối lệnh, bước 4b và số ca nghiệm thu.
