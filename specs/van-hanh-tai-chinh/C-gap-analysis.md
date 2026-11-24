# C. Gap analysis, xung đột, rủi ro

Trạng thái: **ĐỀ XUẤT** (Claude, 24/11/2026), dựa trên [A](A-audit-hien-trang.md) (quan sát), blueprint v3.0 (mục tiêu) và [R](R-nghien-cuu-tham-chieu.md) (tham chiếu).

[← Mục lục](README.md) · Quyết định: [I](I-decision-register.md)

## 1. Cách đọc

- **Rủi ro** (nếu không làm gì): Rất cao / Cao / TB / Thấp. **Ưu tiên:** P0-a, P0-b, P0-c, P1, P2 ([H](H-migration-rollout.md)).
- Cột tham chiếu ghi loại nguồn theo [R](R-nghien-cuu-tham-chieu.md): TT (thông lệ), YC (chính thức), NCC (nhà cung cấp).

## 2. Gap theo năng lực

| # | Năng lực | Hiện tại (quan sát) | Mục tiêu (v3) | Tham chiếu | Tác động nghiệp vụ | Rủi ro | Ưu tiên | Giải pháp |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G-01 | Pháp nhân, tài khoản, số dư mở | Không có bảng nào; bên phát hành debit note mã cứng ở trình duyệt | Tài khoản gắn pháp nhân, nguyên tệ, số dư mở có bằng chứng | TT | Không biết phạm vi tiền | Cao | P0-a | ADR-TIEN-06; QD-02, QD-10 |
| G-02 | Nhập Excel sao kê có xem trước | Sao kê không vào hệ thống | Staging, kiểm, xem trước, commit một lần | NCC: Microsoft, Oracle | Tiền về không ai biết | Cao | P0-a | ADR-TIEN-02, 03, 17 |
| G-03 | Chống trùng, chồng kỳ | Không có; đề xuất SAO-KE-01 băm theo thứ tự dòng | Hai tầng, không tự bỏ dòng | NCC: Microsoft, Oracle | Tiền giả hoặc mất giao dịch | Cao | P0-a | ADR-TIEN-03 |
| G-04 | Coverage, cutoff, ngày thiếu | Không có | Liên tục số dư, ngày chưa trọn, đánh dấu ngày thiếu | NCC: Microsoft (số dư đầu = cuối kỳ trước) | Kết luận sai "không có giao dịch" | Cao | P0-a | ADR-TIEN-12 |
| G-05 | Tiền chưa rõ (`unidentified`/`unapplied`) | Web không cho (V7-CSM (1)); chat đoán tiền | Trạng thái riêng ở tầng tiền | NCC: Oracle, Odoo | Gán bừa khách, sai nợ | Cao | P0-a | ADR-TIEN-07; QD-05 |
| G-06 | Phân bổ nhiều–nhiều | Phiếu tự phân bổ theo tháng; chat ghép một–một | Bảng phân bổ có trần | NCC: Oracle, Microsoft | Ghi thiếu/trùng khi khách trả gộp | TB | P0-a | ADR-TIEN-05 |
| G-07 | Review cuối ngày, ký | Không có | Hai chữ ký mỗi ngày | NCC: Oracle (*Reviewed*), SAP (cockpit đóng kỳ) | Không ai chịu trách nhiệm số dư | TB | P0-a | ADR-TIEN-04; BR-DC |
| G-08 | Ngoại lệ có chủ, hạn | Việc cần làm chỉ cho sổ nợ | Loại, mức độ, người, hạn, vết | NCC: Oracle, SAP | Việc rơi rớt | TB | P0-a | F1 `exception_case` |
| G-09 | Phân quyền theo chức năng, pháp nhân | Vai chỉ chia màn; fail-open; API mới mở | Cổng riêng, đóng mặc định, phạm vi | YC: COSO; NCC: Microsoft SoD | Lạm quyền | Cao | P0-a | ADR-TIEN-08 |
| G-10 | Bảo vệ dữ liệu ngân hàng | Không có; sao lưu trên `hao` không mã hóa; số tài khoản không che | HMAC, quyền hẹp, mã hóa sao lưu, log truy cập | v3 §8 | Lộ dữ liệu | Cao | P0-a | QD-08 |
| G-11 | Đọc file an toàn | Có bộ đọc xlsx cho Sheet; không `.xls` | Bộ đọc theo mẫu, giới hạn, không thực thi | v3 §4.1 | File độc hại, sai cột | TB | P0-a | ADR-TIEN-17; QD-07 |
| G-12 | Ranh giới agent, máy | Agent tự ghi dữ liệu, đổi quyền ([`TU-LAM-01`](../../docs/decisions/tu-lam-01.md)) | Agent không ghi dữ liệu tiền; login riêng | YC: COSO (môi trường kiểm soát) | Sửa số ngoài kiểm soát | Cao | P0-a | QD-06 |
| G-13 | Số dư xác nhận và ước tính | Hỏi trong nhóm | Số dư theo cutoff + ước tính thận trọng tách riêng | KN | Quyết định chi theo số sai | TB | P0-a / P0-b | ADR-TIEN-16 |
| G-14 | Xuất cho kế toán | Không có | CSV theo kỳ, chống chèn công thức | TT | Đối chiếu tay | TB | P0-a | QD-09 |
| G-15 | Đề nghị chi có snapshot | Xin chi bằng tin nhắn | Phiên bản bất biến, mất duyệt khi sửa | NCC: SAP, Oracle, Microsoft | Chi trái phép, sai người nhận | Cao | P0-b | ADR-TIEN-15 |
| G-16 | Maker–checker | Không có (V6-DB cho sổ nợ) | Chặn tự duyệt ở máy chủ | YC: COSO; NCC: Microsoft, SAP | Tự duyệt | Cao | P0-b | ADR-TIEN-08; QD-14 |
| G-17 | Xác minh người nhận | Không có | Xác minh độc lập khi mới/đổi tài khoản | NCC: SAP (khóa thanh toán khi đổi trường nhạy cảm) | Lừa đổi tài khoản | Cao | P0-b | QD-13 |
| G-18 | Báo thực hiện, ghép chi | Ảnh lệnh vào nhóm | Báo thực hiện ≠ tiền; ghép cuối ngày | NCC: Oracle (lệnh bị trả tự bỏ đối soát) | Chi trùng/sai không bị phát hiện | Cao | P0-b | ADR-TIEN-15 |
| G-19 | Báo thu | "Khách báo đã chuyển" (`contact_mark`) đã có | Báo thu tùy chọn | NCC: Odoo (*In payment* → *Paid*) | Nhập trùng nếu làm màn mới | Thấp | P0-c | ADR-TIEN-14 |
| G-20 | Nối sổ nợ không ghi hai lần | Máy ghi phiếu theo Sheet; không liên kết ngân hàng | Shadow rồi một nguồn ghi | NCC: Microsoft (tạo payment ≠ tất toán) | Ghi công nợ hai lần | Cao | P0-c | ADR-TIEN-09; QD-16 |
| G-21 | Pháp nhân ở sổ nợ | Không có | Ánh xạ sổ → pháp nhân | NCC: SAP, Oracle, Microsoft | Gán nợ sai pháp nhân | TB | P0-c | QD-17 |
| G-22 | Cước trả bằng USD | Sổ nợ chỉ VND; debit note mặc định tài khoản USD | Chính sách quy đổi | NCC: Oracle, Microsoft | Sổ nợ sai khi khách trả USD | Cao nếu tỷ lệ lớn | P0-c (đo ở Discovery) | QD-18 |
| G-23 | Mã thanh toán trên debit note | Số sinh ở trình duyệt, không lưu | Mã lưu DB, QR tùy chọn | NCC: SAP (thuật toán đọc tham chiếu) | Ghép tay nhiều | TB | P0-c / P1 | QD-26 |
| G-24 | Tiền khách Trung Quốc | Excel + ảnh | Sổ tiền khách sau cổng pháp lý | NCC: Microsoft (trả trước là nợ phải trả); YC: pháp lý | Rủi ro pháp lý, tín dụng | Rất cao | P1 | QD-20 |
| G-25 | Quỹ tiền mặt | Không có | Tài khoản `cash`, kiểm quỹ | APQC 8.7.2 | Thất thoát tiền mặt | Cao | P1 | QD-03 |
| G-26 | Phải trả | Chỉ Đội xe | Sổ phải trả, chứng từ | NCC: Oracle (hold), Microsoft (2/3 chiều) | Chi trước nghĩa vụ | TB | P1 | — |
| G-27 | Liên công ty, đa tệ | Không có | Hai bên, tỷ giá có nguồn | NCC: SAP, Oracle, Microsoft | Gộp sai giữa công ty | TB | P1 | ADR-TIEN-06 |
| G-28 | Dự báo, lãi lỗ | Không có | Dự báo 7/30 ngày, giá vốn | NCC: Microsoft | Thiếu thông tin thanh khoản | TB | P2 | — |

