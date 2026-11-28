# KHACH-THANG-02

[← Sổ quyết định](../decisions.md)

## Quyết định

Mỗi bảng khách của Tổng quan chỉ dùng **một mốc thời gian**. Người dùng chốt ngày 28/11/2026 trong phiên ("Làm phương án A"), sau khi xem phân tích so với chuẩn ngành và phác thảo dữ liệu giả. Lý do: bảng lọc tháng cũ trộn bốn mốc thời gian trong một dòng (tháng nợ, ngày thu, nợ của tháng đo tới hôm nay, số hôm nay) và ba nghĩa của chữ "Còn nợ", nên cộng trừ theo hàng không ra.

1. **Đang lọc tháng:** bảng là sổ tháng, giống thanh tháng của Sổ khách ([`SO-GON-05`](so-gon-05.md)) và bảng tổng hợp công nợ của phần mềm kế toán: **Nợ đầu tháng + Phát sinh − Đã thu = Còn nợ cuối tháng**. Mỗi dòng tự khớp.
   - Bỏ cột "Còn nợ Tx" (phần phát sinh của tháng chưa trả). Tiền thu trừ nợ cũ trước, nên với khách còn nợ cũ, số này luôn bằng phát sinh và đọc như "thu rồi mà nợ không giảm". Số này vẫn có ở Công nợ theo tháng.
   - Bỏ các cột số hôm nay: Quá hạn, Còn nợ, Trả, Đi hàng.
   - Điều này thay cách hiểu "còn nợ của tháng" trong phần ĐỀ XUẤT của [`KHACH-THANG-01`](khach-thang-01.md).
2. **Không lọc tháng:** mọi cột vẫn là số hôm nay như cũ.
   - Hai cột ngày đổi nhãn thành "Trả gần nhất" và "Chuyến gần nhất".
   - Ô ghi "27 ngày trước"; quá 90 ngày thì đếm tháng. Chưa trả hoặc chưa có chuyến thì ghi "chưa có".
   - Ngày cụ thể nằm ở chú thích khi rê chuột.
   - Chú giải màu của ô hiện sẵn dưới bảng.

Claude chọn phần cách làm (ĐỀ XUẤT, trong phạm vi trên):

- Máy chủ tính nợ đầu tháng và còn nợ cuối tháng theo đúng phép của `get_ledger`:
  - còn nợ cuối tháng = tổng còn nợ trừ (phát sinh − đã thu) của các tháng sau;
  - nợ đầu tháng = còn nợ cuối tháng − phát sinh + đã thu.

  Tháng hiện tại chưa hết thì còn nợ cuối tháng là còn nợ đến hôm nay.
- Tập sổ của tháng giữ như `KHACH-THANG-01`.
- Không thêm cột tăng/giảm. Tiền vẫn rút gọn tỷ/triệu như cả trang. Nợ đầu/cuối tháng âm ghi "dư …".
- Bốn cột tiền của tháng đều bấm được để xếp:
  - mặc định xếp phát sinh nhiều trước;
  - tham số trên địa chỉ: `?xep=no-dau`, `phat-sinh`, `da-thu`, `no-cuoi`.
- Tiêu đề khối khi lọc tháng đổi thành "Khách tháng 9/2026".
- Trên điện thoại bỏ cột Nợ đầu tháng (tính lại được từ ba cột kia), để cột Còn nợ cuối tháng luôn nằm trong màn.

## Phạm vi

Chỉ đọc. Phạm vi gồm:

- Hàm `sokhach.get_month_customers(date)`: thêm hai trường `prior_months_vnd` và `end_of_month_vnd` cho từng sổ (migration `2026-11-28-v7-khach-thang-so-thang.sql`). Tên trường giống thanh tháng của `get_ledger`.
- Trang Tổng quan.

Không đổi tiền, phân bổ, quyền hay dữ liệu. Spec: [`v7-tim-cont-khach-thang`](../../specs/v7-tim-cont-khach-thang.md#sổ-tháng-khach-thang-02-28112026).

## Trạng thái

ĐÃ CHỐT 28/11/2026 (phương án A). Cách làm ở trên là ĐỀ XUẤT của Claude.

ĐÃ KIỂM CHỨNG trên bản sao `webdebit_v7` của `hao` (28/11/2026, DB thử đã xóa):

- So 23 tháng, từ 1/2025, gồm 834 dòng sổ × tháng.
- Nợ đầu/cuối tháng lệch so với thanh tháng của `get_ledger`: 0 dòng. Sai đẳng thức: 0 dòng.
- Tập sổ và ba số cũ (phát sinh, đã thu, còn nợ của tháng) không đổi so với hàm cũ.
- Tháng hiện tại: còn nợ cuối tháng bằng còn nợ hôm nay ở 44/44 sổ.

CÒN MỞ: triển khai lên `hao`; người dùng tự xem trên `hao`.
