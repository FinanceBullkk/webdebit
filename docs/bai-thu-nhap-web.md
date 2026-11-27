# Bài làm thử trên web trước ngày thôi gõ Sheet

Lập 27/11/2026 (Claude), theo [`WEB-CHINH-01`](decisions/web-chinh-01.md): từ **1/12/2026** người nhập thôi gõ Sheet sổ nợ, mọi đầu vào nhập trên web, và trước 1/12 người nhập phải đi thử từng đường trên `hao`. Đo chỉ đọc trên `hao` 27/11/2026: trong 7 ngày, người chỉ có 13 thao tác ghi, đều từ login chủ sổ; login người nhập có 6 thao tác, tất cả ngày 20/11; chưa phiếu thu nào do người ghi trên web.

Bài này phục vụ các mục C1, C2, C3, C4, C5 của [checklist chuyển hẳn](chuyen-han-checklist.md). **ĐỀ XUẤT**: thứ tự và cách làm do Claude đặt; ngày làm do chủ sổ chọn.

## Ai, khi nào

- **Người làm:** người nhập, bằng **login của chính mình**, không mượn login chủ sổ (để Lịch sử ra đúng tên, mục C3). Chủ sổ ở cạnh hoặc gọi được.
- **Khi nào:** một buổi khoảng một giờ trong 28–30/11 cho bài 1–6. Tốt nhất là làm **trọn ngày 30/11 trên web** (mục C1): việc nào gõ Sheet ngày đó thì gõ cả trên web.
- **Máy:** laptop thường dùng, Chrome, màn 1280×720 trở lên.

## Bốn điều phải giữ

1. **Chỉ nhập việc thật của hôm đó.** Web là sổ thật, không có bản thử. Không gõ số bịa để "xem thử nút".
2. **Tới hết 30/11 vẫn gõ Sheet như mọi ngày.** Cái gì gõ trên web thì gõ y hệt trên Sheet: cùng số tiền, cùng ngày. Máy chép Sheet chạy tới hết 30/11 và chỉ *thêm* cái web chưa có: phiếu cùng số tiền, ngày lệch không quá 3 ngày là phiếu đã có ([`THU-SHEET-01`](decisions/thu-sheet-01.md)); giá web đã có thì máy không đè ([`WEB-CHINH-01`](decisions/web-chinh-01.md) nguyên tắc 3). Hai bên gõ khác nhau thì sổ đó hiện ở danh sách lệch cho chủ sổ xem, không tự sửa.
3. **Ghi nhầm thì sửa đúng chỗ, không xóa lung tung.** Phiếu nhầm: mở phiếu, **Hủy phiếu**, ghi lý do (bắt buộc), rồi ghi lại cho đúng. Giá nhầm: bấm lại ô, gõ số đúng, Enter. Việc khác thì dừng và báo chủ sổ.
4. **Mỗi bài ghi kết quả** vào bảng cuối trang: Được, hay Vướng kèm câu chữ trên màn (chụp màn hình càng tốt).

## Bước 0 — Vào web

Mở web công nợ bằng login của mình. Menu bên trái có: Tìm khách, Tổng quan, Công nợ theo tháng, Sổ khách, Bảng thu, Báo cáo tháng, Thu chi. Không có Việc cần làm, Máy chạy hay Quản trị là **đúng** (đó là trang của quản lý, [`QUYEN-01`](decisions/quyen-01.md)).

## Bài 1 — Tìm sổ và đọc sổ (không ghi gì)

1. Tìm khách theo tên, mở Sổ khách.
2. Chọn tháng trên thanh tháng; xem chuyến, phụ phí, phiếu thu, số còn nợ.
3. Mở **Lịch sử** của sổ, xem ai đã làm gì.

Đạt khi: tự tìm được sổ và nói được khách còn nợ bao nhiêu, tháng nào.

## Bài 2 — Gõ giá cho chuyến chưa có giá

