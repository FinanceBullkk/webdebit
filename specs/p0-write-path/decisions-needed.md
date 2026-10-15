# Quyết định nghiệp vụ còn mở

Mỗi mục dưới đây đang **CÒN MỞ**; chủ quyết định là người dùng/chủ nghiệp vụ. Các đề xuất chỉ là gợi ý kỹ thuật-nghiệp vụ, chưa được áp dụng. Quy tắc đã chốt dẫn từ `docs/business-rules.md` / `docs/decisions.md` tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`. Không cần hỏi lại các nguyên tắc đã chốt ở cuối tài liệu.

## Q01 — Nguồn danh tính maker/checker

- **Đã chốt / nguồn:** Maker và checker khác nhau (D01, `docs/decisions.md`); chưa chốt danh tính vận hành.
- **Còn thiếu:** Principal chuẩn, tài khoản chia sẻ/ủy quyền, cấp và thu hồi quyền, tài khoản service.
- **Ví dụ giả:** nhân viên An dùng tài khoản dùng chung `ke_toan` tạo phiếu; không xác định được An hay Bình đã thao tác.
- **Lựa chọn / hệ quả:** (A) tài khoản cá nhân qua SSO + role được cấp có audit: quy trách nhiệm được nhưng cần vòng đời quyền; (B) DB login cá nhân: audit DB rõ nhưng kết nối ứng dụng cần quản lý; (C) tài khoản chia sẻ: vận hành đơn giản nhưng không xác định actor thật.
- **Đề xuất:** principal cá nhân xác thực tập trung, quyền maker/checker tách biệt và audit ánh xạ principal → DB/service identity.
- **Ảnh hưởng:** P0-02; kiểm DB role hiện tại không bị chặn, nhưng duyệt/auth người thật và implementation bị chặn.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ + chủ vận hành/auth; **CÒN MỞ**.

## Q02 — Approval bao phủ revision/nội dung nào

- **Đã chốt / nguồn:** Approval phải hợp lệ; maker khác checker (D01, `docs/business-rules.md`). Cách sửa sau submit chưa chốt.
- **Còn thiếu:** Các field/hash bao phủ, thời điểm đóng băng, sửa/withdraw/re-submit và hiệu lực approval cũ.
- **Ví dụ giả:** checker duyệt 100 VND cho kỳ 2026-01; maker đổi thành 101 hoặc đổi kỳ trước khi post.
- **Lựa chọn / hệ quả:** (A) mọi thay đổi tạo revision mới và duyệt lại: gắn duyệt với nội dung rõ nhưng thêm bước; (B) giữ duyệt nếu đổi field “không trọng yếu”: nhanh hơn nhưng cần danh sách field và nguy cơ bỏ sót; (C) cho phép sửa proposal đã duyệt: dễ thao tác nhưng làm sai audit nếu không có version.
- **Đề xuất:** revision bất biến; approval lưu revision/hash trên toàn field ảnh hưởng nghiệp vụ, source/evidence và allocation; thay đổi tạo revision mới, approval cũ không dùng được.
- **Ảnh hưởng:** P0-01, P0-02, P0-04, acceptance stale approval; **chặn triển khai guard/version**, không chặn task characterization schema hiện có.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ; **CÒN MỞ**.

## Q03 — Tiền dư/chưa phân bổ/ứng trước (D04)

- **Đã chốt / nguồn:** Receipt khác allocation; không tự biến pending thành balance (`docs/business-rules.md`).
- **Còn thiếu:** Cách ghi receipt còn dư sau khi phân bổ nợ đủ điều kiện.
- **Ví dụ giả:** receipt 100, nợ đủ điều kiện 60, còn 40.
- **Lựa chọn / hệ quả:** (A) giữ 40 là unapplied credit: phản ánh tiền nhận, cần báo cáo/hoàn; (B) từ chối receipt vượt nợ: đơn giản nhưng không phản ánh tiền đã nhận; (C) ghi ứng trước vào account riêng: semantics rõ nhưng cần chứng từ/ledger riêng.
- **Đề xuất:** chưa chọn; cần quyết định nghiệp vụ và báo cáo liên quan.
- **Ảnh hưởng:** P0-03, reconciliation, test allocation cap; có thể để sau khi test không ghi nhận policy tiền dư.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ/kế toán; **CÒN MỞ**.

## Q04 — Ngoại lệ FIFO

- **Đã chốt / nguồn:** Thu mới ưu tiên kỳ nợ cũ trước (D03, `docs/business-rules.md`).
- **Còn thiếu:** Xử lý kỳ cũ thiếu baseline, tranh chấp hoặc không đủ chứng cứ.
- **Ví dụ giả:** khách muốn cấn kỳ 2026-02 trong khi kỳ 2026-01 thiếu baseline.
- **Lựa chọn / hệ quả:** (A) dừng tới khi xử lý kỳ cũ: bảo toàn FIFO, có thể trì hoãn; (B) override có checker/reason: linh hoạt nhưng phải cấp quyền và diễn giải statement; (C) theo chỉ định khách: có thể trái FIFO đã chốt.
- **Đề xuất:** chưa cho override tới khi định nghĩa ngoại lệ cụ thể.
- **Ảnh hưởng:** P0-03 và test FIFO; chặn policy acceptance, không chặn harness test giới hạn receipt đơn giản.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ/kế toán; **CÒN MỞ**.

## Q05 — Source identity và chống nhập trùng receipt

- **Đã chốt / nguồn:** Không suy cùng receipt từ amount; receipt và allocation khác nhau (`docs/business-rules.md`).
- **Còn thiếu:** Khóa nguồn ổn định khi chứng từ thiếu mã duy nhất; scope/retention idempotency key.
- **Ví dụ giả:** hai khoản 100 VND cùng ngày từ hai khách/chứng từ khác nhau; hoặc một chứng từ được gửi lại bằng key mới.
- **Lựa chọn / hệ quả:** (A) nguồn tham chiếu ngoài có unique theo nguồn: chống lặp tốt nhưng đòi nguồn ổn định; (B) fingerprint nhiều field: phát hiện candidate, có nguy cơ false positive; (C) chỉ idempotency key: chống retry, không chống nhập lại cùng chứng từ với key mới.
- **Đề xuất:** idempotency key riêng với source identity; fingerprint chỉ cảnh báo review, không tự từ chối cho tới khi rule nguồn chốt.
- **Ảnh hưởng:** P0-04, P0-03; semantics source dedupe có thể để sau harness nền.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ/kế toán; **CÒN MỞ**.

## Q06 — Phạm vi đảo và hoàn tiền

- **Đã chốt / nguồn:** Posting không sửa đè; sai sót dùng đảo/điều chỉnh có audit (`docs/business-rules.md`).
- **Còn thiếu:** Đảo cả document hay từng line, allocation đã sử dụng, đảo reversal, hoàn tiền ngân hàng.
- **Ví dụ giả:** receipt 100 phân bổ 60+40, line 40 sai; hoặc ngân hàng trả lại 20.
- **Lựa chọn / hệ quả:** (A) đảo toàn receipt rồi post lại: audit đầy đủ nhưng nhiều biến động; (B) đảo line/adjustment: gọn nhưng cần quyền/phạm vi tham chiếu; (C) refund là event riêng: giữ cashflow nhưng cần nguồn/chứng từ.
- **Đề xuất:** phân biệt reversal ledger với cash refund; chưa chọn scope reversal.
- **Ảnh hưởng:** P0-05 và posting/balance tests; chặn acceptance reversal, để sau task harness đầu.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ/kế toán; **CÒN MỞ**.

## Q07 — Ngày nghiệp vụ, kỳ nợ, ngày ghi sổ khi nhập muộn (D07)

- **Đã chốt / nguồn:** Ngày xe nhập kho là event date của chuyến; các ngày/kỳ tách riêng (`docs/business-rules.md`).
- **Còn thiếu:** Backdate posting, debt period và as-of report khi nhập sau close.
- **Ví dụ giả:** xe vào kho 31/01, nhập 03/02 sau khi tháng 01 đã khóa.
- **Lựa chọn / hệ quả:** (A) posting 03/02, giữ event date 31/01, debt period theo nghiệp vụ: không sửa báo cáo đã close; (B) reopen/backdate tháng 01: cần tái phát hành snapshot; (C) đưa cả debt period sang tháng 02: có thể đổi nghĩa vụ khách.
- **Đề xuất:** giữ riêng ba trường; chưa chốt ngày/kỳ nào chịu nghiệp vụ.
- **Ảnh hưởng:** P0-06, statement/as-of; chặn acceptance policy, để sau harness đầu.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ/kế toán; **CÒN MỞ**.

## Q08 — Close/reopen kỳ và điều chỉnh

- **Đã chốt / nguồn:** Số dư có ngày chốt; posting bất biến (`docs/business-rules.md`).
- **Còn thiếu:** Ai close/reopen, thời điểm có hiệu lực, cạnh tranh với approve, tái phát hành snapshot.
- **Ví dụ giả:** checker approve đồng thời kế toán close tháng 01; hoặc phát hiện sai sau close.
- **Lựa chọn / hệ quả:** (A) một lock tuyến tính, close thắng thì post bị từ chối: nhất quán, cần retry; (B) reopen kỳ cũ: sửa lịch sử báo cáo, cần quyền/audit/reissue; (C) adjustment kỳ đang mở: giữ snapshot cũ nhưng cần giải thích điều chỉnh.
- **Đề xuất:** sau khi chọn policy, dùng một serialization point cho post và close.
- **Ảnh hưởng:** P0-06, reversal; chặn acceptance period-lock, để sau harness đầu.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ/kế toán và chủ vận hành; **CÒN MỞ**.

## Q09 — Xác minh receipt và căn cứ tiền (D05/D06)

- **Đã chốt / nguồn:** Chứng từ không tự chứng minh tiền đã nhận; receipt khác chứng từ (`docs/business-rules.md`).
- **Còn thiếu:** Ai/nguồn nào xác minh ngân hàng, reference nào lưu, xử lý phí/tỷ giá và lệch số.
- **Ví dụ giả:** file báo chuyển 100 VND nhưng sao kê xác nhận 99 VND sau phí.
- **Lựa chọn / hệ quả:** (A) người có quyền đối chiếu sao kê: tin cậy hơn, cần phân quyền/chứng cứ; (B) chỉ lưu chứng từ khách gửi: đủ hồ sơ nhưng không xác nhận tiền; (C) tự tính phí/tỷ giá: cần rule và audit riêng.
- **Đề xuất:** chỉ actor/quy trình xác minh đã chỉ định mới cho receipt đạt trạng thái eligible; không tự suy từ file.
- **Ảnh hưởng:** P0-01/02, receipt evidence; chặn hợp thức hóa giao dịch, không chặn test với fixture giả.
- **Người quyết định / trạng thái:** Chủ nghiệp vụ/kế toán; **CÒN MỞ**.

## Không cần hỏi lại

Opening lịch sử không cộng lại; maker và checker khác nhau; thu mới ưu tiên kỳ cũ trước; ngày xe nhập kho là ngày nghiệp vụ chuyến; posting không sửa đè; VND nguyên chính xác và NULL/blank không là 0. Các nguồn tương ứng là `docs/business-rules.md` và `docs/decisions.md` tại revision nêu đầu tài liệu. Không mục nào ở đây biến các fixture/probe thành quyết định đã chốt.
