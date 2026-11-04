# CONTAINER-DUNG-LAI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: dòng nguồn có container **đã có trong cùng sổ** mà không dòng nào trong sổ cách quá 3 ngày, máy coi là **chuyến mới** khi tab khách trên Sheet ghi riêng chuyến đó. Phải đủ cả hai điều kiện:

1. Tab của chính sổ có dòng cùng container, ngày lệch không quá 3 ngày so với dòng nguồn. Dòng đó cũng không được sát (trong 3 ngày) một dòng đã có trong sổ.
2. Số dòng của container đó trên tab **nhiều hơn** số dòng đang có trong sổ.

Không đủ thì dòng vẫn chờ người xem ("container đã dùng"), như trước. Đủ thì dòng đi tiếp qua các đường có sẵn: vẫn kiểm chuyến ở sổ khác, khách khác; máy chỉ tự đưa vào sổ khi đủ điều kiện cũ của `HANG-CHO-01` và `MAY-KHOA-01` (đúng mặt hàng, ngày không sau hôm nay, tháng mở hoặc từ 10/2026), chưa có giá; giá theo `MAY-GIA-01`. Tháng cũ hơn thì người bấm.

Bản chụp giá của Sheet hỏng hoặc chưa có thì coi như tab không có dòng nào: dòng vẫn chờ người.

## Vì sao không xét theo khoảng cách ngày

Đo trên `hao` tối 4/11/2026 (chỉ đọc) cả 17 dòng "container đã dùng" ở 8 sổ:

| Nhóm | Số dòng | Theo luật mới |
|---|---|---|
| Tab chỉ có một dòng, đúng là dòng đã có trong sổ: nguồn và tab lệch 4–20 ngày, tab không ngày, sai năm hoặc ngày lạ | 15 | Vẫn chờ người |
| Tab có dòng riêng cho chuyến mới | 1 | Chuyến mới |
| Tab chưa có dòng của chuyến mới | 1 | Chờ tới khi tab có |

Luật "cách trên 30 ngày là chuyến mới" sẽ cộng trùng 86.980.000đ ở hai sổ đang khớp Sheet, vì tab ghi sai năm hoặc ngày lạ. Một dòng trên tab là một khoản tiền đã tính, nên đếm dòng vững hơn so ngày.

## Ngày / nguồn

4/11/2026, chat. Sau khi đối soát báo một sổ thấp hơn Sheet 43.000.000đ, Claude tìm ra chuyến ngày 31/10/2026 bị giữ vì cùng container với dòng tháng 2 của chính sổ đó, khác nơi đi, khác giá, cùng booking với chuyến ngay trước. Người dùng chọn sửa luật cho máy; Claude rút lại gợi ý ban đầu theo khoảng cách ngày sau khi đo, đề xuất luật trên, người dùng duyệt.

Điều kiện "không sát dòng trong sổ" do Claude thêm khi code, chặt hơn bản đã duyệt, để hai dòng lặp trên tab không thành chuyến mới.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Chỉ đổi code app, không có migration; `paste_trips` vẫn tự đẩy chuyến nghi trùng sang "chờ kiểm". Không đổi quy tắc phân bổ. Không ghi Sheet.

Giới hạn:

- Chuyến mới bị giữ tới khi tab có dòng riêng. Trước lúc đó nó chưa có giá nên chưa làm tăng nợ.
- 15 dòng còn lại cần người xem nếu muốn hết hẳn; sổ đã khớp Sheet thì việc này được ẩn theo `MAY-DOI-SOAT-01`.
- Chỉ xét chuyến biển trong hàng chờ Sheet. Chuyến bộ (`NGUON-CHUYEN-01`) có luật riêng.
