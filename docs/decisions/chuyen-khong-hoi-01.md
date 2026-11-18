# CHUYEN-KHONG-HOI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: máy thôi hỏi hai loại "chuyến cần kiểm" mà người không trả lời khác đi được.

1. **Dòng sổ gốc lệch ngày không quá 3 ngày với nguồn booking: giữ ngày sổ gốc, không hỏi.** Luật ghép vốn coi lệch 3 ngày là cùng một chuyến, và ngày sổ gốc là ngày của Sheet sổ nợ, đang là sổ chính thức ([`SONG-SONG-01`](song-song-01.md)). Không ghi gì khi chỉ lệch ngày. Lệch 3 ngày qua ranh tháng (sổ gốc 31/3, nguồn 2/4) cũng vậy: tháng nợ của dòng sổ gốc không đổi.
   - **Hệ quả với ô chữ:** dòng lệch ngày kèm lệch nơi đi, nơi đến hoặc shipper trước đây nằm chờ người, máy không đụng. Nay ô ngày không còn là câu hỏi nên phần chữ thành "lệch chữ" và **máy lấy chữ theo Sheet** như [`HANG-CHO-01`](hang-cho-01.md) Q1, kể cả ở tháng đã khóa (sửa chữ không cần mở tháng), khi `WEBDEBIT_AUTO_SHEET` có `text`. Tức tập dòng máy ghi chữ rộng ra; tiền, ngày, tháng nợ của dòng không đổi.
   - **Ngoại lệ:** một dòng sổ gốc bị **hai dòng nguồn cùng nhận** (nguồn có hai chuyến cách nhau trong 3 ngày, sổ có một dòng) thì giữ luật cũ, vẫn hỏi ngày và máy không lấy chữ. Bỏ ô ngày ở ca này sẽ làm máy lấy chữ theo dòng này rồi dòng kia.
2. **Container đã có trong sổ mà tab khách chưa có dòng riêng: không còn là việc, chỉ là dòng "chờ tab Sheet".** Dòng không tính vào số việc, không hiện ở Việc cần làm, không có chấm trên chip tháng. Ở Sổ khách nó hiện xám tại tháng của ngày chuyến, nhãn "CHỜ TAB SHEET · Không cần làm gì". Khi tab có dòng riêng thì thành chuyến mới và đi tiếp như [`CONTAINER-DUNG-LAI-01`](container-dung-lai-01.md).

Không đổi: luật ghép (±3 ngày, trùng booking, dòng không ngày cùng tháng), điều kiện máy đưa chuyến vào sổ, máy điền ngày cho dòng sổ gốc **chưa có ngày** ([`MAY-KHOA-01`](may-khoa-01.md) việc A), lệch ngày của **chuyến web**, lệch booking, khớp nhiều chuyến, container ở khách khác. Không đổi tiền, DB, quyền, loại lệnh ghi.

## Thay thế

- Vế "vẫn để người quyết: lệch ngày khi dòng cũ đã có ngày" của [`MAY-KHOA-01`](may-khoa-01.md), **chỉ cho dòng sổ gốc**. Chuyến web giữ nguyên.
- Vế "không đủ thì dòng vẫn chờ người xem" của [`CONTAINER-DUNG-LAI-01`](container-dung-lai-01.md): dòng vẫn bị giữ ngoài sổ y như cũ, nhưng không còn là việc của người.

## Vì sao

Đo chỉ đọc trên `hao` 13/11/2026 (27 chuyến cần kiểm ở 20 sổ):

| Loại | Số dòng | Người làm được gì trước quyết định này |
| --- | --- | --- |
| Lệch ngày 1–3 ngày với dòng sổ gốc, đều ở tháng 1–8/2026 đã khóa | 9 | Chỉ bấm được "Giữ web"; tháng khóa không lấy được ngày Sheet |
| Container đã có trong sổ, tab chưa có dòng riêng | 16 | Chỉ có "Mở trong sổ", không nút nào đóng được |
| Khớp hai dòng sổ gốc; container ở khách khác | 2 | Cần người xem thật, giữ nguyên |

