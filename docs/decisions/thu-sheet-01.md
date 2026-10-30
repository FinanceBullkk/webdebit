# THU-SHEET-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Phiếu thu trên Sheet lên web bằng hàng chờ, như giá: runner đọc tab khách, sổ khách có nút "Ghi N phiếu thu từ Sheet", người nhập bấm thì ghi cả lô qua lệnh ghi phiếu thu có sẵn. (1) Không cắt theo ngày mốc; phiếu đã có trên web nhận ra bằng ghép với dòng thu sổ gốc (tháng, số tiền, chữ ngày thu) và phiếu web (số tiền, ngày, lệch ≤ 3 ngày). (2) Không tự ghi khi: Sheet không ghi ngày thu, ngày thu sau hôm nay, cùng tháng còn dòng thu sổ gốc không thấy trên Sheet (Sheet đã sửa phiếu cũ), phiếu trùng dòng sổ gốc đã xóa trên web, tab có lỗi cấu trúc. (3) Hình thức `THU TIỀN`, chứng từ "Sheet: <chữ ngày thu>". (4) Phân bổ theo nợ cũ trước như mọi phiếu.

## Ngày / nguồn

30/10/2026. Người dùng chọn "Làm đồng bộ phiếu thu" trong chat sau đối soát chỉ đọc cùng ngày; quy tắc (1)–(3) do Claude đề xuất theo [`CLAUDE-ALL-01`](claude-all-01.md), dựa trên số đo trong [spec](../../specs/v7-receipt-queue.md).

## Hiệu lực và giới hạn

ĐÃ CHỐT hướng; quy tắc ghép là ĐỀ XUẤT tới khi người dùng đi hết luồng trên sổ thật. Không đổi luật tiền, không migration. Áp dụng trong thời gian chạy song song ([`SONG-SONG-01`](song-song-01.md)); xét lại khi chuyển hẳn sang web.
