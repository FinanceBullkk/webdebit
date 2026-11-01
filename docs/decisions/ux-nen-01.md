# UX-NEN-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt mục tiêu sản phẩm của web công nợ: **bỏ được Sheet mà không mất độ đúng**. Giá trị số 1 là hết ghi nhầm tiền ("phải đảm bảo những data input của chúng ta chuẩn 100%"). Mọi việc UX từ nay đo bằng năm chỉ số máy kiểm được, ghi ở mục 7 của [Nền UX](../ux-nen-nguoi-dung.md):

- **M1:** tổng nợ từng khách trên web bằng Sheet (236/236, liền một tháng).
- **M2:** mỗi container của booking sheet có đúng một chuyến (0 trùng, 0 sót).
- **M3:** giá chuyến lấy từ bảng giá hoặc nhập tay có người làm; 0 chuyến thiếu giá lọt vào tổng, giá lệch bảng giá được báo.
- **M4:** phiếu thu đúng khách, đúng số tiền; 0 phiếu hủy vì nhầm, phiếu nghi trùng được hỏi lại.
- **M5:** web chậm hơn nguồn không quá 1 ngày.

Mục tiêu phụ: sếp trả lời được "tổng nợ, ai nợ nhiều, ai quá hạn, ai cần đòi" ở một màn; người đòi nợ copy tin nhắc với số đúng.

Kèm theo là thứ tự làm UX người dùng đặt ra cùng ngày: người dùng và mục tiêu → cấu trúc thông tin và luồng → dễ dùng và tương tác → giao diện → kiểm với người dùng. Không sửa giao diện khi chưa qua bước trước.

## Ngày / nguồn

1/11/2026, chat. Người dùng trả lời câu hỏi bước 01 và chọn "Chốt, sang bước 02" cho M1–M5 do Claude đề xuất.

## Hiệu lực và giới hạn

ĐÃ CHỐT mục tiêu và thứ tự làm. Chưa triển khai phép kiểm nào; mức "hôm nay" của từng chỉ số ghi ở Nền UX. Không đổi luật tiền, phân bổ hay quyền ghi. Bản bấm thử "một tháng trên màn hình" (1/11) và mục H1 của [`SO-GON-04`](so-gon-04.md) xét lại ở bước giao diện, sau bước luồng.