1. Ở **Tổng quan**, bấm viên **chuyến chưa giá**: hiện danh sách sổ còn chuyến chưa giá. Bấm một sổ: Sổ khách mở và tô các chuyến thiếu giá.
2. Ô giá ghi **"chưa có giá"**. Có giá booking thì dưới chữ đó có dòng nhỏ "booking … tr".
3. Bấm vào ô (hoặc Enter): ô điền sẵn giá booking. Kiểm với giá thật, gõ đè nếu khác. **Chỉ Enter mới ghi.** Rời ô mà chưa Enter thì không ghi gì.
4. Máy hỏi đơn vị (ví dụ "45" là 45 triệu?) thì đọc kỹ rồi chọn.
5. Gõ cùng giá đó trên Sheet.

Đạt khi: ô có giá, số còn nợ của tháng đổi, Lịch sử có dòng sửa giá mang tên mình.

## Bài 3 — Dán một cột giá

1. Trên Sheet hoặc Excel, chọn một cột giá nhiều dòng (đúng thứ tự chuyến như trên sổ web), Ctrl+C.
2. Trên Sổ khách, đứng ở ô giá của chuyến đầu tiên, Ctrl+V.
3. Khung xem lại hiện từng chuyến và nợ trước → sau. Kiểm từng dòng. Dòng nào bị bỏ qua (tháng khóa, chuyến chờ kiểm, dòng sổ gốc) thì khung nói rõ.
4. Bấm ghi.

Đạt khi: đúng chuyến nhận đúng giá; không chuyến nào bị lệch dòng.

## Bài 4 — Phụ phí

1. **Gõ một ô:** bấm ô ở cột phụ phí riêng (nâng, hạ, lưu bãi…), gõ số, Enter.
2. **Dán cả cột phụ phí:** như bài 3, đứng ở ô phụ phí của chuyến đầu, Ctrl+V. Khung xem lại hiện nợ trước → sau; ô nào ngoài khoảng 10 nghìn tới 100 triệu đồng thì có cờ "nghi sai đơn vị", đọc kỹ trước khi ghi. Giảm trừ là số âm.
3. Chuyến chưa có giá thì phụ phí ghi được nhưng chưa cộng vào nợ; khung nói rõ.

Đạt khi: phụ phí đúng cột, đúng chuyến; Lịch sử có dòng mang tên mình.

## Bài 5 — Ghi một phiếu thu

1. Trên Sổ khách bấm **+ Ghi phiếu thu**.
2. Nhập ngày khách trả, số tiền, hình thức, tham chiếu (mã giao dịch ngân hàng hoặc chữ như trên Sheet).
3. Bước xem lại hiện nợ trước → sau; số tiền lạ (dưới 100 nghìn hoặc trên 1 tỷ) phải bấm "Đúng số này". Bấm ghi.
4. Mở **Bảng thu** của tháng, thấy phiếu vừa ghi.
5. Gõ cùng phiếu đó trên Sheet (cùng số tiền, cùng ngày).

Đạt khi: phiếu hiện ở sổ và ở Bảng thu; tiền trừ vào nợ cũ trước; Lịch sử mang tên mình. Lượt máy sau đó không ghi thêm phiếu thứ hai (chủ sổ hoặc Claude kiểm).

## Bài 6 — Các kiểu phiếu khác (chỉ khi hôm đó có ca thật)

| Ca | Làm thế nào |
| --- | --- |
| Không biết khách trả ngày nào | Trong khung Ghi phiếu thu, đánh dấu **Không rõ ngày trả**, chọn tháng. Phiếu ghi ngày cuối tháng đó, tham chiếu có đuôi "(ngày tượng trưng)" ([`PHIEU-WEB-01`](decisions/phieu-web-01.md) mục 1) |
| Một lần chuyển trả cho nhiều sổ | **Chia cho nhiều sổ…**: nhập tổng tiền, thêm sổ, chia từng phần. Tổng các phần phải bằng tổng chuyển. Mỗi sổ thành một phiếu riêng. Đang chia dở mà đóng thì chọn "Đóng, ghi sau", đừng bỏ rồi chia lại |
| Nhiều phiếu một sổ | **Dán nhiều phiếu…**: chép từ Sheet các cột Ngày trả · Số tiền · Hình thức · Tham chiếu, dán, xem trước, ghi. Còn dòng lỗi thì không ghi dòng nào |
| Khách gửi ảnh chuyển khoản trong Zalo | Trang **Thu chi**: khoản đã gắn sổ có nút **Ghi phiếu**, mở Sổ khách với khung điền sẵn. Vẫn tự xem lại rồi mới bấm ghi |
| Cấn trừ giữa hai sổ | Khung Ghi phiếu thu, hình thức CẤN TRỪ, chọn sổ lấy tiền. Cần ngày cụ thể |

