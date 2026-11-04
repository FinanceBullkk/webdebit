# MAY-KHOA-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **khóa tháng chỉ chặn người, không chặn máy (theo Sheet).** Người vẫn dùng khóa tháng như [`V7-SO`](v7-so.md) và [`KHOA-CHU-01`](khoa-chu-01.md).

Máy làm thêm hai việc, kể cả ở tháng đã khóa:

- **A. Điền ngày cho dòng sổ gốc không có ngày.** Điều kiện: cùng container với một dòng Sheet booking, **cùng tháng nợ**, và trong sổ chỉ có đúng một dòng như vậy. Máy điền ngày theo Sheet. Không đổi tiền, không đổi tháng. Áp cho mọi tháng.
- **B. Đưa chuyến mới vào tháng đã khóa**, với đúng điều kiện máy đang dùng cho tháng mở ([`HANG-CHO-01`](hang-cho-01.md) Q2, P3b): khớp sổ theo mặt hàng, ngày không sau hôm nay, chưa có giá thì chưa cộng nợ. **Chỉ từ tháng 10/2026** (tháng nạp V7). Trước đó sổ gốc là chuẩn, nên chuyến mới tháng 1–9 vẫn để người xem.

Cách máy làm ở tháng khóa: **mở khóa tháng, ghi, khóa lại ngay**, bằng đúng ba lệnh có sẵn. Cả ba đều vào Lịch sử, người làm là "Máy (theo Sheet)". Lệnh ghi lỗi thì máy vẫn khóa lại.

Vẫn để người quyết: lệch ngày khi dòng cũ đã có ngày, ngày Sheet khác tháng nợ, container ở khách khác, khớp nhiều chuyến, lệch booking, mặt hàng không khớp sổ.

## Ngày / nguồn

3/11/2026, chat. Claude đo hàng chờ trên `hao` (chỉ đọc), còn khoảng 157 dòng:
- 57 dòng "container đã dùng" thật ra là dòng sổ gốc không ngày, cùng tháng;
- 62 chuyến mới chỉ bị chặn vì tháng đã khóa (52 dòng tháng 10).

Người dùng chọn "Cả nhóm A và B". Sau đó người dùng nói "bỏ khóa tháng đi"; Claude hỏi lại phạm vi, người dùng chọn "Chỉ máy bỏ qua khóa".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi code app (`v7_sheet_queue.py`, `v7_inbox.py`, `v7_api_sheet.py`), không đổi DB, quyền hay phân bổ. Cần `WEBDEBIT_AUTO_SHEET` có `text` (việc A) và `trips` (việc B); trên `hao` đã bật cả hai. Mốc 10/2026 là hằng `AUTO_LOCKED_TRIPS_FROM` trong `v7_inbox.py`. Lên `hao` theo lượt `Deploy hao` của PR; máy chạy ở lượt hộp việc kế tiếp.

Cùng đợt sửa luật "container ở khách khác": chỉ báo khi chuyến web của khách kia **cách dòng Sheet không quá 3 ngày** (cùng luật ±3 ngày với sổ gốc). Trước đó luật chỉ so container, nên mỗi chuyến máy dán có container dùng lại làm dòng cũ ở sổ khác bật đỏ nhầm.

**Rà máy tự ghi 4/11/2026 (Claude, không đổi luật):** mở, ghi, khóa lại là ba lệnh riêng. API tắt giữa chừng (mỗi lần triển khai) thì tháng nằm mở, và lượt sau thấy tháng đang mở nên không khóa lại. Từ nay lượt nền khóa lại tháng mà lần đổi khóa gần nhất là máy mở, cũ hơn 10 phút; tháng người mở giữ nguyên. Đo trên `hao` lúc rà: 99/99 lần máy mở đã khóa lại, chưa tháng nào bị bỏ mở. Cùng đợt: "Máy đã tự làm hôm nay" nạp lại từ Lịch sử ở lượt đầu sau khi API khởi động lại (trước đó chỉ ở RAM, mất mỗi lần triển khai), và mỗi lỗi của máy ghi một dòng journal.

**Thử trên bản sao DB của `hao` (3/11/2026):** chạy máy cho cả 236 sổ.
- Không lỗi; tổng nợ mọi sổ 64.729.039.261 trước và sau, không sổ nào đổi số dư.
- Mọi tháng máy mở đã khóa lại; tháng đang mở sẵn giữ nguyên.
- Máy điền ngày 57 dòng sổ gốc và đưa 52 chuyến tháng 10 vào sổ (không chuyến nào vào chờ kiểm).
- Hàng chờ từ 152 còn 43 dòng, đều là việc người quyết nêu ở trên.
