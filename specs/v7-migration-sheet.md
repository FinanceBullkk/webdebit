# V7 — chuyển và làm sạch dữ liệu từ Sheet `2026 DEBIT` (ĐỀ XUẤT)

Trạng thái: **ĐỀ XUẤT** (Claude, 19/10/2026). Là bước nối giữa [thiết kế backend](v7-backend/thiet-ke.md) và dữ liệu thật. **Không chạy gì lên `hao`, không ghi Google Sheet, không đưa dữ liệu thật vào repo.** Spec này không chứa tên khách, số tiền thật hay mã Sheet.

## 1. Đã chốt (người dùng, 19/10/2026)

- **Nguồn dữ liệu hiện tại vẫn là Sheet `2026 DEBIT`** (nguồn sống). `HAO_CHAU` là bản thử làm sạch ngày 13/10/2026 và **chưa được cập nhật thêm** từ đó; nó là tài liệu tham chiếu, không phải nguồn cho lần chuyển này.
- **Phương án 3 (lai):** số dư đầu theo khách và theo tháng còn nợ; chi tiết từng dòng chỉ nhập cho các tháng còn nợ hoặc tháng đang mở; tháng cũ đã trả đủ chỉ để xem, không cộng lại.
- **Sau chuyển đổi web không liên kết với Sheet nữa.** Sheet trở thành kho lưu chỉ đọc kèm bản chụp có mã băm.
- Tháng cũ không truy ngược từng dòng được; cách làm trước dựa vào **tổng nợ và tổng thu** vì tổng đối chiếu được.

## 2. Nguồn và phạm vi

| Nguồn | Vai trò | Ghi chú |
| --- | --- | --- |
| `2026 DEBIT` (≈252 tab; 241 là sổ khách) | Nguồn duy nhất cho lần chuyển | Mỗi tab một khách (hoặc khách theo loại hàng, đường bộ, bán cước); bố cục cột KHÁC NHAU giữa các tab; ngày có thể bị đảo ngày/tháng; có ô công thức không có giá trị lưu sẵn trong bản xuất. |
| `HAO_CHAU` | Tham chiếu: quy tắc đã dùng, danh sách ngoại lệ (tab `12`, `15`) | Không dùng làm dữ liệu. Phần đã làm sạch có thể dùng để **so** với kết quả mới. |
| Hồ sơ 13/10 (`docs/02, 04, 05, 11`; capture 13/10; engine `pilot/reconcile.py`) | Kết quả đối soát lần trước: 155 khách, 65.051.673.578 VND, chênh 600 VND | Tham chiếu lịch sử, không phải bằng chứng cho dữ liệu hôm nay. |

Dữ liệu thô, bản xuất và báo cáo chi tiết nằm **ngoài repo** (`D:\webdebit\captures\…`), không `git add`.

## 3. Quy trình đề xuất

1. **Đóng băng nguồn** tại thời điểm chuyển: tải bản `.xlsx`, ghi SHA-256, thời điểm, số tab/dòng. Từ lúc này không nhập thêm vào Sheet (một nơi nhận giao dịch).
2. **Dựng lại từ sổ gốc** bằng trình phân tích mới (không dựa vào `HAO_CHAU`): dò bố cục cột từng tab, nhận diện khối `THÁNG m.yyyy`, tách dòng chuyến, dòng thu, dòng tổng.
3. **Lấy mỏ neo:** cột `SỐ CÒN PHẢI THU CUỐI THÁNG` (và cột số thu) mà người giữ sổ đã ghi, theo từng khách × tháng.
4. **Phân loại từng dòng nguồn** vào đúng một nhóm: nhập, nhập kèm cờ, cách ly (chờ người quyết), bỏ qua có lý do. Không dòng nào rơi im lặng (mọi dòng nguồn = nhập + cách ly + bỏ qua).
5. **Dựng dữ liệu V7:**
   - Số dư đầu theo khách × tháng cho các tháng còn nợ tại mốc chuyển.
   - Chi tiết dòng chuyến và khoản thu cho các tháng còn nợ và tháng đang mở; thành tiền lấy theo ô tổng của sổ gốc (xem 5.2).
   - Tháng cũ đã trả đủ: chỉ lưu tham chiếu, đánh dấu "lịch sử, không cộng lại".
6. **Đối soát (mục 6)**, xuất báo cáo từng khách và từng tháng, kèm mọi chênh lệch.
7. **Diễn tập trên bản sao** cơ sở dữ liệu cô lập (không phải `hao`), người dùng tự xem số của các khách mẫu.
8. **Chuyển thật** theo gate riêng: đóng băng Sheet, nhập, đối soát lại, người dùng ký nhận. Có phương án quay lại đã diễn tập.

## 4. Các lớp lỗi dữ liệu và quy tắc đề xuất

Cột "Trạng thái": ĐỀ XUẤT (tôi đề xuất, chưa ai chốt) hoặc CÒN MỞ (cần người dùng quyết).

