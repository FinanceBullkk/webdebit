# VIEC-DOI-CHIEU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Tab **Việc cần làm** trả lời trước một câu: **số nợ hôm nay có đúng với Sheet không?** Đơn vị của trang đổi từ "một việc" sang "một khách lệch".

1. **Dòng đầu trang** nói khớp mấy khách, bao nhiêu phần trăm số nợ, lần đối soát này và lần tới. Thay hai dải "Đối soát" và "N sổ còn việc".
2. **Ba tab:**
   - **Số nợ lệch** (mở mặc định): bảng khách chưa khớp, mở một khách ra là **bảng đối chiếu**: số nợ web ± từng khoản = số nợ Sheet, phần chưa giải thích hiện riêng. Nhiều khách thì mở ngay dưới dòng.
   - **Dọn chi tiết**: bảng sổ × loại việc như cũ, xử lý tại dòng như cũ. Hiện cả sổ đã khớp, nên thay vế "mặc định ẩn" của [`MAY-DOI-SOAT-01`](may-doi-soat-01.md) mục 5. Khoản đã nằm trong bảng đối chiếu không hiện lại ở đây.
   - **Máy đã làm**: nhật ký hôm nay theo giờ, kèm người đã ghi.
3. **Ghi từ bảng đối chiếu:** chọn khoản, thấy số còn lệch đổi ngay, bấm Ghi, xem nợ trước → sau, xác nhận một lần. Dùng đúng đường ghi của máy (`plan`, `apply_fix`), nên số tiền đúng như máy tính, người làm là người bấm.
4. **Tháng khóa (thay một phần [`MAY-KHOA-01`](may-khoa-01.md) và [`V7-SO`](v7-so.md) cho riêng lần xác nhận này):** người chọn khoản thuộc tháng khóa rồi xác nhận thì web **mở tháng, ghi, khóa lại**. Khung xác nhận nói rõ trước khi ghi. Không dùng dòng điều chỉnh vì phụ phí trên dòng vẫn khác Sheet nên việc còn treo. Các chỗ khác người vẫn bị chặn như cũ.
5. **Giữ số web** ([`VCL-GIU-01`](vcl-giu-01.md)) làm được cho cả nhóm hoặc từng chuyến; nợ không đổi và khung xác nhận nói rõ vẫn còn lệch.
6. **Hoàn tác** cho lần vừa ghi khi mọi khoản là giá hoặc phiếu; khoản khác (thay khoản thu cũ, dòng điều chỉnh) thì mở sổ để sửa.

Dòng giá chỉ khác phụ phí phải ghi đúng là phụ phí: không còn "Trên web 85 · trên Sheet 85".

Không đổi: luật tiền, phân bổ, máy đối soát, DB, số đếm trên menu.

## Ngày / nguồn

6/11/2026, chat. Người dùng chê tab; Claude đưa hai phương án, người dùng nói "tất cả phương án bạn đề xuất đều chưa tốt, có phương án B là tạm nhất. Cần architect và thiết kế lại". Claude đo trên `hao` (chỉ đọc): một khách lệch giữ 12% số nợ; 36 sổ đã khớp còn 155 việc nhỏ; từ 1/11 người chưa lần nào giải quyết lệch hay kiểm chuyến. Claude dựng kiến trúc này trên canvas, người dùng trả lời "Đúng hướng"; Claude hỏi cách ghi tháng khóa, người dùng chọn "Mở, ghi, khóa lại".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Spec: [`specs/v7-viec-can-lam-doi-chieu.md`](../../specs/v7-viec-can-lam-doi-chieu.md). Triển khai tự động khi merge qua `Deploy hao`.

- Lịch sử: lệnh ghi mang tên người bấm; hai lệnh mở và khóa tháng ghi là "Máy (theo Sheet)", vì lượt nền chỉ khóa lại tháng máy đã mở nên nơi gọi chết giữa chừng thì tháng không nằm mở (cách của `apply_fix`).
- Phiếu không ngày lấy ngày cuối tháng của khối Sheet như máy, không nhập ngày trong bảng đối chiếu. Muốn ngày khác thì ghi từ sổ.
- Số Sheet lấy từ lượt đối soát gần nhất; khoản lấy từ bản chụp mới nhất, nên có thể lệch nhau trong vài chục phút khi Sheet đang được sửa. Máy đối chiếu lại ở lượt sau.
- CÒN MỞ: người dùng tự đi hết luồng trên `hao`.
