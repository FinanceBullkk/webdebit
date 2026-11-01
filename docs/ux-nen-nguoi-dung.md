# Nền UX · bước 01: người dùng và mục tiêu (1/11/2026)

Trạng thái: phần đo và phần hỏi người dùng **XONG** (1/11/2026); mục tiêu M1–M5 **ĐÃ CHỐT** 1/11/2026 ([`UX-NEN-01`](decisions/ux-nen-01.md)). Đây là bước 01 trong thứ tự UX người dùng đặt ra ngày 1/11/2026: người dùng và mục tiêu kinh doanh → cấu trúc thông tin và luồng → dễ dùng và tương tác → giao diện → kiểm với người dùng. Chưa có thiết kế nào ở đây; tài liệu chỉ ghi điều đã đo được, giả thuyết cần kiểm và câu hỏi còn thiếu. Bổ sung cho mục "CÒN MỞ" của [hướng dẫn UX](ux-guidelines.md) (bỏ trống từ 16/10/2026) và đặt nền lại cho [audit UX 31/10](ux-audit-2026-10-31.md), vốn đo giao diện trước khi biết ai dùng.

## 1. Nguồn và giới hạn

- **Số liệu `hao`, ĐÃ KIỂM CHỨNG 1/11/2026.** DB `webdebit_v7`, đọc trong phiên `default_transaction_read_only=on`, không ghi gì, không đụng DB legacy.
  - Bảng `sokhach.event` ghi mọi thao tác ghi, kèm người làm.
  - `sokhach.legacy_row` là dữ liệu Sheet nạp lúc mốc 21/10.
  - `v_outstanding_month` cho nợ còn lại theo tháng.
  - `reminder_log` là nhật ký nhắc nợ.
- **Không đo được ai đã *xem* web.** API không ghi nhật ký truy cập. `event` chỉ có thao tác ghi; mở trang, xem sổ, xem Tổng quan không để lại dấu.
- **Số tháng 9–10 chưa đủ.** Dữ liệu Sheet dừng ở mốc nạp 21/10. Sau mốc, thay đổi trên Sheet chỉ vào web khi có người duyệt (hàng chờ). Vì vậy nợ trên web không trừ các phiếu thu từ 21/10 tới nay.
- Tài liệu chỉ ghi số tổng hợp, không có tên khách hay tài khoản (repo public).

## 2. Khối lượng nghiệp vụ thật (từ Sheet đã nạp)

| Tháng 2026 | Chuyến | Phiếu thu | Khách có chuyến | Khách có trả | Phát sinh (tỷ) | Thu (tỷ) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 463 | 65 | 46 | 39 | 17,29 | 18,31 |
| 2 | 483 | 48 | 40 | 36 | 18,14 | 17,45 |
| 3 | 798 | 102 | 51 | 49 | 31,91 | 30,61 |
| 4 | 660 | 66 | 50 | 45 | 28,62 | 26,72 |
| 5 | 839 | 87 | 52 | 44 | 30,39 | 28,98 |
| 6 | 981 | 76 | 48 | 45 | 26,31 | 25,07 |
| 7 | 1.007 | 102 | 65 | 54 | 38,87 | 31,87 |
| 8 | 924 | 90 | 57 | 43 | 36,18 | 19,61 |
| 9 (thiếu) | 589 | 32 | 40 | 20 | 28,33 | 3,84 |
| 10 (tới 21/10) | 126 | 4 | 17 | 4 | 5,80 | 0,35 |

Đọc ra:

