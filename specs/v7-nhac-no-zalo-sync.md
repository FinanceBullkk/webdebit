# Theo dõi đòi nợ: tab Đòi nợ + đồng bộ "đã nhắc" từ Zalo

Trạng thái: ĐÃ CHỐT kiến trúc (người dùng, 30/10/2026). v1: chỉ mốc "đã nhắc" (không dự báo tiền về), đồng bộ bấm tay, có nút Copy tin nhắc, **chỉ Zalo**. Còn một việc kỹ thuật nhỏ khi code (xác định `fromUid` chủ TK).

## Vấn đề

Web đã trả lời "khách nào nợ, quá hạn bao lâu, nên đòi ai trước" (DASH-03/04). Chưa trả lời "đã đòi khách đó chưa, lần cuối khi nào" → sếp không biết việc đòi tới đâu, không lên kế hoạch được. Người đi đòi (một mình người dùng) trao đổi với khách qua **group Zalo/WeChat**; không muốn thêm bước ghi tay sau mỗi lần nhắc.

## Người dùng và luồng

- **Người dùng (đi đòi):** nhắc khách trong group Zalo như hiện tại. Định kỳ bấm **"Đồng bộ nhắc nợ"** (khi Zalo đang mở) → web tự cập nhật "đã nhắc khách X ngày Y". Không gõ gì thêm.
- **Sếp (xem):** mở tab **Đòi nợ** → thấy từng khách quá hạn kèm *lần nhắc gần nhất · số ngày từ lần nhắc · nhãn* (chưa nhắc / đã nhắc chưa trả / đã trả sau nhắc). Lọc nhanh: **chưa ai nhắc**, **nhắc lâu chưa trả**.

Luồng bị chặn: Zalo không mở → không đồng bộ được (báo rõ, giữ số liệu lần trước). Group chưa map với khách → không đọc.

## Đầu ra

Tab **Đòi nợ** hiển thị, mỗi khách quá hạn: nợ quá hạn, lần nhắc gần nhất (nguồn: Zalo-sync hoặc nút Copy), số ngày từ lần nhắc, nhãn. Mốc "đã nhắc" được cập nhật tự động sau mỗi lần bấm Đồng bộ, **không ai gõ tay**.

## Kiến trúc (4 thành phần)

### A. Helper cục bộ `nhac-sync` (chạy trên PC người dùng, nơi có Zalo)
1. Chỉ chạy khi Zalo đang mở; kích hoạt **thủ công** (nút/CLI), không nền thường trực.
2. Khôi phục khóa SQLCipher từ **RAM tiến trình Zalo** (session.UIN, 32 ký tự) — đã chứng minh được (xem Đối chiếu). **Không lưu khóa ra đĩa.**
3. Copy các group DB **đã map** (`g<gid>.db`+wal+shm) sang thư mục tạm (read-only trên bản gốc).
4. Mở bản sao bằng SQLCipher; đọc **CHỈ** `sendDttm`, `fromUid`, `msgType` của bảng `message`. **Không đọc** `message`/`content`/`quote`/… (nội dung).
5. Suy ra mỗi khách: **ngày gần nhất chủ TK gửi** trong group đó = "đã nhắc gần nhất"; số lần nhắc trong kỳ.
6. Đẩy lên `hao` qua endpoint xác thực (Tailscale): chỉ `{customer_id, reminded_at, reminder_count, source:"zalo"}`. **Không đẩy nội dung, không đẩy uid thô.**

### B. Map group ↔ khách (làm tay một lần)
- Màn web liệt kê group id của các group liên quan; người dùng gán mỗi group → một sổ khách. Lưu trên `hao`. **Chỉ group đã map mới bao giờ bị đọc.**

### C. Lưu trên `hao`: bảng ghi chú, KHÔNG phải đường tiền
- Bảng `reminder_log`: `customer_id, source (zalo|copy-button|manual), reminded_at (ngày), reminder_count, created_at`. Không nội dung, không số tiền → không phải quy tắc tiền, không đụng khóa tháng/phân bổ.

