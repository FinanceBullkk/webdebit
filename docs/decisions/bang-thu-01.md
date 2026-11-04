# BANG-THU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web có một **Bảng thu** gom phiếu thu của mọi sổ, chỉ để xem, không ghi.

1. **Bố cục:** danh sách theo ngày, mỗi dòng một phiếu, mới nhất trên cùng, mỗi ngày có tổng. Có nút đổi sang Theo khách. Bấm một dòng thì mở sổ khách đúng tháng.
2. **Tháng tính theo ngày tiền về**, không theo tháng ghi trên sổ. Khoản thu từ Sheet đọc ngày từ ô ngày của dòng. Dòng không đọc được ngày hoặc ngày vô lý nằm nhóm "Không rõ ngày" ở tháng của khối, không cộng vào tổng tháng, không đoán.
3. Từ tháng không còn khối Sheet (T11/2026 trở đi) tổng khớp Thu tháng của Tổng quan. Tháng có dòng Sheet thì khác "Đã thu" của sổ, có ghi chú giải thích. Tổng cả đời luôn bằng nhau.
4. **Hôm nay** và **tháng này** hiện đầu trang. Khi Sheet còn phiếu chưa ghi thì có một dòng cảnh báo dẫn sang Việc cần làm.

Không đổi [`DA-THU-01`](da-thu-01.md): "Đã thu" trong sổ vẫn như Sheet. Bảng thu trả lời câu hỏi khác: tiền về khi nào.

## Ngày / nguồn

4/11/2026, chat. Người dùng hỏi "chưa có 1 bảng thu tổng hợp nhỉ", chọn mục đích "Xem thu theo ngày" trong ba hướng (xem theo ngày, đối chiếu sao kê, nhập tại bảng). Sau khi Claude đo trên `hao` và báo Sheet ghi khoản thu ở khối tháng nợ, người dùng chọn "Danh sách theo ngày" và "Theo ngày tiền về". Quy tắc nhóm "Không rõ ngày" (ngày sau lúc nạp sổ, trước tháng của khối hơn 12 tháng, phiếu máy đặt cuối tháng) do Claude đề xuất trong [spec](../../specs/v7-bang-thu.md) theo [`CLAUDE-ALL-01`](claude-all-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đọc: migration thêm hai hàm đọc, không đổi luật tiền, phân bổ, số nợ hay dữ liệu. Có migration nên triển khai tay theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md). Bước nghiệm thu cuối là người dùng tự mở trang trên `hao`. CÒN MỞ: bổ sung ngày cho khoảng 510 dòng Sheet không rõ ngày; đối chiếu sao kê ngân hàng ([`CHUNG-TU-01`](chung-tu-01.md)).
