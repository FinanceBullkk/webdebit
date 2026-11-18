# Đội xe đợt 2: thu cước, bảng kê và công nợ cước (DOI-XE-THU-01)

Trạng thái: ĐỀ XUẤT (Claude, 18/11/2026). Đây là đợt 2 của mục tiêu [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md), xem [spec đợt 1](chi-phi-xe-01.md). Người dùng chọn làm phần này song song với đợt 1 (18/11/2026). Hiện chỉ có spec và phân tích; code đợi đợt 1 có bảng phương tiện và chặng rồi mới nối vào.

## Mục tiêu

- Mỗi chặng có **dòng thu**: cước lấy theo bảng giá tuyến, phát sinh lấy theo danh mục.
- Web tự ra **bảng kê tháng** gửi công ty hàng, thay cho file "Công nợ cảng" gõ tay hiện nay.
- Theo dõi **công nợ cước**: công ty hàng còn nợ đội xe bao nhiêu, tính bằng bảng kê đã gửi ± điều chỉnh − tiền đã về.
- Thu và chi gắn chung một chặng, để đợt 3 tính được lãi từng chặng, từng xe.

**Đội xe là công ty con** (người dùng cho biết 18/11/2026): mỗi tháng đội xe xuất debit cho công ty mẹ là **HTH**, và HTH trả theo tháng, đủ bảng kê. Vì vậy:

- Bảng kê là giấy đòi tiền **nội bộ**, gửi công ty mẹ.
- Giá trên debit bằng giá xe thuê ngoài (Trần Hùng) ở 10/11 nhóm tuyến cùng chạy. Vậy lãi của đội xe đọc được như phần công ty mẹ **tiết kiệm được so với thuê xe ngoài**. Lãi âm nghĩa là thuê ngoài còn rẻ hơn tự chạy.

## Hiện trạng (đo 18/11/2026, file tháng 10, chỉ đọc)

Hai file công nợ cảng: Tín Phát có 204 dòng, Trần Hùng có 68 dòng. Các cột: ngày, container, cont kéo, tỉnh, kho, tài xế, số xe, nơi lấy, nơi hạ, tên hàng, cước, đóng ghép (chỉ file Tín Phát), phát sinh, ghi chú, cước tổng, kế toán note, +/− tiền, check lý do.

- **Tổng mỗi dòng đúng:** cước tổng = cước + đóng ghép + phát sinh ở cả 272 dòng.
- **Giá cước rất đều, nên bảng giá tuyến thay được việc gõ tay cước.**
  - Gom theo (tên hàng, tỉnh): Tín Phát có 55 nhóm, chỉ 1 nhóm có hai mức giá. Trần Hùng có 14 nhóm, không nhóm nào có hai mức.
  - Chuyển cảng dùng một giá cho cả 79 dòng.
  - Chặng thả mooc và rút mooc tính 70% giá tuyến. Công thức phần trăm làm 3 dòng ra số tiền lẻ.
- **Tên tuyến chưa chuẩn:** cùng một hàng hoặc một vùng nhưng viết nhiều kiểu (hàng có hoặc không có chữ "tươi"; tỉnh có hoặc không kèm huyện). Cần danh mục tuyến chuẩn, kèm các tên gốc hay gặp để nhận ra khi dán.
- **Phát sinh nằm trong ô ghi chú**, mỗi khoản một dòng theo dạng "_ Tên khoản số k".
  - Đọc được 100% các mẩu ghi chú. Tổng các khoản khớp số phát sinh ở 271/272 dòng.
  - Các khoản gặp trong tháng 10: xí cont, neo, kiểm hoá, hạ sớm, nổ máy phát, cont mới, phí bãi Đồng An, cân, mua seal, bãi chờ, điều độ, nâng hạ, hạ kiểm hoá.
  - Phần lớn khoản có một mức cố định, ví dụ kiểm hoá, hạ sớm.
  - Neo có dạng bậc: mức ngày đầu, mỗi ngày thêm một mức bằng nhau.
  - Nổ máy phát luôn là bội số của cùng một đơn giá.
  - Xí cont và cont mới có mức khác nhau giữa Tín Phát và Trần Hùng, nên danh mục cần giá riêng theo từng bên.
- **Đóng ghép không có mức cố định:** 19 dòng có 7 mức khác nhau, phụ thuộc số kho và khoảng cách; có 1 dòng lớn bất thường cần soát.
- **Ba cột đối chiếu** (kế toán note, +/− tiền, check lý do) đều trống ở cả hai file tháng 10.
- File BK tháng 3–4 có mẫu bảng kê "Kính gửi" công ty hàng. Các cột doanh thu: cước, kiểm hóa, đóng ghép, neo, nổ máy phát, hạ sớm, lấy xa, xí cont/trái tuyến/xe nâng, hạ Hưng Thịnh, phát sinh, cont mới; thêm một cột chi hộ.
- Không có chỗ nào ghi tiền công ty hàng đã trả.

Kiểm thêm theo yêu cầu người dùng (18/11/2026), trên file tháng 9 và tháng 10 của cả hai bên:

