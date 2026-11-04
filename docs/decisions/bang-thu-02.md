# BANG-THU-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Bảng thu có **năm cách xem** dạng tab ngay trên bảng, cùng các phiếu của tháng đang chọn. Mỗi tab trả lời một câu hỏi:

1. **Theo ngày:** ngày nào thu bao nhiêu, ai trả.
2. **Theo khách:** cả tháng ai trả bao nhiêu.
3. **Theo mặt hàng:** mặt hàng nào thu được bao nhiêu, rồi tới từng khách.
4. **Theo tháng nợ:** tiền về tháng này trừ vào nợ tháng nào. Phiếu chia nhiều tháng tách đúng phần tiền từng tháng, phần vượt nợ nằm nhóm Ứng trước (cùng chữ với sổ khách).
5. **12 tháng:** tiền về từng tháng, bấm tháng để mở Theo ngày của tháng đó.

Có **bộ lọc mặt hàng** ở mọi tab trừ 12 tháng; phân nhóm mặt hàng giống bộ lọc của Tổng quan. Tab và bộ lọc nằm trên địa chỉ trang. Không làm view tự lưu kiểu Notion.

Trang đổi sang ngôn ngữ của Tổng quan bản ít chữ: đổi tháng ở thanh đầu, số lớn rút gọn và số đúng tới đồng ở chú thích, chip biểu tượng thay câu chữ, dải ngày, thẻ Hôm nay ở tháng đang chạy. Bảng vẫn ghi đồng đầy đủ để đối chiếu từng phiếu.

Không đổi cách tính tiền của [`BANG-THU-01`](bang-thu-01.md): tháng theo ngày tiền về, khoản không rõ ngày không cộng vào tổng tháng. Mọi cách gom đều giữ đẳng thức: tổng các nhóm bằng tổng tháng.

## Ngày / nguồn

4/11/2026, chat. Người dùng xem bản dựng lại trên Claude Design, hỏi "có làm nhiều view dc ko nhỉ, kiểu theo khách, theo gì gì đó, nhiều view giống notion". Claude dựng năm tab trên canvas, đề xuất để 12 tháng lại sau; người dùng chọn "Giữ đủ 5 view". Năm điểm trình bày (dải ngày, số rút gọn, bảng ghi đồng, đổi tháng ở thanh đầu và tab trên bảng, thanh "Phần trong tháng") người dùng xem trên canvas, không đổi; Claude chốt theo canvas theo [`CLAUDE-ALL-01`](claude-all-01.md). Bỏ view tự lưu, Theo hình thức, Theo người ghi, Lịch và Kanban là đề xuất của Claude ghi trên canvas.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Triển khai tự động khi merge qua `Deploy hao`, không có migration. Chỉ đổi cách trình bày; không đổi luật tiền, phân bổ, số nợ hay dữ liệu. Bước nghiệm thu cuối là người dùng tự đi hết các tab trên `hao`. Spec: [`v7-bang-thu`](../../specs/v7-bang-thu.md).