- **Người nhập:** mùa cao điểm khoảng 800–1.000 chuyến một tháng, tức 35–40 chuyến mỗi ngày làm việc. Phiếu thu ít hơn nhiều, khoảng 65–100 phiếu một tháng (3–4 phiếu mỗi ngày). Nhập chuyến là việc chiếm khối lượng; ghi phiếu thu là việc ít nhưng đụng thẳng tới tiền.
- **Khách:** sổ có 236 khách, nhưng mỗi tháng chỉ 40–65 khách có chuyến. Tháng 9–10 có 3 khách từ 100 chuyến trở lên, 4 khách 30–99 chuyến, 3 khách 10–29 chuyến và 30 khách dưới 10 chuyến.
- **Nợ trên web lúc đo:** 67 khách còn nợ, tổng 67,90 tỷ (cao hơn thực tế vì thiếu phiếu thu sau 21/10).
  - 5 khách chiếm **70%** số nợ, 10 khách chiếm **81%**, 20 khách chiếm **90%**.
  - Theo tháng phát sinh: T10–T11 là 8,79 tỷ (14 khách); T8–T9 là **43,48 tỷ** (36 khách); T5–T7 là 8,95 tỷ (20 khách); trước T5 là 6,67 tỷ (23 khách).

## 3. Web đang được dùng thế nào

Trong 10 ngày từ 21/10 tới 30/10, `event` có 6.555 dòng. Bỏ các script hệ thống (nạp mốc, chép shipper từ Sheet, chuyển phụ phí) thì còn **204 thao tác của người, tất cả từ một tài khoản** (tài khoản chủ dự án). Các thao tác này chạm tối đa 6 trong 236 sổ. Thao tác cuối cùng là ngày 30/10.

| Thao tác | Số lần | Ghi chú |
| --- | ---: | --- |
| Giải quyết lệch Sheet ↔ web | 69 | 63 lần chọn "theo Sheet", 6 lần "giữ web"; chủ yếu shipper và nơi đến |
| Khóa / mở khóa tháng | 31 | 17 lần mở, 14 lần khóa; phần lớn khóa lại **trong vòng 1 phút** sau khi mở |
| Sửa dòng sổ gốc | 30 | |
| Sửa giá | 27 | 3 sổ, 28–29/10 |
| Dán chuyến | 13 | Trên web có 51 chuyến, đều đã xác nhận |
| Ghi phiếu thu | 5 | **Cả 5 đã hủy**, không ghi lý do (phiếu thử) |
| Xóa chuyến, xóa điều chỉnh, phụ phí, bảng giá, ảnh chứng từ | 29 | Đa số trong 1 sổ |
| Nhắc nợ (Copy tin nhắc) | 1 | 30/10 |

## 4. Điều rút ra (ĐÃ KIỂM CHỨNG bằng số trên)

1. **Chưa có người dùng thật ngoài chủ dự án.** Không có thao tác ghi nào của người nhập hay người đòi nợ. Mọi quyết định giao diện tới nay ("người trên 40 tuổi", "người nhập cuối ngày") chưa được chính người đó thử.
2. **Web đang chậm hơn Sheet.** Từ 21/10, phiếu thu và chuyến mới trên Sheet không tự vào sổ web. Sổ web vì vậy không đủ tin để dùng thay Sheet, và người dùng không có lý do mở nó. Đây là vòng luẩn quẩn: không ai dùng thì không ai duyệt, không ai duyệt thì sổ không đúng.
3. **Phần lớn việc ghi trên web là làm lại việc của Sheet.** 63 trên 69 lần lệch chọn "theo Sheet". Trong giai đoạn song song, bước "giải quyết lệch" gần như chỉ là bấm xác nhận điều Sheet đã nói.
4. **Khóa tháng đang là bước cản khi sửa.** Mẫu "mở khóa, sửa, khóa lại trong 1 phút" lặp nhiều lần. Có thể một phần là thử nghiệm, nhưng đúng là điều người nhập sẽ gặp khi sửa tháng cũ.
5. **Giá trị tiền dồn vào ít khách và nợ cũ.** 10 khách giữ 81% nợ; 59,10 tỷ (87%) là nợ phát sinh từ tháng 9 trở về trước.

## 5. Giả thuyết cần kiểm (chưa chứng minh)

