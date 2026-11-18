# Đội xe: chặng, thu, chi và nhập liệu trên web (CHI-PHI-XE-01)

Trạng thái: ĐỀ XUẤT (Claude, 18/11/2026). Những gì người dùng đã chốt ghi ở [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md). Chỗ ghi CÒN MỞ phải hỏi lại trước khi code phần đó.

## Mục tiêu

Người dùng chốt ngày 18/11/2026:

- Web giúp công ty **quản lý chi phí vận hành đội xe**.
- Có đủ dữ liệu để phân tích **vì sao xe chạy không có lời**.
- **Nhập liệu trên web**, thay các Sheet rời hiện nay.

Sổ hoàn tiền tài xế chỉ là một phần của mục tiêu này.

## Hiện trạng (đo 18/11/2026)

Chỉ đọc. Bản sao dữ liệu nằm ngoài Git, ở `captures/nha-xe/`.

Đội xe gồm 18 xe của công ty (nhóm VTP, NSX) và 5 xe thuê ngoài (Trần Hùng). Cùng một chuyến đang được ghi rải ở bốn nơi:

| Nơi ghi | Người ghi | Ghi gì của chuyến |
| --- | --- | --- |
| Sheet booking + sheet điều xe | Điều xe | Container, kho, shipper, ngày đóng, nhà xe, số xe |
| File điều xe "XE TIN PHAT" | Điều xe | Phí hạ, hạ sớm, hạ khác, phụ thu; các lần ứng và quyết toán |
| Sheet chi phí tài xế (10 xe) và file "BK TÍN PHÁT" (8 xe) | Hai nhân viên | Phí nâng, nâng hạ, cầu đường, neo, xí cont, VETC, sửa vặt |
| File công nợ cảng (Tín Phát, Trần Hùng) | Kế toán | Cước, đóng ghép, phát sinh tính cho công ty hàng |

Số đo:

- **Chặng hàng đã có trên nguồn chuyến của web.** File công nợ Tín Phát tháng 10/2026 có 204 dòng: 123 chặng chở hàng và 81 chặng phụ (chuyển cảng, trả rỗng, rút/thả mooc).
  - Cả 123 chặng hàng có container trong `CONT_NGUON`, nguồn chuyến của web; 122 chặng lệch ngày không quá 10 ngày.
  - Trần Hùng: 58/58 chặng hàng có trong `CONT_NGUON`, cả 58 lệch không quá 10 ngày.
  - Chặng phụ không có trong booking.
- **Web chưa biết xe nào chở container nào.** Ô `carrier` của chuyến trên web là hãng tàu.
  - Tab tổng hợp trong file điều xe, kéo từ sheet booking và sheet điều xe, có nhà xe và số xe cho 255/256 container tháng 10.
  - Nhưng tab này ghi nhà xe "TP" cho cả xe Trần Hùng. Muốn phân biệt xe mình với xe thuê phải dựa vào biển số.
- **Phí cảng của một chuyến nằm ở hai file.** Kiểm 42 chuyến tháng 10 có phí nâng ở sheet tài xế: cả 42 đều có trong file điều xe, ở đó phí nâng bằng 0 và các phí hạ được ghi.
- **Khoản lớn nhất không có ở file nào đã đọc:** dầu, lương tài xế, trả góp hoặc khấu hao, bảo hiểm, lốp, sửa chữa lớn.
- **Đã từng thử làm lãi lỗ trên Excel.** File BK tháng 3–4 có cột doanh thu, lợi nhuận, lương chuyến, đổ dầu.
  - 464 dòng, không dòng nào có doanh thu; cột lương trống; cột dầu có 1 dòng.
  - Lợi nhuận vì vậy ra âm đúng bằng chi phí.
  - Từ tháng 5, mẫu file bỏ hẳn phần doanh thu.
- **Doanh thu giữa các tài xế chênh 6,5 lần.** Theo file công nợ Tín Phát tháng 10: tài xế cao nhất có 22 dòng, thấp nhất có 4 dòng.

## Thu, chi và debit

