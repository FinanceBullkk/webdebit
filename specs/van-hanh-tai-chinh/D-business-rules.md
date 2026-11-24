# D. Đặc tả quy tắc nghiệp vụ (Business Rules Specification)

Trạng thái: **ĐỀ XUẤT** (Claude, 24/11/2026), trừ các dòng ghi [HH]. Quy tắc chưa chốt không được code như chính sách ([AGENTS.md](../../AGENTS.md)).

[← Mục lục](README.md) · Quyết định cần chốt: [I](I-decision-register.md) · Kiến trúc: [F1](F1-kien-truc-ky-thuat.md)

Nhãn trạng thái:

- **[HH]** hiện hành: đã có trong mã hoặc đã chốt (dẫn nguồn).
- **[CDN]** đề xuất, cần **chủ doanh nghiệp** chốt.
- **[KT]** đề xuất, cần **kế toán** chốt.
- **[KTh]** đề xuất kỹ thuật bảo vệ tính đúng; cần review nhưng không phải lựa chọn nghiệp vụ.

Giai đoạn: P0-a (sổ tiền nền), P0-b (kiểm soát chi), P0-c (nối sổ nợ) — xem [H](H-migration-rollout.md).

## 1. Nguyên tắc chung (BR-G)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-G1 | Một giao dịch ngân hàng thật chỉ được ghi **một lần**, dù xuất hiện trong nhiều file | [KTh] |
| BR-G2 | Báo thu, đề nghị chi, duyệt, báo thực hiện là hồ sơ nghiệp vụ, **không** chứng minh tiền đã di chuyển | [KTh] (v3 §2) |
| BR-G3 | Tiền vào không tự là doanh thu; tiền ra không tự là chi phí | [KT] (v3 §1) |
| BR-G4 | Giao dịch chưa đủ căn cứ không được gán cho khách tùy ý; giữ trạng thái chưa rõ | [CDN] (v3 §4.3) |
| BR-G5 | Không ghép tự động chỉ vì số tiền bằng nhau | [KTh] (v3 §5) |
| BR-G6 | Số dư xác nhận (theo sao kê, ghi rõ cutoff) và số dư ước tính luôn hiển thị riêng | [CDN] (v3 §6) |
| BR-G7 | Tách theo pháp nhân và nguyên tệ; không cộng khác tiền tệ khi thiếu tỷ giá ghi rõ | [KT] |
| BR-G8 | Tiền là số nguyên ở đơn vị nhỏ nhất (đồng, xu); ô trống là chưa biết, không thành 0 | [HH] (`VND-01/02`, [quy tắc nghiệp vụ](../../docs/business-rules.md)) |
| BR-G9 | Sửa sai bằng đảo, gỡ, hủy có lý do; không sửa im lặng dữ liệu đã ghi | [HH] cho sổ nợ ([`V7-SO`](../../docs/decisions/v7-so.md)); [KTh] cho sổ tiền |
| BR-G10 | Sao kê thật, chứng từ, nội dung chuyển khoản không gửi tới dịch vụ AI bên ngoài, repo, log, bot | [CDN] (v3 §8) |
| BR-G11 | Không đổi luật và lịch sử sổ nợ hiện có: nợ cũ trước, khóa tháng, Lịch sử, phiếu tháng khóa vẫn nhập | [HH] ([`V7-BE`](../../docs/decisions/v7-be.md), [`CAN-DU-01`](../../docs/decisions/can-du-01.md), [khóa tháng](../../docs/decisions/khoa-thang-2026-10-24.md)) |
| BR-G12 | Không kết nối ngân hàng (API, webhook, RPA, dịch vụ đọc), không lưu mật khẩu/OTP, không chuyển tiền từ webdebit | [HH] ràng buộc chủ doanh nghiệp đã xác nhận (v3 §1) |

