# HOAT-DONG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Tab **"Máy đã làm"** của Việc cần làm đổi thành **"Đã làm"**: xem việc đã ghi của **một ngày bất kỳ**, mọi sổ, **cả máy lẫn người**, để chủ sổ biết ngày đó đã nhập và sửa những gì.

1. Nguồn là Lịch sử trong DB (bảng `sokhach.event`): mọi hàm ghi đều chèn một dòng có người làm, giờ, trước → sau. Không đọc nhật ký trong RAM của hộp việc nữa (chỉ có hôm nay và mất khi API khởi động lại).
2. Mặc định là hôm nay (giờ VN). Thanh chọn ngày: nút về **ngày gần nhất trước đó có việc**, ô chọn ngày (không quá hôm nay), nút ngày sau, nút "Hôm nay". Lọc **Tất cả / Máy / Người**, kèm số việc.
3. Mỗi dòng: giờ · người làm (máy là "Máy", người là tên ngắn theo PRESENCE-01) · sổ · câu **giống hệt khung Lịch sử của sổ** (cùng file `so-khach-v7-lich-su-cau.js`) · ghi chú/lý do · Mở sổ. Hôm nay giữ dòng "Đã ghi hôm nay" như trước.
4. Số trên nhãn tab vẫn là số việc máy làm hôm nay như trước.
5. Một ngày hiện tối đa 2.000 việc mới nhất; ngày nhiều hơn thì ghi rõ tổng.

Backend: hàm đọc `get_activity(date)` cấp cho app (không cấp reader, như `get_ledger_events`), route `GET /api/v7/activity[?day=yyyy-mm-dd]`. Migration `2026-11-09-v7-hoat-dong.sql` chỉ thêm hàm, triển khai tay theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md). Spec: [`specs/v7-viec-can-lam-doi-chieu.md`](../../specs/v7-viec-can-lam-doi-chieu.md), mục Tab Đã làm.

## Ngày / nguồn

9/11/2026, người dùng trong chat: hỏi tab Máy đã làm "có thể check toàn bộ lịch sử các ngày khác luôn không, để sếp biết là đã có những gì được nhập và sửa vào"; chọn "Làm, cả máy và người". Cách hiện (ngày gần nhất có việc, lọc, dùng chung câu chữ Lịch sử) do Claude quyết theo [`CLAUDE-ALL-01`](claude-all-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT. ĐÃ TRIỂN KHAI trên `hao` 9/11/2026 14:15 (migration và release `451b5c2`, [nhật ký](../deploys/2026-11-09-hoat-dong.md)). Chỉ đọc: không đổi bảng, hàm ghi, tiền hay quyền cũ. Trạng thái triển khai ghi theo lượt `Deploy hao` (frontend) và nhật ký `docs/deploys/` (migration). Release mới trên DB chưa có hàm thì tab báo không tải được và có Thử lại. CÒN MỞ: người dùng tự đi hết luồng trên `hao`.
