# KHACH-MOI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan gắn cờ **khách mới** để người dùng để ý thu sớm, trước khi luật quá hạn của [`DASH-03`](dash-03.md) bắt được. Người dùng chốt mốc và chỗ hiện theo spec [`specs/v7-khach-moi.md`](../../specs/v7-khach-moi.md):

1. **Sổ mới:** chuyến đầu của sổ cách hôm nay (giờ VN) **≤ 60 ngày** (lúc đầu 90 ngày, xem Ngày / nguồn), không có lần trả nào sớm hơn chuyến đầu quá 7 ngày, và không có nợ mốc ở tháng trước tháng của chuyến đầu. Chuyến đầu và lần trả đọc cùng luật ngày với lần đi hàng, lần trả gần nhất của `DASH-03`.
2. **Chưa trả lần nào** (`no_pay`): sổ mới, đủ **30 ngày** từ chuyến đầu mà chưa có lần trả nào.
3. **Chuyến chậm trả** (`slow`): sổ mới có chuyến cũ nhất còn chưa trả đủ đã quá **45 ngày**. Tiền trả xếp vào chuyến theo nợ cũ trước, theo ngày chuyến; tiền chuyến tính như số dư (chuyến đã xác nhận, cộng điều chỉnh của chuyến).
4. **Chỗ hiện:** nhãn Mới ở bảng khách; ô lọc "Khách mới" ở Tổng quan (mọi sổ mới đang nợ, kèm số sổ cần để ý; sổ cần để ý xếp lên đầu), là một chiều lọc theo [`DASH-08`](dash-08.md); một dòng dữ kiện ở thẻ Tình hình của trang khách.
5. Cờ chỉ để tô màu và lọc. Không đổi nhóm hạn trả, mức rủi ro, tiền, phân bổ, khóa tháng hay quyền. Chưa làm nút "Không phải khách mới" cho sổ tách từ khách cũ; xem lại khi có sổ bị gắn nhầm.

Các mốc lấy từ phép đo chỉ đọc trên `hao` ngày 19/11/2026: gộp hai tín hiệu bắt đủ 12/12 sổ kẹt của 165 sổ mới đã đủ 180 ngày, ở trung vị ngày 30 kể từ chuyến đầu, trong khi luật quá hạn hiện tại bắt ở ngày 52. Đổi lại, khoảng 6/7 sổ bị gắn cuối cùng vẫn trả, nên đây là nhắc để ý, không phải nhãn đỏ (chi tiết ở mục Số đo của spec).

## Ngày / nguồn

19/11/2026, chat. Người dùng hỏi có cách cảnh báo để ý thu sớm khách mới không. Claude nêu vì sao luật hạn trả hiện tại không thấy khách mới trong gần 60 ngày đầu và đề nghị đo trước. Người dùng chọn "Đo rồi viết spec"; spec ĐỀ XUẤT ở PR FinanceBullkk/webdebit#502. Sau đó người dùng trả lời "Chốt, làm backend", tức chốt ba mốc 90 / 30 / 45 ngày và chỗ hiện như spec. Sau khi giao diện lên `hao`, người dùng hỏi xem danh sách khách mới ở đâu (ô lọc lúc đó chỉ có 3 sổ cần để ý trong 9 sổ mới đang nợ) và chọn "Thêm lọc": ô lọc đổi thành mọi sổ mới (điểm 4). Cũng ngày đó người dùng nói "giảm xuống còn 2 tháng thôi". Claude đo lại: với 60 ngày, trên hao còn 7 sổ mới đang nợ (thay vì 9) và 2 sổ cần để ý (thay vì 3, một sổ đang chậm trả rơi khỏi danh sách); trong dữ liệu cũ bắt được 11/12 sổ kẹt (thay vì 12/12). Claude đề xuất giữ "cần để ý" tới 90 ngày; người dùng chọn "Cả hai 2 tháng": mốc sổ mới là 60 ngày cho cả nhãn và cờ (điểm 1). Cùng ngày, sau review độc lập của PR backend, Claude thêm theo [`CLAUDE-ALL-01`](claude-all-01.md): loại sổ có nợ mốc trước tháng của chuyến đầu; tiền chuyến dùng để xếp tính như số dư (bỏ chuyến chờ duyệt, cộng điều chỉnh của chuyến).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Backend: `get_dashboard_debt` trả thêm `first_trip_day`, `first_trip_exact`, `is_new`, `new_flag`, `oldest_unpaid_trip_day` cho từng sổ đang nợ và ba mốc `new_*` trong `rule` (migration `2026-11-19-v7-khach-moi.sql`, triển khai tay theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md); ĐÃ TRIỂN KHAI trên `hao` 19/11/2026, [nhật ký](../deploys/2026-11-19-khach-moi.md)). Frontend (nhãn, ô lọc, dòng Tình hình) là PR riêng, chưa code. Trạng thái triển khai ghi ở nhật ký `docs/deploys/`. CÒN MỞ: một sổ không chắc là một khách ([`TRANG-KHACH-01`](trang-khach-01.md) K1); chưa có nhật ký lần đòi nên chưa đo được nhắc sớm có làm khách trả nhanh hơn không.