## 2. Báo thu — receipt notice (BR-RN)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-RN1 | Báo thu là **tùy chọn**; tiền về không có báo thu vẫn được ghi và xử lý cuối ngày | [CDN] (v3 §3.1) |
| BR-RN2 | P0 dùng lại "Khách báo đã chuyển" (`contact_mark` loại `paid_claim`): sổ khách, số tiền VND, ngày, ghi chú mục đích/tháng, gắn tin Zalo nếu có | [CDN] (QD-15); [HH] cho dữ liệu đang có (`schema:131-171`) |
| BR-RN3 | Báo thu không tạo phiếu, không giảm nợ; sổ khách hiện riêng "đang chờ xác minh" | [HH] (`contact_mark` không tham gia tính tiền) |
| BR-RN4 | Cuối ngày, báo thu được ghép với giao dịch vào; báo thu chỉ là bằng chứng phụ của phân bổ | [KTh] |
| BR-RN5 | Báo thu quá 3 ngày làm việc chưa thấy tiền → ngoại lệ theo dõi; không tự hủy | [CDN] (QD-24) |
| BR-RN6 | Báo thu chưa xác minh không được dùng để tài trợ chi (kể cả chi hộ ở P1) | [CDN] (v3 §3.3) |
| BR-RN7 | Hủy báo thu bắt buộc lý do; giữ lịch sử | [HH] (`schema:149-155`) |

## 3. Đề nghị chi và duyệt (BR-PR) — P0-b

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-PR1 | Đề nghị tạo từ hồ sơ sẵn có (chuyến, container, xe, dòng Đội xe, nhà cung cấp); không nhập lại dữ liệu đã có | [CDN] |
| BR-PR2 | Trường bắt buộc: pháp nhân, tài khoản trả dự kiến, số tiền + tiền tệ, người nhận + tài khoản thụ hưởng (lưu HMAC + 4 số cuối), loại chi, lý do, ngày cần chi, tham chiếu nghĩa vụ hoặc lý do không có | [CDN] |
| BR-PR3 | Hệ thống sinh mã đề nghị duy nhất (ví dụ `DC0456`, mã bịa), in sẵn để kế toán dán vào nội dung chuyển khoản | [KTh] |
| BR-PR4 | Mỗi lần sửa trường trọng yếu (số tiền, tiền tệ, người nhận, tài khoản thụ hưởng, tài khoản trả, mục đích) tạo **phiên bản mới**; duyệt cũ mất hiệu lực | [CDN] (v3 §3.2) |
| BR-PR5 | Người duyệt **khác** người đề nghị (maker–checker), kiểm ở máy chủ | [CDN] (QD-06, QD-14) |
| BR-PR6 | Ngưỡng duyệt, người duyệt thay, khoản khẩn/định kỳ, duyệt bù theo chính sách chủ doanh nghiệp chốt | [CDN] (QD-12) |
| BR-PR7 | Người nhận mới hoặc đổi tài khoản thụ hưởng phải xác minh độc lập qua kênh đã biết trước khi duyệt; ghi kết quả | [CDN] (QD-13) |
| BR-PR8 | Duyệt có hạn hiệu lực (đề xuất 7 ngày); quá hạn chưa thực hiện → `expired`, phải duyệt lại | [CDN] |
| BR-PR9 | Báo thực hiện (`reported_sent`) chỉ là lời kế toán báo; một đề nghị có thể nhiều lần báo; tổng báo vượt số duyệt → chặn hoặc ngoại lệ | [KTh] |
| BR-PR10 | Lệnh lỗi, bị trả lại: báo trạng thái `failed`/`returned`, không xóa lịch sử | [KTh] (v3 §3.2) |
| BR-PR11 | Đề nghị đã duyệt chưa chuyển là **cam kết chi**, hiển thị riêng, không trừ vào số dư xác nhận | [CDN] (v3 §6) |
| BR-PR12 | Không có chức năng chuyển tiền; kế toán kiểm số dư và lệnh trực tiếp tại ngân hàng, dùng duyệt hai cấp của ngân hàng nếu có | [HH] ràng buộc (v3 §1) |