- **Không file debit nào ghi tên công ty nhận.** Cả 5 file chỉ có tiêu đề "DEBIT … THÁNG …". Cột kho có mã khách của HTH, còn mẫu BK tháng 3–4 ghi "Kính gửi" AS Logistics: CÒN MỞ (1).
- **Chi hộ, đo bằng cách so khoản thu trên debit với khoản đội xe đã chi cho cùng container:**
  - Kiểm hoá: 51/51 lần thu đúng bằng số đã chi (ghi ở cột hạ kiểm hoá của file điều xe).
  - Hạ sớm: 49/50 lần thu đúng bằng số đã chi.
  - Cân: 7/9 lần thu đúng bằng số đã chi; khoản này đang bị ghi vào cột phí nâng của file điều xe.
  - Xí cont: 89/165 lần thu đúng bằng số tài xế đã chi; các lần còn lại không có dòng chi tương ứng (phần lớn là chặng không có trong sheet chi phí tài xế).
  - Cont mới: 10/20 lần thu đúng bằng số đã chi.
  - Neo: 59/94 lần thu cao hơn số tài xế được chi, không lần nào bằng nhau. Vậy neo là doanh thu, kèm một khoản chi cho tài xế.
  - Nổ máy phát, phí bãi Đồng An: không có dòng chi tương ứng, tức là doanh thu.
- **Phí cảng không có trên debit, vì đội xe chịu.** Phí nâng (do tài xế trả, hoặc trả qua file điều xe) và phí hạ (file điều xe) là các khoản lớn, không nằm trên debit. Người dùng chốt 18/11/2026: đội xe chịu các khoản này trong cước. Vậy đây là chi phí thật của chặng, không phải chi hộ.
- **Xe Trần Hùng tính cùng giá cước với Tín Phát.** Trong 11 nhóm tuyến cả hai bên cùng chạy, 10 nhóm có cùng mức giá. Phát sinh thì có mức riêng. File điều xe trả phí cảng cho cả chặng của xe Trần Hùng. Chưa đủ để biết tiền cước của Trần Hùng đi qua mình hay không: CÒN MỞ (2).

## Mô hình dữ liệu (ĐỀ XUẤT)

Nối vào schema `doixe` của đợt 1. Chỉ đọc bảng của `sokhach`, không ghi vào đó.

| Bảng | Một dòng là | Ghi chú |
| --- | --- | --- |
| `tuyen` | một tuyến chuẩn | Tên hàng + vùng (tỉnh/kho) + nơi hạ; kèm danh sách tên gốc để nhận ra khi dán |
| `bang_gia_tuyen` | một mức cước | Theo bên nhận bảng kê, tuyến, loại chặng, áp dụng từ ngày. Chặng phụ có giá cố định hoặc tính % giá tuyến |
| `danh_muc_phat_sinh` | một loại phát sinh | Tên, cách tính (cố định / theo ngày / theo số đơn vị / nhập tay), mức theo từng bên, có phải chi hộ không |
| `dong_thu` | một khoản thu của chặng | Đã có trong mô hình đợt 1. Số tiền do web gợi ý theo bảng giá, người nhập sửa được, mọi lần sửa ghi Lịch sử |
| `bang_ke` | một bảng kê tháng gửi một công ty hàng | Trạng thái: nháp → đã gửi → đã đối chiếu; có số bảng kê |
| `dieu_chinh_bang_ke` | một khoản cộng hoặc trừ khi đối chiếu | Bắt buộc lý do, ghi người làm; thay cho cột +/− tiền và check lý do |
| `tien_ve_cuoc` | một lần công ty hàng trả tiền | Ngày tiền về, số tiền, gắn vào bảng kê tháng mà khoản tiền đó trả (người dùng cho biết công ty hàng trả theo tháng, đủ bảng kê) |

Web tự tính, không có ô sửa tay: **công nợ cước** = tổng bảng kê đã gửi + điều chỉnh − tiền đã về.

## Người dùng và luồng (ĐỀ XUẤT)

Người thao tác: hai nhân viên đang nhập chi phí (đợt 1) và kế toán đang làm file công nợ cảng. Màn 1280×720, theo phong cách sổ khách.

1. **Gợi ý thu khi nhập chặng:** lúc nhập chặng ở đợt 1, web điền sẵn cước theo bảng giá tuyến và các khoản phát sinh đọc được từ ghi chú. Người nhập sửa nếu khác. Chặng chưa có giá tuyến thì hiện cờ "chưa có giá".
2. **Ra bảng kê:** chọn công ty hàng và tháng. Web gom các chặng có thu, cho xem trước đúng mẫu file hiện nay, rồi xuất Excel.
3. **Đối chiếu:** công ty hàng góp ý từng dòng. Kế toán ghi điều chỉnh, bắt buộc lý do. Bảng kê chuyển sang "đã đối chiếu".
4. **Ghi tiền về:** chọn bảng kê tháng, nhập ngày và số tiền. Trả đủ thì bảng kê chuyển "đã thu đủ"; thiếu hoặc thừa thì hiện số chênh. Số còn nợ hiện ở đầu trang Đội xe.
5. **Xe thuê ngoài:** nếu cước của xe Trần Hùng đi qua mình (câu hỏi 2), thêm một bảng kê phải trả Trần Hùng, cùng mô hình nhưng chiều ngược lại.

