# DASH-07

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan có khối **"Công nợ theo mặt hàng"** luôn hiện, đặt giữa dải đầu và bảng khách, rộng cả trang:

1. Mỗi nhóm mặt hàng một dòng, chia hai cột: tên · thanh dài theo còn phải thu (cùng thang = nhóm nhiều tiền nhất; phần xanh trong hạn, phần đỏ quá hạn, cùng màu ngoặc Trong hạn / Quá hạn của dải đầu) · **Còn phải thu** · **Quá hạn** (đỏ; không có thì "–") · số khách. Tiền rút gọn tỷ/tr như dải đầu.
2. Nhóm giống ô lọc mặt hàng cũ (`DashboardModel.commodities`): sầu riêng tách cảng/bộ; mặt hàng dưới 1% còn phải thu gộp **Khác** (chú thích kể tên); sổ chưa gán mặt hàng hoặc sầu riêng chưa ghi cảng/bộ là **Chưa phân loại**. Nhiều tiền trước, Khác rồi Chưa phân loại cuối.
3. **Bấm dòng = lọc bảng khách** theo mặt hàng (bấm lại bỏ), kết hợp với lọc hạn trả và mức rủi ro; dòng khác mờ đi; hàng chip có thêm chip "Tên mặt hàng ✕" để bỏ lọc. **Bỏ ô chọn mặt hàng (phễu)** ở đầu bảng khách vì khối mới đã làm việc đó. Địa chỉ `?mh=` và link cũ `?nhom=com:` giữ.
4. Khối chỉ hiện khi số từng khách khớp tổng của server (cùng điều kiện cho lọc tại chỗ), nên các dòng cộng lại đúng bằng Còn phải thu của dải đầu. Lọc không đổi số trên khối. Quá hạn âm của khách dư ở nợ cũ được trừ trong số Quá hạn của nhóm; thanh chỉ vẽ phần dương.
5. Đánh đổi đã chọn: ở khung 1280×560, khối nằm trọn trong màn (tới 8 nhóm) nhưng bảng khách xuống dưới mép màn.

Không đổi API, không SQL: dữ liệu lấy từ `GET /api/v7/dashboard/debt` (`customers[].commodity`, `transport_mode`, `outstanding_vnd`, `overdue_vnd`). Spec: [`specs/v7-tong-quan-v3.md`](../../specs/v7-tong-quan-v3.md), mục Khối Công nợ theo mặt hàng.

## Ngày / nguồn

9/11/2026, người dùng trong chat: "dashboard tổng quan đang thiếu công nợ theo mặt hàng". Claude dựng bản xem hai phương án trên code thật với dữ liệu giả (A: nút chuyển Hạn trả | Mặt hàng ở dải đầu, bảng khách vẫn trong màn; B: khối riêng luôn hiện, bảng khách xuống dưới mép màn). Người dùng chọn **B** sau khi xem ảnh và bản bấm thử. Bỏ ô chọn mặt hàng (điểm 3) là hệ quả của "mỗi thao tác một chỗ", Claude quyết theo [`CLAUDE-ALL-01`](claude-all-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thêm vào trình bày của [`DASH-05`](dash-05.md); bỏ phễu mặt hàng của `DASH-05`. Quy tắc tính của [`DASH-03`](dash-03.md) không đổi. PR frontend của [`DASH-06`](dash-06.md) phải giữ khối này giữa dải đầu và khối "Nợ quá hạn nằm ở đâu", không đưa lại select mặt hàng. Bản xem dữ liệu giả: [`preview/mockups/tong-quan-mat-hang/`](../../cong-no-web-handoff/preview/mockups/tong-quan-mat-hang/index.html). Trạng thái triển khai ghi theo lượt `Deploy hao`. CÒN MỞ: người dùng tự xem trên `hao`; số nhóm thật trên `hao` hơn 8 thì khối vượt mép 560px.