## 4. Nhập sao kê (BR-IM) — P0-a

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-IM1 | Chỉ vai nhập được tải; file là bản **gốc** tải từ ngân hàng, không mở rồi lưu lại bằng Excel | [CDN] (QD-07) |
| BR-IM2 | Mỗi tài khoản gắn một mẫu file (bộ đọc có tên + phiên bản); file khác mẫu bị từ chối, không đoán cột | [KTh] (v3 §4.1) |
| BR-IM3 | Đọc an toàn: không chạy macro/công thức/liên kết ngoài; giới hạn kích thước file, số mục và dung lượng giải nén; từ chối XML có DOCTYPE | [KTh] (v3 §4.1) |
| BR-IM4 | Bắt buộc xem trước: mỗi dòng là *mới / trùng chắc / nghi trùng / lỗi*; dòng lỗi phải sửa bằng file khác, dòng nghi trùng phải có quyết định | [KTh] |
| BR-IM5 | Commit nguyên tử dưới khóa tài khoản; **phân loại lại tại thời điểm commit**; nếu sổ tài khoản đã đổi từ lúc xem trước thì từ chối và yêu cầu xem trước lại | [KTh] (sửa sau review) |
| BR-IM6 | Đích "trùng của giao dịch X" phải tồn tại, cùng tài khoản, còn hiệu lực, và không bị hai dòng cùng lô trỏ tới | [KTh] |
| BR-IM7 | Chống trùng tầng file: cùng tài khoản + cùng băm file đã commit → trả lô cũ, 0 giao dịch mới | [KTh] |
| BR-IM8 | Mã giao dịch ngân hàng chỉ làm khóa duy nhất khi Discovery chứng minh ổn định; nếu không, dấu vân (tài khoản, ngày ghi sổ, chiều, số tiền, mô tả chuẩn hóa — **không** gồm số dư sau) chỉ để tìm ứng viên; dòng không ghép được trong vùng chồng kỳ thành nghi trùng | [KTh] (sửa sau review) |
| BR-IM9 | Hai giao dịch thật giống hệt nhau trong cùng file đều được giữ | [KTh] (v3 U03) |
| BR-IM10 | Liên tục: số dư đầu của file phải bằng số dư sổ tiền ở cuối điểm đã phủ trước đó; không bằng → gãy chuỗi, không xác nhận coverage | [KTh] (sửa sau review) |
| BR-IM11 | Ngày cuối của file là **ngày chưa trọn** trừ khi file chứng minh đã hết ngày; lần nhập sau phải bắt đầu từ ngày đó trở về trước | [KTh] (v3 §4.2) |
| BR-IM12 | Ngày không có file, hoặc không có bằng chứng "không phát sinh", được đánh dấu **thiếu**; không suy ra "không có giao dịch" | [CDN] (v3 §4.2) |
| BR-IM13 | Hủy lô bắt buộc lý do; giao dịch chỉ mất khi không còn dòng nguồn nào ở lô khác còn hiệu lực; bị chặn nếu giao dịch sẽ mất đang có phân bổ hoặc thuộc ngày đã ký | [KTh] (sửa sau review) |
| BR-IM14 | File có băm khác nhưng nội dung trùng (thường do mở/lưu lại) → cảnh báo "không phải bản gốc", dòng vẫn chống trùng theo BR-IM8 | [KTh] |

## 5. Ghép (BR-MA)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-MA1 | Mức **A** (đủ căn cứ): mã hợp lệ (mã đề nghị, mã thanh toán) + đúng pháp nhân, tài khoản, tiền tệ, chiều, số tiền, không mâu thuẫn | [KTh] (v3 §5) |
| BR-MA2 | Mức **B** (ứng viên): người chuyển đã biết, báo thu/báo thực hiện cùng số tiền và thời gian, nội dung gần đúng → gợi ý có lý do, người xác nhận | [KTh] |
| BR-MA3 | Mức **C** (không rõ/mâu thuẫn): nhiều ứng viên, mã sai, khác pháp nhân, trả hộ, thiếu dữ liệu → không ghép, mở ngoại lệ | [KTh] |
| BR-MA4 | P0-a, P0-b: chỉ gợi ý (shadow). Tự áp mức A chỉ sau khi đo shadow đạt ngưỡng và kế toán ký | [KT] (ngưỡng ở QD-21) |
| BR-MA5 | Danh bạ tài khoản đối tác chỉ dùng khi file thật có trường đó và quan hệ đã xác minh; không tự học người trả hộ thành quan hệ độc quyền | [KTh] (v3 §5) |
| BR-MA6 | Nhận diện khách tách khỏi xác định mục đích/tháng: biết khách chưa chắc là tiền cước | [KT] (v3 §5) |
| BR-MA7 | Luật có phiên bản; mỗi gợi ý lưu luật + phiên bản + lý do | [KTh] |
| BR-MA8 | AI/OCR chỉ trích xuất chứng từ; không xác nhận tiền, không ghép, không ghi sổ | [CDN] (QD-25) |

