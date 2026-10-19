# Quyết định nghiệp vụ còn mở

Các trạng thái dưới đây được cập nhật theo quyết định người dùng ngày 15/10/2026. Quy tắc nền đã chốt dẫn từ `docs/business-rules.md` / `docs/decisions.md`; quyết định lịch sử tại revision `8365e8aa5ae2517959dedcc52ed8384232458b75`. Không cần hỏi lại các nguyên tắc đã chốt ở cuối tài liệu.

## Q01 — Danh tính maker/checker — MÔ HÌNH ĐÃ CHỐT

- **Đã chốt / nguồn:** Maker và checker khác nhau (D01). Người dùng chốt self-host trên máy này, phải nối vào tailnet của chủ máy mới vào được login, và giao chọn mô hình phù hợp nghiệp vụ; đã chọn tài khoản ứng dụng riêng theo từng người.
- **Quyết định:** Tailscale là cổng mạng, không là danh tính phê duyệt. Sau khi vào app, mỗi người đăng nhập bằng tài khoản cá nhân; ứng dụng lấy actor từ session server-side đã xác thực, bỏ qua actor tự khai trong payload/header. Không dùng chung tài khoản. Maker và checker phải là hai người/tài khoản khác nhau. Chưa yêu cầu nhiều máy.
- **Lý do:** Vẫn truy cập gọn trong tailnet nhưng audit ghi được người cụ thể; maker/checker tách được ngay cả khi app chỉ chạy trên một máy. Tài khoản dùng chung không thể quy trách nhiệm; dùng Tailscale làm identity principal sẽ buộc phải dựa vào cấu hình proxy/header đáng tin cậy và ánh xạ danh tính mạng sang quyền nghiệp vụ.
- **Ví dụ giả:** An tạo phiếu bằng account của An; Bình duyệt bằng account của Bình. Nếu hiện chỉ có An, phiếu không được tự duyệt/post cho đến khi có checker khác.
- **Còn làm rõ trước implementation:** bootstrap/admin đầu tiên, lưu và reset mật khẩu, hết hạn/thu hồi session, cấp-thu hồi account/role, offboarding, ánh xạ app actor → DB audit, trust proxy và chặn direct bypass ngoài Tailscale. Đây là chi tiết triển khai/vận hành, không còn là lựa chọn giữa account cá nhân và identity Tailscale.
- **Ảnh hưởng:** Q01 không còn chặn thiết kế P0-02 ở mức quyết định mô hình. Write guard vẫn chưa được triển khai; cần thiết kế và kiểm chứng login/session/role/audit cùng quyền DB trước khi mở đường ghi thật.
- **Người quyết định / trạng thái:** Phạm vi Tailscale do người dùng chốt ngày 15/10/2026; mô hình tài khoản riêng được chọn theo yêu cầu người dùng giao lựa chọn; **ĐÃ CHỐT mô hình**, chi tiết vận hành và kiểm chứng **CÒN LÀM**.

## Q02 — Approval bao phủ revision/nội dung nào — ĐÃ CHỐT

- **Đã chốt / nguồn:** Người dùng xác nhận ngày 15/10/2026: approval gắn với revision nội dung bất biến; mọi thay đổi nghiệp vụ tạo revision mới và cần duyệt lại. Chỉnh sửa trình bày không đổi ý nghĩa nghiệp vụ không cần duyệt lại. Maker khác checker (D01).
- **Còn thiếu cho thiết kế kỹ thuật:** Cách mã hóa/hash canonical payload, append-only storage, thao tác withdraw/re-submit và chính xác metadata audit. Đây là chi tiết triển khai, không thay đổi quy tắc đã chốt.
- **Ví dụ giả:** checker duyệt 100 VND cho kỳ 2026-01; maker đổi thành 101 hoặc đổi kỳ trước khi post.
- **Quy tắc:** revision gồm khách, kỳ nợ, loại phiếu, tổng tiền và từng dòng/phân bổ, ngày nghiệp vụ/ngày ghi sổ, source reference, evidence reference/hash, lý do và mọi trường làm thay đổi nội dung được ghi/đối soát. Sửa một trường thuộc phạm vi này tạo revision mới; approval cũ không dùng cho bản mới. Lưu lịch sử cũ, không sửa đè. Không cần duyệt lại khi chỉ đổi cách trình bày không làm đổi nghĩa.
- **Ảnh hưởng:** Quy tắc stale approval đã chốt; cần acceptance tests cho nội dung không đổi, nội dung đổi, approval revision cũ, và chỉnh sửa trình bày. Mô hình app actor đã chọn tại Q01; kiểm chứng login/session/role và nối actor tới audit DB còn trước implementation.
- **Người quyết định / trạng thái:** Người dùng/chủ nghiệp vụ; **ĐÃ CHỐT** ngày 15/10/2026. Thiết kế storage/hash cụ thể CÒN LÀM.

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
