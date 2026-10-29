# NHAP-SHEET-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng/chủ nghiệp vụ chốt cách nhập và sửa chuyến trên sổ V7 theo lối Sheet ([`specs/v7-nhap-kieu-sheet.md`](../../specs/v7-nhap-kieu-sheet.md)): (1) bỏ ô "Dán các dòng từ Sheet"; tháng đang mở luôn có **một hàng trống**, dán vào ô bất kỳ thì tự trải theo bố cục tab khách, gõ tay cũng được; hàng mới là **nháp**, bấm **Lưu** một lần mới ghi sổ (một lệnh dán lô, kiểm trùng [`NEWTRIP-01`](newtrip-01.md)); bảng nhập **chỉ nhận chuyến**, phần tiền khách trả dán vào bị bỏ qua. (2) Chuyến đã lưu **sửa đè tại ô**, rời ô/Enter là lưu, ghi Lịch sử trước → sau. (3) **Tháng đã khóa cũng sửa đè được** các ô chữ và ngày; đơn giá/phụ phí của tháng khóa người dùng vẫn gõ đè, hệ thống ghi thành dòng điều chỉnh theo [`V7-SO`](v7-so.md). (4) **Được xóa hẳn một chuyến**, ghi Lịch sử. (5) **Đổi ngày chuyến sang tháng khác thì chuyến tự chuyển sang bảng của tháng đó** (kỳ nợ theo tháng của ngày chuyến); chuyến nháp lưu cũng vào tháng của ngày chuyến. (6) **Dòng từ sổ gốc sửa và xóa được** như chuyến web; số dư đầu không bị viết lại, phần chênh (số mới − số trong bản mốc, xóa thì trừ hết) ghi thành điều chỉnh có Lịch sử. (7) Chuyến nháp có ngày thuộc **tháng đã khóa** khi Lưu **vào thẳng tháng đó**, không chặn, không cần mở khóa.

**Thay một phần (29/10/2026):** vế (1) — bảng nhập/hàng trống/nháp + Lưu — đã bỏ theo [`NHAP-SHEET-02`](nhap-sheet-02.md); chuyến mới lấy từ Sheet. Các vế (2)–(7) còn hiệu lực.

## Ngày / nguồn

22/10/2026, xác nhận trong chat: (1) chọn "Nháp + nút Lưu", "Chỉ nhận chuyến", "bản xem HTML"; (2) "khi lưu xong thì data vẫn phải chỉnh sửa được"; (3)–(6) trả lời "1. cho sửa đè 2. cho xóa hẳn 1 chuyến. Khi đổi tháng tự chạy bảng của tháng đó 3. có"; (7) "Chuyến nháp có ngày thuộc tháng đã khóa thì cho vào thẳng tháng đó"

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng; có bản xem HTML dữ liệu giả. **Chưa triển khai**: trang live vẫn dùng ô dán 7 cột; backend chưa có lệnh sửa trường chữ/ngày, xóa chuyến, sửa dòng sổ gốc. Vế (6) trả lời CÒN MỞ (b) của [`MOC-CHUYEN-MOI`](moc-chuyen-moi.md) và vế "cách ghi kỹ thuật giá điền sau mốc" của [`SONG-SONG-01`](song-song-01.md) ở mức chính sách; cách ghi kỹ thuật (bảng/sự kiện điều chỉnh gắn dòng sổ gốc, phân bổ lại phiếu) CÒN MỞ tới khi có spec backend. Không đổi luật tiền khác của V6, `V7-SO`, `V7-BE`.
