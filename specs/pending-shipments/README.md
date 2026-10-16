# Cảnh báo chuyến chờ duyệt trong fixture

Trạng thái: ĐỀ XUẤT thay đổi hiển thị theo nguyên tắc pending đã chốt; không thêm chính sách tài chính. Phạm vi: workbench giả trong trình duyệt, không API/DB. Chủ yêu cầu: người dùng; triển khai và kiểm: Codex trong lượt 15/10/2026. Xem [quy tắc](../../docs/business-rules.md), [nguồn](../../docs/source-register.md) và [bằng chứng](../../docs/verification.md).

## Vấn đề và hành vi

Sau khi lưu chuyến có giá thành nháp, bảng có nhãn Chờ duyệt nhưng cảnh báo đầu trang chỉ đếm chuyến chờ giá và khoản thu chờ xác nhận. Người xem có thể bỏ sót chuyến chưa duyệt khi bảng tháng thu gọn.

Thêm liên kết `N chuyến chờ duyệt` trong cảnh báo đầu trang. Đếm riêng shipment có `status='draft'` đã lưu trong bộ nhớ tab, theo kỳ và ngày đang xem. Bấm vào phải mở đúng tháng và cuộn tới chuyến đầu tiên. Giữ riêng chờ giá và khoản thu; không đếm chuyến posted thành pending. Dòng đang gõ chưa lưu vẫn thuộc bảng nhập, ngoài bộ đếm này.

## Tiêu chí nghiệm thu

| ID | Tình huống | Kết quả cần có | Entry point / kiểm |
| --- | --- | --- | --- |
| P01 | Nhập ngày, container và giá hợp lệ, phí xác nhận 0; lưu nháp | Thêm đúng 1 chuyến chờ duyệt, có nhãn và link | `saveShipments` → `render`; test model + browser |
| P02 | Đóng tháng rồi bấm cảnh báo | Mở đúng tháng, chuyến đích nhìn thấy | `pending-shipment` click; browser |
| P03 | Lọc sang kỳ khác hoặc ngày trước chuyến | Cảnh báo chuyến chờ duyệt ẩn khi không thuộc phạm vi | `snapshot(state)` → `render`; browser |
| P04 | Dòng thiếu giá, dòng posted, dòng sai tiền | Chờ giá riêng; posted không đếm; sai tiền giữ ở editor | Model + browser |
| P05 | Trước/sau lưu nháp và đổi bộ lọc | Tổng đã ghi không đổi; không tạo payment/posting | Model + browser |

Không sửa schema, opening, phân bổ, quyền duyệt hoặc backend. Không dùng trạng thái UI như chứng cứ đã thu tiền. Khôi phục bằng việc bỏ phần cảnh báo và test của thay đổi này; không có dữ liệu bền vững cần rollback. Các P0 ghi tiền trong [quyết định](../../docs/decisions.md) vẫn CÒN MỞ.

## Kết quả triển khai

ĐÃ TRIỂN KHAI trên fixture cục bộ; ĐÃ KIỂM CHỨNG P01–P05 bằng model và Chromium trên clone mới của `75b3ecc4ee023705473cb240841097adc42c48ac`. Regression thất bại trước sửa và đạt sau sửa; xem [bằng chứng](../../docs/verification.md). Chưa triển khai vào runtime hoặc DB thật.
