# BAO-CAO-THANG-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Web có tab **Báo cáo tháng** ở menu trái, chỉ để xem. Mỗi tháng trả lời: tháng này có những khách nào, loại nào (mặt hàng, biển hay bộ), đi bao nhiêu cont; đối chiếu ba nguồn là booking, Sheet sổ nợ và sổ web.

Người dùng chốt:

1. **Bố cục: bảng theo khách.**
   - Trên cùng là bảng tổng ba hàng Booking / Sheet / Web, chia theo Biển, Bộ, Tổng.
   - Dưới là một dòng cho mỗi khách. Bấm dòng thì bung danh sách cont.
   - Khách có lệch xếp lên đầu.
   - Phương án "việc cần xem trước, bảng theo khách thu gọn" không chọn.
2. **Có cột Web** (số chuyến trên sổ web) cạnh Booking và Sheet, để vẫn dùng được khi bỏ Sheet.
3. **Tháng theo ngày chuyến**, không theo khối tháng trên tab khách. Người dùng nói "phải lấy toàn bộ chuyến có ngày chuyến trong tháng 10".
4. **Hai tab của cùng một khách:** tab chép lại chuyến của tab kia với 0đ thì dòng 0đ đó không đếm là chuyến. Người dùng xác nhận một cặp tab như vậy là cùng một khách.

Claude chọn phần cách làm (ĐỀ XUẤT, áp dụng trong phạm vi trên):

- **Booking** là hai bản chụp `CONT_NGUON` (biển) và `CONT_BO` (bộ) đang có trên `hao`, ghép với Sheet bằng đúng luật của [`KIEM-BOOKING-01`](kiem-booking-01.md) / [`NGUON-CHUYEN-01`](nguon-chuyen-01.md) (1): cùng container, lệch không quá 3 ngày, một đối một.
  - Tháng của chuyến đã ghép theo ngày booking (ngày theo nguồn, NGUON-CHUYEN-01).
  - Chuyến chưa ghép theo ngày trên Sheet.
  - Dòng Sheet không ngày nằm ở khối tháng của nó, nhóm "Sheet không ghi ngày". Nhóm này không đếm là chuyến nhưng có tiền.
- **Bản chép 0đ:** dòng Sheet 0đ không ghép được, mà cùng container đã có dòng Sheet khác ghép booking cách không quá 31 ngày. Ngưỡng 31 ngày lấy theo nhóm lệch ngày của công cụ GĐ1. Đo 16/11/2026, khối tháng cũ để 0đ ngày 07/10 cho chuyến đã tính ngày 26/10.
- **Chuyến booking trước tháng đầu của tab khách** nằm trong số dư đầu kỳ, không cộng lại (`AGENTS.md`). Chỉ đếm, ghi một câu dưới bảng tổng.
- **Khoảng có số booking:** từ 12/2025, tháng đầu cả hai bản chụp cùng phủ. Tháng trước đó chỉ có cột Web.
- **Web:** chuyến có container của mọi sổ đang hoạt động, gồm cả dòng chuyến sổ gốc chưa xóa; chuyến web chưa xóa, không bị loại. Tên tab Sheet ghép với sổ web theo tên như trang Máy chạy. Chuyến web ghép với dòng Sheet cùng sổ, cùng container, lệch không quá 3 ngày. Chuyến web không ghép được hiện là "Chỉ có trên web".
- **Nhịp:** Booking và Sheet tính trong chính lượt kiểm booking mỗi giờ (không tải Sheet thêm). Web đọc lúc mở trang.

## Ngày / nguồn

16/11/2026, chat.
- Người dùng hỏi tháng 10 có những khách nào và cont trên Sheet có khớp booking không. Claude đối chiếu chỉ đọc trên `hao` và xuất file Excel; người dùng sửa cách đếm theo điểm 3 và 4.
- Người dùng nói "web của chúng ta cần 1 tab report như vậy", rồi chọn "Bảng theo khách (Đề xuất)" và "Có, thêm cột Web (Đề xuất)" trong hai câu hỏi có phác thảo.

Số đo chỉ đọc trên `hao` ngày 16/11/2026 (luật ở trên, trước khi nới ngưỡng bản chép):
- Tháng 10/2026, booking biển: 262 = 260 khớp + 2 Sheet chưa ghi. Booking bộ: 201 khớp đủ.
- 12 dòng chép 0đ; 2 dòng không ngày.
- 12/2025–11/2026: file báo cáo khoảng 1,9 MB.

## Hiệu lực và giới hạn

ĐÃ CHỐT bốn điểm của người dùng. Phần cách làm là ĐỀ XUẤT. ĐÃ TRIỂN KHAI trên `hao` 16/11/2026 ([nhật ký](../deploys/2026-11-16-bao-cao-thang.md)). Chỉ đọc: không ghi sổ, không ghi DB, không ghi Sheet. Không đổi luật tiền, luật ghép hay điều kiện máy ghi.

Mã:
- job `tools/v7_booking_check.py` (`month_report`, file `booking-report.json`);
- hàm đọc `sokhach.get_trip_month(date)` (migration `2026-11-16-v7-bao-cao-thang.sql`);
- API `GET /api/v7/report/month?month=YYYY-MM` (`web/v7_month_report.py`), sau xác thực danh tính;
- trang `preview/bao-cao-thang.html`.

Giới hạn:
- Ghép tab với sổ web theo tên: tab chưa có sổ web cùng tên không có link mở sổ và cột Web trống. Gộp tab chép vào tab chính ở đây nhờ luật bản chép 0đ, không nhờ bảng gộp tên.
- Ngày booking chỉ đọc được dạng `dd/mm/yyyy`. Dòng booking không có ngày đọc được không xếp vào tháng nào.
- Tháng đang chạy: chuyến mới thường lên Sheet chậm một hai ngày, nên trang ghi "Chưa lên Sheet" thay cho "Sheet chưa ghi".
- Menu trái nay có tám mục. Để tám mục lọt khung 1280×560, mục cao tối thiểu 48px thay 56px.
- CÒN MỞ: người dùng tự đi hết trang trên `hao`.
