# Brief — ứng dụng công nợ phải thu

Trạng thái: **ĐỀ XUẤT** (Claude, 17/10/2026).

Tài liệu này mô tả **bối cảnh, chức năng, quy tắc nghiệp vụ và luồng sử dụng**. Nó **không quy định bố cục màn hình**. Người dựng tự quyết số màn, cách sắp xếp, cách hiển thị, và nên đề xuất vài hướng khác nhau (mục 8).

Những phương án đã thử trước đây cố tình không đưa vào đây để khỏi dẫn dắt. Chỉ ghi một điều đã học được: bản nào bắt người dùng thao tác nhiều hơn bảng tính hiện tại thì bị bác.

---

## 1. Bối cảnh

Công ty vận tải container. Việc cần quản lý là **tiền khách hàng còn nợ**.

Hiện tại làm trên bảng tính, khoảng 240 trang tính. Cách tổ chức của họ:

- **Một trang tính = một khách × một loại hàng.** Loại hàng gồm thanh long, chuối, dừa, xoài, sầu riêng, mít, nhãn, bưởi…; và theo dịch vụ: đường bộ, bán cước, hàng nhập. Một khách có thể có nhiều trang.
- **Trong một trang, các tháng xếp chồng dọc.** Mỗi khối tháng gồm: tiêu đề tháng → dòng số dư tháng trước chuyển sang → bảng các chuyến → dòng tổng (tổng phát sinh, đã thu, còn phải thu cuối tháng).
- **Thêm chuyến = gõ vào dòng trống cuối khối tháng đó.** Không có ô chọn kỳ nợ ở đâu cả: tháng chính là cái khối đang gõ vào. Nhập muộn thì gõ vào khối tháng cũ.
- **Tiền khách trả ghi ngay trên dòng chuyến**, ở các cột bên phải. Một khoản thu thường phủ nhiều chuyến cùng lúc.
- **Có một trang tổng**: mỗi khách một dòng, nhóm theo loại hàng; mỗi tháng có số chuyển sang, phát sinh, đã thu, còn lại, số container.
- Tháng nào không có hàng thì không có khối tháng đó.

Cách làm này chậm nhưng họ thuộc. Thao tác để thêm một chuyến hiện là **ba bước**: mở trang khách → tới khối tháng → gõ.

Vấn đề của bảng tính: không kiểm soát được ai sửa gì, không tách được tiền đã xác nhận với tiền mới khai, công thức dễ gãy, và không chặn được số sai.

## 2. Người dùng

- **Trên 40 tuổi.** Ưu tiên đúng luồng nghiệp vụ và ít thao tác hơn là hình thức. Giao diện không được có thông tin thừa. Chữ và số phải dễ đọc, nút phải dễ bấm.
- **Khối lượng:** 10–50 container mỗi ngày. Người nhập thường **copy cả lô từ bảng tính** rồi dán, chứ không gõ từng chuyến.
- **Ba vai trò**, có thể là ba người khác nhau:
  - *Người nhập*: gõ chuyến vào tháng đang làm.
  - *Người chốt*: cuối tháng xem lại rồi chốt công nợ tháng đó của một khách.
  - *Người thu tiền / chủ*: ghi tiền khách trả, xem ai còn nợ.

**Tiêu chí sống còn:** nếu app bắt làm nhiều thao tác hơn bảng tính thì sẽ không ai dùng, dù nó chính xác đến đâu.

## 3. Chức năng phải làm được

Mô tả bằng việc, không bằng màn hình.

