# Đội xe: điều độ, chặng sinh từ booking (DOI-XE-DIEU-DO-01)

Trạng thái: nguyên tắc ĐÃ CHỐT (người dùng, 19/11/2026: chặng sinh từ booking, điều xe phân công trên web; [`DOI-XE-DIEU-DO-01`](../docs/decisions/doi-xe-dieu-do-01.md)). Luồng, mô hình dữ liệu và thứ tự các bước dưới đây là ĐỀ XUẤT (Claude), chưa code. Chỗ ghi CÒN MỞ phải hỏi trước khi code phần đó. Bức tranh chung: [Đội xe: bản đồ dữ liệu và kiến trúc](../docs/doi-xe-kien-truc-du-lieu.md).

## Mục tiêu

- Danh sách việc của đội xe tự có từ booking của HTH. Không ai gõ lại container, kho, ngày đóng, cảng.
- Điều xe chỉ ghi điều chỉ mình biết: xe nào, tài xế nào chạy, và chặng phụ nào phát sinh.
- Chi phí, bảng kê, và về sau dầu, lương, lãi lỗ dùng chung một danh sách chặng.
- Thay phần chuyến của file điều xe và các bảng chuyến chép lại.

## Hiện trạng (đo 19/11/2026, chỉ đọc)

Bản xuất các nguồn nằm ngoài Git. Số dưới đây là số đếm.

**Cùng một việc đang được ghi ở ba nơi trước khi lên bảng kê.** HTH ghi dòng booking. File điều xe ghi lại số booking, container, seal, nơi đóng, tàu, cảng, nhiệt độ, kèm xe và tài xế. Sheet chi phí tài xế ghi lần nữa ngày, container, kho, nơi lấy, nơi hạ, tên hàng. Bảng kê đi sau sheet chi phí: cả 144 container trên bảng kê tháng 10 đều có dòng chi phí.

**Danh sách của điều xe chính là booking lọc theo nhà xe.**

- Tab booking tháng 10 có 265 dòng, 254 dòng có số cont. Cột nhà xe có 11 giá trị. Đội xe nhận hai mã: 166 container.
- Tab tháng 10 của file điều xe có 205 dòng, 203 container. Cả 205 dòng đều là dòng booking mang mã của đội xe (ở tab booking tháng 9, 10 hoặc 11).
- Chiều ngược lại, container mang mã đội xe trên booking có trong file điều xe: 139/141 (tháng 9), 166/166 (tháng 10), 89/89 (tháng 11, tới lúc đo).
- Có một mã khác trùng một phần chữ với mã đội xe. Công thức lọc của file điều xe bắt nhầm mã này, nhưng điều xe không chạy container nào của nó (0/31). Vì vậy phải so nguyên mã.

**Ngày của điều xe là ngày đóng hàng.** Tab tháng 10: 190 dòng đọc được cả hai ngày, trùng ngày ở 180 dòng, lệch một ngày ở 8 dòng, lệch 4–10 ngày ở 2 dòng. Chặng hàng trên bảng kê tháng 10: trùng ngày đóng ở 114/123 dòng, lệch một ngày ở 8 dòng.

**Số booking không làm khóa được.** Ở tab tháng 10 của file điều xe, số booking trùng với booking HTH ở 103/205 dòng; 62 dòng một bên chứa bên kia; 38 dòng khác hẳn. Container và ngày đóng mới là khóa.

**Web đã đọc gần đủ, chỉ thiếu cột nhà xe.** Tab `CONT_NGUON` mà web đọc ứng từng dòng với tab booking: cùng số dòng và cùng container ở 254/254 dòng (tháng 10) và 207/207 dòng (tháng 11). Công thức dựng tab này tìm cột theo tên tiêu đề.

**Việc được giao trước khoảng một ngày; số cont có sau.** Lúc đo, tab booking tháng 11 có 211 dòng. 207 dòng ngày đóng đã qua đều đã có nhà xe, số cont và seal. 4 dòng có ngày đóng sau lúc đo: 3 dòng đã có mã đội xe, chưa dòng nào có số cont. Cùng lúc file điều xe có 3 dòng đã có xe và ngày mà chưa có số cont.

