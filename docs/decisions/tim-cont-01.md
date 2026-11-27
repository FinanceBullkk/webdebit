# TIM-CONT-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Ô Tìm khách tìm được cả theo **số cont**. Người dùng chốt 28/11/2026 (chọn qua câu hỏi trong phiên):

1. Đặt ngay trong ô Tìm khách sẵn có ở menu trái (cả hộp đổi khách của Sổ khách), không làm ô tìm riêng.
2. Gõ số cont đủ hoặc vài số cuối; kết quả là các chuyến có số đó, bấm mở Sổ khách đúng tháng và tô dòng chuyến.

Claude chọn phần cách làm (ĐỀ XUẤT, trong phạm vi trên):

- Chỉ chuỗi có chữ số, 4–20 ký tự sau khi bỏ khoảng trắng mới hỏi máy chủ (tên khách hiếm có số); chờ 250 ms ngừng gõ.
- Khớp một phần, bỏ khoảng trắng, không phân biệt hoa thường; nguyên số trước, rồi ngày chuyến mới trước; tối đa 30 dòng.
- Gồm chuyến web chưa xóa, không bị loại (ghi "chờ kiểm" nếu đang chờ) và dòng chuyến sổ gốc theo bản sửa mới nhất ("sổ gốc"). Sổ lưu trữ không có.
- Sổ khách nhận `?cont=`: tô mọi chuyến web và dòng chuyến sổ gốc có đúng số đó (so sau khi bỏ ký tự không phải chữ/số), dùng chung thanh "Đến dòng tiếp" của `?loc=`.

## Phạm vi

Chỉ đọc; không đổi tiền, phân bổ hay dữ liệu. Hàm `sokhach.find_container(text)`, API `GET /api/v7/containers/find`, mở cho mọi login (`QUYEN-01`). Spec: [`v7-tim-cont-khach-thang`](../../specs/v7-tim-cont-khach-thang.md).

## Trạng thái

ĐÃ CHỐT 28/11/2026 (chỗ đặt, hành vi chính). Cách làm ở trên là ĐỀ XUẤT của Claude. ĐÃ TRIỂN KHAI trên `hao` 28/11/2026 ([nhật ký](../deploys/2026-11-28-tim-cont-khach-thang.md)); CÒN MỞ: người dùng tự đi hết luồng.
