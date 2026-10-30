# DASH-04

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan trình bày theo nguyên tắc **mỗi câu hỏi một hình, số nằm trong hình, không câu kết luận**. Bốn khối: **1. Nợ theo hạn trả** (gộp Còn phải thu: số headline + thanh lớn 5 đoạn có số trong đoạn, ngoặc trong hạn / quá hạn), **2. Thu tháng này** (thước đo đã thu / phát sinh với vạch hôm nay), **3. Khách cần đòi trước** (bảng: cột cơ cấu nợ cùng thang, quá hạn, còn nợ, hai cột số ngày chưa trả / đi hàng tô theo ngưỡng; chấm màu mức rủi ro, chú giải chữ một lần), **4. Khách quá hạn đang ở đâu** (ma trận 2×2 trả gần nhất × đi hàng gần nhất, bấm ô = lọc bảng). Mặt hàng thành bộ lọc dropdown trên bảng. Bỏ: ô "Khách rủi ro cao", dòng số đồng đầy đủ, câu kết luận, % dưới nhóm, câu lý do từng dòng, khối Phân loại 5 tab, tiêu chí Quy mô.

Mọi quy tắc tính của [`DASH-03`](dash-03.md) (hạn trả, 5 nhóm, mức rủi ro, lần trả/đi hàng gần nhất, thu tháng này) và tương tác đã chốt ở [`DASH-01`](dash-01.md) giữ nguyên; API không đổi. Spec: [`specs/v7-tong-quan-v2.md`](../../specs/v7-tong-quan-v2.md).

## Ngày / nguồn

30/10/2026, người dùng góp ý trong chat (Tổng quan "full of text", cần thiết kế lại ở mức kiến trúc), xem audit, bản gọn và layout thử v2 dữ liệu giả rồi chọn "Theo v2, viết spec".

## Hiệu lực và giới hạn

ĐÃ CHỐT. Thay phần trình bày của `DASH-03` (các câu "một câu kết luận", "một câu lý do", 5 tiêu chí phân loại); phần quy tắc của `DASH-03` vẫn hiệu lực. Ma trận 2×2 còn chờ người dùng tự nhìn trên bản thử; nếu không đọc hiểu, lùi về 4 thanh ngang cùng nhãn (không đổi dữ liệu). Trạng thái triển khai ghi theo lượt `Deploy hao` và nhật ký trong [`docs/deploys/`](../deploys/README.md).
