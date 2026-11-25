# WEB-CHINH-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt (25/11/2026): **web là sổ chính thức, nguồn sự thật duy nhất của công nợ.** Phát triển từ nay theo hướng này, không chạy theo Sheet sổ nợ nữa. Quyết định thay vế (1) của [`SONG-SONG-01`](song-song-01.md) ("Sheet vẫn là sổ chính thức… lệch thì tra lỗi phía web") và vế "chưa chuyển hẳn" của [`CHUYEN-HAN-01`](chuyen-han-01.md).

Phạm vi là Sheet sổ nợ "2026 debit" (tab TONG và các tab khách), như `CHUYEN-HAN-01` đã khoanh ngày 11/11/2026. File nguồn chuyến CHAU_HAO (`CONT_NGUON`, `CONT_BO`, `WEB_GHEP_KHACH`) vẫn là đầu vào chuyến ([`NGUON-CHUYEN-01`](nguon-chuyen-01.md), [`DU-CHUYEN-01`](du-chuyen-01.md)): đó là nguồn nghiệp vụ, không phải sổ nợ.

Claude đặt các nguyên tắc dưới đây để áp quyết định vào việc phát triển (ĐỀ XUẤT, áp dụng ngay cho việc mới; đổi hành vi máy đang chạy thì làm theo từng PR riêng):

1. **Web lệch Sheet thì web là chuẩn.** Chỉ sửa web khi có bằng chứng từ nguồn gốc: booking, sao kê, chứng từ, người nhập hay chủ sổ xác nhận. "Khác Sheet" một mình không phải lỗi của web. Không báo, không đề xuất sửa Sheet; ngoại lệ là lỗi Sheet đã chảy vào web, hoặc Sheet là chỗ duy nhất cho biết web đúng hay sai.
2. **Không thêm phụ thuộc mới vào Sheet sổ nợ.** Việc mới không thêm máy chép từ Sheet, phép so mới với Sheet, điều kiện "chờ tab Sheet" hay chỉ số "khớp Sheet". Mọi thứ người dùng làm được phải làm được trên web.
3. **Máy theo Sheet chỉ còn là đường chuyển tiếp, và không được đè web.** Trong lúc người nhập còn gõ Sheet, máy chỉ được *thêm* cái web chưa có (giá cho chuyến chưa giá, phiếu thu chưa có trên web, chuyến mới). Máy không được sửa đè hay hủy cái web đã có theo Sheet: giá web khác giá Sheet, Sheet sửa hoặc xóa phiếu đã ghi, dòng điều chỉnh để kéo tổng về bằng Sheet. Các ca đó thành việc ở Việc cần làm cho người quyết, web giữ nguyên tới khi người bấm.
4. **Tắt từng đường chép khi web có đường nhập thay và người nhập đã thôi gõ đầu vào đó trên Sheet**, theo thứ tự đề xuất ở bảng dưới. Tắt bằng cờ, có nhật ký trong `docs/deploys/`.
5. **Lưới an toàn sau khi bỏ Sheet:** sổ web so với booking mỗi giờ ([`DU-CHUYEN-01`](du-chuyen-01.md)), lưới an toàn trên chính sổ web ([`LUOI-AN-TOAN-01`](luoi-an-toan-01.md)), xuất cả sổ làm đường lui ([`XUAT-SO-01`](xuat-so-01.md)). Đối soát "khớp Sheet" và [`KIEM-TONG-01`](kiem-tong-01.md) tắt cùng lúc khóa Sheet.

### Các đường chép và đường thay

