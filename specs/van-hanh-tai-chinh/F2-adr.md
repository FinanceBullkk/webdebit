# F2. Architecture Decision Records

Trạng thái: **ĐỀ XUẤT** (Claude, 24/11/2026). Không ADR nào đã chốt. Khi chốt, mỗi ADR thành `docs/decisions/tien-<số>.md` theo [sổ quyết định](../../docs/decisions.md). `schema:` = `cong-no-web-handoff/schema/v7_schema_current.pgsql` trên `main` tại `3c75c094`. Tham chiếu ngành chi tiết ở [R](R-nghien-cuu-tham-chieu.md).

[← Mục lục](README.md) · Kiến trúc: [F1](F1-kien-truc-ky-thuat.md) · Test của từng `AT-xx.y`: [G §3](G-uat-test.md#3-kế-hoạch-test-tự-động)

| ADR | Chủ đề | Người chốt |
| --- | --- | --- |
| 01 | Ranh giới sổ, nguồn sự thật | Chủ DN, kế toán |
| 02 | Lịch sử nguồn bất biến | Kỹ thuật |
| 03 | Chống trùng hai tầng | Kỹ thuật |
| 04 | Ba lớp kiểm tra độc lập | Kế toán |
| 05 | Phân bổ là bảng liên kết duy nhất | Kỹ thuật, kế toán |
| 06 | Pháp nhân và nguyên tệ | Chủ DN, kế toán |
| 07 | Trạng thái tách trục | Kỹ thuật |
| 08 | Phân quyền, maker–checker, kiểm soát bù | Chủ DN |
| 09 | Tương thích sổ nợ, một nguồn ghi | Chủ DN, kỹ thuật |
| 10 | Luật ghép A/B/C; AI/OCR không là nguồn tiền | Kế toán, chủ DN |
| 11 | Schema riêng, cùng DB, login riêng | Kỹ thuật |
| 12 | Ngày, cutoff, độ phủ | Kế toán |
| 13 | Không kết nối ngân hàng và kiểm soát bù | Chủ DN (đã xác nhận ràng buộc) |
| 14 | Báo thu dùng lại "khách báo đã chuyển" | Chủ DN |
| 15 | Kiểm soát chi theo phiên bản | Chủ DN |
| 16 | Số dư xác nhận và số dư ước tính | Chủ DN, kế toán |
| 17 | Bộ đọc Excel an toàn | Kỹ thuật, kế toán |
| 18 | Chia P0 thành ba bước có cổng | Chủ DN |

---

## ADR-TIEN-01 — Ranh giới sổ và nguồn sự thật

**Bối cảnh.** Sổ nợ chính thức vẫn là Google Sheet; web `sokhach` chạy song song, máy ghi phiếu theo Sheet ([`SONG-SONG-01`](../../docs/decisions/song-song-01.md), [`CHUYEN-HAN-01`](../../docs/decisions/chuyen-han-01.md), [`MAY-DOI-SOAT-01`](../../docs/decisions/may-doi-soat-01.md)). Repo không có sổ cái kép. v3 §2 nêu nguồn có thẩm quyền theo từng câu hỏi.

**Quyết định.** Mỗi câu hỏi một nguồn:

| Câu hỏi | Nguồn |
| --- | --- |
| Tiền ngân hàng đã đi/về? | `tien.bank_transaction` từ sao kê đã nhập, có coverage |
| Tiền mặt? | Sổ quỹ + kiểm quỹ (P1) |
| Vì sao có khoản tiền? | Hồ sơ nghiệp vụ (sổ nợ, Đội xe, đề nghị chi, chứng từ) |
| Ai được chi? | Phiên bản đề nghị đã duyệt trước giao dịch |
| Khách còn nợ? | Sổ nợ hiện có (Sheet → `sokhach`) |
| Sổ cái pháp định? | Phần mềm kế toán (QD-09); sổ tiền xuất CSV để đối chiếu |

Sổ tiền là **sổ chi tiết quản trị**; không lưu dư nợ khách; không lập bút toán ở P0.

**Lý do, tham chiếu.** Thông lệ ERP tách sao kê/đối soát ngân hàng khỏi sổ phụ phải thu/phải trả và sổ cái; Odoo giữ giao dịch ở tài khoản treo tới khi đối soát (R §2). Tránh hai sổ cái chính thức (v3 §7).

**Đánh đổi.** + Không đụng sổ nợ, kế toán giữ định khoản. − Lãi lỗ, định khoản chờ sau; đối chiếu với phần mềm kế toán là việc tay theo kỳ.

**Kiểm nghiệm.** AT-01.1 sau mọi lệnh `tien` ở P0-a/P0-b, dấu vân bảng và tổng từng khách của `sokhach` không đổi. AT-01.2 không hàm `tien` nào có quyền ghi `sokhach`. AT-01.3 bản xuất CSV một kỳ cộng đúng chênh số dư đầu/cuối.

## ADR-TIEN-02 — Lịch sử nguồn bất biến

**Bối cảnh.** `sokhach` dùng trigger `reject_immutable_change` cho 12 bảng (ví dụ `schema:337`, `schema:392`), event có `before`/`after` bắt buộc (`schema:278-343`). v3 §4.1 yêu cầu lưu file/dòng gốc, hash, phiên bản bộ đọc.

**Quyết định.** File, lô, dòng gốc, giao dịch, phiên bản đề nghị, event chỉ thêm; cột trạng thái chỉ đổi qua hàm lệnh sau khi ghi event. Sửa sai bằng hủy lô có lý do hoặc giao dịch đảo của ngân hàng. Giao dịch còn hiệu lực khi còn ít nhất một dòng nguồn ở lô chưa hủy; hủy lô bị chặn nếu làm mất giao dịch đang có phân bổ hoặc thuộc ngày đã ký (sửa sau review). SHA-256 chỉ chứng minh file không đổi **sau** khi nhận.

**Tham chiếu.** Oracle xử lý lỗi ngân hàng bằng đảo/điều chỉnh; Microsoft: đối soát đã đánh dấu xong không hoàn tác (R §2).

**Đánh đổi.** + Truy vết tới dòng gốc. − Sửa lỗi nhập phải hủy lô → bù bằng xem trước bắt buộc.

**Kiểm nghiệm.** AT-02.1 UPDATE/DELETE trực tiếp bị từ chối. AT-02.2 hủy lô không lý do, hoặc làm mất giao dịch đã phân bổ, bị từ chối. AT-02.3 hủy lô A khi lô B đã xác nhận trùng các dòng của A: giao dịch vẫn còn (nguồn B). AT-02.4 file lấy lại có SHA-256 như lúc nhận.

## ADR-TIEN-03 — Chống trùng hai tầng

**Bối cảnh.** `sokhach.idempotency` khóa (sổ, khóa) + SHA-256 nội dung (`schema:1116-1142`). Mẫu VCB chưa khảo sát. SAO-KE-01 đề xuất băm có thứ tự dòng (`specs/sao-ke-ngan-hang.md:134`) — file chồng kỳ sẽ ghi hai lần.

**Quyết định.**
- **Lệnh:** `idempotency(scope, key, request_hash, result)`, scope = tài khoản hoặc đề nghị.
- **File:** (tài khoản, SHA-256) đã commit → trả lô cũ.
- **Mã ngân hàng:** chỉ làm khóa duy nhất khi Discovery chứng minh ổn định qua các lần tải.
- **Dấu vân:** (tài khoản, ngày ghi sổ, chiều, số tiền, mô tả chuẩn hóa), **không** gồm số dư sau (thứ tự cùng ngày làm số dư sau đổi) — chỉ để tìm ứng viên; trong vùng chồng kỳ so bội số; dòng không ghép được thành nghi trùng; không bao giờ tự bỏ.
- **Commit:** dưới khóa tài khoản, phân loại lại; version tài khoản đổi từ lúc xem trước → `IMPORT_PREVIEW_STALE`; đích "trùng của X" phải hợp lệ và không bị hai dòng trỏ (sửa sau review).

**Tham chiếu.** Microsoft từ chối sao kê trùng (cùng tài khoản, mã sao kê, ngày) và kiểm số dư đầu bằng số dư cuối kỳ trước; ISO 20022 camt.053 có tham chiếu entry của ngân hàng (R §2).

**Đánh đổi.** + Không tiền giả, không mất giao dịch thật. − Có hàng chờ nghi trùng cần người.

**Kiểm nghiệm.** AT-03.1 cùng file hai lần → 0 giao dịch mới. AT-03.2 kỳ 1–15 rồi 10–31 → chỉ 16–31 mới. AT-03.3 hai giao dịch thật giống hệt trong một file → hai giao dịch. AT-03.4 bội số lệch → nghi trùng. AT-03.5 hai lô chồng kỳ xem trước song song rồi commit lần lượt → lô sau bị `IMPORT_PREVIEW_STALE`, không ghi trùng. AT-03.6 cùng khóa khác nội dung → `IDEMPOTENCY_CONFLICT`.

## ADR-TIEN-04 — Ba lớp kiểm tra độc lập

**Bối cảnh.** v3 §4.3: coverage & số dư; đối soát ngân hàng (ghép với hồ sơ); phân bổ nghiệp vụ & ghi nhận. Ở `sokhach`, phiếu thu vừa là chứng từ thu vừa tự phân bổ (`schema:5705-5780`).

**Quyết định.** (1) **Coverage + số dư** theo tài khoản/ngày → chữ ký coverage. (2) **Ghép** giao dịch với báo thu, báo thực hiện, hồ sơ → gợi ý, xác nhận. (3) **Phân bổ + ghi nhận** → dòng phân bổ; ghi phiếu sổ nợ chỉ ở P0-c sau QD-16; không bút toán ở P0. Một tài khoản có thể "khớp số dư" mà còn giao dịch chưa rõ — hai chữ ký riêng.

**Tham chiếu.** Microsoft tách hành động khớp, tạo payment, tất toán, tạo voucher; Odoo giữ ở tài khoản treo tới khi đối soát (R §2).

**Kiểm nghiệm.** AT-04.1 ký coverage chỉ khi đủ điều kiện I-3. AT-04.2 phân bổ không đổi chữ ký coverage. AT-04.3 P0-a/P0-b không route nào ghi phiếu hay bút toán.

## ADR-TIEN-05 — Phân bổ là bảng liên kết duy nhất

**Bối cảnh.** v3 §7 liệt kê `ReconciliationGroup/Link` và `Allocation` riêng nhưng nói rõ đó là mô hình logic. Ví dụ v3 §5: +500tr = 350 cước + 100 tiền khách + 50 chưa rõ (số bịa).

**Quyết định.** Một bảng `allocation`: mỗi dòng gắn một phần tiền của giao dịch với **đích** (sổ nợ, đề nghị chi, nội bộ, phí, Đội xe, danh mục…) và **bằng chứng** (`contact_mark_id`, `payment_execution_id`). Trạng thái ghép của báo thu, đề nghị, báo thực hiện là **suy ra** (Σ dòng trỏ tới nó), không lưu nhóm riêng. Nhiều–nhiều; Σ ≤ số tiền, cùng tiền tệ; thay cả bộ tạo phiên bản; **mọi** lần bỏ/đổi dòng đang hiệu lực bắt buộc lý do (sửa sau review). Phí, chênh tỷ giá, xóa chênh chỉ qua dòng loại riêng.

**Lý do.** Bớt một tầng bảng mà vẫn đủ một–nhiều, nhiều–một, nhiều–nhiều; không có hai nơi nói "khoản này đã khớp" có thể lệch nhau.

**Tham chiếu.** Oracle hỗ trợ một–một, một–nhiều, nhiều–một, nhiều–nhiều; Microsoft đối soát 1:1, n:1, n:n (R §2).

**Đánh đổi.** + Đơn giản, một nguồn trạng thái. − Báo cáo "nhóm đối soát" phải tính khi đọc (khối lượng nhỏ, chấp nhận).

**Kiểm nghiệm.** AT-05.1 vượt số tiền → `OVER_ALLOCATION`. AT-05.2 hai người cùng sửa → một `STALE_VERSION`. AT-05.3 khác tiền tệ → `CURRENCY_MISMATCH`. AT-05.4 thay bộ làm mất một dòng mà không lý do → `REASON_REQUIRED`. AT-05.5 một đề nghị 50 khớp hai lệnh 20 + 30 → đề nghị `settled`.

## ADR-TIEN-06 — Pháp nhân và nguyên tệ

**Bối cảnh.** `sokhach` chỉ VND, không pháp nhân (`schema:173-185`, `schema:605-634`). Debit note chọn bên phát hành ở trình duyệt và mặc định tài khoản USD ([`TAI-KHOAN-COT-E-01`](../../docs/decisions/tai-khoan-cot-e-01.md)); sổ nợ chỉ ghi VND thực nhận ([`V7-CSM`](../../docs/decisions/v7-csm.md) (2)).

**Quyết định.** Mỗi tài khoản một pháp nhân, một tiền tệ, không đổi. Tiền `bigint` đơn vị nhỏ nhất + mã tiền tệ; tỷ giá (P1) `numeric` kèm nguồn, ngày. Tổng luôn nhóm theo (pháp nhân, tiền tệ). Phân bổ khác pháp nhân bị từ chối; ngoại lệ liên công ty mở bằng lệnh riêng (sửa sau review). Sổ nợ → pháp nhân qua `ar_book_entity` (QD-17). Tiền USD trả cước chờ chính sách kế toán (QD-18) trước khi ghi vào sổ nợ.

**Tham chiếu.** Microsoft: tiền giao dịch quy đổi riêng sang tiền hạch toán và tiền báo cáo; liên công ty dùng tài khoản due to/due from theo cặp pháp nhân (R §2, §4).

**Kiểm nghiệm.** AT-06.1 parser từ chối VND có phần lẻ, USD quá 2 chữ số lẻ. AT-06.2 phân bổ sang sổ của pháp nhân khác → `ENTITY_SCOPE`, và lệnh mở ngoại lệ sau đó thành công. AT-06.3 không báo cáo nào cộng VND với USD.

## ADR-TIEN-07 — Trạng thái tách trục

**Quyết định.** Máy trạng thái riêng cho: lô nhập; giao dịch vào (`unidentified/unapplied/partial/applied`, suy ra); giao dịch ra (`unmatched/partial/matched`, suy ra); đề nghị chi; báo thực hiện (`reported_sent/failed/returned`); ngoại lệ; ngày review (coverage và nghiệp vụ riêng). Không dùng một `completed` cho mọi thứ (v3 §5). Sơ đồ ở [F1 §4](F1-kien-truc-ky-thuat.md#4-trạng-thái).

**Tham chiếu.** Oracle phân biệt receipt chưa rõ khách, chưa áp, đã áp, on-account; Odoo hiện hóa đơn "In payment" tới khi khớp ngân hàng mới "Paid" (R §2, §3).

**Kiểm nghiệm.** AT-07.1 chuyển trái phép bị từ chối. AT-07.2 trạng thái suy ra đúng sau mỗi phân bổ, gỡ. AT-07.3 mỗi chuyển có đúng một event (kể cả `exception_assign`).

## ADR-TIEN-08 — Phân quyền, maker–checker, kiểm soát bù

**Bối cảnh.** [`QUYEN-01`](../../docs/decisions/quyen-01.md): vai chỉ chia màn, API mới mặc định mở, thiếu danh sách quản lý thì ai cũng quản lý (`web/v7_role.py:28-29`). [`QUYEN-02`](../../docs/decisions/quyen-02.md): quản lý được quản lý login. Một login DB `v7_app` cho người và máy. [`V6-DB`](../../docs/decisions/v6-db.md) bỏ người duyệt thứ hai ở sổ nợ. [`TU-LAM-01`](../../docs/decisions/tu-lam-01.md): agent tự nạp dữ liệu, đổi quyền. Lệnh của người đến từ 2 login (đo chỉ đọc 23/11/2026).

**Quyết định.**
1. Cổng `/api/v7/tien` **riêng**, đóng mặc định: kiểm vai sổ tiền ở `access_grant`; không suy từ vai quản lý; từ chối peer chỉ-đọc; module tắt khi chưa có vai nào (sửa sau review).
2. Bảy vai ([E §3](E-prd-p0.md#3-vai)), phạm vi theo pháp nhân/tài khoản; hàm SQL kiểm phạm vi.
3. **Maker–checker** cho chi: người duyệt ≠ người đề nghị, kiểm ở máy chủ — không phải cấu hình tùy chọn.
4. Khi thiếu người: cho trùng vai nhập/review có cờ `role_overlap` + tóm tắt tuần cho chủ doanh nghiệp + chủ doanh nghiệp tự tải sao kê đối chiếu định kỳ. Không cho tự duyệt, không cho người chuyển gỡ cờ chi chưa duyệt.
5. DB login `tien_api` riêng; agent vận hành không có quyền ghi dữ liệu `tien` (QD-06).

**Tham chiếu.** COSO đặt tách nhiệm vụ trong thành phần hoạt động kiểm soát và cho phép kiểm soát thay thế khi tách nhiệm vụ không khả thi; Microsoft cho cấu hình chặn người gửi tự duyệt (mặc định không chặn) (R §2).

**Đánh đổi.** + Kiểm soát đúng ở chỗ có rủi ro gian lận. − Khác tinh thần V6 (sổ nợ không duyệt hai người) → chủ doanh nghiệp phải chốt rõ phạm vi khác nhau.

**Kiểm nghiệm.** AT-08.1 login không vai → 403 trước khi đụng DB. AT-08.2 ID ngoài phạm vi → từ chối khi gọi thẳng hàm. AT-08.3 chưa có vai → route không mở. AT-08.4 tự duyệt → `SELF_APPROVAL`. AT-08.5 peer chỉ-đọc gọi GET `tien` → `READONLY_PEER`. AT-08.6 trùng vai nhập/review → ghi được nhưng có cờ và vào tóm tắt tuần. AT-08.7 log ứng dụng không chứa nội dung chuyển khoản, số tài khoản.

## ADR-TIEN-09 — Tương thích sổ nợ, một nguồn ghi

**Bối cảnh.** Phân bổ sổ nợ theo tháng, nợ cũ trước, tính lại khi có phiếu mới, điều chỉnh, sửa giá, đổi ngày phiếu; chỉ ghi lại phiếu có phân bổ đổi (`schema:5437-5536`, `schema:5508`). Máy hủy/ghi lại phiếu khi Sheet sửa ([`THAY-PHIEU-SHEET-01`](../../docs/decisions/thay-phieu-sheet-01.md)); phiếu sửa được ngày, hình thức, tham chiếu (`schema:3478`). `record_receipt` không có tham số tháng chỉ định.

**Quyết định.**
1. P0-a, P0-b không ghi `sokhach`; không migration `sokhach`.
2. Liên kết ở mức sổ (`ar_book`) và phiếu (`ar_receipt` = sổ + `pid`), không bao giờ trỏ `receipt_line`.
3. Liên kết phiếu kiểm lại khi phiếu bị hủy **hoặc** sửa (so dấu vân trạng thái phiếu); lệch → "cần xem lại" (sửa sau review).
4. P0-c shadow: đối chiếu chỉ đọc. Ghi phiếu chỉ khi QD-16 chọn phương án B: tắt máy ghi phiếu theo Sheet cho sổ đó cùng lúc; khóa lặp = băm(mã giao dịch, mã sổ); `reference` = mã giao dịch; dừng nếu đã có phiếu sống cùng `reference` (sửa sau review).
5. Chỉ định tháng là thay đổi động cơ sổ nợ (QD-19), không làm trong P0.

**Tham chiếu.** Microsoft tách "tạo payment" khỏi "tất toán hóa đơn"; v3 §3.1 "không ghi đồng thời vào Excel và web như hai nguồn".

**Kiểm nghiệm.** AT-09.1 như AT-01.1. AT-09.2 phiếu đã liên kết bị hủy hoặc sửa → "cần xem lại" ở lượt đọc sau. AT-09.3 ghi phiếu lặp sau sập giữa chừng → một phiếu. AT-09.4 bật ghi từ ngân hàng khi máy theo Sheet còn bật cho cùng sổ → `AR_POSTING_DISABLED`. AT-09.5 lưới an toàn hiện có xanh.

## ADR-TIEN-10 — Luật ghép A/B/C; AI/OCR không là nguồn tiền

**Bối cảnh.** Ghép chat hiện có là một–một theo số tiền ([A §4](A-audit-hien-trang.md#4-phần-khác-chạm-tiền)); đo 24/11/2026: 0/48 phiếu khớp, 45 biên lai bên thứ ba bị đếm là thu. [`ZALO-THU-CHI-01`](../../docs/decisions/zalo-thu-chi-01.md) Q2 và [`ANH-GEMINI-01`](../../docs/decisions/anh-gemini-01.md) cho đọc tin/ảnh tiền (chỉ đọc).

**Quyết định.** Mức A/B/C theo BR-MA1–3; luật có phiên bản; P0-a/P0-b chỉ gợi ý; tự áp mức A khi đo shadow đạt ngưỡng kế toán chốt (QD-21). AI/OCR không xác nhận tiền, không ghép, không ghi. Đề xuất **đóng băng** việc đọc tin/ảnh chat để tính tiền — sửa phạm vi ZALO-THU-CHI-01 Q2 và ANH-GEMINI-01, cần chủ doanh nghiệp chốt (QD-25).

**Tham chiếu.** Microsoft có tham số buộc khớp tay khi nhiều chứng từ cùng số tiền; Odoo cho mô hình đối soát tự xác nhận và dung sai — vendor cho phép tự động, P0 chủ ý chặt hơn (R §2).

**Kiểm nghiệm.** AT-10.1 P0-a/P0-b không đường nào đổi phân bổ từ luật. AT-10.2 gợi ý lưu luật + phiên bản. AT-10.3 hai ứng viên → không gợi ý mức A/B, ngoại lệ. AT-10.4 module không gọi mạng ra ngoài.

## ADR-TIEN-11 — Schema riêng, cùng DB, login riêng

**Quyết định.** Schema `tien` trong DB hiện có; owner `tien_owner`, role `tien_app` (chỉ EXECUTE), `tien_reader`; login `tien_api` cho API, `tien_reader` cho máy canh; hàm `SECURITY DEFINER` + `search_path` cố định như `sokhach` (`schema:5778-5780`); không khóa ngoại sang `sokhach`; thêm `tien` vào `EXTRA_SCHEMAS` của sao lưu (`tools/v7_backup.py:364-365`); snapshot schema trong CI.

**Đánh đổi.** + Một runbook, một bộ sao lưu. − Chung máy với sổ nợ; dữ liệu ngân hàng nằm trong bản sao lưu trên `hao` (hiện chưa mã hóa → QD-08).

**Kiểm nghiệm.** AT-11.1 `tien_api` không có quyền bảng `sokhach`; `v7_app` không có quyền ghi `tien`. AT-11.2 sao lưu → khôi phục có `tien`, số dư khớp. AT-11.3 snapshot schema khớp SQL nguồn.

## ADR-TIEN-12 — Ngày, cutoff, độ phủ

**Bối cảnh.** `sokhach` lấy "hôm nay" theo giờ VN (`schema:5723-5724`). v3 §4.2: cutoff 17h ví dụ; không suy giờ khi file chỉ có ngày; tải chồng kỳ; ngày thiếu không suy ra không phát sinh.

**Quyết định.** Ngày nghiệp vụ = ngày ghi sổ ngân hàng in (kiểu `date`, không đổi múi giờ); "hôm nay" để chặn ngày tương lai tính theo giờ VN. Mốc dữ liệu = mốc ngân hàng ghi trong file, nếu có; nếu không, chỉ ghi ngày. Ngày cuối mỗi file là chưa trọn trừ khi chứng minh được. **Độ phủ xác nhận bằng liên tục số dư** (số dư đầu file = số dư sổ ở điểm phủ trước), không chỉ bằng khoảng ngày (sửa sau review). Ngày thiếu được đánh dấu.

**Kiểm nghiệm.** AT-12.1 dòng ngày tương lai (giờ VN, kể cả máy chạy UTC) → lỗi dòng. AT-12.2 dòng ngoài kỳ khai báo → lỗi dòng. AT-12.3 file xuất giữa ngày rồi file bắt đầu từ ngày sau → gãy chuỗi, không ký coverage. AT-12.4 ngày không có file → `missing`.

## ADR-TIEN-13 — Không kết nối ngân hàng và kiểm soát bù

**Bối cảnh.** Chủ doanh nghiệp đã xác nhận: không API, webhook, RPA, dịch vụ đọc, không lưu mật khẩu/OTP, không chuyển tiền từ webdebit (v3 §1). File do người tải lên có thể bị sửa trước khi tải.

**Quyết định.** File Excel gốc là nguồn duy nhất của sổ tiền ngân hàng. Kiểm soát bù: (1) người review **khác** người nhập định kỳ tự tải sao kê (hoặc bản PDF ngân hàng) và nhập số dư cuối làm `balance_evidence`; (2) liên tục số dư bắt buộc; (3) cảnh báo file không phải bản gốc; (4) kiểm trực tiếp tại ngân hàng trước chi lớn là SOP, không phải chức năng web. Không đưa kết nối ngân hàng vào backlog.

**Tham chiếu.** Microsoft và Odoo đều hỗ trợ nhập file sao kê (định dạng chuẩn hoặc CSV) như một đường chính (R §2).

**Kiểm nghiệm.** AT-13.1 không có thư viện, cấu hình hay lời gọi mạng tới ngân hàng/dịch vụ đọc. AT-13.2 ký coverage cần bằng chứng số dư của người khác người nhập hoặc có cờ trùng vai.

## ADR-TIEN-14 — Báo thu dùng lại "khách báo đã chuyển"

**Bối cảnh.** `sokhach.contact_mark` loại `paid_claim` đã có: sổ, số tiền, ngày, ghi chú, tin Zalo, khóa lặp, hủy có lý do, không tính tiền (`schema:131-171`); nút có ở sổ khách. v3 §3.1 cần báo thu tùy chọn.

**Quyết định.** P0-c dùng `paid_claim` làm báo thu cho khách sổ nợ (VND); sổ tiền đọc qua hàm đọc sẵn có và ghi `contact_mark_id` vào `evidence` của dòng phân bổ. Không tạo bảng báo thu mới ở P0. Thêm trường (tiền tệ, tài khoản dự kiến, mục đích có cấu trúc) chỉ khi P1 cần (tiền khách, USD).

**Đánh đổi.** + Không thêm màn, không nhập hai lần. − Chỉ VND, ghi chú tự do cho mục đích.

**Kiểm nghiệm.** AT-14.1 báo thu không đổi số dư, không tạo phiếu. AT-14.2 báo thu hủy sau khi đã làm bằng chứng → gợi ý gỡ bằng chứng, không đổi tiền.

## ADR-TIEN-15 — Kiểm soát chi theo phiên bản

**Quyết định.** Đề nghị chi có phiên bản bất biến (snapshot số tiền, tiền tệ, người nhận, tài khoản thụ hưởng, tài khoản trả, mục đích, nghĩa vụ); duyệt gắn số phiên bản và hạn; sửa trọng yếu tạo phiên bản mới và mất duyệt; xác minh người nhận mới/đổi tài khoản; báo thực hiện nhiều lần, `failed`/`returned`; cam kết chi = đã duyệt chưa thực hiện. Báo thực hiện ≠ tiền: chỉ giao dịch ra trên sao kê mới đóng đề nghị. Duyệt bù được ghi rõ `is_retroactive`, không thành duyệt trước.

**Tham chiếu.** Microsoft: nhật ký thanh toán có thể duyệt tay hoặc theo workflow, có tùy chọn chặn người gửi tự duyệt; APQC xếp duyệt thanh toán trong quy trình phải trả (R §2).

**Kiểm nghiệm.** AT-15.1 sửa số tiền sau duyệt → phải duyệt lại. AT-15.2 báo thực hiện vượt số duyệt → `EXECUTION_EXCEEDS_APPROVED`. AT-15.3 giao dịch ra không có đề nghị → ngoại lệ, không tạo duyệt giả. AT-15.4 duyệt quá hạn → `APPROVAL_EXPIRED`.

## ADR-TIEN-16 — Số dư xác nhận và số dư ước tính

**Bối cảnh.** v3 §6: ước tính = số dư tại cutoff + thu đã báo − chi đã báo chưa vào sao kê; không chắc thì hiện riêng.

**Quyết định (chặt hơn v3).** Hiển thị ba dòng tách bạch: **số dư theo sao kê** (kèm cutoff); **ước tính thận trọng** = số dư theo sao kê − chi đã báo thực hiện sau cutoff chưa khớp; **có thể về** = thu đã báo chưa thấy tiền (không cộng vào ước tính). Cam kết chi hiện riêng. Khi giao dịch khớp, khoản đó rời phần ước tính trong cùng lệnh. Không dùng ước tính để cho phép chi.

**Lý do.** Báo thu có thể không về (v3 tự nêu); cộng vào làm số đẹp hơn thực tế — trái nguyên tắc thận trọng (QD-22).

**Kiểm nghiệm.** AT-16.1 ví dụ v3 §6 (số bịa): sao kê 2 tỷ, báo chi 500tr, báo thu 300tr → ước tính thận trọng 1,5 tỷ, "có thể về" 300tr; sau khi sao kê xác nhận cả hai, số dư 1,8 tỷ, không còn khoản nào trong ước tính. AT-16.2 không khoản nào bị trừ hai lần.

## ADR-TIEN-17 — Bộ đọc Excel an toàn

**Bối cảnh.** Repo đọc xlsx bằng `zipfile` + XML ở công cụ nạp Sheet (`tools/v7_load_real_copy.py`); không có bộ đọc `.xls` (BIFF); phụ thuộc runtime duy nhất là `tzdata`. Mở rồi lưu file bằng Excel làm đổi băm và có thể đổi định dạng số/ngày.

**Quyết định.** Một bộ đọc cho mỗi mẫu file đã khai (tên + phiên bản), từ chối file lạ. Giới hạn kích thước, số mục, dung lượng giải nén; từ chối DOCTYPE; đọc giá trị đã lưu, không tính công thức, bỏ liên kết ngoài. Nếu VCB chỉ xuất `.xls`: chọn ở QD-07 giữa (A) thêm một thư viện đọc `.xls` ghim phiên bản + băm, cô lập trong bộ đọc; (B) yêu cầu xuất CSV/xlsx nếu ngân hàng có; không chọn "mở và lưu lại bằng Excel".

**Kiểm nghiệm.** AT-17.1 file quá lớn, zip bom, XML có DOCTYPE → `IMPORT_UNSAFE_FILE`. AT-17.2 ô công thức → đọc giá trị lưu, không thực thi. AT-17.3 file khác mẫu → `IMPORT_PARSE_ERROR`, không đoán cột.

## ADR-TIEN-18 — Chia P0 thành ba bước có cổng

**Bối cảnh.** v3 §9 gom vào P0: nền nhập sao kê (phase 1), luồng cuối ngày gồm báo thu, đề nghị chi, duyệt, báo thực hiện, gợi ý, hàng đợi, review, dashboard (phase 2), và nối sổ nợ có ghi phiếu (phase 3).

**Quyết định.** P0-a sổ tiền nền **gồm cả** review cuối ngày, ngoại lệ, thẻ số dư (cần để vận hành nhập hằng ngày); P0-b kiểm soát chi; P0-c nối sổ nợ (báo thu chuyển vào đây vì gắn với sổ nợ). Mỗi bước có cổng riêng ([H](H-migration-rollout.md)). Thứ tự P0-b/P0-c có thể đảo nếu chủ doanh nghiệp coi rủi ro thu lớn hơn chi.

**Lý do.** Mỗi bước tự mang giá trị và tự lùi được; P0-c phụ thuộc quyết định chuyển hẳn khỏi Sheet, không nên chặn P0-a/P0-b.

**Kiểm nghiệm.** AT-18.1 tắt cờ P0-b/P0-c thì P0-a vẫn chạy đủ; tắt P0-a thì không route `tien` nào mở.
