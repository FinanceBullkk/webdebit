# DEBIT-NOTE-03

[← Sổ quyết định](../decisions.md)

## Quyết định

Debit note **mẫu v4**: một trang A4 ngang theo gói thiết kế v4.0 bộ phận chốt 10/11/2026 ([`docs/debit-note-v4/SPEC.md`](../debit-note-v4/SPEC.md), trang mẫu ở `docs/debit-note-v4/reference/`). Từ trên xuống: đầu trang, BILL TO | DOCUMENT, bảng container + dòng Total, PAYMENT INFORMATION | ACCOUNT STATUS. Không còn Amount due và Charge summary; số phải trả là ô Amount của dòng Total. Mẫu v3 ([DEBIT-NOTE-02](debit-note-02.md)) vẫn bật lại được bằng cấu hình cho tới khi team duyệt mẫu v4 trên dữ liệu thật. Spec: [`specs/v7-debit-note.md`](../../specs/v7-debit-note.md) mục Mẫu v4.

Người dùng chốt (chat 10/11/2026, trả lời câu hỏi của Claude sau khi đọc gói):

1. **Cột phí theo cột phụ phí của sổ** ([PHU-PHI-01](phu-phi-01.md)): Unit price, các cột riêng của sổ (tối đa 3, theo thứ tự sổ), rồi Khác. Loại không phải cột riêng của sổ (Phụ phí ban đầu, Khác, Giảm trừ…) vào cột Khác. Vì vậy không bao giờ quá 5 cột phí, không cần quy tắc gộp cột của SPEC mục 4.2.
2. **Lump-sum đổi thành Unit price** `单价`, như [#364](https://github.com/FinanceBullkk/webdebit/pull/364) đã đổi ở mẫu v3.
3. **Không có cột B/L no.** (sổ chưa có số B/L); cột Shipper rộng ra.
4. **ACCOUNT STATUS**: Opening balance = nợ trước tháng công nợ; Payments received = phiếu thu, cấn trừ và điều chỉnh trong tháng; Outstanding balance = còn nợ cuối tháng. Số lấy nguyên từ `months[]` của `GET /api/v7/ledger`: Payments = `received_vnd − (charges_vnd − Total)`, Outstanding = `end_of_month_vnd`. Chỉ để tham khảo, không cộng vào số phải trả. Điểm (5) "không ghi nợ cũ" của [DEBIT-NOTE-01](debit-note-01.md) vẫn đúng cho số phải trả.
5. **Xuất cả Excel** cùng cột với PDF. 11/11/2026 người dùng chê file Excel "format bị lỗi, xấu, không giống design": Excel làm lại theo bố cục PDF (thanh navy, đầu trang, BILL TO | DOCUMENT, bảng tiêu đề nền #E6EBF2 chữ Anh đậm trên chữ Trung thường dưới, Total kẻ đơn trên kẻ đôi dưới, PAYMENT | ACCOUNT STATUS với số thẳng cột Amount, chân trang; Times New Roman). Bảng vẫn không gộp ô; bỏ bộ lọc và cố định hàng tiêu đề vì nút lọc che chữ tiêu đề (Claude chọn).

## Claude chọn (theo `CLAUDE-ALL-01`, người dùng sửa được khi xem bản thử)

- **Xuất PDF**: trang sổ dựng HTML với CSS chép từ trang mẫu, chia trang bằng cách đo chiều cao trong khung in rồi mở hộp in của Chrome (khổ A4 ngang, lề 0 theo `@page`). `tools/debit-note-v4-pdf.js` xuất cùng HTML bằng Chromium headless (Playwright) để kiểm thử và so ảnh. Chưa cài Chromium trên `hao`: xuất phía máy chủ cần người dùng cho phép (việc hạ tầng).
- **Cấu hình** công ty, ngân hàng, tên phí Anh/Trung, mẫu đang dùng: `GET /api/v7/debit-note/config` đọc `web/debit-note-config.default.json` (chỉ thông tin công khai, ô chưa có là null → in `[Tên trường]`) ghi đè bằng file riêng ở `WEBDEBIT_DEBIT_NOTE_CONFIG` ngoài repo (repo public). Mặc định `v3`; `?debit=v4` / `?debit=v3` trên địa chỉ trang để xem thử mẫu kia.
- **Sáu phép kiểm** của SPEC mục 7 chạy trước khi xuất; thêm chặn khi thiếu giá, khi máy chủ không có số tháng, khi không đọc được cấu hình. Còn chặn thì khóa In và Excel (không có bản nháp như v3). Cảnh báo (nơi/cảng ngoài danh mục, số container sai ISO 6346) cần tích xác nhận.
- Cột phí **hiện khi có ô khác 0** trên cả chứng từ (SPEC ghi "tổng ≠ 0"; chọn vậy để khoản +x/−x không bị ẩn làm sai phép 1), như mẫu v3.
- **Phí không gắn container** là dòng không đánh số "Additional charge · 附加费用" cuối bảng, không tính vào số container.
- **Ngày ở Payments received** là ngày phiếu thu hoặc cấn trừ đi muộn nhất trong tháng; tháng không có thì để trống.
- **Không in tiếng Việt**: chữ Latin bỏ dấu khi in; tên tiếng Trung của nơi/cảng ([DIA-DIEM-01](dia-diem-01.md)) chỉ in khi cấu hình `show_place_cn` bật, vì trang mẫu v4 chỉ có tên Latin. Khi bật, tên Trung nằm cùng dòng bên phải tên Latin, không xuống dòng (người dùng 11/11/2026); cột Loading place / POD nới theo tên dài nhất của chứng từ, Shipper co lại tới 60px, còn thiếu chỗ thì chữ hai cột này thu nhỏ, không dưới 9px. Bản in và Excel v4 cùng theo cờ này. Người dùng muốn debit note có tên tiếng Trung (chat 11/11/2026), nên cờ đã bật trên `hao` ngày 11/11/2026; tắt lại là sửa file cấu hình riêng, không cần deploy.
- Ngày phát hành để trống thì in `[Issue date]` (SPEC mục 8 đang chờ team), người lập điền thì in ngày đó.

## Ngày / nguồn

10/11/2026, chat: người dùng gửi gói `debit-note-v4-handoff` (SPEC, trang HTML mẫu, ảnh PNG/PDF chuẩn, dữ liệu mẫu) và yêu cầu thay mẫu xuất; trả lời các câu hỏi về cột phí, Lump-sum, B/L, ACCOUNT STATUS và Excel. Gói trong repo đã bỏ thông tin ngân hàng; bản đầy đủ ở `D:\webdebit\design\debit-note-v4\` ngoài git.

## Hiệu lực và giới hạn

ĐÃ CHỐT các điểm 1–5. ĐÃ CODE, mặc định trong code vẫn mẫu v3. ĐÃ TRIỂN KHAI trên `hao` 11/11/2026 theo lời người dùng "Bật v4 ngay": file cấu hình riêng `/etc/webdebit/debit-note.json` (`"template": "v4"`; chưa có ngân hàng, bản in ghi `[Tên trường]`; `show_place_cn` cũng bật cùng ngày, xem điểm Không in tiếng Việt) và drop-in `v7-ledger-api.service.d/debit-note.conf` đặt `WEBDEBIT_DEBIT_NOTE_CONFIG`. Về v3, thêm ngân hàng hoặc tắt tên Trung: sửa file JSON, không cần khởi động lại. CÒN MỞ theo SPEC mục 8 (không tự điền): người thụ hưởng và nhãn `USD Account` khi tiền là VND; Issue date, Tax ID, Phone, tên pháp lý và địa chỉ khách, người liên hệ; địa chỉ HTH; tên phí tiếng Trung. Thêm: xuất PDF phía máy chủ `hao` (cần cài Chromium); team duyệt mẫu v4 trên dữ liệu thật.