## 3. Xung đột với quyết định hiện hành

| # | Hiện hành | v3 / đề xuất | Cách giải | Chốt |
| --- | --- | --- | --- | --- |
| C1 | [`V7-CSM`](../../docs/decisions/v7-csm.md) (1): không tiền chưa rõ chủ trên web | Tiền chưa rõ ở trạng thái riêng | Câu đó chỉ áp cho sổ nợ | QD-05 |
| C2 | V7-CSM (2): sổ nợ chỉ VND thực nhận | Quản lý nguyên tệ | Sổ tiền giữ nguyên tệ; sổ nợ nhận VND theo chính sách | QD-18 |
| C3 | [`V6`](../../docs/decisions/v6.md), [`V6-DB`](../../docs/decisions/v6-db.md): không người duyệt thứ hai | Maker–checker cho chi | Sổ nợ giữ V6; chi có maker–checker | QD-06, QD-12 |
| C4 | [`SONG-SONG-01`](../../docs/decisions/song-song-01.md), [`CHUYEN-HAN-01`](../../docs/decisions/chuyen-han-01.md), [`MAY-DOI-SOAT-01`](../../docs/decisions/may-doi-soat-01.md): Sheet chính thức, máy ghi phiếu | Ghi phiếu khi có tiền thật | Song song chỉ so; một nguồn ghi sau chuyển hẳn | QD-16 |
| C5 | `reallocate`, [`THAY-PHIEU-SHEET-01`](../../docs/decisions/thay-phieu-sheet-01.md): phân bổ tính lại, phiếu bị thay | Phân bổ có khóa, sửa bằng gỡ | Liên kết mức phiếu, kiểm lại khi hủy/sửa | ADR-TIEN-09 |
| C6 | [`QUYEN-01`](../../docs/decisions/quyen-01.md): vai chỉ chia màn, fail-open | RBAC theo chức năng, pháp nhân | Cổng sổ tiền riêng, đóng mặc định | ADR-TIEN-08 |
| C7 | [`QUYEN-02`](../../docs/decisions/quyen-02.md): quản lý quản lý được login | Quyền kỹ thuật không mặc định có quyền tài chính | Vai sổ tiền không suy từ vai quản lý; cấp vai cần người thứ hai | ADR-TIEN-08 |
| C8 | DB sổ nợ không có pháp nhân | Tách pháp nhân | Ánh xạ sổ → pháp nhân ngoài `sokhach` | QD-17 |
| C9 | Số debit note không lưu | Mã tham chiếu trên debit note | Bảng phát hành + mã thanh toán | QD-26 |
| C10 | THU-CHI-02: mỗi giao dịch vào đúng một sổ | Nhiều–nhiều | Theo v3 | v3 đã giải |
| C11 | [`DOI-XE-MO-HINH-01`](../../docs/decisions/doi-xe-mo-hinh-01.md) B4 `tien_chuyen` (chưa code) | Một nguồn giao dịch | Gộp vào sổ tiền; Đội xe giữ nghĩa vụ | Kỹ thuật + chủ Đội xe |
| C12 | [`TU-LAM-01`](../../docs/decisions/tu-lam-01.md): agent tự ghi dữ liệu, đổi quyền | Admin kỹ thuật không duyệt/ghi tài chính | Agent không ghi dữ liệu tiền | QD-06 |
| C13 | [`TELEGRAM-01`](../../docs/decisions/telegram-01.md): tin kèm tên khách, số tiền | Thông báo tối thiểu có link | Chỉ số đếm + link | QD-23 |
| C14 | [`ZALO-THU-CHI-01`](../../docs/decisions/zalo-thu-chi-01.md) Q2, [`ANH-GEMINI-01`](../../docs/decisions/anh-gemini-01.md): đọc tin/ảnh tiền | AI/OCR không xác nhận tiền | Đóng băng phần tính tiền | QD-25 |
| C15 | [`TAI-KHOAN-COT-E-01`](../../docs/decisions/tai-khoan-cot-e-01.md): debit note mặc định tài khoản USD | Sổ nợ VND; thí điểm một tài khoản VND | Đo tỷ lệ cước về USD trước khi chọn tài khoản | QD-18, QD-02 |
| C16 | [SAO-KE-01](../sao-ke-ngan-hang.md) (đề xuất): băm có thứ tự dòng, bảng trong `sokhach`, gãy số dư chặn cả lô | Chống trùng an toàn, schema riêng | Thay bằng ADR-TIEN-03, 11; đánh dấu SAO-KE-01 được thay khi chốt | Kỹ thuật |