| Lỗi | Dấu hiệu đã thấy | Quy tắc | Trạng thái |
| --- | --- | --- | --- |
| Ngày đảo ngày/tháng | Ô ngày thật lưu `8/4` nhưng hiển thị `4/8` trong khối tháng 8 (≈79% ô ngày thật cần đảo mới khớp tháng của khối) | Ngày = theo tháng của khối; giữ cả hai cách đọc; dòng không khớp cách nào chuyển vào danh sách cách ly | CÒN MỞ |
| Số tiền sai định dạng | `46,000,000` / `46.000.000` / dạng chữ / ký tự thừa | Chuẩn hóa về số nguyên VND; không đoán khi không phân tích được → cách ly | ĐỀ XUẤT |
| Trống thành 0 | Bản thử cũ ghi 0 cho đơn giá trống | Trống giữ là "chưa biết" (NULL), không ghi 0 | ĐỀ XUẤT (khớp quy tắc nền) |
| Tổng ≠ đơn giá + phí | Hàng nghìn dòng | Thành tiền = **ô tổng của sổ gốc**; đơn giá và phí chỉ là giải thích; lệch ghi cờ | ĐỀ XUẤT (khớp quyết định 13/10, xung đột công thức V7 — xem 5.2) |
| Giá nằm ở cột phí | Đơn giá trống, ba khoản ở ba cột phí, tổng có số | Giữ tổng của sổ gốc; không chuyển giá giữa các cột trừ khi bố cục tab đã được xác nhận | CÒN MỞ |
| Chưa có giá / tổng 0 | Hàng trăm dòng | Cách ly, cờ "thiếu giá" (cam trong V7); không tính vào nợ cho tới khi có giá | ĐỀ XUẤT (khớp 13/10) |
| Dòng không container, không ngày, có số tiền (phí không ghi rõ gốc; ví dụ một dòng 1.500.000 dưới chuyến cuối của một khối) | **Cộng vào phát sinh của tháng khối như dòng phí lẻ**, giữ nguyên ghi chú gốc nếu có. Không thêm cờ hay bước xử lý riêng | ĐÃ CHỐT (người dùng, 19/10/2026: "cộng vào phí phát sinh, không cần phức tạp hóa") |
| Phí lẻ không container | Rất ít dòng | Nhập như dòng phí lẻ của V7 (cộng vào phát sinh, không đếm là chuyến) | ĐỀ XUẤT |
| Thu 2026 trong khối cũ | ≈60 khoản | Ghi theo ngày thu thật hay theo khối? | CÒN MỞ |
| Hình thức thu từ ghi chú tự do | `CAN TRU USD`, `TT`… | Ánh xạ về bốn hình thức; ghi chú gốc giữ nguyên; không tự nâng thành "thực nhận" | CÒN MỞ |
| Một khách nhiều tab | Tab thường và tab đường bộ/bán cước của cùng khách | Một sổ = một tab, hay gộp theo khách? | CÒN MỞ |
| Tên khách lệch | Khoảng trắng, hoa/thường, ký tự | Chuẩn hóa nhẹ; không gộp mờ (fuzzy) khi chưa được duyệt | ĐỀ XUẤT |
| Tab không phải sổ khách | `TONG`, `Sheet..`, bản sao | Bỏ qua có lý do, ghi vào báo cáo | ĐỀ XUẤT |
| Nghi trùng dòng | Cùng khách+container+ngày | Giữ cả hai, cờ, người quyết; không tự xóa | ĐỀ XUẤT |
| Số dư thiếu giá trị lưu | Ô công thức không có cache trong bản xuất | Tính lại từ ô đầu vào, ghi rõ "tính lại"; không coi trống là 0 | ĐỀ XUẤT |

Giữ nguyên các cờ NO_BASELINE, chênh lịch sử 600 VND và khoản thiếu giá (AGENTS.md); không làm sạch cho tới khi chúng biến mất.

## 5. Điều kiện cho V7 và schema

1. **Dòng lịch sử không cộng lại.** V7 hiện cộng mọi dòng đang hiển thị. Với dữ liệu thật cần dòng được đánh dấu "lịch sử" hiển thị nhưng không vào tổng, và số dư đầu theo khách × tháng. Hai việc này **chưa có** trong `schema-draft.sql` và model V7 (CÒN MỞ cho bước thiết kế).
2. **Thành tiền:** V5 (17/10/2026) chốt "đơn giá + ba loại phí"; dữ liệu thật và quyết định 13/10 dùng ô tổng của sổ gốc, và 1.773/6.552 dòng lệch hai công thức. Đề xuất: dòng lịch sử giữ tổng gốc; dòng nhập mới trên web dùng đơn giá + phụ phí. Cần người dùng xác nhận.
3. **Mã chuyến:** quyết định 15/10/2026 (booking + số container) chỉ áp cho chuyến có booking; phần còn lại CHỜ KIỂM; phải quyết trước khi dùng mã chuyến làm khóa.

