# G. UAT và chiến lược test

Trạng thái: **ĐỀ XUẤT** (Claude, 24/11/2026). Ưu tiên tính đúng tài chính hơn tỷ lệ tự động. Mục tiêu trên bộ UAT: không ghi trùng, không bỏ sót dòng thật, không ghép sai được xác nhận, không chênh số dư chưa giải thích — không đồng nghĩa bảo đảm tuyệt đối ở production (v3 §9).

[← Mục lục](README.md) · ADR và `AT-xx.y`: [F2](F2-adr.md) · Quy tắc: [D](D-business-rules.md) · Rollout: [H](H-migration-rollout.md)

## 1. Nguyên tắc

- Test tự động chỉ dùng **số bịa** và file sao kê tự dựng theo cấu trúc mẫu đã che; không chép dòng thật vào repo.
- UAT trên `hao` dùng dữ liệu thật của tài khoản thí điểm ở chế độ `shadow`; kết quả ghi **số đếm** vào nhật ký, không tên khách, không số tiền thật.
- Mỗi ca có người chạy (kế toán, người duyệt, team công nợ) và người ký kết quả.
- Bộ test hiện có (`npm run check`, harness `tools/test_pg_v7_*`, lưới an toàn) phải xanh **không sửa** — bằng chứng sổ nợ không bị phá.

## 2. UAT

### 2.1 Bộ cơ sở theo v3 §10

| ID | Tình huống | Kết quả bắt buộc | GĐ | Phủ bởi |
| --- | --- | --- | --- | --- |
| U01 | Nhập file lặp, gửi lại, hai người cùng nhập | Không thêm tiền giả | P0-a | AT-03.1, 03.5, 03.6 |
| U02 | Hai file chồng kỳ | Giữ đúng giao dịch mới, không trùng | P0-a | AT-03.2, 03.4 |
| U03 | Hai giao dịch thật giống số tiền/nội dung | Không tự loại nhầm | P0-a | AT-03.3 |
| U04 | Thiếu kỳ; sai tài khoản, tiền tệ, số dư | Cảnh báo; không xác nhận coverage/số dư | P0-a | AT-12.3, 12.4, 04.1 |
| U05 | Giao dịch sau cutoff, cuối tuần | Lần sau nhập đúng ngày ghi sổ, không mất, không trùng | P0-a | AT-12.3, 03.2 |
| U06 | Tiền về không có báo thu | Ghi nhận tiền; `unidentified`; mở xác minh | P0-a | AT-07.2 |
| U07 | Báo thu có ảnh nhưng không thấy tiền | Chờ xác minh; không giảm nợ | P0-c | AT-14.1 |
| U08 | Nội dung chung chung, hai ứng viên cùng tiền | Không tự ghép; review | P0-a (shadow) | AT-10.3 |
| U09 | Một người trả hộ nhiều khách, mã mâu thuẫn | Review, không học quan hệ sai | P0-a (shadow) | BR-MA5 |
| U10 | Một khoản thu cho nhiều tháng, nhiều mục đích | Phân bổ đúng tổng, không ghi tiền hai lần | P0-a | AT-05.1 |
| U11 | Trả dư, chỉ định tháng | Theo luật sổ nợ hiện hành; dư không thành doanh thu | P0-c | BR-PO6, QD-19 |
| U12 | Đề nghị đã duyệt chưa gửi lệnh | Không giảm tiền thực; hiện ở cam kết | P0-b | AT-16.1 |
| U13 | Báo đã chuyển chưa thấy sao kê | Chờ; không tự chuyển lại | P0-b | AT-16.2 |
| U14 | Đề nghị 50 chi 30 rồi 20 (số bịa) | `in_execution` rồi `settled`, không báo trùng | P0-b | AT-05.5 |
| U15 | Chi vượt, sai người nhận, trước duyệt, không duyệt | Ghi tiền thật, ngoại lệ, không sửa lịch sử duyệt | P0-b | AT-15.3 |
| U16 | Sửa snapshot sau duyệt | Phải duyệt lại phiên bản mới | P0-b | AT-15.1 |
| U17 | Giao dịch khớp rời khỏi ước tính | Không cộng/trừ hai lần | P0-b | AT-16.1, 16.2 |
| U18 | Khớp số dư nhưng còn giao dịch chưa phân loại | Ký coverage được; ngoại lệ vẫn mở | P0-a | AT-04.2 |
| U19 | Hoàn trả, đảo phân bổ, ngày đã ký | Điều chỉnh có quyền, có vết, không mất lịch sử | P0-a | AT-02.2, 05.4 |
| U20 | Khách trả thẳng hãng tàu | Không tạo giao dịch ngân hàng giả | P0-a | BR-G2 |
| U21 | Chuyển nội bộ, rút quỹ | Không ghi thu/chi giả; ghép hai chân hoặc `internal_transfer_pending` | P0-a | BR-AL9 |
| U22 | Truy cập ID pháp nhân khác; tự duyệt | Chặn ở máy chủ | P0-a/b | AT-08.2, 08.4 |
| U23 | Lỗi giữa commit/ghi | Lùi nguyên tử, gửi lại an toàn | P0-a/c | AT-03.6, 09.3 |
| U24 | File độc hại/quá lớn; đọc dòng gốc không quyền | Từ chối an toàn, không lộ dữ liệu | P0-a | AT-17.1, 08.1 |
| U25 | P1: hai yêu cầu chi hộ đồng thời | Không vượt số dư/hạn mức | P1 | — |
| U26 | P1: USD đổi một phần, phí, tỷ giá khác | Nguyên tệ, hai chân đúng | P1 | — |
| U27 | P1: khách A dương, khách B âm | Không bù trừ che rủi ro | P1 | — |
| U28 | P1: chuyển giữa pháp nhân, kiểm quỹ lệch | Tách đúng, cảnh báo, review | P1 | AT-06.2 (phần P0) |

