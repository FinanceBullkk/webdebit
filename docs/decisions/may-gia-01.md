# MAY-GIA-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **máy tự ghi giá Sheet, không cần người bấm, ở mọi tháng: cả tháng đang mở lẫn tháng đã khóa.** Thay vế "giá từ Sheet vẫn do người bấm ghi ở hộp chung" của [`HANG-CHO-01`](hang-cho-01.md) Q5. Phiếu thu từ Sheet (Q3) vẫn do người bấm.

Máy chỉ ghi dòng giá đã chắc chắn, tức đúng các dòng nút "Ghi N giá từ Sheet" vẫn ghi ([spec](../../specs/v7-price-queue.md)):
- dòng Sheet ghép đúng một chuyến web hoặc một dòng sổ gốc của cùng khách;
- web chưa có giá, hoặc chỉ đổi giảm trừ âm khi đơn giá giữ nguyên;
- không có phụ phí gõ tay, không phải chuyến chờ kiểm.

Thêm cả dòng **chỉ vướng tháng khóa** (`MONTH_LOCKED`). Với tháng khóa, máy làm như [`MAY-KHOA-01`](may-khoa-01.md): **mở khóa tháng, ghi, khóa lại ngay**, bằng các lệnh có sẵn, gom một lần mở/khóa cho cả tháng. Mọi lệnh vào Lịch sử với người làm là "Máy (theo Sheet)". Lệnh ghi lỗi thì máy vẫn khóa lại.

Vẫn để người quyết: giá Sheet khác giá web (`CONFLICT`), nhiều chuyến khớp một dòng (`AMBIGUOUS`), phụ phí gõ tay hoặc giá âm (`MANUAL`), dòng người đã bấm "Giữ giá web" ([`VCL-GIU-01`](vcl-giu-01.md)).

**Điều kiện an toàn Claude thêm:** máy chỉ ghi giá cho tháng nợ **từ 10/2026** (tháng nạp V7), cùng mốc với việc B của `MAY-KHOA-01`, kể cả khi tháng cũ đang được ai đó mở. Trước đó sổ gốc là chuẩn, nên giá tháng 1–9/2026 vẫn để người.

## Ngày / nguồn

3/11/2026, chat. Đối soát chỉ đọc lúc 20:19 cho ra `KHONG DAT`: 212/236 khách khớp. Claude đo trên `hao` (chỉ đọc, 236 sổ): 53 dòng giá Sheet kẹt `MONTH_LOCKED` ở 11 sổ, đều thuộc tháng 10/2026 (đã khóa từ 1/11). Trong đó 41 chuyến web và 12 dòng sổ gốc, chưa dòng nào có giá trên web; ghi hết thì tổng nợ tăng 2.842.302.125đ. 9 trong 20 khách lệch tổng có dòng loại này.

Claude hỏi cách ghi, ba phương án: (1, đề xuất) người bấm, máy mở rồi khóa tháng; (2) máy tự ghi luôn; (3) giữ chặn, thêm nút mở khóa tại dòng. Người dùng chọn "Máy tự ghi luôn". Claude hỏi tiếp phạm vi: chỉ tháng đã khóa (đề xuất) hay mọi tháng. Người dùng chọn "Mọi tháng, cả tháng mở".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi code app (`v7_price_queue.py` thêm tháng nợ của chuyến đích vào mỗi dòng giá; `v7_inbox.py` thêm việc máy ghi giá; giao diện Việc cần làm hiện giá máy đã ghi). Không đổi DB, quyền, luật ghép giá hay phân bổ: máy đi đúng `write_price_items` của nút, nên `edit_trip_price` / `edit_legacy_trip` vẫn phân bổ lại như khi người bấm.

Bật bằng `WEBDEBIT_AUTO_SHEET` có `prices` (gộp được với `text,trips`), mặc định tắt. Mốc 10/2026 là hằng `AUTO_PRICES_FROM` trong `v7_inbox.py`. Máy chạy ở lượt hộp việc khi bản chụp Sheet đổi (runner giá 15 phút một lần). Khi bật `trips`, chuyến máy vừa đưa vào sổ nhận giá Sheet ngay trong cùng lượt.

Giá máy đã ghi hiện ở mục "Máy đã tự làm hôm nay" của tab Việc cần làm để người nhập soát. Ghi sai thì sửa giá tại ô như hiện nay (tháng khóa: mở khóa trước).

Hết hiệu lực khi chuyển hẳn khỏi Sheet, vì lúc đó web là sổ chính, không còn "theo Sheet".

**Cập nhật 4/11/2026:** máy ghi giá 15 phút một lần giữ nguyên phạm vi trên. [`MAY-DOI-SOAT-01`](may-doi-soat-01.md) thêm một đường riêng theo giờ: giá Sheet khác giá web ở mọi tháng được ghi khi đúng một tổ hợp việc đưa tổng khách về đúng tổng Sheet.