- **Thu** là tiền đội xe được nhận: cước và phát sinh tính cho công ty hàng.
- **Chi** là tiền đội xe bỏ ra để chạy xe, trả ngay hay còn nợ đều tính.
- **Debit** là ai còn nợ ai. Số này tăng khi có bảng kê hoặc khi ứng tiền, giảm khi trả.
- Một khoản phát sinh có thể có cả dòng thu lẫn dòng chi, với số tiền khác nhau. Ví dụ cùng một chuyến tháng 10: số neo tính cho công ty hàng gấp 5 lần số neo tài xế thực chi. Đây là hai dòng riêng, không gộp chung một cột.
- **Chi hộ** (trả giùm rồi đòi lại đúng số) không phải thu, cũng không phải chi của đội xe. Khoản nào là chi hộ: CÒN MỞ (13).

| Khoản | Thu | Chi | Debit |
| --- | --- | --- | --- |
| Cước, phát sinh tính cho công ty hàng | Có | | Công ty hàng nợ đội xe |
| Phí nâng hạ, VETC, neo, sửa vặt | | Có, theo chặng | Tài xế chi thì công ty nợ tài xế tới khi hoàn |
| Dầu, lốp, sửa chữa lớn | | Có, theo xe | Mua chịu thì nợ nơi bán |
| Trả góp hoặc khấu hao, bảo hiểm, đăng kiểm, phí đường bộ, GPS, lương cứng | | Có, theo xe từng tháng | |
| Tiền ứng tài xế | | | Tài xế nợ công ty tới khi quyết toán |
| Cước thuê xe ngoài | | Có | Mình nợ nhà xe |

## Mô hình dữ liệu (ĐỀ XUẤT)

Dùng một schema PostgreSQL riêng tên `doixe`, nằm cùng cơ sở dữ liệu với sổ khách. Schema này chỉ đọc bảng của `sokhach`, không ghi vào đó.

| Bảng | Một dòng là | Ghi chú |
| --- | --- | --- |
| `xe` | một đầu kéo | Biển số chuẩn, nhóm (VTP, NSX, thuê ngoài), ngày vào, ngày ra |
| `tai_xe` | một tài xế | |
| `chang` | một chặng một xe chạy | Ngày, xe, tài xế, loại chặng (hàng, chuyển cảng, trả rỗng, rút mooc, thả mooc, khác), container, nơi lấy, nơi hạ. Chặng hàng trỏ tới chuyến khách theo container + ngày |
| `dong_thu` | một khoản thu của chặng | Loại theo danh mục, số tiền, có phải chi hộ không |
| `dong_chi` | một khoản chi | Gắn với chặng, **hoặc** với xe + tháng. Loại theo danh mục. Người trả: tài xế, công ty, người đi lệnh, mua chịu |
| `ung`, `dot_hoan` | một lần ứng, một đợt hoàn | Đợt hoàn gom các dòng chi do tài xế trả |
| `dinh_phi` | một khoản cố định của xe | Số tiền, kỳ, từ ngày đến ngày; web tự chia theo ngày |

Không lưu số tổng nào cho người sửa tay. Web tự tính:

- **Lãi chặng** = tổng dòng thu − tổng dòng chi của chặng.
- **Lãi xe trong tháng** = tổng lãi chặng − chi phí xe trong tháng − phần định phí chia theo ngày.
- **Số dư tài xế** = tổng tài xế chi − tổng đã hoàn − tổng đã ứng (ĐÃ CHỐT).
- **Chi phí trên km, số ngày xe nằm:** tính khi có số km, CÒN MỞ (11).

## Ai nhập gì (ĐỀ XUẤT)

| Người | Nhập trên web | Thay cho |
| --- | --- | --- |
| Điều xe | Gán xe, tài xế cho chuyến hàng có sẵn từ booking; thêm chặng phụ | Cột số xe ở sheet điều xe |
| Hai nhân viên | Chi phí từng chặng (chọn chặng, gõ hoặc dán tiền theo cột như Sheet, chọn người trả); ghi ứng, đợt hoàn | Sheet chi phí tài xế, file BK, phần phí cảng của file điều xe |
| Kế toán | Đợt 2: thu theo bảng giá tuyến + phát sinh, bảng kê gửi công ty hàng. Đợt 3: dầu, sửa chữa, lốp, định phí, lương | File công nợ cảng, các file chi phí khác |