### 2.2 Ca bổ sung từ audit mã và review

| ID | Tình huống (nguồn phát hiện) | Kết quả bắt buộc | GĐ |
| --- | --- | --- | --- |
| UA-01 | File mở rồi lưu lại bằng Excel (băm khác, nội dung trùng) | Cảnh báo `NOT_ORIGINAL_FILE`; dòng trùng vẫn nhận ra | P0-a |
| UA-02 | File xuất giữa ngày, file sau bắt đầu từ ngày kế (review) | Gãy chuỗi; không ký coverage; phải nhập lại ngày chưa trọn | P0-a |
| UA-03 | Hai lô chồng kỳ xem trước song song, commit lần lượt (review) | Lô sau `IMPORT_PREVIEW_STALE`; không ghi trùng | P0-a |
| UA-04 | Hủy lô A sau khi lô B xác nhận trùng các dòng của A (review) | Giao dịch còn nguyên (nguồn B); số dư không đổi | P0-a |
| UA-05 | `.xls` khi chưa chốt QD-07; zip bom; XML có DOCTYPE; ô công thức | Từ chối hoặc đọc giá trị lưu; không thực thi gì | P0-a |
| UA-06 | Máy theo Sheet hủy rồi ghi lại phiếu đã liên kết (`THAY-PHIEU-SHEET-01`) | Liên kết thành "cần xem lại" | P0-c |
| UA-07 | Sửa ngày/hình thức phiếu đã liên kết (`schema:3478`, review) | Liên kết thành "cần xem lại" | P0-c |
| UA-08 | Ghi phiếu từ ngân hàng, sập giữa hai giao dịch DB, chạy lại | Đúng một phiếu; liên kết được lưu | P0-c |
| UA-09 | Bật ghi từ ngân hàng khi máy theo Sheet còn bật cho cùng sổ | `AR_POSTING_DISABLED` | P0-c |
| UA-10 | Phiếu mới làm `reallocate` đổi phân bổ tháng của phiếu cũ | Liên kết sổ tiền không đổi (trỏ phiếu, không trỏ dòng phân bổ) | P0-c |
| UA-11 | Phiếu từ ngân hàng rơi vào tháng khóa | Ghi được như luật hiện hành; khóa tháng không đổi | P0-c |
| UA-12 | Login "người dùng" của QUYEN-01; bot Zalo chỉ-đọc | 403 `TIEN_FORBIDDEN` / `READONLY_PEER` | P0-a |
| UA-13 | Chưa cấp vai nào; vai quản lý QUYEN-01 không có vai tiền | Module không mở; quản lý không tự có quyền tiền | P0-a |
| UA-14 | "Khách báo đã chuyển" bị hủy sau khi làm bằng chứng | Gợi ý gỡ bằng chứng; tiền không đổi | P0-c |
| UA-15 | Chi cho tài xế phân bổ vào `fleet` | Không tạo dòng ứng thứ hai ở Đội xe; số dư người không đổi | P0-a |
| UA-16 | Ảnh biên lai trong nhóm Zalo/WeChat | Không tạo giao dịch tiền nào | P0-a |
| UA-17 | Xuất CSV có ô bắt đầu bằng `=`, `+`, `-`, `@` | Ô bị vô hiệu | P0-a |
| UA-18 | Khôi phục bản sao lưu | Có schema `tien`; số dư tiền và tổng sổ nợ khớp | P0-a |
| UA-19 | Chủ doanh nghiệp tự tạo đề nghị chi | Không tự duyệt; theo người duyệt thay (QD-14) | P0-b |
| UA-20 | Hai giao dịch ra cùng số tiền cùng ngày, chỉ một có mã đề nghị | Chỉ giao dịch có mã khớp; giao dịch kia ngoại lệ | P0-b |
| UA-21 | Mở dòng gốc, nội dung chuyển khoản | Có dòng log truy cập (ai, lúc, đối tượng), không chứa nội dung | P0-a |

