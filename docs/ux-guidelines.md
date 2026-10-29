# Hướng dẫn UX/UI

Áp dụng cho code frontend và bản xem (nếu có) của app công nợ. Bổ sung cho [quy trình frontend](development.md#quy-trình-frontend), không thay quy tắc nghiệp vụ ở [business-rules](business-rules.md).

## Người dùng

ĐÃ CHỐT bởi người dùng ngày 16/10/2026 trong chat:

- Người dùng chính trên 40 tuổi.
- Ưu tiên đúng luồng nghiệp vụ và luồng sử dụng thực tế hơn hình thức.
- Giao diện không được có thông tin thừa.

- **Màn hình: 1280×720 ở mức logic** (1920×1080 vật lý, Windows để tỉ lệ 150%); Chrome toàn màn hình còn khoảng 1280×560 nhìn thấy. Đo ngày 18/10/2026 trên máy người dùng. Mọi mockup và khung chụp lấy 1280×720.

CÒN MỞ (hỏi người dùng khi làm spec màn hình, không tự giả định):

- Vai trò cụ thể của người dùng từng màn hình (người nhập chuyến, người thu tiền, người duyệt, chủ xem báo cáo).
- Khối lượng thường gặp: số chuyến mỗi lô, số khách, số kỳ đang mở.
- Thói quen hiện tại: đang làm việc này trên Google Sheet như thế nào, gọi các cột/khái niệm bằng tên gì.

## Nguyên tắc

ĐỀ XUẤT ngày 16/10/2026, dùng cho đến khi người dùng chỉnh:

1. **Một màn hình, một việc.** Mỗi bước có một nút chính rõ ràng; thao tác phụ để nhẹ hơn hoặc trong "Chi tiết".
2. **Chỉ hiện thông tin cần để quyết định ở bước đó.** Không đưa lên giao diện người dùng: mã quyết định (D01, Q02…), từ kỹ thuật (fixture, revision, RAM, API, guardrail), giải thích quy trình nội bộ. Chi tiết phụ (nguồn, lịch sử, chứng từ) mở khi bấm.
3. **Dễ đọc.** Chữ thân tối thiểu 16px, số tiền chính lớn hơn và đậm; tương phản đạt WCAG AA (4.5:1); không chỉ dùng màu để báo trạng thái, luôn kèm chữ.
4. **Ngôn ngữ nghiệp vụ quen thuộc.** Dùng từ người dùng đang dùng (khách, kỳ nợ, chuyến, thu tiền, còn nợ…); nút ghi đúng hành động ("Lưu nháp trong tab", "Bỏ dòng đã chọn"); thông báo nói chuyện gì đã xảy ra và cần làm gì tiếp, câu ngắn.
5. **Tiền rõ ràng.** VND nguyên, phân cách hàng nghìn, căn phải, chữ số đều. Ô chưa có giá trị hiện `—`, không cộng như 0. Luôn tách "đã ghi sổ" với "chờ duyệt / chờ giá / chưa xác nhận"; khoản chờ không nằm trong tổng còn nợ.
6. **Thao tác chắc tay.** Vùng bấm tối thiểu 40px; không bắt buộc hover, kéo thả hay phím tắt (có thể thêm sau, không thay nút). Hành động ghi sổ/duyệt có bước xem lại; hành động mất dữ liệu chưa lưu nói rõ số dòng bị ảnh hưởng.
7. **Lỗi ngay tại chỗ.** Lỗi hiện ở đúng ô/dòng kèm một dòng tóm tắt; giữ nguyên dữ liệu người dùng đã nhập.
8. **Nhất quán với màn hình đang có.** Giữ tên cột, nút, câu thông báo hiện có trong workbench; chỉ đổi khi spec nêu lý do.

## Quy tắc cho bản xem/mockup (khi có)

Từ 29/10/2026 mockup Penpot không còn bắt buộc ([`CLAUDE-ALL-01`](decisions/claude-all-01.md)); các quy tắc dưới áp dụng khi có dựng bản xem.

- Khung màn hình chỉ chứa đúng những gì người dùng nhìn thấy. Ghi chú cho người duyệt đặt **ngoài khung**, ngắn, hoặc gom vào một board ghi chú riêng.
- Board xếp theo đúng thứ tự thao tác thật, đánh số bước; mỗi board một trạng thái. Page chỉ gồm board màn hình và một board ghi chú; không lặp lại spec (ranh giới, gate, tiêu chí) trong Penpot.
- Vẽ tỉ lệ 1:1 với app (cùng chiều rộng khung, cùng cỡ chữ) để đánh giá được độ dễ đọc.
- Dữ liệu giả khớp fixture/nguồn ghi trong mục "Đối chiếu dữ liệu" của spec; không bịa số dư, trạng thái hay quy tắc.
- Không tự thêm tính năng, câu hỏi thiết kế hay chính sách ngoài spec; điểm chưa chốt ghi một dòng CÒN MỞ trong ghi chú.
- Sau khi người dùng duyệt một phiên bản (version có tên trong Penpot), không sửa page đó nữa; cần chỉnh thì tạo phiên bản mới và xin duyệt lại.

## Checklist review (Claude và người dùng)

- Luồng có đúng thứ tự công việc thật của người dùng không, có bước thừa không?
- Mỗi màn hình có thông tin nào bỏ được mà không ảnh hưởng quyết định không?
- Người trên 40 tuổi có đọc rõ chữ, số và nhận ra nút chính không?
- Số liệu có khớp fixture/nguồn, ô trống có bị coi là 0, khoản chờ có lọt vào tổng nợ không?
- Câu chữ có từ kỹ thuật hoặc mã nội bộ nào lọt lên giao diện không?