Chạy song song với Sheet một tháng để so số, rồi bỏ Sheet: ĐỀ XUẤT.

## Người dùng và luồng đợt 1 (bước 1)

**Người thao tác:**

- Hai nhân viên văn phòng và điều xe, làm trên máy tính màn 1280×720.
- Tài xế **không** dùng web ở đợt 1.
- Người quản lý xem số liệu.
- Đăng nhập và quyền theo `ACCESS-01`, như sổ khách.

**Luồng chính:**

1. **Mở Đội xe:** menu trái có mục "Đội xe", gồm hai bảng.
   - Bảng xe: biển số, tài xế đang chạy, số chặng trong tháng, số chặng chưa có chi phí.
   - Bảng tài xế: số dư (dương là công ty còn nợ tài xế, âm là tài xế còn giữ tiền ứng).
2. **Gán xe:** điều xe mở danh sách chuyến hàng từ booking chưa gán xe (lọc theo ngày, kho), rồi chọn xe và tài xế. Thêm chặng phụ (chuyển cảng, trả rỗng, mooc) cho một container.
3. **Nhập chi phí chặng:**
   - Bảng kiểu Sheet theo xe và tháng, dùng lại cách nhập của `NHAP-SHEET-01`. Mỗi dòng là một chặng, các cột là loại phí.
   - Dán được khối dòng chép từ Sheet cũ.
   - Cột "Người trả" mặc định là tài xế; riêng VETC mặc định là công ty.
4. **Ghi ứng:** nút "Ghi ứng" → số tiền, ngày chuyển, ghi chú → xem lại → ghi.
5. **Hoàn tiền theo đợt:** nút "Hoàn tiền" → tích các dòng chi tài xế trả mà chưa hoàn → nhập ngày chuyển và số tiền thực chuyển → ghi. Các dòng đó đánh dấu "Đã hoàn ngày …".
6. **Sửa, hủy:**
   - Sửa ô thì ghi Lịch sử trước → sau.
   - Hủy một lần ứng hoặc một đợt hoàn **bắt buộc lý do**. Hủy đợt hoàn thì các dòng chi trở lại "chưa hoàn".

**Bị chặn khi:**

- Ngày ở tương lai (giờ VN).
- Số tiền không phải số nguyên VND.
- Đợt hoàn không có dòng nào.
- Dòng có tiền nhưng không gắn được chặng.

Chặng hàng không tìm thấy chuyến khách (theo container, lệch không quá 10 ngày) vẫn ghi được, nhưng gắn cờ "chưa nối chuyến khách".

## Đối chiếu cột Sheet chi phí hiện tại (bước 2)

Sheet "TÀI XẾ T10" và các tab tháng 5 đến tháng 11 của "BK TÍN PHÁT" dùng chung một mẫu: dòng 2 là tiêu đề, dòng 1 là tổng từng cột.

| Cột Sheet | Trường web | Ghi chú |
| --- | --- | --- |
| STT, TRÂN/GL | — | Đang bị dùng để ghi ngày hoàn ("14/10") và "da tt" |
| NGÀY | `chang.ngay` | Chuỗi tháng/ngày/năm (`10/2/2026` = 2/10) |
| SỐ CONT, CONT KÉO | `chang.container` | Một container có thể đi nhiều chặng |
| TỈNH, KHO, NƠI LẤY, NƠI HẠ, TÊN HÀNG | thông tin chặng | Chặng hàng lấy sẵn từ chuyến khách |
| TÀI XẾ, Số xe | `chang.tai_xe`, `chang.xe` | Biển số ghi không thống nhất giữa các file |
| PHÍ NÂNG, NÂNG HẠ, CẦU ĐƯỜNG, NEO, XÍ CONT/TRÁI TUYẾN/XE NÂNG, ĐẢO CONT, CONT MỚI, DỜI CONT, MUA SEAL, BÃI CHỜ, ĐIỀU ĐỘ, ĐỔ DẦU, PHÁT SINH, NỔ MÁY PHÁT | `dong_chi`, người trả = tài xế | Danh mục phí, cách làm như `PHU-PHI-01` |
| GHI CHÚ | ghi chú dòng chi | Diễn giải phát sinh (vá vỏ, tưới vỏ…) |
| CẦU ĐƯỜNG (VETC) CTY THANH TOÁN | `dong_chi`, người trả = công ty | Không cộng vào phần hoàn tài xế |
| Cột cuối không tiêu đề | tổng tài xế chi của chặng | Đã kiểm trên 3 dòng mẫu ở hai file: bằng tổng phí tài xế trả, không gồm VETC |

