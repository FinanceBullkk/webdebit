# NHAC-NO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Thêm phần **theo dõi đòi nợ** để sếp thấy việc đòi tới đâu và lên kế hoạch (bổ sung cho [`DASH-03`](dash-03.md)/[`DASH-04`](dash-04.md) vốn chỉ cho biết ai nợ, quá hạn bao lâu). Kiến trúc chốt 4 thành phần: (A) **helper cục bộ** chạy tay trên PC người dùng khi Zalo mở, khôi phục khóa SQLCipher từ RAM tiến trình Zalo (session.UIN, không lưu khóa), copy các group DB **đã map** rồi đọc **chỉ metadata** `sendDttm`/`fromUid`/`msgType` của bảng `message` — **không đọc nội dung tin nhắn** — suy ra "đã nhắc khách X ngày Y", đẩy lên `hao`; (B) màn **map group ↔ khách** làm tay một lần, chỉ group đã map mới bị đọc; (C) bảng `reminder_log` trên `hao` (`customer_id, source, reminded_at, reminder_count`) là **ghi chú thuần, ngoài đường tiền** — không VND, không khóa tháng, không phân bổ; (D) tab web **Đòi nợ** hiện mỗi khách quá hạn kèm lần nhắc gần nhất, số ngày, nhãn (chưa nhắc / đã nhắc chưa trả / đã trả sau nhắc), và **nút "Copy tin nhắc"** (web soạn tin nợ để người dùng dán vào group, tự ghi `source:copy-button`).

Phạm vi **v1** (người dùng chốt): chỉ mốc "đã nhắc", **bỏ** dự báo tiền về (hẹn trả nằm trong nội dung tin, không đọc); đồng bộ **bấm nút thủ công**, không chạy nền; **có** nút Copy tin nhắc ngay; **chỉ Zalo** (WeChat để sau). Nút Copy là đường bền, dự phòng khi helper hỏng do Zalo cập nhật.

Bất biến: metadata-only (không đọc/đẩy/lưu nội dung tin); không lưu khóa plaintext/UIN; không restart/inject/hook Zalo, chỉ đọc RAM read-only và copy, không mở DB gốc; dữ liệu chat không vào repo. Spec: [`specs/v7-nhac-no-zalo-sync.md`](../../specs/v7-nhac-no-zalo-sync.md).

## Ngày / nguồn

30/10/2026, người dùng chốt trong chat ("làm lớp chat" → sau khi chứng minh giải mã metadata khả thi, chốt kiến trúc và 4 lựa chọn v1 qua phiếu hỏi: bỏ dự báo, bấm tay, có nút Copy, chỉ Zalo). Bối cảnh kỹ thuật Zalo (SQLCipher 4.5.3, khóa = session.UIN trong RAM, lớp nội dung BasicEncryption/E2EE không đọc) đã kiểm chứng cùng ngày trên bản sao snapshot.

## Sửa đổi 30/10/2026: hiện nội dung chat từ bản xuất (ZALO-CHAT-01)

Người dùng chốt cùng ngày trong chat ("tính năng đòi nợ đang không đúng ý", giao bundle `zalo-web-handoff-20261030` do HermesAgent xuất: 104.387 tin đã giải mã, 331 hội thoại, ID băm HMAC, không URL/media). Thay thành phần (A) và bất biến *metadata-only*: web có trang **Chat Zalo** (con của tab Đòi nợ) đọc **nội dung** hội thoại từ bản xuất theo trang, tìm hội thoại và tìm trong hội thoại; mỗi dòng khách ở Đòi nợ có nút **Chat**. Helper đọc RAM Zalo không làm nữa. Giữ: (C) `reminder_log` và nút Copy tin nhắc; dữ liệu chat không vào repo; chỉ đọc; truy cập qua lớp danh tính hiện có. Bản xuất nằm ngoài release, bật bằng `WEBDEBIT_ZALO_EXPORT_DIR`; chép lên `hao` hay không là việc người dùng quyết. Spec: [`specs/v7-zalo-chat-viewer.md`](../../specs/v7-zalo-chat-viewer.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT kiến trúc; tab Đòi nợ + Copy tin nhắc đã code (PR [FinanceBullkk/webdebit#203](https://github.com/FinanceBullkk/webdebit/pull/203), `4251cb6`); trang Chat Zalo đã code 30/10/2026 (ZALO-CHAT-01), chưa có bản xuất trên `hao`. **ĐÃ TRIỂN KHAI tab Đòi nợ trên `hao` 30/10/2026** (người dùng duyệt "Merge + deploy hao"): migration áp trong cửa sổ dừng ghi, tổng từng khách và số event 236/6555 không đổi, checker 9/9 OK, release đổi `c8b3c23`→`4251cb6`, `/doi-no.html` và `GET /api/v7/reminders` trả 200 ([nhật ký](../deploys/2026-10-30-nhac-no.md)). Giới hạn đã ghi: khóa chỉ sống trong RAM khi Zalo chạy nên helper fragile và phụ thuộc phiên bản Zalo (nút Copy là lưới an toàn); nội dung tin có thể còn lớp BasicEncryption/E2EE — v1 không cần vì chỉ dùng metadata; mới kiểm chứng trên 2 snapshot, engine kiểm là SQLCipher 4.12 chứ không phải binding của Zalo. CÒN MỞ: người dùng tự đi hết luồng tab Đòi nợ trên web thật; trang Chat Zalo chưa có bản xuất trên `hao`; xác định đúng `fromUid` chủ TK để tính "chủ TK đã nhắc".
