# PHIEU-WEB-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Từ 1/12/2026 mọi phiếu thu nhập trên web ([`WEB-CHINH-01`](web-chinh-01.md)), nên khung **Ghi phiếu thu** của Sổ khách phải ghi được mọi kiểu phiếu đang gặp trên Sheet, cho cả login người dùng ([`QUYEN-01`](quyen-01.md)). Phiên kiểm toàn bộ website giao 25/11/2026; Claude đặt cách làm dưới đây (ĐỀ XUẤT, không đổi luật tiền, không thêm hàm SQL).

1. **Phiếu không rõ ngày trả.** Khung có ô đánh dấu "Không rõ ngày trả". Đánh dấu thì ô ngày tắt, người chọn tháng khách trả (12 tháng tới tháng hiện tại, không chọn sẵn để không ghi nhầm tháng). Phiếu ghi:
   - **ngày** = ngày cuối tháng đó, không sau hôm nay (giờ VN) — đúng luật phiếu Sheet không ngày chủ sổ chốt 4/11/2026 (`month_end` ở `web/v7_sheet_fix.py`, xem [`MAY-DOI-SOAT-01`](may-doi-soat-01.md)). Hàm phía trang là `CongNoFormat.symbolicDate`; hai bên chạy chung bộ ca ở `cong-no-web-handoff/tests/golden/ngay-tuong-trung.json`, lệch luật là test đỏ;
   - **tham chiếu** = chữ người gõ + đuôi ` (ngày tượng trưng)`, đuôi mà Bảng thu, ngày trả thật và chữ tham chiếu trên sổ đã nhận ra ([`BANG-THU-01`](bang-thu-01.md)). Không gõ gì thì chữ là "Không rõ ngày" (server cắt khoảng trắng hai đầu, đuôi đứng một mình sẽ mất dấu cách và thôi khớp);
   - bước xem lại ghi rõ "(ngày tượng trưng)". Biết ngày thật sau thì sửa ngày ở dòng phiếu như phiếu thường.
   Cấn trừ cần ngày cụ thể: hình thức CẤN TRỪ không đi cùng "Không rõ ngày trả".

Các mục sau (một lần chuyển chia nhiều sổ, dán nhiều phiếu một lần, ghi phiếu từ ảnh Thu chi) thêm vào file này theo từng PR.

## Ngày / nguồn

25/11/2026, phiên kiểm toàn bộ website giao việc theo `WEB-CHINH-01`. Đo chỉ đọc trên `hao` cùng ngày: từ 1/10/2026 có 104 phiếu, đều từ login quản lý, trong đó 6 phiếu ngày tượng trưng; login người dùng chưa ghi phiếu nào.

## Hiệu lực và giới hạn

ĐỀ XUẤT của Claude trong phạm vi việc được giao; mục 1 không đổi DB, API hay quyền. ĐÃ KIỂM CHỨNG bằng test trang (`test-cong-no-format.js`, `test-so-khach-v7-entry-browser.js`) và unittest `test_v7_sheet_fix.py`. Người nhập đi thử trên `hao` là bước còn lại.
