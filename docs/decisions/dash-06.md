# DASH-06

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan là màn để **C-level theo dõi công nợ của công ty**, không phải danh sách đi đòi nợ. Người dùng chốt bốn điểm:

1. **Chia khách đang nợ theo tình trạng**, thay ba mức rủi ro của [`DASH-03`](dash-03.md) mục 2. Khách có nợ quá hạn vào một trong bốn nhóm, dựng từ hai dữ kiện đã có trên bảng (còn đi hàng không, còn trả tiền không) và nợ cũ:
   - **Vẫn đi hàng, không trả**: có chuyến trong 30 ngày qua, và hơn 60 ngày chưa trả hoặc chưa trả lần nào.
   - **Ngừng đi hàng, không trả**: không có chuyến trong 30 ngày qua (kể cả chưa có chuyến), và hơn 60 ngày chưa trả hoặc chưa trả lần nào.
   - **Vẫn trả, còn nợ cũ**: có trả trong 60 ngày qua, còn nợ quá hạn từ 3 tháng.
   - **Vẫn trả, quá hạn ngắn**: có trả trong 60 ngày qua, nợ quá hạn dưới 3 tháng.

   Khách không có nợ quá hạn vẫn là **Không quá hạn** ([`DASH-05`](dash-05.md) điểm 4). Khối khách đổi tên thành **"Nợ quá hạn nằm ở đâu"**: mỗi nhóm một ô bấm để lọc bảng (thay chip mức rủi ro của DASH-05), bảng chia theo nhóm, cột chữ **"Quá hạn lâu nhất"** thay thanh "Theo hạn trả". Nhãn trên thẻ Tình hình của trang khách đổi theo để hai nơi gọi một khách như nhau. Màn chỉ ghi dữ kiện, không gợi ý việc, như [`TINH-HINH-01`](tinh-hinh-01.md).
2. **Mở lại "không so tháng trước"** của DASH-03 mục 4: Tổng quan có **hình 12 tháng cho cả công ty** gồm phát sinh, đã thu và còn phải thu cuối tháng. Cách tính giống hình 12 tháng của thẻ Tình hình, cộng qua mọi sổ.
3. **Mốc "vẫn đi hàng" là 30 ngày** (`active_trip_days`), không dùng mốc 90 ngày "ngừng đi hàng" của luật rủi ro cũ. Mốc trả 60 ngày và nợ cũ 3 tháng giữ như DASH-03.
4. **Sổ lớn lên đầu khối khách.** Hàng thẻ riêng trên các ô tình trạng, mỗi sổ một thẻ có tên, tiền quá hạn, tỷ lệ trên tổng quá hạn, tình trạng, ngày trả và đi hàng. Các ô và bảng không kể sổ lớn, nên mỗi số vẫn ở một chỗ. Đánh đổi đã biết: dòng đầu của bảng nằm dưới mép 560px, chỉ còn thấy đầu bảng.

ĐỀ XUẤT: mốc sổ lớn là quá hạn từ 10% tổng quá hạn, tối đa 4 thẻ; người dùng chọn trên bản xem có mốc này, chưa nói riêng về mốc.

ĐỀ XUẤT, chờ người dùng xem bản xem: hình 12 tháng thay chỗ thẻ Thu tháng ở dải đầu, vẽ thành hai hình chồng (đường còn phải thu ở trên, cột phát sinh / đã thu ở dưới, mỗi hình một thang); số thu / phát sinh tháng này còn ở dòng dưới hình. Chi tiết ở spec [`specs/v7-tong-quan-v4.md`](../../specs/v7-tong-quan-v4.md); bản xem dữ liệu giả [`preview/mockups/tong-quan-v4/`](../../cong-no-web-handoff/preview/mockups/tong-quan-v4/index.html).

CÒN MỞ: có đổi luật "còn nợ cũ" ở điểm 1 không, trước PR backend. Sổ giữ 17% tiền quá hạn vào nhóm này chỉ vì 1% nợ của nó đã từ 3 tháng ([spec, mục Số thật](../../specs/v7-tong-quan-v4.md#số-thật-trên-hao-6112026-chỉ-đọc-sau-khi-người-dùng-chốt)).

## Ngày / nguồn

6/11/2026, chat. Người dùng gửi hai bản "Khách cần đòi trước" team đề xuất và nói chưa ưng: "Dashboard này là để C-level theo dõi tình hình công nợ của cty". Claude chỉ ra hai bản vẫn trả lời câu "gọi ai trước": nhãn Rủi ro cao gom 10/12 khách mẫu (trên `hao` ngày 4/11 là 50/63 khách) vì chỉ cần một khoản quá hạn từ 3 tháng; bản chia theo chuyến cuối để khách vẫn chạy hàng mà không trả nằm ở ô xanh; Tổng quan không có chỗ trả lời nợ tăng hay giảm. Claude đưa phác thảo bốn nhóm, hỏi ba điểm đầu; người dùng trả lời "ok theo bạn đề xuất".

Điểm 4 cùng ngày: lúc chốt ba điểm đầu người dùng chỉ thấy khách mẫu. Đo trên `hao` sau đó thấy nhóm Vẫn trả, quá hạn ngắn giữ 48% tiền quá hạn (bản xem lúc đó 2%) và 3 sổ có quá hạn từ 10% tổng giữ 61%. Người dùng trả lời "Có, làm bản xem"; Claude dựng ba phương án trên dữ liệu giả đúng tỷ trọng, đề xuất B; người dùng trả lời "Chọn B". Phương án A (đánh dấu trong ô và dòng) và C (xếp nhóm theo tiền) không chọn.

## Hiệu lực và giới hạn

ĐÃ CHỐT bốn điểm trên. Thay mục 2 (mức rủi ro) và mục 4 (không so tháng trước) của DASH-03; hạn trả, 5 nhóm hạn trả, cách tính lần trả / đi hàng gần nhất và thu / phát sinh tháng này của DASH-03 giữ nguyên. Thay cách chia chip của DASH-05 điểm 1 (vẫn là chip bấm để lọc). Chưa code, chưa triển khai: cần thêm trường tình trạng và sổ lớn ở `get_dashboard_debt` và một hàm đọc 12 tháng cộng mọi sổ (spec, bước 5). Không đổi tiền, phân bổ, quyền ghi hay dữ liệu. Trạng thái triển khai ghi theo lượt `Deploy hao`.
