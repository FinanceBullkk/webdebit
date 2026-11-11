# KIEM-TONG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Máy đối soát mỗi giờ ([`MAY-DOI-SOAT-01`](may-doi-soat-01.md)) **kiểm thêm tab TONG** của Sheet sổ nợ: khối tháng mới nhất (ngoài cùng bên phải) có cộng đủ các tab khách không. **Chỉ báo**: không ghi tiền, không sửa Sheet, không đổi điều kiện máy ghi hay cách máy nhận tab mới ([`MAY-TAO-SO-01`](may-tao-so-01.md)).

1. Mỗi lượt nêu tháng của khối TONG mới nhất, số dòng TONG khớp sổ, các sổ còn số dư mà TONG để trống, các dòng TONG lệch sổ và các tên trên TONG không ứng với sổ nào.
2. Phép so là phép so của lệnh audit chuyển hẳn ([spec](../../specs/v7-cutover-audit.md)): số cuối tháng trên TONG phải bằng tổng nợ web, trừ phần web đi trước, trừ phát sinh các tháng sau trên tab, cộng thu ghi ở khối các tháng sau. Máy và lệnh audit dùng chung một đoạn mã.
3. Kết quả hiện ở **đầu tab Việc cần làm**. Phần màn hình làm thành PR riêng, sau PR máy.

## Ngày / nguồn

11/11/2026, chat. Lượt audit chỉ đọc cùng ngày ([checklist chuyển hẳn](../chuyen-han-checklist.md), mục A2) thấy TONG để trống 14 khách còn số dư, mà chưa lượt đối soát nào báo. Claude hỏi hai câu, người dùng chọn đúng phương án đề xuất:

- "Có, kiểm mỗi giờ", không chọn "Không, chỉ kiểm cuối tháng";
- "Đầu tab Việc cần làm", không chọn "Chỉ trong reconcile.json".

Khi hỏi, Claude đã nói trước rằng lúc khối tháng mới của TONG còn đang gõ dở, dòng này sẽ báo nhiều sổ để trống.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chi tiết ở [spec máy đối soát](../../specs/v7-may-doi-soat.md#kiểm-tab-tong-kiem-tong-01). Không đổi DB, quyền, luật tiền hay điều kiện ghi. Các giới hạn dưới đây do Claude ghi khi làm, không phải lựa chọn của người dùng:

- Tên trên TONG ghép với tên sổ bằng chữ và số đã bỏ dấu, không dùng bảng tên khác hay `--tong-alias` của audit. Tên trên TONG khác hẳn tên sổ thì hiện thành một tên không ứng với sổ nào, và sổ đó nằm ở danh sách để trống.
- Sổ đang lệch Sheet thì số kỳ vọng vẫn tính theo web, như audit. Dòng TONG "lệch" của sổ đó có thể do sổ web chứ không do TONG: xem dòng đối soát của khách đó trước.
- Lượt có hơn 40 khách lệch thì không kiểm TONG, vì phần web đi trước chưa được tính.
- Lượt mà mọi khách đều khớp phải dựng thêm bản chụp giá và phiếu (đo trên `hao` 11/11/2026: lượt có bước này 449 giây, lượt không có 288 giây). Ở 46/48 lượt gần nhất bản chụp đã được dựng sẵn cho việc tìm cách sửa, nên phép kiểm dùng lại, không tốn thêm.
