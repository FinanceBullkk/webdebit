# GHEP-KHONG-NGAY-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Hàng chờ giá Sheet ([spec](../../specs/v7-price-queue.md)) thôi hỏi một kiểu "khớp nhiều chuyến" mà thật ra không có gì để làm:

1. Dòng Sheet **không có ngày, đã có đơn giá**, mà web có **dòng không ngày cùng container tính đúng số đó** (cùng đơn giá và cùng tổng tính tiền) thì dòng web đó là bản sao của nó. Dòng Sheet chỉ ghép với (các) bản sao giống hệt; các dòng khác cùng container (container dùng lại ở chuyến khác) không còn là ứng viên của dòng Sheet này.
2. Luật chỉ chen vào **chỗ luật cũ đang hỏi**, tức container đó còn ít nhất một dòng web chưa có giá. Chỗ luật cũ không hỏi thì giữ nguyên, nên không câu hỏi nào mới hiện ra.
3. Kết quả luôn là không có gì để ghi: một bản sao thì dòng thành "giá đã giống"; nhiều bản sao giống hệt nhau thì thành "khớp nhiều dòng, đều đã có giá". Cả hai không hiện ở "Cần xem".
4. Vẫn hỏi người như cũ: không có dòng web không ngày nào giống hệt (khác đơn giá, khác tổng, chưa có giá), dòng Sheet trống giá hoặc thiếu TỔNG khi so với dòng sổ gốc, dòng Sheet có ngày, và **hai dòng Sheet cùng nhận một bản sao** (một dòng thừa trên Sheet hoặc một dòng web còn thiếu giá).

Không đổi: máy ghi giá (`MAY-GIA-01`), tổ hợp khớp tổng của máy đối soát ([`MAY-DOI-SOAT-01`](may-doi-soat-01.md)), phép tính web đi trước, lệnh ghi, DB, quyền, luật phân bổ. Dòng "khớp nhiều chuyến" trước giờ không nằm trong việc máy được ghi; dòng rời hàng chờ theo luật này trỏ vào một dòng web đã tính đúng số đó, nên không lệnh ghi nào được thêm hay bớt.

## Vì sao

Dòng không ngày trên web là dòng sổ gốc nạp từ chính các dòng không ngày của Sheet (chuyến web có container thì luôn có ngày). Chuyến có ngày cùng container thường có dòng Sheet có ngày của riêng nó. Luật cũ gom mọi dòng cùng container làm ứng viên, nên chỉ cần một chuyến chưa giá là dòng Sheet không ngày thành "khớp nhiều chuyến", dù bản sao của nó đã nằm trong sổ với đúng số tiền. Trả lời câu hỏi đó bằng cách ghi giá vào chuyến chưa giá thì web tính trùng.

## Ngày / nguồn

13/11/2026, chat. Người dùng nói backend "chưa đạt mức thông minh và tự động vì người dùng còn phải xử lý tay nhiều". Claude đo chỉ đọc hộp Việc cần làm trên `hao` (GET API, 242 sổ): 41 dòng giá cần xem ở 8 sổ, 40 là "khớp nhiều chuyến", không dòng nào trả lời được bằng nút. Ước lượng từ dữ liệu API: 32/40 dòng có bản sao không ngày giống hệt (25 dòng một bản sao, 7 dòng ở nhóm 2–3 dòng Sheet ứng 2–3 bản sao cùng bộ số); 8 dòng còn lại không thuộc luật này (5 dòng có ngày, 2 dòng cùng nhận một bản sao, 1 dòng không có bản sao). Lần đo 27/10/2026 ghi trong spec hàng chờ cũng ra 40 dòng "khớp nhiều chuyến có chuyến chưa giá"; chưa đối chiếu được đó có phải cùng các dòng.

Luật do Claude chọn theo mục tiêu người dùng nêu; người dùng không chốt riêng từng vế. Chọn bản hẹp (chỉ chỗ luật cũ đang hỏi, chỉ bản sao giống hệt) để không đổi việc máy được ghi và không làm hiện câu hỏi mới. Bản đầu rộng hơn (ghép với mọi dòng web không ngày của container) bị lượt review độc lập cùng ngày chỉ ra hai ca: làm hiện câu hỏi ở chỗ luật cũ không hỏi, và giấu ca hai dòng Sheet cùng ứng một dòng web; bản này sửa cả hai.

## Hiệu lực và giới hạn

ĐÃ CHỐT trong phạm vi trên. Luật ghép nằm ở một chỗ, `web/v7_price_queue.py` (`candidates`), dùng chung cho hàng chờ, máy đối soát, gợi ý lệch và công cụ audit chuyển hẳn. Kiểm bằng dữ liệu giả: `tests/test_v7_price_match.py`, `test_v7_price_queue.py`, `test_v7_sheet_fix.py` (nhóm việc và tiền web đi trước của máy không đổi).

Giới hạn:

- Con số 32/40 là ước lượng từ dòng "Cần xem" mà API trả, lấy đơn giá + phụ phí làm tổng; số thật đo lại trên `hao` sau khi lên.
- Dòng Sheet không ngày mà dòng web không ngày của nó **chưa có giá** vẫn là "khớp nhiều chuyến" khi container có chuyến khác. Cho máy ghi ca đó là đổi việc máy được ghi, CÒN MỞ.
- Nhiều bản sao giống hệt nhau thì máy không đếm số dòng Sheet ứng với chúng: ba dòng Sheet cùng số mà web chỉ có hai bản sao cùng số thì không câu hỏi nào hiện. Tổng khách vẫn do đối soát mỗi giờ canh.
- Nếu ô ngày của một dòng Sheet bị xóa sau khi nạp và dòng đó trùng đúng số với một dòng không ngày của cùng container, câu hỏi không hiện (khi dòng không ngày kia vẫn còn trên Sheet thì hai dòng cùng nhận một bản sao và vẫn hỏi).
- Chuyến chưa giá không có dòng Sheet riêng thì không còn dòng Sheet nào nhắc tới nó ở "Cần xem"; nó vẫn nằm ở nhóm "Chưa giá" của Việc cần làm.
- Hàng chờ phụ phí PS có luật ghép riêng (`v7_ps_queue.match`), không đổi.