**Code dùng lại được:**

- Đăng nhập, danh tính người thao tác, Lịch sử dạng sự kiện.
- Khóa trùng lệnh ở `so-khach-v7-api.js`.
- Lưới nhập kiểu Sheet và dán khối (`NHAP-SHEET-01`); danh mục và dòng phụ phí (`PHU-PHI-01`).
- Chuyến khách đồng bộ từ `CONT_NGUON`; triển khai, backup mỗi giờ, canh lỗi email trên `hao`.

**Còn thiếu:** schema `doixe`, API `/api/v7/doixe/*`, màn Đội xe.

## Phân kỳ

| Đợt | Nội dung | Thay cho |
| --- | --- | --- |
| 1 | Xe, tài xế, chặng (gán xe cho chuyến booking, chặng phụ), chi phí chặng, ứng, hoàn, số dư tài xế | Sheet chi phí tài xế, file BK, phí cảng trong file điều xe |
| 2 | Thu theo bảng giá tuyến + phát sinh, bảng kê và debit công ty hàng; phải trả xe thuê ngoài | File công nợ cảng |
| 3 | Chi phí xe theo tháng (dầu, sửa chữa, lốp, định phí, lương), lãi lỗ theo chặng/xe/tháng, phân tích vì sao lỗ | Chưa có file nào |

Đợt 1 làm trước theo lựa chọn của người dùng. Thứ tự đợt 2 và đợt 3: CÒN MỞ (14).

## Nguồn quyết định

- [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md): mục tiêu, phạm vi, nhập trên web, công thức số dư.
- Áp dụng nguyên các quy tắc tiền chung của `AGENTS.md`: VND nguyên, NULL không phải 0, mọi thao tác tiền ghi người làm và trước → sau, hủy bắt buộc lý do, cấm ngày ghi tương lai.
- Khóa tháng (`V7-SO`) có áp dụng cho đội xe không: CÒN MỞ (4).

## Hành vi và bất biến

- Tiền là số nguyên VND. Số Sheet có phần lẻ (ví dụ công thức `=giá*70%`) bị chặn khi dán; người nhập tự làm tròn.
- Ô phí trống là NULL: không hiện 0 và không cộng vào tổng.
- Chặng hàng chỉ đọc chuyến khách, không làm đổi số nợ của sổ khách.
- Xe mình hay xe thuê xác định theo danh sách xe, không theo chữ "nhà xe".
- Một dòng chi thuộc tối đa một đợt hoàn chưa hủy.
- Mọi số tổng và số dư tính lại được từ các dòng gốc.

## Chỗ dễ sai trong dữ liệu hiện tại

1. Dòng không có ngày, không có container nhưng vẫn có tiền nâng hạ, và vẫn được cộng vào tổng tab.
2. Cột STT và TRÂN/GL bị dùng để ghi ngày hoàn và "da tt".
3. Sheet chi phí ghi ngày dạng tháng/ngày, file điều xe ghi ngày/tháng.
4. Biển số ghi thiếu tỉnh ("44115") ở file này, đủ ("50H-44115") ở file khác.
5. Cột nhà xe ghi "TP" cho cả xe thuê ngoài.
6. Một container của xe thuê ngoài lại mang biển số xe mình trong tab tổng hợp của file điều xe.
7. Trong file công nợ tháng 10, hai tài xế khác nhau cùng ghi một biển số.
8. Tiền có phần lẻ do công thức nhân phần trăm.