**Mã nhà xe không cho biết xe công ty hay xe thuê.** 63/203 container tháng 10 do 5 xe thuê ngoài chạy; file điều xe chép 63 dòng này sang một tab riêng. Không chặng hàng nào của 63 container đó nằm trên bảng kê của đội xe. Phân biệt bằng biển số, như [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md) đã ghi.

**Chặng phụ không có dòng riêng ở booking lẫn file điều xe.** Bảng kê tháng 10 có 204 dòng: 123 chặng hàng, 79 chuyển cảng, 1 trả rỗng, 1 rút mooc.

- Chuyển cảng chỉ xuất hiện ở sheet chi phí tài xế rồi lên bảng kê. Container của nó thì có trên booking: 78/79, trong đó 73 mang mã đội xe và 5 do nhà xe khác kéo chặng hàng.
- 59 container có cả chặng hàng lẫn chuyển cảng của đội xe. Chuyển cảng chạy sau chặng hàng 1–5 ngày ở 52 container, từ 9 ngày trở lên ở 7 container.

**Ba sổ nối được thì thấy ngay chỗ hở.** Xe công ty chạy 127 container có ngày đóng trong tháng 10. 122 container có chặng hàng trên bảng kê tháng 10. 5 container còn lại: 1 lên bảng kê là trả rỗng, 1 chỉ có chặng chuyển cảng, 3 không có dòng nào (1 trong đó đóng ngày cuối tháng, có thể sang bảng kê tháng sau). Ngoài ra 1 container có hai chặng hàng cách nhau 14 ngày trong khi booking chỉ có một dòng. Hôm nay muốn thấy các chỗ này phải dò tay ba file.

## Người dùng và luồng (ĐỀ XUẤT)

**Người thao tác:**

- Điều xe: phân công, thêm chặng phụ. Thiết bị và số người: CÒN MỞ (5).
- Hai nhân viên: nhập chi phí như đợt 1, nhưng vào chặng đã có.
- Kế toán: bảng kê như đợt 2, không đổi.
- Đăng nhập và quyền theo `ACCESS-01`. Điều xe cần được thêm vào danh sách cho phép.

**Màn Điều độ** (mục mới trong Đội xe). Mỗi dòng là một việc: một container trên booking giao cho đội xe.

1. **Việc tự xuất hiện** khi dòng booking có mã nhà xe của đội xe, có ngày đóng và số cont. Dòng chưa có số cont hiện mờ ở nhóm "Sắp tới", chưa phân xe được: CÒN MỞ (3).
2. **Mặc định hiện** việc có ngày đóng hôm nay và hôm qua, cộng mọi việc cũ hơn còn chờ phân xe. Lọc theo ngày, kho, xe, tài xế, trạng thái.
3. **Cột:** ngày đóng, container, kho đóng hàng, hàng, cảng và hãng tàu, số booking, khách; xe và tài xế; chặng phụ; trạng thái. Seal, nhiệt độ, tên tàu hiện khi nguồn có.
4. **Phân xe ngay trên dòng.** Gõ vài số cuối của biển hoặc tên tài xế rồi Enter.
   - Tài xế lấy theo xe (tài xế đang chạy xe đó), đổi được.
   - Ngày chạy mặc định là ngày đóng, sửa được.
   - Lưu là có chặng hàng. Nơi lấy, nơi hạ, kho, tỉnh, tên hàng lấy từ booking; tuyến cước gợi ý theo tên gốc như đợt 2.
