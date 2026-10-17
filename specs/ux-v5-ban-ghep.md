# V5 — bản ghép ba hướng, và khung còn thiếu

Trạng thái: **ĐỀ XUẤT** (Claude, 17/10/2026). Dùng kèm [brief](ux-brief-so-cong-no.md); brief vẫn là nguồn cho nghiệp vụ, quy tắc và số liệu. Tài liệu này chỉ nói **chọn gì từ ba hướng A/B/C và vì sao**, cộng một khung chưa ai dựng.

> **Người dựng mockup đọc [mục 8 — vòng sửa 2](#8-vòng-sửa-2--sau-review-ngày-17102026) trước.** Bộ 9 khung đã gửi và đã review xong; mục 8 là việc phải sửa tiếp, cộng các quyết định mới của người dùng ngày 17/10/2026. Chỗ nào mục 8 khác với mục 1–7 thì theo mục 8.

## 1. Vì sao ghép

Ba hướng A, B, C giải **ba bài khác nhau**, không cạnh tranh nhau:

| Hướng | Giải được | Hỏng ở đâu |
| --- | --- | --- |
| A · Sổ theo tháng | Các tháng xếp dọc, chuyển tháng không tốn thao tác, gần cách làm hiện tại nhất | Không giải bài mười lăm trường không vừa màn. Tìm sổ trong 240 nằm ngoài màn |
| B · Bảng thao tác | Chọn một dòng thì bung chi tiết ngay dưới — giải bài mười lăm trường mà không nhồi cột cũng không cắt cột | Tháng cũ rút còn một con số, không xem lại chi tiết ngay được |
| C · Khách & việc cần xử lý | Cột trái 240 sổ có tìm và lọc theo trạng thái chốt — đổi sổ một thao tác | Bỏ dạng bảng, mỗi chuyến thành thẻ nhiều dòng; 50 container một tháng thành cuộn rất dài, mất khả năng quét dọc cột tiền |

Ghép lại thì mỗi điểm mạnh giữ được, mỗi điểm yếu có cái khác bù.

## 2. Bản ghép

**Hai cột.**

**Cột trái — danh sách sổ** (lấy từ C):
- 240 sổ, nhóm theo loại hàng.
- Ô tìm theo tên khách hoặc loại hàng.
- Lọc theo trạng thái chốt của tháng đang xem: tất cả · chưa chốt · đang mở · đã chốt. Đây là cách trả lời "tháng này còn ai chưa chốt" mà không phải mở từng sổ.
- Mỗi sổ hiện sẵn hai số `đã chốt` và `đang mở`, kèm trạng thái.

**Cột phải — sổ đang chọn** (lấy từ A):
- Các tháng xếp dọc, mới nhất dưới cùng.
- Tháng đã chốt **thu gọn thành một thanh**: tên tháng, nhãn đã chốt kèm ngày, số dư cuối tháng. Bấm để mở ra đầy đủ.
- Tháng đang mở **mở sẵn**, dạng **bảng**, có dòng trống cuối bảng để gõ.
- Hai số `đã chốt` và `đang mở` ở đầu cột phải.

**Trong bảng — bung dòng thay vì bật cột** (lấy từ B):
- Mặc định hiện các trường hay dùng. Chọn một dòng thì **bung một hàng chi tiết ngay dưới dòng đó**: hãng tàu, nơi đi, nơi đến, ba loại phí, tham chiếu.
- **Bỏ nút bật/tắt cả cột.** Người dùng chỉ cần chi tiết của đúng dòng đang làm việc, không cần của cả bảng; bung theo dòng giữ được bảng gọn mà vẫn xem được đủ mười lăm trường.

**Khi một thao tác bị chặn** (lấy từ A và B):
- Nêu **đủ mọi lý do** trong một câu, không nêu một cái rồi để người dùng sửa xong vẫn bị chặn.

Những gì không nói ở đây thì người dựng tự quyết.

## 3. Khung còn thiếu: ghi tiền thu

Ba hướng đều dừng ở trạng thái chưa có khoản thu nào, nên **chưa hướng nào chứng minh được quy tắc khó nhất**: tiền thu trừ phần đã chốt trước, phần dư mới sang đang mở, và không số nào được âm. Đây đúng là chỗ một bản dựng trước đó từng cho ra số âm.

Khung này **bắt buộc**.

**Tình huống.** Sổ `KHACH_MAU · thanh long`, tháng 04.2026 đang mở. Trước khi ghi: `đã chốt 95.000.000`, `đang mở 90.000.000`.

Ghi một khoản thu **120.000.000** trên **dòng đầu của nhóm**, phủ ba chuyến DEMO-105, DEMO-106, DEMO-107. Các trường: ngày thực nhận `20/04/2026`, cách thu `Chuyển khoản`, tham chiếu `UNC-0420`, số tiền `120.000.000`.

**Kết quả phải ra đúng:**

| Chỗ | Giá trị |
| --- | --- |
| Đã chốt (đầu sổ) | **0**, kèm chữ `đã thu đủ` |
| Đang mở (đầu sổ) | **65.000.000** |
| Đã thu trong tháng | 120.000.000 |
| Còn phải thu cuối tháng | **0** |
| Đang mở · chưa chốt (cuối tháng) | **65.000.000** |

**Phân bổ phải xem lại được**, theo đúng thứ tự nợ cũ trước:

| Nhận vào | Số tiền |
| --- | --- |
| Số dư trước tháng 01.2026 | 20.000.000 |
| Tháng 01.2026 | 20.000.000 |
| Tháng 02.2026 | 30.000.000 |
| Tháng 03.2026 | 25.000.000 |
| *hết phần đã chốt* | *95.000.000* |
| Tháng 04.2026 · đang mở | 25.000.000 |
| **Tổng** | **120.000.000** |

Hiện rút gọn một dòng cũng được, nhưng **phải bung ra được bảng này**. Khi khách hỏi "tiền tôi trả trừ vào tháng nào" thì đây là chỗ trả lời.

**Hai cái bẫy, đừng sửa thành sai:**

1. **Ba thanh tháng đã chốt giữ nguyên 40.000.000 / 70.000.000 / 95.000.000.** Khoản thu ghi vào tháng 04, nó không sửa ngược số dư lịch sử của các tháng đã chốt. Bảng phân bổ chỉ nói khoản thu xoá nợ của những tháng nào, không đổi số đã chốt của các tháng đó.
2. **Không số nào âm trong khung này.** Tiền thu lớn hơn phần đã chốt là chuyện bình thường; phần dư chảy sang đang mở, không được đẩy số nào xuống dưới 0. Khoản 120.000.000 vẫn nhỏ hơn tổng nợ nên không có số âm nào. Trường hợp khách trả dư **cả** tổng nợ thì khác — xem mục 8.

## 4. Khung cần dựng

| # | Khung | |
| --- | --- | --- |
| 1 | Mặc định: cột trái + sổ đang mở, có một dòng thiếu giá | bắt buộc |
| 2 | Chọn một dòng → bung hàng chi tiết | bắt buộc |
| 3 | Dán từ bảng tính, có liệt kê mười một cột đánh số theo thứ tự | bắt buộc |
| 4 | **Ghi tiền thu 120.000.000** theo mục 3 | bắt buộc |
| 5 | Chốt công nợ bị chặn: đăng nhập bằng người nhập, còn dòng thiếu giá → nêu **cả hai** lý do | bắt buộc |
| 6 | Chốt công nợ đi được: đăng nhập bằng người chốt, không còn dòng thiếu giá, nút bật | bắt buộc |
| 7 | Cột trái đang lọc `chưa chốt` | nên có |

Bộ đã gửi có **9 khung**: bảy khung trên, cộng khung *đang gõ khoản thu ngay trên dòng* và khung *bỏ dòng có chứng từ*. Giữ cả chín. Khung thứ mười ở mục 8.3. Nút trên màn đọc là **"Chốt công nợ tháng 04"**, không dùng chữ "debit".

## 5. Vẫn phải giữ

Toàn bộ mục 5 và mục 6 của [brief](ux-brief-so-cong-no.md): quy tắc tiền, số liệu mẫu, và các con số phải ra đúng. Không nhắc lại ở đây để khỏi lệch hai bản.

Riêng hai điều hay bị bỏ quên:
- Số của cả tháng không được điền vào từng dòng.
- Người nhập khác người chốt; mỗi khung chọn đúng người đăng nhập cho việc của khung đó.

## 6. Còn thiếu từ vòng trước

Mục 8 của brief yêu cầu mỗi hướng **đếm số thao tác** cho ba việc hay làm nhất và nêu đánh đổi. Bộ ba hướng gửi về không kèm phần này, nên chưa so được theo thước đo đã đặt.

Bản ghép cần kèm con số đó: thêm một lô chuyến, chốt công nợ một tháng, ghi một khoản tiền thu — mỗi việc mấy thao tác tính từ lúc mở app. Ngưỡng là **3 / 3 / gõ thẳng trên dòng**.

**ĐÃ CÓ ở bộ 9 khung, đạt ngưỡng:** dán thẳng vào dòng trống cuối bảng = 3; chốt = 3; ghi khoản thu = gõ bốn ô ngay trên dòng, không chuyển màn. Dán qua hộp thoại là 4 thao tác — giữ làm đường phụ, đường chính là dán thẳng vào bảng.

## 7. Còn mở

Giữ nguyên mục 7 của brief. Không chốt hộ trong thiết kế.

## 8. Vòng sửa 2 — sau review ngày 17/10/2026

Bộ 9 khung (`mockup_v5_da_sua`) đã review. Phần tiền đạt: phân bổ 120.000.000 ra đúng 20/20/30/25 rồi 25, ba tháng lịch sử giữ nguyên 40/70/95, hai số đã chốt và đang mở không nơi nào gộp, chặn chốt nêu đủ hai lý do, DEMO-103 không bị xoá âm thầm, đếm thao tác đạt 3 / 3 / gõ thẳng trên dòng.

Mục này là việc **vòng sau**. Lý do đầy đủ nằm ở [bản quyết định 17/10/2026](ux-v5-quyet-dinh-2026-10-17.md); không cần đọc file đó mới sửa được.

### 8.1 Chín quyết định mới của người dùng

| # | Chốt |
| --- | --- |
| 1 | Khoản thu thuộc **sổ (khách × loại hàng) + kỳ nợ**, không thuộc chuyến. Dòng chuyến chỉ là chỗ gõ |
| 2 | **Không có cột số lượng** |
| 3 | **Thành tiền = đơn giá + phí khác + phí cắm điện cảng + phí áp tải**, hệ thống tự cộng |
| 4 | Chưa xét phân quyền xác nhận chứng từ |
| 5 | **Cho chốt tháng** dù còn chứng từ chưa xác nhận |
| 6 | Ô phí trống = **không có phí**: vẫn hiện `—`, không hiện `0`, cộng thành tiền thì coi như không phát sinh |
| 7 | Bỏ dòng chuyến đã lưu thì **bỏ luôn chứng từ chưa xác nhận** trên đó, có lưu vết. Khoản **đã xác nhận** thì không đi đường này |
| 8 | Khách trả dư hiện **số âm** kèm chữ `khách trả dư · phải trả lại` |
| 9 | Tiền dư nằm lại **trong sổ đó**, không tự mang sang sổ khác của cùng khách |

### 8.2 Bảy việc phải sửa trên mockup

1. Khoản thu hiện như của **sổ**; dòng chuyến chỉ còn nhãn `ghi tại dòng DEMO-105`. Bỏ chữ "gắn với chuyến này".
2. Khung "chặn bỏ dòng" đổi thành **xác nhận bỏ dòng**: bỏ luôn chứng từ 5.000.000 chưa xác nhận, không đổi số dư, có lưu vết; thêm một câu cho biết khoản **đã xác nhận** không đi đường này.
3. Đơn giá về **40.000.000 / 30.000.000 / 20.000.000**, ba ô phí để trống. Bung chi tiết thì hiện rõ thành tiền = đơn giá + 3 phí. Bỏ hẳn kiểu đơn giá 10.000.000 ra thành tiền 40.000.000 — không có cột số lượng nào giải thích được con số đó.
4. Khung dán ghi rõ: cột **Thành tiền** dán vào chỉ dùng **đối chiếu**; lệch với số tự cộng thì báo "lệch X, kiểm lại", không tự sửa và không tự bỏ dòng.
5. Khung chốt hợp lệ thêm một câu: chốt xong, chứng từ 5.000.000 **vẫn treo, vẫn chưa vào số dư**.
6. Cột `Đã thu` của DEMO-103 đang hiện `—` trong khi dòng đó có chứng từ 5.000.000 — hiện `5.000.000 · chưa xác nhận` (mờ). Biết mà chưa xác nhận khác với không có.
7. Sau khi lưu khoản thu, mất dấu **"phủ ba chuyến"**: DEMO-106 và DEMO-107 chỉ còn `—`. Giữ lại vạch nối hoặc nhãn. Hộp phân bổ cũng đang che nửa phải của bảng. Và sidebar ở khung đó thiếu `1 dòng thiếu giá` trong khi bảng vẫn còn dòng thiếu giá.

### 8.3 Khung cần thêm

| # | Khung | |
| --- | --- | --- |
| 10 | **Khách trả dư**: khoản thu lớn hơn toàn bộ nợ của sổ → số âm kèm chữ `khách trả dư · phải trả lại`, bảng phân bổ cho thấy phần dư không trừ vào đâu nữa | bắt buộc |

### 8.4 Còn mở — đừng tự quyết

1. **Thứ tự 11 cột thật** trong bảng tính: chưa đối chiếu. Giữ câu "cần đối chiếu với bảng tính thật" trên khung dán.
2. **Ai xác nhận chứng từ, căn cứ gì**: hoãn theo quyết định 4. Không vẽ nút xác nhận.
3. **Tiền dư dùng cho sổ khác của cùng khách**: đang mặc định là không.
4. **Sổ "chưa mở" có tính là "chưa chốt" không**: khung lọc hiện đang tự quyết là không.

## 9. Hoàn tác

Tài liệu mới, chưa sửa code hay dữ liệu. Bỏ bằng cách xoá file này.