## 6. Phân bổ (BR-AL)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-AL1 | Một giao dịch nhiều dòng phân bổ; một đích nhận nhiều giao dịch (nhiều–nhiều) | [KTh] |
| BR-AL2 | Σ dòng hiệu lực ≤ số tiền giao dịch, cùng tiền tệ; phần còn lại là chưa phân bổ | [KTh] |
| BR-AL3 | Thay bộ phân bổ tạo phiên bản mới; **mọi** lần bỏ hoặc đổi dòng đang hiệu lực bắt buộc lý do | [KTh] (sửa sau review) |
| BR-AL4 | Tiền vào: `unidentified` (chưa rõ khách) → `unapplied` (biết khách, chưa rõ mục đích) → `partial` → `applied` | [CDN] (v3 §5) |
| BR-AL5 | Tiền ra: `unmatched` → `partial` → `matched` (với đề nghị/đích); chi không có đề nghị đã duyệt → ngoại lệ | [CDN] |
| BR-AL6 | Phân bổ khác pháp nhân bị từ chối; người dùng mở ngoại lệ "liên công ty" bằng lệnh riêng (lệnh này không bị chặn) | [CDN] (sửa sau review) |
| BR-AL7 | Phí ngân hàng, chênh tỷ giá, xóa chênh nhỏ chỉ bằng dòng loại riêng do vai được phép tạo; không tự xóa chênh lệch bằng dung sai | [KT] (QD-21) |
| BR-AL8 | Tiền hàng khách (P0) chỉ gắn nhãn `customer_funds_pending`, giữ nguyên tệ; không tự đưa vào sổ nợ | [CDN] (QD-20) |
| BR-AL9 | Chuyển nội bộ ghép hai chân; nếu tài khoản đối ứng chưa trong phạm vi thì để `internal_transfer_pending` | [KT] |
| BR-AL10 | Chi cho Đội xe phân bổ vào đích `fleet` tham chiếu dòng ứng/hoàn sẵn có; không tạo bản ghi Đội xe thứ hai | [CDN] |

## 7. Ghi nhận — posting (BR-PO)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-PO1 | P0 không lập sổ cái kép; sổ cái pháp định ở phần mềm kế toán; sổ tiền xuất CSV để kế toán đối chiếu | [KT] (QD-09) |
| BR-PO2 | Ghi phiếu thu sổ nợ từ giao dịch ngân hàng chỉ ở P0-c, **sau** khi chủ doanh nghiệp chọn một nguồn ghi duy nhất (QD-16) | [CDN] |
| BR-PO3 | Một nguồn ghi: khi bật ghi phiếu từ ngân hàng cho một sổ thì máy ghi phiếu theo Sheet phải tắt cho sổ đó, cùng một lần đổi cấu hình | [CDN] |
| BR-PO4 | Ghi phiếu qua hàm hiện có `record_receipt`; khóa lặp = băm(mã giao dịch sổ tiền, mã sổ khách), không đổi theo phiên bản phân bổ; `reference` = mã giao dịch sổ tiền | [KTh] (sửa sau review) |
| BR-PO5 | Trước khi ghi, kiểm không có phiếu còn hiệu lực mang cùng `reference`; có thì dừng | [KTh] |
| BR-PO6 | FIFO, phân bổ theo tháng, trả dư thành số âm giữ nguyên | [HH] (V7-BE, CAN-DU-01, V7-CSM (1)) |
| BR-PO7 | Tiền USD trả cước: sổ nợ ghi VND thực nhận theo chính sách kế toán chốt; chưa chốt thì không ghi | [KT] (QD-18) |
| BR-PO8 | Bản xuất CSV vô hiệu ô bắt đầu bằng `=`, `+`, `-`, `@` (chống chèn công thức) | [KTh] (v3 §8) |