5. **Chặng phụ:** nút "+ chặng" trên dòng, chọn chuyển cảng, trả rỗng, rút mooc hoặc thả mooc, rồi chọn xe và ngày. Một container có nhiều chặng, mỗi chặng một xe.
6. **Chặng ngoài booking:** dùng cho container không phải việc của đội xe trên booking, ví dụ chuyển cảng cho container nhà xe khác kéo. Phải gõ container, ngày, loại, xe.
7. **Đổi hoặc bỏ phân công.** Chặng chưa có phí, chưa hoàn, chưa lên bảng kê đã gửi: đổi xe, tài xế, ngày hoặc bỏ tự do, có Lịch sử. Chặng đã có một trong ba thứ đó: theo luật sửa và xóa chặng của đợt 1.
8. **Booking đổi sau khi phân xe.** Web so lại theo nhịp đồng bộ đang có (15 phút).
   - Đổi ngày đóng, kho, cảng: dòng hiện nhãn "booking đã đổi" kèm trước → sau. Điều xe bấm nhận để cập nhật chữ của chặng, hoặc giữ.
   - Đổi số cont, hoặc việc bị giao cho nhà xe khác: chặng cũ mang nhãn "không còn trên booking". Người quyết sửa container của chặng hay bỏ chặng.
   - Web không tự sửa và không tự xóa chặng.

**Trạng thái của việc** do web tính, không ai gõ: Sắp tới → Chờ phân xe → Đã phân xe → Đã có phí → Đã lên bảng kê. Đầu màn có bộ đếm, bấm là lọc: Chờ phân xe, Chưa có phí, Booking đã đổi, Chặng ngoài booking.

**Nhập chi phí (đổi so với đợt 1):**

- Ở sổ tài xế và sổ xe, chặng đã phân xe hiện sẵn với tình trạng "Chưa có phí". Nhân viên gõ tiền vào dòng đó.
- Hàng trống vẫn còn, dùng cho chặng ngoài booking.
- Dán khối từ Sheet vẫn còn để chuyển dữ liệu cũ. Dòng dán trùng container, xe, loại với một chặng đã có và ngày lệch không quá 3 ngày thì ghi tiền vào chặng đó, không tạo chặng mới.

**Bị chặn:**

- phân xe cho việc đã có chặng hàng chưa bỏ;
- chọn xe đã ngừng dùng;
- ngày chạy sau hôm nay (giờ VN), trừ khi bằng đúng ngày đóng của việc (xe lấy rỗng hôm nay, đóng hàng hôm sau);
- ghi tiền vào chặng có ngày chạy sau hôm nay.

## Nguồn dữ liệu (ĐỀ XUẤT)

- **Cần thêm cột nhà xe vào nguồn chuyến của web.** Hai cách:
  - A. Thêm cột vào `CONT_NGUON`: thêm một lần tìm tiêu đề "NHÀ XE" và một cột đầu ra trong công thức của tab. Bộ đọc của web tìm cột theo tên, nên luồng sổ khách không đổi.
  - B. Máy đọc thẳng file booking (giai đoạn 2b của [hợp đồng Sheet](v7-sheet-contract.md)). Cần chủ file chia sẻ cho tài khoản máy.

  Đề xuất làm A trước. Sửa Sheet cần người dùng đồng ý riêng: CÒN MỞ (2).
- **Nên thêm cùng lúc:** số seal và nhiệt độ. Tab booking điền gần đủ hai ô này và file điều xe đang ghi lại cả hai.
- **Tên tàu và chuyến tàu:** tab booking tháng 10 chỉ điền tên tàu ở 95/265 dòng, trong khi file điều xe điền ở 203/205 dòng. Điều xe đang có nguồn khác cho hai ô này: CÒN MỞ (6).
- **Mã nhà xe của đội xe** là danh mục trong cơ sở dữ liệu, không cố định trong code. So nguyên mã, không so chuỗi con: CÒN MỞ (1).
- Web dùng bản chụp booking đã có trên `hao`. Không thêm đường đồng bộ mới, không ghi Sheet.

## Mô hình dữ liệu (ĐỀ XUẤT)

- **Không thêm bảng "việc".** Việc là dòng booking của đội xe, đọc từ bản chụp nguồn. Chặng vẫn là dòng duy nhất mang tiền, đúng như đợt 1–2.
- **`chang` thêm hai ô:**
  - ngày đóng của việc mà chặng phục vụ; NULL với chặng ngoài booking và chặng đã có từ trước. Container cùng ngày đóng gom các chặng của một việc, kể cả chuyển cảng chạy nhiều ngày sau.
  - nguồn tạo: điều độ, nhập chi phí, hay nạp.
