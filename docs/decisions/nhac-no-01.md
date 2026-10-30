# NHAC-NO-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Thêm phần **theo dõi đòi nợ** để sếp thấy việc đòi tới đâu và lên kế hoạch (bổ sung cho [`DASH-03`](dash-03.md)/[`DASH-04`](dash-04.md) vốn chỉ cho biết ai nợ, quá hạn bao lâu). Kiến trúc chốt 4 thành phần: (A) **helper cục bộ** chạy tay trên PC người dùng khi Zalo mở, khôi phục khóa SQLCipher từ RAM tiến trình Zalo (session.UIN, không lưu khóa), copy các group DB **đã map** rồi đọc **chỉ metadata** `sendDttm`/`fromUid`/`msgType` của bảng `message` — **không đọc nội dung tin nhắn** — suy ra "đã nhắc khách X ngày Y", đẩy lên `hao`; (B) màn **map group ↔ khách** làm tay một lần, chỉ group đã map mới bị đọc; (C) bảng `reminder_log` trên `hao` (`customer_id, source, reminded_at, reminder_count`) là **ghi chú thuần, ngoài đường tiền** — không VND, không khóa tháng, không phân bổ; (D) tab web **Đòi nợ** hiện mỗi khách quá hạn kèm lần nhắc gần nhất, số ngày, nhãn (chưa nhắc / đã nhắc chưa trả / đã trả sau nhắc), và **nút "Copy tin nhắc"** (web soạn tin nợ để người dùng dán vào group, tự ghi `source:copy-button`).

Phạm vi **v1** (người dùng chốt): chỉ mốc "đã nhắc", **bỏ** dự báo tiền về (hẹn trả nằm trong nội dung tin, không đọc); đồng bộ **bấm nút thủ công**, không chạy nền; **có** nút Copy tin nhắc ngay; **chỉ Zalo** (WeChat để sau). Nút Copy là đường bền, dự phòng khi helper hỏng do Zalo cập nhật.

Bất biến: metadata-only (không đọc/đẩy/lưu nội dung tin); không lưu khóa plaintext/UIN; không restart/inject/hook Zalo, chỉ đọc RAM read-only và copy, không mở DB gốc; dữ liệu chat không vào repo. Spec: [`specs/v7-nhac-no-zalo-sync.md`](../../specs/v7-nhac-no-zalo-sync.md).

## Ngày / nguồn

30/10/2026, người dùng chốt trong chat ("làm lớp chat" → sau khi chứng minh giải mã metadata khả thi, chốt kiến trúc và 4 lựa chọn v1 qua phiếu hỏi: bỏ dự báo, bấm tay, có nút Copy, chỉ Zalo). Bối cảnh kỹ thuật Zalo (SQLCipher 4.5.3, khóa = session.UIN trong RAM, lớp nội dung BasicEncryption/E2EE không đọc) đã kiểm chứng cùng ngày trên bản sao snapshot.

## Hiệu lực và giới hạn

ĐÃ CHỐT kiến trúc; CHƯA CODE. Giới hạn đã ghi: khóa chỉ sống trong RAM khi Zalo chạy nên helper fragile và phụ thuộc phiên bản Zalo (nút Copy là lưới an toàn); nội dung tin có thể còn lớp BasicEncryption/E2EE — v1 không cần vì chỉ dùng metadata; mới kiểm chứng trên 2 snapshot, engine kiểm là SQLCipher 4.12 chứ không phải binding của Zalo. CÒN MỞ (việc kỹ thuật khi code, không cần hỏi): xác định đúng `fromUid` chủ TK để tính "chủ TK đã nhắc".
