# E. P0 Product Requirements Document

Trạng thái: **ĐỀ XUẤT** (Claude, 24/11/2026). Chưa code. P0 chỉ bắt đầu khi các quyết định chặn P0-a ở [I](I-decision-register.md) có người chốt.

[← Mục lục](README.md) · Quy trình: [B](B-quy-trinh-as-is-to-be.md) · Quy tắc: [D](D-business-rules.md) · Kiến trúc: [F1](F1-kien-truc-ky-thuat.md) · Nghiệm thu: [G](G-uat-test.md)

## 1. Vấn đề và mục tiêu

Hôm nay hệ thống không có bằng chứng tiền thật nào; chi được duyệt bằng tin nhắn; số dư phải hỏi trong nhóm ([A §12](A-audit-hien-trang.md#12-rủi-ro-tài-chính-và-vận-hành-hiện-tại)). P0 đạt ba mục tiêu, theo thứ tự:

1. **Biết tiền đã xác minh tới đâu**: số dư theo sao kê của tài khoản thí điểm, ghi rõ cutoff, độ phủ, ai ký.
2. **Phát hiện chi bất thường** sau giao dịch: chi không duyệt, trước duyệt, sai người nhận, vượt số, chi trùng.
3. **Nối với sổ nợ hiện có** mà không ghi công nợ hai lần: tiền về chưa phiếu, phiếu chưa thấy tiền; ghi phiếu từ ngân hàng chỉ khi đã chọn một nguồn ghi.

Không cam kết: realtime, tự động 100%, chống mọi gian lận, thay phần mềm kế toán (v3 §1).

## 2. Phạm vi

P0 chia ba bước có cổng riêng (điều chỉnh so với v3 §9, lý do ở [F2 ADR-TIEN-18](F2-adr.md#adr-tien-18--chia-p0-thành-ba-bước-có-cổng)).

| Bước | Trong phạm vi | Cổng ra |
| --- | --- | --- |
| **P0-a Sổ tiền nền** | Dữ liệu chủ (pháp nhân, tài khoản thí điểm, số dư mở); nhập Excel có xem trước, chống trùng, liên tục số dư, coverage/cutoff; phân loại và phân bổ **thủ công**; ngoại lệ; review cuối ngày hai chữ ký; thẻ số dư cho sếp; vai sổ tiền đóng mặc định; vết; máy canh; xuất CSV | Một tháng lịch sử: đủ dòng, 0 trùng, chênh = 0, nhập lặp/chồng kỳ an toàn; 4 tuần vận hành |
| **P0-b Kiểm soát chi** | Đề nghị chi có phiên bản snapshot; duyệt maker–checker trên điện thoại; báo thực hiện (nhiều lần); ghép chi cuối ngày; ngoại lệ chi; cam kết chi; số dư ước tính thận trọng | Mọi chi trong phạm vi có duyệt trước hoặc ngoại lệ; UAT chi qua |
| **P0-c Nối sổ nợ** | Báo thu dùng lại "khách báo đã chuyển"; đối chiếu chỉ đọc tiền về ↔ phiếu; luật gợi ý shadow; sau QD-16: ghi phiếu có kiểm soát qua hàm hiện có | Tổng khách/tháng/toàn kỳ đúng tập chuẩn; không ghi hai lần; khóa tháng an toàn; ký |

**Ngoài P0:** kết nối ngân hàng dưới mọi hình thức (ràng buộc); chuyển tiền từ webdebit; sổ cái kép; phải trả đầy đủ, three-way matching; tiền khách Trung Quốc, tỷ giá, hạn mức, giữ chỗ; quỹ tiền mặt; liên công ty đầy đủ; nhiều tài khoản và USD (P1); dự báo, lãi lỗ (P2); đọc chat/ảnh để tính tiền; tự áp mức A trước khi đo shadow.

## 3. Vai

| Vai | Quyền chính | Không được |
| --- | --- | --- |
| `tien_xem` | Xem số dư, coverage, giao dịch đã che, báo cáo | Xem dòng gốc, nội dung chuyển khoản |
| `tien_nhap` | Tải, xem trước, commit sao kê; xem dòng gốc | Ký coverage của lô mình nhập (trừ trùng vai có cờ) |
| `tien_phan_bo` | Phân loại, phân bổ, mở/giao ngoại lệ, báo thực hiện chi | Gỡ cờ chi chưa duyệt |
| `tien_review` | Quyết nghi trùng, ký hai chữ ký, mở lại ngày, hủy lô, bỏ ngoại lệ | — |
| `chi_de_nghi` | Tạo, sửa, hủy đề nghị của mình | Duyệt đề nghị của mình |
| `chi_duyet` | Duyệt/từ chối/thu hồi theo ngưỡng; duyệt bù; gỡ cờ chi chưa duyệt | Duyệt đề nghị do mình tạo |
| `tien_quan_tri` | Dữ liệu chủ, cấp vai | Mọi quyền nghiệp vụ ở trên (trừ khi được cấp riêng, có cờ) |

Mỗi vai có phạm vi pháp nhân/tài khoản. Agent vận hành và tài khoản máy không có vai nào ở bảng trên (QD-06).

## 4. Yêu cầu chức năng

### P0-a

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-01 | Khai pháp nhân, tài khoản thí điểm (ngân hàng, 4 số cuối, tiền tệ, người phụ trách), số dư mở có bằng chứng | Must |
| FR-02 | Tải file Excel gốc, chọn tài khoản và kỳ; kiểm mẫu, an toàn file | Must |
| FR-03 | Xem trước: lớp từng dòng, số dư đầu/cuối, chuỗi, chồng kỳ, ngày thiếu, cảnh báo "không phải bản gốc" | Must |
| FR-04 | Quyết dòng nghi trùng trước commit | Must |
| FR-05 | Commit nguyên tử, idempotent, phân loại lại dưới khóa tài khoản | Must |
| FR-06 | Thẻ tài khoản: số dư theo sao kê + mốc dữ liệu ngân hàng + lần tải + trạng thái ký; ngày thiếu | Must |
| FR-07 | Danh sách giao dịch, lọc theo trạng thái `unidentified`/`unapplied`/`partial`/`applied`, `unmatched`/`matched` | Must |
| FR-08 | Phân bổ một hoặc nhiều dòng; tách; gỡ có lý do | Must |
| FR-09 | Ngoại lệ: mở, giao, gia hạn, đóng, bỏ có lý do; hàng đợi theo người | Must |
| FR-10 | Review cuối ngày: ký coverage + số dư; ký đối soát nghiệp vụ; mở lại có lý do | Must |
| FR-11 | Báo cáo cuối ngày (BR-DC7) xem trên điện thoại | Must |
| FR-12 | Hủy lô theo BR-IM13 | Must |
| FR-13 | Xuất CSV theo kỳ cho kế toán | Should |
| FR-14 | Luật gợi ý shadow mức B/C, lưu gợi ý để đo | Should |
| FR-15 | Tóm tắt tuần cho chủ doanh nghiệp: trùng vai, ngoại lệ quá hạn, chỉnh sửa sau ký | Must khi trùng vai |

### P0-b

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-20 | Tạo đề nghị chi từ hồ sơ có sẵn (chuyến, container, xe, dòng Đội xe) hoặc loại chi tự do có lý do | Must |
| FR-21 | Mã đề nghị, nút chép nội dung chuyển khoản | Must |
| FR-22 | Phiên bản snapshot; sửa trọng yếu tạo phiên bản mới, mất duyệt | Must |
| FR-23 | Duyệt/từ chối (lý do)/thu hồi trên điện thoại; chặn tự duyệt ở máy chủ | Must |
| FR-24 | Xác minh người nhận mới/đổi tài khoản, ghi kết quả | Must |
| FR-25 | Báo thực hiện nhiều lần; `failed`/`returned` | Must |
| FR-26 | Cuối ngày ghép chi với đề nghị/báo thực hiện; ngoại lệ chi không duyệt, sai người nhận, vượt số, trùng | Must |
| FR-27 | Cam kết chi và số dư ước tính thận trọng hiển thị riêng | Should |

### P0-c

| ID | Yêu cầu | Ưu tiên |
| --- | --- | --- |
| FR-30 | Báo thu = "Khách báo đã chuyển" sẵn có; hiện trạng thái chờ xác minh và giao dịch ghép được | Must |
| FR-31 | Đối chiếu chỉ đọc: tiền về đã phân bổ cho sổ ↔ phiếu `THU TIỀN`; ngoại lệ cho team công nợ | Must |
| FR-32 | Liên kết giao dịch ↔ phiếu (sổ, `pid`), tự kiểm lại khi phiếu bị hủy hoặc sửa | Must |
| FR-33 | Sau QD-16: ghi phiếu từ phân bổ qua `record_receipt`, khóa lặp ổn định, loại trừ máy theo Sheet cho sổ đó | Could (chỉ khi QD-16 = B) |
| FR-34 | Sổ khách hiện liên kết nguồn tiền của phiếu và khoản đang chờ xác minh | Should |

## 5. Yêu cầu phi chức năng

| ID | Yêu cầu |
| --- | --- |
| NFR-01 Đúng | Mọi bất biến I-1…I-14 ([F1 §6](F1-kien-truc-ky-thuat.md#6-bất-biến-tài-chính)) kiểm trong hàm SQL và máy canh |
| NFR-02 Bảo mật | Vai đóng mặc định, thiếu cấu hình thì module tắt; DB login riêng cho module; không lưu số tài khoản đầy đủ ngoài file gốc được bảo vệ (QD-08); không gửi dữ liệu ra ngoài |
| NFR-03 Riêng tư | Dòng gốc, nội dung, tên đối ứng chỉ vai nhập/review; truy cập dòng gốc được ghi log (ai, lúc, tài khoản, không ghi nội dung) |
| NFR-04 Vết | Mọi lệnh ghi có event chỉ thêm: người, loại người làm, trước → sau, khóa lệnh |
| NFR-05 Hiệu năng | Xem trước và commit một file vài nghìn dòng trong giới hạn 15 giây/câu lệnh hiện có; vượt thì chia lô |
| NFR-06 Sẵn sàng | Theo `hao` hiện tại; sao lưu có schema mới; khôi phục thử khớp số dư; RTO được đo trước P0-c |
| NFR-07 Dễ dùng | Người dùng trên 40 tuổi; màn máy tính 1280×720, điện thoại 390px; chữ thân ≥ 16px, vùng bấm ≥ 40px; trạng thái có chữ, không chỉ màu ([UX](../../docs/ux-guidelines.md)) |
| NFR-08 Ít nhập | Đề nghị lấy dữ liệu có sẵn; báo thu tùy chọn; không thêm bước bắt buộc ngoài nhập sao kê và duyệt |
| NFR-09 Không phụ thuộc mới | Thư viện chuẩn Python, JS thuần như hiện có; thêm thư viện chỉ khi QD-07 cần (bộ đọc `.xls`) |
| NFR-10 Lưu trữ | Theo QD-08; không xóa dữ liệu tài chính trong đường lùi |

## 6. Màn hình P0 (tối thiểu: 5 màn mới + 2 chỗ sửa)

| Màn | Thiết bị | Ai | Bước |
| --- | --- | --- | --- |
| **Sổ tiền** — tài khoản, nhập + xem trước, giao dịch, nguồn file | 1280×720 | Kế toán, review | P0-a |
| **Đối soát cuối ngày** — gợi ý, phân bổ, ngoại lệ, hai chữ ký | 1280×720 | Kế toán, review | P0-a |
| **Tổng quan tiền** — số dư theo cutoff, chưa rõ, chi bất thường, (P0-b) cam kết, ước tính | 390px + máy tính | Sếp | P0-a |
| **Việc của tôi** — đề nghị của tôi, báo thực hiện, ngoại lệ được giao | 390px | Nhân viên, kế toán | P0-b |
| **Duyệt chi** — thẻ đề nghị, snapshot, lịch sử, duyệt/từ chối | 390px | Người duyệt | P0-b |
| Sửa: **Sổ khách** — khoản chờ xác minh, nguồn tiền của phiếu | có sẵn | Team công nợ | P0-c |
| Sửa: **menu** — mục Tiền theo vai | có sẵn | — | P0-a |

Không tạo màn "Báo thu" riêng ở P0 (dùng nút có sẵn ở sổ khách). Mỗi màn một mục tiêu, theo thói quen thiết kế đã chốt của repo.

## 7. Bất biến tài chính

Danh sách và nơi kiểm: [F1 §6](F1-kien-truc-ky-thuat.md#6-bất-biến-tài-chính). Tóm tắt: một giao dịch một lần; Σ phân bổ ≤ số tiền; số dư = mở + vào − ra của giao dịch còn hiệu lực; chuỗi liên tục trước khi ký; tách pháp nhân/tiền tệ; bảng chỉ thêm; sổ nợ không đổi trước P0-c; khóa lặp; duyệt đúng phiên bản; người duyệt ≠ người đề nghị; số dư ước tính không trộn vào số dư xác nhận.

## 8. Tiêu chí nghiệm thu

- **AC-a1** Một tháng lịch sử của tài khoản thí điểm: số dòng file = mới + trùng xác nhận + lỗi đã sửa; 0 trùng; chênh = 0 mọi ngày đã ký.
- **AC-a2** Nhập lặp, chồng kỳ, đồng thời, ngắt giữa chừng: không thêm tiền giả, không mất giao dịch (G: U01–U05, UA-01…UA-05).
- **AC-a3** Quyền: login không vai → 403 mọi route tiền; ID ngoài phạm vi → từ chối khi gọi thẳng; bot chỉ-đọc bị chặn; thiếu cấu hình → module tắt.
- **AC-a4** Sổ nợ không đổi (dấu vân bảng `sokhach` và tổng từng khách trước/sau); lưới an toàn hiện có xanh.
- **AC-a5** Bốn tuần vận hành: sao kê không cũ quá 2 ngày làm việc; ngoại lệ quá hạn = 0 hoặc có lý do; sếp xác nhận đọc được thẻ số dư.
- **AC-b1** Mọi giao dịch chi trong phạm vi: có đề nghị duyệt trước, hoặc ngoại lệ có kết luận.
- **AC-b2** Tự duyệt bị chặn ở máy chủ; sửa sau duyệt buộc duyệt lại; nhiều lệnh cho một đề nghị không bị báo trùng (U12–U16, U22).
- **AC-c1** Đối chiếu shadow 1 tháng: tổng theo khách/tháng/toàn kỳ khớp tập chuẩn; 0 gợi ý sai được người xác nhận.
- **AC-c2** Nếu bật ghi phiếu: 0 phiếu ghi hai lần qua thử lặp, đồng thời, bật nhầm hai nguồn (UA-06…UA-09).
- **AC-all** `npm run check`, quét secrets, harness PostgreSQL mới xanh; kế toán và sếp tự đi hết luồng trên `hao`.