- **Nối việc với chặng:**
  - cùng container;
  - chặng có ngày đóng: ngày đóng của hai bên lệch không quá 3 ngày. Đây là luật ±3 ngày của [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md), chịu được việc Sheet sửa ngày;
  - chặng cũ chưa có ngày đóng: theo ngày chặng, lệch không quá 10 ngày, gần nhất trước, như đợt 1;
  - mỗi việc nhiều nhất một chặng hàng chưa bỏ.
- **Danh mục mới:** mã nhà xe trên booking mà đội xe nhận.
- **Lịch sử** thêm các việc: phân xe, đổi phân công, bỏ phân công, nhận thay đổi của booking.
- Chặng bản thử tháng 10–11 đã nạp không phải làm lại: theo luật nối trên, chúng sẽ khớp việc theo container và ngày.

## Đối chiếu dữ liệu và code hiện có

**Dùng lại được:**

- Bản chụp booking 15 phút một lần và bộ đọc tìm cột theo tên (`tools/sheet_sync_runner.py`, `tools/webdebit_export_connector.py`).
- Bảng `xe`, `nguoi`, `chang` và các lệnh `luu_chang`, `sua_chang`, `xoa_chang` của đợt 1.
- Cách nối chuyến khách theo container (`doixe._chuyen_ds`).
- Tuyến cước và tên gốc của đợt 2.
- Lịch sử, chống ghi trùng lệnh, khóa tháng.

**Còn thiếu:**

- cột nhà xe trong bản chụp; danh mục mã nhà xe;
- hai ô mới của `chang`; lệnh phân xe, đổi, bỏ;
- đường đọc danh sách việc và trạng thái;
- màn Điều độ;
- ghép dòng dán vào chặng đã có.

## Phí cảng do người đi lệnh trả (bước sau)

File điều xe còn giữ năm cột phí cảng (195/205 dòng tháng 10 có phí) và các lần ứng của người đi lệnh. Mô hình đợt 1 gán một người trả cho cả chặng. Thực tế một chặng có khoản tài xế trả và khoản người đi lệnh trả. Cần đưa "người trả" về từng khoản chi.

Đây là thay đổi đường ghi tiền, cần spec và quyết định riêng: CÒN MỞ (7). Tới lúc đó điều xe vẫn giữ phần phí cảng trong file của mình; phần chuyến thì bỏ được.

## Các bước (ĐỀ XUẤT)

| Bước | Nội dung | Cần gì trước |
| --- | --- | --- |
| 1 | Nguồn: cột nhà xe (và seal, nhiệt độ) vào bản chụp; danh mục mã nhà xe | Người dùng đồng ý sửa Sheet; xác nhận danh sách mã |
| 2 | Bản bấm thử màn Điều độ, dữ liệu giả | Không |
| 3 | Schema và hàm ghi, harness PostgreSQL; API; màn Điều độ | Người dùng và điều xe thử bản bấm rồi chốt luồng |
| 4 | Đổi đường nhập chi phí: chặng có sẵn, dán khối ghép vào chặng đã có | Bước 3 |
| 5 | Đối chiếu: việc chưa phân xe, chặng chưa có phí, chặng chưa lên bảng kê | Bước 3 |

Bước 2 làm song song với bước 1 được.

## Nguồn quyết định

- [`DOI-XE-DIEU-DO-01`](../docs/decisions/doi-xe-dieu-do-01.md): chặng sinh từ booking, điều xe phân công trên web.
- [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md), [`DOI-XE-THU-01`](../docs/decisions/doi-xe-thu-01.md): luật chặng, chi phí, ứng, hoàn, khóa tháng, bảng kê. Giữ nguyên, trừ mặc định 1 của đợt 1.
- [`NGUON-CHUYEN-01`](../docs/decisions/nguon-chuyen-01.md): luật ghép ±3 ngày theo container.
- Luật tiền chung của `AGENTS.md`.

## Hành vi và bất biến