### D. Tab web "Đòi nợ" (đọc `hao`)
- Mỗi khách quá hạn: nợ quá hạn (từ dữ liệu hiện có) + `reminded_at` gần nhất + số ngày + nhãn. Nhóm lọc: chưa nhắc / nhắc lâu chưa trả. Đối chiếu "đã trả sau nhắc" = có phiếu thu sau `reminded_at`.

## Đối chiếu dữ liệu và code hiện có

- **Khóa + giải mã:** đã kiểm chứng 30/10 — khóa lấy từ RAM mở được DB; đọc được `sendDttm`/`fromUid` dạng thường (bản sao `db_2.TTLItem`, ngày thật 23–30/10). PoC ở scratchpad phiên; audit độc lập tại `HermesAgent/.../continuation-20261030` (SQLCipher 4.5.3, page 4096/kdf 256000/PBKDF2-HMAC-SHA512/HMAC-SHA512).
- **Nợ quá hạn / rủi ro / lần trả gần nhất:** đã có theo DASH-03 (quy tắc hạn trả, rủi ro, DA-THU-01).
- **Còn thiếu:** helper cục bộ, endpoint nhận `reminder_log` trên `hao`, bảng `reminder_log`, màn map group↔khách, tab Đòi nợ.

## Hành vi và bất biến

- **Metadata-only:** tuyệt đối không đọc/đẩy/ lưu nội dung tin nhắn; chỉ thời gian + người gửi.
- Không lưu khóa plaintext/UIN; không restart/inject/hook Zalo; chỉ đọc RAM read-only; chỉ copy, không mở DB gốc.
- Chỉ group đã map mới bị đọc. Dữ liệu chat không bao giờ vào repo.
- `reminder_log` là ghi chú, ngoài đường tiền: không đụng VND/khóa tháng/phân bổ/opening.
- Nếu khôi phục khóa thất bại (Zalo cập nhật) → helper báo lỗi, **lớp web vẫn chạy** nhờ nút "Copy tin nhắc" (tự ghi `source:copy-button`).

## Đã chốt (người dùng, 30/10/2026)

1. **Dự báo tiền về / "hẹn trả":** BỎ ở v1 — chỉ mốc "đã nhắc". (Hẹn trả nằm trong nội dung tin, ta không đọc; có thể thêm ô nhập tay sau.)
2. **Nhịp đồng bộ:** **bấm nút thủ công** "Đồng bộ nhắc nợ" khi Zalo mở; không chạy nền.
3. **Nút "Copy tin nhắc":** làm luôn ở v1 — đường bền, dự phòng khi helper hỏng.
4. **Nguồn chat:** v1 **chỉ Zalo**; WeChat để sau.

## Việc kỹ thuật còn lại (khi code, không cần hỏi)

- Xác định đúng `fromUid` của chủ TK một lần (lần đọc `TTLItem` chưa khớp id đoán) để tính "chủ TK đã nhắc".

## Tiêu chí nghiệm thu (khi code)

- [ ] Helper: trên bản sao một group thật đã map, đọc đúng ngày gửi gần nhất của chủ TK; không truy vấn nào chạm cột nội dung (test chặn danh sách cột).
- [ ] `hao`: nhận và lưu `reminder_log`; không có trường nội dung; endpoint xác thực.
- [ ] Tab Đòi nợ: khách quá hạn hiện `reminded_at` + nhãn đúng; "chưa nhắc" lọc đúng.
- [ ] Khóa recover thất bại → thông báo rõ, web vẫn chạy bằng nút Copy.
- [ ] Người dùng tự đi hết luồng trên bản thử.

## Nguồn quyết định

- [DASH-03](../docs/decisions/dash-03.md), [DASH-04](../docs/decisions/dash-04.md) (Tổng quan, hạn trả, rủi ro) · [DA-THU-01](../docs/decisions/da-thu-01.md).
- Bối cảnh kỹ thuật Zalo crypto: bộ nhớ phiên `zalo-pc-chat-crypto`. Khi CHỐT sẽ tạo `docs/decisions/nhac-no-01.md`.