### 2.3 Hồi quy sổ nợ

Theo v3 §10, kiểm trên mã thật: ma trận theo tháng/năm, tổng năm và toàn kỳ, khách không hoạt động năm chọn, tháng khóa, số dư âm, điều chỉnh. Cách làm: chạy bộ test hiện có không sửa; harness mới `test_pg_tien_isolation.py` so dấu vân bảng `sokhach` và kết quả `get_receivables_matrix`, `get_dashboard` trước/sau một kịch bản đầy đủ của `tien`.

## 3. Kế hoạch test tự động

Không thêm thư viện (Hypothesis đã ghim trong `requirements-dev.txt`). Harness PostgreSQL theo khuôn `tools/pg_v7_harness.py` (PostgreSQL dùng một lần, không mạng).

| Tầng | Vị trí (đề xuất) | Nội dung | AT |
| --- | --- | --- | --- |
| Unit | `tests/test_v7_tien_import.py` | Bộ đọc theo mẫu: cột Có/Nợ, dấu, phân cách nghìn, ô trống, phần lẻ, ngày, dòng tổng; an toàn file | 06.1, 12.1, 12.2, 17.1–17.3 |
| Unit | `tests/test_v7_tien_dedup.py` | Băm file, dấu vân không gồm số dư sau, bội số vùng chồng kỳ, giao dịch giống hệt | 03.1–03.4 |
| Unit | `tests/test_v7_tien_coverage.py` | Liên tục số dư, ngày chưa trọn, ngày thiếu | 04.1, 12.3, 12.4 |
| Unit | `tests/test_v7_tien_projection.py` | Ước tính thận trọng, "có thể về", rời ước tính khi khớp | 16.1, 16.2 |
| Harness | `tools/test_pg_tien_import.py` | Commit nguyên tử, lặp, đồng thời, `IMPORT_PREVIEW_STALE`, đích trùng, hủy lô có nguồn khác; ký coverage cần bằng chứng số dư của người khác, trùng vai có cờ | 02.1–02.4, 03.5, 03.6, 08.6, 13.2 |
| Harness | `tools/test_pg_tien_allocation.py` | Trần, tiền tệ, pháp nhân, phiên bản, lý do, trạng thái suy ra, event; phân bổ không đổi chữ ký coverage; không tổng khác tiền tệ | 04.2, 05.1–05.5, 06.2, 06.3, 07.1–07.3 |
| Harness | `tools/test_pg_tien_chi.py` | Phiên bản, tự duyệt, hạn duyệt, báo thực hiện vượt, chi không đề nghị | 08.4, 15.1–15.4 |
| Harness | `tools/test_pg_tien_grants.py` | Chỉ EXECUTE; login riêng; không quyền chéo `sokhach`; phạm vi khi gọi thẳng | 08.2, 11.1 |
| Harness | `tools/test_pg_tien_isolation.py` | Dấu vân `sokhach` trước/sau; hồi quy ma trận | 01.1, 01.2, 09.1 |
| Harness | `tools/test_pg_tien_ar.py` (P0-c) | Kiểm lại liên kết khi hủy/sửa phiếu; khóa ổn định; loại trừ hai nguồn | 09.2–09.4, 14.1, 14.2 |
| Thuộc tính | `tools/test_pg_tien_ngau_nhien.py` | Chuỗi ngẫu nhiên hạt cố định: nhập chồng kỳ, lặp, hủy lô, phân bổ/gỡ, so mô hình tham chiếu; kiểm I-1, I-4, I-5, I-6 | 03.x, 05.x |
| API | `tests/test_v7_ledger_api.py` (thêm ca) | Cổng riêng, 403, bot chỉ-đọc, module tắt, giới hạn 4 MiB, số thực/trường lạ, log không có nội dung, log truy cập dòng gốc; CSV cộng đúng chênh số dư, vô hiệu ô công thức | 01.3, 08.1, 08.3, 08.5, 08.7, 18.1 |
| Browser | `preview/test-so-tien-browser.js`, `preview/test-duyet-chi-browser.js` | Luồng 5 màn ở 1280×720 và 390px; bàn phím; rỗng, lỗi, tải chậm, mất mạng | luồng B §4–§5 |
| Tĩnh | Quét mã | Không thư viện/địa chỉ ngân hàng; không gọi mạng từ module; không hàm ghi `sokhach` ở P0-a/b | 10.4, 13.1, 04.3 |
| Vận hành | Máy canh, bài khôi phục | Bất biến I-1, I-4, I-6, I-7, I-12; khôi phục khớp; lưới an toàn sổ nợ hiện có xanh | 09.5, 11.2 |
| Snapshot | CI | Snapshot schema `tien` khớp SQL nguồn | 11.3 |
| Shadow | `tests/test_v7_tien_rules.py` | Luật chỉ ghi gợi ý; phiên bản luật; hai ứng viên | 10.1–10.3 |