- **G1 · Việc của web.** Với công ty, việc chính của web có thể là *biết ai nợ, nợ từ bao giờ, ai cần đòi, số nào đang sai*. Còn chép từng dòng chuyến như Sheet là phương tiện, chưa phải mục tiêu. Kiểm bằng câu hỏi 4 và 5 ở mục 6.
- **G2 · Đối tượng quan trọng nhất.** Khoảng 10 khách lớn và nợ tháng 8–9 quan trọng với tiền hơn 236 sổ chi tiết. Nếu đúng thì màn hay dùng nhất phải là danh sách khách lớn và nợ cũ, còn sổ khách chỉ là nơi soi chi tiết.
- **G3 · Lý do chuyển sang web.** Người nhập chỉ chuyển sang web khi web bớt việc cho họ so với Sheet (nhập chuyến theo lô, tự tính giá, tự phân bổ thu), không phải khi web đẹp hơn. Kiểm bằng câu hỏi 2 và 7.
- **G4 · Song song.** Trong lúc song song, bước giải quyết lệch có thể tự lấy theo Sheet và chỉ hỏi người khi khác tiền. Đây là chuyện của bước 02, ghi lại để không quên.

## 6. Người dùng trả lời (chat 1/11/2026)

| Câu hỏi | Trả lời |
| --- | --- |
| Ai đang dùng web | Ngoài chủ dự án có người **mở xem**, không ghi: sếp (tổng nợ, ai nợ nhiều; nợ quá hạn, ai cần đòi) và người đòi nợ (lấy tin nhắc). Người nhập chưa dùng. |
| Web có giá trị nhất khi nào | **Hết ghi nhầm tiền.** "Mục tiêu là thay thế Sheet, nên phải đảm bảo những data input của chúng ta chuẩn 100%." |
| Việc tốn thời gian của người nhập | Cả bốn việc: nhập chuyến và giá, ghi và khớp tiền thu, làm debit note, tra nợ khi bị hỏi. |
| Chỗ từng sai tiền | Đơn giá / phụ phí; phiếu thu nhầm (khách, tháng, số tiền); trùng hoặc sót container. |
| Sau khi bỏ Sheet, nhập chuyến ở đâu | Đồng bộ lô container từ booking sheet. Giá thì nhập tay hoặc web tự tính, tùy khách. |
| Quan sát người nhập | Chưa được. Tạm dùng số liệu và câu trả lời này. |

Kết luận cho G1–G3:
- **G1 sửa lại.** Việc chính của web là **thay Sheet với dữ liệu vào đúng 100%**. Phần "biết ai nợ, ai cần đòi" là việc của người xem, đứng sau độ đúng.
- **G2 giữ, nhưng cho người xem.** Sếp và người đòi nợ cần khách lớn và nợ quá hạn.
- **G3 xác nhận.** Đường vào của chuyến là booking sheet chứ không phải gõ tay, nên chỗ dễ sai nằm ở đồng bộ, giá và phiếu thu, không nằm ở bố cục sổ.

## 7. Mục tiêu đo được (ĐÃ CHỐT, `UX-NEN-01`)

Mục tiêu kinh doanh: **bỏ được Sheet mà không mất độ đúng.** Đo bằng năm chỉ số, mỗi chỉ số kiểm được bằng máy:

