# T1 — Hợp đồng nghiệp vụ cho charge chuyến đầu tiên

Ngày chốt: 15/10/2026. Người quyết định: người dùng/chủ nghiệp vụ. Nguồn: xác nhận của người dùng trong chat gốc, được giao ghi nhận ở T1.

- **Chính sách trong phạm vi dưới đây: ĐÃ CHỐT.**
- **Thiết kế triển khai: ĐỀ XUẤT, chưa được duyệt.**
- **Triển khai/kiểm chứng: CHƯA THỰC HIỆN.** Tài liệu này không hoàn tất M2 và không mở đường ghi tiền.

## Phạm vi

Một charge mới gồm một chuyến, một khách, một dòng tăng nợ và một kỳ nợ đang mở. Ngày xe nhập kho từ 14/10/2026 trở đi. Ngày xe nhập kho là ngày nghiệp vụ; `debt_period` là trường độc lập. Kỳ phải được xác nhận đang mở tại lúc xử lý.

Không gồm receipt/Q09, nhập muộn, chuyến ngày 13/10/2026, đảo, login thật, API ghi, migration, DB hoặc Google Sheet thật.

## Điều kiện hợp đồng

1. **Không cộng trùng opening.** Opening được chọn là replay ngày 13/10/2026 16:44. Phải đối chiếu chuyến bằng định danh nguồn ổn định với chính snapshot này và lưu tham chiếu chứng cứ cho kết luận chuyến chưa nằm trong opening. Ngày xe nhập kho từ 14/10 trở đi không tự chứng minh điều đó. Nếu không định danh/đối chiếu ổn định được, giữ `CHỜ KIỂM`, ngoài số dư. Container hoặc ngày đơn lẻ không là định danh đủ.
2. **Kỳ nợ độc lập với ngày nghiệp vụ.** UI sau này gợi ý tháng xe nhập kho. Maker phải xác nhận `debt_period` theo nguồn. Nếu chọn kỳ khác tháng được gợi ý, phải có lý do và chứng cứ; checker duyệt đúng revision. Gợi ý không tự quyết kỳ.
3. **Xác nhận giá theo chuyến.** Chủ nghiệp vụ (người dùng) xác nhận tổng và từng cấu phần giá của từng chuyến tại đúng revision. Các cấu phần phải đủ, khớp nguồn và khớp chính xác tổng. Xác nhận này riêng với checker approval; không thay thế hoặc ngầm tạo approval. Maker và checker phải là hai người khác nhau theo D01.
4. **Giữ ngoại lệ chờ kiểm.** Thiếu hoặc lệch cấu phần, tổng blank/0, thiếu định danh nguồn ổn định hoặc thiếu đối chiếu opening đều giữ `CHỜ KIỂM` và ngoài số dư. Không tự điền, làm tròn hay suy giá.
5. **Tiền chính xác.** Dùng VND nguyên; tổng phải khớp chính xác với cấu phần. Blank/NULL không phải 0.
6. **Revision và duyệt lại.** Sửa tiền/cấu phần, kỳ, ngày xe nhập kho, nguồn hoặc chứng cứ tạo revision mới. Chủ nghiệp vụ xác nhận giá lại tại revision mới; checker duyệt lại revision mới. Approval cũ không áp dụng cho nội dung đã đổi. Áp dụng Q02 cho mọi trường nghiệp vụ còn lại.
7. **Số dư.** Chờ kiểm, chờ xác nhận hoặc chờ duyệt không làm đổi số dư. T1 không xác nhận rằng đường posting đã triển khai hay được phép dùng.

## Ma trận ví dụ

| Trường hợp | Kết quả | Điều kiện/lý do |
|---|---|---|
| Chuyến nhập kho 14/10/2026; kỳ đang mở; nguồn có định danh ổn định; đối chiếu đúng opening 13/10 16:44 cho thấy chuyến chưa có; cấu phần đủ, khớp nguồn và tổng; chủ nghiệp vụ xác nhận giá tại revision; maker xác nhận kỳ; checker khác duyệt cùng revision | **Đủ điều kiện theo hợp đồng** | Vẫn không tự tạo posting hay số dư. |
| Ngày xe nhập kho 14/10/2026 trở đi nhưng không có đối chiếu với opening | **Chờ kiểm, ngoài số dư** | Ngày không chứng minh chuyến vắng mặt trong snapshot. |
| Không có định danh nguồn ổn định hoặc không thể đối chiếu riêng chuyến với opening | **Chờ kiểm, ngoài số dư** | Không xác định được chuyến chưa được tính trong opening. |
| Thiếu/lệch cấu phần, tổng blank/0, hoặc tổng không khớp cấu phần | **Chờ kiểm, ngoài số dư** | Giá chưa được xác nhận đầy đủ và chính xác. |
| Maker xác nhận kỳ khác tháng được UI gợi ý; nguồn và lý do/chứng cứ hỗ trợ; kỳ còn mở; checker khác duyệt cùng revision | **Đủ điều kiện theo hợp đồng** | Kỳ độc lập; lệch gợi ý có căn cứ và được checker duyệt. |
| Maker và checker là cùng một người | **Từ chối duyệt** | Vi phạm D01; cần checker khác. |
| Đổi tiền, kỳ, ngày, nguồn hoặc chứng cứ sau xác nhận/approval | **Từ chối dùng revision cũ; chờ revision mới** | Phải xác nhận giá và checker approval lại trên revision mới. |

## Còn mở trước triển khai

- Chưa chọn loại định danh nguồn cụ thể hoặc quy tắc đối chiếu kỹ thuật để chứng minh một chuyến vắng mặt trong opening.
- Chưa có danh mục cấu phần giá chuẩn theo từng loại chuyến; nguồn nghiệp vụ quyết định cấu phần cụ thể cho chuyến.
- Chưa duyệt cách lưu/xác thực xác nhận của chủ nghiệp vụ, bằng chứng đối chiếu opening, hay cách thể hiện các trạng thái trong app.
- Login thật, API ghi, migration và DB/Sheet thật vẫn ngoài T1; các gate P0 liên quan vẫn áp dụng.

## Cách kiểm và giới hạn

Review tài liệu theo từng điều kiện và ma trận trên; xác nhận mọi nhánh chờ kiểm ở ngoài số dư, đồng thời phân biệt xác nhận giá của chủ nghiệp vụ với checker approval. `git diff --check` kiểm khoảng trắng/diff. Không có thay đổi code/fixture nên T1 không có test runtime; tài liệu này chưa chứng minh app, DB hoặc nghiệp vụ live thực hiện đúng hợp đồng.