| Đầu vào | Hôm nay (theo Sheet sổ nợ) | Đường thay trên web | Bước |
| --- | --- | --- | --- |
| Khách mới | Máy tạo sổ khi tab có trên TONG ([`MAY-TAO-SO-01`](may-tao-so-01.md)) | Thẻ Khách trong Quản trị ([`KHACH-WEB-01`](khach-web-01.md)), đã chạy trên `hao` | Tắt sớm nhất |
| Chuyến bộ vào sổ nào | Theo tab khách ([`NGUON-CHUYEN-01`](nguon-chuyen-01.md)) | Tên chủ hàng gán trên web (`KHACH-WEB-01`); chuyến còn lại chọn sổ ngay trên web | Sau khách mới |
| Giá, phụ phí | Máy chép ([`MAY-GIA-01`](may-gia-01.md), [`MAY-PS-01`](may-ps-01.md), [`MAY-DOI-SOAT-01`](may-doi-soat-01.md)) | Bảng giá web ([`BANG-GIA-02`](bang-gia-02.md)), giá booking gợi ý ([`GIA-BOOKING-01`](gia-booking-01.md)), gõ tại ô | Sau khi đo được tỷ lệ chuyến có giá trên web không cần Sheet |
| Phiếu thu | Máy chép ([`THU-SHEET-01`](thu-sheet-01.md), [`THAY-PHIEU-SHEET-01`](thay-phieu-sheet-01.md)) | Khung Ghi phiếu thu ở Sổ khách; sau này tiền về từ sổ tiền ([`SO-TIEN-01`](so-tien-01.md)) | Khi người nhập ghi phiếu trên web |
| Lưới an toàn | Đối soát khớp Sheet mỗi giờ, `KIEM-TONG-01` | Mục 5 ở trên | Cuối cùng, cùng lúc khóa Sheet |

Việc khác phải làm trước khi khóa Sheet (phiên kiểm toàn bộ website nêu 25/11/2026 từ audit 23/11, chưa đo lại sau các PR 23–24/11): [`KIEM-BOOKING-01`](kiem-booking-01.md) còn lấy workbook Sheet làm đầu vào, phải đổi sang so booking với sổ web; bot Zalo gắn chân "khớp Sheet" vào câu trả lời, phải đổi tiêu chí; các nút và tab đặt Sheet làm chuẩn ("Lấy Sheet / Giữ web", "Sheet cần sửa") đổi chữ theo nguyên tắc 3; khi web là sổ duy nhất, mất máy `hao` là mất tới bản backup gần nhất, nên diễn tập dựng lại trên máy khác (mục E1 của checklist) thành việc bắt buộc.

## Ngày / nguồn