| # | Chỉ số | Mức đạt | Hôm nay |
| --- | --- | --- | --- |
| M1 | Tổng nợ từng khách web = Sheet (đối soát cuối ngày, [`SONG-SONG-01`](decisions/song-song-01.md)) | 236/236 khách khớp, liền một tháng | Chưa đo được: web thiếu dữ liệu sau 21/10 |
| M2 | Mỗi container trong booking sheet có đúng một chuyến trên web | 0 trùng, 0 sót | Chưa có phép đối chiếu tự động |
| M3 | Chuyến tính tiền có giá đúng nguồn (bảng giá của khách hoặc nhập tay có người làm) | 0 chuyến thiếu giá lọt vào tổng; giá lệch bảng giá đều được báo | Có "chưa có giá", chưa báo lệch bảng giá |
| M4 | Phiếu thu ghi đúng khách, đúng số tiền | 0 phiếu phải hủy vì ghi nhầm; phiếu nghi trùng (cùng khách, cùng số tiền, gần ngày) được hỏi lại | Có bước xem lại tổng nợ, chưa kiểm trùng |
| M5 | Độ tươi: web chậm hơn booking sheet / Sheet thu tiền | ≤ 1 ngày | Khoảng 11 ngày (từ 21/10) |

Mục tiêu phụ cho người xem: sếp trả lời được "tổng nợ, ai nợ nhiều, ai quá hạn, ai cần đòi" ở một màn; người đòi nợ copy tin nhắc có số đúng (đúng theo M1).

## 8. Việc thật của từng vai

| Vai | Hôm nay | Việc | Tần suất | Chỗ dễ sai |
| --- | --- | --- | --- | --- |
| Người nhập | Làm trên Sheet, chưa dùng web | Đưa lô container từ booking sheet vào sổ khách | 35–40 chuyến/ngày, 40–65 khách/tháng | Trùng, sót container |
| | | Gán giá: tự tính theo bảng giá hoặc nhập tay, tùy khách; thêm phụ phí | Theo từng chuyến | Sai đơn giá, thiếu/thừa phụ phí |
| | | Ghi phiếu thu và khớp với nợ | 3–4 phiếu/ngày | Nhầm khách, nhầm tháng, nhầm số tiền |
| | | Làm debit note gửi khách | Cuối tháng, mỗi khách có chuyến | Số không khớp sổ |
| | | Tra nợ khi khách hoặc sếp hỏi | Chưa đo | Trả lời theo số cũ |
| Sếp | Mở xem web | Xem tổng nợ, khách nợ nhiều, nợ quá hạn, ai cần đòi | Chưa đo (không có nhật ký xem) | Tin vào số web khi web đang thiếu dữ liệu |
| Người đòi nợ | Mở xem web | Lấy tin nhắc gửi khách | 1 lần ghi nhận (30/10) | Nhắc theo số chưa trừ phiếu thu mới |
| Chủ dự án | Người duy nhất ghi trên web | Thử, sửa, cấu hình | 204 thao tác / 10 ngày | — |

Hệ quả: hôm nay sếp và người đòi nợ đang đọc số của một sổ chậm khoảng 11 ngày. Đây là rủi ro độ đúng có thật ngay lúc này, trước mọi chuyện giao diện.

## 9. Bước tiếp

- Người dùng chốt hoặc sửa mục tiêu M1–M5 ở mục 7.
- **Bước 02 (cấu trúc thông tin và luồng):** vẽ đường đi của dữ liệu trước rồi mới tới màn: booking sheet → chuyến → giá → phiếu thu → nợ → người xem.
  - Ở mỗi chặng ghi rõ máy kiểm gì (M2–M4) và người phải làm gì.
  - Từ đó xét từng màn (6 trang và 4 thẻ của trang khách) xem giữ, gộp hay bỏ.
  - Câu hỏi trọng tâm: chặng nào cần người, chặng nào máy tự làm được. Ví dụ, 63/69 lần lệch đều chọn "theo Sheet".
- Bản bấm thử "một tháng trên màn hình" ([mockups/so-khach-mot-thang](../cong-no-web-handoff/preview/mockups/so-khach-mot-thang/index.html), dữ liệu giả) để đó tới bước 04. Vạch phần nhìn thấy đã sửa từ 720px về 560px theo số đo thật (Chrome chỉ thấy khoảng 1280×560).
- Muốn đo được ai *xem* web thì cần thêm đếm lượt mở trang. Đây là đổi backend: ĐỀ XUẤT, chờ người dùng quyết định.