## Bài 7 — Sửa ở tháng đã khóa (chỉ khi có ca thật)

Mặc định chỉ tháng hiện tại mở. Sửa giá hay phụ phí chuyến tháng cũ: bấm **Mở khóa tháng N** ở sổ đó, sửa, rồi bấm khóa lại. Phiếu thu thì ghi được cả ở tháng khóa, không cần mở. Riêng tháng 11: tối 30/11 máy sẽ mở sẵn tháng 11 ở các sổ còn chuyến chưa giá, tới 15/12 thì khóa lại ([runbook](v7-deploy-runbook.md#giữ-tháng-11-mở-ở-sổ-còn-chuyến-chưa-giá-web-chinh-01--chưa-chạy)).

## Bài 8 — Chuyến bộ chờ chọn sổ (chỉ khi có)

Sổ nào có chuyến bộ máy không tự xếp được thì đầu sổ có dải **Chuyến bộ chờ chọn sổ: N · Xem**. Bấm Xem, đọc container, ngày, lời nhắn, chọn sổ đúng rồi bấm vào sổ. Chuyến vào sổ chưa có giá; gõ giá như bài 2.

## Bài 9 — Hai người cùng mở một sổ

Chủ sổ và người nhập cùng mở một sổ. Mỗi người thấy người kia đang ở đâu ("… đang sửa…"). Một người ghi một việc thật (giá hay phiếu của hôm đó); người kia thấy câu báo sổ vừa đổi và số mới, không mất gì ([`PRESENCE-01`](decisions/presence-01.md)). Đây là mục C4 của checklist.

## Không phải việc của người nhập

- **Khách mới, chủ hàng mới chưa có sổ:** chỉ quản lý tạo sổ hoặc gán tên chủ hàng ở thẻ Khách trong Quản trị ([`KHACH-WEB-01`](decisions/khach-web-01.md)). Người nhập gặp chủ hàng lạ thì báo chủ sổ.
- **Kết luận chuyến chờ kiểm, xử lý danh sách lệch, Việc cần làm:** của quản lý.
- **Web không vào được:** ghi lại việc chưa nhập được (giấy hoặc file riêng) và báo chủ sổ ngay. Quy trình khi `hao` sập giữa ngày (mục E2 của checklist) chưa có.

## Bảng kết quả

Người nhập điền, chủ sổ giữ. Không ghi tên khách hay số tiền vào repo.

| Bài | Ngày làm | Được / Vướng | Câu trên màn khi vướng |
| --- | --- | --- | --- |
| 1 Tìm, đọc sổ | | | |
| 2 Gõ giá | | | |
| 3 Dán cột giá | | | |
| 4 Phụ phí | | | |
| 5 Phiếu thu | | | |
| 6 Kiểu phiếu khác | | | |
| 7 Tháng khóa | | | |
| 8 Chuyến bộ chọn sổ | | | |
| 9 Hai người cùng sổ | | | |

## Sau buổi thử

- Claude đọc Lịch sử trên `hao` (chỉ đọc): đếm thao tác theo login và loại việc, kiểm lượt máy chép sau đó không ghi trùng phiếu nào. Ghi số đếm vào mục C1–C5 của [checklist chuyển hẳn](chuyen-han-checklist.md).
- Mỗi chỗ vướng thành một việc sửa trước 1/12 nếu chặn việc nhập, hoặc ghi lại nếu không chặn.
