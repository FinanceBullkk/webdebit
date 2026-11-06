# Tương tác của Bảng thu và thẻ Tình hình

Trạng thái: **ĐÃ CHỐT** hành vi ([`TUONG-TAC-01`](../docs/decisions/tuong-tac-01.md), người dùng, 5/11/2026). Bản xem dữ liệu giả: trang "Tương tác" của canvas Claude Design. Sửa cách bấm của [`v7-bang-thu.md`](v7-bang-thu.md) và [`v7-trang-khach.md`](v7-trang-khach.md); phần còn lại của hai spec đó giữ nguyên.

## Vì sao

Người dùng chê hai màn "chưa có interactive". Quan sát trên code tại `0817497`:

- Bảng thu: chip khách, chip phiếu và thẻ Hôm nay chỉ có chú thích. Bấm cột ngày chỉ cuộn trang. Bong bóng số che số lớn của tháng khi rê các ngày đầu tháng.
- Tình hình: bấm số Quá hạn hay một tháng là rời trang sang thẻ Sổ ngay, chưa kịp xem. Bấm được mà không thấy trước số của tháng, rê chuột chỉ có chú thích của trình duyệt. Thẻ chỉ số và Hoạt động không bấm được.
- Hoạt động chỉ đọc `trips` và `receipts`, bỏ sót `legacy_rows`, nên dòng thu và chuyến từ sổ gốc không lên.

## Người dùng

Sếp và người đòi nợ xem một khách; người nhập xem tiền về. Trên 40 tuổi, màn 1280×560 nhìn thấy, vùng bấm ≥ 40px, tần suất hằng ngày. Cả hai màn chỉ đọc.

## Bảng thu

| Thao tác | Kết quả |
| --- | --- |
| Rê hoặc Tab tới cột ngày | Bong bóng nằm **dưới** dải ngày: ngày, số đúng tới đồng, số phiếu, số khách, gợi ý bấm. Không che số lớn. |
| Bấm cột ngày, đầu nhóm ngày, thẻ Hôm nay | Lọc một ngày. Nhãn "Thu 03/11", số lớn, hai chip và bảng theo ngày đó; cạnh nhãn vẫn ghi tổng tháng. Có chip `03/11 ✕`. Bấm lại cùng ngày hoặc ✕ để bỏ. |
| Đổi tab khi đang lọc | Giữ ngày. Tab 12 tháng không áp bộ lọc ngày; quay lại vẫn còn. |
| Đổi tháng | Bỏ lọc ngày và phần đang mở. |
| Chip khách, chip phiếu | Sang tab Theo khách, Theo ngày; chip của tab đang xem có nền xanh. |
| Rê hoặc Tab tới một dòng phiếu hay khách | Dải ngày tô đậm phần tiền của khách đó trong từng ngày. |
| Bấm tên khách ở tab gom nhóm | Mở phiếu của khách tại dòng: ngày, ghi chú, trừ nợ, số tiền, link "Mở sổ khách này". Một lúc một dòng. Dải ngày giữ tô đậm khi đang mở. |
| Mũi tên cuối dòng | Mở sổ đúng tháng như cũ. |
| Bấm dòng ở Theo ngày | Mở sổ đúng tháng như cũ. |
| Chip Không rõ ngày | Bỏ lọc ngày, sang Theo ngày, tới nhóm đó. |

Trạng thái: lọc ngày cộng với lọc mặt hàng mà không còn phiếu thì báo "Không có phiếu … ngày dd/mm" và vẫn còn chip ✕. Khi lọc ngày, ẩn nhóm không rõ ngày, cấn trừ và phiếu hủy vì chúng thuộc cả tháng; chip Không rõ ngày vẫn hiện. Ngày lọc ghi lên địa chỉ (`ngay=yyyy-mm-dd`) để Back từ sổ về đúng chỗ; ngày không thuộc tháng đang xem thì bỏ qua. Tự tải mỗi 60 giây giữ nguyên lọc và phần đang mở.

Dữ liệu: tất cả tính trên trang từ `days[].rows`, `customers[]`, `undated[]` của `GET /api/v7/receipt-book`. Không lọc ngày và mặt hàng thì số vẫn nguyên số server. Có lọc ngày thì cộng BigInt ở `bang-thu-model.js`.

## Thẻ Tình hình

Sửa theo [`TINH-HINH-01`](../docs/decisions/tinh-hinh-01.md) (6/11/2026): bỏ đổi hình, cột nhỏ Đi hàng, khung dữ kiện của nhãn rủi ro, khung việc cần xem và tab lọc Hoạt động.

