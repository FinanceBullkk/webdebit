# PRESENCE-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt web V7 hiện **ai đang online và đang ở đâu** như Google Sheets, gồm cả hai mức: (1) người đang mở web, trang/sổ khách/tháng họ đang xem, ô họ đang chọn hoặc đang sửa; (2) **con trỏ chuột** của người khác di chuyển trên bảng sổ khách. Chỉ là chỉ báo: không khóa ô, không chặn lưu; chống ghi đè vẫn dùng phiên bản sổ (`STALE_LEDGER`) hiện có. Spec: [`specs/v7-ai-dang-online.md`](../../specs/v7-ai-dang-online.md).

## Ngày / nguồn

29/10/2026, chat: hỏi "thấy ai đang online … thao tác ở tab nào vùng nào", rồi "hiện được vị trí con trỏ của người kia luôn", chọn "cả 1 và 2".

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng. Backend (`web/v7_presence.py`, PR FinanceBullkk/webdebit#141) đã triển khai trên `hao` 29/10/2026. Mức 1 (vòng tròn, chấm ở Tổng quan/ma trận, viền ô đang chọn/đang sửa, câu báo sổ vừa đổi kèm tên) ĐÃ CODE: `preview/presence.js`, `presence.css`, `so-khach-v7-presence-ui.js`; ĐÃ TRIỂN KHAI trên `hao` cùng release `639c1d7` (đợt bảng giá + ảnh chứng từ 29/10/2026); ĐÃ KIỂM CHỨNG qua Tailscale 29/10/2026: trang nạp `presence.js`, SSE qua `tailscale serve` đẩy về khoảng 0,25 giây sau khi tab khác báo vị trí. Mức 2 (mũi tên chuột neo theo dòng + cột + phần nghìn trong ô, tối đa 5 lần báo/giây, nút **Ẩn con trỏ** nhớ theo trình duyệt) ĐÃ CODE; triển khai tự động khi merge qua `Deploy hao`. CÒN MỞ: chưa thử bằng hai người thật trên trình duyệt. Thiết kế chi tiết ĐỀ XUẤT trong spec; frontend chờ duyệt bản xem dữ liệu giả. Chưa code, chưa triển khai. Tên hiển thị (người dùng chọn 29/10/2026 "Đổi tên"): bảng tên ngắn theo login Tailscale trong file trên máy chạy, ngoài Git vì chứa login — mặc định `/srv/v7/presence-names.json` (đổi bằng `WEBDEBIT_PRESENCE_NAMES_PATH`), dạng `{"version": 1, "names": {"<login>": "<tên ≤ 30 ký tự>"}}`; sửa file là có hiệu lực, không cần khởi động lại; login không có trong bảng hoặc file hỏng thì dùng phần trước `@`. Từ PR 2d của [`SO-GON-04`](so-gon-04.md) (31/10/2026), Lịch sử của sổ khách cũng ghi tên này: `GET /api/v7/ledger` gắn `events[].actor_name` theo cùng bảng. CÒN MỞ: nội dung bảng tên trên `hao`.
