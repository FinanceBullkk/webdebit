# V7: đo tỉ lệ ghép giá Sheet → web (chỉ đọc)

Trạng thái: ĐỀ XUẤT công cụ đo (người dùng đồng ý làm trong chat 27/10/2026). Chưa có hàng chờ giá, chưa có đường ghi. Không đổi luật tiền.

## Mục đích

Trước khi làm hàng chờ "Ghi N giá", đo trên dữ liệu thật bao nhiêu dòng chuyến trong tab khách ghép được **đúng một** chuyến web hoặc dòng sổ gốc. Nếu tỉ lệ thấp thì phải đổi khóa ghép trước khi làm giao diện.

## Khóa ghép

- Tab khách **không có cột booking**, nên khóa là container + ngày, so trong cùng khách.
- Khách: tên tab khớp tên sổ web (chỉ chuẩn hóa khoảng trắng). Nếu không khớp thì xét tên hiển thị theo Sheet và tên phụ (`display_name`, `aliases` của `/api/v7/customers`). Tên phụ trùng ở hai sổ thì bỏ, không đoán. Cột `customer_basis` ghi `name` hoặc `alias`.
- Ngày khớp đúng trước (`exact_date`). Không có thì xét lệch tối đa 3 ngày (`near_date`), giống ngưỡng JOIN-01.
- Dòng Sheet **không có ngày** (chủ yếu lịch sử cũ): ghép theo container trong cùng khách (`container_only`), chỉ khi container đó có đúng một dòng web. Dòng Sheet có ngày không bao giờ rơi về cách này.
- Báo cáo ghi rõ dòng nào ghép theo cách nào.
- Không dùng số dòng Sheet làm khóa.
- Không xét chuyến web đã xóa hoặc đã loại (`rejected`).

## Trạng thái mỗi dòng Sheet

| Mã | Nghĩa |
| --- | --- |
| `READY` | Đúng 1 dòng web, web chưa có giá, tháng mở |
| `MONTH_LOCKED` | Như `READY` nhưng tháng đang khóa (24/10: cột giá chỉ đọc) |
| `PRICE_UNCHANGED` | Đơn giá giống; chuyến web: phụ phí giống (trống = 0 khi có giá, theo `V7-BE`); dòng sổ gốc: tổng tính tiền (`counted_vnd`) bằng ô TOTAL của Sheet, vì sổ gốc không lưu riêng phụ phí như giảm trừ âm |
| `CONFLICT` | Web đã có giá khác Sheet |
| `PENDING_REVIEW` | Chuyến web đang CHỜ KIỂM |
| `AMBIGUOUS` | Khớp nhiều dòng web, hoặc nhiều dòng Sheet cùng trỏ một dòng web |
| `NOT_FOUND` | Không có dòng web cùng container và ngày (±3) |
| `NO_CUSTOMER` | Tên tab không có trên web |
| `SHEET_NO_PRICE` | Sheet chưa có đơn giá: giữ NULL, không có gì để ghi |
| `NO_CONTAINER` | Dòng phí lẻ không container: ngoài phạm vi |

## Đầu ra

`v7_price_match.py --xlsx <bản tải Sheet> (--ledger-json <thư mục> | --api <URL> --serve-host <host>) --out <thư mục mới ngoài repo>`

- `price_match_rows.csv`: từng dòng, gồm giá Sheet, giá web, trạng thái, cách ghép, dòng web đích.
- `summary.json`: đếm theo trạng thái và cách ghép, hash đầu vào.
- `price_match_report.html`: bảng đếm và danh sách dòng cần xem (bỏ dòng giá đã giống).
- Màn hình chỉ in số đếm, không in tên hay tiền.

## Kiểm

`tests/test_v7_price_match.py`: test từng trạng thái, ưu tiên ngày khớp đúng, dòng sổ gốc, CLI đọc xlsx giả và từ chối thư mục ra trong repo hoặc đã có. `npm run check`.

## CÒN MỞ

- Chưa chạy trên dữ liệu thật: cần bản tải Sheet mới nhất và đường đọc web (API qua Tailscale hoặc JSON sổ khách).
- Có số liệu rồi mới viết spec hàng chờ giá và mockup.