1. **Nhập nhiều chuyến một lúc**, gồm dán cả lô từ bảng tính (một lần tối đa 50 dòng, ánh xạ theo vị trí cột).
2. **Sửa chuyến chưa chốt**, kể cả chuyến của tháng cũ nếu tháng đó chưa chốt.
3. **Chốt công nợ một tháng của một khách** — một lần cho cả tháng, không chốt từng dòng. Trước khi chốt phải xem lại được số chuyến, tổng tiền, và những dòng còn thiếu dữ liệu.
4. **Ghi tiền khách trả** và phân bổ vào nợ cũ trước. Một khoản thu phủ nhiều chuyến.
5. **Xem còn nợ**: của một khách theo từng tháng, và của toàn bộ khách trong một tháng.
6. **Thấy ngay việc chưa xong**: dòng thiếu giá, tháng chưa chốt, chứng từ chưa xác nhận. Với 240 sổ, phải lọc hoặc lướt nhanh ra được **tháng này còn khách nào chưa chốt**.
7. **Trả lời được "tiền khách trả trừ vào tháng nào"**. Khi khách thắc mắc, phải xem lại được một khoản thu đã phân bổ vào những tháng nào và mỗi tháng bao nhiêu, không chỉ một con số tổng.
8. **Sau khi chốt, muốn sửa thì phải đề nghị điều chỉnh**, không sửa đè.

## 4. Dữ liệu một chuyến

Mười lăm trường, giữ theo bảng tính hiện hành.

**Người nhập gõ hoặc dán — 11 trường, đúng thứ tự này khi dán:**

1. Số thứ tự trong tháng (hệ thống tự đánh)
2. Số container
3. Hãng tàu
4. Ngày (ngày nghiệp vụ của chuyến)
5. Nơi đi
6. Nơi đến
7. Phí khác
8. Phí cắm điện cảng
9. Phí áp tải
10. Đơn giá
11. Thành tiền

**Người thu tiền gõ — 4 trường:**

12. Ngày thực nhận
13. Cách thu: chuyển khoản · cấn trừ · ứng trước · khác
14. Tham chiếu (số tài khoản, số chứng từ, ghi chú)
15. Số tiền đã thu

**Số của cả tháng, không thuộc từng dòng:** số dư chuyển sang, tổng phát sinh, đã thu trong tháng, còn phải thu cuối tháng.

Mười lăm trường không vừa một màn 1440 nếu bày hết cùng lúc. Cách giải quyết để người dựng tự chọn; chỉ lưu ý trường **Ngày** phải luôn thấy được, vì nó quyết định dòng thuộc tháng nào.

## 5. Quy tắc không được vi phạm

Đây là quy tắc **tiền**, không phải sở thích trình bày. Vi phạm là ra số sai.

1. **VND số nguyên chính xác.** Không làm tròn để ép khớp.
2. **Trống khác 0.** Ô chưa biết phải hiện là chưa biết, không hiện 0 và không cộng như 0.
3. **Chưa chốt thì ngoài số đã chốt.** Chuyến đã nhập nhưng chưa chốt phải nhìn thấy được, nhưng không được cộng vào số đã chốt. **Không có chỗ nào gộp hai loại thành một con số.**
4. **Tiền thu trừ nợ cũ trước**, rồi mới tới tháng đang mở. Ghi tiền thu cho tháng chưa chốt là bình thường.
4b. **Hai loại số âm, đừng lẫn.** Âm do **phân bổ sai** — trừ nhầm kỳ, sai thứ tự, cộng nhầm phần chưa chốt vào phần đã chốt — là lỗi, cấm tuyệt đối; đây là chỗ một bản dựng trước đã ra số âm giả. Âm do **khách trả nhiều hơn toàn bộ nợ** là thật và được phép: hiện số âm kèm chữ `khách trả dư · phải trả lại`, không để số âm trần. Tiền dư nằm lại trong sổ đó, không tự mang sang sổ khác của cùng khách. ĐÃ CHỐT bởi người dùng 17/10/2026, xem [bản quyết định](ux-v5-quyet-dinh-2026-10-17.md).
5. **Người nhập khác người chốt.** Không ai chốt được tháng mà các dòng do chính mình nhập.
6. **Đã chốt thì không sửa đè.** Chỉ có đề nghị điều chỉnh, có lý do và lưu vết.
7. **Kỳ nợ là tháng của khối đang gõ**, không suy từ ngày chuyến.
8. **Container không phải khóa duy nhất.** Trùng container chỉ là dấu hiệu cần kiểm tra, không tự gộp và không tự kết luận trùng.
9. **Một khoản thu phủ nhiều chuyến là bình thường.** Không tự gắn tiền thu vào từng chuyến.
10. **Số dư chuyển sang chỉ giải thích đầu tháng**, không phải phát sinh mới, không cộng lại.
11. **Không nhận ngày tương lai** cho ngày chuyến.
11b. **Chặn thì phải nói đủ lý do.** Một thao tác bị chặn vì nhiều lý do cùng lúc thì nêu hết; nêu một lý do rồi người dùng sửa xong vẫn bị chặn là lỗi.
12. Số dư chuyển sang của một tháng phải bằng đúng còn phải thu cuối tháng của tháng trước.

