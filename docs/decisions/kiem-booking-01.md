# KIEM-BOOKING-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt ba điểm cho phép kiểm "Sheet sổ nợ so với booking", lưới an toàn thay "khớp Sheet" khi chuyển hẳn (mục A6, F5 của [checklist chuyển hẳn](../chuyen-han-checklist.md)):

1. **Chỗ hiện:** một khối trong tab Máy chạy, dưới bảng "Các job trên máy chủ". Không phải trang riêng, không phải cột ở Việc cần làm.
2. **Nhịp:** mỗi giờ, trong chính lượt đối soát máy ([`MAY-DOI-SOAT-01`](may-doi-soat-01.md), :05 từ 7 tới 22 giờ), trên cùng bản tải sổ gốc. Không tải Sheet thêm, không có timer mới.
3. **Phạm vi:** theo hai bản chụp nguồn đang có trên `hao`: `CONT_NGUON` (chuyến biển) và `CONT_BO` (chuyến bộ). Chưa làm bản chụp booking 2025 (GĐ2 của [spec](../../specs/v7-chuyen-theo-nguon.md)).

Claude chọn phần cách làm (ĐỀ XUẤT, áp dụng trong phạm vi trên):

- **Luật ghép và phân nhóm:** đúng công cụ GĐ1 `v7_trip_source_match` ([`NGUON-CHUYEN-01`](nguon-chuyen-01.md) (1)).
- **Khoảng kiểm:** chuyến biển từ 12/2025, chuyến bộ từ 08/2025, theo số đo dưới đây. Trước các tháng đó không báo "không có booking" hay "booking có, sổ chưa tính".
- **Bảy nhóm trên trang**, theo thứ tự chủ sổ hỏi.
  - Bốn nhóm đụng tiền:
    - nghi tính hai lần (cùng ngày, lệch 1–3 ngày, đảo ngày/tháng);
    - booking có, sổ chưa tính (kể cả chủ hàng chưa ứng sổ nào);
    - sổ khác khách booking, chỉ chuyến biển: chuyến bộ lấy khách theo sổ, theo `NGUON-CHUYEN-01` (2);
    - trên sổ, booking không có.
  - Ba nhóm chỉ để biết: lệch ngày, sổ thiếu ngày, chuyến tháng này chưa lên sổ.
- **Chỉ đếm, không lên trang:**
  - chuyến trước tháng đầu của tab khách: nằm trong số dư đầu kỳ, không cộng lại (`AGENTS.md`);
  - "giá khác booking": bản chụp `CONT_NGUON` không mang cột giá chữ nên không tính được.
- **Chạy ở tiến trình con song song với lượt đối soát:** lượt không dài thêm, và lỗi của phép kiểm không làm đổ lượt.
- **Khi không tin được số:** bản chụp nguồn thiếu, hỏng, rỗng, hoặc cũ quá 3 giờ thì không kiểm. File kết quả giữ lượt đạt trước, thêm `last_error`. Trang chỉ ghi "không thấy chuyến nào…" khi lượt mới nhất đạt và còn mới.

## Ngày / nguồn

13/11/2026, chat. Phiên điều phối giao việc A6/F5. Claude viết bài toán của màn (chủ sổ hỏi gì, theo thứ tự) rồi hỏi bằng ba câu chọn. Người dùng chọn:
- "Khối trong Máy chạy" (Claude đề xuất trang riêng);
- "Mỗi giờ, cùng lượt đối soát";
- "Theo hai bản chụp đang có".

Số đo chỉ đọc trên `hao` cùng ngày (bản tải 13/11, release `2cbbe02`):

- **Bản chụp:**
  - `CONT_NGUON`: 5.726 dòng. Tháng 11/2025 mới có 87 chuyến; từ 12/2025 mỗi tháng có 349–704. 175 dòng mang ngày năm 1899–1902 (ô rác).
  - `CONT_BO`: 2.719 dòng, từ 08/2025 (tháng 07/2025 chỉ có 2 chuyến).
- **Một lượt:**
  - 7.308/7.641 dòng chuyến trong khoảng kiểm khớp booking.
  - Nhóm đụng tiền: nghi tính hai lần 62 dòng, booking có mà sổ chưa tính 115, sổ khác khách booking 23, trên sổ mà booking không có 45.
  - Nhóm để biết: lệch ngày 67, sổ thiếu ngày 231, tháng này 125.
  - 550 chuyến trước tháng đầu của tab khách (toàn bộ 08–12/2025) chỉ đếm.
- **Chi phí:** 160 giây, bộ nhớ đỉnh 286 MB. Trước khi đọc xlsx một lần cho cả tab TONG và tab khách là 252 giây.

## Hiệu lực và giới hạn

ĐÃ CHỐT ba điểm của người dùng. Phần cách làm là ĐỀ XUẤT. Chỉ đọc: không ghi sổ, không ghi DB, không ghi Sheet. Không đổi luật tiền, luật ghép hay điều kiện máy ghi.

Mã:
- job `tools/v7_booking_check.py`, gọi từ `tools/v7_reconcile_auto.py`;
- API `GET /api/v7/machine/booking` (`web/v7_booking_view.py`), sau xác thực danh tính;
- khối `preview/may-chay-booking.js`.

File `booking-check.json` (mode 600) có tên tab khách và số tiền, chỉ nằm trên `hao`. Stdout, journal và `reconcile-log.jsonl` chỉ có số đếm. Tắt nhanh: `WEBDEBIT_BOOKING_CHECK=off` trong env của unit đối soát.

Giới hạn:
- Chưa có nút xử lý. ĐỀ XUẤT cho bước sau: "Đã xem" hoặc "Giữ" theo từng dòng, để dòng đã kết luận không hiện lại mỗi giờ. Việc này cần nơi lưu và đường ghi riêng, nên chưa làm.
- Sửa ở đâu: Sheet sổ nợ vẫn là sổ chính thức ([`SONG-SONG-01`](song-song-01.md)), nên chỗ sai sửa trên Sheet; lượt sau tự cập nhật.
- Trang ghép tên tab với sổ web theo tên để có link mở sổ. Tab chưa có sổ web, hoặc hai sổ trùng tên, thì không có link.
- Trước 12/2025 (biển) và 08/2025 (bộ) chưa kiểm. Mở rộng cần bản chụp booking 2025.
- Khi chuyển hẳn khỏi Sheet, phép kiểm phải đổi sang so sổ web với booking. Mã ghép dùng lại được, nhưng đầu vào là sổ web thay cho xlsx.
- CÒN MỞ: người dùng tự đi hết khối trên `hao`.