## Tiêu chí nghiệm thu (đợt 1)

- [ ] Trên bản thử (dữ liệu sao chép), 123 chặng hàng tháng 10 của Tín Phát gán được xe và nối được chuyến khách, lệch không quá 10 ngày; chặng phụ nhập được.
- [ ] Dán 1 tab tài xế tháng 10/2026: tổng "tài xế chi" và tổng từng cột phí khớp dòng tổng của tab, trừ các dòng bị chặn đã liệt kê.
- [ ] Ghi ứng, ghi đợt hoàn, hủy từng loại: số dư đổi đúng; Lịch sử có người làm, trước → sau, lý do hủy.
- [ ] Bấm hai lần hoặc mất mạng giữa chừng không tạo hai lần ứng hay hai đợt hoàn.
- [ ] Harness PostgreSQL cho schema `doixe` chạy xanh; `npm run check` xanh.
- [ ] Kiểm trình duyệt 1280×720: bàn phím, nhập sai, tải chậm, thiếu quyền.
- [ ] Hai nhân viên và điều xe tự đi hết luồng trên bản thử với dữ liệu một tháng, và xác nhận.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`).
- Review: opus (có ghi tiền).
- Được sửa: PR này chỉ có tài liệu (`specs/chi-phi-xe-01.md`, `docs/decisions/chi-phi-xe-01.md`, `docs/decisions.md`). Các PR code sau sẽ ghi phạm vi file riêng.
- Cấm: chạy DDL, nạp dữ liệu thật, ghi Google Sheet.

## Hoàn tác

Revert PR. Không có dữ liệu.

## Bằng chứng

Đọc nguồn ngày 18/11/2026, chỉ đọc:

- 2 file công nợ cảng tháng 10/2026.
- Sheet "TÀI XẾ T10".
- File Drive "XE TIN PHAT" và "BK TÍN PHÁT - TRÂN".
- Tab `CONT_NGUON` (cột số cont, ngày đóng, booking, chủ hàng).

Các số trong mục Hiện trạng được đo bằng script đọc file, không sửa nguồn. Chưa có code, chưa có bản thử.

## Câu hỏi mở

1. ~~Số dư = tài xế chi − đã hoàn − đã ứng, một số dư chung mỗi tài xế?~~ ĐÃ TRẢ LỜI 18/11/2026: đúng.
2. Khối "LẦN ỨNG" trong file điều xe (nhiều lần 20 triệu một tháng) là ứng cho từng tài xế, hay cho người đi lệnh trả phí cảng?
3. ĐỀ XUẤT: tiền (ứng, hoàn, số dư) theo tài xế; chặng và chi phí theo xe. Mỗi chặng ghi cả xe lẫn tài xế. Cần xác nhận.
4. Có khóa tháng như sổ khách không, hay sửa lúc nào cũng được miễn có Lịch sử?
5. Bắt đầu từ tháng nào, và số dư đầu của từng tài xế lấy ở đâu? Nạp dữ liệu thật cần người dùng duyệt riêng.
6. Cột "Nổ máy phát" có tính vào phần hoàn tài xế không? Trong dữ liệu đã đọc, cột này trống.
7. Dầu đổ ở đâu, trả thế nào (cây dầu ghi nợ, thẻ, tài xế tự trả)? Có hóa đơn theo từng xe không?
8. Lương tài xế tính theo chuyến, lương cứng hay cả hai? Đang ghi ở đâu?
9. Định phí từng xe (trả góp hoặc khấu hao, bảo hiểm, đăng kiểm, phí đường bộ, GPS) do ai giữ số?
10. Sửa chữa lớn và lốp đang ghi ở đâu?
11. Xe gắn định vị của hãng nào, có xuất được km theo ngày không?
12. Tháng đầu, web đọc số xe từ sheet điều xe để khỏi gõ hai lần, hay điều xe gán trên web ngay?
13. Khoản nào là chi hộ (đòi lại công ty hàng đúng số đã trả)?
14. Sau đợt 1, làm thu và bảng kê (đợt 2) trước, hay chi phí xe và lãi lỗ (đợt 3) trước?