25/11/2026, chat. Người dùng: "giờ web chúng ta tiến đến giai đoạn: web là single source of truth, giao tiếp với các session liên quan để phát triển theo hướng này thay vì phải chạy theo sheet debit". Cùng ngày người dùng đã nói chỉ cần web đúng, Sheet sai thì không báo. Số đo gần nhất trước quyết định (lượt đo lại audit chuyển hẳn sáng 25/11/2026, chỉ đọc): 240/250 sổ khớp Sheet, 3 sổ web đi trước, 2 sổ lệch chưa giải thích; số đo ở [checklist chuyển hẳn](../chuyen-han-checklist.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng (web là sổ chính thức). Nguyên tắc 1–5 và bảng là ĐỀ XUẤT của Claude. Quyết định này không đổi DB, quyền, luật tiền (FIFO, khóa tháng, NULL không phải 0) hay hành vi máy đang chạy; mỗi thay đổi máy là một PR riêng có test và nhật ký.

**Ngày thôi gõ Sheet (người dùng chốt 25/11/2026, chat, chọn "Từ 1/12/2026" thay vì chuyển từng đầu vào):** từ **1/12/2026** người nhập thôi gõ Sheet sổ nợ; mọi đầu vào (khách mới, chuyến bộ chọn sổ, giá, phụ phí, phiếu thu) nhập trên web, kể cả giá hay phiếu của tháng 11 nhập trễ. Cách làm (ĐỀ XUẤT của Claude): cho tới hết 30/11 máy chép vẫn chạy theo nguyên tắc 3; lượt đối soát cuối tháng 11 là lượt so Sheet cuối cùng có giá trị; sau lượt đó tắt các đường chép từ Sheet sổ nợ theo mục "Tắt máy ngày 1/12" dưới đây, có nhật ký trong `docs/deploys/`. Lệnh audit chuyển hẳn (`v7_cutover_audit.py`) đo theo kiểu "khớp Sheet": chạy lần cuối cho đối soát cuối tháng 11, sau đó thôi dùng; từ 1/12 web được kiểm theo booking, chứng từ và lưới an toàn (nguyên tắc 5), không theo [checklist chuyển hẳn](../chuyen-han-checklist.md) phần A1–A3. Trước 1/12 phải xong: đường nhập trên web cho từng đầu vào ở bảng trên dùng được, và người nhập đã đi thử từng đường trên `hao`.

### Tắt máy ngày 1/12 (ĐỀ XUẤT)

Sửa 25/11/2026 theo phiên kiểm toàn bộ website, Claude đã đối chiếu mã trên `main`. Câu cũ "tắt `WEBDEBIT_AUTO_SHEET`" là sai. Cờ đó điều khiển cả việc tự dán chuyến từ booking, mà booking vẫn là nguồn chuyến. Vì vậy chỉ tắt phần lấy từ Sheet sổ nợ:

1. **Cờ `WEBDEBIT_AUTO_SHEET`:**
   - bỏ `prices`, `ps`, `headers`;
   - **giữ `trips`, `road`**: chuyến biển `CONT_NGUON` và chuyến bộ `CONT_BO` tự vào sổ;
   - `text` (chữ nơi đi, nơi đến…) xét theo nguồn: nếu chép từ tab Sheet sổ nợ thì bỏ.
2. **Lượt đối soát mỗi giờ:**
   - thôi ghi theo Sheet và thôi so Sheet, kéo theo `KIEM-TONG-01` và `MAY-TAO-SO-01`;
   - phép so sổ web với booking ([`DU-CHUYEN-01`](du-chuyen-01.md)) đang chạy trong lượt này, sau bước tải bản xlsx Sheet. Phải tách ra chạy riêng từ bản chụp booking và DB **trước** khi tắt lượt, không thì mất lưới booking.
3. **Bản chụp:**
   - runner bản chụp vẫn đọc CHAU_HAO;
   - bản chụp giá của Sheet sổ nợ đang là lịch sử tab để xếp chuyến bộ vào sổ. Thiếu file thì mọi chuyến bộ thành `NO_TAB`. Phải đóng băng file đó, hoặc thêm dự phòng như đường của thẻ Khách, trước khi thôi đọc tab.
4. **Máy canh ([`CANH-BAO-01`](canh-bao-01.md)):** sửa cùng lúc danh sách timer tiền, danh sách bản chụp và cờ phải có, không thì báo động giả.
5. **Trước 1/12:**
   - ghi các cặp chủ hàng → sổ mà máy đã học từ tab thành tên booking trên web ([`KHACH-WEB-01`](khach-web-01.md));
   - chuyến bộ `AMBIGUOUS_TAB` / `TAB_FAR` cần nút chọn sổ như chuyến biển;
   - **tháng 11 tự khóa ngày 1/12** (mặc định chỉ tháng hiện tại mở). Đo 25/11: còn nhiều chuyến tháng 11 chưa giá ở hơn 20 sổ. Mấy tuần gần đây, gần như mọi lần mở–ghi–khóa là máy làm; sau 1/12, người nhập phải tự mở khóa từng sổ mới gõ được giá hay phụ phí. Cách xử lý CÒN MỞ, chờ người dùng chọn;
   - gợi ý giá booking ([`GIA-BOOKING-01`](gia-booking-01.md)) và danh sách "Chưa giá" mọi sổ hiện chỉ có ở trang Việc cần làm, mà login người dùng ([`QUYEN-01`](quyen-01.md)) không vào được trang này. Phải đưa gợi ý vào ô giá của Sổ khách, hoặc mở trang cho người dùng;
   - chữ còn coi Sheet là nơi ghi giá ("chờ Sheet ghi giá", "Lấy giá Sheet", "Máy tự tách ở lượt chạy sau") phải đổi; ô giá trống nên ghi rõ là chưa có giá.
6. **Phiếu chỉ ghi trên web:** máy đối soát coi đó là sổ lệch, quá ngưỡng thì dừng ghi cả lượt và gửi email. Từ nay tới 30/11, phiếu người nhập thử trên web làm lệch là đúng dự kiến, không phải lỗi.

CÒN MỞ:

- Ngày khóa Sheet chỉ xem (đề xuất: cùng 1/12/2026, để không ai lỡ tay gõ vào đó).
- Các mục chưa đạt của [checklist chuyển hẳn](../chuyen-han-checklist.md) (người nhập làm trọn một ngày trên web, hai người cùng sửa, diễn tập phục hồi) không còn là điều kiện để coi web là chuẩn, nhưng vẫn là việc phải làm trước khi khóa Sheet.
- Hai sổ lệch chưa giải thích lúc chốt: theo nguyên tắc 1, chỉ tra khi nghi web sai.
