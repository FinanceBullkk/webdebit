# DASH-05

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan theo bản **ít chữ** đã chốt trên canvas Claude Design (khung `TongQuanGon`): menu trái như các trang khác; **dải đầu** Còn phải thu (số lớn) + nút biểu tượng có số: số khách đang nợ, chuyến chưa giá, khách trả thừa; **thanh hạn trả** chỉ là hình, số mỗi nhóm nằm ở **5 ô** ngay dưới, ngoặc Trong hạn / Quá hạn là tổng phụ; thẻ **Thu tháng** (đã thu / phát sinh, vạch hôm nay, số ngày còn lại); **bảng khách** rộng cả trang. Bốn điểm người dùng chốt:

1. **Chia khách theo mức rủi ro bằng chip** Rủi ro cao · Theo dõi · Không quá hạn (số khách + tiền quá hạn) trên bảng; bấm chip = lọc bảng. Bỏ ma trận 2×2 trả × đi hàng của [`DASH-04`](dash-04.md). Ba chip cộng lại = số khách đang nợ.
2. **Bỏ ngăn kéo khách**; bấm tên khách mở trang khách ở thẻ Tình hình (`so-khach-v7-live.html?customer=<id>&the=tinh-hinh`). Thay tương tác "bấm khách mở ngăn kéo" của [`DASH-01`](dash-01.md)/[`DASH-03`](dash-03.md).
3. **Bảng khách ghi bằng triệu** (1.410 · 83,4), đơn vị "tr" ghi một lần ở đầu cột; số ngày ghi số trong viên màu, đơn vị "ngày" ở đầu cột. Số lớn ở dải đầu và chip vẫn rút gọn tỷ/tr. Thay quy tắc "bảng dùng tỷ" của `DASH-04`.
4. Khách không có nợ quá hạn gọi là **"Không quá hạn"**; "Trong hạn" chỉ dùng cho **tiền** chưa quá hạn (ngoặc trên thanh).

Bản ít chữ: thao tác phụ và số đếm là nút biểu tượng + số (làm mới, phễu mặt hàng, lịch → Công nợ theo tháng, hình người + số khách, thẻ giá chuyến chưa giá, ví khách trả thừa), câu đầy đủ ở chú thích khi rê chuột hoặc focus; nhãn để ra quyết định (Trong hạn/Quá hạn, nhóm hạn trả, mức rủi ro, đầu cột) vẫn bằng chữ. Điều này nới quy tắc "trang xem nút có chữ" riêng cho Tổng quan.

**Mỗi số một chỗ:** còn phải thu và số khách chỉ ở dải đầu; tiền từng nhóm hạn trả chỉ ở 5 ô (số khách mỗi nhóm khi rê chuột); tiền quá hạn theo mức rủi ro chỉ ở chip; từng khách một dòng. Nợ theo tháng, lý do chi tiết, hứa trả, nhắc nợ ở trang khách, không lặp ở Tổng quan.

Mọi quy tắc tính của [`DASH-03`](dash-03.md) giữ nguyên (hạn trả cuối tháng M+1, 5 nhóm, rủi ro cao = có quá hạn và quá hạn từ 3 tháng / hơn 60 ngày chưa trả / hơn 90 ngày không đi hàng, giờ VN, NULL khác 0). API không đổi, không SQL mới. Spec: [`specs/v7-tong-quan-v3.md`](../../specs/v7-tong-quan-v3.md).

## Ngày / nguồn

2/11/2026, người dùng chốt qua chat và trên canvas Claude Design (trang "Tổng quan": chọn đề xuất A, rồi lần lượt chốt bốn điểm trên, cuối cùng chọn bản ít chữ làm bản chính sau khi chê bản nhiều chữ "biểu diễn bằng text nhiều nên nhìn bị loạn"). Ghi và code 3/11/2026.

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thay phần trình bày của `DASH-04` (bốn khối, ma trận 2×2, bảng tỷ, chú giải chấm màu) và tương tác ngăn kéo của `DASH-01`/`DASH-03`; quy tắc tính của `DASH-03` vẫn hiệu lực. Lọc tại chỗ (nhóm hạn trả, mức rủi ro, mặt hàng) và soi sâu ở Công nợ theo tháng giữ. Trạng thái triển khai ghi theo lượt `Deploy hao`. CÒN MỞ: người dùng tự đi hết luồng trên `hao`.