| Thao tác | Kết quả |
| --- | --- |
| Quá hạn, Đến hạn, Chưa đến hạn, hoặc đoạn trên thanh màu | Mở khung ngay dưới: từng tháng nợ, số còn nợ, số ngày quá hạn hoặc còn lại tới hạn. Bấm dòng thì sang thẻ Sổ tháng đó. Một lúc một khung, có nút Đóng. |
| Mục ở dòng "Còn nợ chưa tính" | Sang thẻ Sổ đúng chỗ (`loc=`). |
| Rê hoặc Tab tới một tháng trên hình | Bong bóng bốn số: phát sinh, đã thu, còn nợ cuối tháng, chuyến. |
| Bấm một tháng | Ghim: tô cột, dải số của tháng, nút "Mở sổ T9", nút bỏ. Tiền về và hứa trả chỉ còn tháng đó, có chip `T9 ✕`. Bấm lại để bỏ. |
| Bấm một dòng Tiền về và hứa trả | Mở chi tiết: phần trừ nợ của phiếu, số tiền và ngày hẹn. Nút mở Sổ tháng đó hoặc thẻ Trao đổi. |
| Rê dòng Tiền về và hứa trả | Tháng của dòng sáng trên hình. |
| Xem thêm | Thêm 10 dòng ngay trong khối. |

Trạng thái: chưa đọc được Tổng quan thì nhãn và ba số giữ cách báo cũ, không có khung. Tháng không có dòng không bấm được, không thành 0. Khách trả trước không có nhãn và khung. Lọc không còn gì thì ghi "Không có … trong T9". Vẽ lại do nguồn phụ về sau hoặc khi ghi sổ không làm mất tháng đang ghim hay tiêu điểm; đổi khách thì bỏ hết. Bốn phần trên không gọi thêm API.

Dữ liệu:

| Khối | Nguồn | Ghi chú |
| --- | --- | --- |
| Từng tháng nợ | `dashboard/debt` dòng khách, `months[]` | Cùng tập với `tiers_vnd`, cùng cách xếp hạn: chậm = số tháng tính tới tháng này − 1. Hàm `debtTiers` kiểm cộng lại bằng `tiers_vnd`; lệch thì không hiện khung tháng, báo mở ở Sổ. |
| Dữ kiện nhãn | `oldest_open_month`, `last_receipt_*`, `last_trip_*` cùng dòng | Không có ngày đúng thì ghi "trong tháng M". |
| Hình 12 tháng | `months[]` của sổ qua `monthSeries` | Không đổi. |
| Chuyến mỗi tháng | `trips` + `legacy_rows` | Cùng cách đếm thẻ Đi hàng đang có. |
| Hoạt động | `receipts`, `trips`, `legacy_rows`, dấu Zalo, hội thoại Zalo | Thêm dòng sổ gốc. Dòng chưa sửa có thể không có `current` (khoản thu sổ gốc luôn vậy): số ở `source_total_vnd`, chữ ở `display`. Khoản thu sổ gốc thường không có ngày: ghi tháng của khối, xếp ở cuối tháng đó (cùng cách `pay_last` của `get_dashboard_debt`), không đoán ngày. |

Trễ trung bình sau hạn đã bỏ khỏi thẻ ([`TINH-HINH-01`](../docs/decisions/tinh-hinh-01.md)), trở lại khi có B1.

## Kiểm

- `test-bang-thu-model.js`: lọc ngày cộng đúng, khách trong ngày, phiếu của khách theo nhóm, phần của khách trong dải ngày.
- `test-tinh-hinh-model.js`: xếp tháng theo hạn, cộng bằng `tiers_vnd`, lệch thì báo; Hoạt động có dòng sổ gốc, không đoán ngày, dòng đã xóa không hiện; đếm chuyến.
- `test-bang-thu-browser.js`, `test-so-khach-v7-overview-browser.js`: các thao tác ở hai bảng trên, giữ trạng thái khi vẽ lại, Back từ sổ, 1265×560 và màn hẹp không cuộn ngang, vùng bấm ≥ 40px, font rộng hơn.
- Máy chủ giả, dữ liệu giả. Không phải bằng chứng live; người dùng tự đi hết luồng trên `hao` là bước cuối.
- Kiểm chỉ đọc trên `hao` 5/11/2026 (`b6d6ef5`): từng tháng cộng bằng `tiers_vnd` ở cả 69 sổ đang nợ; sổ lớn nhất không có lỗi trên trang. Lần này cũng bắt được lỗi khoản thu sổ gốc không lên Hoạt động vì dữ liệu giả khác dạng API thật; đã sửa ở PR sau.
