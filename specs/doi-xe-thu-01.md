# Đội xe đợt 2: thu cước, bảng kê và công nợ cước (DOI-XE-THU-01)

Trạng thái: luồng ĐÃ CHỐT 18/11/2026 ([`DOI-XE-THU-01`](../docs/decisions/doi-xe-thu-01.md), người dùng "Chốt mockup" sau khi bấm thử); mô hình dữ liệu và cách tính ĐÃ CODE (PR #491), chưa triển khai. Đây là đợt 2 của mục tiêu [`CHI-PHI-XE-01`](../docs/decisions/chi-phi-xe-01.md), xem [spec đợt 1](chi-phi-xe-01.md). Đợt 1 đã chạy trên `hao` (18/11/2026), nên đợt 2 code được ngay trên schema `doixe` của đợt 1.

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

## Mô hình dữ liệu (ĐÃ CODE)

Migration `cong-no-web-handoff/tools/migrations/2026-11-18-v7-doi-xe-thu.sql` (PR #491), nối vào schema `doixe`, áp sau migration đợt 1 và migration phiếu chi; rồi `2026-11-18-v7-doi-xe-thu-doc-ghi-chu.sql` thay bộ đọc ghi chú bằng bản sửa sau review độc lập (bản đầu đã áp trên `hao` trước khi có bản sửa). Chỉ đọc bảng của `sokhach`, không ghi vào đó. Harness: `cong-no-web-handoff/tools/test_pg_doixe_thu.py`.

| Bảng | Một dòng là | Ghi chú |
| --- | --- | --- |
| `ben` | một bên nhận bảng kê | Hiện một dòng: HTH, nhận chặng của xe công ty (`xe_thue_ngoai = false`). Bảng kê riêng cho xe Trần Hùng thêm một dòng khi câu 2 có trả lời |
| `tuyen`, `tuyen_ten_goc` | một tuyến chuẩn; một tên gốc | Tuyến hàng (hàng + đi + đến tùy chọn), tuyến chuyển cảng, trả rỗng. Tên gốc là `TÊN HÀNG\|TỈNH` đã chuẩn hóa (bỏ dấu, chữ hoa, dấu câu thành khoảng trắng), chỉ cho tuyến hàng; mỗi tên gốc trỏ một tuyến |
| `gia_tuyen` | một mức giá từ một ngày | Theo bên nhận và tuyến; giá của chặng là bản có ngày áp dụng lớn nhất không sau ngày chặng. Ngày áp dụng được trước tới một năm |
| `phat_sinh`, `phat_sinh_ten` | một khoản phát sinh; một tên đọc được | Cách tính, mức (để trống tới khi người dùng ghi), chi hộ, cột trên bảng kê (phát sinh hay đóng ghép), loại phí phía chi tương ứng |
| `thu_chang` | phần thu riêng của một chặng chưa gửi | Tuyến gắn tay, giá cước nhập tay. Không có dòng: theo tên gốc và bảng giá |
| `bang_ke` | một bảng kê đã gửi | Số bảng kê `HTH-yyyy-mm`; trạng thái đã gửi → đã đối chiếu; thu đủ là tiền về bằng số đòi |
| `bang_ke_dong` | một dòng chép lúc gửi | Chữ và số như lúc gửi (tài xế, xe, tuyến, cước, đóng ghép, phát sinh, chi hộ, từng khoản). Một chặng vào tối đa một bảng kê. Không sửa, không xóa |
| `dieu_chinh_bk` | một điều chỉnh của một dòng | Số có dấu, khác 0, lý do bắt buộc. Chỉ thêm |
| `tien_ve` | một lần HTH trả | Gắn bảng kê của tháng. Không xóa; hủy bắt buộc lý do |

`loai_phi` có thêm cờ `chi_ho` (xí cont, cont mới, hạ sớm/KH). Lịch sử dùng chung `su_kien` với đợt 1, thêm các việc thu; Lịch sử của màn Người và xe không hiện việc thu.

Web tự tính, không có ô sửa tay: **công nợ cước** = tổng các bảng kê đã gửi + điều chỉnh − tiền về chưa hủy.

## Cách tính khi code (Claude, 18/11/2026)

Các điểm dưới đây theo bản bấm thử đã chốt. Chỗ bản bấm thử không nói, Claude chọn cách an toàn và ghi rõ là ĐỀ XUẤT; người dùng thấy khác thì đổi.

- **Thu tính ở màn Bảng kê, không điền lúc nhập chặng.** Khi chưa gửi, mọi số tính lại mỗi lần mở: đổi giá, sửa ghi chú, gắn tuyến thấy ngay. Bấm "Gửi bảng kê" thì web chép từng dòng; sau đó đổi giá hay sửa chặng không làm đổi bảng kê đã gửi. Máy gửi kèm số đòi, số chặng và dấu của các dòng đang thấy; khác hiện tại thì chặn, phải tải lại rồi gửi (thấy gì gửi nấy).
- **Chặng ghi muộn** vào tháng đã gửi tự sang bảng kê đang gom của tháng kế tiếp chưa gửi. Gửi bảng kê tháng này rồi mới ghi thêm chặng thì chặng sang tháng sau: thanh tháng hiện tháng đó, xem được, gửi được từ ngày 1 của tháng đó. ĐỀ XUẤT, theo câu cảnh báo "chặng chạy sau vào bảng kê tháng sau" của bản bấm thử.
- **Cước:** giá tay của chặng, nếu không thì giá tuyến ở ngày chặng. Tuyến của chặng là tuyến gắn tay; nếu không thì theo tên gốc; nếu không, chặng chuyển cảng hay trả rỗng nhận tuyến cùng loại khi chỉ có đúng một tuyến loại đó. Tuyến phải hợp loại chặng: chặng hàng, rút/thả mooc theo tuyến hàng; chặng chuyển cảng, trả rỗng theo tuyến cùng loại (ghi hàng, tỉnh trùng tên gốc của tuyến hàng cũng không nhận tuyến hàng). Gắn tuyến sai loại bị chặn; "Nhớ tên gốc" chỉ cho chặng hàng, rút/thả mooc. Rút/thả mooc lấy 70% giá tuyến hàng, làm tròn tới nghìn đồng (nửa nghìn làm tròn lên). Gõ giá tay bằng giá bảng thì coi như theo bảng.
- **Phát sinh và đóng ghép** đọc từ ghi chú của chặng. Mỗi khoản bắt đầu bằng "_" (đầu ghi chú hoặc sau khoảng trắng); chữ trước "_" đầu tiên là ghi chú thường (ghi chú chi phí của tài xế không lên bảng kê).
  - Số tiền ở cuối khoản: `125k`, `1tr5` (chữ số lẻ liền sau tr), `1,5tr` (phần lẻ 1–2 chữ số), `125.000`, `125000đ`; dấu câu hay ngoặc đóng sau số tiền bỏ qua. Không có số tiền thì khoản theo ngày lấy số ngày (mức + (ngày − 1) × mức thêm), khoản theo đơn vị lấy số giờ hoặc lần, khoản cố định lấy mức; khi đó tên không được có số nào khác. Đơn vị phải hợp cách tính: khoản theo ngày chỉ nhận số ngày, khoản theo giờ/lần không nhận số ngày.
  - Tên khoản là tên dài nhất của danh mục ở đầu khoản, phần còn lại là mô tả. Khoản đã ghi số tiền thì mô tả được có số lượng kèm đơn vị: ngày, đêm, giờ, lần, kho, km, cont (ví dụ "_ Đóng ghép 2 kho cách 70km 3100k"). Tên danh mục một chữ khớp sau khi bỏ dấu nhưng ghi khác dấu ("Cần cẩu" với "Cân") không nhận là khoản đó; gõ không dấu vẫn nhận.
  - Không đoán, gắn cờ và không tính: số âm, số ở cuối thiếu đơn vị tiền (`Kiểm hoá 125`), số tiền không ở cuối khoản, hai số tiền trong một khoản (quên dấu "_", kể cả cách nhau bằng dấu phẩy), số lạ khác trong khoản (`Xí cont 2 x 150k`, `Xí cont 2 cont`), số lẻ trước k hay tr (`1.250k`, `1.200tr`), số tiền dưới 10.000, số không đơn vị lớn hơn 10, đơn vị không hợp cách tính (`Neo 12 tiếng`), danh mục chưa có mức.
  - Tên không có trong danh mục mà có số tiền: vẫn tính, không coi là chi hộ, gắn cờ "khoản lạ". ĐỀ XUẤT.
  - Đo trên ghi chú file debit tháng 9–10: tháng 10 đọc ra đúng cột ĐÓNG GHÉP tới từng đồng và đúng cột PHÁT SINH ở mọi dòng trừ một dòng mà chính file ghi chú và ô lệch nhau; tháng 9 có một khoản thiếu chữ k bị gắn cờ thay vì đoán.
- **Ô ngày neo, giờ máy phát của phiếu chi mới:** ghi chú chưa có khoản Neo hay Nổ máy phát thì lấy số ở ô, tính theo danh mục; ghi chú có thì theo ghi chú, không cộng hai lần; danh mục chưa có mức thì gắn cờ. ĐỀ XUẤT, sau khi phiên phiếu chi báo nhân viên sẽ nhập số ngày, số giờ ở ô thay cho ghi chú.
- **Trước khi gửi** web liệt kê: chặng chưa có giá, giá tay khác bảng giá, khoản phát sinh chưa tính được, khoản lạ, và chặng cùng ngày, container, loại với một dòng đã gửi (chặng đã gửi bị xóa rồi nhập lại). Mỗi việc mở đúng bộ lọc. Chặng trùng chỉ báo, không tự bỏ.
- **Điều chỉnh** chỉ khi bảng kê đã gửi, chưa đối chiếu xong; tổng dòng sau điều chỉnh không được âm. Dòng đã gửi có chặng bị xóa hoặc bỏ ở sổ tài xế sau khi gửi thì gắn cờ "Chặng đã bỏ". Khung "Đối chiếu xong" nhắc dòng chưa có giá và dòng có chặng đã bỏ, vì sau bước này không điều chỉnh được nữa.
- **Tiền về** chỉ sau "Đối chiếu xong" (nút chính theo bước của bản bấm thử); ngày không sau hôm nay (giờ VN), không trước ngày gửi; trả thừa chặn.
- **File Excel** (nút tải ở đầu bảng kê, và tự tải khi bấm Gửi): 19 cột như file debit hiện nay, dòng "Kính gửi: HTH", số bảng kê và ngày gửi. GHI CHÚ chỉ có các khoản phát sinh đã đọc; điều chỉnh vào cột "+ - TIỀN", cột CHECK LÝ DO chỉ ghi lý do (không ghi người làm: file gửi công ty khác; Lịch sử trên web giữ ai, lúc nào). Tổng cộng lại phải bằng tổng máy chủ, lệch thì không xuất. Tháng chưa gửi là bản nháp.

## Người dùng và luồng (ĐỀ XUẤT trước bản bấm thử)

Bản bấm thử đã chốt thay vài điểm dưới đây (xem [quyết định](../docs/decisions/doi-xe-thu-01.md) và mục Cách tính khi code): thu tính ở màn Bảng kê chứ không điền lúc nhập chặng; trả thừa bị chặn.

Người thao tác: hai nhân viên đang nhập chi phí (đợt 1) và kế toán đang làm file công nợ cảng. Màn 1280×720, theo phong cách sổ khách.

**Bố cục theo tháng** (người dùng chọn ngày 18/11/2026, giữa hai phương án "theo tháng" và "sổ công nợ HTH"):

- Mỗi tháng một màn, chọn bằng hàng nút tháng; mỗi nút ghi trạng thái (đang gom, đang đối chiếu, chờ HTH trả, thu đủ).
- Trên cùng là ba số: Đòi HTH, HTH đã trả, Còn phải thu. Dòng dưới tách cước, đóng ghép, phát sinh, chi hộ, điều chỉnh.
- Nút chính đổi theo bước: Gửi bảng kê → Đối chiếu xong → Ghi tiền HTH trả.
- Bên dưới là bảng chặng giống file debit hiện nay.

Bản bấm thử (dữ liệu giả) nằm trên canvas thiết kế của dự án, trang "Đội xe: bảng kê HTH (đợt 2)", gồm 5 khung: tháng đã gửi, tháng đang gom, ghi điều chỉnh, ghi tiền về, bảng giá.

1. **Gợi ý thu khi nhập chặng:** lúc nhập chặng ở đợt 1, web điền sẵn cước theo bảng giá tuyến và các khoản phát sinh đọc được từ ghi chú. Người nhập sửa nếu khác. Chặng chưa có giá tuyến thì hiện cờ "chưa có giá".
2. **Ra bảng kê:** chọn công ty hàng và tháng. Web gom các chặng có thu, cho xem trước đúng mẫu file hiện nay, rồi xuất Excel.
3. **Đối chiếu:** công ty hàng góp ý từng dòng. Kế toán bấm nút ± ở cuối dòng đó; ô điều chỉnh mở ngay dưới dòng (bớt hay thêm, số tiền, lý do bắt buộc) và cho thấy Đòi HTH trước → sau. Xong thì bấm "Đối chiếu xong"; bảng kê chuyển sang "đã đối chiếu" và thôi nhận điều chỉnh (ĐỀ XUẤT, câu 13).
4. **Ghi tiền về:** chọn bảng kê tháng, nhập ngày và số tiền. Trả đủ thì bảng kê chuyển "đã thu đủ"; thiếu hoặc thừa thì hiện số chênh. Số còn nợ hiện ở đầu trang Đội xe.
5. **Xe thuê ngoài:** nếu cước của xe Trần Hùng đi qua mình (câu hỏi 2), thêm một bảng kê phải trả Trần Hùng, cùng mô hình nhưng chiều ngược lại.

**Bị chặn khi:** ngày tương lai (giờ VN); số tiền không phải số nguyên VND; sửa bảng kê đã đối chiếu mà không ghi điều chỉnh; tiền về lớn hơn số còn nợ mà không ghi rõ là trả trước.

## Hành vi và bất biến

- Tiền là số nguyên VND. Giá tính theo phần trăm (rút/thả mooc 70%) làm tròn tới nghìn đồng, nửa nghìn làm tròn lên (theo bản bấm thử đã chốt).
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
12. ĐÃ CHỐT 18/11/2026 (chốt mockup): chặng chưa có giá vẫn gửi được, ô cước để trống, chưa tính vào số đòi, có cảnh báo trước khi gửi.
13. ĐÃ CHỐT 18/11/2026 (chốt mockup): sau "Đối chiếu xong" thì thôi nhận điều chỉnh.

Theo bản bấm thử đã chốt, câu 5, 6 và 10 lấy cách làm mặc định: neo theo ngày, nổ máy phát theo đơn vị, đóng ghép nhập tay, làm tròn tới nghìn đồng. Danh sách chi hộ (câu 3) và cách tính nổ máy đang được hỏi lại ở phiên đợt 1; câu trả lời ở đó thay mặc định này.