Trong 16 dòng nhóm hai: 7 dòng lệch 4–20 ngày với đúng một dòng cùng tháng, 6 dòng sổ gốc không ngày khác tháng, 1 dòng sai năm, 1 dòng ngày lạ, 1 container dùng lại thật đang chờ tab có dòng. Lượt đo 4/11/2026 của `CONTAINER-DUNG-LAI-01` có 17 dòng cùng kiểu. Cả 9 dòng nhóm một đều kèm lệch chữ (nơi đi, nơi đến hoặc shipper). Cả hai trường hợp (cùng một chuyến ghi khác ngày, hoặc chuyến mới chưa lên tab) đều không có gì để làm trên web trong lúc web chạy theo Sheet ([`MAY-DOI-SOAT-01`](may-doi-soat-01.md)).

## Ngày / nguồn

13/11/2026, chat. Người dùng nói backend "chưa đạt mức thông minh và tự động vì người dùng còn phải xử lý tay nhiều". Claude rà 27 chuyến cần kiểm, đưa hai thay đổi kèm số đo và nêu rõ vế nào của hai quyết định cũ bị đổi; người dùng chọn "Làm cả hai". Lúc đề xuất Claude viết "chữ vẫn tự lấy theo Sheet như hiện nay"; lượt review độc lập chỉ ra câu đó sai với nhóm dòng lệch ngày kèm lệch chữ (trước đây máy không đụng). Claude báo lại điểm này cùng bốn điểm khác; người dùng chọn "Sửa rồi merge".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi code app: `web/v7_sheet_queue.py` (`project_customer`), `web/v7_api_sheet.py`, bảng chuyến của Sổ khách; `tools/v7_cutover_audit.py` đếm thêm `sheet_sync.waiting_count`. Kiểm bằng dữ liệu giả: `tests/test_sheet_queue.py`, `preview/test-so-khach-v7-sheet-browser.js`.

Giới hạn:

- Người nhập không còn bị nhắc khi nguồn booking có chuyến mà Sheet sổ nợ chưa ghi. Dòng đó chỉ thấy khi mở sổ đúng tháng, hoặc qua số đếm của audit chuyển hẳn. Việc so Sheet sổ nợ với booking vẫn là mục A6 của [checklist chuyển hẳn](../chuyen-han-checklist.md), chưa có màn riêng.
- Dòng chờ tab Sheet ở tháng chưa có bảng tháng nào trong sổ thì không hiện (nó không tạo bảng tháng). Trên điện thoại không hiện.
- Ngày sổ gốc sai mà chỉ lệch 1–3 ngày thì web không hỏi nữa; muốn sửa thì sửa tay tại ô ngày.
- Dòng lệch 1–3 ngày mà nguồn trống shipper thì còn lại là "thiếu shipper Sheet": máy không lấy được, người cũng không có nút; nó chuyển từ "cần kiểm" sang "lệch chữ" chứ không biến mất. Lượt đo 13/11/2026 không có dòng nào như vậy trong 9 dòng.
- Phép đếm "tab có nhiều dòng hơn sổ" của `CONTAINER-DUNG-LAI-01` tính cả chuyến web đã bấm "Trùng, bỏ" (lỗi có từ trước). Sổ có chuyến đã loại cùng container thì chuyến dùng lại thật bị giữ; trước đây nó hiện đỏ, nay hiện xám "Không cần làm gì". CÒN MỞ: sửa phép đếm.
- Sổ đang xem bảng chi tiết (`SO-CHI-TIET-01`) không vẽ dòng chờ tab Sheet.
- Tab có dòng riêng thì dòng thành chuyến mới; máy chỉ tự đưa vào sổ khi đủ điều kiện cũ (đúng mặt hàng, ngày không sau hôm nay, tháng mở hoặc từ 10/2026). Tháng cũ hơn thì nó thành "chờ duyệt", người vẫn bấm.
- Hết hiệu lực vế 1 khi chuyển hẳn khỏi Sheet, cùng lý do với `HANG-CHO-01` Q1: lúc đó Sheet sổ nợ không còn là sổ chính thức.
- CÒN MỞ: người dùng tự xem dòng "CHỜ TAB SHEET" trên `hao`.
