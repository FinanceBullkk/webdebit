# ZALO-GROUP-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Theo dõi nợ bằng chính tin nhắn trong group Zalo chung với khách, theo spec [`v7-zalo-group-web.md`](../../specs/v7-zalo-group-web.md):

1. **Dựng lại tin như `zalo-audit-viewer`** trên trang Chat Zalo: bong bóng kiểu Zalo, tên người gửi, **có ảnh**. Người dùng chốt ảnh là phần quan trọng (ảnh chuyển khoản).
2. **Đánh dấu một tin** và nối dấu vào trang khách (thẻ Trao đổi). Bấm vào dấu thì mở lại đúng tin.
3. **Chỉ group được chọn mới lên `hao`.** Việc chọn làm ở máy có Zalo. Hội thoại riêng tư không rời máy.
4. **Người dùng tự bấm đánh dấu**: người dùng được add vào các group của khách.
5. **Làm luôn**, không chờ hết đợt tạm dừng tính năng mới của PLAN.

Mặc định Claude chọn, người dùng đã đọc trong chat và không phản đối:

- **"Đã thanh toán" đổi thành "Khách báo đã chuyển".** Dấu này không ghi tiền. Nó là việc chờ đối chiếu, máy tự chấm theo phiếu thu: có phiếu thu đúng số trong khoảng ngày → đã có phiếu thu; quá 3 ngày chưa có → chưa thấy phiếu thu. Lý do: tiền chỉ vào sổ bằng phiếu thu, không thêm chỗ ghi tiền thứ hai ([`UX-NEN-01`](ux-nen-01.md) M1).
- **"Đã nhắn hỏi nợ" không cần nút.** Lần mình nhắn gần nhất đọc thẳng từ chat (`last_own_message_at`, như ZALO-CHAT-01).
- **Ba loại dấu:** Hứa trả (số tiền, hẹn ngày), Khách báo đã chuyển (số tiền, ngày), Ghi chú. Hứa trả chính là B2 của [`TRANG-KHACH-01`](trang-khach-01.md) K4, cùng bảng, cùng cách máy tự chấm.
- **Gắn group ↔ sổ nhiều–nhiều**, làm tay một lần (TRANG-KHACH-01 K6, B3). Đánh dấu trong group gắn nhiều sổ thì phải chọn sổ.
- **Mỗi dấu lưu kèm giờ, người gửi và đoạn chữ của tin** (≤ 300 ký tự). Dấu vẫn đọc được khi tin không còn trên web (bỏ chọn group, dựng lại kho đổi mã tin).
- Bỏ dấu, bỏ gắn: bắt buộc lý do, giữ vết, như hủy phiếu.

## Ngày / nguồn

1/11/2026, chat. Người dùng: "dựng lại các tin nhắn như bạn đã thấy trong zalo-audit-viewer… thêm button để mark… nối vào UI để khi track thì mở lại được". Sau khi Claude nêu rủi ro (hai chỗ ghi tiền, bấm thừa, dựng giống hệt Zalo), người dùng trả lời ba câu: người dùng bấm; chỉ group muốn show lên web; ảnh quan trọng. Chọn "Làm luôn".

## Hiệu lực và giới hạn

ĐÃ CHỐT.
- **G1** (công cụ dựng gói, FinanceBullkk/webdebit#241) và **G2** (trang chat đọc gói, ảnh, mở đúng tin, FinanceBullkk/webdebit#243): đã lên `hao` 1/11/2026.
- **G3** (bảng `zalo_link`, `contact_mark`, API, FinanceBullkk/webdebit#244): nâng DB tay trên `hao` 1/11/2026 ([nhật ký](../deploys/2026-11-01-zalo-group.md)).
- **G4** (nút Đánh dấu, gắn sổ trong chat, dấu ở thẻ Trao đổi): đã code.
- **G5** (đẩy gói lên `hao`): chưa làm. `hao` chưa có gói chat nên trên web thật chưa xem hay đánh dấu được.

- Mọi bảng mới nằm ngoài đường tiền: không vào `v_outstanding_month`, không đổi phân bổ, không khóa tháng, không bump `customer.version`. Triển khai theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md).
- **Đẩy gói chat lên `hao` cần hỏi người dùng trước** khi mở đường ghi mới (CLAUDE.md: đổi quyền ngoài runbook). Chép dữ liệu chat lên `hao` chỉ gồm group đã chọn; người dùng đã đồng ý nguyên tắc này ngày 1/11/2026.
- Thay một phần [`NHAC-NO-01`](nhac-no-01.md), sửa đổi ZALO-CHAT-01: trang chat đọc **gói web** (chỉ group đã chọn, có ảnh) thay cho bản xuất 30/10. Bản xuất cũ vẫn đọc được.

Còn mở: một group thường là một khách hay nhiều khách (thiết kế cho cả hai); tự đẩy gói theo lịch hay bấm tay.