## 4. Sổ rủi ro tài chính và kiểm soát

K = khả năng, T = tác động, xét khi chạy mà chưa có kiểm soát đề xuất.

| # | Rủi ro | K | T | Kiểm soát hiện có | Phòng ngừa đề xuất | Phát hiện đề xuất | GĐ |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | Tiền tăng giả do nhập lặp, chồng kỳ | Cao | Cao | — | Chống trùng hai tầng, phân loại lại khi commit | Liên tục số dư, so bằng chứng ngân hàng | P0-a |
| R2 | Bỏ sót giao dịch, tài khoản | TB | Cao | — | Danh mục tài khoản, kỳ chồng | Coverage, ngày thiếu, số dư cuối | P0-a |
| R3 | Ghi công nợ hai lần khi nối ngân hàng | TB | Cao | Sheet là nguồn duy nhất hôm nay | Một nguồn ghi, khóa ổn định | Đối chiếu tiền ↔ phiếu, lưới an toàn | P0-c |
| R4 | Gán nhầm khách/pháp nhân | TB | Cao | — | Không tự gán ở P0; chặn khác pháp nhân | Ngoại lệ, đối chiếu | P0-a |
| R5 | File sao kê bị sửa trước khi tải | Thấp–TB | Cao | — | Lưu file gốc, cảnh báo không phải bản gốc | Người khác tự tải đối chiếu; liên tục số dư | P0-a |
| R6 | Lạm quyền (login bất kỳ, agent, chủ bảng) | TB | Cao | Event, lưới an toàn | Cổng riêng, login riêng, agent không ghi | Cờ trùng vai, tóm tắt tuần, máy canh | P0-a |
| R7 | Lộ dữ liệu ngân hàng | TB | Cao | Quét secrets; log không có thân | HMAC, quyền hẹp, mã hóa sao lưu | Log truy cập, review quyền | P0-a |
| R8 | Hiểu sai cutoff ("số dư cuối ngày" khi file mới tới 17h) | TB | TB | — | Hiện mốc ngân hàng, ngày chưa trọn | Cảnh báo chữ trên thẻ | P0-a |
| R9 | Số thực, làm tròn, cộng khác tệ | Thấp | Cao | `VND-01/02` | Đơn vị nhỏ nhất, tỷ giá `numeric` | Test không cộng khác tệ | P0-a |
| R10 | Đồng thời (bấm hai lần, hai người sửa) | TB | TB | Khuôn khóa `sokhach` | Khóa tài khoản, phiên bản | Harness đồng thời | P0-a |
| R11 | Chi trái phép, đổi người nhận | TB | Cao | — | Phiên bản + maker–checker + xác minh | Ghép chi cuối ngày | P0-b |
| R12 | Báo thực hiện bị hiểu là đã chi | TB | TB | — | Trạng thái `reported_sent` tách biệt | Báo chi chưa thấy tiền | P0-b |
| R13 | Đề nghị của sếp lọt maker–checker | TB | TB | — | Người duyệt thay (QD-14) | Hậu kiểm tuần | P0-b |
| R14 | Tiền khách: trộn tiền, pháp lý, tín dụng | Cao | Rất cao | — (Excel) | Cổng pháp lý trước P1 | Hạn mức, tuổi khoản ứng (P1) | P1 |
| R15 | Tài khoản cá nhân dùng cho công ty | Cao | Cao | — | QD-03; ngoài P0 | — | P1 |
| R16 | Mất dữ liệu, khôi phục chậm | Thấp | Cao | Sao lưu giờ, 3 PC kéo bản mã hóa | Bản ngoài địa điểm, mã hóa bản trên `hao` | Diễn tập có số phút | Trước P0-c |
| R17 | Sao kê không được nhập đều | Cao | TB | — | Phân công, lịch QD-04 | Cảnh báo độ mới | P0-a |