## 8. Đảo và sửa (BR-RV)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-RV1 | Không sửa số tiền, ngày, chiều của giao dịch đã commit; giao dịch đảo của ngân hàng là giao dịch mới | [KTh] |
| BR-RV2 | Gỡ phân bổ bắt buộc lý do; giữ dòng cũ và vết | [KTh] |
| BR-RV3 | Hủy đề nghị chi chỉ trước khi có báo thực hiện; sau đó dùng `failed`/`returned` theo thực tế | [CDN] |
| BR-RV4 | Thu hồi duyệt trước khi chuyển: có lý do, tạo vết | [CDN] |
| BR-RV5 | Mở lại ngày đã ký: người review, lý do bắt buộc; mọi thay đổi sau đó có vết "sau ký" | [CDN] |
| BR-RV6 | Phiếu sổ nợ sinh từ ngân hàng bị sai: hủy phiếu (có lý do, theo luật hiện có) rồi gỡ phân bổ | [HH] cho hủy phiếu (`schema:6498-6540`) |
| BR-RV7 | Liên kết tới phiếu sổ nợ được kiểm lại khi phiếu bị hủy **hoặc** sửa ngày, hình thức, tham chiếu; lệch → "cần xem lại" | [KTh] (sửa sau review) |

## 9. Ngoại lệ (BR-EX)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-EX1 | Mỗi ngoại lệ có loại, mức độ, số tiền + tiền tệ, tài khoản, người xử lý, hạn, bằng chứng, lịch sử, kết quả | [CDN] (v3 §5) |
| BR-EX2 | Ngoại lệ không tự đóng khi sang ngày; chỉ đóng bằng hành động thật hoặc bỏ có lý do (người review) | [CDN] |
| BR-EX3 | Cờ "chi chưa duyệt" chỉ người duyệt gỡ (duyệt bù có lý do, ghi rõ là duyệt bù); người chuyển tiền không tự gỡ | [CDN] |
| BR-EX4 | Mở ngoại lệ là lệnh riêng, không phụ thuộc lệnh đang bị từ chối | [KTh] |
| BR-EX5 | Cảnh báo là dấu hiệu cần xác minh, không phải kết luận gian lận; câu chữ trên màn tránh quy kết | [CDN] |

## 10. Chốt cuối ngày (BR-DC)

| ID | Quy tắc | Trạng thái |
| --- | --- | --- |
| BR-DC1 | Mỗi ngày làm việc, mỗi tài khoản trong phạm vi: nhập → kiểm số dư, coverage → ghép → phân bổ → ngoại lệ → review | [CDN] (QD-04, QD-24) |
| BR-DC2 | Hai chữ ký riêng: **coverage + số dư** và **đối soát nghiệp vụ**; ký nghiệp vụ được khi còn ngoại lệ mở nhưng phải ghi số lượng | [CDN] (v3 §4.3) |
| BR-DC3 | Ký coverage + số dư chỉ khi: chuỗi liên tục, không ngày thiếu trong kỳ ký, không dòng lỗi/nghi trùng, chênh = 0 | [KTh] |
| BR-DC4 | Chênh = số dư cuối tính từ sổ tiền − số dư cuối theo bằng chứng ngân hàng; file không có số dư cuối thì bằng chứng do người **khác** người nhập tải và nhập | [KT] (sửa sau review) |
| BR-DC5 | Người review khác người nhập; thiếu người thì được trùng vai nhưng bị gắn cờ và vào tóm tắt tuần cho chủ doanh nghiệp | [CDN] (QD-06) |
| BR-DC6 | Review ngày không phải khóa kỳ tháng; khóa kỳ tháng là việc riêng của kế toán | [KT] (v3 §4.4) |
| BR-DC7 | Báo cáo cuối ngày gồm: thu/chi đã xác nhận, chuyển nội bộ tách riêng, số dư theo cutoff, chưa phân loại, báo thu chưa thấy tiền, báo chi chưa thấy tiền, chi bất thường, người phụ trách, hạn | [CDN] (v3 §4.4) |
