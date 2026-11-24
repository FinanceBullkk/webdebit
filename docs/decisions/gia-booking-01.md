# GIA-BOOKING-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **cột "Giá + phí (gốc)" của tab `CONT_NGUON` (file booking CHAU_HAO) là gợi ý, người bấm ghi.**

1. Ở nhóm "Chưa giá" của Việc cần làm, chuyến có giá booking hiện nút "Giá booking 38 tr + 1 tr". Bấm thì **điền ô giá**. Người vẫn bấm "Ghi giá" rồi "Xác nhận" như luồng hiện có; lệnh ghi giá, khóa chống trùng và Hoàn tác giữ nguyên.
2. **Máy không tự ghi giá booking.** Không đổi luật tiền, phân bổ, khóa tháng hay quyền.
3. Trong lúc chạy song song ([`SONG-SONG-01`](song-song-01.md)), giá Sheet vẫn là chuẩn như hiện nay: máy vẫn ghi giá Sheet theo [`MAY-GIA-01`](may-gia-01.md) và [`MAY-DOI-SOAT-01`](may-doi-soat-01.md). Giá người ghi theo booking mà khác Sheet thì thành việc "Giá khác", hoặc máy đối soát sửa theo Sheet.

Đổi vế "chỉ dùng để đối chiếu" của [`NGUON-CHUYEN-01`](nguon-chuyen-01.md) (3): chữ giá booking nay hiện cho người làm gợi ý. Máy vẫn không ghi.

**Cách làm (ĐỀ XUẤT của Claude, 24/11/2026; chi tiết ở [spec](../../specs/v7-gia-booking.md)):**

- **Đọc chữ.** Mọi phần tính bằng triệu đồng, phẩy hay chấm là dấu thập phân. Đơn giá là phần đầu, phụ phí là tổng các phần sau dấu "+": "38TR+1" là đơn giá 38 tr và phụ phí 1 tr. Không có phần sau "+" thì không có phụ phí (trống, không phải 0).
- **Ô máy không đọc chắc thì không thành số.** Đó là ô có phần không phải số (chữ, USD, RMB, "HC", ghi chú trong ngoặc), hay đơn giá ngoài 1 triệu – 1 tỷ đ. Màn chỉ hiện nguyên chữ ("Booking ghi: …") để người đọc rồi tự gõ.
- **Ghép chuyến** theo luật ±3 ngày của NGUON-CHUYEN-01 (1), chỉ với dòng booking đã gắn đúng sổ. Chỉ gợi ý khi chuyến ghép đúng một dòng, và dòng đó chỉ ghép một chuyến của sổ.
- **Phụ phí booking chỉ đi kèm khi chuyến chưa có phụ phí**, và chỉ khi ô còn đúng đơn giá đã điền. Người gõ số khác thì giá là của người, không kèm phụ phí booking. Bước xem lại nêu rõ đơn giá và phụ phí trước khi ghi.
- **Hàng tuyến có nút khi mọi chuyến của tuyến cùng một gợi ý.** Bấm thì điền cả tuyến như gõ ở ô tuyến ([GIA-TUYEN-01](../../specs/v7-gia-theo-tuyen.md)).

## Ngày / nguồn

24/11/2026, chat. Claude đề xuất dùng ô giá booking cho chuyến biển chưa giá. Người dùng chọn "Gợi ý, người bấm ghi", không để máy tự ghi.

Số đo chỉ đọc trên `hao` cùng ngày, chỉ số đếm:

- **Dạng chữ**, đếm theo hình dạng, 9 thay cho chữ số: `9TR` 2.630, `9TR+9` 977, `9.9TR` 119, `9,9TR` 81, `9TR+9+9` 20, `9TR+9 (TẾT)` 15, `HC +9TR` 8, `9TR+9USD` 5. Còn lại vài chục dạng lẻ (ghi chú, USD, RMB, "SUA BILL"…).
- **Tỷ lệ chuyến biển có ghi ô này**, theo tháng: 12/2025 304/390, 1/2026 337/403, 2/2026 380/448, 3/2026 635/704, 4/2026 547/605, 5/2026 535/598, 6/2026 362/427, 7/2026 374/605, 8/2026 159/511, 9/2026 17/349, 10/2026 65/262, 11/2026 102/221. Ô thưa dần từ 7/2026, nên gợi ý giúp ít hơn ở các tháng gần đây.
- **So với tab khách trên Sheet:** 3.672 chuyến đọc được giá và ghép đúng một dòng tab có giá.
  - 2.564 chuyến: phần đầu bằng đơn giá, tổng phần sau bằng phụ phí.
  - 831 chuyến (thêm 1 kiểu khác): tổng bằng, nhưng Sheet dồn cả vào đơn giá.
  - 69 chuyến: phần đầu bằng đơn giá, phụ phí khác.
  - 207 chuyến: khác hẳn.
  - 54 ô không đọc được thành số.

Gần một phần tư số chuyến Sheet ghi khác cách tách của booking, và vài phần trăm khác hẳn. Vì vậy giá booking không đủ chắc để máy tự ghi: người nhìn rồi quyết.

## Hiệu lực và giới hạn

ĐÃ CHỐT nguyên tắc (1)–(3), người dùng, 24/11/2026. Phần cách làm là ĐỀ XUẤT của Claude, chưa qua bước người dùng đi thử (bước 8 của spec).

Chỉ đổi code app:
- `webdebit_export_connector.py` đọc thêm cột tùy chọn; thiếu cột thì ô trống.
- `v7_sheet_queue.py` và `v7_api_sheet.py` trả `sheet_sync.booking_prices` trong `GET /api/v7/ledger`.
- Giao diện Việc cần làm.

Không đổi DB, lệnh ghi hay quyền. Triển khai tự động khi merge qua `Deploy hao`. Gợi ý có sau lượt đọc Sheet đầu tiên của runner (15 phút một lần) sau khi triển khai.

Giới hạn:
- Chỉ chuyến biển trong hàng chờ `CONT_NGUON` từ năm 2026 (`QUEUE_FIRST_YEAR`).
- Chỉ ở Việc cần làm, chưa có ở Sổ khách.
- Nhóm tuyến chưa tách theo hãng tàu: việc sau, lý do ở spec.
