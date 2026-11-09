# DASH-08

[← Sổ quyết định](../decisions.md)

## Quyết định

Tổng quan **lọc chéo**: bấm ô hạn trả, chip mức rủi ro hoặc dòng mặt hàng thì mọi khối tính lại số theo lọc, không chỉ bảng khách. Thay câu "lọc không đổi dải đầu" của [`DASH-03`](dash-03.md)/spec v3 và "lọc không đổi số trên khối" của [`DASH-07`](dash-07.md).

1. **Mỗi khối lọc theo mọi lựa chọn, trừ chiều của chính nó**, nên khối vẫn hiện đủ lựa chọn của mình (cái đang chọn được tô), còn số thì tính lại theo các lọc khác:
   - dải đầu (Còn phải thu, số khách, ngoặc Trong hạn / Quá hạn, thanh và 5 ô): theo mức rủi ro và mặt hàng;
   - chip mức rủi ro (số khách, tiền): theo hạn trả và mặt hàng;
   - khối mặt hàng (từng dòng): theo hạn trả và mức rủi ro;
   - bảng khách: theo cả ba, như trước.
2. Đang lọc một nhóm hạn trả thì tiền trên chip và khối mặt hàng là **tiền thuộc nhóm đó** (cột khối mặt hàng đổi tên thành "Nhóm này"), giống cột đầu của bảng khách. Nhóm và thứ tự dòng mặt hàng giữ nguyên khi lọc; nhóm không còn khách ghi "–".
3. Khối đang tính theo lọc có **nhãn phạm vi** xanh cạnh tên (ví dụ "Sầu riêng cảng · Rủi ro cao"). Số cả công ty không tách theo lọc thì không hiện như số của phạm vi: dải đầu ẩn nút chuyến chưa giá và khách trả thừa khi đang lọc.
4. **Thẻ Thu tháng** lọc theo cả ba chiều từ thu / phát sinh tháng này từng sổ (`this_month.customers`): lọc mặt hàng tính cả sổ đã hết nợ của mặt hàng đó; lọc hạn trả hay mức rủi ro chỉ tính sổ đang nợ trong nhóm (sổ hết nợ không có nhóm). API chưa có số từng sổ thì thẻ giữ số cả công ty với nhãn xám **"cả công ty"**.
5. Lọc chéo chỉ chạy khi số từng khách khớp tổng server (`totalsMatch` + `riskMatches`), cùng điều kiện cho lọc tại chỗ đã có; không lọc gì thì mọi số là số của server như trước.

Backend: `get_dashboard_debt` trả thêm `this_month.customers` (hàm đọc, migration `2026-11-09-v7-thu-thang-theo-so.sql`, PR riêng, triển khai tay theo [`DEPLOY-CLAUDE-01`](deploy-claude-01.md)). Spec: [`specs/v7-tong-quan-v3.md`](../../specs/v7-tong-quan-v3.md), mục Hành vi.

## Ngày / nguồn

9/11/2026, người dùng trong chat: "hiện tại dashboard tổng quan chưa đủ interactive, có mấy cái vẫn bị tĩnh và chưa thay đổi theo lọc". Claude liệt kê khối nào tĩnh với từng lọc; người dùng chọn cả bốn khối phải tính lại (dải đầu + 5 ô, chip mức rủi ro, khối mặt hàng, thẻ Thu tháng). Quy tắc "trừ chiều của chính nó" và nhãn phạm vi do Claude quyết theo [`CLAUDE-ALL-01`](claude-all-01.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT. Trạng thái triển khai ghi theo lượt `Deploy hao` (frontend) và nhật ký `docs/deploys/` (migration). Frontend và migration độc lập: release mới trên DB cũ thì thẻ Thu tháng ghi "cả công ty" khi lọc. PR frontend của [`DASH-06`](dash-06.md) giữ quy tắc lọc chéo cho hàng ô tình trạng và thẻ 12 tháng. CÒN MỞ: người dùng tự đi hết luồng trên `hao`.