## 5. Phát hiện kiểm soát ở hệ thống hiện có

Không thuộc P0 nhưng ảnh hưởng độ tin của mọi số tiền; nhiều điểm là lựa chọn có chủ đích.

| # | Phát hiện | Mức | Bằng chứng | Gợi ý |
| --- | --- | --- | --- | --- |
| F1 | Vai chỉ chia màn; mọi login được vào ghi được sổ nợ; API mới mặc định mở; thiếu danh sách quản lý thì ai cũng là quản lý | TB | `web/v7_role.py:5`, `:28-29`, `:40-46` | Chế độ Serve: thiếu danh sách thì từ chối khởi động |
| F2 | Một login DB cho người và máy; người làm do app đặt, DB không xác minh | TB | `web/v7_psql.py:207-212` | Chấp nhận ở quy mô nhỏ; module mới dùng login riêng |
| F3 | Agent vận hành được tự nạp dữ liệu, đổi quyền | Cao với tiền | [`TU-LAM-01`](../../docs/decisions/tu-lam-01.md) | QD-06 |
| F4 | Login nạp dữ liệu là thành viên owner (tắt được trigger); superuser vượt trigger | TB | `docs/v7-deploy-runbook.md:237`; `tools/test_pg_v7_luoi_an_toan.py:94-96` | Tách owner khỏi login dùng hằng ngày |
| F5 | Debit note tính tổng ở trình duyệt, số không lưu, tài khoản nhận không che | TB | `preview/debit-note-v4.js:395`; `web/v7_debit_note_config.py:60-61` | QD-26 |
| F6 | Đội xe: bảng tiền chỉ chặn DELETE; `dong_phi` sửa/xóa tại chỗ; `tien_ve` không cờ sau khóa | TB | `tools/migrations/2026-11-18-v7-doi-xe.sql:185-192`, `:691-696` | Rà khi nối Đội xe với sổ tiền |
| F7 | Người sửa từ bảng đối chiếu thì mở/khóa tháng vẫn ghi là máy | Thấp | `web/v7_sheet_fix.py:419-421` | Ghi "theo lệnh của <người>" |
| F8 | Telegram (đang tắt) gửi tên khách, số tiền; có thể gửi trùng | Thấp | `web/v7_telegram.py:92-125`, `:176-179` | QD-23 |
| F9 | Bản sao lưu trên `hao` không mã hóa; PC kéo bản sao cùng địa điểm; RTO chưa đo | TB | `tools/v7_backup.py:364-365`; `docs/rebuild-hao.md:7` | QD-08; bản ngoài địa điểm |
| F10 | Peer chỉ-đọc (bot Zalo) gọi được mọi GET không thuộc tiền tố quản lý | TB | `web/v7_identity.py:312-315`; `web/v7_role.py:40-46` | Cổng sổ tiền từ chối peer chỉ-đọc |
| F11 | `cash_report_review` chỉ thêm nhờ quyền hàm, không trigger | Thấp | `tools/migrations/2026-11-21-v7-cash-report-review.sql:124-128` | Đóng băng |
| F12 | SAO-KE-01 băm chống trùng gồm thứ tự dòng → file chồng kỳ ghi hai lần | Cao nếu code theo | `specs/sao-ke-ngan-hang.md:134` | ADR-TIEN-03 |