Trước PR: `npm run check`, `node scripts/check-secrets.js`; harness PostgreSQL chạy tay khi sửa SQL và chạy trong CI.

## 4. KPI đo ở shadow và vận hành

| KPI | Cách đo | Mục tiêu bộ UAT |
| --- | --- | --- |
| Đủ kỳ/tài khoản | Ngày có coverage ký / ngày làm việc | 100% kỳ mẫu |
| Chênh số dư chưa giải thích | Theo ngày | 0 |
| Trùng / bỏ sót trên tập chuẩn | So tập chuẩn kế toán dựng tay | 0 / 0 |
| Độ chính xác và độ phủ gợi ý | Theo số dòng **và** theo giá trị, trên tập đã người xác nhận | Đo, không cam kết tỷ lệ trước khi có mẫu |
| Sai phân bổ nghiêm trọng | Gán nhầm khách/pháp nhân được phát hiện sau | 0 |
| Ngoại lệ | Số, số tiền, tuổi | Không quá hạn không lý do |
| Chi có duyệt trước | Giao dịch ra có đề nghị duyệt trước / tổng | Đo; ngoại lệ đều có kết luận |
| Thời gian thao tác | Tạo đề nghị + duyệt + nhập + review / ngày | So với đo ban đầu ở Discovery |