- Web không ghi Sheet và không ghi vào schema `sokhach`.
- Máy không tự tạo, sửa hay xóa chặng. Mọi chặng do người phân công hoặc nhập, có ghi người làm.
- Một việc nhiều nhất một chặng hàng chưa bỏ. Một container có nhiều chặng.
- Xe công ty hay xe thuê xác định theo danh sách xe, không theo mã nhà xe.
- Booking đổi không làm đổi tiền đã ghi và không đổi bảng kê đã gửi.
- Bấm lặp hoặc gửi lại sau mất mạng chỉ tạo một chặng.
- Luật tiền, khóa tháng, hoàn, bảng kê của đợt 1–2 giữ nguyên.

## Tiêu chí nghiệm thu

- [ ] Trên bản sao tháng 10: mọi dòng booking mang mã đội xe hiện thành việc; dòng mã khác không hiện; mã trùng một phần chữ không bị bắt nhầm.
- [ ] Chặng bản thử tháng 10–11 đã nạp tự khớp việc, không phải phân xe lại. Chặng không khớp được liệt kê.
- [ ] Phân xe, đổi, bỏ: Lịch sử có người làm, trước → sau. Ba lệnh song song cùng mã chỉ tạo một chặng (harness PostgreSQL).
- [ ] Dán lại một tab chi phí tháng 10 sau khi đã có chặng từ điều độ: không sinh chặng trùng.
- [ ] Booking đổi ngày đóng, đổi số cont, đổi nhà xe sau khi phân xe: nhãn đúng, không chặng nào tự đổi.
- [ ] Kiểm trình duyệt 1280×720 và 1265×560: bàn phím (gõ biển số, Enter), nhập sai, tải chậm, mất mạng, thiếu quyền.
- [ ] Điều xe tự làm trọn một ngày thật trên bản thử, không mở file điều xe cho phần chuyến, và xác nhận.
- [ ] `npm run check` xanh; harness `doixe` xanh.

## Phạm vi agent

- Agent: claude (theo `CLAUDE-ALL-01`).
- Review: opus (đổi schema `doixe` và đường ghi).
- PR này chỉ có tài liệu. Code làm theo từng bước ở trên, mỗi bước một PR.
- Cấm: ghi Google Sheet, nạp dữ liệu, chạy DDL trên `hao` khi chưa tới bước và chưa có đồng ý; chép tên khách, container, biển số, mã nhà xe vào repo.

## Hoàn tác

Revert PR. Không có dữ liệu.

## Bằng chứng

Đọc ngày 18–19/11/2026, chỉ đọc, không ghi Sheet, cơ sở dữ liệu hay `hao`:

- tab booking tháng 9, 10, 11 và tab `CONT_NGUON`;
- file điều xe (tab tháng 9, 10, 11 và hai tab xe thuê);
- bảng kê cước tháng 10 của đội xe;
- sheet chi phí tài xế tháng 10.

Số đếm đo bằng script đọc bản xuất; bản xuất và script nằm ngoài Git. Chưa đọc bảng kê của nhà xe thuê ngoài và bảng kê tháng 11. Chưa hỏi điều xe.

## Câu hỏi mở

1. Mã nhà xe của đội xe trên booking: đo thấy điều xe nhận đúng hai mã, và một mã trùng một phần chữ không phải của đội xe. Người dùng xác nhận danh sách.
2. Đưa cột nhà xe vào nguồn theo cách A hay B? Nếu A, ai sửa công thức `CONT_NGUON`?
3. Điều xe có cần phân xe trên web trước khi có số cont không (lập kế hoạch hôm sau), hay ghi trong ngày là đủ? Lúc đo chỉ có 3–4 việc như vậy.
4. Chuyển cảng phát sinh khi nào và ai quyết? Có đoán trước được từ booking không? Khoảng 4 trên 10 dòng bảng kê tháng 10 là chuyển cảng.
5. Điều xe dùng máy tính hay điện thoại, mấy người, đã vào được web chưa?
6. Seal, trọng lượng tối đa của container, tên tàu và chuyến tàu: điều xe lấy từ đâu, và có cần ghi trên web không hay chỉ cần xem?
7. Có làm "người trả theo từng khoản chi" (phí cảng người đi lệnh trả) ngay sau bước phân xe không?
8. Việc bị giao lại cho nhà xe khác sau khi đã phân xe có xảy ra không, và khi đó xử lý thế nào?
