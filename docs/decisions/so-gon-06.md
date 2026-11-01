# SO-GON-06

[← Sổ quyết định](../decisions.md)

## Quyết định

Sổ khách live (UX bước 04, đợt 2; spec [`v7-so-khach-mot-thang.md`](../../specs/v7-so-khach-mot-thang.md) mục "Đợt 2"):

1. **Phiếu thu lên đầu tháng.** Danh sách phiếu thu của tháng là một khối riêng ngay dưới thanh tháng: "Tiền khách trả tháng …", bảng ba cột (ngày trả, hình thức, số tiền kèm tham chiếu và tháng trừ nợ). Bảng chuyến bên dưới dùng hết bề ngang; tiêu đề cột của sổ không còn ba cột thu. Tháng không có phiếu chỉ còn dòng "… : chưa có phiếu thu". Dòng Tổng tháng chỉ còn phụ phí và Thành tiền; Đã thu ở dòng tóm tắt của thanh tháng.
2. **Một thanh việc ở đầu sổ.** Gộp các dải dưới đầu trang thành một thanh: bên trái là việc cần làm (duyệt chuyến, giá và phụ phí từ Sheet cần xem…), bên phải là giờ Sheet, Làm mới và nút "Cài đặt ▾" (cài đặt phụ phí, bảng giá, ẩn con trỏ).

## Ngày / nguồn

1/11/2026, chat. Sau `SO-GON-05` người dùng nói "thấy vẫn chưa ổn" và chọn hai chỗ: "Ba thanh đầu sổ rối", "Cột thu tiền trống". Claude đưa phác thảo từng chỗ; người dùng chọn "Lên đầu tháng (đề xuất)" và "Một thanh việc (đề xuất)".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thay vế "phiếu thu là danh sách riêng **bên phải**, dính khi cuộn" của [`SO-GON-02`](so-gon-02.md) và [`SO-GON-04`](so-gon-04.md) (vẫn là danh sách riêng, không chung hàng với chuyến). Thay sửa (a) của `SO-GON-04` (Cài đặt phụ phí, Bảng giá luôn thấy ở dải dưới đầu sổ, không có menu): nay nằm trong "Cài đặt ▾". Chỉ đổi giao diện trang live; không đổi luật tiền, phân bổ, khóa tháng hay lệnh ghi. Trang mẫu fixture `so-khach-v7.html` giữ nguyên.