Ngoài ra, **không đưa lên giao diện**: mã quyết định nội bộ, từ kỹ thuật (revision, API, schema, fixture, idempotency), đoạn văn giải thích quy trình nội bộ, hộp khoe các kiểm tra đã đạt. Ghi chú cho người review để riêng ngoài khung màn hình.

## 6. Dữ liệu mẫu và số phải ra đúng

**Dữ liệu giả.** Không dùng tên khách, số container hay số tiền thật.

Sổ `KHACH_MAU · thanh long`, tuyến `PHAN THIET → SHEKOU`.

| Tháng | Trạng thái | Các chuyến | Chuyển sang | Phát sinh đã chốt | Đã thu | Còn phải thu cuối tháng |
| --- | --- | --- | --- | --- | --- | --- |
| 01.2026 | đã chốt | DEMO-101 · 30.000.000 | 20.000.000 | 30.000.000 | 10.000.000 | **40.000.000** |
| 02.2026 | đã chốt | DEMO-102 · 40.000.000 | 40.000.000 | 40.000.000 | 10.000.000 | **70.000.000** |
| 03.2026 | đã chốt | DEMO-104 · 25.000.000 | 70.000.000 | 25.000.000 | — | **95.000.000** |
| 04.2026 | **đang mở** | DEMO-105 · 40.000.000<br>DEMO-106 · 30.000.000<br>DEMO-107 · 20.000.000<br>DEMO-103 · chưa có giá | 95.000.000 | — | — | **95.000.000** |

Tháng 04 có **90.000.000 đang mở** (40+30+20; dòng chưa có giá không được cộng). Thêm một chứng từ 5.000.000 có số tiền nhưng **chưa có ngày thực nhận** → chưa xác nhận, không vào số dư.

**Các con số phải ra đúng, bất kể bố cục thế nào:**

- `20+30−10=40` · `40+40−10=70` · `70+25−0=95` · tháng 04 đã chốt vẫn là `95.000.000`.
- Hai số của sổ: **đã chốt 95.000.000** và **đang mở 90.000.000**. Không nơi nào cộng thành 185.
- Thêm một chuyến 35.000.000 vào tháng 04 → đang mở thành **125.000.000**, đã chốt không đổi.
- Ghi tiền thu **120.000.000** vào tháng 04: trừ hết 95.000.000 phần đã chốt (số dư trước tháng 01 là 20, tháng 01 là 20, tháng 02 là 30, tháng 03 là 25), phần dư 25.000.000 trừ tiếp vào đang mở → **đã chốt 0, đang mở 65.000.000**. Không có số âm.
- Chốt công nợ tháng 04 khi còn dòng chưa có giá: phải bị chặn, và phần xem lại chỉ đếm và cộng **3 chuyến có giá · 90.000.000**, chỉ đúng dòng DEMO-103 bị nêu tên.

**Màn tổng tháng 04.2026**, nhóm theo loại hàng:

| Loại hàng | Khách | Chuyển sang | Phát sinh đã chốt | Đã thu | Cuối tháng | Đang mở | Cont | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Thanh long | KHACH_MAU | 95.000.000 | — | — | 95.000.000 | 90.000.000 | 4 | đang mở |
| Thanh long | KHACH_B | 18.000.000 | 122.000.000 | 40.000.000 | 100.000.000 | — | 9 | đã chốt |
| Thanh long | KHACH_C | 0 | — | — | 0 | — | — | chưa mở |
| Mít | KHACH_D | 30.000.000 | 60.000.000 | 20.000.000 | 70.000.000 | — | 3 | đã chốt |
| Mít | KHACH_E | 12.000.000 | — | — | 12.000.000 | 45.000.000 | 2 | đang mở |