**Bị chặn khi:** ngày tương lai (giờ VN); số tiền không phải số nguyên VND; sửa bảng kê đã đối chiếu mà không ghi điều chỉnh; tiền về lớn hơn số còn nợ mà không ghi rõ là trả trước.

## Hành vi và bất biến

- Tiền là số nguyên VND. Giá tính theo phần trăm phải làm tròn rõ ràng; quy tắc làm tròn: CÒN MỞ (10).
- Ô trống là NULL, không hiện là 0.
- Bảng giá có ngày áp dụng: đổi giá không làm đổi cước của các tháng đã khóa.
- Chi hộ không tính vào doanh thu, cũng không tính vào chi phí của đội xe.
- Mọi thao tác tiền ghi người làm và giá trị trước → sau; hủy tiền về bắt buộc lý do.

## Tiêu chí nghiệm thu

- [ ] Trên dữ liệu sao chép tháng 10: bảng giá tuyến dựng từ chính dữ liệu cho ra đúng cước ở ít nhất 99% của 272 dòng. Các dòng lệch được liệt kê.
- [ ] Đọc ghi chú dạng "_ Tên khoản số k" thành dòng phát sinh, khớp số phát sinh ở 271/272 dòng. Dòng lệch hiện cờ.
- [ ] Bảng kê xuất Excel có cùng cột với file hiện nay; tổng khớp tổng file tháng 10 tới từng đồng.
- [ ] Ghi tiền về, điều chỉnh, hủy: công nợ cước đổi đúng; Lịch sử có người làm, trước → sau, lý do.
- [ ] Harness PostgreSQL cho các bảng mới chạy xanh; `npm run check` xanh.
- [ ] Kế toán tự đi hết luồng ra bảng kê tháng 10 trên bản thử và xác nhận.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`).
- Review: opus (có ghi tiền).
- PR này chỉ có tài liệu (`specs/doi-xe-thu-01.md`). Code làm sau, khi đợt 1 đã merge.
- Cấm: chạy DDL, nạp dữ liệu thật, ghi Google Sheet; chép số tiền thật, số container, biển số, tên tài xế, tên khách vào repo.

## Hoàn tác

Revert PR. Không có dữ liệu.

## Bằng chứng

Đọc hai file công nợ cảng tháng 10/2026 và file BK (các tab tháng 3–4) ngày 18/11/2026, chỉ đọc. Các số đếm ở mục Hiện trạng đo bằng script đọc file, không sửa nguồn.

## Câu hỏi mở

1. ĐÃ TRẢ LỜI 18/11/2026: bảng kê gửi **công ty mẹ HTH**, vì đội xe là công ty con. (Mẫu BK tháng 3–4 từng ghi AS Logistics.)
2. Cước các chặng của xe Trần Hùng đi qua mình hay công ty hàng trả thẳng cho Trần Hùng? (Trùng câu 15 của `CHI-PHI-XE-01`.) Dữ liệu chỉ cho thấy cùng giá cước và văn phòng điều xe trả phí cảng cho xe Trần Hùng (kiểm 18/11/2026).
3. Chi hộ: ĐỀ XUẤT theo số đo 18/11/2026, chi hộ gồm kiểm hoá, hạ sớm, cân, xí cont, cont mới (vì thu đúng bằng chi); doanh thu gồm cước, đóng ghép, neo, nổ máy phát, phí bãi Đồng An. Cần người dùng xác nhận. (Trùng câu 13.)
4. ĐÃ TRẢ LỜI 18/11/2026: công ty hàng trả theo tháng, đủ bảng kê. Còn hỏi: hiện ai ghi tiền về?
5. Neo tính theo số ngày như dữ liệu cho thấy (mức ngày đầu + mỗi ngày thêm một mức)? Nổ máy phát tính theo giờ hay theo lần?
6. Đóng ghép tính theo số kho, theo khoảng cách, hay thỏa thuận từng chuyến?
7. Giá tuyến đổi khi nào, có đi theo giá dầu không?
8. ~~Tiền về trừ vào bảng kê cũ trước hay trừ đúng bảng kê?~~ Theo câu 4, tiền về gắn vào bảng kê tháng mà nó trả.
9. Ba cột đối chiếu trống ở tháng 10: việc đối chiếu với công ty hàng đang làm ở đâu (Zalo, file khác)?
10. Giá tính theo phần trăm làm tròn thế nào: tới nghìn đồng, hay tới đồng?
11. ĐÃ TRẢ LỜI 18/11/2026: phí nâng và phí hạ cảng do **đội xe chịu** trong cước. Ghi là dòng chi của chặng; người trả là tài xế hoặc người đi lệnh. Không đưa vào bảng kê.