## 6. Cổng nghiệm thu (gate)

Chưa đạt mục nào thì chưa chuyển thật.

- [ ] Phủ 100%: mọi dòng nguồn thuộc phạm vi = nhập + cách ly + bỏ qua có lý do (số khớp tổng dòng nguồn).
- [ ] Tổng nợ **từng khách** khớp mỏ neo của người giữ sổ (hoặc mỗi chênh lệch có giải thích bằng văn bản), tính đến từng đồng; không làm tròn để ép khớp.
- [ ] Tổng nợ toàn bộ, tổng thu, tổng phát sinh khớp nguồn; chênh lịch sử 600 VND được ghi, không bị ẩn.
- [ ] Mọi dòng cách ly có người quyết hoặc lý do loại; không dòng nào vào số dư khi chưa rõ.
- [ ] Mỗi khoản có nguồn (tab + dòng nguồn) để tra ngược.
- [ ] Diễn tập: nạp vào bản sao cô lập, ra cùng số; chạy lại cho cùng kết quả (tất định).
- [ ] Người dùng tự xem các khách mẫu và xác nhận.
- [ ] Chỉ chuyển thật khi có gate triển khai riêng, người ký nhận, kế hoạch quay lại.

## 7. Phân công

- Phát triển bộ phân tích, trích mỏ neo, báo cáo đối soát: Codex (script ngoài repo trong giai đoạn thăm dò; khi ổn định thì công cụ không chứa dữ liệu mới vào repo).
- Kiểm chéo độc lập: agent thứ hai (Hermes `cx/gpt-6-luna`) trên cùng bản xuất, chỉ đọc.
- Review: Claude; chốt quy tắc: người dùng.

## Đã chốt thêm (người dùng, 19/10/2026)

- Định nghĩa "tháng còn nợ" (mục CÒN MỞ 3): mọi tháng có số còn phải thu > 0 theo người giữ sổ, cộng tháng đang mở. **Phải kiểm tra thêm công thức bị thiếu hoặc bị ghi đè trong sổ gốc** (ô tổng, ô còn phải thu cuối tháng, ô tổng thu) trước khi tin các mỏ neo.
- Quy tắc ngày bị đảo (CÒN MỞ 1): chấp nhận "ngày theo tháng của khối"; dòng không khớp cách nào vẫn vào danh sách cách ly để người xem.
- Thành tiền (CÒN MỞ 2): dòng lịch sử giữ tổng của sổ gốc; dòng nhập mới trên web dùng đơn giá + phụ phí.
- Người dùng xác nhận (19/10/2026) 12 tab đã hết nợ (số dư mỏ neo = 0): A HUNG- CHUỐI, KIM HY, FARMY LOG, TNC- DỪA, BÁN CƯỚC NEWAY, DUONG BO LIJIE 李姐 HTH257, DUONG BO -TNC, DUONG BO KIROS HTH194, DUONG BO ALEX HTH211, DUONG BO ALEX HTH223, DUONG BO ALEX HTH235, DUONG BO FENG ZONG 冯总 HTH215. Đây là xác nhận bằng lời của chủ nghiệp vụ, chưa phải bằng chứng từ dữ liệu; vẫn đối chiếu dữ liệu của các tab này khi chuyển.
- Số còn phải thu `KK - DỪA` = 2.587.705.877 (ô P654) được người dùng xác nhận còn nợ (19/10/2026), dù tab có nhiều ô công thức nghi.
- **Chia số cộng dồn thành nợ từng tháng (người dùng chọn phương án A, 19/10/2026):** mỏ neo "còn phải thu cuối tháng" của sổ gốc là số cộng dồn; số dư đầu theo tháng được tính bằng cách chạy lại quy tắc thu trừ nợ cũ trước trên các khối tháng của từng khách. Cách chia theo tháng là quy ước; **tổng các tháng phải bằng đúng mỏ neo của khách**, khách nào không khớp thì cách ly để người xem.
- Phân vai: Codex làm bộ phân tích, Hermes kiểm chéo, Claude review.

## CÒN MỞ cần người dùng quyết

1. Quy tắc ngày bị đảo (mục 4) và ai xem các dòng không khớp.
2. Thành tiền theo tổng gốc hay theo đơn giá + phí (mục 5.2).
3. Định nghĩa "tháng còn nợ": mọi tháng có số còn phải thu > 0 theo người giữ sổ, cộng tháng đang mở; có cần thêm vài tháng gần nhất không.
4. Thu trong khối cũ, hình thức thu từ ghi chú, một khách nhiều tab (mục 4).
5. Mốc chuyển (ngày giờ đóng băng) và người ký nhận.
6. Dòng lịch sử hiển thị thế nào trong V7 (đề xuất: hiện đủ, đánh dấu "lịch sử, không cộng lại").

## Câu hỏi mở

- <Agent hoặc reviewer ghi vào đây.>