Người nhập `Nguyễn Văn A`, người chốt `Lê Văn C`.

## 7. Còn mở — đừng tự quyết thay

Những điểm này chưa có câu trả lời. Nếu phương án chạm tới chúng thì nêu ra như câu hỏi, **không chốt hộ trong thiết kế**:

1. Thứ tự 11 cột thật trong bảng tính của họ có đúng như mục 4 không.
2. Có được chốt công nợ trước khi hết tháng không.
3. Đã chốt rồi mới phát hiện chuyến của tháng đó thì mở lại hay đẩy sang tháng sau.
4. Một người có được chốt cho mọi khách không, hay chia theo nhóm khách.
5. Ai có quyền xác nhận một khoản thu, và căn cứ là gì.
6. Thiết bị thật đang dùng. Tạm giả định màn hình bàn hoặc laptop.
7. Danh mục cách thu bốn giá trị đã đủ chưa.
8. Tiền khách trả dư, hoàn tiền, tranh chấp: chưa có chính sách. Không vẽ.

## 8. Yêu cầu với bản đề xuất

Đây là phần thay cho việc quy định bố cục:

- **Đề xuất 2–3 hướng bố cục khác nhau**, không phải một. Mỗi hướng nói rõ nó đánh đổi cái gì lấy cái gì.
- **Tự quyết số màn và số trạng thái cần vẽ.** Không có con số bắt buộc.
- Với mỗi hướng, **đếm số thao tác** để đi hết ba việc hay làm nhất: thêm một lô chuyến, chốt công nợ một tháng, ghi một khoản tiền thu.

**Ngưỡng phải đạt.** Đã có một phương án dựng xong và chạy đúng toàn bộ mục 6. Số thao tác của nó, tính từ lúc mở app:

| Việc | Số thao tác |
| --- | --- |
| Thêm một lô chuyến bằng dán | 3 |
| Chốt công nợ một tháng | 3 |
| Ghi một khoản tiền thu | gõ thẳng trên dòng, không mở màn khác |

Bảng tính hiện tại cũng là 3 thao tác cho việc thêm lô. **Hướng đề xuất phải bằng hoặc ít hơn**, nếu nhiều hơn thì phải nói rõ đổi lại được cái gì đáng giá hơn. Cố tình không mô tả bố cục của phương án đó ở đây để khỏi dẫn dắt.
- Nêu rõ hướng nào xử lý tốt nhất chuyện **15 trường không vừa một màn**.
- Chỉ ra chỗ nào trong phương án đang chạm vào mục 7, và hỏi.
- Dữ liệu trên mockup lấy từ mục 6; con số phải khớp.

Không cần theo bất kỳ phương án nào đã thử trước. Nếu thấy cách tổ chức theo khối tháng của bảng tính không phải cách tốt nhất, cứ đề xuất khác — nhưng phải giải thích người dùng đang quen cách cũ sẽ chuyển sang thế nào.

## 9. Nguồn

- Quy tắc nghiệp vụ và sổ quyết định: `docs/business-rules.md`, `docs/decisions.md`.
- Hướng dẫn UX đã chốt: `docs/ux-guidelines.md`.
- Cấu trúc bảng tính hiện hành: đọc read-only ngày 17/10/2026, chỉ lấy cấu trúc, không sao chép nội dung và không ghi mã sổ ở đây.
- Một phương án chi tiết đã dựng và đã sửa qua nhiều vòng: `ux-v4-so-khach.md`. **Chỉ mở ra khi cần đối chiếu**, không dùng làm yêu cầu.

Mockup không thay nghiệm thu nghiệp vụ và không mở đường ghi tiền.
